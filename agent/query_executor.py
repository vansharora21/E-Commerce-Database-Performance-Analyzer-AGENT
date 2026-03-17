"""
agent/query_executor.py
────────────────────────
Stage 3 of the pipeline.

Translates QueryPlan objects into actual Motor/MongoDB aggregation
pipelines and executes them safely and asynchronously.

Key safety constraints enforced at query-building time:
 - Only $match, $group, $sort, $limit, $project, $count stages.
 - No $out, $merge, $lookup (prevents data exfiltration).
 - Date ranges are computed server-side (not from the plan string).
 - Execution timeout of 10 seconds.
 - Results are capped at 100 documents.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from models import QueryPlan, QueryPlanResult, ExecutionResult, TimePeriod

logger = logging.getLogger(__name__)

_MAX_DOCS    = 100
_TIMEOUT_MS  = 10_000          # 10-second server-side timeout

# Operator mapping → MongoDB equivalents
_OP_MAP = {
    "eq":    "$eq",
    "ne":    "$ne",
    "gt":    "$gt",
    "gte":   "$gte",
    "lt":    "$lt",
    "lte":   "$lte",
    "in":    "$in",
    "nin":   "$nin",
    "regex": "$regex",
}


# ── Date range builder (server-side, not from LLM) ───────────────────────────

def _date_range(period: TimePeriod) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    from datetime import timedelta
    match period:
        case TimePeriod.TODAY:
            return today, now
        case TimePeriod.YESTERDAY:
            yd = today - timedelta(days=1)
            return yd, today
        case TimePeriod.THIS_WEEK:
            return today - timedelta(days=now.weekday()), now
        case TimePeriod.LAST_WEEK:
            tw = today - timedelta(days=now.weekday())
            return tw - timedelta(weeks=1), tw
        case TimePeriod.THIS_MONTH:
            return today.replace(day=1), now
        case TimePeriod.LAST_MONTH:
            first = today.replace(day=1)
            lme = first - timedelta(days=1)
            return lme.replace(day=1), first
        case TimePeriod.THIS_YEAR:
            return today.replace(month=1, day=1), now
        case _:
            return datetime(2000, 1, 1, tzinfo=timezone.utc), now


# ── Filter → $match stage ────────────────────────────────────────────────────

def _build_match(plan: QueryPlan) -> dict[str, Any]:
    match: dict[str, Any] = {}

    # Date range
    if plan.date_field and plan.time_period:
        start, end = _date_range(plan.time_period)
        match[plan.date_field] = {"$gte": start, "$lte": end}

    # Explicit filters from the plan
    for f in plan.filters:
        # Skip date field if already handled above
        if f.field == plan.date_field:
            continue

        if f.operator == "between":
            match[f.field] = {"$gte": f.value, "$lte": f.value2}
        elif f.operator in _OP_MAP:
            match[f.field] = {_OP_MAP[f.operator]: f.value}
        elif f.operator == "eq":
            match[f.field] = f.value

    return match


# ── Build aggregation pipeline ────────────────────────────────────────────────

def _build_pipeline(plan: QueryPlan) -> list[dict[str, Any]]:
    pipeline: list[dict[str, Any]] = []

    match_stage = _build_match(plan)
    if match_stage:
        pipeline.append({"$match": match_stage})

    if plan.operation == "count":
        pipeline.append({"$count": "total"})
        return pipeline

    if plan.operation == "aggregate":
        if plan.group_by and plan.metric and plan.metric_field:
            agg_op = {
                "sum": "$sum", "avg": "$avg",
                "min": "$min", "max": "$max", "count": "$sum"
            }.get(plan.metric, "$sum")

            value_expr = (
                f"${plan.metric_field}"
                if plan.metric != "count"
                else 1
            )

            pipeline.append({
                "$group": {
                    "_id": f"${plan.group_by}",
                    "value": {agg_op: value_expr},
                    "count": {"$sum": 1},
                }
            })
        elif plan.metric and plan.metric_field:
            # Single aggregation (no group-by)
            agg_op = {
                "sum": "$sum", "avg": "$avg",
                "min": "$min", "max": "$max",
            }.get(plan.metric, "$sum")
            pipeline.append({
                "$group": {
                    "_id": None,
                    "value": {agg_op: f"${plan.metric_field}"},
                    "count": {"$sum": 1},
                }
            })

    # Sort
    if plan.sort_field:
        direction = 1 if plan.sort_order == "asc" else -1
        sort_key = (
            "value" if plan.sort_field in (plan.metric_field, "value")
            else plan.sort_field
        )
        pipeline.append({"$sort": {sort_key: direction}})

    # Limit
    limit = min(plan.limit, _MAX_DOCS)
    pipeline.append({"$limit": limit})

    return pipeline


# ── Executor ──────────────────────────────────────────────────────────────────

class QueryExecutor:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def _run_plan(self, plan: QueryPlan) -> list[dict[str, Any]]:
        collection = self._db[plan.collection]
        pipeline = _build_pipeline(plan)
        logger.debug(f"Executing pipeline on '{plan.collection}': {pipeline}")

        cursor = collection.aggregate(
            pipeline,
            maxTimeMS=_TIMEOUT_MS,
            allowDiskUse=False,
        )
        results: list[dict[str, Any]] = []
        async for doc in cursor:
            # Convert ObjectId → str to make it JSON-serialisable
            doc = {
                k: str(v) if not isinstance(v, (int, float, str, bool, list, dict, type(None), datetime))
                else v
                for k, v in doc.items()
            }
            results.append(doc)
        return results

    async def execute(self, plan_result: QueryPlanResult) -> ExecutionResult:
        if not plan_result.safety_passed:
            raise PermissionError(
                "Query plan failed security check: "
                + "; ".join(plan_result.safety_notes)
            )

        t0 = time.monotonic()

        primary_data = await self._run_plan(plan_result.primary)
        comparison_data = None
        if plan_result.comparison:
            comparison_data = await self._run_plan(plan_result.comparison)

        elapsed_ms = (time.monotonic() - t0) * 1000

        # Complexity heuristic
        pipe_len = len(_build_pipeline(plan_result.primary))
        complexity = (
            "complex"   if pipe_len > 4  else
            "moderate"  if pipe_len > 2  else
            "simple"
        )

        return ExecutionResult(
            primary_data=primary_data,
            comparison_data=comparison_data,
            row_count=len(primary_data) if isinstance(primary_data, list) else 1,
            execution_time_ms=round(elapsed_ms, 2),
            query_complexity=complexity,
        )

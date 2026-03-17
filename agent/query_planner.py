"""
agent/query_planner.py
──────────────────────
Stage 2 of the pipeline.
Uses the unified LLMClient to build a safe, structured QueryPlan JSON.
"""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import get_settings
from models import (
    IntentResult, IntentType, TimePeriod,
    QueryPlan, QueryPlanResult, QueryFilter
)
from agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

_DB_SCHEMA = """
=== MONGODB COLLECTIONS & FIELD NAMES ===

Collection: orders
  _id, userId, items (Array of {productId, name, quantity, price, category})
  totalAmount (Number) ← revenue field
  status: "pending"|"confirmed"|"shipped"|"delivered"|"cancelled"|"returned"
  paymentStatus: "pending"|"paid"|"failed"|"refunded"
  createdAt (Date), updatedAt (Date), shippingCity (String)

Collection: products
  _id, name, category ("tops"|"dresses"|"shoes"|"accessories"|"bottoms")
  brand, price (Number), stock (Number), soldCount (Number), rating (0-5)
  isActive (Boolean), createdAt (Date)

Collection: users
  _id, createdAt, city, totalOrders, totalSpent
  tier: "bronze"|"silver"|"gold"|"platinum"
  isActive (Boolean)
  *** NO PII — name, email, phone never exposed ***

Collection: payments
  _id, orderId, amount, method ("card"|"cod"|"upi"|"wallet"|"bnpl")
  status: "success"|"failed"|"pending"|"refunded"
  createdAt (Date)
"""

_ALLOWED_COLLECTIONS = {"users", "orders", "products", "payments"}
_ALLOWED_OPERATIONS  = {"aggregate", "count", "find_one", "distinct"}
_BLOCKED_FIELDS      = {"name", "email", "phone", "address", "password", "token"}

_PLANNER_PROMPT = """
You are the Query Planner for a Fashion E-Commerce Analytics Agent.
Return ONLY raw JSON — no markdown, no explanation.

{{
  "primary": {{
    "collection": "<orders|products|users|payments>",
    "operation": "<aggregate|count|find_one|distinct>",
    "filters": [{{"field":"<f>","operator":"<eq|ne|gt|gte|lt|lte|in|nin|between>","value":<v>,"value2":null}}],
    "group_by": "<field or null>",
    "metric": "<sum|avg|count|min|max or null>",
    "metric_field": "<field or null>",
    "sort_field": "<field or null>",
    "sort_order": "<asc|desc>",
    "limit": <1-100>,
    "date_field": "<field or null>",
    "time_period": "<same as intent>",
    "compare_previous": <true|false>
  }},
  "comparison": null,
  "index_suggestions": ["<field1>"]
}}

Rules:
- ONLY fields from the schema. ONLY read operations. NEVER write ops.
- Revenue: collection=orders, metric=sum, metric_field=totalAmount
- Order status breakdown: collection=orders, group_by=status, metric=count
- Product rankings: collection=products, sort by soldCount desc
- If compare_previous=true, fill "comparison" with prior period plan
- Today: {today}

DB SCHEMA: {schema}
INTENT: {intent}
"""


def _security_check(plan: QueryPlan) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True
    if plan.collection not in _ALLOWED_COLLECTIONS:
        notes.append(f"BLOCKED: unknown collection '{plan.collection}'")
        ok = False
    if plan.operation not in _ALLOWED_OPERATIONS:
        notes.append(f"BLOCKED: operation '{plan.operation}' not allowed")
        ok = False
    for f in plan.filters:
        if f.field in _BLOCKED_FIELDS:
            notes.append(f"BLOCKED: filter on PII field '{f.field}'")
            ok = False
    if plan.metric_field and plan.metric_field in _BLOCKED_FIELDS:
        notes.append(f"BLOCKED: metric on PII field '{plan.metric_field}'")
        ok = False
    return ok, notes


def _previous_period(period: TimePeriod) -> Optional[TimePeriod]:
    return {
        TimePeriod.THIS_WEEK:  TimePeriod.LAST_WEEK,
        TimePeriod.THIS_MONTH: TimePeriod.LAST_MONTH,
    }.get(period)


class QueryPlanner:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def plan(self, intent: IntentResult) -> QueryPlanResult:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        prompt = _PLANNER_PROMPT.format(
            today=today,
            schema=_DB_SCHEMA,
            intent=intent.model_dump_json(indent=2)
        )

        logger.debug("Query planner → calling LLM…")
        raw = await self._llm.generate(prompt)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        logger.debug(f"Plan raw: {raw[:300]}")

        data = json.loads(raw)
        primary = QueryPlan(**data.get("primary", {}))

        comparison: Optional[QueryPlan] = None
        if data.get("comparison"):
            comparison = QueryPlan(**data["comparison"])

        if intent.intent == IntentType.TREND or primary.compare_previous:
            prev = _previous_period(intent.time_period)
            if prev and comparison is None:
                comparison = primary.model_copy(update={"time_period": prev})

        ok, notes = _security_check(primary)
        if comparison:
            ok2, notes2 = _security_check(comparison)
            ok = ok and ok2
            notes.extend(notes2)

        return QueryPlanResult(
            primary=primary,
            comparison=comparison,
            safety_passed=ok,
            safety_notes=notes,
            index_suggestions=data.get("index_suggestions", []),
        )

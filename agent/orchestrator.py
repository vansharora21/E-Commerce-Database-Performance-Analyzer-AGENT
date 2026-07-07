"""
agent/orchestrator.py
──────────────────────
The main Agent Orchestrator — wires all pipeline stages with
full conversation memory support.

Routing logic:
  - Conversational / unknown+casual → ConversationalAgent (no DB)
  - Analytics intent → full 4-stage pipeline (Intent→Plan→Execute→Insight)

Session history is stored in ConversationManager and injected into
follow-up questions so context is maintained across turns.
"""
from __future__ import annotations
import logging
import time
import asyncio
from typing import Any, Optional
import json

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import get_settings
from models import AgentResponse, InsightResult, IntentType, TimePeriod, IntentResult, QueryPlanResult, ExecutionResult
from .intent_detector       import IntentDetector
from .query_planner         import QueryPlanner
from .query_executor        import QueryExecutor
from .insight_generator     import InsightGenerator
from .conversational_agent  import ConversationalAgent, is_conversational
from .conversation_manager  import ConversationManager, conversation_manager

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db              = db
        self._intent_detector = IntentDetector()
        self._query_planner   = QueryPlanner()
        self._query_executor  = QueryExecutor(db)
        self._insight_gen     = InsightGenerator()
        self._conv_agent      = ConversationalAgent()
        self._conv_manager    = conversation_manager
        self._settings        = get_settings()

    async def ask(self, question: str, session_id: str = "default") -> AgentResponse:
        t_total = time.monotonic()
        session = self._conv_manager.get_or_create(session_id)

        # Add user turn to history
        session.add("user", question)

        # ── Stage 1: Intent Detection ──────────────────────────────────────
        logger.info(f"[AGENT] session={session_id[:8]} Q={question!r}")
        intent = await self._retry(self._intent_detector.detect, question)

        # ── Route: Conversational vs Analytics ─────────────────────────────
        if is_conversational(question, intent.intent.value):
            return await self._handle_conversational(
                question, session, intent.intent, t_total
            )

        pipeline_steps = []
        if intent.is_compound:
            pipeline_steps.append(
                f"[1] Intent: Compound Question composed of {len(intent.sub_intents)} sub-intents"
                f" ({(time.monotonic()-t_total)*1000:.0f}ms)"
            )
        else:
            pipeline_steps.append(
                f"[1] Intent: {intent.intent.value} ({intent.time_period.value})"
                f" conf={intent.confidence:.0%}"
                f" ({(time.monotonic()-t_total)*1000:.0f}ms)"
            )

        # Helper to execute plan with bounded re-planning loop
        async def plan_and_execute_with_replan(
            sub_intent: IntentResult,
            step_prefix: str = "",
            prev_context: Optional[str] = None
        ) -> tuple[QueryPlanResult, ExecutionResult]:
            attempts = 0
            max_replan_attempts = 2
            feedback = None
            prev_primary = None

            t0 = time.monotonic()
            plan_res = await self._retry(
                self._query_planner.plan,
                sub_intent,
                feedback=feedback,
                previous_context=prev_context
            )
            plan_time_ms = (time.monotonic() - t0) * 1000

            step_num = f"2{step_prefix}"
            pipeline_steps.append(
                f"[{step_num}] Plan: {plan_res.primary.collection}.{plan_res.primary.operation}"
                f" safety={'OK' if plan_res.safety_passed else 'BLOCKED'}"
                f" ({plan_time_ms:.0f}ms)"
            )

            if not plan_res.safety_passed:
                raise PermissionError("Query blocked: " + "; ".join(plan_res.safety_notes))

            t0 = time.monotonic()
            exec_res = await self._query_executor.execute(plan_res)
            db_num = f"3{step_prefix}"
            pipeline_steps.append(
                f"[{db_num}] DB: {exec_res.row_count} rows in {exec_res.execution_time_ms:.0f}ms"
            )

            # Re-planning on failure (row_count == 0)
            while exec_res.row_count == 0 and attempts < max_replan_attempts:
                prev_primary = plan_res.primary
                attempts += 1

                feedback = (
                    f"The previous plan on collection '{plan_res.primary.collection}' returned 0 rows. "
                    f"Please loosen the filters/date range, or check a different range."
                )

                new_plan_res = await self._retry(
                    self._query_planner.plan,
                    sub_intent,
                    feedback=feedback,
                    previous_context=prev_context
                )

                # Check if the plan is identical to previous (legitimate zero/no change possible)
                if prev_primary and new_plan_res.primary == prev_primary:
                    logger.info(f"Re-plan attempt {attempts}: LLM returned identical plan. Stopping re-plan loop.")
                    break

                plan_res = new_plan_res
                if not plan_res.safety_passed:
                    raise PermissionError("Query blocked during re-plan: " + "; ".join(plan_res.safety_notes))

                exec_res = await self._query_executor.execute(plan_res)

                replan_desc = plan_res.replan_reason or "loosened filters"
                if not step_prefix:
                    replan_step_num = "2b" if attempts == 1 else "2c"
                    db_replan_step_num = "3b" if attempts == 1 else "3c"
                else:
                    replan_step_num = f"2{step_prefix}-replan{attempts}"
                    db_replan_step_num = f"3{step_prefix}-replan{attempts}"

                pipeline_steps.append(
                    f"[{replan_step_num}] Re-plan attempt {attempts}: {replan_desc}"
                )
                pipeline_steps.append(
                    f"[{db_replan_step_num}] DB: {exec_res.row_count} rows"
                )

            return plan_res, exec_res

        # ── Stage 2 & 3: Planning and Execution ────────────────────────────
        if intent.is_compound:
            exec_results = []
            plan_results = []

            for idx, sub_intent in enumerate(intent.sub_intents, 1):
                step_suffix = chr(96 + idx)  # 1 -> 'a', 2 -> 'b', etc.
                pipeline_steps.append(
                    f"[1{step_suffix}] Sub-intent {idx}: {sub_intent.intent.value} ({sub_intent.time_period.value})"
                    f" conf={sub_intent.confidence:.0%}"
                )

                # Build sequential context
                context_lines = []
                for prev_idx, (prev_sub, prev_plan, prev_exec) in enumerate(zip(intent.sub_intents[:idx-1], plan_results, exec_results), 1):
                    context_lines.append(f"Sub-step {prev_idx} Question: {prev_sub.rephrased_question}")
                    context_lines.append(f"Sub-step {prev_idx} Plan: collection={prev_plan.primary.collection}, operation={prev_plan.primary.operation}")
                    preview = self._sanitise_preview(prev_exec.primary_data)
                    context_lines.append(f"Sub-step {prev_idx} Result Data: {json.dumps(preview)}")

                prev_context = "\n".join(context_lines) if context_lines else None

                # Execute with re-plan support
                sub_plan_res, sub_exec_res = await plan_and_execute_with_replan(
                    sub_intent,
                    step_prefix=step_suffix,
                    prev_context=prev_context
                )

                plan_results.append(sub_plan_res)
                exec_results.append(sub_exec_res)

            # ── Stage 4: Insight Generation (Synthesised) ──────────────────
            t0 = time.monotonic()
            insight = await self._retry(self._insight_gen.generate, question, intent, exec_results)
            pipeline_steps.append(
                f"[4] Insight: '{insight.headline}' ({(time.monotonic()-t0)*1000:.0f}ms)"
            )

            primary_plan_res = plan_results[0]
            primary_exec_res = exec_results[0]
            raw_preview = self._sanitise_preview(primary_exec_res.primary_data)
        else:
            # Simple single execution
            plan_result, exec_result = await plan_and_execute_with_replan(intent)

            # ── Stage 4: Insight Generation ────────────────────────────────
            t0 = time.monotonic()
            insight = await self._retry(self._insight_gen.generate, question, intent, exec_result)
            pipeline_steps.append(
                f"[4] Insight: '{insight.headline}' ({(time.monotonic()-t0)*1000:.0f}ms)"
            )

            primary_plan_res = plan_result
            primary_exec_res = exec_result
            raw_preview = self._sanitise_preview(primary_exec_res.primary_data)

        total_ms = round((time.monotonic() - t_total) * 1000, 2)
        pipeline_steps.append(f"[DONE] {total_ms:.0f}ms total")

        # Save assistant insight to session history
        session_summary = f"[Analytics] {insight.headline} — {insight.summary[:200]}"
        session.add("assistant", session_summary, intent=intent.intent.value)

        return AgentResponse(
            question=question,
            intent=intent.intent,
            time_period=intent.time_period,
            insight=insight,
            raw_results_preview=raw_preview,
            execution_time_ms=total_ms,
            pipeline_steps=pipeline_steps,
            index_suggestions=primary_plan_res.index_suggestions,
            is_conversational=False,
        )


    async def _handle_conversational(
        self, question: str, session, intent: IntentType, t_start: float
    ) -> AgentResponse:
        """Handle non-analytics conversational turns."""
        t0 = time.monotonic()
        text = await self._conv_agent.respond(question, session)
        total_ms = round((time.monotonic() - t_start) * 1000, 2)

        # Save to session history
        session.add("assistant", text)

        # Wrap in an AgentResponse with a minimal InsightResult
        return AgentResponse(
            question=question,
            intent=IntentType.CONVERSATIONAL,
            time_period=TimePeriod.ALL_TIME,
            insight=InsightResult(
                headline="",
                summary=text,
                key_metrics=[],
                recommendations=[],
                data_quality_notes=[],
                chart_hint=None,
            ),
            raw_results_preview=[],
            execution_time_ms=total_ms,
            pipeline_steps=[f"[chat] Conversational response in {total_ms:.0f}ms"],
            index_suggestions=[],
            is_conversational=True,
            plain_response=text,
        )

    async def _retry(self, fn, *args, **kwargs):
        max_retries = self._settings.agent_max_retries
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                err = str(exc)
                if "429" in err or "quota" in err.lower():
                    raise
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(f"Attempt {attempt} failed ({err[:80]}). Retry in {wait}s…")
                    await asyncio.sleep(wait)
        raise RuntimeError(f"All {max_retries} attempts failed: {last_exc}") from last_exc

    @staticmethod
    def _sanitise_preview(data: Any) -> list[dict]:
        _PII = {"name", "email", "phone", "address", "password", "token"}
        if not data:
            return []
        rows = data if isinstance(data, list) else [data]
        return [{k: v for k, v in row.items() if k not in _PII} for row in rows[:5]]

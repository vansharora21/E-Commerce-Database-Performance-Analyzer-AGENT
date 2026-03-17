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
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import get_settings
from models import AgentResponse, InsightResult, IntentType, TimePeriod
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

        # ── Stage 2: Query Planning ────────────────────────────────────────
        pipeline_steps = [
            f"[1] Intent: {intent.intent.value} ({intent.time_period.value})"
            f" conf={intent.confidence:.0%}"
            f" ({(time.monotonic()-t_total)*1000:.0f}ms)"
        ]

        t0 = time.monotonic()
        plan_result = await self._retry(self._query_planner.plan, intent)
        pipeline_steps.append(
            f"[2] Plan: {plan_result.primary.collection}.{plan_result.primary.operation}"
            f" safety={'OK' if plan_result.safety_passed else 'BLOCKED'}"
            f" ({(time.monotonic()-t0)*1000:.0f}ms)"
        )

        if not plan_result.safety_passed:
            raise PermissionError("Query blocked: " + "; ".join(plan_result.safety_notes))

        # ── Stage 3: Query Execution ───────────────────────────────────────
        t0 = time.monotonic()
        exec_result = await self._query_executor.execute(plan_result)
        pipeline_steps.append(
            f"[3] DB: {exec_result.row_count} rows in {exec_result.execution_time_ms:.0f}ms"
        )

        # ── Stage 4: Insight Generation ────────────────────────────────────
        t0 = time.monotonic()
        insight = await self._retry(self._insight_gen.generate, question, intent, exec_result)
        pipeline_steps.append(
            f"[4] Insight: '{insight.headline}' ({(time.monotonic()-t0)*1000:.0f}ms)"
        )

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
            raw_results_preview=self._sanitise_preview(exec_result.primary_data),
            execution_time_ms=total_ms,
            pipeline_steps=pipeline_steps,
            index_suggestions=plan_result.index_suggestions,
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

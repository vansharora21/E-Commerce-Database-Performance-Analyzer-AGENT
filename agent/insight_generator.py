"""
agent/insight_generator.py
───────────────────────────
Stage 4 of the pipeline. Uses the unified LLMClient to convert
raw DB results into structured business insights.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from config import get_settings
from models import IntentResult, ExecutionResult, InsightResult
from agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

_INSIGHT_PROMPT = """
You are the Insight Generator for a Fashion E-Commerce Analytics Agent.
Return ONLY raw JSON — no markdown, no explanation.

{{
  "headline": "<punchy one-liner, max 12 words>",
  "summary": "<2-3 sentence business narrative answering the question>",
  "key_metrics": [
    {{"label":"<name>","value":<number or string>,"unit":"<INR|units|orders|%|users>","change_pct":<float or null>}}
  ],
  "trend": {{
    "direction": "<up|down|flat|null>",
    "change_pct": <float>,
    "period_label": "<e.g. vs last week>",
    "narrative": "<1 sentence>"
  }},
  "recommendations": ["<actionable rec 1>", "<rec 2>"],
  "data_quality_notes": ["<note if data sparse or empty>"],
  "chart_hint": "<bar|line|pie|table|number>"
}}

Rules:
- NEVER fabricate numbers — only use values from the data below.
- If data is empty: headline="No data found for this period", explain in summary.
- Monetary values are in INR (Indian Rupees ₹).
- change_pct = ((current-previous)/previous)*100, rounded to 1 decimal.
- Max 3 recommendations.

QUESTION: {question}
INTENT: {intent}
TIME PERIOD: {time_period}
PRIMARY DATA ({primary_count} rows): {primary_data}
COMPARISON DATA ({comparison_count} rows): {comparison_data}
"""


class InsightGenerator:
    def __init__(self) -> None:
        self._llm = LLMClient()

    def _fmt(self, data: Any) -> str:
        if not data:
            return "[]"
        rows = data if isinstance(data, list) else [data]
        return json.dumps(rows[:20], indent=2, default=str)

    async def generate(
        self,
        question: str,
        intent: IntentResult,
        execution: ExecutionResult,
    ) -> InsightResult:
        primary_count = len(execution.primary_data) if isinstance(execution.primary_data, list) else 1
        comparison_count = (
            len(execution.comparison_data) if isinstance(execution.comparison_data, list) else 0
        ) if execution.comparison_data else 0

        prompt = _INSIGHT_PROMPT.format(
            question=question,
            intent=intent.intent.value,
            time_period=intent.time_period.value,
            primary_count=primary_count,
            primary_data=self._fmt(execution.primary_data),
            comparison_count=comparison_count,
            comparison_data=self._fmt(execution.comparison_data),
        )

        logger.debug("Insight generation → calling LLM…")
        raw = await self._llm.generate(prompt)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        logger.debug(f"Insight raw: {raw[:300]}")

        data = json.loads(raw)

        trend = data.get("trend")
        if trend and not any(v for v in trend.values() if v is not None):
            trend = None

        return InsightResult(
            headline=data.get("headline", "Insight generated"),
            summary=data.get("summary", ""),
            key_metrics=data.get("key_metrics", []),
            trend=trend,
            recommendations=data.get("recommendations", []),
            data_quality_notes=data.get("data_quality_notes", []),
            chart_hint=data.get("chart_hint"),
        )

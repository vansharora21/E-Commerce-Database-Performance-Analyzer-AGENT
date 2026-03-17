"""
agent/intent_detector.py
────────────────────────
Stage 1 of the pipeline.
Uses the unified LLMClient (Gemini or Groq) to parse the user's
natural-language question into a structured IntentResult JSON.
"""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime

from config import get_settings
from models import IntentResult, IntentType, TimePeriod
from agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Intent Detector for a Fashion E-Commerce Analytics Agent.

Your ONLY job is to analyse the user's question and return a JSON object with
these exact fields (no markdown, no explanation, raw JSON only):

{{
  "intent": "<one of: revenue | order_status | product_performance | customer_insight | inventory | trend_comparison | top_n_ranking | payment_analytics | unknown>",
  "time_period": "<one of: today | yesterday | this_week | last_week | this_month | last_month | this_year | all_time | custom>",
  "entities": {{
      // Any specific values mentioned: product_name, category, status,
      // brand, limit (for top 5), threshold amount, etc.
      // Use snake_case keys. Leave empty {{}} if none.
  }},
  "confidence": <float 0.0-1.0>,
  "rephrased_question": "<clean, normalised English version of the question>"
}}

Rules:
- NEVER invent facts or metrics.
- If the question is ambiguous, pick the best intent and lower confidence.
- If time period is not mentioned, default to "this_month".
- "trend_comparison" means the user wants WoW, MoM, or YoY comparisons.
- Detect "top N" patterns and store N in entities.limit.
- Today's date is: {today}

Question: {question}
"""


class IntentDetector:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def detect(self, question: str) -> IntentResult:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        prompt = _SYSTEM_PROMPT.format(today=today, question=question)

        logger.debug("Intent detection → calling LLM…")
        raw = await self._llm.generate(prompt)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        logger.debug(f"Intent raw: {raw[:200]}")

        data = json.loads(raw)

        try:
            intent = IntentType(data.get("intent", "unknown"))
        except ValueError:
            intent = IntentType.UNKNOWN

        try:
            period = TimePeriod(data.get("time_period", "this_month"))
        except ValueError:
            period = TimePeriod.THIS_MONTH

        return IntentResult(
            intent=intent,
            time_period=period,
            entities=data.get("entities", {}),
            confidence=float(data.get("confidence", 0.5)),
            rephrased_question=data.get("rephrased_question", question),
        )

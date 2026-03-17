"""
agent/llm_client.py
────────────────────
Unified LLM client that supports both Gemini and Groq.

Priority:
  1. Uses whatever PROVIDER is set in .env (gemini | groq)
  2. Groq uses OpenAI-compatible API — no extra SDK needed (uses httpx)
  3. Falls back to the other provider if the primary is quota-exceeded

Groq free tier: 14,400 req/day, 30 req/minute — very generous.
Get a free key at: https://console.groq.com
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Literal

import httpx
import google.generativeai as genai

from config import get_settings

logger = logging.getLogger(__name__)

Provider = Literal["gemini", "groq"]

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Groq model fallback chain (all free)
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]

# Gemini model fallback chain
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-pro",
]


class LLMClient:
    """
    Single unified client for calling either Gemini or Groq.
    Call `generate(prompt)` — returns the raw text response.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._settings  = settings
        self._provider: Provider = getattr(settings, "llm_provider", "gemini")
        self._gemini_key = settings.gemini_api_key
        self._groq_key   = getattr(settings, "groq_api_key", "")
        self._temperature = settings.agent_temperature

        # Initialise whichever provider is active
        if self._provider == "groq" and self._groq_key:
            self._groq_model   = GROQ_MODELS[0]
            self._gemini_model = None
            logger.info(f"LLM provider: Groq ({self._groq_model})")
        else:
            # Default: Gemini
            self._provider = "gemini"
            genai.configure(api_key=self._gemini_key)
            self._gemini_model_name = settings.gemini_model
            self._gemini_obj = genai.GenerativeModel(self._gemini_model_name)
            self._groq_model = GROQ_MODELS[0]
            logger.info(f"LLM provider: Gemini ({self._gemini_model_name})")

    async def generate(self, prompt: str) -> str:
        """
        Generate a response from the configured LLM.
        Automatically falls back to the other provider on quota errors.
        Always returns the raw text string.
        """
        try:
            if self._provider == "groq":
                return await self._call_groq(prompt)
            else:
                return await self._call_gemini(prompt)
        except Exception as e:
            err = str(e)
            # Quota / rate limit → try the other provider
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                logger.warning(f"Primary provider quota hit. Trying fallback provider…")
                if self._provider == "gemini" and self._groq_key:
                    logger.info("Falling back to Groq…")
                    return await self._call_groq(prompt)
                elif self._provider == "groq" and self._gemini_key:
                    logger.info("Falling back to Gemini…")
                    return await self._call_gemini(prompt)
            raise

    # ── Groq (OpenAI-compatible REST) ─────────────────────────────────────────

    async def _call_groq(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GROQ_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    # ── Gemini ────────────────────────────────────────────────────────────────

    async def _call_gemini(self, prompt: str) -> str:
        genai.configure(api_key=self._gemini_key)
        model = genai.GenerativeModel(self._gemini_model_name)
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=self._temperature,
                response_mime_type="application/json",
            ),
        )
        return response.text.strip()

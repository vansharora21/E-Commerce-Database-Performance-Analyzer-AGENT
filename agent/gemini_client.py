"""
agent/gemini_client.py
───────────────────────
Shared Gemini client factory with automatic model fallback.

IMPORTANT: build_model() makes NO network calls.
It just configures the API and returns a GenerativeModel object.
Model validity is confirmed naturally on the first real request.
This prevents blocking the async event loop during FastAPI startup.
"""
from __future__ import annotations
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Ordered fallback chain — used by the orchestrator retry logic
MODEL_FALLBACKS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-pro-latest",
    "gemini-pro",
]


def build_model(api_key: str, preferred: str) -> tuple[genai.GenerativeModel, str]:
    """
    Configure Gemini API key and return (GenerativeModel, model_name).

    No network call is made here — the model object is just configured.
    The first real request will surface any 404/auth errors, which the
    orchestrator retry + fallback loop will handle.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(preferred)
    logger.info(f"Gemini model configured: {preferred}")
    return model, preferred


async def find_working_model_async(api_key: str, preferred: str) -> tuple[genai.GenerativeModel, str]:
    """
    Async probe — tests each model in the fallback chain until one responds.
    Safe to call from an async context (e.g. lifespan startup).
    Only used if you want eager startup validation.
    """
    genai.configure(api_key=api_key)
    chain = [preferred] + [m for m in MODEL_FALLBACKS if m != preferred]

    for name in chain:
        try:
            m = genai.GenerativeModel(name)
            r = await m.generate_content_async(
                "Reply with one word: pong",
                generation_config=genai.GenerationConfig(max_output_tokens=5),
            )
            _ = r.text
            logger.info(f"✅ Working Gemini model confirmed: {name}")
            return m, name
        except Exception as e:
            err = str(e)
            if "404" in err or "not found" in err.lower() or "deprecated" in err.lower():
                logger.warning(f"Model '{name}' not available, trying next…")
                continue
            logger.error(f"Gemini error with '{name}': {err[:200]}")
            raise

    raise RuntimeError(f"No working Gemini model found. Tried: {chain}")

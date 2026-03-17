"""
agent/conversational_agent.py
───────────────────────────────
Handles non-analytics / casual conversation turns.

When the intent detector classifies a question as "conversational"
(greetings, explanations, follow-ups, help requests, general knowledge),
this agent responds directly via LLM without touching MongoDB.

It also handles "explain that" or "what does that mean?" by injecting
the previous assistant insight as context.
"""
from __future__ import annotations
import logging
from agent.llm_client import LLMClient
from agent.conversation_manager import Session

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are InsightAI, an intelligent assistant for a fashion e-commerce startup.
You help founders and admins understand their business data and answer questions.

Your personality:
- Friendly, concise, and professional
- Business-focused — always relate back to e-commerce when relevant
- If asked what you can do, explain you can query sales, revenue, orders, products, customers, and payments data in real-time

You have access to the conversation history below.
For follow-up questions like "explain that", "what does this mean", or "tell me more",
use the previous assistant message as context.

Respond in plain text (no markdown headers, keep it conversational).
Keep answers under 150 words unless the user asks for detail.
"""

_CONVERSATIONAL_KEYWORDS = {
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay",
    "help", "what can you do", "who are you", "what are you",
    "explain", "what does", "what is", "tell me more", "clarify",
    "how does", "why", "good morning", "good evening", "bye", "goodbye",
    "what does that mean", "elaborate", "can you", "could you",
}


def is_conversational(question: str, intent: str) -> bool:
    """
    Returns True if this question should be handled conversationally
    rather than through the full DB pipeline.
    """
    if intent == "conversational":
        return True
    if intent == "unknown":
        q_lower = question.lower().strip()
        # Short question (< 6 words) with no analytics keywords
        analytics_words = {
            "revenue", "sales", "order", "product", "customer", "payment",
            "stock", "inventory", "trend", "week", "month", "today", "compare",
            "top", "best", "worst", "pending", "delivered", "cancelled", "refund",
        }
        if len(q_lower.split()) <= 5 and not any(w in q_lower for w in analytics_words):
            return True
        # Explicit conversational keywords
        if any(kw in q_lower for kw in _CONVERSATIONAL_KEYWORDS):
            return True
    return False


class ConversationalAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def respond(self, question: str, session: Session) -> str:
        """
        Generate a conversational response using session history as context.
        Returns plain text string.
        """
        # Build context from recent history
        history = session.to_llm_messages(max_turns=5)

        # Build a history string for the prompt
        history_text = ""
        if history:
            lines = []
            for msg in history[-8:]:  # last 4 back-and-forths
                prefix = "User" if msg["role"] == "user" else "Assistant"
                lines.append(f"{prefix}: {msg['content'][:300]}")
            history_text = "\n".join(lines)

        prompt = f"""{_SYSTEM_PROMPT}

--- CONVERSATION HISTORY (most recent) ---
{history_text if history_text else "(No prior conversation)"}
---

User: {question}
Assistant:"""

        logger.debug(f"Conversational agent responding to: {question!r}")

        # Use non-JSON mode for conversational responses
        try:
            # Temporarily use plain text (override json_object mode in llm_client)
            response = await self._call_plain(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"Conversational agent error: {e}")
            return (
                "I'm here to help! You can ask me about your store's revenue, "
                "orders, products, customers, or payment data. "
                "For example: 'How much revenue this week?' or 'What are our top products?'"
            )

    async def _call_plain(self, prompt: str) -> str:
        """Call LLM without forcing JSON output mode."""
        from config import get_settings
        import httpx
        import google.generativeai as genai

        settings = get_settings()

        if settings.llm_provider == "groq" and settings.groq_api_key:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama-3.1-8b-instant",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 200,
                        # No response_format → plain text
                    },
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        else:
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            response = await model.generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(temperature=0.7, max_output_tokens=200),
            )
            return response.text.strip()

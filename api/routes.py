"""
api/routes.py
─────────────
All FastAPI route definitions.

Endpoints:
  GET  /health             → system health check
  POST /api/ask            → main agent query endpoint
  GET  /api/history        → recent query history (in-memory)
  GET  /api/schema         → human-readable DB schema info
  GET  /api/sample-questions → suggested questions for the UI
"""
from __future__ import annotations
import logging
from collections import deque
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from agent import AgentOrchestrator
from config import get_db
from models import QueryRequest, AgentResponse, ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory history (last 50 queries per session)
_query_history: deque[dict[str, Any]] = deque(maxlen=50)


def _get_agent(request: Request) -> AgentOrchestrator:
    """Dependency: pull the shared agent from app state."""
    return request.app.state.agent


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["System"])
async def health_check():
    """Liveness + readiness probe."""
    try:
        db = get_db()
        await db.command("ping")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Agentic AI Sales & DB Insight",
        "version": "1.0.0",
    }


# ── Main Agent Endpoint ───────────────────────────────────────────────────────

@router.post(
    "/api/ask",
    response_model=AgentResponse,
    tags=["Agent"],
    summary="Ask the AI agent a business question",
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        401: {"model": ErrorResponse, "description": "Unauthorised"},
        500: {"model": ErrorResponse, "description": "Agent error"},
    },
)
async def ask_agent(
    body: QueryRequest,
    agent: AgentOrchestrator = Depends(_get_agent),
):
    """
    Submit a natural-language question and receive structured AI insights.

    Examples:
    - "How much revenue did we generate this week?"
    - "Which products are underperforming this month?"
    - "What is the breakdown of orders by status today?"
    - "Who are our top 5 customers by total spend?"
    - "Compare this week's sales vs last week"
    """
    logger.info(f"POST /api/ask session={body.session_id[:8]} → {body.question!r}")
    try:
        result = await agent.ask(body.question, session_id=body.session_id)
        # Save to history
        _query_history.appendleft({
            "question": body.question,
            "headline": result.insight.headline,
            "intent": result.intent.value,
            "timestamp": result.timestamp.isoformat(),
            "execution_time_ms": result.execution_time_ms,
        })
        return result
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        err_str = str(e)
        logger.exception(f"Agent error: {err_str[:300]}")

        # Gemini quota / rate-limit
        if "429" in err_str or "quota" in err_str.lower() or "quota_dimensions" in err_str.lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Gemini API free-tier quota exceeded. "
                    "Wait 1 minute and try again, or upgrade your Google AI Studio plan. "
                    "Free tier allows ~15 requests/minute."
                ),
            )

        # Model not found (should be auto-resolved by fallback, but just in case)
        if "404" in err_str or "not found" in err_str.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Gemini model unavailable. "
                    "Update GEMINI_MODEL in .env (try: gemini-2.0-flash) and restart."
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent pipeline error: {err_str[:500]}",
        )


# ── Query History ─────────────────────────────────────────────────────────────

@router.get("/api/history", tags=["Agent"])
async def get_history():
    """Return the last 50 questions asked in this session."""
    return {"count": len(_query_history), "history": list(_query_history)}


# ── Schema Info ───────────────────────────────────────────────────────────────

@router.get("/api/schema", tags=["System"])
async def get_schema():
    """Returns the human-readable DB schema the agent reasons over."""
    return {
        "collections": {
            "orders": {
                "description": "Customer purchase orders",
                "key_fields": ["totalAmount", "status", "paymentStatus", "createdAt", "items", "shippingCity"],
                "statuses": ["pending", "confirmed", "shipped", "delivered", "cancelled", "returned"],
            },
            "products": {
                "description": "Fashion product catalogue",
                "key_fields": ["name", "category", "brand", "price", "stock", "soldCount", "rating"],
                "categories": ["tops", "dresses", "shoes", "accessories", "bottoms"],
            },
            "users": {
                "description": "Customer accounts (PII-free view)",
                "key_fields": ["tier", "totalOrders", "totalSpent", "city", "isActive", "createdAt"],
                "tiers": ["bronze", "silver", "gold", "platinum"],
            },
            "payments": {
                "description": "Payment transaction records",
                "key_fields": ["amount", "method", "status", "createdAt"],
                "methods": ["card", "cod", "upi", "wallet", "bnpl"],
            },
        }
    }


# ── Sample Questions ──────────────────────────────────────────────────────────

@router.get("/api/sample-questions", tags=["Agent"])
async def sample_questions():
    """Suggested questions to get started with the AI agent."""
    return {
        "questions": [
            # Revenue
            "How much revenue did we generate this week?",
            "What was our total revenue last month?",
            "Compare this week's revenue vs last week",
            # Orders
            "How many orders were placed today?",
            "What are the pending orders this month?",
            "How many orders were cancelled this month?",
            "Show me the order status breakdown this week",
            # Products
            "Which products are underperforming this month?",
            "What are our top 5 best-selling products?",
            "Which product categories generate the most revenue?",
            "How many products are low on stock?",
            # Customers
            "How many new customers signed up this month?",
            "Who are our top 10 customers by total spend?",
            "What percentage of customers are gold or platinum tier?",
            # Payments
            "What is the most popular payment method this month?",
            "How many payments failed this week?",
            # Trends
            "How did our sales compare this month vs last month?",
        ]
    }

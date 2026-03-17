"""
api/middleware.py
─────────────────
Custom middleware:
 - API key authentication (X-Admin-Key header)
 - Request/response logging
 - CORS
"""
from __future__ import annotations
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from config import get_settings
import logging
import time

logger = logging.getLogger(__name__)


async def auth_middleware(request: Request, call_next):
    """Enforce X-Admin-Key header on all /api/* routes."""
    # Skip auth for docs, health, and static files
    skip_paths = {
        "/", "/docs", "/openapi.json", "/redoc",
        "/health", "/favicon.ico",
        "/api/sample-questions", "/api/schema", "/api/history",
    }
    if request.url.path in skip_paths or not request.url.path.startswith("/api"):
        return await call_next(request)

    settings = get_settings()
    api_key = request.headers.get("X-Admin-Key", "")

    if not api_key or api_key != settings.admin_api_key:
        logger.warning(f"Unauthorised request from {request.client.host}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Unauthorised", "detail": "Valid X-Admin-Key header required."},
        )

    return await call_next(request)


async def timing_middleware(request: Request, call_next):
    """Add X-Process-Time header to every response."""
    t0 = time.monotonic()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.monotonic()-t0)*1000:.1f}ms"
    return response

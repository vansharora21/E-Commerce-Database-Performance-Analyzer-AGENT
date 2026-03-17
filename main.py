"""
main.py — FastAPI application entry point.
"""
from __future__ import annotations
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# ── Force .env reload FIRST before any config is imported ─────────────────────
from dotenv import load_dotenv
load_dotenv(override=True)   # override=True forces re-read even if vars already set

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import connect_db, disconnect_db, get_db, get_settings
from config.settings import get_settings as _gs
_gs.cache_clear()   # ensure fresh read after dotenv override
from api import router, auth_middleware, timing_middleware
from agent import AgentOrchestrator

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=" * 55)
    logger.info("  🚀 Agentic AI Sales & DB Insight System")
    logger.info("=" * 55)

    s = get_settings()
    provider = s.llm_provider.upper()
    if s.llm_provider == "groq":
        key_preview = s.groq_api_key[:12] + "…" if s.groq_api_key else "NOT SET"
    else:
        key_preview = s.gemini_api_key[:12] + "…" if s.gemini_api_key else "NOT SET"
    logger.info(f"LLM Provider : {provider}  (key: {key_preview})")
    await connect_db()
    db = get_db()
    app.state.agent = AgentOrchestrator(db)
    logger.info("✅ Agent ready — pipeline initialised")
    yield
    # Shutdown
    await disconnect_db()
    logger.info("Server shut down cleanly.")


# ── App ───────────────────────────────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title="Agentic AI Sales & DB Insight",
    description=(
        "Production-ready AI agent for fashion e-commerce analytics. "
        "Accepts natural language questions and returns structured business insights."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(timing_middleware)
app.middleware("http")(auth_middleware)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(router)

# ── Static frontend ───────────────────────────────────────────────────────────
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(frontend_dir / "index.html"))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )

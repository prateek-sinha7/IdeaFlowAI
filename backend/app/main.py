"""FastAPI application entry point for the AI SaaS Platform."""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.auth import router as auth_router
from app.api.chats import router as chats_router
from app.api.agents import router as agents_router
from app.api.workflows import router as workflows_router
from app.api.capabilities import router as capabilities_router
from app.api.runs import router as runs_router
from app.api.analytics import router as analytics_router
from app.api.run_commands import router as run_commands_router
from app.api.run_stream import router as run_stream_router
from app.api.user_workflows import router as user_workflows_router
from app.api.handoff import router as handoff_router
from app.api.settings import router as settings_router
from app.api.mcp import router as mcp_router
from app.api.install import router as install_router
from app.api.websocket_handoff import router as websocket_handoff_router
from app.api.prototype_templates import router as prototype_templates_router
from app.api.ppt_templates import router as ppt_templates_router
from app.api.admin import router as admin_router
from app.api.file_extract import router as file_extract_router
from app.api.run_files import router as run_files_router
from app.core.config import settings
from app.models.database import engine

# ============================================================
# LOGGING CONFIGURATION
# ============================================================

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Set specific loggers
logging.getLogger("app").setLevel(logging.DEBUG)
logging.getLogger("app.agents").setLevel(logging.DEBUG)
logging.getLogger("app.api").setLevel(logging.DEBUG)
logging.getLogger("agents.factory").setLevel(logging.DEBUG)  # KAN-71: show prompt override usage
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("app.main")

# ============================================================
# LANGSMITH TRACING SETUP
# ============================================================

# LangSmith is configured via environment variables:
# LANGSMITH_TRACING=true
# LANGSMITH_ENDPOINT=https://api.smith.langchain.com
# LANGSMITH_API_KEY=lsv2_pt_...
# LANGSMITH_PROJECT=ideaflow-ai
#
# These are read automatically by LangChain when making LLM calls.
# No additional code needed — just having them in .env is sufficient.

langsmith_enabled = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
if langsmith_enabled:
    logger.info("🔍 LangSmith tracing ENABLED — project: %s", os.getenv("LANGSMITH_PROJECT", "default"))
else:
    logger.info("LangSmith tracing disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create database tables on startup."""
    logger.info("🚀 Starting VelocityAI Backend...")
    logger.info("   Database: %s", settings.DATABASE_URL)
    if settings.ANTHROPIC_API_KEY:
        logger.info("   LLM provider: anthropic-direct (model=%s)", settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5")
    elif settings.AWS_BEARER_TOKEN_BEDROCK:
        logger.info(
            "   LLM provider: bedrock-bearer-token (model=%s region=%s)",
            settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID or "NOT SET",
            settings.AWS_REGION or "NOT SET",
        )
    else:
        logger.info(
            "   LLM provider: bedrock-iam (model=%s region=%s)",
            settings.BEDROCK_MODEL_ID or "NOT SET",
            settings.AWS_REGION or "NOT SET",
        )
    logger.info("   LangSmith: %s", "enabled ✓" if langsmith_enabled else "disabled")

    # Schema is now driven by alembic, not Base.metadata.create_all. We do a
    # cheap sanity check: if the alembic_version table is missing the DB has
    # never been migrated, which in production means we're about to serve
    # traffic against an empty schema and fail every query. Refuse to boot.
    # In development we tolerate it (with a loud warning) so first-time
    # contributors don't have to remember an extra step.
    inspector = inspect(engine)
    if not inspector.has_table("alembic_version"):
        msg = (
            "Database schema has not been initialised. Run "
            "`alembic upgrade head` from backend/ before starting the backend."
        )
        if settings.ENV.lower() == "development":
            logger.warning("%s (Continuing because ENV=development.)", msg)
        else:
            logger.error(msg)
            raise RuntimeError(msg)
    else:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.first()
            logger.info(
                "   Database schema: alembic=%s",
                row[0] if row else "unknown",
            )

    logger.info("🟢 Backend ready — accepting connections")

    # Phase 3 (T070): restore non-terminal WorkflowRuns on startup.
    # Re-registers asyncio.Events for runs in waiting_for_user state so they
    # can be resumed by user action (FR-011, SC-007 — within 30s of startup).
    try:
        from agents.execution_engine.engine import get_execution_engine
        engine_instance = get_execution_engine()
        # ── 12-09 Gap 2a: wire the engine→WS live-task bridge BEFORE the
        # restore scan, so auto-resumed runs register their queue+task in the
        # WS pipeline registry and a reconnect mid-resume live-attaches. This
        # is the SINGLE wiring site — the engine never imports app.api (the
        # import-linter forbidden direction); the app layer injects callbacks.
        from app.api import run_engine as _ws_bridge
        engine_instance._resume_register_queue = _ws_bridge._register_resume_queue
        engine_instance._resume_register_task = _ws_bridge._register_resume_task
        engine_instance._resume_cleanup = _ws_bridge._cleanup_pipeline
        # ── RESUME-10: wire the live-layer trio onto the engine so an AUTO-RESUMED run
        # (restore_non_terminal_runs branch b) is a first-class LIVE run — it registers
        # its rebuilt ectx (steering / per-turn images / Concierge resolve via
        # _live_ectx_for_run) and emits narrator milestone cards, exactly as the REST/SSE
        # launch path does. These are the SAME callables run_commands threads into
        # engine.execute(...) at launch; app→app import (the kernel never imports app.*).
        from app.api.run_commands import register_live_ectx, unregister_live_ectx
        from app.agents.chat_narrator import persist_milestone_card
        engine_instance._resume_live_ectx_register = register_live_ectx
        engine_instance._resume_live_ectx_unregister = unregister_live_ectx
        engine_instance._resume_milestone_sink = persist_milestone_card
        await engine_instance.restore_non_terminal_runs()
    except Exception as _startup_exc:
        logger.warning("Startup restoration failed (non-fatal): %s", _startup_exc)

    yield
    logger.info("🔴 Shutting down...")


app = FastAPI(
    title="AI SaaS Platform",
    description="Enterprise-grade AI SaaS platform with multi-agent orchestration",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(capabilities_router)
app.include_router(runs_router)
# SC-1 / SHELL-05 (38-01): additive, owner-scoped, READ-ONLY analytics
# aggregation over existing WorkflowRun columns (its own /api/analytics prefix;
# no new table / migration). Registered beside runs_router.
app.include_router(analytics_router)
# CHAT-07 / D-13: the per-run SSE down-channel — the SOLE run event transport
# after the /ws/chat WebSocket was retired (44-07, INV-12 exit gate). Shares the
# /api/runs prefix with runs_router (FastAPI allows multiple routers per prefix).
app.include_router(run_stream_router)
# CHAT-07 / D-13: the up-channel REST command endpoints (gate/answers/cancel) for
# paused-run interactions — the sole command surface after /ws/chat retirement
# (44-07). Thin over the SAME store/cancel seams. Shares the /api/runs prefix.
app.include_router(run_commands_router)
app.include_router(user_workflows_router)
app.include_router(handoff_router)
app.include_router(settings_router)
app.include_router(mcp_router)
app.include_router(install_router)
app.include_router(websocket_handoff_router)
app.include_router(prototype_templates_router)
app.include_router(ppt_templates_router)
app.include_router(admin_router)
app.include_router(file_extract_router)
# UPLD-01: owner-scoped, capped document upload → RunSandbox ``.uploads/`` prefix
# (additive — shares the /api/runs prefix; no new table / migration).
app.include_router(run_files_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    llm_configured = bool(settings.BEDROCK_MODEL_ID and settings.AWS_REGION)
    return {
        "status": "healthy",
        "llm_provider": "bedrock" if llm_configured else "none",
        "langsmith": langsmith_enabled,
    }

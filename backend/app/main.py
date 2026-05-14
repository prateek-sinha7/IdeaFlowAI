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
from app.api.websocket import router as websocket_router
from app.api.handoff import router as handoff_router
from app.api.settings import router as settings_router
from app.api.mcp import router as mcp_router
from app.api.install import router as install_router
from app.api.websocket_handoff import router as websocket_handoff_router
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
    logger.info(
        "   LLM provider: bedrock (model=%s region=%s)",
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
app.include_router(websocket_router)
app.include_router(handoff_router)
app.include_router(settings_router)
app.include_router(mcp_router)
app.include_router(install_router)
app.include_router(websocket_handoff_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    llm_configured = bool(settings.BEDROCK_MODEL_ID and settings.AWS_REGION)
    return {
        "status": "healthy",
        "llm_provider": "bedrock" if llm_configured else "none",
        "langsmith": langsmith_enabled,
    }

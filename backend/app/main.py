"""FastAPI application entry point for the AI SaaS Platform."""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chats import router as chats_router
from app.api.agents import router as agents_router
from app.api.workflows import router as workflows_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.models.database import Base, engine

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
    """Application lifespan context manager for startup and shutdown events.
    
    On startup, initializes the database, logs configuration details, and signals
    that the backend is ready to accept connections. On shutdown, logs the cleanup.
    
    Args:
        app: The FastAPI application instance.
        
    Yields:
        Control back to FastAPI to serve requests, then resumes on shutdown.
    """
    logger.info("🚀 Starting IdeaFlow AI Backend...")
    logger.info("   Database: %s", settings.DATABASE_URL)
    logger.info("   API Key: %s", "configured ✓" if settings.ANTHROPIC_API_KEY else "NOT SET ✗")
    logger.info("   LangSmith: %s", "enabled ✓" if langsmith_enabled else "disabled")
    Base.metadata.create_all(bind=engine)
    logger.info("   Database tables: created ✓")
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "ai_provider": "anthropic" if settings.ANTHROPIC_API_KEY else "none",
        "langsmith": langsmith_enabled,
    }

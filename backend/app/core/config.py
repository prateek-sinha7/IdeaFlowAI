"""Application configuration settings."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve the backend directory (where this file lives: backend/app/core/config.py)
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    ANTHROPIC_API_KEY: str = ""
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    DATABASE_URL: str = "sqlite:///./dev.db"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24

    # LangSmith (set via env vars, read by LangChain automatically)
    LANGSMITH_TRACING: str = "false"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "ideaflow-ai"

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure LangSmith env vars are set for LangChain to pick up
if settings.LANGSMITH_TRACING.lower() == "true":
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT

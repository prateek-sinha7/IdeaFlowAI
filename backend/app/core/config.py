"""Application configuration settings.

LLM provider notes
------------------
The backend supports two LLM providers, selectable via ``LLM_PROVIDER``:

* ``"bedrock"`` (default) — AWS Bedrock via ``langchain_aws.ChatBedrockConverse``.
  Auth comes from the boto3 default credential chain (instance profile in prod,
  ``~/.aws/credentials`` / ``AWS_PROFILE`` locally). Requires
  ``BEDROCK_MODEL_ID`` and ``AWS_REGION``.

  IMPORTANT — operator action: the ``BEDROCK_MODEL_ID`` default below is a
  cross-region inference profile for ``eu-west-2``. Verify availability with::

      aws bedrock list-foundation-models --region eu-west-2

  If a model ID isn't returned, request access in the Bedrock console and/or
  pick the inference-profile ID that maps to your region.

* ``"anthropic"`` — Direct Anthropic API via ``langchain_anthropic.ChatAnthropic``.
  Kept as an emergency-continuity fallback. Requires ``ANTHROPIC_API_KEY``.
"""

import logging
import os
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger("app.core.config")

# Resolve the backend directory (where this file lives: backend/app/core/config.py)
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# The literal value that ships in the codebase as the SECRET_KEY default. If
# a deployment leaves this in place we refuse to start in any environment that
# isn't explicitly opted-in to development mode (ENV=development).
_DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production"

# Minimum acceptable SECRET_KEY length. 32 bytes ≈ 256 bits of entropy when the
# value is generated with `openssl rand -hex 64` (which yields 128 hex chars,
# well over the floor). 32 chars is a deliberately conservative floor that
# rejects obviously weak keys (e.g. "abc123") while still accepting reasonable
# operator-supplied values.
_MIN_SECRET_KEY_LENGTH = 32


class SecretKeyMisconfigured(RuntimeError):
    """Raised at boot when SECRET_KEY is unset or still the shipped default in
    a non-development environment. Refusing to boot is intentional: a
    predictable signing key means any attacker can forge JWTs."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ---- Environment selector (controls SECRET_KEY strictness) ----
    # "development" → permissive (accepts the default SECRET_KEY).
    # Anything else (production, staging, ci, …) → strict.
    ENV: str = "development"

    # ---- LLM provider selection ----
    # "bedrock" (default) → AWS Bedrock; "anthropic" → direct Anthropic API.
    LLM_PROVIDER: str = "bedrock"

    # ---- AWS Bedrock (used when LLM_PROVIDER=bedrock) ----
    # Cross-region inference profile is the safest default for eu-west-2.
    # See module docstring for verification command.
    BEDROCK_MODEL_ID: str = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    AWS_REGION: str = "eu-west-2"

    # ---- Anthropic direct API (used when LLM_PROVIDER=anthropic) ----
    # Optional now: only required when LLM_PROVIDER=anthropic.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5-20251001"

    SECRET_KEY: str = _DEFAULT_SECRET_KEY
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
        # Tolerate unrelated env vars (boto3 reads AWS_*, the production
        # secrets-loader pours every SSM key into the env file, etc.).
        # Without this, any unexpected variable raises ValidationError at boot.
        extra = "ignore"

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        """Refuse to boot with a default or weak SECRET_KEY in non-dev environments.

        Forging JWTs requires only the signing key. If the codebase default
        ever escapes onto a real EC2 box, every user account is trivially
        compromisable. We catch this at process start so the failure is loud
        and immediate, not 24 hours later when the first stolen token is used.
        """
        is_dev = self.ENV.lower() == "development"

        if not self.SECRET_KEY:
            raise SecretKeyMisconfigured(
                "SECRET_KEY is empty. Set it via the environment or .env file. "
                "Generate a strong value with: openssl rand -hex 64"
            )

        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            if is_dev:
                logger.warning(
                    "SECRET_KEY is the shipped default. Acceptable in ENV=development "
                    "only. Set ENV=production (or any non-development value) and "
                    "rotate the key before deploying."
                )
            else:
                raise SecretKeyMisconfigured(
                    f"SECRET_KEY is still the shipped default in ENV={self.ENV!r}. "
                    "This would let any attacker who has read the source code "
                    "forge JWTs for every user. Rotate it before booting. "
                    "Generate a strong value with: openssl rand -hex 64"
                )

        if len(self.SECRET_KEY) < _MIN_SECRET_KEY_LENGTH:
            if is_dev:
                logger.warning(
                    "SECRET_KEY is shorter than %d characters. Acceptable in dev only.",
                    _MIN_SECRET_KEY_LENGTH,
                )
            else:
                raise SecretKeyMisconfigured(
                    f"SECRET_KEY is shorter than {_MIN_SECRET_KEY_LENGTH} characters "
                    f"in ENV={self.ENV!r}. Generate a strong value with: "
                    "openssl rand -hex 64"
                )

        return self


settings = Settings()

# Ensure LangSmith env vars are set for LangChain to pick up
if settings.LANGSMITH_TRACING.lower() == "true":
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT

"""Application configuration settings.

LLM provider notes
------------------
The backend uses AWS Bedrock via ``langchain_aws.ChatBedrockConverse``.
Auth comes from the boto3 default credential chain (instance profile in
prod, ``~/.aws/credentials`` / ``AWS_PROFILE`` locally). Requires
``BEDROCK_MODEL_ID`` and ``AWS_REGION``.

IMPORTANT — operator action: the ``BEDROCK_MODEL_ID`` default below is a
cross-region inference profile for ``eu-central-1``. Verify availability
with::

    aws bedrock list-foundation-models --region eu-central-1

If a model ID isn't returned, request access in the Bedrock console and/or
pick the inference-profile ID that maps to your region.
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

    # ---- Anthropic direct API (local dev fallback) ----
    # When set, uses langchain-anthropic instead of Bedrock.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL_ID: str = "claude-haiku-4-5-20251001"

    # ---- AWS Bedrock ----
    # Foundation-model ID. The IAM policy in
    # infra/policies/bedrock-invoke.json scopes invoke to this exact ID, the
    # cross-region inference-profile ID, and the EU regions the profile fans
    # out to.
    BEDROCK_MODEL_ID: str = "anthropic.claude-haiku-4-5-20251001-v1:0"
    # Cross-region inference profile is the safest default for eu-central-1.
    # See module docstring for verification command. The application invokes
    # the inference profile (not the foundation-model ID directly), so
    # CloudWatch metrics dimension by this string.
    BEDROCK_INFERENCE_PROFILE_ID: str = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    # Optional override for the coding agent in /flowin-handoff. Coding-task
    # quality benefits from Sonnet over Haiku; the test + compliance agents
    # stay on the default Haiku profile. Leave empty to use the default model
    # for the coding agent too. Example value for eu-central-1:
    #   eu.anthropic.claude-sonnet-4-5-20250929-v1:0
    BEDROCK_CODING_MODEL_ID: str = ""
    AWS_REGION: str = "eu-central-1"
    # Optional Bedrock API bearer token (env: AWS_BEARER_TOKEN_BEDROCK). When
    # set, selects the bedrock-bearer-token auth path; leave empty to use the
    # default IAM (instance-role) credential chain — the production default.
    AWS_BEARER_TOKEN_BEDROCK: str = ""

    # ---- Output token ceiling (single source of truth) ----
    # The Anthropic/Bedrock APIs REQUIRE a finite max_tokens on every call — it
    # cannot be omitted — so "no capping" means "run every agent at the model's
    # maximum" rather than truncating with small per-agent budgets. This value
    # is applied uniformly to ALL agents by the factory, overriding the per-agent
    # `max_tokens` declared in AGENT.md (which is retained only as documentation).
    # 32768 is the largest value proven against the deployed Claude Haiku 4.5
    # profile and is safe across the selectable Claude models (Opus 4.x caps at
    # 32k output). Raise via the MAX_OUTPUT_TOKENS env var only after confirming
    # the active model accepts it, or Bedrock returns a ValidationException.
    MAX_OUTPUT_TOKENS: int = 32768

    # ---- Per-LLM-call total timeout (seconds) ----
    # Wraps one streaming LLM call inside DeepAgent. With MAX_OUTPUT_TOKENS lifted
    # to the model ceiling a single full-length generation can run several minutes,
    # so this must comfortably exceed it; the old 300s would truncate a max-length
    # response. The botocore read_timeout (set where the Bedrock client is built)
    # remains the lower-level guard against a genuinely hung socket.
    LLM_CALL_TIMEOUT_SECONDS: int = 900

    # ---- deepagents runtime ----
    # Root of the per-user/per-run sandbox filesystem the deepagents disk backend
    # writes into. In production this is the persistent runs volume bind-mounted
    # from the host EBS (mirrors /app/skills). Off-container (local dev) override
    # to a writable dir, e.g. RUNS_ROOT=/tmp/flowin-runs, since /app does not exist.
    RUNS_ROOT: str = "/app/runs"
    # Safety ceiling on one agent graph's model<->tool recursion. We DROP the old
    # tight per-agent iteration caps (build 3 / validate 8 / …) in favour of letting
    # agents explore + self-validate; this is only a runaway-loop backstop, not a
    # quality knob. Maps to LangGraph's recursion_limit.
    AGENT_RECURSION_LIMIT: int = 400
    # Retention for a finished run's sandbox dir before the cleanup sweep removes it.
    RUN_DIR_TTL_HOURS: int = 48

    # ── Per-workspace fan-out budget ceilings (Phase 11 / OBS-01) ──────────────
    # The OPTIONAL per-workspace aggregate ceilings the run-entry BudgetManager checks
    # at reserve time against the workspace's already-spent fan-out budget (summed
    # across the workspace's runs by ScopedStore.workspace_budget_spent). DEFAULT None
    # = UNSET = uncapped (the per-run module-constant caps still apply; the workspace
    # aggregate gate is simply dormant). No UI — this is the settings SEAM only; an
    # operator sets it via the env var to cap a multi-run fork-bomb at the workspace
    # grain (T-11-04-01). Mirrors the LocalExecutionPolicy cap-seam pattern.
    WORKSPACE_BUDGET_MAX_SUBAGENTS: int | None = None
    WORKSPACE_BUDGET_MAX_TOKENS: int | None = None

    # Base URL the IDE-side slash command and the MCP client use to reach
    # Flowin. Used to format the handoff URL returned by /api/handoff/receive.
    # Override in production to the public-facing URL (e.g. https://flowin.example).
    PUBLIC_BASE_URL: str = "http://localhost:3000"

    # Maximum bytes of transcript we'll accept on a /api/handoff/receive call.
    # 1 MiB is several long Claude Code sessions in JSONL form; anything more
    # is almost certainly a misconfigured client. Cheap DoS guard.
    HANDOFF_MAX_TRANSCRIPT_BYTES: int = 1024 * 1024

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

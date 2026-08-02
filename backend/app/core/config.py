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
    # Optional Bedrock API-key / bearer-token auth (env: AWS_BEARER_TOKEN_BEDROCK,
    # consumed natively by botocore). main.py's lifespan reads this to report the
    # active provider mode; the field MUST be declared here because Settings is
    # configured extra="ignore", so an undeclared env var is NOT surfaced as an
    # attribute → accessing settings.AWS_BEARER_TOKEN_BEDROCK raised AttributeError
    # on boot whenever ANTHROPIC_API_KEY was empty (i.e. every Bedrock run).
    # Empty (default) → fall through to the IAM/SSO credential chain (AWS_PROFILE).
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

    # ---- Bedrock prompt caching (default ON) ----
    # Provider-agnostic Bedrock prompt caching (default ON); langchain_aws
    # _apply_cache_points reads only `ttl`, `type` is ignored (Converse always
    # uses "default"). deepagents' built-in AnthropicPromptCachingMiddleware
    # caches ONLY ChatAnthropic, so on Bedrock (prod) caching is silently OFF
    # without this — _BedrockCachePointsMiddleware injects the cache_control dict.
    BEDROCK_PROMPT_CACHE_ENABLED: bool = True
    BEDROCK_PROMPT_CACHE_TTL: str = "5m"

    # ---- Extended-thinking budget (enable-only, default OFF) ----
    # extended-thinking budget, enable-only; 0 disables (never fires); clamped to
    # [1024, MAX_OUTPUT_TOKENS-1] in build_model. Threads a thinking budget into
    # both provider branches of build_model when > 0.
    THINKING_BUDGET_TOKENS: int = 0

    # ---- SSE transport down-channel (CHAT-07 / D-13) ----
    # The per-run SSE stream ``GET /api/runs/{id}/events/stream``
    # (``app/api/run_stream.py``) is the SOLE run event transport after the
    # ``/ws/chat`` WebSocket was retired (44-07, INV-12 exit gate). It reuses the
    # per-run live queue + durable ``run_events`` log. The former SSE transport
    # feature-gate is gone (44-07) — the stream is now unconditional.
    # D-14h streaming-infra knobs. ``sse-starlette`` emits a comment-``ping`` at
    # this cadence so an idle proxy never buffers/half-closes a long-lived stream;
    # the INGRESS (nginx/ALB) idle-timeout MUST exceed the ping cadence so the
    # socket stays open between events. The route also sets ``X-Accel-Buffering: no``
    # + ``Cache-Control: no-cache`` on the response and REQUIRES the ingress to run
    # with ``proxy_buffering off`` for ``text/event-stream`` (documented for ops).
    # SSE stream endpoints (for ops reference):
    #   GET /api/runs/{id}/events/stream — per-run live + durable event firehose
    # Nginx idle-timeout for SSE (ops-owned, not enforced here):
    #   proxy_read_timeout 300s; (or proxy_read_timeout 0; for unlimited)
    # D10 (KAN-139): SSE_STREAM_IDLE_TIMEOUT_SECONDS was dead configuration with
    # zero readers anywhere in the codebase (logged as Phase 29 IN-01 and Phase 44
    # IN-01 for months). It has been DELETED. Idle-timeout is purely an ops/nginx
    # concern and is not enforced at the application layer.
    SSE_KEEPALIVE_PING_SECONDS: int = 15
    SSE_STREAM_IDLE_TIMEOUT_SECONDS: int = 300
    # KAN-134: Per-subscriber queue maxsize for the per-run fan-out bus. Each SSE
    # client gets its own queue fed by the shared pump. A slow client that falls
    # behind (queue full) is silently evicted; it reconnects with Last-Event-ID and
    # replays the gap from the durable log. 1000 events ≈ 5–10 MB in memory per
    # subscriber. Set to 0 for unbounded (INV-3 parity with old single-queue model).
    SSE_SUBSCRIBER_QUEUE_MAXSIZE: int = 1000

    # ---- Graceful shutdown budget (KAN-151 D8) ────────────────────────────
    # The container's hard ceiling is docker's stop_grace_period (30s,
    # docker-compose.yml:138); uvicorn's own --timeout-graceful-shutdown (5s,
    # docker-entrypoint.sh) is spent BEFORE the lifespan body runs. These two
    # knobs bound what the lifespan body itself may consume. Sum them with 5s for
    # the checkpointer pool close and keep the total under 25s so SIGKILL is never
    # the thing that ends the process.
    # A Concierge turn owns the ONLY durable write of its chat_reply row
    # (run_commands.py:1356) and is explicitly never cancelled on client
    # disconnect - so it is AWAITED, not cancelled, and only cut past this bound.
    SHUTDOWN_CONCIERGE_DRAIN_SECONDS: float = 10.0
    # How long to wait for run-transport teardown (pump tasks after A2, queue
    # sentinels) before escalating to task.cancel().
    SHUTDOWN_TASK_DRAIN_SECONDS: float = 3.0
    # D8/D9 conflict switch - see the D8 investigation section I11. When False
    # (default) the shutdown leaves in-flight runs non-terminal so the next boot's
    # restore_non_terminal_runs auto-resumes them (the shipped Phase 45-50 tier).
    # When True the shutdown cooperatively cancels them: every in-flight run lands
    # "cancelled", auto-resume is replaced by the user's "Run again" button
    # (POST /api/runs/{id}/resume already accepts "cancelled", run_commands.py:379).
    SHUTDOWN_STOP_RUNS: bool = False

    # ---- Image-input ingress (default ON) ----
    # Feature flag for the image-input ingress (IMAGE-INPUT §3 Layer 1/5, Wave 2).
    # When True, a `run_pipeline` payload may carry a transient `images` list that
    # `_validate_images` caps + vision-guards before it reaches `engine.execute`.
    # When False the WS ingress IGNORES any `images` on the payload (clean
    # off-switch — the run still proceeds as text-only, byte-identical to today).
    IMAGE_INPUT_ENABLED: bool = True

    # ---- Input-brief character cap (single source of truth) ----
    # The maximum number of characters of the user brief that reaches the
    # SmartPlanner analyze prompt + its stored planning_context.user_request,
    # the ClarifyEngine brief_sample, AND the upload/attach ingest cap
    # (file_extract._MAX_TEXT_CHARS). This is now the SINGLE source of truth for
    # all three, so a full uploaded/attached document reaches the planner/clarify
    # LLM instead of being whittled to a head+tail sample.
    #
    # 450,000 chars ≈ ~150k input tokens for dense content (code/HTML ~3 chars/tok),
    # ~112k tokens for prose (~4 chars/tok), and stays safely under Haiku's 200k
    # context window even for minified content (worst case ~180k tokens + prompt
    # scaffolding < 200k). Planner + clarify are each a SINGLE LLM call, so the
    # cost is a one-time ~150k input tokens — no token-loop concern. Briefs beyond
    # this ceiling are still head+tail sampled (planner) / head-capped
    # (clarify + storage) to bound input.
    BRIEF_MAX_CHARS: int = 450_000

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
    # D6 (KAN-139): raised to 168 hours (7 days) to cover the revision-parent seed
    # window — the old 48h was too short for users creating revisions the next day.
    RUN_DIR_TTL_HOURS: int = 168

    # ── Render fail-closed default (quick-260701-bob / REQUIRE-RENDER-KNOB) ────
    # The DEFAULT for the per-step ``require_render`` knob when a manifest step does
    # not declare one. False (the default) preserves today's behavior — a render-
    # unavailable html_render is a PASS (skip-is-a-pass, INV-3): the 5 characterization
    # goldens stay byte/event-identical. Set True (globally, via env) OR per-step in a
    # manifest to fail CLOSED (render-unavailable → P0 → ValidationGate → GATE_BLOCK).
    PROTOTYPE_REQUIRE_RENDER: bool = False

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

    # ── Startup restore admission control (D9 — KAN-139) ─────────────────────
    # Gate the restore_non_terminal_runs() concurrent resume drivers so N
    # non-terminal runs at restart do NOT fire N simultaneous Bedrock calls that
    # saturate the checkpointer pool (10 connections) and the Bedrock concurrency
    # limit, AND do NOT block the event loop with unbounded read_events queries
    # before the port is bound. The port is bound before restore_non_terminal_runs
    # returns because the lifespan `yield` delivers traffic immediately; restore
    # runs AFTER yield-ing only when all drivers are batched with a stagger.
    # RESTORE_ADMISSION_CONCURRENCY: max simultaneous resume drivers in flight.
    # RESTORE_ADMISSION_STAGGER_SECONDS: time-based stagger between batches (NOT a
    # lifetime lease — a gate-parked run never acquires the semaphore so this cannot
    # deadlock). Defaults match the KAN-139 spec (4 concurrent, 15s stagger).
    RESTORE_ADMISSION_CONCURRENCY: int = 4
    RESTORE_ADMISSION_STAGGER_SECONDS: float = 15.0

    # ── Sandbox sweep interval (D6 — KAN-139) ─────────────────────────────────
    # How often (seconds) the periodic sandbox sweep task runs in the background.
    # Default = 6 hours (21600s). Set lower in dev to observe sweeps faster.
    SANDBOX_SWEEP_INTERVAL_SECONDS: int = 21_600

    # RUN_DIR_TTL_HOURS: raised to 168h (7 days) to cover the revision-parent seed
    # window. The old 48h was too short — a run could be deleted before a user
    # creates a revision from it. Operator-overridable via the env var.
    # (Field already declared above; the default value update is noted here for
    # documentation; update the default if changing.)

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

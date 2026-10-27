"""Application configuration settings.

LLM provider notes
------------------
The backend uses AWS Bedrock via ``langchain_aws.ChatBedrockConverse``.
Auth comes from the boto3 default credential chain (instance profile in
prod, ``~/.aws/credentials`` / ``AWS_PROFILE`` locally). Requires
``BEDROCK_MODEL_ID`` and ``AWS_REGION``.
Mistral (``langchain_mistralai.ChatMistralAI``) is an optional, $0 free-tier provider
 — reachable as a fallback when neither Anthropic nor Bedrock is configured, or
forced explicitly via ``build_model(..., provider="mistral")`` (used by the eval
harness so it can run against Mistral without disturbing any other caller's
Anthropic/Bedrock config).

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
from urllib.parse import urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger("app.core.config")


def redact_db_url(url: str) -> str:
    """Return ``url`` with any inline password replaced by ``***``.

    In every deployed environment ``DATABASE_URL`` carries the Postgres
    password inline (``postgresql://user:password@host:5432/db``) because the
    on-host loader composes it that way. Logging that value verbatim wrote the
    LIVE database credential into CloudWatch on every single boot, where it sat
    for the log group's full retention window (14 days on dev) readable by any
    principal holding ``logs:GetLogEvents``. Redact before the value reaches a
    logger, never after.

    A URL with no password (e.g. the ``sqlite:///./dev.db`` default) is returned
    unchanged, so local output is unaffected.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        # Never let a malformed URL turn a startup banner into a crash, and
        # never fall back to echoing the raw value.
        return "<unparseable database url>"

    if not parts.password:
        return url

    netloc = f"{parts.username or ''}:***@{parts.hostname or ''}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


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


class CognitoMisconfigured(RuntimeError):
    """Raised at boot when the Cognito pool/client settings are unset in a
    non-development environment. See _validate_cognito_config."""


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

    # ---- Mistral (free-tier fallback / eval-harness opt-in) ----
    # When set, build_model() can reach langchain-mistralai's ChatMistralAI —
    # either as the third-tier fallback (only when neither ANTHROPIC_API_KEY nor
    # Bedrock resolves) or unconditionally via the explicit
    # build_model(provider="mistral") opt-in that the eval harness uses. Empty
    # (default) means Mistral is never reachable.
    MISTRAL_API_KEY: str = ""
    # mistral-small-latest — the closest weight-class match to Haiku 4.5 among
    # the free providers investigated (see specs/005-prompt-eval-scoring/research/candidate.md).
    # Overridable per-call via build_model(model=...).
    MISTRAL_MODEL_ID: str = "mistral-small-latest"

    # ---- AWS Bedrock ----
    # Foundation-model ID. The IAM policy in
    # infra/policies/bedrock-invoke.json scopes invoke to this exact ID, the
    # cross-region inference-profile ID, and the EU regions the profile fans
    # out to.
    BEDROCK_MODEL_ID: str = "anthropic.claude-haiku-4-5-20251001-v1:0"
    # The GLOBAL default model for every run that sets no override (spec 020 /
    # FR-13). The application invokes the inference profile (not the
    # foundation-model ID directly), so CloudWatch metrics dimension by this
    # string. This ONE line is the default: ~12 call sites read
    # ``settings.BEDROCK_INFERENCE_PROFILE_ID`` and none carries its own literal,
    # so an unset env var lands here and nowhere else.
    #
    # ⚠ DATA RESIDENCY — read before changing this to another `global.` profile.
    # GPT-5.6 is published ONLY as Global CRIS: `list_inference_profiles` on
    # eu-north-1 returns `global.openai.gpt-5.6-luna` and no `eu.openai.*` of any
    # kind (verified 2026-09-22). `global.` routes to whichever region has
    # capacity, WORLDWIDE, so every default run now leaves the EU. The Claude
    # entries stay on `eu.` prefixes and keep EU residency; `global.anthropic.*`
    # exists but was deliberately declined for exactly this reason.
    #
    # Revert = put back "eu.anthropic.claude-haiku-4-5-20251001-v1:0". One line,
    # no other code changes, no data migration.
    BEDROCK_INFERENCE_PROFILE_ID: str = "global.openai.gpt-5.6-luna"
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

    # ---- Host capacity matrix + admission gate (specs/014) --------------------
    # Reads the CPU/memory series the CloudWatch Agent already publishes
    # (infra/scripts/reconcile-host-config.sh) via the boto3 default credential
    # chain — same auth model as Bedrock/Cognito above, no new credentials.
    #
    # HOST_CAPACITY_ENABLED: master switch for collection (matrix + poller).
    # Independent of the gate switch below — the matrix can run read-only with
    # the gate off.
    HOST_CAPACITY_ENABLED: bool = True
    # HOST_CAPACITY_GATE_ENABLED: enforce the admission gate on launch/resume/
    # revision/etc. Originally defaulted OFF (D-10, specs/014 §5); switched ON
    # deliberately by the operator (RUNBOOK §capacity step 4, Option A) after
    # the ISS-1211 metric-dimension fix. Fail-open when blind; admins exempt.
    # Roll back by setting this to False and redeploying.
    HOST_CAPACITY_GATE_ENABLED: bool = True
    # Engage thresholds (specs/014 §10 Resolutions Q1 — operator-confirmed 75%
    # for both, deliberately tighter than the existing 80%/85% CloudWatch
    # alarms in infra/terraform/modules/monitoring/variables.tf).
    HOST_CAPACITY_CPU_THRESHOLD_PERCENT: float = 75.0
    HOST_CAPACITY_MEM_THRESHOLD_PERCENT: float = 75.0
    # Hysteresis band (specs/014 D-05): once engaged, the gate clears only
    # below (threshold - this margin), so a reading oscillating right at the
    # threshold does not flap the busy modal on and off.
    HOST_CAPACITY_CLEAR_MARGIN_PERCENT: float = 10.0
    # Consecutive breaching datapoints required to ENGAGE (mirrors the existing
    # alarms' evaluation_periods "sustained, not a burst" logic).
    HOST_CAPACITY_BREACH_DATAPOINTS: int = 2
    # Minimum time an engaged gate stays engaged, so one transient spike cannot
    # produce a three-second modal flash.
    HOST_CAPACITY_MIN_BLOCK_SECONDS: int = 60
    # A datapoint older than this is treated as UNKNOWN, not stale-but-valid —
    # unknown fails OPEN (specs/014 D-03/D-04). Bounds how long a broken poller
    # can keep gating the product on a frozen reading.
    HOST_CAPACITY_MAX_STALENESS_SECONDS: int = 300
    # Background poller cadence. The CloudWatch Agent itself publishes every
    # 60s, so polling faster than that buys nothing.
    HOST_CAPACITY_POLL_SECONDS: int = 30
    # ec2:DescribeInstances is the more expensive call and the instance list
    # changes rarely, so it is cached far longer than the metric poll.
    HOST_CAPACITY_INVENTORY_TTL_SECONDS: int = 300
    # CloudWatch namespace the agent publishes to. Empty (default) derives
    # "VelocityAI/{ENV.title()}" to match reconcile-host-config.sh's
    # `"namespace": "VelocityAI/${ENV_TITLE}"` exactly — see the model_validator
    # below. Override only if the agent config's namespace has diverged.
    HOST_CAPACITY_METRIC_NAMESPACE: str = ""
    # Optional comma-separated EC2 instance-id allow-list (specs/014 D-07 /
    # §10 Resolutions Q3). Highest precedence over discovery — set this and
    # tag-based ec2:DescribeInstances discovery is skipped entirely. Delivered
    # per environment as a GitHub Environment variable through the same SSM
    # pipeline as BEDROCK_MODEL_ID (see docs/GITHUB_CICD_SETUP.md). Empty
    # default = discover via instance tags (Project=velocityai,
    # Environment=<ENV>, state=running) — the default, per the operator's
    # confirmation that discovery should remain the primary path and a
    # supplied id only a cross-check.
    HOST_CAPACITY_INSTANCE_IDS: str = ""
    # Which instance's reading decides admission for a REQUEST TO THIS PROCESS.
    # "self"  (default) — the instance serving the request (resolved via IMDSv2
    #          at startup). Correct for today's single-instance deployment
    #          (specs/014 §10 Resolutions Q2 — operator-confirmed one instance).
    # "fleet_worst" — reserved for a future multi-instance fleet; deliberately
    #          not the default (one hot node would gate every node).
    HOST_CAPACITY_GATE_SCOPE: str = "self"
    # Retry-After (seconds) sent on a 503 host_capacity_exhausted rejection.
    HOST_CAPACITY_RETRY_AFTER_SECONDS: int = 120
    # botocore timeouts for the metrics adapter — deliberately tight, NOT the
    # Bedrock model clients' long read_timeout. A metrics call must fail fast; a hung
    # one must never wedge the background poller.
    HOST_CAPACITY_AWS_CONNECT_TIMEOUT: int = 5
    HOST_CAPACITY_AWS_READ_TIMEOUT: int = 10
    # Admin history charts (ADR-0056): GET /api/admin/capacity/history reads
    # CloudWatch on demand — the one sanctioned AWS call on a request path; it
    # never touches the admission gate. A successful result is cached this
    # many seconds per (instance, range, period) so an open Machines tab (60s
    # refresh) or several admins at once cost one GetMetricData call, not N.
    HOST_CAPACITY_HISTORY_CACHE_SECONDS: int = 60
    # Upper bound on cached history results. One 15-day / 1-minute entry holds
    # ~300k datapoints, so the cache is kept deliberately small.
    HOST_CAPACITY_HISTORY_CACHE_MAX_ENTRIES: int = 16

    # ---- Output token ceiling (single source of truth) ----
    # The Anthropic/Bedrock APIs REQUIRE a finite max_tokens on every call — it
    # cannot be omitted — so "no capping" means "run every agent at the model's
    # maximum" rather than truncating with small per-agent budgets. This value
    # is applied uniformly to ALL agents by the factory, overriding the per-agent
    # `max_tokens` declared in AGENT.md (which is retained only as documentation).
    # A model the catalog lists runs at its own ceiling instead
    # (model_catalog.max_output_tokens: Haiku 4.5 64K, Sonnet 4.6+/Opus 4.6+/Fable
    # 128K); this value is the cap for any model it does not list. Raise it only
    # after confirming the model accepts it, or Bedrock returns a ValidationException.
    MAX_OUTPUT_TOKENS: int = 32768

    # ---- Bedrock prompt caching (default ON) ----
    # Provider-agnostic Bedrock prompt caching (default ON); langchain_aws
    # _apply_cache_points reads only `ttl`, `type` is ignored (Converse always
    # uses "default"). deepagents' built-in AnthropicPromptCachingMiddleware
    # caches ONLY ChatAnthropic, so on Bedrock (prod) caching is silently OFF
    # without this — _BedrockCachePointsMiddleware injects the cache_control dict.
    BEDROCK_PROMPT_CACHE_ENABLED: bool = True
    BEDROCK_PROMPT_CACHE_TTL: str = "5m"

    # ---- Extended-thinking budget (enable-only, default ON) ----
    # Extended thinking is enabled by the non-zero default; 0 disables it. Only the
    # on/off switch now: the budget itself is derived from the call's max_tokens
    # (max_tokens - 1, floor 1024) in build_model, so it scales with each model's cap.
    THINKING_BUDGET_TOKENS: int = 32767

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
    # KAN-134: Per-subscriber queue maxsize for the per-run fan-out bus. Each SSE
    # client gets its own queue fed by the shared pump. A slow client that falls
    # behind (queue full) is silently evicted; it reconnects with Last-Event-ID and
    # replays the gap from the durable log. 1000 events ≈ 5–10 MB in memory per
    # subscriber. Set to 0 for unbounded (INV-3 parity with old single-queue model).
    SSE_SUBSCRIBER_QUEUE_MAXSIZE: int = 1000
    # P1 fix (COGNITO-AUTH-QA-BUGS.md "Stream Revocation"): how many live-drain
    # events pass before the attached SSE stream re-checks the caller's
    # revocation state (per-jti logout, password/role/tier change,
    # expiry). Checked on a cadence rather than every event since the check
    # hits the DB; a long-idle stream between events is covered separately by
    # the keepalive-triggered path in the endpoint's disconnect-poll loop.
    SSE_REVOCATION_CHECK_EVERY_N_EVENTS: int = 5
    # Idle-time bound on the SAME check: even a live-drain loop that sees no
    # events for a while (a long-running quiet agent step) re-checks
    # revocation at least this often, rather than only when the next event
    # happens to arrive.
    SSE_REVOCATION_CHECK_INTERVAL_SECONDS: int = 30

    # ---- Graceful shutdown budget (KAN-151 D8) ────────────────────────────
    # The container's hard ceiling is docker's stop_grace_period (30s, the backend
    # service in docker-compose.yml); uvicorn's own --timeout-graceful-shutdown (5s,
    # docker-entrypoint.sh) is spent BEFORE the lifespan body runs. Worst case from
    # SIGTERM to process exit, counting EVERY wait on the path:
    #    5  uvicorn graceful window      docker-entrypoint.sh
    #   10  Concierge drain              run_shutdown.py step 1
    #    3  Concierge cancel-and-wait    run_shutdown.py step 1 escalation
    #    3  pump drain                   run_shutdown.py step 2b
    #    3  pump cancel-and-wait         run_shutdown.py step 2b escalation
    #    1  checkpointer pool close      run_shutdown.py step 4 (ISS-106)
    #   ──
    #   25  with SHUTDOWN_STOP_RUNS off. Turning it on adds a driver drain plus its
    #       escalation (+3 +3) for 31s — PAST the SIGKILL line, which is the arithmetic
    #       reason production keeps it off. tests/unit/services/test_shutdown_reachability.py
    #       asserts this sum against the parsed stop_grace_period instead of trusting
    #       this comment: the previous version claimed "under 25s" while omitting both
    #       escalations and the pump drain entirely.
    #       Every wait on the path is now bounded: ISS-106 put a timeout around step 4's
    #       pool.close(), which used to sit unbounded on top of the drains.
    # A Concierge turn owns the ONLY durable write of its chat_reply row (_drive
    # inside run_commands.post_message) and is explicitly never cancelled on client
    # disconnect - so it is AWAITED, not cancelled, and only cut past this bound.
    SHUTDOWN_CONCIERGE_DRAIN_SECONDS: float = 10.0
    # How long to wait for run-transport teardown (pump tasks after A2, queue
    # sentinels) before escalating to task.cancel().
    SHUTDOWN_TASK_DRAIN_SECONDS: float = 3.0
    # ISS-106: how long step 4's close_checkpointer() may spend inside pool.close()
    # before abandoning it. A wedged Postgres close (in-flight statement, dead socket,
    # unresponsive server) used to be unbounded and sat AFTER every drain above, i.e.
    # directly against the SIGKILL deadline, with the shutdown summary never logged.
    SHUTDOWN_CHECKPOINTER_CLOSE_SECONDS: float = 1.0
    # D8/D9 conflict switch - see the D8 investigation section I11. When False the
    # shutdown leaves in-flight runs non-terminal so the next boot's
    # restore_non_terminal_runs auto-resumes them (the shipped Phase 45-50 tier).
    # When True the shutdown cooperatively cancels them: every in-flight run lands
    # "cancelled", auto-resume is replaced by the user's "Run again" button
    # (POST /api/runs/{id}/resume, resume_run_endpoint, already accepts "cancelled").
    #
    # The DEFAULT is environment-differentiated (ISS-088), resolved by
    # _default_shutdown_stop_runs_from_env below - this declared value is the
    # conservative one and is what every non-development ENV resolves to:
    #   production/staging/ci -> False. Deploys stay invisible to users mid-run,
    #     and the teardown budget stays under stop_grace_period (see above).
    #   development           -> True. Restarting the backend to stop an expensive
    #     experiment must actually stop it; an od_prototype build costs 5-21M Bedrock
    #     tokens and today survives the restart.
    # An explicit SHUTDOWN_STOP_RUNS env var always wins, in both directions.
    #
    # This is NOT already true by accident: uvicorn re-raises the captured signal
    # inside serve() (capture_signals) after restoring the default disposition, so
    # under SIGTERM the process dies before asyncio.run's _cancel_all_tasks can run and
    # no driver's CancelledError handler ever writes a terminal status. (Under SIGINT
    # the restored handler raises KeyboardInterrupt, which unwinds normally and DOES
    # reach that teardown - so Ctrl-C already cancels runs regardless of this switch.)
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
    # Root of the built-in global Skills catalog: <root>/<skill_id>/SKILL.md plus
    # each skill's sibling reference files. app/agents/skills_catalog.py scans it
    # (Library Skills tab, manifest `skills:`, composer-selected skills) and skill
    # staging copies a skill's folder into the run sandbox from it.
    # "" (default) = the checkout's backend/skills/global, so local dev, the test
    # suite and the characterization goldens resolve exactly what they always did.
    # The container image sets GLOBAL_SKILLS_ROOT=/app/builtin-skills/global
    # (backend/Dockerfile ENV): /app/skills is the per-user EBS bind-mount and
    # shadows anything baked under it, the same reason OD_ROOT exists. A value
    # that is not an existing directory never blocks boot: the catalog logs a
    # WARNING and falls back to the checkout default.
    GLOBAL_SKILLS_ROOT: str = ""
    # The remaining on-disk content roots, configurable the same way so every
    # path can follow wherever a deployment mounts it. "" (default) = the path
    # relative to backend/ that each module has always used, so the checkout and
    # the container image (backend/ == /app) resolve exactly what they did before.
    #   USER_SKILLS_ROOT   per-user SKILL.md + PROMPT_OVERRIDE.md   (backend/skills/users)
    #   GLOBAL_HOOKS_ROOT  built-in Hooks catalog                   (backend/hooks/global)
    #   PPTX_SKILLS_ROOT   shipped PPT reference docs               (backend/pptx)
    # OpenDesign is the OD_ROOT env var, read directly by app/services/od_loader.py.
    USER_SKILLS_ROOT: str = ""
    GLOBAL_HOOKS_ROOT: str = ""
    PPTX_SKILLS_ROOT: str = ""
    # Safety ceiling on one agent graph's model<->tool recursion. We DROP the old
    # tight per-agent iteration caps (build 3 / validate 8 / …) in favour of letting
    # agents explore + self-validate; this is only a runaway-loop backstop, not a
    # quality knob. Maps to LangGraph's recursion_limit.
    # Raised 400 -> 1000 after run 17de7ccb: a 32-screen prototype walk spent 133
    # model turns + 142 tool nodes doing real work (12 `edit_file` repairs) and was
    # cut off one step after writing its screenshot. 400 was sized for a smaller
    # prototype; it stopped being a runaway backstop and became a work ceiling.
    # Raised 1000 -> 2500 after run 5ab1be23: the backlog Reviewer was cut off at
    # 360 tool calls with its fixes unfinished. The platform must not be the
    # ceiling on a reviewer with genuine volume of work.
    AGENT_RECURSION_LIMIT: int = 2500

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

    # ── Cross-process revision-family lock (sandbox-git-versioning-v2 task 3.9) ─
    # Maximum seconds any caller may wait to acquire the family lock keyed on
    # (user_id, revision_root_id) before FamilyLockTimeout is raised. The lock
    # serializes revision admission, sandbox open, dirty recovery, uploads, restore,
    # and terminal finalization across processes. 120 s is generous enough to
    # accommodate a long finalizer pass while still bounding how long an upload or
    # revision-launch blocks before getting a clear failure.  The upload admission
    # table in Requirement 10 AC 10 explicitly names a "bounded-wait" ceiling for
    # the finalization-holds-lock case; this setting provides that ceiling uniformly.
    FAMILY_LOCK_TIMEOUT_S: int = 120

    # ── Browser URL policy (agent-browser-tools / FR-015) ────────────────────
    # Comma-separated list of URL schemes/hosts the browser tool is permitted to
    # visit. Each token controls:
    #   - "file": local files, resolved through RunSandbox.path_for (traversal-proof,
    #     cannot escape the run sandbox)
    #   - "localhost": http(s) on localhost / 127.0.0.1 only
    #   - "http": any http(s) URL (allows model-driven outbound egress from containers
    #     holding database credentials — same trust surface as web_fetch — which is why
    #     it is not in the default)
    # Parsing/enforcement of this policy is in T3b and later; this setting is the
    # configuration surface only.
    BROWSER_URL_POLICY: str = "file,localhost"

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

    # ---- Cognito: the sole authentication authority --------------------
    # Cognito-only auth migration (.kiro/specs/login/prompt.md Phase 1):
    # local bcrypt/HS256 authentication, the AUTH_PROVIDER dual-accept
    # switch, the AUTH_ALLOW_LEGACY_JWT dual-accept window, and the
    # BREAK_GLASS_ENABLED local-admin kill switch have all been removed.
    # Every principal is verified against Cognito; there is no other
    # credential authority and no local fallback. See
    # _validate_cognito_config below, which is now unconditional outside
    # ENV=development.
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_CLIENT_ID: str = ""
    COGNITO_CLIENT_SECRET: str = ""
    # Empty default: falls back to AWS_REGION when unset (see
    # core/cognito.py). Kept as a distinct setting because the Cognito pool
    # and the Bedrock region are configured independently even though they
    # are usually the same value in this deployment.
    COGNITO_REGION: str = ""
    COGNITO_JWKS_CACHE_TTL_SECONDS: int = 3600
    # Phase 6 item 1 (plan §5.5): require a confirmed second factor for ADMIN
    # operations. Cognito's MFA setting is pool-wide, so "admins only" has to be
    # an app-layer gate. Defaults to True as the secure default.
    ADMIN_MFA_REQUIRED: bool = True

    # ---- Post-expiry refresh grace window (P1 fix — token refresh) ----
    # POST /api/auth/refresh accepts an access token up to this many seconds
    # PAST its own `exp` (see core.identity.verify_credential(allow_expired=True)).
    # Without this, an idle REST-only client with no SSE stream attached has no
    # way to trigger a pre-expiry refresh (the frontend's pre-expiry timer only
    # runs inside an active stream's effect scope), so the token expires with no
    # recovery path and the user is forced to log in again on the very next
    # request. 5 minutes is generous enough to cover a request that was already
    # in flight when the token expired, or a client that reacts to a 401 within
    # a reasonable window, while still bounding how long a leaked/expired token
    # can be exchanged for a fresh one.
    AUTH_REFRESH_GRACE_SECONDS: int = 300

    # Mirrors the pool's email-OTP posture, published to SSM as
    # AUTH_EMAIL_MFA_ENABLED from the Terraform cognito module's DERIVED
    # email_mfa_active output (not its raw input flag).
    #
    # This is not a feature toggle for the endpoints -- it records a constraint
    # AWS imposes. Cognito refuses to let email be BOTH a second factor and the
    # account-recovery channel, and this pool has no phone numbers, so a pool
    # with email MFA is created with account_recovery_setting = admin_only. When
    # that is the case, `ForgotPassword` cannot deliver anything, so
    # /api/auth/forgot-password must say so plainly rather than return its usual
    # generic 202 and leave the user waiting for mail that will never arrive.
    #
    # Kept as an explicit setting rather than probed from Cognito at runtime: the
    # answer is a deploy-time property of the pool, and an unauthenticated
    # endpoint should not make an AWS call to decide how to answer.
    AUTH_EMAIL_MFA_ENABLED: bool = False

    # ---- Logging (M-06) ------------------------------------------------
    # app.agents / app.api carry prompts/payloads/user content at DEBUG — that
    # was previously HARDCODED to DEBUG in every environment (main.py), which is
    # the category of log most likely to leak sensitive request content once it
    # ships to CloudWatch (H-06). Environment-driven instead: defaults to DEBUG
    # in ENV=development (unchanged local-dev experience) and INFO everywhere
    # else. Override explicitly via env var if an environment genuinely needs
    # DEBUG temporarily for an investigation.
    # Accepted: DEBUG | INFO | WARNING | ERROR | CRITICAL. backend/.env sets
    # DEBUG locally; production sets WARNING. An unrecognised value logs a
    # warning and falls back to INFO rather than crashing at startup.
    LOG_LEVEL_APP: str = ""  # "" = derive from ENV (see app/core/logging.py)
    LOG_FORMAT: str = (
        ""  # "" = auto (pretty in development, json elsewhere); "json" | "pretty"
    )
    # JSON-formatted logs carry these two static fields on every line so a
    # CloudWatch Logs Insights query can filter/group by service+environment
    # without string-parsing the message. SERVICE_NAME defaults per-process;
    # docker-compose does not need to set it since each service just imports
    # this module inside its own container.
    SERVICE_NAME: str = "velocityai-backend"

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

    @field_validator(
        "GLOBAL_SKILLS_ROOT",
        "USER_SKILLS_ROOT",
        "GLOBAL_HOOKS_ROOT",
        "PPTX_SKILLS_ROOT",
        mode="before",
    )
    @classmethod
    def _normalize_global_skills_root(cls, value: object) -> str:
        """Coerce an unset value to "" and strip surrounding whitespace.

        A script-written env file often leaves a trailing newline or space, which
        would name a directory that does not exist and silently empty the
        catalog. Never raises: this runs at boot.
        """
        return "" if value is None else str(value).strip()

    @model_validator(mode="after")
    def _validate_cognito_config(self) -> "Settings":
        """Refuse to boot without a configured Cognito pool.

        Cognito is now the sole authentication authority (no local fallback,
        no AUTH_PROVIDER switch) — unconditional outside development.
        Mirrors ``_validate_secret_key``: this converts a silent
        misconfiguration (the SSM secrets-loader allowlist omission) into a
        loud, immediate startup error. In ``ENV=development`` we only warn,
        so a local `.env` without Cognito set up still boots for
        Cognito-independent local work (e.g. non-auth endpoints).
        """
        is_dev = self.ENV.lower() == "development"
        missing = [
            name
            for name, value in (
                ("COGNITO_USER_POOL_ID", self.COGNITO_USER_POOL_ID),
                ("COGNITO_CLIENT_ID", self.COGNITO_CLIENT_ID),
                ("COGNITO_CLIENT_SECRET", self.COGNITO_CLIENT_SECRET),
            )
            if not value
        ]
        if missing:
            message = (
                f"Cognito is the sole authentication authority but "
                f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} "
                "unset. The Cognito SSM parameters may exist but be missing "
                "from the on-host secrets-loader allowlist "
                "(infra/scripts/bootstrap-ec2.sh) — verify "
                "/etc/velocityai/app.env on the host."
            )
            if is_dev:
                logger.warning(message)
            else:
                raise CognitoMisconfigured(message)

        return self

    @model_validator(mode="after")
    def _default_shutdown_stop_runs_from_env(self) -> "Settings":
        """Resolve SHUTDOWN_STOP_RUNS' environment-differentiated default (ISS-088).

        Only when the operator did not supply a value: ``model_fields_set`` carries
        every field an env var, an ``.env`` entry or a constructor argument provided,
        so an explicit setting is never overridden - in either direction.
        """
        if "SHUTDOWN_STOP_RUNS" not in self.model_fields_set:
            self.SHUTDOWN_STOP_RUNS = self.ENV.lower() == "development"
        return self

    @model_validator(mode="after")
    def _default_host_capacity_namespace_from_env(self) -> "Settings":
        """Derive the CloudWatch namespace from ENV when unset (specs/014 §6).

        Must match ``reconcile-host-config.sh``'s
        ``"namespace": "VelocityAI/${ENV_TITLE}"`` byte-for-byte, or the
        adapter queries a namespace the CloudWatch Agent never publishes to
        and every reading comes back empty. ``ENV_TITLE`` there is the shell's
        capitalized deploy-environment name (e.g. ``Prod``, ``Dev``); ``.title()``
        on the Python side reproduces that for the common single-word values.
        Only applied when the operator did not supply an explicit value.
        """
        if "HOST_CAPACITY_METRIC_NAMESPACE" not in self.model_fields_set:
            self.HOST_CAPACITY_METRIC_NAMESPACE = f"VelocityAI/{self.ENV.title()}"
        return self

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

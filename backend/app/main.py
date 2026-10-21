"""FastAPI application entry point for the AI SaaS Platform."""

import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager

# ── Windows asyncio fix ────────────────────────────────────────────────────────
# Playwright (used by the html_render validator) launches a subprocess via
# asyncio. On Windows the default SelectorEventLoop does NOT support subprocess
# creation — only the ProactorEventLoop does. Setting the policy here, before
# uvicorn creates the loop, makes asyncio.create_subprocess_exec work correctly.
# This is a no-op on Linux/macOS (the condition is never true there).
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from botocore.exceptions import BotoCoreError
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.api.auth import router as auth_router
from app.api.chats import router as chats_router
from app.api.agents import router as agents_router
from app.api.skills import router as skills_router
from app.api.hooks import router as hooks_router
from app.api.workflows import router as workflows_router
from app.api.capabilities import router as capabilities_router
from app.api.runs import router as runs_router
from app.api.analytics import router as analytics_router
from app.api.run_commands import router as run_commands_router
from app.api.run_stream import router as run_stream_router
from app.api.user_agents import router as user_agents_router
from app.api.user_workflows import router as user_workflows_router
from app.api.handoff import router as handoff_router
from app.api.settings import router as settings_router
from app.api.mcp import router as mcp_router
from app.api.install import router as install_router
from app.api.websocket_handoff import router as websocket_handoff_router
from app.api.prototype_templates import router as prototype_templates_router
from app.api.ppt_templates import router as ppt_templates_router
from app.api.admin import router as admin_router
from app.api.admin_capacity import router as admin_capacity_router
from app.api.admin_capacity_history import router as admin_capacity_history_router
from app.api.file_extract import router as file_extract_router
from app.api.run_files import router as run_files_router
from app.api.run_figma_export import router as run_figma_export_router
from app.core.config import settings
from app.models.database import engine

# `settings` above and `app.core.logging`'s own `_early_settings` (imported at
# that module's top, before its `configure_logging()` reads it) are the SAME
# object -- Settings() is instantiated once at module import in app.core.config
# and both names bind to it. Logging setup itself now lives in app.core.logging
# so main.py isn't carrying it; call it here, at the same point it used to run.

from app.core.logging import configure_logging, _request_id_var  # noqa: E402 - preserves original setup-order point

configure_logging()

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
    logger.info(
        "🔍 LangSmith tracing ENABLED — project: %s",
        os.getenv("LANGSMITH_PROJECT", "default"),
    )
else:
    logger.info("LangSmith tracing disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create database tables on startup."""
    logger.info("🚀 Starting VelocityAI Backend...")
    if settings.ANTHROPIC_API_KEY:
        logger.info(
            "   LLM provider: anthropic-direct (model=%s)",
            settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5",
        )
    elif settings.AWS_BEARER_TOKEN_BEDROCK:
        logger.info(
            "   LLM provider: bedrock-bearer-token (model=%s region=%s)",
            settings.BEDROCK_INFERENCE_PROFILE_ID
            or settings.BEDROCK_MODEL_ID
            or "NOT SET",
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
        # ── ISS-084: arm the cooperative STOP signal for every resume-family drive.
        # The engine spawns those drivers itself (restore_non_terminal_runs), so unlike a
        # launch there is no caller to hand it a cancel_event — without this line
        # _drive_resumed_stream passes None and Stop / POST /cancel / SIGTERM / a restart
        # are ALL no-ops for any run that has crossed a restart. Returns the SAME Event
        # object the REST cancel endpoint sets (one registry, one object).
        engine_instance._resume_cancel_event = _ws_bridge._resume_cancel_event
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
        # ── BUG-R03: arm the resume output-column persister on the SAME engine instance so an
        # AUTO-RESUMED run (restore_non_terminal_runs branch b) persists its output-bearing
        # WorkflowRun columns (output/agent_outputs/token_usage/duration/deliverable_*) on
        # resume-completion — the columns _drive_launch_to_queue writes on the launch path but
        # neither resume entry point replicated (the run then read empty from /chain-context,
        # /summary, analytics, export). App→app import (the kernel never imports app.*); fired
        # from _drive_resumed_stream's finally, reading the owner-scoped durable tail.
        from app.api.run_commands import persist_resume_output_columns

        engine_instance._resume_output_persist_sink = persist_resume_output_columns
        await engine_instance.restore_non_terminal_runs()
    except Exception as _startup_exc:
        logger.warning("Startup restoration failed (non-fatal): %s", _startup_exc)

    # D6 (KAN-139): start the periodic sandbox sweep task so run dirs no longer
    # accumulate on the 60 GB root volume for the process lifetime.
    # The sweep is DB-backed — it queries non-terminal run IDs PLUS the in-process
    # live registry before deleting, so an active build run (even one with a stale
    # directory mtime, e.g. prototype build edit_file path) is never deleted.
    # TTL is raised to 168 hours (7 days) in config to cover the revision-parent
    # seed window (48 h was too short).  Scheduled every 6 hours — one sweep per
    # startup + periodic sweeps thereafter, never blocking the event loop (offloaded
    # to a thread via asyncio.to_thread).
    import asyncio as _asyncio

    async def _sandbox_sweep_loop() -> None:
        """Periodic sandbox sweep — runs every SANDBOX_SWEEP_INTERVAL_SECONDS (config)."""
        while True:
            await _asyncio.sleep(settings.SANDBOX_SWEEP_INTERVAL_SECONDS)
            try:
                from app.models.database import SessionLocal
                from app.models.workflow import WorkflowRun
                from app.api.run_engine import _PIPELINE_QUEUES
                from app.agents.sandbox import sweep_expired
                from agents.execution_engine.engine import TERMINAL_RUN_STATUSES

                # Task 3.8 (sandbox-git-versioning-v2): build the protected set by
                # walking parent_run_id via the canonical resolve_revision_root
                # resolver (Requirement 2 AC 1, V2-Q1).
                #
                # The old code walked source_run_id via _find_chain_root, which is
                # the workflow-chaining edge — not the revision-family edge.  A live
                # revision therefore never protected its shared physical sandbox
                # (keyed on parent_run_id root), producing the D1 defect.
                #
                # V2 rules:
                #   • parent_run_id defines physical sandbox identity (V2-Q1).
                #   • source_run_id is a workflow-chaining edge and NEVER changes the
                #     physical sandbox (Requirement 2 AC 2–3).
                #   • A gate-paused OR active descendant protects the family root
                #     (Requirement 2 AC 14 — "waiting_for_user" is non-terminal).
                #   • On resolver failure → protected, never deletable
                #     (Requirement 2 AC 11, AC 15).
                #   • The DB session MUST be open for the duration of root resolution
                #     because resolve_revision_root makes per-hop DB queries.
                from app.api.runs import (
                    resolve_revision_root,
                    RevisionRootResolved,
                )

                _db = SessionLocal()
                try:
                    # Fetch (id, user_id) for all non-terminal runs.
                    # Non-terminal statuses include "waiting_for_user" which covers
                    # gate-paused runs — they protect the family (Requirement 2 AC 14).
                    # We use user_id (the authz key) rather than owner_id (the legacy
                    # backfilled column) for ownership-scoped resolution.
                    _rows = (
                        _db.query(WorkflowRun.id, WorkflowRun.user_id)
                        .filter(WorkflowRun.status.notin_(TERMINAL_RUN_STATUSES))
                        .all()
                    )
                    # Also cover in-process live run ids that may not yet have a
                    # non-terminal DB row (race window at launch / startup restore).
                    _live_ids = set(_PIPELINE_QUEUES.keys())
                    _db_ids = {r.id for r in _rows}
                    _extra_ids = _live_ids - _db_ids
                    _extra_rows: list = []
                    if _extra_ids:
                        _extra_rows = (
                            _db.query(WorkflowRun.id, WorkflowRun.user_id)
                            .filter(WorkflowRun.id.in_(_extra_ids))
                            .all()
                        )
                    _all_pairs = list(_rows) + _extra_rows

                    # Resolve each (run_id, user_id) pair to its revision-root
                    # sandbox directory id via the canonical parent_run_id walk.
                    # The DB session stays open here because resolve_revision_root
                    # issues per-hop queries against it.
                    #
                    # On RevisionRootUnresolved (cycle, missing ancestor, cross-owner,
                    # null principal, DB error) → fail CLOSED: add the run's own id to
                    # the protected set so the directory is never deleted on a resolver
                    # failure (Requirement 2 AC 11, AC 15).
                    protected: set[str] = set()
                    for _run_id, _user_id in _all_pairs:
                        if not _user_id:
                            # Null principal → fail closed: protect the run's own dir.
                            logger.debug(
                                "sandbox sweep: null user_id for run %s — protecting (fail closed)",
                                _run_id,
                            )
                            protected.add(_run_id)
                            continue
                        _result = resolve_revision_root(_db, _run_id, _user_id)
                        if isinstance(_result, RevisionRootResolved):
                            protected.add(_result.root_id)
                        else:
                            # RevisionRootUnresolved — fail closed (Requirement 2 AC 11).
                            logger.debug(
                                "sandbox sweep: resolve_revision_root failed for run %s "
                                "(reason=%s visited=%d repeated=%s) — protecting (fail closed)",
                                _run_id,
                                _result.reason,
                                _result.visited_count,
                                _result.repeated_node,
                            )
                            protected.add(_run_id)

                finally:
                    _db.close()

                # Belt-and-suspenders: also protect the raw live ids directly —
                # in case the DB row is absent (race at launch) the run's own dir
                # would not be covered by the resolution above.
                protected.update(_live_ids)

                removed = await _asyncio.to_thread(
                    sweep_expired,
                    ttl_hours=settings.RUN_DIR_TTL_HOURS,
                    protected_run_ids=protected,
                )
                if removed:
                    logger.info("sandbox sweep: removed %d expired run dir(s)", removed)
            except Exception as _sweep_exc:  # noqa: BLE001
                logger.warning("sandbox sweep failed (non-fatal): %s", _sweep_exc)

    _sweep_task = _asyncio.create_task(_sandbox_sweep_loop())

    # Event-loop lag watchdog (STABILIZATION.md diagnosability): a 2026-09-02
    # postmortem found the process pinned at ~39% CPU for 5h19m with zero log
    # output after a run's SSE close — no traceback, nothing to diagnose from.
    # This task makes the NEXT such stall a lag value + a task-stack dump
    # instead of a guess. See app/core/watchdog.py for the detection logic.
    from app.core.watchdog import watch_event_loop_lag

    _watchdog_task = _asyncio.create_task(watch_event_loop_lag())
    # specs/014 (host capacity matrix + admission gate): periodic poller that
    # reads CPU/memory from CloudWatch (via app.services.host_metrics) and
    # publishes a decision into the process-local app.services.capacity_state
    # holder. Mirrors the sandbox-sweep shape immediately above: interval from
    # settings, the blocking boto3 call offloaded via asyncio.to_thread, broad
    # non-fatal except (a monitoring outage must never crash the app — D-03),
    # cancel-then-await on shutdown. Skipped entirely when HOST_CAPACITY_ENABLED
    # is off, so a disabled deployment pays zero background cost.
    _capacity_task = None
    if settings.HOST_CAPACITY_ENABLED:

        async def _capacity_poll_loop() -> None:
            """Periodic host-capacity poll — runs every HOST_CAPACITY_POLL_SECONDS.

            Logs only on a STATE TRANSITION (blind<->known, engaged<->allowing),
            never once per tick — D-03 asks for a log per transition, not a
            WARNING every HOST_CAPACITY_POLL_SECONDS while a state persists.
            """
            from datetime import datetime, timezone

            from app.services import capacity_state, host_metrics

            while True:
                try:
                    prev = capacity_state.current_decision()
                    snapshot = await _asyncio.to_thread(host_metrics.collect_snapshot)
                    decision = capacity_state.advance(
                        snapshot, datetime.now(timezone.utc)
                    )
                    if decision.blind and not prev.blind:
                        logger.warning(
                            "host capacity: now blind (%s)", decision.blind_reason
                        )
                    elif not decision.blind and prev.blind:
                        logger.info("host capacity: monitoring recovered")
                    if decision.engaged and not prev.engaged:
                        logger.warning(
                            "host capacity: gate engaged — signals=%s",
                            [(s.name, s.value, s.threshold) for s in decision.signals],
                        )
                    elif prev.engaged and not decision.engaged:
                        logger.info("host capacity: gate cleared")
                except Exception as _capacity_exc:  # noqa: BLE001
                    logger.warning(
                        "host capacity poll failed (non-fatal): %s", _capacity_exc
                    )
                await _asyncio.sleep(settings.HOST_CAPACITY_POLL_SECONDS)

        _capacity_task = _asyncio.create_task(_capacity_poll_loop())

    yield

    # ── Shutdown sequence (D7 — KAN-139). The checkpointer pool close is NOT wired
    # here. It is step 4 of shutdown_run_infrastructure() below, which must run LAST
    # among the awaits because the Concierge drain and the pump teardown ahead of it
    # may still hold a pooled connection. Closing it here as well ran it FIRST, which
    # made that documented ordering guarantee false in every environment — and with
    # SHUTDOWN_STOP_RUNS on it would leave stop_pipeline_drivers() driving runs against
    # an already-closed pool (get_checkpointer() raises after close).
    _sweep_task.cancel()
    try:
        await _sweep_task
    except _asyncio.CancelledError:
        pass

    _watchdog_task.cancel()
    try:
        await _watchdog_task
    except _asyncio.CancelledError:
        pass
    if _capacity_task is not None:
        _capacity_task.cancel()
        try:
            await _capacity_task
        except _asyncio.CancelledError:
            pass

    # ── KAN-151 D8: the shutdown half of the application lifecycle. ────────────
    # Reachable only because the process is launched with --timeout-graceful-shutdown
    # (docker-entrypoint.sh in production; the documented local run command otherwise —
    # see README.txt). With uvicorn's unbounded default a live SSE stream makes this
    # code unreachable: measured, the process stayed alive past 30s on SIGTERM and only
    # `startup_complete` was ever recorded (ISS-088, pinned by
    # tests/unit/services/test_shutdown_reachability.py).
    # The body itself lives in app.api.run_shutdown so main.py never reaches into
    # the private per-run registries; it never raises, so a teardown failure cannot
    # turn a clean exit into uvicorn's "Application shutdown failed".
    try:
        from app.api.run_shutdown import shutdown_run_infrastructure

        _summary = await shutdown_run_infrastructure()
        logger.info("shutdown summary: %s", json.dumps(_summary, default=str))
    except Exception as _shutdown_exc:  # noqa: BLE001
        logger.error(
            "Shutdown teardown failed (non-fatal): %s", _shutdown_exc, exc_info=True
        )
    logger.info("🔴 Shut down complete.")


app = FastAPI(
    title="AI SaaS Platform",
    description="Enterprise-grade AI SaaS platform with multi-agent orchestration",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware configuration
#
# COGNITO-MIGRATION-PLAN §3.6 / Phase 6 item 4: this block previously
# HARDCODED the three localhost dev origins and ignored `settings.CORS_ORIGINS`
# entirely, while still setting `allow_credentials=True`. That was harmless
# under a pure bearer-token transport (the browser never sends ambient
# credentials, so a permissive-but-wrong origin list grants nothing), but it is
# a hard blocker for the Phase 6 cookie/BFF session: the moment the session
# moves to a cookie, `allow_credentials=True` combined with an origin list that
# doesn't match the real deployment either breaks every production request or —
# if someone "fixes" it by widening the list — turns into a cross-origin
# credential leak. Fixing the drift is therefore a PREREQUISITE, not a cleanup.
#
# The production origin list comes from SSM (`CORS_ORIGINS`, a JSON array) via
# the on-host secrets loader. The localhost origins are appended ONLY in
# development so a local `next dev` on :3000/:3001 keeps working without
# operators having to hand-maintain dev origins in production config.
_cors_origins = list(settings.CORS_ORIGINS)
if settings.ENV.lower() == "development":
    for _dev_origin in (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ):
        if _dev_origin not in _cors_origins:
            _cors_origins.append(_dev_origin)

# Never allow the wildcard together with credentials. The CORS spec forbids the
# combination, and browsers reject it — but Starlette will happily emit it, so a
# misconfigured CORS_ORIGINS would produce confusing "works in curl, fails in
# browser" behaviour instead of a clear error. Fail fast and loudly instead.
if "*" in _cors_origins:
    raise RuntimeError(
        "CORS_ORIGINS contains '*', which cannot be combined with "
        "allow_credentials=True. List the exact origins instead."
    )

logger.info("CORS allow_origins=%s (env=%s)", _cors_origins, settings.ENV)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # KAN-131: expose X-Total-Count so the frontend can read the total run count
    # for pagination without a separate request. Custom response headers are NOT
    # accessible from browser fetch() by default — they must be explicitly listed
    # in Access-Control-Expose-Headers.
    # specs/014: expose Retry-After so the capacity gate's 503 rejections let the
    # frontend show a countdown — otherwise the header is silently invisible to
    # fetch() despite being present on the wire.
    expose_headers=["X-Total-Count", "Retry-After"],
)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    """M-02: adopt nginx's X-Request-ID (forwarded per the reconcile-host-config.sh
    proxy-headers snippet), or mint one for a request that arrived without it
    (local dev / a request that bypassed nginx). Stashed in the module-level
    contextvar so every log line emitted while handling this request carries
    it (via ``_RequestIdFilter``), and echoed back on the response so a client
    can quote it when reporting an issue.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = _request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


# STABILIZATION.md diagnosability: any request whose handler takes longer than
# this is logged (method/path/duration) so a slow/blocked endpoint shows up in
# the log without needing the event-loop lag watchdog to catch it too.
_SLOW_REQUEST_THRESHOLD_SECONDS = 5.0


@app.middleware("http")
async def _slow_request_middleware(request: Request, call_next):
    """Log any request that takes longer than ``_SLOW_REQUEST_THRESHOLD_SECONDS``.

    Logged on both success and failure (the ``finally``) — a slow request that
    ultimately errors is exactly as diagnostically interesting as a slow one
    that succeeds.
    """
    start = time.monotonic()
    try:
        response = await call_next(request)
        return response
    finally:
        duration = time.monotonic() - start
        if duration > _SLOW_REQUEST_THRESHOLD_SECONDS:
            logger.warning(
                "slow request: method=%s path=%s duration=%.2fs",
                request.method,
                request.url.path,
                duration,
            )


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    """ISS-224/ISS-257: never echo a rejected value back to the client.

    FastAPI's default 422 handler serialises Pydantic's error shape as-is, and
    that shape carries ``input`` — the COMPLETE value that failed validation.
    For a length-constrained credential (``GithubPATRequest.pat``,
    ``RegisterRequest.password``) that means the submitted secret round-trips
    back in the response body. Nothing in the error tells us which fields are
    sensitive, so ``input`` is dropped for every field on every route; ``loc``,
    ``msg``, ``type`` and ``ctx`` are untouched, so the body still says exactly
    what was wrong and where.
    """
    errors = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": errors}))


@app.exception_handler(BotoCoreError)
async def _botocore_error_handler(request: Request, exc: BotoCoreError):
    """ISS-1150: a botocore call that never completed (expired SSO token, no
    credentials, unreachable endpoint) and that no route translated is a 503.

    Keyed on the class on purpose. Starlette mounts an ``Exception`` or ``500``
    handler on ServerErrorMiddleware, OUTSIDE CORSMiddleware, so that response
    still reaches the browser with no CORS header and reads as a CORS block. Any
    other key is served inside it. Logged here because a handled exception no
    longer reaches Starlette's own error log.
    """
    logger.error(
        "Unhandled botocore error on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "A cloud service is unavailable. Please try again."},
    )


# Register routers
app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(agents_router)
app.include_router(skills_router)
app.include_router(hooks_router)
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
app.include_router(user_agents_router)
app.include_router(handoff_router)
app.include_router(settings_router)
app.include_router(mcp_router)
app.include_router(install_router)
app.include_router(websocket_handoff_router)
app.include_router(prototype_templates_router)
app.include_router(ppt_templates_router)
app.include_router(admin_router)
# specs/014: admin-only, read-only host capacity matrix. Own module (not
# admin.py) so admin_capacity.py stays free of the Cognito user-management
# imports; shares the /api/admin prefix (FastAPI allows multiple routers per
# prefix, same as runs_router/run_stream_router/run_commands_router do for
# /api/runs).
app.include_router(admin_capacity_router)
# ADR-0056: admin-only history charts. Its own module because, unlike the
# matrix above, it reads CloudWatch on demand — keeping admin_capacity.py's
# "never calls AWS" guarantee literally true.
app.include_router(admin_capacity_history_router)
app.include_router(file_extract_router)
# UPLD-01: owner-scoped, capped document upload → RunSandbox ``.uploads/`` prefix
# (additive — shares the /api/runs prefix; no new table / migration).
app.include_router(run_files_router)
# Figma export — Playwright SCRAPE_FN + IRNode mapper in plugin.
# Shares /api/runs prefix. Falls back to 503 when Playwright unavailable.
app.include_router(run_figma_export_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    llm_configured = bool(settings.BEDROCK_MODEL_ID and settings.AWS_REGION)
    return {
        "status": "healthy",
        "llm_provider": "bedrock" if llm_configured else "none",
        "langsmith": langsmith_enabled,
    }


# ---------------------------------------------------------------------------
# /s/{token} — unauthenticated public share route (Option B).
#
# Serves ONLY the deliverable (output bytes + Content-Type).  Never echoes
# input, agent_outputs, token_usage, owner_id, or any PII.  Access is bounded
# by the share_token uniqueness and its expiry (share_expires_at).
# ---------------------------------------------------------------------------


@app.get("/s/{token}")
async def view_shared_run(token: str):
    """Return the deliverable for a public share token — NO auth required.

    SC-001: dispatches on ``deliverable_mimetype`` (generic), never on a
    workflow-name literal.  Returns 404 for missing or expired tokens so the
    caller cannot distinguish the two cases (no enumeration).
    """
    from fastapi.responses import HTMLResponse, PlainTextResponse, Response as _Resp
    from app.models.database import get_db as _get_db
    from app.api.runs import get_shared_run_by_token

    db_gen = _get_db()
    db = next(db_gen)
    try:
        run = get_shared_run_by_token(token, db)
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    if run is None or not run.output:
        raise HTTPException(status_code=404, detail="Share not found or expired.")

    output = run.output
    mimetype = run.deliverable_mimetype or "text/html"

    # Strip JSON envelope if present (the output column stores a JSON string
    # for prototype HTML when the serialized_sandbox strategy is used).
    if mimetype == "text/html" and output.startswith('"') and output.endswith('"'):
        import json as _json

        try:
            output = _json.loads(output)
        except Exception:
            pass

    # Content-Security-Policy: sandbox so the shared prototype cannot run
    # arbitrary JS in the viewer's main browsing context.
    share_headers = {
        # Opaque origin: adding allow-same-origin would undo the isolation.
        "Content-Security-Policy": "sandbox allow-scripts",
        "X-Frame-Options": "SAMEORIGIN",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        # Cache for 5 minutes on CDN; revoked tokens return 404 immediately.
        "Cache-Control": "public, max-age=300, stale-while-revalidate=60",
    }

    from agents.capabilities.deliverables._mimetype import BINARY_MIMETYPES

    if mimetype in BINARY_MIMETYPES and run.deliverable_filename:
        # output holds the text form; the deliverable itself is the sandbox file.
        from app.agents.sandbox import RunSandbox
        from app.api.run_files import _resolve_chain_root_or_404

        try:
            root_id = _resolve_chain_root_or_404(run.id, run.user_id)
            path = RunSandbox(
                run.user_id, root_id, runs_root=settings.RUNS_ROOT
            ).path_for(run.deliverable_filename)
            data = path.read_bytes()
        except (ValueError, OSError):
            raise HTTPException(
                status_code=404, detail="Share not found or expired."
            ) from None
        return _Resp(content=data, media_type=mimetype, headers=share_headers)
    if mimetype == "text/html":
        return HTMLResponse(content=output, headers=share_headers)
    if mimetype in ("text/markdown", "text/plain"):
        return PlainTextResponse(content=output, headers=share_headers)
    # Generic fallback — let the browser decide.
    return _Resp(
        content=output.encode() if isinstance(output, str) else output,
        media_type=mimetype,
        headers=share_headers,
    )

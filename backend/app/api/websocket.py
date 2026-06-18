"""WebSocket endpoint for real-time AI chat streaming."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.agents.chat_runner import ChatRunner
from app.agents.llm_errors import map_exception as _map_llm_exception
from app.agents.model_factory import ModelConfigurationError
from app.agents.modes import get_mode_prompt
from app.core.config import settings
from app.core.security import decode_access_token, is_token_revoked
from app.models.chat import ChatSession, Message
from app.models.database import SessionLocal
from app.models.user import User
from app.models.workflow import WorkflowRun

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pipeline event queue registry
# ---------------------------------------------------------------------------
# Decouples pipeline execution from the WebSocket connection.
# Each running pipeline writes events to a queue keyed by pipeline_run_id.
# The WebSocket drains the queue. If the WS disconnects and reconnects,
# the new connection picks up the same queue and resumes streaming.
# A sentinel value of None signals the pipeline has finished.

_PIPELINE_QUEUES: dict[str, asyncio.Queue] = {}
_PIPELINE_TASKS: dict[str, asyncio.Task] = {}  # pipeline_run_id → background task
# ISS-007 (16-02): per-run COOPERATIVE cancel signal. The Stop button
# (``cancel_pipeline``) sets this event instead of destructively cancelling the
# drainer task; the engine observes it (per-chunk / pre-agent) and emits
# ``pipeline_cancelled`` through the normal persisted+drained path, so the live
# wire receives the terminal and the FE clears its in-flight cards. Keyed by
# pipeline_run_id only (SC-001 — no workflow/model name).
_CANCEL_EVENTS: dict[str, asyncio.Event] = {}


def _get_or_create_queue(pipeline_run_id: str) -> asyncio.Queue:
    if pipeline_run_id not in _PIPELINE_QUEUES:
        _PIPELINE_QUEUES[pipeline_run_id] = asyncio.Queue(maxsize=0)  # unbounded
    return _PIPELINE_QUEUES[pipeline_run_id]


def _cleanup_pipeline(pipeline_run_id: str) -> None:
    _PIPELINE_QUEUES.pop(pipeline_run_id, None)
    _PIPELINE_TASKS.pop(pipeline_run_id, None)
    _CANCEL_EVENTS.pop(pipeline_run_id, None)


# ---------------------------------------------------------------------------
# Engine→WS live-task bridge for AUTO-RESUMED runs (12-09 Gap 2a)
# ---------------------------------------------------------------------------
# An auto-resumed run (engine.resume_run, driven by restore_non_terminal_runs
# on startup) was never registered in _PIPELINE_TASKS/_PIPELINE_QUEUES, so a
# reconnect during the resumed run took the live:false branch and never
# received the resumed tail (incl. pipeline_complete). These two functions are
# the app-layer half of the bridge: they are INJECTED onto the engine instance
# in app/main.py at startup (the single wiring site) — the engine never imports
# app.api (import-linter forbidden direction; the bridge is a callback). The
# bridge is purely ADDITIVE: the legacy run_pipeline registration path below is
# unchanged. Workflow-agnostic — keyed by run_id only (SC-001). Cleanup reuses
# _cleanup_pipeline (injected as the engine's _resume_cleanup hook).


def _register_resume_queue(pipeline_run_id: str) -> asyncio.Queue:
    """Return/create the live event queue for an auto-resumed run.

    Recorded in _PIPELINE_QUEUES so a reconnect_pipeline mid-resume finds a
    live queue and attaches its drainer (the live:true branch).
    """
    return _get_or_create_queue(pipeline_run_id)


def _register_resume_task(pipeline_run_id: str, task: asyncio.Task) -> None:
    """Record an auto-resumed run's driver task in _PIPELINE_TASKS.

    A reconnect_pipeline checks ``task.done()`` — a live resume driver makes
    _has_live_task true; a finished one naturally falls back to the durable
    replay + status branch.
    """
    _PIPELINE_TASKS[pipeline_run_id] = task


def _validate_model_overrides(
    model_overrides: dict, run_agent_ids: set[str]
) -> str | None:
    """Allow-list-validate the per-run ``{agent_id → model_id}`` override map.

    The security chokepoint for MODEL-03 (Phase 6 D-07, [HIGH] threat T-06-06):
    ``model_overrides`` is UNTRUSTED run-payload input crossing into model
    selection. Each entry is checked against TWO allow-lists, both derived from
    authoritative sources (never an arbitrary string, Q2 trust):

      * ``model_id ∈ ModelCatalog.ids()`` — the kernel-pure model catalog (06-01)
        is the ONE authoritative model-id list (INV-12). An unknown/arbitrary
        model id (unknown-provider / cost-abuse / invalid-model-crash vector) is
        rejected here.
      * ``agent_id ∈ run_agent_ids`` — the resolved agent set for THIS run
        (``get_pipeline_agents`` / the custom ``agent_ids`` list). An override
        targeting a non-existent agent (silent no-op, T-06-07 [MED]) is rejected.

    Returns ``None`` when every entry is valid (or the map is empty — the
    no-override default the frontend sends until Phase 8). On the FIRST
    violation returns a human-readable error message naming the bad value; the
    caller emits the existing ``{"type":"error", ..., "code":"invalid_model_override"}``
    event and rejects the run BEFORE ``engine.execute`` is called.
    """
    if not model_overrides:
        return None
    # Type guard (CR-01): ``model_overrides`` is UNTRUSTED run-payload input. The
    # ``or {}`` normalisation at the call sites only swaps FALSY values for ``{}``;
    # a truthy non-dict ("evil_string", ["list"]) — or a dict with non-string
    # keys/values — passes through and would crash on ``.items()`` / the set
    # membership check, killing the asyncio task silently (no error event, leaked
    # _PIPELINE_TASKS). REJECT malformed input with the same str-return contract as
    # every other violation, so the caller emits ``code="invalid_model_override"``
    # and refuses the run before any WorkflowRun is created.
    if not isinstance(model_overrides, dict):
        return (
            f"model_overrides must be an object mapping agent_id to model_id "
            f"(got {type(model_overrides).__name__!r})"
        )
    # Import the kernel-pure catalog lazily (app → kernel import is allowed; the
    # catalog has no app.* reach so this stays import-clean).
    from agents.capabilities.model_catalog import ModelCatalog

    allowed_model_ids = set(ModelCatalog().ids())
    for agent_id, model_id in model_overrides.items():
        if not isinstance(agent_id, str) or not isinstance(model_id, str):
            return (
                f"model_overrides entries must be string agent_id → string "
                f"model_id; got {agent_id!r}: {model_id!r}"
            )
        if agent_id not in run_agent_ids:
            return (
                f"model_overrides targets agent {agent_id!r}, which is not part "
                f"of this run's agents"
            )
        if model_id not in allowed_model_ids:
            return (
                f"model_overrides for agent {agent_id!r} requests model "
                f"{model_id!r}, which is not an allowed model"
            )
    return None


def _revalidate_selections_trust_user(
    base_pipeline_type: str,
    agent_ids: list[str],
    selections: dict | None,
) -> str | None:
    """LAUNCH-side CAP-03 re-validation of persisted per-step selections (Pitfall 3).

    EMP-02 / T-22-04-02: the FE lock + the SAVE-time check are NOT sufficient — a
    saved row could be TAMPERED after save (its ``manifest_json`` mutated to
    reference a ``user_allowed=False`` capability). So the launch path re-synthesizes
    the SAME ``WorkflowManifest`` (the shared ``agents.workflows.selections`` synth
    seam — no duplicated logic) and re-compiles it with ``trust="user"`` BEFORE
    execute. The dormant ``_check_trust`` path rejects any non-user-allowed reference
    (or ceiling-raising Limits), so a tampered row is REJECTED at launch, not run.

    Returns ``None`` when the selections are clean (or empty — parity), else a
    human-readable error message naming the offending ``(kind, name)`` (the caller
    emits the existing error-event shape and refuses the run before execute).
    """
    from agents.workflows.selections import (
        has_selections,
        validate_selection_model_ids,
    )

    if not has_selections(selections):
        return None

    # CR-01: a per-step ``model`` selection takes a different route than the
    # ``model_overrides`` map and is never catalog-validated by the trust=user
    # compile (the compiler accepts any string model id). Enforce the SAME allow-list
    # the MODEL-03 chokepoint applies, at the LAUNCH chokepoint, before execute — so a
    # crafted ``run_pipeline`` selections payload cannot route to an unintended /
    # disallowed provider via ``build_model``.
    _model_error = validate_selection_model_ids(selections)
    if _model_error is not None:
        return _model_error

    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.selections import synthesize_manifest

    manifest = synthesize_manifest(base_pipeline_type, agent_ids, selections)
    try:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    except CompilerError as exc:
        return f"Rejected persisted selection: {exc}"
    return None


def _get_db() -> Session:
    """Create a new database session for WebSocket use."""
    return SessionLocal()


def _review_gate_owned_by(gate_key: str, user_id: str) -> bool:
    """True iff the run named in ``gate_key`` (``{run_id}:{agent_id}``) belongs
    to ``user_id``.

    The gate response is a cross-run WRITE — ``approved``/``edited_content``
    resolve the named run's HITL gate and are folded into its results — so it
    must be owner-gated like every other cross-run surface (13-REVIEW CR-01 /
    T-13-01-01). Ownership is matched on ``WorkflowRun.user_id``: it is set at
    every creation site, whereas ``owner_id`` is a nullable Phase-5 backfill
    the main WS creation path leaves unset. An unknown run and an unowned run
    are indistinguishable to the caller (no run-existence oracle) — both deny.
    """
    run_id = (gate_key or "").split(":", 1)[0]
    if not run_id:
        return False
    db = _get_db()
    try:
        row = (
            db.query(WorkflowRun.id)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == user_id)
            .first()
        )
    finally:
        db.close()
    return row is not None


def _extract_message_text(content: Any) -> str:
    """Pull plain text out of a chat-model response ``content`` payload.

    Anthropic returns a ``str``; Bedrock returns a list of content blocks
    (e.g. ``[{"type": "text", "text": "..."}]``). Mirrors the
    ``_extract_text`` helper used by the agent runtime so one-shot calls here
    decode model output identically.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _authenticate_token(token: str, db: Session) -> User | None:
    """Validate JWT token and return the user, or None if invalid.

    Mirrors :func:`app.core.dependencies.get_current_user` — including the
    revocation checks introduced for /api/auth/logout — so a token that has
    been revoked over HTTP can no longer be used to open or keep a WebSocket.

    Called from both the open-time auth gate and the per-message re-validation
    in ``websocket_chat``; the latter is what catches a /logout that revoked
    the token mid-session.

    Args:
        token: The JWT token string.
        db: The database session.

    Returns:
        The authenticated User or None.
    """
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None

    user_id: str | None = payload.get("sub")
    if user_id is None:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None

    # Per-token revocation (logout)
    jti = payload.get("jti")
    if jti and is_token_revoked(jti, db):
        return None

    # Blanket revocation on password change: reject any JWT whose ``iat``
    # second is strictly before the password-rotation second. Comparison is
    # done at whole-second resolution to match JWT ``iat`` precision — see
    # the matching logic + rationale in app.core.dependencies.
    pwd_changed_at = user.password_changed_at
    if pwd_changed_at is not None and pwd_changed_at.tzinfo is None:
        pwd_changed_at = pwd_changed_at.replace(tzinfo=timezone.utc)
    iat_raw = payload.get("iat")
    if pwd_changed_at is not None and iat_raw is not None:
        if isinstance(iat_raw, (int, float)):
            iat_seconds = int(iat_raw)
        elif isinstance(iat_raw, datetime):
            iat_dt = iat_raw if iat_raw.tzinfo else iat_raw.replace(tzinfo=timezone.utc)
            iat_seconds = int(iat_dt.timestamp())
        else:
            iat_seconds = None
        if iat_seconds is not None and iat_seconds < int(pwd_changed_at.timestamp()):
            return None

    return user


_WORKFLOW_TITLE_PIPELINE_HINTS: dict[str, str] = {
    "user_stories": "product requirements / user-stories backlog",
    "user_stories_revision": "revised user-stories backlog",
    "ppt": "executive presentation / slide deck",
    "ppt_revision": "revised executive presentation",
    "prototype": "interactive HTML prototype",
    "prototype_revision": "revised interactive prototype",
    "app_builder": "full-stack application build",
    "app_builder_revision": "revised application build",
    "custom": "custom AI workflow",
    "mulesoft_to_springboot": "Mulesoft → Spring Boot migration plan",
    "dotnet_to_azure": ".NET → Azure migration plan",
}


# Marker prefixes injected into the workflow input by the frontend when
# chaining pipelines (DashboardLayout.tsx::handleChainPipeline) — and by
# the orchestrator when sourcing context (orchestrator_v2.py). We strip
# any text from these markers onward before using the content as either
# a title placeholder or as the LLM-title-gen input. Otherwise the
# title shows raw "=== CONTEXT FROM PREVIOUS PIPELINE ..." cruft, or
# the LLM generates a title describing the previous pipeline's content
# rather than what the user actually asked for.
import re as _re  # noqa: E402

_WORKFLOW_TITLE_CONTEXT_MARKER = _re.compile(
    r"\n*\s*===\s*(?:CONTEXT FROM PREVIOUS|EXISTING|USER PREFERENCES|ORIGINAL USER REQUEST)"
)

# Extracts the revision instruction from revision messages that start with
# === EXISTING ... === blocks. The user's actual request is in the
# === REVISION REQUEST === section.
_REVISION_REQUEST_MARKER = _re.compile(
    r"===\s*REVISION REQUEST\s*===\s*\n(.*?)\n===\s*END REQUEST\s*===",
    _re.DOTALL,
)

# Extracts the "Title: ..." line from a chain context block when the content
# is ONLY a context block (no user-authored prefix). Used as a fallback title
# for wizard-based chained runs where finalBrief == contextBlock exclusively.
# The context block format (runs.py:503-508) always places "Title: {value}"
# on its second line: "=== CONTEXT FROM PREVIOUS PIPELINE (...) ===\nTitle: ...".
_CHAIN_CONTEXT_TITLE = _re.compile(
    r"===\s*CONTEXT FROM PREVIOUS PIPELINE[^=]*===\s*\nTitle:\s*(.+)",
)


def _extract_title_from_context(content: str) -> str:
    """Extract the Title: line from a chain context block.

    Used as a fallback when _strip_pipeline_context returns "" (i.e. the
    content is ONLY a context block with no user-authored prefix, as happens
    for wizard-based chained runs where prototype/ppt/templates/page.tsx sets
    finalBrief = contextBlock). Returns the extracted title (max 80 chars),
    or "" when the pattern is absent.
    """
    if not content:
        return ""
    m = _CHAIN_CONTEXT_TITLE.search(content)
    if not m:
        return ""
    return m.group(1).strip()[:80]


def _strip_pipeline_context(content: str) -> str:
    """Return the user-authored prefix of a workflow input.

    For revision messages that start with === EXISTING ... === blocks,
    extracts the === REVISION REQUEST === section instead, since there
    is no user-authored prefix before the existing content block.

    Splits on the first occurrence of any of the section markers used to
    inject upstream pipeline context, previous output, or system-side
    preferences. Returns the leading user prompt only, trimmed. Empty
    string in -> empty string out.
    """
    if not content:
        return ""
    # For revision messages: content starts with === EXISTING ... ===
    # Extract the revision instruction from === REVISION REQUEST === section
    stripped = _WORKFLOW_TITLE_CONTEXT_MARKER.split(content, maxsplit=1)[0].strip()
    if not stripped:
        # Content started with a context marker — look for revision request
        match = _REVISION_REQUEST_MARKER.search(content)
        if match:
            return match.group(1).strip()
        return ""
    return stripped


async def _generate_workflow_title(
    workflow_run_id: str,
    content: str,
    pipeline_type: str,
    websocket: WebSocket,
) -> None:
    """Generate a short, professional title for a WorkflowRun via Bedrock.

    Replaces the placeholder ``title = content[:60]`` the run record was
    created with. Runs as a background task (asyncio.create_task) so it
    does not delay the pipeline. Best-effort: any failure leaves the
    placeholder title in place and the pipeline continues unaffected.

    On success:
      * Updates ``workflow_runs.title`` in the database.
      * Emits a ``workflow_title_update`` WebSocket event the frontend
        handler at ``dashboard/page.tsx::workflow_title_update`` uses
        to swap the title in the recent-runs list in-place.

    The system prompt asks for 3-7 words, no quotes, no trailing
    punctuation — matching the chat-title generator's contract so both
    surfaces feel consistent.
    """
    # Strip injected pipeline-context markers BEFORE the LLM sees the
    # content. Otherwise on a chained run the LLM gets:
    #   "make me a fintech app === CONTEXT FROM PREVIOUS PIPELINE (...)"
    # and tends to write a title describing the *previous* pipeline's
    # output rather than the user's actual request. We want the title
    # to reflect what the user typed at the prompt.
    clean_content = _strip_pipeline_context(content)
    if not clean_content:
        # Content is ONLY a context block (wizard-based chained run). Extract
        # the Title: line from the context block as the title directly — no LLM
        # call needed; the title is already embedded in the chain context.
        context_title = _extract_title_from_context(content)
        if not context_title:
            return
        db = _get_db()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if wr is None:
                return
            wr.title = context_title[:60].strip()
            db.commit()
        finally:
            db.close()
        try:
            await websocket.send_json({
                "type": "workflow_title_update",
                "chunk": None,
                "section": None,
                "data": {"workflow_id": workflow_run_id, "title": context_title[:60].strip()},
            })
        except Exception:
            pass
        return
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.agents.model_factory import build_model

        hint = _WORKFLOW_TITLE_PIPELINE_HINTS.get(pipeline_type, "AI workflow")
        # Direct one-shot model call: title generation is a single-call
        # utility, not a pipeline agent (constitution §II).
        llm = build_model(max_tokens=64)
        resp = await llm.ainvoke([
            SystemMessage(content=(
                "Generate a short, professional title (3-7 words) for a "
                f"workflow that produces a {hint} based on the user's input. "
                "The title should describe the topic of the deliverable, "
                "not the workflow type itself. Return ONLY the title text "
                "— no quotes, no trailing punctuation, no explanation."
            )),
            HumanMessage(content=clean_content),
        ])
        generated_title = _extract_message_text(resp.content)
        generated_title = generated_title.strip().strip('"').strip("'").strip(".")[:80]
        if not generated_title:
            return

        db = _get_db()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if wr is None:
                return
            wr.title = generated_title
            db.commit()
        finally:
            db.close()

        # send_json may raise if the client disconnected between pipeline
        # start and title-generation completion — that's fine, the DB
        # update is what makes the title persist into the next /api/workflows
        # call.
        try:
            await websocket.send_json({
                "type": "workflow_title_update",
                "chunk": None,
                "section": None,
                "data": {"workflow_id": workflow_run_id, "title": generated_title},
            })
        except Exception:
            pass
    except Exception as e:
        logger.warning("Failed to generate workflow title for %s: %s", workflow_run_id, e)


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time AI chat streaming.

    Authentication (A5): the JWT is read from the ``Sec-WebSocket-Protocol``
    request header as the entry ``bearer.<jwt>``. Browsers can't set arbitrary
    headers on a WebSocket open, but they *can* declare subprotocols via the
    second arg to ``new WebSocket(url, protocols)`` — we piggyback the token
    there. This keeps the JWT off the URL, off nginx access logs, and off any
    ``Referer`` header the browser may send on subsequent navigations.

    Transitional path: a ``?token=<jwt>`` query parameter is still accepted for
    one release so any in-flight client tabs at deploy time keep working. It
    emits a deprecation warning in the backend log on every use; the frontend
    only sends the new path.

    On successful auth, the connection enters a message loop where:
    - Client sends JSON messages with type, content, and chat_session_id
    - Server routes to ChatRunner and streams responses back
    - Responses include phase_start, stream, phase_end, and complete messages

    Close codes:
    - 4001: JWT missing, invalid, expired, or revoked
    """
    # Extract token BEFORE accept() so we can pick the right subprotocol echo
    # — once you've called accept() you can't change the subprotocol the
    # handshake committed to.
    token: str | None = None
    auth_method: str | None = None  # for logging only

    # 1) Preferred: Sec-WebSocket-Protocol header (A5).
    proto_raw = websocket.headers.get("sec-websocket-protocol", "")
    proto_list = [p.strip() for p in proto_raw.split(",") if p.strip()]
    for p in proto_list:
        if p.startswith("bearer."):
            token = p[len("bearer."):]
            auth_method = "subprotocol"
            break

    # 2) Transitional: ?token= query parameter. Still works, but logged as
    # deprecated so we can spot stragglers before removing this branch.
    if token is None:
        token = websocket.query_params.get("token")
        if token:
            auth_method = "query_param"
            logger.warning(
                "WebSocket auth via query string ?token= is deprecated and will be removed. "
                "Switch the client to Sec-WebSocket-Protocol: bearer.<jwt>."
            )

    if not token:
        # Reject before accept() — browsers see this as a connect failure,
        # which is exactly what we want for a missing-credential case.
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    # When the client offered a subprotocol we MUST echo something back
    # (otherwise browsers reject the handshake response). RFC 6455 + browser
    # strict mode require the server to pick a value that was in the client's
    # offered list, so we cannot invent a placeholder. The frontend offers
    # ["bearer.<jwt>", "flowin.v1"]; we always echo the second (selector) one
    # and never the credential. If a client only offered the credential
    # (e.g. an older smoke client), we degrade by echoing the credential too —
    # not ideal for log hygiene, but the alternative is closing 4001.
    if auth_method == "subprotocol":
        echo_subprotocol = "flowin.v1" if "flowin.v1" in proto_list else f"bearer.{token}"
        await websocket.accept(subprotocol=echo_subprotocol)
    else:
        await websocket.accept()
    logger.debug("[WS] Connection accepted via %s, validating token...", auth_method)

    # Validate JWT and get user
    db = _get_db()
    try:
        user = _authenticate_token(token, db)
        if user is None:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Authentication error")
        return
    finally:
        db.close()

    logger.info(f"WebSocket connected: user={user.id}")
    logger.debug("[WS] Authenticated user=%s, entering message loop", user.id)

    # Track the in-flight pipeline (if any) for this connection. Pipelines run
    # as background tasks so the receive loop stays responsive — that's what
    # makes cancel_pipeline actually able to interrupt a running pipeline
    # (blocker A3) and lets WebSocketDisconnect propagate cancellation to the
    # task. A single connection can run at most one pipeline at a time.
    current_pipeline_task: asyncio.Task | None = None
    # ISS-007 (16-02): the run_id of the in-flight pipeline for THIS connection,
    # published BACK by the handler (which mints the id internally) via the
    # single-element ``run_id_sink`` below. ``cancel_pipeline`` resolves this run's
    # cooperative ``_CANCEL_EVENTS`` entry from it. Connection-scoped — a cancel
    # can only ever reach the run THIS authenticated connection started
    # (T-16-02-TENANT: no cross-connection / client-supplied-run-id lookup).
    _run_id_sink: list[str] = []

    # Message loop
    try:
        while True:
            # Receive message from client
            raw_message = await websocket.receive_text()

            try:
                message_data = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "chunk": None,
                    "section": None,
                    "data": {"error": "Invalid JSON message"},
                })
                continue

            # Validate message structure
            msg_type = message_data.get("type")
            content = message_data.get("content")
            chat_session_id = message_data.get("chat_session_id")
            mode = message_data.get("mode", "default")

            # Handle pipeline execution requests
            if msg_type == "run_pipeline":
                logger.debug(
                    "[WS] Received run_pipeline: type=%s",
                    message_data.get("pipeline_type"),
                )
                # Reject overlapping runs — the UI should never send a second
                # run_pipeline while one is in flight, but a misbehaving client
                # or a double-click race would otherwise spawn parallel
                # WorkflowRuns and stream interleaved events.
                if current_pipeline_task is not None and not current_pipeline_task.done():
                    await websocket.send_json({
                        "type": "error",
                        "chunk": None,
                        "section": None,
                        "data": {
                            "error": "Pipeline already running. Cancel the current one first.",
                            "code": "pipeline_already_running",
                            "recoverable": True,
                        },
                    })
                    continue
                pipeline_type = message_data.get("pipeline_type", "user_stories")
                pipeline_content = message_data.get("message") or message_data.get("content") or ""
                agent_ids = message_data.get("agent_ids")  # Optional custom agent list
                attached_skills = message_data.get("attached_skills") or []  # UI-selected skills
                attached_hooks = message_data.get("attached_hooks") or []    # UI-selected hooks
                # Optional per-run Human-gate selection (Phase 6 UI sends this).
                # Absent / None → engine falls back to today's static gate set,
                # so existing clients are unaffected. A list of agent IDs = gate
                # exactly those agents this run. We pass it through verbatim
                # (None when absent) and let the engine apply the semantics.
                gate_agent_ids = message_data.get("gate_agent_ids")
                # Optional per-agent model override map (Phase 6 D-07, MODEL-03).
                # Untrusted run-payload input — allow-list-validated at ingress
                # (against the catalog AND this run's agents) inside
                # _handle_workflow_execution, once the agent set is resolved.
                # Absent → {} (the frontend doesn't send it until Phase 8).
                model_overrides = message_data.get("model_overrides") or {}
                # EMP-01/02 (22-04): the per-step capability-selections map a saved
                # workflow launch replays (the FE composer sends it, mirroring
                # agent_ids/model_overrides — pure data, SC-001). Re-validated with
                # trust="user" at launch (a tampered/smuggled cap is rejected here,
                # not only at save — Pitfall 3). Absent → None (every existing run is
                # byte-identical — no overlay, no re-compile).
                selections = message_data.get("selections") or None

                # Tier gate — map od_* aliases to their base type for the check
                from app.core.entitlements import can_run_pipeline
                _tier_check_type = {
                    "od_prototype": "prototype",
                    "od_ppt": "ppt",
                }.get(pipeline_type, pipeline_type)
                allowed, reason = can_run_pipeline(user.tier, _tier_check_type)
                if not allowed:
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": reason, "code": "tier_limit",
                                 "recoverable": False, "upgrade_required": True},
                    })
                    continue

                # ── Unified routing — every pipeline goes through the
                #    Universal Execution_Engine (Phase 2, T020). ───────────
                # Reset the per-connection run_id sink — the handler republishes
                # this run's id into it once minted, so cancel_pipeline resolves
                # the right cooperative event (ISS-007).
                _run_id_sink.clear()
                current_pipeline_task = asyncio.create_task(
                    _handle_workflow_execution(
                        websocket, pipeline_content, pipeline_type,
                        chat_session_id, token, user, agent_ids=agent_ids,
                        attached_skills=attached_skills,
                        attached_hooks=attached_hooks,
                        gate_agent_ids=gate_agent_ids,
                        model_overrides=model_overrides,
                        selections=selections,
                        template_id=message_data.get("template_id"),
                        design_system_id=message_data.get("design_system_id"),
                        discovery=message_data.get("discovery"),
                        custom_ds_body=message_data.get("custom_design_system_body") or None,
                        custom_template_body=message_data.get("custom_template_body") or None,
                        source_workflow_run_id=message_data.get("source_workflow_run_id") or None,
                        run_id_sink=_run_id_sink,
                    )
                )
                continue

            # Handle pipeline cancellation
            if msg_type == "cancel_pipeline":
                logger.info(f"Pipeline cancellation requested by user={user.id}")
                _cancel_run_id = _run_id_sink[0] if _run_id_sink else None
                _cancel_event = (
                    _CANCEL_EVENTS.get(_cancel_run_id) if _cancel_run_id else None
                )
                if (
                    current_pipeline_task is not None
                    and not current_pipeline_task.done()
                    and _cancel_event is not None
                ):
                    # ISS-007 (16-02): COOPERATIVE cancel. Set the per-run
                    # cancel_event instead of destructively cancelling the
                    # drainer task (the old `current_pipeline_task.cancel()`,
                    # which killed the drainer in its `except CancelledError`
                    # BEFORE the bg task's `pipeline_cancelled` frame could be
                    # drained → the live wire got no terminal, the FE card
                    # stayed RUNNING). The bg task keeps running; the engine
                    # observes the event (per-chunk / pre-agent), emits
                    # `pipeline_cancelled` through the normal persisted+drained
                    # path; the still-alive drainer forwards it to the WS and
                    # breaks on the terminal. We deliberately do NOT send a sync
                    # ack here — that would race the bg task's own ack + the
                    # WorkflowRun "cancelled" write (the cooperative event is
                    # precisely what removes that race).
                    _cancel_event.set()
                elif current_pipeline_task is not None and not current_pipeline_task.done():
                    # Defensive: a live task with no resolvable cooperative event
                    # (e.g. the run_id sink not yet populated). Fall back to the
                    # destructive cancel so a Stop still terminates the run; the
                    # durable replay covers the (rare) missed live ack.
                    current_pipeline_task.cancel()
                else:
                    # Idempotent: nothing to cancel, but the client expects an
                    # ack so its UI state machine can return to idle.
                    await websocket.send_json({
                        "type": "pipeline_cancelled",
                        "chunk": None,
                        "section": None,
                        "data": {"message": "No active pipeline"},
                    })
                continue

            # Handle reconnect restoration — client reconnects while a pipeline
            # is still running. Attaches to the running pipeline's event queue
            # so the client resumes receiving events seamlessly without losing
            # any pipeline output.
            if msg_type == "reconnect_pipeline":
                _reconnect_run_id = message_data.get("pipeline_run_id")
                if _reconnect_run_id:
                    running_task = _PIPELINE_TASKS.get(_reconnect_run_id)
                    running_queue = _PIPELINE_QUEUES.get(_reconnect_run_id)
                    _has_live_task = bool(
                        running_task
                        and not running_task.done()
                        and running_queue is not None
                    )

                    # ── AUTHZ-03 owner gate for the LIVE attach (CR-01) ──────────────
                    # The durable replay below is owner-scoped (RunEvent.owner_id ==
                    # user.id / ScopedStore default-deny), but the live-attach drainer
                    # streamed every event for ANY authenticated user presenting the
                    # run_id. The 12-09 bridge widened the exposure: auto-resumed runs
                    # — whose owner is by definition not connected (backend restarted)
                    # — now sit in _PIPELINE_TASKS/_PIPELINE_QUEUES for the whole
                    # resumed drive. Gate the live attach the same way the replay is
                    # gated: recover the run's workspace from the workflow_runs row
                    # FILTERED BY the authenticated principal (never from the client
                    # payload — the T-12-05-TENANT precedent), then resolve the run
                    # through the default-deny ScopedStore. A miss demotes to the
                    # no-live-task path, so a run this principal does not own behaves
                    # exactly like a finished/unknown run (∅ replay + live:false,
                    # never the stream).
                    # WR-03 (14 review fix): revision runs pin section = the
                    # TARGET artifact type on EVERY frame (the
                    # test_run_revision_ws_dispatch contract) — a reconnect
                    # mid-revision must not switch the stream to section: None
                    # or the FE revision panel mis-routes the remainder.
                    # Derived below from the owner-filtered run row's type via
                    # the INVERSE of the WR-06 alias transform (generic suffix
                    # transform — no workflow-name literal); non-revision runs
                    # keep the legacy section: None byte-identically.
                    _reattach_section = None
                    if _has_live_task:
                        from agents.authz import ScopedStore as _GateStore
                        from app.models.workflow import WorkflowRun as _GateRun

                        _gate_db = _get_db()
                        try:
                            _gate_row = (
                                _gate_db.query(_GateRun)
                                .filter(
                                    _GateRun.id == _reconnect_run_id,
                                    _GateRun.owner_id == user.id,
                                )
                                .first()
                            )
                            _gate_ws = getattr(_gate_row, "workspace_id", None)
                            _gate_run_type = getattr(_gate_row, "type", None) or ""
                            if _gate_run_type.endswith("_revision"):
                                _reattach_section = (
                                    f"{_gate_run_type.removesuffix('_revision')}_output"
                                )
                        finally:
                            _gate_db.close()
                        _own_store = _GateStore(
                            owner_id=user.id, workspace_id=_gate_ws
                        )
                        if await _own_store.get_run(_reconnect_run_id) is None:
                            _has_live_task = False

                    # ── Durable run_events tail replay (RESUME-03 / API-05) ──────────
                    # The reconnecting client may supply ``after_seq`` (the highest
                    # ``seq`` it has already rendered). When ``after_seq`` is provided
                    # OR there is NO live task (the process was restarted and the
                    # in-memory queue/task are gone), FIRST replay the durable tail
                    # from the persisted ``run_events`` log (``seq > after_seq``) BEFORE
                    # attaching to the live queue, so a reconnect after a crash/restart
                    # still receives every missed event. The replay is OWNER-SCOPED via
                    # the default-deny ``ScopedStore`` (constructed with the reconnecting
                    # user's id): a cross-owner reconnect resolves to ∅ (T-12-03-IDOR).
                    # The FE dedupes by ``event_id`` (12-04), so a replayed event that
                    # the live attach also delivers is idempotent client-side.
                    #
                    # ``after_seq`` defaults to 0 when ABSENT — so a legacy reconnect
                    # (no ``after_seq``) WITH a live task replays nothing new only when
                    # there are no persisted rows; but to keep the legacy live-attach
                    # path byte-identical (the 5 snapshots + existing reconnect
                    # behavior), the replay branch is entered ONLY when the client
                    # explicitly sent ``after_seq`` OR there is no live task. A pure
                    # legacy reconnect (no ``after_seq`` + live task) skips replay
                    # entirely and runs the unchanged live-attach drainer below.
                    _after_seq_raw = message_data.get("after_seq")
                    _did_replay = False
                    if _after_seq_raw is not None or not _has_live_task:
                        # Int-coerce ``after_seq`` (the ``runs.py after:int`` precedent —
                        # a non-int is rejected, never reaching the scoped read / raw SQL).
                        try:
                            _after_seq = int(_after_seq_raw) if _after_seq_raw is not None else 0
                        except (TypeError, ValueError):
                            await websocket.send_json({
                                "type": "error", "chunk": None, "section": None,
                                "data": {"error": "after_seq must be an integer",
                                         "code": "invalid_after_seq", "recoverable": True},
                            })
                            continue
                        from agents.authz import ScopedStore

                        # ── Recover the run's workspace_id BEFORE the replay read (CR-02 /
                        # T-12-05-TENANT) ────────────────────────────────────────────────
                        # The engine sink stamps every run_events row with the run's REAL
                        # non-null workspace_id. A ScopedStore with workspace_id=None scopes
                        # the read to ``workspace_id IS NULL`` and matches ZERO production
                        # rows. Recover the workspace from a RunEvent row ALREADY FILTERED
                        # BY ``owner_id == user.id`` (never from the client payload — a row
                        # that is not the authenticated user's never feeds the workspace_id,
                        # so the recovered value can never become a cross-tenant read
                        # primitive; a non-owner run → no row → None → ∅ replay, identical
                        # to the cross-owner IDOR ∅). Then construct the replay store with
                        # BOTH the owner_id AND the recovered workspace_id so the read keeps
                        # the full owner+workspace default-deny scoping.
                        from app.models.run_event import RunEvent
                        from app.models.workflow import WorkflowRun as _ReplayRun

                        # ISS-008 (16-03): derive the replay `section` ONCE before the
                        # replay loop, the SAME way the live-attach drainer computes
                        # `_reattach_section` (:698-718). `section` is a WS-frame-wrapper
                        # field, NEVER persisted (RunEvent has no `section` column) — so a
                        # revision run replayed on reconnect must re-derive it from the
                        # OWNER-SCOPED run row's `type` via the INVERSE of the WR-06 alias
                        # transform (generic `removesuffix('_revision')` + `_output`; NO
                        # workflow-name literal — SC-001). A non-revision run → None →
                        # byte-identical to today and to the live-attach contract.
                        # T-16-03-TENANT: the run-row read is filtered by
                        # `owner_id == user.id` in the SAME owner-scoped session that
                        # recovers the workspace — a cross-owner reconnect resolves ∅ →
                        # `_replay_section` stays None and leaks no section for a run the
                        # principal does not own (no new/unscoped DB session).
                        _replay_section = None
                        _ws_db = _get_db()
                        try:
                            _run_evt_row = (
                                _ws_db.query(RunEvent)
                                .filter(
                                    RunEvent.run_id == _reconnect_run_id,
                                    RunEvent.owner_id == user.id,
                                )
                                .first()
                            )
                            _recovered_ws = getattr(_run_evt_row, "workspace_id", None)
                            _replay_run_row = (
                                _ws_db.query(_ReplayRun)
                                .filter(
                                    _ReplayRun.id == _reconnect_run_id,
                                    _ReplayRun.owner_id == user.id,
                                )
                                .first()
                            )
                            _replay_run_type = getattr(_replay_run_row, "type", None) or ""
                            if _replay_run_type.endswith("_revision"):
                                _replay_section = (
                                    f"{_replay_run_type.removesuffix('_revision')}_output"
                                )
                        finally:
                            _ws_db.close()
                        _replay_store = ScopedStore(
                            owner_id=user.id, workspace_id=_recovered_ws
                        )
                        try:
                            _missed = await _replay_store.read_events(
                                _reconnect_run_id, after_seq=_after_seq
                            )
                        except Exception as _replay_exc:  # noqa: BLE001
                            logger.warning(
                                "reconnect replay read failed for %s: %s",
                                _reconnect_run_id, _replay_exc,
                            )
                            _missed = []
                        for _r in _missed:
                            try:
                                await websocket.send_json({
                                    "type": _r.type, "chunk": None,
                                    "section": _replay_section, "data": _r.payload_json,
                                })
                            except Exception:
                                break
                        _did_replay = True
                        # When there is NO live task (restarted), the replayed tail plus
                        # the run's CURRENT status is the complete response — report the
                        # status so the client is not left silently hanging.
                        if not _has_live_task:
                            _run_row = await _replay_store.get_run(_reconnect_run_id)
                            await websocket.send_json({
                                "type": "pipeline_reconnected", "chunk": None, "section": None,
                                "data": {
                                    "pipeline_run_id": _reconnect_run_id,
                                    "status": getattr(_run_row, "status", None),
                                    "replayed_through_seq": _after_seq,
                                    "live": False,
                                    "message": "Replayed durable run_events tail (no live task)",
                                },
                            })

                    if _has_live_task:
                        # Pipeline is still running — attach a new drainer
                        logger.info("Client reconnected to running pipeline run=%s", _reconnect_run_id)
                        try:
                            await websocket.send_json({
                                "type": "pipeline_reconnected", "chunk": None, "section": None,
                                "data": {"pipeline_run_id": _reconnect_run_id,
                                         # ISS-009 (16-03): the live-attach ack is now
                                         # symmetric + self-describing — `live: True`,
                                         # mirroring the no-live-task ack's `live: False`
                                         # (:825). The FE keeps its tolerant
                                         # `live !== false` guard (useWorkflow.ts:455).
                                         "live": True,
                                         "message": "Reconnected — resuming pipeline stream"},
                            })
                        except Exception:
                            pass
                        try:
                            while True:
                                try:
                                    # ISS-007 (16-02): asyncio.timeout() is the
                                    # correct CPython-3.11 primitive — unlike
                                    # asyncio.wait_for() it does not swallow a
                                    # result-vs-cancel race at the await boundary
                                    # (defense-in-depth for cooperative cancel).
                                    async with asyncio.timeout(10.0):
                                        event = await running_queue.get()
                                except asyncio.TimeoutError:
                                    try:
                                        await websocket.send_json({
                                            "type": "pipeline_heartbeat", "chunk": None,
                                            "section": _reattach_section,
                                            "data": {"pipeline_run_id": _reconnect_run_id,
                                                     "timestamp": datetime.now(timezone.utc).isoformat()},
                                        })
                                    except Exception:
                                        break
                                    continue
                                if event is None:
                                    break
                                try:
                                    # WR-03: _reattach_section preserves the
                                    # revision frame contract (section = TARGET
                                    # artifact type); None for non-revision runs.
                                    await websocket.send_json({
                                        "type": event["type"], "chunk": None,
                                        "section": _reattach_section,
                                        "data": event.get("data", {}),
                                    })
                                except Exception:
                                    await running_queue.put(event)
                                    break
                                # IN-02 (13 review fix): pipeline_failed (F3 total
                                # collapse) and budget_aborted are terminals too —
                                # break immediately instead of idling until the bg
                                # task's None sentinel (post-DB-persist latency).
                                if event["type"] in (
                                    "pipeline_complete", "pipeline_cancelled",
                                    "error", "pipeline_failed", "budget_aborted",
                                ):
                                    break
                        except Exception:
                            pass
                    else:
                        # No running pipeline — check if paused at clarify gate
                        from agents.authz import ScopedStore as _ScopedStore
                        from agents.execution_engine.state_machine import get_state_machine as _get_sm
                        _sm = _get_sm()
                        _state = _sm.get_state(_reconnect_run_id)
                        if _state == "waiting_for_user":
                            # T-5-IDOR mitigation (05-06): the clarifications PAYLOAD now
                            # lives in artifact_refs (kind=clarifications, written by
                            # clarify_engine), read back through the default-deny
                            # ScopedStore. The reconnecting user's principal owner-scopes
                            # the read: a run the user does NOT own resolves to an empty
                            # list, so the clarifications are never read (no cross-session
                            # disclosure of another user's questionnaire). The literal
                            # thin-store retrieve_latest is gone.
                            _scoped = _ScopedStore(owner_id=user.id)
                            _clar_kind = "clarifications"
                            _clar_refs = await _scoped.list_refs(
                                _reconnect_run_id, kind=_clar_kind
                            )
                            _clarifications = _clar_refs[-1] if _clar_refs else None
                            if _clarifications:
                                try:
                                    import json as _json
                                    _qa_pairs = _json.loads(_clarifications.content)
                                    _unanswered = [
                                        {"question_id": q["question_id"], "question_text": q["question_text"],
                                         "impact_level": q.get("impact_level", "medium"), "answer_type": "free_text",
                                         "options": None, "recommended_answer": ""}
                                        for q in _qa_pairs if not q.get("answer")
                                    ]
                                    if _unanswered:
                                        await websocket.send_json({
                                            "type": "questionnaire_ready", "chunk": None, "section": None,
                                            "data": {"pipeline_run_id": _reconnect_run_id, "questions": _unanswered,
                                                     "round": _qa_pairs[0].get("round", 1) if _qa_pairs else 1,
                                                     "timestamp": datetime.now(timezone.utc).isoformat()},
                                        })
                                except Exception as _exc:
                                    logger.warning("Reconnect restoration failed for %s: %s", _reconnect_run_id, _exc)
                continue

            # Handle revision requests (Phase 3 / T054, FR-014).
            # Ingress validation stays inline (byte-identical error frames);
            # everything else (WorkflowRun row, engine dispatch, terminal
            # status) lives in _handle_revision_execution, dispatched as a
            # background task so the receive loop stays responsive — that is
            # what lets cancel_pipeline / pings / reconnects be processed
            # while a multi-minute revision runs (Phase 14, RESEARCH Pitfall 3).
            if msg_type == "run_revision":
                # CR-01 (14 review fix): reject overlapping runs BEFORE anything
                # else — identical to the run_pipeline guard above, because the
                # connection-level invariant ("a single connection can run at
                # most one pipeline at a time") covers revisions too. Without
                # this, a second run_revision (double-click race / misbehaving
                # client) would overwrite current_pipeline_task — the ONLY
                # handle cancel_pipeline uses — leaving the in-flight run
                # uncancellable from its own connection while both drainers
                # interleave send_json on the same WS; a frame loop could
                # accumulate unbounded concurrent revision tasks.
                if current_pipeline_task is not None and not current_pipeline_task.done():
                    await websocket.send_json({
                        "type": "error",
                        "chunk": None,
                        "section": None,
                        "data": {
                            "error": "Pipeline already running. Cancel the current one first.",
                            "code": "pipeline_already_running",
                            "recoverable": True,
                        },
                    })
                    continue
                _rev_parent_run_id = message_data.get("parent_run_id")
                _rev_target_type = message_data.get("target_artifact_type")
                _rev_instruction = message_data.get("instruction", "").strip()

                # Pre-creation validation (FR-014)
                if not _rev_instruction:
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "run_revision requires a non-empty instruction",
                                 "code": "empty_revision_instruction", "recoverable": True},
                    })
                    continue
                if not _rev_parent_run_id or not _rev_target_type:
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "run_revision requires parent_run_id and target_artifact_type",
                                 "code": "missing_revision_params", "recoverable": True},
                    })
                    continue

                # Mirror the run_pipeline dispatch: assigning the task to
                # current_pipeline_task is what makes the cancel_pipeline
                # handler able to cancel a running revision. The run_id sink is
                # republished by the handler so cancel_pipeline resolves the
                # cooperative cancel_event for this revision run (ISS-007).
                _run_id_sink.clear()
                current_pipeline_task = asyncio.create_task(
                    _handle_revision_execution(
                        websocket, user, _rev_parent_run_id,
                        _rev_target_type, _rev_instruction,
                        run_id_sink=_run_id_sink,
                    )
                )
                continue

            # Handle questionnaire answer submission (Phase 2 — replaces the
            # retired `generate_questions` request/response flow). The Clarify_Engine
            # (running inside the ExecutionEngine) is paused on an asyncio.Event
            # keyed by pipeline_run_id; submitting answers sets that event and
            # resumes the paused pipeline from the gate.
            if msg_type == "submit_questionnaire":
                from agents.artifact_store.store import get_artifact_store
                pipeline_run_id = message_data.get("pipeline_run_id")
                responses = message_data.get("responses") or []
                # ISS-027: "Skip all & run directly" sends skip_clarification=True
                # so the ClarifyEngine force-proceeds instead of re-asking the same
                # questions for the remaining rounds. Absent/false for ordinary
                # answer submissions.
                skip_clarification = bool(message_data.get("skip_clarification", False))
                if not pipeline_run_id:
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "submit_questionnaire requires pipeline_run_id",
                                 "code": "missing_pipeline_run_id", "recoverable": True},
                    })
                    continue
                store = get_artifact_store()
                await store.set_questionnaire_responses(
                    pipeline_run_id, responses, skip_clarification=skip_clarification
                )
                continue

            # Handle review gate approval/rejection.
            # The user has reviewed an agent's output and either approved it
            # (optionally with edits) or rejected it (cancels the pipeline).
            if msg_type == "approve_review":
                from agents.artifact_store.store import get_artifact_store
                gate_key = message_data.get("gate_key")
                approved = message_data.get("approved", True)
                edited_content = message_data.get("edited_content")  # None = no edits
                if not gate_key:
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "approve_review requires gate_key",
                                 "code": "missing_gate_key", "recoverable": True},
                    })
                    continue
                # Only the run's owner may resolve its review gate (13-REVIEW
                # CR-01 / T-13-01-01) — this handler is the live boundary for
                # HITL approval, including the N3 exec sign-off gate. Deny
                # without revealing whether the run exists.
                if not _review_gate_owned_by(gate_key, user.id):
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "Unknown gate_key",
                                 "code": "invalid_gate_key", "recoverable": True},
                    })
                    continue
                store = get_artifact_store()
                await store.set_review_response(gate_key, approved=approved, edited_content=edited_content)
                continue

            if msg_type == "ping":
                # Client keepalive ping — respond with pong to confirm connection is alive
                try:
                    await websocket.send_json({"type": "pong", "chunk": None, "section": None, "data": {}})
                except Exception:
                    pass
                continue

            if msg_type != "user_message" or not content or not chat_session_id:
                await websocket.send_json({
                    "type": "error",
                    "chunk": None,
                    "section": None,
                    "data": {"error": "Invalid message format. Expected {type: 'user_message', content: string, chat_session_id: string}"},
                })
                continue

            # Re-validate JWT before processing (check for expiry during session)
            db = _get_db()
            try:
                user = _authenticate_token(token, db)
                if user is None:
                    await websocket.close(code=4001, reason="Token expired")
                    return

                # Verify chat session belongs to user
                chat_session = (
                    db.query(ChatSession)
                    .filter(
                        ChatSession.id == chat_session_id,
                        ChatSession.user_id == user.id,
                    )
                    .first()
                )

                if chat_session is None:
                    await websocket.send_json({
                        "type": "error",
                        "chunk": None,
                        "section": None,
                        "data": {"error": "Chat session not found"},
                    })
                    continue

                # Persist user message
                user_msg = Message(
                    chat_session_id=chat_session_id,
                    role="user",
                    content=content,
                )
                db.add(user_msg)
                chat_session.last_activity = datetime.now(timezone.utc)

                # Check if this chat needs a title (first message or default title)
                needs_title = chat_session.title in ("New Chat", "") or chat_session.title == content[:50]
                db.commit()
            finally:
                db.close()

            # Auto-generate chat title from first message (like ChatGPT)
            if needs_title:
                try:
                    from langchain_core.messages import HumanMessage, SystemMessage

                    from app.agents.model_factory import build_model
                    # Direct one-shot model call: chat-title generation is a
                    # single-call utility, not a pipeline agent (constitution
                    # §II).
                    llm = build_model(max_tokens=64)
                    resp = await llm.ainvoke([
                        SystemMessage(content=(
                            "Generate a very short title (3-5 words max) for a chat conversation "
                            "based on the user's first message. Return ONLY the title text, nothing else. "
                            "No quotes, no punctuation at the end, no explanation. Just the title."
                        )),
                        HumanMessage(content=content),
                    ])
                    generated_title = _extract_message_text(resp.content)
                    # Clean up the title
                    generated_title = generated_title.strip().strip('"').strip("'").strip(".")[:60]
                    if generated_title:
                        db2 = _get_db()
                        try:
                            cs = db2.query(ChatSession).filter(ChatSession.id == chat_session_id).first()
                            if cs:
                                cs.title = generated_title
                                db2.commit()
                        finally:
                            db2.close()
                        # Notify frontend of the title update
                        await websocket.send_json({
                            "type": "title_update",
                            "chunk": None,
                            "section": None,
                            "data": {"chat_session_id": chat_session_id, "title": generated_title},
                        })
                except Exception as e:
                    logger.warning(f"Failed to generate chat title: {e}")

            # Route to Agent Orchestrator and stream responses
            assistant_chunks: list[str] = []
            collected_steps: list[dict] = []
            stream_msg: dict | None = None

            # Get mode-specific system prompt enhancement
            mode_prompt = get_mode_prompt(mode)

            try:
                # Chat agents are text-only (no sandbox/tools); run_id is
                # incidental but we pass chat_session_id for traceability.
                runner = ChatRunner(user_id=user.id, run_id=chat_session_id)
                async for stream_msg in runner.astream_execute(
                    user_message=content,
                    chat_session_id=chat_session_id,
                    mode=mode,
                    mode_prompt=mode_prompt,
                ):
                    if stream_msg.get("type") == "stream" and stream_msg.get("chunk"):
                        assistant_chunks.append(stream_msg["chunk"])
                    await websocket.send_json(stream_msg)

            except ModelConfigurationError:
                # Provider-config gap (Bedrock model id / region not set).
                # Always non-recoverable.
                logger.error("Agent configuration error during chat stream")
                await websocket.send_json({
                    "type": "error", "chunk": None, "section": None,
                    "data": {
                        "error": "AI service is not configured. Please contact the administrator.",
                        "code": "api_key_missing",
                        "recoverable": False,
                    },
                })
            except Exception as exc:
                # Maps botocore (Bedrock) exceptions to the
                # {error, code, recoverable} triple the frontend expects.
                # Falls back to a generic recoverable internal_error otherwise.
                payload = _map_llm_exception(exc)
                logger.error(
                    "LLM call failed: code=%s recoverable=%s exc=%s",
                    payload.code, payload.recoverable, exc,
                )
                await websocket.send_json({
                    "type": "error", "chunk": None, "section": None,
                    "data": {
                        "error": payload.message,
                        "code": payload.code,
                        "recoverable": payload.recoverable,
                    },
                })

            # Persist assistant response and final output
            db = _get_db()
            try:
                assistant_content = "".join(assistant_chunks)

                if assistant_content:
                    # Embed steps as a hidden marker at the start of content
                    persisted_content = assistant_content
                    if collected_steps:
                        steps_json = json.dumps(collected_steps)
                        persisted_content = f"<!--steps:{steps_json}-->{assistant_content}"
                    assistant_msg = Message(
                        chat_session_id=chat_session_id,
                        role="assistant",
                        content=persisted_content,
                    )
                    db.add(assistant_msg)

                # Update chat session last_activity and store final_output if complete
                chat_session = (
                    db.query(ChatSession)
                    .filter(ChatSession.id == chat_session_id)
                    .first()
                )
                if chat_session:
                    chat_session.last_activity = datetime.now(timezone.utc)
                    # Store final output if the last stream message was 'complete'
                    if stream_msg and stream_msg.get("type") == "complete" and stream_msg.get("data"):
                        chat_session.final_output = json.dumps(stream_msg["data"])
                    db.commit()
            finally:
                db.close()

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={user.id}")
        # Stop burning Bedrock tokens for a connection that's already gone.
        # Without this, the pipeline task keeps streaming into a dead WS.
        if current_pipeline_task is not None and not current_pipeline_task.done():
            current_pipeline_task.cancel()
            try:
                await current_pipeline_task
            except (asyncio.CancelledError, Exception):
                # The task's CancelledError handler will have marked the
                # WorkflowRun "cancelled" already; any send_json there will
                # have failed silently because the WS is closed. That's fine.
                pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if current_pipeline_task is not None and not current_pipeline_task.done():
            current_pipeline_task.cancel()
            try:
                await current_pipeline_task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
async def _handle_workflow_execution(
    websocket: WebSocket,
    content: str,
    pipeline_type: str,
    chat_session_id: str | None,
    token: str,
    user: User,
    agent_ids: list[str] | None = None,
    attached_skills: list[dict] | None = None,
    attached_hooks: list[dict] | None = None,
    gate_agent_ids: list[str] | None = None,
    model_overrides: dict | None = None,
    selections: dict | None = None,
    template_id: str | None = None,
    design_system_id: str | None = None,
    discovery: dict | None = None,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
    source_workflow_run_id: str | None = None,
    run_id_sink: list | None = None,
) -> None:
    """Unified pipeline handler — routes every pipeline through the Universal
    Execution_Engine (Phase 2, T020).

    Replaces _handle_pipeline_execution, _handle_od_prototype_execution, and
    _handle_od_ppt_execution. Preserves all DB persistence, tier gating,
    validation, cancellation, and async title generation.

    For od_prototype / od_ppt pipelines, loads od_context (template skill,
    design system, craft rules) and threads it to the engine, which delegates
    injection composition to factory.py via the `injects` field.
    """
    import uuid as _uuid

    from agents.execution_engine.engine import get_execution_engine
    from agents.execution_engine.od_context import (
        load_prototype_od_context,
        load_ppt_od_context,
    )
    from agents.loader import SUPPORTED_PIPELINE_TYPES, load_agent_spec
    from agents.registry import get_pipeline_agents

    logger.info(
        "Workflow execution: type=%s user=%s custom_agents=%s",
        pipeline_type, user.id, len(agent_ids) if agent_ids else "default",
    )

    # ── Resolve od_prototype/od_ppt to their base pipeline + load od_context ──
    od_context: dict | None = None
    base_pipeline_type = pipeline_type
    if pipeline_type == "od_prototype":
        base_pipeline_type = "prototype"
        try:
            od_context = load_prototype_od_context(
                template_id or "", design_system_id or "",
                custom_ds_body=custom_ds_body, custom_template_body=custom_template_body,
            )
        except LookupError as exc:
            await websocket.send_json({
                "type": "error", "chunk": None, "section": None,
                "data": {"error": str(exc), "code": "template_not_found", "recoverable": False},
            })
            return
    elif pipeline_type == "od_ppt":
        base_pipeline_type = "od_ppt"
        try:
            od_context = load_ppt_od_context(
                template_id or "", design_system_id,
                custom_ds_body=custom_ds_body, custom_template_body=custom_template_body,
            )
        except LookupError as exc:
            await websocket.send_json({
                "type": "error", "chunk": None, "section": None,
                "data": {"error": str(exc), "code": "template_not_found", "recoverable": False},
            })
            return
    elif pipeline_type == "od_ppt_revision":
        # Revision of an od_ppt run — load od_context so template/DS context
        # is available to the revision agent (T056 / FR-014).
        base_pipeline_type = "od_ppt_revision"
        if template_id:
            try:
                od_context = load_ppt_od_context(
                    template_id, design_system_id,
                    custom_ds_body=custom_ds_body, custom_template_body=custom_template_body,
                )
            except LookupError:
                # Non-fatal for revisions — proceed without od_context
                pass

    # ── Validate pipeline type ────────────────────────────────────────────
    if base_pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": f"Unsupported pipeline_type: {pipeline_type!r}",
                     "code": "invalid_pipeline_type", "recoverable": False},
        })
        return

    # ── Resolve agents ────────────────────────────────────────────────────
    if agent_ids:
        from agents.registry import allowed_custom_agent_ids
        allowed_ids = allowed_custom_agent_ids(base_pipeline_type)
        rejected = [aid for aid in agent_ids if aid not in allowed_ids]
        if rejected:
            await websocket.send_json({
                "type": "error", "chunk": None, "section": None,
                "data": {"error": f"Invalid agent_ids for {pipeline_type!r}: {rejected}",
                         "code": "invalid_agent_ids", "recoverable": False,
                         "rejected_agent_ids": rejected},
            })
            return
        agents = [load_agent_spec(aid) for aid in agent_ids]
    else:
        agents = get_pipeline_agents(base_pipeline_type)
        # od_ppt/ppt share agents — the scan returns od_ppt agents for both.
        if not agents and base_pipeline_type == "ppt":
            from agents.registry import PIPELINE_AGENTS
            agents = [load_agent_spec(aid) for aid in PIPELINE_AGENTS.get("ppt", [])]

    if not agents:
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": f"No agents found for pipeline_type {pipeline_type!r}",
                     "code": "no_agents", "recoverable": False},
        })
        return

    # ── F3 (13-06): template-inject ingress guard ─────────────────────────
    # A pipeline whose resolved agents declare `injects: [template, ...]` is
    # unsatisfiable without a loadable template body: the factory's
    # _compose_injection raises TemplateMissingError for EVERY such agent
    # pre-execution, so the run would silently collapse agent-by-agent (live
    # UAT finding F3). Fail fast here instead — BEFORE the engine, the
    # checkpointer, and the sandbox spin up (T-13-06-01). The condition
    # mirrors the factory raise EXACTLY ("template" in spec.injects AND no
    # od_context template_body) and is GENERIC — keyed on the resolved specs'
    # DECLARED injects only, never a pipeline-name allow/deny list (SC-001):
    # od_* runs with a loaded template pass unchanged; workflows whose agents
    # declare no template inject are untouched.
    #
    # Product decision (13-06, F3 — see 13-UAT.md Gap 3 missing item 3): bare
    # prototype/ppt remain admissible pipeline types (the tier sets include
    # them) but REQUIRE template context; the FE always sends od_* aliases,
    # so the only user-visible change is broken runs becoming visible.
    # F3 (13-06): template-inject ingress guard — only for pipelines that are
    # supposed to have OD context (od_* aliases and bare prototype/ppt which
    # require a template). Custom workflows that happen to include template-
    # injecting agents (e.g. prototype agents added to a custom workflow) skip
    # this guard — the factory's _compose_injection handles a missing
    # od_context gracefully for custom runs (injects are skipped when od_context
    # is empty).
    _template_injecting = [
        spec.id for spec in agents if "template" in (getattr(spec, "injects", None) or [])
    ]
    _needs_template = pipeline_type in ("prototype", "ppt", "od_prototype", "od_ppt")
    if _template_injecting and _needs_template and not (od_context or {}).get("template_body"):
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {
                "error": (
                    f"Pipeline {pipeline_type!r} agents "
                    f"{_template_injecting} declare template injection, so the "
                    "run requires a template (template_id) or an od_* alias — "
                    "no template body could be loaded."
                ),
                "code": "missing_template_context",
                "recoverable": False,
            },
        })
        return

    # ── model_overrides ingress validation (Phase 6 D-07, MODEL-03) ───────
    # The security chokepoint: validate the untrusted per-agent override map
    # against the catalog allow-list AND this run's resolved agent set, BEFORE
    # any run starts. A rejection emits the existing error-event shape with
    # code "invalid_model_override" and returns without calling engine.execute
    # (no WorkflowRun is created). Done here because the run's agent set
    # (`agents`) is only known after resolution above. Absent → {} (no-op).
    model_overrides = model_overrides or {}
    _override_error = _validate_model_overrides(
        model_overrides, {spec.id for spec in agents}
    )
    if _override_error is not None:
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": _override_error,
                     "code": "invalid_model_override", "recoverable": False},
        })
        return

    # ── EMP-02 launch-side trust=user re-validation (Pitfall 3) ───────────────
    # Re-compile the persisted/replayed per-step selections with trust="user"
    # BEFORE any run starts — a tampered/smuggled non-user-allowed capability is
    # rejected at LAUNCH, not only at save. Empty/absent selections → no-op (every
    # existing run is byte-identical). Done here, after the agent set is resolved,
    # so the synth manifest carries this run's exact agents.
    _selection_error = _revalidate_selections_trust_user(
        base_pipeline_type, [spec.id for spec in agents], selections
    )
    if _selection_error is not None:
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": _selection_error,
                     "code": "invalid_selection", "recoverable": False},
        })
        return

    # ── Create WorkflowRun record ─────────────────────────────────────────
    pipeline_run_id = str(_uuid.uuid4())
    # ISS-007 (16-02): register this run's COOPERATIVE cancel event and publish
    # the run id back to the connection loop so cancel_pipeline (the Stop button)
    # resolves THIS run's event and sets it (instead of destructively cancelling
    # the drainer). Owner/connection-scoped: only the connection that started the
    # run holds the sink, so a cancel can never reach another owner's run
    # (T-16-02-TENANT). The event is passed to engine.execute below; the engine
    # observes it per-chunk / pre-agent and emits pipeline_cancelled.
    cancel_event = asyncio.Event()
    _CANCEL_EVENTS[pipeline_run_id] = cancel_event
    if run_id_sink is not None:
        run_id_sink.clear()
        run_id_sink.append(pipeline_run_id)
    workflow_run_id = None
    execution_start = datetime.now(timezone.utc)
    monotonic_start = time.monotonic()
    db = _get_db()
    try:
        # Only link parent_run_id if the source run actually exists. parent_run_id
        # is an enforced FK (migration 0013), so a stale/foreign id would abort
        # run creation — degrade gracefully to an unlinked run instead.
        parent_run_id = None
        if source_workflow_run_id:
            _src = (
                db.query(WorkflowRun.id)
                .filter(WorkflowRun.id == source_workflow_run_id)
                .first()
            )
            parent_run_id = source_workflow_run_id if _src else None

        workflow_run = WorkflowRun(
            # WorkflowRun.id IS the run identifier used end-to-end (engine, state
            # machine, and the workflow_artifacts FK). We generate it as a uuid4
            # and set it as the PK so artifact writes resolve against this row.
            id=pipeline_run_id,
            user_id=user.id,
            title=(_strip_pipeline_context(content) or _extract_title_from_context(content) or content or "Untitled")[:60].strip(),
            type=pipeline_type,
            status="running",
            input=content or f"Run {pipeline_type} pipeline",
            agent_count=len(agents),
            # Phase 3 (T072): persist session_id for cross-restart resumability
            session_id=user.id,
            # Phase 3 (T056): revision chaining — link to the source run (validated)
            parent_run_id=parent_run_id,
            # WR-02 — persist the launch-validated per-step selections so
            # resume_run can re-apply them (re-validated trust="user" at launch
            # :1544 via _revalidate_selections_trust_user and AGAIN on resume at
            # _apply_selections overlay time). Persisted at row CREATION (not
            # finalize) so the row carries selections BEFORE the run can crash —
            # a backend-restart resume must find them. None for non-composed runs.
            selections_json=selections,
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)
        workflow_run_id = workflow_run.id
    finally:
        db.close()

    # Async title generation (best-effort, non-blocking)
    if workflow_run_id:
        asyncio.create_task(
            _generate_workflow_title(
                workflow_run_id=workflow_run_id, content=content or "",
                pipeline_type=pipeline_type, websocket=websocket,
            )
        )

    # ── Bedrock config check ──────────────────────────────────────────────
    if not (settings.BEDROCK_MODEL_ID and settings.AWS_REGION) and not settings.ANTHROPIC_API_KEY:
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": "LLM provider not configured.",
                     "code": "llm_provider_misconfigured", "recoverable": False},
        })
        return

    # ── Execute through the Universal Engine — queue-based, WS-decoupled ──
    # The pipeline runs as a background task writing events to a queue.
    # The WebSocket drains the queue. If the WS disconnects, the pipeline
    # keeps running. On reconnect, the new WS picks up the same queue.
    engine = get_execution_engine()
    final_output = ""
    agent_outputs_collector: list[dict] = []
    current_agent: dict = {}
    any_agent_errored = False
    first_agent_error_msg: Optional[str] = None
    # IN-03 (13 review fix): the pipeline_complete payload is the authoritative
    # terminal truth (WR-05 semantics) — capture it so DB persistence agrees
    # with what the FE was told, instead of flipping ANY run with an
    # agent_error to "failed" (which marked degraded AND recovered-timeout
    # completions as failures — three surfaces disagreed).
    pipeline_complete_seen = False
    degraded_failed_agents: Optional[list] = None  # non-None ⇒ status "degraded"
    # UXFIX-02 (22-03 / D-19): capture the DECLARED/resolved deliverable shape the
    # engine emits on pipeline_complete (engine.py:2117-2128 — already in
    # _VOLATILE_STRIP_KEYS, INV-3-safe) so the run-finalize persist writes them
    # onto the two additive WorkflowRun columns. History-reopen then drives the
    # deliverable mimetype from the persisted value (so a binary deliverable, e.g.
    # application/zip, re-renders faithfully) instead of the FE text heuristic.
    # Keyed GENERICALLY on the emitted deliverable values — NOT a workflow name
    # (SC-001). Legacy NULL rows fall back to the FE heuristic (parity).
    deliverable_mimetype: Optional[str] = None
    deliverable_filename: Optional[str] = None
    # ISS-007 (16-02): the engine emits pipeline_cancelled as a NORMAL yield on
    # the cooperative path (cancel_event observed per-chunk / pre-agent) — NOT
    # via CancelledError. The async-for then completes normally and falls into
    # the success-persist block below, which (without this flag) would mis-mark a
    # cooperatively-cancelled run "completed". Track it so the persist block
    # writes "cancelled", matching the destructive-path CancelledError handler.
    pipeline_cancelled_seen = False

    event_queue = _get_or_create_queue(pipeline_run_id)

    async def _run_pipeline_to_queue() -> None:
        """Run the engine and push all events into the queue. Never touches WS."""
        nonlocal final_output, agent_outputs_collector, current_agent
        nonlocal any_agent_errored, first_agent_error_msg
        nonlocal pipeline_complete_seen, degraded_failed_agents
        nonlocal pipeline_cancelled_seen
        nonlocal deliverable_mimetype, deliverable_filename

        try:
            async for update in engine.execute(
                agents=agents,
                user_message=content,
                pipeline_run_id=pipeline_run_id,
                pipeline_type=pipeline_type,
                # ISS-007 (16-02): cooperative cancel — cancel_pipeline sets this
                # event; the engine observes it (per-chunk / pre-agent) and emits
                # pipeline_cancelled through this same drained path.
                cancel_event=cancel_event,
                user_id=user.id,
                # D-09 anon-principal source: the WS chat session id. For authed runs
                # owner_id == user_id so this is unused; threaded so an unauthenticated
                # run would get a stable per-session owner (anon:<session_id>, AUTHZ-03).
                session_id=chat_session_id,
                attached_skills=attached_skills or [],
                attached_hooks=attached_hooks or [],
                model_id=getattr(user, "preferred_model", None) or None,
                od_context=od_context,
                gate_agent_ids=gate_agent_ids,
                parent_run_id=parent_run_id,
                model_overrides=model_overrides,
                selections=selections,
            ):
                await event_queue.put({"type": update["type"], "data": update.get("data", {})})
                # Track state for DB persistence
                utype = update["type"]
                if utype == "agent_start":
                    current_agent = {
                        "agent_id": update["data"].get("agent_id"),
                        "name": update["data"].get("name"),
                        "role": update["data"].get("role"),
                        "icon": update["data"].get("icon"),
                        "output": "", "duration": None,
                        "input_prompt": None, "context_sources": [],
                        "tool_calls": [], "thinking_text": "",
                    }
                elif utype == "agent_input":
                    current_agent["input_prompt"] = update["data"].get("context_message")
                    current_agent["context_sources"] = update["data"].get("context_sources", [])
                elif utype == "agent_thinking":
                    current_agent["thinking_text"] = (current_agent.get("thinking_text") or "") + update["data"].get("thinking", "")
                elif utype == "tool_call":
                    current_agent.setdefault("tool_calls", []).append({
                        "tool": update["data"].get("tool"),
                        "args": update["data"].get("args", {}),
                        "result": None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                elif utype == "tool_result":
                    for tc in reversed(current_agent.get("tool_calls", [])):
                        if tc.get("tool") == update["data"].get("tool") and tc.get("result") is None:
                            tc["result"] = update["data"].get("result")
                            break
                elif utype == "agent_chunk":
                    current_agent["output"] = current_agent.get("output", "") + update["data"].get("chunk", "")
                elif utype == "agent_complete":
                    current_agent["duration"] = update["data"].get("duration")
                    current_agent["input_tokens"] = update["data"].get("input_tokens", 0)
                    current_agent["output_tokens"] = update["data"].get("output_tokens", 0)
                    current_agent["total_tokens"] = update["data"].get("total_tokens", 0)
                    # Only persist when this corresponds to a real agent_start.
                    # A trailing agent_complete (e.g. validator-timeout path) can
                    # fire after current_agent was already appended + reset to {},
                    # which would otherwise append an orphan with no agent_id.
                    if current_agent.get("agent_id"):
                        agent_outputs_collector.append(current_agent)
                    current_agent = {}
                elif utype == "agent_error":
                    any_agent_errored = True
                    if first_agent_error_msg is None:
                        first_agent_error_msg = update["data"].get("error") or "Agent execution error"
                    current_agent["error"] = update["data"].get("error")
                    # Same guard as agent_complete: skip an empty/reset current_agent.
                    if current_agent.get("agent_id"):
                        agent_outputs_collector.append(current_agent)
                    current_agent = {}
                elif utype == "pipeline_complete":
                    final_output = update["data"].get("final_output", "")
                    # IN-03: capture the WR-05 terminal payload semantics —
                    # status "degraded" + agents_failed are present ONLY when
                    # some agent errored and never completed.
                    pipeline_complete_seen = True
                    # UXFIX-02 (22-03): capture the emitted deliverable shape so
                    # the run-finalize persist writes the two additive columns
                    # (engine emits these unconditionally on pipeline_complete).
                    deliverable_mimetype = update["data"].get("deliverable_mimetype")
                    deliverable_filename = update["data"].get("deliverable_filename")
                    if update["data"].get("status") == "degraded":
                        degraded_failed_agents = list(
                            update["data"].get("agents_failed", [])
                        )
                elif utype == "pipeline_cancelled":
                    # ISS-007 (16-02): cooperative cancel terminal observed as a
                    # normal yield — flag it so the persist block writes
                    # "cancelled" (not "completed").
                    pipeline_cancelled_seen = True

            # ── Pipeline completed successfully — persist immediately ──────
            # This runs INSIDE the background task, after the async for loop
            # completes normally (all events processed). We have the full
            # agent_outputs_collector and final_output here — no race condition.
            if workflow_run_id:
                db = _get_db()
                try:
                    wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                    if wr:
                        # Always write output and agent_outputs — the outer block
                        # may have already set status to "completed" but with NULL output
                        # due to the race condition. We fix it here with real data.
                        # IN-03 (13 review fix): status follows the authoritative
                        # terminal payload (WR-05). A degraded completion persists
                        # the distinct "degraded" status (free-string column — no
                        # migration, Q3) instead of "failed"; a clean
                        # pipeline_complete (incl. a recovered-timeout agent that
                        # errored then completed) persists "completed". Runs that
                        # ended WITHOUT pipeline_complete (pipeline_failed /
                        # budget_aborted / gate-cancel) keep the legacy
                        # errored→failed mapping.
                        if pipeline_cancelled_seen:
                            # ISS-007 (16-02): cooperative cancel — the engine
                            # emitted pipeline_cancelled as a normal terminal and
                            # the async-for ended cleanly. Persist "cancelled"
                            # (parity with the destructive-path CancelledError
                            # handler) instead of falling through to "completed".
                            wr.status = "cancelled"
                            if not wr.completed_at:
                                wr.completed_at = datetime.now(timezone.utc)
                        elif degraded_failed_agents is not None:
                            wr.status = "degraded"
                            wr.error = first_agent_error_msg or (
                                "degraded: agent(s) failed: "
                                + ", ".join(degraded_failed_agents)
                            )
                        elif pipeline_complete_seen:
                            wr.status = "completed"
                        else:
                            wr.status = "failed" if any_agent_errored else "completed"
                            if any_agent_errored:
                                wr.error = first_agent_error_msg
                        if final_output:
                            wr.output = final_output
                        # UXFIX-02 (22-03 / D-19): persist the DECLARED/resolved
                        # deliverable shape so reopen drives the mimetype from the
                        # persisted value (a binary deliverable re-renders true to
                        # type). Generic — keyed on the emitted values, no workflow
                        # name (SC-001). Only write when emitted (legacy NULL stays
                        # NULL → FE heuristic fallback, parity).
                        if deliverable_mimetype is not None:
                            wr.deliverable_mimetype = deliverable_mimetype
                        if deliverable_filename is not None:
                            wr.deliverable_filename = deliverable_filename
                        if agent_outputs_collector:
                            wr.agent_outputs = json.dumps(agent_outputs_collector)
                        # Aggregate token usage across all agents
                        total_input = sum(a.get("input_tokens", 0) or 0 for a in agent_outputs_collector)
                        total_output = sum(a.get("output_tokens", 0) or 0 for a in agent_outputs_collector)
                        if total_input + total_output > 0:
                            wr.token_usage = json.dumps({
                                "total_input_tokens": total_input,
                                "total_output_tokens": total_output,
                                "total_tokens": total_input + total_output,
                                "estimated_cost_usd": round(
                                    (total_input * 0.00000025) + (total_output * 0.00000125), 6
                                ),  # Haiku pricing: $0.25/M input, $1.25/M output
                            })
                        if not wr.completed_at:
                            wr.completed_at = datetime.now(timezone.utc)
                        if not wr.duration:
                            wr.duration = round(time.monotonic() - monotonic_start, 1)
                        db.commit()
                        logger.info(
                            "Pipeline completed — run=%s status=%s agents=%d output=%d chars tokens=%d",
                            workflow_run_id, wr.status, len(agent_outputs_collector),
                            len(final_output) if final_output else 0,
                            total_input + total_output,
                        )
                finally:
                    db.close()
        except asyncio.CancelledError:
            duration = round(time.monotonic() - monotonic_start, 1)
            logger.info("Pipeline task cancelled — run=%s duration=%.1fs", workflow_run_id, duration)
            await event_queue.put({"type": "pipeline_cancelled", "data": {
                "message": "Pipeline cancelled", "duration": duration,
                "agents_completed": len(agent_outputs_collector),
            }})
            if workflow_run_id:
                db = _get_db()
                try:
                    wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                    if wr:
                        wr.status = "cancelled"
                        wr.completed_at = datetime.now(timezone.utc)
                        wr.duration = duration
                        if agent_outputs_collector:
                            wr.agent_outputs = json.dumps(agent_outputs_collector)
                        db.commit()
                finally:
                    db.close()
        except Exception as e:
            logger.error("Pipeline task error — run=%s: %s", workflow_run_id, e, exc_info=True)
            await event_queue.put({"type": "error", "data": {
                "error": f"Pipeline execution failed: {e}",
                "code": "pipeline_error", "recoverable": True,
            }})
            if workflow_run_id:
                db = _get_db()
                try:
                    wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                    if wr:
                        wr.status = "failed"
                        wr.error = str(e)
                        wr.completed_at = datetime.now(timezone.utc)
                        wr.duration = round((datetime.now(timezone.utc) - execution_start).total_seconds(), 1)
                        db.commit()
                finally:
                    db.close()
        finally:
            # Signal queue consumers that the pipeline is done
            await event_queue.put(None)
            _cleanup_pipeline(pipeline_run_id)

    # Start the pipeline as a background task (independent of WS connection)
    pipeline_bg_task = asyncio.create_task(_run_pipeline_to_queue())
    _PIPELINE_TASKS[pipeline_run_id] = pipeline_bg_task

    # ── Drain the queue to the WebSocket ─────────────────────────────────
    # This loop reads events from the queue and sends them to the WS.
    # If the WS dies, we exit this loop but the pipeline keeps running.
    # On reconnect, the client sends reconnect_pipeline and a new drainer starts.
    # Timeout of 10s — sends heartbeat to detect dead connections quickly.
    try:
        while True:
            try:
                # Use a short timeout so we can send WS-level pings periodically.
                # ISS-007 (16-02): asyncio.timeout() (not asyncio.wait_for) — the
                # correct CPython-3.11 primitive; it does not swallow a
                # result-vs-cancel race at the await boundary, removing the latent
                # path where a cooperatively-emitted pipeline_cancelled could be
                # lost (defense-in-depth).
                async with asyncio.timeout(10.0):
                    event = await event_queue.get()
            except asyncio.TimeoutError:
                # Send a heartbeat to detect dead connections.
                try:
                    await websocket.send_json({
                        "type": "pipeline_heartbeat",
                        "chunk": None,
                        "section": pipeline_type,
                        "data": {"pipeline_run_id": pipeline_run_id,
                                 "timestamp": datetime.now(timezone.utc).isoformat()},
                    })
                except Exception:
                    # WS is dead — exit drainer, pipeline keeps running in background
                    logger.info(
                        "WS send failed during heartbeat — disconnecting drainer for run=%s (pipeline continues)",
                        pipeline_run_id,
                    )
                    break
                continue

            if event is None:
                # Pipeline finished — sentinel received
                break

            try:
                await websocket.send_json({
                    "type": event["type"], "chunk": None,
                    "section": pipeline_type, "data": event.get("data", {}),
                })
            except Exception:
                # WS died — put the event back and exit drainer
                # Pipeline keeps running; reconnect will resume
                logger.info(
                    "WS send failed — disconnecting drainer for run=%s (pipeline continues in background)",
                    pipeline_run_id,
                )
                await event_queue.put(event)  # put it back for the next consumer
                break

            utype = event["type"]
            if utype == "pipeline_complete":
                final_output = event.get("data", {}).get("final_output", "")
                break
            # IN-02 (13 review fix): pipeline_failed (F3 total collapse) and
            # budget_aborted are terminals — break here like the other
            # terminals instead of idling until the bg task's None sentinel.
            elif utype in ("pipeline_cancelled", "error", "pipeline_failed", "budget_aborted"):
                break

    except asyncio.CancelledError:
        # WS connection task was cancelled (e.g. user closed tab)
        # Cancel the pipeline background task too
        pipeline_bg_task.cancel()
        raise

    # ── Persist terminal state (safety fallback) ─────────────────────────
    # The pipeline background task already persists the success case above.
    # This fallback only writes if output/agents are still missing.
    try:
        await asyncio.wait_for(pipeline_bg_task, timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
        pass

    if workflow_run_id and not pipeline_bg_task.cancelled():
        db = _get_db()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            # Only write if output/agents are still missing — the bg task should have written them
            if wr and (wr.output is None or wr.agent_outputs is None):
                if wr.status == "running":
                    # IN-03: mirror the bg-task persistence — status follows the
                    # terminal payload, not the bare any_agent_errored flag.
                    if degraded_failed_agents is not None:
                        wr.status = "degraded"
                        wr.error = first_agent_error_msg or (
                            "degraded: agent(s) failed: "
                            + ", ".join(degraded_failed_agents)
                        )
                    elif pipeline_complete_seen:
                        wr.status = "completed"
                    else:
                        wr.status = "failed" if any_agent_errored else "completed"
                        if any_agent_errored:
                            wr.error = first_agent_error_msg
                    wr.completed_at = datetime.now(timezone.utc)
                    wr.duration = round((datetime.now(timezone.utc) - execution_start).total_seconds(), 1)
                if final_output and wr.output is None:
                    wr.output = final_output
                # UXFIX-02 (22-03): mirror the bg-task persist for the additive
                # deliverable-shape columns (only when still missing / emitted).
                if deliverable_mimetype is not None and wr.deliverable_mimetype is None:
                    wr.deliverable_mimetype = deliverable_mimetype
                if deliverable_filename is not None and wr.deliverable_filename is None:
                    wr.deliverable_filename = deliverable_filename
                if agent_outputs_collector and wr.agent_outputs is None:
                    wr.agent_outputs = json.dumps(agent_outputs_collector)
                db.commit()
                logger.info("Fallback persistence wrote output/agents for run=%s", workflow_run_id)
        finally:
            db.close()

    # ── Persist assistant message ─────────────────────────────────────────
    if final_output and chat_session_id:
        db = _get_db()
        try:
            chat_session = (
                db.query(ChatSession)
                .filter(ChatSession.id == chat_session_id, ChatSession.user_id == user.id)
                .first()
            )
            if chat_session is not None:
                if pipeline_type in ("ppt", "od_ppt"):
                    summary = "\u2705 **Presentation generated!** Check the Preview panel."
                elif pipeline_type in ("prototype", "od_prototype"):
                    summary = "\u2705 **Prototype generated!** Check the Preview panel."
                else:
                    summary = final_output[:500]
                db.add(Message(chat_session_id=chat_session_id, role="assistant", content=summary))
                chat_session.last_activity = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()


async def _handle_revision_execution(
    websocket: WebSocket,
    user: User,
    parent_run_id: str,
    target_artifact_type: str,
    instruction: str,
    run_id_sink: list | None = None,
) -> None:
    """Run a ``run_revision`` request — queue-decoupled (Phase 14, 14-02).

    The extracted execution half of the WS ``run_revision`` branch, mirroring
    ``_handle_workflow_execution``'s background-task + per-run-queue + drainer
    pattern: the revision engine runs as a background task writing events to a
    per-run queue keyed by the revision ``pipeline_run_id``; this coroutine
    drains the queue to the WebSocket. The run is registered in
    ``_PIPELINE_TASKS`` / ``_PIPELINE_QUEUES`` (cancellable via cancel_pipeline,
    reconnect-discoverable via the owner-gated reconnect path) and cleaned by
    ``_cleanup_pipeline``.

    Terminal-status fidelity (RESEARCH Pitfall 4): the revision WorkflowRun's
    terminal status follows the AUTHORITATIVE terminal event observed on the
    forwarded stream — a clean ``pipeline_complete`` → "completed", a
    ``pipeline_complete`` carrying ``data.status == "degraded"`` → "degraded"
    (WR-02, mirroring the run_pipeline mapping), ``pipeline_failed`` or no
    terminal → "failed", cancellation → "cancelled". Never an unconditional
    "completed" flip (a failed/degraded revision recorded as completed would
    be offered as a revision parent by the FE's status === "completed"
    lookup); no terminal path leaves the row "revising".
    """
    import uuid as _uuid_mod

    # app → agents is a legal import direction (the reverse is the
    # import-linter-forbidden one); imported locally to keep websocket.py's
    # import-time graph unchanged (matching the engine import below).
    from agents.registry import get_pipeline_agents

    pipeline_run_id = str(_uuid_mod.uuid4())
    # ISS-007 (16-02): per-run cooperative cancel event (Stop button) for the
    # revision run — registered + published to the connection sink exactly like
    # the run_pipeline path so cancel_pipeline sets THIS run's event cooperatively
    # instead of destructively cancelling the drainer.
    cancel_event = asyncio.Event()
    _CANCEL_EVENTS[pipeline_run_id] = cancel_event
    if run_id_sink is not None:
        run_id_sink.clear()
        run_id_sink.append(pipeline_run_id)

    # WR-06 (13 review fix): the FE-routed revision alias (ppt_revision /
    # od_ppt_revision), matching the engine's emitted pipeline_type — the FE's
    # revision-of-revision lookup matches runs on ``workflowType + "_revision"``,
    # which the verbatim ``{target}_revision`` (= ppt_output_revision) never hit.
    revision_pipeline_type = f"{target_artifact_type.removesuffix('_output')}_revision"

    # RESEARCH Pitfall 6: agent_count reflects the REAL registry membership of
    # the derived revision pipeline (ppt_revision=2, od_ppt_revision=1) — never
    # a hardcoded 1. An unknown target yields an empty list (closed registry
    # lookup, no dispatch implication at this layer) → cosmetic fallback 1; the
    # dispatch itself fails later at the engine's pre-dispatch guard.
    _rev_agents = get_pipeline_agents(revision_pipeline_type)

    # Create the revision WorkflowRun (fields byte-identical to the pre-14-02
    # inline branch EXCEPT the derived agent_count above).
    db = _get_db()
    try:
        wr = WorkflowRun(
            # WorkflowRun.id is the single run identifier (see the main
            # pipeline path). The revision engine writes the new artifact
            # version with run_id == this id, and the state machine looks
            # the run up by id.
            id=pipeline_run_id,
            user_id=user.id,
            # CR-01 / AUTHZ-03: stamp the owner at creation so the row is
            # never owner-None. The workspace is transiently NULL here:
            # execute() — the 14-03 dispatch chokepoint — mints the revision
            # run's OWN workspace and completes the scope via its
            # set_run_scope, so the run row and its run_events carry that
            # minted workspace (NOT the parent's; the pre-14 in-method
            # writeback was deleted, WR-04). Only the post-dispatch
            # exact-kind lineage ref is stamped with the PARENT artifact's
            # workspace (engine.py write_ref workspace_id=original
            # .workspace_id) so the owner+workspace scope filter holds for
            # revision-of-revision reads. Proven by
            # test_revision_run_events_persist_and_resolve_on_real_db.
            owner_id=user.id,
            # Link the revision run to its parent so lineage stays intact
            # (parent_run_id is an enforced FK — only set when the parent
            # row actually exists, else creation would abort).
            parent_run_id=(
                parent_run_id
                if db.query(WorkflowRun.id)
                .filter(WorkflowRun.id == parent_run_id)
                .first()
                else None
            ),
            title=f"Revision: {instruction[:50]}",
            type=revision_pipeline_type,
            status="revising",
            input=instruction,
            agent_count=len(_rev_agents) or 1,
        )
        db.add(wr)
        db.commit()
        db.refresh(wr)
        workflow_run_id = wr.id
    finally:
        db.close()

    event_queue = _get_or_create_queue(pipeline_run_id)

    async def _run_revision_to_queue() -> None:
        """Run the revision engine and push all events into the queue.

        Never touches the WS. Owns the terminal status persistence — every
        exit path (return / ValueError / CancelledError / Exception) writes a
        terminal status keyed on the observed terminal state, so the row can
        never be left "revising".
        """
        pipeline_complete_seen = False
        pipeline_failed_seen = False
        degraded_seen = False
        # ISS-007 (16-02): cooperative cancel terminal observed on the forwarded
        # stream (engine emits pipeline_cancelled as a normal yield).
        pipeline_cancelled_seen = False

        async def _queue_send(event: dict) -> None:
            """The websocket_send_fn handed to the engine — the WS layer
            observes terminal events from the stream it forwards (no
            _handle_revision signature change)."""
            nonlocal pipeline_complete_seen, pipeline_failed_seen, degraded_seen
            nonlocal pipeline_cancelled_seen
            etype = event.get("type")
            if etype == "pipeline_cancelled":
                pipeline_cancelled_seen = True
            if etype == "pipeline_complete":
                pipeline_complete_seen = True
                # WR-02 (14 review fix): execute() emits pipeline_complete with
                # status "degraded" + agents_failed when an agent errored
                # unrecovered. Mirror the run_pipeline mapping (13 IN-03): a
                # degraded revision must never be recorded "completed" — the
                # FE's revision-parent lookup keys on status === "completed",
                # so a lying status offers a partial deliverable as a future
                # revision parent.
                if event.get("data", {}).get("status") == "degraded":
                    degraded_seen = True
            elif etype == "pipeline_failed":
                pipeline_failed_seen = True
            await event_queue.put(event)

        def _persist_terminal_status(status: str) -> None:
            sdb = _get_db()
            try:
                swr = (
                    sdb.query(WorkflowRun)
                    .filter(WorkflowRun.id == workflow_run_id)
                    .first()
                )
                if swr:
                    swr.status = status
                    swr.completed_at = datetime.now(timezone.utc)
                    sdb.commit()
            finally:
                sdb.close()

        from agents.execution_engine.engine import get_execution_engine

        try:
            await get_execution_engine()._handle_revision(
                parent_run_id=parent_run_id,
                target_artifact_type=target_artifact_type,
                instruction=instruction,
                pipeline_run_id=pipeline_run_id,
                websocket_send_fn=_queue_send,
                model_id=getattr(user, "preferred_model", None) or None,
                owner_id=user.id,
                cancel_event=cancel_event,
            )
            # Terminal status follows the authoritative terminal event:
            # cancelled if a cooperative pipeline_cancelled was observed (ISS-007),
            # degraded if the completion carried status "degraded" (WR-02),
            # completed iff a CLEAN pipeline_complete was observed.
            _persist_terminal_status(
                "cancelled"
                if pipeline_cancelled_seen
                else "degraded"
                if degraded_seen
                else "completed"
                if (pipeline_complete_seen and not pipeline_failed_seen)
                else "failed"
            )
        except ValueError as exc:
            await event_queue.put({
                "type": "error",
                "data": {"error": str(exc), "code": "revision_validation_error",
                         "recoverable": False},
            })
            _persist_terminal_status("failed")
        except asyncio.CancelledError:
            # run_pipeline precedent (_run_pipeline_to_queue): absorb the
            # cancellation, surface pipeline_cancelled, persist "cancelled".
            logger.info("Revision task cancelled — run=%s", workflow_run_id)
            await event_queue.put({
                "type": "pipeline_cancelled",
                "data": {"message": "Revision cancelled"},
            })
            _persist_terminal_status("cancelled")
        except Exception as exc:
            logger.error("Revision failed: %s", exc, exc_info=True)
            await event_queue.put({
                "type": "error",
                "data": {"error": f"Revision failed: {exc}",
                         "code": "revision_error", "recoverable": True},
            })
            _persist_terminal_status("failed")
        finally:
            # Signal queue consumers that the revision is done
            await event_queue.put(None)
            _cleanup_pipeline(pipeline_run_id)

    # Start the revision as a background task (independent of WS connection)
    revision_bg_task = asyncio.create_task(_run_revision_to_queue())
    _PIPELINE_TASKS[pipeline_run_id] = revision_bg_task

    # ── Drain the queue to the WebSocket ─────────────────────────────────
    # Mirrors the run_pipeline drainer. Every drained frame preserves the
    # pre-14-02 _send_revision_event FE contract: {type, chunk: None,
    # section: <target_artifact_type>, data} — section is the TARGET artifact
    # type, not the pipeline type. Error events from the background task ride
    # the same wrapper.
    terminal_break = False  # WR-01: True only when a terminal event broke the loop
    try:
        while True:
            try:
                # ISS-007 (16-02): asyncio.timeout() — the correct CPython-3.11
                # primitive (no result-vs-cancel swallow), matching the main
                # drainer; defense-in-depth for cooperative cancel delivery.
                async with asyncio.timeout(10.0):
                    event = await event_queue.get()
            except asyncio.TimeoutError:
                # Send a heartbeat to detect dead connections.
                try:
                    await websocket.send_json({
                        "type": "pipeline_heartbeat",
                        "chunk": None,
                        "section": target_artifact_type,
                        "data": {"pipeline_run_id": pipeline_run_id,
                                 "timestamp": datetime.now(timezone.utc).isoformat()},
                    })
                except Exception:
                    # WS is dead — exit drainer, revision continues in background
                    logger.info(
                        "WS send failed during heartbeat — disconnecting revision drainer for run=%s (revision continues)",
                        pipeline_run_id,
                    )
                    break
                continue

            if event is None:
                # Revision finished — sentinel received
                break

            try:
                await websocket.send_json({
                    "type": event["type"], "chunk": None,
                    "section": target_artifact_type, "data": event.get("data", {}),
                })
            except Exception:
                # WS died — put the event back and exit drainer
                # Revision keeps running; reconnect will resume
                logger.info(
                    "WS send failed — disconnecting revision drainer for run=%s (revision continues in background)",
                    pipeline_run_id,
                )
                await event_queue.put(event)  # put it back for the next consumer
                break

            if event["type"] in (
                "pipeline_complete", "pipeline_cancelled", "error",
                "pipeline_failed", "budget_aborted",
            ):
                terminal_break = True
                break

    except asyncio.CancelledError:
        # The outer task was cancelled (cancel_pipeline / connection closed) —
        # propagate to the background engine task, whose CancelledError path
        # persists "cancelled" (mirrors _handle_workflow_execution).
        revision_bg_task.cancel()
        raise

    # Let the background task finish its terminal persistence + cleanup so
    # callers awaiting this coroutine observe the final row state.
    try:
        await asyncio.wait_for(revision_bg_task, timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
        pass

    # ── WR-01 (14 review fix): residual drain after a terminal break ─────
    # The engine emits state_restoration_failed AFTER the terminal
    # pipeline_complete (the post-dispatch exact-kind lineage write runs
    # post-emit since 14-03), so it lands on the queue after the terminal
    # break above — previously queued for nobody and discarded by
    # _cleanup_pipeline, making a failed FR-014 chain-link-1 lineage write
    # invisible to the client. The bg task has now finished (awaited with
    # grace), so forward any residual non-sentinel events on the same
    # wrapper. Scoped to the terminal-break exit ONLY: a WS-death break
    # leaves the queue intact for the reconnect drainer.
    if terminal_break and revision_bg_task.done():
        while True:
            try:
                residual = event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if residual is None:
                break
            try:
                await websocket.send_json({
                    "type": residual["type"], "chunk": None,
                    "section": target_artifact_type,
                    "data": residual.get("data", {}),
                })
            except Exception:
                break

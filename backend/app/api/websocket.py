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


def _get_or_create_queue(pipeline_run_id: str) -> asyncio.Queue:
    if pipeline_run_id not in _PIPELINE_QUEUES:
        _PIPELINE_QUEUES[pipeline_run_id] = asyncio.Queue(maxsize=0)  # unbounded
    return _PIPELINE_QUEUES[pipeline_run_id]


def _cleanup_pipeline(pipeline_run_id: str) -> None:
    _PIPELINE_QUEUES.pop(pipeline_run_id, None)
    _PIPELINE_TASKS.pop(pipeline_run_id, None)


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
    # Import the kernel-pure catalog lazily (app → kernel import is allowed; the
    # catalog has no app.* reach so this stays import-clean).
    from agents.capabilities.model_catalog import ModelCatalog

    allowed_model_ids = set(ModelCatalog().ids())
    for agent_id, model_id in model_overrides.items():
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


def _get_db() -> Session:
    """Create a new database session for WebSocket use."""
    return SessionLocal()


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
    print(f"[WS] Connection accepted via {auth_method}, validating token...")

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
    print(f"[WS] Authenticated user={user.id}, entering message loop")

    # Track the in-flight pipeline (if any) for this connection. Pipelines run
    # as background tasks so the receive loop stays responsive — that's what
    # makes cancel_pipeline actually able to interrupt a running pipeline
    # (blocker A3) and lets WebSocketDisconnect propagate cancellation to the
    # task. A single connection can run at most one pipeline at a time.
    current_pipeline_task: asyncio.Task | None = None

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
                print(f"[WS] Received run_pipeline: type={message_data.get('pipeline_type')}")
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
                current_pipeline_task = asyncio.create_task(
                    _handle_workflow_execution(
                        websocket, pipeline_content, pipeline_type,
                        chat_session_id, token, user, agent_ids=agent_ids,
                        attached_skills=attached_skills,
                        attached_hooks=attached_hooks,
                        gate_agent_ids=gate_agent_ids,
                        model_overrides=model_overrides,
                        template_id=message_data.get("template_id"),
                        design_system_id=message_data.get("design_system_id"),
                        discovery=message_data.get("discovery"),
                        custom_ds_body=message_data.get("custom_design_system_body") or None,
                        custom_template_body=message_data.get("custom_template_body") or None,
                        source_workflow_run_id=message_data.get("source_workflow_run_id") or None,
                    )
                )
                continue

            # Handle pipeline cancellation
            if msg_type == "cancel_pipeline":
                logger.info(f"Pipeline cancellation requested by user={user.id}")
                if current_pipeline_task is not None and not current_pipeline_task.done():
                    # Issue cancellation; the task itself (in
                    # _handle_pipeline_execution) catches CancelledError,
                    # marks the WorkflowRun as "cancelled" (A6), and sends
                    # pipeline_cancelled to the client. We deliberately do
                    # NOT send the ack here — doing so would race with the
                    # task's own ack and the WorkflowRun update.
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

                    if running_task and not running_task.done() and running_queue is not None:
                        # Pipeline is still running — attach a new drainer
                        logger.info("Client reconnected to running pipeline run=%s", _reconnect_run_id)
                        try:
                            await websocket.send_json({
                                "type": "pipeline_reconnected", "chunk": None, "section": None,
                                "data": {"pipeline_run_id": _reconnect_run_id,
                                         "message": "Reconnected — resuming pipeline stream"},
                            })
                        except Exception:
                            pass
                        try:
                            while True:
                                try:
                                    event = await asyncio.wait_for(running_queue.get(), timeout=10.0)
                                except asyncio.TimeoutError:
                                    try:
                                        await websocket.send_json({
                                            "type": "pipeline_heartbeat", "chunk": None, "section": None,
                                            "data": {"pipeline_run_id": _reconnect_run_id,
                                                     "timestamp": datetime.now(timezone.utc).isoformat()},
                                        })
                                    except Exception:
                                        break
                                    continue
                                if event is None:
                                    break
                                try:
                                    await websocket.send_json({
                                        "type": event["type"], "chunk": None,
                                        "section": None, "data": event.get("data", {}),
                                    })
                                except Exception:
                                    await running_queue.put(event)
                                    break
                                if event["type"] in ("pipeline_complete", "pipeline_cancelled", "error"):
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
            # Creates a new WorkflowRun with parent_run_id and runs the revision
            # agent with the original artifact, version history, and instruction
            # as three separate structured inputs.
            if msg_type == "run_revision":
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

                import uuid as _uuid_mod
                _rev_pipeline_run_id = str(_uuid_mod.uuid4())

                # Create a new WorkflowRun with parent_run_id
                _rev_db = _get_db()
                try:
                    _rev_wr = WorkflowRun(
                        # WorkflowRun.id is the single run identifier (see the main
                        # pipeline path). The revision engine writes the new artifact
                        # version with run_id == this id, and the state machine looks
                        # the run up by id.
                        id=_rev_pipeline_run_id,
                        user_id=user.id,
                        # CR-01 / AUTHZ-03: stamp the owner at creation so the row is
                        # never owner-None. The workspace is the PARENT artifact's
                        # workspace (only resolvable inside the engine), so
                        # _handle_revision writes workspace_id back via
                        # ScopedStore.set_run_scope once `original` is read. Until
                        # then the row carries a real owner + (transiently) a null
                        # workspace; the engine writeback completes the scope so the
                        # owner+workspace-scoped /events get_run resolves it.
                        owner_id=user.id,
                        # Link the revision run to its parent so lineage stays intact
                        # (parent_run_id is an enforced FK — only set when the parent
                        # row actually exists, else creation would abort).
                        parent_run_id=(
                            _rev_parent_run_id
                            if _rev_db.query(WorkflowRun.id)
                            .filter(WorkflowRun.id == _rev_parent_run_id)
                            .first()
                            else None
                        ),
                        title=f"Revision: {_rev_instruction[:50]}",
                        type=f"{_rev_target_type}_revision",
                        status="revising",
                        input=_rev_instruction,
                        agent_count=1,
                    )
                    _rev_db.add(_rev_wr)
                    _rev_db.commit()
                    _rev_db.refresh(_rev_wr)
                    _rev_workflow_run_id = _rev_wr.id
                finally:
                    _rev_db.close()

                async def _send_revision_event(event: dict) -> None:
                    await websocket.send_json({
                        "type": event["type"], "chunk": None,
                        "section": _rev_target_type, "data": event["data"],
                    })

                from agents.execution_engine.engine import get_execution_engine as _get_engine
                _rev_engine = _get_engine()
                try:
                    await _rev_engine._handle_revision(
                        parent_run_id=_rev_parent_run_id,
                        target_artifact_type=_rev_target_type,
                        instruction=_rev_instruction,
                        pipeline_run_id=_rev_pipeline_run_id,
                        websocket_send_fn=_send_revision_event,
                        model_id=getattr(user, "preferred_model", None) or None,
                        owner_id=user.id,
                    )
                    # Mark revision run completed
                    _rev_db2 = _get_db()
                    try:
                        _rev_wr2 = _rev_db2.query(WorkflowRun).filter(WorkflowRun.id == _rev_workflow_run_id).first()
                        if _rev_wr2:
                            _rev_wr2.status = "completed"
                            _rev_wr2.completed_at = datetime.now(timezone.utc)
                            _rev_db2.commit()
                    finally:
                        _rev_db2.close()
                except ValueError as _rev_err:
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": str(_rev_err), "code": "revision_validation_error",
                                 "recoverable": False},
                    })
                except Exception as _rev_err:
                    logger.error("Revision failed: %s", _rev_err, exc_info=True)
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": f"Revision failed: {_rev_err}",
                                 "code": "revision_error", "recoverable": True},
                    })
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
                if not pipeline_run_id:
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "submit_questionnaire requires pipeline_run_id",
                                 "code": "missing_pipeline_run_id", "recoverable": True},
                    })
                    continue
                store = get_artifact_store()
                await store.set_questionnaire_responses(pipeline_run_id, responses)
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
    template_id: str | None = None,
    design_system_id: str | None = None,
    discovery: dict | None = None,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
    source_workflow_run_id: str | None = None,
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

    # ── Create WorkflowRun record ─────────────────────────────────────────
    pipeline_run_id = str(_uuid.uuid4())
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
            title=(_strip_pipeline_context(content) or content or "Untitled")[:60].strip(),
            type=pipeline_type,
            status="running",
            input=content or f"Run {pipeline_type} pipeline",
            agent_count=len(agents),
            # Phase 3 (T072): persist session_id for cross-restart resumability
            session_id=user.id,
            # Phase 3 (T056): revision chaining — link to the source run (validated)
            parent_run_id=parent_run_id,
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

    event_queue = _get_or_create_queue(pipeline_run_id)

    async def _run_pipeline_to_queue() -> None:
        """Run the engine and push all events into the queue. Never touches WS."""
        nonlocal final_output, agent_outputs_collector, current_agent
        nonlocal any_agent_errored, first_agent_error_msg

        try:
            async for update in engine.execute(
                agents=agents,
                user_message=content,
                pipeline_run_id=pipeline_run_id,
                pipeline_type=pipeline_type,
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
                        wr.status = "failed" if any_agent_errored else "completed"
                        if any_agent_errored:
                            wr.error = first_agent_error_msg
                        if final_output:
                            wr.output = final_output
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
                # Use a short timeout so we can send WS-level pings periodically
                event = await asyncio.wait_for(event_queue.get(), timeout=10.0)
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
            elif utype in ("pipeline_cancelled", "error"):
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
                    wr.status = "failed" if any_agent_errored else "completed"
                    if any_agent_errored:
                        wr.error = first_agent_error_msg
                    wr.completed_at = datetime.now(timezone.utc)
                    wr.duration = round((datetime.now(timezone.utc) - execution_start).total_seconds(), 1)
                if final_output and wr.output is None:
                    wr.output = final_output
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

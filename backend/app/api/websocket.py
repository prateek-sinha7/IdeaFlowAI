"""WebSocket endpoint for real-time AI chat streaming."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.agents.base import AgentConfigurationError
from app.agents.llm_errors import map_exception as _map_llm_exception
from app.agents.modes import get_mode_prompt
from app.agents.orchestrator import AgentOrchestrator
from app.core.config import settings
from app.core.security import decode_access_token, is_token_revoked
from app.models.chat import ChatSession, Message
from app.models.database import SessionLocal
from app.models.user import User
from app.models.workflow import WorkflowRun

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_db() -> Session:
    """Create a new database session for WebSocket use."""
    return SessionLocal()


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
        from app.agents.base import BaseAgent

        hint = _WORKFLOW_TITLE_PIPELINE_HINTS.get(pipeline_type, "AI workflow")
        title_agent = BaseAgent(
            system_prompt=(
                "Generate a short, professional title (3-7 words) for a "
                f"workflow that produces a {hint} based on the user's input. "
                "The title should describe the topic of the deliverable, "
                "not the workflow type itself. Return ONLY the title text "
                "— no quotes, no trailing punctuation, no explanation."
            ),
            max_tokens=64,
        )
        generated_title = await title_agent.run(clean_content)
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
    - Server routes to AgentOrchestrator and streams responses back
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

                # OD prototype uses its own runner with per-request prompt
                # composition; everything else goes through the standard
                # orchestrator_v2 path.
                if pipeline_type == "od_prototype":
                    # Tier gate — prototype requires Pro or higher
                    from app.core.entitlements import can_run_pipeline
                    allowed, reason = can_run_pipeline(user.tier, "prototype")
                    if not allowed:
                        await websocket.send_json({
                            "type": "error", "chunk": None, "section": None,
                            "data": {"error": reason, "code": "tier_limit", "recoverable": False, "upgrade_required": True},
                        })
                        continue
                    current_pipeline_task = asyncio.create_task(
                        _handle_od_prototype_execution(
                            websocket,
                            brief=pipeline_content,
                            template_id=message_data.get("template_id", ""),
                            design_system_id=message_data.get("design_system_id", ""),
                            discovery=message_data.get("discovery"),
                            user=user,
                        )
                    )
                else:
                    # Spawn as a background task — DO NOT await. Awaiting here
                    # blocks the receive loop for the entire pipeline duration,
                    # which is what made cancel_pipeline a no-op before A3.
                    current_pipeline_task = asyncio.create_task(
                        _handle_pipeline_execution(
                            websocket, pipeline_content, pipeline_type,
                            chat_session_id, token, user, agent_ids=agent_ids,
                            attached_skills=attached_skills,
                            attached_hooks=attached_hooks,
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

            # Handle questionnaire generation requests
            if msg_type == "generate_questions":
                pipeline_type = message_data.get("pipeline_type", "user_stories")
                prompt = message_data.get("message") or message_data.get("content") or ""
                await _handle_questionnaire(websocket, prompt, pipeline_type)
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
                    from app.agents.base import BaseAgent
                    title_agent = BaseAgent(
                        system_prompt=(
                            "Generate a very short title (3-5 words max) for a chat conversation "
                            "based on the user's first message. Return ONLY the title text, nothing else. "
                            "No quotes, no punctuation at the end, no explanation. Just the title."
                        )
                    )
                    generated_title = await title_agent.run(content)
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
                orchestrator = AgentOrchestrator()
                async for stream_msg in orchestrator.astream_execute(
                    user_message=content,
                    chat_session_id=chat_session_id,
                    mode=mode,
                    mode_prompt=mode_prompt,
                ):
                    if stream_msg.get("type") == "stream" and stream_msg.get("chunk"):
                        assistant_chunks.append(stream_msg["chunk"])
                    await websocket.send_json(stream_msg)

            except AgentConfigurationError:
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


async def _handle_od_prototype_execution(
    websocket: WebSocket,
    brief: str,
    template_id: str,
    design_system_id: str,
    discovery: dict | None,
    user: User,
) -> None:
    """Run the OpenDesign-style 4-agent prototype pipeline over WebSocket.

    Translates od_runner's NDJSON-shaped events into the same
    ``{type, chunk, section, data}`` envelope the existing pipelines use so
    the frontend ``useWorkflow`` hook and ``AgentProgressPanel`` component
    work without modification.
    """
    from app.agents.od_runner import run_od_prototype_pipeline
    from app.services.od_loader import get_template, get_design_system

    # Validate IDs up front — avoids starting a WorkflowRun that will fail
    # immediately inside the runner with a LookupError.
    if not template_id or get_template(template_id) is None:
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": f"Unknown template: {template_id!r}", "code": "invalid_template", "recoverable": False},
        })
        return
    if not design_system_id or get_design_system(design_system_id) is None:
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": f"Unknown design system: {design_system_id!r}", "code": "invalid_design_system", "recoverable": False},
        })
        return

    # Create WorkflowRun record for history.
    workflow_run_id = None
    db = _get_db()
    try:
        workflow_run = WorkflowRun(
            user_id=user.id,
            title=(brief or "Prototype")[:60].strip(),
            type="od_prototype",
            status="running",
            input=brief or f"template={template_id} ds={design_system_id}",
            agent_count=4,
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)
        workflow_run_id = workflow_run.id
    finally:
        db.close()

    final_html = ""
    monotonic_start = time.monotonic()
    execution_start = datetime.now(timezone.utc)

    # Collectors for DB persistence (mirrors _handle_pipeline_execution)
    od_agent_outputs_collector: list[dict] = []
    current_od_agent_live: dict = {}
    od_token_summary: dict = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "per_agent": {},
    }

    try:
        async for event in run_od_prototype_pipeline(
            template_id=template_id,
            design_system_id=design_system_id,
            brief=brief,
            discovery=discovery,
        ):
            t = event.get("type")

            if t == "pipeline_start":
                await websocket.send_json({
                    "type": "pipeline_start", "chunk": None, "section": "od_prototype",
                    "data": {
                        "agents": event.get("agents", []),
                        "pipeline_type": "od_prototype",
                    },
                })

            elif t == "agent_start":
                current_od_agent_live = {
                    "agent_id": event.get("agent_id"),
                    "name": event.get("name"),
                    "role": event.get("role"),
                    "icon": event.get("icon"),
                    "output": "",
                    "duration": None,
                }
                await websocket.send_json({
                    "type": "agent_start", "chunk": None, "section": "od_prototype",
                    "data": {
                        "agent_id": event.get("agent_id"),
                        "name": event.get("name"),
                        "role": event.get("role"),
                        "icon": event.get("icon"),
                        "index": event.get("index"),
                    },
                })

            elif t == "agent_chunk":
                current_od_agent_live["output"] = (
                    current_od_agent_live.get("output", "") + event.get("chunk", "")
                )
                await websocket.send_json({
                    "type": "agent_chunk", "chunk": None, "section": "od_prototype",
                    "data": {
                        "agent_id": event.get("agent_id"),
                        "chunk": event.get("chunk", ""),
                    },
                })

            elif t == "agent_complete":
                current_od_agent_live["duration"] = event.get("duration")
                od_agent_outputs_collector.append(current_od_agent_live)
                current_od_agent_live = {}
                await websocket.send_json({
                    "type": "agent_complete", "chunk": None, "section": "od_prototype",
                    "data": {
                        "agent_id": event.get("agent_id"),
                        "duration": event.get("duration"),
                        "output_length": event.get("output_length", 0),
                    },
                })

            elif t == "agent_error":
                current_od_agent_live["error"] = event.get("error", "Agent failed")
                od_agent_outputs_collector.append(current_od_agent_live)
                current_od_agent_live = {}
                await websocket.send_json({
                    "type": "agent_error", "chunk": None, "section": "od_prototype",
                    "data": {
                        "agent_id": event.get("agent_id"),
                        "error": event.get("error", "Agent failed"),
                    },
                })

            elif t == "artifact" and event.get("stage") == "final":
                # Final artifact — store for pipeline_complete; don't emit
                # a separate WS event since the frontend reads final_output
                # from pipeline_complete.data.
                final_html = event.get("html", "")

            elif t == "pipeline_complete":
                if not final_html:
                    final_html = event.get("final_html", "")
                duration = round(time.monotonic() - monotonic_start, 1)
                od_token_summary = {
                    "total_input_tokens": event.get("total_input_tokens", 0),
                    "total_output_tokens": event.get("total_output_tokens", 0),
                    "total_tokens": event.get("total_tokens", 0),
                    "estimated_cost_usd": event.get("estimated_cost_usd", 0.0),
                    "per_agent": event.get("token_usage_per_agent", {}),
                }
                await websocket.send_json({
                    "type": "pipeline_complete", "chunk": None, "section": "od_prototype",
                    "data": {
                        "final_output": final_html,
                        "pipeline_type": "od_prototype",
                        "total_duration": duration,
                        "total_input_tokens": od_token_summary["total_input_tokens"],
                        "total_output_tokens": od_token_summary["total_output_tokens"],
                        "total_tokens": od_token_summary["total_tokens"],
                        "estimated_cost_usd": od_token_summary["estimated_cost_usd"],
                        "token_usage_per_agent": od_token_summary["per_agent"],
                    },
                })

            elif t == "pipeline_error":
                raise RuntimeError(event.get("error", "Pipeline failed"))

    except asyncio.CancelledError:
        duration = round(time.monotonic() - monotonic_start, 1)
        if workflow_run_id:
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    wr.status = "cancelled"
                    wr.completed_at = datetime.now(timezone.utc)
                    wr.duration = duration
                    db.commit()
            finally:
                db.close()
        try:
            await websocket.send_json({
                "type": "pipeline_cancelled", "chunk": None, "section": None,
                "data": {"message": "Pipeline cancelled", "duration": duration},
            })
        except Exception:
            pass
        raise

    except Exception as exc:
        logger.error("OD prototype pipeline error: %s", exc)
        if workflow_run_id:
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    wr.status = "failed"
                    wr.error = str(exc)
                    wr.completed_at = datetime.now(timezone.utc)
                    wr.duration = round((datetime.now(timezone.utc) - execution_start).total_seconds(), 1)
                    db.commit()
            finally:
                db.close()
        try:
            await websocket.send_json({
                "type": "error", "chunk": None, "section": None,
                "data": {"error": f"Pipeline failed: {exc}", "code": "pipeline_error", "recoverable": True},
            })
        except Exception:
            pass
        return

    # Mark complete in DB — write all fields for consistent workflow history.
    if workflow_run_id:
        db = _get_db()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if wr:
                wr.status = "completed"
                wr.output = final_html
                wr.agent_outputs = json.dumps(od_agent_outputs_collector) if od_agent_outputs_collector else None
                wr.token_usage = json.dumps(od_token_summary)
                wr.completed_at = datetime.now(timezone.utc)
                wr.duration = round(time.monotonic() - monotonic_start, 1)
                db.commit()
        finally:
            db.close()


async def _handle_pipeline_execution(
    websocket: WebSocket,
    content: str,
    pipeline_type: str,
    chat_session_id: str,
    token: str,
    user: User,
    agent_ids: list[str] | None = None,
    attached_skills: list[dict] | None = None,
    attached_hooks: list[dict] | None = None,
):
    """Handle a pipeline execution request via WebSocket.

    Runs the full agent pipeline and streams per-agent status updates.
    Creates a WorkflowRun record to track the execution.
    If agent_ids is provided, uses that custom agent list instead of defaults.
    """
    from app.agents.orchestrator_v2 import WorkflowOrchestrator
    from app.agents.registry import (
        SUPPORTED_PIPELINE_TYPES,
        allowed_custom_agent_ids,
    )

    logger.info(f"Pipeline execution: type={pipeline_type}, user={user.id}, custom_agents={len(agent_ids) if agent_ids else 'default'}")

    # --- Input validation (G1-C6) -----------------------------------------
    # Validate BEFORE any DB writes so we don't leave phantom WorkflowRun
    # rows behind when the client sends a bad pipeline_type or a forged
    # agent_ids list. Both checks emit an `error` WS event the frontend can
    # surface to the user, and return without spawning the orchestrator.
    #
    # See docs/_audit/TRIAGE.md G1-C6 for the original mass-assignment
    # write-up — the previous code path (`get_all_agents()` + dict lookup)
    # silently dropped unknown IDs, which is how cross-pipeline injection
    # of e.g. PPT agents into a User Stories run slipped past review.
    if pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        await websocket.send_json({
            "type": "error",
            "chunk": None,
            "section": None,
            "data": {
                "error": f"Unsupported pipeline_type: {pipeline_type!r}",
                "code": "invalid_pipeline_type",
                "recoverable": False,
            },
        })
        return

    # Tier gate — check if user's plan allows this pipeline
    from app.core.entitlements import can_run_pipeline
    allowed, reason = can_run_pipeline(user.tier, pipeline_type)
    if not allowed:
        await websocket.send_json({
            "type": "error",
            "chunk": None,
            "section": None,
            "data": {
                "error": reason,
                "code": "tier_limit",
                "recoverable": False,
                "upgrade_required": True,
            },
        })
        return

    if agent_ids:
        allowed = allowed_custom_agent_ids(pipeline_type)
        rejected = [aid for aid in agent_ids if aid not in allowed]
        if rejected:
            # List the rejected IDs in the message — silently dropping them
            # (which is what `get_all_agents()` filtering did before) is the
            # whole class of bug we're fixing. The client UI should be able
            # to highlight exactly which entries it asked for that the
            # server refused.
            await websocket.send_json({
                "type": "error",
                "chunk": None,
                "section": None,
                "data": {
                    "error": (
                        "Invalid agent_ids for pipeline_type "
                        f"{pipeline_type!r}: {rejected}"
                    ),
                    "code": "invalid_agent_ids",
                    "recoverable": False,
                    "rejected_agent_ids": rejected,
                },
            })
            return

    # Determine agent count
    if agent_ids:
        agent_count = len(agent_ids)
    else:
        agent_counts = {
            "user_stories": 12, "ppt": 4, "prototype": 4, "app_builder": 15,
            "mulesoft_to_springboot": 13, "dotnet_to_azure": 13,
        }
        agent_count = agent_counts.get(pipeline_type, 12)

    # Create a WorkflowRun record
    workflow_run_id = None
    db = _get_db()
    try:
        workflow_run = WorkflowRun(
            user_id=user.id,
            # Placeholder title — overwritten asynchronously by the
            # Bedrock-generated title in _generate_workflow_title below.
            # We strip any pipeline-context markers (=== CONTEXT FROM
            # PREVIOUS PIPELINE ===) before truncating, so even if the
            # async title-gen fails or never lands, the user sees the
            # user-authored prefix of their prompt rather than the
            # injected context block.
            title=(_strip_pipeline_context(content) or content or "Untitled")[:60].strip(),
            type=pipeline_type,
            status="running",
            input=content or f"Run {pipeline_type} pipeline",
            agent_count=agent_count,
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)
        workflow_run_id = workflow_run.id
    finally:
        db.close()

    # Kick off LLM-generated title in the background. The WorkflowRun was
    # just stored with title = first 60 chars of the user's input, which
    # renders as raw / unpolished in the run-history sidebar (e.g.
    # "blockchain" or "make me a deck about quantum compute"). We replace
    # it with a 3-7 word professional title once Bedrock responds. The
    # task runs in parallel with the pipeline — pipeline execution does
    # not block on it, and a failure here only leaves the placeholder
    # title in place (it never breaks the pipeline run).
    if workflow_run_id:
        asyncio.create_task(
            _generate_workflow_title(
                workflow_run_id=workflow_run_id,
                content=content or "",
                pipeline_type=pipeline_type,
                websocket=websocket,
            )
        )

    # Persist user message if chat_session_id provided
    if chat_session_id:
        db = _get_db()
        try:
            chat_session = (
                db.query(ChatSession)
                .filter(ChatSession.id == chat_session_id, ChatSession.user_id == user.id)
                .first()
            )
            if chat_session:
                user_msg = Message(
                    chat_session_id=chat_session_id,
                    role="user",
                    content=content or f"Run {pipeline_type} pipeline",
                )
                db.add(user_msg)
                chat_session.last_activity = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    # Check if Bedrock is configured
    if not (settings.BEDROCK_MODEL_ID and settings.AWS_REGION):
        await websocket.send_json({
            "type": "error",
            "chunk": None,
            "section": None,
            "data": {
                "error": (
                    "Bedrock is not fully configured. Set BEDROCK_MODEL_ID and "
                    "AWS_REGION in backend/.env to run pipelines."
                ),
                "code": "llm_provider_misconfigured",
                "recoverable": False,
            },
        })
        return

    final_output = ""
    pipeline_token_summary: dict = {}
    execution_start = datetime.now(timezone.utc)
    agent_outputs_collector: list[dict] = []  # Collect per-agent thinking/output

    # === LIVE PIPELINE MODE ===
    # If custom agent_ids provided, resolve them to AgentSpec objects from
    # the new slim registry. By the time we reach here, every entry in
    # `agent_ids` is guaranteed to be in the pipeline's allow-list (validated
    # above). The orchestrator handles default agent loading itself when
    # custom_agents=None.
    custom_agent_specs = None
    if agent_ids:
        from agents.loader import load_agent_spec
        custom_agent_specs = []
        for aid in agent_ids:
            try:
                custom_agent_specs.append(load_agent_spec(aid))
            except Exception:
                # Defensive: skip agents that can't be loaded (shouldn't
                # happen since they passed the allow-list check above).
                logger.warning("Could not load AgentSpec for %s — skipping", aid)
        if not custom_agent_specs:
            custom_agent_specs = None

    # Execute the workflow. user_id is forwarded so the orchestrator's
    # _load_skills picks up per-user custom skills (WORKFLOWS.md §B6 —
    # was previously assembled here in the WS handler before we moved
    # skill loading into the orchestrator).
    executor = WorkflowOrchestrator(
        pipeline_type,
        custom_agents=custom_agent_specs,
        user_id=user.id,
        attached_skills=attached_skills or [],
        attached_hooks=attached_hooks or [],
    )

    monotonic_start = time.monotonic()
    try:
        current_agent_output_live: dict = {}
        # Tracks whether the orchestrator emitted any agent_error events
        # during this run. Used after the loop to decide whether to mark
        # the WorkflowRun as `completed` (no errors) or `failed` (one or
        # more agents errored). Without this, a single agent_error in a
        # 12-agent pipeline would still produce status="completed" with
        # garbage final output.
        any_agent_errored = False
        first_agent_error_msg: Optional[str] = None
        async for update in executor.execute(content):
            await websocket.send_json({
                "type": update["type"],
                "chunk": None,
                "section": pipeline_type,
                "data": update["data"],
            })
            # Collect agent outputs for persistence
            if update["type"] == "agent_start":
                current_agent_output_live = {
                    "agent_id": update["data"].get("agent_id"),
                    "name": update["data"].get("name"),
                    "role": update["data"].get("role"),
                    "icon": update["data"].get("icon"),
                    "thinking": "",
                    "output": "",
                    "duration": None,
                }
            elif update["type"] == "agent_thinking":
                # agent_thinking marks the START of an LLM call. The
                # orchestrator re-emits it on each retry attempt (orchestrator_v2
                # retries up to 2x within a single agent without re-emitting
                # agent_start). Reset the chunk buffer here so retries don't
                # accumulate duplicated content into the persisted output.
                current_agent_output_live["thinking"] = update["data"].get("thinking", "")
                current_agent_output_live["output"] = ""
            elif update["type"] == "agent_chunk":
                current_agent_output_live["output"] += update["data"].get("chunk", "")
            elif update["type"] == "agent_complete":
                current_agent_output_live["duration"] = update["data"].get("duration")
                agent_outputs_collector.append(current_agent_output_live)
                current_agent_output_live = {}
            elif update["type"] == "agent_error":
                any_agent_errored = True
                if first_agent_error_msg is None:
                    first_agent_error_msg = update["data"].get("error") or "Agent execution error"
                # Persist what we collected so far for the failed agent
                # too — useful for "show me what the pipeline got through"
                # debugging UX.
                current_agent_output_live["duration"] = update["data"].get("duration")
                current_agent_output_live["error"] = update["data"].get("error")
                agent_outputs_collector.append(current_agent_output_live)
                current_agent_output_live = {}
            elif update["type"] == "pipeline_complete":
                final_output = update["data"].get("final_output", "")
                # Capture pipeline-level token totals for DB persistence
                pipeline_token_summary = {
                    "total_input_tokens": update["data"].get("total_input_tokens", 0),
                    "total_output_tokens": update["data"].get("total_output_tokens", 0),
                    "total_tokens": update["data"].get("total_tokens", 0),
                    "estimated_cost_usd": update["data"].get("estimated_cost_usd", 0.0),
                    "per_agent": update["data"].get("token_usage_per_agent", {}),
                }
    except asyncio.CancelledError:
        # Cooperative cancellation from cancel_pipeline (or WebSocketDisconnect
        # cleanup). The async generator's CancelledError propagates here from
        # the LLM stream; everything below is the A6 fix — without it the
        # WorkflowRun row stays at status="running" forever.
        duration = round(time.monotonic() - monotonic_start, 1)
        logger.info(
            "Pipeline cancelled by user — workflow_run_id=%s agents_completed=%d duration=%.1fs",
            workflow_run_id, len(agent_outputs_collector), duration,
        )
        if workflow_run_id:
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    wr.status = "cancelled"
                    wr.completed_at = datetime.now(timezone.utc)
                    wr.duration = duration
                    # Persist whatever partial output we collected — useful
                    # for "show me what the pipeline got through" UX, and
                    # avoids losing finished agents' work.
                    if agent_outputs_collector:
                        wr.agent_outputs = json.dumps(agent_outputs_collector)
                    db.commit()
            finally:
                db.close()
        # Best-effort ack; the WS may already be closed (e.g. user closed the
        # tab → WebSocketDisconnect → cleanup cancelled us).
        try:
            await websocket.send_json({
                "type": "pipeline_cancelled",
                "chunk": None,
                "section": None,
                "data": {
                    "message": "Pipeline cancelled by user",
                    "agents_completed": len(agent_outputs_collector),
                    "duration": duration,
                },
            })
        except Exception:
            pass
        # Re-raise so the asyncio scheduler finalises this task as
        # `cancelled` (not `done`). Anything that introspects task state
        # later (`task.cancelled()`) depends on this re-raise.
        raise
    except Exception as e:
        logger.error(f"Pipeline execution error: {e}")
        # Persist the failure FIRST. If we sent over the WS first and the
        # client was already disconnected (the most common trigger of an
        # `except Exception` here), the send_json would re-raise and skip
        # the DB write — leaving WorkflowRun rows at `status="running"`
        # forever. Doing the DB commit before the best-effort send is
        # order-of-operations: durable state, then notify.
        if workflow_run_id:
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    wr.status = "failed"
                    wr.error = str(e)
                    wr.completed_at = datetime.now(timezone.utc)
                    duration = (datetime.now(timezone.utc) - execution_start).total_seconds()
                    wr.duration = round(duration, 1)
                    db.commit()
            finally:
                db.close()
        # Best-effort error event. Swallow send errors — the row is already
        # marked failed, and a disconnected client can't be told anyway.
        try:
            await websocket.send_json({
                "type": "error",
                "chunk": None,
                "section": None,
                "data": {
                    "error": f"Pipeline execution failed: {str(e)}",
                    "code": "pipeline_error",
                    "recoverable": True,
                },
            })
        except Exception:
            logger.info("Failed to notify client of pipeline failure — WS likely closed.")
        return

    # Persist terminal state. If any agent emitted `agent_error` during the
    # run, mark the WorkflowRun `failed` rather than `completed` — leaving
    # it `completed` would mislead history UIs and downstream consumers
    # that branch on `status` (e.g. "show retry" affordances). The final
    # output is still persisted because the orchestrator continues running
    # subsequent agents after a recoverable error, and the user may want
    # to see whatever was produced.
    if workflow_run_id:
        db = _get_db()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if wr:
                if any_agent_errored:
                    wr.status = "failed"
                    wr.error = first_agent_error_msg
                else:
                    wr.status = "completed"
                wr.output = final_output if final_output else None
                wr.agent_outputs = json.dumps(agent_outputs_collector) if agent_outputs_collector else None
                wr.token_usage = json.dumps(pipeline_token_summary) if pipeline_token_summary else None
                wr.completed_at = datetime.now(timezone.utc)
                duration = (datetime.now(timezone.utc) - execution_start).total_seconds()
                wr.duration = round(duration, 1)
                db.commit()
        finally:
            db.close()

    # Persist the final output as assistant message.
    #
    # `chat_session_id` arrives from the client over the WS. The earlier
    # user-message persistence path (around :514-518) already filters on
    # `ChatSession.user_id == user.id`; this assistant-message write
    # previously did NOT, which let an authenticated user persist messages
    # into another user's session by guessing the session UUID. We now do
    # the ownership check up-front and bail without writing if the session
    # doesn't belong to `user`.
    if final_output and chat_session_id:
        db = _get_db()
        try:
            chat_session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.id == chat_session_id,
                    ChatSession.user_id == user.id,
                )
                .first()
            )
            if chat_session is None:
                logger.warning(
                    "Skipping assistant-message persistence: chat_session %s not owned by user %s",
                    chat_session_id, user.id,
                )
            else:
                if pipeline_type == "ppt":
                    summary = "\u2705 **Presentation generated!** Check the Preview panel \u2192 PPT tab."
                elif pipeline_type == "prototype":
                    summary = "\u2705 **Prototype generated!** Check the Preview panel \u2192 Prototype tab."
                else:
                    summary = final_output[:500]

                assistant_msg = Message(
                    chat_session_id=chat_session_id,
                    role="assistant",
                    content=summary,
                )
                db.add(assistant_msg)
                chat_session.last_activity = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()


async def _handle_questionnaire(websocket: WebSocket, prompt: str, pipeline_type: str):
    """Generate clarifying MCQ questions based on the user's prompt and pipeline type.

    Uses the questionnaire agent to produce 4 targeted questions.
    Sends the questions back as a 'questionnaire' WebSocket message.
    """
    from app.agents.base import BaseAgent, AgentConfigurationError
    from app.agents.registry import QUESTIONNAIRE_AGENT

    logger.info(f"Generating questionnaire: pipeline_type={pipeline_type}, prompt={prompt[:50]}")

    try:
        agent = BaseAgent(
            system_prompt=QUESTIONNAIRE_AGENT.system_prompt,
            max_tokens=QUESTIONNAIRE_AGENT.max_tokens,
        )

        context_message = f"Pipeline type: {pipeline_type}\nUser's idea: {prompt}"
        response = await agent.run(context_message)

        # Try to parse JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            questions_data = json.loads(json_match.group())
            await websocket.send_json({
                "type": "questionnaire",
                "chunk": None,
                "section": None,
                "data": questions_data,
            })
        else:
            # Fallback — couldn't parse questions, skip questionnaire
            await websocket.send_json({
                "type": "questionnaire",
                "chunk": None,
                "section": None,
                "data": {"questions": []},
            })

    except AgentConfigurationError:
        # No API key — skip questionnaire
        await websocket.send_json({
            "type": "questionnaire",
            "chunk": None,
            "section": None,
            "data": {"questions": []},
        })
    except Exception as e:
        logger.error(f"Questionnaire generation error: {e}")
        await websocket.send_json({
            "type": "questionnaire",
            "chunk": None,
            "section": None,
            "data": {"questions": []},
        })

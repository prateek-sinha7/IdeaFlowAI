"""REST routes of the AI Workflow Builder (design section 3.2.1).

Thin handlers under ``/api/workflow-builder``. Every route depends on
:func:`~app.api.workflow_builder.admission.require_builder_access`, which runs
checks 1, 3 and 4 (authentication, the custom entitlement, readiness) before
any lookup. ``GET /sessions/{id}/events`` lives in ``stream.py``.

Authorisation key: ``user_id``. A session that is missing and a session that
belongs to someone else both answer 404 ``session_not_found``. A workflow the
caller does not own, or that does not exist, answers 404 ``workflow_not_found``
[pending G-07].

Handlers that publish an event or stop a Turn are ``async``: the event bus and
``asyncio.Task.cancel`` are not thread-safe, so they run on the event loop and
send their blocking store calls to a worker thread. The others are plain ``def``
handlers, which FastAPI runs in its thread pool.

Logs carry ids and counts only, never message text or ``canvas_state``.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DbSession

from agents.capabilities.model_catalog import ModelCatalog
from app.agents.workflow_builder.canonical import canonical_hash
from app.agents.workflow_builder.events import DraftRestored, SessionDeleted
from app.agents.workflow_builder.model_catalog_view import (
    builder_models,
    check_chat_choice,
)
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.skill_package import read_skill_facts
from app.agents.workflow_builder.transcript import skill_updated_flags
from app.api.capabilities import project_model_entry
from app.api.run_commands import _reject  # noqa: PLC2701 - the shared error shape
from app.api.run_engine import _saved_row_trust  # noqa: PLC2701 - same trust as launch
from app.api.workflow_builder.admission import (
    BuilderAccess,
    CapacityGate,
    TurnStarter,
    _session_not_found,  # noqa: PLC2701 - one 404 shape for the whole API
    _turn_running,  # noqa: PLC2701 - one 409 shape for the whole API
    admit_message,
    admit_retry,
    get_admission_clock,
    get_capacity_gate,
    get_turn_starter,
    require_builder_access,
)
from app.api.workflow_builder.schemas import (
    ActivitySummary,
    BuilderModelsResponse,
    ChangeSummary,
    CreateSessionRequest,
    DraftRevisionOut,
    ErrorOut,
    LaunchNeed,
    LinkRequest,
    SendMessageRequest,
    SessionDetail,
    SessionPage,
    SessionSummary,
    ToolActivityOut,
    TranscriptMessage,
    TurnAccepted,
    UndoRequest,
)
from app.api.workflow_builder.store import (
    BuilderStore,
    InvalidCursorError,
    SessionNotFoundError,
    get_builder_store,
)
from app.api.workflow_builder.turns import (
    build_snapshot,
    cancel_turn,
    get_event_bus,
    get_live_turn,
    stop_session_turn,
)
from app.models.database import get_db
from app.models.workflow_builder import (
    DRAFT_KIND_ACCEPTED,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_FAILED,
    SESSION_MODE_CREATE,
    SESSION_MODE_EDIT,
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)
from app.models.workflow_definition import WorkflowDefinition

__all__ = ["effective_manifest", "router"]

logger = logging.getLogger("app.api.workflow_builder.routes")

router = APIRouter(prefix="/api/workflow-builder", tags=["workflow-builder"])

_CUSTOM_PIPELINE: Final = "custom"
_NEW_SESSION_TITLE: Final = "New conversation"
_EDIT_TITLE_MAX: Final = 60
_SANDBOX_WAIT_SECONDS: Final = 5.0
_GENERIC_ERROR_MESSAGE: Final = "The reply could not be completed."
# Launch-path fallbacks for the keys a canvas manifest never carries
# (``run_commands`` USER_WORKFLOW_MANIFEST branch).
_DEFAULT_DELIVERABLE: Final = {"strategy": "streamed_text", "name": "output.md"}
_DEFAULT_PLANNER: Final = "skip"
_DEFAULT_CLARIFY: Final = {"mode": "skip", "defaults": []}


# --- Errors ----------------------------------------------------------------------------


def _workflow_not_found() -> Exception:
    return _reject(
        "workflow_not_found",
        "Workflow not found.",
        http_status=status.HTTP_404_NOT_FOUND,
    )


def _bad_cursor() -> Exception:
    return _reject(
        "invalid_cursor",
        "The page cursor is not valid.",
        http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


# --- Saved workflows -------------------------------------------------------------------


def _owned_workflow(
    db: DbSession, user_id: str, workflow_id: str
) -> WorkflowDefinition:
    """Return the caller's saved workflow or raise 404 ``workflow_not_found``."""
    row = (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.user_id == user_id,
            WorkflowDefinition.source == "user",
        )
        .first()
    )
    if row is None:
        raise _workflow_not_found()
    return row


def _base_pipeline_defaults(base_pipeline_type: str) -> dict[str, Any]:
    """``deliverable``, ``planner`` and ``clarify`` declared by a built-in pipeline.

    Returns an empty mapping when the manifest cannot be read, so the launch-path
    fallbacks apply.
    """
    from agents.execution_engine.engine import _WORKFLOWS_DIR  # noqa: PLC0415, PLC2701
    from agents.workflows.manifest import load_manifest  # noqa: PLC0415

    try:
        base = load_manifest(base_pipeline_type, _WORKFLOWS_DIR)
    except Exception:  # noqa: BLE001 - any unreadable base falls back to defaults
        logger.warning("base manifest unreadable base=%s", base_pipeline_type)
        return {}
    return {
        "deliverable": copy.deepcopy(base.deliverable),
        "planner": base.planner,
        "clarify": copy.deepcopy(base.clarify),
    }


def effective_manifest(row: WorkflowDefinition) -> dict[str, Any]:
    """The manifest the builder starts from for a saved workflow (Req 20.15).

    A step manifest in ``manifest_json`` is used as stored. A row without one
    (no manifest yet, or a compact selections map) starts from an empty canvas,
    ``{"steps": []}``. For a base that is not ``custom``, ``deliverable``,
    ``planner`` and ``clarify`` are copied from the base pipeline's manifest when
    the row lacks them [pending open decision, see ``open-decisions.md``].
    """
    stored = row.manifest_json
    manifest: dict[str, Any] = (
        copy.deepcopy(stored)
        if isinstance(stored, dict) and "steps" in stored
        else {"steps": []}
    )
    base = row.base_pipeline_type
    if base and base != _CUSTOM_PIPELINE:
        defaults = _base_pipeline_defaults(str(base))
        for key in ("deliverable", "planner", "clarify"):
            if key not in manifest and key in defaults:
                manifest[key] = defaults[key]
    return manifest


def _linked_row_changed(db: DbSession, session: WorkflowBuilderSession) -> bool:
    """True when the linked row's manifest hash differs from the stored one (G-24)."""
    if session.workflow_id is None or session.linked_manifest_hash is None:
        return False
    row = (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.id == session.workflow_id,
            WorkflowDefinition.user_id == session.user_id,
        )
        .first()
    )
    if row is None:
        return False
    return canonical_hash(effective_manifest(row)) != session.linked_manifest_hash


# --- Skill hash ------------------------------------------------------------------------


def _current_skill_hash() -> str:
    """The hash of the builder skill a new session starts with (Req 20.1)."""
    try:
        return read_skill_facts().skill_hash
    except OSError:
        logger.warning("builder skill could not be read", exc_info=True)
        raise _reject(
            "builder_unavailable",
            "The workflow builder is not available right now.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            recoverable=False,
        ) from None


# --- Row to schema ---------------------------------------------------------------------


def _revision_out(draft: WorkflowBuilderDraft) -> DraftRevisionOut:
    summary = draft.change_summary
    needs = draft.launch_needs
    return DraftRevisionOut(
        revision=int(draft.revision),  # type: ignore[arg-type]
        kind=draft.kind,  # type: ignore[arg-type]
        manifest=draft.manifest,  # type: ignore[arg-type]
        target_trust=draft.target_trust,  # type: ignore[arg-type]
        change_summary=(
            ChangeSummary.model_validate(summary) if isinstance(summary, dict) else None
        ),
        launch_needs=[LaunchNeed.model_validate(n) for n in needs or []],  # type: ignore[union-attr]
        source_turn_id=draft.source_turn_id,  # type: ignore[arg-type]
        created_at=draft.created_at,  # type: ignore[arg-type]
    )


def _summary_out(session: WorkflowBuilderSession) -> SessionSummary:
    return SessionSummary(
        id=str(session.id),
        title=str(session.title),
        mode=session.mode,  # type: ignore[arg-type]
        workflow_id=session.workflow_id,  # type: ignore[arg-type]
        model_id=str(session.model_id or ""),
        effort=session.effort,  # type: ignore[arg-type]
        running=get_live_turn(str(session.id)) is not None,
        created_at=session.created_at,  # type: ignore[arg-type]
        updated_at=session.updated_at,  # type: ignore[arg-type]
    )


def _tool_activity(row: WorkflowBuilderMessage) -> ToolActivityOut:
    tool = row.tool if isinstance(row.tool, dict) else {}
    return ToolActivityOut(
        call_id=str(tool.get("call_id", row.id)),
        tool=str(tool.get("tool", "")),
        kind=tool.get("kind", "read"),
        label=str(tool.get("label", "")),
        status=row.status,  # type: ignore[arg-type]
        duration_ms=tool.get("duration_ms"),
        command=tool.get("command"),
        exit_code=tool.get("exit_code"),
        summary=tool.get("summary"),
    )


def _activity_summary(
    row: WorkflowBuilderMessage, activity: list[ToolActivityOut]
) -> ActivitySummary:
    started, ended = row.started_at, row.ended_at
    duration_ms = 0
    if started is not None and ended is not None:
        duration_ms = max(0, int((ended - started).total_seconds() * 1000))  # type: ignore[operator]
    return ActivitySummary(
        actions=len(activity),
        checks=sum(1 for a in activity if a.kind == "propose"),
        duration_ms=duration_ms,
    )


def _transcript(rows: Iterable[WorkflowBuilderMessage]) -> list[TranscriptMessage]:
    """User and assistant rows in order, each assistant row with its tool rows."""
    ordered = sorted(rows, key=lambda r: int(r.seq))  # type: ignore[arg-type]
    tools: dict[str, list[WorkflowBuilderMessage]] = defaultdict(list)
    for row in ordered:
        if row.role == MESSAGE_ROLE_TOOL:
            tools[str(row.turn_id)].append(row)
    updated = skill_updated_flags(ordered)  # type: ignore[arg-type]
    messages: list[TranscriptMessage] = []
    for row in ordered:
        if row.role not in (MESSAGE_ROLE_USER, MESSAGE_ROLE_ASSISTANT):
            continue
        is_assistant = row.role == MESSAGE_ROLE_ASSISTANT
        activity = (
            [_tool_activity(t) for t in tools.get(str(row.turn_id), [])]
            if is_assistant
            else []
        )
        error = (
            ErrorOut(
                code=str(row.error_code),
                message=_GENERIC_ERROR_MESSAGE,
                retryable=row.status == MESSAGE_STATUS_FAILED,
            )
            if row.error_code
            else None
        )
        messages.append(
            TranscriptMessage(
                id=str(row.id),
                seq=int(row.seq),  # type: ignore[arg-type]
                role=row.role,  # type: ignore[arg-type]
                turn_id=str(row.turn_id),
                reply_to_message_id=row.reply_to_message_id,  # type: ignore[arg-type]
                status=row.status,  # type: ignore[arg-type]
                outcome=row.outcome,  # type: ignore[arg-type]
                stop_reason=row.stop_reason,  # type: ignore[arg-type]
                content=str(row.content or ""),
                thinking=row.thinking,  # type: ignore[arg-type]
                model_id=str(row.model_id or ""),
                effort=row.effort,  # type: ignore[arg-type]
                skill_hash=row.skill_hash,  # type: ignore[arg-type]
                skill_updated=updated.get(str(row.id), False),
                error=error,
                revision=row.revision,  # type: ignore[arg-type]
                activity=activity,
                activity_summary=(
                    _activity_summary(row, activity) if is_assistant else None
                ),
                created_at=row.created_at,  # type: ignore[arg-type]
                ended_at=row.ended_at,  # type: ignore[arg-type]
            )
        )
    return messages


def _detail(
    store: BuilderStore, db: DbSession, session: WorkflowBuilderSession
) -> SessionDetail:
    user_id, session_id = str(session.user_id), str(session.id)
    revisions = store.get_latest_revisions(user_id, session_id)
    drafts = [r for r in (revisions.seed, revisions.accepted, revisions.undo) if r]
    latest_draft = max(drafts, key=lambda r: int(r.revision), default=None)  # type: ignore[arg-type]
    unproposed = revisions.unproposed
    newer_unproposed = unproposed is not None and (
        latest_draft is None or int(unproposed.revision) > int(latest_draft.revision)  # type: ignore[arg-type]
    )
    snapshot = build_snapshot(session_id, user_id=user_id, store=store)
    base = _summary_out(session)
    return SessionDetail(
        **base.model_dump(),
        target_trust=session.target_trust,  # type: ignore[arg-type]
        skill_hash=str(session.skill_hash),
        messages=_transcript(store.list_messages(user_id, session_id)),
        latest_draft=_revision_out(latest_draft) if latest_draft else None,
        latest_unproposed=(
            _revision_out(unproposed) if unproposed and newer_unproposed else None
        ),
        running_turn=snapshot.running_turn,
        linked_row_changed=_linked_row_changed(db, session),
    )


def _require_session(
    store: BuilderStore, access: BuilderAccess, session_id: str
) -> WorkflowBuilderSession:
    session = store.get_session(str(access.user.id), session_id)
    if session is None:
        raise _session_not_found()
    return session


# --- Models ----------------------------------------------------------------------------


@router.get("/models", response_model=BuilderModelsResponse)
def list_models(
    access: BuilderAccess = Depends(require_builder_access),
) -> BuilderModelsResponse:
    """The Chat_List for this user, the default model and each default effort."""
    preferred = getattr(access.user, "preferred_model", None)
    view = builder_models(access.tier, preferred)
    return BuilderModelsResponse(
        models=[project_model_entry(entry) for entry in view.chat],
        default_model_id=view.default_chat_id,
        default_efforts={
            entry.id: entry.reasoning.default_effort for entry in view.chat
        },
    )


# --- Sessions --------------------------------------------------------------------------


@router.post(
    "/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionDetail
)
def create_session(
    body: CreateSessionRequest,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
    db: DbSession = Depends(get_db),
) -> SessionDetail:
    """Create a session. Edit mode checks ownership and stores revision 0."""
    user_id = str(access.user.id)
    refusal = check_chat_choice(
        ModelCatalog().list(),
        builder_models(access.tier),
        body.model_id,
        body.effort,
    )
    if refusal is not None:
        raise _reject(refusal.code, refusal.message, http_status=refusal.status_code)

    kwargs: dict[str, Any] = {
        "title": _NEW_SESSION_TITLE,
        "mode": SESSION_MODE_CREATE,
        "model_id": body.model_id,
        "effort": body.effort,
    }
    if body.mode == "edit":
        row = _owned_workflow(db, user_id, str(body.workflow_id))
        manifest = effective_manifest(row)
        manifest_hash = canonical_hash(manifest)
        kwargs.update(
            title=f"Edit: {row.name}"[:_EDIT_TITLE_MAX],
            mode=SESSION_MODE_EDIT,
            workflow_id=str(row.id),
            linked_manifest_hash=manifest_hash,
            target_trust=_saved_row_trust(access.tier),
            seed_manifest=manifest,
            seed_manifest_hash=manifest_hash,
        )
    session = store.create_session(user_id, skill_hash=_current_skill_hash(), **kwargs)
    logger.info("builder session created session=%s mode=%s", session.id, body.mode)
    return _detail(store, db, session)


@router.get("/sessions", response_model=SessionPage)
def list_sessions(
    cursor: str | None = Query(default=None, max_length=512),
    limit: int | None = Query(default=None, ge=1),
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
) -> SessionPage:
    """The caller's sessions, newest activity first (keyset pagination)."""
    try:
        page = store.list_sessions(str(access.user.id), limit=limit, cursor=cursor)
    except InvalidCursorError as exc:
        raise _bad_cursor() from exc
    return SessionPage(
        items=[_summary_out(s) for s in page.items], next_cursor=page.next_cursor
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
    db: DbSession = Depends(get_db),
) -> SessionDetail:
    """Metadata, transcript, drafts, the running-turn snapshot and the link note."""
    return _detail(store, db, _require_session(store, access, session_id))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
) -> Response:
    """Stop any running turn, delete the rows and the sandbox, close the streams."""
    user_id = str(access.user.id)
    await asyncio.to_thread(_require_session, store, access, session_id)

    live = get_live_turn(session_id)
    if stop_session_turn(session_id, "deleted") and live is not None and live.task:
        # Let the turn unwind so it does not write into rows that are going away.
        await asyncio.wait({live.task}, timeout=_SANDBOX_WAIT_SECONDS)

    deleted = await asyncio.to_thread(store.delete_session, user_id, session_id)
    if deleted:
        await asyncio.to_thread(BuilderSandbox(user_id, session_id).delete_session)
    get_event_bus().close_session(session_id, SessionDeleted(ts=datetime.now(UTC)))
    logger.info("builder session deleted session=%s", session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/link", response_model=SessionSummary)
def link_session(
    session_id: str,
    body: LinkRequest,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
    db: DbSession = Depends(get_db),
) -> SessionSummary:
    """Link the session to a saved workflow the caller owns (Req 2.9, 2.10)."""
    user_id = str(access.user.id)
    _require_session(store, access, session_id)
    row = _owned_workflow(db, user_id, body.workflow_id)
    try:
        session = store.link_session(
            user_id,
            session_id,
            workflow_id=str(row.id),
            linked_manifest_hash=canonical_hash(effective_manifest(row)),
        )
    except SessionNotFoundError as exc:
        raise _session_not_found() from exc
    return _summary_out(session)


# --- Turns -----------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TurnAccepted,
)
async def send_message(  # noqa: PLR0913 - every collaborator is a dependency
    session_id: str,
    body: SendMessageRequest,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
    start_turn: TurnStarter = Depends(get_turn_starter),
    capacity_gate: CapacityGate = Depends(get_capacity_gate),
    clock: Callable[[], datetime] = Depends(get_admission_clock),
) -> TurnAccepted:
    """Send a message: checks 6 to 16 of design 3.1.2, then start the turn."""
    return await admit_message(
        store=store,
        access=access,
        session_id=session_id,
        body=body,
        start_turn=start_turn,
        capacity_gate=capacity_gate,
        clock=clock,
    )


@router.post(
    "/sessions/{session_id}/turns/{turn_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TurnAccepted,
)
async def retry_turn(  # noqa: PLR0913 - every collaborator is a dependency
    session_id: str,
    turn_id: str,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
    start_turn: TurnStarter = Depends(get_turn_starter),
    capacity_gate: CapacityGate = Depends(get_capacity_gate),
    clock: Callable[[], datetime] = Depends(get_admission_clock),
) -> TurnAccepted:
    """Retry the latest failed turn on its stored user message [pending G-01]."""
    return await admit_retry(
        store=store,
        access=access,
        session_id=session_id,
        turn_id=turn_id,
        start_turn=start_turn,
        capacity_gate=capacity_gate,
        clock=clock,
    )


@router.post("/sessions/{session_id}/turns/{turn_id}/cancel")
async def cancel_turn_route(
    session_id: str,
    turn_id: str,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
) -> JSONResponse:
    """Cancel the running turn: 202 ``cancelling``, or 200 ``not_running`` [G-35]."""
    await asyncio.to_thread(_require_session, store, access, session_id)
    live = get_live_turn(session_id)
    if live is not None and live.user_id != str(access.user.id):
        return JSONResponse({"state": "not_running"}, status_code=status.HTTP_200_OK)
    state = cancel_turn(session_id, turn_id)
    code = status.HTTP_202_ACCEPTED if state == "cancelling" else status.HTTP_200_OK
    return JSONResponse({"state": state}, status_code=code)


# --- Undo ------------------------------------------------------------------------------


def _undo_blocking(
    store: BuilderStore, access: BuilderAccess, session_id: str, expected: int
) -> DraftRevisionOut:
    """Check staleness and store the ``undo`` revision. Blocking."""
    user_id = str(access.user.id)
    _require_session(store, access, session_id)
    if store.get_running_turn(user_id, session_id) is not None:
        raise _turn_running()

    stale = _reject(
        "undo_stale",
        "The canvas changed since that update, so it cannot be undone.",
        http_status=status.HTTP_409_CONFLICT,
    )
    revisions = store.get_latest_revisions(user_id, session_id)
    candidates = [
        r
        for r in (
            revisions.seed,
            revisions.accepted,
            revisions.undo,
            revisions.unproposed,
        )
        if r is not None
    ]
    latest = max(candidates, key=lambda r: int(r.revision), default=None)  # type: ignore[arg-type]
    if (
        latest is None
        or int(latest.revision) != expected  # type: ignore[arg-type]
        or latest.kind != DRAFT_KIND_ACCEPTED
        or not latest.source_turn_id
    ):
        raise stale
    assistant = store.get_message(user_id, str(latest.source_turn_id))
    starter = (
        store.get_message(user_id, str(assistant.reply_to_message_id))
        if assistant is not None and assistant.reply_to_message_id
        else None
    )
    restored = starter.canvas_state if starter is not None else None
    if not isinstance(restored, dict):
        raise stale

    row = store.insert_revision(
        user_id,
        session_id,
        kind="undo",
        manifest=restored,
        manifest_hash=canonical_hash(restored),
        source_turn_id=str(latest.source_turn_id),
        undo_of_revision=expected,
    )
    return _revision_out(row)


@router.post("/sessions/{session_id}/undo", response_model=DraftRevisionOut)
async def undo(
    session_id: str,
    body: UndoRequest,
    access: BuilderAccess = Depends(require_builder_access),
    store: BuilderStore = Depends(get_builder_store),
) -> DraftRevisionOut:
    """Restore the canvas state that started the latest AI change [pending G-16]."""
    if get_live_turn(session_id) is not None:
        await asyncio.to_thread(_require_session, store, access, session_id)
        raise _turn_running()
    revision = await asyncio.to_thread(
        _undo_blocking, store, access, session_id, body.expected_revision
    )
    get_event_bus().publish(
        session_id,
        DraftRestored(
            ts=datetime.now(UTC),
            revision=revision.revision,
            manifest=revision.manifest,
        ),
    )
    logger.info("builder undo session=%s revision=%d", session_id, revision.revision)
    return revision

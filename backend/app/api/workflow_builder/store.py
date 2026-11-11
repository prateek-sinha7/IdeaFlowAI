"""Session_Store repository for the AI Workflow Builder (design §4, §3.1.2).

A concrete, synchronous SQLAlchemy repository over the three builder tables
(``workflow_builder_sessions``, ``workflow_builder_messages``,
``workflow_builder_drafts``). Rules it enforces:

- Every query filters on ``user_id`` (the authorisation key, Req 2.6, 24.7).
  A missing or foreign row looks the same to the caller: ``None``/``False`` from
  reads, ``SessionNotFoundError`` from mutations. The only queries without a
  ``user_id`` filter are the two startup-sweep methods, which act on every
  user's stale rows by design (Req 21.9, design §3.1.6).
- ``owner_id`` and ``workspace_id`` are stamped with ``user_id`` on insert
  [pending G-37].
- Every public mutating method is one transaction: it commits on success and
  rolls back on any error.
- ORM rows are returned as they are (``expire_on_commit=False`` on the
  application session factory keeps them readable after the commit).

Public interface (``InMemoryBuilderStore`` in ``tests/fakes/builder_store.py``
mirrors exactly this list; ``user_id`` is always the first argument unless noted)::

    Sessions
      create_session(user_id, *, title, mode, skill_hash, workflow_id=None,
                     linked_manifest_hash=None, model_id=None, effort=None,
                     target_trust="user", seed_manifest=None,
                     seed_manifest_hash=None) -> WorkflowBuilderSession
      get_session(user_id, session_id) -> WorkflowBuilderSession | None
      list_sessions(user_id, *, limit=None, cursor=None) -> SessionPage
      delete_session(user_id, session_id) -> bool

    Messages
      begin_turn(user_id, session_id, *, content, canvas_state, client_message_id,
                 model_id, effort, skill_hash, prompt_version=None,
                 first_message_title=None) -> BegunTurn
      begin_retry(user_id, session_id, user_message_id, *, model_id, effort,
                  skill_hash, prompt_version=None) -> BegunTurn
      link_session(user_id, session_id, *, workflow_id, linked_manifest_hash)
                         -> WorkflowBuilderSession
      insert_tool_row(user_id, session_id, turn_id, *, status, content, tool,
                      started_at=None, ended_at=None) -> WorkflowBuilderMessage
      finalize_assistant(user_id, turn_id, *, status, outcome=None,
                         stop_reason=None, error_code=None, content="",
                         thinking=None, steps=None, usage=None, adherence=None,
                         revision=None, ended_at=None)
                         -> WorkflowBuilderMessage | None
      get_message(user_id, message_id) -> WorkflowBuilderMessage | None
      find_user_message_by_client_id(user_id, session_id, client_message_id)
                         -> WorkflowBuilderMessage | None
      list_messages(user_id, session_id, *, after_seq=None)
                         -> list[WorkflowBuilderMessage]
      list_tool_rows(user_id, turn_id) -> list[WorkflowBuilderMessage]
      get_running_turn(user_id, session_id) -> WorkflowBuilderMessage | None
      get_latest_message(user_id, session_id) -> WorkflowBuilderMessage | None

    Revisions
      insert_revision(user_id, session_id, *, kind, manifest, manifest_hash,
                      target_trust=None, change_summary=None, launch_needs=None,
                      source_turn_id=None, source_file=None,
                      undo_of_revision=None) -> WorkflowBuilderDraft
      get_latest_revision(user_id, session_id, kind) -> WorkflowBuilderDraft | None
      get_latest_revisions(user_id, session_id) -> LatestRevisions

    Summary and clarify count
      get_summary(user_id, session_id) -> SummaryState | None
      set_summary(user_id, session_id, *, text, through_seq) -> None
      get_clarify_count(user_id, session_id) -> int | None
      set_clarify_count(user_id, session_id, count) -> None

    Admission counts (the caller owns the clock and passes ``since``)
      count_user_messages_since(user_id, since) -> int
      oldest_user_message_since(user_id, since) -> datetime | None
      count_running_turns(user_id) -> int

    Success metric facts (read-only, user-scoped)
      list_session_metric_facts(user_id) -> list[SessionFact]
      list_turn_gate_facts(user_id) -> list[TurnGateFact]

    Startup sweep and storage report (no ``user_id``: acts on every user)
      list_running_assistant_rows() -> list[WorkflowBuilderMessage]
      mark_running_interrupted(*, ended_at=None) -> int
      storage_usage_by_user() -> list[UserStorageRows]

Module-level helpers shared with the fake: ``DEFAULT_SESSION_PAGE_SIZE``,
``MAX_SESSION_PAGE_SIZE``, ``clamp_page_size``, ``encode_cursor``,
``decode_cursor``, ``SessionPage``, ``BegunTurn``, ``LatestRevisions``,
``SummaryState``, ``UserStorageRows``, ``PROPOSE_DRAFT_TOOL`` and the
exceptions below.

Domain errors the admission layer maps: ``SessionNotFoundError`` (404
``session_not_found``), ``TurnRunningError`` (409 ``turn_running``),
``DuplicateClientMessageError`` (202 replay, Req 21.10) and
``InvalidCursorError`` (422).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends
from sqlalchemy import Text, and_, cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.agents.workflow_builder.success_metrics import SessionFact, TurnGateFact
from app.models.database import get_db
from app.models.workflow_builder import (
    DRAFT_KIND_ACCEPTED,
    DRAFT_KIND_SEED,
    DRAFT_KIND_UNDO,
    DRAFT_KIND_UNPROPOSED,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_CANCELLED,
    MESSAGE_STATUS_COMPLETED,
    MESSAGE_STATUS_FAILED,
    MESSAGE_STATUS_INTERRUPTED,
    MESSAGE_STATUS_RUNNING,
    MESSAGE_STATUS_TIMED_OUT,
    MESSAGE_STATUS_TOOL_ERROR,
    MESSAGE_STATUS_TOOL_OK,
    MESSAGE_STATUS_TOOL_REFUSED,
    MESSAGE_STATUS_TOOL_STOPPED,
    MESSAGE_STATUS_USER_ACCEPTED,
    SESSION_MODE_CREATE,
    SESSION_MODE_EDIT,
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)

# Session list page size [pending G-24].
DEFAULT_SESSION_PAGE_SIZE = 20
MAX_SESSION_PAGE_SIZE = 50

# Value of ``tool["tool"]`` on the tool row of a ``propose_draft`` call (design §4.3).
PROPOSE_DRAFT_TOOL = "propose_draft"

_UNIQUE_CLIENT_ID_INDEX = "uq_wb_messages_client_id"
_UNIQUE_RUNNING_INDEX = "uq_wb_messages_one_running"

_SESSION_MODES = frozenset({SESSION_MODE_CREATE, SESSION_MODE_EDIT})
_ASSISTANT_FINAL_STATUSES = frozenset(
    {
        MESSAGE_STATUS_COMPLETED,
        MESSAGE_STATUS_FAILED,
        MESSAGE_STATUS_CANCELLED,
        MESSAGE_STATUS_TIMED_OUT,
        MESSAGE_STATUS_INTERRUPTED,
    }
)
_TOOL_STATUSES = frozenset(
    {
        MESSAGE_STATUS_TOOL_OK,
        MESSAGE_STATUS_TOOL_ERROR,
        MESSAGE_STATUS_TOOL_REFUSED,
        MESSAGE_STATUS_TOOL_STOPPED,
        MESSAGE_STATUS_TIMED_OUT,
    }
)
# ``seed`` is written only by ``create_session`` (revision 0).
_INSERTABLE_REVISION_KINDS = frozenset(
    {DRAFT_KIND_ACCEPTED, DRAFT_KIND_UNDO, DRAFT_KIND_UNPROPOSED}
)


# --- Domain errors ------------------------------------------------------------


class BuilderStoreError(Exception):
    """Base class of the store's domain errors."""


class SessionNotFoundError(BuilderStoreError):
    """The session does not exist or belongs to another user."""


class TurnRunningError(BuilderStoreError):
    """The session already has a running assistant row (409 ``turn_running``)."""


class DuplicateClientMessageError(BuilderStoreError):
    """The session already holds this ``client_message_id`` (Req 21.10)."""


class InvalidCursorError(ValueError):
    """A list cursor could not be decoded."""


# --- Value objects shared with the in-memory fake ----------------------------


@dataclass(frozen=True)
class SessionPage:
    """One page of the session list; ``next_cursor`` is None on the last page."""

    items: tuple[WorkflowBuilderSession, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class BegunTurn:
    """The two rows ``begin_turn`` inserts."""

    user_message: WorkflowBuilderMessage
    assistant_message: WorkflowBuilderMessage


@dataclass(frozen=True)
class LatestRevisions:
    """The newest revision of each kind (None when the kind has none)."""

    seed: WorkflowBuilderDraft | None
    accepted: WorkflowBuilderDraft | None
    undo: WorkflowBuilderDraft | None
    unproposed: WorkflowBuilderDraft | None


@dataclass(frozen=True)
class SummaryState:
    """A session's Transcript_Summary and the last message seq it covers."""

    text: str | None
    through_seq: int | None


@dataclass(frozen=True)
class UserStorageRows:
    """Row counts and approximate payload bytes one user holds in the Session_Store.

    ``db_bytes`` sums the UTF-8 byte length of the text and JSON payload columns
    (message content, thinking, usage, adherence, tool and ``canvas_state``;
    revision manifest, change summary and launch needs; session title and
    summary). It excludes indexes and row overhead. ``canvas_state_bytes`` is the
    part of ``db_bytes`` held in user-message ``canvas_state``, the largest
    growth term (design R-04).
    """

    user_id: str
    session_count: int
    message_count: int
    draft_count: int
    db_bytes: int
    canvas_state_bytes: int


# --- Cursor helpers (reused by the fake) --------------------------------------


def clamp_page_size(limit: int | None) -> int:
    """Return a page size in ``1..MAX_SESSION_PAGE_SIZE`` (default 20)."""
    if limit is None:
        return DEFAULT_SESSION_PAGE_SIZE
    return max(1, min(limit, MAX_SESSION_PAGE_SIZE))


def encode_cursor(updated_at: datetime, session_id: str) -> str:
    """Encode the ``(updated_at, id)`` sort key of the last returned row."""
    payload = json.dumps(
        {"u": updated_at.isoformat(), "i": session_id}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode a cursor; raise ``InvalidCursorError`` when it is malformed."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        updated_at = datetime.fromisoformat(data["u"])
        session_id = data["i"]
    except (
        binascii.Error,
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
    ) as exc:
        raise InvalidCursorError("invalid cursor") from exc
    if not isinstance(session_id, str):
        raise InvalidCursorError("invalid cursor")
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at, session_id


# --- Helpers ------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _violates(exc: IntegrityError, index_name: str) -> bool:
    """True when the integrity error names the given unique index/constraint."""
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    if getattr(diag, "constraint_name", None) == index_name:
        return True
    return index_name in str(orig)


# --- Repository ---------------------------------------------------------------


class BuilderStore:
    """Session_Store repository bound to one SQLAlchemy session."""

    def __init__(self, db: DbSession) -> None:
        self._db = db

    @contextmanager
    def _unit_of_work(self) -> Iterator[None]:
        """Commit on success; roll back and re-raise on any error."""
        try:
            yield
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _lock_session(self, user_id: str, session_id: str) -> WorkflowBuilderSession:
        """Load the caller's session row ``FOR UPDATE`` or raise.

        The row lock serialises ``next_seq`` allocation and revision numbering.
        """
        row = self._db.execute(
            select(WorkflowBuilderSession)
            .where(
                WorkflowBuilderSession.id == session_id,
                WorkflowBuilderSession.user_id == user_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise SessionNotFoundError(session_id)
        return row

    # --- Sessions -------------------------------------------------------------

    def create_session(
        self,
        user_id: str,
        *,
        title: str,
        mode: str,
        skill_hash: str,
        workflow_id: str | None = None,
        linked_manifest_hash: str | None = None,
        model_id: str | None = None,
        effort: str | None = None,
        target_trust: str = "user",
        seed_manifest: dict[str, Any] | None = None,
        seed_manifest_hash: str | None = None,
    ) -> WorkflowBuilderSession:
        """Insert a session; an edit session also gets its seed (revision 0).

        ``seed_manifest`` and ``seed_manifest_hash`` go together.
        """
        if mode not in _SESSION_MODES:
            raise ValueError(f"unknown session mode: {mode!r}")
        if (seed_manifest is None) != (seed_manifest_hash is None):
            raise ValueError("seed_manifest and seed_manifest_hash go together")
        now = _utcnow()
        session_row = WorkflowBuilderSession(
            id=_new_id(),
            user_id=user_id,
            owner_id=user_id,
            workspace_id=user_id,
            title=title,
            mode=mode,
            workflow_id=workflow_id,
            linked_manifest_hash=linked_manifest_hash,
            model_id=model_id,
            effort=effort,
            target_trust=target_trust,
            skill_hash=skill_hash,
            next_seq=1,
            turn_count=0,
            clarify_turns_without_draft=0,
            created_at=now,
            updated_at=now,
        )
        with self._unit_of_work():
            self._db.add(session_row)
            if seed_manifest is not None and seed_manifest_hash is not None:
                self._db.flush()  # the draft row references the session
                self._db.add(
                    WorkflowBuilderDraft(
                        id=_new_id(),
                        session_id=session_row.id,
                        user_id=user_id,
                        owner_id=user_id,
                        workspace_id=user_id,
                        revision=0,
                        kind=DRAFT_KIND_SEED,
                        manifest=seed_manifest,
                        manifest_hash=seed_manifest_hash,
                        created_at=now,
                    )
                )
        return session_row

    def get_session(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderSession | None:
        """Return the caller's session or None (missing and foreign look alike)."""
        return self._db.execute(
            select(WorkflowBuilderSession).where(
                WorkflowBuilderSession.id == session_id,
                WorkflowBuilderSession.user_id == user_id,
            )
        ).scalar_one_or_none()

    def list_sessions(
        self, user_id: str, *, limit: int | None = None, cursor: str | None = None
    ) -> SessionPage:
        """Keyset page of the caller's sessions, newest first.

        Order is ``(updated_at DESC, id ASC)``, matching
        ``ix_wb_sessions_user_updated``. The page size is clamped to
        ``1..50`` (default 20) [pending G-24].
        """
        page_size = clamp_page_size(limit)
        stmt = select(WorkflowBuilderSession).where(
            WorkflowBuilderSession.user_id == user_id
        )
        if cursor is not None:
            after_updated_at, after_id = decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    WorkflowBuilderSession.updated_at < after_updated_at,
                    and_(
                        WorkflowBuilderSession.updated_at == after_updated_at,
                        WorkflowBuilderSession.id > after_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            WorkflowBuilderSession.updated_at.desc(), WorkflowBuilderSession.id.asc()
        ).limit(page_size + 1)
        rows = list(self._db.execute(stmt).scalars())
        has_more = len(rows) > page_size
        page = rows[:page_size]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_cursor(last.updated_at, last.id)  # type: ignore[arg-type]
        return SessionPage(items=tuple(page), next_cursor=next_cursor)

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """Delete the session with its messages and revisions (Req 31.2).

        Returns False when the caller owns no such session. The sandbox folder
        is removed by the caller after this commit.
        """
        with self._unit_of_work():
            exists = self._db.execute(
                select(WorkflowBuilderSession.id)
                .where(
                    WorkflowBuilderSession.id == session_id,
                    WorkflowBuilderSession.user_id == user_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if exists is None:
                return False
            self._db.execute(
                delete(WorkflowBuilderMessage).where(
                    WorkflowBuilderMessage.session_id == session_id,
                    WorkflowBuilderMessage.user_id == user_id,
                )
            )
            self._db.execute(
                delete(WorkflowBuilderDraft).where(
                    WorkflowBuilderDraft.session_id == session_id,
                    WorkflowBuilderDraft.user_id == user_id,
                )
            )
            self._db.execute(
                delete(WorkflowBuilderSession).where(
                    WorkflowBuilderSession.id == session_id,
                    WorkflowBuilderSession.user_id == user_id,
                )
            )
        return True

    # --- Messages -------------------------------------------------------------

    def begin_turn(
        self,
        user_id: str,
        session_id: str,
        *,
        content: str,
        canvas_state: dict[str, Any] | None,
        client_message_id: str | None,
        model_id: str | None,
        effort: str | None,
        skill_hash: str | None,
        prompt_version: str | None = None,
        first_message_title: str | None = None,
    ) -> BegunTurn:
        """Insert the user message and the running assistant row in one transaction.

        The two rows take seqs ``next_seq`` and ``next_seq + 1``. The assistant
        row's id is the turn id; the user row's ``turn_id`` points at it. The
        session records the model and effort as the last choice (Req 26.5),
        counts the turn, and takes ``first_message_title`` when this is its
        first message (Req 12.2).

        Raises ``SessionNotFoundError``, ``TurnRunningError`` (partial unique
        index) or ``DuplicateClientMessageError`` (unique client id).
        """
        now = _utcnow()
        user_message_id = _new_id()
        turn_id = _new_id()
        with self._unit_of_work():
            session_row = self._lock_session(user_id, session_id)
            first_seq = int(session_row.next_seq)  # type: ignore[arg-type]
            user_message = WorkflowBuilderMessage(
                id=user_message_id,
                session_id=session_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=user_id,
                seq=first_seq,
                role=MESSAGE_ROLE_USER,
                turn_id=turn_id,
                status=MESSAGE_STATUS_USER_ACCEPTED,
                content=content,
                canvas_state=canvas_state,
                client_message_id=client_message_id,
                model_id=model_id,
                effort=effort,
                skill_hash=skill_hash,
                prompt_version=prompt_version,
                created_at=now,
            )
            assistant_message = WorkflowBuilderMessage(
                id=turn_id,
                session_id=session_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=user_id,
                seq=first_seq + 1,
                role=MESSAGE_ROLE_ASSISTANT,
                turn_id=turn_id,
                reply_to_message_id=user_message_id,
                status=MESSAGE_STATUS_RUNNING,
                content="",
                model_id=model_id,
                effort=effort,
                skill_hash=skill_hash,
                prompt_version=prompt_version,
                started_at=now,
                created_at=now,
            )
            if first_message_title is not None and session_row.turn_count == 0:
                session_row.title = first_message_title  # type: ignore[assignment]
            session_row.next_seq = first_seq + 2  # type: ignore[assignment]
            session_row.turn_count = int(session_row.turn_count) + 1  # type: ignore[arg-type,assignment]
            session_row.model_id = model_id  # type: ignore[assignment]
            session_row.effort = effort  # type: ignore[assignment]
            session_row.updated_at = now  # type: ignore[assignment]
            self._db.add_all([user_message, assistant_message])
            try:
                self._db.flush()
            except IntegrityError as exc:
                if _violates(exc, _UNIQUE_RUNNING_INDEX):
                    raise TurnRunningError(session_id) from exc
                if _violates(exc, _UNIQUE_CLIENT_ID_INDEX):
                    raise DuplicateClientMessageError(client_message_id or "") from exc
                raise
        return BegunTurn(user_message=user_message, assistant_message=assistant_message)

    def begin_retry(
        self,
        user_id: str,
        session_id: str,
        user_message_id: str,
        *,
        model_id: str | None,
        effort: str | None,
        skill_hash: str | None,
        prompt_version: str | None = None,
    ) -> BegunTurn:
        """Insert a new running assistant row that replies to an existing user row.

        Used by retry [pending G-01]: no second user message is stored, and the
        session's ``turn_count`` is unchanged because the user sent nothing new.

        Raises ``SessionNotFoundError`` (unknown session or user row) or
        ``TurnRunningError`` (partial unique index).
        """
        now = _utcnow()
        turn_id = _new_id()
        with self._unit_of_work():
            session_row = self._lock_session(user_id, session_id)
            user_message = self._db.execute(
                select(WorkflowBuilderMessage).where(
                    WorkflowBuilderMessage.id == user_message_id,
                    WorkflowBuilderMessage.session_id == session_id,
                    WorkflowBuilderMessage.user_id == user_id,
                    WorkflowBuilderMessage.role == MESSAGE_ROLE_USER,
                )
            ).scalar_one_or_none()
            if user_message is None:
                raise SessionNotFoundError(session_id)
            seq = int(session_row.next_seq)  # type: ignore[arg-type]
            assistant_message = WorkflowBuilderMessage(
                id=turn_id,
                session_id=session_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=user_id,
                seq=seq,
                role=MESSAGE_ROLE_ASSISTANT,
                turn_id=turn_id,
                reply_to_message_id=user_message_id,
                status=MESSAGE_STATUS_RUNNING,
                content="",
                model_id=model_id,
                effort=effort,
                skill_hash=skill_hash,
                prompt_version=prompt_version,
                started_at=now,
                created_at=now,
            )
            session_row.next_seq = seq + 1  # type: ignore[assignment]
            session_row.model_id = model_id  # type: ignore[assignment]
            session_row.effort = effort  # type: ignore[assignment]
            session_row.updated_at = now  # type: ignore[assignment]
            self._db.add(assistant_message)
            try:
                self._db.flush()
            except IntegrityError as exc:
                if _violates(exc, _UNIQUE_RUNNING_INDEX):
                    raise TurnRunningError(session_id) from exc
                raise
        return BegunTurn(user_message=user_message, assistant_message=assistant_message)

    def link_session(
        self,
        user_id: str,
        session_id: str,
        *,
        workflow_id: str,
        linked_manifest_hash: str,
    ) -> WorkflowBuilderSession:
        """Link the session to a saved workflow and store the hash it was linked at.

        Raises ``SessionNotFoundError`` when the caller owns no such session.
        """
        with self._unit_of_work():
            session_row = self._lock_session(user_id, session_id)
            session_row.workflow_id = workflow_id  # type: ignore[assignment]
            session_row.linked_manifest_hash = linked_manifest_hash  # type: ignore[assignment]
            session_row.updated_at = _utcnow()  # type: ignore[assignment]
        return session_row

    def insert_tool_row(
        self,
        user_id: str,
        session_id: str,
        turn_id: str,
        *,
        status: str,
        content: str,
        tool: dict[str, Any],
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> WorkflowBuilderMessage:
        """Store one finished tool call under the turn (Req 24.5).

        Tool rows take a seq from the same ``next_seq`` counter.
        """
        if status not in _TOOL_STATUSES:
            raise ValueError(f"invalid tool row status: {status!r}")
        now = _utcnow()
        with self._unit_of_work():
            session_row = self._lock_session(user_id, session_id)
            seq = int(session_row.next_seq)  # type: ignore[arg-type]
            row = WorkflowBuilderMessage(
                id=_new_id(),
                session_id=session_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=user_id,
                seq=seq,
                role=MESSAGE_ROLE_TOOL,
                turn_id=turn_id,
                status=status,
                content=content,
                tool=tool,
                started_at=started_at,
                ended_at=ended_at,
                created_at=now,
            )
            session_row.next_seq = seq + 1  # type: ignore[assignment]
            session_row.updated_at = now  # type: ignore[assignment]
            self._db.add(row)
        return row

    def finalize_assistant(
        self,
        user_id: str,
        turn_id: str,
        *,
        status: str,
        outcome: str | None = None,
        stop_reason: str | None = None,
        error_code: str | None = None,
        content: str = "",
        thinking: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        adherence: dict[str, Any] | None = None,
        revision: int | None = None,
        skill_hash: str | None = None,
        prompt_version: str | None = None,
        ended_at: datetime | None = None,
    ) -> WorkflowBuilderMessage | None:
        """Write the final state of a running assistant row (Req 21.9).

        `steps` is the ordered thinking, tool-call groups and checks of the turn,
        or None for a turn that had none.

        `skill_hash` and `prompt_version` replace the stored values only when
        given, so the values written at admission stay when the caller has none.

        Returns None when the caller has no running assistant row with this id
        (missing, foreign, or already finalised), and changes nothing.
        """
        if status not in _ASSISTANT_FINAL_STATUSES:
            raise ValueError(f"invalid final assistant status: {status!r}")
        now = _utcnow()
        with self._unit_of_work():
            row = self._db.execute(
                select(WorkflowBuilderMessage)
                .where(
                    WorkflowBuilderMessage.id == turn_id,
                    WorkflowBuilderMessage.user_id == user_id,
                    WorkflowBuilderMessage.role == MESSAGE_ROLE_ASSISTANT,
                    WorkflowBuilderMessage.status == MESSAGE_STATUS_RUNNING,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return None
            row.status = status  # type: ignore[assignment]
            row.outcome = outcome  # type: ignore[assignment]
            row.stop_reason = stop_reason  # type: ignore[assignment]
            row.error_code = error_code  # type: ignore[assignment]
            row.content = content  # type: ignore[assignment]
            row.thinking = thinking  # type: ignore[assignment]
            row.steps = steps  # type: ignore[assignment]
            row.usage = usage  # type: ignore[assignment]
            row.adherence = adherence  # type: ignore[assignment]
            row.revision = revision  # type: ignore[assignment]
            if skill_hash is not None:
                row.skill_hash = skill_hash  # type: ignore[assignment]
            if prompt_version is not None:
                row.prompt_version = prompt_version  # type: ignore[assignment]
            row.ended_at = ended_at or now  # type: ignore[assignment]
            self._db.execute(
                update(WorkflowBuilderSession)
                .where(
                    WorkflowBuilderSession.id == row.session_id,
                    WorkflowBuilderSession.user_id == user_id,
                )
                .values(updated_at=now)
            )
        return row

    def get_message(
        self, user_id: str, message_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return one of the caller's message rows (any role) or None."""
        return self._db.execute(
            select(WorkflowBuilderMessage).where(
                WorkflowBuilderMessage.id == message_id,
                WorkflowBuilderMessage.user_id == user_id,
            )
        ).scalar_one_or_none()

    def find_user_message_by_client_id(
        self, user_id: str, session_id: str, client_message_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return the user row stored for this ``client_message_id`` (Req 21.10)."""
        return self._db.execute(
            select(WorkflowBuilderMessage).where(
                WorkflowBuilderMessage.user_id == user_id,
                WorkflowBuilderMessage.session_id == session_id,
                WorkflowBuilderMessage.role == MESSAGE_ROLE_USER,
                WorkflowBuilderMessage.client_message_id == client_message_id,
            )
        ).scalar_one_or_none()

    def list_messages(
        self, user_id: str, session_id: str, *, after_seq: int | None = None
    ) -> list[WorkflowBuilderMessage]:
        """Return the session's rows (all roles) by ``seq``, optionally after one."""
        stmt = select(WorkflowBuilderMessage).where(
            WorkflowBuilderMessage.user_id == user_id,
            WorkflowBuilderMessage.session_id == session_id,
        )
        if after_seq is not None:
            stmt = stmt.where(WorkflowBuilderMessage.seq > after_seq)
        stmt = stmt.order_by(WorkflowBuilderMessage.seq.asc())
        return list(self._db.execute(stmt).scalars())

    def list_tool_rows(
        self, user_id: str, turn_id: str
    ) -> list[WorkflowBuilderMessage]:
        """Return the turn's tool rows by ``seq``."""
        return list(
            self._db.execute(
                select(WorkflowBuilderMessage)
                .where(
                    WorkflowBuilderMessage.user_id == user_id,
                    WorkflowBuilderMessage.turn_id == turn_id,
                    WorkflowBuilderMessage.role == MESSAGE_ROLE_TOOL,
                )
                .order_by(WorkflowBuilderMessage.seq.asc())
            ).scalars()
        )

    def get_running_turn(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return the session's running assistant row, from stored state (Req 21.8)."""
        return self._db.execute(
            select(WorkflowBuilderMessage).where(
                WorkflowBuilderMessage.user_id == user_id,
                WorkflowBuilderMessage.session_id == session_id,
                WorkflowBuilderMessage.role == MESSAGE_ROLE_ASSISTANT,
                WorkflowBuilderMessage.status == MESSAGE_STATUS_RUNNING,
            )
        ).scalar_one_or_none()

    def get_latest_message(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return the newest user or assistant row (tool rows excluded), or None.

        The Session_Stream snapshot reports its id as ``latest_message_id``
        (Req 38.3).
        """
        return self._db.execute(
            select(WorkflowBuilderMessage)
            .where(
                WorkflowBuilderMessage.user_id == user_id,
                WorkflowBuilderMessage.session_id == session_id,
                WorkflowBuilderMessage.role != MESSAGE_ROLE_TOOL,
            )
            .order_by(WorkflowBuilderMessage.seq.desc())
            .limit(1)
        ).scalar_one_or_none()

    # --- Revisions ------------------------------------------------------------

    def insert_revision(
        self,
        user_id: str,
        session_id: str,
        *,
        kind: str,
        manifest: dict[str, Any],
        manifest_hash: str,
        target_trust: str | None = None,
        change_summary: dict[str, Any] | None = None,
        launch_needs: list[dict[str, Any]] | None = None,
        source_turn_id: str | None = None,
        source_file: str | None = None,
        undo_of_revision: int | None = None,
    ) -> WorkflowBuilderDraft:
        """Insert an ``accepted``, ``undo`` or ``unproposed`` revision.

        The number is ``max(revision) + 1`` computed inside this transaction,
        under the session row lock (the unique constraint is the backstop). The
        ``seed`` kind is written only by ``create_session``.

        Side effects on the session row: an accepted revision sets
        ``first_accepted_revision`` when unset and ``target_trust`` when given;
        accepted and undo revisions set ``linked_manifest_hash`` to the
        revision's hash.
        """
        if kind not in _INSERTABLE_REVISION_KINDS:
            raise ValueError(f"cannot insert a revision of kind {kind!r}")
        with self._unit_of_work():
            session_row = self._lock_session(user_id, session_id)
            current_max = self._db.execute(
                select(func.max(WorkflowBuilderDraft.revision)).where(
                    WorkflowBuilderDraft.session_id == session_id,
                    WorkflowBuilderDraft.user_id == user_id,
                )
            ).scalar_one_or_none()
            revision = (current_max if current_max is not None else 0) + 1
            row = WorkflowBuilderDraft(
                id=_new_id(),
                session_id=session_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=user_id,
                revision=revision,
                kind=kind,
                manifest=manifest,
                target_trust=target_trust,
                change_summary=change_summary,
                launch_needs=launch_needs,
                source_turn_id=source_turn_id,
                source_file=source_file,
                undo_of_revision=undo_of_revision,
                manifest_hash=manifest_hash,
                created_at=_utcnow(),
            )
            if kind == DRAFT_KIND_ACCEPTED:
                if session_row.first_accepted_revision is None:
                    session_row.first_accepted_revision = revision  # type: ignore[assignment]
                if target_trust is not None:
                    session_row.target_trust = target_trust  # type: ignore[assignment]
            if kind in (DRAFT_KIND_ACCEPTED, DRAFT_KIND_UNDO):
                session_row.linked_manifest_hash = manifest_hash  # type: ignore[assignment]
            self._db.add(row)
        return row

    def get_latest_revision(
        self, user_id: str, session_id: str, kind: str
    ) -> WorkflowBuilderDraft | None:
        """Return the highest-numbered revision of ``kind`` or None."""
        return self._db.execute(
            select(WorkflowBuilderDraft)
            .where(
                WorkflowBuilderDraft.user_id == user_id,
                WorkflowBuilderDraft.session_id == session_id,
                WorkflowBuilderDraft.kind == kind,
            )
            .order_by(WorkflowBuilderDraft.revision.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_latest_revisions(self, user_id: str, session_id: str) -> LatestRevisions:
        """Return the newest seed, accepted, undo and unproposed revisions."""
        return LatestRevisions(
            seed=self.get_latest_revision(user_id, session_id, DRAFT_KIND_SEED),
            accepted=self.get_latest_revision(user_id, session_id, DRAFT_KIND_ACCEPTED),
            undo=self.get_latest_revision(user_id, session_id, DRAFT_KIND_UNDO),
            unproposed=self.get_latest_revision(
                user_id, session_id, DRAFT_KIND_UNPROPOSED
            ),
        )

    # --- Summary and clarify count -------------------------------------------

    def get_summary(self, user_id: str, session_id: str) -> SummaryState | None:
        """Return the Transcript_Summary state, or None for an unknown session."""
        row = self.get_session(user_id, session_id)
        if row is None:
            return None
        return SummaryState(
            text=row.summary_text,  # type: ignore[arg-type]
            through_seq=row.summary_through_seq,  # type: ignore[arg-type]
        )

    def set_summary(
        self, user_id: str, session_id: str, *, text: str, through_seq: int
    ) -> None:
        """Store the Transcript_Summary and the last seq it covers."""
        self._update_session(
            user_id,
            session_id,
            {"summary_text": text, "summary_through_seq": through_seq},
        )

    def get_clarify_count(self, user_id: str, session_id: str) -> int | None:
        """Return ``clarify_turns_without_draft``, or None for an unknown session."""
        row = self.get_session(user_id, session_id)
        if row is None:
            return None
        return int(row.clarify_turns_without_draft)  # type: ignore[arg-type]

    def set_clarify_count(self, user_id: str, session_id: str, count: int) -> None:
        """Store ``clarify_turns_without_draft``."""
        if count < 0:
            raise ValueError("clarify count cannot be negative")
        self._update_session(
            user_id, session_id, {"clarify_turns_without_draft": count}
        )

    def _update_session(
        self, user_id: str, session_id: str, values: dict[str, Any]
    ) -> None:
        """Update columns of the caller's session or raise ``SessionNotFoundError``."""
        with self._unit_of_work():
            result = self._db.execute(
                update(WorkflowBuilderSession)
                .where(
                    WorkflowBuilderSession.id == session_id,
                    WorkflowBuilderSession.user_id == user_id,
                )
                .values(**values)
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                raise SessionNotFoundError(session_id)

    # --- Admission counts -----------------------------------------------------

    def count_user_messages_since(self, user_id: str, since: datetime) -> int:
        """Count the caller's stored user messages created at or after ``since``."""
        return int(
            self._db.execute(
                select(func.count())
                .select_from(WorkflowBuilderMessage)
                .where(
                    WorkflowBuilderMessage.user_id == user_id,
                    WorkflowBuilderMessage.role == MESSAGE_ROLE_USER,
                    WorkflowBuilderMessage.created_at >= since,
                )
            ).scalar_one()
        )

    def oldest_user_message_since(
        self, user_id: str, since: datetime
    ) -> datetime | None:
        """Return the oldest user-message time at or after ``since``.

        Admission turns it into ``Retry-After`` for the rate limit.
        """
        return self._db.execute(
            select(func.min(WorkflowBuilderMessage.created_at)).where(
                WorkflowBuilderMessage.user_id == user_id,
                WorkflowBuilderMessage.role == MESSAGE_ROLE_USER,
                WorkflowBuilderMessage.created_at >= since,
            )
        ).scalar_one_or_none()

    def count_running_turns(self, user_id: str) -> int:
        """Count the caller's running assistant rows across all sessions."""
        return int(
            self._db.execute(
                select(func.count())
                .select_from(WorkflowBuilderMessage)
                .where(
                    WorkflowBuilderMessage.user_id == user_id,
                    WorkflowBuilderMessage.role == MESSAGE_ROLE_ASSISTANT,
                    WorkflowBuilderMessage.status == MESSAGE_STATUS_RUNNING,
                )
            ).scalar_one()
        )

    # --- Success metric facts (Req 44.6) ---------------------------------------

    def list_session_metric_facts(self, user_id: str) -> list[SessionFact]:
        """Return one fact per session of the caller, oldest first.

        A session counts as saved when it is linked to a saved workflow
        (``workflow_id`` set, Req 10.7). Nothing stores the turn count at the
        moment of the first save, so ``turns_before_first_save`` is the
        session's current ``turn_count`` for a saved session. That is an upper
        bound for a session that kept going after its save, and it also reads as
        unsaved after the linked workflow is deleted (``ON DELETE SET NULL``).
        Recording the turn count at link time needs a column the design does
        not have.
        """
        rows = self._db.execute(
            select(
                WorkflowBuilderSession.id,
                WorkflowBuilderSession.workflow_id,
                WorkflowBuilderSession.turn_count,
            )
            .where(WorkflowBuilderSession.user_id == user_id)
            .order_by(WorkflowBuilderSession.created_at.asc())
        ).all()
        return [
            SessionFact(
                session_id=str(session_id),
                turns_before_first_save=(
                    None if workflow_id is None else int(turn_count)
                ),
            )
            for session_id, workflow_id, turn_count in rows
        ]

    def list_turn_gate_facts(self, user_id: str) -> list[TurnGateFact]:
        """Return one fact per caller turn that called ``propose_draft``.

        The first call of a turn is its ``propose_draft`` tool row with the
        lowest ``seq``. It passed the Server_Gate when the turn has an
        ``accepted`` revision stored at or before that tool row was inserted: the
        gate stores the revision inside the call, and the tool row follows when
        the call ends, so a revision from a later call is newer than the first
        row. Turns that never called ``propose_draft`` are not returned.
        """
        tool_rows = self._db.execute(
            select(
                WorkflowBuilderMessage.turn_id,
                WorkflowBuilderMessage.seq,
                WorkflowBuilderMessage.created_at,
            )
            .where(
                WorkflowBuilderMessage.user_id == user_id,
                WorkflowBuilderMessage.role == MESSAGE_ROLE_TOOL,
                WorkflowBuilderMessage.tool["tool"].as_string() == PROPOSE_DRAFT_TOOL,
            )
            .order_by(WorkflowBuilderMessage.seq.asc())
        ).all()
        first_call_at: dict[str, datetime] = {}
        for turn_id, _seq, created_at in tool_rows:
            first_call_at.setdefault(str(turn_id), created_at)
        if not first_call_at:
            return []
        accepted = self._db.execute(
            select(
                WorkflowBuilderDraft.source_turn_id,
                func.min(WorkflowBuilderDraft.created_at),
            )
            .where(
                WorkflowBuilderDraft.user_id == user_id,
                WorkflowBuilderDraft.kind == DRAFT_KIND_ACCEPTED,
                WorkflowBuilderDraft.source_turn_id.in_(list(first_call_at)),
            )
            .group_by(WorkflowBuilderDraft.source_turn_id)
        ).all()
        first_accepted_at = {str(turn_id): at for turn_id, at in accepted}
        return [
            TurnGateFact(
                turn_id=turn_id,
                first_call_passed=(
                    turn_id in first_accepted_at
                    and first_accepted_at[turn_id] <= called_at
                ),
            )
            for turn_id, called_at in first_call_at.items()
        ]

    # --- Storage report (all users) -------------------------------------------

    def storage_usage_by_user(self) -> list[UserStorageRows]:
        """Return row counts and payload bytes per user, ordered by user id.

        Operator-level: it has no ``user_id`` filter because the storage report
        covers every user (Req 44.7). It returns counts and sizes only, never
        row content. Sizes use ``octet_length`` on PostgreSQL.
        """

        def size(column: Any) -> Any:
            return func.coalesce(func.octet_length(cast(column, Text)), 0)

        msg = WorkflowBuilderMessage
        draft = WorkflowBuilderDraft
        sess = WorkflowBuilderSession
        message_rows = self._db.execute(
            select(
                msg.user_id,
                func.count(),
                func.coalesce(
                    func.sum(
                        size(msg.content)
                        + size(msg.thinking)
                        + size(msg.steps)
                        + size(msg.canvas_state)
                        + size(msg.usage)
                        + size(msg.adherence)
                        + size(msg.tool)
                    ),
                    0,
                ),
                func.coalesce(func.sum(size(msg.canvas_state)), 0),
            ).group_by(msg.user_id)
        ).all()
        draft_rows = self._db.execute(
            select(
                draft.user_id,
                func.count(),
                func.coalesce(
                    func.sum(
                        size(draft.manifest)
                        + size(draft.change_summary)
                        + size(draft.launch_needs)
                    ),
                    0,
                ),
            ).group_by(draft.user_id)
        ).all()
        session_rows = self._db.execute(
            select(
                sess.user_id,
                func.count(),
                func.coalesce(func.sum(size(sess.title) + size(sess.summary_text)), 0),
            ).group_by(sess.user_id)
        ).all()

        counts: dict[str, dict[str, int]] = {}

        def slot(user_id: Any) -> dict[str, int]:
            return counts.setdefault(
                str(user_id),
                {
                    "sessions": 0,
                    "messages": 0,
                    "drafts": 0,
                    "bytes": 0,
                    "canvas": 0,
                },
            )

        for user_id, count, payload, canvas in message_rows:
            entry = slot(user_id)
            entry["messages"] = int(count)
            entry["bytes"] += int(payload)
            entry["canvas"] = int(canvas)
        for user_id, count, payload in draft_rows:
            entry = slot(user_id)
            entry["drafts"] = int(count)
            entry["bytes"] += int(payload)
        for user_id, count, payload in session_rows:
            entry = slot(user_id)
            entry["sessions"] = int(count)
            entry["bytes"] += int(payload)
        return [
            UserStorageRows(
                user_id=user_id,
                session_count=entry["sessions"],
                message_count=entry["messages"],
                draft_count=entry["drafts"],
                db_bytes=entry["bytes"],
                canvas_state_bytes=entry["canvas"],
            )
            for user_id, entry in sorted(counts.items())
        ]

    # --- Startup sweep (all users) -------------------------------------------

    def list_running_assistant_rows(self) -> list[WorkflowBuilderMessage]:
        """List every user's assistant rows still ``running``, oldest first."""
        return list(
            self._db.execute(
                select(WorkflowBuilderMessage)
                .where(
                    WorkflowBuilderMessage.role == MESSAGE_ROLE_ASSISTANT,
                    WorkflowBuilderMessage.status == MESSAGE_STATUS_RUNNING,
                )
                .order_by(WorkflowBuilderMessage.created_at.asc())
            ).scalars()
        )

    def mark_running_interrupted(self, *, ended_at: datetime | None = None) -> int:
        """Mark every running assistant row ``interrupted`` / ``restart``.

        Returns the number of rows changed (design §3.1.6 step 2).
        """
        with self._unit_of_work():
            result = self._db.execute(
                update(WorkflowBuilderMessage)
                .where(
                    WorkflowBuilderMessage.role == MESSAGE_ROLE_ASSISTANT,
                    WorkflowBuilderMessage.status == MESSAGE_STATUS_RUNNING,
                )
                .values(
                    status=MESSAGE_STATUS_INTERRUPTED,
                    stop_reason="restart",
                    ended_at=ended_at or _utcnow(),
                )
            )
            return int(result.rowcount)  # type: ignore[attr-defined]


def get_builder_store(db: DbSession = Depends(get_db)) -> BuilderStore:
    """FastAPI dependency: the Session_Store for this request.

    Tests substitute ``InMemoryBuilderStore`` with
    ``app.dependency_overrides[get_builder_store]``.
    """
    return BuilderStore(db)

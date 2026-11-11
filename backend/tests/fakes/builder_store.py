"""In-memory ``BuilderStore`` for tests that must not touch a database.

``InMemoryBuilderStore`` has the public interface and the observable semantics of
``app.api.workflow_builder.store.BuilderStore``; override ``get_builder_store`` with
it via ``app.dependency_overrides``. It reuses the real module's cursor helpers,
value objects and domain errors, and returns ORM instances (un-attached to a
database), so callers see the same attribute shape.

Semantics mirrored from the real store:

- Every read and write is scoped to ``user_id``; a foreign row is a missing row.
  Only the two sweep methods and ``storage_usage_by_user`` act on all users.
  ``storage_usage_by_user`` returns exact counts and approximate byte sizes.
- ``begin_turn`` takes seqs ``next_seq`` (user) and ``next_seq + 1`` (assistant);
  tool rows take one seq each from the same counter. A duplicate
  ``client_message_id`` is reported before a second running turn, as the real
  flush does (the user row is inserted first). A failed call changes nothing.
- A revision number is ``max + 1`` with the seed at 0. Accepted and undo
  revisions set ``linked_manifest_hash``; an accepted one also sets
  ``first_accepted_revision`` once and ``target_trust`` when given.
- ``finalize_assistant`` only touches a running assistant row.
- ``updated_at`` moves where the real SQL moves it: ``begin_turn``,
  ``insert_tool_row``, ``finalize_assistant``, ``set_summary`` and
  ``set_clarify_count`` (the column's ``onupdate``), and when ``insert_revision``
  changes a session column.

Time: the real store reads the wall clock. The fake takes an optional ``clock``
and by default uses the wall clock made strictly increasing, so rows created in
sequence never tie on ``updated_at`` or ``created_at``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agents.workflow_builder.success_metrics import SessionFact, TurnGateFact
from app.api.workflow_builder.store import (
    PROPOSE_DRAFT_TOOL,
    BegunTurn,
    DuplicateClientMessageError,
    LatestRevisions,
    SessionNotFoundError,
    SessionPage,
    SummaryState,
    TurnRunningError,
    UserStorageRows,
    clamp_page_size,
    decode_cursor,
    encode_cursor,
)
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
_INSERTABLE_REVISION_KINDS = frozenset(
    {DRAFT_KIND_ACCEPTED, DRAFT_KIND_UNDO, DRAFT_KIND_UNPROPOSED}
)


def _new_id() -> str:
    return str(uuid.uuid4())


def _payload_size(value: Any) -> int:
    """UTF-8 length of a text value or of a JSON value's text; 0 for ``None``."""
    if value is None:
        return 0
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return len(text.encode("utf-8"))


class InMemoryBuilderStore:
    """Dict-backed stand-in for ``BuilderStore`` (same public interface)."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock
        self._last_tick: datetime | None = None
        self._sessions: dict[str, WorkflowBuilderSession] = {}
        self._messages: list[WorkflowBuilderMessage] = []
        self._drafts: list[WorkflowBuilderDraft] = []

    # --- Internals ------------------------------------------------------------

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock()
        tick = datetime.now(timezone.utc)
        if self._last_tick is not None and tick <= self._last_tick:
            tick = self._last_tick + timedelta(microseconds=1)
        self._last_tick = tick
        return tick

    def _require_session(self, user_id: str, session_id: str) -> WorkflowBuilderSession:
        row = self.get_session(user_id, session_id)
        if row is None:
            raise SessionNotFoundError(session_id)
        return row

    def _session_messages(
        self, user_id: str, session_id: str
    ) -> list[WorkflowBuilderMessage]:
        return [
            m
            for m in self._messages
            if m.user_id == user_id and m.session_id == session_id
        ]

    def _drafts_of(self, user_id: str, session_id: str) -> list[WorkflowBuilderDraft]:
        return [
            d
            for d in self._drafts
            if d.user_id == user_id and d.session_id == session_id
        ]

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
        if mode not in _SESSION_MODES:
            raise ValueError(f"unknown session mode: {mode!r}")
        if (seed_manifest is None) != (seed_manifest_hash is None):
            raise ValueError("seed_manifest and seed_manifest_hash go together")
        now = self._now()
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
        self._sessions[session_row.id] = session_row  # type: ignore[index]
        if seed_manifest is not None and seed_manifest_hash is not None:
            self._drafts.append(
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
        row = self._sessions.get(session_id)
        if row is None or row.user_id != user_id:
            return None
        return row

    def list_sessions(
        self, user_id: str, *, limit: int | None = None, cursor: str | None = None
    ) -> SessionPage:
        page_size = clamp_page_size(limit)
        rows = [s for s in self._sessions.values() if s.user_id == user_id]
        if cursor is not None:
            after_updated_at, after_id = decode_cursor(cursor)
            rows = [
                s
                for s in rows
                if s.updated_at < after_updated_at  # type: ignore[operator]
                or (s.updated_at == after_updated_at and s.id > after_id)  # type: ignore[operator]
            ]
        # Order is (updated_at DESC, id ASC): sort by id, then stably by time desc.
        rows.sort(key=lambda s: s.id)  # type: ignore[arg-type,return-value]
        rows.sort(key=lambda s: s.updated_at, reverse=True)  # type: ignore[arg-type,return-value]
        has_more = len(rows) > page_size
        page = rows[:page_size]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_cursor(last.updated_at, last.id)  # type: ignore[arg-type]
        return SessionPage(items=tuple(page), next_cursor=next_cursor)

    def delete_session(self, user_id: str, session_id: str) -> bool:
        if self.get_session(user_id, session_id) is None:
            return False
        self._messages = [
            m
            for m in self._messages
            if not (m.session_id == session_id and m.user_id == user_id)
        ]
        self._drafts = [
            d
            for d in self._drafts
            if not (d.session_id == session_id and d.user_id == user_id)
        ]
        del self._sessions[session_id]
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
        session_row = self._require_session(user_id, session_id)
        # Checks come before any change so a failed call leaves the store as it was.
        if client_message_id is not None and (
            self.find_user_message_by_client_id(user_id, session_id, client_message_id)
            is not None
        ):
            raise DuplicateClientMessageError(client_message_id)
        if self.get_running_turn(user_id, session_id) is not None:
            raise TurnRunningError(session_id)

        now = self._now()
        user_message_id = _new_id()
        turn_id = _new_id()
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
        self._messages.extend([user_message, assistant_message])
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
        session_row = self._require_session(user_id, session_id)
        user_message = next(
            (
                m
                for m in self._session_messages(user_id, session_id)
                if m.id == user_message_id and m.role == MESSAGE_ROLE_USER
            ),
            None,
        )
        if user_message is None:
            raise SessionNotFoundError(session_id)
        if self.get_running_turn(user_id, session_id) is not None:
            raise TurnRunningError(session_id)
        now = self._now()
        turn_id = _new_id()
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
        self._messages.append(assistant_message)
        return BegunTurn(user_message=user_message, assistant_message=assistant_message)

    def link_session(
        self,
        user_id: str,
        session_id: str,
        *,
        workflow_id: str,
        linked_manifest_hash: str,
    ) -> WorkflowBuilderSession:
        session_row = self._require_session(user_id, session_id)
        session_row.workflow_id = workflow_id  # type: ignore[assignment]
        session_row.linked_manifest_hash = linked_manifest_hash  # type: ignore[assignment]
        session_row.updated_at = self._now()  # type: ignore[assignment]
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
        if status not in _TOOL_STATUSES:
            raise ValueError(f"invalid tool row status: {status!r}")
        session_row = self._require_session(user_id, session_id)
        now = self._now()
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
        self._messages.append(row)
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
        if status not in _ASSISTANT_FINAL_STATUSES:
            raise ValueError(f"invalid final assistant status: {status!r}")
        now = self._now()
        row = next(
            (
                m
                for m in self._messages
                if m.id == turn_id
                and m.user_id == user_id
                and m.role == MESSAGE_ROLE_ASSISTANT
                and m.status == MESSAGE_STATUS_RUNNING
            ),
            None,
        )
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
        session_row = self._sessions.get(row.session_id)  # type: ignore[arg-type]
        if session_row is not None and session_row.user_id == user_id:
            session_row.updated_at = now  # type: ignore[assignment]
        return row

    def get_message(
        self, user_id: str, message_id: str
    ) -> WorkflowBuilderMessage | None:
        return next(
            (m for m in self._messages if m.id == message_id and m.user_id == user_id),
            None,
        )

    def find_user_message_by_client_id(
        self, user_id: str, session_id: str, client_message_id: str
    ) -> WorkflowBuilderMessage | None:
        return next(
            (
                m
                for m in self._session_messages(user_id, session_id)
                if m.role == MESSAGE_ROLE_USER
                and m.client_message_id == client_message_id
            ),
            None,
        )

    def list_messages(
        self, user_id: str, session_id: str, *, after_seq: int | None = None
    ) -> list[WorkflowBuilderMessage]:
        rows = self._session_messages(user_id, session_id)
        if after_seq is not None:
            rows = [m for m in rows if m.seq > after_seq]  # type: ignore[operator]
        return sorted(rows, key=lambda m: m.seq)  # type: ignore[arg-type,return-value]

    def list_tool_rows(
        self, user_id: str, turn_id: str
    ) -> list[WorkflowBuilderMessage]:
        rows = [
            m
            for m in self._messages
            if m.user_id == user_id
            and m.turn_id == turn_id
            and m.role == MESSAGE_ROLE_TOOL
        ]
        return sorted(rows, key=lambda m: m.seq)  # type: ignore[arg-type,return-value]

    def get_running_turn(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderMessage | None:
        return next(
            (
                m
                for m in self._session_messages(user_id, session_id)
                if m.role == MESSAGE_ROLE_ASSISTANT
                and m.status == MESSAGE_STATUS_RUNNING
            ),
            None,
        )

    def get_latest_message(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderMessage | None:
        rows = [
            m
            for m in self._session_messages(user_id, session_id)
            if m.role != MESSAGE_ROLE_TOOL
        ]
        if not rows:
            return None
        return max(rows, key=lambda m: m.seq)  # type: ignore[arg-type,return-value]

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
        if kind not in _INSERTABLE_REVISION_KINDS:
            raise ValueError(f"cannot insert a revision of kind {kind!r}")
        session_row = self._require_session(user_id, session_id)
        existing = [int(d.revision) for d in self._drafts_of(user_id, session_id)]  # type: ignore[arg-type]
        revision = (max(existing) if existing else 0) + 1
        now = self._now()
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
            created_at=now,
        )
        changed = False
        if kind == DRAFT_KIND_ACCEPTED:
            if session_row.first_accepted_revision is None:
                session_row.first_accepted_revision = revision  # type: ignore[assignment]
                changed = True
            if target_trust is not None and session_row.target_trust != target_trust:
                session_row.target_trust = target_trust  # type: ignore[assignment]
                changed = True
        if kind in (DRAFT_KIND_ACCEPTED, DRAFT_KIND_UNDO):
            if session_row.linked_manifest_hash != manifest_hash:
                session_row.linked_manifest_hash = manifest_hash  # type: ignore[assignment]
                changed = True
        if changed:
            session_row.updated_at = now  # type: ignore[assignment]
        self._drafts.append(row)
        return row

    def get_latest_revision(
        self, user_id: str, session_id: str, kind: str
    ) -> WorkflowBuilderDraft | None:
        rows = [d for d in self._drafts_of(user_id, session_id) if d.kind == kind]
        if not rows:
            return None
        return max(rows, key=lambda d: d.revision)  # type: ignore[arg-type,return-value]

    def get_latest_revisions(self, user_id: str, session_id: str) -> LatestRevisions:
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
        row = self._require_session(user_id, session_id)
        row.summary_text = text  # type: ignore[assignment]
        row.summary_through_seq = through_seq  # type: ignore[assignment]
        row.updated_at = self._now()  # type: ignore[assignment]

    def get_clarify_count(self, user_id: str, session_id: str) -> int | None:
        row = self.get_session(user_id, session_id)
        if row is None:
            return None
        return int(row.clarify_turns_without_draft)  # type: ignore[arg-type]

    def set_clarify_count(self, user_id: str, session_id: str, count: int) -> None:
        if count < 0:
            raise ValueError("clarify count cannot be negative")
        row = self._require_session(user_id, session_id)
        row.clarify_turns_without_draft = count  # type: ignore[assignment]
        row.updated_at = self._now()  # type: ignore[assignment]

    # --- Admission counts -----------------------------------------------------

    def _user_messages_since(
        self, user_id: str, since: datetime
    ) -> list[WorkflowBuilderMessage]:
        return [
            m
            for m in self._messages
            if m.user_id == user_id
            and m.role == MESSAGE_ROLE_USER
            and m.created_at >= since  # type: ignore[operator]
        ]

    def count_user_messages_since(self, user_id: str, since: datetime) -> int:
        return len(self._user_messages_since(user_id, since))

    def oldest_user_message_since(
        self, user_id: str, since: datetime
    ) -> datetime | None:
        rows = self._user_messages_since(user_id, since)
        if not rows:
            return None
        return min(m.created_at for m in rows)  # type: ignore[type-var,return-value]

    def count_running_turns(self, user_id: str) -> int:
        return sum(
            1
            for m in self._messages
            if m.user_id == user_id
            and m.role == MESSAGE_ROLE_ASSISTANT
            and m.status == MESSAGE_STATUS_RUNNING
        )

    # --- Success metric facts (Req 44.6) --------------------------------------

    def list_session_metric_facts(self, user_id: str) -> list[SessionFact]:
        rows = sorted(
            (s for s in self._sessions.values() if s.user_id == user_id),
            key=lambda s: s.created_at,  # type: ignore[arg-type,return-value]
        )
        return [
            SessionFact(
                session_id=str(s.id),
                turns_before_first_save=(
                    None if s.workflow_id is None else int(s.turn_count)  # type: ignore[arg-type]
                ),
            )
            for s in rows
        ]

    def list_turn_gate_facts(self, user_id: str) -> list[TurnGateFact]:
        tool_rows = sorted(
            (
                m
                for m in self._messages
                if m.user_id == user_id
                and m.role == MESSAGE_ROLE_TOOL
                and isinstance(m.tool, dict)
                and m.tool.get("tool") == PROPOSE_DRAFT_TOOL
            ),
            key=lambda m: m.seq,  # type: ignore[arg-type,return-value]
        )
        first_call_at: dict[str, datetime] = {}
        for row in tool_rows:
            first_call_at.setdefault(str(row.turn_id), row.created_at)  # type: ignore[arg-type]
        first_accepted_at: dict[str, datetime] = {}
        for draft in self._drafts:
            turn_id = str(draft.source_turn_id)
            if (
                draft.user_id == user_id
                and draft.kind == DRAFT_KIND_ACCEPTED
                and turn_id in first_call_at
            ):
                created = draft.created_at
                if (
                    turn_id not in first_accepted_at
                    or created < first_accepted_at[turn_id]
                ):  # type: ignore[operator]
                    first_accepted_at[turn_id] = created  # type: ignore[assignment]
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
        """Counts match the real store; byte sizes are approximate.

        The real store sums ``octet_length`` of each column cast to text. The fake
        uses the UTF-8 length of the text, or of the compact-spaced JSON text, so the
        figures have the same order of magnitude but are not byte-identical.
        """
        slots: dict[str, dict[str, int]] = {}

        def slot(user_id: str) -> dict[str, int]:
            return slots.setdefault(
                user_id,
                {"sessions": 0, "messages": 0, "drafts": 0, "bytes": 0, "canvas": 0},
            )

        for m in self._messages:
            entry = slot(str(m.user_id))
            entry["messages"] += 1
            entry["bytes"] += sum(
                _payload_size(getattr(m, name))
                for name in (
                    "content",
                    "thinking",
                    "canvas_state",
                    "usage",
                    "adherence",
                    "tool",
                )
            )
            entry["canvas"] += _payload_size(m.canvas_state)
        for d in self._drafts:
            entry = slot(str(d.user_id))
            entry["drafts"] += 1
            entry["bytes"] += sum(
                _payload_size(getattr(d, name))
                for name in ("manifest", "change_summary", "launch_needs")
            )
        for s in self._sessions.values():
            entry = slot(str(s.user_id))
            entry["sessions"] += 1
            entry["bytes"] += _payload_size(s.title) + _payload_size(s.summary_text)
        return [
            UserStorageRows(
                user_id=user_id,
                session_count=entry["sessions"],
                message_count=entry["messages"],
                draft_count=entry["drafts"],
                db_bytes=entry["bytes"],
                canvas_state_bytes=entry["canvas"],
            )
            for user_id, entry in sorted(slots.items())
        ]

    # --- Startup sweep (all users) -------------------------------------------

    def list_running_assistant_rows(self) -> list[WorkflowBuilderMessage]:
        rows = [
            m
            for m in self._messages
            if m.role == MESSAGE_ROLE_ASSISTANT and m.status == MESSAGE_STATUS_RUNNING
        ]
        return sorted(rows, key=lambda m: m.created_at)  # type: ignore[arg-type,return-value]

    def mark_running_interrupted(self, *, ended_at: datetime | None = None) -> int:
        rows = self.list_running_assistant_rows()
        stamp = ended_at or self._now()
        for row in rows:
            row.status = MESSAGE_STATUS_INTERRUPTED  # type: ignore[assignment]
            row.stop_reason = "restart"  # type: ignore[assignment]
            row.ended_at = stamp  # type: ignore[assignment]
        return len(rows)

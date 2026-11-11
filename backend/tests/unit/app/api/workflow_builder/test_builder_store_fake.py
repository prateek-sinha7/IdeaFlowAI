"""Parity checks for ``InMemoryBuilderStore`` against the real store's contract.

The fake stands in for ``BuilderStore`` in router and service tests, so these tests
pin the semantics those tests rely on (design §4, Req 21.8-21.10, 24.5).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.api.workflow_builder.store import (
    DuplicateClientMessageError,
    InvalidCursorError,
    SessionNotFoundError,
    TurnRunningError,
)
from app.models.workflow_builder import (
    DRAFT_KIND_ACCEPTED,
    DRAFT_KIND_SEED,
    DRAFT_KIND_UNDO,
    DRAFT_KIND_UNPROPOSED,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_COMPLETED,
    MESSAGE_STATUS_INTERRUPTED,
    MESSAGE_STATUS_RUNNING,
    MESSAGE_STATUS_TOOL_OK,
    SESSION_MODE_EDIT,
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)
from tests.factories.builder_session_factory import (
    BuilderSessionFactory,
    build_message,
    build_revision,
    build_tool_row,
)
from tests.fakes.builder_store import InMemoryBuilderStore

USER = "user-a"
OTHER = "user-b"


class _Clock:
    """A settable clock so tests control row timestamps."""

    def __init__(self) -> None:
        self.now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def store(clock: _Clock) -> InMemoryBuilderStore:
    return InMemoryBuilderStore(clock=clock)


def _session(store: InMemoryBuilderStore, user_id: str = USER, **overrides: Any):
    return store.create_session(
        user_id, **BuilderSessionFactory.create_kwargs(**overrides)
    )


def _begin(
    store: InMemoryBuilderStore,
    session_id: str,
    user_id: str = USER,
    client_message_id: str | None = "c1",
    **overrides: Any,
):
    kwargs: dict[str, Any] = {
        "content": "hello",
        "canvas_state": None,
        "client_message_id": client_message_id,
        "model_id": "m",
        "effort": "low",
        "skill_hash": "h",
    }
    kwargs.update(overrides)
    return store.begin_turn(user_id, session_id, **kwargs)


def _revise(store: InMemoryBuilderStore, session_id: str, kind: str, hash_: str, **kw):
    return store.insert_revision(
        USER,
        session_id,
        kind=kind,
        manifest={"id": "wf"},
        manifest_hash=hash_,
        **kw,
    )


# --- Sessions -----------------------------------------------------------------


def test_create_session_returns_orm_row_stamped_with_user_when_created(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    assert isinstance(row, WorkflowBuilderSession)
    assert (row.owner_id, row.workspace_id, row.next_seq, row.turn_count) == (
        USER,
        USER,
        1,
        0,
    )


def test_create_session_writes_seed_revision_zero_when_seed_given(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(
        store,
        mode=SESSION_MODE_EDIT,
        seed_manifest={"id": "wf"},
        seed_manifest_hash="s",
    )

    seed = store.get_latest_revisions(USER, row.id).seed
    assert isinstance(seed, WorkflowBuilderDraft)
    assert (seed.revision, seed.kind) == (0, DRAFT_KIND_SEED)


def test_create_session_raises_when_seed_hash_missing(
    store: InMemoryBuilderStore,
) -> None:
    with pytest.raises(ValueError):
        _session(store, seed_manifest={"id": "wf"})


def test_get_session_returns_none_when_session_is_foreign(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    assert store.get_session(OTHER, row.id) is None
    assert store.get_session(USER, "missing") is None


def test_list_sessions_orders_by_updated_desc_then_id_when_paging(
    store: InMemoryBuilderStore, clock: _Clock
) -> None:
    first = _session(store)
    clock.advance(seconds=1)
    second = _session(store)
    clock.advance(seconds=1)
    third = _session(store)
    _session(store, OTHER)

    page1 = store.list_sessions(USER, limit=2)
    page2 = store.list_sessions(USER, limit=2, cursor=page1.next_cursor)

    assert [s.id for s in page1.items] == [third.id, second.id]
    assert page1.next_cursor is not None
    assert [s.id for s in page2.items] == [first.id]
    assert page2.next_cursor is None


def test_list_sessions_breaks_ties_by_id_ascending_when_updated_at_equal(
    store: InMemoryBuilderStore,
) -> None:
    rows = [_session(store) for _ in range(3)]  # fixed clock: all tie

    page = store.list_sessions(USER)

    assert [s.id for s in page.items] == sorted(r.id for r in rows)


def test_list_sessions_raises_invalid_cursor_when_cursor_malformed(
    store: InMemoryBuilderStore,
) -> None:
    with pytest.raises(InvalidCursorError):
        store.list_sessions(USER, cursor="!!not-a-cursor!!")


def test_delete_session_removes_messages_and_revisions_when_owner_deletes(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    begun = _begin(store, row.id)
    _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h1")

    assert store.delete_session(USER, row.id) is True

    assert store.get_session(USER, row.id) is None
    assert store.get_message(USER, begun.user_message.id) is None
    assert store.get_latest_revision(USER, row.id, DRAFT_KIND_ACCEPTED) is None


def test_delete_session_returns_false_and_keeps_row_when_session_is_foreign(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    assert store.delete_session(OTHER, row.id) is False
    assert store.get_session(USER, row.id) is row


# --- Turns and messages -------------------------------------------------------


def test_begin_turn_allocates_consecutive_seqs_when_tool_rows_follow(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    begun = _begin(store, row.id)
    tool = store.insert_tool_row(
        USER,
        row.id,
        begun.assistant_message.id,
        status=MESSAGE_STATUS_TOOL_OK,
        content="ok",
        tool={"name": "t"},
    )
    store.finalize_assistant(
        USER, begun.assistant_message.id, status=MESSAGE_STATUS_COMPLETED
    )
    next_turn = _begin(store, row.id, client_message_id="c2")

    assert begun.user_message.seq == 1
    assert begun.assistant_message.seq == 2
    assert tool.seq == 3
    assert (next_turn.user_message.seq, next_turn.assistant_message.seq) == (4, 5)
    assert row.next_seq == 6
    assert row.turn_count == 2


def test_begin_turn_links_rows_by_turn_id_when_turn_begins(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    begun = _begin(store, row.id)

    assert begun.assistant_message.id == begun.user_message.turn_id
    assert begun.assistant_message.reply_to_message_id == begun.user_message.id
    assert begun.assistant_message.status == MESSAGE_STATUS_RUNNING
    assert begun.user_message.role == MESSAGE_ROLE_USER
    assert begun.assistant_message.role == MESSAGE_ROLE_ASSISTANT
    assert row.model_id == "m"
    assert row.effort == "low"


def test_begin_turn_sets_title_only_when_first_message(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store, title="New session")
    first = _begin(store, row.id, first_message_title="Build a flow")
    store.finalize_assistant(
        USER, first.assistant_message.id, status=MESSAGE_STATUS_COMPLETED
    )

    _begin(store, row.id, client_message_id="c2", first_message_title="Other")

    assert row.title == "Build a flow"


def test_begin_turn_raises_turn_running_and_changes_nothing_when_turn_active(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    _begin(store, row.id)

    with pytest.raises(TurnRunningError):
        _begin(store, row.id, client_message_id="c2")

    assert row.next_seq == 3
    assert row.turn_count == 1
    assert len(store.list_messages(USER, row.id)) == 2


def test_begin_turn_raises_duplicate_when_client_message_id_reused(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    first = _begin(store, row.id)
    store.finalize_assistant(
        USER, first.assistant_message.id, status=MESSAGE_STATUS_COMPLETED
    )

    with pytest.raises(DuplicateClientMessageError):
        _begin(store, row.id)

    found = store.find_user_message_by_client_id(USER, row.id, "c1")
    assert found is first.user_message


def test_begin_turn_reports_duplicate_before_running_when_both_apply(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    _begin(store, row.id)

    with pytest.raises(DuplicateClientMessageError):
        _begin(store, row.id)


def test_begin_turn_allows_repeated_none_client_id_when_turns_finish(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    first = _begin(store, row.id, client_message_id=None)
    store.finalize_assistant(
        USER, first.assistant_message.id, status=MESSAGE_STATUS_COMPLETED
    )

    second = _begin(store, row.id, client_message_id=None)

    assert second.user_message.seq == 3


def test_begin_turn_raises_not_found_when_session_is_foreign(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    with pytest.raises(SessionNotFoundError):
        _begin(store, row.id, user_id=OTHER)


def test_insert_tool_row_raises_value_error_when_status_invalid(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    with pytest.raises(ValueError):
        store.insert_tool_row(USER, row.id, "t", status="running", content="", tool={})


def test_list_tool_rows_returns_rows_by_seq_when_turn_has_tools(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    begun = _begin(store, row.id)
    turn_id = begun.assistant_message.id
    for name in ("a", "b"):
        store.insert_tool_row(
            USER,
            row.id,
            turn_id,
            status=MESSAGE_STATUS_TOOL_OK,
            content=name,
            tool={"name": name},
        )

    rows = store.list_tool_rows(USER, turn_id)

    assert [r.content for r in rows] == ["a", "b"]
    assert store.list_tool_rows(OTHER, turn_id) == []


def test_list_messages_filters_after_seq_when_after_seq_given(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    _begin(store, row.id)

    rows = store.list_messages(USER, row.id, after_seq=1)

    assert [m.seq for m in rows] == [2]
    assert store.list_messages(OTHER, row.id) == []


def test_finalize_assistant_returns_none_when_not_running(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    begun = _begin(store, row.id)
    turn_id = begun.assistant_message.id

    done = store.finalize_assistant(
        USER, turn_id, status=MESSAGE_STATUS_COMPLETED, content="done"
    )
    again = store.finalize_assistant(
        USER, turn_id, status=MESSAGE_STATUS_COMPLETED, content="changed"
    )

    assert done is not None
    assert done.content == "done"
    assert done.ended_at is not None
    assert again is None
    assert store.get_running_turn(USER, row.id) is None


def test_finalize_assistant_returns_none_when_turn_is_foreign(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    begun = _begin(store, row.id)

    result = store.finalize_assistant(
        OTHER, begun.assistant_message.id, status=MESSAGE_STATUS_COMPLETED
    )

    assert result is None
    assert store.get_running_turn(USER, row.id) is begun.assistant_message


def test_finalize_assistant_raises_value_error_when_status_not_final(
    store: InMemoryBuilderStore,
) -> None:
    with pytest.raises(ValueError):
        store.finalize_assistant(USER, "t", status=MESSAGE_STATUS_RUNNING)


# --- Revisions ----------------------------------------------------------------


def test_insert_revision_numbers_from_max_plus_one_when_seed_is_zero(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(
        store,
        mode=SESSION_MODE_EDIT,
        seed_manifest={"id": "wf"},
        seed_manifest_hash="s",
    )

    first = _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h1")
    second = _revise(store, row.id, DRAFT_KIND_UNPROPOSED, "h2")

    assert (first.revision, second.revision) == (1, 2)


def test_insert_revision_numbers_from_one_when_no_seed(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    assert _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h1").revision == 1


def test_insert_revision_updates_session_when_revision_accepted(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h1", target_trust="system")
    _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h2")

    assert row.first_accepted_revision == 1
    assert row.target_trust == "system"
    assert row.linked_manifest_hash == "h2"


def test_insert_revision_links_hash_when_revision_is_undo(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h1")

    _revise(store, row.id, DRAFT_KIND_UNDO, "h0", undo_of_revision=1)

    assert row.linked_manifest_hash == "h0"
    assert row.first_accepted_revision == 1


def test_insert_revision_leaves_session_unchanged_when_unproposed(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    _revise(store, row.id, DRAFT_KIND_UNPROPOSED, "h1")

    assert row.linked_manifest_hash is None
    assert row.first_accepted_revision is None


def test_insert_revision_rejects_seed_kind_when_called_directly(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    with pytest.raises(ValueError):
        _revise(store, row.id, DRAFT_KIND_SEED, "h1")


def test_get_latest_revisions_returns_newest_per_kind_when_several_exist(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h1")
    newest = _revise(store, row.id, DRAFT_KIND_ACCEPTED, "h2")

    latest = store.get_latest_revisions(USER, row.id)

    assert latest.accepted is newest
    assert (latest.seed, latest.undo, latest.unproposed) == (None, None, None)
    assert store.get_latest_revisions(OTHER, row.id).accepted is None


# --- Summary and clarify count ------------------------------------------------


def test_summary_round_trips_when_set(store: InMemoryBuilderStore) -> None:
    row = _session(store)

    store.set_summary(USER, row.id, text="so far", through_seq=4)

    state = store.get_summary(USER, row.id)
    assert state is not None
    assert (state.text, state.through_seq) == ("so far", 4)
    assert store.get_summary(OTHER, row.id) is None


def test_set_summary_raises_not_found_when_session_is_foreign(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    with pytest.raises(SessionNotFoundError):
        store.set_summary(OTHER, row.id, text="x", through_seq=1)


def test_clarify_count_defaults_to_zero_and_updates_when_set(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)
    assert store.get_clarify_count(USER, row.id) == 0

    store.set_clarify_count(USER, row.id, 2)

    assert store.get_clarify_count(USER, row.id) == 2
    assert store.get_clarify_count(OTHER, row.id) is None


def test_set_clarify_count_raises_value_error_when_negative(
    store: InMemoryBuilderStore,
) -> None:
    row = _session(store)

    with pytest.raises(ValueError):
        store.set_clarify_count(USER, row.id, -1)


# --- Admission counts and sweep -----------------------------------------------


def test_count_user_messages_since_counts_only_window_and_user_rows(
    store: InMemoryBuilderStore, clock: _Clock
) -> None:
    row = _session(store)
    t0 = clock.now
    first = _begin(store, row.id, client_message_id="c1")
    store.finalize_assistant(
        USER, first.assistant_message.id, status=MESSAGE_STATUS_COMPLETED
    )
    clock.advance(minutes=10)
    _begin(store, row.id, client_message_id="c2")
    other_session = _session(store, OTHER)
    _begin(store, other_session.id, user_id=OTHER)

    in_window = clock.now - timedelta(minutes=5)

    assert store.count_user_messages_since(USER, t0) == 2
    assert store.count_user_messages_since(USER, in_window) == 1
    assert store.oldest_user_message_since(USER, in_window) == clock.now
    assert store.oldest_user_message_since(USER, clock.now + timedelta(days=1)) is None


def test_count_running_turns_counts_caller_rows_across_sessions(
    store: InMemoryBuilderStore,
) -> None:
    a1, a2 = _session(store), _session(store)
    _begin(store, a1.id)
    _begin(store, a2.id, client_message_id="c2")
    b1 = _session(store, OTHER)
    _begin(store, b1.id, user_id=OTHER)

    assert store.count_running_turns(USER) == 2
    assert store.count_running_turns(OTHER) == 1


def test_mark_running_interrupted_marks_every_users_running_rows_when_swept(
    store: InMemoryBuilderStore,
) -> None:
    a = _session(store)
    b = _session(store, OTHER)
    done = _begin(store, a.id, client_message_id="c0")
    store.finalize_assistant(
        USER, done.assistant_message.id, status=MESSAGE_STATUS_COMPLETED
    )
    live_a = _begin(store, a.id, client_message_id="c1")
    live_b = _begin(store, b.id, user_id=OTHER)
    assert len(store.list_running_assistant_rows()) == 2

    changed = store.mark_running_interrupted()

    assert changed == 2
    assert store.list_running_assistant_rows() == []
    for turn in (live_a, live_b):
        assert turn.assistant_message.status == MESSAGE_STATUS_INTERRUPTED
        assert turn.assistant_message.stop_reason == "restart"
        assert turn.assistant_message.ended_at is not None
    assert done.assistant_message.status == MESSAGE_STATUS_COMPLETED
    assert store.mark_running_interrupted() == 0


# --- Factory ------------------------------------------------------------------


def test_builders_return_unattached_orm_rows_with_required_columns_when_built() -> None:
    session = BuilderSessionFactory.build()
    user_msg = build_message(session_id=session.id, seq=1)
    tool = build_tool_row(session_id=session.id, seq=2, turn_id="t1")
    revision = build_revision(session_id=session.id)

    assert isinstance(session, WorkflowBuilderSession)
    assert session.owner_id == session.workspace_id == session.user_id
    assert isinstance(user_msg, WorkflowBuilderMessage)
    assert user_msg.status == "accepted"
    assert (tool.role, tool.turn_id) == ("tool", "t1")
    assert isinstance(revision, WorkflowBuilderDraft)
    assert revision.owner_id == revision.user_id

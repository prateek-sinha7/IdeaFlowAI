"""``BuilderStore`` against real PostgreSQL, with ``InMemoryBuilderStore`` as a twin.

Covers task 6.8 of the AI Workflow Builder spec (Req 2.6, 2.8, 20.16, 21.8, 21.10,
24.8, 31.7):

* owner filters: a foreign session looks like a missing one on every read, write
  and count (Req 2.6, 24.7);
* ``client_message_id`` uniqueness and the ``IntegrityError`` mapping to
  ``DuplicateClientMessageError`` (Req 21.10);
* the one-running-turn partial unique index, including real concurrent inserts, and
  the mapping to ``TurnRunningError`` (Req 21.8, 24.8);
* revision numbering ``max + 1``, including under concurrency;
* ``ON DELETE SET NULL`` on ``sessions.workflow_id`` by deleting a workflow row
  (Req 20.16);
* a keyset pagination walk with fixed examples (Req 2.8);
* account deletion through ``delete_user_dependents`` (Req 31.7).

Database: real PostgreSQL, never SQLite. The sibling ``conftest.py`` of this folder
shadows ``db_session`` with an in-memory SQLite engine; this module deliberately does
not use it. It builds a private throwaway database on the server from
``tests/integration/conftest.py`` (testcontainers, needs Docker, errors at setup
without it) or from ``PYTEST_POSTGRES_ADMIN_URL``, and upgrades it with Alembic to
head so the real migration DDL (partial indexes, foreign keys) is what runs.

Twin: tests that take the ``harness`` fixture run twice, once per backend
(``[postgres]`` and ``[in_memory]``) over the same sequence. The ``[in_memory]``
variants need no Docker and prove the fake behaves like PostgreSQL (open decision
6.6). Tests that take ``pg_harness`` are PostgreSQL only (threads, foreign keys,
account deletion, raw index checks).

The store commits for real, so rows are not rolled back between tests. Every test
creates its own users with unique ids, and the throwaway database is dropped when
the module finishes.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from alembic import command
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.workflow_builder.store import (
    BegunTurn,
    BuilderStore,
    DuplicateClientMessageError,
    InvalidCursorError,
    SessionNotFoundError,
    SummaryState,
    TurnRunningError,
)
from app.core.user_deletion import delete_user_dependents
from app.models.user import User
from app.models.workflow_builder import (
    DRAFT_KIND_ACCEPTED,
    DRAFT_KIND_SEED,
    DRAFT_KIND_UNDO,
    DRAFT_KIND_UNPROPOSED,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_RUNNING,
    SESSION_MODE_EDIT,
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)
from app.models.workflow_definition import WorkflowDefinition
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.integration.db.conftest import (
    alembic_config_for,
    postgres_admin_url,
    throwaway_database,
)

Store = BuilderStore | InMemoryBuilderStore

_RUNNING_INDEX = "uq_wb_messages_one_running"
_CLIENT_ID_INDEX = "uq_wb_messages_client_id"
_DRAFT_REVISION_CONSTRAINT = "uq_wb_drafts_session_revision"

# Fixed clock for the pagination examples. The microseconds are deliberate: they
# prove the cursor round-trips PostgreSQL's timestamptz precision exactly.
_BASE_TIME = datetime(2030, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)


# --- Harnesses: one interface over PostgreSQL and the fake ---------------------


class PostgresHarness:
    """A ``BuilderStore`` on a real database, plus the rows a test must seed by hand."""

    kind = "postgres"

    def __init__(self, engine: Engine) -> None:
        self.session_factory: sessionmaker[Session] = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )
        self._open: list[Session] = []
        self.store: BuilderStore = self.fresh()

    def fresh(self) -> BuilderStore:
        """A store on a new DB session (empty identity map): reads see what is committed."""
        db = self.session_factory()
        self._open.append(db)
        return BuilderStore(db)

    def new_user(self) -> str:
        """Insert a ``users`` row (sessions reference it) and return its id."""
        user_id = str(uuid.uuid4())
        with self.session_factory() as db:
            db.add(
                User(
                    id=user_id,
                    email=f"{user_id}@example.test",
                    cognito_sub=f"sub-{user_id}",
                )
            )
            db.commit()
        return user_id

    def set_session_updated_at(
        self, user_id: str, session_id: str, when: datetime
    ) -> None:
        """Write ``updated_at`` straight to the row (an explicit value skips ``onupdate``)."""
        with self.session_factory() as db:
            db.execute(
                update(WorkflowBuilderSession)
                .where(
                    WorkflowBuilderSession.id == session_id,
                    WorkflowBuilderSession.user_id == user_id,
                )
                .values(updated_at=when)
            )
            db.commit()

    def add_workflow(self, user_id: str) -> str:
        """Insert a saved ``workflows`` row owned by the user and return its id."""
        workflow_id = str(uuid.uuid4())
        with self.session_factory() as db:
            db.add(
                WorkflowDefinition(
                    id=workflow_id,
                    user_id=user_id,
                    owner_id=user_id,
                    workspace_id=user_id,
                    name=f"workflow-{workflow_id[:8]}",
                    agents="[]",
                    artifact_edges="[]",
                    source="user",
                )
            )
            db.commit()
        return workflow_id

    def close(self) -> None:
        for db in self._open:
            db.close()


class MemoryHarness:
    """The same interface over ``InMemoryBuilderStore`` (no database)."""

    kind = "in_memory"

    def __init__(self) -> None:
        self.store: Store = InMemoryBuilderStore()

    def fresh(self) -> Store:
        return self.store

    def new_user(self) -> str:
        return str(uuid.uuid4())

    def add_workflow(self, user_id: str) -> str:
        """A workflow id; the fake keeps no ``workflows`` table, so nothing is stored."""
        return str(uuid.uuid4())

    def set_session_updated_at(
        self, user_id: str, session_id: str, when: datetime
    ) -> None:
        row = self.store.get_session(user_id, session_id)
        assert row is not None
        row.updated_at = when  # type: ignore[assignment]

    def close(self) -> None:
        return None


Harness = PostgresHarness | MemoryHarness


@pytest.fixture(scope="module")
def builder_pg_engine(request: pytest.FixtureRequest) -> Generator[Engine, None, None]:
    """Engine on a throwaway PostgreSQL database migrated to Alembic head."""
    with throwaway_database(postgres_admin_url(request), "wbstore") as url:
        command.upgrade(alembic_config_for(url), "head")
        engine = create_engine(url, pool_pre_ping=True)
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture
def pg_harness(builder_pg_engine: Engine) -> Generator[PostgresHarness, None, None]:
    """PostgreSQL-only harness over the migrated throwaway database."""
    harness = PostgresHarness(builder_pg_engine)
    try:
        yield harness
    finally:
        harness.close()


@pytest.fixture(params=["postgres", "in_memory"])
def harness(request: pytest.FixtureRequest) -> Generator[Harness, None, None]:
    """The same test body on PostgreSQL and on the in-memory fake.

    The PostgreSQL engine is requested lazily, so ``-k in_memory`` needs no Docker.
    """
    if request.param == "in_memory":
        memory = MemoryHarness()
        yield memory
        memory.close()
        return
    postgres = PostgresHarness(request.getfixturevalue("builder_pg_engine"))
    try:
        yield postgres
    finally:
        postgres.close()


# --- Helpers ---------------------------------------------------------------------


def _new_session(
    store: Store, user_id: str, **overrides: Any
) -> WorkflowBuilderSession:
    return store.create_session(
        user_id, **BuilderSessionFactory.create_kwargs(**overrides)
    )


def _begin(
    store: Store,
    user_id: str,
    session_id: str,
    *,
    client_message_id: str | None = None,
    content: str = "build me a workflow",
) -> BegunTurn:
    return store.begin_turn(
        user_id,
        session_id,
        content=content,
        canvas_state=None,
        client_message_id=client_message_id,
        model_id="model-x",
        effort=None,
        skill_hash="skill-hash-1",
    )


def _finish(
    store: Store, user_id: str, turn: BegunTurn, status: str = "completed"
) -> None:
    row = store.finalize_assistant(
        user_id, str(turn.assistant_message.id), status=status, content="done"
    )
    assert row is not None


def _state(store: Store, user_id: str, session_id: str) -> tuple[int, int, int, int]:
    """(next_seq, turn_count, message rows, running turns) as stored."""
    row = store.get_session(user_id, session_id)
    assert row is not None
    return (
        int(row.next_seq),  # type: ignore[arg-type]
        int(row.turn_count),  # type: ignore[arg-type]
        len(store.list_messages(user_id, session_id)),
        store.count_running_turns(user_id),
    )


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _race(count: int, work: Callable[[int], Any]) -> list[Any]:
    """Run ``work(i)`` on ``count`` threads released together; exceptions are returned."""
    barrier = threading.Barrier(count)
    results: list[Any] = [None] * count

    def runner(index: int) -> None:
        try:
            barrier.wait(timeout=30)
            results[index] = work(index)
        except BaseException as exc:  # noqa: BLE001 - returned to the test for inspection
            results[index] = exc

    threads = [threading.Thread(target=runner, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads), "a racing thread hung"
    return results


def _insert_running_assistant(
    pg_harness: PostgresHarness, user_id: str, session_id: str, seq: int
) -> str:
    """Insert one running assistant row directly, bypassing the store's row lock."""
    row_id = str(uuid.uuid4())
    with pg_harness.session_factory() as db:
        db.add(
            WorkflowBuilderMessage(
                id=row_id,
                session_id=session_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=user_id,
                seq=seq,
                role=MESSAGE_ROLE_ASSISTANT,
                turn_id=row_id,
                status=MESSAGE_STATUS_RUNNING,
                content="",
            )
        )
        db.commit()
    return row_id


def _insert_user_row(
    pg_harness: PostgresHarness,
    user_id: str,
    session_id: str,
    seq: int,
    client_message_id: str | None,
) -> None:
    """Insert one user row directly."""
    row_id = str(uuid.uuid4())
    with pg_harness.session_factory() as db:
        db.add(
            WorkflowBuilderMessage(
                id=row_id,
                session_id=session_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=user_id,
                seq=seq,
                role=MESSAGE_ROLE_USER,
                turn_id=str(uuid.uuid4()),
                status="accepted",
                content="hi",
                client_message_id=client_message_id,
            )
        )
        db.commit()


# --- Owner filters (Req 2.6, 24.7) -------------------------------------------------


class TestOwnerFilters:
    def test_reads_return_nothing_when_caller_is_not_the_owner(
        self, harness: Harness
    ) -> None:
        store = harness.store
        owner, intruder = harness.new_user(), harness.new_user()
        session = _new_session(store, owner)
        sid = str(session.id)
        turn = _begin(store, owner, sid, client_message_id="cid-1")
        store.insert_tool_row(
            owner,
            sid,
            str(turn.assistant_message.id),
            status="ok",
            content="",
            tool={"tool": "x"},
        )
        store.insert_revision(
            owner,
            sid,
            kind=DRAFT_KIND_ACCEPTED,
            manifest={"id": "wf"},
            manifest_hash="h1",
        )
        reader = harness.fresh()
        since = datetime.now(timezone.utc) - timedelta(hours=1)

        assert reader.get_session(owner, sid) is not None
        assert reader.get_session(intruder, sid) is None
        assert reader.list_sessions(intruder).items == ()
        assert reader.get_message(intruder, str(turn.user_message.id)) is None
        assert reader.find_user_message_by_client_id(intruder, sid, "cid-1") is None
        assert reader.list_messages(intruder, sid) == []
        assert reader.list_tool_rows(intruder, str(turn.assistant_message.id)) == []
        assert reader.get_running_turn(intruder, sid) is None
        assert reader.get_latest_revision(intruder, sid, DRAFT_KIND_ACCEPTED) is None
        latest = reader.get_latest_revisions(intruder, sid)
        assert (latest.seed, latest.accepted, latest.undo, latest.unproposed) == (
            None,
            None,
            None,
            None,
        )
        assert reader.get_summary(intruder, sid) is None
        assert reader.get_clarify_count(intruder, sid) is None
        assert reader.count_user_messages_since(intruder, since) == 0
        assert reader.oldest_user_message_since(intruder, since) is None
        assert reader.count_running_turns(intruder) == 0

    def test_mutations_raise_not_found_and_change_nothing_when_caller_is_not_the_owner(
        self, harness: Harness
    ) -> None:
        store = harness.store
        owner, intruder = harness.new_user(), harness.new_user()
        sid = str(_new_session(store, owner).id)
        turn = _begin(store, owner, sid)
        turn_id = str(turn.assistant_message.id)
        before = _state(harness.fresh(), owner, sid)

        with pytest.raises(SessionNotFoundError):
            _begin(store, intruder, sid)
        with pytest.raises(SessionNotFoundError):
            store.insert_tool_row(
                intruder, sid, turn_id, status="ok", content="", tool={}
            )
        with pytest.raises(SessionNotFoundError):
            store.insert_revision(
                intruder, sid, kind=DRAFT_KIND_ACCEPTED, manifest={}, manifest_hash="h"
            )
        with pytest.raises(SessionNotFoundError):
            store.set_summary(intruder, sid, text="x", through_seq=1)
        with pytest.raises(SessionNotFoundError):
            store.set_clarify_count(intruder, sid, 2)
        assert store.finalize_assistant(intruder, turn_id, status="completed") is None
        assert store.delete_session(intruder, sid) is False

        reader = harness.fresh()
        assert _state(reader, owner, sid) == before
        running = reader.get_running_turn(owner, sid)
        assert running is not None and running.id == turn_id
        assert reader.get_summary(owner, sid) == SummaryState(
            text=None, through_seq=None
        )
        assert reader.get_clarify_count(owner, sid) == 0
        assert reader.get_latest_revision(owner, sid, DRAFT_KIND_ACCEPTED) is None

    def test_admission_counts_are_per_user_when_two_users_have_running_turns(
        self, harness: Harness
    ) -> None:
        store = harness.store
        first, second = harness.new_user(), harness.new_user()
        _begin(store, first, str(_new_session(store, first).id))
        _begin(store, second, str(_new_session(store, second).id))
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        reader = harness.fresh()

        assert reader.count_running_turns(first) == 1
        assert reader.count_running_turns(second) == 1
        assert reader.count_user_messages_since(first, since) == 1
        assert reader.count_user_messages_since(second, since) == 1


# --- client_message_id uniqueness (Req 21.10) --------------------------------------


class TestClientMessageIdUniqueness:
    def test_begin_turn_raises_duplicate_and_changes_nothing_when_id_reused_after_turn_ended(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)
        first = _begin(store, user, sid, client_message_id="cid-1")
        _finish(store, user, first)
        before = _state(harness.fresh(), user, sid)

        with pytest.raises(DuplicateClientMessageError):
            _begin(store, user, sid, client_message_id="cid-1")

        reader = harness.fresh()
        assert _state(reader, user, sid) == before == (3, 1, 2, 0)
        stored = reader.find_user_message_by_client_id(user, sid, "cid-1")
        assert stored is not None and stored.id == first.user_message.id

    def test_begin_turn_raises_duplicate_not_turn_running_when_both_apply(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)
        first = _begin(store, user, sid, client_message_id="cid-1")

        with pytest.raises(DuplicateClientMessageError):
            _begin(store, user, sid, client_message_id="cid-1")

        reader = harness.fresh()
        running = reader.get_running_turn(user, sid)
        assert running is not None and running.id == first.assistant_message.id
        assert _state(reader, user, sid) == (3, 1, 2, 1)

    def test_begin_turn_accepts_same_client_id_when_sessions_differ(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        first_sid = str(_new_session(store, user).id)
        second_sid = str(_new_session(store, user).id)

        first = _begin(store, user, first_sid, client_message_id="shared")
        second = _begin(store, user, second_sid, client_message_id="shared")

        assert first.user_message.id != second.user_message.id

    def test_begin_turn_accepts_repeated_turns_when_client_id_is_null(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)

        for _ in range(3):
            _finish(store, user, _begin(store, user, sid, client_message_id=None))

        assert _state(harness.fresh(), user, sid) == (7, 3, 6, 0)


# --- One running turn per session (Req 21.8, 24.8) ----------------------------------


class TestRunningTurnIndex:
    def test_begin_turn_raises_turn_running_and_changes_nothing_when_a_turn_is_running(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)
        first = _begin(store, user, sid, client_message_id="cid-1")

        with pytest.raises(TurnRunningError):
            _begin(store, user, sid, client_message_id="cid-2")

        reader = harness.fresh()
        assert _state(reader, user, sid) == (3, 1, 2, 1)
        assert reader.find_user_message_by_client_id(user, sid, "cid-2") is None
        running = reader.get_running_turn(user, sid)
        assert running is not None and running.id == first.assistant_message.id

    @pytest.mark.parametrize(
        "final_status", ["completed", "failed", "cancelled", "timed_out", "interrupted"]
    )
    def test_begin_turn_succeeds_when_previous_turn_reached_final_status(
        self, harness: Harness, final_status: str
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)
        _finish(store, user, _begin(store, user, sid), status=final_status)

        second = _begin(store, user, sid)

        assert (second.user_message.seq, second.assistant_message.seq) == (3, 4)
        assert _state(harness.fresh(), user, sid) == (5, 2, 4, 1)

    def test_finalize_assistant_returns_none_when_turn_already_finalised(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)
        turn = _begin(store, user, sid)
        turn_id = str(turn.assistant_message.id)
        assert store.finalize_assistant(user, turn_id, status="completed", content="a")

        again = store.finalize_assistant(user, turn_id, status="failed", content="b")

        stored = harness.fresh().get_message(user, turn_id)
        assert again is None
        assert stored is not None
        assert (stored.status, stored.content) == ("completed", "a")

    def test_begin_turn_allows_running_turns_when_sessions_differ(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        _begin(store, user, str(_new_session(store, user).id))
        _begin(store, user, str(_new_session(store, user).id))

        assert harness.fresh().count_running_turns(user) == 2

    def test_insert_tool_row_shares_the_sequence_when_rows_interleave(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)
        first = _begin(store, user, sid)
        first_id = str(first.assistant_message.id)
        tool = store.insert_tool_row(
            user, sid, first_id, status="ok", content="", tool={"tool": "propose_draft"}
        )
        _finish(store, user, first)
        _begin(store, user, sid)

        reader = harness.fresh()
        rows = reader.list_messages(user, sid)
        assert [r.seq for r in rows] == [1, 2, 3, 4, 5]
        assert [r.role for r in rows] == [
            MESSAGE_ROLE_USER,
            MESSAGE_ROLE_ASSISTANT,
            MESSAGE_ROLE_TOOL,
            MESSAGE_ROLE_USER,
            MESSAGE_ROLE_ASSISTANT,
        ]
        assert tool.seq == 3
        assert [r.seq for r in reader.list_messages(user, sid, after_seq=3)] == [4, 5]
        assert [r.id for r in reader.list_tool_rows(user, first_id)] == [tool.id]


class TestRunningTurnConcurrency:
    """Real concurrent transactions on PostgreSQL; the fake has no threads to race."""

    _THREADS = 6

    def test_begin_turn_admits_exactly_one_when_threads_race_with_distinct_client_ids(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)

        def work(index: int) -> BegunTurn:
            with pg_harness.session_factory() as db:
                return _begin(
                    BuilderStore(db), user, sid, client_message_id=f"cid-{index}"
                )

        results = _race(self._THREADS, work)

        winners = [r for r in results if isinstance(r, BegunTurn)]
        losers = [r for r in results if not isinstance(r, BegunTurn)]
        assert len(winners) == 1
        assert len(losers) == self._THREADS - 1
        assert all(isinstance(r, TurnRunningError) for r in losers), losers
        reader = pg_harness.fresh()
        assert _state(reader, user, sid) == (3, 1, 2, 1)
        running = reader.get_running_turn(user, sid)
        assert running is not None and running.id == winners[0].assistant_message.id

    def test_begin_turn_reports_duplicate_for_every_loser_when_threads_race_on_one_client_id(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)

        def work(_: int) -> BegunTurn:
            with pg_harness.session_factory() as db:
                return _begin(BuilderStore(db), user, sid, client_message_id="same")

        results = _race(self._THREADS, work)

        winners = [r for r in results if isinstance(r, BegunTurn)]
        losers = [r for r in results if not isinstance(r, BegunTurn)]
        assert len(winners) == 1
        assert all(isinstance(r, DuplicateClientMessageError) for r in losers), losers
        assert _state(pg_harness.fresh(), user, sid) == (3, 1, 2, 1)

    def test_running_index_admits_one_row_when_direct_inserts_race(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)

        results = _race(
            self._THREADS,
            lambda index: _insert_running_assistant(pg_harness, user, sid, 10 + index),
        )

        winners = [r for r in results if isinstance(r, str)]
        losers = [r for r in results if not isinstance(r, str)]
        assert len(winners) == 1
        assert all(isinstance(r, IntegrityError) for r in losers), losers
        assert {_constraint_name(r) for r in losers} == {_RUNNING_INDEX}
        running = pg_harness.fresh().get_running_turn(user, sid)
        assert running is not None and running.id == winners[0]

    def test_insert_revision_numbers_are_unique_and_gapless_when_threads_race(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)

        def work(index: int) -> WorkflowBuilderDraft:
            with pg_harness.session_factory() as db:
                return BuilderStore(db).insert_revision(
                    user,
                    sid,
                    kind=DRAFT_KIND_ACCEPTED,
                    manifest={"n": index},
                    manifest_hash=f"hash-{index}",
                )

        results = _race(self._THREADS, work)

        assert all(isinstance(r, WorkflowBuilderDraft) for r in results), results
        numbers = sorted(int(r.revision) for r in results)  # type: ignore[arg-type]
        assert numbers == list(range(1, self._THREADS + 1))
        newest = max(results, key=lambda r: int(r.revision))  # type: ignore[arg-type]
        session = pg_harness.fresh().get_session(user, sid)
        assert session is not None
        assert session.first_accepted_revision == 1
        assert session.linked_manifest_hash == newest.manifest_hash


class TestIntegrityErrorNames:
    """The store maps ``IntegrityError`` by index name; PostgreSQL must report those names."""

    def test_insert_names_running_index_when_second_running_row_inserted(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)
        _insert_running_assistant(pg_harness, user, sid, 1)

        with pytest.raises(IntegrityError) as excinfo:
            _insert_running_assistant(pg_harness, user, sid, 2)

        assert _constraint_name(excinfo.value) == _RUNNING_INDEX
        assert _RUNNING_INDEX in str(excinfo.value.orig)

    def test_insert_names_client_id_index_when_client_id_repeated_in_session(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)
        _insert_user_row(pg_harness, user, sid, 1, "dup")

        with pytest.raises(IntegrityError) as excinfo:
            _insert_user_row(pg_harness, user, sid, 2, "dup")

        assert _constraint_name(excinfo.value) == _CLIENT_ID_INDEX
        assert _CLIENT_ID_INDEX in str(excinfo.value.orig)

    def test_insert_accepts_many_rows_when_client_id_is_null(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)

        for seq in (1, 2, 3):
            _insert_user_row(pg_harness, user, sid, seq, None)

        assert len(pg_harness.fresh().list_messages(user, sid)) == 3

    def test_insert_names_revision_constraint_when_revision_number_repeated(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        sid = str(_new_session(pg_harness.store, user).id)
        pg_harness.store.insert_revision(
            user, sid, kind=DRAFT_KIND_ACCEPTED, manifest={}, manifest_hash="h1"
        )

        with (
            pytest.raises(IntegrityError) as excinfo,
            pg_harness.session_factory() as db,
        ):
            db.add(
                WorkflowBuilderDraft(
                    id=str(uuid.uuid4()),
                    session_id=sid,
                    user_id=user,
                    owner_id=user,
                    workspace_id=user,
                    revision=1,
                    kind=DRAFT_KIND_ACCEPTED,
                    manifest={},
                    manifest_hash="h2",
                )
            )
            db.commit()

        assert _constraint_name(excinfo.value) == _DRAFT_REVISION_CONSTRAINT


# --- Revision numbering --------------------------------------------------------------


class TestRevisionNumbering:
    def test_insert_revision_continues_after_seed_when_edit_session_has_a_seed(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(
            _new_session(
                store,
                user,
                mode=SESSION_MODE_EDIT,
                seed_manifest={"id": "wf", "v": 0},
                seed_manifest_hash="hash-0",
            ).id
        )

        accepted_1 = store.insert_revision(
            user,
            sid,
            kind=DRAFT_KIND_ACCEPTED,
            manifest={"v": 1},
            manifest_hash="hash-1",
            target_trust="builtin",
        )
        after_first = harness.fresh().get_session(user, sid)
        assert after_first is not None
        first_link = after_first.linked_manifest_hash
        unproposed = store.insert_revision(
            user,
            sid,
            kind=DRAFT_KIND_UNPROPOSED,
            manifest={"v": 2},
            manifest_hash="hash-2",
            source_file="/workflows/a.yaml",
        )
        after_unproposed = harness.fresh().get_session(user, sid)
        assert after_unproposed is not None
        unproposed_link = after_unproposed.linked_manifest_hash
        undo = store.insert_revision(
            user,
            sid,
            kind=DRAFT_KIND_UNDO,
            manifest={"v": 0},
            manifest_hash="hash-3",
            undo_of_revision=1,
        )
        accepted_4 = store.insert_revision(
            user,
            sid,
            kind=DRAFT_KIND_ACCEPTED,
            manifest={"v": 4},
            manifest_hash="hash-4",
        )

        assert [d.revision for d in (accepted_1, unproposed, undo, accepted_4)] == [
            1,
            2,
            3,
            4,
        ]
        assert first_link == "hash-1"
        assert unproposed_link == "hash-1"  # an unproposed draft does not move the link
        reader = harness.fresh()
        latest = reader.get_latest_revisions(user, sid)
        assert latest.seed is not None and latest.seed.revision == 0
        assert latest.seed.kind == DRAFT_KIND_SEED
        assert latest.accepted is not None and latest.accepted.revision == 4
        assert latest.undo is not None and latest.undo.revision == 3
        assert latest.unproposed is not None and latest.unproposed.revision == 2
        session = reader.get_session(user, sid)
        assert session is not None
        assert session.first_accepted_revision == 1
        assert session.linked_manifest_hash == "hash-4"
        assert session.target_trust == "builtin"

    def test_insert_revision_starts_at_one_when_session_has_no_seed(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)

        first = store.insert_revision(
            user, sid, kind=DRAFT_KIND_ACCEPTED, manifest={}, manifest_hash="h"
        )

        assert first.revision == 1
        assert harness.fresh().get_latest_revisions(user, sid).seed is None

    def test_insert_revision_numbers_each_session_separately_when_user_has_two(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        first_sid = str(_new_session(store, user).id)
        second_sid = str(_new_session(store, user).id)

        for sid in (first_sid, second_sid, first_sid):
            store.insert_revision(
                user, sid, kind=DRAFT_KIND_ACCEPTED, manifest={}, manifest_hash="h"
            )

        reader = harness.fresh()
        first_latest = reader.get_latest_revision(user, first_sid, DRAFT_KIND_ACCEPTED)
        second_latest = reader.get_latest_revision(
            user, second_sid, DRAFT_KIND_ACCEPTED
        )
        assert first_latest is not None and first_latest.revision == 2
        assert second_latest is not None and second_latest.revision == 1

    def test_insert_revision_raises_value_error_when_kind_is_seed(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user = harness.new_user()
        sid = str(_new_session(store, user).id)

        with pytest.raises(ValueError):
            store.insert_revision(
                user, sid, kind=DRAFT_KIND_SEED, manifest={}, manifest_hash="h"
            )

        assert harness.fresh().get_latest_revision(user, sid, DRAFT_KIND_SEED) is None


# --- ON DELETE SET NULL on the workflow link (Req 20.16) -------------------------------


class TestWorkflowLink:
    def test_delete_workflow_sets_session_link_to_null_when_session_is_linked(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()
        doomed = pg_harness.add_workflow(user)
        kept = pg_harness.add_workflow(user)
        store = pg_harness.store
        linked = _new_session(
            store,
            user,
            mode=SESSION_MODE_EDIT,
            workflow_id=doomed,
            linked_manifest_hash="hash-link",
            seed_manifest={"id": "wf"},
            seed_manifest_hash="hash-link",
        )
        other = _new_session(store, user, workflow_id=kept)
        linked_id, other_id = str(linked.id), str(other.id)
        _begin(store, user, linked_id)
        before = {
            f.session_id: f.turns_before_first_save
            for f in pg_harness.fresh().list_session_metric_facts(user)
        }
        assert before[linked_id] == 1

        with pg_harness.session_factory() as db:
            db.execute(
                delete(WorkflowDefinition).where(WorkflowDefinition.id == doomed)
            )
            db.commit()

        reader = pg_harness.fresh()
        after_linked = reader.get_session(user, linked_id)
        after_other = reader.get_session(user, other_id)
        assert after_linked is not None and after_other is not None
        assert after_linked.workflow_id is None
        assert after_linked.linked_manifest_hash == "hash-link"
        assert after_other.workflow_id == kept
        assert len(reader.list_messages(user, linked_id)) == 2
        assert reader.get_latest_revision(user, linked_id, DRAFT_KIND_SEED) is not None
        after = {
            f.session_id: f.turns_before_first_save
            for f in reader.list_session_metric_facts(user)
        }
        assert after[linked_id] is None
        assert after[other_id] == 0


# --- Metric facts and storage usage (Req 44.6, 44.7) ------------------------------------


class TestReportingReads:
    def test_metric_facts_and_storage_counts_agree_when_two_users_hold_rows(
        self, harness: Harness
    ) -> None:
        store = harness.store
        alice, bob = harness.new_user(), harness.new_user()
        saved_id = str(
            _new_session(store, alice, workflow_id=harness.add_workflow(alice)).id
        )
        unsaved_id = str(_new_session(store, alice).id)
        bob_session_id = str(_new_session(store, bob).id)
        passing = str(_begin(store, alice, saved_id).assistant_message.id)
        failing = str(_begin(store, alice, unsaved_id).assistant_message.id)
        # The gate stored the revision inside the call; the tool row follows it.
        store.insert_revision(
            alice,
            saved_id,
            kind=DRAFT_KIND_ACCEPTED,
            manifest={"id": "wf-a"},
            manifest_hash="h-a",
            source_turn_id=passing,
        )
        store.insert_tool_row(
            alice,
            saved_id,
            passing,
            status="ok",
            content="",
            tool={"tool": "propose_draft"},
        )
        # The failing turn's first call ended before any revision existed; a later call passed.
        store.insert_tool_row(
            alice,
            unsaved_id,
            failing,
            status="ok",
            content="",
            tool={"tool": "propose_draft"},
        )
        store.insert_tool_row(
            alice, unsaved_id, failing, status="ok", content="", tool={"tool": "other"}
        )
        store.insert_revision(
            alice,
            unsaved_id,
            kind=DRAFT_KIND_ACCEPTED,
            manifest={"id": "wf-b"},
            manifest_hash="h-b",
            source_turn_id=failing,
        )
        reader = harness.fresh()

        alice_sessions = {
            f.session_id: f.turns_before_first_save
            for f in reader.list_session_metric_facts(alice)
        }
        alice_turns = {
            f.turn_id: f.first_call_passed for f in reader.list_turn_gate_facts(alice)
        }
        assert alice_sessions == {saved_id: 1, unsaved_id: None}
        assert alice_turns == {passing: True, failing: False}
        assert {
            f.session_id: f.turns_before_first_save
            for f in reader.list_session_metric_facts(bob)
        } == {bob_session_id: None}
        assert reader.list_turn_gate_facts(bob) == []

        usage = {r.user_id: r for r in reader.storage_usage_by_user()}
        assert (
            usage[alice].session_count,
            usage[alice].message_count,
            usage[alice].draft_count,
        ) == (2, 7, 2)
        assert (
            usage[bob].session_count,
            usage[bob].message_count,
            usage[bob].draft_count,
        ) == (1, 0, 0)
        # Byte sizes are approximate on the fake, so only their order is compared.
        assert usage[alice].db_bytes > usage[bob].db_bytes > 0


# --- Pagination walk with fixed examples (Req 2.8) --------------------------------------


# label -> minutes after the base time. b, c and d tie, as do e and f, so the
# (updated_at DESC, id ASC) tie-break decides the order inside a group.
_PAGINATION_EXAMPLE: dict[str, int] = {
    "a": 0,
    "b": 5,
    "c": 5,
    "d": 5,
    "e": 3,
    "f": 3,
    "g": 10,
}
_OFFSETS_DESC = [10, 5, 5, 5, 3, 3, 0]


def _walk(
    reader: Store, user_id: str, limit: int | None
) -> tuple[list[list[str]], list[str | None]]:
    """Follow ``next_cursor`` to the end; return the ids per page and each page's cursor."""
    pages: list[list[str]] = []
    cursors: list[str | None] = []
    cursor: str | None = None
    for _ in range(20):  # a safe bound: seven rows can never need this many pages
        page = reader.list_sessions(user_id, limit=limit, cursor=cursor)
        pages.append([str(s.id) for s in page.items])
        cursors.append(page.next_cursor)
        if page.next_cursor is None:
            return pages, cursors
        cursor = page.next_cursor
    raise AssertionError("pagination walk did not terminate")


class TestPaginationWalk:
    @pytest.fixture
    def example(self, harness: Harness) -> tuple[Harness, str, dict[str, int], str]:
        """Seven sessions with fixed ``updated_at`` values plus one foreign tied session."""
        store = harness.store
        user, other = harness.new_user(), harness.new_user()
        minutes_by_id: dict[str, int] = {}
        for label, minutes in _PAGINATION_EXAMPLE.items():
            sid = str(_new_session(store, user, title=f"session {label}").id)
            minutes_by_id[sid] = minutes
            harness.set_session_updated_at(
                user, sid, _BASE_TIME + timedelta(minutes=minutes)
            )
        foreign = str(_new_session(store, other, title="foreign").id)
        harness.set_session_updated_at(
            other, foreign, _BASE_TIME + timedelta(minutes=5)
        )
        return harness, user, minutes_by_id, foreign

    @pytest.mark.parametrize(
        ("limit", "expected_sizes"),
        [
            (1, [1, 1, 1, 1, 1, 1, 1]),
            (2, [2, 2, 2, 1]),
            (3, [3, 3, 1]),
            (7, [7]),
            (50, [7]),
        ],
    )
    def test_list_sessions_walks_every_row_once_in_order_when_paged_with_fixed_limit(
        self,
        example: tuple[Harness, str, dict[str, int], str],
        limit: int,
        expected_sizes: list[int],
    ) -> None:
        harness, user, minutes_by_id, foreign = example
        reader = harness.fresh()
        reference = [str(s.id) for s in reader.list_sessions(user, limit=50).items]

        pages, cursors = _walk(reader, user, limit)

        flat = [sid for page in pages for sid in page]
        assert [len(p) for p in pages] == expected_sizes
        assert cursors[-1] is None
        assert all(c is not None for c in cursors[:-1])
        assert sorted(flat) == sorted(minutes_by_id)  # complete, no duplicates
        assert foreign not in flat
        assert [minutes_by_id[sid] for sid in flat] == _OFFSETS_DESC
        assert flat == reference  # ties break the same way on every page size

    def test_list_sessions_returns_default_page_when_limit_is_omitted(
        self, example: tuple[Harness, str, dict[str, int], str]
    ) -> None:
        harness, user, minutes_by_id, _ = example

        page = harness.fresh().list_sessions(user)

        assert len(page.items) == len(minutes_by_id)
        assert page.next_cursor is None

    def test_list_sessions_clamps_page_to_one_when_limit_is_zero(
        self, example: tuple[Harness, str, dict[str, int], str]
    ) -> None:
        harness, user, _, _ = example

        page = harness.fresh().list_sessions(user, limit=0)

        assert len(page.items) == 1
        assert page.next_cursor is not None

    def test_list_sessions_raises_invalid_cursor_when_cursor_is_malformed(
        self, harness: Harness
    ) -> None:
        user = harness.new_user()

        with pytest.raises(InvalidCursorError):
            harness.fresh().list_sessions(user, cursor="not-a-cursor")

    def test_list_sessions_returns_empty_page_when_user_has_no_sessions(
        self, harness: Harness
    ) -> None:
        page = harness.fresh().list_sessions(harness.new_user())

        assert page.items == ()
        assert page.next_cursor is None

    def test_list_sessions_returns_only_linked_own_sessions_when_workflow_id_given(
        self, harness: Harness
    ) -> None:
        store = harness.store
        user, other = harness.new_user(), harness.new_user()
        target, unrelated = harness.add_workflow(user), harness.add_workflow(user)
        linked = [
            str(_new_session(store, user, workflow_id=target).id) for _ in range(3)
        ]
        _new_session(store, user, workflow_id=unrelated)
        _new_session(store, user)
        _new_session(store, other, workflow_id=harness.add_workflow(other))

        first = harness.fresh().list_sessions(user, limit=2, workflow_id=target)
        second = harness.fresh().list_sessions(
            user, limit=2, cursor=first.next_cursor, workflow_id=target
        )
        foreign = harness.fresh().list_sessions(other, workflow_id=target)

        assert sorted(str(s.id) for s in first.items + second.items) == sorted(linked)
        assert second.next_cursor is None
        assert foreign.items == ()


# --- Account deletion (Req 31.7) -----------------------------------------------------------


_BUILDER_MODELS = (
    ("workflow_builder_messages", WorkflowBuilderMessage),
    ("workflow_builder_drafts", WorkflowBuilderDraft),
    ("workflow_builder_sessions", WorkflowBuilderSession),
)


def _builder_row_counts(pg_harness: PostgresHarness, user_id: str) -> dict[str, int]:
    with pg_harness.session_factory() as db:
        counts = {
            name: int(
                db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.user_id == user_id)
                )
                or 0
            )
            for name, model in _BUILDER_MODELS
        }
        counts["workflows"] = int(
            db.scalar(
                select(func.count())
                .select_from(WorkflowDefinition)
                .where(WorkflowDefinition.user_id == user_id)
            )
            or 0
        )
    return counts


def _seed_builder_account(pg_harness: PostgresHarness) -> str:
    """A user with 2 sessions, 5 messages (2 turns + 1 tool row), 2 revisions, 1 workflow."""
    store = pg_harness.store
    user = pg_harness.new_user()
    workflow_id = pg_harness.add_workflow(user)
    edit_sid = str(
        _new_session(
            store,
            user,
            mode=SESSION_MODE_EDIT,
            workflow_id=workflow_id,
            seed_manifest={"id": "wf"},
            seed_manifest_hash="hash-0",
        ).id
    )
    turn = _begin(store, user, edit_sid)
    store.insert_tool_row(
        user,
        edit_sid,
        str(turn.assistant_message.id),
        status="ok",
        content="",
        tool={"tool": "propose_draft"},
    )
    store.insert_revision(
        user,
        edit_sid,
        kind=DRAFT_KIND_ACCEPTED,
        manifest={"id": "wf"},
        manifest_hash="hash-1",
    )
    _begin(store, user, str(_new_session(store, user).id))
    return user


class TestAccountDeletion:
    _EXPECTED = {
        "workflow_builder_messages": 5,
        "workflow_builder_drafts": 2,
        "workflow_builder_sessions": 2,
        "workflows": 1,
    }

    def test_delete_user_dependents_removes_builder_rows_when_account_is_deleted(
        self, pg_harness: PostgresHarness
    ) -> None:
        victim = _seed_builder_account(pg_harness)
        bystander = _seed_builder_account(pg_harness)
        assert _builder_row_counts(pg_harness, victim) == self._EXPECTED

        with pg_harness.session_factory() as db:
            counts = delete_user_dependents(db, victim)
            db.query(User).filter(User.id == victim).delete(synchronize_session=False)
            db.commit()

        assert counts == self._EXPECTED
        assert _builder_row_counts(pg_harness, victim) == dict.fromkeys(
            self._EXPECTED, 0
        )
        assert _builder_row_counts(pg_harness, bystander) == self._EXPECTED
        with pg_harness.session_factory() as db:
            assert db.get(User, victim) is None
            assert db.get(User, bystander) is not None

    def test_delete_user_dependents_keeps_rows_when_caller_rolls_back(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = _seed_builder_account(pg_harness)

        with pg_harness.session_factory() as db:
            counts = delete_user_dependents(db, user)
            db.rollback()

        assert counts == self._EXPECTED
        assert _builder_row_counts(pg_harness, user) == self._EXPECTED

    def test_delete_user_dependents_omits_builder_keys_when_user_has_no_builder_data(
        self, pg_harness: PostgresHarness
    ) -> None:
        user = pg_harness.new_user()

        with pg_harness.session_factory() as db:
            counts = delete_user_dependents(db, user)
            db.commit()

        assert counts == {}

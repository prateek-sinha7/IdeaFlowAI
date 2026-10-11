"""tests/integration/repositories/test_authz_bounded_calls_db.py — A16 ``ScopedStore`` reads over a real DB.

Both acquisition modes (session-injected and session-owned/threaded) against an
in-memory SQLite database. Split out of ``tests/unit/test_authz_bounded_calls.py``:
these tests open a real database connection, which the unit I/O guard
(``tests/unit/conftest.py``) correctly refuses. The blocked-call / timeout tests,
which never touch a database, stay in the unit module. Test bodies are
byte-identical to their originals.
"""

from __future__ import annotations


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from app.models.database import Base
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def db_factory(monkeypatch):
    """In-memory SQLite (StaticPool, shared connection) wired into
    ``app.models.database.SessionLocal`` so the owned/threaded ``ScopedStore``
    path (session=None) hits THIS DB. Mirrors
    ``tests/unit/test_revision_intelligence.py``'s ``db_factory`` fixture."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(
        "app.models.database.SessionLocal", TestingSession, raising=False
    )
    try:
        yield TestingSession
    finally:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """In-memory SQLite session for the session-INJECTED acquisition mode
    (mirrors ``tests/unit/test_run_events.py``'s ``db_session`` fixture)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed_run(
    session_factory, *, run_id: str, owner_id: str, workspace_id: str
) -> None:
    s = session_factory() if callable(session_factory) else session_factory
    s.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="t",
            type="prototype",
            status="running",
            input="idea",
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
    )
    s.commit()
    if s is not session_factory:
        s.close()


@pytest.mark.asyncio
async def test_assert_owns_cross_owner_raises_same_permission_error(db_factory):
    """``assert_owns`` on a parent owned by a DIFFERENT owner raises
    ``PermissionError`` with the pre-fix message shape (D-07), unaffected by
    the off-loop execution change (only WHERE the query runs changed)."""
    _seed_run(db_factory, run_id="parent-1", owner_id="alice", workspace_id="ws-1")

    attacker_store = ScopedStore(owner_id="mallory", workspace_id="ws-9")

    with pytest.raises(PermissionError) as exc_info:
        await attacker_store.assert_owns("parent-1")

    msg = str(exc_info.value)
    assert "mallory" in msg
    assert "parent-1" in msg
    assert "alice" in msg


@pytest.mark.asyncio
async def test_assert_owns_same_owner_does_not_raise(db_factory):
    """The non-denied branch is unaffected: a same-owner parent returns ``None``."""
    _seed_run(db_factory, run_id="parent-2", owner_id="alice", workspace_id="ws-1")

    owner_store = ScopedStore(owner_id="alice", workspace_id="ws-1")
    assert await owner_store.assert_owns("parent-2") is None


@pytest.mark.asyncio
async def test_read_events_returns_same_rows_session_injected(db_session):
    """Session-INJECTED mode (endpoint path) runs in-line, unchanged."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    for seq in range(1, 4):
        await store.append_event("run-1", seq, f"evt-{seq}", "t", {"seq": seq})

    rows = await store.read_events("run-1", after_seq=0)
    assert [r.seq for r in rows] == [1, 2, 3]
    assert [r.event_id for r in rows] == ["evt-1", "evt-2", "evt-3"]


@pytest.mark.asyncio
async def test_read_events_returns_same_rows_session_owned_threaded(db_factory):
    """Session-OWNED mode (engine path / session-less SSE store) now runs
    threaded — must return the identical rows as the session-injected mode."""
    _seed_run(db_factory, run_id="run-2", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1")  # session=None

    for seq in range(1, 4):
        await store.append_event("run-2", seq, f"evt-{seq}", "t", {"seq": seq})

    rows = await store.read_events("run-2", after_seq=0)
    assert [r.seq for r in rows] == [1, 2, 3]
    assert [r.event_id for r in rows] == ["evt-1", "evt-2", "evt-3"]

    # Cross-owner read still resolves to nothing (default-deny unaffected).
    other = ScopedStore(owner_id="bob", workspace_id="ws-1")
    assert await other.read_events("run-2", after_seq=0) == []


@pytest.mark.asyncio
async def test_get_run_returns_same_row_both_modes(db_factory):
    """``get_run`` (the SSE-attach hot path, A12 candidate 2) returns the same
    row whether the session is injected or owned/threaded."""
    _seed_run(db_factory, run_id="run-3", owner_id="alice", workspace_id="ws-1")

    owned_store = ScopedStore(owner_id="alice", workspace_id="ws-1")
    row = await owned_store.get_run("run-3")
    assert row is not None
    assert row.id == "run-3"

    session = db_factory()
    try:
        injected_store = ScopedStore(
            owner_id="alice", workspace_id="ws-1", session=session
        )
        row2 = await injected_store.get_run("run-3")
        assert row2 is not None
        assert row2.id == "run-3"
    finally:
        session.close()

    cross_owner_store = ScopedStore(owner_id="mallory", workspace_id="ws-9")
    assert await cross_owner_store.get_run("run-3") is None

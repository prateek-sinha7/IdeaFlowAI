"""tests/unit/test_run_events.py — durable run_events seq/event_id log (PERSIST-03).

Phase 5 (05-04) introduced the SINGLE per-run event sink at the ``execute()`` emit
boundary: every emitted engine event is stamped with a monotonic per-run ``seq``
(1,2,3,… — contiguous deltas==1, SAFE-03) plus a unique ``event_id`` (uuid —
idempotent replay), then persisted to ``run_events`` via the owner+workspace-scoped
``ScopedStore`` (AUTHZ-01). This suite covers PERSIST-03 directly at the sink +
``append_event`` layer (no live LLM / Bedrock):

1. Persisted rows carry contiguous per-run ``seq`` (deltas==1 from 1).
2. Each row carries a unique ``event_id``.
3. Rows carry ``type`` + ``payload_json`` + ``owner_id`` + ``workspace_id``.
4. Read-back via ``ScopedStore.read_events(run_id, after_seq=k)`` returns ONLY
   ``seq > k`` rows, ascending (the API-05 idempotent-replay filter).
5. The engine's ``_RunEventSink`` stamps + persists when armed, and DEGRADES
   gracefully (no raise) when the persist fails — the byte-identity / parity
   guard (INV-3): a DB/FK failure must never break the live stream.

Offline / in-memory SQLite / no API key — the ``backend:characterization`` job.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from agents.execution_engine.engine import _RunEventSink
from app.models.database import Base
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# In-memory DB fixture (single shared StaticPool connection)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def db_session():
    """In-memory SQLite session with all Phase-5 tables created (StaticPool so the
    seeded run row and the helper reads share one connection)."""
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


def _seed_run(session, *, run_id: str, owner_id: str, workspace_id: str) -> None:
    """Insert the parent ``workflow_runs`` row (the run_events FK target)."""
    session.add(
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
    session.commit()


# ════════════════════════════════════════════════════════════════════════════
# append_event — durable log shape + scoped read-back
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_append_event_persists_contiguous_seq_and_unique_event_id(db_session):
    """Five appended events → five rows with contiguous seq 1..5 and unique
    event_ids, each carrying type + payload + owner/workspace (PERSIST-03)."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    appended_event_ids: list[str] = []
    for seq in range(1, 6):
        eid = str(uuid.uuid4())
        appended_event_ids.append(eid)
        await store.append_event(
            "run-1", seq, eid, f"event_type_{seq}", {"seq_echo": seq, "k": "v"}
        )

    rows = (
        db_session.query(RunEvent)
        .filter(RunEvent.run_id == "run-1")
        .order_by(RunEvent.seq.asc())
        .all()
    )
    assert len(rows) == 5

    # (a) contiguous per-run seq, deltas == 1 from 1
    seqs = [r.seq for r in rows]
    assert seqs == [1, 2, 3, 4, 5]
    deltas = [b - a for a, b in zip(seqs, seqs[1:], strict=False)]
    assert all(d == 1 for d in deltas), f"seq not contiguous: {seqs!r}"

    # (b) each row has a unique event_id (the uuids we appended)
    row_event_ids = [r.event_id for r in rows]
    assert len(set(row_event_ids)) == 5
    assert row_event_ids == appended_event_ids

    # (c) rows carry type + payload_json + owner_id + workspace_id
    for r in rows:
        assert r.type == f"event_type_{r.seq}"
        assert r.payload_json == {"seq_echo": r.seq, "k": "v"}
        assert r.owner_id == "alice"
        assert r.workspace_id == "ws-1"


@pytest.mark.asyncio
async def test_read_events_after_seq_returns_only_greater_ascending(db_session):
    """read_events(run, after_seq=k) returns only seq > k, ascending (API-05)."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    for seq in range(1, 6):
        await store.append_event(
            "run-1", seq, str(uuid.uuid4()), f"t{seq}", {"seq": seq}
        )

    after_2 = await store.read_events("run-1", after_seq=2)
    assert [r.seq for r in after_2] == [3, 4, 5]  # only seq > 2, ascending

    after_0 = await store.read_events("run-1", after_seq=0)
    assert [r.seq for r in after_0] == [1, 2, 3, 4, 5]  # full replay

    after_5 = await store.read_events("run-1", after_seq=5)
    assert after_5 == []  # nothing past the last event (idempotent re-replay)


@pytest.mark.asyncio
async def test_read_events_cross_owner_denied(db_session):
    """A second owner cannot read the first owner's run_events (default-deny)."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store_a = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store_a.append_event("run-1", 1, str(uuid.uuid4()), "t1", {"x": 1})

    store_b = ScopedStore(owner_id="bob", workspace_id="ws-1", session=db_session)
    assert await store_b.read_events("run-1", after_seq=0) == []  # cross-owner → []


# ════════════════════════════════════════════════════════════════════════════
# _RunEventSink — the engine's emit-boundary sink (stamp + persist + degrade)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_run_event_sink_persists_when_armed(db_session):
    """The engine sink, ARMED with a scoped store + run id, persists each stamped
    event to run_events (the live PERSIST-03 path)."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    sink = _RunEventSink()
    sink.arm(store, "run-1")

    for seq in range(1, 4):
        await sink.persist(seq, str(uuid.uuid4()), "agent_chunk", {"seq": seq})

    rows = (
        db_session.query(RunEvent)
        .filter(RunEvent.run_id == "run-1")
        .order_by(RunEvent.seq.asc())
        .all()
    )
    assert [r.seq for r in rows] == [1, 2, 3]
    assert all(r.type == "agent_chunk" for r in rows)


@pytest.mark.asyncio
async def test_run_event_sink_unarmed_is_noop():
    """An un-armed sink (no store/run id) silently no-ops — never raises."""
    sink = _RunEventSink()
    # Must not raise even though nothing is persisted.
    await sink.persist(1, str(uuid.uuid4()), "agent_start", {"k": "v"})


@pytest.mark.asyncio
async def test_run_event_sink_degrades_on_db_persist_failure():
    """A DB persist FAILURE (the offline harness has no workflow_runs/run_events
    schema → SQLAlchemyError) is degraded to a warning — the byte-identity / parity
    guard (INV-3): the live stream must never break on a DB error. WR-02: the
    degrade is narrowed to the SQLAlchemy error family."""
    from sqlalchemy.exc import OperationalError

    class _BoomStore:
        async def append_event(self, *a, **k):
            raise OperationalError("no such table: run_events", None, Exception())

    sink = _RunEventSink()
    sink.arm(_BoomStore(), "run-1")  # type: ignore[arg-type]
    # Must NOT raise — the DB failure degrades to a warning log.
    await sink.persist(1, str(uuid.uuid4()), "agent_complete", {"k": "v"})


@pytest.mark.asyncio
async def test_run_event_sink_reraises_non_db_persist_failure():
    """WR-02: a NON-DB persist failure (a real bug — not the offline-harness DB
    condition) must PROPAGATE, not be masked as a silent no-op."""

    class _BoomStore:
        async def append_event(self, *a, **k):
            raise RuntimeError("unexpected non-DB failure")

    sink = _RunEventSink()
    sink.arm(_BoomStore(), "run-1")  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="unexpected non-DB failure"):
        await sink.persist(1, str(uuid.uuid4()), "agent_complete", {"k": "v"})


# ════════════════════════════════════════════════════════════════════════════
# CR-03 (Phase 29) — per-run uniqueness backstops + serialized seq allocation
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_run_events_reject_duplicate_seq_and_event_id(db_session):
    """The additive (run_id, seq) + (run_id, event_id) unique constraints reject a
    racing duplicate insert LOUDLY (IntegrityError) instead of silently succeeding
    twice — the CR-03 backstop the chat-lane writers rely on."""
    from sqlalchemy.exc import IntegrityError

    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.append_event("run-1", 1, "e1", "t", {"k": 1})

    # Duplicate (run_id, seq) — different event_id — must fail loudly.
    with pytest.raises(IntegrityError):
        await store.append_event("run-1", 1, "e2", "t", {"k": 2})
    db_session.rollback()

    # Duplicate (run_id, event_id) — different seq — must fail loudly.
    with pytest.raises(IntegrityError):
        await store.append_event("run-1", 2, "e1", "t", {"k": 3})
    db_session.rollback()

    # The original row is intact; no duplicate landed.
    rows = db_session.query(RunEvent).filter(RunEvent.run_id == "run-1").all()
    assert len(rows) == 1
    assert (rows[0].seq, rows[0].event_id) == (1, "e1")


@pytest.mark.asyncio
async def test_append_event_next_seq_allocates_and_is_idempotent(db_session):
    """append_event_next_seq allocates the next contiguous per-run seq and is a no-op
    on a replayed event_id (no second row) — the D-01 idempotency the chat up-channel
    and narrator both depend on."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    created, seq = await store.append_event_next_seq(
        "run-1", event_id="chat:m1", type="chat_message", payload_json={"n": 1}
    )
    assert (created, seq) == (True, 1)

    # Replay of the SAME event_id → no-op, same seq, no second row.
    created2, seq2 = await store.append_event_next_seq(
        "run-1", event_id="chat:m1", type="chat_message", payload_json={"n": 1}
    )
    assert (created2, seq2) == (False, 1)
    assert db_session.query(RunEvent).filter(RunEvent.run_id == "run-1").count() == 1

    # A distinct event_id allocates the next contiguous seq.
    created3, seq3 = await store.append_event_next_seq(
        "run-1", event_id="chat:m2", type="chat_message", payload_json={"n": 2}
    )
    assert (created3, seq3) == (True, 2)


@pytest.mark.asyncio
async def test_append_event_next_seq_retries_past_a_raced_seq(db_session):
    """When a concurrent writer already took the seq this writer computed (its read was
    stale), the append hits the (run_id, seq) constraint and the writer RETRIES past the
    new tail — it never persists a duplicate seq nor raises. Simulates the engine sink
    winning the race by forcing the first read to be stale."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    # A concurrent (engine) writer already occupies seq 1.
    await store.append_event("run-1", 1, "engine-1", "agent_chunk", {"seq": 1})

    # Make ONLY the first read stale (empty) so the writer computes seq=1 → collides →
    # then re-reads the real tail (seq 1 present) → recomputes seq=2 → succeeds.
    calls = {"n": 0}
    real_read = store.read_events

    async def _stale_first_read(run_id, after_seq):
        calls["n"] += 1
        if calls["n"] == 1:
            return []  # stale snapshot: misses the engine's seq-1 row
        return await real_read(run_id, after_seq=after_seq)

    store.read_events = _stale_first_read  # type: ignore[assignment]

    created, seq = await store.append_event_next_seq(
        "run-1", event_id="chat:m1", type="chat_message", payload_json={"n": 1}
    )
    assert created is True
    assert seq == 2, "retry must allocate past the concurrently-taken seq"
    assert calls["n"] >= 2, "a seq collision must have forced a re-read (retry)"

    # Exactly two rows with DISTINCT seqs — no duplicate seq persisted.
    rows = (
        db_session.query(RunEvent)
        .filter(RunEvent.run_id == "run-1")
        .order_by(RunEvent.seq.asc())
        .all()
    )
    assert [r.seq for r in rows] == [1, 2]

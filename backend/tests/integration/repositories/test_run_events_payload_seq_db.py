"""ISS-135 (QA-KB-007) — payload_json.seq must equal run_events.seq after a retry.

Offline, in-memory SQLite. Asserts CORRECT behaviour; regression guard for ISS-135 (fixed).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from agents.execution_engine.engine import ExecutionEngine, _RunEventSink
from app.models.database import Base
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    session.add(
        WorkflowRun(
            id="run-1",
            user_id="alice",
            title="t",
            type="prototype",
            status="running",
            input="idea",
            owner_id="alice",
            workspace_id="ws-1",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.mark.issue("ISS-135")
async def test_store_retry_restamps_payload_seq(db_session):
    """ISS-135 — a retried append must persist payload.seq == the landed row.seq."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.append_event("run-1", 1, "a", "t", {"seq": 1})
    landed = await store.append_event_at_or_after("run-1", 1, "b", "t", {"seq": 1})
    db_session.expire_all()
    seq, payload = db_session.execute(
        text("SELECT seq, payload_json FROM run_events WHERE event_id = 'b'")
    ).one()
    payload = json.loads(payload) if isinstance(payload, str) else payload
    assert landed == seq == 2
    assert payload["seq"] == seq


@pytest.mark.issue("ISS-135")
async def test_execute_wrapper_stored_payload_seq_matches_row(db_session, monkeypatch):
    """ISS-135 — through the real execute() wrapper, every stored payload.seq == row.seq."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    async def _scripted_impl(self, **kwargs):
        kwargs["_sink"].arm(store, "run-1")
        yield {"type": "review_gate_ready", "data": {"gate_key": "run-1:a"}}
        await store.append_event_next_seq(
            "run-1", event_id="chat:m1", type="chat_message", payload_json={"t": "stop"}
        )
        yield {"type": "pipeline_cancelled", "data": {}}
        yield {"type": "agent_chunk", "data": {}}

    monkeypatch.setattr(ExecutionEngine, "_execute_impl", _scripted_impl)
    _ = [
        e
        async for e in ExecutionEngine().execute(
            agents=[], user_message="", pipeline_run_id="run-1"
        )
    ]
    db_session.expire_all()
    rows = db_session.query(RunEvent).order_by(RunEvent.seq.asc()).all()
    stamped = [r for r in rows if "seq" in (r.payload_json or {})]
    assert stamped
    for r in stamped:
        assert r.payload_json["seq"] == r.seq, f"{r.type}: payload.seq != row.seq"


def _stored(session, event_id):
    """The STORED row for event_id as (seq, payload), or None -- never the dict passed in."""
    session.expire_all()
    row = session.execute(
        text("SELECT seq, payload_json FROM run_events WHERE event_id = :e"),
        {"e": event_id},
    ).one_or_none()
    if row is None:
        return None
    payload = json.loads(row[1]) if isinstance(row[1], str) else row[1]
    return row[0], payload


def _stale_first_probe(store, stale_tail):
    """Make ONLY the first tail probe report ``stale_tail`` (the race), count all probes.
    ``stale_tail=None`` leaves every probe real and only counts them."""
    real, calls = store._max_event_seq, []

    async def _probe(run_id):
        calls.append(run_id)
        if stale_tail is not None and len(calls) == 1:
            return stale_tail
        return await real(run_id)

    store._max_event_seq = _probe
    return calls


@pytest.mark.issue("ISS-907")
async def test_retry_restamps_a_copy_and_leaves_the_callers_dict_alone(db_session):
    """A: FIX-692 constraint 1 -- the dict passed in is the live frame."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.append_event("run-1", 1, "a", "t", {"seq": 1})
    frame = {"seq": 1, "x": "y"}
    landed = await store.append_event_at_or_after("run-1", 1, "b", "t", frame)
    assert landed == 2
    assert _stored(db_session, "b") == (2, {"seq": 2, "x": "y"})
    assert frame == {"seq": 1, "x": "y"}


@pytest.mark.issue("ISS-907")
async def test_two_hop_retry_restamps_the_final_landed_seq(db_session):
    """B: FIX-692 constraint 2 -- the re-stamp runs on EVERY hop, not just the first."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    for n in (1, 2, 3):
        await store.append_event("run-1", n, f"e{n}", "t", {"seq": n})
    probes = _stale_first_probe(store, stale_tail=1)
    landed = await store.append_event_at_or_after("run-1", 1, "z", "t", {"seq": 1})
    assert len(probes) == 2, "the stale probe must have forced a second hop"
    assert landed == 4
    assert _stored(db_session, "z") == (4, {"seq": 4})


@pytest.mark.issue("ISS-907")
async def test_exhaustion_raises_the_dbs_own_rejection_and_keeps_the_callers_seq(
    db_session,
):
    """C: exhaustion is IntegrityError (not RuntimeError), writes no row, and the live
    frame keeps the seq it was stamped with."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.append_event("run-1", 1, "a", "t", {"seq": 1})
    frame = {"seq": 1}
    with pytest.raises(IntegrityError):
        await store.append_event_at_or_after(
            "run-1", 1, "b", "t", frame, _max_attempts=1
        )
    db_session.rollback()
    assert _stored(db_session, "b") is None
    assert frame == {"seq": 1}


@pytest.mark.issue("ISS-907")
async def test_sink_degrades_on_exhaustion_and_the_live_frame_keeps_its_seq(db_session):
    """C': the production consequence. persist() returns None on exhaustion, and the drive
    loops (engine.py:4208, :15951) re-stamp only on a non-None return, so a store that
    moved the frame's seq here would leave a live frame no row carries.

    A tail probe that LAGS the real tail by design (reports 1, 2, 3, ...) while rows 1-10
    exist makes every hop land on an occupied seq with the guard satisfied, so all 8
    attempts are spent and the exhaustion branch (authz.py:674) is the one that fires."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    for n in range(1, 11):
        await store.append_event("run-1", n, f"e{n}", "t", {"seq": n})
    probes = []

    async def _lagging_probe(run_id):
        probes.append(run_id)
        return len(probes)

    store._max_event_seq = _lagging_probe
    sink = _RunEventSink()
    sink.arm(store, "run-1")
    frame = {"seq": 1}
    assert await sink.persist(1, "z", "t", frame) is None
    assert (
        len(probes) == 8
    ), "all 8 attempts must have been spent (exhaustion, not the guard)"
    db_session.rollback()
    assert _stored(db_session, "z") is None
    assert frame == {"seq": 1}


@pytest.mark.issue("ISS-907")
async def test_payload_without_a_seq_key_is_stored_untouched_on_a_retry(db_session):
    """D: FIX-692 constraint 3 -- run_resuming / pipeline_cancelled markers carry no seq."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.append_event("run-1", 1, "a", "t", {"seq": 1})
    marker = {"pipeline_run_id": "run-1", "reason": "user"}
    landed = await store.append_event_at_or_after(
        "run-1", 1, "c", "pipeline_cancelled", marker
    )
    assert landed == 2
    assert _stored(db_session, "c") == (
        2,
        {"pipeline_run_id": "run-1", "reason": "user"},
    )
    assert marker == {"pipeline_run_id": "run-1", "reason": "user"}


@pytest.mark.issue("ISS-907")
async def test_a_rejection_no_tail_explains_is_not_retried(db_session):
    """E: the `tail < attempt_seq` guard -- a duplicate event_id at a FREE seq is re-raised
    after ONE attempt and ONE probe, not spun 8 times."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.append_event("run-1", 1, "a", "t", {"seq": 1})
    attempts = []
    real_append = store.append_event

    async def _counting_append(*args, **kwargs):
        attempts.append(args[1])
        return await real_append(*args, **kwargs)

    store.append_event = _counting_append
    probes = _stale_first_probe(store, stale_tail=None)  # count only
    frame = {"seq": 5}
    with pytest.raises(IntegrityError):
        await store.append_event_at_or_after("run-1", 5, "a", "t", frame)
    db_session.rollback()
    assert attempts == [5], f"retried a rejection the tail does not explain: {attempts}"
    assert len(probes) == 1
    assert frame == {"seq": 5}

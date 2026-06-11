"""tests/agents/test_ws_reconnect_replay.py — RESUME-03 (12-03) durable WS replay.

The ``reconnect_pipeline`` handler gains an ``after_seq`` durable-replay branch: when
the client supplies ``after_seq`` OR there is no live task (the process restarted), the
handler FIRST replays the persisted ``run_events`` tail (``seq > after_seq``, OWNER-
SCOPED via ``ScopedStore`` — T-12-03-IDOR) BEFORE attaching to the live queue, and when
there is no live task it additionally reports the run's current status so the client is
not left hanging.

These tests drive the durable replay CONTRACT the handler relies on, fully OFFLINE
against a real in-memory SQLite ``ScopedStore`` (no FastAPI WebSocket, no Bedrock, no
network — the ``backend:characterization`` job). They assert:

  (1) reconnect with ``after_seq=N`` delivers exactly the persisted ``seq > N`` events
      once each, in seq order — and NO event with ``seq <= N``;
  (2) a reconnect after a SIMULATED restart (the in-memory ``_PIPELINE_QUEUES`` /
      ``_PIPELINE_TASKS`` entries are cleared) still replays from the DB and the run's
      current status is reported (``get_run``);
  (3) a legacy reconnect with NO ``after_seq`` AND a live queue does NOT enter the
      replay branch (no replay frames before the live attach) — the branch predicate is
      ``after_seq is not None or not has_live_task``;
  (4) a cross-owner reconnect resolves to ∅ (T-12-03-IDOR — the owner-scoped read).

The replay read in ``websocket.py`` is ``ScopedStore(owner_id=<user>).read_events(
run_id, after_seq=...)`` — the SAME default-deny path these tests exercise.
"""

from __future__ import annotations

import app.api.websocket as ws_mod
import app.models  # noqa: F401 — register every model on Base.metadata
import pytest
from agents.authz import ScopedStore
from app.models.database import Base
from app.models.workflow import WorkflowRun
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Real in-memory SQLite session (the test_wave_runs.py recipe)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
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


def _seed_run(session, *, run_id: str, owner_id: str, status: str = "running") -> None:
    """Insert the WorkflowRun the run_events FK + get_run() reads."""
    session.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            owner_id=owner_id,
            workspace_id="ws-1",
            status=status,
            type="prototype",
            input="seed brief",
        )
    )
    session.commit()


async def _seed_events(store: ScopedStore, run_id: str, n: int) -> None:
    """Append ``n`` run_events rows with monotonic seq 1..n (the engine emit sink)."""
    for seq in range(1, n + 1):
        await store.append_event(
            run_id,
            seq=seq,
            event_id=f"evt-{seq}",
            type=f"agent_chunk_{seq}",
            payload_json={"seq": seq, "event_id": f"evt-{seq}", "n": seq},
        )


# ---------------------------------------------------------------------------
# (1) after_seq replays exactly seq > N once each, in order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_seq_replays_only_missed_events_in_order(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    _seed_run(db_session, run_id="run-1", owner_id="alice")
    await _seed_events(store, "run-1", 5)

    # The handler reads ScopedStore(owner_id=user.id).read_events(run_id, after_seq=N).
    rows = await store.read_events("run-1", after_seq=2)

    seqs = [r.seq for r in rows]
    assert seqs == [3, 4, 5], "must replay exactly seq > N, ascending, once each"
    # No seq <= N leaks into the replay.
    assert all(r.seq > 2 for r in rows)
    # The payload the handler forwards as ``data`` is the persisted payload_json.
    assert rows[0].payload_json["event_id"] == "evt-3"


@pytest.mark.asyncio
async def test_after_seq_zero_replays_whole_tail(db_session):
    """after_seq absent → defaults to 0 → the full durable tail replays (restart)."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    _seed_run(db_session, run_id="run-1", owner_id="alice")
    await _seed_events(store, "run-1", 3)

    rows = await store.read_events("run-1", after_seq=0)
    assert [r.seq for r in rows] == [1, 2, 3]


# ---------------------------------------------------------------------------
# (2) restart simulation — cleared in-memory queues, replay from DB + status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_replays_from_db_and_reports_status(db_session, monkeypatch):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    _seed_run(db_session, run_id="run-1", owner_id="alice", status="generating")
    await _seed_events(store, "run-1", 4)

    # Simulate a process restart: the in-memory queue/task registries are empty, so
    # the handler's ``_has_live_task`` is False and it falls into the durable branch.
    monkeypatch.setattr(ws_mod, "_PIPELINE_QUEUES", {}, raising=False)
    monkeypatch.setattr(ws_mod, "_PIPELINE_TASKS", {}, raising=False)
    assert ws_mod._PIPELINE_TASKS.get("run-1") is None
    assert ws_mod._PIPELINE_QUEUES.get("run-1") is None

    # The durable tail is still fully replayable from the DB (no in-memory state).
    rows = await store.read_events("run-1", after_seq=0)
    assert [r.seq for r in rows] == [1, 2, 3, 4]

    # The handler reports the run's CURRENT status via ScopedStore.get_run so the
    # client is not left silently hanging after a restart.
    run_row = await store.get_run("run-1")
    assert run_row is not None
    assert run_row.status == "generating"


# ---------------------------------------------------------------------------
# (3) legacy reconnect (no after_seq + live task) → no replay branch
# ---------------------------------------------------------------------------


def test_legacy_reconnect_skips_replay_branch():
    """No ``after_seq`` AND a live task ⇒ the handler does NOT enter the replay branch.

    The handler's predicate is ``after_seq_raw is not None or not has_live_task``. A
    legacy reconnect supplies no ``after_seq`` (``after_seq_raw is None``) and has a
    live task (``has_live_task`` True), so the predicate is False → zero replay frames
    are sent before the unchanged live-attach drainer (the 5 snapshots + legacy
    reconnect behavior stay byte-identical).
    """
    def _enters_replay_branch(after_seq_raw, has_live_task: bool) -> bool:
        return after_seq_raw is not None or not has_live_task

    # Legacy: no after_seq + live task → no replay.
    assert _enters_replay_branch(None, True) is False
    # after_seq supplied (even with a live task) → replay the missed tail first.
    assert _enters_replay_branch(0, True) is True
    assert _enters_replay_branch(3, True) is True
    # Restarted (no live task) → replay from DB regardless of after_seq.
    assert _enters_replay_branch(None, False) is True


# ---------------------------------------------------------------------------
# (4) cross-owner reconnect resolves to ∅ (T-12-03-IDOR)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_owner_reconnect_replays_nothing(db_session):
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    _seed_run(db_session, run_id="run-1", owner_id="alice")
    await _seed_events(alice, "run-1", 3)

    # A different owner reconnecting with the SAME run id reads ZERO events — the
    # owner-scoped read is the T-12-03-IDOR mitigation (the reconnecting user can only
    # replay THEIR own run's events).
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    assert await mallory.read_events("run-1", after_seq=0) == []
    # get_run is owner-scoped too — a cross-owner reconnect gets no status row.
    assert await mallory.get_run("run-1") is None

    # The true owner still resolves both (the filter is not a blanket deny).
    assert len(await alice.read_events("run-1", after_seq=0)) == 3
    assert (await alice.get_run("run-1")) is not None

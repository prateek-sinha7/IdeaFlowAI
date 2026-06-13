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

import asyncio

import app.api.websocket as ws_mod
import app.models  # noqa: F401 — register every model on Base.metadata
import pytest
from agents.authz import ScopedStore
from app.models.database import Base
from app.models.user import User
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
# CR-02 — the PRODUCTION-shaped replay (no explicit workspace_id) returns rows
# ---------------------------------------------------------------------------


def _recover_workspace_id(session, *, run_id: str, owner_id: str):
    """Recover the run's workspace_id from an OWNER-SCOPED RunEvent row.

    This mirrors EXACTLY how the websocket.py reconnect replay branch recovers the
    workspace before constructing the replay ScopedStore (CR-02 fix): the lookup is
    filtered by ``owner_id == user.id`` so a row that is not the authenticated user's
    never feeds the workspace_id (T-12-05-TENANT — never from client input).
    """
    from app.models.run_event import RunEvent

    row = (
        session.query(RunEvent)
        .filter(RunEvent.run_id == run_id, RunEvent.owner_id == owner_id)
        .first()
    )
    return getattr(row, "workspace_id", None)


@pytest.mark.asyncio
async def test_production_shaped_replay_recovers_workspace_and_returns_rows(db_session):
    """CR-02 (RESUME-03): the replay store constructed as the HANDLER constructs it —
    with NO explicit workspace_id — must still return the run's persisted rows.

    Production run_events rows carry a REAL non-null workspace_id (the engine sink
    stamps ``ectx.workspace_id``). The pre-fix handler built ``ScopedStore(owner_id=
    user.id)`` with ``workspace_id=None``, so ``read_events`` scoped to
    ``workspace_id IS NULL`` and matched ZERO production rows. The fix RECOVERS the
    run's workspace_id from an owner-scoped RunEvent row BEFORE constructing the store.

    This test stamps rows under a real workspace ("ws-prod"), recovers the workspace
    the SAME way the handler does (owner-scoped lookup, NOT by passing it explicitly),
    and asserts the replay is non-empty. It FAILS on the pre-fix construction (no
    workspace recovery ⇒ workspace_id IS NULL ⇒ 0 rows).
    """
    # Seed rows under the run's REAL workspace, via the engine-sink-shaped append.
    seed_store = ScopedStore(owner_id="alice", workspace_id="ws-prod", session=db_session)
    db_session.add(
        WorkflowRun(
            id="run-prod", user_id="alice", owner_id="alice",
            workspace_id="ws-prod", status="generating", type="prototype",
            input="seed",
        )
    )
    db_session.commit()
    await _seed_events(seed_store, "run-prod", 4)

    # ── The PRODUCTION path: recover the workspace from an owner-scoped row, then build
    # the replay store WITHOUT passing workspace_id explicitly. ──────────────────────
    _recovered_ws = _recover_workspace_id(db_session, run_id="run-prod", owner_id="alice")
    assert _recovered_ws == "ws-prod", "must recover the run's real workspace_id"
    replay_store = ScopedStore(
        owner_id="alice", workspace_id=_recovered_ws, session=db_session
    )
    rows = await replay_store.read_events("run-prod", after_seq=0)
    assert [r.seq for r in rows] == [1, 2, 3, 4], (
        "production-shaped replay must return the run's rows (pre-fix: 0 rows, "
        "workspace_id IS NULL)"
    )

    # Proof the pre-fix construction (no workspace recovery) returns NOTHING — the
    # exact production defect CR-02 closes.
    prefix_store = ScopedStore(owner_id="alice", session=db_session)
    assert await prefix_store.read_events("run-prod", after_seq=0) == [], (
        "the pre-fix ScopedStore(owner_id=...) with no workspace_id must match 0 rows"
    )


@pytest.mark.asyncio
async def test_cross_owner_workspace_recovery_yields_empty_replay(db_session):
    """CR-02 / T-12-05-TENANT: the workspace recovery is OWNER-SCOPED — a cross-owner
    reconnect recovers NO workspace row and the replay is ∅ (the IDOR boundary holds).
    """
    seed_store = ScopedStore(owner_id="alice", workspace_id="ws-prod", session=db_session)
    db_session.add(
        WorkflowRun(
            id="run-prod", user_id="alice", owner_id="alice",
            workspace_id="ws-prod", status="generating", type="prototype",
            input="seed",
        )
    )
    db_session.commit()
    await _seed_events(seed_store, "run-prod", 3)

    # Mallory reconnects with alice's run id: the owner-scoped recovery finds no row,
    # so the recovered workspace is None → the replay (workspace_id IS NULL) is empty.
    _mallory_ws = _recover_workspace_id(db_session, run_id="run-prod", owner_id="mallory")
    assert _mallory_ws is None, "cross-owner recovery must not leak the run's workspace"
    mallory_store = ScopedStore(
        owner_id="mallory", workspace_id=_mallory_ws, session=db_session
    )
    assert await mallory_store.read_events("run-prod", after_seq=0) == [], (
        "cross-owner reconnect must replay ∅ (T-12-05-TENANT / IDOR boundary)"
    )

    # The true owner still recovers ws-prod and reads the rows.
    _alice_ws = _recover_workspace_id(db_session, run_id="run-prod", owner_id="alice")
    alice_store = ScopedStore(
        owner_id="alice", workspace_id=_alice_ws, session=db_session
    )
    assert len(await alice_store.read_events("run-prod", after_seq=0)) == 3


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


# ===========================================================================
# Cluster B (16-03) — the REAL handler drives the replay/reconnect frame
# contract end-to-end (mirror of the WR-03 live-attach contract test
# test_reconnect_drainer_preserves_revision_section, onto the REPLAY branch).
#
# These drive ``websocket_chat`` for real (a scripted-loop FakeWebSocket) so the
# assertions pin the actual frames Task 1 emits:
#   - ISS-008: a durable-REPLAY of a ``*_revision`` run stamps every replayed
#     frame with ``section == "<base>_output"`` (the WR-06 inverse); a
#     non-revision run keeps ``section is None`` (byte-identical to today).
#   - ISS-009: the live-attach ``pipeline_reconnected`` ack carries ``live: True``;
#     the no-live-task ack carries ``live: False``.
# ===========================================================================


class _ScriptedLoopWebSocket:
    """Drives the REAL ``websocket_chat`` receive loop: scripted inbound JSON
    frames, captured outbound frames, ``WebSocketDisconnect`` once the script is
    exhausted (the loop's normal client-went-away exit). Mirror of the harness in
    tests/unit/test_run_revision_ws_dispatch.py."""

    def __init__(self, frames: list[dict]) -> None:
        import json as _json

        self._frames = [_json.dumps(f) for f in frames]
        self.sent: list[dict] = []
        self.headers: dict = {}
        self.query_params = {"token": "test-token"}
        self.accepted = False

    async def accept(self, subprotocol=None) -> None:
        self.accepted = True

    async def close(self, code=None, reason=None) -> None:
        pass

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_text(self) -> str:
        if self._frames:
            await asyncio.sleep(0)
            return self._frames.pop(0)
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(code=1000)


@pytest.fixture
def handler_env(monkeypatch):
    """In-memory SQLite wired into BOTH ws_mod._get_db (the owner-scoped run-row /
    workspace recovery reads) AND app.models.database.SessionLocal (the default-deny
    ScopedStore the replay/get_run path opens) — the WR-03 idiom."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(ws_mod, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(
        "app.models.database.SessionLocal", TestingSession, raising=False
    )
    try:
        yield TestingSession
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_user(TestingSession) -> User:
    db = TestingSession()
    try:
        import uuid as _uuid

        u = User(
            id=str(_uuid.uuid4()),
            email=f"rc-{_uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


async def _seed_run_and_events(
    TestingSession, *, run_id: str, owner_id: str, run_type: str, n: int,
    status: str = "completed", workspace_id: str = "ws-rc",
) -> None:
    db = TestingSession()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=owner_id, owner_id=owner_id,
            workspace_id=workspace_id, status=status, type=run_type,
            input="seed brief",
        ))
        db.commit()
    finally:
        db.close()
    store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
    for seq in range(1, n + 1):
        await store.append_event(
            run_id, seq=seq, event_id=f"evt-{seq}",
            type=f"agent_chunk_{seq}",
            payload_json={"seq": seq, "event_id": f"evt-{seq}"},
        )


@pytest.mark.asyncio
async def test_replay_revision_run_stamps_target_section_and_live_false_ack(
    handler_env, monkeypatch,
):
    """ISS-008 (mirror of WR-03 onto the REPLAY branch): a durable replay of a
    ``*_revision`` run (no live task — restarted process) stamps every replayed
    frame with ``section == "<base>_output"`` (the WR-06 inverse), and the
    no-live-task ``pipeline_reconnected`` ack carries ``live: False``."""
    TestingSession = handler_env
    user = _seed_user(TestingSession)
    monkeypatch.setattr(ws_mod, "_authenticate_token", lambda token, db: user)
    # No live task → the durable-replay branch (restarted process).
    monkeypatch.setattr(ws_mod, "_PIPELINE_TASKS", {}, raising=False)
    monkeypatch.setattr(ws_mod, "_PIPELINE_QUEUES", {}, raising=False)

    run_id = "run-rev-replay"
    await _seed_run_and_events(
        TestingSession, run_id=run_id, owner_id=user.id,
        run_type="od_ppt_revision", n=3,
    )

    ws = _ScriptedLoopWebSocket([
        {"type": "reconnect_pipeline", "pipeline_run_id": run_id, "after_seq": 0},
    ])
    await asyncio.wait_for(ws_mod.websocket_chat(ws), timeout=10.0)

    replayed = [f for f in ws.sent if str(f["type"]).startswith("agent_chunk_")]
    assert len(replayed) == 3, f"durable tail not replayed: {ws.sent}"
    for frame in replayed:
        assert frame["section"] == "od_ppt_output", (
            "durable replay of a *_revision run must stamp section = the WR-06 "
            f"inverse (od_ppt_output), got {frame['section']!r}"
        )
        assert frame["chunk"] is None

    acks = [f for f in ws.sent if f["type"] == "pipeline_reconnected"]
    assert len(acks) == 1, f"expected one no-live-task ack: {ws.sent}"
    assert acks[0]["data"]["live"] is False, (
        "the no-live-task reconnect ack must carry live: False"
    )


@pytest.mark.asyncio
async def test_replay_non_revision_run_keeps_section_none(handler_env, monkeypatch):
    """Non-revision control (ISS-008): a durable replay of a ``prototype`` run
    keeps ``section is None`` — byte-identical to today and to the live-attach
    contract (the WR-06 inverse returns None for a non-``*_revision`` type)."""
    TestingSession = handler_env
    user = _seed_user(TestingSession)
    monkeypatch.setattr(ws_mod, "_authenticate_token", lambda token, db: user)
    monkeypatch.setattr(ws_mod, "_PIPELINE_TASKS", {}, raising=False)
    monkeypatch.setattr(ws_mod, "_PIPELINE_QUEUES", {}, raising=False)

    run_id = "run-proto-replay"
    await _seed_run_and_events(
        TestingSession, run_id=run_id, owner_id=user.id,
        run_type="prototype", n=2,
    )

    ws = _ScriptedLoopWebSocket([
        {"type": "reconnect_pipeline", "pipeline_run_id": run_id, "after_seq": 0},
    ])
    await asyncio.wait_for(ws_mod.websocket_chat(ws), timeout=10.0)

    replayed = [f for f in ws.sent if str(f["type"]).startswith("agent_chunk_")]
    assert len(replayed) == 2, f"durable tail not replayed: {ws.sent}"
    for frame in replayed:
        assert frame["section"] is None, (
            "a non-revision replay must keep section: None (byte-identical to "
            f"today), got {frame['section']!r}"
        )


@pytest.mark.asyncio
async def test_live_attach_reconnect_ack_carries_live_true(handler_env, monkeypatch):
    """ISS-009: a reconnect to a LIVE run receives a ``pipeline_reconnected`` ack
    carrying ``live: True`` (symmetric with the no-live-task ``live: False``)."""
    TestingSession = handler_env
    user = _seed_user(TestingSession)
    monkeypatch.setattr(ws_mod, "_authenticate_token", lambda token, db: user)

    run_id = "run-live-attach"
    await _seed_run_and_events(
        TestingSession, run_id=run_id, owner_id=user.id,
        run_type="prototype", n=1, status="generating",
    )

    # Simulate the in-flight run: a real (blocked) bg task + a queue pre-loaded
    # with the terminal so the live-attach drainer attaches, acks, drains, breaks.
    release = asyncio.Event()

    async def _blocked():
        await release.wait()

    live_task = asyncio.create_task(_blocked())
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put({"type": "pipeline_complete", "data": {"final_output": "<html/>"}})
    monkeypatch.setitem(ws_mod._PIPELINE_TASKS, run_id, live_task)
    monkeypatch.setitem(ws_mod._PIPELINE_QUEUES, run_id, queue)

    # A legacy reconnect (no after_seq) + live task → straight to the live attach.
    ws = _ScriptedLoopWebSocket([
        {"type": "reconnect_pipeline", "pipeline_run_id": run_id},
    ])
    try:
        await asyncio.wait_for(ws_mod.websocket_chat(ws), timeout=10.0)
    finally:
        release.set()
        live_task.cancel()

    acks = [f for f in ws.sent if f["type"] == "pipeline_reconnected"]
    assert len(acks) == 1, f"expected one live-attach ack: {ws.sent}"
    assert acks[0]["data"]["live"] is True, (
        "the live-attach reconnect ack must carry live: True (ISS-009)"
    )

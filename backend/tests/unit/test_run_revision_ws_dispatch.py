"""14-02 — ``run_revision`` queue-dispatch regression (handler level).

Phase 14 moved the WS ``run_revision`` branch off the inline
``await _rev_engine._handle_revision(...)`` onto the proven background-task +
per-run-queue + drainer pattern (``_handle_revision_execution``, mirroring
``_handle_workflow_execution``). This suite drives the extracted coroutine
DIRECTLY (the ``asyncio.create_task`` indirection is the receive loop's
concern) and pins the contract:

  (a) happy path — every drained frame is {type, chunk: None,
      section: <target_artifact_type>, data}; exactly one pipeline_complete;
      the revision WorkflowRun ends "completed" with completed_at set;
      _PIPELINE_QUEUES/_PIPELINE_TASKS are cleaned after completion;
  (b) failure path — a run that ends in pipeline_failed (and never
      pipeline_complete) is recorded "failed", NEVER "completed"
      (RESEARCH Pitfall 4: the FE revision-of-revision lookup matches
      status === "completed", so a lying status offers a failed revision
      as a future revision parent);
  (c) ValueError from the engine → an error frame with code
      "revision_validation_error" (recoverable False), row "failed";
  (d) runtime error → code "revision_error" (recoverable True), row "failed";
  (e) agent_count derives from get_pipeline_agents over the derived revision
      alias (ppt_revision vs od_ppt_revision) — computed against the LIVE
      registry, never a hardcoded 1 (RESEARCH Pitfall 6);
  (f) cancellation — cancelling the outer handler propagates to the
      background engine task; the row ends "cancelled" (never left
      "revising") and a pipeline_cancelled frame is queued or sent.

Assertion hygiene: no wall-clock timing assertions — determinism is driven by
events (the cancellation stub sets an asyncio.Event when entered, so the test
cancels only after dispatch started).

Offline — in-memory SQLite (StaticPool) monkeypatched onto the WS module's
``_get_db``; stub engine via ``agents.execution_engine.engine
.get_execution_engine``; no Bedrock, no network.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the handler path touches on Base.metadata BEFORE
# create_all (db_factory pattern, see test_run_revision_fe_contract.py).
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
from agents.registry import get_pipeline_agents
from app.models.database import Base
from app.models.user import User
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# Harness — fake WS, stub engine, in-memory DB
# ════════════════════════════════════════════════════════════════════════════


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class _StubEngine:
    """Stub engine whose ``_handle_revision`` is parameterized per scenario.

    Records every call's kwargs (including the minted ``pipeline_run_id`` and
    the ``websocket_send_fn`` queue closure) so tests can locate the revision
    row and the per-run queue without guessing identifiers.
    """

    def __init__(self, behavior) -> None:
        self._behavior = behavior
        self.calls: list[dict] = []

    async def _handle_revision(self, **kwargs) -> None:
        self.calls.append(kwargs)
        await self._behavior(kwargs)


@pytest.fixture
def ws_env(monkeypatch):
    """Offline harness for ``_handle_revision_execution``: in-memory SQLite
    wired into the WS module's ``_get_db`` (mirrors
    tests/unit/test_pipeline_failure_semantics.py)."""
    from app.api import websocket as ws_module

    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    yield ws_module, TestingSession

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


@pytest.fixture
def ws_user(ws_env):
    """A persisted user principal (id + preferred_model None)."""
    ws_module, TestingSession = ws_env
    db = TestingSession()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"rev-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _seed_parent(TestingSession, user_id: str) -> str:
    """Seed a completed parent WorkflowRun so the parent_run_id FK guard in
    ``_handle_revision_execution`` links the revision row to it."""
    parent_id = str(uuid.uuid4())
    db = TestingSession()
    try:
        db.add(WorkflowRun(
            id=parent_id,
            user_id=user_id,
            owner_id=user_id,
            title="parent deck",
            type="od_ppt",
            status="completed",
            input="make a deck",
            agent_count=3,
        ))
        db.commit()
    finally:
        db.close()
    return parent_id


def _row(TestingSession, run_id: str) -> WorkflowRun | None:
    db = TestingSession()
    try:
        return db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    finally:
        db.close()


def _install_stub(monkeypatch, behavior) -> _StubEngine:
    stub = _StubEngine(behavior)
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: stub)
    return stub


# ────────────────────────────────────────────────────────────────────────────
# (a) Happy path — section stamping, completed status, cleanup
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_frames_status_and_cleanup(ws_env, ws_user, monkeypatch):
    ws_module, TestingSession = ws_env
    parent_id = _seed_parent(TestingSession, ws_user.id)

    async def _happy(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_start", "data": {"agents": []}})
        await send({"type": "pipeline_complete",
                    "data": {"final_output": "<html>revised deck</html>",
                             "pipeline_type": "od_ppt_revision"}})

    stub = _install_stub(monkeypatch, _happy)
    ws = _FakeWebSocket()

    await ws_module._handle_revision_execution(
        ws, ws_user, parent_id, "od_ppt_output", "Make the closing slide a CTA.",
    )

    # FE frame contract: every drained frame is {type, chunk: None,
    # section: <target_artifact_type>, data} — section is the TARGET artifact
    # type, never the pipeline type.
    assert ws.sent, "no frames were drained to the WS"
    for frame in ws.sent:
        assert set(frame.keys()) == {"type", "chunk", "section", "data"}
        assert frame["chunk"] is None
        assert frame["section"] == "od_ppt_output"

    completes = [f for f in ws.sent if f["type"] == "pipeline_complete"]
    assert len(completes) == 1, f"expected exactly one pipeline_complete: {ws.sent}"

    # Terminal status fidelity: the row ends "completed" with completed_at set.
    run_id = stub.calls[0]["pipeline_run_id"]
    row = _row(TestingSession, run_id)
    assert row is not None
    assert row.status == "completed"
    assert row.completed_at is not None
    assert row.parent_run_id == parent_id

    # Cleanup ran: the run id is gone from both per-run registries.
    assert run_id not in ws_module._PIPELINE_QUEUES
    assert run_id not in ws_module._PIPELINE_TASKS


# ────────────────────────────────────────────────────────────────────────────
# (b) pipeline_failed terminal → "failed", never "completed" (Pitfall 4)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_failed_records_failed_not_completed(ws_env, ws_user, monkeypatch):
    ws_module, TestingSession = ws_env
    parent_id = _seed_parent(TestingSession, ws_user.id)

    async def _fails(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_start", "data": {"agents": []}})
        await send({"type": "pipeline_failed",
                    "data": {"error": "no agent completed"}})
        # NO pipeline_complete — total collapse (13-06 semantics).

    stub = _install_stub(monkeypatch, _fails)
    ws = _FakeWebSocket()

    await ws_module._handle_revision_execution(
        ws, ws_user, parent_id, "od_ppt_output", "Fix slide two.",
    )

    run_id = stub.calls[0]["pipeline_run_id"]
    row = _row(TestingSession, run_id)
    assert row is not None
    assert row.status == "failed", (
        "a pipeline_failed dispatch must NEVER be recorded as a clean success "
        f"(got {row.status!r}) — the FE revision-parent lookup keys on completed"
    )
    assert row.status != "completed"
    assert [f["type"] for f in ws.sent].count("pipeline_failed") == 1


# ────────────────────────────────────────────────────────────────────────────
# (c) ValueError → revision_validation_error frame, row "failed"
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_value_error_maps_to_revision_validation_error(ws_env, ws_user, monkeypatch):
    ws_module, TestingSession = ws_env
    parent_id = _seed_parent(TestingSession, ws_user.id)

    async def _raises_value_error(kwargs):
        raise ValueError("boom")

    stub = _install_stub(monkeypatch, _raises_value_error)
    ws = _FakeWebSocket()

    await ws_module._handle_revision_execution(
        ws, ws_user, parent_id, "od_ppt_output", "Fix it.",
    )

    errors = [f for f in ws.sent if f["type"] == "error"]
    assert len(errors) == 1, f"expected one error frame: {ws.sent}"
    data = errors[0]["data"]
    assert data["code"] == "revision_validation_error"
    assert data["recoverable"] is False
    assert data["error"] == "boom"
    # Error frames ride the same drainer wrapper (section = target type).
    assert errors[0]["section"] == "od_ppt_output"

    row = _row(TestingSession, stub.calls[0]["pipeline_run_id"])
    assert row is not None and row.status == "failed"


# ────────────────────────────────────────────────────────────────────────────
# (d) Runtime error → revision_error frame, row "failed"
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_error_maps_to_revision_error(ws_env, ws_user, monkeypatch):
    ws_module, TestingSession = ws_env
    parent_id = _seed_parent(TestingSession, ws_user.id)

    async def _raises_runtime_error(kwargs):
        raise RuntimeError("engine exploded")

    stub = _install_stub(monkeypatch, _raises_runtime_error)
    ws = _FakeWebSocket()

    await ws_module._handle_revision_execution(
        ws, ws_user, parent_id, "od_ppt_output", "Fix it.",
    )

    errors = [f for f in ws.sent if f["type"] == "error"]
    assert len(errors) == 1, f"expected one error frame: {ws.sent}"
    data = errors[0]["data"]
    assert data["code"] == "revision_error"
    assert data["recoverable"] is True
    assert "engine exploded" in data["error"]

    row = _row(TestingSession, stub.calls[0]["pipeline_run_id"])
    assert row is not None and row.status == "failed"


# ────────────────────────────────────────────────────────────────────────────
# (e) agent_count derives from the live registry (Pitfall 6)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_count_derives_from_registry_membership(ws_env, ws_user, monkeypatch):
    ws_module, TestingSession = ws_env

    async def _happy(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_complete", "data": {"final_output": "x"}})

    stub = _install_stub(monkeypatch, _happy)

    # The expectations are computed from the LIVE registry at test time, so
    # they can never drift from a hardcoded numeral. Sanity: the ppt_revision
    # pipeline has MORE than one member — the value that distinguishes the
    # derivation from the old hardcoded agent_count=1.
    expected_ppt = len(get_pipeline_agents("ppt_revision"))
    expected_od_ppt = len(get_pipeline_agents("od_ppt_revision"))
    assert expected_ppt > 1, "ppt_revision lost its multi-agent membership?"
    assert expected_od_ppt >= 1

    parent_a = _seed_parent(TestingSession, ws_user.id)
    await ws_module._handle_revision_execution(
        _FakeWebSocket(), ws_user, parent_a, "ppt_output", "Revise the deck.",
    )
    row_ppt = _row(TestingSession, stub.calls[0]["pipeline_run_id"])
    assert row_ppt is not None
    assert row_ppt.agent_count == expected_ppt
    assert row_ppt.type == "ppt_revision"

    parent_b = _seed_parent(TestingSession, ws_user.id)
    await ws_module._handle_revision_execution(
        _FakeWebSocket(), ws_user, parent_b, "od_ppt_output", "Revise the deck.",
    )
    row_od = _row(TestingSession, stub.calls[1]["pipeline_run_id"])
    assert row_od is not None
    assert row_od.agent_count == expected_od_ppt
    assert row_od.type == "od_ppt_revision"


# ────────────────────────────────────────────────────────────────────────────
# (f) Cancellation — propagates to the bg task; row "cancelled" (Pitfall 3/4)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancellation_lands_row_cancelled(ws_env, ws_user, monkeypatch):
    ws_module, TestingSession = ws_env
    parent_id = _seed_parent(TestingSession, ws_user.id)

    entered = asyncio.Event()

    async def _long_running(kwargs):
        entered.set()  # dispatch started — the test may now cancel
        await asyncio.sleep(60)  # stands in for a multi-minute model run

    stub = _install_stub(monkeypatch, _long_running)
    ws = _FakeWebSocket()

    outer = asyncio.create_task(ws_module._handle_revision_execution(
        ws, ws_user, parent_id, "od_ppt_output", "Take your time.",
    ))
    # Event-driven determinism: cancel only after the engine dispatch started
    # (the row exists and the bg task is awaiting the engine).
    await asyncio.wait_for(entered.wait(), timeout=5.0)

    run_id = stub.calls[0]["pipeline_run_id"]
    # Hold direct references BEFORE cancelling — _cleanup_pipeline pops the
    # registries, but the held queue still carries the terminal events.
    held_queue = ws_module._PIPELINE_QUEUES[run_id]
    bg_task = ws_module._PIPELINE_TASKS[run_id]

    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer

    # The bg task absorbs the cancellation (run_pipeline precedent), persists
    # the terminal state, and finishes.
    try:
        await asyncio.wait_for(bg_task, timeout=5.0)
    except asyncio.CancelledError:
        pass

    row = _row(TestingSession, run_id)
    assert row is not None
    assert row.status == "cancelled", (
        f"cancelled revision must never be left 'revising' or recorded "
        f"'completed' (got {row.status!r})"
    )
    assert row.status not in ("revising", "completed")

    # A pipeline_cancelled frame was queued (drainer died with the outer task)
    # or sent before the drainer exited.
    queued_types: list[str] = []
    while not held_queue.empty():
        item = held_queue.get_nowait()
        if item is not None:
            queued_types.append(item.get("type"))
    sent_types = [f["type"] for f in ws.sent]
    assert "pipeline_cancelled" in (queued_types + sent_types), (
        f"no pipeline_cancelled observed — queued={queued_types} sent={sent_types}"
    )

    # Cleanup ran despite cancellation.
    assert run_id not in ws_module._PIPELINE_QUEUES
    assert run_id not in ws_module._PIPELINE_TASKS


# ────────────────────────────────────────────────────────────────────────────
# WR-02 (14 review) — degraded completion persists "degraded", not "completed"
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_degraded_completion_records_degraded_not_completed(
    ws_env, ws_user, monkeypatch
):
    """WR-02 (14 review): ``pipeline_complete`` carrying ``data.status ==
    "degraded"`` + ``agents_failed`` (an agent errored unrecovered) persists
    "degraded" — mirroring the run_pipeline mapping (13 IN-03) — never
    "completed" (the FE revision-parent lookup keys on completed, so a lying
    status would offer a partial deliverable as a future revision parent)."""
    ws_module, TestingSession = ws_env
    parent_id = _seed_parent(TestingSession, ws_user.id)

    async def _degraded(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_complete",
                    "data": {"final_output": "<html>partial deck</html>",
                             "status": "degraded",
                             "agents_failed": ["ppt-revision-assembler"]}})

    stub = _install_stub(monkeypatch, _degraded)
    ws = _FakeWebSocket()

    await ws_module._handle_revision_execution(
        ws, ws_user, parent_id, "ppt_output", "Fix the deck.",
    )

    row = _row(TestingSession, stub.calls[0]["pipeline_run_id"])
    assert row is not None
    assert row.status == "degraded", (
        f"a degraded completion must persist 'degraded' (got {row.status!r}) — "
        "never 'completed' (FE revision-parent lookup) nor 'failed' "
        "(a deliverable DID complete)"
    )
    assert row.status != "completed"
    assert row.completed_at is not None


# ────────────────────────────────────────────────────────────────────────────
# WR-01 (14 review) — post-terminal state_restoration_failed is delivered
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_state_restoration_failed_after_terminal_is_delivered(
    ws_env, ws_user, monkeypatch
):
    """WR-01 (14 review): the engine emits ``state_restoration_failed`` AFTER
    the terminal ``pipeline_complete`` (the post-dispatch exact-kind lineage
    write runs post-emit since 14-03). The drainer breaks on the terminal —
    the residual drain must still forward the post-terminal event on the same
    wrapper instead of silently discarding it with the queue."""
    ws_module, TestingSession = ws_env
    parent_id = _seed_parent(TestingSession, ws_user.id)

    async def _complete_then_lineage_failure(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_complete",
                    "data": {"final_output": "<html>revised deck</html>"}})
        # The lineage write failed AFTER the terminal emit (engine.py order).
        await send({"type": "state_restoration_failed",
                    "data": {"error": "artifact_refs write refused"}})

    stub = _install_stub(monkeypatch, _complete_then_lineage_failure)
    ws = _FakeWebSocket()

    await ws_module._handle_revision_execution(
        ws, ws_user, parent_id, "od_ppt_output", "Fix slide 1.",
    )

    types = [f["type"] for f in ws.sent]
    assert "state_restoration_failed" in types, (
        f"post-terminal event silently dropped — sent={types}"
    )
    # It rides the same drainer wrapper (section = TARGET artifact type) and
    # arrives AFTER the terminal it trails.
    srf = [f for f in ws.sent if f["type"] == "state_restoration_failed"][0]
    assert srf["section"] == "od_ppt_output"
    assert srf["chunk"] is None
    assert types.index("pipeline_complete") < types.index("state_restoration_failed")

    # A lineage-persist failure does NOT fail the run (RESEARCH Open Q2): the
    # dispatch completed, so the row stays "completed".
    row = _row(TestingSession, stub.calls[0]["pipeline_run_id"])
    assert row is not None and row.status == "completed"


# ════════════════════════════════════════════════════════════════════════════
# Receive-loop-level pins (14 review fixes) — drive the REAL websocket_chat
# endpoint with scripted inbound frames so the loop's own guards (not just the
# extracted coroutine) are under test.
# ════════════════════════════════════════════════════════════════════════════


class _ScriptedLoopWebSocket:
    """Drives the REAL ``websocket_chat`` receive loop: scripted inbound JSON
    frames, captured outbound frames, ``WebSocketDisconnect`` once the script
    is exhausted (the loop's normal client-went-away exit)."""

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
            # Yield once so a just-created background task gets scheduled
            # before the next frame is delivered (mirrors a real socket's
            # at-least-one-event-loop-tick gap between frames).
            await asyncio.sleep(0)
            return self._frames.pop(0)
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(code=1000)


# ────────────────────────────────────────────────────────────────────────────
# CR-01 (14 review) — run_revision overlap guard
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overlap_guard_rejects_second_run_revision(ws_env, ws_user, monkeypatch):
    """CR-01 (14 review): a run_revision frame while one is already in flight
    is rejected with ``pipeline_already_running`` (the run_pipeline guard,
    byte-identical error frame) — the in-flight task's cancel handle
    (``current_pipeline_task``) is never overwritten and NO second execution
    starts (pre-14 the inline ``await`` serialized this; the background-task
    dispatch must guard it explicitly)."""
    ws_module, TestingSession = ws_env

    monkeypatch.setattr(ws_module, "_authenticate_token", lambda token, db: ws_user)

    release = asyncio.Event()
    calls: list[tuple] = []

    async def _stub_revision_execution(
        websocket, user, parent_run_id, target, instruction, run_id_sink=None
    ):
        calls.append((parent_run_id, target, instruction))
        await release.wait()  # stays in flight until the endpoint cancels it

    monkeypatch.setattr(ws_module, "_handle_revision_execution", _stub_revision_execution)

    frame = {
        "type": "run_revision",
        "parent_run_id": "parent-1",
        "target_artifact_type": "od_ppt_output",
        "instruction": "Tighten slide 1.",
    }
    ws = _ScriptedLoopWebSocket([frame, dict(frame)])

    try:
        # The endpoint returns after the script exhausts (WebSocketDisconnect),
        # cancelling the still-pending revision task on its way out.
        await asyncio.wait_for(ws_module.websocket_chat(ws), timeout=10.0)
    finally:
        release.set()

    # Exactly ONE execution started — the second frame never dispatched.
    assert len(calls) == 1, (
        f"overlap guard missing: {len(calls)} revision executions started "
        "from one connection"
    )
    rejections = [
        f for f in ws.sent
        if f.get("type") == "error"
        and f.get("data", {}).get("code") == "pipeline_already_running"
    ]
    assert len(rejections) == 1, (
        f"expected one pipeline_already_running rejection: {ws.sent}"
    )
    assert rejections[0]["data"]["recoverable"] is True


# ────────────────────────────────────────────────────────────────────────────
# WR-03 (14 review) — reconnect drainer preserves the revision section contract
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconnect_drainer_preserves_revision_section(ws_env, ws_user, monkeypatch):
    """WR-03 (14 review): a client reconnecting to a LIVE revision run receives
    the remaining stream with ``section = <target_artifact_type>`` (derived
    from the run row's ``*_revision`` type — the inverse of the WR-06 alias
    transform), the same frame shape the revision drainer pins above — never
    ``section: None`` (which would mis-route post-reconnect frames in an FE
    that routes on section)."""
    ws_module, TestingSession = ws_env

    monkeypatch.setattr(ws_module, "_authenticate_token", lambda token, db: ws_user)
    # The AUTHZ-03 live-attach gate resolves the run through a default-deny
    # ScopedStore, which opens app.models.database.SessionLocal — wire it onto
    # the test DB (the test_revision_intelligence.py idiom).
    monkeypatch.setattr(
        "app.models.database.SessionLocal", TestingSession, raising=False
    )

    # A live revision run owned by the reconnecting principal.
    run_id = str(uuid.uuid4())
    db = TestingSession()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=ws_user.id, owner_id=ws_user.id,
            workspace_id="ws-rev", title="Revision: x",
            type="od_ppt_revision", status="revising", input="x",
        ))
        db.commit()
    finally:
        db.close()

    # Simulate the in-flight revision: a real (blocked) bg task + a queue
    # pre-loaded with the remaining stream (one mid-run event + the terminal).
    release = asyncio.Event()

    async def _blocked():
        await release.wait()

    live_task = asyncio.create_task(_blocked())
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put({"type": "agent_chunk", "data": {"text": "slide html..."}})
    await queue.put({"type": "pipeline_complete",
                     "data": {"final_output": "<html>revised</html>"}})
    monkeypatch.setitem(ws_module._PIPELINE_TASKS, run_id, live_task)
    monkeypatch.setitem(ws_module._PIPELINE_QUEUES, run_id, queue)

    ws = _ScriptedLoopWebSocket([
        {"type": "reconnect_pipeline", "pipeline_run_id": run_id},
    ])
    try:
        await asyncio.wait_for(ws_module.websocket_chat(ws), timeout=10.0)
    finally:
        release.set()
        live_task.cancel()

    forwarded = [
        f for f in ws.sent if f["type"] in ("agent_chunk", "pipeline_complete")
    ]
    assert len(forwarded) == 2, f"live frames not forwarded on reconnect: {ws.sent}"
    for frame in forwarded:
        assert frame["section"] == "od_ppt_output", (
            "reconnect drainer must preserve the revision frame contract "
            f"(section = TARGET artifact type), got {frame['section']!r}"
        )
        assert frame["chunk"] is None

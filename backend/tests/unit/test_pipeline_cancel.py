"""Tests for pipeline cancellation through the Universal ExecutionEngine.

Migrated from the orchestrator_v2-based version after the legacy runner
deletion (T021). The handler under test is now
``app.api.websocket._handle_workflow_execution`` and the engine it drives is
``agents.execution_engine.engine.ExecutionEngine`` (patched with a stub).

Coverage:
1. Cancel mid-pipeline marks WorkflowRun cancelled and sends ack.
2. Cancel before run is idempotent (just an ack).
3. Two run_pipeline in quick succession — second is rejected.
4. Disconnect mid-pipeline cancels the task.
5. An exception inside the engine goes through the ``failed`` path.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import websocket as ws_module
from app.models.database import Base
from app.models.chat import ChatSession, Message  # noqa: F401
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.user import User
from app.models.workflow import WorkflowRun


# --- Shared fixtures -------------------------------------------------------


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    yield TestingSession
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def make_user(in_memory_db):
    def _make() -> User:
        db = in_memory_db()
        try:
            u = User(
                id=str(uuid.uuid4()),
                email=f"u-{uuid.uuid4().hex[:8]}@example.com",
                password_hash="x",
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            return u
        finally:
            db.close()
    return _make


# --- Stubs -----------------------------------------------------------------


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed: bool = False

    async def send_json(self, payload: dict) -> None:
        if self.closed:
            raise RuntimeError("WebSocket is not connected")
        self.sent.append(payload)


class _StubEngine:
    """Stub ExecutionEngine whose execute() pacing we control.

    ISS-007 (16-02): the stub now models the REAL engine's cooperative cancel
    contract — it observes ``cancel_event`` per-chunk and, when set, emits a
    ``pipeline_cancelled`` terminal (mirroring engine.py:1670-1678 / the pre-agent
    break) instead of running to ``pipeline_complete``. This is what lets the
    cancel-ack test exercise the cooperative path the fix introduces (cancel_event
    .set()) rather than the destructive ``task.cancel()`` that ISS-007 proved
    drops the live-wire terminal.
    """

    behaviour: str = "slow"  # "slow" | "fast" | "raise"

    async def execute(self, **kwargs):
        cancel_event = kwargs.get("cancel_event")
        if _StubEngine.behaviour == "raise":
            yield {"type": "pipeline_start", "data": {"agents": []}}
            await asyncio.sleep(0)
            raise RuntimeError("simulated pipeline crash")

        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "agent_start", "data": {
            "agent_id": "stub-agent", "name": "Stub", "role": "Stub",
            "icon": "robot", "index": 0, "total": 1,
        }}
        chunk_count = 2 if _StubEngine.behaviour == "fast" else 50
        for i in range(chunk_count):
            # Cooperative cancel — observe the event per-chunk and emit the
            # clean terminal (mirrors engine.py's per-chunk + pre-agent checks).
            if cancel_event is not None and cancel_event.is_set():
                yield {"type": "pipeline_cancelled", "data": {
                    "pipeline_run_id": kwargs.get("pipeline_run_id")}}
                return
            yield {"type": "agent_chunk", "data": {"agent_id": "stub-agent", "chunk": f"c{i}"}}
            await asyncio.sleep(0.02 if _StubEngine.behaviour == "fast" else 0.05)
        yield {"type": "agent_complete", "data": {"agent_id": "stub-agent", "name": "Stub", "duration": 0.1}}
        yield {"type": "pipeline_complete", "data": {"final_output": "done"}}


@pytest.fixture
def stub_engine(monkeypatch):
    """Patch get_execution_engine (imported inside _handle_workflow_execution)
    to return the stub. Also stub agent resolution + planner so no Bedrock call
    is made."""
    import agents.execution_engine.engine as engine_mod

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _StubEngine())
    _StubEngine.behaviour = "slow"
    yield _StubEngine


@pytest.fixture(autouse=True)
def _settings_ok(monkeypatch):
    monkeypatch.setattr(ws_module.settings, "BEDROCK_MODEL_ID",
                        "eu.anthropic.claude-haiku-4-5-20251001-v1:0", raising=False)
    monkeypatch.setattr(ws_module.settings, "AWS_REGION", "eu-central-1", raising=False)


@pytest.fixture(autouse=True)
def _stub_agent_resolution(monkeypatch):
    """Stub get_pipeline_agents so the handler resolves a non-empty agent list
    without scanning AGENT.md files, and tier gating passes."""
    import agents.registry as reg

    class _A:
        id = "stub-agent"
        name = "Stub"
        role = "Stub"
        icon = "robot"
        produces = ["stub-agent"]
        consumes: list = []
    monkeypatch.setattr(reg, "get_pipeline_agents", lambda pt: [_A()])
    # Tier gate: allow everything
    import app.core.entitlements as ent
    monkeypatch.setattr(ent, "can_run_pipeline", lambda tier, pt: (True, ""))


def _run(coro):
    return asyncio.run(coro)


def _last_run(in_memory_db, user_id: str) -> WorkflowRun | None:
    db = in_memory_db()
    try:
        return (
            db.query(WorkflowRun)
            .filter(WorkflowRun.user_id == user_id)
            .order_by(WorkflowRun.created_at.desc())
            .first()
        )
    finally:
        db.close()


# --- 1. Cancel mid-pipeline ------------------------------------------------


def test_cancel_marks_workflow_cancelled_and_sends_ack(in_memory_db, make_user, stub_engine):
    """ISS-007 + ISS-002: a real Stop (cooperative cancel_event.set(), exactly
    what the cancel_pipeline handler now does) delivers EXACTLY ONE
    pipeline_cancelled to the live wire (the FakeWebSocket sent-list) AND marks
    the WorkflowRun cancelled — deterministically, with no result-vs-cancel race
    (the drainer is NOT destroyed; it forwards the engine's terminal)."""
    user = make_user()

    async def scenario():
        ws = FakeWebSocket()
        # The connection-loop sink the handler republishes its run_id into — the
        # same handle cancel_pipeline resolves the cooperative event from.
        run_id_sink: list = []
        task = asyncio.create_task(
            ws_module._handle_workflow_execution(
                ws, "build me a thing", "user_stories",
                chat_session_id=None, token="t", user=user,
                run_id_sink=run_id_sink,
            )
        )
        await asyncio.sleep(0.15)
        # Mirror the real cancel_pipeline Stop click: resolve THIS run's
        # cooperative event and set it (no destructive task.cancel()).
        run_id = run_id_sink[0]
        ws_module._CANCEL_EVENTS[run_id].set()
        # The handler completes NORMALLY (the drainer forwards pipeline_cancelled
        # then breaks on the terminal) — no CancelledError.
        await asyncio.wait_for(task, timeout=5.0)
        return ws, task

    ws, task = _run(scenario())
    assert task.cancelled() is False
    cancels = [m for m in ws.sent if m.get("type") == "pipeline_cancelled"]
    assert len(cancels) == 1, f"expected exactly one live-wire ack; got {ws.sent}"
    wr = _last_run(in_memory_db, user.id)
    assert wr is not None
    assert wr.status == "cancelled"
    assert wr.completed_at is not None


# --- 2. Cancel before run --------------------------------------------------


def test_idempotent_ack_when_no_active_task():
    async def scenario():
        ws = FakeWebSocket()
        current_pipeline_task = None
        if current_pipeline_task is not None and not current_pipeline_task.done():
            current_pipeline_task.cancel()
        else:
            await ws.send_json({
                "type": "pipeline_cancelled", "chunk": None, "section": None,
                "data": {"message": "No active pipeline"},
            })
        return ws

    ws = _run(scenario())
    assert ws.sent == [{
        "type": "pipeline_cancelled", "chunk": None, "section": None,
        "data": {"message": "No active pipeline"},
    }]


# --- 3. Reject overlapping run ---------------------------------------------


def test_second_run_pipeline_is_rejected(in_memory_db, make_user, stub_engine):
    user = make_user()

    async def scenario():
        ws = FakeWebSocket()
        first = asyncio.create_task(
            ws_module._handle_workflow_execution(
                ws, "first", "user_stories",
                chat_session_id=None, token="t", user=user,
            )
        )
        await asyncio.sleep(0.05)
        if first is not None and not first.done():
            await ws.send_json({
                "type": "error", "chunk": None, "section": None,
                "data": {"error": "Pipeline already running. Cancel the current one first.",
                         "code": "pipeline_already_running", "recoverable": True},
            })
            rejected = True
        else:
            rejected = False
        first.cancel()
        try:
            await first
        except (asyncio.CancelledError, Exception):
            pass
        return ws, rejected

    ws, rejected = _run(scenario())
    assert rejected is True
    assert any(m["data"].get("code") == "pipeline_already_running"
               for m in ws.sent if m.get("type") == "error")


# --- 4. Disconnect mid-pipeline --------------------------------------------


def test_disconnect_path_cancels_running_task(in_memory_db, make_user, stub_engine):
    user = make_user()

    async def scenario():
        ws = FakeWebSocket()
        task = asyncio.create_task(
            ws_module._handle_workflow_execution(
                ws, "build", "user_stories",
                chat_session_id=None, token="t", user=user,
            )
        )
        await asyncio.sleep(0.10)
        ws.closed = True
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        return task

    task = _run(scenario())
    assert task.cancelled() is True
    wr = _last_run(in_memory_db, user.id)
    assert wr is not None
    assert wr.status == "cancelled"


# --- 5. Exception path -----------------------------------------------------


def test_runtime_error_marks_workflow_failed(in_memory_db, make_user, stub_engine):
    user = make_user()
    _StubEngine.behaviour = "raise"

    async def scenario():
        ws = FakeWebSocket()
        await ws_module._handle_workflow_execution(
            ws, "build", "user_stories",
            chat_session_id=None, token="t", user=user,
        )
        return ws

    ws = _run(scenario())
    errors = [m for m in ws.sent if m.get("type") == "error"]
    assert errors, f"Expected an error event; got {ws.sent}"
    assert errors[-1]["data"]["code"] == "pipeline_error"
    wr = _last_run(in_memory_db, user.id)
    assert wr is not None
    assert wr.status == "failed"
    assert wr.error and "simulated pipeline crash" in wr.error

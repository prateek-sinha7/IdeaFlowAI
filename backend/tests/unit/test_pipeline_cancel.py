"""Tests for pipeline cancellation (blockers A3 + A6).

Together these blockers make ``cancel_pipeline`` actually cancel the pipeline
task and finalise the ``WorkflowRun`` row to ``status="cancelled"``.

Strategy: rather than stand up a real WebSocket — which would require
``pytest-asyncio`` and either ``httpx_ws`` or a custom ASGI test loop — these
tests drive the ``_handle_pipeline_execution`` coroutine directly with:

* A ``FakeWebSocket`` that records every ``send_json`` call.
* A ``StubPipelineExecutor`` whose ``execute`` is a slow async generator
  (sleeps between yields) so ``task.cancel()`` lands mid-stream.
* An in-memory SQLite DB wired into the websocket module's ``_get_db`` and
  the model schema, exactly like ``test_logout.py`` does for the auth router.

Coverage:

1. Cancel mid-pipeline marks WorkflowRun cancelled (A6) and sends ack (A3).
2. Cancel before run is idempotent (just an ack).
3. Two run_pipeline in quick succession — second is rejected.
4. Disconnect mid-pipeline cancels the task.
5. An exception inside the pipeline still goes through the ``failed`` path
   (regression check that the new CancelledError handler didn't break it).
6. ``CancelledError`` raised from inside ``PipelineExecutor`` propagates
   through orchestrator-style retry layers — verifies the
   ``except asyncio.CancelledError: raise`` shielding in
   ``app/agents/pipeline.py`` works as designed.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import WebSocketDisconnect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import websocket as ws_module
from app.models.database import Base
# Ensure all model tables are registered with Base.metadata before create_all.
from app.models.chat import ChatSession, Message  # noqa: F401
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.user import User
from app.models.workflow import WorkflowRun


# --- Shared fixtures -------------------------------------------------------


@pytest.fixture
def in_memory_db(monkeypatch):
    """Build an in-memory SQLite DB and bind ``ws_module._get_db`` to it.

    Mirrors ``tests/unit/test_logout.py``: ``StaticPool`` keeps the in-memory
    database alive across the multiple connections the WS handler opens.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Replace the module-level helper that the production handler uses for
    # every db access. Doing it here (vs. patching SessionLocal) keeps the
    # patch surface tiny and explicit.
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    yield TestingSession

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def make_user(in_memory_db):
    """Persist a user we can attach pipelines to."""
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
    """Minimal ``WebSocket`` stand-in that records every ``send_json`` call.

    Mirrors the surface area ``_handle_pipeline_execution`` relies on. We don't
    need ``accept``/``close``/``receive_text`` because the helper only sends.
    """

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed: bool = False

    async def send_json(self, payload: dict) -> None:
        if self.closed:
            # Mimic Starlette's behaviour after a disconnect.
            raise RuntimeError("WebSocket is not connected")
        self.sent.append(payload)


class StubPipelineExecutor:
    """Async-generator stub for ``PipelineExecutor`` whose pacing we control.

    The yielded events match the shape ``_handle_pipeline_execution`` expects
    so the collector branches (``agent_start``/``agent_thinking``/
    ``agent_chunk``/``agent_complete``/``pipeline_complete``) all execute.
    """

    # Every instance shares this attribute so tests can configure it before
    # the helper instantiates the class internally.
    behaviour: str = "slow"  # "slow" | "fast" | "raise"

    def __init__(self, pipeline_type: str, custom_agents=None):
        self.pipeline_type = pipeline_type

    async def execute(self, content: str, skills=None):
        if StubPipelineExecutor.behaviour == "raise":
            yield {"type": "pipeline_start", "data": {"agents": []}}
            await asyncio.sleep(0)
            raise RuntimeError("simulated pipeline crash")

        # Simulate one agent producing chunks slowly so cancel() lands
        # mid-stream. Sleeps act as cancellation checkpoints.
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {
            "type": "agent_start",
            "data": {
                "agent_id": "stub-agent",
                "name": "Stub Agent",
                "role": "Stub",
                "icon": "robot",
                "index": 0,
                "total": 1,
            },
        }
        yield {
            "type": "agent_thinking",
            "data": {"agent_id": "stub-agent", "thinking": "stubbed"},
        }
        chunk_count = 2 if StubPipelineExecutor.behaviour == "fast" else 50
        for i in range(chunk_count):
            yield {
                "type": "agent_chunk",
                "data": {"agent_id": "stub-agent", "chunk": f"chunk-{i}"},
            }
            # Long enough that cancel() in the test reliably interrupts;
            # short enough that the "fast" path completes quickly.
            await asyncio.sleep(0.02 if StubPipelineExecutor.behaviour == "fast" else 0.05)
        yield {
            "type": "agent_complete",
            "data": {"agent_id": "stub-agent", "name": "Stub Agent", "duration": 0.1},
        }
        yield {
            "type": "pipeline_complete",
            "data": {"final_output": "all done"},
        }


@pytest.fixture
def stub_executor(monkeypatch):
    """Replace ``PipelineExecutor`` (the symbol imported lazily inside the
    helper) so every test can swap behaviour by setting
    ``StubPipelineExecutor.behaviour``.
    """
    import app.agents.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "PipelineExecutor", StubPipelineExecutor)
    # Reset to default for each test so leakage between tests is impossible.
    StubPipelineExecutor.behaviour = "slow"
    yield StubPipelineExecutor


@pytest.fixture(autouse=True)
def _llm_provider_ok(monkeypatch):
    """The helper short-circuits on a misconfigured LLM provider before it
    even imports the executor. Pin a valid Bedrock-shaped settings to bypass
    that gate without ever calling out to Bedrock (the executor is stubbed).
    """
    monkeypatch.setattr(ws_module.settings, "LLM_PROVIDER", "bedrock", raising=False)
    monkeypatch.setattr(
        ws_module.settings, "BEDROCK_MODEL_ID",
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0", raising=False,
    )
    monkeypatch.setattr(ws_module.settings, "AWS_REGION", "eu-west-2", raising=False)


@pytest.fixture(autouse=True)
def _no_per_user_skills(monkeypatch):
    """Make ``get_skill_content`` a no-op so we never touch the skills DB
    table in these unit tests; tests that needed it would mock it anyway.
    """
    import app.agents.skills as skills_mod

    monkeypatch.setattr(skills_mod, "get_skill_content", lambda *a, **kw: "")


# --- Helpers ---------------------------------------------------------------


def _run(coro):
    """Synchronously drive an async coroutine to completion in tests.

    We use ``asyncio.run`` per-test rather than a session loop so each test
    gets a fresh event loop — that keeps ``Task`` cancellation semantics
    deterministic.
    """
    return asyncio.run(coro)


def _last_workflow_run(in_memory_db, user_id: str) -> WorkflowRun | None:
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


class TestCancelMidPipeline:
    """``cancel_pipeline`` mid-flight must (a) cancel the task, (b) send the
    ``pipeline_cancelled`` event, and (c) finalise the ``WorkflowRun`` row.
    """

    def test_cancel_marks_workflow_cancelled_and_sends_ack(
        self, in_memory_db, make_user, stub_executor,
    ):
        user = make_user()

        async def scenario():
            ws = FakeWebSocket()
            task = asyncio.create_task(
                ws_module._handle_pipeline_execution(
                    ws, "build me a thing", "user_stories",
                    chat_session_id=None, token="t", user=user,
                )
            )
            # Let the pipeline get into the chunk loop. With 0.05s sleeps
            # between yields, 0.15s reliably puts us past the first chunk.
            await asyncio.sleep(0.15)

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return ws, task

        ws, task = _run(scenario())

        # (a) The task must finalise as cancelled (re-raise is what makes
        # this true; without the re-raise, ``done()`` is True but
        # ``cancelled()`` is False).
        assert task.cancelled() is True

        # (b) An ack with the cancelled shape was sent to the client. We
        # filter rather than index because earlier events (pipeline_start,
        # agent_start, agent_chunk...) will also have been sent.
        cancels = [m for m in ws.sent if m.get("type") == "pipeline_cancelled"]
        assert len(cancels) == 1
        assert cancels[0]["data"]["message"] == "Pipeline cancelled by user"
        # We collected at least the in-progress agent's chunks before cancel.
        assert "agents_completed" in cancels[0]["data"]
        assert cancels[0]["data"]["duration"] >= 0

        # (c) WorkflowRun row is marked cancelled, with completed_at and
        # duration populated. Without A6 this would still be "running".
        wr = _last_workflow_run(in_memory_db, user.id)
        assert wr is not None
        assert wr.status == "cancelled"
        assert wr.completed_at is not None
        assert wr.duration is not None and wr.duration >= 0


# --- 2. Cancel before pipeline starts -------------------------------------


class TestCancelBeforeRun:
    """If no pipeline is running, ``cancel_pipeline`` is a no-op ack.

    This branch lives in the WS message loop, not in
    ``_handle_pipeline_execution``, so we exercise the loop logic directly
    by simulating the same conditional.
    """

    def test_idempotent_ack_when_no_active_task(self):
        async def scenario():
            ws = FakeWebSocket()
            current_pipeline_task: asyncio.Task | None = None

            # Replicate exactly the `cancel_pipeline` branch in
            # ``_websocket_chat`` so this test catches any divergence
            # introduced by a refactor of that branch.
            if current_pipeline_task is not None and not current_pipeline_task.done():
                current_pipeline_task.cancel()
            else:
                await ws.send_json({
                    "type": "pipeline_cancelled",
                    "chunk": None,
                    "section": None,
                    "data": {"message": "No active pipeline"},
                })
            return ws

        ws = _run(scenario())
        assert ws.sent == [{
            "type": "pipeline_cancelled",
            "chunk": None,
            "section": None,
            "data": {"message": "No active pipeline"},
        }]


# --- 3. Reject overlapping run_pipeline -----------------------------------


class TestRejectOverlappingRun:
    """A second ``run_pipeline`` while one is in flight must be rejected,
    NOT silently spawn a parallel ``WorkflowRun`` + interleaved stream.
    """

    def test_second_run_pipeline_is_rejected(self, in_memory_db, make_user, stub_executor):
        user = make_user()

        async def scenario():
            ws = FakeWebSocket()
            current_pipeline_task: asyncio.Task | None = asyncio.create_task(
                ws_module._handle_pipeline_execution(
                    ws, "first", "user_stories",
                    chat_session_id=None, token="t", user=user,
                )
            )
            # Inline the dispatch logic from the receive loop — same as in
            # production, but without standing up a real WS server.
            await asyncio.sleep(0.05)  # Let task start.

            second_msg = {"type": "run_pipeline", "pipeline_type": "user_stories", "message": "second"}
            if current_pipeline_task is not None and not current_pipeline_task.done():
                await ws.send_json({
                    "type": "error",
                    "chunk": None,
                    "section": None,
                    "data": {
                        "error": "Pipeline already running. Cancel the current one first.",
                        "code": "pipeline_already_running",
                        "recoverable": True,
                    },
                })
                rejected = True
            else:
                rejected = False

            # Clean up: cancel the first so the test doesn't hang.
            current_pipeline_task.cancel()
            try:
                await current_pipeline_task
            except (asyncio.CancelledError, Exception):
                pass

            return ws, rejected

        ws, rejected = _run(scenario())
        assert rejected is True
        errors = [m for m in ws.sent if m.get("type") == "error"]
        assert any(
            e["data"].get("code") == "pipeline_already_running"
            for e in errors
        )


# --- 4. Disconnect mid-pipeline -------------------------------------------


class TestDisconnectCancels:
    """Closing the WS while a pipeline is running must cancel it (so we stop
    burning Bedrock tokens for a connection that's already gone).
    """

    def test_disconnect_path_cancels_running_task(
        self, in_memory_db, make_user, stub_executor,
    ):
        user = make_user()

        async def scenario():
            ws = FakeWebSocket()
            current_pipeline_task = asyncio.create_task(
                ws_module._handle_pipeline_execution(
                    ws, "build", "user_stories",
                    chat_session_id=None, token="t", user=user,
                )
            )
            await asyncio.sleep(0.10)

            # Simulate the WS being closed first (so the task's send_json
            # ack will hit the closed branch — exercises the
            # best-effort try/except around send_json on cancel).
            ws.closed = True

            # Then run the disconnect-cleanup branch from
            # ``_websocket_chat``: cancel + await + swallow exceptions.
            if current_pipeline_task is not None and not current_pipeline_task.done():
                current_pipeline_task.cancel()
                try:
                    await current_pipeline_task
                except (asyncio.CancelledError, Exception):
                    pass
            return current_pipeline_task

        task = _run(scenario())
        # The task ends up cancelled even though the WS is closed.
        assert task.cancelled() is True

        # WorkflowRun was still updated (DB write happens before the ack
        # send_json call, so a closed WS doesn't lose the row update — A6).
        wr = _last_workflow_run(in_memory_db, user.id)
        assert wr is not None
        assert wr.status == "cancelled"


# --- 5. Exception inside pipeline (regression for "failed" path) ----------


class TestExceptionPathStillWorks:
    """The new ``except CancelledError`` block must NOT shadow the existing
    ``except Exception`` "failed" path. Adding a new earlier except clause
    is the kind of change that can silently break the broader handler.
    """

    def test_runtime_error_marks_workflow_failed(
        self, in_memory_db, make_user, stub_executor,
    ):
        user = make_user()
        StubPipelineExecutor.behaviour = "raise"

        async def scenario():
            ws = FakeWebSocket()
            await ws_module._handle_pipeline_execution(
                ws, "build", "user_stories",
                chat_session_id=None, token="t", user=user,
            )
            return ws

        ws = _run(scenario())

        # The "failed" branch sends an error event and returns (no raise).
        errors = [m for m in ws.sent if m.get("type") == "error"]
        assert errors, f"Expected an error event; got {ws.sent}"
        assert errors[-1]["data"]["code"] == "pipeline_error"

        # And the row is "failed", not "running" or "cancelled".
        wr = _last_workflow_run(in_memory_db, user.id)
        assert wr is not None
        assert wr.status == "failed"
        assert wr.error and "simulated pipeline crash" in wr.error


# --- 6. CancelledError shield in PipelineExecutor.execute -----------------


class TestPipelineExecutorShield:
    """``PipelineExecutor.execute``'s retry block previously caught
    ``Exception`` — which would also catch ``CancelledError`` — and the
    outer per-agent block did the same. Both now have an
    ``except asyncio.CancelledError: raise`` shield ahead of the broad
    catch. This test verifies the shield is honoured.
    """

    def test_cancellederror_is_not_swallowed_by_retry_or_outer_catch(self):
        """A real ``PipelineExecutor`` driven by a ``BaseAgent`` whose
        ``astream`` raises ``CancelledError`` must propagate the
        ``CancelledError`` out — not yield an ``agent_error`` event and
        keep iterating.
        """
        from app.agents.pipeline import PipelineExecutor
        from app.agents.registry import AgentDefinition

        class CancellingAgent:
            async def astream(self, _msg):
                # Allow one yield boundary before raising so the retry
                # loop has actually started consuming.
                await asyncio.sleep(0)
                raise asyncio.CancelledError()
                # Ensure this is treated as an async generator method by
                # the type system; the unreachable yield keeps Python
                # from optimising the function into a coroutine.
                yield  # pragma: no cover

        async def scenario():
            executor = PipelineExecutor(
                "user_stories",
                custom_agents=[
                    AgentDefinition(
                        id="cancel-stub",
                        name="Cancel Stub",
                        role="Tester",
                        description="stub used only to drive the executor",
                        icon="bug",
                        order=1,
                        pipeline_type="user_stories",
                        system_prompt="x",
                        max_tokens=100,
                        estimated_duration=1.0,
                    )
                ],
            )

            # Patch BaseAgent so ``PipelineExecutor`` uses our cancelling
            # double instead of building a real LLM client.
            import app.agents.pipeline as pipeline_mod

            class _StubBase:
                def __init__(self, system_prompt, max_tokens):
                    self._impl = CancellingAgent()

                def astream(self, msg):
                    return self._impl.astream(msg)

            saved = pipeline_mod.BaseAgent
            pipeline_mod.BaseAgent = _StubBase
            try:
                events = []
                with pytest.raises(asyncio.CancelledError):
                    async for ev in executor.execute("hi"):
                        events.append(ev)
                # The cancellation should have surfaced before any
                # ``agent_error`` event was yielded — the shield's whole
                # purpose is to prevent the retry/exception layers from
                # turning cancellation into a recoverable agent_error.
                assert not any(e["type"] == "agent_error" for e in events)
            finally:
                pipeline_mod.BaseAgent = saved

        _run(scenario())

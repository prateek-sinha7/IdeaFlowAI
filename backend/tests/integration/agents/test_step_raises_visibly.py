"""A step whose strategy raises fails the run visibly (run 48b0811e).

Revision 48b0811e's ``blr-write`` wave step raised on its task list ("json_tasks: could
not parse task list as JSON …") before any agent_start. The exception escaped the engine,
the revision driver's ``except ValueError`` failed the run without a log line, the error
event it queued was never stored, and the run row kept ``error=None``.

Now the engine logs it at ERROR with the step id, emits the step's ``agent_error`` and ONE
``pipeline_failed`` carrying the message, and the revision driver saves that reason on the
run. Offline: scripted model, no live calls.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from types import SimpleNamespace

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# (no Postgres / no creds) BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import (  # noqa: E402  (import-for-side-effects order)
    ScriptedFakeChatModel,
    _RUNS_ROOT,
    _ScriptedTurn,
)

MESSAGE = "json_tasks: could not parse task list as JSON — Expecting value: line 1 column 1 (char 0)"


class _RaisingStrategy:
    """Raises before it yields anything, like a wave step whose task list fails to parse.
    With ``cancel_first``, the run is cancelled before the raise (a cancel racing the step)."""

    name = "wave_scheduler"

    def __init__(self, engine, run_id: str, cancel_first: bool) -> None:
        self.engine, self.run_id, self.cancel_first = engine, run_id, cancel_first

    async def run(self, step, ectx):
        if self.cancel_first:
            self.engine._state_machine.transition(self.run_id, "cancelled")
            raise RuntimeError("raced the cancel")
        raise ValueError(MESSAGE)
        yield  # pragma: no cover — makes this an async generator


async def _drive(monkeypatch, events: list[dict], *, cancel_first: bool = False) -> str:
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.capabilities.registry import CapabilityRegistry
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT
    first = get_pipeline_agents("user_stories")[0].id
    run_id = str(uuid.uuid4())
    engine = ExecutionEngine()
    raising = _RaisingStrategy(engine, run_id, cancel_first)

    orig_resolve = CapabilityRegistry.resolve

    def _resolve(self, kind, name, *a, **k):
        return (
            raising if kind == "strategy" else orig_resolve(self, kind, name, *a, **k)
        )

    monkeypatch.setattr(CapabilityRegistry, "resolve", _resolve)
    orig_compile = engine_mod.compile_for_run

    def _compile(pipeline_type, _orig=orig_compile):
        compiled = _orig(pipeline_type)
        compiled.planner = "skip"
        compiled.clarify.mode = "off"
        return compiled

    monkeypatch.setattr(engine_mod, "compile_for_run", _compile)
    orig_create_runner = factory_mod.create_runner

    def _create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(
            [_ScriptedTurn(texts=["never reached"], usage=(1, 1))]
        )
        return orig_create_runner(agent_id, ctx, **kw)

    monkeypatch.setattr(factory_mod, "create_runner", _create_runner)
    monkeypatch.setattr(engine_mod, "create_runner", _create_runner)

    async def _noop(*a, **k):
        return None

    engine._dual_write_artifact = _noop  # type: ignore[assignment]
    async for ev in engine.execute(
        agents=[],
        user_message="build a backlog",
        pipeline_run_id=run_id,
        pipeline_type="user_stories",
        session_id="step-raises",
    ):
        events.append(ev)
    return first


@pytest.mark.asyncio
async def test_a_step_that_raises_before_agent_start_fails_the_run_with_its_message(
    monkeypatch, caplog
):
    caplog.set_level(logging.ERROR, logger="agents.execution_engine.engine")
    events: list[dict] = []
    first = await _drive(monkeypatch, events)  # no exception escapes execute()

    errors = [e["data"] for e in events if e.get("type") == "agent_error"]
    assert [(d["agent_id"], d["error"], d["recoverable"]) for d in errors] == [
        (first, MESSAGE, False)
    ]
    assert (
        "seq" in errors[0]
    )  # stamped by execute(), so it is stored with the run's events
    failed = [e["data"] for e in events if e.get("type") == "pipeline_failed"]
    assert (
        len(failed) == 1
        and failed[0]["error"] == MESSAGE
        and failed[0]["agents_failed"] == [first]
    )
    assert not [e for e in events if e.get("type") == "pipeline_complete"]
    assert any(
        r.levelno == logging.ERROR
        and first in r.getMessage()
        and MESSAGE in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_a_step_that_raises_after_the_run_was_cancelled_propagates_as_before(
    monkeypatch,
):
    # A cancelled run allows no transition to "failed"; the guard must not report it.
    events: list[dict] = []
    with pytest.raises(RuntimeError, match="raced the cancel"):
        await _drive(monkeypatch, events, cancel_first=True)
    assert not [
        e for e in events if e.get("type") in ("agent_error", "pipeline_failed")
    ]


@pytest.mark.asyncio
async def test_the_revision_driver_saves_the_reason_on_the_run(monkeypatch):
    """The driver's own status mapping: a pipeline_failed with an error is saved as
    WorkflowRun.error (a revision used to keep error=None on every failure)."""
    import app.api.run_commands as rc

    class _Engine:
        async def _handle_revision(self, *, websocket_send_fn, **_):
            await websocket_send_fn(
                {
                    "type": "agent_error",
                    "data": {
                        "agent_id": "custom-agent:blr-write",
                        "error": MESSAGE,
                        "recoverable": False,
                    },
                }
            )
            await websocket_send_fn(
                {"type": "pipeline_failed", "data": {"error": MESSAGE}}
            )

    row = SimpleNamespace(id="rev-1", status="revising", error=None, completed_at=None)

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return row

    class _Db:
        def query(self, *_a, **_k):
            return _Query()

        def commit(self):
            pass

        def close(self):
            pass

    import agents.execution_engine.engine as engine_mod

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _Engine())
    monkeypatch.setattr(rc, "_get_db", lambda: _Db())
    monkeypatch.setattr(rc, "_apply_terminal_output_columns", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_cleanup_pipeline", lambda *_a, **_k: None)
    queue: asyncio.Queue = asyncio.Queue()
    await rc._drive_revision_to_queue(
        workflow_run_id="rev-1",
        parent_run_id="parent-1",
        target_artifact_type="backlog_output",
        instruction="x",
        user=SimpleNamespace(id="u-1", preferred_model=None),
        cancel_event=asyncio.Event(),
        event_queue=queue,
    )
    assert (row.status, row.error) == ("failed", MESSAGE)


@pytest.mark.asyncio
async def test_drive_revision_to_queue_persists_bounded_reason_when_driver_raises(
    monkeypatch,
):
    import app.api.run_commands as rc

    class _Engine:
        async def _handle_revision(self, **_):
            raise RuntimeError("provider disconnected")

    row = SimpleNamespace(id="rev-2", status="revising", error=None, completed_at=None)

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return row

    class _Db:
        def query(self, *_a, **_k):
            return _Query()

        def commit(self):
            return None

        def close(self):
            return None

    import agents.execution_engine.engine as engine_mod

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _Engine())
    monkeypatch.setattr(rc, "_get_db", lambda: _Db())
    monkeypatch.setattr(rc, "_apply_terminal_output_columns", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_cleanup_pipeline", lambda *_a, **_k: None)
    queue: asyncio.Queue = asyncio.Queue()

    await rc._drive_revision_to_queue(
        workflow_run_id="rev-2",
        parent_run_id="parent-1",
        target_artifact_type="backlog_output",
        instruction="x",
        user=SimpleNamespace(id="u-1", preferred_model=None),
        cancel_event=asyncio.Event(),
        event_queue=queue,
    )

    assert (row.status, row.error) == (
        "failed",
        "Revision failed: provider disconnected",
    )
    assert await queue.get() == {
        "type": "error",
        "data": {
            "error": "Revision failed: provider disconnected",
            "code": "revision_error",
            "recoverable": True,
        },
    }
    assert await queue.get() is None

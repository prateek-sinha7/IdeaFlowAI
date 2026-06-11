"""tests/agents/test_resume_ws_bridge.py — 12-09 Gap 2a: the engine→WS live-task bridge.

An auto-resumed run (``resume_run``, driven by ``restore_non_terminal_runs``) was never
registered in the WS pipeline registry (``_PIPELINE_TASKS`` / ``_PIPELINE_QUEUES``), so a
reconnect during the resumed run took the live:false branch and the resumed tail —
including ``pipeline_complete`` — was never delivered to a connected client.

The fix is an INJECTED bridge (import-linter-safe — the kernel never imports app.api):
three optional callables on ``ExecutionEngine`` set from the app layer (app/main.py):

  * ``_resume_register_queue(run_id) -> asyncio.Queue`` — registers/returns the run's
    live WS queue BEFORE the resume drive loop (a reconnect mid-resume finds it);
  * ``_resume_register_task(run_id, task)`` — records the resume driver task at the
    ``create_task`` site in ``restore_non_terminal_runs``;
  * ``_resume_cleanup(run_id)`` — drops the registry entries when the drive finishes.

All three default ``None`` → the bridge is DORMANT (byte/event-identical) for every
construction path that does not set them — proven by the parity test below.

Offline / in-memory SQLite / no API key / no network — the ``backend:characterization``
job. Reuses the ``_ResumeHarness`` from test_restart_resume.py.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

from tests.agents.test_restart_resume import (  # noqa: E402
    _ResumeHarness,
    _make_session,
    _seed_workflow_run,
)

_ENGINE_SRC = (
    Path(__file__).resolve().parents[2]
    / "agents" / "execution_engine" / "engine.py"
)


# ===========================================================================
# (1)+(2)+(3) — queue registered before the drive emits; every resumed event
#               lands on the live queue (incl. the terminal pipeline_complete);
#               a None sentinel terminates the queue; cleanup fires.
# ===========================================================================


@pytest.mark.asyncio
async def test_resume_run_pushes_resumed_tail_onto_registered_live_queue():
    session, db_engine = _make_session()
    run_id = f"br-{uuid.uuid4().hex[:8]}"
    owner = "br-user"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    registered_queues: dict[str, asyncio.Queue] = {}
    cleanup_calls: list[str] = []
    call_order: list[str] = []

    def _reg_queue(rid: str) -> asyncio.Queue:
        call_order.append(f"queue_registered:{rid}")
        return registered_queues.setdefault(rid, asyncio.Queue())

    def _cleanup(rid: str) -> None:
        cleanup_calls.append(rid)

    call_log: dict[str, int] = {}
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        engine._resume_register_queue = _reg_queue
        engine._resume_cleanup = _cleanup
        await engine.resume_run(run_id)

    # (1) The run's live queue was registered (before the drive loop — the
    # registration is the FIRST bridge interaction; events only exist after it).
    assert run_id in registered_queues, "resume_run did not register the live queue"
    assert call_order and call_order[0] == f"queue_registered:{run_id}"

    # (2) Drain the live queue: every resumed event landed on it, terminated by
    # the None sentinel (3). The terminal pipeline_complete is in the tail — the
    # exact event a reconnected live-attach drainer must receive (Gap 2a).
    q = registered_queues[run_id]
    drained: list[dict] = []
    saw_sentinel = False
    while True:
        try:
            item = q.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is None:
            saw_sentinel = True
            break
        drained.append(item)

    assert drained, "no resumed events were pushed onto the live queue"
    types = [e["type"] for e in drained]
    assert "pipeline_complete" in types, (
        f"the resumed tail must include the terminal pipeline_complete; got {types}"
    )
    # Every queued event matches the run_pipeline queue contract: a dict with
    # type + data, the data carrying the stamped seq/event_id (the same payload
    # the durable sink persisted — replay/live dedupe by event_id stays valid).
    for e in drained:
        assert isinstance(e.get("data"), dict)
        assert "seq" in e["data"] and "event_id" in e["data"]

    # (3) The None sentinel terminates the queue (the drainer's end-of-stream).
    assert saw_sentinel, "the live queue was not terminated with the None sentinel"

    # The injected cleanup fired for this run (no stale registration).
    assert cleanup_calls == [run_id]
    session.close()


# ===========================================================================
# restore_non_terminal_runs registers the DRIVER TASK at the create_task site
# ===========================================================================


@pytest.mark.asyncio
async def test_restore_registers_resume_driver_task_via_bridge():
    session, db_engine = _make_session()
    run_id = f"bt-{uuid.uuid4().hex[:8]}"
    _seed_workflow_run(session, run_id, owner="bt-user", status="generating")

    registered_tasks: dict[str, asyncio.Task] = {}

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()

        # Classify the seeded run as resumable (branch b) and stub the driver so
        # the test isolates the REGISTRATION at the create_task site.
        async def _resumable(wr):
            return True

        resume_driven = asyncio.Event()

        async def _quick_resume(rid):
            resume_driven.set()

        engine._is_resumable_in_flight = _resumable  # type: ignore[assignment]
        engine.resume_run = _quick_resume  # type: ignore[assignment]
        engine._resume_register_task = (
            lambda rid, task: registered_tasks.__setitem__(rid, task)
        )

        await engine.restore_non_terminal_runs()
        # Let the spawned driver task run to completion.
        await asyncio.wait_for(resume_driven.wait(), timeout=5)

    assert run_id in registered_tasks, (
        "restore_non_terminal_runs did not register the resume driver task"
    )
    assert isinstance(registered_tasks[run_id], asyncio.Task), (
        "the registered object must be the asyncio.Task driving resume_run"
    )
    session.close()


# ===========================================================================
# (4) — DORMANT bridge parity: without the hooks, resume_run drives identically
# ===========================================================================


@pytest.mark.asyncio
async def test_bridge_dormant_without_hooks_resume_drives_identically():
    """With NO hooks set (the default — every offline/characterization path),
    resume_run drives the run to completion exactly as before and never raises."""
    from app.models.run_event import RunEvent

    session, db_engine = _make_session()
    run_id = f"bd-{uuid.uuid4().hex[:8]}"
    owner = "bd-user"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    call_log: dict[str, int] = {}
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        # Hooks untouched — all three default None (the dormant bridge).
        assert engine._resume_register_queue is None
        assert engine._resume_register_task is None
        assert engine._resume_cleanup is None
        await engine.resume_run(run_id)

    # The resume persisted its events to the durable log (the drive completed) —
    # the queue-less behavior is unchanged.
    rows = session.query(RunEvent).filter(RunEvent.run_id == run_id).all()
    assert rows, "dormant-bridge resume_run must still drive + persist events"
    assert any(r.type == "pipeline_complete" for r in rows)
    session.close()


# ===========================================================================
# import-linter direction: the kernel never imports app.api
# ===========================================================================


def test_engine_module_does_not_import_app_api():
    """The bridge MUST stay an injected callback — engine.py never imports app.api
    (the import-linter forbidden direction) nor the websocket module."""
    import re

    source = _ENGINE_SRC.read_text(encoding="utf-8")
    offending = re.findall(
        r"^\s*(?:from\s+app\.api\b.*|import\s+app\.api\b.*)$", source, re.MULTILINE
    )
    assert not offending, (
        "agents/execution_engine/engine.py must not import app.api — the "
        f"engine→WS bridge is an injected callback, never a direct import: {offending}"
    )
    assert "import websocket" not in source
    assert "from app.api.websocket" not in source

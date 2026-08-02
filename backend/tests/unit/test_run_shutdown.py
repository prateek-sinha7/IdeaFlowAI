"""tests/unit/test_run_shutdown.py — H-11 (SSE pump tasks must join coordinated shutdown).

Before this fix, ``shutdown_run_infrastructure`` sentinelled every entry in
``_PIPELINE_QUEUES`` but never awaited or cancelled the corresponding entries in
``run_engine._PUMP_TASKS``. A pump that was slow to drain to its sentinel (or one
whose subscriber queue was momentarily full) was still running when the lifespan
proceeded to close the checkpointer's Postgres pool underneath it (step 4) — the
module's own docstring already anticipated this must change ("AFTER A2 lands,
`_close_run` is the single idempotent teardown ... cancels the pump ...").

These tests drive ``shutdown_run_infrastructure`` directly against the REAL
``run_engine`` module-level registries (no mocking of the pump machinery), with
``close_checkpointer`` monkeypatched to a no-op so the test stays fully offline
(no Postgres pool to actually close).
"""

from __future__ import annotations

import asyncio

import pytest

import app.api.run_engine as run_engine_mod
import app.api.run_shutdown as run_shutdown_mod


@pytest.fixture(autouse=True)
def _isolate_registries(monkeypatch):
    """Clear every module-level registry the shutdown path touches, and stub the
    checkpointer close so the test never needs a real Postgres pool."""
    from app.api import run_commands as rc_mod

    async def _noop_close_checkpointer() -> None:
        return None

    monkeypatch.setattr(
        "app.agents.checkpointer.close_checkpointer", _noop_close_checkpointer
    )

    run_engine_mod._PIPELINE_QUEUES.clear()
    run_engine_mod._PIPELINE_TASKS.clear()
    run_engine_mod._CANCEL_EVENTS.clear()
    run_engine_mod._SUBSCRIBERS.clear()
    run_engine_mod._QUEUE_GENERATIONS.clear()
    for t, _gen in run_engine_mod._PUMP_TASKS.values():
        t.cancel()
    run_engine_mod._PUMP_TASKS.clear()
    rc_mod._CONCIERGE_STREAM_TASKS.clear()
    rc_mod._LIVE_ECTX.clear()

    yield

    # Best-effort: a test may have monkeypatched _PUMP_TASKS itself (the registry-
    # corruption test) or already had its tasks cancelled/awaited by the shutdown
    # path under test, so tolerate a foreign/closed object here.
    try:
        for t, _gen in run_engine_mod._PUMP_TASKS.values():
            if not t.done():
                t.cancel()
    except Exception:  # noqa: BLE001
        pass
    run_engine_mod._PIPELINE_QUEUES.clear()
    run_engine_mod._PIPELINE_TASKS.clear()
    run_engine_mod._CANCEL_EVENTS.clear()
    run_engine_mod._SUBSCRIBERS.clear()
    run_engine_mod._QUEUE_GENERATIONS.clear()
    try:
        run_engine_mod._PUMP_TASKS.clear()
    except Exception:  # noqa: BLE001
        pass
    rc_mod._CONCIERGE_STREAM_TASKS.clear()
    rc_mod._LIVE_ECTX.clear()


class TestShutdownDrainsPumpTasks:
    @pytest.mark.asyncio
    async def test_pump_that_finishes_promptly_is_drained_not_cancelled(self):
        """A pump that observes its sentinel quickly should be reported as
        DRAINED (finished cleanly), not force-cancelled."""
        run_engine_mod._get_or_create_queue("run-1")
        run_engine_mod._PIPELINE_TASKS["run-1"] = asyncio.current_task()
        sub_q = await run_engine_mod._subscribe("run-1")

        summary = await run_shutdown_mod.shutdown_run_infrastructure()

        # The queue-sentinel step (2) put None onto the producer queue; the real
        # pump task drains it and exits on its own well within the drain budget.
        assert summary["pump_tasks_in_flight"] == 1
        assert summary["pump_tasks_drained"] == 1
        assert summary["pump_tasks_cancelled"] == 0
        assert summary["errors"] == []

        # The subscriber must have received the forwarded sentinel.
        event = await asyncio.wait_for(sub_q.get(), timeout=1.0)
        assert event is None

    @pytest.mark.asyncio
    async def test_stuck_pump_is_cancelled_within_the_drain_budget(self, monkeypatch):
        """A pump that never reaches its sentinel (e.g. its dispatch hangs) must be
        force-cancelled rather than left running past the shutdown teardown —
        this is the H-11 regression: before the fix nothing awaited or cancelled
        _PUMP_TASKS at all, so a stuck pump would run forever, still holding
        whatever DB/connection resources it referenced when the checkpointer pool
        below it was closed."""
        monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_TASK_DRAIN_SECONDS", 0.05)

        async def _stuck_forever() -> None:
            await asyncio.Event().wait()  # never completes on its own

        stuck_task = asyncio.create_task(_stuck_forever())
        run_engine_mod._PUMP_TASKS["run-stuck"] = (stuck_task, 1)

        summary = await run_shutdown_mod.shutdown_run_infrastructure()

        assert summary["pump_tasks_in_flight"] == 1
        assert summary["pump_tasks_cancelled"] == 1
        assert stuck_task.cancelled() or stuck_task.done()

    @pytest.mark.asyncio
    async def test_no_pump_tasks_is_a_clean_no_op(self):
        """The common case (no run ever attached a subscriber, so no pump was ever
        started) must not error or hang the shutdown path."""
        summary = await run_shutdown_mod.shutdown_run_infrastructure()
        assert summary["pump_tasks_in_flight"] == 0
        assert summary["pump_tasks_drained"] == 0
        assert summary["pump_tasks_cancelled"] == 0
        assert summary["errors"] == []

    @pytest.mark.asyncio
    async def test_pump_drain_failure_is_captured_not_raised(self, monkeypatch):
        """Shutdown must never raise — a broken registry access during the pump
        drain step degrades to a logged error, and the rest of shutdown (the
        checkpointer close) still runs."""

        class _BoomDict(dict):
            def values(self):
                raise RuntimeError("simulated registry corruption")

        monkeypatch.setattr(run_engine_mod, "_PUMP_TASKS", _BoomDict())

        summary = await run_shutdown_mod.shutdown_run_infrastructure()

        assert any("pump_drain" in e for e in summary["errors"])
        assert summary["checkpointer_closed"] is True

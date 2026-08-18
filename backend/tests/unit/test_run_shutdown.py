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

    # ISS-088: SHUTDOWN_STOP_RUNS' default is now environment-differentiated (True in
    # ENV=development, False everywhere else), so whether step 3 runs would otherwise
    # depend on the ambient ENV of whoever runs pytest. Every test below asserts the
    # stop-runs-OFF behaviour, so pin that branch explicitly; the ON branch has its own
    # class (TestShutdownStopsRunsWhenEnabled) which re-pins it.
    monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_STOP_RUNS", False)

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


class TestShutdownStopsRunsWhenEnabled:
    """ISS-088 — step 3, which no test exercised until the default became env-differentiated.

    ``SHUTDOWN_STOP_RUNS`` now resolves True in ``ENV=development``, so on every developer
    machine this is the branch that actually runs. It was previously dead in tests: the
    only coverage of ``_drain_then_cancel`` came through ``stop_run_driver`` (the per-run
    Stop), never through the shutdown sweep.
    """

    @pytest.mark.asyncio
    async def test_enabled_stop_runs_cancels_drivers_and_empties_the_boot_restore_set(
        self, monkeypatch
    ):
        """With the switch on, in-flight drivers are stopped and nothing is left for the
        next boot's ``restore_non_terminal_runs`` to auto-resume — which is the whole
        point of turning it on locally (an od_prototype build survives a restart today
        and bills 5-21M Bedrock tokens finishing itself)."""
        monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_STOP_RUNS", True)
        monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_TASK_DRAIN_SECONDS", 0.05)

        cooperative_event = asyncio.Event()

        async def _driver() -> None:
            await cooperative_event.wait()  # the engine's cooperative boundary

        task = asyncio.create_task(_driver())
        run_engine_mod._PIPELINE_TASKS["run-live"] = task
        run_engine_mod._CANCEL_EVENTS["run-live"] = cooperative_event

        summary = await run_shutdown_mod.shutdown_run_infrastructure()

        assert summary["pipeline_drivers_stopped"] == 1
        assert summary["runs_left_for_boot_restore"] == 0
        assert task.done()
        # The cooperative event is the mechanism; cancel() is only the fallback, so a
        # driver that observes it must NOT be force-cancelled (ISS-007's contract).
        assert not task.cancelled()
        assert summary["errors"] == []

    @pytest.mark.asyncio
    async def test_disabled_stop_runs_leaves_the_run_for_boot_restore(self, monkeypatch):
        """The production branch: the driver is untouched and the run stays in the set the
        next boot re-adopts. This is what keeps the Phase 45-50 resume tier working."""
        monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_STOP_RUNS", False)

        async def _driver() -> None:
            await asyncio.Event().wait()

        task = asyncio.create_task(_driver())
        run_engine_mod._PIPELINE_TASKS["run-live"] = task
        try:
            summary = await run_shutdown_mod.shutdown_run_infrastructure()

            assert summary["pipeline_drivers_stopped"] == 0
            assert summary["runs_left_for_boot_restore"] == 1
            assert not task.done(), "the driver must survive a stop-runs-off shutdown"
        finally:
            task.cancel()


class TestPerRunStopEscalation:
    """ISS-084 — the ``POST /cancel`` fallback, sharing the shutdown sweep's ONE bounded
    escalation policy (``_drain_then_cancel``) rather than a second, untested one.

    Before KAN-88 the WS Stop handler had a destructive fallback; KAN-88 deleted it on the
    false premise that resumed runs read the cooperative event, and Phase 44's REST port
    kept only the cooperative branch — leaving no path at all by which a user could stop a
    run stuck in the mid-model-call blind window (``read_timeout=600``).
    """

    @pytest.mark.asyncio
    async def test_a_driver_that_ignores_the_stop_is_cancelled_and_left_terminal(
        self, monkeypatch
    ):
        """A driver that cannot observe the cooperative event inside the drain budget is
        force-cancelled — and the row is then reconciled to a TERMINAL status, because a
        non-terminal row is re-adopted by the next boot's ``restore_non_terminal_runs``
        and driven to completion at the owner's expense."""
        monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_TASK_DRAIN_SECONDS", 0.05)
        reconciled: list[str] = []

        async def _spy_reconcile(run_id: str) -> None:
            reconciled.append(run_id)

        monkeypatch.setattr(
            "app.api.run_commands._reconcile_terminal_status", _spy_reconcile
        )

        async def _ignores_the_signal() -> None:
            await asyncio.Event().wait()  # e.g. parked mid-Bedrock-call

        task = asyncio.create_task(_ignores_the_signal())
        run_engine_mod._PIPELINE_TASKS["run-stuck"] = task
        run_engine_mod._CANCEL_EVENTS["run-stuck"] = asyncio.Event()
        run_engine_mod._CANCEL_EVENTS["run-stuck"].set()  # what POST /cancel does

        await run_shutdown_mod.stop_run_driver("run-stuck")

        assert task.done(), "an unresponsive driver must not survive a Stop"
        assert reconciled == ["run-stuck"], (
            "a force-cancelled run must be reconciled terminal, or the next boot "
            "re-adopts it"
        )

    @pytest.mark.asyncio
    async def test_a_cooperative_driver_is_never_force_cancelled(self, monkeypatch):
        """ISS-007's contract is preserved: escalation is a FALLBACK, not the mechanism.
        A driver that observes the event and unwinds cleanly (yielding its own
        ``pipeline_cancelled``) must reach ``done()`` un-cancelled — a destructive kill
        here would race the terminal off the wire, which is the defect Phase 16-02
        removed."""
        monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_TASK_DRAIN_SECONDS", 1.0)

        async def _spy_reconcile(run_id: str) -> None:
            return None

        monkeypatch.setattr(
            "app.api.run_commands._reconcile_terminal_status", _spy_reconcile
        )

        event = asyncio.Event()

        async def _cooperative() -> None:
            await event.wait()  # the engine's cooperative boundary

        task = asyncio.create_task(_cooperative())
        run_engine_mod._PIPELINE_TASKS["run-coop"] = task
        run_engine_mod._CANCEL_EVENTS["run-coop"] = event
        event.set()  # what POST /cancel does

        await run_shutdown_mod.stop_run_driver("run-coop")

        assert task.done() and not task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_run_driver_is_a_no_op_without_a_live_task(self):
        """No registered driver (or an un-introspectable sentinel) → nothing to escalate
        against, and no terminal is stamped on a run whose state is unknown."""
        await run_shutdown_mod.stop_run_driver("run-absent")
        run_engine_mod._PIPELINE_TASKS["run-sentinel"] = object()
        await run_shutdown_mod.stop_run_driver("run-sentinel")

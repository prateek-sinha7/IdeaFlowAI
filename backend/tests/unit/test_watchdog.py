"""tests/unit/test_watchdog.py — the event-loop lag watchdog (app/core/watchdog.py).

STABILIZATION.md diagnosability: proves the lag monitor actually detects a
blocked event loop (a synchronous ``time.sleep`` in a scheduled coroutine —
the same class of bug as a sync DB call inside an async handler) rather than
merely asserting on its source code.
"""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from app.core import watchdog


@pytest.mark.asyncio
async def test_watchdog_warns_when_the_loop_falls_behind(caplog, monkeypatch):
    monkeypatch.setattr(watchdog, "POLL_INTERVAL_SECONDS", 0.2)
    monkeypatch.setattr(watchdog, "WARN_LAG_SECONDS", 0.5)
    monkeypatch.setattr(
        watchdog, "ERROR_LAG_SECONDS", 999.0
    )  # keep this test to the warning path

    async def block_the_loop():
        # A synchronous sleep inside a coroutine blocks the WHOLE loop for its
        # duration — exactly what a blocking DB call or a busy retry loop does.
        time.sleep(3)

    task = asyncio.create_task(watchdog.watch_event_loop_lag())
    # Let the watchdog task actually start and enter its own `asyncio.sleep`
    # BEFORE the synchronous block below — otherwise `create_task` has only
    # scheduled it and the block-then-resume never overlaps its wakeup.
    await asyncio.sleep(0)
    with caplog.at_level(logging.WARNING, logger="app.core.watchdog"):
        await block_the_loop()
        # Let the watchdog's already-overdue sleep resolve and log.
        await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    warnings = [r for r in caplog.records if "event loop lag" in r.message]
    assert (
        warnings
    ), f"expected a lag warning, got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_watchdog_error_path_dumps_task_stacks(caplog, monkeypatch):
    monkeypatch.setattr(watchdog, "POLL_INTERVAL_SECONDS", 0.2)
    monkeypatch.setattr(watchdog, "WARN_LAG_SECONDS", 0.5)
    monkeypatch.setattr(watchdog, "ERROR_LAG_SECONDS", 1.0)
    monkeypatch.setattr(watchdog, "ERROR_DUMP_COOLDOWN_SECONDS", 60.0)

    async def block_the_loop():
        time.sleep(3)

    task = asyncio.create_task(watchdog.watch_event_loop_lag())
    await asyncio.sleep(0)  # let the watchdog task start its own sleep first
    with caplog.at_level(logging.WARNING, logger="app.core.watchdog"):
        await block_the_loop()
        await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert (
        errors
    ), f"expected an error-level stack dump, got: {[r.message for r in caplog.records]}"
    assert "all task stacks" in errors[0].message

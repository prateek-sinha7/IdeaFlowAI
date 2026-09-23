"""Event-loop lag watchdog.

STABILIZATION.md postmortem (2026-09-02): uvicorn served a run to completion,
logged its SSE close, then produced ZERO log output for 5h19m while pinned at
~39% CPU — `/health` unresponsive, no traceback, no error. A single-threaded
asyncio process has exactly one symptom for "something synchronous is blocking
the loop": every OTHER coroutine, including a scheduled wakeup, arrives late.
This task polls that gap directly instead of waiting for a request to time out
and guess. It is diagnostic-only: it never touches DB/IO itself, so it cannot
be the cause of a hang, only its reporter.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback

logger = logging.getLogger("app.core.watchdog")

POLL_INTERVAL_SECONDS = 1.0
WARN_LAG_SECONDS = 2.0
ERROR_LAG_SECONDS = 10.0
# One full task-stack dump per stall is enough to diagnose it; without a
# cooldown a stall that persists for minutes would log the same dump every
# single poll.
ERROR_DUMP_COOLDOWN_SECONDS = 60.0


def _dump_all_task_stacks() -> str:
    """Render every task's current call stack (``task.get_stack()``), one block
    per task, so a stalled poll gives a traceback instead of a guess."""
    output_lines = []
    for task in asyncio.all_tasks():
        output_lines.append(f"--- task {task.get_name()} ---")
        stack = task.get_stack()
        if not stack:
            output_lines.append("  <no stack>")
            continue
        for frame in stack:
            output_lines.append("".join(traceback.format_stack(frame)).rstrip())
    return "\n".join(output_lines)


async def watch_event_loop_lag() -> None:
    """Run until cancelled: sleep 1s, log if the wakeup arrived late.

    Lag = actual elapsed time minus the requested sleep. Warns past
    ``WARN_LAG_SECONDS``; past ``ERROR_LAG_SECONDS`` also dumps every task's
    stack once (rate-limited by ``ERROR_DUMP_COOLDOWN_SECONDS``) so the
    blocking call itself is visible, not just its symptom.
    """
    last_dump = 0.0
    while True:
        start = time.monotonic()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        lag = (time.monotonic() - start) - POLL_INTERVAL_SECONDS
        if lag < WARN_LAG_SECONDS:
            continue
        if lag >= ERROR_LAG_SECONDS:
            now = time.monotonic()
            if now - last_dump >= ERROR_DUMP_COOLDOWN_SECONDS:
                last_dump = now
                logger.error(
                    "event loop lag %.2fs (>= %.1fs) — all task stacks:\n%s",
                    lag, ERROR_LAG_SECONDS, _dump_all_task_stacks(),
                )
                continue
        logger.warning("event loop lag %.2fs (>= %.1fs)", lag, WARN_LAG_SECONDS)

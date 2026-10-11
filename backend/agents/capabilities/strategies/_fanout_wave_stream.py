"""agents/capabilities/strategies/_fanout_wave_stream.py — wave-scoped fan-out merge.

A wave clones ONE agent N times (``agent="self"``), so every worker's own per-agent
events (agent_start/agent_chunk/tool_call/tool_result/agent_complete — pushed onto
the ``run_fanout`` side-channel queue, see ``_fanout_stream.py``) carry the SAME
``agent_id`` as the parent step. The frontend keys nodes on ``agent_id``, so N
workers collapse onto one node and re-render it N times instead of nesting as
children under the parent.

This module is a wave-specific COPY of ``_fanout_stream.py``'s merge loop (the
caller — ``wave_scheduler`` — must not import ``_fanout_stream.py``'s sibling
``parallel_group`` concern) that ADDS per-worker identity stamping to every event
sourced off the WORKER queue: ``wave_index`` / ``step`` / ``task_id`` /
``worker_index`` / ``wave_total``. Events sourced off the ``run_fanout`` generator
itself (``subagent_spawned`` / ``subagent_result``) are left untouched — the caller
already stamps those (CR-06, wave_scheduler.py).

Worker identity (``worker_index`` / ``task_id``) is carried on the wire: ``fanout.py``
stamps both onto a COPY of each queued event's ``data`` dict at push time (it is the
only place that knows which worker pushed the event). This module reads them straight
off the event and layers on the wave-only fields it alone owns (``wave_index`` /
``step`` / ``wave_total``). An event that somehow arrives without ``worker_index``/
``task_id`` (a caller on an older kernel, or the defensive case) passes through
unstamped rather than guessing.

Import purity (INV-13): stdlib + typing only — nothing from ``agents.execution_engine``
or ``app.*``. The kernel is reached only through the caller's ``runner`` handle.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator


async def stream_wave_fanout(
    runner: Any,
    requests: list[dict],
    ctx: Any,
    *,
    step: Any,
    wave_index: int,
    task_ids: list[str],
) -> AsyncIterator[dict]:
    """Run one wave's fan-out, stamping wave identity onto each queued worker event.

    ``requests``/``task_ids`` are parallel lists (index ``i`` of each belongs to the
    same worker). Fan-out lifecycle events (``subagent_spawned``/``subagent_result``)
    pass through UNCHANGED — the caller stamps those itself (CR-06). Every event
    sourced off the worker side-channel queue already carries ``worker_index``/
    ``task_id`` (stamped by ``fanout.py`` at push time); this layers on ``wave_index``,
    ``step`` (the parent step id) and ``wave_total`` on a COPY of its data dict (a
    shared dict must never be mutated under the kernel). An event missing
    ``worker_index``/``task_id`` passes through unstamped rather than guessing.
    """
    step_id = getattr(step, "agent_id", None)
    wave_total = len(task_ids)

    def _stamp_queued(event: dict) -> dict:
        data = event.get("data") or {}
        if "worker_index" not in data or "task_id" not in data:
            return event

        data = dict(data)
        data["wave_index"] = wave_index
        data["step"] = step_id
        data["wave_total"] = wave_total
        return {**event, "data": data}

    child_events: asyncio.Queue[dict] = asyncio.Queue()
    fanout_iter = runner.run_fanout(
        requests, ctx, step=step, event_queue=child_events
    ).__aiter__()

    next_fanout: asyncio.Task[dict] | None = asyncio.ensure_future(
        fanout_iter.__anext__()
    )
    next_queued: asyncio.Task[dict] | None = asyncio.ensure_future(child_events.get())
    try:
        # Same race handling as _fanout_stream.stream_fanout — see that module for
        # the invariant this loop preserves (kept faithful on purpose).
        while next_fanout is not None or next_queued is not None:
            pending_futs = {t for t in (next_fanout, next_queued) if t is not None}
            done, _ = await asyncio.wait(
                pending_futs, return_when=asyncio.FIRST_COMPLETED
            )

            if next_fanout is not None and next_fanout in done:
                try:
                    yield next_fanout.result()
                    next_fanout = asyncio.ensure_future(fanout_iter.__anext__())
                except StopAsyncIteration:
                    next_fanout = None
                    if next_queued is not None:
                        if next_queued in done:
                            yield _stamp_queued(next_queued.result())
                        else:
                            next_queued.cancel()
                        next_queued = None
                    while not child_events.empty():
                        yield _stamp_queued(child_events.get_nowait())
                    continue

            if next_queued is not None and next_queued in done:
                yield _stamp_queued(next_queued.result())
                next_queued = asyncio.ensure_future(child_events.get())

    except asyncio.CancelledError:
        for t in (next_fanout, next_queued):
            if t is not None:
                t.cancel()
        await fanout_iter.aclose()
        raise

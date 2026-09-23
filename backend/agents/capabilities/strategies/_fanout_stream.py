"""agents/capabilities/strategies/_fanout_stream.py — live per-worker event merge.

``run_fanout`` yields lifecycle-only events (``subagent_spawned`` /
``subagent_result``). Each worker's OWN per-agent events (agent_start /
agent_chunk / tool_call / tool_result / agent_complete) are pushed onto an
optional side-channel queue instead (``fanout.py``: ``event_queue``).

A strategy that wants live per-worker streaming has to consume BOTH — the
generator and the queue — concurrently, or the queued events only surface after
the whole fan-out finishes. ``parallel_group`` had that merge inline; the wave
scheduler needs exactly the same thing, so it lives here once.

Import purity (INV-13): nothing from ``agents.execution_engine`` or ``app.*`` —
the kernel is reached only through the caller's ``runner`` handle.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator


async def stream_fanout(
    runner: Any, requests: list[dict], ctx: Any, *, step: Any
) -> AsyncIterator[dict]:
    """Run a fan-out, yielding its lifecycle events AND each worker's own events.

    Same spawn path as a bare ``runner.run_fanout(...)`` (INV-12) — this only adds
    the side-channel queue and interleaves the two sources as they arrive.
    """
    child_events: asyncio.Queue[dict] = asyncio.Queue()
    fanout_iter = runner.run_fanout(
        requests, ctx, step=step, event_queue=child_events
    ).__aiter__()

    next_fanout: asyncio.Task[dict] | None = asyncio.ensure_future(
        fanout_iter.__anext__()
    )
    next_queued: asyncio.Task[dict] | None = asyncio.ensure_future(child_events.get())
    try:
        # Loop while there is still a fanout event to come OR a queued-item wait in
        # flight. next_queued is set to None only once fanout_iter is exhausted AND
        # the queue has been fully drained — the ONLY way this loop ends.
        while next_fanout is not None or next_queued is not None:
            pending = {t for t in (next_fanout, next_queued) if t is not None}
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

            if next_fanout is not None and next_fanout in done:
                try:
                    yield next_fanout.result()
                    next_fanout = asyncio.ensure_future(fanout_iter.__anext__())
                except StopAsyncIteration:
                    # No worker can push to child_events after this point
                    # (run_fanout doesn't exhaust until every worker task is done)
                    # — safe to stop waiting on it. But next_queued may have ALSO
                    # completed in this same asyncio.wait() batch (same-tick race);
                    # its result is already out of the queue and must be yielded
                    # here, not discarded by cancelling it unread.
                    next_fanout = None
                    if next_queued is not None:
                        if next_queued in done:
                            yield next_queued.result()
                        else:
                            next_queued.cancel()
                        next_queued = None
                    while not child_events.empty():
                        yield child_events.get_nowait()
                    continue

            if next_queued is not None and next_queued in done:
                yield next_queued.result()
                next_queued = asyncio.ensure_future(child_events.get())

    except asyncio.CancelledError:
        for t in (next_fanout, next_queued):
            if t is not None:
                t.cancel()
        await fanout_iter.aclose()
        raise

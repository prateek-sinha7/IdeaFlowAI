"""In-process fan-out of builder events to the clients of one Session (design 3.3.5).

The Turn_Runner publishes every :data:`BuilderEvent` of a Turn here and each
connected Session_Stream reads its own bounded queue. The eviction policy
mirrors the run fan-out in ``run_engine.py`` (rule H-09): a subscriber whose
queue is full is removed and receives a ``None`` sentinel, so its client
reconnects and gets a fresh ``Snapshot`` instead of silently losing an event.

The bus keeps its own registry. It never touches ``_PIPELINE_QUEUES``,
``_SUBSCRIBERS`` or the pump generations of ``run_engine.py``.

Every method is synchronous and never awaits. The event loop runs one task at
a time, so a method body is atomic with respect to every other coroutine. That
is what makes :meth:`SessionEventBus.subscribe` safe: no event can be published
between building the snapshot and registering the queue (design 3.3.4, G-14).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Final

from app.agents.workflow_builder.events import BuilderEvent, Snapshot
from app.core.config import settings

__all__ = ["SessionEventBus", "SessionQueue"]

logger = logging.getLogger(__name__)

#: A client queue. ``None`` tells the reader to close the stream.
type SessionQueue = asyncio.Queue[BuilderEvent | None]

_CLOSE_SLOTS: Final = 2  # room for the final event and the ``None`` sentinel


class SessionEventBus:
    """Per-session fan-out with bounded client queues and eviction on overflow."""

    def __init__(self, queue_maxsize: int | None = None) -> None:
        """Create an empty bus.

        Args:
            queue_maxsize: Size of each client queue. ``None`` reads
                ``settings.SSE_SUBSCRIBER_QUEUE_MAXSIZE`` at subscribe time;
                ``0`` means unbounded.
        """
        self._queue_maxsize = queue_maxsize
        self._subs: dict[str, list[SessionQueue]] = {}

    def subscribe(
        self, session_id: str, snapshot_fn: Callable[[], Snapshot]
    ) -> tuple[SessionQueue, Snapshot]:
        """Register a client queue and build its snapshot in one synchronous block.

        Args:
            session_id: The Session the client watches.
            snapshot_fn: Builds the current ``Snapshot``. It must not await,
                which a plain callable guarantees.

        Returns:
            The client's queue and the snapshot. Every event published after
            this call reaches the queue; none published before it does.

        Raises:
            Exception: Anything ``snapshot_fn`` raises. The queue is not
                registered in that case.
        """
        maxsize = (
            settings.SSE_SUBSCRIBER_QUEUE_MAXSIZE
            if self._queue_maxsize is None
            else self._queue_maxsize
        )
        snapshot = snapshot_fn()
        queue: SessionQueue = asyncio.Queue(maxsize=maxsize)
        self._subs.setdefault(session_id, []).append(queue)
        return queue, snapshot

    def unsubscribe(self, session_id: str, q: SessionQueue) -> None:
        """Remove a client queue. Unknown sessions and queues are ignored."""
        queues = self._subs.get(session_id)
        if queues is None:
            return
        try:
            queues.remove(q)
        except ValueError:
            return
        if not queues:
            del self._subs[session_id]

    def publish(self, session_id: str, event: BuilderEvent) -> None:
        """Put ``event`` on every queue of the Session without blocking.

        A queue that is full is evicted (H-09). Subscribers see events in call
        order, so the caller must assign ``seq`` before publishing (Req 40.5).
        """
        for queue in list(self._subs.get(session_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._evict(session_id, queue)

    def close_session(self, session_id: str, final: BuilderEvent | None) -> None:
        """Send ``final`` (if any) and then ``None`` to every client, and forget them.

        Used for ``session_deleted``. A queue without room drops its oldest
        events to make space, because the stream is closing and a reconnecting
        client takes a fresh snapshot anyway.
        """
        for queue in self._subs.pop(session_id, []):
            _close_queue(queue, final)

    def close_all(self) -> None:
        """Close every Session's clients with no final event (shutdown)."""
        for session_id in list(self._subs):
            self.close_session(session_id, None)

    def subscriber_count(self, session_id: str) -> int:
        """Return how many clients are registered for the Session."""
        return len(self._subs.get(session_id, ()))

    def _evict(self, session_id: str, queue: SessionQueue) -> None:
        """Remove a subscriber whose queue is full and give it the close sentinel."""
        logger.warning(
            "Builder subscriber evicted: session=%s queue_maxsize=%s "
            "reason=queue_full_on_publish",
            session_id,
            queue.maxsize,
        )
        self.unsubscribe(session_id, queue)
        _close_queue(queue, None)


def _close_queue(queue: SessionQueue, final: BuilderEvent | None) -> None:
    """Make room, then put ``final`` (if any) and the ``None`` sentinel on ``queue``."""
    needed = _CLOSE_SLOTS if final is not None else 1
    while (
        queue.maxsize and queue.maxsize - queue.qsize() < needed and not queue.empty()
    ):
        queue.get_nowait()
    if final is not None and (not queue.maxsize or queue.maxsize >= _CLOSE_SLOTS):
        queue.put_nowait(final)
    queue.put_nowait(None)

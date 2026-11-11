"""Session_Stream: ``GET /api/workflow-builder/sessions/{id}/events`` (design 3.3).

The per-session SSE down-channel of the AI Workflow Builder. It follows
``run_stream.stream_run_events`` with three differences:

* **Snapshot, not replay.** Text and thinking deltas are not stored (Q-28), so a
  reconnect cannot replay. The first frame is a ``snapshot`` and every later frame
  comes from the in-process :class:`~app.api.workflow_builder.bus.SessionEventBus`.
  The snapshot is built and the queue registered in one synchronous block
  (G-14), so no event is lost or repeated between them.
* **No ``id:`` line.** Frames carry only a ``data:`` line holding
  ``{"type": ..., "data": {...}}`` (``run_stream._sse_body``).
* **The stream stays open between turns.** ``turn_completed`` does not end it. It
  ends on ``session_deleted``, on ``session_revoked``, on a ``None`` sentinel from
  the bus (eviction, shutdown) or when the client disconnects.

Authorisation key: ``user_id``. A missing and a foreign session both answer 404
``session_not_found`` (Req 2.7). The request-scoped database session is used only
for that lookup. The generator opens its own short-lived sessions, because
FastAPI closes the request session before a streaming body runs (BUG-004).

Revocation (design 3.3.6, G-15). The generator waits on its queue only until ``SSE_REVOCATION_CHECK_INTERVAL_SECONDS``
after the last check (or after the stream opened), and calls ``_run_revocation_check``
at that deadline, after every ``SSE_REVOCATION_CHECK_EVERY_N_EVENTS`` events, and after
an event that arrives once the interval has already passed. A
reason (the check fails closed) sends ``session_revoked`` and closes the stream.
The revoked user's running turn is not touched; it keeps running and its result is
stored.

Logs carry ids and counts only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as DbSession
from sse_starlette import EventSourceResponse

from app.agents.workflow_builder.events import (
    BuilderEvent,
    SessionDeleted,
    SessionRevoked,
    Snapshot,
    to_wire,
)
from app.api.run_commands import _reject  # noqa: PLC2701 - the shared error shape
from app.api.run_stream import (  # noqa: PLC2701 - reused on purpose (design 3.3.1, 3.3.6)
    _run_revocation_check,
    _sse_body,
)
from app.api.workflow_builder.admission import BuilderAccess, require_builder_access
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.store import BuilderStore
from app.api.workflow_builder.turns import (
    SnapshotStore,
    build_snapshot,
    get_event_bus,
)
from app.core.config import settings
from app.core.dependencies import bearer_scheme
from app.models.database import SessionLocal, get_db

__all__ = [
    "RevocationCheck",
    "iter_session_frames",
    "router",
    "stream_session_events",
]

logger = logging.getLogger("app.api.workflow_builder.stream")

router = APIRouter(prefix="/api/workflow-builder", tags=["workflow-builder-stream"])

#: Returns a reason when the caller's credential is no longer valid, else ``None``.
type RevocationCheck = Callable[[], Awaitable[str | None]]

#: Events that end the stream after they are sent.
_CLOSING_EVENTS = (SessionDeleted, SessionRevoked)


@contextmanager
def _open_snapshot_store() -> Iterator[SnapshotStore]:
    """Open a Session_Store on its own database session and close it afterwards."""
    db = SessionLocal()
    try:
        yield BuilderStore(db)
    finally:
        db.close()


def _frame(event: BuilderEvent) -> dict[str, str]:
    """Render one event as an ``sse-starlette`` frame: a ``data:`` line, no ``id:``."""
    event_type, data = to_wire(event)
    return {"data": _sse_body(event_type, data)}


def _utcnow() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


async def iter_session_frames(  # noqa: PLR0913 - every collaborator is injected for tests
    *,
    session_id: str,
    bus: SessionEventBus,
    snapshot_fn: Callable[[], Snapshot],
    revocation_check: RevocationCheck,
    now: Callable[[], datetime] = _utcnow,
    clock: Callable[[], float] = time.monotonic,
) -> AsyncIterator[dict[str, str]]:
    """Yield the SSE frames of one attached client.

    Order: the snapshot, then the live events of the Session until a closing
    event, the ``None`` sentinel or cancellation (client disconnect).

    Args:
        session_id: The Session the client watches.
        bus: The fan-out bus the client subscribes to.
        snapshot_fn: Builds the snapshot. It must not await (G-14).
        revocation_check: Returns a reason when the credential is no longer valid.
        now: Wall-clock time for the ``session_revoked`` timestamp.
        clock: Monotonic seconds for the revocation timing, so a wall-clock step
            cannot stretch a wait past the interval.
    """
    queue, snapshot = bus.subscribe(session_id, snapshot_fn)
    try:
        yield _frame(snapshot)
        interval = settings.SSE_REVOCATION_CHECK_INTERVAL_SECONDS
        every_n_events = settings.SSE_REVOCATION_CHECK_EVERY_N_EVENTS
        events_since_check = 0
        last_check = clock()
        while True:
            # The idle wait ends at the deadline counted from the last check, not from the last event.
            remaining = max(0.0, interval - (clock() - last_check))
            try:
                event = await asyncio.wait_for(queue.get(), timeout=remaining)
            except TimeoutError:
                last_check = clock()
                reason = await revocation_check()
                if reason:
                    yield _revoked_frame(session_id, reason, now())
                    return
                continue

            if event is None:
                return
            yield _frame(event)
            if isinstance(event, _CLOSING_EVENTS):
                return

            events_since_check += 1
            count_due = events_since_check >= every_n_events
            if count_due:
                events_since_check = 0
            if count_due or clock() - last_check >= interval:
                last_check = clock()
                reason = await revocation_check()
                if reason:
                    yield _revoked_frame(session_id, reason, now())
                    return
    finally:
        bus.unsubscribe(session_id, queue)


def _revoked_frame(session_id: str, reason: str, ts: datetime) -> dict[str, str]:
    """Render the terminal ``session_revoked`` frame."""
    return _frame(SessionRevoked(ts=ts, session_id=session_id, reason=reason))


def _owner_lookup(db: DbSession, user_id: str, session_id: str) -> bool:
    """Return True when the caller owns the Session. Blocking; runs in a worker thread."""
    return BuilderStore(db).get_session(user_id, session_id) is not None


@router.get("/sessions/{session_id}/events")
async def stream_session_events(
    session_id: str,
    access: BuilderAccess = Depends(require_builder_access),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: DbSession = Depends(get_db),
) -> EventSourceResponse:
    """Stream a Session's events as SSE (Req 2.7, 21.4, 38, 40).

    ``require_builder_access`` authenticates the caller and runs the
    entitlement and readiness checks. The raw credential is captured here so the
    periodic re-check can run the full verifier. A missing or foreign Session is
    404, never 403.
    """
    user_id = str(access.user.id)
    if not await asyncio.to_thread(_owner_lookup, db, user_id, session_id):
        raise _reject(
            "session_not_found",
            "Conversation not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    token = credentials.credentials

    async def revocation_check() -> str | None:
        return await _run_revocation_check(
            token=token, user_id=user_id, run_id=session_id
        )

    def snapshot_fn() -> Snapshot:
        with _open_snapshot_store() as store:
            return build_snapshot(session_id, user_id=user_id, store=store)

    async def generator() -> AsyncIterator[dict[str, str]]:
        logger.info(
            "evt=builder_sse.open session_id=%s user_id=%s", session_id, user_id
        )
        try:
            async for frame in iter_session_frames(
                session_id=session_id,
                bus=get_event_bus(),
                snapshot_fn=snapshot_fn,
                revocation_check=revocation_check,
            ):
                yield frame
        finally:
            logger.info(
                "evt=builder_sse.close session_id=%s user_id=%s", session_id, user_id
            )

    return EventSourceResponse(
        generator(),
        ping=settings.SSE_KEEPALIVE_PING_SECONDS,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )

"""WebSocket endpoint streaming /flowin-handoff pipeline events.

Routing: ``/ws/handoff/{token}``. The browser opens this WS right after
loading ``/handoff/<token>``. Auth uses the same ``Sec-WebSocket-Protocol``
subprotocol pattern as the chat WS (``bearer.<jwt>, flowin.v1``) so the
JWT never lands in nginx access logs.

Event distribution is in-memory and single-process. That matches our
single-EC2 deployment (one backend container, one process per worker).
If we ever shard backend, swap the ``_SUBSCRIBERS`` dict for Redis pub-
sub — the only callers are :func:`dispatch_event` (pipeline producer)
and the WS handler (consumer).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.websocket import _authenticate_token, _get_db
from app.models.handoff import HandoffSession

logger = logging.getLogger("app.api.websocket_handoff")

router = APIRouter()


# token → list of queues. Each queue belongs to a single WS connection.
# ``defaultdict(list)`` keeps the producer side simple; the WS handler
# is responsible for adding and removing its own queue.
_SUBSCRIBERS: dict[str, list[asyncio.Queue]] = defaultdict(list)
_SUBSCRIBERS_LOCK = asyncio.Lock()


async def dispatch_event(token: str, event: dict[str, Any]) -> None:
    """Fan-out an event to every WS subscribed to ``token``.

    A queue with no consumer is fine — the WS handler drains and dies.
    A queue with a slow consumer just buffers; we never drop events.
    """
    async with _SUBSCRIBERS_LOCK:
        queues = list(_SUBSCRIBERS.get(token, ()))
    for q in queues:
        await q.put(event)


async def _subscribe(token: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    async with _SUBSCRIBERS_LOCK:
        _SUBSCRIBERS[token].append(q)
    return q


async def _unsubscribe(token: str, q: asyncio.Queue) -> None:
    async with _SUBSCRIBERS_LOCK:
        if token in _SUBSCRIBERS:
            try:
                _SUBSCRIBERS[token].remove(q)
            except ValueError:
                pass
            if not _SUBSCRIBERS[token]:
                _SUBSCRIBERS.pop(token, None)


def _extract_jwt(websocket: WebSocket) -> str | None:
    """Pull the JWT out of the ``Sec-WebSocket-Protocol`` header."""
    raw = websocket.headers.get("sec-websocket-protocol") or ""
    for entry in (s.strip() for s in raw.split(",")):
        if entry.startswith("bearer."):
            return entry[len("bearer.") :]
    return None


@router.websocket("/ws/handoff/{token}")
async def websocket_handoff(websocket: WebSocket, token: str) -> None:
    jwt = _extract_jwt(websocket)
    if not jwt:
        await websocket.close(code=4001, reason="missing bearer subprotocol")
        return

    db: Session = _get_db()
    try:
        user = _authenticate_token(jwt, db)
        if user is None:
            await websocket.close(code=4001, reason="invalid token")
            return
        sess = db.query(HandoffSession).filter(HandoffSession.token == token).first()
        if sess is None or sess.issuer_user_id != user.id:
            await websocket.close(code=4004, reason="handoff not found")
            return
    finally:
        db.close()

    await websocket.accept(subprotocol="flowin.v1")

    queue = await _subscribe(token)
    try:
        # Send an immediate "subscribed" event so the frontend knows the
        # channel is live before the first pipeline event arrives.
        await websocket.send_text(json.dumps({"type": "handoff_ready", "chunk": None, "section": None, "data": {"token": token}}))

        while True:
            event = await queue.get()
            await websocket.send_text(json.dumps(event, default=str))
            if event.get("type") in ("pipeline_complete", "handoff_error"):
                # Pipeline is done. Drain any final events that may already be
                # queued, then close politely. We rely on the queue being
                # bounded by pipeline pacing, so a short timeout is enough.
                drain_deadline = asyncio.get_event_loop().time() + 0.5
                while True:
                    remaining = drain_deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        late = await asyncio.wait_for(queue.get(), timeout=remaining)
                    except asyncio.TimeoutError:
                        break
                    await websocket.send_text(json.dumps(late, default=str))
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Handoff WS handler crashed for token=%s", token)
    finally:
        await _unsubscribe(token, queue)
        try:
            await websocket.close()
        except Exception:
            pass

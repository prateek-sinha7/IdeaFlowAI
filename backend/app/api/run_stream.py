"""Per-run SSE down-channel — ``GET /api/runs/{id}/events/stream`` (CHAT-07, D-01/D-13).

The browser-native, one-way event firehose half of the ``/ws/chat`` → HTTP+SSE
transport cutover. It streams a run's events as ``text/event-stream``, stamping the
durable per-run ``seq`` onto every frame's ``id:`` line so a dropped connection
resumes from the browser-native ``Last-Event-ID`` request header — no client cursor
bookkeeping, no second envelope.

Wire parity (CHAT-07). The SSE frame body re-implements the 29-01 projection contract
(``tests/agents/characterization/_sse_projection.py``): each frame carries an ``id:``
line (``seq``) + a single-line ``data:`` JSON body shaped ``{"type", "data"}`` — so the
frames the browser receives are, volatile-stripped, byte/event-identical to the
recorded ``/ws/chat`` drainer frames. The projection module ANTICIPATES this
re-implementation ("29-02 will re-implement the same rendering inside the endpoint
against this contract") precisely so production code does NOT import the test-support
module; ``tests/unit/test_sse_stream.py`` binds the endpoint's frames to the REAL
projection's ``assert_wire_parity`` to guard against accidental divergence.

Handshake + gate re-arm on attach:
  * After replaying the durable tail past the client cursor, the stream emits
    ``stream_attached {live, replayed_through_seq}`` — the new-transport replacement
    for the legacy ``pipeline_reconnected`` ack (``websocket.py:1157``);
    ``replayed_through_seq`` mirrors the last replayed ``seq`` (== the legacy
    ``pipeline_reconnected.replayed_through_seq`` value).
  * D-14g: when the run is paused at a still-open human review gate (a durable
    ``review_gate_ready`` with no following ``review_gate_approved``/terminal), the
    attach path RE-EMITS ``review_gate_ready`` — re-armed purely from the owner-scoped
    persisted events, so a reload during a paused gate resumes correctly (closes the
    P23/F4 hole). The re-arm reads state; it NEVER re-runs an agent or mutates the
    artifact graph. This makes reattach server-derived (ND-9) — no sessionStorage trust.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models.workflow import WorkflowRun

logger = logging.getLogger("app.api.run_stream")

# Read-only import of the EXISTING per-run live-queue registry (LOCK-B — websocket.py
# is NOT modified and NO new symbol is added there). ``_get_or_create_queue`` returns
# the same ``asyncio.Queue`` the WS drainer feeds; membership in ``_PIPELINE_QUEUES``
# is the liveness signal (a registered queue == a live/attached run).
from app.api.run_engine import _PIPELINE_QUEUES, _get_or_create_queue

router = APIRouter(prefix="/api/runs", tags=["runs-stream"])

# Terminal / gate-resolution event types: a ``review_gate_ready`` FOLLOWED by any of
# these in the durable log means the gate is no longer open (do NOT re-arm, D-14g).
# RESUME-17 / INV-12: this is the ONE shared review-resolution frozenset (byte-identical
# to the former inline set), now sourced from ``agents.capabilities.gate_pendency`` so
# the SSE re-arm and the restart re-arm derive open gates from the SAME vocabulary.
from agents.capabilities.gate_pendency import (  # noqa: E402
    REVIEW_GATE_READY,
    REVIEW_RESOLUTIONS as _GATE_RESOLUTION_TYPES,
)

# BUG-016: the live-drain STREAM terminals — the subset that actually closes the
# open SSE stream. ``review_gate_approved`` is a gate RESUMPTION, not a stream
# terminal: approve makes the engine keep building on the SAME per-run queue
# (post-approve ``generating`` frames follow), so closing the stream on it forces
# a needless reconnect + full replay. Only pipeline_complete / pipeline_cancelled /
# pipeline_failed / budget_aborted / error truly end the run's event stream. The
# broader ``_GATE_RESOLUTION_TYPES`` (which DOES include approve) still drives the
# D-14g durable gate re-arm derivation below — that is a separate concern.
_STREAM_TERMINAL_TYPES = _GATE_RESOLUTION_TYPES - frozenset({"review_gate_approved"})

# D-14g gate-re-arm vocabulary: the event types whose LAST occurrence decides whether a
# review gate is still open. DERIVED from gate_pendency (RESUME-17 / INV-12: that module
# is the ONE home of the durable gate vocabulary -- never restate its members here),
# mirroring how _STREAM_TERMINAL_TYPES is derived just above. NOTE the two sets are
# deliberately different: review_gate_approved IS a re-arm resolution but is NOT a stream
# terminal (BUG-016) -- do not conflate them.
_GATE_REARM_TYPES = frozenset({REVIEW_GATE_READY}) | _GATE_RESOLUTION_TYPES


# ---------------------------------------------------------------------------
# SSE frame rendering — the 29-01 projection contract, re-implemented in-line.
# ---------------------------------------------------------------------------
def _sse_body(event_type: str, payload: Any) -> str:
    """The single-line JSON body on a frame's ``data:`` line: ``{"type", "data"}``.

    Shaped 1:1 with the WS frame's ``{type, data}`` core so the volatile-stripped
    wire-parity compare holds by construction (``_sse_projection._sse_body``).
    """
    return json.dumps(
        {"type": event_type, "data": payload if payload is not None else {}},
        sort_keys=True,
        ensure_ascii=False,
    )


def _sse_frame(seq: int, event_type: str, payload: Any) -> dict:
    """Render ONE event as a ``sse-starlette`` frame dict.

    ``id`` becomes the SSE ``id:`` line (the browser ``Last-Event-ID`` resume cursor);
    ``data`` is the single-line ``{type, data}`` JSON body. Matches
    ``_sse_projection.run_event_to_sse_frame`` (``id: {seq}\\ndata: {body}\\n\\n``).
    """
    return {"id": str(seq), "data": _sse_body(event_type, payload)}


# ---------------------------------------------------------------------------
# Gate re-arm derivation (D-14g) — bounded, owner-scoped, read-only.
# ---------------------------------------------------------------------------
async def _dangling_review_gate(store: Any, run_id: str) -> Optional[Any]:
    """Return the last still-OPEN ``review_gate_ready`` row, or ``None``.

    A gate is open iff its ``review_gate_ready`` is NOT followed (by ``seq``) by any
    gate-resolution event. Derived ENTIRELY from the owner-scoped durable ``run_events``
    (ND-9: server-derived, no client-state trust). Reads only — never mutates.

    This used to materialise the ENTIRE log (``read_events(run_id, after_seq=0)``) and scan
    it in Python for one row -- ~2x the log retained per live stream, on every attach.
    ``ScopedStore.last_event_of_types`` answers the same question with ONE row.

    Equivalence (proven by a 1,004-case differential over the frozen pre-fix oracle, see
    ``tests/unit/test_sse_stream.py::TestGateRearmEquivalence``): let
    ``V = {review_gate_ready} | REVIEW_RESOLUTIONS``. If the max-``seq`` row in ``V`` is a
    ``review_gate_ready`` then nothing in ``V`` follows it, so no resolution does, so it is
    the last still-open ready. If it is a resolution, that resolution follows EVERY ready,
    so the old loop's ``last_ready`` is ``None`` at exit. If ``V`` is empty both return
    ``None``. The branches are mutually exclusive because ``review_gate_ready`` is not a
    member of ``REVIEW_RESOLUTIONS`` (``gate_pendency.py:53-62``). A ``seq`` tie -- the only
    place stable ``sorted()`` and ``ORDER BY ... LIMIT 1`` could differ -- is unreachable:
    ``uq_run_events_scope_seq`` is UNIQUE on exactly the scope ``_scope_owner_ws`` filters.
    """
    # after_seq defaults to 0, i.e. `seq > 0` -- byte-for-byte the filter the deleted
    # `read_events(run_id, after_seq=0)` applied, so a legacy `seq <= 0` row stays
    # invisible here exactly as it was before.
    row = await store.last_event_of_types(run_id, _GATE_REARM_TYPES)
    return row if row is not None and row.type == REVIEW_GATE_READY else None


# ---------------------------------------------------------------------------
# The SSE event stream — dependency-injected so it is directly unit-testable.
# ---------------------------------------------------------------------------
async def _iter_sse_frames(
    *,
    run_id: str,
    store: Any,
    after_seq: int,
    live_queue: Any = None,
    request: Optional[Request] = None,
) -> AsyncIterator[dict]:
    """Yield the SSE frame dicts for one attached client.

    Order: durable replay (``seq > after_seq``) → ``stream_attached`` handshake →
    D-14g gate re-arm (if paused) → live queue drain (until the ``None`` sentinel or
    client disconnect). ``live_queue is None`` means the run has no live task, so the
    replayed durable tail + the handshake are the complete response.
    """
    # 1. Durable replay — the run_events tail past the client cursor, ascending seq.
    rows = await store.read_events(run_id, after_seq=after_seq)
    replayed_through_seq = after_seq
    for r in rows:
        yield _sse_frame(r.seq, r.type, r.payload_json)
        replayed_through_seq = r.seq
    # Release the replay list (and the loop variable's last row) NOW. This generator then
    # parks in `await live_queue.get()` for the run's ENTIRE duration, so anything still
    # bound here is retained per live stream, not per attach. Nothing below reads either
    # name. Measured: `rows = ()` alone frees 399/400 ORM rows -- `r` pins the last one,
    # which for an `agent_input` row is ~214 KB.
    rows = ()
    r = None

    # 2. stream_attached handshake — the new-transport replacement for the legacy
    #    pipeline_reconnected ack. `live` reflects whether a live queue is attached;
    #    `replayed_through_seq` mirrors the last replayed seq (legacy semantics). Its
    #    id: line carries the same cursor so a resume from it re-reads nothing new.
    is_live = live_queue is not None
    yield _sse_frame(
        replayed_through_seq,
        "stream_attached",
        {
            "pipeline_run_id": run_id,
            "live": is_live,
            "replayed_through_seq": replayed_through_seq,
        },
    )

    # 3. D-14g gate re-arm — a reload during a paused human gate re-emits the durable
    #    review_gate_ready so the FE re-opens the gate. Read-only, owner-scoped, BOUNDED
    #    (one row). Never re-runs an agent / mutates the artifact graph.
    #
    #    CR-01: re-emit ONLY when the step-1 durable replay did NOT already deliver the
    #    gate frame. Replay above yields rows with ``seq > after_seq``, so when the open
    #    gate's ``seq`` is > after_seq it was ALREADY replayed -- re-emitting here would
    #    DOUBLE it. The re-arm is needed ONLY when the client cursor is at or past the gate
    #    (``dangling.seq <= after_seq``) -- exactly the case the replay filter excluded.
    #
    #    ``after_seq == 0`` therefore CANNOT re-arm: the derivation reads with `seq > 0`
    #    (same filter the deleted full-log read used), so ``dangling.seq >= 1`` always and
    #    ``dangling.seq <= 0`` is unreachable. Skipping the query on a fresh attach is a
    #    provable no-op -- and a fresh attach (no Last-Event-ID) is the common case AND the
    #    attach-churn amplification vector, so this is where the saving matters most.
    if after_seq > 0:
        dangling = await _dangling_review_gate(store, run_id)
        if dangling is not None and dangling.seq <= after_seq:
            yield _sse_frame(dangling.seq, "review_gate_ready", dangling.payload_json)

    # 4. Live drain — forward new events off the shared per-run queue until the None
    #    sentinel (pipeline finished) or the client disconnects. sse-starlette's built-in
    #    comment-ping (SSE_KEEPALIVE_PING_SECONDS) keeps idle proxies from buffering.
    if live_queue is None:
        return
    try:
        while True:
            if request is not None and await request.is_disconnected():
                return
            event = await live_queue.get()
            if event is None:  # sentinel: pipeline finished
                return
            data = event.get("data", {}) if isinstance(event, dict) else {}
            seq = data.get("seq", replayed_through_seq) if isinstance(data, dict) else replayed_through_seq
            yield _sse_frame(seq, event.get("type", "message"), data)
            replayed_through_seq = seq
            if event.get("type") in _STREAM_TERMINAL_TYPES:
                return
    finally:
        # KAN-134: unsubscribe from the fan-out bus when the stream closes
        # (client disconnect, terminal event, or request error).
        await _unsubscribe(run_id, live_queue)


@router.get("/{workflow_id}/events/stream")
async def stream_run_events(
    workflow_id: str,
    request: Request,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream a run's events as SSE, resumable via ``Last-Event-ID`` (CHAT-07, D-13).

    Unconditional — the sole run event transport after ``/ws/chat`` was retired
    (44-07). Two-layer owner check identical to ``runs.py::get_run_events``: the
    ``user_id`` filter → 404, then the default-deny ``ScopedStore.get_run`` → 404
    (IDOR → 404, never 403). The resolved cursor is the ``Last-Event-ID`` header
    (browser-native) or 0 for a fresh attach; a non-int header degrades to a full
    replay (0) rather than erroring.
    """
    # Layer 1: owner-scoped ORM filter (cross-owner / missing → 404, never 403).
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    from agents.authz import ScopedStore

    store = ScopedStore(
        owner_id=current_user.id,
        workspace_id=workflow_run.workspace_id,
        session=db,
    )
    # Layer 2: default-deny re-resolve so the ownership boundary lives in ONE place.
    if await store.get_run(workflow_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    # BUG-004: the request-session store above is used ONLY for the two pre-stream owner
    # checks (Layer 1 ORM filter + Layer 2 get_run), which run in request scope and return
    # normally. It must NOT back the streaming generator: FastAPI >= 0.106 tears the
    # get_db yield-dependency down (db.close()) BEFORE the streaming body runs, so a
    # read_events INSIDE _iter_sse_frames would re-acquire a FRESH pool connection on the
    # closed session with owned=False (authz.py:95-99) and NEVER release it (authz.py
    # :328-330 only closes owned sessions) — one leaked connection per live SSE stream.
    # Build a SEPARATE session-less store for the generator so each read_events opens+closes
    # its own SessionLocal (owned=True), mirroring the safe post_message idiom
    # (run_commands.py:758). Only the session-acquisition mode changes — frames/replay/
    # handshake/gate re-arm stay byte/event-identical (INV-3 parity).
    stream_store = ScopedStore(
        owner_id=current_user.id,
        workspace_id=workflow_run.workspace_id,
    )

    # Resolve the resume cursor from the browser-native Last-Event-ID header. A missing
    # / non-int header is a full replay (0) — never a 422 (the browser controls this
    # header on auto-reconnect; a hostile value only bounds the caller's OWN replay,
    # T-29-02-2). The int cursor flows into the parameterized ScopedStore filter.
    after_seq = 0
    if last_event_id is not None:
        try:
            after_seq = max(0, int(last_event_id))
        except (TypeError, ValueError):
            after_seq = 0

    # KAN-134: Subscribe to the per-run fan-out bus if the run is live.
    # A run has a live queue iff it has a LIVE driver task. After A4, stale queue/task
    # entries from failed drivers are self-healed, so _is_run_live() returns False and
    # the stream is a durable replay + handshake (the complete response, clean close).
    # The subscriber is unsubscribed in the finally block of _iter_sse_frames.
    from app.core.config import settings

    live_queue = None
    if _is_run_live(workflow_id):
        live_queue = await _subscribe(
            workflow_id,
            queue_maxsize=settings.SSE_SUBSCRIBER_QUEUE_MAXSIZE,
        )

    # D11 (KAN-139): log every stream open/close so A1's 429 storm, A2's event
    # theft, and D7's pool drops are diagnosable from the application layer.
    _close_reason: list[str] = ["client_disconnect"]  # mutable to let the generator update it

    async def _iter_with_logging() -> AsyncIterator[dict]:
        nonlocal _close_reason
        try:
            async for frame in _iter_sse_frames(
                run_id=workflow_id,
                store=stream_store,
                after_seq=after_seq,
                live_queue=live_queue,
                request=request,
            ):
                # Detect close reason from the frame type as it flows through.
                frame_type = frame.get("data", "")
                if isinstance(frame_type, str):
                    try:
                        import json as _json
                        parsed = _json.loads(frame_type)
                        ft = parsed.get("type", "")
                    except Exception:
                        ft = ""
                    if ft == "stream_attached":
                        pass  # handshake — not a close
                    elif ft in _STREAM_TERMINAL_TYPES:
                        _close_reason[0] = "terminal_event"
                    elif ft == "sentinel":
                        _close_reason[0] = "sentinel"
                yield frame
            # If we fell through without a terminal event the queue closed via sentinel.
            if _close_reason[0] == "client_disconnect":
                _close_reason[0] = "sentinel"
        except Exception:
            _close_reason[0] = "error"
            raise

    logger.info(
        "evt=sse.open run_id=%s user_id=%s after_seq=%s live=%s",
        workflow_id,
        current_user.id,
        after_seq,
        live_queue is not None,
    )

    from sse_starlette import EventSourceResponse

    async def _generator() -> AsyncIterator[dict]:
        try:
            async for frame in _iter_with_logging():
                yield frame
        finally:
            logger.info(
                "evt=sse.close run_id=%s user_id=%s reason=%s",
                workflow_id,
                current_user.id,
                _close_reason[0],
            )

    return EventSourceResponse(
        _generator(),
        ping=settings.SSE_KEEPALIVE_PING_SECONDS,
        # D-14h: never let a proxy buffer/gzip an event-stream (X-Accel-Buffering: no
        # for nginx; Cache-Control: no-cache; ops MUST also set proxy_buffering off).
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )

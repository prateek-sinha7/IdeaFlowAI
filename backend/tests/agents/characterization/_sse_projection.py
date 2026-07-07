"""Wire-parity projection contract — the pure ``run_events``→SSE frame projection
that the CHAT-07 transport cutover binds against (Phase 29, plan 29-01).

This module is the SINGLE SOURCE OF TRUTH for how a run's durable ``run_events``
rows project to the ``/api/runs/{id}/stream`` SSE frame sequence. The SSE stream
endpoint (29-02) mounts THIS projection into the live route, so wire parity holds
*by construction*: the SSE frames the browser receives are, volatile-stripped,
byte/event-identical to the ``/ws/chat`` WebSocket drainer frames the current
transport emits.

Why this is a test-support module (not production):
  * Under LOCK-B the SSE transport is built ADDITIVELY — nothing here touches
    ``app/api/websocket.py`` / ``websocket_handoff.py`` / ``useWebSocket.ts``.
  * The projection is dependency-free of ``app.*`` and the ``agents.*`` kernel so
    import-linter stays 4 kept / 0 broken; it depends ONLY on the characterization
    normalizer (the shared ``_VOLATILE_STRIP_KEYS`` + ``_canonical_order``). 29-02
    will re-implement the same rendering inside the endpoint against this contract.

Wire shapes (grounded in evidence 03 §1 + ``app/api/websocket.py``):
  * WS drainer frame (live):    ``{"type", "chunk": None, "section": <pipeline>, "data": <event.data>}``
    (``websocket.py:2325-2328``) — reproduced by :func:`ws_frame_from_engine_event`.
  * WS reconnect replay frame:  ``{"type": r.type, "chunk": None, "section": …, "data": r.payload_json}``
    (``websocket.py:1144-1146``) — the run_events→frame shape the SSE stream mirrors.
  * SSE frame (the 29-02 emit):  an ``id: {seq}`` line (browser ``Last-Event-ID``
    resume cursor) + a ``data: {json}`` line + a blank-line terminator, where the
    JSON body is the row's ``{type, data}`` — rendered by :func:`run_event_to_sse_frame`.

The engine stamps a monotonic per-run ``seq`` + a uuid ``event_id`` into every
event's ``data`` at the single ``execute()`` emit boundary; the durable
``run_events.payload_json`` is exactly that ``data`` dict. So a run_events row and
the WS frame for the same event carry the SAME payload — parity is a real,
non-vacuous property proven over the 5 golden pipelines by ``test_wire_parity.py``.

Public surface:
    ws_frame_from_engine_event(event, section) — wrap an engine ``{type,data}`` event
        into the current WS drainer 4-key frame (for recording the goldens).
    run_events_from_engine_events(events)       — derive the durable ``run_events`` rows
        (``{seq, type, payload}``) from a captured engine event stream.
    run_event_to_sse_frame(row)                 — render ONE row as the SSE text frame.
    project_events(rows)                        — yield SSE frames for all rows, ascending seq.
    assert_wire_parity(ws_frames, run_events)   — normalize both sides through the shared
        ``_VOLATILE_STRIP_KEYS`` + ``_canonical_order`` and raise on ANY residual drift.
"""

from __future__ import annotations

import json
from typing import Iterator

# Import the SHARED normalizer — NEVER copy the strip list (the single source of
# truth is characterization/_normalize.py; a new volatile key added there flows
# through here automatically). This is the only dependency; no app.* / no kernel.
from tests.agents.characterization._normalize import (
    _VOLATILE_STRIP_KEYS,
    _canonical_order,
    _normalize,
)

__all__ = [
    "ws_frame_from_engine_event",
    "run_events_from_engine_events",
    "run_event_to_sse_frame",
    "project_events",
    "assert_wire_parity",
]


# ---------------------------------------------------------------------------
# WS drainer frame shape — reproduce the live wrapping so a recorded engine
# event can be compared to a projected SSE frame after normalization.
# ---------------------------------------------------------------------------
def ws_frame_from_engine_event(event: dict, section: str) -> dict:
    """Wrap an engine ``{type, data}`` event into the current WS drainer frame.

    Reproduces the live drainer wrapping verbatim
    (``app/api/websocket.py:2325-2328``): ``chunk`` is always ``None`` on the
    drained path and ``section`` is the run's ``pipeline_type``. The engine event's
    ``data`` is forwarded as-is (the drainer does ``event.get("data", {})``).
    """
    return {
        "type": event["type"],
        "chunk": None,
        "section": section,
        "data": event.get("data", {}),
    }


# ---------------------------------------------------------------------------
# Durable run_events rows — the projection's INPUT.
# ---------------------------------------------------------------------------
def run_events_from_engine_events(events: list[dict]) -> list[dict]:
    """Derive the durable ``run_events`` rows from a captured engine event stream.

    Each engine event carries the run-stamped ``seq`` inside its ``data`` (the
    single ``execute()`` emit boundary stamps it; the durable ``run_events`` row's
    ``payload_json`` IS that ``data`` dict — see evidence 03 §1). We mirror the row
    shape the ``ScopedStore.append_event`` sink persists: ``{seq, type, payload}``.
    When an event carries no ``seq`` (defensive), fall back to its 1-based position.
    """
    rows: list[dict] = []
    for i, ev in enumerate(events):
        data = ev.get("data") or {}
        seq = data.get("seq", i + 1)
        rows.append({"seq": seq, "type": ev["type"], "payload": data})
    return rows


# ---------------------------------------------------------------------------
# The SSE projection — the exact shape the 29-02 endpoint emits.
# ---------------------------------------------------------------------------
def _sse_body(row: dict) -> dict:
    """The JSON body carried on a row's SSE ``data:`` line: the row's type+payload.

    Shaped ``{"type", "data"}`` so it aligns 1:1 with the WS frame's
    ``{"type", "data"}`` core for the volatile-stripped parity compare.
    """
    return {"type": row["type"], "data": row.get("payload", {})}


def run_event_to_sse_frame(row: dict) -> str:
    """Render ONE ``run_events`` row as the SSE text frame.

    Form (SSE wire spec): an ``id: {seq}`` line — the browser ``Last-Event-ID``
    resume cursor — then a single ``data: {json}`` line carrying the row's
    ``{type, data}`` body, then a blank-line terminator. The JSON is single-line
    (no embedded newlines) so the frame is a valid SSE event with exactly one
    ``data:`` field.
    """
    body = json.dumps(_sse_body(row), sort_keys=True, ensure_ascii=False)
    return f"id: {row['seq']}\ndata: {body}\n\n"


def project_events(rows: list[dict]) -> Iterator[str]:
    """Yield one SSE frame per ``run_events`` row, in ASCENDING ``seq`` order.

    The ``id:`` line of each frame carries that row's ``seq`` (the resume cursor);
    ordering by ``seq`` reproduces the durable emission order the SSE stream and the
    WS reconnect-replay tail both use.
    """
    for row in sorted(rows, key=lambda r: r["seq"]):
        yield run_event_to_sse_frame(row)


# ---------------------------------------------------------------------------
# Parity comparator — the binding gate's engine.
# ---------------------------------------------------------------------------
def _parse_sse_frame(frame: str) -> dict:
    """Parse an SSE frame string back to its ``{type, data}`` body.

    Reads the single ``data:`` line and JSON-decodes it. Raises AssertionError if
    the frame carries no ``data:`` line (a malformed projection must not pass
    silently — this keeps the comparator honest).
    """
    for line in frame.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise AssertionError(f"SSE frame carries no 'data:' line: {frame!r}")


def _frame_core(frame: dict) -> dict:
    """Reduce a WS drainer frame to its ``{type, data}`` parity core.

    ``chunk`` (always ``None`` on the drained path) and ``section`` (a constant
    transport-envelope field the SSE endpoint sets separately) are envelope
    concerns, not payload; parity is on the ``{type, data}`` the FE reducer reads.
    """
    return {"type": frame["type"], "data": frame.get("data", {})}


def assert_wire_parity(ws_frames: list[dict], run_events: list[dict]) -> None:
    """Assert the SSE projection of ``run_events`` == the WS frame sequence.

    Both sides are reduced to their ``{type, data}`` core and normalized through the
    SHARED ``_VOLATILE_STRIP_KEYS`` + ``_canonical_order`` (the order-canonical
    multiset framing from the characterization goldens — robust to the engine's
    nondeterministic tool_result/task_progress interleaving, yet failing on a
    dropped/added/changed frame). Raises ``AssertionError`` on ANY residual
    difference.

    Anti-vacuity: BOTH sides must be non-empty — an empty projection or an empty
    frame list cannot pass silently (T-29-01-1).
    """
    ws_core = [_frame_core(f) for f in ws_frames]
    projected_core = [_parse_sse_frame(frame) for frame in project_events(run_events)]

    assert ws_core, (
        "assert_wire_parity: the WS frame sequence is EMPTY — a vacuous gate would "
        "give false confidence in the transport cutover (T-29-01-1)."
    )
    assert projected_core, (
        "assert_wire_parity: the SSE projection is EMPTY — the run produced no "
        "run_events to project (vacuous pass guard, T-29-01-1)."
    )

    ws_norm = _canonical_order(_normalize(ws_core))
    projected_norm = _canonical_order(_normalize(projected_core))

    # Reference the shared strip list explicitly so a reviewer can see the contract
    # is single-sourced (and so a future copy-paste of the strip set fails review).
    assert "seq" in _VOLATILE_STRIP_KEYS, (
        "invariant: the shared _VOLATILE_STRIP_KEYS must strip 'seq' — the SSE 'id:' "
        "line carries the resume cursor, so 'seq' must not perturb the payload compare."
    )

    if ws_norm != projected_norm:
        ws_types = [f["type"] for f in ws_norm]
        proj_types = [f["type"] for f in projected_norm]
        raise AssertionError(
            "WIRE PARITY DRIFT: the run_events→SSE projection diverged from the "
            "recorded WS frame sequence (volatile-stripped, order-canonical).\n"
            f"  WS frame count={len(ws_norm)} types={ws_types}\n"
            f"  SSE projection count={len(projected_norm)} types={proj_types}\n"
            "This is the CHAT-07 binding gate: the SSE transport is NOT a faithful "
            "replacement of the /ws/chat drainer. If the change is intentional, "
            "regenerate the *.wsframes.json goldens with SNAPSHOT_UPDATE=1 and review."
        )

"""CHAT-07 wire-parity gate — the binding proof of the transport cutover (Phase 29, 29-01).

This is the ONE test the whole ``/ws/chat`` → SSE transport cutover binds against
(POR §4 Wave 1). It proves, OFFLINE via the scripted harness, that the pure
``run_events``→SSE projection (``characterization/_sse_projection.py``) replays each
of the 5 golden pipelines' recorded ``/ws/chat`` outbound frame sequences
IDENTICALLY (volatile-stripped, order-canonical). Because the SSE stream endpoint
(29-02) mounts that SAME projection, wire parity holds by construction — the SSE
frames are byte/event-identical to the WS drainer frames the current transport emits.

Two halves, both mandatory:
  * PARITY (5 cases): per golden pipeline, ``assert_wire_parity(recorded_ws_frames,
    run_events)`` passes — the SSE projection == the recorded WS frame sequence.
  * NON-VACUITY (1 case): an injected frame drift (extra key / changed type) makes
    ``assert_wire_parity`` RAISE — the gate provably cannot pass silently on empty or
    unchanged input (T-29-01-1; mirrors the ``assert_seq_contiguous`` non-vacuity
    precedent).

The goldens (``golden/<pipeline>.wsframes.json``) are the recorded, volatile-stripped,
order-canonical WS frame sequences. Regenerate them DELIBERATELY with
``SNAPSHOT_UPDATE=1`` (the same convention as the characterization event goldens);
the default (no-env) run is a real assertion against the committed frames. INV-3: the
scripted harness emits NO chat lane, so ``chat_message`` / ``chat_reply`` /
``stream_attached`` never appear in a ``*.wsframes.json`` golden — asserted below.
"""

from __future__ import annotations

import copy

import pytest

from tests.agents._scripted_model import _drive
from tests.agents.characterization import SNAPSHOT_UPDATE
from tests.agents.characterization._normalize import (
    _VOLATILE_STRIP_KEYS,
    _canonical_order,
    _normalize,
    load_events_golden,
    write_events_golden,
)
from tests.agents.characterization._sse_projection import (
    assert_wire_parity,
    run_events_from_engine_events,
    ws_frame_from_engine_event,
)

# The 5 INV-3 golden pipelines the transport cutover must preserve.
_PIPELINES = [
    "prototype",
    "od_prototype",
    "ppt",
    "prototype_revision",
    "app_builder",
]

# Chat-lane event types that must NEVER appear in a golden WS frame sequence — the
# scripted harness has no chat lane (INV-3; POR D-01). A golden carrying any of
# these would mean chat events leaked into the characterization baseline.
_CHAT_EVENT_TYPES = frozenset({"chat_message", "chat_reply", "stream_attached"})


def _golden_name(pipeline: str) -> str:
    return f"{pipeline}.wsframes.json"


async def _capture(pipeline: str) -> tuple[list[dict], list[dict]]:
    """Drive a pipeline offline and return ``(engine_events, ws_frames)``.

    The WS drainer sets ``section = pipeline_type`` (``websocket.py:2327``), so the
    section here is the driven pipeline label — reproducing the live wrapping.
    """
    events = await _drive(pipeline)
    assert events, f"{pipeline} produced no events"
    ws_frames = [ws_frame_from_engine_event(ev, section=pipeline) for ev in events]
    return events, ws_frames


def _record_golden(pipeline: str, ws_frames: list[dict]) -> None:
    """Write the volatile-stripped, order-canonical WS frame sequence golden.

    The ``--snapshot-update``-style regeneration path (consistent with the
    ``SNAPSHOT_UPDATE`` convention in ``characterization/__init__.py``). Reuses the
    shared ``_normalize`` + ``_canonical_order`` so the golden is stripped through the
    exact same ``_VOLATILE_STRIP_KEYS`` the parity comparator uses.
    """
    normalized = _canonical_order(_normalize(ws_frames))
    write_events_golden(_golden_name(pipeline), normalized)


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", _PIPELINES)
async def test_wire_parity_matches_golden(pipeline: str) -> None:
    """The run_events→SSE projection replays the recorded WS frame sequence identically.

    Under ``SNAPSHOT_UPDATE`` this RECORDS the golden; otherwise it asserts the fresh
    projection matches the committed, volatile-stripped WS frame golden and that no
    chat event leaked into the baseline (INV-3).
    """
    events, ws_frames = await _capture(pipeline)

    if SNAPSHOT_UPDATE:
        _record_golden(pipeline, ws_frames)
        return

    golden = load_events_golden(_golden_name(pipeline))
    assert golden is not None, (
        f"{_golden_name(pipeline)} golden missing — run once with SNAPSHOT_UPDATE=1 "
        f"and COMMIT golden/{_golden_name(pipeline)} so the default run is a real "
        "wire-parity assertion (CHAT-07)."
    )
    assert golden, f"{_golden_name(pipeline)} golden is empty (would pass vacuously)."

    # INV-3: the scripted harness has no chat lane — the baseline must be chat-dormant.
    golden_types = {f.get("type") for f in golden}
    leaked = golden_types & _CHAT_EVENT_TYPES
    assert not leaked, (
        f"{_golden_name(pipeline)} golden contains chat-lane event(s) {sorted(leaked)} "
        "— the INV-3 characterization baseline must stay chat-dormant."
    )
    # must_haves: every recorded frame carries a 'type'.
    assert all("type" in f for f in golden), (
        f"{_golden_name(pipeline)} golden has a frame missing 'type'."
    )

    # The binding compare: recorded WS frame sequence vs the SSE projection of the
    # freshly-derived run_events. `golden` IS the recorded ws_frames argument.
    run_events = run_events_from_engine_events(events)
    assert_wire_parity(golden, run_events)


@pytest.mark.asyncio
async def test_wire_parity_gate_is_non_vacuous() -> None:
    """The comparator RAISES on injected drift — the gate cannot silently pass.

    Baseline parity holds; then two independent drifts (an extra payload key, and a
    changed event type) each make ``assert_wire_parity`` raise. This proves the
    CHAT-07 gate detects a divergent SSE transport rather than passing on empty or
    unchanged input (T-29-01-1). Uses ``prototype_revision`` (the smallest pipeline).
    """
    events, ws_frames = await _capture("prototype_revision")
    run_events = run_events_from_engine_events(events)

    # Sanity: with no drift, the projection matches the freshly-captured WS frames.
    assert_wire_parity(ws_frames, run_events)

    # Drift 1 — an extra, non-volatile payload key (not in _VOLATILE_STRIP_KEYS, so
    # it survives normalization and MUST trip the comparator).
    assert "__injected_drift__" not in _VOLATILE_STRIP_KEYS
    drifted_key = copy.deepcopy(run_events)
    drifted_key[0]["payload"]["__injected_drift__"] = "boom"
    with pytest.raises(AssertionError):
        assert_wire_parity(ws_frames, drifted_key)

    # Drift 2 — a changed event type on one row.
    drifted_type = copy.deepcopy(run_events)
    drifted_type[0]["type"] = "totally_bogus_type"
    with pytest.raises(AssertionError):
        assert_wire_parity(ws_frames, drifted_type)

    # Drift 3 — an empty projection cannot pass (anti-vacuity guard).
    with pytest.raises(AssertionError):
        assert_wire_parity(ws_frames, [])

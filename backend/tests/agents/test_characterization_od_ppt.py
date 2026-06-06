"""Characterization: `od_ppt` deliverable byte-snapshot (SAFE-01 / INV-3).

The 003 characterization baseline for the `od_ppt` (OpenDesign PPT deck) pipeline.
Its three agents (od-ppt-brief-analyst / od-ppt-composer / od-ppt-validator) are
text-only, so the deck is a STREAMED-TEXT deliverable: ``_resolve_final_output``'s
text/PPT branch takes the LAST agent's (validator's) streamed output and unwraps a
single ``<artifact>`` wrapper. This test LOCKS that unwrapped deck BYTE-FOR-BYTE
before any engine/factory refactor (plan §24; INV-3). Byte-identity half of SAFE-01;
the semantic event snapshot lands in 01-02.

The od_ppt agents declare ``injects=[template, design_system]``; ``_drive`` seeds an
``od_context`` for od_ppt so ``_compose_injection`` does not raise
``TemplateMissingError``. Offline + unmarked so CI runs it; regenerate with
``SNAPSHOT_UPDATE=1``.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import _drive
from tests.agents.characterization import (
    SNAPSHOT_UPDATE,
    assert_deliverable_snapshot,
    extract_final_output,
)
from tests.agents.characterization._normalize import (
    _DOCUMENTED_EVENT_TYPES,
    _REQUIRED_DATA_KEYS,
    _canonical_order,
    _normalize,
    assert_seq_contiguous,
    load_events_golden,
    write_events_golden,
)


@pytest.mark.asyncio
async def test_od_ppt_deliverable_byte_snapshot() -> None:
    events = await _drive("od_ppt")
    assert events, "od_ppt produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("od_ppt.html", deliverable)


@pytest.mark.asyncio
async def test_od_ppt_event_snapshot() -> None:
    """Lock the normalized semantic event stream for ``od_ppt`` (SAFE-02 / SAFE-03)."""
    events = await _drive("od_ppt")
    assert events, "od_ppt produced no events"

    seen = {e.get("type") for e in events}
    unknown = seen - _DOCUMENTED_EVENT_TYPES
    assert not unknown, f"od_ppt emitted UNDOCUMENTED event type(s): {sorted(unknown)}"

    for ev in events:
        required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
        if required is None:
            continue
        missing = required - set((ev.get("data") or {}).keys())
        assert not missing, (
            f"od_ppt event '{ev.get('type')}' is MISSING required data keys "
            f"{sorted(missing)}"
        )

    assert_seq_contiguous(events)

    normalized = _canonical_order(_normalize(events))
    if SNAPSHOT_UPDATE:
        write_events_golden("od_ppt.events.json", normalized)
        return

    golden = load_events_golden("od_ppt.events.json")
    assert golden is not None, (
        "od_ppt.events.json golden missing — run once with SNAPSHOT_UPDATE=1 and "
        "COMMIT golden/od_ppt.events.json."
    )
    assert normalized == golden, (
        "od_ppt normalized event stream diverged from the committed golden "
        "(dropped/reordered event or lost required key). Regenerate intentionally "
        "with SNAPSHOT_UPDATE=1 (SAFE-02)."
    )

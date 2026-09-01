"""Characterization: `prototype_revision` deliverable byte-snapshot (SAFE-01 / INV-3).

The 003 characterization baseline for the `prototype_revision` pipeline (the
single revision agent edits ``prototype.html`` in place; that file IS the
deliverable). It LOCKS the deliverable BYTE-FOR-BYTE before any engine/factory
refactor (plan §24; INV-3). Byte-identity half of SAFE-01; the semantic event
snapshot lands in 01-02.

Drives fully OFFLINE via ``_drive``; snapshots ``pipeline_complete.final_output``.
Carries no live-LLM marker so CI runs it; regenerate with ``SNAPSHOT_UPDATE=1``.
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
async def test_prototype_revision_deliverable_byte_snapshot() -> None:
    events = await _drive("prototype_revision")
    assert events, "prototype_revision produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("prototype_revision.html", deliverable)


@pytest.mark.asyncio
@pytest.mark.issue("ISS-631")
async def test_prototype_revision_event_snapshot() -> None:
    """Lock the normalized semantic event stream for ``prototype_revision`` (SAFE-02 / SAFE-03)."""
    events = await _drive("prototype_revision")
    assert events, "prototype_revision produced no events"

    seen = {e.get("type") for e in events}
    unknown = seen - _DOCUMENTED_EVENT_TYPES
    assert not unknown, (
        f"prototype_revision emitted UNDOCUMENTED event type(s): {sorted(unknown)}"
    )

    for ev in events:
        required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
        if required is None:
            continue
        missing = required - set((ev.get("data") or {}).keys())
        assert not missing, (
            f"prototype_revision event '{ev.get('type')}' is MISSING required data "
            f"keys {sorted(missing)}"
        )

    assert_seq_contiguous(events)

    normalized = _canonical_order(_normalize(events))
    if SNAPSHOT_UPDATE:
        write_events_golden("prototype_revision.events.json", normalized)
        return

    golden = load_events_golden("prototype_revision.events.json")
    assert golden is not None, (
        "prototype_revision.events.json golden missing — run once with "
        "SNAPSHOT_UPDATE=1 and COMMIT golden/prototype_revision.events.json."
    )
    assert normalized == golden, (
        "prototype_revision normalized event stream diverged from the committed "
        "golden (dropped/reordered event or lost required key). Regenerate "
        "intentionally with SNAPSHOT_UPDATE=1 (SAFE-02)."
    )

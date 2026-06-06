"""Characterization: `prototype` deliverable byte-snapshot (SAFE-01 / INV-3).

This is the 003 characterization baseline for the `prototype` pipeline. It LOCKS
the pipeline's deliverable output BYTE-FOR-BYTE *before* any engine/factory refactor
(plan §24 — characterization tests first; INV-3 — no silent behavior change). It is
the byte-identity half of SAFE-01; the semantic event-stream snapshot (text-drift
robust) lands in plan 01-02.

The test drives the pipeline fully OFFLINE via ``_scripted_model._drive`` (no DB /
Bedrock / API key) and snapshots the deliverable carried on the engine's
``pipeline_complete`` event ``final_output``. It carries no live-LLM marker so CI
runs it offline. Regenerate the golden deliberately with ``SNAPSHOT_UPDATE=1``.
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
async def test_prototype_deliverable_byte_snapshot() -> None:
    events = await _drive("prototype")
    assert events, "prototype produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("prototype.html", deliverable)


@pytest.mark.asyncio
async def test_prototype_event_snapshot() -> None:
    """Lock the normalized semantic event stream for ``prototype`` (SAFE-02 / SAFE-03).

    Pins event types/order/required-keys/final-result while normalizing out volatile
    fields, so the snapshot survives 0C text drift but FAILS on a dropped/reordered
    event or a lost required key (INV-3 / D-05b). The required-keys + vocabulary
    assertions run BEFORE the equality compare so an empty/garbage stream cannot pass
    vacuously (T-02-02).
    """
    events = await _drive("prototype")
    assert events, "prototype produced no events"

    seen = {e.get("type") for e in events}
    unknown = seen - _DOCUMENTED_EVENT_TYPES
    assert not unknown, f"prototype emitted UNDOCUMENTED event type(s): {sorted(unknown)}"

    for ev in events:
        required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
        if required is None:
            continue
        missing = required - set((ev.get("data") or {}).keys())
        assert not missing, (
            f"prototype event '{ev.get('type')}' is MISSING required data keys "
            f"{sorted(missing)}"
        )

    assert_seq_contiguous(events)

    normalized = _canonical_order(_normalize(events))
    if SNAPSHOT_UPDATE:
        write_events_golden("prototype.events.json", normalized)
        return

    golden = load_events_golden("prototype.events.json")
    assert golden is not None, (
        "prototype.events.json golden missing — run once with SNAPSHOT_UPDATE=1 and "
        "COMMIT golden/prototype.events.json so the default run is a real assertion."
    )
    assert normalized == golden, (
        "prototype normalized event stream diverged from the committed golden — a "
        "dropped/reordered event or lost required key. If intentional (sanctioned 0C "
        "change), regenerate with SNAPSHOT_UPDATE=1 and review the diff (SAFE-02)."
    )

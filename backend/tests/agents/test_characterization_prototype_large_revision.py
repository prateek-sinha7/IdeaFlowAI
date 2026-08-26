"""Characterization: ``prototype_large_revision`` deliverable byte-snapshot (SAFE-01 / INV-3).

The 003 characterization baseline for the ``prototype_large_revision`` pipeline (the
multi-step planner + task_loop revision pipeline that edits ``prototype.html`` in
place as its deliverable). It LOCKS the deliverable BYTE-FOR-BYTE and the semantic
event stream before any engine/factory refactor (plan §24; INV-3).

Key structural invariants verified by this golden (revision-pipeline-refactor):
  * ``prototype-revision-analyzer`` fires as step 0 (``agent_start`` / ``agent_complete``).
  * ``=== REVISION ANALYSIS ===`` is injected into the context of step 1
    (``prototype-revision-planner``) via ``ectx.analyzer_solution`` (Requirements 2.2,
    2.4, 4.2, 5.2).
  * ``deliverable.revises_existing: true`` is intact (the pipeline_complete deliverable
    carries the revised ``prototype.html``).

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
async def test_prototype_large_revision_deliverable_byte_snapshot() -> None:
    events = await _drive("prototype_large_revision")
    assert events, "prototype_large_revision produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("prototype_large_revision.html", deliverable)


@pytest.mark.asyncio
async def test_prototype_large_revision_event_snapshot() -> None:
    """Lock the normalized semantic event stream for ``prototype_large_revision`` (SAFE-02 / SAFE-03)."""
    events = await _drive("prototype_large_revision")
    assert events, "prototype_large_revision produced no events"

    seen = {e.get("type") for e in events}
    unknown = seen - _DOCUMENTED_EVENT_TYPES
    assert not unknown, (
        f"prototype_large_revision emitted UNDOCUMENTED event type(s): {sorted(unknown)}"
    )

    for ev in events:
        required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
        if required is None:
            continue
        missing = required - set((ev.get("data") or {}).keys())
        assert not missing, (
            f"prototype_large_revision event '{ev.get('type')}' is MISSING required data "
            f"keys {sorted(missing)}"
        )

    assert_seq_contiguous(events)

    normalized = _canonical_order(_normalize(events))
    if SNAPSHOT_UPDATE:
        write_events_golden("prototype_large_revision.events.json", normalized)
        return

    golden = load_events_golden("prototype_large_revision.events.json")
    assert golden is not None, (
        "prototype_large_revision.events.json golden missing — run once with "
        "SNAPSHOT_UPDATE=1 and COMMIT golden/prototype_large_revision.events.json."
    )
    assert normalized == golden, (
        "prototype_large_revision normalized event stream diverged from the committed "
        "golden (dropped/reordered event or lost required key). Regenerate "
        "intentionally with SNAPSHOT_UPDATE=1 (SAFE-02)."
    )

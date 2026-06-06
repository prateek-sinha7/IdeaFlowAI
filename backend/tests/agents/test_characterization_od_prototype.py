"""Characterization: `od_prototype` deliverable byte-snapshot (SAFE-01 / INV-3).

The 003 characterization baseline for the `od_prototype` pipeline — the
OpenDesign-context alias of `prototype` (same agents, plus a selected template +
design system). It LOCKS the deliverable BYTE-FOR-BYTE before any engine/factory
refactor (plan §24; INV-3). Byte-identity half of SAFE-01; the semantic event
snapshot lands in 01-02.

``od_prototype`` has no AGENT.md of its own (the prototype agents declare
``pipeline_type: prototype``); ``_drive`` resolves the od_ alias for agent lookup
and forwards the unaliased label to ``execute()`` — exactly as the production WS
handler does. Offline + unmarked so CI runs it; regenerate with ``SNAPSHOT_UPDATE=1``.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import _drive
from tests.agents.characterization import (
    assert_deliverable_snapshot,
    extract_final_output,
)


@pytest.mark.asyncio
async def test_od_prototype_deliverable_byte_snapshot() -> None:
    events = await _drive("od_prototype")
    assert events, "od_prototype produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("od_prototype.html", deliverable)

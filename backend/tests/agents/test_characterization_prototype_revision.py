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
    assert_deliverable_snapshot,
    extract_final_output,
)


@pytest.mark.asyncio
async def test_prototype_revision_deliverable_byte_snapshot() -> None:
    events = await _drive("prototype_revision")
    assert events, "prototype_revision produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("prototype_revision.html", deliverable)

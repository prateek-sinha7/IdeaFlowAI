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
    assert_deliverable_snapshot,
    extract_final_output,
)


@pytest.mark.asyncio
async def test_od_ppt_deliverable_byte_snapshot() -> None:
    events = await _drive("od_ppt")
    assert events, "od_ppt produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("od_ppt.html", deliverable)

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
    assert_deliverable_snapshot,
    extract_final_output,
)


@pytest.mark.asyncio
async def test_prototype_deliverable_byte_snapshot() -> None:
    events = await _drive("prototype")
    assert events, "prototype produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("prototype.html", deliverable)

"""Characterization: `app_builder` deliverable byte-snapshot (SAFE-01 / INV-3).

The 003 characterization baseline for the `app_builder` code-gen pipeline. Code-gen
pipelines write multiple files to the run sandbox; ``_resolve_final_output``
serializes them into the ``filename:``-block bundle the UI's FilesTab /
AppBuilderPreview parse — that bundle is the deliverable. This test LOCKS that
serialized bundle BYTE-FOR-BYTE before any engine/factory refactor (plan §24;
INV-3). Byte-identity half of SAFE-01; the semantic event snapshot lands in 01-02.

Drives fully OFFLINE via ``_drive`` (the code-gen agent writes ``src/app.py`` +
``README.md`` to a fresh temp sandbox); snapshots ``pipeline_complete.final_output``.
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
async def test_app_builder_deliverable_byte_snapshot() -> None:
    events = await _drive("app_builder")
    assert events, "app_builder produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("app_builder.txt", deliverable)

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
async def test_app_builder_deliverable_byte_snapshot() -> None:
    events = await _drive("app_builder")
    assert events, "app_builder produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("app_builder.txt", deliverable)


@pytest.mark.asyncio
async def test_app_builder_event_snapshot() -> None:
    """Lock the normalized semantic event stream for ``app_builder`` (SAFE-02 / SAFE-03)."""
    events = await _drive("app_builder")
    assert events, "app_builder produced no events"

    seen = {e.get("type") for e in events}
    unknown = seen - _DOCUMENTED_EVENT_TYPES
    assert not unknown, f"app_builder emitted UNDOCUMENTED event type(s): {sorted(unknown)}"

    for ev in events:
        required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
        if required is None:
            continue
        missing = required - set((ev.get("data") or {}).keys())
        assert not missing, (
            f"app_builder event '{ev.get('type')}' is MISSING required data keys "
            f"{sorted(missing)}"
        )

    assert_seq_contiguous(events)

    normalized = _canonical_order(_normalize(events))
    if SNAPSHOT_UPDATE:
        write_events_golden("app_builder.events.json", normalized)
        return

    golden = load_events_golden("app_builder.events.json")
    assert golden is not None, (
        "app_builder.events.json golden missing — run once with SNAPSHOT_UPDATE=1 "
        "and COMMIT golden/app_builder.events.json."
    )
    assert normalized == golden, (
        "app_builder normalized event stream diverged from the committed golden "
        "(dropped/reordered event or lost required key). Regenerate intentionally "
        "with SNAPSHOT_UPDATE=1 (SAFE-02)."
    )

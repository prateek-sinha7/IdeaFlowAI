"""A gate step's reply must survive the single_file deliverable readback.

For a `single_file` deliverable the engine replaces a step's streamed text with
the deliverable file whenever the file is longer — so a downstream reader sees
the built artifact rather than a tool confirmation. Applied to a CONDITIONAL
GATE's source step that is fatal: the gate reads the trailing JSON object of that
reply, and an HTML document has none, so the run halts with "malformed
route_decision JSON" having built everything correctly.

Six live runs died this way. The readback now skips a step that declares
`produces: ["route_decision"]`.
"""
from __future__ import annotations

import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "agents/execution_engine/engine.py"


def _readback_block() -> str:
    """The single_file readback condition, as written in the engine."""
    text = SOURCE.read_text()
    start = text.index("_deliv = getattr(ectx, \"deliverable\", None)")
    end = text.index("output = file_from_disk", start)
    return text[start:end]


def test_readback_skips_a_decision_step() -> None:
    block = _readback_block()
    assert "route_decision" in block, (
        "the readback must exempt a step that produces route_decision — without "
        "it a conditional gate is handed the deliverable instead of the verdict"
    )
    assert re.search(r"not\s+_is_decision_step", block), (
        "the exemption must be part of the guard, not merely computed"
    )


def test_readback_still_applies_to_an_ordinary_step() -> None:
    block = _readback_block()
    # The point of the readback is unchanged for every non-gate step.
    assert '_deliv_strategy == "single_file"' in block
    assert "is_revision_workflow" in block
    assert "len(file_from_disk) > len(output)" in block


def test_decision_step_is_detected_from_produces() -> None:
    block = _readback_block()
    assert 'getattr(spec, "produces", None)' in block, (
        "a decision step is identified by its DECLARED produces, never by name"
    )

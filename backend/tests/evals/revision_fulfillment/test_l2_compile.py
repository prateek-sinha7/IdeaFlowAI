"""L2 — workflow compile shape (R-08 / design.md D-06).

``compile_for_run("prototype_revision")`` is the typed plan the kernel
executes. These assertions pin the exact shape the rest of this eval suite
(and the Phase-3 fix wiring) depends on — if the manifest drifts, this file
localizes it before any deeper eval confuses the symptom for the defect.

Mock-free: direct compiler call.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


@pytest.fixture(scope="module")
def compiled():
    from agents.execution_engine.engine import compile_for_run

    return compile_for_run("prototype_revision")


def test_two_steps_in_order(compiled) -> None:
    assert [s.agent_id for s in compiled.steps] == [
        "prototype-revision-agent",
        "prototype-revision-validate",
    ]


def test_step1_revision_agent_capabilities(compiled) -> None:
    step1 = compiled.steps[0]
    assert step1.strategy == "single_shot"
    assert step1.gates == ["validation"]
    assert step1.validators == ["html_static", "html_render"]
    assert step1.post_step == "revision_validation"
    assert step1.require_render is True


def test_step2_validate_agent_ungated(compiled) -> None:
    """FINDINGS A5: the LAST agent to touch the file runs with no gates —
    its edits are never re-validated. Pinned here as current behavior."""
    step2 = compiled.steps[1]
    assert step2.gates == []
    assert step2.post_step is None  # will change in Phase 3 (T-023: instruction_fulfillment)


def test_deliverable_is_in_place_revision(compiled) -> None:
    d = compiled.deliverable
    assert d.strategy == "single_file"
    assert d.name == "prototype.html"
    assert d.revises_existing is True


def test_context_and_clarify(compiled) -> None:
    assert "previous_run" in compiled.context_providers
    # FINDINGS A3: no clarification round-trip — the raw instruction is the
    # complete brief; interpretation rides on one model pass.
    assert compiled.clarify.mode == "skip"

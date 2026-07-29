"""Compiled workflow-manifest shape for the prototype_revision pipeline
(formerly "L2"; R-08 / design.md D-06), pinned against this pipeline's own
expected values. Shared assertion machinery lives in
evals/hybrid/common/compile_helpers.py — copy this pattern for a new
pipeline's equivalent test, supplying that pipeline's own expected values.

``compile_for_run("prototype_revision")`` turns
``agents/workflows/prototype_revision/workflow.yaml`` into the typed
``CompiledWorkflow`` plan the kernel executes. These assertions pin the
EXACT shape (step order/capabilities, deliverable, context providers,
clarify mode) that the rest of this eval suite (and the Phase-3 fix wiring)
depends on — if the manifest drifts, this file localizes it before any
deeper eval confuses the symptom for the defect.

Mock-free: direct compiler call, no monkeypatching.
"""

from __future__ import annotations

import pytest

from evals.hybrid.common.compile_helpers import (
    assert_deliverable,
    assert_step_agent_ids,
    assert_step_capabilities,
    compile_pipeline,
)

pytestmark = pytest.mark.eval


@pytest.fixture(scope="module")
def compiled():
    return compile_pipeline("prototype_revision")


def test_manifest_has_revision_agent_then_validate_agent_in_order(compiled) -> None:
    assert_step_agent_ids(
        compiled, ["prototype-revision-agent", "prototype-revision-validate"]
    )


def test_revision_agent_step_is_gated_and_validated_on_html(compiled) -> None:
    assert_step_capabilities(
        compiled.steps[0],
        strategy="single_shot",
        gates=["validation"],
        validators=["html_static", "html_render"],
        post_step="revision_validation",
        require_render=True,
    )


def test_validate_agent_step_runs_ungated_with_no_post_step(compiled) -> None:
    """FINDINGS A5: the LAST agent to touch the file runs with no gates —
    its edits are never re-validated. Pinned here as current behavior."""
    # post_step=None will change in Phase 3 (T-023: instruction_fulfillment)
    assert_step_capabilities(compiled.steps[1], gates=[], post_step=None)


def test_deliverable_is_single_file_revision_of_prototype_html(compiled) -> None:
    assert_deliverable(
        compiled, strategy="single_file", name="prototype.html", revises_existing=True
    )


def test_previous_run_context_wired_and_clarify_round_trip_skipped(compiled) -> None:
    assert "previous_run" in compiled.context_providers
    # FINDINGS A3: no clarification round-trip — the raw instruction is the
    # complete brief; interpretation rides on one model pass.
    assert compiled.clarify.mode == "skip"

"""Parity tests — the two parity traps that snapshots do NOT catch (MAN-04).

Parity trap #1 — planner: run everywhere EXCEPT the run_revision-dispatched pair.
  The legacy prototype planner-skip flag was False, so skip_planner is ALWAYS
  False — every dispatchable pipeline (incl. prototype) runs the planner/clarifier.
  That flag (and its module) were DELETED in 07-05; the AUTHORED truth is now the
  manifest's ``planner`` key. As of Phase 14 the two run_revision-dispatched
  manifests (``ppt_revision``, ``od_ppt_revision`` — ``_RUN_REVISION_DISPATCHED``)
  declare ``planner: skip``: clarify-auto would pause INDEFINITELY at
  ``event.wait()`` (clarify_engine) waiting for a questionnaire round-trip the FE
  revision panel never sends — a dispatched revision would hang forever. ALL other
  dispatchable manifests still declare planner: run; a skip on any of THOSE would
  change behavior and break the prototype event snapshots.

Parity trap #2 — clarify.defaults reproduce engine._pipeline_defaults verbatim.
  The clarify-mode auto seeding (engine.py) keys the default clarifying questions
  off a per-pipeline dict. With the offline _drive harness this is NOT exercised by
  characterization snapshots — this dedicated test is the only guard. The compiled
  clarify.defaults must equal the engine dict per pipeline; revisions / ids absent
  from the dict reuse the "custom" list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.loader import load_agent_spec
from agents.registry import _INTERNAL_PIPELINES, PIPELINE_AGENTS
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest

_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"

# The two pipelines the FE reaches via the `run_revision` WS frame
# (DashboardLayout.tsx). As of Phase 14 they declare planner: skip — clarify-auto
# would hang a dispatched revision at the clarify event.wait(). The other three
# *_revision manifests (prototype_revision, user_stories_revision,
# app_builder_revision) ride run_pipeline and KEEP planner: run.
_RUN_REVISION_DISPATCHED = frozenset({"ppt_revision", "od_ppt_revision"})

# Hard-copied VERBATIM from engine.ExecutionEngine.execute's local
# `_pipeline_defaults` dict (agents/execution_engine/engine.py:752-761). This is
# the authoritative source for clarify.defaults; if the engine dict changes, this
# copy (and the manifests) must change with it. Keep in lockstep.
_ENGINE_PIPELINE_DEFAULTS: dict[str, list[str]] = {
    "od_ppt":        ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "ppt":           ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "od_prototype":  ["target_audience", "scope", "priority", "style"],
    "prototype":     ["target_audience", "scope", "priority", "style"],
    "user_stories":  ["target_audience", "scope", "priority", "technology"],
    "app_builder":   ["technology", "scope", "target_audience", "security"],
    "mulesoft_to_springboot": ["scope", "technology", "timeline", "priority"],
    "dotnet_to_azure":        ["scope", "technology", "timeline", "priority"],
    "custom":        ["target_audience", "key_objectives", "scope", "priority"],
}
# The fallback the engine uses for any id absent from the dict: _pipeline_defaults["custom"].
_CUSTOM_DEFAULTS = _ENGINE_PIPELINE_DEFAULTS["custom"]


def _compile(workflow_id: str):
    return WorkflowCompiler().compile(
        load_manifest(workflow_id, _BASE), CapabilityRegistry()
    )


# ---------------------------------------------------------------------------
# Parity trap #1 — planner: run for every dispatchable manifest, EXCEPT the
# two run_revision-dispatched manifests which declare planner: skip (Phase 14)
# ---------------------------------------------------------------------------


def test_prototype_planner_runs() -> None:
    # Guards the premise of trap #1, re-expressed via the AUTHORED manifest after
    # the legacy planner-skip flag (and its module) were deleted in 07-05: the
    # prototype manifest must declare planner: run (i.e. NOT skip). If this ever
    # flips, the manifests + this test must be revisited.
    assert _compile("prototype").planner == "run"


@pytest.mark.parametrize(
    "workflow_id",
    sorted(set(PIPELINE_AGENTS) - set(_INTERNAL_PIPELINES)),
)
def test_planner_run_everywhere(workflow_id: str) -> None:
    plan = _compile(workflow_id)
    expected = "skip" if workflow_id in _RUN_REVISION_DISPATCHED else "run"
    assert plan.planner == expected, (
        f"{workflow_id} must declare planner: {expected} (parity trap #1 — "
        f"run_revision-dispatched manifests declare skip as of Phase 14, "
        f"clarify-auto would hang the revision panel; every other dispatchable "
        f"manifest still declares run)"
    )


def test_run_revision_manifests_declare_planner_skip() -> None:
    """The two run_revision-dispatched manifests declare planner: skip (Phase 14).

    A dispatched revision bypasses the planner LLM call AND the clarify pause:
    the engine's skip branch sets gate_verdict=PROCEED with no planner events,
    so the indefinite clarify event.wait() is never reached.
    """
    for workflow_id in sorted(_RUN_REVISION_DISPATCHED):
        assert _compile(workflow_id).planner == "skip", (
            f"{workflow_id} is run_revision-dispatched and must declare "
            f"planner: skip (clarify-auto would hang at event.wait())"
        )


def test_run_revision_revision_agents_declare_no_template_injects() -> None:
    """Design-wrinkle pin (Phase 14, settled): no agent of the two
    run_revision-dispatched pipelines may declare a ``template`` or
    ``design_system`` inject.

    Evidence for why this constraint must hold (the executable pin the Phase-14
    planning context mandates):

    * Revision dispatch passes ``od_context=None`` and goes
      ``_handle_revision -> execute()`` — it NEVER traverses the run_pipeline
      ingress where the 13-06 ``missing_template_context`` guard lives
      (websocket.py ``_handle_workflow_execution``), so nothing would resolve a
      template for an inject-declaring agent on this path.
    * ``factory._compose_injection`` raises ``TemplateMissingError`` ONLY for
      inject-declaring agents — inject-free agents dispatch fine with
      ``od_context=None``.
    * The composed revision context already embeds the complete parent deck —
      the physical realization of the template — so the injects are not needed
      for a surgical revision.

    A future inject-declaring revision agent must FIRST persist ``template_id``
    on WorkflowRun (additive migration, Q3) so revision dispatch can re-resolve
    the parent's template. This test makes that prerequisite loud: adding the
    inject without the persistence work fails CI here.
    """
    for workflow_id in sorted(_RUN_REVISION_DISPATCHED):
        plan = _compile(workflow_id)
        for step in plan.steps:
            spec = load_agent_spec(step.agent_id)
            assert "template" not in spec.injects, (
                f"{workflow_id}/{step.agent_id} declares a 'template' inject — "
                f"run_revision dispatch passes od_context=None; persist "
                f"template_id on WorkflowRun (additive, Q3) first"
            )
            assert "design_system" not in spec.injects, (
                f"{workflow_id}/{step.agent_id} declares a 'design_system' "
                f"inject — run_revision dispatch passes od_context=None; "
                f"persist template_id on WorkflowRun (additive, Q3) first"
            )


# ---------------------------------------------------------------------------
# Parity trap #2 — clarify.defaults == engine _pipeline_defaults (verbatim)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workflow_id", sorted(PIPELINE_AGENTS))
def test_clarify_defaults_match_engine(workflow_id: str) -> None:
    plan = _compile(workflow_id)
    # od_prototype is an alias (no manifest); every real id resolves to itself.
    # An id present in the engine dict must match it verbatim; any id absent
    # (the *_revision manifests, reverse_engineer, chat) reuses the custom list.
    expected = _ENGINE_PIPELINE_DEFAULTS.get(workflow_id, _CUSTOM_DEFAULTS)
    assert plan.clarify.defaults == expected, (
        f"{workflow_id} clarify.defaults must reproduce the engine "
        f"_pipeline_defaults entry verbatim (engine.py:752-761)"
    )

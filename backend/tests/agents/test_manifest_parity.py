"""Parity tests — the two parity traps that snapshots do NOT catch (MAN-04).

Parity trap #1 — planner: run everywhere EXCEPT the run_revision-dispatched pair.
  The legacy prototype planner-skip flag was False, so skip_planner is ALWAYS
  False — every dispatchable pipeline (incl. prototype) runs the planner/clarifier.
  That flag (and its module) were DELETED in 07-05; the AUTHORED truth is now the
  manifest's ``planner`` key. As of Phase 14 the run_revision-dispatched
  manifest (``ppt_revision`` — ``_RUN_REVISION_DISPATCHED``) declares
  ``planner: skip``: clarify-auto would pause INDEFINITELY at
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
from agents.loader import SUPPORTED_PIPELINE_TYPES, load_agent_spec
from agents.registry import _INTERNAL_PIPELINES
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest

_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"

# FIX-051 / ISS-035: PIPELINE_AGENTS is now derived from a folder scan and can
# contain a pipeline_type with real agents but no manifest yet (e.g.
# spec_kit) or a pure id-alias with none (od_prototype/od_prototype_revision
# — resolved to `prototype` before ever reaching a manifest lookup). These
# manifest-content parity tests only make sense for pipelines that actually
# have an authored workflow.yaml.
_PROMPTS = Path(__file__).resolve().parents[2] / "agents" / "prompts"


def _is_product_workflow(workflow_id: str) -> bool:
    """True unless this manifest's agents live only under tests/agents/fixtures/.

    ADR-0005 derives SUPPORTED_PIPELINE_TYPES from disk, which pulled in the
    four ``sample_*`` engine fixtures. Three of them — sample_brownfield,
    sample_fanout, sample_wave — name agents with no ``AGENT.md`` under
    ``agents/prompts/`` at all; their agents are test fixtures. The parity
    traps below pin PRODUCT conventions (planner mode, the clarify question
    set), which those manifests were never written to satisfy — sample_fanout
    exists to exercise fan-out compilation, not to ask a user about scope.

    Filtered by PROPERTY, not by name prefix: give a fixture real agents under
    agents/prompts/ and it becomes a product workflow subject to these traps,
    which is the correct outcome. ``sample_subagents_parallel`` already is one
    — its agent (custom-agent) exists — so it is NOT filtered here and is
    pinned explicitly below.
    """
    manifest = load_manifest(workflow_id, _BASE)
    # WorkflowManifest.steps are raw dicts at this stage (the compiler turns them
    # into Step objects later), so read the key, not an attribute.
    steps = getattr(manifest, "steps", None) or []
    ids = [s.get("agent") for s in steps if isinstance(s, dict)]
    ids = [i for i in ids if i]
    if not ids:
        return True
    return any((_PROMPTS / i / "AGENT.md").exists() for i in ids)


_MANIFEST_BACKED_IDS = sorted(
    pt
    for pt in SUPPORTED_PIPELINE_TYPES
    if (_BASE / pt / "workflow.yaml").exists() and _is_product_workflow(pt)
)

# The pipeline the FE reaches via the `run_revision` WS frame
# (DashboardLayout.tsx). As of Phase 14 it declares planner: skip — clarify-auto
# would hang a dispatched revision at the clarify event.wait(). (Formerly two
# manifests — ppt_revision and od_ppt_revision — collapsed into one: the
# od_ppt_revision agent set now declares pipeline_type: ppt_revision directly,
# see agents/registry.py. That collapse (commit ef32ef88) ALSO deleted
# agents/workflows/od_ppt_revision/workflow.yaml — "od_ppt_revision" is no
# longer in SUPPORTED_PIPELINE_TYPES at all, so it must NOT appear below; a
# manifest-id set is compiled directly via `_compile()`, which raises
# FileNotFoundError for a dropped id.) The other three *_revision manifests
# (prototype_revision, user_stories_revision, app_builder_revision) ride
# run_pipeline and KEEP planner: run.
# ISS-050 (KAN-156) adds prototype_revision and user_stories_revision — both are
# now reachable from the generic chat-lane revision channel (Phase 29
# route_chat_turn / CHANNEL_REVISION) and CR-02 in engine._handle_revision
# rejects any planner: run target pre-dispatch. app_builder_revision still
# declares planner: run (not chat-lane dispatched).
_RUN_REVISION_DISPATCHED = frozenset({
    "ppt_revision",
    "prototype_revision",
    "user_stories_revision",
    # Authored with the composed-workflow builder; declares planner: skip like
    # its siblings but was never added here. Sibling trap: keep in lockstep with
    # tests/agents/test_id_alias_resolver.py::_RUN_REVISION_DISPATCHED.
    "custom_revision",
    # Flipped to planner: skip — it was authored as `run` and so could never be
    # revision-dispatched (CR-02 refused it; the run died with 0 events).
    "app_builder_revision",
})

# sample_subagents_parallel is a separate, non-revision planner-skip case: a
# deliberately tiny local workflow where running the deep planner would cost
# more than the work. It is NOT run_revision-dispatched (not reachable via the
# run_revision WS frame), so it is kept out of _RUN_REVISION_DISPATCHED and
# unioned in separately wherever "planner: skip" is the expectation. Visible
# here only since ADR-0005 derived SUPPORTED_PIPELINE_TYPES from disk. It is
# also a TIMING test for sibling-group parallelism, and a deep-planner
# round-trip in front of it would add variance to the only number the
# workflow exists to measure.
_PLANNER_SKIP_IDS = _RUN_REVISION_DISPATCHED | {
    "sample_subagents_parallel",
}

# Hard-copied VERBATIM from each pipeline's `agents/workflows/<id>/workflow.yaml`
# `clarify.defaults`. This dict originally mirrored engine.ExecutionEngine
# .execute's local `_pipeline_defaults` dict (pre-migration engine.py:752-761),
# but that literal dict was migrated OUT of the engine and into the manifests in
# MAN-04/MAN-05 (commit 63f0fc66) — `compiled.clarify.defaults` (sourced from the
# manifest) is the authoritative value now, and KAN-74 (commit ae4e36f7)
# subsequently extended most pipelines' defaults from 4 to 8 items. This copy
# exists purely to catch UNINTENTIONAL manifest drift; when a manifest's
# clarify.defaults is deliberately changed, update this copy to match.
_ENGINE_PIPELINE_DEFAULTS: dict[str, list[str]] = {
    "ppt":           ["target_audience", "tone_and_style", "key_objectives", "slide_count", "content_depth", "data_availability", "visual_style", "key_sections"],
    "prototype":     ["target_audience", "scope", "priority", "style", "user_journeys", "key_screens", "interactions", "personas"],
    "user_stories":  ["target_audience", "scope", "priority", "technology", "personas", "user_journeys", "business_rules", "compliance_security"],
    "app_builder":   ["technology", "scope", "target_audience", "security", "user_journeys", "data_model", "integrations", "performance"],
    "mulesoft_to_springboot": ["scope", "technology", "timeline", "priority", "integration_patterns", "target_infrastructure", "data_migration", "compliance_security"],
    "dotnet_to_azure":        ["scope", "technology", "timeline", "priority", "azure_services", "data_migration", "integration_patterns", "compliance_security"],
    "custom":        ["target_audience", "key_objectives", "scope", "priority", "output_format", "constraints", "domain", "assumptions"],
    # clarify.mode: skip — a composed spec-012 shape test takes its topic
    # straight from the run input and asks nothing (ADR-0005 made it visible).
    "sample_subagents_parallel": [],
    # clarify.mode: skip for the same reason — the revision panel supplies the
    # instruction directly.
    "custom_revision": [],
}
# The fallback for any id absent from the dict above — the *_revision manifests
# (ppt_revision, prototype_revision, user_stories_revision, app_builder_revision),
# chat, and reverse_engineer. These were NOT touched by KAN-74 and still declare
# the pre-KAN-74 4-item "custom" list verbatim — this is intentionally decoupled
# from `_ENGINE_PIPELINE_DEFAULTS["custom"]` above (the "custom" PIPELINE's own
# defaults DID get extended to 8 by KAN-74; the revision/edge-id fallback did not).
_CUSTOM_DEFAULTS = ["target_audience", "key_objectives", "scope", "priority"]


def _compile(workflow_id: str):
    return WorkflowCompiler().compile(
        load_manifest(workflow_id, _BASE), CapabilityRegistry()
    )


# ---------------------------------------------------------------------------
# Parity trap #1 — planner: run for every dispatchable manifest, EXCEPT the
# run_revision-dispatched set which declares planner: skip (Phase 14 original:
# ppt_revision / od_ppt_revision; ISS-050 addition: prototype_revision /
# user_stories_revision — now also reachable via the chat-lane revision channel)
# ---------------------------------------------------------------------------


def test_prototype_planner_runs() -> None:
    # Guards the premise of trap #1, re-expressed via the AUTHORED manifest after
    # the legacy planner-skip flag (and its module) were deleted in 07-05: the
    # prototype manifest must declare planner: run (i.e. NOT skip). If this ever
    # flips, the manifests + this test must be revisited.
    assert _compile("prototype").planner == "run"


@pytest.mark.parametrize(
    "workflow_id",
    sorted(set(_MANIFEST_BACKED_IDS) - set(_INTERNAL_PIPELINES)),
)
def test_planner_run_everywhere(workflow_id: str) -> None:
    plan = _compile(workflow_id)
    expected = "skip" if workflow_id in _PLANNER_SKIP_IDS else "run"
    assert plan.planner == expected, (
        f"{workflow_id} must declare planner: {expected} (parity trap #1 — "
        f"run_revision-dispatched manifests declare skip as of Phase 14, "
        f"clarify-auto would hang the revision panel; sample_subagents_parallel "
        f"declares skip as a deliberately-minimal local pipeline; every other "
        f"dispatchable manifest still declares run)"
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


@pytest.mark.parametrize("workflow_id", _MANIFEST_BACKED_IDS)
def test_clarify_defaults_match_engine(workflow_id: str) -> None:
    plan = _compile(workflow_id)
    # od_prototype is an alias (no manifest); every real id resolves to itself.
    # An id present in the engine dict must match it verbatim; any id absent
    # (the *_revision manifests, reverse_engineer, chat) reuses the custom list.
    expected = _ENGINE_PIPELINE_DEFAULTS.get(workflow_id, _CUSTOM_DEFAULTS)
    assert plan.clarify.defaults == expected, (
        f"{workflow_id} clarify.defaults must reproduce the pinned copy of the "
        f"manifest's own clarify.defaults verbatim (see _ENGINE_PIPELINE_DEFAULTS "
        f"above) — if this manifest's defaults were deliberately changed, update "
        f"the pinned copy to match"
    )

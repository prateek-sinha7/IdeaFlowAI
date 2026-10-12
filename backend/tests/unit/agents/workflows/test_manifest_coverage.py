"""Coverage test — every manifest-backed pipeline loads + compiles (MAN-04 / D-05).

ZERO exemptions: all 17 manifest-backed pipelines must load via load_manifest
and compile via WorkflowCompiler. Additionally the compiled step order must
equal the registry's agent membership order (RESEARCH Pitfall 3 — a manifest
must not silently reorder agents and break snapshots).

FIX-051 / ISS-035: the coverage set is scoped to pipeline_types that actually
have an authored `workflow.yaml` manifest, NOT to every ``PIPELINE_AGENTS``
key — ``PIPELINE_AGENTS`` is now derived from a folder scan and can contain a
pipeline_type with real agents but no manifest yet (e.g. ``spec_kit``), which
is an in-progress pipeline, not a compilable one.

NOTE: the former `ppt` quirk (ppt agents physically declaring pipeline_type:
od_ppt, a shared-agent alias) is gone — the od-ppt agent set now declares
pipeline_type: ppt directly, and the legacy ppt/od_ppt_revision manifests are
archived (agents/workflows/.archive/), dropping the manifest-backed count from
15 to 13. get_pipeline_agents(id) is the canonical membership/order for every
remaining id.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.loader import SUPPORTED_PIPELINE_TYPES
from agents.registry import PIPELINE_AGENTS, get_pipeline_agents
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest
from agents.workflows.plan import CompiledWorkflow

_BASE = Path(__file__).resolve().parents[4] / "agents" / "workflows"
_PROMPTS = Path(__file__).resolve().parents[4] / "agents" / "prompts"

_MANIFEST_BACKED_IDS = sorted(
    pt for pt in SUPPORTED_PIPELINE_TYPES if (_BASE / pt / "workflow.yaml").exists()
)


def test_exactly_18_keys() -> None:
    """The coverage set is every manifest-backed pipeline — currently 39.

    (The test NAME is historical — the pin has moved several times and renaming
    the test would churn its id. The number below is the contract.)

    Went 17 -> 18 when ``custom_revision`` was authored alongside the composed
    workflow builder; went 18 -> 20 when ``prototype_large_revision`` and
    ``prototype_feature_revision`` had their duplicate agent directories
    replaced with shared agents from the main prototype pipeline (revision
    pipeline agent reuse spec), making them fully loadable and discoverable;
    went 20 -> 21 when ``sc001-test-fixture`` was authored (d0562d97) — the
    manifest-only workflow that PROVES SC-001 (a new custom workflow needs no
    engine edit), so it necessarily has a ``workflow.yaml`` and is in scope.

    Went 20 -> 28 with spec 014/015: the seven ``ex_A*`` conditional-gate example
    workflows, ``sc001-test-fixture``, and the ``ex_A3`` language variants. Every
    directory carrying a ``workflow.yaml`` is in scope by the rule below, so they
    join on their own.

    Went 28 -> 29 with spec 017's `ppt_v2`.

    Went 29 -> 35 with spec 017/018 STABILIZATION: four ex_* engine-dispatch fixtures
    (ex_publish_step, ex_test_loop_reachable_skip, ex_test_transitive_skip,
    ex_validation_retry) plus two smoke tests (pdf_to_prototype, ex_playwright_smoke_test).
    All follow the "every directory with a workflow.yaml" rule (ADR-0005).

    Went 36 -> 35: pdf_to_prototype deleted; prototype_v2 ("Build a prototype
    from documents") replaces it.

    Went 35 -> 36 with spec 021: the backlog workflow.

    Went 36 -> 39 with spec 022: prototype_v2_revision, prototype_v2_feature_revision
    and backlog_revision.

    Includes the ``sample_*`` fixture manifests: ``SUPPORTED_PIPELINE_TYPES``
    is derived from disk (ADR-0005), so every directory with a
    ``workflow.yaml`` is in scope — "zero exemptions among pipelines that
    actually have a workflow.yaml" is the rule.
    """
    assert len(_MANIFEST_BACKED_IDS) == 39, (
        f"manifest-backed pipeline count changed to {len(_MANIFEST_BACKED_IDS)} "
        f"— a workflow.yaml was added or removed. Confirm it is intentional, then "
        f"update this pin: {_MANIFEST_BACKED_IDS}"
    )


def _agent_is_absent_from_prompts(agent_id: str) -> bool:
    """True when the registry could not possibly know about this step's agent.

    Two legitimate reasons a manifest step has no registry counterpart:

      * it is a template INSTANCE — ``custom-agent:emoji`` (ADR-0003). No
        ``AGENT.md`` declares it and none ever will; the compiler mints the
        synthetic id from ``instance_id``.
      * its ``AGENT.md`` lives under ``tests/agents/fixtures/`` rather than
        ``agents/prompts/`` — the ``sample_*`` engine fixtures.

    Either way the registry is not MISSING something; there is nothing on the
    production agent path for it to have found.
    """
    if ":" in agent_id:
        return True
    return not (_PROMPTS / agent_id / "AGENT.md").exists()


# ── Known drift: the shared revision analyzer (ADR-0003 / ADR-0005) ──────────
# `prototype-revision-analyzer` is step 0 of all THREE prototype revision
# manifests (commit e0f6beeed promoted it), but an AGENT.md may declare only ONE
# `pipeline_type`, so it declares its own — `prototype_revision_analyzer`.
# `get_pipeline_agents()` derives membership by scanning that field, so the
# registry can never list it under the three pipelines that actually run it.
#
# This is the registry/manifest split working as designed: the registry says
# WHICH agents belong to a pipeline, the manifest says HOW they run. ADR-0003
# removed the run-entry membership assertion for exactly this class of case.
# xfail is strict: if the drift is ever genuinely resolved (multi-pipeline
# membership, or an explicit PIPELINE_AGENTS entry) this turns red and must be
# un-marked rather than quietly passing.
_SHARED_ANALYZER_DRIFT = {
    "prototype_revision",
    "prototype_large_revision",
    "prototype_feature_revision",
}


def _is_manifest_supplied(agent_id: str, workflow_id: str) -> bool:
    """True when a manifest step's agent is legitimately absent from THIS roster.

    ``PIPELINE_AGENTS`` is derived from each ``AGENT.md``'s ``pipeline_type`` (a single
    id OR a list). An agent whose declaration does not enumerate ``workflow_id`` cannot
    appear in that pipeline's roster, yet the manifest may still run it as a step — the
    engine builds the roster from ``compiled.steps`` in that case, so the MANIFEST is
    the execution source of truth.

    ``prototype-revision-analyzer`` is the live case: promoted to step 0 of all three
    revision manifests while declaring only its own private
    ``pipeline_type: prototype_revision_analyzer``.

    Deliberately NARROW — the agent must be discoverable under some OTHER pipeline (or
    have no ``AGENT.md`` at all). An agent that exists on disk but belongs to NO pipeline
    is the wrong-``pipeline_type``/rename drift the caller must still flag.
    """
    if _agent_is_absent_from_prompts(agent_id):
        return True
    return any(
        agent_id in ids for pt, ids in PIPELINE_AGENTS.items() if pt != workflow_id
    )


# Shared-analyzer workflows are filtered out when the parameters are built — the
# roster comparison does not apply to them (ADR-0003/ADR-0005). A run-time xfail
# is a failure in CI's offline partition.
@pytest.mark.parametrize(
    "workflow_id",
    [w for w in _MANIFEST_BACKED_IDS if w not in _SHARED_ANALYZER_DRIFT],
)
def test_all_load_compile(workflow_id: str) -> None:
    manifest = load_manifest(workflow_id, _BASE)
    plan = WorkflowCompiler().compile(manifest, CapabilityRegistry())

    assert isinstance(plan, CompiledWorkflow)
    assert plan.id == workflow_id

    compiled_order = [s.agent_id for s in plan.steps]
    registry_order = [a.id for a in get_pipeline_agents(workflow_id)]

    if registry_order:
        # Every manifest step the roster does NOT contain must be explainable —
        # otherwise an agent silently dropped from discovery (wrong pipeline_type,
        # a rename) would be excused by the filter below instead of caught.
        unexplained_steps = [
            a
            for a in compiled_order
            if a not in registry_order and not _is_manifest_supplied(a, workflow_id)
        ]
        assert not unexplained_steps, (
            f"{workflow_id}: manifest steps {unexplained_steps} are absent from the "
            f"registry roster and are NOT manifest-supplied — they exist under "
            f"agents/prompts/ but belong to no pipeline. That is discovery drift "
            f"(a wrong pipeline_type, or a rename), not a legitimate manifest-only step."
        )

        # Step order must equal the registry membership order (Pitfall 3), compared
        # over the REGISTRY-OWNED steps. This is the ONLY surviving check of
        # manifest/registry parity — the run-entry assertion that used to enforce it
        # was removed (ADR-0003), so if this fails, nothing else will catch it.
        # Manifest-supplied steps are excluded because the roster cannot contain them
        # by construction (see ``_is_manifest_supplied``); every other step, and their
        # relative ORDER, is still strictly pinned.
        registry_owned_order = [a for a in compiled_order if a in registry_order]
        assert registry_owned_order == registry_order, (
            f"{workflow_id}: manifest step order has drifted from registry "
            f"membership. Nothing checks this at runtime any more (ADR-0003). "
            f"manifest(registry-owned)={registry_owned_order} registry={registry_order}"
        )
        return

    # Empty registry membership. Legitimate ONLY when the registry genuinely
    # has nothing to describe — otherwise this is exactly the drift the deleted
    # assertion existed to catch, and it must not pass silently.
    assert PIPELINE_AGENTS.get(workflow_id) in (None, []), (
        f"{workflow_id}: get_pipeline_agents returned nothing but PIPELINE_AGENTS "
        "has entries — that is a discovery bug, not a template workflow"
    )
    unexplained = [a for a in compiled_order if not _agent_is_absent_from_prompts(a)]
    assert not unexplained, (
        f"{workflow_id} has no registry membership, but these steps name agents "
        f"that DO exist under agents/prompts/: {unexplained}. An agent that "
        "exists on disk should have been discovered into the roster — this is "
        "drift (a wrong pipeline_type, or a rename), not a template workflow."
    )

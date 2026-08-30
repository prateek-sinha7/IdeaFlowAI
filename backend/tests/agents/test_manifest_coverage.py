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

_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"
_PROMPTS = Path(__file__).resolve().parents[2] / "agents" / "prompts"

_MANIFEST_BACKED_IDS = sorted(
    pt
    for pt in SUPPORTED_PIPELINE_TYPES
    if (_BASE / pt / "workflow.yaml").exists()
)


def test_exactly_18_keys() -> None:
    """The coverage set is every manifest-backed pipeline — currently 29.

    Went 17 -> 18 when ``custom_revision`` was authored alongside the composed
    workflow builder; went 18 -> 20 when ``prototype_large_revision`` and
    ``prototype_feature_revision`` had their duplicate agent directories
    replaced with shared agents from the main prototype pipeline (revision
    pipeline agent reuse spec), making them fully loadable and discoverable.

    Went 20 -> 28 with spec 014/015: the seven ``ex_A*`` conditional-gate example
    workflows, ``sc001-test-fixture``, and the ``ex_A3`` language variants. Every
    directory carrying a ``workflow.yaml`` is in scope by the rule below, so they
    join on their own.

    Went 28 -> 29 with spec 017's `ppt_v2`.

    Went 29 -> 30 with spec 018's `playwright_smoke_test`.

    Includes the ``sample_*`` fixture manifests: ``SUPPORTED_PIPELINE_TYPES``
    is derived from disk (ADR-0005), so every directory with a
    ``workflow.yaml`` is in scope — "zero exemptions among pipelines that
    actually have a workflow.yaml" is the rule.
    """
    assert len(_MANIFEST_BACKED_IDS) == 30


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


@pytest.mark.parametrize("workflow_id", _MANIFEST_BACKED_IDS)
def test_all_load_compile(workflow_id: str) -> None:
    manifest = load_manifest(workflow_id, _BASE)
    plan = WorkflowCompiler().compile(manifest, CapabilityRegistry())

    assert isinstance(plan, CompiledWorkflow)
    assert plan.id == workflow_id

    compiled_order = [s.agent_id for s in plan.steps]
    registry_order = [a.id for a in get_pipeline_agents(workflow_id)]

    if registry_order and set(registry_order) < set(compiled_order):
        # A workflow that REUSES an agent from another pipeline has a PARTIAL
        # registry side: PIPELINE_AGENTS is derived from each AGENT.md's
        # `pipeline_type`, so ppt_v2's entry holds only the two agents authored
        # for it, not ppt's brief-analyst and composer it reuses verbatim
        # (spec 017). Equality would forbid reuse; the anti-reorder guard below
        # survives as relative order.
        positions = [compiled_order.index(a) for a in registry_order]
        assert positions == sorted(positions), (
            f"{workflow_id}: registry agents {registry_order} appear out of order "
            f"in the compiled plan {compiled_order} — the manifest reordered them"
        )
        return
    elif registry_order:
        # Step order must equal the registry membership order (Pitfall 3).
        # This is the ONLY surviving check of manifest/registry parity — the
        # run-entry assertion that used to enforce it was removed (ADR-0003),
        # so if this fails, nothing else will catch it.
        assert compiled_order == registry_order, (
            f"{workflow_id}: manifest step order has drifted from registry "
            "membership. Nothing checks this at runtime any more (ADR-0003)."
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

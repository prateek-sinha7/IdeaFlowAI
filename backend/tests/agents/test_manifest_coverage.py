"""Coverage test — every manifest-backed pipeline loads + compiles (MAN-04 / D-05).

ZERO exemptions: all 15 manifest-backed pipelines must load via load_manifest
and compile via WorkflowCompiler. Additionally the compiled step order must
equal the registry's agent membership order (RESEARCH Pitfall 3 — a manifest
must not silently reorder agents and break snapshots).

FIX-051 / ISS-035: the coverage set is scoped to pipeline_types that actually
have an authored `workflow.yaml` manifest, NOT to every ``PIPELINE_AGENTS``
key — ``PIPELINE_AGENTS`` is now derived from a folder scan and can contain a
pipeline_type with real agents but no manifest yet (e.g. ``spec_kit``), which
is an in-progress pipeline, not a compilable one.

NOTE on the `ppt` quirk: the ppt agents physically declare pipeline_type: od_ppt
(shared agents), so get_pipeline_agents("ppt") is empty even though
PIPELINE_AGENTS["ppt"] lists 3 agents. The canonical membership/order the engine
drives is PIPELINE_AGENTS[id]; get_pipeline_agents(id) equals it wherever it is
non-empty. The step-order assertion therefore compares against
get_pipeline_agents(id) when that is non-empty, and against PIPELINE_AGENTS[id]
otherwise.
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

_MANIFEST_BACKED_IDS = sorted(
    pt
    for pt in SUPPORTED_PIPELINE_TYPES
    if (_BASE / pt / "workflow.yaml").exists()
)


def test_exactly_15_keys() -> None:
    """The coverage set is exactly the 15 manifest-backed pipelines (zero
    exemptions among pipelines that actually have a workflow.yaml)."""
    assert len(_MANIFEST_BACKED_IDS) == 15


@pytest.mark.parametrize("workflow_id", _MANIFEST_BACKED_IDS)
def test_all_load_compile(workflow_id: str) -> None:
    manifest = load_manifest(workflow_id, _BASE)
    plan = WorkflowCompiler().compile(manifest, CapabilityRegistry())

    assert isinstance(plan, CompiledWorkflow)
    assert plan.id == workflow_id

    # Step order must equal the registry membership order (Pitfall 3).
    compiled_order = [s.agent_id for s in plan.steps]
    registry_order = [a.id for a in get_pipeline_agents(workflow_id)]
    expected = registry_order if registry_order else PIPELINE_AGENTS[workflow_id]
    assert compiled_order == expected

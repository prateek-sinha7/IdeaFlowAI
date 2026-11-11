"""``deliverable.chain_policy`` accepts only ``refuse`` (gap 3, option A).

Admission refuses a missing chain payload whatever the manifest says (B5), so the
former ``degrade`` value described behaviour that no longer exists. The compiler now
rejects it by name (INV-5: unknown values are an error, never defaulted).
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest


def _manifest(**deliverable_extra) -> WorkflowManifest:
    return WorkflowManifest(
        id="chain-demo",
        steps=[{"agent": "demo-agent", "strategy": "single_shot"}],
        deliverable={"strategy": "single_file", "name": "out.md", **deliverable_extra},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def test_compile_rejects_degrade_when_chain_policy_is_degrade() -> None:
    manifest = _manifest(chains_from=True, chain_policy="degrade")

    with pytest.raises(CompilerError, match="chain_policy 'degrade'"):
        WorkflowCompiler().compile(manifest, CapabilityRegistry())


def test_compile_rejects_unknown_value_when_chain_policy_is_bogus() -> None:
    manifest = _manifest(chains_from=True, chain_policy="bogus")

    with pytest.raises(CompilerError, match="chain_policy 'bogus'"):
        WorkflowCompiler().compile(manifest, CapabilityRegistry())


def test_compile_accepts_refuse_when_chain_policy_is_refuse() -> None:
    manifest = _manifest(chains_from=True, chain_policy="refuse")

    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())

    assert compiled.deliverable.chain_policy == "refuse"


def test_compile_defaults_to_refuse_when_chain_policy_is_omitted() -> None:
    compiled = WorkflowCompiler().compile(_manifest(), CapabilityRegistry())

    assert compiled.deliverable.chain_policy == "refuse"

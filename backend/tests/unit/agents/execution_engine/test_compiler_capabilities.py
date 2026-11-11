"""Manifest -> compiler propagation of the ``capabilities`` block (gap 1).

``WorkflowManifest.capabilities`` (``{"internet": bool}``) is parsed and validated, and
the engine / factory consume ``CompiledWorkflow.capabilities``. The compiler is the only
link between the two: ``WorkflowCompiler.compile`` must CARRY the block verbatim onto the
compiled plan (INV-5: pure data pass-through). Before the fix it dropped the block, so a
user-composed workflow that enabled Internet compiled to ``capabilities == {}`` and the
run never bound the internet tools.

The sibling ``tests/unit/agents/test_capabilities_threading.py`` covers the engine ->
factory half; this file covers the manifest -> compiler half and proves the 39 shipped
manifests compile exactly as before apart from the new ``capabilities`` value.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest, load_manifest

_WORKFLOWS_DIR = Path(__file__).resolve().parents[4] / "agents" / "workflows"
_SHIPPED_IDS = sorted(p.parent.name for p in _WORKFLOWS_DIR.glob("*/workflow.yaml"))


def _manifest(**overrides) -> WorkflowManifest:
    """A minimal, well-formed one-step manifest; any field can be overridden."""
    base = dict(
        id="demo",
        steps=[{"agent": "demo-specify", "strategy": "single_shot"}],
        deliverable={"strategy": "single_file", "name": "out.html"},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )
    base.update(overrides)
    return WorkflowManifest(**base)


def test_compile_carries_internet_capability_when_manifest_enables_it() -> None:
    manifest = _manifest(capabilities={"internet": True})

    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())

    assert compiled.capabilities == {"internet": True}


def test_compile_carries_false_internet_capability_when_manifest_disables_it() -> None:
    manifest = _manifest(capabilities={"internet": False})

    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())

    assert compiled.capabilities == {"internet": False}


def test_compile_yields_empty_capabilities_when_manifest_omits_the_block() -> None:
    compiled = WorkflowCompiler().compile(_manifest(), CapabilityRegistry())

    assert compiled.capabilities == {}


def test_compile_copies_capabilities_when_manifest_declares_them() -> None:
    manifest = _manifest(capabilities={"internet": True})

    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    compiled.capabilities["internet"] = False

    assert manifest.capabilities == {"internet": True}


def test_compile_carries_capabilities_when_trust_is_user() -> None:
    # The Composer / inline-launch path compiles at trust="user" or "db"; the block is
    # pure data and must survive every trust level.
    manifest = _manifest(capabilities={"internet": True})

    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")

    assert compiled.capabilities == {"internet": True}


def test_compile_loads_internet_capability_when_yaml_declares_it(
    tmp_path: Path,
) -> None:
    # Real parse path: YAML text -> load_manifest -> compile.
    wf_dir = tmp_path / "caps-demo"
    wf_dir.mkdir()
    (wf_dir / "workflow.yaml").write_text(
        "id: caps-demo\n"
        "planner: skip\n"
        "clarify: {mode: skip, defaults: []}\n"
        "deliverable: {strategy: single_file, name: out.md}\n"
        "capabilities: {internet: true}\n"
        "steps:\n"
        "  - {agent: caps-demo-agent, strategy: single_shot}\n",
        encoding="utf-8",
    )

    manifest = load_manifest("caps-demo", tmp_path)
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())

    assert compiled.capabilities == {"internet": True}


@pytest.mark.parametrize("workflow_id", _SHIPPED_IDS)
def test_compile_changes_only_capabilities_when_shipped_manifest_declares_block(
    workflow_id: str,
) -> None:
    """Shipped behaviour is unchanged: every shipped manifest that declares the block
    sets ``internet: false``, and the compiled plan differs from the block-less compile
    in the ``capabilities`` field alone."""
    manifest = load_manifest(workflow_id, _WORKFLOWS_DIR)
    registry = CapabilityRegistry()

    compiled = WorkflowCompiler().compile(manifest, registry)
    blank = WorkflowCompiler().compile(
        dataclasses.replace(manifest, capabilities={}), registry
    )

    assert compiled.capabilities == dict(manifest.capabilities)
    assert not compiled.capabilities.get("internet", False)
    compiled_rest = dataclasses.asdict(compiled)
    blank_rest = dataclasses.asdict(blank)
    compiled_rest.pop("capabilities")
    blank_rest.pop("capabilities")
    assert compiled_rest == blank_rest


def test_shipped_manifest_set_is_not_empty() -> None:
    assert _SHIPPED_IDS

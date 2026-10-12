"""Spec 021 (backlog) — the ``mechanical: assemble_backlog`` no-model step kind.

Two halves:
  * compile-time — ``WorkflowCompiler`` accepts a declared ``mechanical: "assemble_backlog"``
    step, materializes it onto the compiled ``Step``, and rejects a malformed declaration
    (an unknown kind, or ``mechanical`` paired with a ``tools:`` grant).
  * run-time — ``agents.capabilities.backlog_assemble.MechanicalAssembleBacklogStrategy``
    reads stories/*.json, validates them, renders backlog.md/.csv/.json and build/coverage.json,
    and raises ``AssembleBacklogFailed`` when coverage is below the threshold.
"""

from __future__ import annotations

import json

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.capabilities.backlog_assemble import (
    AssembleBacklogFailed,
    MechanicalAssembleBacklogStrategy,
)
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest
from app.agents.sandbox import RunSandbox


# ===========================================================================
# Compile-time: mechanical: assemble_backlog
# ===========================================================================


def _manifest_one_step(step: dict) -> WorkflowManifest:
    return WorkflowManifest(
        id="stories-test",
        steps=[step],
        deliverable={"strategy": "single_file", "name": "backlog.md"},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def test_mechanical_assemble_backlog_compiles_and_is_materialized_on_the_step():
    manifest = _manifest_one_step({
        "agent": "custom-agent",
        "instance_id": "assemble",
        "mechanical": "assemble_backlog",
    })
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].mechanical == "assemble_backlog"


def test_mechanical_absent_defaults_to_none():
    manifest = _manifest_one_step({"agent": "step-x"})
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].mechanical is None


def test_unknown_mechanical_kind_raises():
    manifest = _manifest_one_step({"agent": "step-x", "mechanical": "teleport"})
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert "teleport" in str(exc.value)


def test_mechanical_with_tools_grant_raises():
    """A mechanical step runs no agent — a tools: grant has nothing to bind to."""
    manifest = _manifest_one_step({
        "agent": "step-x",
        "mechanical": "assemble_backlog",
        "tools": {"read_files": True},
    })
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert "tools" in str(exc.value)


def test_mechanical_with_validators_is_allowed():
    """validators: is explicitly meaningful on an assemble step (the deliverable files
    are checked) — must NOT be rejected."""
    manifest = _manifest_one_step({
        "agent": "step-x",
        "mechanical": "assemble_backlog",
        "validators": ["html_static"],
    })
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].mechanical == "assemble_backlog"
    assert compiled.steps[0].validators == ["html_static"]


def test_mechanical_with_human_gate_is_allowed():
    """gates: is explicitly meaningful on an assemble step (review before delivery)
    — must NOT be rejected."""
    manifest = _manifest_one_step({
        "agent": "step-x",
        "mechanical": "assemble_backlog",
        "gates": ["human"],
    })
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].gates == ["human"]


# ===========================================================================
# Run-time: MechanicalAssembleBacklogStrategy basic construction
# ===========================================================================


class _Deliverable:
    def __init__(self, name: str = "backlog.md") -> None:
        self.name = name


class _FakeRunner:
    def __init__(self, sandbox) -> None:
        self.sandbox = sandbox


class _Ctx:
    def __init__(self, runner, deliverable) -> None:
        self.runner = runner
        self.deliverable = deliverable


@pytest.fixture
def sandbox(tmp_path):
    return RunSandbox("tester", "run-assemble-stories", runs_root=str(tmp_path))


def test_strategy_constructs_with_required_args(sandbox):
    """The strategy should construct without error."""
    spec = {"id": "test-spec"}
    strategy = MechanicalAssembleBacklogStrategy(
        spec=spec,
        index=0,
        total=1,
        results={},
    )
    assert strategy is not None


@pytest.mark.asyncio
async def test_strategy_raises_on_missing_input_files(sandbox):
    """When required input files are absent, strategy should raise AssembleBacklogFailed."""
    class _Spec:
        id = "us-assemble"
        name = "Assemble"
        role = "Assembler"
        icon = "🧩"

    ctx = _Ctx(_FakeRunner(sandbox), _Deliverable())
    strategy = MechanicalAssembleBacklogStrategy(
        spec=_Spec(),
        index=0,
        total=1,
        results=[],
    )
    # The strategy.run() is an async generator that emits events and raises
    # AssembleBacklogFailed when required files are missing
    with pytest.raises(AssembleBacklogFailed):
        async for event in strategy.run(step=None, ctx=ctx):
            pass

"""T39 — Compiler validation tests for conditional route trigger_max_depth (R-19).

Tests:
  - R-19-clarified: trigger_max_depth is FIXED at 5 in v1; any other declared value
    is rejected by WorkflowCompiler.compile() with CompilerError.
  - Positive case: trigger_max_depth: 5 (or omitted, relying on the default) compiles
    without error.

Audit finding: the compiler-side rejection of trigger_max_depth != 5 WAS implemented
correctly (compiler.py ~lines 1171-1174, `if trigger_max_depth != 5: raise ...`), but it
had NO test file anywhere in backend/tests/ asserting it — a future edit weakening or
removing the != 5 check would go undetected.
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest


def _minimal_conditional_manifest(
    trigger_max_depth: int | None = None,
) -> WorkflowManifest:
    """A minimal manifest with a conditional gate (route block).

    If trigger_max_depth is provided, it is declared in the route block;
    otherwise, the key is omitted (relying on the compiler's default of 5).
    """
    main_step: dict = {
        "agent": "conditional-test-agent",
        "strategy": "single_shot",
        "produces": ["route_decision"],
        "gates": ["conditional"],
        "route": {
            "outcomes": {
                "branch_a": {"trigger": "step", "target": "step-a-agent"},
                "branch_b": {"trigger": "step", "target": "step-b-agent"},
            },
        },
    }

    # Add trigger_max_depth if explicitly provided (even if None was passed,
    # only add it if not None).
    if trigger_max_depth is not None:
        main_step["route"]["trigger_max_depth"] = trigger_max_depth

    # Define the target steps referenced in the route outcomes.
    step_a: dict = {
        "agent": "step-a-agent",
        "strategy": "single_shot",
    }
    step_b: dict = {
        "agent": "step-b-agent",
        "strategy": "single_shot",
    }

    return WorkflowManifest(
        id="conditional-route-test",
        steps=[main_step, step_a, step_b],
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def test_route_trigger_max_depth_5_compiles_successfully():
    """Positive case: trigger_max_depth: 5 compiles without error (R-19)."""
    manifest = _minimal_conditional_manifest(trigger_max_depth=5)
    # Should not raise.
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    # Verify the compiled route spec has the correct value.
    assert compiled.steps[0].route is not None
    assert compiled.steps[0].route.trigger_max_depth == 5


def test_route_trigger_max_depth_omitted_compiles_successfully():
    """Positive case: omitting trigger_max_depth uses the default (5) and compiles (R-19)."""
    manifest = _minimal_conditional_manifest(trigger_max_depth=None)
    # Should not raise.
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    # Verify the compiled route spec has the default value.
    assert compiled.steps[0].route is not None
    assert compiled.steps[0].route.trigger_max_depth == 5


def test_route_trigger_max_depth_6_raises_compiler_error():
    """Negative case: trigger_max_depth: 6 raises CompilerError with message referencing the field (R-19)."""
    manifest = _minimal_conditional_manifest(trigger_max_depth=6)
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())

    msg = str(exc.value)
    # Assert the message references trigger_max_depth so the author can locate the issue.
    assert "trigger_max_depth" in msg
    # Assert the message explains the constraint.
    assert "5" in msg


def test_route_trigger_max_depth_4_raises_compiler_error():
    """Negative case: trigger_max_depth: 4 also raises CompilerError (R-19 requires exactly 5)."""
    manifest = _minimal_conditional_manifest(trigger_max_depth=4)
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())

    msg = str(exc.value)
    assert "trigger_max_depth" in msg
    assert "5" in msg


def test_route_trigger_max_depth_0_raises_compiler_error():
    """Negative case: trigger_max_depth: 0 raises CompilerError."""
    manifest = _minimal_conditional_manifest(trigger_max_depth=0)
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())

    msg = str(exc.value)
    assert "trigger_max_depth" in msg


def test_route_trigger_max_depth_10_raises_compiler_error():
    """Negative case: trigger_max_depth: 10 raises CompilerError (large value rejected)."""
    manifest = _minimal_conditional_manifest(trigger_max_depth=10)
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())

    msg = str(exc.value)
    assert "trigger_max_depth" in msg

"""Test on_loop_exhausted flag for conditional gates with exhausted loop caps.

When a conditional gate's loop_max_iterations is exhausted, the default behavior
(on_loop_exhausted="continue") suppresses the jump and falls through to the next
step. With on_loop_exhausted="fail", the run terminates via BudgetExceeded
instead, which is useful for gates with no default_next: they fail closed when
they run out of retries instead of presenting a build the inspector just rejected.

Tests:
  1. Compiler: on_loop_exhausted accepts "continue" and "fail"; rejects invalid values
  2. Engine (fail mode): loop cap exhaustion raises BudgetExceeded, run fails
  3. Engine (default mode): loop cap exhaustion falls through (existing behavior)
"""

from __future__ import annotations

import copy
import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest
from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive


# =============================================================================
# COMPILER TESTS
# =============================================================================


def _minimal_conditional_manifest_with_on_loop_exhausted(
    on_loop_exhausted: str | None = None,
) -> WorkflowManifest:
    """A minimal manifest with a conditional gate (route block).

    If on_loop_exhausted is provided, it is declared in the route block;
    otherwise, the key is omitted (relying on the compiler's default of "continue").
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

    # Add on_loop_exhausted if explicitly provided.
    if on_loop_exhausted is not None:
        main_step["route"]["on_loop_exhausted"] = on_loop_exhausted

    step_a: dict = {
        "agent": "step-a-agent",
        "strategy": "single_shot",
    }
    step_b: dict = {
        "agent": "step-b-agent",
        "strategy": "single_shot",
    }

    return WorkflowManifest(
        id="conditional-on-loop-exhausted-test",
        steps=[main_step, step_a, step_b],
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


class TestOnLoopExhaustedCompiler:
    """Compiler validation for on_loop_exhausted field."""

    def test_on_loop_exhausted_fail_compiles_successfully(self):
        """Positive case: on_loop_exhausted: fail compiles without error."""
        manifest = _minimal_conditional_manifest_with_on_loop_exhausted(on_loop_exhausted="fail")
        compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
        assert compiled.steps[0].route is not None
        assert compiled.steps[0].route.on_loop_exhausted == "fail"

    def test_on_loop_exhausted_continue_compiles_successfully(self):
        """Positive case: on_loop_exhausted: continue compiles without error."""
        manifest = _minimal_conditional_manifest_with_on_loop_exhausted(on_loop_exhausted="continue")
        compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
        assert compiled.steps[0].route is not None
        assert compiled.steps[0].route.on_loop_exhausted == "continue"

    def test_on_loop_exhausted_omitted_uses_default(self):
        """Positive case: omitting on_loop_exhausted uses the default ("continue")."""
        manifest = _minimal_conditional_manifest_with_on_loop_exhausted(on_loop_exhausted=None)
        compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
        assert compiled.steps[0].route is not None
        assert compiled.steps[0].route.on_loop_exhausted == "continue"

    def test_on_loop_exhausted_invalid_value_raises_compiler_error(self):
        """Negative case: on_loop_exhausted: banana raises CompilerError."""
        manifest = _minimal_conditional_manifest_with_on_loop_exhausted(on_loop_exhausted="banana")
        with pytest.raises(CompilerError) as exc:
            WorkflowCompiler().compile(manifest, CapabilityRegistry())

        msg = str(exc.value)
        assert "on_loop_exhausted" in msg
        assert "banana" in msg
        assert "continue" in msg or "fail" in msg


# =============================================================================
# ENGINE TESTS
# =============================================================================


_PIPELINE = "ex_A1_loop"


def _always_retry_scripts_for(agent_id: str) -> list[_ScriptedTurn]:
    """``check`` ALWAYS returns {"decision": "retry"} to exhaust the loop cap."""
    if agent_id == "custom-agent:check":
        return [_ScriptedTurn(texts=['{"decision": "retry"}'], usage=(5, 3))]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.mark.asyncio
async def test_loop_exhausted_fail_raises_budget_exceeded():
    """Engine: when on_loop_exhausted=fail and loop cap is exhausted, run fails."""
    # Set up scripts: check always retries (trips the cap)
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _always_retry_scripts_for

    try:
        # Drive ex_A1_loop and force on_loop_exhausted="fail" by monkeypatching
        # the compiled plan BEFORE the engine reads it
        orig_compile_for_run = __import__(
            "agents.execution_engine.engine", fromlist=["compile_for_run"]
        ).compile_for_run

        def _patched_compile_for_run_fail(pipeline_type):
            compiled = copy.deepcopy(orig_compile_for_run(pipeline_type))
            # Find the check step and set on_loop_exhausted=fail
            for step in compiled.steps:
                if "check" in step.id:
                    if step.route is not None:
                        step.route.on_loop_exhausted = "fail"
                    break
            return compiled

        import agents.execution_engine.engine as engine_mod
        engine_mod.compile_for_run = _patched_compile_for_run_fail

        events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for
        import agents.execution_engine.engine as engine_mod
        engine_mod.compile_for_run = orig_compile_for_run

    assert events, f"{_PIPELINE} produced no events"

    types = [e.get("type") for e in events]
    budget_events = [e for e in events if e.get("type") == "budget_aborted"]
    pipeline_failed = [e for e in events if e.get("type") == "pipeline_failed"]
    pipeline_complete = [e for e in events if e.get("type") == "pipeline_complete"]

    # With on_loop_exhausted=fail, we expect:
    # - exactly one budget_aborted event with dimension="loop_iterations"
    # - exactly one pipeline_failed event
    # - no pipeline_complete event
    # - no agent_start for "custom-agent:done" (the step after the gate)

    assert len(budget_events) == 1, (
        f"expected exactly one budget_aborted, got {len(budget_events)}. "
        f"Events: {types}"
    )
    budget_event = budget_events[0]
    assert budget_event["data"]["dimension"] == "loop_iterations"
    assert "on_loop_exhausted=fail" in budget_event["data"]["message"]

    assert len(pipeline_failed) == 1, (
        f"expected exactly one pipeline_failed, got {len(pipeline_failed)}. "
        f"Events: {types}"
    )

    assert len(pipeline_complete) == 0, (
        f"expected no pipeline_complete with on_loop_exhausted=fail, "
        f"got {len(pipeline_complete)}. Events: {types}"
    )

    # Verify done step was never started (it comes after the gate that failed)
    done_starts = [e for e in events if e.get("type") == "agent_start" and "done" in str(e)]
    assert len(done_starts) == 0, (
        f"expected no agent_start for done step, got {done_starts}"
    )


@pytest.mark.asyncio
async def test_loop_exhausted_continue_falls_through():
    """Engine: default behavior (on_loop_exhausted=continue) falls through."""
    # Set up scripts: check always retries (trips the cap)
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _always_retry_scripts_for

    try:
        events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for

    assert events, f"{_PIPELINE} produced no events"

    types = [e.get("type") for e in events]
    budget_events = [e for e in events if e.get("type") == "budget_aborted"]
    pipeline_complete = [e for e in events if e.get("type") == "pipeline_complete"]
    pipeline_failed = [e for e in events if e.get("type") == "pipeline_failed"]

    # With default on_loop_exhausted=continue, we expect:
    # - exactly one budget_aborted event (the convergence warning)
    # - the message should NOT mention on_loop_exhausted=fail
    # - the run should complete (either pipeline_complete or have degraded status)
    # - no pipeline_failed

    assert len(budget_events) == 1, (
        f"expected exactly one budget_aborted, got {len(budget_events)}. "
        f"Events: {types}"
    )
    budget_event = budget_events[0]
    assert budget_event["data"]["dimension"] == "loop_iterations"
    # The message should end with "continuing forward", not "on_loop_exhausted=fail"
    assert "continuing forward" in budget_event["data"]["message"]
    assert "on_loop_exhausted=fail" not in budget_event["data"]["message"]

    # Default behavior completes the pipeline (possibly with degraded status)
    assert len(pipeline_complete) == 1, (
        f"expected pipeline_complete with default on_loop_exhausted, "
        f"got {len(pipeline_complete)}. Events: {types}"
    )

    # No pipeline_failed when using default (continue) mode
    assert len(pipeline_failed) == 0, (
        f"expected no pipeline_failed with default on_loop_exhausted, "
        f"got {len(pipeline_failed)}. Events: {types}"
    )

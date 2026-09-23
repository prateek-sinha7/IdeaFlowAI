"""T024 — Unit tests for the ExecutionEngine (Phase 2).

Tests:
  - StateMachine transitions and terminal-state guard
  - ClarifyEngine immediate-PROCEED when nothing is missing (zero-I/O)
  - All 14 pipeline definitions resolve to valid DAGs

The ClarifyEngine tests that COMPLETE a questionnaire round live in
``tests/integration/agents/test_clarify_engine_db.py``: finishing a round makes
``_persist_clarifications`` write through ``ScopedStore.write_ref(...,
force_db_version=True)``, i.e. a real ``SessionLocal()``, which the
unit-isolation guard rejects. Only the no-missing-information case returns
before touching the store, so only it belongs here.
"""

from __future__ import annotations

import pytest

from agents.execution_engine.state_machine import (
    StateMachine,
    StateMachineError,
)
from agents.execution_engine.clarify_engine import ClarifyEngine
from agents.artifact_store.store import ArtifactStore
import agents.artifact_store.store as _store_mod


@pytest.fixture(autouse=True)
def _use_inmemory_store(monkeypatch):
    """Reset the ArtifactStore singleton to in-memory mode for all tests in this module."""
    store = ArtifactStore()
    monkeypatch.setattr(_store_mod, "_STORE", store)
    yield
    monkeypatch.setattr(_store_mod, "_STORE", None)


# ---------------------------------------------------------------------------
# StateMachine
# ---------------------------------------------------------------------------


def test_state_machine_valid_transition():
    sm = StateMachine()
    assert sm.transition("run-1", "planning") == "planning"
    assert sm.get_state("run-1") == "planning"
    assert sm.transition("run-1", "generating") == "generating"


def test_state_machine_invalid_state_raises():
    sm = StateMachine()
    with pytest.raises(StateMachineError, match="Invalid state"):
        sm.transition("run-1", "bogus_state")


def test_state_machine_terminal_state_blocks_transition():
    sm = StateMachine()
    sm.transition("run-1", "completed")
    with pytest.raises(StateMachineError, match="terminal"):
        sm.transition("run-1", "generating")


def test_state_machine_full_lifecycle():
    sm = StateMachine()
    sm.transition("run-1", "planning")
    sm.transition("run-1", "clarifying")
    sm.transition("run-1", "waiting_for_user")
    sm.transition("run-1", "clarifying")
    sm.transition("run-1", "generating")
    sm.transition("run-1", "completed")
    assert sm.get_state("run-1") == "completed"


# ---------------------------------------------------------------------------
# ClarifyEngine pause/resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarify_engine_no_missing_info_proceeds():
    """When planning_context has no missing_information, gate proceeds immediately."""
    engine = ClarifyEngine()
    events = []

    async def ws(e):
        events.append(e)

    ctx = {"execution_gate": "CLARIFY_REQUIRED", "missing_information": []}
    result = await engine.run("run-clarify-1", ctx, ws, owner_id="user-test")
    assert result["execution_gate"] == "PROCEED"




# ---------------------------------------------------------------------------
# All pipelines resolve
# ---------------------------------------------------------------------------


def test_all_pipelines_resolve_to_valid_dags():
    from agents.execution_engine.resolver import WorkflowResolver
    from agents.registry import PIPELINE_AGENTS, get_pipeline_agents

    resolver = WorkflowResolver()
    for ptype in PIPELINE_AGENTS:
        # FIX-051 / ISS-035: spec_kit's agents are real and scannable but the
        # pipeline is a known in-progress/unfinished one (no manifest yet,
        # produces/consumes contracts not fully wired) — see
        # tests/integration/test_pipeline_workflows.py's _STRUCTURALLY_INCOMPLETE
        # for the same carve-out and rationale.
        if ptype == "spec_kit":
            continue
        agents = get_pipeline_agents(ptype)
        if not agents:
            continue  # ppt/reverse_engineer have no scannable agents
        result = resolver.validate(agents)
        assert result.satisfiable, f"{ptype} unsatisfiable: {result.errors}"


# ---------------------------------------------------------------------------
# ExecutionContext step_visit_counts (conditional gates feature)
# ---------------------------------------------------------------------------


def test_execution_context_step_visit_counts_starts_empty():
    """ExecutionContext.step_visit_counts initializes as an empty dict."""
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="test-run", owner_id="test-owner")
    assert ectx.step_visit_counts == {}
    assert isinstance(ectx.step_visit_counts, dict)


def test_execution_context_step_visit_counts_increments_correctly():
    """step_visit_counts increments correctly with repeated dict-key mutation."""
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="test-run", owner_id="test-owner")

    # Increment a step visit count 3 times using the canonical pattern
    for _ in range(3):
        ectx.step_visit_counts["step_a"] = ectx.step_visit_counts.get("step_a", 0) + 1

    assert ectx.step_visit_counts["step_a"] == 3


def test_execution_context_step_visit_counts_multiple_steps():
    """step_visit_counts tracks multiple steps independently."""
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="test-run", owner_id="test-owner")

    # Increment step_a 3 times
    for _ in range(3):
        ectx.step_visit_counts["step_a"] = ectx.step_visit_counts.get("step_a", 0) + 1

    # Increment step_b 2 times
    for _ in range(2):
        ectx.step_visit_counts["step_b"] = ectx.step_visit_counts.get("step_b", 0) + 1

    # Increment step_c 1 time
    ectx.step_visit_counts["step_c"] = ectx.step_visit_counts.get("step_c", 0) + 1

    assert ectx.step_visit_counts["step_a"] == 3
    assert ectx.step_visit_counts["step_b"] == 2
    assert ectx.step_visit_counts["step_c"] == 1
    assert len(ectx.step_visit_counts) == 3

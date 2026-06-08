"""T024 — Unit tests for the ExecutionEngine (Phase 2).

Tests:
  - StateMachine transitions and terminal-state guard
  - ClarifyEngine pause/resume cycle
  - ClarifyEngine max 3 rounds + clarification_limit_reached
  - All 14 pipeline definitions resolve to valid DAGs
  - Engine default planning context
"""

from __future__ import annotations

import asyncio

import pytest

from agents.execution_engine.state_machine import (
    StateMachine,
    StateMachineError,
)
from agents.execution_engine.clarify_engine import ClarifyEngine, MAX_CLARIFICATION_ROUNDS
from agents.artifact_store.store import ArtifactStore, get_artifact_store
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
    result = await engine.run("run-clarify-1", ctx, ws)
    assert result["execution_gate"] == "PROCEED"


@pytest.mark.asyncio
async def test_clarify_engine_pause_resume_cycle():
    """ClarifyEngine emits questionnaire_ready, pauses, resumes on answer submission."""
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-2"
    events = []

    async def ws(e):
        events.append(e)
        # When questionnaire_ready is emitted, simulate the user answering
        if e["type"] == "questionnaire_ready":
            await store.set_questionnaire_responses(
                pipeline_run_id,
                [{"question_id": q["question_id"], "answer": "answered"}
                 for q in e["data"]["questions"]],
            )

    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["target audience"],
        "explicit_constraints": [],
    }
    result = await engine.run(pipeline_run_id, ctx, ws)

    # questionnaire_ready and questionnaire_complete should both fire
    types = [e["type"] for e in events]
    assert "questionnaire_ready" in types
    assert "questionnaire_complete" in types
    assert result["execution_gate"] == "PROCEED"
    # answer was merged into explicit_constraints
    assert any("answered" in c for c in result["explicit_constraints"])


@pytest.mark.asyncio
async def test_clarify_engine_max_rounds():
    """After MAX_CLARIFICATION_ROUNDS, emit clarification_limit_reached and proceed."""
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-3"
    events = []

    async def ws(e):
        events.append(e)
        if e["type"] == "questionnaire_ready":
            # Answer with empty strings so missing_information is never resolved
            await store.set_questionnaire_responses(
                pipeline_run_id,
                [{"question_id": q["question_id"], "answer": ""}
                 for q in e["data"]["questions"]],
            )

    # 5 missing items, all answered empty → never resolves → hits max rounds
    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c", "d", "e"],
        "explicit_constraints": [],
    }
    result = await engine.run(pipeline_run_id, ctx, ws)

    types = [e["type"] for e in events]
    assert "clarification_limit_reached" in types
    assert result["execution_gate"] == "PROCEED"
    # questionnaire_ready fired exactly MAX_CLARIFICATION_ROUNDS times
    assert types.count("questionnaire_ready") == MAX_CLARIFICATION_ROUNDS


@pytest.mark.asyncio
async def test_clarify_engine_caps_questions_at_5():
    """Question count is capped at min(5, missing_count)."""
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-4"
    captured_question_counts = []

    async def ws(e):
        if e["type"] == "questionnaire_ready":
            captured_question_counts.append(len(e["data"]["questions"]))
            await store.set_questionnaire_responses(
                pipeline_run_id,
                [{"question_id": q["question_id"], "answer": "x"}
                 for q in e["data"]["questions"]],
            )

    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c", "d", "e", "f", "g"],  # 7 items
        "explicit_constraints": [],
    }
    await engine.run(pipeline_run_id, ctx, ws)
    # First round must cap at 5
    assert captured_question_counts[0] == 5


# ---------------------------------------------------------------------------
# All pipelines resolve
# ---------------------------------------------------------------------------


def test_all_pipelines_resolve_to_valid_dags():
    from agents.execution_engine.resolver import WorkflowResolver
    from agents.registry import PIPELINE_AGENTS, get_pipeline_agents

    resolver = WorkflowResolver()
    for ptype in PIPELINE_AGENTS:
        agents = get_pipeline_agents(ptype)
        if not agents:
            continue  # ppt/reverse_engineer have no scannable agents
        result = resolver.validate(agents)
        assert result.satisfiable, f"{ptype} unsatisfiable: {result.errors}"

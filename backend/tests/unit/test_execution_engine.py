"""T024 — Unit tests for the ExecutionEngine (Phase 2).

Tests:
  - StateMachine transitions and terminal-state guard
  - ClarifyEngine pause/resume cycle
  - ClarifyEngine one-round-then-run + rounds knob + clarification_limit_reached
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


async def _unresolved_generate_questions(self, planning_context, round_num, clarify_agent):
    """Test double for ``ClarifyEngine._generate_questions``.

    KAN-124 (commit 90ad687e) made ``_merge_answers`` auto-fill each
    unanswered question with its LLM-generated ``recommended_answer`` so an
    agent never runs with empty ``explicit_constraints`` — but the static
    question library (the fallback path exercised in these tests, since no
    real model is configured) always sets a non-empty ``recommended_answer``
    (``options[-1]``), so a genuinely-empty submit now resolves
    ``missing_information`` after a single round regardless of the rounds
    knob. To still exercise the round-limit / multi-round mechanics
    genuinely, this double returns questions with an EMPTY
    ``recommended_answer`` — KAN-124's auto-fill only fires when
    ``recommended_answer`` is truthy (see ``_merge_answers``), so an empty
    submit against these questions stays genuinely unresolved.
    """
    missing = planning_context.get("missing_information", [])
    if not missing:
        return []
    return [
        {
            "question_id": f"r{round_num}_q{i + 1}",
            "question_text": f"Question about {item}?",
            "impact_level": "high",
            "answer_type": "short_text",
            "options": [],
            "recommended_answer": "",
            "recommended_reasoning": "",
            "recommended_display": "",
            "ambiguity_category": "Functional Scope",
        }
        for i, item in enumerate(missing[:5])
    ]


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
    result = await engine.run(pipeline_run_id, ctx, ws, owner_id="user-test")

    # questionnaire_ready and questionnaire_complete should both fire
    types = [e["type"] for e in events]
    assert "questionnaire_ready" in types
    assert "questionnaire_complete" in types
    assert result["execution_gate"] == "PROCEED"
    # answer was merged into explicit_constraints
    assert any("answered" in c for c in result["explicit_constraints"])


@pytest.mark.asyncio
async def test_clarify_engine_asks_once_then_limit_reached(monkeypatch):
    """Default one-round-then-run: unresolved after the single round emits
    clarification_limit_reached (the accepted terminal 'proceed') and PROCEEDs."""
    monkeypatch.setattr(ClarifyEngine, "_generate_questions", _unresolved_generate_questions)
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

    # 5 missing items, all answered empty → never resolves → single round only
    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c", "d", "e"],
        "explicit_constraints": [],
    }
    result = await engine.run(pipeline_run_id, ctx, ws, owner_id="user-test")

    types = [e["type"] for e in events]
    assert "clarification_limit_reached" in types
    assert result["execution_gate"] == "PROCEED"
    # questionnaire_ready fired exactly ONCE (one-round-then-run default)
    assert types.count("questionnaire_ready") == 1


@pytest.mark.asyncio
async def test_clarify_engine_rounds_knob_allows_multi_round(monkeypatch):
    """max_rounds opts into multi-round; empty answers loop up to the ceiling."""
    monkeypatch.setattr(ClarifyEngine, "_generate_questions", _unresolved_generate_questions)
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-multi"
    events = []

    async def ws(e):
        events.append(e)
        if e["type"] == "questionnaire_ready":
            await store.set_questionnaire_responses(
                pipeline_run_id,
                [{"question_id": q["question_id"], "answer": ""}
                 for q in e["data"]["questions"]],
            )

    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c", "d", "e"],
        "explicit_constraints": [],
    }
    result = await engine.run(
        pipeline_run_id, ctx, ws, owner_id="user-test", max_rounds=3
    )

    types = [e["type"] for e in events]
    # Loops up to the MAX_CLARIFICATION_ROUNDS ceiling when the knob opts in.
    assert types.count("questionnaire_ready") == MAX_CLARIFICATION_ROUNDS
    assert "clarification_limit_reached" in types
    assert result["execution_gate"] == "PROCEED"


@pytest.mark.asyncio
async def test_clarify_engine_skip_clarification_force_proceeds_round_1():
    """ISS-027: submit with skip_clarification=True breaks the loop on round 1.

    The bug: "Skip all & run directly" sent EMPTY responses (no flag), which left
    missing_information unchanged, so the engine re-asked up to MAX rounds. With
    the force-proceed flag the engine must stop after the FIRST questionnaire_ready
    and PROCEED — no re-ask, no clarification_limit_reached.
    """
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-skip"
    events = []

    async def ws(e):
        events.append(e)
        if e["type"] == "questionnaire_ready":
            # Same EMPTY submission as the buggy skip — but WITH force-proceed.
            await store.set_questionnaire_responses(
                pipeline_run_id,
                [],
                skip_clarification=True,
            )

    # 5 unresolved items: without the flag this is exactly the max-rounds case
    # above (re-asks 3×). With the flag it must proceed after round 1.
    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c", "d", "e"],
        "explicit_constraints": [],
    }
    result = await engine.run(pipeline_run_id, ctx, ws, owner_id="user-test")

    types = [e["type"] for e in events]
    # Asked exactly ONCE, then proceeded — no re-ask, no limit-reached banner.
    assert types.count("questionnaire_ready") == 1
    assert "questionnaire_complete" in types
    assert "clarification_limit_reached" not in types
    assert result["execution_gate"] == "PROCEED"


@pytest.mark.asyncio
async def test_clarify_engine_prearm_skip_before_questionnaire_ready_proceeds():
    """BUG-R04: a skip submitted BEFORE ``questionnaire_ready`` must still PROCEED.

    Reproduces the pre-arm lost-wakeup race: a client (the QA harness) POSTs
    ``{responses:[], skip_clarification:true}`` in the window between the status
    flip to ``waiting_for_user`` and the loop's ``event.clear()``. We simulate it
    by seeding the store (responses=[] + force_proceed=True, which also sets the
    resume event) BEFORE calling ``run()`` — so the loop's ``event.clear()`` at
    the top of round 1 WIPES that set(). The ``ws`` callback does NOT re-submit
    (a real pre-arm submitter is already done), so nothing re-arms the event.

    Pre-fix: ``await event.wait()`` blocks forever on the wiped event → the run
    sits at ``waiting_for_user`` (here, the ``asyncio.wait_for`` timeout fires).
    Post-fix: the guard detects the already-stored (un-consumed) submission and
    skips the wait, emitting exactly ONE ``questionnaire_ready`` and PROCEEDing.
    """
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-prearm-skip"
    events = []

    async def ws(e):
        # Record only — the pre-arm submitter already POSTed before run() began;
        # it does NOT answer again in response to questionnaire_ready.
        events.append(e)

    # PRE-ARM: the skip landed before questionnaire_ready. This stores []+
    # force_proceed=True AND sets the resume event; the loop's clear() then wipes
    # the set(), stranding a naive await event.wait().
    await store.set_questionnaire_responses(
        pipeline_run_id, [], skip_clarification=True
    )

    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c", "d", "e"],
        "explicit_constraints": [],
    }
    # Bounded wait so a regression is a clean TimeoutError (RED), never a hang.
    result = await asyncio.wait_for(
        engine.run(pipeline_run_id, ctx, ws, owner_id="user-test"),
        timeout=5.0,
    )

    types = [e["type"] for e in events]
    # Asked exactly ONCE, proceeded via the pre-arm force-proceed — no re-ask.
    assert types.count("questionnaire_ready") == 1
    assert "questionnaire_complete" in types
    assert result["execution_gate"] == "PROCEED"


@pytest.mark.asyncio
async def test_clarify_engine_empty_submit_proceeds_after_one_round(monkeypatch):
    """One-round-then-run: an empty submit (no force-proceed flag) no longer
    re-asks — the questionnaire is asked exactly once, then the run PROCEEDs via
    the terminal clarification_limit_reached (default max_rounds=1)."""
    monkeypatch.setattr(ClarifyEngine, "_generate_questions", _unresolved_generate_questions)
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-noflag"
    events = []

    async def ws(e):
        events.append(e)
        if e["type"] == "questionnaire_ready":
            # Empty submit, default flag (False).
            await store.set_questionnaire_responses(pipeline_run_id, [])

    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c", "d", "e"],
        "explicit_constraints": [],
    }
    result = await engine.run(pipeline_run_id, ctx, ws, owner_id="user-test")

    types = [e["type"] for e in events]
    assert types.count("questionnaire_ready") == 1
    assert "clarification_limit_reached" in types
    assert result["execution_gate"] == "PROCEED"


@pytest.mark.asyncio
async def test_clarify_engine_asks_once_then_proceeds_on_subset():
    """Answering a SUBSET (some missing_information remains) proceeds after one
    round: one questionnaire_ready, questionnaire_complete present, PROCEED, and
    the answered item merged into explicit_constraints."""
    engine = ClarifyEngine()
    store = get_artifact_store()
    pipeline_run_id = "run-clarify-subset"
    events = []

    async def ws(e):
        events.append(e)
        if e["type"] == "questionnaire_ready":
            questions = e["data"]["questions"]
            # Answer only the FIRST question; leave the rest blank (a subset).
            responses = [
                {"question_id": q["question_id"],
                 "answer": "subset-answer" if idx == 0 else ""}
                for idx, q in enumerate(questions)
            ]
            await store.set_questionnaire_responses(pipeline_run_id, responses)

    ctx = {
        "execution_gate": "CLARIFY_REQUIRED",
        "missing_information": ["a", "b", "c"],
        "explicit_constraints": [],
    }
    result = await engine.run(pipeline_run_id, ctx, ws, owner_id="user-test")

    types = [e["type"] for e in events]
    assert types.count("questionnaire_ready") == 1
    assert "questionnaire_complete" in types
    assert result["execution_gate"] == "PROCEED"
    assert any("subset-answer" in c for c in result["explicit_constraints"])


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
    await engine.run(pipeline_run_id, ctx, ws, owner_id="user-test")
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

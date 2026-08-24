"""T26 (spec 014 / Phase 3 dispatch loop): ``ex_A4_human_gate`` (A4, the
human-gate-as-condition-source fixture) driven end-to-end, proving R-05's claim that a
conditional gate's decision source ``condition_agent`` "may name an EARLIER step,
including one whose gate is `human` — reads that gate's captured response the same way."

Fixture shape (``agents/workflows/ex_A4_human_gate/workflow.yaml``):

    1. greet (writes draft.txt)
    2. review        gates:[human], produces:[route_decision]  — PAUSES for input
    3. revise-check   gates:[conditional], produces:[route_decision]
                      route.condition_agent: review   (NOT itself)
                      route.outcomes: continue -> {step, done} | revise -> {step, greet}
    4. done (terminal)

Two scripted passes:

  * ``test_revise_outcome_loops_back_to_greet`` — review's ONE scripted turn answers
    ``{"decision": "revise"}``. ``revise-check`` never emits a decision of its own
    (its scripted turn is an EMPTY string — never valid decision JSON), so a
    successful route can ONLY have come from reading ``review``'s captured content.
    Asserts: after ``revise-check`` evaluates, ``greet`` is dispatched a SECOND time
    (the loop-back cursor jump) and ``done`` never runs.

  * ``test_continue_outcome_advances_to_done`` — review's ONE scripted turn answers
    ``{"decision": "continue"}``. Asserts: ``done`` runs, ``greet`` runs exactly
    ONCE (no loop-back), and the run reaches ``pipeline_complete``.

Human-gate scripting mechanism: the SAME one the repo's existing declared-gate tests
use (``tests/agents/test_declared_gate_streaming.py``) — drive ``engine.execute()``
by hand, and on each ``review_gate_ready`` call
``engine._store.set_review_response(gate_key, approved=True)`` (the same call
``websocket.py``'s ``approve_review`` handler makes). ``_drive()`` is NOT used here:
it passes ``gate_agent_ids=[]``, which the WR-02 dedupe in ``_evaluate_gates``
treats as "skip every declared human gate" — that would bypass the human gate
entirely rather than exercising a scripted response through it.

review's own per-call decision (revise vs continue) is supplied by locally
monkeypatching ``_scripted_model._scripts_for`` for the duration of each test
(restored in ``finally``) — the same recipe ``test_conditional_loop_budget_t24.py``
documents for a step needing a decision the shared per-agent-id registry has no
static branch for.

No live LLM: fully scripted offline (``ScriptedFakeChatModel``).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _RUNS_ROOT, ScriptedFakeChatModel, _ScriptedTurn

_PIPELINE = "ex_A4_human_gate"
_EVENT_TIMEOUT_S = 30.0


def _scripts_for(review_decision: str):
    """Build a ``_scripts_for`` override: review answers ``review_decision`` (its
    ONE call); revise-check's own output is EMPTY (never valid decision JSON, so a
    successful route can only have come from reading review's captured content);
    everything else is inert.
    """

    def _fn(agent_id: str) -> list[_ScriptedTurn]:
        if agent_id == "custom-agent:review":
            return [_ScriptedTurn(texts=[f'{{"decision": "{review_decision}"}}'], usage=(5, 3))]
        if agent_id == "custom-agent:revise-check":
            return [_ScriptedTurn(texts=[""], usage=(1, 1))]
        return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]

    return _fn


async def _run_pipeline(review_decision: str, *, stop_when) -> list[dict]:
    """Drive ``engine.execute()`` by hand (real declared human-gate pause/approve —
    the ``test_declared_gate_streaming.py`` recipe), approving every
    ``review_gate_ready`` as it arrives. Returns every event observed once
    ``stop_when(events)`` first returns True (checked after each event, including
    after an approval is sent) or the generator naturally exhausts — the "revise"
    scenario only needs to observe ONE loop-back, not a full drain to a terminal
    event, so the caller supplies the exact stopping condition.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    _orig_compile_for_run = engine_mod.compile_for_run

    def _patched_compile_for_run(pipeline_type, _orig=_orig_compile_for_run):
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    engine_mod.compile_for_run = _patched_compile_for_run

    specs = list(get_pipeline_agents(_PIPELINE))  # [] for a composed workflow —
    # execute() falls back to the compiled plan's own steps (ADR-0008).

    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _scripts_for(review_decision)

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_sm._scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    run_id = f"t26-{uuid.uuid4().hex[:8]}"
    events: list[dict] = []

    gen = engine.execute(
        agents=list(specs),
        user_message="Review the draft.",
        pipeline_run_id=run_id,
        pipeline_type=_PIPELINE,
        user_id="harness-user",
        # gate_agent_ids left at the default (None): the declared gates:[human]
        # step must take the REAL pause (see module docstring — NOT _drive()'s
        # gate_agent_ids=[] skip).
    )

    try:
        while True:
            try:
                ev = await asyncio.wait_for(gen.__anext__(), timeout=_EVENT_TIMEOUT_S)
            except StopAsyncIteration:
                break
            events.append(ev)
            if ev.get("type") == "review_gate_ready":
                await engine._store.set_review_response(
                    ev["data"]["gate_key"], approved=True
                )
            if stop_when(events):
                break
    finally:
        await gen.aclose()
        _sm._scripts_for = orig_scripts_for
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile_for_run

    return events


@pytest.mark.asyncio
async def test_revise_outcome_loops_back_to_greet():
    """revise-check's condition_agent:review reads review's captured 'revise'
    answer and routes the SAME run back to greet (R-05/R-06/R-07/R-08 — identical
    loop mechanism to A1, per spec.md A4)."""

    def _stop_when(events: list[dict]) -> bool:
        # Stop once greet has started a SECOND time (the loop-back), or a
        # gate_blocked/pipeline terminal event proves it never will.
        starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
        if starts.count("custom-agent:greet") >= 2:
            return True
        return any(
            e.get("type") in ("gate_blocked", "pipeline_complete", "pipeline_cancelled", "budget_aborted")
            for e in events
        )

    events = await _run_pipeline("revise", stop_when=_stop_when)

    assert events, f"{_PIPELINE} produced no events"
    types = [e.get("type") for e in events]
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    print("EVENT TYPES:", types)
    print("AGENT_START agent_ids:", starts)

    # ── The load-bearing assertions (T26 / revise pass) ────────────────────────
    # revise-check never blocked (which is what "read my own empty output"
    # would have produced — no default_next on this fixture, so a failed
    # decision read is a gate_blocked, not a silent pass-through).
    assert not any(e.get("type") == "gate_blocked" for e in events), (
        f"revise-check blocked instead of routing — condition_agent:review did "
        f"not resolve a decision. Events: {types}"
    )
    # greet ran a SECOND time — the loop-back cursor jump fired.
    assert starts.count("custom-agent:greet") >= 2, (
        f"expected greet to be re-dispatched via the loop-back after review "
        f"answered 'revise'; agent_start sequence: {starts}"
    )
    # revise-check's OWN agent dispatches exactly once — the conditional gate
    # evaluates POST-step (spec.md decision log #1: "the agent runs, the gate is
    # evaluated post-step"; engine.py's post-step gate loop runs AFTER
    # _dispatch_step_with_retry, by design), so a route match does NOT skip the
    # step's own dispatch. It is condition_agent:review — not revise-check's own
    # (empty/invalid) output — that supplies the "revise" decision the gate reads.
    assert starts.count("custom-agent:revise-check") == 1, (
        "expected revise-check's own agent to dispatch exactly once (the gate "
        f"evaluates POST-step, per spec.md decision log #1). starts={starts}"
    )
    # The SECOND greet start must be AFTER revise-check's own dispatch — i.e. this
    # is genuinely a loop-back through revise-check's post-step routing, not some
    # other duplicate start.
    revise_check_idx = starts.index("custom-agent:revise-check")
    second_greet_idx = [i for i, a in enumerate(starts) if a == "custom-agent:greet"][1]
    assert second_greet_idx > revise_check_idx, (
        "the second 'greet' dispatch did not come after revise-check's own "
        f"dispatch — not a genuine loop-back through revise-check's routing. "
        f"starts={starts}"
    )
    # done never ran within this window (the run looped, it didn't advance).
    assert "custom-agent:done" not in starts, (
        f"'done' ran despite review answering 'revise' — the run advanced "
        f"forward instead of looping back. starts={starts}"
    )


@pytest.mark.asyncio
async def test_continue_outcome_advances_to_done():
    """revise-check's condition_agent:review reads review's captured 'continue'
    answer and routes forward to done — the run completes normally, with NO
    loop-back (greet runs exactly once)."""

    def _stop_when(events: list[dict]) -> bool:
        return any(
            e.get("type") in ("pipeline_complete", "pipeline_cancelled", "gate_blocked", "budget_aborted")
            for e in events
        )

    events = await _run_pipeline("continue", stop_when=_stop_when)

    assert events, f"{_PIPELINE} produced no events"
    types = [e.get("type") for e in events]
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    print("EVENT TYPES:", types)
    print("AGENT_START agent_ids:", starts)

    # ── The load-bearing assertions (T26 / continue pass) ───────────────────────
    assert not any(e.get("type") == "gate_blocked" for e in events), (
        f"revise-check blocked instead of routing — condition_agent:review did "
        f"not resolve a decision. Events: {types}"
    )
    # revise-check's OWN agent dispatches exactly once — the conditional gate
    # evaluates POST-step (spec.md decision log #1), so a route match does not
    # skip the step's own dispatch (see the mirror assertion in the 'revise'
    # pass above for the full rationale).
    assert starts.count("custom-agent:revise-check") == 1, (
        "expected revise-check's own agent to dispatch exactly once (the gate "
        f"evaluates POST-step, per spec.md decision log #1). starts={starts}"
    )
    assert starts.count("custom-agent:greet") == 1, (
        f"greet re-ran (a spurious loop-back) despite review answering "
        f"'continue'. starts={starts}"
    )
    assert "custom-agent:done" in starts, (
        f"'done' never ran despite review answering 'continue'. starts={starts}"
    )
    assert "pipeline_complete" in types, (
        f"run never reached pipeline_complete after the 'continue' route; "
        f"got {types[-5:]}"
    )

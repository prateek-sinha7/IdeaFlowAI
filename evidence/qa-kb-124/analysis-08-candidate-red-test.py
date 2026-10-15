"""ISS-1156 (QA-KB-124) CANDIDATE red test, for the 4-test-writer to adopt (copy to backend/tests/agents/).

Why it is shaped like this
  backend/tests/unit/agents/test_decision_step_no_delivery_block.py composes the prompt from a HAND-BUILT spec
  (`dataclasses.replace(load_agent_spec("custom-agent:check"), produces=["route_decision"])`). A run never sees
  that spec: the engine hands the factory only the id and `create_runner` reloads it (factory.py:350), so the
  declared `produces` is gone. That test XPASSes against a predicate that never fires in production
  (evidence/qa-kb-124/fix-01-card-predicate-inert.txt).

  This test goes through the path a run takes: ExecutionEngine.execute() -> _run_agent -> AgentContext ->
  create_runner -> _compose_system_prompt, via the shared offline harness, and asserts on the system prompt the
  step was really given (the `agent_input` event). It names no mechanism, so it holds for any fix that gets the
  step's declared `produces` to the factory.

Verified (analysis-08-candidate-red-test-results.txt): FAILS on HEAD, FAILS on the card's original predicate
(spec.produces only), PASSES with `AgentContext.step_produces` threaded by the engine.

Run one file only:  cd backend && .venv/bin/python -m pytest tests/agents/<this file> -q -p no:cacheprovider
"""

from __future__ import annotations

import copy

import pytest

import agents.execution_engine.engine as engine_mod
from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _drive, _ScriptedTurn

_PIPELINE = "ex_A1_loop"


def _scripts_for(agent_id: str) -> list[_ScriptedTurn]:
    if agent_id == "custom-agent:check":
        return [_ScriptedTurn(texts=['{"decision": "ok"}'], usage=(5, 3))]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.mark.asyncio
async def test_write_granted_decision_step_is_not_told_to_deliver_to_a_file(monkeypatch):
    """The plan a saved override or the Composer produces: every step holds read+write, `check` declares
    `produces: [route_decision]` and a conditional route. The gate parses only `check`'s reply, so `check`
    must not be told to put its answer in a file; a plain write-granted step must still be told to."""
    orig_compile = engine_mod.compile_for_run

    def _compile(pipeline_type, _orig=orig_compile):
        plan = copy.deepcopy(_orig(pipeline_type))
        if pipeline_type == _PIPELINE:
            for step in plan.steps:
                step.tools.read_files = True
                step.tools.write_files = True
        return plan

    monkeypatch.setattr(engine_mod, "compile_for_run", _compile)
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _scripts_for
    try:
        events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for

    prompts = {
        e["data"]["agent_id"]: e["data"].get("system_prompt") or ""
        for e in events
        if e.get("type") == "agent_input"
    }
    assert "custom-agent:check" in prompts and "custom-agent:greet" in prompts, sorted(prompts)
    assert "How to deliver" not in prompts["custom-agent:check"], (
        "the decision source was told to deliver its answer via write_file; the conditional gate reads only the reply"
    )
    assert "How to deliver" in prompts["custom-agent:greet"], (
        "a plain write-granted step must keep the delivery contract (ADR-0011)"
    )

"""Engine: a conditional ``trigger: end`` outcome finishes the run successfully.

Reproduces run 725474ee: a final step whose route declared only a loop-back outcome
(``revise``) replied ``{"decision": "pass"}``; nothing matched, ``default_next`` was
unset, and the gate failed the run. ``trigger: end`` is the declared way out of a loop.

``ex_A1_loop`` is driven offline with its ``check`` step's route patched (the compiled
plan is deep-copied, as ``test_loop_exhausted_fail.py`` does) so ``stop`` ends the run
while ``retry`` still loops. The unmatched-decision case proves ISS-170 stays closed.
"""

from __future__ import annotations

import copy

import agents.execution_engine.engine as engine_mod
import pytest

from agents.workflows.plan import RouteOutcome
from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

_PIPELINE = "ex_A1_loop"
_DECISION_STEP = "custom-agent:check"


def _scripts_replying(decision: str):
    def _inner(agent_id: str) -> list[_ScriptedTurn]:
        if agent_id == _DECISION_STEP:
            return [
                _ScriptedTurn(texts=[f'{{"decision": "{decision}"}}'], usage=(5, 3))
            ]
        return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]

    return _inner


async def _drive_with_end_outcome(decision: str) -> list[dict]:
    """Drive ``ex_A1_loop`` with ``check`` answering ``decision`` and a ``stop`` end outcome."""
    orig_scripts_for = _sm._scripts_for
    orig_compile_for_run = engine_mod.compile_for_run

    def _compile_with_end_outcome(pipeline_type):
        compiled = copy.deepcopy(orig_compile_for_run(pipeline_type))
        for step in compiled.steps:
            if step.id == _DECISION_STEP:
                step.route.outcomes["stop"] = RouteOutcome(trigger="end", target="")
        return compiled

    _sm._scripts_for = _scripts_replying(decision)
    engine_mod.compile_for_run = _compile_with_end_outcome
    try:
        return await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for
        engine_mod.compile_for_run = orig_compile_for_run


def _started(events: list[dict]) -> list[str]:
    return [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]


@pytest.mark.asyncio
async def test_run_completes_when_decision_matches_an_end_outcome():
    events = await _drive_with_end_outcome("stop")

    types = [e.get("type") for e in events]
    assert (
        "pipeline_complete" in types
    ), f"an end outcome must complete the run: {types}"
    assert (
        "pipeline_failed" not in types
    ), f"an end outcome must not fail the run: {types}"


@pytest.mark.asyncio
async def test_steps_after_the_ending_step_are_skipped_when_decision_ends_the_run():
    events = await _drive_with_end_outcome("stop")

    assert "custom-agent:done" not in _started(events)
    skipped = [
        e["data"]["agent_id"] for e in events if e.get("type") == "agent_skipped"
    ]
    assert "custom-agent:done" in skipped, f"done must be reported skipped: {skipped}"


@pytest.mark.asyncio
async def test_run_still_fails_when_decision_matches_no_outcome():
    """ISS-170: ``end`` declares the happy path; an unknown decision is still a refusal."""
    events = await _drive_with_end_outcome("passed")

    types = [e.get("type") for e in events]
    assert (
        "pipeline_failed" in types
    ), f"an unmatched decision must fail the run: {types}"
    assert "pipeline_complete" not in types

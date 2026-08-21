"""T25 (spec 014 / Phase 3 dispatch loop): ``sample_conditional_branch_new`` (A2, the
forward-branch fixture) driven end-to-end via the shared offline scripted-model harness
(``tests.agents._scripted_model._drive``), with the ``pick`` step scripted to answer
``{"decision": "english"}`` in one run and ``{"decision": "spanish"}`` in the other.

Confirms R-06/R-09's mutual exclusivity holds for a FORWARD branch (not just the loop
case T23/T24 cover): exactly one of ``say_hello`` / ``say_hola`` ever runs per run, never
both, never neither. Also asserts spec.md's AC-04: the SKIPPED branch's
``ExecutionContext.step_visit_counts`` stays at 0 — R-06 (engine.py: "forward branches
never touch step_visit_counts") means this holds for the TAKEN branch too, since only a
backward/self ("loop") jump increments the counter; captured here by locally monkeypatching
``engine_mod.ExecutionContext`` to stash the run's live context, mirroring the same
local-monkeypatch discipline T24 uses for ``_scripts_for`` (restored in ``finally``).

No live LLM: fully scripted offline (``ScriptedFakeChatModel``), same recipe as every other
``tests/agents/_scripted_model.py``-based suite.
"""

from __future__ import annotations

import agents.execution_engine.engine as engine_mod
import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

_PIPELINE = "sample_conditional_branch_new"


def _scripts_for_decision(decision: str):
    def _inner(agent_id: str) -> list[_ScriptedTurn]:
        if agent_id == "custom-agent:pick":
            return [_ScriptedTurn(texts=[f'{{"decision": "{decision}"}}'], usage=(5, 3))]
        return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]

    return _inner


async def _drive_with_captured_ectx(decision: str):
    """Run ``_drive`` with ``pick`` scripted to ``decision``, capturing both the yielded
    events AND the run's live ``ExecutionContext`` (for the AC-04 ``step_visit_counts``
    check, which the event stream does not surface). Both monkeypatches are local to this
    call and restored in ``finally`` — no shared harness file is touched.
    """
    orig_scripts_for = _sm._scripts_for
    orig_execution_context = engine_mod.ExecutionContext
    captured: dict = {}

    def _capturing_execution_context(*a, **kw):
        ectx = orig_execution_context(*a, **kw)
        captured["ectx"] = ectx
        return ectx

    _sm._scripts_for = _scripts_for_decision(decision)
    engine_mod.ExecutionContext = _capturing_execution_context
    try:
        events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for
        engine_mod.ExecutionContext = orig_execution_context

    return events, captured.get("ectx")


@pytest.mark.asyncio
async def test_english_decision_runs_say_hello_not_say_hola():
    events, ectx = await _drive_with_captured_ectx("english")

    types = [e.get("type") for e in events]
    started = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    print("EVENT TYPES:", types)
    print("AGENT_START agent_ids:", started)

    # ── R-06/R-09 mutual exclusivity (forward branch) ─────────────────────
    assert "custom-agent:say-hello" in started, (
        f"english decision did not run say_hello. started={started}"
    )
    assert "custom-agent:say-hola" not in started, (
        f"english decision ALSO ran say_hola — mutual exclusivity violated. started={started}"
    )

    # ── AC-04: the SKIPPED branch's step_visit_counts stays at 0 ──────────
    assert ectx is not None, "ExecutionContext was not captured"
    assert ectx.step_visit_counts.get("custom-agent:say-hola", 0) == 0, (
        f"skipped branch 'say_hola' has a non-zero step_visit_counts entry: "
        f"{ectx.step_visit_counts}"
    )


@pytest.mark.asyncio
async def test_spanish_decision_runs_say_hola_not_say_hello():
    events, ectx = await _drive_with_captured_ectx("spanish")

    types = [e.get("type") for e in events]
    started = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    print("EVENT TYPES:", types)
    print("AGENT_START agent_ids:", started)

    # ── R-06/R-09 mutual exclusivity (forward branch) ─────────────────────
    assert "custom-agent:say-hola" in started, (
        f"spanish decision did not run say_hola. started={started}"
    )
    assert "custom-agent:say-hello" not in started, (
        f"spanish decision ALSO ran say_hello — mutual exclusivity violated. started={started}"
    )

    # ── AC-04: the SKIPPED branch's step_visit_counts stays at 0 ──────────
    assert ectx is not None, "ExecutionContext was not captured"
    assert ectx.step_visit_counts.get("custom-agent:say-hello", 0) == 0, (
        f"skipped branch 'say_hello' has a non-zero step_visit_counts entry: "
        f"{ectx.step_visit_counts}"
    )

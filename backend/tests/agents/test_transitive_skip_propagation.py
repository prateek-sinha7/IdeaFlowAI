"""Regression for run b80eff36: a conditional gate skip must propagate down
the dependency chain, not just report the gate's own direct route sibling.

``ex_test_transitive_skip`` (agents/workflows/ex_test_transitive_skip/workflow.yaml):

    1. side-input                          (always runs)
    2. gate  gates:[conditional]           decision "ok" -> target finisher
         |___ sibling outcome "gaps" -> planner   (NOT taken)
    3. planner   depends_on: [gate]                        — direct skip target
    4. builder   depends_on: [planner]                     — TRANSITIVE skip target
    5. finisher  depends_on: [planner, side-input]          — must still run
                                                               (side-input is live)

Before the fix: only ``planner`` got an ``agent_skipped`` event (the gate's own
``skipped_targets``); ``builder`` sat past the cursor jump with ZERO events —
the exact shape the frontend defaulted to a green "complete" check in
b80eff36 (Revision Builders: no duration, no tokens, but not greyed either).
"""

from __future__ import annotations

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

_PIPELINE = "ex_test_transitive_skip"
_DECISION_STEP = "custom-agent:gate"


def _scripts_for_ok(agent_id: str) -> list[_ScriptedTurn]:
    if agent_id == _DECISION_STEP:
        return [_ScriptedTurn(texts=['{"decision": "ok"}'], usage=(5, 3))]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


async def _drive_ok():
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _scripts_for_ok
    try:
        return await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for


@pytest.mark.asyncio
async def test_downstream_step_is_skipped_when_its_only_upstream_is_skipped():
    events = await _drive_ok()

    started = [
        e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"
    ]
    skipped = [
        e["data"].get("agent_id") for e in events if e.get("type") == "agent_skipped"
    ]

    print("AGENT_START:", started)
    print("AGENT_SKIPPED:", skipped)

    # Direct skip (pre-existing mechanism) — the gate's own sibling outcome.
    assert (
        "custom-agent:planner" in skipped
    ), f"the gate's direct skip target was not reported skipped: skipped={skipped}"
    assert "custom-agent:planner" not in started

    # ── The bug: transitive skip down the depends_on chain ────────────────
    assert "custom-agent:builder" in skipped, (
        f"builder depends_on ONLY the skipped 'planner' and must be reported "
        f"skipped too, not silently left with zero events. "
        f"started={started} skipped={skipped}"
    )
    assert "custom-agent:builder" not in started, (
        f"builder ran despite its only upstream (planner) being skipped — "
        f"it never received real input. started={started}"
    )

    # ── Safety rail: a step with ONE live + ONE skipped dep must still run ──
    assert "custom-agent:finisher" in started, (
        f"finisher has a LIVE dependency (side-input) in addition to the "
        f"skipped 'planner' — over-skipping it would silently drop real "
        f"work. started={started}"
    )
    assert "custom-agent:finisher" not in skipped
    assert "custom-agent:side-input" in started

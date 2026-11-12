"""goal_revision: one revision pipeline for goal runs that sizes the change itself,
and the routing that sends every goal revision to it."""

from __future__ import annotations

import pytest

from agents.execution_engine.engine import compile_for_run
from agents.registry import REVISION_BASE_MAP
from app.api import run_commands as rc
from tests.unit.test_v2_revision_routing import _create, _dispose, wired  # noqa: F401

STEPS = [
    "custom-agent:size",
    "custom-agent:analyst",
    "custom-agent:tests",
    "custom-agent:plan",
    "custom-agent:build",
    "custom-agent:change",
    "custom-agent:fix",
    "custom-agent:verify",
    "custom-agent:report",
]


def _step(compiled, step_id):
    return next(s for s in compiled.steps if s.agent_id == step_id)


def test_manifest_steps_and_deliverable():
    compiled = compile_for_run("goal_revision")
    assert [s.agent_id for s in compiled.steps] == STEPS
    d = compiled.deliverable
    assert (d.strategy, d.name, d.revises_existing) == (
        "single_file",
        "prototype.html",
        True,
    )


def test_size_branches_small_to_change_and_full_to_reviewed_analyst():
    compiled = compile_for_run("goal_revision")
    size = _step(compiled, "custom-agent:size")
    targets = {k: v.target for k, v in size.route.outcomes.items()}
    assert targets == {"small": "change", "full": "analyst"}
    assert "human" in _step(compiled, "custom-agent:analyst").gates
    assert "human" not in _step(compiled, "custom-agent:change").gates
    # Fix runs after whichever branch ran.
    assert set(_step(compiled, "custom-agent:fix").depends_on) == {
        "custom-agent:build",
        "custom-agent:change",
    }


def test_revision_base_and_step_count():
    assert REVISION_BASE_MAP["goal_revision"] == "goal"
    assert rc._revision_base_type("goal_revision") == "goal"
    assert rc._compiled_step_count("goal_revision") == len(STEPS)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [None, "prototype_output", "goal_output"])
@pytest.mark.parametrize("tier", ["small", "large", "feature"])
async def test_concierge_goal_parent_always_lands_on_goal_target(wired, tier, target):  # noqa: F811
    assert await _dispose(wired, tier, "goal", target) == "goal_output"


@pytest.mark.asyncio
async def test_concierge_nested_goal_revision_parent_keeps_goal_target(wired):  # noqa: F811
    assert (
        await _dispose(wired, "small", "goal_revision", "prototype_output")
        == "goal_output"
    )


@pytest.mark.asyncio
async def test_create_revision_goal_target_is_not_reclassified(wired):  # noqa: F811
    assert await _create(wired, "large", "goal_output") == "goal_output"

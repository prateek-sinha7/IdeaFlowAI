"""ADR-0010 — a composer-authored per-agent skill must actually reach the run.

WHY THIS FILE EXISTS. Run-level ``attached_skills`` (one skill bag applied to
every agent in a launch) is retired; skills are per-agent now. But a saved row's
``manifest_json`` is NEVER the run plan — the engine compiles its own file-backed
plan at run entry and overlays the ``selections`` map on top
(``ExecutionEngine._apply_selections``). So the SAVE path and the RUN path carry
skills through two different channels:

    save  →  manifest_json["steps"][i]["skills"]
    run   →  selections[agent_id]["skills"]  →  Step.skills  →  ctx.step_skills

Only the second one makes a skill reach a model. When the run-level path was
retired, ``skills`` was not in ``_synthesize_step``'s projection list, so a user
could tick a skill, watch it persist, and have it silently never be delivered.
These tests pin the repaired chain link by link so that regression cannot return
quietly — a broken link here produces a run that succeeds while ignoring the
user's skill, which no other test would catch.
"""

from __future__ import annotations

import pytest

from agents.execution_engine.engine import ExecutionEngine, compile_for_run
from agents.workflows.selections import _synthesize_step, synthesize_manifest


# --------------------------------------------------------------------------
# Link 1 — the selections synth projects `skills` onto the raw step
# --------------------------------------------------------------------------

def test_synthesize_step_projects_skills():
    step = _synthesize_step("some-agent", {"skills": ["emoji", "joke"]})
    assert step["skills"] == ["emoji", "joke"]


def test_synthesize_step_without_skills_omits_the_key():
    """Parity: a step that selected no skills must not gain an empty key."""
    assert "skills" not in _synthesize_step("some-agent", {"model": "x"})
    assert "skills" not in _synthesize_step("some-agent", None)


def test_synthesized_manifest_compiles_under_trust_user():
    """`skills` is a plain id list, so it must survive the trust=user gate that
    the launch path re-validates every selections map through."""
    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import WorkflowCompiler

    manifest = synthesize_manifest(
        "custom", ["market-research-agent"], {"market-research-agent": {"skills": ["emoji"]}}
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert compiled.steps[0].skills == ["emoji"]


# --------------------------------------------------------------------------
# Link 2 — the engine overlay lands them on the compiled Step
# --------------------------------------------------------------------------

@pytest.fixture
def custom_plan():
    return compile_for_run("custom")


def test_overlay_puts_selected_skills_on_the_compiled_step(custom_plan):
    agent_id = custom_plan.steps[0].agent_id
    assert custom_plan.steps[0].skills == [], "fixture assumption: base step declares none"

    plan, _ = ExecutionEngine._apply_selections(
        custom_plan, {agent_id: {"skills": ["emoji", "joke"]}}, run_agent_ids=[agent_id]
    )
    assert plan.steps[0].skills == ["emoji", "joke"]


def test_overlay_unions_rather_than_replaces(custom_plan):
    """The picker may only ADD to what the manifest author declared."""
    import dataclasses

    seeded = dataclasses.replace(custom_plan.steps[0], skills=["html-page"])
    plan_in = dataclasses.replace(custom_plan, steps=[seeded, *custom_plan.steps[1:]])

    plan, _ = ExecutionEngine._apply_selections(
        plan_in, {seeded.agent_id: {"skills": ["emoji"]}}, run_agent_ids=[seeded.agent_id]
    )
    assert plan.steps[0].skills == ["html-page", "emoji"]


def test_overlay_drops_unknown_ids_instead_of_crashing_the_run(custom_plan):
    """A workflow saved when a skill existed must survive that skill's removal.

    `factory._resolve_step_skills` asserts on an unresolvable id, so carrying a
    stale user-supplied id through would kill the run.
    """
    agent_id = custom_plan.steps[0].agent_id
    plan, _ = ExecutionEngine._apply_selections(
        custom_plan,
        {agent_id: {"skills": ["emoji", "no-such-skill-anywhere"]}},
        run_agent_ids=[agent_id],
    )
    assert plan.steps[0].skills == ["emoji"]


def test_no_skills_selected_leaves_the_plan_untouched(custom_plan):
    """INV-3 parity: the empty-selections path must not synthesize a skills key."""
    plan, _ = ExecutionEngine._apply_selections(custom_plan, None, run_agent_ids=None)
    assert plan is custom_plan
    assert all(s.skills == [] for s in plan.steps)


# --------------------------------------------------------------------------
# Link 3 — Step.skills resolves to a real staged payload
# --------------------------------------------------------------------------

def test_selected_ids_resolve_to_skill_payloads_with_content():
    """The last link: ids become the {"id","name","content"} shape stage_skills
    writes to the sandbox. An id that resolves to empty content would stage a
    file the model gains nothing from."""
    from agents.factory import _resolve_step_skills

    resolved = _resolve_step_skills(["emoji", "joke"])
    assert [r["id"] for r in resolved] == ["emoji", "joke"]
    assert all(r["content"].strip() for r in resolved)


def test_path_b_absent_agent_still_carries_its_skills(custom_plan):
    """A custom-agent instance is absent from the base manifest, so it never hits
    the overlay loop — it is served from the user-step map instead (Path B). Its
    skills must survive that route too."""
    _plan, user_map = ExecutionEngine._apply_selections(
        custom_plan,
        {"custom-agent:facts": {"skills": ["emoji"]}},
        run_agent_ids=["custom-agent:facts"],
    )
    assert user_map["custom-agent:facts"].skills == ["emoji"]

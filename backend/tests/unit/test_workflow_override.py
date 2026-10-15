"""Spec 016 — user overrides of built-in workflows.

Two units, tested here because they are the whole security and correctness
surface of the feature:

* ``app.api._workflow_override`` — the owner-scoped lookup every call site
  shares. The screen and the run MUST agree about which plan is in force, and
  they only can if they resolve through one function. Its tests need a real
  session, so they live in ``tests/integration/api/test_workflow_override_api.py``
  (ISS-1091).
* ``agents.execution_engine.overrides.merge_override_steps`` — the merge that
  takes ONLY ``steps`` from the DB and leaves every workflow-level field
  (deliverable, context_providers, clarify, planner) coming from the file
  manifest.

The cache-identity test is the load-bearing one: ``compile_for_run`` is
``lru_cache(maxsize=None)`` and its result is shared across every user and run,
so a merge that mutated it would leak one user's customisation into everybody
else's runs until process restart.
"""

from __future__ import annotations

import dataclasses

import pytest


# ── merge_override_steps ─────────────────────────────────────────────────────
#
# `ppt` is the real fixture on purpose: it is the workflow this feature exists
# for, and it is the one whose workflow-level capabilities (deliverable `ppt`,
# context_provider `opendesign`) are NOT user-allowed. A merge that sourced
# those from the override would fail to compile — these tests prove it doesn't.


@pytest.fixture
def ppt_compiled():
    from agents.execution_engine.engine import compile_for_run

    return compile_for_run("ppt")


@pytest.fixture
def registry():
    from agents.execution_engine.engine import _CAPABILITY_REGISTRY

    return _CAPABILITY_REGISTRY


def _steps(*instance_ids):
    return [
        {
            "agent": "custom-agent",
            "instance_id": iid,
            "name": iid,
            "prompt": f"You are {iid}.",
            "tools": {"read_files": False, "write_files": False, "exec": False},
        }
        for iid in instance_ids
    ]


def test_merge_does_not_mutate_the_cached_plan(ppt_compiled, registry):
    """THE load-bearing test.

    compile_for_run is lru_cache(maxsize=None), so its CompiledWorkflow is
    shared across every user and run in the process. A merge that mutated it
    would leak one user's customisation into everyone else's runs until restart.
    """
    from agents.execution_engine.engine import compile_for_run
    from agents.execution_engine.overrides import merge_override_steps

    before_ids = [s.agent_id for s in ppt_compiled.steps]
    merged = merge_override_steps(ppt_compiled, _steps("mine"), registry)

    # The cached object is untouched...
    assert [s.agent_id for s in ppt_compiled.steps] == before_ids
    assert [s.agent_id for s in compile_for_run("ppt").steps] == before_ids
    # ...and the result is a different object carrying the override.
    assert merged is not ppt_compiled
    assert [s.agent_id for s in merged.steps] != before_ids


def test_merge_keeps_every_workflow_level_field_from_the_file(ppt_compiled, registry):
    """deliverable `ppt` and context_provider `opendesign` are NOT user_allowed.
    They survive only because they are never sourced from the override."""
    from agents.execution_engine.overrides import merge_override_steps

    merged = merge_override_steps(ppt_compiled, _steps("mine"), registry)

    assert merged.deliverable.strategy == ppt_compiled.deliverable.strategy == "ppt"
    assert merged.deliverable.name == ppt_compiled.deliverable.name
    assert merged.context_providers == ppt_compiled.context_providers
    assert "opendesign" in merged.context_providers
    assert merged.planner == ppt_compiled.planner
    assert merged.clarify.mode == ppt_compiled.clarify.mode
    assert list(merged.clarify.defaults) == list(ppt_compiled.clarify.defaults)
    assert merged.id == ppt_compiled.id


def test_merge_applies_the_override_steps(ppt_compiled, registry):
    from agents.execution_engine.overrides import merge_override_steps

    merged = merge_override_steps(ppt_compiled, _steps("one", "two"), registry)
    assert len(merged.steps) == 2


def test_empty_steps_returns_the_file_plan_unchanged(ppt_compiled, registry):
    from agents.execution_engine.overrides import merge_override_steps

    assert merge_override_steps(ppt_compiled, [], registry) is ppt_compiled


@pytest.mark.issue("ISS-1092")
def test_a_not_user_allowed_gate_is_rejected(ppt_compiled, registry):
    """`security` is registered user_allowed=False. A row smuggling one must be
    refused by the trust gate and the run must fall back to the file plan."""
    from agents.execution_engine.overrides import merge_override_steps

    bad = _steps("mine")
    bad[0]["gates"] = ["security"]
    assert merge_override_steps(ppt_compiled, bad, registry) is ppt_compiled


def test_a_malformed_step_list_falls_back_to_the_file_plan(ppt_compiled, registry):
    from agents.execution_engine.overrides import merge_override_steps

    assert merge_override_steps(ppt_compiled, ["not-a-step"], registry) is ppt_compiled


@pytest.mark.issue("ISS-1111")
@pytest.mark.parametrize("grant", ["exec", "spawn_subagents"])
def test_an_override_step_cannot_carry_a_privileged_tool_grant(
    ppt_compiled, registry, grant
):
    """ISS-1111 — exec / spawn_subagents are not user_allowed; an override step
    carrying one must be refused and the file plan kept."""
    from agents.execution_engine.overrides import merge_override_steps

    bad = _steps("mine")
    bad[0]["tools"] = {
        "read_files": True,
        "write_files": True,
        "exec": False,
        grant: True,
    }
    if grant == "exec":
        # D-01: an exec step must declare both gates, or it fails for that reason
        # at any trust level and proves nothing about the user_allowed check.
        bad[0]["gates"] = ["security", "approval"]
    assert merge_override_steps(ppt_compiled, bad, registry) is ppt_compiled

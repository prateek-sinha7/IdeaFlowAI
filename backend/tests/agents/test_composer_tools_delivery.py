"""QA-PS-019 — the composer's per-step Tools tab levers never reach the run.

WHY THIS FILE EXISTS. ``ExecutionEngine._apply_selections`` overlays the
composer's per-step ``selections`` onto the file-compiled plan (same seam
``test_composer_skills_delivery.py`` pins for ``skills``). The overlay's
``patch`` dict builds one case per lever — ``validators``, ``gates``,
``model``, ``retry``, ``injects``, ``skills``, ``strategy``, ``fanout``,
``task_source`` — but has NO case for ``tools``. So a user who toggles
"Write files" ON in the Tools tab (ISS-698) or "Read files" OFF (ISS-732)
watches the selection save, and the selected step keeps whatever the base
manifest declared instead — silently, no error.

``_synthesize_step`` already projects ``tools`` onto the trust=user
re-compile (``selections.py`` generic key list), and the compiler already
turns it into a real ``ToolPermissions`` on ``user_step.tools`` — confirmed
by the first test below. The break is ONLY in the overlay not copying that
onto the step that actually runs, which the second/third tests pin directly
against ``ExecutionEngine._apply_selections``.
"""

from __future__ import annotations

import pytest

from agents.execution_engine.engine import ExecutionEngine, compile_for_run


@pytest.fixture
def custom_plan():
    return compile_for_run("custom")


def test_trust_user_recompile_already_carries_the_tools_selection():
    """Link 1 (not the bug): the synth + compiler chain works fine on its own."""
    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import WorkflowCompiler
    from agents.workflows.selections import synthesize_manifest

    manifest = synthesize_manifest(
        "custom",
        ["market-research-agent"],
        {"market-research-agent": {"tools": {"write_files": True}}},
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    assert compiled.steps[0].tools.write_files is True


@pytest.mark.issue("ISS-698")
def test_write_files_toggle_on_reaches_the_running_step(custom_plan):
    """ISS-698 — toggling "Write files" ON must grant write_files at runtime.

    The custom base manifest's first step declares no ``tools:`` block, which
    compiles to the least-privilege default (``write_files=False``,
    ``compiler.py`` §8) — that is the fixture assumption this test pins before
    asserting the overlay should flip it.
    """
    agent_id = custom_plan.steps[0].agent_id
    assert (
        custom_plan.steps[0].tools.write_files is False
    ), "fixture assumption: base step defaults write_files off"

    plan, _ = ExecutionEngine._apply_selections(
        custom_plan,
        {agent_id: {"tools": {"write_files": True}}},
        run_agent_ids=[agent_id],
    )
    assert plan.steps[0].tools.write_files is True


@pytest.mark.issue("ISS-732")
def test_read_files_toggle_off_reaches_the_running_step(custom_plan):
    """ISS-732 — toggling "Read files" OFF must revoke read access at runtime.

    Every custom-workflow step defaults ``read_files=True`` (either declared
    explicitly in the base manifest or via the §8 default) — pinned here
    before asserting the overlay should flip it off.
    """
    agent_id = custom_plan.steps[0].agent_id
    assert (
        custom_plan.steps[0].tools.read_files is True
    ), "fixture assumption: base step defaults read_files on"

    plan, _ = ExecutionEngine._apply_selections(
        custom_plan,
        {agent_id: {"tools": {"read_files": False}}},
        run_agent_ids=[agent_id],
    )
    assert plan.steps[0].tools.read_files is False

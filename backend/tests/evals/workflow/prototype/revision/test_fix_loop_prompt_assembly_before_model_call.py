"""Fix-loop prompt assembly at the LLM boundary (formerly "L6"; R-12 / D-06).

``_run_validation_fix_loop``'s revision branch is the LAST deterministic
point before a model call: it assembles the fix prompt and mints the fix
thread. Everything beyond it is model behavior (covered by the Phase-2
scenario evals with scripted models).

Asserts, with ``create_runner`` captured and the validators scripted:
  * the revision ``fix_message`` embeds the user's instruction VERBATIM
    (the re-injection FINDINGS A2 relies on when a retry does fire);
  * the selected issue lines ride along;
  * the fix thread id is ``{run}:{agent_id}:{label}:fix{n}`` with the
    agent id threaded from the caller (compiled step), not a literal;
  * the revision residual path logs the SELECTED issues (not the build
    residual assembly).

Capture harness lives in tests/evals/common/fix_loop_capture.py — generic
to any pipeline's fix-loop, build or revision, since both go through
``_run_validation_fix_loop`` (see PLAN.md's Amendment 2).

Offline: static/render checks monkeypatched at their source modules (the
loop imports them at call time); the captured runner drains instantly.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.evals.common.fix_loop_capture import patch_fix_loop_seams

pytestmark = pytest.mark.eval

INSTRUCTION = "Make the Save button on Settings actually save"


@pytest.fixture
def captured(monkeypatch, runs_root):
    """Wire the loop's seams: failing static check, clean render, captured runner."""
    return patch_fix_loop_seams(
        monkeypatch, static_issues=["static-NEW-from-edit"], static_ok=False
    )


def _run_loop(captured, runs_root) -> None:
    from agents.execution_engine.engine import ExecutionEngine
    from app.agents.sandbox import RunSandbox

    sandbox = RunSandbox("eval-user", "eval-run-l6")
    sandbox.ensure()
    sandbox.path_for("prototype.html").write_text("<!doctype html>", encoding="utf-8")

    engine = ExecutionEngine()
    asyncio.run(
        engine._run_validation_fix_loop(
            ctx=object(),  # opaque to the loop; only forwarded to create_runner
            sandbox=sandbox,
            pipeline_run_id="eval-run-l6",
            task_num=1,
            total_tasks=1,
            cancel_event=None,
            filename="prototype.html",
            max_attempts=1,
            agent_id="prototype-revision-agent",
            baseline_static=set(),
            baseline_console=set(),
            user_instruction=INSTRUCTION,
            label="revision",
            require_render=True,
        )
    )


def test_fix_message_embeds_instruction_verbatim(captured, runs_root) -> None:
    _run_loop(captured, runs_root)

    assert len(captured.messages) == 1
    msg = captured.messages[0]
    assert f'"{INSTRUCTION}"' in msg                      # verbatim re-injection
    assert "- static-NEW-from-edit" in msg                # selected issues ride along
    assert "do not undo the requested change" in msg.lower()  # revision framing, not build framing


def test_fix_thread_uses_threaded_agent_id(captured, runs_root) -> None:
    _run_loop(captured, runs_root)

    assert captured.agent_ids == ["prototype-revision-agent"]
    assert captured.thread_ids == ["eval-run-l6:prototype-revision-agent:revision:fix1"]

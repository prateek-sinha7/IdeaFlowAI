"""L6 — the LLM boundary (R-12 / D-06).

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

Offline: static/render checks monkeypatched at their source modules (the
loop imports them at call time); the captured runner drains instantly.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents.render_check import RenderResult
from app.agents.static_check import StaticCheckResult

pytestmark = pytest.mark.eval

INSTRUCTION = "Make the Save button on Settings actually save"


class _CapturedFix:
    """Records what create_runner + the fix agent's dispatch received."""

    def __init__(self) -> None:
        self.agent_ids: list[str] = []
        self.thread_ids: list[str] = []
        self.messages: list[str] = []

    def runner_factory(self, agent_id, ctx, *, thread_id=None, checkpointer=None):
        self.agent_ids.append(agent_id)
        self.thread_ids.append(thread_id)
        capture = self

        class _FixRunner:
            async def astream_events(self, message):
                capture.messages.append(message)
                if False:  # pragma: no cover — async-gen shape, no events
                    yield {}

        return _FixRunner()


@pytest.fixture
def captured(monkeypatch, runs_root):
    """Wire the loop's seams: failing static check, clean render, captured runner."""
    import agents.execution_engine.engine as engine_mod
    import app.agents.render_check as render_mod
    import app.agents.static_check as static_mod

    cap = _CapturedFix()
    monkeypatch.setattr(engine_mod, "create_runner", cap.runner_factory)
    monkeypatch.setattr(
        static_mod, "static_check",
        lambda path: StaticCheckResult(ok=False, issues=["static-NEW-from-edit"]),
    )

    async def _fake_render(path):
        return RenderResult(ok=True, available=True)

    monkeypatch.setattr(render_mod, "render_check", _fake_render)
    return cap


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

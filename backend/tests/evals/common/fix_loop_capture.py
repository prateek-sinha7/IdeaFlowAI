"""Reusable capture harness for testing ANY pipeline's fix-loop LLM boundary
(_run_validation_fix_loop) offline — records create_runner calls (agent_id,
thread_id, dispatched message) instead of calling a real model. Generic to
build or revision callers, since both go through the same
_run_validation_fix_loop.
"""

from __future__ import annotations


class CapturedRunnerFactory:
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


def patch_fix_loop_seams(
    monkeypatch,
    *,
    static_issues: list[str] | None = None,
    static_ok: bool = False,
    render_ok: bool = True,
) -> CapturedRunnerFactory:
    """Wires the loop's 3 seams offline: create_runner captured, static_check
    scripted, render_check scripted. Call from a test's own @pytest.fixture
    (which also needs the runs_root fixture from the root conftest) — this
    function is the reusable BODY, not a fixture itself, since fixtures must
    live in a conftest.py or be declared with @pytest.fixture in the test
    module that uses them.
    """
    import agents.execution_engine.engine as engine_mod
    import app.agents.render_check as render_mod
    import app.agents.static_check as static_mod
    from app.agents.render_check import RenderResult
    from app.agents.static_check import StaticCheckResult

    cap = CapturedRunnerFactory()
    monkeypatch.setattr(engine_mod, "create_runner", cap.runner_factory)
    monkeypatch.setattr(
        static_mod, "static_check",
        lambda path: StaticCheckResult(ok=static_ok, issues=static_issues or []),
    )

    async def _fake_render(path):
        return RenderResult(ok=render_ok, available=True)

    monkeypatch.setattr(render_mod, "render_check", _fake_render)
    return cap

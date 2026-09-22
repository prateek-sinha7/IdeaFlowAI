"""tests/agents/test_iss033a_fixloop_token_fold_offline.py — ISS-033-A offline proof.

Offline (no Bedrock / no network / no live DB) proof that the VALIDATION FIX-LOOP's
model spend is COUNTED in the run's token totals.

``_run_validation_fix_loop`` re-invokes the build sub-agent on a ``…:fixN`` thread and
drains its stream INTERNALLY (it re-emits nothing, by design — the UI must show ONE
build per task). Before FIX-230 that drain was a bare ``continue``, so every ``usage``
event the fix sub-agent produced was discarded: 300k-600k input tokens per fix call
that the run's reported cost never saw (≈6.9% of the input on the measured live run
``fa66227a``).

The tests below pin the chain from the narrowest seam outward. This file holds the
zero-I/O SEAM half:

  1. the loop routes ``usage`` into the injected sink (and nothing else);
  2. ``KernelServices`` threads its constructor sink into the loop — the PRODUCTION
     wiring, not just the private keyword.

The END-TO-END half (3 — the ``prototype`` run's totals exceed the visible per-agent
totals by exactly the fix spend; 4 — the fold must not inflate ``agents_completed``)
drives the real ``execute()`` and therefore a real ``SessionLocal()``, so it lives in
``tests/integration/agents/test_iss033a_fixloop_token_fold_db.py``.

Companion to ``tests/integration/agents/test_iss033_aux_token_fold_offline.py``, which
pins the OTHER two aux sources (SmartPlanner + ClarifyEngine) folding into the same
``aux_token_usage`` sink.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# The fix sub-agent's scripted spend. Distinct, non-round-tripping magnitudes so a
# delta can only be explained by THIS usage event.
_FIX_USAGE = {
    "type": "usage",
    "input_tokens": 4321,
    "output_tokens": 765,
    "cache_read_tokens": 210,
    "cache_write_tokens": 43,
}


class _UsageEmittingRunner:
    """A stand-in ``DeepAgentRunner`` that streams one chunk, one usage, one chunk.

    Mirrors the real runner's event vocabulary (``deep_agent_runner.py:495/509``) so
    the loop's drain sees the same shapes it sees in production.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def astream_events(self, message: str):
        self.calls += 1
        yield {"type": "chunk", "chunk": "fixing "}
        yield dict(_FIX_USAGE)
        yield {"type": "tool_call", "tool": "edit_file", "args": {}}


def _failing_static(_path):
    """A static_check result with one issue — enough to open a fix thread."""
    return SimpleNamespace(
        ok=False,
        issues=[
            'no active page: expected one <section data-page> with class="is-active"'
        ],
        warnings=[],
        summary=lambda: "1 issue(s)",
    )


@pytest.fixture()
def _fixloop_env(tmp_path, monkeypatch):
    """Patch validation to FAIL and ``create_runner`` to return a usage-emitting fake.

    Returns ``(sandbox, runner)``. Render is reported unavailable so the render half
    contributes nothing and the fix-list is exactly the one static issue.
    """
    from agents.execution_engine import engine as engine_mod
    import app.agents.render_check as rc_mod
    import app.agents.static_check as sc_mod
    from app.agents.render_check import RenderResult

    html_file = tmp_path / "prototype.html"
    html_file.write_text("<!doctype html><html><body>x</body></html>", encoding="utf-8")

    monkeypatch.setattr(sc_mod, "static_check", _failing_static, raising=True)

    async def _skipped_render(_p):
        return RenderResult(ok=True, available=False, note="Chromium unavailable")

    monkeypatch.setattr(rc_mod, "render_check", _skipped_render, raising=True)

    runner = _UsageEmittingRunner()
    monkeypatch.setattr(
        engine_mod, "create_runner", lambda *a, **k: runner, raising=True
    )
    return SimpleNamespace(path_for=lambda name: html_file), runner


# ---------------------------------------------------------------------------
# 1 — the loop routes the fix sub-agent's usage into the sink
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fix_loop_routes_usage_to_aux_sink(_fixloop_env) -> None:
    from agents.execution_engine import engine as engine_mod

    sandbox, runner = _fixloop_env
    collected: list[dict] = []

    await engine_mod.ExecutionEngine._run_validation_fix_loop(
        SimpleNamespace(),
        ctx=SimpleNamespace(),
        sandbox=sandbox,
        pipeline_run_id="run-iss033a",
        task_num=1,
        total_tasks=1,
        cancel_event=None,
        filename="prototype.html",
        max_attempts=1,
        require_render=False,
        aux_usage_sink=collected.append,
    )

    assert runner.calls == 1, "exactly one fix attempt should have opened"
    assert len(collected) == 1, f"expected the one usage event, got {collected}"
    got = collected[0]
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ):
        assert got[key] == _FIX_USAGE[key], f"{key} did not reach the sink intact"


@pytest.mark.asyncio
async def test_fix_loop_without_a_sink_still_runs(_fixloop_env) -> None:
    """No sink (the direct/unit call shape) must remain a no-op, not a crash."""
    from agents.execution_engine import engine as engine_mod

    sandbox, runner = _fixloop_env
    await engine_mod.ExecutionEngine._run_validation_fix_loop(
        SimpleNamespace(),
        ctx=SimpleNamespace(),
        sandbox=sandbox,
        pipeline_run_id="run-iss033a-nosink",
        task_num=1,
        total_tasks=1,
        cancel_event=None,
        filename="prototype.html",
        max_attempts=1,
        require_render=False,
    )
    assert runner.calls == 1


# ---------------------------------------------------------------------------
# 2 — KernelServices threads its CONSTRUCTOR sink into the loop
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kernel_services_threads_aux_usage_sink_into_fix_loop() -> None:
    """The production path: ``execute()`` binds the sink at construction, and the
    handle must hand it to the engine loop — otherwise the loop's new parameter is
    dead code on the only caller that matters."""
    from agents.execution_engine.kernel_services import KernelServices

    captured: dict = {}

    class _StubEngine:
        @staticmethod
        def _resolve_model(ectx, spec, model_id, step=None):
            return model_id

        async def _run_validation_fix_loop(self, **kwargs):
            captured.update(kwargs)

    aux: list[dict] = []
    spec = SimpleNamespace(id="prototype-build", name="Build", role="r", icon="i")
    ectx = SimpleNamespace(
        od_context=None,
        disk_principal="u1",
        checkpointer=None,
        current_step=None,
    )
    handle = KernelServices(
        engine=_StubEngine(),
        ectx=ectx,
        sandbox=SimpleNamespace(),
        ordered_agents=[spec],
        user_message="build a thing",
        pipeline_run_id="run-ks",
        pipeline_type="prototype",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        results=[],
        cancel_event=None,
        aux_usage_sink=aux.append,
    )

    await handle.run_validation_fix_loop(
        SimpleNamespace(agent_id="prototype-build", require_render=False),
        task_num=1,
        total_tasks=1,
        filename="prototype.html",
    )

    assert "aux_usage_sink" in captured, (
        "KernelServices.run_validation_fix_loop did not thread aux_usage_sink into "
        "the engine loop — the fix-loop spend would stay uncounted on the live path"
    )
    captured["aux_usage_sink"]({"input_tokens": 7})
    assert aux == [{"input_tokens": 7}], "the threaded sink is not the constructor's"

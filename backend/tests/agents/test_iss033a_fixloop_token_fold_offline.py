"""tests/agents/test_iss033a_fixloop_token_fold_offline.py — ISS-033-A offline proof.

Offline (no Bedrock / no network / no live DB) proof that the VALIDATION FIX-LOOP's
model spend is COUNTED in the run's token totals.

``_run_validation_fix_loop`` re-invokes the build sub-agent on a ``…:fixN`` thread and
drains its stream INTERNALLY (it re-emits nothing, by design — the UI must show ONE
build per task). Before FIX-230 that drain was a bare ``continue``, so every ``usage``
event the fix sub-agent produced was discarded: 300k-600k input tokens per fix call
that the run's reported cost never saw (≈6.9% of the input on the measured live run
``fa66227a``).

The four tests below pin the whole chain, from the narrowest seam outward:

  1. the loop routes ``usage`` into the injected sink (and nothing else);
  2. ``KernelServices`` threads its constructor sink into the loop — the PRODUCTION
     wiring, not just the private keyword;
  3. end-to-end on the REAL ``prototype`` pipeline: the ``pipeline_complete`` totals
     now EXCEED the sum of the visible ``agent_complete`` totals by exactly the fix
     sub-agents' spend. That inequality is the ISS-033 statement itself;
  4. the fold must NOT reach ``results`` — ``agents_completed = len(results)``, so a
     fix attempt counted as an agent would corrupt the run's agent count.

Companion to ``test_iss033_aux_token_fold_offline.py``, which pins the OTHER two aux
sources (SmartPlanner + ClarifyEngine) folding into the same ``aux_token_usage`` sink.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.agents._scripted_model import _drive

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
        issues=["no active page: expected one <section data-page> with class=\"is-active\""],
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


# ---------------------------------------------------------------------------
# 3 — END TO END on the real prototype pipeline: the number moves
# ---------------------------------------------------------------------------
def _pipeline_complete(events: list[dict]) -> dict:
    for ev in events:
        if ev.get("type") == "pipeline_complete":
            return ev["data"]
    raise AssertionError("no pipeline_complete event was emitted")


def _visible_agent_totals(events: list[dict]) -> tuple[int, int]:
    """Sum the per-agent ``agent_complete`` tokens — everything the UI can SEE."""
    tin = sum(
        (ev.get("data") or {}).get("input_tokens", 0) or 0
        for ev in events
        if ev.get("type") == "agent_complete"
    )
    tout = sum(
        (ev.get("data") or {}).get("output_tokens", 0) or 0
        for ev in events
        if ev.get("type") == "agent_complete"
    )
    return tin, tout


#: The prototype golden runs 2 tasks × 2 bounded fix attempts = 4 fix sub-agents, each
#: consuming the ``prototype-build`` script's turns (50/20 then 10/5 — the fix agent
#: gets a FRESH scripted model per ``create_runner``). Hard-coded rather than derived
#: so a silent change in what the fix loop invokes fails loudly here.
_EXPECTED_FIXLOOP_INPUT = 240
_EXPECTED_FIXLOOP_OUTPUT = 100


@pytest.mark.asyncio
async def test_prototype_run_total_includes_fix_loop_tokens() -> None:
    """The run's reported totals EXCEED the visible per-agent totals by exactly the
    fix sub-agents' spend — the previously invisible money, now counted."""
    events = await _drive("prototype")
    totals = _pipeline_complete(events)
    visible_in, visible_out = _visible_agent_totals(events)

    assert visible_in > 0 and visible_out > 0, "the harness produced no agent tokens"

    assert totals["total_input_tokens"] - visible_in == _EXPECTED_FIXLOOP_INPUT
    assert totals["total_output_tokens"] - visible_out == _EXPECTED_FIXLOOP_OUTPUT
    assert totals["total_tokens"] == (
        totals["total_input_tokens"] + totals["total_output_tokens"]
    )


# ---------------------------------------------------------------------------
# 4 — the fold must not turn fix attempts into "agents"
# ---------------------------------------------------------------------------
#: ``agents_completed = len(results)`` counts ``_run_agent`` INVOCATIONS, not steps:
#: the prototype's 5 steps plus the build agent's second task = 6, which is why it
#: legitimately exceeds ``agents_total`` (5). Pinned literally so the four fix
#: sub-agents showing up here (6 → 10) fails loudly.
_EXPECTED_AGENTS_COMPLETED = 6


@pytest.mark.asyncio
async def test_fix_loop_tokens_do_not_inflate_agents_completed() -> None:
    """The fix spend goes to ``aux_token_usage``, never to ``results`` — so four fix
    sub-agents must not appear as four more completed agents (a regression guard:
    green before AND after, unlike the three tests above)."""
    events = await _drive("prototype")
    totals = _pipeline_complete(events)
    agent_completes = sum(1 for ev in events if ev.get("type") == "agent_complete")

    assert totals["agents_completed"] == agent_completes
    assert totals["agents_completed"] == _EXPECTED_AGENTS_COMPLETED

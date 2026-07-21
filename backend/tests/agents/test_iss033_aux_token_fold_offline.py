"""tests/agents/test_iss033_aux_token_fold_offline.py — ISS-033 offline proof.

Offline (no Bedrock / no network / no live DB) proof that the AUX one-shot
model-call tokens — the SmartPlanner planning call and the ClarifyEngine
question-generation call, both of which run OUTSIDE the per-agent stream — FOLD
into the run's ``pipeline_complete`` token totals (the fold at
``engine.py:2474-2482``).

``tests/unit/test_cached_invoke.py`` already proves the *counting* half: each aux
call-site routes its ``usage`` into the run-usage sink through the shared
``cached_invoke`` helper. THIS test closes the OTHER half — that the engine's
``aux_token_usage`` sink entries actually reach the emitted ``pipeline_complete``
totals — and it does so as a DELTA against a planner-skipped baseline run so the
fold MUST be non-zero to pass (T-44-11-01: a vacuous ``baseline == folded`` cannot
slip through).

The aux tokens are injected through the engine's REAL ``usage_sink``
(``aux_token_usage.append``, the exact callable both the planner and the clarify
sink use), so the code path under test is the production fold, not a stand-in.

Fully offline: a scripted ``BaseChatModel`` per agent (no Bedrock), the planner
neutralised to a deterministic PROCEED context that emits scripted aux ``usage``,
``clarify.mode`` forced ``off`` (no live WS round-trip), and the thin store stubbed.
"""

from __future__ import annotations

import copy
import uuid as _uuid

import pytest

from tests.agents._scripted_model import (
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _scripts_for,
)

# The two AUX one-shot calls, scripted with KNOWN token counts. In production the
# SmartPlanner (via ``SmartPlanner.plan`` → ``cached_invoke``) and the ClarifyEngine
# (via ``clarify._usage_sink``) each append one of these usage dicts to the engine's
# ``aux_token_usage`` list; the fold at engine.py:2474-2482 sums them into the run
# totals. Distinct, non-round-tripping magnitudes so the delta is unambiguous.
_PLANNER_USAGE = {
    "input_tokens": 1300,
    "output_tokens": 240,
    "cache_read_tokens": 110,
    "cache_write_tokens": 55,
}
_CLARIFY_USAGE = {
    "input_tokens": 640,
    "output_tokens": 180,
    "cache_read_tokens": 70,
    "cache_write_tokens": 33,
}


async def _drive_with_aux(pipeline_type: str, aux_usages: list[dict]) -> list[dict]:
    """Run ``ExecutionEngine.execute()`` end-to-end OFFLINE and return the yielded
    event dicts. The planner is neutralised to a deterministic PROCEED context that
    routes each dict in ``aux_usages`` into the engine's REAL ``usage_sink`` — exactly
    as the SmartPlanner + ClarifyEngine do via ``cached_invoke``. ``aux_usages=[]``
    yields a planner-skipped-equivalent BASELINE (the sink is never called, so
    ``aux_token_usage`` stays empty and nothing folds).
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    # Disable the auto-clarify override (needs a live WS round-trip) by forcing the
    # compiled ``clarify.mode`` to "off". Deep-copy first — ``compile_for_run`` is
    # lru_cache'd, so mutating the shared CompiledWorkflow in place would corrupt the
    # cache for every later caller in the process.
    _orig_compile = engine_mod.compile_for_run

    def _patched_compile(pt, _orig=_orig_compile):
        compiled = copy.deepcopy(_orig(pt))
        compiled.clarify.mode = "off"
        for s in getattr(compiled, "steps", []) or []:
            if hasattr(s, "require_render"):
                s.require_render = False
        return compiled

    engine_mod.compile_for_run = _patched_compile

    specs = get_pipeline_agents(pipeline_type)

    # Per-agent scripted model (no Bedrock): each agent consumes its own script.
    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    # The planner runs OFFLINE: return a deterministic PROCEED context and route the
    # scripted aux usage into the engine's REAL ``usage_sink`` (``aux_token_usage.append``)
    # — the same sink SmartPlanner + ClarifyEngine feed in production. An empty
    # ``aux_usages`` never calls the sink → the baseline carries no aux tokens.
    async def _fake_run_planner(
        user_message,
        pipeline_run_id,
        model_id,
        cancel_event,
        ptype="custom",
        ectx=None,
        usage_sink=None,
        **kwargs,
    ):
        if usage_sink is not None:
            for u in aux_usages:
                usage_sink(dict(u))
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover — make it an async generator

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    events: list[dict] = []
    run_id = f"iss033-{pipeline_type}-{_uuid.uuid4().hex[:8]}"
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Build me a thing for managing tasks and reminders.",
            pipeline_run_id=run_id,
            pipeline_type=pipeline_type,
            user_id="iss033-user",
            od_context=None,
            gate_agent_ids=[],
        ):
            events.append(ev)
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile
    return events


def _pipeline_complete(events: list[dict]) -> dict:
    for ev in events:
        if ev.get("type") == "pipeline_complete":
            return ev["data"]
    raise AssertionError("no pipeline_complete event was emitted")


@pytest.mark.asyncio
async def test_aux_tokens_fold_into_pipeline_complete_totals() -> None:
    """The SmartPlanner + clarify aux tokens land in the pipeline_complete totals —
    proven as the DELTA vs a planner-skipped baseline (the fold must be non-zero)."""
    baseline = _pipeline_complete(await _drive_with_aux("user_stories", []))
    folded = _pipeline_complete(
        await _drive_with_aux("user_stories", [_PLANNER_USAGE, _CLARIFY_USAGE])
    )

    aux_in = _PLANNER_USAGE["input_tokens"] + _CLARIFY_USAGE["input_tokens"]
    aux_out = _PLANNER_USAGE["output_tokens"] + _CLARIFY_USAGE["output_tokens"]
    aux_cr = _PLANNER_USAGE["cache_read_tokens"] + _CLARIFY_USAGE["cache_read_tokens"]
    aux_cw = _PLANNER_USAGE["cache_write_tokens"] + _CLARIFY_USAGE["cache_write_tokens"]

    # T-44-11-01: the aux contribution is strictly positive, so a vacuous
    # baseline == folded cannot pass.
    assert aux_in > 0 and aux_out > 0 and aux_cr > 0 and aux_cw > 0

    # The baseline (no aux) carries ONLY the per-agent stream tokens — the aux fold
    # is absent, so its totals are the pure agent-stream sums.
    assert baseline["total_input_tokens"] == 72
    assert baseline["total_output_tokens"] == 42
    assert baseline["total_cache_read_tokens"] == 0
    assert baseline["total_cache_write_tokens"] == 0

    # The fold: every aux tier is added on top of the agent-stream totals.
    assert folded["total_input_tokens"] == baseline["total_input_tokens"] + aux_in
    assert folded["total_output_tokens"] == baseline["total_output_tokens"] + aux_out
    assert (
        folded["total_cache_read_tokens"]
        == baseline["total_cache_read_tokens"] + aux_cr
    )
    assert (
        folded["total_cache_write_tokens"]
        == baseline["total_cache_write_tokens"] + aux_cw
    )

    # total_tokens stays the input+output sum AFTER the fold (the aux tokens are in it).
    assert folded["total_tokens"] == folded["total_input_tokens"] + folded[
        "total_output_tokens"
    ]
    assert folded["total_tokens"] == baseline["total_tokens"] + aux_in + aux_out


@pytest.mark.asyncio
async def test_single_aux_source_folds_independently() -> None:
    """Each aux source folds on its own — a planner-only run adds exactly the planner
    tokens (guards against the fold only summing when BOTH sinks fire)."""
    baseline = _pipeline_complete(await _drive_with_aux("user_stories", []))
    planner_only = _pipeline_complete(
        await _drive_with_aux("user_stories", [_PLANNER_USAGE])
    )

    assert (
        planner_only["total_input_tokens"]
        == baseline["total_input_tokens"] + _PLANNER_USAGE["input_tokens"]
    )
    assert (
        planner_only["total_output_tokens"]
        == baseline["total_output_tokens"] + _PLANNER_USAGE["output_tokens"]
    )
    assert (
        planner_only["total_cache_read_tokens"]
        == baseline["total_cache_read_tokens"] + _PLANNER_USAGE["cache_read_tokens"]
    )
    assert (
        planner_only["total_cache_write_tokens"]
        == baseline["total_cache_write_tokens"] + _PLANNER_USAGE["cache_write_tokens"]
    )

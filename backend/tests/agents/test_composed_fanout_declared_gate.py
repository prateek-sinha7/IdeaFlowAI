"""ISS-131 regression — a declared ``gates:[human]`` on a composed fan-out step.

``engine.py:2470`` (pre-step) and ``:2799``/``:3026`` (the current line numbers) pass
``inline_gated=self._should_gate(spec, ectx)`` into ``_evaluate_gates`` so a step that
BOTH declares ``gates:[human]`` AND has its agent in the inline gate set does not
double-prompt (an empty pre-step payload, then a real post-step one). ``_should_gate``
predicts whether the INLINE ``_run_agent`` → ``_run_review_gate`` path will cover this
agent id — but for a ``fanout_batch`` step the strategy replaces the step's own inline
``_run_agent`` dispatch entirely (it spawns per-task children instead), so the inline
gate never actually fires for the step's own invocation. The stale ``True`` prediction
then makes ``_evaluate_gates`` skip the declared gate too: the step gets **no gate at
all**, silently.

Reuses the Path-B composed-fan-out harness from ``test_composed_fanout.py`` (a
user-COMPOSED worker, since the only two file-manifest fan-out steps declare
``gates: []`` — this defect is reachable only via a composed selection, per the card).
The only divergences: the worker's selection declares ``gates: ["human"]``, the run
opts the worker into ``gate_agent_ids``, and ``_run_review_gate`` is a RECORDING no-op
(not the silent no-op the original harness uses) so the test can see whether the
declared gate ever actually reached it.

Offline-safe: scripted model only, same as the harness it borrows from.
"""

from __future__ import annotations

import uuid

import pytest

from tests.agents._scripted_model import _RUNS_ROOT
from tests.agents.test_composed_fanout import (
    _FIXTURE_ID,
    _PRODUCER_ID,
    _WORKER_ID,
    _PartWritingModel,
    _build_base_compiled,
    _load_fixture_specs,
    _scripts_for,
)

_SELECTIONS_WITH_DECLARED_GATE: dict = {
    _WORKER_ID: {
        "strategy": "fanout_batch",
        "task_source": {
            "kind": "parsed",
            "parser": "heading_tasks",
            "source_step": _PRODUCER_ID,
        },
        "fanout": {"mode": "parallel", "max_parallel": 3},
        "tools": {"read_files": True, "write_files": True, "exec": False},
        # The declared gate under test (ISS-131). The worker's AGENT.md carries no
        # ``gate: Human_Gate`` — it is gated ONLY via this declared list plus the
        # per-run ``gate_agent_ids`` opt-in passed to ``execute()`` below.
        "gates": ["human"],
    }
}


async def _drive_with_declared_gate() -> tuple[list[dict], list[str]]:
    """Same harness as ``test_composed_fanout._drive_composed_fanout``, except the
    worker declares a gate, is opted into ``gate_agent_ids``, and ``_run_review_gate``
    RECORDS its calls instead of silently no-opping them.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    import agents.registry as registry_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.loader import _SPEC_CACHE

    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = _load_fixture_specs()  # [producer, worker] (sorted by order)
    spec_ids = [s.id for s in specs]
    membership_specs = [s for s in specs if s.id != _WORKER_ID]

    _orig_compile = engine_mod.compile_for_run
    _orig_resolve_alias = engine_mod.resolve_alias

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        if pipeline_type == _FIXTURE_ID:
            return _build_base_compiled()
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    def _patched_resolve_alias(pipeline_type, _orig=_orig_resolve_alias):
        if pipeline_type == _FIXTURE_ID:
            return _FIXTURE_ID
        return _orig(pipeline_type)

    _orig_get_pipeline_agents = registry_mod.get_pipeline_agents

    def _patched_get_pipeline_agents(pipeline_type, _orig=_orig_get_pipeline_agents):
        if pipeline_type == _FIXTURE_ID:
            return list(membership_specs)  # producer ONLY — worker is absent
        return _orig(pipeline_type)

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = _PartWritingModel(
            _scripts_for(agent_id), is_worker=(agent_id == _WORKER_ID)
        )
        return _orig_create_runner(agent_id, ctx, **kw)

    for s in specs:
        _SPEC_CACHE[s.id] = s

    engine_mod.compile_for_run = _patched_compile
    engine_mod.resolve_alias = _patched_resolve_alias
    registry_mod.get_pipeline_agents = _patched_get_pipeline_agents
    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    gated_agent_ids: list[str] = []

    async def _recording_gate(*, agent_id, **kw):
        # RECORDING, not silent: this is what proves whether the declared gate
        # ever reached the review-gate delegate. Yields nothing → GateOutcome
        # collapses to GATE_PASS (see HumanGate.evaluate_stream), so a fixed run
        # still completes instead of hanging on an approval that never comes.
        gated_agent_ids.append(agent_id)
        return
        yield  # pragma: no cover — makes this an async generator

    engine._run_review_gate = _recording_gate  # type: ignore[assignment]

    events: list[dict] = []
    run_id = f"composedfangate-{uuid.uuid4().hex[:8]}"
    try:
        async for ev in engine.execute(
            agents=list(specs),  # INCLUDES the worker
            user_message="Fan out three file writers from a composed selection.",
            pipeline_run_id=run_id,
            pipeline_type=_FIXTURE_ID,
            user_id="composedfangate-user",
            gate_agent_ids=[_WORKER_ID],
            selections=_SELECTIONS_WITH_DECLARED_GATE,
        ):
            events.append(ev)
    finally:
        engine_mod.compile_for_run = _orig_compile
        engine_mod.resolve_alias = _orig_resolve_alias
        registry_mod.get_pipeline_agents = _orig_get_pipeline_agents
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        for sid in spec_ids:
            _SPEC_CACHE.pop(sid, None)

    return events, gated_agent_ids


@pytest.mark.issue("ISS-131")
@pytest.mark.asyncio
async def test_declared_human_gate_fires_on_a_composed_fanout_step() -> None:
    """ISS-131 — a fan-out step's declared human gate must not be silently deduped
    against a stale inline-gate prediction.

    The worker step declares ``gates: [human]`` AND is opted into ``gate_agent_ids``,
    so ``_should_gate(spec, ectx)`` predicts the inline review gate covers it — but its
    strategy is ``fanout_batch``, which never invokes the step's own inline
    ``_run_agent``. Correct behaviour: the declared gate still fires (the inline
    prediction is not true for a fan-out step), so ``_run_review_gate`` is reached for
    the worker. Today it is skipped instead — the step gets NO gate at all.
    """
    events, gated_agent_ids = await _drive_with_declared_gate()
    assert events, "composed fan-out with a declared gate produced no events"
    errors = [e for e in events if e.get("type") == "error"]
    assert not errors, f"run errored: {errors}"

    assert _WORKER_ID in gated_agent_ids, (
        "the declared gates:[human] fan-out step never reached _run_review_gate — "
        f"the stale inline_gated prediction skipped it (ISS-131); saw {gated_agent_ids}"
    )

"""ISS-016 non-transient error — the end-to-end (DB-touching) half.

Split out of ``tests/unit/agents/test_model_fallback.py::test_non_transient_propagates``,
which asserted the contract at two levels:

  1. per-agent — a non-throttle never advances the model chain (only the primary
     runner is ever built) and surfaces an ``agent_error`` with no empty
     ``agent_complete``. Zero-I/O, so it STAYS in the unit suite.
  2. end-to-end — a single-agent run whose only agent errors collapses to
     ``pipeline_failed`` (F3 terminal block) and never emits ``pipeline_complete``.
     This drives the full ``ExecutionEngine.execute()``, which opens a real
     ``SessionLocal()`` to persist run events, so the unit-isolation guard in
     ``tests/unit/conftest.py`` rejects it. That half lives HERE.

Per the test-structure standard: "If a test needs a real DB AND has heavy logic,
split it: logic → unit (mock repo), persistence → integration."

Offline (scripted model, no Bedrock) — but NOT zero-I/O.
"""

from __future__ import annotations

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# (no Postgres / no creds) BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import (  # noqa: E402  (import-for-side-effects order)
    ScriptedFakeChatModel,
    ScriptedNonTransientError,
)

# The same real catalog id the unit half uses as the primary (standard cost class).
PRIMARY_STANDARD = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"


async def _drive_execute_single_non_transient(*, primary: str):
    """Drive the FULL ``ExecutionEngine.execute()`` for a single text-only agent whose
    runner hits a non-transient error, returning the emitted event list.

    Patches ``create_runner`` so the agent's runner is built on a
    ``ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())``: the real
    ``DeepAgentRunner`` swallows that non-throttle exception into a
    ``{"type":"error"}`` event (deep_agent_runner.py:507-527), which the engine's
    ISS-016 ``error`` arm consumes → marks the agent failed (no completion) → the
    single-agent run collapses to ``pipeline_failed`` via the F3 terminal block.
    """
    import uuid

    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings
    from tests.agents._scripted_model import _RUNS_ROOT

    _settings.RUNS_ROOT = _RUNS_ROOT

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)
    _orig_compile = engine_mod.compile_for_run

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())
        return _orig_create_runner(agent_id, ctx, **kw)

    # Skip the Deep-Planner model call (offline) — mirror test_pipeline_failure_semantics.
    def _patched_compile(pipeline_type, _orig=_orig_compile):
        compiled = _orig(pipeline_type)
        compiled.planner = "skip"
        return compiled

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    engine_mod.compile_for_run = _patched_compile

    engine = ExecutionEngine()

    async def _noop_dual_write(*a, **k):
        return None

    engine._dual_write_artifact = _noop_dual_write  # type: ignore[assignment]

    spec = get_pipeline_agents("user_stories")[0]  # a single text-only agent
    run_id = str(uuid.uuid4())
    events: list[dict] = []
    try:
        async for ev in engine.execute(
            agents=[spec],
            user_message="Build me a thing.",
            pipeline_run_id=run_id,
            pipeline_type="user_stories",
            session_id="non-transient-test",
        ):
            events.append(ev)
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile

    return events, spec.id, engine, run_id


@pytest.mark.asyncio
async def test_non_transient_single_agent_run_ends_pipeline_failed() -> None:
    """End-to-end half of ISS-016: a single-agent run whose only agent hits a
    non-transient error collapses to ``pipeline_failed`` (F3 terminal block) and
    NEVER rides through as a clean ``pipeline_complete``.

    Pre-fix the engine dropped the runner's ``{"type":"error"}`` event, so the run
    reported success with an empty deliverable. The per-agent half of this contract
    (no model switch on a non-throttle, ``agent_error`` surfaced, no empty
    ``agent_complete``) is asserted by
    ``tests/unit/agents/test_model_fallback.py::test_non_transient_propagates``.
    """
    full_events, agent_id, engine, run_id = await _drive_execute_single_non_transient(
        primary=PRIMARY_STANDARD,
    )
    failed = [e for e in full_events if e.get("type") == "pipeline_failed"]
    assert (
        len(failed) == 1
    ), f"single-agent non-transient run must end pipeline_failed: {full_events}"
    assert [
        e for e in full_events if e.get("type") == "pipeline_complete"
    ] == [], "a totally-failed run must NEVER emit pipeline_complete (ISS-016/F3)"
    assert agent_id in failed[0]["data"]["agents_failed"]
    assert engine._state_machine.get_state(run_id) == "failed"

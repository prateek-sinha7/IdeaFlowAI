"""tests/agents/test_engine_runner_error_arm.py — ISS-016 fault-injection (16-01).

Proves the ISS-016 fix END-TO-END, from the runner's swallowed ``{"type":"error"}``
event through the engine's new ``_run_agent`` ``error`` consume-arm to the terminal
``pipeline_failed`` / ``status:degraded`` semantics — with NO empty ``agent_complete``
for a failed agent.

The lever is fully offline + deterministic: ``ScriptedFakeChatModel([],
raise_exc=ScriptedNonTransientError())`` raises a ``ValidationException`` analogue
PRE-token (``_scripted_model.py:106-176``). The REAL ``DeepAgentRunner`` swallows that
non-throttle exception into ``yield {"type":"error","error":str(exc)}`` and returns
(``deep_agent_runner.py:507-527``) — exactly the live ISS-016 mechanism — so the
engine's new ``error`` arm (engine.py ``_run_agent``) consumes it, marks the agent
failed, and SKIPS the result-append + ``agent_complete``. The existing F3 terminal
block (``engine.py:1713-1739`` all-fail / ``:1885-1887`` partial) then maps the
``_failed_agent_ids`` to ``pipeline_failed`` (every agent) / ``pipeline_complete``
``status="degraded"`` (some agents).

This is NOT a unit stub of ``_run_agent`` (that is test_pipeline_failure_semantics.py):
here the REAL per-agent runner path runs, so the new consume-arm is genuinely exercised.

Offline — patched ``create_runner`` injects the scripted model; no Bedrock, no SSO.
"""

from __future__ import annotations

import uuid

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# (no Postgres / no creds) BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import (  # noqa: E402  (import-for-side-effects order)
    ScriptedFakeChatModel,
    ScriptedNonTransientError,
    _ScriptedTurn,
    _RUNS_ROOT,
)


def _text_turn(tag: str) -> list[_ScriptedTurn]:
    """A deterministic text-only turn embedding ``tag`` (a completing agent)."""
    return [_ScriptedTurn(texts=[f"completed on {tag}. "], usage=(5, 3))]


async def _drive_execute(*, error_ids: set[str]):
    """Drive the FULL ``ExecutionEngine.execute()`` for a 2-agent user_stories subset
    through the REAL ``_run_agent`` path, returning ``(events, engine, run_id, ids)``.

    ``create_runner`` is patched so an agent whose id is in ``error_ids`` is built on a
    ``ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())`` (its runner
    swallows the non-throttle into a ``{"type":"error"}`` event → the engine's ISS-016
    arm fires); every other agent streams a deterministic completing turn.

    The Deep-Planner model call is skipped offline by flipping ``compiled.planner`` to
    "skip" (mirrors tests/unit/test_pipeline_failure_semantics.py).
    """
    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = get_pipeline_agents("user_stories")[:2]
    assert len(specs) == 2, "harness expects two user_stories agents"
    ids = [s.id for s in specs]

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)
    _orig_compile = engine_mod.compile_for_run

    def _patched_create_runner(agent_id, ctx, **kw):
        if agent_id in error_ids:
            ctx.model = ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())
        else:
            ctx.model = ScriptedFakeChatModel(_text_turn(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        compiled = _orig(pipeline_type)
        compiled.planner = "skip"
        return compiled

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    engine_mod.compile_for_run = _patched_compile

    engine = ExecutionEngine()

    # No-op the typed dual-write (no workflow_runs FK row in this offline unit context).
    async def _noop_dual_write(*a, **k):
        return None

    engine._dual_write_artifact = _noop_dual_write  # type: ignore[assignment]

    run_id = str(uuid.uuid4())
    events: list[dict] = []
    try:
        async for ev in engine.execute(
            agents=specs,
            user_message="build a backlog",
            pipeline_run_id=run_id,
            pipeline_type="user_stories",
            session_id="iss016-arm-test",
        ):
            events.append(ev)
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile

    return events, engine, run_id, ids


def _events_of(events: list[dict], etype: str) -> list[dict]:
    return [e for e in events if e.get("type") == etype]


def _agent_complete_ids(events: list[dict]) -> set[str]:
    return {
        e["data"].get("agent_id")
        for e in _events_of(events, "agent_complete")
    }


# ────────────────────────────────────────────────────────────────────────────
# All agents error → pipeline_failed (no empty agent_complete, no complete)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_agents_error_ends_pipeline_failed() -> None:
    """Every agent's runner raises ``ScriptedNonTransientError`` → the run emits ≥1
    ``agent_error``, a single terminal ``pipeline_failed`` with a populated
    ``agents_failed``, NO ``agent_complete`` for the failed agents, and NO
    ``pipeline_complete`` (the empty agent_complete at engine.py:2619 is skipped)."""
    # Learn the agent ids first (a no-error drive), then re-drive flagging ALL of them.
    _events, _engine, _run_id, ids = await _drive_execute(error_ids=set())
    events, engine, run_id, ids = await _drive_execute(error_ids=set(ids))

    # ≥1 agent_error surfaced (the runner error was consumed, not dropped).
    errs = _events_of(events, "agent_error")
    assert errs, f"expected ≥1 agent_error, got: {events}"

    # Exactly one terminal pipeline_failed with the failed agents listed.
    failed = _events_of(events, "pipeline_failed")
    assert len(failed) == 1, f"expected exactly one pipeline_failed: {events}"
    data = failed[0]["data"]
    assert data["agents_failed"], "pipeline_failed must list the failed agents"
    assert set(data["agents_failed"]) == set(ids)
    assert data["agents_completed"] == 0

    # No pipeline_complete for a totally-failed run.
    assert _events_of(events, "pipeline_complete") == [], (
        "a totally-failed run must NEVER emit pipeline_complete (ISS-016)"
    )
    # No (empty) agent_complete for any failed agent.
    assert _agent_complete_ids(events) & set(ids) == set(), (
        "ISS-016: a failed agent must NOT emit an (empty) agent_complete"
    )

    assert engine._state_machine.get_state(run_id) == "failed"


# ────────────────────────────────────────────────────────────────────────────
# One agent errors, one completes → degraded pipeline_complete
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_partial_error_ends_degraded() -> None:
    """ONE agent errors, the other completes normally → the run emits
    ``pipeline_complete`` carrying ``status == "degraded"`` + the errored agent in
    ``agents_failed``, the completing agent's ``agent_complete`` IS present, and NO
    ``pipeline_failed`` fires."""
    # First learn the ids (a no-error drive), then re-drive flagging only the first.
    _events, _engine, _run_id, ids = await _drive_execute(error_ids=set())
    failed_id, completed_id = ids[0], ids[1]

    events, engine, run_id, ids = await _drive_execute(error_ids={failed_id})

    # No total-collapse terminal — a partial failure completes (degraded).
    assert _events_of(events, "pipeline_failed") == [], (
        "a partially-failed run completes (degraded), not pipeline_failed"
    )
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1, f"expected one pipeline_complete: {events}"

    data = complete[0]["data"]
    assert data["status"] == "degraded", f"expected degraded: {data!r}"
    assert data["agents_failed"] == [failed_id]
    assert data["agents_completed"] == 1

    # The errored agent surfaced an agent_error and produced NO agent_complete; the
    # surviving agent's agent_complete IS present.
    err_ids = {e["data"].get("agent_id") for e in _events_of(events, "agent_error")}
    assert failed_id in err_ids
    completes = _agent_complete_ids(events)
    assert completed_id in completes, "the completing agent must emit agent_complete"
    assert failed_id not in completes, (
        "ISS-016: the failed agent must NOT emit an (empty) agent_complete"
    )

    assert engine._state_machine.get_state(run_id) == "completed"

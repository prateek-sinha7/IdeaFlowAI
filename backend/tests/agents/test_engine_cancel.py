"""tests/agents/test_engine_cancel.py — T7 (spec 018 / FR-009): the run-teardown
``finally`` in ``ExecutionEngine._execute_impl`` releases this run's Playwright
session on EVERY exit path.

tasks.md names this file as T7's own verify command, but no task in the 018
ledger owns creating it (T10 owns ``test_playwright_tools.py``, T11 owns
``test_playwright_session.py``) — a drift the previous review round caught. T11's
suite already proves ``playwright_session.release()`` itself is idempotent,
no-op-safe, and swallows a failure; what was still unproven anywhere in the repo
is that the REAL ``ExecutionEngine`` generator actually reaches that call on
every one of its exit shapes. That is what this file adds.

Offline throughout — reuses the existing scripted-model harnesses rather than
building new fixtures (INV-12):
  * ``tests.agents.test_engine_runner_error_arm`` for two full, PUBLIC
    ``engine.execute()`` drives — a normal completion and the ISS-023
    cooperative per-chunk cancel.
  * ``tests.agents.test_conditional_loop_budget_t24`` for a real ``BudgetExceeded``
    abort (a SECOND, structurally distinct handled-except shape — no
    cancel_event branching at all — proving the ``finally`` fires because it is
    attached to the ``try`` itself, not duplicated into each ``except``).
  * A genuine (non-cooperative) cancel and a ``GeneratorExit`` are driven
    against ``_execute_impl`` DIRECTLY rather than through the ``execute()``
    wrapper. Closing/throwing into ``execute()``'s OWN generator would only
    reach the nested ``_execute_impl`` generator via CPython's async-generator
    GC finalizer — a scheduled, non-deterministic cleanup — which would make
    those two cases racy. Calling ``.athrow()`` / ``.aclose()`` directly on
    ``_execute_impl``'s generator, once it is confirmed suspended INSIDE the
    guarded try (past ``agent_start``), delivers the exception synchronously at
    its real suspend point — deterministic, and still the exact production
    method the ``try/except/finally`` under test lives in.

``FanoutWorkerFailed`` (the third handled abort) is not separately re-driven
live here: it is byte-for-byte the same shape as the ``BudgetExceeded`` except
block below (persist → yield a terminal → bare ``return``), so the same
evidence that proves the ``finally`` is try-attached (not except-duplicated)
covers it by construction; building a live fan-out-failure fixture just to
re-demonstrate identical control flow was judged not worth the added fixture
weight (ponytail: sampling two structurally-distinct handled aborts is enough
to prove the mechanism; add a third live drive if that assumption is ever
challenged).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

# Importing this harness sets RUNS_ROOT + forces the InMemory checkpointer
# BEFORE app.core.config loads — keep this import first (mirrors the sibling
# files this one reuses fixtures from).
from tests.agents._scripted_model import (  # noqa: E402
    ScriptedFakeChatModel,
    _RUNS_ROOT,
    _ScriptedTurn,
)
from tests.agents import _scripted_model as _sm  # noqa: E402
from tests.agents.test_conditional_loop_budget_t24 import (  # noqa: E402
    _always_retry_scripts_for,
)
from tests.agents.test_engine_runner_error_arm import (  # noqa: E402
    _drive_execute,
    _drive_execute_with_midstream_cancel,
    _events_of,
)


def _install_release_spy(monkeypatch, *, raise_exc: Exception | None = None) -> list[str]:
    """Wrap the REAL ``playwright_session.release`` to record every call, while
    preserving its no-op/never-raises behaviour — unless ``raise_exc`` is given,
    which proves the engine's own defensive wrapper swallows a misbehaving
    release instead of letting it mask the exit it's attached to (AC5)."""
    from app.agents import playwright_session

    calls: list[str] = []
    orig_release = playwright_session.release

    async def _spy(run_id: str) -> None:
        calls.append(run_id)
        if raise_exc is not None:
            raise raise_exc
        await orig_release(run_id)

    monkeypatch.setattr(playwright_session, "release", _spy)
    return calls


async def _advance_to(gen, etype: str, *, cap: int = 50) -> dict:
    """Consume ``gen`` until it yields an event of type ``etype`` (inclusive),
    returning that event. Used to confirm the generator is suspended INSIDE the
    guarded try (past ``agent_start``) before closing/throwing into it."""
    for _ in range(cap):
        ev = await gen.__anext__()
        if ev.get("type") == etype:
            return ev
    raise AssertionError(f"never observed event type {etype!r} within {cap} events")


def _build_single_agent_engine(monkeypatch):
    """The shared ``_execute_impl``-direct setup for the genuine-cancel and
    GeneratorExit tests below: one ``user_stories`` agent, planner skipped, a
    scripted model that streams several chunks (so the generator's suspend
    point lands on ``agent_start`` well before the agent completes)."""
    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT
    specs = get_pipeline_agents("user_stories")[:1]
    assert len(specs) == 1

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)
    _orig_compile = engine_mod.compile_for_run

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(
            [_ScriptedTurn(texts=["first ", "second ", "third"], usage=(5, 3))]
        )
        return _orig_create_runner(agent_id, ctx, **kw)

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        compiled = _orig(pipeline_type)
        compiled.planner = "skip"
        return compiled

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    engine_mod.compile_for_run = _patched_compile

    def _restore():
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile

    return ExecutionEngine(), specs, _restore


# ════════════════════════════════════════════════════════════════════════════
# Normal completion — a run that never launches a browser (nearly every run)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_normal_completion_releases_session_and_is_noop(monkeypatch) -> None:
    """AC2/AC7: driving the REAL public ``ExecutionEngine.execute()`` to a clean
    completion still calls the T7 release hook exactly once for this run — and
    since nothing ever acquired a browser, it is a true no-op (the run id never
    entered the session registry)."""
    from app.agents import playwright_session

    calls = _install_release_spy(monkeypatch)
    events, _engine, run_id, _ids = await _drive_execute(error_ids=set())

    assert _events_of(events, "pipeline_complete"), f"run did not complete: {events}"
    assert calls == [run_id], f"expected exactly one release for {run_id}, got {calls}"
    assert run_id not in playwright_session._SESSIONS


@pytest.mark.asyncio
async def test_release_failure_does_not_mask_normal_completion(monkeypatch) -> None:
    """AC5: a release() that raises must not mask the exit it's attached to —
    engine.py's own try/except around the call swallows it (logs a warning), so
    a normal completion still completes cleanly."""
    calls = _install_release_spy(monkeypatch, raise_exc=RuntimeError("boom"))
    events, _engine, _run_id, _ids = await _drive_execute(error_ids=set())

    assert calls, "release was never even attempted"
    assert _events_of(events, "pipeline_complete"), (
        "a raising release() must not mask a normal completion"
    )


# ════════════════════════════════════════════════════════════════════════════
# CancelledError — the two ISS-023 branches (cooperative return vs genuine raise)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cooperative_cancel_releases_and_execute_does_not_raise(monkeypatch) -> None:
    """AC3/AC6: the ISS-023 cooperative per-chunk cancel (Stop button —
    cancel_event IS set) still RETURNS rather than re-raising, so the public
    ``execute()`` async-for ends normally — and the T7 release still fires on
    that return exit."""
    calls = _install_release_spy(monkeypatch)
    events, _engine, run_id, cancel_event = await _drive_execute_with_midstream_cancel()

    assert cancel_event.is_set(), "harness must have armed the cooperative cancel"
    assert _events_of(events, "pipeline_cancelled")
    assert calls == [run_id]


@pytest.mark.asyncio
async def test_genuine_cancel_still_raises_and_releases(monkeypatch) -> None:
    """AC3/AC6: a GENUINE destructive cancel (no cancel_event — the
    WebSocketDisconnect / defensive-fallback case) must still RE-RAISE
    CancelledError after yielding the one ``pipeline_cancelled`` (ISS-023), so
    the disconnect cleanup that depends on the propagating exception still
    runs — and the T7 release must still have fired before that exception
    finishes leaving the generator."""
    calls = _install_release_spy(monkeypatch)
    engine, specs, restore = _build_single_agent_engine(monkeypatch)
    run_id = str(uuid.uuid4())

    try:
        gen = engine._execute_impl(
            agents=specs,
            user_message="build a backlog",
            pipeline_run_id=run_id,
            pipeline_type="user_stories",
            session_id="t7-genuine-cancel-test",
        )
        await _advance_to(gen, "agent_start")
        # cancel_event is None here (never supplied) — the genuine, non-cooperative
        # branch. The except block yields pipeline_cancelled once (returned by this
        # athrow), then the NEXT resumption hits `if cancel_event is not None and
        # cancel_event.is_set(): return` (False) and falls through to the bare
        # `raise`, re-raising on the following __anext__.
        cancelled_ev = await gen.athrow(asyncio.CancelledError())
        assert cancelled_ev["type"] == "pipeline_cancelled"
        with pytest.raises(asyncio.CancelledError):
            await gen.__anext__()
    finally:
        restore()

    assert calls == [run_id]


# ════════════════════════════════════════════════════════════════════════════
# GeneratorExit — the consumer abandons the run (e.g. a WebSocket disconnect
# that stops draining without an explicit cancel)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generator_exit_releases_session(monkeypatch) -> None:
    """AC4: closing the run generator while it is suspended mid-dispatch (no
    exception raised at all — just abandonment) must still run the T7
    ``finally`` and release the session."""
    calls = _install_release_spy(monkeypatch)
    engine, specs, restore = _build_single_agent_engine(monkeypatch)
    run_id = str(uuid.uuid4())

    try:
        gen = engine._execute_impl(
            agents=specs,
            user_message="build a backlog",
            pipeline_run_id=run_id,
            pipeline_type="user_stories",
            session_id="t7-generator-exit-test",
        )
        await _advance_to(gen, "agent_start")
        await gen.aclose()
    finally:
        restore()

    assert calls == [run_id]


# ════════════════════════════════════════════════════════════════════════════
# BudgetExceeded — a second, structurally distinct handled abort (no
# cancel_event branching at all) proving the finally is try-attached
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_budget_exceeded_releases_session(monkeypatch) -> None:
    """AC3: reuses the existing ``ex_A1_loop`` always-retry fixture (spec 014
    T24) that already drives a real ``BudgetExceeded`` abort end-to-end through
    the public ``execute()``. This except block has NO cancel_event branch at
    all (persist → yield ``budget_aborted`` → bare ``return``) — a release here
    proves the ``finally`` fires because it's attached to the try itself, not
    duplicated into each individual except."""
    calls = _install_release_spy(monkeypatch)

    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _always_retry_scripts_for
    try:
        events = await _sm._drive("ex_A1_loop")
    finally:
        _sm._scripts_for = orig_scripts_for

    budget_events = [e for e in events if e.get("type") == "budget_aborted"]
    assert len(budget_events) == 1, events
    run_id = budget_events[0]["data"]["pipeline_run_id"]
    assert calls == [run_id]

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

import asyncio
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


@pytest.mark.issue("ISS-632")
@pytest.mark.xfail(reason="ISS-632 unfixed", strict=True)
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


@pytest.mark.issue("ISS-632")
@pytest.mark.xfail(reason="ISS-632 unfixed", strict=True)
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


# ════════════════════════════════════════════════════════════════════════════
# ISS-028 — same-agent task_loop partial failure → DEGRADED (not clean complete)
# ════════════════════════════════════════════════════════════════════════════
#
# The prototype build step runs ONE agent_id (``prototype-build``) across all tasks
# via the real ``task_loop`` strategy. Before the fix, the terminal degraded decision
# subtracted on agent_id alone — so when task 1 succeeded (appending a prototype-build
# result) and task 2 hard-errored (adding prototype-build to _failed_agent_ids without
# a result), the subtraction zeroed it and the run emitted a CLEAN ``pipeline_complete``
# over a half-built deliverable. The fix keys the decision on (agent_id, task_number),
# so the unrecovered task-2 failure survives → ``status:degraded``.
#
# This drives the REAL ``ExecutionEngine.execute()`` for the ``prototype`` pipeline
# through the REAL ``TaskLoopStrategy`` + ``_run_agent`` per-task loop. The scripted
# ``prototype-plan`` emits exactly two ``## Task N:`` blocks (→ 2 build tasks); a
# per-invocation counter injects ``ScriptedNonTransientError`` on the SECOND
# ``prototype-build`` invocation only (its runner swallows it into ``{"type":"error"}``
# → the engine's ISS-016 arm fires → no result-append for task 2). The validation
# fix-loop is no-op'd so the only ``prototype-build`` create_runner calls are the two
# task invocations (call #2 == task 2), keeping the injection deterministic.


def _prototype_build_html_turn() -> list[_ScriptedTurn]:
    """The successful prototype-build task turn — writes prototype.html + reports done."""
    import json as _j

    html = "<!doctype html><html><body><section data-page='dashboard'>hi</section></body></html>"
    return [
        _ScriptedTurn(
            texts=["Building the page. "],
            tool_calls=[
                ("write_file", _j.dumps({"file_path": "prototype.html", "content": html}), "c_wf"),
                ("report_task_complete",
                 _j.dumps({"task_number": 1, "task_title": "Build", "summary": "did it"}), "c_rtc"),
            ],
            usage=(50, 20),
        ),
        _ScriptedTurn(texts=["Done."], usage=(10, 5)),
    ]


async def _drive_prototype_with_build_task_failure(*, fail_on_build_call: int):
    """Drive the REAL ``prototype`` ``execute()`` through the task_loop, failing the
    ``fail_on_build_call``-th ``prototype-build`` invocation. Returns the event list.

    Mirrors ``_scripted_model._drive`` offline scaffolding (planner/gate/fix-loop no-ops,
    clarify off, RUNS_ROOT temp, od_context for injects) but adds the per-invocation
    error injection on ``prototype-build``.
    """
    import uuid as _uuid

    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.kernel_services import KernelServices
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    from tests.agents._scripted_model import _scripts_for

    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = get_pipeline_agents("prototype")

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)
    _orig_compile = engine_mod.compile_for_run
    _orig_fix_loop = KernelServices.run_validation_fix_loop

    _build_calls = {"n": 0}

    def _patched_create_runner(agent_id, ctx, **kw):
        if agent_id == "prototype-build":
            _build_calls["n"] += 1
            if _build_calls["n"] == fail_on_build_call:
                ctx.model = ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())
            else:
                ctx.model = ScriptedFakeChatModel(_prototype_build_html_turn())
        else:
            ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    # No-op the Both-validation fix-loop so the ONLY prototype-build create_runner calls
    # are the two task invocations (no fix sub-agent eats a call slot — deterministic).
    async def _noop_fix_loop(self, *a, **k):
        return None

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    engine_mod.compile_for_run = _patched_compile
    KernelServices.run_validation_fix_loop = _noop_fix_loop  # type: ignore[assignment]

    engine = ExecutionEngine()

    # NOTE: do NOT no-op _dual_write_artifact here. The task_loop reads the planner's
    # task plan from the IN-MEMORY typed graph (ectx.artifacts), which _dual_write_artifact
    # populates BEFORE its best-effort DB write — stubbing it to a no-op would empty the
    # graph, so prototype-plan's 2-task plan would never reach the build loop (it would run
    # ONE empty-block task). The DB half degrades on the offline FK miss (logged), exactly
    # as _scripted_model._drive relies on.

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    od_context = {
        "template_body": "## Workflow\nUse .card and .grid. Build pages into <section data-page>.",
        "template_id": "web-prototype",
        "ds_id": "default",
        "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;}",
        "craft_block": "Keep markup semantic; wire every nav link.",
        "is_design_system_required": True,
    }

    run_id = f"iss028-{_uuid.uuid4().hex[:8]}"
    events: list[dict] = []
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Build me a task manager.",
            pipeline_run_id=run_id,
            pipeline_type="prototype",
            user_id="iss028-user",
            od_context=od_context,
            gate_agent_ids=[],
        ):
            events.append(ev)
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile
        KernelServices.run_validation_fix_loop = _orig_fix_loop  # type: ignore[assignment]

    return events, engine, run_id


@pytest.mark.asyncio
async def test_task_loop_task2_hard_error_ends_degraded() -> None:
    """ISS-028: prototype build task 1 succeeds, task 2 hard-errors → the run ends
    ``pipeline_complete`` carrying ``status:degraded`` with ``prototype-build`` in
    ``agents_failed`` (the half-built deliverable is reported degraded), and NOT a
    clean ``pipeline_complete`` (the pre-fix agent_id-collapse bug)."""
    events, engine, run_id = await _drive_prototype_with_build_task_failure(
        fail_on_build_call=2
    )

    # The build agent ran twice (2 tasks) — task 2 surfaced an agent_error.
    err_ids = {e["data"].get("agent_id") for e in _events_of(events, "agent_error")}
    assert "prototype-build" in err_ids, (
        f"expected a prototype-build agent_error from the failed task 2; got: "
        f"{[ (e['type'], e['data'].get('agent_id')) for e in events ]}"
    )

    # A partial failure COMPLETES (degraded) — it must NOT collapse to pipeline_failed
    # (other agents + task 1 completed).
    assert _events_of(events, "pipeline_failed") == [], (
        "a partially-failed task_loop completes degraded, not pipeline_failed"
    )
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1, f"expected one pipeline_complete: {events}"
    data = complete[0]["data"]

    # THE FIX: a same-agent task_loop partial failure is now degraded, not clean.
    assert data.get("status") == "degraded", (
        f"ISS-028: task 1 ok + task 2 hard-error must end DEGRADED, not a clean "
        f"pipeline_complete — got status={data.get('status')!r}, data={data!r}"
    )
    assert "prototype-build" in (data.get("agents_failed") or []), (
        f"the failed build agent must be listed in agents_failed; got {data!r}"
    )
    assert engine._state_machine.get_state(run_id) == "completed"


@pytest.mark.asyncio
async def test_task_loop_all_tasks_succeed_stays_clean() -> None:
    """ISS-028 regression guard: when NO build task errors, the run stays a CLEAN
    ``pipeline_complete`` (no ``status:degraded`` key) — proving the new pair-keyed
    branch is DORMANT on the all-success path (the same condition the characterization
    goldens rely on for INV-3 byte-parity)."""
    # fail_on_build_call=0 ⇒ no invocation matches ⇒ both tasks succeed.
    events, engine, run_id = await _drive_prototype_with_build_task_failure(
        fail_on_build_call=0
    )

    assert _events_of(events, "agent_error") == [], (
        f"no task errored — expected zero agent_error: "
        f"{[ (e['type'], e['data'].get('agent_id')) for e in events ]}"
    )
    complete = _events_of(events, "pipeline_complete")
    assert len(complete) == 1, f"expected one pipeline_complete: {events}"
    data = complete[0]["data"]
    assert "status" not in data, (
        f"ISS-028 dormancy: an all-success task_loop must NOT carry a degraded status "
        f"key (INV-3 byte-parity); got {data!r}"
    )
    assert "agents_failed" not in data
    assert engine._state_machine.get_state(run_id) == "completed"


# ════════════════════════════════════════════════════════════════════════════
# ISS-023 — the per-chunk cooperative cancel yields pipeline_cancelled EXACTLY once
# ════════════════════════════════════════════════════════════════════════════
#
# When the Stop button sets ``cancel_event`` while an agent is mid-stream, the engine's
# per-chunk check (engine.py:2613) raises CancelledError, which lands in _execute_impl's
# outer ``except asyncio.CancelledError``. Pre-fix that handler yielded pipeline_cancelled
# AND re-raised — and the re-raise propagated out of ``execute()`` into the websocket bg
# task's own ``except CancelledError`` (_run_pipeline_to_queue), which enqueued a SECOND
# pipeline_cancelled (a discarded duplicate — the drainer breaks on the first terminal).
# The fix RETURNS instead of re-raising ON THE COOPERATIVE PATH, so ``execute()`` yields
# the one true terminal exactly once. This drives the REAL ``execute()`` and asserts the
# generator itself yields a single pipeline_cancelled (the source of the former duplicate).


class _CancelMidStreamModel(ScriptedFakeChatModel):
    """A scripted model that sets ``cancel_event`` after streaming its FIRST chunk.

    Mirrors a user clicking Stop mid-agent: the engine's per-chunk loop processes
    chunk 1 (cancel not yet set), then on the NEXT event sees ``cancel_event.is_set()``
    and raises CancelledError → the cooperative per-chunk cancel terminal. Streams
    several text pieces so there IS a 2nd event for the check to fire on.
    """

    def __init__(self, cancel_event: asyncio.Event, **kwargs):
        super().__init__(
            [_ScriptedTurn(texts=["first chunk. ", "second chunk. ", "third chunk."], usage=(5, 3))],
            **kwargs,
        )
        object.__setattr__(self, "_cancel_event", cancel_event)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for i, chunk in enumerate(super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)):
            if i == 1:
                # After the first chunk has been yielded+consumed, arm the cancel so the
                # engine's per-chunk check raises on this (the 2nd) event.
                self._cancel_event.set()
            yield chunk


async def _drive_execute_with_midstream_cancel():
    """Drive the FULL ``execute()`` for a 1-agent user_stories subset where the agent's
    model arms ``cancel_event`` mid-stream → the per-chunk cooperative cancel fires.
    Returns ``(events, engine, run_id, cancel_event)``."""
    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = get_pipeline_agents("user_stories")[:1]
    assert len(specs) == 1

    cancel_event = asyncio.Event()

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)
    _orig_compile = engine_mod.compile_for_run

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = _CancelMidStreamModel(cancel_event)
        return _orig_create_runner(agent_id, ctx, **kw)

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

    run_id = str(uuid.uuid4())
    events: list[dict] = []
    try:
        # Drive through the PUBLIC execute() (the websocket bg task's exact call shape)
        # — threading the cooperative cancel_event so the per-chunk path fires.
        async for ev in engine.execute(
            agents=specs,
            user_message="build a backlog",
            pipeline_run_id=run_id,
            pipeline_type="user_stories",
            session_id="iss023-cancel-test",
            cancel_event=cancel_event,
        ):
            events.append(ev)
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile

    # Let the deepagents middleware background tasks that ``astream_events`` spawns
    # (bridged via _GatheringFuture) settle after the mid-stream cancel, so the
    # short-lived test event loop tears them down quietly. These dangling-task /
    # GeneratorExit notices are a harness artifact of abandoning a real deepagents
    # graph mid-stream under asyncio.run — they appear identically on the pre-fix
    # re-raise path (15 vs 14) and are NOT a behavior change; the settle just trims
    # the noise. Production keeps a long-lived loop, so they cancel cleanly there.
    await asyncio.sleep(0.05)

    return events, engine, run_id, cancel_event


@pytest.mark.asyncio
async def test_per_chunk_cancel_yields_pipeline_cancelled_exactly_once() -> None:
    """ISS-023: a per-chunk cooperative cancel makes the REAL ``execute()`` yield
    EXACTLY ONE ``pipeline_cancelled`` (no re-raise → no websocket-layer duplicate),
    the run lands in the ``cancelled`` terminal state, and ``execute()`` completes
    normally (it does NOT propagate CancelledError on the cooperative path)."""
    events, engine, run_id, cancel_event = await _drive_execute_with_midstream_cancel()

    assert cancel_event.is_set(), "harness must have armed the cooperative cancel"

    cancels = _events_of(events, "pipeline_cancelled")
    assert len(cancels) == 1, (
        f"ISS-023: the cooperative per-chunk cancel must yield EXACTLY ONE "
        f"pipeline_cancelled (the engine yield), not a second discarded duplicate; "
        f"got {len(cancels)}: {[e['type'] for e in events]}"
    )
    assert cancels[0]["data"].get("pipeline_run_id") == run_id

    # No clean terminal leaked alongside the cancel.
    assert _events_of(events, "pipeline_complete") == []
    assert _events_of(events, "pipeline_failed") == []

    assert engine._state_machine.get_state(run_id) == "cancelled"


@pytest.mark.asyncio
async def test_per_chunk_cancel_execute_does_not_raise() -> None:
    """ISS-023: on the COOPERATIVE per-chunk cancel, ``execute()`` returns normally
    (its async-for ends without a CancelledError). This is precisely what stops the
    websocket bg task's ``except CancelledError`` from enqueuing the duplicate frame —
    the wire still delivers exactly one ack (the single yielded terminal above), the
    bg-task path is just no longer asked to synthesize a second one. A genuine
    destructive ``task.cancel()`` (cancel_event NOT set) is unaffected — it still
    re-raises (covered by the existing disconnect test in test_pipeline_cancel.py)."""
    # If execute() re-raised on the cooperative path, the async-for in the driver would
    # propagate CancelledError and this await would raise; reaching the assert proves it
    # completed normally.
    events, _engine, _run_id, _ce = await _drive_execute_with_midstream_cancel()
    assert any(e["type"] == "pipeline_cancelled" for e in events)

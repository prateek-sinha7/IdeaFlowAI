"""tests/agents/test_cancel_stops_resumed_run.py — ISS-084 / FIX-227 (TEST-011).

Stop must actually stop a run that crossed a backend restart.

Every resume-family driver (``resume_run`` branch (b), ``_rearm_gate_run`` branch (a),
``_replay_clarify_run``, and the user ``POST /resume`` wrapper) reaches the kernel through
ONE funnel — ``ExecutionEngine._drive_resumed_stream``. That funnel handed
``_execute_impl`` no ``cancel_event``, so the parameter bound its ``None`` default and
EVERY cooperative guard (``if cancel_event and cancel_event.is_set()``) short-circuited.
Meanwhile ``run_engine._register_resume_task`` minted an ORPHAN ``asyncio.Event`` into
``_CANCEL_EVENTS`` for exactly those runs, so ``POST /cancel`` found one, set it, and
answered ``cancelled: true``. Nobody read it. One measured run billed 7,510,082 tokens
AFTER that answer.

The tests below are the four assertions the pre-existing cancel suite never made — it
seeded ``_CANCEL_EVENTS`` itself and asserted only that the endpoint set it, i.e. the one
thing that still worked:

  * the resumed drive OBSERVES the event (and the object it observes IS the one the REST
    registry holds — object identity, which is what makes the orphan impossible to
    reintroduce);
  * it stops dispatching (zero further model calls);
  * ``pipeline_cancelled`` is EMITTED and persisted;
  * the ``workflow_runs`` row reaches a TERMINAL status — and therefore the next boot's
    ``restore_non_terminal_runs`` does NOT re-adopt it. That last one is the guard that
    matters most: a cancel that leaves the row non-terminal is not a cancel, it is a
    delayed re-run, which is exactly what happened in production.

Offline: in-memory SQLite + the scripted ``sample_wave`` model. No network, no Bedrock,
no money. Reuses ``test_restart_resume``'s ``_ResumeHarness`` rather than cloning it
(INV-12).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.agents.test_restart_resume import (  # noqa: E402
    _FIXTURE_ID,
    _ResumeHarness,
    _make_session,
    _seed_workflow_run,
)


@pytest.fixture
def registry():
    """The process-global REST run registries, emptied around each test."""
    from app.api import run_engine as rq

    rq._CANCEL_EVENTS.clear()
    rq._PIPELINE_TASKS.clear()
    yield rq
    rq._CANCEL_EVENTS.clear()
    rq._PIPELINE_TASKS.clear()


def _recording_impl(recorded: dict):
    """An ``_execute_impl`` stand-in that records its kwargs and yields nothing."""

    async def _impl(**kwargs):
        recorded.update(kwargs)
        return
        yield  # pragma: no cover — makes this an async generator

    return _impl


async def _drive(engine, run_id: str) -> None:
    """Call the resume funnel with the minimum kwargs every driver supplies."""
    await engine._drive_resumed_stream(
        run_id,
        agents=[],
        user_message="brief",
        pipeline_type="custom",
        user_id="u",
        session_id=None,
        parent_run_id=None,
        selections=None,
        start_seq=1,
        live_queue=None,
    )


# ===========================================================================
# 1. The funnel — the signal reaches the kernel
# ===========================================================================


@pytest.mark.asyncio
async def test_resume_funnel_hands_the_cancel_event_to_execute_impl():
    """ROOT CAUSE. ``_drive_resumed_stream`` must pass the resolved cancel Event down to
    ``_execute_impl`` — without it every one of the kernel's cooperative guards reads
    ``None`` and short-circuits, so no resumed run can ever be stopped.

    RED pre-fix: the funnel passes no ``cancel_event`` kwarg at all.
    """
    from agents.execution_engine.engine import ExecutionEngine

    engine = ExecutionEngine()
    event = asyncio.Event()
    engine._resume_cancel_event = lambda _run_id: event  # type: ignore[assignment]
    recorded: dict = {}
    engine._execute_impl = _recording_impl(recorded)  # type: ignore[assignment]

    await _drive(engine, "run-x")

    assert "cancel_event" in recorded, (
        "the resume funnel passed NO cancel_event to _execute_impl — every kernel "
        f"guard binds None and short-circuits. kwargs seen: {sorted(recorded)}"
    )
    assert recorded["cancel_event"] is event


@pytest.mark.asyncio
async def test_resume_funnel_is_dormant_when_the_hook_is_unset():
    """INV-3: with no app layer armed (the goldens, the offline harness, every non-app
    driver) the funnel still passes ``cancel_event=None`` — byte/event-identical."""
    from agents.execution_engine.engine import ExecutionEngine

    engine = ExecutionEngine()
    recorded: dict = {}
    engine._execute_impl = _recording_impl(recorded)  # type: ignore[assignment]

    await _drive(engine, "run-x")

    assert recorded.get("cancel_event", "MISSING") is None


@pytest.mark.asyncio
async def test_the_engine_reads_the_same_event_object_the_rest_registry_holds(registry):
    """THE ORPHAN. ``_register_resume_task`` minting its own Event is only useful if the
    engine ends up holding THAT object — object identity, not mere presence. This is the
    assertion that makes the orphan impossible to reintroduce.

    RED pre-fix: the engine holds ``None`` while ``_CANCEL_EVENTS[run_id]`` holds an
    Event nobody reads.
    """
    from agents.execution_engine.engine import ExecutionEngine

    run_id = f"iss084-{uuid.uuid4().hex[:8]}"
    registry._register_resume_task(run_id, object())  # the restore create_task site

    engine = ExecutionEngine()
    engine._resume_cancel_event = registry._resume_cancel_event  # the app/main.py wiring
    recorded: dict = {}
    engine._execute_impl = _recording_impl(recorded)  # type: ignore[assignment]

    await _drive(engine, run_id)

    assert recorded.get("cancel_event") is registry._CANCEL_EVENTS[run_id], (
        "the engine must read the SAME Event object POST /cancel sets — one registry, "
        "one object"
    )


# ===========================================================================
# 2. End-to-end — a resumed drive stops, and stops TERMINALLY
# ===========================================================================


async def _interrupted_run(session, db_engine, call_log):
    """Instance A: drive ``sample_wave`` until the wave-1 fan-out crashes, leaving a
    resumable, non-terminal run with durable step state (the production shape a restart
    hands to the resume tier)."""
    run_id = f"iss084-{uuid.uuid4().hex[:8]}"
    owner = "iss084-user"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    with _ResumeHarness(
        session, call_log, fail_on=set(), db_engine=db_engine, raise_on_fanout_call=2
    ) as h:
        engine_a = h.make_engine()
        try:
            async for _ev in engine_a._execute_impl(
                agents=list(h.specs), user_message="Run the wave workflow.",
                pipeline_run_id=run_id, pipeline_type=_FIXTURE_ID, user_id=owner,
                gate_agent_ids=[],
            ):
                pass
        except Exception:  # noqa: BLE001 — the scripted mid-wave crash
            pass
    return run_id, owner


def _persisted_types(session, run_id: str) -> list[str]:
    from app.models.run_event import RunEvent

    return [
        r.type
        for r in session.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.seq)
        .all()
    ]


@pytest.mark.asyncio
async def test_cancel_stops_a_resumed_drive_and_writes_the_terminal_row(registry):
    """THE HEADLINE. A run interrupted mid-build is auto-resumed; the owner has pressed
    Stop, so ``_CANCEL_EVENTS[run_id]`` is set. The resumed drive must observe it at its
    first step boundary — dispatching NOTHING, emitting ``pipeline_cancelled``, and
    leaving the ``workflow_runs`` row TERMINAL.

    RED pre-fix on all three counts: the drive re-enters the incomplete wave and runs the
    remaining workers, no ``pipeline_cancelled`` is ever emitted, and the row never
    becomes ``cancelled``.
    """
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    call_log: dict[str, int] = {}
    run_id, _owner = await _interrupted_run(session, db_engine, call_log)
    calls_before = dict(call_log)

    # The owner presses Stop. This is the REAL registry the REST endpoint writes to.
    registry._register_resume_task(run_id, object())
    registry._CANCEL_EVENTS[run_id].set()

    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()
        engine_b._resume_cancel_event = registry._resume_cancel_event
        await engine_b.resume_run(run_id)

    assert call_log == calls_before, (
        f"a cancelled resume kept dispatching agents: {calls_before} -> {call_log}"
    )
    assert "pipeline_cancelled" in _persisted_types(session, run_id), (
        "a cancelled run must persist exactly the pipeline_cancelled terminal — "
        "without it nothing downstream (UI, status, cost accounting) is ever told"
    )

    session.expire_all()
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row.status == "cancelled", (
        f"the run row must reach a TERMINAL cancelled status, not {row.status!r} — "
        "a non-terminal row is re-adopted by the next boot's auto-resume"
    )
    session.close()


@pytest.mark.asyncio
async def test_a_cancelled_resumed_run_is_not_re_adopted_by_auto_resume(registry):
    """THE REGRESSION GUARD. Killing the backend to stop a run does not work: the next
    startup's ``restore_non_terminal_runs`` re-adopts every non-terminal row and drives
    it to completion (measured — the replacement backend emitted ``pipeline_start`` two
    seconds after boot and billed 7.5M further tokens). So a cancel is only real if it
    leaves the row OUTSIDE the non-terminal set.

    RED pre-fix: the cancel is ignored, the resumed drive dies on the scripted wave crash
    with the row still ``generating``, and the restore scan picks the run straight back up.
    """
    session, db_engine = _make_session()
    call_log: dict[str, int] = {}
    run_id, _owner = await _interrupted_run(session, db_engine, call_log)

    registry._register_resume_task(run_id, object())
    registry._CANCEL_EVENTS[run_id].set()

    # The resumed drive would crash on the wave-1 fan-out (as instance A did) if the
    # cancel were ignored — leaving the row non-terminal, which is the re-adoption setup.
    with _ResumeHarness(
        session, call_log, fail_on=set(), db_engine=db_engine, raise_on_fanout_call=1
    ) as h:
        engine_b = h.make_engine()
        engine_b._resume_cancel_event = registry._resume_cancel_event
        await engine_b.resume_run(run_id)

    # A fresh boot scans for non-terminal runs.
    adopted: list[str] = []

    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_c = h.make_engine()

        async def _spy_stamp(wr):
            adopted.append(f"stamp:{wr.id}")

        async def _spy_resume(rid):
            adopted.append(f"resume_run:{rid}")

        async def _spy_rearm(rid):
            adopted.append(f"rearm:{rid}")

        engine_c._stamp_resume_marker = _spy_stamp  # type: ignore[assignment]
        engine_c.resume_run = _spy_resume  # type: ignore[assignment]
        engine_c._rearm_gate_run = _spy_rearm  # type: ignore[assignment]

        await engine_c.restore_non_terminal_runs()
        await asyncio.sleep(0.05)  # let any spawned driver task actually run

    assert adopted == [], (
        f"the next boot re-adopted a run the owner paid to stop: {adopted}"
    )
    session.close()

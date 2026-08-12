"""Graceful application-shutdown orchestration for the run transport (KAN-151 D8).

The FastAPI lifespan's shutdown half was a bare log line: nothing cancelled the
in-flight pipeline drivers, nothing awaited the Concierge turns that own their own
durable ``chat_reply`` write, and nothing closed the LangGraph checkpointer's
Postgres pool - despite ``checkpointer.py:12`` saying to. This module is that body.

Reachability prerequisite (KAN-151 D8, measured): uvicorn's ``timeout_graceful_shutdown``
defaults to ``None`` and ``H11Protocol.shutdown()`` does NOT close a connection whose
response is still streaming - it only clears keep_alive. A live SSE stream therefore never
leaves ``server_state.connections``, ``_wait_tasks_to_complete()`` spins forever, and
``lifespan.shutdown()`` is NEVER reached; docker SIGKILLs at ``stop_grace_period`` (30s).
``docker-entrypoint.sh`` passes ``--timeout-graceful-shutdown 5`` so this code runs.

Ordering is load-bearing and is NOT the simple "signal then cancel":
  1. Concierge drive tasks are AWAITED first (never cancelled first) - a cancel
     landing inside ``converse()`` skips the durable ``chat_reply`` persist
     entirely, losing the user's answer with no record.
  2. Run-transport teardown (A2 pumps / queue sentinels) - releases attached
     consumers before their producers vanish.
  3. ``close_checkpointer()`` LAST among the awaits - it tears down a pool that
     step 1/2 tasks may still hold a connection from.
  4. Counts are logged so D9's thundering herd is measurable (D11 pairs the same
     JSON shape on the stream side).

By default this does NOT stop the pipeline drivers and does NOT write any
``WorkflowRun.status``. That is deliberate: every stop path makes the engine yield
``pipeline_cancelled``, which ``engine.py:1032`` persists unconditionally and which
makes the driver write ``status="cancelled"`` - and ``cancelled`` is outside
``restore_non_terminal_runs``' ``NON_TERMINAL`` set (``engine.py:5263``), so the run
would never auto-resume on the next boot. Leaving the row ``running`` is what keeps
the Phase 45-50 resume tier working. See ``stop_pipeline_drivers`` below and the
KAN-151 D8 investigation section I11 for the alternative.

Workflow-agnostic - keyed by run id only, no workflow/agent-name literal (SC-001).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger("app.api.run_shutdown")


async def _drain(tasks: set[asyncio.Task], timeout: float) -> tuple[int, int]:
    """Await ``tasks`` up to ``timeout``. Returns ``(finished, still_pending)``."""
    if not tasks:
        return 0, 0
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    return len(done), len(pending)


async def shutdown_run_infrastructure() -> dict[str, Any]:
    """Quiesce the run transport. Returns a JSON-safe summary for the caller to log.

    Never raises - a shutdown path that throws would abort the rest of the teardown
    and (via uvicorn's ``lifespan.shutdown_failed``) turn a clean exit into an error
    exit. Every step is individually guarded.
    """
    t0 = time.monotonic()
    # Deferred imports: this module is a leaf, but keeping them here also means an
    # import failure in one registry's module cannot break the whole shutdown.
    from app.api.run_commands import _CONCIERGE_STREAM_TASKS, _LIVE_ECTX
    from app.api.run_engine import (
        _CANCEL_EVENTS,
        _PIPELINE_QUEUES,
        _PIPELINE_TASKS,
        _PUMP_TASKS,
    )

    summary: dict[str, Any] = {
        "event": "app_shutdown",
        "runs_in_flight": len(_PIPELINE_TASKS),
        "run_ids_in_flight": sorted(_PIPELINE_TASKS.keys()),
        "live_queues": len(_PIPELINE_QUEUES),
        "cancel_events": len(_CANCEL_EVENTS),
        "live_ectx": len(_LIVE_ECTX),
        "concierge_turns_in_flight": len(_CONCIERGE_STREAM_TASKS),
        "concierge_persisted": 0,
        "concierge_lost": 0,
        "pipeline_drivers_stopped": 0,
        "queues_sentinelled": 0,
        "pump_tasks_in_flight": len(_PUMP_TASKS),
        "pump_tasks_drained": 0,
        "pump_tasks_cancelled": 0,
        "checkpointer_closed": False,
        "errors": [],
    }

    # ── 1. Concierge turns: AWAIT, never cancel-first. ──────────────────────────
    # run_commands.py:1401 holds these deliberately ("NEVER cancel it on generator
    # teardown"); the durable chat_reply row is written at :1356 inside _drive's
    # SECOND try, so a CancelledError raised inside converse() at :1347 skips it.
    try:
        _concierge_tasks = set(_CONCIERGE_STREAM_TASKS)
        done, pending_tasks = await asyncio.wait(
            _concierge_tasks, timeout=settings.SHUTDOWN_CONCIERGE_DRAIN_SECONDS
        ) if _concierge_tasks else (set(), set())
        summary["concierge_persisted"] = len(done)
        summary["concierge_lost"] = len(pending_tasks)
        if pending_tasks:
            logger.warning(
                "shutdown: %d Concierge turn(s) exceeded the %.1fs drain budget - "
                "their chat_reply rows will NOT be written (the user's question row "
                "persists with no answer).",
                len(pending_tasks),
                settings.SHUTDOWN_CONCIERGE_DRAIN_SECONDS,
            )
            # M-14: ``asyncio.wait(timeout=...)`` returns WITHOUT cancelling
            # ``pending`` -- step 4 below closes the checkpointer pool
            # unconditionally afterwards, which directly contradicts this
            # module's own "close last because earlier steps may hold
            # connections" invariant (see the module docstring) for exactly
            # these stragglers. Explicitly cancel them and give them a short
            # window to unwind (release their pooled connection) before the
            # pool closes underneath them.
            for t in pending_tasks:
                t.cancel()
            await asyncio.wait(pending_tasks, timeout=settings.SHUTDOWN_TASK_DRAIN_SECONDS)
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"concierge_drain: {exc}")
        logger.warning("shutdown: concierge drain failed: %s", exc)

    # ── 2. Run-transport teardown. ──────────────────────────────────────────────
    # Release every attached consumer before its producer disappears: a per-run
    # None sentinel on the shared producer queue, which each run's pump (if one
    # was ever started) forwards to its own subscribers. H-11: step 2b below
    # additionally awaits/cancels the pump tasks themselves — sentinelling the
    # producer queue only makes a pump exit EVENTUALLY; nothing waited for that
    # before, so a slow pump could still be running when the checkpointer pool
    # closes underneath it (step 4).
    try:
        for run_id in list(_PIPELINE_QUEUES.keys()):
            try:
                _PIPELINE_QUEUES[run_id].put_nowait(None)
                summary["queues_sentinelled"] += 1
            except Exception:  # noqa: BLE001 - a full/absent queue must not abort
                pass
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"queue_sentinel: {exc}")

    # ── 2b. H-11: pump tasks are NOT covered by the queue-sentinel step above. ──
    # Sentinelling a producer queue makes its pump exit ON ITS OWN once it drains
    # to that sentinel (``_pump_run_events``'s own ``finally`` pops its registry
    # entry) — but nothing here AWAITS that exit, so a slow pump (a subscriber's
    # queue momentarily full, or simply a long backlog still ahead of the
    # sentinel) is still running when the lifespan proceeds to close the
    # checkpointer pool underneath it. Drain with the same budget as the run
    # drivers, then cancel any stragglers — mirrors the run-driver drain/escalate
    # shape in ``stop_pipeline_drivers`` without depending on ``SHUTDOWN_STOP_RUNS``
    # (a pump is a transport-side reader, not a run-status decision, so its
    # teardown is unconditional regardless of that switch).
    try:
        pump_tasks = {task for task, _generation in _PUMP_TASKS.values()}
        if pump_tasks:
            done_tasks, pending_tasks = await asyncio.wait(
                pump_tasks, timeout=settings.SHUTDOWN_TASK_DRAIN_SECONDS
            )
            summary["pump_tasks_drained"] = len(done_tasks)
            if pending_tasks:
                logger.warning(
                    "shutdown: cancelling %d SSE pump task(s) that did not exit "
                    "within %.1fs of their sentinel.",
                    len(pending_tasks),
                    settings.SHUTDOWN_TASK_DRAIN_SECONDS,
                )
                for t in pending_tasks:
                    t.cancel()
                await asyncio.wait(
                    pending_tasks, timeout=settings.SHUTDOWN_TASK_DRAIN_SECONDS
                )
                summary["pump_tasks_cancelled"] = len(pending_tasks)
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"pump_drain: {exc}")
        logger.warning("shutdown: pump task drain failed: %s", exc)

    # ── 3. Optional: stop the pipeline drivers (see stop_pipeline_drivers). ─────
    if settings.SHUTDOWN_STOP_RUNS:
        try:
            summary["pipeline_drivers_stopped"] = await stop_pipeline_drivers()
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"stop_runs: {exc}")

    # ── 4. Close the checkpointer pool LAST among the awaits (D7). ──────────────
    # checkpointer.py:12 has said to do this since Phase 3; it has never had a
    # caller. Steps 1-3 may still hold a pooled connection, so this runs after them.
    try:
        from app.agents.checkpointer import close_checkpointer

        await close_checkpointer()
        summary["checkpointer_closed"] = True
    except Exception as exc:  # noqa: BLE001
        # M-16: the pool's DSN is derived from DATABASE_URL (contains the DB
        # password), and psycopg errors can embed the DSN in their message.
        # These logs ship to CloudWatch (H-06) -- log only the exception TYPE
        # in the summary/warning; the full traceback (still potentially
        # DSN-bearing) goes to logger.exception at DEBUG-adjacent detail only
        # an operator actively investigating would enable, not the routine
        # shutdown path.
        summary["errors"].append(f"close_checkpointer: {type(exc).__name__}")
        logger.warning("shutdown: close_checkpointer failed: %s", type(exc).__name__)
        logger.debug("shutdown: close_checkpointer failure detail", exc_info=True)

    summary["elapsed_seconds"] = round(time.monotonic() - t0, 3)
    # D9 measurability: runs left non-terminal here are exactly the set the next
    # boot's restore_non_terminal_runs will classify (branch b auto-resume /
    # branch c fail). This is the number the D9 semaphore must be sized against.
    summary["runs_left_for_boot_restore"] = (
        0 if settings.SHUTDOWN_STOP_RUNS else summary["runs_in_flight"]
    )
    return summary


async def _drain_then_cancel(tasks: set[asyncio.Task], *, context: str) -> None:
    """The ONE bounded escalation (INV-12): wait out the drain budget, then
    ``task.cancel()`` whatever did not observe the cooperative signal in time.

    Shared by the shutdown sweep (``stop_pipeline_drivers``) and the per-run Stop
    (``stop_run_driver``) so there is exactly one escalation policy in the codebase and
    the interactive path cannot drift from the tested one. The escalation is a FALLBACK,
    never the mechanism: the caller must already have set the cooperative ``cancel_event``
    so the driver takes its clean ``pipeline_cancelled`` terminal at the next boundary.
    It exists only for the mid-model-call blind window (``model_factory`` sets
    ``read_timeout=600``, so a per-chunk check can be up to ten minutes away).
    """
    if not tasks:
        return
    _done, pending = await asyncio.wait(
        tasks, timeout=settings.SHUTDOWN_TASK_DRAIN_SECONDS
    )
    if not pending:
        return
    logger.warning(
        "%s: escalating task.cancel() for %d driver(s) that did not observe "
        "the cooperative cancel within %.1fs (mid-model-call).",
        context,
        len(pending),
        settings.SHUTDOWN_TASK_DRAIN_SECONDS,
    )
    for t in pending:
        t.cancel()
    _done2, still = await asyncio.wait(
        pending, timeout=settings.SHUTDOWN_TASK_DRAIN_SECONDS
    )
    if still:
        logger.error(
            "%s: %d driver(s) survived cancel; their runs stay non-terminal "
            "and will be classified by restore_non_terminal_runs on the next boot.",
            context,
            len(still),
        )


async def stop_pipeline_drivers() -> int:
    """Cooperatively stop, then cancel, every live pipeline driver. Returns the count.

    NOT called by default (``SHUTDOWN_STOP_RUNS`` is False). Enabling it converts
    every in-flight run to ``WorkflowRun.status = "cancelled"`` and removes it from
    the boot-time auto-resume set. See KAN-151 D8 investigation section I11 - this
    is a product decision, not a technical one.

    Reuses the ONE sanctioned stop mechanism (Phase 16-02 / quick-260720-ec4): set
    the per-run cooperative ``cancel_event``, which the engine observes at the
    per-chunk (:2514/:3621), pre-agent (:2287), clarify-drain-heartbeat (:1943),
    review-gate-race (:5155), task-loop (:4437/:4566) and wave (:5012) boundaries.
    Escalate to ``task.cancel()`` only for drivers that cannot observe it in time
    (the mid-Bedrock-call case: the per-chunk check only fires when a chunk arrives,
    and ``model_factory.py:112`` sets ``read_timeout=600``). Both paths end in the
    driver's own terminal write (``run_commands.py:2155`` launch /
    ``:2473`` revision), so the outcome is deterministic either way.
    """
    from app.api.run_engine import _CANCEL_EVENTS, _PIPELINE_TASKS

    tasks = set(_PIPELINE_TASKS.values())
    if not tasks:
        return 0
    for ev in list(_CANCEL_EVENTS.values()):
        ev.set()
    await _drain_then_cancel(tasks, context="shutdown")
    return len(tasks)


async def stop_run_driver(run_id: str) -> None:
    """Bounded escalation for ONE run's driver — the ``POST /cancel`` fallback (ISS-084).

    The endpoint has already set the run's cooperative ``cancel_event``; this backstops
    the case where the driver cannot observe it in bounded time. Same policy as the
    shutdown sweep, deliberately: before KAN-88 the WS Stop handler HAD a destructive
    fallback, KAN-88 deleted it on the false premise that resumed runs read the
    cooperative event, and Phase 44's REST port kept only the cooperative branch — which
    left no path at all, cooperative or destructive, by which a user could stop a resumed
    run. Never raises: it runs detached from the HTTP response.

    It then RECONCILES the terminal row. That is the half that makes a Stop real: the
    launch driver writes ``status="cancelled"`` from its own ``CancelledError`` handler,
    but the resume tier writes no status of its own, and ``_drive_resumed_stream`` catches
    only ``Exception`` — so a destructive cancel landing on one of its persist awaits would
    leave the row NON-TERMINAL, and ``restore_non_terminal_runs`` re-adopts every
    non-terminal row on the next boot and drives it to completion. A cancel that leaves the
    row non-terminal is not a cancel, it is a delayed re-run. ``_reconcile_terminal_status``
    is the app layer's existing durable-tail→status decision (INV-12, the user-resume path
    already uses it): ``pipeline_cancelled`` → ``cancelled``, no clean terminal →
    ``failed`` — either way TERMINAL, so no boot re-adopts it.
    """
    from app.api.run_engine import _PIPELINE_TASKS

    task = _PIPELINE_TASKS.get(run_id)
    # A non-Task sentinel (the ``_is_run_live`` un-introspectable case) has nothing to
    # escalate against; the cooperative signal is the whole stop mechanism there.
    if not isinstance(task, asyncio.Task) or task.done():
        return
    try:
        await _drain_then_cancel({task}, context=f"cancel(run={run_id})")
    except Exception as exc:  # noqa: BLE001 — a detached backstop must never surface
        logger.warning("cancel(run=%s): escalation failed: %s", run_id, exc)
        return
    # Only once the driver is provably gone — never stamp a terminal on a live run.
    if not task.done():
        return
    try:
        from app.api.run_commands import _reconcile_terminal_status

        await _reconcile_terminal_status(run_id)
    except Exception as exc:  # noqa: BLE001 — best-effort, mirrors _drive_user_resume
        logger.warning("cancel(run=%s): terminal reconcile failed: %s", run_id, exc)

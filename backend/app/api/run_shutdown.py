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
    from app.api.run_engine import _CANCEL_EVENTS, _PIPELINE_QUEUES, _PIPELINE_TASKS

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
        "checkpointer_closed": False,
        "errors": [],
    }

    # ── 1. Concierge turns: AWAIT, never cancel-first. ──────────────────────────
    # run_commands.py:1401 holds these deliberately ("NEVER cancel it on generator
    # teardown"); the durable chat_reply row is written at :1356 inside _drive's
    # SECOND try, so a CancelledError raised inside converse() at :1347 skips it.
    try:
        done, pending = await _drain(
            set(_CONCIERGE_STREAM_TASKS), settings.SHUTDOWN_CONCIERGE_DRAIN_SECONDS
        )
        summary["concierge_persisted"] = done
        summary["concierge_lost"] = pending
        if pending:
            logger.warning(
                "shutdown: %d Concierge turn(s) exceeded the %.1fs drain budget - "
                "their chat_reply rows will NOT be written (the user's question row "
                "persists with no answer).",
                pending,
                settings.SHUTDOWN_CONCIERGE_DRAIN_SECONDS,
            )
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"concierge_drain: {exc}")
        logger.warning("shutdown: concierge drain failed: %s", exc)

    # ── 2. Run-transport teardown. ──────────────────────────────────────────────
    # Release every attached consumer before its producer disappears. Today that is
    # a per-run None sentinel on the shared queue; AFTER A2 lands, _close_run is the
    # single idempotent teardown (pops the liveness key, cancels the pump, sentinels
    # every subscriber) and the branch below MUST switch to it.
    try:
        for run_id in list(_PIPELINE_QUEUES.keys()):
            try:
                _PIPELINE_QUEUES[run_id].put_nowait(None)
                summary["queues_sentinelled"] += 1
            except Exception:  # noqa: BLE001 - a full/absent queue must not abort
                pass
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"queue_sentinel: {exc}")

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
        summary["errors"].append(f"close_checkpointer: {exc}")
        logger.warning("shutdown: close_checkpointer failed: %s", exc)

    summary["elapsed_seconds"] = round(time.monotonic() - t0, 3)
    # D9 measurability: runs left non-terminal here are exactly the set the next
    # boot's restore_non_terminal_runs will classify (branch b auto-resume /
    # branch c fail). This is the number the D9 semaphore must be sized against.
    summary["runs_left_for_boot_restore"] = (
        0 if settings.SHUTDOWN_STOP_RUNS else summary["runs_in_flight"]
    )
    return summary


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
    _done, pending = await asyncio.wait(tasks, timeout=settings.SHUTDOWN_TASK_DRAIN_SECONDS)
    if pending:
        logger.warning(
            "shutdown: escalating task.cancel() for %d driver(s) that did not observe "
            "the cooperative cancel within %.1fs (mid-model-call).",
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
                "shutdown: %d driver(s) survived cancel; their runs stay non-terminal "
                "and will be classified by restore_non_terminal_runs on the next boot.",
                len(still),
            )
    return len(tasks)

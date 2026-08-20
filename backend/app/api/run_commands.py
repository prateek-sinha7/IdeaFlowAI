"""app/api/run_commands.py — CHAT-07 / D-13: up-channel REST command endpoints.

Transport-agnostic HTTP counterparts to the three paused-run ``/ws/chat``
inbound handlers, so commands work over plain HTTP (and while the SSE stream is
down). Each endpoint is a **thin wrapper over the SAME seams** the WS handlers
call — it adds NO new behavior, NO new event shape, and NO new persistence:

  * ``POST /api/runs/{id}/gate``   → ``store.set_review_response(...)`` — the exact
    seam WS ``approve_review`` uses (store.py:118). Preserves the FOUR-action
    contract (approve / reject / redo+instructions / update_specs), the KAN-100
    terminal fence (``pipeline_not_running``, recoverable:false), the KAN-94
    event-driven gate semantics (no armed gate → clean not-found, never a
    fabricated pause), and the P13 owner gate (IDOR → 404, never 403).
  * ``POST /api/runs/{id}/answers`` → ``store.set_questionnaire_responses(...)`` —
    the exact seam WS ``submit_questionnaire`` uses (store.py:62), incl. the
    ISS-027 ``skip_clarification`` force-proceed.
  * ``POST /api/runs/{id}/cancel``  → sets the per-run cooperative cancel event
    ``_CANCEL_EVENTS[run_id]`` — the exact seam WS ``cancel_pipeline`` uses
    (websocket.py:924-949, ISS-007).

LOCK-B: this module is ADDITIVE. ``/ws/chat`` (``websocket.py``) is untouched;
the ownership + terminal predicates and the cooperative cancel registry are
reached by **read-only import** of the existing symbols — no symbol is added to
``websocket.py`` and the store seams are reused verbatim (no re-implementation of
the KAN-100 cancel-while-paused race or the KAN-101 spec-revision sub-pipeline —
this layer only ROUTES to them).

Owner scoping (T-29-03-1/2/3): every command resolves ownership on
``WorkflowRun.user_id`` via the shared ``_review_gate_owned_by`` predicate BEFORE
any write; an unknown / cross-owner target denies with a non-revealing
``Unknown gate_key`` / 404, never a run-existence oracle (IDOR → 404).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid as _uuid
from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from agents.artifact_store.store import get_artifact_store
from agents.workflows.plan import CompiledWorkflow
from agents.capabilities.model_pricing import estimate_cost_usd
from app.agents.chat_runner import ChatRunner
from app.agents.modes import get_mode_prompt
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.entitlements import can_run_pipeline
from app.models.chat import ChatSession, Message
from app.models.user import User
from app.models.workflow import WorkflowRun

# READ-ONLY import of the EXISTING /ws/chat seams (LOCK-B — websocket.py is NOT
# modified and no symbol is added to it). These are the same predicates + the
# same cooperative-cancel registry the WS inbound handlers use, so the REST and
# WS command paths cannot diverge.
#
# 29-04 extends the read-only surface to the WS-agnostic background-execution
# machinery: the per-run queue registry (`_get_or_create_queue` / `_cleanup_pipeline`
# / `_PIPELINE_TASKS`), the ingress validators (`_validate_images`,
# `_validate_model_overrides`, `_revalidate_selections_trust_user`), the
# owner-checked parent-link resolver (`_resolve_owned_parent_run_id`), and the DB
# session factory (`_get_db`). The engine-drive loops themselves are DUPLICATED
# here (sanctioned LOCK-B duplication — the WS `run_pipeline`/`run_revision`
# handlers keep their own copies; the de-dup is the deferred supervised follow-up)
# because the WS copies are nested socket-coupled closures, not importable.
from app.api.run_engine import (
    _CANCEL_EVENTS,
    _PIPELINE_TASKS,
    _cleanup_pipeline,
    _get_db,
    _get_or_create_queue,
    _is_run_live,
    _resolve_owned_parent_run_id,
    _review_gate_advertises_update_specs,
    _review_gate_owned_by,
    _review_gate_run_is_terminal,
    _revalidate_selections_trust_user,
    _validate_images,
    _validate_model_overrides,
)

# API-001 (task.md R-05): the single canonical terminal-status set (engine.py —
# see its own docstring for why it now exists beside NON_TERMINAL_RUN_STATUSES).
from agents.execution_engine.engine import TERMINAL_RUN_STATUSES

logger = logging.getLogger("app.api.run_commands")

router = APIRouter(prefix="/api/runs", tags=["run-commands"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class GateCommand(BaseModel):
    """Body for ``POST /{id}/gate`` — the four gate actions (D-13 / POR §6).

    ``action`` is the generic discriminator (SC-001 / INV-1 — no workflow name):
      * ``approve`` (default) — resolve the gate; optional ``edited_content``.
      * ``reject``            — approved=False (pipeline cancelled downstream).
      * ``redo``              — in-place re-run with optional ``instructions``.
      * ``update_specs``      — KAN-101 spec-revision loop; carries
        ``analysis_report`` in the ``instructions`` field (routes to the shipped
        sub-pipeline; not rebuilt here).
    """

    gate_key: str
    # ISS-070: a CLOSED domain. The vocabulary's single authority is
    # ``chat_router.GATE_ACTIONS``; ``Literal`` needs static values, so the two are
    # pinned together by a set-equality test rather than a second constant (INV-12).
    # The default is RETAINED — an ABSENT action still means approve (the published
    # OpenAPI contract, and test_attach_replay_matrix.py:551's bare POST).
    action: Literal["approve", "reject", "redo", "update_specs"] = "approve"
    approved: bool | None = None
    edited_content: str | None = None
    instructions: str | None = None
    analysis_report: str | None = None


class AnswersCommand(BaseModel):
    """Body for ``POST /{id}/answers`` — clarify responses (D-13).

    ``responses`` mirrors the WS ``submit_questionnaire`` shape verbatim
    (``[{question_id, answer}]``); the global "anything else" note maps to
    ``question_id: "freeform"`` (the frontend already emits it that way — see
    DashboardLayout.tsx). ``skip_clarification`` is the ISS-027 force-proceed.
    """

    responses: list[dict] = []
    skip_clarification: bool = False
    freeform: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gate_is_pending(store, gate_key: str) -> bool:
    """True iff a review gate for ``gate_key`` is armed and awaiting a response.

    KAN-94 — gates are EVENT-DRIVEN: ``_run_review_gate`` arms the review event
    (``get_review_event`` → ``clear`` → ``await wait``) only for an agent that is
    actually gated this run; an agent EXCLUDED by ``gate_agent_ids`` never arms
    one. So an armed-but-unset review event is the ground truth that a pause is
    genuinely pending. Reading the store's existing per-process registry (no
    store mutation) lets the REST endpoint return a clean not-found instead of
    fabricating a pause / resolving a gate no one is waiting on.

    IN-02: reads the store's PUBLIC ``review_event_pending`` accessor — the
    ``store._resume_events`` private-dict peek no longer appears in the app layer.
    """
    return store.review_event_pending(gate_key)


def _deny_unknown_gate() -> HTTPException:
    """Non-revealing IDOR denial (T-29-03-1): an unknown run and an unowned run
    are indistinguishable to the caller — both 404 "Unknown gate_key"."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Unknown gate_key"
    )


def _deny_update_specs_not_offered(gate_key: str) -> HTTPException:
    """ISS-053: this gate firing did not offer the spec-revision affordance.

    The verdict is the engine's own, read back off the ``review_gate_ready`` it published
    (``_review_gate_advertises_update_specs``) — this restates no rule. Raised by ALL
    THREE ``set_review_response`` ingresses so no channel is privileged; a fence on
    ``POST /gate`` alone would leave both ``/messages`` routes open.

    409 rather than 403: the request is well-formed and authorised, it just conflicts with
    the run's current state — the same shape as the KAN-100 terminal fence beside it.
    ``recoverable: false`` because retrying the identical POST cannot succeed; the user
    must approve to the gate where a revision cycle IS offered.
    """
    logger.warning(
        "gate update_specs REFUSED at ingress: gate_key=%s — the gate published "
        "update_specs_eligible=False",
        gate_key,
    )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "This review gate does not offer a spec-revision cycle",
            "code": "update_specs_not_offered",
            "recoverable": False,
        },
    )


def _deny_unknown_gate_action(action: object) -> HTTPException:
    """ISS-070: an unrecognised discriminator must never resolve a HITL gate.

    The degrade is to REFUSE and leave the gate ARMED — never approve (the fail-open
    this replaces), and never reject either: FIX-232 makes a rejection terminal, so
    degrading an unparseable action into a denial would destroy the run on a typo.
    Refusing the request is the only degrade that preserves every legitimate option —
    the same choice the engine already makes for an ineligible ``update_specs``.

    400 rather than 409: the request is malformed, not in conflict with the run's state,
    so re-issuing it correctly WILL succeed — hence ``recoverable: true``.

    Raised by ALL THREE ``set_review_response`` ingresses so no channel is privileged.
    The log line is the forensic trace: the refused action is never persisted, and the
    store's own ``action="approve"`` default would otherwise launder it into a clean-
    looking approval record.
    """
    logger.warning("gate action REFUSED at ingress: unrecognised action=%r", action)
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": "Unknown gate action",
            "code": "unknown_gate_action",
            "recoverable": True,
        },
    )


# ---------------------------------------------------------------------------
# POST /api/runs/{run_id}/gate — approve / reject / redo / update_specs
# ---------------------------------------------------------------------------


@router.post("/{run_id}/gate")
async def resolve_gate(
    run_id: str,
    body: GateCommand,
    current_user: User = Depends(get_current_user),
):
    """Resolve a paused HITL review gate over HTTP (mirrors WS ``approve_review``).

    Order of checks is identical to the WS handler: missing gate_key → 400;
    owner gate (P13) → 404; terminal fence (KAN-100) → pipeline_not_running;
    then the store write. An extra event-driven not-found (KAN-94) precedes the
    write so the REST channel never resolves a gate that was never armed.
    """
    gate_key = body.gate_key
    if not gate_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "gate requires gate_key",
                "code": "missing_gate_key",
                "recoverable": True,
            },
        )

    # P13 / T-29-03-1: only the run's owner may resolve its gate. Deny without
    # revealing whether the run exists. (The owner check runs BEFORE any write —
    # every action, incl. redo/update_specs, rides this same IDOR boundary.)
    if not _review_gate_owned_by(gate_key, current_user.id):
        raise _deny_unknown_gate()

    # KAN-100 / T-29-03-2: reject any gate action on a terminal (cancelled /
    # failed / degraded) run so a Redo cannot resume a stopped pipeline. Keyed on
    # the persisted DB status — accurate across reconnects.
    if _review_gate_run_is_terminal(gate_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Pipeline is no longer running",
                "code": "pipeline_not_running",
                "recoverable": False,
            },
        )

    store = get_artifact_store()

    # KAN-94: gates are event-driven. An agent excluded by gate_agent_ids has no
    # armed gate → clean not-found (never a fabricated pause).
    if not _gate_is_pending(store, gate_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "No pending gate for gate_key",
                "code": "gate_not_pending",
                "recoverable": False,
            },
        )

    action = body.action or "approve"
    if action == "redo":
        await store.set_review_response(
            gate_key, approved=False, action="redo", instructions=body.instructions
        )
    elif action == "update_specs":
        # KAN-101: route to the shipped spec-revision sub-pipeline. The analysis
        # report is carried in the generic ``instructions`` field (SC-001 / INV-1).
        # ISS-053: only at a gate that ADVERTISED the affordance — the engine's own
        # published verdict, read back rather than recomputed.
        if not _review_gate_advertises_update_specs(gate_key):
            raise _deny_update_specs_not_offered(gate_key)
        analysis_report = body.analysis_report or ""
        await store.set_review_response(
            gate_key, approved=False, action="update_specs", instructions=analysis_report
        )
    elif action == "reject":
        await store.set_review_response(
            gate_key, approved=False, edited_content=body.edited_content
        )
    elif action == "approve":
        approved = True if body.approved is None else bool(body.approved)
        await store.set_review_response(
            gate_key,
            approved=approved,
            action="approve",
            edited_content=body.edited_content,
        )
    else:
        # ISS-070: fail CLOSED. Unreachable over HTTP now that the schema closes the
        # domain — kept because an in-process caller (or a fifth Literal member added
        # without a branch here) would otherwise reopen the silent approval.
        raise _deny_unknown_gate_action(action)

    return {"ok": True, "action": action, "gate_key": gate_key}


# ---------------------------------------------------------------------------
# POST /api/runs/{run_id}/answers — clarify responses
# ---------------------------------------------------------------------------


@router.post("/{run_id}/answers")
async def submit_answers(
    run_id: str,
    body: AnswersCommand,
    current_user: User = Depends(get_current_user),
):
    """Submit clarify answers over HTTP (mirrors WS ``submit_questionnaire``).

    Owner-gated (T-29-03-3) → 404 on cross-owner. Passes the responses verbatim
    to the SAME store seam the WS handler calls; the ISS-027 force-proceed flows
    through ``skip_clarification``.
    """
    if not _review_gate_owned_by(run_id, current_user.id):
        raise _deny_unknown_gate()

    # API-001 (task.md R-05): this endpoint had ZERO terminal-status fencing —
    # unlike /gate (KAN-100's ``_review_gate_run_is_terminal`` check) and /cancel
    # (its own idempotent-terminal branch), a clarify-answers POST against an
    # already-terminal (cancelled/failed/degraded/completed) run was accepted
    # unconditionally and written straight to the store. Mirror /gate's fence —
    # ``_review_gate_run_is_terminal`` takes a ``{run_id}:{agent_id}``-shaped
    # ``gate_key``, and a bare ``run_id`` parses identically (split on the first
    # ``:``, which is absent here → the whole string is the run_id — see its
    # docstring), so passing ``run_id`` directly is correct, not a workaround.
    if _review_gate_run_is_terminal(run_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Pipeline is no longer running",
                "code": "pipeline_not_running",
                "recoverable": False,
            },
        )

    responses = list(body.responses or [])
    # The global freeform "anything else" note rides as question_id="freeform"
    # (the frontend maps it this way; support the convenience field over HTTP).
    if body.freeform:
        responses.append({"question_id": "freeform", "answer": body.freeform})

    store = get_artifact_store()
    await store.set_questionnaire_responses(
        run_id, responses, skip_clarification=bool(body.skip_clarification)
    )
    return {"ok": True, "run_id": run_id, "count": len(responses)}


# ---------------------------------------------------------------------------
# POST /api/runs/{run_id}/cancel — cooperative cancel
# ---------------------------------------------------------------------------

# Strong references to the detached escalation backstops, so a task started for a Stop is
# not garbage-collected mid-flight (the asyncio contract). Mirrors _CONCIERGE_STREAM_TASKS.
_CANCEL_ESCALATIONS: set = set()


def _arm_cancel_escalation(run_id: str) -> None:
    """Start the bounded fallback for a Stop, detached from the HTTP response.

    The cooperative event is the mechanism; this only backstops the mid-model-call blind
    window. Best-effort by construction: no running loop (a sync test client outside the
    portal) simply means no escalation, never a failed Stop.
    """
    from app.api.run_shutdown import stop_run_driver

    try:
        task = asyncio.get_running_loop().create_task(stop_run_driver(run_id))
    except Exception as exc:  # noqa: BLE001 — the ack must never depend on the backstop
        logger.warning("cancel(run=%s): could not arm the escalation: %s", run_id, exc)
        return
    _CANCEL_ESCALATIONS.add(task)
    task.add_done_callback(_CANCEL_ESCALATIONS.discard)


async def _record_cancellation_in_the_durable_tail(
    run_id: str, *, reason: str = "owner_stopped_run_with_no_live_driver"
) -> None:
    """Append the ``pipeline_cancelled`` row a driver would have emitted (ISS-089).

    Best-effort: audit + SSE replay + ``_reconcile_terminal_status`` agreement, none of
    which the money guarantee depends on. It rides ``append_event_at_or_after`` — the
    COLLISION-SAFE append — because the chat lane allocates from the same per-run seq
    space and FIX-240 (ISS-121) proved a ``uq_run_events_scope_seq`` rejection here is
    swallowed by the persist degrade rather than retried.

    Principal resolution is ``_reconcile_terminal_status``'s, verbatim: never the nullable
    ``owner_id`` alone, and the run's RECOVERED workspace (the value the sink actually
    wrote under) rather than the WS-path row's frequently-NULL ``workspace_id``.

    ``reason`` is parameterised for ISS-124 — the two app-layer DRIVER terminals
    (``_drive_launch_to_queue`` / ``_drive_revision_to_queue``) reach this same append
    from their ``except asyncio.CancelledError`` branches, where a driver WAS live and
    was destructively cancelled. The default is FIX-243's original string, unchanged, so
    the no-live-driver payload stays byte-identical. Extended, not copied (INV-12): one
    durable-terminal writer, three callers.
    """
    from agents.authz import ScopedStore
    from agents.execution_engine.engine import get_execution_engine

    db = _get_db()
    try:
        wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if wr is None:
            return
        owner_id = wr.owner_id or wr.user_id or f"anon:{wr.session_id or run_id}"
    finally:
        db.close()

    try:
        workspace_id = await get_execution_engine()._recover_workspace_id(owner_id, run_id)
        store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
        await store.append_event_at_or_after(
            run_id,
            (await store._max_event_seq(run_id)) + 1,
            str(_uuid.uuid4()),
            "pipeline_cancelled",
            {"pipeline_run_id": run_id, "reason": reason},
        )
    except Exception as exc:  # noqa: BLE001 — the audit row must never fail the Stop
        logger.warning(
            "cancel(run=%s): durable pipeline_cancelled append failed: %s", run_id, exc
        )


async def _cancel_run_without_a_live_driver(run_id: str) -> dict:
    """Make the owner's Stop DURABLE when no in-process driver can carry it (ISS-089).

    The cooperative ``asyncio.Event`` and the escalation task both die with the process,
    so before this a Stop that arrived with no live driver wrote NOTHING — and the run
    stayed inside ``NON_TERMINAL_RUN_STATUSES``, so the next boot re-adopted it and drove
    it to completion at the owner's expense (the ``d5dbc9f2`` incident: 45% of a
    16,530,718-token run billed AFTER the API answered ``cancelled: true``).

    Writing the terminal status HERE needs no migration, no new event type and no change
    to ``restore_non_terminal_runs``: ``cancelled`` is already outside
    ``NON_TERMINAL_RUN_STATUSES``, so the boot scan consults this decision through the
    filter it already has, and ``POST /resume`` already accepts ``cancelled`` — the run
    moves from AUTOMATIC resume to EXPLICIT, owner-authenticated resume, which is what a
    Stop should mean.

    SCOPE — single-process only. ``_is_run_live`` is process-local, and today the
    deployment is single-process (``exec uvicorn``, no ``--workers``, no replicas), so
    "not live here" == "not live anywhere". Under the locked ECS Fargate to-be, a Stop
    landing on instance B would mark a row cancelled while instance A kept billing; that
    needs a cross-process liveness fact (lease/heartbeat) and is NOT solved here.
    """
    from agents.execution_engine.engine import NON_TERMINAL_RUN_STATUSES

    db = _get_db()
    try:
        wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        status_now = wr.status if wr is not None else None
    finally:
        db.close()

    # Already terminal (or gone) — nothing is owed, so answer exactly as before, key order
    # included, and write nothing. This is what makes a repeated Stop idempotent.
    if status_now not in NON_TERMINAL_RUN_STATUSES:
        return {
            "ok": True, "run_id": run_id, "accepted": False, "cancelled": False,
            "status": "not_running", "message": "No active pipeline",
        }

    await _record_cancellation_in_the_durable_tail(run_id)
    try:
        # AUTHORITATIVE, unlike the audit row above: this is the write that closes the
        # money hole, so it must not inherit _reconcile_terminal_status's best-effort
        # degrade. A failure is reported as a failure.
        _persist_resume_status(run_id, "cancelled")
    except Exception as exc:  # noqa: BLE001 — surfaced, never swallowed into a false ack
        logger.error(
            "cancel(run=%s): terminal status write FAILED: %s", run_id, exc, exc_info=True
        )
        raise _reject(
            "cancel_not_persisted",
            "The run could not be marked cancelled; it may still resume on the next "
            "restart. Retry the Stop.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            recoverable=True,
        ) from exc

    return {
        "ok": True, "run_id": run_id, "accepted": True, "cancelled": True,
        "status": "cancelled",
    }


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Cooperatively cancel a run over HTTP (mirrors WS ``cancel_pipeline``).

    Owner-gated (T-29-03-3) → 404 on cross-owner. Sets the per-run cooperative
    ``asyncio.Event`` in ``_CANCEL_EVENTS`` (ISS-007) — the engine observes it at its next
    boundary and emits ``pipeline_cancelled`` through the normal persisted+drained path,
    which is what writes the terminal ``WorkflowRun.status``; suspend/persist semantics are
    unchanged. ``stop_run_driver`` backstops the mid-model-call blind window.

    ISS-084 — the response is an ACCEPTANCE, not a claim of cancellation. It used to
    answer ``cancelled: true`` whenever an Event object existed in a dict and ``.set()``
    did not raise, which said nothing about whether any consumer held that object. For
    every resumed run that Event was an orphan, so the field was ``true`` in exactly the
    case where cancelling was impossible — an unfalsifiable success that turned a visible
    failure into a silent one while the run kept billing. Liveness (``_is_run_live``, the
    driver TASK, which also self-heals a stale registration) is now the truth condition,
    and the field says what actually happened:

      * ``accepted: true`` + ``status: "stopping"`` — a live driver was signalled. The
        terminal follows on the event stream; it is not asserted here.
      * ``accepted: true`` + ``cancelled: true`` + ``status: "cancelled"`` — no live
        driver, but the run was still owed work, so the Stop was made DURABLE here
        (ISS-089). Nothing follows on the event stream; the row is already terminal.
      * ``accepted: false`` + ``status: "not_running"`` — nothing to stop (idempotent ack,
        so the client UI still returns to idle).
    """
    if not _review_gate_owned_by(run_id, current_user.id):
        raise _deny_unknown_gate()

    # Ordering: the liveness probe self-heals (and clears _CANCEL_EVENTS for) a stale
    # registration, so it must run BEFORE the event lookup.
    if not _is_run_live(run_id):
        return await _cancel_run_without_a_live_driver(run_id)

    event: asyncio.Event | None = _CANCEL_EVENTS.get(run_id)
    if event is not None:
        event.set()
    _arm_cancel_escalation(run_id)
    return {
        "ok": True, "run_id": run_id, "accepted": True, "cancelled": False,
        "status": "stopping",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/runs/{id}/resume — user resume-from-failed (RESUME-18 / Phase 50).
# ═══════════════════════════════════════════════════════════════════════════════
#
# The "reopen & fix" headline: a terminal-FAILED run becomes user-resumable. The
# endpoint is the ONLY new surface — drive is pure reuse of the shipped Phase 45–49
# resume tier via ``engine.resume_run`` (armed on the startup singleton, main.py:141-154;
# the live-layer callbacks fire off ``self.*`` — NOT re-threaded here, RESUME-10 by
# construction). Authorized by the LOCK-E/ND-4 supersede record — POR §8.1.
#
# The one pinned decision (RESEARCH §Arm-Failure): ``resume_run``/``_drive_resumed_stream``
# write NO ``WorkflowRun.status`` (only the app-layer launch/revision drivers do). A bare
# ``create_task(resume_run)`` would strand a user-resumed run at ``running`` forever on
# success AND on arm-failure. So the endpoint spawns a THIN ``_drive_user_resume`` wrapper
# that delegates ALL drive to ``resume_run`` and adds ONLY the two status writes the resume
# tier structurally lacks: terminal reconcile (``_reconcile_terminal_status``) + arm-failure
# flip-back (``_flip_back_to_failed``). This is NOT a third driver — no ``engine.execute``
# event ladder, no clone of ``_drive_launch_to_queue`` (INV-12 / Pitfall 7).


@router.post("/{run_id}/resume")
async def resume_run_endpoint(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Resume a terminal-FAILED or CANCELLED run over HTTP (RESUME-18 / KAN-120).

    Ordering pin (RESEARCH §Ordering Pin — all on the single event loop; NO ``await``
    between the overlap mutex and the synchronous queue+task registration, which is the
    double-POST atomicity argument):
      1. Owner gate — ``.filter(id==run_id, user_id==current_user.id).first()`` → None →
         404 (cross-owner AND missing indistinguishable; no existence oracle; keyed on
         ``user_id`` never nullable ``owner_id``). *(Layer 1; ScopedStore default-deny
         inside ``resume_run`` is Layer 2.)*
      2. Eligibility — ``status in {"failed", "cancelled"}`` is resumable; anything else
         → 409 ``run_not_resumable``.
      3. Overlap mutex — a registry-live run (``_PIPELINE_TASKS`` OR ``_PIPELINE_QUEUES``)
         → 409 ``pipeline_already_running`` (CR-01). NO ``await`` before step 4.
      4. Register the live queue + cancel-event SYNCHRONOUSLY — BEFORE the status flip
         (BUG-015 live-attach: the FE must never observe ``running`` without a live queue).
      5. Flip ``failed/cancelled→running`` + commit (existing status vocabulary; no new
         status).
      6. Stamp the additive ``run_resuming`` marker (reuse the engine method — the
         double-drive guard + workspace recovery; NOT a status).
      6b. Clear the in-memory state machine entry — a ``cancelled`` run resumed within the
         SAME process session has ``"cancelled"`` locked in the singleton; clearing it lets
         ``_execute_impl``'s ``transition(…, "generating")`` proceed normally. For a
         ``failed`` run resumed after a restart the entry is absent (new process) so pop
         is a no-op. Safe: DB status is already ``running`` at this point.
      7. Spawn ``_drive_user_resume`` + register the task (closes the mutex window).
      8. Return 200 ``{"run_id": run_id}``.
    """
    from agents.execution_engine.engine import get_execution_engine

    db = _get_db()
    try:
        # (1) Owner gate — cloned from ``create_revision`` (IDOR → 404, never 403).
        wr = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == current_user.id)
            .first()
        )
        if wr is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run"
            )

        # (2) Eligibility — failed, degraded, and cancelled runs are resumable; anything else → 409.
        # A "degraded" run completed partially (some agents failed, some succeeded) —
        # the user should be able to resume it to retry the failed portion. A
        # successfully "completed" run is DELIBERATELY excluded (not resumable) even
        # though it IS in the canonical terminal set — resume-eligibility is a
        # NARROWER predicate than "is this run terminal", so it stays its own literal
        # rather than reusing TERMINAL_RUN_STATUSES directly (API-001 unified the
        # SEPARATE stray duplicate of this exact set that used to live in
        # ``_review_gate_run_is_terminal``, not this deliberately-different one).
        _RESUMABLE_STATUSES = frozenset(TERMINAL_RUN_STATUSES) - {"completed"}
        if wr.status not in _RESUMABLE_STATUSES:
            raise _reject(
                "run_not_resumable",
                f"Run is {wr.status!r}; only failed, degraded, or cancelled runs are resumable",
                http_status=status.HTTP_409_CONFLICT,
            )

        # (3) Overlap mutex — the authoritative liveness signal is the in-process DRIVER
        # TASK (NOT the DB status, and NOT bare registry membership: a stale entry from a
        # driver that raised before its cleanup used to 409 this run forever). NO ``await``
        # between this check and the synchronous registration in step 4 (asyncio
        # no-preemption ⇒ a concurrent double-POST resuming after step 4 sees the entry
        # → 409). ``_is_run_live`` is a plain ``def`` precisely to preserve that.
        if _is_run_live(run_id):
            raise _reject(
                "pipeline_already_running",
                "Run is already live",
                http_status=status.HTTP_409_CONFLICT,
            )

        # (4) Register queue + cancel-event SYNCHRONOUSLY, BEFORE the status flip
        # (BUG-015 live-attach). ``_get_or_create_queue`` is idempotent.
        _get_or_create_queue(run_id)
        _CANCEL_EVENTS[run_id] = asyncio.Event()

        # (5) Flip failed/cancelled/degraded→running (existing status vocabulary; INV-12) + commit.
        wr.status = "running"
        db.commit()

        # (6b) Clear the in-memory state machine entry so _execute_impl's
        # transition(run_id, "generating") does not hit the terminal-state guard.
        # A cancelled run resumed in the SAME process session has "cancelled" locked;
        # a failed run resumed after a restart has no entry (new process) → pop is
        # a no-op in that case. The DB status is already "running" (step 5) so
        # clearing the in-memory mirror is safe ownership-wise.
        # D5 (KAN-139): use the public StateMachine.forget_run() instead of the private
        # dict reach (FIX-105 workaround) — the new method is the authorised eviction path.
        from agents.execution_engine.state_machine import get_state_machine
        get_state_machine().forget_run(run_id)
    finally:
        db.close()

    # (7) Spawn the thin drive wrapper + register the task (closes the mutex window
    # opened at step 3). The armed-singleton hooks fire automatically inside resume_run.
    # NOTE: _stamp_resume_marker is called INSIDE _drive_user_resume (step 6 moved
    # to background) so this endpoint returns immediately without blocking on DB reads.
    task = asyncio.create_task(_drive_user_resume(run_id, user=current_user))
    _PIPELINE_TASKS[run_id] = task

    # (8) Return the standard command envelope.
    return {"run_id": run_id}


async def _drive_user_resume(run_id: str, *, user: User) -> None:
    """The THIN drive wrapper the resume endpoint spawns (RESEARCH §Arm-Failure, PINNED).

    Delegates 100% of drive to ``engine.resume_run`` (the SOLE drive path — the armed
    singleton's live-layer hooks fire off ``self.*``, so NO callbacks are re-threaded here;
    ``resume_run`` accepts none, and adding them would be dead code) and adds ONLY the two
    status writes the resume tier structurally lacks: on success, reconcile the terminal
    status from the durable tail; on any failure, flip back to ``failed`` (honest state —
    never stuck ``running`` with no live task, T-50-06).

    HARD FENCE (INV-12 / Pitfall 7): this body MUST NOT contain an
    ``async for ... engine.execute(`` event ladder and MUST NOT clone
    ``_drive_launch_to_queue``'s per-event accumulation. It is NOT a third driver.
    """
    from agents.execution_engine.engine import get_execution_engine

    engine = get_execution_engine()
    try:
        # Stamp the run_resuming marker (best-effort audit, moved from the
        # endpoint handler so the HTTP response returns immediately).
        db = _get_db()
        try:
            wr_snap = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if wr_snap is not None:
                await engine._stamp_resume_marker(wr_snap)
        except Exception as _stamp_exc:  # noqa: BLE001
            logger.warning("_drive_user_resume: stamp failed run=%s: %s", run_id, _stamp_exc)
        finally:
            db.close()

        await engine.resume_run(run_id)  # SOLE drive path — armed-singleton hooks fire.
        await _reconcile_terminal_status(run_id)
    except Exception as exc:  # noqa: BLE001 — any drive failure → honest state
        logger.error(
            "user-resume drive failed run=%s: %s", run_id, exc, exc_info=True
        )
        _flip_back_to_failed(run_id, str(exc))


async def _reconcile_terminal_status(run_id: str) -> None:
    """Persist the terminal ``WorkflowRun.status`` from the durable ``run_events`` tail.

    The resume tier writes no status, so the app layer reconciles it here — reading the
    run's OWNER-SCOPED durable tail (the SAME event→status decision the launch driver
    applies at ``_drive_launch_to_queue:1470-1491``, but read from the durable tail rather
    than a live stream): terminal ``pipeline_cancelled`` → ``cancelled``; a
    ``pipeline_complete`` carrying ``status=="degraded"`` → ``degraded``; a clean
    ``pipeline_complete`` with no ``pipeline_failed`` → ``completed``; anything else /
    no clean terminal → ``failed`` (the D2 fail-safe). Best-effort: the offline harness /
    a read error degrades to leaving the prior status (INV-3) — the arm-failure path owns
    the honest-state guarantee, so a reconcile no-op never strands a genuinely-failed run.
    """
    from agents.authz import ScopedStore

    # Resolve the owner principal for the owner-scoped tail read (never the nullable
    # owner_id alone — mirror _stamp_resume_marker's principal resolution).
    db = _get_db()
    try:
        wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if wr is None:
            return
        owner_id = wr.owner_id or wr.user_id or f"anon:{wr.session_id or run_id}"
    finally:
        db.close()

    try:
        from agents.execution_engine.engine import get_execution_engine

        engine = get_execution_engine()
        workspace_id = await engine._recover_workspace_id(owner_id, run_id)
        store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
        events = await store.read_events(run_id, after_seq=0)
        cancelled = any(e.type == "pipeline_cancelled" for e in events)
        failed = any(e.type == "pipeline_failed" for e in events)
        completes = [e for e in events if e.type == "pipeline_complete"]
        degraded = any(
            isinstance(e.payload_json, dict)
            and e.payload_json.get("status") == "degraded"
            for e in completes
        )
        # KAN-120: a resumed run has BOTH pipeline_cancelled (from the original
        # cancellation) AND pipeline_complete (from the resume) in the durable tail.
        # The original logic unconditionally prioritised cancelled, leaving a
        # successfully-resumed run with status="cancelled" in history.
        # Fix: a clean pipeline_complete belonging to a LATER ATTEMPT than the last
        # pipeline_cancelled supersedes that cancellation → completed.
        #
        # FIX-229 (ISS-078): "later attempt", not merely "higher seq". A user who
        # REJECTS at a gate on a resumed run produces both events within ONE attempt —
        # the engine emits pipeline_cancelled and the dispatch loop then falls through
        # to the run's single pipeline_complete emitter:
        #     … 5:review_gate_ready | 6:pipeline_cancelled | 7:pipeline_complete
        # On a bare seq comparison that trailing complete wins and the run the user
        # explicitly rejected is recorded as "completed". An attempt boundary is a
        # run_resuming / pipeline_start row, so require one BETWEEN the cancellation
        # and the winning completion — same-attempt tails then keep the cancellation.
        cancelled_seqs = [e.seq for e in events if e.type == "pipeline_cancelled"]
        complete_seqs = [e.seq for e in completes
                         if not (isinstance(e.payload_json, dict)
                                 and e.payload_json.get("status") == "degraded")]
        reattempt_seqs = [e.seq for e in events
                          if e.type in ("run_resuming", "pipeline_start")]
        resume_supersedes = (
            cancelled
            and complete_seqs
            and max(complete_seqs) > max(cancelled_seqs)
            and any(
                max(cancelled_seqs) < s < max(complete_seqs) for s in reattempt_seqs
            )
        )
        if cancelled and not resume_supersedes:
            new_status = "cancelled"
        elif degraded:
            new_status = "degraded"
        elif completes and not failed:
            new_status = "completed"
        else:
            new_status = "failed"
        # BUG-R03: feed the SAME durable tail to the shared output-column mapping so a
        # USER-resumed completion persists output/agent_outputs/token_usage/duration/
        # deliverable_* — the columns _drive_launch_to_queue writes on the launch path,
        # which the resume tier is otherwise structurally silent on (only the engine state
        # machine wrote status). App-layer, always runs on the user-resume drive regardless
        # of whether the engine _resume_output_persist_sink hook is armed (INV-12 mapping).
        _persist_resume_output_columns(run_id, events)
    except Exception as exc:  # noqa: BLE001 — best-effort reconcile (offline degrade)
        logger.warning("_reconcile_terminal_status(%s) failed: %s", run_id, exc)
        return

    _persist_resume_status(run_id, new_status)


def _flip_back_to_failed(run_id: str, err: str) -> None:
    """Flip a user-resumed run back to ``failed`` + record the error (T-50-06 honest
    state — never left stuck ``running`` with no live task). The ``_persist_terminal_status``
    idiom with ``new_status="failed"`` + ``wr.error``."""
    _persist_resume_status(run_id, "failed", error=err)


def _persist_resume_status(run_id: str, new_status: str, *, error: str | None = None) -> None:
    """The shared terminal-status persist idiom (``_persist_terminal_status:1707``):
    ``_get_db``/query/``.status=``/``completed_at``/commit/``finally close``. Best-effort —
    a schemaless / offline session degrades without perturbing the drive (INV-3)."""
    sdb = _get_db()
    try:
        swr = sdb.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if swr:
            swr.status = new_status
            if error is not None:
                swr.error = error
            swr.completed_at = datetime.now(timezone.utc)
            sdb.commit()
    finally:
        sdb.close()


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/runs/{id}/messages — the chat backbone up-channel (CHAT-01/02/05, 29-09).
# ═══════════════════════════════════════════════════════════════════════════════
#
# A user chat turn reaches a run over REST, persists durably as a ``chat_message``
# ``run_events`` row (idempotent by client ``message_id``), and is delivered per the
# run's GENERIC live state by the mechanical intent router (``chat_router.route_chat_turn``)
# with ZERO model calls: clarify answer / gate action (incl. update_specs→KAN-101) /
# steering note / revision.
#
# LOCK-B / D-01: NO new table — the turn is a ``chat_message`` row appended through the
# SAME ``ScopedStore.append_event`` stamping boundary (seq/event_id) every engine event
# rides. The ``chat_message`` type + the ``message_id`` volatile-strip were seeded in
# Phase 28 (test_phase3_cutover_verify._DOCUMENTED_EVENT_TYPES / _normalize).


class MessageCommand(BaseModel):
    """Body for ``POST /api/runs/{id}/messages`` — one up-channel chat turn.

    ``message_id`` is the FE-generated idempotency key (a replay is a no-op).
    ``action`` is the optional gate-action discriminator (approve/reject/redo/
    update_specs); ``sticky`` marks an uploaded-context steering note (D-06);
    ``responses``/``skip_clarification`` carry structured clarify answers;
    ``target_artifact_type`` the revision target. ``attachments`` are payload-transient
    refs (ND-10 — never persisted to sandbox/DB; a placeholder marks them on replay).
    ``file_contents`` are FIX-218 pre-extracted file texts — [{name, text, error?}] —
    sent by the FE after client-side text extraction (text formats) or a
    /api/files/extract-text round-trip (binary: pdf/docx/pptx). Payload-transient
    (ND-10): content rides the live Concierge ctx and ectx.steering_notes for the next
    agent dispatch only — never persisted (the attachment ref row stays retained:false).
    """

    text: str = ""
    attachments: list[dict] | None = None
    message_id: str
    action: str | None = None
    sticky: bool = False
    responses: list[dict] | None = None
    skip_clarification: bool = False
    analysis_report: str | None = None
    target_artifact_type: str | None = None
    # concierge: the generic free-form marker (Phase 33 / D-04) the FE sets on a lane
    # "ask the Concierge" turn. A NON-workflow discriminator (SC-001/INV-1) — it opts the
    # turn into the free-form→Concierge escalation (route_chat_turn → CHANNEL_CONCIERGE)
    # without disturbing the zero-model routing of any routable turn. Default False ⇒
    # dormant (byte-identical Phase-29 routing for every non-concierge turn, INV-12).
    concierge: bool = False
    # file_contents: FIX-218 (KAN-170) — pre-extracted file text from chat attachments.
    # Each entry: {name: str, text: str, error?: str}. Additive optional; default None
    # ⇒ dormant (byte-identical routing, INV-3). The FE populates this AFTER extraction
    # (client-side for text formats; /api/files/extract-text for binary) and sends it
    # alongside body.attachments. Payload-transient (ND-10) — never persisted; the text
    # is threaded to _ConciergeCtx.attached_files and apply_steering for the live ectx.
    file_contents: list[dict] | None = None
    # confirm_proposal: the FE confirm round-trip (33-04). A concierge turn carrying a
    # previously-HELD consequential proposal to EXECUTE: {"channel": ..., "params": {...}}
    # reconstructed from the durable ``concierge_proposal`` row. Present ⇒ the held intent
    # is disposed CONFIRMED through its Phase-29 seam; absent ⇒ a fresh free-form ask.
    confirm_proposal: dict | None = None
    # chain_hints: the FE-computed chain suggestions [{id,label}] from the settled-run
    # lane (c72), threaded to the Concierge ctx as GENERIC data the prompt reflects — no
    # workflow-name branch (INV-1). Additive optional; default None ⇒ dormant (byte-
    # identical Phase-29 routing for every non-concierge turn; no chain block when absent).
    chain_hints: list[dict] | None = None
    # images: per-turn image attachments (UPLD-02 residue, 30-03) — untrusted base64
    # {mime_type, data} entries cap-validated by the SHARED ``_validate_images`` ingress
    # caps (the exact caps the launch path uses) BEFORE queueing; a violation → 400.
    # PAYLOAD-TRANSIENT (ND-10/LOCK-E): threaded onto the live run's next dispatch via
    # ``apply_turn_images``, never persisted (the chat_message row keeps retained:false
    # refs, no bytes). Default None ⇒ dormant (no image flow → run_images unchanged).
    images: list | None = None


# ---------------------------------------------------------------------------
# A.3 (Phase 43) — live-ectx registry: the run_id → in-process ExecutionContext map
# ---------------------------------------------------------------------------
# The process-local registry that lets a mid-run chat turn reach the RUNNING run's live
# in-process context. Mirrors the ``_PIPELINE_TASKS`` / ``_CANCEL_EVENTS`` per-run registries
# (websocket.py) — a plain module-level dict, safe for the single-process asyncio runtime (all
# access is on the event loop thread; no cross-thread mutation). The engine REGISTERS a run's
# ExecutionContext at run start (``register_live_ectx``, via an INJECTED callback so no
# engine→app import edge is created) and UNREGISTERS it on teardown (``unregister_live_ectx``,
# the engine's finally-block — no leak). Keyed by run_id ONLY (SC-001/INV-1); a lookup returns
# exactly that run's ectx, so two concurrent runs never cross-deliver steering/images.
_LIVE_ECTX: dict[str, Any] = {}


def register_live_ectx(run_id: str, ectx: "Any") -> None:
    """Register a RUNNING run's live in-process ``ExecutionContext`` (A.3).

    Injected into ``ExecutionEngine.execute(live_ectx_register=…)`` and called once at run
    start, right after the per-run context is constructed. Keyed by run_id so
    ``_live_ectx_for_run`` can resolve it for the duration of the run. Idempotent: a second
    register for the same run_id simply overwrites (a resumed run re-registers its rebuilt ctx).
    """
    _LIVE_ECTX[run_id] = ectx


def unregister_live_ectx(run_id: str) -> None:
    """Deregister a run's live ectx on teardown (A.3) — no leak.

    Injected into ``ExecutionEngine.execute(live_ectx_unregister=…)`` and called from the
    engine wrapper's finally-block (ALWAYS — normal completion, error, or early GeneratorExit).
    ``pop`` with a default so a never-registered / double-unregister run_id is a safe no-op.
    """
    _LIVE_ECTX.pop(run_id, None)


def _live_ectx_for_run(run_id: str):
    """Resolve the LIVE in-process ``ExecutionContext`` for ``run_id`` (A.3), or ``None``.

    Returns the ``ExecutionContext`` the running engine registered for ``run_id`` (via
    ``register_live_ectx``), so a mid-run steering note (``chat_router.apply_steering`` →
    ``ectx.steering_notes`` → the engine's ``=== USER GUIDANCE ===`` drain) or a per-turn image
    (``chat_router.apply_turn_images`` → ``ectx.pending_turn_images`` → the engine's
    ``_drain_turn_images`` one-shot carrier) reaches the NEXT agent dispatch. This ONE handle
    closes both the steering deferral (DEF-29-09-1) and the per-turn-image deferral
    (DEF-30-03-1) — a single registry, a single seam (INV-12).

    Degrade-safe: a run NOT live in THIS process (never registered, already terminated, or
    running behind a different worker) resolves to ``None`` → ``apply_steering`` /
    ``apply_turn_images`` no-op, and the durable ``chat_message`` row remains the record (the
    note is re-derived on resume from ``run_events``; images are payload-transient, ND-10).
    Keyed by run_id ONLY (SC-001/INV-1) — the endpoint already owner-gated the run (404) BEFORE
    reaching here, so a caller only ever resolves their own run's ectx (T-43-05-XINJECT).
    """
    return _LIVE_ECTX.get(run_id)


def _chat_event_id(message_id: str) -> str:
    """Derive the durable ``event_id`` from the client ``message_id`` (D-01).

    Idempotency lives at the stamping boundary: the same ``message_id`` yields the same
    ``event_id``, so a replayed turn resolves to an already-present ``run_events`` row
    (a no-op — no second row). Namespaced so it can never collide with an engine-emitted
    uuid ``event_id``.
    """
    return f"chat:{message_id}"


async def _persist_chat_message(
    store, run_id: str, body: "MessageCommand"
) -> tuple[bool, int]:
    """Append the turn as a ``chat_message`` ``run_events`` row (idempotent).

    Returns ``(created, seq)``: ``created=False`` when a row with the derived
    ``event_id`` already exists (a replayed ``message_id`` → no-op). The ``seq`` is the
    next contiguous per-run seq (max persisted + 1), exactly as the engine sink and the
    resume marker compute it (engine.py:_stamp_resume_marker) — but CR-03: allocated +
    idempotency-checked through ``ScopedStore.append_event_next_seq``, which serializes
    against the engine's own concurrently-scheduled event sink (and a double-submitted
    ``message_id``) on the additive ``run_events`` uniqueness constraints, so a race can
    never persist a duplicate ``seq`` (Last-Event-ID replay) or a duplicate row.
    """
    # ND-10: attachment bytes are payload-transient — NEVER persisted.
    # But metadata (kind, name, mimeType, sizeBytes) IS persisted as a ref so
    # the transcript can show the filename on replay/reopen (FIX-218).
    # The `retained: False` flag tells the FE the bytes are gone (honest placeholder).
    attachment_refs = [
        {
            "kind": (a.get("kind") or a.get("type") or "attachment"),
            "name": str(a.get("name") or "").strip(),
            "mimeType": a.get("mimeType") or a.get("mime_type") or None,
            "sizeBytes": a.get("sizeBytes") or a.get("size_bytes") or None,
            "retained": False,
        }
        for a in (body.attachments or [])
    ]
    # ND-10/LOCK-E (30-03): per-turn images are ALSO payload-transient — stamp a
    # retained:false ref with NO ``data``/bytes so replay/reopen shows "image not kept"
    # (the image rides the live dispatch only, never the durable log). The bytes live
    # solely on the transient carrier drained by the engine.
    attachment_refs.extend(
        {"kind": "image", "retained": False}
        for img in (body.images or [])
        if isinstance(img, dict)
    )
    return await store.append_event_next_seq(
        run_id,
        event_id=_chat_event_id(body.message_id),
        type="chat_message",
        payload_json={
            "pipeline_run_id": run_id,
            "message_id": body.message_id,
            "text": body.text,
            "attachments": attachment_refs,
        },
    )


# ---------------------------------------------------------------------------
# Concierge disposal (33-03 / D-05) — the app layer DISPOSES the Concierge's
# proposal-only intents through the SAME Phase-29 seams the mechanical router uses.
# NO new execution path (INV-12): gate_action → set_review_response, steering_note →
# apply_steering, revision → _mint_revision_row + _drive_revision_to_queue.
# ---------------------------------------------------------------------------

# The Concierge PROPOSES gate actions in its own vocabulary ({approve, reject,
# request_changes, update_specs}); the Phase-29 gate seam (store.set_review_response)
# names "changes requested, carrying instructions" `redo`. Reconcile the ONE differing
# name here so a proposed action never reaches the seam unrecognized (never silently
# passed through). approve/reject/update_specs are identical on both sides.
_CONCIERGE_GATE_ACTION_MAP = {"request_changes": "redo"}

# The two CONSEQUENTIAL proposal channels — held behind a confirm chip (T-33-03-01).
# steering_note is non-consequential (best-effort nudge) and applies immediately.
_CONSEQUENTIAL_PROPOSAL_CHANNELS = frozenset({"gate_action", "revision", "chain"})

# Strong references to the fresh-Concierge streaming DRIVE tasks (Option B). The
# ``_drive`` task performs the turn's DURABLE side-effects (the ``chat_reply`` row + the
# proposal drain/disposal) INDEPENDENTLY of client consumption, so it must NOT be
# garbage-collected while it runs — hold a reference here and discard on completion. It
# is never cancelled on client disconnect (the durable writes land even if the streamed
# body is dropped mid-stream).
_CONCIERGE_STREAM_TASKS: set = set()

# FIX-218 (KAN-170): character cap for a single attached file's text in the Concierge
# system prompt and the steering note. Keeps the combined prompt within reasonable
# token bounds while still giving agents enough context. Mirrors the launch-composer
# ATTACH_MAX_CHARS constant on the FE (6,000 chars).
_ATTACHED_FILE_TEXT_CAP = 6_000


def _build_attached_files_block(file_contents: list[dict] | None) -> str:
    """FIX-218 (KAN-170): render pre-extracted file texts into a prompt block.

    ``file_contents`` is the ``body.file_contents`` list — each entry:
    ``{name: str, text: str, error?: str}``. Builds a multi-file block capped
    per-file at ``_ATTACHED_FILE_TEXT_CAP`` chars. Returns ``""`` when the list is
    absent or all entries have extraction errors (so the Concierge prompt is
    byte-identical to the pre-fix behaviour — INV-3).

    Payload-transient (ND-10): the block is used solely in the live Concierge ctx
    and the ``ectx.steering_notes`` carry; it is NEVER persisted to the DB.
    """
    if not file_contents:
        return ""
    parts: list[str] = []
    for entry in file_contents:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "attachment").strip()[:200]
        error = entry.get("error")
        text = str(entry.get("text") or "").strip()
        if error:
            # Extraction failed — include a diagnostic note so the Concierge can
            # inform the user rather than silently omitting the file.
            parts.append(f"=== ATTACHED FILE: {name} ===\n[Extraction error: {error}]\n=== END FILE ===")
        elif text:
            capped = text[:_ATTACHED_FILE_TEXT_CAP]
            suffix = "\n[Content truncated — showing first portion]" if len(text) > _ATTACHED_FILE_TEXT_CAP else ""
            parts.append(f"=== ATTACHED FILE: {name} ===\n{capped}{suffix}\n=== END FILE ===")
    return "\n\n".join(parts)

class _ConciergeCtx:
    """The minimal owner-scoped ctx handed to ``ConciergeCapability.converse``.

    Carries only what the Concierge reads: the ``run_id``, the owner+workspace
    ``ScopedStore`` (its ONLY read surface), ``model=None`` (Haiku default via the
    sanctioned runner), and the run's ``compiled`` CompiledWorkflow (M3 — the manifest
    ``chat:`` block the Concierge injects into its system prompt, or ``None``).
    ``conversation_context`` is absent + ``compiled`` may be ``None`` ⇒ the Concierge
    degrades gracefully (``getattr`` defaults). No workflow name is ever passed (INV-1);
    ``compiled`` is DATA (a typed plan), never a name branch.

    ``chain_hints`` (c72) is DATA the Concierge reflects: the FE-curated chain
    suggestions ``[{id,label}]`` from the settled-run lane. Absent ⇒ ``[]`` ⇒ the
    ``_compose_system_prompt`` getattr default degrades safely (no chain block). No
    workflow name is ever passed — only display labels the FE already surfaced.

    ``run_summary`` (FIX-116) is a short human-readable summary of WHAT this run produced,
    injected into the system prompt so the Concierge knows the deliverable without having
    to read all run events first. Derived from wr.title + wr.output (first 400 chars) —
    GENERIC, never a workflow-name branch (INV-1). Absent → degrade safely.
    """

    def __init__(
        self, *, run_id, scoped_store, owner_id, workspace_id, compiled=None,
        chain_hints=None, run_summary=None, open_gate=None, run_status=None,
        attached_files=None,
    ):
        self.run_id = run_id
        self.scoped_store = scoped_store
        self.owner_id = owner_id
        self.workspace_id = workspace_id
        self.model = None
        self.compiled = compiled
        self.chain_hints = chain_hints or []
        self.run_summary = run_summary or ""
        # FIX-210 (ISS-054): the run's current gate state — "questionnaire", "review",
        # or None. Injected into the system prompt so the Concierge gives an accurate
        # status answer when the run is paused at clarify/review instead of reporting
        # a stale state from reading events. GENERIC — opaque string, no workflow name.
        self.open_gate = open_gate or ""
        # The run's persisted status (WorkflowRun.status) — used to distinguish a
        # live-building run from a completed one so the prompt label is accurate.
        self.run_status = run_status or ""
        # ISS-092: DECLARE the ``conversation`` inject so ``context_provider:conversation``
        # surfaces this run's bounded chat transcript. Before this, the Concierge's only
        # cross-turn memory was the unbounded read_events tool happening to return chat
        # rows inside the whole event log; with that tool gone, this is what keeps
        # multi-turn coherent. The provider self-gates on this token, so declaring it
        # HERE — on the Concierge ctx alone — leaves every pipeline agent untouched and
        # the characterization goldens byte-identical (INV-3).
        self.current_spec_injects = {"conversation"}
        # FIX-218 [dev] (KAN-170): pre-extracted file text from chat attachments. A rendered
        # text block injected into the system prompt so the Concierge can answer
        # questions about the file and surface a propose_steering_note for injection.
        # Payload-transient (ND-10) — never persisted. Format: formatted text block
        # ready to inject into the system prompt, or "" when no files were attached.
        # NOTE (merge 2026-08-13): "FIX-218" here is dev's id. This branch's own FIX-218
        # was renumbered to FIX-252 on merge — see .planning/FIX-REGISTER.md.
        self.attached_files = attached_files or ""


def _resolve_concierge():
    """Resolve the shared ``chat:concierge`` capability impl (static registry lookup).

    A pure ``(kind, name)`` dict lookup — no workflow-name branch (SC-001/INV-1). Isolated
    in a helper so the offline test can monkeypatch it with a scripted fake (no live
    model call); production returns the registered ``ConciergeCapability`` (Haiku)."""
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    return CapabilityRegistry().resolve("chat", "concierge")


def _drain_concierge_proposals(concierge, ctx=None) -> list:
    """Return the ProposalIntents the Concierge surfaced this invocation (else []).

    Duck-typed forward seam: a concierge exposing ``drain_proposals`` returns the
    intents its ``converse`` surfaced. The intents are CTX-SCOPED (per-request) — the
    drain reads the per-request buffer ``converse`` stashed on ``ctx``, never shared
    instance state — so two overlapping requests never cross-contaminate. A drain that
    takes no ctx (e.g. a test fake stashing its own proposals) is called arg-free."""
    drain = getattr(concierge, "drain_proposals", None)
    if not callable(drain):
        return []
    try:
        return list(drain(ctx) or [])
    except TypeError:
        return list(drain() or [])


def _load_pending_proposal(events, *, message_id: str, channel: str) -> dict | None:
    """Locate the DURABLE pending ``concierge_proposal`` row for a confirm turn (H1/IDOR).

    The ask turn wrote it as event_id ``concierge-proposal:{message_id}:{channel}`` with
    status ``pending`` (``_dispose_concierge_proposal`` hold path). ``events`` is the
    caller's OWNER-SCOPED read (``ScopedStore.read_events`` default-deny), so a
    cross-owner / other-run pending row is simply NOT in the list → this returns ``None``
    → the caller raises 404 (IDOR → 404, never 403, never a 409 existence-leak).

    Idempotent-replay guard: a later ``concierge-proposal-resolved:{message_id}:{channel}``
    row means the intent was already disposed → treated as not-pending → ``None`` (a
    replayed confirm executes nothing twice). Returns the pending row's payload dict
    (carrying the DURABLE ``channel`` + ``params`` — the ONLY trusted source of the
    intent to execute) when a live pending row exists; else ``None``.
    """
    if not channel or not message_id:
        return None
    pending_id = f"concierge-proposal:{message_id}:{channel}"
    resolved_id = f"concierge-proposal-resolved:{message_id}:{channel}"
    pending_payload: dict | None = None
    resolved_seen = False
    for ev in events or []:
        if getattr(ev, "type", None) != "concierge_proposal":
            continue
        eid = getattr(ev, "event_id", None)
        payload = getattr(ev, "payload_json", None) or {}
        if eid == pending_id and payload.get("status") == "pending":
            pending_payload = payload
        elif eid == resolved_id:
            resolved_seen = True
    if pending_payload is None or resolved_seen:
        return None
    return pending_payload


async def _dispose_concierge_proposal(
    intent,
    *,
    confirmed: bool,
    store,
    art_store,
    run_id: str,
    message_id: str,
    current_user: "User",
    wr_status: str,
    wr_type: str,
    gate_key: str | None,
    ectx,
    open_gate: str | None = None,
    attached_files: str = "",
) -> dict:
    """Dispose ONE Concierge ``ProposalIntent`` through its matching Phase-29 seam (D-05).

    NO new execution path (INV-12) — the SAME functions the mechanical router uses:

      * ``steering_note`` → :func:`chat_router.apply_steering` (29-08). Non-consequential:
        applied immediately, best-effort (the durable ``chat_message`` row is the record,
        re-derived on resume — ND-9).
      * ``gate_action`` → ``store.set_review_response`` (the POST /gate seam). The proposed
        action is reconciled via ``_CONCIERGE_GATE_ACTION_MAP`` (request_changes→redo);
        the KAN-100 terminal fence + KAN-94 armed-gate ground truth are enforced so a
        proposal never resolves a stopped run or an unarmed gate.
      * ``revision`` → ``_mint_revision_row`` + ``_drive_revision_to_queue`` (D-02, SC-3) —
        the shipped family-child seam; live stitching rides the existing per-run queue +
        ``run_events``. Reuses ``REVISION_BASE_MAP`` (via ``_mint_revision_row``).

    CONSEQUENTIAL proposals (gate_action, revision) are HELD behind a confirm chip
    (T-33-03-01): when ``confirmed`` is False a durable ``concierge_proposal`` ``run_events``
    row is emitted carrying the pending intent and NO seam runs — the seam executes only on
    the subsequent confirmed turn (the FE confirm round-trip lands in 33-04). The row is
    additive (no new table; owner_id+workspace_id stamped by ``ScopedStore``).
    """
    channel = getattr(intent, "channel", None)
    params = dict(getattr(intent, "params", {}) or {})

    # ── steering_note → apply_steering (best-effort; applied immediately). ───────────
    # FIX-210 (ISS-054): EXCEPTION — when the run is paused at a questionnaire or
    # review gate, a steering note would unblock the clarify engine and auto-proceed
    # without user input. Treat it as consequential in that case: hold it behind a
    # confirm chip. The user asked a status question; the Concierge should NEVER
    # silently launch the build by applying a note that skips clarification.
    if channel == "steering_note":
        if open_gate in ("questionnaire", "review"):
            # Hold behind a confirm chip — identical to gate_action/revision path.
            await store.append_event_next_seq(
                run_id,
                event_id=f"concierge-proposal:{message_id}:{channel}",
                type="concierge_proposal",
                payload_json={
                    "pipeline_run_id": run_id,
                    "message_id": message_id,
                    "channel": channel,
                    "params": params,
                    "status": "pending",
                },
            )
            return {"channel": channel, "held": True, "params": params}
        from app.api.chat_router import apply_steering
        apply_steering(ectx, {"text": params.get("note", ""), "sticky": False})
        return {"channel": channel, "disposed": "steering"}

    # ── CONSEQUENTIAL: hold behind a confirm chip until the FE confirms (33-04). ─────
    if channel in _CONSEQUENTIAL_PROPOSAL_CHANNELS and not confirmed:
        await store.append_event_next_seq(
            run_id,
            event_id=f"concierge-proposal:{message_id}:{channel}",
            type="concierge_proposal",
            payload_json={
                "pipeline_run_id": run_id,
                "message_id": message_id,
                "channel": channel,
                "params": params,
                "status": "pending",  # awaiting the FE confirm round-trip (33-04)
            },
        )
        return {"channel": channel, "held": True, "params": params}

    # ── gate_action → store.set_review_response (KAN-94 armed + KAN-100 fenced). ─────
    if channel == "gate_action":
        from app.api.chat_router import TERMINAL_STATUSES

        if (
            wr_status in TERMINAL_STATUSES
            or not gate_key
            or not _gate_is_pending(art_store, gate_key)
        ):
            # A proposed gate resolution never resolves a stopped run or an unarmed gate.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "Pipeline is no longer running",
                    "code": "pipeline_not_running",
                    "recoverable": False,
                },
            )
        # M1: a MISSING action must NEVER silently approve a gate. Default to the
        # non-consequential ``request_changes`` (→ the seam's ``redo``), matching the
        # same safe-degrade the Concierge tool itself uses (concierge.py _gate_intent).
        raw_action = params.get("action", "request_changes")
        action = _CONCIERGE_GATE_ACTION_MAP.get(raw_action, raw_action)
        rationale = params.get("rationale") or None
        if action == "redo":
            await art_store.set_review_response(
                gate_key, approved=False, action="redo", instructions=rationale
            )
        elif action == "update_specs":
            # ISS-053: the Concierge reaches the same seam, so it rides the same fence.
            if not _review_gate_advertises_update_specs(gate_key):
                raise _deny_update_specs_not_offered(gate_key)
            await art_store.set_review_response(
                gate_key, approved=False, action="update_specs",
                instructions=rationale or "",
            )
        elif action == "reject":
            await art_store.set_review_response(gate_key, approved=False)
        elif action == "approve":
            await art_store.set_review_response(gate_key, approved=True)
        else:
            # ISS-070 hardening: currently unreachable — concierge.py:350 normalizes any
            # action outside _GATE_ACTIONS to request_changes, and these params are
            # server-written (H1), never client body. Fail closed so adding a member to
            # concierge.py:80 without a branch here cannot silently approve a gate.
            raise _deny_unknown_gate_action(action)
        return {"channel": channel, "disposed": "gate", "action": action}

    # ── chain → surface to FE as a chain proposal (FIX-115 / Option A). ───────────
    # The "chain" channel is CONSEQUENTIAL (held behind a confirm chip, T-33-03-01).
    # On confirm the FE calls onSuggestion(target_id) through the existing suggestion-
    # chip seam — no new backend execution path needed. The disposal here is
    # confirmation-only: return the target_id so the FE caller can fire it. The
    # target_id MUST be one the FE passed as chain_hints (validated FE-side before
    # calling onSuggestion). No workflow-name branch (SC-001/INV-1) — generic data.
    if channel == "chain":
        target_id = params.get("target_id", "")
        return {"channel": channel, "disposed": "chain", "target_id": target_id}

    # ── revision → _mint_revision_row + _drive_revision_to_queue (family child). ────
    if channel == "revision":
        # FIX-211: when the parent run is itself a revision (e.g. user_stories_revision),
        # wr_type already ends with "_revision". Using it verbatim as the target gives
        # "user_stories_revision_output" → revision_pipeline_type becomes
        # "user_stories_revision_revision" which is not in TIER_PIPELINES → 403.
        # Strip any trailing "_revision" suffix from wr_type to get the base artifact
        # family (e.g. "user_stories") before constructing the fallback target.
        base_type = wr_type.removesuffix("_revision") if wr_type.endswith("_revision") else wr_type
        # Two OD remap tables used to sit here (_OD_FALLBACK_MAP, _OD_TARGET_REMAP),
        # rewriting od_prototype/od_ppt targets onto their real revision pipelines.
        # They were a workaround for an incomplete alias table — the alias covered
        # the BASE label but never the ``_revision`` variant — and because they lived
        # in this handler only, the REST ``POST /runs/{id}/revisions`` entry point
        # skipped them entirely: the same revision succeeded from chat and failed
        # from REST. Both labels are now collapsed at the root (registry, manifests,
        # entitlements, and the persisted rows), so the derivation below needs no
        # correction and both entry points agree by construction.
        target = params.get("target") or f"{base_type}_output"
        instruction = params.get("instruction", "")
        # FIX-218: when files were attached on this Concierge turn, frame them as
        # supplementary reference material. The user's chat instruction always takes
        # precedence — if the file conflicts with or is unrelated to the request,
        # agents must follow the user's instruction and ignore irrelevant file content.
        if attached_files.strip():
            user_instruction = instruction.strip()
            file_section = (
                "=== USER'S REVISION REQUEST (PRIMARY — always follow this) ===\n"
                + (user_instruction if user_instruction else "(apply the reference material to improve the deliverable)")
                + "\n=== END USER REQUEST ===\n\n"
                "=== SUPPLEMENTARY REFERENCE MATERIAL (user-attached files) ===\n"
                "Use this content ONLY where it is relevant and consistent with the user's request above.\n"
                "If this content conflicts with or is unrelated to the user's request, IGNORE IT "
                "and follow the user's request exactly.\n\n"
                + attached_files.strip()
                + "\n=== END REFERENCE MATERIAL ==="
            )
            instruction = file_section
        rdb = _get_db()
        try:
            child_run_id, _ = _mint_revision_row(
                rdb, user=current_user, parent_run_id=run_id,
                target_artifact_type=target, instruction=instruction,
            )
        finally:
            rdb.close()
        cancel_event = asyncio.Event()
        _CANCEL_EVENTS[child_run_id] = cancel_event
        event_queue = _get_or_create_queue(child_run_id)
        task = asyncio.create_task(
            _drive_revision_to_queue(
                workflow_run_id=child_run_id,
                parent_run_id=run_id,
                target_artifact_type=target,
                instruction=instruction,
                user=current_user,
                cancel_event=cancel_event,
                event_queue=event_queue,
            )
        )
        _PIPELINE_TASKS[child_run_id] = task
        return {"channel": channel, "disposed": "revision", "revision_run_id": child_run_id}

    # Unknown channel — inert (a proposal never self-executes past the known seams).
    return {"channel": channel, "disposed": "noop"}


@router.post("/{run_id}/messages")
async def post_message(
    run_id: str,
    body: MessageCommand,
    current_user: User = Depends(get_current_user),
):
    """Persist + deliver one up-channel chat turn (CHAT-01/02/05, 29-09).

    Two-layer owner check (mirrors ``run_stream.py`` / ``runs.py::get_run_events``): the
    ``user_id`` ORM filter → 404, then the default-deny ``ScopedStore.get_run`` → 404
    (IDOR → 404, never 403). The turn persists as an idempotent ``chat_message`` row
    (D-01), then the mechanical router (Task 3 wiring) delivers it by run state.
    """
    from agents.authz import ScopedStore

    from app.api.chat_router import (
        CHANNEL_ANSWERS,
        CHANNEL_CONCIERGE,
        CHANNEL_GATE,
        CHANNEL_REVISION,
        CHANNEL_STEERING,
        ChatTurn,
        RunState,
        apply_steering,
        apply_turn_images,
        derive_open_gate,
        route_chat_turn,
    )

    # Layer 1: owner-scoped ORM filter (cross-owner / missing → 404, never 403).
    db = _get_db()
    try:
        wr = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == current_user.id)
            .first()
        )
        if wr is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found"
            )
        wr_status = wr.status
        wr_workspace = wr.workspace_id
        wr_type = wr.type
        # FIX-116: capture the run's title + first 400 chars of its deliverable output
        # so the Concierge knows what THIS run produced without calling read_events first.
        # Generic — uses wr.title (plain text) and wr.output (deliverable text), never
        # a pipeline_type / workflow-name branch (INV-1). 400 chars is enough to give
        # context (a user stories backlog excerpt, a prototype summary, etc.) while
        # keeping the system prompt token-budget small.
        _wr_title = (wr.title or "").strip()
        _wr_output = (wr.output or "").strip()
        _wr_output_preview = _wr_output[:400] + ("…" if len(_wr_output) > 400 else "")
        wr_run_summary = (
            (f"Run title: {_wr_title}\n" if _wr_title else "")
            + (f"Deliverable preview:\n{_wr_output_preview}" if _wr_output_preview else "")
        ).strip()
    finally:
        db.close()

    # Owner+workspace-scoped store — the SAME principal the SSE reader (run_stream.py)
    # uses, so the persisted chat_message row is visible on the same down-channel.
    store = ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)

    # Layer 2: default-deny re-resolve so the ownership boundary lives in ONE place.
    if await store.get_run(run_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found"
        )

    # ── Per-turn image ingress gate (UPLD-02 residue, 30-03) ─────────────────────────
    # A chat turn may carry images (payload-transient, ND-10). Validate them with the
    # SAME caps the launch path uses — ``_validate_images`` (mime allow-list, ~3.75MB/
    # image, ≤20, ~8MB aggregate, vision-model guard). Flag OFF / no images → ignored
    # (dormant). A cap/vision violation DENIES with 400 BEFORE any persist or queueing
    # (nothing queued). Endpoint is NOT rebuilt — this reuses the Phase-29 /messages path.
    validated_turn_images: list = []
    if settings.IMAGE_INPUT_ENABLED and body.images:
        base_model = (
            getattr(current_user, "preferred_model", None)
            or settings.BEDROCK_INFERENCE_PROFILE_ID
        )
        _image_error = _validate_images(body.images, effective_model_ids={base_model})
        if _image_error is not None:
            raise _reject("invalid_image_input", _image_error)
        validated_turn_images = list(body.images)

    # ── Persist the turn (idempotent, D-01) BEFORE routing so a delivered command is
    #    always backed by a durable record (family-anchored, D-02). ──────────────────
    created, seq = await _persist_chat_message(store, run_id, body)

    # ── Assemble the GENERIC run-state (name-free) + route mechanically (D-04). ──────
    events = await store.read_events(run_id, after_seq=0)
    gate_kind, gate_key = derive_open_gate(events)
    art_store = get_artifact_store()
    open_gate: str | None = None
    resolved_gate_key: str | None = None
    if gate_kind == "review" and gate_key:
        # KAN-94 event-driven ground truth: only a genuinely ARMED gate pauses. A
        # declared gate the engine skipped (gate_agent_ids exclusion) never armed one,
        # so the run is treated as running (steering), not a fabricated pause.
        if _gate_is_pending(art_store, gate_key):
            open_gate, resolved_gate_key = "review", gate_key
    elif gate_kind == "questionnaire":
        open_gate = "questionnaire"

    run_state = RunState(
        status=wr_status, open_gate=open_gate, gate_key=resolved_gate_key
    )
    turn = ChatTurn(
        text=body.text,
        message_id=body.message_id,
        action=body.action,
        sticky=body.sticky,
        responses=list(body.responses or []),
        skip_clarification=body.skip_clarification,
        analysis_report=body.analysis_report,
        target_artifact_type=body.target_artifact_type,
        concierge=body.concierge,
    )
    dispatch = route_chat_turn(run_state, turn)

    # ── Execute the dispatch through the SAME command seams (29-03/29-04/29-08). ─────
    if dispatch.channel == CHANNEL_ANSWERS:
        # clarify answer → the exact seam POST /answers wraps.
        await art_store.set_questionnaire_responses(
            run_id, dispatch.responses, skip_clarification=dispatch.skip_clarification
        )
    elif dispatch.channel == CHANNEL_GATE:
        if dispatch.fenced:
            # KAN-100 terminal fence: never resolve a gate on a stopped pipeline.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "Pipeline is no longer running",
                    "code": dispatch.code or "pipeline_not_running",
                    "recoverable": False,
                },
            )
        # gate action → the exact store.set_review_response seam POST /gate wraps. The
        # four actions ride the generic ``action`` discriminator; update_specs routes to
        # the shipped KAN-101 loop (never rebuilt).
        _gk = dispatch.gate_key
        if dispatch.action == "redo":
            await art_store.set_review_response(
                _gk, approved=False, action="redo", instructions=dispatch.instructions
            )
        elif dispatch.action == "update_specs":
            # ISS-053: this route needs no gate_key from the caller (the server derives it
            # from the event log), so it is the EASIEST ingress to replay — fence it too.
            if not _review_gate_advertises_update_specs(_gk):
                raise _deny_update_specs_not_offered(_gk)
            await art_store.set_review_response(
                _gk, approved=False, action="update_specs",
                instructions=dispatch.instructions or "",
            )
        elif dispatch.action == "reject":
            await art_store.set_review_response(_gk, approved=False)
        elif dispatch.action == "approve":
            await art_store.set_review_response(_gk, approved=True)
        else:
            # ISS-070 hardening: currently unreachable — BOTH Dispatch(channel=
            # CHANNEL_GATE) sites (chat_router.py:244/:255) require
            # turn.action in GATE_ACTIONS, which IS the ISS-119 routing contract and is
            # deliberately NOT touched here. Fail closed so adding a member to
            # GATE_ACTIONS without a branch here cannot silently approve a gate.
            raise _deny_unknown_gate_action(dispatch.action)
    elif dispatch.channel == CHANNEL_STEERING:
        # A.3 (Phase 43): resolve the RUNNING run's live in-process ectx ONCE (the live-ectx
        # registry now populates it at run start — DEF-29-09-1 closed) and drain BOTH the
        # steering note AND any per-turn images through that SINGLE handle (INV-12 — one
        # registry, one seam).
        #
        # 29-08 seam: the note is queued onto ectx.steering_notes for the NEXT agent dispatch
        # (ND-11 — base thread, next dispatch, no fork); the engine's _compose_context_message
        # renders + consume-once-clears it as a === USER GUIDANCE === block. The durable
        # chat_message row above IS the record (a run NOT live in this process resolves to None
        # → apply_steering no-ops; the note is re-derived on resume from run_events, ND-9).
        #
        # 30-03: a RUNNING-turn's cap-validated per-turn images ride the SAME live handle —
        # apply_turn_images enqueues them onto ectx.pending_turn_images and the engine drains
        # them onto the one-shot ectx.turn_images_once carrier at the next dispatch (payload-
        # transient, ND-10; rendered once, then cleared) — closing DEF-30-03-1. Keyed on the
        # generic queues only (SC-001/INV-1). Dormant when nothing is queued (INV-3).
        ectx = _live_ectx_for_run(run_id)
        if dispatch.note is not None:
            apply_steering(ectx, dispatch.note)
        if validated_turn_images:
            apply_turn_images(ectx, validated_turn_images)
        # FIX-218 (KAN-170): when file contents are attached during a RUNNING phase,
        # also inject them as a steering note for the next agent dispatch. Mirrors the
        # steering path (INV-12 — same apply_steering seam, no new path). Payload-
        # transient (ND-10). Degrade-safe: no-op when ectx is None or block is empty.
        _steering_file_block = _build_attached_files_block(body.file_contents)
        if _steering_file_block:
            apply_steering(ectx, {"text": _steering_file_block, "sticky": False})
    elif dispatch.channel == CHANNEL_REVISION:
        # revision → mint + drive the shipped family child run (D-02), the exact seam
        # POST /{id}/revisions uses. A generic target derives from the run type when the
        # client omits one (string derivation only — no workflow name-branch).
        target_artifact_type = dispatch.target_artifact_type or f"{wr_type}_output"
        rdb = _get_db()
        try:
            child_run_id, _ = _mint_revision_row(
                rdb, user=current_user, parent_run_id=run_id,
                target_artifact_type=target_artifact_type,
                instruction=dispatch.instruction or "",
            )
        finally:
            rdb.close()
        cancel_event = asyncio.Event()
        _CANCEL_EVENTS[child_run_id] = cancel_event
        event_queue = _get_or_create_queue(child_run_id)
        task = asyncio.create_task(
            _drive_revision_to_queue(
                workflow_run_id=child_run_id,
                parent_run_id=run_id,
                target_artifact_type=target_artifact_type,
                instruction=dispatch.instruction or "",
                user=current_user,
                cancel_event=cancel_event,
                event_queue=event_queue,
            )
        )
        _PIPELINE_TASKS[child_run_id] = task
        return {
            "ok": True, "run_id": run_id, "seq": seq, "persisted": created,
            "channel": dispatch.channel, "revision_run_id": child_run_id,
        }
    elif dispatch.channel == CHANNEL_CONCIERGE:
        # ── Free-form → Concierge (D-04, Phase 33). The router CLASSIFIED this turn as
        #    free-form; the model INVOCATION happens HERE (never in the pure router). ──
        # A.3 (Phase 43): the live in-process ectx handle now resolves via the live-ectx
        # registry (DEF-29-09-1 closed) — a disposed steering_note rides the SAME 29-08 seam
        # as the mechanical steering channel. Degrade-safe: None for a run not live in this
        # process → apply_steering no-ops (the durable row remains the record).
        ectx = _live_ectx_for_run(run_id)

        # A CONFIRM turn carries a previously-HELD proposal to EXECUTE (the FE confirm
        # round-trip, 33-04). H1 (server-enforce the confirm-hold): STOP trusting the
        # client body as the intent. The client ``{channel}`` only LOCATES the durable
        # pending row (``concierge-proposal:{message_id}:{channel}``, owner-scoped read);
        # the intent's ``params`` come EXCLUSIVELY from that DURABLE row, never the body.
        # Missing / cross-owner (default-deny → absent) / already-resolved → 404 (IDOR →
        # 404, never 403). No model call — the answer was already given on the ask turn.
        if body.confirm_proposal:
            from app.agents.chat.concierge import ProposalIntent

            confirm_channel = str(body.confirm_proposal.get("channel", "") or "")
            pending = _load_pending_proposal(
                events, message_id=body.message_id, channel=confirm_channel
            )
            if pending is None:
                # IDOR → 404: never reveal whether the run/proposal exists for another
                # owner, and never resolve a non-pending / replayed proposal.
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Unknown proposal"
                )
            intent = ProposalIntent(
                channel=pending.get("channel") or confirm_channel,
                params=dict(pending.get("params") or {}),  # DURABLE params, not body
            )
            result = await _dispose_concierge_proposal(
                intent, confirmed=True, store=store, art_store=art_store,
                run_id=run_id, message_id=body.message_id, current_user=current_user,
                wr_status=wr_status, wr_type=wr_type, gate_key=resolved_gate_key,
                ectx=ectx, open_gate=open_gate,
                attached_files=_build_attached_files_block(body.file_contents),
            )
            # Mark the durable pending row RESOLVED (additive; namespaced event_id so a
            # replayed confirm is idempotent — the resolved row makes _load_pending_proposal
            # return None next time). owner_id+workspace_id stamped by ScopedStore.
            await store.append_event_next_seq(
                run_id,
                event_id=f"concierge-proposal-resolved:{body.message_id}:{intent.channel}",
                type="concierge_proposal",
                payload_json={
                    "pipeline_run_id": run_id,
                    "message_id": body.message_id,
                    "channel": intent.channel,
                    "params": intent.params,
                    "status": "resolved",
                },
            )
            return {
                "ok": True, "run_id": run_id, "seq": seq, "persisted": created,
                "channel": dispatch.channel, "proposal": result,
            }

        # A fresh free-form turn: invoke the Concierge (owner-scoped) and project its
        # answer to the lane as a chat_reply row (the documented answer-projection type;
        # additive, no new table). The Concierge is proposal-only — any proposal it
        # surfaces is HELD behind a confirm chip (T-33-03-01), never auto-executed.
        concierge = _resolve_concierge()
        # M3: thread the run's compiled workflow onto the ctx so the Concierge injects
        # the manifest ``chat:`` block into its system prompt. Resolve via the existing
        # compile-for-run seam; DATA only (no workflow-name branch, INV-1). Degrade-safe:
        # a missing/malformed manifest → compiled=None (the Concierge getattr-defaults).
        compiled = None
        try:
            from agents.execution_engine.engine import compile_for_run

            compiled = compile_for_run(wr_type)
        except Exception:
            compiled = None
        ctx = _ConciergeCtx(
            run_id=run_id, scoped_store=store,
            owner_id=current_user.id, workspace_id=wr_workspace,
            compiled=compiled,
            # c72: thread the FE-computed chain suggestions onto the ctx as GENERIC
            # data (absent ⇒ []). No workflow-name branch (INV-1) — the Concierge
            # reflects the SAME curated labels the lane chips show.
            chain_hints=body.chain_hints,
            # FIX-116: thread the run's deliverable summary so the Concierge knows
            # what was produced without read_events round-trip (generic, INV-1).
            run_summary=wr_run_summary,
            # FIX-210 (ISS-054): thread the run's current gate state so the Concierge
            # gives an accurate status answer when paused at clarify/review.
            open_gate=open_gate,
            # Thread the run's persisted status so the prompt label is accurate
            # (building run vs completed run — avoids "produced" for in-flight runs).
            run_status=wr_status,
            # FIX-218 (KAN-170): thread pre-extracted file text from chat attachments so
            # the Concierge can answer questions about the file content and propose
            # injection into the running pipeline. Payload-transient (ND-10) — never
            # persisted. Absent ⇒ "" ⇒ dormant (byte-identical prompt, INV-3).
            attached_files=_build_attached_files_block(body.file_contents),
        )
        # FIX-218 (KAN-170): when file contents were attached AND a running pipeline
        # exists (live ectx), also inject the file text as a sticky steering note so
        # the NEXT agent dispatch receives it as a === USER GUIDANCE === block. This
        # mirrors the existing CHANNEL_STEERING apply_steering path (INV-12) — we reuse
        # the SAME seam rather than building a new one. Payload-transient (ND-10).
        # Degrade-safe: if ectx is None (run not live in this process), no-op.
        _attached_block = getattr(ctx, "attached_files", "") or ""
        if _attached_block and ectx is not None:
            apply_steering(ectx, {"text": _attached_block, "sticky": False})
        # ── Option B: STREAM the reply on the POST response body (text/event-stream). ──
        # The model's ordered text deltas ride the POST the FE already makes as TRANSIENT
        # ``chat_reply_chunk`` frames (never persisted → never replayed → never
        # deduped-away; the FE appends them), followed by ONE terminal durable
        # ``chat_reply`` frame carrying the full text + any held proposals. The durable
        # side-effects (the ``chat_reply`` row via ``append_event_next_seq`` + the
        # proposal drain/disposal) run in a BACKGROUND task so they land even if the
        # client drops the streamed body — the response generator only drains the frame
        # queue to the ``None`` sentinel. Nothing is pushed to ``_PIPELINE_QUEUES`` (a
        # settled run stays out of the live-queue lifecycle; BUG-013). ``chat_reply_chunk``
        # is a GENERIC data type — no workflow/agent-name literal (INV-1/SC-001). The
        # model is reached ONLY through the runner inside ``converse`` (INV-13).
        from sse_starlette import EventSourceResponse

        from app.api.run_stream import _sse_frame

        frame_q: asyncio.Queue = asyncio.Queue()

        async def _on_chunk(delta: str) -> None:
            # TRANSIENT chunk frame: seq=0 placeholder (no durable seq), no event_id —
            # the terminal ``chat_reply`` below stays the single canonical record.
            await frame_q.put(_sse_frame(0, "chat_reply_chunk", {
                "pipeline_run_id": run_id,
                "message_id": body.message_id,
                "delta": delta,
            }))

        async def _drive() -> None:
            # ``store`` here is the session-less/owned ScopedStore built above (after
            # db.close()) — each append_event_next_seq opens+closes its own SessionLocal,
            # so this background task reuses store + art_store safely (same idiom as the
            # blocking persist today; the BUG-004 request-session-teardown trap does not
            # apply). ``art_store`` is a module singleton; ectx/current_user/wr_* are
            # captured values.
            answer_text = ""
            reply_seq: int | None = None
            held: list = []
            errored = False
            try:
                answer_text = await concierge.converse(
                    ctx, body.text, on_chunk=_on_chunk
                ) or ""
            except Exception:  # noqa: BLE001 — stream a partial terminal, still persist.
                logger.exception("Concierge stream failed for run %s", run_id)
                errored = True
            try:
                # Durable terminal — persists EXACTLY as today (the single canonical
                # record history/replay/BUG-017/the li0 spinner depend on).
                _created, reply_seq = await store.append_event_next_seq(
                    run_id,
                    event_id=f"chat-reply:{body.message_id}",
                    type="chat_reply",
                    payload_json={
                        "pipeline_run_id": run_id,
                        "message_id": body.message_id,
                        "text": answer_text or "",
                    },
                )
                # ── ISS-092: record the Concierge's OWN model spend, durably. ──────
                # ``converse`` runs here, in a background task spawned AFTER the run
                # settled — outside execute()'s lifetime — so neither the engine's
                # aux_token_usage fold nor _apply_terminal_completion can ever see it.
                # Without this row a chat turn's cost does not exist anywhere.
                #
                # It is a run_events row, NOT a workflow_runs column: token_usage is
                # written solely by _apply_terminal_completion (the documented SOLE
                # writer, already run and never run again) and answers "what does this
                # workflow cost to RUN" — folding a user's chattiness into it would make
                # two runs of the same workflow non-comparable. Reported as a separate
                # line instead.
                #
                # event_id is namespaced on message_id, so append_event_next_seq's
                # idempotency makes a retried/double-submitted POST a no-op rather than
                # a double count. An ABSENT ctx.usage writes NO row: a token that was not
                # observed is reported as unmeasured, never estimated from len(answer).
                # Its own try/except — telemetry must never break the reply.
                try:
                    chat_usage = getattr(ctx, "usage", None)
                    if isinstance(chat_usage, dict):
                        _in = int(chat_usage.get("input_tokens", 0) or 0)
                        _out = int(chat_usage.get("output_tokens", 0) or 0)
                        _cr = int(chat_usage.get("cache_read_tokens", 0) or 0)
                        _cw = int(chat_usage.get("cache_write_tokens", 0) or 0)
                        _model = (
                            chat_usage.get("model_id")
                            or settings.BEDROCK_INFERENCE_PROFILE_ID
                        )
                        await store.append_event_next_seq(
                            run_id,
                            event_id=f"chat-usage:{body.message_id}",
                            type="chat_usage",
                            payload_json={
                                "pipeline_run_id": run_id,
                                "message_id": body.message_id,
                                "model_id": _model,
                                "input_tokens": _in,
                                "output_tokens": _out,
                                "total_tokens": _in + _out,
                                "cache_read_tokens": _cr,
                                "cache_write_tokens": _cw,
                                # Same pricing convention as the run's headline cost
                                # site (:2107): input_tokens is the UNCACHED portion.
                                "estimated_cost_usd": estimate_cost_usd(
                                    _model,
                                    input_tokens=max(0, _in - _cr - _cw),
                                    output_tokens=_out,
                                    cache_read_tokens=_cr,
                                    cache_write_tokens=_cw,
                                    cache_ttl=settings.BEDROCK_PROMPT_CACHE_TTL,
                                ),
                            },
                        )
                except Exception:  # noqa: BLE001 — telemetry never breaks the answer.
                    logger.exception("chat_usage record failed for run %s", run_id)
                # Drain + dispose proposals EXACTLY as today — still HELD behind a confirm
                # chip (T-33-03-01), never auto-executed; only the call-site moved here.
                for intent in _drain_concierge_proposals(concierge, ctx):
                    disposed = await _dispose_concierge_proposal(
                        intent, confirmed=False, store=store, art_store=art_store,
                        run_id=run_id, message_id=body.message_id,
                        current_user=current_user, wr_status=wr_status,
                        wr_type=wr_type, gate_key=resolved_gate_key, ectx=ectx,
                        open_gate=open_gate,
                        attached_files=_attached_block,
                    )
                    held.append(disposed)
                    logger.info(
                        "Concierge proposal disposed: run=%s channel=%s held=%s",
                        run_id,
                        getattr(intent, "channel", "?"),
                        disposed.get("held"),
                    )
            except Exception:  # noqa: BLE001 — never leave the stream hung on a persist error.
                logger.exception("Concierge durable persist failed for run %s", run_id)
                errored = True
            finally:
                # FIX-210 (ISS-054): provide a visible fallback when the Concierge fails
                # to generate a response. An empty text with errored=True was silently
                # rendering as a blank invisible bubble — the user saw no reply at all.
                display_text = answer_text or (
                    "I'm sorry, I couldn't retrieve the run status right now. "
                    "Please try again in a moment."
                    if errored else ""
                )
                # FIX-211: emit each HELD proposal as its own concierge_proposal SSE
                # frame BEFORE the terminal chat_reply, so the FE receives the proposal
                # events through the same streamed-POST drain path (RunConnectionProvider
                # fanout → handleFrame → setProposals). This avoids the fetchEvents
                # timing race where the POST resolves before the background DB writes
                # finish. The durable rows were already written above; these frames are
                # TRANSIENT echoes of those rows carrying the same payload shape the
                # FE's concierge_proposal handleFrame case expects.
                # The event_id MUST match the durable row so the FE seenRef dedup
                # treats the later fetchEvents re-fetch of the same row as a duplicate
                # and drops it — preventing double chips.
                for h in held:
                    h_channel = h.get("channel")
                    if h.get("held") and h_channel:
                        await frame_q.put(_sse_frame(reply_seq or 0, "concierge_proposal", {
                            "pipeline_run_id": run_id,
                            "message_id": body.message_id,
                            "channel": h_channel,
                            "params": h.get("params", {}),
                            "status": "pending",
                            # Match the durable row's event_id so seenRef dedup
                            # drops the fetchEvents re-fetch of the same row.
                            "event_id": f"concierge-proposal:{body.message_id}:{h_channel}",
                        }))
                terminal = {
                    "pipeline_run_id": run_id,
                    # Carry the SAME distinct event_id the durable row uses (:1266) so the
                    # FE keys the reply on `chat-reply:{message_id}` (merging the streamed
                    # bubble) instead of falling back to the bare `message_id` — which
                    # equals the user turn's id and OVERWRITES the user's bubble
                    # (BUG-018 regression on the streamed-POST path).
                    "event_id": f"chat-reply:{body.message_id}",
                    "message_id": body.message_id,
                    "text": display_text,
                    "seq": reply_seq,
                    "proposals": held,
                }
                if errored:
                    terminal["error"] = True
                await frame_q.put(_sse_frame(reply_seq or 0, "chat_reply", terminal))
                await frame_q.put(None)  # sentinel — end of stream

        # CRITICAL correctness pin: run the driver INDEPENDENTLY of client consumption so
        # its durable side-effects (persist + proposal disposal) complete even if the SSE
        # body is dropped mid-stream. Hold a strong reference; NEVER cancel it on
        # generator teardown / client disconnect.
        drive_task = asyncio.create_task(_drive())
        _CONCIERGE_STREAM_TASKS.add(drive_task)
        drive_task.add_done_callback(_CONCIERGE_STREAM_TASKS.discard)

        async def _stream_frames():
            # Drain ONLY — the durable writes are the driver task's job, not the
            # generator's; on client disconnect the generator ends but the task lives on.
            while True:
                frame = await frame_q.get()
                if frame is None:
                    return
                yield frame

        return EventSourceResponse(
            _stream_frames(),
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    return {
        "ok": True, "run_id": run_id, "seq": seq, "persisted": created,
        "channel": dispatch.channel,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/runs — run launch (D-13, replaces the WS `run_pipeline` inbound).
# ═══════════════════════════════════════════════════════════════════════════════
#
# The REST twin of the WS `run_pipeline` handler (`_handle_workflow_execution`).
# It runs the SAME ingress validation (pipeline-type gate, agent allow-list,
# model_overrides, trust=user selections, image caps) BEFORE any run is minted,
# then mints the WorkflowRun and spawns the WS-agnostic background driver onto the
# per-run queue. The SSE down-channel (`GET /api/runs/{id}/events/stream`, 29-02)
# attaches to that same queue and streams the result — so a run can be launched
# entirely over REST while SSE carries the events.
#
# LOCK-B: websocket.py is untouched. The ingress validators + the queue registry
# are read-only imports; the engine-drive loop below is a sanctioned duplication
# of the WS `_run_pipeline_to_queue` closure (the closure is nested + nonlocal-
# coupled, so it is not importable — the de-dup is the deferred follow-up).


class LaunchSource(str, Enum):
    """Which of the three launch shapes a ``POST /api/runs`` request is using.

    Detected once, near the top of ``launch_run``, from ``body.user_workflow_id``
    + the referenced row's ``manifest_json`` shape — see ``_detect_launch_source``.
    Every branch below eventually reconverges at the SAME mint + execute call
    (marked ``# JOIN POINT`` further down) — this enum only decides how
    ``pipeline_type`` / ``agents`` (or, for MANIFEST, a compiled plan) get
    populated before that point, not how the run actually executes.
    """

    # Case 1 — no user_workflow_id at all. A fresh built-in pipeline launch,
    # or an ad-hoc `pipeline_type: "custom"` + agent_ids picked straight from
    # the library with no saved row behind it. UNCHANGED existing behavior.
    FILE_PIPELINE = "file_pipeline"

    # Case 2 — user_workflow_id present, row.manifest_json is null/absent.
    # A saved workflow that's still just a flat list of real, file-backed
    # agents (e.g. "Hello Poet": hello_html + attached_hooks/skills on the
    # row). Composition is still agent_ids-shaped; only the SOURCE of
    # pipeline_type/agent_ids/hooks/skills changes (row, not client body).
    USER_WORKFLOW_FLAT = "user_workflow_flat"

    # Case 3 — user_workflow_id present, row.manifest_json has a "steps" key.
    # A workflow built entirely in the Composer (spec 012) — the manifest
    # tree IS the composition. No file behind base_pipeline_type. The
    # agent_ids allow-list does not apply here (nothing to check it against).
    USER_WORKFLOW_MANIFEST = "user_workflow_manifest"


class LaunchCommand(BaseModel):
    """Body for ``POST /api/runs`` — the full run-launch payload (D-13 / POR §6).

    Mirrors the WS ``run_pipeline`` inbound fields 1:1. ``images`` is the untrusted
    per-run image ingress (cap- + vision-guarded before mint); ``source_workflow_run_id``
    is the (owner-checked) revision/chaining parent link.
    """

    message: str
    pipeline_type: str
    agent_ids: list[str] | None = None
    attached_skills: list[dict] | None = None
    attached_hooks: list[dict] | None = None
    gate_agent_ids: list[str] | None = None
    model_overrides: dict | None = None
    selections: dict | None = None
    template_id: str | None = None
    design_system_id: str | None = None
    custom_ds_body: str | None = None
    custom_template_body: str | None = None
    source_workflow_run_id: str | None = None
    images: list | None = None
    user_workflow_id: str | None = None
    # Composer Run-settings (deliverable/planner/clarify/internet) — the
    # run-time values from the Composer's Workflow-tab rail. Only consumed by
    # the USER_WORKFLOW_MANIFEST branch below, where they take precedence over
    # both the saved row's manifest_json and the hardcoded setdefault fallback,
    # so a user who changes these post-save doesn't have to re-save to have
    # Run once respect the change.
    deliverable: dict | None = None
    planner: str | None = None
    clarify: dict | None = None
    capabilities: dict | None = None


def _reject(code: str, error: str, *, http_status: int = status.HTTP_400_BAD_REQUEST,
            recoverable: bool = False, **extra) -> HTTPException:
    """Shape a rejection identically to the WS error-event ``data`` triple, but as
    an HTTP error (the REST channel's equivalent of ``ws.send_json({"type":"error"})``
    + ``return`` before ``engine.execute`` — never a silent drop)."""
    detail = {"error": error, "code": code, "recoverable": recoverable}
    detail.update(extra)
    return HTTPException(status_code=http_status, detail=detail)


def _resolve_launch_agents(body: "LaunchCommand"):
    """Resolve + validate a launch payload's pipeline + od_context, returning
    ``(base_pipeline_type, od_context)`` or raising the matching HTTPException.

    D-15/C: od_context eligibility now flows through the shared declared-signal
    seam ``resolve_launch_od_context`` (context_providers:[opendesign]) — the old
    od_prototype/od_ppt workflow-name eligibility branch is deleted (SC-001).
    The SUPPORTED_PIPELINE_TYPES gate is preserved.

    Per-boundary parity: the REST launch twin never loaded od_context for the
    ``ppt_revision`` arm (websocket.py loads it NON-FATALLY; the REST path fell
    through to ``None``). That exact behavior is preserved here — REST keeps
    ``ppt_revision`` od_context ``None`` — while prototype/ppt load fatally
    through the seam so a bad template rejects pre-mint (V5).
    """
    from agents.loader import SUPPORTED_PIPELINE_TYPES

    from app.api.launch_context import resolve_launch_od_context

    pipeline_type = body.pipeline_type
    if pipeline_type == "ppt_revision":
        # REST parity: revisions seed from previous_run, not a launch-time template;
        # the REST twin never resolved od_context for this arm (WS owns the
        # non-fatal template load). Preserve od_context=None per boundary.
        base_pipeline_type, od_context = "ppt_revision", None
    else:
        try:
            base_pipeline_type, od_context = resolve_launch_od_context(
                pipeline_type,
                body.template_id,
                body.design_system_id,
                custom_ds_body=body.custom_ds_body,
                custom_template_body=body.custom_template_body,
                fatal=True,
            )
        except LookupError as exc:
            raise _reject("template_not_found", str(exc))

    if base_pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        raise _reject(
            "invalid_pipeline_type",
            f"Unsupported pipeline_type: {pipeline_type!r}",
        )

    return base_pipeline_type, od_context


# ---------------------------------------------------------------------------
# KAN-116 (Bug 3): clean run title helper — strips pipeline context markers
# before storing the title so history / run header / notifications never show
# internal === ... === marker text.
#
# Revision pipelines (ending in _revision) embed the full prior output in the
# content with "=== EXISTING ... ===" markers. The brief / instruction is the
# text AFTER the last "=== REVISION REQUEST ===" marker (or, for the user-stories
# pattern, after "=== REVISION REQUEST ===").
# Chained pipelines embed "=== CONTEXT FROM PREVIOUS PIPELINE ===" at the end
# of enrichedInput; the clean brief is the text BEFORE it.
#
# SC-001 / INV-1: generic marker matching, never a hardcoded pipeline name.
# ---------------------------------------------------------------------------
import re as _re_title

_REVISION_REQUEST_RE = _re_title.compile(
    r"===\s*REVISION REQUEST\s*===\s*(.*?)\s*(?:===|$)", _re_title.DOTALL
)
_CONTEXT_BLOCK_RE = _re_title.compile(
    r"\s*===\s*CONTEXT FROM PREVIOUS PIPELINE.*", _re_title.DOTALL
)
_EXISTING_BLOCK_RE = _re_title.compile(
    r"^===.*?===\s*\n.*?===\s*END.*?===\s*\n?", _re_title.DOTALL
)


def _clean_run_title(content: str | None, pipeline_type: str) -> str:
    """Extract a clean, marker-free title from a run's content string.

    For revision pipelines (type ends in ``_revision``): pull the revision
    instruction from inside the ``=== REVISION REQUEST ===`` block (the text
    after the marker block).
    For all other pipelines: strip any trailing ``=== CONTEXT FROM PREVIOUS
    PIPELINE ===`` block and use the leading brief.
    Falls back to a generic label when no clean text is extractable.
    """
    raw = (content or "").strip()
    if not raw:
        return f"Run {pipeline_type} pipeline"

    title = raw
    if pipeline_type.endswith("_revision"):
        # Try to extract the revision instruction from the structured block.
        m = _REVISION_REQUEST_RE.search(raw)
        if m:
            title = m.group(1).strip()
        else:
            # Fallback: strip leading === ... === blocks to get at the instruction.
            stripped = _EXISTING_BLOCK_RE.sub("", raw).strip()
            title = stripped if stripped else raw
    else:
        # For chained / plain pipelines: remove any appended context block.
        # Use a more targeted pattern that handles the case where the context
        # block is at the very start (no leading brief) — split on the marker.
        context_marker = "=== CONTEXT FROM PREVIOUS PIPELINE"
        if context_marker in raw:
            # Everything before the first context marker is the clean brief.
            title = raw.split(context_marker)[0].strip()
        else:
            title = raw

    # Ensure we never return an empty or whitespace-only title.
    if not title:
        # If the whole content was a context block, extract the Original Brief
        # from inside it (it's always present in the context block header).
        brief_match = _re_title.search(r"Original Brief:\s*(.+)", raw)
        if brief_match:
            title = brief_match.group(1).strip()
        else:
            title = raw
    title = title.split("\n")[0].strip() if title else raw.split("\n")[0].strip()
    # Strip "Title: " prefix if present — can appear when a prior polluted run's
    # title (which itself contained "Title: ...") cascaded into enrichedInput.
    if title.startswith("Title: "):
        title = title[len("Title: "):].strip()
    return (title[:60].strip() or "Untitled")


@router.post("")
async def launch_run(
    body: LaunchCommand,
    current_user: User = Depends(get_current_user),
):
    """Launch a run over REST (mirrors WS ``run_pipeline``).

    Runs the full ingress validation BEFORE minting (bad payload / bad agents /
    bad model_overrides / rejected images all deny with no WorkflowRun and no
    execute), then mints the run + spawns the background driver onto the per-run
    queue and returns ``{run_id}``. The SSE stream (29-02) attaches to that queue.
    """
    from agents.loader import load_agent_spec
    from agents.registry import (
        PIPELINE_AGENTS,
        allowed_custom_agent_ids,
        get_pipeline_agents,
    )
    from app.api.user_workflows import _owned

    # ── Detect which of the 3 launch shapes this request is (see LaunchSource) ─
    launch_source = LaunchSource.FILE_PIPELINE
    user_workflow_row = None
    compiled = None  # set only in the USER_WORKFLOW_MANIFEST branch (TODO #3)
    if body.user_workflow_id is not None:
        # Row is the sole source of truth from here on — any client-sent
        # agent_ids/pipeline_type gets overwritten below (TODO #2/#3), never merged.
        #
        # SNAPSHOT the columns we need while the session is still open, rather than
        # reading them off the ORM instance afterwards: `close()` detaches the
        # instance, and while plain already-loaded columns survive that today, adding
        # a `deferred=True` column or a relationship to WorkflowDefinition would turn
        # every read below into a DetachedInstanceError at run-launch time. A plain
        # namespace of values has no such coupling.
        launch_db = _get_db()
        try:
            _row = _owned(launch_db, body.user_workflow_id, current_user)
            user_workflow_row = SimpleNamespace(
                id=_row.id,
                base_pipeline_type=_row.base_pipeline_type,
                agents=_row.agents,
                manifest_json=_row.manifest_json,
                attached_hooks=_row.attached_hooks,
                attached_skills=_row.attached_skills,
                model_overrides=_row.model_overrides,
            )
        finally:
            launch_db.close()
        if user_workflow_row.manifest_json and "steps" in user_workflow_row.manifest_json:
            launch_source = LaunchSource.USER_WORKFLOW_MANIFEST
        else:
            launch_source = LaunchSource.USER_WORKFLOW_FLAT

    if launch_source is LaunchSource.FILE_PIPELINE:
        # Case 1 — unchanged, nothing to do here.
        pass

    elif launch_source is LaunchSource.USER_WORKFLOW_FLAT:
        # Case 2 — still agent_ids-shaped, just sourced from the row instead
        # of the client body. Falls through into the UNCHANGED allow-list
        # block below, which now reads these overwritten body.* values.
        body.pipeline_type = user_workflow_row.base_pipeline_type
        body.agent_ids = (
            json.loads(user_workflow_row.agents) if user_workflow_row.agents else []
        )
        if user_workflow_row.attached_hooks:
            body.attached_hooks = user_workflow_row.attached_hooks
        if user_workflow_row.attached_skills:
            body.attached_skills = user_workflow_row.attached_skills
        if user_workflow_row.model_overrides:
            body.model_overrides = user_workflow_row.model_overrides

    elif launch_source is LaunchSource.USER_WORKFLOW_MANIFEST:
        # Case 3 — the manifest tree IS the composition; no flat agent_ids
        # list, no allow-list check. Synthesize the top-level fields
        # build_manifest_from_dict requires but a DB-composed manifest_json
        # never carries (its docstring in user_workflows.py._validated_manifest
        # says this is the intended synthesis point), then compile with
        # trust="db" — the compiler's own less-privileged, step-by-step
        # capability checks are the real security boundary for this shape.
        from agents.execution_engine.engine import (
            _CAPABILITY_REGISTRY,
            _WORKFLOW_COMPILER,
        )
        from agents.workflows.manifest import (
            ManifestValidationError,
            build_manifest_from_dict,
        )
        from agents.workflows.compiler import CompilerError

        raw_manifest = dict(user_workflow_row.manifest_json)
        raw_manifest.setdefault("id", f"user-workflow-{user_workflow_row.id}")
        # Request body (this run's live Composer settings) wins over the row's
        # last-saved manifest_json, which in turn wins over the hardcoded
        # fallback — so Run once reflects whatever the Workflow-tab rail shows
        # right now, not a stale save or a silently-hardcoded default.
        raw_manifest["deliverable"] = (
            body.deliverable
            or raw_manifest.get("deliverable")
            or {"strategy": "streamed_text", "name": "output.md"}
        )
        raw_manifest["planner"] = body.planner or raw_manifest.get("planner") or "skip"
        raw_manifest["clarify"] = (
            body.clarify or raw_manifest.get("clarify") or {"mode": "skip", "defaults": []}
        )
        raw_manifest["capabilities"] = (
            body.capabilities or raw_manifest.get("capabilities") or {}
        )

        try:
            parsed_manifest = build_manifest_from_dict(
                raw_manifest, f"workflow:{user_workflow_row.id}"
            )
            compiled = _WORKFLOW_COMPILER.compile(
                parsed_manifest, _CAPABILITY_REGISTRY, trust="db"
            )
        except (ManifestValidationError, CompilerError) as exc:
            raise _reject(
                "invalid_workflow_manifest",
                str(exc),
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        body.pipeline_type = user_workflow_row.base_pipeline_type

    pipeline_type = body.pipeline_type
    content = body.message

    # ── Empty-brief gate (ISS-155) ─────────────────────────────────────────────
    # A run with no brief has nothing to build, and the spend is committed HERE —
    # an od_prototype build is 5–21M Bedrock tokens (measured ceiling 37.3M), so a
    # briefless launch burns the owner's money on nothing. This has to live at the
    # ingress rather than in the wizard: `LaunchCommand.message` is a bare `str`,
    # every client shares this seam (wizard, chain, Concierge, any future API
    # consumer), and a stale `sessionStorage` draft can reach it with no wizard in
    # the loop at all. Deny BEFORE the mint, like every other ingress denial here
    # (no WorkflowRun row, no driver, no spend).
    #
    # Reachable in practice, not theoretical: the chain path waives the brief on
    # the wizard side (`LaunchWizard.canContinue` — `isChaining || brief.trim()`)
    # on the assumption a chain context block stands in for it, and `handleLaunch`
    # falls through to `brief.trim()` — the empty string — whenever that block is
    # absent. A legitimate chained launch is unaffected: when chaining works, the
    # context block IS the message, and it is never blank.
    if not (content or "").strip():
        raise _reject(
            "empty_brief",
            "A run needs a brief. Describe what you want built, or — when chaining — "
            "make sure the source run's context could be loaded.",
        )

    base_pipeline_type, od_context = _resolve_launch_agents(body)

    # ── Entitlement gate (tier) — KAN-161 / ISS-055 ────────────────────────────
    # Use the RAW pipeline_type (not base_pipeline_type): TIER_PIPELINES carries
    # "od_prototype" and "prototype" as DISTINCT keys, and WorkflowRun.type is
    # stamped from pipeline_type too. Checking the alias-collapsed base would
    # silently mis-key the lookup for every od_prototype launch.
    _allowed, _reason = can_run_pipeline(current_user.tier, pipeline_type)
    if not _allowed:
        raise _reject("pipeline_not_entitled", _reason, http_status=status.HTTP_403_FORBIDDEN)

    # ── Resolve + allow-list the agents (invalid_agent_ids) ────────────────────
    # RUNS for: FILE_PIPELINE, USER_WORKFLOW_FLAT (both are agent_ids-shaped —
    # the inner `if agent_ids: / else:` below is UNCHANGED, untouched logic).
    # SKIPPED for: USER_WORKFLOW_MANIFEST — no flat list to check against.
    agent_ids = body.agent_ids
    agents = None
    if launch_source is not LaunchSource.USER_WORKFLOW_MANIFEST:
        if agent_ids:
            allowed_ids = allowed_custom_agent_ids(base_pipeline_type)
            rejected = [aid for aid in agent_ids if aid not in allowed_ids]
            if rejected:
                raise _reject(
                    "invalid_agent_ids",
                    f"Invalid agent_ids for {pipeline_type!r}: {rejected}",
                    rejected_agent_ids=rejected,
                )
            agents = [load_agent_spec(aid) for aid in agent_ids]
            # CWF-001 D1: producer-first pre-sort (defense-in-depth + legacy repair).
            # A custom composition sent/saved consumer-before-producer is reordered to a
            # runnable producer-first order BEFORE the mint; a genuinely-unsatisfiable set
            # (a consumed non-exempt type no selected agent produces, or a real cycle) is
            # rejected pre-mint (no WorkflowRun row). ONLY the custom `agent_ids` branch —
            # file-backed built-in manifests (the `else`) are already producer-first and
            # MUST NOT be re-sorted (scope fence).
            from app.api.composition_order import (
                UnsatisfiableComposition,
                presort_specs,
            )

            try:
                agents = presort_specs(agents)
            except UnsatisfiableComposition as exc:
                raise _reject(
                    "workflow_unsatisfiable",
                    str(exc),
                    http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        else:
            agents = get_pipeline_agents(base_pipeline_type)
            if not agents and base_pipeline_type == "ppt":
                agents = [load_agent_spec(aid) for aid in PIPELINE_AGENTS.get("ppt", [])]
            # Composed workflows (nodes are INSTANCES of an agent template, e.g.
            # "custom-agent:facts") have no AGENT.md on disk, so the registry
            # legitimately returns [] for them. Fall back to the compiled plan —
            # the same single source of roster truth the engine now uses — before
            # rejecting as no_agents.
            if not agents:
                from agents.execution_engine.engine import compile_for_run

                try:
                    _plan = compile_for_run(base_pipeline_type)
                except Exception:
                    _plan = None
                if _plan is not None and _plan.steps:
                    agents = [load_agent_spec(s.agent_id) for s in _plan.steps]
    else:
        # `agents` stays None on purpose — Case 3 has no flat agent list.
        # `compiled` (set above) carries the roster instead; it reaches
        # `_drive_launch_to_queue` via `compiled_override`.
        pass

    if launch_source is not LaunchSource.USER_WORKFLOW_MANIFEST and not agents:
        raise _reject(
            "no_agents",
            f"No agents found for pipeline_type {pipeline_type!r}",
        )

    # ── template-inject ingress guard (F3, 13-06 — re-homed from the deleted WS
    # path in 44-08/DEF-44-08-1) ───────────────────────────────────────────────
    # GENERIC, keyed on the resolved specs' DECLARED injects only (never a
    # pipeline-name allow/deny, SC-001): if any agent declares `template` inject
    # AND this is a template-requiring pipeline (prototype/ppt/od_*) AND no
    # template_body was loaded, reject BEFORE the mint/execute (mirrors the
    # factory raise EXACTLY). A deliberate no-template run (KAN-87) is exempt.
    # od_* runs with a loaded template pass unchanged; custom workflows that
    # merely include a template-injecting agent skip this (factory _compose_injection
    # degrades gracefully when od_context is empty).
    # `agents or []`: Case 3 (USER_WORKFLOW_MANIFEST) leaves `agents` as None —
    # harmless here since its pipeline_type is always "custom", which does not
    # declare `opendesign`, so `_needs_template` is False for it.
    _template_injecting = [
        spec.id for spec in (agents or []) if "template" in (getattr(spec, "injects", None) or [])
    ]
    # The second half of the predicate was a pipeline-name allow-list —
    # ``pipeline_type in ("prototype", "ppt", "od_prototype")`` — which is exactly
    # the SC-001 leak this block's own comment above disclaims, sitting three lines
    # under it. The manifest already declares the thing being tested: a deliverable
    # that needs template/design-system context says so with
    # ``context_providers: [opendesign]``. That is what separates prototype/ppt from
    # a `custom` composition that merely happens to include a template-injecting
    # agent, and it means a new template-driven deliverable is covered by declaring
    # one manifest line instead of editing this tuple.
    from agents.execution_engine.engine import compile_for_run as _compile_for_run

    try:
        _needs_template = "opendesign" in (
            _compile_for_run(base_pipeline_type).context_providers or []
        )
    except FileNotFoundError:
        # No manifest for this id — the SUPPORTED_PIPELINE_TYPES gate above already
        # rejected it, or will; fail closed rather than demand a template.
        _needs_template = False
    if (
        _template_injecting
        and _needs_template
        and not (od_context or {}).get("template_body")
        and not (od_context or {}).get("no_template")
    ):
        raise _reject(
            "missing_template_context",
            f"Pipeline {pipeline_type!r} agents {_template_injecting} declare template "
            "injection, so the run requires a template (template_id) — no template "
            "body could be loaded.",
        )

    # ── model_overrides ingress validation (D-07, MODEL-03) ────────────────────
    # SKIPPED for Case 3 (USER_WORKFLOW_MANIFEST): both checks below are
    # agent_ids-specific re-validations against a flat roster. Case 3's
    # manifest already went through the compiler's own trust="db" step-by-step
    # checks (TODO #3) — a stricter, per-step equivalent, not a gap.
    model_overrides = body.model_overrides or {}
    if launch_source is not LaunchSource.USER_WORKFLOW_MANIFEST:
        _override_error = _validate_model_overrides(
            model_overrides, {spec.id for spec in agents}
        )
        if _override_error is not None:
            raise _reject("invalid_model_override", _override_error)

        # ── EMP-02 launch-side trust=user re-validation of persisted selections ─
        _selection_error = _revalidate_selections_trust_user(
            base_pipeline_type, [spec.id for spec in agents], body.selections
        )
        if _selection_error is not None:
            raise _reject("invalid_selection", _selection_error)

    # ── image-input ingress gate (IMAGE-INPUT §3 Layer 1/5) ────────────────────
    # Identical caps to the WS path: mime allow-list, ~3.75MB/image, ≤20, ~8MB
    # aggregate, vision-model guard. Flag OFF / no images → [] (byte-identical,
    # images ignored not rejected). A cap/vision violation denies pre-mint.
    images = body.images or []
    validated_images: list = []
    if settings.IMAGE_INPUT_ENABLED and images:
        base_model = (
            getattr(current_user, "preferred_model", None)
            or settings.BEDROCK_INFERENCE_PROFILE_ID
        )
        effective_model_ids = {base_model} | {
            m for m in model_overrides.values() if isinstance(m, str)
        }
        _image_error = _validate_images(images, effective_model_ids=effective_model_ids)
        if _image_error is not None:
            raise _reject("invalid_image_input", _image_error)
        validated_images = images

    # ── Mint the WorkflowRun (mirror websocket.py:1912-1966) ───────────────────
    # ═══ JOIN POINT ═════════════════════════════════════════════════════════
    # All 3 LaunchSource branches reconverge HERE.
    # `compiled` is only non-None for Case 3 (set in the USER_WORKFLOW_MANIFEST
    # branch, TODO #3) — CompiledWorkflow.steps is already FLAT (the compiler
    # flattens the tree; parent/child is encoded per-step via `dispatched_by`,
    # not nesting), so counting it needs no recursion.
    agent_count = len(compiled.steps) if compiled is not None else len(agents)
    pipeline_run_id = str(_uuid.uuid4())
    cancel_event = asyncio.Event()
    _CANCEL_EVENTS[pipeline_run_id] = cancel_event
    workflow_run_id = None
    db = _get_db()
    try:
        # KAN-116 (Bug 2): only set parent_run_id for REVISION pipelines (type ends in
        # "_revision"). Chained pipelines (different base type) must NOT inherit parent_run_id
        # — that would place them in the source workflow's revision family (BFS in
        # _owned_family_members has no type filter). A chain is NOT a revision; chained runs
        # should appear as SEPARATE entries in history, never as vN of the source family.
        # SC-001/INV-1: generic endswith check, never a hardcoded pipeline name.
        parent_run_id = (
            _resolve_owned_parent_run_id(db, body.source_workflow_run_id, current_user.id)
            if pipeline_type.endswith("_revision")
            else None
        )
        workflow_run = WorkflowRun(
            id=pipeline_run_id,
            user_id=current_user.id,
            title=_clean_run_title(content, pipeline_type),
            type=pipeline_type,
            status="running",
            input=content or f"Run {pipeline_type} pipeline",
            agent_count=agent_count,
            session_id=current_user.id,
            parent_run_id=parent_run_id,
            selections_json=body.selections,
            # KAN-120: persist the launch-time od_context so resume_run can
            # reconstruct it without a template_id round-trip (the template
            # body is large; re-loading from disk at resume is the alternative
            # but requires storing template_id separately). od_context is None
            # for non-OD runs → od_context_json stays NULL (INV-3 parity).
            od_context_json=od_context,
            # Persist the per-run gate selection (migration 0031) for the same
            # reason as the two above: resume_run rebuilds the context from this
            # row. Without it a gate that exists only via this override vanishes
            # on restart and a pending redo is silently dropped. None (the
            # "use static AGENT.md gates" default) stays NULL.
            gate_agent_ids_json=body.gate_agent_ids,
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)
        workflow_run_id = workflow_run.id
    finally:
        db.close()

    # ── Spawn the WS-agnostic background driver onto the per-run queue ─────────
    event_queue = _get_or_create_queue(pipeline_run_id)
    task = asyncio.create_task(
        _drive_launch_to_queue(
            workflow_run_id=workflow_run_id,
            pipeline_run_id=pipeline_run_id,
            agents=agents,
            content=content,
            pipeline_type=pipeline_type,
            cancel_event=cancel_event,
            user=current_user,
            attached_skills=body.attached_skills or [],
            attached_hooks=body.attached_hooks or [],
            compiled_override=compiled,
            od_context=od_context,
            validated_images=validated_images,
            gate_agent_ids=body.gate_agent_ids,
            parent_run_id=parent_run_id,
            model_overrides=model_overrides,
            selections=body.selections,
            event_queue=event_queue,
        )
    )
    _PIPELINE_TASKS[pipeline_run_id] = task

    return {"run_id": pipeline_run_id}


def _apply_terminal_output_columns(
    wr: WorkflowRun,
    events: "list[tuple[str, dict]]",
    *,
    model_id: str | None,
    duration_seconds: float | None,
) -> None:
    """The SINGLE event→``WorkflowRun`` output-column mapping (BUG-R03, INV-12).

    Replays a normalized ``(event_type, data)`` list — the SAME ``agent_*`` /
    ``pipeline_complete`` accumulation the launch loop ran inline (this file, the old
    1599-1675) — into the terminal ``output`` / ``agent_outputs`` / ``token_usage`` /
    ``deliverable_mimetype`` / ``deliverable_filename`` / ``completed_at`` / ``duration``
    columns, byte-for-byte identical to ``_drive_launch_to_queue``'s post-stream block
    (the old 1704-1742). It writes NO ``status`` / ``error`` — those stay caller-owned
    (launch's seen-flags, user-resume's ``_reconcile_terminal_status``, the engine state
    machine on restart). It does NOT commit — the caller owns the session.

    This is the SOLE writer of these columns for the launch path, the two resume entry
    points (restart auto-resume via the engine ``_resume_output_persist_sink`` hook,
    user-resume via ``_reconcile_terminal_status``), AND the revision driver
    (``_drive_revision_to_queue``, ISS-152 — the fourth caller BUG-R03 missed), so a
    revision or resume-completion row matches a never-restarted launch completion.
    Workflow-agnostic (SC-001 — no workflow/agent name).
    """
    agent_outputs_collector: list[dict] = []
    current_agent: dict = {}
    final_output = ""
    deliverable_mimetype: str | None = None
    deliverable_filename: str | None = None
    for utype, data in events:
        if not isinstance(data, dict):
            data = {}
        if utype == "agent_start":
            current_agent = {
                "agent_id": data.get("agent_id"),
                "name": data.get("name"),
                "role": data.get("role"),
                "icon": data.get("icon"),
                "output": "", "duration": None,
                "input_prompt": None, "context_sources": [],
                "tool_calls": [], "thinking_text": "",
            }
        elif utype == "agent_input":
            current_agent["input_prompt"] = data.get("context_message")
            current_agent["context_sources"] = data.get("context_sources", [])
        elif utype == "agent_thinking":
            current_agent["thinking_text"] = (current_agent.get("thinking_text") or "") + data.get("thinking", "")
        elif utype == "tool_call":
            current_agent.setdefault("tool_calls", []).append({
                "tool": data.get("tool"),
                "args": data.get("args", {}),
                "result": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif utype == "tool_result":
            # FIFO, not LIFO. The tool_call event carries no call id, so the only
            # thing to pair on is the tool NAME — and results come back in call
            # order. Walking newest-first handed result #1 to the LAST outstanding
            # call and shifted every result after it by one, so any step with two
            # same-named calls (a composed agent reading three artifacts) recorded
            # a wrong audit trail. Matching oldest-unresolved-first is correct for
            # in-order results and no worse than LIFO for out-of-order ones.
            for tc in current_agent.get("tool_calls", []):
                if tc.get("tool") == data.get("tool") and tc.get("result") is None:
                    tc["result"] = data.get("result")
                    break
        elif utype == "agent_chunk":
            current_agent["output"] = current_agent.get("output", "") + data.get("chunk", "")
        elif utype == "agent_complete":
            current_agent["duration"] = data.get("duration")
            current_agent["input_tokens"] = data.get("input_tokens", 0)
            current_agent["output_tokens"] = data.get("output_tokens", 0)
            current_agent["total_tokens"] = data.get("total_tokens", 0)
            current_agent["cache_read_tokens"] = data.get("cache_read_tokens", 0)
            current_agent["cache_write_tokens"] = data.get("cache_write_tokens", 0)
            if current_agent.get("agent_id"):
                agent_outputs_collector.append(current_agent)
            current_agent = {}
        elif utype == "agent_error":
            current_agent["error"] = data.get("error")
            if current_agent.get("agent_id"):
                agent_outputs_collector.append(current_agent)
            current_agent = {}
        elif utype == "pipeline_complete":
            final_output = data.get("final_output", "")
            deliverable_mimetype = data.get("deliverable_mimetype")
            deliverable_filename = data.get("deliverable_filename")
    if final_output:
        wr.output = final_output
    if deliverable_mimetype is not None:
        wr.deliverable_mimetype = deliverable_mimetype
    if deliverable_filename is not None:
        wr.deliverable_filename = deliverable_filename
    if agent_outputs_collector:
        wr.agent_outputs = json.dumps(agent_outputs_collector)
    # CWF-002 (fix b): record the run's EFFECTIVE model BEFORE the cost computation so the
    # estimate_cost_usd line reads the real model instead of the BEDROCK default fallback.
    wr.model_id = model_id
    total_input = sum(a.get("input_tokens", 0) or 0 for a in agent_outputs_collector)
    total_output = sum(a.get("output_tokens", 0) or 0 for a in agent_outputs_collector)
    total_cache_read = sum(a.get("cache_read_tokens", 0) or 0 for a in agent_outputs_collector)
    total_cache_write = sum(a.get("cache_write_tokens", 0) or 0 for a in agent_outputs_collector)
    if total_input + total_output > 0:
        wr.token_usage = json.dumps({
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cache_read_tokens": total_cache_read,
            "total_cache_write_tokens": total_cache_write,
            "estimated_cost_usd": estimate_cost_usd(
                wr.model_id or settings.BEDROCK_INFERENCE_PROFILE_ID,
                input_tokens=max(0, total_input - total_cache_read - total_cache_write),
                output_tokens=total_output,
                cache_read_tokens=total_cache_read,
                cache_write_tokens=total_cache_write,
                cache_ttl=settings.BEDROCK_PROMPT_CACHE_TTL,
            ),
            # ISS-034: the as-if-UNCACHED counterfactual on the SAME token base, so
            # Analytics can report the SIGNED effect of prompt caching. Rows written
            # before this key existed simply lack it — every reader is a tolerant
            # json.loads and the Analytics fold treats an absent key as a ZERO delta
            # (never a fabricated $0 baseline), so no migration is needed.
            "estimated_cost_full_usd": estimate_cost_usd(
                wr.model_id or settings.BEDROCK_INFERENCE_PROFILE_ID,
                input_tokens=total_input,
                output_tokens=total_output,
            ),
        })
    if not wr.completed_at:
        wr.completed_at = datetime.now(timezone.utc)
    if duration_seconds is not None and not wr.duration:
        wr.duration = duration_seconds


def _resume_events_duration(events) -> "float | None":
    """Best-effort total agent execution time for a resumed run — the sum of the durable
    ``agent_complete`` durations (the launch path's wall-clock ``monotonic`` is unavailable
    off a durable tail). ``None`` when no agent reported a duration (→ the helper leaves
    ``wr.duration`` untouched)."""
    total = 0.0
    seen = False
    for e in events:
        if getattr(e, "type", None) != "agent_complete":
            continue
        payload = getattr(e, "payload_json", None)
        d = payload.get("duration") if isinstance(payload, dict) else None
        if d is None:
            continue
        try:
            total += float(d)
            seen = True
        except (TypeError, ValueError):
            pass
    return round(total, 1) if seen else None


def _persist_resume_output_columns(run_id: str, events) -> None:
    """Persist a RESUMED run's terminal output columns from its durable ``run_events`` tail
    via the SHARED ``_apply_terminal_output_columns`` mapping (BUG-R03, INV-12) — so the
    resume-completion row carries ``output`` / ``agent_outputs`` / ``token_usage`` /
    ``duration`` / ``deliverable_*`` exactly like a never-restarted completion. Writes NO
    ``status`` (the caller's status tier owns it). Best-effort: a schemaless / offline
    session degrades without perturbing the drive (INV-3)."""
    normalized = [
        (
            getattr(e, "type", "") or "",
            e.payload_json if isinstance(getattr(e, "payload_json", None), dict) else {},
        )
        for e in events
    ]
    duration_seconds = _resume_events_duration(events)
    sdb = _get_db()
    try:
        wr = sdb.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if wr:
            _apply_terminal_output_columns(
                wr, normalized, model_id=wr.model_id, duration_seconds=duration_seconds
            )
            sdb.commit()
    finally:
        sdb.close()


async def persist_resume_output_columns(run_id: str) -> None:
    """Read a resumed run's OWNER-SCOPED durable ``run_events`` tail and persist its terminal
    output columns (BUG-R03). This is the app-layer callback ARMED onto the engine as
    ``_resume_output_persist_sink`` (app/main.py) and fired from ``_drive_resumed_stream``'s
    ``finally`` for the RESTART auto-resume path (branch b) — the engine cannot import
    ``app.*`` so the tail read + mapping live here (ports-and-adapters, MIRRORING the injected
    ``_resume_milestone_sink`` / live-ectx trio). Reuses the SAME owner/workspace tail-read
    idiom as ``_reconcile_terminal_status``. Best-effort: a read/resolve error degrades to a
    no-op (INV-3)."""
    from agents.authz import ScopedStore

    db = _get_db()
    try:
        wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if wr is None:
            return
        owner_id = wr.owner_id or wr.user_id or f"anon:{wr.session_id or run_id}"
    finally:
        db.close()

    try:
        from agents.execution_engine.engine import get_execution_engine

        engine = get_execution_engine()
        workspace_id = await engine._recover_workspace_id(owner_id, run_id)
        store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
        events = await store.read_events(run_id, after_seq=0)
    except Exception as exc:  # noqa: BLE001 — best-effort tail read (offline degrade)
        logger.warning("persist_resume_output_columns(%s) tail read failed: %s", run_id, exc)
        return

    _persist_resume_output_columns(run_id, events)


async def _drive_launch_to_queue(
    *,
    workflow_run_id: str | None,
    pipeline_run_id: str,
    agents: list,
    content: str,
    pipeline_type: str,
    cancel_event: asyncio.Event,
    user: User,
    attached_skills: list,
    attached_hooks: list,
    od_context: dict | None,
    validated_images: list,
    gate_agent_ids: list | None,
    parent_run_id: str | None,
    model_overrides: dict,
    selections: dict | None,
    event_queue: asyncio.Queue,
    compiled_override: "CompiledWorkflow | None" = None,
) -> None:
    """Run the engine and push every event into the per-run queue. Never touches a
    socket — the SSE stream drains the same queue (and the engine's durable
    run_events sink persists independently). A sanctioned duplication of the WS
    ``_run_pipeline_to_queue`` closure body (websocket.py:2025-2279)."""
    from agents.execution_engine.engine import get_execution_engine

    engine = get_execution_engine()
    # A.4 (Phase 43, DEF-43-03-1): the app-layer narrator projector, injected into the engine as
    # milestone_sink below (the kernel never imports app.* — import-linter). Local import keeps
    # module load clean and mirrors the file's other lazy-import pattern.
    from app.agents.chat_narrator import persist_milestone_card
    # BUG-R03: capture every engine event as a normalized ``(type, data)`` tuple for the
    # SHARED terminal-column mapping (_apply_terminal_output_columns) — the SOLE
    # event→WorkflowRun output-column accumulation, now reused by the two resume entry
    # points (INV-12, no inline duplicate). The status seen-flags below stay inline (the
    # status decision is caller-owned, not part of the output-column mapping).
    raw_events: list[tuple[str, dict]] = []
    any_agent_errored = False
    first_agent_error_msg: str | None = None
    pipeline_complete_seen = False
    degraded_failed_agents: list | None = None
    pipeline_cancelled_seen = False
    # CWF-001 D2: track the generic ``error`` event + ``pipeline_failed`` so a run that
    # died at runtime is never persisted "completed". Mirrors the LOCK-B revision twin
    # _drive_revision_to_queue (Phase 29) — the two drivers stay behaviorally identical.
    pipeline_error_seen = False
    pipeline_failed_seen = False
    pipeline_error_msg: str | None = None
    monotonic_start = time.monotonic()

    try:
        async for update in engine.execute(
            agents=agents,
            user_message=content,
            pipeline_run_id=pipeline_run_id,
            pipeline_type=pipeline_type,
            cancel_event=cancel_event,
            user_id=user.id,
            session_id=user.id,
            attached_skills=attached_skills,
            attached_hooks=attached_hooks,
            model_id=getattr(user, "preferred_model", None) or None,
            od_context=od_context,
            images=validated_images,
            compiled_override=compiled_override,
            gate_agent_ids=gate_agent_ids,
            parent_run_id=parent_run_id,
            model_overrides=model_overrides,
            selections=selections,
            event_queue=event_queue,
            # A.3 (Phase 43): register this run's live in-process ExecutionContext so a
            # mid-run chat steering note / per-turn image posted to POST /messages resolves
            # via _live_ectx_for_run and drains onto the NEXT agent dispatch. This SSE/REST
            # launch path is the seam that goes LIVE at the Part-C transport cutover; the WS
            # run_pipeline launch (websocket.py, LOCK-B — not modified here) wires the same
            # pair at Part C. unregister runs in the engine wrapper's finally — no leak.
            live_ectx_register=register_live_ectx,
            live_ectx_unregister=unregister_live_ectx,
            # A.4 (Phase 43, DEF-43-03-1): wire the narrator LIVE on the SSE/REST launch path —
            # the engine projects a chat_reply milestone card per generic lifecycle event, draws
            # its seq from the engine's own contiguous allocator (no durable-log gap), and yields
            # it into this loop → event_queue → SSE. Self-filtering + best-effort (a card never
            # perturbs the deterministic stream). The WS run_pipeline launch stays dormant (LOCK-B,
            # deleted at 43-09). `persist_milestone_card` lives in the app layer (no kernel import).
            milestone_sink=persist_milestone_card,
        ):
            await event_queue.put({"type": update["type"], "data": update.get("data", {})})
            utype = update["type"]
            # BUG-R03: record the raw event for the shared terminal-column mapping (the SOLE
            # agent_*/pipeline_complete accumulation now lives in
            # _apply_terminal_output_columns — no inline duplicate; INV-12). The status
            # seen-flags below stay inline (status is caller-owned, not a mapped column).
            raw_events.append((utype, update.get("data", {})))
            if utype == "agent_error":
                any_agent_errored = True
                if first_agent_error_msg is None:
                    first_agent_error_msg = update["data"].get("error") or "Agent execution error"
            elif utype == "pipeline_complete":
                pipeline_complete_seen = True
                if update["data"].get("status") == "degraded":
                    degraded_failed_agents = list(update["data"].get("agents_failed", []))
            elif utype == "pipeline_cancelled":
                pipeline_cancelled_seen = True
            elif utype == "error":
                pipeline_error_seen = True
                if pipeline_error_msg is None:
                    pipeline_error_msg = (
                        update["data"].get("error")
                        or update["data"].get("code")
                        or "Pipeline error"
                    )
            elif utype == "pipeline_failed":
                pipeline_failed_seen = True
                if pipeline_error_msg is None:
                    pipeline_error_msg = update["data"].get("error") or "Pipeline failed"

        if workflow_run_id:
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    if pipeline_cancelled_seen:
                        wr.status = "cancelled"
                        if not wr.completed_at:
                            wr.completed_at = datetime.now(timezone.utc)
                    elif degraded_failed_agents is not None:
                        wr.status = "degraded"
                        wr.error = first_agent_error_msg or (
                            "degraded: agent(s) failed: " + ", ".join(degraded_failed_agents)
                        )
                    elif (
                        pipeline_complete_seen
                        and not pipeline_error_seen
                        and not pipeline_failed_seen
                    ):
                        wr.status = "completed"
                    else:
                        # CWF-001 D2 fail-safe: any generic ``error`` / ``pipeline_failed`` /
                        # agent_error-without-clean-terminal (or a stream that ended with no
                        # clean pipeline_complete) → "failed". Reaches "completed" ONLY on a
                        # clean terminal. Mirrors _drive_revision_to_queue's else → "failed".
                        wr.status = "failed"
                        wr.error = first_agent_error_msg or pipeline_error_msg
                    # BUG-R03: the output columns (output/deliverable_*/agent_outputs/
                    # model_id/token_usage/completed_at/duration) are now written by the
                    # SHARED _apply_terminal_output_columns mapping — the SOLE event→column
                    # accumulation, reused byte-for-byte by the two resume entry points
                    # (INV-12). The status decision above stays inline (caller-owned).
                    _apply_terminal_output_columns(
                        wr,
                        raw_events,
                        model_id=getattr(user, "preferred_model", None) or None,
                        duration_seconds=round(time.monotonic() - monotonic_start, 1),
                    )
                    db.commit()
            finally:
                db.close()
    except asyncio.CancelledError:
        await event_queue.put({"type": "pipeline_cancelled", "data": {"message": "Pipeline cancelled"}})
        # ISS-124: make the terminal DURABLE, not queue-only. This branch is the
        # ``stop_run_driver`` escalation path (``task.cancel()`` for a driver that could
        # not observe the cooperative event in bounded time), and it wrote no ``run_events``
        # row at all — so (a) the run's durable log ended on whatever came before, which is
        # how ISS-126's dangling ``review_gate_ready`` reopens are still being MINTED, and
        # (b) ``stop_run_driver`` then runs ``_reconcile_terminal_status``, which decides
        # from the durable tail alone and took its D2 fail-safe → the owner's Stop was
        # recorded as ``failed``, overwriting the ``cancelled`` written just below.
        # The frame above is already emitted unconditionally; this only makes the row agree
        # with it. Best-effort by construction (the helper swallows its own failures), so a
        # cancelled driver can never be made worse by the audit write.
        if workflow_run_id:
            await _record_cancellation_in_the_durable_tail(
                workflow_run_id, reason="driver_task_cancelled"
            )
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    wr.status = "cancelled"
                    wr.completed_at = datetime.now(timezone.utc)
                    db.commit()
            finally:
                db.close()
    except Exception as e:  # pragma: no cover - defensive parity with WS driver
        logger.error("REST launch driver error — run=%s: %s", workflow_run_id, e, exc_info=True)
        await event_queue.put({"type": "error", "data": {
            "error": f"Pipeline execution failed: {e}",
            "code": "pipeline_error", "recoverable": True,
        }})
        if workflow_run_id:
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    wr.status = "failed"
                    wr.error = str(e)
                    wr.completed_at = datetime.now(timezone.utc)
                    db.commit()
            finally:
                db.close()
    finally:
        await event_queue.put(None)
        _cleanup_pipeline(pipeline_run_id)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/runs/{id}/revisions — child-run dispatch (D-13, replaces WS run_revision).
# ═══════════════════════════════════════════════════════════════════════════════
#
# The REST twin of the WS `run_revision` handler (`_handle_revision_execution`).
# It mints a FAMILY CHILD WorkflowRun (parent_run_id + owner_id) of type
# `<base>_revision` and dispatches the shipped revision sub-pipeline via
# `engine._handle_revision`, pushing events to the per-run queue. This is D-02's
# family "revision run" — NOT the intra-run KAN-101 spec-revision loop.
#
# Ownership: unlike the WS path (which drops a foreign parent LINK but still
# dispatches), the REST endpoint denies a cross-owner / missing parent outright
# with 404 (IDOR → 404, never 403 — the ported parent-link ownership contract).


class RevisionCommand(BaseModel):
    """Body for ``POST /api/runs/{id}/revisions`` — a child revision run."""

    target_artifact_type: str
    instruction: str


def _mint_revision_row(db, *, user: User, parent_run_id: str,
                       target_artifact_type: str, instruction: str) -> tuple[str, str]:
    """Mint the child revision WorkflowRun (mirror websocket.py:2475-2524) and return
    ``(run_id, revision_pipeline_type)``. ``agent_count`` derives from the LIVE
    registry membership of the derived revision alias (Pitfall 6 — never a
    hardcoded 1)."""
    from agents.registry import get_pipeline_agents

    pipeline_run_id = str(_uuid.uuid4())
    revision_pipeline_type = f"{target_artifact_type.removesuffix('_output')}_revision"

    # ── Existence gate — BEFORE the entitlement gate, and that order matters ───
    # Some pipelines have no revision implementation at all: `dotnet_to_azure` and
    # `mulesoft_to_springboot` are launchable and produce a deliverable, but neither
    # has a *_revision manifest, agents, or a tier entry. Reaching the entitlement
    # gate first meant the user was told "This pipeline is not available on your
    # current plan" — on enterprise, where UPGRADE_PATH is None and so no upgrade is
    # even offered. The plan was never the problem and no plan change could fix it.
    #
    # Answer the question that is actually true first: the feature does not exist.
    # A 400 (not 403) because this is not an authorization outcome.
    #
    # The predicate is ``get_pipeline_agents`` — the SAME one the engine uses for its
    # own pre-dispatch guard (engine.py, "No revision pipeline is registered"). Using
    # the registry rather than a directory probe keeps one definition of "this
    # pipeline exists" and moves the engine's check earlier, before the row is minted.
    _rev_agents = get_pipeline_agents(revision_pipeline_type)
    if not _rev_agents:
        raise _reject(
            "revision_unsupported",
            f"Revisions aren't available for this workflow yet — {revision_pipeline_type!r} "
            f"has no pipeline behind it. Launch a new run instead.",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Entitlement gate (tier) — KAN-161 / ISS-055 ────────────────────────────
    # Single insertion covers all 3 production call sites (create_revision,
    # CHANNEL_REVISION in post_message, Concierge "revision" disposal). Fails fast
    # BEFORE any registry lookup or DB row is minted, matching the fail-fast
    # pattern in user_workflows.py. user.tier is available — the full User object
    # is threaded to every caller already.
    _rev_allowed, _rev_reason = can_run_pipeline(user.tier, revision_pipeline_type)
    if not _rev_allowed:
        raise _reject("pipeline_not_entitled", _rev_reason, http_status=status.HTTP_403_FORBIDDEN)

    # Inherit workspace_id from the parent run (required — run_events.workspace_id
    # is NOT NULL; a revision row without it fails on the first event write).
    parent_wr = db.query(WorkflowRun).filter(WorkflowRun.id == parent_run_id).first()
    parent_workspace_id = getattr(parent_wr, "workspace_id", None) if parent_wr else None
    wr = WorkflowRun(
        id=pipeline_run_id,
        user_id=user.id,
        owner_id=user.id,
        workspace_id=parent_workspace_id,
        parent_run_id=parent_run_id,
        title=f"Revision: {instruction[:50]}",
        type=revision_pipeline_type,
        status="revising",
        input=instruction,
        agent_count=len(_rev_agents) or 1,
    )
    db.add(wr)
    db.commit()
    return pipeline_run_id, revision_pipeline_type


@router.post("/{run_id}/revisions")
async def create_revision(
    run_id: str,
    body: RevisionCommand,
    current_user: User = Depends(get_current_user),
):
    """Dispatch a child revision run over REST (mirrors WS ``run_revision``).

    Owner-gated on the PARENT (T-29-04-1): a cross-owner / unknown parent denies
    with 404 (IDOR → 404, never a run-existence oracle). On success mints the
    child run (parent_run_id + owner_id) and spawns the WS-agnostic revision
    driver onto the per-run queue; the SSE stream (29-02) attaches.
    """
    # Parent-link ownership: resolve the parent by id AND owner (user_id) — a
    # missing or cross-owner parent is indistinguishable (both 404).
    db = _get_db()
    try:
        parent = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == current_user.id)
            .first()
        )
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run"
            )
        child_run_id, _ = _mint_revision_row(
            db,
            user=current_user,
            parent_run_id=run_id,
            target_artifact_type=body.target_artifact_type,
            instruction=body.instruction,
        )
    finally:
        db.close()

    cancel_event = asyncio.Event()
    _CANCEL_EVENTS[child_run_id] = cancel_event
    event_queue = _get_or_create_queue(child_run_id)
    task = asyncio.create_task(
        _drive_revision_to_queue(
            workflow_run_id=child_run_id,
            parent_run_id=run_id,
            target_artifact_type=body.target_artifact_type,
            instruction=body.instruction,
            user=current_user,
            cancel_event=cancel_event,
            event_queue=event_queue,
        )
    )
    _PIPELINE_TASKS[child_run_id] = task

    return {"run_id": child_run_id}


async def _drive_revision_to_queue(
    *,
    workflow_run_id: str,
    parent_run_id: str,
    target_artifact_type: str,
    instruction: str,
    user: User,
    cancel_event: asyncio.Event,
    event_queue: asyncio.Queue,
) -> None:
    """Run the revision engine and push every event into the per-run queue, owning
    the terminal-status persistence on ``workflow_run_id`` (never left "revising").
    A sanctioned duplication of the WS ``_run_revision_to_queue`` closure body
    (websocket.py:2543-2650), minus the socket drainer."""
    from agents.execution_engine.engine import get_execution_engine
    # A.4 (Phase 43, DEF-43-03-1): inject the narrator so chat_reply milestone
    # cards are persisted for revision runs (FIX-171) — same pattern as the
    # _run_workflow_to_queue fresh-run path. The kernel never imports app.*.
    from app.agents.chat_narrator import persist_milestone_card

    pipeline_complete_seen = False
    pipeline_failed_seen = False
    degraded_seen = False
    pipeline_cancelled_seen = False
    # ISS-152: this driver is a fourth caller of the shared
    # _apply_terminal_output_columns mapping (BUG-R03, INV-12) — mirrors the launch
    # driver's raw_events/monotonic_start (this file, _drive_launch_to_queue) so a
    # revision completion carries output/agent_outputs/token_usage/duration/model_id/
    # deliverable_* exactly like a launch or resume completion, never silently NULL.
    raw_events: list[tuple[str, dict]] = []
    monotonic_start = time.monotonic()

    async def _queue_send(event: dict) -> None:
        nonlocal pipeline_complete_seen, pipeline_failed_seen, degraded_seen
        nonlocal pipeline_cancelled_seen
        etype = event.get("type")
        raw_events.append((etype or "", event.get("data") or {}))
        if etype == "pipeline_cancelled":
            pipeline_cancelled_seen = True
        if etype == "pipeline_complete":
            pipeline_complete_seen = True
            if event.get("data", {}).get("status") == "degraded":
                degraded_seen = True
        elif etype == "pipeline_failed":
            pipeline_failed_seen = True
        await event_queue.put(event)

    def _persist_terminal_status(new_status: str) -> None:
        sdb = _get_db()
        try:
            swr = sdb.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if swr:
                swr.status = new_status
                swr.completed_at = datetime.now(timezone.utc)
                # ISS-152: the SOLE event→column mapping (_apply_terminal_output_columns),
                # reused byte-for-byte from the launch driver — the driver's OWN monotonic
                # clock, never pipeline_complete's total_duration (keeps ISS-150's two
                # disagreeing duration numbers from getting a third).
                _apply_terminal_output_columns(
                    swr,
                    raw_events,
                    model_id=getattr(user, "preferred_model", None) or None,
                    duration_seconds=round(time.monotonic() - monotonic_start, 1),
                )
                sdb.commit()
        finally:
            sdb.close()

    try:
        await get_execution_engine()._handle_revision(
            parent_run_id=parent_run_id,
            target_artifact_type=target_artifact_type,
            instruction=instruction,
            pipeline_run_id=workflow_run_id,
            websocket_send_fn=_queue_send,
            model_id=getattr(user, "preferred_model", None) or None,
            owner_id=user.id,
            cancel_event=cancel_event,
            # FIX-171: wire the narrator so pipeline_start ("Revision started")
            # and pipeline_complete ("Delivered") cards are persisted for revision
            # runs — the same milestone_sink pattern _run_workflow_to_queue uses.
            milestone_sink=persist_milestone_card,
        )
        _persist_terminal_status(
            "cancelled"
            if pipeline_cancelled_seen
            else "degraded"
            if degraded_seen
            else "completed"
            if (pipeline_complete_seen and not pipeline_failed_seen)
            else "failed"
        )
    except ValueError as exc:
        await event_queue.put({
            "type": "error",
            "data": {"error": str(exc), "code": "revision_validation_error",
                     "recoverable": False},
        })
        _persist_terminal_status("failed")
    except asyncio.CancelledError:
        await event_queue.put({
            "type": "pipeline_cancelled",
            "data": {"message": "Revision cancelled"},
        })
        # ISS-124 (second locus) — identical hole, identical fix. See the launch driver's
        # CancelledError branch for the full rationale; the two drivers stay behaviorally
        # identical by design (LOCK-B).
        await _record_cancellation_in_the_durable_tail(
            workflow_run_id, reason="driver_task_cancelled"
        )
        _persist_terminal_status("cancelled")
    except Exception as exc:
        logger.error("REST revision driver failed: %s", exc, exc_info=True)
        await event_queue.put({
            "type": "error",
            "data": {"error": f"Revision failed: {exc}",
                     "code": "revision_error", "recoverable": True},
        })
        _persist_terminal_status("failed")
    finally:
        await event_queue.put(None)
        _cleanup_pipeline(workflow_run_id)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/runs/user_message — legacy free-chat POST+stream shim (ND-3).
# ═══════════════════════════════════════════════════════════════════════════════
#
# The legacy WS ``user_message`` free-chat path ported to a POST+SSE shim: it
# persists the Message rows and drives ``ChatRunner`` exactly as the WS handler
# does (websocket.py:1478-1616), streaming ChatRunner's own
# ``phase_start/stream/phase_end/error/complete`` vocabulary back over SSE. The
# ``chat`` agents, ``ChatRunner``, and the frozen ``test_chat_contract.py`` golden
# are UNTOUCHED (landmine / POR §7 / ND-3) — the shim only wraps the sequencer.


class UserMessageCommand(BaseModel):
    """Body for ``POST /api/runs/user_message`` — a legacy free-chat turn."""

    content: str
    chat_session_id: str
    mode: str = "default"


@router.post("/user_message")
async def user_message_shim(
    body: UserMessageCommand,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Drive the legacy free-chat ``ChatRunner`` over POST+stream (mirrors WS
    ``user_message``).

    Owner-gated: the chat session must belong to the caller (→ 404 on cross-owner
    / unknown). Persists the user Message, then returns an SSE stream that drives
    ``ChatRunner.astream_execute`` (its native ``{type, chunk, section, data}``
    frames) and persists the assistant Message at the end. ChatRunner is unchanged.
    """
    content = body.content
    chat_session_id = body.chat_session_id

    if not content or not chat_session_id:
        raise _reject(
            "invalid_message",
            "Expected {content: string, chat_session_id: string}",
        )

    # Owner-gated chat-session resolution (cross-owner / unknown → 404).
    db = _get_db()
    try:
        chat_session = (
            db.query(ChatSession)
            .filter(
                ChatSession.id == chat_session_id,
                ChatSession.user_id == current_user.id,
            )
            .first()
        )
        if chat_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found"
            )
        db.add(Message(chat_session_id=chat_session_id, role="user", content=content))
        chat_session.last_activity = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    mode_prompt = get_mode_prompt(body.mode)

    async def _event_source():
        assistant_chunks: list[str] = []
        last_msg: dict | None = None
        runner = ChatRunner(user_id=current_user.id, run_id=chat_session_id)
        try:
            async for stream_msg in runner.astream_execute(
                user_message=content,
                chat_session_id=chat_session_id,
                mode=body.mode,
                mode_prompt=mode_prompt,
            ):
                if stream_msg.get("type") == "stream" and stream_msg.get("chunk"):
                    assistant_chunks.append(stream_msg["chunk"])
                last_msg = stream_msg
                # SSE frame body: the ChatRunner event verbatim (byte-for-byte the
                # same {type, chunk, section, data} the WS handler forwarded).
                yield {"data": json.dumps(stream_msg, ensure_ascii=False)}
        finally:
            # Persist the assistant response + final output (mirror websocket.py:1585).
            pdb = _get_db()
            try:
                assistant_content = "".join(assistant_chunks)
                if assistant_content:
                    pdb.add(Message(
                        chat_session_id=chat_session_id,
                        role="assistant",
                        content=assistant_content,
                    ))
                cs = (
                    pdb.query(ChatSession)
                    .filter(ChatSession.id == chat_session_id)
                    .first()
                )
                if cs:
                    cs.last_activity = datetime.now(timezone.utc)
                    if last_msg and last_msg.get("type") == "complete" and last_msg.get("data"):
                        cs.final_output = json.dumps(last_msg["data"])
                    pdb.commit()
            finally:
                pdb.close()

    from sse_starlette import EventSourceResponse

    return EventSourceResponse(
        _event_source(),
        ping=settings.SSE_KEEPALIVE_PING_SECONDS,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )

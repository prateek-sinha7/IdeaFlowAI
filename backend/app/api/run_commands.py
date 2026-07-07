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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agents.artifact_store.store import get_artifact_store
from app.core.dependencies import get_current_user
from app.models.user import User

# READ-ONLY import of the EXISTING /ws/chat seams (LOCK-B — websocket.py is NOT
# modified and no symbol is added to it). These are the same predicates + the
# same cooperative-cancel registry the WS inbound handlers use, so the REST and
# WS command paths cannot diverge.
from app.api.websocket import (
    _CANCEL_EVENTS,
    _review_gate_owned_by,
    _review_gate_run_is_terminal,
)

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
    action: str = "approve"
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
    """
    event = store._resume_events.get(f"review:{gate_key}")
    return event is not None and not event.is_set()


def _deny_unknown_gate() -> HTTPException:
    """Non-revealing IDOR denial (T-29-03-1): an unknown run and an unowned run
    are indistinguishable to the caller — both 404 "Unknown gate_key"."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Unknown gate_key"
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
        analysis_report = body.analysis_report or ""
        await store.set_review_response(
            gate_key, approved=False, action="update_specs", instructions=analysis_report
        )
    elif action == "reject":
        await store.set_review_response(
            gate_key, approved=False, edited_content=body.edited_content
        )
    else:  # approve (default)
        approved = True if body.approved is None else bool(body.approved)
        await store.set_review_response(
            gate_key, approved=approved, edited_content=body.edited_content
        )

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


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Cooperatively cancel a run over HTTP (mirrors WS ``cancel_pipeline``).

    Owner-gated (T-29-03-3) → 404 on cross-owner. Sets the per-run cooperative
    ``asyncio.Event`` in ``_CANCEL_EVENTS`` (ISS-007) — the engine observes it
    (per-chunk / pre-agent) and emits ``pipeline_cancelled`` through the normal
    persisted+drained path; suspend/persist semantics are unchanged. When no live
    event exists the ack is idempotent (nothing to cancel).
    """
    if not _review_gate_owned_by(run_id, current_user.id):
        raise _deny_unknown_gate()

    event: asyncio.Event | None = _CANCEL_EVENTS.get(run_id)
    if event is not None:
        event.set()
        return {"ok": True, "run_id": run_id, "cancelled": True}
    # Idempotent: nothing active to cancel, but ack so the client returns to idle.
    return {"ok": True, "run_id": run_id, "cancelled": False, "message": "No active pipeline"}

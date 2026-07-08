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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from agents.artifact_store.store import get_artifact_store
from agents.capabilities.model_pricing import estimate_cost_usd
from app.agents.chat_runner import ChatRunner
from app.agents.modes import get_mode_prompt
from app.core.config import settings
from app.core.dependencies import get_current_user
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
from app.api.websocket import (
    _CANCEL_EVENTS,
    _PIPELINE_TASKS,
    _cleanup_pipeline,
    _get_db,
    _get_or_create_queue,
    _resolve_owned_parent_run_id,
    _review_gate_owned_by,
    _review_gate_run_is_terminal,
    _revalidate_selections_trust_user,
    _validate_images,
    _validate_model_overrides,
)

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
    # confirm_proposal: the FE confirm round-trip (33-04). A concierge turn carrying a
    # previously-HELD consequential proposal to EXECUTE: {"channel": ..., "params": {...}}
    # reconstructed from the durable ``concierge_proposal`` row. Present ⇒ the held intent
    # is disposed CONFIRMED through its Phase-29 seam; absent ⇒ a fresh free-form ask.
    confirm_proposal: dict | None = None
    # images: per-turn image attachments (UPLD-02 residue, 30-03) — untrusted base64
    # {mime_type, data} entries cap-validated by the SHARED ``_validate_images`` ingress
    # caps (the exact caps the launch path uses) BEFORE queueing; a violation → 400.
    # PAYLOAD-TRANSIENT (ND-10/LOCK-E): threaded onto the live run's next dispatch via
    # ``apply_turn_images``, never persisted (the chat_message row keeps retained:false
    # refs, no bytes). Default None ⇒ dormant (no image flow → run_images unchanged).
    images: list | None = None


def _live_ectx_for_run(run_id: str):
    """Best-effort resolve the LIVE in-process ``ExecutionContext`` for ``run_id``.

    The per-turn image carrier (30-03) delivers cap-validated images onto the running
    run's ``ectx.pending_turn_images`` via ``chat_router.apply_turn_images``. That
    requires the live in-process context handle — the SAME deferred wiring the 29-08
    steering seam needs (DEF-29-09-1: engine-side drain / run_events re-derivation).
    No live-ectx registry exists yet, so this returns ``None`` today — ``apply_turn_images``
    then no-ops (the durable ``chat_message`` row keeps the record; images are
    payload-transient, ND-10). The seam + engine drain are proven offline
    (test_run_message_images); the live handle lands with the DEF-29-09-1 follow-up.
    """
    return None


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
    # ND-10: attachments are payload-transient — persist a placeholder ref (kind + a
    # "not retained" marker), NEVER the bytes (no sandbox/DB retention; the image does
    # not survive replay/reopen).
    attachment_refs = [
        {"kind": (a.get("kind") or a.get("type") or "attachment"), "retained": False}
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
_CONSEQUENTIAL_PROPOSAL_CHANNELS = frozenset({"gate_action", "revision"})


class _ConciergeCtx:
    """The minimal owner-scoped ctx handed to ``ConciergeCapability.converse``.

    Carries only what the Concierge reads: the ``run_id``, the owner+workspace
    ``ScopedStore`` (its ONLY read surface), and ``model=None`` (Haiku default via the
    sanctioned runner). ``conversation_context``/``compiled`` are absent ⇒ the Concierge
    degrades gracefully (``getattr`` defaults). No workflow name is ever passed (INV-1).
    """

    def __init__(self, *, run_id, scoped_store, owner_id, workspace_id):
        self.run_id = run_id
        self.scoped_store = scoped_store
        self.owner_id = owner_id
        self.workspace_id = workspace_id
        self.model = None


def _resolve_concierge():
    """Resolve the shared ``chat:concierge`` capability impl (static registry lookup).

    A pure ``(kind, name)`` dict lookup — no workflow-name branch (SC-001/INV-1). Isolated
    in a helper so the offline test can monkeypatch it with a scripted fake (no live
    model call); production returns the registered ``ConciergeCapability`` (Haiku)."""
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    return CapabilityRegistry().resolve("chat", "concierge")


def _drain_concierge_proposals(concierge) -> list:
    """Return the ProposalIntents the Concierge surfaced this invocation (else []).

    Duck-typed forward seam: a concierge exposing ``drain_proposals()`` returns its
    staged intents. The 33-02 ``converse`` returns only its answer text (proposals ride
    the model's tool-results); LIVE surfacing of those tool-results is Phase-34
    live-deferred (DEF), so this yields [] against the current impl — the disposal +
    confirm-chip contract itself is proven offline via the confirm round-trip below."""
    drain = getattr(concierge, "drain_proposals", None)
    if callable(drain):
        return list(drain() or [])
    return []


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
    if channel == "steering_note":
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
        return {"channel": channel, "held": True}

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
        raw_action = params.get("action", "approve")
        action = _CONCIERGE_GATE_ACTION_MAP.get(raw_action, raw_action)
        rationale = params.get("rationale") or None
        if action == "redo":
            await art_store.set_review_response(
                gate_key, approved=False, action="redo", instructions=rationale
            )
        elif action == "update_specs":
            await art_store.set_review_response(
                gate_key, approved=False, action="update_specs",
                instructions=rationale or "",
            )
        elif action == "reject":
            await art_store.set_review_response(gate_key, approved=False)
        else:  # approve (default)
            await art_store.set_review_response(gate_key, approved=True)
        return {"channel": channel, "disposed": "gate", "action": action}

    # ── revision → _mint_revision_row + _drive_revision_to_queue (family child). ────
    if channel == "revision":
        target = params.get("target") or f"{wr_type}_output"
        instruction = params.get("instruction", "")
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
            await art_store.set_review_response(
                _gk, approved=False, action="update_specs",
                instructions=dispatch.instructions or "",
            )
        elif dispatch.action == "reject":
            await art_store.set_review_response(_gk, approved=False)
        else:  # approve (default)
            await art_store.set_review_response(_gk, approved=True)
    elif dispatch.channel == CHANNEL_STEERING:
        # 29-08 seam: the note is queued for the NEXT agent dispatch (ND-11 — base
        # thread, next dispatch, no fork). The durable chat_message row above IS the
        # record; the running engine re-derives pending steering from run_events (ND-9)
        # and the injector consumes it via apply_steering into ectx.steering_notes. The
        # live in-process ectx handle lookup (engine-side drain) is out of this plan's
        # LOCK-B allow-list — proven at the seam by test_mechanical_router.apply_steering.
        #
        # 30-03: a RUNNING-turn's cap-validated per-turn images ride the SAME
        # live-delivery seam — apply_turn_images enqueues them onto
        # ectx.pending_turn_images and the engine drains them onto the one-shot
        # ectx.turn_images_once carrier at the next dispatch (payload-transient, ND-10;
        # rendered once, then cleared). The live in-process ectx handle is the
        # DEF-29-09-1 deferred wiring (no live-ectx registry yet), so this is best-effort
        # (a no-op until the handle lands); the seam + drain are proven offline by
        # test_run_message_images. Keyed on the generic queue only (SC-001/INV-1).
        if validated_turn_images:
            apply_turn_images(_live_ectx_for_run(run_id), validated_turn_images)
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
        # Best-effort live in-process ectx handle (None today — DEF-29-09-1): a disposed
        # steering_note rides the SAME 29-08 seam as the mechanical steering channel.
        ectx = _live_ectx_for_run(run_id)

        # A CONFIRM turn carries a previously-HELD proposal to EXECUTE (the FE confirm
        # round-trip, 33-04): reconstruct the intent and dispose it CONFIRMED through its
        # Phase-29 seam. No model call — the answer was already given on the ask turn.
        if body.confirm_proposal:
            from app.agents.chat.concierge import ProposalIntent

            intent = ProposalIntent(
                channel=body.confirm_proposal.get("channel", ""),
                params=dict(body.confirm_proposal.get("params", {}) or {}),
            )
            result = await _dispose_concierge_proposal(
                intent, confirmed=True, store=store, art_store=art_store,
                run_id=run_id, message_id=body.message_id, current_user=current_user,
                wr_status=wr_status, wr_type=wr_type, gate_key=resolved_gate_key,
                ectx=ectx,
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
        ctx = _ConciergeCtx(
            run_id=run_id, scoped_store=store,
            owner_id=current_user.id, workspace_id=wr_workspace,
        )
        answer = await concierge.converse(ctx, body.text)
        await store.append_event_next_seq(
            run_id,
            event_id=f"chat-reply:{body.message_id}",
            type="chat_reply",
            payload_json={
                "pipeline_run_id": run_id,
                "message_id": body.message_id,
                "text": answer or "",
            },
        )
        held: list = []
        for intent in _drain_concierge_proposals(concierge):
            held.append(await _dispose_concierge_proposal(
                intent, confirmed=False, store=store, art_store=art_store,
                run_id=run_id, message_id=body.message_id, current_user=current_user,
                wr_status=wr_status, wr_type=wr_type, gate_key=resolved_gate_key,
                ectx=ectx,
            ))
        return {
            "ok": True, "run_id": run_id, "seq": seq, "persisted": created,
            "channel": dispatch.channel, "reply": True, "proposals": held,
        }

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

    Ported from ``_handle_workflow_execution`` (websocket.py:1712-1762): the od_*
    alias resolution + od_context load and the SUPPORTED_PIPELINE_TYPES gate. The
    agent allow-list + the remaining ingress guards live in ``launch_run``.
    """
    from agents.execution_engine.od_context import (
        load_ppt_od_context,
        load_prototype_od_context,
    )
    from agents.loader import SUPPORTED_PIPELINE_TYPES

    pipeline_type = body.pipeline_type
    od_context: dict | None = None
    base_pipeline_type = pipeline_type
    if pipeline_type == "od_prototype":
        base_pipeline_type = "prototype"
        try:
            od_context = load_prototype_od_context(
                body.template_id or "", body.design_system_id or "",
                custom_ds_body=body.custom_ds_body,
                custom_template_body=body.custom_template_body,
            )
        except LookupError as exc:
            raise _reject("template_not_found", str(exc))
    elif pipeline_type == "od_ppt":
        base_pipeline_type = "od_ppt"
        try:
            od_context = load_ppt_od_context(
                body.template_id or "", body.design_system_id,
                custom_ds_body=body.custom_ds_body,
                custom_template_body=body.custom_template_body,
            )
        except LookupError as exc:
            raise _reject("template_not_found", str(exc))

    if base_pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        raise _reject(
            "invalid_pipeline_type",
            f"Unsupported pipeline_type: {pipeline_type!r}",
        )

    return base_pipeline_type, od_context


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

    pipeline_type = body.pipeline_type
    content = body.message

    base_pipeline_type, od_context = _resolve_launch_agents(body)

    # ── Resolve + allow-list the agents (invalid_agent_ids) ────────────────────
    agent_ids = body.agent_ids
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
    else:
        agents = get_pipeline_agents(base_pipeline_type)
        if not agents and base_pipeline_type == "ppt":
            agents = [load_agent_spec(aid) for aid in PIPELINE_AGENTS.get("ppt", [])]

    if not agents:
        raise _reject(
            "no_agents",
            f"No agents found for pipeline_type {pipeline_type!r}",
        )

    # ── model_overrides ingress validation (D-07, MODEL-03) ────────────────────
    model_overrides = body.model_overrides or {}
    _override_error = _validate_model_overrides(
        model_overrides, {spec.id for spec in agents}
    )
    if _override_error is not None:
        raise _reject("invalid_model_override", _override_error)

    # ── EMP-02 launch-side trust=user re-validation of persisted selections ────
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
    pipeline_run_id = str(_uuid.uuid4())
    cancel_event = asyncio.Event()
    _CANCEL_EVENTS[pipeline_run_id] = cancel_event
    workflow_run_id = None
    db = _get_db()
    try:
        parent_run_id = _resolve_owned_parent_run_id(
            db, body.source_workflow_run_id, current_user.id
        )
        workflow_run = WorkflowRun(
            id=pipeline_run_id,
            user_id=current_user.id,
            title=(content or f"Run {pipeline_type} pipeline")[:60].strip() or "Untitled",
            type=pipeline_type,
            status="running",
            input=content or f"Run {pipeline_type} pipeline",
            agent_count=len(agents),
            session_id=current_user.id,
            parent_run_id=parent_run_id,
            selections_json=body.selections,
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
) -> None:
    """Run the engine and push every event into the per-run queue. Never touches a
    socket — the SSE stream drains the same queue (and the engine's durable
    run_events sink persists independently). A sanctioned duplication of the WS
    ``_run_pipeline_to_queue`` closure body (websocket.py:2025-2279)."""
    from agents.execution_engine.engine import get_execution_engine

    engine = get_execution_engine()
    final_output = ""
    agent_outputs_collector: list[dict] = []
    current_agent: dict = {}
    any_agent_errored = False
    first_agent_error_msg: str | None = None
    pipeline_complete_seen = False
    degraded_failed_agents: list | None = None
    pipeline_cancelled_seen = False
    deliverable_mimetype: str | None = None
    deliverable_filename: str | None = None
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
            gate_agent_ids=gate_agent_ids,
            parent_run_id=parent_run_id,
            model_overrides=model_overrides,
            selections=selections,
            event_queue=event_queue,
        ):
            await event_queue.put({"type": update["type"], "data": update.get("data", {})})
            utype = update["type"]
            if utype == "agent_start":
                current_agent = {
                    "agent_id": update["data"].get("agent_id"),
                    "name": update["data"].get("name"),
                    "role": update["data"].get("role"),
                    "icon": update["data"].get("icon"),
                    "output": "", "duration": None,
                    # CR-02: the four scaffold keys the WS driver seeds so the
                    # agent_input/thinking/tool_call/tool_result branches below have a
                    # place to write. Missing keys made the persisted history drop
                    # tool-call/thinking/input-prompt data for every REST-launched run.
                    "input_prompt": None, "context_sources": [],
                    "tool_calls": [], "thinking_text": "",
                }
            # CR-02: ported verbatim from websocket.py::_run_pipeline_to_queue
            # (2079-2095) so the REST launch path persists the SAME agent_outputs
            # history as the WS path (sanctioned-duplication behavioral parity — the
            # live event queue already forwarded these unconditionally above; only the
            # PERSISTED WorkflowRun.agent_outputs blob was degraded).
            elif utype == "agent_input":
                current_agent["input_prompt"] = update["data"].get("context_message")
                current_agent["context_sources"] = update["data"].get("context_sources", [])
            elif utype == "agent_thinking":
                current_agent["thinking_text"] = (current_agent.get("thinking_text") or "") + update["data"].get("thinking", "")
            elif utype == "tool_call":
                current_agent.setdefault("tool_calls", []).append({
                    "tool": update["data"].get("tool"),
                    "args": update["data"].get("args", {}),
                    "result": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            elif utype == "tool_result":
                for tc in reversed(current_agent.get("tool_calls", [])):
                    if tc.get("tool") == update["data"].get("tool") and tc.get("result") is None:
                        tc["result"] = update["data"].get("result")
                        break
            elif utype == "agent_chunk":
                current_agent["output"] = current_agent.get("output", "") + update["data"].get("chunk", "")
            elif utype == "agent_complete":
                current_agent["duration"] = update["data"].get("duration")
                current_agent["input_tokens"] = update["data"].get("input_tokens", 0)
                current_agent["output_tokens"] = update["data"].get("output_tokens", 0)
                current_agent["total_tokens"] = update["data"].get("total_tokens", 0)
                current_agent["cache_read_tokens"] = update["data"].get("cache_read_tokens", 0)
                current_agent["cache_write_tokens"] = update["data"].get("cache_write_tokens", 0)
                if current_agent.get("agent_id"):
                    agent_outputs_collector.append(current_agent)
                current_agent = {}
            elif utype == "agent_error":
                any_agent_errored = True
                if first_agent_error_msg is None:
                    first_agent_error_msg = update["data"].get("error") or "Agent execution error"
                current_agent["error"] = update["data"].get("error")
                if current_agent.get("agent_id"):
                    agent_outputs_collector.append(current_agent)
                current_agent = {}
            elif utype == "pipeline_complete":
                final_output = update["data"].get("final_output", "")
                pipeline_complete_seen = True
                deliverable_mimetype = update["data"].get("deliverable_mimetype")
                deliverable_filename = update["data"].get("deliverable_filename")
                if update["data"].get("status") == "degraded":
                    degraded_failed_agents = list(update["data"].get("agents_failed", []))
            elif utype == "pipeline_cancelled":
                pipeline_cancelled_seen = True

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
                    elif pipeline_complete_seen:
                        wr.status = "completed"
                    else:
                        wr.status = "failed" if any_agent_errored else "completed"
                        if any_agent_errored:
                            wr.error = first_agent_error_msg
                    if final_output:
                        wr.output = final_output
                    if deliverable_mimetype is not None:
                        wr.deliverable_mimetype = deliverable_mimetype
                    if deliverable_filename is not None:
                        wr.deliverable_filename = deliverable_filename
                    if agent_outputs_collector:
                        wr.agent_outputs = json.dumps(agent_outputs_collector)
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
                        })
                    if not wr.completed_at:
                        wr.completed_at = datetime.now(timezone.utc)
                    if not wr.duration:
                        wr.duration = round(time.monotonic() - monotonic_start, 1)
                    db.commit()
            finally:
                db.close()
    except asyncio.CancelledError:
        await event_queue.put({"type": "pipeline_cancelled", "data": {"message": "Pipeline cancelled"}})
        if workflow_run_id:
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
    _rev_agents = get_pipeline_agents(revision_pipeline_type)
    wr = WorkflowRun(
        id=pipeline_run_id,
        user_id=user.id,
        owner_id=user.id,
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

    pipeline_complete_seen = False
    pipeline_failed_seen = False
    degraded_seen = False
    pipeline_cancelled_seen = False

    async def _queue_send(event: dict) -> None:
        nonlocal pipeline_complete_seen, pipeline_failed_seen, degraded_seen
        nonlocal pipeline_cancelled_seen
        etype = event.get("type")
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

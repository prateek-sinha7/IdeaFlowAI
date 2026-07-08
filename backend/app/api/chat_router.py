"""app/api/chat_router.py — CHAT-01/CHAT-02/CHAT-05 / D-04: the mechanical intent router.

The chat backbone's **mechanical** intent router (D-04): given a run's GENERIC live
state and one up-channel chat turn, it decides — with **zero model calls** — which
command channel the turn is delivered on, then the ``/messages`` endpoint dispatches it
through the SAME command seams the 29-03/29-04 endpoints wrap (gate / answers /
revisions) and the 29-08 steering seam (``ectx.steering_notes``).

**Name-freedom (SC-001 / INV-1):** this router keys ONLY on the generic run-state
signals from the Live-State Contract (LIVE-STATE-CONTRACT.md §1) — the durable event
vocabulary (``questionnaire_ready`` / ``review_gate_ready``), the KAN-94 event-driven
armed-gate ground truth, and the persisted run status. It NEVER branches on a workflow
name / ``pipeline_type`` / ``spec.id``. It lives in the APP layer, not the kernel, so
the banned-pattern gate over ``agents/execution_engine/`` stays green.

**The four routable branches** (LIVE-STATE-CONTRACT.md §1 + §2a):

  * **clarify_waiting** (an open ``questionnaire_ready``) → the turn is a **clarify
    answer** — delivered on the ``POST /answers`` seam (``store.set_questionnaire_responses``).
  * **gate_paused** (an armed, still-open ``review_gate_ready``, KAN-94) → the turn is a
    **gate action** — approve / reject / redo / update_specs — delivered on the
    ``POST /gate`` seam (``store.set_review_response``). ``update_specs`` routes to the
    shipped KAN-101 spec-revision loop (never rebuilt).
  * **running** (an agent is live, no open gate) → the turn is a **steering note**,
    appended to ``ectx.steering_notes`` (the 29-08 consume-once seam; applied at the
    NEXT dispatch — honest: no mid-generation injection).
  * **terminal** (``completed`` / ``degraded`` / ``failed`` / ``cancelled``) → the turn
    is a **revision** — delivered on the ``POST /revisions`` seam (a family child run,
    D-02). A GATE ACTION arriving after terminal is **fenced** with
    ``pipeline_not_running`` (KAN-100), never resolving a stopped pipeline.

Free-form / ambiguous turns that do not map to one of these mechanical branches are left
for the Concierge escalation (Phase 33) — out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Generic run-state phases (NOT workflow names — SC-001/INV-1) ─────────────
# The four mechanical routing phases derived from the Live-State Contract §1.
PHASE_CLARIFY_WAITING = "clarify_waiting"
PHASE_GATE_PAUSED = "gate_paused"
PHASE_RUNNING = "running"
PHASE_TERMINAL = "terminal"

# The command channels a turn can be dispatched on (the 29-03/29-04 seams + 29-08).
CHANNEL_ANSWERS = "answers"        # POST /answers  → store.set_questionnaire_responses
CHANNEL_GATE = "gate"             # POST /gate     → store.set_review_response
CHANNEL_STEERING = "steering"     # ectx.steering_notes append (29-08 seam)
CHANNEL_REVISION = "revision"     # POST /revisions → family child run (D-02)

# The FOUR gate actions (D-04 / POR §6). Generic discriminators — no workflow name.
GATE_ACTIONS = frozenset({"approve", "reject", "redo", "update_specs"})

# Terminal run statuses (KAN-100 fence). Generic status vocabulary, NOT pipeline names.
TERMINAL_STATUSES = frozenset({"completed", "degraded", "failed", "cancelled"})

# ── Durable gate event vocabulary (LIVE-STATE-CONTRACT.md §1) ────────────────
# These are GENERIC engine event types (the documented run-chat/gate vocabulary),
# never a workflow name. A gate "opens" on its *_ready event and "closes" when a
# resolution event for it (or any terminal) follows in the durable log.
_QUESTIONNAIRE_READY = "questionnaire_ready"
_REVIEW_GATE_READY = "review_gate_ready"

# Events that close an OPEN questionnaire (clarify) gate.
_QUESTIONNAIRE_RESOLUTIONS = frozenset(
    {
        "questionnaire_complete",
        "pipeline_start",
        "pipeline_complete",
        "pipeline_cancelled",
        "pipeline_failed",
        "error",
    }
)

# Events that close an OPEN review gate (mirrors run_stream._GATE_RESOLUTION_TYPES).
_REVIEW_RESOLUTIONS = frozenset(
    {
        "review_gate_approved",
        "pipeline_complete",
        "pipeline_cancelled",
        "pipeline_failed",
        "budget_aborted",
        "error",
    }
)


@dataclass
class RunState:
    """The GENERIC live-state descriptor the router keys on (SC-001/INV-1).

    Assembled by the ``/messages`` endpoint from generic signals ONLY:
      * ``status``    — the persisted ``WorkflowRun.status``.
      * ``open_gate`` — ``"questionnaire"`` / ``"review"`` / ``None`` derived from the
        durable ``run_events`` (the last still-open ``*_ready`` gate) AND confirmed
        armed for a review gate (KAN-94 event-driven ground truth). A declared gate the
        engine skipped (``gate_agent_ids`` exclusion) is never marked open.
      * ``gate_key``  — the ``{run_id}:{agent_id}`` of the open review gate (from its
        durable ``review_gate_ready`` payload), or ``None``.

    No field is a workflow name / ``pipeline_type`` / ``spec.id``.
    """

    status: str
    open_gate: str | None = None
    gate_key: str | None = None

    @property
    def phase(self) -> str:
        """Map the generic signals onto one of the four mechanical routing phases.

        Precedence: an OPEN gate (clarify or review) wins over the raw status (a paused
        run's status is the generic ``waiting_for_user``, so the driving *signal* — the
        open gate — is what distinguishes clarify from gate); then a terminal status;
        else the run is running.
        """
        if self.open_gate == "questionnaire":
            return PHASE_CLARIFY_WAITING
        if self.open_gate == "review":
            return PHASE_GATE_PAUSED
        if self.status in TERMINAL_STATUSES:
            return PHASE_TERMINAL
        return PHASE_RUNNING


@dataclass
class ChatTurn:
    """One up-channel chat turn — the generic payload the router decides on.

    ``action`` is the optional gate-action discriminator (approve/reject/redo/
    update_specs); ``sticky`` marks an uploaded-context steering note that persists
    across dispatches (D-06). Everything else is free-form user content.
    """

    text: str = ""
    message_id: str | None = None
    action: str | None = None
    sticky: bool = False
    responses: list[dict] = field(default_factory=list)
    skip_clarification: bool = False
    analysis_report: str | None = None
    target_artifact_type: str | None = None
    # images: per-turn image attachments (UPLD-02 residue, 30-03) — cap-validated
    # {mime_type, data(base64)} entries the /messages endpoint threads onto the live
    # run's next dispatch via ``apply_turn_images``. Default-empty ⇒ dormant (no image
    # flow → run_images unchanged → INV-3 byte-parity).
    images: list = field(default_factory=list)


@dataclass
class Dispatch:
    """The router's decision: which channel + the per-channel parameters.

    ``fenced`` + ``code`` mark a KAN-100 terminal-fence refusal (a gate action after
    terminal): the endpoint returns ``pipeline_not_running`` and performs NO write.
    """

    channel: str
    # gate channel
    action: str | None = None
    gate_key: str | None = None
    instructions: str | None = None
    # answers channel
    responses: list[dict] = field(default_factory=list)
    skip_clarification: bool = False
    # steering channel
    note: dict | None = None
    # revision channel
    instruction: str | None = None
    target_artifact_type: str | None = None
    # KAN-100 terminal fence
    fenced: bool = False
    code: str | None = None


# ---------------------------------------------------------------------------
# Open-gate derivation — pure, generic, read-only over the durable run_events.
# ---------------------------------------------------------------------------
def derive_open_gate(events: list) -> tuple[str | None, str | None]:
    """Return ``(open_gate_kind, gate_key)`` for the run's last STILL-OPEN gate.

    Scans the durable ``run_events`` (ascending ``seq``) tracking the last unresolved
    ``questionnaire_ready`` / ``review_gate_ready``. A gate is open iff its ``*_ready``
    is not followed by a matching resolution (or any terminal). Keyed on the GENERIC
    event vocabulary only (LIVE-STATE-CONTRACT.md §1) — never a workflow name.

    ``events`` rows may be ORM ``RunEvent`` objects or plain dicts (``{type, seq,
    payload_json}``) — both are read via ``getattr``/``get``.
    """
    def _type(r: Any) -> str:
        return getattr(r, "type", None) if not isinstance(r, dict) else r.get("type")

    def _seq(r: Any) -> int:
        if isinstance(r, dict):
            return int(r.get("seq", 0) or 0)
        return int(getattr(r, "seq", 0) or 0)

    def _payload(r: Any) -> dict:
        if isinstance(r, dict):
            p = r.get("payload_json", r.get("payload", r.get("data", {})))
        else:
            p = getattr(r, "payload_json", None)
        return p if isinstance(p, dict) else {}

    ordered = sorted(events, key=_seq)
    open_questionnaire = False
    open_review_key: str | None = None
    for r in ordered:
        t = _type(r)
        if t == _QUESTIONNAIRE_READY:
            open_questionnaire = True
        elif t == _REVIEW_GATE_READY:
            open_review_key = _payload(r).get("gate_key")
        if t in _QUESTIONNAIRE_RESOLUTIONS:
            open_questionnaire = False
        if t in _REVIEW_RESOLUTIONS:
            open_review_key = None

    # A review gate takes precedence when both look open (a run is paused at one gate
    # at a time; the review gate is the later, more specific pause).
    if open_review_key is not None:
        return "review", open_review_key
    if open_questionnaire:
        return "questionnaire", None
    return None, None


# ---------------------------------------------------------------------------
# The mechanical router — the D-04 decision. PURE. ZERO model calls.
# ---------------------------------------------------------------------------
def route_chat_turn(run_state: RunState, turn: ChatTurn) -> Dispatch:
    """Route one chat turn to a command channel by the run's GENERIC live state.

    Pure + side-effect-free + **zero model calls**: it inspects only the generic
    ``run_state`` phase (LIVE-STATE-CONTRACT.md §1) and the turn's generic
    discriminators, and returns a ``Dispatch`` the endpoint executes. No workflow name
    / ``pipeline_type`` / ``spec.id`` is ever read (SC-001/INV-1).
    """
    phase = run_state.phase

    if phase == PHASE_CLARIFY_WAITING:
        # The composer is the clarify ANSWER channel. Structured responses ride
        # verbatim; a bare free-text turn maps to the "freeform" note the FE emits.
        responses = list(turn.responses or [])
        if not responses and turn.text:
            responses = [{"question_id": "freeform", "answer": turn.text}]
        return Dispatch(
            channel=CHANNEL_ANSWERS,
            responses=responses,
            skip_clarification=bool(turn.skip_clarification),
        )

    if phase == PHASE_GATE_PAUSED:
        # A gate action (default approve). update_specs carries the analysis report;
        # redo carries free-text instructions. All ride store.set_review_response —
        # update_specs routes to the shipped KAN-101 loop (never rebuilt here).
        action = turn.action if turn.action in GATE_ACTIONS else "approve"
        if action == "update_specs":
            instructions = turn.analysis_report or turn.text or ""
        else:
            # redo carries free-text instructions; approve/reject carry none.
            instructions = turn.text or None
        return Dispatch(
            channel=CHANNEL_GATE,
            action=action,
            gate_key=run_state.gate_key,
            instructions=instructions,
        )

    if phase == PHASE_TERMINAL:
        # KAN-100 terminal fence: a GATE action on a stopped run is refused with
        # pipeline_not_running — never resolving a gate on a terminal pipeline.
        if turn.action in GATE_ACTIONS:
            return Dispatch(
                channel=CHANNEL_GATE,
                action=turn.action,
                fenced=True,
                code="pipeline_not_running",
            )
        # Otherwise a post-terminal turn is a revision request (family child, D-02).
        return Dispatch(
            channel=CHANNEL_REVISION,
            instruction=turn.text,
            target_artifact_type=turn.target_artifact_type,
        )

    # PHASE_RUNNING — steering: queue the note for the NEXT agent dispatch (29-08 seam).
    return Dispatch(
        channel=CHANNEL_STEERING,
        note={"text": turn.text, "sticky": bool(turn.sticky)},
    )


# ---------------------------------------------------------------------------
# Steering seam (29-08) — append the note to a live ExecutionContext.
# ---------------------------------------------------------------------------
def apply_steering(ectx: Any, note: dict) -> None:
    """Append a steering note to ``ectx.steering_notes`` (the 29-08 consume-once seam).

    Mirrors the ND-11 contract: a ``{"text", "sticky"}`` entry is enqueued onto the
    generic per-run ``steering_notes`` queue; the engine's ``_compose_context_message``
    renders + consumes it at the NEXT dispatch (thread-id policy per ND-11 — base
    thread, next dispatch, no fork). Keyed on the generic queue only (SC-001/INV-1).

    Best-effort: an ``ectx`` without the attribute (a fresh/foreign context) is a no-op
    — the durable ``chat_message`` row remains the record and the note is re-derived on
    resume from ``run_events`` (ND-9).
    """
    queue = getattr(ectx, "steering_notes", None)
    if queue is None:
        return
    queue.append({"text": note.get("text", ""), "sticky": bool(note.get("sticky"))})


# ---------------------------------------------------------------------------
# Per-turn image seam (UPLD-02 residue, 30-03) — the IMAGE analogue of
# ``apply_steering``. Append validated per-turn images to a live ExecutionContext.
# ---------------------------------------------------------------------------
def apply_turn_images(ectx: Any, images: list) -> None:
    """Enqueue per-turn images onto ``ectx.pending_turn_images`` (the 30-03 carrier).

    The image analogue of :func:`apply_steering`: images attached to an in-flight chat
    turn (already cap-validated by the shared ``_validate_images`` ingress caps at the
    ``/messages`` endpoint) are normalized to ``{mime_type, data}`` (the
    ``engine._normalize_run_images`` shape) and appended to the generic per-run
    ``pending_turn_images`` queue. The engine DRAINS that queue onto ``ectx.run_images``
    at the NEXT dispatch (before ``_compose_input_blocks``) so an ``injects:[images]``
    agent's HumanMessage carries the base64 image content-blocks. Keyed on the generic
    queue only (SC-001/INV-1) — no workflow/agent name.

    Best-effort: an ``ectx`` without the attribute (a fresh/foreign context, or the
    DEF-29-09-1 live in-process handle that is not yet wired) is a no-op — the durable
    ``chat_message`` row (attachment refs stamped ``retained:false``, no bytes) remains
    the record, and images are payload-transient (ND-10 — not re-derived on resume).
    """
    queue = getattr(ectx, "pending_turn_images", None)
    if queue is None:
        return
    for img in images or []:
        if not isinstance(img, dict):
            continue
        mime = img.get("mime_type") or img.get("mimeType")
        data = img.get("data")
        if not mime or not data:
            continue
        queue.append({"mime_type": mime, "data": data})


__all__ = [
    "RunState",
    "ChatTurn",
    "Dispatch",
    "route_chat_turn",
    "derive_open_gate",
    "apply_steering",
    "apply_turn_images",
    "PHASE_CLARIFY_WAITING",
    "PHASE_GATE_PAUSED",
    "PHASE_RUNNING",
    "PHASE_TERMINAL",
    "CHANNEL_ANSWERS",
    "CHANNEL_GATE",
    "CHANNEL_STEERING",
    "CHANNEL_REVISION",
    "GATE_ACTIONS",
    "TERMINAL_STATUSES",
]

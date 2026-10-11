"""agents/capabilities/gate_pendency.py — RESUME-17 shared open-gate derivation.

THE single home of the durable open-gate derivation (INV-12 / SC-2). A run parks at
exactly one HITL gate at a time; whether that gate is still OPEN is a pure function of
the durable ``run_events`` log: a ``*_ready`` event with no subsequent matching
resolution (or any terminal) is an open gate. This module owns that derivation plus the
generic event vocabulary it keys on, so the app layer (``chat_router.derive_open_gate``,
``run_stream._dangling_review_gate``) AND the kernel (``ExecutionEngine`` restart re-arm)
import ONE derivation — never three near-duplicate frozensets.

Historically this logic lived inline in ``app/api/chat_router.py`` (the clarify+review
superset), duplicated as ``run_stream._GATE_RESOLUTION_TYPES`` (review-only) and peeked
at again by ``run_commands._gate_is_pending``. RESUME-17 factors it here so the restart
scan re-arms exactly the gate the chat router / SSE re-emit derive — no parallel
pending-arm store (POR §5.5 / Phase 49 SC-2).

Scope guards (mirroring ``agents/capabilities/task_identity.py``):
  - PURE functions + stdlib/typing ONLY. Reads rows via ``getattr``/``get`` so an ORM
    ``RunEvent`` row and a plain ``{type, seq, payload_json}`` dict both derive alike.
  - MUST NOT import ``app.*``, ``agents.execution_engine``, or ``agents.workflows``
    control flow — the import-linter contract "agents.capabilities must not import the
    execution kernel or the web layer". The kernel/strategies AND the app layer import
    THIS module, never the reverse.
  - Zero workflow/agent-name literals (SC-001 / INV-1): keys ONLY on the generic durable
    event vocabulary (``questionnaire_ready`` / ``review_gate_ready`` + resolutions).
"""

from __future__ import annotations

from typing import Any

# ── Durable gate event vocabulary (LIVE-STATE-CONTRACT.md §1) ────────────────
# GENERIC engine event types (the documented run-chat/gate vocabulary), never a
# workflow name. A gate "opens" on its *_ready event and "closes" when a resolution
# event for it (or any terminal) follows in the durable log.
QUESTIONNAIRE_READY = "questionnaire_ready"
REVIEW_GATE_READY = "review_gate_ready"

# Events that close an OPEN questionnaire (clarify) gate.
QUESTIONNAIRE_RESOLUTIONS = frozenset(
    {
        "questionnaire_complete",
        "pipeline_start",
        "pipeline_complete",
        "pipeline_cancelled",
        "pipeline_failed",
        "error",
    }
)

# Events that close an OPEN review gate (the byte-identical superset that
# ``run_stream._GATE_RESOLUTION_TYPES`` re-points at).
REVIEW_RESOLUTIONS = frozenset(
    {
        "review_gate_approved",
        "pipeline_complete",
        "pipeline_cancelled",
        "pipeline_failed",
        "budget_aborted",
        "error",
    }
)

# A3 (resume re-arm): a run-ending marker that recorded an INTERRUPTION of this
# attempt — not a genuine human/gate resolution. ``derive_open_gate`` treats these
# as REVIEW/QUESTIONNAIRE resolutions, which is correct for "is this run's gate
# still live for a client watching it right now" (chat_router / run_stream). A
# RESUME (crash-restart OR the explicit "resume a cancelled/failed run" action)
# exists SPECIFICALLY to continue PAST one of these markers, so the resume-offset
# derivation must not read the interruption itself as "the human resolved it" —
# see ``strip_premature_stops`` below, applied ONLY at resume call sites.
PREMATURE_STOP_EVENT_TYPES = frozenset(
    {"pipeline_cancelled", "pipeline_failed", "budget_aborted", "error"}
)


def strip_premature_stops(events: list) -> list:
    """Drop ``PREMATURE_STOP_EVENT_TYPES`` rows before a RESUME open-gate derivation.

    Bug evidence (pdf_to_prototype STABILIZATION A3): a run cancelled (or crashed)
    while a review gate was durably open, then resumed (crash-restart or the
    explicit "resume a cancelled/failed run" action), persists a
    ``pipeline_cancelled``/``pipeline_failed`` row AFTER the gate's ``*_ready`` and
    BEFORE the resume's own ``run_resuming``/``pipeline_start``. Left in the row
    list, ``derive_open_gate`` reads that marker as a REVIEW_RESOLUTIONS match and
    forgets the gate was open — the resume offset then falls back to the
    per-step completeness scan and can land on an EARLIER, already-approved gate
    (observed: 2+ steps backward, re-prompting an approval the user already gave).
    Every non-resume caller of ``derive_open_gate`` (chat_router / run_stream)
    passes its row list through UNFILTERED — this helper is opt-in at the
    resume-offset call sites only.
    """

    def _type(r: Any) -> str:
        return getattr(r, "type", None) if not isinstance(r, dict) else r.get("type")

    return [r for r in events if _type(r) not in PREMATURE_STOP_EVENT_TYPES]


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
        if t == QUESTIONNAIRE_READY:
            open_questionnaire = True
        elif t == REVIEW_GATE_READY:
            open_review_key = _payload(r).get("gate_key")
        if t in QUESTIONNAIRE_RESOLUTIONS:
            open_questionnaire = False
        if t in REVIEW_RESOLUTIONS:
            open_review_key = None

    # A review gate takes precedence when both look open (a run is paused at one gate
    # at a time; the review gate is the later, more specific pause).
    if open_review_key is not None:
        return "review", open_review_key
    if open_questionnaire:
        return "questionnaire", None
    return None, None


def derive_approved_gate_keys(events: list) -> frozenset:
    """Return every review ``gate_key`` that reached a genuine ``review_gate_approved``.

    RESUME idempotency companion to ``derive_open_gate`` (A3): a ``before-human``
    (pre-step) gate can be durably APPROVED before the step's own agent has produced
    its output — the approval only clears the step to RUN, it does not mean the step
    finished. If the run is interrupted before that agent run completes, the resume
    offset correctly re-enters at that same step (its own work is genuinely
    incomplete) — but re-entering must not re-open the gate that already has a durable
    ``review_gate_approved`` for its EXACT ``gate_key`` (``f"{run}:{agent_id}:
    {visit_count}"`` — the visit_count keeps a loop-revisited step's firings distinct).
    Doing so re-asks the human a question they already answered. This derivation lets
    the kernel skip re-opening a gate whose key is in the returned set; the step's
    STRATEGY still re-runs (only the ALREADY-RESOLVED gate is skipped).

    Same one-gate-open-at-a-time scan ``derive_open_gate`` uses: the gate_key open
    when a ``review_gate_approved`` fires is the one that resolved. Unaffected by
    ``PREMATURE_STOP_EVENT_TYPES`` — a genuine ``review_gate_approved`` row is a real
    human action regardless of what happened to the run afterward, so no filtering is
    needed here (unlike ``derive_open_gate``, callers pass the row list unfiltered).
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
    open_review_key: str | None = None
    approved: set[str] = set()
    for r in ordered:
        t = _type(r)
        if t == REVIEW_GATE_READY:
            open_review_key = _payload(r).get("gate_key")
        elif t == "review_gate_approved" and open_review_key is not None:
            approved.add(open_review_key)
            open_review_key = None
    return frozenset(approved)


__all__ = [
    "QUESTIONNAIRE_READY",
    "REVIEW_GATE_READY",
    "QUESTIONNAIRE_RESOLUTIONS",
    "REVIEW_RESOLUTIONS",
    "PREMATURE_STOP_EVENT_TYPES",
    "strip_premature_stops",
    "derive_open_gate",
    "derive_approved_gate_keys",
]

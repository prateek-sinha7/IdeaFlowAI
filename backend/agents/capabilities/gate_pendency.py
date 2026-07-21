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


__all__ = [
    "QUESTIONNAIRE_READY",
    "REVIEW_GATE_READY",
    "QUESTIONNAIRE_RESOLUTIONS",
    "REVIEW_RESOLUTIONS",
    "derive_open_gate",
]

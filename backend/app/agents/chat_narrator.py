"""app/agents/chat_narrator.py — CHAT-04 / D-01: the milestone → chat_reply narrator.

The chat backbone's **down-channel** half: an APP-LAYER projection that turns run
milestones into ``chat_reply`` result cards — clarify / gate / pipeline / deliverable,
plus a ``spec_revision`` card for the KAN-101 intra-run loop-back ("Revising spec —
cycle N"). Each card is a **pure projection of an already-emitted run event** (NO model
call), persisted as a ``chat_reply`` ``run_events`` row through the SAME
``ScopedStore.append_event`` stamping boundary every engine event rides — inheriting
seq/event_id replay, owner+workspace default-deny, and family-anchoring, with **zero new
tables** (evidence 03 §6; the ``chat_reply`` type was seeded in the Phase-28 vocab).

**Name-freedom (SC-001 / INV-1):** the projection keys ONLY on the GENERIC engine event
vocabulary (``questionnaire_ready`` / ``review_gate_ready`` / ``pipeline_*``) and generic
numeric discriminators (``spec_revision_attempt``). It NEVER branches on a workflow name /
``pipeline_type`` / ``spec.id``. It lives in the APP layer and imports only the stdlib —
NO execution-kernel import — so the banned-pattern gate and import-linter stay green.

**Golden-neutral (INV-3):** the narrator is DORMANT on a scripted golden run — it only
projects when the chat lane is active — so the 5 characterization goldens stay byte/event-
identical (the ``chat_reply`` card discriminators are stable and never appear on a golden).

**Deep-link seam (T-29-10-2 / WR-02):** every card carries a ``{target, nonce}`` deep-link
whose ``nonce`` is **single-use** and now **DB-backed + owner+workspace-scoped**. The Phase-29
process-global in-memory ``_ISSUED_NONCES`` set (unbounded, unscoped, lost on restart) is
DELETED (INV-3/INV-12 — no dual store): ``persist_milestone_card`` mints the nonce as a durable
``deep_link_nonces`` row through the SAME scoped ``store`` (owner+workspace stamped), and
``consume_deep_link(store, nonce)`` delegates to that store's single-use, owner-scoped consume —
a replayed OR cross-owner nonce resolves to nothing (False → 404), never twice.
"""

from __future__ import annotations

import uuid
from typing import Any

# ── The five card-kind discriminators (MOCKWS-CHAT-DRIVER-CONTRACT §2.2 + the ─────────
# Phase-29 ``spec_revision`` addition for the KAN-101 loop-back). GENERIC — not names.
CARD_CLARIFY = "clarify"
CARD_GATE = "gate"
CARD_PIPELINE = "pipeline"
CARD_DELIVERABLE = "deliverable"
CARD_SPEC_REVISION = "spec_revision"

CARD_KINDS = frozenset(
    {CARD_CLARIFY, CARD_GATE, CARD_PIPELINE, CARD_DELIVERABLE, CARD_SPEC_REVISION}
)

# ── Source-event vocabulary (LIVE-STATE-CONTRACT §1 / evidence 03 §1). GENERIC engine ─
# event types the milestones project from — never a workflow name.
_CLARIFY_EVENTS = frozenset({"questionnaire_ready", "questionnaire_complete"})
_GATE_EVENTS = frozenset({"review_gate_ready"})
# KAN-154: gate-resolution events — the user's approval/reject action surfaced in chat.
# Generic: keyed on event type only (SC-001/INV-1).
_GATE_RESOLVED_EVENTS = frozenset({"review_gate_approved"})

# The persisted run-chat card type — ALREADY in the Phase-28 vocab
# (_DOCUMENTED_EVENT_TYPES); reused verbatim, never re-added / drifted.
CHAT_REPLY_TYPE = "chat_reply"


# ---------------------------------------------------------------------------
# Event shape helpers — read a live engine event ({type, data}) OR a persisted
# RunEvent-like row ({type, payload_json}) uniformly (mirrors derive_open_gate).
# ---------------------------------------------------------------------------
def _event_type(event: Any) -> str:
    if isinstance(event, dict):
        return event.get("type", "") or ""
    return getattr(event, "type", "") or ""


def _event_data(event: Any) -> dict:
    if isinstance(event, dict):
        d = event.get("data", event.get("payload_json", {}))
    else:
        d = getattr(event, "data", None)
        if d is None:
            d = getattr(event, "payload_json", None)
    return d if isinstance(d, dict) else {}


def _event_id(event: Any) -> str | None:
    if isinstance(event, dict):
        eid = event.get("event_id")
        if not eid:
            # The live engine event sink stamps the source id into ``data`` (not the
            # top level: ``{type, data:{event_id, seq, …}}``) — read it there too so the
            # chat_reply row's idempotency key namespaces on the real source event id
            # (stable across a durable-log replay), not the fallback nonce.
            data = event.get("data")
            if isinstance(data, dict):
                eid = data.get("event_id")
    else:
        eid = getattr(event, "event_id", None)
    return eid if isinstance(eid, str) and eid else None


def _run_id(data: dict, event: Any) -> str | None:
    run_id = data.get("pipeline_run_id") or data.get("run_id")
    if run_id:
        return run_id
    if not isinstance(event, dict):
        return getattr(event, "run_id", None)
    return None


def _revision_index(data: dict) -> int:
    """The KAN-101 loop-back cycle counter (``spec_revision_attempt`` / ``revision_index``).

    A generic positive-int discriminator — NOT a workflow name — marking an intra-run
    spec-revision cycle (distinct from a family revision run, D-02).
    """
    raw = data.get("spec_revision_attempt")
    if raw is None:
        raw = data.get("revision_index")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Deep-link nonce — DB-backed, owner+workspace-scoped, single-use (T-29-10-2 / WR-02).
# ---------------------------------------------------------------------------
async def consume_deep_link(store: Any, nonce: str) -> bool:
    """Consume a deep-link nonce ONCE, owner+workspace-scoped (WR-02).

    Delegates to the injected owner+workspace-scoped ``store``
    (``agents.authz.ScopedStore``): returns ``True`` iff a durable ``deep_link_nonces`` row
    exists that is owner+workspace-matched AND unconsumed — atomically marking it consumed —
    and ``False`` on every subsequent presentation (replay/reuse defense, T-43-03-REPLAY),
    for a nonce this owner never held (cross-owner, T-43-03-SPOOF/IDOR), or for one that was
    never issued. The API maps ``False`` to a 404 (IDOR→404 — never leaks existence). The
    Phase-29 process-global in-memory ``_ISSUED_NONCES`` set is DELETED (no dual store).
    """
    return await store.consume_deep_link_nonce(nonce)


# ---------------------------------------------------------------------------
# The projection — pure, generic, ZERO model calls.
# ---------------------------------------------------------------------------
def _classify(
    etype: str, data: dict, run_id: str | None
) -> tuple[str | None, str, str]:
    """Map one generic run event to ``(card_kind, text, deep_link_target)``.

    Returns ``(None, "", "")`` when the event is not a projectable milestone. Keyed on the
    generic event vocabulary + numeric discriminators ONLY (SC-001/INV-1).
    """
    anchor = run_id or "run"

    # spec_revision wins first: an intra-run KAN-101 loop-back cycle (label DISTINCTLY
    # from a family revision run, D-02 terminology) regardless of the carrying event.
    attempt = _revision_index(data)
    if attempt > 0:
        return (
            CARD_SPEC_REVISION,
            f"Revising spec — cycle {attempt}",
            f"spec_revision:{anchor}:{attempt}",
        )

    if etype in _CLARIFY_EVENTS:
        n = data.get("question_count")
        if n is None:
            n = len(data.get("questions", []) or [])
        if etype == "questionnaire_complete":
            text = f"{n} clarifications answered" if n else "Clarifications answered"
        else:
            text = "Before I build, I need to lock a few things down."
        return CARD_CLARIFY, text, f"clarify:{anchor}"

    if etype in _GATE_EVENTS:
        gate_key = data.get("gate_key")
        return CARD_GATE, "Paused — needs approval", gate_key or f"gate:{anchor}"

    # KAN-154: gate-resolved events — surfaces the user's approve/reject action as an
    # inline clarify-style note in the transcript. Generic: keyed on event type only
    # (SC-001/INV-1). Action "reject" ends the pipeline (pipeline_cancelled follows);
    # "approve" advances it.
    # FIX-178 follow-up: the "approve" action is no longer emitted as a separate
    # narrator card — the FE now resolves the original gate card in-place and renders
    # "Review approved — build continues" inline. Emitting a second card caused a
    # duplicate "Approved" entry. Only redo/update_specs still emit a card (they are
    # informational loop-back actions not covered by the gate card resolution).
    if etype in _GATE_RESOLVED_EVENTS:
        action = data.get("action", "approve")
        if action == "redo":
            return CARD_CLARIFY, "Redo requested", f"gate:{anchor}"
        if action == "update_specs":
            return CARD_CLARIFY, "Updating the specs", f"gate:{anchor}"
        # approve / reject / default: no separate card — the gate card itself is
        # resolved by the FE on review_gate_approved.
        return None

    if etype == "pipeline_complete":
        # A completion carrying deliverable metadata is a DELIVERABLE milestone
        # ("Delivered as vN — open in Preview →"); otherwise the plain pipeline summary.
        filename = data.get("deliverable_filename")
        if filename or data.get("deliverable_mimetype"):
            target = f"deliverable:{filename}" if filename else f"deliverable:{anchor}"
            return CARD_DELIVERABLE, "Delivered — open in Preview →", target
        return CARD_PIPELINE, "Run complete", f"run:{anchor}"

    if etype == "pipeline_start":
        # KAN-154: *_revision pipeline_start surfaces as an inline clarify-style note
        # ("Revision started") so the user can see when a revision run launched in the
        # shared family transcript. Generic: keyed on the "_revision" suffix, never the
        # full pipeline_type literal (SC-001/INV-1).
        pipeline_type = data.get("pipeline_type", "")
        if isinstance(pipeline_type, str) and pipeline_type.endswith("_revision"):
            return CARD_CLARIFY, "Revision started", f"run:{anchor}"
        return CARD_PIPELINE, "Run started", f"run:{anchor}"
    if etype == "pipeline_failed":
        return CARD_PIPELINE, "What went wrong", f"run:{anchor}"
    if etype == "pipeline_cancelled":
        return CARD_PIPELINE, "Cancelled by you", f"run:{anchor}"

    return None, "", ""


def project_milestone_card(event: Any) -> dict | None:
    """Project one run event into a ``chat_reply`` card payload, or ``None``.

    PURE + side-effect-free (bar minting the card's single-use nonce) + **zero model
    calls**: it inspects only the generic event type + data (LIVE-STATE-CONTRACT §1) and
    returns the ``chat_reply`` payload — the narrator's projection of the milestone the
    event reports. ``event`` may be a live engine event (``{type, data}``) or a persisted
    ``RunEvent``-like row (``{type, payload_json}``). Non-milestone events → ``None``.

    The returned card mirrors the MOCKWS-CHAT-DRIVER-CONTRACT §2.2 ``chat_reply`` shape:
    ``card_kind`` ∈ :data:`CARD_KINDS`, a narrator ``text`` body, and the consume-once
    ``deep_link = {target, nonce}`` seam linking the card to its milestone/artifact. The
    ``nonce`` here is a freshly-generated candidate id ONLY; it becomes a durable, owner-
    scoped, single-use ``deep_link_nonces`` row when — and only when — ``persist_milestone_card``
    actually persists the card (WR-02). Keeping this projection side-effect-free means the
    pure event→card mapping never touches the DB (and the DELETED in-memory set can't leak).
    """
    etype = _event_type(event)
    data = _event_data(event)
    run_id = _run_id(data, event)

    kind, text, target = _classify(etype, data, run_id)
    if kind is None:
        return None

    return {
        "pipeline_run_id": run_id,
        "message_id": f"reply:{uuid.uuid4().hex}",  # server-assigned reply id
        "card_kind": kind,
        "text": text,
        "deep_link": {"target": target, "nonce": uuid.uuid4().hex},
    }


# ---------------------------------------------------------------------------
# Persistence — append the card as a chat_reply run_events row (zero new tables).
# ---------------------------------------------------------------------------
def _reply_event_id(source_event_id: str | None, card: dict) -> str:
    """Derive the durable ``event_id`` for the card row.

    Idempotency lives at the stamping boundary: a card projected from the SAME source
    milestone yields the SAME ``event_id`` (namespaced ``chat_reply:{source}``), so a
    replayed milestone resolves to the already-present row (a no-op — no second card).

    For run-level pipeline_start cards, idempotency must be per-RUN rather than
    per-source-event-id: a resumed run emits a NEW pipeline_start with a NEW event_id,
    which would otherwise produce a second "Run started" card.  We key on
    ``pipeline_start:{run_id}`` so all pipeline_start events for the same run collapse to
    one card.  Other CARD_PIPELINE events (complete/failed/cancelled) keep the
    source-event-id key because each occurrence is genuinely distinct (one per run).
    KAN-120: fixes the duplicate "Run started" card on resume.
    """
    # pipeline_start cards are keyed by run_id, not by the source event_id, so that a
    # resumed run's new pipeline_start event resolves to the existing card (idempotent).
    card_text = card.get("text", "")
    card_kind = card.get("card_kind", "")
    deep_link_target = (card.get("deep_link") or {}).get("target", "")
    if card_kind == CARD_PIPELINE and card_text == "Run started" and deep_link_target:
        return f"{CHAT_REPLY_TYPE}:pipeline_start:{deep_link_target}"
    if source_event_id:
        return f"{CHAT_REPLY_TYPE}:{source_event_id}"
    return f"{CHAT_REPLY_TYPE}:{card['deep_link']['nonce']}"


async def persist_milestone_card(
    store: Any, run_id: str, event: Any
) -> tuple[bool, int, dict, str] | None:
    """Project ``event`` and persist the card as a ``chat_reply`` ``run_events`` row.

    Returns ``(created, seq, card, reply_eid)`` — or ``None`` when the event is not a
    projectable milestone (nothing persisted). ``created=False`` marks an idempotent no-op
    (a row for the same source milestone already exists). ``reply_eid`` is the DB row's
    ``event_id`` — returned so the engine can stamp the SAME value on the live SSE yield,
    ensuring the FE's ``seenRef`` dedup recognises the DB-fetched frame as a duplicate
    (FIX-175: the idempotency key for "Run started" differs from the source event UUID).

    The row is appended through the SINGLE ``ScopedStore.append_event`` stamping boundary
    (evidence 03 §6): family-anchored on ``run_id``, owner+workspace default-deny (the
    ``store`` carries the scope), with the contiguous per-run ``seq`` (max persisted + 1)
    the engine sink itself computes — so the card inherits seq/event_id replay + reopen for
    free, with **zero new tables**.

    The projection reads only the run's OWN scoped events (``store.read_events``), so a
    card can never leak or resolve a cross-owner milestone (T-29-10-1).
    """
    card = project_milestone_card(event)
    if card is None:
        return None

    # CR-03: allocate seq + enforce idempotency through the store's serialized
    # ``append_event_next_seq`` (collision-safe against the engine's own concurrent
    # event sink), NOT a bare read-``max(seq)+1``-then-write. This stays stdlib-only —
    # it is a method call on the INJECTED ``store`` (no execution-kernel import).
    reply_eid = _reply_event_id(_event_id(event), card)
    created, seq = await store.append_event_next_seq(
        run_id,
        event_id=reply_eid,
        type=CHAT_REPLY_TYPE,
        payload_json=card,
    )
    # WR-02: mint the durable, owner+workspace-scoped, single-use deep-link nonce row ONLY
    # when the card row was actually created — so a replayed milestone (created=False, an
    # idempotent no-op) never leaks a second unconsumed nonce, keeping nonce rows 1:1 with
    # card rows. The row is stamped with the SAME scoped ``store`` principal that owns the
    # card, so ``consume_deep_link`` under any other owner resolves to nothing (IDOR→404).
    if created:
        await store.mint_deep_link_nonce(
            nonce=card["deep_link"]["nonce"],
            run_id=run_id,
            target=card["deep_link"]["target"],
        )
    # FIX-175: return reply_eid alongside (created, seq, card) so the engine can
    # stamp the SAME event_id on the live SSE yield.  Using the raw
    # f"chat_reply:{source_uuid}" on the live frame but a different idempotency key
    # in the DB row (e.g. "chat_reply:pipeline_start:run:{run_id}" for "Run started")
    # caused the FE seenRef dedup to miss the match — appendFrames (FIX-172) would
    # add the card a second time as a "new" event, producing duplicate chat cards.
    return created, seq, card, reply_eid


__all__ = [
    "project_milestone_card",
    "persist_milestone_card",
    "consume_deep_link",
    "CARD_KINDS",
    "CARD_CLARIFY",
    "CARD_GATE",
    "CARD_PIPELINE",
    "CARD_DELIVERABLE",
    "CARD_SPEC_REVISION",
    "CHAT_REPLY_TYPE",
]

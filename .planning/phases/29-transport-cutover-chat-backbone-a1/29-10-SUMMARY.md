---
phase: 29-transport-cutover-chat-backbone-a1
plan: 10
subsystem: chat-backbone
tags: [CHAT-04, narrator, chat_reply, deep-link, INV-3, LOCK-B, name-free]
requires:
  - "chat_reply type seeded in _DOCUMENTED_EVENT_TYPES (Phase 28)"
  - "ScopedStore.append_event single stamping boundary (agents/authz.py:284)"
  - "chat_router.py mechanical up-channel (29-09 sibling)"
provides:
  - "app.agents.chat_narrator.project_milestone_card — milestone -> chat_reply card projection"
  - "app.agents.chat_narrator.persist_milestone_card — chat_reply run_events persistence"
  - "app.agents.chat_narrator.consume_deep_link — single-use deep-link nonce seam"
affects:
  - "Phase 31/32 chat-lane rendering consumes chat_reply cards"
tech-stack:
  added: []
  patterns:
    - "App-layer pure projection (no model call, no kernel import)"
    - "Idempotent run_events persistence keyed on source event_id"
    - "Consume-once nonce registry (single-use deep-link)"
key-files:
  created:
    - backend/app/agents/chat_narrator.py
    - backend/tests/unit/test_chat_narrator.py
  modified: []
decisions:
  - "spec_revision card keyed on a generic numeric discriminator (spec_revision_attempt/revision_index>0), name-free — precedes plain milestone classification"
  - "deliverable card fires from pipeline_complete carrying deliverable metadata; plain pipeline card from start/failed/cancelled/complete-without-artifact"
  - "reply event_id namespaced chat_reply:{source_event_id} for idempotency; nonce fallback when source lacks an event_id"
metrics:
  duration: ~18 min
  completed: 2026-07-08
  tasks: 2
  files: 2
---

# Phase 29 Plan 10: Narrator (CHAT-04) chat_reply Milestone Cards Summary

App-layer narrator that projects run milestones into `chat_reply` result cards (clarify / gate / pipeline / deliverable + a `spec_revision` card for the KAN-101 intra-run loop-back), each a pure projection of an existing run event (no model call), persisted as a `chat_reply` `run_events` row through the single `ScopedStore.append_event` boundary with a single-use deep-link `{target, nonce}` seam — golden-neutral, zero new tables. This is the FINAL plan of Phase 29.

## What Was Built

- **`project_milestone_card(event) -> dict | None`** — maps a generic run event to a `chat_reply` card. Card kinds `{clarify, gate, pipeline, deliverable, spec_revision}` derive purely from the generic engine vocabulary (`questionnaire_ready`/`questionnaire_complete` → clarify; `review_gate_ready` → gate; `pipeline_start`/`failed`/`cancelled`/`complete` → pipeline; `pipeline_complete` carrying deliverable metadata → deliverable) and a generic numeric discriminator (`spec_revision_attempt`/`revision_index` > 0 → `spec_revision`, labelled distinctly as "Revising spec — cycle N", D-02 terminology). Accepts both a live engine event (`{type, data}`) and a persisted `RunEvent`-like row (`{type, payload_json}`). No model call.
- **Deep-link `{target, nonce}` seam** — every card carries a consume-once nonce; `consume_deep_link(nonce)` resolves it exactly once (True first, False on reuse and for any never-issued nonce) — the T-29-10-2 replayed-nonce defense.
- **`persist_milestone_card(store, run_id, event)`** — projects then appends the card as a `type="chat_reply"` `run_events` row via `ScopedStore.append_event`: family-anchored on `run_id`, owner+workspace default-deny (store carries the scope), contiguous per-run `seq` (max persisted + 1, exactly the engine sink's rule), idempotent on `event_id = chat_reply:{source_event_id}` (replayed milestone → no-op). Projection reads only the run's own scoped events (T-29-10-1). Zero new tables.

## Verification Evidence (all OFFLINE — python3.11, no live Bedrock/server)

- `pytest tests/unit/test_chat_narrator.py` → **23 passed** (18 projection/deep-link + 5 persistence).
- `pytest test_chat_narrator.py test_wire_parity.py test_characterization_prototype.py test_characterization_od_ppt.py -x -q` → **33 passed** (35.94s).
- Remaining goldens `test_characterization_od_prototype.py test_characterization_prototype_revision.py test_characterization_app_builder.py` → **6 passed** (20.64s). All 5 INV-3 characterization goldens byte/event-identical (NO SNAPSHOT_UPDATE; narrator dormant on scripted golden runs).
- `pytest tests/agents/test_banned_patterns.py` → **11 passed** (SC-001 name-free clean).
- `cd backend && /opt/homebrew/bin/lint-imports` → **4 kept, 0 broken** (narrator is stdlib-only; no execution-kernel import).

## LOCK-B Confirmation

`git diff --name-only` for the plan =
```
backend/app/agents/chat_narrator.py
backend/tests/unit/test_chat_narrator.py
```
- websocket.py / websocket_handoff.py / useWebSocket.ts — **ABSENT** from the diff.
- No migration file added (no `alembic/versions/*`); zero new tables — `chat_reply` rides the existing `run_events` row via `append_event`, reusing the Phase-28 `_DOCUMENTED_EVENT_TYPES` vocab (not re-added/drifted).
- No `/ws/chat` handler touched, no arm ratchet, no ledger row.

## Deviations from Plan

None — plan executed exactly as written. Both tasks followed the RED → GREEN gate (failing test committed, then implementation).

## Design Notes

- `spec_revision` is checked FIRST in classification so an intra-run KAN-101 loop-back (carrying `spec_revision_attempt`) is labelled distinctly even when its carrying event (e.g. a re-fired `agent_start`/`pipeline_start`) would otherwise classify as a plain milestone — honoring the mandatory D-02 terminology rule (spec-revision loop ≠ family revision run).
- `deliverable` vs `pipeline` on `pipeline_complete`: keyed on the presence of `deliverable_filename`/`deliverable_mimetype` so a completion carrying the artifact projects the "Delivered — open in Preview →" deliverable card, while a bare completion projects the plain pipeline summary card.

## Known Stubs

None. The narrator is a complete projection + persistence seam. Live in-process emission of cards onto the down-channel (wiring the narrator into the running engine/queue) is intentionally OUT of LOCK-B scope for this plan — the projection + durable `chat_reply` record are proven offline at the seam level, and the FE consumes them via the existing `run_events` replay in Phase 31/32.

## Deferred-to-live

- End-to-end live emission of narrator cards during a real Bedrock run (card appears on the SSE/WS down-channel as milestones fire) — proven at the seam level offline (projection + `append_event` persistence + idempotent replay); confirm at the consolidated milestone-end live pass (D-24).

## Self-Check: PASSED
- FOUND: backend/app/agents/chat_narrator.py
- FOUND: backend/tests/unit/test_chat_narrator.py
- Commits verified present (see completion report).

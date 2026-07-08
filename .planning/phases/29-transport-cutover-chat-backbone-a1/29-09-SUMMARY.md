---
phase: 29-transport-cutover-chat-backbone-a1
plan: 09
subsystem: chat-backbone-up-channel
tags: [CHAT-01, CHAT-02, CHAT-05, D-04, D-01, D-02, KAN-94, KAN-100, KAN-101, LOCK-B]
requires:
  - "29-03/29-04 REST command seams (gate/answers/revisions in run_commands.py)"
  - "29-08 steering seam (ectx.steering_notes in context.py) + ND-11 decision record"
  - "28 chat vocab: chat_message/chat_reply in _DOCUMENTED_EVENT_TYPES; message_id in _VOLATILE_STRIP_KEYS"
  - "agents/authz.py ScopedStore.append_event (single stamping boundary)"
provides:
  - "POST /api/runs/{id}/messages — idempotent chat-turn up-channel (chat_message run_events row)"
  - "chat_router.route_chat_turn — mechanical intent router (run-state -> dispatch, zero model calls)"
affects:
  - "backend/app/api/run_commands.py"
  - "backend/app/api/chat_router.py"
tech-stack:
  added: []
  patterns: ["mechanical run-state routing (name-free)", "idempotency by client message_id -> derived event_id at the stamping boundary"]
key-files:
  created:
    - backend/app/api/chat_router.py
    - backend/tests/unit/test_mechanical_router.py
    - backend/tests/unit/test_chat_messages_endpoint.py
  modified:
    - backend/app/api/run_commands.py
decisions:
  - "Router is PURE (RunState + ChatTurn -> Dispatch); the endpoint executes the dispatch through the shipped seams — zero model calls on any routable branch"
  - "open_gate derived from durable run_events (generic vocab) AND confirmed armed in the store (KAN-94) before treating a run as gate_paused"
  - "steering live-delivery to the in-process ectx is deferred (engine drain out of LOCK-B); the durable chat_message row is the record and the seam is proven offline"
metrics:
  duration: ~40 min
  completed: 2026-07-08
---

# Phase 29 Plan 09: Chat Backbone Up-Channel + Mechanical Router Summary

Ships the chat backbone's up-channel: `POST /api/runs/{id}/messages` persists a user turn as an idempotent `chat_message` `run_events` row (zero new tables) and the mechanical intent router keys on GENERIC run state to deliver the turn with zero model calls — clarify answer / gate action (incl. `update_specs`→KAN-101) / steering note / revision.

## What shipped

**Task 1 — `POST /api/runs/{id}/messages` (persist + idempotency).** The turn persists as a `type="chat_message"` `run_events` row via `ScopedStore.append_event` through the single stamping boundary (seq = max persisted + 1, exactly as `_stamp_resume_marker`). Idempotency is at the boundary: `event_id = f"chat:{message_id}"` — a replayed `message_id` resolves to the already-present row and is a no-op (no second row). Two-layer owner check mirrors `run_stream.py`/`runs.py::get_run_events` (`user_id` filter → 404, then default-deny `ScopedStore.get_run` → 404; IDOR → 404, never 403). Attachments are payload-transient (ND-10): a `{kind, retained:False}` placeholder is stored — bytes are never persisted.

**Task 2 — `chat_router.route_chat_turn` (the mechanical router).** A PURE function `route_chat_turn(run_state, turn) -> Dispatch` that keys ONLY on generic live-state signals (LIVE-STATE-CONTRACT.md §1) — never a workflow name / `pipeline_type` / `spec.id`. It lives in the app layer, not the kernel. The four branches: `clarify_waiting → answers`; `gate_paused → gate` (approve/reject/redo/update_specs, `update_specs` carries the analysis report to the shipped KAN-101 loop); `running → steering`; `terminal → revision`. A gate action after terminal is fenced (`pipeline_not_running`, KAN-100). `derive_open_gate` scans the durable `run_events` for the last still-open gate using the generic event vocabulary; `apply_steering` appends `{text,sticky}` to `ectx.steering_notes` (the 29-08 seam, ND-11).

**Task 3 — wire `/messages` → router.** The endpoint assembles a generic `RunState` (`status` + event-derived `open_gate`, gated on the KAN-94 armed-store ground truth so an excluded gate is not assumed to pause) and dispatches through the SAME seams the 29-03/29-04 endpoints wrap: `store.set_questionnaire_responses` / `store.set_review_response` (four actions) / the family-child revision driver (`_mint_revision_row` + `_drive_revision_to_queue`). Steering queues to the 29-08 seam (durable `chat_message` record; live in-process delivery deferred — see below).

## Verification (offline, real output)

- `python3.11 -m pytest tests/unit/test_chat_messages_endpoint.py tests/unit/test_mechanical_router.py tests/agents/test_wire_parity.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_ppt.py -x -q` → **49 passed** (14 endpoint + 25 router + 6 wire-parity + 2 prototype + 2 od_ppt).
- `python3.11 -m pytest tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -q` → **6 passed** (the remaining 3 of the 5 goldens — byte/event-identical, NO SNAPSHOT_UPDATE).
- `python3.11 -m pytest tests/agents/test_banned_patterns.py -x -q` → **11 passed** (SC-001/INV-1 name-free clean).
- `cd backend && /opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**.

All 5 characterization goldens stay byte/event-identical (INV-3): the chat lane is dormant on the scripted harness (goldens send no `chat_message`); no golden fixture edited; no `SNAPSHOT_UPDATE`.

## LOCK-B confirmation

`git diff --name-only 3ea0beae~1..HEAD`:
```
backend/app/api/chat_router.py
backend/app/api/run_commands.py
backend/tests/unit/test_chat_messages_endpoint.py
backend/tests/unit/test_mechanical_router.py
```
- `websocket.py` / `websocket_handoff.py` / `useWebSocket.ts` — **ABSENT** from the diff.
- **Zero** migration / alembic files added → **zero new tables** (the chat turn is a `chat_message` `run_events` row through the existing `append_event` boundary).
- No `/ws/chat` handler deletion, no ratchet, no ledger row.

## Threats mitigated (register)

- **T-29-09-1 (Info Disclosure)** — two-layer owner check → 404; ScopedStore owner+workspace default-deny (`test_cross_owner_is_404`, `test_missing_run_is_404`).
- **T-29-09-2 (Tampering / replay)** — idempotency by `message_id`→`event_id` at the stamping boundary (`test_replayed_message_id_is_noop`).
- **T-29-09-3 (Tampering / gate after terminal)** — KAN-100 `pipeline_not_running` fence in the router (`test_gate_action_after_terminal_is_fenced`).
- **T-29-09-4 (EoP / kernel name-branch creep)** — router is app-layer + generic-state-keyed; banned-pattern + import-linter green.

## Deviations from Plan

None — plan executed as written (Rules 1–4 not triggered). The endpoint follows the 29-03/29-04 read-only-seam idiom exactly.

## Deferred Items

- **DEF-29-09-1 — steering live in-process delivery.** The router routes `running → steering` and `apply_steering` appends to `ectx.steering_notes` (both proven offline). The LIVE endpoint→running-`ectx` handle lookup (an engine-side drain / re-derivation of pending steering from `run_events` at the next dispatch, ND-9/ND-11 §5) requires an `engine.py` edit that is OUTSIDE this plan's LOCK-B allow-list. The durable `chat_message` row is the record; the wiring lands with the engine-side steering-drain plan. The seam contract is fully proven (`test_mechanical_router.TestSteeringRouting`).
- **DEF-live** — end-to-end delivery over live Bedrock (revision child run, gate resume→engine continuation) is proven at the seam level offline; the consolidated live pass runs at milestone end (D-24).

## Known Stubs

None. No hardcoded empty values flow to UI; the steering branch is documented-deferred (DEF-29-09-1), not a silent stub.

## Self-Check: PASSED

- `backend/app/api/chat_router.py` — FOUND
- `backend/tests/unit/test_mechanical_router.py` — FOUND
- `backend/tests/unit/test_chat_messages_endpoint.py` — FOUND
- Commit `3ea0beae` (Task 1) — FOUND
- Commit `e5b659fa` (Task 2) — FOUND
- Commit `fd5104b9` (Task 3) — FOUND

---
phase: 28-chat-contracts-guards-a0
plan: 03
subsystem: ui
tags: [contracts, e2e, mockws, chat-driver, resolved-decisions, decision-lock, additive-only]

# Dependency graph
requires:
  - phase: 28-chat-contracts-guards-a0 (plan 01)
    provides: chat event vocabulary (chat_message/chat_reply/stream_attached) + golden guards
  - phase: 28-chat-contracts-guards-a0 (plan 02)
    provides: Steps/live-state/figure-pinning UI-SPEC contracts
provides:
  - "MOCKWS-CHAT-DRIVER-CONTRACT.md — the e2e chat-driver API pinned against the live mockWs.ts { type, data:{…, event_id, seq } } envelope; catalogues chat_message / chat_reply / stream_attached frames + driver methods; records LOCK-B additive-only transport and the 123-spec preservation bar (consumer RUNUI-05)"
  - "RESOLVED-DECISIONS.md — LOCK-A..G transcribed verbatim-in-substance + a ND-1..ND-13 disposition table (all 13 distinct, each RESOLVED/RESOLVED-deferred/DEFERRED with its POR §3 lock source); the single citable authority so the auto-chain never re-opens a locked ND"
affects: [31-chat-lane, 32-run-redesign, 29-chat-backbone, 35-sibling-reskin, 37-configure-composer, RUNUI-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive-extension e2e driver contract: the new chat driver extends the existing MockWs controller (same envelope, same seq/event_id counters, same connection) rather than a rewrite — the 123 existing mocked specs stay green"
    - "Decision-lock record: every ND transcribed from the POR §3 AUTONOMOUS-RUN DECISION LOCK as DECIDED with its lock source; Phase 28 only FORMALIZES, never re-derives (mode yolo/skip_discuss)"

key-files:
  created:
    - .planning/phases/28-chat-contracts-guards-a0/contracts/MOCKWS-CHAT-DRIVER-CONTRACT.md
    - .planning/phases/28-chat-contracts-guards-a0/contracts/RESOLVED-DECISIONS.md
  modified: []

key-decisions:
  - "Chat driver is ADDITIVE to MockWs (LOCK-B): reuses the single seq counter, nextEventId()/GLOBAL_EVENT_ID, and the one connection; pipeline_reconnected stays and stream_attached is added beside it — no WS frame-contract removal, no useWebSocket.ts touch"
  - "stream_attached { live, replayed_through_seq } supersedes pipeline_reconnected for chat/stream reattach, mirroring the existing reconnected() replay semantics (replayed_through_seq = current seq cursor)"
  - "All 13 NDs recorded as DECIDED: ND-2 Concierge always-on (Haiku); LOCK-E defers team-sharing/resume-from-failed/prompt-override/image-persistence (placeholder); output name = Deliverable (ND-13.6); DS real ~14 count (ND-8); ND-11/ND-9 = Phase 29 design tasks; ND-12 sibling scope locked (35/37, Handoff deferred)"

patterns-established:
  - "Contract docs are prose + tables only — no fenced code blocks (a contract, not an implementation; Phase 31 implements the driver)"

requirements-completed: [CHAT-06]

# Metrics
duration: 9min
completed: 2026-07-07
---

# Phase 28 Plan 03: mockWs Chat-Driver & Resolved-Decisions Contracts Summary

Pinned the last two Phase 28 [A0] contract deliverables — the e2e mockWs chat-driver contract (the additive test-harness surface phases 31/32 build chat specs against, RUNUI-05) and the resolved-decisions record (LOCK-A..G + ND-1..ND-13 transcribed as DECIDED) — as documents only, transcribed from the locked POR §3 and the live `mockWs.ts` frame contract, with zero code change and no decision re-opened.

## What Was Built

**Task 1 — `MOCKWS-CHAT-DRIVER-CONTRACT.md` (commit 07f270a5).** Read `frontend/e2e/fixtures/mockWs.ts` fully (its header `INBOUND FRAME CONTRACT` block + the private `emit(type, data)` wrapper) and specified the new chat driver as an additive extension of the existing `MockWs` controller. Pins the exact `{ type, data: { …payload, event_id, seq } }` envelope (dedup reads `data.event_id` string, resume cursor reads `data.seq` number — same as today), catalogues the three POR D-01 chat frames (`chat_message` user-turn echo with client `message_id`/text/attachments; `chat_reply` narrator cards for clarify/gate/pipeline/deliverable milestones with the consume-once deep-link nonce seam; `stream_attached` `{ live, replayed_through_seq }` handshake replacing `pipeline_reconnected`), describes the driver methods mirroring the existing `MockWs` shape (inbound scripters + an outbound POST-shaped-command assert reusing `sent[]`/`waitForClientFrame` + a `stream_attached` replay helper), and records the LOCK-B additive-only constraint and the 123-mocked-spec preservation bar.

**Task 2 — `RESOLVED-DECISIONS.md` (commit b6ca9751).** Transcribed the POR §3 AUTONOMOUS-RUN DECISION LOCK: section 1 is LOCK-A..G verbatim-in-substance; section 2 is a ND-1..ND-13 disposition table (13 distinct ND ids, each RESOLVED / RESOLVED-deferred / DEFERRED with its lock source), pulled from the POR ND bodies + evidence 11 §B/§C for the ND-13 cosmetic defaults. Section 3 restates the load-bearing invariants (transport ADDITIVE-ONLY, Concierge always-on, the LOCK-E deferrals, output name "Deliverable"). Header forbids re-opening — the single artifact later phases cite instead of re-litigating.

## Verification

Both automated grep gates print OK:
- Task 1 gate: file exists + contains `chat_message`, `chat_reply`, `stream_attached`, `event_id`, `seq`, `LOCK-B`, `RUNUI-05` → OK.
- Task 2 gate: file exists + contains `LOCK-A`..`LOCK-G`, `ND-1`, `ND-13`, `Deliverable`, `additive` AND distinct ND-id count = 13 (≥13 required) → OK (distinct ND ids = 13).

Both docs are prose + tables only (fenced-code-block count = 0 in each). No source file was edited — `git diff` across both commits shows only the two contract `.md` files; `mockWs.ts` was read-only.

## Deviations from Plan

None — plan executed exactly as written. No auto-fixes, no architectural decisions, no auth gates. Both tasks are `type="auto"`, docs-only; no package installs, no runtime surface.

## Known Stubs

None — both deliverables are complete contract documents, not stubs. They intentionally contain no implementation (the driver is implemented in Phase 31 per RUNUI-05); this is the documented contract-vs-implementation split, not a stub gap.

## Self-Check: PASSED

- FOUND: .planning/phases/28-chat-contracts-guards-a0/contracts/MOCKWS-CHAT-DRIVER-CONTRACT.md
- FOUND: .planning/phases/28-chat-contracts-guards-a0/contracts/RESOLVED-DECISIONS.md
- FOUND: commit 07f270a5 (Task 1)
- FOUND: commit b6ca9751 (Task 2)

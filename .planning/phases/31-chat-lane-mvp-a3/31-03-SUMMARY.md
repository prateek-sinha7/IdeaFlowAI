---
phase: 31-chat-lane-mvp-a3
plan: 03
subsystem: ui
tags: [react, typescript, vitest, chat, transcript, deep-link, open-design, apache-2.0]

# Dependency graph
requires:
  - phase: 29-chat-backbone
    provides: "chat frame vocabulary (chat_message/chat_reply/stream_attached) + {type,data:{event_id,seq}} envelope + RunConnectionProvider.subscribe/sendCommand up-channel"
  - phase: 31-chat-lane-mvp-a3 (plan 01)
    provides: "blocks.types ChatBlock/AgentEvent union (the render contract; this plan supplies the transcript/message contract beside it)"
provides:
  - "useRunChat — transport-agnostic, family-anchored (D-02) transcript hook: append-only accumulation over chat_message/chat_reply/stream_attached frames, event_id dedup, optimistic sendMessage reconciled by client message_id, SSE (sendCommand) OR legacy WS (legacyWsSend) up-channel"
  - "ChatMessage extended with OPTIONAL attachments/cardKind/deepLink/runId/threadId (non-breaking) + ChatAttachment (ND-10 payload-transient) + DeepLinkTarget"
  - "useTabDeepLink — nonce'd deep-link-into-tabs seam (borrow #6): requestOpenTab/consume single-use + re-triggerable"
affects: [31-04-chat-lane, 31-05-quick-actions, 31-06-attachments, 31-07-integration]

# Tech tracking
tech-stack:
  added: []  # ZERO new deps — react/@testing-library/react/vitest already present
  patterns:
    - "Transport-agnostic transcript reducer: the hook consumes a subscribe(fn) fan-out + a sendCommand up-channel, so the SAME transcript works under the Phase-29 SSE flag AND the flag-OFF legacy WS path (single backend channel)"
    - "Append-only accumulation with event_id dedup + optimistic-send reconciliation by client-minted message_id (strict-id reconcile, mismatched echo appends distinct — T-31-03-S)"
    - "Ref-canonical single-use nonce seam: consume() read-and-clears off a ref (independent of React state-flush timing); module-level monotonic nonce guarantees re-triggerability"

key-files:
  created:
    - frontend/src/hooks/useRunChat.ts
    - frontend/src/hooks/useRunChat.test.ts
    - frontend/src/hooks/useTabDeepLink.ts
    - frontend/src/hooks/useTabDeepLink.test.ts
  modified:
    - frontend/src/types/index.ts

key-decisions:
  - "ChatMessage extension is strictly ADDITIVE/OPTIONAL (attachments/cardKind/deepLink/runId/threadId) — the dead-kit MessageBubble/ChatPanel still compile (tsc-identity). Added runId/threadId beyond the plan's named three because family anchoring (D-02, behavior test 6) requires per-turn run/thread ids; still non-breaking."
  - "DeepLinkTarget maps the frame's deep_link {target,nonce} → {tab,nonce}: target is the generic string tab id. This is the STORED descriptor on the narrator message; the live navigation nonce is minted by useTabDeepLink when the card is clicked (two distinct concerns, both nonce-typed)."
  - "useTabDeepLink uses a module-level monotonic nonce + a ref-canonical pending target so consume() is synchronous read-and-clear (single-use) and two same-tab requests mint different nonces (re-triggerable). Generic string tab ids only (SC-001)."
  - "useWorkflow.ts deliberately NOT touched — the pipeline reducer (FIX-039 accumulator-reset ordering) is a separate concern; the transcript is its own hook."

patterns-established:
  - "frontend/src/hooks/useRunChat.ts as the canonical chat transcript contract downstream plans import (interface-first)"
  - "Ref-canonical single-use nonce seam (useTabDeepLink) as the deep-link-into-tabs pattern for result cards → Preview panel"

requirements-completed: [CHATUI-01]

# Metrics
duration: 3min
completed: 2026-07-08
---

# Phase 31 Plan 03: Chat Transcript DATA Layer (useRunChat / ChatMessage extension / useTabDeepLink) Summary

**The chat lane's data layer ships interface-first: `useRunChat` folds the Phase-29 chat frame vocabulary into an append-only, family-anchored (D-02) transcript transport-agnostically (SSE or legacy WS), `ChatMessage` gains non-breaking optional fields, and `useTabDeepLink` provides the single-use nonce'd deep-link seam (borrow #6) — 12 green vitest cases, tsc-identity, useWorkflow.ts untouched, zero backend/e2e change.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-08T08:40:23Z
- **Completed:** 2026-07-08T08:43:40Z
- **Tasks:** 2
- **Files modified:** 4 created + 1 modified

## Accomplishments
- `useRunChat.ts` — a transport-agnostic transcript reducer over the shared `{type, data:{event_id, seq}}` envelope. `chat_message` appends/reconciles a user turn keyed by `message_id`; `chat_reply` appends an assistant NARRATOR turn carrying generic `cardKind` + `deepLink`; `stream_attached` updates the handshake state WITHOUT touching the transcript. Frames dedupe by `event_id`; the transcript ACCUMULATES (a `pipeline_complete`/state-change frame never wipes a prior turn — LIVE-STATE-CONTRACT §0); a child run's frames stitch into the SAME array (family anchoring, D-02).
- `sendMessage(text, attachments?)` optimistically renders the user turn keyed on a client-minted `message_id`, sends it up-channel via `sendCommand` (SSE) OR `legacyWsSend` as a `user_message` frame (flag-OFF), and the later server echo with the SAME id reconciles in place — no duplicate bubble; a mismatched-id echo appends as a distinct turn (T-31-03-S).
- `ChatMessage` extended with OPTIONAL `attachments`/`cardKind`/`deepLink`/`runId`/`threadId` (non-breaking, tsc-identity) + new `ChatAttachment` (ND-10 payload-transient default `retained:false`) and `DeepLinkTarget` types.
- `useTabDeepLink.ts` — the nonce'd deep-link-into-tabs seam (borrow #6): `requestOpenTab(tab)` mints a fresh monotonic nonce; `consume()` read-and-clears the pending target (single-use, T-31-03-T); two same-tab requests mint DIFFERENT nonces so a repeat deep-link re-fires the consumer effect. Apache-2.0 attribution header; generic string tab ids only (SC-001).
- 12 green vitest cases (8 + 4); tsc-identity (zero new errors vs the `e2e/fixtures/mockApi.ts` baseline); SC-001 grep 0; INV-3 held; useWorkflow.ts untouched (FIX-039 preserved).

## Task Commits

Each task was committed atomically:

1. **Task 1: ChatMessage extension + useRunChat transcript reducer (D-02)** — `689536c5` (feat)
2. **Task 2: useTabDeepLink nonce'd deep-link seam (borrow #6)** — `9426ffb6` (feat)

**Plan metadata:** _(this docs commit)_

_Opportunistic TDD (`tdd_mode=false`): each task committed test + implementation together as one atomic unit (mirrors 31-02)._

## Files Created/Modified
- `frontend/src/types/index.ts` — extended `ChatMessage` (5 optional additive fields) + new `ChatAttachment` / `DeepLinkTarget` (modified)
- `frontend/src/hooks/useRunChat.ts` — family-anchored transcript state + `sendMessage` + frame projections (created)
- `frontend/src/hooks/useRunChat.test.ts` — 8 vitest cases (append user turn; narrator cardKind+deepLink; accumulate/no-wipe; event_id dedup; optimistic+reconcile+distinct-id; family anchoring; legacy WS path; stream_attached) (created)
- `frontend/src/hooks/useTabDeepLink.ts` — nonce'd deep-link seam (created)
- `frontend/src/hooks/useTabDeepLink.test.ts` — 4 vitest cases (fresh nonce; same-tab different nonces; single-use consume; stale-nonce no re-open) (created)

## Decisions Made
- **Added `runId`/`threadId` beyond the plan's named three optional fields:** family anchoring (D-02, behavior test 6) requires each turn to carry its run/thread ids so a child (revision) run's frames stitch into the same transcript array. Still strictly additive/optional — existing consumers ignore them, tsc-identity holds.
- **`DeepLinkTarget` on the message is a STORED descriptor, distinct from the live navigation nonce:** `useRunChat` maps the frame's `deep_link {target,nonce}` → `{tab,nonce}` for display; the card, when clicked, calls `useTabDeepLink.requestOpenTab(tab)` which mints the ACTUAL single-use navigation nonce. Two nonce-typed concerns, cleanly separated.
- **`useTabDeepLink` is ref-canonical:** `consume()` reads-and-clears off a ref so it is synchronous regardless of React's state-flush timing (the state mirror only drives the consumer `useEffect`). A module-level monotonic counter guarantees every request — across every hook instance — gets a strictly-increasing unique nonce (re-triggerability).

## Deviations from Plan

None - plan executed exactly as written. (The additive `runId`/`threadId` fields are within the plan's non-breaking-extension posture and required by its own family-anchoring behavior test — recorded above as a decision, not a deviation.)

## Issues Encountered
None.

## Deferred / Follow-ups
- **Live transport wiring is out of scope (interface-first):** `useRunChat` exposes a stable contract but is NOT yet mounted against the live `RunConnectionProvider` — that integration is plan 31-07. Downstream plans (04 lane, 05 quick-actions, 06 attachments) import these pinned contracts.
- **THIRD-PARTY-NOTICES.md borrow #6 local-path cell:** the module carries the `Adapted from nexu-io/open-design (Apache-2.0)` header (attribution satisfied); finalizing the table's concrete local-path cell is folded into plan 04 (same deferral posture as 31-02's #3/#5/#7).

## User Setup Required
None - no external service configuration required. Zero new npm dependencies.

## Known Stubs
None — both hooks are fully functional against the frame/transport contract. Live-transport MOUNTING (not stubbing) is the deferred 31-07 integration; the data-layer logic is complete and test-proven.

## Next Phase Readiness
- `useRunChat` / `ChatMessage` / `useTabDeepLink` are stable, importable contracts for 31-04 (the chat lane composition), 31-05 (quick-actions), 31-06 (attachments), and 31-07 (live integration).
- Verified offline: `vitest run src/hooks/useRunChat.test.ts src/hooks/useTabDeepLink.test.ts` → 12/12 green; `tsc --noEmit` identity (0 new errors beyond the known `e2e/fixtures/mockApi.ts` baseline); SC-001 grep 0; INV-3 held (no backend / golden / e2e-spec touched); useWorkflow.ts untouched (FIX-039 preserved).

## Self-Check: PASSED

---
*Phase: 31-chat-lane-mvp-a3*
*Completed: 2026-07-08*

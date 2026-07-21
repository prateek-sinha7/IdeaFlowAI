---
phase: 260716-dhr
plan: 01
subsystem: frontend/run-screen
tags: [DEF-44-12-4, DEF-44-12-2, DEF-44-12-1, run-binding, sse, concierge]
requires:
  - GET /api/runs/{id}/events (existing owner-scoped durable endpoint — no change)
provides:
  - getRunEvents durable-events fetch helper
  - Steps trace + runInput seed on history-open
  - Concierge reply render via re-fetch-after-send + event_id de-collision
  - imperative seedTranscript for prior chat on open
  - shared openHistory/openRecent/stubRunEvents e2e helpers + ts-live-state coverage
affects:
  - frontend/src/lib/api.ts
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/hooks/useRunChat.ts
key-files:
  created:
    - frontend/e2e/tests/ts-live-state.spec.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/hooks/useRunChat.ts
    - frontend/src/hooks/useRunChat.test.ts
    - frontend/e2e/fixtures/dashboard.ts
    - frontend/e2e/fixtures/test.ts
decisions:
  - Seed trigger is the Home "Jump back in" recents (onOpenRun→handleSelectWorkflowRun), NOT the Run History list (which renders WorkflowHistory's own RunDetailPage and never calls handleSelectWorkflowRun)
  - DashboardLayout.tsx left untouched — the minimal setSubmittedBrief set sufficed (runInput={submittedBrief} already threads it)
  - Piece 3 SHIPPED (not deferred) as a separate atomic commit
metrics:
  tasks: 5
  commits: 6
  duration: ~35m
  completed: 2026-07-16
---

# Phase 260716-dhr Plan 01: Bind run-screen live state to the viewed run — Summary

Bound the run-screen's two live consumers — the Steps pipeline trace (from `useWorkflow`) and the `useRunChat` transcript — to the run the user is VIEWING, not only the run they launched in-session, by seeding both from the durable `GET /api/runs/{id}/events` rows on history-open and re-fetching after a Concierge send. Closes DEF-44-12-4 (empty Steps trace on an opened running run) and subsumes DEF-44-12-2 (Concierge reply not rendering) + the missing DEF-44-12-1 e2e. Frontend-only; no backend/engine/queue change.

## What shipped (3 pieces over one shared primitive)

- **Shared primitive — `getRunEvents(token, runId, afterSeq=0)`** (`api.ts`): hits the read-only durable endpoint, maps each row to a `{ type, data: payload_json }` frame, tolerates a missing/empty `events` array (mock `{}` → `[]`), no normalization (consumers dedup by `event_id`).
- **Piece 1 — Steps trace + runInput seed** (`page.tsx` `handleSelectWorkflowRun`): when the opened run differs from the live launched run, reset replay state + reducer, fetch the durable events, replay each through the page router (`handleWebSocketMessage`) so each `event_id` lands in `seenEventIdsRef` (the later-attached live tail is deduped), and set `submittedBrief` to the viewed run's input. Hard-guarded on `fullRun.id !== pipelineState.pipelineRunId` so the live launched run is never re-seeded. `useCallback` deps updated.
- **Piece 2 — Concierge reply render** (`useRunChat.ts` + `page.tsx`): key the assistant bubble on the distinct `data.event_id` (`chat-reply:{id}`) so a reply carrying `message_id === the user turn's id` appends as its own turn instead of overwriting the question (the landmine). Added optional `fetchEvents` + a per-hook `lastSeq` cursor; `sendMessage` awaits the up-channel then re-fetches events since the last seq and folds each through `handleFrame` (idempotent by `event_id`), covering both terminal and live opened runs with no backend queue-put. Page wires `fetchEvents` to `getRunEvents`.
- **Piece 3 — prior-transcript seed** (`useRunChat.ts` + `page.tsx`): imperative `seedTranscript(frames)` clears the seen-set + seq cursor, resets `messages`, folds each frame through `handleFrame`. Fired ONLY from the deliberate history-open with the SAME once-fetched events, so a live revision (which never calls it) keeps accumulating — family anchoring preserved. Separate atomic commit for independent revertability.

## Real baseline (the "132/0" figure is STALE — established by running)

| Suite | Baseline (pre-edit) | After |
|-------|--------------------|-------|
| Playwright (mocked): ts-j.streaming, ts-sse, ts-sse-resilience, ts-s.reconnect, ts-chat, ts-chat-cards, ts-t.history, ts-u.revisions | **34 passed, 6 skipped** | **37 passed, 6 skipped** (+3 new ts-live-state) |
| Vitest: useRunChat, useWorkflow.clarifyRetention, useWorkflow.reconnect, RunChatLane, revisionFamilyLinkage.source, AgentThinkingTab | **64 passed (6 files)** | **66 passed (6 files)** (+2 new de-collision/re-fetch cases) |

Every previously-green spec stayed green; the 6 skips are unchanged (pre-existing `test.fixme` in ts-u.revisions). `npx tsc --noEmit` → **clean** at every task.

## New tests

- **vitest** (`useRunChat.test.ts`): Test 12 (a `chat_reply` keyed on a distinct `event_id` appends as its own turn, question preserved) and Test 13 (`sendMessage` re-fetches after the up-channel and folds the reply idempotently). Both seen RED (message-id overwrite / `fetchEvents` unwired) before GREEN.
- **playwright** (`ts-live-state.spec.ts`, all 3 PASS): (a) live-open renders the Steps trace not the "Start a pipeline…" placeholder; (b) terminal-open renders the deliverable + prior chat + a Concierge reply that renders as its OWN turn with a recorded `POST /api/runs/{id}/messages`; (c) launch→watch renders the launched run's live trace unchanged.

## At-risk tests — all GREEN, tokens intact (none changed)

- `ts-u.revisions.spec.ts:86` (`parent_run_id === on-screen run`) — green; `page.tsx:496` launched→`contentSourceRunId` untouched.
- `revisionFamilyLinkage.source.test.ts` — green; the literal `postRevision(getToken() ?? "", contentSourceRunId,` and `contentSourceRunId={contentSourceRunId}` source tokens are verbatim (source-scan passed).
- `useRunChat.test.ts:140-143` (Test 5 send routing) and Test 6 (family anchoring) — green; `sendMessage` still returns the client id synchronously and routes to the hook's `runId`.

## Deviations from Plan

**1. [Rule 1 — make it actually work] Seed trigger is Home recents, not the Run History list.**
- **Found during:** Task 5.
- **Issue:** The plan's Task 5 instructed opening a run via `openHistory` (the Run History LIST) for coverage. Verified in source that the list-row reopen renders WorkflowHistory's OWN internal `RunDetailPage` (`WorkflowHistory.tsx` `setSelectedRun`) and does NOT call `page.tsx`'s `handleSelectWorkflowRun` — so it never seeds the execution-lane pipeline/transcript. The ONLY caller of `handleSelectWorkflowRun` is the Home "Jump back in" recents (`DashboardLayout.tsx:1475` `onOpenRun` → `onSelectWorkflowRun` → `setMainView("execution")`).
- **Fix:** Added an `openRecent(title)` helper (the real seed-path deep-link) and used it for cases (a)/(b). Still lifted `openHistory` into the shared fixture as the plan requested (removes duplication; genuinely shared). Also added `openRecent`/`stubRunEvents` to the shared page object.
- **Files:** `frontend/e2e/fixtures/dashboard.ts`, `frontend/e2e/fixtures/test.ts` (re-export `StubRunEventRow`).
- **Commit:** 8f7d9e9b.

**2. [Scope-minimal] DashboardLayout.tsx not touched.**
- **Found during:** Task 2.
- **Issue:** Task 2 listed `DashboardLayout.tsx` as a possible file for the `runInput` thread.
- **Fix:** Per the plan's own guidance ("prefer the minimal `setSubmittedBrief` set… Do NOT change the `runInput` prop wiring in DashboardLayout unless a cleaner viewed-input thread is warranted"), the minimal `setSubmittedBrief(fullRun.input ?? "")` sufficed — `DashboardLayout.tsx:1798` already threads `runInput={submittedBrief}`. No SC-001 concern (no literal added). DashboardLayout left untouched.

## Piece 3 status

**SHIPPED** (commit 8b49634f) — not deferred. Kept as its own atomic commit for independent revertability; family-anchoring Test 6 + RunChatLane vitest stayed green, and the (b) e2e proves the prior transcript renders on open.

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | 396ae3db | feat(frontend): add getRunEvents durable-events fetch helper (DEF-44-12-4) |
| 2 (Piece 1) | 349e5038 | fix(frontend): seed the Steps trace + runInput on history-open (DEF-44-12-4 Piece 1) |
| 3 RED | 294ecffc | test(frontend): add failing de-collision + re-fetch-after-send cases (DEF-44-12-2) |
| 3 GREEN (Piece 2) | b784f412 | feat(frontend): render the Concierge reply on an opened run (DEF-44-12-2 Piece 2) |
| 4 (Piece 3) | 8b49634f | feat(frontend): seed the prior transcript on history-open (DEF-44-12-4 Piece 3) |
| 5 | 8f7d9e9b | test(frontend): add ts-live-state coverage + shared history-open helpers (DEF-44-12-4) |

## Known Stubs

None — no placeholder/empty-value stubs introduced. `getRunEvents`'s `events ?? []` tolerance is intentional defensive handling of the mock catch-all `{}`, documented in the helper.

## Live proof

Deferred to the ORCHESTRATOR (per constraints — the executor does NOT run a live Bedrock run). Offline evidence: tsc clean, 37/6 playwright, 66 vitest, 3 new e2e cases green.

## Self-Check: PASSED
- All 6 key files present on disk.
- All 6 commits present in git history.
- Working tree clean (docs uncommitted per constraints — orchestrator commits them).

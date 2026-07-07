---
phase: 29-transport-cutover-chat-backbone-a1
plan: 06
subsystem: testing
tags: [playwright, e2e, sse, websocket, mock, transport, chat, test-harness]

# Dependency graph
requires:
  - phase: 28-chat-contracts-guards-a0
    provides: MOCKWS-CHAT-DRIVER-CONTRACT.md (RUNUI-05 additive chat-driver surface; POR D-01 chat frames; LOCK-B additive transport)
provides:
  - "mockSse.ts — a mock-SSE transport driver (route GET /api/runs/{id}/events/stream, id:{seq} frames, Last-Event-ID replay, drop/reattach)"
  - "Additive chat driver methods on MockWs (chatMessage/chatReply/streamAttached/waitForChatCommand)"
  - "Shared monotonic seq/event_id source exposed from mockWs.ts (SeqSource + exported nextEventId) so SSE + WS frames ride ONE sequence"
  - "ts-sse.spec.ts smoke — attach → replay-from-cursor → drop → reattach, dedup-by-event_id + resume-by-seq"
affects: [29-07 FE transport adapter, 29-08 chat backbone, Phase 31/32 chat-lane specs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive test-harness extension: new SSE driver + chat helpers alongside the existing MockWs, ONE seq/event_id space, no WS route removed (LOCK-B)"
    - "Mock-SSE via page.route fulfilling a text/event-stream body; Last-Event-ID header → replay-from-cursor (frames with seq > cursor)"
    - "Consumer-modeled smoke: dedup by data.event_id + resume by data.seq mimics the future 29-07 transport adapter without touching useWebSocket.ts"

key-files:
  created:
    - frontend/e2e/fixtures/mockSse.ts
    - frontend/e2e/tests/ts-sse.spec.ts
  modified:
    - frontend/e2e/fixtures/mockWs.ts

key-decisions:
  - "SSE `id:` line == the shared `seq` cursor; `data.event_id` remains the dedup key — same split the WS handler uses today"
  - "mockSse shares the MockWs SeqSource (nextSeq/currentSeq) + exported nextEventId() — no second seq counter, no second envelope"
  - "Smoke drives a modeled fetch consumer (not the live app) because LOCK-B forbids touching useWebSocket.ts and the FE SSE consumer lands in 29-07"
  - "streamAttached added beside pipeline_reconnected (both kept); mockSse route is additive to the WS route path"

patterns-established:
  - "Pattern: transport driver shares the controller's monotonic sequence via a small SeqSource interface rather than duplicating counters"
  - "Pattern: replay-from-cursor honors Last-Event-ID and returns only frames with seq strictly greater than the cursor"

requirements-completed: [CHAT-07]

# Metrics
duration: 35min
completed: 2026-07-07
---

# Phase 29 Plan 06: Mock-SSE Transport Driver + Additive Chat Driver Summary

**A mock-SSE transport driver (`mockSse.ts`) + additive `chatMessage`/`chatReply`/`streamAttached`/`waitForChatCommand` helpers on `MockWs`, riding ONE shared monotonic seq/event_id space, with an `ts-sse` smoke proving attach → replay-from-cursor → drop → reattach (dedup-by-event_id, resume-by-seq) — `useWebSocket.ts` untouched (LOCK-B).**

## Performance

- **Duration:** ~35 min (majority spent diagnosing a pre-existing `feat/ui-2` suite breakage, not implementation)
- **Started:** 2026-07-07T22:08:00Z
- **Completed:** 2026-07-07T22:43:02Z
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- **mockSse.ts** — intercepts `GET /api/runs/{id}/events/stream` via `page.route`, serves a `text/event-stream` body (`id:{seq}` / `event:{type}` / `data:{json}`), honors the `Last-Event-ID` request header for replay-from-cursor, and supports `drop()`/reattach. It shares the `MockWs` `SeqSource` so SSE frames interleave with pipeline frames on ONE monotonic sequence.
- **MockWs chat driver (additive)** — `chatMessage({messageId,text,attachments?})`, `chatReply({cardKind,text,deepLink?,messageId?})`, `streamAttached({live,replayedThroughSeq?})` (defaults `replayedThroughSeq` to current seq, mirroring `reconnected()`), and `waitForChatCommand(predicate?)` reusing the existing `sent[]`/`waiters` machinery. All ride the existing `emit()`/envelope, the ONE `seq` counter, and the ONE `event_id` space.
- **Shared sequence source** — exported `nextEventId()` (module-level `GLOBAL_EVENT_ID`) + a `SeqSource` interface (`nextSeq()`/`currentSeq`) that `MockWs` implements; `mockSse` consumes it. No second envelope, no second seq space.
- **ts-sse.spec.ts** — a 2-test smoke driving `mockSse` through attach → replay-from-cursor → drop → reattach, asserting a consumer dedups by `data.event_id` and resumes its cursor from `data.seq`, plus `mockWs.currentSeq` proving ONE shared counter. Both pass (2/2, ~1.7s).

## Task Commits

Each task was committed atomically:

1. **Task 1: Additive chat driver methods on MockWs** — `6c5de02a` (feat)
2. **Task 2: mockSse.ts transport driver (attach/replay/drop)** — `0f0e3856` (feat)
3. **Task 3: ts-sse smoke spec** — `6898cb92` (test)

**Plan metadata:** _(final docs commit — see git log)_

## Files Created/Modified

- `frontend/e2e/fixtures/mockSse.ts` (created) — mock-SSE transport driver: SSE route, `id:{seq}` framing, `Last-Event-ID` replay-from-cursor, `drop()`/reattach, chat convenience emitters, shared `SeqSource`.
- `frontend/e2e/fixtures/mockWs.ts` (modified, purely additive) — exported `nextEventId()` + `SeqSource` interface; `MockWs implements SeqSource` with `nextSeq()`/`currentSeq`; the three chat frame helpers + `waitForChatCommand`. Existing helper bodies byte-identical; `pipeline_reconnected`/`reconnected()` kept.
- `frontend/e2e/tests/ts-sse.spec.ts` (created) — the SSE-driver smoke (TS-SSE-01/02).

## LOCK-B Confirmation (required)

`git diff --name-only` for this plan's code commits (`6c5de02a~1..HEAD`, frontend only):

```
frontend/e2e/fixtures/mockSse.ts
frontend/e2e/fixtures/mockWs.ts
frontend/e2e/tests/ts-sse.spec.ts
```

- All changed files are within the plan's `files_modified` allow-list. ✅
- `frontend/src/hooks/useWebSocket.ts` is **NOT** in the diff (`git diff --name-only | grep useWebSocket` → empty). ✅
- `pipeline_reconnected` is **still present** in `mockWs.ts` (grep → 4 occurrences, incl. the `reconnected()` emit at line 282). ✅
- `stream_attached` added **beside** it (grep → 2 occurrences); no existing MockWs helper renamed/removed. ✅
- ONE monotonic seq/event_id space: `mockSse` uses `MockWs.nextSeq()` + exported `nextEventId()`; no second envelope, no second seq counter. ✅

## Verification

- `cd frontend && npx tsc --noEmit -p tsconfig.json` → **clean** (exit 0), after each task.
- `cd frontend && npx playwright test --project=mocked e2e/tests/ts-sse.spec.ts` → **2 passed** (TS-SSE-01, TS-SSE-02), ~1.7s, fully offline.
- Full `--project=mocked` suite ("123 green" bar): **DEFERRED** — see Issues Encountered. The baseline is already red on `feat/ui-2` for reasons independent of this plan; correctness of the additive driver is proven via tsc + the targeted `ts-sse` run per the OFFLINE VERIFICATION DISCIPLINE fallback.

## Decisions Made

- **Modeled consumer in the smoke, not the live app.** LOCK-B forbids touching `useWebSocket.ts`, and the FE SSE consumer lands in 29-07, so `ts-sse` drives a minimal in-page `fetch` consumer that mimics the exact dedup-by-`data.event_id` + resume-by-`data.seq` contract the WS handler uses today. This proves the driver end-to-end through the real browser network layer without any app change.
- **`id:` == `seq`, `data.event_id` == dedup key.** Matches the existing WS envelope split (mockWs header) so a future adapter reuses one code path.
- **ACAO header on the SSE fulfill + same-origin relative fetch** in the smoke to keep the cross-transport round-trip robust and CORS-free.

## Deviations from Plan

None — plan executed exactly as written (3 tasks, 3 atomic commits, additive-only). The mockWs edit is purely additive; no existing helper signature/behavior changed.

## Issues Encountered

**Full mocked-suite "123 green" bar is unmeetable on `feat/ui-2` (pre-existing, out-of-scope).**
The full `--project=mocked` run shows ~120/123 specs timing out at 45s on **home-render** assertions (e.g. `getByRole('button', { name: /Generate product requirements/i })` → not found). Root cause: the `feat/ui-2` branch **redesigned the dashboard home** — the current home renders a new nav (`Home / Library / Catalogue / Notifications`) + a `Create workflow` button, and the legacy text-labelled CreationHub rows the 123 specs target no longer exist (confirmed via the Playwright accessibility snapshot; responsible commits `9c7b78bb`, `fe7a351b`/KAN-78).

This is **independent of 29-06**: the plan's entire diff is 3 e2e files with **zero `frontend/src/` app code**; the failing assertions render **before any WS/SSE interaction** (`TS-B-07` fails on a pure home check with no WS/SSE involvement); the mockWs edit is byte-identical for existing helpers; and 29-06's own `ts-sse.spec.ts` passes 2/2 with a healthy `dashboard.goto()`/`ws.ready()`. Per the SCOPE BOUNDARY + OFFLINE VERIFICATION DISCIPLINE I did **not** fabricate a pass and did **not** fix unrelated app code (also outside the 3-file allow-list). Logged in full to `deferred-items.md` (DEF-29-06-1). Owner: the `feat/ui-2` UI-convergence workstream must realign the mocked specs (and likely the `mockApi` workflow-catalogue stub) with the redesigned home.

## Known Stubs

None — no placeholder data or unwired components introduced. `mockSse` is a fully-functional test driver; `ts-sse` exercises real behavior.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **29-07 (FE transport adapter)** can now script SSE attach/replay/drop and outbound chat-command assertions against `mockSse` + the MockWs chat helpers, on one monotonic seq/event_id space.
- **Blocker for the broader Phase-29 e2e story:** the mocked spec suite must be realigned to the `feat/ui-2` redesigned home before the "keep the 123 green" acceptance bar can be exercised (DEF-29-06-1). This is a `feat/ui-2` workstream task, not a 29-06 regression.

## Self-Check: PASSED

- `frontend/e2e/fixtures/mockSse.ts` — FOUND
- `frontend/e2e/fixtures/mockWs.ts` — FOUND (modified)
- `frontend/e2e/tests/ts-sse.spec.ts` — FOUND
- Commit `6c5de02a` — FOUND
- Commit `0f0e3856` — FOUND
- Commit `6898cb92` — FOUND

---
*Phase: 29-transport-cutover-chat-backbone-a1*
*Completed: 2026-07-07*

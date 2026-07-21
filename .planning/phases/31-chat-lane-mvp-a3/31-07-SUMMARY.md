---
phase: 31-chat-lane-mvp-a3
plan: 07
subsystem: ui
tags: [react, chat, integration, sse, websocket, deep-link, aria-live, sc-001, lock-b, fix-039, delta-verify]

# Dependency graph
requires:
  - phase: 31-chat-lane-mvp-a3 (plan 03)
    provides: "useRunChat transport-agnostic transcript + useTabDeepLink nonce'd seam (borrow #6)"
  - phase: 31-chat-lane-mvp-a3 (plan 04)
    provides: "RunChatLane composition root (D-12 composer + absorbed controls) + ResultCard"
  - phase: 29-chat-backbone
    provides: "RunConnectionProvider.subscribe/sendCommand (SSE) + the Phase-29 chat frame vocabulary + mock chat driver (29-06)"
provides:
  - "The RunChatLane mounted LIVE in the execution-surface left column, fed the family-anchored transcript from useRunChat wired to whichever transport is active (SSE flag ON = RunConnectionProvider.subscribe/sendCommand; flag OFF = legacy WS chat frames + user_message send) — SAME transcript either way"
  - "PreviewPanel as the nonce'd deep-link CONSUMER for ALL panel tabs (was preview/files only) — a result-card click opens the target tab exactly once"
  - "The codebase's first data-testid-driven chat e2e specs (ts-chat + ts-chat-cards), DELTA-verified against the pre-existing feat/ui-2 baseline"
affects: [chat-lane, run-screen, 32-reskin, 33-concierge]

# Tech tracking
tech-stack:
  added: []  # ZERO new deps — composes already-committed 31-03/04 pieces + Phase-29 transport
  patterns:
    - "Transport-agnostic transcript feed: page.tsx selects subscribe/sendCommand (SSE, when RunConnectionProvider is mounted+enabled) vs a local WS chat-frame fan-out + legacy user_message send (flag OFF) — one useRunChat, one transcript"
    - "Additive WS chat-frame routing: chat_message/chat_reply/stream_attached are dispatched from handleWebSocketMessage into the transcript fan-out; those frame types were previously unhandled (no-op) so the legacy path stays byte-identical (LOCK-B)"
    - "Nonce'd deep-link consumer: PreviewPanel switches tabs on an effect keyed on deepLinkTarget.nonce (monotonic) for all generic PanelTab ids; a non-panel target (e.g. 'steps') is ignored"
    - "Control absorption: the lane owns Stop/revise/suggestions + gate/clarify quick-actions; AgentProgressPanel is retained (Phase 32 relocates it) but demoted and stripped of those controls"

key-files:
  created:
    - frontend/e2e/tests/ts-chat.spec.ts
    - frontend/e2e/tests/ts-chat-cards.spec.ts
  modified:
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/preview/PreviewPanel.tsx

key-decisions:
  - "Gate on runConnection.enabled (flag AND provider-mounted), not ENV.SSE_TRANSPORT alone. The RunConnectionProvider is NOT mounted today, so enabled === false → the legacy WS path is the ACTIVE transport (byte-identical, LOCK-B). A future mount with the flag ON activates the SSE path with ZERO change here."
  - "Widen msg.type to string for the additive chat-frame membership test (the StreamMessage union in types/index.ts does not enumerate the Phase-29 frame names, and types/index.ts is out of scope / INV-3). No type edit."
  - "Reach the execution view in the e2e specs via pipeline_start (isRunning → DashboardLayout auto-switches), NOT the home CreationHub — whose text locators are RED in the feat/ui-2 baseline (DEF-29-06-1). This isolates the new specs from the pre-existing home breakage."
  - "runState is derived in DashboardLayout from the GENERIC signals it already owns (reviewGateData / questionnaireQuestions / pipelineState) — gate > clarify > building > terminal > complete > idle — never a workflow name (SC-001)."

patterns-established:
  - "page.tsx owns the transport selection + useRunChat/useTabDeepLink instantiation; DashboardLayout mounts + wires the lane; PreviewPanel consumes the deep-link seam"
  - "data-testid-driven mocked chat specs that survive the Phase-32 reskin"

requirements-completed: [CHATUI-01, CHATUI-02, CHATUI-03]

# Metrics
duration: 14min
completed: 2026-07-08
---

# Phase 31 Plan 07: Chat Lane Live Integration Summary

**The RunChatLane is now LIVE in the run screen: mounted in the execution left column, fed a family-anchored transcript by `useRunChat` wired transport-agnostically (SSE `RunConnectionProvider.subscribe`/`sendCommand` when the provider is mounted+enabled; the legacy WS chat frames + `user_message` send when OFF — SAME transcript either way, flag-OFF byte-identical LOCK-B), absorbing the AgentProgressPanel Stop/revise/suggestions controls plus the plan-05 gate/clarify quick-actions, and deep-linking into `PreviewPanel` tabs via the nonce'd seam (now honoring ALL tabs). Proven by two new data-testid-driven mocked chat specs (7 tests) verified BY DELTA — new pass, zero green→red regression against the pre-existing feat/ui-2 baseline — with tsc-identity, FIX-039 preserved, and `useWorkflow.ts`/`useWebSocket.ts` untouched.**

## Performance
- **Duration:** ~14 min
- **Started:** 2026-07-08T11:18:26Z
- **Completed:** 2026-07-08T11:32:48Z
- **Tasks:** 3 (each committed atomically)
- **Files:** 3 modified + 2 created

## Accomplishments
- **Task 1 — transport-agnostic transcript + deep-link consumer (`c2bb8d6b`).** `page.tsx` instantiates `useRunChat({ runId: activePipelineRunId, subscribe, sendCommand, legacyWsSend })` and the `useTabDeepLink` seam. `subscribe`/`sendCommand` come from `RunConnectionProvider` when the SSE transport is enabled; otherwise a local pub-sub (`chatFrameListenersRef`) fed by an ADDITIVE branch in `handleWebSocketMessage` that routes the Phase-29 chat frames (`chat_message`/`chat_reply`/`stream_attached`) into `useRunChat`, and `legacyWsSend` emits the legacy `user_message` WS frame. Those three frame types were previously unhandled (no-op), so the legacy path stays byte-identical (LOCK-B); `useWorkflow.ts` (FIX-039) and `useWebSocket.ts` are untouched. `PreviewPanel` became the nonce'd deep-link CONSUMER for ALL panel tabs (preview/files/thinking/audit), via an effect keyed on `deepLinkTarget.nonce` (was `initialTab` preview/files only).
- **Task 2 — mount RunChatLane (`368bc522`).** The lane is the primary left-column surface (`data-testid="execution-chat-lane"`), fed `messages`/`sendMessage`/`onRequestOpenTab` + the derived GENERIC `runState` (D-12; gate > clarify > building > terminal > complete > idle, SC-001). It ABSORBS the AgentProgressPanel Stop/revise/suggestions controls (wired to the existing cancel/revise/chain callbacks) and mounts the plan-05 gate & clarify quick-actions (approve/reject/redo/update_specs + submit_questionnaire). AgentProgressPanel is RETAINED (not deleted — Phase 32 relocates it into Steps) as a demoted, controls-stripped per-agent region; WaveTreePanel kept. Current skin (D-15).
- **Task 3 — mocked chat e2e specs, DELTA-verified (`e9b601c7`).** `ts-chat.spec.ts` (4 tests): send→outbound command + optimistic echo reconcile (no dupe); transcript `role=log` + `aria-live=polite` + narrator markdown; gate quick-actions (Approve fires `approve_review`, a terminal event hides the actions — KAN-100 fence); clarify chips submit `submit_questionnaire`. `ts-chat-cards.spec.ts` (3 tests): `deliverable` card labeled **"Deliverable"** (LOCK-F) + deep-link switches the Preview tab (nonce seam); `spec_revision` card reads **"Revising spec — cycle 1"** (KAN-101); a picked file renders a `chat-attach-chip`. Both drive the EXISTING mockWs chat driver (Phase 29-06) — no driver rewrite.

## Task Commits
1. **Task 1: wire useRunChat transport-agnostically + deep-link consumer** — `c2bb8d6b` (feat)
2. **Task 2: mount RunChatLane in the execution left column** — `368bc522` (feat)
3. **Task 3: mocked chat-lane e2e specs (DELTA-verified)** — `e9b601c7` (test)

## Verification Evidence (offline / mocked)

### tsc-identity (IDENTITY gate)
- `npx tsc --noEmit` (excluding the known `e2e/fixtures/mockApi.ts` baseline) → **0 new `error TS`** after each task (baseline was 0). Held including the two new specs.

### Invariant guards
- **FIX-039:** `git diff --name-only | grep -x frontend/src/hooks/useWorkflow.ts` → **empty** (untouched — the accumulator-reset ordering is preserved by construction).
- **LOCK-B:** `frontend/src/hooks/useWebSocket.ts` NOT in the diff; no `/ws/chat` handler edit; the flag-OFF legacy path is byte-identical (the routed chat frames were previously unhandled no-ops).
- **INV-3:** no backend file, no golden fixture, no other e2e spec, no mock driver edited.
- **a11y:** `ChatPanel` `role="log"` + `aria-live` untouched (not in the diff); asserted live in TS-CHAT-02.
- **SC-001:** the mounted lane keys on the generic `RunLaneState`; the deep-link consumer keys on generic `PanelTab` ids; `RunChatLane.tsx` workflow-name grep = 0. (`PreviewPanel.tsx`'s pre-existing 19 workflow-name references are the untouched generic-deliverable render-branch logic, not part of this plan's deep-link addition.)

### DELTA verification (the phase crux — verify by delta, not absolute-green)
- **New specs PASS:** `npx playwright test --project=mocked e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts` → **7 passed / 0 failed** (4 + 3).
- **No previously-green regressed:** `npx playwright test --project=mocked` on the 5 canonical baseline-green files (ts-a.auth, ts-sse-resilience, ts-sse, ts-t.history, ts-x.timing) → **12 passed / 9 failed / 1 skipped**. The **12 passed == all 12 baseline-green tests** (TS-A-01/02, TS-SSE-RESILIENCE-01..04, TS-SSE-01/02, TS-T-01/02/06, TS-X-01) — **ZERO green→red regression**. The 9 failures every one die at `DashboardPage.selectWorkflow`/`runWith` on the home CreationHub, which is red in the pre-existing feat/ui-2 baseline (DEF-29-06-1) — home-screen code this plan never touched; they are members of the pre-existing 128-red set, not new breakage.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Widen `msg.type` to string for the additive chat-frame test**
- **Found during:** Task 1 (first tsc run)
- **Issue:** `msg.type === "chat_message"` (etc.) tripped TS2367 — the `StreamMessage.type` union in `types/index.ts` does not enumerate the additive Phase-29 chat frame names.
- **Fix:** `const frameType = msg.type as string;` for the membership test — `types/index.ts` is out of scope (INV-3) and the union is intentionally unchanged (LOCK-B).
- **Files modified:** frontend/src/app/dashboard/page.tsx
- **Committed in:** `c2bb8d6b` (Task 1 commit)

**2. [Rule 3 - Blocking] Reach the execution view without the broken home CreationHub in the e2e specs**
- **Found during:** Task 3 (first spec run — all 7 failed at `selectWorkflow("Generate product requirements")`)
- **Issue:** The plan's natural `runWith` path selects a workflow from the home screen, whose text locators are RED in the feat/ui-2 baseline (DEF-29-06-1) — a pre-existing breakage, not a lane bug.
- **Fix:** Drive the specs to the execution view via `mockWs.start(...)` (a `pipeline_start` flips `isRunning` → DashboardLayout auto-switches to execution and mounts the lane). This isolates the new specs from the pre-existing home red and is transport-independent.
- **Files modified:** frontend/e2e/tests/ts-chat.spec.ts, frontend/e2e/tests/ts-chat-cards.spec.ts
- **Committed in:** `e9b601c7` (Task 3 commit)

**Total deviations:** 2 auto-fixed (both Rule-3 blocking). No scope creep — same files, same behavior; both are mechanical unblocks for a type-union gap and a pre-existing baseline breakage.

## Authentication Gates
None — fully offline / mocked. No live backend or Bedrock invoked.

## Known Stubs
None. The integration is real and end-to-end proven: the transcript is fed by the active transport, the deep-link seam switches real PreviewPanel tabs, and the absorbed controls fire the real run commands (asserted in the mocked e2e specs). The SSE branch is dormant only because `RunConnectionProvider` is not yet mounted (an intentional deferral — the flag-OFF legacy path is the active, byte-identical transport per LOCK-B); mounting the provider is a future integration, not a stub here.

## Deferred / Follow-ups
- **RunConnectionProvider mount (SSE activation):** the SSE subscribe/sendCommand branch is wired but dormant until the provider is mounted above the router with the flag ON (out of this plan's 3-file scope; the flag-OFF path is the active transport today).
- **Live end-to-end (streaming SSE, multimodal send):** remains milestone-end live-deferred (DEF-29-09-1 — needs the live-ectx registry), unchanged by this FE-only plan.
- **Absolute-green e2e:** out of scope (the feat/ui-2 baseline is pre-existing red, DEF-29-06-1) — the home CreationHub spec realignment is owned by the feat/ui-2 task; delta-verify only.

## Self-Check: PASSED

- Created files present: `frontend/e2e/tests/ts-chat.spec.ts` ✓, `frontend/e2e/tests/ts-chat-cards.spec.ts` ✓.
- Modified files carry the changes: `page.tsx` (useRunChat/useTabDeepLink + additive frame routing) ✓, `DashboardLayout.tsx` (RunChatLane mount + absorbed controls) ✓, `PreviewPanel.tsx` (deep-link consumer) ✓.
- Commits present in history: `c2bb8d6b` ✓, `368bc522` ✓, `e9b601c7` ✓.
- Gates: tsc identity 0 new; FIX-039/LOCK-B/INV-3 guards clean; 7 new tests pass; 12 baseline-green tests still green (0 regressions).

---
*Phase: 31-chat-lane-mvp-a3*
*Completed: 2026-07-08*

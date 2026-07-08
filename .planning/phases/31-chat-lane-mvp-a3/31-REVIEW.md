---
phase: 31-chat-lane-mvp-a3
reviewed: 2026-07-08T00:00:00Z
depth: deep
files_reviewed: 41
files_reviewed_list:
  - frontend/NOTICE
  - frontend/THIRD-PARTY-NOTICES.md
  - frontend/e2e/tests/ts-chat-cards.spec.ts
  - frontend/e2e/tests/ts-chat.spec.ts
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/chat/ChatAttachments.test.tsx
  - frontend/src/components/chat/ChatAttachments.tsx
  - frontend/src/components/chat/ChatPanel.tsx
  - frontend/src/components/chat/ChatTokenWidget.test.tsx
  - frontend/src/components/chat/ChatTokenWidget.tsx
  - frontend/src/components/chat/InlineClarifyActions.test.tsx
  - frontend/src/components/chat/InlineClarifyActions.tsx
  - frontend/src/components/chat/InlineGateActions.test.tsx
  - frontend/src/components/chat/InlineGateActions.tsx
  - frontend/src/components/chat/MessageBubble.tsx
  - frontend/src/components/chat/ResultCard.test.tsx
  - frontend/src/components/chat/ResultCard.tsx
  - frontend/src/components/chat/RunChatLane.test.tsx
  - frontend/src/components/chat/RunChatLane.tsx
  - frontend/src/components/chat/blocks/FileOpsSummary.tsx
  - frontend/src/components/chat/blocks/ThinkingBlock.tsx
  - frontend/src/components/chat/blocks/TodoCard.tsx
  - frontend/src/components/chat/blocks/blocks.test.tsx
  - frontend/src/components/chat/runtime/blocks.types.ts
  - frontend/src/components/chat/runtime/buildBlocks.test.ts
  - frontend/src/components/chat/runtime/buildBlocks.ts
  - frontend/src/components/chat/runtime/partial-json.test.ts
  - frontend/src/components/chat/runtime/partial-json.ts
  - frontend/src/components/chat/runtime/streaming-json.test.ts
  - frontend/src/components/chat/runtime/streaming-json.ts
  - frontend/src/components/chat/runtime/tool-renderers.test.tsx
  - frontend/src/components/chat/runtime/tool-renderers.tsx
  - frontend/src/components/chat/runtime/useMeasuredVirtualWindow.test.ts
  - frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/hooks/useChatAttachments.test.ts
  - frontend/src/hooks/useChatAttachments.ts
  - frontend/src/hooks/useRunChat.test.ts
  - frontend/src/hooks/useRunChat.ts
  - frontend/src/hooks/useTabDeepLink.test.ts
  - frontend/src/hooks/useTabDeepLink.ts
  - frontend/src/types/index.ts
findings:
  critical: 0
  high: 2
  medium: 3
  low: 3
  total: 8
status: issues_found
---

# Phase 31: Code Review Report

**Reviewed:** 2026-07-08
**Depth:** deep (cross-file wiring traced page.tsx → DashboardLayout.tsx → RunChatLane/useRunChat → RunConnectionProvider/useWorkflow)
**Files Reviewed:** 41
**Status:** issues_found

## Summary

Reviewed the full Phase 31 (chat-lane-mvp-a3) diff (`44e2d0c9..HEAD`, `frontend/` only). The borrowed open-design mechanisms (`partial-json`, `streaming-json`, `buildBlocks`, `tool-renderers`, `useMeasuredVirtualWindow`, `ThinkingBlock`/`FileOpsSummary`/`TodoCard`, `useTabDeepLink`) are clean, single-pass, well-tested, and carry the Apache-2.0 attribution header; `NOTICE` + `THIRD-PARTY-NOTICES.md` correctly credit nexu-io/open-design. `role="log"` + `aria-live="polite"` is present on the streaming transcript region in `ChatPanel.tsx` (the documented open-design a11y failure is NOT repeated). `ResultCard`/`buildBlocks`/`tool-renderers`/`RunChatLane` all key strictly on generic `cardKind`/event `kind` discriminators — no `prototype|od_ppt|app_builder|user_stories` literal was found gating any dispatch in the new chat sources (SC-001 holds). `frontend/src/hooks/useWorkflow.ts` and `frontend/src/hooks/useWebSocket.ts` are confirmed absent from the diff (FIX-039/LOCK-B intact) and `npx tsc --noEmit` is clean.

However, tracing the actual data-flow wiring in `page.tsx` → `DashboardLayout.tsx` surfaced two HIGH-severity correctness bugs that unit tests (which construct `useRunChat` in isolation with a fixed `runId`) do not catch, plus several MEDIUM/LOW robustness and dead-code issues. None of the HIGH findings break the *currently active* legacy-WS path (both are gated behind conditions that are false today — the SSE transport flag is OFF, and `pipeline_cancelled` is not a common QA path), but they are real, provable bugs in delivered code and should be fixed before the dependent flags/paths are exercised.

## Critical Issues

None found.

## High-Severity Issues

### HI-01: `useRunChat`'s `runId` is wired to the clarify-only `activePipelineRunId`, so the SSE up-channel would create a NEW run instead of posting to the active one

**File:** `frontend/src/app/dashboard/page.tsx:917-923` (wiring), `frontend/src/hooks/useRunChat.ts:281-283` (consumer), `frontend/src/providers/RunConnectionProvider.tsx:275-291` (effect)

**Issue:** `useRunChat` is constructed with `runId: activePipelineRunId`. `activePipelineRunId` is declared and documented elsewhere in the same file as "pipeline_run_id of the run currently paused at the clarify gate" (`page.tsx:156-158`) — it is set ONLY inside the `questionnaire_ready` handler (`page.tsx:791-793`) and is explicitly reset to `null` on every `pipeline_start` (`page.tsx:478`). That means for the entire "building" phase of a normal (non-clarifying) run — i.e. almost the whole lifecycle — `activePipelineRunId` is `null`.

When the SSE transport flag is ON (`sseEnabled`), `sendMessage` calls `sendCommand(runId, payload)` (`useRunChat.ts:282`). `RunConnectionProvider.sendCommand` branches explicitly on `runId`:
```ts
const url = runId
  ? `${ENV.API_URL}/api/runs/${runId}/messages`
  : `${ENV.API_URL}/api/runs`;              // <-- runId===null creates a NEW run
```
So any chat message sent while a run is actively building (the common case) would silently POST to `/api/runs` and spawn a brand-new, unrelated run instead of appending a message to the run in progress. The one time `activePipelineRunId` IS populated (clarify pause) is also the one case where the composer routes through `InlineClarifyActions`/`submitQuestionnaire`, not free-text `sendMessage` — so the "correct" runId is only ever available when it is least needed.

This is inert today only because `NEXT_PUBLIC_SSE_TRANSPORT` defaults OFF (LOCK-B), so `legacyWsSend` is used instead and `runId` is never consulted. The moment the SSE flag is flipped ON, every in-run chat message misfires.

**Fix:** Thread the actual live run id (e.g. `pipelineState.pipelineRunId`, already captured by `useWorkflow` on every `pipeline_start`/`planner_start`) into `useRunChat`, not `activePipelineRunId`:
```ts
const { messages: runChatMessages, sendMessage: sendRunChatMessage } = useRunChat({
  runId: pipelineState.pipelineRunId ?? activePipelineRunId,
  ...
});
```

### HI-02: The LIVE-STATE-CONTRACT "Cancelled" state is unimplemented — composer never enters relaunch mode and no "Cancelled by you" card is shown after Stop

**File:** `frontend/src/components/layout/DashboardLayout.tsx:1290-1296`, `frontend/src/hooks/useWorkflow.ts:534-567`, `frontend/src/app/dashboard/page.tsx:834-842`

**Issue:** `.planning/phases/28-chat-contracts-guards-a0/contracts/LIVE-STATE-CONTRACT.md` §1 (an authoritative input this phase was built against) mandates for `pipeline_cancelled`: chat lane renders **"Cancelled by you" line + "Run again"**, composer mode = **relaunch mode**. The implementation does neither:

1. `useWorkflow.ts`'s `pipeline_cancelled` handler (`:534-567`) sets `isRunning: false` only — it never sets a `failed`/`cancelled` flag on `pipelineState`.
2. `runLaneState` in `DashboardLayout.tsx` is derived as:
   ```ts
   reviewGateData && isPipelineRunning ? "gate" :
   laneClarifyOpen ? "clarify" :
   isPipelineRunning ? "building" :
   pipelineState?.failed ? "terminal" :        // never true after a cancel
   laneHasDeliverable ? "complete" :
   "idle";
   ```
   Since `pipelineState.failed` is never set by `pipeline_cancelled`, and a stopped run before completion typically has no deliverable content, `runLaneState` falls through to `"idle"` after a Stop — i.e. the plain "Message the run…" composer, not the contract's relaunch affordance.
3. `page.tsx`'s legacy-WS switch handles `case "pipeline_cancelled": case "pipeline_failed":` only to `setReviewGateData(null)` (`:834-842`) — unlike `pipeline_failed` (handled separately inside the `pipelineTypes` block, `:562-584`, which DOES push a chat error message), `pipeline_cancelled` never pushes any chat message. No "Cancelled by you" narrator line is ever produced.

**Fix:** Surface a distinct cancelled signal (e.g. `pipelineState.cancelled = true` alongside the existing `failed` flag) and fold it into `runLaneState` (`pipelineState?.failed || pipelineState?.cancelled ? "terminal" : ...`), and push a "Cancelled by you" `ChatMessage` from the `pipeline_cancelled` case the same way `pipeline_failed` already does.

## Medium-Severity Issues

### MD-01: `useRunChat.sendMessage` swallows `sendCommand` rejections — a failed send leaves the optimistic bubble stranded with no error indication

**File:** `frontend/src/hooks/useRunChat.ts:278-283`

**Issue:**
```ts
if (legacyWsSend) {
  legacyWsSend({ type: "user_message", ...payload });
} else {
  void sendCommand(runId, payload);
}
```
`sendCommand` is `async` and can reject (network failure) — `RunConnectionProvider.sendCommand` does a bare `await fetch(...)` with no try/catch and no non-2xx status check. `void sendCommand(...)` discards the promise entirely: on failure there is no retry, no rollback of the optimistic user bubble, and no error surfaced to the transcript — the user sees their message "sent" forever with no indication it never reached the server. This is a silent-failure UX gap, and in a strict environment it also produces an unhandled promise rejection.

**Fix:** Await and catch, appending an error/`isError` turn (mirroring the existing error-message convention in `page.tsx`) on failure:
```ts
sendCommand(runId, payload).catch(() => {
  setMessages((prev) => [...prev, /* error turn, e.g. isError:true */]);
});
```

### MD-02: Sent attachments are never rendered in the transcript — `ChatMessage.attachments` is populated but never read by `MessageBubble`/`ChatPanel`/`ResultCard`

**File:** `frontend/src/components/chat/MessageBubble.tsx` (whole file), `frontend/src/hooks/useRunChat.ts:150,167-176` (attachments are stored on the message)

**Issue:** `useRunChat`'s optimistic `sendMessage` and `upsertUserMessage` both populate `ChatMessage.attachments` (the picked/pasted/dropped files from `ChatAttachments`/`useChatAttachments`). Grepping the entire diff for `message.attachments` / `att.` rendering inside `MessageBubble.tsx`, `ChatPanel.tsx`, and `ResultCard.tsx` turns up nothing — none of them read `message.attachments`. The composer's pre-send preview chips (`ChatAttachments`) are the ONLY place a picked file is ever visible; once sent, the image/file the user attached simply disappears from the transcript with no acknowledgement it was included. This is a regression against the phase's own deliverable #4 ("Attachment UI... ADD paste + drag-drop + wire the client resize") — the intake exists but the send-time confirmation in the transcript does not.

**Fix:** Render `message.attachments` in `MessageBubble` (e.g. reuse `ChatAttachments`'s reopened-mode placeholder-chip rendering, or a lightweight inline thumbnail/chip row) for both user and echoed turns.

### MD-03: The page-level `useRunChat` transcript state is never cleared when the user switches to a different, unrelated run — stale messages leak across `handleSelectWorkflowRun`/history reopen

**File:** `frontend/src/app/dashboard/page.tsx:917-923` (single hook instance), `:1247-1341` (`handleSelectWorkflowRun` does not touch it), `frontend/src/hooks/useRunChat.ts:217-223` (`messages`/`seenRef` state, by design never wiped)

**Issue:** `useRunChat`'s `messages` and `seenRef` dedup set live in one hook instance mounted once at the page level; by design (family-anchoring) they are never cleared on a `runId` change — the doc explicitly says the transcript "is NEVER swapped per phase/state." That is correct WITHIN one run family (parent + revision children), but `handleSelectWorkflowRun` (user picks a different, unrelated historical run from the sidebar/history) resets every other piece of run-scoped state (`userStoryContent`, `pptContent`, `genericDeliverable`, `reopenedRunStatus`, etc.) but never resets `useRunChat`'s internal transcript. Selecting run B after having chatted on run A leaves run A's chat messages (and dedup set) bleeding into run B's `RunChatLane`, since `RunChatLane` always renders `runChatMessages ?? messages` regardless of which run is now "selected."

**Fix:** Expose a `reset()`/`clear()` from `useRunChat` (mirroring `useChatAttachments.clear`) and call it from `handleSelectWorkflowRun` and `handleNewChat` when the newly selected run is not a member of the currently-tracked family.

## Low-Severity Issues

### LO-01: `TodoCard` (borrow-list item #7) is dead code — never wired into any block-kind union or renderer

**File:** `frontend/src/components/chat/blocks/TodoCard.tsx`, `frontend/src/components/chat/runtime/blocks.types.ts:33-76`, `frontend/src/components/chat/MessageBubble.tsx:61-70`

**Issue:** `TodoCard` is exported and documented as one of the borrowed open-design mechanisms ("open-design borrow #7"), but there is no `"todo"` variant anywhere in the `AgentEvent`/`ChatBlock` discriminated unions, `buildBlocks.ts` never produces one, and `AgentBlockStrip`'s switch in `MessageBubble.tsx` only handles `thinking` / `tool` / `file_ops`. A repo-wide grep shows `TodoCard` is referenced ONLY by its own test file (`blocks.test.tsx`) — it is unreachable in the running application.

**Fix:** Either add a `todo`/`TodoWrite` `AgentEvent`+`ChatBlock` kind and wire it through `buildBlocks`/`AgentBlockStrip`, or remove the component and its test until a downstream plan actually lands it, to avoid shipping an unreferenced borrowed mechanism.

### LO-02: `useTabDeepLink().consume()` is exported/documented as the consume-once mechanism but is never called by any consumer

**File:** `frontend/src/hooks/useTabDeepLink.ts:40-41,63-69`, `frontend/src/app/dashboard/page.tsx:927,1432-1433`, `frontend/src/components/preview/PreviewPanel.tsx:405-429`

**Issue:** The hook's doc comment describes `consume()` as the mechanism that makes the deep-link target "CONSUME-ONCE... so a stale/replayed nonce cannot re-navigate." In practice, `page.tsx` only ever reads `runTabDeepLink.pending` (never calls `.consume()`), and `PreviewPanel` keys its effect purely on `deepLinkTarget?.nonce` changing — which does correctly work (an effect only fires once per distinct nonce), but by an entirely different mechanism than the one documented. `consume()` is unused dead code and the header comment is misleading about how single-use-ness is actually achieved.

**Fix:** Either wire `consume()` into the actual navigation path (e.g. have the page call `consume()` after `PreviewPanel`'s effect fires) or update the doc comment to describe the nonce-diffing mechanism that is actually in effect, and remove the unused `consume` export if it stays unused.

### LO-03: `InlineGateActionsProps.agentId` is declared but never used inside the component

**File:** `frontend/src/components/chat/InlineGateActions.tsx:39,61-73`

**Issue:** The props interface declares `agentId: string` (line 39), and callers (`RunChatLane.tsx:236`) pass it, but the component's destructuring (lines 61-73) omits `agentId` entirely — it is accepted and silently discarded. Dead prop; harmless today but a maintenance trap (a future consumer may assume `agentId` is used for keying/display when it is not).

**Fix:** Either use `agentId` (e.g. as a `data-agent-id` attribute for test/debug hooks) or remove it from the props interface and call sites.

---

_Reviewed: 2026-07-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

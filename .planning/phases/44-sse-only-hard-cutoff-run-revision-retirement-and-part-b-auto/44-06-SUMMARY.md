---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 06
subsystem: ui
tags: [sse, rest, transport, websocket, flag-removal, hard-cutoff, handoff, INV-12, react]

# Dependency graph
requires:
  - phase: 44-01
    provides: "flag-selected SSE down-channel + launch->attach (runConnection.attachRun) — the pipeline reducer is fed from the SSE fan-out"
  - phase: 44-04
    provides: "REST run-command fetchers (postGate/postCancel/postAnswers) — the up-channel that replaces the WS command frames"
  - phase: 44-05
    provides: "postRevision REST /revisions launch — the up-channel that replaces the WS run_revision frame"
provides:
  - "frontend/src/hooks/useHandoffSocket.ts — the D10 handoff-survivor WS hook for /ws/handoff/{token} (connect + backoff + JWT-4001 close + keepalive ping), re-exporting ConnectionStatus"
  - "SSE + REST is the sole, unconditional FE run transport: NEXT_PUBLIC_SSE_TRANSPORT + useWebSocket.ts + /ws/chat client are DELETED (grep-proven)"
  - "RunConnectionProvider always attaches (enabled hardcoded true); useWorkflow launches over REST only (websocketSend param removed)"
  - "/ws/handoff surface unchanged, now riding useHandoffSocket; the vestigial dead /workflow WS is removed"
affects: [44-07 (delete the BE /ws/chat endpoint + config.py SSE_TRANSPORT_ENABLED + run_stream.py 404 guard), 44-09 (re-point the mocked Playwright suite from WS frames to SSE), 44-10 (banned-pattern CI gate — useWebSocket/routeWebSocket now bannable)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Extract-before-delete (INV-12): the shared useWebSocket hook was extracted into a dedicated useHandoffSocket survivor for /ws/handoff BEFORE useWebSocket.ts was deleted — no live caller ever pointed at a deleted hook."
    - "SSE-derived connection status: the header/reconnect UI and the staged-run launch effects key on effectiveConnectionStatus = phaseToConnectionStatus(runConnection.phase) (idle -> connected), replacing the retired WS connectionStatus."
    - "REST-only gate/cancel/revision up-channel: every runConnection.enabled ? REST : websocketSend(frame) branch collapsed to the REST side; the WS frame sends are gone."

key-files:
  created:
    - "frontend/src/hooks/useHandoffSocket.ts - the /ws/handoff survivor hook (extracted verbatim from useWebSocket; re-exports ConnectionStatus)"
  modified:
    - "frontend/src/components/handoff/HandoffWorkflow.tsx - repointed from useWebSocket to useHandoffSocket (behavior byte-identical)"
    - "frontend/src/app/workflow/page.tsx + frontend/src/components/workflow/WorkflowView.tsx - removed the vestigial dead /workflow WS + its unused websocketSend prop"
    - "frontend/src/lib/env.ts - deleted resolveSseTransport/SSE_TRANSPORT (Task 2) then resolveWsUrl/WS_URL (Task 3, with its last consumer)"
    - "frontend/src/providers/RunConnectionProvider.tsx - enabled hardcoded true; all !enabled guards + the aggregatePhase short-circuit removed; provider always attaches"
    - "frontend/src/app/layout.tsx - dropped the stale flag comment"
    - "frontend/src/hooks/useWorkflow.ts - removed the websocketSend param + the WS else-branches; startPipeline -> sendCommand, submitQuestionnaire -> postAnswers unconditionally"
    - "frontend/src/hooks/useRunStream.ts - scrubbed stale useWebSocket/NEXT_PUBLIC_SSE_TRANSPORT comments"
    - "frontend/src/app/dashboard/page.tsx - deleted the useWebSocket call + sseEnabled; unconditional SSE subscribe; deleted chatWsSubscribe/legacyChatSend + the dead legacy chat handlers; effectiveConnectionStatus/reconnect + staged effects source from the SSE phase; gate handlers POST over REST only"
    - "frontend/src/components/layout/DashboardLayout.tsx - ConnectionStatus import repointed to useHandoffSocket; reconnect_pipeline WS effect + getLastSeq/websocketSend deleted; revision/cancel handlers collapsed to REST-only; onSendMessage made optional"
    - "frontend/src/lib/api.ts - scrubbed the useWebSocket.ts comment -> useHandoffSocket.ts"
  deleted:
    - "frontend/src/hooks/useWebSocket.ts - the legacy /ws/chat client (zero src consumers after the repoints)"
  tests:
    - "frontend/src/hooks/useWorkflow.imagePayload.test.ts - reworked onto the REST sendCommand transport (asserts the payload object, not the retired JSON-string send)"
    - "frontend/src/hooks/useWorkflow.clarifyRetention.test.ts - dropped the removed send arg (useWorkflow()), block-body act"
    - "frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts - the PPT revision parent linkage moved from the WS run_revision frame literal to the REST postRevision(..., contentSourceRunId, ...) call"

key-decisions:
  - "Extracted useHandoffSocket FIRST (Task 1), removed the flag SECOND (Task 2), deleted useWebSocket.ts LAST (Task 3) — the mandated extract->flag->delete order; no commit ever had a live caller pointing at a deleted hook (INV-12 / T-44-06-03)."
  - "Deferred the env.ts WS_URL/resolveWsUrl removal from Task 2 to Task 3. The plan placed it in Task 2, but WS_URL's only consumers (useWebSocket.ts + the dashboard WS call) live until Task 3 — removing it in Task 2 broke tsc. Keeping WS_URL through Task 2 and deleting it in Task 3 alongside its last consumer keeps every commit tsc-green while still honoring 'delete useWebSocket LAST'."
  - "Deleted the legacy chat handlers handleSendMessage/handleSendMessageWithMode (they called the deleted WS send). onSendMessage was only a never-taken fallback in runChatSend (onRunChatSend is always supplied); onSendMessageWithMode was entirely unused. Made onSendMessage optional in DashboardLayout rather than removing the prop, so no caller (incl. the catalogHome test) breaks."
  - "Re-sourced the staged od_prototype/od_ppt launch effects from effectiveConnectionStatus (SSE-derived; idle -> connected) rather than the retired WS connectionStatus — a REST launch only needs auth, and the SSE app is 'connected' when idle so a staged run fires on boot."
  - "useHandoffSocket carries the token param + the JWT-4001 close-code handling verbatim (T-44-06-01 mitigation) — the handoff auth path is byte-identical to the retired shared hook."

patterns-established:
  - "Extract-before-delete for a shared hook with a surviving consumer: extract the survivor + repoint the live caller in one commit, delete the shared hook only after tsc proves zero dangling references."

requirements-completed: [W4, "C.3", "INV-12"]

# Metrics
duration: 26min
completed: 2026-07-15
---

# Phase 44 Plan 06: W4-FE — Remove the SSE Transport Flag + Delete useWebSocket (Handoff Survivor Extracted) Summary

**The FE INV-12 transport-cutover exit gate: `NEXT_PUBLIC_SSE_TRANSPORT` + `useWebSocket.ts` + the `/ws/chat` client are DELETED and SSE + REST is the sole unconditional run transport — after first extracting a dedicated `useHandoffSocket` survivor for the still-live `/ws/handoff` surface and repointing `HandoffWorkflow` to it, so no live caller ever referenced the deleted hook.**

## What shipped (strict extract -> flag -> delete order)

- **Task 1 (extract survivor):** New `useHandoffSocket.ts` (verbatim connect/backoff/JWT-4001/ping from `useWebSocket`, re-exports `ConnectionStatus`). `HandoffWorkflow` repointed to it — `/ws/handoff` behavior byte-identical. The vestigial dead `/workflow` WS (`workflow/page.tsx` + `WorkflowView`'s unused `websocketSend` prop) removed.
- **Task 2 (remove the flag):** `env.ts` loses `resolveSseTransport/SSE_TRANSPORT`; `RunConnectionProvider.enabled` hardcoded true (all `!enabled` guards + the `aggregatePhase` short-circuit gone); `useWorkflow` loses its `websocketSend` param and both WS else-branches (launch -> `sendCommand`, answers -> `postAnswers` unconditionally).
- **Task 3 (delete useWebSocket LAST):** `useWebSocket.ts` deleted; `env.ts` `WS_URL` removed (its last consumer); dashboard's WS call + `sseEnabled` + `chatWsSubscribe`/`legacyChatSend` + the dead legacy chat handlers removed; `DashboardLayout`'s `reconnect_pipeline` WS effect + `getLastSeq`/`websocketSend` removed; gate/cancel/revision handlers collapsed to REST-only.

## Verification

- `cd frontend && npx tsc --noEmit` -> **clean (exit 0)** after every task.
- Grep-removal proof (`frontend/src`): `useWebSocket` / `WS_URL` / `SSE_TRANSPORT` / `/ws/chat` / `routeWebSocket` / `NEXT_PUBLIC_SSE_TRANSPORT` / `resolveSseTransport` / `sseEnabled` / `legacyChatSend` / `chatWsSubscribe` -> **0 matches**. `/ws/handoff` survives (HandoffWorkflow + useHandoffSocket + an env.ts comment).
- Targeted vitest (useWorkflow x5, useRunChat, RunChatLane x2, DashboardLayout.catalogHome, the two dashboard source tests) -> **79 passed**.
- Full vitest suite -> **706 passed / 8 failed**. The 8 reds are in 4 files (`HomeLaunchGrid.inspect`, `PreviewPanel.switcher`, `PreviewPanel.degraded`, `FilesTab.runInput`) — **PROVEN pre-existing**: they fail identically at the base commit `3ed21a74` (before this plan), and none import any module this plan changed.

## Expected-red (do NOT fix here)

The **mocked Playwright suite is now RED-as-expected**: once the flag is gone SSE is unconditional, but the mocked harness still mocks WS frames. It is re-pointed to SSE in **44-09 (wave 5)** — per the phase guardrail, this plan does not gate on it.

## Deviations from Plan

### Auto-fixed / adjusted

**1. [Rule 3 - blocking] Deferred env.ts `WS_URL`/`resolveWsUrl` removal from Task 2 to Task 3.**
- **Issue:** The plan removed `WS_URL` in Task 2, but its only consumers (`useWebSocket.ts` + the dashboard WS call) live until Task 3 — Task 2 tsc failed with "Property 'WS_URL' does not exist".
- **Fix:** Kept `WS_URL` through Task 2; removed it in Task 3 with its last consumer. Keeps every commit tsc-green and honors "delete useWebSocket LAST".
- **Commits:** f6ce1142 (kept), a931c066 (removed).

**2. [Rule 3 - blocking] Removed the `useWorkflow` `websocketSend` param -> updated the sole caller.**
- The dashboard `useWorkflow(send)` call was updated to `useWorkflow()` in Task 2 (required for tsc once the param was gone). File: `dashboard/page.tsx`.

**3. [Rule 1 - tests] Reworked two useWorkflow tests + one source test onto the new transport.**
- `useWorkflow.imagePayload.test.ts` asserted on the WS `send` payload (deleted); reworked to capture the payload via a mocked `runConnection.sendCommand`. `clarifyRetention.test.ts` dropped the removed arg. `revisionFamilyLinkage.source.test.ts` moved the PPT-revision parent-linkage assertion from the WS `run_revision` frame literal to the REST `postRevision(..., contentSourceRunId, ...)` call. Logic/intent intact — not loosened.

**4. [Rule 1 - dead code / INV-12] Deleted the legacy chat handlers.**
- `handleSendMessage`/`handleSendMessageWithMode` called the deleted WS `send`. `onSendMessage` was only a never-taken fallback (onRunChatSend always supplied); `onSendMessageWithMode` was entirely unused. Removed them; made `onSendMessage` optional in `DashboardLayout` so no caller breaks.

**5. [Rule 3 - scope] Comment scrubs outside the per-task file lists.**
- `useRunStream.ts` and `api.ts` carried stale `useWebSocket` / `NEXT_PUBLIC_SSE_TRANSPORT` / `/ws/chat` mentions that would trip the 44-10 banned-pattern CI gate + the success-criteria zero-grep. Scrubbed (comment-only).

**Note on residual channel-name strings:** `approve_review` / `cancel_pipeline` / `run_revision` still appear in `api.ts` ("mirrors WS X") and `InlineGateActions.tsx` (the backend gate command CHANNEL name, used over REST) as documentation/backend-channel references. These are NOT WS frame sends (all WS sends are removed) and are NOT in the CI banned list (`/ws/chat`, `useWebSocket`, `routeWebSocket`, `NEXT_PUBLIC_SSE_TRANSPORT`, `SSE_TRANSPORT_ENABLED`).

## Known Stubs

None introduced.

## Threat Flags

None. `useHandoffSocket` carries the token param + the JWT-4001 close handling verbatim (T-44-06-01 mitigation); the deleted flag held no auth logic (T-44-06-02); `useWebSocket.ts` was deleted only after all consumers were repointed and tsc proved zero dangling references (T-44-06-03).

## Backend note (out of scope — 44-07)

The BE half of the flag (`config.py SSE_TRANSPORT_ENABLED`, `run_stream.py` 404 guard, the `/ws/chat` endpoint) is untouched — that is plan 44-07.

## Self-Check: PASSED

- FOUND: frontend/src/hooks/useHandoffSocket.ts (created)
- GONE: frontend/src/hooks/useWebSocket.ts (deleted)
- FOUND commits: d8f93efb (Task 1), f6ce1142 (Task 2), a931c066 (Task 3)

---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 04
subsystem: ui
tags: [sse, rest, react, transport, pipeline, gate, cancel, questionnaire, flag-selected, wr-03]

# Dependency graph
requires:
  - phase: 44-01
    provides: "flag-selected SSE pipeline/questionnaire/review-gate down-channel + launch->attach (the SSE stream the REST command acks re-emit onto)"
  - phase: 29
    provides: "owner-scoped REST run-command endpoints (POST /api/runs/{id}/gate|/answers|/cancel) — the same store seams the WS handlers use"
provides:
  - "Gate actions (approve+edited_content / reject / redo / update_specs) POST to /api/runs/{id}/gate when the SSE flag is ON — edited_content preserved (WR-03); /messages is never used for gates"
  - "Cancel POSTs to /api/runs/{id}/cancel with the run_id threaded (both DashboardLayout cancel sites) when the flag is ON"
  - "Questionnaire submit POSTs to /api/runs/{id}/answers (AnswersCommand, no message_id) when the flag is ON — closes the R4 422 the /messages MessageCommand path raised"
  - "Typed api.ts fetchers: postGate, postCancel, postAnswers (owner-scoped run commands)"
affects: [W4 (delete /ws/chat + remove the flag), W5 (44-09 re-point the mocked e2e harness to REST)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Flag-selected command up-channel: REST run-command fetcher when NEXT_PUBLIC_SSE_TRANSPORT is ON, existing WS frame when OFF (mirrors 44-01's down-channel flag-select) — exactly one transport per branch"
    - "Gate routes to /gate (carries edited_content via set_review_response), never /messages CHANNEL_GATE (which drops it) — WR-03"
    - "Fire-and-forget REST commands: void postX(...).catch(console.error) at the handler, matching the old sync WS send's non-blocking shape"

key-files:
  created: []
  modified:
    - "frontend/src/lib/api.ts - postGate/postCancel/postAnswers owner-scoped run-command fetchers (mirror the Pydantic request bodies verbatim)"
    - "frontend/src/app/dashboard/page.tsx - the four gate handlers flag-gated onto postGate(reviewGateData.pipelineRunId); WS approve_review frames kept on the flag-OFF branch"
    - "frontend/src/components/layout/DashboardLayout.tsx - both cancel sites (handleCancelWorkflow, handleStopPipeline) flag-gated onto postCancel(runId); WS cancel_pipeline kept on the flag-OFF branch"
    - "frontend/src/hooks/useWorkflow.ts - submitQuestionnaire SSE path now posts /answers (was /messages -> 422); WS submit_questionnaire kept on the flag-OFF branch"

key-decisions:
  - "Kept the command rewires FLAG-SELECTED (REST when the flag is ON, the existing WS send when OFF) rather than the plan's unconditional REST — the flag is not removed until 44-06 and the mocked e2e harness is not re-pointed to REST until 44-09, so unconditional REST would break the flag-OFF gate/cancel/questionnaire specs (orchestrator guardrail = load-bearing intermediate-state rule; 44-01 made the same override)"
  - "Gates route to POST /{id}/gate, never /messages: /messages CHANNEL_GATE drops edited_content (run_commands.py), /gate preserves it via set_review_response (WR-03)"
  - "Questionnaire SSE path targets /answers (AnswersCommand — no message_id) instead of /messages (MessageCommand requires message_id -> the R4 422); ISS-027 skip_clarification rides along unchanged"
  - "Reused getToken() from @/lib/api at each call site for a fresh JWT (matches the existing REST-fetcher idiom in these files) rather than threading token through props"

patterns-established:
  - "Pattern: flag-selected command up-channel — REST fetcher (flag ON) | legacy WS frame (flag OFF), one branch each; the ack + re-emitted gate/questionnaire event arrive over the 44-01 SSE down-channel"

requirements-completed: [W2, "WR-03"]

# Metrics
duration: 20min
completed: 2026-07-15
---

# Phase 44 Plan 04: Rewire the un-flagged WS commands (gate / cancel / questionnaire) to REST Summary

**Gate/cancel/questionnaire commands ride owner-scoped REST when the SSE flag is ON — gates via POST /{id}/gate so edited_content survives (WR-03), cancel via /{id}/cancel with the run_id threaded, and the questionnaire via /{id}/answers which closes the R4 422 — while the WS flag-OFF path stays byte-identical until W4/W5.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-15T21:40:00Z
- **Completed:** 2026-07-15T22:00:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Three typed, owner-scoped REST fetchers added to `api.ts` (`postGate`, `postCancel`, `postAnswers`) mirroring the backend `GateCommand`/`AnswersCommand`/cancel bodies verbatim — no invented fields.
- The four gate UI actions (approve+edited_content / reject / redo / update_specs) POST to `/api/runs/{id}/gate` on the SSE branch, carrying `edited_content` through `set_review_response` (WR-03) — gates never touch `/messages` (whose CHANNEL_GATE branch drops `edited_content`).
- Both `DashboardLayout` cancel sites (`handleCancelWorkflow`, `handleStopPipeline`) POST to `/api/runs/{id}/cancel` with the active run id threaded (the WS frame was connection-scoped and carried no id).
- `submitQuestionnaire` SSE path re-pointed from `/messages` (MessageCommand → 422, missing `message_id`) to `/answers` (AnswersCommand → no `message_id` required), closing R4; the ISS-027 `skip_clarification` force-proceed is preserved.
- The flag-OFF (WS) path is byte-identical: the mocked Playwright gate/cancel/questionnaire specs stay green (18 passed / 0 failed).

## Task Commits

Each task was committed atomically:

1. **Task 1: owner-scoped REST run-command fetchers in api.ts** - `748d8d0d` (feat)
2. **Task 2: rewire the four gate actions to POST /{id}/gate (flag-gated)** - `92ab6a41` (feat)
3. **Task 3: cancel over /{id}/cancel (run_id threaded) + questionnaire /answers 422 fix** - `2ce7ec1a` (feat)

**Plan metadata:** committed with this SUMMARY.

## Files Created/Modified
- `frontend/src/lib/api.ts` - `postGate` (GatePayload w/ `edited_content`), `postCancel`, `postAnswers` fetchers; reuse the existing `request`/`authHeaders` machinery; a cross-owner/missing run surfaces as `ApiError(404)`.
- `frontend/src/app/dashboard/page.tsx` - imports `postGate`; the four `onApproveReview`/`onRejectReview`/`onRedoReview`/`onUpdateSpecsReview` handlers flag-gated: SSE → `postGate(getToken(), reviewGateData.pipelineRunId, {...})`, OFF → the existing WS `approve_review` frame. The `pendingGateEditRef` stash and `setReviewGateData(null)` side-effects are unchanged.
- `frontend/src/components/layout/DashboardLayout.tsx` - imports `postCancel`; both cancel sites flag-gated on `runConnection.enabled`: SSE → `postCancel(getToken(), runId)` (`activePipelineRunId` in `handleCancelWorkflow`; `pipelineState.pipelineRunId ?? activePipelineRunId` in `handleStopPipeline`), OFF → the existing WS `cancel_pipeline` frame. The two-step unblock-then-cancel sequence is preserved.
- `frontend/src/hooks/useWorkflow.ts` - imports `getToken`, `postAnswers`; `submitQuestionnaire` SSE branch posts `/answers` instead of `runConnection.sendCommand(...)` (`/messages`), OFF branch keeps the WS `submit_questionnaire` frame.

## Decisions Made
- Command rewires kept FLAG-SELECTED, not unconditional REST (see Deviations — the load-bearing intermediate-state rule for this wave).
- Gates route to `/gate`, never `/messages` (WR-03 — edited_content preservation).
- Questionnaire targets `/answers` (no message_id) to close the R4 422.
- `getToken()` reused at each call site for a fresh JWT (matches the existing REST-fetcher idiom) rather than threading a token prop.

## Deviations from Plan

### Auto-fixed Issues

**1. [Orchestrator guardrail override] Kept the command rewires FLAG-GATED instead of unconditional REST**
- **Found during:** Tasks 2 & 3 (gate / cancel / questionnaire rewires)
- **Issue:** The plan text and its per-task acceptance criteria assume UNCONDITIONAL REST — e.g. `grep -c 'type: "approve_review"'` and `grep -c "cancel_pipeline"` must return 0. But the `NEXT_PUBLIC_SSE_TRANSPORT` flag is not removed until 44-06 and the mocked e2e harness is not re-pointed to REST until 44-09. Rewiring unconditionally would delete the WS frames the flag-OFF mocked specs (TS-N approve/reject, TS-R cancel, TS-M questionnaire) still assert, breaking the intermediate state.
- **Fix:** Each rewire is `if (sseEnabled/runConnection.enabled) { REST } else { existing WS frame }`. The REST branch is the new behavior; the WS branch is retained byte-identical. Consequently `approve_review` still greps to 4 and `cancel_pipeline` to 2 (both only inside the flag-OFF `else` branches) — the plan's grep-0 criteria are intentionally NOT met this wave; W4 removes the flag and the WS branches together.
- **Files modified:** frontend/src/app/dashboard/page.tsx, frontend/src/components/layout/DashboardLayout.tsx, frontend/src/hooks/useWorkflow.ts
- **Verification:** `npx tsc --noEmit` clean; mocked Playwright gate/cancel/questionnaire specs green (18 passed / 7 pre-existing skips / 0 failed) with the flag OFF.
- **Committed in:** 92ab6a41 (Task 2), 2ce7ec1a (Task 3)

**2. [Rule 3 - Blocking] Imported getToken into useWorkflow.ts (not in the plan's action text)**
- **Found during:** Task 3 (questionnaire /answers rewire)
- **Issue:** `useWorkflow` had no token in scope — the old SSE path used `runConnection.sendCommand`, which fetches the token internally. `postAnswers` needs a token argument.
- **Fix:** Imported `getToken` from `@/lib/api` (the same idiom `dashboard/page.tsx` and `DashboardLayout.tsx` already use) and passed `getToken() ?? ""`.
- **Files modified:** frontend/src/hooks/useWorkflow.ts
- **Verification:** `npx tsc --noEmit` clean.
- **Committed in:** 2ce7ec1a (Task 3 commit)

---

**Total deviations:** 2 (1 orchestrator-guardrail override, 1 blocking).
**Impact on plan:** The guardrail override is the intended intermediate-state behavior (flag-selected, not unconditional REST) — the SSE-active behavior the plan specifies (gate→/gate w/ edited_content, cancel→/cancel w/ run_id, questionnaire→/answers) is fully delivered; the only difference is it is flag-SELECTED rather than force-on this wave (W4 removes the flag + the WS branches). The `getToken` import is a mechanical consequence of the fetcher signature. No scope creep.

## Issues Encountered
None — all three rewires compiled and the flag-OFF mocked suite passed on the first run.

## Known Stubs
None — every rewire calls a live owner-scoped REST endpoint; the ack + re-emitted gate/questionnaire event arrive over the 44-01 SSE down-channel.

## Threat Surface
No new surface. The FE targets the existing owner-scoped Phase-29 endpoints unchanged (cross-owner/missing → 404, matching the WS owner fence — T-44-04-01/03). WR-03 (T-44-04-02) is satisfied by routing gates through `/gate`, never `/messages`. Backend owner-scoping is covered by `tests/unit/test_rest_gate_commands.py` + `test_rest_answers_cancel.py` (not re-run here — no backend change).

## User Setup Required
None - no external service configuration required. To exercise the REST command path locally set `NEXT_PUBLIC_SSE_TRANSPORT=1`; unset (default) keeps the WS command path.

## Next Phase Readiness
- W2 lands: gate (with edited_content), cancel (run_id threaded), and questionnaire (422 closed) all ride owner-scoped REST when the flag is ON, over the 44-01 SSE stream — no command has WS as its only transport anymore.
- W3 (44-05, run_revision retirement) and W4 (delete /ws/chat + remove the flag + the retained WS command branches) can proceed. W5 (44-09) re-points the mocked e2e harness to the REST path and flips these specs to assert the REST calls.
- The flag, the WS `approve_review`/`cancel_pipeline`/`submit_questionnaire` flag-OFF branches, and the WS `send`/`websocketSend` seams are all still present for W4's wholesale de-flagging.

## Self-Check: PASSED
- All 4 modified files present on disk.
- All 3 task commits present in git history (748d8d0d, 92ab6a41, 2ce7ec1a).
- `npx tsc --noEmit` clean; mocked gate/cancel/questionnaire specs green (18 passed / 0 failed, flag OFF).

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-15*

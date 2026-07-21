---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 03
subsystem: ui
tags: [react, run-screen, runchatlane, previewpanel, clarify, gate, failed-run, tabs, typescript]

# Dependency graph
requires:
  - phase: 42-02
    provides: "state-keyed default-tab effect + right panel always PreviewPanel; the deferred failed→Audit auto-tab this plan lands"
provides:
  - "Lane composer during clarify/gate is a plain phase-hint FreeTextComposer (composerHint), not a second answer surface — Steps is the sole answer surface; the AwaitingCard status card is kept"
  - "Terminal-FAILED run (failed/degraded, no deliverable, not cancel) drops the Preview tab (tabs become Steps · Files · Audit), defaults to Audit, and retires the amber DegradedRunAffordance on the run screen"
  - "The deferred failed→Audit auto-tab (from 42-02) landed, folded into a generic default-tab discriminator"
affects: [42-04, 42-05, 42-06, 42-10]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Composer clarify/gate cases fall through to a single FreeTextComposer hint input; free text routes as a steering note via the shared handleFreeText → sendMessage seam (no new channel)"
    - "Terminal-failed tab derivation: terminalFailureNoDeliverable = showFailureAffordance && !isCancelledTerminal drives both visibleTabs (Preview filtered) and a folded default-tab discriminator (failed → Audit); failed-WITH-content keeps Preview (content wins); cancelled keeps its Preview affordance"

key-files:
  created: []
  modified:
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/chat/RunChatLane.test.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/preview/PreviewPanel.test.tsx
    - frontend/src/components/preview/PreviewPanel.degraded.test.tsx
  deleted: []

key-decisions:
  - "The in-Preview DegradedRunAffordance mount was NOT deleted outright — it was scoped to the CANCELLED-terminal case only. Deleting it would regress the cancelled-reopen affordance (a §8 decision-4 history behavior) and break the degraded suite's cancelled test. Failed/degraded drop the Preview tab, so the affordance is unreachable for them = retired."
  - "The tab-drop / failed→Audit signal keys on terminalFailureNoDeliverable (failed with NO deliverable), not raw headerFailed — a failed/degraded run that still carries content keeps its Preview tab so a real deliverable is never hidden (content wins)."

patterns-established:
  - "Generic default-tab discriminator: fold the failed-no-deliverable state into a synthetic 'failed' key so the 42-02 auto-tab latch fires for it (SC-001 — no workflow/agent-name literal)."

requirements-completed: [RUNUI-06, RUNUI-08]

# Metrics
duration: 22 min
completed: 2026-07-15
---

# Phase 42 Plan 03: Lane Composer Hint (Group C) + Failed-Run Tabs (Group D) Summary

**During clarify/gate the run-screen lane composer is now a plain phase-hint FreeTextComposer (Steps is the sole answer surface, the AwaitingCard status card kept), and a terminal-failed run drops the Preview tab, defaults to Audit, and retires the amber DegradedRunAffordance on the run screen (red lives in the lane/Steps/header) while RunDetailPage's history-reopen mount is untouched.**

## Performance
- **Duration:** ~22 min
- **Tasks:** 2
- **Files modified:** 5 (2 source + 3 test)

## Accomplishments
- **Group C — lane composer = plain hint.** `RunChatLane.renderComposerBody` clarify/gate cases now fall through to a single `FreeTextComposer` hint input with a per-state `composerHint` ("Answer the questions above to continue…" / "Approve the plan above, or add a note…"). The full `InlineClarifyActions`/`InlineGateActions` mounts are gone from the composer; a free-text turn routes as a steering note through the shared `handleFreeText → sendMessage` seam (no new channel). The `AwaitingCard` status card (`renderTranscriptFooter` clarify/gate) is preserved untouched. The now-unused `InlineClarifyActions`/`InlineGateActions` component imports were dropped (the `type ClarifyResponse` import — still used by the props interface — is kept).
- **Group D — failed run tabs.** For a terminal FAILED run (`terminalFailureNoDeliverable = showFailureAffordance && !isCancelledTerminal`), `PreviewPanel` filters `preview` out of the tab set (`visibleTabs` → Steps · Files · Audit) and lands on Audit via a generic default-tab discriminator that folds the failed-no-deliverable state into the 42-02 auto-tab latch. The amber `DegradedRunAffordance` in-Preview mount is scoped to the cancelled-terminal case only, so it is retired for failed/degraded on the run screen (they have no Preview tab). Red failed treatment stays in the lane / Steps / header (§4 KEEP, unmodified).
- **Landed the deferred `failed → Audit` auto-tab** (flagged in the 42-02 SUMMARY) together with the Preview-tab drop, so a failed run defaults to Audit rather than a now-removed Preview.
- Verification: `tsc --noEmit` clean; touched vitest suites at the documented 4-failure baseline (zero net-new); fidelity harness 8/8 green (incl. the failed-run capture).

## Task Commits
1. **Task 1: Lane composer = plain phase-hint during clarify/gate (Group C)** — `995e5907` (feat)
2. **Task 2: Failed run drops Preview tab, defaults Audit, retires DegradedRunAffordance (Group D)** — `2fd421b6` (feat)

## Files Modified
- `frontend/src/components/chat/RunChatLane.tsx` — clarify/gate composer cases → `FreeTextComposer` hint (`composerHint`); dropped unused `InlineClarifyActions`/`InlineGateActions` imports; updated the class doc comment.
- `frontend/src/components/chat/RunChatLane.test.tsx` — the two composer-mode tests now assert the plain hint input (placeholder + steering-note send), not the inline forms.
- `frontend/src/components/preview/PreviewPanel.tsx` — `terminalFailureNoDeliverable` / `showCancelledAffordance` / `visibleTabs` derivations; Tabs render uses `visibleTabs`; default-tab effect folds `failed → Audit` via `defaultTabDiscriminator` (ref retyped to `string`); the in-Preview `DegradedRunAffordance` mount is scoped to cancelled.
- `frontend/src/components/preview/PreviewPanel.test.tsx` — the terminal-failed chrome test rewritten to the Group-D contract; added a non-failed "keeps four tabs, defaults Preview" test.
- `frontend/src/components/preview/PreviewPanel.degraded.test.tsx` — the failed/degraded/reopen-failed/reopen-degraded tests rewritten to the Group-D contract (no Preview tab, Audit default, no amber affordance) via a shared `expectFailedTabSet` helper; added an `AuditTab` stub; the cancelled-reopen test is unchanged (still keeps its Preview affordance).

## Deviations from Plan

### 1. [Rule 1/4-adjacent — Scope] DegradedRunAffordance mount scoped to cancelled, not deleted
- **Found during:** Task 2
- **Issue:** The plan action says "Remove the DegradedRunAffordance mount from the Preview branch." But the same mount serves the **cancelled-terminal** case (`reopenedRunStatus='cancelled'`), which is NOT a "failed" run (`isCancelledTerminal` → `headerFailed=false`), keeps its Preview tab, and is explicitly preserved by CONTEXT §8 decision 4 (history/reopen untouched). A literal deletion would (a) blank the cancelled-reopen surface to "Output will appear here" and (b) break `PreviewPanel.degraded.test.tsx`'s cancelled test.
- **Fix:** Scoped the mount guard to `showCancelledAffordance = showFailureAffordance && isCancelledTerminal`. Failed/degraded runs drop the Preview tab (`visibleTabs`) + default Audit, so the affordance is unreachable for them = retired on the run screen; cancelled keeps it. Net effect matches the plan's intent (no amber affordance for a FAILED run) without the cancelled regression.
- **Files:** `PreviewPanel.tsx`
- **Committed in:** `2fd421b6`

### 2. [Rule 1 — Correctness] Tab-drop keys on failed-NO-deliverable, not raw headerFailed
- **Found during:** Task 2
- **Issue:** Keying the Preview-tab drop / Audit default on raw `headerFailed` (`terminalFailure && !isCancelledTerminal`) would also drop Preview for a failed/**degraded run that still carries a deliverable** (degraded = "completed with issues" commonly HAS partial output), hiding a real deliverable and breaking the "content wins" test.
- **Fix:** Keyed on `terminalFailureNoDeliverable = showFailureAffordance && !isCancelledTerminal` (i.e. `!hasContent && isTerminal && terminalFailure && !cancelled`) — the true "Failed mock" case (no deliverable). A failed run with content keeps Preview and stays put.
- **Files:** `PreviewPanel.tsx`
- **Committed in:** `2fd421b6`

**Total deviations:** 2 (both correctness/scope refinements of the Group-D action; end state matches the plan's must-haves and mock).

## Plan path note
The plan's Task-2 acceptance greps `frontend/src/components/results/RunDetailPage.tsx`, but the file lives at `frontend/src/components/history/RunDetailPage.tsx` (its `DegradedRunAffordance` mount is at `:296`). Confirmed: RunDetailPage still imports/uses `DegradedRunAffordance` (3 refs) and is **not** in this plan's diff — the history-reopen surface is untouched (§8 decision 4).

## Verification (actual output)
- `npx tsc --noEmit` (full project, mockApi-filtered) → **0 errors**.
- `npx vitest run RunChatLane` → **32 passed** (2 files) — clarify/gate composer now assert the hint input.
- `npx vitest run PreviewPanel DashboardLayout InlineClarifyActions RunChatLane StepsDrilldown StepsOverviewSpine AgentThinkingTab` → **107 passed / 4 failed** — the 4 = the documented pre-existing baseline (3 in `__tests__/PreviewPanel.switcher.test.tsx` `renderer-switcher` drift + 1 in `PreviewPanel.degraded.test.tsx` "streaming+empty"); **zero net-new failures**.
- `FIDELITY_CAPTURE=1 npx playwright test zzz-baseline --workers=1` (from `frontend/`) → **8 passed** (incl. `CAPTURE failed run`, clarify/gate-awaiting lanes).
- Grep gates: `composerHint|FreeTextComposer` in RunChatLane == **9**; both `case "clarify"` + `case "gate"` fall through to `FreeTextComposer`; `DegradedRunAffordance` in `PreviewPanel.tsx` retained (cancelled + export); `DegradedRunAffordance` in `history/RunDetailPage.tsx` == **3** (untouched).
- `git diff --name-only 995e5907~1..HEAD` → only 5 `frontend/**.tsx` files (INV-3 / LOCK-B: no backend/transport/golden/manifest/useWorkflow/useRunStream changes).

## Confirmations requested by the orchestrator
- **(a) Lane composer is a plain hint with the AwaitingCard kept:** YES. Clarify/gate composer cases render `FreeTextComposer` with the phase-cue placeholder; the full inline answer/approval forms are gone from the lane (they live only in Steps); the `AwaitingCard` status card (`renderTranscriptFooter`, `:359-398`) is unchanged.
- **(b) Failed runs drop Preview + default Audit + use red with DegradedRunAffordance retired on the run screen (RunDetailPage untouched):** YES. Terminal-failed runs render tabs [Steps, Files, Audit], default Audit, no amber DegradedRunAffordance (scoped to cancelled). Red failed treatment stays in the §4-KEEP lane/Steps/header. `history/RunDetailPage.tsx` history-reopen mount is untouched (out of scope, §8 decision 4).

## KEEP-set integrity
Untouched toward the mock (§4 KEEP): the failed lane (`RunChatLane:803-869` What-went-wrong + Resume + change-composer), Steps failed rows + "Pipeline halted" banner, Files "Build incomplete" banner, Audit "governance stopped" verdict, RunHeader red failed badge, and the `AwaitingCard` status cards. Submit channels (`submit_questionnaire` / `approve_review`) and all handlers unchanged — Group C only swapped the composer body render, Group D only reshaped the tab set + affordance guard.

## Self-Check: PASSED
- `42-03-SUMMARY.md` present on disk.
- Commits `995e5907`, `2fd421b6` present in git history.
- `frontend/src/components/chat/RunChatLane.tsx` clarify/gate → `FreeTextComposer`; `frontend/src/components/preview/PreviewPanel.tsx` `visibleTabs` + `defaultTabDiscriminator` present.
- `history/RunDetailPage.tsx` not in this plan's diff.

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-15*

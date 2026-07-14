---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 02
subsystem: ui
tags: [react, run-screen, previewpanel, clarify, tabs, dashboardlayout, typescript]

# Dependency graph
requires:
  - phase: 42-01
    provides: run-screen paused-state fidelity harness (zzz-baseline capture) used as the acceptance oracle
provides:
  - "Right panel is always PreviewPanel — the three legacy full-screen takeover branches (planning overlay / review-gate / questionnaire) removed from the DashboardLayout cascade"
  - "State-keyed default-tab effect in PreviewPanel (gate/clarify/building -> Steps, complete -> Preview), keyed on the generic headerRunState (SC-001)"
  - "onCancelWorkflow re-homed onto InlineClarifyActions and threaded to both inline-clarify mounts (lane + Steps)"
  - "ClarifyQuestion + MCQQuestion relocated to types/index.ts; QuestionnairePanel.tsx deleted"
affects: [42-03, 42-04, 42-05, 42-06, 42-10]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "State-keyed default-tab via a useRef latch keyed on the generic run-state value (fires once per transition, never clobbers a manual tab click)"
    - "Cancel-Workflow re-home: an optional callback prop threaded DashboardLayout -> PreviewPanel -> AgentThinkingTab -> StepsOverviewSpine -> InlineClarifyActions, and DashboardLayout -> RunChatLane -> InlineClarifyActions"

key-files:
  created: []
  modified:
    - frontend/src/types/index.ts
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/chat/InlineClarifyActions.tsx
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/results/StepsOverviewSpine.tsx
    - frontend/src/components/results/AgentThinkingTab.tsx
  deleted:
    - frontend/src/components/preview/QuestionnairePanel.tsx

key-decisions:
  - "Removed the QuestionnairePanel cascade branch + import in Task 1 (not Task 2) because deleting the file with tsc clean requires DashboardLayout to stop importing the component first."
  - "Deferred failed -> Audit auto-tab to Group D (42-03), where DegradedRunAffordance is retired + the Preview tab dropped, to avoid a half-migrated failed surface (affordance hidden but still present)."

patterns-established:
  - "Auto-tab keys on the pre-existing generic headerRunState discriminator (gate|clarify|building|terminal|complete|idle) — never a workflow/agent-name literal (SC-001)."

requirements-completed: [RUNUI-06, RUNUI-08]

# Metrics
duration: 27 min
completed: 2026-07-14
---

# Phase 42 Plan 02: Kill Legacy Full-Screen Takeovers + Auto-Tab + Cancel Re-home Summary

**Removed the three legacy full-screen right-panel takeover branches so PreviewPanel's mock-matching inline Steps clarify/gate/planning surfaces mount during those states, added a generic state-keyed default-tab effect, re-homed Cancel-Workflow onto the inline clarify, relocated the shared ClarifyQuestion type, and deleted QuestionnairePanel.tsx.**

## Performance

- **Duration:** ~27 min
- **Started:** 2026-07-14T21:53:00Z
- **Completed:** 2026-07-14T22:21:00Z
- **Tasks:** 3
- **Files modified:** 13 (7 source + 5 test modified, 1 source deleted; +1 type home)

## Accomplishments
- The right-panel cascade in `DashboardLayout` now renders `<PreviewPanel>` unconditionally — the `PlanningOverlay`, `<ReviewGatePanel>`, and `<QuestionnairePanel>` branches, their imports, and the local `PlanningOverlay` fn (+ `PLANNING_STEPS`, `Brain`/`Sparkles` icons) are gone. The mock-correct inline surfaces (Steps clarify/gate cards, header pills, review-dot, planning-in-Steps) are now reachable during planning/clarify/gate.
- `PreviewPanel` auto-selects the correct tab per state via a `useRef`-latched effect keyed on the generic `headerRunState`: gate/clarify/building(incl. planning) → Steps; complete → Preview. Fires once per state transition; never overrides a manual tab click.
- Cancel-Workflow is preserved: `InlineClarifyActions` gained an optional `onCancelWorkflow` prop + a subtle "Cancel workflow" affordance, threaded from `DashboardLayout` to BOTH inline-clarify mounts (lane via `RunChatLane`; Steps via `PreviewPanel → AgentThinkingTab → StepsOverviewSpine`), bound to the existing owner-scoped `handleCancelWorkflow`.
- `ClarifyQuestion` + `MCQQuestion` now live in `types/index.ts`; all importers + 3 test files repointed; `QuestionnairePanel.tsx` deleted. `ReviewGatePanel.tsx` file retained (its parsers are extracted in 42-05).
- Fidelity harness green (8/8 captures incl. planning/clarify/gate); `tsc --noEmit` clean; all touched-component suites at baseline parity (zero net-new failures).

## Task Commits

1. **Task 1: Relocate the ClarifyQuestion type + delete QuestionnairePanel.tsx** - `94707834` (refactor)
2. **Task 2: Remove the three takeover branches + auto-select the tab per state** - `14fd527b` (feat)
3. **Task 3: Re-home the Cancel-Workflow affordance onto the inline clarify** - `c1673fa0` (feat)

## Files Created/Modified
- `frontend/src/types/index.ts` - New home for `ClarifyQuestion` + `MCQQuestion` (shared contract).
- `frontend/src/components/layout/DashboardLayout.tsx` - Cascade collapsed to PreviewPanel only; QuestionnairePanel/ReviewGatePanel imports + branches + PlanningOverlay fn removed; `onCancelWorkflow` wired to both inline-clarify mounts.
- `frontend/src/components/preview/PreviewPanel.tsx` - State-keyed default-tab effect (`autoTabbedForState` latch); `onCancelWorkflow` passthrough; type import repoint.
- `frontend/src/components/chat/InlineClarifyActions.tsx` - `onCancelWorkflow` prop + "Cancel workflow" affordance; type import repoint.
- `frontend/src/components/chat/RunChatLane.tsx` - `onCancelWorkflow` prop threaded into the clarify composer case.
- `frontend/src/components/results/StepsOverviewSpine.tsx` / `AgentThinkingTab.tsx` - `onCancelWorkflow` passthrough to the Steps InlineClarifyActions mount; type import repoint.
- `frontend/src/components/preview/QuestionnairePanel.tsx` - **Deleted** (no reusable logic; the only reusable export, `ClarifyQuestion`, was relocated first).
- Tests: `InlineClarifyActions.test.tsx` (repoint + 2 cancel tests), `RunChatLane.test.tsx` / `StepsDrilldown.test.tsx` (repoint), `PreviewPanel.test.tsx` (select Preview tab in the streaming-chrome spec), `DashboardLayout.waveMount.test.tsx` / `DashboardLayout.catalogHome.test.tsx` (drop dead QuestionnairePanel `vi.mock`).

## Decisions Made
- **QuestionnairePanel branch removed in Task 1, not Task 2.** Task 1's acceptance requires the file deleted AND tsc clean; that is impossible while `DashboardLayout` still imports/mounts the component. So the QuestionnairePanel import + its cascade branch were removed in Task 1; Task 2 then removed the remaining two branches (PlanningOverlay, ReviewGatePanel).
- **Deferred `failed → Audit` auto-tab to Group D (42-03).** See Deviations.

## Deviations from Plan

### Auto-fixed / scoping decisions

**1. [Rule 3 - Blocking] QuestionnairePanel branch + import removed in Task 1 (sequencing)**
- **Found during:** Task 1
- **Issue:** Task 1's acceptance requires `QuestionnairePanel.tsx` deleted AND `tsc` clean AND 0 path imports. `DashboardLayout.tsx` imported and mounted the component, so deleting the file would break the build (TS2307).
- **Fix:** Removed the QuestionnairePanel import (`:27`) and its cascade branch in Task 1 (the plan nominally assigned the branch removal to Task 2). Task 2 removed the other two branches. Net end state identical to the plan; only the split point moved.
- **Files modified:** `DashboardLayout.tsx`
- **Verification:** Task 1 `tsc` clean; grep for the path import == 0.
- **Committed in:** `94707834`

**2. [Rule 4-adjacent - Scope] Deferred `failed → Audit` auto-tab to Group D (42-03)**
- **Found during:** Task 2
- **Issue:** The plan action lists `terminal-failure → 'audit'`. But `DegradedRunAffordance` (the failed run's "did not complete" surface) still lives on the **still-present** Preview tab in this plan — CONTEXT §D / §5 W2 bundles the failed-Audit-default WITH dropping the Preview tab + retiring the affordance in Group D (plan 42-03). Auto-tabbing failed→Audit now would leave a failed run's own affordance hidden by default (an incoherent half-migration) and broke 8 coherent PreviewPanel tests.
- **Fix:** The auto-tab effect implements the generic core that the plan's *verified* acceptance (human-check + done criteria) requires — gate/clarify/building→Steps and complete→Preview — and leaves `terminal` as-is (stays on Preview, showing the affordance). A code comment registers the deferral for Group D. `building→Steps` (required for the planning→Steps human-check) still changes the streaming default, so the one streaming-build-chrome spec was reconciled to select the Preview tab (build chrome still hosted there).
- **Files modified:** `PreviewPanel.tsx`, `PreviewPanel.test.tsx`
- **Verification:** degraded suite back to baseline parity (1 pre-existing failure, 10 passing); fidelity harness 8/8 green.
- **Committed in:** `14fd527b`

---

**Total deviations:** 2 (1 blocking-sequencing, 1 scoping/defer).
**Impact on plan:** No scope creep; the end state matches the plan's objective and verified acceptance. The deferred failed→Audit is registered for its natural home (42-03/Group D), avoiding a broken intermediate.

## Issues Encountered
- **Pre-existing test failures (out of scope, NOT introduced here):** 3 in `PreviewPanel.switcher.test.tsx` (`renderer-switcher` testid not found — a Phase-39 reskin drift) and 1 in `PreviewPanel.degraded.test.tsx` ("streaming+empty → keeps the neutral empty-state" — post-Phase-39 a streaming run shows build chrome, not the neutral copy). Both confirmed red on the Task-1 baseline via a temporary checkout. Left untouched per the scope boundary; zero net-new failures across all touched suites (106 passed / 4 pre-existing failed).

## Verification (actual output)
- `npx tsc --noEmit` → **0 errors** (full project; no mockApi noise present).
- `npx vitest run PreviewPanel DashboardLayout InlineClarifyActions RunChatLane StepsDrilldown StepsOverviewSpine AgentThinkingTab` → **106 passed, 4 failed** (the 4 = pre-existing baseline failures above).
- Task-specific: InlineClarifyActions + RunChatLane **42 passed**; Steps suites **18 passed**.
- `FIDELITY_CAPTURE=1 npx playwright test zzz-baseline --workers=1` → **8 passed** (incl. paused planning / clarify-awaiting / gate-awaiting captures).
- Grep gates: DashboardLayout `PlanningOverlay|<ReviewGatePanel|<QuestionnairePanel` == **0**; QuestionnairePanel/ReviewGatePanel imports == **0**; `ClarifyQuestion` in types == **1**; PreviewPanel name-gate delta vs baseline == **0** (3 pre-existing comment matches).
- `git diff --name-only 94707834~1..HEAD` → **all `frontend/**.ts(x)`** (INV-3 / LOCK-B: no backend/transport/golden/manifest files).

## KEEP-set / channel integrity
Confirmed intact: `reviewGateData`, `questionnaireData`, `questionnaireQuestions`, `questionnaireLoading`, `activePipelineRunId`; the `questionnaireData→questionnaireQuestions` effect; the `laneGate` mapping; `runLaneState`/`laneClarifyOpen`; and all submit handlers (`handleQuestionnaireSubmit`, `handleLaneSubmitAnswers`, `handleQuestionnaireSkip`, `handleRejectReview`, `handleCancelWorkflow`, `onApproveReview`, `onRedoReview`, `onUpdateSpecsReview`). The shared `submit_questionnaire` / `approve_review` channels are unchanged (only the inline passthrough props were added).

## Next Phase Readiness
- Ready for **42-03** (Group C lane composer hint + Group D failed tab/Audit-default + retire DegradedRunAffordance). **42-03 must land the `failed → Audit` default** together with dropping the Preview tab + retiring `DegradedRunAffordance` (deferred here — see Deviation 2).
- `ReviewGatePanel.tsx` intentionally retained; its parsers/discriminator are extracted into a shared module in **42-05**, which then deletes the file.

## Self-Check: PASSED
- `42-02-SUMMARY.md` present on disk.
- `QuestionnairePanel.tsx` deleted.
- Commits `94707834`, `14fd527b`, `c1673fa0` all present in git history.
- `ClarifyQuestion` resolves from `types/index.ts` (export count == 1).

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-14*

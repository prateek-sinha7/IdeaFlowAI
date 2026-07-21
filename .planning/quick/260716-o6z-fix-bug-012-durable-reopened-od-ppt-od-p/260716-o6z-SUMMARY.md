---
phase: quick-260716-o6z
plan: 01
subsystem: frontend-run-screen
tags: [bug-fix, BUG-012, preview-dispatch, reopen, frontend]
requires:
  - "DashboardLayout viewedRunType / effectiveReviseType (BUG-001/BUG-006)"
  - "PreviewPanel FIRST_PARTY_RENDERERS ppt/prototype dispatch (unchanged)"
provides:
  - "Durable viewed-run-type thread: page.tsx contentSourceRunType -> DashboardLayout -> PreviewPanel"
affects:
  - "Reopened od_ppt / od_prototype runs now render their typed deliverable, not blank"
tech-stack:
  added: []
  patterns: ["durable prop thread over recents-window lookup", "grep-style source-lock test"]
key-files:
  created:
    - frontend/src/app/dashboard/contentSourceRunType.source.test.ts
  modified:
    - frontend/e2e/tests/ts-t.history.spec.ts
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
decisions:
  - "Chose the durable fullRun.type thread (not the recents-window one-liner) so runs outside the recents window also render"
  - "Kept the !isPipelineRunning gate on viewedRunType so live launch->watch is byte-identical"
metrics:
  duration: "~25m"
  completed: "2026-07-16"
  tasks: 3
  files: 4
---

# Phase quick-260716-o6z Plan 01: BUG-012 durable reopened od_ppt/od_prototype render Summary

Reopening a completed od_ppt (or od_prototype) run rendered the shared run screen's Preview BLANK because the PreviewPanel render dispatch keyed on a stale `workflowType` default ("user_stories"); the fix threads the viewed run's REAL type (`fullRun.type`) end-to-end so the correct first-party renderer fires — for runs both inside and outside the recents window.

## What shipped

- **page.tsx** — new durable `contentSourceRunType` state (`WorkflowType | null`): SET from `fullRun.type` on reopen, CLEARED on the fresh-launch reset, PASSED to DashboardLayout. `WorkflowType` added to the `@/types/index` type-import (it was not previously imported).
- **DashboardLayout.tsx** — new `contentSourceRunType?: WorkflowType | null` prop, folded into `viewedRunType` (`contentSourceRunType ?? recentRuns?.find(...)?.type`), and the PreviewPanel render-dispatch prop changed from `workflowType={workflowType}` to `workflowType={effectiveReviseType}`. The IdeaInputPage/ComposerPage `workflowType={workflowType}` sites are untouched.
- **Tests** — `TS-T-04c` (mocked Playwright reopen proof for od_ppt + od_prototype) and `contentSourceRunType.source.test.ts` (source-lock).

PreviewPanel.tsx, FIRST_PARTY_RENDERERS, GenericDeliverablePreview, the P18 sandbox, and the SSE/reducer path are all untouched.

## Tasks & commits

| Task | Description | Commit |
| ---- | ----------- | ------ |
| 1 | RED — author TS-T-04c + source-lock, observed failing on the unmodified tree | `9320445f` |
| 2 | GREEN — thread the viewed run's real type (page.tsx + DashboardLayout.tsx) | `ef4ccd26` |
| 3 | Regression gate — verification only, no code edits (no regression found) | (no commit) |

## RED -> GREEN evidence

**Task 1 (RED, unmodified tree):**
- Source-lock: `npm test -- src/app/dashboard/contentSourceRunType.source.test.ts` -> **7 failed (7)**. All new tokens absent (`setContentSourceRunType`, `workflowType={effectiveReviseType}`, the durable viewedRunType fold) and the old PreviewPanel dispatch literal still present.
- TS-T-04c: `playwright test --project=mocked ts-t.history -g "TS-T-04c"` -> **1 failed**. `locator('iframe[title="Slide Deck Preview"]')` — "element(s) not found" (the reopened od_ppt run showed the blank "Output will appear here" state). This is the required fail-before evidence.

**Task 2 (GREEN, after the thread):**
- Source-lock: **7 passed (7)**.
- TS-T-04c: **1 passed (5.5s)** — the od_ppt "Slide Deck Preview" iframe renders AND the od_prototype "Prototype Preview" iframe renders; the blank state has count 0 in both.

## Verification (Task 3)

- `npx tsc --noEmit` -> **exit 0 (clean)**.
- At-risk vitest (contentSourceRunType.source, contentSourceRunScope.source, revisionFamilyLinkage.source, WorkflowHistory.genericReopen, DashboardLayout.laneTitle, DashboardLayout.launchLatch, PreviewPanel.genericDeliverable) -> **42 passed (42)**.
- Full vitest (`npm test`) -> **8 failed | 735 passed (743)**. The 8 reds are exactly the known pre-Phase-42 reds, all in files this plan did NOT touch: `HomeLaunchGrid.inspect` (2), `PreviewPanel.switcher` (3), `PreviewPanel.degraded` (1), `FilesTab.runInput` (2). No red in any file this plan modified — no regression.
- Mocked e2e (`playwright --project=mocked ts-t.history ts-u.revisions`) -> **11 passed, 0 failed** (incl. TS-T-04c; TS-U-03/TS-U-05 are pre-existing `test.fixme` skips, not failures).
- **SC-001**: grep of the DashboardLayout diff -> no new workflow-name string literal (the change keys on `effectiveReviseType` / `run.type`). PreviewPanel.tsx unchanged (0 matches in the commit's changed files). page.tsx is SC-001-exempt.
- **launch->watch byte-identity**: `viewedRunType` stays gated on `!isPipelineRunning`, so during live launch `effectiveReviseType === workflowType` — the PreviewPanel dispatch is unchanged for the launch path.

## Deviations from Plan

None — plan executed as written. Minor mechanics notes:
- The repo `test` npm script already passes `--run`, so the plan's `npm test -- --run <file>` doubles the flag and errors ("Expected a single value for option --run"); ran `npm test -- <file>` instead. Behavior identical.
- Source-lock: because `workflowType={workflowType}` also legitimately appears at the IdeaInputPage (:1652) and ComposerPage (:1687) sites, the "old dispatch gone" assertion targets the PreviewPanel site specifically via its adjacent `rawPipelineType` prop (whitespace-collapsed match), not a blanket `not.toContain`.

## Known Stubs

None.

## Deferred / Live proof

Executor did not run live Bedrock (per constraints). Live proof (reopen a real od_ppt run -> deck renders; reopen a real od_prototype run -> prototype renders) is deferred to the orchestrator.

## Self-Check: PASSED
- FOUND: frontend/src/app/dashboard/contentSourceRunType.source.test.ts
- FOUND: commit 9320445f (Task 1)
- FOUND: commit ef4ccd26 (Task 2)

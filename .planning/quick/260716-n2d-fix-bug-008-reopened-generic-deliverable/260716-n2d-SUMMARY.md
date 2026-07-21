---
phase: quick-260716-n2d
plan: 01
subsystem: frontend/run-screen-preview
tags: [bugfix, frontend, preview-panel, run-scope, sse]
requires: [feat/ui-2 @ 247372fe]
provides:
  - "Reopened generic/custom HTML deliverable renders the P18 sandboxed iframe (BUG-008)"
  - "pipeline_complete content-source set run-scoped by trackedRunIdRef (BUG-011)"
affects:
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/app/dashboard/page.tsx
tech-stack:
  added: []
  patterns: ["run-identity guard mirroring BUG-005 isForeignRun", "grep-style source-lock test"]
key-files:
  created:
    - frontend/src/app/dashboard/contentSourceRunScope.source.test.ts
  modified:
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/preview/PreviewPanel.genericDeliverable.test.tsx
    - frontend/e2e/tests/ts-t.history.spec.ts
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts
decisions:
  - "BUG-008 fixed via the PREFERRED decouple (knownContentPresent), not workflowType={viewedRunType} (recentRuns-membership gap)"
  - "BUG-011 guard reuses the existing trackedRunIdRef; NOT-foreign = launch->watch OR no-tracked-id, so the set stays byte-identical for the launched run"
metrics:
  duration: ~15m
  completed: 2026-07-16
---

# Phase quick-260716-n2d Plan 01: Reopened Generic Deliverable + Run-Scoped Completion Summary

Two frontend "run-screen state not bound to the viewed run" fixes: a reopened generic/custom HTML deliverable now renders the P18 sandboxed iframe instead of "Output will appear here" (BUG-008), and a foreign concurrent run's `pipeline_complete` can no longer hijack the viewed content-source (BUG-011) — while the primary launch→watch flow stays byte-identical.

## What was built

### Task 1 — BUG-008 (commit 3cce39df)
- `PreviewPanel.tsx:577`: replaced `const hasGenericDeliverable = !isKnownRenderType && !!genericDeliverable?.content;` with a two-line decouple: `const knownContentPresent = !!(effUserStoryContent || effPptContent || effPrototypeContent || pptxCode);` then `const hasGenericDeliverable = !!genericDeliverable?.content && (!isKnownRenderType || !knownContentPresent);`. A present generic deliverable now counts whenever the typed renderer for the (possibly-stale) renderType has nothing to show. `renderDeliverable()`, `GenericDeliverablePreview`, and the P18 `sandbox="allow-scripts"` contract are untouched.
- Added a `describe("BUG-008 — reopened generic deliverable survives a STALE workflowType")` block to `PreviewPanel.genericDeliverable.test.tsx` with two cases (stale `workflowType="user_stories"` + empty typed content: text/html → sandboxed iframe no `allow-same-origin` + no empty state; text/markdown → MarkdownPreview no iframe) plus a local `terminalPipelineState()` helper.
- Un-`fixme`'d TS-T-04b at `ts-t.history.spec.ts:166` (body unchanged).

**RED→GREEN:** the two new cases were observed RED (both rendered "Output will appear here") against the unmodified `:577`; GREEN (13/13 in the file) after the edit.

### Task 2 — BUG-011 (commit e604b361)
- `page.tsx:530` (inside `pipeline_complete`): replaced the unconditional `if (data.pipeline_run_id) setContentSourceRunId(data.pipeline_run_id as string);` with a run-scoped guard mirroring the BUG-005 `isForeignRun` shape: `const completingRunId = data.pipeline_run_id as string | undefined;`, `const isForeignCompletion = !!completingRunId && !!trackedRunIdRef.current && completingRunId !== trackedRunIdRef.current;`, then `if (completingRunId && !isForeignCompletion) setContentSourceRunId(completingRunId);`. When the completing run IS the tracked/launched run OR there is no tracked id yet, it is NOT foreign → the set runs byte-identically; only a genuine foreign concurrent completion is skipped. `trackedRunIdRef` decl/sync/launch-set and the pipeline_start `isForeignRun` guard are untouched.
- Created `contentSourceRunScope.source.test.ts` (mirrors `reviseGuard.source.test.ts`): asserts the old unconditional set is gone, `isForeignCompletion` gates the set, and the launch pins (`trackedRunIdRef.current = launchedRunId;`, `const isForeignRun =`) remain.

**RED→GREEN:** the source-lock was observed RED (2 failed — old line present, `isForeignCompletion` absent) against the unmodified `page.tsx`; GREEN (3/3) after the guard edit.

### Task 3 — Regression gate
No code edits. All gates green offline.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated an at-risk source-lock that pinned the exact refactored token**
- **Found during:** Task 2 verification.
- **Issue:** `revisionFamilyLinkage.source.test.ts:36` asserted the literal `setContentSourceRunId(data.pipeline_run_id` — the exact line the BUG-011 guard refactors. My change renamed the argument to a local `completingRunId` (`= data.pipeline_run_id`), so the stale token assertion went RED even though the semantic (live completion still sets the source) is preserved.
- **Fix:** updated that one assertion to the post-fix equivalent — asserts `const completingRunId = data.pipeline_run_id` and `setContentSourceRunId(completingRunId)`, preserving the pipeline_run_id linkage proof. The other two lifecycle tokens (`setContentSourceRunId(fullRun.id)`, `setContentSourceRunId(null)`) are unchanged.
- **Files modified:** `frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts`
- **Commit:** e604b361 (bundled with the BUG-011 fix it locks)

## Verification

- `npx tsc --noEmit`: clean (from `frontend/`).
- **Task 1 RED→GREEN:** observed RED (empty state ×2) → GREEN (`PreviewPanel.genericDeliverable.test.tsx` 13/13).
- **Task 2 RED→GREEN:** observed RED (2 failed) → GREEN (`contentSourceRunScope.source.test.ts` 3/3).
- **Targeted suites GREEN:** `src/components/preview` (minus the 4 pre-existing reds below), `WorkflowHistory.genericReopen`, `DashboardLayout.laneTitle`, `DashboardLayout.launchLatch`, `reviseGuard.source`, `revisionFamilyLinkage.source` (4/4), `contentSourceRunScope.source` (3/3) — all pass.
- **Mocked e2e (killed :3000 first):**
  - `ts-t.history` → 6 passed, incl. TS-T-04b (reopened custom HTML renders the sandboxed Deliverable Preview iframe).
  - `ts-live-state ts-u.revisions ts-y.run-scope-clarify` → 9 passed, 5 skipped (pre-existing `.skip` on TS-U-03/04/05/06/08). TS-Y-01/02 (BUG-005 run-scope family) and the launch→watch regression (c) pass.
- **Full vitest:** 728 passed / 8 failed / 736 total. All 8 reds are the known pre-Phase-42 reds in UNTOUCHED files: `HomeLaunchGrid.inspect` (2), `PreviewPanel.degraded` (1), `FilesTab.runInput` (2), `PreviewPanel.switcher` (3). The degraded (1) + switcher (3) were confirmed IDENTICAL on the pre-fix baseline (`3cce39df^`) via a throwaway worktree — not regressions from my PreviewPanel.tsx edit. `HomeLaunchGrid.inspect` and `FilesTab.runInput` are files this plan never touched.
- **SC-001:** the PreviewPanel.tsx diff introduces NO workflow-name string literal — `knownContentPresent` keys on the variable names `effUserStoryContent`/`effPptContent`/`effPrototypeContent`/`pptxCode` (the only "user_stories" occurrence is inside a comment). page.tsx guard adds none.

## At-risk green (confirmed still passing)
`WorkflowHistory.genericReopen.test.tsx`, `DashboardLayout.laneTitle`, `DashboardLayout.launchLatch`, `reviseGuard.source`, `revisionFamilyLinkage.source`, and the mocked e2e specs `ts-live-state`/`ts-u.revisions`/`ts-y.run-scope-clarify`.

## Live verification (deferred to orchestrator)
The executor did NOT run a live Bedrock run. Orchestrator should confirm: (a) reopen a real custom HTML run → iframe renders; (b) two concurrent runs, a background completion does not re-point the viewed content-source.

## Self-Check: PASSED

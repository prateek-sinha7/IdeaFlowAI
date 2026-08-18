---
id: BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-012 follow-up — non-terminal reopen shows the stale "USER_STORIES" type
  label
status: open
applies_to:
  phases: []
  modules:
  - App
  - AppHeader
  - ComposerPage
  - DashboardLayout
  - IdeaInputPage
  - User
  - WorkflowRun
  - contentSourceRunType.source.test
  - getWorkflowLabel
  globs:
  - frontend/src/components/layout/DashboardLayout.tsx
  - AppHeader.tsx
  - page.tsx
  - DashboardLayout.tsx
  - PreviewPanel.tsx
  - contentSourceRunType.source.test.ts
  requirements: []
locked_constraints: []
verification:
  type: manual
  status: required
  test_files: []
compact_summary: 'The BUG-006/012 binding was gated on !isPipelineRunning, so a non-terminal reopen still showed the stale label; un-gates viewedRunType to prefer contentSourceRunType always.'
last_updated: '2026-08-14'
author: 'Bilal Arshad <bilala@hexaware.com>'
author_source: applies-to-glob
---

# BUG-012 follow-up — non-terminal reopen shows the stale "USER_STORIES" type label

> Frontend-only, cosmetic. The last tail of the stale-`workflowType` family: BUG-006 (label) + BUG-012 (render dispatch) bound the viewed-run type on TERMINAL reopens, but the binding is `!isPipelineRunning`-gated, so a NON-terminal reopen (a `clarifying`/`building`/`waiting_for_user` run opened from history) still falls back to the stale `workflowType` default. Surfaced live during the BUG-013 proof (`bug013-clarify-fixed.png`): a reopened od_prototype clarify run showed "USER_STORIES · Clarifying" in the lane AND a "User Stories" pill in the header. Executable spec for a `gsd-quick`.

## Root cause (VERIFIED to file:line)
`frontend/src/components/layout/DashboardLayout.tsx`:
- `viewedRunType` (`:1274-1277`) = `!isPipelineRunning && contentSourceRunId != null ? (contentSourceRunType ?? recentRuns?.find(...).type) : undefined`. The `!isPipelineRunning` gate makes it `undefined` for a NON-terminal reopen (a reopened clarify/build run is "running" — the durable replay left `isPipelineRunning` true), so `effectiveReviseType = viewedRunType ?? workflowType` (`:1278`) falls back to the stale `workflowType` state (default `"user_stories"`, its sync binder `:330` is itself `isRunning`-gated and never fires on reopen).
- Consumers that then show the stale label: the lane type label `runType={effectiveReviseType || pipelineState?.pipeline_type}` (`:1771`, BUG-006) and the PreviewPanel dispatch `workflowType={effectiveReviseType}` (`:1834`, BUG-012) — both go stale because `effectiveReviseType` is stale.
- SEPARATE stale surface: the header pill `<AppHeader pipelineType={workflowType} …>` (`:1475`) uses the RAW `workflowType` (not `effectiveReviseType`) → `AppHeader.tsx:150` renders `getWorkflowLabel(pipelineType)` = "User Stories" whenever `isPipelineRunning` (`AppHeader.tsx:140`). Display-only.

`contentSourceRunType` is set ONLY on reopen (`page.tsx handleSelectWorkflowRun`, BUG-012) and cleared on a fresh-launch reset (`page.tsx:1484`), so it is a reliable "this is a reopened run" signal independent of `isPipelineRunning`.

## The fix (two display bindings; launch flow byte-identical)
### 1. `DashboardLayout.tsx:1274-1277` — un-gate the durable type
```
// before:
const viewedRunType =
  !isPipelineRunning && contentSourceRunId != null
    ? (contentSourceRunType ?? recentRuns?.find((r) => r.id === contentSourceRunId)?.type)
    : undefined;
// after — prefer the durable reopened type regardless of running state; keep the recents
// fallback gated (contentSourceRunType is null on a fresh launch → launch stays byte-identical):
const viewedRunType =
  contentSourceRunType ??
  (!isPipelineRunning && contentSourceRunId != null
    ? recentRuns?.find((r) => r.id === contentSourceRunId)?.type
    : undefined);
```
Fixes the lane label (`:1771`), the PreviewPanel dispatch (`:1834`), and the revise-handler selection (`:1280`) for non-terminal reopens in one edit.

### 2. `DashboardLayout.tsx:1475` — bind the header pill to the viewed type
```
// before:  pipelineType={workflowType}
// after:   pipelineType={effectiveReviseType}
```
`effectiveReviseType` is in scope (declared `:1278`). During a LIVE LAUNCH `contentSourceRunType` is null and `viewedRunType` is undefined → `effectiveReviseType === workflowType` → the header pill is byte-identical. On a reopen it shows the viewed run's real type.

### Do NOT touch
- `IdeaInputPage workflowType={workflowType}` (`:1661`) and `ComposerPage workflowType={workflowType}` (`:1696`) — these are LAUNCH controls (the type you're about to launch/compose), correctly the launch `workflowType`. Leaving them is intentional.
- `PreviewPanel.tsx`, the reducer, the SSE path, the j1u/lb6/n2d/o6z/r7d fixes.

## Constraints
- Branch **feat/ui-2**. NO commit trailer. NEVER push. FE cwd-sensitive (from `frontend/`; kill :3000 before mocked Playwright). SC-001: both edits key on existing type variables (`contentSourceRunType`/`effectiveReviseType`), NO workflow-name literal added. Keep at-risk green: `DashboardLayout.laneTitle`, `DashboardLayout.launchLatch`, `ts-t.history` (terminal reopen label unchanged), `ts-u.revisions`, `ts-y.run-scope-clarify`, the `contentSourceRunType.source`/`revisionFamilyLinkage.source` locks. The "132/0" baseline is stale; the 8 pre-Phase-42 vitest reds in untouched files are NOT regressions.

## Verification (executor)
- `npx tsc --noEmit` clean.
- **Fail-before/pass-after:** a DashboardLayout (or source-lock) test proving a NON-terminal reopen (`contentSourceRunType="od_prototype"` / `contentSourceRunId` set / `isPipelineRunning=true` / stale `workflowType="user_stories"`) yields `viewedRunType="od_prototype"` (⇒ lane label + header pill show the prototype label, NOT "User Stories"); fail-before = stale. PLUS a no-regression assertion that a LIVE LAUNCH (`contentSourceRunType=null`, `isPipelineRunning=true`) leaves `viewedRunType` undefined ⇒ `effectiveReviseType === workflowType` (header/lane byte-identical). A source-lock mirroring `contentSourceRunType.source.test.ts` (assert the un-gated `viewedRunType` shape + `pipelineType={effectiveReviseType}`) is acceptable where rendering DashboardLayout is impractical.
- **No-regression:** terminal reopen label unchanged (still the viewed type); launch→watch header/lane byte-identical; at-risk suites green.
- Executor does NOT run live Bedrock — the orchestrator live-proves: reopen the clarify-paused od_prototype run → lane + header show a prototype label, not "USER_STORIES".

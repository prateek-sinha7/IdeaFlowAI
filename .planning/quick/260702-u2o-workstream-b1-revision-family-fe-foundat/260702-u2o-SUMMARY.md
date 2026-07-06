---
phase: 260702-u2o
plan: 01
subsystem: frontend-revision-families
tags: [revision-families, frontend, linkage, api-fetcher, contentSourceRunId]
requires:
  - "Workstream A backend (260702-s3p): WorkflowRunResponse.parent_run_id/root_run_id, GET /api/runs/{id}/family, IDOR-hardened parent-link ingress"
provides:
  - "getRunFamily(token, id) fetcher → GET /api/runs/{id}/family"
  - "RunFamily + FamilyMember raw wire types"
  - "WorkflowRun.parentRunId (null default) + rootRunId (own-id default) mapped in normalizeWorkflowRun"
  - "contentSourceRunId single-source-of-truth for the on-screen run id (page.tsx → DashboardLayout prop)"
  - "universal revision parent linkage: 4 inline handlers + 4 history callbacks send source_workflow_run_id/parent_run_id"
affects:
  - "B2/B3 (grouping, timeline, chips) and Workstream C build on getRunFamily + reliable linkage"
tech-stack:
  added: []
  patterns:
    - "raw snake_case wire types (like ChainContext) returned unnormalized from single-purpose fetchers"
    - "state lifted to page.tsx and threaded down as a prop (contentSourceRunId), replacing an in-component derived heuristic"
    - "source-lock vitest for wiring impractical to render (huge DashboardLayout/page.tsx)"
key-files:
  created:
    - frontend/src/lib/api.getRunFamily.test.ts
    - frontend/src/components/history/WorkflowHistory.revise.test.tsx
    - frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/types/index.ts
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/history/WorkflowHistory.tsx
    - frontend/src/components/history/WorkflowHistory.test.tsx
    - frontend/src/components/history/WorkflowHistory.genericReopen.test.tsx
decisions:
  - "contentSourceRunId owned by page.tsx (where pipeline_complete + reopen land), threaded to DashboardLayout as a prop — the single reliable source; the derived currentWorkflowRunId heuristic is deleted, not shadowed (INV-3, no dual impl)"
  - "history onRevise* callbacks gain a required 3rd param sourceRunId = selectedRun.id — history revisions previously sent no parent and orphaned runs"
  - "getRunFamily returns the raw unnormalized {root_id, members} shape (mirrors getChainContext) — no normalizer"
metrics:
  duration: ~9 min
  tasks: 3
  files: 10
  completed: 2026-07-02
---

# Phase 260702-u2o Plan 01: Workstream B1 — Revision-Family FE Foundation + Universal Linkage Summary

FRONTEND plumbing that consumes the Workstream-A backend: `getRunFamily` fetcher, `RunFamily`/`FamilyMember` types, `WorkflowRun.parentRunId`/`rootRunId`, and a `contentSourceRunId` single-source-of-truth that makes every revision launch path (4 inline handlers + 4 history callbacks) send parent linkage — deleting the fragile `currentWorkflowRunId` heuristic that orphaned history revisions.

## What Was Built

### Task 1 — API fetcher + types + WorkflowRun extension (commit 7098f811)
- `types/index.ts`: exported `FamilyMember` and `RunFamily` raw wire interfaces (snake_case on purpose, like `ChainContext`); `WorkflowRun` gains required `parentRunId: string | null` and `rootRunId: string` (D1/D2/D7).
- `api.ts`: imported `RunFamily`; `RawWorkflowRun` gains optional `parent_run_id`/`root_run_id` (legacy rows still parse); `normalizeWorkflowRun` maps `parentRunId: raw.parent_run_id ?? null` and `rootRunId: raw.root_run_id ?? raw.id` (standalone run → own root); new `getRunFamily(token, runId)` hits `GET /api/runs/{id}/family` with Bearer auth, returns the raw shape.
- Extended both `makeRun` fixtures (WorkflowHistory.test.tsx, WorkflowHistory.genericReopen.test.tsx) with `parentRunId: null` + `rootRunId: "run-1"` — the only 2 WorkflowRun literals besides `normalizeWorkflowRun` (confirmed by grep of `agentCount:`, `as WorkflowRun`, `: WorkflowRun`, `WorkflowRun = {`; no other literal-construction site found).

### Task 2 — contentSourceRunId lift + universal revision linkage (commit 17562b1e)
- `page.tsx`: `contentSourceRunId` state; set from `data.pipeline_run_id` in the pipeline_complete handler (live), from `fullRun.id` in `handleSelectWorkflowRun` (reopen), cleared with `setContentSourceRunId(null)` in the fresh non-revision branch of the onStartPipeline wrapper; prop passed as `contentSourceRunId={contentSourceRunId}`.
- `DashboardLayout.tsx`: `contentSourceRunId?: string | null` prop added + destructured; the fragile `currentWorkflowRunId` heuristic DELETED. handleRevisePpt now gates + payloads on `contentSourceRunId` (run_revision `parent_run_id`); handleReviseUserStory / handleRevisePrototype / handleReviseAppBuilder all send `contentSourceRunId ? { source_workflow_run_id: contentSourceRunId } : undefined` as the onStartPipeline 6th arg (deps updated). The 4 history `onRevise*` inline callbacks each gain a 3rd `sourceRunId` param threaded as `source_workflow_run_id: sourceRunId` — the core orphan fix.
- `WorkflowHistory.tsx`: the 4 `onRevise*` prop signatures gain a required `sourceRunId: string` 3rd param; the detail-view reviseCallback builders pass `selectedRun.id`. The unrelated preview `onRevise={undefined}` props were left untouched.
- WS-field distinction preserved: handleRevisePpt uses `parent_run_id` (run_revision WS message); the run_pipeline paths use `source_workflow_run_id` (onStartPipeline 6th context arg).

### Task 3 — vitest coverage (commit 9a8da4d0)
- `api.getRunFamily.test.ts` (global.fetch mock): getRunFamily called once with url containing `/api/runs/run-1/family`, method GET, `Authorization: "Bearer tok"`, returns the parsed body verbatim; normalizeWorkflowRun maps `parent_run_id`/`root_run_id` when present and falls back to `null`/own-id when absent.
- `WorkflowHistory.revise.test.tsx` (real render): opens a completed prototype run's "Revise Prototype" affordance, types + sends, asserts `onRevisePrototype` called with `(instruction, output, "hist-7")` — proving selectedRun.id is forwarded.
- `revisionFamilyLinkage.source.test.ts` (source-lock): DashboardLayout has no `const currentWorkflowRunId` and no `workflowType + "_revision"`, and contains `parent_run_id: contentSourceRunId`, `source_workflow_run_id: contentSourceRunId`, `source_workflow_run_id: sourceRunId`; page.tsx contains the three `setContentSourceRunId(...)` calls + `contentSourceRunId={contentSourceRunId}`.

## Verification Results
- `npx tsc --noEmit`: 3 errors total, ALL pre-existing (proven via `git stash` on clean HEAD 99125327): `e2e/fixtures/mockApi.ts:95,96` TS2352 (long-documented) + `src/components/workflow/IdeaInputPage.tsx:738` TS17001. ZERO new errors introduced by this plan.
- `npx vitest run` (Task 3 command — 3 new specs + 2 touched fixtures): **5 files passed, 25 tests passed**.
- INV-3: `git status backend/` empty — FRONTEND-ONLY change; the 5 backend characterization goldens + semantic-event multiset are untouched by construction (no engine/websocket/manifest edit). Backend golden battery not run (per plan).
- Known-red baseline NOT chased: full FE vitest suite not run; only the touched/new specs executed.

## Deviations from Plan
### Auto-fixed Issues
**1. [Rule 1 - Bug] Heuristic-removal comment embedded the forbidden literal**
- **Found during:** Task 3 (source-lock spec failed on `workflowType + "_revision"`).
- **Issue:** The explanatory comment I wrote when deleting the heuristic quoted the exact string `workflowType + "_revision"`, which the source-lock test asserts is absent from DashboardLayout.tsx.
- **Fix:** Reworded the comment to describe the double-revision-suffix branch in prose without the literal.
- **Files modified:** frontend/src/components/layout/DashboardLayout.tsx
- **Commit:** 9a8da4d0 (folded into the Task 3 test commit, since it is the fix that makes the source-lock spec green).

**2. [Rule 3 - Test robustness] userEvent.type dropped chars under re-render churn**
- **Found during:** Task 3 (revise spec received only "m").
- **Issue:** The detail view re-renders per keystroke; `userEvent.type` registered only the first character.
- **Fix:** Switched to `fireEvent.change` to set the controlled textarea value in one shot.
- **Files modified:** frontend/src/components/history/WorkflowHistory.revise.test.tsx
- **Commit:** 9a8da4d0.

## Grep confirmation (WorkflowRun literal sites)
Grep of `agentCount:`, `as WorkflowRun`, `: WorkflowRun`, `WorkflowRun = {` found only the 3 anticipated sites (normalizeWorkflowRun + the 2 makeRun fixtures). No additional literal-construction site required patching.

## Deferred Issues (out of scope — pre-existing)
Logged to `deferred-items.md`: pre-existing tsc `IdeaInputPage.tsx:738` TS17001 and `mockApi.ts:95,96` TS2352 — present on clean HEAD, unrelated to revision families, in files this plan does not touch.

## Known Stubs
None. B1 is fetcher + types + state + payloads only; no UI stubs introduced. Visual grouping/timeline/chips are intentionally deferred to B2/B3 (scope fence); `parseRunInput` deferred to Workstream C.

## Self-Check: PASSED
- FOUND: frontend/src/lib/api.getRunFamily.test.ts
- FOUND: frontend/src/components/history/WorkflowHistory.revise.test.tsx
- FOUND: frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts
- FOUND commits: 7098f811, 17562b1e, 9a8da4d0

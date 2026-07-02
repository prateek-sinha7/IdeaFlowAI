---
phase: 260702-u2o
verified: 2026-07-02T22:05:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 260702-u2o Plan 01: Workstream B1 — Revision-Family FE Foundation + Universal Linkage Verification Report

**Phase Goal:** FE plumbing that consumes the shipped Workstream-A backend: getRunFamily fetcher + RunFamily/FamilyMember types + WorkflowRun.parentRunId/rootRunId; contentSourceRunId replacing the fragile currentWorkflowRunId heuristic; universal revision linkage (4 inline handlers + 4 history onRevise* callbacks send the parent run id). Frontend-only, ZERO backend edits.
**Verified:** 2026-07-02T22:05:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | getRunFamily(token,id) → GET /api/runs/{id}/family with Bearer, returns parsed {root_id, members} | ✓ VERIFIED | api.ts:346-354 `getRunFamily` returns `request<RunFamily>(\`/api/runs/${runId}/family\`, {method:"GET", headers: authHeaders(token)})`. Test api.getRunFamily.test.ts:26-56 asserts url contains `/api/runs/run-1/family`, method GET, `Authorization === "Bearer tok"`, and `result` deep-equals parsed body incl `members[0].revision_index`. Real global.fetch mock — not vacuous. |
| 2 | normalizeWorkflowRun maps parentRunId (default null) + rootRunId (default own id) from raw snake_case | ✓ VERIFIED | api.ts:269-270 RawWorkflowRun gains optional `parent_run_id`/`root_run_id`; api.ts:305-306 maps `parentRunId: raw.parent_run_id ?? null`, `rootRunId: raw.root_run_id ?? raw.id`. types/index.ts:304-305 WorkflowRun has REQUIRED `parentRunId: string|null` + `rootRunId: string`. Test asserts both present-case (p-1/r-1) and absent-case (null / own id). |
| 3 | Every revision launch path sends parent linkage (4 inline from contentSourceRunId, 4 history threading selectedRun.id) | ✓ VERIFIED | Inline: handleRevisePpt (DashboardLayout.tsx:467,471 `parent_run_id: contentSourceRunId` via run_revision WS msg); handleReviseUserStory :508, handleRevisePrototype :528, handleReviseAppBuilder :540 each send `contentSourceRunId ? {source_workflow_run_id: contentSourceRunId} : undefined` as onStartPipeline 6th arg. History: 4 onRevise* inline callbacks :1260/1271/1280/1289 thread `sourceRunId → source_workflow_run_id: sourceRunId`. WorkflowHistory.tsx:42-45 signatures gain 3rd param `sourceRunId: string`; call sites :477-480 pass `selectedRun.id`. WorkflowHistory.revise.test.tsx is a real render→click→type→send test asserting spy called with `(instruction, output, "hist-7")`. WS-field distinction (parent_run_id vs source_workflow_run_id) preserved. |
| 4 | Fragile currentWorkflowRunId heuristic + `workflowType + "_revision"` never-match GONE | ✓ VERIFIED | grep `const currentWorkflowRunId` → empty; grep `workflowType + "_revision"` → empty in DashboardLayout.tsx. Only prose comments (:64,452,456) reference the name for documentation, which is permitted. Source-lock test asserts both absent. |
| 5 | contentSourceRunId set on pipeline_complete + reopen, cleared on fresh run | ✓ VERIFIED | page.tsx:122 state; :435 set from `data.pipeline_run_id` inside the `pipeline_complete` handler; :1142 set from `fullRun.id` on reopen; :1316 `setContentSourceRunId(null)` inside the `if (!isRevision)` fresh-run branch; :1323 prop passed `contentSourceRunId={contentSourceRunId}`. |
| 6 | FE-only, INV-3 holds; tsc clean; touched vitest green | ✓ VERIFIED | `git diff --name-only 99125327..HEAD` → 10 files, ALL under frontend/src/**; zero backend/. tsc: only 3 known pre-existing errors, zero new (see below). vitest: 5 files / 25 tests passed. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| frontend/src/lib/api.ts | getRunFamily + raw parent/root fields + normalize mapping | ✓ VERIFIED | :346 fetcher, :269-270 raw fields, :305-306 mapping. Wired: imported RunFamily :10. |
| frontend/src/types/index.ts | RunFamily + FamilyMember + WorkflowRun.parentRunId/rootRunId | ✓ VERIFIED | :316 FamilyMember, :327 RunFamily, :304-305 required fields. |
| frontend/src/app/dashboard/page.tsx | contentSourceRunId state + setters + prop pass-down | ✓ VERIFIED | :122/435/1142/1316/1323. |
| frontend/src/components/layout/DashboardLayout.tsx | prop; heuristic deleted; 4 inline + 4 history wirings | ✓ VERIFIED | :64 prop, :248 destructure, heuristic gone, 8 linkage sites. |
| frontend/src/components/history/WorkflowHistory.tsx | onRevise* gain sourceRunId; call sites pass selectedRun.id | ✓ VERIFIED | :42-45 signatures, :477-480 call sites. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| DashboardLayout.tsx | onStartPipeline 6th arg | source_workflow_run_id = contentSourceRunId | ✓ WIRED | :508/528/540 |
| WorkflowHistory.tsx → DashboardLayout history wiring | onStartPipeline | source_workflow_run_id: sourceRunId | ✓ WIRED | WH :477-480 pass selectedRun.id → DL :1268/1277/1286/1295 |
| page.tsx | DashboardLayout contentSourceRunId prop | setContentSourceRunId(pipeline_run_id)/(fullRun.id) | ✓ WIRED | :435/1142/1323 |
| api.ts | GET /api/runs/{id}/family | request<RunFamily> | ✓ WIRED | :350 template literal matches pattern |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Type check (whole FE project) | `npx tsc --noEmit` | 3 errors, all pre-existing (mockApi.ts:95,96 TS2352; IdeaInputPage.tsx:738 TS17001) — files NOT touched by this plan; 0 new | ✓ PASS |
| Fetcher/mapping/linkage/source-lock specs | `npx vitest run <5 specs>` | `Test Files 5 passed (5) / Tests 25 passed (25)` in 1.27s | ✓ PASS |

### Probe Execution

Not applicable — FE-only change, no project probes declared or implied. Verification is the tsc + vitest gates above.

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| B1-1 | getRunFamily fetcher | ✓ SATISFIED | Truth 1 |
| B1-2 | RunFamily/FamilyMember types + WorkflowRun extension | ✓ SATISFIED | Truth 2 |
| B1-7 | Universal revision linkage | ✓ SATISFIED | Truth 3 |
| D1/D2/D7 | Child-run family model unified at read layer, contentSourceRunId source-of-truth, universal parent linkage | ✓ SATISFIED | Truths 2,3,4,5 |

### Anti-Patterns Found

None. No TBD/FIXME/XXX debt markers, no stubs, no empty handlers, no hardcoded-empty rendered data. The only `undefined` values are the intentional `X ? {...} : undefined` 6th-arg pattern (matching brownfield idiom) and the unrelated preview `onRevise={undefined}` props explicitly left untouched per plan scope fence.

### Human Verification Required

None. B1 is deterministic FE plumbing (fetcher + types + state + payloads); all behavior is offline-verifiable via tsc + vitest, both run and green. The live/visual surface (grouping, timeline, chips) is explicitly deferred to Workstream B2/B3 by the scope fence.

### Gaps Summary

No gaps. All 6 must-have truths verified against real code and confirmed by self-run gates:
- tsc --noEmit produces only the 3 documented pre-existing errors (in mockApi.ts and IdeaInputPage.tsx, neither touched by this plan) — zero new errors in any touched file.
- The 5 target vitest specs pass 25/25.
- Every revision launch path (4 inline + 4 history) now sends parent linkage; the history callbacks — which previously sent nothing and orphaned runs — now forward selectedRun.id, proven by a real render→click→submit behavior test (not source-lock).
- The fragile currentWorkflowRunId heuristic and its `workflowType + "_revision"` never-match literal are deleted (only prose comments reference the name).
- All 10 changed files are under frontend/src/**; zero backend files touched — INV-3 holds by construction.

---

_Verified: 2026-07-02T22:05:00Z_
_Verifier: Claude (gsd-verifier)_

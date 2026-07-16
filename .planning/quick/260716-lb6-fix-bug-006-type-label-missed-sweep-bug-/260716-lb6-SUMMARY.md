---
phase: quick-260716-lb6
plan: 01
subsystem: frontend/run-screen
tags: [bugfix, react, strictmode, viewed-run-binding, idempotency]
requires: []
provides:
  - "lane-run-type chip bound to the viewed run (effectiveReviseType)"
  - "StrictMode-safe single-mint latches on both launch consumers"
affects:
  - frontend/src/components/layout/DashboardLayout.tsx
tech-stack:
  added: []
  patterns: ["useRef object-identity latch for effect idempotency"]
key-files:
  created:
    - frontend/src/components/layout/DashboardLayout.launchLatch.test.tsx
  modified:
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx
decisions:
  - "Bound the lane-run-type chip to the already-in-scope effectiveReviseType (viewedRunType ?? workflowType) — no new workflow-name literal (SC-001)."
  - "Latch on object identity (=== pendingOd*Params) placed BEFORE any side effect so the second StrictMode mount-invoke early-returns; a fresh param object still mints."
metrics:
  duration: "~25m"
  completed: "2026-07-16"
  tasks: 3
  files-changed: 3
  commits: 2
---

# Phase quick-260716-lb6: BUG-006 type-label missed-sweep + BUG-007 double-mint latch Summary

One-liner: Closed the FE viewed-run-binding cluster — the lane-run-type chip now tracks the VIEWED run's type (BUG-006) and each UI launch mints exactly one run under StrictMode via `useRef` object-identity latches on both launch consumers (BUG-007).

## What Was Built

- **BUG-006** — `DashboardLayout.tsx:1745` `runType` feed changed from `workflowType || pipelineState?.pipeline_type` to `effectiveReviseType || pipelineState?.pipeline_type`. `effectiveReviseType` (= `viewedRunType ?? workflowType`, already declared at :1252) resolves to the viewed run's own `type` on a completed history/recents reopen, and to `workflowType` on a fresh launch/live run (byte-identical). The `laneTitle` test was extended: the RunChatLane stub now echoes `runType` into `data-testid="lane-run-type"`, `makeRun` accepts a `type` arg, and a BUG-006 describe block asserts the chip tracks the viewed type across a mixed-type recents plus a launch-null no-regression guard.
- **BUG-007** — two `useRef<object | null>` latches (`launchedProtoParamsRef`, `launchedPptParamsRef`) declared next to `pendingStartOnConnectRef`. Each launch-consumer effect (od_prototype, od_ppt) now compares its ref to the incoming param object immediately after the null-guard and before any side effect; a matching object early-returns, so React StrictMode's synchronous double mount-invoke mints once. A fresh param object (new identity) still mints. New `DashboardLayout.launchLatch.test.tsx` proves single-mint under StrictMode for both consumers plus the new-object re-mint.

## Commits

| Commit | Bug | Message |
| ------ | --- | ------- |
| `616d481a` | BUG-006 | fix(frontend): bind lane-run-type chip to the viewed run (BUG-006) |
| `c959fe44` | BUG-007 | fix(frontend): StrictMode-safe single-mint latch on both launch consumers (BUG-007) |

Two atomic commits (one per bug), no trailer, on `feat/ui-2`, not pushed.

## RED → GREEN Evidence

**BUG-006** (`DashboardLayout.laneTitle.test.tsx`):
- RED (pre-`:1745` fix): "viewed app_builder run…" expected `app_builder`, received `prototype`; "different viewed type deeper…" expected `user_stories`, received `prototype`. 2 failed | 4 passed. The stale `workflowType` (the `od_prototype.pending` latch value `prototype`) leaked into the chip.
- GREEN (post-fix): 6 passed — the two BUG-006 viewed-type assertions, the launch-null regression, and all 3 BUG-001 title tests.

**BUG-007** (`DashboardLayout.launchLatch.test.tsx`):
- RED (pre-latch): all 3 failed — `onStartPipeline` "called 2 times" for one param object (confirms StrictMode dev double mount-invoke is active in the harness) for both od_prototype and od_ppt.
- GREEN (post-latch): 3 passed — single-mint for od_prototype, single-mint for od_ppt twin, and a new param object re-mints (2 total calls).

## Verification

- `npx tsc --noEmit` — clean (run from `frontend/`, after each fix).
- Full FE vitest suite (`npm test`): **723 passed | 8 failed** across 101 files. The 8 reds are the documented pre-Phase-42 baseline, all in files untouched by this task: `HomeLaunchGrid.inspect` (2), `PreviewPanel.switcher` (3), `PreviewPanel.degraded` (1), `FilesTab.runInput` (2). This task touched only `DashboardLayout.tsx` + its 2 test files, so those files' pass/fail state is identical to before the commits. All DashboardLayout specs (laneTitle 6, launchLatch 3, and siblings) are GREEN.
- Mocked Playwright at-risk specs (`ts-u.revisions`, `ts-live-state`, `ts-y.run-scope-clarify`): 9 passed | 0 failed | 5 skipped (by-design `.skip`/lineage markers).
- **Full mocked Playwright baseline (real, supersedes the stale 132/0): 139 passed | 0 failed | 44 skipped.** The 44 skipped are the `zzz-baseline`/`zzz-shell-baseline` capture specs and backend-integration `.skip` markers.
- `revisionFamilyLinkage.source` (vitest) — GREEN in the full suite. No `page.tsx`, `next.config.ts` (StrictMode left ON), backend, or j1u-fix edits. No live Bedrock run (orchestrator owns the live check).

## Deviations from Plan

None — plan executed exactly as written. Both fixes are confined to the one `runType` line (006) plus two refs/two guards (007) in `DashboardLayout.tsx` and the two test files.

## Self-Check: PASSED

- `frontend/src/components/layout/DashboardLayout.tsx` — modified (runType feed + 2 refs + 2 guards). FOUND.
- `frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx` — extended. FOUND.
- `frontend/src/components/layout/DashboardLayout.launchLatch.test.tsx` — created. FOUND.
- Commit `616d481a` (BUG-006) — FOUND in git log.
- Commit `c959fe44` (BUG-007) — FOUND in git log.

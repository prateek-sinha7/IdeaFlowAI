---
phase: quick-260716-j1u
plan: 01
subsystem: frontend/run-screen
tags: [frontend, run-screen, sse, viewed-run-binding, revisions, clarify]
requires:
  - "feat/ui-2 SSE cutover (44-06/44-07) + DEF-44-12-4 durable-seed reopen"
provides:
  - "Run-scoped pipeline_start reset (trackedRunIdRef) — foreign runs can't wipe the viewed run's clarify"
  - "History row tap → shared run screen (onOpenRun) instead of the divergent RunDetailPage"
  - "Lane title bound to the viewed run (contentSourceRunId), not recents[0]"
  - "handleRevisePpt REST path fires on a reopened run; revise selector bound to the viewed run's type"
affects:
  - "frontend/src/app/dashboard/page.tsx"
  - "frontend/src/components/layout/DashboardLayout.tsx"
  - "frontend/src/components/history/WorkflowHistory.tsx"
tech-stack:
  added: []
  patterns: ["viewed-run binding via contentSourceRunId / trackedRunIdRef", "run-scoped SSE reducer side-effect guard"]
key-files:
  created:
    - "frontend/e2e/tests/ts-y.run-scope-clarify.spec.ts"
    - "frontend/src/components/history/WorkflowHistory.openRun.test.tsx"
    - "frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx"
    - "frontend/src/app/dashboard/reviseGuard.source.test.ts"
  modified:
    - "frontend/src/app/dashboard/page.tsx"
    - "frontend/src/components/layout/DashboardLayout.tsx"
    - "frontend/src/components/history/WorkflowHistory.tsx"
    - "frontend/e2e/tests/ts-u.revisions.spec.ts"
    - "frontend/e2e/tests/ts-t.history.spec.ts"
    - "frontend/e2e/fixtures/mockSse.ts"
decisions:
  - "Run-scope the pipeline_start RESET only (a targeted skip-when-foreign guard), not the RunConnectionProvider fan-out — safe default, no transport rewrite."
  - "Guard reads trackedRunIdRef.current (a ref), NOT activePipelineRunId/contentSourceRunId state — handleWebSocketMessage is useCallback([]) and a state read captures the stale initial null."
  - "BUG-005 authoritative fail-before/pass-after observes the LANE clarify (lane-clarify-status, activePipelineRunId-gated), NOT the Steps chat-clarify-actions (questionnaireQuestions-gated, never cleared)."
  - "BUG-003 e2e reproduces via the SELECTOR binding (fix 2) with a non-empty od_ppt reopen; the guard relaxation (fix 1) is pinned by the source-lock (the confirm chip needs runState=complete which needs non-empty content, so the empty-content path is not reachable in the mocked harness)."
metrics:
  duration: "~2.5h"
  completed: "2026-07-16"
---

# Phase quick-260716-j1u Plan 01: FE run-screen cluster (BUG-001/002/003/005) Summary

Fixed four live-QA run-screen bugs of one class — run-screen live state bound to the launched/latest run (or any concurrently-attached run) instead of the VIEWED run — frontend-only, one atomic commit per bug, each with a fail-before/pass-after test, then a regression-green gate.

## Commits

| Bug | Commit | Message |
|-----|--------|---------|
| BUG-005 | `8eec694c` | run-scope the pipeline_start reset so a concurrent foreign run can't wipe the viewed run's clarify |
| BUG-002 | `e8a22842` | route History row taps into the shared run screen via onOpenRun |
| BUG-001 | `cc2f98f7` | bind the run-lane title to the viewed run, not recents[0] |
| BUG-003 | `8b4e2eb7` | relax handleRevisePpt guard + bind revise selector to the viewed run's type |
| gate | `3c8945e0` | test: reconcile ts-t.history reopen cases to the BUG-002 shared-run-screen routing |

## Per-bug fail-before / pass-after evidence

**BUG-005 (Task 1)** — `ts-y.run-scope-clarify` (new).
- Fail-before (buggy code, with the ordered Steps-agent barrier so the foreign frame IS applied before the assertion): a foreign `pipeline_start` nulled `activePipelineRunId` → the lane fell clarify→building → `lane-clarify-status` disappeared / `lane-run-status` no longer "Clarifying" → **TS-Y-01 RED** (`expect(lane-clarify-status).toBeVisible() → element(s) not found`).
- Pass-after: guard skips the reset for a foreign `pipeline_run_id` → the clarify lane SURVIVES → **TS-Y-01 GREEN**. Positive control **TS-Y-02** (same-run `pipeline_start` STILL clears) GREEN before and after (guard is skip-when-foreign, not skip-always).
- Harness note: the initial attempt observed the Steps `chat-clarify-actions` card, which is gated only on `questionnaireQuestions.length` (never cleared by the reset — the sync effect at DashboardLayout.tsx:585 has no else branch), so it could not distinguish the bug. Switched to the LANE `lane-clarify-status` (activePipelineRunId-gated), which is the true symptom surface.

**BUG-002 (Task 2)** — `WorkflowHistory.openRun.test.tsx` (new, vitest).
- Fail-before: a row tap (id ≠ activeRunId) fell to `setSelectedRun` → RunDetailPage; `onOpenRun` never called → **RED** (`onOpenRun toHaveBeenCalledTimes(1)` timed out).
- Pass-after: `handleSelectRun` calls `onOpenRun(run); return;` and DashboardLayout passes it (byte-identical to the Home-recents wiring) → **GREEN**. KAN-96 active-run guard still routes live; no-onOpenRun legacy fallback preserved.

**BUG-001 (Task 3)** — `DashboardLayout.laneTitle.test.tsx` (new, vitest; RunChatLane stubbed to echo `runTitle=runHeaderTitle`, execution view forced via the od_prototype.pending sessionStorage latch).
- Fail-before: with `contentSourceRunId=B.id` over `recentRuns=[A,B,C]`, the title resolved to `recents[0]=A` → **2 RED** (B and a deeper-window C).
- Pass-after: `viewedRun = contentSourceRunId != null ? recentRuns.find(r => r.id === contentSourceRunId) : recentRuns[0]` → title = the viewed run's title → **GREEN**. Launch case (`contentSourceRunId=null` → recents[0]) byte-identical (green throughout).

**BUG-003 (Task 4)** — `reviseGuard.source.test.ts` (new, source-lock) + `ts-u.revisions` TS-U-09 (new, e2e).
- Source-lock: pins the relaxed guard `if (!contentSourceRunId && !pptxCode && !pptContent) return;` + the viewed-run-type selector `recentRuns?.find((r) => r.id === contentSourceRunId)?.type` and re-locks the Revision-Families linkage tokens — GREEN after fix, would be RED before (no such tokens).
- e2e TS-U-09 (reopened od_ppt run, stale workflowType): **RED demonstrated by a controlled temporary revert** of fix-2 (`effectiveReviseType = workflowType`) → the wrong handler (handleReviseUserStory, empty userStoryContent) no-ops → zero `run_revision` → timeout. Fix restored → **GREEN** (exactly one POST /api/runs/{parent}/revisions, parented to the reopened run).

## Real before/after mocked-spec + vitest counts (the "132/0" baseline was stale)

- **tsc `--noEmit`: clean** (verified after each task + final).
- **vitest (at-risk set: useRunChat, useWorkflow*, RunChatLane, revisionFamilyLinkage.source, reviseGuard.source, AgentThinkingTab, DashboardLayout*, WorkflowHistory*):** **131 passed / 0 failed** across 22 files (includes the 2 new suites + the new source-lock).
- **mocked Playwright (at-risk set: ts-j, ts-sse, ts-s.reconnect, ts-chat, ts-chat-cards, ts-t.history, ts-u.revisions, ts-live-state, ts-y.run-scope-clarify, ts-m.questionnaire):** **43 passed / 0 failed / 11 skipped** (skips = pre-existing `test.fixme` BE/persistence cases + the 1 new documented TS-T-04b fixme).
- At-risk-specific greens confirmed: `ts-u.revisions` TS-U-01 (`:86` parent-linkage + `ppt_output` target) GREEN, `revisionFamilyLinkage.source` GREEN, `useRunChat` GREEN, `ts-live-state` (DEF-44-12-4) GREEN.

## Deviations from Plan

### Auto-fixed / reconciled

**1. [Rule 3 - blocking test harness] BUG-005 observable corrected from Steps card to lane card.**
- Found during: Task 1. The plan suggested asserting `chat-clarify-actions` (or the questions). That surface is gated purely on `questionnaireQuestions.length`, which the reset never clears (no else branch in the DashboardLayout.tsx:585 sync effect), so it could not distinguish buggy vs fixed. Switched the fail-before/pass-after to the LANE `lane-clarify-status` + `lane-run-status` (both `activePipelineRunId`-gated) — the true BUG-005 symptom surface. Added an ordered Steps-agent barrier so the foreign frame is provably applied before the survival assertion.

**2. [Rule 1 - mock fidelity] `mockSse.start` now types the surfaced live run by its real `pipeline_type`.**
- Found during: Task 4. The lazy-attach placeholder typed EVERY launched run as `user_stories` on GET /api/runs. BUG-003's viewed-run-type selector then resolved a live-completed od_ppt run to `user_stories` → wrong handler → `ts-u.revisions` TS-U-01/02 regressed. The real GET /api/runs returns the true type, so this was a mock-fidelity gap. Fix: `start()` re-types the live run entry to its pipelineType. TS-U-01/02 restored; TS-U-09 green.

**3. [Changed-behavior reconcile] `ts-t.history` TS-T-03/04 rewired to the BUG-002 shared-run-screen routing (commit `3c8945e0`).**
- Found during: Task 5 gate. Both asserted the now-bypassed internal RunDetailPage reopen. Reconciled TS-T-03 (reopen → shared run screen shows output) and TS-T-04 (tap → shared run screen). Removed the now-unused RunDetailPage `/summary` stub. Never deleted a test.

### Known follow-ups (documented, NOT fixed — out of the 4-bug scope)

**DEF-BUG-002-generic-reopen** (`ts-t.history` TS-T-04b, `test.fixme`; see `deferred-items.md`): after BUG-002 routes custom/generic History taps to the shared run screen, its PreviewPanel renders the EMPTY state for a reopened generic/custom deliverable (the reopen seed doesn't repopulate `genericDeliverable` on this path). TYPED deliverables (user_stories/ppt/prototype/app_builder) render fine. The Home-recents path shares this gap, so BUG-002 exposed rather than introduced it; the sandbox SECURITY contract stays covered by `WorkflowHistory.genericReopen.test.tsx`.

**Plan-checker WARNING-2 (NOTED, not fixed):** BUG-005's `trackedRunIdRef` priority (`activePipelineRunId ?? contentSourceRunId`) can mistrack in the "background build A while viewing a DIFFERENT run C" case (outside the four bugs' scope). Not fixed now (risk); logged in `deferred-items.md` as a follow-up.

## SC-001 / at-risk compliance

- No workflow-name literal added to any guarded component (RunChatLane/LaneRunHeader/PreviewPanel). BUG-001/003 key only on generic run identity (`run.id`/`run.type`/`contentSourceRunId`); page.tsx is exempt (BUG-005).
- Preserved: `ts-u.revisions:86`, `revisionFamilyLinkage.source` pinned tokens, `useRunChat`, `ts-live-state` (DEF-44-12-4) — all GREEN.

## Live proof (NOT run by executor — orchestrator scope)

Relaunch prototype in isolation → clarify renders; two concurrent runs → the viewed run's clarify survives; open a live + a terminal run from History → correct title + chat lane + revise fires.

## Self-Check: PASSED
- Commits `8eec694c`, `e8a22842`, `cc2f98f7`, `8b4e2eb7`, `3c8945e0` all present in `git log`.
- Created files present: `ts-y.run-scope-clarify.spec.ts`, `WorkflowHistory.openRun.test.tsx`, `DashboardLayout.laneTitle.test.tsx`, `reviseGuard.source.test.ts`.

---
phase: 36-home-history-my-workflows-b2
plan: 05
subsystem: ui
tags: [react, history, revision-families, phase-32-tokens, a11y, run-detail, tdd]

# Dependency graph
requires:
  - phase: 36-home-history-my-workflows-b2 (36-04)
    provides: RunDetailPage + getRunSummary + src/lib/runStats.ts (single-source formatters)
  - phase: 36-home-history-my-workflows-b2 (36-02)
    provides: owner-scoped GET /api/runs/{id}/summary (the read the detail column consumes)
  - phase: 32
    provides: "@theme token layer + components/ui primitives (Badge, Tabs)"
provides:
  - History Today/Earlier/Older grouping + tokens/duration sort (client-side over existing fields)
  - Terminal-run detail promoted onto RunDetailPage (single source for KPI/agents/timeline/failure banner; in-panel duplicate retired)
  - WorkflowHistory + RevisionFamilyView reskinned onto Phase-32 tokens (retired-palette grep 0 on both)
affects: [phase-34 (live e2e verification), history, run-detail]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Date-bucket + sort layer OVER family grouping, derived from existing row fields (no fetch)"
    - "Detail wrapper composes the single-source RunDetailPage (summary column) + the deliverable it does not cover (right column)"

key-files:
  created:
    - frontend/src/components/history/WorkflowHistory.grouping.test.tsx
  modified:
    - frontend/src/components/history/WorkflowHistory.tsx
    - frontend/src/components/history/RevisionFamilyView.tsx
    - frontend/src/components/history/WorkflowHistory.test.tsx
    - frontend/src/components/history/WorkflowHistory.family.test.tsx
    - frontend/src/components/history/WorkflowHistory.genericReopen.test.tsx
    - frontend/src/components/history/WorkflowHistory.revise.test.tsx
    - frontend/src/components/history/WorkflowHistory.runInput.test.tsx

key-decisions:
  - "Two-column detail wrapper: RunDetailPage owns the summary surfaces; the deliverable preview/files/thinking/audit + revise/chain stay in the wrapper (CONTEXT: terminal run → the detail page; deliverable must not regress)"
  - "Bucket keyed on group.root.created_at; sort representative = the displayed latest member; sort applies within buckets (buckets stay date-ordered)"
  - "Failure-affordance + version-timeline coverage relocated to RunDetailPage (RunDetailPage.test owns the unit matrix); wrapper tests keep an integration-level guarantee"

patterns-established:
  - "bucketAndSortFamilies/dateBucketOf helpers live next to groupRunsByFamily in RevisionFamilyView (extend grouping helpers there, not inline)"
  - "Retired in-panel summary JSX replaced by a mount of the single-source page — no dual implementation (INV-12)"

requirements-completed: [SHELL-02, SHELL-03]

# Metrics
duration: 70min
completed: 2026-07-09
---

# Phase 36 Plan 05: History Restructure + RunDetailPage Promotion + Reskin Summary

**History now groups runs Today/Earlier/Older with a tokens/duration sort (client-side over existing fields), the terminal-run detail is promoted onto the single-source RunDetailPage (in-panel KPI/agents/version-timeline/failure duplicate retired), and WorkflowHistory + RevisionFamilyView are reskinned onto Phase-32 tokens — retired-palette grep 0 on both.**

## Performance

- **Duration:** ~70 min
- **Started:** 2026-07-09T05:04:00Z
- **Completed:** 2026-07-09T05:15:00Z
- **Tasks:** 3
- **Files modified:** 7 (+1 created)

## Accomplishments
- Today/Earlier/Older date buckets + Recent/Tokens/Duration sort over the family-grouped list, derived entirely from `created_at` / `duration` / `token_usage.total_tokens` already on each row — no backend change, no new fetch. Revision families stay intact (a family card matches if ANY member matches).
- Terminal-run detail promoted onto `<RunDetailPage>` (fed by `getRunSummary`): the hand-rolled KPI strip, per-agent breakdown, VersionTimeline mount and DegradedRunAffordance were retired from WorkflowHistory (no dual implementation, INV-12). The local `formatDuration`/`formatDate` were deleted — the run-detail formatters live once in `@/lib/runStats` via RunDetailPage.
- The deliverable the summary does not cover (preview/files/thinking/audit + revise/chain) is preserved in the right column of the detail wrapper; KAN-96 (running→live / terminal→detail) and KAN-92 (real async titles) preserved verbatim.
- Both files reskinned onto Phase-32 `@theme` tokens + `ui/` primitives; retired-palette grep 0 and stray-stock grep 0 on both; a11y on list rows, kebab, and delete modal.

## Task Commits

1. **Task 1: Today/Earlier/Older grouping + token/duration sort (TDD)** — `21c5cd6a` (test RED) + `e5ccb85f` (feat GREEN)
2. **Task 2: Promote detail onto RunDetailPage; preserve KAN-96/delete/families** — `47cf61a7` (feat)
3. **Task 3: Reskin WorkflowHistory + RevisionFamilyView onto Phase-32 tokens** — `714687c4` (feat)

## Files Created/Modified
- `frontend/src/components/history/RevisionFamilyView.tsx` — new `bucketAndSortFamilies`/`dateBucketOf`/`HistorySortKey` grouping+sort helpers; reskinned family cards, status dots, StatusBadge, RowMenu (kebab a11y), VersionTimeline chips onto tokens; row keyboard focusability
- `frontend/src/components/history/WorkflowHistory.tsx` — Today/Earlier/Older sections + sort control; detail wrapper now mounts `<RunDetailPage>` for the summary column (retired in-panel duplicate + local formatters); full token reskin + delete-modal a11y
- `frontend/src/components/history/WorkflowHistory.grouping.test.tsx` — new: pure bucket/sort assertions + rendered group headers + sort-control reorder + families-intact
- `WorkflowHistory.{test,family,genericReopen,revise,runInput}.test.tsx` — added `getRunSummary` to the api mocks (RunDetailPage is now mounted on detail-open); reconciled the family detail-timeline + terminal-failure assertions to their new home (RunDetailPage)

## Decisions Made
- **Detail composition (D-15 discretion):** the plan sanctioned keeping the tabbed preview/files/audit in the History wrapper OR threading them into RunDetailPage. Chose the two-column wrapper: `<RunDetailPage>` (summary) + the deliverable column. This honors CONTEXT ("a terminal run → the detail page") while preserving the deliverable/revise experience the summary endpoint does not cover.
- **Version switching:** the version timeline now lives in the RunDetailPage summary column (switches the summary via `getRunSummary`); the right-column deliverable stays keyed on the opened run. `handleSelectVersion` (which drove the retired in-panel timeline via `getWorkflow`) was removed as dead code.
- **Neutral empty-state:** for a terminal-FAILED/cancelled/degraded run with no deliverable, the right column suppresses the neutral "No preview available" — the RunDetailPage failure banner explains it (server-status-gated, SC-001).

## Deviations from Plan

None functional — the plan was executed as written. The plan explicitly granted D-15 executor discretion for the detail composition and anticipated test reconciliation; the following test maintenance was required and is in-scope:

### Test reconciliation (sanctioned by the plan's "keep the suites green" + D-15)

**1. [Test maintenance] `getRunSummary` added to five history test mocks**
- **Found during:** Task 2 — opening the detail now mounts RunDetailPage, which calls `getRunSummary`; the suites mocked `@/lib/api` without it and threw on the undefined export.
- **Fix:** benign reject-mock in genericReopen/revise/runInput/WorkflowHistory.test (RunDetailPage lands in its graceful error state; those suites assert the preserved right-column deliverable/footer); controllable resolve-mock in family.test + WorkflowHistory.test for the summary-fed surfaces.
- **Verification:** all 7 history suites green (35 tests).

**2. [Test maintenance] family detail-timeline + WorkflowHistory ISS-017 assertions relocated**
- **Found during:** Task 2 — the version timeline + failure affordance moved out of WorkflowHistory into the single-source RunDetailPage (INV-12). The family D4 "loads via getWorkflow" and the six in-panel ISS-017 affordance tests asserted the retired surfaces.
- **Fix:** family D4 now drives the RunDetailPage timeline via `getRunSummary` (radiogroup + active-chip-follows on the version read); WorkflowHistory's terminal-failure block now proves the wrapper→RunDetailPage wiring (failure banner + failed-agent names surface; neutral empty-state suppressed; content-wins right-column deliverable preserved). The exhaustive name-resolution matrix is unit-covered in `RunDetailPage.test.tsx` (from 36-04) — no net coverage loss.
- **Verification:** RunDetailPage.test 5/5 + reconciled suites all green.

---

**Total deviations:** 0 functional; 2 sanctioned test-reconciliation items.
**Impact on plan:** No scope creep. All hard guardrails held (KAN-96, KAN-92, no dual impl, formatter consolidation, retired-palette 0 on both, a11y, LOCK-B).

## Issues Encountered
- `tokenUsage` type requires `estimated_cost_usd`; grouping-test fixtures were updated to include it (tsc identity restored to 0).

## Known Stubs
None. The terminal-failure neutral-state suppression is intentional (the failure is explained by the RunDetailPage summary column), not a stub.

## Verification (offline)
- `npx vitest run src/components/history/` → 7 files / 35 tests passed
- retired-palette grep (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`) → 0 on WorkflowHistory.tsx AND RevisionFamilyView.tsx
- `grep -c 'RunDetailPage' WorkflowHistory.tsx` → 12 (detail promoted)
- KAN-96 `onViewRunningPipeline` early-return in `handleSelectRun` intact (lines 158-159)
- `grep -c 'function formatDuration' WorkflowHistory.tsx` → 0 (local dup deleted; consolidated onto runStats)
- `grep 'VersionTimeline|DegradedRunAffordance' WorkflowHistory.tsx` → none (in-panel detail retired)
- `npx tsc --noEmit` → 0 errors (identity, baseline 0)
- LOCK-B: no transport files touched (useWebSocket/useRunStream/layout untouched)
- Mocked Playwright e2e + live KAN-96 running→live SSE: LIVE-DEFERRED (offline, per phase contract)

## Next Phase Readiness
- 36-05 completes Phase 36's plan set (5/5). History is grouped/sortable, the run detail is the single-source RunDetailPage, and the largest reskin surface is on Phase-32 tokens.
- Live verification (real summary round-trip, running→live SSE, pixel visual) deferred to the Phase-34 / end-of-milestone live pass.

## Self-Check: PASSED
- FOUND: 36-05-SUMMARY.md
- FOUND: WorkflowHistory.grouping.test.tsx
- FOUND commits: 21c5cd6a, e5ccb85f, 47cf61a7, 714687c4

---
*Phase: 36-home-history-my-workflows-b2*
*Completed: 2026-07-09*

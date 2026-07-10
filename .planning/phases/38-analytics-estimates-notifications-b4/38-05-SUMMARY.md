---
phase: 38-analytics-estimates-notifications-b4
plan: 05
subsystem: ui
tags: [react, nextjs, analytics, estimates, vitest, tdd]

# Dependency graph
requires:
  - phase: 38-01
    provides: type_avg_duration_sec on /api/analytics/summary (owner-scoped per-type history average)
  - phase: 38-04
    provides: getAnalyticsSummary client + AnalyticsSummary.type_avg_duration_sec in api.ts
provides:
  - Real per-deliverable "~N agents · ~Xm" estimate line on each HomeLaunchGrid card
  - Tolerant, generic-keyed estimate (agents always; time only when owner-scoped history exists)
affects: [home, catalog, analytics, estimates]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Second tolerant fetch in an existing cancelled-guarded mount effect (agents-only degrade on analytics failure)"
    - "Generic row.id keying for a derived estimate — no workflow-name branch (SC-001/INV-1)"

key-files:
  created: []
  modified:
    - frontend/src/components/catalog/HomeLaunchGrid.tsx
    - frontend/src/components/catalog/HomeLaunchGrid.test.tsx
    - frontend/src/components/catalog/HomeLaunchGrid.inspect.test.tsx

key-decisions:
  - "agents = row.step_count (agent_count tolerated via safe cast, no new WorkflowSummary field)"
  - "minutes = round(type_avg_duration_sec[row.id]/60); render '~Xm' ONLY when a history entry exists — else omit the time clause (no fabricated time)"
  - "fetch getAnalyticsSummary(jwt, 'all'); tolerant .catch -> empty map so the grid never crashes"

patterns-established:
  - "Pattern: real derived estimate from additive analytics field, keyed generically, degrading gracefully"

requirements-completed: [SC-2, SHELL-05]

# Metrics
duration: ~20min
completed: 2026-07-10
---

# Phase 38 Plan 05: HomeLaunchGrid real estimate line Summary

**Each Home deliverable card now shows a REAL, generic-keyed `~N agents · ~Xm` estimate — agents from the `step_count` already on the wire, minutes from the owner-scoped per-type history average (`type_avg_duration_sec`), with the time clause omitted (never fabricated) when no history exists.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-10
- **Tasks:** 2
- **Files modified:** 3 (1 component, 2 test files)

## Accomplishments
- Extended the HomeLaunchGrid mount effect with a second, cancelled-guarded `getAnalyticsSummary(jwt, "all")` fetch (owner-scoped; tolerant `.catch` → empty map so the grid still renders agents-only if analytics is unavailable).
- Added a `text-ink-*` estimate line to each card: `~{agents} agents` always; ` · ~{minutes}m` only when `type_avg_duration_sec[row.id]` exists.
- Keyed purely on the generic `row.id` — no workflow-name branch introduced; no hardcoded `24m`/`5 agents` literal.
- TDD: RED estimate test observed failing before the implementation; GREEN after.

## Task Commits

1. **Task 1: Wave-0 failing estimate-line test (TDD RED)** - `7b418f68` (test)
2. **Task 2: Render the real estimate line on each card (TDD GREEN)** - `54058103` (feat)

## Files Created/Modified
- `frontend/src/components/catalog/HomeLaunchGrid.tsx` - second analytics fetch in the mount effect + per-card estimate line (agents always, minutes only with history), generic row.id keying, `text-ink-400` styling.
- `frontend/src/components/catalog/HomeLaunchGrid.test.tsx` - new estimate-line suite (with-history → `~3 agents · ~5m`; without-history → `~5 agents` only; owner-scoped `getAnalyticsSummary(token, "all")` keying) + `getAnalyticsSummary` added to the shared `@/lib/api` mock.
- `frontend/src/components/catalog/HomeLaunchGrid.inspect.test.tsx` - `getAnalyticsSummary` stub added to its `@/lib/api` mock (the grid's mount now requires it).

## Verification (observed)

- `npx vitest run src/components/catalog/HomeLaunchGrid.test` → the 2 new estimate tests PASS; DOM shows `~3 agents · ~5m` (with-history), `~5 agents` (without-history, no time clause), `~1 agents` (custom). Both render cases assert.
- Grep gates on `HomeLaunchGrid.tsx`: `getAnalyticsSummary|type_avg_duration_sec` = 3 (≥1 ✓); `step_count|agent_count` = 3 (≥1 ✓); not-hardcoded = 0 ✓; retired-palette = 0 ✓.
- name-branch grep = 2 — these are the PRE-EXISTING `handleClick` launch-routing lines (`if (type === "prototype")` / `if (type === "ppt")`), identical in committed HEAD; my estimate code adds ZERO name branches (delta = 0). See Deviations.
- `npx tsc --noEmit` (excl mockApi.ts) → 0 errors (identity baseline held).

## Decisions Made
- Used a safe cast `(row as WorkflowSummary & { agent_count?: number }).agent_count` for the `?? agent_count` fallback rather than adding a field to `WorkflowSummary` — honors the settled decision and the grep while keeping tsc identity and the additive constraint (no new field/table).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] getAnalyticsSummary missing from HomeLaunchGrid.inspect.test.tsx mock**
- **Found during:** Task 2 (adding the analytics fetch to the mount effect)
- **Issue:** The sibling `HomeLaunchGrid.inspect.test.tsx` mocks `@/lib/api` without `getAnalyticsSummary`; once the component's mount effect calls it, the mock returned `undefined` and the effect threw at mount, failing both inspect tests. Directly caused by this plan's new dependency.
- **Fix:** Added `getAnalyticsSummary: async () => ({ type_avg_duration_sec: {} })` to the inspect test's mock (a stub; no assertion weakened).
- **Files modified:** frontend/src/components/catalog/HomeLaunchGrid.inspect.test.tsx
- **Verification:** Both inspect tests pass again.
- **Committed in:** `54058103` (Task 2 commit)

**2. [Rule 3 - Blocking] tsc identity: partial AnalyticsSummary fixture cast**
- **Found during:** Task 2 (tsc identity gate)
- **Issue:** Casting a `{ type_avg_duration_sec: {...} }` fixture directly `as AnalyticsSummary` triggered TS2352 (insufficient overlap), a new error vs the 0-error baseline.
- **Fix:** Cast via `as unknown as AnalyticsSummary` on the two test fixtures.
- **Files modified:** frontend/src/components/catalog/HomeLaunchGrid.test.tsx
- **Verification:** `npx tsc --noEmit` (excl mockApi.ts) → 0.
- **Committed in:** `54058103` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3, directly caused by this plan). No scope creep — both were mock/type plumbing for the new dependency.

## Issues Encountered

- **Pre-existing failures (NOT caused here, out of scope):** The committed `HomeLaunchGrid.test.tsx` "Phase 21 — 'Your workflows' section + kebab" suite (5 tests) was already failing on the baseline (`git show HEAD:...test.tsx` → 5 failed | 2 passed) because that saved-workflows/kebab feature was moved out of `HomeLaunchGrid.tsx` to `SavedWorkflowsPage`. Left untouched (negative space: do not weaken/delete tests); logged to `deferred-items.md`.

## Next Phase Readiness
- SC-2 satisfied offline. Live round-trip / visual + mocked Playwright e2e remain LIVE-DEFERRED to Phase 34 per the plan's verification note. This is the last plan of Phase 38.

## Self-Check: PASSED

- All modified files present on disk (HomeLaunchGrid.tsx, .test.tsx, .inspect.test.tsx, 38-05-SUMMARY.md).
- Both task commits verified in git log: `7b418f68` (test RED), `54058103` (feat GREEN).

---
*Phase: 38-analytics-estimates-notifications-b4*
*Completed: 2026-07-10*

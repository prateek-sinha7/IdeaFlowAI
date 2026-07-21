---
phase: 36-home-history-my-workflows-b2
plan: 04
subsystem: ui
tags: [react, typescript, run-detail, run-summary, revision-timeline, phase-32-tokens, a11y, tdd]

# Dependency graph
requires:
  - phase: 36-02
    provides: "GET /api/runs/{id}/summary (RunSummaryResponse: id/title/type/status/duration/agent_count/token_usage/error/agents/root_id/members)"
  - phase: 36-01
    provides: "HomeLaunchGrid rename + fused Home recents strip (a caller of the run-detail page)"
  - phase: 32
    provides: "@theme token layer + ui/ primitives (Badge, Tabs) + status ramp"
provides:
  - "getRunSummary(token, runId) client + RunSummary/RunSummaryAgent response types in api.ts (mirrors backend RunSummaryResponse field-for-field)"
  - "RunDetailPage.tsx — self-contained run detail/reopen page fed by the summary endpoint (KPI + per-agent + VersionTimeline + DegradedRunAffordance)"
  - "src/lib/runStats.ts — shared formatDuration/formatTokenCount formatters (single source)"
affects: [36-05, history, run-detail, saved-workflows]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Interface-first API client: RunSummary type pinned before its consumers (page + Wave-3 History)"
    - "Reuse-don't-rebuild page composition: import shared surfaces (VersionTimeline/DegradedRunAffordance/parseFailedAgents/formatters), never re-implement (D-15/no dual impl)"
    - "Generic-keyed rendering (SC-001/INV-1): every branch on status/agents/tokens, never summary.type name"
    - "React sanctioned state-on-prop-change adjustment (prevRunId tracker) instead of a sync useEffect"

key-files:
  created:
    - frontend/src/components/history/RunDetailPage.tsx
    - frontend/src/components/history/RunDetailPage.test.tsx
    - frontend/src/lib/runStats.ts
  modified:
    - frontend/src/lib/api.ts

key-decisions:
  - "RunSummary mirrors RunSummaryResponse field-for-field (11 keys); members reuse FamilyMember so { root_id, members } slots straight into VersionTimeline as RunFamily"
  - "Extracted formatDuration/formatTokenCount into src/lib/runStats.ts (new single source) rather than re-implementing inline; WorkflowHistory's local copies retire with the in-panel duplicate in 36-05"
  - "Version-chip click refetches that member's summary by keying the mount-fetch on activeVersionId (family walk shares the read model)"

patterns-established:
  - "Summary-fed detail page: cancellable mount-fetch → generic-keyed compose of reused KPI/agent/timeline/failure surfaces on Phase-32 tokens"

requirements-completed: [SHELL-03]

# Metrics
duration: ~35min
completed: 2026-07-09
---

# Phase 36 Plan 04: RunDetailPage + getRunSummary Summary

**Self-contained Run detail/reopen page fed by `GET /api/runs/{id}/summary` — KPI strip, per-agent breakdown, revision `VersionTimeline`, and terminal-failure `DegradedRunAffordance` — reusing every shared surface (no dual implementation), generic-keyed on status/agents/tokens.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-09
- **Tasks:** 2
- **Files modified:** 4 (1 modified, 3 created)

## Accomplishments
- `getRunSummary(token, runId)` + `RunSummary`/`RunSummaryAgent` types in `api.ts`, mirroring the backend `RunSummaryResponse` field-for-field (owner-JWT `authHeaders`, `getRunFamily` idiom)
- `RunDetailPage` composes the KPI token strip, per-agent cards, reused `VersionTimeline`, and reused `DegradedRunAffordance` from the summary payload — keyed on generic run fields only (no `summary.type` branch)
- Extracted `formatDuration`/`formatTokenCount` into `src/lib/runStats.ts` as the single formatter source (imported, not inlined)
- `RunDetailPage.test.tsx` (5 tests, TDD): completed → KPI+agents+timeline; failed/degraded → DegradedRunAffordance; cancelled → cancelled copy; fetch error → graceful; back control aria; retired-palette absent in rendered class strings

## Task Commits

Each task was committed atomically:

1. **Task 1: getRunSummary client + RunSummary type** - `9dcaab0f` (feat)
2. **Task 2: RunDetailPage.tsx — reuse shared surfaces, feed off getRunSummary** - `fb0b5e9c` (feat, TDD test co-located)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified
- `frontend/src/lib/api.ts` - Added `RunSummary` + `RunSummaryAgent` interfaces (mirror `RunSummaryResponse`/`_SUMMARY_SAFE_AGENT_KEYS`) + `getRunSummary` client; imported `FamilyMember`
- `frontend/src/components/history/RunDetailPage.tsx` - The run detail/reopen page (cancellable mount-fetch, generic-keyed compose, Phase-32 tokens, a11y frame/tabs/back)
- `frontend/src/components/history/RunDetailPage.test.tsx` - 5 vitest tests (mock getRunSummary + motion proxy; real shared surfaces prove reuse)
- `frontend/src/lib/runStats.ts` - Shared `formatDuration` + `formatTokenCount` (single-source formatters)

## Type Parity Proof (RunSummary vs backend RunSummaryResponse)

| # | RunSummaryResponse (runs.py) | RunSummary (api.ts) |
|---|------------------------------|---------------------|
| 1 | `id: str` | `id: string` |
| 2 | `title: str` | `title: string` |
| 3 | `type: str` | `type: string` |
| 4 | `status: str` | `status: string` |
| 5 | `duration: Optional[float]` | `duration: number \| null` |
| 6 | `agent_count: int` | `agent_count: number` |
| 7 | `token_usage: dict` | `token_usage: { total_input_tokens?; total_output_tokens?; total_tokens? }` |
| 8 | `error: Optional[str]` | `error: string \| null` |
| 9 | `agents: list` | `agents: RunSummaryAgent[]` (mirrors `_SUMMARY_SAFE_AGENT_KEYS`) |
| 10 | `root_id: str` | `root_id: string` |
| 11 | `members: list[FamilyMemberResponse]` | `members: FamilyMember[]` |

No extra/missing key on either side. `RunSummaryAgent` mirrors `_SUMMARY_SAFE_AGENT_KEYS` (agent_id/name/role/icon/duration/error/input_tokens/output_tokens/total_tokens/cache_read_tokens/cache_write_tokens), all optional (server projects only present keys).

## Shared Surfaces Reused (imported, not rebuilt — D-15 / no dual impl)
- `VersionTimeline` from `./RevisionFamilyView` — revision/version chip row (self-hides < 2 members)
- `DegradedRunAffordance` from `@/components/preview/PreviewPanel` — terminal-failure banner
- `parseFailedAgentIds` + `buildAgentNameById` from `@/lib/parseFailedAgents` — failed-agent id parse + id→name map
- `formatDuration` + `formatTokenCount` from `@/lib/runStats` — duration/token formatters (extracted this plan)
- `Badge` + `Tabs` from `@/components/ui/*` — Phase-32 status pill + accessible tab controls

## Decisions Made
- See key-decisions frontmatter. Extracting the formatters into `runStats.ts` gives a single importable source; WorkflowHistory's local copies are left for 36-05 to retire with the whole in-panel duplicate (temporary, sanctioned duplication that dies with the panel).

## Deviations from Plan

None material. One in-task refinement (not a scoped deviation): replaced the initial `runId`-sync `useEffect` (which tripped `react-hooks/set-state-in-effect`) with React's sanctioned render-phase state-on-prop-change adjustment (`prevRunId` tracker) to reset the shown version without a cascading-render warning. The remaining single `set-state-in-effect` warning is inherent to the cancellable mount-fetch idiom and matches the accepted pre-existing pattern (SavedWorkflowsPage); 0 eslint errors.

## Verification (literal)

```
### grep -c 'getRunSummary' src/lib/api.ts
1
### grep -En imports (VersionTimeline|DegradedRunAffordance|parseFailedAgentIds|buildAgentNameById) RunDetailPage.tsx
13:import { parseFailedAgentIds, buildAgentNameById } from "@/lib/parseFailedAgents";
14:import { VersionTimeline } from "./RevisionFamilyView";
15:import { DegradedRunAffordance } from "@/components/preview/PreviewPanel";
### grep -c 'summary.type ===' RunDetailPage.tsx
0
### grep -rEn retired-palette RunDetailPage.tsx
(no matches)
### npx vitest run RunDetailPage.test.tsx
 Test Files  1 passed (1)
      Tests  5 passed (5)
### npx tsc --noEmit | grep -c error
0
```

Mocked Playwright e2e: LIVE-DEFERRED (offline; live summary round-trip → Phase 34).

## Issues Encountered
- The `VersionTimeline` radio accessible name for v2 contains "revises version 1", so a `getByRole("radio", {name:/version 1/i})` matched both chips. Resolved by asserting positionally (`getAllByRole("radio")[0]`/`[1]` + `toHaveAccessibleName`).
- The `DegradedRunAffordance` failed-agent list requires the `agent(s) failed: <ids>` marker (parseFailedAgents contract); the failed-run fixture error was adjusted to that persisted shape so the reused affordance resolves the agent name.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `getRunSummary` + `RunSummary` and `RunDetailPage` are the stable contract Wave-3 (36-05) History consumes to render detail and retire its inline duplicate (removing WorkflowHistory's in-panel detail incl. its local formatters — repoint onto `runStats.ts`).
- SHELL-03 FE half complete; live summary round-trip verification deferred to the milestone-end live pass (Phase 34).

## Self-Check: PASSED

- FOUND: frontend/src/components/history/RunDetailPage.tsx
- FOUND: frontend/src/components/history/RunDetailPage.test.tsx
- FOUND: frontend/src/lib/runStats.ts
- FOUND: .planning/phases/36-home-history-my-workflows-b2/36-04-SUMMARY.md
- FOUND commit: 9dcaab0f (Task 1)
- FOUND commit: fb0b5e9c (Task 2)

---
*Phase: 36-home-history-my-workflows-b2*
*Completed: 2026-07-09*

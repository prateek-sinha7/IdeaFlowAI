---
phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo
plan: 03
subsystem: frontend
tags: [react, nextjs, playwright, e2e, saved-workflows, launch-preload, composer]

# Dependency graph
requires:
  - phase: 21-01 (backend spine)
    provides: the owner-scoped /api/user-workflows CRUD + UserWorkflowResponse shape ({base_pipeline_type, agent_ids, model_overrides}) the launch replays
  - phase: 21-02 (FE save + catalog section)
    provides: api.ts UserWorkflowSummary + 4 CRUD fetchers; WorkflowCatalog "Your workflows" section + kebab + onLaunchSaved? (declared, optional); IdeaInputPage "Save workflow" button
provides:
  - IdeaInputPage initialAgentIds/initialModelOverrides props + guarded re-derive seed (the load-bearing launch preload)
  - DashboardLayout handleLaunchSaved + savedComposition state + onLaunchSaved wiring + IdeaInputPage seed threading
  - ts-z2.saved-workflows.spec.ts (mocked Playwright: compose -> Save -> appears -> rename -> launch)
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Launch = seed the composer (initialAgentIds/initialModelOverrides) + run UNCHANGED through handleRunPipeline -> startPipeline (pure-data replay, SC-001)"
    - "Guarded re-derive effect: early-return on initialAgentIds so the saved-workflow seed is not clobbered by the empty-for-custom filter"
    - "Saved-composition state carried via a NEW onLaunchSaved prop (onSelectFeature's bare WorkflowType cannot carry a composition); cleared on a normal select (no stale seed bleed)"
    - "Stateful per-spec Playwright mock of /api/user-workflows (GET reflects POST/PATCH/DELETE), registered AFTER goto for reverse-precedence over the fixtures catch-all"

key-files:
  created:
    - frontend/e2e/tests/ts-z2.saved-workflows.spec.ts
  modified:
    - frontend/src/components/workflow/IdeaInputPage.tsx
    - frontend/src/components/layout/DashboardLayout.tsx

key-decisions:
  - "Seed resolves against ALL_LIBRARY_AGENTS (LIBRARY_AGENTS ∪ CUSTOM_AGENTS), NOT the base LIBRARY_AGENTS the plan/pattern named — saved custom workflows reference CUSTOM_AGENTS which are absent from the base list (Rule 1 bug, caught by the launch e2e; without it launch loads 0 agents)"
  - "Faithful custom-compose path in the e2e: catalog '+ Create workflow' -> composer -> Advanced -> '+ Add agent' -> AgentLibrary '+ Add' -> Save, so the saved row is genuinely base_pipeline_type=custom (not a seeded-workflow shortcut)"
  - "Spec mock glob is **/api/user-workflows** (double-star), not *, so it also matches the /{id} sub-path used by PATCH/DELETE (a single * does not cross a / in Playwright glob → those would fall to the catch-all and break rename/delete)"

patterns-established:
  - "LAUNCH-EXISTING-PATH realized: a saved workflow launches by seeding the composer + running the existing path; re-validated server-side at launch (no engine/run-path edit, no `if saved` fork)"
  - "SC-001 held: onRun + handleRunPipeline bodies unchanged; the seed is purely additive (absent ⇒ the existing custom/idea flow is byte-for-byte preserved)"

requirements-completed: [LAUNCH-EXISTING-PATH, SAVE-FROM-BOTH, SC-001]

# Metrics
duration: ~9min
completed: 2026-06-14
---

# Phase 21 Plan 03: Saved-Workflow Launch Wiring + Mocked Playwright Spec Summary

**The ONE load-bearing FE change that makes a saved workflow launchable: `IdeaInputPage` gains `initialAgentIds`/`initialModelOverrides` props that seed `pipelineAgents` + `modelOverridesRef` (with the re-derive effect guarded so the seed survives), `DashboardLayout` carries the saved composition via a new `onLaunchSaved` prop into the composer, and Run flows UNCHANGED through `handleRunPipeline` → `startPipeline` — pure-data replay, zero engine edit (SC-001). A mocked Playwright spec proves the whole loop: compose → Save → appears in "Your workflows" → rename → launch pre-loaded.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-14T12:33Z
- **Completed:** 2026-06-14T12:42Z
- **Tasks:** 3
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- **`IdeaInputPage.tsx`** (load-bearing launch preload): added optional `initialAgentIds?: string[]` + `initialModelOverrides?: Record<string,string>` props. The `pipelineAgents` `useState` initializer now seeds from `initialAgentIds` (resolving each id through `ALL_LIBRARY_AGENTS`) when present, else keeps the existing `LIBRARY_AGENTS.filter(type)` derive. The re-derive effect is **guarded** with an early `return` keyed on `initialAgentIds?.length` so the seed is not clobbered on the first effect run (gotcha #1). `modelOverridesRef` is seeded from `initialModelOverrides ?? {}` (gotcha #3). `onRun` is **unchanged** — the seed flows through the existing run payload (`pipelineAgents.map(a=>a.id)` + `effectiveType` + ref overrides), so launch is pure data (SC-001).
- **`DashboardLayout.tsx`** (wiring): added `savedComposition` state (`{ agentIds, modelOverrides } | null`) + `UserWorkflowSummary` type import. `handleLaunchSaved(saved)` mirrors `handleSelectFeature` — stashes the saved triple, sets `workflowType = saved.base_pipeline_type`, routes to `mainView="input"`. `handleSelectFeature` clears the seed (`setSavedComposition(null)`) so a normal launch starts clean (T-21-12). `onLaunchSaved={handleLaunchSaved}` is passed to `WorkflowCatalog`; `initialAgentIds`/`initialModelOverrides` are threaded to `IdeaInputPage`. `handleRunPipeline` is **untouched** (no fork).
- **`ts-z2.saved-workflows.spec.ts`** (NEW mocked Playwright spec, `tier: "enterprise"`): TS-Z2-01 composes a custom workflow via the catalog "+ Create workflow" → composer → Advanced → "+ Add agent" → AgentLibrary "+ Add" → "Save workflow" → NameWorkflowModal, asserting the POST fired with the composer triple (`base_pipeline_type=custom`, non-empty `agent_ids`). TS-Z2-02 asserts a saved row appears in "Your workflows", renames it via the kebab → NameWorkflowModal (prefilled) → PATCH (label updates optimistically), and launches the row → `IdeaInputPage` opens **pre-loaded** (2 seeded agents, "Run workflow" enabled — not "Add agents first"). The mock of `**/api/user-workflows**` is stateful (GET reflects POST/PATCH/DELETE) and registered after `dashboard.goto()` for reverse-precedence over the fixtures catch-all; `fixtures/` untouched.

## Task Commits

1. **Task 1: IdeaInputPage launch preload — props + guarded re-derive seed** — `e49ccac7` (feat)
2. **Task 2: DashboardLayout — handleLaunchSaved + savedComposition + onLaunchSaved wiring + seed threading** — `e6b38a9b` (feat)
3. **Task 1 bug-fix: resolve seed against ALL_LIBRARY_AGENTS** — `569aa93d` (fix) *(deviation, see below)*
4. **Task 3: mocked Playwright spec** — `1c42455c` (test)

## Files Created/Modified

- `frontend/src/components/workflow/IdeaInputPage.tsx` — `initialAgentIds?`/`initialModelOverrides?` props; seed `pipelineAgents` (via `ALL_LIBRARY_AGENTS`) + `modelOverridesRef`; guarded re-derive effect; `onRun` unchanged.
- `frontend/src/components/layout/DashboardLayout.tsx` — `savedComposition` state + `UserWorkflowSummary` import + `handleLaunchSaved`; `onLaunchSaved` to WorkflowCatalog; seed threading to IdeaInputPage; seed cleared on a normal select; `handleRunPipeline` unchanged.
- `frontend/e2e/tests/ts-z2.saved-workflows.spec.ts` — NEW mocked spec (compose → Save → appears → rename → launch); 2/2 green.

## Decisions Made

- **Seed resolution superset.** The plan/pattern said resolve `initialAgentIds` via `LIBRARY_AGENTS`. In fact the custom agents (`market-research-agent`, `swot-analyst`, …) live in the separate `CUSTOM_AGENTS` export and are absent from `LIBRARY_AGENTS`; the composer's own `AgentLibrary` resolves against `[...LIBRARY_AGENTS, ...CUSTOM_AGENTS]` (`ALL_LIBRARY_AGENTS`). The launch seed had to match that superset, otherwise launching a saved custom workflow resolved to 0 agents. Tracked as a Rule 1 bug (below).
- **Faithful custom-compose path in the e2e** (vs. a seeded-workflow shortcut for the Save step): the spec drives the real custom composer entry so the persisted row is genuinely `base_pipeline_type=custom` — the exact shape launch replays.
- **`**/api/user-workflows**` glob** (double-star): a single `*` does not cross a `/` in Playwright glob, so PATCH/DELETE on `/api/user-workflows/{id}` would have fallen to the fixtures catch-all (returning `{}`) and silently broken rename/delete. The double-star covers both the collection and the `/{id}` sub-path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Launch seed resolved against the wrong agent set (loaded 0 agents)**
- **Found during:** Task 3 (the launch e2e assertion `2 agents` / Run-enabled failed; the ARIA snapshot showed "Advanced 0 agents" + "Add agents first").
- **Issue:** Task 1 (and the 21-PATTERNS §12 pattern) seeded `pipelineAgents` by resolving `initialAgentIds` through `LIBRARY_AGENTS`. Saved custom workflows reference `CUSTOM_AGENTS` ids, which are NOT in `LIBRARY_AGENTS` — so every id resolved to `undefined`, was filtered out, and the launch loaded an empty pipeline. The load-bearing change would have silently no-op'd in production.
- **Fix:** Import and resolve the seed against `ALL_LIBRARY_AGENTS` (`LIBRARY_AGENTS ∪ CUSTOM_AGENTS`) — the same superset the composer's `AgentLibrary` uses. The non-seed default filter is unchanged (still `LIBRARY_AGENTS`).
- **Files modified:** `frontend/src/components/workflow/IdeaInputPage.tsx`.
- **Verification:** spec TS-Z2-02 now loads 2 seeded agents + Run enabled; tsc clean; the 12-test IdeaInputPage/DashboardLayout/WorkflowCatalog vitest regression stays green.
- **Committed in:** `569aa93d`.

---

**Total deviations:** 1 auto-fixed (1 bug). No scope creep; no architectural change; no new npm package (T-21-SC held).

## Out-of-Scope (Deferred)

The 2 **pre-existing** TS2352 errors in `frontend/e2e/fixtures/mockApi.ts` (readonly-tuple cast on `CAPABILITIES`/`MODEL_CATALOG`) remain — confirmed identical on HEAD, in the fixtures dir (not in this plan's `files_modified`), already logged to `deferred-items.md` in 21-02. The plan acceptance is "tsc clean for the touched files" — satisfied (`IdeaInputPage.tsx`, `DashboardLayout.tsx`, and the new spec all emit 0 errors). NOT fixed (SCOPE BOUNDARY).

## Verification Evidence

- `npx tsc --noEmit` — clean for all touched files (only the 2 pre-existing `e2e/fixtures/mockApi.ts` errors remain).
- `npm run e2e -- ts-z2.saved-workflows.spec.ts` (`playwright test --project=mocked`) — **2/2 passed** (TS-Z2-01 compose→Save→POST; TS-Z2-02 appears→rename→launch pre-loaded).
- Regression: `vitest --run` IdeaInputPage.modelOverrides + DashboardLayout.waveMount + WorkflowCatalog — **12/12 passed**.
- Greps (all satisfied): `initialAgentIds` ×7 + `initialModelOverrides` ×3 + the guard `if (initialAgentIds?.length) return` in IdeaInputPage; `handleLaunchSaved` ×2 + `savedComposition` ×3 + `onLaunchSaved={handleLaunchSaved}` + `initialAgentIds={savedComposition` in DashboardLayout; `user-workflows` ×8 in the spec.
- **SC-001 grep:** `if (saved` = 0 in DashboardLayout — no run-path/engine fork; `onRun`/`handleRunPipeline` bodies unchanged.

## Known Stubs

None — the launch preload is fully wired end-to-end: a saved row's persisted `{agent_ids, model_overrides}` seeds the composer, which runs through the existing `handleRunPipeline → startPipeline` path (already sends `agent_ids` + merges `model_overrides`), re-validated server-side at launch. The e2e proves a non-empty seeded pipeline reaches an enabled Run.

## Next Phase Readiness

- Phase 21 is FE-complete: 21-01 backend CRUD + 21-02 FE save/catalog section + 21-03 launch wiring. The full SAVE-FROM-BOTH → persist → appears → rename → launch loop is proven under the mocked harness.
- Live re-confirm (real backend save + launch + server-side `agent_ids`/`model_overrides` re-validation) deferred to the consolidated Bedrock/Playwright pass (per the defer-live-verification memo).
- No blockers.

## Self-Check: PASSED

- Files: `ts-z2.saved-workflows.spec.ts` FOUND; `IdeaInputPage.tsx`/`DashboardLayout.tsx` modified+FOUND.
- Commits: `e49ccac7`, `e6b38a9b`, `569aa93d`, `1c42455c` — all present in `git log`.

---
*Phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo*
*Completed: 2026-06-14*

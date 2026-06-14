---
phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo
plan: 02
subsystem: frontend
tags: [react, nextjs, motion, lucide, vitest, catalog, crud, saved-workflows]

# Dependency graph
requires:
  - phase: 21-01 (backend spine)
    provides: the owner-scoped /api/user-workflows CRUD + UserWorkflowResponse shape ({id,name,description,base_pipeline_type,agent_ids,model_overrides,created_at,updated_at}) this FE consumes
  - phase: 20 (data-driven catalog)
    provides: the WorkflowCatalog two-gate list + CreationHub row markup this section copies
provides:
  - api.ts UserWorkflowSummary + getUserWorkflows/createUserWorkflow/renameUserWorkflow/deleteUserWorkflow (4 owner-scoped CRUD fetchers hitting /api/user-workflows)
  - NameWorkflowModal (DeleteModal clone + AgentsPopup inputs; z-[80]) reusable by Save AND Rename
  - WorkflowCatalog "Your workflows" section + per-row Rename/Duplicate/Delete kebab + "+ Create workflow" affordance + onLaunchSaved prop (declared, optional)
  - IdeaInputPage "Save workflow" button (composer Save entry; POSTs the composer triple)
  - WorkflowCatalog.test.tsx extended with the saved-section + kebab + delete-optimistic vitest
affects: [21-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Second list in the catalog: getUserWorkflows (no user_launchable filter) alongside the built-in getWorkflowDefinitions list (SC-001 no regression)"
    - "Saved rows render their OWN name (the never-raw-API-name rule is MANIFEST-only); built-in rows stay read-only (no kebab)"
    - "NameWorkflowModal is one modal reused by Save and Rename (initialName/initialDescription/title props)"
    - "Optimistic CRUD on the saved list (prepend on Duplicate, map on Rename, filter on Delete)"

key-files:
  created:
    - frontend/src/components/catalog/NameWorkflowModal.tsx
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/components/catalog/WorkflowCatalog.tsx
    - frontend/src/components/workflow/IdeaInputPage.tsx
    - frontend/src/components/catalog/WorkflowCatalog.test.tsx

key-decisions:
  - "onLaunchSaved made OPTIONAL (onLaunchSaved?) so the existing DashboardLayout caller keeps compiling — the load-bearing handleLaunchSaved->IdeaInputPage preload wiring is explicitly 21-03's scope (not this plan's files_modified)"
  - "WorkflowCatalog.test.tsx EXTENDED (not recreated) — a Phase-20 catalog test already existed at that path; extending preserves the two existing gate/label tests while adding the saved-section coverage"
  - "Delete-confirm uses an INLINE DeleteModal-shell copy inside WorkflowCatalog (not a NameWorkflowModal) — it is a destructive confirm, matching the WorkflowHistory analog verbatim"

patterns-established:
  - "SAVE-FROM-BOTH realized FE-side: composer 'Save workflow' button + catalog '+ Create workflow' (onSelectFeature('custom')) — two entry points, one createUserWorkflow payload"
  - "SC-001 held: the Save payload is the EXACT existing composer triple {effectiveType, agent_ids, model_overrides}; no new pipeline name, no `if (saved...)` fork"

requirements-completed: [REUSE-MANDATE, SAVE-FROM-BOTH, CRUD-OWNER-SCOPED, SC-001]

# Metrics
duration: ~23min
completed: 2026-06-14
---

# Phase 21 Plan 02: Saved Workflows Frontend (Save + Catalog Section) Summary

**The FE save + persistence surface for saved workflows: 4 owner-scoped /api/user-workflows CRUD fetchers + a reusable NameWorkflowModal (DeleteModal clone), a catalog "Your workflows" section with a per-row Rename/Duplicate/Delete kebab, a "+ Create workflow" affordance, and a composer "Save workflow" button — every node a copy of its named analog (REUSE-MANDATE), Save reachable from BOTH the composer and the catalog (SAVE-FROM-BOTH), the payload pure data (SC-001).**

## Performance

- **Duration:** ~23 min
- **Started:** 2026-06-14T12:06Z
- **Completed:** 2026-06-14T12:29Z
- **Tasks:** 3
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- `api.ts`: added `UserWorkflowSummary` + `getUserWorkflows`/`createUserWorkflow`/`renameUserWorkflow`/`deleteUserWorkflow` against `/api/user-workflows`, copied verbatim from the `getWorkflowDefinitions`/`adminCreateUser`/`adminUpdateTier`/`adminDeleteUser` idioms — GET/POST/PATCH via `request<T>`, the 204 DELETE via the manual `fetch` + `ApiError` idiom; every fetcher sends `authHeaders(token)` (T-21-06).
- `NameWorkflowModal.tsx`: a `DeleteModal` clone (backdrop + scale-in + header + two-button footer) with the `AgentsPopup` name `<input>` + description `<textarea>`, bumped to `z-[80]`, Save disabled on empty name, props `{initialName, initialDescription, title, onSave, onCancel}` so it serves BOTH Save and Rename. No new visual language (UI-SPEC §4).
- `WorkflowCatalog.tsx`: a second `getUserWorkflows` mount fetch + a "Your workflows" `<section>` (rows copied from the built-in list, `label = row.name`, click → `onLaunchSaved(row)`) with a per-row kebab copied from `WorkflowHistory.tsx:872-918` (Rename → NameWorkflowModal → `renameUserWorkflow` optimistic; Duplicate → `createUserWorkflow` "(copy)" prepend; Delete → DeleteModal-shell confirm → `deleteUserWorkflow` optimistic filter). Built-in manifest rows get NO kebab (read-only, T-21-07). A "+ Create workflow" header affordance calls `onSelectFeature("custom")`. `onLaunchSaved` prop declared (optional; wired in 21-03).
- `IdeaInputPage.tsx`: a "Save workflow" button beside Run (gray-900 pill family) → `NameWorkflowModal` → `createUserWorkflow({ base_pipeline_type: effectiveType, agent_ids: pipelineAgents.map(a=>a.id), model_overrides: modelOverridesRef.current })` (the exact triple `onRun` sends) + a "Saved" toast. Pure data — SC-001 held (no new pipeline name, no saved-fork).
- `WorkflowCatalog.test.tsx`: extended the existing Phase-20 catalog test — mocked `getUserWorkflows` + the CRUD fetchers, threaded `onLaunchSaved` through the two existing renders, and added 4 new specs (section + name render; `onLaunchSaved` on row-click; kebab present on saved rows / absent on built-ins; Delete → confirm → `deleteUserWorkflow` called + optimistic removal). 6/6 green.

## Task Commits

1. **Task 1: api.ts CRUD fetchers + UserWorkflowSummary + NameWorkflowModal** — `d4254093` (feat)
2. **Task 2: 'Your workflows' section + kebab + '+ Create workflow' + composer Save button** — `40ecc797` (feat)
3. **Task 3: vitest — saved section + kebab + delete-optimistic flow** — `84d4e769` (test)

## Files Created/Modified
- `frontend/src/lib/api.ts` — +`UserWorkflowSummary` + 4 owner-scoped CRUD fetchers (`/api/user-workflows`).
- `frontend/src/components/catalog/NameWorkflowModal.tsx` — NEW: DeleteModal-clone name+description modal (z-[80]); reused by Save + Rename.
- `frontend/src/components/catalog/WorkflowCatalog.tsx` — second fetch + "Your workflows" section + per-row kebab + "+ Create workflow" + `onLaunchSaved?` prop.
- `frontend/src/components/workflow/IdeaInputPage.tsx` — "Save workflow" button → NameWorkflowModal → `createUserWorkflow` (composer triple) + toast.
- `frontend/src/components/catalog/WorkflowCatalog.test.tsx` — extended with the saved-section + kebab + delete-optimistic vitest (6/6 green).

## Decisions Made
- **`onLaunchSaved` optional (`onLaunchSaved?`)** — the prop is declared on `WorkflowCatalogProps` per the plan, but the load-bearing wiring (`DashboardLayout.handleLaunchSaved` → `IdeaInputPage` agent/model preload) is explicitly 21-03's scope. Making it optional keeps the existing `DashboardLayout.tsx:1073` caller compiling without touching a file outside this plan's `files_modified`. The call site is `onLaunchSaved?.(row)`.
- **Extended the existing `WorkflowCatalog.test.tsx`** — a Phase-20 catalog test already lived at that path (the plan said "Create"). Extending it (vs. recreating) preserves the two existing two-gate/label-precedence tests and the established `vi.mock`/motion-proxy harness (REUSE-MANDATE), and adds the saved-section coverage in a new `describe` block.
- **Delete-confirm is an inline DeleteModal-shell copy** inside `WorkflowCatalog` (not a `NameWorkflowModal`) — a destructive confirm has no name/description inputs; it mirrors the `WorkflowHistory.tsx:923-969` analog verbatim (gray-900 "Delete" pill).
- **`model_overrides` omitted when empty** in both the composer Save and the catalog Duplicate payloads (mirrors the existing `onRun` "omit empty map" idiom) — keeps the POST body minimal and matches the BE optional field.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Required `onLaunchSaved` broke two out-of-scope callers**
- **Found during:** Task 2 (whole-project tsc).
- **Issue:** Declaring `onLaunchSaved` as a REQUIRED prop made `DashboardLayout.tsx:1073` (a caller in 21-03's scope, NOT this plan's `files_modified`) fail to type-check, plus the existing test renders.
- **Fix:** Made the prop OPTIONAL (`onLaunchSaved?`) with a guarded call site (`onLaunchSaved?.(row)`). The prop is still declared (the 21-03 wiring target); no out-of-scope file was edited.
- **Files modified:** `frontend/src/components/catalog/WorkflowCatalog.tsx`.
- **Verification:** tsc clean for all touched files; the section still renders and the new vitest exercises the prop.
- **Committed in:** `40ecc797` (Task 2 commit).

---

**Total deviations:** 1 auto-fixed (1 blocking). No scope creep; no architectural change.

## Out-of-Scope (Deferred)

Logged to `deferred-items.md`: 2 **pre-existing** TS2352 errors in `frontend/e2e/fixtures/mockApi.ts` (readonly-tuple → `unknown[]` cast on `CAPABILITIES`/`MODEL_CATALOG`). Confirmed identical on HEAD (`git show HEAD:` + "No local changes to save" when stash-testing), file untouched by this plan and outside `files_modified`. The plan acceptance is "tsc clean for the **touched** files" — satisfied (all 4 touched/created files emit 0 errors). NOT fixed (SCOPE BOUNDARY).

## Verification Evidence
- `npx tsc --noEmit` — clean for all touched files (`api.ts`, `NameWorkflowModal.tsx`, `WorkflowCatalog.tsx`, `IdeaInputPage.tsx`, `WorkflowCatalog.test.tsx`); only the 2 pre-existing `e2e/fixtures/mockApi.ts` errors remain.
- `npx vitest --run src/components/catalog/WorkflowCatalog.test.tsx` — 6/6 passed (2 existing Phase-20 + 4 new saved-section).
- Regression check: `IdeaInputPage.modelOverrides.test.tsx` + `DashboardLayout.waveMount.test.tsx` — 6/6 passed.
- Greps (all satisfied): `/api/user-workflows` ×4 + `UserWorkflowSummary` in api.ts; `Your workflows`/`getUserWorkflows`/`onLaunchSaved`/`MoreHorizontal`/`onSelectFeature("custom")` in WorkflowCatalog; `createUserWorkflow`/`pipelineAgents.map`/`base_pipeline_type: effectiveType`/`modelOverridesRef.current` in IdeaInputPage; no `if (saved` fork (SC-001).

## Known Stubs
None — every saved row is wired to the live `/api/user-workflows` CRUD; the "Your workflows" list is a real `getUserWorkflows` fetch (no hardcoded names). The one DECLARED-but-not-yet-wired surface is the `onLaunchSaved` prop (optional), whose launch-preload wiring is explicitly 21-03's deliverable (documented above, not a stub blocking this plan's goal — Save + management is fully functional).

## Next Phase Readiness
- 21-03 wires `onLaunchSaved` end-to-end: `DashboardLayout.handleLaunchSaved` (carry the saved triple into state) → `IdeaInputPage` `initialAgentIds`/`initialModelOverrides` preload props + the guarded re-derive effect → `useWorkflow.startPipeline` (unchanged) → plus the mocked Playwright spec. The api.ts fetchers + the `UserWorkflowSummary` shape + the catalog section/kebab are all in place for it to consume.
- No blockers.

## Self-Check: PASSED

- Files: `NameWorkflowModal.tsx` FOUND; `api.ts`/`WorkflowCatalog.tsx`/`IdeaInputPage.tsx`/`WorkflowCatalog.test.tsx` modified+FOUND.
- Commits: `d4254093`, `40ecc797`, `84d4e769` — all FOUND in `git log`.

---
*Phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo*
*Completed: 2026-06-14*

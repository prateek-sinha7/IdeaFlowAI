---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 07
subsystem: ui
tags: [react, nextjs, tailwind, fastapi, workflow-catalog, deliverable-renderer, mimetype-dispatch]

# Dependency graph
requires:
  - phase: 20-workflow-catalog-data-driven-browse-and-launch-gallery-reali
    provides: data-driven WorkflowCatalog (GET /api/workflows) + BE display_name coalesce fix (WR-01)
  - phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo
    provides: handleLaunchSaved wiring + WorkflowCatalog "Your workflows" section
  - phase: 18-prototype-and-deliverable-adherence
    provides: GenericDeliverablePreview (mimetype-dispatched renderer) + P18 sandboxed-iframe security contract
provides:
  - "Catalog-as-home: the data-driven WorkflowCatalog is the DEFAULT home landing; CreationHub.WORKFLOWS no longer drives the default view (UXFIX-03/D-20)"
  - "Authored display_name on 6 launchable manifests; custom stays unauthored (UXFIX-01/D-18); P20 BE coalesce fix intact"
  - "Generic-primary mimetype-dispatch TABLE in PreviewPanel: the generic renderer is the PRIMARY route, the 4 first-party types are registered routed entries (UXFIX-04/D-21)"
affects: [phase-22 verification, v1.0 milestone audit, future custom-workflow deliverable rendering]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "renderType-keyed dispatch table (FIRST_PARTY_RENDERERS) — generic-primary, first-party entries routed, no workflow-name branch (SC-001)"
    - "catalog-as-home re-route: mount the data-driven surface in the default view, no new visual"

key-files:
  created:
    - frontend/src/components/layout/DashboardLayout.catalogHome.test.tsx
  modified:
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/layout/AppHeader.tsx
    - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/preview/PreviewPanel.genericDeliverable.test.tsx
    - backend/agents/workflows/user_stories/workflow.yaml
    - backend/agents/workflows/prototype/workflow.yaml
    - backend/agents/workflows/ppt/workflow.yaml
    - backend/agents/workflows/app_builder/workflow.yaml
    - backend/agents/workflows/mulesoft_to_springboot/workflow.yaml
    - backend/agents/workflows/dotnet_to_azure/workflow.yaml
    - backend/tests/agents/test_manifest.py
    - backend/tests/unit/test_workflows_api.py

key-decisions:
  - "Catalog-as-home implemented by mounting WorkflowCatalog in the existing `home` view block (re-route, zero new visual per UI-SPEC), not by flipping the default mainView initializer — keeps handleGoHome/header semantics stable"
  - "Removed the now-redundant separate Catalog nav tab + its view block: home IS the catalog, so a second identical tab would re-create the dual-surface smell UXFIX-03 was chartered to remove"
  - "Authored display_name on the 6 first-party/conversion launchable manifests; left `custom` (user-composed) unauthored so the composer/getWorkflowLabel FE fallback owns its label — exercises BOTH halves of the P20 coalesce contract"
  - "PreviewPanel dispatch keyed on the structural renderType (FIRST_PARTY_RENDERERS map) with the generic renderer as the default/primary route — never a workflow-name kernel branch (SC-001)"

patterns-established:
  - "Generic-primary deliverable dispatch: a Record<renderType, ()=>ReactNode|null> of first-party entries + a generic default route; a brand-new workflow renders via the generic path with zero new branch"

requirements-completed: [UXFIX-01, UXFIX-03, UXFIX-04]

# Metrics
duration: 11min
completed: 2026-06-14
---

# Phase 22 Plan 07: Catalog-as-Home + Authored display_name + Generic-Primary Deliverable Dispatch Summary

**The data-driven WorkflowCatalog is now the default home landing (CreationHub.WORKFLOWS no longer drives it), launchable manifests render authored friendly display_names, and PreviewPanel routes deliverables through a generic-primary mimetype-dispatch table where the 4 first-party types are routed entries — no visual regression, P18 sandbox intact.**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-06-14T20:36:00Z
- **Completed:** 2026-06-14T20:47:00Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 13 (+1 created)

## Accomplishments

- **UXFIX-03 / D-20 (catalog-as-home):** `DashboardLayout` mounts the data-driven `WorkflowCatalog` (`GET /api/workflows`) as the DEFAULT home landing; the hardcoded `CreationHub.WORKFLOWS` array no longer drives the default view (SC-001 holds on the default surface). Removed the redundant separate Catalog nav tab so there is one canonical surface.
- **UXFIX-01 / D-18 (display_name):** authored a friendly `display_name` on 6 launchable manifests (`user_stories`, `prototype`, `ppt`, `app_builder`, `mulesoft_to_springboot`, `dotnet_to_azure`); `custom` stays unauthored so the FE fallback label is used. The P20 BE coalesce fix (`workflows.py` carries only the manifest's EXPLICIT display_name) is intact.
- **UXFIX-04 / D-21 (generic-primary):** restructured `PreviewPanel` from "4 first-party branches + generic-fallback-last" into a `renderType`-keyed dispatch TABLE (`FIRST_PARTY_RENDERERS`) where the generic mimetype-dispatched renderer is the PRIMARY route and the first-party types are registered routed entries. No visual regression; the P18 sandboxed-iframe contract (`sandbox="allow-scripts"`, NO `allow-same-origin`) and the CR-01 fix (`custom` not routed to MarkdownPreview) survive.

## Task Commits

Each task was committed atomically (TDD: test → feat/refactor):

1. **Task 1 RED: failing tests for catalog-home + display_name** - `93fe98d3` (test)
2. **Task 1 GREEN: catalog-as-home + authored display_name** - `1fb41883` (feat)
3. **Task 2 RED/contract: pin generic-primary dispatch-table** - `5121ceb2` (test)
4. **Task 2 GREEN: generic-primary mimetype-dispatch table** - `86db9e3b` (refactor)

## Files Created/Modified

- `frontend/src/components/layout/DashboardLayout.tsx` - default `home` view mounts WorkflowCatalog; removed the redundant `catalog` view block + unused CreationHub import
- `frontend/src/components/layout/AppHeader.tsx` - removed the now-duplicate Catalog nav button + unused LayoutGrid import
- `frontend/src/components/layout/DashboardLayout.catalogHome.test.tsx` - NEW: default landing mounts WorkflowCatalog, NOT CreationHub
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` - stub WorkflowCatalog (the new default landing) so the wave-tree regression stays isolated
- `frontend/src/components/preview/PreviewPanel.tsx` - `FIRST_PARTY_RENDERERS` dispatch table + `renderDeliverable()` (generic-primary)
- `frontend/src/components/preview/PreviewPanel.genericDeliverable.test.tsx` - +3 tests pinning generic-primary + first-party routed-entry contract
- `backend/agents/workflows/{user_stories,prototype,ppt,app_builder,mulesoft_to_springboot,dotnet_to_azure}/workflow.yaml` - authored `display_name`
- `backend/tests/agents/test_manifest.py` - real-manifest authored-vs-unauthored display_name assertions
- `backend/tests/unit/test_workflows_api.py` - updated P20 launchable-flags assertion to the authored/unauthored coalesce contract

## Decisions Made

See `key-decisions` frontmatter. Key: catalog-as-home via the `home` view re-route (not the mainView initializer); removed the redundant Catalog tab; `custom` intentionally unauthored; dispatch keyed on structural renderType.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] waveMount regression test broke after catalog-as-home re-route**
- **Found during:** Task 1 (catalog-as-home)
- **Issue:** `DashboardLayout.waveMount.test.tsx` mocked `CreationHub` (the old default landing) but not `WorkflowCatalog`. With WorkflowCatalog now the default `home` mount, its mount fetch fired `getToken()` → `localStorage.getItem` in a jsdom env that lacks it, failing all 4 wave-tree tests.
- **Fix:** stub `WorkflowCatalog` in the test alongside the other heavy children (mirrors the existing CreationHub stub).
- **Files modified:** frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
- **Verification:** waveMount 4/4 green (isolated + combined).
- **Committed in:** `1fb41883` (Task 1 commit)

**2. [Rule 1 - Bug] P20 test_workflows_api stale "display_name is None for every row" assertion**
- **Found during:** Task 1 (authoring display_name)
- **Issue:** `TestList::test_list_carries_launchable_flags` asserted `display_name is None` for ALL rows "until a manifest declares one." Authoring display_name on the launchable manifests correctly broke this stale assertion.
- **Fix:** updated the assertion to pin BOTH halves of the coalesce contract — authored rows carry their verbatim label, `custom` stays None — preserving the WR-01/D-18 intent (BE never coalesces to the title-cased id).
- **Files modified:** backend/tests/unit/test_workflows_api.py
- **Verification:** test_workflows_api 24/24 green.
- **Committed in:** `1fb41883` (Task 1 commit)

**3. [Rule 2 - Missing Critical / dual-surface removal] Removed the redundant Catalog nav tab**
- **Found during:** Task 1 (catalog-as-home)
- **Issue:** After mounting WorkflowCatalog as home, the existing separate "Catalog" nav tab rendered the identical surface — re-creating the dual-surface confusion UXFIX-03 was chartered to remove.
- **Fix:** removed the Catalog nav button (AppHeader) + the `catalog` view block (DashboardLayout); home is now the single canonical catalog surface. Left the `currentPage`/`onNavigate` "catalog" type union member untouched (harmless, no caller).
- **Files modified:** frontend/src/components/layout/AppHeader.tsx, frontend/src/components/layout/DashboardLayout.tsx
- **Verification:** full FE vitest 135/135 green; tsc clean (touched files).
- **Committed in:** `1fb41883` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 bug, 1 missing-critical/dual-surface)
**Impact on plan:** All three were necessary to land the plan's own goal (catalog-as-home without a re-introduced dual surface) and to keep the suite green. No scope creep beyond the plan's stated surfaces.

## Issues Encountered

- The plan's verify command `npm test -- --run <file>` double-passes `--run` (the npm script already includes it) and errors; used `npx vitest run <file>` instead. No behavior change.

## Verification Evidence

- **FE:** full vitest suite 135/135 green (incl. PreviewPanel.genericDeliverable 11/11, degraded, MarkdownPreview.security, DashboardLayout.catalogHome 2/2, waveMount 4/4, WorkflowCatalog 7/7). `npx tsc --noEmit` clean for all touched files — only the 2 pre-existing `e2e/fixtures/mockApi.ts` TS2352 casts remain (out of scope).
- **BE:** test_manifest.py + test_workflows_api.py 50/50; characterization goldens (prototype, app_builder, manifest-parity, phase3-cutover) 42/42 byte/event-identical (NO SNAPSHOT_UPDATE — display_name is inert presentation metadata, INV-3 parity preserved); banned-patterns + SC-001 gate 17/17; `lint-imports` 4 kept / 0 broken; zero migrations.
- **SC-001:** the PreviewPanel deliverable dispatch is `renderType`-keyed (FIRST_PARTY_RENDERERS), no workflow-name kernel branch; the default home view has no hardcoded workflow-name list (catalog is data-driven from GET /api/workflows).

## Known Stubs

None — no new stubs introduced. All surfaces are wired to live data (catalog → GET /api/workflows; deliverable dispatch → declared mimetype).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The three v1.0-audit UX data-faithfulness warnings (UXFIX-01/03/04) are closed.
- Manual visual no-regression of the 4 first-party deliverable types remains a deferred eyeball check (22-VALIDATION Manual-Only) — the unit regression tests are the offline gate.

## Self-Check: PASSED

- Created/modified files verified on disk (DashboardLayout.catalogHome.test.tsx, PreviewPanel.tsx, manifests, SUMMARY).
- All 4 task commits verified in git log (93fe98d3, 1fb41883, 5121ceb2, 86db9e3b).

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime*
*Completed: 2026-06-14*

---
phase: 36-home-history-my-workflows-b2
plan: 03
subsystem: ui
tags: [react, vitest, testing-library, tailwind-v4, design-tokens, a11y, motion, my-workflows]

# Dependency graph
requires:
  - phase: 36-01
    provides: "HomeLaunchGrid rename + Phase-32 token reskin idiom (bg-surface-*/text-ink-*/border-line-*/text-brand/status-* fills) this page mirrors"
  - phase: 32
    provides: "Canonical @theme token layer (globals.css) + components/ui primitives"
  - phase: 35
    provides: "AppHeader nav pill already reads 'My Workflows' (D-11); the menu a11y idiom (aria-haspopup/expanded, role=menu/menuitem, Escape-close+refocus) mirrored here"
provides:
  - "Relabeled 'My Workflows' page (in-page <h1> no longer 'Workflow Catalogue' — D-11 reserves Catalogue for the future marketplace)"
  - "SavedWorkflowsPage fully reskinned onto Phase-32 @theme tokens (retired-palette grep 0, stray-stock grep 0)"
  - "Module-level KebabMenu with correct a11y (stable identity, aria-haspopup/expanded, role=menu/menuitem, Escape close+refocus)"
  - "SavedWorkflowsPage.test.tsx (Wave-0 gap closure) locking the label + real-kebab-CRUD + a11y contract"
affects: [36-04, 36-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level menu component (props: row/isOpen/onToggle/onClose/onRename/onDuplicate/onDelete) for a STABLE element identity — avoids the render-body remount that breaks in-place aria state + focus refs"
    - "Co-located vitest api-mock + motion-proxy idiom (mirrors HomeLaunchGrid.test); re-query nodes after a state change because the motion mock remounts the subtree"

key-files:
  created:
    - frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx
  modified:
    - frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx

key-decisions:
  - "In-page heading 'Workflow Catalogue' -> 'My Workflows'; delete copy 'removed from your catalogue' -> 'removed from your saved workflows' (D-11)"
  - "Dropped the dead style={{fontFamily: var(--font-fraunces)}} in favour of the font-serif class (Heebo) — fraunces is retired from the token layer"
  - "ICON_STYLES avatar tints rebuilt from @theme tokens (no raw hex) instead of the old #1B2A4A/#E8EDF5 pairs"
  - "Hoisted KebabMenu to module scope (Rule 1 a11y correctness) so aria-expanded updates in place and the Escape-focus ref survives"

patterns-established:
  - "Reskin-look/keep-behavior (D-15): all CRUD wiring + optimistic mutation + cancellable mount-fetch preserved byte-behavior-identical while palette/labels change"
  - "Real-kebab-not-static-text is now test-locked: each menuitem asserts its /api/user-workflows CRUD call fires + the optimistic list mutation"

requirements-completed: [SHELL-02]

# Metrics
duration: 12min
completed: 2026-07-09
---

# Phase 36 Plan 03: My Workflows Relabel + Token Reskin Summary

**Relabeled the in-page 'Workflow Catalogue' heading to 'My Workflows' (D-11), reskinned SavedWorkflowsPage onto Phase-32 @theme tokens, and added the Wave-0-gap SavedWorkflowsPage.test.tsx locking the label + the already-real Rename/Duplicate/Delete kebab CRUD + a11y.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-09T04:26:00Z
- **Completed:** 2026-07-09T04:35:00Z
- **Tasks:** 2 (plus 1 Rule-1 a11y deviation)
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- In-page `<h1>` now renders "My Workflows"; "Catalogue" is gone as a user-facing label (D-11). Delete-confirm copy updated to "saved workflows".
- SavedWorkflowsPage migrated onto the canonical token layer: `bg-surface-paper/card/white/warm`, `text-ink-*`, `border-line-*`, `text-brand`/`bg-brand`/`hover:bg-brand-pressed`, `status-failed` error + delete affordances, `radius-menu`/`elevation-menu`/`elevation-modal`/`scrim` vars. Retired-palette grep and stray-stock grep both 0.
- Kebab CRUD preserved byte-behavior-identical (D-15): Rename→`renameUserWorkflow`, Duplicate→`createUserWorkflow`, Delete→`deleteUserWorkflow`, each with optimistic `setUserWorkflows`; cancellable mount-fetch + delete-confirm modal intact.
- a11y hardened: kebab trigger `aria-haspopup=menu`/`aria-expanded` + `aria-label`, `role=menu` with three `role=menuitem` rows, Escape closes + refocuses the trigger; delete modal `role=dialog`/`aria-modal`/`aria-labelledby` + Escape-close.
- New `SavedWorkflowsPage.test.tsx` (5 tests) closes the 36-VALIDATION Wave-0 gap: label present / "Workflow Catalogue" absent; each kebab action fires its real CRUD call + the optimistic list mutation; kebab aria + Escape a11y.

## Task Commits

Each task was committed atomically:

1. **Task 1: Relabel 'My Workflows' + reskin onto tokens** - `3eaea5f5` (feat)
2. **Rule-1 a11y deviation: hoist KebabMenu to module scope** - `e7b29891` (fix)
3. **Task 2: SavedWorkflowsPage.test.tsx label + kebab CRUD parity** - `91039712` (test)

_Task 1 landed the relabel + reskin on SavedWorkflowsPage.tsx; while writing Task 2's test the kebab's render-body definition was found to break in-place aria/focus, fixed in e7b29891 (source-only), then locked by the Task-2 test._

## Files Created/Modified
- `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx` - Relabeled heading + delete copy; reskinned every retired/stock palette literal onto @theme tokens; hoisted KebabMenu to module scope with full a11y; all CRUD/fetch/modal wiring preserved.
- `frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx` - New co-located vitest suite (5 tests) asserting the D-11 label, the D-15 real-kebab-CRUD contract (rename/create/delete + optimistic mutation), and kebab aria + Escape a11y.

## Decisions Made
- Rebuilt the neutral avatar tints (`ICON_STYLES`) from tokens rather than dropping variety — kept six rotating tints but sourced from brand/surface/status vars so the raw-hex gate stays 0.
- Kept the destructive confirm button as a neutral-dark `bg-ink-900`/`hover:bg-ink-800` (tokenized) rather than switching it to the red status ramp, preserving the original neutral-destructive visual intent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/a11y correctness] Hoisted KebabMenu out of the render body**
- **Found during:** Task 2 (writing the aria-expanded / Escape a11y assertions)
- **Issue:** `KebabMenu` was defined inside `SavedWorkflowsPage`'s render body, so every `openMenuId` change re-created its component type and REMOUNTED the trigger button. That detached the node (so `aria-expanded` never updated in place) and reset the Escape-focus `useRef`, breaking the close-and-refocus a11y contract required by the phase's a11y invariant.
- **Fix:** Moved `KebabMenu` to module scope, taking explicit props (`row`, `isOpen`, `onToggle`, `onClose`, `onRename`, `onDuplicate`, `onDelete`). Stable identity → the button re-renders in place; the trigger ref survives so Escape refocuses it. All CRUD wiring and optimistic mutation unchanged.
- **Files modified:** frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx
- **Verification:** SavedWorkflowsPage.test.tsx a11y test green (aria-haspopup/expanded, 3 menuitems, Escape closes); retired-palette grep 0; kebab-CRUD grep 5; tsc 0.
- **Committed in:** `e7b29891` (separate source-only commit)

---

**Total deviations:** 1 auto-fixed (1 Rule-1 a11y correctness)
**Impact on plan:** The fix was required to satisfy the plan's a11y invariant (T-36-03-A11Y mitigation) and to make the Task-2 aria/Escape assertions truthful. No scope creep — CRUD behavior byte-behavior-identical.

## Issues Encountered
- Two initial test failures were test-harness artifacts, not product bugs:
  - `findByRole('heading', {name})` returned a stale node after the async mount-fetch re-render → switched to the proven `findByText('My Workflows')` + `tagName === 'H1'` idiom (as HomeLaunchGrid.test uses `findByText`).
  - The mocked `motion/react` proxy returns a fresh component type on every property access, so each state change fully remounts the card subtree, detaching captured nodes → re-query the trigger after the click (same pattern HomeLaunchGrid.test uses when looping `getAllByRole('button')`). Real `motion` keeps the node stable.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- SHELL-02 SC-3 (My Workflows relabel) complete on the FE. Remaining Phase-36 plans: 36-04 (RunDetailPage + `getRunSummary` FE half of SHELL-03) and 36-05 (History grouping/sort/delete).
- Mocked Playwright e2e for this page remains LIVE-DEFERRED (offline Next webServer timeout), consistent with the phase contract; not run.

## Verification Output (literal)

```
=== 1. grep -c "Workflow Catalogue" src/components/savedworkflows/SavedWorkflowsPage.tsx (expect 0) ===
0
=== 2. grep -rEn '#1B2A4A|#2563eb|#f5f5f0|\bInter\b|\bFraunces\b|\bJetBrains\b' SavedWorkflowsPage.tsx (expect none) ===
(no matches — grep exit 1)
=== 3. grep -c 'renameUserWorkflow\|createUserWorkflow\|deleteUserWorkflow' SavedWorkflowsPage.tsx (expect >0) ===
5
=== 4. npx vitest run src/components/savedworkflows/SavedWorkflowsPage.test.tsx ===
 Test Files  1 passed (1)
      Tests  5 passed (5)
=== 5. npx tsc --noEmit 2>&1 | grep -c error (baseline 0) ===
0
```

---
*Phase: 36-home-history-my-workflows-b2*
*Completed: 2026-07-09*

## Self-Check: PASSED

- FOUND: frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx
- FOUND: frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx
- FOUND: .planning/phases/36-home-history-my-workflows-b2/36-03-SUMMARY.md
- FOUND commit: 3eaea5f5 (Task 1 feat)
- FOUND commit: e7b29891 (Rule-1 a11y fix)
- FOUND commit: 91039712 (Task 2 test)

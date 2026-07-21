---
phase: quick-260713-rcf
plan: 260713-rcf
subsystem: ui
tags: [react, nextjs, revert, prototype, ppt, launch-wizard, dead-code-removal]

requires:
  - phase: 41 (wave 41-02 d7a947e1 + 41-03 88f4db97)
    provides: the ConfigureScreen single-screen launch surface (now reverted)
provides:
  - "prototype/ppt launch routed back through the intact LaunchWizard (/workflow/create)"
  - "removal of the orphaned Configure single-screen cluster + its dead deps"
affects: [phase-41, prototype, ppt, launch-wizard]

tech-stack:
  added: []
  patterns:
    - "git checkout <sha>^ -- <files> to restore the exact pre-wave state of wired files"

key-files:
  created: []
  modified:
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/catalog/HomeLaunchGrid.tsx
    - frontend/e2e/tests/ts-b.selection.spec.ts
    - frontend/src/components/workflow/LaunchWizard.test.tsx
  deleted:
    - frontend/src/components/workflow/ConfigureScreen.tsx
    - frontend/src/components/workflow/ConfigureScreen.test.tsx
    - frontend/src/components/workflow/configure/TemplatesAccordion.tsx
    - frontend/src/components/workflow/configure/DesignSystemAccordion.tsx
    - frontend/src/components/workflow/configure/ReviewGatesAccordion.tsx
    - frontend/src/components/workflow/configure/WorkflowSettingsAccordion.tsx
    - frontend/src/app/workflow/configure/page.tsx
    - frontend/src/lib/draft.ts
    - frontend/src/lib/draft.test.ts

key-decisions:
  - "Template/design-system selection is the LaunchWizard's job and is functionally required; the bare ConfigureScreen prototype launch was rejected by the backend (missing_template_context), so prototype/ppt revert to the wizard."
  - "The Configure surface was reachable only from Home prototype/ppt cards + a dead /workflow/configure route → removed entirely (INV-3, no orphaned dual impl)."
  - "draft.ts/draft.test.ts (Configure-only client draft) deleted; launchDraft.ts (the wizard's) kept."

requirements-completed: []

duration: ~8min
completed: 2026-07-13
---

# Quick 260713-rcf: Remove Configure Single-Screen — prototype/ppt Back to the Wizard Summary

**Reverses Phase 41 waves 41-02 (d7a947e1) + 41-03 (88f4db97): the single-screen ConfigureScreen launched a bare prototype with no design-system/template context (backend rejects with missing_template_context), so prototype/ppt route back to the intact LaunchWizard and the now-orphaned Configure cluster is deleted — a mechanical FE-only removal.**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-07-13
- **Files:** 4 modified (3 restored + 1 comment) · 9 deleted
- **Commit:** `131c4e30` (single atomic, no trailer, not pushed)

## Accomplishments
- Restored the 3 wired files to pre-41-03 (`88f4db97^` = d7a947e1) via `git checkout 88f4db97^ -- …`:
  - `DashboardLayout.tsx` — drops the `ConfigureScreen` import, `handleConfigureFeature`/`handleConfigureLaunch`, the `mainView==="configure"` render block, and the `"configure"` member of the `MainView` union.
  - `HomeLaunchGrid.tsx` — drops the `onConfigure` prop + wiring so prototype/ppt cards route to the wizard again.
  - `ts-b.selection.spec.ts` — restored to its wizard-asserting assertions.
- Deleted the Configure cluster + now-dead deps (9 files): `ConfigureScreen.tsx` + `.test.tsx`, the four `configure/` accordions (Templates / DesignSystem / ReviewGates / WorkflowSettings), the `/workflow/configure` route (`page.tsx`), and `lib/draft.ts` + `draft.test.ts` (the Configure-only client draft). Both empty dirs (`components/workflow/configure/`, `app/workflow/configure/`) removed by the `git rm`.
- Reworded a stale comment in `LaunchWizard.test.tsx` (~line 12) that named the deleted `ConfigureScreen.test` — comment only, no test-logic change.
- `LaunchWizard.tsx` and `launchDraft.ts` left untouched (confirmed absent from the staged diff).

## Deviations from Plan
None — executed exactly as written.

## Verification (offline)
- `npx tsc --noEmit` → **exit 0, clean** — no dangling `ConfigureScreen` / `@/lib/draft` imports.
- `npx vitest run` → **91 passed / 4 failed files; 648 passed / 8 failed tests.** All 8 failures are PRE-EXISTING and out of scope:
  - `PreviewPanel.switcher.test.tsx` (3), `PreviewPanel.degraded.test.tsx` (1), `FilesTab.runInput.test.tsx` (2) — unrelated components, untouched by this change.
  - `HomeLaunchGrid.inspect.test.tsx` (2) — proven pre-existing: the same 2 tests fail against the pristine HEAD (88f4db97) HomeLaunchGrid.tsx; the WR-02 inspect affordance was last touched by commits 54058103/89518471 (both pre-41-03) and the 41-03 diff only added the `onConfigure` prop, never the inspect affordance.
  - `ConfigureScreen.test` + `draft.test` are gone as intended.
- Dead-reference grep (`ConfigureScreen|ComposedLaunchCommand|onConfigure|@/lib/draft|ConfigureDraft`) over `frontend/src` and `frontend/e2e/tests`: **empty.** Only matches remain in `frontend/e2e/fidelity/` (gallery-doc prose describing the Phase 41 mock analysis — not code imports, out of scope).
- `grep 'mainView === "configure"|"configure"'` in `DashboardLayout.tsx`: **empty.**
- `git diff --cached --stat` did **not** list `LaunchWizard.tsx`.

## Self-Check: PASSED

---
*Phase: quick-260713-rcf*
*Completed: 2026-07-13*

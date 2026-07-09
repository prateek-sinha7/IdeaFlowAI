# Phase 36 — Deferred / Out-of-Scope Items

Append-only log of pre-existing issues discovered during execution that are OUT OF SCOPE
for the current task (per the executor SCOPE BOUNDARY rule — do not fix, do not delete).

## 36-01 Task 1 (rename) — pre-existing dead tests in HomeLaunchGrid.test.tsx

- **File:** `frontend/src/components/catalog/HomeLaunchGrid.test.tsx` (was `WorkflowCatalog.test.tsx`)
- **What:** The `describe("HomeLaunchGrid — 'Your workflows' section + kebab (Phase 21)")` block
  (5 tests: saved-row name, launch-via-onLaunchSaved, kebab Rename/Duplicate/Delete,
  delete-confirm, delete-error-keeps-row) fails.
- **Why pre-existing (proven this session):** the component's JSDoc states the "Your Workflows"
  saved-section was **moved to `SavedWorkflowsPage`**. The component imports only
  `getWorkflowDefinitions, getToken` (never `getUserWorkflows`/`deleteUserWorkflow`) and never
  renders a "Your workflows" heading — so these 5 tests assert behavior that no longer lives in
  this component. They are red at base `92af09ec` and documented in STATE.md as the
  `WorkflowCatalog 5` pre-existing failures (part of the 10 pre-existing repo-wide).
- **Not a regression:** the pure symbol rename (`WorkflowCatalog`→`HomeLaunchGrid`) cannot change
  test-logic outcomes. The 2 in-scope tests (`two-gate filter + friendly label` describe) PASS,
  and both `DashboardLayout` mock-path suites PASS (the vi.mock trap gate).
- **Disposition:** NOT fixed, NOT deleted (CLAUDE.md: never delete a failing test to go green).
  These dead tests should be retargeted/removed when `SavedWorkflowsPage` gets its own test file
  (RESEARCH.md Wave-0 gap: `SavedWorkflowsPage.test.tsx`), a later 36-plan.

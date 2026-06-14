# Phase 20 — Deferred Items

## Pre-existing, out-of-scope (NOT introduced by this phase)

- **`frontend/e2e/fixtures/mockApi.ts` (lines 95-96) — TS2352 readonly-tuple cast errors.**
  Discovered while running `npx tsc --noEmit` for Plan 20-02 verification. These are
  `Conversion of type 'readonly [...]' to type 'unknown[]'` errors on two
  `as unknown[]` casts of `readonly` fixture tuples. The file is under
  `frontend/e2e/fixtures/`, which Plan 20-02 is explicitly forbidden to edit, and the
  errors are unrelated to any catalog file. Confirmed pre-existing (the two casts have
  nothing to do with `getWorkflowDefinitions`/`WorkflowCatalog`). All files created or
  modified by Plan 20-02 are tsc-clean. Left untouched per the SCOPE BOUNDARY rule.

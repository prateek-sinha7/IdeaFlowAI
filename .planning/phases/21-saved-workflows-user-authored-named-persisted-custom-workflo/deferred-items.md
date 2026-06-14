# Deferred Items — Phase 21

Out-of-scope discoveries logged during execution (SCOPE BOUNDARY). NOT fixed by this phase.

## Pre-existing tsc errors in `frontend/e2e/fixtures/mockApi.ts`

- **Found during:** 21-02 Task 1 (whole-project `npx tsc --noEmit`).
- **Errors:** `mockApi.ts(95,21)` + `mockApi.ts(96,22)` — TS2352 readonly-tuple → `unknown[]` cast (`CAPABILITIES as unknown[]`, `MODEL_CATALOG as unknown[]`).
- **Status:** PRE-EXISTING on HEAD (identical code, `git show HEAD:` confirmed), file untouched by 21-02. Out of this plan's `files_modified`. The plan acceptance is "tsc clean for the **touched** files" — satisfied (api.ts + NameWorkflowModal + WorkflowCatalog + IdeaInputPage emit 0 errors).
- **Owner:** an e2e-fixtures cleanup task / the team that owns `e2e/fixtures` (not a saved-workflows concern).

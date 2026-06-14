# Phase 22 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed; see SCOPE BOUNDARY in execute-plan).

## 22-02

- **Pre-existing FE TS2352 errors in `frontend/e2e/fixtures/mockApi.ts:95-96`** — two
  `as unknown[]` const-assertion conversion errors on the mocked `CAPABILITIES` /
  `MODEL_CATALOG` fixtures. These predate plan 22-02 (documented in STATE.md across
  21-02/21-03/19-x sessions) and are NOT introduced by the `CapabilityEntry` type
  extension (the fixtures cast to `unknown[]`, bypassing the interface). `npx tsc --noEmit`
  reports exactly these 2 errors and none in `src/`. Out of scope for SURF-02.
## Deferred (out-of-scope pre-existing failures) — Phase 22-04
- tests/unit/test_user_workflows.py::test_migration_adds_then_drops_columns FAILS pre-existing (proven via git stash on clean HEAD). The P21 0021-down assertion no longer holds after migration 0022 (P22-03) layered on top; the columns persist across the 0021 downgrade. Unrelated to 22-04 (no migration touched). SCOPE BOUNDARY — not fixed here.

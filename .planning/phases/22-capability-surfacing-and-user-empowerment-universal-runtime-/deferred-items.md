# Phase 22 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed; see SCOPE BOUNDARY in execute-plan).

## 22-02

- **Pre-existing FE TS2352 errors in `frontend/e2e/fixtures/mockApi.ts:95-96`** — two
  `as unknown[]` const-assertion conversion errors on the mocked `CAPABILITIES` /
  `MODEL_CATALOG` fixtures. These predate plan 22-02 (documented in STATE.md across
  21-02/21-03/19-x sessions) and are NOT introduced by the `CapabilityEntry` type
  extension (the fixtures cast to `unknown[]`, bypassing the interface). `npx tsc --noEmit`
  reports exactly these 2 errors and none in `src/`. Out of scope for SURF-02.

# Phase 22 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed; see SCOPE BOUNDARY in execute-plan).

## 22-02

- **Pre-existing FE TS2352 errors in `frontend/e2e/fixtures/mockApi.ts:95-96`** — two
  `as unknown[]` const-assertion conversion errors on the mocked `CAPABILITIES` /
  `MODEL_CATALOG` fixtures. These predate plan 22-02 (documented in STATE.md across
  21-02/21-03/19-x sessions) and are NOT introduced by the `CapabilityEntry` type
  extension (the fixtures cast to `unknown[]`, bypassing the interface). `npx tsc --noEmit`
  reports exactly these 2 errors and none in `src/`. Out of scope for SURF-02.
## Deferred — Phase 22 post-review fix pass (22-REVIEW-FIX)

- **WR-02: `resume_run` drops launch-time `selections` (tracked follow-up).** A
  backend-restart-resumed run re-drives the BARE file-compiled plan — the user-composed
  levers (selected validators/gates/per-step model/retry) that were active pre-crash are
  not persisted on the `workflow_runs` row, so they silently vanish on resume. NOT a
  security issue (resume can only ever apply LESS privilege than the engineer authored).
  Fix deferred out of this review-fix pass per scope (no new migration here). Resolution
  requires: an additive nullable column (or run JSON) persisting the launch `selections`,
  then re-threading them through `resume_run → _execute_impl → _apply_selections`. A code
  comment marks the limitation at the `resume_run` `_execute_impl` site (engine.py).

## Deferred (out-of-scope pre-existing failures) — Phase 22-04
- ~~tests/unit/test_user_workflows.py::test_migration_adds_then_drops_columns FAILS pre-existing~~ **RESOLVED at the regression gate (commit 607ddf54).** Re-diagnosis: this was NOT pre-existing — it was a Phase-22 regression. The test used `downgrade("-1")`, which before P22 went 0021→0020 (dropping P21's columns) but after P22-03's additive `0022` only undid `0022`, leaving P21's columns. The git-stash "proof" was flawed (stashing 22-04 does not remove the already-committed `0022`). Fixed test-only: downgrade to the explicit pre-0021 revision (`0020`) so it asserts 0021's own reversibility and is robust to later additive migrations. No production/migration code changed; INV-3 goldens unaffected.

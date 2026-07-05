---
phase: quick-260705-ed8
status: passed
verified_by: orchestrator (independent gate re-run)
date: 2026-07-05
score: 6/6 hard gates verified
branch: new-workflow-engine
---

# Quick 260705-ed8 Verification — model_pricing INV-12 single-source restore

**Goal:** Fix the proven t2x regression (hardcoded model-family literals in
`model_pricing.py` violating INV-12 and breaking
`test_model_catalog::test_single_source_grep`) the PROPER way — co-locate a frozen
`Pricing` dataclass + `pricing` field in `model_catalog.py` (the single source) and
make `model_pricing.py` DERIVE prices from the catalog with ZERO model-id literals,
WITHOUT loosening the test.

All gates were re-run independently from a clean read of the code (python3.11, no venv,
from `backend/`). SUMMARY claims were NOT trusted.

## Gate results

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | Regression fixed the RIGHT way | ✓ PASS | `test_model_catalog.py` → 9 passed; `test_single_source_grep` PASSED. Assertion UNCHANGED at line 181: `assert hits == {"model_catalog.py"}`. `git diff eb3ccced HEAD -- tests/agents/test_model_catalog.py` = EMPTY (test not loosened). `grep -nE 'claude-(haiku|sonnet|opus)-4' agents/capabilities/model_pricing.py` → zero lines (exit 1). |
| 2 | No dual impl / INV-12 restored | ✓ PASS | `model_pricing.py`: `MODEL_PRICING`, local `Price`, `_FALLBACK`, `_canonical` all GONE; prices resolved via three-tier `_resolve_pricing` (exact → normalized fallback → cheap default). Imports `ModelCatalog, Pricing` from `model_catalog`. `model_catalog.py`: frozen `Pricing` dataclass (input/output/cache_read/cache_write_5m/cache_write_1h) + `pricing: Pricing` field on `ModelEntry`; all 5 entries populated with verified rates. (Remaining `_FALLBACK`/`_canonical` grep hits are in unrelated `deliverables/_mimetype.py`.) |
| 3 | Behavior preserved | ✓ PASS | `test_model_pricing.py` + `test_iss032_cache_tokens.py` → 39 passed. Reconciliation pin present & green (line 127-131): `estimate_cost_usd("eu.anthropic.claude-haiku-4-5-20251001-v1:0", 21_460_378, 225_860) == pytest.approx(24.85, abs=0.01)`. `estimate_cost_usd` signature unchanged: `(model_id: str \| None, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0, *, cache_ttl="5m")`. |
| 4 | INV-3 goldens neutral | ✓ PASS | 5 characterization suites (prototype / od_prototype / prototype_revision / app_builder / od_ppt), SNAPSHOT_UPDATE unset → 10 passed, 0 failed. `git status --short` clean — no golden files modified. (od_ppt passed green here too — strictly satisfies "no new divergence".) |
| 5 | Cost sites untouched / import-safe | ✓ PASS | `git diff --name-only 4cb0aa58~1 5257e42c` = exactly `.planning/FIX-REGISTER.md`, `model_catalog.py`, `model_pricing.py`, `test_model_pricing.py`. engine.py / websocket.py NOT in diff. `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken. |
| 6 | Commits clean | ✓ PASS | 4 code+doc commits (4cb0aa58, 9af3ec1b, 3d6b31d0, 5257e42c) + SUMMARY commit 3865502e — ALL have EMPTY bodies: no `Co-Authored-By`, no `Claude-Session` trailer. On branch `new-workflow-engine`. |

## Observable truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `test_single_source_grep` green with unchanged assertion | ✓ VERIFIED | Passes; diff since baseline empty; still `== {"model_catalog.py"}` |
| 2 | `model_pricing.py` holds zero model-id literals | ✓ VERIFIED | grep exit 1 (no lines) |
| 3 | Prices derive from catalog (no second list) | ✓ VERIFIED | `_resolve_pricing` reads `ModelCatalog().get(...).pricing`; literal machinery deleted |
| 4 | `Pricing` dataclass + field on all 5 entries | ✓ VERIFIED | model_catalog.py L30-59, 5 entries each with `pricing=Pricing(...)` |
| 5 | `estimate_cost_usd` signature + $24.85 pin preserved | ✓ VERIFIED | Signature identical; pin asserts approx(24.85, 0.01) and passes |
| 6 | Goldens byte/event-identical | ✓ VERIFIED | 10 characterization passed, git tree clean |
| 7 | Scope discipline (only 4 files) | ✓ VERIFIED | diff name-only = 4 files; engine/websocket untouched |
| 8 | import-linter 4/0 | ✓ VERIFIED | lint-imports output |

## Verdict

**PASS.** All 6 hard gates and all 8 derived truths independently verified. The
regression is fixed the intended way — the test was preserved verbatim (not loosened),
INV-12 is restored (single model-id list in `model_catalog.py`), the dual-implementation
literal machinery is deleted, behavior (signature + $24.85 pin + cache/regional math) is
preserved, goldens are neutral, and the commit set is clean and correctly scoped.

_Verified: 2026-07-05_
_Verifier: Claude (gsd-verifier), independent gate re-run_

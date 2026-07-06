---
phase: quick-260704-t2x
status: passed
verified_by: orchestrator (independent gate re-run)
date: 2026-07-04
---

# Verification — quick-260704-t2x (per-model / region-aware run-cost pricing)

**Status: passed** — plan-checker PASSED pre-exec; all gates independently re-run by the orchestrator post-exec.

## Must-haves verified against the codebase
- **New kernel-pure module** `backend/agents/capabilities/model_pricing.py` — `Price` frozen dataclass + `MODEL_PRICING` (5 families) + `_canonical` + `_regional_premium` (+10% for eu./us./apac CRIS) + `estimate_cost_usd` (cache-ready). Import-linter: **4 kept / 0 broken** (no `app.*` / `agents.execution_engine` import).
- **Both cost sites routed through the shared function (INV-12):** `engine.py:46/2278` and `websocket.py:18/1994` both `from agents.capabilities.model_pricing import estimate_cost_usd`; residual-formula grep for `0.00000025|0.00000125` → **NONE** (both inline Haiku-3 formulas deleted).
- **Correctness pin:** `estimate_cost_usd("eu.anthropic.claude-haiku-4-5-20251001-v1:0", 21_460_378, 225_860)` = 24.8486 ≈ **$24.85** (was $5.65) — the e49cbccb reconciliation.
- **Cache-ready, fed 0 for now:** `cache_read_tokens`/`cache_write_tokens` params present; call sites pass 0 pending the runner surfacing `input_token_details` (ISS-032 follow-up).

## Invariants
- **INV-3 golden-neutral:** 5 characterization goldens **10/10 byte/event-identical**, SNAPSHOT_UPDATE unset, golden dir clean (no file changed) — `estimated_cost_usd` + `model_id` are `_VOLATILE_STRIP_KEYS`, so a rate swap is invisible by construction.
- **INV-13:** no runtime/loop change. **SC-001:** model dispatch (`_canonical`/`_regional_premium`) lives in the module; call sites pass `model_id` only.

## Tests
- `test_model_pricing.py` → **26 passed** (rates, regional premium, canonicalization incl. unknown→haiku fallback, reconciliation pin, cache tiers, both-sites-import).
- `test_context_providers.py` → green.

## Commits
`a4c4181c` (module) · `52c9825d` (both call sites) · `b576190d` (tests) · `4d949f9a` (FIX-035 + ISS-032).

## Deferred (ISS-032)
Surface `cache_read`/`cache_creation` from the runner `usage_metadata["input_token_details"]`, accumulate into `token_usage`, and thread into `estimate_cost_usd` (subtracting cached from the total input to avoid double-count) — so reported cost tracks the discounted AWS bill once prompt caching is live.

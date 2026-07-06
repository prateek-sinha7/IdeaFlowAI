---
phase: quick-260704-t2x
plan: 01
subsystem: telemetry
tags: [pricing, cost, bedrock, kernel-pure, model_pricing, hexagonal]

requires:
  - phase: quick-260704-p10
    provides: Bedrock prompt caching ON (cachePoints) — motivates the cache-ready pricing tiers + ISS-032 follow-up
provides:
  - Kernel-pure per-family + regional + cache-tier run-cost module (model_pricing.py)
  - One shared estimate_cost_usd routed at BOTH cost sites (INV-12)
  - Corrected run cost (Haiku 1x → Opus ~20x) at engine pipeline_complete + persisted workflow_runs.token_usage
affects: [billing telemetry, cost display, ISS-032 cache-discounted pricing]

tech-stack:
  added: []
  patterns:
    - "Kernel-pure DATA + PURE-FN capability module (stdlib-only), mirroring model_catalog.py"
    - "Single shared cost function at both call sites (no per-model branch at the sites — SC-001)"

key-files:
  created:
    - backend/agents/capabilities/model_pricing.py
    - backend/tests/agents/test_model_pricing.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/app/api/websocket.py
    - .planning/FIX-REGISTER.md
    - .planning/ISSUES-REGISTER.md
    - .planning/STATE.md

key-decisions:
  - "Top-level import of estimate_cost_usd in engine.py (kernel→capability port is the sanctioned direction) rather than a lazy in-method import"
  - "Opus 4.6 / Sonnet 4.6 Bedrock rates DERIVED from the 4.5 tier (in-code operator-confirm note) pending published Bedrock $"
  - "Cache args left at default 0 at both sites — runner does not yet surface cache token counts (tracked as ISS-032)"

patterns-established:
  - "Pattern: model-keyed cost logic lives entirely in the capability module; call sites pass model_id + tokens only"
  - "Pattern: INV-3 golden-neutrality by construction — estimated_cost_usd + model_id are stripped keys, so a rate change cannot perturb a golden"

requirements-completed: [FIX-035, ISS-032]

duration: 12min
completed: 2026-07-04
---

# Phase quick-260704-t2x Plan 01: Per-model / region-aware run-cost pricing Summary

**Kernel-pure `model_pricing.py` with per-family + regional (+10% eu./us./apac) + cache-tier rates, routed through one shared `estimate_cost_usd` at both cost sites — replacing the hardcoded Claude-3-Haiku $0.25/$1.25/M formula that under-reported every non-Haiku run 4x–20x.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-07-04
- **Tasks:** 4
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- New stdlib-only, import-linter-pure `backend/agents/capabilities/model_pricing.py`: `Price` frozen dataclass, `MODEL_PRICING` (5 families with verified base rates), `_FALLBACK`, `_canonical` (prefix/suffix strip, unknown→haiku warn-once), `_regional_premium` (+10% eu./us./apac), and the shared `estimate_cost_usd` (cache-ready: read / write-5m / write-1h tiers).
- BOTH cost sites now compute cost via the ONE shared function (INV-12): engine `pipeline_complete` (~L2277) and the persisted `workflow_runs.token_usage` (~L1993). Both inline `0.00000025/0.00000125` formulas deleted; NULL `model_id` prices against `BEDROCK_INFERENCE_PROFILE_ID`.
- Offline test suite `test_model_pricing.py` (26 cases): per-family rates, regional premium, `_canonical` (incl. unknown→haiku), reconciliation pin `24.85 ±0.01`, cache tiers, premium-compounds, and the INV-12 both-sites source-scan.
- INV-3 preserved: the 5 characterization goldens stay byte/event-identical with SNAPSHOT_UPDATE unset — no regen.

## Task Commits

1. **Task 1: kernel-pure model_pricing module** - `a4c4181c` (feat)
2. **Task 2: route both cost sites through estimate_cost_usd** - `52c9825d` (fix)
3. **Task 3: offline test suite + INV-3 golden gate** - `b576190d` (test)
4. **Task 4: register FIX-035 + ISS-032** - `4d949f9a` (docs)

_(STATE.md updated but intentionally left uncommitted — the GSD orchestrator commits the plan meta-docs.)_

## Files Created/Modified
- `backend/agents/capabilities/model_pricing.py` - The single source of run-cost rates (per-family + regional + cache tiers + `estimate_cost_usd`).
- `backend/agents/execution_engine/engine.py` - `pipeline_complete` cost now via `estimate_cost_usd`; top-level import added.
- `backend/app/api/websocket.py` - Persisted `token_usage` cost now via `estimate_cost_usd`; stale Haiku-pricing comment removed.
- `backend/tests/agents/test_model_pricing.py` - Offline unit + reconciliation + INV-12 both-sites coverage.
- `.planning/FIX-REGISTER.md` - FIX-035 row.
- `.planning/ISSUES-REGISTER.md` - ISS-032 (cache-token surfacing follow-up, OPEN/deferred).

## Decisions Made
- Followed the plan exactly. Opus 4.6 / Sonnet 4.6 Bedrock rates carry an in-code DERIVED / operator-confirm note. Cache args stay 0 at both sites (ISS-032 follow-up).

## Deviations from Plan
None - plan executed exactly as written.

## Verification Gate Results
- **Reconciliation pin:** `estimate_cost_usd("eu.anthropic.claude-haiku-4-5-20251001-v1:0", 21_460_378, 225_860)` ≈ 24.8486 → 24.85 (±0.01). PASS.
- **`test_model_pricing.py`:** 26 passed. PASS.
- **`test_context_providers.py`:** green (46 combined with pricing). PASS.
- **5 characterization goldens** (prototype, od_prototype, prototype_revision, app_builder, od_ppt), SNAPSHOT_UPDATE UNSET: 10 passed, byte/event-identical, NO regen, no golden file changed. PASS.
- **lint-imports (from backend/):** 4 contracts kept, 0 broken — module stays kernel-pure. PASS.
- **Residual formula grep:** no `0.00000025` / `0.00000125` in engine.py or websocket.py. PASS.
- **Purity grep:** PURITY-OK (no `app.*` / `agents.execution_engine` / `agents.workflows` import).

## Known Stubs
Cache args (`cache_read_tokens` / `cache_write_tokens`) are passed as the default 0 at both call sites — an intentional, documented deferral (ISS-032). `estimate_cost_usd` is already cache-ready; the runner does not yet surface cache token counts. Not a blocker: the plan's goal (per-model + regional correction) is fully achieved; cache-discounting is the explicit next step.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Cost telemetry now reflects the run's actual model family + region premium at both the live event and the persisted row.
- Follow-up ISS-032 (OPEN): thread `usage_metadata.input_token_details` cache token counts into `estimate_cost_usd` at both sites for true cache-discounted billing — relevant now that FIX-034 turned Bedrock prompt caching ON.

## Self-Check: PASSED
- FOUND: backend/agents/capabilities/model_pricing.py
- FOUND: backend/tests/agents/test_model_pricing.py
- FOUND commits: a4c4181c, 52c9825d, b576190d, 4d949f9a

---
*Phase: quick-260704-t2x*
*Completed: 2026-07-04*

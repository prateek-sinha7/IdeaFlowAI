---
quick_id: 260705-ed8
date: 2026-07-05
type: quick
mode: backend-regression-fix
branch: new-workflow-engine
status: complete
files_modified:
  - backend/agents/capabilities/model_catalog.py
  - backend/agents/capabilities/model_pricing.py
  - backend/tests/agents/test_model_pricing.py
  - .planning/FIX-REGISTER.md
commits:
  - 4cb0aa58  # Task 1 — Pricing dataclass + pricing field in model_catalog
  - 9af3ec1b  # Task 2 — model_pricing derives from catalog, zero literals
  - 3d6b31d0  # Task 3 — rewired test_model_pricing
  - 5257e42c  # Task 4 — FIX-038 in FIX-REGISTER.md
---

# Quick 260705-ed8: model_pricing INV-12 single-source restore

Restored INV-12 (model-id literals in exactly ONE list) after the earlier
`260704-t2x` quick-task introduced a second hand-maintained model-id list in
`model_pricing.py`. The fix co-locates pricing data IN the authoritative catalog and
makes `model_pricing.py` derive every rate from it — holding ZERO model-id literals.
No test-loosening; the public `estimate_cost_usd` signature + math are unchanged, so
both cost sites and the $24.85 reconciliation pin keep working untouched.

## Regression fixed

t2x created `model_pricing.py` with a literal `MODEL_PRICING` dict keyed by
model-family literals (`claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-sonnet-4-6`,
`claude-opus-4-5`, `claude-opus-4-6`). That was a SECOND model-id list, which:
1. Violated INV-12 (single model-id source = `model_catalog.py`), and
2. Broke `test_model_catalog::test_single_source_grep` — which greps
   `backend/app/api` + `backend/agents/capabilities` for `claude-(haiku|sonnet|opus)-4`
   on non-comment lines and asserts the hit set is exactly `{model_catalog.py}`.
   Post-t2x it saw `{model_catalog.py, model_pricing.py}` → FAIL (green at baseline
   `eb3ccced`, red at t2x HEAD).

## What changed

- **`model_catalog.py` (Task 1, additive):** added a frozen `Pricing` dataclass
  (`input, output, cache_read, cache_write_5m, cache_write_1h` — USD per single
  token, base/pre-premium) above `ModelEntry`, and appended a `pricing: Pricing`
  field to `ModelEntry`. All 5 entries carry the verified rates (Haiku/Sonnet-4.5/
  Sonnet-4.6/Opus-4.5/Opus-4.6). The "Opus 4.6 / Sonnet 4.6 Bedrock $ are DERIVED —
  operator confirm" caveat comment moved here, next to the 4.6 entries. No existing
  field/value touched, so the `/api/settings` projection + catalog tests stay green.
- **`model_pricing.py` (Task 2, rewrite):** deleted the literal `MODEL_PRICING` dict,
  the local `Price` dataclass, `_FALLBACK`, and `_canonical` (all held claude-*-4
  literals). Now imports `ModelCatalog, Pricing` from `model_catalog` and derives
  each model's `Pricing` via a three-tier `_resolve_pricing`. Kept `_regional_premium`
  and the exact `estimate_cost_usd` signature + math. ZERO model-id literals remain.
- **`test_model_pricing.py` (Task 3):** rewired to the catalog-derived structure —
  asserts the catalog carries the rates, covers the three `_resolve_pricing` tiers,
  and preserves every behavioral pin.
- **`.planning/FIX-REGISTER.md` (Task 4):** logged FIX-038 (dated 2026-07-05, after
  FIX-037, 8-column layout, `INV-1/3/12/13 · SC-001 ✅`).

## Three-tier `_resolve_pricing(model_id) -> Pricing`

1. **Exact:** `ModelCatalog().get(model_id).pricing` if the id matches a catalog entry.
2. **Normalized fallback:** strip leading region/provider prefixes (`eu./us./apac./
   global./anthropic.`) and trailing version/date suffixes off BOTH the input id and
   each catalog id, then match on the bare family form (so `us.…-v1` maps to the
   `eu.…` seed). Prefix tuple + suffix regex carry no model-id literals.
3. **Cheap default:** the catalog's `cost_class == "cheap"` entry's pricing (located
   by cost_class, not by a literal id), with a warn-once log for the unknown id.

`_regional_premium` (eu./us./apac → 1.10, else 1.0) is unchanged. A `None`/unknown id
prices as the cheap (Haiku) tier at 1.0x.

## Gate results (all 6 pass)

1. `test_model_catalog.py` — **9 passed**, incl. `test_single_source_grep` GREEN
   (hit set == `{model_catalog.py}`).
2. `test_model_pricing.py` + `test_iss032_cache_tokens.py` — **39 passed**;
   reconciliation pin holds: `estimate_cost_usd("eu.anthropic.claude-haiku-4-5-…",
   21_460_378, 225_860) ≈ 24.85 (±0.01)` observed green.
3. Characterization goldens (prototype / od_prototype / prototype_revision /
   app_builder / od_ppt), SNAPSHOT_UPDATE unset — **10 passed**, no golden
   divergence (od_ppt was green here too — better than the expected known-red shape;
   cost + model_id are stripped volatile keys, so the change is golden-neutral).
4. `lint-imports` — **4 kept / 0 broken** (`Pricing`/`ModelCatalog` import is a
   sibling within `agents.capabilities`, contract-safe).
5. `grep -nE 'claude-(haiku|sonnet|opus)-4' agents/capabilities/model_pricing.py` —
   **zero lines** (no non-comment, no comment literals at all).
6. Scope — `git diff --name-only HEAD~4 HEAD` = exactly the 4 intended files
   (`model_catalog.py`, `model_pricing.py`, `test_model_pricing.py`, FIX-REGISTER.md);
   engine.py / websocket.py / deep_agent_runner untouched.

## Invariants

- **INV-1 / SC-001:** cost dispatch keys off model_id + region only — no workflow-name
  or agent branching in the pricing path.
- **INV-3:** goldens byte-identical + event-parity (cost + model_id are stripped
  volatile keys); all 10 characterization tests green.
- **INV-12:** model-id literals live in exactly ONE list — `model_catalog.py` —
  RESTORED (the whole point).
- **INV-13:** no agent-runtime / loop / deepagents change.

## Deviations from Plan

None — plan executed exactly as written. Note: the plan anticipated `od_ppt` as a
known pre-existing offline red for gate 3; in this run it passed green alongside the
other 4, which strictly satisfies the "no new golden divergence" gate.

## Commits

- `4cb0aa58` fix(agents): co-locate frozen Pricing + pricing field in model_catalog (INV-12 single source)
- `9af3ec1b` fix(agents): derive model_pricing rates from catalog — remove model-id literals (INV-12)
- `3d6b31d0` test(agents): rewire test_model_pricing to catalog-derived pricing (pins preserved)
- `5257e42c` docs(planning): add FIX-038 (model_pricing INV-12 single-source restore)

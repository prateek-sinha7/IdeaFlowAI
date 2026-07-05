---
phase: quick-260704-uvs
status: passed
verified_by: orchestrator (independent gate re-run)
date: 2026-07-04
---

# Verification — quick-260704-uvs (show prompt-cache token breakdown in the UI)

**Status: passed** — plan-checker PASSED pre-exec; all gates independently re-run.

## Must-haves verified
- **Threaded (FE):** `types/index.ts` tokenUsage + `PipelineRunState` carry the optional cache fields; `useWorkflow.ts` parses `total_cache_read_tokens`/`total_cache_write_tokens` from the `pipeline_complete` token_usage into `pipelineState.cacheReadTokens`/`cacheWriteTokens`; `api.ts` unchanged (its `JSON.parse(token_usage)` already carries the keys).
- **Rendered:** `TokenUsageSummary.tsx` destructures the cache fields (L34), and renders `⚡ {formatTokens(cacheRead)} cached ({pct}%)` (L70) ONLY when `cacheReadTokens > 0`; the cost figure is unchanged (already discounted).
- **Zero-regression:** when `cacheReadTokens` is 0/undefined (the common case until a live cached run) the render is byte-identical to before — asserted by the new specs.

## Tests / gates (independent re-run)
- `vitest run TokenUsageSummary useWorkflow` → **12/12 passed** (incl. new `TokenUsageSummary.cache.test.tsx`: cached / undefined / zero / written>0 / written=0).
- tsc-identity → only the 2 pre-existing `e2e/fixtures/mockApi.ts` errors, **zero new**.
- Scope: only `types/index.ts`, `useWorkflow.ts`, `TokenUsageSummary.tsx` (+ new `.cache.test.tsx`) + 2 register docs. No backend/golden touch.

## Invariants
- **INV-12:** no dollar/per-model math on the FE — token count + integer % only; `estimatedCostUsd` untouched. **SC-001:** the segment gates on `cacheReadTokens > 0` (a value, not a workflow name).

## Commits
`4b22ab74` (threading) · `b845d0f9` (render + test) · `3d8ff806` (FIX-037 + ISS-034).

## Deferred (ISS-034)
Explicit dollar-savings ("saved $Y, Z%") needs the backend to also emit `estimated_cost_full_usd` (cost priced as-if-uncached); FE would then show the delta. Non-zero cache values (and the visible breakdown) appear only after a live Bedrock run with caching.

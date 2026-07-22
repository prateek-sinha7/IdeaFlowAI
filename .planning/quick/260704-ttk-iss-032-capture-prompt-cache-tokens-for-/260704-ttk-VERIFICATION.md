---
phase: quick-260704-ttk
status: passed
verified_by: orchestrator (independent gate re-run)
date: 2026-07-04
---

# Verification — quick-260704-ttk (ISS-032: capture prompt-cache tokens for costing)

**Status: passed** — plan-checker PASSED pre-exec; all gates independently re-run by the orchestrator.

## Must-haves verified against the codebase
- **Producer (runner + engine):** `_cache_token_counts` surfaces `usage_metadata["input_token_details"]` (`cache_read`/`cache_creation`) into the usage event + `TokenUsage`; engine accumulates per-agent → `results` + `agent_complete` + `pipeline_complete` run totals. Universal (shared runner/engine → every workflow's agents).
- **Consumer (both cost sites, no double-count):** `engine.py:2293` and `websocket.py:2008` both price `input_tokens=max(0, total − cache_read − cache_write)` + `cache_read_tokens` (0.1×) + `cache_write_tokens` (1.25×/2×) + `cache_ttl` — confirmed by grep.
- **INV-3 golden-neutral, NO regen:** 5 characterization goldens **10/10 byte/event-identical**, SNAPSHOT_UPDATE unset, **golden dir clean** (no file changed). The 4 new payload keys (`cache_read_tokens`, `cache_write_tokens` on `agent_complete`; `total_cache_read_tokens`, `total_cache_write_tokens` on `pipeline_complete`) are added to `_VOLATILE_STRIP_KEYS` (lines 159-162). Under the scripted model there is no `input_token_details` → cache=0 → uncached=total → cost/token math identical.
- **INV-12:** single shared `estimate_cost_usd`, identical split at both sites. **INV-13:** plumbing only, no loop change. **SC-001:** no workflow-name branch.

## Tests / lint
- `test_iss032_cache_tokens.py` + `test_model_pricing.py` → **38 passed**. `test_context_providers.py` green (executor run).
- `lint-imports` → **4 kept / 0 broken**.

## Commits
`34849369` (producer) · `2e5e0912` (cost split) · `82f400da` (tests) · `16b89f03` (FIX-036 + ISS-032 RESOLVED + ISS-033).

## Deferred
Live `cache_read_input_tokens > 0` confirmation → end-of-milestone Bedrock pass (offline structural proof landed). **ISS-033** logged: SmartPlanner + ClarifyEngine (+ handoff Test/Compliance agents) call the model DIRECTLY (bypass the runner) → still no caching + uncounted cost; the shared cached-invoke-helper fix to make caching truly universal.

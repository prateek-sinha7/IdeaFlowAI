---
phase: quick-260704-ttk
plan: 01
subsystem: agents / execution-engine / run-cost
tags: [ISS-032, FIX-036, ISS-033, prompt-cache, run-cost, INV-3, INV-12, SC-001]
requires:
  - FIX-035 (per-model estimate_cost_usd, cache-ready tiers)
  - FIX-034 (Bedrock prompt caching ON in prod)
provides:
  - Runner surfaces the Bedrock prompt-cache split into the usage event + TokenUsage
  - Engine per-agent cache accumulation → agent_complete + pipeline_complete run totals
  - Both cost sites price the UNCACHED input split (no double-count)
affects:
  - backend/app/agents/deep_agent_runner.py
  - backend/agents/execution_engine/engine.py
  - backend/app/api/websocket.py
  - backend/tests/agents/characterization/_normalize.py
tech-stack:
  added: []
  patterns:
    - ADDITIVE _VOLATILE_STRIP_KEYS for golden-neutral event-key additions (INV-3)
    - single shared estimate_cost_usd at both cost sites (INV-12)
key-files:
  created:
    - backend/tests/agents/test_iss032_cache_tokens.py
  modified:
    - backend/app/agents/deep_agent_runner.py
    - backend/agents/execution_engine/engine.py
    - backend/app/api/websocket.py
    - backend/tests/agents/characterization/_normalize.py
    - .planning/FIX-REGISTER.md
    - .planning/ISSUES-REGISTER.md
    - .planning/STATE.md
decisions:
  - "Runner keeps input_tokens as the TOTAL (incl. cache); the uncached split is computed only at the cost sites — never subtract twice."
  - "The 4 new event keys are additive telemetry (not in _REQUIRED_DATA_KEYS) → stripped by _VOLATILE_STRIP_KEYS, so no golden regen."
  - "Direct-call agents (SmartPlanner/ClarifyEngine/handoff) deliberately out of scope → logged as ISS-033."
metrics:
  duration: ~15 min
  tasks: 4
  files: 7
  completed: 2026-07-04
---

# Phase quick-260704-ttk Plan 01: Capture Prompt-Cache Tokens for Cost (ISS-032) Summary

Surfaced the Bedrock prompt-cache token split (`input_token_details={cache_read, cache_creation}`) through the SHARED deep-agent runner → engine → both run-cost sites, so cached runs are priced on the UNCACHED input split with no double-count — universal for every workflow's agents, golden-neutral, no engine-by-name branch.

## What Was Built

**Task 1 — Producer plumbing (commit 34849369).**
- New module-level pure helper `_cache_token_counts(meta) -> (cache_read, cache_write)` in the runner, guarding `meta or {}` / `input_token_details or {}` with `int(... or 0)` → `(0, 0)` on any absent/None/partial shape (ChatAnthropic/scripted/no-cache), never raises.
- The `on_chat_model_end` usage-emit now carries `cache_read_tokens`/`cache_write_tokens` (input_tokens stays the TOTAL); `astream_with_usage` sums the split into the text-only `TokenUsage`. Two docstrings updated (class usage-event contract + the now-stale astream note).
- Engine accumulates `agent_cache_read_tokens`/`agent_cache_write_tokens` per attempt (reset at both per-attempt init points), threads them onto `results[i]` + the `agent_complete` event, and sums run totals `total_cache_read_tokens`/`total_cache_write_tokens` onto `pipeline_complete`.
- Normalizer: the 4 new keys added to `_VOLATILE_STRIP_KEYS` (ADDITIVE, deliverable_mimetype/redoable precedent) → INV-3 goldens byte-identical.

**Task 2 — Consumer/pricing split (commit 2e5e0912).**
- Both cost sites now call `estimate_cost_usd(model, input_tokens=max(0, total − cache_read − cache_write), output_tokens=…, cache_read_tokens=…, cache_write_tokens=…, cache_ttl=BEDROCK_PROMPT_CACHE_TTL)` — the engine `pipeline_complete` value and the persisted `workflow_runs.token_usage`. The websocket `agent_complete` collector threads per-agent cache counts into the run-total sum. Input telemetry stays the TOTAL; only the cost is discounted.

**Task 3 — Offline test suite (commit 82f400da).**
- New `tests/agents/test_iss032_cache_tokens.py`: extraction + (0,0) defaults on absent/None/partial; source-pinned usage-event wiring; no-double-count cost split strictly less than all-at-1x + exact hand-computed value (`(5000·1e-6 + 60000·0.1e-6 + 5000·1.25e-6)·1.10`); normalizer strips all 4 keys on agent_complete + pipeline_complete.

**Task 4 — Registers (commit 16b89f03).**
- FIX-036 appended to FIX-REGISTER.md; ISS-032 flipped OPEN → RESOLVED; ISS-033 logged (direct-call agents bypass caching + uncounted cost). STATE.md "Last activity" updated (STATE commit left to the orchestrator).

## Deviations from Plan

None — plan executed exactly as written. One trivial in-test adjustment: `_normalize` operates on a list, so the single-event normalizer tests use the sibling `_normalize_event`, and the surviving `input_tokens` key is asserted present (it is volatile-required → sentinel-normalized, not stripped) rather than equal to its literal value.

## Verification Results

- `test_iss032_cache_tokens.py` + `test_model_pricing.py` + `test_context_providers.py` → **58 passed**.
- 5 characterization goldens (prototype, od_prototype, prototype_revision, app_builder, od_ppt) → **10 passed**, SNAPSHOT_UPDATE UNSET, **NO golden JSON regenerated** (INV-3 preserved).
- `grep -c 'cache_ttl='` → 1 in engine.py + 1 in websocket.py (both cost sites price the split).
- `/opt/homebrew/bin/lint-imports` → **4 contracts kept, 0 broken**.
- Docs gate → DOCS-OK (FIX-036, ISS-032 RESOLVED, ISS-033, 260704-ttk in STATE).

## Invariants

- INV-3 golden-neutral: additive stripped keys, no regen.
- INV-12: the ONE shared `estimate_cost_usd` at both sites.
- INV-13: plumbing only — no deepagents-loop / cachePoints middleware / thinking / pricing-table change.
- SC-001: the fix lives in the shared runner + engine + shared cost fn — no workflow/agent-name branch.

## Known Stubs

None.

## Self-Check: PASSED

- Created file `backend/tests/agents/test_iss032_cache_tokens.py` — FOUND.
- Commits 34849369, 2e5e0912, 82f400da, 16b89f03 — all present in `git log`.

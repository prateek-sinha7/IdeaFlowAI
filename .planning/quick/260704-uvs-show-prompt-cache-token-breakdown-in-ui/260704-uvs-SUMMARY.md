---
phase: quick-260704-uvs
plan: 01
subsystem: frontend / workflow token-usage UI
tags: [frontend, prompt-cache, token-usage, ui, FIX-037]
requires:
  - "Backend FIX-036: pipeline_complete + persisted token_usage emit total_cache_read_tokens/total_cache_write_tokens; estimated_cost_usd already cache-discounted"
provides:
  - "PipelineRunState.cacheReadTokens/cacheWriteTokens threaded from WS events"
  - "WorkflowRun.tokenUsage optional cache keys (type-visible from persisted JSON)"
  - "Conditional '⚡ N cached (X%)' segment in TokenUsageSummary"
affects:
  - frontend/src/components/workflow/TokenUsageSummary.tsx
tech-stack:
  added: []
  patterns:
    - "Consume-only FE surfacing of already-emitted backend fields (no new data source, INV-12)"
    - "Render gate (cacheRead > 0) → byte-identical no-cache render"
key-files:
  created:
    - frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx
  modified:
    - frontend/src/types/index.ts
    - frontend/src/hooks/useWorkflow.ts
    - frontend/src/components/workflow/TokenUsageSummary.tsx
    - .planning/FIX-REGISTER.md
    - .planning/ISSUES-REGISTER.md
    - .planning/STATE.md
decisions:
  - "No FE dollar/per-model math (INV-12) — cost already discounted by FIX-036; dollar-savings deferred to ISS-034"
  - "agent_complete handler only preserves prev cache totals (msg carries no run-level cache total); pipeline_complete is authoritative"
metrics:
  duration: ~15m
  completed: 2026-07-04
---

# Phase quick-260704-uvs Plan 01: Show Prompt-Cache Token Breakdown in UI Summary

Surface the prompt-cache token breakdown in the workflow token-usage UI — a FRONTEND-ONLY consume of the already-emitted FIX-036 `total_cache_read_tokens`/`total_cache_write_tokens` fields, rendering a conditional `⚡ N cached (X%)` segment with zero regression when cache is 0.

## What Was Built

**Task 1 — Thread cache fields through types + WS parse** (`4b22ab74`)
- `frontend/src/types/index.ts`: added optional `total_cache_read_tokens?`/`total_cache_write_tokens?` to `WorkflowRun.tokenUsage` (makes the already-parsed persisted keys type-visible) and optional `cacheReadTokens?`/`cacheWriteTokens?` on `PipelineRunState`.
- `frontend/src/hooks/useWorkflow.ts`: threaded the cache totals into `pipelineState` in both `pipeline_complete` (authoritative run totals from `msg.total_cache_read_tokens`) and `agent_complete` (msg has no run-level total → simply preserves `prev`), both using the sibling `(msg.x as number) || prev.x || 0` fallback idiom.
- `frontend/src/lib/api.ts`: verified only — `JSON.parse(raw.token_usage)` carries the cache keys verbatim; the Task-1 type change makes them visible. No logic change needed.

**Task 2 — Render conditional cached segment + rendered-DOM tests** (`b845d0f9`)
- `frontend/src/components/workflow/TokenUsageSummary.tsx`: destructured `cacheReadTokens`/`cacheWriteTokens`; computed `cacheRead`/`cacheWrite`/`pct = Math.round(cacheRead / Math.max(1, input) * 100)`; inserted a `·`-separated `⚡ {formatTokens(cacheRead)} cached ({pct}%)` span (amber-600 accent) after the input span and before the output separator, gated on `cacheRead > 0`, with an optional `· {formatTokens(cacheWrite)} written` fragment when `cacheWrite > 0`. When `cacheRead === 0` the whole fragment is behind the gate → render is byte-identical to before.
- `frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx`: new @testing-library/react specs (motion/react mocked per repo harness). Spec A (cached: asserts "cached"/"86%"/"60.0K"), Spec B + B2 (no-cache undefined/0: no "cached", input/output still present), Spec C + C2 (write>0 renders "written"; write=0 does not).

**Task 3 — Docs** (`3d8ff806`)
- `.planning/FIX-REGISTER.md`: FIX-037 8-column row after FIX-036 (Status Done).
- `.planning/ISSUES-REGISTER.md`: ISS-034 6-column row after ISS-033 (Status OPEN — deferred dollar-savings follow-up).
- `.planning/STATE.md`: recorded the quick-260704-uvs completion + ISS-034 follow-up (narrative fields; STATE.md left uncommitted for the orchestrator).

## Deviations from Plan

None — plan executed as written. The plan-checker-corrected tsc command was used in place of the Task-1 verify stub (`frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit`).

## Verification Results

- `vitest run TokenUsageSummary useWorkflow` → **12/12 passed** (3 test files), including the new `TokenUsageSummary.cache.test.tsx` (5 specs).
- tsc-identity (`tsc -p frontend/tsconfig.json --noEmit`) → only the **2 pre-existing** `e2e/fixtures/mockApi.ts` errors, **ZERO new** (0 errors outside mockApi).
- Scope: only `types/index.ts`, `useWorkflow.ts`, `TokenUsageSummary.tsx` (+ new `.cache.test.tsx`) under `frontend/src`; docs limited to FIX-REGISTER + ISSUES-REGISTER (+ STATE.md, uncommitted for orchestrator). `api.ts` untouched. No backend/golden/WorkflowHistory/AnalyticsPage change. FE dev server not launched.

## Known Stubs

None. The cached segment is data-driven from live WS/persisted fields; the no-cache render is the intended common case until a live cached run.

## Self-Check: PASSED

- Created file present: `frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx` — FOUND.
- Commits: `4b22ab74`, `b845d0f9`, `3d8ff806` — all FOUND in `git log`.

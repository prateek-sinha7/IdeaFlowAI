---
phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
plan: 06
subsystem: infra
tags: [constitution, workflow-memory, prompt-assembly, async-sync-bridge, R12, F4, INV-3, INV-12, AGENTRT-06]

# Dependency graph
requires:
  - phase: 08-05
    provides: "PromptAssemblyPolicy (prompt:default) — the constitution slot the pre-warmed block plugs into; F1/F3/F5 already deleted"
provides:
  - "Constitution sync-safe / pre-warmed injection — a DB-stored Constitution is injected into the composed prompt under a running event loop (production); the R12 no-op is fixed"
  - "ExecutionContext.prewarmed_constitution + AgentContext.prewarmed_constitution — the pre-warm seam: owner Constitution awaited ONCE at engine run entry, threaded into each per-agent context, read sync-safely by the factory"
  - "Deleted: the R12 _mem-only event-loop-running branch in _inject_constitution (factory.py); F4 ledger row ☑ — all F1–F5 rows now ☑"
affects: [08-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Async-prewarm-then-sync-read: the async engine awaits an async dependency ONCE at run entry and stashes the value on the per-run/per-agent context so a SYNC factory under a running event loop reads it without awaiting (no async-in-running-loop hazard) — RESEARCH A3 / D-08 lower-risk option vs run_coroutine_threadsafe"

key-files:
  created:
    - "backend/tests/agents/test_constitution_prod.py (AGENTRT-06 constitution-injected-in-prod test, NEW — 3 cases under a running event loop)"
  modified:
    - "backend/agents/factory.py (AgentContext.prewarmed_constitution field; _inject_constitution rewired to the single sync-safe pre-warmed read; R12 _mem-only running-loop branch DELETED)"
    - "backend/agents/execution_engine/engine.py (Constitution pre-warm at run entry — await get_constitution once; thread prewarmed_constitution into each per-agent AgentContext)"
    - "backend/agents/execution_engine/context.py (ExecutionContext.prewarmed_constitution field)"
    - "backend/tests/agents/test_migration_ledger.py (F4 added to the expected flipped set; docstring updated — all F1–F5 ☑ after 08-06)"
    - "specs/003-workflow-engine-decoupling/migration-ledger.md (F4 row ☐ → ☑, SHA 5d0c704)"

key-decisions:
  - "Pre-warm-at-run-entry (RESEARCH A3 / D-08): await get_constitution ONCE in execute() before the sync create_runner calls and stash on the context — chosen over run_coroutine_threadsafe / a worker thread because it has no await-in-running-loop hazard"
  - "Pre-warm key = ectx.disk_principal (the SAME value threaded as AgentContext.user_id in _run_agent — the factory's effective Constitution key) so the pre-warmed value matches what the factory would have resolved"
  - "Best-effort pre-warm: a DB/store failure logs a warning and degrades to None (graceful no-op) so the offline characterization harness (no DB, no Constitution) stays byte-identical (INV-3)"
  - "INV-12 single path: _inject_constitution now has ONE branch (read prewarmed_constitution); the _mem-only running-loop fallback AND the dead loop.run_until_complete sync-context path were both deleted — no dual implementation"

requirements-completed: [AGENTRT-06]

metrics:
  duration: ~12 min
  completed: 2026-06-09
  tasks: 2
  files-created: 1
  files-modified: 5
---

# Phase 8 Plan 6: Constitution Sync-Safe Pre-Warm (F4/R12) Summary

Fixed the R12 constitution no-op: a Postgres/DB-stored Constitution is now injected into the composed prompt under a running event loop (production) via an async-prewarm-then-sync-read seam, and the broken `_mem`-only running-loop branch is deleted (F4 ledger row ☑ — all F1–F5 now ☑).

## What Was Built

**The bug (R12 / F4):** `factory._inject_constitution` is SYNC but is called from the async engine (`_run_agent`) under a running event loop. Its old running-loop branch read only the in-process `WorkflowMemory._mem` dict — so a Constitution stored in Postgres (the production store) was silently NOT injected. The no-op only "worked" in unit tests because those use the `_mem` fallback.

**The fix (pre-warm at run entry — RESEARCH A3 / D-08, the lower-risk option):**
1. `ExecutionEngine.execute()` awaits `get_constitution(disk_principal)` ONCE at run entry (after `disk_skills` load, before the per-agent `create_runner` calls) and stashes the value on `ExecutionContext.prewarmed_constitution`. Best-effort: a store failure degrades to `None`.
2. `_run_agent` threads `ectx.prewarmed_constitution` into each per-agent `AgentContext`.
3. `_inject_constitution` reads `ctx.prewarmed_constitution` sync-safely (no await, no event-loop access) — a DB-stored Constitution now appears in the prompt under a running loop.

**Task sequencing (deletion-after-proof):** Task 1 added the pre-warm seam + the sync-safe read + the NEW `test_constitution_prod.py` while leaving the R12 branch in place. Task 2 — once the new test + the 5 snapshots proved parity — DELETED the R12 `_mem`-only branch (and the dead `loop.run_until_complete` sync-context path), leaving a single sync-safe path (INV-12), and flipped the F4 ledger row.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Pre-warm Constitution at run entry + sync-safe read; NEW in-prod test | 5d0c704 | engine.py, context.py, factory.py, test_constitution_prod.py (new) |
| 2 | DELETE R12 `_mem`-only running-loop branch; flip F4 ledger row | 6f897b0 | factory.py, test_migration_ledger.py, migration-ledger.md |

## Verification

- `test_constitution_prod.py` — 3 cases, all PASS under a running event loop: (a) DB-stored Constitution injected (`## Constitution (Governing Principles` + body present); (b) no Constitution → graceful no-op (no block); (c) no `RuntimeError: event loop already running`.
- `test_migration_ledger.py` — PASS; F4 row ☑; all F1–F5 ☑ (`grep -E '^\| F[1-5] ' migration-ledger.md` → 5× ☑).
- 5 characterization snapshots (prototype / app_builder / od_ppt / od_prototype / prototype_revision) — byte/event-identical, NO re-baseline (the runs set no Constitution → the pre-warm is invisible).
- `grep -c "_mem.get" agents/factory.py` → 0 (R12 branch deleted).
- `grep -rln "constitution" tests/agents/characterization/` → empty (A4 confirmed: characterization fixtures carry no Constitution).
- `test_guardrails.py` — 13 PASS (the simplified `_inject_constitution` keeps the existing guardrail/constitution composition intact).
- `lint-imports` — 3 kept / 0 broken (hexagonal boundaries intact).

Full gate `pytest test_constitution_prod.py test_migration_ledger.py test_characterization_*.py -x` → 33 passed, 3 skipped.

## Parity Trap Verified (A4)

Per RESEARCH A4 and the CONTEXT note, the characterization fixtures set NO Constitution (and no `user_id`) — verified by grep BEFORE relying on it. The fix is therefore invisible to the snapshots (they stay byte-identical), and `test_constitution_prod.py` is a NEW additive test, not a snapshot re-baseline. No characterization fixture unexpectedly set a Constitution, so no surfacing/escalation was needed.

## Deviations from Plan

None — plan executed as written. Minor cleanups within plan intent:
- Removed the now-dead `loop.run_until_complete` sync-context branch from `_inject_constitution` (not just the `_mem`-only running-loop branch the plan names) — the pre-warmed read supersedes the entire async-bridge scaffolding, so leaving the sync-context path would be a residual dual implementation (INV-12). The outer `try/except` wrapping only the format-string return was also dropped as dead (no exception path remained).

## Threat Surface

No new security-relevant surface. The plan's threat register (T-08-06-R: constitution silently dropped in prod) is now MITIGATED — the in-prod test is the gate. T-08-06-parity is mitigated (snapshots byte-identical). No package installs (T-08-06-SC: accept).

## Self-Check: PASSED

- FOUND: backend/tests/agents/test_constitution_prod.py
- FOUND: commit 5d0c704 (Task 1)
- FOUND: commit 6f897b0 (Task 2)
- FOUND: factory.py `_mem.get` count = 0; migration-ledger F4 row ☑; all F1–F5 ☑

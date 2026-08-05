---
id: REQ-11
type: req
status: done
area: [workflow, agents, auth, artifacts, runtime]
summary: >-
  Engine-Owned Fan-Out & Merge (Phase 5)
source: .planning/REQUIREMENTS.md#engine-owned-fan-out-merge-phase-5
---

### Engine-Owned Fan-Out & Merge (Phase 5)

- [x] **FANOUT-01**: `spawn_subagents(tasks=[{agent,input}], mode=…)` tool bound only to steps granted `tools.spawn_subagents`; it emits a structured request — the kernel fulfils it (INV-7 / §6/§12) ✅ 11-01
- [x] **FANOUT-02**: Kernel `run_fanout(requests, ctx)` funnels both declarative (`step.fanout`) and runtime (tool) entry points (§12) ✅ 11-01
- [x] **FANOUT-03**: Worker selection — `agent="self"` (N copies) or a named worker from `allowed_workers` + registry (Q14) ✅ 11-01
- [x] **FANOUT-04**: Mode parallel (capped `asyncio.gather`) or sequential; engine enforces `max_concurrency` (Q15) ✅ 11-01
- [x] **FANOUT-05**: `IsolationProvider.allocate(scope)` → shared_read | sub_sandbox | worktree; writes default isolated (Q20/Q34 — N2 SETTLED: shipped in Phase 11 [5]; writes-default-isolated decision recorded, no open question)
- [x] **FANOUT-06**: Results return both files/artifacts and a structured summary (Q16)
- [x] **FANOUT-07**: `MergeStrategy` integrates fragments (copy_disjoint/git_3way/json/html_fragment) (§13)
- [x] **FANOUT-08**: Merge-conflict flow — write a `merge_conflict` artifact + emit event; resolve per `on_conflict` policy (human_gate default | merge_agent (bounded) | partial | abort) (§13 / A6)
- [x] **FANOUT-09**: `BudgetManager` reserves-before-spawn and enforces total subagents, concurrency, tokens, cost, wall-clock, recursion, fan-out depth (`ctx.depth`); `BudgetExceeded` aborts gracefully with partial results (Q17/Q18/Q44)
- [x] **FANOUT-10**: Each child → a `subagent_runs` row; events `subagent_spawned`/`subagent_result`/`merge_*` (§12/§18) ✅ 11-01 (subagent_runs row + subagent_spawned/subagent_result; merge_* lands 11-03)
- [x] **FANOUT-11**: Fan-out cancellation propagates to children (§21)

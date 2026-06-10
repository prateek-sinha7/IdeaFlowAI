# Phase 11: Engine-Owned Fan-Out + Merge [5] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 11-engine-owned-fan-out-merge-5
**Areas discussed:** none deep-dived — all four locked to recommendations at the user's direction

---

## Session shape

SPEC-first session: `11-SPEC.md` was written the same day via `/gsd-spec-phase 11` (13 requirements locked; the spec interview locked budget defaults 8/4/2/900s, € dormancy, and the panel→Phase-12 deferral — see the SPEC's own Interview Log). This discuss-phase session then presented four HOW gray areas. The AskUserQuestion TUI received no response twice; per the answer-validation rule the areas were re-presented as a plain-text numbered list. The user replied: **"none — lock recommendations"** — all four areas locked to Claude's plan-grounded recommendations (the Phase 1–8 pattern).

## Gray areas presented (all locked to the recommendation)

## Worker execution shape

| Option | Description | Selected |
|--------|-------------|----------|
| One isolated agent invocation (recommended) | Via existing `KernelServices.run_agent`/`create_runner`, per-worker thread_id `{run_id}:{step}:{worker_i}` (build-loop precedent), no per-worker gates/validators; children are `subagent_runs` rows | ✓ (locked) |
| Nested mini-run per child | Full engine invocation with gates/validators per child; implies `workflow_runs` rows + full event streams | |

**User's choice:** Locked recommendation without deep-dive ("none — lock recommendations")
**Notes:** Captured as D-01 in CONTEXT.md with the Q17 nesting rule (`ctx.depth+1`, cap 2) and researcher directives on workspace threading + token accumulation.

## Declarative entry shape

| Option | Description | Selected |
|--------|-------------|----------|
| Registered `fanout_batch` strategy (recommended) | The Q8/base.py reserved name; sources tasks from declared `TaskSource`, maps task→worker, submits to `run_fanout`; compiler materializes `FanoutSpec` | ✓ (locked) |
| `step.fanout` as a modifier on any strategy | More general but undefined semantics for `task_loop × fanout`; parallel task scheduling is Phase 12's `wave_scheduler` | |

**User's choice:** Locked recommendation without deep-dive
**Notes:** Captured as D-02 with the mid-stream tool-interception researcher directive (the riskiest research item).

## Child event streaming

| Option | Description | Selected |
|--------|-------------|----------|
| Lifecycle-only (recommended) | `subagent_spawned`/`subagent_result`/`merge_*`/`budget_warning`; child chunks suppressed (non-yielding fix-loop precedent); summary + rows carry detail | ✓ (locked) |
| Tagged `subagent_chunk` streaming | Rich live visibility but noisy; event-schema surface with no consumer until the P12 panel | |
| Mode-dependent (sequential streams, parallel doesn't) | Inconsistent contract | |

**User's choice:** Locked recommendation without deep-dive
**Notes:** Captured as D-03; tagged streaming noted as an additive later option in Deferred Ideas.

## Merge mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| Merge into parent run workspace (recommended) | Base = run sandbox / repo working branch; fragments = child workspaces; fragments persist as artifacts pre-merge; worktree branch-per-worker `fanout/{step}/{i}` with `LocalWorkspace` as single git owner | ✓ (locked) |
| Merge into a fresh staging workspace | Extra copy step; deliverable resolvers would need re-pointing | |

**User's choice:** Locked recommendation without deep-dive
**Notes:** Captured as D-04 with concrete per-strategy conflict semantics and worktree/sub_sandbox mechanics + researcher directives.

## Claude's Discretion

- Exact `FanoutSpec`/`allowed_workers` field names + compiler materialization
- Event payload schemas within the locked families
- `subagent_runs` column types/indexes within §18's fields
- Worktree branch naming + spawn-point capture; `IsolationProvider` impl registration vs host-seam binding (import-linter gates)
- Merge strategy kernel-side vs app-side placement per the heavy-dep boundary
- Plan-task granularity within the ROADMAP's 5-plan frame; where 0019 rides

## Deferred Ideas

- Wave scheduler/`wave_runs`/mid-wave resume → Phase 12
- Frontend subagent-tree panel + subagents read endpoint → Phase 12 (SPEC round-1 decision)
- `subagent_chunk` tagged streaming → additive later
- Real € price table/enforcement → when a price source exists
- Prototype fragment-merge wiring → MERGE-01 v2
- User-grantable `spawn_subagents` → user-composer trust work
- Durable long-job queue → N8 (in-process for v1)
- Workspace budget-ceiling UI → later

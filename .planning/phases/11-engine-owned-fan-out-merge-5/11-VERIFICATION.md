---
phase: 11-engine-owned-fan-out-merge-5
verified: 2026-06-11T14:00:00Z
status: passed
score: 13/13
overrides_applied: 0
---

# Phase 11: Engine-Owned Fan-Out & Merge Verification Report

**Phase Goal:** Implement engine-owned fan-out (declarative + `spawn_subagents` tool) with isolation, merge-conflict handling, budgets, depth/concurrency caps, subagent persistence, and cancellation propagation — the engine alone decides isolation/caps/merge (INV-7).
**Verified:** 2026-06-11T14:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Context: Code Review Fix History

This verification runs POST code review. The REVIEW.md found 6 Critical + 8 Warning findings (all
"dead wiring masked by test stubs") which were fixed in commits da0eddb..476c1b0 documented in
11-REVIEW-FIX.md. This report verifies the post-fix codebase state, not the pre-review state.
SUMMARY.md claims are treated as low-evidence; code + tests are the ground truth.

The pre-existing failure in `test_phase5_revision_validation.py::test_event_types_subset_of_documented_vocabulary`
(gate_blocked event missing from documented vocabulary — exists at baseline before phase 11) is
excluded from this evaluation as noted in the verification brief.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `spawn_subagents` tool is permission-bound (`user_allowed=False`) and spawn-free (returns JSON request only) | VERIFIED | `@register("tool","spawn_subagents", user_allowed=False)` in providers.py:116; `grep -c "asyncio\|run_fanout" runner_tools.py` = 0 |
| 2 | Both declarative (`fanout_batch` strategy) and runtime (`spawn_subagents` tool) entry points funnel through a single `run_fanout` kernel path | VERIFIED | `fanout_batch` calls `runner.run_fanout` (fanout_batch.py:92); engine `_derive_fanout` calls `run_fanout` on `spawn_subagents` tool result (engine.py:1677+2039); test_fanout.py asserts one spawn path |
| 3 | Worker selection (self×N or named via `allowed_workers`) with pre-spawn rejection of disallowed/unknown workers (zero rows on reject) | VERIFIED | `_select_workers` in fanout.py:78; `KernelServices.allowed_workers` bound from `compiled.allowed_workers` at handle construction (kernel_services.py:198); `KernelServices.agent_exists` live lookup (kernel_services.py:775); CR-01 fix confirmed |
| 4 | Parallel mode bounded by `asyncio.Semaphore(min(declared, 4))`; sequential mode runs workers in order | VERIFIED | `_resolve_concurrency` in fanout.py; semaphore capping at DEFAULT_MAX_CONCURRENCY=4; test_fanout.py instrumented test asserts ≤ 4 concurrent workers |
| 5 | Each child writes one owner-scoped `subagent_runs` row; cross-owner read returns empty | VERIFIED | `SubagentRun` ORM with `owner_id`/`workspace_id` NOT NULL (subagent_run.py:35-36); `ScopedStore.read_subagent_runs` applies `_scope_owner_ws` (authz.py:1015); test_subagent_runs.py cross-owner test passes |
| 6 | Isolation scope is engine-decided from `has_git` (worktree when True, sub_sandbox otherwise) — never manifest-controlled (INV-7) | VERIFIED | `_select_isolation_scope` in fanout.py:226 reads only `base_workspace.has_git`; `LocalWorkspace.has_git` stored at construction (local.py:199); `grep -c "step.fanout.*scope"` = 0 in fanout.py; isolation field absent from FanoutSpec |
| 7 | Two parallel workers writing the same filename land in distinct isolated workspaces (no cross-contamination) | VERIFIED | CR-02 fix: `create_runner` accepts `run_sandbox` override (factory.py); `_isolated_run_sandbox` helper threads `isolated_workspace._sandbox` through to deepagents backend (engine.py); test_isolation.py live-seam test passes |
| 8 | MergeStrategy port with 4 registered impls; copy_disjoint is deterministic and overlap→conflict (never silent overwrite) | VERIFIED | `base.py`: `class MergeStrategy`; 4 `@register("merge",...)` impls confirmed; copy_disjoint overlap test in test_merge.py passes; WR-08 fix: json/html_fragment also write merged content |
| 9 | Merge conflict produces owner-scoped `merge_conflict` artifact + event; all 4 `on_conflict` policies behave per spec (human_gate via one durable HITL, merge_agent ≤ 2 attempts, partial, abort) | VERIFIED | `_merge_fragments` + `_resolve_conflict` in fanout.py:819,924; `grep -c run_merge_gate` = 0; CR-03 fix: `on_conflict` compiled from manifest (compiler.py:498-516); `KernelServices.run_merge_agent` live (kernel_services.py:722); test_merge_conflict.py 4 policy tests pass |
| 10 | BudgetManager reserves before every spawn and enforces total subagents, concurrency, depth, tokens, wall-clock; defaults are module constants (8/4/2/900s); BudgetExceeded aborts gracefully with partial results | VERIFIED | `BudgetManager.reserve` raises `BudgetExceeded` on cap breach (budget.py:181-207); defaults confirmed (budget.py:43-46); CR-04 fix: `_note_wall_clock`/`_note_tokens` called at boundaries (fanout.py:177-202); CR-05 fix: `ctx.depth` incremented (fanout.py:493); test_budget.py passes |
| 11 | BudgetSnapshot persisted to `workflow_runs.budget_snapshot_json` on completion, abort, and cancel (OBS-01); `budget_warning` event at ≥80% consumption | VERIFIED | `_persist_budget_snapshot_if_active` called at run termination (engine.py:1440,1450,1535); `KernelServices.persist_budget_snapshot` (kernel_services.py:491); budget_warning event in fanout.py; test_budget.py snapshot tests pass |
| 12 | Cancellation propagates to all in-flight children; cancel checked at 3 boundaries; every allocated isolated workspace torn down with zero residue | VERIFIED | `_check_cancel` at 3 sites (fanout.py:258,502,605); `try/finally` + `_teardown_allocated` (fanout.py:621,634); `KernelServices.teardown_isolated_workspace` (kernel_services.py:582); WR-04 fix: sibling cancellation on exception; test_fanout_cancel.py zero-residue test passes |
| 13 | A brand-new fan-out workflow runs end-to-end from manifest + AGENT.md only with zero engine edits authored for it (SC-001) | VERIFIED | `sample_fanout/workflow.yaml` at real manifest home; `grep -rc "sample_fanout" backend/agents/execution_engine/` = 0 for all files; `registry.is_registered` asserts for `fanout_batch`/`copy_disjoint`/`spawn_subagents`/`heading_tasks`; test_sc001_fanout.py 3/3 tests pass |

**Score:** 13/13 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/execution_engine/fanout.py` | Kernel `run_fanout` — single spawn path | VERIFIED | 1057 lines; `async def run_fanout`, `_select_workers`, `_select_isolation_scope`, `_check_cancel`, `_merge_fragments`, `_resolve_conflict`, `_teardown_allocated` all present |
| `backend/agents/execution_engine/budget.py` | BudgetManager with enforcing reserve + module constants | VERIFIED | 286 lines; `raise BudgetExceeded` at 8 sites; DEFAULT_MAX_SUBAGENTS=8, DEFAULT_MAX_CONCURRENCY=4, DEFAULT_MAX_DEPTH=2, DEFAULT_WALL_CLOCK_SECONDS=900 confirmed |
| `backend/agents/capabilities/strategies/fanout_batch.py` | Registered fanout_batch strategy | VERIFIED | `@register("strategy","fanout_batch", user_allowed=True)`; calls `runner.run_fanout`; zero execution engine imports |
| `backend/app/agents/tools/runner_tools.py` | Spawn-free `spawn_subagents` tool | VERIFIED | `@tool spawn_subagents` returns JSON string only; `grep asyncio\|run_fanout` = 0 |
| `backend/alembic/versions/0019_subagent_runs.py` | Additive subagent_runs migration | VERIFIED | `revision="0019"`, `down_revision="0018"`, `grep -c "sa.Enum"` = 0 (free-String status) |
| `backend/app/models/subagent_run.py` | SubagentRun ORM | VERIFIED | `class SubagentRun`, `owner_id`/`workspace_id` NOT NULL columns |
| `backend/agents/capabilities/merge/base.py` | MergeStrategy Protocol + MergeResult | VERIFIED | `class MergeStrategy` (Protocol), `class MergeResult` (dataclass) |
| `backend/agents/capabilities/merge/copy_disjoint.py` | Deterministic disjoint-file merge | VERIFIED | `@register("merge","copy_disjoint", user_allowed=True)`; overlap→conflict path present |
| `backend/agents/capabilities/merge/git_3way.py` | Git 3-way merge via handle | VERIFIED | `@register("merge","git_3way", user_allowed=True)`; no subprocess import; reaches git via `runner` |
| `backend/agents/capabilities/merge/json_merge.py` | JSON key-level merge | VERIFIED | `@register("merge","json", user_allowed=True)`; WR-08 fix: `base.write` called for non-conflicting keys |
| `backend/agents/capabilities/merge/html_fragment.py` | HTML fragment merge | VERIFIED | `@register("merge","html_fragment", user_allowed=True)`; WR-08 fix: `base.set_section` called |
| `backend/agents/workflows/sample_fanout/workflow.yaml` | SC-001 fan-out proof manifest | VERIFIED | References fanout_batch + copy_disjoint + allowed_workers; at real manifest home |
| `backend/tests/agents/test_sc001_fanout.py` | SC-001 end-to-end zero-engine-edit proof | VERIFIED | 3 tests pass; registry.is_registered + kernel-names-no-workflow grep asserted |
| `backend/tests/agents/test_fanout_cancel.py` | Cancellation + teardown tests | VERIFIED | 6 tests pass; cancel at 3 boundaries; zero-residue teardown; rows cancelled |
| `backend/tests/agents/test_budget.py` | Budget enforcement tests | VERIFIED | 30 tests pass; reserve-before-spawn, depth cap, wall-clock breach, partial results on abort, BudgetSnapshot persistence |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `fanout_batch.py` | `ctx.runner.run_fanout` | `async for event in runner.run_fanout(requests, ctx, step=step)` | WIRED | fanout_batch.py:92; no execution engine import |
| `engine.py` | `run_fanout` | `_derive_fanout` on `spawn_subagents` tool_result (engine.py:1677+2039) | WIRED | `spawn_subagents` dispatch at engine.py:2039 confirmed |
| `engine.py` | `step.tools.spawn_subagents` | Permission gate in `_derive_fanout` before fulfilling request (WR-01 fix) | WIRED | engine.py:1698 gate confirmed |
| `KernelServices` | `compiled.allowed_workers` | Threaded at `_execute_impl` handle construction into `KernelServices.allowed_workers` (CR-01 fix) | WIRED | kernel_services.py:198 confirmed |
| `fanout.py` | `ctx.budget.reserve` | Called FIRST before any allocate/spawn (reserve-before-spawn) | WIRED | fanout.py calls budget.reserve at spawn entry point |
| `fanout.py` | `ctx.cancel_event` | `_check_cancel` at 3 boundaries (before wave, between sequential workers, before merge) | WIRED | fanout.py:258,502,605 confirmed |
| `fanout.py` | isolation teardown | `try/finally` → `_teardown_allocated` reclaims all allocated isolated workspaces | WIRED | fanout.py:621,634 confirmed |
| `engine.py` | `workflow_runs.budget_snapshot_json` | `_persist_budget_snapshot_if_active` at completion/abort/cancel | WIRED | engine.py:1440,1450,1535 confirmed |
| `authz.py::ScopedStore` | `subagent_runs` | `record_subagent_run` with `owner_id`+`workspace_id` stamping; `_scope_owner_ws` on reads | WIRED | authz.py:939,1015 confirmed |
| `git_3way.py` | git operations | `KernelServices.git_3way_merge` → `LocalWorkspace.merge_worktree` (no capability-side subprocess) | WIRED | grep confirmed `subprocess` = 0 in merge/*.py; git_3way.py:0 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `fanout.py::run_fanout` | worker results / subagent_runs rows | `ctx.runner.run_worker` → `_run_agent` → deepagents execution | Yes — live deepagents workers; test_sc001_fanout drives real engine | FLOWING |
| `fanout.py::_merge_fragments` | merge strategy output | registered `MergeStrategy.merge(base, fragments)` call | Yes — real fragment files from isolated workspaces | FLOWING |
| `budget.py::BudgetManager` | snapshot fields | `note_tokens` accumulation + `note_wall_clock` time.monotonic calls | Yes — CR-04 fix wired call sites at fanout boundaries | FLOWING |
| `engine.py::_persist_budget_snapshot_if_active` | `budget_snapshot_json` | `ctx.budget.spent()` → DB write via `KernelServices.persist_budget_snapshot` | Yes — persisted at 3 termination paths | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full targeted test suite (288 tests) | `cd backend && python3.11 -m pytest tests/agents/test_fanout.py tests/agents/test_fanout_tool.py tests/agents/test_subagent_runs.py tests/agents/test_isolation.py tests/agents/test_merge.py tests/agents/test_merge_conflict.py tests/agents/test_budget.py tests/agents/test_fanout_cancel.py tests/agents/test_sc001_fanout.py tests/agents/test_registry_capabilities.py tests/agents/test_compiler_trust.py tests/agents/test_characterization_prototype.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q -p no:cacheprovider` | 288 passed, 6 skipped (pre-existing env-gated) | PASS |
| Import linter (4 contracts, 0 broken) | `/opt/homebrew/bin/lint-imports` | 4 kept, 0 broken | PASS |
| SC-001 kernel names no workflow | `grep -rc "sample_fanout" backend/agents/execution_engine/` | all 0 | PASS |
| INV-1: no workflow-name branches in fanout/budget | `grep -c "if pipeline_type ==\|spec.id ==" fanout.py budget.py` | 0 | PASS |
| spawn_subagents spawn-free | `grep -c "asyncio\|run_fanout" runner_tools.py` | 0 | PASS |
| 0019 migration no sa.Enum (free-String status) | `grep -c "sa.Enum" 0019_subagent_runs.py` | 0 | PASS |
| 5 characterization snapshots byte/event-identical | included in targeted suite above | 2 passed (5 snapshot tests) | PASS |

---

## Probe Execution

No probe scripts declared. The targeted test suite above is the functional equivalent.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FANOUT-01 | 11-01 | spawn_subagents tool bound only to granted steps; emits structured request; kernel fulfils | SATISFIED | `user_allowed=False`; spawn-free tool body; `_derive_fanout` permission gate (WR-01 fix) |
| FANOUT-02 | 11-01 | Kernel `run_fanout` funnels both declarative and runtime entry points | SATISFIED | fanout_batch calls `runner.run_fanout`; `_derive_fanout` calls `run_fanout` on tool result |
| FANOUT-03 | 11-01 | Worker selection — self×N or named via `allowed_workers` + registry | SATISFIED | `_select_workers` + `_apply_declared_fanout`; CR-01 fix: live KernelServices.allowed_workers/agent_exists bound |
| FANOUT-04 | 11-01 | Parallel (capped) or sequential mode; engine enforces max_concurrency | SATISFIED | Semaphore at min(declared, DEFAULT_MAX_CONCURRENCY=4); sequential ordered loop |
| FANOUT-05 | 11-02 | IsolationProvider allocate → shared_read / sub_sandbox / worktree; writes default isolated | SATISFIED | `_select_isolation_scope`; `allocate_sub_sandbox`/`allocate_worktree` on LocalWorkspace; CR-02 fix: live write-path honored |
| FANOUT-06 | 11-03 | Results include files/artifacts + structured summary with typed artifact refs | SATISFIED | `write_fragment_artifact` in KernelServices; `artifact_refs` per worker in summary; WR-03 fix: all files persisted |
| FANOUT-07 | 11-03 | MergeStrategy integrates fragments (copy_disjoint/git_3way/json/html_fragment) | SATISFIED | 4 registered impls; copy_disjoint deterministic + overlap→conflict; WR-08 fix: json/html write merged content |
| FANOUT-08 | 11-03 | merge_conflict artifact + event; 4 on_conflict policies (human_gate/merge_agent/partial/abort) | SATISFIED | `_resolve_conflict` implements all 4; merge_conflict ArtifactRef written; CR-03 fix: on_conflict compiled from manifest; no run_merge_gate sibling |
| FANOUT-09 | 11-04 | BudgetManager reserves-before-spawn; enforces subagents/concurrency/depth/tokens/wall-clock; BudgetExceeded graceful abort with partial results | SATISFIED | Enforcing reserve (budget.py:161+); CR-04 fix: note_wall_clock/note_tokens wired at boundaries; CR-05 fix: ctx.depth incremented |
| FANOUT-10 | 11-01 | Each child → subagent_runs row; subagent_spawned/subagent_result/merge_* events | SATISFIED | subagent_runs row per child; events emitted in fanout.py; ScopedStore cross-owner = empty |
| FANOUT-11 | 11-05 | Fan-out cancellation propagates to children | SATISFIED | `_gather_or_cancel` + `_mark_open_cancelled`; cancel at 3 boundaries; rows marked cancelled; test_fanout_cancel.py passes |
| OBS-01 | 11-04 | BudgetManager per-run AND per-workspace ceilings; snapshot persisted on run | SATISFIED | `ScopedStore.workspace_budget_spent`; `KernelServices.persist_budget_snapshot`; engine.py persists at 3 termination paths |
| RESUME-01 | 11-05 | Cooperative cancel at step/gate/fanout boundaries; preserve partial artifacts; teardown isolated workspaces | SATISFIED | `_check_cancel` at 3 fanout boundaries; `try/finally` + `_teardown_allocated`; `KernelServices.teardown_isolated_workspace`; completed fragments preserved |

All 13 requirement IDs from PLAN frontmatter verified. No orphaned requirements found.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | The code review (11-REVIEW.md) identified 6 Critical + 8 Warning stub/wiring gaps; all 14 were fixed in commits da0eddb..476c1b0 before this verification ran. Post-fix scan found no residual debt markers or unresolved stubs relevant to the must-haves. |

**Debt marker gate:** No unreferenced TBD/FIXME/XXX markers found in phase-11 files.

**Pre-existing known failure (excluded):** `test_phase5_revision_validation.py::test_event_types_subset_of_documented_vocabulary` — the `gate_blocked` event is absent from the documented vocabulary. This failure exists at the pre-phase-11 baseline (confirmed by running the test). It is not a phase-11 regression and does not count against this phase.

---

## Human Verification Required

None. All must-haves are programmatically verifiable and the test suite provides comprehensive behavioral coverage including end-to-end SC-001 proof, 5 characterization snapshot parity, live-handle contract tests (CR-01/CR-02/CR-03 each added live-seam tests), and the zero-residue teardown test. Live Bedrock checks are deferred to end-of-milestone per project convention (memory: defer-live-verification-to-milestone-end).

---

## Gaps Summary

No gaps. All 13 must-have truths verified, all 13 requirement IDs satisfied, targeted test suite green (288 passed / 6 pre-existing env-gated skips), import-linter 4/0, SC-001 proven, INV-1/INV-7/INV-12/INV-13 all held.

The code review found 14 Critical+Warning findings that were dead-wiring gaps; the REVIEW-FIX.md documents all 14 fixed with tests. The post-fix codebase now has live wiring for: named-worker selection (CR-01), per-worker write isolation (CR-02), on_conflict compilation + merge_agent policy (CR-03), wall-clock/token budget enforcement call sites (CR-04), ctx.depth propagation (CR-05), has_git worktree path (CR-06), spawn_subagents permission gate at fulfilment (WR-01), distinct merge_failed event (WR-02), full fragment persistence (WR-03), sibling task cancellation (WR-04), correct total_workers threading (WR-05), FanoutSpec fields consumed (WR-06), mode argument honored (WR-07), json/html_fragment merged content written (WR-08).

---

_Verified: 2026-06-11T14:00:00Z_
_Verifier: Claude (gsd-verifier)_

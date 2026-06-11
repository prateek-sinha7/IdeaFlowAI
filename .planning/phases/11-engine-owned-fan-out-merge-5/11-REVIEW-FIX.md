---
phase: 11-engine-owned-fan-out-merge-5
fixed_at: 2026-06-11T13:30:00Z
review_path: .planning/phases/11-engine-owned-fan-out-merge-5/11-REVIEW.md
iteration: 1
findings_in_scope: 14
fixed: 14
skipped: 0
status: all_fixed
---

# Phase 11: Code Review Fix Report

**Fixed at:** 2026-06-11T13:30:00Z
**Source review:** .planning/phases/11-engine-owned-fan-out-merge-5/11-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 14 (6 Critical + 8 Warning; 5 Info excluded by fix_scope=critical_warning)
- Fixed: 14
- Skipped: 0

All fixes follow the review's dominant pattern correction: wire the LIVE path
(bind real attributes / thread real values) instead of letting test fakes
fabricate them, and add tests that exercise the live binding. Verified with the
full targeted suite (296 passed, 6 pre-existing env-gated skips), the 5
characterization snapshots (byte/event parity intact), test_banned_patterns
(INV-13), and `lint-imports` (4 contracts kept / 0 broken).

## Fixed Issues

### CR-01: Named-worker fan-out always rejected — `allowed_workers`/`agent_exists` never bound live

**Files modified:** `backend/agents/execution_engine/kernel_services.py`, `backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_fanout.py`
**Commit:** da0eddb
**Applied fix:** `KernelServices.__init__` now takes `allowed_workers` (threaded from `compiled.allowed_workers` at handle construction in `_execute_impl`) and exposes `agent_exists` (ordered-agents lookup with an agent-loader fallback, fail-closed). Added live-handle contract tests constructing the real `KernelServices` via `__init__` and driving a named-worker `run_fanout` through it (resolve + pre-spawn rejection both proven).

### CR-02: Per-worker write isolation was cosmetic — `isolated_workspace` had zero readers

**Files modified:** `backend/agents/factory.py`, `backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_isolation.py`
**Commit:** 44c1220
**Applied fix:** `create_runner` accepts a `run_sandbox` override that roots the deepagents FilesystemBackend at the isolated dir; `_run_agent` extracts the worker step view's `isolated_workspace._sandbox` via the new `ExecutionEngine._isolated_run_sandbox` helper and threads it through. Non-worker invocations pass `None` (shared-sandbox parity). Tests: helper extraction unit test + a live-seam test where two workers writing the same relpath through the real deepagents disk backend land in distinct roots with the shared base untouched.

### CR-03: `on_conflict` silently dropped; `merge_agent` policy unreachable end-to-end

**Files modified:** `backend/agents/workflows/compiler.py`, `backend/agents/execution_engine/kernel_services.py`, `backend/tests/agents/test_subagent_runs.py`, `backend/tests/agents/test_merge_conflict.py`
**Commit:** 00eefa1
**Applied fix:** `_compile_step` carries `on_conflict` onto `Step` validated against the §13 four-policy set (unknown policy = fail-loud `CompilerError`); `merge_agent` added to `_ALLOWED_FANOUT_KEYS` and materialized onto `FanoutSpec`; implemented `KernelServices.run_merge_agent` — one bounded `run_agent` invocation of the designated worker per attempt with the serialized conflict payload as its CURRENT TASK block, returning `False` on any failure (human_gate fallback preserved). Tests cover compilation of both fields, the human_gate default, fail-loud rejection, and the live handle (designated worker runs / unknown worker degrades False).

### CR-04: Wall-clock and token budget enforcement was dead code

**Files modified:** `backend/agents/execution_engine/fanout.py`, `backend/tests/agents/test_budget.py`
**Commit:** cb8d3ce
**Applied fix:** Added `_note_wall_clock`/`_note_tokens` boundary helpers; `run_fanout` checks the wall clock before each sequential spawn, before each parallel worker enters `_run_one` (inside the semaphore), and before the merge; `_run_one` accumulates each worker's `agent_complete.total_tokens` into the budget (and onto its `subagent_runs` row) at the collect boundary; the ≥80% warn loop refreshes via `budget.spent()` first so the wall-clock warning can fire. Tests prove a mid-flight wall-clock breach stops the next sequential spawn and a token-cap breach aborts at the collect boundary.

### CR-05: `ctx.depth` never incremented — `max_depth` and nested thread-id namespacing unenforceable

**Files modified:** `backend/agents/execution_engine/fanout.py`, `backend/tests/agents/test_fanout.py`
**Commit:** d17109e
**Applied fix:** `run_fanout` bumps `ctx.depth` to `depth + 1` for the wave's execution scope (restored in the `finally`), so a worker-triggered nested fan-out (which reuses the shared ctx) reserves at the correct depth, namespaces child thread ids with the `d{depth}` segment, and records the nested depth on its `subagent_runs` rows. Test drives a real nested `run_fanout` through the same ctx and asserts row depths `[0, 1]`, the `:d1:` thread segment, and the post-wave restore.

### CR-06: Worktree scope and `git_3way` unreachable — `has_git` discarded, workers never committed

**Files modified:** `backend/app/agents/runtime/local.py`, `backend/agents/execution_engine/fanout.py`, `backend/tests/agents/test_isolation.py`
**Commit:** fe4d569
**Applied fix:** `LocalWorkspace` stores `has_git` (set by `create_workspace(has_git=...)`, flipped True by `clone_repo`, and True on every `allocate_worktree` child); added `LocalWorkspace.commit_all` (git add -A + commit via the single git owner, tolerating nothing-to-commit); `run_fanout._run_one` commits a completed worktree worker's edits on its per-worker branch before fragment persistence/merge, so `merge_worktree` actually integrates them instead of "already up to date" + teardown destroying the output. Live tests: scope selection off the real workspace (created / cloned), and a commit-then-merge test proving worker edits land in the base.

### WR-01: Fan-out fulfilment point enforced no `spawn_subagents` permission

**Files modified:** `backend/agents/execution_engine/engine.py`, `backend/agents/workflows/compiler.py`, `backend/tests/agents/test_compiler_trust.py`, `backend/tests/agents/test_fanout.py`
**Commit:** ac2fbfc
**Applied fix:** `_derive_fanout` now ignores (and logs) a `spawn_subagents` tool result on a step without an effective `tools.spawn_subagents` grant; the compiler's untrusted privileged-grant guard rejects `spawn_subagents: true` by name (fail-loud symmetry with exec/network/secrets). Tests cover the engine gate both ways, the user-trust rejection, and file-trust grant survival.

### WR-02: Crashed merge strategy reported as a clean `merge_completed`

**Files modified:** `backend/agents/execution_engine/fanout.py`, `backend/tests/agents/test_merge_conflict.py`
**Commit:** 3e15acd
**Applied fix:** The strategy-crash handler emits a distinct `merge_failed` event carrying `error: str(exc)` (applied=[], conflicts=0) instead of a clean `merge_completed`. Test asserts the failure is first-class and no `merge_completed` is emitted on a crash.

### WR-03: Fragment persistence kept only the alphabetically-first file; worktree fragments walked the whole checkout

**Files modified:** `backend/app/agents/runtime/local.py`, `backend/agents/execution_engine/fanout.py`, `backend/tests/agents/test_isolation.py`, `backend/tests/agents/test_merge_conflict.py`
**Commit:** dbaf9ed
**Applied fix:** `_run_one` persists one typed ref per file (`artifact_refs` on the summary; `artifact_ref` keeps the primary for back-compat); added `LocalWorkspace.changed_since(base_commit)` (diff vs spawn point + untracked) and `_fragment_files` restricts worktree fragments to it, degrading to NO fragment when scoping is unavailable (never a whole-repo "fragment"). Also fixed a latent exclusion bug found while testing: the `.git`/`.worktrees` filter now checks RELATIVE path parts, since a worktree workspace root itself lives under `.worktrees/` and the absolute-path check wrongly excluded every worktree fragment file.

### WR-04: Non-worker exception orphaned sibling tasks and tore workspaces down under them

**Files modified:** `backend/agents/execution_engine/fanout.py`, `backend/tests/agents/test_fanout_cancel.py`
**Commit:** 2e059a9
**Applied fix:** The parallel gather path mirrors the cancel path on any exception: cancel + await all outstanding tasks (each in-flight worker's own handler flips its row `cancelled`), mark still-open rows cancelled, then re-raise. Test crashes `allocate` for one worker while siblings block in `run_worker` and asserts every recorded row reaches terminal `cancelled` with zero residue.

### WR-05: `total_tasks=worker_index+1` — wrong "task i of N" for all but the last worker

**Files modified:** `backend/agents/execution_engine/kernel_services.py`, `backend/agents/execution_engine/fanout.py`, `backend/tests/agents/test_fanout.py`, `backend/tests/agents/test_fanout_cancel.py`, `backend/tests/agents/test_isolation.py`, `backend/tests/agents/test_merge_conflict.py`
**Commit:** 9c7ca69
**Applied fix:** `run_fanout` threads `total_workers=len(selected)` into `run_worker`; `run_worker` passes it as `total_tasks` (falling back to the old shape when unthreaded) and the fabricated worker step view runs `strategy="single_shot"` instead of inheriting `fanout_batch`. Test fakes updated to the new call shape; tests assert "task 3 of 5" and the single_shot view.

### WR-06: `FanoutSpec.agent`/`count`/`workers` compiled but consumed by nothing

**Files modified:** `backend/agents/execution_engine/fanout.py`, `backend/agents/capabilities/strategies/fanout_batch.py`, `backend/tests/agents/test_fanout.py`
**Commit:** 12ccd6d
**Applied fix:** Chose the consume option (the declared heterogeneous/self×N surface is the FANOUT-03 intent): `run_fanout._apply_declared_fanout` maps `workers[i]` onto default-agent request i (still validated against `allowed_workers` + the registry), defaults an agent-less request to `agent`, and clamps the width to `count`; `fanout_batch` synthesizes self×count requests when the task source parses nothing. Tests cover mapping, allow-list validation of mapped workers, width clamping, and count synthesis. `sample_fanout` (count=3, 3 tasks) is behaviorally unchanged.

### WR-07: The tool's `mode` argument parsed and then ignored

**Files modified:** `backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_fanout.py`
**Commit:** 0dd68e1
**Applied fix:** `_derive_fanout` reads `payload["mode"]` and threads a valid value onto a COPIED step view (shared compiled step never mutated) so `run_fanout` honors a sequential request; the engine concurrency clamp still applies. Test asserts the sequential request reaches `run_fanout` and the declared FanoutSpec is untouched.

### WR-08: `json`/`html_fragment` merges never produced the merged document

**Files modified:** `backend/agents/capabilities/merge/json_merge.py`, `backend/agents/capabilities/merge/html_fragment.py`, `backend/tests/agents/test_merge.py`
**Commit:** 476c1b0
**Applied fix:** Mirroring `copy_disjoint`, `JsonMerge` invokes `base.write(key, value)` and `HtmlFragmentMerge` prefers `base.set_section(sid, html)` (generic `write` fallback) for each non-conflicting claim; conflicting entries are still never written. Writer-less dict/str bases (offline tests) keep asserting the typed `MergeResult` directly (parity). Tests assert writer-backed bases receive exactly the non-conflicting merged content.

## Skipped Issues

None — all 14 in-scope findings were fixed. (IN-01..IN-05 are Info-tier and outside `fix_scope=critical_warning`; note IN-05's handle-contract concern is substantially addressed by the live-handle tests added under CR-01/CR-03/WR-05.)

## Verification

- Targeted Phase-11 suite + characterization + banned patterns + migration ledger: **296 passed, 6 skipped** (pre-existing env-gated skips), 0 failures.
- `lint-imports`: **4 contracts kept, 0 broken** (kernel/capability/runtime import direction intact).
- INV-13: single `create_deep_agent` call site unchanged (banned-pattern gate green).
- INV-7/INV-1: isolation scope still engine-derived from `has_git` only; no workflow-name branches added (SC-001 grep test green).
- Security defaults: `spawn_subagents` remains `user_allowed=False` and is now additionally rejected fail-loud for user/db grants.

---

_Fixed: 2026-06-11T13:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

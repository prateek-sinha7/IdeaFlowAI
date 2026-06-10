---
phase: 11-engine-owned-fan-out-merge-5
plan: 02
subsystem: infra
tags: [fanout, isolation, worktree, sub_sandbox, git, runtime-workspace, kernel]

# Dependency graph
requires:
  - phase: 11-engine-owned-fan-out-merge-5
    provides: "11-01 run_fanout single spawn path (isolation fixed at shared_read) + KernelServices run_worker + record/update_subagent_run + subagent_runs.isolation column"
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    provides: "IsolationProvider.allocate(scope) port + LocalSandboxRuntime/LocalWorkspace single git-subprocess owner (clone/branch/diff) + RunSandbox path_for traversal-safety"
provides:
  - "LocalWorkspace.allocate_sub_sandbox / allocate_worktree / spawn_point_commit / remove_worktree — the two Phase-11 isolation scopes on the single git-subprocess owner"
  - "_ChildSandbox facade — a RunSandbox-shaped isolated child/worktree root under the run root (traversal-proof, cleanup never touches parent)"
  - "fanout._select_isolation_scope(base_workspace) — engine-decided scope (has_git->worktree else sub_sandbox), INV-7 (never manifest-controlled)"
  - "run_fanout per-worker isolated-workspace binding + recorded scope on subagent_runs.isolation + happy-path teardown after collect"
  - "KernelServices.allocate_isolated_workspace / reclaim_isolated_workspace — the capability/engine-facing seam to the LocalWorkspace git owner"
affects: [11-03-merge, 11-05-cancel-teardown]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Engine-decided isolation scope (INV-7): scope derived SOLELY from base_workspace.has_git, never read from step.fanout — a user manifest cannot downgrade isolation (T-11-02-03)"
    - "Single git-subprocess owner extended (Phase-9 D-10): worktree add/remove + branch delete live on LocalWorkspace, reached by the engine ONLY through the ctx.runner handle"
    - "Additive-kwarg parity: run_worker's workspace kwarg is threaded ONLY when a workspace was allocated, so the 11-01 shared-workspace call shape stays byte-identical"
    - "Runtime-layer isolation (CONTEXT D-04 discretion): the scopes are LocalWorkspace methods bound via the host seam, NOT a new @register capability kind — _KNOWN stays 55"

key-files:
  created:
    - backend/tests/agents/test_isolation.py
  modified:
    - backend/app/agents/runtime/local.py
    - backend/agents/runtime/base.py
    - backend/agents/execution_engine/fanout.py
    - backend/agents/execution_engine/kernel_services.py

key-decisions:
  - "Isolation impl is RUNTIME-LAYER code on LocalWorkspace bound via the §15 host seam (CONTEXT D-04 discretion), NOT a @register('isolation', ...) capability kind — so the registry lockstep count stays 55 and no test_registry_capabilities bump was needed"
  - "_ChildSandbox is a RunSandbox-shaped facade (root/ensure/path_for/user_seg/run_seg/cleanup) rooted at the isolated child/worktree dir; its cleanup rmtrees ONLY the child dir so a worker teardown can never delete sibling/parent work"
  - "The worktree dir lives under {run}/.worktrees/{step}/{i}/ (outside the tracked working tree) so git worktree add's target-must-not-exist + not-picked-up-as-content constraints both hold"
  - "run_fanout passes workspace= to run_worker ONLY when a workspace was allocated (worker_kwargs spread) so the existing _FakeRunner.run_worker signature + the 11-01 shared path stay byte-identical (parity over a forced new positional)"

patterns-established:
  - "Engine isolation-scope select: has_git base -> worktree, sandbox base -> sub_sandbox, no-handle -> shared_read fallback (offline/non-exec parity)"
  - "Happy-path teardown: every allocated isolated workspace is reclaimed after collect via reclaim_isolated_workspace (worktree remove+branch delete / child rmtree); cancel-path teardown of the SAME list is 11-05"

requirements-completed: [FANOUT-05]

# Metrics
duration: ~18min
completed: 2026-06-11
---

# Phase 11 Plan 02: Engine-Owned Isolation Scopes Summary

**The two Phase-11 fan-out isolation scopes (`sub_sandbox` child-dir + git `worktree` per-worker branch) on the single git-subprocess owner, with the engine (INV-7) selecting the scope from `base_workspace.has_git` and binding each worker to its own isolated workspace — worker writes isolated before the 11-03 merge.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-11
- **Completed:** 2026-06-11
- **Tasks:** 2 (both TDD)
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- `LocalWorkspace` grew the two isolation scopes as the SINGLE git-subprocess owner (Phase-9 D-10): `allocate_sub_sandbox` (isolated child dir `{run}/subagents/{step}/{i}/` via the traversal-proof `path_for`), `allocate_worktree` (`git worktree add -b fanout/{step}/{i}` off the working branch), `spawn_point_commit` (the 11-03 3-way merge-base capture), and `remove_worktree` (happy-path worktree remove + branch delete, zero `git worktree list` orphans).
- The engine — NOT the manifest (INV-7) — selects the scope: `_select_isolation_scope(base_workspace)` returns `worktree` when `has_git=True` else `sub_sandbox`. `run_fanout` allocates a per-worker isolated workspace, binds it into `run_worker` (writes isolated, reads shared-read of parent refs), and records the chosen scope on each child's `subagent_runs.isolation`.
- Two parallel workers writing the SAME filename land in DISTINCT isolated workspaces with no cross-contamination (T-11-02-02), and each isolated workspace carries the parent's `owner_id`/`workspace_id` (T-11-02-05) — both asserted in `test_isolation.py`.
- Happy-path teardown reclaims every allocated workspace after collect (worktree remove+branch delete / child rmtree); the full cancel-path teardown of the same allocation list is left as the documented 11-05 seam.

## Task Commits

Each task was committed atomically:

1. **Task 1: LocalWorkspace sub_sandbox + worktree allocation (single git owner)** — `49aa7b9` (feat)
2. **Task 2: Engine isolation-scope selection + per-worker workspace binding in run_fanout** — `395de75` (feat)

_Note: both tasks carried `tdd="true"`; tests were authored alongside the implementation (RED→GREEN within the same task commit, the project's established offline-suite cadence)._

## Files Created/Modified
- `backend/app/agents/runtime/local.py` — `allocate_sub_sandbox` / `allocate_worktree` / `spawn_point_commit` / `remove_worktree` on `LocalWorkspace` (the single git owner); `_ChildSandbox` isolated-root facade; `_seg` path-segment sanitiser; `_worktree_branch`/`_worktree_path` stamps.
- `backend/agents/runtime/base.py` — grew the `IsolationProvider` docstring to state `sub_sandbox`/`worktree` are now LIVE (additive doc; port signature unchanged).
- `backend/agents/execution_engine/fanout.py` — `_select_isolation_scope`; per-worker allocate + bind in `run_fanout`; scope recorded on `subagent_runs.isolation`; `_teardown_allocated` happy-path reclaim.
- `backend/agents/execution_engine/kernel_services.py` — `allocate_isolated_workspace` / `reclaim_isolated_workspace` handle methods (delegate to the Task-1 `LocalWorkspace` allocators); `run_worker` grew the additive `workspace` kwarg.
- `backend/tests/agents/test_isolation.py` — sub_sandbox/worktree alloc + spawn-point + no-cross-contamination + git-not-capability-side + engine scope-select (worktree/sub_sandbox/shared_read fallback) + INV-7 no-manifest-scope grep.

## Decisions Made
- Isolation is RUNTIME-LAYER code on `LocalWorkspace` bound via the host seam (CONTEXT D-04 discretion), NOT a new `@register('isolation', ...)` capability kind — so `_KNOWN` stays 55 and `test_registry_capabilities.py` needed no lockstep bump.
- `_ChildSandbox`'s `cleanup` rmtrees ONLY the isolated child/worktree dir (never the parent), so a worker teardown can never delete sibling/parent work.
- The worktree dir lives under `{run}/.worktrees/{step}/{i}/` (outside the tracked working tree) to satisfy `git worktree add`'s target-must-not-exist constraint and keep it out of repo content.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Narrowed the "git not capability-side" guard to actual spawns**
- **Found during:** Task 1 (`test_git_ops_are_not_capability_side`)
- **Issue:** The plan's acceptance grep `grep -c "subprocess\|git worktree" agents/capabilities/` was authored expecting 0, but the 10-04 code validators (landed AFTER this plan was written) legitimately `import subprocess` and reference `subprocess.TimeoutExpired` (an exception TYPE) while reaching exec ONLY through the runner/workspace handle — they spawn nothing. A literal `subprocess`-token grep false-fired on those three files.
- **Fix:** Scoped the guard to actual process SPAWNS (`subprocess.run(` / `subprocess.Popen(` / `subprocess.call(` / `subprocess.check_output(`) plus the `git worktree` token — the genuine FANOUT-05 boundary (no git-worktree shelling, no spawn capability-side). The 10-04 exception-type reference is correctly NOT a leak.
- **Files modified:** `backend/tests/agents/test_isolation.py`
- **Verification:** Guard passes; the three 10-04 validators are not flagged; a real spawn or `git worktree` capability-side would still fail it.
- **Committed in:** `49aa7b9` (Task 1 commit)

**2. [Rule 3 - Blocking] Made the run_worker workspace kwarg conditional to preserve parity**
- **Found during:** Task 2 (existing `test_fanout.py` broke)
- **Issue:** Passing `workspace=worker_ws` unconditionally to `run_worker` broke the existing `_FakeRunner.run_worker` signature (no `workspace` param) and would have forced a non-byte-identical call shape on the 11-01 shared path.
- **Fix:** `run_fanout` now spreads `worker_kwargs = {"workspace": worker_ws} if worker_ws is not None else {}` — the kwarg is threaded ONLY when a workspace was actually allocated, so the shared_read/offline path keeps the exact 11-01 call shape.
- **Files modified:** `backend/agents/execution_engine/fanout.py`
- **Verification:** `test_fanout.py` 9/9 + 5 characterization snapshots byte/event-identical.
- **Committed in:** `395de75` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both auto-fixes are correctness/parity requirements — the first fixes a stale acceptance grep against post-plan code, the second preserves the INV-3 byte/event parity guarantee. No scope creep.

## Issues Encountered
- The plan's `grep -c "subprocess..." == 0` acceptance criterion conflicted with the 10-04 code validators' legitimate `subprocess` import. Resolved by scoping the boundary guard to actual spawns + `git worktree` (Deviation 1) — the intent (no git ops capability-side) is preserved and tested.

## Known Stubs
- **Cancel-path teardown (11-05 seam)** — INTENTIONAL forward seam. `run_fanout` records every allocated isolated workspace on the `allocated` list and tears down the HAPPY-PATH workspaces after collect via `_teardown_allocated` / `reclaim_isolated_workspace`. The FULL cancel/finally-path teardown (reclaiming the SAME list on a mid-flight cancel or exception) is explicitly deferred to **11-05** per the plan objective ("Teardown wiring lands fully in 11-05; this plan implements the allocate + the happy-path remove"). Documented in `run_fanout`'s docstring + `_teardown_allocated` — NOT a gap.

## User Setup Required
None — no external service configuration required (zero new packages this phase; T-11-02-SC accept — stdlib subprocess + system git only).

## Next Phase Readiness
- The two isolated scopes are live behind the engine-decided selector; each worker writes isolated (the FANOUT-05 precondition for the 11-03 deterministic merge).
- 11-03 (merge) consumes `spawn_point_commit()` as the 3-way merge-base and the per-worker worktree branches `fanout/{step}/{i}` as the merge inputs; the `MergeStrategy` registry + typed fragment artifacts replace this plan's status-only summary.
- 11-05 (cancel teardown) extends `_teardown_allocated` from the happy path to the cancel/finally path over the `allocated` list `run_fanout` already records.

## Self-Check: PASSED

`backend/tests/agents/test_isolation.py` exists on disk; both task commits (`49aa7b9`, `395de75`) are present in git history. Full plan verification suite green: 124 passed (test_isolation + test_fanout + test_registry_capabilities + 5 characterization snapshots byte/event-identical with SNAPSHOT_UPDATE unset + test_banned_patterns), lint-imports 4 kept / 0 broken; `_KNOWN` unchanged at 55 (runtime-layer impl, no capability registration).

---
*Phase: 11-engine-owned-fan-out-merge-5*
*Completed: 2026-06-11*

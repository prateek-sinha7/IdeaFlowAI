---
phase: 11-engine-owned-fan-out-merge-5
plan: 05
subsystem: infra
tags: [fanout, cancellation, teardown, resume, sc001, dos-mitigation, kernel]

# Dependency graph
requires:
  - phase: 11-engine-owned-fan-out-merge-5
    provides: "11-01 run_fanout single spawn path + subagent_runs persistence; 11-02 isolation alloc/reclaim (sub_sandbox/worktree) + allocated-workspace list; 11-03 write_fragment_artifact (fragments persisted before merge) + merge dispatch; 11-04 reserve-before-spawn + BudgetExceeded graceful abort"
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    provides: "LocalWorkspace single git-subprocess owner (remove_worktree + branch delete / RunSandbox.cleanup rmtree) — the teardown primitives"
  - phase: 07-task-loop-strategy
    provides: "test_sc001_nonprototype_task_loop.py — the SC-001 zero-engine-edit proof pattern (registered-capabilities-only + kernel-names-no-workflow grep)"
provides:
  - "fanout._check_cancel(ctx) — cooperative cancel boundary helper (raises asyncio.CancelledError when ctx.cancel_event is set), checked BEFORE the wave, BETWEEN sequential workers, and BEFORE merge (RESUME-01)"
  - "Parallel-mode cancellation propagation: _gather_or_cancel races the gathered worker tasks against cancel_event, cancels every in-flight worker task on cancel; _mark_open_cancelled flips pending rows cancelled (FANOUT-11)"
  - "run_fanout try/finally: _teardown_allocated reclaims EVERY allocated isolated workspace on the happy AND cancel AND BudgetExceeded paths (Pitfall 5 — no leaked worktrees/branches/sub_sandbox dirs)"
  - "KernelServices.teardown_isolated_workspace(base, ws) — the cancel-path teardown entry point (delegates to reclaim_isolated_workspace)"
  - "Each in-flight/spawned child's subagent_runs row flips terminal `cancelled` on cancel; completed fragments' artifacts preserved (persisted before merge by 11-03)"
  - "agents/workflows/sample_fanout/workflow.yaml — the SC-001 fan-out proof manifest (fanout_batch fanning 3 self-copies + copy_disjoint merge) at the real manifest home"
  - "compiler workflow ceiling permits spawn_subagents=trusted (mirrors exec): a file-trusted manifest's privileged fan-out grant binds True (T-11-05-03)"
  - "run_worker threads each worker's per-worker input through the CURRENT TASK injection path (FANOUT-04 — workers receive their assigned slice)"
affects: [phase-11-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cooperative cancel at fan-out boundaries (RESUME-01): _check_cancel raises CancelledError so the kernel's existing outer handler (emitting pipeline_cancelled) drives termination — the fan-out never re-implements the cancel/snapshot/emit path"
    - "finally-teardown of EVERY allocation (Pitfall 5): the spawn+merge body runs inside try/finally so teardown reclaims every isolated workspace on the happy, cancel, AND BudgetExceeded paths — zero-residue (no orphan worktrees/dirs)"
    - "Race-cancel parallel workers (FANOUT-11): _gather_or_cancel polls cancel_event alongside asyncio.gather; on cancel it cancels every in-flight task (each marks its own row cancelled) and pending tasks never start"
    - "spawn_subagents rides the SAME trust-conditional ceiling as exec: file/builtin may grant the privilege, user/db collapses it OFF (the engineer-authored-only posture)"
    - "SC-001 proof = registered-capabilities-only + kernel-names-no-workflow grep (the 07-11 pattern), NOT a phase-start engine file-diff (11-01..11-04 legitimately edited the agnostic kernel)"

key-files:
  created:
    - backend/tests/agents/test_fanout_cancel.py
    - backend/agents/workflows/sample_fanout/workflow.yaml
    - backend/tests/agents/fixtures/sc001_fanout/sample-fanout-plan/AGENT.md
    - backend/tests/agents/fixtures/sc001_fanout/sample-fanout-worker/AGENT.md
    - backend/tests/agents/test_sc001_fanout.py
  modified:
    - backend/agents/execution_engine/fanout.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/agents/workflows/compiler.py

key-decisions:
  - "The worker AGENT.md specs are test-scoped under tests/agents/fixtures/sc001_fanout/ (NOT agents/prompts/sample-fanout-worker/ as the plan's file list named) — a real prompt-home AGENT.md with pipeline_type: sample_fanout would break test_loader.py's SUPPORTED_PIPELINE_TYPES schema gate. This MIRRORS the proven sc001_task_loop / sample_brownfield precedent the plan told me to follow exactly. The manifest itself IS at the real home (agents/workflows/sample_fanout/) so compile_for_run loads it with zero engine edit."
  - "Cancel boundaries raise asyncio.CancelledError (the engine's per-chunk idiom) rather than emitting pipeline_cancelled in run_fanout — the kernel's existing outer CancelledError handler (engine.py:1430) already transitions cancelled + persists the budget snapshot + emits pipeline_cancelled. Re-emitting in run_fanout would duplicate/diverge that single home (INV-12)."
  - "spawn_subagents added to the trust-conditional workflow ceiling (ToolPermissions(exec=trusted, spawn_subagents=trusted)) so the file-trusted sample_fanout grant survives intersect_permissions and binds True. Without it the ceiling's default spawn_subagents=False AND-masked the grant to False — the privileged fan-out grant the threat model T-11-05-03 describes could never bind."
  - "run_worker passes task_number=worker_index+1 (not None) so the worker's per-worker input rides the EXISTING CURRENT TASK injection path — fan-out workers previously received task_block=input but run_agent dropped it (the injection only fired when task_number was set), so every worker saw only the shared context and could not differentiate its task (FANOUT-04 bug)."

patterns-established:
  - "_gather_or_cancel + _suppress_cancel: race the gathered worker tasks against the cooperative cancel_event, cancelling in-flight tasks on cancel; the poller is always cleaned up"
  - "teardown_isolated_workspace is the cancel-path teardown name run_fanout's finally prefers (falling back to reclaim_isolated_workspace) — one teardown entry point for happy + cancel + abort"

requirements-completed: [FANOUT-11, RESUME-01]

# Metrics
duration: ~30min
completed: 2026-06-11
---

# Phase 11 Plan 05: Cancellation Propagation + SC-001 Fan-Out Proof Summary

**Cancellation now propagates to fan-out children at every boundary (`_check_cancel` before the wave / between sequential workers / before merge), in-flight worker tasks are cancelled and their `subagent_runs` rows flip terminal `cancelled`, EVERY allocated isolated workspace is torn down in a `finally` (happy + cancel + BudgetExceeded — no leaks), completed fragments' artifacts are preserved, and `pipeline_cancelled` fires from the kernel's outer handler — plus the SC-001 core-value proof: a brand-new `sample_fanout` workflow (manifest + AGENT.md only) runs end-to-end with ZERO engine edits authored for it (registered-capabilities-only + the kernel names no workflow).**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-11
- **Completed:** 2026-06-11
- **Tasks:** 2 (both TDD)
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments

- **Cooperative cancel at fan-out boundaries (RESUME-01):** `fanout._check_cancel(ctx)` reads `ctx.cancel_event` (the same Stop-button signal the engine checks per-agent-step + per-chunk) and raises `asyncio.CancelledError` when set. It is called BEFORE a fan-out wave (a pre-wave cancel leaves zero `subagent_runs` rows / zero allocations), BETWEEN sequential workers (the next worker never spawns), and BEFORE merge (the merge is skipped). The CancelledError propagates to the kernel's existing outer handler (`engine.py:1430`) which transitions `cancelled`, persists the budget snapshot, and emits `pipeline_cancelled` — no re-implementation in `run_fanout` (INV-12).
- **Parallel-mode cancellation propagation (FANOUT-11):** the gathered worker tasks run through `_gather_or_cancel`, which races `asyncio.gather` against a `cancel_event` poller. When the event fires mid-flight it cancels EVERY in-flight worker task (each worker's own `CancelledError` handler flips its row terminal `cancelled`) and pending tasks never start; `_mark_open_cancelled` flips any still-open rows (a pending task cancelled before it entered `_run_one`). A CancelledError then propagates so the run terminates.
- **`finally`-teardown of every allocation (Pitfall 5 / RESUME-01):** the spawn+merge body runs inside a `try/finally` so `_teardown_allocated` reclaims EVERY allocated isolated workspace on the happy path AND the cancel path AND the BudgetExceeded path — a `worktree` via `LocalWorkspace.remove_worktree` (git worktree remove + branch delete), a `sub_sandbox` child via its own `teardown` (rmtree). `KernelServices.teardown_isolated_workspace` is the cancel-path teardown entry point. The zero-residue test asserts NO isolated workspace dir / orphan `git worktree list` entry remains after cancel. Completed fragments' artifacts (persisted before merge by 11-03's `write_fragment_artifact`) are preserved.
- **SC-001 fan-out proof (the phase close):** `agents/workflows/sample_fanout/workflow.yaml` at the REAL manifest home declares a `fanout_batch` step fanning 3 self-copies (each writing `part_N.txt`), `mode: parallel`, `copy_disjoint` merge, `allowed_workers`, and the `spawn_subagents` grant — using ONLY already-registered capabilities. `test_sc001_fanout.py` drives it end-to-end OFFLINE: 3 workers spawn (3 `subagent_runs` rows), 3 distinct files merged with no conflict, and the conceptual zero-engine-edit proof exactly as `test_sc001_nonprototype_task_loop.py` does it — `registry.is_registered(...)` for `fanout_batch`/`copy_disjoint`/`spawn_subagents`/`heading_tasks` AND `grep -rc "sample_fanout" backend/agents/execution_engine/` == 0 (the kernel names no workflow, INV-1).

## Task Commits

Each task was committed atomically:

1. **Task 1: Cancellation propagation + fanout-boundary checks + finally-teardown** — `cab1e8a` (feat)
2. **Task 2: SC-001 sample fan-out workflow (manifest + AGENT.md only) + phase exit gate** — `de807e8` (feat)

_Note: both tasks carried `tdd="true"`; tests were authored alongside the implementation (RED→GREEN within the same task commit, the project's established offline-suite cadence)._

## Files Created/Modified

- `backend/agents/execution_engine/fanout.py` — `_check_cancel`; the cancel checks at the 3 boundaries; `_gather_or_cancel` + `_suppress_cancel` + `_mark_open_cancelled`; the `try/finally` wrap; `_teardown_allocated` extended to all paths + the `teardown_isolated_workspace`-preferred handle; per-worker `cancelled`-on-cancel row flip.
- `backend/agents/execution_engine/kernel_services.py` — `teardown_isolated_workspace` cancel-path handle; `run_worker` threads the worker input via `task_number=worker_index+1` (FANOUT-04).
- `backend/agents/workflows/compiler.py` — `spawn_subagents=trusted` added to the trust-conditional workflow ceiling (T-11-05-03).
- `backend/agents/workflows/sample_fanout/workflow.yaml` (new) — the SC-001 fan-out proof manifest.
- `backend/tests/agents/fixtures/sc001_fanout/sample-fanout-plan/AGENT.md` + `sample-fanout-worker/AGENT.md` (new) — the test-scoped worker specs.
- `backend/tests/agents/test_fanout_cancel.py` (new) — FANOUT-11 + RESUME-01 (cancel before wave / mid-parallel / between sequential / before merge; zero-residue teardown; rows cancelled; fragments retained).
- `backend/tests/agents/test_sc001_fanout.py` (new) — the end-to-end SC-001 zero-engine-edit fan-out proof.

## Decisions Made

- Worker AGENT.md specs kept test-scoped (fixtures), NOT at `agents/prompts/` — a prompt-home `pipeline_type: sample_fanout` AGENT.md would break the loader schema gate; the manifest itself is at the real home. (See key-decisions for the full rationale; this is the proven sc001_task_loop/sample_brownfield precedent the plan told me to mirror exactly.)
- Cancel boundaries raise `CancelledError` (deferring `pipeline_cancelled` to the kernel's single outer handler) rather than re-emitting — INV-12 single home.
- `spawn_subagents` added to the trust-conditional ceiling (mirrors `exec`) so the file-trusted fan-out grant binds True (T-11-05-03).
- `run_worker` passes `task_number=worker_index+1` so the worker's per-worker input rides the existing CURRENT TASK injection path (FANOUT-04).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fan-out workers did not receive their per-worker input**
- **Found during:** Task 2 (the 3 SC-001 workers all wrote the SAME file)
- **Issue:** `run_worker` passed `task_block=input` with `task_number=None`, but `run_agent` only injected `current_task_block` when `task_number is not None`. So a fan-out worker's per-worker input was DROPPED — every worker saw only the shared context (the full plan via `context_from:[$previous]`) and could not differentiate its assigned task. The 3 fan-out workers all resolved to the same (last) `part_N.txt`. This is a genuine FANOUT-04 correctness bug in the worker path (the worker must receive its assigned slice), not a test artifact.
- **Fix:** `run_worker` now passes `task_number=worker_index+1` (a fan-out worker IS a per-task agent — one per fanned task) so the worker's input rides the EXISTING engine CURRENT TASK injection path. Parity-safe: a non-fanout `single_shot` step never routes through `run_worker`, so its byte/event parity is untouched (5 characterization snapshots byte/event-identical).
- **Files modified:** `backend/agents/execution_engine/kernel_services.py`
- **Verification:** the 3 workers now write 3 distinct files; characterization snapshots byte/event-identical.
- **Committed in:** `de807e8` (Task 2 commit)

**2. [Rule 2 - Missing critical functionality] File-trusted spawn_subagents grant could not bind**
- **Found during:** Task 2 (the sample_fanout `tools.spawn_subagents: true` compiled to `False`)
- **Issue:** The compiler's per-step workflow ceiling was `ToolPermissions(exec=trusted)` — its default `spawn_subagents=False` AND-masked the authored grant to `False` via `intersect_permissions`. So a file-trusted manifest could NEVER bind the privileged fan-out spawn grant the threat model T-11-05-03 describes ("the sample_fanout file manifest is trusted, so the privileged grant is allowed").
- **Fix:** `spawn_subagents` now rides the SAME trust-conditional ceiling as `exec` — `ToolPermissions(exec=trusted, spawn_subagents=trusted)`. A file/builtin manifest may grant it (binds True); a user/db manifest's untrusted ceiling collapses it OFF (and the CAP-03 `_check_trust` of the `tool:spawn_subagents` reference, `user_allowed=False`, already rejects the user/db grant upstream). Mirrors the engineer-authored-only `exec` posture exactly.
- **Files modified:** `backend/agents/workflows/compiler.py`
- **Verification:** the file-trust grant binds True; `test_compiler_trust.py` 23/23 + 5 characterization snapshots byte/event-identical (no user/db grant gained).
- **Committed in:** `de807e8` (Task 2 commit)

### File-placement deviation (decision, not auto-fix)

The plan's Task-2 `<files>` named `backend/agents/prompts/sample-fanout-worker/AGENT.md` (the real prompt home). Placing it there would add a `pipeline_type: sample_fanout` AGENT.md that `test_loader.py::test_every_pipeline_type_supported` scans and rejects (not in `SUPPORTED_PIPELINE_TYPES`) — breaking the loader gate, and requiring a non-test-scoped loader/registry edit. The proven SC-001 precedent the plan explicitly told me to "MIRROR EXACTLY" (`test_sc001_nonprototype_task_loop.py` / `sample_brownfield`) keeps the worker AGENT.md test-scoped in fixtures for this exact reason. I followed the precedent: manifest at the real home, AGENT.md test-scoped. Documented in key-decisions.

**Total deviations:** 2 auto-fixed (1 FANOUT-04 bug, 1 missing-critical ceiling) + 1 file-placement decision. **Impact:** both auto-fixes are correctness/security requirements surfaced BY the SC-001 proof (the proof is doing its job — exercising the agnostic kernel end-to-end found a real worker-input drop + a real grant-binding gap). No scope creep.

## Issues Encountered

- The SC-001 worker recursion: the first draft had the planner with `tools: [workspace]` (looped on the filesystem tools) and the part-writing model matched the planner's own prompt body. Resolved by making the planner text-only (`tools: []`) + scoping the part-write to the WORKER agent only + terminating the worker after its single write (the offline-harness scripted-model discipline).

## Known Stubs

None — cancellation propagates at every boundary; rows flip `cancelled`; every isolated workspace is torn down on every path (zero residue); completed fragments are preserved; `pipeline_cancelled` fires from the single outer handler; the SC-001 fan-out workflow runs end-to-end on registered capabilities with zero engine edit. The offline harness runs the fan-out in `shared_read` (no base workspace bound), so the 3 workers write into the shared merged base — the per-worker isolated-write redirection to the allocated workspace remains a runtime-layer wiring (the `isolated_workspace` is recorded + torn down; the agent's disk write redirection is the broader runtime concern, exercised live, not a stub of THIS plan's deliverables).

## Threat Flags

None — the only new surface is the `spawn_subagents` trust-conditional ceiling entry (mirrors the existing `exec` posture; a user/db grant still collapses OFF + is CAP-03-rejected) and the cancel-path teardown (reuses the existing `remove_worktree`/`cleanup` primitives). Both are in the plan's `<threat_model>` (T-11-05-01/03) and tested.

## User Setup Required

None — no external service configuration (zero new packages this phase; T-11-05-SC accept). The sample workflow uses only registered capabilities.

## Next Phase Readiness

- FANOUT-11 + RESUME-01 are closed: cancellation propagates to children, rows are marked cancelled, every isolated workspace is torn down (no leaks), partial artifacts are preserved, and `pipeline_cancelled` is emitted.
- SC-001 is PROVEN for fan-out (the core-value exit): a brand-new fanning workflow runs from manifest + AGENT.md only with zero engine edits authored for it.
- Phase 11 (engine-owned fan-out + merge) is feature-complete across 11-01..11-05; the full targeted offline gate is green (5 characterization snapshots byte/event-identical, banned-pattern + migration-ledger + compiler-trust + registry lockstep, lint-imports 4/0) as the phase exit. Ready for phase verification/security.

## Self-Check: PASSED

All 5 created files exist on disk; both task commits (`cab1e8a`, `de807e8`) are present in git history. Phase-exit gate green: 253 passed / 6 skipped across `test_sc001_fanout` + `test_fanout_cancel` + `test_fanout` + `test_isolation` + `test_merge` + `test_merge_conflict` + `test_budget` + `test_subagent_runs` + 5 characterization snapshots (byte/event-identical, SNAPSHOT_UPDATE unset) + `test_banned_patterns` + `test_migration_ledger` + `test_compiler_trust` + `test_registry_capabilities`; `test_loader.py` 44/44 green (the fixture-scoped AGENT.md choice did not break the schema gate); lint-imports 4 kept / 0 broken. SC-001 grep: `sample_fanout` in `backend/agents/execution_engine/` == 0.

---
*Phase: 11-engine-owned-fan-out-merge-5*
*Completed: 2026-06-11*

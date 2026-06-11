---
phase: 11-engine-owned-fan-out-merge-5
reviewed: 2026-06-11T10:30:00Z
depth: standard
files_reviewed: 40
files_reviewed_list:
  - backend/agents/authz.py
  - backend/agents/capabilities/merge/__init__.py
  - backend/agents/capabilities/merge/base.py
  - backend/agents/capabilities/merge/copy_disjoint.py
  - backend/agents/capabilities/merge/git_3way.py
  - backend/agents/capabilities/merge/html_fragment.py
  - backend/agents/capabilities/merge/json_merge.py
  - backend/agents/capabilities/registry.py
  - backend/agents/capabilities/strategies/fanout_batch.py
  - backend/agents/capabilities/tools/providers.py
  - backend/agents/execution_engine/budget.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/fanout.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/agents/factory.py
  - backend/agents/runtime/base.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/manifest.py
  - backend/agents/workflows/plan.py
  - backend/agents/workflows/sample_fanout/workflow.yaml
  - backend/alembic/versions/0019_subagent_runs.py
  - backend/app/agents/runtime/local.py
  - backend/app/agents/tools/runner_tools.py
  - backend/app/core/config.py
  - backend/app/models/__init__.py
  - backend/app/models/subagent_run.py
  - backend/tests/agents/fixtures/sc001_fanout/sample-fanout-plan/AGENT.md
  - backend/tests/agents/fixtures/sc001_fanout/sample-fanout-worker/AGENT.md
  - backend/tests/agents/test_budget.py
  - backend/tests/agents/test_compiler_trust.py
  - backend/tests/agents/test_fanout_cancel.py
  - backend/tests/agents/test_fanout_tool.py
  - backend/tests/agents/test_fanout.py
  - backend/tests/agents/test_isolation.py
  - backend/tests/agents/test_merge_conflict.py
  - backend/tests/agents/test_merge.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/agents/test_sc001_fanout.py
  - backend/tests/agents/test_subagent_runs.py
  - specs/003-workflow-engine-decoupling/migration-ledger.md
findings:
  critical: 6
  warning: 8
  info: 5
  total: 19
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-06-11T10:30:00Z
**Depth:** standard
**Files Reviewed:** 40
**Status:** issues_found

## Summary

Phase 11 lands a large, well-documented fan-out + merge subsystem (single kernel spawn path, per-run budget, isolation scopes, four merge strategies, subagent audit rows, conflict policies). The unit-level pieces are individually solid: the migration is additive with `owner_id`+`workspace_id`, the merge strategies never silently overwrite, `spawn_subagents` is a spawn-free emitter with `user_allowed=False`, the kernel branches on no workflow name (INV-1 holds), and the cancel/teardown discipline in `run_fanout` is careful.

The systemic problem is **integration wiring**: several documented behaviors reference handle attributes, context fields, or compiled fields that are **never bound on the live path** — and the test suites stub exactly those attributes onto fake runners/steps, so every gap is green in CI. Concretely: named-worker selection, per-worker write isolation, the worktree/git_3way path, the `on_conflict`/`merge_agent` policy surface, and the wall-clock/token/depth budget dimensions are all dead or mis-wired in live operation. Only the self×N, shared-workspace, vacuous-merge path actually works end-to-end (which is exactly what the SC-001 test exercises — its own comment concedes "offline isolation degrades to shared_read").

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Named-worker fan-out is always rejected — `allowed_workers` / `agent_exists` never bound on the live runner handle

**File:** `backend/agents/execution_engine/fanout.py:89-90`, `backend/agents/execution_engine/kernel_services.py` (no binding), `backend/agents/workflows/compiler.py:230`
**Issue:** `_select_workers` reads `getattr(runner, "allowed_workers", None) or []` and `getattr(runner, "agent_exists", None)`. `KernelServices` (the live `ctx.runner`) defines **neither** attribute, and the engine never threads `compiled.allowed_workers` onto the handle (repo-wide grep: the only non-test references are manifest/compiler/plan/fanout). Consequence: on the live path `allowed` is always the empty set, so **every** named-worker request raises `FanoutError` — even when the manifest's `allowed_workers` lists the worker and the compiler accepted it. The registry-existence check (`agent_exists`) is silently skipped (`None` → no check). FANOUT-03's heterogeneous fan-out can never succeed in production. The tests pass only because `_FakeRunner` in `tests/agents/test_fanout.py:42-56` fabricates both attributes.
**Fix:** Bind both in `KernelServices.__init__` (or at handle construction in `_execute_impl`):
```python
# kernel_services.py — constructor
self.allowed_workers = list(getattr(compiled, "allowed_workers", []) or [])

def agent_exists(self, agent_id: str) -> bool:
    return any(s.id == agent_id for s in self._ordered_agents)  # or registry lookup
```
and add an integration test that drives `run_fanout` through the **real** `KernelServices` with a named worker.

### CR-02: Per-worker write isolation is cosmetic — `isolated_workspace` is bound but consumed by nothing; workers write into the shared run sandbox

**File:** `backend/agents/execution_engine/kernel_services.py:774` (only write site), `backend/agents/execution_engine/fanout.py:286-289, 332-349`
**Issue:** `run_worker` stamps `isolated_workspace=workspace` onto the worker step view and its docstring claims "the run-one-agent primitive reads it when present" — but `_run_agent` (and everything downstream: `create_runner`, `DeepAgentRunner`, `RunSandbox`) never reads `isolated_workspace` anywhere (repo-wide grep: zero readers). Every worker therefore writes into the **shared** run sandbox (`self.sandbox`):
1. Two parallel workers writing the same relpath cross-contaminate — the exact T-11-02-02 threat FANOUT-05 claims to mitigate.
2. The allocated `sub_sandbox`/worktree dirs stay **empty**, so `_fragment_files(worker_ws)` returns `{}`, `write_fragment_artifact` never fires (no FANOUT-06 fragment refs), and the merge runs over zero fragments — `copy_disjoint`'s conflict detection can never engage live.
The SC-001 test passes only because the workers' shared-sandbox writes happen to coincide with the expected "merged base" (`test_sc001_fanout.py:336-351` acknowledges the degrade).
**Fix:** Make the run-one-agent path honor the per-worker workspace: thread `worker_step.isolated_workspace` through `run_agent` → `_run_agent` → `create_runner` as the sandbox the deepagents disk backend writes to (e.g. pass the `_ChildSandbox`-backed workspace in place of the shared `RunSandbox` for the worker invocation), then read fragments from it as today. Add a test asserting two parallel workers writing the same relpath land in distinct roots **through `run_worker`**, not just through `allocate_sub_sandbox` directly.

### CR-03: Manifest `on_conflict` is silently dropped; the merge_agent policy is unreachable end-to-end

**File:** `backend/agents/workflows/compiler.py:479-490` (Step construction), `backend/agents/workflows/compiler.py:99-101` (`_ALLOWED_FANOUT_KEYS`), `backend/agents/execution_engine/fanout.py:745, 779-781`
**Issue:** Three compounding gaps in the §13 conflict-policy surface:
1. `on_conflict` is in `_ALLOWED_STEP_KEYS`, and `sample_fanout/workflow.yaml:53` declares it, but `_compile_step` never passes `raw.get("on_conflict")` into the `Step(...)` constructor — `Step.on_conflict` stays at its `"human_gate"` default. A manifest declaring `on_conflict: abort` (a fail-closed correctness intent) is **silently downgraded** to human_gate.
2. `FanoutSpec.merge_agent` exists (`plan.py:216`) but `merge_agent` is **not** in `_ALLOWED_FANOUT_KEYS` and `_compile_fanout` never sets it — so no manifest can ever designate a merge worker (declaring one is a CompilerError).
3. Even if it could, `_run_merge_agent` reads `getattr(runner, "run_merge_agent", None)` and **`KernelServices` defines no `run_merge_agent`** — the live path always falls straight to human_gate.
`tests/agents/test_merge_conflict.py:144-146` fabricates `SimpleNamespace(on_conflict=..., fanout=SimpleNamespace(merge_agent=...))` and a fake `run_merge_agent`, masking all three.
**Fix:** In `_compile_step`, pass `on_conflict=raw.get("on_conflict", "human_gate")` (validated against the 4-policy set); add `"merge_agent"` to `_ALLOWED_FANOUT_KEYS` and set it in `_compile_fanout`; implement `KernelServices.run_merge_agent` (a bounded `run_agent` invocation over the designated worker) or explicitly document/strip the policy until it exists.

### CR-04: Wall-clock and token budget enforcement is dead code — `note_wall_clock()` / `note_tokens()` have zero call sites

**File:** `backend/agents/execution_engine/budget.py:219-254`, `backend/agents/execution_engine/fanout.py:201-205, 422-443`
**Issue:** `run_fanout` arms the wall-clock deadline (`budget.arm()`, fanout.py:204) but **nothing ever calls `note_wall_clock()`** — not between sequential workers, not at the pre-merge boundary, nowhere (repo-wide grep: only budget.py itself and tests). The deadline is therefore never checked and a fan-out run can exceed `wall_clock_seconds` indefinitely, contradicting the docstring's "a mid-flight breach aborts gracefully" (FANOUT-09). Likewise `note_tokens()` is never called, so a declared `limits.max_tokens` cap is never enforced at any boundary. Compounding: `warn_threshold_reached("wall_clock")` reads `_snapshot.wall_clock_seconds`, which only those uncalled methods (or `spent()`) refresh — so the 80% wall-clock `budget_warning` in fanout.py:430-443 can never fire either (the snapshot is stale at 0.0 when the warn loop runs). `tests/agents/test_budget.py:187-213` calls `note_*` directly, masking the missing call sites.
**Fix:** Call `budget.note_wall_clock()` at the run_fanout boundaries (before each sequential spawn, before the merge, and inside `_bounded` before each parallel worker), and `budget.note_tokens(n)` where worker usage is collected (e.g. in `_run_one` after `run_worker` completes, from the worker's usage events). Have the warn loop call `budget.spent()` first so wall-clock spend is fresh.

### CR-05: `ctx.depth` is never incremented — the `max_depth` budget dimension and nested thread-id namespacing are unenforceable

**File:** `backend/agents/execution_engine/context.py:167-168` (sole definition, default 0; no writer anywhere), `backend/agents/execution_engine/budget.py:179-185`, `backend/agents/execution_engine/fanout.py:182, 275-279`
**Issue:** `run_fanout` reads `depth = getattr(ctx, "depth", 0)` and `reserve()` refuses when `depth + 1 > max_depth`. But nothing in the codebase ever writes `ectx.depth` — a worker that itself triggers a fan-out (via `spawn_subagents` → `_derive_fanout`, engine.py:1976-1978, which reuses the **same** `ectx`) still sees `depth == 0`. So the depth ceiling (`max_depth=2`) can never trip, the `d{depth}` thread-id segment (fanout.py:276-279, "child thread ids never collide across fan-out levels") never engages, and every `subagent_runs.depth` row is recorded as 0 regardless of nesting. The only live bound on recursive fan-out is the per-run `max_subagents` count. `tests/agents/test_budget.py:142` passes `depth=` to `reserve` directly, masking the missing propagation.
**Fix:** Increment depth for the worker's execution scope — e.g. in `run_fanout`'s `_run_one`, run the worker under a child context view (`worker_ctx = copy with depth=depth+1`) or save/restore `ectx.depth += 1` around `runner.run_worker(...)`, so a nested `_derive_fanout` reserves at the correct depth and thread ids/audit rows carry it.

### CR-06: The worktree isolation scope and `git_3way` merge are unreachable live — `has_git` is never stored on a workspace, and workers never commit

**File:** `backend/app/agents/runtime/local.py:583-628` (`create_workspace` accepts `has_git` and discards it; `LocalWorkspace.__init__` has no `has_git`), `backend/agents/execution_engine/fanout.py:168`, `backend/app/agents/runtime/local.py:534-567`
**Issue:** `_select_isolation_scope` keys on `getattr(base_workspace, "has_git", False)`. `LocalWorkspace` never defines a `has_git` attribute (the param is documented "advisory" and dropped), so on the live runtime the getattr default always yields `False` → the scope is **always** `sub_sandbox`, never `worktree`; `git_3way` is never selected (`_select_merge_strategy`, fanout.py:586). The entire worktree machinery (`allocate_worktree`, `spawn_point_commit`, `merge_worktree`, `remove_worktree`) is dead-wired live. Worse, even if it were reachable: nothing in the worker path ever **commits** on the per-worker branch, so `merge_worktree`'s `git merge --no-ff --no-commit <branch>` would report "already up to date" (clean, nothing merged) and the worker's uncommitted worktree writes are then destroyed by the `remove_worktree --force` teardown — worker output silently lost. Tests mask both: `test_isolation.py:237` uses `SimpleNamespace(has_git=True)` and `test_merge.py` drives `Git3WayMerge` against fakes.
**Fix:** Store the flag (`self.has_git = has_git` in `LocalWorkspace.__init__`, set/updated by `clone_repo`), and add a commit step to the worker teardown-before-merge path (e.g. `git add -A && git commit` on the worker branch inside `allocate_worktree`'s workspace before `merge_worktree` runs, or commit in `_run_one` after the worker completes). Add a live-shaped test: real `LocalSandboxRuntime` base with a git repo → `run_fanout` selects `worktree` and the merge actually integrates committed worker edits.

## Warnings

### WR-01: The fan-out fulfilment point enforces no `spawn_subagents` permission — the compiled grant ceiling is computed and then never read

**File:** `backend/agents/execution_engine/engine.py:1673-1704` (`_derive_fanout`), `backend/agents/workflows/compiler.py:424-437, 467-470`, `backend/agents/factory.py:472-541`
**Issue:** `_derive_fanout` fulfils any `spawn_subagents` tool_result without consulting `step.tools.spawn_subagents`. The factory binds the tool purely off AGENT.md `spec.tools` (the grant model is explicitly "not yet enforced", factory.py:483-493). The compiler's untrusted-grant guard rejects `exec`/`network`/`secrets` but **not** `spawn_subagents: true` (compiler.py:426-431), relying on the trust-conditional ceiling (`ToolPermissions(spawn_subagents=trusted)`) — whose output (`effective_tools`) nothing ever reads. Net: a user/db manifest that references an agent whose AGENT.md declares the `spawn_subagents` tool set gains fan-out spawning despite `user_allowed=False` (T-11-01-01's intent). Impact is bounded by the BudgetManager subagent cap and self-only worker selection, and user/db manifests are not yet live — hence Warning, not Critical.
**Fix:** Gate the fulfilment point: in `_derive_fanout`, return (and log) unless `getattr(getattr(step, "tools", None), "spawn_subagents", False)` is True. Optionally also add `spawn_subagents` to the untrusted `granted_priv` rejection list in the compiler for fail-loud symmetry, and add a `test_compiler_trust` case for it (the suite covers exec/network/secrets but omits spawn_subagents).

### WR-02: A crashed merge strategy is reported as a clean `merge_completed`

**File:** `backend/agents/execution_engine/fanout.py:672-678`
**Issue:** When `strategy.merge(base, fragments)` raises, the handler logs a warning and yields `{"type": "merge_completed", "data": {..., "applied": [], "conflicts": 0}}` — indistinguishable from a genuinely clean merge. Consumers (UI, downstream steps, audit) see success while nothing was integrated; the failure is observable only in server logs.
**Fix:** Emit a distinct event (e.g. `merge_failed` or `merge_completed` with `"error": str(exc)` and `"applied": []`) so the failure is first-class, mirroring the conflict path's no-silent-overwrite discipline.

### WR-03: Fragment persistence keeps only the alphabetically-first file, contradicting its own docstring

**File:** `backend/agents/execution_engine/fanout.py:339-349`
**Issue:** The comment says "the concatenation is a stable digest of the fragment", but the code persists only `frag_files[sorted(frag_files.keys())[0]]` — a multi-file worker's remaining outputs do not survive an abort/cancel (the stated purpose of FANOUT-06). In worktree mode `_fragment_files` walks the **entire checkout** (all repo files), so the persisted "fragment" would be an arbitrary, likely-unmodified repo file.
**Fix:** Persist all files (one ref per file, or a serialized bundle matching the `file_bundle` kind), and in worktree mode restrict `_fragment_files` to paths changed since `base_commit` (e.g. via the git handle's diff).

### WR-04: A non-worker exception in `_run_one` orphans sibling tasks and tears their workspaces down under them

**File:** `backend/agents/execution_engine/fanout.py:286-299, 409-420, 471-508`
**Issue:** `_run_one` only catches exceptions around `runner.run_worker`; an exception from `allocate(...)` or `record_subagent_run(...)` propagates out of the task. `asyncio.gather` (no `return_exceptions`) then re-raises immediately while the **sibling tasks keep running detached**; `run_fanout`'s `finally` runs `_teardown_allocated`, rmtree-ing workspaces that in-flight workers are still writing to, and their `subagent_runs` rows are left `running` forever (the `_mark_open_cancelled` path only runs on `CancelledError`).
**Fix:** On any gather exception, cancel and await all outstanding tasks before propagating (mirror the cancel path: `for t in tasks: t.cancel()`; `await asyncio.gather(*tasks, return_exceptions=True)`; `await _mark_open_cancelled(...)`), then re-raise.

### WR-05: `run_worker` reports `total_tasks=worker_index + 1` — every worker but the last sees a wrong "task i of N"

**File:** `backend/agents/execution_engine/kernel_services.py:785-792`
**Issue:** `run_agent(..., task_number=worker_index + 1, total_tasks=worker_index + 1, ...)` makes worker 0 of a 5-wide fan-out see "task 1 of 1" and worker 2 see "task 3 of 3". The `=== CURRENT TASK ===` header the model reads is wrong for all but the last worker. Also, the named-worker step view inherits `strategy=getattr(step, "strategy", ...)` — i.e. `"fanout_batch"` — which is misleading metadata on a plain worker run (harmless today only because `_run_agent` ignores it).
**Fix:** Thread the actual wave width into `run_worker` (e.g. a `total_workers` kwarg from `run_fanout`, which knows `len(selected)`) and pass it as `total_tasks`; set the worker step view's `strategy="single_shot"`.

### WR-06: `FanoutSpec.agent` / `count` / `workers` are compiled but consumed by nothing — the declared heterogeneous/self×N surface is inert

**File:** `backend/agents/workflows/compiler.py:516-523`, `backend/agents/capabilities/strategies/fanout_batch.py:73`, `backend/agents/execution_engine/fanout.py` (no reader of `step.fanout.agent/count/workers`)
**Issue:** The compiler materializes `agent`, `count`, and `workers` onto `FanoutSpec`, and `sample_fanout/workflow.yaml:62-63` declares `agent: self` / `count: 3` — but `fanout_batch` always emits `{"agent": "self"}` per parsed task and `run_fanout` never reads any of the three fields. The actual fan-out width is the parsed task count; `count: 3` is decorative (it coincidentally matches the 3-task plan). The plan.py/fanout_batch docstrings claim "workers ... resolved + validated inside run_fanout", which is false.
**Fix:** Either consume the fields (`workers` → per-request `agent` values; `count` → self×N width when no task_source) or remove them from `_ALLOWED_FANOUT_KEYS`/`FanoutSpec` until implemented — a declared-but-ignored manifest field violates the "manifests are data the engine honors" contract.

### WR-07: The `spawn_subagents` tool's `mode` argument is parsed and then ignored by the engine

**File:** `backend/app/agents/tools/runner_tools.py:44-58`, `backend/agents/execution_engine/engine.py:1696-1703`
**Issue:** The tool serializes `{"fanout_request": [...], "mode": mode}` and its docstring promises `"sequential"` support; `_derive_fanout` extracts only `fanout_request` and never reads `payload["mode"]` — the runtime path always uses the step's `FanoutSpec.mode` (default: parallel). The inline comment ("for the runtime tool path the request carries the mode") describes behavior that does not exist. A model requesting sequential execution gets parallel.
**Fix:** Read `payload.get("mode")` in `_derive_fanout` and thread it into the step view passed to `run_fanout` (clamped to the engine's concurrency cap as today), or remove `mode` from the tool signature/docstring.

### WR-08: `json` and `html_fragment` merges never produce the merged document — only conflict detection

**File:** `backend/agents/capabilities/merge/json_merge.py:54-89`, `backend/agents/capabilities/merge/html_fragment.py:55-88`
**Issue:** Both strategies record `applied` keys/section-ids but write/return no merged output: `JsonMerge`'s docstring claims "The merged document accumulates each fragment's NON-conflicting keys", yet the accumulated `claimed` dict is discarded (contrast `copy_disjoint`, which calls `base.write(...)`). A custom SC-001 workflow selecting these strategies would get a `merge_completed` event listing applied keys while no integrated document exists anywhere.
**Fix:** Mirror `copy_disjoint`: invoke a structural writer on the base when present (e.g. `base.write(key, value)` / `base.set_section(sid, html)`), or return the merged doc on `MergeResult` and have the engine persist it.

## Info

### IN-01: `WORKSPACE_BUDGET_MAX_TOKENS` setting defined but never read

**File:** `backend/app/core/config.py:127`
**Issue:** Only `WORKSPACE_BUDGET_MAX_SUBAGENTS` is consumed (engine.py:810). The tokens ceiling has no reader — and given CR-04 (token accounting never runs), it could not be enforced even if read.
**Fix:** Wire it into `BudgetManager.from_limits` alongside the subagents ceiling, or drop it until the token path exists.

### IN-02: `BudgetManager.reserve`'s concurrency dimension is unreachable from the live path

**File:** `backend/agents/execution_engine/budget.py:187-192`, `backend/agents/execution_engine/fanout.py:119-129, 220`
**Issue:** `run_fanout` passes `concurrency=_resolve_concurrency(step)`, which is already clamped to `min(declared, DEFAULT_MAX_CONCURRENCY)`; `max_concurrency` equals `DEFAULT_MAX_CONCURRENCY`, so `concurrency > max_concurrency` can never be true except in direct unit invocations (`test_budget.py:133`). Dead check on the live path.
**Fix:** Either pass the *declared* (unclamped) value to `reserve` so the budget is the enforcer, or document the check as defense-in-depth for non-kernel callers.

### IN-03: `copy_disjoint` re-invokes `fragment.files()` once per path

**File:** `backend/agents/capabilities/merge/copy_disjoint.py:78-79`
**Issue:** `content = _files_of(frag)[path]` inside the per-path loop rebuilds the whole files map for every path (it was already built for the `sorted(...)` iteration). Wasteful and risks inconsistency against a non-snapshotting fragment view.
**Fix:** Hoist: `frag_files = _files_of(frag)` once per fragment; iterate `sorted(frag_files)`.

### IN-04: `_suppress_cancel` re-implements `contextlib.suppress`

**File:** `backend/agents/execution_engine/fanout.py:511-518`
**Issue:** A hand-rolled context-manager class duplicating stdlib behavior.
**Fix:** `with contextlib.suppress(asyncio.CancelledError): await poller`.

### IN-05: The Phase-11 test suites stub exactly the live-handle attributes that are never bound, so none of CR-01..CR-06 is catchable by CI

**File:** `backend/tests/agents/test_fanout.py:42-56`, `backend/tests/agents/test_merge_conflict.py:131-146`, `backend/tests/agents/test_isolation.py:236-258`, `backend/tests/agents/test_budget.py:142, 187-213`
**Issue:** Fake runners define `allowed_workers`, `agent_exists`, `run_merge_agent`; fake steps carry `on_conflict`/`fanout.merge_agent`; fake workspaces carry `has_git`; `reserve(depth=...)`/`note_*` are invoked directly. Each stub papers over a missing live binding (see CR-01..CR-06). This is a structural test-design gap: the contract between `fanout.py` and its handle is verified only against fakes, never against the real `KernelServices` surface.
**Fix:** Add a handle-contract test asserting `KernelServices` exposes every attribute `run_fanout`/`_resolve_conflict` reads (`allowed_workers`, `agent_exists`, `run_merge_agent`, ...), plus one end-to-end named-worker / on_conflict-from-manifest test through `compile_for_run` + the real handle.

---

_Reviewed: 2026-06-11T10:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

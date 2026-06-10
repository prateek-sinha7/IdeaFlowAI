---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
fixed_at: 2026-06-10T00:00:00Z
review_path: .planning/phases/09-local-workspace-runtime-repo-workflows-no-exec-4a/09-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-06-10
**Source review:** .planning/phases/09-local-workspace-runtime-repo-workflows-no-exec-4a/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (fix_scope: critical_warning — 3 Info findings out of scope)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: Infinite recursion between `RunSandbox.cleanup()` and `LocalWorkspace.teardown()`

**Files modified:** `backend/app/agents/sandbox.py`, `backend/app/agents/runtime/local.py`, `backend/tests/agents/test_local_runtime.py`
**Commit:** 3ef3f05
**Applied fix:** `RunSandbox.cleanup()` owns the rmtree again (`shutil.rmtree(self.root, ignore_errors=True)` — the pre-refold working body); `LocalWorkspace.teardown()` delegates one-way to it, so both entry points (sandbox facade and `LocalSandboxRuntime.teardown(ws)`) delete the run dir exactly once with a single disk-IO owner and no cycle. Added two regression tests: `test_teardown_removes_run_dir_without_recursion` (runtime entry, idempotent) and `test_runsandbox_cleanup_direct_entry_removes_run_dir` (facade entry — the exact RecursionError repro from the review).

### WR-01: Unrestricted `git clone <source>` enables transport/argument injection despite exec=OFF

**Files modified:** `backend/app/agents/runtime/local.py`
**Commit:** 8dc4d76
**Applied fix:** `clone_repo` now rejects `-`-prefixed sources (git option/argument injection), passes `--` to terminate option parsing, and threads `GIT_ALLOW_PROTOCOL=file:https:ssh` into the clone subprocess env so the command-executing `ext::`/`fd::` transports cannot fire from a host-injected RepoSpec URL. `_git` gained an optional `env` kwarg (None = inherit). Restricts only — nothing enabled; local-path fixture clones (`file` protocol) keep working, proven by the existing clone tests.

### WR-02: Fire-and-forget lineage persist task can be silently dropped

**Files modified:** `backend/agents/capabilities/context_pack/pack.py`, `backend/agents/capabilities/repo_inventory/inventory.py`
**Commit:** 49bd2ca
**Applied fix:** Both modules now hold the `loop.create_task(_persist())` result in a module-level `_PENDING_LINEAGE_TASKS` set with a done-callback discard, so asyncio's weak-ref-only task tracking can no longer garbage-collect the lineage DB write before it runs. The sync (`asyncio.run`) fallback path is unchanged.

### WR-03: `git_diff` mutates repo state (commits) during deliverable resolution

**Files modified:** `backend/app/agents/runtime/local.py`
**Commit:** 16f6bbe
**Applied fix:** `git_diff(base, work)` no longer commits. It checks the checked-out branch: when `work` is checked out, it stages to the index only (`git add -A`, surfacing untracked files) and returns `git diff --cached <base>` (subsumes committed `base..work` deltas plus uncommitted edits); when `work` is NOT checked out it returns the pure ref diff `git diff base..work` — so an edit can never be committed onto the wrong (e.g. `base`) branch by the read-path resolver. `test_repo_diff_performs_no_commit_or_push` and the uncommitted-edit path in `test_clone_branch_read_write_search_diff` both pass.

### WR-04: Dead computed variable `_active_integration_servers` in the engine run-entry

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** fa1b86e
**Applied fix:** Deleted the never-read declaration and assignment; left a NOTE pointing at the single computation site (`_rec_servers` via `SCOPE_TO_SERVER` at the scoped-store entry) so the duplicate resolution is not reintroduced. Characterization parity gate (5 snapshot suites, 24 tests) and import-linter (4 kept / 0 broken) verified green after the engine edit.

### WR-05: MCP allow-list filter accepts only exact name forms; silent over-drop on prefixed tools

**Files modified:** `backend/app/agents/mcp/client.py`
**Commit:** e52f212
**Applied fix:** `get_tools` now matches on the bare MCP tool name robustly — a tool whose name carries a known server prefix with any of the separators `__`, `.`, `-`, `:` matches when the stripped remainder is a declared exposed tool. When an allow-list filters out ALL connected tools (while tools exist), the adapter logs at WARNING with the allowed and connected name sets, so a total over-drop from adapter naming drift is visible instead of indistinguishable from "no scope active". Partial drops keep the INFO log.

## Verification

- Targeted suites green after each fix; final sweep: 118 passed (`test_sandbox_deliverable`, `test_local_runtime`, `test_repo_diff`, `test_context_pack`, `test_repo_inventory`, `test_mcp_client`, `test_sample_brownfield_workflow`, `test_registry_capabilities`).
- Characterization parity gate: 24 passed (all 5 snapshot suites) after the engine/sandbox/runtime edits.
- import-linter: 4 contracts kept, 0 broken.
- Each fix committed atomically on the phase branch; no uncommitted source changes remain.

---

_Fixed: 2026-06-10_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

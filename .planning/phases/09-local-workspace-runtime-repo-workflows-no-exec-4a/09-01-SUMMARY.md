---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
plan: 01
subsystem: infra
tags: [runtime, workspace, git, hexagonal-ports, import-linter, capability-registry, sandbox]

# Dependency graph
requires:
  - phase: 08-capabilities-runtime-frontend-1d
    provides: "self-registering CapabilityRegistry (@register / discover() / _KNOWN membership + drift guard)"
  - phase: 04-manifest-compiler-1a
    provides: "agents/capabilities/base.py one-method @runtime_checkable Protocol idiom (stdlib-only port boundary)"
provides:
  - "agents/runtime/base.py — RuntimeEnvironment / Workspace / ExecutionPolicy / IsolationProvider kernel-side Protocol ports (the ECS-swap seam, D-01)"
  - "app/agents/runtime/local.py — LocalSandboxRuntime + LocalWorkspace, the single git-subprocess owner (clone/branch/diff), @register('runtime_env','local')"
  - "the runtime_env capability kind, registered + reachable via the ctx.runner handle"
  - "the 4th import-linter forbidden contract locking agents.runtime ↛ [agents.execution_engine, app]"
  - "tests/agents/conftest.py local_git_fixture — a real local git repo seeder (no network), reusable by 09-03/09-04"
affects: [09-02-runtime-workspace-runsandbox-refold, 09-03-repo-inventory-index-context, 09-04-repo-diff-brownfield-workflow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "kernel-side stdlib-only Protocol port layer (agents/runtime/base.py) — the kernel imports only ports; concrete impl reached via handle, locked by import-linter"
    - "app-side concrete runtime impl self-registers under a distinct capability kind (runtime_env) discovered via discover() _forward_packages"
    - "the impl is the SINGLE git-subprocess owner; disk-safety reuses the existing RunSandbox.path_for traversal-rejection"

key-files:
  created:
    - backend/agents/runtime/__init__.py
    - backend/agents/runtime/base.py
    - backend/app/agents/runtime/__init__.py
    - backend/app/agents/runtime/local.py
    - backend/tests/agents/test_local_runtime.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/tests/agents/conftest.py
    - backend/tests/agents/test_registry_capabilities.py
    - backend/pyproject.toml

key-decisions:
  - "Runtime ports kept kernel-side stdlib-only (agents/runtime/base.py) mirroring agents/capabilities/base.py; the 4th import-linter contract locks agents.runtime ↛ [agents.execution_engine, app] — the ECS-swap seam (D-01)"
  - "LocalSandboxRuntime registered under a DISTINCT runtime_env kind (NOT runtime:langchain_deepagents, which is the agent-runtime adapter); user_allowed defaults False — a runtime backend is an operator concern"
  - "LocalWorkspace is the single git-subprocess owner (clone/branch/diff) and reuses RunSandbox.path_for for traversal-safety; exec_command raises PermissionError under the default exec=OFF policy (no-exec invariant until N3)"
  - "git_diff stages + commits the working-tree edit onto the work branch before diffing base..work so an uncommitted edit is surfaced in the ref diff"
  - "the local_git_fixture seeder lives in tests/agents/conftest.py (suite-shared) so 09-03/09-04 reuse it; it forces git identity via -c flags so it works on a machine with no global git config"

patterns-established:
  - "Runtime backend = port (kernel) + impl (app-side, @register('runtime_env', name)) + discover() wiring — adding ECS later is a backend swap, zero engine edit"
  - "Capability membership growth bumps the _KNOWN drift-guard count + _EXPECTED_NAMES in test_registry_capabilities.py in lockstep (34→35)"

requirements-completed: [RUNTIME-01]

# Metrics
duration: ~8min
completed: 2026-06-10
---

# Phase 09 Plan 01: Local Workspace Runtime Port Layer Summary

**Net-new kernel-side runtime port layer (RuntimeEnvironment/Workspace/ExecutionPolicy/IsolationProvider) plus an app-side LocalSandboxRuntime that clones a local git fixture, branches, reads/writes/searches, and produces a git_diff — exec denied under the default policy, locked by a 4th import-linter contract (the ECS-swap seam, D-01).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-10T07:54Z
- **Completed:** 2026-06-10T08:02:27Z
- **Tasks:** 3
- **Files modified:** 9 (5 created, 4 modified)

## Accomplishments
- Landed the four kernel-side runtime ports (`RuntimeEnvironment`, `Workspace`, `ExecutionPolicy`, `IsolationProvider`) as stdlib-only `@runtime_checkable` Protocols in `agents/runtime/base.py` — kernel imports only ports.
- Implemented `LocalSandboxRuntime` + `LocalWorkspace` app-side: clones a local git fixture into the per-run dir, creates a branch, round-trips read/write/search, produces a non-empty unified `git_diff`, and owns the single git-subprocess surface.
- Enforced the no-exec invariant: `exec_command` raises `PermissionError` under the default `ExecutionPolicy(exec=False/network=False/secrets=[])`.
- Added the 4th import-linter `forbidden` contract (`agents.runtime ↛ [agents.execution_engine, app]`) — import-linter now 4 kept / 0 broken.
- Registered the distinct `runtime_env` capability kind + wired `app.agents.runtime` into `discover()`; the capabilities API palette surfaces it reflectively (zero endpoint edit).
- Seeded a reusable `local_git_fixture` (offline, no network) in the suite conftest for 09-03/09-04.

## Task Commits

Each task was committed atomically:

1. **Task 1 (Wave 0): test + git-fixture seeder + import-linter contract** - `e55f89a` (test)
2. **Task 2: kernel-side runtime ports (stdlib-only Protocols)** - `6125267` (feat)
3. **Task 3: LocalSandboxRuntime + register runtime_env + discover() wiring** - `5707298` (feat)

**Plan metadata:** _(final docs commit below)_

## Files Created/Modified
- `backend/agents/runtime/base.py` - The 4 kernel-side runtime Protocol ports (stdlib-only).
- `backend/agents/runtime/__init__.py` - Package marker documenting the runtime port boundary.
- `backend/app/agents/runtime/local.py` - `LocalSandboxRuntime` + `LocalWorkspace` + `LocalExecutionPolicy`; the single git-subprocess owner; `@register("runtime_env","local")`.
- `backend/app/agents/runtime/__init__.py` - Imports `local` so `@register` fires on package import (discovery precedent: `app.agents.validators`).
- `backend/tests/agents/test_local_runtime.py` - Wave-0 clone/branch/read/write/search/diff + exec-denied + traversal-reject + registry-reachable.
- `backend/agents/capabilities/registry.py` - Added `("runtime_env","local")` to `_KNOWN`; added `"app.agents.runtime"` to `discover()` `_forward_packages`.
- `backend/tests/agents/conftest.py` - Added `local_git_fixture` (real local git repo via subprocess, no network).
- `backend/tests/agents/test_registry_capabilities.py` - Drift-guard count 34→35 + `_EXPECTED_NAMES` pair (expected membership growth).
- `backend/pyproject.toml` - 4th `forbidden` import-linter contract on `agents.runtime`.

## Decisions Made
- Ports kept kernel-side stdlib-only (mirrors `agents/capabilities/base.py`); the impl is app-side because it reaches `app.agents.sandbox` (disk-safety) + `app.core.config.settings.RUNS_ROOT`.
- Registered under the distinct `runtime_env` kind (NOT `runtime:langchain_deepagents`); `user_allowed=False` — a runtime backend is an operator concern, off the user palette.
- `LocalWorkspace` is the single git-subprocess owner; `git_diff` stages + commits the working-tree edit onto the work branch before diffing `base..work` so uncommitted edits surface in the ref diff.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Default-policy test instantiated the ExecutionPolicy Protocol directly**
- **Found during:** Task 3 (LocalSandboxRuntime verification)
- **Issue:** `test_default_execution_policy_denies_privileged_actions` called `ExecutionPolicy()`, but `ExecutionPolicy` is a `@runtime_checkable` Protocol — `TypeError: Protocols cannot be instantiated`.
- **Fix:** Constructed the concrete `LocalExecutionPolicy()` impl instead and asserted it `isinstance`-satisfies the `ExecutionPolicy` port structurally.
- **Files modified:** backend/tests/agents/test_local_runtime.py
- **Verification:** All 6 runtime tests pass.
- **Committed in:** 5707298 (Task 3 commit)

**2. [Rule 3 - Blocking] _KNOWN drift-guard count out of lockstep after registering runtime_env**
- **Found during:** Task 3 (registry wiring)
- **Issue:** `test_registered_count_is_exactly_thirty_four` (a hard-coded membership drift guard) tripped because adding `("runtime_env","local")` bumped `_KNOWN` from 34→35 — expected membership growth, not a regression.
- **Fix:** Updated the count assertion 34→35 (renamed the test accordingly), added the new pair to `_EXPECTED_NAMES`, and extended the count-rationale comment.
- **Files modified:** backend/tests/agents/test_registry_capabilities.py
- **Verification:** Registry + capabilities-API tests pass (72 passed).
- **Committed in:** 5707298 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both necessary for a green suite; no scope creep. The drift-guard bump is the sanctioned lockstep update for declared capability growth.

## Issues Encountered
None beyond the two auto-fixed deviations above.

## Known Stubs
- `IsolationProvider.allocate` / the per-run-vs-`shared_read` scope is declared (port exists, designed-now per the spec) but the concrete `allocate` impl is downstream (09-02); `sub_sandbox`/`worktree` scopes are Phase 11. This is an intentional, plan-declared forward seam, not a UI-blocking stub.

## Threat Flags
None — no new security surface beyond the plan's `<threat_model>`. `exec_command` is present-but-denied (T-09-01-02), traversal is rejected via `RunSandbox.path_for` (T-09-01-01), and the kernel↔app import direction is locked by the 4th import-linter contract (T-09-01-03). No `pyproject.toml` dependency was added (T-09-01-SC accept).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The runtime substrate (ports + LocalSandboxRuntime + git_diff/clone/branch + the reusable `local_git_fixture`) is ready for 09-02 (RunSandbox refold delegating to `Workspace`) and 09-03/09-04 (repo inventory/index/context + repo_diff workflow).
- import-linter 4 kept / 0 broken; banned-pattern + migration-ledger green (INV-13 untouched); 5 characterization snapshots byte/event-identical (09-01 is purely additive).

## Verification Evidence
- `tests/agents/test_local_runtime.py` — 6 passed (clone/branch/read/write/search/diff + exec-denied + traversal-reject + registry-reachable).
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (the new `agents.runtime` contract non-vacuous + green).
- `tests/agents/test_banned_patterns.py` + `test_migration_ledger.py` — 31 passed, 3 skipped (INV-13 / no parity files touched).
- `tests/agents/test_registry_capabilities.py` + `tests/unit/test_capabilities_api.py` + `test_registry.py` — 72 passed (drift count 34→35; palette reflective).
- 5 characterization snapshots (`prototype`/`app_builder`/`od_prototype`/`od_ppt`/`prototype_revision`) — 10 passed (byte/event-identical; no re-baseline).
- `grep -nE "import (app|agents\.execution_engine)" agents/runtime/base.py` — 0 lines (kernel-clean).

## Self-Check: PASSED
- FOUND: backend/agents/runtime/base.py
- FOUND: backend/app/agents/runtime/local.py
- FOUND: backend/tests/agents/test_local_runtime.py
- FOUND commit: e55f89a
- FOUND commit: 6125267
- FOUND commit: 5707298

---
*Phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a*
*Completed: 2026-06-10*

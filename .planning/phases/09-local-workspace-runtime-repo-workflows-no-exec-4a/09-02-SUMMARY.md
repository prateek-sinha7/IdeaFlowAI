---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
plan: 02
subsystem: infra
tags: [runtime, workspace, runsandbox-refold, migration, repositories, scoped-store, parity, hexagonal-ports]

# Dependency graph
requires:
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 01
    provides: "RuntimeEnvironment/Workspace/ExecutionPolicy ports + LocalSandboxRuntime/LocalWorkspace (the has_git=False/exec=off disk impl RunSandbox now delegates to)"
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: "ScopedStore default-deny owner/workspace-scoped writer (agents/authz.py) + workspaces table (0014, free-String kind + nullable repo_id)"
provides:
  - "Alembic 0017 — additive repositories table (owner_id/workspace_id NN, free-String provider) + workspaces.repo_id FK; reversible upgrade->downgrade -1->upgrade"
  - "Repository SQLAlchemy model (owner/workspace-scoped, auth_ref scoped-cred pointer)"
  - "ScopedStore.create_repository — one repositories row + linked kind=repo workspace; get_repository/assert_repo_owned default-deny reads (T-09-02-ID)"
  - "RunSandbox refolded as a thin Workspace(has_git=False, exec=off) facade — the single disk-IO impl, no if repo: engine fork (RUNTIME-02)"
  - "tests/agents/test_repositories_persistence.py — Wave-0 one-repo+one-kind=repo-workspace + cross-owner PermissionError denial"
affects: [09-03-repo-inventory-index-context, 09-04-repo-diff-brownfield-workflow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RunSandbox keeps the traversal-proof disk PRIMITIVES (root + path_for) that LocalWorkspace itself reuses; read/write/cleanup delegate to a lazily-built has_git=False Workspace — move-don't-copy, one disk-IO home, NOT a dual impl"
    - "additive repositories migration mirrors 0016: free-String columns (no sa.Enum), batch_alter_table FK so the ALTER is portable to SQLite + Postgres, named FK constraint for a deterministic downgrade"
    - "ScopedStore.create_repository + assert_repo_owned mirror create_workspace + assert_owns (default-deny owner/workspace scope; cross-owner read returns None / raises PermissionError)"

key-files:
  created:
    - backend/alembic/versions/0017_repositories_repo_workspace.py
    - backend/app/models/repository.py
    - backend/tests/agents/test_repositories_persistence.py
  modified:
    - backend/app/models/__init__.py
    - backend/agents/authz.py
    - backend/app/agents/sandbox.py
    - backend/tests/agents/test_migration_ledger.py
    - specs/003-workflow-engine-decoupling/migration-ledger.md

key-decisions:
  - "RunSandbox retains the disk primitives (root resolution + path_for) rather than itself wrapping a separate RunSandbox, because LocalWorkspace is constructed FROM the sandbox (sandbox.path_for/ensure) — wrapping would be circular. The facade's read/write/cleanup route through a lazily-built LocalWorkspace so disk IO lives in ONE place (the Workspace), satisfying move-don't-copy without dual-implementing path_for."
  - "RunSandbox.read keeps the legacy None-on-missing contract via an is_file() guard before delegating (LocalWorkspace.read_file raises on missing) — load-bearing for byte-parity."
  - "Migration-ledger R1 is a CHECK row (prose), not a grep row: the refold's consumed surface (path_for/read/write/...) survives byte-identical, so a bare grep would false-fire — the gate is the 5-pipeline byte/event parity + persistence test, exactly the L16/F4/F5 CHECK-row precedent."
  - "0017 uses batch_alter_table + a NAMED FK constraint so the FK add/drop is portable to SQLite (no native ADD CONSTRAINT) and the downgrade drops it deterministically; verified reversible offline against in-memory SQLite (no live Postgres offline)."
  - "repositories.provider is a free String (github|gitlab|local), no sa.Enum — additive + reversible, consistent with workspaces.kind/runtime; kind='repo' needs NO enum widening (the column was already a free String since 0014)."

patterns-established:
  - "Refold-by-delegation: a legacy facade survives by name while its bespoke internals route to a registered capability impl — the consumed surface is the parity oracle, the snapshots are the gate (SNAPSHOT_UPDATE UNSET)."

requirements-completed: [RUNTIME-02, RUNTIME-03]

# Metrics
duration: ~12min
completed: 2026-06-10
---

# Phase 09 Plan 02: Runtime Workspace + RunSandbox Refold + Migration 0017 Summary

**Additive migration 0017 adds the owner/workspace-scoped `repositories` table + the `workspaces.repo_id` FK (reversible offline), a `Repository` model + `ScopedStore.create_repository` writer that persists exactly one repo row + one linked `kind=repo` workspace, and the move-don't-copy refold of `RunSandbox` onto a `Workspace(has_git=False, exec=off)` facade — the 5-pipeline characterization stays byte + event identical with `SNAPSHOT_UPDATE` UNSET, and there is no `if repo:` engine fork.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2
- **Files modified:** 8 (3 created, 5 modified)

## Accomplishments
- Landed Alembic **0017** (`revision="0017"`, `down_revision="0016"`): creates `repositories` FIRST (so the FK target exists), then wires the already-present nullable `workspaces.repo_id` to it via a named, batch-portable FK. `downgrade()` drops the FK then the table — verified reversible (`upgrade head` → `downgrade -1` → `upgrade head`) against in-memory SQLite, with a single alembic head (`0017`).
- Added the `Repository` model (owner/workspace-scoped, free-String `provider`, `auth_ref` scoped-cred pointer) and registered it on `Base.metadata` (Pitfall 5).
- Added `ScopedStore.create_repository` (one `repositories` row + links the `kind=repo` workspace's `repo_id`) plus `get_repository` (default-deny read) and `assert_repo_owned` (explicit cross-owner `PermissionError`) — mirroring `create_workspace` / `assert_owns`.
- Refolded `RunSandbox` IN-PLACE onto a `Workspace(has_git=False, exec=off)`: `read`/`write`/`cleanup` now delegate to a lazily-built `LocalWorkspace` (the single disk-IO impl); the consumed surface (`__init__`/`ensure`/`root`/`path_for`/`read`/`write`/`cleanup` + `serialize_sandbox_deliverable`/`count_sandbox_deliverables`) is byte-identical, the `path_for` traversal-rejection and the serializer's raw-bytes read are preserved.
- Added the migration-ledger `R1` CHECK row for the refold and updated the ledger ratchet test (`_REQUIRED_ITEMS` + the `expected` flipped set) in lockstep.

## Task Commits

1. **Task 1 (Wave 0): migration 0017 + Repository model + ScopedStore writer + persistence/ledger tests** — `8682402` (feat)
2. **Task 2: RunSandbox refold → Workspace(has_git=False, exec=off)** — `0e90f3e` (refactor)

**Plan metadata:** _(final docs commit below)_

## Files Created/Modified
- `backend/alembic/versions/0017_repositories_repo_workspace.py` — additive `repositories` table + `workspaces.repo_id` FK (reversible).
- `backend/app/models/repository.py` — `Repository` model (owner/workspace-scoped; free-String provider; `auth_ref` cred pointer).
- `backend/app/models/__init__.py` — register `Repository` on `Base.metadata` + `__all__`.
- `backend/agents/authz.py` — `ScopedStore.create_repository` + `get_repository` + `assert_repo_owned` (default-deny / denial gate).
- `backend/app/agents/sandbox.py` — `RunSandbox` refolded to delegate disk IO to a `has_git=False` Workspace (consumed surface byte-identical).
- `backend/tests/agents/test_repositories_persistence.py` — Wave-0 one-repo + one-kind=repo-workspace linked by `repo_id`; cross-owner `PermissionError`.
- `backend/tests/agents/test_migration_ledger.py` — `R1` added to required + expected-flipped sets.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — `R1` RunSandbox-refold CHECK row.

## Decisions Made
- `RunSandbox` keeps the disk primitives (`root`/`path_for`) and delegates only `read`/`write`/`cleanup` to a `LocalWorkspace` built FROM itself — wrapping a separate `RunSandbox` would be circular since `LocalWorkspace` consumes `sandbox.path_for`/`ensure`.
- `R1` is a CHECK row (the consumed surface survives byte-identical, so a grep gate would false-fire) — the parity snapshots + persistence test are the real gate.
- `0017` uses `batch_alter_table` + a named FK so the FK is portable to SQLite and the downgrade is deterministic; reversibility proven offline against SQLite (no live Postgres offline, per backend/CLAUDE.md).

## Deviations from Plan

None — plan executed as written. Two minor in-task corrections (not scope changes):
- The persistence denial test initially scoped the reader store to a throwaway `workspace_id` that did not match the repo workspace's self-id, so the owner's own scoped read returned `None`. Fixed by scoping the run's store to the repo workspace's id (the real-world principal for a repo run) — the cross-owner denial assertion is unchanged.

## Issues Encountered
None beyond the test-scoping correction above.

## Known Stubs
None. `auth_ref` is a declared forward column (the scoped-cred pointer consumed by 09-05 MCP creds) — a plan-declared seam, not a UI-blocking stub. `IsolationProvider.allocate` remains the 09-01-declared downstream seam (untouched here).

## Threat Flags
None — no new security surface beyond the plan's `<threat_model>`. The `repositories`/`workspaces` rows carry `owner_id` + `workspace_id` and route through the default-deny `ScopedStore` (T-09-02-ID mitigated by the cross-owner `PermissionError` denial test). The migration is additive + reversible (T-09-02-01). The `RunSandbox.path_for` traversal-rejection is preserved through the refold and exercised by `test_local_runtime.py::test_path_traversal_rejected` (T-09-02-02). Prototype parity is byte/event-identical with `SNAPSHOT_UPDATE` UNSET (T-09-02-03).

## User Setup Required
None.

## Next Phase Readiness
- The `repositories` table + scoped writer + the one `Workspace` abstraction (now serving both the `has_git=False` artifact path and the 09-04 `has_git=True` repo path) are ready for 09-03 (repo inventory/index/context) and 09-04 (repo_diff + brownfield workflow).
- 5-pipeline characterization byte/event-identical (no re-baseline); lint-imports 4/0; banned-pattern + migration-ledger green (INV-13 untouched).

## Verification Evidence
- `tests/agents/test_repositories_persistence.py` + `test_migration_ledger.py` — 22 passed, 4 skipped (one repo + one kind=repo workspace linked by repo_id; cross-owner `PermissionError`; `R1` ledger row parses).
- Migration 0017 reversibility — offline SQLite `upgrade head` → assert `repositories` + `repo_id` FK present → `downgrade -1` → assert dropped → `upgrade head` (reversible); single alembic head `0017`.
- `grep -rn "if repo" agents/execution_engine/` → 0 matches (no engine fork).
- `serialize_sandbox_deliverable` has 0 executable `read_text(` calls (raw-bytes read preserved); `revision = "0017"` + `down_revision = "0016"` grep-confirmed.
- 5 characterization files + `test_sandbox_deliverable.py` + `test_local_runtime.py` — 29 passed, `SNAPSHOT_UPDATE` UNSET (byte + event identical, no re-baseline).
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken; `test_banned_patterns.py` + `test_create_runner.py` — 20 passed (INV-13 untouched; RunSandbox callers unbroken).

## Self-Check: PASSED
- FOUND: backend/alembic/versions/0017_repositories_repo_workspace.py
- FOUND: backend/app/models/repository.py
- FOUND: backend/tests/agents/test_repositories_persistence.py
- FOUND commit: 8682402
- FOUND commit: 0e90f3e

---
*Phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a*
*Completed: 2026-06-10*

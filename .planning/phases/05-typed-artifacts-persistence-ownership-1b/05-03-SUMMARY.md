---
phase: 05-typed-artifacts-persistence-ownership-1b
plan: 03
subsystem: api
tags: [ownership, authz, default-deny, sqlalchemy, scoped-store, idor, sync-orm]

# Dependency graph
requires:
  - phase: 05-02
    provides: "ORM models ArtifactRef/Workspace/RunEvent/RunCapabilities/WorkflowRun (owner_id + workspace_id columns)"
  - phase: 02-executioncontext-ownership-0b
    provides: "pure assert_owns L16 ownership predicate (relocated by this plan)"
provides:
  - "Single default-deny scoped store helper (agents/authz.py ScopedStore) — the one enforced read/write path for artifacts/runs/workspaces/events/capabilities"
  - "Relocated assert_owns as a real store-lookup method (reads parent run's true owner_id, raises typed PermissionError on mismatch)"
  - "Deletion of the old agents/execution_engine/authz.py (move-don't-copy, INV-12)"
  - "AUTHZ-04 cross-owner artifact + workspace denial test coverage; AUTHZ-03 anon:<session_id> isolation"
affects: [05-04, 05-05, 05-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Default-deny scoped store: one helper constructed with (owner_id, workspace_id, session) enforces the ownership boundary on every read (§19)"
    - "Injected-or-owned Session: pass Depends(get_db) from an endpoint or leave session=None for the engine path (sync SessionLocal()-inside-async, D-08)"
    - "assert_owns as a real store lookup (D-07) replacing the by-convention parent_owner_id argument"

key-files:
  created:
    - backend/agents/authz.py
  modified:
    - backend/tests/agents/test_parent_run_ownership.py
  deleted:
    - backend/agents/execution_engine/authz.py

key-decisions:
  - "ScopedStore is the single enforced read/write path (§19); reads use owner+visibility filter for ArtifactRef, owner+workspace for run/workspace/event/capabilities"
  - "assert_owns does an UNSCOPED-by-owner parent lookup (reads parent's true owner regardless of caller) then compares — preserves Phase-2 PermissionError message shape"
  - "Engine call-site rewiring deferred to 05-04 (next wave); this plan's gate is the store-layer denial suite, NOT an engine-importing E2E suite (vetted intra-phase gap)"
  - "Engine-driving E2E denial tests removed from this suite and reinstated in 05-04 once engine.py imports the relocated path"

patterns-established:
  - "Default-deny ownership: WHERE owner_id = :owner AND (workspace_id = :ws OR visibility IN ('workspace','public')); cross-owner → nothing → 404 at API"
  - "Sync ORM inside async def with injected-or-owned Session acquisition"

requirements-completed: [AUTHZ-01, AUTHZ-02, AUTHZ-03, AUTHZ-04]

# Metrics
duration: 3min
completed: 2026-06-07
---

# Phase 05 Plan 03: Default-Deny Scoped Store Helper Summary

**Relocated the L16 assert_owns seam into a single default-deny `ScopedStore` helper (owner_id + workspace_id/visibility filter on every artifact/run/workspace/event/capability read) with assert_owns now a real store lookup; deleted the old execution_engine/authz.py.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-07T20:17:25Z
- **Completed:** 2026-06-07T20:20:45Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 1 modified, 1 deleted)

## Accomplishments
- Created `agents/authz.py` with `ScopedStore` — the single enforced read/write path for `write_ref`/`get_ref`/`list_refs`/`lineage`/`tree`/`append_event`/`read_events`/`get_run`/`create_workspace`/`record_capabilities` + the relocated `assert_owns`.
- Every read applies the default-deny filter (owner + workspace/visibility); cross-owner reads return nothing → 404 at the API (IDOR→404 precedent).
- `assert_owns` is now a real store lookup (D-07): reads the parent run's true `owner_id` regardless of the caller and raises the typed `PermissionError` on mismatch, preserving the Phase-2 message shape.
- Deleted `agents/execution_engine/authz.py` (move-don't-copy, INV-12); helper imports `app.models` only, never `app.api` — `lint-imports` stays green.
- Extended the ownership test suite to 13 cases: L16 via store lookup, AUTHZ-04 artifact + workspace cross-owner denial (with same-owner positive controls), and AUTHZ-03 `anon:<session_id>` isolation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Relocate + grow agents/authz.py into the default-deny scoped store helper; delete the old module** - `6a210ea` (refactor)
2. **Task 2: Extend test_parent_run_ownership.py — AUTHZ-04 artifact + workspace denial + AUTHZ-03 anon:<session_id>** - `7b22c0c` (test)

_Note: TDD tasks — Task 1's behavioral RED lands in Task 2's denial suite (the helper smoke-import + lint-imports gate Task 1; Task 2's tests exercise the helper's enforced reads)._

## Files Created/Modified
- `backend/agents/authz.py` (created) - `ScopedStore` default-deny scoped store helper + relocated `assert_owns` real-lookup method.
- `backend/agents/execution_engine/authz.py` (deleted) - old pure predicate, moved up (INV-12).
- `backend/tests/agents/test_parent_run_ownership.py` (modified) - repointed to `agents.authz`; rewrote unit cases to the store-lookup method; added AUTHZ-04 + AUTHZ-03 coverage; anon strings → `anon:<session_id>`.

## Decisions Made
- ScopedStore is the single enforced ownership boundary (§19) rather than scattering filters in callers.
- `assert_owns` uses an UNSCOPED-by-owner parent lookup so it reads the parent's true owner regardless of the caller, then compares to `self._owner_id`.
- Removed the engine-driving E2E denial tests from this suite (the engine still imports the old path until 05-04 rewires it — vetted intra-phase gap). The L16 denial behavior is fully covered at the store layer it now lives in (`assert_owns` cross-owner/same-owner/missing-parent cases). The E2E suite is reinstated in 05-04 once the engine imports the relocated path.

## Deviations from Plan

None - plan executed exactly as written.

The plan explicitly anticipated that `engine.py:33` still imports `agents.execution_engine.authz` after deletion and that the engine call-site rewiring belongs to 05-04. Per the plan's instruction, only the test import was updated this plan; `engine.py` was left untouched. The acceptance gate is the authz/ownership tests + `lint-imports` (both green), not a full engine-importing suite.

## Issues Encountered
None. The new helper imported clean, all 13 tests pass, `lint-imports` reports 3 kept / 0 broken, and `ruff` is clean on both files.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The single default-deny store boundary is in place and tested. 05-04 wires `engine.py` (the L16 seed block at ~656–663 and the per-task/read sites) through `ScopedStore` and reinstates the engine-driving E2E denial tests; the `_derive_parent_owner` by-convention helper (engine.py:2694) is superseded by `ScopedStore.assert_owns` and can be removed in that wave.
- 05-05 (endpoints) can construct `ScopedStore(owner_id, workspace_id, session=Depends(get_db))` for `GET /{id}/artifacts` and `GET /{id}/events`.
- **Intra-phase note for the verifier:** `engine.py` currently imports the deleted `agents.execution_engine.authz` — this is the vetted wave boundary, NOT a regression. The engine-importing suite is expected to be repaired by 05-04.

## Self-Check: PASSED

- `backend/agents/authz.py` — FOUND
- `backend/tests/agents/test_parent_run_ownership.py` — FOUND
- `backend/agents/execution_engine/authz.py` — CONFIRMED DELETED
- Commit `6a210ea` (Task 1) — FOUND
- Commit `7b22c0c` (Task 2) — FOUND

---
*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Completed: 2026-06-07*

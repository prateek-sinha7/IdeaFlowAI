---
phase: 05-typed-artifacts-persistence-ownership-1b
plan: 06
subsystem: engine
tags: [execution-engine, artifacts, persistence, ownership, scoped-store, artifact-refs, clarifications, revision, websocket]

# Dependency graph
requires:
  - phase: 05-03
    provides: default-deny ScopedStore helper (write_ref / list_refs / assert_owns)
  - phase: 05-04
    provides: per-run armed ScopedStore + _dual_write_artifact + typed ArtifactGraph; assert_owns wired above the L16 seed
  - phase: 05-05
    provides: artifact_refs read API + the in-memory-SQLite ScopedStore test bootstrap pattern
provides:
  - "all six thin-store artifact-method consumers (_run_planner planning_context write, _run_agent produces-loop write, _handle_revision cross-run reads + revision write, clarify_engine clarifications write, websocket reconnect clarifications read) migrated onto ScopedStore/artifact_refs"
  - "_handle_revision cross-run parent reads are owner-scoped + assert_owns(parent_run_id)-gated (T-5-SEED); same-owner reads byte-identical (INV-3); no new cross-owner behavior"
  - "clarifications payload now lands in + is read back from artifact_refs (kind=clarifications), ownership-gated end-to-end"
  - "the engine/clarify/websocket surface has ZERO live thin-store artifact-method calls — 05-07's destructive deletion + 0015 DROP now rests on a TRUE precondition"
  - "producer writes carry visibility=workspace so a same-owner cross-run revision resolves them through the owner+visibility scope filter"
affects: [05-07, workflow-runtime-kernel]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cross-run owner-scoped read: _handle_revision reads the PARENT run's artifact_refs via ScopedStore(owner_id), assert_owns-gated, never the per-run in-memory ArtifactGraph (which cannot serve cross-run)"
    - "Transient ArtifactGraph as a dataclass factory: build an ArtifactRef (graph computes id/content_hash/version) then persist via ScopedStore.write_ref — used by _handle_revision + clarify_engine which have no armed per-run graph"
    - "visibility=workspace on cross-run-readable producer artifacts so the owner+visibility scope filter admits same-owner reads regardless of the caller's threaded workspace_id"
    - "Best-effort typed persist folds the old hard-fail produces-loop into the _dual_write_artifact degrade shape (the offline characterization harness has no workflow_runs FK row)"

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/clarify_engine.py
    - backend/app/api/websocket.py
    - backend/tests/unit/test_revision_intelligence.py
    - backend/tests/agents/_scripted_model.py
    - backend/tests/agents/live_harness.py
    - backend/tests/agents/test_phase3_token_delta_live.py
    - backend/tests/agents/test_phase5_revision_validation.py

key-decisions:
  - "Producer writes (planning_context, each produces kind) + the revision write + clarifications use visibility=workspace so a same-owner cross-run _handle_revision read passes _scope_with_visibility even though the cross-run ScopedStore threads no workspace_id (the default 'private' would have silently returned nothing → INV-3 break)"
  - "The revision ArtifactRef lands in the SAME workspace as the parent original (original.workspace_id) — artifact_refs.workspace_id is NOT NULL and ScopedStore.write_ref falls back to its own (None) principal when the ref's workspace is falsy"
  - "_run_agent produces-loop folded from hard-fail (transition→failed + agent_error + return) into best-effort _dual_write_artifact: the old hard-fail was never observable in the 0A snapshots and would break parity on the FK-less harness"
  - "_handle_revision's revision-write error branch broadened from ArtifactStoreWriteError to Exception, preserving the state_restoration_failed emit shape; assert_owns/ValueError guards stay ABOVE the try so PermissionError + validation errors propagate"

patterns-established:
  - "Owner-scoped cross-run artifact read gated by assert_owns(parent_run_id) — the canonical IDOR-safe parent-run read"
  - "Clarifications write/read loop served entirely from artifact_refs; the thin store keeps ONLY the HITL asyncio.Event half live"

requirements-completed: [ART-01, ART-03, PERSIST-02]

# Metrics
duration: ~40min
completed: 2026-06-08
---

# Phase 05 Plan 06: Thin-store Consumer Migration Summary

**Migrated all six live thin-store artifact-method consumers (engine producer writes, `_handle_revision` cross-run reads + revision write, clarify_engine clarifications write, websocket reconnect read) onto the owner-scoped persisted `ScopedStore`/`artifact_refs` layer — assert_owns-gated, byte-identity preserved, leaving ZERO live `self._store.(store|retrieve_latest|...)` calls so 05-07's destructive deletion rests on a TRUE precondition.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-06-08
- **Tasks:** 3 (all auto, all committed atomically)
- **Files modified:** 8 (4 source + 4 test-harness/suite)

## Accomplishments

- **Task 1 — engine producer writes migrated:** `_run_planner` planning_context write and `_run_agent` `produces`-loop write moved off `self._store.store(...)` onto `_dual_write_artifact` (kind=`planning_context` / each declared `produces` kind, `visibility="workspace"`). The produces-loop hard-fail folded into the best-effort degrade. `ectx` threaded into `_run_planner`; `_dual_write_artifact` gained a `visibility` param.
- **Task 2 — `_handle_revision` + websocket reconnect read migrated:** the three cross-run parent reads (`original` / `version_history` / `planning_context`) and the revision write now go through an owner-scoped `ScopedStore` against `artifact_refs`, with `assert_owns(parent_run_id)` gating ABOVE the reads (T-5-SEED). `owner_id` threaded from `user.id` at the WS caller; dict-access → ORM-row attribute access. The websocket reconnect clarifications read moved off `retrieve_latest` onto `ScopedStore.list_refs(kind="clarifications")`. `test_revision_intelligence.py` rewritten to the ScopedStore API + a cross-owner `PermissionError` denial case.
- **Task 3 — clarifications write migrated (loop closed):** `clarify_engine._persist_qa` now writes the clarifications payload into `artifact_refs` (kind=`clarifications`, `visibility="workspace"`) via `ScopedStore`; `owner_id`/`workspace_id` threaded through `ClarifyEngine.run()` from `ectx`. A round-trip test (clarify write → `ScopedStore.list_refs` read-back + non-owner denial) added.
- **Precondition for 05-07 is now TRUE:** `grep -rnE "self\._store\.(store|retrieve_latest|retrieve_version|list_by_type|list_lineage)\(" agents/execution_engine/ app/api/websocket.py` → **0**.

## Task Commits

1. **Task 1: migrate engine producer writes to ScopedStore/artifact_refs** — `c0f9a91` (feat)
2. **Task 2: migrate _handle_revision + websocket clarifications read to owner-scoped ScopedStore** — `2cfa55d` (feat)
3. **Task 3: migrate clarify_engine clarifications write to artifact_refs** — `a7b36e1` (feat)

## Files Created/Modified

- `backend/agents/execution_engine/engine.py` — producer writes migrated (T1); `_handle_revision` owner-scoped reads/write + `owner_id` param + assert_owns gate (T2); `_dual_write_artifact` `visibility` param; clarify.run() owner/workspace threading (T3); `ArtifactGraph` import; dropped unused `ArtifactStoreWriteError` import.
- `backend/agents/execution_engine/clarify_engine.py` — `_persist_qa` writes clarifications to `artifact_refs` via ScopedStore; `run()`/`__init__` thread+stash owner_id/workspace_id (T3).
- `backend/app/api/websocket.py` — reconnect clarifications read off the thin store → `ScopedStore.list_refs`; `owner_id=user.id` passed to `_handle_revision`; removed the now-dead `_get_store()` acquisition (T2).
- `backend/tests/unit/test_revision_intelligence.py` — rewritten to the ScopedStore/artifact_refs API (in-memory SQLite, SessionLocal monkeypatch) + cross-owner denial + clarifications round-trip (9 tests, was 7).
- `backend/tests/agents/_scripted_model.py`, `live_harness.py`, `test_phase3_token_delta_live.py`, `test_phase5_revision_validation.py` — `_fake_run_planner` / `_forced_run_planner` shims accept `**kwargs` (Task 1 signature consequence).

## Decisions Made

See `key-decisions` frontmatter. Headline: producer/revision/clarifications writes use `visibility="workspace"` so a same-owner cross-run `_handle_revision` read resolves through the owner+visibility scope filter — the `"private"` default would silently return nothing and break INV-3 byte-identity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `_run_planner` signature-change broke four `_fake`/`_forced` planner harness shims**
- **Found during:** Task 1 (then a second shim surfaced in the Task 3 broad sweep)
- **Issue:** Threading `ectx` into `_run_planner` (called as `ectx=ectx`) broke the positional-only `_fake_run_planner` (×3) and `_forced_run_planner` (×1) test overrides → `TypeError: unexpected keyword argument 'ectx'` across the characterization suite + the offline clarify-harness suites.
- **Fix:** Added `**kwargs` to all four shims (`_scripted_model.py`, `test_phase3_token_delta_live.py`, `test_phase5_revision_validation.py`, `live_harness.py`).
- **Verification:** characterization suite (10) + offline live-harness/contract variants (11) green.
- **Committed in:** `c0f9a91` (3 shims) + `a7b36e1` (the 4th `_forced_run_planner`).

**2. [Rule 2 - Missing critical] `visibility="workspace"` on cross-run-readable writes**
- **Found during:** Task 2 (the rewritten revision suite hit empty cross-run reads)
- **Issue:** The default `visibility="private"` makes `_scope_with_visibility` require `workspace_id == self._workspace_id`; the cross-run `ScopedStore(owner_id=...)` threads no workspace_id, so same-owner reads returned NOTHING → INV-3 byte-identity break (the plan asserted the visibility default admits owner reads, but the on-disk default is `private`).
- **Fix:** Producer writes (planning_context, each `produces` kind), the revision write, and the clarifications write all set `visibility="workspace"`; the revision ref also inherits `original.workspace_id` (NOT NULL constraint).
- **Verification:** revision suite (9) green incl. cross-run reads + cross-owner denial; clarifications round-trip green.
- **Committed in:** `c0f9a91` / `2cfa55d` / `a7b36e1`.

**3. [Rule 1 - Bug] `_handle_revision` revision-write error branch broadened**
- **Found during:** Task 2
- **Issue:** The old branch caught only `ArtifactStoreWriteError` (thin-store specific); the typed `ScopedStore.write_ref` raises generic DB exceptions, which would have escaped the `state_restoration_failed` emit.
- **Fix:** Broadened to `except Exception` (assert_owns/ValueError guards stay ABOVE the try, so `PermissionError` + validation errors still propagate).
- **Verification:** cross-owner test asserts `PermissionError` propagates; happy-path emits `pipeline_complete`.
- **Committed in:** `2cfa55d`.

**4. [Plan-action narrowing] `_run_agent` produces-loop folded from hard-fail into best-effort**
- **Found during:** Task 1
- **Issue:** The old produces-loop transitioned the run to `failed` + yielded `agent_error` + returned on write failure. The plan flagged this to keep ONLY if observable in 0A snapshots; it is not, and the FK-less characterization harness would hard-fail every run.
- **Fix:** Folded into the best-effort `_dual_write_artifact` degrade.
- **Verification:** characterization suite green (no `agent_error` regression).
- **Committed in:** `c0f9a91`.

---

**Total deviations:** 4 (1 blocking harness fix, 1 missing-critical visibility, 1 bug, 1 plan-action narrowing). All required for correctness/parity. No scope creep; thin store NOT deleted (that's 05-07).

## Issues Encountered

- **Pre-existing environmental test failures (out of scope, NOT chased):** `tests/unit/test_logout.py` (7 — self-registration disabled → 403) and `tests/unit/test_pipeline_cancel.py` (1 — expired AWS Bedrock token). Both predate this plan.
- **Pre-existing ruff** `F841` (`inferred_intent` in `clarify_engine._generate_questions`) + `B023` (`_rev_target_type` closure in `websocket.py`, line shifted by my reconnect-block edits) — logged to `deferred-items.md` per the SCOPE BOUNDARY rule.
- The full `test_live_harness.py`/`test_live_contract.py` files include non-offline SSO/Bedrock-gated tests that hang without credentials; the OFFLINE variants (which were the only ones that regressed) are green.

## Verification Results

- Surface grep `self._store.(store|retrieve_latest|retrieve_version|list_by_type|list_lineage)\(` over `agents/execution_engine/ app/api/websocket.py` — **0** (05-07 precondition TRUE).
- `assert_owns(parent_run_id)` present inside `_handle_revision` (engine.py:2637) — T-5-SEED gate.
- `tests/unit/test_revision_intelligence.py` — **9 passed** (ScopedStore API + cross-owner denial + clarifications round-trip).
- `tests/agents/test_characterization_*.py` — **10 passed** (byte-identity + semantic-event parity, incl. prototype_revision + ppt — INV-3).
- Offline live-harness/contract clarify variants — **11 passed**.
- Broad sweep `tests/agents/ tests/unit/` — **942 passed, 19 skipped**; only the 2 documented environmental suites failed (8 tests, pre-existing); the 2 clarify-harness regressions fixed.
- `cd backend && lint-imports` — **exit 0** (3 contracts kept; clarify_engine's new `agents.authz`/`agents.artifacts` imports are kernel-safe).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **05-07** can now perform the parity-gated DESTRUCTIVE deletion of the thin-store artifact methods (`store`/`retrieve_latest`/`retrieve_version`/`list_by_type`/`list_lineage`/`_store_in_memory`/`_to_dict`) + the `0015` DROP of `workflow_artifacts` — the precondition (zero live consumers) is proven TRUE. The HITL `asyncio.Event` half of the thin store stays untouched.
- The `accumulated_outputs` mirror is still live (the sanctioned temporary duplication) and is also a 05-07 concern.

## Known Stubs

None. The thin-store artifact methods remain physically present-but-unused on these paths (their deletion is the explicit job of 05-07); this is the documented additive-migration state, not a stub.

## Self-Check: PASSED

All modified files present on disk; all 3 task commits (`c0f9a91`, `2cfa55d`, `a7b36e1`) present in git log.

---
*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Completed: 2026-06-08*

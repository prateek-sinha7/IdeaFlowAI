---
phase: 05-typed-artifacts-persistence-ownership-1b
plan: 07
subsystem: engine
tags: [execution-engine, artifacts, persistence, deletion, strangler-cutover, migration-ledger, alembic, hitl]

# Dependency graph
requires:
  - phase: 05-06
    provides: all six thin-store artifact-method consumers migrated to ScopedStore/artifact_refs (zero live consumers) + visibility=workspace producer writes
  - phase: 05-04
    provides: per-run typed ArtifactGraph + _dual_write_artifact + the accumulated_outputs mirror this plan deletes
provides:
  - "the accumulated_outputs mirror is DELETED — ExecutionContext.accumulated_outputs field gone, the local prior-output dict gone, the typed ArtifactGraph is the SOLE prior-agent output source (INV-3/INV-12); ledger L15 ☑"
  - "the thin-store artifact-persistence half (store/retrieve_latest/retrieve_version/list_by_type/list_lineage/_store_in_memory/_to_dict + _use_db/_mem_* + ArtifactStoreWriteError) + WorkflowArtifact model + workflow_artifacts table are DELETED; ledger D2 ☑"
  - "the in-memory asyncio.Event HITL half of the store is KEPT (get_resume_event/set+get_questionnaire_responses/get_review_event/set+get_review_response + get_artifact_store) — websocket submit_questionnaire/approve_review + engine review gate still work"
  - "alembic 0015 drops workflow_artifacts (reversible — downgrade recreates the table + index), sequenced LAST (down_revision=0014)"
  - "build-loop scratch (_build_task_number/_build_task_total) relocated off the deleted dict onto ectx.build_task_number/build_task_total (a non-artifact home)"
  - "ONE artifact implementation remains — phase 05 is DONE per INV-3/INV-12 (deletion-as-exit-gate)"
affects: [workflow-runtime-kernel, phase-7-task-loop-strategy, phase-8-hitl]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deletion-as-exit-gate: a parity-gated [BLOCKING] gate (zero live consumers proven by grep + 0A characterization byte+event parity GREEN) precedes any destructive removal; deletion split into mirror-removal then thin-store-removal with a test run between"
    - "Typed-only reads: _latest_typed_content/_filter_consumed_outputs/_build_context_sources read solely from ectx.artifacts (the mirror fallback param dropped)"
    - "Grep-ratchet gate authored on the deleted MODEL IMPORT PATH (from app.models.artifact import) rather than the table-name literal, because the table name is load-bearing in the 0010 create + 0015 drop migrations (non-vacuous → 0)"

key-files:
  created:
    - backend/alembic/versions/0015_drop_thin_artifact_store.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/context.py
    - backend/agents/artifact_store/store.py
    - backend/agents/artifacts/graph.py
    - backend/app/models/workflow.py
    - backend/app/models/__init__.py
    - backend/app/models/artifact_ref.py
    - specs/003-workflow-engine-decoupling/migration-ledger.md
    - backend/tests/agents/test_migration_ledger.py
    - backend/tests/conftest.py
    - backend/tests/unit/test_artifact_store.py
    - backend/tests/agents/test_execution_context.py
    - backend/tests/agents/test_phase3_compaction.py
    - backend/tests/agents/test_phase3_cutover_verify.py
    - backend/tests/agents/test_phase3_token_delta_live.py
    - backend/tests/agents/test_phase4_build_loop.py
    - backend/tests/unit/test_agent_input_event.py
    - backend/tests/unit/test_resumability.py
    - backend/tests/unit/test_execution_engine.py
    - backend/tests/integration/test_performance.py
  deleted:
    - backend/app/models/artifact.py
    - backend/tests/unit/test_artifact_store_fk.py

key-decisions:
  - "The accumulated_outputs mirror that L15 names was the ExecutionContext.accumulated_outputs FIELD (zero dot-access — already dead) PLUS the local prior-output dict threaded through the pipeline. Removed the field; renamed/removed the local dict; the dict's per-agent CONTENT writes were already redundant (the typed graph dual-write held the same content), so they were dropped and the build-loop scratch keys moved onto ectx (non-artifact home)."
  - "Dropped the `mirror` fallback parameter from _latest_typed_content/_filter_consumed_outputs/_build_context_sources (typed-ONLY reads) per the plan — the Task 1 parity gate proved the typed graph returns identical content."
  - "D2 grep gate authored on `from app\\.models\\.artifact import` (the deleted model import path) NOT `WorkflowArtifact|workflow_artifacts`: the table name is required literally in the 0010 create + 0015 drop migrations + 0013/0014 prose, so a bare-name gate could never be 0. The import-path is the precise, non-vacuous deletion signature → 0 in *.py."
  - "PRESERVED the 05-06 visibility=workspace producer-write deviation (the `private` default would starve cross-run revision reads and break INV-3) — untouched."
  - "Replaced the thin-store unit suite with an HITL-only suite; deleted the workflow_artifacts FK regression + its now-unused conftest fk_session/make_fk_sqlite_engine fixture (removing new dead code vulture would flag); rewired the SC-008 clarification-restore perf test onto the typed ScopedStore.list_refs path (clarifications persist in artifact_refs since 05-06)."

patterns-established:
  - "Parity-gated destructive deletion: prove zero-consumers (grep) + byte/event parity (characterization) BEFORE removing; never ship-with-mirror-alive."
  - "Reversible non-additive migration: a DROP whose downgrade() recreates the original column shape + index (Q3 reversibility), verified by an upgrade/downgrade/re-upgrade roundtrip."

requirements-completed: [PERSIST-02]

# Metrics
duration: ~55min
completed: 2026-06-08
---

# Phase 05 Plan 07: Final Parity-Gated Deletion (Strangler Cutover) Summary

**Completed the strangler cutover (PERSIST-02, D-13 step 5): with the [BLOCKING] parity gate GREEN (zero live thin-store consumers + 0A characterization byte+event parity), DELETED the `accumulated_outputs` mirror (ledger L15 ☑), DELETED the thin-store artifact-persistence half + `WorkflowArtifact` model + the `workflow_artifacts` table via reversible alembic `0015` (ledger D2 ☑), KEPT the in-memory `asyncio.Event` HITL half, and updated the ledger flip set to {D2,L14,L15,L16}. One artifact implementation remains — phase 05 is DONE (INV-3/INV-12).**

## Performance

- **Duration:** ~55 min
- **Completed:** 2026-06-08
- **Tasks:** 3 (Task 1 BLOCKING gate; Tasks 2-3 destructive deletion, committed atomically)
- **Files:** 1 created, 20 modified, 2 deleted

## Accomplishments

- **Task 1 — [BLOCKING] parity gate GREEN before any deletion:** (a) `grep -rnE "self\._store\.(store|retrieve_latest|retrieve_version|list_by_type|list_lineage)\(" agents/execution_engine/ app/api/websocket.py` → **0** (precondition TRUE — 05-06 migration complete); (b) the full 0A characterization + migration-ledger + parent-ownership + artifact_graph + 0014 + run_events/capabilities + runs_api + revision suites → **65 passed**. Deletion proceeded only after BOTH green.
- **Task 2 / Commit A (`aa68dc9`) — mirror deleted:** removed `ExecutionContext.accumulated_outputs`; removed the local prior-output dict + its threading through `_run_agent`/`_run_build_task_loop`/`_build_context_message`/`_run_review_gate`/`_write_build_reference_files`; dropped the `mirror` fallback param from the three typed-read helpers (typed-ONLY); moved `_build_task_number`/`_build_task_total` scratch onto `ectx`. Characterization byte+event parity GREEN after removal; `accumulated_outputs` grep → 0 across all of backend.
- **Task 2 / Commit B (`26863bc`) — thin-store artifact half + model deleted:** trimmed `store.py` to the HITL-only registry (KEEP `get_resume_event`/`set+get_questionnaire_responses`/`get_review_event`/`set+get_review_response` + `get_artifact_store`); deleted `app/models/artifact.py` (`WorkflowArtifact`); dropped the `WorkflowRun.artifacts` relationship + the `__init__` import. HITL/resumability/exec-engine + characterization suites GREEN; lint-imports 0; vulture clean.
- **Task 3 / Commits `bdd9909` + `ddfdc06` — 0015 DROP + ledger:** hand-authored `0015_drop_thin_artifact_store.py` (down_revision=0014, reversible — verified upgrade/downgrade/re-upgrade SQLite roundtrip); flipped ledger L15 ☑ + added the D2 thin-store deletion gate row; updated `test_migration_ledger.py` (`_REQUIRED_ITEMS` += D2; flip-set assertion → {D2,L14,L15,L16}).

## Task Commits

1. **Commit A — delete accumulated_outputs mirror** — `aa68dc9` (refactor)
2. **Commit B — delete thin-store artifact half + WorkflowArtifact (keep HITL)** — `26863bc` (refactor)
3. **0015 drop workflow_artifacts** — `bdd9909` (feat)
4. **Flip L15 + add D2 gate; ledger flip set {D2,L14,L15,L16}** — `ddfdc06` (test)

## Files Created/Modified/Deleted

See `key-files` frontmatter. Headline: `0015` created; `engine.py`/`context.py`/`store.py` carry the deletions; `migration-ledger.md` + `test_migration_ledger.py` carry the L15/D2 flip; `artifact.py` + `test_artifact_store_fk.py` deleted.

## Decisions Made

See `key-decisions` frontmatter. Headline: the L15 "mirror" was the `ExecutionContext` field (already dead) + the local prior-output dict; the typed graph already held identical content (dual-written, gate-proven), so the dict's content writes were dropped and only the build-loop scratch was relocated onto `ectx`. The D2 grep gate targets the deleted model import path (not the table-name literal that is load-bearing in migrations) so the ratchet is non-vacuous → 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] D2 ledger gate pattern changed from the planned `WorkflowArtifact|workflow_artifacts` to `from app\.models\.artifact import`**
- **Found during:** Task 3 (running the ledger ratchet)
- **Issue:** The plan suggested a `WorkflowArtifact`/`workflow_artifacts` grep gate. But that table name is REQUIRED literally in `0010_artifact_store.py` (CREATE) and `0015_drop_thin_artifact_store.py` (DROP + downgrade recreate), plus 0013/0014 prose — so a bare-name grep over `backend/ *.py` can NEVER return 0. The ratchet would always fail.
- **Fix:** Authored the gate on `from app\.models\.artifact import` — the precise import-path of the deleted `WorkflowArtifact` model, which is genuinely absent (→ 0) and is the canonical "this model is gone" signature.
- **Verification:** `test_migration_ledger.py` green (D2 ratchet → 0; non-vacuity guard still proves the machinery fires).
- **Committed in:** `ddfdc06`.

**2. [Rule 2 - Missing critical] Deleted the now-unused conftest `fk_session`/`make_fk_sqlite_engine` fixture + rewired the SC-008 perf test**
- **Found during:** Task 2 / Commit B (collection errors in `test_artifact_store.py`/`test_artifact_store_fk.py`; lingering `ArtifactStore(use_db=False)` + `retrieve_latest` callers)
- **Issue:** Deleting the thin-store artifact half orphaned its tests: `test_artifact_store_fk.py` (FK regression on the dropped table), the artifact-method tests in `test_artifact_store.py`, and `conftest.fk_session` (its sole consumer). Five `ArtifactStore(use_db=False)` constructions + one `store.retrieve_latest(...)` perf call referenced the deleted API. Leaving these would fail collection and leave new dead code (vulture).
- **Fix:** Rewrote `test_artifact_store.py` as an HITL-only suite (resume/questionnaire/review-gate + singleton); deleted `test_artifact_store_fk.py` + the unused `fk_session`/`make_fk_sqlite_engine`; replaced `ArtifactStore(use_db=False)` → `ArtifactStore()`; rewired the SC-008 clarification-restore perf test onto `ScopedStore.list_refs` (clarifications persist in `artifact_refs` since 05-06).
- **Verification:** HITL/resumability/exec-engine + 451-test unit sweep + 387-test agents sweep GREEN; vulture reports no new dead code.
- **Committed in:** `26863bc`.

**3. [Rule 3 - Blocking] Test-harness signature consequences of the mirror removal**
- **Found during:** Task 2 / Commit A
- **Issue:** Dropping the `accumulated_outputs` param from `_run_agent`/`_run_build_task_loop`/`_build_context_message`/`_build_context_sources`/`_write_build_reference_files` broke positional callers/spies in `test_phase4_build_loop.py`, `test_phase3_cutover_verify.py`, `test_phase3_compaction.py`, `test_phase3_token_delta_live.py`, `test_agent_input_event.py`, and an `ectx.accumulated_outputs` assertion in `test_execution_context.py`.
- **Fix:** Updated each test to seed upstream content into `ectx.artifacts` (the sole source) and read scratch from `ectx.build_task_*`; dropped the obsolete dict args; updated the build-loop spy signature; removed the dead `engine._store.store` monkeypatch (the typed write degrades best-effort on the FK-less harness).
- **Verification:** all six suites GREEN (characterization 10/10 byte+event parity preserved).
- **Committed in:** `aa68dc9`.

---

**Total deviations:** 3 (1 gate-pattern correction, 1 missing-critical test cleanup, 1 blocking harness fix). All required for correctness/parity. No scope creep.

## Issues Encountered

- **Pre-existing environmental test failures (out of scope, NOT chased):** `tests/agents/test_logout.py` (self-registration disabled → 403) and `tests/agents/test_pipeline_cancel.py` (expired AWS Bedrock token) — both predate this plan (documented in 05-06). The live/SSO-gated suites (`test_phase3_token_delta_live.py`, `test_phase5_revision_validation.py` live tests, `test_performance.py` `@requires_api_key`) hang without credentials and were excluded from the broad sweeps; their collection (imports/signatures) was verified clean.

## Verification Results

- Task 1 [BLOCKING] gate: thin-store-consumer grep → **0**; parity+correctness suite → **65 passed, 1 skipped**.
- `cd backend && grep -rn "accumulated_outputs" agents app` → **0** (non-test); whole-backend `*.py` → **0** (L15 ratchet target).
- `from app.models.artifact import` whole-backend `*.py` → **0** (D2 ratchet target).
- Thin-store artifact half deleted (`grep -E "def (store|retrieve_latest|retrieve_version|list_by_type|list_lineage)\b" agents/artifact_store/store.py` → 0); HITL half intact (`get_resume_event|set_questionnaire_responses|get_review_event|set_review_response` ≥ 4); `app/models/artifact.py` absent; `WorkflowArtifact` not in `__init__`.
- `alembic upgrade head` applies `0015` cleanly; `downgrade 0014` recreates `workflow_artifacts` + index; re-upgrade re-drops — full reversible roundtrip on SQLite.
- `test_migration_ledger.py` → **6 passed, 1 skipped** (flip set {D2,L14,L15,L16}; L15 + D2 grep ratchets → 0; non-vacuity guard live; L16 CHECK row skipped).
- Characterization STILL GREEN after all deletions (**10 passed** — byte-identity + semantic-event parity for prototype/od_prototype/prototype_revision/ppt/code-gen).
- `cd backend && lint-imports` → **exit 0** (3 contracts kept). `vulture app/ agents/` → no new dead-code from the deletions.
- Broad sweeps: `tests/unit/` (minus gated) **451 passed**; `tests/agents/` (minus live) **387 passed, 1 skipped**.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Phase 05 is DONE (INV-3/INV-12):** the typed `ArtifactGraph` + persisted `artifact_refs` layer is the SOLE artifact implementation; the mirror and thin store are gone; the deletion ratchets (L15 bare-token + D2 import-path) are permanent CI gates.
- The HITL `asyncio.Event` half of the store is preserved for **Phase 8** (HITL ownership). The build-loop scratch (`current_task_block`/`build_task_number`/`build_task_total`) on `ectx` is the documented D-02 temporary home for **Phase 7**'s `TaskLoopStrategy`.

## Known Stubs

None. The deletion is complete — no placeholder/empty-value stubs introduced.

## Self-Check: PASSED

- Created `backend/alembic/versions/0015_drop_thin_artifact_store.py` — FOUND on disk.
- Deleted `backend/app/models/artifact.py` — confirmed GONE.
- All four task commits present in git log: `aa68dc9`, `26863bc`, `bdd9909`, `ddfdc06`.

---
*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Completed: 2026-06-08*

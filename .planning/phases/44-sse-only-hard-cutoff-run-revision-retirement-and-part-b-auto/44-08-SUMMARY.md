---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 08
subsystem: testing
tags: [websocket, sse, rest, transport-cutover, test-migration, idor, inv-3]

# Dependency graph
requires:
  - phase: 44-07
    provides: "/ws/chat + app/api/websocket.py deleted; the transport-neutral seams (_get_db, _validate_model_overrides, _revalidate_selections_trust_user, _resolve_owned_parent_run_id, _review_gate_owned_by) relocated to app/api/run_engine.py"
provides:
  - "The backend WS-endpoint tests that drove the deleted /ws/chat handlers are migrated to their REST twins or deleted — zero test imports app.api.websocket"
  - "Unique WS coverage preserved on REST: parent-link resolver contract + run_pipeline IDOR (Site 1) + run-entry image ingress + D3 no-base64"
  - "tests/agents/ + tests/unit/ collect with ZERO collection errors (was 3)"
affects: [phase-44-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Transport-retirement test migration: a WS driver test either (a) migrates its transport-neutral assertions to the REST twin via TestClient POST, (b) repoints a relocated-symbol import to run_engine, or (c) is deleted when a KEPT SSE/REST suite already supersedes it — never ports a FakeWebSocket"
    - "Security-assertion migration before deletion (T-44-08-01): the parent-link ownership (IDOR) cases were folded into test_rest_revisions.py + test_rest_run_launch.py BEFORE test_ws_parent_link_ownership.py was deleted; grep-proven no coverage loss"

key-files:
  created: []
  modified:
    - "backend/tests/unit/test_rest_revisions.py (added TestResolverDirect — the owner-checked parent-link resolver contract)"
    - "backend/tests/unit/test_rest_run_launch.py (added Site-1 run_pipeline parent-link IDOR: owned links, foreign/unknown drop the edge but still launch)"
    - "backend/tests/unit/test_image_ws_ingress.py (deleted WS half; repointed harness to run_engine; carries run-entry image ingress + D3 over the REST launch endpoint)"
    - "backend/tests/unit/test_run_message_images.py (repointed _get_db seam to run_engine)"
    - "backend/tests/unit/test_pipeline_failure_semantics.py (deleted WS ingress-guard half; kept the engine-level terminal-semantics tests)"
    - "backend/tests/unit/test_capabilities_api.py (repointed the additive-event forward pin from websocket to run_stream._sse_body)"
    - "backend/tests/unit/test_approve_review_ownership.py (dropped the superseded WS-source approve_review pin; predicate tests already on run_engine)"
    - "backend/tests/unit/test_user_workflows_selections.py, test_run_pipeline_validation.py, test_chat_messages_endpoint.py, test_concierge_proposal_channels.py, test_run_files_upload.py (repointed app.api.websocket imports to app.api.run_engine)"
  deleted:
    - "backend/tests/unit/test_pipeline_cancel.py (superseded by test_rest_answers_cancel.py)"
    - "backend/tests/unit/test_run_revision_ws_dispatch.py (migrated to test_rest_revisions.py)"
    - "backend/tests/unit/test_ws_parent_link_ownership.py (migrated to test_rest_revisions.py + test_rest_run_launch.py)"
    - "backend/tests/agents/test_ws_reconnect_replay.py (superseded by test_sse_stream.py + test_attach_replay_matrix.py)"

key-decisions:
  - "Cancel coverage needed NO additions to test_rest_answers_cancel.py — the twin already carries the migratable assertions (cooperative event set, idempotent ack, cross-owner 404); the WS test's overlapping-run/disconnect/engine-crash cases are WS-connection-lifecycle-specific (no stateless REST equivalent) and the terminal transition is characterization-golden territory"
  - "test_image_ws_ingress.py was KEPT (WS half deleted) rather than whole-file deleted — its in-file REST section is the ONLY run-entry image-ingress REST coverage (test_rest_run_launch.py tests no images); folding it elsewhere would be pure churn"
  - "The missing_template_context ingress guard is a SRC gap, not a test gap — it was deleted with websocket.py (44-07) and never re-homed on REST; a tests-only plan cannot close it (see DEF-44-08-1)"

patterns-established:
  - "The parity oracle (test_wire_parity.py) + SSE target-state suites (test_sse_stream.py, test_attach_replay_matrix.py) + the 5 characterization goldens are the deletion gate — never gate a transport retirement on the deleted endpoint's own tests"

requirements-completed: [W5, "INV-3"]

# Metrics
duration: ~45 min
completed: 2026-07-15
---

# Phase 44 Plan 08: W5b Backend WS-Test Migration to REST Summary

**Migrated the /ws/chat-driver backend tests onto their REST twins (cancel, revision dispatch, parent-link IDOR, run-entry image ingress + D3), deleted the four superseded/migrated WS-only suites, and repointed every remaining `app.api.websocket` import to `run_engine` — clearing all 3 collection errors while keeping the parity oracle + SSE suites + 5 goldens byte/event-identical.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-07-15
- **Tasks:** 3 (2 with atomic commits; Task 3 verification-only)
- **Files:** 12 modified, 4 deleted

## Accomplishments
- **Migrated the unique, transport-neutral coverage** off the deleted `_handle_workflow_execution` / `_handle_revision_execution` WS drivers onto the REST twins:
  - parent-link **resolver contract** (owned→id; foreign/missing→None; falsy→None with NO query) → `test_rest_revisions.py::TestResolverDirect`;
  - the **run_pipeline parent-link IDOR** (Site 1) → `test_rest_run_launch.py` (owned source links the child; a foreign/unknown source has its edge DROPPED to None but the run still launches — the WS Site-1 contract, no leak);
  - **run-entry image ingress + D3** (no base64 in `WorkflowRun.input`/`title`) → over the REST launch endpoint in `test_image_ws_ingress.py`.
- **Deleted the four obsolete WS-only suites** (cancel, revision-dispatch, parent-link, reconnect-replay) whose handlers no longer exist, each superseded by a KEPT REST/SSE suite.
- **Repointed every remaining `app.api.websocket` import** (module-level + in-function fixtures + two source-inspection pins) to `app.api.run_engine` / `app.api.run_stream` — the 44-03 relocation targets — clearing all collection + ImportError reds.
- **Proved INV-3:** the 5 characterization goldens (10 passed) + `test_wire_parity.py` (6 passed) stayed byte/event-identical after the migration; SSE suites 27 passed; `lint-imports` 4 kept / 0 broken.

## Task Commits

1. **Task 1: Fold WS cancel/revision/image coverage into the REST twins** — `59f33f96` (test)
2. **Task 2: Delete obsolete WS-only tests + repoint deleted-module imports** — `f30b841a` (test)
3. **Task 3: Confirm the parity oracle + SSE suites + goldens stay green** — verification-only (no file change; results below)

## Files Created/Modified
See frontmatter `key-files`. Net: 12 test files modified (folds + repoints), 4 test files deleted (superseded/migrated).

## Per-test disposition (CONTEXT §5 table + 44-07's break-as-expected list)

| Test | Disposition | REST twin / target |
|---|---|---|
| `test_pipeline_cancel.py` | **DELETED** (migrated) | `test_rest_answers_cancel.py` (cancel ack + cross-owner already covered; LV-01 `wait_for` flake dropped) |
| `test_run_revision_ws_dispatch.py` | **DELETED** (migrated) | `test_rest_revisions.py` (6 dispatch scenarios already covered) |
| `test_ws_parent_link_ownership.py` | **DELETED** (migrated) | `test_rest_revisions.py::TestResolverDirect` + endpoint 404 + `test_rest_run_launch.py` Site-1 |
| `test_ws_reconnect_replay.py` | **DELETED** (superseded) | `test_sse_stream.py` + `test_attach_replay_matrix.py` |
| `test_image_ws_ingress.py` | **MIGRATED** (WS half deleted; REST section kept + D3 added) | in-file REST launch cases |
| `test_pipeline_failure_semantics.py` | **MIGRATED** (WS guard half deleted; engine terminal half kept) | — (guard is a SRC gap, see DEF-44-08-1) |
| `test_run_message_images.py` | **IMPORT-REPOINT** | `run_engine` |
| `test_user_workflows_selections.py` | **IMPORT-REPOINT** | `run_engine._revalidate_selections_trust_user` |
| `test_run_pipeline_validation.py` | **IMPORT-REPOINT** | `run_engine._validate_model_overrides` (12 pre-existing agent-pool reds remain) |
| `test_capabilities_api.py` | **REPOINT + assertion update** | `run_stream._sse_body` (additive-event forward moved to SSE) |
| `test_approve_review_ownership.py` | **REPOINT + drop superseded pin** | predicate on `run_engine`; source-order pin now in `test_rest_gate_commands.py` |
| `test_chat_messages_endpoint.py`, `test_concierge_proposal_channels.py`, `test_run_files_upload.py` | **IMPORT-REPOINT** | `run_engine._get_db` |
| `test_wire_parity.py`, `test_sse_stream.py`, `test_attach_replay_matrix.py`, `test_rest_*` twins, `test_handoff_contract.py`, `test_resume_ws_bridge.py` | **KEPT untouched** | — |

## Decisions Made
See frontmatter `key-decisions`. Notably: cancel needed no additions (twin complete); `test_image_ws_ingress.py` kept for its unique REST run-entry image coverage; the `missing_template_context` guard is a SRC gap not closable by a tests-only plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repointed four deleted-module imports NOT enumerated in the plan's files**
- **Found during:** Task 2
- **Issue:** Beyond the plan's explicit import-repoint bucket, four fixtures still imported the deleted `app.api.websocket` (`test_chat_messages_endpoint.py`, `test_concierge_proposal_channels.py`, `test_run_files_upload.py`, `test_run_message_images.py`) — 56 runtime `ImportError`s. Left unfixed they would be residual reds beyond the sanctioned 12.
- **Fix:** repointed each `from app.api import websocket as ws_module` → `run_engine` (the seam the source endpoints already bind `_get_db` from); updated two stale comments.
- **Files modified:** the four files above.
- **Verification:** all four green (0 ImportError).
- **Committed in:** `f30b841a` (test_run_message_images repoint in `59f33f96`).

**2. [Rule 2 - Missing critical] Migrated the run_pipeline parent-link IDOR (Site 1) to test_rest_run_launch.py**
- **Found during:** Task 1
- **Issue:** `test_ws_parent_link_ownership.py` pinned the PRIMARY IDOR path (`source_workflow_run_id` chaining) at the deleted WS Site 1. `test_rest_run_launch.py` had NO parent-link coverage — deleting the WS test without this would drop a security assertion (threat T-44-08-01). `test_rest_run_launch.py` is not in the plan's `files_modified`.
- **Fix:** added 3 tests exercising `run_commands.py::launch_run`'s `_resolve_owned_parent_run_id(db, source_workflow_run_id, current_user.id)` — owned links, foreign/unknown drop the edge but still launch.
- **Files modified:** `backend/tests/unit/test_rest_run_launch.py`.
- **Verification:** 3 new tests pass; resolver contract also pinned in `test_rest_revisions.py::TestResolverDirect`.
- **Committed in:** `59f33f96`.

**3. [Rule 1 - Obsolete/misdirected pins] Repointed two WS-source-inspection tests off the deleted module**
- **Found during:** Task 2
- **Issue:** `test_capabilities_api.py::test_new_event_types_need_no_websocket_edit` and `test_approve_review_ownership.py::test_approve_review_branch_gates_...` inspected `websocket.py` source for patterns (`"type": event["type"]`, the `msg_type == "approve_review"` receive-loop branch) that no longer exist. A blind alias-repoint to `run_engine` would leave them asserting against the wrong module.
- **Fix:** repointed the additive-event pin to `run_stream._sse_body` (where the type-agnostic forward now lives) with an updated assertion; deleted the approve_review source-pin (superseded by `test_rest_gate_commands.py`'s ownership-before-write pin) and removed its now-unused `re`/`Path` imports.
- **Files modified:** `test_capabilities_api.py`, `test_approve_review_ownership.py`.
- **Verification:** both files green.
- **Committed in:** `f30b841a`.

---

**Total deviations:** 3 auto-fixed (1 blocking import repoint, 1 missing-critical security migration, 1 obsolete-pin correction).
**Impact on plan:** all necessary to satisfy the plan's own acceptance (no deleted-module imports; parent-link ownership preserved before deletion; no FakeWebSocket). No scope creep — every change is a test-only consequence of the 44-07 deletion + 44-03 seam relocation.

## Issues Encountered
- **🔴 SRC GAP — `missing_template_context` ingress guard was deleted, not re-homed on REST (DEF-44-08-1).** The guard lived only in the deleted `websocket.py` ingress (`engine.py:5265` confirms). The REST launch path has no equivalent, so a bare `prototype` REST launch is no longer rejected pre-mint. This is a behavioral regression introduced by 44-07's whole-file deletion. A tests-only plan cannot close it (a REST guard test would be RED). Removed the WS-half guard tests; kept the engine-level terminal half. **Follow-up SRC plan needed** to re-home the guard in `run_commands.py::launch_run` + add its REST test. Full detail in `deferred-items.md` DEF-44-08-1.

## Verification Results
- `pytest tests/agents/ -k characterization` → **10 passed** (goldens byte-identical, INV-3).
- `pytest tests/agents/test_wire_parity.py` → **6 passed** (SSE frames == frozen WS goldens).
- `pytest tests/unit/test_sse_stream.py tests/agents/test_attach_replay_matrix.py` → **27 passed**.
- `pytest` migrated twins (`test_rest_answers_cancel/revisions/run_launch/run_message_images` + `test_image_ws_ingress`) → **70 passed**.
- `pytest` repointed + failure + gate + resume suites → **118 passed**.
- `pytest tests/agents/ tests/unit/ --co --continue-on-collection-errors` → **2506 collected, 0 collection errors** (was 2503 / 3 errors).
- `pytest tests/agents/ tests/unit/ --continue-on-collection-errors -q` (FULL run) → **82 failed, 2398 passed, 26 skipped, 0 collection errors** in 6m30s. Failure breakdown proves ZERO regressions from this plan:
  - **12** in `test_run_pipeline_validation.py` — the sanctioned pre-existing agent-pool-membership `AssertionError`s (custom-pool widening on feat/ui-2), NOT transport-related.
  - **70** in files this plan NEVER touched (`test_id_alias_resolver`, `test_manifest_parity`, `test_registry_helpers`, `test_factory_injects`, `test_logout`, `test_live_*`, `test_phase8_live`, `test_alembic`, `test_migrations`, etc.) — the same agent-pool/registry/manifest-widening state + live-Bedrock/Postgres/alembic env-gated suites, all pre-existing on the branch.
  - **Proof of no regression:** this plan's two commits (`git diff --name-only 59f33f96~1 f30b841a`) touched ONLY `backend/tests/` files (zero source, zero conftest). Since test-file outcomes are a pure function of (that file + its source imports + shared fixtures), untouched files are bit-identical to before. Every one of my 12 touched files is green EXCEPT the 12 known `test_run_pipeline_validation` reds.
- `grep -rln "FakeWebSocket|_ScriptedLoopWebSocket|routeWebSocket" tests` → **0 files**.
- `grep app.api.websocket in tests` → only a string-literal assertion in `test_resume_ws_bridge.py` (a KEEP guard checking the module is NOT imported).
- `/opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**.
- Migration chain unchanged (latest **0025**, no new migration).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave-6 backend test surface is clean: no test drives a deleted WS handler; the REST/SSE suites carry the migrated coverage; the parity oracle + goldens remain the deletion gate.
- **Open for a SRC follow-up:** DEF-44-08-1 (`missing_template_context` guard re-home on REST) — out of scope for this tests-only plan.

## Self-Check: PASSED
- All 3 task/doc commits found in git log (`59f33f96`, `f30b841a`, `b2046921`).
- `44-08-SUMMARY.md` present on disk.
- The 4 deleted WS-only tests confirmed gone (`test_pipeline_cancel`, `test_run_revision_ws_dispatch`, `test_ws_parent_link_ownership`, `test_ws_reconnect_replay`).
- Zero collection errors (2506 collected); `grep FakeWebSocket` = 0; `lint-imports` 4/0.

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-15*

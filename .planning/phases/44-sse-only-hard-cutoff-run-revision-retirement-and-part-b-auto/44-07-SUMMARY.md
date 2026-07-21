---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 07
subsystem: api
tags: [websocket, sse, transport-cutover, run_revision, inv-12, feature-flag]

# Dependency graph
requires:
  - phase: 44-03
    provides: transport-neutral seams relocated to app/api/run_engine.py (auth, db, queue registry, validators, resume registrars)
  - phase: 44-06
    provides: frontend makes zero WS connections (useWebSocket deleted, SSE/REST unconditional)
provides:
  - "/ws/chat WebSocket endpoint + receive-loop handlers deleted (app/api/websocket.py removed entirely)"
  - "run_revision WS handler + _handle_revision_execution driver retired (engine._handle_revision KEPT for the REST /revisions twin)"
  - "_handle_workflow_execution (run_pipeline WS driver) deleted"
  - "SSE_TRANSPORT_ENABLED backend flag + run_stream 404 feature-gate removed — the SSE stream is unconditional"
  - "no dual run transport survives on the backend (INV-12 exit gate cleared)"
affects: [44-08, phase-44-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single run transport: per-run SSE down-channel (run_stream) + REST command up-channel (run_commands) are the sole surface; /ws/handoff (IDE handoff) is the only surviving WebSocket"
    - "Byte/event parity preserved across a transport deletion: the 5 characterization goldens + wire-parity compare against FROZEN goldens, proving the cutover changed transport not engine bytes"

key-files:
  created: []
  modified:
    - "backend/app/api/websocket.py (DELETED — endpoint + WS framing + 4 WS-only title helpers + both WS drivers)"
    - "backend/app/main.py (dropped websocket_router import + mount)"
    - "backend/app/core/config.py (removed SSE_TRANSPORT_ENABLED)"
    - "backend/app/api/run_stream.py (removed the 404 feature-gate; SSE unconditional)"
    - "backend/tests/unit/test_sse_stream.py (dropped obsolete test_flag_off_is_404 + unused import)"
    - "backend/tests/unit/test_rest_run_launch.py (repointed fixture seam to run_engine)"
    - "backend/tests/unit/test_rest_revisions.py (repointed fixture seam to run_engine)"

key-decisions:
  - "Deleted websocket.py entirely (not just the endpoint) — after removing the endpoint + both drivers the only remaining content was the 4 WS-only title helpers (used nowhere else — REST launch generates titles inline in run_commands.py) + the run_engine re-import block; nothing live survived, so per the plan the whole file was removed"
  - "engine._handle_revision KEPT unchanged — only the WS driver (_handle_revision_execution) was deleted; the REST /revisions byte-twin still calls the engine method"

patterns-established:
  - "Transport retirement without engine drift: gate the deletion on frozen goldens + wire-parity, never on the deleted endpoint's own tests"

requirements-completed: [W4, W3, "C.3", "D1", "CTX-04", "INV-12", "INV-3"]

# Metrics
duration: ~20 min
completed: 2026-07-15
---

# Phase 44 Plan 07: /ws/chat Retirement + Backend Flag Removal (INV-12 Exit Gate) Summary

**Deleted the `/ws/chat` WebSocket endpoint, its `run_pipeline`/`run_revision` drivers, and the `SSE_TRANSPORT_ENABLED` backend flag — leaving the per-run SSE stream + REST commands as the single run transport, with the 5 characterization goldens + wire-parity still byte/event-identical.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-15T19:25Z (approx)
- **Completed:** 2026-07-15T19:45:26Z
- **Tasks:** 3
- **Files modified:** 7 (1 deleted, 6 edited); 2358 deletions

## Accomplishments
- Removed `backend/app/api/websocket.py` entirely (2316 lines): the `websocket_chat` receive-loop `/ws/chat` endpoint, the WS framing/drainer, the four WS-only title-generation helpers, and both WS drivers `_handle_workflow_execution` (run_pipeline) and `_handle_revision_execution` (run_revision).
- Dropped the `websocket_router` import + `include_router` mount from `main.py`; confirmed the `restore_non_terminal_runs` resume-registrar wiring already sources from `app.api.run_engine` (44-03), so startup restoration still runs and `import app.main` is clean.
- Removed the `SSE_TRANSPORT_ENABLED` config flag and the `run_stream.py` 404 feature-gate — the SSE stream is now unconditional; the two-layer owner 404 fences (user_id filter + `ScopedStore` default-deny → IDOR resolves to 404, never 403) are untouched.
- Proved INV-3: the 5 characterization goldens (10 passed) + `test_wire_parity.py` (6 passed) stayed byte/event-identical against the frozen goldens after the deletion — the cutover changed transport, not engine bytes.

## Task Commits

1. **Task 1: Delete /ws/chat endpoint + WS drivers** — `0c8ee539` (feat)
2. **Task 2: Remove SSE_TRANSPORT_ENABLED flag + 404 gate** — `7b79b972` (feat)
3. **Task 3: INV-3 gate + REST-twin fixture repoints** — `369a63c7` (fix)

## Files Created/Modified
- `backend/app/api/websocket.py` — DELETED entirely (WS-only endpoint + drivers + helpers).
- `backend/app/main.py` — removed the `websocket_router` import + mount; refreshed the SSE/REST mount comments to note WS retirement.
- `backend/app/core/config.py` — removed `SSE_TRANSPORT_ENABLED`; rewrote the surrounding comment block (SSE is now the sole run transport).
- `backend/app/api/run_stream.py` — removed the `if not settings.SSE_TRANSPORT_ENABLED: 404` gate + updated the docstring; owner fences intact.
- `backend/tests/unit/test_sse_stream.py` — removed the obsolete `test_flag_off_is_404` and its now-unused `settings` import.
- `backend/tests/unit/test_rest_run_launch.py`, `backend/tests/unit/test_rest_revisions.py` — repointed the `env` fixture's `_get_db` seam alias from the deleted `app.api.websocket` to `app.api.run_engine` (the 44-03 relocation target).

## Decisions Made
- **Whole-file deletion of websocket.py.** After removing the endpoint + both drivers, the only remaining symbols were the four WS-only title helpers (`_extract_message_text`, `_extract_title_from_context`, `_strip_pipeline_context`, `_generate_workflow_title`) — verified used nowhere else (the REST launch path in `run_commands.py` builds titles inline) — plus the `run_engine` re-import block. Nothing live survived, so the plan's conditional ("delete entirely IF it holds nothing but the dead endpoint + re-imports") was met and the file was removed.
- **engine._handle_revision KEPT.** Only the WS driver was retired; the REST `/revisions` twin still calls the engine method (grep count = 1, unchanged).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repointed two REST-twin fixtures off the deleted websocket module**
- **Found during:** Task 3 (INV-3 gate — the REST twins are gated on)
- **Issue:** `test_rest_run_launch.py` and `test_rest_revisions.py` `env` fixtures aliased the shared `_get_db` seam via `from app.api import websocket as ws_module` — a stale reference from before 44-03 relocated the transport-neutral seams to `run_engine`. With `websocket.py` deleted they raised `ImportError: cannot import name 'websocket' from 'app.api'` (17 + 10 collection/setup errors).
- **Fix:** Changed the alias to `from app.api import run_engine as ws_module` (identical seam — `run_commands` already binds `_get_db` from `run_engine`). Updated one stale comment. No behavior change.
- **Files modified:** backend/tests/unit/test_rest_run_launch.py, backend/tests/unit/test_rest_revisions.py
- **Verification:** handoff-contract + all 4 REST twins → 64 passed.
- **Committed in:** 369a63c7

**2. [Rule 1 - Obsolete test] Removed test_flag_off_is_404**
- **Found during:** Task 2 (flag removal)
- **Issue:** `test_sse_stream.py::test_flag_off_is_404` monkeypatched `SSE_TRANSPORT_ENABLED = False` to assert a 404 — but the flag (and the flag-off path) no longer exists.
- **Fix:** Deleted the obsolete test method + its now-unused `settings` import. This was required to hit the Task 2 acceptance (`grep SSE_TRANSPORT_ENABLED → 0`).
- **Files modified:** backend/tests/unit/test_sse_stream.py
- **Verification:** `test_sse_stream.py` → 27 passed (was 28, minus the deleted test).
- **Committed in:** 7b79b972

---

**Total deviations:** 2 auto-fixed (1 blocking import repoint on gated tests, 1 obsolete-test removal). **Impact on plan:** Both were necessary to satisfy the plan's own acceptance criteria (REST twins green; flag grep = 0). No scope creep — the repoints reflect the 44-03 seam relocation the tests hadn't yet followed.

## Issues Encountered
- **Break-as-expected WS-endpoint tests (44-08 migrates them — NOT gated on here, per plan).** The deletion breaks tests that drive the now-gone endpoint or import WS-only helpers: module-level importers `tests/agents/test_ws_reconnect_replay.py` and `tests/unit/test_user_workflows_selections.py` (fail at collection); and in-function importers `tests/unit/test_run_pipeline_validation.py`, `tests/unit/test_capabilities_api.py`, `tests/unit/test_approve_review_ownership.py`, plus the orchestrator-named `test_run_revision_ws_dispatch.py`, `test_pipeline_cancel.py`, `test_ws_parent_link_ownership.py`, and the WS halves of `test_image_ws_ingress.py` / `test_pipeline_failure_semantics.py`. These were explicitly declared out-of-scope for this plan (migrated/deleted in 44-08, wave 6). Not fixed here.

## Verification Results (INV-3 exit gate)
- `pytest tests/agents/ -k characterization` (ignoring the break-as-expected `test_ws_reconnect_replay.py`) → **10 passed** (goldens byte-identical).
- `pytest tests/agents/test_wire_parity.py` → **6 passed** (SSE frames == frozen WS goldens).
- `pytest test_handoff_contract.py + test_rest_revisions + test_rest_gate_commands + test_rest_answers_cancel + test_rest_run_launch` → **64 passed**.
- `pytest test_sse_stream.py + test_attach_replay_matrix.py` (Task 2) → **27 passed**.
- `/opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**.
- `python3.11 -c "import app.main"` → clean (startup wiring resolves).
- Migration chain unchanged (latest **0025**, no new migration).
- Grep-proofs: `app/api/websocket.py` DELETED (route/endpoint gone); `websocket_router` in `main.py` = 0; `SSE_TRANSPORT_ENABLED` repo-wide = 0; `/ws/handoff` in `websocket_handoff.py` survives; `engine._handle_revision` count = 1 (KEPT); `run_engine.py` KEPT.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- INV-12 backend exit gate cleared: no dual run transport survives (SSE + REST only; `/ws/handoff` is the sole remaining WebSocket, untouched).
- **44-08 (wave 6)** must migrate/delete the break-as-expected WS-endpoint tests listed under Issues Encountered.

## Self-Check: PASSED
- All 3 task commits found (0c8ee539, 7b79b972, 369a63c7).
- SUMMARY.md present on disk; `backend/app/api/websocket.py` confirmed deleted.

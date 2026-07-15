---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 03
subsystem: api
tags: [fastapi, websocket, sse, refactor, ports-and-adapters, run-engine]

# Dependency graph
requires:
  - phase: 29-rest-sse-twin
    provides: the REST/SSE twin endpoints (run_commands/run_stream/run_files) that consume the shared run infra
  - phase: 44-01-and-44-02
    provides: FE confirm-first refinement chip + wave-1 FE rewire (untouched here)
provides:
  - "app/api/run_engine.py — the transport-neutral home for the R3 shared run infra (queues/tasks/cancel-events, resume registrars, cleanup, ingress validators, owner/terminal fences, _get_db + _authenticate_token)"
  - "All 5 non-endpoint importers repointed at run_engine; /ws/chat endpoint + WS drivers still fully functional"
affects: [44-07 (deletes /ws/chat off the relocated infra), 44-04, 44-05, 44-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Extract-before-delete (INV-12): relocate shared infra to a transport-neutral module BEFORE the endpoint deletion, so the deletion wave is a clean receive-loop removal"
    - "Transport-neutral run kernel module (app.api.run_engine) imported by both the WS endpoint and the REST/SSE endpoints; import-linter direction preserved (app.api layer, kernel still imports no app.*)"

key-files:
  created:
    - backend/app/api/run_engine.py
  modified:
    - backend/app/api/websocket.py
    - backend/app/api/run_commands.py
    - backend/app/api/run_stream.py
    - backend/app/api/run_files.py
    - backend/app/main.py
    - backend/app/api/websocket_handoff.py

key-decisions:
  - "MOVE (cut) not copy — no dual implementation survives (INV-12). websocket.py re-imports the 13 symbols it still uses from run_engine; the two resume registrars are consumed only by main.py so are NOT re-imported into websocket.py."
  - "Test seams coupled to the moved module were repointed to app.api.run_engine (the relocated predicates resolve _get_db in their own namespace, so monkeypatching websocket._get_db no longer reaches them)."

patterns-established:
  - "When relocating a private helper that other modules monkeypatch, the patch target must move with it — repoint the test seam, do not keep a shim in the old module (INV-12)."

requirements-completed: [W4, "C.3", "INV-3", "INV-12"]

# Metrics
duration: 45 min
completed: 2026-07-15
---

# Phase 44 Plan 03: Relocate Shared Transport-Neutral Run Infra Summary

**Extracted the R3 shared run infrastructure (pipeline queues/tasks/cancel-events, resume registrars, ingress validators, owner/terminal fences, `_get_db` + `_authenticate_token`) out of `websocket.py` into a new transport-neutral `app/api/run_engine.py` and repointed all 5 importers — the `/ws/chat` endpoint and the REST/SSE endpoints both run off the relocated infra, byte/event-identical (INV-3).**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-07-15
- **Tasks:** 3
- **Files modified:** 12 (1 created, 6 source modified, 5 test seams repointed)

## Accomplishments
- Created `app/api/run_engine.py` as the single transport-neutral home for the symbols that must outlive the `/ws/chat` deletion (relocated verbatim, MOVE not copy — INV-12).
- Repointed the 5 non-endpoint importers (`run_commands`, `run_stream`, `run_files`, `main`, `websocket_handoff`) at `run_engine` with zero logic change; `/ws/chat` endpoint + WS drivers stay intact.
- Proved byte/event-neutrality: the 5 characterization goldens (10 passed) and `test_wire_parity.py` (6 passed) stay identical; `lint-imports` 4 kept / 0 broken; migration chain unchanged (0025).

## Task Commits

1. **Task 1: Create run_engine.py + relocate the R3 symbols** - `9e3913e7` (refactor)
2. **Task 2: Repoint the 5 importers + coupled test seams** - `3ff8a24c` (refactor)
3. **Task 3: INV-3 gate — prove byte/event neutrality** - verification only (no code commit; goldens + wire-parity green)

**Plan metadata:** (this commit) docs: complete plan

## Files Created/Modified
- `backend/app/api/run_engine.py` - NEW. Transport-neutral home for `_PIPELINE_QUEUES`/`_PIPELINE_TASKS`/`_CANCEL_EVENTS`, `_get_or_create_queue`, `_cleanup_pipeline`, `_register_resume_queue`/`_register_resume_task`, the ingress validators/fences (`_validate_images`, `_validate_model_overrides`, `_revalidate_selections_trust_user`, `_resolve_owned_parent_run_id`, `_review_gate_owned_by`, `_review_gate_run_is_terminal`), the image caps constants, and `_get_db` + `_authenticate_token`.
- `backend/app/api/websocket.py` - Removed the moved defs; re-imports the 13 symbols it still uses from `run_engine`; the `/ws/chat` endpoint, WS framing, `_handle_workflow_execution`/`_handle_revision_execution` drivers and `router` are untouched (44-07 deletes those). Dropped now-unused imports (`JWTError`, `Session`, `decode_access_token`, `is_token_revoked`, `SessionLocal`).
- `backend/app/api/run_commands.py` - Import source `app.api.websocket` → `app.api.run_engine` (11 symbols).
- `backend/app/api/run_stream.py` - Import source → `run_engine` (`_PIPELINE_QUEUES`, `_get_or_create_queue`).
- `backend/app/api/run_files.py` - Import source → `run_engine` (`_get_db`).
- `backend/app/main.py` - `_ws_bridge` rebound to `app.api.run_engine` so the resume registrars + cleanup hook source from there; `restore_non_terminal_runs()` wiring unchanged.
- `backend/app/api/websocket_handoff.py` - Import source → `run_engine` (`_authenticate_token`, `_get_db`); `/ws/handoff` route/auth/reducer otherwise byte-identical.

## Decisions Made
- **MOVE not copy (INV-12):** the defs were cut from `websocket.py`; the endpoint keeps working by re-importing them from `run_engine`. No dual implementation survives.
- **Two resume registrars not re-imported into websocket.py:** they are consumed only by `main.py`, so re-importing them into `websocket.py` would be an unused import (F401). `main.py` sources them from `run_engine` directly.
- **Test seams repointed to run_engine:** the relocated predicates (`_review_gate_owned_by` / `_review_gate_run_is_terminal`) resolve `_get_db` in the `run_engine` namespace, so tests that monkeypatch the seam must patch `app.api.run_engine`, not `app.api.websocket`. This is the correct consequence of relocation, not a shim in the old module.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repointed test seams coupled to the moved symbols**
- **Found during:** Task 2 (verification of the REST twin + ownership tests)
- **Issue:** `test_rest_gate_commands`, `test_rest_answers_cancel`, `test_approve_review_ownership` and `test_attach_replay_matrix` monkeypatch `app.api.websocket._get_db` (and reference `_CANCEL_EVENTS`); the relocated predicates now resolve `_get_db` in the `run_engine` namespace, so the patch no longer reached them → "Unknown gate_key" / ownership-False failures. `test_image_ingress_validation` imported the image caps constants directly from `websocket` (not re-exported) → collection ImportError. A source-order pin in `test_rest_gate_commands` asserted the old import string `from app.api.websocket import`.
- **Fix:** Repointed the fixture imports/monkeypatch targets and the source-order assertion to `app.api.run_engine`; repointed the caps-constant import in `test_image_ingress_validation`.
- **Files modified:** backend/tests/unit/test_rest_gate_commands.py, test_rest_answers_cancel.py, test_approve_review_ownership.py, test_image_ingress_validation.py, backend/tests/agents/test_attach_replay_matrix.py
- **Verification:** All previously-red tests green; the full affected-suite run is 277 passed / 12 pre-existing reds.
- **Committed in:** `3ff8a24c` (Task 2 commit)

**2. [Rule 3 - Blocking] Fixed a pre-existing B905 (`zip` without `strict=`)**
- **Found during:** Task 2 (ruff on the edited `test_attach_replay_matrix.py`)
- **Issue:** Line 239 had `zip(...)` without an explicit `strict=` (ruff B905), a pre-existing violation surfaced because I edited the file; ruff on the changed file would flag it.
- **Fix:** Added `strict=False` (the default `zip` behavior — zero behavior change).
- **Files modified:** backend/tests/agents/test_attach_replay_matrix.py
- **Verification:** ruff clean; the 12 tests in the file pass.
- **Committed in:** `3ff8a24c` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking). **Impact:** Both were mechanical, behavior-preserving consequences of the relocation (test-seam repoint + a ruff-gate unblock). No scope creep; no production behavior changed.

## Issues Encountered
- **Pre-existing reds (out of scope, NOT caused by this plan):** `tests/unit/test_run_pipeline_validation.py` has 12 failing agent-pool-membership assertions. Verified pre-existing by stashing the Task-2 edits and re-running at the Task-1 state — identical 12 reds. Logically unrelated to a DB/auth/validator relocation. Left untouched; logged for the phase.
- **No pre-commit hooks installed** in this clone (`.git/hooks/pre-commit` absent); `git commit` runs no hooks. Quality gates were run manually instead: `ruff` clean on all changed files, `pyright` clean (only the pre-existing `sse_starlette` import-resolution false-positives on untouched lines), and the targeted pytest suites.

## Verification Results
- `pytest tests/agents/ -k characterization` → **10 passed** (INV-3 goldens byte-identical).
- `pytest tests/agents/test_wire_parity.py` → **6 passed** (SSE-frame parity oracle unchanged).
- `pytest test_handoff_contract + test_rest_gate_commands + test_rest_answers_cancel + test_rest_revisions + test_rest_run_launch` → **64 passed** (Task 2 acceptance).
- WS/REST driver suites (`test_run_revision_ws_dispatch`, `test_pipeline_cancel`, `test_ws_reconnect_replay`, `test_ws_parent_link_ownership`, `test_pipeline_failure_semantics`, `test_image_ws_ingress`) → green.
- `lint-imports` → **4 kept / 0 broken**.
- Migration chain unchanged (latest **0025**, no new migration).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `run_engine.py` now owns the R3 symbols; 44-07 can delete the `/ws/chat` receive-loop endpoint + WS framing cleanly (the shared infra no longer lives in `websocket.py`).
- `/ws/handoff` (the D10 survivor) and the resume-bridge startup wiring are intact.

## Self-Check: PASSED
- `backend/app/api/run_engine.py` — FOUND on disk.
- `44-03-SUMMARY.md` — FOUND on disk.
- Task 1 commit `9e3913e7` — FOUND in git log.
- Task 2 commit `3ff8a24c` — FOUND in git log.

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-15*

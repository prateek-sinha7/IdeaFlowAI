---
phase: 16-terminal-state-integrity-and-reconnect-frame-contract
plan: 01
subsystem: engine
tags: [execution-engine, deepagents-runner, pipeline-failed, degraded, terminal-semantics, iss-016, inv-3]

# Dependency graph
requires:
  - phase: 13-terminal-semantics
    provides: "F3 terminal gating (_failed_agent_ids → pipeline_failed / status:degraded) + the WR-05 unrecovered-failure subtraction"
  - phase: 06-model-policy
    provides: "the runner's non-throttle swallow → {'type':'error'} event (06-05 D-05 LOCKED) + the ScriptedFakeChatModel(raise_exc=...) offline lever"
provides:
  - "engine.py _run_agent consumes the runner {'type':'error'} event into the agent_error machinery (the ISS-016 error consume-arm)"
  - "a runner-surfaced model/tool error on EVERY agent now ends pipeline_failed; a PARTIAL error ends status:degraded; no empty agent_complete for a failed agent"
  - "an offline fault-injection suite (ScriptedNonTransientError) proving the fix end-to-end through the real runner+engine path"
affects: [16-04-iss017-fe-affordance, terminal-state-integrity]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Consume-arm divergence: the error path emits a recoverable agent_error then RETURNs, deliberately SKIPPING the result-append + agent_complete (unlike the timeout path which keeps the completion) — so the agent stays in _failed_agent_ids and the existing F3 block maps it to the terminal."
    - "Fault-injection via the real DeepAgentRunner: patch create_runner to inject ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError()) and drive the FULL execute() — exercises the runner→error→engine arm, not a _run_agent stub."

key-files:
  created:
    - backend/tests/agents/test_engine_runner_error_arm.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_model_fallback.py

key-decisions:
  - "The error arm keys on the GENERIC event type (etype == 'error') only — no ValidationException / provider / workflow / model text match (SC-001). The literal example was even removed from the code comment so the SC-001 grep gate returns 0."
  - "The surfaced agent_error message is bounded to 500 chars from the runner's str(exc) (no traceback / internal path) per the T-16-01-ID information-disclosure mitigation."
  - "The runner (deep_agent_runner.py) is UNCHANGED — the 06-05 D-05 LOCKED non-throttle swallow is preserved; only the engine's CONSUMPTION of the error event changes. Verified git diff touches no runner file."
  - "test_non_transient_propagates was flipped: it previously encoded the ISS-016 bug (only asserted built_for); it now asserts the agent_error surfaces, no empty agent_complete, and a single-agent run collapses to pipeline_failed."

patterns-established:
  - "ISS-016 error consume-arm: an elif etype=='error' in the _run_agent stream loop sets agent_errored + captures the bounded message; a post-loop if agent_errored branch emits the recoverable agent_error and returns before the output build."

requirements-completed: [ISS-016]

# Metrics
duration: ~18 min
completed: 2026-06-13
---

# Phase 16 Plan 01: ISS-016 Engine Consumes the Runner error Event Summary

**The `_run_agent` stream loop now consumes the runner's swallowed `{"type":"error"}` event into a recoverable `agent_error` (skipping the empty `agent_complete`), so an all-fail run ends `pipeline_failed` and a partial-fail run ends `status:degraded` instead of riding through as a clean `pipeline_complete`.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-13T12:40:36Z
- **Completed:** 2026-06-13
- **Tasks:** 2
- **Files modified:** 3 (1 engine, 2 test)

## Accomplishments
- Added the ISS-016 `elif etype == "error":` consume-arm to the `_run_agent` stream loop: it records the runner's bounded error message and breaks, then a post-loop `if agent_errored:` branch emits a recoverable `agent_error` and `return`s — deliberately skipping the `output` build, the result-append, and the empty `agent_complete` for that agent.
- The failed agent therefore stays in the dispatch loop's `_failed_agent_ids` set and is NOT in `results`, so the EXISTING F3 terminal machinery maps it: all-fail → one `pipeline_failed` (state `failed`); partial-fail → `pipeline_complete` with `status:degraded` + `agents_failed`. No FE change, no F3 logic change, no runner edit.
- Flipped `test_model_fallback.py::test_non_transient_propagates` (which encoded the bug) to assert the corrected contract: the `agent_error` surfaces, no empty `agent_complete` fires, and a single-agent `execute()` run collapses to `pipeline_failed`.
- Added `test_engine_runner_error_arm.py`: an offline fault-injection suite that drives the REAL `execute()` + `_run_agent` path with a `create_runner` patch injecting `ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())` — exercising the genuine runner-swallow → engine-arm chain end-to-end (all-fail → `pipeline_failed`; partial → degraded; no empty `agent_complete` for failed agents).

## Task Commits

1. **Task 1: Add the `error` consume-arm + flip test_non_transient_propagates** — `5eee8cca` (fix)
2. **Task 2: Fault-injection test (ScriptedNonTransientError → pipeline_failed / degraded)** — `be4d4643` (test)

## Files Created/Modified
- `backend/agents/execution_engine/engine.py` — `_run_agent`: `agent_errored`/`agent_error_message` locals; the `elif etype == "error":` consume-arm; the post-loop emit-and-return failure branch.
- `backend/tests/agents/test_model_fallback.py` — flipped `test_non_transient_propagates` + a new `_drive_execute_single_non_transient` helper that drives the full `execute()` for the `pipeline_failed` assertion.
- `backend/tests/agents/test_engine_runner_error_arm.py` — NEW offline fault-injection suite (`test_all_agents_error_ends_pipeline_failed`, `test_partial_error_ends_degraded`).

## Decisions Made
- **Branch on the generic event type only (SC-001):** the arm keys on `etype == "error"`; the `ValidationException`/"Operation not allowed" example was removed even from the code comment so the SC-001 grep gate (`grep -nE 'ValidationException|Operation not allowed'`) returns 0 matches.
- **Bounded message (T-16-01-ID):** the surfaced `agent_error.error` is `str(event.get("error"))[:500]` — no stack frames or internal paths.
- **Runner untouched:** the 06-05 D-05 LOCKED non-throttle swallow stays; only the engine's consumption changes (`git diff` confirms zero runner changes).

## Deviations from Plan

None - plan executed exactly as written.

The plan's Task-1 acceptance criterion asked the flipped test to also assert a single-agent `pipeline_failed` terminal. Because the existing `_drive_one_agent` harness drives `_run_agent` directly (which never emits `pipeline_failed` — that is `execute()`'s job), a small full-`execute()` driver (`_drive_execute_single_non_transient`) was added within the same test file to satisfy that criterion. This is implementing the plan as specified, not a deviation.

## Verification Evidence

- **Task tests:** `test_model_fallback.py` 4/4 pass (incl. the flipped test); `test_engine_runner_error_arm.py` 2/2 pass; `test_pipeline_failure_semantics.py` 8/8 pass (no F3 regression). Consolidated: 14 passed.
- **SC-001 grep:** `grep -nE 'ValidationException|Operation not allowed' agents/execution_engine/engine.py` → 0 matches. `grep -n 'etype == "error"'` → exactly one (the arm).
- **Runner untouched:** `git diff 53b939d9..HEAD --stat app/agents/deep_agent_runner.py` → empty.
- **INV-3 parity (mandatory):** the 5 characterization goldens (prototype / od_prototype / prototype_revision / od_ppt / app_builder) + banned-patterns + migration-ledger → 44 passed, 7 skipped, byte/event-IDENTICAL (SNAPSHOT_UPDATE UNSET); the scripted model never raises so the new arm is dormant on the goldens.
- **import-linter:** `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken.
- **Zero new tables/migrations:** `git status --porcelain` shows no new alembic file.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ISS-016 engine half is closed: the run now TELLS the truth on the live wire (`pipeline_failed` / `status:degraded`).
- Plan 16-04 (ISS-017, the FE affordance) consumes this — it makes the Preview SHOW the truth, keyed on the `pipeline_failed`/`status:degraded` server signal this plan now emits.
- Plans 16-02/16-03 (ISS-007/002 cancel delivery, ISS-008/009 reconnect frame-contract) are independent of this change.

## Self-Check: PASSED
- `backend/agents/execution_engine/engine.py` — FOUND (modified, the error arm present)
- `backend/tests/agents/test_engine_runner_error_arm.py` — FOUND (created)
- `backend/tests/agents/test_model_fallback.py` — FOUND (modified)
- Commit `5eee8cca` — FOUND
- Commit `be4d4643` — FOUND

---
*Phase: 16-terminal-state-integrity-and-reconnect-frame-contract*
*Completed: 2026-06-13*

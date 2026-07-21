---
phase: 260718-p8m
plan: 01
subsystem: run-launch-driver
tags: [cwf-001, d2, status-lifecycle, lock-b-twin, app-layer]
requires:
  - _drive_revision_to_queue (LOCK-B fail-safe template, Phase 29)
provides:
  - _drive_launch_to_queue fail-safe terminal status (error / pipeline_failed → failed)
affects:
  - backend/app/api/run_commands.py
  - backend/tests/unit/test_rest_run_launch.py
tech-stack:
  added: []
  patterns: [fail-safe-terminal-status, lock-b-twin-reconciliation, generic-event-keying]
key-files:
  created: []
  modified:
    - backend/app/api/run_commands.py
    - backend/tests/unit/test_rest_run_launch.py
decisions:
  - "Completed reachable ONLY on a clean pipeline_complete with no error signal; every other outcome fail-safes to failed."
  - "Key on generic event types (utype == error / pipeline_failed) — no workflow-name / pipeline_type literal (INV-1/SC-001)."
  - "Reconcile launch driver toward the revision twin (Phase 29 LOCK-B) — no engine/resolver/compiler edit, no migration, no sa.Enum."
metrics:
  duration: ~9m
  completed: 2026-07-18
  tasks: 2
  files: 2
---

# Phase 260718-p8m Plan 01: CWF-001 FIX D2 — Launch Driver Fail-Safe Run Status Summary

Fixed `_drive_launch_to_queue` mislabeling errored/failed custom runs as `completed` by tracking the generic `error` event + `pipeline_failed` and making the terminal status fail-safe, reconciled toward the already-correct LOCK-B revision twin `_drive_revision_to_queue`.

## What Was Built

`backend/app/api/run_commands.py::_drive_launch_to_queue` — three minimal, additive changes:

1. **State flags** (`~:1318`) — added `pipeline_error_seen`, `pipeline_failed_seen`, `pipeline_error_msg` alongside the existing terminal-tracking flags.
2. **Event-loop tracking** (`~:1430`) — after the `pipeline_cancelled` branch, added `elif utype == "error":` (captures `data.error` / `data.code`) and `elif utype == "pipeline_failed":` (captures `data.error`). The unconditional `event_queue.put` at the loop top is untouched.
3. **Fail-safe terminal** (`~:1457`) — `wr.status = "completed"` now requires `pipeline_complete_seen and not pipeline_error_seen and not pipeline_failed_seen`; the terminal `else` unconditionally sets `wr.status = "failed"` and persists `wr.error = first_agent_error_msg or pipeline_error_msg`. The `pipeline_cancelled` and `degraded` branches are unchanged, preserving precedence `cancelled > degraded > failed > completed`.

`backend/tests/unit/test_rest_run_launch.py` — two new driver-level tests + a one-line reconcile:
- `test_driver_generic_error_records_failed` — stub ends in `{"type":"error","code":"workflow_unsatisfiable"}` → asserts `status=="failed"`, `!= "completed"`, `error` non-null containing "unsatisfiable".
- `test_driver_pipeline_failed_records_failed` — stub emits `pipeline_failed` → asserts `status=="failed"`, `!= "completed"`.
- Reconciled the existing happy-path assertion (`test_driver_drives_engine_and_populates_queue`): kept `assert row.status == "completed"` (clean `pipeline_complete` is legitimately completed) and added the anti-regression `assert row.status != "failed"` with a fail-safe-contract comment. `_RecordingEngine` was NOT modified.

## RED → GREEN Evidence

RED (before the fix, against the unfixed driver):
```
tests/unit/test_rest_run_launch.py .FF
test_driver_generic_error_records_failed   AssertionError: assert 'completed' == 'failed'
test_driver_pipeline_failed_records_failed AssertionError: assert 'completed' == 'failed'
(happy-path drives_engine PASSED)
```
GREEN (after the fix):
```
tests/unit/test_rest_run_launch.py .......................  (23 passed)
tests/unit/test_rest_revisions.py .............. (14 passed)
37 passed in 0.71s
```

## Verification

- `test_rest_run_launch.py` + `test_rest_revisions.py`: **37 passed** (fix + untouched LOCK-B twin).
- 5 characterization goldens (`prototype`, `od_prototype`, `prototype_revision`, `od_ppt`, `app_builder`): **10 passed** — byte/event-identical (INV-3 not exposed; the harness asserts deliverable bytes + the event multiset, not the `WorkflowRun.status` DB write).
- `/opt/homebrew/bin/lint-imports`: **4 kept, 0 broken** (kernel/app boundary intact; no kernel import added).
- SC-001 spot-check: grep confirms both branches added (`utype == "error"` `:1430`, `utype == "pipeline_failed"` `:1438`); the D2 edit introduced no new `pipeline_type ==` literal and no workflow-name string (the two pre-existing `pipeline_type ==` refs at `:1089`/`:1154` are outside the edited terminal-derivation block and are generic app-layer refs).

## Scope Held

FIX D2 ONLY. No FIX D1 (compose-time DAG guard / producer-first pre-sort). No CWF-002 (per-agent model persistence). App-layer status derivation only — `engine.py`, `resolver.py`, and the compiler untouched. No migration, no `sa.Enum` (run-status stays a free `String`). The two drivers remain behaviorally identical on terminal-status derivation (Phase 29 LOCK-B).

## Deviations from Plan

None — plan executed exactly as written.

## Commits

- `32c6220a` test(tests): add RED tests for launch driver fail-safe status (CWF-001 D2)
- `a0c98b8f` fix(engine): make launch driver terminal status fail-safe (CWF-001 D2)

## Self-Check: PASSED

- `backend/app/api/run_commands.py` — FOUND (modified, commit a0c98b8f)
- `backend/tests/unit/test_rest_run_launch.py` — FOUND (modified, commit 32c6220a)
- Commit `32c6220a` — FOUND
- Commit `a0c98b8f` — FOUND

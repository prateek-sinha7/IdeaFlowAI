---
phase: 01-0a-safety-net-deletion-guard
plan: 02
subsystem: testing / characterization harness
tags: [characterization, event-snapshot, safe-02, safe-03, normalize, offline-harness]
requires:
  - "backend/tests/agents/_scripted_model.py::_drive (offline driver, D-01)"
  - "backend/tests/agents/characterization/__init__.py::GOLDEN_DIR / SNAPSHOT_UPDATE (01-01)"
  - "backend/tests/agents/test_phase3_cutover_verify.py::_DOCUMENTED_EVENT_TYPES / _REQUIRED_DATA_KEYS (contract SoT)"
provides:
  - "semantic event-stream snapshots for prototype/od_prototype/prototype_revision/od_ppt/app_builder (SAFE-02)"
  - "_normalize() + VOLATILE_SENTINEL + _canonical_order() + assert_seq_contiguous() (SAFE-02/SAFE-03)"
  - "characterization/golden/<pipeline>.events.json x5 (committed normalized snapshots)"
affects:
  - "01-04 (CI backend:characterization job runs these event-snapshot tests offline)"
  - "Phase 0C (event snapshots are the INV-3 tripwire that survives sanctioned text drift)"
tech-stack:
  added: []
  patterns:
    - "event-snapshot golden gated behind SNAPSHOT_UPDATE=1 (D-07, mirrors 01-01 byte-snapshot)"
    - "volatile-but-required keys keep their key, value replaced by named VOLATILE_SENTINEL (D-06)"
    - "order-canonical multiset snapshot (sort by canonical JSON) to tolerate engine build-loop interleaving"
    - "contract dicts IMPORTED from phase3 verify (single source of truth, never copied)"
key-files:
  created:
    - backend/tests/agents/characterization/_normalize.py
    - backend/tests/agents/characterization/golden/prototype.events.json
    - backend/tests/agents/characterization/golden/od_prototype.events.json
    - backend/tests/agents/characterization/golden/prototype_revision.events.json
    - backend/tests/agents/characterization/golden/od_ppt.events.json
    - backend/tests/agents/characterization/golden/app_builder.events.json
  modified:
    - backend/tests/agents/test_characterization_prototype.py
    - backend/tests/agents/test_characterization_od_prototype.py
    - backend/tests/agents/test_characterization_prototype_revision.py
    - backend/tests/agents/test_characterization_od_ppt.py
    - backend/tests/agents/test_characterization_app_builder.py
decisions:
  - "VOLATILE_SENTINEL = \"<normalized>\" — single-sourced named constant, referenced everywhere (never inlined)."
  - "agent_chunk text handled by DROPPING per-chunk granularity (value→VOLATILE_SENTINEL) while keeping the structural chunk slot, not by coalescing across events — preserves event count/order for the multiset and keeps _REQUIRED_DATA_KEYS[agent_chunk]={agent_id,chunk} present."
  - "_REQUIRED_DATA_KEYS / _DOCUMENTED_EVENT_TYPES are IMPORTED from test_phase3_cutover_verify (not copied) so _normalize() can never silently diverge from the documented WS contract."
  - "Snapshot is an ORDER-CANONICAL MULTISET (Rule 1 deviation): the prototype/app build loop interleaves tool_result/task_progress/retry tool_call nondeterministically across runs of the UNCHANGED engine, so a raw positional snapshot was flaky. _canonical_order() sorts by canonical JSON; strict emission order stays covered by assert_seq_contiguous + the phase3/01-01 positional sequence tests."
metrics:
  duration: "~12 min"
  completed: "2026-06-06T23:55:00Z"
  tasks: 2
  files: 11
---

# Phase 1 Plan 02: Safety-Net Semantic Event-Snapshots Summary

Adds the semantic event-stream snapshot half of the characterization safety net (SAFE-02) plus the contiguous-`seq` assertion (SAFE-03) for all five named pipelines, via a single shared `_normalize()` helper grounded on the existing outbound WS event contract — with zero runtime-code changes and the 01-01 byte-snapshots left untouched.

## What Was Built

- **Task 1 — `_normalize.py`** (`backend/tests/agents/characterization/_normalize.py`):
  - `VOLATILE_SENTINEL = "<normalized>"` — exported named constant, referenced at every call site.
  - `_normalize(events)` — per-event deep-copy that KEEPS `type`, order, and the `_REQUIRED_DATA_KEYS[type]` keys; STRIPS volatile non-required keys; replaces volatile-but-required values with `VOLATILE_SENTINEL`.
  - `assert_seq_contiguous(events)` — asserts per-run `seq` (where present) has deltas all == 1; vacuous today (the engine stamps no `seq`), wired in for SAFE-03 and to enforce contiguity if a `seq` is ever added.
  - `_canonical_order(events)` — stable order-canonical sort (added during Task 2 to tolerate engine interleaving; see Deviations).
  - `load_events_golden` / `write_events_golden` — canonical JSON (`indent=2, sort_keys=True, ensure_ascii=False`, trailing newline).
  - `_DOCUMENTED_EVENT_TYPES` / `_REQUIRED_DATA_KEYS` imported from `test_phase3_cutover_verify` (single source of truth).
- **Task 2 — event-snapshot tests + 5 committed goldens**:
  - Each `test_characterization_<pipeline>.py` gained a second test `test_<pipeline>_event_snapshot` (additive — the 01-01 byte-snapshot test is unchanged). Each: asserts event types ⊆ `_DOCUMENTED_EVENT_TYPES`, asserts per-event `_REQUIRED_DATA_KEYS` present, calls `assert_seq_contiguous`, then compares `_canonical_order(_normalize(events))` to the committed golden (or writes it under `SNAPSHOT_UPDATE`).
  - Five `golden/<pipeline>.events.json` generated with `SNAPSHOT_UPDATE=1` and committed.

## `_normalize()` field list (kept vs stripped vs sentinel)

| Disposition | Keys | Rationale |
|-------------|------|-----------|
| **KEEP (verbatim)** | `type`, plus every `_REQUIRED_DATA_KEYS[type]` non-volatile key (`agent_id`, `name`, `role`, `icon`, `index`, `total`, `output_length`, `tool`, `args`, `result`, `task_number`, `completed_tasks`, `completed_count`, `final_output`, `pipeline_type`, …) | the structural contract the frontend reducer depends on |
| **SENTINEL (key kept, value → `VOLATILE_SENTINEL`)** | `duration`, `input_tokens`, `output_tokens`, `total_tokens`, `total_input_tokens`, `total_output_tokens`, and `agent_chunk.chunk` | volatile-but-required: presence asserted, value drift tolerated |
| **STRIP (key removed)** | `timestamp`, `pipeline_run_id`, `run_id`, `total_duration`, `estimated_cost_usd`, `model_id`, `context_message`, `context_sources` | volatile + NOT required: wall-clock, generated run ids, cost/duration rollups, env-dependent model id, run-specific context echo |

- **`VOLATILE_SENTINEL` value:** `"<normalized>"`.
- **`agent_chunk` handling:** per-chunk text granularity DROPPED — the `chunk` value is normalized to `VOLATILE_SENTINEL` while the structural `chunk` slot is kept (so `_REQUIRED_DATA_KEYS["agent_chunk"] = {agent_id, chunk}` still passes). Chosen over cross-event coalescing because coalescing would change event count/order and weaken the multiset structure.
- **`_REQUIRED_DATA_KEYS` / `_DOCUMENTED_EVENT_TYPES`:** IMPORTED from `test_phase3_cutover_verify` (not copied) — guarantees no silent divergence (T-02-01).

## Committed event-golden files

`backend/tests/agents/characterization/golden/`: `prototype.events.json`, `od_prototype.events.json`, `prototype_revision.events.json`, `od_ppt.events.json`, `app_builder.events.json` — all staged and committed in `eeead30`. Snapshot sizes: prototype/od_prototype 41 events, app_builder 85, od_ppt 19, prototype_revision 13.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Raw positional event snapshot was flaky on the UNCHANGED engine**
- **Found during:** Task 2 (the default no-env assertion run after generating goldens).
- **Issue:** The plan specified a positional snapshot pinning event "order". But `_drive("prototype")` / `od_prototype` / `app_builder` emit `tool_result` / `task_progress` / retry `tool_call` events from the per-task build loop in an order that is NOT stable run-to-run (async-interleaving artifact — the final deliverable byte-snapshot is stable, but adjacent intermediate tool/progress events swap positions). Three event-snapshot tests failed on a second clean run of the unmodified engine — a flaky test, which is a test-design bug.
- **Fix:** Added `_canonical_order(events)` to `_normalize.py` (sorts normalized events by canonical JSON) and compare the snapshot as an **order-canonical multiset**. This still pins event vocabulary, per-type required keys, the full event multiset, and the final result (so a dropped event / new undocumented type / lost required key all still fail), while being robust to legitimate interleaving and 0C text drift. Strict emission order remains covered by `assert_seq_contiguous()` (when a `seq` exists) and the existing positional sequence assertions in `test_phase3_cutover_verify.py` and the 01-01 suite.
- **Files modified:** `_normalize.py` (+ `_canonical_order` wired into all five test modules).
- **Commit:** `eeead30`
- **Verification:** generate (`SNAPSHOT_UPDATE=1`) + two consecutive default asserts → 10 passed each (5 byte + 5 event), deterministic.

### Notes (not deviations)

- The pre-existing non-fatal `sqlite3.IntegrityError (FOREIGN KEY) … INSERT INTO workflows` log line from `_drive` (documented in 01-01) still appears; it does not affect events or snapshots. Out of scope.
- `assert_seq_contiguous` is vacuous on today's engine (no `seq` stamped) but proven to RAISE on a synthetic gapped seq and to pass vacuously when no `seq` is present (unit-checked).

## Authentication Gates

None — all work was offline test code; no auth required.

## Known Stubs

None. Every event-snapshot test drives a real end-to-end `ExecutionEngine.execute()` run, asserts a non-empty documented event stream against a committed golden, and guards against vacuous pass (types-subset + required-keys assertions precede the equality compare — T-02-02).

## Self-Check: PASSED

- Created files exist: `_normalize.py` + 5 `*.events.json` goldens — FOUND.
- Commits exist: `1fceb13` (Task 1 helper), `eeead30` (Task 2 tests + goldens) — FOUND in `git log`.
- `cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py -q` → 10 passed (5 byte + 5 event), no env vars; ran twice, deterministic.
- 01-01 byte-snapshots: unchanged + still green (included in the 10 passed) — no regression.
- `test_phase3_cutover_verify.py` (import source): 8 passed — no regression.
- No runtime code modified: `git diff HEAD~2 --name-only` shows only `backend/tests/agents/**` (test modules + `_normalize.py` + golden) — `engine.py` / `factory.py` untouched.

---
phase: 01-0a-safety-net-deletion-guard
plan: 01
subsystem: testing / characterization harness
tags: [characterization, golden-snapshot, safe-01, offline-harness, deepagents]
requires:
  - "backend/tests/agents/_scripted_model.py::_drive (existing offline driver, D-01)"
  - "agents.execution_engine.engine.ExecutionEngine.execute (read-only, snapshotted)"
provides:
  - "deliverable byte-snapshots for prototype/od_prototype/prototype_revision/od_ppt/app_builder (SAFE-01 byte-identity half)"
  - "characterization/ package with golden-path + byte-snapshot helpers"
  - "od_ppt/ppt offline drivability (PPT agents scripted in _scripts_for)"
affects:
  - "01-02 (semantic event-stream snapshots — _normalize.py + *.events.json)"
  - "01-04 (CI backend:characterization job runs these tests offline)"
tech-stack:
  added: []
  patterns:
    - "byte-snapshot golden files gated behind SNAPSHOT_UPDATE=1 (D-07)"
    - "deliverable extracted from pipeline_complete.final_output (PATTERNS S4)"
    - "od_ alias resolution for agent-lookup-only in the offline driver (mirrors WS handler)"
key-files:
  created:
    - backend/tests/agents/characterization/__init__.py
    - backend/tests/agents/characterization/golden/prototype.html
    - backend/tests/agents/characterization/golden/od_prototype.html
    - backend/tests/agents/characterization/golden/prototype_revision.html
    - backend/tests/agents/characterization/golden/od_ppt.html
    - backend/tests/agents/characterization/golden/app_builder.txt
    - backend/tests/agents/test_characterization_prototype.py
    - backend/tests/agents/test_characterization_od_prototype.py
    - backend/tests/agents/test_characterization_prototype_revision.py
    - backend/tests/agents/test_characterization_od_ppt.py
    - backend/tests/agents/test_characterization_app_builder.py
  modified:
    - backend/tests/agents/_scripted_model.py
decisions:
  - "Extracted the deliverable from pipeline_complete.final_output for ALL five pipelines (event-stream, not disk read) — _drive uses a fresh temp RUNS_ROOT per call, so the event payload is the stable source (PATTERNS S4)."
  - "od_ppt deliverable is the VALIDATOR's streamed output (text/PPT class = last agent's output); scripted the validator to emit the deck wrapped in <artifact> so _resolve_final_output unwraps it to clean, deterministic, non-empty HTML."
  - "Resolved od_ aliases (od_prototype->prototype, ppt->od_ppt) for agent LOOKUP only inside _drive, mirroring the production WS handler — required because neither alias has its own AGENT.md (get_pipeline_agents returned ∅ → 'must contain at least 1 agent')."
metrics:
  duration: "~6 min"
  completed: "2026-06-06T21:37:40Z"
  tasks: 2
  files: 12
---

# Phase 1 Plan 01: Safety-Net Characterization Byte-Snapshots Summary

Offline deliverable byte-snapshots locking the current output of all five named pipeline families (`prototype`, `od_prototype`, `prototype_revision`, `od_ppt`, `app_builder`) byte-for-byte before any engine refactor — the byte-identity half of SAFE-01, with zero runtime-code changes.

## What Was Built

- **Task 1 — PPT scripts + alias resolution in the offline harness** (`_scripted_model.py`):
  - Added `_scripts_for` branches for the three od_ppt agents: `od-ppt-brief-analyst` (text slide plan), `od-ppt-composer` (text narration), `od-ppt-validator` (last agent → emits the final deck wrapped in `<artifact>`). Usage tuples are fixed for determinism.
  - Extended the `od_context` seeding block in `_drive` to cover `od_ppt`/`ppt` (the composer declares `injects=[template, design_system]`, the brief-analyst `injects=[template]`; without the context `_compose_injection` raises `TemplateMissingError`).
  - Added od_-alias resolution for **agent lookup only** (`od_prototype→prototype`, `ppt→od_ppt`), forwarding the unaliased label to `execute()` exactly as the production WS handler does.
- **Task 2 — characterization package + 5 byte-snapshot tests**:
  - `characterization/__init__.py`: `GOLDEN_DIR`, `SNAPSHOT_UPDATE`, `read/write_golden_bytes`, `extract_final_output` (reads `pipeline_complete.final_output`), and `assert_deliverable_snapshot` (non-empty guard on both paths + write-under-SNAPSHOT_UPDATE or byte-for-byte assert).
  - Five `test_characterization_<pipeline>.py` modules, each driving the pipeline offline and locking the deliverable against a committed non-empty golden.

## Deliverable-extraction mechanism (per pipeline)

All five use the **`pipeline_complete` event `final_output`** (PATTERNS S4 preferred mechanism — stable across `_drive`'s fresh-per-run temp `RUNS_ROOT`), encoded UTF-8 and snapshotted:

| Pipeline | Golden file | Bytes | Underlying deliverable source (in the engine) |
|----------|-------------|-------|------------------------------------------------|
| prototype | `prototype.html` | 84 | build loop's `prototype.html` on the run sandbox |
| od_prototype | `od_prototype.html` | 84 | same prototype build path (alias) |
| prototype_revision | `prototype_revision.html` | 48 | revision agent's in-place edit of `prototype.html` |
| od_ppt | `od_ppt.html` | 252 | last agent (validator) streamed output, `<artifact>`-unwrapped (text/PPT class) |
| app_builder | `app_builder.txt` | 88 | `serialize_sandbox_deliverable()` `filename:`-block bundle |

All goldens are non-empty (verified by the test's `len > 0` guard AND a `test -s` loop). The default no-env run asserts byte-for-byte (5 passed).

## od_context extension for PPT

Yes — the `od_context` seeding block in `_drive` (previously `("prototype", "od_prototype")` only) was extended to include `("od_ppt", "ppt")` so the PPT composer/brief-analyst `injects` resolve without `TemplateMissingError`. Confirmed by reading the od-ppt-composer/brief-analyst AGENT.md frontmatter (`injects: [template, design_system]` / `[template]`).

## Committed golden files

`backend/tests/agents/characterization/golden/`: `prototype.html`, `od_prototype.html`, `prototype_revision.html`, `od_ppt.html`, `app_builder.txt` — all staged and committed in `ed8cb18`; `git status` shows them tracked (no zero-byte golden).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] od_prototype and ppt drove zero agents → "Workflow must contain at least 1 agent"**
- **Found during:** Task 1 (regression check before committing).
- **Issue:** `_drive` calls `get_pipeline_agents(pipeline_type)` directly, which discovers agents by AGENT.md `pipeline_type` frontmatter. `od_prototype` has no AGENT.md of its own (it is an `_OD_ALIAS_BASE` alias of `prototype`), and `ppt` likewise has no agents (the deck agents declare `pipeline_type: od_ppt`). Both resolved to ∅ → the resolver rejected the run with a single `error` event. The plan's must-have requires `od_prototype` to drive.
- **Fix:** Added an `_OD_ALIAS_FOR_LOOKUP` map in `_drive` (`od_prototype→prototype`, `ppt→od_ppt`) used for the spec lookup ONLY; the unaliased label is still passed to `execute()`. This faithfully mirrors the production WS handler (resolve alias for agent lookup, forward original label) and matches engine.py's documented `_PROTOTYPE_PIPELINE_TYPES`/`_PPT_PIPELINE_TYPES` dual-spelling contract — it is not a fork of `_drive`'s logic (D-02 honored).
- **Files modified:** `backend/tests/agents/_scripted_model.py`
- **Commit:** `839ad8b`

### Notes (not deviations)

- A non-fatal `sqlite3.IntegrityError (FOREIGN KEY constraint failed) ... INSERT INTO workflows` is logged during `_drive` (the engine attempts to persist a workflow definition to a SQLite DB whose `users`/parent row is absent in the offline harness). It is pre-existing, does NOT interrupt the run (all events still flow through to `pipeline_complete`), and does not affect the snapshotted `final_output`. Out of scope for this tests-only plan; logged here for the verifier.

## Authentication Gates

None — all work was offline test code; no auth required.

## Known Stubs

None. Every characterization test drives a real end-to-end `ExecutionEngine.execute()` run and asserts a non-empty deliverable against a committed golden — no placeholder data, no empty snapshots.

## Self-Check: PASSED

- Created files exist: all 5 test modules + `characterization/__init__.py` + 5 golden files — FOUND.
- Commits exist: `839ad8b` (Task 1), `ed8cb18` (Task 2) — FOUND in `git log`.
- Default no-env run: `pytest tests/agents/test_characterization_*.py` → 5 passed.
- No runtime code modified: `git diff 04e9105..HEAD -- backend/agents/execution_engine/engine.py backend/agents/factory.py` → unchanged; all backend changes confined to `tests/agents/`.

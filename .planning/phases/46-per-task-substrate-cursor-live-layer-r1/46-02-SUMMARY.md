---
phase: 46-per-task-substrate-cursor-live-layer-r1
plan: 02
subsystem: infra
tags: [resume, artifacts, kernel, sandbox, durable-capture, file_bundle, RESUME-07]

# Dependency graph
requires:
  - phase: 45-resume-completeness-bug-fix-r0
    provides: the seed-durable-then-invoke test idiom + task-granular distinct-task_id counting
provides:
  - persist_task_html is now a GENERIC per-task capture — every file a task wrote to the run sandbox is durably captured per task_id (declared file → html_file dual-write byte-identical; siblings → file_bundle durable rows), deduped by content_hash, .uploads/ + PLANNER.md excluded, event-free
  - a complete durable per-task on-disk record for Plan 46-03 re-materialisation to restore
affects: [46-03 re-materialization, 46-04 skip-cursor, RESUME-08, RESUME-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Durable-mirror-only capture: write to the owner-scoped ScopedStore WITHOUT touching the in-memory ArtifactGraph, so context routing / _latest_typed_content stay byte-identical (INV-3 dormant) while the durable record is complete for resume"
    - "Reuse the exclusion-proven _collect_deliverable_relpaths walk (.uploads/ + PLANNER.md) for the sibling enumeration — the Phase-47/ND-10 fence comes free"

key-files:
  created:
    - backend/tests/agents/test_per_task_capture.py
  modified:
    - backend/agents/execution_engine/kernel_services.py

key-decisions:
  - "Sibling capture is DURABLE-STORE-ONLY, not a graph dual-write (deviation from the plan's _dual_write_artifact instruction) — required to keep the goldens dormant"
  - "Reuse file_bundle kind — no new ARTIFACT_KINDS member"
  - "Dedup by content_hash against store.tree() latest-per-location; force_db_version=True for DB-authoritative versioning (clarify-path idiom)"

patterns-established:
  - "Store-only durable capture at a kernel seam that must not perturb the in-memory typed graph"

requirements-completed: [RESUME-07]

# Metrics
duration: 40min
completed: 2026-07-19
---

# Phase 46 Plan 02: Generic Per-Task Capture Summary

**`persist_task_html` extended in place into a generic per-task capture — the declared deliverable stays a byte-identical `html_file` dual-write and every OTHER file a task wrote to the run sandbox is durably captured as a `file_bundle` row under the same `task_id`, deduped by `content_hash`, with `.uploads/`/`PLANNER.md` excluded and zero new WS events.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-07-19T00:00Z
- **Completed:** 2026-07-19
- **Tasks:** 2 (TDD RED → GREEN)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- Generic per-task sandbox capture at the single `persist_task_html` seam (INV-12 — no second writer): branch 1 = declared file `html_file` (unchanged), branch 2 = sibling walk → `file_bundle` durable rows.
- Content-hash dedup so an unchanged sibling (or the fix-loop re-persist under the same `task_id`) spawns no runaway versions (T-46-02-03 mitigated).
- `.uploads/` (Phase-47) and images (ND-10) never captured — free via the reused `_collect_deliverable_relpaths` exclusion.
- Goldens stay 10/10, lint-imports 4/0, KAN-88 remains the sole `restart_resume` red.

## Task Commits

1. **Task 1: RED — multi-file capture + byte-neutrality test** - `7679ec8e` (test)
2. **Task 2: GREEN — generic per-task capture** - `92aba363` (feat)

## Files Created/Modified
- `backend/tests/agents/test_per_task_capture.py` - multi-file capture (siblings → file_bundle), `.uploads/` exclusion, dedup (unchanged + changed sibling), prototype byte-neutrality; seed-durable-then-invoke harness reusing the Phase-45 idiom.
- `backend/agents/execution_engine/kernel_services.py` - `persist_task_html` extended with branch 2 (durable-store-only sibling capture); import block extended with `_collect_deliverable_relpaths` + `_DELIVERABLE_EXCLUDE`; `hashlib` + `uuid4` imports.

## RED → GREEN Evidence

RED (Task 1, on HEAD before the source change):
```
tests/agents/test_per_task_capture.py FFF.
test_multifile_task_capture_produces_sibling_file_bundles
  AssertionError: every non-declared sibling must be captured as file_bundle; got set()
  assert set() == {'nested/part_c.md', 'part_b.txt'}
test_sibling_dedup_no_runaway_versions  → got 0 refs (siblings absent)
test_sibling_recaptured_when_content_changes → got 0 (siblings absent)
test_prototype_byte_neutrality_single_html_file  → PASSED on HEAD (golden path unperturbed)
3 failed, 1 passed
```
GREEN (Task 2): `4 passed`. Full wave gate: `36 passed, 1 failed` (KAN-88 only).

## Decisions Made
- **Reuse `file_bundle`** — already an `ARTIFACT_KINDS` member; no vocabulary change (`grep -c '"task_file"' graph.py` → 0).
- **Dedup against `store.tree()`** (durable), not the in-memory graph, since sibling writes are store-only.
- **`_surface_partial_fragments` (engine.py:870) interaction documented:** it reads `file_bundle` off the *in-memory* graph for the budget-abort payload; because siblings are store-only they never enter that in-memory read on a first run — on a RESUMED run they arrive via `_hydrate_artifacts_from_store` (46-03) and would surface as semantically-correct partial results (golden-dormant: goldens never resume nor budget-abort).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Sibling capture must be durable-store-only, not a graph `_dual_write_artifact`**
- **Found during:** Task 2 (GREEN) — the goldens `test_characterization_prototype` and `test_characterization_od_prototype` diverged (2 failed) after the first implementation followed the plan's `_dual_write_artifact(..., kind="file_bundle")` instruction.
- **Issue:** The RESEARCH/plan premise "a golden prototype run writes only `prototype.html` → siblings = ∅" is **false**. The `task_loop` reference-file writer (task_loop.py:479-493) writes `spec.md`/`design.md`/`tasks.md` (and od_prototype writes template seed files at engine.py:1141-1143) into the sandbox before the build tasks. My sibling walk captured those into the in-memory `ArtifactGraph` under `producer_agent="prototype-build"`. `_latest_typed_content(producer_agent)` (engine.py:5509-5537) returns the **MAX-`version` ref across ALL kinds** for that agent, so a sibling `file_bundle` out-versioned the `html_file` and corrupted what the NEXT build task reads → the build agent's `context_message` diverged (index 16 in the golden event stream). Confirmed causation by reverting the source file (golden passed) and re-applying.
- **Fix:** Branch 2 writes siblings to the run's owner-scoped `ScopedStore` **only** (construct `ArtifactRef` + `await store.write_ref(ref, force_db_version=True)`), leaving `ectx.artifacts` untouched. Branch 1 (the declared file) still dual-writes graph + store unchanged. Context routing / `_latest_typed_content` are byte-identical, and Plan 46-03 re-materialisation reads `store.tree()` (durable), not the in-memory graph, so the durable record is still complete.
- **Files modified:** `backend/agents/execution_engine/kernel_services.py`
- **Verification:** `SNAPSHOT_UPDATE= pytest tests/agents/test_characterization_*.py -q` → `10 passed`; the 4 capture tests pass; lint-imports 4/0.
- **Committed in:** `92aba363` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 bug).
**Impact on plan:** Necessary to hold INV-3 (goldens 10/10 — a LOCKED phase gate). No scope creep — the durable per-task capture contract (RESUME-07 must_haves: "captured as file_bundle rows deduped by content_hash") is fully satisfied; only the write *target* changed from graph+store to store-only. The `contains: _collect_deliverable_relpaths` and `key_links` artifact assertions still hold. The plan's `key_link` "persist_task_html sibling walk → engine._dual_write_artifact" is superseded by a direct `store.write_ref` for siblings (branch 1 still uses `_dual_write_artifact`).

## Issues Encountered
- Plan path in the execution context (`backend/.planning/...`) was stale — `.planning/` lives at the repo root. Located the real plan and proceeded.

## Threat Flags
None — no new endpoint/auth surface. The walk reads only this run's `RunSandbox` root (traversal-proof); the write goes through the run's own owner-scoped `ScopedStore` (default-deny). Threat register T-46-02-01..04 mitigations hold (`.uploads/` excluded, content-hash dedup, owner-scoped read/write).

## Next Phase Readiness
- Plan 46-03 (re-materialization) can restore a task's full on-disk output from the durable `file_bundle` rows now written per `task_id`.
- **Note for 46-03:** siblings live in the durable store ONLY (not the first-run in-memory graph). `_hydrate_artifacts_from_store` will adopt them into the graph on resume — that is the intended re-materialization path; do not assume first-run graph presence.

## Self-Check: PASSED

- FOUND: backend/tests/agents/test_per_task_capture.py
- FOUND: backend/agents/execution_engine/kernel_services.py
- FOUND: .planning/phases/46-per-task-substrate-cursor-live-layer-r1/46-02-SUMMARY.md
- FOUND commit: 7679ec8e (test RED)
- FOUND commit: 92aba363 (feat GREEN)

---
*Phase: 46-per-task-substrate-cursor-live-layer-r1*
*Completed: 2026-07-19*

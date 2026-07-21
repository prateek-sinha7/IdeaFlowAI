---
phase: 46-per-task-substrate-cursor-live-layer-r1
plan: 03
subsystem: infra
tags: [resume, artifacts, kernel, sandbox, re-materialization, merge-re-entry, RESUME-08]

# Dependency graph
requires:
  - phase: 46-per-task-substrate-cursor-live-layer-r1
    provides: "Plan 46-02's generic per-task durable capture — the file_bundle sibling rows (durable-store-only) that this plan restores to disk"
  - phase: 45-resume-completeness-bug-fix-r0
    provides: the seed-durable-then-invoke test idiom + _hydrate_artifacts_from_store graph-only twin
provides:
  - "_rematerialize_artifacts_to_disk(ectx, sandbox) — the DISK half of resume: latest durable file-backed refs (max-version, .uploads/-excluded, file-kinds-only) written onto the fresh RunSandbox BEFORE strategies re-enter, reconstructed from artifact_refs never git"
  - "the :1350 resume hook gated on _is_resume (not only _resume_from>0) so the in-flight wave at offset==0 gets its fragments back — enabling correct mid-wave merge re-entry via the EXISTING run_fanout->_merge_fragments (no second merge impl)"
affects: [46-04 skip-cursor, RESUME-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Durable → disk re-materialization mirroring the graph-only _hydrate_artifacts_from_store: same owner-scoped store.tree read + best-effort degrade, but sandbox.write instead of graph.adopt; per-location max(version) wins; file-backed kinds only"
    - "wave_runs.status as the merged-vs-unmerged discriminator: completed ⇒ merge ran (wave skipped); running/absent ⇒ in-flight wave whose merge re-runs over re-materialized + newly-run fragments"

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_restart_resume.py

key-decisions:
  - "Filter to kind in {html_file, file_bundle, deliverable} — the file-backed kinds that map to a real on-disk relpath; the typed metadata kinds (spec/plan/clarifications/…) are graph-only handoffs already restored by hydrate and have no disk file"
  - "Gate on _is_resume, NOT only _resume_from>0 — the in-flight wave at offset==0 IS the first incomplete step and its already-persisted fragments must be back on disk for the whole-wave merge re-entry (Edge-Case 6)"
  - "No second merge implementation (INV-12) — re-materialization only restores fragments; the existing wave_scheduler whole-wave re-run drives run_fanout→_merge_fragments over the recovered fragments"

patterns-established:
  - "Reverse-of-capture durable→disk restore at the resume seam, symmetric with the Plan 46-02 sandbox.read capture (CRLF round-trip parity)"

requirements-completed: [RESUME-08]

# Metrics
duration: 35min
completed: 2026-07-19
---

# Phase 46 Plan 03: Durable→Disk Re-Materialization + Merge Re-Entry Summary

**Added the missing DISK half of resume: `_rematerialize_artifacts_to_disk(ectx, sandbox)` walks the latest durable file-backed `artifact_refs` (by `location`, `max(version)`, filtered to `html_file`/`file_bundle`/`deliverable` with `.uploads/` excluded) and writes their content back onto the fresh `RunSandbox` BEFORE strategies re-enter — wired at the `:1350` resume point gated on `_is_resume` so the in-flight wave at offset==0 gets its fragments back, enabling correct mid-wave merge re-entry through the EXISTING `run_fanout`→`_merge_fragments` machinery (no second merge impl).**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-19
- **Tasks:** 2 (TDD RED → GREEN)
- **Files modified:** 2 (0 created, 2 modified)

## Accomplishments
- `_rematerialize_artifacts_to_disk` mirrors the graph-only `_hydrate_artifacts_from_store` skeleton (owner-scoped `store.tree(run_id)` read + best-effort degrade) but writes to disk via `sandbox.write` (traversal-proof `path_for`) instead of `graph.adopt`.
- Per-location `max(version)` wins (fix-loop re-persist / fan-out fragment versions → latest content is the disk truth); `.uploads/` (Phase-47 fence) and non-file kinds (`spec`/`plan`/`clarifications`/…) never reach disk.
- Reconstructed from `artifact_refs` ONLY, never git (POR §3.2); reads the run's own owner-scoped `ScopedStore` (default-deny — a foreign row cannot appear, so it cannot reach disk).
- Mid-wave merge re-entry closed: fragments persisted before the merge are re-materialized so the existing whole-wave re-run merges over the recovered fragments — `wave_runs.status` is the merged/unmerged discriminator, documented in the method docstring. NO second merge implementation (INV-12).
- Dormant on a normal run (gated on `_is_resume`): goldens 10/10 with `SNAPSHOT_UPDATE` unset; lint-imports 4/0; INV-1 grep 0; INV-12 enumerate-pin 1; KAN-88 remains the sole `restart_resume` red.

## Task Commits

1. **Task 1: RED — re-materialization + merge-re-entry tests** - `3e891a6a` (test)
2. **Task 2: GREEN — _rematerialize_artifacts_to_disk + the :1350 resume hook** - `d995dd4d` (feat)

## Files Modified
- `backend/agents/execution_engine/engine.py` — new `_rematerialize_artifacts_to_disk(self, ectx, sandbox)` beside `_hydrate_artifacts_from_store`; the `:1350` hook `if _is_resume: await self._rematerialize_artifacts_to_disk(ectx, sandbox)` immediately after the hydrate call.
- `backend/tests/agents/test_restart_resume.py` — `test_rematerialize_restores_durable_files_to_disk` (declared + sibling restored, max-version wins, `.uploads/` + non-file kinds filtered) and `test_midwave_merge_reentry_rematerializes_fragments` (two worker fragment rows + a `running` `wave_runs` row → fragments re-materialize so the existing merge re-runs); plus `_build_rematerialize_ctx` / `_seed_ref` seed helpers reusing the Phase-45/46-02 idiom.

## RED → GREEN Evidence

RED (Task 1, on HEAD before the source change):
```
tests/agents/test_restart_resume.py::test_rematerialize_restores_durable_files_to_disk
  AttributeError: 'ExecutionEngine' object has no attribute '_rematerialize_artifacts_to_disk'
tests/agents/test_restart_resume.py::test_midwave_merge_reentry_rematerializes_fragments
  AttributeError: 'ExecutionEngine' object has no attribute '_rematerialize_artifacts_to_disk'
Full file: 8 passed, 3 failed (KAN-88 + the 2 new RED)
```
GREEN (Task 2): the 2 new tests pass. Full file `10 passed, 1 failed` (KAN-88 the sole remaining red — verify-by-delta).

## Verification (verify-by-delta)
- `test_restart_resume.py` → `10 passed, 1 failed` (KAN-88 only; the fail count did not increase — 8 original + 2 new GREEN).
- `test_wave_scheduler.py` → `10 passed` (mid-wave behavior intact).
- `test_characterization_*.py` (5 files) → `10 passed` with `SNAPSHOT_UPDATE` unset (re-materialization dormant on non-resume).
- `test_fanout.py` + `test_subagent_runs.py` + `test_banned_patterns.py` → `50 passed`.
- `/opt/homebrew/bin/lint-imports` → `Contracts: 4 kept, 0 broken.`
- `grep -cE 'pipeline_type ==|spec\.id ==' engine.py` → `0`; `grep -c 'for i, spec in enumerate(ordered_agents)' engine.py` → `1`.

## Decisions Made
- **File-backed kinds only** (`html_file`/`file_bundle`/`deliverable`) — matches exactly what the Plan 46-02 generic capture writes; the graph-only metadata kinds have no disk file and are already restored by hydrate.
- **`_is_resume` gate, not `_resume_from > 0`** — the in-flight wave at offset==0 needs its fragments on disk for the merge re-entry (Edge-Case 6); mirrors the CR-01 workspace-recovery reasoning.
- **Reuse the existing merge machinery** — re-materialization only restores fragments; the merge itself is the untouched `wave_scheduler` whole-wave re-run → `run_fanout` → `_merge_fragments` (INV-12, no parallel merge).
- **Symmetric codec** — capture (46-02) reads via `sandbox.read`; re-materialize writes via `sandbox.write` (both LocalWorkspace UTF-8) → CRLF round-trip parity (Pitfall/Edge-Case 3).

## Deviations from Plan

None — plan executed exactly as written. The upstream 46-02 deviation (siblings are DURABLE-STORE-ONLY, not in the first-run in-memory graph) is exactly what this plan's durable `store.tree()` read consumes; no adjustment needed.

## Interaction Notes (for downstream plans)
- **Pitfall 1 (input_hash stability):** re-materialization restores the exact stored `content`, so `content_hash`es are unchanged → completed-step reuse keys are unperturbed.
- **Pitfall 2 (workspace recovery):** the read rides `ectx.scoped_store` (the ORIGINAL owner+workspace), never a fresh-minted workspace.
- **Plan 46-04 (skip cursor)** can now safely skip completed tasks/workers — their files are already back on disk after this re-materialization, so the next task's skeleton read / the wave merge are coherent.

## Threat Flags
None — no new endpoint/auth surface. The read is the SAME owner-scoped `store.tree(run_id)` hydrate already uses (default-deny); `sandbox.write` is traversal-proof via `path_for`; `.uploads/` is filtered out. Threat register T-46-03-01..04 mitigations hold.

## Self-Check: PASSED

- FOUND: backend/agents/execution_engine/engine.py (`_rematerialize_artifacts_to_disk`)
- FOUND: backend/tests/agents/test_restart_resume.py (2 new tests)
- FOUND: .planning/phases/46-per-task-substrate-cursor-live-layer-r1/46-03-SUMMARY.md
- FOUND commit: 3e891a6a (test RED)
- FOUND commit: d995dd4d (feat GREEN)

---
*Phase: 46-per-task-substrate-cursor-live-layer-r1*
*Completed: 2026-07-19*

---
phase: 03-token-trim-measured-change-0c
plan: 01
subsystem: engine
tags: [execution-engine, prototype-build, context-compaction, token-trim, html-skeleton, deepagents]

# Dependency graph
requires:
  - phase: 02-executioncontext-ownership-0b
    provides: "ectx threading through _build_context_message (current_task_block, od_context on ExecutionContext)"
  - phase: 00-characterization
    provides: "offline _scripted_model._drive harness + characterization snapshot split (semantic events held / deliverable bytes re-baselineable)"
provides:
  - "build-task-2+ context compaction live: _extract_html_skeleton wired into _build_context_message (COMPACT-01 / L13 wired, not deleted)"
  - "deterministic offline >=50% reduction CI gate (COMPACT-03) on a multi-page HTML fixture"
  - "read-before-edit framing: skeleton block carries a literal read_file('prototype.html') pointer (Req 7)"
affects: [phase-07-capability-reexpression, PARITY-04, CompactionStrategy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Branch on the already-computed is_build_task_2_plus flag inside _build_context_message — no new state, no signature change"
    - "Deterministic prompt-size gate via a direct _build_context_message call on an inline multi-page HTML fixture (offline, no DB/Bedrock/API key)"

key-files:
  created:
    - backend/tests/agents/test_phase3_compaction.py
  modified:
    - backend/agents/execution_engine/engine.py

key-decisions:
  - "Skeleton marker '=== CURRENT PROTOTYPE (skeleton — call read_file(prototype.html) for full content before editing) ===' (D-01: distinct from --- CURRENT HTML ---, carries the read_file pointer)"
  - "Test placement in a new module backend/tests/agents/test_phase3_compaction.py (D-64 discretion)"
  - "Full-HTML baseline reconstructed inline by swapping the skeleton block back for the full-HTML block (D-02), so the >=50% ratio measures the real injection-site delta"

patterns-established:
  - "0C compaction rides the existing is_build_task_2_plus branch; task 1 + non-build agents unchanged; empty/[Error: guard preserved"
  - "Ratchet self-check test asserts task-1 vs task-2 injection paths diverge so the gate is non-vacuous"

requirements-completed: [COMPACT-01, COMPACT-03]

# Metrics
duration: ~25min
completed: 2026-06-07
---

# Phase 3 Plan 01: Token-Trim build-task-2+ context compaction Summary

**Wired the dead `_extract_html_skeleton` into `_build_context_message`'s `is_build_task_2_plus` branch — the build-task-2+ prompt now carries a ~419-char skeleton state-map (with a `read_file('prototype.html')` pointer) instead of the full current HTML, proven by an offline >=50% CI gate (measured 96.9% reduction on a multi-page fixture).**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-07
- **Tasks:** 2
- **Files modified:** 2 (1 engine edit + 1 new test module)

## Accomplishments
- `_extract_html_skeleton` is now invoked on the `prototype-build` build-task-2+ context path (COMPACT-01 / ledger L13 wired). The full `--- CURRENT HTML (modify this … ---` block (up to 120k chars) is replaced by the compact skeleton state-map; task 1 (HTML shell) keeps the full-HTML block unchanged; the empty/`[Error:` guard is preserved exactly.
- The skeleton block is framed as a state-map (not editable source) and carries a literal `read_file('prototype.html')` read-before-edit pointer (Req 7) — no AGENT.md edit needed (the prototype-build prompt already mandates `read_file`).
- A deterministic, fully-offline CI gate (`test_phase3_compaction.py`) asserts the task-2 message is <=50% of the full-HTML version on a >=2-page fixture (COMPACT-03), plus skeleton-marker presence/absence, task-1 control, read_file pointer + native fs tool access, and a ratchet self-check.
- Covers both `prototype` and `od_prototype` automatically (the od alias rides the same `prototype-build` path).

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire _extract_html_skeleton into the is_build_task_2_plus branch** - `3907274` (feat/engine)
2. **Task 2: Add the deterministic offline >=50% reduction gate** - `cddb293` (test/tests)

_Note: Task 1 was implemented TDD-style — the engine edit and its driving test (Task 2's module) were authored together; the test was verified to FAIL when the edit is reverted before the commits were split by scope._

## Files Created/Modified
- `backend/agents/execution_engine/engine.py` - `_build_context_message`: the `if spec.id == "prototype-build":` HTML branch now calls `self._extract_html_skeleton(current_html)` on the `is_build_task_2_plus` path and emits the distinct skeleton block; the task-1 else branch keeps the full-HTML block verbatim. `_extract_html_skeleton`'s body and the `=== TEMPLATE COMPLIANCE ===` block are byte-unchanged.
- `backend/tests/agents/test_phase3_compaction.py` - 5 offline tests: the >=50% gate, skeleton-markers-present/full-HTML-absent, task-1 full-HTML control, read_file pointer + `exclude_builtin=False` (native fs tools) access, and a task-1-vs-task-2 divergence ratchet.

## Measured token reduction (COMPACT-03 evidence — deterministic gate)

On the in-test multi-page fixture (2 `<section data-page>` sections — dashboard + settings — with `:root` tokens and a `const routes` map; ~29,749 chars of HTML):

| Metric | Value |
|--------|-------|
| Fixture HTML | 29,749 chars |
| Skeleton state-map | 419 chars |
| Compacted task-2 message | 941 chars |
| Full-HTML task-2 message (old behavior) | 30,227 chars |
| **Reduction** | **96.9% (ratio 0.031)** — far exceeds the 50% floor |

**Reproduction (offline, no DB/Bedrock/API key):**
```bash
cd backend && python3.11 -m pytest tests/agents/test_phase3_compaction.py -v
```

**Note on COMPACT-03 Requirement 3 (real-run live token delta):** This plan delivers the
deterministic CI gate (Requirement 2). The real-run live-model token-delta evidence
(Requirement 3, D-04 opt-in live test) and the deliverable re-baseline / pages-routes parity
(Requirements 4–6, D-03) are the remaining 0C scope (ROADMAP candidate plan 03-02) and were
not implemented here. The scripted characterization harness writes a fixed 84-byte HTML
regardless of prompt, so the prototype/od_prototype deliverable byte-goldens are a no-op diff
under the scripted model (confirmed: `test_characterization_prototype.py` +
`test_characterization_od_prototype.py` pass with NO golden edit) — the real byte/token change
is only observable under a live model run.

## Decisions Made
- **Skeleton marker (D-01):** `=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') for full content before editing) ===` / `=== END CURRENT PROTOTYPE ===` — visually distinct from `--- CURRENT HTML ---` and carries the read_file pointer.
- **Test placement (D-64):** new `backend/tests/agents/test_phase3_compaction.py`.
- **>=50% baseline (D-02):** reconstructed inline by swapping the skeleton block back for the full-HTML block in the real task-2 message, so the ratio measures exactly the injection-site delta.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## Verification Results
- `cd backend && python3.11 -m pytest tests/agents/test_phase3_compaction.py -v` → 5 passed (offline).
- Ratchet confirmed: simulating a revert of the engine edit fails 4 of the 5 tests.
- `grep -c "_extract_html_skeleton" backend/agents/execution_engine/engine.py` → 3 (def + call + comment); call site is inside `_build_context_message` (engine.py:2537).
- L13 in `specs/003-workflow-engine-decoupling/migration-ledger.md` is still `☐`; `test_migration_ledger.py` → 4 passed, 1 skipped.
- `vulture agents/execution_engine/engine.py --min-confidence 80` does NOT flag `_extract_html_skeleton` (now called); no allow-list entry added.
- `test_characterization_prototype.py` + `test_characterization_od_prototype.py` → 4 passed with NO golden edits (semantic event snapshots held green; scripted deliverable bytes unchanged).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- COMPACT-01 (skeleton wired) and COMPACT-03 (deterministic CI gate) are live for both `prototype` and `od_prototype`.
- Remaining 0C scope (candidate plan 03-02): real-run live token-delta evidence (Req 3 / D-04), prototype + od_prototype deliverable byte re-baseline (Req 5), and the pages/routes + validation parity assertion (Req 6 / D-03).
- Phase 7 (out of scope here): re-express this inline wiring as a registered `CompactionStrategy(html_skeleton)` and delete the inline helper (flips L13 → ☑, PARITY-04).

## Self-Check: PASSED

- FOUND: backend/agents/execution_engine/engine.py
- FOUND: backend/tests/agents/test_phase3_compaction.py
- FOUND: .planning/phases/03-token-trim-measured-change-0c/03-01-SUMMARY.md
- FOUND commit: 3907274 (Task 1, engine)
- FOUND commit: cddb293 (Task 2, tests)

---
*Phase: 03-token-trim-measured-change-0c*
*Completed: 2026-06-07*

---
phase: 01-safety-net-deletion-guard-0a
plan: 03
subsystem: testing
tags: [migration-ledger, ci-ratchet, grep, pytest, inv-12, deletion-guard]

# Dependency graph
requires:
  - phase: 01-safety-net-deletion-guard-0a
    provides: "01-CONTEXT decisions D-08/D-09/D-10 (standalone ledger mirroring §31, ☑-row grep ratchet, green/empty in Phase 1)"
provides:
  - "specs/003-workflow-engine-decoupling/migration-ledger.md — operational mirror of plan §31 (all 20 L#/F#/D# rows, verbatim grep patterns, Status column, all ☐)"
  - "backend/tests/agents/test_migration_ledger.py — CI ratchet asserting each ☑ grep row's pattern → 0 in backend/, with a proven non-vacuous negative guard"
affects: [phase-2, phase-3, phase-7, phase-1b, "01-04 (wires backend:characterization CI job that runs this test)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Ledger-as-data: a markdown table parsed by CI; status column drives enforcement"
    - "Ratchet test: ☑ rows enforce grep→0, ☐ rows skip (green/empty until owning phase deletes)"
    - "Explicit CHECK/test: marker distinguishes prose-gate rows from grep-pattern rows"
    - "Non-vacuity guard: synthetic ☑ row with a known-present token proves classifier+grep are live"

key-files:
  created:
    - "specs/003-workflow-engine-decoupling/migration-ledger.md"
    - "backend/tests/agents/test_migration_ledger.py"
  modified: []

key-decisions:
  - "CHECK rows distinguished by explicit `CHECK:`/`test:` marker (not metacharacter heuristics) — robust for single-token grep patterns like SKIP_PLANNER_FOR_PROTOTYPE"
  - "Gate cells strip surrounding markdown backticks before grep so backtick-wrapped identifiers match"
  - "Repo-root depth = Path(__file__).resolve().parents[3] (tests/agents → tests → backend → repo), verified"
  - "Non-vacuity token = _PROTOTYPE_PIPELINE_TYPES (confirmed present in engine.py:105 + :375)"

patterns-established:
  - "Migration ledger ratchet: ☐→☑ flip per owning phase permanently bans the deleted symbol"
  - "Every CI guard ships a non-vacuity test proving it actually fires"

requirements-completed: [DEL-01, DEL-02, DEL-03, DEL-04, SAFE-04]

# Metrics
duration: 3min
completed: 2026-06-06
---

# Phase 1 Plan 03: Migration Ledger + Deletion-Guard Ratchet Summary

**Standalone migration-ledger.md mirroring all 20 §31 rows (verbatim grep patterns, all ☐) plus a pytest CI ratchet that asserts each ☑ grep row → 0 matches in backend/, proven non-vacuous against a known-present token.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-06T21:40:55Z
- **Completed:** 2026-06-06T21:43:48Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- Created `specs/003-workflow-engine-decoupling/migration-ledger.md` mirroring plan §31 faithfully: all 20 ledger items (L1, L2/L9, L3, L4/L8, L5, L6, L7, L10, L11, L12, L13, L14, L15, L16, D1, F1–F5), same columns, grep patterns copied verbatim, plus a `Deleting SHA` column (DEL-04). Every row Status = `☐` (D-10) → guard green/empty.
- Created `backend/tests/agents/test_migration_ledger.py`: parametrized deletion ratchet over `☑` grep rows (grep→0 in `backend/`), CHECK-row skip, parse/pending assertion, CHECK-classification assertion, and a non-vacuity negative guard.
- Test suite passes: 3 passed, 1 skipped (the deletion ratchet, green/empty per D-10). No runtime code touched.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create migration-ledger.md mirroring every §31 row (all ☐)** - `982f20b` (docs)
2. **Task 2: Create test_migration_ledger.py ratchet with a non-vacuous negative guard** - `66e9b9d` (test)

**Plan metadata:** see final docs commit.

## Files Created/Modified
- `specs/003-workflow-engine-decoupling/migration-ledger.md` - Operational single-source-of-truth ledger mirroring plan §31; 20 rows, all `☐`, legend + ratchet rule + gate-cell convention.
- `backend/tests/agents/test_migration_ledger.py` - CI ratchet: parses the ledger, enforces `☑` grep rows → 0 matches in `backend/`, skips CHECK rows, asserts all §31 ids present and pending, proves non-vacuity.

## Decisions Made
- **CHECK vs grep classification by explicit marker.** Initially attempted a metacharacter-heuristic classifier; it misclassified single-token grep patterns (e.g. `SKIP_PLANNER_FOR_PROTOTYPE`) as prose. Switched to an explicit `CHECK:`/`test:` marker on the three prose rows (L16, F4, F5). The parser treats marker-bearing cells as `(item, None)` (skipped); all other gate cells are grep patterns.
- **Backtick stripping.** Ledger wraps identifiers in markdown backticks; `_gate_pattern()` strips them so grep sees the bare pattern.
- **Repo-root depth verified** as `parents[3]` (resolves to repo root, confirmed at author time).
- **Non-vacuity token = `_PROTOTYPE_PIPELINE_TYPES`** (confirmed present via subprocess grep before use; returncode 0, matches in engine.py).

### §31-vs-ledger row diff
**0.** All 20 required item ids (L14, L16, D1, L13, L1, L2/L9, L3, L4/L8, L5, L6, L7, L10, L11, L12, L15, F1, F2, F3, F4, F5) are present; `test_ledger_parses_and_all_phase1_rows_pending` asserts this in-suite.

### Grep rows vs CHECK rows (parser convention)
- **CHECK rows (L16, F4, F5):** gate cell carries the literal `CHECK:` marker → classified prose → yielded `(item, None)` → `pytest.skip()`. Their enforcement lives in dedicated tests in their owning phase (Phase 0B / Phase 3), not the grep ratchet.
- **Grep rows (all others):** gate cell is a verbatim `grep -rnE` pattern; when the row is `☑`, grep over `backend/` must return 0 matches. In Phase 1 all rows are `☐`, so the parametrized list is empty → a single sentinel `(__none__, None)` → skipped (green/empty, D-10).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CHECK/grep classifier misclassified single-token grep rows**
- **Found during:** Task 2 (test authoring/verification)
- **Issue:** The first classifier used regex-metacharacter heuristics to distinguish CHECK rows from grep rows. A single-token grep pattern with no metacharacters and no leading-underscore (e.g. `SKIP_PLANNER_FOR_PROTOTYPE`) was wrongly classified as prose, which would have silently dropped a real grep row from the ratchet — exactly the false-green threat T-03-01. Caught by `test_check_rows_classified_as_check`.
- **Fix:** Replaced the heuristic with an explicit `CHECK:`/`test:` marker check, added `_gate_pattern()` to strip markdown backticks, and removed the now-unused `re` import.
- **Files modified:** backend/tests/agents/test_migration_ledger.py
- **Verification:** Full suite re-run → 3 passed, 1 skipped; the CHECK-classification test and non-vacuity guard both pass.
- **Committed in:** `66e9b9d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** The fix hardens the very anti-false-green property the plan mandates (T-03-01). No scope creep; no runtime code touched.

## Issues Encountered
- The zsh shell expanded `--include=*.py` during ad-hoc verification (`no matches found`); re-ran the check via a Python `subprocess` call (no shell), which is how the test itself invokes grep — confirming the pattern is found. Not a code issue.

## Threat Mitigations Applied
- **T-03-01 (false-green / vacuous ratchet):** `test_guard_fails_on_known_present_pattern` runs the same parse+classify+grep logic against a synthetic `☑` row whose pattern (`_PROTOTYPE_PIPELINE_TYPES`) exists in `backend/`, asserting it is classified as a grep row AND found — proving the ratchet fires.
- **T-03-02 (ledger drift from §31):** `test_ledger_parses_and_all_phase1_rows_pending` asserts every required id present and all `☐`.
- **T-03-03 (wrong repo-root → silent 0 matches):** the non-vacuity guard greps a known-present token; a wrong root would fail it immediately.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The deletion guard is armed and green/empty. As Phase 0B/2/3/7/1B delete legacy elements, flip the corresponding row to `☑` (and fill the Deleting SHA) — the ratchet then permanently bans the pattern.
- The `backend:characterization` CI job that RUNS this test is wired by sibling plan 01-04.
- No blockers.

## Self-Check: PASSED

- FOUND: specs/003-workflow-engine-decoupling/migration-ledger.md
- FOUND: backend/tests/agents/test_migration_ledger.py
- FOUND: .planning/phases/01-safety-net-deletion-guard-0a/01-03-SUMMARY.md
- FOUND commit: 982f20b (Task 1)
- FOUND commit: 66e9b9d (Task 2)

---
*Phase: 01-safety-net-deletion-guard-0a*
*Completed: 2026-06-06*

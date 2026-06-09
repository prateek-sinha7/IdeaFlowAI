---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 07
subsystem: engine
tags: [task_loop, validation-fix-loop, kernel-services, INV-3, INV-12, no-dual-implementations, characterization-parity]

# Dependency graph
requires:
  - phase: 07-prototype-as-manifest-parity-proof-sc-001-2 (07-04/07-05)
    provides: "KernelServices.run_validation_fix_loop — the single engine-owned fix-loop handle the strategy delegates to"
provides:
  - "task_loop.py holds exactly ONE validation-fix path (delegated unconditionally to the engine via runner.run_validation_fix_loop) — dead else-branch, _SkippedRender, and duplicated pure helpers removed"
  - "test_strategies fix-loop double re-pointed onto run_validation_fix_loop (drives the same path real runs take)"
  - "truthful ctx.runner contract docstring (no run_fix_agent handle advertised; kernel_services already had none)"
affects: [07-verification, 07-review-deep, cluster-C-gap-closure]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-home delegation: a strategy carries NO copy of a kernel behavior; it reaches the behavior only through the ctx.runner handle (INV-3/INV-12)"
    - "RED→GREEN deletion guard: re-point the only test that drove a dead branch onto the live path BEFORE deleting the dead branch (T-07-07-01)"

key-files:
  created: []
  modified:
    - "backend/agents/capabilities/strategies/task_loop.py — deleted the dead dual fix-loop + duplicate helpers + _SkippedRender; pruned run_fix_agent docstring"
    - "backend/tests/agents/test_strategies.py — _FakeRunner re-pointed onto run_validation_fix_loop; imports _select_issues_to_fix from the engine"

key-decisions:
  - "kernel_services.py already advertised no run_fix_agent (WR-08 target was the task_loop.py:50 docstring bullet, not a kernel_services mention) — verified by grep, no edit needed there"
  - "Kept _now()/import time in task_loop.py — still used by the task_loop_progress event payload (NOT orphaned by the deletion)"
  - "The _FakeRunner.run_validation_fix_loop fake reproduces the bounded N=2 decision using the engine's _select_issues_to_fix (the single selection home), so the test drives the real delegation contract"

patterns-established:
  - "No dual implementations: when an abstraction supersedes code, the superseded code is DELETED in the same plan — verified by a grep gate in the verify block"
  - "Deletion is golden-safe when proven by characterization snapshots run in a clean session with byte-unchanged goldens"

requirements-completed: [PARITY-09]

# Metrics
duration: 6min
completed: 2026-06-09
---

# Phase 07 Plan 07: Delete the Dead Dual Validation Fix-Loop in task_loop Summary

**Removed the INV-3/INV-12 dual implementation of the validation fix-loop from `task_loop.py` — the dead `else` branch, the in-strategy `_run_validation_fix_loop`, `_SkippedRender`, and the duplicated `_select_issues_to_fix`/`_static_issue_sigs`/`_console_sigs` are gone; the strategy now delegates unconditionally to the engine's single `run_validation_fix_loop`, with the fix-loop tests re-pointed onto that same path first (RED→GREEN guard).**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-09T11:41:58Z
- **Completed:** 2026-06-09T11:47:39Z
- **Tasks:** 2
- **Files modified:** 2 (plus deferred-items.md log)

## Accomplishments
- Re-pointed `_FakeRunner` in `test_strategies.py` onto `run_validation_fix_loop` (the handle the strategy delegates to), importing `_select_issues_to_fix` from the single engine home — proving the fix-loop assertions drive the live path BEFORE deletion.
- Deleted the dead dual implementation from `task_loop.py`: the `else: # pragma: no cover` fallback, the in-strategy `_run_validation_fix_loop` (~135 lines), the `_SkippedRender` stand-in, the duplicated pure helpers, and the now-unused `_MAX_FIX_ATTEMPTS` const (net −263 lines in `task_loop.py`).
- `TaskLoopStrategy.run` now calls `await runner.run_validation_fix_loop(...)` unconditionally — exactly one validation-fix path.
- Pruned the `run_fix_agent` bullet from the `ctx.runner` contract docstring; verified `kernel_services.py` already advertises no `run_fix_agent` (WR-08 satisfied).

## Task Commits

Each task was committed atomically:

1. **Task 1: Re-point test_strategies onto run_validation_fix_loop (RED→GREEN guard)** - `5540b5d` (test)
2. **Task 2: Delete the dead dual fix-loop + duplicate helpers; prune run_fix_agent docstring** - `cc716cd` (refactor)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `backend/tests/agents/test_strategies.py` - `_FakeRunner.run_fix_agent` replaced by `run_validation_fix_loop` driving the bounded N=2 decision via the engine's `_select_issues_to_fix`; added the engine-home import.
- `backend/agents/capabilities/strategies/task_loop.py` - dead dual fix-loop, `_SkippedRender`, duplicated pure helpers, and `_MAX_FIX_ATTEMPTS` deleted; `run()` delegates validation+fix unconditionally to the handle; docstring corrected.
- `.planning/phases/07-.../deferred-items.md` - logged a pre-existing test-isolation pollution discovery (see Issues Encountered).

## Decisions Made
- `kernel_services.py` needed no edit for WR-08: it already exposes no `run_fix_agent` (grep-verified). The misadvertised `run_fix_agent` lived only in the strategy docstring at `task_loop.py:50`, which is now corrected to document `run_validation_fix_loop` and note the fix sub-agent is engine-owned.
- Kept `_now()` + `import time` in `task_loop.py` — the plan explicitly flagged it is still used by the `task_loop_progress` payload; vulture confirms no orphan remains.
- The fix-loop test double reproduces the N=2 decision rather than recording every `run_fix_agent` call, because the strategy no longer calls a per-attempt fix method directly — the whole loop is now one delegated call, so the double models the loop and records the per-attempt fix records the assertions read.

## Deviations from Plan

None - plan executed exactly as written. (Task 2 noted `kernel_services.py` may already lack `run_fix_agent`; that conditional was resolved in favor of "no edit needed there" after grep confirmation — within the plan's stated intent.)

## Issues Encountered

**Pre-existing test-isolation pollution (NOT caused by this plan):** When the full Task 2 verify command runs `test_strategies.py` and the prototype characterization snapshots in the SAME pytest session, the two characterization snapshots fail. Root cause is `test_strategies.py::test_task_loop_requests_html_skeleton_compaction_for_task_2` mutating the process-global capability registry (`registry_mod.install()` + `_IMPLS[...]`) without fully restoring it. **Verified pre-existing:** reverting both `task_loop.py` and `test_strategies.py` to their pre-07-07 (HEAD~1) versions reproduces the identical single characterization failure in the same combined order. Both files individually pass, and all 3 prototype characterization suites pass in a clean session (6 passed) with goldens byte-unchanged — so 07-07's golden-safety is intact. Logged to `deferred-items.md` for separate triage (needs a registry save/restore or autouse reset fixture); out of cluster-B scope.

## Verification Evidence
- Grep gate: `grep -c "_SkippedRender|def _run_validation_fix_loop|def _select_issues_to_fix|def _static_issue_sigs|def _console_sigs" task_loop.py` → **0**.
- `grep -L "run_fix_agent" kernel_services.py` → returns the filename (no match) ✓; `task_loop.py` has no `run_fix_agent` ✓.
- No test imports the fix-selection helpers from `task_loop` (only `TaskLoopStrategy` is imported).
- Sole delegation present: `task_loop.py:218 await runner.run_validation_fix_loop(...)`.
- `pytest tests/agents/test_strategies.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_capability_resolution.py` → **39 passed**.
- `pytest` of the 3 prototype characterization suites (clean session) → **6 passed**, goldens unmodified (`git status` shows no golden/snapshot/fixture changes).
- `vulture task_loop.py` → no dead symbols.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Cluster B (WR-07, WR-08) closed: the dual fix-loop implementation is gone; INV-3/INV-12 "no dual implementations" holds for the validation fix-loop.
- Remaining 07-REVIEW-DEEP clusters (if any) are unaffected by this golden-safe deletion.
- One pre-existing test-harness hygiene item deferred (test_strategies → characterization session pollution); does not block this plan.

## Self-Check: PASSED

- FOUND: `.planning/phases/07-.../07-07-SUMMARY.md`
- FOUND: `backend/agents/capabilities/strategies/task_loop.py`
- FOUND: `backend/tests/agents/test_strategies.py`
- FOUND commit `5540b5d` (Task 1, test re-point)
- FOUND commit `cc716cd` (Task 2, dead-code deletion)

---
*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Completed: 2026-06-09*

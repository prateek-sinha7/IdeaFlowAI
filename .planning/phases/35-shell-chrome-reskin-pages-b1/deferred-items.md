# Phase 35 — Deferred / Out-of-Scope Items

Append-only log of pre-existing issues discovered during execution that are
OUT OF SCOPE for the current task (per the scope boundary: only auto-fix issues
directly caused by the current task's changes).

## 35-04 — Pre-existing ReviewGatesSection.test.tsx drift (NOT reskin-caused)

**Discovered:** Plan 35-04, Task 3 (ReviewGatesSection reskin).
**Status:** Pre-existing on pristine HEAD — proven identical (3 failed | 16 passed)
before AND after the classNames-only reskin. Delta = 0.

Three tests in `frontend/src/components/workflow/ReviewGatesSection.test.tsx`
fail because `AgentLibraryData.ts` drifted ahead of the test's hardcoded
expectations:

1. `PIPELINE_CATEGORIES counts are reconciled (ppt=3, prototype=4, all=54)` —
   received `all=55` / `prototype=5` (data grew; test still asserts 54 / 4).
2. `each non-custom category count matches the LIBRARY_AGENTS membership` —
   same prototype 5-vs-4 drift.
3. `unchecking ALL gates yields onChange([], true)` — `prototype-analyze` is now
   a third `gate === "Human_Gate"` default (the test's own fixture at L101-105
   already lists it), but the test only unchecks 2 of the 3 default gates, so
   `['prototype-analyze']` remains instead of `[]`.

**Why deferred:** These are data/test-expectation drift in files the 35-04
reskin does not touch (`AgentLibraryData.ts`, the test's hardcoded counts). The
reskin is classNames-only and preserves the `onChange(gateAgentIds, touched)`
contract byte-for-byte (D-15 / INV-3). Fixing the counts + the 2-vs-3 gate
expectation is a data-reconciliation task, not a reskin concern.

**Suggested owner:** a follow-up data-reconciliation quick task to update the
test's expected counts (`all=55`, `prototype=5`) and uncheck all 3 default gates
in the "no-gates payload" case.

---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 11
subsystem: testing
tags: [iss-033, token-accounting, sse, notifications, playwright, pytest, engine]

# Dependency graph
requires:
  - phase: 44-09
    provides: the re-pointed mockSse harness (pipeline emit helpers + REST command mock) driving the run surface over SSE
provides:
  - offline proof that SmartPlanner + clarify aux tokens fold into the pipeline_complete totals (ISS-033 engine fold)
  - a mocked-SSE B.6b spec proving pipeline_complete fires the CompletionToast + notification-bell unread badge
affects: [44-12 (live ISS-033 cache_read verification), token-accounting, notifications]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ISS-033 fold delta test: drive execute() twice (planner-skipped baseline vs aux-emitting run) and assert the pipeline_complete token delta equals the aux totals"
    - "Transport-agnostic notification e2e: launch over REST + drive to pipeline_complete over the mockSse down-channel, assert the client-derived toast + bell badge"

key-files:
  created:
    - backend/tests/agents/test_iss033_aux_token_fold_offline.py
    - frontend/e2e/tests/ts-x.notifications-b6b.spec.ts
  modified: []

key-decisions:
  - "Injected the aux usage through the engine's REAL usage_sink (aux_token_usage.append) so the code path under test is the production fold at engine.py:2474-2482, not a stand-in."
  - "Used user_stories (runs the planner, all text-only agents) as the offline drive pipeline — deterministic baseline totals (input=72, output=42, cache=0)."
  - "Asserted the fold as a strictly-positive DELTA vs a planner-skipped baseline (T-44-11-01), so a vacuous baseline==folded cannot pass."
  - "Text-located the CompletionToast (no data-testid) via 'User Stories complete' + the unique 'View results' button; asserted the bell badge without opening the panel (opening marks all read)."

patterns-established:
  - "Local offline engine driver (mirrors _scripted_model._drive) with a configurable planner that routes scripted aux usage into the real sink."

requirements-completed: [W6, "B.6b", "ISS-033"]

# Metrics
duration: ~40min
completed: 2026-07-16
---

# Phase 44 Plan 11: W6 Offline Part-B (ISS-033 aux-token fold + B.6b notifications) Summary

**Two offline tests closing the ISS-033 and B.6b coverage gaps: an engine drive proving SmartPlanner+clarify aux tokens fold into the pipeline_complete totals (delta vs a planner-skipped baseline), and a mocked-SSE spec proving a run to pipeline_complete fires the CompletionToast + notification-bell unread badge.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-07-16
- **Tasks:** 2
- **Files modified:** 2 (both new, test-only)

## Accomplishments
- ISS-033 offline fold proof: `execute()` driven twice on `user_stories` (planner-skipped baseline vs aux-emitting run); the `pipeline_complete` input/output/cache_read/cache_write totals grow by exactly the aux totals. A second test proves each aux source folds independently (planner-only delta).
- B.6b mocked-SSE spec: launch a `user_stories` run over the REST up-channel, drive every agent to done + `pipeline_complete` over the mockSse down-channel, then assert the bottom-right `CompletionToast` ("User Stories complete" + "View results") and the header bell's unread badge (count "1").
- Both tests are fully offline (no Bedrock / no network); both are test-only additions (no `frontend/src` or backend `app`/`agents` source touched).

## Task Commits

Each task was committed atomically (no trailer):

1. **Task 1: Offline ISS-033 aux-token-fold test** — `0dadd5da` (test)
2. **Task 2: Mocked-SSE B.6b notifications spec** — `b4a20c55` (test)

## Files Created/Modified
- `backend/tests/agents/test_iss033_aux_token_fold_offline.py` — offline proof of the aux-token fold into pipeline_complete (2 tests: combined planner+clarify delta, planner-only independent fold).
- `frontend/e2e/tests/ts-x.notifications-b6b.spec.ts` — mocked-SSE B.6b (CompletionToast + bell unread badge over the SSE mock).

## Decisions Made
- Injected aux usage through the engine's real `usage_sink` (`aux_token_usage.append`) so the fold at `engine.py:2474-2482` is the code under test — the same sink SmartPlanner (`cached_invoke`) and ClarifyEngine (`clarify._usage_sink`) feed in production. `tests/unit/test_cached_invoke.py` already covers the per-call-site counting half; this closes the fold half.
- Drove `user_stories` (planner runs; all text-only agents in the scripted registry) for a deterministic baseline (input=72, output=42, cache=0).
- Asserted the fold as a strictly-positive delta (T-44-11-01) to preclude a vacuous pass.
- For B.6b, text-located the toast and asserted the bell badge without opening the panel (opening triggers `onMarkAllRead`, which would clear the badge).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The `ts-l.token-usage` suite flakes under full-suite load (the failure jumped between TS-L-01 and TS-L-02 across two full runs; TS-L-04 is self-documented in-code as a "flaky drill-in"). It is a PRE-EXISTING load/timing flake, not caused by this plan: the new `ts-x.notifications-b6b` spec is test-only and runs LATER in the alphabetical sequence than `ts-l`, so it cannot affect an already-completed `ts-l` test. `ts-l.token-usage.spec.ts` passes cleanly in isolation (3 passed / 4 skipped), and the new B.6b spec passes deterministically in isolation and in both full runs.

## Verification
- `cd backend && python3.11 -m pytest tests/agents/test_iss033_aux_token_fold_offline.py -q` → 2 passed.
- `cd frontend && npx playwright test --project=mocked -g "B.6b"` → 1 passed.
- Full mocked Playwright suite: 132 passed / 43 skipped / 1 pre-existing ts-l load-flake (176 total; 133 runnable = the prior 132 + this plan's +1). The new B.6b spec is deterministically green.
- `python3.11 -m pytest -k characterization --continue-on-collection-errors` → 10 passed (INV-3 parity intact).
- `/opt/homebrew/bin/lint-imports` → 4 kept, 0 broken.
- Test-only: `git diff --name-only HEAD~2..HEAD` = the two new test files only; no `frontend/src` or backend source touched. No migration.

## Next Phase Readiness
- ISS-033 offline half is proven; the LIVE half (real `cache_read>0` + real magnitude on Bedrock) remains 44-12 (live).
- No blockers.

## Self-Check: PASSED

- FOUND: backend/tests/agents/test_iss033_aux_token_fold_offline.py
- FOUND: frontend/e2e/tests/ts-x.notifications-b6b.spec.ts
- FOUND commit 0dadd5da (Task 1), b4a20c55 (Task 2)

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-16*

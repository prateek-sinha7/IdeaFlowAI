---
phase: 12-wave-scheduler-durable-resume-6
plan: 02
subsystem: engine
tags: [retry, content-hash-reuse, durable-resume, transient-classification, idempotency, resume-02]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6
    plan: 01
    provides: "durable run_events sink + owner-scoped ScopedStore.read_events; wave_runs substrate"
  - phase: 06-model-policy-1c
    plan: 03
    provides: "the single _is_transient_throttle classifier (one transient-classification home)"
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: "the typed ArtifactGraph (content_hash = sha256 content) the input-hash reads"
provides:
  - "RetryPolicy.on (default ['transient']) pure-data field"
  - "the SINGLE engine-side per-step retry/reuse wrapper at the one dispatch home (D-10)"
  - "_compute_step_input_hash (cross-restart-stable) + _find_reused_completion (owner-scoped durable lookup)"
  - "step_retry / step_reused / step_completed lifecycle events (single emit boundary, zero websocket edits)"
  - "_retry_sleep module-level patchable backoff seam"
affects: [12-03-durable-resume, 12-04-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cross-restart-stable input content-hash = sha256 over SORTED upstream content_hashes + resolved input (no timestamp/uuid/unsorted) — the shared key for retry re-entries AND restart re-runs"
    - "Single retry wrapper around the ONE dispatch site, strictly gated on retry.max_attempts > 0 so the absent/None path is byte/event-identical (Pitfall 4 dormancy)"
    - "Best-effort owner-scoped run_events reuse-lookup that degrades to None offline (no DB) → re-execute"

key-files:
  created:
    - backend/tests/agents/test_step_retry.py
  modified:
    - backend/agents/workflows/plan.py
    - backend/agents/execution_engine/engine.py

key-decisions:
  - "input_hash hashes the SORTED upstream content_hashes + the resolved input string (user brief + per-task block) — never a timestamp/uuid/unsorted collection, so 12-03 restart re-runs get hash equality for identical input (D-11/Pitfall 1)"
  - "the wrapper is the SINGLE home (engine dispatch loop), extracted into _dispatch_step_with_retry so it is unit-testable against a fake strategy while remaining the only retry site (D-10) — NOT inside strategies, NOT per-worker in run_fanout"
  - "transient classification REUSES 06-03 _is_transient_throttle (one classifier home, zero second list in engine.py)"
  - "reuse-lookup confirms the referenced output artifact still exists in the typed graph before reusing — a stale ref id → re-execute"

patterns-established:
  - "Pattern: _dispatch_step_with_retry(step, ectx, strategy) async-generator wrapper — gate-FALSE re-yields strategy.run unchanged; gate-TRUE does reuse-skip OR bounded transient-retry with step_retry/step_completed events"

requirements-completed: [RESUME-02]

# Metrics
duration: ~25min
completed: 2026-06-11
---

# Phase 12 Plan 02: Per-Step Retry + Content-Hash Reuse Summary

**A single engine-side per-step retry/reuse wrapper — `RetryPolicy.on`, a cross-restart-stable input content-hash, an owner-scoped durable reuse-lookup, and `step_retry`/`step_reused`/`step_completed` events — that retries transient errors and reuses identical-input artifacts, with the 5 characterization snapshots byte/event-identical (retry dormant for existing workflows).**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-11
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `RetryPolicy.on: list[str]` added (default `["transient"]`) as a pure data field (INV-5) — the §21 policy is now LIVE; `max_attempts == 0` / absent stays dormant.
- `_compute_step_input_hash(step, ectx)`: deterministic, CROSS-RESTART-STABLE sha256 over `{"upstream": sorted([content_hashes]), "input": resolved_input}` (canonical `json.dumps(sort_keys=True, separators=(",",":"))`) — no timestamp, no uuid, no unsorted collection (the 12-03 restart re-runs depend on hash equality).
- `_find_reused_completion(ectx, step_id, input_hash)`: queries the durable, OWNER-SCOPED `run_events` (`ScopedStore.read_events`, T-12-02-REPLAY) for a prior `step_completed`/`step_reused` payload carrying the SAME `(step_id, input_hash)`, confirms the produced artifact still exists, and returns its `output_ref_id`; a `None` store (offline) or any read error → `None` (re-execute).
- `_dispatch_step_with_retry`: the SINGLE retry/reuse wrapper at the one dispatch home (D-10), strictly gated on `step.retry and step.retry.max_attempts > 0`. Gate-FALSE re-yields `strategy.run` UNCHANGED. Gate-TRUE reuses (yield `step_reused`, zero agent call) or runs a bounded attempt loop: transient (`_is_transient_throttle`) + attempts remaining → yield `step_retry` + `await _retry_sleep(backoff)` + loop; success → yield `step_completed` carrying `input_hash` + the produced `output_ref_id`; non-transient or exhaustion → re-raise the visible error (never swallowed).
- `_retry_sleep` shipped as a module-level patchable async backoff seam; the attempt loop is strictly bounded by `max_attempts` (T-12-02-DOS).
- `test_step_retry.py` (offline, fake-strategy): transient-then-success retries the declared count then completes; never-recovers exhausts `max_attempts` then surfaces a visible error; non-transient does NOT retry; a matching `(run_id, step_id, input_hash)` reuses with ZERO agent calls; no-retry (and `max_attempts==0`) runs the byte-identical legacy path.

## Task Commits

1. **Task 1: RetryPolicy.on field + input_hash + reuse-lookup helpers** — `9830f81` (feat)
2. **Task 2: single per-step retry/reuse wrapper + step_retry/step_reused events** — `bb19844` (feat)

## Files Created/Modified
- `backend/agents/workflows/plan.py` — `RetryPolicy.on: list[str]` (default `["transient"]`), pure data (INV-5).
- `backend/agents/execution_engine/engine.py` — `import hashlib`; module-level `_retry_sleep` backoff seam; `_compute_step_input_hash` + `_find_reused_completion` helpers; the `_dispatch_step_with_retry` wrapper; dispatch site rewired to call it.
- `backend/tests/agents/test_step_retry.py` — new offline retry/reuse suite (7 tests).

## Decisions Made
- The wrapper is extracted into `_dispatch_step_with_retry` (still the ONLY retry site) so it is unit-testable against a fake strategy + minimal ctx without driving a full pipeline — the single-home (D-10) invariant holds (no retry logic inside strategies / run_fanout).
- `input_hash` includes the per-task block (`ectx.current_task_block`) when present, so a task-loop step's per-task input is distinguished; absent → just the user brief + sorted upstream hashes.
- The reuse-lookup confirms `ectx.artifacts.get(output_ref_id) is not None` before reusing — a recorded completion whose artifact is gone falls through to re-execution.

## Deviations from Plan

None - plan executed exactly as written. (One in-test fix during development: the reuse test seeds the prior artifact BEFORE computing the expected `input_hash`, since the hash includes the produced refs — a test-construction ordering correction, not a production change.)

## Issues Encountered
None blocking. The full offline backend pytest hangs (Chromium/Bedrock/Postgres-gated), so verification used the targeted plan-named suites + lint-imports per the project note.

## Verification Evidence
- `pytest tests/agents/test_step_retry.py tests/agents/test_characterization_*.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py` → **51 passed, 7 skipped**.
- `/opt/homebrew/bin/lint-imports` → **4 kept / 0 broken**.
- 5 characterization snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset (retry dormant).
- `grep -n "step.retry" engine.py` shows the strict `max_attempts > 0` gate; engine.py references ONLY the imported `_is_transient_throttle` classifier (no second transient list).

## User Setup Required
None — stdlib only (`hashlib`/`json`/`asyncio`); zero new packages; INV-13 banned-pattern gate unaffected.

## Next Phase Readiness
- The `(run_id, step_id, input_hash)` reuse key + the durable `step_completed`/`step_reused` events are the substrate 12-03 mid-run durable resume re-uses for restart re-runs (one mechanism serves retry re-entries AND restart re-runs).
- `RetryPolicy.on` is data-ready for a future non-transient retry class without an engine edit.
- No blockers.

## Threat Flags
None — the new surface (input-hash reuse-lookup, retry attempt loop) is covered by the plan's threat model: T-12-02-REPLAY mitigated via the owner-scoped `read_events` + content-addressed `input_hash`; T-12-02-DOS mitigated via the strictly-bounded attempt loop + non-transient immediate break; T-12-02-HASH accepted (sha256 for dedup/idempotency, never an auth control); T-12-02-SC mitigated (zero external packages).

## Self-Check: PASSED
- FOUND: backend/agents/workflows/plan.py
- FOUND: backend/agents/execution_engine/engine.py
- FOUND: backend/tests/agents/test_step_retry.py
- FOUND commit: 9830f81 (Task 1)
- FOUND commit: bb19844 (Task 2)

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*

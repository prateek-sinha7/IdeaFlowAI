---
phase: 12-wave-scheduler-durable-resume-6
plan: 05
subsystem: engine
tags: [durable-resume, reconnect-replay, after-seq, seq-continuity, workspace-recovery, gap-closure, idor]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6
    plan: 03
    provides: "resume_run + the WS after_seq reconnect replay branch this plan fixes (CR-01 seq seeding + CR-02 workspace recovery)"
provides:
  - "resume_run seeds the seq counter from the durable run_events tail (max(seq)+1) — resumed events continue the monotonic per-run seq, no collision with the pre-restart 1..N"
  - "_execute_impl recovers the ORIGINAL workspace_id on ANY resume (_is_resume), not only offset>0, so resumed events are stamped with the pre-restart workspace and the after_seq reconnect read resolves to them"
  - "the WS reconnect replay branch recovers the run's workspace_id from an owner-scoped RunEvent row before constructing the replay ScopedStore (owner+workspace-scoped, never client-supplied)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Resume seq continuity: read the durable run_events tail under the recovered owner+workspace scope and seed itertools.count(max(seq)+1) so resumed events strictly continue the per-run seq (the after_seq=N reconnect contract)"
    - "Resume workspace binding is keyed on _is_resume (a resume with offset 0 is still a resume), NOT on offset>0 — a run with a durable run_events tail but no completed step must still bind to its original workspace or its resumed events land under a fresh (unreadable) workspace_id"
    - "WS replay workspace recovery: recover from a RunEvent row filtered by owner_id == user.id (server-side, never from the reconnect payload) → owner+workspace-scoped replay; a non-owner run recovers no row → None → ∅ replay (IDOR boundary)"

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/app/api/websocket.py
    - backend/tests/agents/test_restart_resume.py
    - backend/tests/agents/test_ws_reconnect_replay.py

key-decisions:
  - "resume_run reads the durable tail with the RECOVERED workspace_id (not a fresh create_workspace id, IN-04) and seeds counter = itertools.count(max(seq)+1); a missing tail (offline harness) degrades to start=1 — byte/event-identical"
  - "Added _is_resume to _execute_impl and widened the workspace recovery from `_resume_from > 0` to `_is_resume or _resume_from > 0` (Rule 1 bug): an offset-0 resume of a run with a durable run_events tail must bind to the ORIGINAL workspace, else the after_seq read resolves to ∅ (the resumed events are under a fresh minted workspace)"
  - "WS replay recovery uses the PRIMARY approach (a fresh _get_db() session — no DB session is otherwise in scope in the reconnect branch); the lookup is owner-scoped (RunEvent.owner_id == user.id) and the recovered workspace_id is passed to a normal owner+workspace-scoped ScopedStore — the workspace predicate is preserved, never dropped (T-12-05-TENANT)"
  - "Left _did_replay (IN-01) and the line-728 clarifications _ScopedStore branch untouched — out of scope for this gap-closure plan"

requirements-completed: [RESUME-03]

# Metrics
duration: ~6min
completed: 2026-06-11
---

# Phase 12 Plan 05: Durable Resume/Replay Gap Closure (CR-01 + CR-02) Summary

**Closed the two RESUME-03 BLOCKERS that made durable WS reconnect-replay dead on arrival in production: `resume_run` now seeds its event seq counter from the durable `run_events` tail (`max(seq)+1`) so resumed events continue the monotonic per-run seq instead of colliding with the pre-restart 1..N (and a run resuming at offset 0 with a durable tail now binds to its ORIGINAL workspace, so its resumed events are readable under the same scope); and the WS reconnect replay branch recovers the run's real workspace_id from an owner-scoped `RunEvent` row before constructing the replay `ScopedStore`, so the owner+workspace-scoped `read_events` matches the production rows (`workspace_id IS NULL` matched zero) — recovery is server-side and owner-scoped, never client-supplied.**

## Performance
- **Duration:** ~6 min
- **Started:** 2026-06-11T10:57:48Z
- **Completed:** 2026-06-11T11:03:56Z
- **Tasks:** 2 (both TDD: RED → GREEN)
- **Files modified:** 4 (0 created, 4 modified)

## Accomplishments

- **CR-01 — resume seq continuity (RESUME-03):** `resume_run` (engine.py) now reads the durable `run_events` tail under the SAME owner+workspace scope the engine sink wrote the rows under — recovering the ORIGINAL `workspace_id` via `_recover_workspace_id` (NOT a fresh `create_workspace` id, IN-04) — and seeds `counter = itertools.count(max(seq)+1)`. Resumed events now persist with seq strictly greater than the pre-restart max, so a reconnecting client that sends `after_seq=N` (its last pre-crash seq) receives the resumed tail. A read failure / offline harness with no durable tail degrades to `start = 1` (byte/event-identical to the prior behavior — an offline resume has no tail to collide with).
- **CR-01 — workspace binding widened (Rule 1 bug surfaced by the fix):** `_execute_impl` previously recovered the original `workspace_id` ONLY when `_resume_from > 0`. A run interrupted with a durable `run_events` tail but no COMPLETED step computes offset 0, so it was minting a FRESH workspace and stamping its resumed events under it — making the owner+workspace-scoped `after_seq` reconnect read resolve to ∅ even after the seq fix. Added an explicit `_is_resume` param to `_execute_impl` (threaded `True` from `resume_run`) and widened the recovery to `_is_resume or _resume_from > 0`. A run with no durable row (offline) still recovers `None` → mints fresh → byte/event-identical.
- **CR-02 — WS replay workspace recovery (RESUME-03):** the reconnect replay branch (websocket.py) recovers the run's real `workspace_id` from a `RunEvent` row ALREADY FILTERED BY `owner_id == user.id` (a fresh `_get_db()` session — no DB session is otherwise in scope in that branch) and passes it to the replay `ScopedStore(owner_id=user.id, workspace_id=_recovered_ws)`. The read keeps the FULL owner+workspace default-deny scoping (the workspace predicate is preserved with a server-recovered value, never dropped). The pre-fix `ScopedStore(owner_id=user.id)` scoped the read to `workspace_id IS NULL` and matched ZERO production rows. A non-owner run recovers no row → `workspace_id=None` → ∅ replay (the cross-owner IDOR boundary).

## Task Commits
1. **Task 1 (CR-01): seed resume seq counter past the durable tail** — `02202ea4` (test, RED), `cb34ca82` (fix, GREEN)
2. **Task 2 (CR-02): recover workspace_id in the WS reconnect replay branch** — `11280c94` (test, RED), `987e8262` (fix, GREEN)

## Files Created/Modified
- `backend/agents/execution_engine/engine.py` — `resume_run` durable-tail seq seeding (`itertools.count(max(seq)+1)`, recovered-workspace scoped, offline-degrading); added `_is_resume` param to `_execute_impl` + widened the resume workspace recovery from `_resume_from > 0` to `_is_resume or _resume_from > 0`; `resume_run` threads `_is_resume=True`.
- `backend/app/api/websocket.py` — reconnect replay branch recovers the run's `workspace_id` from an owner-scoped `RunEvent` row before constructing the replay `ScopedStore`.
- `backend/tests/agents/test_restart_resume.py` — `test_resumed_events_seq_continues_past_durable_tail`: seeds run_events 1..N, drives `resume_run`, asserts resumed events carry seq > N (min == N+1) and the `after_seq=N` read returns the resumed tail.
- `backend/tests/agents/test_ws_reconnect_replay.py` — `test_production_shaped_replay_recovers_workspace_and_returns_rows` (production-shaped store with recovered, not explicit, workspace returns rows; pre-fix shape returns 0) + `test_cross_owner_workspace_recovery_yields_empty_replay` (owner-scoped recovery → ∅ for a cross-owner reconnect).

## Decisions Made
- **Seq seed from the recovered-workspace tail, offline-degrading:** the durable-tail read uses the recovered original `workspace_id` (not a minted one) so `max(seq)` is over the rows the sink actually wrote; any failure (offline / no tail) → `start = 1` (the prior behavior, correct for a tail-less run).
- **`_is_resume`, not `_resume_from > 0`, for workspace recovery:** an offset-0 resume is still a resume. Keying the workspace recovery on `_resume_from > 0` left a run with a durable run_events tail but no completed step minting a fresh workspace — making CR-01's seq fix necessary-but-insufficient. The `is_resuming` flag (wave mid-wave filter) stays `_resume_from > 0` (its skip semantics only matter when there are completed waves to skip).
- **PRIMARY (not fallback) recovery in websocket.py:** a fresh `_get_db()` session is opened just for the owner-scoped `RunEvent` lookup; the recovered `workspace_id` feeds a normal owner+workspace-scoped `ScopedStore` (the full default-deny scoping preserved). No new ScopedStore helper was needed — the workspace predicate is never dropped.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_execute_impl` minted a fresh workspace for an offset-0 resume**
- **Found during:** Task 1 (CR-01) — after seeding the seq counter, the new `after_seq=N` assertion still failed because the resumed events were stamped under a fresh minted `workspace_id`, not the recovered one.
- **Issue:** The resume workspace recovery in `_execute_impl` was gated on `_resume_from > 0`. A run with a durable run_events tail but no completed step computes offset 0, so it minted a fresh workspace and the owner+workspace-scoped `after_seq` reconnect read resolved to ∅ — RESUME-03 still broken despite the seq fix.
- **Fix:** Added an explicit `_is_resume: bool` param to `_execute_impl` (threaded `True` from `resume_run`) and widened the recovery condition to `_is_resume or _resume_from > 0`. Offline runs (no durable row) still recover `None` → mint fresh → byte/event-identical.
- **Files modified:** `backend/agents/execution_engine/engine.py`
- **Commit:** `cb34ca82`

## Issues Encountered
None blocking. The Rule-1 bug above was the only surprise — the CR-01 seq fix was necessary but not sufficient on its own; the workspace-binding widening completed the after_seq reconnect contract.

## Verification Evidence
- `pytest test_restart_resume.py test_ws_reconnect_replay.py test_characterization_*.py test_banned_patterns.py test_migration_ledger.py` → **55 passed, 7 skipped** (10 characterization snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset).
- `pytest test_wave_runs.py test_wave_scheduler.py test_subagent_runs.py tests/unit/test_resumability.py tests/unit/test_execution_engine.py` → **44 passed** (adjacent resume/wave behavior unbroken).
- `/opt/homebrew/bin/lint-imports` → **4 kept / 0 broken**.
- `grep -c "for i, spec in enumerate(ordered_agents)" engine.py` → **1** (no forked dispatch loop, INV-12).
- `grep "itertools.count(1)" engine.py` → no match in `resume_run` (the seed is `itertools.count(start)`); only the fresh-run (535) and revision (3261) counters remain.
- `grep "read_events(run_id, after_seq=0)" engine.py` → match inside `resume_run` (the durable-tail read).
- `grep "ScopedStore(owner_id=user.id)" app/api/websocket.py` → no match in the replay branch (now carries `workspace_id=_recovered_ws`); line 728 is the separate clarifications branch (out of scope).
- `grep 'message_data.get("workspace_id")' app/api/websocket.py` → **0** (workspace recovered server-side, never client-supplied).

## Threat Model Outcomes
- **T-12-05-SEQ (Tampering, mitigate):** the seq seed is computed server-side from the owner+workspace-scoped durable tail — a client cannot influence it. No new unique constraint / schema change.
- **T-12-05-TENANT (Information Disclosure, mitigate):** the WS replay workspace_id is recovered from a `RunEvent` row filtered by `owner_id == user.id` and fed to a normal owner+workspace-scoped `ScopedStore` (predicate preserved, not dropped). Never read from the reconnect payload. A non-owner run → no row → ∅.
- **T-12-05-IDOR (Information Disclosure, mitigate):** the replay read stays owner+workspace-scoped; a cross-owner `pipeline_run_id` recovers no workspace → ∅ replay.
- **T-12-05-SC (Tampering, mitigate):** zero new packages (stdlib `itertools` + existing `ScopedStore`/`RunEvent` ORM). INV-13 banned-pattern gate unaffected (test_banned_patterns green).

## Threat Flags
None — no new security surface beyond the plan's threat model. The only new query is the owner-scoped `RunEvent` lookup, which is strictly narrower than the existing replay read.

## Self-Check: PASSED

All modified files exist on disk; all 4 task commits (`02202ea4`, `cb34ca82`, `11280c94`, `987e8262`) are present in the git log.

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*

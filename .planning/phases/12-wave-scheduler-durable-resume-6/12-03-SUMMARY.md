---
phase: 12-wave-scheduler-durable-resume-6
plan: 03
subsystem: engine
tags: [durable-resume, mid-wave, reconnect-replay, after-seq, restart-classification, idor]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6
    plan: 01
    provides: "durable wave_runs persistence + owner-scoped read_wave_runs/read_subagent_runs + the wave_scheduler strategy this plan adds the mid-wave skip to"
  - phase: 12-wave-scheduler-durable-resume-6
    plan: 02
    provides: "the (run_id, step_id, input_hash) content-hash reuse key + step_completed/step_reused durable events the resume offset reuses for completed steps"
  - phase: 11-fan-out-merge
    provides: "subagent_runs persistence + fragments-persist-before-merge (a completed worker's fragment is durable pre-merge, so the mid-wave skip reuses it)"
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: "the typed ArtifactGraph + durable artifact_refs the resume hydration adopts"
provides:
  - "reconnect_pipeline after_seq durable replay branch (owner-scoped run_events tail, restart-survives, status-reports)"
  - "resume_run(run_id) — rebuilds the ExecutionContext via the single _execute_impl path + re-enters the SINGLE dispatch loop at the first incomplete step (_resume_from offset)"
  - "_first_incomplete_step + durable-substrate completeness (artifact_refs/run_events/wave_runs, no new step-status table)"
  - "wave_scheduler MID-WAVE resume skip (completed waves + completed leading workers not re-fanned-out)"
  - "three-way restore_non_terminal_runs (waiting_for_user re-arm / resumable in-flight auto-resume / WR-05 verbatim)"
  - "ArtifactGraph.adopt (id/hash/version-preserving durable hydration) + ExecutionContext.is_resuming + KernelServices.read_wave_runs/read_subagent_runs"
affects: [12-04-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Durable IN-PROCESS resume re-enters the SAME generator (_execute_impl) at a _resume_from offset — NO forked dispatch loop (INV-12); the loop skips i < offset, planner/clarify suppressed, ectx rebuilt via the one construction path"
    - "Resume binding-drift guard (Pitfall 2): the ORIGINAL workspace_id is RECOVERED from a durable row (owner-scoped) — create_workspace mints a fresh id, which would silently miss the owner+workspace-scoped wave_runs/subagent_runs reads"
    - "Mid-wave skip reads the durable wave_runs/subagent_runs via ctx.runner (import-pure strategy) and re-enters the SAME run_fanout with a filtered task set — completed workers' fragments reused (Phase-11 pre-merge durability)"
    - "Double-drive guard: stamp an additive run_resuming event BEFORE asyncio.create_task(resume_run) so a crash-during-resume is itself resumable; an additive event (not a new status) keeps NON_TERMINAL + the state machine untouched"

key-files:
  created:
    - backend/tests/agents/test_ws_reconnect_replay.py
    - backend/tests/agents/test_restart_resume.py
  modified:
    - backend/app/api/websocket.py
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/context.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/agents/capabilities/strategies/wave_scheduler.py
    - backend/agents/artifacts/graph.py

key-decisions:
  - "resume re-enters _execute_impl with a _resume_from offset (NOT a forked resume loop) — the ExecutionContext is rebuilt via the ONE construction path, so the grep gate `for i, spec in enumerate(ordered_agents)` stays at 1 (the completeness SCAN iterates by index to avoid tripping it)"
  - "the resume marker is an additive `run_resuming` EVENT, not a new status value (Open Q2) — NON_TERMINAL + the state machine are untouched, so the 5 characterization snapshots stay byte/event-identical"
  - "_is_resumable_in_flight = a compilable-manifest run WITH any durable step state (run_events OR artifact_refs OR wave_runs); a stateless run has nothing to resume FROM → WR-05 verbatim (branch c). Offline (no DB) ⇒ False ⇒ resume dormant for existing test runs"
  - "the original workspace_id is recovered from a durable row (owner-scoped) on resume — create_workspace is not idempotent and a fresh id would make the owner+workspace-scoped mid-wave reads resolve to ∅ (silently re-running completed workers)"
  - "the after_seq replay branch is entered when after_seq is supplied OR there is no live task; a pure legacy reconnect (no after_seq + live task) skips replay so the live-attach drainer + 5 snapshots are byte-identical"

patterns-established:
  - "Pattern: durable resume = recover identity (workflow_runs) → recover workspace_id (durable row) → hydrate typed graph (adopt durable refs) → compute first-incomplete offset → re-enter the single dispatch loop at the offset"
  - "Pattern: a capability strategy reads durable resume state ONLY via ctx.runner (read_wave_runs/read_subagent_runs) — never importing the store (import-linter clean)"

requirements-completed: [RESUME-03, RESUME-04, WAVE-03]

# Metrics
duration: ~20min
completed: 2026-06-11
---

# Phase 12 Plan 03: Durable Resume Tier Summary

**The durable resume tier — a WS `reconnect_pipeline` `after_seq` branch that replays the owner-scoped `run_events` tail (surviving a process restart with cleared in-memory queues), plus `resume_run` + a three-way `restore_non_terminal_runs` that auto-resumes an interrupted in-flight run IN-PROCESS by re-entering the SINGLE dispatch loop at the first incomplete step (mid-wave: completed workers are not re-invoked) — with the 5 characterization snapshots byte/event-identical (resume dormant for existing runs).**

## Performance
- **Duration:** ~20 min
- **Started:** 2026-06-11T09:26:07Z
- **Completed:** 2026-06-11T09:46:16Z
- **Tasks:** 2
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments
- **WS `after_seq` durable replay (RESUME-03):** `reconnect_pipeline` reads `message_data.get("after_seq", 0)` (int-coerced — a non-int is rejected) and, when `after_seq` is supplied OR there is no live task (restart), FIRST replays the durable `run_events` tail (`seq > after_seq`) from an owner-scoped `ScopedStore` BEFORE attaching to the live queue. A restart (cleared `_PIPELINE_QUEUES`/`_PIPELINE_TASKS`) still replays from the DB and reports the run's current status via `ScopedStore.get_run`. A cross-owner reconnect resolves to ∅ (T-12-03-IDOR). The legacy no-`after_seq`+live-task path is byte-identical (the live-attach drainer + clarify-gate restoration preserved).
- **`resume_run(run_id)` (RESUME-04):** rebuilds the ExecutionContext via the SAME `_execute_impl` construction path (no copy-paste fork — Pitfall 2) and re-enters the SINGLE per-step dispatch loop at the first incomplete step via a `_resume_from` offset. Planner/clarify are suppressed on resume; the loop skips `i < _resume_from`. The grep gate `for i, spec in enumerate(ordered_agents)` stays at 1 (the completeness scan iterates by index).
- **`_first_incomplete_step` (D-07):** derives completeness from the durable substrate (no new step-status table): a non-wave step is complete iff it produced a durable `artifact_refs` row OR has a terminal `step_completed`/`step_reused` event; a wave step is complete only when it has terminal `wave_runs` rows and none running. Resume hydrates the typed graph (`ArtifactGraph.adopt`) + recovers the ORIGINAL `workspace_id` from a durable row so the owner+workspace-scoped reads align with the pre-restart rows.
- **Mid-wave resume (WAVE-03):** on `ctx.is_resuming` the `wave_scheduler` strategy reads `read_wave_runs`/`read_subagent_runs` via `ctx.runner` and skips completed waves (terminal `wave_runs`) wholesale + the completed LEADING workers of the in-flight wave (terminal `subagent_runs`), re-entering the SAME `run_fanout` with only the incomplete tasks. Completed fragments are reused (Phase-11 pre-merge durability).
- **Three-way `restore_non_terminal_runs` (D-08):** (a) `waiting_for_user` → the existing resume-event re-arm UNCHANGED; (b) a resumable in-flight run → stamp an additive `run_resuming` marker BEFORE `asyncio.create_task(self.resume_run(...))` (the double-drive guard, T-12-03-DOUBLEDRIVE), then auto-resume in-process; (c) anything else → the WR-05 abandoned→failed path VERBATIM. The `NON_TERMINAL` list + the state machine are untouched (the marker is an additive event, Open Q2).

## Task Commits
1. **Task 1: reconnect_pipeline after_seq durable replay branch** — `97f63c16` (feat)
2. **Task 2: resume_run + first-incomplete-step (mid-wave) + three-way restore** — `83cfff4c` (feat)

## Files Created/Modified
- `backend/app/api/websocket.py` — `reconnect_pipeline` `after_seq` durable replay branch (owner-scoped `read_events`, restart status report, legacy path preserved).
- `backend/agents/execution_engine/engine.py` — `_resume_from` param + resume offset in the single dispatch loop; `resume_run`; `_compute_resume_offset`; `_first_incomplete_step`; `_recover_workspace_id`; `_hydrate_artifacts_from_store`; `_is_resumable_in_flight`; `_stamp_resume_marker`; three-way `restore_non_terminal_runs`; `ectx.is_resuming` wiring.
- `backend/agents/execution_engine/context.py` — `ExecutionContext.is_resuming` flag.
- `backend/agents/execution_engine/kernel_services.py` — `read_wave_runs`/`read_subagent_runs` best-effort, owner-scoped, None-degrading handles.
- `backend/agents/capabilities/strategies/wave_scheduler.py` — mid-wave resume skip (completed waves + completed leading workers).
- `backend/agents/artifacts/graph.py` — `ArtifactGraph.adopt` (id/hash/version-preserving durable hydration).
- `backend/tests/agents/test_ws_reconnect_replay.py` — after_seq tail, restart-from-DB+status, legacy-no-replay predicate, cross-owner ∅ (5 tests).
- `backend/tests/agents/test_restart_resume.py` — mid-wave resume (completed workers not re-invoked, run completes), waiting_for_user gates, stateless run keeps WR-05 (3 tests, real in-memory SQLite per RESEARCH Open Q3).

## Decisions Made
- **No forked dispatch loop:** resume re-enters `_execute_impl` at an offset rather than a second driver — the single-construction-path requirement is met in the strongest sense (zero duplicated build). The completeness SCAN in `_first_incomplete_step` iterates by index so the dispatch-loop grep gate stays at 1.
- **Workspace-id recovery on resume:** `create_workspace` mints a fresh uuid, which would make the owner+workspace-scoped `wave_runs`/`subagent_runs`/`artifact_refs` reads miss the pre-restart rows — silently re-running completed workers. The original id is recovered from the first durable row (owner-scoped) so the resume reads align (Pitfall 2 — no binding drift).
- **Additive resume marker, not a new status:** the `run_resuming` event keeps `NON_TERMINAL` + the state machine untouched (Open Q2), so existing runs never hit branch b and the 5 snapshots are byte/event-identical.
- **Resume dormant offline:** `_is_resumable_in_flight` returns `False` with no DB, so every characterization test run keeps the WR-05 path — the resume branch never fires for existing runs.

## Deviations from Plan
None — plan executed exactly as written. (Two in-test construction corrections during development: the WorkflowRun seed uses the real `type`/`input` columns, and the mid-wave interrupt is a `run_fanout`-call wrapper that raises ON ENTRY for wave 1 — so the failing wave's workers never run on instance A, making the resume re-run them and proving the offset re-enters the incomplete wave. Both are test scaffolding, not production changes.)

## Issues Encountered
None blocking. Two resume correctness bugs surfaced + fixed during the mid-wave test build: (1) the wave step's task plan was empty on resume because the skipped plan step's typed output was not in the fresh-process in-memory graph → fixed by `ArtifactGraph.adopt` durable hydration on resume; (2) the mid-wave skip read ∅ because `create_workspace` minted a new workspace_id → fixed by `_recover_workspace_id` (recover the original id from a durable row). Both are the binding-drift class the project note warned about.

## Verification Evidence
- `pytest test_ws_reconnect_replay.py test_restart_resume.py test_characterization_*.py test_banned_patterns.py test_migration_ledger.py` → **52 passed, 7 skipped** (10 characterization snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset — resume dormant).
- `pytest test_wave_runs.py test_wave_scheduler.py test_sample_wave_workflow.py test_step_retry.py test_subagent_runs.py` → **46 passed**.
- `pytest tests/unit/test_resumability.py tests/unit/test_execution_engine.py` → **16 passed** (existing restore behavior unbroken).
- `/opt/homebrew/bin/lint-imports` → **4 kept / 0 broken**.
- `grep -c "for i, spec in enumerate(ordered_agents)" engine.py` → **1** (no forked dispatch loop).
- Three branches present (`grep -n "WR-05\|asyncio.create_task(self.resume_run\|waiting_for_user"`); `NON_TERMINAL` list unchanged (no new status added).

## User Setup Required
None — stdlib only (`asyncio`/`uuid`/`itertools`); zero new packages (T-12-03-SC). INV-13 banned-pattern gate unaffected.

## Next Phase Readiness
- The `after_seq` replay branch is the durable substrate the 12-04 frontend reconnect consumes (the FE dedupes by `event_id`); the `run_resuming` marker + resumed events flow through the same seq/event_id sink, so a reconnecting client replays them.
- No blockers. Phase 12 = 3/4 plans complete (12-04 frontend remaining).

## Threat Flags
None — the new surface is covered by the plan's threat model: T-12-03-IDOR mitigated (owner-scoped `read_events`/`get_run` ⇒ cross-owner reconnect = ∅; `after_seq` int-coerced); T-12-03-DOUBLEDRIVE mitigated (stamp-before-create_task + once-at-startup classification); T-12-03-RESUMESCOPE mitigated (resume rebuilds via the shared path ⇒ same owner/workspace; workspace_id recovered, not re-minted); T-12-03-CROSSNODE accepted (single-node startup-only, N8 v1); T-12-03-SC mitigated (zero external packages).

## Self-Check: PASSED

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*

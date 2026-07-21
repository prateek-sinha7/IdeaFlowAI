---
phase: 50-user-resume-from-failed-r5
plan: 01
subsystem: api
tags: [resume, fastapi, rest, asyncio, workflow-run, sse, hitl-gate]

# Dependency graph
requires:
  - phase: 45-49 (shared resume tier)
    provides: "engine.resume_run + _drive_resumed_stream + _first_incomplete_step cursor + gate re-entry classifier + _stamp_resume_marker + the run_engine bridge/armed singleton hooks"
provides:
  - "POST /api/runs/{id}/resume — user resume-from-failed endpoint (RESUME-18)"
  - "_drive_user_resume thin wrapper (delegates all drive to resume_run; adds terminal reconcile + arm-failure flip-back)"
  - "_reconcile_terminal_status durable-tail event->status reconciler + _flip_back_to_failed honest-state guard"
affects: [frontend-resume-button, milestone-end-live-pass]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin app-layer drive wrapper over a status-agnostic engine driver (reconcile status from the durable run_events tail, never a third engine.execute ladder — INV-12/Pitfall 7)"
    - "In-process registry mutex (queue+task) as the double-POST atomicity primitive (asyncio no-preemption; no await between check and register)"
    - "Queue-before-flip ordering (BUG-015 live-attach) for a status transition into an AUTO_STREAM state"

key-files:
  created:
    - backend/tests/unit/test_rest_resume.py
  modified:
    - backend/app/api/run_commands.py
    - backend/tests/agents/test_restart_resume.py

key-decisions:
  - "PINNED tension resolution: resume_run writes NO WorkflowRun.status, so a bare create_task(resume_run) strands a user-resumed run at 'running'. Resolved with a THIN _drive_user_resume wrapper that reconciles the terminal status from the durable tail + flips back to failed on arm-failure — NOT a third driver, and auto-resume's own status posture is untouched (out of scope)."
  - "No re-threaded callbacks: resume_run reads its live-layer hooks off self.* on the armed singleton (main.py:141-154); threading live_ectx_register=/milestone_sink= would be dead code (resume_run takes none)."
  - "Double-POST behavior pinned as 'exactly one 200, the other 409' — the ordering pin (eligibility before overlap + a synchronous failed->running commit before the first await) makes a truly-concurrent second POST land on the eligibility fence (run_not_resumable); the overlap pipeline_already_running guard is proven separately by a registry-preloaded case. Within CONTEXT's stated discretion."
  - "Gate-at-failure E2E marks the sample-wave-plan spec gate='Human_Gate' (the realistic statically-gated path) so _should_gate is True on resume — gate CONFIG is Phase-49 scope; Phase-50 proves the classifier COMPOSITION (offset override -> gate_reentry sentinel -> consumer) with zero endpoint special-casing."

patterns-established:
  - "Resume drive wrapper: await engine.resume_run(run_id) then _reconcile_terminal_status; except -> _flip_back_to_failed. Fence: no async-for engine.execute ladder in the wrapper."
  - "Owner gate cloned from create_revision (.filter(id, user_id).first() -> 404 never 403; keyed on user_id never nullable owner_id)."

requirements-completed: [RESUME-18]

# Metrics
duration: ~40min
completed: 2026-07-19
---

# Phase 50 Plan 01: User Resume-From-Failed [R5] Summary

**`POST /api/runs/{id}/resume` makes a terminal-FAILED run user-resumable — a thin `_drive_user_resume` wrapper reuses the Phase 45–49 resume tier (cursor skip, gate re-entry, live callbacks) and adds only the terminal-status reconcile the tier structurally lacks; zero new drivers, no FE edits, no migration.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-07-19T05:47:51Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- Shipped `POST /api/runs/{run_id}/resume` (RESUME-18) — the "reopen & fix" headline of milestone v3.0's final phase. Endpoint is the ONLY new surface; drive is pure reuse of `engine.resume_run`.
- Implemented the exact ordering pin: owner-404 → eligibility-409 → overlap-mutex-409 (no await) → register queue+cancel (BUG-015 before flip) → `failed→running` commit → reuse `_stamp_resume_marker` → `create_task(_drive_user_resume)` + register task → 200.
- `_drive_user_resume` delegates 100% of drive to `resume_run` (armed-singleton hooks fire automatically — no re-threaded callbacks) and adds ONLY `_reconcile_terminal_status` (durable-tail event→status, the D2 table) + `_flip_back_to_failed` (honest state on arm-failure). No `engine.execute` event ladder (INV-12 / Pitfall 7).
- 9-case endpoint battery (RED-first) + 2 E2E cases proving completed-task skip / deliverable completion / status reconcile / same-id-no-new-row, and gate-at-failure re-entry with zero endpoint special-casing.

## Task Commits

1. **Task 1: endpoint + thin wrapper + reconciler + guards (RED battery)** — `70fc41e8` (feat)
2. **Task 2: E2E failed→resume skip + gate-at-failure re-entry** — `3e80fcc4` (test)

**Plan metadata:** _(this commit)_ (docs: execution summary)

_TDD: Task 1 wrote `test_rest_resume.py` RED (9 failed — endpoint/wrapper absent) → implemented → GREEN (9/0)._

## Files Created/Modified
- `backend/app/api/run_commands.py` — added `_PIPELINE_QUEUES` to the run_engine import block; `resume_run_endpoint` (`POST /{run_id}/resume`); `_drive_user_resume` thin wrapper; `_reconcile_terminal_status`; `_flip_back_to_failed`; shared `_persist_resume_status` idiom.
- `backend/tests/unit/test_rest_resume.py` — NEW 9-case endpoint battery (owner 404, eligibility 409, overlap 409, double-POST atomicity, queue-before-flip, flip+marker, arm-failure flip-back). SQLite StaticPool harness modeled on `test_rest_revisions.py`; stub engine for `_stamp_resume_marker`/`resume_run`/`_recover_workspace_id`.
- `backend/tests/agents/test_restart_resume.py` — appended `test_failed_run_resumes_skips_completed_tasks` + `test_failed_run_with_open_gate_resumes_into_gate`, reusing the durable-seed harness (`_seed_workflow_run` / `_seed_open_review_gate`); a shared `_wire_user_resume_drive` helper points `_get_db` + the engine singleton at the harness DB.

## Decisions Made
See `key-decisions` frontmatter. Headline: the CONTEXT tension ("terminal statuses land exactly as auto-resume does") is unsatisfiable as written — auto-resume writes no `WorkflowRun.status`, so a literal reading ships a run stuck `running`. Resolved with the thin wrapper's reconcile + flip-back (research-recommended, POR §8.1 authorized), leaving auto-resume's posture untouched.

## Deviations from Plan

Two test-design pins within CONTEXT's stated discretion (no production-code deviations; Rules 1–3 not triggered):

**1. Double-POST second-request code — pinned to "one 200 / one 409" (not strictly `pipeline_already_running`)**
- **Found during:** Task 1 (`test_resume_double_post_second_409`).
- **Rationale:** The ordering pin (eligibility BEFORE overlap; a synchronous `failed→running` commit before the first `await`) means a truly-concurrent second coroutine resumes only at the marker `await` — by which point the winner has already committed `running`, so the loser lands on the eligibility fence (`run_not_resumable`). Both are 409 and only one drive occurs (atomicity holds). The `pipeline_already_running` (CR-01) overlap guard is proven separately by `test_resume_already_running_409` (a registry-preloaded live run with DB status still `failed`). CONTEXT §Claude's Discretion explicitly grants "pin the exact behavior."
- **Verification:** `test_resume_double_post_second_409` asserts exactly one 200 + one 409 + a single registry task.

**2. Gate-at-failure E2E marks the plan spec `gate="Human_Gate"`**
- **Found during:** Task 2 (`test_failed_run_with_open_gate_resumes_into_gate`).
- **Rationale:** The `sample_wave` fixture's `sample-wave-plan` carries no static gate and resume does not restore per-run `gate_agent_ids`, so `_should_gate` is False on resume unless the agent is statically gated. Marking the plan spec `Human_Gate` (exactly as a real gated agent like `prototype-specify` is authored) exercises the REAL gate seam. Gate CONFIG is Phase-49 scope; Phase-50's concern is the classifier COMPOSITION (`_first_incomplete_step` open-gate override → `gate_reentry` sentinel → consumer), which the test proves fires with ZERO endpoint special-casing.
- **Verification:** the spied `_run_review_gate` is invoked exactly once for `sample-wave-plan`; the run stops at the gate (reconciled `cancelled`), never completing past it; no new WorkflowRun row.

---

**Total deviations:** 0 production-code (2 documented test-design pins within discretion).
**Impact on plan:** None — all locked fences honored (no FE edits, no third driver, no new status vocabulary, no migration, no re-threaded callbacks, no new WS event types).

## Issues Encountered
- The plan's `<verify>` referenced characterization filenames (`od_generic`, `ppt`, `code_gen`, `revision`) that do not exist on disk. The actual 5 golden files are `test_characterization_{prototype, od_prototype, od_ppt, app_builder, prototype_revision}.py` — ran those for the INV-3 gate (10/0, `SNAPSHOT_UPDATE` unset). Command-label correction only; no behavior change.

## Verification (BY DELTA vs 50-VALIDATION baseline)

| Gate | Baseline | Result |
|------|----------|--------|
| `tests/unit/test_rest_resume.py` | new | **9 / 0** ✓ |
| `tests/agents/test_restart_resume.py` | 39 / 0 | **41 / 0** ✓ (+2) |
| Goldens (5 characterization) | 10 / 0 | **10 / 0** ✓ (`SNAPSHOT_UPDATE` unset) |
| rest_run_launch / answers_cancel / revisions / approve_review / sse / router | 25/9/14/6/17/28 | **all at baseline** ✓ (108 total incl. resume) |
| `/opt/homebrew/bin/lint-imports` | 4 / 0 | **4 kept / 0 broken** ✓ |
| HELD env-reds: redo_gate_safety / declared_gate_streaming | 4/3 · 0/3 | **4/3 · 0/3 unchanged** ✓ (not greened) |

E2E reopen-and-fix evidence: `test_failed_run_resumes_skips_completed_tasks` — wave-0 workers NOT re-invoked (`call_log` unchanged), all four files produced, status reconciled to `completed`, `count(workflow_runs)` unchanged (no new row). `test_failed_run_with_open_gate_resumes_into_gate` — `_run_review_gate` re-entered once for `sample-wave-plan`, run stopped at the gate (`cancelled`, not `completed`).

## Next Phase Readiness
- RESUME-18 satisfied; milestone v3.0's final API surface shipped. The FE "Resume" affordance (deferred, CONTEXT §Deferred) can now call this contract.
- Live-Bedrock reopen-and-fix proof deferred to the orchestrator-owned milestone-end consolidated live pass (50-VALIDATION manual-only row; offline gates bind phase completion).

## Self-Check: PASSED

- Files verified on disk: `test_rest_resume.py`, `run_commands.py`, `test_restart_resume.py`, `50-01-SUMMARY.md` — all FOUND.
- Commits verified in git log: `70fc41e8` (Task 1), `3e80fcc4` (Task 2) — all FOUND.

---
*Phase: 50-user-resume-from-failed-r5*
*Completed: 2026-07-19*

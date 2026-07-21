---
phase: 50-user-resume-from-failed-r5
verified: 2026-07-19T08:20:00Z
status: passed
score: 5/5 must-haves verified
verifier: Claude (gsd-verifier)
overrides_applied: 0
re_verification:
  previous_status: none
  note: initial verification
deferred:
  - truth: "Live-Bedrock reopen-and-fix (fail mid-build on real Bedrock → POST /resume → deliverable completes; FE AUTO_STREAM auto-attach + live SSE)"
    addressed_in: "Milestone v3.0 end — consolidated orchestrator-owned live pass"
    evidence: "50-VALIDATION.md 'Manual-Only Verifications' row (defer-live-verification convention: offline gates bind phase completion). Every offline gate this phase is green."
---

# Phase 50: User Resume-From-Failed — Reopen & Fix [R5] Verification Report

**Phase Goal:** A terminal-FAILED run becomes user-resumable (`POST /api/runs/{id}/resume`) — the "reopen & fix" headline (ND-4), authorized by the LOCK-E supersede record (POR §8.1). The endpoint is the only new surface; everything else reuses the shared resume tier built in Phases 45–49.
**Verified:** 2026-07-19T08:20:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Phase 50 Success Criteria)

| # | Truth (SC) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Ownership + safety: two-layer owner check (404 never 403); overlap guard `pipeline_already_running`; replayed/concurrent POSTs idempotent | ✓ VERIFIED | Endpoint owner gate `run_commands.py:360-368` clones `create_revision` — `.filter(id==run_id, user_id==current_user.id).first()` → 404 "Unknown run" (keyed on `user_id`, never nullable `owner_id`; cross-owner and missing indistinguishable — no oracle). Layer 2 = `ScopedStore(owner_id, …)` default-deny inside `resume_run` (engine.py:7343 `tail_store`). Overlap mutex `:382` (`run_id in _PIPELINE_TASKS or _PIPELINE_QUEUES` → 409 `pipeline_already_running`). Additive `run_resuming` marker (`_stamp_resume_marker`, no status) + registry mutex = idempotent replay/concurrent. Tests: `test_resume_cross_owner_404`, `test_resume_missing_404`, `test_resume_completed_409`, `test_resume_cancelled_409`, `test_resume_already_running_409`, `test_resume_double_post_second_409` — 9/9 green. |
| 2 | State recovery: workspace_id from durable rows (never fresh-minted — Pitfall 2), `selections_json` re-applied (0023), completed steps/tasks via the cursor, disk re-materialized — all by reuse inside `resume_run` | ✓ VERIFIED | Endpoint adds NONE of this — pure reuse. `resume_run` (engine.py:7233-7420) calls `_recover_workspace_id(owner_id, run_id)` (:7342, Pitfall-2), reads `wr.selections_json` and re-applies via `_apply_selections` (:7288/comment block), dispatches at `_first_incomplete_step` (cursor, :7241 docstring), and `_drive_resumed_stream` re-materializes disk. Proven end-to-end by `test_failed_run_resumes_skips_completed_tasks`: wave-0 workers NOT re-invoked on resume (`call_log['a']/['b']` unchanged), wave-1 ran, all four `part_*.txt` produced on the recovered sandbox. |
| 3 | Drive + stream: queue re-registered in `_PIPELINE_QUEUES` BEFORE the FE attaches (BUG-015); `run_engine` bridge reuse; NO third driver; terminal ladder behavior-identical to the fail-safe launch driver | ✓ VERIFIED | Queue-before-flip: endpoint step 4 (`_get_or_create_queue` :391) precedes the `wr.status="running"` commit (:395-396) — `test_resume_registers_queue_before_status_flip` captures row status `"failed"` at queue-registration time. Bridge reuse: main.py:141 wires `engine._resume_register_queue = _ws_bridge._register_resume_queue`; endpoint + wrapper both call the SAME `get_execution_engine()` singleton. HARD FENCE holds: `sed 413-518` of `_drive_user_resume` region contains NO `async for … engine.execute(` (only the docstring stating the fence); the 5 `engine.execute` occurrences file-wide are the pre-existing launch/revision drivers, none in the resume path. `_reconcile_terminal_status` (:440-493) clones the D2 four-way table (cancelled/degraded/completed/failed) as LOGIC read from the durable tail — not a ladder. |
| 4 | Status transition failed→running + `run_resuming` marker so FE `AUTO_STREAM_STATUSES` auto-attaches; live-layer callbacks fire off the armed singleton (RESUME-10 by construction) | ✓ VERIFIED | Endpoint flips `failed→running` (existing vocab, :395) + stamps additive `run_resuming` via `_stamp_resume_marker` (:400) — `test_resume_flips_running_and_stamps_marker` asserts row is `"running"` at stamp time + one marker. Armed-singleton identity CONFIRMED: `get_execution_engine()` returns module-level `_ENGINE` (engine.py:8167-8173); main.py:134/152-154 arms `_resume_live_ectx_register`/`_resume_live_ectx_unregister`/`_resume_milestone_sink` on that SAME singleton; endpoint (:355/400) and wrapper (:429) call `get_execution_engine()` → same instance. `resume_run` reads hooks off `self.*` (no re-threading — grep confirms NO `live_ectx_register=`/`milestone_sink=` kwargs in `_drive_user_resume`). |
| 5 | E2E proof: fail mid-build → resume → completed tasks skipped, deliverable completed, same run id/no new row, family coherent; gate-at-failure re-enters the gate | ✓ VERIFIED | `test_failed_run_resumes_skips_completed_tasks`: real engine `_execute_impl` fails mid-wave → `_drive_user_resume` → cursor skip, all four files, status reconciled `completed`, `parent_run_id` unchanged, `count(workflow_runs)` unchanged (no re-mint, Pitfall 5). `test_failed_run_with_open_gate_resumes_into_gate`: durable open gate → resume re-enters `_run_review_gate` for exactly `sample-wave-plan` (49 classifier composes, zero endpoint special-casing), stops at gate (`cancelled`, not completed past), no new row. Both green (restart_resume 41/0). Live-Bedrock ladder deferred to milestone-end (see Deferred). |

**Score:** 5/5 truths verified

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Live-Bedrock reopen-and-fix (real SSE + FE auto-attach) | Milestone v3.0 end (orchestrator-owned consolidated live pass) | 50-VALIDATION.md manual-only row; defer-live-verification convention — offline gates bind phase completion, and every offline gate is green |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `backend/app/api/run_commands.py` | `/resume` endpoint + `_drive_user_resume` + `_reconcile_terminal_status` + `_flip_back_to_failed` (+ shared `_persist_resume_status`) | ✓ VERIFIED | All present (:329/413/440/496/503); `_PIPELINE_QUEUES` imported (:73); +212 lines in commit 70fc41e8. Wired: endpoint on `@router.post("/{run_id}/resume")`; wrapper spawned via `create_task` (:406). |
| `backend/tests/unit/test_rest_resume.py` | 9-case endpoint battery, ≥120 lines | ✓ VERIFIED | 373 lines, 9 cases, all green. Owner-404 (×2), eligibility-409 (×2), overlap-409, double-POST atomicity, queue-before-flip, flip+marker, arm-failure flip-back. |
| `backend/tests/agents/test_restart_resume.py` | +2 E2E (`test_failed_run_resumes_skips_completed_tasks`, gate-at-failure) | ✓ VERIFIED | Both present (:3022/3110); +193 lines commit 3e80fcc4; 39→41/0 (floor held). |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| resume endpoint | `_PIPELINE_QUEUES`/`_get_or_create_queue` | queue registered BEFORE status flip | ✓ WIRED | `_get_or_create_queue(run_id)` :391 precedes `wr.status="running"` commit :396 (BUG-015). |
| resume endpoint | `engine.resume_run` | `create_task(_drive_user_resume)` sole drive | ✓ WIRED | :406 `create_task`; wrapper :431 `await engine.resume_run(run_id)` — the sole drive path. |
| `_drive_user_resume` | `WorkflowRun.status` terminal write | `_reconcile_terminal_status`/`_flip_back_to_failed` | ✓ WIRED | :432 success reconcile; :437 except → flip-back. Both via shared `_persist_resume_status`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `_reconcile_terminal_status` | `new_status` | `ScopedStore.read_events(run_id)` durable tail (real owner-scoped event rows) | Yes — D2 map over live events | ✓ FLOWING |
| `resume_run` (reused) | workspace/cursor/selections | `_recover_workspace_id` + `wr.selections_json` + `_first_incomplete_step` over durable rows | Yes — E2E produced 4 real files + reconciled `completed` | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Endpoint battery | `pytest tests/unit/test_rest_resume.py -q` | 9 passed | ✓ PASS |
| E2E resume tier | `pytest tests/agents/test_restart_resume.py -q` | 41 passed | ✓ PASS |
| HARD FENCE | `sed 413,518 | grep 'engine.execute'` in wrapper | only docstring, no ladder | ✓ PASS |
| Armed singleton | `get_execution_engine` returns module `_ENGINE` | confirmed (engine.py:8167) | ✓ PASS |

### Probe Execution

Not applicable — no `scripts/*/tests/probe-*.sh` declared for this phase; verification is pytest-driven (per 50-VALIDATION).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| RESUME-18 | 50-01 | User resume-from-failed (`POST /api/runs/{id}/resume`) | ✓ SATISFIED | All 5 SCs verified; endpoint + wrapper + reconciler + guards shipped; 9 endpoint + 2 E2E tests green. |

### Regression Battery (BY DELTA vs 50-VALIDATION baseline)

| Gate | Baseline | Result | Status |
|------|----------|--------|--------|
| `test_rest_resume.py` | new | 9/0 | ✓ |
| `test_restart_resume.py` | 39/0 | 41/0 (+2) | ✓ |
| Goldens (5 characterization, `SNAPSHOT_UPDATE` unset) | 10/0 | 10/0 | ✓ |
| rest_run_launch/answers_cancel/revisions/approve_review/sse/router | 25/9/14/6/17/28 | 99/0 combined (all at baseline) | ✓ |
| `/opt/homebrew/bin/lint-imports` (run from backend/) | 4/0 | 4 kept / 0 broken | ✓ |
| HELD env-reds: redo_gate_safety / declared_gate_streaming | 4/3 · 0/3 | 4/3 · 0/3 unchanged (not greened) | ✓ |

Note: the plan's `<verify>` listed non-existent characterization filenames (`od_generic`/`ppt`/`code_gen`/`revision`); the actual 5 goldens are `prototype`/`od_prototype`/`od_ppt`/`app_builder`/`prototype_revision` — ran those (10/0). Command-label correction only, documented in SUMMARY Issues.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| run_commands.py | 460/491 | `return` / best-effort `except` in reconcile | ℹ️ Info | Intentional INV-3 offline-degrade (documented); the arm-failure path owns the honest-state guarantee, so a reconcile no-op never strands a genuinely-failed run. Not a stub — real durable-tail read drives the status. |

No `TBD`/`FIXME`/`XXX` debt markers in the modified files. No re-mint (`WorkflowRun(` absent from resume region). No re-threaded callbacks. No new status vocabulary (`run_resuming` is the additive engine event, never a `WorkflowRun.status` value).

### Two Test-Design Pins (executor) — Soundness Review

1. **Double-POST "one 200 / one 409"** — `test_resume_double_post_second_409` genuinely `asyncio.gather`s two endpoint coroutines and asserts exactly one 200 dict + one 409 + a single registered task (`_PIPELINE_TASKS` count ≤ 1). The concurrent loser lands on the eligibility fence (`run_not_resumable`, also 409) because the winner commits `running` before the first `await`; the `pipeline_already_running` code is proven separately by `test_resume_already_running_409` (registry-preloaded, DB still `failed`). The atomicity property (exactly one drive) is DIRECTLY asserted — not weakened. Sound, within CONTEXT's stated discretion.
2. **Gate-at-failure `gate="Human_Gate"`** — the E2E marks the fixture plan spec statically gated (exactly as a real gated agent is authored) so `_should_gate` is True on resume, exercising the REAL gate seam. Gate CONFIG is Phase-49 scope; Phase-50 proves the classifier COMPOSITION (`_first_incomplete_step` open-gate override → `gate_reentry` sentinel → consumer) fires with zero endpoint special-casing. The spy asserts the gate re-entered for exactly `sample-wave-plan` and the run stopped at the gate (`cancelled`, not completed past). Legitimate fixture setup, not assertion-weakening. Sound.

### Human Verification Required

None blocking phase completion. The live-Bedrock reopen-and-fix pass is deferred to the milestone-end consolidated live run (orchestrator-owned) per the project's defer-live-verification convention — offline gates bind phase completion and all are green.

### Gaps Summary

No gaps. All five ROADMAP Phase-50 success criteria are observably true in the codebase. The endpoint is the only new surface; drive is pure reuse of the Phase 45–49 resume tier via the armed-singleton `resume_run` (identity confirmed). The HARD FENCE (no third driver / no `engine.execute` ladder) holds. The queue-before-flip ordering, the no-await double-POST mutex, the two-layer 404-never-403 owner check, the honest-state arm-failure flip-back, and the durable-tail terminal reconcile are each implemented as written and covered by green tests. Every regression battery is at baseline; the two held env-red suites remain red (not greened); lint-imports 4/0. RESUME-18 satisfied — milestone v3.0's final API surface shipped.

---

_Verified: 2026-07-19T08:20:00Z_
_Verifier: Claude (gsd-verifier)_

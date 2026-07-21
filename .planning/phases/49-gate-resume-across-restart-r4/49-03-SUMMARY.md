---
phase: 49
plan: 03
subsystem: execution-engine / gate-resume
tags: [RESUME-17, restart-resume, clarify-gate, questionnaire-replay, INV-12, A5, KAN-88-twin]
requires:
  - phase: 49-01
    provides: "gate_pendency.derive_open_gate shared home + _rearm_gate_run driver skeleton (clarify branch was a no-op stub)"
  - phase: 49-02
    provides: "review-gate re-entry (offset override + gate_reentry sentinel) + resume_run drive loop (now the extracted shared stream)"
provides:
  - "ClarifyEngine.run replay_questions/replay_round — REPLAY the durable open round verbatim (no _generate_questions LLM re-gen)"
  - "_execute_impl _clarify_replay param — forces the clarify gate on the planner-skip path so Step 3 replays the durable questions"
  - "_drive_resumed_stream — the SHARED resume sink/seq/live-queue/milestone-card loop (INV-12; extracted from resume_run, used by both restart drivers)"
  - "_replay_clarify_run — the distinct clarify re-arm REPLAY driver (never resume_run — the KAN-88 twin holds)"
  - "the v3.0 restart tier locked at its delta floor (dormancy + regression sweep)"
affects:
  - "agents/execution_engine/engine.py (resume_run refactored onto the shared stream), clarify_engine.py"
  - "RESUME-17 clarify-parked runs now survive a backend restart symmetrically with review gates"
tech-stack:
  added: []
  patterns:
    - "questionnaire REPLAY via a param on the ONE questionnaire machine (ClarifyEngine.run) — no second clarify loop (INV-12)"
    - "shared resume-stream drive loop parameterized by re-entry mode (_resume_from offset vs _clarify_replay)"
key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/clarify_engine.py
    - backend/tests/agents/test_restart_resume.py
key-decisions:
  - "A5 (LOCKED): a THIN REPLAY driver re-drives _execute_impl from planning with _clarify_replay set — NOT a re-entry of ClarifyEngine.run's generation. The replay lives INSIDE the run (Step 3) so ALL events flow through one seq-correct sink."
  - "Extract _drive_resumed_stream from resume_run (INV-12) — the two restart drivers share the substantive drive/persist/live-queue/card loop; resume_run drives with _resume_from=offset, the clarify twin with _clarify_replay."
  - "The clarify re-arm reconstruction (identity read + seq-seed + live-queue reg) is inline in _replay_clarify_run (not extracted): it reads durable events under the wr.owner_id-first scope branch (a) armed under, which legitimately differs from resume_run's user_id-first owner derivation."
requirements-completed: [RESUME-17]
duration: ~50min
completed: 2026-07-19
---

# Phase 49 Plan 03: Clarify Twin — Durable-Questionnaire Replay on Restart Summary

**A restart-parked clarify gate now survives the restart symmetrically with the review gate: the re-arm driver REPLAYS the durable `questionnaire_ready` questions verbatim (zero LLM re-gen of the answered round), re-enters the store wait leaving the run `waiting_for_user`, and — on answers via the UNCHANGED `POST /answers` seam — proceeds into the normal planner→agents dispatch exactly as a never-restarted run; the whole v3.0 restart tier holds at its delta floor.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-07-19
- **Completed:** 2026-07-19
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- **The clarify twin (A5).** `_rearm_gate_run`'s clarify branch (a 49-01 no-op stub) now drives `_replay_clarify_run` — a REPLAY driver that reads the durable open round's `questions`+`round`, re-drives `_execute_impl` from planning with `_clarify_replay` set, re-emits the SAME questions (no `_generate_questions`), re-enters the wait, and converges on answers into the standard dispatch reusing `ClarifyEngine._merge_answers`/`_persist_qa` (INV-12).
- **One questionnaire machine (INV-12).** `ClarifyEngine.run` gained `replay_questions`/`replay_round`: the round whose number equals `replay_round` replays those durable questions instead of calling `_generate_questions`; every other line of `run` (emit → wait → merge → persist → `questionnaire_complete`) is byte-unchanged, and a subsequent round generates normally.
- **Shared resume stream (INV-12).** Extracted `_drive_resumed_stream` from `resume_run` — the seq/persist/live-queue/milestone-card drive loop is now shared by BOTH restart drivers; `resume_run` drives with `_resume_from=offset`, the clarify twin with `_clarify_replay`. `resume_run` is byte/event-identical to its pre-extraction form (`_clarify_replay=None`).
- **Dormancy + regression sweep.** Goldens 10/10 (SNAPSHOT_UPDATE unset — the replay path is dormant on scripted runs), banned_patterns 11/0 (enumerate-pin still 1; no name literals), lint-imports 4/0, and the whole at-risk table held at the 49-VALIDATION baseline.

## Task Commits

1. **Task 1: clarify re-arm replay driver (A5) + the clarify-twin test** — `d506c480` (feat)
2. **Task 2: dormancy sweep + full at-risk battery** — verification-only (the replay-param dormancy assertion `test_clarify_run_without_replay_generates_normally` was co-committed in `d506c480`; the two tasks are coupled — both exercise the single replay-param change — and no leak was found to fix)

**Plan metadata:** _(this SUMMARY commit)_

## Files Created/Modified

- `backend/agents/execution_engine/clarify_engine.py` — `ClarifyEngine.run` gains `replay_questions`/`replay_round`; the round == `replay_round` replays the durable questions verbatim (no LLM re-gen). Dormant when the params are absent.
- `backend/agents/execution_engine/engine.py` — `_execute_impl` gains `_clarify_replay` (forces the clarify gate on the planner-skip path; threads the replay params to `ClarifyEngine.run`); `_drive_resumed_stream` extracted from `resume_run` (shared drive loop); new `_replay_clarify_run` (the distinct clarify re-arm driver); `_rearm_gate_run`'s clarify branch now drives it.
- `backend/tests/agents/test_restart_resume.py` — `test_clarify_parked_run_replays_durable_questions_and_proceeds` (the KAN-88 twin: replay + `waiting_for_user` + `resume_run` not driven + answers proceed into dispatch, no `_generate_questions`) + `test_clarify_run_without_replay_generates_normally` (INV-3 dormancy of the replay branch) + `_seed_open_questionnaire_gate` helper.

## Decisions Made

- **A5 replay lives INSIDE `_execute_impl` (Step 3), not as a standalone wait loop.** The driver re-drives the run with `_clarify_replay`; the replay-emit/wait/merge/complete all run through `ClarifyEngine.run` and the run's ONE seq-correct sink, so the re-emitted `questionnaire_ready` and the post-answer dispatch events carry monotonic seq > the durable tail (a reconnecting client replays them via `after_seq`). This reused the maximum existing code (INV-12) — the planner-skip path + Step 3 + the whole Step 4 dispatch.
- **Force the clarify gate via `_clarify_replay`, independent of `compiled.clarify.mode`.** A run PARKED at a clarify gate provably had clarify enabled; keying the replay on the durable open gate (not the manifest mode) makes it robust even when a compiled plan's `clarify.mode` reads `off` (as the offline harness sets).
- **Extract the drive loop, keep the reconstruction inline.** The 100-line drive/persist/live-queue/card loop was the real dual-implementation risk → extracted to `_drive_resumed_stream`. The reconstruction glue (identity read + seq-seed + live-queue reg) stays inline in each driver because the clarify driver reads durable events under the `wr.owner_id`-first scope branch (a) armed the event under (matching engine.py:5240), which differs from `resume_run`'s `user_id`-first owner derivation — a justified, contract-driven difference, not a shadow.

## Deviations from Plan

None — plan executed exactly as written (PINNED A5 followed verbatim; the replay driver replays the durable questions, re-arms the store wait, converges via the existing merge/persist helpers, keeps `POST /answers` byte-unchanged, and holds status at `waiting_for_user` until resolution).

## Issues Encountered

- **Async timing in the twin test.** Driving the full `_execute_impl` through a `create_task` driver that PARKS at `event.wait()` required a deterministic observation channel. Resolved by wiring the harness `_resume_register_queue` to a real per-run `asyncio.Queue` and `_resume_register_task` to capture the driver task: the test drains the live queue until `questionnaire_ready`, asserts the parked state, sets responses via the SAME store seam `POST /answers` wraps, then drains to `pipeline_complete` and awaits the driver task. No `sleep`-based polling.

## Verification (delta vs 49-VALIDATION / 49-02 baseline; offline, python3.11, `cd backend/`)

| Suite | Baseline | After | Result |
|-------|----------|-------|--------|
| `test_restart_resume.py` | 37 / 0 | **39 / 0** | +2 new twins green (clarify replay + replay-param dormancy); no red |
| `test_redo_gate_safety.py` | 4 / 3 | 4 / 3 | HELD (pre-existing `_fake_gate` KAN-101 `update_specs_eligible` kwarg drift — NOT fixed) |
| `test_characterization_*.py` (goldens) | 10 / 10 | 10 / 10 | HELD — byte/event-identical, SNAPSHOT_UPDATE unset (replay path dormant on scripted runs, INV-3) |
| `test_banned_patterns.py` | 11 / 0 | 11 / 0 | HELD — enumerate-pin 1; zero workflow/agent-name literals in `agents/execution_engine/` |
| `test_sse_stream.py` | 17 / 0 | 17 / 0 | HELD (D-14g re-emit unperturbed) |
| `test_mechanical_router.py` | 28 / 0 | 28 / 0 | HELD |
| `test_rest_answers_cancel.py` | 9 / 0 | 9 / 0 | HELD (the clarify-answers seam byte-unchanged) |
| `test_approve_review_ownership.py` | 6 / 0 | 6 / 0 | HELD |
| `test_concierge_escalation.py` | 13 / 0 | 13 / 0 | HELD |
| `test_clarify_json_parse.py` | 11 / 0 | 11 / 0 | HELD |
| `test_declared_gate_streaming.py` | 3 env-red | 3 env-red | HELD — `sqlite3.IntegrityError: FOREIGN KEY constraint failed` on `run_events` persist (Postgres-gated offline artifact, A4; root cause re-confirmed unchanged) |
| `lint-imports` | 4 / 0 | 4 / 0 | HELD (no new import edges; gate_pendency stays capabilities-tier) |

**The dormancy proof (INV-3):** goldens 10/10 with SNAPSHOT_UPDATE unset is the by-construction proof — the 5 scripted characterization runs never park at a gate, so `_clarify_replay` stays None, `_drive_resumed_stream` never spawns, `ClarifyEngine.run`'s replay branch is unreachable, and the resume_run extraction is byte/event-identical (its `_clarify_replay` argument is None). The targeted `test_clarify_run_without_replay_generates_normally` pins the clarify-side dormancy directly (round 1 generates normally, no `questionnaire_ready` without questions).

**Every seam is dormant on scripted golden runs (the phase dormancy sweep):** review offset override no-ops (`derive_open_gate → (None,None)`), the `gate_reentry` sentinel unset, the clarify replay driver never spawns, and `_clarify_replay=None` ⇒ the new `_execute_impl` branch is inert.

## Success Criteria

- **SC-4:** ✅ clarify re-arm replays the durable questions with NO LLM re-gen of the open round; answers via the unchanged `POST /answers` proceed into the normal dispatch; multi-round semantics unchanged (the OPEN round replays; a subsequent round's `_generate_questions` is the same LLM call a live run makes).
- **SC-5:** ✅ status stays `waiting_for_user` throughout the re-arm and transitions exactly as a live run on resolution (the KAN-88 twin assertion holds; `resume_run` is never driven for a clarify re-arm).
- **INV-3:** ✅ goldens 10/10; all new machinery dormant on scripted runs.
- **INV-12:** ✅ reuse `ClarifyEngine._merge_answers`/`_persist_qa` (no second questionnaire machine) + the extracted `_drive_resumed_stream` (no forked resume loop); single dispatch loop (enumerate-pin 1).
- **The whole v3.0 restart tier holds at the delta floor.** ✅ The only red→green flip anywhere in the phase was KAN-88 (in 49-01); this plan adds only green tests.

## Known Stubs

None. RESUME-17 is complete end-to-end: the review-gate re-entry (49-02) and the clarify twin (this plan) both survive a restart. Standing out-of-scope fences (unchanged): the cancel-aware gate wait (P23 T8/F7), the declared-path non-inline gate redo (P23 v1), and the live-Bedrock restart-mid-gate proof (milestone-end pass).

## Next Phase Readiness

- RESUME-17 closed; the R0–R4 restart-resume tier is complete. Phase 50's REST resume-from-failed endpoint is the next tier (out of scope here).
- No migration, no FE work, no new WS event types, no new dependency surface.

## Self-Check: PASSED

- `backend/agents/execution_engine/engine.py` (`_replay_clarify_run`, `_drive_resumed_stream`), `backend/agents/execution_engine/clarify_engine.py` (`replay_questions`), `backend/tests/agents/test_restart_resume.py`, `49-03-SUMMARY.md` — all present on disk.
- Commit `d506c480` — in git log.
- Post-commit deletion guard: no tracked files deleted.

---
*Phase: 49-gate-resume-across-restart-r4*
*Completed: 2026-07-19*

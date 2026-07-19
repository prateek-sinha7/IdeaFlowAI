---
phase: 50
slug: user-resume-from-failed-r5
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
---

# Phase 50 — Validation Strategy

> Sourced from 50-RESEARCH "## Validation Architecture"; planner filled the per-task map.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/unit/test_rest_resume.py tests/agents/test_restart_resume.py -q` (first file lands in Wave 0 / Task 1) |
| **Full suite command** | quick + rest_run_launch + rest_answers_cancel + rest_revisions + approve_review_ownership + sse_stream + mechanical_router + 5 characterization files -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~10s · battery ~110s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (50-RESEARCH, 2026-07-19):** restart_resume **39/0** · rest_run_launch 25 · rest_answers_cancel 9 · rest_revisions 14 · approve_review_ownership 6 · sse_stream 17 · mechanical_router 28 · goldens 10 · redo 4/3 HELD · declared_gate_streaming 3 env-reds HELD · lint 4/0. Verify BY DELTA; no intended red→green flips this phase (KAN-88 already green).

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T1 · owner 404 (cross-owner + missing) | 50-01 | 1 | RESUME-18 | T-50-01 | Two-layer owner check, 404 never 403, keyed on `user_id` | unit | `python3.11 -m pytest tests/unit/test_rest_resume.py -x -q` (`test_resume_cross_owner_404`, `test_resume_missing_404`) | ⬜ new file (Task 1 creates) | ⬜ |
| T1 · eligibility 409 (completed/cancelled/running) | 50-01 | 1 | RESUME-18 | T-50-02 | failed-only fence; `run_not_resumable` | unit | ″ (`test_resume_completed_409`, `test_resume_cancelled_409`) | ⬜ | ⬜ |
| T1 · overlap 409 (already-live) | 50-01 | 1 | RESUME-18 | T-50-03 | in-process registry mutex; `pipeline_already_running` (CR-01) | unit | ″ (`test_resume_already_running_409`) | ⬜ | ⬜ |
| T1 · double-POST race (2nd → 409) | 50-01 | 1 | RESUME-18 | T-50-03 | no-await-between-check-and-register atomicity | unit | ″ (`test_resume_double_post_second_409`) | ⬜ | ⬜ |
| T1 · queue-before-flip (live attach) | 50-01 | 1 | RESUME-18 | T-50-03 | `_PIPELINE_QUEUES` registered before status commit (BUG-015) | unit | ″ (`test_resume_registers_queue_before_status_flip`) | ⬜ | ⬜ |
| T1 · status flip failed→running + marker | 50-01 | 1 | RESUME-18 | — | failed→running + additive `run_resuming` (no new status; INV-12) | unit | ″ (`test_resume_flips_running_and_stamps_marker`) | ⬜ | ⬜ |
| T1 · arm-failure → honest state (back to failed) | 50-01 | 1 | RESUME-18 | T-50-06 | `_flip_back_to_failed`; never stuck `running` | unit | ″ (`test_resume_arm_failure_flips_back_to_failed`) | ⬜ | ⬜ |
| T2 · E2E failed mid-build → resume → tasks skipped, deliverable completes, same id/no new row | 50-01 | 1 | RESUME-18 | T-50-03 | no re-mint; cursor skip; workspace recovered | integration | `python3.11 -m pytest tests/agents/test_restart_resume.py -x -q` (`test_failed_run_resumes_skips_completed_tasks`) | ✅ test_restart_resume.py (append) | ⬜ |
| T2 · gate-at-failure re-entry | 50-01 | 1 | RESUME-18 | — | 49 classifier composes; re-emits `review_gate_ready` | integration | ″ (`test_failed_run_with_open_gate_resumes_into_gate`) | ✅ (append) | ⬜ |
| Phase gate · INV-3 dormancy | 50-01 | 1 | RESUME-18 | — | endpoint absent from golden paths; byte/event-identical | characterization | `python3.11 -m pytest tests/agents/test_characterization_*.py -q` (10/0) | ✅ | ⬜ |
| Phase gate · import boundaries | 50-01 | 1 | RESUME-18 | — | hexagonal boundaries intact (§31) | lint | `/opt/homebrew/bin/lint-imports` (4/0) | ✅ | ⬜ |

## Wave 0 Requirements

- [x] `tests/unit/test_rest_resume.py` created (NEW) in Task 1, tests written RED before the endpoint exists — the 9-case endpoint battery. Modeled on `test_rest_revisions.py` harness (SQLite StaticPool, `_get_db` patch on `run_engine` + `run_commands`, `get_execution_engine` stub, cleared registries per test).
- [x] `tests/agents/test_restart_resume.py` E2E cases appended in Task 2, reusing the durable-seed harness (`_seed_workflow_run` / `_seed_open_review_gate`); no new harness.
- No framework install needed (pytest 8.3.4 + pytest-asyncio 0.24 STRICT already present).

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live reopen-and-fix on real Bedrock (fail mid-build → POST /resume → deliverable completes; FE auto-attach) | RESUME-18 | live env + real SSE | Milestone-end consolidated live pass (orchestrator-owned); offline gates bind phase completion (defer-live-verification convention) |

## Validation Sign-Off

- [x] automated verifies (every task carries an `<automated>` command with a measured delta floor)
- [x] continuity (each behavior maps to a named test; battery returns to baseline tallies)
- [x] Wave 0 (test_rest_resume.py created RED-first in Task 1; E2E harness reused in Task 2)
- [x] no watch-mode (all commands are one-shot `-q`)
- [x] latency <120s (quick ~10s · battery ~110s)
- [x] nyquist_compliant flipped (every `<verify>` has an `<automated>` command)

**Approval:** approved (2026-07-19, planner — grounded on 50-RESEARCH baselines + verified anchors)

---
phase: 46
slug: per-task-substrate-cursor-live-layer-r1
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
---

# Phase 46 — Validation Strategy

> Per-phase validation contract. Sourced from 46-RESEARCH.md "## Validation Architecture"; per-task map filled by the planner (2026-07-19).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, cwd `backend/`) |
| **Config file** | `backend/pyproject.toml` (existing) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` |
| **Full suite command** | targeted battery ONLY: restart_resume + wave_scheduler + fanout suites + subagent_runs + per_task_capture + the 5 characterization files + banned_patterns + migration_ledger + test_migrations, then `/opt/homebrew/bin/lint-imports` (from `backend/`) |
| **Estimated runtime** | quick ~2s · battery ~90s |

**NEVER the full backend suite (hangs offline). NEVER live Bedrock in executors. Migration reversibility proven on offline SQLite (upgrade → downgrade → upgrade, explicit revisions).**

**Pre-phase baseline (recorded by 46-RESEARCH, 2026-07-19):** at-risk sweep 61 passed / 1 failed (the KAN-88 anchor — stays red); `test_migrations.py` has 2 PRE-EXISTING stale-head fails (assert heads==0016/0023 at head 0025 — NOT this phase's; new migration tests must be source-assertions, never "fix" those); `test_attach_replay_matrix` 1 pre-existing SSE fail; goldens 10/10. Verify BY DELTA against this baseline.

---

## Sampling Rate

- **After every task commit:** quick run (the task's new test(s) + `test_restart_resume.py`, ~2s) — RED→GREEN + KAN-88 unchanged.
- **After every plan wave:** full targeted battery + `lint-imports`.
- **Before verification:** battery at baseline-delta-zero (only intended new greens; KAN-88 + the 2 stale-head + 1 SSE fails unchanged).
- **Max feedback latency:** 120 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 46-01-T1 | 46-01 | 1 | RESUME-06 | T-46-01-03 | additive nullable columns, no table rewrite/backfill | source-assertion + alembic round-trip | `python3.11 -m pytest tests/unit/test_migrations.py -k "0026 or additive" tests/agents/test_subagent_runs.py -q` | NEW test_migration_0026_is_additive + reversibility | ⬜ |
| 46-01-T2 | 46-01 | 1 | RESUME-06 | T-46-01-01 | kernel-derived identity via owner-scoped ScopedStore | RED→GREEN spawn-identity | `python3.11 -m pytest tests/agents/test_subagent_runs.py tests/agents/test_fanout.py tests/agents/test_wave_scheduler.py -q` | test_subagent_runs.py (+2) | ⬜ |
| 46-02-T1 | 46-02 | 2 | RESUME-07 | T-46-02-01 | .uploads/ + images excluded from capture | RED (multi-file) + byte-neutrality | `python3.11 -m pytest tests/agents/test_per_task_capture.py -q` | NEW test_per_task_capture.py | ⬜ |
| 46-02-T2 | 46-02 | 2 | RESUME-07 | T-46-02-02/04 | owner-scoped dedup read, no scope widening | RED→GREEN capture + goldens | `python3.11 -m pytest tests/agents/test_per_task_capture.py tests/agents/test_characterization_*.py -q` | test_per_task_capture.py | ⬜ |
| 46-03-T1 | 46-03 | 3 | RESUME-08 | T-46-03-01 | owner-scoped read; git never a substrate | RED (rematerialize + merge re-entry) | `python3.11 -m pytest tests/agents/test_restart_resume.py -k "rematerial or merge_reentry" -q` | test_restart_resume.py (+2) | ⬜ |
| 46-03-T2 | 46-03 | 3 | RESUME-08 | T-46-03-02 | path_for traversal-proof; .uploads/ filtered | RED→GREEN + goldens | `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_wave_scheduler.py tests/agents/test_characterization_*.py -q` | engine.py | ⬜ |
| 46-04-T1 | 46-04 | 4 | RESUME-09 | T-46-04-01 | kernel decides skip, agent never does | RED (per-task + per-worker skip) | `python3.11 -m pytest tests/agents/test_restart_resume.py -k "skip or resume_completed" -q` | context.py + test_restart_resume.py | ⬜ |
| 46-04-T2 | 46-04 | 4 | RESUME-09 | T-46-04-02/03 | owner-scoped reads; fail-safe=re-run; task_id key | RED→GREEN + goldens + banned-pattern | `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_wave_scheduler.py tests/agents/test_characterization_*.py tests/agents/test_banned_patterns.py -q` | engine.py/task_loop.py/wave_scheduler.py | ⬜ |
| 46-05-T1 | 46-05 | 5 | RESUME-10 | T-46-05-02/03/05 | engine-counter seq; unregister-in-finally; no app import | RED→GREEN live-wire + goldens | `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_characterization_*.py -q` | engine.py + app/main.py + test | ⬜ |
| 46-05-T2 | 46-05 | 5 | RESUME-11 | T-46-05-04 | owner-scoped run_events read; classification bound documented | RED→GREEN no-loss/no-duplicate pair | `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_characterization_*.py -q` | engine.py + test | ⬜ |

---

## Wave 0 Requirements

RED/regression tests to author FIRST (seed-durable-then-invoke idiom from the Phase-45 tests — real `ArtifactRef` dataclass, real `Step`/`TaskSource`, direct engine/strategy invocation; offline `shared_read` seed, no live isolated writes per register 11-05):

- [x] `test_migration_0026_is_additive` (source-assertion) + 0026 reversibility round-trip (46-01-T1)
- [x] fan-out/wave spawn-identity assertion — row carries `worker_index`+`task_id` (46-01-T2, RED on HEAD)
- [x] multi-file task_loop capture (siblings present, `.uploads/` excluded) + prototype byte-neutrality + dedup (46-02-T1, RED on HEAD)
- [x] durable→disk re-materialization (max-version, filtered) (46-03-T1, RED on HEAD)
- [x] mid-wave merge re-entry (fragments + `running` wave_run → merge re-runs) (46-03-T1, RED on HEAD)
- [x] per-task skip (completed task_num not re-dispatched) + per-worker wave skip (completed `task_id` filtered) (46-04-T1, RED on HEAD)
- [x] resumed-run live-wire — ectx registered + `chat_reply` card with engine-counter seq + unregister-in-finally (46-05-T1, RED on HEAD)
- [x] steering no-loss / no-duplicate pair (46-05-T2, RED on HEAD)

All Wave-0 tests live in existing files (`tests/unit/test_migrations.py`, `tests/agents/test_subagent_runs.py`, `tests/agents/test_restart_resume.py`) or the one NEW file (`tests/agents/test_per_task_capture.py`). No framework install needed (pytest + pytest-asyncio present).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live crash→resume ladder (steering/Concierge/cards on a resumed run; isolated-write fan-out; real merge) | RESUME-08/09/10 | live-Bedrock + isolated-write redirection is live-only (offline harness runs shared_read) | Milestone-end consolidated live pass (orchestrator-owned), NOT executors |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify (every task's `<verify><automated>` + `<acceptance_criteria>` carry exact commands)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has one)
- [x] Wave 0 covers all MISSING references (all new tests enumerated above)
- [x] No watch-mode flags (targeted `-q` runs only)
- [x] Feedback latency < 120s (quick ~2s, battery ~90s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-19)

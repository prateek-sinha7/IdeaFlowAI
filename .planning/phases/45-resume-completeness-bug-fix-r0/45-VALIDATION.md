---
phase: 45
slug: resume-completeness-bug-fix-r0
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-19
---

# Phase 45 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from 45-RESEARCH.md "## Validation Architecture" — the planner filled the per-task map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, cwd `backend/`) |
| **Config file** | `backend/pyproject.toml` (existing) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` |
| **Full suite command** | targeted battery ONLY: `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q` + `/opt/homebrew/bin/lint-imports` (from `backend/`) |
| **Estimated runtime** | quick ~2s · targeted battery ~50s |

**NEVER run the full backend pytest suite — it hangs offline (Chromium/Bedrock/Postgres-gated). NEVER run live Bedrock in executors.**

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full targeted battery + lint-imports
- **Before `/gsd-verify-work`:** Targeted battery green (with the ONE known pre-existing red `test_waiting_for_user_run_is_rearmed_not_driven` unchanged — verify by DELTA, never "fix" or delete it; it is Phase 49's anchor)
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 45-01-T1 | 45-01 | 1 | RESUME-05 | T-45-02 | A partial `task_loop` build classifies INCOMPLETE — no silent skip, no deliverable truncation (the data-integrity property). Companion guards over-correction. | unit (RED→GREEN) | `python3.11 -m pytest tests/agents/test_restart_resume.py::test_partial_task_loop_build_reenters_step_not_skipped tests/agents/test_restart_resume.py::test_completed_task_loop_build_stays_complete_no_rerun -q` | ❌ Wave 0 (new tests) | ⬜ pending |
| 45-01-T2 | 45-01 | 1 | RESUME-05 | T-45-01, T-45-02 | Classifier reads per-task refs + source_step plan content ONLY via the owner-scoped `ectx.scoped_store` (no scope widening); count-based completeness restores deliverable integrity; INV-1/INV-12 grep pins unchanged. | unit + characterization + banned-pattern + import-linter | `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q && /opt/homebrew/bin/lint-imports` | ✅ (engine.py exists) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] RED regression in `backend/tests/agents/test_restart_resume.py` — `test_partial_task_loop_build_reenters_step_not_skipped` (partial-build case, must FAIL on HEAD) + `test_completed_task_loop_build_stays_complete_no_rerun` (all-tasks-complete no-regression case), per 45-RESEARCH "RED-Case Construction". Written and observed RED by Plan 45-01 Task 1 before the fix (Task 2) lands.

*Existing infrastructure (SQLite ScopedStore harness in test_restart_resume.py + the 5-file characterization suite) covers everything else.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live crash-mid-build → auto-resume completes the deliverable on real Bedrock | RESUME-05 | live-Bedrock; project defer-live-verification convention | Covered by the milestone-end consolidated live pass (orchestrator-owned), NOT by executors |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (the 2 new regression tests)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner) — 2026-07-19

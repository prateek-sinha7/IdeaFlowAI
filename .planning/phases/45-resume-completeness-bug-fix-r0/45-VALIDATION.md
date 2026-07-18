---
phase: 45
slug: resume-completeness-bug-fix-r0
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 45 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from 45-RESEARCH.md "## Validation Architecture" — the planner fills the per-task map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, cwd `backend/`) |
| **Config file** | `backend/pyproject.toml` (existing) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` |
| **Full suite command** | targeted battery ONLY: `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py -q` + `/opt/homebrew/bin/lint-imports` (from `backend/`) |
| **Estimated runtime** | quick ~15s · targeted battery ~50s |

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
| (filled by planner) | | | RESUME-05 | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] RED regression in `backend/tests/agents/test_restart_resume.py` (partial-build classification case + all-tasks-complete no-regression case) — must FAIL before the fix, per 45-RESEARCH "RED-Case Construction"

*Existing infrastructure (SQLite ScopedStore harness in test_restart_resume.py + the characterization suite) covers everything else.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live crash-mid-build → auto-resume completes the deliverable on real Bedrock | RESUME-05 | live-Bedrock; project defer-live-verification convention | Covered by the milestone-end consolidated live pass (orchestrator-owned), NOT by executors |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

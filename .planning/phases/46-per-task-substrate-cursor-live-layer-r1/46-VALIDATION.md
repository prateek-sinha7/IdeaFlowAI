---
phase: 46
slug: per-task-substrate-cursor-live-layer-r1
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 46 — Validation Strategy

> Per-phase validation contract. Sourced from 46-RESEARCH.md "## Validation Architecture"; the planner fills the per-task map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, cwd `backend/`) |
| **Config file** | `backend/pyproject.toml` (existing) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` |
| **Full suite command** | targeted battery ONLY: restart_resume + wave_scheduler + fanout suites + subagent_runs + the 5 characterization files + banned_patterns + migration_ledger, then `/opt/homebrew/bin/lint-imports` (from `backend/`) |
| **Estimated runtime** | quick ~2s · battery ~90s |

**NEVER the full backend suite (hangs offline). NEVER live Bedrock in executors. Migration reversibility proven on offline SQLite (upgrade head → downgrade -1 → upgrade head).**

**Pre-phase baseline (recorded by 46-RESEARCH, 2026-07-19):** at-risk sweep 61 passed / 1 failed (the KAN-88 anchor — stays red); `test_migrations.py` has 2 PRE-EXISTING stale-head fails (assert heads==0016/0023 at head 0025 — NOT this phase's; new migration tests must be source-assertions, never "fix" those); `test_attach_replay_matrix` 1 pre-existing SSE fail; goldens 10/10. Verify BY DELTA against this baseline.

---

## Sampling Rate

- **After every task commit:** quick run
- **After every plan wave:** full targeted battery + lint-imports
- **Before verification:** battery at baseline-delta-zero (only intended new greens)
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | RESUME-06..11 | | | | | | ⬜ pending |

---

## Wave 0 Requirements

- [ ] (filled by planner — RED/regression tests per requirement, seed-durable-then-invoke idiom from the Phase-45 tests)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live crash→resume ladder (steering/Concierge/cards on a resumed run; isolated-write fan-out) | RESUME-08/09/10 | live-Bedrock + isolated-write redirection is live-only (offline harness runs shared_read) | Milestone-end consolidated live pass (orchestrator-owned), NOT executors |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

---
phase: 50
slug: user-resume-from-failed-r5
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 50 — Validation Strategy

> Sourced from 50-RESEARCH "## Validation Architecture"; planner fills the per-task map.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/unit/test_rest_resume.py tests/agents/test_restart_resume.py -q` (first file lands in Wave 0) |
| **Full suite command** | quick + rest_run_launch + rest_answers_cancel + rest_revisions + approve_review_ownership + sse_stream + mechanical_router + 5 characterization files + banned_patterns -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~10s · battery ~110s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (50-RESEARCH, 2026-07-19):** restart_resume **39/0** · rest_answers_cancel 9 · approve_review_ownership 6 · sse_stream 17 · mechanical_router 28 · goldens 10 · redo 4/3 HELD · declared_gate_streaming 3 env-reds HELD · lint 4/0. Verify BY DELTA; no intended red→green flips this phase (KAN-88 already green).

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | RESUME-18 | | | | | | ⬜ |

## Wave 0 Requirements

- [ ] (filled by planner)

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live reopen-and-fix on real Bedrock (fail mid-build → POST /resume → deliverable completes; FE auto-attach) | RESUME-18 | live env + real SSE | Milestone-end pass (orchestrator-owned) |

## Validation Sign-Off

- [ ] automated verifies · [ ] continuity · [ ] Wave 0 · [ ] no watch-mode · [ ] latency <120s · [ ] nyquist_compliant flipped

**Approval:** pending

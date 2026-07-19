---
phase: 49
slug: gate-resume-across-restart-r4
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 49 — Validation Strategy

> Sourced from 49-RESEARCH "## Validation Architecture"; planner fills the per-task map.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` |
| **Full suite command** | quick + redo_gate_safety + approve_review_ownership + mechanical_router + sse_stream + the 5 characterization files + banned_patterns -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~8s · battery ~100s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (49-RESEARCH, 2026-07-19):** restart_resume **24 passed / 1 failed** — the 1 = KAN-88 `test_waiting_for_user_run_is_rearmed_not_driven`, THE RED→GREEN TARGET of this phase (the one pre-existing red we finally FLIP, per the POR §5.5 restoration mandate) · redo_gate_safety 4/3 (pre-existing, HELD — never fix) · declared_gate_streaming 3 env-gated reds (Postgres-FK offline artifact — HELD, not phase-related) · goldens 10/10 · banned_patterns 11 · sse_stream 17 · mechanical_router 28 · lint 4/0. Verify BY DELTA; the ONLY intended red→green flip is KAN-88.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | RESUME-17 | | | | | | ⬜ |

## Wave 0 Requirements

- [ ] (filled by planner)

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live restart-mid-gate (review + clarify) on real Bedrock incl. D-14g attach surfacing | RESUME-17 | live env + real SSE client | Milestone-end pass (orchestrator-owned) |

## Validation Sign-Off

- [ ] automated verifies · [ ] continuity · [ ] Wave 0 · [ ] no watch-mode · [ ] latency <120s · [ ] nyquist_compliant flipped

**Approval:** pending

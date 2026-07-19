---
phase: 48
slug: task-identity-mutable-list-reconciliation-r3
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 48 — Validation Strategy

> Sourced from 48-RESEARCH "## Validation Architecture"; planner fills the per-task map.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_task_identity.py -q` (second file lands in Wave 0) |
| **Full suite command** | quick + per_task_capture + wave_scheduler + json_tasks + subagent_runs + redo_gate_safety + 5 characterization files + banned_patterns -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~5s · battery ~90s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (48-RESEARCH, 2026-07-19):** restart_resume 16/1 (KAN-88 sole red) · per_task_capture 4 · wave_scheduler 10 · json_tasks 12 · subagent_runs 18 · **redo_gate_safety 4 passed / 3 FAILED (PRE-EXISTING harness drift on clean HEAD — NOT this phase's; verify-by-delta, never "fix"/delete)** · goldens 10 · lint 4/0. CONTEXT's "redo 7/0" expectation is stale — RESEARCH's measured baseline governs.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | RESUME-14/15/16 | | | | | | ⬜ |

## Wave 0 Requirements

- [ ] (filled by planner)

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live edit→resume ladder on real Bedrock | RESUME-14..16 | live env | Milestone-end pass (orchestrator-owned) |

## Validation Sign-Off

- [ ] automated verifies · [ ] continuity · [ ] Wave 0 · [ ] no watch-mode · [ ] latency <120s · [ ] nyquist_compliant flipped

**Approval:** pending

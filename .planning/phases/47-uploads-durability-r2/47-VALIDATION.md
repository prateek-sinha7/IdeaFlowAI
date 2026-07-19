---
phase: 47
slug: uploads-durability-r2
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 47 — Validation Strategy

> Sourced from 47-RESEARCH.md "## Validation Architecture"; the planner fills the per-task map.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd to `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/unit/test_run_files_upload.py tests/agents/test_uploaded_files_provider.py -q` |
| **Full suite command** | quick + `tests/agents/test_restart_resume.py` + the 5 characterization files + `tests/agents/test_banned_patterns.py` -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~8s · battery ~60s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (47-RESEARCH, 2026-07-19):** test_run_files_upload 20 ✅ · test_uploaded_files_provider 16 ✅ · test_restart_resume 16 ✅ / 1 red (KAN-88 — stays) · goldens 10 ✅ · lint 4/0 · registry drift-guard 69. Verify BY DELTA.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | RESUME-12/13 | | | | | | ⬜ |

## Wave 0 Requirements

- [ ] (filled by planner)

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live upload→crash→resume doc-context proof on real Bedrock | RESUME-12/13 | live env | Milestone-end pass (orchestrator-owned) |

## Validation Sign-Off

- [ ] All tasks have automated verify · [ ] continuity · [ ] Wave 0 coverage · [ ] no watch-mode · [ ] latency <60s · [ ] nyquist_compliant flipped

**Approval:** pending

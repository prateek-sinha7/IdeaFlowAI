---
phase: 49
slug: gate-resume-across-restart-r4
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
---

# Phase 49 — Validation Strategy

> Sourced from 49-RESEARCH "## Validation Architecture"; planner filled the per-task map.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` |
| **Full suite command** | quick + redo_gate_safety + `test_characterization_*.py` + banned_patterns + sse_stream + mechanical_router + rest_answers_cancel -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~8s · battery ~100s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (49-RESEARCH, 2026-07-19):** restart_resume **24 passed / 1 failed** — the 1 = KAN-88 `test_waiting_for_user_run_is_rearmed_not_driven`, THE RED→GREEN TARGET of this phase (the one pre-existing red we finally FLIP, per the POR §5.5 restoration mandate) · redo_gate_safety 4/3 (pre-existing, HELD — never fix) · declared_gate_streaming 3 env-gated reds (Postgres-FK offline artifact — HELD, not phase-related) · goldens 10/10 · banned_patterns 11 · sse_stream 17 · mechanical_router 28 · rest_answers_cancel 9 · lint 4/0. Verify BY DELTA; the ONLY intended red→green flip is KAN-88.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 49-01 T1 shared pendency + IN-02 accessor | 49-01 | 1 | RESUME-17 (SC-2) | T-49-01-03 | in-memory accessor only; ownership at REST unchanged | refactor/regression | `pytest tests/unit/test_mechanical_router.py tests/unit/test_sse_stream.py tests/unit/test_rest_answers_cancel.py -q && lint-imports` | ✅ (baseline suites) | ⬜ |
| 49-01 T2 branch-(a) re-arm + KAN-88 flip | 49-01 | 1 | RESUME-17 (SC-1, SC-5) | T-49-01-01/02/04 | owner-scoped read; arm-then-classify fail-safe; no runaway driver | RED→GREEN + new | `pytest tests/agents/test_restart_resume.py -q` | ✅ (KAN-88 anchor) / ❌ 3 new (Wave 0) | ⬜ |
| 49-02 T1 offset override + gate_reentry + 5 actions | 49-02 | 2 | RESUME-17 (SC-3) | T-49-02-02/04 | model-skip read-only reconstruct; owner-scoped events | new | `pytest tests/agents/test_restart_resume.py -q` | ❌ (Wave 0) | ⬜ |
| 49-02 T2 redo/update_specs continuation + A2 + D-14g | 49-02 | 2 | RESUME-17 (SC-3) | T-49-02-01/03 | fail-safe-HIGH thread ids; no new ingress | new | `pytest tests/agents/test_restart_resume.py tests/unit/test_sse_stream.py -q` | ❌ (Wave 0) | ⬜ |
| 49-03 T1 clarify twin replay driver | 49-03 | 3 | RESUME-17 (SC-4, SC-5) | T-49-03-01/02/03 | owner-scoped replay; no gate-closing emit; unchanged answers ingress | new (KAN-88 twin) | `pytest tests/agents/test_restart_resume.py -q` | ❌ (Wave 0) | ⬜ |
| 49-03 T2 dormancy sweep + full battery | 49-03 | 3 | RESUME-17 (SC-5/INV-3) | T-49-03-04 | goldens/banned by construction; no re-baseline | regression | `pytest tests/agents/test_restart_resume.py tests/agents/test_redo_gate_safety.py tests/agents/test_characterization_*.py tests/agents/test_banned_patterns.py tests/unit/test_sse_stream.py tests/unit/test_mechanical_router.py -q ; lint-imports` | ✅ (baseline suites) / ❌ dormancy assert (Wave 0) | ⬜ |

## Wave 0 Requirements

- [ ] `tests/agents/test_restart_resume.py` — 49-01: fail-safe (arm-raise→WR-05 fail), uncompilable-legacy (→WR-05 fail), re-arm-spawn (arms + spawns a non-`resume_run` driver, status stays `waiting_for_user`). KAN-88 anchor is EXISTING (flips RED→GREEN, zero edits).
- [ ] `tests/agents/test_restart_resume.py` — 49-02: review five-actions (approve/reject/edit/redo/update_specs each identical post-restart, output reconstructed from the max-version ref); redo-numbering (2 seeded redo `gate_events` → next thread `:redo3`); a D-14g compatibility assertion (re-armed state satisfies `_dangling_review_gate`).
- [ ] `tests/agents/test_restart_resume.py` — 49-03: clarify twin (durable `questionnaire_ready` → re-emit replayed questions with NO `_generate_questions`, status `waiting_for_user`, `resume_run` not driven, answers proceed into dispatch); a dormancy assertion (a scripted run leaves `ectx.gate_reentry` unset + offset unchanged).
- [ ] Reuse `_ResumeHarness` (:188) + `_seed_workflow_run` (:374) + `write_ref`/`append_event` seed helpers — extend the file, do NOT create a new one. No framework install (pytest-asyncio present).

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live restart-mid-gate (review + clarify) on real Bedrock incl. D-14g attach surfacing | RESUME-17 | live env + real SSE client | Milestone-end pass (orchestrator-owned) |

## Validation Sign-Off

- [x] automated verifies · [x] continuity · [x] Wave 0 · [x] no watch-mode · [x] latency <120s · [x] nyquist_compliant flipped

**Approval:** approved (planner, 2026-07-19) — every task carries an `<automated>` command with a delta tally; the KAN-88 anchor is the single RED→GREEN flip; all new behavior has a Wave-0 test listed above.

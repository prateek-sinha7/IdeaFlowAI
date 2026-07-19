---
phase: 48
slug: task-identity-mutable-list-reconciliation-r3
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-19
---

# Phase 48 — Validation Strategy

> Sourced from 48-RESEARCH "## Validation Architecture"; planner-filled per-task map.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_task_identity.py -q` (second file lands in Wave 0) |
| **Full suite command** | quick + per_task_capture + wave_scheduler + json_tasks + subagent_runs + redo_gate_safety + 5 characterization files + banned_patterns + sc001_* -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~5s · battery ~90s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (48-RESEARCH, 2026-07-19; verify-by-delta floor — re-baseline against the PRE-PHASE commit, never trust CONTEXT's stale "redo 7/0"):**
restart_resume **16/1** (KAN-88 `test_waiting_for_user_run_is_rearmed_not_driven` = SOLE red) · per_task_capture **4** · wave_scheduler **10** · json_tasks **12** · subagent_runs **18** · **redo_gate_safety 4 passed / 3 FAILED (PRE-EXISTING scripted-model harness drift on clean HEAD — NOT this phase's; hold at 4/3, never "fix"/delete/re-enable)** · goldens **10** (`SNAPSHOT_UPDATE` unset) · lint-imports **4 kept / 0 broken** · INV-1 grep `grep -cE 'pipeline_type ==|spec.id ==' agents/execution_engine/engine.py` == **0**.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 48-01 T1 | 48-01 | 1 | RESUME-14 | T-48-01 | Canonical-JSON sha256 key; no `hash()`/ts/uuid; ordinal-disambiguated; cross-restart stable | tdd (pure) | `python3.11 -m pytest tests/agents/test_task_identity.py -q` | ❌ (Wave 0) | ⬜ |
| 48-01 T2 | 48-01 | 1 | RESUME-14 | T-48-02 | Single upstream-hash home reused by input_hash + key handle (INV-12); owner-scoped tree read unchanged | unit | `python3.11 -m pytest tests/agents/test_restart_resume.py -k upstream_context_hash -q` + goldens 10 | ❌ (Wave 0) | ⬜ |
| 48-01 T3 | 48-01 | 1 | RESUME-14 | T-48-05 | Positional→key WRITE switch; goldens byte-neutral; INV-1 grep 0; legacy 64-char key never == positional | golden/contract | goldens 10/10 (`SNAPSHOT_UPDATE` unset) + `test_restart_resume.py` (updated cursor/skip contract tests) + lint 4/0 + INV-1 grep 0 | (updates existing) | ⬜ |
| 48-02 T1 | 48-02 | 2 | RESUME-15 | T-48-03 | Edit rides `/gate` (WR-03) only; new version + `derived_from` lineage; `max(version)` wins; no new table/endpoint | tdd | `python3.11 -m pytest tests/agents/test_task_list_gate_lineage.py -q` | ❌ (Wave 0) | ⬜ |
| 48-02 T2 | 48-02 | 2 | RESUME-16 | T-48-02 | ORDER-based common-prefix skip (never skip a suffix whose predecessor changed); p==0 first-task divergence → run all from empty basis; fail-safe = re-run | tdd | `python3.11 -m pytest tests/agents/test_restart_resume.py -k "reconcile_common_prefix or reconcile_first_task" -q` | ❌ (Wave 0) | ⬜ |
| 48-02 T3 | 48-02 | 2 | RESUME-16 | T-48-04 | Three-state boundary re-materialization (None→global-max / p>0→boundary version / p==0→restore-nothing, no negative-index); immutable rows read-only; `.uploads/` fence held | tdd | `python3.11 -m pytest tests/agents/test_restart_resume.py -k "reconcile_boundary_version or reconcile_first_task" -q` | ❌ (Wave 0) | ⬜ |
| 48-03 T1 | 48-03 | 3 | RESUME-16 | T-48-04 | Three-way fragment→key join: in-allow-set→restore / mappable-but-absent→EXCLUDE / unresolvable→fail-safe keep; excluded from merge + assembly at gate; merge impls untouched; rows never deleted | tdd | `python3.11 -m pytest tests/agents/test_restart_resume.py -k "reconcile_orphan_excluded or reconcile_unmappable" -q` | ❌ (Wave 0) | ⬜ |
| 48-03 T2 | 48-03 | 3 | RESUME-16 | T-48-02 | update_specs spec-v2 rotates upstream hash → all keys rotate → all build tasks re-run; no v1-key skipped | tdd | `python3.11 -m pytest tests/agents/test_restart_resume.py -k update_specs_reconcile_composes -q` | ❌ (Wave 0) | ⬜ |
| 48-03 T3 | 48-03 | 3 | RESUME-16 / SC-001 | T-48-01,T-48-04 | Synthetic non-prototype full reconcile (complete 2/4 → delete-completed+edit-pending+add → resume → exact set + orphan excluded); zero engine name-literals | tdd (sc001) | `python3.11 -m pytest tests/agents/test_sc001_reconcile.py tests/agents/test_banned_patterns.py -q` + `grep -rc "<name>" agents/execution_engine/ == 0` | ❌ (Wave 0) | ⬜ |

## Wave 0 Requirements

- [ ] `tests/agents/test_task_identity.py` — NEW (pure key/normalize/ordinal cases) — 48-01 T1
- [ ] `tests/agents/test_task_list_gate_lineage.py` — NEW (gate-edit `derived_from` on `task_list`) — 48-02 T1
- [ ] `test_restart_resume.py` new cases: `test_task_loop_reconcile_common_prefix`, `test_task_loop_reconcile_first_task_clean_basis` (p==0 restore-nothing / run-all), `test_task_loop_reconcile_boundary_version`, `test_wave_reconcile_orphan_excluded` (confidently-orphaned = mappable-but-absent), `test_wave_reconcile_unmappable_kept` (fail-safe keep), `test_update_specs_reconcile_composes`, plus a `_compute_upstream_context_hash` unit case — appended to the existing seed-durable harness (48-01 T2, 48-02 T2/T3, 48-03 T1/T2)
- [ ] `tests/agents/test_sc001_reconcile.py` (+ fixture reuse of `fixtures/sc001_task_loop/` or a small `sc001_reconcile` fixture) — NEW — 48-03 T3

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live edit→resume ladder on real Bedrock | RESUME-14..16 | live env | Milestone-end pass (orchestrator-owned); offline gates bind phase completion |

## Validation Sign-Off

- [x] automated verifies · [x] continuity · [x] Wave 0 · [x] no watch-mode · [x] latency <120s · [x] nyquist_compliant flipped

**Approval:** approved 2026-07-19 (planner; every task has an automated command, RED-before-change pinnable, all under 120s, verify-by-delta against the measured 16/1 + 4/3 baseline)

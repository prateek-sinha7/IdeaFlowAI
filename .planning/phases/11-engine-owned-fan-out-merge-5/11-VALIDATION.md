---
phase: 11
slug: engine-owned-fan-out-merge-5
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-10
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 (`python3.11 -m pytest`, no venv) |
| **Config file** | `backend/pyproject.toml` (pytest + import-linter contracts) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/test_fanout.py -x -p no:cacheprovider` |
| **Full suite command** | targeted offline suite per backend/CLAUDE.md (full pytest hangs offline): `test_characterization_*.py` + `test_banned_patterns.py` + `test_migration_ledger.py` + `test_compiler_trust.py` + `test_sc001_*.py` + `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | ~35–60 seconds (targeted suite) |

---

## Sampling Rate

- **After every task commit:** Run the new focused suite for the task's requirement (`pytest tests/agents/test_<area>.py -x -p no:cacheprovider`) + `lint-imports` if a capability/kernel module changed
- **After every plan wave:** Run full targeted offline suite + `lint-imports` (4 contracts kept / 0 broken) + characterization + banned-patterns + migration-ledger
- **Before `/gsd-verify-work`:** Full targeted suite green; 5 characterization snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset; live Bedrock deferred to end-of-milestone
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Filled by planner — task IDs map to the Phase Requirements → Test Map in 11-RESEARCH.md (§ Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | FANOUT-01..11, OBS-01, RESUME-01 (+ SC-001 fixture, INV-3 parity, INV-13 ratchet) | — | see RESEARCH.md test map | unit/integration/snapshot/ratchet/lint | see RESEARCH.md test map | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/test_fanout.py` — covers FANOUT-02/03/04/06 (funnel, worker selection, parallel/sequential modes, fragment summary)
- [ ] `tests/agents/test_fanout_tool.py` — covers FANOUT-01 (grant-gated binding incl. spawn-free grep assertion)
- [ ] `tests/agents/test_isolation.py` — covers FANOUT-05 (sub_sandbox/worktree, engine scope select, teardown)
- [ ] `tests/agents/test_merge.py` — covers FANOUT-07 (4 strategies, determinism, conflict detection)
- [ ] `tests/agents/test_merge_conflict.py` — covers FANOUT-08 (4 on_conflict policies, merge_conflict artifact+event, human_gate round-trip)
- [ ] `tests/agents/test_budget.py` — covers FANOUT-09 + OBS-01 (reserve-before-spawn, defaults, depth, wall-clock, workspace ceiling, snapshot persistence)
- [ ] `tests/agents/test_subagent_runs.py` + `0019` reversibility test — covers FANOUT-10
- [ ] `tests/agents/test_fanout_cancel.py` — covers FANOUT-11 + RESUME-01 (cancellation propagation, teardown asserted)
- [ ] `tests/agents/test_sc001_fanout.py` + `tests/agents/fixtures/sc001_fanout/` + `agents/workflows/<fanout fixture>/` — covers SC-001
- [ ] Add `subagent_runs` row(s) to the `0019` ledger entry (migration-ledger.md) so `test_migration_ledger.py` tracks it
- [ ] Scripted-model scaffolding for parallel workers (extend `tests/agents/_scripted_model.py`; `RUNS_ROOT` monkeypatch to temp dir)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live multi-worker fan-out against real Bedrock | FANOUT-04 | Offline suite uses scripted models; live concurrency behavior unobservable offline | Deferred to end-of-milestone live pass per project convention |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

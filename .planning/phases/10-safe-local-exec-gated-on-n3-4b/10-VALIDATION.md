---
phase: 10
slug: safe-local-exec-gated-on-n3-4b
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-10
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 (`python3.11 -m pytest`, no venv) |
| **Config file** | `backend/pytest.ini` / pyproject (existing) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/test_gates.py tests/agents/test_local_runtime.py -x -p no:cacheprovider` |
| **Full suite command** | targeted offline suite per backend/CLAUDE.md (full pytest hangs offline) + `/opt/homebrew/bin/lint-imports` + `test_characterization_*` + `test_banned_patterns.py` + `test_migration_ledger.py` |
| **Estimated runtime** | ~35 seconds (targeted suite) |

---

## Sampling Rate

- **After every task commit:** Run the relevant `tests/agents/test_*.py -x -p no:cacheprovider` (quick)
- **After every plan wave:** Run full targeted offline suite + `lint-imports` + characterization + banned-patterns + migration-ledger
- **Before `/gsd-verify-work`:** Full targeted suite must be green; all 14 SPEC acceptance criteria green; 5 characterization snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Filled by planner — task IDs map to the Phase Requirements → Test Map in 10-RESEARCH.md (§ Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | EXEC-01 / EXEC-02 (SPEC: EXEC-PROFILE, EXEC-POLICY, EGRESS-DENY, GRANT-PATH, GATES, AUDIT, VALIDATORS, VALIDATOR-DENY, DEBT+PARITY) | — | see RESEARCH.md test map | unit/engine/migration/grep | see RESEARCH.md test map | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/test_code_validators.py` — covers VALIDATORS + VALIDATOR-DENY (new)
- [ ] `tests/agents/fixtures/sample_python_repo/` — tiny compile+test fixture + lint-error seed
- [ ] Grow `tests/agents/test_local_runtime.py` — EXEC-PROFILE + EXEC-POLICY
- [ ] Grow `tests/agents/test_gates.py` — security profile-pass + approval first-exec + approve/reject + no-re-pause
- [ ] New compiler test — GRANT-PATH trust-conditional + D-01 gates-required CompilerError
- [ ] New `exec_runs` migration (0018) + ORM model test (reversibility + scoped writes)
- [ ] Grow `tests/agents/test_repo_diff.py` — IN-03 unparseable-header synthetic key
- [ ] `shell=True` grep assertion (standalone test OR migration-ledger IN-02 row)
- [ ] Registry count guard: bump `test_registry_capabilities.py` `== 50` → `== 53`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live egress denial against a real network | EGRESS-DENY | Offline suite cannot observe live network; policy-level denial is unit-tested, residual documented | Deferred to end-of-milestone live pass per project convention |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

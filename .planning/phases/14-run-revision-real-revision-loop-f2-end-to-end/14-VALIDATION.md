---
phase: 14
slug: run-revision-real-revision-loop-f2-end-to-end
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 on python3.11 (no venv) |
| **Config file** | backend test layout per backend/CLAUDE.md (tests/unit, tests/agents) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/unit/test_revision_intelligence.py tests/unit/test_run_revision_fe_contract.py tests/agents/test_manifest_parity.py -x -q` |
| **Full suite command** | targeted battery: 5 characterization suites + `test_banned_patterns.py` + `test_migration_ledger.py` + touched suites + `/opt/homebrew/bin/lint-imports` (full pytest hangs offline — never block on it) |
| **Estimated runtime** | ~35 seconds (targeted battery); <30s quick run |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (two revision suites + manifest parity, `-x -q`, <30s)
- **After every plan wave:** Run the targeted battery (~35s)
- **Before `/gsd-verify-work`:** Targeted battery must be green; live-Bedrock items recorded as deferred (milestone-end live pass)
- **Max feedback latency:** 35 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD (planner fills) | — | — | SC1 — run_revision drives real revision agents; deliverable is the revised artifact | — | revision dispatch stays owner/workspace-scoped | unit (scripted models) | `cd backend && python3.11 -m pytest tests/unit/test_run_revision_fe_contract.py -x` | ✅ (rewrite to real-dispatch contract) | ⬜ pending |
| TBD (planner fills) | — | — | SC2 — `derived_from` lineage + owner/workspace scope + revision-of-revision (FR-014 chain link 1) | — | lineage rows carry owner_id + workspace_id | unit | `cd backend && python3.11 -m pytest tests/unit/test_revision_intelligence.py -x` | ✅ (rewrite storage/lineage tests; keep guards) | ⬜ pending |
| TBD (planner fills) | — | — | SC3a — non-revision goldens byte/event-identical (INV-3) | — | N/A | characterization | `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_prototype_revision.py -q` | ✅ | ⬜ pending |
| TBD (planner fills) | — | — | SC3b — no workflow-name literal in the kernel (SC-001) | — | N/A | gate | `cd backend && python3.11 -m pytest tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q` | ✅ | ⬜ pending |
| TBD (planner fills) | — | — | SC3c — manifest parity (planner flip pinned) | — | N/A | unit | `cd backend && python3.11 -m pytest tests/agents/test_manifest_parity.py -q` | ✅ (update planner-run-everywhere expectation) | ⬜ pending |
| TBD (planner fills) | — | — | SC3d — import boundaries | — | N/A | lint | `cd backend && /opt/homebrew/bin/lint-imports` | ✅ (4 contracts kept / 0 broken baseline) | ⬜ pending |
| TBD (planner fills) | — | — | revision gating unchanged (`revises_existing` only on prototype_revision) | — | N/A | unit | `cd backend && python3.11 -m pytest tests/agents/test_revision_gating.py -q` | ✅ unchanged | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/_scripted_model.py` — additive: dedicated `od-ppt-revision-agent` entry in `_scripts_for` emitting an `<artifact>`-wrapped revised deck (generic fallback works but yields weak assertions)

*Otherwise: existing infrastructure covers all phase requirements — both named suites and the scripted-model harness exist.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| FE-exact `run_revision` frame → revised deck in the preview on real Bedrock | SC4 | Live model + FE preview; offline harness cannot observe real Bedrock output | Milestone-end live pass (deferred BY CONVENTION — defer-live-verification-to-milestone-end; not a Wave 0 gap) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 35s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

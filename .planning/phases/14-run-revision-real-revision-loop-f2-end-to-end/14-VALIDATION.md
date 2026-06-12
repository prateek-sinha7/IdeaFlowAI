---
phase: 14
slug: run-revision-real-revision-loop-f2-end-to-end
status: ready
nyquist_compliant: true
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
| 14-01-01 | 14-01 | 1 | SC3c — manifest parity (planner flip pinned in BOTH traps); SC1 precondition (no clarify hang); revision gating unchanged (`revises_existing` only on prototype_revision); INV-3 (prototype_revision golden untouched) | T-14-01-01, T-14-01-02 | injects-free pin test makes the settled design wrinkle executable (an inject-declaring revision agent fails CI) | unit + characterization + lint | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_manifest_parity.py tests/agents/test_id_alias_resolver.py tests/agents/test_revision_gating.py tests/agents/test_characterization_prototype_revision.py -q && /opt/homebrew/bin/lint-imports` | ✅ (both traps updated in place) | ⬜ pending |
| 14-01-02 | 14-01 | 1 | Wave 0 item — deterministic scripted revision-agent turns (SC1/SC2 test precondition for 14-03/14-04) | — | N/A (test harness, additive only) | unit (source asserts) + characterization | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -c "from tests.agents._scripted_model import _scripts_for; assert _scripts_for('od-ppt-revision-agent')[0].texts[0] != _scripts_for('ppt-revision-assembler')[0].texts[0]; assert '<artifact>' in _scripts_for('od-ppt-revision-agent')[0].texts[0]; assert '<artifact>' in _scripts_for('ppt-revision-assembler')[0].texts[0]; assert '<artifact>' not in _scripts_for('ppt-revision-agent')[0].texts[0]" && python3.11 -m pytest tests/agents/test_characterization_od_ppt.py tests/unit/test_run_revision_fe_contract.py -q` | ✅ `_scripted_model.py` exists — additive branches | ⬜ pending |
| 14-02-01 | 14-02 | 1 | SC1 (WS half) — non-blocking queue dispatch (Pitfall 3), terminal-status fidelity (Pitfall 4), registry-derived agent_count (Pitfall 6) | T-14-02-01..05 | owner_id=user.id threads to the engine; reconnect/cancel stay owner-gated; ingress error vocabulary byte-unchanged | unit + lint | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -c "import app.api.websocket as w; assert hasattr(w, '_handle_revision_execution')" && python3.11 -m pytest tests/unit/test_run_pipeline_validation.py tests/unit/test_pipeline_failure_semantics.py -q && /opt/homebrew/bin/lint-imports` | ✅ (websocket.py refactor in place) | ⬜ pending |
| 14-02-02 | 14-02 | 1 | SC1 (WS half) regression — queue-dispatch contract: section stamping, completed/failed/cancelled status, error vocabulary, agent_count, cleanup | T-14-02-01 | failed/cancelled revisions never recorded "completed" (FE revision-parent lookup keyed on status) | unit | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/unit/test_run_revision_ws_dispatch.py -x -q && python3.11 -m pytest tests/unit/test_run_pipeline_validation.py tests/unit/test_pipeline_failure_semantics.py -q` | ➕ new file (created by this task) | ⬜ pending |
| 14-03-01 | 14-03 | 2 | SC1+SC2 (engine half) — real execute() dispatch + guarded exact-kind lineage write; SC3a — goldens byte/event-identical; SC3b — no kernel workflow-name literal | T-14-03-01..06 | assert_owns stays FIRST (T-5-SEED); lineage write guarded `final_output and not terminal_failed` | characterization + gate + lint | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py tests/agents/test_revision_gating.py -q && /opt/homebrew/bin/lint-imports` | ✅ (test_revision_intelligence RED until 14-04 — documented intra-phase intermediate) | ⬜ pending |
| 14-03-02 | 14-03 | 2 | SC1 — model runs observed, revised deck is final_output (never the context blob); SC2 — exact-kind `derived_from` lineage + revision-of-revision via FR-014 chain link 1; single-source seq (INV-12/SAFE-03) | T-14-03-05, T-14-03-06 | lineage ref owner/workspace-stamped, visibility="workspace"; reads via default-deny ScopedStore | unit (scripted models) | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/unit/test_run_revision_fe_contract.py -x -q && python3.11 -m pytest tests/agents/test_characterization_od_ppt.py tests/agents/test_banned_patterns.py -q` | ✅ exists — rewrite to real-dispatch contract | ⬜ pending |
| 14-04-01 | 14-04 | 3 | SC2/SC3 (test half) — stub-pinning suite rewritten to real dispatch; all eight guards byte-meaning-identical; run_events single-stamping seq trap; closes the 14-03 intermediate | T-14-04-01, T-14-04-02 | cross-owner PermissionError BEFORE any event + falsy-owner guard kept verbatim (presence grep-pinned) | unit (scripted models) | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/unit/test_revision_intelligence.py tests/unit/test_run_revision_fe_contract.py tests/agents/test_manifest_parity.py -x -q` | ✅ exists — rewrite storage/lineage tests; keep guards | ⬜ pending |
| 14-04-02 | 14-04 | 3 | SC3a–d phase gate — full targeted battery in one session + SC-001/INV-3/INV-12 grep sweep + SC3d import boundaries; SC4 deferral recorded in SUMMARY | — | N/A (gate task) | characterization + gate + lint | `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py tests/agents/test_manifest_parity.py tests/agents/test_id_alias_resolver.py tests/agents/test_revision_gating.py tests/unit/test_revision_intelligence.py tests/unit/test_run_revision_fe_contract.py tests/unit/test_run_revision_ws_dispatch.py tests/unit/test_run_pipeline_validation.py tests/unit/test_pipeline_failure_semantics.py -q && /opt/homebrew/bin/lint-imports` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Requirement coverage: SC1 → 14-02-01/14-02-02 (WS half) + 14-03-01/14-03-02 (engine half) · SC2 → 14-03-01/14-03-02/14-04-01 · SC3a → 14-03-01/14-04-02 · SC3b → 14-03-01/14-04-02 · SC3c → 14-01-01 · SC3d → lint-imports in 14-01-01/14-02-01/14-03-01/14-04-02 · revision gating → 14-01-01 · SC4 → manual-only (deferred, below).

---

## Wave 0 Requirements

- [ ] `tests/agents/_scripted_model.py` — additive: dedicated `od-ppt-revision-agent` entry in `_scripts_for` emitting an `<artifact>`-wrapped revised deck (generic fallback works but yields weak assertions)

*Delivered by task 14-01-02 during execution (plan 14-01 expands this to all three revision agents: `od-ppt-revision-agent`, `ppt-revision-agent`, `ppt-revision-assembler`); `wave_0_complete` flips true at that task's commit. Otherwise: existing infrastructure covers all phase requirements — both named suites and the scripted-model harness exist.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| FE-exact `run_revision` frame → revised deck in the preview on real Bedrock | SC4 | Live model + FE preview; offline harness cannot observe real Bedrock output | Milestone-end live pass (deferred BY CONVENTION — defer-live-verification-to-milestone-end; not a Wave 0 gap) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (8/8 tasks carry an `<automated>` command; the single Wave 0 item is itself task 14-01-02)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no `<automated>MISSING ...` entries exist; the one additive harness item is owned by 14-01-02)
- [x] No watch-mode flags
- [x] Feedback latency < 35s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-12

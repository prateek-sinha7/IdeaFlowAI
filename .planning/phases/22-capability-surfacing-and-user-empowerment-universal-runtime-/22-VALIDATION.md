---
phase: 22
slug: capability-surfacing-and-user-empowerment-universal-runtime
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-14
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `22-RESEARCH.md` § Validation Architecture (Nyquist enabled). The Per-Task map
> below is keyed by **requirement** until plans assign task IDs; the planner/executor refine it
> into per-task rows. Requirement evidence lives in `22-SPEC.md`; HOW decisions in `22-CONTEXT.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (BE)** | pytest — `python3.11 -m pytest` from `backend/` (no venv) |
| **Framework (FE)** | vitest (`npm test`) + Playwright e2e (`npm run e2e`, mocked-green at `frontend/e2e/`) |
| **Config file** | `backend/` pytest project default; `frontend/` vitest config |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py -q` (the INV-3 goldens floor) |
| **Full targeted suite** | `cd backend && python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -q` (expect 44 passed / 7 skipped) + `lint-imports` + SC-001 grep |
| **Estimated runtime** | ~35 seconds (targeted suite); goldens-only ~10s |

> The full backend pytest hangs offline (Chromium/Bedrock/Postgres-gated) — always use the targeted
> parity/gate suite, never `pytest` bare (project memory: offline-test-suite-targeted).

---

## Sampling Rate

- **After every task commit:** Run the **quick goldens command** — the INV-3 byte+event-parity floor on every backend change.
- **After every plan wave:** Run the **full targeted suite (~35s)** + `lint-imports` (4 kept / 0 broken) + the SC-001 kernel name-free grep.
- **Before `/gsd-verify-work`:** Full targeted suite green + `test_capabilities_api.py` + the new WIRE-03 parametrized test + FE `npm test` + `npx tsc --noEmit`.
- **Max feedback latency:** ~35 seconds.

---

## Per-Requirement Verification Map

> Planner refines into per-task rows (`22-PP-TT` ids) once plans exist. `❌ W0` = Wave-0 test gap to author first.

| Requirement | Wave | Secure Behavior (V4/V5) | Test Type | Automated Command | File Exists | Status |
|-------------|------|-------------------------|-----------|-------------------|-------------|--------|
| SURF-01 | early | Palette renders from payload only — no hardcoded cap-name array (SC-001) | grep + FE unit | `grep -rnE "\[.*('strategy'\|\"strategy\").*('validator'\|\"validator\")" frontend/src/components/workflow/` → 0; FE render test vs fixture payload | ❌ W0 | ⬜ pending |
| SURF-02 | early | `description` + security-gated + `config_schema` additive; `Depends(get_current_user)` + keys preserved (API-02) | unit | `python3.11 -m pytest tests/unit/test_capabilities_api.py -q` | ✅ extend | ⬜ pending |
| SURF-03 | mid | Composer shows compiled per-step caps from registry projection | FE unit / integration | FE test rendering the compiled-capability projection | ❌ W0 | ⬜ pending |
| EMP-01 | mid | Chosen validator fires / chosen model resolved / retry activates under injected fault | integration | `python3.11 -m pytest tests/unit/ -k "user_workflow_launch or compose_launch"` (new) | ❌ W0 | ⬜ pending |
| EMP-02 | mid | Smuggled `user_allowed=False` rejected at SAVE **and** LAUNCH (`_check_trust`, CAP-03) | unit | `python3.11 -m pytest tests/agents/test_compiler.py -k "trust or user_allowed"` + new save/launch rejection test | ✅ compiler / ❌ save+launch W0 | ⬜ pending |
| EMP-03 | mid | Selections round-trip (save→list→reopen); cross-owner GET → 404 (IDOR); additive persistence | unit | new `tests/unit/test_user_workflows_selections.py`; `python3.11 -m pytest tests/unit/test_user_workflows*.py` | ❌ W0 | ⬜ pending |
| EMP-04 | mid | Coupled-gate auto-attach (FE) + compiler backstop raises on missing gate | unit | `python3.11 -m pytest tests/agents/test_compiler.py -k "gate or coupling"` + FE auto-attach test | ✅ backstop / ❌ FE W0 | ⬜ pending |
| WIRE-01 | early | Per-step + top-level `model:` changes resolved model; goldens byte-identical | unit | `python3.11 -m pytest tests/agents/test_compiler.py -k model`; goldens suite | ❌ W0 | ⬜ pending |
| WIRE-02 | early | `retry:{max_attempts:N}` activates wrapper under injected throttle; no-retry stays parity | unit | `python3.11 -m pytest tests/unit/ -k "retry"` | ❌ W0 | ⬜ pending |
| WIRE-03 | early | Parametrized over `_ALLOWED_STEP_KEYS`: each key consumed OR raises `CompilerError`; goldens byte-identical | unit | new `tests/agents/test_allowed_step_keys.py`; extend `tests/unit/test_factory_injects.py` for the merge | ✅ factory_injects / ❌ allowed_step_keys W0 | ⬜ pending |
| UXFIX-01 | late | `display_name` renders in catalog; BE fallback null only where intended | unit | `python3.11 -m pytest tests/agents/test_manifest.py tests/unit/test_workflows_api.py -k display_name` | ✅ extend | ⬜ pending |
| UXFIX-02 | early | Binary deliverable re-renders from persisted mimetype; migration additive; goldens byte-identical (keys in `_VOLATILE_STRIP_KEYS`) | unit | `python3.11 -m pytest tests/unit/test_deliverable_mimetype.py` + new migration/reopen test | ✅ extend | ⬜ pending |
| UXFIX-03 | late | Default landing renders `WorkflowCatalog`; `CreationHub.WORKFLOWS` no longer drives home | FE unit | FE test asserting default `mainView==="catalog"` / catalog mount | ❌ W0 | ⬜ pending |
| UXFIX-04 | late | Custom deliverable via generic path as PRIMARY; first-party render identical (no regression) | FE unit | extend PreviewPanel per-type render tests; e2e mocked | ✅ extend | ⬜ pending |
| DECIDE-01 | doc | ART-04 keep-by-default; 3 stale "confirm" labels (REPO-02/REPO-04/FANOUT-05) reconciled; no retention default contradicts | assertion | `grep -n "confirm" .planning/REQUIREMENTS.md` for the three → reconciled; doc review | N/A doc | ⬜ pending |
| DECIDE-02 | doc + FE | MODEL-05 premium-open-to-all-tiers; picker offers premium to non-premium tier (filter removed at `AgentModelPicker.tsx:76`); fallback chain documented | FE unit + doc | FE test: picker renders premium model for non-premium tier | ❌ W0 | ⬜ pending |
| LIVE-01 | deferred | Per-item evidence (8 deferrals) — CONFIRMED-live or explicit disposition | manual (deferred) | Milestone-end live pass on AWS `default` profile, Haiku 4.5 (D-24) | N/A deferred | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/test_allowed_step_keys.py` — WIRE-03 parametrized over `_ALLOWED_STEP_KEYS` (each key consumed or raises)
- [ ] `tests/unit/test_user_workflows_selections.py` — EMP-03 round-trip + IDOR→404 + launch re-validation
- [ ] Extend `tests/agents/test_compiler.py` — WIRE-01 (`model:`) + WIRE-02 (`retry:`) materialization
- [ ] BE save/launch trust-rejection test (EMP-02) — extend compiler test + new save/launch endpoint test
- [ ] Extend `tests/unit/test_factory_injects.py` — the `step.injects` + AGENT.md merge (WIRE-03 consume side)
- [ ] UXFIX-02 reopen-from-persisted-mimetype test + migration `0022` additive test
- [ ] FE palette render test (SURF-01: no-hardcoded-array + grouped rows + locked rows for `user_allowed=False`)
- [ ] FE Advanced-expander test (EMP-01 lever selection) + EMP-04 auto-attach test
- [ ] FE catalog-as-home test (UXFIX-03) + DECIDE-02 picker-offers-premium test
- [ ] FE compiled-capability projection test (SURF-03)

---

## Invariant-Proof Commands (the falsifiable checks)

```bash
# INV-3 — 5 characterization goldens byte + event identical
cd backend && python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py -q

# SC-001 — kernel knows no workflow by name (grep == 0) + banned-pattern gate
cd backend && python3.11 -m pytest tests/agents/test_banned_patterns.py -q
grep -nE "if pipeline_type ==|spec\.id ==" agents/workflows/compiler.py agents/execution_engine/engine.py   # → 0 on routed paths

# INV-13 — create_deep_agent only in the adapter (sole site app/agents/deep_agent_runner.py:291)
cd backend && python3.11 -m pytest tests/agents/test_banned_patterns.py -k "deep_agent" -q

# Ports & Adapters — import-linter 4 kept / 0 broken
lint-imports                                   # /opt/homebrew/bin/lint-imports

# Additive migration only — new 0022 additive (no drop/alter-narrow), owner_id/workspace_id scope present
cd backend && python3.11 -m pytest tests/unit/ -k "migration" -q   # + manual review of alembic/versions/0022_*.py

# SURF-02 contract
cd backend && python3.11 -m pytest tests/unit/test_capabilities_api.py -q

# FE
cd frontend && npm test && npx tsc --noEmit
```

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Consolidated live-Bedrock evidence pass (8 standing deferrals) | LIVE-01 | Requires live AWS entitlement; deferred to milestone-end per D-24 / defer-live-verification convention | Run on AWS `default` profile (acct 473293451041) with `claude-haiku-4-5`; record CONFIRMED-live or explicit disposition per item: COMPACT-03 · P6 CR-02 · P8 OTLP · P13 F1/F4/F5 · P14 SC4 · P16 SC1/SC2 · P19 ISS-004 |
| Visual no-regression of the 4 first-party deliverable types via the generic dispatch | UXFIX-04 | Pixel-level visual parity is eyeball-verified beyond the unit render tests | Open user_stories / app_builder / ppt / prototype deliverables; confirm identical render through the generic-primary path |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 35s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

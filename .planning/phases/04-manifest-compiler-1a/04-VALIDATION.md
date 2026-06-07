---
phase: 4
slug: manifest-compiler-1a
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-07
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `04-RESEARCH.md` § Validation Architecture. Task-ID column is finalized during planning; the requirement→test rows below are the authoritative coverage contract.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/test_<new>.py -x` |
| **Full suite command** | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |
| **Estimated runtime** | ~60–120 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3.11 -m pytest tests/agents/test_<touched>.py -x`
- **After every plan wave:** Run `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -x` + `lint-imports` + `vulture app/ agents/`
- **Before `/gsd-verify-work`:** Full suite green + all characterization snapshots green + migration-ledger green
- **Max feedback latency:** ~120 seconds

---

## Per-Requirement Verification Map

> Task-ID assigned during planning. `File Exists` ❌ W0 = test is a Wave-0 dependency (does not exist yet); ✅ = existing infra.

| Plan (target) | Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|---------------|-------------|----------|-----------|-------------------|-------------|--------|
| 04-01 | MAN-01 | well-formed `workflow.yaml` → populated `WorkflowManifest`; every authored manifest loads clean | unit | `pytest tests/agents/test_manifest.py -x` | ❌ W0 | ⬜ pending |
| 04-01 | MAN-01 | missing required field → `ManifestValidationError` NAMING the field | unit | `pytest tests/agents/test_manifest.py::test_missing_field_named -x` | ❌ W0 | ⬜ pending |
| 04-01 / INV-5 | MAN-02 | manifest with control-flow construct (`when:`/`if:`/`for:`/`${}`/`{{}}`) is REJECTED | unit | `pytest tests/agents/test_compiler.py::test_rejects_dsl -x` | ❌ W0 | ⬜ pending |
| 04-02 | MAN-02 | each authored manifest compiles to a `CompiledWorkflow` whose steps/agents/deliverable/clarify/planner match | unit | `pytest tests/agents/test_compiler.py::test_compiles_clean -x` | ❌ W0 | ⬜ pending |
| 04-02 / INV-1 | MAN-02 | structure test: `compiler.py` source contains NO `pipeline_type`/workflow-name branch | structure | `pytest tests/agents/test_compiler.py::test_no_name_branch -x` | ❌ W0 | ⬜ pending |
| 04-02 / INV-4 | MAN-03 | unknown capability ref (`strategy: nonexistent`) → compile error NAMING the bad ref | unit | `pytest tests/agents/test_compiler.py::test_unknown_capability -x` | ❌ W0 | ⬜ pending |
| 04-02 | MAN-03 | `base.py` ports + `registry.py` exist; known names registered; all 15 manifests reference only registered names | unit | `pytest tests/agents/test_registry_capabilities.py -x` | ❌ W0 | ⬜ pending |
| 04-01 | MAN-04 | all 15 manifests load + compile (zero exemptions) | parametrized unit | `pytest tests/agents/test_manifest_coverage.py::test_all_load_compile -x` | ❌ W0 | ⬜ pending |
| 04-03 | MAN-04 | the 13 dispatchable pipelines (+ `od_prototype` alias) execute from `CompiledWorkflow`; no legacy dispatch fallback | parametrized integration | `pytest tests/agents/test_compiled_plan_runs.py -x` (reuse `_drive`) | ❌ W0 | ⬜ pending |
| 04-01 | MAN-04 | `reverse_engineer` → empty plan; `chat` compiles but engine does NOT dispatch | unit | `pytest tests/agents/test_edge_manifests.py -x` | ❌ W0 | ⬜ pending |
| 04-03 | MAN-04 | Phase-0A characterization snapshots stay green (prototype, od_prototype, prototype_revision, ppt/od_ppt, one code-gen) | characterization | `pytest tests/agents/test_characterization_*.py -x` | ✅ exist | ⬜ pending |
| 04-01 | MAN-04 | `clarify.defaults` per manifest == engine `_pipeline_defaults`; `planner` per manifest matches live behavior (note: `SKIP_PLANNER_FOR_PROTOTYPE = False` today → all 13 declare `planner: run`) | unit | `pytest tests/agents/test_manifest_parity.py -x` | ❌ W0 | ⬜ pending |
| 04-03 | MAN-05 | legacy `pipeline_type` resolves to correct manifest id and runs; `od_prototype`→`prototype` | unit | `pytest tests/agents/test_id_alias_resolver.py -x` | ❌ W0 | ⬜ pending |
| 04-03 | MAN-05 | grep/structure: `pipeline_type` consumed ONLY by id-alias resolver for routing; behavioral branches allow-listed | structure | `pytest tests/agents/test_pipeline_type_routing.py -x` | ❌ W0 | ⬜ pending |
| 04-04 | API-01 | `GET /api/workflows` lists every authored workflow with metadata | api | `pytest tests/unit/test_workflows_api.py::test_list -x` | ❌ W0 | ⬜ pending |
| 04-04 | API-01 | `GET /api/workflows/{id}` returns full compiled step configs; 404 on unknown id; `prototype` payload matches its manifest | api | `pytest tests/unit/test_workflows_api.py::test_get_and_404 -x` | ❌ W0 | ⬜ pending |
| 04-04 | D-01/D-02 | relocated `/api/runs/*` routes serve the old run-history shapes (regression of moved CRUD; preserve `user_id == current_user.id` IDOR filter) | api | `pytest tests/unit/test_runs_api.py -x` | ❌ W0 | ⬜ pending |
| all | CI gates | import-linter + migration-ledger + vulture stay green (L1–L13 NOT flipped) | gate | `cd backend && lint-imports && python3.11 -m pytest tests/agents/test_migration_ledger.py -x && vulture app/ agents/` | ✅ exist | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/test_manifest.py` — MAN-01 (load + named-field errors + DSL-key rejection)
- [ ] `tests/agents/test_compiler.py` — MAN-02/INV-1/INV-5 (compile-clean, reject-DSL, no-name-branch, structure)
- [ ] `tests/agents/test_registry_capabilities.py` — MAN-03 (ports exist, names registered)
- [ ] `tests/agents/test_manifest_coverage.py` + `test_compiled_plan_runs.py` + `test_edge_manifests.py` — MAN-04 (reuse `_drive`)
- [ ] `tests/agents/test_manifest_parity.py` — clarify-defaults + planner parity vs. engine dicts
- [ ] `tests/agents/test_id_alias_resolver.py` + `test_pipeline_type_routing.py` — MAN-05
- [ ] `tests/unit/test_workflows_api.py` + `tests/unit/test_runs_api.py` — API-01 + D-01/D-02
- [ ] Framework install: none — pytest already configured.

*Existing infra that already covers part of the phase:* `tests/agents/test_characterization_*.py` (5 snapshots), `tests/agents/test_migration_ledger.py`, the import-linter contract, vulture config.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

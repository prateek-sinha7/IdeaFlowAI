---
phase: 04-manifest-compiler-1a
verified: 2026-06-07T19:20:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
---

# Phase 4: Manifest + Compiler [1A] Verification Report

**Phase Goal:** Introduce hand-authored file-backed workflow manifests and a thin compiler (no DSL) that produces a typed `CompiledWorkflow`; run every existing pipeline from a compiled plan while artifacts still flow via the legacy `accumulated_outputs` mirror; no L1–L13 kernel branch deleted yet.
**Verified:** 2026-06-07T19:20:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (SPEC Acceptance Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | `WorkflowManifest` loads every authored `workflow.yaml`; malformed manifest raises `ManifestValidationError` naming the offending field | VERIFIED | `manifest.py` implements per-field validation naming every missing/invalid field; spot-checked live: missing `id` raises `"missing required field 'id'"`. 15 manifests all load. |
| 2 | `WorkflowCompiler.compile()` returns a typed `CompiledWorkflow` (Step DAG) for every authored manifest | VERIFIED | `compiler.py` confirmed; 16/16 tests in `test_compiled_plan_runs.py` pass (13 dispatchable + `od_prototype`); `test_manifest_coverage.py` 16/16 pass. |
| 3 | A manifest containing any control-flow construct is rejected (INV-5); a test asserts the compiler has no workflow-name/`pipeline_type` branch (INV-1) | VERIFIED | Strict-key rejection in `_ALLOWED_TOP_KEYS` frozenset verified; `if:` field rejected live. Compiler source grep: zero `pipeline_type`/workflow-name literal branches. `test_compiler.py` 11/11 pass including the DSL-rejection and structure tests. |
| 4 | The compiler rejects an unknown/unregistered capability reference with an error naming the bad reference (INV-4) | VERIFIED | Spot-checked: `strategy: nonexistent` raises `CompilerError("unknown strategy 'nonexistent' in step 'my-agent'")`. 7 `is_registered` call sites in `compiler.py` cover strategy, gate, validator, compaction, task_parser, context_provider, deliverable. |
| 5 | `agents/capabilities/base.py` ports + `agents/capabilities/registry.py` exist; known capability names are registered; compiler validates references against the registry | VERIFIED | Both files exist and are substantive. 26/26 tests in `test_registry_capabilities.py` pass. Exactly 14 `(kind, name)` pairs in `_KNOWN`; drift-guard test `test_registered_count_is_exactly_fourteen` passes. |
| 6 | Every `PIPELINE_AGENTS` pipeline_type (+ `od_*` aliases) has a manifest and runs from its compiled plan — asserted by a parametrized test; no legacy `pipeline_type` agent-dispatch fallback remains | VERIFIED | 15 `workflow.yaml` files confirmed (one per `PIPELINE_AGENTS` key; no `od_prototype` dir — alias only). `test_compiled_plan_runs.py` 16/16 pass (parametrized over 13 engine-dispatchable + `od_prototype`). `test_no_legacy_pipeline_type_dispatch_fallback` PASSES: `_pipeline_defaults` dict gone from executable code, `SKIP_PLANNER_FOR_PROTOTYPE and is_prototype_pipeline` gone, `compiled.planner == "skip"` + `compiled.clarify.defaults` are the routing sources. |
| 7 | Phase 0A characterization snapshots stay green (deliverable byte-identical + semantic event parity) | VERIFIED | 10/10 characterization snapshot tests pass: `test_characterization_prototype.py`, `test_characterization_od_prototype.py`, `test_characterization_prototype_revision.py`, `test_characterization_od_ppt.py`, `test_characterization_app_builder.py` — all 2 tests each. |
| 8 | `accumulated_outputs` mirror is unchanged (no schema change); no typed `ArtifactGraph` is introduced | VERIFIED | `grep "accumulated_outputs" engine.py` shows 8 unchanged usages. `plan.py` contains no `ArtifactGraph` class. Zero schema migrations in phase 4. |
| 9 | `pipeline_type` is consumed only by the id-alias resolver in the run path; no behavioral branch keys off it for the migrated set | VERIFIED | `test_behavioral_branches_match_allow_list_exactly` PASSES (8 allow-listed behavioral `pipeline_type` branches + 3 `spec.id` branches exactly match the Phase-7-scoped set; no new routing branches). `test_routing_consumption_is_the_id_alias_resolver_only` PASSES. |
| 10 | `GET /api/workflows` lists all authored workflows with metadata; `GET /api/workflows/{id}` returns full compiled step configs and 404s on an unknown id | VERIFIED | Live API spot-check: `GET /api/workflows` returns 15 entries; `GET /api/workflows/prototype` returns step configs matching the manifest (planner: run, clarify_defaults: [target_audience, scope, priority, style], 4 steps); `GET /api/workflows/nonexistent_workflow_id` returns 404. `test_workflows_api.py` 7/7 pass. |
| 11 | Import-linter + migration-ledger CI guards stay green (Phase 4 adds the declaration layer; L1–L13 deletions remain Phase 7) | VERIFIED | `lint-imports`: 1 contract KEPT, 0 broken. `test_migration_ledger.py`: 4 passed, 1 skipped. L1–L13 behavioral branches untouched (confirmed by structure test allow-list). |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/capabilities/__init__.py` | Package marker | VERIFIED | Exists |
| `backend/agents/capabilities/base.py` | 6 Protocol ports (ExecutionStrategy, Validator, DeliverableResolver, ContextProvider, GateHandler, TaskParser) | VERIFIED | All 6 @runtime_checkable Protocol ports defined; no kernel/api imports |
| `backend/agents/capabilities/registry.py` | CapabilityRegistry with 14 (kind, name) pairs + resolve_alias | VERIFIED | `_KNOWN` set has exactly 14 entries; `resolve_alias` lifts `_OD_ALIAS_BASE` from `agents.registry` (single source, no re-hardcoding) |
| `backend/agents/workflows/__init__.py` | Package marker | VERIFIED | Exists |
| `backend/agents/workflows/plan.py` | CompiledWorkflow/Step/Task §6 dataclasses | VERIFIED | All 3 dataclasses + 8 forward stub dataclasses (ToolPermissions, ModelPolicy, TaskSource, FixPolicy, FanoutSpec, RetryPolicy, RepoSpec, Limits, DeliverableSpec, ClarifySpec). No Pydantic. |
| `backend/agents/workflows/manifest.py` | WorkflowManifest + load_manifest + ManifestValidationError | VERIFIED | Per-field validation naming offending field; strict-key rejection; yaml.safe_load only |
| `backend/agents/workflows/compiler.py` | WorkflowCompiler.compile() — thin, no-DSL | VERIFIED | 7 is_registered call sites; no pipeline_type/workflow-name branch; topo-validates Step DAG |
| 15 x `backend/agents/workflows/<id>/workflow.yaml` | One per PIPELINE_AGENTS key | VERIFIED | Exactly 15 files, no od_prototype directory (alias only). All load + compile clean. |
| `backend/app/api/workflows.py` | Rewritten as manifest-definitions router | VERIFIED | GET /api/workflows + GET /api/workflows/{id}; closed allow-list path validation; no DB query |
| `backend/app/api/runs.py` | New run-history CRUD router | VERIFIED | All 5 run-history routes relocated; user_id ownership filter preserved on all 6 query paths |
| `backend/tests/agents/test_registry_capabilities.py` | Registry + ports tests | VERIFIED | 26 tests pass |
| `backend/tests/agents/test_manifest.py` | MAN-01 loader tests | VERIFIED | 15 tests pass |
| `backend/tests/agents/test_compiler.py` | MAN-02/03 compiler tests | VERIFIED | 11 tests pass |
| `backend/tests/agents/test_manifest_coverage.py` | All 15 manifests load+compile + step-order | VERIFIED | 16 tests pass |
| `backend/tests/agents/test_manifest_parity.py` | planner: run + clarify.defaults parity | VERIFIED | 26 tests pass |
| `backend/tests/agents/test_edge_manifests.py` | reverse_engineer empty plan + chat non-dispatchable | VERIFIED | 2 tests pass |
| `backend/tests/agents/test_id_alias_resolver.py` | id-alias resolver + compiled plan sourcing | VERIFIED | 60 tests pass |
| `backend/tests/agents/test_pipeline_type_routing.py` | MAN-05 structure test | VERIFIED | 3 tests pass (allow-list exactly matches; resolver-only routing; no legacy fallback) |
| `backend/tests/agents/test_compiled_plan_runs.py` | MAN-04 parametrized integration | VERIFIED | 16 tests pass (13 dispatchable + od_prototype) |
| `backend/tests/unit/test_workflows_api.py` | API-01 endpoint tests | VERIFIED | 7 tests pass |
| `backend/tests/unit/test_runs_api.py` | Relocated run-history CRUD tests | VERIFIED | 11 tests pass (IDOR + export sanitization preserved) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py:execute()` | `CompiledWorkflow` | `compile_for_run(pipeline_type)` at top of run | WIRED | Lines 778; 4 routing concerns confirmed sourced from `compiled.*` |
| `engine.py:compile_for_run` | `WorkflowManifest` | `load_manifest(manifest_id, _WORKFLOWS_DIR)` | WIRED | Lines 175-177 |
| `engine.py:compile_for_run` | `WorkflowCompiler.compile` | `_WORKFLOW_COMPILER.compile(manifest, _CAPABILITY_REGISTRY)` | WIRED | Line 177 |
| `compiler.py` | `CapabilityRegistry.is_registered` | 7 inline call sites per capability kind | WIRED | strategy, gate, validator, compaction, task_parser, context_provider, deliverable all checked |
| `registry.py:resolve_alias` | `agents.registry._OD_ALIAS_BASE` | import + `.get(pipeline_type, pipeline_type)` | WIRED | Single source; `grep '"od_prototype"' registry.py` returns 0 (not re-hardcoded) |
| `app/api/workflows.py` | compiled manifests | `compile_for_run(workflow_id)` | WIRED | Lines 187; closed allow-list `_KNOWN_WORKFLOW_IDS` guards path param |
| `app/main.py` | `runs_router` | `include_router(runs_router)` | WIRED | Line 149 |
| Frontend (4 files) | `/api/runs` | repointed from `/api/workflows` | WIRED | 10 refs confirmed; 0 old `/api/workflows` run-history refs remain |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `engine.py execute()` | `compiled.steps` → `ordered_agents` membership drift check | `compile_for_run` → manifest YAML → registry | Manifest files on disk → typed `CompiledWorkflow` | FLOWING |
| `engine.py execute()` | `compiled.clarify.defaults` | `compile_for_run` → `ClarifySpec.defaults` from YAML | Per-pipeline verbatim copy of engine's former `_pipeline_defaults` dict | FLOWING |
| `engine.py execute()` | `skip_planner = compiled.planner == "skip"` | `compile_for_run` → `CompiledWorkflow.planner` | Always `"run"` (SKIP_PLANNER_FOR_PROTOTYPE=False today) | FLOWING |
| `app/api/workflows.py` | `compiled.steps`, `compiled.deliverable` | `compile_for_run(workflow_id)` | Real compiled manifest data, no DB query | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ManifestValidationError names the offending field | `python3.11` inline test with missing `id` field | `"missing required field 'id'"` | PASS |
| Control-flow field rejected at manifest load | `python3.11` inline test with `if: some_condition` in manifest | `ManifestValidationError: unknown top-level key(s) ['if']` | PASS |
| Unknown capability names CompilerError | `python3.11` inline test with `strategy: nonexistent` | `CompilerError("unknown strategy 'nonexistent' in step 'my-agent'")` | PASS |
| GET /api/workflows returns 15 entries | TestClient live call | `200 OK`, 15 entries | PASS |
| GET /api/workflows/{id} returns 404 on unknown | TestClient live call | `404 Not Found` | PASS |
| prototype payload matches manifest | TestClient `/api/workflows/prototype` | planner=run, clarify_defaults=[target_audience,scope,priority,style], 4 steps, single_file deliverable | PASS |
| 13 dispatchable pipelines + od_prototype run from compiled plan | `test_compiled_plan_runs.py` (20s) | 16 passed | PASS |
| Phase 0A characterization snapshots | `pytest -k characterization` | 10/10 passed | PASS |

### Probe Execution

No probes declared in PLAN files. Characterization tests serve as the parity probe (all green, confirmed above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| MAN-01 | 04-02 | WorkflowManifest schema + YAML loader/validator; malformed → typed error naming field | SATISFIED | `manifest.py` + `test_manifest.py` 15/15 + live spot-check |
| MAN-02 | 04-03 | WorkflowCompiler → typed CompiledWorkflow; no DSL; no workflow-name branch (INV-1) | SATISFIED | `compiler.py` + `test_compiler.py` 11/11 + structure test |
| MAN-03 | 04-01 | CapabilityRegistry; unknown ref → compile error naming the ref (INV-4); base.py ports | SATISFIED | `registry.py` + `base.py` + `test_registry_capabilities.py` 26/26 |
| MAN-04 | 04-03, 04-04 | Every pipeline runs from compiled plan; no legacy dispatch fallback; accumulated_outputs unchanged | SATISFIED | `test_compiled_plan_runs.py` 16/16 + no-fallback structure test + characterization snapshots green |
| MAN-05 | 04-04 | pipeline_type reduced to id-alias resolver only; no behavioral branch keys off it for routing | SATISFIED | `test_pipeline_type_routing.py` 3/3 (allow-list exact match) |
| API-01 | 04-05 | GET /api/workflows + GET /api/workflows/{id}; 404 on unknown | SATISFIED | `test_workflows_api.py` 7/7 + live spot-check |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/api/workflows.py` | 126, 129 | `"agents TBD."` in docstring + return value | INFO | Not a debt marker — this is the runtime-returned description for the `reverse_engineer` empty-plan stub (D-05). The string is user-visible API data, not a TODO comment. Intentional per CONTEXT.md D-05 design decision. |

No `TBD`/`FIXME`/`XXX` debt markers in any code path. The `"TBD"` occurrence is exclusively in the `_describe()` helper's return value for `reverse_engineer`, which is the intentional description for that empty-plan stub — not a code incompleteness marker.

### Human Verification Required

None. All observable truths were verifiable programmatically via test execution and code inspection. The 10 characterization snapshot tests serve as the parity oracle. No visual/real-time/external service checks are required for this phase.

---

## Gaps Summary

No gaps. All 11 SPEC acceptance criteria are verified against the actual codebase. All test suites pass (884 passed, 19 skipped excluding 8 pre-existing unrelated failures documented in `deferred-items.md`). Import-linter green (1 contract kept, 0 broken). Migration-ledger ratchet green (L1–L13 all un-flipped). Phase 0A characterization snapshots green (10/10).

### Pre-existing Test Failures (Not Phase 4 Gaps)

Per `deferred-items.md` and the verification focus specification:
- `tests/unit/test_logout.py` (7 failures): auth/registration environment config (`ALLOW_SELF_REGISTRATION` disabled); unrelated to routing seam.
- `tests/unit/test_pipeline_cancel.py` (1 failure): async cancel timing flakiness using `_StubEngine`; real `ExecutionEngine.execute`/`compile_for_run` never invoked.

Both confirmed pre-existing on the phase-4 base commit `df5a4ef`.

---

_Verified: 2026-06-07T19:20:00Z_
_Verifier: Claude (gsd-verifier)_

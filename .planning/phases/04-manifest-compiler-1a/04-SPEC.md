# Phase 4: Manifest + Compiler [1A] — Specification

**Created:** 2026-06-07
**Ambiguity score:** 0.12 (gate: ≤ 0.20)
**Requirements:** 6 locked

## Goal

Introduce hand-authored file-backed workflow manifests and a thin, no-DSL `WorkflowCompiler` that produces a typed `CompiledWorkflow` (Step DAG), and route **every** current pipeline to execute from its compiled plan — while artifacts still flow through the legacy `accumulated_outputs` mirror and no L1–L13 kernel branch is deleted yet.

## Background

`backend/agents/execution_engine/engine.py` (139 KB) selects behavior by a string `pipeline_type`: hardwired branches (`if pipeline_type == "prototype_revision"`, `pipeline_type in _PROTOTYPE_PIPELINE_TYPES`, the `spec.id == "prototype-build"` build-loop dispatch, the `_resolve_final_output` deliverable-by-class chooser, the `_pipeline_defaults`/`ALWAYS_CLARIFY` clarify dict). Agent lists come from `PIPELINE_AGENTS` in `agents/registry.py` (~15 registered types — `prototype`, `prototype_revision`, `ppt`, `od_ppt`, `user_stories`, `app_builder`, `mulesoft_to_springboot`, `dotnet_to_azure`, `chat`, `reverse_engineer`, the `*_revision` variants, `custom`, plus the `od_prototype`→`prototype` and `*_revision`→base alias maps). No `manifest.py`, `compiler.py`, `plan.py`, or capability registry exists — Phase 4 is net-new code.

The authoritative master plan `specs/003-workflow-engine-decoupling/plan.md` locks this phase as **1A — Manifest + compiler (legacy artifact mirror)** (§25). The §31 migration ledger is decisive: **Phase 1A deletes no legacy branch** — every L1–L13 deletion is tagged Phase 2 (roadmap Phase 7); the only 1A ledger item is L15 (`accumulated_outputs` mirror), retained now and deleted in Phase 5/1B. So Phase 4 *introduces the declaration layer and routes execution through it*; the rich behavioral strategies stay in the kernel until Phase 7. Target homes are fixed by §32: `agents/workflows/` (manifest/compiler/plan + `<id>/workflow.yaml`) and `agents/capabilities/` (`base.py` ports + `registry.py`).

## Requirements

1. **WorkflowManifest schema + loader/validator**: A typed manifest model reads hand-authored file-backed YAML, one per workflow. (MAN-01)
   - Current: No manifest type exists; a workflow's definition is implicit in `PIPELINE_AGENTS` + hardwired `engine.py` branches.
   - Target: `agents/workflows/manifest.py` defines `WorkflowManifest` + a loader for `agents/workflows/<id>/workflow.yaml`; required fields (`id`, `steps`, `deliverable`, `planner`, `clarify`) validated; malformed/missing field raises a typed `ManifestValidationError` naming the offending field.
   - Acceptance: Loading a well-formed `workflow.yaml` returns a populated `WorkflowManifest`; a manifest with a missing required field raises `ManifestValidationError` naming that field; every authored manifest loads clean.

2. **WorkflowCompiler → typed CompiledWorkflow, thin & no-DSL**: The compiler validates + resolves names into a typed Step DAG and nothing more. (MAN-02 / INV-5 / INV-1)
   - Current: No compiler; no typed plan; control flow lives in Python `if pipeline_type` / `if spec.id` branches.
   - Target: `agents/workflows/compiler.py` `WorkflowCompiler.compile(manifest) -> CompiledWorkflow`; `agents/workflows/plan.py` defines `CompiledWorkflow` / `Step` / `Task` dataclasses (per plan §6). Manifests carry **data only** — no conditionals, loops, or expressions; the compiler resolves declared names to capabilities and topo-validates the DAG.
   - Acceptance: Each authored manifest compiles to a `CompiledWorkflow` whose steps/agents/deliverable/clarify/planner match the manifest; a manifest containing any control-flow construct is rejected; a structure test asserts the compiler contains no workflow-name/`pipeline_type` branch (INV-1).

3. **Capability-reference validation against the registry; reject unknown**: Every declared capability name is checked against a `CapabilityRegistry`. (MAN-03 / INV-4)
   - Current: No registry; capability names are not validated — behavior is hardcoded, not referenced.
   - Target: `agents/capabilities/base.py` (Protocol ports: Strategy, Validator, DeliverableResolver, ContextProvider, GateHandler, TaskParser, …) + `agents/capabilities/registry.py` (`CapabilityRegistry` keyed by `(kind, name)`); the known capability **names** are registered (seam real); the compiler validates every reference (strategy, validators, deliverable resolver, context_providers, task parser, gates) against the registry; an unknown/unregistered name → compile error. Trust flags / `user_allowed` / owner allow-list are **not** built here (Phase 8); concrete capability **impls** are **not** built here (Phase 7).
   - Acceptance: A manifest referencing an unregistered capability (e.g. `strategy: nonexistent`) fails compilation with an error naming the bad reference; all authored manifests reference only registered names and compile clean; `registry.py` + `base.py` exist with ports defined.

4. **Every current pipeline runs from a compiled plan; legacy mirror retained**: All registered pipelines route through the compiled plan with no legacy dispatch fallback. (MAN-04)
   - Current: The engine sources agents from `PIPELINE_AGENTS` and behavior from `pipeline_type` branches; `accumulated_outputs` is the untyped artifact handoff.
   - Target: A hand-authored `workflow.yaml` exists for **every** pipeline currently dispatchable (all `PIPELINE_AGENTS` base + revision + `custom` types, plus the `od_*` and `*_revision` aliases); the engine sources step sequence, agent IDs, deliverable, clarify, and planner-skip **from the `CompiledWorkflow`** rather than the hardcoded dicts; **no run reaches a legacy `pipeline_type` agent-dispatch fallback**. The `accumulated_outputs` mirror is unchanged (no schema change). L1–L13 behavioral branches remain in the kernel (deleted in Phase 7).
   - Acceptance: For every `pipeline_type` in `PIPELINE_AGENTS` (+ `od_*` aliases), a run compiles and executes from its `CompiledWorkflow`; a parametrized test asserts **no** registered pipeline_type lacks a manifest; the Phase 0A characterization snapshots stay green.

5. **`pipeline_type` retained only as a temporary migration alias**: It resolves a manifest id; it no longer selects behavior. (MAN-05 / Q1)
   - Current: `pipeline_type` is the primary behavioral dispatch key.
   - Target: `pipeline_type` is reduced to an **id alias** (the `od_*`→base and `*_revision`→base maps become manifest-id resolution); no behavioral code keys off it for the migrated set. Marked temporary (removed when manifests become the sole entry surface, a later phase).
   - Acceptance: Passing a legacy `pipeline_type` resolves to the correct manifest id and runs; a grep/test confirms `pipeline_type` is consumed **only** by the id-alias resolver in the run path — no behavioral branch keys off it.

6. **`GET /api/workflows` + `GET /api/workflows/{id}` return manifest-derived metadata**: The composer reads workflows dynamically, not from hardcoded types. (API-01)
   - Current: No workflow-metadata endpoint; the composer relies on hardcoded workflow types.
   - Target: `app/api/workflows.py` exposes `GET /api/workflows` (list: id, name, description, step summary) and `GET /api/workflows/{id}` (full step configs, gates, validators, deliverable, declared capabilities) — all derived from the compiled manifests.
   - Acceptance: `GET /api/workflows` lists every authored workflow with metadata; `GET /api/workflows/{id}` returns the compiled step configs for a known id and returns 404 for an unknown id; the `prototype` payload matches its manifest (agents, gates, deliverable).

## Boundaries

**In scope:**
- `agents/workflows/manifest.py` — `WorkflowManifest` schema + YAML loader/validator
- `agents/workflows/compiler.py` — `WorkflowCompiler` (thin, no-DSL, name resolution + DAG validation)
- `agents/workflows/plan.py` — `CompiledWorkflow` / `Step` / `Task` typed dataclasses
- `agents/capabilities/base.py` — capability Protocol ports
- `agents/capabilities/registry.py` — `CapabilityRegistry` with known capability **names** registered (INV-4 validation only)
- `agents/workflows/<id>/workflow.yaml` — a hand-authored manifest for **every** current pipeline (+ `od_*`/`*_revision` aliases)
- Engine routed to execute from the `CompiledWorkflow` (steps/agents/deliverable/clarify/planner sourced from the plan); no legacy `pipeline_type` dispatch fallback
- `accumulated_outputs` legacy mirror retained **unchanged**
- `pipeline_type` reduced to an id-alias (MAN-05)
- `GET /api/workflows` + `GET /api/workflows/{id}` (API-01)
- Phase 0A characterization snapshots stay green; import-linter + migration-ledger CI guards stay green

**Out of scope:**
- Extracting L1–L13 behavioral branches into registered strategy/validator/resolver/provider capabilities and deleting them — **Phase 7 (plan-2)**; per §31, all L1–L13 deletions are tagged Phase 2, not 1A. Phase 4 introduces only the declaration layer.
- Concrete capability implementations (`single_shot`/`task_loop` strategies, `html_static`/`html_render` validators, `single_file` resolver, `opendesign` provider, `heading_tasks` parser, `html_skeleton` compaction) — **Phase 7**; Phase 4 registers names only.
- Typed `ArtifactGraph`/`ArtifactRef`, persistence schema, and deleting the `accumulated_outputs` mirror — **Phase 5 (plan-1B)** (ledger L15).
- `CapabilityRegistry` trust flags / `user_allowed` / owner allow-list enforcement, the gate registry, tool-permission enforcement — **Phase 8 (plan-3)**.
- Model policy / `ModelResolver` — **Phase 6 (plan-1C)**.
- `GET /api/capabilities`, new run-stream events (`subagent_*`, `wave_*`, `validator_result`, …) — **Phase 8+**.
- Fan-out, wave scheduler, `Workspace`/`RuntimeEnvironment` runtime, `exec`, repo workflows — **Phases 9–12**.
- DB-backed user-authored workflows — file-backed hand-authored manifests only (Q5).
- Any DSL / control flow inside manifests — **permanently out** (INV-5).

## Constraints

- **Thin compiler, no DSL (INV-5):** manifests are pure data; all logic stays in (later) strategies. The compiler only validates + resolves names.
- **Kernel knows no workflow by name (INV-1):** resolution is by declared capability name via the registry, never a workflow-name branch.
- **No dual implementation beyond the sanctioned mirror (INV-3/INV-12):** Phase 4 adds the declaration layer without a second execution path — every pipeline routes through the compiled plan; the only permitted temporary duplication is `accumulated_outputs` (L15).
- **Backward-compat (INV-3):** deliverable byte-identical where deterministic + semantic event parity; the Phase 0A characterization snapshots are the regression gate.
- **Additive only (Q3):** no DB migration in Phase 4 — no schema change; the mirror is untouched.
- **Runtime mandate (INV-13):** no agent-loop changes; `deepagents` runtime untouched.
- **Hand-authored manifests (§28):** any generated manifest index is optional and never authoritative.
- **Layout (§32):** Ports & Adapters — `agents/workflows/` (data) and `agents/capabilities/` (ports + registry); kernel imports ports only (import-linter).

## Acceptance Criteria

- [ ] `WorkflowManifest` loads every authored `workflow.yaml`; a malformed manifest raises a typed validation error naming the offending field
- [ ] `WorkflowCompiler.compile()` returns a typed `CompiledWorkflow` (Step DAG) for every authored manifest
- [ ] A manifest containing any control-flow construct is rejected (INV-5); a test asserts the compiler has no workflow-name/`pipeline_type` branch (INV-1)
- [ ] The compiler rejects an unknown/unregistered capability reference with an error naming the bad reference (INV-4)
- [ ] `agents/capabilities/base.py` ports + `agents/capabilities/registry.py` exist; known capability names are registered; the compiler validates references against the registry
- [ ] Every `PIPELINE_AGENTS` pipeline_type (+ `od_*` aliases) has a manifest and runs from its compiled plan — asserted by a parametrized test (no type lacks a manifest); no legacy `pipeline_type` agent-dispatch fallback remains
- [ ] Phase 0A characterization snapshots stay green (deliverable byte-identical where deterministic + semantic event parity) for prototype, od_prototype, prototype_revision, ppt/od_ppt, and one code-gen pipeline
- [ ] `accumulated_outputs` mirror is unchanged (no schema change); no typed `ArtifactGraph` is introduced
- [ ] `pipeline_type` is consumed only by the id-alias resolver in the run path (grep/test); no behavioral branch keys off it for the migrated set
- [ ] `GET /api/workflows` lists all authored workflows with metadata; `GET /api/workflows/{id}` returns full compiled step configs and 404s on an unknown id
- [ ] Import-linter + migration-ledger CI guards stay green (Phase 4 adds the declaration layer; L1–L13 deletions remain Phase 7)

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                        |
|--------------------|-------|------|--------|--------------------------------------------------------------|
| Goal Clarity       | 0.92  | 0.75 | ✓      | Locked by plan §25 (1A) + MAN-01..05 / API-01                |
| Boundary Clarity   | 0.90  | 0.70 | ✓      | All-pipelines coverage + registry-seam locked; L1–L13 → P7   |
| Constraint Clarity | 0.85  | 0.65 | ✓      | INV-1/3/4/5/12/13; additive (no migration); §32 layout       |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | ROADMAP SC + §24 characterization snapshots                  |
| **Ambiguity**      | 0.12  | ≤0.20| ✓      | Gate passed; authoritative plan + two scoping confirmations  |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective              | Question summary                                  | Decision locked                                                                 |
|-------|--------------------------|---------------------------------------------------|---------------------------------------------------------------------------------|
| 0     | Researcher (scout)       | What exists today for this phase?                 | engine.py dispatches by `pipeline_type`; ~15 `PIPELINE_AGENTS` types; no manifest/compiler/registry |
| 0     | Plan ingestion           | Does plan.md already lock 1A?                      | Yes — §25/§6/§10/§28/§31/§32 fix goal, boundary, constraints, acceptance         |
| 1     | Boundary Keeper          | Which pipelines get manifests in Phase 4?         | **All** registered pipelines; no legacy `pipeline_type` dispatch fallback (INV-12) |
| 1     | Boundary Keeper          | How much CapabilityRegistry in Phase 4?           | Ports + registry seam now (names registered for INV-4); impls → P7, trust → P8   |
| 1     | Boundary Keeper          | Gate / proceed?                                   | Ambiguity 0.12 — write SPEC.md                                                   |

---

*Phase: 04-manifest-compiler-1a*
*Spec created: 2026-06-07*
*Next step: /gsd-discuss-phase 4 — implementation decisions (how to build what's specified above)*

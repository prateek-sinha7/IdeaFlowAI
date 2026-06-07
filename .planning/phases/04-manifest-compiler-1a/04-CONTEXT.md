# Phase 4: Manifest + Compiler [1A] - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Introduce the **declaration layer**: hand-authored file-backed `WorkflowManifest` (YAML, one per workflow) → a thin, no-DSL `WorkflowCompiler` → a typed `CompiledWorkflow` (Step DAG), plus a minimal `CapabilityRegistry` (names only) the compiler validates references against. Route **every** current pipeline to execute **from its compiled plan** (sequence, agent IDs, deliverable, clarify, planner-skip sourced from the `CompiledWorkflow`, not the hardcoded dicts), while artifacts still flow through the legacy `accumulated_outputs` mirror and **no L1–L13 kernel branch is deleted** (those are Phase 7). Add `GET /api/workflows` + `GET /api/workflows/{id}` returning manifest-derived metadata.

**This phase is the declaration + routing seam only.** No concrete capability impls (Phase 7), no typed `ArtifactGraph`/persistence (Phase 5/1B), no model policy (Phase 6/1C), no trust flags / self-registration discovery (Phase 8/3). Net-new code under `agents/workflows/` + `agents/capabilities/`; the kernel knows no workflow by name (INV-1) and resolves by declared capability name (INV-4).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**6 requirements are locked.** See `04-SPEC.md` for full requirements (MAN-01..05 + API-01), boundaries, and acceptance criteria.

Downstream agents MUST read `04-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
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

**Out of scope (from SPEC.md):**
- Extracting L1–L13 behavioral branches into capabilities and deleting them — **Phase 7 (plan-2)**
- Concrete capability impls (`single_shot`/`task_loop`, `html_static`/`html_render`, `single_file`, `opendesign`, `heading_tasks`, `html_skeleton`) — **Phase 7**; Phase 4 registers names only
- Typed `ArtifactGraph`/`ArtifactRef`, persistence schema, deleting the `accumulated_outputs` mirror — **Phase 5 (plan-1B)** (ledger L15)
- `CapabilityRegistry` trust flags / `user_allowed` / owner allow-list, gate registry, tool-permission enforcement — **Phase 8 (plan-3)**
- Model policy / `ModelResolver` — **Phase 6 (plan-1C)**
- `GET /api/capabilities`, new run-stream events — **Phase 8+**
- Fan-out, wave scheduler, `Workspace`/`RuntimeEnvironment` runtime, `exec`, repo workflows — **Phases 9–12**
- DB-backed user-authored workflows — file-backed hand-authored manifests only (Q5)
- Any DSL / control flow inside manifests — **permanently out** (INV-5)

</spec_lock>

<decisions>
## Implementation Decisions

> The SPEC locked the 6 requirements (WHAT). These are the HOW forks resolved in discussion. Two areas were discussed (A, D); the rest are locked to plan-grounded / codebase-derived recommendations. Where the user chose against the recommendation it is marked **[user override]** with the rationale.

### API surface — `/api/workflows` namespace (Area A, discussed)

- **D-01 [user override]: Reclaim `/api/workflows` for manifest definitions; relocate run-history to `/api/runs`.** `GET /api/workflows` + `GET /api/workflows/{id}` currently serve **run-history** (`list[WorkflowRunResponse]` / one `WorkflowRun`) — a collision the SPEC did not flag. Decision: honor SPEC Req 6's literal paths — `/api/workflows` (list) + `/api/workflows/{id}` (one) now return **manifest-derived** metadata; the existing run-history moves out to a new `/api/runs` router.
  - *Rationale:* plan-aligned — §22 already places run-scoped sub-resources under `/api/runs/{id}/*` (API-04 artifacts, API-05 events, in Phase 5). The run-history was squatting on `/api/workflows`; moving it makes room exactly as the plan envisions. Recommendation had been the lower-risk catalog sub-path; user chose the SPEC-literal reclaim (consistent with the standing "honor the plan literally / nothing dropped" directive).

- **D-02: Full move + frontend repoint, clean break (no aliases).** Create **`backend/app/api/runs.py`** (`APIRouter(prefix="/api/runs")`) housing **all** run-history routes that move out of `workflows.py`:
  - `GET /api/runs` (was `GET /api/workflows`, keeps `?type=&limit=` query params)
  - `GET /api/runs/{id}` (was `GET /api/workflows/{id}`)
  - `GET /api/runs/{id}/chain-context`
  - `DELETE /api/runs/{id}`
  - `POST /api/runs/export-pptx`
  - `backend/app/api/workflows.py` is rewritten as the **manifest-definitions** router (`GET /api/workflows` → list: id, name, description, step summary; `GET /api/workflows/{id}` → full step configs, gates, validators, deliverable, declared capabilities; **404 on unknown id**) — all derived from the compiled manifests.
  - Register the new router in `backend/app/main.py` (`include_router(runs_router)` alongside the now-definitions `workflows_router`).
  - Repoint the **10 frontend refs**: `frontend/src/lib/api.ts` (list / get / chain-context / delete), `frontend/src/components/results/FilesTab.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/preview/PPTPreview.tsx` (each calls `GET /api/workflows?type=ppt&limit=N` + `POST /api/workflows/export-pptx`).
  - **No legacy aliases.** The app moves atomically (backend + frontend in this phase). The two colliding GETs cannot be aliased anyway (a path returns one shape).
  - **Researcher directive:** confirm whether the old run-history paths are part of the **API-key public surface** (`backend/app/api/api_key_auth.py`); if an external consumer exists, escalate D-02 to add deprecated 308-redirect aliases for the non-colliding routes (`export-pptx`, `chain-context`, `DELETE`). Phase-0A characterization snapshots are about engine/deliverables, **not** these REST routes, so they stay green regardless.

### Manifest coverage & aliases (Area D, discussed)

- **D-03: 15 manifests — one per `PIPELINE_AGENTS` key.** Every registered key gets `agents/workflows/<id>/workflow.yaml`: `user_stories`, `user_stories_revision`, `ppt`, `ppt_revision`, `od_ppt`, `od_ppt_revision`, `prototype`, `prototype_revision`, `app_builder`, `app_builder_revision`, `mulesoft_to_springboot`, `dotnet_to_azure`, `custom`, `reverse_engineer`, `chat`. **Revisions get their own manifest** (distinct agents — e.g. `prototype_revision` = `[prototype-revision-agent]`, unlike `prototype`'s four — so they cannot alias to a base).

- **D-04: `od_prototype` is the sole id-alias → `prototype`** (no own manifest). It is the only `_OD_ALIAS_BASE` entry (not a real `PIPELINE_AGENTS` key). `pipeline_type` is reduced to an **id-alias resolver** at the run entry: `od_prototype` → `prototype` manifest id; every real key resolves to itself (MAN-05). `od_ppt` / `od_ppt_revision` are **real keys** → own manifests (their OpenDesign flavor is declared via `context_providers: [opendesign]` in the manifest, but the actual injection stays in the surviving L12 branch until Phase 7).

- **D-05 [user override]: Placeholder manifests for both edge cases (zero coverage-test exemptions).** Recommendation had been to exclude them; user chose full coverage:
  - **`reverse_engineer`** (`PIPELINE_AGENTS["reverse_engineer"] == []`): MAN-01 schema **permits `steps: []`** (a valid empty workflow). Author it as an explicit stub — `steps: []`, `description: "agents TBD"` — that compiles to an **empty plan**.
  - **`chat`** (internal — driven by `app/agents/chat_runner.py` `ChatRunner`, **not** the `ExecutionEngine`; excluded from `allowed_custom_agent_ids`): author a manifest declaring its 7 agents (`chat-discovery`…`chat-preview`). It **loads + compiles** (feeds the coverage test + the `/api/workflows` catalog + pre-stages the Phase-7b ChatRunner→runtime migration) but the **engine does NOT dispatch it**.
  - **No new schema fields** for runnability — the registry already encodes the facts (chat internal; reverse_engineer empty).
  - **Coverage test shape:** (1) **all 15** manifests load + compile (zero exemptions); (2) the **13 engine-dispatchable** pipelines (15 − `chat` − `reverse_engineer`) execute from their `CompiledWorkflow` with **no legacy `pipeline_type` dispatch fallback** (+ the `od_prototype` alias path runs `prototype`'s plan). `reverse_engineer` compiles to an empty plan; `chat` compiles but stays on ChatRunner.

### Type contracts in `plan.py` (Area B, locked to recommendation)

- **D-06: Define the full §6 typed contract now; populate only Phase-4 fields.** `plan.py` defines `CompiledWorkflow` / `Step` / `Task` with the **full §6 field set** (incl. forward fields `model`, `tools`, `validators`, `fix`, `compaction`, `fanout`, `on_conflict`, `retry`, `injects`, `repo`, `limits`, …). Forward fields are **declared-but-inert** (default values, not consumed) until their owning phase wires behavior. Phase 4 only **routes/populates** the fields it uses: step `agent_id` + `strategy` (name), `gates` (names), `task_source`, plus workflow-level `steps`, `context_providers` (names), `seed_files`, `deliverable` (spec), `planner`, `clarify`.
  - *Rationale:* avoids dataclass churn across the 8 remaining phases (§6 is "the contracts"; final names land here per "final names TBD in Phase 1"). Nested forward types referenced by inert fields may be defined as minimal stub dataclasses now or deferred — **planner's call**; the constraint is no Phase-4 behavior keys off an inert field.

### Capability registry seam (Area C, locked to recommendation)

- **D-07: Minimal central name-registry now; defer self-registration + trust to Phase 8.** `agents/capabilities/registry.py` = a `CapabilityRegistry` keyed by `(kind, name)` with the **known capability names registered** (no impls, no behavior — the seam is real for INV-4 validation). `agents/capabilities/base.py` = the Protocol **ports** (`ExecutionStrategy`, `Validator`, `DeliverableResolver`, `ContextProvider`, `GateHandler`, `TaskParser`, … per §6). The compiler validates **every** declared reference (strategy, validators, deliverable resolver, context_providers, task parser, gates) against the registry — unknown name → compile error naming the bad reference.
  - **Deferred to Phase 8 (CAP-02/CAP-03):** the `@register(kind, name)` decorator + startup `discover()` machinery, `user_allowed` trust flags, owner allow-list. Registering names centrally now and converting to self-registration in Phase 8 is an **evolution, not a dual implementation** (INV-12 respected).
  - **Known names to register (from §10 + §32, names only):** strategies `single_shot`, `task_loop`; validators `html_static`, `html_render`; deliverable resolvers `single_file`, `serialized_sandbox`, `streamed_text` (+ `ppt`); context_providers `opendesign`, `previous_run`; task_parsers `heading_tasks`; gates `human`, `validation`; compaction `html_skeleton`. **Researcher confirms the exact set** the 15 manifests must reference so all compile clean.

### No-DSL enforcement (INV-5, locked)

- **D-08: Strict-schema rejection + a guard test.** Manifests are **pure data**. The loader/schema **rejects unknown/extra keys** (so a conditional/loop/expression field simply has nowhere to live), and a dedicated test asserts a manifest containing any control-flow construct (e.g. `when:`, `if:`, `for:`, a `${...}`/`{{...}}` expression value) is **rejected**. A structure test asserts the compiler contains **no** workflow-name / `pipeline_type` branch (INV-1).

### Engine routing seam (MAN-04 / MAN-05, locked)

- **D-09: Source structure from the plan; allow-list surviving behavioral branches as Phase-7-scoped.** The engine sources **step sequence, agent IDs, deliverable spec, clarify, planner-skip** from the `CompiledWorkflow` (replacing `get_pipeline_agents(pipeline_type)` + the hardcoded `_pipeline_defaults`/`ALWAYS_CLARIFY`/`SKIP_PLANNER_FOR_PROTOTYPE` dicts as the **source of these values**). `pipeline_type` is resolved to a manifest id at the run entry and is **consumed only by that id-alias resolver** for the migrated routing concerns.
  - The **surviving L1–L13 behavioral branches that still read `pipeline_type`/`spec.id`** (e.g. L1 `_PROTOTYPE_PIPELINE_TYPES`/`_PPT_PIPELINE_TYPES` frozensets, L7 `spec.id == "prototype-build"`, L10 HTML-readback `pipeline_type in (...)`, L12 `_build_context_message` od/ppt/build injection) **remain** (deleted in Phase 7) and are **explicitly allow-listed** in the MAN-05 grep/structure test as Phase-7-scoped — they are *behavioral*, not *routing*. `accumulated_outputs` mirror unchanged (L15).
  - **Researcher directive (critical):** inventory **all 44** `pipeline_type`/`spec.id ==` occurrences in `engine.py` and classify each as **routing** (→ now sourced from the `CompiledWorkflow`) vs **behavioral** (→ survives + allow-listed for Phase 7). This classification is the backbone of the plan and the MAN-04/MAN-05 acceptance.

### Manifest schema & validation mechanism (plan/loader-derived, locked)

- **D-10: Dataclass + `python-frontmatter`/`yaml` + manual validation raising `ManifestValidationError`.** Mirror the established `agents/loader.py` pattern (`AgentSpec` dataclass + `AgentSpecError` raised on each missing/invalid field) rather than Pydantic — §6/§32 both say `@dataclass`/`Protocol` at every boundary, and the codebase's typed-config-loader precedent is dataclass + explicit validation. `ManifestValidationError` must **name the offending field** (SPEC Req 1 / MAN-01). `yaml` is already importable (used by `app/services/od_loader.py`; `python-frontmatter` ships PyYAML).

### Claude's Discretion
- Exact route handler signatures, response models, and auth dependencies for the new `/api/runs` + `/api/workflows` definitions routers (mirror the existing `workflows.py` patterns — `Depends(...)` auth, `response_model=`).
- Whether nested forward-field types (D-06) are stub-defined now or deferred — provided no Phase-4 behavior keys off an inert field.
- Plan-task granularity / split (e.g. manifest+compiler+plan; capabilities base+registry; the 15 manifests; engine routing; API reclaim+frontend) — planner's call.
- Exact `description`/metadata wording in the stub `reverse_engineer` manifest and the `chat` manifest.
- The precise name of the new run-history router file (`runs.py` recommended) and whether `export-pptx` lands at `/api/runs/export-pptx` or a nested path.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/04-manifest-compiler-1a/04-SPEC.md` — the 6 locked requirements (MAN-01..05 + API-01), boundaries, acceptance criteria. **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`)
- **§6 (lines 324–516)** — Core abstractions / contracts: `ExecutionContext`, `Step`, `CompiledWorkflow`, `Task`, the capability ports (`ExecutionStrategy`/`Validator`/`DeliverableResolver`/`ContextProvider`/`GateHandler`/`TaskParser`). "Final names TBD in Phase 1" = **this phase** (D-06).
- **§7 (lines 524–533)** — Capability registry & trust model: registry keyed by `(kind, name)`; engineers register, manifests reference; trust flags are Phase 8 (D-07).
- **§10 (lines 572–607)** — Prototype re-expressed as a manifest (the YAML shape to author); `od_prototype` = alias; `prototype_revision` = variant.
- **§11 (lines 609–628)** — Leak → new-home mapping (L1–L16); confirms L1–L13 stay until Phase 2/7, only L15 mirror touches 1A→1B.
- **§22 (lines 755–772)** — API/frontend contract: `/api/workflows`, `/api/workflows/{id}`, and the `/api/runs/{id}/*` run-scoped endpoints (validates D-01's reclaim).
- **§25 (lines 811–814)** — Phase 1A definition: manifest + compiler, legacy artifact mirror, every pipeline runs from a compiled plan, snapshots green.
- **§28 (lines 887–902)** — File-by-file change map (new `agents/workflows/`, `agents/capabilities/`; `app/api/workflows.py`).
- **§30 (lines 921–988)** — Capability kinds grounded in code (which names exist where today).
- **§31 (lines 989–1025)** — Migration & deletion ledger: only **L15** is 1A→1B; all L1–L13 are Phase 2 (roadmap Phase 7). Ledger ratchet must stay green (do NOT flip L1–L13).
- **§32 (lines 1027–1098)** — Target directory structure + engineering patterns (Ports & Adapters; the exact `agents/workflows/` + `agents/capabilities/` layout; one-name-everywhere; thin compiler).
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — operational mirror of §31; CI-asserted. L1–L13 grep patterns stay un-enforced this phase.

### Project planning
- `.planning/REQUIREMENTS.md` — MAN-01..05 (lines 38–42) + API-01 (line 161) with plan anchors; the full phase→requirement traceability.
- `.planning/ROADMAP.md` — § Phase 4 (goal, success criteria, candidate plan breakdown).
- `.planning/PROJECT.md` — invariants/constraints (INV-1 no name branches, INV-3 back-compat, INV-4 capability validation, INV-5 thin compiler, INV-12 no dual impl, INV-13 deepagents); the §4 leak map; "nothing from plan.md dropped".
- `.planning/phases/03-token-trim-measured-change-0c/03-CONTEXT.md` — prior-phase decisions that constrain this phase (ectx threading, snapshot model, commit scopes, `od_prototype` = alias → `prototype`).

### Code to read (targets / assets)
- `backend/agents/execution_engine/engine.py` (2710 lines) — `execute()` (`:410`) entry; `_run_agent` (`:1130`); **44** `pipeline_type`/`spec.id ==` occurrences to inventory + classify (D-09). The engine sources its agent list from `get_pipeline_agents(pipeline_type)`.
- `backend/agents/registry.py` — `PIPELINE_AGENTS` (`:29–180`, the 15 keys); `_OD_ALIAS_BASE` `{od_prototype: prototype}` (`:262`); `REVISION_BASE_MAP` (`:210–215`); `get_pipeline_agents()` (`:223`); `allowed_custom_agent_ids()` (`:331`, encodes the chat exclusion + od/revision resolution).
- `backend/agents/loader.py` — the **pattern to mirror** for D-10: `AgentSpec` dataclass (`:64`), `AgentSpecError` (`:105`), `load_agent_spec` (`:121`) with `python-frontmatter` + per-field validation raising the typed error.
- `backend/agents/factory.py` — `create_runner` / `_compose_system_prompt` / `_build_runner_tools`; where `injects` (od) + L12 context injection originate (unchanged this phase; Phase 3/F-series).
- `backend/app/api/workflows.py` (488 lines) — the existing run-history router being **split**: `GET /api/workflows` (`:80`), `POST /export-pptx` (`:111`), `GET /{id}` (`:230`), `delete` (`:255`), `GET /{id}/chain-context` (`:461`). `WorkflowRunResponse` / `ChainContextResponse` models live here.
- `backend/app/main.py` — router mounting (`:144–152`; `workflows_router` at `:147`) — add `runs_router`.
- `backend/app/api/api_key_auth.py` — check for external consumers of the moved run paths (D-02 researcher directive).
- `backend/app/agents/chat_runner.py` — `ChatRunner` (drives `chat`, not the engine; D-05).
- `frontend/src/lib/api.ts` (`:306`, `:324`, `:348`, `:358`) + `frontend/src/components/results/FilesTab.tsx` (`:328`, `:341`) + `frontend/src/components/preview/PreviewPanel.tsx` (`:380`, `:388`) + `frontend/src/components/preview/PPTPreview.tsx` (`:60`, `:74`) — the 10 refs to repoint (D-02).
- `backend/tests/agents/characterization/` + `tests/agents/test_characterization_*.py` — Phase-0A deliverable + semantic-event snapshots that MUST stay green.
- `backend/tests/test_migration_ledger.py` + the import-linter contract — CI gates that MUST stay green (do not flip L1–L13).
- `backend/pyproject.toml` — vulture allow-list + import-linter config (new `agents/workflows` + `agents/capabilities` packages must satisfy the kernel→ports contract).
- `backend/CLAUDE.md` — backend architecture guide (engine = deterministic sequencer; Adding-a-Pipeline; commit scopes `engine`/`registry`/`tests`/`factory`; dev runtime `python3.11`, no venv).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`agents/loader.py`** — the canonical typed-config-loader pattern (dataclass + `python-frontmatter` + per-field validation raising a typed error). `WorkflowManifest` + `ManifestValidationError` mirror it (D-10).
- **`agents/registry.py`** — `PIPELINE_AGENTS` + `_OD_ALIAS_BASE` + `REVISION_BASE_MAP` are the source of truth the manifests + id-alias resolver are derived from (D-03/D-04). `get_pipeline_agents()` is what the engine currently calls — the seam D-09 replaces.
- **`app/api/workflows.py`** — existing FastAPI router patterns (`APIRouter(prefix=…)`, `response_model=`, `Depends` auth, `HTTPException(404)`) to reuse for both the new `/api/runs` router and the rewritten `/api/workflows` definitions router.
- **`yaml`** already a transitive dep (`app/services/od_loader.py` imports it) — no new dependency for manifest parsing.

### Established Patterns
- **The engine is a deterministic sequencer** — it reads the ordered agent list + behavior; the LLM never decides order. Phase 4 keeps that; only the *source* of the structure changes (dicts → `CompiledWorkflow`).
- **`od_*` = OpenDesign-flavored alias** — single code path (`od_prototype` → `prototype`); the flavor today comes from L12 context injection (survives until Phase 7).
- **Snapshot model** — deliverable byte snapshot (deterministic) + semantic event snapshot (order-canonical multiset, volatile fields normalized). Phase 4 must keep BOTH green for prototype/od_/revision/ppt/code-gen (no behavior change).
- **Ports & Adapters / import-linter** — kernel imports only `capabilities.base` ports; new `agents/workflows` + `agents/capabilities` packages must respect the dependency direction (§32 / SAFE-05).
- Dev runtime: `python3.11`, no venv; `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v`; commit scopes per `backend/CLAUDE.md`; PR off `feature/003-workflow-engine-decoupling`, never `main`.

### Integration Points
- **Net-new packages:** `agents/workflows/` (manifest.py, compiler.py, plan.py, `<id>/workflow.yaml` ×15) and `agents/capabilities/` (base.py, registry.py) — neither exists yet.
- **Engine seam:** `execute()`/`_run_agent` consume the `CompiledWorkflow` for sequence/agents/deliverable/clarify/planner (D-09); the per-pipeline behavioral bodies stay.
- **API/frontend cutover:** new `app/api/runs.py` + rewritten `app/api/workflows.py` + `main.py` registration + 10 frontend repoints (D-01/D-02).
- **CI gates that constrain the work:** migration-ledger ratchet (don't flip L1–L13), import-linter (kernel→ports), banned-pattern (no hand-rolled deep agent), characterization snapshots.

</code_context>

<specifics>
## Specific Ideas

- Standing project directive (init): **"everything from plan.md must be honored — nothing dropped."** Both user overrides this session (D-01 SPEC-literal `/api/workflows` reclaim; D-05 full 15-manifest coverage) follow that directive — favor the complete, plan-faithful option over the lower-risk shortcut.
- The `/api/runs` relocation is **plan-aligned, not scope creep** — §22 already defines `/api/runs/{id}/artifacts|events|diff` (API-04/05, Phase 5). Phase 4 establishes the `/api/runs` home early so those land naturally.
- Authoring the `chat` manifest now **pre-stages** the Phase-7b ChatRunner→runtime migration (it'll already have a compiled definition + appear in the `/api/workflows` catalog).
- User took the recommended option on B, C, and the two locked forks (no-DSL, engine seam, validation mechanism); treat all as locked unless this file is edited.

</specifics>

<deferred>
## Deferred Ideas

- **`@register(kind, name)` self-registration + startup `discover()` + trust flags (`user_allowed`, owner allow-list)** — Phase 8 [3] / CAP-02, CAP-03. Phase 4 registers names centrally; Phase 8 converts to self-registration (evolution, not duplication).
- **Concrete capability impls** (`single_shot`/`task_loop` strategies, `html_static`/`html_render` validators, `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` resolvers, `opendesign`/`previous_run` providers, `heading_tasks` parser, `html_skeleton` compaction) + **deleting L1–L13** — Phase 7 [2] / PARITY-01..08.
- **Typed `ArtifactGraph`/`ArtifactRef` + persistence + deleting the `accumulated_outputs` mirror** — Phase 5 [1B] / ART-*, PERSIST-*, ledger L15.
- **`ModelResolver` / model policy** (the inert `model` fields populated by D-06) — Phase 6 [1C] / MODEL-*.
- **`GET /api/capabilities`** (registry palette) + new run-stream events + the dynamic composer — Phase 8+ / API-02/03/06.
- **Deprecated 308-redirect aliases for the old run-history paths** — only if the D-02 researcher directive finds an external API-key consumer; otherwise the clean break stands.

None of these are scope creep — all are explicitly later-phase per ROADMAP.md / the §31 ledger.

</deferred>

---

*Phase: 4-manifest-compiler-1a*
*Context gathered: 2026-06-07*

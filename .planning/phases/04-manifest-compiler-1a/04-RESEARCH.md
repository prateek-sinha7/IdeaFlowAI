# Phase 4: Manifest + Compiler [1A] - Research

**Researched:** 2026-06-07
**Domain:** Brownfield engine refactor — declarative workflow manifests + thin compiler + capability-name registry; route every pipeline through a compiled plan (legacy `accumulated_outputs` mirror retained, no L1–L13 deletion).
**Confidence:** HIGH (all findings grounded in the in-repo code + the locked plan/spec; no external/training dependencies — `yaml` 6.0.3 + `python-frontmatter` 1.1.0 already installed)

## Summary

Phase 4 is **net-new code under two packages** (`agents/workflows/`, `agents/capabilities/`) plus a **routing seam** in the existing `engine.py` and an **API reclaim** (`/api/workflows` → manifest metadata; run-history → new `/api/runs`). No new dependencies: the manifest loader mirrors the established `agents/loader.py` pattern (dataclass + `python-frontmatter` + per-field validation raising a typed error), both deps already present. The work splits cleanly along D-03..D-10 and the candidate 04-01..04-04 breakdown.

The single most important research output is the **D-09 classification of every `pipeline_type`/`spec.id ==` occurrence** in `engine.py`. The actual count is **not 44** — see the inventory below. The grep yields **41 `pipeline_type` references + 3 `spec.id == "<literal>"` references** for the **dispatch-relevant** symbols, but most `pipeline_type` hits are parameter declarations/log fields/pass-throughs, not behavioral branches. The behavioral branches that **survive** (allow-listed for Phase 7) are a small, enumerable set: the two frozensets (`_PPT_PIPELINE_TYPES`, `_PROTOTYPE_PIPELINE_TYPES`), `_resolve_final_output`, the L10 HTML-readback, the L7 `spec.id == "prototype-build"` dispatch, the `prototype_revision` seeding/post-fix blocks, and the L12 `_build_context_message` injection. The **routing** concerns that move to the `CompiledWorkflow` are: the agent list source (`get_pipeline_agents`), the `clarify.defaults` dict, the `planner: skip` flag, and the `od_prototype`→`prototype` id alias.

D-02 is resolved by evidence: the run-history routes in `workflows.py` are **JWT-only** (`Depends(get_current_user)`). The API-key dependency (`get_user_via_api_key`) is used **only** by `handoff.py` and `mcp.py` — never by `workflows.py`. **No external API-key consumer exists; the clean break stands; no 308-redirect aliases are required.**

**Primary recommendation:** Build the manifest/compiler/plan/registry as pure data+validation (mirroring `loader.py`), author 15 manifests grounded in `PIPELINE_AGENTS`, then introduce a single id-alias resolver + a `CompiledWorkflow`-sourced routing seam in `execute()` that replaces ONLY the four routing concerns above — leaving every behavioral branch in place and allow-listed. Reclaim `/api/workflows`, move run-history to `/api/runs`, repoint 10 frontend refs, no aliases.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 [user override]:** Reclaim `/api/workflows` for manifest definitions; relocate run-history to `/api/runs`. `GET /api/workflows` (list) + `GET /api/workflows/{id}` (one) return manifest-derived metadata; existing run-history moves to a new `/api/runs` router.
- **D-02:** Full move + frontend repoint, **clean break (no aliases)**. New `backend/app/api/runs.py` (`APIRouter(prefix="/api/runs")`) houses all moved run-history routes: `GET /api/runs` (was `GET /api/workflows`, keeps `?type=&limit=`), `GET /api/runs/{id}`, `GET /api/runs/{id}/chain-context`, `DELETE /api/runs/{id}`, `POST /api/runs/export-pptx`. `workflows.py` rewritten as the manifest-definitions router (404 on unknown id). Register `runs_router` in `main.py`. Repoint the 10 frontend refs. **No legacy aliases** (researcher directive resolved → none needed; see Security/D-02 below).
- **D-03:** 15 manifests — one per `PIPELINE_AGENTS` key. Revisions get their own manifest (distinct agents).
- **D-04:** `od_prototype` is the SOLE id-alias → `prototype` (no own manifest). `pipeline_type` reduced to an id-alias resolver at run entry: `od_prototype` → `prototype`; every real key resolves to itself. `od_ppt`/`od_ppt_revision` are REAL keys → own manifests (OpenDesign flavor declared via `context_providers: [opendesign]`; actual injection stays in surviving L12 until Phase 7).
- **D-05 [user override]:** Placeholder manifests for both edge cases (zero coverage-test exemptions). `reverse_engineer` → `steps: []` empty-plan stub. `chat` → manifest declaring its 7 agents; loads+compiles but engine does NOT dispatch it (ChatRunner-driven). No new schema fields for runnability. Coverage test: (1) all 15 load+compile; (2) the 13 engine-dispatchable pipelines execute from `CompiledWorkflow` with no legacy `pipeline_type` dispatch fallback (+ `od_prototype` alias runs `prototype`'s plan).
- **D-06:** Define the full §6 typed contract now; populate only Phase-4 fields. Forward fields (`model`, `tools`, `validators`, `fix`, `compaction`, `fanout`, `on_conflict`, `retry`, `injects`, `repo`, `limits`, …) declared-but-inert. Phase 4 populates: step `agent_id` + `strategy` (name) + `gates` (names) + `task_source`; workflow-level `steps`, `context_providers` (names), `seed_files`, `deliverable` (spec), `planner`, `clarify`.
- **D-07:** Minimal central name-registry now; defer self-registration + trust to Phase 8. `registry.py` = `CapabilityRegistry` keyed by `(kind, name)` with known names registered (no impls). `base.py` = the Protocol ports. Compiler validates every reference against the registry — unknown → compile error naming the bad reference.
- **D-08:** Strict-schema rejection + a guard test. Loader/schema rejects unknown/extra keys; a test asserts a manifest with any control-flow construct (`when:`/`if:`/`for:`/`${...}`/`{{...}}`) is rejected; a structure test asserts the compiler contains no workflow-name/`pipeline_type` branch (INV-1).
- **D-09:** Source structure from the plan; allow-list surviving behavioral branches as Phase-7-scoped. Engine sources step sequence, agent IDs, deliverable spec, clarify, planner-skip from the `CompiledWorkflow`. `pipeline_type` resolved to a manifest id at run entry, consumed only by that id-alias resolver for routing. Surviving L1–L13 behavioral branches that still read `pipeline_type`/`spec.id` remain and are explicitly allow-listed in the MAN-05 grep/structure test.
- **D-10:** Dataclass + `python-frontmatter`/`yaml` + manual validation raising `ManifestValidationError` (mirror `agents/loader.py`), NOT Pydantic. Error must name the offending field.

### Claude's Discretion
- Exact route handler signatures, response models, auth dependencies for the new `/api/runs` + `/api/workflows` definitions routers (mirror existing `workflows.py`: `Depends(...)` auth, `response_model=`).
- Whether nested forward-field types (D-06) are stub-defined now or deferred — provided no Phase-4 behavior keys off an inert field.
- Plan-task granularity / split — planner's call.
- Exact `description`/metadata wording in the stub `reverse_engineer` manifest and the `chat` manifest.
- Precise name of the new run-history router file (`runs.py` recommended) and whether `export-pptx` lands at `/api/runs/export-pptx` or nested.

### Deferred Ideas (OUT OF SCOPE)
- `@register(kind, name)` self-registration + startup `discover()` + trust flags (`user_allowed`, owner allow-list) — Phase 8 / CAP-02, CAP-03.
- Concrete capability impls (`single_shot`/`task_loop`, `html_static`/`html_render`, `single_file`/`serialized_sandbox`/`streamed_text`/`ppt`, `opendesign`/`previous_run`, `heading_tasks`, `html_skeleton`) + deleting L1–L13 — Phase 7 / PARITY-01..08.
- Typed `ArtifactGraph`/`ArtifactRef` + persistence + deleting the `accumulated_outputs` mirror — Phase 5 / ART-*, PERSIST-*, ledger L15.
- `ModelResolver` / model policy (the inert `model` fields) — Phase 6 / MODEL-*.
- `GET /api/capabilities` + new run-stream events + dynamic composer — Phase 8+.
- Deprecated 308-redirect aliases for old run-history paths — ONLY if an external API-key consumer existed; **research finds none → not built.**
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MAN-01 | `WorkflowManifest` schema + file-backed YAML loader/validator; required fields validated; malformed → typed `ManifestValidationError` naming the field | Mirror `agents/loader.py` `_build_spec` + `_require_nonempty_str` + `_optional_list_of_str` exactly (D-10). Pattern, deps, error shape all proven in-repo (see Code Examples). |
| MAN-02 | Thin no-DSL compiler → typed `CompiledWorkflow` Step DAG; nothing more | §6 dataclasses (`CompiledWorkflow`/`Step`/`Task`); compiler = name-resolution + topo-validate only. INV-5 enforced via strict-key rejection (D-08). Structure test: no `pipeline_type`/workflow-name branch in `compiler.py`. |
| MAN-03 | Capability-reference validation against `CapabilityRegistry`; reject unknown | `(kind, name)` registry with the authoritative name set below (D-07). Compiler validates strategy/validators/deliverable/context_providers/task parser/gates. Unknown → compile error naming the ref. |
| MAN-04 | Every pipeline runs from a compiled plan; legacy mirror retained; no legacy dispatch fallback | The four routing concerns (agent list, clarify defaults, planner skip, alias) sourced from `CompiledWorkflow`. 13 engine-dispatchable pipelines + `od_prototype` alias run from plan; `reverse_engineer` → empty plan; `chat` → compiles only. Parametrized coverage test (mirror `_drive`). |
| MAN-05 | `pipeline_type` retained only as a temporary id alias | Single id-alias resolver (`od_prototype`→`prototype`; identity otherwise). Surviving behavioral branches allow-listed. Grep/test confirms `pipeline_type` consumed only by the resolver for routing. |
| API-01 | `GET /api/workflows` + `GET /api/workflows/{id}` return manifest-derived metadata; 404 on unknown id | Rewrite `workflows.py` as definitions router (D-01/D-02). List = id/name/description/step summary; get = full step configs/gates/validators/deliverable/declared capabilities — from compiled manifests. Mirror existing FastAPI patterns. |
</phase_requirements>

## Project Constraints (from CLAUDE.md + backend/CLAUDE.md)

- **Tech stack:** Python · FastAPI · PostgreSQL · LangGraph checkpointer — extend, don't replace.
- **INV-13 deepagents runtime untouched:** no agent-loop changes; canonical `from deepagents import create_deep_agent` (`deepagents==0.6.7`). Phase 4 touches none of this.
- **Ports & Adapters (hexagonal):** kernel depends only on capability ports; import-linter enforces `agents.execution_engine.engine` must not import `app.api` (the only live contract today — see Environment/Validation).
- **Compiler thin, no DSL (INV-5);** manifests are data.
- **Additive migrations only; no DB change in Phase 4.**
- **`exec`/`network`/`secrets`/`spawn_subagents` default OFF** — `ToolPermissions` defaults in §6 already encode this; Phase 4 only declares fields inert.
- **No dual implementations (INV-3/INV-12):** only sanctioned temporary duplication is the `accumulated_outputs` mirror (deleted Phase 5/1B). The routing seam REPLACES the dict source — it does not run alongside a legacy dispatch.
- **Dev runtime:** `python3.11`, no venv. Tests: `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v`.
- **Commit scopes:** new packages map to `engine` (routing seam), `registry` (capability registry — or a new scope at planner discretion), `tests`; API work → no dedicated scope, use `feat(...)` with the route file. PR off `feature/003-workflow-engine-decoupling`, never `main`.
- **GSD enforcement:** all edits go through a GSD command.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Manifest schema + YAML load/validate (MAN-01) | `agents/workflows` (data layer) | — | Pure config-loading; mirrors `agents/loader.py` which already lives here. No web/engine dependency. |
| Compiler manifest→CompiledWorkflow (MAN-02) | `agents/workflows` (data layer) | `agents/capabilities` (registry, for name validation) | Pure transform; imports the registry port for INV-4 checks. No engine import. |
| `CompiledWorkflow`/`Step`/`Task` types (D-06) | `agents/workflows` (data layer) | — | Plain `@dataclass`; consumed by both compiler and kernel. The shared seam type. |
| Capability ports + registry (MAN-03) | `agents/capabilities` (ports) | — | The hexagonal port boundary; kernel imports only `capabilities.base`. |
| Engine routing seam (MAN-04/MAN-05) | `agents/execution_engine` (kernel) | `agents/workflows` (consumes `CompiledWorkflow`) | Kernel reads the compiled plan for sequence/agents/deliverable/clarify/planner; behavioral bodies stay. |
| id-alias resolver (MAN-05) | run entry (kernel `execute()` or a thin pre-resolver) | `agents/registry` (`_OD_ALIAS_BASE` as the source) | `pipeline_type` → manifest id only. Mirror the existing `_OD_ALIAS_BASE` resolution already in `registry.py` + `websocket.py`. |
| `/api/workflows` definitions (API-01) | `app/api` (web) | `agents/workflows` (reads compiled manifests) | Read-only metadata endpoint over the manifests. JWT auth (`get_current_user`). |
| `/api/runs` run-history (D-01/D-02) | `app/api` (web) | `app/models` (`WorkflowRun`) | Pure relocation of existing JWT-only CRUD; no engine/manifest dependency. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `python-frontmatter` | 1.1.0 (installed) | Parse YAML frontmatter / YAML files for manifests | [VERIFIED: requirements.txt:53 + `python3.11 -c "import frontmatter"` OK] Already the AGENT.md loader's parser; ships PyYAML. Use `frontmatter.loads` OR `yaml.safe_load` — manifests are pure YAML (no markdown body), so `yaml.safe_load` is the cleaner fit. |
| `PyYAML` (`yaml`) | 6.0.3 (installed) | Direct YAML parse of `workflow.yaml` | [VERIFIED: `python3.11 -c "import yaml; yaml.__version__"` → 6.0.3] Transitive via python-frontmatter; already imported by `app/services/od_loader.py`. No new dependency. |
| `dataclasses` (stdlib) | — | `WorkflowManifest`, `CompiledWorkflow`, `Step`, `Task` typed models | [CITED: plan §6/§32 "`@dataclass`/`Protocol` at every boundary"] Matches `AgentSpec` precedent. NOT Pydantic (D-10). |
| `typing.Protocol` (stdlib) | — | Capability ports in `capabilities/base.py` | [CITED: plan §6 — ports are `Protocol`] |
| `fastapi.APIRouter` | (installed) | `/api/workflows` rewrite + new `/api/runs` | [VERIFIED: app/api/workflows.py:15] Existing pattern to mirror. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-asyncio` | (installed) | All unit/coverage/structure tests | [VERIFIED: tests/agents/ run via `python3.11 -m pytest`] |
| `tests/agents/_scripted_model.py::_drive` | in-repo | Offline end-to-end `execute()` driver for the MAN-04 coverage test | [VERIFIED: tests/agents/_scripted_model.py:325] The exact harness the characterization tests use; the parametrized coverage test should reuse/extend it. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| dataclass + manual validation | Pydantic `BaseModel` | REJECTED by D-10 + §6/§32. The codebase precedent is dataclass + explicit per-field validation (`loader.py`); Pydantic would introduce a second validation idiom and is not how `AgentSpec` works. |
| `yaml.safe_load` | `frontmatter.loads` | Manifests are pure YAML (no markdown prompt body), so `yaml.safe_load` reads them directly. `frontmatter.loads` also works (returns `.metadata` + empty `.content`) and keeps the loader visually identical to `loader.py`. Planner's call; `yaml.safe_load` is marginally cleaner for body-less YAML. |

**Installation:** None required — `python-frontmatter==1.1.0` and `PyYAML 6.0.3` are already installed.

## Package Legitimacy Audit

> Phase 4 installs **no new external packages**. All parsing/validation uses stdlib + already-pinned deps.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `python-frontmatter` | PyPI | 1.1.0 pinned (mature) | high | github.com/eyeseast/python-frontmatter | N/A (already a dep) | Already installed — no install action |
| `PyYAML` (`yaml`) | PyPI | 6.0.3 (mature) | very high | github.com/yaml/pyyaml | N/A (transitive, already present) | Already installed — no install action |

**Packages removed due to slopcheck [SLOP] verdict:** none (no installs).
**Packages flagged as suspicious [SUS]:** none.

## D-09 — Engine `pipeline_type` / `spec.id ==` Inventory + Classification (CRITICAL)

**Verified count:** the grep for the dispatch-relevant symbols returns **41 lines containing `pipeline_type`** + **3 lines containing `spec.id == "<literal>"`** in `engine.py` (2710 lines). The CONTEXT.md "~44" figure is approximately the **41 `pipeline_type` + 3 `spec.id ==`** total (44). Most `pipeline_type` hits are **non-branching** (parameter declarations, log/event fields, pass-throughs). The exhaustive classification below covers every line; the legend is:

- **ROUTING** → now sourced from the `CompiledWorkflow` in Phase 4 (replaced as the source of the value).
- **BEHAVIORAL** → an L1–L13 branch that SURVIVES Phase 4; allow-listed for Phase 7 in the MAN-05 grep/structure test.
- **PASS-THROUGH** → a parameter, log field, event payload, or label that neither routes nor branches; stays as-is (still carries `pipeline_type` as the id label; not a violation of MAN-05 because it does not *select behavior*).
- **ALIAS** → the id-alias resolution point (MAN-05).

### `pipeline_type` declarations / definitions

| Line | Code (abbrev) | Class | Phase-4 action |
|------|---------------|-------|-----------------|
| 95 | `_PPT_PIPELINE_TYPES = frozenset({...})` | BEHAVIORAL (L1) | Survives. Allow-listed. |
| 107 | `_PROTOTYPE_PIPELINE_TYPES = frozenset({"prototype","od_prototype"})` | BEHAVIORAL (L1) | Survives. Allow-listed. |
| 319 | `def _resolve_final_output(pipeline_type, ...)` | BEHAVIORAL (L2/L9) | Survives (param of the deliverable resolver). Allow-listed. |
| 348 | docstring `pipeline_type:` | comment | none |
| 415 | `def execute(..., pipeline_type: str = "custom", ...)` | PASS-THROUGH (param) | Stays — this is the run label. The seam resolves it to a manifest id internally. |
| 1044 | `_run_planner(..., pipeline_type=...)` signature | PASS-THROUGH | none |
| 1074 | `_invoke_planner(..., pipeline_type=...)` signature | PASS-THROUGH | none |
| 1101 | `_run_build_task_loop(..., pipeline_type, ...)` signature | PASS-THROUGH (L11 internals) | Survives. |
| 1139 | `_run_agent(..., pipeline_type, ...)` signature | PASS-THROUGH | Stays; the per-agent body still receives the label. |
| 1487 | `_build_context_message(..., pipeline_type, ...)` signature | PASS-THROUGH (L12 host) | Survives. |
| 2096 | `_persist_workflow_definition(..., pipeline_type, ...)` signature | PASS-THROUGH | none |

### `pipeline_type` branches (behavioral) — SURVIVE, allow-list for Phase 7

| Line | Code (abbrev) | Class | Leak | Note |
|------|---------------|-------|------|------|
| 360 | `if pipeline_type == "prototype_revision":` (in `_resolve_final_output`) | BEHAVIORAL | L2/L9 | Deliverable-by-class. |
| 377 | `if pipeline_type in _PROTOTYPE_PIPELINE_TYPES:` (in `_resolve_final_output`) | BEHAVIORAL | L2/L9 | Deliverable-by-class. |
| 555 | `if pipeline_type == "prototype_revision":` (seeding/baseline block) | BEHAVIORAL | L4/L8 | Revision seeding survives. |
| 939 | `pipeline_type == "prototype_revision"` (post-revision fix-loop) | BEHAVIORAL | L4/L8 | Post-revision validation survives. |
| 1004 | `if pipeline_type in _PPT_PIPELINE_TYPES and final_output:` (carousel sanitize) | BEHAVIORAL | L3 | Survives. |
| 1356 | `if pipeline_type in ("od_prototype","prototype"):` (HTML read-back) | BEHAVIORAL | L10 | Survives. **Note: the migration-ledger L10 grep pattern is `pipeline_type in \("od_prototype", ?"prototype"\)` — the seam must NOT alter this line's spelling or it breaks the ledger test wiring.** |
| 1370 | `if pipeline_type in _PPT_PIPELINE_TYPES and output:` (per-agent carousel sanitize) | BEHAVIORAL | L3 | Survives. |
| 2114 | `if pipeline_type in PIPELINE_AGENTS and pipeline_type != "custom":` (skip custom-workflow persist) | BEHAVIORAL (persistence guard) | — | Survives; persistence concern, not routing. |

### `pipeline_type` ROUTING concerns — move to the `CompiledWorkflow` in Phase 4

| Line(s) | Code (abbrev) | Class | Phase-4 action |
|---------|---------------|-------|-----------------|
| 723–724 | `from agents.prototype.pipeline import SKIP_PLANNER_FOR_PROTOTYPE, is_prototype_pipeline; skip_planner = SKIP_PLANNER_FOR_PROTOTYPE and is_prototype_pipeline(pipeline_type)` | ROUTING (L5) | Source `planner: skip\|run` from `CompiledWorkflow.planner`. **NOTE: `SKIP_PLANNER_FOR_PROTOTYPE = False` today** (see `agents/prototype/pipeline.py:63`) — so `skip_planner` is currently ALWAYS `False`; every pipeline (incl. prototype) runs the planner/clarifier. The prototype manifests must therefore declare `planner: run` to be byte-identical (NOT `planner: skip` despite §10's illustrative YAML). This is a real-code-vs-plan divergence the planner MUST honor. |
| 752–766 | `_pipeline_defaults: dict[...]` + `defaults = _pipeline_defaults.get(pipeline_type, _pipeline_defaults["custom"])` (ALWAYS_CLARIFY seeding) | ROUTING (L6) | Source `clarify.defaults` from `CompiledWorkflow.clarify`. **NOTE: this dict is keyed by `od_ppt`/`ppt`/`od_prototype`/`prototype`/… — the per-manifest `clarify.defaults` lists must reproduce these EXACT lists per pipeline (see per-manifest map below).** |
| (implicit) `get_pipeline_agents(pipeline_type)` at the call sites that build `agents=` | ROUTING (agent list) | The agent SEQUENCE + ids now come from `CompiledWorkflow.steps[*].agent_id`. In production the WS handler calls `get_pipeline_agents`; the seam should resolve agents from the compiled plan (or assert plan order == registry order during 1A). |
| 433/953/etc. `od_prototype` → `prototype` alias handling (in `websocket.py:433`, `registry._OD_ALIAS_BASE`) | ALIAS (MAN-05) | Centralize into the id-alias resolver: `od_prototype` → manifest id `prototype`. |

### `pipeline_type` PASS-THROUGH (log fields / event payloads / labels) — no change

Lines 386, 710, 717, 729, 737, 742, 769, 810, 867, 894, 902, 994, 1020, 1049, 1079, 1582, 2148, 2237, 2277 — all are log-event fields, planner-context dict entries, event `data` payloads, sub-call pass-throughs, or the persisted run `type=` label. **None select behavior.** They keep carrying `pipeline_type` as the run id label and are NOT MAN-05 violations. The MAN-05 grep/structure test should target *behavioral branches* (`if pipeline_type ==` / `if pipeline_type in`), not every textual occurrence.

### `spec.id == "<literal>"` branches

| Line | Code | Class | Leak | Phase-4 action |
|------|------|-------|------|-----------------|
| 891 | `if getattr(spec, "id", None) == "prototype-build":` (build-task-loop dispatch) | BEHAVIORAL | L7 | Survives. Allow-listed. **Ledger L7 grep is `spec\.id == "prototype-build"` — do not alter line 1014-context; the dispatch on line ~891 is the live one (ledger cites :872, drifted to 891).** |
| 2428 | `is_build_task_2_plus = (spec.id == "prototype-build" and ...)` (L12 injection sizing) | BEHAVIORAL | L12 | Survives. |
| 2511 | `if spec.id == "prototype-build":` (current-task block injection) | BEHAVIORAL | L12 | Survives. |

> All other `spec.id` occurrences (1160, 1168, 1199, 2339, 2371, etc.) are `spec.id` *used as the agent identity* (dict keys, event payloads, gate membership tests, first-agent detection) — **not `== "<workflow/agent literal>"` behavioral dispatch**. They are correct and untouched.

**Classification summary:** 8 behavioral `pipeline_type` branches + 3 behavioral `spec.id` branches survive (allow-listed). 3 routing concerns (planner-skip L5, clarify-defaults L6, agent-list) move to the `CompiledWorkflow`. 1 alias concern (`od_prototype`) becomes the id-alias resolver. All remaining occurrences are pass-throughs/labels.

## D-07 — Authoritative Capability Name Set + Per-Manifest Reference Map (CRITICAL)

The registry must register every `(kind, name)` the 15 manifests reference so all compile clean. Derived from §10 + §30 + §32 cross-checked against `PIPELINE_AGENTS` + actual engine behavior:

### Authoritative `(kind, name)` registry set

| Kind | Names to register | Source / justification |
|------|-------------------|------------------------|
| `strategy` | `single_shot`, `task_loop` | §10/§32. `task_loop` only for `prototype-build`; everything else `single_shot`. |
| `validator` | `html_static`, `html_render` | §10 (prototype build validators). Only referenced by the `prototype-build` step. |
| `deliverable` (resolver) | `single_file`, `serialized_sandbox`, `streamed_text`, `ppt` | §32 lists `single_file·serialized_sandbox·streamed_text·repo_diff`; `_resolve_final_output` proves the 4 live classes: prototype.html (`single_file`), code-gen bundle (`serialized_sandbox`), text/PPT streamed (`streamed_text`), and PPT needs a `ppt` resolver per §31 L3. **`repo_diff` is NOT needed by any of the 15 manifests** (repo workflows are Phases 9–12) — register it only if the planner wants forward-completeness; not required for clean compile. |
| `context_provider` | `opendesign`, `previous_run` | §10/§32. `opendesign` for od_* manifests; `previous_run` for revisions (seeding). |
| `task_parser` | `heading_tasks` | §10 (`task_source.parser: heading_tasks`). Only the prototype-build step. |
| `gate` | `human`, `validation` | §10/§32. `human` for prototype-specify/plan; `validation` for revision post-edit. |
| `compaction` | `html_skeleton` | §10/§32 (prototype-build `compaction`). Only the prototype-build step. |

**Minimum set for clean compile of the 15 manifests:** `single_shot`, `task_loop`, `html_static`, `html_render`, `single_file`, `serialized_sandbox`, `streamed_text`, `ppt`, `opendesign`, `previous_run`, `heading_tasks`, `human`, `validation`, `html_skeleton`. (`repo_diff` optional/forward.)

### Per-manifest reference map (what each of the 15 must reference)

> Strategy defaults to `single_shot`; only `prototype`/`od_prototype`-base `prototype-build` step uses `task_loop`. Deliverable resolver derived from `_resolve_final_output` classes. `clarify.defaults` reproduce the exact `_pipeline_defaults` dict (engine.py:752-761). `planner: run` for ALL (since `SKIP_PLANNER_FOR_PROTOTYPE = False`).

| Manifest id | agents (from `PIPELINE_AGENTS`) | strategy(s) | deliverable | gates | context_providers | task_parser | validators | clarify.defaults (exact) |
|-------------|--------------------------------|-------------|-------------|-------|-------------------|-------------|------------|--------------------------|
| `user_stories` | 6: domain-analyst…backlog-compiler | single_shot | streamed_text | (per AGENT.md `gate`) | — | — | — | `[target_audience, scope, priority, technology]` |
| `user_stories_revision` | 1: user-story-revision-agent | single_shot | streamed_text | — | previous_run | — | — | (falls to custom) `[target_audience, key_objectives, scope, priority]` |
| `ppt` | 3: od-ppt-brief-analyst, od-ppt-composer, od-ppt-validator | single_shot | ppt (streamed_text + carousel sanitize) | — | — | — | — | `[target_audience, tone_and_style, key_objectives, slide_count]` |
| `ppt_revision` | 2: ppt-revision-agent, ppt-revision-assembler | single_shot | ppt | — | previous_run | — | — | (custom) |
| `od_ppt` | 3: od-ppt-brief-analyst, od-ppt-composer, od-ppt-validator | single_shot | ppt | — | opendesign | — | — | `[target_audience, tone_and_style, key_objectives, slide_count]` |
| `od_ppt_revision` | 1: od-ppt-revision-agent | single_shot | ppt | — | opendesign, previous_run | — | — | (custom) |
| `prototype` | 4: prototype-specify, prototype-plan, prototype-build, prototype-validate | single_shot (specify/plan/validate), **task_loop** (build) | single_file (prototype.html) | human (specify, plan) | opendesign | heading_tasks (build) | html_static, html_render (build) | `[target_audience, scope, priority, style]` |
| `prototype_revision` | 1: prototype-revision-agent | single_shot | single_file | validation (post-edit) | previous_run | — | html_static, html_render | (custom) |
| `app_builder` | 15: material-analyzer…app-sdlc-governance | single_shot | serialized_sandbox | (per AGENT.md) | — | — | — | `[technology, scope, target_audience, security]` |
| `app_builder_revision` | 1: app-builder-revision-agent | single_shot | serialized_sandbox | — | previous_run | — | — | (custom) |
| `mulesoft_to_springboot` | 13: mulesoft-inventory…mulesoft-sdlc-governance | single_shot | serialized_sandbox | (per AGENT.md) | — | — | — | `[scope, technology, timeline, priority]` |
| `dotnet_to_azure` | 13: dotnet-inventory…dotnet-sdlc-governance | single_shot | serialized_sandbox | (per AGENT.md) | — | — | — | `[scope, technology, timeline, priority]` |
| `custom` | 8: market-research-agent…report-generator | single_shot | streamed_text | — | — | — | — | `[target_audience, key_objectives, scope, priority]` |
| `reverse_engineer` | `[]` (empty) | — | (none / streamed_text default) | — | — | — | — | (custom) — STUB, `steps: []`, compiles to empty plan |
| `chat` | 7: chat-discovery…chat-preview | single_shot | streamed_text | — | — | — | — | (n/a) — compiles; engine does NOT dispatch (ChatRunner) |

**Edge cases (D-05):**
- `reverse_engineer`: `steps: []` — the schema MUST permit an empty `steps` list (MAN-01); compiler produces an empty-DAG `CompiledWorkflow`. `description: "agents TBD"`.
- `chat`: full 7-agent manifest; loads + compiles + appears in `/api/workflows`; engine never dispatches it (driven by `app/agents/chat_runner.py` `ChatRunner`; excluded from `allowed_custom_agent_ids` via `_INTERNAL_PIPELINES`).

> The `gates` per step for the non-prototype pipelines should be derived from each agent's AGENT.md `gate: Human_Gate` declaration (the engine's static gate set). The planner should grep `agents/prompts/*/AGENT.md` for `gate:` to populate per-step `gates` accurately, OR declare `gates: []` per step and rely on the surviving static-gate detection (`_should_gate` reads `spec.gate`) — **the latter is the lower-risk 1A choice** since gate selection still flows through `gate_agent_ids`/`_should_gate` (behavioral, Phase-7-scoped), and the manifest `gates` field can be declared-but-inert for non-prototype steps in Phase 4.

## D-02 — API-Key Public Surface Check (RESOLVED)

**Finding: NO external API-key consumer of the run-history routes. The clean break stands. No 308-redirect aliases required.**

Evidence:
- `backend/app/api/workflows.py` route handlers ALL use `current_user: User = Depends(get_current_user)` — the **JWT** dependency (`app/core/dependencies.py`), NOT the API-key dependency.
- `grep get_user_via_api_key` across `app/` returns matches ONLY in `app/api/handoff.py:179` and (`hash_api_key`/`mint_api_key`) in `mcp.py`/`settings.py`. **`workflows.py` never imports or uses `get_user_via_api_key`.** [VERIFIED: grep — see Environment Availability]
- The API-key surface (`api_key_auth.py` docstring) is explicitly "the IDE / MCP clients" → the `/flowin-handoff` pipeline, not run-history.

**Conclusion:** Relocating `GET /api/workflows`, `GET /api/workflows/{id}`, `/chain-context`, `DELETE`, `/export-pptx` to `/api/runs` affects only browser (JWT) clients. The 10 frontend refs are repointed atomically in this phase; the Deferred "308-redirect aliases" item is **not built.**

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────────────────────────────┐
  run entry               │  pipeline_type (legacy label, e.g.           │
  (WS run_pipeline /      │  "od_prototype")                             │
   /api/prototype/run /   └───────────────────┬─────────────────────────┘
   coverage test _drive)                      │
                                              ▼
                              ┌───────────────────────────────┐
                              │  id-alias resolver (MAN-05)    │  od_prototype → "prototype"
                              │  _OD_ALIAS_BASE-derived        │  every real key → itself
                              └───────────────┬───────────────┘
                                              │ manifest id
                                              ▼
        agents/workflows/<id>/workflow.yaml ──► WorkflowManifest (MAN-01: dataclass + yaml + validate)
                                              │        │ ManifestValidationError(field) on malformed
                                              ▼        ▼
                              ┌───────────────────────────────┐     ┌──────────────────────────────┐
                              │  WorkflowCompiler.compile()    │────►│  CapabilityRegistry          │
                              │  (MAN-02: thin, no DSL)        │ ref │  (kind,name) → seam (MAN-03)  │
                              │  - resolve names               │◄────│  unknown name → compile error│
                              │  - topo-validate Step DAG      │     └──────────────────────────────┘
                              └───────────────┬───────────────┘
                                              │ CompiledWorkflow (Step DAG, deliverable, planner, clarify)
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │  ExecutionEngine.execute()  (KERNEL — routing seam, MAN-04)                                 │
   │   sources FROM CompiledWorkflow:  step sequence · agent_ids · deliverable spec · clarify    │
   │                                   defaults · planner skip                                   │
   │   SURVIVING behavioral branches (allow-listed, Phase 7): _resolve_final_output, L10 HTML    │
   │     read-back, L7 prototype-build dispatch, prototype_revision seeding/fix, L12 injection,  │
   │     PPT carousel sanitize, _PPT/_PROTOTYPE frozensets                                       │
   │   artifacts handoff:  accumulated_outputs mirror (UNCHANGED — L15, deleted Phase 5)         │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
                                              │ events (semantic parity, INV-3)
                                              ▼
                          frontend / characterization snapshots (must stay green)

   ── API track (parallel) ──
   GET /api/workflows, /{id}  ──► reads compiled manifests ──► metadata (id,name,desc,steps,gates,...)  [JWT]
   /api/runs/* (NEW)          ──► WorkflowRun DB CRUD (relocated run-history)                            [JWT]
```

### Recommended Project Structure (Phase-4 subset of §32)
```
backend/agents/
├── workflows/                       # NEW — data layer (no engine/api imports)
│   ├── __init__.py
│   ├── manifest.py                  # WorkflowManifest + ManifestValidationError + load (D-10)
│   ├── compiler.py                  # WorkflowCompiler.compile() (thin, no DSL — MAN-02/INV-5)
│   ├── plan.py                      # CompiledWorkflow / Step / Task (+ inert forward types, D-06)
│   ├── user_stories/workflow.yaml
│   ├── prototype/workflow.yaml      # the SC-001 parity manifest
│   ├── … (15 dirs total; od_prototype has NO dir — alias only)
│   └── chat/workflow.yaml           # compiles, engine does not dispatch
├── capabilities/                    # NEW — ports + registry
│   ├── __init__.py
│   ├── base.py                      # Protocols: ExecutionStrategy, Validator, DeliverableResolver,
│   │                                #            ContextProvider, GateHandler, TaskParser, … (§6)
│   └── registry.py                  # CapabilityRegistry((kind,name)) + register known NAMES (D-07)
└── execution_engine/engine.py       # routing seam added; behavioral bodies untouched

backend/app/api/
├── workflows.py                     # REWRITTEN — manifest definitions router (API-01)
└── runs.py                          # NEW — relocated run-history CRUD (D-01/D-02)
```

### Pattern 1: Typed-config loader mirroring `loader.py` (MAN-01 / D-10)
**What:** dataclass + `yaml`/`frontmatter` parse + per-field validation raising `ManifestValidationError(field)`.
**When to use:** `manifest.py`.
**Example:** see Code Examples below (verbatim adaptation of `agents/loader.py:_build_spec`).

### Pattern 2: Registry keyed by `(kind, name)` with name-only registration (MAN-03 / D-07)
**What:** a dict `{(kind, name): <marker/port-class>}`; `is_registered(kind, name) -> bool`; the compiler calls it for every declared reference. No impls, no trust flags.
**When to use:** `capabilities/registry.py`. Phase 8 swaps the central registration for `@register` self-registration (evolution, not duplication — INV-12 respected).

### Pattern 3: Thin compiler = name-resolve + topo-validate only (MAN-02 / INV-5)
**What:** `compile(manifest) -> CompiledWorkflow`: map manifest dicts → `Step`/`Task` dataclasses, validate every capability name against the registry, topo-validate the DAG. **No `if pipeline_type`, no workflow-name branch, no eval of any value.**
**When to use:** `compiler.py`. A structure test (D-08) asserts the source contains no `pipeline_type`/workflow-name literal branch.

### Anti-Patterns to Avoid
- **Running a legacy dispatch fallback alongside the compiled plan** (INV-12 violation). The seam must REPLACE `get_pipeline_agents` as the *source* of sequence/agents — not add a second path. (The behavioral bodies are allowed to remain; that is leak-survival, not dual dispatch.)
- **Putting any logic in manifests** (INV-5). Strict-key rejection (D-08) makes control-flow keys have nowhere to live.
- **Declaring `planner: skip` for prototype manifests** — `SKIP_PLANNER_FOR_PROTOTYPE = False` today; `planner: skip` would change behavior and break snapshots. Use `planner: run`.
- **Altering the exact spelling of L7/L10 behavioral lines** — the migration-ledger grep patterns are pinned to specific text; cosmetic edits there would falsely trip the ratchet once those rows flip in Phase 7.
- **Using Pydantic** for the manifest (D-10 / §6 / §32).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | A custom parser | `yaml.safe_load` / `frontmatter.loads` | Already a dep; `safe_load` avoids arbitrary-object construction. |
| Per-field validation idiom | A new validation framework | Copy `loader.py::_require_nonempty_str` / `_optional_list_of_str` | Proven, tested, named-field errors — exactly MAN-01's requirement. |
| End-to-end engine driver for the coverage test | A fresh harness | `tests/agents/_scripted_model.py::_drive` | Already runs `execute()` offline with scripted models + od_context + alias handling; the characterization tests use it. |
| od_prototype→prototype alias logic | A new map | Reuse/centralize `registry._OD_ALIAS_BASE` + the `websocket.py:433` map | Single source of truth already exists; MAN-05 just lifts it to a named resolver. |
| Topo-sort / DAG validation | A custom sort | Reuse `agents/execution_engine/resolver.py` (`WorkflowResolver`) if its DAG validation fits, else stdlib | `execute()` already calls `WorkflowResolver`; check whether it can validate the compiled Step DAG to avoid a second DAG validator. |

**Key insight:** Phase 4 is overwhelmingly *plumbing of existing, tested patterns*. The risk is not novel algorithms; it is (a) byte-identity of the routing seam vs. the surviving behavioral branches, and (b) the manifests faithfully reproducing the hardcoded dicts (clarify defaults, planner flag, agent order).

## Runtime State Inventory

> This is a refactor/routing phase. A grep finds files; it does not find runtime/registered state. Each category answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None affecting Phase 4.** `WorkflowRun` rows carry `type = pipeline_type` (the legacy label). Phase 4 does NOT rename `pipeline_type` values — it keeps them as ids (MAN-05 keeps the label). So no DB data migration. | None — verified: `pipeline_type` strings are unchanged; manifests reuse the same ids. |
| Live service config | **None.** No external service (n8n/Datadog/etc.) stores these workflow ids. The composer/frontend reads workflow types via the API — which is exactly what API-01 makes dynamic. The 10 frontend refs to `/api/workflows` (run-history) are in git and repointed in this phase. | Code edit only — repoint 10 frontend refs (D-02). |
| OS-registered state | **None.** No Task Scheduler / pm2 / systemd registration embeds `pipeline_type`. | None — verified: backend runs under uvicorn; no OS-registered task names involved. |
| Secrets/env vars | **None renamed.** `RUNS_ROOT`, `DATABASE_URL`, `ANTHROPIC_API_KEY` unaffected. The API-key surface (`X-Flowin-API-Key`) is untouched (D-02 finding). | None. |
| Build artifacts / installed packages | **None.** No package rename; no egg-info. New packages `agents/workflows`, `agents/capabilities` are importable in-tree (no install). `yaml`/`frontmatter` already installed. | None — confirm `agents/workflows/__init__.py` + `agents/capabilities/__init__.py` exist so imports resolve. |

**Routing-seam runtime caution (not a stored-state item but the real migration hazard):** the engine reads its agent list from `get_pipeline_agents(pipeline_type)` which **scans `agents/prompts/*/AGENT.md` by `pipeline_type` and sorts by `order`** (`loader.list_agent_ids`). The manifest `steps[*].agent_id` order MUST match that sorted order exactly, or the compiled plan reorders agents and breaks snapshots. The planner should either (a) derive manifest step order FROM `get_pipeline_agents` output, or (b) add a 1A assertion `[s.agent_id for s in plan.steps] == [a.id for a in get_pipeline_agents(id)]`.

## Common Pitfalls

### Pitfall 1: Prototype manifest `planner: skip` breaks parity
**What goes wrong:** Authoring `planner: skip` per §10's illustrative YAML.
**Why it happens:** §10 documents the *intended* behavior (L5 was skip-planner); but the live flag `SKIP_PLANNER_FOR_PROTOTYPE = False` means the planner currently runs for prototype too.
**How to avoid:** All 13 dispatchable manifests declare `planner: run`. Verify against `agents/prototype/pipeline.py:63`.
**Warning signs:** prototype characterization event snapshot diff (missing/extra `planner_start`/`planner_complete` events).

### Pitfall 2: `clarify.defaults` lists drift from the hardcoded dict
**What goes wrong:** The manifest `clarify.defaults` don't match `_pipeline_defaults` (engine.py:752-761) verbatim.
**Why it happens:** Re-typing the lists from memory.
**How to avoid:** Copy each list verbatim from the per-manifest map above (sourced from the engine dict). Note `od_ppt`==`ppt` and `od_prototype`==`prototype`; revisions + unknown fall to the `custom` list.
**Warning signs:** With `ALWAYS_CLARIFY` on in production, the clarifier seeds different default questions — a visible UX change (not caught by the offline `_drive` snapshot, which sets `ALWAYS_CLARIFY = False`). Add a unit test comparing `compiled.clarify.defaults` to the engine dict for each pipeline.

### Pitfall 3: Manifest step order ≠ registry/AGENT.md `order`
**What goes wrong:** Compiled plan dispatches agents in manifest-author order, not `order`-sorted order.
**Why it happens:** `get_pipeline_agents` sorts by `AgentSpec.order`; a hand-authored manifest could list them differently.
**How to avoid:** Derive step order from `get_pipeline_agents(id)` when authoring; assert equality in the coverage test.
**Warning signs:** Snapshot agent-sequence diffs.

### Pitfall 4: Touching the L7/L10 behavioral lines' exact text
**What goes wrong:** Reformatting `if pipeline_type in ("od_prototype","prototype"):` or `spec.id == "prototype-build"` while wiring the seam.
**Why it happens:** Natural cleanup during refactor.
**How to avoid:** Leave behavioral branches byte-identical (they're Phase-7 deletions). The migration-ledger grep patterns are pinned to this text.
**Warning signs:** `test_migration_ledger.py` would only catch this once the row flips to `☑` (Phase 7) — so a silent drift now becomes a future false ratchet trip. Treat behavioral lines as read-only.

### Pitfall 5: import-linter / hexagonal direction violation
**What goes wrong:** `compiler.py` importing the kernel, or `engine.py` importing `app.api`.
**Why it happens:** Convenience imports.
**How to avoid:** `agents/workflows` and `agents/capabilities` import only stdlib + each other (workflows → capabilities for name validation); the kernel imports `capabilities.base` ports + `workflows.plan` types. The current import-linter contract only forbids `agents.execution_engine.engine → app.api`; do not add an `engine → app.api` import via the new API code.
**Warning signs:** `cd backend && lint-imports` fails.

## Code Examples

### MAN-01 loader pattern (verbatim adaptation of `agents/loader.py`)
```python
# Source: backend/agents/loader.py:121-171, 229-394 (the proven in-repo pattern)
# agents/workflows/manifest.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml  # PyYAML 6.0.3 — already installed

class ManifestValidationError(Exception):
    """Raised when a workflow.yaml has invalid or missing fields (names the field)."""

@dataclass
class WorkflowManifest:
    id: str
    steps: list[dict]                 # raw step dicts; compiler turns these into Step
    deliverable: dict                 # {strategy: ..., name: ...}
    planner: str                      # "run" | "skip"
    clarify: dict                     # {mode, defaults}
    context_providers: list[str] = field(default_factory=list)
    seed_files: dict = field(default_factory=dict)
    version: int = 1
    model: dict | None = None
    limits: dict | None = None

_ALLOWED_TOP_KEYS = {"id","version","model","planner","clarify","context_providers",
                     "seed_files","deliverable","limits","steps"}

def load_manifest(workflow_id: str, base_dir: Path) -> WorkflowManifest:
    path = base_dir / workflow_id / "workflow.yaml"
    if not path.exists():
        raise FileNotFoundError(f"workflow.yaml not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ManifestValidationError(f"{path}: top-level must be a mapping")
    # D-08 strict-key rejection → no DSL field has anywhere to live (INV-5)
    extra = set(data) - _ALLOWED_TOP_KEYS
    if extra:
        raise ManifestValidationError(f"{path}: unknown key(s) {sorted(extra)} — manifests are pure data (INV-5)")
    # required fields (MAN-01) — each error NAMES the field
    for req in ("id", "steps", "deliverable", "planner", "clarify"):
        if req not in data:
            raise ManifestValidationError(f"{path}: missing required field '{req}'")
    steps = data["steps"]
    if not isinstance(steps, list):                       # steps:[] is valid (reverse_engineer)
        raise ManifestValidationError(f"{path}: field 'steps' must be a list")
    # ... per-field type checks mirroring _require_nonempty_str / _optional_list_of_str ...
    return WorkflowManifest(id=data["id"], steps=steps, deliverable=data["deliverable"],
                            planner=data["planner"], clarify=data["clarify"],
                            context_providers=data.get("context_providers", []),
                            seed_files=data.get("seed_files", {}),
                            version=data.get("version", 1),
                            model=data.get("model"), limits=data.get("limits"))
```

### MAN-03 registry (name-only, `(kind, name)`)
```python
# agents/capabilities/registry.py — D-07 (names only; impls + trust = Phase 7/8)
_KNOWN: set[tuple[str, str]] = {
    ("strategy", "single_shot"), ("strategy", "task_loop"),
    ("validator", "html_static"), ("validator", "html_render"),
    ("deliverable", "single_file"), ("deliverable", "serialized_sandbox"),
    ("deliverable", "streamed_text"), ("deliverable", "ppt"),
    ("context_provider", "opendesign"), ("context_provider", "previous_run"),
    ("task_parser", "heading_tasks"),
    ("gate", "human"), ("gate", "validation"),
    ("compaction", "html_skeleton"),
}
class CapabilityRegistry:
    def is_registered(self, kind: str, name: str) -> bool:
        return (kind, name) in _KNOWN
```

### MAN-02 compiler reference-validation (the INV-4 check)
```python
# agents/workflows/compiler.py — thin: resolve names + topo-validate, no DSL
class CompilerError(Exception): ...

def compile(manifest, registry) -> "CompiledWorkflow":
    for raw in manifest.steps:
        strat = raw.get("strategy", "single_shot")
        if not registry.is_registered("strategy", strat):
            raise CompilerError(f"unknown strategy '{strat}' in step {raw.get('agent')!r}")
        for v in raw.get("validators", []):
            if not registry.is_registered("validator", v):
                raise CompilerError(f"unknown validator '{v}' in step {raw.get('agent')!r}")
        # ... gates, task_source.parser, compaction likewise ...
    for cp in manifest.context_providers:
        if not registry.is_registered("context_provider", cp):
            raise CompilerError(f"unknown context_provider '{cp}'")
    dres = manifest.deliverable.get("strategy")
    if dres and not registry.is_registered("deliverable", dres):
        raise CompilerError(f"unknown deliverable resolver '{dres}'")
    # build Step DAG, topo-validate (reuse WorkflowResolver if it fits) ...
```

### Coverage-test harness reuse (MAN-04)
```python
# Source: backend/tests/agents/_scripted_model.py:325-453 — reuse for the parametrized coverage test
# from tests.agents._scripted_model import _drive
# @pytest.mark.parametrize("ptype", THE_13_DISPATCHABLE + ["od_prototype"])
# async def test_runs_from_compiled_plan(ptype): events = await _drive(ptype); assert events
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Behavior selected by `if pipeline_type ==` in the engine | Declared capabilities referenced by name; kernel resolves via registry | This refactor (003), Phase 4 introduces the seam; Phase 7 deletes branches | Phase 4 = declaration layer only; branches survive. |
| Agents from `PIPELINE_AGENTS` dict | Steps from `CompiledWorkflow` | Phase 4 | Source of sequence/agents moves; dict stays as the manifest-derivation source until removed later. |
| Pydantic-style config (not used here) | dataclass + manual validation (`loader.py`) | established | Manifest mirrors it (D-10). |

**Deprecated/outdated:**
- §10's illustrative `planner: skip` for prototype — **outdated vs. live code** (`SKIP_PLANNER_FOR_PROTOTYPE = False`). Use `planner: run`. [VERIFIED: agents/prototype/pipeline.py:63]
- `_OD_ALIAS_BASE` duplicated between `registry.py:262` and `websocket.py:433` — Phase 4's id-alias resolver should consolidate (single source).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `ppt` deliverable resolver name (`deliverable: ppt`) is the right capability for ppt/od_ppt rather than `streamed_text` + a transform | D-07 / per-manifest map | LOW — §31 L3 explicitly assigns PPT its own resolver; either way the name just needs registering. If planner prefers `streamed_text` for 1A (since the resolver is inert), register both; behavior is the surviving L3 branch regardless. |
| A2 | Non-prototype per-step `gates` can be declared-but-inert in 1A (gate selection stays in `_should_gate`/`gate_agent_ids`) | D-07 map / pitfalls | LOW — gate dispatch is behavioral (Phase 7). But IF the planner wants the manifest `gates` to be the live source in 1A, they must grep AGENT.md `gate:` to populate per-step gates exactly. Recommend inert for 1A. |
| A3 | `repo_diff` deliverable resolver is NOT needed for clean compile of the 15 manifests | D-07 | LOW — no 1A manifest produces a repo diff; register only if forward-completeness desired. |
| A4 | The coverage test will reuse `_drive` (which pre-resolves agents via `get_pipeline_agents` and forwards the unaliased label) | Validation / MAN-04 | LOW — verified `_drive` already handles od_prototype/ppt alias for lookup; the test just parametrizes over the 13 + `od_prototype`. |
| A5 | "44" in CONTEXT = 41 `pipeline_type` + 3 `spec.id ==` lines | D-09 inventory | LOW — exact greps run this session; behavioral subset is what matters and is fully enumerated. |

## Open Questions

1. **Should the manifest `gates`/`validators` be the LIVE source in 1A or declared-but-inert?**
   - What we know: gate dispatch (`_should_gate`) + validators (`_run_validation_fix_loop`) are behavioral (Phase 7). D-06 says forward fields are inert.
   - What's unclear: whether the planner wants per-step `gates` to drive `_should_gate` already in 1A.
   - Recommendation: **inert in 1A** (lowest parity risk). Populate `gates`/`validators`/`task_source`/`strategy` as data the API-01 endpoint reports, but let the surviving behavioral branches drive actual execution. Revisit in Phase 7.

2. **Does `WorkflowResolver` (resolver.py) validate the compiled Step DAG, or is a separate topo-validate needed?**
   - What we know: `execute()` already calls `self._resolver` and uses `validation.dag` for ordering.
   - What's unclear: whether its DAG model accepts the new `Step` shape.
   - Recommendation: planner reads `resolver.py`; reuse if it fits, else a minimal stdlib topo-check in `compiler.py`. Don't build a second heavy resolver.

3. **`export-pptx` final path under `/api/runs`.**
   - Recommendation (Claude's discretion per D-02): `POST /api/runs/export-pptx` (flat, mirrors the current flat `/api/workflows/export-pptx`) to minimize frontend churn.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` | all backend code/tests | ✓ | 3.11 (project runtime, no venv) | — |
| `PyYAML` (`yaml`) | manifest parsing (MAN-01) | ✓ | 6.0.3 | — |
| `python-frontmatter` | manifest parsing (alt) | ✓ | 1.1.0 | use `yaml.safe_load` |
| `pytest` + `pytest-asyncio` | tests | ✓ | (installed; `tests/agents/` run) | — |
| `import-linter` (`lint-imports`) | hexagonal CI gate | ✓ (configured) | — | — |
| `vulture` | dead-code CI gate | ✓ (configured) | — | — |
| Chromium (`render_check`) | only IF `html_render` validator were live (it is NOT in 1A) | degrades to skip | — | render_check already skips when absent; not exercised in 1A |
| Postgres / Bedrock | NOT needed — `_drive` runs offline (no DB/LLM) | ✓ via scripted model | — | scripted model + `_noop_store` |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none material to Phase 4.

[VERIFIED: `python3.11 -c "import yaml; ... import frontmatter"` both OK; `grep get_user_via_api_key app/` → only handoff.py/mcp.py/settings.py.]

## Validation Architecture

> Nyquist validation enabled (no `workflow.nyquist_validation: false` found). Consumed downstream to build VALIDATION.md.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_<new>.py -x` |
| Full suite command | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MAN-01 | well-formed `workflow.yaml` → populated `WorkflowManifest`; every authored manifest loads clean | unit | `pytest tests/agents/test_manifest.py -x` | ❌ Wave 0 |
| MAN-01 | missing required field → `ManifestValidationError` NAMING the field | unit | `pytest tests/agents/test_manifest.py::test_missing_field_named -x` | ❌ Wave 0 |
| MAN-02 | each authored manifest compiles to a `CompiledWorkflow` whose steps/agents/deliverable/clarify/planner match | unit | `pytest tests/agents/test_compiler.py::test_compiles_clean -x` | ❌ Wave 0 |
| MAN-02 / INV-5 | a manifest with a control-flow construct (`when:`/`if:`/`for:`/`${}`/`{{}}`) is REJECTED | unit | `pytest tests/agents/test_compiler.py::test_rejects_dsl -x` | ❌ Wave 0 |
| MAN-02 / INV-1 | structure test: `compiler.py` source contains NO `pipeline_type`/workflow-name branch | structure | `pytest tests/agents/test_compiler.py::test_no_name_branch -x` (read source, assert no `if pipeline_type`/literal-id `if`) | ❌ Wave 0 |
| MAN-03 / INV-4 | unknown capability ref (e.g. `strategy: nonexistent`) → compile error NAMING the bad ref | unit | `pytest tests/agents/test_compiler.py::test_unknown_capability -x` | ❌ Wave 0 |
| MAN-03 | `base.py` ports + `registry.py` exist; known names registered; all 15 manifests reference only registered names | unit | `pytest tests/agents/test_registry_capabilities.py -x` | ❌ Wave 0 |
| MAN-04 | all 15 manifests load + compile (zero exemptions) | parametrized unit | `pytest tests/agents/test_manifest_coverage.py::test_all_load_compile -x` | ❌ Wave 0 |
| MAN-04 | the 13 dispatchable pipelines (+ `od_prototype` alias) execute from `CompiledWorkflow`; no legacy dispatch fallback | parametrized integration | `pytest tests/agents/test_compiled_plan_runs.py -x` (reuse `_drive`) | ❌ Wave 0 |
| MAN-04 | `reverse_engineer` → empty plan; `chat` compiles but engine does NOT dispatch | unit | `pytest tests/agents/test_edge_manifests.py -x` | ❌ Wave 0 |
| MAN-04 | Phase-0A characterization snapshots stay green (prototype, od_prototype, prototype_revision, ppt/od_ppt, one code-gen) | characterization | `pytest tests/agents/test_characterization_*.py -x` | ✅ exist |
| MAN-04 | `clarify.defaults` per manifest == engine `_pipeline_defaults` dict; `planner` per manifest matches live behavior | unit | `pytest tests/agents/test_manifest_parity.py -x` | ❌ Wave 0 |
| MAN-05 | legacy `pipeline_type` resolves to correct manifest id and runs; `od_prototype`→`prototype` | unit | `pytest tests/agents/test_id_alias_resolver.py -x` | ❌ Wave 0 |
| MAN-05 | grep/structure: `pipeline_type` consumed ONLY by the id-alias resolver for routing; behavioral branches allow-listed | structure | `pytest tests/agents/test_pipeline_type_routing.py -x` (assert the surviving branches match the allow-list; no NEW routing branch) | ❌ Wave 0 |
| API-01 | `GET /api/workflows` lists every authored workflow with metadata | api | `pytest tests/unit/test_workflows_api.py::test_list -x` | ❌ Wave 0 |
| API-01 | `GET /api/workflows/{id}` returns full compiled step configs; 404 on unknown id; `prototype` payload matches its manifest | api | `pytest tests/unit/test_workflows_api.py::test_get_and_404 -x` | ❌ Wave 0 |
| D-01/D-02 | relocated `/api/runs/*` routes serve the old run-history shapes (regression of moved CRUD) | api | `pytest tests/unit/test_runs_api.py -x` | ❌ Wave 0 |
| CI gates | import-linter + migration-ledger + vulture stay green (L1–L13 NOT flipped) | gate | `cd backend && lint-imports && python3.11 -m pytest tests/agents/test_migration_ledger.py -x && vulture app/ agents/` | ✅ exist |

### Sampling Rate
- **Per task commit:** `cd backend && python3.11 -m pytest tests/agents/test_<touched>.py -x`
- **Per wave merge:** `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -x` + `lint-imports` + `vulture app/ agents/`
- **Phase gate:** full suite green + all characterization snapshots green + migration-ledger green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/agents/test_manifest.py` — MAN-01 (load + named-field errors + DSL-key rejection)
- [ ] `tests/agents/test_compiler.py` — MAN-02/INV-1/INV-5 (compile-clean, reject-DSL, no-name-branch, structure)
- [ ] `tests/agents/test_registry_capabilities.py` — MAN-03 (ports exist, names registered)
- [ ] `tests/agents/test_manifest_coverage.py` + `test_compiled_plan_runs.py` + `test_edge_manifests.py` — MAN-04 (reuse `_drive`)
- [ ] `tests/agents/test_manifest_parity.py` — clarify-defaults + planner parity vs. engine dicts
- [ ] `tests/agents/test_id_alias_resolver.py` + `test_pipeline_type_routing.py` — MAN-05
- [ ] `tests/unit/test_workflows_api.py` + `tests/unit/test_runs_api.py` — API-01 + D-01/D-02
- [ ] Framework install: none — pytest already configured.

*Existing infra that already covers part of the phase:* `tests/agents/test_characterization_*.py` (5 snapshots), `tests/agents/test_migration_ledger.py`, the import-linter contract, vulture config.

## Security Domain

> `security_enforcement` not explicitly `false` → included. Phase 4 is a declaration/routing + read-only-metadata phase; it introduces NO new auth surface, NO code-exec, NO secrets.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no change) | Both routers keep `Depends(get_current_user)` (JWT). API-key surface untouched. |
| V3 Session Management | no | unchanged |
| V4 Access Control | yes (preserve) | The moved run-history routes MUST keep the per-user ownership filter `WorkflowRun.user_id == current_user.id` on every query (list/get/delete/chain-context/export-pptx). Do not weaken during relocation. `/api/workflows` definitions are non-sensitive (static manifest metadata) but still JWT-gated for parity. 404 on unknown id (no enumeration leak). |
| V5 Input Validation | yes | Manifest loader rejects unknown keys + validates types (D-08/D-10). `workflow_id` path param on `/api/runs/{id}` keeps the existing `max_length`/UUID handling; `export-pptx` keeps its Pydantic caps + filename `re.sub` sanitization (carry over verbatim — do not regress the HTTP-response-splitting fix at workflows.py:215-221). |
| V6 Cryptography | no | none |

### Known Threat Patterns for {FastAPI + YAML manifests}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| YAML deserialization RCE | Tampering / EoP | Use `yaml.safe_load` (NEVER `yaml.load`/`Loader=FullLoader`). Manifests are repo-authored, but safe_load is mandatory hygiene. |
| Broken object-level authZ on relocated run routes (IDOR) | EoP / Info Disclosure | Preserve the `user_id == current_user.id` filter on `/api/runs/{id}` exactly as in the source handlers. |
| Path traversal via manifest id in `/api/workflows/{id}` | Tampering | Resolve id against the in-memory compiled-manifest registry (a known set), NOT the filesystem path directly; 404 on miss. Never `open(base / id)` with an unvalidated id. |
| HTTP response splitting via export-pptx filename | Tampering | Carry over the existing `re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40]` sanitization verbatim. |
| DSL/expression injection into manifests | Tampering | Strict-key rejection + no eval anywhere in the compiler (INV-5 / D-08). |

## Sources

### Primary (HIGH confidence — in-repo, verified this session)
- `backend/agents/execution_engine/engine.py` (2710 lines) — full D-09 inventory: lines 95, 107, 319, 360, 377, 415, 555, 723-766, 891, 939, 1004, 1356, 1370, 2114, 2428, 2511.
- `backend/agents/registry.py` — `PIPELINE_AGENTS` (15 keys), `_OD_ALIAS_BASE`, `REVISION_BASE_MAP`, `_INTERNAL_PIPELINES`, `allowed_custom_agent_ids`, `get_pipeline_agents`.
- `backend/agents/loader.py` — `AgentSpec`/`AgentSpecError`/`load_agent_spec`/`_build_spec` (the D-10 pattern).
- `backend/agents/prototype/pipeline.py:63` — `SKIP_PLANNER_FOR_PROTOTYPE = False` (the planner-parity finding).
- `backend/app/api/workflows.py` — run-history router (JWT auth; the routes being relocated).
- `backend/app/api/api_key_auth.py` + `grep get_user_via_api_key app/` — D-02 resolution (no external consumer).
- `backend/app/main.py:144-156` — router registration point.
- `backend/tests/agents/_scripted_model.py:325-453` — `_drive` offline harness.
- `backend/tests/agents/test_characterization_prototype.py` (+ od_ppt/od_prototype/prototype_revision/app_builder) — snapshot tests that must stay green.
- `backend/pyproject.toml:131-192` — import-linter + vulture config.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — the CI-asserted ledger (L1–L13 stay `☐`; L7/L10 grep patterns).
- `specs/003-workflow-engine-decoupling/plan.md` §6 (324-516), §10 (572-607), §11 (609-628), §22 (755-772), §30 (921-988), §31 (989-1025), §32 (1027-1098).
- `python3.11` import checks: `yaml` 6.0.3, `frontmatter` OK; `requirements.txt:53` `python-frontmatter==1.1.0`.

### Secondary (MEDIUM confidence)
- `backend/CLAUDE.md` — engine-as-sequencer model, commit scopes, dev runtime, "Adding a Pipeline".
- `backend/app/api/websocket.py:418-435, 950-997` — production alias resolution + dispatch entry (the seam's caller).

### Tertiary (LOW confidence)
- None — all findings are grounded in the in-repo code or the locked plan/spec. No external/training-only claims.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; both parsers verified installed; pattern is an existing in-repo file.
- D-09 classification: HIGH — every line read and classified against the migration-ledger leak map.
- D-07 capability set: HIGH for the minimum set (cross-checked vs. PIPELINE_AGENTS + _resolve_final_output); MEDIUM on `ppt` vs `streamed_text` resolver naming (A1) and per-step `gates` liveness (A2) — both flagged.
- D-02: HIGH — grep-verified no API-key consumer.
- Architecture/pitfalls: HIGH — derived from read code + the locked plan.

**Research date:** 2026-06-07
**Valid until:** 2026-07-07 (stable — brownfield in-repo code; revalidate only if `engine.py`/`registry.py`/`pipeline.py` change before planning).

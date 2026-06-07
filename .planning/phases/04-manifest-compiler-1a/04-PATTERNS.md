# Phase 04: Manifest + Compiler [1A] - Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 11 net-new code/config targets + 3 modified + test targets
**Analogs found:** 11 / 11 (all net-new files have strong in-repo analogs)

All file paths below are absolute. Excerpts are verbatim from the cited analog; line numbers are as-read.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/agents/workflows/manifest.py` | loader/model (config) | file-I/O → transform | `backend/agents/loader.py` | exact (D-10 mirror) |
| `backend/agents/workflows/plan.py` | model (typed dataclasses) | transform | `backend/agents/loader.py::AgentSpec` + `resolver.py` dataclasses | exact |
| `backend/agents/workflows/compiler.py` | service (transform) | transform (resolve + validate DAG) | `backend/agents/execution_engine/resolver.py::WorkflowResolver` + `registry.get_pipeline_agents` | role-match |
| `backend/agents/capabilities/base.py` | port (Protocol/ABC) | n/a (interface) | `backend/agents/execution_engine/resolver.py` dataclass cluster (no Protocol precedent yet) | partial (no exact Protocol port exists) |
| `backend/agents/capabilities/registry.py` | registry | lookup (name validation) | `backend/agents/registry.py` (`PIPELINE_AGENTS` dict + accessors) | role-match |
| `backend/agents/workflows/<id>/workflow.yaml` ×15 | config (hand-authored) | file-I/O input | `backend/agents/prompts/*/AGENT.md` frontmatter + `PIPELINE_AGENTS` (derivation source) | role-match |
| `backend/app/api/workflows.py` (rewritten) | controller (router) | request-response (read-only metadata) | current `backend/app/api/workflows.py` router patterns | exact |
| `backend/app/api/runs.py` (NEW) | controller (router) | request-response (CRUD) | current `backend/app/api/workflows.py` (the routes being relocated) | exact (pure relocation) |
| `backend/app/main.py` (modified) | config (router mount) | n/a | `app/main.py:143-154` `include_router` block | exact |
| `backend/agents/execution_engine/engine.py` (modified — routing seam) | kernel (sequencer) | event-driven (async generator) | the current `execute()` routing call sites | exact (in-place seam) |
| `backend/tests/agents/*` + `backend/tests/unit/*` | test | n/a | `tests/agents/_scripted_model.py::_drive`; `tests/agents/test_characterization_*` | exact |

## Pattern Assignments

### `backend/agents/workflows/manifest.py` (loader/model, file-I/O → transform)

**Analog:** `backend/agents/loader.py` — the canonical typed-config-loader (D-10 says mirror this exactly; do NOT use Pydantic).

**Imports + typed error pattern** (`agents/loader.py:15-23, 105-106`):
```python
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
import frontmatter  # python-frontmatter

class AgentSpecError(Exception):
    """Raised when an AGENT.md file has invalid or missing fields."""
```
Mirror: `class ManifestValidationError(Exception)` — and it MUST name the offending field (SPEC Req 1 / MAN-01). Note manifests are body-less pure YAML, so `yaml.safe_load(path.read_text())` is the cleaner read than `frontmatter.loads` (RESEARCH Standard Stack; both work).

**Dataclass-with-required-then-defaulted pattern** (`agents/loader.py:64-103`):
```python
@dataclass
class AgentSpec:
    # ── Required ──
    id: str
    name: str
    ...
    # ── Optional with defaults ──
    tools: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    ...
    gate: str | None = None
```
Mirror for `WorkflowManifest`: required `id`, `steps`, `deliverable`, `planner`, `clarify`; defaulted `context_providers`, `seed_files`, `version`, plus forward-inert `model`, `limits` (D-06). RESEARCH §"Code Examples" gives the verbatim target shape including `_ALLOWED_TOP_KEYS` strict-key rejection for D-08/INV-5.

**Load + existence-check + parse-then-validate flow** (`agents/loader.py:121-171`):
```python
def load_agent_spec(agent_id: str) -> AgentSpec:
    if agent_id in _SPEC_CACHE:
        return _SPEC_CACHE[agent_id]
    agent_dir = _PROMPTS_DIR / agent_id
    agent_file = agent_dir / "AGENT.md"
    if not agent_dir.exists():
        raise FileNotFoundError(f"Agent directory not found: {agent_dir}")
    ...
    raw_text = agent_file.read_text(encoding="utf-8")
    post = frontmatter.loads(raw_text)
    spec = _build_spec(post.metadata, post.content, agent_file)
    _SPEC_CACHE[agent_id] = spec
    return spec
```
Mirror: `load_manifest(workflow_id, base_dir)` reading `<base_dir>/<id>/workflow.yaml`; existence check raises `FileNotFoundError`, malformed/missing field raises `ManifestValidationError`. The module-level `_SPEC_CACHE` caching idiom (`loader.py:113`) is optional but matches precedent.

**Per-field validation idiom:** reuse the `_build_spec` / `_require_nonempty_str` / `_optional_list_of_str` helper pattern (`loader.py:229-394`, beyond the read window — grep there when authoring). Each raises an `*Error` naming the field — exactly MAN-01's requirement. `steps: []` MUST be permitted (reverse_engineer stub, D-05).

---

### `backend/agents/workflows/plan.py` (model, transform)

**Analog:** `backend/agents/loader.py::AgentSpec` (dataclass-with-defaults idiom, above) + the dataclass cluster in `resolver.py:37-59`.

**Plain-dataclass cluster pattern** (`agents/execution_engine/resolver.py:37-59`):
```python
@dataclass
class DagEdge:
    from_agent_id: str
    to_agent_id: str
    artifact_type: str

@dataclass
class ValidationResult:
    satisfiable: bool
    errors: list[str] = field(default_factory=list)
    dag: list = field(default_factory=list)
    edges: list[DagEdge] = field(default_factory=list)
```
Mirror for `CompiledWorkflow` / `Step` / `Task`: define the **full §6 field set** now (D-06); Phase-4-consumed fields populated (`agent_id`, `strategy` name, `gates` names, `task_source`; workflow-level `steps`, `context_providers`, `seed_files`, `deliverable`, `planner`, `clarify`); forward fields (`model`, `tools`, `validators`, `fix`, `compaction`, `fanout`, `on_conflict`, `retry`, `injects`, `repo`, `limits`) **declared-but-inert** with defaults — no Phase-4 behavior keys off an inert field. Nested forward types may be stub dataclasses or deferred (planner's call, D-06).

---

### `backend/agents/workflows/compiler.py` (service, transform)

**Analog:** `backend/agents/execution_engine/resolver.py::WorkflowResolver` (DAG validation) + `backend/agents/registry.py::get_pipeline_agents` (name→spec resolution).

**Validate-then-return-typed-result pattern** (`resolver.py:67-79`):
```python
class WorkflowResolver:
    def validate(self, agents: list) -> ValidationResult:
        """Compute and validate the Workflow DAG."""
```
RESEARCH "Don't Hand-Roll": reuse `WorkflowResolver`'s DAG/topo validation if it fits the compiled `Step` DAG rather than writing a second validator. The compiler's reference-validation (INV-4) target shape is given verbatim in RESEARCH §"Code Examples" (MAN-02 compiler) — for each step validate `strategy`/`validators`/`gates`/`task_source.parser`/`compaction`, plus workflow-level `context_providers` and `deliverable.strategy`, against the registry; unknown name → `CompilerError` naming the bad ref.

**Constraint (D-08/INV-1):** `compiler.py` must contain **no** `if pipeline_type` / workflow-name literal branch — a structure test asserts this. Contrast with the legacy dispatch it replaces:
```python
# registry.py:238-243 — what the compiler must NOT imitate (name-keyed dispatch)
if pipeline_type not in SUPPORTED_PIPELINE_TYPES:
    return []
```
The compiler is pure data transform: map manifest dicts → `Step`/`Task`, resolve names, topo-validate. No `eval` of any value.

---

### `backend/agents/capabilities/registry.py` (registry, lookup)

**Analog:** `backend/agents/registry.py` (`PIPELINE_AGENTS` module-level dict + accessor functions).

**Module-level data + accessor pattern** (`agents/registry.py:29, 210-215, 223`):
```python
PIPELINE_AGENTS: dict[str, list[str]] = { "user_stories": [...], ... }
REVISION_BASE_MAP: dict[str, str] = { "ppt_revision": "ppt", ... }

def get_pipeline_agents(pipeline_type: str) -> list[AgentSpec]:
    if pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        return []
    ...
```
Mirror: a module-level `_KNOWN: set[tuple[str,str]]` keyed by `(kind, name)` + a `CapabilityRegistry.is_registered(kind, name) -> bool`. The exact name set to register is the **authoritative D-07 set** (RESEARCH §D-07): strategies `single_shot`/`task_loop`; validators `html_static`/`html_render`; deliverable resolvers `single_file`/`serialized_sandbox`/`streamed_text`/`ppt`; context_providers `opendesign`/`previous_run`; task_parser `heading_tasks`; gates `human`/`validation`; compaction `html_skeleton`. Names only — no impls, no trust flags (Phase 8). RESEARCH §"Code Examples" gives the verbatim target.

**Also reuse the alias map (MAN-05):** `registry.py:262-264`:
```python
_OD_ALIAS_BASE: dict[str, str] = {
    "od_prototype": "prototype",
}
```
The id-alias resolver centralizes exactly this (`od_prototype` → `prototype`; identity otherwise). Single source of truth already exists — lift it to a named resolver, don't recreate it.

---

### `backend/agents/capabilities/base.py` (port — Protocol)

**Analog:** No exact `typing.Protocol` port precedent in the codebase (the codebase uses `@dataclass` clusters like `resolver.py:37-59` and plain classes). This is the one **partial** match — follow plan §6/§32 ("ports are `Protocol`") for the structure and the dataclass-docstring style of `resolver.py`/`loader.py` for conventions.

Define Protocol ports: `ExecutionStrategy`, `Validator`, `DeliverableResolver`, `ContextProvider`, `GateHandler`, `TaskParser` (per §6). No bodies/impls (Phase 7). Use `from typing import Protocol` (stdlib).

---

### `backend/agents/workflows/<id>/workflow.yaml` ×15 (config, file-I/O input)

**Analog:** `backend/agents/prompts/*/AGENT.md` frontmatter (the YAML the loader reads) + `PIPELINE_AGENTS` (`registry.py:29-180`) as the **derivation source** for agent lists/order.

**Derivation rule (critical, RESEARCH Pitfall 3):** step order MUST equal `get_pipeline_agents(id)` output order (sorted by `AgentSpec.order`), not author order. Per-manifest content (agents, strategy, deliverable, gates, context_providers, validators, `clarify.defaults`) is fully tabulated in RESEARCH §D-07 "Per-manifest reference map." Edge cases (D-05): `reverse_engineer` → `steps: []`, `description: "agents TBD"`; `chat` → full 7-agent manifest (`chat-discovery`…`chat-preview` per `registry.py:171-179`) that compiles but is never engine-dispatched.

**Two parity traps baked into the manifests:**
- `planner: run` for ALL (not `skip`) — `SKIP_PLANNER_FOR_PROTOTYPE = False` today (RESEARCH Pitfall 1).
- `clarify.defaults` must reproduce the engine dict verbatim — see the exact lists in the engine excerpt under the routing seam below.

---

### `backend/app/api/workflows.py` (REWRITTEN — manifest-definitions router) + `backend/app/api/runs.py` (NEW — relocated run-history)

**Analog:** the current `backend/app/api/workflows.py` router (exact patterns to mirror for both files).

**Router + auth + response_model pattern** (`app/api/workflows.py:6-15, 57-74, 80-108`):
```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

class WorkflowRunResponse(BaseModel):
    id: str
    ...
    model_config = {"from_attributes": True}

@router.get("", response_model=list[WorkflowRunResponse])
def list_workflows(current_user: User = Depends(get_current_user), db: Session = Depends(get_db), ...):
    query = db.query(WorkflowRun).filter(WorkflowRun.user_id == current_user.id)
    ...
```

**404 + per-user ownership filter pattern** (`app/api/workflows.py:230-251`):
```python
@router.get("/{workflow_id}", response_model=WorkflowRunResponse)
def get_workflow(workflow_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    return workflow_run
```

Assignments:
- **`runs.py` (NEW):** `APIRouter(prefix="/api/runs")`; move `list`/`get`/`delete`/`chain-context`/`export-pptx` (`workflows.py:80, 230, 254, 111, ~461`) verbatim — pure relocation, JWT-only (`get_current_user`), no API-key surface (RESEARCH D-02 RESOLVED → no 308 aliases).
- **`workflows.py` (REWRITTEN):** same `APIRouter(prefix="/api/workflows")` + `Depends(get_current_user)` + `HTTPException(404)` idioms, but the data source is the **compiled manifests**, not `WorkflowRun` DB rows. `GET ""` → list of id/name/description/step-summary; `GET /{id}` → full step configs/gates/validators/deliverable/declared-capabilities; 404 on unknown id (API-01).

---

### `backend/app/main.py` (modified — mount the new router)

**Analog:** `app/main.py:143-154` `include_router` block:
```python
# Register routers
app.include_router(auth_router)
...
app.include_router(workflows_router)
```
Add `app.include_router(runs_router)` alongside the now-definitions `workflows_router` (D-02).

---

### `backend/agents/execution_engine/engine.py` (modified — routing seam, MAN-04/MAN-05)

**Analog:** the current `execute()` routing call sites — replace these as the *source* of value; leave behavioral branches byte-identical.

**Planner-skip routing source** (`engine.py:723-724`) — REPLACE source with `CompiledWorkflow.planner`:
```python
from agents.prototype.pipeline import SKIP_PLANNER_FOR_PROTOTYPE, is_prototype_pipeline
skip_planner = SKIP_PLANNER_FOR_PROTOTYPE and is_prototype_pipeline(pipeline_type)
```
Note `SKIP_PLANNER_FOR_PROTOTYPE = False` today → manifests declare `planner: run` (Pitfall 1).

**Clarify-defaults routing source** (`engine.py:752-763`) — REPLACE source with `CompiledWorkflow.clarify.defaults`; manifests must reproduce these EXACT lists:
```python
_pipeline_defaults: dict[str, list[str]] = {
    "od_ppt":        ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "ppt":           ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "od_prototype":  ["target_audience", "scope", "priority", "style"],
    "prototype":     ["target_audience", "scope", "priority", "style"],
    "user_stories":  ["target_audience", "scope", "priority", "technology"],
    "app_builder":   ["technology", "scope", "target_audience", "security"],
    "mulesoft_to_springboot": ["scope", "technology", "timeline", "priority"],
    "dotnet_to_azure":        ["scope", "technology", "timeline", "priority"],
    "custom":        ["target_audience", "key_objectives", "scope", "priority"],
}
defaults = _pipeline_defaults.get(pipeline_type, _pipeline_defaults["custom"])
```

**Agent-list routing source** (`engine.py:705`, `get_pipeline_agents` upstream) — sequence/agent_ids now come from `CompiledWorkflow.steps[*].agent_id`. Add a 1A assertion `[s.agent_id for s in plan.steps] == [a.id for a in get_pipeline_agents(id)]` (RESEARCH Runtime State caution).

**SURVIVING behavioral branches — DO NOT touch text** (allow-list for Phase 7). The deliverable-by-class chooser is the canonical example (`engine.py:319-388`):
```python
def _resolve_final_output(pipeline_type, sandbox, results, *, revision_original_html=None) -> str:
    ...
    if pipeline_type == "prototype_revision":      # BEHAVIORAL L2/L9 — survives
        ...
    if pipeline_type in _PROTOTYPE_PIPELINE_TYPES: # BEHAVIORAL L2/L9 — survives
        ...
```
Full survives/routing/pass-through classification of all 41 `pipeline_type` + 3 `spec.id ==` occurrences is in RESEARCH §D-09. Critical: the L10 line `if pipeline_type in ("od_prototype","prototype"):` (engine.py:1356) and L7 `spec.id == "prototype-build"` (engine.py:~891) are pinned by migration-ledger grep patterns — leave their exact spelling untouched (Pitfall 4). `accumulated_outputs` mirror unchanged (L15).

---

### Tests (`backend/tests/agents/*`, `backend/tests/unit/*`)

**Analog:** `tests/agents/_scripted_model.py::_drive` (offline end-to-end engine harness) + `tests/agents/test_characterization_*` snapshots.

**Coverage-test harness reuse** (`tests/agents/_scripted_model.py:325-355`):
```python
async def _drive(pipeline_type: str, world: str = "new") -> list[dict]:
    ...
    _OD_ALIAS_FOR_LOOKUP = {"od_prototype": "prototype", "ppt": "od_ppt"}
    _lookup_type = _OD_ALIAS_FOR_LOOKUP.get(pipeline_type, pipeline_type)
    engine_mod.ALWAYS_CLARIFY = False
    specs = get_pipeline_agents(_lookup_type)
```
Reuse `_drive` for the MAN-04 parametrized coverage test (the 13 dispatchable pipelines + `od_prototype` alias run from `CompiledWorkflow`). The harness already handles od-alias lookup, RUNS_ROOT temp dir, and ALWAYS_CLARIFY=False. Add: (1) all-15 load+compile test; (2) D-08 control-flow-rejection test; (3) INV-1 structure test (no `pipeline_type`/name branch in `compiler.py`); (4) unit test asserting `compiled.clarify.defaults` == the engine dict per pipeline (Pitfall 2, NOT caught by the offline snapshot).

## Shared Patterns

### Typed-error-naming-the-field (MAN-01)
**Source:** `backend/agents/loader.py:105-106` (`AgentSpecError`) + the `_build_spec` per-field checks.
**Apply to:** `manifest.py` (`ManifestValidationError`), `compiler.py` (`CompilerError`). Every validation failure names the offending field/reference.

### Dataclass-not-Pydantic (D-10 / §6 / §32)
**Source:** `backend/agents/loader.py:64-103`, `resolver.py:37-59`.
**Apply to:** `manifest.py`, `plan.py`, any nested forward types. `@dataclass` with required fields first, defaulted fields second (`field(default_factory=...)`). Pydantic is used only at the API boundary (`workflows.py` response models), never for manifests.

### FastAPI router: prefix + JWT auth + 404 + ownership filter
**Source:** `backend/app/api/workflows.py:15, 80-108, 230-251`.
**Apply to:** both `runs.py` and the rewritten `workflows.py`. `APIRouter(prefix=...)`, `Depends(get_current_user)`, `HTTPException(status.HTTP_404_NOT_FOUND, ...)`, `.filter(... .user_id == current_user.id)` for run-scoped reads.

### od_prototype id-alias resolution (MAN-05)
**Source:** `backend/agents/registry.py:262-264` (`_OD_ALIAS_BASE`); also `_scripted_model.py:354` (`_OD_ALIAS_FOR_LOOKUP`).
**Apply to:** the run-entry id-alias resolver and the capability registry's resolver. `od_prototype` → `prototype`; every real key → itself.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/agents/capabilities/base.py` | port (Protocol) | n/a | No `typing.Protocol` port precedent exists in the codebase (it uses `@dataclass` clusters + plain classes). Follow plan §6/§32 ("ports are `Protocol`") for structure; borrow docstring/convention style from `loader.py`/`resolver.py`. Partial-match only. |

## Metadata

**Analog search scope:** `backend/agents/` (loader, registry, resolver, execution_engine/engine), `backend/app/api/` (workflows, main), `backend/tests/agents/`.
**Files read for excerpts:** `agents/loader.py`, `agents/registry.py`, `agents/execution_engine/resolver.py`, `agents/execution_engine/engine.py` (targeted ranges 319-388, 700-774), `app/api/workflows.py` (1-130, 225-284), `app/main.py` (140-154), `tests/agents/_scripted_model.py` (325-384).
**Pattern extraction date:** 2026-06-07

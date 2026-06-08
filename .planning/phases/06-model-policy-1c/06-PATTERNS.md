# Phase 6: Model Policy [1C] - Pattern Map

**Mapped:** 2026-06-08
**Files analyzed:** 13 (2 net-new, 10 grows, 1 test-helper)
**Analogs found:** 13 / 13 (all in-repo; net-new modules grounded on existing same-layer patterns)
**Line-anchor drift vs CONTEXT/RESEARCH:** NONE — every cited file:line verified exact this session (see § Anchor Verification).

> All patterns below are concrete copy-from excerpts at verified line numbers. The planner's
> `<read_first>` should cite the analog file:line; `<action>` should mirror the excerpt shape.
> Two cross-cutting rules (import-purity typing, allow-list validation) are in § Shared Patterns.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `agents/model_policy.py` (NEW) | service (kernel resolver) | transform (precedence resolution) + event-driven (throttle advance) | `agents/authz.py::ScopedStore` (per-run kernel helper) + `agents/execution_engine/context.py::scoped_store` typing | role-match (new kernel service; no exact resolver analog) |
| `agents/capabilities/model_catalog.py` (NEW) | model (pure-data catalog) | CRUD (list/get/ids/is_allowed over static data) | `app/api/settings.py::AVAILABLE_MODELS` (the seed list) + `agents/capabilities/registry.py::_KNOWN` (kernel-pure data module) | role-match (data module; no behavior-port analog) |
| `agents/execution_engine/context.py` | config (dataclass state) | n/a (state container) | `context.py::scoped_store` (line 82) — same file, exact precedent | exact |
| `app/agents/model_factory.py` | factory (model builder) | request-response (build a client) | itself — extend in place (single source) | exact (self) |
| `agents/execution_engine/engine.py` | controller (sequencer) | event-driven (per-agent loop) | itself — `execute()` 537/608, `_run_agent` model sites 1286/1560/2033, record_capabilities 738 | exact (self) |
| `agents/loader.py` | utility (frontmatter parser) | transform (YAML→AgentSpec) | `loader.py` `description` optional-string (325-335) + `gate` (342-354) | exact (same-file pattern) |
| `agents/factory.py` | factory (runner builder) | request-response | `factory.py::AgentContext.model` (44) + `create_runner` (155) — already correct, no signature change | exact (self) |
| `app/api/settings.py` | route (FastAPI settings) | request-response | `settings.py::AVAILABLE_MODELS` (40-71) — becomes projection | exact (self) |
| `app/api/websocket.py` | route (WS ingress) | request-response (payload validation) | `websocket.py` payload reads (418-428) + error-event shape (438-442) + execute call (1142) | exact (self) |
| `agents/authz.py` | service (scoped persistence) | CRUD (DB insert) | `authz.py::record_capabilities` (452-487) — already accepts `model_overrides` via `**deferred` | exact (no change needed) |
| `app/models/run_capabilities.py` | model (ORM) | CRUD | `run_capabilities.py:31` `model_overrides` column — already exists | exact (confirm-only) |
| `agents/workflows/plan.py` | model (dataclass) | n/a | `plan.py::ModelPolicy` (64-71), `Step.model` (209), `CompiledWorkflow.model` (248) — already correct, read-only consumption | exact (no change) |
| `tests/agents/_scripted_model.py` | test (scripted BaseChatModel) | event-driven (stream) | `ScriptedFakeChatModel` (86-155) — extend to raise a throttle | exact (extend) |

---

## Pattern Assignments

### `agents/model_policy.py` (NEW — service, transform + event-driven)

**Analog A — kernel per-run helper, import-pure carry:** `agents/execution_engine/context.py:82`
```python
# scoped_store: typed object|None so the pure-data context module stays free of the
# helper's app.models import. ModelResolver rides on ctx the SAME way.
scoped_store: object | None = None
```
The resolver is built at `execute()` entry and stored on `ectx.model_resolver` (typed `object | None`).

**Analog B — precedence resolution shape (from RESEARCH § Code Examples, parity-critical):**
```python
def resolve(self, spec, step=None) -> str:
    return (
        self._overrides.get(spec.id)                            # 1 user override
        or (step.model.model if step and step.model else None)  # 2 step.model
        or getattr(spec, "model", None)                         # 3 AgentSpec.model (D-09)
        or (self._workflow_model.model if self._workflow_model else None)  # 4 workflow.model
        or self._session_model_id                               # 5a session model_id
        or self._haiku_default                                  # 5b global Haiku
    )
# overrides={} + all tiers None → session_model_id or Haiku == today's build_model input. INV-3 ✔
```
Seed tier 5b from `settings.BEDROCK_INFERENCE_PROFILE_ID` (read in the resolver, NOT the catalog — keeps catalog kernel-pure; see Pitfall 3 in RESEARCH).

**Imports the resolver MAY make (import-linter VERIFIED — no contract restricts `agents/model_policy.py`):**
- `from agents.workflows.plan import ModelPolicy` (for `CompiledWorkflow.model`/`Step.model`)
- `from agents.capabilities.model_catalog import ModelCatalog`
- `from app.core.config import settings` (Haiku default) — allowed; this module is not under `agents.capabilities`.

**Co-locate `_is_transient_throttle(exc)` here** (RESEARCH MUST-RESOLVE #7) — both the engine retry and the test import one predicate. Defensive layered predicate (type-name OR HTTP-status OR error-code/message substring):
- Bedrock/botocore: `ClientError` code ∈ `{ThrottlingException, TooManyRequestsException, ServiceUnavailableException, InternalServerException, ModelTimeoutException, ServiceQuotaExceededException}`; status 429/503/500.
- ChatAnthropic: `RateLimitError` (429) / overloaded (529).
- Non-matching (ValidationException, AccessDenied, ModelConfigurationError) → propagate, no switch.

**Chain derivation (N11 tier-descent):** empty `ModelPolicy.fallback` → Opus→[Sonnet,Haiku], Sonnet→[Haiku], Haiku→[]. Explicit `fallback` overrides. Every entry must be catalog-valid.

---

### `agents/capabilities/model_catalog.py` (NEW — model, CRUD)

**Analog — the seed list to convert into the single source:** `app/api/settings.py:40-71`
```python
AVAILABLE_MODELS = [
    {"id": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",  "name": "Claude Haiku 4.5",  "description": "Fastest and most cost-efficient. Great for high-volume tasks.", "tier": "fast"},
    {"id": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0", "name": "Claude Sonnet 4.5", "description": "Balanced speed and intelligence. Ideal for most pipelines.",       "tier": "balanced"},
    {"id": "eu.anthropic.claude-sonnet-4-6",               "name": "Claude Sonnet 4.6", "description": "Best combination of speed and intelligence. 1M token context.",     "tier": "balanced"},
    {"id": "eu.anthropic.claude-opus-4-5-20251101-v1:0",   "name": "Claude Opus 4.5",   "description": "Most powerful. Best for complex reasoning and coding tasks.",      "tier": "powerful"},
    {"id": "eu.anthropic.claude-opus-4-6-v1",              "name": "Claude Opus 4.6",   "description": "Most intelligent broadly available model. Exceptional coding.",   "tier": "powerful"},
]
```
**Catalog entry field set (D-04, MODEL-04):** each model carries `id`, `label` (= `name`), `description`, `tier` (legacy/display, KEEP), `cost_class` (new), `provider`, `context_window`, `user_allowed`. Field map:

| id | label | tier | cost_class | provider | user_allowed |
|----|-------|------|-----------|----------|--------------|
| `…haiku-4-5-20251001-v1:0` | Claude Haiku 4.5 | `fast` | `cheap` | bedrock | true |
| `…sonnet-4-5-20250929-v1:0` | Claude Sonnet 4.5 | `balanced` | `standard` | bedrock | true |
| `…sonnet-4-6` | Claude Sonnet 4.6 | `balanced` | `standard` | bedrock | true |
| `…opus-4-5-20251101-v1:0` | Claude Opus 4.5 | `powerful` | `premium` | bedrock | true |
| `…opus-4-6-v1` | Claude Opus 4.6 | `powerful` | `premium` | bedrock | true |

`context_window` exact numerics are **[ASSUMED]** (RESEARCH A1: codebase has no numbers; e.g. 200000 default, 1000000 for Sonnet 4.6 — confirm or populate descriptively; does not block resolution/fallback which key off id/cost_class). `tier`↔`cost_class` must be asserted consistent: fast↔cheap, balanced↔standard, powerful↔premium. All `user_allowed=true`, no gate (N11).

**Exposes:** `list()`, `get(id)`, `is_allowed(id)`, `ids()`.

**Import-purity rule (import-linter VERIFIED, contract `pyproject.toml:165-169`):** this module is under `agents.capabilities` → **MUST NOT import `app.*`** (`forbidden_modules = ["agents.execution_engine", "app"]`). It is self-contained model data. Do NOT reach for `app.core.config` here.

**No new Protocol** in `base.py` — ports there are *behavior* (TaskParser.parse / ExecutionStrategy.run / Validator.validate); a catalog is *pure data*. Concrete class only.

---

### `agents/execution_engine/context.py` (config — exact same-file precedent)

**Analog (line 82, verbatim):**
```python
scoped_store: object | None = None
```
**Add identically (same import-purity reason — no new import):**
```python
model_resolver: object | None = None                 # ModelResolver, typed object → no inbound import
model_overrides: dict = field(default_factory=dict)  # validated {agent_id → model_id}, seeded at entry
```
Module imports today are ONLY stdlib + `agents.artifacts.graph` (lines 25-37) — preserve that.

---

### `app/agents/model_factory.py` (factory — extend in place, do NOT fork)

**Current signature + body (lines 29-80, single source):**
```python
def build_model(model: str | None = None, *, max_tokens: int | None = None) -> "BaseChatModel":
    if max_tokens is None:
        max_tokens = settings.MAX_OUTPUT_TOKENS
    if settings.ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic
        model_id = model or settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5-20251001"
        return ChatAnthropic(model=model_id, api_key=settings.ANTHROPIC_API_KEY, max_tokens=max_tokens)
    from botocore.config import Config
    from langchain_aws import ChatBedrockConverse
    model_id = model or settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID
    # ...
    return ChatBedrockConverse(
        model=model_id, region_name=region, max_tokens=max_tokens,
        config=Config(read_timeout=600, connect_timeout=30,
                      retries={"max_attempts": 5, "mode": "adaptive"}),  # ← botocore retries STAY
    )
```
**Action constraint:** keep this as the single per-id client builder. Do NOT fork provider selection or botocore retries. Under APPROACH B the model-switch lives in the engine, NOT here — so `build_model` may stay **unchanged** (RESEARCH § Recommended Structure marks it UNCHANGED). `max_tokens` stays doc-only (already defaults to `MAX_OUTPUT_TOKENS`; a `ModelPolicy.max_tokens` must NOT raise this cap — MODEL-02 acceptance).

---

### `agents/execution_engine/engine.py` (controller — execute() + _run_agent rewire + APPROACH B)

**1. `execute()` + `_execute_impl` signatures (537-552, 608-623) — BOTH gain the param; forward at 576-590:**
```python
async def execute(self, agents, user_message, pipeline_run_id, pipeline_type="custom",
                  cancel_event=None, user_id=None, session_id=None,
                  attached_skills=None, attached_hooks=None, model_id=None,
                  od_context=None, gate_agent_ids=None, parent_run_id=None):  # ← add model_overrides=None
    ...
    async for event in self._execute_impl(..., parent_run_id=parent_run_id, _sink=sink):  # ← add model_overrides=model_overrides
```
Add `model_overrides: dict[str, str] | None = None` to both signatures and the forward call.

**2. Resolver construction + persist at entry (738-740, verbatim current call):**
```python
await scoped_store.record_capabilities(
    pipeline_run_id, runtime="langchain_deepagents"
)
```
**Rewire to (D-08, `{}`→NULL for parity):**
```python
await scoped_store.record_capabilities(
    pipeline_run_id, runtime="langchain_deepagents",
    model_overrides=(ectx.model_overrides or None),
)
```
Construct the resolver near here into `ectx.model_resolver` (seed: overrides, `CompiledWorkflow.model`, session `model_id`, Haiku default).

**3. The three `_run_agent` model-set sites (VERIFIED model=model_id at):**
```python
# engine.py:1560 — primary AgentContext (verbatim context):
ctx = AgentContext(
    user_request=user_message,
    agent_outputs=self._filter_consumed_outputs(spec, ordered_agents, ectx),
    attached_skills=merged_skills,
    attached_hooks=list(attached_hooks or []),
    model=model_id,                       # ← rewire: ectx.model_resolver.resolve(spec, step)
    ...
)
# engine.py:1286 — revision path AgentContext (model=model_id)
# engine.py:2033 — validation fix-loop AgentContext (model=model_id)
```
All three `model=model_id` become the resolved id. `factory.py:155 model=ctx.model` is UNCHANGED — `ctx.model` now carries the resolved id (INV-13: reaches the graph only through `build_model`).

**4. SmartPlanner — LEAVE on session model_id (engine.py:1432, VERIFIED):**
```python
planner = SmartPlanner(model_id=model_id)   # ← do NOT route through resolver (no agent_id; builds own client; parity)
```

**5. APPROACH B fallback loop** (the one genuinely new mechanism — RESEARCH MUST-RESOLVE #1, VERDICT B / sub-option B1):
- Wrap the engine-level per-agent consume (`async for event in agent.astream_events(...)`, engine.py:1634).
- The runner currently SWALLOWS model exceptions into `{"type":"error"}` (`deep_agent_runner.py:451-455`) and the engine ignores `error` events (engine.py:1637-1673). **B1:** make the runner re-raise classified `_is_transient_throttle` matches (the runner docstring already flags "promote to raise", deep_agent_runner.py:307,453). Engine catches → `ctx.model_resolver.advance()` → rebuild via `create_runner` (next id) → re-invoke, bounded by `len(chain)`. Exhaustion re-raises last error.
- Rebuild via `create_runner` keeps the banned-pattern gate green (no new `create_deep_agent`).
- Reset `output_chunks` between attempts; pre-first-token throttle restarts clean (common case); mid-stream re-streams (Pitfall 4).

---

### `agents/loader.py` (utility — optional frontmatter field, exact same-file pattern)

**Analog — `description` optional-string (325-335) and `gate` (342-354):**
```python
raw_description = metadata.get("description")
if raw_description is not None and not isinstance(raw_description, str):
    raise AgentSpecError(f"Invalid field 'description' in {file_path_str}: expected a string or null, got {type(raw_description).__name__!r}")
```
**1. `AgentSpec` dataclass (after `injects`, line 102) — add:**
```python
model: str | None = None   # optional AGENT.md model id (D-09); absent → None
```
**2. `_build_spec` parse (alongside 325-335) — add:**
```python
raw_model = metadata.get("model")
if raw_model is not None and not isinstance(raw_model, str):
    raise AgentSpecError(f"Invalid field 'model' in {file_path_str}: expected a string or null, got {type(raw_model).__name__!r}")
model: str | None = raw_model
```
**3. Constructor call (356-374) — add `model=model,`.**

Optional load-time catalog validation (`model in ModelCatalog.ids()`) is import-clean (loader is not under `agents.capabilities`/`workflows`) — RESEARCH A3; or defer to resolve-time (both acceptable per D-09). No existing AGENT.md declares `model` → absent=None → loader schema test stays green for all ~80 agents.

---

### `agents/factory.py` (factory — NO change; confirm pass-through)

**VERIFIED already correct:**
```python
# factory.py:44 — AgentContext
model: str | None = None                   # User-selected model ID (overrides system default)
# factory.py:155 — create_runner
model=ctx.model,                           # ← now carries the resolved id, unchanged
```
No signature change. The resolved id flows `ectx.model_resolver.resolve()` → `AgentContext.model` (engine.py:1560) → here → `DeepAgentRunner(model=ctx.model)` → `build_model`.

---

### `app/api/settings.py` (route — derive AVAILABLE_MODELS from catalog, INV-12)

**Current (40-74) — the literal list + derived id set.** **Rewire to a projection (RESEARCH § Code Examples):**
```python
from agents.capabilities.model_catalog import ModelCatalog   # app→kernel: ALLOWED
AVAILABLE_MODELS = [
    {"id": m.id, "name": m.label, "description": m.description, "tier": m.tier}
    for m in ModelCatalog().list()
]   # shape == frontend ModelOption {id,name,description,tier} — UNCHANGED
_VALID_MODEL_IDS = set(ModelCatalog().ids())
```
Frontend `ModelOption` requires EXACTLY `{id, name, description, tier}` with `tier ∈ {fast,balanced,powerful}` (VERIFIED `frontend/src/lib/api.ts:394-399`) — the projection drops the catalog's extra fields. After this, grep must show the model-id list in exactly ONE place (`model_catalog.py`) — INV-12.

---

### `app/api/websocket.py` (route — model_overrides ingress + validation)

**Analog 1 — payload read (418-428, verbatim):**
```python
agent_ids = message_data.get("agent_ids")
attached_skills = message_data.get("attached_skills") or []
gate_agent_ids = message_data.get("gate_agent_ids")
```
**Add identically:** `model_overrides = message_data.get("model_overrides") or {}` (absent → `{}`; frontend doesn't send it until Phase 8).

**Analog 2 — error-event shape (438-442, verbatim) — reuse for invalid override:**
```python
await websocket.send_json({
    "type": "error", "chunk": None, "section": None,
    "data": {"error": reason, "code": "tier_limit", "recoverable": False, "upgrade_required": True},
})
continue
```
**Reuse with** `"code": "invalid_model_override"` for: `model_id ∉ ModelCatalog.ids()` (Q2 allow-list) OR `agent_id ∉ run agents`. Send BEFORE `engine.execute`, then `continue` (reject, no run).

**Analog 3 — execute call (1142-1158, verbatim relevant line):**
```python
model_id=getattr(user, "preferred_model", None) or None,
```
**Add** `model_overrides=model_overrides,` to this `engine.execute(...)` call. (The revision path at websocket.py:662 is a separate execute — Phase 6 threads only the main `run_pipeline`; revision overrides are a follow-up per RESEARCH Open Q2.)

---

### `agents/authz.py` (service — NO change; already accepts the field)

**VERIFIED (452-487):** `record_capabilities(self, run_id, runtime, **deferred)` already maps `model_overrides=deferred.get("model_overrides")` onto the row (line 475). No signature change — the engine just passes `model_overrides=…` (see engine.py:738 rewire above). Row inserted **at entry** (engine.py:738), and `model_overrides` is known at entry → correct.

---

### `app/models/run_capabilities.py` (model — confirm-only, NO migration)

**VERIFIED (line 31):**
```python
model_overrides = Column(JSON, nullable=True)    # Phase 6
```
Created in migration 0014 (head is 0015). `run_capabilities` already carries `owner_id` + `workspace_id` (lines 28-29). **No new migration** (Q3 additive-only satisfied).

---

### `agents/workflows/plan.py` (model — READ-only this phase, NO change)

**VERIFIED already correct:**
```python
# plan.py:64-71
@dataclass
class ModelPolicy:
    model: str | None = None
    max_tokens: int | None = None
    cost_class: str = "standard"
    fallback: list[str] = field(default_factory=list)
# plan.py:209   Step.model: ModelPolicy | None = None
# plan.py:248   CompiledWorkflow.model: ModelPolicy = field(default_factory=ModelPolicy)
```
The resolver READS `Step.model` (tier 2) and `CompiledWorkflow.model` (tier 4). All None/default in manifests today → inert until Phase 7 authors them. No field churn.

---

### `tests/agents/_scripted_model.py` (test — extend with a throttle-raising variant)

**Analog — `ScriptedFakeChatModel` (86-155):** `bind_tools` no-op (100-101), `_stream` (110-144), `_generate` (146-155). The model node calls `ainvoke` → `_generate` (RESEARCH #1 evidence).

**Extend (D-06 simulated-fallback test, no live Bedrock):** add a variant/flag so that, when constructed for model-id A, `_generate`/`_stream` **raises** the throttle exception; model-id B streams normally. Inject A then B via a two-entry chain. APPROACH B drives the retry at the engine level (rebuild via `create_runner` with next id), so the test exercises: throttle on chain[0] → engine advances → rebuild with chain[1] → completes; and a second test where every entry throttles → last error re-raised. Tests force InMemory checkpointer + temp `RUNS_ROOT` (already standard, lines 53-57).

---

## Shared Patterns

### Import-purity carry (typed `object | None`)
**Source:** `agents/execution_engine/context.py:82` (`scoped_store: object | None = None`)
**Apply to:** `model_resolver` on `ExecutionContext`. Any kernel helper that holds run-level inputs and would otherwise pull an `app.*`/DB import rides on ctx typed `object | None` to keep the pure-data context module import-free.

### Allow-list validation (Q2 trust)
**Source:** the catalog `ids()` set; reject pattern modeled on websocket error-event (`websocket.py:438-442`)
**Apply to:** `model_overrides` ingress (websocket — `model_id ∈ ModelCatalog.ids()` AND `agent_id ∈ run agents`) AND AGENT.md `model` (loader load-time or resolver resolve-time). Never accept an arbitrary model string — only catalog ids.

### Optional frontmatter field (loader per-field)
**Source:** `agents/loader.py:325-335` (description) / `342-354` (gate)
**Apply to:** the new `model` field — `metadata.get(...)` → isinstance(str) guard or `AgentSpecError` → default None → pass to `AgentSpec(...)`.

### Name-only capability membership (Phase-4 D-07)
**Source:** `agents/capabilities/registry.py:36-51` (`_KNOWN` set) + docstring at line 27
**Apply to:** add `("model_catalog", "default")` to `_KNOWN` (pure membership; no instance, no `@register`, no trust). **Update the docstring count** at registry.py:27 ("authoritative 14" → 15). `is_registered` (62-64) stays a pure set-membership check.

### Persist-at-entry via ScopedStore (owner+workspace-scoped)
**Source:** `agents/authz.py:452-487` + call site `engine.py:738`
**Apply to:** `model_overrides` write — pass `model_overrides=(ectx.model_overrides or None)` to the existing entry call (`{}`→NULL preserves legacy-row parity, INV-3).

---

## No Analog Found

Two net-new modules have no exact same-role analog (no resolver/catalog exists yet); both are grounded on same-layer patterns above, NOT RESEARCH-only:

| File | Role | Data Flow | Grounding |
|------|------|-----------|-----------|
| `agents/model_policy.py` | service | transform + event-driven | Kernel-helper carry (`scoped_store` typing) + precedence skeleton (RESEARCH § Code Examples) + co-located `_is_transient_throttle`. No prior resolver in repo. |
| `agents/capabilities/model_catalog.py` | model | CRUD | Seeded from `AVAILABLE_MODELS` (settings.py:40-71); kernel-pure data-module shape like `registry.py::_KNOWN`. No prior catalog/data-port in repo. |

The genuinely-new mechanism (no analog at all): the **APPROACH B engine-level rebuild-and-retry loop** — there is no existing model-switch in the codebase. It is built from the existing `astream_events` consume (engine.py:1634), the runner swallow (deep_agent_runner.py:451-455), and `create_runner` rebuild.

---

## Anchor Verification (drift check)

Every CONTEXT/RESEARCH file:line anchor re-verified against current code this session — **zero drift:**

| Anchor | Cited | Verified |
|--------|-------|----------|
| `context.py` scoped_store | 82 | ✓ 82 |
| `registry.py` _KNOWN / "14" docstring | 36-51 / 27 | ✓ 36-51 / 27 ("authoritative 14") |
| `model_factory.py` build_model | 29 | ✓ 29-80 |
| `loader.py` AgentSpec / description / gate / ctor | 64 / 325-335 / 342-354 / 356-374 | ✓ all exact |
| `factory.py` AgentContext.model / create_runner | 44 / 155 | ✓ 44 / 155 |
| `plan.py` ModelPolicy / Step.model / CompiledWorkflow.model | 64-71 / 209 / 248 | ✓ all exact |
| `authz.py` record_capabilities | 452-487 (model_overrides at 475) | ✓ exact |
| `settings.py` AVAILABLE_MODELS / _VALID_MODEL_IDS | 40-71 / 74 | ✓ exact |
| `websocket.py` payload reads / error shape / execute call | 418-428 / 438-442 / 1142-1158 (model_id 1154) | ✓ exact |
| `run_capabilities.py` model_overrides column | 31 | ✓ 31 (+ owner_id 28 / workspace_id 29) |
| `engine.py` execute()/_execute_impl / record_capabilities / model sites / SmartPlanner | 537/608 / 738 / 1286,1560,2033 / 1432 | ✓ all exact (grep-confirmed `model=model_id` at 1286,1560,2033; `SmartPlanner(` at 1432) |
| `_scripted_model.py` ScriptedFakeChatModel | 86-155 | ✓ exact |

---

## Metadata

**Analog search scope:** `backend/agents/` (execution_engine, capabilities, workflows, loader, factory, authz), `backend/app/agents/`, `backend/app/api/`, `backend/app/models/`, `backend/tests/agents/`.
**Files scanned/read:** 13 target files at cited anchors + import-linter contract (pyproject.toml, per RESEARCH).
**Pattern extraction date:** 2026-06-08

## PATTERN MAPPING COMPLETE

**Phase:** 6 - Model Policy [1C]
**Files classified:** 13
**Analogs found:** 13 / 13

### Coverage
- Files with exact analog: 11 (same-file/self or exact precedent)
- Files with role-match analog: 2 (the net-new resolver + catalog)
- Files with no analog: 0 (the 2 net-new are grounded on same-layer patterns; only the APPROACH B retry loop is a net-new mechanism, built from existing seams)

### Key Patterns Identified
- Kernel per-run helpers ride on `ExecutionContext` typed `object | None` to keep the pure-data context module import-free (`scoped_store` precedent → `model_resolver`).
- Single-source-derive (INV-12): `ModelCatalog` owns model data; `AVAILABLE_MODELS`/`_VALID_MODEL_IDS` become projections; `agents.capabilities.model_catalog` must NOT import `app.*` (import-linter).
- Name-only capability membership (Phase-4 D-07): `_KNOWN += ("model_catalog","default")`, no instance/trust until Phase 8.
- Optional frontmatter field via the loader's per-field guard pattern (`description`/`gate` → `model`).
- Persist-at-entry via the existing owner+workspace-scoped `ScopedStore.record_capabilities` (already accepts `model_overrides`; `{}`→NULL for INV-3 parity).
- Fallback = **APPROACH B** engine-level rebuild-and-retry (NOT `with_fallbacks` — it does not compose through the deepagents graph); `build_model` stays the unchanged single source.

### Line-Anchor Drift
NONE — all 13 anchors verified exact this session.

### File Created
`.planning/phases/06-model-policy-1c/06-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can reference exact analog file:line in every `<read_first>`/`<action>`.

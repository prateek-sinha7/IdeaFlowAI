# Phase 6: Model Policy [1C] - Research

**Researched:** 2026-06-08
**Domain:** Brownfield engine refactor — per-agent model resolution, model-switch fallback, capability-as-data catalog (Python · FastAPI · LangChain deepagents · PostgreSQL)
**Confidence:** HIGH (every locked decision grounded in current code at file:line; the one high-risk binary D-05 resolved empirically against the installed library stack)

## Summary

Phase 6 makes the inert Phase-4/5 model-policy scaffolding live. The design (D-01..D-09) is LOCKED; this research grounds each decision in the actual codebase and **resolves the one high-risk binary (D-05)** that decides plan task granularity. All target files were read; the green baseline for every CI gate (loader schema, banned-pattern, migration-ledger, run_capabilities, migration_0014, import-linter) was verified by running them.

**The decisive finding is D-05 → APPROACH B.** `RunnableWithFallbacks` (the object `build_model().with_fallbacks(...)` returns) does **not** expose `bind_tools` `[VERIFIED: python repl — RunnableWithFallbacks has bind_tools: False]`, but the langchain agent factory unconditionally calls `request.model.bind_tools(...)` `[VERIFIED: langchain/agents/factory.py:1249,1274,1283]` and invokes the model with `await model_.ainvoke(messages)` `[VERIFIED: langchain/agents/factory.py:1351]`. Passing a `RunnableWithFallbacks` into `create_deep_agent(model=...)` raised during graph assembly in an empirical test `[VERIFIED: python repl — create_deep_agent(model=wrapped) → error in fallbacks.__getattr__]`. Independently, the `DeepAgentRunner.astream_events` loop **swallows every model exception** into a `{"type":"error"}` event rather than raising `[VERIFIED: app/agents/deep_agent_runner.py:451-455]`, and the engine's consumer loop ignores `error` events entirely `[VERIFIED: agents/execution_engine/engine.py:1637-1673]`. So a `with_fallbacks` seam cannot compose through the deepagents graph as a drop-in, and even a swallowed throttle never surfaces to a fallback. **Use APPROACH B:** an engine-level rebuild-and-retry wrapper in `_run_agent` that classifies the throttle, advances `ctx.model_resolver` to the next chain id, rebuilds via `create_runner`, and re-invokes — bounded by chain length.

**Primary recommendation:** Build `ModelResolver` in a new kernel module `agents/model_policy.py` (carried on `ExecutionContext.model_resolver: object | None`); build `ModelCatalog` as pure data in `agents/capabilities/model_catalog.py` (kernel-pure, no `app.*`); refactor `app/api/settings.py::AVAILABLE_MODELS` into a derived projection over the catalog; thread `model_overrides` through `execute()` and the websocket `run_pipeline` handler; persist it via the existing `ScopedStore.record_capabilities(..., model_overrides=...)`; add the optional `model` field to the loader; and implement fallback as **APPROACH B** (engine-level rebuild-and-retry around the per-agent `astream_events` consume, NOT `with_fallbacks`). No new migration. All five CI gates stay green.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `ModelResolver` lives in a new kernel-importable module (`agents/model_policy.py`), carried on `ExecutionContext.model_resolver` (typed `object | None = None`). Constructed at `execute()` entry, seeded with `model_overrides`, `CompiledWorkflow.model`, the run-wide session `model_id`, and the global Haiku default; per-agent `step` + `AgentSpec.model` supplied at resolve time.
- **D-02:** Resolution precedence (highest wins), None tiers skipped — parity-preserving: (1) user per-agent override `ctx.model_overrides[agent_id]`; (2) `step.model`; (3) agent default `AgentSpec.model`; (4) `workflow.model`; (5) run default = session `model_id` if set, else global Haiku. With every manifest/agent tier None today, every agent resolves to `session model_id or Haiku` = exactly today's behavior (INV-3 parity).
- **D-03:** `ModelCatalog` data + lookup live in `agents/capabilities/model_catalog.py` (kernel-importable); the registry adds `("model_catalog", "default")` as pure membership only — NO held instance, NO `@register`, NO trust enforcement (Phase 8). Resolver + override-validator import the catalog directly.
- **D-04:** `ModelCatalog` is the single source; `app/api/settings.py::AVAILABLE_MODELS` + `_VALID_MODEL_IDS` become derived projections (INV-12); `/api/settings` response shape unchanged. Catalog owns 5 models (Haiku 4.5 / Sonnet 4.5 / Sonnet 4.6 / Opus 4.5 / Opus 4.6). Keep BOTH `cost_class` (new) and legacy `tier` (display). cost_class: Haiku=cheap, Sonnet 4.5/4.6=standard, Opus 4.5/4.6=premium; all `user_allowed=true`, no gate.
- **D-05:** Prefer LangChain `Runnable.with_fallbacks([...])`; engine-level rebuild-and-retry is the locked alternative IF `with_fallbacks` does not compose through the deepagents `astream_events` stream. (**This research resolves it to APPROACH B — see "MUST RESOLVE #1".**) Chain construction (N11 tier-descent): empty `ModelPolicy.fallback` → derive Opus→[Sonnet,Haiku], Sonnet→[Haiku], Haiku→[]. Explicit fallback overrides the derived default. Every chain entry must be catalog-valid.
- **D-06:** Shared `_is_transient_throttle(exc)` predicate matches Bedrock `ThrottlingException` / botocore `ClientError` throttling codes / HTTP 429 / transient 5xx (ServiceUnavailable, InternalServerError); ChatAnthropic analogue (429/529/overloaded). Non-matching errors (validation/auth) propagate immediately. Chain exhaustion re-raises the last error. Unit-tested with a scripted model — no live Bedrock.
- **D-07:** `model_overrides` enters as a new optional `execute()` parameter, threaded from the websocket `run_pipeline` payload; validated against the catalog at ingress; stored on `ExecutionContext.model_overrides`. Each `{agent_id → model_id}` checked: `model_id ∈ ModelCatalog.ids()` AND `agent_id` is a run-workflow agent — failing fast with a clear error before execution.
- **D-08:** `model_overrides` persisted to `run_capabilities` via `ScopedStore.record_capabilities` (Phase 5 D-12); `cost_class` metadata-only (no budget enforcement until Phase 11). Inserted at `execute()` entry.
- **D-09:** AGENT.md optional `model` field — `agents/loader.py::AgentSpec` gains `model: str | None = None`; loader parses optional `model:` frontmatter (absent → None). Validate at load OR resolve time (Claude's discretion).

### Claude's Discretion
- Exact module name (`agents/model_policy.py` vs `agents/capabilities/model_resolver.py`) and resolver method signature (returns `ModelPolicy` vs `(id, chain)`).
- Whether `build_model` composes the fallback chain or the resolver does. (Moot under APPROACH B — neither composes `with_fallbacks`; the engine drives rebuild-and-retry.)
- Whether AGENT.md `model` is validated at load or resolve time (D-09).
- Whether the resolved `cost_class` set (beyond `model_overrides`) is recorded in `run_capabilities` (D-08).
- Whether `run_capabilities` is inserted at entry or upserted at completion (provided `model_overrides` lands). — Today it is inserted at entry (engine.py:738); `model_overrides` is known at entry, so insert-at-entry is correct.
- The `tier`↔`cost_class` representation (store-both vs derive) within D-04.
- Plan-task granularity / split.

### Deferred Ideas (OUT OF SCOPE)
- `GET /api/capabilities` endpoint + dynamic composer + per-agent model picker UI — Phase 8.
- Capability self-registration (`@register`/`discover()`) + `user_allowed` trust flags + owner allow-list — Phase 8.
- `cost_class` → `BudgetManager` enforcement — Phase 11.
- Manifests declaring `step.model` / `workflow.model` (prototype re-expression) — Phase 7. Phase 6 READS the fields; it does not author them.
- Session-`model_id` vs manifest-`workflow.model` precedence edge — Phase 7.
- New model providers beyond Anthropic/Bedrock.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODEL-01 | `ModelResolver` resolves effective model id per agent invocation by fixed precedence (user override > step > agent > workflow > global Haiku) | D-02 precedence grounded: 5 tiers map to `ctx.model_overrides[agent_id]` → `Step.model` (plan.py:209) → `AgentSpec.model` (new, D-09) → `CompiledWorkflow.model` (plan.py:248) → `model_id or settings.BEDROCK_INFERENCE_PROFILE_ID`. All tiers None today → parity. Resolver placed in `agents/model_policy.py`, carried on `ExecutionContext` (import-pure via `object | None` — context.py:82 precedent). |
| MODEL-02 | Resolved selection expressed as `ModelPolicy`; drives `build_model`; fallback chain fires on throttle | `ModelPolicy` already correct (plan.py:64-71). `build_model(model, max_tokens)` stays the single source (model_factory.py:29). Fallback = **APPROACH B** engine wrapper (see MUST RESOLVE #1) — `with_fallbacks` does NOT compose through the deepagents graph. |
| MODEL-03 | Per-agent `model_overrides {agent_id→model_id}` accepted, applied at top, persisted | Ingress at websocket `run_pipeline` (websocket.py:418-428 read sites; execute call websocket.py:1142). `execute()` gains param (engine.py:548 signature). Persist via `record_capabilities(..., model_overrides=...)` (authz.py:452-487, already accepts it via `**deferred`). |
| MODEL-04 | `ModelCatalog` registered capability (label/provider/cost_class/context_window/user_allowed); single source | New `agents/capabilities/model_catalog.py` (kernel-pure); registry membership `("model_catalog","default")` (registry.py:36-51). `AVAILABLE_MODELS` derives (settings.py:40-74). 5 models enumerated below. |
| MODEL-05 | Fixed precedence resolution order (the ordering contract behind MODEL-01) | Same as MODEL-01: D-02 ordered tiers, None-skipping, parity-preserving. |
| AGENT.md `model` field | Optional `model:` frontmatter → `AgentSpec.model` (None when absent) | Loader pattern mirrors `description` optional-string handling (loader.py:319-335, 356-374). Additive — no existing AGENT.md declares it. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-agent model resolution | API / Backend (kernel engine) | — | Resolution is a kernel service consumed per agent in `_run_agent`; lives on `ExecutionContext` (D-01). Not a swappable capability port. |
| Model metadata catalog | API / Backend (kernel-pure data) | — | Pure data importable by both the kernel resolver AND `app.api.settings`; must NOT reach into `app.*` (import-linter). |
| Model-switch fallback on throttle | API / Backend (kernel engine `_run_agent`) | — | APPROACH B: the engine owns the retry loop because the deepagents graph swallows model exceptions; `build_model` stays per-id single-client. |
| `model_overrides` ingress + validation | Frontend Server (FastAPI websocket) | API / Backend (catalog) | The `run_pipeline` WS handler is the ingress chokepoint; validation reads the kernel-pure catalog. |
| `model_overrides` persistence | Database / Storage (via `ScopedStore`) | — | Owner+workspace-scoped write to `run_capabilities` (Phase 5 path). |
| AGENT.md `model` parse | API / Backend (loader) | — | Frontmatter parse is a loader concern; additive optional field. |
| `AVAILABLE_MODELS` / `/api/settings` projection | Frontend Server (FastAPI settings router) | API / Backend (catalog) | The API derives its response from the kernel catalog (app→kernel allowed). |

## Standard Stack

This is a brownfield refactor — **no new packages**. The phase extends existing pinned libraries. Verified versions:

### Core (installed, pinned — `backend/requirements.txt`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `deepagents` | 0.6.7 | Agent runtime (`create_deep_agent`) | INV-13 mandate; canonical import `from deepagents import create_deep_agent` `[VERIFIED: python — deepagents.__version__ == 0.6.7]` |
| `langchain` | 1.3.4 | Agent factory + middleware | `request.model.bind_tools` + `await model_.ainvoke` is the model-node contract `[VERIFIED: langchain/agents/factory.py:1249,1351]` |
| `langchain-core` | 1.4.0 | `BaseChatModel`, `RunnableWithFallbacks`, message types | `RunnableWithFallbacks.astream` only catches on the FIRST chunk `[VERIFIED: langchain_core/runnables/fallbacks.py astream source]` |
| `langgraph` | 1.2.4 | Graph runtime under deepagents | event stream instrumentation; `astream_events` v2 |
| `langchain-aws` | 1.4.6 | `ChatBedrockConverse` (prod provider) | source of `botocore.exceptions` throttle types (`ClientError`/`ThrottlingException`) |
| `langchain-anthropic` | 1.4.3 | `ChatAnthropic` (local-dev provider) | source of the local-dev throttle analogue (429/529/overloaded) |
| `boto3` / `botocore` | (transitive, ≥1.42.42) | Bedrock client + adaptive retries | `botocore.config.Config(retries={"max_attempts":5,"mode":"adaptive"})` already embedded (model_factory.py:78) |

**Version verification:**
```bash
cd backend && python3.11 -c "import deepagents, langchain, langchain_core; print(deepagents.__version__, langchain.__version__, langchain_core.__version__)"
# → 0.6.7 1.3.4 1.4.0   [VERIFIED 2026-06-08]
```

### No new dependencies
`ThrottlingException` and the throttle-code set come from `botocore.exceptions.ClientError` (already a transitive dep through `langchain-aws`). No package install. **The Package Legitimacy Audit is therefore N/A — zero external packages are added.**

## Package Legitimacy Audit

**Not applicable.** Phase 6 installs **zero** new packages — it is a pure brownfield refactor extending already-pinned, already-installed libraries (`deepagents`, `langchain*`, `botocore`). No `pip install` task appears in any plan. slopcheck/registry verification is moot.

---

## MUST RESOLVE — Directive Answers

### 1. [CRITICAL — HIGH RISK] D-05 fallback seam binary → **VERDICT: APPROACH B**

**APPROACH B (engine-level rebuild-and-retry wrapper in `_run_agent`). Do NOT use `with_fallbacks`.**

**Evidence chain (each link verified this session):**

1. **The model is consumed by `ainvoke`, not `astream`, inside the graph.** The langchain agent's main model node calls `model_, _ = _get_bound_model(request)` then `output = await model_.ainvoke(messages)` `[VERIFIED: langchain/agents/factory.py:1346-1351]`. The streaming the engine observes comes from LangGraph's `astream_events` instrumentation wrapping that `ainvoke`, not from the model's own `.astream`.

2. **The agent factory requires `bind_tools` on the passed model.** `_get_bound_model` calls `request.model.bind_tools(...)` (and `request.model.bind(...)`) `[VERIFIED: langchain/agents/factory.py:1249, 1274, 1283, 1288]`. `request.model` originates from `create_deep_agent(model=...)`.

3. **`RunnableWithFallbacks` does not expose `bind_tools`.** `[VERIFIED: python repl — hasattr(RunnableWithFallbacks, "bind_tools") == False; has bind == True]`. So `build_model().with_fallbacks([...])` returns an object the agent cannot bind tools onto.

4. **Empirical: passing a `RunnableWithFallbacks` into `create_deep_agent` errors during assembly.** `[VERIFIED: python repl — create_deep_agent(model=primary.with_fallbacks([fb])) raised inside langchain_core/runnables/fallbacks.py:626 __getattr__ → _returns_runnable]`. The fallbacks proxy machinery cannot satisfy the bind_tools access path the agent assembly performs.

5. **Even if (3)/(4) were worked around, the deepagents runner swallows the throttle before any fallback could see it.** `DeepAgentRunner.astream_events` wraps the whole loop in `except Exception ... yield {"type":"error","error":str(exc)}` `[VERIFIED: app/agents/deep_agent_runner.py:451-455]` — it does NOT re-raise. And the engine's consumer loop only handles `chunk`/`usage`/`tool_call`/`tool_result`; an `error` event is silently ignored `[VERIFIED: agents/execution_engine/engine.py:1637-1673]`. So a model throttle currently ends the agent with whatever partial text streamed — no exception ever propagates to a `with_fallbacks` boundary anyway.

6. **`RunnableWithFallbacks.astream` only catches on the FIRST chunk.** Once the stream has begun, `except BaseException: raise` re-raises `[VERIFIED: langchain_core/runnables/fallbacks.py astream source]`. So even at the model level, mid-stream throttles never fall back — only pre-first-token ones would, and only if links 2-5 didn't already block the approach.

**Conclusion:** `with_fallbacks` is **not viable** as a composed seam through the deepagents graph at the installed versions (deepagents 0.6.7 / langchain 1.3.4 / langchain-core 1.4.0). The locked alternative APPROACH B is the implementation.

**APPROACH B implementation shape (for the planner):**

The fallback must wrap the **engine-level per-agent consume**, not the model. In `_run_agent` (engine.py:1593-1673):
- Before the `async for event in agent.astream_events(...)` loop, capture the resolved model id + its fallback chain from `ctx.model_resolver`.
- To detect a throttle, the runner's swallow must be made visible. **Two sub-options (planner's call):**
  - **B1 (preferred, minimal blast radius):** Add an optional `raise_on_error: bool` to `DeepAgentRunner` (or have it classify+re-raise transient throttles instead of yielding `error`). The engine catches the re-raised classified throttle, advances the resolver to the next chain id, rebuilds via `create_runner` (a fresh runner with `ctx.model` = next id), and re-invokes — bounded by `len(chain)`. **Caveat:** a throttle after partial tokens have streamed cannot un-emit them; restart on a fresh thread_id or accept that the retried run re-streams from scratch (the engine already accumulates `output_chunks` per attempt — reset between attempts). Pre-first-token is the common throttle case and restarts cleanly.
  - **B2 (no runner change):** Have the engine inspect the `{"type":"error"}` event, classify its `error` string against `_is_transient_throttle`, and on a match advance + rebuild + re-invoke. Lower-fidelity (string-matching an already-stringified exception) but touches only the engine.
- **B1 is recommended** — classifying a real exception object is more robust than re-parsing a stringified one. It keeps the runner the single streaming surface and the engine the single retry authority.
- The retry advances `ctx.model_resolver` (it holds the chain) and rebuilds via `create_runner` → the sanctioned `langchain_deepagents` adapter, so the **banned-pattern gate stays green** (no new `create_deep_agent` call).
- **Residual risk (LOW):** B1 requires a one-line behavioral change to the runner's exception handling (re-raise transient throttles, or expose a flag). This is a deliberate, documented change to a Phase-1 swallow that the runner docstring already flags as "Phase 3 will promote this to a raise" (deep_agent_runner.py:307,453). Mid-stream-after-tokens throttle is rare for Bedrock (throttles are pre-call) — accept restart-from-scratch.

**This binary is now resolved. Plan task granularity should assume APPROACH B** (engine + minimal runner change + a `_is_transient_throttle` predicate + a scripted-throttle test), NOT a `build_model`-composes-`with_fallbacks` task.

---

### 2. D-01 ModelResolver placement + rewire sites

**Import-linter permits it — VERIFIED.** `[VERIFIED: backend/pyproject.toml:131-169 + lint-imports run → "3 kept, 0 broken"]`. Contracts:
- "kernel imports only capability ports (scaffold)": `source = agents.execution_engine.engine`, `forbidden = app.api`. A new `agents/model_policy.py` is NOT `agents.execution_engine.engine`, so it has **no forbidden-import contract at all** today — free to import `agents.workflows.plan` (`ModelPolicy`) and the new catalog. And the engine importing `agents.model_policy` is fine (only `app.api` is forbidden to the engine).
- "agents.capabilities must not import the execution kernel or the web layer": `source = agents.capabilities`, `forbidden = [agents.execution_engine, app]`. This constrains the **catalog** (Area B), not the resolver.
- **Recommendation:** place `ModelResolver` in `agents/model_policy.py` (top-level kernel module, like the engine package) so it can import `agents.workflows.plan.ModelPolicy` + `agents.capabilities.model_catalog` AND be imported by `agents.execution_engine.engine`. Do **not** put the resolver under `agents/capabilities/` — that package is forbidden from importing the kernel, and a resolver is a kernel service.

**`ExecutionContext` import-purity — VERIFIED.** `context.py` imports ONLY stdlib + `agents.artifacts.graph` `[VERIFIED: context.py:25-37]`. The Phase-5 `scoped_store: object | None = None` field (context.py:82) is the exact precedent: typing the helper as `object` keeps the pure-data module free of the helper's `app.models` import. **Add identically:** `model_resolver: object | None = None` and `model_overrides: dict = field(default_factory=dict)` — **no new import**, import-purity preserved.

**The `_run_agent` model-set sites — VERIFIED current line numbers:**
| Site | File:line | Current code | Rewire to |
|------|-----------|--------------|-----------|
| Primary agent ctx | engine.py:1560 | `model=model_id,` (inside `AgentContext(...)` in `_run_agent`) | resolved id from `ctx.model_resolver.resolve(spec)` |
| Revision agent ctx | engine.py:1281 (`model=model_id` ~1286 area) | `AgentContext(... model=model_id ...)` in `_handle_revision`/rev path | resolved id |
| Validation fix-loop ctx | engine.py:2033 | `AgentContext(... model=model_id ...)` in `_run_validation_fix_loop` | resolved id (same agent as the build task) |
| Factory pass-through | factory.py:155 | `model=ctx.model,` in `create_runner` → `DeepAgentRunner` | unchanged — `ctx.model` now carries the resolved id |
| SmartPlanner | engine.py:1432 | `SmartPlanner(model_id=model_id)` | run-default tier (session `model_id`); see #2-note below |
| `execute()` entry | engine.py:548 (signature), 711 (`ExecutionContext(...)` construct) | `model_id: str | None = None` param | add `model_overrides`; construct resolver into `ectx.model_resolver` |

**Note on SmartPlanner (engine.py:1432, 1428-1434):** `SmartPlanner` builds its OWN client (`_build_llm`, smart_planner.py:161-183) — it does **not** go through `build_model` (a known pre-existing duplication, NOT introduced by this phase). It is a pre-agent planning call for `custom` pipelines only, sitting at the run-default tier. **Recommendation:** leave SmartPlanner on the session `model_id` (run default) — it has no `agent_id`, so per-agent overrides do not apply to it. Do not try to route it through the resolver; that would be scope creep and risk an INV-3 parity break on the planning call. (Documented as out-of-scope-of-resolver in the plan.)

**`AgentContext.model` (factory.py:44):** `model: str | None = None` — the resolved id flows through unchanged. `create_runner` passes `model=ctx.model` (factory.py:155) → `DeepAgentRunner(model=ctx.model)` (factory.py:152-166) → `build_model(model)` (deep_agent_runner.py:219-220). INV-13 preserved: the resolved id reaches the graph ONLY through `build_model`.

---

### 3. D-03 ModelCatalog kernel-purity + registry name-only

**Kernel-purity REQUIRED and VERIFIED enforceable.** `[VERIFIED: pyproject.toml:165-169]` — contract "agents.capabilities must not import the execution kernel or the web layer" with `forbidden_modules = ["agents.execution_engine", "app"]`. So `agents/capabilities/model_catalog.py` **must NOT import `app.*`** (any `app` import breaks the contract). It MAY be imported by `agents/model_policy.py` (kernel→capabilities is allowed) AND by `app/api/settings.py` (app→kernel/capabilities is allowed — only the reverse is forbidden). This satisfies D-03 and D-04's import-direction requirement (the kernel resolver cannot import `app.api`, so the catalog must live on the kernel side and settings.py must derive from it).

**Registry name-only — VERIFIED pattern.** `registry.py:36-51` is a `_KNOWN: set[tuple[str,str]]` of `(kind, name)` pairs with `is_registered` a pure set-membership check `[VERIFIED: registry.py:62-64]`. Adding `("model_catalog", "default")` to `_KNOWN` matches the Phase-4 D-07 pattern exactly — no held instance, no `@register`, no trust. Update the `_KNOWN` docstring count comment (registry.py:27 says "14"; becomes 15).

**No new Protocol needed.** The capability ports in `base.py` are **behavior** ports (`TaskParser.parse`, `ExecutionStrategy.run`, `Validator.validate`, etc.) `[VERIFIED: base.py:27-95]`. A `ModelCatalog` is **pure data** (list/get/is_allowed/ids over a static model list), not a behavior port. **Recommendation:** do NOT add a Protocol to `base.py`; the catalog is a concrete data class in `model_catalog.py`. (Planner's call per CONTEXT, but adding a port for pure data would be premature — INV-12.)

---

### 4. D-04 single-source / INV-12

**Every hand-maintained model list today (grep-enumerated):**
| Location | What it is | Disposition after Phase 6 |
|----------|-----------|---------------------------|
| `app/api/settings.py:40-71` `AVAILABLE_MODELS` | The 5-model list with `id`/`name`/`description`/`tier` | **DERIVED projection** over `ModelCatalog.list()` |
| `app/api/settings.py:74` `_VALID_MODEL_IDS` | `{m["id"] for m in AVAILABLE_MODELS}` | **DERIVED** = `set(ModelCatalog.ids())` |
| `agents/capabilities/model_catalog.py` (NEW) | The catalog | **THE SINGLE SOURCE** |

**Single-source other model-id references (NOT lists — env-var defaults, not duplicated lists):**
- `app/core/config.py:63,70,75,81` — `ANTHROPIC_MODEL_ID`, `BEDROCK_MODEL_ID`, `BEDROCK_INFERENCE_PROFILE_ID` (Haiku global default), `BEDROCK_CODING_MODEL_ID` (empty default, `/flowin-handoff` only). These are **single env-var defaults**, not a maintained model *list* — they are the global-default source the resolver reads at tier 5. **Leave unchanged** (the catalog seeds FROM these ids; the global default still reads `settings.BEDROCK_INFERENCE_PROFILE_ID`). Not an INV-12 violation.
- `app/agents/model_factory.py:46,57` — fallback literal `"claude-haiku-4-5-20251001"` and the `model or settings.*` defaulting. Single-source defaulting, not a list. Unchanged.
- `agents/planner/smart_planner.py:166,176` — same defaulting pattern in the SmartPlanner client. Unchanged.

**INV-12 grep assertion (for the plan's test):** after the refactor, `grep -rn 'claude-haiku-4\|claude-sonnet-4\|claude-opus-4' backend/app/api backend/agents/capabilities` must show the model-id list in **exactly one place** — `model_catalog.py`. `settings.py` must contain **no literal model dicts** (only the projection). `[VERIFIED current consumers: settings.py:40,74,318,334,337,347 — all four AVAILABLE_MODELS/_VALID_MODEL_IDS usages stay, but now read from the projection]`.

**The 5 catalog entries (exact seed — VERIFIED from settings.py:40-71):**
| id | name (`label`) | description | tier (legacy/display) | cost_class (new) | provider | user_allowed |
|----|------|-------------|------|-----------|----------|--------------|
| `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | Claude Haiku 4.5 | Fastest and most cost-efficient. Great for high-volume tasks. | `fast` | `cheap` | bedrock | true |
| `eu.anthropic.claude-sonnet-4-5-20250929-v1:0` | Claude Sonnet 4.5 | Balanced speed and intelligence. Ideal for most pipelines. | `balanced` | `standard` | bedrock | true |
| `eu.anthropic.claude-sonnet-4-6` | Claude Sonnet 4.6 | Best combination of speed and intelligence. 1M token context. | `balanced` | `standard` | bedrock | true |
| `eu.anthropic.claude-opus-4-5-20251101-v1:0` | Claude Opus 4.5 | Most powerful. Best for complex reasoning and coding tasks. | `powerful` | `premium` | bedrock | true |
| `eu.anthropic.claude-opus-4-6-v1` | Claude Opus 4.6 | Most intelligent broadly available model. Exceptional coding. | `powerful` | `premium` | bedrock | true |

`context_window`: SPEC requires the field. Sonnet 4.6 description says "1M token context"; others are standard Claude windows. **[ASSUMED]** the exact numeric `context_window` per model — the codebase carries no context-window numbers today (only the descriptive strings). The planner/discuss-phase should confirm exact values (e.g. 200000 default, 1000000 for Sonnet 4.6) OR the field may be populated descriptively. This does not block resolution/fallback (those key off `id`/`cost_class`).

**Frontend projection compatibility — VERIFIED.** The frontend `ModelOption` interface requires **exactly** `{id, name, description, tier}` with `tier: "fast" | "balanced" | "powerful"` `[VERIFIED: frontend/src/lib/api.ts:394-399]`, consumed by `AccountSettings.tsx` (sets `availableModels`, renders `m.name`) `[VERIFIED: frontend/src/components/settings/AccountSettings.tsx:90,110-112,333-355]` and `AnalyticsPage.tsx` (`MODEL_META[id].name`). The projection MUST emit `{id, name, description, tier}` (the catalog's extra fields `cost_class`/`provider`/`context_window`/`user_allowed` are dropped by the projection). Keeping legacy `tier` on the catalog (D-04 store-both) lets the projection stay byte-shape-identical. The `tier→cost_class` mapping is: fast↔cheap, balanced↔standard, powerful↔premium — assert consistent.

---

### 5. D-07 model_overrides ingress

**Inbound `run_pipeline` schema — VERIFIED.** The handler reads run-payload fields via `message_data.get(...)` `[VERIFIED: websocket.py:418-428: pipeline_type, message/content, agent_ids, attached_skills, attached_hooks, gate_agent_ids]`. `model_overrides` slots in identically: `model_overrides = message_data.get("model_overrides") or {}` alongside these reads. The frontend does not send it yet (Phase 8 wires the picker) → defaults to `{}` when absent.

**Where it threads:** `engine.execute(...)` is called at `[VERIFIED: websocket.py:1142-1158]` with `model_id=getattr(user, "preferred_model", None) or None` (websocket.py:1154). Add `model_overrides=model_overrides` to that call. (The second `model_id` read at websocket.py:662 is the **revision** path `_handle_revision` — a separate execute path; if revisions should accept overrides, thread there too, but SPEC scope is the main `run_pipeline` — planner's call.)

**Error event shape to reuse — VERIFIED.** The handler emits errors as `await websocket.send_json({"type":"error", "chunk":None, "section":None, "data":{"error": <message>, "code": <code>}})` `[VERIFIED: websocket.py:385-389, 407-413, 438-440]`. For an invalid override (unknown model id OR unknown agent id), reuse this shape with a clear `error` message and a `code` like `"invalid_model_override"`, sent **before** `engine.execute` is called, and `continue`/return without starting the run.

**`execute()` signature — VERIFIED.** `[engine.py:537-552]` ends with `parent_run_id: str | None = None`. Add `model_overrides: dict[str, str] | None = None` cleanly (and thread it through the `_execute_impl` mirror at engine.py:608-623, which duplicates the full param list — both signatures must gain the param). The `execute()` wrapper forwards every arg to `_execute_impl` (engine.py:576-590) — add `model_overrides=model_overrides` there too.

**Validation:** at ingress (websocket) or `execute()` entry, for each `{agent_id → model_id}`: assert `model_id in ModelCatalog.ids()` (reject unknown — Q2 allow-list trust) AND `agent_id` is in the run's agent set (the resolved `agents` list / `get_pipeline_agents`). Fail fast with the error event above. (CONTEXT D-07 allows either ingress-validation OR execute-entry; ingress is earlier/cheaper — recommend websocket ingress so a bad payload never starts a run.)

---

### 6. D-08 persistence

**`ScopedStore.record_capabilities` signature — VERIFIED.** `async def record_capabilities(self, run_id, runtime, **deferred) -> str` `[VERIFIED: authz.py:452-487]`. It already maps `model_overrides=deferred.get("model_overrides")` onto the row (authz.py:475). **No signature change needed** — just pass `model_overrides=<validated map>` from the engine call.

**Insert at entry — VERIFIED.** The row is inserted **at `execute()` entry**, not upserted at completion: `await scoped_store.record_capabilities(pipeline_run_id, runtime="langchain_deepagents")` `[VERIFIED: engine.py:738-740]`. `model_overrides` is known at entry (validated at ingress, carried on `ectx.model_overrides`), so insert-at-entry works — change the call to `record_capabilities(pipeline_run_id, runtime="langchain_deepagents", model_overrides=ectx.model_overrides or None)`. (Use `or None` so an empty `{}` persists as SQL NULL, matching the nullable column and avoiding a spurious non-null write for no-override runs — keeps INV-3 parity on the persisted row for legacy runs.)

**`run_capabilities.model_overrides` column — VERIFIED exists.** `model_overrides = Column(JSON, nullable=True)  # Phase 6` `[VERIFIED: app/models/run_capabilities.py:31]`. Created in migration 0014 (`sa.Column("model_overrides", sa.JSON(), nullable=True)`) `[VERIFIED: alembic/versions/0014_typed_artifacts_persistence.py:126]`. Head migration is 0015. **NO new migration this phase** — Q3 additive-only satisfied. `run_capabilities` already carries `owner_id` + `workspace_id` (run_capabilities.py:28-29).

**cost_class (planner's discretion):** the resolved per-agent `cost_class` set MAY additionally be recorded in `run_capabilities.versions` (also `**deferred`-routed, authz.py:480). At minimum `model_overrides` is persisted (MODEL-03). cost_class drives NO budget gate (Phase 11).

---

### 7. D-06 throttle classification + offline test

**Scripted-model seam — VERIFIED.** `ScriptedFakeChatModel(BaseChatModel)` `[VERIFIED: tests/agents/_scripted_model.py:86-155]` has `bind_tools` (no-op, returns self, line 100-101), `_stream` (line 110-144) and `_generate` (line 146-155). The model node calls `ainvoke` → `_generate` (per #1 evidence). **For the D-06 simulated-fallback test:** extend `ScriptedFakeChatModel` (or add a sibling) that, when constructed with a "throttle" flag for model-id A, **raises** the throttle exception from `_generate`/`_stream`; model-id B's instance streams normally. Inject A then B via the per-agent script / a two-entry chain. Because APPROACH B drives the retry at the engine level (rebuild via `create_runner` with the next id), the test exercises: throttle on chain[0] → engine advances → rebuild with chain[1] → run completes. A second test: every chain entry throttles → original re-raised after exhaustion. No live Bedrock (`os.environ` forces InMemory checkpointer; `RUNS_ROOT` temp dir — _scripted_model.py:53-57).

**Throttle exception types + codes (for `_is_transient_throttle(exc)`):**
- **Bedrock / botocore (prod, `ChatBedrockConverse`):** `botocore.exceptions.ClientError` where `exc.response["Error"]["Code"]` ∈ `{"ThrottlingException", "TooManyRequestsException", "ServiceUnavailableException", "InternalServerException", "ModelTimeoutException", "ServiceQuotaExceededException"}`; HTTP status 429 (throttle) / 503 (ServiceUnavailable) / 500 (InternalServer). langchain-aws may wrap these — also match by code substring `"Throttl"` / status 429/503/500. `[CITED: botocore exception model — ClientError.response["Error"]["Code"]; AWS Bedrock runtime throttling = ThrottlingException/429]` `[ASSUMED exact wrapped type names — langchain-aws 1.4.6 may re-raise botocore ClientError directly or wrap it; the predicate should match on (a) ClientError code AND (b) status code AND (c) message substring to be robust]`
- **ChatAnthropic (local dev):** `anthropic.RateLimitError` (HTTP 429), `anthropic.InternalServerError` / overloaded (HTTP 529). Match status 429/529 or type names `RateLimitError`/`overloaded`. `[CITED: Anthropic API — 429 rate_limit, 529 overloaded_error]` `[ASSUMED exact exception class import path under langchain-anthropic 1.4.3 wrapping]`
- **Non-matching (propagate immediately, no switch):** `ValidationException` (bad model id / params), auth errors (`AccessDeniedException`, `UnrecognizedClientException`), `ModelConfigurationError` (model_factory.py:25). These are not transient → re-raise.

**Recommendation:** implement `_is_transient_throttle` defensively as a layered predicate (type-name check OR HTTP-status check OR error-code/message substring), since the exact wrapped type depends on langchain-aws/anthropic internals. Co-locate it with the resolver (`agents/model_policy.py`) so both the engine retry and the test import one predicate. **Verify the real exception shapes empirically when implementing** (the wrapped types are `[ASSUMED]` — confirm against `langchain-aws`/`langchain-anthropic` at implementation time, but the test uses a synthetic raise so it doesn't depend on the real wrapper).

---

### 8. D-09 AGENT.md model field

**Loader pattern — VERIFIED.** `_build_spec` (loader.py:229-374) validates each field; the optional `description` field (loader.py:319-335) is the exact template for an optional string: `metadata.get("description")` → if present must be `str` else `AgentSpecError`, else default. **Add identically:** in `AgentSpec` (loader.py:64-103) add `model: str | None = None` after `injects`; in `_build_spec` read `raw_model = metadata.get("model")`, validate `isinstance(str)` if present (else `AgentSpecError`), default `None`; pass `model=model` to the `AgentSpec(...)` constructor (loader.py:356-374).

**Schema test stays green — VERIFIED.** No existing AGENT.md declares `model` (it is brand-new), so absent→None for all ~80 agents; the loader schema test (`tests/agents/test_loader.py`, calls `load_agent_spec` for every agent) stays green `[VERIFIED: test_loader.py passes today, 41 tests; adding an optional defaulted field cannot break it]`.

**Load-time vs resolve-time validation (D-09 / discretion):** **Recommendation — validate at LOAD time** against `ModelCatalog.ids()` (fail-fast, consistent with the loader's per-field validation philosophy). BUT: the loader is currently kernel-pure for catalog import? — `agents/loader.py` is NOT under `agents.capabilities` or `agents.workflows`, so importing `agents.capabilities.model_catalog` from the loader is import-linter-clean (the catalog is kernel-pure). **Caveat:** load-time validation means a typo'd `model:` in any AGENT.md fails the schema test — desirable (fail-fast) but means the catalog must be importable from the loader. If the planner prefers minimal coupling, defer to resolve-time (the resolver already validates against the catalog). Either is acceptable per D-09; load-time is the lower-risk fail-fast choice.

---

### 9. CI gates / parity guardrails

| Gate | What it checks | File | Plan must keep green by |
|------|----------------|------|-------------------------|
| **Loader schema** | every AGENT.md loads to a valid `AgentSpec` | `tests/agents/test_loader.py` | optional defaulted `model` field (absent=None) |
| **Banned-pattern (INV-13/R15)** | only the `langchain_deepagents` adapter imports/calls `create_deep_agent`; no local `deepagents`/`langchain_deepagents` module | `tests/agents/test_banned_patterns.py` `[VERIFIED: 8 tests pass]` | APPROACH B rebuilds via `create_runner` (sanctioned path) — NO new `create_deep_agent` call |
| **Migration-ledger ratchet** | L-row ledger does not regress (Phase 6 flips no L-rows) | `tests/agents/test_migration_ledger.py` `[VERIFIED: 7 tests, 1 skip]` + `specs/003-workflow-engine-decoupling/migration-ledger.md` | no leak deletion this phase — keep ledger unchanged |
| **Characterization / parity (INV-3, 0A/0C)** | deliverable bytes + semantic-event multiset identical for existing pipelines | `tests/agents/characterization/` (golden snapshots), `test_characterization_{prototype,od_ppt,od_prototype,app_builder,prototype_revision}.py`, `test_phase3_parity.py`, `test_manifest_parity.py`, `test_runner_output_fallback.py` | a no-overrides + no-manifest-model run must resolve to `session model_id or Haiku` = today's exact path; no new events |
| **Import-linter** | kernel→ports direction; catalog kernel-pure (no `app.*`); resolver may import workflows+catalog | `backend/pyproject.toml:131-169` `[VERIFIED: lint-imports → 3 kept, 0 broken]` | `model_catalog.py` no `app.*` import; `model_policy.py` clean (no contract restricts it) |
| **run_capabilities / migration_0014** | row schema incl. `model_overrides` | `tests/unit/test_run_capabilities.py`, `tests/unit/test_migration_0014.py` `[VERIFIED: 4 tests pass]` | no migration; populate existing column |

**Exact test commands (CONTEXT-confirmed, dev runtime `python3.11`, no venv):**
```bash
cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v          # full phase suite
cd backend && python3.11 -m pytest tests/agents/test_loader.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q   # gate subset
cd backend && lint-imports                                                # import boundary
cd backend && python3.11 -m pytest tests/agents/characterization/ -q      # parity snapshots
```

---

## Architecture Patterns

### System Architecture Diagram

```
WS run_pipeline payload  ──► app/api/websocket.py (run_pipeline handler, ~418)
   {model_overrides{agent→id}, preferred_model, ...}
        │  read model_overrides; VALIDATE each {agent_id→model_id} against ModelCatalog.ids()
        │  + agent_id ∈ run agents.  invalid → send_json {"type":"error","data":{"error":...}}  (reject, no run)
        ▼
engine.execute(..., model_id=preferred_model, model_overrides={...})   (engine.py:537/608)
        │  construct ModelResolver(overrides, workflow.model, session model_id, Haiku default)
        │   → ectx.model_resolver ; ectx.model_overrides = validated map
        │  ScopedStore.record_capabilities(run_id, runtime, model_overrides=map)  (engine.py:738 → authz.py:452)
        │   → INSERT run_capabilities row AT ENTRY (model_overrides column, migration 0014)
        ▼
   for each AgentSpec:  _run_agent(spec, ..., ectx)   (engine.py:1484)
        │  resolved_id = ectx.model_resolver.resolve(spec, step)   ── precedence (D-02):
        │       overrides[spec.id] > step.model > spec.model > workflow.model > (session_id or Haiku)
        │  AgentContext(model=resolved_id)   (engine.py:1560)
        ▼
   create_runner(spec.id, ctx)  (factory.py:69) ──► DeepAgentRunner(model=ctx.model)  (factory.py:152)
        │                                              └─► build_model(resolved_id)  (model_factory.py:29)  ◄── single source / INV-13
        ▼
   async for ev in agent.astream_events(msg):   (engine.py:1634)
        │   chunk/usage/tool_call/tool_result → WS events
        │
        │   ── APPROACH B fallback wrapper ──
        │   on classified transient throttle (re-raised by runner, B1):
        │       resolver.advance() → next chain id (tier-descent: Opus→Sonnet→Haiku, ...)
        │       rebuild via create_runner(next_id) → re-invoke   (bounded by len(chain))
        │       chain exhausted → re-raise last error
        ▼
   deliverable read back from RunSandbox (unchanged)

ModelCatalog (agents/capabilities/model_catalog.py — KERNEL-PURE, no app.*)
   ├──► imported by agents/model_policy.py (resolver + validator)
   ├──► imported by agents/loader.py (load-time model validation, optional)
   └──► imported by app/api/settings.py  ── AVAILABLE_MODELS = projection(catalog) ; _VALID_MODEL_IDS = set(ids)
                                              /api/settings response shape UNCHANGED ({id,name,description,tier})
registry._KNOWN += ("model_catalog","default")   (name-only membership; no instance)
```

### Recommended Project Structure
```
backend/agents/
├── model_policy.py            # NEW — ModelResolver + _is_transient_throttle (kernel module)
├── capabilities/
│   ├── model_catalog.py       # NEW — ModelCatalog (pure data; kernel-pure, no app.*)
│   ├── registry.py            # +("model_catalog","default") in _KNOWN
│   └── base.py                # UNCHANGED — no new Protocol (catalog is data, not behavior)
├── loader.py                  # +AgentSpec.model: str|None + _build_spec parse
├── factory.py                 # UNCHANGED signature — ctx.model now carries resolved id
├── workflows/plan.py          # UNCHANGED — ModelPolicy/Step.model/CompiledWorkflow.model already correct
├── authz.py                   # UNCHANGED — record_capabilities already takes model_overrides
└── execution_engine/
    ├── context.py             # +model_resolver: object|None, +model_overrides: dict
    └── engine.py              # execute() +param +resolver construct +record_capabilities arg;
                               #   _run_agent rewire model sites + APPROACH B fallback loop
backend/app/
├── api/settings.py            # AVAILABLE_MODELS/_VALID_MODEL_IDS → derived projections
├── api/websocket.py           # run_pipeline +model_overrides ingress + validation + error
├── agents/model_factory.py    # UNCHANGED (single source — do NOT fork provider/retries)
└── models/run_capabilities.py # UNCHANGED — model_overrides column already exists (0014)
```

### Pattern 1: Per-run helper on ExecutionContext typed as `object`
**What:** A kernel service that needs run-level inputs rides on `ExecutionContext` typed `object | None` to keep the pure-data context module import-free.
**When to use:** `model_resolver` (exactly like `scoped_store`).
```python
# Source: backend/agents/execution_engine/context.py:82 (scoped_store precedent)
scoped_store: object | None = None        # typed object → no app.models import
# ADD identically:
model_resolver: object | None = None      # ModelResolver, typed object → no inbound import
model_overrides: dict = field(default_factory=dict)
```

### Pattern 2: Name-only capability membership (Phase-4 D-07)
```python
# Source: backend/agents/capabilities/registry.py:36-51
_KNOWN: set[tuple[str, str]] = {
    ("strategy", "single_shot"),
    # ...
    ("model_catalog", "default"),   # ADD — pure membership, no instance, no trust
}
```

### Pattern 3: Optional frontmatter string field (loader)
```python
# Source: backend/agents/loader.py:325-335 (description optional-string template)
raw_model = metadata.get("model")
if raw_model is not None and not isinstance(raw_model, str):
    raise AgentSpecError(f"Invalid field 'model' in {file_path_str}: expected string or null")
model: str | None = raw_model  # absent → None
```

### Anti-Patterns to Avoid
- **`build_model().with_fallbacks(...)` returned into the graph** — breaks (`RunnableWithFallbacks` lacks `bind_tools`; deepagents calls it). Use APPROACH B.
- **Forking `build_model`** — SPEC + CLAUDE.md forbid it; it stays the single source of provider selection + botocore retries. The model-switch layers ABOVE it (engine-level), not inside it.
- **Adding the catalog beside `AVAILABLE_MODELS`** — INV-12 dual-impl. `AVAILABLE_MODELS` must DERIVE.
- **Importing `app.*` from `agents/capabilities/model_catalog.py`** — breaks import-linter.
- **Persisting `{}` for no-override runs** — write `None` (SQL NULL) so legacy-run rows stay parity-identical.
- **Routing SmartPlanner through the resolver** — it has no agent_id and builds its own client; leave it on the session model_id (run default).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP-layer throttle retry | A retry loop in the engine | Existing botocore `retries={"max_attempts":5,"mode":"adaptive"}` in `build_model` | Already embedded (model_factory.py:78); the model-switch is a SEPARATE layer above it |
| Provider selection | New provider branching | `build_model` (model_factory.py:29) | Single source; INV-13 |
| run_capabilities write | New SQLAlchemy insert | `ScopedStore.record_capabilities(..., model_overrides=)` (authz.py:452) | Owner/workspace-scoped; already accepts the field |
| Model metadata storage | A second model list | `ModelCatalog` single source; project `AVAILABLE_MODELS` | INV-12 |
| AGENT.md field validation | Bespoke parser | `_build_spec` per-field pattern (loader.py:325) | Consistent errors, cached |
| Migration for model_overrides | New alembic revision | Existing column (0014, run_capabilities.py:31) | Q3 additive-only; column exists |

**Key insight:** Almost every seam this phase needs already exists, inert. The work is *wiring* (resolver construct + rewire 3 model sites + ingress + 1 persist arg + 1 loader field + 1 catalog module + 1 projection) plus the **one genuinely new mechanism** — the APPROACH B fallback loop, which requires a minimal runner exception-handling change.

## Runtime State Inventory

> This is a code-refactor phase, not a rename/data-migration. No stored string is being renamed. Inventory included for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `run_capabilities.model_overrides` column exists (migration 0014, run_capabilities.py:31), currently always NULL. Phase 6 begins WRITING it (new rows only). No backfill of existing rows. | Code edit (write at entry). No data migration. |
| Live service config | None — no external service holds a model string outside git. | None — verified by grep (only config.py env defaults + settings.py list, both in git). |
| OS-registered state | None. | None — no OS registrations involved. |
| Secrets/env vars | `ANTHROPIC_MODEL_ID` / `BEDROCK_INFERENCE_PROFILE_ID` / `BEDROCK_MODEL_ID` / `BEDROCK_CODING_MODEL_ID` (config.py:63-81) — read unchanged as the global-default source. Names NOT renamed. | None — read-only; catalog seeds from these ids. |
| Build artifacts | None — no compiled/egg-info artifact carries a model id. | None. |

**The canonical question:** After every file is updated, no runtime system holds a stale model string — the only persisted model data (`run_capabilities.model_overrides`) is *newly written by this phase*, not migrated.

## Common Pitfalls

### Pitfall 1: Assuming `with_fallbacks` composes through deepagents
**What goes wrong:** Plan a `build_model`-returns-`with_fallbacks` task; it fails at `create_deep_agent` assembly (no `bind_tools`) or silently never fires (runner swallows the throttle).
**Why it happens:** `with_fallbacks` is the LangChain-idiomatic answer, but the model lives inside a graph that binds tools and the runner eats exceptions.
**How to avoid:** APPROACH B (this research). Engine-level rebuild-and-retry.
**Warning signs:** `AttributeError: ... bind_tools` during graph build; or a throttle producing a blank agent output with no fallback.

### Pitfall 2: Breaking INV-3 parity on no-override runs
**What goes wrong:** Resolver returns Haiku for a user who set `preferred_model`, OR a `{}` model_overrides persists a non-null row, changing the characterization snapshot.
**Why it happens:** Dropping the session `model_id` from tier 5, or writing `{}` instead of `None`.
**How to avoid:** Tier 5 = `session model_id or Haiku`; persist `model_overrides or None`. Run characterization snapshots after each change.
**Warning signs:** `test_characterization_*` diffs; a `run_capabilities` row with `{}` where prior runs had NULL.

### Pitfall 3: Catalog importing `app.*`
**What goes wrong:** `model_catalog.py` imports something from `app` (e.g. settings) → import-linter breaks; the kernel resolver can no longer import it.
**Why it happens:** Reaching for `app.core.config` model-id defaults from the catalog.
**How to avoid:** The catalog is self-contained model data. If it needs the global-default id, the *resolver* (kernel module) reads `settings.BEDROCK_INFERENCE_PROFILE_ID`, not the catalog — or pass it in.
**Warning signs:** `lint-imports` → "agents.capabilities must not import ... app" BROKEN.

### Pitfall 4: Mid-stream throttle re-streaming on retry (APPROACH B)
**What goes wrong:** A throttle after some tokens streamed → retry restarts the agent → the UI sees the first chunks twice.
**Why it happens:** Streaming cannot un-emit tokens.
**How to avoid:** Reset `output_chunks` between attempts (engine already collects per-loop); restart on a fresh thread_id. Document that pre-first-token is the common case (clean) and mid-stream restart re-streams.
**Warning signs:** Duplicated `agent_chunk` text in the live UI after a fallback.

## Code Examples

### Resolver precedence (D-02) — the parity-critical default
```python
# agents/model_policy.py (new). resolve() returns the effective id (+ chain).
# None tiers are SKIPPED; tier 5 preserves today's behavior exactly.
def resolve(self, spec, step=None) -> str:
    return (
        self._overrides.get(spec.id)                       # 1 user override
        or (step.model.model if step and step.model else None)   # 2 step.model
        or getattr(spec, "model", None)                    # 3 AgentSpec.model (D-09)
        or (self._workflow_model.model if self._workflow_model else None)  # 4 workflow.model
        or self._session_model_id                          # 5a session model_id
        or self._haiku_default                             # 5b global Haiku
    )
# With overrides={}, step.model=None, spec.model=None, workflow.model.model=None:
#   → session_model_id or Haiku  ==  today's build_model(model_id) input.  INV-3 ✔
```

### Persist model_overrides at entry (D-08)
```python
# engine.py:738 — change the existing call
await scoped_store.record_capabilities(
    pipeline_run_id,
    runtime="langchain_deepagents",
    model_overrides=(ectx.model_overrides or None),   # {} → NULL (parity for legacy rows)
)
```

### AVAILABLE_MODELS as a projection (D-04, INV-12)
```python
# app/api/settings.py — replace the literal list
from agents.capabilities.model_catalog import ModelCatalog   # app→kernel: allowed
AVAILABLE_MODELS = [
    {"id": m.id, "name": m.label, "description": m.description, "tier": m.tier}
    for m in ModelCatalog().list()
]   # shape == ModelOption {id,name,description,tier}  — frontend unchanged
_VALID_MODEL_IDS = set(ModelCatalog().ids())
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single session model id threaded run-wide | Per-agent resolution by precedence | Phase 6 (this) | Resolver on ctx; parity preserved |
| `AVAILABLE_MODELS` hand-list in settings.py | Catalog single-source + projection | Phase 6 | INV-12 |
| Model throttle aborts the agent (no model fallback) | Engine-level model-switch fallback (APPROACH B) | Phase 6 | Tier-descent chain |
| `with_fallbacks` (LangChain idiom) | NOT viable through deepagents — engine retry instead | Resolved this research | Decides task granularity |

**Deprecated/outdated:**
- The runner's `astream_events` exception swallow (deep_agent_runner.py:451) is a Phase-1 artifact the docstring already marks for promotion to `raise` (deep_agent_runner.py:307,453). APPROACH B B1 acts on that planned promotion (scoped to transient throttles).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Exact `context_window` numeric per model (SPEC requires the field; codebase has no numbers, only "1M token context" prose for Sonnet 4.6) | D-04 catalog seed | LOW — field is metadata; resolution/fallback key off id/cost_class. Confirm values in discuss-phase or populate descriptively. |
| A2 | Exact wrapped throttle exception types under langchain-aws 1.4.6 / langchain-anthropic 1.4.3 (botocore `ClientError` codes + Anthropic 429/529 are documented; the *wrapper* class path is not verified live) | D-06 predicate | MEDIUM — `_is_transient_throttle` must be defensive (type OR status OR code/message). The offline test uses a synthetic raise, so the test is not blocked; real-Bedrock behavior should be confirmed at implementation time. |
| A3 | Load-time catalog validation in the loader is import-clean (loader is not under agents.capabilities/workflows, so importing the kernel-pure catalog is allowed) | D-09 | LOW — verified the loader has no import-linter contract; if coupling is undesired, defer to resolve-time validation (also acceptable per D-09). |

## Open Questions (RESOLVED)

> Both resolved at plan time and adopted by the Phase 6 plans: Q1 → **B1** (06-05 rebuilds via `create_runner` on a re-raised classified throttle); Q2 → **main `run_pipeline` only** (06-04 threads `model_overrides` into the `websocket.py:1142` execute, not the revision path).

1. **B1 vs B2 for the throttle-visibility seam (APPROACH B).**
   - What we know: B1 (runner re-raises classified transient throttles) is more robust than B2 (engine string-matches the `error` event).
   - What's unclear: whether the team prefers touching `DeepAgentRunner` now vs. keeping the swallow and string-matching.
   - Recommendation: B1 — it aligns with the runner's own documented "promote to raise" plan and gives the engine a real exception to classify. Scope the re-raise strictly to `_is_transient_throttle` matches; keep yielding `error` for everything else (no behavior change for non-throttle errors → parity preserved).

2. **Should the revision path (`_handle_revision`, websocket.py:662) accept `model_overrides`?**
   - What we know: SPEC scope names the main `run_pipeline`; the revision execute is a separate call site.
   - Recommendation: thread `model_overrides` only into the main `run_pipeline` execute (websocket.py:1142) for Phase 6; note revision overrides as a follow-up. (Planner's call.)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All backend work / tests | ✓ | 3.11.14 | — |
| `deepagents` | Runner / INV-13 | ✓ | 0.6.7 | — |
| `langchain` / `langchain-core` | Agent factory / model | ✓ | 1.3.4 / 1.4.0 | — |
| `langgraph` | Graph runtime | ✓ | 1.2.4 | — |
| `langchain-aws` / `langchain-anthropic` | Providers / throttle types | ✓ | 1.4.6 / 1.4.3 | — |
| `import-linter` (`lint-imports`) | Import-boundary gate | ✓ | runs (3 kept, 0 broken) | — |
| pytest (+asyncio/hypothesis) | Test suite | ✓ | 8.3.4 | — |
| Postgres / live Bedrock | NOT required (offline scripted-model test; InMemory checkpointer) | n/a | — | scripted model + temp RUNS_ROOT (already standard) |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — all work is offline-testable (no live Bedrock, per SPEC test-isolation constraint).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 (+ pytest-asyncio 0.24.0 STRICT, hypothesis 6.122.3) |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/<file>.py -q` |
| Full suite command | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODEL-01/05 | Precedence: 5 tiers, override>step>agent>workflow>global, None-skipping | unit | `python3.11 -m pytest tests/unit/test_model_resolver.py -x` | ❌ Wave 0 |
| MODEL-01 (parity) | No-override run resolves to `session model_id or Haiku` == today | unit + characterization | `python3.11 -m pytest tests/agents/characterization/ -q` | ✅ (snapshots exist; assert unchanged) |
| MODEL-02 | `ModelPolicy` drives `build_model` with resolved id; policy max_tokens does NOT raise runtime cap (still MAX_OUTPUT_TOKENS) | unit | `python3.11 -m pytest tests/unit/test_model_resolver.py::test_max_tokens_doc_only -x` | ❌ Wave 0 |
| MODEL-02 (fallback) | Simulated throttle on chain[0] → engine advances → run completes on chain[1] (APPROACH B, no live Bedrock) | unit (scripted) | `python3.11 -m pytest tests/agents/test_model_fallback.py::test_throttle_advances -x` | ❌ Wave 0 |
| MODEL-02 (exhaustion) | Every chain entry throttles → original/last error re-raised | unit (scripted) | `python3.11 -m pytest tests/agents/test_model_fallback.py::test_chain_exhaustion_reraises -x` | ❌ Wave 0 |
| MODEL-02 (chain) | Empty `fallback` derives tier-descent: Opus→[Sonnet,Haiku], Sonnet→[Haiku], Haiku→[] | unit | `python3.11 -m pytest tests/unit/test_model_resolver.py::test_default_chains -x` | ❌ Wave 0 |
| MODEL-03 | `model_overrides={agent→id}` resolves that agent; persists to `run_capabilities.model_overrides` | unit + integration | `python3.11 -m pytest tests/unit/test_run_capabilities.py -k model_overrides -x` | ✅ (file exists; add case) |
| MODEL-03 (reject) | Unknown model id OR unknown agent id → clear rejection (no run) | unit | `python3.11 -m pytest tests/unit/test_run_pipeline_validation.py -k override -x` | ✅ (file exists; add case) |
| MODEL-04 | Catalog lists entries w/ label/provider/cost_class/context_window/user_allowed; Opus user_allowed=true; registry membership | unit | `python3.11 -m pytest tests/agents/test_model_catalog.py -x` | ❌ Wave 0 |
| MODEL-04 (INV-12) | `AVAILABLE_MODELS` derives; grep proves ONE model-id list; `/api/settings` shape unchanged | unit + grep | `python3.11 -m pytest tests/agents/test_model_catalog.py::test_available_models_is_projection -x` | ❌ Wave 0 |
| AGENT.md model | `model:` parses to `AgentSpec.model` (None when absent); schema test green for all agents | unit | `python3.11 -m pytest tests/agents/test_loader.py -x` | ✅ (extend) |

### Sampling Rate
- **Per task commit:** the touched file's quick test (e.g. `pytest tests/unit/test_model_resolver.py -x`) + `lint-imports`.
- **Per wave merge:** `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -q` + `lint-imports` + `pytest tests/agents/characterization/ -q`.
- **Phase gate:** full suite green + characterization snapshots unchanged (INV-3) + banned-pattern + migration-ledger green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/unit/test_model_resolver.py` — precedence (5 tiers + None-skip), parity default, max_tokens-doc-only, default tier-descent chains (MODEL-01/02/05)
- [ ] `tests/agents/test_model_fallback.py` — scripted-throttle advance + chain-exhaustion re-raise (MODEL-02); extend `_scripted_model.py` with a throttle-raising variant
- [ ] `tests/agents/test_model_catalog.py` — catalog field set + registry membership + AVAILABLE_MODELS-is-projection + grep-single-source (MODEL-04/INV-12)
- [ ] Extend `tests/unit/test_run_capabilities.py` (model_overrides persisted) + `tests/unit/test_run_pipeline_validation.py` (override rejection) + `tests/agents/test_loader.py` (model field)
- [ ] Shared fixture: a `_scripted_model.py` helper that raises a synthetic throttle for a given model id (no live Bedrock)
- [ ] Framework install: none — pytest stack already present.

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Existing JWT on the WS path; unchanged by this phase. |
| V3 Session Management | no | Unchanged. |
| V4 Access Control | yes | `model_overrides` persists via `ScopedStore` (owner+workspace-scoped, AUTHZ-01) — already enforced (authz.py). New writes inherit the scope; no new access path. |
| V5 Input Validation | yes | `model_overrides` is untrusted run-payload input — MUST validate each `model_id ∈ ModelCatalog.ids()` (allow-list, Q2) AND `agent_id ∈ run agents`, rejecting unknown values (never an arbitrary string) before execution. AGENT.md `model` validated against the catalog (load or resolve time). |
| V6 Cryptography | no | No crypto in scope. |

### Known Threat Patterns for {FastAPI WS + kernel engine}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary/unknown model id injected via `model_overrides` (SSRF-to-unknown-provider / cost abuse / invalid model crash) | Tampering / Elevation | Allow-list validation against `ModelCatalog.ids()` at ingress; reject with the existing `{"type":"error"}` event before `execute` (Q2 trust). |
| Override targeting a non-existent agent_id (silent no-op / confusion) | Tampering | Validate `agent_id ∈ run agents` at ingress; reject clearly. |
| Cross-tenant override leakage via persistence | Information Disclosure | `record_capabilities` writes are owner+workspace-scoped (ScopedStore) — no change needed; reuse the Phase-5 scoped path. |
| Premium-model cost abuse | (out of scope) | N11 = no gate this phase; cost_class metadata-only; `BudgetManager` enforcement is Phase 11. |

## Sources

### Primary (HIGH confidence)
- Codebase (read this session, with line anchors): `app/agents/model_factory.py`, `app/agents/deep_agent_runner.py`, `agents/factory.py`, `agents/execution_engine/engine.py`, `agents/execution_engine/context.py`, `agents/loader.py`, `agents/capabilities/registry.py`, `agents/capabilities/base.py`, `agents/workflows/plan.py`, `agents/authz.py`, `app/api/settings.py`, `app/api/websocket.py`, `app/models/run_capabilities.py`, `app/core/config.py`, `agents/planner/smart_planner.py`, `tests/agents/_scripted_model.py`, `alembic/versions/0014_typed_artifacts_persistence.py`, `pyproject.toml`, `frontend/src/lib/api.ts`, `frontend/src/components/settings/AccountSettings.tsx`.
- Installed library source (read): `langchain/agents/factory.py` (model node `ainvoke` + `bind_tools`), `langchain_core/runnables/fallbacks.py` (`RunnableWithFallbacks.astream`/`ainvoke`), `deepagents.create_deep_agent` signature.
- Empirical runs (this session): version probe (`deepagents 0.6.7 / langchain 1.3.4 / langchain-core 1.4.0 / langgraph 1.2.4`); `RunnableWithFallbacks` `bind_tools` absence + `create_deep_agent(model=wrapped)` failure; `lint-imports` (3 kept, 0 broken); gate-subset pytest (59 passed, 1 skipped).

### Secondary (MEDIUM confidence)
- Botocore exception model (ClientError code dictionary) + AWS Bedrock runtime throttling semantics (ThrottlingException/429) — documented behavior, exact langchain-aws wrapper class is A2.
- Anthropic API status codes (429 rate_limit, 529 overloaded) — documented, exact langchain-anthropic wrapper is A2.

### Tertiary (LOW confidence)
- None — all load-bearing claims are tool-verified against the codebase or installed libraries.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions probed; no new packages.
- Architecture / placement (D-01/D-03/D-04): HIGH — import-linter contracts read + run; line anchors verified.
- D-05 fallback verdict: HIGH — multi-link empirical chain (bind_tools absence, ainvoke node, create_deep_agent failure, runner swallow, astream first-chunk-only).
- D-06 predicate exception types: MEDIUM — documented codes HIGH, exact wrapper class A2 (test uses synthetic raise → unblocked).
- D-07/D-08/D-09 wiring: HIGH — exact signatures/line numbers + existing column + record_capabilities already accepting the field, all verified.

**Research date:** 2026-06-08
**Valid until:** 2026-07-08 (stable — pinned libraries; brownfield refactor). Re-verify if `deepagents`/`langchain`/`langchain-core` are bumped.

## RESEARCH COMPLETE

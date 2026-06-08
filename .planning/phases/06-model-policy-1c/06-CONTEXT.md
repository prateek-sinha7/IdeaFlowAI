# Phase 6: Model Policy [1C] - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Mode:** Recommended options locked (gray-area question dismissed — user chose "lock all to recommendations", mirroring Phases 1/2/4/5). Every decision below is the plan.md-grounded recommendation. Review/edit this file before planning if any needs changing.

<domain>
## Phase Boundary

Make the **inert** model-policy scaffolding (Phase 4 D-06) **live**: a `ModelResolver` carried on `ExecutionContext` resolves the effective model per agent invocation by precedence — **user per-agent override > `step.model` > agent default (AGENT.md) > `workflow.model` > run default (session `model_id`, else global Haiku)** — and drives `model_factory.build_model` through a `ModelPolicy` (model id + `cost_class` metadata + ordered `fallback`). A model-switch layer **above** the existing botocore retries advances to the next model in the chain on a sustained throttle/transient error. A kernel-importable `ModelCatalog` (the single source of model metadata; `AVAILABLE_MODELS` derives from it) lists selectable models with `label`/`provider`/`cost_class`/`context_window`/`user_allowed` (all incl. Opus `user_allowed`, no gate — N11). Per-agent `model_overrides {agent_id → model_id}` ride in the run payload, validated against the catalog, applied at the top of the order, and persisted to `run_capabilities.model_overrides`.

**Backend-only this phase.** Existing single-model runs (no overrides, no manifest model fields) resolve to today's outcome (session `model_id` or Haiku) — byte/semantic parity preserved (INV-3).

**Explicitly NOT this phase:** the `GET /api/capabilities` endpoint + the frontend per-agent model picker (Phase 8); capability self-registration / `@register` / trust-flag machinery (Phase 8); `cost_class` → `BudgetManager` enforcement (Phase 11); re-expressing prototype manifests to declare `step.model`/`workflow.model` (Phase 7 — the fields are READ now, not authored).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**6 requirements are locked.** See `06-SPEC.md` for full requirements (MODEL-01..05 + the AGENT.md `model` field), boundaries, and acceptance criteria.

Downstream agents MUST read `06-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `ModelResolver` (fixed precedence) constructed at `execute()` entry, carried on `ExecutionContext`
- `ModelPolicy` wired into `build_model` (resolved id + `cost_class` metadata + ordered `fallback`)
- Model-switch fallback layer above botocore retries (throttle/429/transient-5xx after retries → next chain entry; exhaustion re-raises), unit-tested with a simulated throttle
- Default tier-descent fallback chains (Opus→Sonnet→Haiku, Sonnet→Haiku, Haiku→none)
- `model_overrides {agent_id → model_id}` accepted in the run payload, applied at top of order, validated against the catalog, persisted to `run_capabilities.model_overrides`
- `ModelCatalog` registered capability (label/provider/cost_class/context_window/user_allowed); all models incl. Opus `user_allowed`, no gate
- `ModelCatalog` as single source; `AVAILABLE_MODELS` refactored to derive from it (INV-12)
- Optional `model` field on AGENT.md frontmatter + `AgentSpec.model` + loader parse
- Global default stays Haiku

**Out of scope (from SPEC.md):**
- `GET /api/capabilities` HTTP endpoint — Phase 8 (08-08) owns it; Phase 6 only registers the catalog capability
- Frontend per-agent model picker UI — Phase 8 composer track
- `BudgetManager` / `cost_class` budget **enforcement** — Phase 11 (cost_class is metadata-only here)
- Premium/Opus gating or approval flow — N11 confirmed no gate
- Changing `build_model`'s provider selection or botocore retry tuning — preserved as single source of truth
- New model providers beyond Anthropic/Bedrock
- Re-expressing prototype as a manifest / authoring `step.model` for prototype — Phase 7

</spec_lock>

<decisions>
## Implementation Decisions

> SPEC locked the 6 requirements (WHAT) at ambiguity 0.138. These are the four HOW forks (resolver placement, catalog↔registry fit, fallback plumbing, overrides ingress), each **locked to the plan.md-grounded recommendation** per the standing directive ("honor plan.md, nothing dropped"), plus the mechanical decisions they imply. The SPEC interview already locked: backend-only; N11 (Haiku default, all incl. Opus `user_allowed` no gate, tier-descent fallback); fallback switches above botocore retries (tested w/ simulated throttle); optional AGENT.md `model` field; `cost_class` metadata-only.

### Area A — ModelResolver placement & shape

- **D-01: `ModelResolver` lives in a new kernel-importable module (`agents/model_policy.py`), carried on `ExecutionContext.model_resolver`.** It must be kernel-importable (the engine's `_run_agent` calls it per agent invocation) and follow the Phase 5 per-run-helper-on-ctx pattern (`scoped_store`/`artifacts`). `ExecutionContext` gains `model_resolver: object | None = None` typed as `object` (keeps the pure-data context module free of an inbound import, exactly as `scoped_store: object | None` is typed today). Constructed at `execute()` entry, seeded with `model_overrides`, the `CompiledWorkflow.model` (workflow default), the run-wide session `model_id`, and the global Haiku default; per-agent `step` + `AgentSpec.model` supplied at resolve time.
  - *Rejected:* a pure free function called inline at each build site (no place to hold run-level inputs / harder to guarantee one resolution path); putting it in `agents/capabilities/` (it is a kernel service, not a swappable capability port like strategies/validators).
  - **Researcher directive:** confirm import-linter permits `agents/model_policy.py` to import `agents/workflows/plan.py` (`ModelPolicy`) + the catalog module (Area B) and be imported by the kernel; confirm the `_run_agent` sites where `AgentContext.model` / `build_model(ctx.model)` are set (engine.py ~1286, ~1560, ~2033; factory.py `model=ctx.model` ~155) to rewire to the resolver.

- **D-02: Resolution precedence (highest wins), None tiers skipped — parity-preserving.**
  1. **user per-agent override** — `ctx.model_overrides[agent_id]` (run payload, Area D)
  2. **`step.model`** — `Step.model: ModelPolicy | None` from the compiled step (None in all manifests today → inert until Phase 7 authors them)
  3. **agent default** — `AgentSpec.model` (the new optional AGENT.md field, D-09)
  4. **`workflow.model`** — `CompiledWorkflow.model: ModelPolicy` (default `ModelPolicy(model=None)` today)
  5. **run default** — the session `model_id` (`user.preferred_model`) if set, **else** global Haiku (`settings.BEDROCK_INFERENCE_PROFILE_ID` / `ANTHROPIC_MODEL_ID`)
  - The session-level `model_id` becomes the **run-wide default** at the base of the order (the plan: overrides "extend today's single session-level model_id"). With every manifest/agent tier `None` today, every agent resolves to `session model_id or Haiku` = **exactly today's behavior** (INV-3 parity). Per-agent overrides refine it at the top.
  - The **session-`model_id` vs manifest-`workflow.model` precedence edge** only arises once a manifest declares `workflow.model` (Phase 7); Phase 6 treats session `model_id` as the run-wide default (parity-safe; manifest tiers are None today). Noted in Deferred.
  - *Rejected:* dropping the session `model_id` (breaks parity — existing runs would all fall to Haiku, ignoring the user's preferred model).

### Area B — ModelCatalog ↔ name-only registry fit + single source

- **D-03: `ModelCatalog` data + lookup live in a kernel-importable module (`agents/capabilities/model_catalog.py`); the registry adds the name `("model_catalog", "default")` only — matching Phase 4 D-07.** The module holds the authoritative model list and a `ModelCatalog` exposing `list()`, `get(id)`, `is_allowed(id)`, `ids()`. The `CapabilityRegistry._KNOWN` set gains `("model_catalog", "default")` as **pure membership** — NO held instance, NO `@register`/self-registration, NO `user_allowed` trust enforcement (those stay Phase 8 per D-07). The resolver + override-validator import the catalog **directly** from the module. Phase 8 later wraps it in the self-registration / `user_allowed`-trust / `/api/capabilities` machinery — **evolution, not dual implementation** (INV-12), exactly as Phase 4 D-07 framed every capability.
  - *Rejected:* building a full instance-holding capability + trust now (pulls Phase 8 forward; risks an INV-12 dual-impl when Phase 8 redoes it).
  - **Researcher directive:** confirm import-linter allows `agents/capabilities/model_catalog.py` to be kernel-pure (no `app.*` import) and importable by `agents/model_policy.py` and by `app/api/settings.py` (app→kernel is allowed).

- **D-04: `ModelCatalog` is the single source; `app/api/settings.py::AVAILABLE_MODELS` + `_VALID_MODEL_IDS` become derived projections (INV-12); `/api/settings` response shape unchanged.** The catalog owns the 5 models (Haiku 4.5 / Sonnet 4.5 / Sonnet 4.6 / Opus 4.5 / Opus 4.6) with the full field set. `AVAILABLE_MODELS` is rebuilt as a projection `[{id, name, description, tier} …]` over `ModelCatalog.list()`; `_VALID_MODEL_IDS = {m.id …}`. Keep **both** `cost_class` (new, canonical) and the legacy `tier` (display) on each catalog entry, asserting them consistent — lowest-risk for the frontend, which reads `tier`. **cost_class assignment (N11):** Haiku=`cheap`, Sonnet 4.5/4.6=`standard`, Opus 4.5/4.6=`premium`; all `user_allowed=true`, no gate.
  - *Rejected:* settings.py keeping the list as source + catalog reading it (wrong import direction — the kernel resolver can't import `app.api`); dropping `tier` (frontend display regression).
  - **Researcher directive:** grep for any second hand-maintained model list (must be 0 after this — INV-12); confirm the frontend `tier`→display mapping so the projection stays compatible.

### Area C — Fallback plumbing seam

- **D-05: Prefer LangChain `Runnable.with_fallbacks([...])` on the built model with a throttle/transient exception filter; engine-level rebuild-and-retry is the locked alternative IF `with_fallbacks` does not compose through the deepagents `astream_events` stream.** `build_model` is the single source — the deepagents graph consumes its output as a Runnable — so returning `primary.with_fallbacks([fb1, fb2], exceptions_to_handle=(…throttle…))` layers the model-switch **above** botocore adaptive retries (botocore exhausts its 5 attempts, the exception propagates, `with_fallbacks` switches). This satisfies the SPEC "switch above retries."
  - **CRITICAL researcher directive (HIGH risk):** verify `with_fallbacks` actually triggers through `DeepAgentRunner.astream_events` — when the model raises mid-stream inside the deepagents LangGraph loop, does the fallback fire? Streaming can't un-emit already-streamed tokens; if the throttle fires **before first token** (the common throttle case) it works cleanly. **If `with_fallbacks` does NOT compose through `astream_events`:** use the locked alternative — an engine-level wrapper around the per-agent run in `_run_agent` that catches the classified throttle, advances `ctx.model_resolver` to the next chain id, rebuilds the runner via `create_runner`, and re-invokes (bounded by chain length).
  - **Chain construction (N11 tier-descent):** when `ModelPolicy.fallback` is empty, the resolver derives the chain from the resolved model's `cost_class`/tier — Opus→[Sonnet, Haiku], Sonnet→[Haiku], Haiku→[] (none). An explicit `ModelPolicy.fallback` overrides the derived default. Every chain entry must be catalog-valid.
  - **Build split:** the resolver owns chain composition (it knows the policy); `build_model` stays per-id (single client) + a thin compose step. Exact split is planner's call.

- **D-06: Throttle classification + exhaustion behavior.** A shared `_is_transient_throttle(exc)` predicate matches retryable model errors — Bedrock `ThrottlingException` / botocore `ClientError` throttling codes / HTTP 429 / transient 5xx (ServiceUnavailable, InternalServerError); for ChatAnthropic (local dev) the analogue (429 / 529 / overloaded). Non-matching errors (validation/auth) propagate immediately — no switch. Chain exhaustion re-raises the **last** error. Unit-tested with a scripted model raising the throttle on model-id A and succeeding on model-id B — **no live Bedrock** (extend `tests/agents/_scripted_model.py`).

### Area D — model_overrides ingress + cost_class persistence

- **D-07: `model_overrides` enters as a new optional `execute()` parameter, threaded from the websocket `run_pipeline` payload; validated against the catalog at ingress; stored on `ExecutionContext.model_overrides`.** The websocket handler (`app/api/websocket.py` ~662, ~1154 — where `model_id=getattr(user, "preferred_model")` is read) reads `model_overrides` from the inbound run payload and passes it to `engine.execute(..., model_overrides=…)`. `execute()` gains `model_overrides: dict[str,str] | None = None`; `ExecutionContext` gains `model_overrides: dict = field(default_factory=dict)`. **Ingress validation:** each `{agent_id → model_id}` is checked — `model_id ∈ ModelCatalog.ids()` (reject unknown — never an arbitrary string, Q2 trust) AND `agent_id` is a member of the run's workflow agents — failing fast with a clear error before execution starts.
  - **Researcher directive:** confirm the inbound `run_pipeline` message schema + where `model_overrides` slots in; confirm the existing websocket **error event shape** for an invalid override; the frontend does not send it yet (Phase 8 wires the picker) — Phase 6 accepts it when present, defaults to `{}` absent.

- **D-08: `model_overrides` persisted to `run_capabilities` via `ScopedStore.record_capabilities` (Phase 5 D-12); `cost_class` is metadata-only (no budget enforcement until Phase 11).** The Phase 5 `run_capabilities` row (written at `execute()` entry, `runtime=langchain_deepagents`) now also writes the validated `model_overrides` map — filling the column Phase 5 reserved (Phase 5 deferred list: "model_overrides population — Phase 6"). Whether the per-agent resolved `cost_class` set is also recorded (e.g. in `versions`) is planner's call; at minimum `model_overrides` is persisted (MODEL-03). `cost_class` rides on the resolved `ModelPolicy` and is recorded but drives **no** budget gate this phase (§20 "cost_class informs BudgetManager" tie-in deferred to Phase 11).
  - **Researcher directive:** confirm the `ScopedStore.record_capabilities` signature (Phase 5 `agents/authz.py`) and whether the row is inserted at entry or upserted at completion (Phase 5 left this discretionary) — `model_overrides` is known at entry, so insert-at-entry works.

- **D-09: AGENT.md optional `model` field — loader + `AgentSpec` (backs D-02 tier 3).** `agents/loader.py::AgentSpec` gains `model: str | None = None`; the loader parses an optional `model:` frontmatter field (absent → `None`). Lean: validate against `ModelCatalog.ids()` at load time for fail-fast (consistent with the loader's per-field validation pattern) — planner may instead defer to resolve-time. No existing AGENT.md adds it (absent=None) → the loader schema test stays green for all ~80 agents.

### Claude's Discretion
- Exact module name (`agents/model_policy.py` vs `agents/capabilities/model_resolver.py`) and the resolver method signature (returns `ModelPolicy` vs `(id, chain)`).
- Whether `build_model` composes the `with_fallbacks` chain or the resolver does.
- Whether AGENT.md `model` is validated at load or resolve time (D-09).
- Whether the resolved `cost_class` set (beyond `model_overrides`) is recorded in `run_capabilities` (D-08).
- Whether `run_capabilities` is inserted at entry or upserted at completion (carried from Phase 5 D-12), provided `model_overrides` lands.
- The `tier`↔`cost_class` representation (store-both vs derive) within D-04.
- Plan-task granularity / split.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/06-model-policy-1c/06-SPEC.md` — the 6 locked requirements (MODEL-01..05 + the AGENT.md `model` field), boundaries, acceptance criteria. **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`)
- **§20** — Model policy + per-agent model selection (A10/A12): the precedence order, the `ModelPolicy` field set (model id, `max_tokens` doc-only, `cost_class`, ordered `fallback`), `ModelCatalog` (label/provider/cost_class/window/`user_allowed`), the `model_overrides` run-payload + persistence, and the `cost_class`→`BudgetManager` tie-in **(deferred to Phase 11)**. Resolves/extends N11.
- **§18** — Persistence schema: `run_capabilities` row carries **`model_overrides {agent→model}`** (the column populated this phase); every table carries `owner_id` + `workspace_id`; additive only.
- **§22** — API/frontend contract: `GET /api/capabilities` surfaces the catalog + the per-agent model picker **— Phase 8, NOT this phase** (confirms the backend-only boundary).
- **§7 / §30** — Capability registry + trust model: engineers register, manifests reference; `user_allowed`/self-registration are **Phase 8** (D-03 keeps the registry name-only).
- **§32** — Target directory structure + Ports & Adapters + import-linter direction (kernel-importable `agents/` modules must not pull `app.*`; D-01/D-03 placement).

### Project planning
- `.planning/REQUIREMENTS.md` — MODEL-01..05 (lines 60–64) with plan anchors; the Phase 6 traceability row (line 231).
- `.planning/ROADMAP.md` § Phase 6 — goal + the 06-01/02/03 candidate plan breakdown; surrounding phases that bound deferral (Phase 8 = `/api/capabilities` + composer picker; Phase 11 = `BudgetManager`; Phase 7 = prototype-as-manifest where `step.model` gets authored).
- `.planning/PROJECT.md` — invariants (INV-1 no name branches, INV-3 parity byte-identical+semantic, INV-12 no dual impl, INV-13 deepagents-only via `build_model`); Key Decisions (A12 per-agent model selection at top of order; **N11 resolved by the SPEC**); "nothing from plan.md dropped".
- `.planning/phases/04-manifest-compiler-1a/04-CONTEXT.md` — D-06 (the inert `ModelPolicy`/`Step.model`/`CompiledWorkflow.model` fields this phase makes live); D-07 (name-only registry → self-registration/trust/`/api/capabilities` are Phase 8 — the evolution D-03 follows).
- `.planning/phases/05-typed-artifacts-persistence-ownership-1b/05-CONTEXT.md` — D-09 (per-run helpers on `ExecutionContext`; the byte-identity guard); D-12 (`run_capabilities` row at `execute()` entry, `model_overrides` column reserved for Phase 6); the `ScopedStore.record_capabilities` persistence path.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — Phase 6 flips **no** L-rows (no leak deletion this phase); confirm the ratchet does not regress.

### Code to read (targets / assets)
- `backend/app/agents/model_factory.py` — `build_model(model, max_tokens)` (the single source; gains `ModelPolicy`/fallback composition — do NOT fork provider select or botocore retries); `model_identifier`.
- `backend/agents/execution_engine/context.py` — `ExecutionContext` (add `model_resolver: object | None` + `model_overrides: dict`; typed to keep the module import-pure, like `scoped_store`).
- `backend/agents/execution_engine/engine.py` (~146 KB) — `execute()` entry (~537; add `model_overrides` param, construct the resolver, write `run_capabilities.model_overrides`); the `_run_agent` model sites (~1286, ~1560, ~2033 — `model=model_id` → resolver); the `SmartPlanner(model_id=…)` path (~1432, decide whether the planner participates in resolution).
- `backend/agents/workflows/plan.py` — `ModelPolicy` (lines 64–72), `Step.model` (line 209), `CompiledWorkflow.model` (line 248): **inert → live**; the field set is already correct (no churn).
- `backend/agents/capabilities/registry.py` — `_KNOWN` set (add `("model_catalog","default")` membership); `base.py` ports (a catalog is **data**, not a behavior port — likely no new Protocol; planner's call).
- `backend/agents/loader.py` — `AgentSpec` (add `model: str | None`) + `load_agent_spec` per-field validation (D-09).
- `backend/agents/factory.py` — `AgentContext.model` (line 44) + `create_runner` `model=ctx.model` (line 155); rewire to the resolved id/policy.
- `backend/app/api/settings.py` — `AVAILABLE_MODELS` (lines 40–71) + `_VALID_MODEL_IDS` (line 74) → derive from the catalog; `UserPreferencesResponse.available_models` shape stays unchanged.
- `backend/app/api/websocket.py` — the `run_pipeline` handler (~662, ~1154 `model_id` read) — add `model_overrides` ingress + validation + the error surface.
- `backend/app/models/run_capabilities.py` — `model_overrides = Column(JSON, nullable=True)  # Phase 6` (populated now).
- `backend/agents/authz.py` — `ScopedStore.record_capabilities` (Phase 5) — persist `model_overrides`.
- `backend/app/core/config.py` — `ANTHROPIC_MODEL_ID`/`BEDROCK_INFERENCE_PROFILE_ID` (Haiku global default), `MAX_OUTPUT_TOKENS` (the runtime cap `max_tokens` must not exceed).
- `backend/tests/agents/_scripted_model.py` — the offline `BaseChatModel` pattern; extend to raise a throttle for the D-06 simulated-fallback test.
- `backend/CLAUDE.md` — runtime (`build_model` = single source; model user-selected, Haiku default); commit scopes (`sandbox` for model_factory, plus `engine`/`registry`/`loader`/`factory`/`tests`); dev runtime `python3.11`, no venv.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`app/agents/model_factory.py::build_model`** — the single source for the chat model; already embeds botocore adaptive retries (5 attempts). Extend (compose `with_fallbacks` / accept a `ModelPolicy`), do NOT fork — the model-switch layers above the retries that already live here.
- **`tests/agents/_scripted_model.py`** — the minimal offline `BaseChatModel` that drives the deepagents loop; extend it to raise `ThrottlingException` on a given model id for the simulated-fallback unit test (no live Bedrock).
- **`agents/authz.py::ScopedStore.record_capabilities`** (Phase 5) — the owner-scoped persistence path that already writes the `run_capabilities` row; fill its reserved `model_overrides` column here.
- **`agents/loader.py` `AgentSpec` + per-field validation** — the pattern for adding the optional `model` field (D-09), mirroring `max_tokens` validation.
- **`ExecutionContext` per-run-helper pattern** (Phase 5 `scoped_store`/`artifacts`, typed `object`) — the resolver rides on ctx the same way, import-pure.
- **`CapabilityRegistry._KNOWN` name-membership** (Phase 4) — add `("model_catalog","default")` the same way (no impl).
- **`app/api/settings.py::AVAILABLE_MODELS`** — the 5-model list (with `tier`) is the **seed** for the catalog; becomes a derived projection.

### Established Patterns
- **INV-3 parity** — a run with no overrides + no manifest model fields resolves to `session model_id or Haiku` = today's exact behavior; 0A/0C characterization snapshots stay green.
- **INV-12 no dual implementations** — the catalog is the single source; `AVAILABLE_MODELS` derives. Adding the catalog without removing the hand-maintained list = not done.
- **INV-13 deepagents-only** — the resolved model reaches the graph ONLY through `build_model`.
- **Phase-8 evolution (Phase 4 D-07)** — name-only registry now → self-registration / `user_allowed` trust / `/api/capabilities` later. Not a dual implementation.
- **Additive only (Q3)** — `run_capabilities.model_overrides` column already exists (migration 0014); **no new migration** needed; `run_capabilities` already carries `owner_id` + `workspace_id`.
- **Allow-list trust (Q2)** — model selection from the catalog only; never an arbitrary string (validated at override ingress + AGENT.md load).
- **Dev runtime** — `python3.11`, no venv; `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v`; PR off `feature/003-workflow-engine-decoupling`, never `main`.

### Integration Points
- **Net-new:** `agents/model_policy.py` (`ModelResolver`); `agents/capabilities/model_catalog.py` (`ModelCatalog`).
- **Grows:** `ExecutionContext` (+`model_resolver`, +`model_overrides`); `build_model` (+`ModelPolicy`/fallback compose); `execute()` (+`model_overrides` param, resolver construction, capabilities write); `_run_agent` (model sites → resolver); `AgentSpec`/loader (+`model`); `registry._KNOWN` (+`model_catalog`); `app/api/settings.py` (`AVAILABLE_MODELS` derives); `app/api/websocket.py` (`run_pipeline` +`model_overrides` ingress); the `run_capabilities` write (+`model_overrides`).
- **Reads (inert → live):** `Step.model` / `CompiledWorkflow.model` / the new `AgentSpec.model` — read by the resolver; not authored in manifests this phase.
- **CI gates that constrain the work:** 0A/0C characterization snapshots (parity), import-linter (kernel→ports; `model_policy` + `model_catalog` kernel-importable, no `app.*` in the catalog), migration-ledger (no regression), banned-pattern (deepagents-only).

</code_context>

<specifics>
## Specific Ideas

- **Standing project directive (init):** "everything from plan.md must be honored — nothing dropped." Every lock above takes the plan-faithful option (resolver on ctx; catalog as single source via projection; `with_fallbacks` above retries; overrides validated at ingress + persisted).
- **Mode:** the user dismissed the per-area discussion (mirrors Phases 1/2/4/5 "lock all to recommendations"). Treat D-01..D-09 as locked unless this file is edited before planning.
- **SPEC interview already locked** (do not re-litigate): backend-only (no `/api/capabilities` endpoint, no frontend picker — Phase 8); N11 (Haiku global default; all models incl. Opus `user_allowed`, no gate; default tier-descent fallback); fallback switches **above** botocore retries, proven by a simulated-throttle unit test (no live Bedrock); optional AGENT.md `model` field; `cost_class` metadata-only (budget tie-in → Phase 11).
- **The main research risk:** `with_fallbacks` composing through the deepagents `astream_events` stream (D-05). If it doesn't, engine-level rebuild-and-retry is the locked alternative — this is a binary the researcher must resolve before planning task granularity.

</specifics>

<deferred>
## Deferred Ideas

- **`GET /api/capabilities` endpoint + dynamic composer + per-agent model picker UI** — Phase 8 (API-02/03/06; plan 08-08). Phase 6 only registers the catalog capability so Phase 8 can surface it.
- **Capability self-registration (`@register`/`discover()`) + `user_allowed` trust flags + owner allow-list** — Phase 8 (CAP-02/03). Phase 6 keeps the registry name-only (D-03).
- **`cost_class` → `BudgetManager` enforcement** (reserve-before-spawn, budget caps, premium-step upgrade) — Phase 11. `cost_class` is recorded as metadata only here.
- **Manifests declaring `step.model` / `workflow.model`** (prototype re-expression) — Phase 7 (parity proof). Phase 6 READS the fields; it does not author manifest model values.
- **Session-`model_id` vs manifest-`workflow.model` precedence edge** — only arises once a manifest declares `workflow.model` (Phase 7). Phase 6 treats the session `model_id` as the run-wide default (parity-safe; manifest tiers are `None` today).
- **New model providers beyond Anthropic/Bedrock** — not this milestone; `build_model`'s provider selection is unchanged.

None of these are scope creep — all are explicitly later-phase per ROADMAP.md / the SPEC boundary.

</deferred>

---

*Phase: 6-model-policy-1c*
*Context gathered: 2026-06-08*

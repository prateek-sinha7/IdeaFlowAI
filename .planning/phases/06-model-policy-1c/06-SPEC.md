# Phase 6: Model Policy [1C] — Specification

**Created:** 2026-06-08
**Ambiguity score:** 0.138 (gate: ≤ 0.20)
**Requirements:** 6 locked

## Goal

A `ModelResolver` on `ExecutionContext` selects the effective model per agent invocation by a fixed precedence (user per-agent override > `step.model` > agent default in AGENT.md > `workflow.model` > global default Haiku), drives `model_factory.build_model` through a `ModelPolicy` (id + cost_class + ordered fallback), switches to the next model in the fallback chain on a sustained throttle/error, and persists the per-run `model_overrides` map — with existing single-model runs resolving to today's Haiku default unchanged.

## Background

Today a **single** session-level model id flows through the whole run: `user.preferred_model` → `app/api/websocket.py` → `ExecutionEngine.execute(model_id=…)` → threaded to `AgentContext.model` → `app/agents/model_factory.py::build_model(ctx.model)`. One model per run; no per-agent, per-step, or per-workflow selection.

`build_model(model, max_tokens)` is the single source of truth for provider selection (ChatAnthropic local / ChatBedrockConverse prod) and embeds botocore **adaptive retries (5 attempts)** for transient HTTP-layer throttling — but has **no model-level fallback** (a sustained throttle/error on one model id aborts the agent).

Scaffolding from Phase 4/5 is already in place but **inert**:
- `agents/workflows/plan.py::ModelPolicy` exists (`model`, `max_tokens`, `cost_class`, `fallback`) — no code reads it.
- `Step.model: ModelPolicy | None` and `CompiledWorkflow.model: ModelPolicy` are declared-but-inert forward surface.
- `app/models/run_capabilities.py::model_overrides` JSON column exists (migration 0014) — nothing writes it.
- `ExecutionContext` has **no** `model_resolver` field (the context docstring explicitly defers it).

`AVAILABLE_MODELS` (5 models with `id`/`name`/`description`/`tier`) lives in `app/api/settings.py`, validated by `_VALID_MODEL_IDS`, surfaced only via `/api/settings` — it is **not** a registered capability and lacks `provider`/`cost_class`/`context_window`/`user_allowed`. There is **no `ModelResolver`, `ModelCatalog`, or `/api/capabilities` endpoint** yet, and AGENT.md frontmatter has **no `model` field**. N11 (premium-model policy + default fallback chain) was an open decision — confirmed in this spec's interview.

## Requirements

1. **ModelResolver + resolution order**: A `ModelResolver` resolves the effective model id per agent invocation by fixed precedence (highest wins): user per-agent override > `step.model` > agent default (AGENT.md `model`) > `workflow.model` > global default (Haiku). (MODEL-01, MODEL-05)
   - Current: No resolver exists; a single `model_id` threads `execute()` → `AgentContext.model` → `build_model`. `ExecutionContext` has no `model_resolver` field.
   - Target: A `ModelResolver` is constructed at `execute()` entry, carried on `ExecutionContext`, and consulted per agent. With nothing set at any tier it returns the global Haiku default.
   - Acceptance: 5 precedence unit tests pass (override beats step; step beats agent; agent beats workflow; workflow beats global; global = Haiku when all empty). With no override/step/workflow/agent model set, the resolver returns the same model id the run uses today.

2. **ModelPolicy drives build_model**: The resolved selection is expressed as a `ModelPolicy` (model id, `max_tokens` doc-only, `cost_class`, ordered `fallback`) that drives `model_factory.build_model`. (MODEL-02)
   - Current: `ModelPolicy` exists but is inert; `build_model` takes a bare model-id string + `max_tokens`; no `cost_class`, no fallback are read.
   - Target: The resolver produces/consults a `ModelPolicy` and calls `build_model` with the resolved id. `max_tokens` stays doc-only (runtime still caps at `settings.MAX_OUTPUT_TOKENS`). `cost_class` is carried/persisted as metadata only — **no budget enforcement this phase**.
   - Acceptance: A `ModelPolicy` with `model="<opus-id>"` yields a `build_model` call with that id; a `max_tokens` value in the policy does NOT change the runtime cap (still `settings.MAX_OUTPUT_TOKENS`); the resolved `cost_class` is recorded on the persisted `run_capabilities` row.

3. **Fallback chain fires on throttle/error**: A model-switch layer above the existing botocore retries advances to the next model in the policy's `fallback` chain when one model id sustains a throttle/error. (MODEL-02)
   - Current: `build_model` has botocore adaptive retries (5 attempts) at the HTTP layer but no model-level fallback — a sustained throttle/error aborts the agent.
   - Target: When an agent invoke raises a throttle (Bedrock `ThrottlingException` / HTTP 429) or transient 5xx **after** botocore retries are exhausted, the resolver advances to the next id in the chain and rebuilds. Chain exhaustion re-raises the original error. Default chains step down the tier: Opus→Sonnet→Haiku, Sonnet→Haiku, Haiku→(none).
   - Acceptance: A simulated-throttle unit test (scripted model raises `ThrottlingException` on the first chain id, succeeds on the next) confirms the resolver advances and the run completes on the fallback model — **no live Bedrock dependency**. A test where every chain entry throttles confirms the original error is re-raised after exhaustion.

4. **Per-agent model_overrides accepted + persisted**: The run payload accepts an optional `model_overrides: {agent_id → model_id}` map applied at the TOP of the resolution order and persisted per run. (MODEL-03)
   - Current: The run payload carries a single session-level `model_id`; `run_capabilities.model_overrides` exists but nothing writes it.
   - Target: `model_overrides` extends (does not replace) the single `model_id`, is applied above `step.model`, validated against the `ModelCatalog` allow-list (unknown id rejected — never an arbitrary string), and written to `run_capabilities.model_overrides` for the run.
   - Acceptance: A run with `model_overrides={"agent-x": "<sonnet-id>"}` resolves `agent-x` to Sonnet and every other agent to the run/global default; the run's `run_capabilities` row has `model_overrides == {"agent-x": "<sonnet-id>"}`; a value not in the catalog is rejected with a clear error.

5. **ModelCatalog registered capability (single source)**: A `ModelCatalog` registered capability lists selectable models with `label`, `provider`, `cost_class` (cheap/standard/premium), context window, and `user_allowed` — and becomes the single source of model metadata. (MODEL-04)
   - Current: `AVAILABLE_MODELS` lives in `app/api/settings.py` (only `id`/`name`/`description`/`tier`), is not a capability, and lacks `provider`/`cost_class`/`context_window`/`user_allowed`. The capability registry has 14 names, no model-catalog kind.
   - Target: A `ModelCatalog` capability registered by `(kind, name)` lists every selectable model with the full field set; all models incl. premium (Opus) are `user_allowed=true` with no gate (N11). It is the single source — the legacy `AVAILABLE_MODELS` is refactored to **derive from** the catalog (no parallel hand-maintained list — INV-12), with the `/api/settings` response shape unchanged.
   - Acceptance: `ModelCatalog` enumerates entries each carrying `label`, `provider`, `cost_class`, `context_window`, `user_allowed`; the id set equals the project allow-list; Opus entries have `user_allowed=true`; the capability is discoverable via the registry by `(kind, name)`; `AVAILABLE_MODELS` is derived from the catalog (grep shows no second hand-maintained model list) and `/api/settings` still returns the same shape.

6. **AGENT.md optional `model` field**: AGENT.md frontmatter gains an optional `model` field that backs the resolver's agent-default tier. (supports MODEL-01)
   - Current: AGENT.md frontmatter has `max_tokens` but no `model`; `AgentSpec` has no `model` attribute; the "agent default (AGENT.md)" tier has no backing field.
   - Target: An optional `model` field (a catalog model id, or absent) parses onto `AgentSpec.model` (`None` when absent). The resolver reads it as the agent-default tier. Fully additive — no existing AGENT.md must add it (absent = `None` = no agent preference).
   - Acceptance: An AGENT.md with `model: "<id>"` loads with `AgentSpec.model == "<id>"`; one without loads with `AgentSpec.model is None`; the loader schema test stays green for all existing agents; the resolver uses `AgentSpec.model` only when no override/step model is set.

## Boundaries

**In scope:**
- `ModelResolver` (fixed precedence) constructed at `execute()` entry and carried on `ExecutionContext`
- `ModelPolicy` wired into `build_model` (resolved id + `cost_class` metadata + ordered `fallback`)
- Model-switch fallback layer above botocore retries (throttle/429/transient-5xx after retries → next chain entry; exhaustion re-raises), unit-tested with a simulated throttle
- Default tier-descent fallback chains (Opus→Sonnet→Haiku, Sonnet→Haiku, Haiku→none)
- `model_overrides: {agent_id → model_id}` accepted in the run payload, applied at top of order, validated against the catalog, persisted to `run_capabilities.model_overrides`
- `ModelCatalog` registered capability (label/provider/cost_class/context_window/user_allowed); all models incl. Opus `user_allowed`, no gate
- `ModelCatalog` as single source; `AVAILABLE_MODELS` refactored to derive from it (INV-12)
- Optional `model` field on AGENT.md frontmatter + `AgentSpec.model` + loader parse
- Global default stays Haiku

**Out of scope:**
- `GET /api/capabilities` HTTP endpoint — Phase 8 (08-08) owns it; Phase 6 only registers the catalog capability so Phase 8 can surface it
- Frontend per-agent model picker UI — Phase 8 composer track
- `BudgetManager` / `cost_class` budget **enforcement** — Phase 11 (cost_class is metadata-only here)
- Premium/Opus gating or approval flow — N11 confirmed no gate
- Changing `build_model`'s provider selection or botocore retry tuning — preserved as the single source of truth
- New model providers beyond Anthropic/Bedrock — no provider abstraction change
- Re-expressing prototype as a manifest / exercising `step.model` for prototype — Phase 7 (prototype stays single-model unless an override is given; manifest `step.model` is honored by the resolver but not driven from a prototype manifest yet)

## Constraints

- **Tech stack / runtime:** Python · FastAPI · LangChain `deepagents` (INV-13). The model reaches every graph only through `build_model`; `build_model` stays the single source of truth for provider selection + botocore retries — do not fork it.
- **INV-3 (parity):** Existing workflows with no overrides must resolve to today's model (Haiku default) and stay at deliverable + semantic-event parity; no new events for existing single-model runs. 0A/0C characterization snapshots stay green.
- **INV-12 (no dual implementations):** `ModelCatalog` is the single source of model metadata; `AVAILABLE_MODELS` must derive from it, not duplicate it.
- **Additive migrations only (Q3):** `run_capabilities.model_overrides` already exists (0014) — persistence needs no new migration; any added column is additive and `run_capabilities` already carries `owner_id` + `workspace_id`.
- **Allow-list trust (Q2):** model selection is from the catalog allow-list only — never an arbitrary string.
- **Test isolation:** the fallback path must be exercised with a **simulated** throttle (scripted model) — no live Bedrock dependency in CI.
- **max_tokens stays doc-only:** runtime caps at `settings.MAX_OUTPUT_TOKENS` (unchanged); a `ModelPolicy.max_tokens` never raises the runtime cap.
- **Global default:** Haiku (`eu.anthropic.claude-haiku-4-5-…` / `claude-haiku-4-5-…`) — unchanged.

## Acceptance Criteria

- [ ] `ModelResolver` resolves by precedence: user override > `step.model` > agent (AGENT.md) > `workflow.model` > global(Haiku) — 5 precedence unit tests pass
- [ ] With nothing set at any tier, the resolver returns the global Haiku default; existing single-model runs are unchanged (0A/0C snapshots green, INV-3)
- [ ] `ModelPolicy` drives `build_model` with the resolved id; a policy `max_tokens` does NOT change the runtime cap (still `MAX_OUTPUT_TOKENS`)
- [ ] The resolved `cost_class` is recorded on the persisted `run_capabilities` row (metadata only — no budget enforcement)
- [ ] Simulated-throttle test: first chain model raises `ThrottlingException`, resolver advances to the next model, run completes on the fallback model — no live Bedrock
- [ ] Chain-exhaustion test: every chain entry throttles → original error re-raised
- [ ] Default fallback chains are tier-descent: Opus→Sonnet→Haiku, Sonnet→Haiku, Haiku→(none)
- [ ] A run with `model_overrides={agent→id}` resolves that agent to the override and persists `model_overrides` to its `run_capabilities` row
- [ ] A `model_overrides` value not in the catalog is rejected with a clear error (no arbitrary strings)
- [ ] `ModelCatalog` lists models each with `label`, `provider`, `cost_class`, `context_window`, `user_allowed`; Opus entries `user_allowed=true`; discoverable via the capability registry
- [ ] `AVAILABLE_MODELS` derives from the catalog (no parallel hand-maintained list — INV-12); `/api/settings` response shape unchanged
- [ ] AGENT.md optional `model` field parses onto `AgentSpec.model` (`None` when absent); loader schema test green for all existing agents
- [ ] `GET /api/capabilities` endpoint and the frontend model picker are NOT added in this phase (deferred to Phase 8) — confirmed absent

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                             |
|--------------------|-------|------|--------|-------------------------------------------------------------------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | Resolution order + 3 components + fallback precisely specified     |
| Boundary Clarity   | 0.88  | 0.70 | ✓      | Backend-only locked; /api/capabilities + picker → Phase 8          |
| Constraint Clarity | 0.85  | 0.65 | ✓      | Fallback = switch above botocore retries; simulated-throttle tests |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | 13 pass/fail checks, all falsifiable                              |
| **Ambiguity**      | 0.138 | ≤0.20| ✓      | Gate passed in round 1                                            |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective      | Question summary                              | Decision locked                                                                 |
|-------|------------------|-----------------------------------------------|---------------------------------------------------------------------------------|
| 1     | Boundary Keeper  | Where does Phase 6 stop (endpoint/UI)?        | Backend-only; `/api/capabilities` + frontend picker deferred to Phase 8         |
| 1     | Researcher/Simpl | N11: premium policy + default fallback chain  | All models incl. Opus `user_allowed`, no gate; default tier-descent fallback     |
| 1     | Failure Analyst  | What fires fallback; how far is it wired?     | Model-switch above botocore retries; throttle/429/5xx after retries → next entry; implemented + unit-tested w/ simulated throttle |
| —     | Boundary Keeper  | (derived) agent-default tier backing field    | Add optional `model` field to AGENT.md (absent = `None`); additive/back-compat   |
| —     | Boundary Keeper  | (derived) cost_class budget tie-in            | Metadata-only this phase; `BudgetManager` enforcement → Phase 11                 |

---

*Phase: 06-model-policy-1c*
*Spec created: 2026-06-08*
*Next step: /gsd-discuss-phase 6 — implementation decisions (resolver placement, fallback retry plumbing, catalog source-of-truth refactor)*

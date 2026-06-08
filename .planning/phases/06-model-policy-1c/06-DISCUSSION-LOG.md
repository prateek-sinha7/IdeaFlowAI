# Phase 6: Model Policy [1C] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 6-model-policy-1c
**Areas discussed:** Resolver placement & shape, Catalog↔registry fit + single source, Fallback plumbing seam, Overrides ingress + cost_class — all **locked to plan-grounded recommendations** (user dismissed the per-area drill-down, mirroring Phases 1/2/4/5).

---

## Resolver placement & shape

| Option | Description | Selected |
|--------|-------------|----------|
| New kernel module + `ctx.model_resolver` | `ModelResolver` in `agents/model_policy.py`, carried on `ExecutionContext` (Phase 5 helper pattern), `resolve(agent_id, step)→ModelPolicy` | ✓ (recommendation) |
| Pure inline function at each build site | No run-level state holder; harder to guarantee one resolution path | |
| Put it under `agents/capabilities/` | It's a kernel service, not a swappable capability port | |

**User's choice:** Dismissed drill-down → locked to recommendation (D-01/D-02).
**Notes:** Precedence locked parity-preserving: override > step.model > AGENT.md > workflow.model > run default (session `model_id` else Haiku). None tiers skipped; with all manifest tiers None today, every agent = today's behavior (INV-3).

---

## Catalog ↔ registry fit + single source

| Option | Description | Selected |
|--------|-------------|----------|
| Name in registry + kernel data module; AVAILABLE_MODELS derives | `("model_catalog","default")` membership only (Phase 4 D-07); catalog data in `agents/capabilities/model_catalog.py`; settings projects from it | ✓ (recommendation) |
| Full instance-holding capability + trust now | Pulls Phase 8 self-registration/`user_allowed` forward; risks INV-12 dual-impl | |
| settings.py stays source; catalog reads it | Wrong import direction (kernel resolver can't import `app.api`) | |

**User's choice:** Dismissed drill-down → locked to recommendation (D-03/D-04).
**Notes:** Single source (INV-12). cost_class: Haiku=cheap, Sonnet=standard, Opus=premium; all `user_allowed=true` (N11). Keep both `cost_class` (canonical) + legacy `tier` (display) for frontend compatibility.

---

## Fallback plumbing seam

| Option | Description | Selected |
|--------|-------------|----------|
| LangChain `with_fallbacks()` above botocore retries | Idiomatic; composes wherever the model is used; exception filter on throttle/429/5xx | ✓ (recommendation, pending research) |
| Engine-level rebuild-and-retry around `_run_agent` | Catch throttle, advance chain, rebuild runner, re-invoke | ✓ (locked alternative if with_fallbacks fails through astream_events) |
| Custom wrapper chat model | More invasive; build_model only constructs the client | |

**User's choice:** Dismissed drill-down → locked to recommendation (D-05/D-06).
**Notes:** CRITICAL research risk — does `with_fallbacks` trigger through `DeepAgentRunner.astream_events` streaming? If not, engine-level rebuild-and-retry is the locked fallback. Tier-descent default chain (Opus→Sonnet→Haiku). Tested with a simulated throttle (no live Bedrock).

---

## Overrides ingress + cost_class

| Option | Description | Selected |
|--------|-------------|----------|
| New `execute()` param from run payload, validated at ingress, persisted via ScopedStore | websocket `run_pipeline` → `execute(model_overrides=)` → ctx; validate against catalog + workflow membership; write `run_capabilities.model_overrides` | ✓ (recommendation) |
| Validate deep in the resolver | Slower failure; resolver should stay pure | |

**User's choice:** Dismissed drill-down → locked to recommendation (D-07/D-08/D-09).
**Notes:** cost_class persisted as metadata only — no budget enforcement (BudgetManager is Phase 11). AGENT.md gains optional `model` field (D-09). model_overrides validated against catalog (no arbitrary strings, Q2).

---

## Claude's Discretion

- Exact module name + resolver method signature; whether build_model or the resolver composes the fallback chain; AGENT.md `model` validated at load vs resolve time; whether resolved cost_class (beyond overrides) is recorded; run_capabilities insert-at-entry vs upsert-at-completion; `tier`↔`cost_class` representation; plan-task granularity.

## Deferred Ideas

- `/api/capabilities` endpoint + composer + per-agent picker UI — Phase 8.
- Capability self-registration + `user_allowed` trust — Phase 8.
- `cost_class` → BudgetManager enforcement — Phase 11.
- Manifests authoring `step.model`/`workflow.model` (prototype re-expression) — Phase 7.
- Session-`model_id` vs manifest-`workflow.model` precedence edge — Phase 7 (manifest tiers None today).
- New model providers beyond Anthropic/Bedrock — not this milestone.

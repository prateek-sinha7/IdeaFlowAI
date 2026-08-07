---
id: REQ-6
type: req
status: done
area: [workflow, agents, auth, runtime]
summary: >-
  Model Policy & Per-Agent Selection (Phase 1C)
source: .planning/REQUIREMENTS.md#model-policy-per-agent-selection-phase-1c
---

### Model Policy & Per-Agent Selection (Phase 1C)

- [x] **MODEL-01**: `ModelResolver` on `ExecutionContext` applies resolution order (highest wins): user per-agent override > `step.model` > agent default (AGENT.md) > `workflow.model` > global default (Haiku) (§20 / A10)
- [x] **MODEL-02**: `ModelPolicy` carries model id, `max_tokens` (doc-only; runtime caps at `MAX_OUTPUT_TOKENS`), `cost_class` (cheap/standard/premium), ordered `fallback` chain on throttle/error (§20)
- [x] **MODEL-03**: User per-agent `model_overrides: {agent_id → model_id}` applied at the top of the order and persisted per run (A12 / §18 `run_capabilities`)
- [x] **MODEL-04**: `ModelCatalog` registered capability lists selectable models (label, provider, cost_class, context window, `user_allowed`); surfaced via `/api/capabilities` (§20)
- [x] **MODEL-05**: Global default stays Haiku with an ordered `fallback` chain on throttle/error; per-step/workflow model honored; premium (`cost_class=premium`) models selectable by ALL tiers — **premium-open-to-all-tiers** (no per-tier premium gating) (Phase 1C Accept / N11 — DECIDED premium-open-to-all-tiers, Phase 22 / DECIDE-02)

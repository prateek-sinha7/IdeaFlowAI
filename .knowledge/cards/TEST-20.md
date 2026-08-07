---
id: TEST-20
type: test
status: done
area: [sse, agents, auth]
summary: >-
  TS-E — Per-agent model selection (AgentModelPicker) — the live model-selection
  surface
source: .planning/TEST-REGISTER.md#ts-e-per-agent-model-selection-agentmodelpicker
covers: [TS-E-01, TS-E-02, TS-E-03, TS-E-04, TS-E-05, TS-E-06, BE-MODEL-04]
---

### TS-E — Per-agent model selection (AgentModelPicker) — **the live model-selection surface**

In AgentsPopup → Agents tab footer. Header `Per-Agent Model`. Options are **live from `GET /api/capabilities → model_catalog` (filtered `user_allowed`)** — not hardcoded; the only static option text is `Default`.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-E-01 | States | open with no agents / unauth / loaded | no agents → `Add agents to assign per-agent models.`; loading → `Loading model catalog…`; no JWT → `Not authenticated.`; loaded → one `<select>` per agent, first option `Default` | 🔴 |
| TS-E-02 | Catalog reflects backend | inspect the `<select>` options | option set == `model_catalog` labels where `user_allowed` (cross-check `GET /api/capabilities`); each `<option value>` == model `id`, text == `label` | 🔴 |
| TS-E-03 | **Pick a non-default model per agent** | for agent A choose e.g. `Sonnet 4.6`; leave agent B `Default` | selection persists in the picker; on Run the `run_pipeline` payload carries `model_overrides:{ "<A.id>":"<sonnet-id>" }` (B omitted) — assert on the WS frame (TS-H) | 🔴 |
| TS-E-04 | Default removes override | re-select `Default` for agent A | that agent's key removed from `model_overrides`; if all Default → field omitted entirely (byte-identical payload) | 🔴 |
| TS-E-05 | Override reflected post-run | run with an override | on `pipeline_complete`, the Token Usage card cost label shows the resolved model short-name (`Est. cost (Sonnet 4.6)`); backend `model_id` matches | 🔴 (live) |
| TS-E-06 | Bogus override rejected | (negative) inject an invalid model id on the wire | backend refuses **before** run starts: `{type:"error", code:"invalid_model_override"}`; no execution view progress | 🟢 (BE-MODEL-04) / 🔴 UI |

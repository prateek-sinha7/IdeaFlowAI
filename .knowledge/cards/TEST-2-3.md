---
id: TEST-2-3
type: test
status: done
area: [workflow, agents, auth]
summary: >-
  2.3 Model policy / catalog / overrides (register part 06)
source: .planning/TEST-REGISTER.md#2-3-model-policy-catalog-overrides-register-part
covers: [BE-MODEL-01, BE-MODEL-02, BE-MODEL-03, BE-MODEL-04, BE-MODEL-05, BE-MODEL-06]
---

### 2.3 Model policy / catalog / overrides  (register part 06)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-MODEL-01 | `ModelCatalog` is the **single** model-id source (5 frozen entries: Haiku 4.5, Sonnet 4.5/4.6, Opus 4.5/4.6); literals live only here | `pytest tests/agents/test_model_catalog.py` (9) | 🟢 |
| BE-MODEL-02 | 5-tier precedence: override > step.model > AGENT.md > workflow.model > session/global Haiku; tier-5 default = INV-3 anchor | `pytest tests/unit/test_model_resolver.py` (25) | 🟢 |
| BE-MODEL-03 | Tier-descent fallback chains from `cost_class`; transient-throttle classifier → bounded engine rebuild-retry + `agent_model_fallback` event (never `with_fallbacks`) | `pytest tests/agents/test_model_fallback.py` (4); `grep with_fallbacks` → 0 | 🟢 |
| BE-MODEL-04 | **`_validate_model_overrides` ingress gate:** per-run `{agent_id→model_id}` checked vs `ModelCatalog.ids()` AND `run_agent_ids`; malformed/bogus rejected **before** `WorkflowRun` created → `code:"invalid_model_override"` | `pytest tests/unit/test_run_pipeline_validation.py` (50); WS msg with bogus id → error frame | 🟢 |
| BE-MODEL-05 | `GET /api/capabilities` (JWT) → `{capabilities:[…user_allowed…], model_catalog:[…]}`; 401 unauth | `pytest tests/unit/test_capabilities_api.py` (8) | 🟢 → drives UI TS-E |
| BE-MODEL-06 | No-override run = byte/semantic-identical (every tier `None` today) | 5 goldens unchanged | 🟢 char-locked |

---
id: TEST-38
type: test
status: done
area: [agents, auth]
summary: >-
  TS-W — Per-agent model selection, live (model override actually applied)
source: .planning/TEST-REGISTER.md#ts-w-per-agent-model-selection-live-model-overri
covers: [TS-W-01, TS-W-02, TS-W-03]
---

### TS-W — Per-agent model selection, live (model override actually applied)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-W-01 | Override one agent live | compose a run, set agent A → a non-Haiku model, Run on real Bedrock | run completes; backend resolves agent A on the chosen model; `pipeline_complete.model_id` + Token cost label reflect it; other agents stay default Haiku | 🔴 (live) |
| TS-W-02 | Override invalid blocked | set a model id not in the catalog (tampered) | run refused at ingress (`invalid_model_override`), no agents run | 🟢 / 🔴 UI |
| TS-W-03 | No-override parity | run with all Default | payload omits `model_overrides`; behavior identical to pre-model-policy | 🟢 char-locked |

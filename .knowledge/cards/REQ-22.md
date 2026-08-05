---
id: REQ-22
type: req
status: done
area: [sse, workflow, agents, auth]
summary: >-
  Run-Screen Redesign (Phase 32)
source: .planning/REQUIREMENTS.md#run-screen-redesign-phase-32
---

### Run-Screen Redesign (Phase 32)

- [x] **RUNUI-01**: Token layer (black/beige/one-blue `#3C2CDA`, Manrope/Heebo) + shared primitives; run screens consume tokens, no new hardcoded palette
- [x] **RUNUI-02**: Run screen = chat lane (left) + Preview/Steps/Files/Audit (right); typed-renderer switcher as manual override over existing dispatch
- [x] **RUNUI-03**: Steps 3-level drill-down from real events (overview spine → agent detail + Context-received rail → task detail, dual task-loop/fanout source); gate/clarify inline
- [x] **RUNUI-04**: Audit tab reads new `gate_events`/`validation_results`/`exec_runs` endpoints; counters/filters/CSV-JSON export; status palette only for governance
- [x] **RUNUI-05**: E2E hardened — brittle color-class assertions fixed, `data-testid`s on chat surfaces, mockWs chat driver in use

---
id: REQ-17
type: req
status: done
area: [agents, auth]
summary: >-
  Budgets & Observability (cross-cutting, §23)
source: .planning/REQUIREMENTS.md#budgets-observability-cross-cutting-23
---

### Budgets & Observability (cross-cutting, §23)

- [x] **OBS-01**: `BudgetManager` enforces per-run AND per-workspace ceilings (tokens, €, subagents, depth, concurrency, wall-clock); reserve-before-spawn; graceful abort; snapshot persisted on the run (§23/§18)
- [x] **OBS-02**: Logging/tracing hooks bound to `*` emit OpenTelemetry-style spans/logs per lifecycle event → native observability; each firing lands in `hook_runs` (§23/§30)

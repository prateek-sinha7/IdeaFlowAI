---
id: TEST-47
type: test
status: done
area: [sse, workflow, agents, artifacts]
summary: >-
  G3 — Add data-testid to load-bearing nodes
source: .planning/TEST-REGISTER.md#g3-add-data-testid-to-load-bearing-nodes
---

### G3 — Add `data-testid` to load-bearing nodes

Text/role selectors work but are brittle. Add stable testids to: the Stop button, agent-card status badge (`RUNNING`/`DONE`/`ERROR`), the wave panel heading + each wave/worker leaf, the failure-affordance root, the generic deliverable iframe, history rows + status badges, the reconnecting/connection-lost banners, the per-agent model `<select>`, and the questionnaire submit. This de-brittles TS-I/K/Q/T/E/M.

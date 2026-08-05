---
id: REQ-25
type: req
status: done
area: [agents]
summary: >-
  Concierge & Compaction (Phase 33)
source: .planning/REQUIREMENTS.md#concierge-compaction-phase-33
---

### Concierge & Compaction (Phase 33)

- [ ] **CONC-01**: `chat:concierge` registered capability — one implementation, per-run instances, read + proposal-only tools, confirm chips, execution only through existing channels (INV-13 via `deep_agent_runner`)
- [ ] **CONC-02**: `compaction:chat_history` + `context_provider:conversation` bound composed history within budget (recent verbatim, older summarized)
- [ ] **CONC-03**: Post-run chat turns produce revision runs stitched into the family transcript

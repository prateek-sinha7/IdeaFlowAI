---
id: REQ-18
type: req
status: done
area: [sse, workflow]
summary: >-
  Anti-Duplication & Deletion Ledger (cross-cutting, INV-12/§31)
source: .planning/REQUIREMENTS.md#anti-duplication-deletion-ledger-cross-cutting-i
covers: [UI-CONVERGENCE-PLAN]
---

### Anti-Duplication & Deletion Ledger (cross-cutting, INV-12/§31)

- [x] **DEL-01**: Every legacy element follows wrap → rewire call-sites → delete, completed within the phase that supersedes it; one implementation per behavior (INV-12)
- [x] **DEL-02**: Each phase ships a banned-pattern test (grep → 0 for deleted symbols/branches), a dead-code scan (ruff/vulture), and the import-linter rule as exit gates; Definition of Done = behavior moved + call-sites rewired + legacy deleted + gates green + snapshots green (§31) — _ledger ratchet (01-03) + banned-pattern test + vulture dead-code scan + import-linter contract (01-04) all shipped and green_
- [x] **DEL-03**: Banned-pattern tests are ratchets — a deleted symbol's reintroduction fails CI (§31)
- [x] **DEL-04**: The `specs/003-…/migration-ledger.md` mirrors the §31 ledger operationally (L1–L16, F1–F5, D1) with status + deleting commit SHA, asserted by CI (§31)

## Milestone v2.0 Requirements — Universal Run Chat & VelocityAI UI Convergence

Registered 2026-07-07 via `/gsd-import`. Plan of record: `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` (locked decisions D-01..D-12, open decision records ND-1..ND-9). Phases 28–38 (23–27 reserved for the post-milestone standalone efforts in IMPLEMENTATION-REGISTER). All requirements inherit the standing invariants: SC-001/INV-1 (no kernel workflow-name branches), INV-3 (5 goldens byte/event-identical), INV-5, INV-12, INV-13, Q3 (additive migrations; owner_id+workspace_id).

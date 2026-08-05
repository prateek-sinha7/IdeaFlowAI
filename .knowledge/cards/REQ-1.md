---
id: REQ-1
type: req
status: done
area: [sse, agents, auth, artifacts]
summary: >-
  Safety Net & Migration Discipline (Phase 0A)
source: .planning/REQUIREMENTS.md#safety-net-migration-discipline-phase-0a
---

### Safety Net & Migration Discipline (Phase 0A)

- [x] **SAFE-01**: Characterization tests record deliverable byte-snapshots (deterministic output) for `prototype`, `od_prototype`, `prototype_revision`, `ppt`/`od_ppt`, and one code-gen pipeline, driven by a scripted model (`tests/agents/_scripted_model.py`) (§24) ✅ 01-01
- [x] **SAFE-02**: Semantic event-stream snapshots assert event types, order, required fields, and final result, with volatile fields normalized out (timestamps, chunk boundaries, generated IDs, token/usage counts, durations) (INV-3 / §24)
- [x] **SAFE-03**: Monotonic per-run event `seq` is asserted contiguous (not by absolute value) in snapshots (§21/§24)
- [x] **SAFE-04**: Migration-ledger CI guard `tests/test_migration_ledger.py` asserts each `☑` ledger item's banned grep-pattern returns 0 (§31)
- [x] **SAFE-05**: Import-linter contract enforces the kernel imports only capability ports — never legacy `engine`/`factory` internals (§31/§32)
- [x] **SAFE-06**: Banned-pattern CI gate blocks hand-rolled deep agents — `class DeepAgent` / `def deep_agent` / a new `deepagents`/`langchain_deepagents` module / bespoke `for _ in range(max_iterations)` loops outside the adapter (INV-13 / R15)
- [x] **SAFE-07**: Ledger guard + import-linter + banned-pattern gates run in CI and start green/empty, tightening as items delete (§31)

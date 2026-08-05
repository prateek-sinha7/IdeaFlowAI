---
id: REQ-2
type: req
status: done
area: [resume, agents, artifacts, runtime]
summary: >-
  Per-Run Execution Context & Ownership (Phase 0B)
source: .planning/REQUIREMENTS.md#per-run-execution-context-ownership-phase-0b
---

### Per-Run Execution Context & Ownership (Phase 0B)

- [x] **CTX-01**: All `self._*` per-run state (`_od_context`, `_completed_tasks`, `_current_task_block`, `_revision_*`, `_gate_agent_ids`, `_user_id`, `_checkpointer`) moves to a per-run `ExecutionContext` (L14 / INV-2)
- [x] **CTX-02**: The kernel singleton holds no per-run attributes and is immutable after construction (NFR-001 / INV-2)
- [x] **CTX-03**: `parent_run` seeding performs an explicit ownership check that rejects cross-owner access (L16 / INV-8)
- [~] **CTX-04**: ~~Dead `_handle_revision` (`engine.py:2138-2251`) is deleted (D1)~~ — **VOIDED/DEFERRED (2026-06-07): `_handle_revision` is LIVE — the frontend `run_revision` PPT-revision handler (`app/api/websocket.py:625`), not dead. Deletion would break PPT revision (CTX-05). Deferred pending a product decision on retiring `run_revision`. See Phase 2 `02-02-SUMMARY.md`.**
- [x] **CTX-05**: No behavior change — deliverable snapshots stay byte-identical and event snapshots stay at semantic parity (INV-3)

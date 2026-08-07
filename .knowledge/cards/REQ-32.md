---
id: REQ-32
type: req
status: done
area: [sse, resume, agents, artifacts]
summary: >-
  Task Identity & Mutable Task List (Phase 48 [R3])
source: .planning/REQUIREMENTS.md#task-identity-mutable-task-list-phase-48-r3
---

### Task Identity & Mutable Task List (Phase 48 [R3])

- [x] **RESUME-14**: Content-addressed task identity — `task_key = sha256(upstream_context_hash · normalized_task_content · occurrence_ordinal)`: position-independent (reorder/insert-safe), duplicate-text-safe (ordinal), and upstream-aware (a spec edit rotates the keys so tasks built against a stale spec re-run); hash discipline inherited from `input_hash` (sorted, no timestamp/uuid — cross-restart stable).
- [x] **RESUME-15**: The task list is user-editable as a VERSIONED `task_list` artifact (Q3): add/edit/delete mints a new version via the extended gate-Edit mechanism (KAN-98 path; `edited_content` rides `POST /{id}/gate` only — WR-03); old versions kept with `derived_from` lineage, `max(version)` wins; NO new tasks table (respects the "no new step-status table" lock).
- [x] **RESUME-16**: AUTOMATIC reconciliation (Q2) on resume or re-run-after-edit: completed+present → skip + re-materialize + inject as prior context; new/edited/rotated → run; deleted-but-completed → excluded from the assembled deliverable at read time (rows NEVER deleted — `artifact_refs` immutable); spec edits auto-invalidate affected tasks with no confirm prompt.

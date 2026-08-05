---
id: REQ-31
type: req
status: done
area: [resume, workflow, agents]
summary: >-
  Uploads Durability (Phase 47 [R2])
source: .planning/REQUIREMENTS.md#uploads-durability-phase-47-r2
---

### Uploads Durability (Phase 47 [R2])

- [x] **RESUME-12**: Uploaded documents' extracted text + manifest are persisted durably at ingest (additive, owner_id+workspace_id-scoped; existing per-file/count/aggregate caps unchanged) — closing the `.uploads/` disk-only hole (Q6).
- [x] **RESUME-13**: The `uploaded_files` context provider falls back to the durable mirror when the sandbox `.uploads/` copy is missing, so a resumed run on a fresh sandbox keeps FULL document context in every subsequent `agent_input`. Images stay payload-transient (ND-10 locked — explicitly untouched).

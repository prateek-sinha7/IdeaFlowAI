---
id: REQ-33
type: req
status: done
area: [sse, resume, workflow, agents, artifacts]
summary: >-
  Gate Survival (Phase 49 [R4])
source: .planning/REQUIREMENTS.md#gate-survival-phase-49-r4
---

### Gate Survival (Phase 49 [R4])

- [x] **RESUME-17**: Clarify AND review gates survive a backend restart: restart branch (a) flips fail→re-arm for compiled-manifest runs with durable state (WR-05 stateless/legacy path byte-untouched), rebuilt on the EXISTING seams (`derive_open_gate`/KAN-94 durable pendency + the D-14g `_dangling_review_gate` SSE re-emit — no parallel pending-arm store; `_gate_is_pending` gains a public accessor, closing the IN-02 debt); the review gate RE-ENTERS `_run_agent`'s loop AT its gate phase with the output reconstructed from `artifact_refs`, so ALL five gate actions (approve/reject/edit/redo/update_specs) work identically post-restart; the pre-existing red `test_restart_resume::test_waiting_for_user_run_is_rearmed_not_driven` flips GREEN (the KAN-88 restoration anchor).

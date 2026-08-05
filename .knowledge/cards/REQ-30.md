---
id: REQ-30
type: req
status: done
area: [resume, workflow, agents, auth, artifacts]
summary: >-
  Per-Task Substrate, Cursor & Live Layer (Phase 46 [R1])
source: .planning/REQUIREMENTS.md#per-task-substrate-cursor-live-layer-phase-46-r1
---

### Per-Task Substrate, Cursor & Live Layer (Phase 46 [R1])

- [x] **RESUME-06**: `subagent_runs` carries per-child task identity — additive nullable `task_id` + `worker_index` columns (the pre-authorized CR-03-followup; free-String, named FK, reversible single-head after 0025), written at spawn (before the crash window — the 0023 `selections_json` precedent).
- [x] **RESUME-07**: GENERIC per-task capture (Q7): every file a task wrote is durably captured per task — not just the declared deliverable file — superseding `persist_task_html`'s single-file scope so any future multi-file task workflow resumes from day one.
- [x] **RESUME-08**: Durable→disk re-materialization: resume walks the latest durable `artifact_refs` (by `location`, `max(version)`, filtered to completed task keys) and rebuilds the fresh `RunSandbox` — including MERGE RE-ENTRY for an in-flight wave (fragments re-materialized + the per-wave merge re-run before remaining workers dispatch). Worktree/sandbox state reconstructs from `artifact_refs`, never from git.
- [x] **RESUME-09**: Per-worker wave skip + per-task sequential skip: completed workers/tasks are never re-invoked on resume (identity-based kernel cursor — NOT the deleted-for-cause prefix-by-count skip); agents receive the completed work as injected context but never decide the skip set.
- [x] **RESUME-10**: A resumed run is a first-class LIVE run: both resume paths (auto `restore_non_terminal_runs` branch (b) AND the Phase-50 user endpoint) thread `register_live_ectx` (+ unregister in `finally`) and `milestone_sink` — mid-run steering, per-turn images, Concierge context, and narrator milestone cards all work on resumed runs; milestone-card `seq` drawn from the engine counter (DEF-43-03-1, 0024 constraint).
- [x] **RESUME-11**: Steering notes durably logged as `chat_message` rows but not yet drained at crash time are re-queued onto `ectx.steering_notes` at resume (no silent loss of accepted guidance).

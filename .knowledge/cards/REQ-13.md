---
id: REQ-13
type: req
status: done
area: [sse, resume, workflow, artifacts]
summary: >-
  Cancellation, Retry & Resume (cross-cutting; basic in Phase 0, hardened 5–6)
source: .planning/REQUIREMENTS.md#cancellation-retry-resume-cross-cutting-basic-in
---

### Cancellation, Retry & Resume (cross-cutting; basic in Phase 0, hardened 5–6)

- [x] **RESUME-01**: Cooperative `cancel_event` checked per-chunk and at step/gate/fanout/wave boundaries; on cancel → mark `cancelled`, preserve partial artifacts, `teardown()` isolated workspaces, emit `pipeline_cancelled` (§21)
- [x] **RESUME-02**: Idempotent per-step retry `retry: {max, on}` for transient errors, keyed by `(run_id, step_id, input content_hash)`; reuses the existing artifact on hash match — distinct from the validator fix-loop (§21)
- [x] **RESUME-03**: Reconnect = durable replay from `run_events` via `after=<last_seq>`, idempotent by `event_id` (§21/§22)
- [x] **RESUME-04**: Server restart = `restore_non_terminal_runs` extended to step granularity; `waiting_for_user` gates resume on user action; in-flight steps resume from checkpoint or re-run idempotently (§21)

---
id: TEST-34
type: test
status: done
area: [sse, workflow, agents]
summary: >-
  TS-S — Reconnect / replay (resilience of a live run)
source: .planning/TEST-REGISTER.md#ts-s-reconnect-replay-resilience-of-a-live-run
covers: [TS-S-01, TS-S-02, TS-S-03, TS-S-04, TS-S-05, TS-S-06, TS-S-07]
---

### TS-S — Reconnect / replay (resilience of a live run)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-S-01 | **Reconnect ack (ISS-008/009)** | reload mid-run | on WS `connected`, FE sends `{type:"reconnect_pipeline", pipeline_run_id, after_seq:<lastSeq>}`; `pipeline_reconnected` ack carries `live`, `replayed_through_seq`, `status` all present (`live` always explicit) | ✅ (V5 live) |
| TS-S-02 | live:true keeps streaming | reconnect to a still-running run | `live!==false` → keep `isRunning`, tail streams via subsequent `agent_*`/`pipeline_complete` | 🟡 |
| TS-S-03 | live:false + terminal resolves | reconnect after backend restart/finish | `live:false` + `status∈{completed,failed,cancelled}` → resolve out of running (stops the "running forever" hang); completed sweeps agents `done` | 🟡 |
| TS-S-04 | Panels rebuild | reload mid-run | replayed durable tail re-drives `pipeline_start`→`agent_*` → panels rebuild from scratch; no home-flash | ✅ |
| TS-S-05 | Replay dedup | reload | replayed frames idempotent by `event_id` — no duplicated streamed text / wave leaves; `seq` cursor only advances after dedup | 🟢 (wsReplayState.test) / 🔴 UI |
| TS-S-06 | Revision replay section (ISS-008) | reconnect mid-revision | replay frames carry the revision `section` (e.g. `od_ppt_output`), matching live-attach (WR-03) | 🟡 (29 live-attach frames ✅) |
| TS-S-07 | Cross-owner demotion | reconnect another user's run id | → ∅ + `live:false` + null status (no leak) | 🟢 (live P12) |

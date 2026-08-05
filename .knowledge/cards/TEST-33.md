---
id: TEST-33
type: test
status: done
area: [sse, agents]
summary: >-
  TS-R — Cancel (Stop)
source: .planning/TEST-REGISTER.md#ts-r-cancel-stop
covers: [TS-R-01, TS-R-02, TS-R-03, TS-R-04]
---

### TS-R — Cancel (Stop)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-R-01 | **Stop delivers cancel (ISS-007/002)** | click `Stop` mid-run | WS sends `{type:"cancel_pipeline"}`; engine cooperative-cancel (not destructive); `pipeline_cancelled` is **delivered to the FE wire** | ✅ (V4 live, count 1) |
| TS-R-02 | In-flight cards clear | after cancel | running/thinking agents → `idle` (badges cleared, **no stuck RUNNING**); done/error untouched; header `Pipeline stopped` | ✅ (`[]` badges) |
| TS-R-03 | Live cancel ≠ failure chrome | after a live Stop | preview shows neutral/last-content, **NOT** the degraded affordance (live cancel sets no `failed`/`degraded` flag — only history-reopen of a `cancelled` run shows cancelled copy) | 🟡 |
| TS-R-04 | Cancel during revision | Stop a revision run | bg task cancelled, row `cancelled`, no exact-kind ref written (no poisoned parent) | 🟡 |

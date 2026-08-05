---
id: TEST-23
type: test
status: done
area: [sse, workflow, agents, auth]
summary: >-
  TS-H — Trigger contract & execution-view transition (what happens when a pipeline
  fires)
source: .planning/TEST-REGISTER.md#ts-h-trigger-contract-execution-view-transition
covers: [TS-H-01, TS-H-02, TS-H-03, TS-H-04, TS-H-05]
---

### TS-H — Trigger contract & execution-view transition (what happens when a pipeline fires)

| ID | Title | Steps | Expected (exact wire + visual) | Status |
|---|---|---|---|---|
| TS-H-01 | run_pipeline payload | Run a `user_stories` brief | WS frame `{type:"run_pipeline", pipeline_type:"user_stories", message:"<trimmed>", agent_ids:[…]}`; optional `attached_skills/attached_hooks/gate_agent_ids/model_overrides` present **only** when set; **no override → byte-identical legacy payload** | 🔴 |
| TS-H-02 | Optimistic transition | click Run | `execution` view shows **immediately** (before any server event); `AgentProgressPanel` left (~340–360px), preview right; a `Running` notification appears | 🔴 |
| TS-H-03 | Queue-on-connect | Run while WS not yet `connected` | the start is stashed and fires on the next `connected` transition (no lost run on reconnect/hot-reload) | 🔴 |
| TS-H-04 | pipeline_start seeds cards | observe first server event | `pipeline_start` → agent cards seeded `idle` from the server agent list; `currentAgentIndex=0`; sessionStorage `active_pipeline_run_id` + `active_pipeline_type` set | 🔴 |
| TS-H-05 | Wizard path (prototype/ppt) | run via `/workflow/prototype/templates` | brief+template+design-system staged in sessionStorage; on WS connect a `run_pipeline` with `pipeline_type:"od_prototype"`, `template_id`, `design_system_id` fires | 🔴 |

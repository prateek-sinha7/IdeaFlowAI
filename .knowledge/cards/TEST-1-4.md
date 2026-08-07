---
id: TEST-1-4
type: test
status: done
area: [workflow, agents]
summary: >-
  1.4 Workflow & capability fixtures
source: .planning/TEST-REGISTER.md#1-4-workflow-capability-fixtures
---

### 1.4 Workflow & capability fixtures

- 18 committed workflow dirs under `backend/agents/workflows/<id>/workflow.yaml`; AGENT.md bodies live separately under `backend/agents/prompts/<agent-id>/AGENT.md`. `od_prototype`/`od_ppt` are **lookup aliases** (no own dir).
- **SC-001 / custom-pipeline fixtures:** committed CI fixture `backend/tests/agents/fixtures/sc001_task_loop/` (the real zero-engine-edit proof). The UI campaign's custom workflow `ui_custom_proto` (5 agents: factfind → 3-worker `fanout_batch` w/ human-gate-on-conflict → human-gated plan → `task_loop` build w/ `html_static`+`html_render` validators → validate) is preserved at `.planning/live-verification/ui_custom_proto-fixture/` and must be admitted via a custom launcher (it is intentionally **not** in the product tree).

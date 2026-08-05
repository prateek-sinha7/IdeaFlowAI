---
id: TEST-35
type: test
status: done
area: [workflow, agents, artifacts]
summary: >-
  TS-T — Workflow history (WorkflowHistory)
source: .planning/TEST-REGISTER.md#ts-t-workflow-history-workflowhistory
covers: [TS-T-01, TS-T-02, TS-T-03, TS-T-04, TS-T-05, TS-Q-02, TS-T-06, TS-T-07]
---

### TS-T — Workflow history (WorkflowHistory)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-T-01 | List & badges | open History | rows: icon + title + `{label} · {date} · {duration}`; status badge `Done`(emerald)/`Cancelled`(amber)/`Failed`(gray)/`Running`(gray, also degraded/revising) | 🔴 |
| TS-T-02 | Filter & search | tabs + search | tabs `all/user_stories/ppt/prototype/app_builder/custom`; `Search workflows...` filters by title | 🔴 |
| TS-T-03 | Reopen | click a row | detail view (agents sidebar + Preview/Files/Thinking); content from `run.output` or `getWorkflow(id)` | 🔴 |
| TS-T-04 | **Generic reopen (ISS-021 parity)** | reopen a custom HTML run | same heuristic as live: `text/html` → `iframe[title="Deliverable Preview"]` `sandbox="allow-scripts"` (no same-origin); `zip`→IDE; else MarkdownPreview | 🟢 (genericReopen.test) / 🔴 UI |
| TS-T-05 | Reopen failed/cancelled | reopen a failed/cancelled run | degraded/cancelled affordance via `reopenedRunStatus` (TS-Q-02/04) | 🔴 |
| TS-T-06 | Delete | kebab → Delete → confirm | modal `Delete workflow` / `The workflow run and all its output will be permanently deleted.`; `deleteWorkflow` removes the row | 🔴 |
| TS-T-07 | Chaining | completed run footer | `Suggested next steps` → `availableChainTargets(type)` buttons start the chained pipeline | 🔴 ⚪(chaining.test ×6 KNOWN-FAIL) |

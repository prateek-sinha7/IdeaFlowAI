---
id: TEST-22
type: test
status: done
area: [sse, agents]
summary: >-
  TS-G — Review gates pre-run (ReviewGatesSection, on IdeaInputPage)
source: .planning/TEST-REGISTER.md#ts-g-review-gates-pre-run-reviewgatessection-on
covers: [TS-G-01, TS-G-02, TS-G-03, TS-G-04]
---

### TS-G — Review gates pre-run (ReviewGatesSection, on IdeaInputPage)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-G-01 | Collapsed summary | observe `Review gates` header | `no gates` when none checked; else `{n} agent[s] pause for review`; chevron toggles | 🔴 |
| TS-G-02 | Default gates | open for prototype agents | `prototype-specify` + `prototype-plan` pre-checked (`gate==="Human_Gate"`), each with a `default` pill | 🔴 |
| TS-G-03 | Toggle → payload | check/uncheck an agent, Run | `gate_agent_ids` sent **only when touched**; the ordered checked ids match | 🔴 |
| TS-G-04 | Hidden when no agents | remove all agents | section renders nothing (`agents.length===0`) | 🔴 |

---
id: TEST-19
type: test
status: done
area: [sse, workflow, agents]
summary: >-
  TS-D — Agent composer (AgentsPopup)
source: .planning/TEST-REGISTER.md#ts-d-agent-composer-agentspopup
covers: [TS-D-01, TS-D-02, TS-D-03, TS-D-04, TS-D-05, TS-D-06, TS-D-07, TS-D-08]
---

### TS-D — Agent composer (AgentsPopup)

Modal title `Workflow configuration`, eyebrow `Advanced`. Tabs `Agents ({n})` / `Skills & Hooks`.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-D-01 | Open/close | click `Advanced`; click backdrop / `X` / `Cancel` / `Save changes` | modal opens; **all four close affordances close it identically** (state is already live; `Save changes` ≡ `Cancel`) | 🔴 |
| TS-D-02 | Roles & locks | inspect agent cards | locked agents show `Core` pill + `Lock` icon (not draggable/removable); required show `Required` (draggable, not removable); optional show `X` `title="Remove agent"` | 🔴 |
| TS-D-03 | Remove optional agent | click a card's `X` | agent removed; `Agents ({n})` count decrements; Add cell shows `+ Add agent ({slotsLeft} left)` | 🔴 |
| TS-D-04 | Drag-reorder | drag an optional card | order changes; dragging card `opacity:0.4`, drop target `scale 1.02`+navy border; locked cards refuse drag | 🔴 |
| TS-D-05 | Add-agent cap | add optional agents to the cap | cap = 8 for `custom`, 5 otherwise; at cap the Add cell reads `Limit reached` | 🔴 |
| TS-D-06 | Agent Library | click `Browse agent library →` | modal `Add agent`; categories `All/User Stories/Presentation/Prototype/App Builder/Mulesoft → Spring Boot/.NET → Azure/Custom`; search `Search agents...`; `+ Add` adds + **closes the library** | 🔴 |
| TS-D-07 | Custom hides anchors | in `custom`, browse library | the `HIDDEN_FROM_CUSTOM` set (ppt-assembler, backlog-compiler, prototype-finalizer, app-sdlc-governance, …) is filtered out | 🔴 |
| TS-D-08 | Capabilities modal | click a card's `title="View capabilities"` | modal shows `What this agent does`, `Pipeline · Step {n}`, `Suggested Skills`, `Suggested Hooks`, and (if `has_skill`) a `Custom skill` inline editor (`Attach skill` disabled until name+content) | 🔴 |

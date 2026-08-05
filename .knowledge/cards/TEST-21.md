---
id: TEST-21
type: test
status: done
area: [workflow, agents, auth]
summary: >-
  TS-F — Skills & Hooks (AgentsPopup → Skills & Hooks tab)
source: .planning/TEST-REGISTER.md#ts-f-skills-hooks-agentspopup-skills-hooks-tab
covers: [TS-F-01, TS-F-02, TS-F-03, TS-F-04, TS-F-05, TS-F-06]
---

### TS-F — Skills & Hooks (AgentsPopup → Skills & Hooks tab)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-F-01 | Empty states | open the tab | `No skills attached · click "Add skill" to browse`; `No hooks attached · click "Add hook" to browse` | 🔴 |
| TS-F-02 | Attach skill | `Add skill` → search/filter → `Add` | row shows `CheckCircle2 {name}`; button `Add`→`Added` (disabled, Check); count pill increments | 🔴 |
| TS-F-03 | Skill category filter | click category pills | pills `All/Planning/Testing/Workflow/Security/Debugging/Collaboration/Meta` filter the list; `No skills found` when empty | 🔴 |
| TS-F-04 | Attach hook | `Add hook`, attach e.g. `Quality Gate` | 8 hooks available with event pills (`PostToolUse` etc.); event filter pills `All Events/Pre Tool Use/Post Tool Use/On Stop/Session Start/Session End` | 🔴 |
| TS-F-05 | Persisted into payload | attach 1 skill + 1 hook, Run | `run_pipeline` carries `attached_skills:[{id,name,content,source,compatible_agents:[]}]` + `attached_hooks:[{id,name,event,trigger,description}]` (TS-H) | 🔴 |
| TS-F-06 | Survives reopen | attach, close popup, reopen | attachments persist (global `SkillsHooksContext`) | 🔴 |

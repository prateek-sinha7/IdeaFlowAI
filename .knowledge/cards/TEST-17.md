---
id: TEST-17
type: test
status: done
area: [sse, workflow, agents]
summary: >-
  TS-B — Workflow selection (CreationHub)
source: .planning/TEST-REGISTER.md#ts-b-workflow-selection-creationhub
covers: [TS-B-01, TS-B-02, TS-B-03, TS-B-04, TS-B-05, TS-B-06, TS-B-07]
---

### TS-B — Workflow selection (CreationHub)

Vertical **list** of 6 `<button>` rows (not tiles). Header H1 `What would you like to build today?`. Assert each row's exact H2 + routing.

| ID | Row (H2 label, exact) | Click → | Expected | Status |
|---|---|---|---|---|
| TS-B-01 | `Generate product requirements` (`user_stories`) | `input` view | IdeaInputPage with eyebrow `Generate product requirements`, H1 `Provide the brief` | 🔴 |
| TS-B-02 | `Pitch an idea` (`ppt`) | **`/workflow/ppt/templates`** | PPT template wizard loads (not IdeaInputPage) | 🔴 |
| TS-B-03 | `Build an interactive prototype` (`prototype`) | **`/workflow/prototype/templates`** | Prototype template wizard loads | 🔴 |
| TS-B-04 | `Build an end-to-end application` (`app_builder`) | `input` view | H1 `Describe the application` | 🔴 (pro+) |
| TS-B-05 | `Platform workflows` (`migration`, `NEW`) | `input` view | H1 `Modernise a legacy estate`; **two migration tiles** shown; Run disabled until a path is picked | 🔴 (ent) |
| TS-B-06 | `Compose a custom workflow` (`custom`) | `input` view | H1 `Describe the task`; AgentsPopup pulls the 8 `custom` agents (cap 8) | 🔴 (ent) |
| TS-B-07 | Row hover affordance | hover an allowed row | label → navy `#1B2A4A`, arrow translates right; staggered fade-in on mount | 🔴 |

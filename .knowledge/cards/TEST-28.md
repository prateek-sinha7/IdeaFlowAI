---
id: TEST-28
type: test
status: done
summary: >-
  TS-M — Questionnaire / clarify gate (QuestionnairePanel)
source: .planning/TEST-REGISTER.md#ts-m-questionnaire-clarify-gate-questionnairepan
covers: [TS-M-01, TS-M-02, TS-M-03, TS-M-04, TS-M-05, TS-M-06]
---

### TS-M — Questionnaire / clarify gate (QuestionnairePanel)

Accordion of MCQ cards (not native radios). Header `Quick Setup`. **No required-answer validation — submit never disabled; defaults filled server-side.**

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-M-01 | Loading | clarify analyzing | `Analyzing your brief…` + `Preparing smart questions to get the best output` | 🔴 |
| TS-M-02 | Render | `questionnaire_ready` arrives | `Quick Setup` + `{label} · {n} questions to personalise your output`; first question auto-expanded; counter `{answered} of {n} answered` | ✅ (S01) |
| TS-M-03 | Select option | click an MCQ option `<button>` | selected fills navy `bg-[#1B2A4A] text-white`; single-select (replaces); **auto-advances to next question after 300ms** | 🔴 |
| TS-M-04 | Hybrid free-text | a `hybrid` question | `Describe your own topic` input (placeholder `e.g. Q3 sales results, climate change impact, AI in healthcare…`); typing clears the MCQ selection | 🔴 |
| TS-M-05 | Submit labels | varying answered count | all answered → `Run {label} Pipeline`; some → `Continue with {a}/{n} answered`; none → `Run with defaults`; secondary `Skip all & run directly` | ✅ |
| TS-M-06 | Submit proceeds | click submit (even 0 answered) | run starts; `questionnaire_complete` clears the panel; unanswered questions omitted from payload | 🔴 |

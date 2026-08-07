---
id: TEST-18
type: test
status: done
area: [workflow, agents]
summary: >-
  TS-C — Idea input & pipeline trigger (IdeaInputPage)
source: .planning/TEST-REGISTER.md#ts-c-idea-input-pipeline-trigger-ideainputpage
covers: [TS-C-01, TS-C-02, TS-C-03, TS-C-04, TS-C-05, TS-C-06, TS-C-07, TS-C-08, TS-C-09, TS-C-10]
---

### TS-C — Idea input & pipeline trigger (IdeaInputPage)

| ID | Title | Steps | Expected (exact) | Status |
|---|---|---|---|---|
| TS-C-01 | Placeholder per type | open each entry workflow | textarea placeholder matches type, e.g. user_stories `e.g. Generate epics and stories for a refunds workflow with multi-currency support.`; app_builder `e.g. A SaaS platform for managing freelance invoices with Stripe integration.`; custom `e.g. Research the competitive landscape for AI coding assistants and generate a SWOT analysis.` | 🔴 |
| TS-C-02 | Run button disabled states | empty idea / no agents / migration-no-path | label = `Run workflow` only when valid; else `Add agents first` (no agents) or `Pick a migration path` (migration); `disabled` + `opacity-30` when `!idea.trim()` or `agents==0` | 🔴 |
| TS-C-03 | Run enables on input | type a brief with ≥1 agent | Run button enabled, label `Run workflow`, navy `bg-gray-900` | 🔴 |
| TS-C-04 | Keyboard submit | focus textarea, press `Cmd/Ctrl+Enter` | triggers run (same as clicking Run); plain Enter inserts newline | 🔴 |
| TS-C-05 | Auto-focus | open `input` | textarea focused ~200ms after mount | 🔴 |
| TS-C-06 | Attach file | click `+ Attach file`, pick `spec.pdf` | a chip `spec.pdf` appears; textarea gains `[Attached: spec.pdf]`; **note: only the name is injected, bytes not uploaded** | 🔴 |
| TS-C-07 | Voice (Chromium) | click `Voice` | toggles to `Stop`, red `animate-pulse`, placeholder → `Listening... speak your idea`; (button absent in Firefox — assert absence) | 🔴 |
| TS-C-08 | Migration path select | pick tile `Mulesoft → Spring Boot microservices on AWS` | tile fills navy `bg-[#1B2A4A]` white; all heading/placeholder copy swaps to mulesoft; Run unlocks | 🔴 |
| TS-C-09 | Advanced summary line | observe the `Advanced` button | shows `{n} agents` + (if est) ` · ~{X}s`/`~{Y}m` + (if attached) ` · {k} skill/hook`; clicking opens AgentsPopup | 🔴 |
| TS-C-10 | **Trigger → execution transition** | click `Run workflow` | view **immediately** swaps to `execution` (2-col); a running notification toast (label = first 60 chars); the `run_pipeline` WS frame is sent (see TS-H for payload) | 🔴 |

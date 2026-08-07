---
id: TEST-49
type: test
status: done
area: [sse, workflow, agents, auth]
summary: >-
  G5 — Offline backend test ergonomics
source: .planning/TEST-REGISTER.md#g5-offline-backend-test-ergonomics
covers: [UI-CAMPAIGN-2026-06-13]
---

### G5 — Offline backend test ergonomics

Full `pytest` hangs offline (Postgres/Bedrock/Chromium-gated) and the `requires_api_key` marker isn't applied uniformly to `*_live.py`/Chromium suites. Add an `offline` marker (or `-m "not requires_api_key and not live"`) and a `make test-offline` target wrapping the §1.6 list so QA has one reliable offline command.

---

## Appendix A — Source maps consumed to build this register

- Architecture spine: `.planning/IMPLEMENTATION-REGISTER.md` + `_register-parts/00..19`.
- Frontend behavior (exact strings/states/selectors/timing): the 4 component maps — compose/trigger (`IdeaInputPage`/`AgentsPopup`/`AgentModelPicker`/`CreationHub`), live panels (`AgentProgressPanel`/`WaveTreePanel`/`AgentThinkingTab`/`TokenUsageSummary`), preview/terminal (`PreviewPanel`/`MarkdownPreview`/`QuestionnairePanel`/`ReviewGatePanel`/per-workflow previews), state/WS/history (`useWorkflow`/`useWebSocket`/`wsReplayState`/`WorkflowHistory`/`DashboardLayout`).
- Live evidence: `.planning/live-verification/CAMPAIGN-2026-06-13-phases16-19.md` (V1–V8), `UI-CAMPAIGN-2026-06-13.md` (S01–S12), `REPORT-2026-06-12.md` (re-pass).
- Issue WHY: `.planning/ISSUES-REGISTER.md` (deep root-cause investigation, ISS-001..026).

## Appendix B — Exact UI strings quick-reference (assert verbatim)

`What would you like to build today?` · `Run workflow` / `Add agents first` / `Pick a migration path` · `Per-Agent Model` / `Default` · `Workflow configuration` · `Review gates` / `no gates` / `{n} agents pause for review` · `Wave / Subagent Tree` / `No waves running.` · `RUNNING`/`DONE`/`ERROR` · `Pipeline stopped` / `{n} / {m} agents` / `Done in {x}s` · `Reasoning (live)` + `▌` · `✓ PROCEED` / `⚡ CLARIFY` · `Quick Setup` / `Run with defaults` / `Skip all & run directly` · `Specification Review` / `Task Plan Review` / `Approve & continue` / `Reject & cancel pipeline` · `Output will appear here` · `This run did not complete successfully` / `No deliverable was produced. The run ended in a failed or degraded state.` / `Failed agents` / `View details / retry` · `This run was cancelled` · `Deliverable ready` / `Deliverable Preview` (iframe `sandbox="allow-scripts"`) · `Slide Deck Preview` / `Prototype Preview` · History badges `Done`/`Cancelled`/`Failed`/`Running` · `The model rejected this request.`

---
*End of TEST-REGISTER. This document is the QA reference for v1.0 production sign-off. Update the Status column as Playwright cases are authored and live runs are recorded.*

---
id: TEST-25
type: test
status: done
area: [agents]
summary: >-
  TS-J — Live streaming, planner & execution gate (AgentThinkingTab / PreviewPanel
  "Thinking" tab)
source: .planning/TEST-REGISTER.md#ts-j-live-streaming-planner-execution-gate-agent
covers: [TS-J-01, TS-J-02, TS-J-03, TS-J-04, TS-J-05, TS-J-06, TS-J-07]
---

### TS-J — Live streaming, planner & execution gate (AgentThinkingTab / PreviewPanel "Thinking" tab)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-J-01 | Empty trace | before a run | `Pipeline Trace` + `Start a pipeline to see real-time agent reasoning, tool calls, and context flow.` | 🔴 |
| TS-J-02 | **Reasoning (live) stream** | agent thinking | header `Reasoning (live)` + last 300 chars of `thinkingText` (mono) + blinking cursor `▌` (`animate-pulse`). **NOTE:** `agent_chunk` output is NOT shown live — only `agent_thinking` drives this | ✅ |
| TS-J-03 | Per-card LIVE/DONE/ERROR | through a run | running → `LIVE` (Zap, navy on `#E8EDF5`); done → `DONE`; error → `ERROR` (red); auto-expand + `scrollIntoView` follows the running card | 🔴 |
| TS-J-04 | Pipeline status banner | running/complete/errors | `Pipeline Running` (navy pulsing dot) / `Pipeline Complete` / `Completed with errors` (red) | 🔴 |
| TS-J-05 | Execution gate badge | after planner | `✓ PROCEED` (navy) or `⚡ CLARIFY` (amber); Deep Planner card title `Deep Planner`, subtitle `Intent: {…}` or `Analyzing brief & planning execution…` | 🔴 |
| TS-J-06 | Spec-Kit live view (prototype) | run a prototype | replaces the trace body: `Spec Kit Pipeline`, 4 PhaseCards `Spec Writer — Specification`/`Task Planner — Build Decomposition`/`Build Agent — Incremental Construction`/`Validation Agent — P0/P1 Checks`; running phase shows `LIVE` + status copy; build shows per-task rows; complete → `Prototype complete — {N}s` | ✅ (S02) |
| TS-J-07 | Planning overlay | planner_start | right panel `Planner is thinking…`, 4 steps rotate every 1800ms | 🔴 |

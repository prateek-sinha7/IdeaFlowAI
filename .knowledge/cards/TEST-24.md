---
id: TEST-24
type: test
status: done
area: [agents, auth]
summary: >-
  TS-I — Live agent panels (AgentProgressPanel) — per-agent visual states & timing
source: .planning/TEST-REGISTER.md#ts-i-live-agent-panels-agentprogresspanel-per-ag
covers: [TS-I-01, TS-I-02, TS-I-03, TS-I-04, TS-I-05, TS-I-06, TS-I-07, TS-I-08, TS-I-09, TS-I-10]
---

### TS-I — Live agent panels (AgentProgressPanel) — **per-agent visual states & timing**

Primary live surface (left column, light theme). Status model `idle→thinking/running→done/error`.

| ID | Title | Steps | Expected (exact badge + style + timing) | Status |
|---|---|---|---|---|
| TS-I-01 | RUNNING badge | agent starts | badge `RUNNING` white-on-navy `bg-[#1B2A4A]`; card navy border; **two animations**: pinging white dot (`animate-ping`) + `Loader2 animate-spin`; status line = `agent.thinking` or `In progress...` | ✅ (campaign) |
| TS-I-02 | DONE badge | agent completes | badge `DONE` emerald `text-emerald-700 bg-emerald-50`; optional `{N}s` (0-dec) left of badge; `Click to view output` (if output) / `Completed successfully`; token pill `{X}K tokens` | ✅ |
| TS-I-03 | ERROR badge | agent fails | badge `ERROR` red `text-red-700 bg-red-50`; card red border; red error text = `agent.error` | ✅ (ISS-016 srini) |
| TS-I-04 | Expand output | click a DONE-with-output card | `role="button"` + `aria-expanded` toggles; `<pre>` mono `text-[10px]` `max-h-64` shows `agent.output` | 🔴 |
| TS-I-05 | Header states | through a run | running → `{completed} / {total} agents`; complete → `Done in {X.X}s`; cancelled → `Pipeline stopped`; else `Agent Progress` | ✅ |
| TS-I-06 | Progress bar | through a run | `h-0.5` fill width = completed/total; color navy normal / `bg-red-400` if any error / `bg-gray-300` if cancelled | 🔴 |
| TS-I-07 | Stop button | while running | `Stop` + `Square` icon visible only while `isRunning && !cancelled`; click → see TS-R | ✅ |
| TS-I-08 | Completion footer | on complete | `TokenUsageSummary` (TS-L) + optional `Suggested next steps` chain buttons + `New Pipeline` (`RotateCcw`) | 🔴 |
| TS-I-09 | Cards seed-then-transition | whole run | all cards exist from `pipeline_start` (seeded `idle`), transition **in place** (don't appear/disappear); stagger entry `delay index*0.04` | 🔴 |
| TS-I-10 | Duration format | any completed agent | assert regex `/\d+(\.\d)?s/` (wall-clock, non-deterministic — never assert exact value) | 🔴 |

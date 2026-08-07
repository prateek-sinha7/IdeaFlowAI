---
id: TEST-39
type: test
status: done
area: [sse, workflow, agents, auth]
summary: >-
  TS-X — Performance & timing budgets
source: .planning/TEST-REGISTER.md#ts-x-performance-timing-budgets
covers: [TS-X-01, TS-X-02, TS-X-03, TS-X-04, TS-X-05, TS-X-06, TS-X-07, TS-X-08]
---

### TS-X — Performance & timing budgets

Durations are wall-clock (assert **ranges/regex**, not exact values). Capture per-run timings to a CSV for trend tracking.

| ID | Title | Target / assert | Status |
|---|---|---|---|
| TS-X-01 | Client ping | WS sends `{type:"ping"}` every **20000ms** while OPEN (keeps long builds alive) | 🔴 |
| TS-X-02 | Reconnect backoff | `min(1000·2^n, 30000)`ms, no retry cap; banner `Connection lost. Reconnecting in {s}s… (attempt {n})` | 🔴 |
| TS-X-03 | Questionnaire auto-advance | 300ms after MCQ select | 🔴 |
| TS-X-04 | Prototype tweaks debounce | 400ms token-change → iframe rebuild | 🔴 |
| TS-X-05 | Copy toast | 2000ms revert | 🔴 |
| TS-X-06 | Custom pipeline wall-clock | `ui_custom_proto` ≈ **190s, ~$0.17** on Haiku (V2 baseline) — alert if a run exceeds ~2× baseline | ✅ baseline |
| TS-X-07 | Per-workflow budgets | record expected ranges: user_stories (clarify+6 agents), od_prototype (4 + 2 gates), od_ppt (3), app_builder (15 ≈ minutes), custom (5). Establish SLOs from first green runs | 🔴 |
| TS-X-08 | No spinner-forever | every run reaches a terminal state (no stuck `RUNNING`/`isRunning`) within its budget — the cancel/reconnect regressions this guards | ✅ (R/S) |

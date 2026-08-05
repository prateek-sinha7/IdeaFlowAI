---
id: TEST-32
type: test
status: done
area: [agents, artifacts]
summary: >-
  TS-Q — Terminal states & degraded affordance (server-signal-gated)
source: .planning/TEST-REGISTER.md#ts-q-terminal-states-degraded-affordance-server
covers: [TS-Q-01, TS-Q-02, TS-Q-03, TS-Q-04, TS-Q-05, TS-Q-06, TS-Q-07]
---

### TS-Q — Terminal states & degraded affordance (server-signal-gated)

`DegradedRunAffordance` shows when `!hasContent && isTerminal && (server failed/degraded OR reopened status∈{failed,cancelled,degraded})`. **Strictly server-derived — never a client "empty==failed" guess** (a clean empty run shows the neutral state).

| ID | Title | Steps | Expected (exact) | Status |
|---|---|---|---|---|
| TS-Q-01 | Success | normal completion | deliverable renders; header `Results`; no failure chrome | ✅ |
| TS-Q-02 | **Model error → failed (ISS-016)** | run on the **srini** backend (forces `ValidationException`) | per-agent `ERROR` badges, sanitized text `The model rejected this request.` (raw exception server-side only — WR-02); terminal `pipeline_failed` (6 `agent_error`/0 `agent_complete`); **degraded panel** `This run did not complete successfully` + `No deliverable was produced. The run ended in a failed or degraded state.` + `Failed agents` list + `View details / retry` — **NOT** DONE badges + `Output will appear here` | ✅ (V3/V8 live) |
| TS-Q-03 | Degraded (partial) | a run with `status:"degraded"` | degraded agents → `error`, others swept `done`; partial deliverable still renders; chat warning `[code:pipeline_degraded]` | 🟡 |
| TS-Q-04 | Cancelled (history) | reopen a `cancelled` run | `This run was cancelled` + `The run was stopped before producing a deliverable.` | 🔴 |
| TS-Q-05 | Clean empty ≠ failed | a completed run with no content + no failure flag | **neutral** `Output will appear here` (NOT the affordance) — server-signal-gating proof | 🟢 (degraded.test) / 🔴 UI |
| TS-Q-06 | Content wins | terminal with content but a stale `failed` flag | renders the deliverable, not the affordance | 🟢 / 🔴 UI |
| TS-Q-07 | Retry affordance | degraded run with a revise handler | `View details / retry` button → calls retry; without handler → `Open the Thinking tab to view details.` | 🔴 |

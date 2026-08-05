---
id: TEST-29
type: test
status: done
area: [sse, agents]
summary: >-
  TS-N — Mid-run human review gate (ReviewGatePanel) — HITL
source: .planning/TEST-REGISTER.md#ts-n-mid-run-human-review-gate-reviewgatepanel-h
covers: [BE-GATE-03, TS-N-01, TS-N-02, TS-N-03, TS-N-04, TS-N-05, TS-N-06, TS-N-07]
---

### TS-N — Mid-run human review gate (ReviewGatePanel) — HITL

Replaces the right panel when an agent with `gate: Human_Gate` completes. This is BE-GATE-03 / Phase 13 F1 made visible.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-N-01 | **Gate streams BEFORE await (F1)** | run od_prototype | the review modal appears **mid-run, before** you approve (not after); title `Specification Review` (specify) / `Task Plan Review` (plan); subtitle `{agent} · Review before continuing` | ✅ (S02; t=4.9s/25.5s) |
| TS-N-02 | Preview mode | observe spec/tasks | spec → `##`-section cards; tasks → `{N} task[s] · Click ✕ to remove a task before building`, deletable task rows | 🔴 |
| TS-N-03 | Edit mode | toggle `Edit` | textarea (mono) prefilled; amber dot on Edit when dirty; helper `Edit the {specification\|task list} directly. Changes will be used by the next agent.` | 🔴 |
| TS-N-04 | Approve | click approve | label `Approve & continue` (or `Approve with edits & continue` if edited); gate closes; run proceeds to next agent; `review_gate_approved` on wire | ✅ |
| TS-N-05 | Reject cancels | click `Reject & cancel pipeline` | run ends; **maps to `pipeline_cancelled`** (WR-03), no downstream agents | 🔴 |
| TS-N-06 | Empty-content gate | gate with no content | `No content was produced for review.` + `The agent returned an empty result. Reject to cancel the pipeline, or approve to continue anyway.` | 🔴 |
| TS-N-07 | Single prompt per agent | agent with inline + declared gate | pauses **exactly once** (inline suppresses the declared duplicate — WR-02) | 🟡 |

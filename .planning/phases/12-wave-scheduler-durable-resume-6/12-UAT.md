---
status: deferred
phase: 12-wave-scheduler-durable-resume-6
source: [12-VERIFICATION.md]
started: 2026-06-11T14:05:00Z
updated: 2026-06-11T14:05:00Z
deferral: end-of-milestone live pass (project convention — phase completion not blocked on live-env checks; offline evidence green)
---

## Current Test

number: 1
name: Live wave-tree panel render with N distinct worker leaves
expected: |
  WaveTreePanel renders wave groups (index, task ids, status badge running→completed)
  AND N distinct worker leaves per wave for sample_wave self×N shape; no same-agent collapse.
awaiting: end-of-milestone live pass

## Tests

### 1. Live wave-tree panel render with N distinct worker leaves
expected: WaveTreePanel renders wave groups (index + task ids + status badge flipping running→completed) and N DISTINCT worker leaves in wave 1 for sample_wave (CR-06 fix live)
result: [pending — deferred to milestone-end live pass]

### 2. Live after_seq reconnect replay — no duplicate events, no lost tail
expected: Mid-run page reload sends after_seq; tree resumes without duplicated wave/worker entries; agent_chunk text not duplicated (CR-05 live); missed tail not lost (CR-01/CR-02 live)
result: [pending — deferred to milestone-end live pass]

### 3. Second run resets wave panel and reconnect cursor
expected: After run 1 completes, starting run 2 clears the previous wave panel and sends after_seq=0 on first reconnect (WR-03 per-run reset live)
result: [pending — deferred to milestone-end live pass]

## How to run (milestone-end live pass)

1. Backend: `cd backend && python3.11 -m uvicorn app.main:app --reload`
2. Frontend: `cd frontend && npm run dev`
3. Run the `sample_wave` workflow (any `wave_scheduler`-strategy step) from the composer UI
4. Execute tests 1–3 above; also confirm no existing panel (AgentProgressPanel / ValidatorIssuePanel / preview) changed for a no-waves workflow

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

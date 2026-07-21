---
status: testing
phase: 29-transport-cutover-chat-backbone-a1
source: [29-VERIFICATION.md]
started: 2026-07-08T00:00:00Z
updated: 2026-07-08T00:00:00Z
---

## Current Test

number: 1
name: Live SSE attach + RunConnectionProvider mounted at app root
expected: |
  With RunConnectionProvider mounted in frontend/src/app/layout.tsx and NEXT_PUBLIC_SSE_TRANSPORT=true, a logged-in user's live run attaches its SSE stream; the connection state machine reaches 'live'; the dashboard reducer updates identically to the WS path; the replay cursor persists across a route change/reload.
awaiting: user response

## Tests

### 1. Live SSE attach + RunConnectionProvider mounted at app root
expected: Connection state machine reaches 'live', dashboard reducer updates identically to the WS path, cursor persists across reload/route-change against a real backend.
why_human: RunConnectionProvider.tsx is built, mocked-driver-tested, and imported by useWorkflow.ts via useRunConnection(), but is NOT mounted in app/layout.tsx (out of the plan's LOCK-B allow-list — 29-07-SUMMARY.md). Needs a running server + browser session.
result: [pending]

### 2. Live steering note lands in the next agent's composed prompt (DEF-29-09-1)
expected: Posting a steering chat turn on a RUNNING pipeline (live Bedrock) causes the next dispatched agent's context to include the steering text inside a `=== USER GUIDANCE ===` block; one-shot notes disappear after one dispatch, sticky notes persist.
why_human: The router computes CHANNEL_STEERING and apply_steering() appends to ectx.steering_notes; engine.py composition is offline-proven (test_steering_seam.py). The LIVE endpoint -> running in-process ectx handle lookup is not wired this phase (needs an engine.py edit outside 29-09's allow-list). Needs a live running pipeline.
result: [pending]

### 3. Live narrator chat_reply cards appear on the down-channel
expected: Triggering a clarify / gate / pipeline-complete / deliverable / spec-revision milestone on a live run persists a chat_reply run_events row AND delivers it live on the down-channel (SSE/WS) as the milestone fires.
why_human: chat_narrator.py's project_milestone_card / persist_milestone_card are proven correct + golden-neutral via 23 offline unit tests, but have no production call site yet (grep confirms zero callers) — documented in 29-10-SUMMARY.md as an explicit LOCK-B deferral. Needs the milestone->card wiring + a live run.
result: [pending]

### 4. Re-confirm the pre-existing feat/ui-2 baseline failures (DEF-29-06-1 / DEF-29-04-1)
expected: The full mocked Playwright suite (~120/123 failing) and test_run_pipeline_validation.py (12/50 failing) show the SAME counts as before Phase 29, on files Phase 29 never touched — confirming they are pre-existing branch baseline breakage, not Phase-29 regressions.
why_human: Quick sanity re-confirmation (already evidenced via git diff showing the failing files are absent from every Phase-29 commit); not a Phase-29 fix obligation. Owner: the feat/ui-2 UI-convergence workstream (dashboard-home redesign / KAN-78 + widened custom-agent-pool).
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps

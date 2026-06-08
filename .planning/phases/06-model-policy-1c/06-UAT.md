---
status: testing
phase: 06-model-policy-1c
source: [06-VERIFICATION.md, 06-REVIEW.md]
started: 2026-06-08T16:30:00Z
updated: 2026-06-08T16:30:00Z
---

## Current Test

number: 1
name: CR-02 live-checkpointer fallback restart (mid-stream Bedrock throttle)
expected: |
  The APPROACH-B fallback retry uses thread_id `{base}:retry1`, LangGraph creates a NEW
  checkpoint thread rather than resuming the throttled attempt's partial state under the base
  thread_id, the `agent_model_fallback` event carries `reset_output: true`, and the final
  deliverable reflects only the fallback model's output (no mixed-model graph replay).
awaiting: user response (requires a live Bedrock + Postgres-checkpointer environment)

## Tests

### 1. CR-02 live-checkpointer fallback restart
expected: |
  Run a pipeline against a LIVE Bedrock backend with the Postgres LangGraph checkpointer.
  During an agent's streaming run, AFTER partial tokens have been emitted, induce/simulate a
  Bedrock `ThrottlingException` on the primary model. Confirm:
  (a) the fallback retry rebuilds with thread_id `{base_thread_id}:retry1`;
  (b) LangGraph starts a clean graph on the new thread (does NOT resume the partial checkpoint
      written under the base thread_id by the throttled attempt);
  (c) the `agent_model_fallback` event is emitted with `fallback_model` = next chain id and
      `reset_output: true`;
  (d) the final deliverable is coherent (only the fallback model's output; no duplicate node replay).
why_human: |
  The offline scripted-model harness uses the InMemory checkpointer, which writes no mid-stream
  state, so a stale-checkpoint resume cannot be triggered offline. The code fix
  (`engine.py:1842` `retry_thread_id = f"{thread_id}:retry{_attempt}"`) is present and provably
  correct for the offline path (test_model_fallback.py 4/4). Only a live Postgres checkpointer
  receiving a mid-stream write before the throttle fires can confirm the `:retry{n}` thread
  diverges cleanly from the partial base checkpoint. Pre-identified as non-blocking in 06-REVIEW.md
  per the phase's offline-test-only constraint (D-06: no live Bedrock).
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

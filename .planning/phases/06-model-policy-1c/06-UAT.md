---
status: complete
completed_at: 2026-06-12
deferred_to: end-of-milestone live-verification pass (staging Bedrock + Postgres checkpointer)
deferred_decision: "User accepted offline evidence and deferred this live item on 2026-06-08; closed by the 2026-06-12 milestone-end live re-pass."
phase: 06-model-policy-1c
source: [06-VERIFICATION.md, 06-REVIEW.md]
started: 2026-06-08T16:30:00Z
updated: 2026-06-12T19:30:00Z
---

## Current Test

[testing complete — deferred live item closed 2026-06-12]

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
  state, so a stale-checkpoint resume cannot be triggered offline. Only a live Postgres
  checkpointer receiving a mid-stream write before the throttle fires can confirm the
  `:retry{n}` thread diverges cleanly from the partial base checkpoint.
result: pass
notes: |
  Closed 2026-06-12 on the milestone-end live re-pass (driver /tmp/cr02_driver.py; evidence
  /tmp/flowin-live-evidence/01-cr02-checkpointer-fallback.md + .planning/live-verification/
  REPORT-2026-06-12.md). Real AsyncPostgresSaver (Postgres 16, alembic 0020) + real Bedrock
  Haiku 4.5 fallback; primary (Sonnet 4.5 catalog id) bound to an induced-throttle model that
  streamed 3 marker chunks then raised a real botocore ThrottlingException.
  (a) PASS — checkpoints table holds BOTH `{run}:domain-analyst` AND `{run}:domain-analyst:retry1`.
  (b) PASS — the base thread froze with partial durable graph state (3 checkpoints ending at
      `branch:to:model`) and stayed untouched; the retry thread ran a FRESH full lifecycle
      (5 checkpoints from `__start__` to terminal); no marker text anywhere downstream.
      The live-Postgres-only precondition was observed: the base thread received mid-stream
      durable writes BEFORE the throttle — exactly the stale-resume hazard the fix guards.
  (c) PASS — exactly one `agent_model_fallback` {fallback_model: eu.anthropic.claude-haiku-4-5-…,
      attempt: 2, reset_output: true}; runner B1 re-raise observed in the log.
  (d) PASS — final deliverable a coherent Haiku-only domain analysis, marker-free.
  NOTE: the engine seam cited at plan time as engine.py:1842 now lives at engine.py:2429
  (line drift only; same `retry_thread_id = f"{thread_id}:retry{_attempt}"` seam).

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]

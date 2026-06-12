# Phase 14 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed; see executor scope boundary).

## 1. Pre-existing: test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack fails offline (environment-gated)

- **Found during:** 14-02 wave-gate battery (2026-06-12)
- **Symptom:** `Failed: DID NOT RAISE asyncio.CancelledError` at tests/unit/test_pipeline_cancel.py:180, preceded by a REAL Bedrock call: `Failed to generate workflow title ... ExpiredTokenException ... security token expired` (websocket.py:403).
- **Pre-existing proof:** fails byte-identically with `backend/app/api/websocket.py` checked out at HEAD~2 (before any 14-02 change). Not in any 14-02 verify command (the plan names test_run_pipeline_validation.py + test_pipeline_failure_semantics.py; test_pipeline_cancel.py was an extra read_first reference only).
- **Likely cause:** the test path reaches the live `_generate_workflow_title` Bedrock call (no monkeypatch / expired local AWS session) — an offline-environment gating gap in the test, same family as the known "full backend pytest hangs offline" memory note.
- **Disposition:** out of scope for 14-02 (no file this plan touched is implicated). Candidate for the milestone-end live pass or a test-hardening quick task (no-op the title generator in that test, as test_pipeline_failure_semantics.py already does).

### UPDATE 2026-06-12 (milestone-end live pass) — root cause SUPERSEDED by LV-01

The "expired AWS session / live Bedrock title call" hypothesis is **disproven**: with VALID
credentials the test still fails deterministically (3/3 runs). Actual root cause: the handler
task finishes normally (`result=None`) because the test's `task.cancel()` at t=0.15s collides
with the stub's 0.05s-cadence events inside `asyncio.wait_for(event_queue.get(), timeout=10.0)`
(websocket.py:1669) — the CPython 3.11 `wait_for` result-vs-cancel race absorbs the
cancellation. The same wait_for pattern exists at websocket.py:802 and :1999 (latent in prod:
a swallowed disconnect-cancel just degrades to the next-send-fails drainer exit). Candidate
fix: `asyncio.timeout()` (3.11+, correct cancellation semantics) at the three drainer sites
and/or re-time the test cancel off the event boundary. Full diagnosis:
`.planning/live-verification/REPORT-2026-06-12.md` (LV-01).

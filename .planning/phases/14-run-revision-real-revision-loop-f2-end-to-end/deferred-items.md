# Phase 14 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed; see executor scope boundary).

## 1. Pre-existing: test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack fails offline (environment-gated)

- **Found during:** 14-02 wave-gate battery (2026-06-12)
- **Symptom:** `Failed: DID NOT RAISE asyncio.CancelledError` at tests/unit/test_pipeline_cancel.py:180, preceded by a REAL Bedrock call: `Failed to generate workflow title ... ExpiredTokenException ... security token expired` (websocket.py:403).
- **Pre-existing proof:** fails byte-identically with `backend/app/api/websocket.py` checked out at HEAD~2 (before any 14-02 change). Not in any 14-02 verify command (the plan names test_run_pipeline_validation.py + test_pipeline_failure_semantics.py; test_pipeline_cancel.py was an extra read_first reference only).
- **Likely cause:** the test path reaches the live `_generate_workflow_title` Bedrock call (no monkeypatch / expired local AWS session) — an offline-environment gating gap in the test, same family as the known "full backend pytest hangs offline" memory note.
- **Disposition:** out of scope for 14-02 (no file this plan touched is implicated). Candidate for the milestone-end live pass or a test-hardening quick task (no-op the title generator in that test, as test_pipeline_failure_semantics.py already does).

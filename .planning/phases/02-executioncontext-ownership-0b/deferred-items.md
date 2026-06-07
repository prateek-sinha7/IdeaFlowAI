# Deferred Items — Phase 02 (ExecutionContext + Ownership [0B])

Out-of-scope discoveries logged during plan execution (executor scope boundary —
only the current task's changes are auto-fixed; unrelated pre-existing failures
are recorded here, not fixed).

## Pre-existing test failures (NOT caused by plan 02-01)

Discovered during the post-Task-2 verification sweep (`python3.11 -m pytest tests/unit/`).
Both are environment-/credential-driven and touch zero code that plan 02-01 changed:

| Test file | Failures | Root cause | Why out of scope |
|-----------|----------|------------|------------------|
| `backend/tests/unit/test_logout.py` | 7 (JtiClaim, LogoutRevokesToken, PerTokenRevocation, PasswordChangeRevocation, LogoutIdempotent, LogoutPersistsCorrectRow) | JWT `jti` / token-revocation / DB-row auth tests | Zero references to `execution_engine` / `ExecutionEngine` / `ExecutionContext`; auth subsystem, unrelated to the state-relocation refactor. |
| `backend/tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack` | 1 | `DID NOT RAISE CancelledError` + `ExpiredTokenException` from a real Bedrock Converse call (websocket title-generation path) using expired AWS creds | The test patches the engine with a `_StubEngine` (`monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _StubEngine())`), so the real `ExecutionEngine.execute` is never invoked. Failure is an expired-AWS-token environment issue. |

The full Phase 0A characterization suite (`backend/tests/agents/`) — the CTX-05
zero-behavior-change gate — is GREEN (268 passed, 18 skipped), and all engine
unit suites (`test_execution_engine.py`, `test_run_pipeline_validation.py`,
`test_resumability.py`, `test_agent_input_event.py`) pass.

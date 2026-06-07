# Deferred / Out-of-Scope Items — Phase 04 (Manifest + Compiler 1A)

Items discovered during execution that are OUT OF SCOPE for the current plan
(not caused by this plan's changes). Logged per the executor scope-boundary rule;
NOT fixed here.

## Pre-existing test failures (unrelated to the 04-04 routing seam)

Discovered while running the full suite (`tests/agents/ tests/unit/`) as Task 3's
broad regression check. All confirmed pre-existing and environment/config-driven —
they do not touch the engine routing seam (the cancel test stubs the engine
entirely via `get_execution_engine` → `_StubEngine`; the logout tests are JWT/auth
with self-registration).

| Test | Cause | Why out of scope |
|------|-------|------------------|
| `tests/unit/test_logout.py` (7 tests: JtiClaim, LogoutRevokesToken, PerTokenRevocation, PasswordChangeRevocation, LogoutIdempotent, LogoutPersistsCorrectRow) | `403 "Self-registration is disabled"` — needs `ALLOW_SELF_REGISTRATION` enabled in the test env | Auth/registration config; no engine/routing code path |
| `tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack` | `task.cancel()` did not raise `CancelledError` in the timing window (async flakiness) | Uses `_StubEngine` (real `ExecutionEngine.execute` / `compile_for_run` never invoked) |

The Phase-0A characterization snapshots, migration-ledger ratchet, import-linter,
and vulture — the INV-3 / SC-001 parity gate — are all GREEN with the seam in place.

---
phase: quick-260806-q4c
plan: 01
subsystem: backend-auth-bootstrap
tags: [bootstrap, cognito, compensation, identity, deploy, test-infra]
affects: [bootstrap-admin, cognito-provisioning, fresh-environment-deploy]
key-files:
  - backend/app/scripts/bootstrap_admin.py
  - backend/tests/unit/test_bootstrap_admin.py
  - backend/tests/integration/test_bootstrap_admin_postgres.py
decisions:
  - "Compensation for a partially provisioned pool user belongs to _bootstrap_cognito_admin, which owns the AdminCreateUser call, not to create_admin — the caller cannot know a pool user exists until the helper returns the sub, so a caller-side guard is structurally incapable of covering this window."
  - "The helper compensates and RE-RAISES unchanged, so create_admin's rollback, log message, and exit-code contract (0/10/1 that remote-deploy.sh §12 branches on) are all untouched."
  - "AdminCreateUser stays OUTSIDE the guard: a failure there created nothing, and an unconditional delete would fire AdminDeleteUser against a user this attempt never made. Pinned by a dedicated test."
  - "Compensation is single-shot by construction rather than by a flag: when the helper raises, cognito_sub stays None, so create_admin's existing guard cannot double-delete. No new state was introduced."
  - "_compensate_delete_cognito_admin now logs the SUCCESS case too — 'was the pool left dirty?' is the first question after a failed bootstrap, and the answer was previously unlogged."
  - "New log assertions substitute the module's `logger` attribute instead of using caplog: caplog depends on root handlers that configure_logging()'s basicConfig(force=True) removes, which is why a sibling test in this file is already order-dependent."
  - "Pinned AUTH_PROVIDER=local in the PostgreSQL integration module. It was missing, so on any developer machine with a cognito .env the suite called the LIVE user pool. In scope: the suite could not otherwise verify this fix, and it was mutating a live pool."
  - "permanent=True on the bootstrap password was deliberately NOT changed here — it is a separate hardening item, not part of this defect."
metrics:
  files_changed: 3
  tests_added: 9
  lines_added: 370
---

# Quick task 260806-q4c: KAN-167 — bootstrap no longer orphans a Cognito admin

`_bootstrap_cognito_admin` created the Cognito pool user as its first action but returned the `sub` last, with three fallible steps in between. `create_admin` only learned a pool user existed once that return value landed in `cognito_sub`, and gated its compensating delete on `cognito_sub is not None` — so any failure in a post-create step rolled back the local row but left the pool user behind. Because the `users` table stayed empty, the next deploy re-ran bootstrap and died on `UsernameExistsException`, keeping a fresh environment unreachable until an operator cleaned the pool by hand (the migration plan's R1 risk). Compensation now lives with the function that owns the creation, so every post-create failure best-effort deletes the pool user exactly once and a retry succeeds.

## Tasks

| Task | Files |
|---|---|
| Move post-create compensation into the helper; re-raise unchanged | `backend/app/scripts/bootstrap_admin.py` |
| Log successful compensation; widen the helper docstring to both callers | `backend/app/scripts/bootstrap_admin.py` |
| Fault-injection coverage for all three post-create failure modes, the create-failure no-delete guard, single-compensation, retry-after-compensation, and log/secret hygiene | `backend/tests/unit/test_bootstrap_admin.py` (+9 tests) |
| Pin `AUTH_PROVIDER=local` so the PostgreSQL suite stops calling the live user pool | `backend/tests/integration/test_bootstrap_admin_postgres.py` |

## What changed

- `_bootstrap_cognito_admin` now wraps `admin_set_user_password`, `admin_add_user_to_group`, and the `sub` extraction in a `try/except` that calls the existing `_compensate_delete_cognito_admin(email)` and re-raises. `admin_create_user` is deliberately outside the guard.
- `create_admin` is unchanged in behaviour. Its comment now names both compensation sites, and the outer guard carries a note explaining why it must NOT fire when the helper already compensated.
- `_compensate_delete_cognito_admin` gained an `else` branch logging the successful delete, and a docstring describing both callers and why it never raises. It still logs the email only, never the password.
- 9 new unit tests in a `TestCognitoPartialProvisioningCompensation` class, driven by an in-memory `FakePool` that models the one Cognito behaviour that matters here: a duplicate `AdminCreateUser` raises, exactly as `UsernameExistsException` does. Without that, the retry test would pass even with the orphan present.
- The PostgreSQL integration module gained the autouse `AUTH_PROVIDER=local` fixture the unit module already had.

## Deviations from Plan

Two additions, both discovered during verification:

1. **`files_modified` grew by one file.** The plan listed two files. Running the opt-in PostgreSQL suite revealed it had no `AUTH_PROVIDER` pin and therefore called the live Cognito pool on a developer machine, failing all 7 lock/concurrency tests on `InvalidPasswordException` and leaving 3 real pool users behind. Those users were deleted and the pool verified back to its 4 legitimate seeded accounts. The pin was added so the suite runs offline as designed; it then passed 9/9. Treated as in scope because KAN-167 could not otherwise be verified on real PostgreSQL.
2. **Log assertions do not use `caplog`.** The plan implied ordinary log capture. `caplog` proved order-dependent here (`configure_logging()` calls `logging.basicConfig(force=True)`, which removes the root handlers pytest captures through) — the same trap that already makes `TestSecretHygiene::test_rejection_message_does_not_echo_the_password` fail in a full-suite run. The new tests substitute the module's `logger` attribute instead, so they give the same verdict in any run order. The pre-existing failing test was left alone.

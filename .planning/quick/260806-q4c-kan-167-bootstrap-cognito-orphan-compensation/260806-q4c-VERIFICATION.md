---
phase: quick-260806-q4c
verified: 2026-08-06
status: passed
---

# Verification — KAN-167 bootstrap Cognito partial-provisioning compensation

## Truths verified

| Truth | Evidence |
|---|---|
| A failure in `AdminSetUserPassword` after create deletes the pool user | `test_aws_failure_after_create_deletes_the_pool_user[admin_set_user_password]` asserts `pool.delete_calls == ["admin@example.com"]`, `pool.users == set()`, and no local row. PASSES with the fix; FAILS on the pre-fix source (`AssertionError: assert [] == ['admin@example.com']`), proven by stashing only `bootstrap_admin.py`. |
| A failure in `AdminAddUserToGroup` after create deletes the pool user | Same parametrized test, `[admin_add_user_to_group]` case. PASSES with the fix; FAILS pre-fix with the same empty-`delete_calls` assertion. |
| A failure to extract `sub` deletes the pool user | `test_missing_sub_in_create_response_deletes_the_pool_user` drives a create response with no `sub` attribute (the `next(...)` raises `StopIteration` with the pool user already created). PASSES with the fix; FAILS pre-fix. |
| An `AdminCreateUser` failure deletes nothing | `test_create_failure_deletes_nothing` asserts `pool.delete_calls == []`. Passes both pre- and post-fix by design — it is the guard against over-correcting into an unconditional delete, so it is the one test in the class that must NOT be RED. |
| Compensation happens exactly once per failed bootstrap | `test_compensation_happens_exactly_once` asserts `len(pool.delete_calls) == 1`. The helper compensates and re-raises; `cognito_sub` is still `None`, so `create_admin`'s outer guard does not fire a second `AdminDeleteUser`. PASSES with the fix; FAILS pre-fix (`assert 0 == 1`). |
| A retry after a compensated failure succeeds | `test_retry_after_compensation_succeeds` — the fake pool raises on a duplicate create exactly as Cognito's `UsernameExistsException` does, so this is a real acceptance test. First attempt fails at `admin_set_user_password`, second attempt returns `EXIT_OK` with `cognito_sub` set, `auth_provider="cognito"`, `is_admin=True`, `password_hash is None`, and `flowin-admins` membership. PASSES with the fix; FAILS pre-fix (`assert 1 == 0` — the retry dies on the leftover pool user). |
| A failed compensation is logged and does not mask the original cause | `test_failed_compensation_is_logged_and_still_returns_error` sets `delete_raises`; asserts `EXIT_ERROR`, a `failed to compensate-delete` message, AND that the original `admin_add_user_to_group` failure is still reported. PASSES with the fix; FAILS pre-fix. |
| A successful compensation is visible to the operator | `test_successful_compensation_is_logged` asserts a `compensated` message. PASSES with the fix; FAILS pre-fix. |
| No compensation log leaks the password | `test_no_compensation_log_leaks_the_password` asserts `VALID_PASSWORD not in logged` and that the email IS present. PASSES with the fix. Re-read of the two new/changed log call sites confirms both interpolate `email` only. |
| Existing behaviour unchanged (local path, Cognito success, idempotent no-op, lock gating, validation, local-commit compensation) | Full module green: `uv run pytest tests/unit/test_bootstrap_admin.py` → **62 passed** (53 pre-existing + 9 new). No pre-existing test was edited. |
| Real PostgreSQL lock + concurrency behaviour still holds | `tests/integration/test_bootstrap_admin_postgres.py` → **9 passed** against a throwaway `bootstrap_admin_test` database (created and dropped by a temporary helper, since deleted). Covers the real `LOCK TABLE ... SHARE ROW EXCLUSIVE`, lock release on commit/no-op-rollback, 2- and 5-way racing callers creating exactly one user, and an ordinary INSERT being serialised by the lock. |
| No regression in the wider backend unit suite | `uv run pytest tests/unit` → **39 failed / 1233 passed / 4 errors**. Baseline on stashed source: **39 failed / 1224 passed / 4 errors**. Identical failure count; delta is exactly +9 passes (the 9 new tests). |
| Static analysis clean | `uv run ruff check` on all three changed files → "All checks passed!". `uv run pyright` on all three → "0 errors, 0 warnings". `uv run vulture app/scripts/bootstrap_admin.py` → no findings. |
| Import boundaries unchanged | `uv run lint-imports` → 3 kept / 1 broken. The broken contract (`agents.capabilities.strategies.task_loop -> agents.execution_engine.od_context`) is **pre-existing and unrelated** — confirmed byte-identical output with all changes stashed. No `agents/` file was touched. |

## Commands run

```
uv run pytest tests/unit/test_bootstrap_admin.py -q                  # 62 passed
uv run pytest tests/unit/test_bootstrap_admin.py::TestCognitoPartialProvisioningCompensation
                                                                     # pre-fix: 8 failed, 1 passed (RED proof)
uv run pytest tests/unit -q                                          # 39 failed / 1233 passed / 4 errors (baseline: 39 / 1224 / 4)
tests/integration/test_bootstrap_admin_postgres.py (throwaway DB)     # 9 passed
uv run ruff check app/scripts/bootstrap_admin.py tests/unit/test_bootstrap_admin.py tests/integration/test_bootstrap_admin_postgres.py
uv run pyright  <same three files>                                   # 0 errors
uv run vulture app/scripts/bootstrap_admin.py                        # clean
uv run lint-imports                                                  # 1 broken, pre-existing, unrelated
```

## Live-pool incident during verification (found, fixed, cleaned)

The first PostgreSQL run made **real AWS calls**. `tests/integration/test_bootstrap_admin_postgres.py`
had no `AUTH_PROVIDER` pin (unlike the unit module, which documents exactly this
rail), so with a developer `.env` set to `cognito` — the normal state since the
migration — `create_admin` took the Cognito branch and called the live pool.

- It created real pool users for `admin@`, `first@`, `second@example.com`, then
  failed on `InvalidPasswordException`: this module's `VALID_PASSWORD`
  (`bootstrap-password-0123456789`) meets the command's 16-char floor but not the
  pool's uppercase policy. All 7 lock/concurrency tests failed for a reason with
  nothing to do with PostgreSQL.
- Three users were left behind (`FORCE_CHANGE_PASSWORD`, no local row — precisely
  the orphan shape this ticket is about). The `admin0..admin4@example.com` users
  from the 5-way race were correctly compensated and absent, so compensation
  itself was working; the residue is attributable to the repeated
  create/compensate cycling across tests reusing the same three addresses.
- **Cleanup performed:** those three users were deleted via `admin_delete_user`
  (verified working with current credentials). The pool was re-listed and holds
  exactly the 4 legitimate seeded users (`qa-basic`, `qa-pro`, `qa-enterprise`,
  `qa-admin@flowinqa.com`) — its pre-run state. Re-listed again after the second
  run: still 4, no new users.
- **Root cause closed:** added the autouse `_force_local_auth_provider` fixture to
  the integration module, mirroring the unit module. The suite then passed 9/9
  fully offline. This is in scope because the suite is unrunnable-as-intended
  without it and it was silently mutating a live pool.

## Gaps Summary

Two gaps, both pre-existing and explicitly **not** introduced by this fix:

1. `TestSecretHygiene::test_rejection_message_does_not_echo_the_password` passes
   in isolation and fails under `pytest tests/unit`. Cause: it asserts via
   `caplog`, which hangs a handler on the ROOT logger, while
   `configure_logging()` calls `logging.basicConfig(force=True)` and removes
   every root handler. Confirmed pre-existing by running the full suite with all
   changes stashed — it fails identically there. Left untouched (no collateral
   cleanup); the new tests avoid the trap entirely by substituting the module's
   `logger` attribute, so they are order-independent. Worth a separate one-line
   test-infra fix.
2. `lint-imports` reports one broken contract in `agents.capabilities.strategies.task_loop`.
   Pre-existing and unrelated; no `agents/` file was touched.

Not attempted: live Cognito verification of the compensation path against a real
pool with a policy-conformant password. The offline stubs assert the exact call
sequence, and the accidental live run above independently demonstrated that a
post-create failure is now compensated rather than orphaned.

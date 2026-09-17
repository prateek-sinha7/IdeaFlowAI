# Operations scripts

Standalone scripts for operational tasks: user management, reconciliation, incident response.

## User management and reconciliation

### `reconcile_cognito_users.py`

Syncs the local `users` table with the Cognito pool, catching drift that occurs when users are created/deleted/disabled in the Cognito console without going through the application's own lifecycle endpoints.

**Read-only report (safe to run anywhere, anytime):**
```powershell
cd backend
uv run python app/scripts/reconcile_cognito_users.py --report
```

Lists every local row that is missing from the pool, disabled in the pool, has the wrong email, or has a `cognito_sub` collision. Non-zero exit code if drift is found.

**Fix mode (write to DB + pool, should be run from an authoritative environment only):**
```powershell
uv run python app/scripts/reconcile_cognito_users.py --fix-disabled
```

Sets local `users.status = 'disabled'` for rows whose pool user is disabled, and advances `tokens_valid_from` + clears the stored refresh token so outstanding access tokens from those users are rejected.

**Detailed help:**
```powershell
uv run python app/scripts/reconcile_cognito_users.py --help
```

### `retry_cognito_deletions.py`

Retries failed user deletions. When `AdminDeleteUser` fails after the local row was already deleted and the account was already disabled/signed-out, a `PendingCognitoDeletion` record is created. This script drains that queue.

**Dry-run (shows what would be retried):**
```powershell
cd backend
uv run python app/scripts/retry_cognito_deletions.py --dry-run
```

**Execute (retries with exponential backoff, max 3 attempts, min 2s / max 300s between attempts):**
```powershell
uv run python app/scripts/retry_cognito_deletions.py
```

Exits cleanly after exhausting all retries; a second run picks up where the first left off. Monitor CloudTrail for the actual `AdminDeleteUser` API calls.

**Detailed help:**
```powershell
uv run python app/scripts/retry_cognito_deletions.py --help
```

## Incident response

For recovery procedures when Cognito is unreachable or an admin account is locked out, see `docs/runbooks/admin-recovery.md`. That guide covers:

- Provisioning the first admin in a fresh environment
- Recovering a locked-out admin (lost MFA device, forgotten password)
- Reverting a disabled account by mistake
- Revoking a compromised account immediately
- Checking for and preventing accidental last-admin removal

All recovery operations use AWS IAM credentials and the Cognito console or CLI — not the application itself — because recovery must work when the application is down or unavailable.

## Related

- `docs/architecture/authentication-and-authorization.md` — the authentication and authorization model.
- `docs/runbooks/cognito-cutover.md` — provisioning a new environment with Cognito.
- `docs/runbooks/admin-recovery.md` — recovery procedures and incident response.

</content>
</invoke>
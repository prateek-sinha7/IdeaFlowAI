# Cognito cutover runbook

> Operational procedures for provisioning a new environment with Cognito authentication or updating an existing environment after infrastructure changes. Cognito is now the **sole** authentication authority: there is no `AUTH_PROVIDER` switch, no dual-accept JWT window, and no local/break-glass admin anywhere in this codebase. This runbook is a straight-line provisioning + verification procedure, not a cutover between two live providers.

## Who this is for

An operator provisioning a **new** environment, or bringing an existing
environment's Terraform/deploy up to date after Phase 4 removed the legacy
auth flags. If the environment has already completed every step below once,
re-running this runbook is a no-op verification pass.

## 0. Preconditions

- You hold (or can obtain) an AWS IAM principal that can run
  `terraform plan`/`apply` against `infra/terraform/foundation` for this
  environment, and separately an IAM principal with `cognito-idp:Admin*`
  against the pool for step 5 (see `docs/runbooks/admin-recovery.md` for why
  these are deliberately not the same as the application's own scoped role).
- `backend/.env` (or the deployed box's `/etc/velocityai/app.env`, depending
  on where you're running from) has a working `DATABASE_URL`.
- You have read `.planning/COGNITO-MIGRATION-PLAN.md`'s Amendment A1 banner if
  you need the full history of *why* the shape below is what it is — this
  runbook only covers *what to do*.

## 1. Pre-flight: check for unlinked local users

If this environment has never run any part of the Cognito migration, or ran
only partially, there may be local `users` rows with no `cognito_sub`.
Migration `0038` refuses to apply against any such row (`cognito_sub IS NULL`,
a duplicated `cognito_sub`, or a non-`cognito` legacy `auth_provider` value),
so this has to be resolved **before** running migrations, not after.

From `backend/`:

```powershell
uv run python scripts/migrate_local_users_to_cognito.py --report
```

This is read-only and lists every row needing attention. Depending on what it
finds:

- **Rows whose email already exists as a pool user** (e.g. someone was
  created in Cognito out-of-band already): adopt the existing `sub` by email
  match.

  ```powershell
  uv run python scripts/migrate_local_users_to_cognito.py --link --apply
  ```

- **Rows with no matching pool user**: invite them. This calls
  `AdminCreateUser(..., DesiredDeliveryMediums=[EMAIL])` — never a permanent
  password — for every row `--link` could not resolve.

  ```powershell
  uv run python scripts/migrate_local_users_to_cognito.py --invite --apply
  ```

Both subcommands default to a dry run; `--apply` is required to actually
write. Re-run `--report` afterward until it shows zero candidate rows.

Both `--link` and `--invite` set `auth_provider = 'cognito'` alongside
`cognito_sub` while that pre-`0038` column still exists. Both halves matter:
`0038` rejects a non-`cognito` `auth_provider` just as firmly as a NULL
`cognito_sub`, so a row with only the sub written stays blocked.

`--link` **refuses** (non-zero exit) to re-point a row that already carries a
different `cognito_sub` than the pool returns for that email. That is an
account-takeover shape, and it is the same fail-closed behaviour
`core/provisioning.py::_link_or_refuse` applies at runtime. Resolve those
deliberately via `docs/runbooks/admin-recovery.md`; the script will not pick a
principal for you.

If this environment has **no existing local users at all** (Decision 5's
default assumption, still true for a genuinely fresh environment), skip this
step — there is nothing to migrate, and the first admin is created directly
in the pool in step 5.

### This is now enforced by the deploy, not just by this runbook

`.github/scripts/remote-deploy.sh` §10a runs the same check automatically on
every deploy, in the newly pulled backend image, between `docker compose pull`
and `up -d`:

```sh
docker compose ... run --rm --no-deps --entrypoint python backend \
    scripts/migrate_local_users_to_cognito.py --report --fail-on-unlinked
```

`--fail-on-unlinked` is what makes it gate — plain `--report` always exits 0.
It is read-only, and on a database with no `users` table yet (a first-ever
deploy) it passes.

This exists because migrations are **not** a deploy step:
`backend/docker-entrypoint.sh` runs `alembic upgrade head` under `set -eu`
before `exec uvicorn`. Without the gate, an unlinked row means the backend
container exits, `restart: unless-stopped` loops it, `:8000` never binds, and
the §11 health gate spends its full five minutes before rolling the images
back — reporting "health gate failed" rather than the actual cause. With the
gate, the deploy stops in seconds, names the offending rows, and leaves the
running stack untouched.

`--entrypoint python` is load-bearing: without it the gate command would run
`alembic upgrade head` itself, which is the thing being gated. The contract is
pinned by `backend/tests/unit/test_cognito_link_deploy_gate.py`.

If a deploy fails here, resolve the listed rows with `--link` / `--invite`
above and re-run the deploy. Nothing was changed on the box.

## 2. Terraform: provision or update Cognito + supporting infrastructure

From `infra/terraform/foundation`:

```powershell
terraform fmt -check -recursive
terraform validate
terraform plan -var-file="<env>.tfvars" -out=tfplan
```

Review the plan. As of Phase 4, expect:

- `cognito_enabled` is no longer overridable to `false` — the variable
  carries a `validation` block requiring `true`. A plan that somehow tries to
  disable it fails validation outright rather than producing a Cognito-less
  stack.
- `admin_mfa_required` now **defaults to `true`**. An environment whose admins
  have not yet enrolled MFA should set `admin_mfa_required = false` explicitly
  in its own `<env>.tfvars` until they have (see step 6) — otherwise every
  admin route 403s for every admin the instant this applies, including
  whoever is trying to fix it.
- No `auth_provider`, `auth_allow_legacy_jwt`, or `break_glass_enabled` values
  anywhere in the plan — those variables were removed. If your `<env>.tfvars`
  still sets any of them, `terraform plan` will fail with an unknown-variable
  error; delete those lines.
- If this is the first apply for this environment, a new
  `flowin-tier-hexaware` Cognito group at precedence 15 (between
  `flowin-tier-enterprise` at 10 and `flowin-tier-pro` at 20) alongside the
  four pre-existing groups (`flowin-admins`, `flowin-tier-enterprise`,
  `flowin-tier-pro`, `flowin-tier-basic`).

Apply once you're satisfied:

```powershell
terraform apply tfplan
```

## 3. Deploy

Run the environment's `deploy.yml` workflow (or your normal deploy path) as
usual. Nothing in the deploy step is Cognito-specific anymore beyond pushing
`COGNITO_USER_POOL_ID` / `COGNITO_CLIENT_ID` / `COGNITO_CLIENT_SECRET` /
`COGNITO_REGION` to SSM if you've chosen the pipeline-owned posture for them
(see `docs/GITHUB_CICD_SETUP.md` §3.2.1) — Terraform-owned (the default) needs
no action here at all.

## 4. Apply database migrations

```powershell
uv run alembic upgrade head
```

Confirm exactly one head:

```powershell
uv run alembic heads
```

If this prints more than one revision, stop — do not deploy against a
two-head chain (`docker-entrypoint.sh` runs the upgrade under `set -eu` and
will crash-loop the container). Re-home the newer migration onto the actual
head before proceeding; see the project index's Alembic section for the
history of prior collisions.

## 4a. Pre-flight SQL (read-only)

Before applying migrations or deploying, run these queries against the target database to identify potential issues:

```sql
-- C1: Find local users with NULL cognito_sub (migration 0038 will refuse to apply)
SELECT id, email, cognito_sub FROM users WHERE cognito_sub IS NULL;

-- C2: Find duplicate cognito_sub values (unique constraint violation risk)
SELECT cognito_sub, COUNT(*) FROM users WHERE cognito_sub IS NOT NULL GROUP BY cognito_sub HAVING COUNT(*) > 1;

-- C3: Check for non-cognito auth_provider (legacy local-auth rows, if any remain)
SELECT id, email, auth_provider FROM users WHERE auth_provider != 'cognito';
```

All three should return zero rows. If not, run `scripts/migrate_local_users_to_cognito.py --report` to decide how to resolve them (see step 1 above).

## 4b. Database snapshot (optional but recommended)

Before applying migrations, take a snapshot of your PostgreSQL database for emergency rollback:

```powershell
# Example using pg_dump (adjust connection string for your environment)
$DbUrl = Get-Content backend/.env | Select-String "DATABASE_URL" | ForEach-Object { $_.Line.Split("=")[1] }
pg_dump $DbUrl > "cognito-cutover-backup-$(Get-Date -Format 'yyyy-MM-dd-HHmm').sql"
```

Store this safely. If a migration fails or causes corruption, this dump lets you restore to the pre-migration state without re-deploying infrastructure.

## 4c. Rollback table (for deferred admin deletes)

Migration `0035` creates the `pending_cognito_deletions` table to hold deferred deletes (cases where `AdminDeleteUser` fails after the local row is already gone). No action needed here — the table is created by the migration — but operators should know it exists so they can check its status after live operations:

```sql
SELECT id, user_id, cognito_sub, attempted_at, retry_count FROM pending_cognito_deletions;
```

If this table ever has rows, run `backend/app/scripts/retry_cognito_deletions.py` (see step 9) to drain it.

## 4d. Smoke tests per step

After each major step (Terraform apply, deploy, migration), run one quick test to confirm the environment is still healthy before moving forward:

```powershell
# After Terraform
terraform -chdir=infra/terraform/foundation show | Select-String "aws_cognito" | Measure-Object

# After deploy (if using containers)
docker compose logs app 2>&1 | tail -20 | Select-String "error|exception"

# After migrations
uv run alembic current
```

No special test, just basic checks that nothing is obviously broken.

## 5. Provision the first admin (fresh environment only)

If this environment already has at least one admin, skip to step 6.

There is no bootstrap script. Create the first admin directly in the pool:

```powershell
$PoolId = terraform -chdir=infra/terraform/foundation output -raw cognito_user_pool_id

aws cognito-idp admin-create-user `
  --user-pool-id $PoolId `
  --username "admin@example.com" `
  --desired-delivery-mediums EMAIL

aws cognito-idp admin-add-user-to-group `
  --user-pool-id $PoolId `
  --username "admin@example.com" `
  --group-name "flowin-admins"
```

The recipient signs in, completes `NEW_PASSWORD_REQUIRED`, and their local
`users` row is created automatically on that first successful sign-in
(`backend/app/core/provisioning.py`). Full detail and every other recovery
scenario is in `docs/runbooks/admin-recovery.md`.

## 6. MFA sequencing (before flipping `admin_mfa_required = true`)

If you deferred `admin_mfa_required` to `false` in step 2 because admins had
not yet enrolled, this is the point to close that gap:

1. Every existing admin enrolls a TOTP factor through the app
   (`POST /api/auth/mfa/totp/associate` → `/mfa/totp/verify`, or the
   frontend's MFA settings) and signs in again through a **completed**
   challenge — enrollment alone does not satisfy the session-bound gate
   (`core/identity.py::enforce_admin_mfa` checks the token's `iat` against a
   stamp set only by a completed MFA challenge).
2. Confirm every admin shows a confirmed factor:

   ```powershell
   aws cognito-idp admin-get-user --user-pool-id $PoolId --username "admin@example.com"
   ```

   and check `UserMFASettingList` is non-empty (AWS only populates it after a
   completed `SetUserMFAPreference` call, not merely `AssociateSoftwareToken`
   — see `backend/app/core/cognito.py`'s notes on this same quirk).
3. Only then set `admin_mfa_required = true` in `<env>.tfvars` (or leave the
   Phase 4 default in place if this is a fresh environment where every admin
   enrolled during step 5) and re-apply.

## 7. Verify: login and entitlements

Verify an admin can log in with a completed MFA challenge and reach an admin
route, and that a non-admin, console-created user can log in and land at the
tier their group implies. There is no automated end-to-end script for this
step in-repo; it is a manual pass against the deployed environment's real
login flow.

## 8. Verify: DB/schema/group consistency

From `backend/`:

```powershell
uv run python scripts/verify_cognito_cutover.py --check-pool
```

This is read-only and checks, among others:

- Every `users` row has a non-null `cognito_sub` (C1).
- The `password_hash`/`auth_provider` columns are gone, `cognito_sub` is
  `NOT NULL`, `status` exists (C2).
- The applied Alembic head matches what this codebase expects (C3).
- Every tier round-trips through a Cognito group — this is what would have
  caught `hexaware` missing a group before Phase 4 added one (C6).
- Local-store ↔ pool reconciliation, if you passed `--check-pool` (C4/C5).

A clean run prints no failures. Any failure names the exact check and the
data it found — resolve it before treating the environment as cut over.

## 9. Ongoing: drift reconciliation

Once live, drift between the pool and the local `users` table can still
happen (an admin disabled or deleted directly in the AWS console, for
example).

A user disabled or deleted directly in the Cognito console may keep using an
unexpired access token for up to the access-token lifetime (30 minutes); the
daily reconciliation marks such users disabled. Disable via the admin panel to
revoke immediately — that path advances `tokens_valid_from` and clears the
stored refresh token in the same transaction, so the next request with the old
token is rejected.

The `Cognito Reconcile` GitHub Actions workflow
(`.github/workflows/cognito-reconcile.yml`) runs `report` mode daily at 03:00
UTC across dev/stage/prod and fails the job on drift. To check a single
environment on demand, run it manually, or from a shell on the box:

```powershell
docker compose exec backend python -m app.scripts.reconcile_cognito_users --report
```

`--fix-disabled` additionally disables local rows Cognito confirms are gone
or disabled — it never re-enables, never deletes, and never creates a row
(see that script's module docstring for why each of those would be an
authority inversion). A pool user with no local row is reported but is not a
failure: just-in-time provisioning creates it on that user's first sign-in.

If an `AdminDeleteUser` call ever fails after the corresponding local delete
already committed (see `backend/app/core/cognito_admin.py::delete_user`'s
docstring for why that ordering is safe), it lands in
`pending_cognito_deletions` and needs the separate retry script:

```powershell
docker compose exec backend python -m app.scripts.retry_cognito_deletions --report
docker compose exec backend python -m app.scripts.retry_cognito_deletions --apply
```

## Related

- `docs/runbooks/admin-recovery.md` — every recovery scenario (lost MFA
  device, locked-out admin, compromised credential, last-admin protection).
- `.planning/COGNITO-MIGRATION-PLAN.md` — Amendment A1 for the full decision
  history behind why this runbook looks the way it does.
- `infra/COGNITO-CUTOVER-RUNBOOK.md` — the superseded dual-accept procedure,
  retained as a historical record only; do not follow it.
- `backend/scripts/verify_cognito_cutover.py`,
  `backend/scripts/migrate_local_users_to_cognito.py`,
  `backend/app/scripts/reconcile_cognito_users.py`,
  `backend/app/scripts/retry_cognito_deletions.py` — the four scripts this
  runbook drives; each has a fuller module docstring than this summary.

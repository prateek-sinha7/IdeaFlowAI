# Admin recovery (Cognito-native)

> Operational procedures for recovering locked-out, compromised, or missing admin accounts when Cognito is the sole authentication authority. There is no local-password admin, no break-glass account, and no code-level bypass of any kind left in this application. Every recovery path below goes through AWS Cognito itself, using an operator's own AWS IAM credentials — never the application.

## When to use this

Use this runbook when:

- The last admin account is locked out (lost MFA device, disabled by mistake,
  forgotten password) and nobody can reach `/api/admin/*`.
- A fresh environment has just been provisioned and has **no** admin yet.
- An admin's Cognito credentials are compromised and need to be revoked
  immediately.

You need an AWS IAM principal with `cognito-idp:Admin*` permissions against
the target user pool (console access, or CLI credentials via SSO/role
assumption). This is intentionally **not** the same IAM identity the running
application uses (`infra/terraform/policies/cognito-admin.json`, scoped to the
EC2 instance role) — recovery must not depend on the application being
healthy, reachable, or even deployed.

## Accepted residual risk

This is a deliberate design choice, recorded in
`.planning/COGNITO-MIGRATION-PLAN.md` Amendment A1: recovery when the
application (or the operator's access to it) is unavailable now depends
entirely on someone holding AWS IAM access to the pool. No local credential,
static token, or in-application bypass replaces the old break-glass admin.
If your organization's IAM access itself becomes unavailable, this runbook
cannot help — that is out of scope for an application-level recovery
procedure and belongs to your AWS account's own break-glass IAM plan.

## Prerequisites

- AWS CLI configured with a principal that can call `cognito-idp:Admin*`
  against the pool (or console access to Amazon Cognito).
- The target user pool ID. Read it from Terraform:

  ```powershell
  terraform -chdir=infra/terraform/foundation output -raw cognito_user_pool_id
  ```

- The recovery target's email address (Cognito's `Username` for this pool,
  since `username_attributes = ["email"]`).

Every command below can equally be done from the AWS Console
(Cognito → User pools → *pool* → Users), if that is more convenient for a
single one-off action. The CLI form is given so the exact operation is
unambiguous and repeatable.

## 1. Provision the very first admin in a fresh environment

There is no bootstrap script. Just-in-time provisioning
(`backend/app/core/provisioning.py`) creates the local `users` row
automatically on that person's first successful sign-in — you only need to
create the pool user and put them in the admins group:

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

The invitation email carries a temporary password. The recipient signs in,
completes `NEW_PASSWORD_REQUIRED` (the app's normal login-challenge flow
handles this — no special endpoint needed), and their local row is created
with `is_admin = true` on that first successful sign-in.

If `ADMIN_MFA_REQUIRED` is `true` in this environment (the default as of
Phase 4 — see `infra/terraform/foundation/variables.tf`), the new admin must
also enroll a TOTP factor (`POST /api/auth/mfa/totp/associate` +
`/mfa/totp/verify` in the app, or via the frontend's MFA settings) and sign in
**again** through a completed MFA challenge before `/api/admin/*` routes
accept their token — `core/identity.py::enforce_admin_mfa` is session-bound
and does not consider enrollment alone sufficient (see that function's
docstring). Plan for two logins, not one.

## 2. Recover a locked-out admin (lost MFA device)

Clearing the MFA preference does not require the user's device — it is an
admin-side (IAM-side) API call:

```powershell
aws cognito-idp admin-set-user-mfa-preference `
  --user-pool-id $PoolId `
  --username "admin@example.com" `
  --software-token-mfa-settings Enabled=false,PreferredMfa=false
```

The user can then sign in without a TOTP code and re-enroll a new device
through the app's normal enrollment flow
(`POST /api/auth/mfa/totp/associate` → `/mfa/totp/verify`).

If `ADMIN_MFA_REQUIRED` is `true`, they will not be able to reach
`/api/admin/*` again until they complete that re-enrollment **and** sign in
through a completed challenge afterward (same session-bound gate as above).

## 3. Reset a forgotten password

```powershell
aws cognito-idp admin-set-user-password `
  --user-pool-id $PoolId `
  --username "admin@example.com" `
  --password "<temporary-password-you-hand-to-them-out-of-band>" `
  --no-permanent
```

`--no-permanent` forces `NEW_PASSWORD_REQUIRED` on next sign-in, so the
temporary value you just set is never the password they actually end up
using — the same invitation-only principle Decision 6 applies to admin
*creation* (`backend/app/core/cognito_admin.py::invite_user`) applies here to
recovery too. Never pass `--permanent`: that would leave a known credential
live on the account indefinitely.

## 4. An admin account was disabled by mistake

```powershell
aws cognito-idp admin-enable-user `
  --user-pool-id $PoolId `
  --username "admin@example.com"
```

This reverses the Cognito-side half of `disable_user` only. It does **not**
restore locally-revoked API keys or the stored encrypted refresh token — see
`backend/app/core/cognito_admin.py::enable_user`'s docstring for why
(re-enabling a login is not consent to un-revoke a credential). Re-run
`app/scripts/reconcile_cognito_users.py --report` afterward (§5) to confirm
the local `users.status` projection catches up; it does so automatically on
that admin's next sign-in via `resolve_principal`, or immediately if you run
the reconciler.

## 5. Revoke a compromised admin's access immediately

```powershell
aws cognito-idp admin-user-global-sign-out --user-pool-id $PoolId --username "admin@example.com"
aws cognito-idp admin-disable-user          --user-pool-id $PoolId --username "admin@example.com"
```

Global sign-out revokes every outstanding refresh token; disable additionally
revokes access tokens and blocks all future sign-in — the same two-call
ordering `core/cognito_admin.py::disable_user` uses, done directly against
the pool. Existing access tokens the attacker already holds remain
offline-verifiable until their own `exp` (typically short-lived; see the app
client's `access_token_validity_minutes` in
`infra/terraform/modules/cognito/main.tf`) — there is no server-side
revocation of an already-issued access token in Cognito, which is why the
disable step matters: it stops anything *new* from being minted while the
old one expires on its own.

If you also need the *local* side revoked immediately (rather than waiting
for their next request to hit `resolve_principal` and re-check pool state),
run:

```powershell
docker compose exec backend python -m app.scripts.reconcile_cognito_users --fix-disabled
```

from a shell on the deployed box (SSM Session Manager, or the same
`.github/actions/ssm-run` path `cognito-reconcile.yml` uses). This sets
`users.status = 'disabled'` locally, advances `tokens_valid_from`, and clears
the stored encrypted refresh token in one transaction — see that script's
module docstring for the full drift-class rationale.

## 6. Refusing to leave zero admins

The application itself refuses to demote or delete the last admin
(`backend/app/core/cognito_admin.py::is_last_admin`, enforced at the
`api/admin.py` route layer with a `409`). This runbook has no equivalent
guard — the AWS CLI/console will happily let you remove the last member of
`flowin-admins`. Before removing an admin from the group or deleting their
pool user, check membership first:

```powershell
aws cognito-idp list-users-in-group --user-pool-id $PoolId --group-name "flowin-admins"
```

If that returns exactly one user and it is the one you are about to act on,
provision a second admin first (§1) before proceeding — otherwise you will
need to repeat §1 from an empty admins group, which still works (JIT
provisioning does not require an existing admin to bootstrap the first one)
but costs you an avoidable round trip.

## Related

- `docs/runbooks/cognito-cutover.md` — the pre-flight and go-live checklist
  for cutting an environment over to Cognito in the first place.
- `backend/app/core/cognito_admin.py` — the lifecycle service the
  application's own `/api/admin/*` routes call; read its module docstring for
  the ordering invariants every write here should also respect when done by
  hand.
- `backend/app/scripts/reconcile_cognito_users.py` — the ongoing drift
  reconciler between the pool and the local `users` table.
- `backend/app/scripts/retry_cognito_deletions.py` — retries a delete whose
  final `AdminDeleteUser` call failed after the local row was already gone;
  not a recovery tool, but the other script that talks to
  `pending_cognito_deletions`, which an operator investigating a
  half-finished delete during a recovery incident may also need.


## Approval and Audit Template

Record each recovery action with this template for compliance and incident tracking:

```
Ticket:         [Jira/GH issue or incident ID]
Environment:    [dev/staging/prod]
Scenario:       [section #: Provision / Locked-out / Password reset / Disabled / Compromised]
Operator:       [AWS IAM principal name or user]
Approver:       [who authorized this recovery, if required by your org]
Date/Time:      [UTC timestamp]

Actions taken:
  aws cognito-idp [command] ...
  [copy exact CLI output or console steps]
  [if multiple commands, list in order]

Verification:
  - Confirmed outcome: [user can/cannot sign in, group membership verified, etc.]
  - Local row reconciled: [yes/no; if no, note when reconcile_cognito_users.py was run]

CloudTrail events to review:
  - cognito-idp:AdminSetUserPassword
  - cognito-idp:AdminDisableUser
  - cognito-idp:AdminEnableUser
  - cognito-idp:AdminUserGlobalSignOut
  - cognito-idp:AdminAddUserToGroup
  - cognito-idp:AdminRemoveUserFromGroup

Verified by:    [reviewer who confirmed the recovery succeeded]
```

Store each recovery record in your incident/audit log. CloudTrail events are automatically logged to the account's trail and can be queried by date, API, and user pool ID.

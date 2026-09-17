# Operator checklist — dev → stage → prod rollout

> Pre-flight and environment-specific checklist for provisioning Cognito authentication in each environment (dev, stage, prod), in that order. Each environment must complete and verify before the next one starts — this is not a big-bang cutover.
> For the detailed procedure behind each step, see
> `docs/runbooks/cognito-cutover.md`. For the underlying model, see
> `docs/architecture/authentication-and-authorization.md`.

## Before any environment

- [ ] Confirm the branch is merged (or the relevant commits are present):
      all Cognito-only auth changes should be in place.
- [ ] Confirm `backend/tests/ci/test_auth_algorithm_verification.py` and
      `backend/tests/unit/test_entitlement_authority.py` are green in CI —
      these are the two regression guards for "Cognito is unconditionally
      the sole authority" and "the DB projection alone cannot grant".
- [ ] Review `docs/architecture/authentication-and-authorization.md` and
      `docs/runbooks/admin-recovery.md` to understand the design and recovery
      paths before proceeding with provisioning.

## Per-environment steps (repeat for dev, then stage, then prod)

### 1. Pre-flight

- [ ] Run `scripts/migrate_local_users_to_cognito.py --report` against this
      environment's database. If it lists any row, resolve with `--link`
      then `--invite` **before** proceeding — migration `0038`'s pre-flight
      will abort the deploy otherwise, loudly and by design.
- [ ] For `prod` specifically: confirm this is genuinely the environment
      the prior two environments already validated. Do not skip dev/stage.

### 2. Terraform

- [ ] `terraform fmt -check -recursive` and `terraform validate` clean in
      `infra/terraform/foundation`.
- [ ] `terraform plan` against this environment's `<env>.tfvars`. Expect:
  - `cognito_enabled` cannot be set to `false` — the variable's own
    `validation` block rejects it. If your `<env>.tfvars` still has
    `auth_provider`, `auth_allow_legacy_jwt`, or `break_glass_enabled`
    lines, delete them; those variables no longer exist and the plan will
    fail with an unknown-variable error otherwise.
  - `admin_mfa_required` defaults to `true` as of Phase 4. If this
    environment's admins have **not yet** enrolled MFA, set
    `admin_mfa_required = false` explicitly in this environment's tfvars
    for now — see step 5 below before turning it on.
  - A new `flowin-tier-hexaware` Cognito group (precedence 15) if this is
    the first apply for this environment since Phase 4.
- [ ] Apply. Confirm the pool, app client, and five groups exist as
      expected (`aws cognito-idp describe-user-pool` /
      `list-groups`), matching `docs/architecture/authentication-and-authorization.md`'s
      table.

### 3. Deploy

- [ ] Run this environment's `deploy.yml` (or equivalent) as usual.
- [ ] Confirm `COGNITO_USER_POOL_ID` / `COGNITO_CLIENT_ID` /
      `COGNITO_CLIENT_SECRET` / `COGNITO_REGION` are present in this
      environment's SSM tree — either Terraform-owned (the default) or
      pipeline-owned, per `docs/GITHUB_CICD_SETUP.md` §3.2.1. Missing any
      one of the three required values crashes the container at boot
      (`_validate_cognito_config`) — that is the intended fail-fast, not a
      surprise.

### 4. Migrations

- [ ] `alembic upgrade head` completes without the pre-flight abort. If it
      *does* abort, this is not a bug — it means step 1 was skipped or
      incomplete. Go back to step 1.
- [ ] `alembic heads` prints exactly one revision.

### 5. First admin, and MFA sequencing

- [ ] If this environment already has an admin, skip to verification.
- [ ] Otherwise, provision the first admin directly in the pool per
      `docs/runbooks/cognito-cutover.md` §5 (`AdminCreateUser` +
      `AdminAddUserToGroup(flowin-admins)`).
- [ ] Have every admin enroll a TOTP factor and sign in once through a
      **completed** challenge (enrolling alone does not satisfy the
      session-bound MFA gate). Confirm with
      `aws cognito-idp admin-get-user` that `UserMFASettingList` is
      non-empty for each.
- [ ] Only then set `admin_mfa_required = true` (or leave Phase 4's shipped
      default in place, if every admin enrolled during this same rollout)
      and re-apply Terraform if you had deferred it in step 2.

### 6. Verify

- [ ] An admin can log in with a completed MFA challenge and reach an admin
      route.
- [ ] A non-admin user created directly in the Cognito console (not through
      the admin panel) can log in on first attempt and lands at the tier
      their group implies — no manual local-row seeding.
- [ ] `scripts/verify_cognito_cutover.py --check-pool` reports no failures.
- [ ] The admin panel's disable/enable buttons work against a disposable
      test account (create, disable, confirm login is rejected, enable,
      confirm login works again, delete).
- [ ] `docs/runbooks/admin-recovery.md`'s procedures are actually exercisable
      by whoever holds on-call for this environment — at minimum, confirm
      they have the IAM access the runbook assumes, before you need it at
      2 a.m.

### 7. Ongoing (leave running, don't just check once)

- [ ] Confirm `Cognito Reconcile`
      (`.github/workflows/cognito-reconcile.yml`) is running on its daily
      schedule (03:00 UTC, `report` mode, all three environments) and that
      failures reach someone. A scheduled run FAILS the job when the report
      contains drift, so a red run is the alarm — it is only useful if somebody
      is notified of it. `fix-disabled` stays a deliberate, reviewed, manual
      action — it is unreachable from the schedule.
- [ ] Confirm the second scheduled job, `Retry Cognito Deletions`, is also
      green. It drains `pending_cognito_deletions` with `--max-attempts 3`;
      rows that exhaust their attempts are left for operator review rather
      than retried forever.
- [ ] If any `AdminDeleteUser` call has ever failed silently, confirm
      `pending_cognito_deletions` is empty (or being drained by
      `scripts/retry_cognito_deletions.py`) before considering this
      environment "steady state".

## Rollback

There is no supported downgrade path past migration `0038` in an
environment that has taken any Cognito-only login — its `downgrade()`
restores column shape only, not password data, and doing so would corrupt
every row (`0038`'s own docstring). If a rollout to an environment needs to
be reversed, that is an application-code rollback to the pre-Phase-1 commit
on a **fresh** database, not a `terraform destroy` + `alembic downgrade` on
the one you just cut over. Treat this as a one-way door per environment, and
do not start `prod` until `stage` has run clean for a real observation
window.

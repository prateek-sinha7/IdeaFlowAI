# ARCHIVED � DO NOT USE FOR IMPLEMENTATION

This document describes the retired dual-provider (local + Cognito) design, including break-glass and bootstrap-admin, all of which were removed. Current design: docs/architecture/authentication-and-authorization.md. Current operations: docs/runbooks/.

---
# Cognito cutover runbook — SUPERSEDED

> **Superseded on 2026-09-12 by `docs/runbooks/cognito-cutover.md` and
> `docs/runbooks/admin-recovery.md`** (Phase 4 deliverables of the Cognito-only
> brief, `.kiro/specs/login/`). Decision 12 of `.planning/COGNITO-MIGRATION-PLAN.md`
> (permanent break-glass local admin) is **revoked** — step 6 below
> ("Create the break-glass admin") **no longer applies** and must not be run.
> The body of this file is retained unedited below as a historical record of
> the dual-accept cutover procedure this repo used before the Cognito-only
> cutover; it is not a current operational document.

---

## Starting state carried into the Phase 4 runbook

The facts below, from this file's "Status: dev" section as of 2026-08-06, are
the actual precondition the new `docs/runbooks/cognito-cutover.md` picks up
from — they are not re-verified here, only carried forward:

- **User pool live:** `velocityai-dev-users` — `eu-central-1_1NiEjdyko` (dev only).
- **App client live:** `velocityai-dev-backend` (confidential, secret generated),
  `ADMIN_USER_PASSWORD_AUTH` + `REFRESH_TOKEN_AUTH` only, token revocation on,
  `prevent_user_existence_errors = ENABLED`, access token 60 min, refresh 7 days,
  pool tier `ESSENTIALS`, MFA `OPTIONAL` + TOTP, min password 12,
  `allow_admin_create_user_only = true`.
- **Groups live:** all 4 original groups with correct precedences
  (`flowin-admins` 0, `flowin-tier-enterprise` 10, `flowin-tier-pro` 20,
  `flowin-tier-basic` 30) — `flowin-tier-hexaware` (15) is **not yet created**
  and is new work for Phase 4 of the Cognito-only brief.
- **IAM live:** `velocityai-dev-cognito-admin`, scoped to the one pool ARN —
  action list needs extending per the new brief (Phase 3: `AdminDisableUser`,
  `AdminEnableUser`, `ListUsers`, `ListUsersInGroup`, etc.).
- **SSM live:** 4 × `COGNITO_*` + `AUTH_PROVIDER` / `AUTH_ALLOW_LEGACY_JWT` /
  `BREAK_GLASS_ENABLED` — the latter three are **removed** per the Cognito-only
  brief (Phase 4); do not carry them into the new runbook.
- **No running EC2 instance exists in the account** — nothing has been deployed
  to cut over yet, in any environment.
- **`AUTH_PROVIDER` is still `local` in SSM** in dev, stage, and prod alike —
  no environment has flipped to Cognito-authoritative.
- **No break-glass admin was ever created** for a real deployment (its alarm
  was never fire-tested) — moot now that Decision 12 is revoked; no break-glass
  admin will be created going forward, in any environment.
- Four `qa-*@flowinqa.com` users exist in the dev pool as test fixtures from
  `seed_test_users.py` — not real accounts, should be deleted or replaced by
  the adapted (Cognito-only) `seed_test_users.py` before the pool is used for
  anything real.

See `.kiro/specs/login/phase0-inventory.md` for the full re-verification this
supersession is based on, and `.planning/COGNITO-MIGRATION-PLAN.md`'s
"Amendment A1" banner for the decision-level record.

---

## Historical body (superseded, do not execute)

Operational procedure for Phase 5 of the Cognito migration
(`.planning/COGNITO-MIGRATION-PLAN.md` §7). Run this **once per environment**,
in order: **dev → stage → prod**. Do not start an environment until the
previous one has completed step 8 and stayed healthy.

Decision 5 (no existing production users) is what makes this a provisioning
exercise rather than a migration campaign: there is no password-reset drive and
no user-migration Lambda. The critical path is the **bootstrap admin** — with
self-registration disabled, it is the only way into a fresh environment.

> **A1:** the "bootstrap admin" critical path described above is obsolete.
> The Cognito-only brief provisions the first admin directly in the pool via
> AWS IAM, and JIT provisioning creates the local row on first login.

---

## Before you start

| Prerequisite | How to confirm |
|---|---|
| Phases 1–4 deployed to this environment | The running image contains `app/core/cognito.py` and `POST /api/auth/refresh` responds (401, not 404) |
| Migrations applied | `uv run alembic current` reports `0032` |
| A password for the break-glass account | Generated and held in your approved secret store — not in git, not in `.tfvars`, not in an SSM `String` |

> **A1:** the break-glass prerequisite row no longer applies — see banner.

**Rollback is available at every step below except step 7.** Steps 1–6 are
additive; the legacy credential path stays fully functional throughout. See
§8 of the migration plan.

---

## Step 1 — Create the pool and deploy dual-accept

`cognito_enabled = true` is already set in
`infra/terraform/foundation/dev.tfvars`, along with the deliberately
conservative cutover switches:

```hcl
cognito_enabled       = true
auth_provider         = "local"   # Cognito EXISTS but is not yet authoritative
auth_allow_legacy_jwt = true      # dual-accept: zero forced logouts
break_glass_enabled   = true
```

> **A1:** `break_glass_enabled` is removed entirely in the Cognito-only brief;
> do not carry it into any new tfvars.

Apply the foundation layer for this environment:

```powershell
./infra/scripts/setup-infra.ps1 -Environments dev -SkipBootstrap -SkipShared
```

Review the plan before typing `yes`. Expect to see created:
`aws_cognito_user_pool`, `aws_cognito_user_pool_client`, 4 ×
`aws_cognito_user_group`, 4 × `aws_ssm_parameter` (`COGNITO_*`), 3 ×
`aws_ssm_parameter` (`AUTH_PROVIDER`, `AUTH_ALLOW_LEGACY_JWT`,
`BREAK_GLASS_ENABLED`), and one `aws_iam_role_policy` (`*-cognito-admin`).

> `auth_provider = "local"` at this step is intentional. It means the pool
> exists and the backend can reach it, but login still uses the local path —
> so a misconfiguration here cannot lock anyone out. You flip it in step 4,
> after the admin has been proven to work.

### Verify the SSM allowlist edit actually took effect

This is the **only** proof that the `bootstrap-ec2.sh` allowlist change worked
(risk R2 — an omitted name is silently dropped, and the app boots without
Cognito config):

```bash
# On the host:
sudo grep -E 'COGNITO_|AUTH_PROVIDER|AUTH_ALLOW_LEGACY_JWT|BREAK_GLASS_ENABLED' \
  /etc/velocityai/app.env
```

You must see all seven names. If any are missing, re-run the host config
reconcile and restart the service — do not proceed.

---

## Step 2 — Bootstrap the admin into the pool

> **A1:** this entire step is obsolete. There is no `bootstrap_admin.py` in
> the Cognito-only brief. An operator with AWS IAM access creates the first
> admin directly in the pool (console or `aws cognito-idp admin-create-user`
> + `admin-add-user-to-group` for `flowin-admins`); the local row is created
> automatically on that admin's first successful login (JIT provisioning,
> D13). See `docs/runbooks/cognito-cutover.md`.

With `AUTH_PROVIDER` still `local`, temporarily point the bootstrap script at
Cognito for this one invocation so it provisions the pool user, adds it to
`flowin-admins`, and writes the local row with `cognito_sub`:

```bash
cd /opt/velocityai   # or wherever the backend runs
AUTH_PROVIDER=cognito \
BOOTSTRAP_ADMIN_EMAIL='admin@yourdomain.com' \
BOOTSTRAP_ADMIN_PASSWORD='<12+ chars, meets the pool policy>' \
  uv run python -m app.scripts.bootstrap_admin
```

The script provisions both stores inside one locked section and
compensating-deletes the pool user if the local commit fails, so a failure
here leaves no half-bootstrapped state.

---

## Step 3 — Prove the Cognito login works

Before making Cognito authoritative, confirm the credential actually works
end to end. Temporarily set `AUTH_PROVIDER=cognito` in `/etc/velocityai/app.env`,
restart, and:

```bash
curl -sS -X POST https://<host>/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@yourdomain.com","password":"<the password>"}'
```

Expect either a `{"token": "...", "user": {...}}` response, or a
`{"challenge": "...", "session": "..."}` if the pool issued a challenge (the
login page handles both). A `503` means the backend cannot reach Cognito —
stop and fix the IAM policy or SSM config before continuing.

**If this fails, revert `AUTH_PROVIDER` to `local` and restart.** You are back
to the pre-migration state with no user impact.

---

## Step 4 — Make Cognito authoritative

> **A1:** in the Cognito-only brief there is no `auth_provider` variable and
> no dual-accept flag — Cognito is mandatory, unconditionally, in every
> environment. This step's "flip a flag" framing does not apply; see the new
> runbook for the actual one-time cutover procedure per environment.

Only after step 3 passes, flip the Terraform variable so the change is durable
and tracked rather than a hand edit on the box:

```hcl
# infra/terraform/foundation/dev.tfvars
auth_provider         = "cognito"
auth_allow_legacy_jwt = true       # STILL true — do not touch this yet
```

Apply the foundation layer, then restart the backend so it re-reads
`/etc/velocityai/app.env`.

Legacy HS256 tokens are still accepted at this point, so nobody holding a
valid session is logged out.

---

## Step 5 — Provision the real users

Through the normal admin API, which writes to both stores in lockstep:

```bash
curl -sS -X POST https://<host>/api/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@yourdomain.com","password":"<pool-policy-compliant>","tier":"pro","is_admin":false}'
```

> **A1:** admin `create_user` no longer accepts an admin-supplied password
> (D15, invitation-based create) — this `curl` body is stale; see the new
> runbook and the updated admin API contract.

For dev/test QA accounts, use the seed script instead — it now provisions
through the same Cognito path rather than writing `password_hash` directly:

```bash
cd backend
AUTH_PROVIDER=cognito E2E_BASE_PASSWORD='<pool-policy-compliant>' \
  uv run python scripts/seed_test_users.py
```

---

## Step 6 — Create the break-glass admin

> **A1: THIS STEP IS REVOKED. DO NOT RUN IT.** Decision 12 is revoked in full.
> `create_break_glass_admin.py` is deleted from the repository. Recovery when
> Cognito is unreachable is AWS-IAM-side and documented in
> `docs/runbooks/admin-recovery.md`. The text below is retained only as a
> historical record of the procedure that used to run here.

Exactly one, documented and alarmed (plan §5.6):

```bash
cd backend
BREAK_GLASS_EMAIL='ops-breakglass@yourdomain.com' \
BREAK_GLASS_PASSWORD='<16+ chars from your secret store>' \
  uv run python scripts/create_break_glass_admin.py
```

The script refuses to create a second local admin. The runtime enforces the
same invariant fail-closed: if more than one local admin ever exists, the
local-admin credential path stops being honoured entirely
(`core/identity.py::_local_admin_credential_is_permitted`).

**Then do the three things the script cannot do for you:**

1. Store the password in the approved secret store.
2. Record the documented owner and rotation cadence.
3. Add a CloudWatch metric filter on the auth log for a break-glass login,
   routed to SNS — **and test that it fires**. An untested alarm is not a
   control.

---

## Step 7 — Verify before the point of no return

```bash
cd backend
uv run python scripts/verify_cognito_cutover.py --check-pool
```

All checks must pass:

| Check | Asserts |
|---|---|
| C1 | Zero `auth_provider='cognito'` rows with a NULL `cognito_sub` (such a user cannot log in at all) |
| C2 | Exactly one local break-glass admin |
| C3 | No Cognito row retains a local `password_hash` (a second credential outside pool policy) |
| C4 | Every local Cognito row maps to a live pool user, with a matching `sub` |
| C5 | Every pool user has a local row (an orphaned pool user authenticates then 401s) |

> **A1:** C2 ("exactly one local break-glass admin") is replaced by "zero local
> admins, zero `password_hash` values anywhere" in the adapted script — see
> the Phase 0 inventory's Resolution section and the new runbook.

The script exits non-zero on any failure, so it can be used directly as a
pipeline gate. **Do not proceed to step 8 until it exits 0.**

---

## Step 8 — Close the dual-accept window

Wait at least `ACCESS_TOKEN_EXPIRE_HOURS` (default 12) after step 4 so every
outstanding legacy token has expired naturally. Then:

```hcl
# infra/terraform/foundation/dev.tfvars
auth_allow_legacy_jwt = false
```

Apply, restart, and re-run the verification script.

### What changes at this point

- Legacy HS256 tokens stop being accepted for regular users.
- The break-glass admin **still works** — that path is permanent by design
  (plan §5.6), gated on `BREAK_GLASS_ENABLED` and the single-row invariant.
- Cognito availability is now a hard dependency for **new** logins. In-flight
  sessions survive a Cognito control-plane blip because token validation is
  offline against cached JWKS, but a prolonged outage blocks sign-in. That is
  the accepted cost of a managed identity provider; the break-glass account is
  the mitigation.

> **A1:** "the break-glass admin still works" no longer applies — there is no
> break-glass admin. A prolonged Cognito outage blocks sign-in for everyone;
> the mitigation is AWS-IAM-side recovery, not a local account.

### Rolling back after step 8

Set `auth_allow_legacy_jwt = true` and restart. Note that Cognito-native users
have no local password hash, so full local fallback exists **only** for the
break-glass admin. This is the accepted design, not a gap.

---

## Then repeat for stage, and finally prod

Create the equivalent block in `stage.tfvars` / `prod.tfvars`. For **prod**,
note that the module sets `deletion_protection = "ACTIVE"` automatically, and
consider a longer `cognito_refresh_token_validity_days` than dev's 7.

---

## Phase 6 — hardening, staged after cutover

The code for these is already shipped. Each is **off by default** so nothing
changes until you deliberately enable it — none of this is a prerequisite for
steps 1–8 above.

### 6.1 Admin MFA enforcement

Two factors are available, and the gate accepts **either**:

| Factor | Enrolment | Notes |
|---|---|---|
| Authenticator app (TOTP) | `POST /api/auth/mfa/totp/associate` → `otpauth://` URI for a QR code, then `POST /api/auth/mfa/totp/verify` | No pool change needed; available on any pool with `mfa_configuration != OFF` |
| Email codes (EMAIL_OTP) | `POST /api/auth/mfa/email/enable` — a single toggle, no secret to provision | Requires the pool change in 6.4 below |

Users manage both from **Security** in the account menu, which opens the
**Security** tab of Account Settings on `/dashboard` (there is no longer a
standalone `/settings/security` route).
`GET /api/auth/mfa` reports current state.

Enforcement is separate from availability:

1. Have every admin enrol **first**. Confirm with
   `aws cognito-idp admin-get-user` → `UserMFASettingList` contains
   `SOFTWARE_TOKEN_MFA` or `EMAIL_OTP`.
2. Then set `ADMIN_MFA_REQUIRED=true`.

Enabling it before admins enrol locks them out of admin routes (they can still
sign in and enrol — the gate covers `/api/admin/*`, not login). The break-glass
account is exempt by construction: gating it on a Cognito call would defeat its
only purpose. Watch the `*-auth-admin-mfa-blocked` metric after enabling.

> **A1:** the break-glass exemption sentence above no longer applies (D12
> revoked). D16 requires `MFA_SETUP` enrollment to actually complete
> end-to-end before `admin_mfa_required` is set `true` anywhere — this section
> pre-dates that completion and describes the pool staying `OPTIONAL` with the
> app-layer gate as the only enforcement, which remains correct.

The gate is deliberately factor-agnostic — an admin holding TOTP must not be
locked out because the environment later standardised on email codes.

### 6.2 Threat protection (Essentials → Plus)

An explicit cost/benefit decision, not an oversight. To evaluate:

```hcl
feature_plan           = "PLUS"
threat_protection_mode = "AUDIT"   # log risk assessments, block nobody
```

Run at `AUDIT` first and read the findings before considering `ENFORCED`.

### 6.3 Self-service password reset (SES)

Cognito's built-in sender is rate limited to a level unusable for real reset
volume, so this needs SES:

1. Verify the domain in SES, enable DKIM, configure bounce/complaint handling.
2. Set `ses_source_arn` + `ses_from_email_address` on the cognito module.
3. `POST /api/auth/forgot-password` and `.../confirm` then work. Both always
   return a generic response so the endpoint cannot be used to enumerate
   accounts. Break-glass is excluded — it is administered out-of-band.
4. Add the "Forgot password?" link to the login page (deliberately omitted at
   cutover per Decision 10).

> **A1:** "Break-glass is excluded" no longer applies — there is no break-glass
> account to exclude.

> **Mutually exclusive with email OTP MFA (6.4).** AWS will not let email serve as
> both a second factor and the account-recovery channel. Pick one.

### 6.4 Email OTP as a second factor — **surrenders 6.3**

Requires SES from 6.3 first. Then:

```hcl
cognito_email_mfa_enabled = true
cognito_ses_source_arn    = "arn:aws:ses:eu-central-1:<acct>:identity/<domain>"
```

The module's variable validation refuses the flag without SES, so a
half-configured apply fails rather than silently producing a pool with no email
factor.

**What this changes, deliberately.** AWS rejects `verified_email` as the only
account-recovery mechanism while email MFA is active, and this pool collects no
phone numbers, so the module switches `account_recovery_setting` to `admin_only`.
Self-service password reset stops working:

| Before | After |
|---|---|
| `POST /api/auth/forgot-password` → generic 202 + emailed code | → **409**, "ask an administrator" |
| User resets their own password | Admin resets it via `POST /api/admin/users/{id}/reset-password` |

The backend learns this from `AUTH_EMAIL_MFA_ENABLED`, published to SSM from the
module's **derived** `email_mfa_active` output. Do not hand-edit that parameter to
disagree with the pool — a `true` against a pool without email MFA disables reset
for a factor nobody can use.

Verify after apply:

```bash
aws cognito-idp describe-user-pool --user-pool-id <pool> \
  --query 'UserPool.{mfa:MfaConfiguration,email:EmailMfaConfiguration,recovery:AccountRecoverySetting}'
```

Expect `recovery` to contain `admin_only` and `email` to be present. Then confirm
the host actually received the flag:

```bash
sudo grep AUTH_EMAIL_MFA_ENABLED /etc/velocityai/app.env
```

The admin reset issues a **temporary** password by default, so the user is forced
through `NEW_PASSWORD_REQUIRED` at next sign-in and the admin never holds a live
credential for another account. Pass `permanent: true` only when provisioning on
someone's behalf.

### 6.5 CORS drift — **already fixed**

`main.py` previously hardcoded three localhost origins and ignored
`settings.CORS_ORIGINS` while setting `allow_credentials=True`. Harmless under
bearer tokens, but a hard blocker for cookie/BFF. It now reads `CORS_ORIGINS`
(appending localhost only when `ENV=development`) and refuses to boot if the
list contains `*` alongside credentials.

**Action required:** make sure `CORS_ORIGINS` is set correctly in SSM for each
environment — it is now actually honoured, so a wrong value will surface as
browser CORS failures where it previously (silently) did nothing.

### 6.6 API-key expiry — **already shipped**

New keys get a 90-day `expires_at`; expired keys 401 identically to revoked
ones. Keys minted before migration `0033` have `expires_at = NULL` (never
expire) so no live IDE/MCP integration breaks. Backfilling an expiry onto those
is a deliberate operator decision — they are now visible via
`GET /api/settings/api-keys`.

> **A1:** the new brief's Phase 2 additionally requires fixing
> `mcp.py::_get_user_from_bearer` to enforce this expiry (it currently only
> checks `revoked_at`) — a real gap this section doesn't mention.

### 6.6 Auth observability — **already shipped**

`core/auth_events.py` emits structured JSON auth events; the monitoring module
creates metric filters and alarms:

| Alarm | Fires on | Threshold |
|---|---|---|
| `*-auth-break-glass-login` | Any break-glass login | 1 occurrence |
| `*-auth-break-glass-invariant-violated` | More than one local admin exists | 1 occurrence |
| `*-auth-login-failure-spike` | Sustained login failures | 50 per 5 min, 2 periods |

> **A1:** the first two alarms above are removed entirely (no break-glass
> account, no local-admin invariant to violate). Only the login-failure-spike
> alarm survives into the new runbook.

> **The `AuthEvent` string values are a published interface.** The metric filters
> match on them. Rename one without updating `modules/monitoring` and the alarm
> silently reports no-data — which looks healthy.

**Do step 6 of the cutover properly: actually trigger a break-glass login and
confirm the SNS email arrives.** An untested alarm is not a control.

> **A1:** this instruction is moot — step 6 (create the break-glass admin) is
> revoked; there is nothing to trigger.

### 6.7 Remaining deferred item

**Cookie/BFF session.** Not implemented. The access token still lives in
`localStorage`, so stored XSS can reach it. Mitigated for now by the short
Cognito access-token TTL (60 min) and per-`jti` revocation. Moving to
`HttpOnly` cookies is a genuine architectural change — it breaks the
`getToken()` seam that kept 122 frontend call sites untouched, and it requires
CSRF defence to be designed first. The 6.4 CORS fix was its prerequisite and is
now done; the rest is a separate, scoped piece of work.


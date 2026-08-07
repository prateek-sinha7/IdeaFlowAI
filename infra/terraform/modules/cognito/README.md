# Module: `cognito`

Creates the Amazon Cognito User Pool that becomes the credential + role
authority for VelocityAI/Flowin (see `.planning/COGNITO-MIGRATION-PLAN.md`).
One pool + one confidential app client per environment (Decision 9 — a
separate call to this module per `dev`/`stage`/`prod`).

Invitation-only (`admin_create_user_config.allow_admin_create_user_only =
true`) — self-registration stays disabled, mirroring the existing
application-layer posture. No hosted UI / domain: the backend talks to
Cognito server-side via `AdminInitiateAuth`/`AdminRespondToAuthChallenge`
(Decision 1 — the in-app login form is unchanged). No Identity Pool — no
browser code calls AWS APIs directly, so there is no use case for temporary
AWS credentials in the browser (see the plan's non-goals).

## Resources created

- `aws_cognito_user_pool` — password policy, optional TOTP MFA, invitation-only
  admin-create, `prevent_destroy = true`.
- `aws_cognito_user_pool_client` — confidential client (has a secret),
  `ADMIN_USER_PASSWORD_AUTH` + `REFRESH_TOKEN_AUTH` only, token revocation
  enabled, `prevent_user_existence_errors = ENABLED`.
- `aws_cognito_user_group` × 4 — the fixed precedence table:

  | Group | Precedence | Meaning |
  |---|---|---|
  | `flowin-admins` | 0 | `is_admin = true` |
  | `flowin-tier-enterprise` | 10 | tier `enterprise` |
  | `flowin-tier-pro` | 20 | tier `pro` |
  | `flowin-tier-basic` | 30 | tier `basic` |

  **Do not rename these groups without updating
  `backend/app/core/entitlements.py`'s `resolve_tier_from_groups` /
  `resolve_is_admin_from_groups` in lockstep** — they match on these exact
  literal names.

No IAM role is attached to any group. `cognito:preferred_role` is an Identity
Pool concept this module does not use.

## Usage

```hcl
module "cognito" {
  source = "../../modules/cognito"

  name_prefix = local.name_prefix
  environment = var.environment

  deletion_protection = var.environment == "prod" ? "ACTIVE" : "INACTIVE"
  mfa_configuration   = "OPTIONAL"

  tags = local.tags
}
```

Then feed the outputs into the `secrets` module as `String`/`SecureString`
SSM parameters, and scope an IAM policy on the EC2 instance role to
`module.cognito.user_pool_arn` (see the migration plan §7 Phase 1 for the full
wiring — SSM allowlist edit, IAM actions list, nginx rate-limit zone).

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix (used in tags/names). | `string` | — | yes |
| `environment` | `dev`/`stage`/`prod` (tagging only). | `string` | — | yes |
| `password_minimum_length` | Password policy minimum length. | `number` | `12` | no |
| `password_require_lowercase/_uppercase/_numbers/_symbols` | Password policy character-class requirements. | `bool` | `true` | no |
| `temp_password_validity_days` | Days an admin-set temp password stays valid. | `number` | `7` | no |
| `mfa_configuration` | `OFF`/`OPTIONAL`/`ON`. | `string` | `"OPTIONAL"` | no |
| `access_token_validity_minutes` | Access token TTL. | `number` | `60` | no |
| `id_token_validity_minutes` | ID token TTL. | `number` | `60` | no |
| `refresh_token_validity_days` | Refresh token TTL. | `number` | `30` | no |
| `deletion_protection` | `ACTIVE`/`INACTIVE`. Set `ACTIVE` in prod. | `string` | `"INACTIVE"` | no |
| `group_names` | The four fixed group names (see table above). Change only with a matching backend update. | `object` | see `variables.tf` | no |
| `tags` | Extra tags merged onto every resource. | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| `user_pool_id` | e.g. `eu-central-1_xxxxxxxxx` → `COGNITO_USER_POOL_ID`. |
| `user_pool_arn` | For IAM policy scoping. |
| `user_pool_endpoint` | Issuer host (`iss` claim base) the backend verifies. |
| `client_id` | → `COGNITO_CLIENT_ID`. |
| `client_secret` | **Sensitive.** → `COGNITO_CLIENT_SECRET` (SecureString). |
| `group_names` | Echo of the input, for reference. |

## Phase 6 hardening inputs

| Name | Description | Type | Default |
|------|-------------|------|---------|
| `feature_plan` | `LITE` / `ESSENTIALS` / `PLUS`. Decision 8 chose `ESSENTIALS` (TOTP MFA). `PLUS` additionally unlocks threat protection at a higher per-MAU cost. | `string` | `"ESSENTIALS"` |
| `threat_protection_mode` | `NO_ACTION` / `AUDIT` / `ENFORCED`. Requires `feature_plan = PLUS`; the risk-configuration resource is skipped entirely otherwise. Start at `AUDIT` — it logs risk assessments without blocking anyone. | `string` | `"NO_ACTION"` |
| `ses_source_arn` | ARN of a **verified** SES identity to send pool email from. Empty keeps Cognito's built-in sender, which is rate limited and unsuitable for real password-reset volume. | `string` | `""` |
| `ses_from_email_address` | `From:` address; must belong to the verified identity. Required when `ses_source_arn` is set. | `string` | `""` |
| `ses_reply_to_email_address` | Optional `Reply-To:`. | `string` | `""` |

### On upgrading to PLUS

Worth knowing when this decision is revisited: AWS documents that
compromised-credential checks apply to `ADMIN_USER_PASSWORD_AUTH` but **not** to
SRP. The backend-mediated flow chosen in Decision 1 is therefore compatible with
threat protection — an SRP-based client-side flow would not have been. The
architecture does not block the upgrade; it is purely a cost/benefit call.

### On admin MFA

The pool stays at `mfa_configuration = "OPTIONAL"` even once admins are required
to hold a factor. Cognito has no per-group MFA requirement, and setting the pool
to `ON` would force a factor on every basic-tier user — explicitly not the
cutover decision. The admin requirement is an application gate
(`ADMIN_MFA_REQUIRED` + `core/identity.py::enforce_admin_mfa`), and it is
factor-agnostic: either an authenticator app or email codes satisfies it.

Do not set `mfa_configuration = "ON"` without revisiting the backend. Required
MFA makes Cognito issue an `MFA_SETUP` challenge to any user without a factor,
and completing that needs a three-call session chain
(`AssociateSoftwareToken` → `VerifySoftwareToken` → `RespondToAuthChallenge`)
that `POST /api/auth/login/challenge` deliberately does not implement — it
returns an explanatory 501 instead of a response Cognito would reject.

### On email OTP (`email_mfa_enabled`) — read before enabling

Email codes need no enrolment ceremony: unlike TOTP there is no secret to
provision, because the mailbox is already the pool's verified sign-in identifier.
Enabling the factor for a user is one `SetUserMFAPreference` write
(`POST /api/auth/mfa/email/enable`).

Two prerequisites, both enforced by variable validation:

| Requirement | Why |
|---|---|
| `ses_source_arn` set | Cognito rejects `EmailMfaConfiguration` on a pool using the built-in `COGNITO_DEFAULT` sender, whose rate limit would make the factor unusable anyway |
| `mfa_configuration != "OFF"` | An MFA factor on a pool with MFA off is meaningless |
| Feature plan `ESSENTIALS` or `PLUS` | Email MFA is not available on `LITE` (the module defaults to `ESSENTIALS`) |

**The cost, which is not optional.** AWS forbids email being both a second factor
and the account-recovery channel — `CreateUserPool` rejects `verified_email` as
the only `AccountRecoverySetting` member while `EmailMfaConfiguration` is active,
and even where a mixed setting is accepted AWS documents that email MFA
*disqualifies* email for recovery. The reasoning is sound: one compromised
mailbox would otherwise yield both the second factor and the password-reset
channel, which is not two factors.

This pool collects no phone numbers, so `verified_phone_number` is not an
available fallback. `email_mfa_enabled = true` therefore switches
`account_recovery_setting` to `admin_only`, which **surrenders self-service
password reset**:

- `POST /api/auth/forgot-password` and `/forgot-password/confirm` return 409
  ("ask an administrator") rather than their usual generic 202. That behaviour is
  driven by the backend's `AUTH_EMAIL_MFA_ENABLED`, which the foundation layer
  publishes to SSM from this module's **derived** `email_mfa_active` output — so a
  caller who sets the flag but forgets SES gets `false` and keeps working reset,
  rather than losing reset for a factor that was never configured.
- Resets happen through `POST /api/admin/users/{id}/reset-password`, which issues
  a temporary password by default so the admin never learns a live credential for
  someone else's account.

`auth_session_validity_minutes` defaults to 10 rather than Cognito's 3 because an
emailed code has SES queuing plus inbox delivery ahead of the user's typing, and
an expired code is indistinguishable from a wrong one in the UI.

## Verified behaviour of a real applied pool

Confirmed against the live `velocityai-dev-users` pool. Two things differ from
what a reading of the config might lead you to expect:

### `flowin-admins` ends up with no `precedence`

The module sets `precedence = 0`, but AWS stores the group with precedence
**unset**. `0` is the zero value for the provider's integer field, so it is
indistinguishable from "not configured" and gets dropped.

**This is harmless here, by design.** Nothing in this system resolves authority
by Cognito's precedence ordering: `resolve_is_admin_from_groups` tests
*membership* of `flowin-admins` by name, and `resolve_tier_from_groups` compares
its own precedence table over the three `flowin-tier-*` groups. No IAM role is
attached to any group and `cognito:preferred_role` is not used. The declared
`precedence = 0` is documentation of intent, not a load-bearing value.

If you ever *do* make something depend on Cognito-side precedence for the admins
group, give it a non-zero value (e.g. `1`) — otherwise it will silently not be set.

### The pool's canonical `Username` is a UUID, not the email

Because `username_attributes = ["email"]`, email is a sign-in **alias** and
Cognito generates a UUID as the real `Username` (identical to the `sub` claim).
This matters for `SECRET_HASH`:

| Flow | Hashed against |
|---|---|
| `AdminInitiateAuth` | whatever you pass as `USERNAME` — the email alias works |
| `REFRESH_TOKEN_AUTH` | the **canonical** username the refresh token was issued to |

Passing the email on the refresh flow fails with
`NotAuthorizedException: Unable to verify secret hash for client` — a message
that points at the client secret rather than the username. The backend passes
`users.cognito_sub` for this reason (`core/cognito.py::refresh_auth`), guarded by
`tests/unit/test_cognito_refresh_secret_hash.py`.

## Notes / accepted risk

- The app-client secret is Terraform-generated, so it enters Terraform
  state — same exposure class as the existing `random_password`
  `SECRET_KEY`/DB password, mitigated identically (encrypted S3 backend,
  DynamoDB locking, restricted access).
- No hosted-UI domain is created (no `aws_cognito_user_pool_domain`) —
  intentional per Decision 1.
- `mfa_configuration = "OPTIONAL"` requires the application to provide its
  own enrolment UI (AWS does not provide one without the hosted UI). See the
  migration plan §5.5 for the backend/frontend challenge-handling this
  requires from Phase 3 onward, even while MFA stays optional.

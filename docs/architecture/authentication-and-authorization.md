# Authentication and authorization architecture

> This document describes the authentication, authorization, and admin-lifecycle model as implemented in IdeaFlowAI after the Phase 4 Cognito-only migration. For operational procedures and recovery, see `docs/runbooks/admin-recovery.md` and `docs/runbooks/cognito-cutover.md`. For provisioning infrastructure and secrets, see `infra/COGNITO-CUTOVER-RUNBOOK.md`.

## The model in one paragraph

Amazon Cognito is the sole authentication authority and the sole source of
truth for admin/tier entitlements. There is no password stored anywhere in
this application, no locally-signed token, and no local administrator
account of any kind. The local `users` table holds exactly one thing:
a **mapping** row (`cognito_sub → users.id`) plus an **advisory projection**
of `tier`/`is_admin` that exists only so list/read endpoints don't need an
AWS round-trip per row. Every authorization decision reads the verified
token's `cognito:groups` claim, never the DB projection alone.

## Authentication: verification, not issuance

The backend never mints a token. `POST /api/auth/login` calls Cognito's
`AdminInitiateAuth` and relays the result; every subsequent request carries
the Cognito-issued RS256 access token as a bearer credential.

`core/identity.py::verify_credential()` is the one function that decides
whether a token is real:

- Resolves the signing key from the pool's JWKS by `kid`.
- Verifies the RS256 signature, `iss` (exact match against
  `https://cognito-idp.{region}.amazonaws.com/{pool_id}`), `exp`,
  `token_use == "access"`, and `client_id`.
- There is no fallback path. A token that fails any of the above raises
  `CredentialInvalid` — there is no HS256 branch, no local-admin branch, no
  "if AUTH_ALLOW_LEGACY_JWT" escape hatch. `backend/tests/ci/
  test_auth_algorithm_verification.py::TestNoLocalHs256Fallback` is the
  regression guard that pins this: it forges an HS256 token with the app's
  own `SECRET_KEY` (which still exists — see below — but no longer signs
  anything) and asserts it is rejected.

`SECRET_KEY` is **not** retired. `core/crypto.py` derives a Fernet key from
it (HKDF) to encrypt GitHub PATs and Cognito refresh tokens at rest. It has
not signed a JWT since Phase 1.

## Just-in-time (JIT) provisioning

No user is ever pre-created in the local database by an admin action alone.
`core/provisioning.py` provisions the local row the first time a verified
Cognito identity is seen, from two entry points:

- **Login** (`provision_from_login`): after a successful `AdminInitiateAuth`,
  using the `sub`/`cognito:groups` the login response already carries — no
  extra AWS call.
- **Token verification** (`provision_from_token_sub`): when a verified
  access token's `sub` has no matching local row (e.g. a user created
  directly in the Cognito console who has never called `/login` through this
  backend, or a token presented to a non-login endpoint first). Calls
  `AdminGetUser(Username=sub)` — Cognito accepts `sub` as `Username` on this
  email-username pool, proven by
  `tests/unit/test_jit_provisioning.py::TestResolvePrincipalJit`.

Both paths are **race-safe via the database, not a lock**: `cognito_sub`
carries a unique constraint (migration 0031/0038), so two concurrent
first-sign-in requests for the same new identity can both attempt an insert;
the loser catches the `IntegrityError` and re-reads the winner's row instead
of raising or duplicating (`provisioning.py::_insert_user`).

**Email collision, not linking.** Decision 4a's original design ("link a row
with `cognito_sub IS NULL`") is unreachable by construction: migration 0038
made `cognito_sub` `NOT NULL`, so no such row can exist post-cutover. What
JIT provisioning actually guards against is a *different* email collision —
an existing local row holding the same email but a **different**
`cognito_sub` (an operator deleted and recreated a pool user, minting a new
`sub`). Re-pointing that row would be an account-takeover primitive, so
`_link_or_refuse` fails closed with `ProvisioningRefused`, surfaced to the
caller as a generic 401. `scripts/reconcile_cognito_users.py --report` is
how an operator finds and deliberately resolves the collision.

A disabled pool user is never provisioned: Cognito itself refuses to
authenticate a disabled user, so a successful `AdminInitiateAuth` result is
already proof of `Enabled = true` — no separate check is needed on that
path. The token-verification path checks `status == 'active'` on whatever
local row it finds, disabled or not.

### Refusal cache (60-second negative cache)

When `provision_from_token_sub` encounters a disabled or missing pool user,
it caches the refusal for 60 seconds to avoid repeated Cognito calls on the
hot path. Without this cache, a holder of a valid-but-unprovisionable token
(deleted or disabled pool user, network failure) would incur an `AdminGetUser`
call on every request — both a cost and a throttling surface an
unauthenticated-ish caller controls. The cache is checked before any Cognito
call; on expiry, the next request queries again.

## Entitlement authority: groups, not columns

`core/identity.py::effective_tier()` / `effective_is_admin()` read
`principal.groups` (the verified token's `cognito:groups` claim) exclusively.
The `users.tier`/`users.is_admin` DB columns are refreshed on login and on
any authenticated request whose token `iat` is newer than
`roles_synced_at` (`refresh_projection_if_stale`), but they are **never**
consulted by a gate directly.

`backend/tests/unit/test_entitlement_authority.py::TestProjectionCannotGrant`
is the test that proves this rather than assumes it: it deliberately makes
the DB column and the token's groups disagree (enterprise column + basic
groups; basic column + enterprise groups) and asserts the token wins both
times.

`entitlements.py` owns the one Cognito-group-name-to-tier/role mapping table
(`_TIER_GROUP_PRECEDENCE`), used by both the read side
(`resolve_tier_from_groups`) and the write side (`group_for_tier`) so the
names can never drift into two disagreeing copies:

| Group | Tier / role | Precedence |
|---|---|---|
| `flowin-admins` | admin | 0 |
| `flowin-tier-enterprise` | enterprise | 10 |
| `flowin-tier-hexaware` | hexaware | 15 |
| `flowin-tier-pro` | pro | 20 |
| `flowin-tier-basic` | basic | 30 |

Lower precedence wins when a token carries more than one tier group. No
matching group resolves to `basic` (fail-closed, never fail-open to a higher
tier).

## Admin lifecycle: fail-closed ordering

`core/cognito_admin.py` is the one module every Cognito Admin* write in the
admin lifecycle goes through — `api/admin.py`'s route handlers are thin
callers that parse the request, delegate the ordering decision, and shape
the response. The invariants it enforces:

- **Revoke-before-mutate.** Every privilege change or account-ending action
  advances `tokens_valid_from` and commits it **before** the corresponding
  Cognito call, so a token minted under the old privilege is rejected from
  the instant the decision is made — regardless of whether the Cognito call
  that enacts it succeeds, retries, or ultimately fails.
- **Invitation-only create.** `AdminCreateUser(..., DesiredDeliveryMediums=
  [EMAIL])` with a Cognito-generated temporary password. This backend never
  sees or stores it; the admin never learns it. The request schema has no
  password field at all (`extra=forbid`), so a client that still tries to
  send one gets a 422, not a silently-ignored value.
- **Disable-before-delete.** A pool user is never deleted while still
  enabled: `AdminUserGlobalSignOut → AdminDisableUser` runs first, so a slow
  or failing `AdminDeleteUser` cannot leave an enabled pool user pointing at
  an already-deleted local row.
- **`UserNotFoundException` is success**, not failure, on every
  delete-shaped operation — a partial prior run may have already removed the
  pool user, and re-running the operation must converge rather than raise.
- **Compensating delete on create failure.** If the local-row insert fails
  after the pool user was already created, `try_delete_pool_user` removes
  the orphan rather than leaving a Cognito identity with no matching local
  row. Proven by `tests/integration/test_admin_authorization_matrix.py::
  TestCreateUserInvitationOnly::test_compensating_delete_fires_when_the_local_insert_fails`
  (Phase 6).
- **Deferred delete via a durable retry queue.** If the final
  `AdminDeleteUser` call fails (network/throttle) after the local delete and
  the disable/sign-out steps already succeeded, a `PendingCognitoDeletion`
  row records it. The account is already disabled and gone locally — safe to
  defer. `scripts/retry_cognito_deletions.py` drains this table.
- **Last-admin protection.** Every action that could remove the final
  administrator (`role` change, `disable`, `delete`) checks
  `cognito_admin.is_last_admin` first — a **live** `ListUsersInGroup` read,
  not the local `is_admin` projection, because the projection can under-count
  relative to the pool's real membership. Refused with `409`.

## Disable vs. delete

Disable is reversible; delete is not. Disabling revokes the account's API
keys and stored refresh token, disables sign-in at Cognito, and globally
signs out every existing session — but leaves the local row and Cognito
identity intact for `enable` to reverse. Re-enabling does **not** restore
the revoked API keys or refresh token: re-enabling a login is not consent to
un-revoke a credential, so the user re-authenticates and mints a fresh key
if they still need IDE/MCP access.

## Multi-factor authentication (MFA)

Enrollment is enabled for admins by default (`ADMIN_MFA_REQUIRED = true`).
Two endpoints handle TOTP enrollment:

- `POST /api/auth/mfa/totp/associate` (requires `get_current_user` only):
  Calls Cognito's `AssociateSoftwareToken`, returns `secret_code` and
  `otpauth_uri` for QR-code display.
- `POST /api/auth/mfa/totp/verify` (requires `get_current_user` only):
  Calls Cognito's `VerifySoftwareToken` then `SetUserMfaPreference` to
  enable the factor.

Verification happens via the normal `SOFTWARE_TOKEN_MFA` challenge flow
during `POST /api/auth/login/challenge`. The enforcement is **session-bound**
(`core/identity.py::enforce_admin_mfa` checks the token's `iat` against
`mfa_verified_at`) — completing MFA enrollment alone does not satisfy the
gate; each admin must sign in once through a completed MFA challenge to prove
they held the device at that moment.

## Failure semantics at a glance

| Situation | What happens |
|---|---|
| Cognito unreachable during login | 503/generic error; no local fallback exists to catch the user |
| Cognito unreachable during an admin write | The commit-before-mutate step already landed (revocation), the Cognito call is retried/reported per the ordering above |
| A verified token's `sub` has no local row | JIT-provisioned on the spot from `AdminGetUser` + groups |
| A verified token's `sub` maps to a `status='disabled'` row | Rejected regardless of token validity |
| Admin tries to demote/disable/delete the last admin | 409, nothing touched |
| `AdminDeleteUser` fails after the local delete already committed | `pending_cognito_deletions` row created; retried later; user already gone locally either way |
| Local row's email collides with a different pool `sub` | `ProvisioningRefused` → generic 401; requires an operator to resolve via `reconcile_cognito_users.py` |

## Residual risk and accepted limitations

**Token revocation lag.** A user disabled or deleted directly in the Cognito
console may keep using an unexpired access token for up to the access-token
lifetime (30 minutes); the daily reconciliation marks such users disabled.
Disable via the admin panel to revoke immediately — that path advances
`tokens_valid_from` and clears the stored refresh token in the same
transaction, so the next request with the old token is rejected.

**Cognito outage = auth outage.** There is no local password, static token, or
in-application bypass. If Cognito becomes unreachable and stays that way, the
application cannot authenticate new users or issue new tokens — only already-held
valid tokens continue to work until they expire. This is an intentional design
choice: a local fallback would mean two independent, possibly-divergent
sources of truth for entitlements, which creates correctness bugs (a disabled
user re-enabled locally but not in Cognito, or vice versa) that are both
silent and difficult to debug after the fact. Recovery when Cognito *itself*
is unavailable is an AWS-IAM-side operator action against the pool directly —
see `docs/runbooks/admin-recovery.md` — not an application-level feature.

**No break-glass admin, no local credentials.** There is no break-glass account,
no application-level admin login, and no hardcoded static token. The "last resort"
when everything has failed is AWS console access — an operator with `cognito-idp:Admin*`
IAM permissions against the pool can reset passwords, clear MFA, and add/remove
group membership directly from the AWS console, regardless of app state. If your
organization's IAM access itself becomes unavailable, this is out of scope for
an application-level recovery procedure and belongs in your AWS account's own
break-glass IAM plan.

## What does NOT exist any more

There is no break-glass local admin, no `BREAK_GLASS_ENABLED` flag, no
`AUTH_PROVIDER`/`AUTH_ALLOW_LEGACY_JWT` dual-accept window, no
`password_hash` column, no `bcrypt`/`passlib` dependency, and no
`bootstrap_admin.py`/`recover_admin.py` scripts. Every recovery path goes
through AWS and your own IAM credentials — never through the application.

## Related documentation

- `docs/runbooks/admin-recovery.md` — step-by-step recovery procedures using
  AWS IAM and the Cognito console (lost MFA, forgotten password, compromised
  account, provisioning the first admin).
- `docs/runbooks/cognito-cutover.md` — provisioning a new environment or
  updating an existing one to align with Cognito-only state.
- `backend/app/core/identity.py` — token verification, principal resolution,
  and authorization gates (read the function docstrings).
- `backend/app/core/provisioning.py` — JIT provisioning and email collision
  detection (read the module docstring for the fail-closed principles).
- `backend/app/core/cognito_admin.py` — admin lifecycle ordering (read the
  module docstring for the invariants every operation enforces).
- `backend/app/core/entitlements.py` — tier/role mapping and effective
  entitlement resolution (read the table and the `effective_*` functions).
- `backend/app/scripts/reconcile_cognito_users.py` — the ongoing drift
  reconciler between the pool and the local `users` table (run `--help` for
  read-only `--report` and fix modes).
- `backend/app/scripts/retry_cognito_deletions.py` — retries deletions whose
  final `AdminDeleteUser` call failed after local deletion already succeeded.
- `infra/terraform/modules/cognito/` — the Cognito pool configuration
  (MFA settings, group management, client settings); see `main.tf` and
  `variables.tf` for the full setup.

</content>
</invoke>
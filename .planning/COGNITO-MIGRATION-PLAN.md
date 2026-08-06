# Cognito Authentication & Authorization Migration Plan

> **Status:** Approved for execution — decisions locked (see §1).
> **Scope:** Replace Flowin's first-party email/password + HS256 JWT authentication with Amazon Cognito User Pools, and move role/tier authorization to Cognito groups.
> **Grounding:** Every current-state claim in this document cites a file read from this repository. The codebase is the source of truth; where older docs (`docs/_audit/*`, `docs/WORKFLOWS.md`) disagree with code, the code wins and the doc is listed for update.
> **Author:** Architecture — Cognito migration
> **Related:** `.planning/IMPLEMENTATION-REGISTER.md`, `.planning/ROADMAP.md`, `.planning/ISSUES-REGISTER.md`, `docs/_audit/section_3_1_auth.md`, `infra/README.md`

---

## 1. Locked decisions

| # | Decision | Answer | Consequence in this plan |
|---|---|---|---|
| 1 | Login UX | **Keep the in-app email/password form; backend calls Cognito** | No CSP change, no `NEXT_PUBLIC_*` build-arg churn, no hosted UI. Backend uses `AdminInitiateAuth` |
| 2 | Federation / SSO | **Not now** | Pool is designed so an IdP can be added later without re-migration |
| 3 | Token storage | **Short-TTL bearer now; cookie/BFF in Phase 6** | `getToken()` seam preserved → 122 call sites / 57 frontend files untouched |
| 4 | MFA | **TOTP optional at cutover; required for admins in Phase 6** | Backend must handle auth challenges from day one; admin-only enforcement is an app-layer gate (see §5.5) |
| 5 | Existing prod users | **None yet** | **No user-migration campaign.** Production is greenfield. Phase 5 collapses to bootstrap + dev/test seed |
| 6 | Role/tier authority | **Cognito groups, not DB** | Reshapes authorization (see §5). DB columns survive only as a non-authoritative projection |
| 7 | `X-Flowin-API-Key` | **Leave as-is; add expiry as separate hardening** | Machine identity untouched by this migration |
| 8 | Cognito feature plan | **Essentials** | TOTP MFA available; **threat protection requires Plus** — flagged as a Phase 6 decision, not assumed |
| 9 | Environments | **One pool per environment** | Separate pool + app client per dev/stage/prod (assumption A-2 on creation timing) |
| 10 | Self-service password reset | **Phase 6 with SES** | Login page keeps omitting "Forgot?" at cutover |
| 11 | Cutover | **Dual-accept overlap, zero forced logout** | Legacy HS256 and Cognito RS256 both valid during the window |
| 12 | Break-glass | **Keep one local-password admin, documented and alarmed** | Local bcrypt + HS256 minting is **retained permanently**, scoped to one account (see §5.6) |

### 1.1 The two answers that reshaped the plan

**Decision 6 (roles in Cognito)** inverts the authorization design. The naive reading — "read `cognito:groups` on every request" — is correct and cheap, but a role change would then take up to one access-token lifetime to bite. This plan solves that by reusing a pattern the codebase already ships: the `iat`-versus-timestamp blanket revocation in `core/dependencies.py:75-115`. See §5.3.

**Decision 5 (no prod users)** removes the single most expensive and risky work package. There is no forced-reset campaign, no user-migration Lambda, no password-hash export debate. The critical path becomes the **bootstrap admin** path, because with self-registration disabled it is the only way into a fresh environment.

---

## 2. Executive summary

Cognito becomes the **credential authority** (passwords, policy, MFA, lockout, future federation) and the **role authority** (groups). PostgreSQL remains the **identity authority** (`users.id` and every ownership foreign key) and the **resource authorization authority** (per-run owner checks).

The migration is deliberately shaped so that the two largest surfaces in the codebase do not move:

- **Backend:** `get_current_user` keeps its exact signature (`-> User`), so all **76 route-level `Depends(get_current_user)` uses across 21 files** are untouched.
- **Frontend:** `getToken`/`setToken`/`clearToken` in `lib/api.ts` keep their exact contracts, so all **122 `getToken()` calls across 57 files** are untouched.

Everything therefore concentrates into: two token-validation functions, the `/api/auth/*` endpoints, the admin user CRUD, one Alembic migration, one Terraform module, and a small amount of frontend challenge/refresh wiring.

**Estimated effort:** 14–19 engineer-days for Phases 0–5, plus 4–6 days for Phase 6 hardening.

### 2.1 Non-goals

This migration explicitly does **not**:

- Introduce a Cognito **Identity Pool**. No browser code calls AWS APIs directly (verified: no `@aws-sdk` or `aws-amplify` import anywhere in `frontend/`), so temporary AWS credentials for the browser have no use case.
- Change `users.id` or any ownership foreign key.
- Introduce a tenant / organization / membership model. `Workspace` is a per-run execution scope, not a tenant.
- Replace per-resource ownership authorization. Cognito has no concept of a workflow run.
- Migrate `X-Flowin-API-Key` machine identity to Cognito M2M.
- Adopt hosted managed login, federation, or cookie/BFF sessions at cutover.

---

## 3. Verified current state

### 3.1 Authentication as implemented

| Concern | Implementation | Location |
|---|---|---|
| Self-registration | Hard-disabled, returns 403 | `backend/app/api/auth.py:23-38` |
| Login | Email lookup + bcrypt verify + local JWT mint | `backend/app/api/auth.py:41-68` |
| Token | HS256, claims `sub`/`exp`/`iat`/`jti`; `sub` **is** `users.id` | `backend/app/core/security.py:16, 46-66` |
| Token validation | `jwt.decode` with no `iss`/`aud`/`nbf` enforcement | `backend/app/core/security.py:82` |
| HTTP identity boundary | `HTTPBearer` → decode → user lookup → revocation gates | `backend/app/core/dependencies.py:19, 45-71, 125-155` |
| Per-token revocation | `revoked_tokens.jti` unique row; idempotent logout | `backend/app/api/auth.py:78-125`, `core/security.py:85-110` |
| Blanket revocation | Reject when `iat < password_changed_at` (whole-second grid) | `backend/app/core/dependencies.py:75-115` |
| Password change | bcrypt rehash + stamp `password_changed_at` | `backend/app/api/auth.py:135-165` |
| Non-HTTP validator | `_authenticate_token(token, db)` — mirrors the dependency, returns `None` instead of raising | `backend/app/api/run_engine.py:781` |
| Handoff WebSocket | JWT via `Sec-WebSocket-Protocol: bearer.<jwt>, flowin.v1` | `backend/app/api/websocket_handoff.py:71-95` |
| Machine identity | `X-Flowin-API-Key`, `flowin_` prefix, SHA-256 hash, revocable, no expiry | `backend/app/api/api_key_auth.py:49-88` |
| Refresh | **Endpoint does not exist.** Frontend calls it anyway | `frontend/src/hooks/useRunStream.ts:116-140` |

### 3.2 Authorization as implemented

| Layer | Mechanism | Location |
|---|---|---|
| Resource ownership | `WorkflowRun.user_id == current_user.id`, plus `owner_id`/`workspace_id` re-checks; cross-owner returns 404 | `api/runs.py`, `agents/authz.py` `ScopedStore` |
| Admin | `require_admin` reads `current_user.is_admin` | `backend/app/api/admin.py:24-31` |
| Tier entitlement | `can_run_pipeline(user.tier, pipeline_type)` against `TIER_PIPELINES` | `backend/app/core/entitlements.py:9-62` |
| Tier mutation | `PATCH /api/admin/users/{id}/tier` writes `users.tier` | `backend/app/api/admin.py:87-122` |
| Role mutation | **No endpoint.** `is_admin` is settable only at `POST /api/admin/users` | `backend/app/api/admin.py:125-166` |

Tiers are `basic` / `pro` / `enterprise` (`entitlements.py:6`).

### 3.3 Identity coupling — why `users.id` cannot change

`users.id` is a String UUID primary key (`backend/app/models/user.py:17`) referenced as a foreign key by, at minimum:

`WorkflowRun.user_id` · `ChatSession.user_id` · `WorkflowDefinition.user_id` · `WorkflowMemory.user_id` · `UserApiKey.user_id` · `HandoffSession.issuer_user_id` · `UserGitHubPat.user_id` · `RevokedToken.user_id`

Plus the `owner_id` / `workspace_id` execution-scope fields threaded through the run substrate. A Cognito `sub` is therefore introduced as a **mapping column**, never as a replacement key.

### 3.4 `SECRET_KEY` is not retired by this migration

`backend/app/core/crypto.py:29-49` derives a Fernet key from `settings.SECRET_KEY` via HKDF to encrypt GitHub PATs at rest (`api/settings.py:142`, `api/handoff.py:291`). Retiring JWT signing does **not** free `SECRET_KEY`; the boot guard at `core/config.py:340-380` stays exactly as it is. Combined with the break-glass decision (§5.6), local JWT signing also survives.

### 3.5 Blast radius

| Surface | Measured | Plan impact |
|---|---|---|
| `Depends(get_current_user)` | **76 uses / 21 files** | **0 changes** — signature preserved |
| `get_current_user` mentions (all forms) | 105 / 21 files | Internals only |
| `getToken()` calls | **122 / 57 files** | **0 changes** — seam preserved |
| `Bearer ${...}` interpolations | 22 | 0 changes — token value differs, shape identical |
| `create_access_token` in tests | 1 file (`test_logout.py`) | Fixture rework |
| Alembic head | `0030_workflow_runs_user_created_index.py` | New revision `0031` |

### 3.6 Infrastructure constraints that shaped the design

| Constraint | Evidence | Design consequence |
|---|---|---|
| `NEXT_PUBLIC_*` inlined at **build** time | `app.env.example`, `docker-compose.yml` build args | Browser-side Cognito config would force per-env image rebuilds → **backend-mediated flow chosen** |
| CSP `connect-src 'self' https://$DOMAIN wss://$DOMAIN` | `infra/scripts/reconcile-host-config.sh` | Direct browser→Cognito calls would be blocked → **backend-mediated flow chosen** |
| Secrets loader uses a **name allowlist** | `infra/scripts/bootstrap-ec2.sh` (`SECRET_KEY\|ACCESS_TOKEN_EXPIRE_HOURS\|LANGSMITH_*\|HANDOFF_MAX_TRANSCRIPT_BYTES`) | New Cognito SSM params are silently dropped unless the allowlist is edited → explicit Phase 1 task + boot guard |
| nginx rate-limits `/login`, `/register`, `/change-password` only | `infra/scripts/reconcile-host-config.sh` | `/api/auth/refresh` needs its own `limit_req_zone` |
| CORS hardcodes localhost, ignores `settings.CORS_ORIGINS`; `allow_credentials=True` | `backend/app/main.py:317-320` | Pre-existing drift. **Must be fixed before Phase 6 cookies**; harmless under bearer |
| Deps already present: `boto3==1.43.2`, `python-jose[cryptography]==3.3.0`, `httpx==0.28.1` | `backend/requirements.txt` | **No new Python dependencies required** |
| Single-EC2, in-process SSE/WS fan-out | `infra/README.md`, `api/websocket_handoff.py` docstring | JWKS cache can be in-process; no shared cache needed |

---

## 4. Target architecture

```text
Browser — unchanged bearer transport, unchanged login form
  │
  │ POST /api/auth/login  {email, password}
  ▼
FastAPI auth gateway ───AdminInitiateAuth──────►  Cognito User Pool (per env)
  │                     (ADMIN_USER_PASSWORD_AUTH)   • passwords + policy
  │  ◄── access(RS256) + id + refresh ──────────     • TOTP MFA (optional)
  │                                                  • groups = roles/tiers
  ├─ refresh token → encrypted at rest (existing Fernet/HKDF via crypto.py)
  ├─ access token  → browser (short TTL, existing getToken seam)
  ▼
Every request:  verify_credential(token)
  │   ├── Cognito RS256: JWKS(kid, cached) · iss · exp · token_use=access
  │   │                  · client_id · jti · iat · cognito:groups
  │   └── legacy HS256  : break-glass + dual-accept window only
  ▼
resolve_principal() → users WHERE cognito_sub = payload.sub
  │                   (or users.id for the legacy/break-glass path)
  ▼
User object (original users.id) + effective role/tier from cognito:groups
  │
  ▼
76 existing routes · ownership filters · require_admin · can_run_pipeline
                        ALL UNCHANGED
```

### 4.1 The crux: one function changes identity resolution

Current (`core/dependencies.py:45-71`):

```python
payload = decode_access_token(token)           # HS256, local secret
user_id = payload.get("sub")                   # sub IS users.id
user = db.query(User).filter(User.id == user_id).first()
```

Target:

```python
principal = verify_credential(token)           # Cognito RS256 | legacy HS256
user = resolve_principal(principal, db)        # cognito_sub | users.id
# principal also carries: jti, iat, groups
```

Because `get_current_user` still returns a `User` whose `id` is the original local UUID, no route, no ownership filter, and no foreign key is affected.

### 4.2 Two validators, one implementation

The codebase has two token validators that must not drift:

1. `core/dependencies.py::_decode_and_load_user` — raises `HTTPException`
2. `api/run_engine.py:781::_authenticate_token` — returns `None` (used by the handoff WebSocket)

Both are rewritten as thin adapters over a single shared resolver in the new `core/cognito.py` + `core/identity.py`. Protocol-drift risk between HTTP and WebSocket auth is thereby closed rather than duplicated.

---

## 5. Authorization design (Decision 6: Cognito groups)

### 5.1 Group model

| Cognito group | Precedence | Meaning |
|---|---|---|
| `flowin-admins` | 0 | `is_admin = true` |
| `flowin-tier-enterprise` | 10 | tier `enterprise` |
| `flowin-tier-pro` | 20 | tier `pro` |
| `flowin-tier-basic` | 30 | tier `basic` |

Cognito places group membership in the `cognito:groups` claim of **both** the access and ID tokens, and group `precedence` is a non-negative integer where **lower values take precedence** ([Cognito group precedence](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_GroupType.html), [user pool JWTs](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html)).

No IAM role is attached to any group. `cognito:preferred_role` is an Identity Pool concept and is not used. Tier resolution is performed in application code from the group names using our own precedence table, keeping `entitlements.py` the single home of tier semantics.

New pure functions in `core/entitlements.py`:

```python
def resolve_tier_from_groups(groups: list[str]) -> Tier:      # lowest precedence wins; default "basic"
def resolve_is_admin_from_groups(groups: list[str]) -> bool:   # membership of flowin-admins
```

Users with no tier group resolve to `basic` (fail-closed, matching the existing `TIER_PIPELINES.get(tier, basic)` fallback at `entitlements.py:52`).

### 5.2 Read path — zero AWS calls per request

The effective role and tier are read from the **verified access token's `cognito:groups` claim**. `AdminListGroupsForUser` is **not** called per request: at 76 authenticated route uses that would add an AWS round-trip, a throttling surface, and a latency tax to every call, and would make Cognito availability a hard dependency of every page load.

### 5.3 Solving group staleness — reuse of an existing pattern

A group change does not retroactively alter already-issued access tokens. Without mitigation, a demotion would remain ineffective for up to one access-token lifetime.

The codebase already solves exactly this shape of problem: `_check_password_change_revocation` (`core/dependencies.py:75-115`) rejects any token whose `iat` predates `users.password_changed_at`, at whole-second resolution, with a documented same-second tolerance rule.

**Design:** generalize that mechanism.

- Add `users.tokens_valid_from` (nullable datetime), backfilled from `password_changed_at`.
- The revocation check compares `iat` against `max(password_changed_at, tokens_valid_from)`, preserving the existing tested behaviour bit-for-bit while adding a second trigger.
- Any role or tier change stamps `tokens_valid_from = now()` and calls Cognito `AdminUserGlobalSignOut` (revoking refresh tokens).
- Net effect: the user's outstanding access tokens are rejected on their **next request**; the frontend's already-implemented silent-refresh path (`useRunStream.ts:116-140`) obtains a fresh token carrying the new `cognito:groups`.

Role changes therefore take effect immediately, with no per-request AWS call. The cost is that a role change forces one re-authentication round for that user — acceptable, and arguably the correct security behaviour for a privilege change.

### 5.4 The DB columns survive as a projection — and why they must

`users.tier` and `users.is_admin` are **demoted to a non-authoritative cached projection**, refreshed on login, on refresh, and on any admin-driven role change. They cannot simply be dropped, for three concrete reasons:

1. **`GET /api/admin/users`** (`api/admin.py:59-86`) lists every user with tier and role in one response. Sourcing that from Cognito means N × `AdminListGroupsForUser` calls per page render.
2. **Break-glass (Decision 12)** must work when Cognito is unreachable. A break-glass admin whose role lives only in Cognito is not a break-glass admin. The local `is_admin` column is the fallback authority for that one account.
3. Analytics and audit surfaces join on these columns.

Precedence rule, to be stated in code comments and enforced by tests:

> For a Cognito-authenticated principal, `cognito:groups` is authoritative and the DB projection is advisory. For the break-glass local principal, the DB columns are authoritative. The projection is never the input to an authorization decision on the Cognito path.

### 5.5 MFA enforcement nuance (Decision 4)

Cognito MFA configuration is **pool-wide** (`OFF` / `OPTIONAL` / `REQUIRED`); there is no native "required for admins only" setting. With optional MFA, AWS documents that the application must provide the enrolment interface ([Adding MFA to a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa.html)).

Therefore:

- **Cutover:** pool MFA = `OPTIONAL`, TOTP enabled. Backend supports the `MFA_SETUP` and `SOFTWARE_TOKEN_MFA` challenges; frontend gains a minimal enrolment/verification step.
- **Phase 6:** admin-only enforcement is an **application gate** — if `resolve_is_admin_from_groups()` is true and the principal has no confirmed TOTP device, deny privileged operations and route to enrolment.

Because MFA can appear as an auth challenge from day one, the login endpoint must be challenge-aware in Phase 3 even though MFA is optional. This avoids a second rewrite in Phase 6.

### 5.6 Break-glass admin (Decision 12)

| Aspect | Design |
|---|---|
| Identity | Exactly one `users` row with `auth_provider = 'local'`, non-null bcrypt `password_hash`, `is_admin = true` |
| Login path | `POST /api/auth/login` branches on `auth_provider`: `local` → existing bcrypt verify + `create_access_token` (HS256); otherwise → Cognito |
| Retained code | `security.create_access_token`, `decode_access_token`, `hash_password`, `verify_password`, `SECRET_KEY` JWT signing — **permanently retained**, scoped to this account |
| Gate | `BREAK_GLASS_ENABLED` setting; refuse if more than one local-admin row exists (fail closed, asserted at boot and by test) |
| Alarming | CloudWatch metric filter on the auth log for any break-glass login → SNS alert |
| Hygiene | Documented owner, documented rotation cadence, password in an approved secret store, never in `.tfvars` or SSM plaintext |

**Architectural consequence to accept explicitly:** the dual-validator is **permanent**, not transitional. `AUTH_ALLOW_LEGACY_JWT` (the dual-accept window flag) can be turned off after cutover, but the local-credential code path remains reachable for the break-glass principal. This is a deliberate trade of a small amount of retained attack surface for incident recoverability.

---

## 6. Data model changes

### 6.1 Migration `0031_cognito_identity_and_token_validity.py`

```python
# users: Cognito identity mapping
op.add_column("users", sa.Column("cognito_sub", sa.String(), nullable=True))
op.create_unique_constraint("uq_users_cognito_sub", "users", ["cognito_sub"])
op.create_index("ix_users_cognito_sub", "users", ["cognito_sub"], unique=False)

op.add_column("users", sa.Column(
    "auth_provider", sa.String(), nullable=False, server_default="local"))

# Generalized blanket revocation (role change + password change)
op.add_column("users", sa.Column("tokens_valid_from", sa.DateTime(), nullable=True))
op.execute("UPDATE users SET tokens_valid_from = password_changed_at "
           "WHERE password_changed_at IS NOT NULL")

# Projection freshness (observability for the group→DB sync)
op.add_column("users", sa.Column("roles_synced_at", sa.DateTime(), nullable=True))

# Cognito-native users have no local password
op.alter_column("users", "password_hash", existing_type=sa.String(), nullable=True)
```

**`password_hash` must become nullable.** Today it is `nullable=False` (`models/user.py:19`) and `api/admin.py:160` always writes one. Cognito-native users legitimately have no local hash; only the break-glass account retains one.

Downgrade path: drop the added columns/constraints and restore `password_hash` to NOT NULL — safe only while every row still has a hash, so the downgrade must assert that and fail loudly otherwise.

### 6.2 Resulting `users` shape

| Column | Authority after migration |
|---|---|
| `id` | **Local, unchanged** — ownership key everywhere |
| `email` | Local, mirrored from Cognito on provisioning |
| `cognito_sub` | Cognito principal mapping (unique, indexed) |
| `auth_provider` | `cognito` \| `local` (break-glass) |
| `password_hash` | Nullable; break-glass only |
| `password_changed_at` | Retained; existing revocation semantics preserved |
| `tokens_valid_from` | New; role-change + password-change revocation |
| `roles_synced_at` | New; projection freshness |
| `tier`, `is_admin` | **Projection** (advisory on the Cognito path; authoritative for break-glass) |
| `preferred_model`, timestamps | Unchanged |

### 6.3 Configuration additions (`core/config.py` `Settings`)

| Setting | Type / default | Source |
|---|---|---|
| `COGNITO_USER_POOL_ID` | `str = ""` | SSM `String` |
| `COGNITO_CLIENT_ID` | `str = ""` | SSM `String` |
| `COGNITO_CLIENT_SECRET` | `str = ""` | SSM `SecureString` + project CMK |
| `COGNITO_REGION` | `str = ""` (falls back to `AWS_REGION`) | SSM `String` |
| `COGNITO_JWKS_CACHE_TTL_SECONDS` | `int = 3600` | code default |
| `AUTH_ALLOW_LEGACY_JWT` | `bool = True` | env; `False` after cutover |
| `BREAK_GLASS_ENABLED` | `bool = True` | env |

New boot guard, mirroring the existing `_validate_secret_key` pattern: outside `ENV=development`, refuse to boot when Cognito is the active provider and pool ID / client ID / client secret are unset. This converts the silent-allowlist-omission failure mode (§3.6) into a loud, immediate startup error.

`ACCESS_TOKEN_EXPIRE_HOURS` remains meaningful **only** for break-glass tokens; Cognito controls its own token lifetimes on the app client. This must be documented at the setting, or it will be misread as the global session length.

---

## 7. Phase plan

### Phase 0 — Decisions and dev spike · 1 day

Decisions are locked (§1). Remaining work is a throwaway proof against a hand-made dev pool: `AdminInitiateAuth` with `SECRET_HASH`, then offline RS256 verification with `python-jose` including `iss` / `token_use` / `client_id` enforcement and a `cognito:groups` read.

**Exit gate:** one real Cognito access token verified offline, with its `cognito:groups` claim printed. No repository changes beyond a scratch script (not committed).

---

### Phase 1 — Infrastructure · 2–3 days

New module `infra/terraform/modules/cognito/` following the existing module layout (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `README.md`) and the mandatory-tags locals pattern.

Resources:

| Resource | Configuration |
|---|---|
| `aws_cognito_user_pool` | `admin_create_user_config { allow_admin_create_user_only = true }` (mirrors the deliberate invitation-only posture at `api/auth.py:23-38`); password policy; `mfa_configuration = "OPTIONAL"` with TOTP; `deletion_protection = "ACTIVE"` in prod; feature plan **Essentials** |
| `aws_cognito_user_pool_client` | Confidential client with secret; `explicit_auth_flows = [ADMIN_USER_PASSWORD_AUTH, REFRESH_TOKEN_AUTH]`; `enable_token_revocation = true`; `prevent_user_existence_errors = "ENABLED"`; `access_token_validity` 30–60 min; `id_token_validity` matched; `refresh_token_validity` per environment |
| `aws_cognito_user_group` ×4 | `flowin-admins` (0), `flowin-tier-enterprise` (10), `flowin-tier-pro` (20), `flowin-tier-basic` (30). No IAM role attached |

No user pool domain and no hosted UI (Decision 1). No IdP resources (Decision 2), but the pool is left able to accept one later.

Wiring tasks:

| Task | File |
|---|---|
| SSM params for pool ID, client ID (`String`) and client secret (`SecureString`, project CMK) | `infra/terraform/modules/secrets/main.tf` |
| Module call, outputs, per-env variables | `infra/terraform/app/*`, env `*.tfvars` |
| IAM: `cognito-idp:AdminInitiateAuth`, `AdminRespondToAuthChallenge`, `AdminCreateUser`, `AdminGetUser`, `AdminSetUserPassword`, `AdminDeleteUser`, `AdminUserGlobalSignOut`, `AdminAddUserToGroup`, `AdminRemoveUserFromGroup`, `AdminListGroupsForUser`, `RevokeToken` — **scoped to the single pool ARN**, least privilege | `infra/terraform/modules/iam` |
| **Add the four Cognito names to the secrets-loader allowlist** | `infra/scripts/bootstrap-ec2.sh` |
| `limit_req_zone velocityai_refresh` + `location /api/auth/refresh` | `infra/scripts/reconcile-host-config.sh` |

**Exit gate:** `terraform fmt -check -recursive`, `terraform validate`, `checkov`, `trivy config`, `tflint` clean; dev plan reviewed and applied; **`/etc/velocityai/app.env` on the dev host actually contains the four Cognito variables** — this is the only proof the allowlist edit worked.

**Accepted risk:** the app-client secret is Terraform-generated, so it enters Terraform state. Same exposure class as the existing `random_password` `SECRET_KEY` and DB password, mitigated identically (encrypted S3 backend, DynamoDB locking, restricted access). Recorded here rather than left implicit.

---

### Phase 2 — Backend identity core · 3–4 days

1. **Migration `0031`** per §6.1, plus the `User` model update.
2. **`backend/app/core/cognito.py`** (new):
   - JWKS fetch via `httpx` with in-process TTL cache and a single refetch on unknown `kid`; bounded retry; **fail closed** when unavailable.
   - `verify_cognito_access_token()` enforcing: signature, `kid`, `iss == https://cognito-idp.{region}.amazonaws.com/{pool_id}`, `exp`, `token_use == "access"`, `client_id`, presence of `sub` and `jti`; returns a typed principal including `groups`.
   - `SECRET_HASH` helper and thin boto3 wrappers for the admin operations.
3. **`backend/app/core/identity.py`** (new): `verify_credential()` + `resolve_principal()` — the single shared resolver, dual-accepting Cognito RS256 and (while `AUTH_ALLOW_LEGACY_JWT` or break-glass) legacy HS256.
4. **Rewire both validators** to the shared resolver: `core/dependencies.py::_decode_and_load_user` and `api/run_engine.py:781::_authenticate_token`. Signatures unchanged.
5. **Generalize revocation:** `_check_password_change_revocation` → compares against `max(password_changed_at, tokens_valid_from)`, preserving the documented same-second tolerance.
6. **`core/entitlements.py`:** add `resolve_tier_from_groups` / `resolve_is_admin_from_groups`; attach effective role/tier to the resolved principal.

**Exit gate:** unit tests for tampered signature, expired token, wrong issuer, wrong `client_id`, `token_use=id` rejection, unknown `kid`, JWKS unavailable, missing `jti`, group precedence resolution, and `tokens_valid_from` revocation. Existing suites green under both token types. CI stays **offline**: tests sign with a locally generated RSA key and inject a fake JWKS.

---

### Phase 3 — Auth and admin endpoints · 4–5 days

| Endpoint | Change | Contract |
|---|---|---|
| `POST /api/auth/login` | Branch on `auth_provider`. Cognito: `AdminInitiateAuth(ADMIN_USER_PASSWORD_AUTH)` + `SECRET_HASH`; persist refresh token encrypted (existing Fernet/HKDF); refresh the role projection; return `AuthResponse`. Handle `NEW_PASSWORD_REQUIRED`, `MFA_SETUP`, `SOFTWARE_TOKEN_MFA` via `AdminRespondToAuthChallenge` | `AuthResponse` shape **unchanged**; new optional challenge response variant |
| `POST /api/auth/refresh` | **New.** `REFRESH_TOKEN_AUTH`; returns `{ "token": "..." }` — exactly the shape `useRunStream.ts:135` already parses | New |
| `POST /api/auth/logout` | Keep the `revoked_tokens` insert **and** add Cognito `RevokeToken`; keep 204 idempotency including the `IntegrityError` path | Unchanged |
| `POST /api/auth/change-password` | Cognito `ChangePassword`; keep stamping `password_changed_at`; revoke the stored refresh token. Break-glass keeps the bcrypt path | Unchanged |
| `GET /api/auth/me` | Serve `tier`/`is_admin` from the **effective** principal (groups), not the raw column | Unchanged |
| `POST /api/auth/register` | Remains 403 | Unchanged |
| `POST /api/admin/users` | `AdminCreateUser` (+ `AdminSetUserPassword` temporary) → `AdminAddUserToGroup` for tier/role → insert local row with `cognito_sub`, `auth_provider='cognito'`, projection. Compensating `AdminDeleteUser` if the local insert fails | Unchanged |
| `PATCH /api/admin/users/{id}/tier` | `AdminRemoveUserFromGroup` + `AdminAddUserToGroup`, stamp `tokens_valid_from`, `AdminUserGlobalSignOut`, update projection | Unchanged |
| `PATCH /api/admin/users/{id}/role` | **New** — first real endpoint for `is_admin`, now that role lives in a group | New |
| `DELETE /api/admin/users/{id}` | `AdminDeleteUser` then local delete; tolerate an already-absent pool user; keep the self-delete guard | Unchanged |
| **Bootstrap admin** | `app/scripts/bootstrap_admin.py` + `.github/scripts/remote-deploy.sh` §12 must create the pool user, add it to `flowin-admins`, and write the local row with `cognito_sub` | **Critical path — a fresh environment is otherwise unreachable** |

**Exit gate:** integration tests against the dev pool — login → refresh → authenticated SSE attach → logout revokes → change-password revokes → tier change forces refresh and new entitlement → admin create/delete leaves no orphan in either store; bootstrap on an empty database yields a working admin login.

---

### Phase 4 — Frontend · 2–3 days

Deliberately minimal, because the `getToken` seam is preserved (Decision 3).

| File | Change |
|---|---|
| `frontend/src/lib/api.ts` | `login()` keeps its shape; add a shared 401 → refresh → retry path so REST matches what SSE already does; handle the challenge response variant |
| `frontend/src/hooks/useRunStream.ts` | **No logic change** — its existing refresh path starts working for the first time |
| `frontend/src/hooks/useHandoffSocket.ts` | No shape change; `bearer.<cognito access token>` |
| `frontend/src/app/login/page.tsx` | Unchanged for the happy path; **new** first-login "set a new password" state and minimal TOTP enrol/verify states |
| `frontend/src/app/admin/*` | Surface the new role endpoint; note that a tier/role change signs the target user out |

No "Forgot password?" affordance at cutover (Decision 10); the deliberate omission recorded in `.planning/phases/35-shell-chrome-reskin-pages-b1/35-CONTEXT.md:17` stands.

**Exit gate:** `npm run lint`, `npm run test`, `npm run build` clean; manual verification that a long-running workflow survives access-token expiry through silent refresh without dropping the SSE stream.

---

### Phase 5 — Cutover · 1–2 days per environment

Decision 5 (no production users) reduces this from a migration campaign to a provisioning exercise.

```text
per environment (dev → stage → prod):
  1. deploy with AUTH_ALLOW_LEGACY_JWT=true          # dual-accept, zero forced logout
  2. bootstrap admin  → Cognito user + flowin-admins + local row (cognito_sub set)
  3. provision real users via POST /api/admin/users  # creates in both stores
  4. create the single break-glass local admin       # documented, alarmed
  5. verify: SELECT count(*) FROM users
             WHERE auth_provider='cognito' AND cognito_sub IS NULL   → 0
  6. verify: exactly one row with auth_provider='local'
  7. flip AUTH_ALLOW_LEGACY_JWT=false
  8. let any outstanding legacy tokens age out (≤ ACCESS_TOKEN_EXPIRE_HOURS)
```

Dev and test data: rewrite `backend/scripts/seed_test_users.py` to provision through the same Cognito-aware path rather than writing `password_hash` directly.

**Exit gate:** step 5 and step 6 assertions pass; a full workflow run completes end to end on Cognito credentials; break-glass login verified **and** confirmed to raise its alarm.

---

### Phase 6 — Hardening · 4–6 days, staged after cutover

1. **Admin MFA enforcement** — app-layer gate per §5.5.
2. **Threat protection decision** — compromised-credential detection and adaptive auth require the **Plus** plan; Decision 8 selected Essentials. Explicit decision point, with a note in Cognito's favour: AWS documents that compromised-credential checks apply to `ADMIN_USER_PASSWORD_AUTH` but **not** SRP, so the backend-mediated flow chosen in Decision 1 is compatible with it.
3. **Self-service password reset with SES** — verified domain, DKIM, bounce handling; then add the "Forgot?" affordance.
4. **Cookie/BFF session** — the remaining XSS exposure. `localStorage` plus a CSP allowing `'unsafe-inline'`/`'unsafe-eval'` means stored XSS reaches the token; the existing audit already records an LLM-output injection path (`docs/_audit/section_2_cross_cutting.md`). **Prerequisite:** fix the `main.py:317` CORS drift and add CSRF defence.
5. **API-key expiry** (Decision 7 follow-up) — add expiry to `UserApiKey`; `api_key_auth.py` currently checks only `revoked_at`.
6. **Auth observability** — structured auth events, CloudWatch alarms on login-failure spikes, break-glass alarm verification.
7. **Documentation closure** — close `docs/_audit/section_3_1_auth.md` C1 (no `iss`/`aud`) and C2 (symmetric HS256), both resolved on the Cognito path; update `docs/WORKFLOWS.md` W02–W07 and `infra/README.md`.

---

## 8. Rollback

| Stage | Rollback |
|---|---|
| Phase 1 | Terraform destroy of the Cognito module. No application impact |
| Phase 2 | Additive only: `cognito_sub` nullable, dual-accept on. Revert the deploy |
| Phase 3 | `AUTH_PROVIDER` / `AUTH_ALLOW_LEGACY_JWT` flags restore local login; `password_hash` still present for any user that has one |
| Phase 5 pre-flip | Both credential stores valid; no user action required |
| Phase 5 post-flip | Set `AUTH_ALLOW_LEGACY_JWT=true`; Cognito-native users have no local hash, so **full local fallback exists only for the break-glass admin** — this is the accepted design, not a gap |
| Cognito outage | Break-glass admin (§5.6) provides operator access. Regular users cannot authenticate; existing unexpired access tokens continue to work because validation is offline against cached JWKS |

The last row is worth stating plainly: after cutover, Cognito availability becomes a hard dependency for **new** logins. Cached JWKS and offline validation mean in-flight sessions survive a Cognito control-plane blip, but a prolonged outage blocks sign-in. That is the accepted cost of a managed identity provider.

---

## 9. Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Fresh environment unreachable — self-registration disabled and bootstrap not Cognito-aware | **High** | Phase 3 rewires `bootstrap_admin.py` + `remote-deploy.sh` §12; proven on a scratch environment before prod |
| R2 | SSM allowlist omission → app boots without Cognito config | **High** | Phase 1 allowlist edit + `app.env` assertion + new boot guard (§6.3) |
| R3 | Revoked Cognito token still passes offline JWT validation | **High** | Keep the `revoked_tokens` denylist; short access TTL. AWS documents this caveat explicitly ([token revocation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)) |
| R4 | Long-running workflows die on token expiry | **High** | `/api/auth/refresh` is a Phase 3 deliverable, not optional. Client half already exists |
| R5 | Group change not honoured until token expiry | **High** | `tokens_valid_from` stamp + `AdminUserGlobalSignOut` (§5.3) |
| R6 | JWKS unavailable → total auth outage | Medium | Cached JWKS with TTL, bounded retry, fail closed, alarm |
| R7 | Orphaned users between Cognito and PostgreSQL | Medium | Compensating actions on create/delete + a reconciliation report script |
| R8 | Two validators drift (HTTP vs handoff WebSocket) | Medium | Single shared resolver in `core/identity.py`; both paths tested |
| R9 | Role projection read as authoritative by future code | Medium | Precedence rule in code comments + a test asserting the Cognito path ignores the columns |
| R10 | App-client secret in Terraform state | Medium | Encrypted remote backend, restricted access; same class as existing generated secrets |
| R11 | Access token still in `localStorage` | Medium | Short TTL now; Phase 6 cookie/BFF |
| R12 | Break-glass account becomes a standing weakness | Medium | Single-row assertion, `BREAK_GLASS_ENABLED` flag, alarm on use, documented rotation |
| R13 | `ACCESS_TOKEN_EXPIRE_HOURS` misread as global session length | Low | Document at the setting; it governs break-glass tokens only |
| R14 | Cognito `sub` reuse after delete/recreate | Low | Unique constraint on `cognito_sub`; delete both stores together |
| R15 | Essentials plan lacks threat protection, assumed present | Low | Explicit Phase 6 decision point (§7 Phase 6, item 2) |

---

## 10. Test impact

| Test / script | Impact |
|---|---|
| `backend/tests/unit/test_logout.py` | Only in-tree user of `create_access_token`; needs Cognito-token fixtures. Already environmentally failing per `.planning` deferred-items notes |
| `backend/tests/unit/test_bootstrap_admin.py` | Asserts non-null `password_hash` and bcrypt round-trip |
| `backend/tests/integration/test_bootstrap_admin_postgres.py` | Same, plus admin bootstrap semantics |
| `backend/scripts/seed_test_users.py` | Writes `password_hash` directly; must move to the Cognito-aware path |
| `backend/tests/integration/test_handoff_api.py` | API-key path — must stay green; use as the regression canary that machine identity was untouched |
| `backend/tests/agents/test_alembic.py` | Migration drift/`check` suite must accept `0031` |
| **New** | JWKS and claim-validation unit tests; group-precedence resolution tests; `tokens_valid_from` revocation tests; login/refresh/logout/change-password integration tests; break-glass single-row assertion; role-change-forces-refresh test |

**CI must remain offline-capable.** No test may call AWS. Sign test tokens with a locally generated RSA key and inject the JWKS into the cache, mirroring the existing `InMemorySpanExporter` injection pattern used for the OTel hook tests.

---

## 11. Configuration and secrets inventory

| Name | Store | Type | Notes |
|---|---|---|---|
| `COGNITO_USER_POOL_ID` | SSM `${prefix}/COGNITO_USER_POOL_ID` | String | Add to loader allowlist |
| `COGNITO_CLIENT_ID` | SSM `${prefix}/COGNITO_CLIENT_ID` | String | Add to loader allowlist |
| `COGNITO_CLIENT_SECRET` | SSM `${prefix}/COGNITO_CLIENT_SECRET` | SecureString + CMK | Add to loader allowlist |
| `COGNITO_REGION` | SSM `${prefix}/COGNITO_REGION` | String | Defaults to `AWS_REGION` (`eu-central-1`) |
| `AUTH_ALLOW_LEGACY_JWT` | env | bool | `true` during cutover, then `false` |
| `BREAK_GLASS_ENABLED` | env | bool | Alarmed when used |
| `SECRET_KEY` | SSM (existing) | SecureString | **Retained** — PAT encryption (§3.4) + break-glass JWT signing |
| `ACCESS_TOKEN_EXPIRE_HOURS` | SSM (existing) | String | Now break-glass tokens only |

No Cognito value is exposed to the browser, so no `NEXT_PUBLIC_*` variable and no frontend image rebuild is required. This is a direct benefit of Decision 1.

---

## 12. Assumptions and remaining open items

| ID | Item | Assumption taken | Needs confirmation |
|---|---|---|---|
| A-1 | Region | `eu-central-1`, consistent with `core/config.py` and the existing infrastructure | Low risk |
| A-2 | Pool creation timing | All three pools (dev/stage/prod) created in Phase 1 via the same module; cutover sequenced dev → stage → prod. Empty pools cost nothing under MAU pricing | **Confirm** |
| A-3 | Access token TTL | 30–60 minutes, with silent refresh covering long runs | **Confirm** |
| A-4 | Refresh token TTL | Shorter in dev, longer in prod; rotation considered in Phase 6 | **Confirm** |
| A-5 | Password policy | Cognito default strengthened to ≥ 12 characters, exceeding the current 8-character rule at `api/auth.py:158` and `api/admin.py:154` | **Confirm** |
| A-6 | Dev/test users | Recreated rather than migrated | Low risk (Decision 5) |
| A-7 | Threat protection | Deferred pending the Essentials → Plus decision | **Phase 6 decision** |
| A-8 | Existing non-prod users | Any dev/stage accounts are disposable | **Confirm** |

---

## 13. Appendix — file-level change inventory

### Created

```text
infra/terraform/modules/cognito/{main,variables,outputs,versions}.tf, README.md
backend/app/core/cognito.py                 # JWKS cache, token verification, boto3 wrappers
backend/app/core/identity.py                # verify_credential + resolve_principal (shared)
backend/alembic/versions/0031_cognito_identity_and_token_validity.py
backend/tests/unit/test_cognito_verifier.py
backend/tests/unit/test_group_role_resolution.py
backend/tests/integration/test_cognito_auth_flow.py
```

### Modified — backend

```text
app/core/config.py          # Cognito settings + boot guard; document ACCESS_TOKEN_EXPIRE_HOURS scope
app/core/dependencies.py    # _decode_and_load_user → shared resolver; generalized revocation
app/core/entitlements.py    # resolve_tier_from_groups / resolve_is_admin_from_groups
app/core/security.py        # unchanged API; docstrings scoped to break-glass
app/api/auth.py             # login branch, /refresh (new), logout revoke, change-password
app/api/admin.py            # create/delete via Cognito; tier via groups; new /role endpoint
app/api/run_engine.py       # _authenticate_token → shared resolver
app/models/user.py          # cognito_sub, auth_provider, tokens_valid_from, roles_synced_at, nullable password_hash
app/scripts/bootstrap_admin.py
scripts/seed_test_users.py
```

### Modified — frontend

```text
src/lib/api.ts                    # 401→refresh→retry; challenge response handling
src/app/login/page.tsx            # first-login password set; minimal TOTP states
src/app/admin/*                   # role endpoint; sign-out-on-role-change notice
```

`src/hooks/useRunStream.ts` and `src/hooks/useHandoffSocket.ts` require **no logic change**.

### Modified — infrastructure and CI

```text
infra/terraform/app/*                       # module call, outputs, tfvars
infra/terraform/modules/secrets/main.tf     # four Cognito SSM parameters
infra/terraform/modules/iam/*               # pool-scoped Cognito permissions
infra/scripts/bootstrap-ec2.sh              # secrets-loader allowlist  ← easily missed
infra/scripts/reconcile-host-config.sh      # /api/auth/refresh rate-limit zone
.github/scripts/remote-deploy.sh            # §12 Cognito-aware admin bootstrap
```

### Documentation to update

```text
docs/WORKFLOWS.md                    # W02–W07 auth workflows
docs/_audit/section_3_1_auth.md      # close C1 (no iss/aud) and C2 (HS256)
infra/README.md                      # Cognito in the AWS service inventory
.planning/IMPLEMENTATION-REGISTER.md # register this migration
.planning/ROADMAP.md                 # phase entries
```

---

## 14. Ordered execution checklist

- [ ] **P0** Dev spike: `AdminInitiateAuth` + offline RS256 verification + `cognito:groups` read
- [ ] **P1** Cognito Terraform module, four groups with precedence, SSM params, pool-scoped IAM
- [ ] **P1** Secrets-loader allowlist edit **and** `app.env` verification on the dev host
- [ ] **P1** nginx rate-limit zone for `/api/auth/refresh`
- [ ] **P2** Migration `0031` + `User` model update
- [ ] **P2** `core/cognito.py` verifier with cached JWKS, fail-closed
- [ ] **P2** `core/identity.py` shared resolver; rewire both validators
- [ ] **P2** Generalized `tokens_valid_from` revocation; group→role resolution
- [ ] **P3** `login` (challenge-aware), **`refresh` (new)**, `logout`, `change-password`
- [ ] **P3** Admin create/delete/tier via Cognito groups; new `/role` endpoint
- [ ] **P3** Cognito-aware bootstrap admin — **fresh-environment critical path**
- [ ] **P4** Frontend 401→refresh→retry, first-login password, minimal TOTP
- [x] **P5** Cutover tooling shipped: `scripts/create_break_glass_admin.py` (single-row refusal), `scripts/verify_cognito_cutover.py` (C1–C5 gate), Cognito-aware `scripts/seed_test_users.py`, runtime fail-closed break-glass invariant, `infra/COGNITO-CUTOVER-RUNBOOK.md`
- [x] **P5** Cutover flags made operational (SSM-managed `AUTH_PROVIDER` / `AUTH_ALLOW_LEGACY_JWT` / `BREAK_GLASS_ENABLED`) so the flip is a parameter change + restart, not a redeploy; `cognito_enabled = true` set for dev
- [x] **P5 (dev)** Foundation applied — pool `eu-central-1_1NiEjdyko` + client + 4 groups + pool-scoped IAM + 7 SSM params live; config verified against AWS
- [x] **P0 exit gate MET (for real)** — real `AdminInitiateAuth` token verified **offline** against the live JWKS with `cognito:groups` printed; plus `sub`→local-row mapping, group→tier/admin resolution across all tiers, refresh, revoke, tampered-signature rejection and `token_use` enforcement. Two real bugs found this way and fixed: (a) `count` guards on unknown-until-apply values broke `terraform plan`; (b) `REFRESH_TOKEN_AUTH` needs `SECRET_HASH` over the **canonical** username (`cognito_sub`), not the email alias — regression-guarded by `tests/unit/test_cognito_refresh_secret_hash.py`
- [ ] **P5 (operator)** Stand up a dev host (app layer needs a real `alert_email`), bootstrap the admin there, prove login — runbook steps 2–3
- [ ] **P5 (operator)** Flip `auth_provider = "cognito"`; provision users; create the break-glass admin (alarm verified) — runbook steps 4–6
- [ ] **P5 (operator)** `verify_cognito_cutover.py --check-pool` green, then flip `AUTH_ALLOW_LEGACY_JWT=false` — runbook steps 7–8
- [ ] **P5 (operator)** Repeat for stage, then prod
- [x] **P6.1** Admin MFA gate — `ADMIN_MFA_REQUIRED` + `core/identity.py::enforce_admin_mfa` (Cognito principals only, break-glass exempt by construction, fails OPEN on a Cognito lookup error with a documented rationale); TOTP enrolment via `POST /api/auth/mfa/totp/associate` + `/verify`; `require_admin` now reads `cognito:groups` instead of the advisory DB column
- [x] **P6.2** Essentials→Plus surfaced as explicit `feature_plan` + `threat_protection_mode` variables + `aws_cognito_risk_configuration` (skipped unless PLUS), closing A-7/R15
- [x] **P6.3** SES-backed email (`ses_source_arn`/`ses_from_email_address`) + `POST /api/auth/forgot-password` and `/confirm` (always-generic response to avoid an enumeration oracle; break-glass excluded; stamps `tokens_valid_from` + clears the refresh token on success)
- [x] **P6.4** CORS drift FIXED — `main.py` now honours `settings.CORS_ORIGINS`, appends localhost only in development, and refuses to boot on `*` + credentials. (Cookie/BFF itself remains deferred; this was its prerequisite.)
- [x] **P6.5** `UserApiKey.expires_at` + migration `0033` + enforcement in `api_key_auth.py` (uniform 401) + 90-day default at mint; pre-existing keys stay NULL/never-expire so no live integration breaks
- [x] **P6.6** `core/auth_events.py` structured auth events + CloudWatch metric filters/alarms for break-glass login, break-glass invariant violation, and login-failure spikes
- [x] **P6.7** Docs closed — `docs/_audit/section_3_1_auth.md` C1/C2 + telemetry theme annotated with the resolution and the deliberate break-glass carve-out; `infra/README.md` Cognito inventory; `infra/COGNITO-CUTOVER-RUNBOOK.md` Phase 6 section
- [ ] **P6 (deferred)** Cookie/BFF session — token still in `localStorage`; needs CSRF design first. Prerequisite (P6.4) now done.

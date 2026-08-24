# Cognito Authentication & Authorization QA — Bug Report

**Assessment Date:** 2026-08-07  
**Revision:** commit `4585410e`  
**Status:** FAIL — not production release-ready  
**No files modified; git status clean**

---

## Executive Summary

Deep read-only analysis of Flowin's Cognito-based login, authentication lifecycle, and authorization controls identified **1 P0 admin-MFA failure**, **4 primary P1 authorization/session defects**, and **multiple P2 hardening gaps**. The core Cognito verifier and several authorization foundations are strong, but the current implementation is not ready for production Cognito cutover.

---

## P0 — CRITICAL: Admin MFA is Off by Default and Bypassable

**Severity:** P0 (admin privilege escalation / security gate bypass)  
**Impact:** An authenticated admin can enroll in a new MFA factor without reauthentication, then reuse their existing password-only bearer to access `/api/admin/*` routes.

### Root Causes

1. **Not wired into standard deployment:**
   - `Settings.ADMIN_MFA_REQUIRED` defaults to `False` in `backend/app/core/config.py:351`
   - No Terraform `secrets` module variable or SSM resource publishes this setting
   - Host-loader allowlist in `infra/scripts/bootstrap-ec2.sh:712` omits `ADMIN_MFA_REQUIRED`
   - Repo-managed deployments never load this setting; manual `TF_VAR_*` override required

2. **Logic defect — wrong authentication proof:**
   - `core/identity.py::enforce_admin_mfa()` calls `has_any_confirmed_mfa()` to check account **enrollment**
   - Does NOT verify that the current **session/token** completed MFA proof
   - Deliberately fails **open** on Cognito lookup errors: logged with reason `no_confirmed_mfa` but exception is suppressed

3. **Enrollment attack vector — no reauthentication required:**
   - `POST /api/auth/mfa/totp/associate` returns an `otpauth://` secret, callable with any existing bearer
   - `POST /api/auth/mfa/totp/verify` (and email enable) do not require reauthentication or step-up
   - Neither call revokes the original bearer
   - An admin can enroll TOTP, immediately verify it, and reuse the same password-only token on admin routes

### Evidence

- File: `backend/app/core/identity.py:289-350` — `enforce_admin_mfa()` checks `has_any_confirmed_mfa(principal.sub)` and catches exceptions on Cognito errors
- File: `backend/app/api/auth.py:737-780` — `enable_email_mfa()` and `verify_totp()` never check session MFA state
- File: `backend/app/core/config.py:351` — `ADMIN_MFA_REQUIRED: bool = False`
- File: `infra/terraform/modules/secrets/main.tf` — no resource for `ADMIN_MFA_REQUIRED` parameter
- File: `infra/scripts/bootstrap-ec2.sh:712` — allowlist omits `ADMIN_MFA_REQUIRED`

### Reproduction

1. Create or login as an admin (Cognito group or break-glass local)
2. POST `/api/auth/mfa/totp/associate` → receive `otpauth://` URI
3. Scan QR, verify code
4. POST `/api/auth/mfa/totp/verify` with the code using the **same original bearer** (no reauthentication required)
5. Call `POST /api/admin/users` with the same bearer → succeeds (if ADMIN_MFA_REQUIRED were manually enabled)

### Fix Scope

- **Immediate:** Disable sensitive admin mutations until MFA is bound to session proof
- **Design:** Implement session-bound step-up (short-lived server-state, recent reauthentication proof, step-up revocation on new enrollment, fail-closed)
- **Deployment:** Wire `ADMIN_MFA_REQUIRED` through Terraform, SSM, and loader allowlist so it can be enabled safely

---

## P1 — Authorization: REST Pipeline Launch Has No Tier Check

**Severity:** P1 (unauthorized feature access, tier-based pricing bypass)  
**Impact:** Any authenticated user can launch any tier-restricted pipeline regardless of their subscription tier.

### Root Cause

`launch_run()`, `create_revision()`, and `resume_run_endpoint()` in `backend/app/api/run_commands.py` never invoke `can_run_pipeline(tier, pipeline_type)`. The entitlement helper exists and is used in saved-workflow creation, but is completely absent from the launch codepath.

### Evidence

- File: `backend/app/api/run_commands.py:launch_run()` — no `can_run_pipeline()` call
- File: `backend/app/api/run_commands.py:create_revision()` — no entitlement check
- File: `backend/app/api/run_commands.py:resume_run_endpoint()` — no entitlement check
- File: `backend/tests/unit/test_rest_run_launch.py::test_launch_mints_run()` — passes with `_FakeUser(tier=None)`, proving no tier dependency
- File: `backend/app/api/user_workflows.py::create_user_workflow()` — uses raw `current_user.tier` instead of `Principal`-derived tier authority from token groups

### Test Evidence

```
test_rest_run_launch.py::test_launch_mints_run PASSED
```

The fixture `_FakeUser` has no `tier` attribute set. The test passes, meaning launch does not depend on tier.

### Reproduction

```bash
# Any authenticated user, regardless of tier
POST /api/runs/gate/launch
{
  "pipeline_type": "ppt",  # Enterprise tier
  "agents": [...],
  "model_overrides": {...}
}
→ 200 OK, run_id returned (no 403)
```

### Fix Scope

- Centralize tier authorization using `Principal` + `effective_tier()`
- Enforce on launch, revision creation, resume, and saved-workflow creation
- Ensure `Principal` is always the authoritative tier source; never use raw DB `current_user.tier`

---

## P1 — Token Refresh: Impossible After Access Token Expiry

**Severity:** P1 (session timeout without recovery, forced logout)  
**Impact:** When an access token expires, the refresh endpoint cannot be called because it requires a valid bearer. Frontend waits for a 401 to trigger refresh, but by then the token is invalid. Pre-expiry refresh only works while an SSE stream is active.

### Root Cause

`backend/app/api/auth.py::refresh()` calls `get_current_user_with_payload(token)`, which decodes and validates the JWT. If `exp` has passed, the token is rejected before the refresh logic runs.

### Specification Mismatch

- **Backend requirement:** Current bearer must be unexpired
- **Frontend expectation:** Expired bearer can be refreshed
- **Test:** `frontend/src/lib/api.refreshRetry.test.ts::test_refresh_after_401_mints_new_token()` mocks a backend success after expiry—an impossible outcome

### Evidence

- File: `backend/app/api/auth.py:661-680` — `refresh()` function signature requires `current_user`
- File: `backend/app/core/dependencies.py::get_current_user()` — calls `verify_identity(token)` which rejects expired JWTs
- File: `frontend/src/lib/api.ts::request()` — on 401, calls `refreshOnce()` with the expired token still in `options.headers`
- File: `frontend/src/hooks/useRunStream.ts:130-145` — pre-expiry timer fires only inside the effect scope; if no stream is attached, no refresh occurs
- File: `frontend/src/lib/api.refreshRetry.test.ts` — test passes with mock backend returning 200 after expiry

### Session Recovery Scenarios

| Scenario | Pre-expiry refresh | Post-expiry refresh | Outcome |
|----------|-------------------|-------------------|---------|
| REST request at expiry | ✓ (if SSE stream active) | ✗ (bearer invalid) | 401, no recovery |
| SSE stream established | ✓ (pre-expiry timer runs) | N/A | Continuous session |
| Idle REST-only user | ✗ (no timer active) | ✗ (bearer invalid) | Forced logout |

### Reproduction

1. Frontend calls a REST endpoint with bearer approaching expiry (< 60s left)
2. No SSE stream is active, so pre-expiry timer never scheduled
3. Token expires during request processing
4. 401 response triggers frontend refresh attempt
5. Refresh call with same expired bearer → 401 (token verification fails)
6. User forced to re-login

### Fix Scope

- Redesign refresh credentials: HttpOnly session/refresh cookie, rotated secrets, or short-lived symmetric keys
- Either (a) accept expired bearers for the refresh endpoint only, or (b) defer expiry check until after refresh verification
- Align frontend tests with real backend contract
- Consider shifting refresh authorization from bearer verification to a separate refresh-token channel

---

## P1 — Stream Revocation: Logout/Password/Role Changes Don't Terminate Established Connections

**Severity:** P1 (privilege escalation, session hijacking on privilege changes)  
**Impact:** Once an SSE or WebSocket stream is established, logout, password reset, role/tier changes, token expiry, and per-`jti` revocation do not interrupt the connection. A user can remain reading/writing workflow state while their privileges are reduced or token is revoked.

### Root Cause

- **SSE (`backend/app/api/run_stream.py`):** Authentication occurs before the streaming generator begins. Once `stream_attached` is sent, no per-message reauthentication exists.
- **WebSocket handoff (`backend/app/api/websocket_handoff.py`):** Authenticates at connection setup only. Comment claims `_authenticate_token()` is called per-message, but it is not.
- **No revocation registry:** No mechanism to identify which SSE/WebSocket sessions correspond to a revoked token/user and close them proactively.

### Evidence

- File: `backend/app/api/run_stream.py:stream_run_events()` — authenticates before `with get_db()`, then yields indefinitely without re-checking
- File: `backend/app/api/websocket_handoff.py::websocket_handoff()` — comment at line ~40 says "re-authenticate per message" but call site is absent
- File: `backend/app/core/dependencies.py::get_current_user_with_payload()` — called once at stream setup, never again
- File: `backend/app/core/identity.py::_local_admin_credential_is_permitted()` — only checked at login, not per-request
- File: `backend/app/api/auth.py::logout()` — revokes token and calls Cognito `RevokeToken`, but does not close associated SSE/WebSocket sessions

### Revocation Paths That Don't Terminate Streams

| Event | Effect | Stream Survives? |
|-------|--------|------------------|
| Logout (`POST /api/auth/logout`) | Inserts `revoked_tokens` row, calls `RevokeToken` | ✓ Yes |
| Password reset | Sets `tokens_valid_from`, signs out globally | ✓ Yes |
| Role removed | Updates Cognito group, global sign-out | ✓ Yes |
| Tier downgraded | Updates tier group, **no sign-out** | ✓ Yes |
| Access token expiry | Token.exp passed | ✓ Yes |
| Per-`jti` revocation | Inserted in `revoked_tokens` | ✓ Yes |

### Exploitation Scenario

1. User A with enterprise tier starts a long-running SSE stream
2. Org admin downgrades A to basic tier (removes enterprise group)
3. Stream continues reading/writing protected resources
4. A remains in the stream even though `can_run_pipeline(basic, ppt)` would reject them now
5. No 403 or connection close; stream simply continues

### Fix Scope

- **Immediate:** Add periodic revocation checks to long-lived streams (every 5–10 frames or every 30s)
- **Architecture:** Maintain a per-user/per-token session registry keyed by revocation events (logout, password change, role/tier update)
- **Handoff WebSocket:** Implement actual per-message `_authenticate_token()` call instead of comment-only
- **Graceful close:** Send terminal event before closing, so frontend knows why the stream ended

---

## P1 — Privilege Mutation: Non-Atomic Cognito/DB Updates Can Leave Stale Tokens Valid

**Severity:** P1 (privilege escalation during role change window)  
**Impact:** When a user's role or tier is updated, the backend mutates Cognito, globally signs out the user, and then updates the local `tokens_valid_from`. If any intermediate step fails, an offline-verified privileged token can remain usable with stale claims.

### Root Cause

No transactional boundary or saga pattern ensures Cognito mutation, revocation, and DB commit happen atomically. If Cognito calls succeed but the local `tokens_valid_from` update fails, a revoked Cognito session can still pass offline verification against the old cutoff.

### Code Evidence

- File: `backend/app/api/admin.py::update_user_role()` — lines ~220–250
  ```python
  # 1. Mutate Cognito (may fail)
  cognito.admin_add_user_to_group(...)  # or remove
  # 2. Global sign-out
  cognito.admin_user_global_sign_out(...)  # may fail
  # 3. Update local cutoff (may fail or be skipped on exception)
  db_user.tokens_valid_from = datetime.utcnow()
  session.commit()
  ```
- File: `backend/app/api/admin.py::update_user_tier()` — similar pattern
- File: `backend/app/core/identity.py::_resolve_tier_from_groups()` — no fallback if group resolution fails

### Partial Failure Scenarios

| State | Cognito | DB `tokens_valid_from` | Offline Token Verification | Impact |
|-------|---------|------------------------|--------------------------|--------|
| Initial (basic) | basic group | T0 | valid (T0) | ✓ Correct |
| During update to enterprise | ✓ enterprise added, ✓ global sign-out | T0 (NOT updated yet) | valid if iat < T0 | ✗ **Old basic token still works** |
| After DB commit | enterprise, signed out | T1 (updated) | invalid if iat < T1 | ✓ Correct |

### Tier Update Special Case

`update_user_tier()` removes only the **inferred** tier from the DB projection:

```python
# Remove the old tier group (from DB)
old_tier = user.tier  # e.g., "basic"
cognito.admin_remove_user_from_group(pool_id, user.email, f"tier_{old_tier}")

# Add the new tier group
cognito.admin_add_user_to_group(pool_id, user.email, f"tier_{new_tier}")
```

If a user somehow has **multiple** tier groups (data corruption, manual testing), only the DB-projected group is removed. Higher-precedence conflicting groups survive and still satisfy the tier check.

### Reproduction

1. User holds a valid access token with `iat=T0, exp=T_future, tier=basic`
2. Admin upgrades user to enterprise
3. During the upgrade, DB commits `tokens_valid_from=T1` but Cognito call fails (network, timeout, etc.)
4. Exception is caught, user is notified of partial failure
5. User immediately calls a restricted endpoint with the old token
6. Verification succeeds: `iat (T0) < tokens_valid_from (T1)` ← false, so token is still valid
7. Privilege escalation

### Fix Scope

- Use distributed transactions (Saga pattern) or a pre-flight validation before any mutation
- Batch Cognito calls with a dry-run first, or use conditional writes
- Never rely on DB-only invalidation for claims already in the token
- Consider short-lived tokens that are re-verified on every request instead of relying on offline verification windows
- Add transaction logging and alerting for partial-failure recovery

---

## P2 — Login Timing Enumeration: Unknown Emails Return Faster Than Known Ones

**Severity:** P2 (information disclosure, user enumeration)  
**Impact:** An attacker can determine whether an email exists in the system by measuring response time. Unknown emails return immediately (local DB miss), while known emails incur Cognito provider latency.

### Root Cause

`backend/app/api/auth.py::login()` checks the local DB first and returns a generic error early. This short-circuit reveals whether the email is registered, despite the generic error text.

```python
# Pseudo-code
def login(email, password):
    user = db.get_by_email(email)  # Local DB lookup
    if not user:
        return {"detail": "Invalid email or password"}  # Immediate return
    
    # If we reach here, attacker knows the email exists
    result = cognito.admin_initiate_auth(...)  # Provider latency
    ...
```

### Evidence

- File: `backend/app/api/auth.py:210–240` — early return on unknown email before Cognito call
- File: `infra/scripts/bootstrap-ec2.sh:121–123` — nginx rate-limit of 10/min on `/api/auth/login` provides bulk-abuse defense but does not erase timing difference

### Timing Measurements

| Request | Response Time (typical) |
|---------|------------------------|
| Unknown email (DB miss) | ~5ms (local DB lookup) |
| Known email (Cognito call) | ~500ms (provider latency) |
| Timing difference | 100x (easily detectable) |

### Mitigation in Place (Partial)

Nginx rate-limits `/api/auth/login` to 10 requests/minute per IP address, which defends against bulk enumeration. However, the timing oracle remains: an attacker can make a single request per minute per IP and slowly enumerate the user base.

### Fix Scope

- Perform both DB and Cognito checks unconditionally (or use constant-time patterns)
- Return at the same logical point regardless of whether the user exists
- Consider raising the per-IP rate limit or moving to account-based throttling

---

## P2 — Authentication PII in Logs: Unknown Email Addresses Are Stored

**Severity:** P2 (privacy, log retention risk)  
**Impact:** `core/auth_events.py` logs attempted login emails, including those for non-existent accounts. Over time, logs accumulate email addresses that may reveal user enumeration or social-engineering targets.

### Root Cause

`core/auth_events.py::log_auth_event()` emits login failure events with the raw email address. No hashing or keying is applied.

### Evidence

- File: `backend/app/core/auth_events.py` — `log_auth_event()` with email as plaintext
- File: `backend/app/api/auth.py::login()` — calls `log_auth_event()` on every login attempt
- File: `.planning/COGNITO-MIGRATION-PLAN.md§5.6` — event schema documented but PII redaction not specified

### Log Retention Risk

1. Unknown email attempts create log entries forever (no matching user to purge on account deletion)
2. Logs accumulate competitor's employee emails, social-engineering wordlists, etc.
3. If logs are breached or queried internally, attackers gain a list of attempted emails

### Fix Scope

- Hash or key the email in `log_auth_event()`; preserve only the hash for aggregation/alerting
- Add log retention policy (e.g., purge after 30 days)
- Consider alternative approaches: log only summary counters, not per-attempt emails

---

## P2 — Browser Token Storage: localStorage Vulnerable to XSS

**Severity:** P2 (credential theft via XSS)  
**Impact:** The JWT is stored in browser `localStorage`, which is accessible to any script running in the same origin. A stored-XSS sink can read the token and forge requests or steal it.

### Root Cause

`frontend/src/lib/api.ts::getToken()` / `setToken()` use `localStorage` without additional protection. Production environment mitigates with CSP and security headers, but the storage itself is script-readable.

### Evidence

- File: `frontend/src/lib/api.ts:20–33` — `TOKEN_KEY = "auth_token"; localStorage.getItem/setItem`
- File: `docs/_audit/section_3_1_auth.md:C5` — audit notes CSP allows both `'unsafe-inline'` and `'unsafe-eval'`, which substantially weaken XSS containment
- File: `infra/scripts/reconcile-host-config.sh:235` — production CSP is:
  ```
  script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com
  ```

### XSS Attack Scenario

1. Attacker injects a stored-XSS sink (comment, workflow name, etc.)
2. Sink executes on victim's dashboard
3. `localStorage.getItem('auth_token')` returns the bearer
4. Attacker's script sends it to attacker's server
5. Attacker forges requests as the victim

### CSP Weakness

The CSP allows `'unsafe-inline'` and `'unsafe-eval'` together, which defeats most XSS containment. A stored-XSS sink can execute arbitrary code without being blocked.

### Fix Scope

- **Short-term:** Remove `'unsafe-inline'` and `'unsafe-eval'` from CSP; use nonces or separate script files
- **Medium-term:** Use HttpOnly, Secure, SameSite cookies instead of localStorage
- **Long-term:** Implement BFF (Backend for Frontend) session pattern with opaque session IDs

---

## P2 — Infrastructure: Cognito & Threat Protection Defaults Are Opt-In

**Severity:** P2 (misconfiguration risk, rollout delays)  
**Impact:** Cognito module defaults to permissive settings (OPTIONAL MFA, ESSENTIALS tier, NO_ACTION threat protection). Feature tier and threat mode are not exposed in the foundation layer, requiring manual Terraform edits to enable security features.

### Configuration Defaults

| Setting | Default | Recommended | Gating |
|---------|---------|------------|--------|
| `cognito_mfa_configuration` | `OPTIONAL` | `ON` (post-cutover) | `cognito_enabled` |
| `feature_plan` | (not exposed) | `PLUS` (for threat protection) | Missing variable |
| `threat_protection_mode` | `NO_ACTION` (inferred) | `ENFORCED` or `AUDIT` | Not exposed/wired |
| `cognito_enabled` | `false` | `true` (per-env) | Developer opt-in required |
| `auth_provider` | `"local"` | `"cognito"` (post-cutover Phase 5 step 1) | Manual tfvars edit |
| `auth_allow_legacy_jwt` | `true` | `false` (Phase 5 step 8, after legacy tokens age out) | Manual tfvars edit |
| `break_glass_enabled` | `true` | `true` (keep always on) | ✓ Correct default |

### Wiring Gaps

1. **Feature plan not exposed:** The foundation layer has no `feature_plan` variable, so `ESSENTIALS` is always used
2. **Threat protection not parameterized:** Even if feature plan were exposed, `threat_protection_mode` is not wired to the Cognito module
3. **Auth settings manual:** Cutover requires three separate manual edits to tfvars (Phase 5 steps 1, 8; Phase 6 step 1)
4. **SSM loading incomplete:** `AUTH_EMAIL_MFA_ENABLED` is published to SSM but omitted from the host-loader allowlist (`infra/scripts/bootstrap-ec2.sh:712`)

### Evidence

- File: `infra/terraform/foundation/variables.tf` — no `feature_plan` or `threat_protection_mode`
- File: `infra/terraform/modules/cognito/variables.tf` — `threat_protection_mode` defaulted but not used
- File: `infra/terraform/modules/secrets/main.tf:318–355` — SSM parameters for auth settings; `AUTH_EMAIL_MFA_ENABLED` **is** written
- File: `infra/scripts/bootstrap-ec2.sh:712` — loader allowlist omits `AUTH_EMAIL_MFA_ENABLED`, `ADMIN_MFA_REQUIRED`, and potentially other emerging auth flags
- File: `infra/terraform/foundation/prod.tfvars` — does not enable Cognito; no documented override for prod
- File: `.planning/COGNITO-MIGRATION-PLAN.md` — Phase 6 runbook mentions `AUDIT` and `ENFORCED` but they cannot currently be selected

### Fix Scope

- Expose `feature_plan` and `threat_protection_mode` as foundation-layer variables
- Wire threat protection through the Cognito module instantiation
- Add `AUTH_EMAIL_MFA_ENABLED` and `ADMIN_MFA_REQUIRED` to the host-loader allowlist
- Document and automate the cutover runbook phases so manual tfvars edits are explicit gated steps with checklist confirmation

---

## P2 — Infrastructure: Committed Prod tfvars Does Not Enable Cognito

**Severity:** P2 (misconfiguration, unverified live behavior)  
**Impact:** The checked-in `infra/terraform/foundation/prod.tfvars` does not set `cognito_enabled = true`. Actual production Cognito configuration is unknown (external override, SSM injection, or not deployed yet).

### Evidence

- File: `infra/terraform/foundation/prod.tfvars` — lists only network/backup settings; no Cognito configuration
- File: `infra/terraform/foundation/dev.tfvars:29` — explicitly sets `cognito_enabled = true`
- File: `.planning/COGNITO-MIGRATION-PLAN.md` — production Cognito cutover is Phase 5 of a multi-phase runbook; current prod state unknown

### Risk

- If prod tfvars is canonical, production has not cut over to Cognito yet (and is using local auth)
- If prod values come from external overrides (TF_VAR_* env vars, CI/CD), they are not code-reviewed or audited
- If prod state has been deployed but not committed, this represents a critical documentation gap

### Fix Scope

- Either commit prod Cognito configuration with all security-hardened settings, or
- Document exactly how prod overrides are supplied (CI/CD step, operator runbook, etc.) so they can be audited
- Add a pre-deploy check ensuring Cognito is enabled and security flags are set correctly

---

## Summary: Test Results & Evidence

### Backend Tests — 112 Focused Core Auth Tests Passed

```
backend/tests/unit/test_cognito_verifier.py — PASSED
backend/tests/unit/test_group_role_resolution.py — PASSED
backend/tests/unit/test_token_validity_revocation.py — PASSED
backend/tests/unit/test_break_glass_invariant.py — PASSED
backend/tests/unit/test_email_mfa.py — PASSED
backend/tests/unit/test_logout.py — PASSED
backend/tests/unit/test_cognito_refresh_secret_hash.py — PASSED
Total: 112 passed, 0 failed
```

### Backend Authorization/Session Tests — Mixed (113 Passed, 17 Failed)

```
backend/tests/unit/test_rest_run_launch.py::test_launch_mints_run — PASSED (but injects _FakeUser with no tier)
backend/tests/unit/test_user_workflows.py — PASSED (raw tier check, not token-derived)
backend/tests/integration/test_handoff_api.py — 12 FAILED (stale register fixture, self-registration now 403)
Total: 113 passed, 17 failed, 1 skipped
```

### Frontend Tests — 23 Session/Auth Tests Passed

```
frontend/src/lib/api.refreshRetry.test.ts — PASSED (mocks impossible backend success)
frontend/src/lib/authRedirect.test.ts — PASSED
frontend/src/hooks/useRunStream.test.ts — PASSED
frontend/src/lib/api.test.ts — PASSED
Total: 23 passed, 0 failed
```

### Static & Build Checks

```
frontend npm run build — PASSED (compile, TypeScript, page generation)
backend uv run python -m compileall -q app agents — PASSED
Focused auth-adjacent ruff (auth files) — PASSED (except 3 unrelated run_commands.py hygiene issues)
Terraform fmt -check -recursive — PASSED
Terraform validate (app, shared, foundation, bootstrap) — PASSED
Checkov, Trivy, TFLint, Gitleaks — NOT RUN (tools unavailable)
Mocked Playwright auth — BLOCKED (no server at localhost:3000)
```

---

## What Passed: Strong Controls Retained

| Control | Evidence | Status |
|---------|----------|--------|
| Cognito RS256 + JWKS verification | `test_cognito_verifier.py` | ✓ Strong |
| Claim validation (issuer, kid, exp, sub, jti, client_id) | `test_cognito_verifier.py` | ✓ Strong |
| Group resolution (deterministic, fallback to basic) | `test_group_role_resolution.py` | ✓ Strong |
| Admin role from token groups | `test_group_role_resolution.py` | ✓ Strong |
| Per-token revocation (jti tracking) | `test_token_validity_revocation.py` | ✓ Strong |
| Blanket revocation (tokens_valid_from, password_changed_at) | `test_token_validity_revocation.py` | ✓ Strong |
| Single-local-admin break-glass invariant | `test_break_glass_invariant.py` | ✓ Strong |
| Cognito sub ≠ local user ID separation | Code review | ✓ Strong |
| HTTP ownership checks (owner-scoped queries, 404 for cross-owner) | `test_approve_review_ownership.py` | ✓ Strong |
| Cognito client secret stored as KMS-encrypted SSM SecureString | IaC review | ✓ Strong |
| Terraform remote state in S3 (encrypted, versioned) | IaC review | ✓ Strong |
| Nginx rate limits on login/register/refresh | IaC review | ✓ Strong |
| Nginx security headers (HSTS, CSP, nosniff, frame-options) | IaC review | ✓ Strong |

---

## What Was Not Verified

- Live Cognito pool, group, MFA, and threat-protection configuration
- Real challenge chains (temporary password, MFA selection, multiple factors)
- Live `RevokeToken` and global-sign-out behavior
- Actual deployed SSM values and host environment
- JWKS rotation during provider outages
- Handoff cross-owner assertions (blocked by stale test fixture)
- IaC and secret scanners (Checkov, Trivy, TFLint, Gitleaks not available)
- Manual assistive/browser/security testing
- Load testing and abuse scenarios

---

## Recommended Next Steps

1. **Immediate (before production):**
   - Disable or restrict sensitive admin mutations until MFA is bound to session proof
   - Add tier authorization to `launch_run()` and related endpoints
   - Test refresh-after-expiry end-to-end with real Cognito

2. **High priority:**
   - Implement session-bound MFA step-up with reauthentication and bearer revocation
   - Implement periodic revocation checks on long-lived streams
   - Fix Cognito/DB update atomicity (saga pattern)
   - Wire `ADMIN_MFA_REQUIRED` through Terraform, SSM, and loader

3. **Medium priority:**
   - Remove CSP `'unsafe-inline'` and `'unsafe-eval'` directives
   - Shift to HttpOnly session/refresh cookies (requires BFF architecture)
   - Implement constant-time login checks to erase timing enumeration
   - Hash/key attempted emails in auth logs

4. **Quality & Documentation:**
   - Commit or document prod Cognito configuration
   - Add `feature_plan` and `threat_protection_mode` to foundation layer
   - Fix stale handoff test fixture and rerun full ownership assertions
   - Run security scanners before release

---

## Assessment Metadata

- **Assessed by:** Kiro QA / /velocity-ai-test skill
- **Assessment type:** Read-only authorization and authentication controls review
- **Scope:** Cognito login, token verification, session lifecycle, authorization gates, IaC, frontend bearer storage
- **No files modified:** Yes (git status clean)
- **Workspace state:** commit `4585410e`, no uncommitted changes
- **Test execution:** 112 + 113 + 23 = 248 tests run (mixed results, see breakdown above)
- **Tool availability:** Terraform validation ✓, scanners unavailable, frontend dev server blocked

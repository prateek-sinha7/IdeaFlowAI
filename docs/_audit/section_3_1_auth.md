# Phase B Audit — §3.1 Auth + §B1

Scope: Auth workflows W01–W07 (register, login, logout, change-password, /me, WS auth gate, password-change blanket revoke) plus backend trace §B1. Phase A findings were taken as given; this pass searches for new issues.

Phase A confirmed (re-stated only to be explicit, not re-investigated here):
- WS `run_pipeline` / `cancel_pipeline` / `generate_questions` skip per-message token re-validation — see `backend/app/api/websocket.py:210`, `:243`, `:265`. Only the `user_message` branch (`:281`-`:285`) re-runs `_authenticate_token`, so the pipeline branch survives logout / password rotation for as long as the LLM stream is producing output.
- `?token=` WS query-param still accepted — `backend/app/api/websocket.py:134`.
- No rate-limiting on `/login` or `/register` — `backend/app/api/auth.py:25`, `:57`; no `slowapi`/middleware in `backend/app/main.py`.
- JWT in `localStorage` — `frontend/src/lib/api.ts:24`, `:28`, `:32`.
- `logout()` swallows errors — `frontend/src/lib/api.ts:47-60`.
- `router.push` vs `router.replace` inconsistency — `frontend/src/app/login/page.tsx:24` (push), `frontend/src/app/register/page.tsx:45` (push), `frontend/src/app/dashboard/page.tsx:51`, `:567` and `frontend/src/app/workflow/page.tsx:25` (replace).
- WS-pipeline-revocation integration test missing — only `backend/tests/unit/test_logout.py` exists; nothing in `backend/tests/` exercises a WebSocket against a revoked token.

The body of this report below is everything new.

## CRITICAL

### C1 — `decode_access_token` does not validate `iss` / `aud`, and `nbf` is never set
File: `backend/app/core/security.py:46-66`, `backend/app/core/security.py:82`
- `create_access_token` only sets `sub`, `exp`, `iat`, `jti`. No `iss`, no `aud`, no `nbf`.
- `decode_access_token` calls `jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])` with no `options=` or `audience=` argument. python-jose's defaults skip `aud`/`iss`/`at_hash`/`iat` checks (it only enforces `exp` when present). It will accept a signature-valid token from any audience.
- Consequence: if `SECRET_KEY` is ever reused across two Flowin environments (dev↔prod or a sibling internal service that uses the same SSM parameter — note `infra/modules/secrets/main.tf:104-122` puts the key under one logical path per environment, but operators commonly copy the dev key into local `.env` files), tokens cross-validate. Without `aud` we have no defence.

### C2 — JWT signing algorithm is HS256 + symmetric secret read into the application process
File: `backend/app/core/security.py:16`, `backend/app/core/security.py:46-66`
- `ALGORITHM = "HS256"`. Any compromise of `SECRET_KEY` (RCE on the EC2, leaked CloudWatch log, leaked SSM parameter, mis-scoped IAM session, container exfil) allows the attacker to forge arbitrary JWTs for every user. The only revocation mechanism is the per-jti `revoked_tokens` table — but the attacker can mint NEW JWTs with any `jti`, so revocation does not save you.
- RS256 / ES256 with the private key only on a signing service (or KMS-managed asymmetric key + `kms:Sign`) would mean a host compromise still cannot forge tokens for future logins.
- Token lifetime is 24 h (`backend/app/core/config.py:76`, `infra/modules/secrets/variables.tf:74-82`). 24h × HS256 × no audience claim means a stolen key gives the attacker 24 h of guaranteed valid tokens for arbitrary users + the ability to mint new ones at will.

### C3 — Default JWT lifetime is 24 hours, no idle timeout, no refresh-token rotation
File: `backend/app/core/config.py:76`, `backend/app/core/security.py:59`, `infra/modules/secrets/variables.tf:74-82` (default 12 h in TF; backend default 24 h — see below)
- A single 24 h JWT covers an entire workday. There is no refresh-token / sliding session pattern. A stolen JWT lives until the user explicitly logs out (revoking just that `jti`), changes their password (which blanket-revokes), or the 24 h `exp` passes.
- Also: the backend default (24 h, `config.py:76`) and the TF default (12 h, `variables.tf:78`) disagree. In dev the backend ships 24 h; in prod SSM the operator's TF apply writes 12 h; the on-host loader will overwrite the backend's default. But anyone running the backend without going through the bootstrap (`docker-compose` straight from the repo) gets the looser 24 h default. `[VERIFY]` whether the production env always goes through `bootstrap-ec2.sh`.

### C4 — `SECRET_KEY` is read from environment but the production loader uses `--with-decryption` and pipes the plaintext through `aws ssm get-parameters-by-path | while read … emit …`
File: `infra/scripts/bootstrap-ec2.sh:478-495`
- `aws ssm get-parameters-by-path … --with-decryption … --output text` returns the *plaintext* `SECRET_KEY` value. It is then written via `emit` into a host-side env file (the script context — line 482 routes `SECRET_KEY` to `emit "$rel" "$value"`).
- The resulting env file is read by the container as `EnvironmentFile=` or `--env-file=`. Anyone with `cat` on the host (cron-running operator, SSM session manager session, AWS Backup snapshot of the EBS volume `[VERIFY]` since `infra/modules/kms/main.tf:9` does encrypt the EBS volume — that *is* covered) can read it.
- More acute: SSM session manager + the EC2 instance role + the env file = a privileged path to the JWT signing key that does not require breaking KMS encryption at rest. Anything that can `ssm:StartSession` can `cat /etc/flowin/app.env`.
- Mitigation: rotate the SECRET_KEY at every `terraform apply`? No — `infra/modules/secrets/main.tf:116-121` explicitly `ignore_changes = [value]`, so the key is **never rotated** unless an operator does it manually. Rotation comment says "Rotate yearly" (`main.tf:106`) but nothing enforces or reminds.

### C5 — No CSP / security-header middleware on the FastAPI app itself
File: `backend/app/main.py:115-121`
- Only middleware is `CORSMiddleware`. There is no CSP, no X-Content-Type-Options, no Strict-Transport-Security, no Referrer-Policy applied by the FastAPI process.
- The nginx layer at `infra/scripts/bootstrap-ec2.sh:598-602` *does* set HSTS / X-Frame / nosniff / CSP / Referrer-Policy, but anyone hitting the backend directly (port-forward, internal call, dev mode without nginx, Docker exposed port) gets no protection. Defence in depth is missing — the API should set its own CSP/headers.
- Also the nginx CSP at `bootstrap-ec2.sh:602` allows `script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net` — `'unsafe-eval'` and `'unsafe-inline'` together mean a stored-XSS sink anywhere in the frontend can read the localStorage JWT (Phase A's localStorage finding); CSP does not save it.

## HIGH

### H1 — bcrypt is invoked with default `gensalt()` rounds (12) and the cleartext password is not pre-hashed → silent truncation at 72 bytes
File: `backend/app/core/security.py:28-29`, `:43`
- `bcrypt.gensalt()` default work factor is 12 (current OWASP guidance is 12 for bcrypt — this happens to be fine *today*) but the constant is implicit. Anyone reviewing the code cannot tell what rounds are in effect; a future Python `bcrypt` library change of the default would silently weaken / strengthen production hashes with no audit trail.
- Bcrypt truncates input to 72 bytes. A 72+ byte password is silently truncated. Verifying with `bcrypt.checkpw` likewise truncates. Result: two passwords that differ only past byte 72 are accepted as the same password. There is no `Field(max_length=…)` on `RegisterRequest.password` (`backend/app/models/schemas.py:16`) or `ChangePasswordRequest.new_password` (`backend/app/api/auth.py:148-149`), so users can submit 1 MB passwords that get silently truncated.
- Standard mitigation (pre-hash with SHA-256 before bcrypt, or use argon2id) is not in place. `requirements.txt` pulls in `passlib[bcrypt]==1.7.4` but the code uses raw `bcrypt`, ignoring passlib's truncation-warning machinery.

### H2 — Password policy is 8 characters, no complexity, no breach-list check, no history
File: `backend/app/models/schemas.py:16` (`Field(..., min_length=8)`), `backend/app/api/auth.py:173` (`len(new_password) < 8`)
- 8 chars with no char-class requirement means `password` and `12345678` pass.
- No haveibeenpwned / breach corpus check on register or change-password.
- No password-history table — a user can change to the same password they had before (and the change-password endpoint does not even check that the new password differs from the old one, see `backend/app/api/auth.py:165-185`).
- The frontend duplicates the rule (`frontend/src/app/register/page.tsx:19-22`, `frontend/src/components/settings/AccountSettings.tsx:40-42`) but adds nothing beyond length.

### H3 — No account-lockout / failed-attempt tracking on `/login`
File: `backend/app/api/auth.py:56-84`, `backend/app/models/user.py`
- The `users` table has no `failed_login_count`, no `locked_until`, no `last_failed_login_at`. The login handler does not consult anything. Combined with no rate-limiting (Phase A), an attacker can pound `/login` for any known email indefinitely.
- The 24h JWT also means that the first successful guess gives a long window of access.

### H4 — No email verification — anyone can register any email
File: `backend/app/api/auth.py:24-53`, `backend/app/models/user.py:18`
- `register` accepts any `EmailStr`-parseable address and immediately issues a JWT. No verification token, no `is_verified` column, no `verified_at`.
- Consequences: (a) victim's email can be hijacked to lock them out of signup (squat-registration); (b) password-reset flows that we *don't have yet* would have nothing to verify against; (c) audit / abuse-tracking has only a self-claimed email, which is unattested.

### H5 — `/api/auth/me`, login responses, and the registration response leak no password-change-required flag or session id, but ALSO bind no client fingerprint / origin
File: `backend/app/api/auth.py:50-53`, `:81-84`; `backend/app/core/dependencies.py:124-150`
- The JWT has no `ip`, no `ua`, no `device_id` claim. If the token is exfiltrated, it works from any IP / any UA. There is no "log me out of all sessions" UI either; the only way is to change password (which is OK as long as the user can be told they should).
- Acceptable trade-off for an MVP but worth flagging — many compliance frames (SOC2, ISO) require session-binding signals at this level.

### H6 — No audit log for auth events (register, login success, login failure, logout, password change)
File: `backend/app/api/auth.py` (whole file — `grep -n logger backend/app/api/auth.py` returns zero matches), `backend/app/core/dependencies.py` (same — only a docstring contains the word "signal")
- None of the auth endpoints emit a single `logger.info` / `logger.warning`. The only logging that occurs around auth is in `backend/app/api/websocket.py:137-140` (deprecation warning for `?token=`) and `:176` (open-event for WS connect). HTTP login/logout/register/change-password produce **no** server-side trace.
- Effect: after-the-fact incident response is blind. A successful credential stuffing run leaves no record.
- Even pre-SOC2 minimum: log `event, user_id, ip, ua, ts, outcome` for the five auth events. Currently we cannot answer "who logged in yesterday?" or "did Alice's account get hit by a password-spray?".

### H7 — Login error message is generic ("Invalid credentials") but user-existence is leaked by `/register`
File: `backend/app/api/auth.py:34-38`
- `/register` returns 409 with `detail = "Email already registered"`. Standard mistake: an attacker can enumerate registered emails. This is intentional from a UX standpoint, but pairs poorly with no rate-limiting + no MFA: a credential-stuffing run will use `/register` to filter the email list down to known-existent users before hitting `/login`.
- The frontend (`frontend/src/app/register/page.tsx:47-48`) reads the 409 and surfaces "An account with this email already exists", which is exactly the leak.

### H8 — `change_password` accepts a new password equal to the current one
File: `backend/app/api/auth.py:165-185`
- The handler verifies the current password (`:166-170`), validates `len(new_password) >= 8` (`:173-176`), then hashes and stores. Nowhere does it compare `new_password` to `current_password` and reject equality.
- A user can "change" their password to the same value, and the only side-effect is to stamp `password_changed_at`. That stamping is itself dangerous (it blanket-revokes ALL outstanding tokens, see `backend/app/core/dependencies.py:72-111`) — meaning an attacker who has stolen a token can call `/change-password` with `current_password == new_password` to invalidate every OTHER session for that user, including the legitimate user's own. The legitimate user is logged out and the attacker still holds a valid token (because their own `jti` and `iat` post-date the rotation).
- This is exploitable today.

### H9 — `change_password` issues NO replacement token and does not revoke the calling token
File: `backend/app/api/auth.py:152-185`
- The endpoint stamps `password_changed_at` to "now" and returns `{"message": "Password changed successfully"}`. The token used to make the call was issued BEFORE `password_changed_at`, so by the dependencies.py logic (`_check_password_change_revocation`, lines `:72-111`) it should now be considered revoked. But because `iat` is integer seconds (`backend/app/core/security.py:63-64` uses `now`, encoded into seconds by python-jose), and `password_changed_at` is `datetime.now(timezone.utc)` *with microsecond precision* (auth.py:182), the comparison at `dependencies.py:106` is `iat_seconds < pwd_changed_seconds` — strictly less than. The token whose `iat` second EQUALS the rotation second is accepted post-rotation. See the comment at `dependencies.py:78-88`.
- Net: the calling token survives the password change. Combined with H8 above, attacker-with-stolen-token can: (a) call /change-password with same password, (b) blanket-revoke every other session, (c) keep their own token because of the same-second equality rule.
- The endpoint should: (a) explicitly revoke the calling JWT's `jti`, (b) return a fresh JWT, or (c) require re-login after change.

### H10 — Frontend logs token presence to console — and bypasses logout-revoke when the WS detects a 4001 close
File: `frontend/src/hooks/useWebSocket.ts:70`, `:178`, `:128-136`
- `useWebSocket.ts:70` and `:178` `console.log(...localStorage.getItem("auth_token")...)`. These only log a "present"/"null" string, not the token itself, but they reveal session state through the browser devtools console (and through any third-party JS that hooks `console.log`).
- Worse: on WS close code 4001 (`:128-136`) the handler calls `clearToken()` and `window.location.href = "/login"` directly. It does NOT call `/api/auth/logout`. If a token was revoked server-side (e.g. password rotation, `cancel_pipeline` from another tab) and the frontend learns about it via this 4001 close, the corresponding `revoked_tokens` row already exists, so this is harmless for the revoked-tokens table. BUT — and this is the actual issue — when the WS closes 4001 because the *backend* observed expiry, the frontend drops the local token and redirects, but never sends `/logout` for the *other* paths a stale token might still flow through. If we later add a service worker or a background tab that holds the JWT, those tabs won't know.

### H11 — Logout endpoint accepts an expired token (idempotency) but does not log the attempt
File: `backend/app/api/auth.py:93-143`, `backend/app/core/dependencies.py:181-202`
- `get_user_for_logout` accepts already-revoked JWTs (deliberate). It does NOT log the attempt. A legitimate logout and a malicious replay of a stolen-but-revoked token are indistinguishable in the logs (and the logs don't exist anyway — see H6).
- Combined with no rate limit, an attacker can replay a stolen token at /logout to *probe* whether the token was previously revoked. The endpoint returns 204 in both "fresh revoke" and "already revoked" paths, so it's not directly exploitable for enumeration, but worth flagging that idempotency + no logging means "logout from a never-issued token" is silently a 401 (because the bearer scheme fails first) while "logout from a revoked token" is silently a 204.

### H12 — `_authenticate_token` (WS path) and `get_current_user_with_payload` (HTTP path) duplicate the password-change check; the two diverge on tzinfo handling
File: `backend/app/api/websocket.py:74-87`, `backend/app/core/dependencies.py:89-111`
- The HTTP path uses `_coerce_to_aware_utc` (dependencies.py:20-31) which handles `value.tzinfo is None` by `replace(tzinfo=timezone.utc)`.
- The WS path (`websocket.py:74-76`) does the same coercion inline. So far consistent.
- BUT the WS handler at `:78` checks `pwd_changed_at is not None and iat_raw is not None` then proceeds, while the HTTP path returns early at `dependencies.py:91-94` if either is None. Both end up with the same effective decision but the inline duplication invites drift. Any future change to the HTTP path that the WS path misses (e.g. a new claim check) creates a per-protocol auth gap, exactly the Phase-A WS-pipeline-revocation pattern repeating itself.

## MEDIUM

### M1 — `random_password` for `SECRET_KEY` uses `special = false`
File: `infra/modules/secrets/main.tf:18-22`
- 64-char `[a-zA-Z0-9]` is 380 bits of entropy by the comment's own math. Plenty. But the comment claims this is necessary because of "EnvironmentFile format used by systemd / docker-compose doesn't have to grapple with embedded quotes". That's a workaround for the secrets-loader writing values without proper shell quoting — a fragile coupling between the TF module and `infra/scripts/bootstrap-ec2.sh:478-495`. The fix is to quote in the loader; the TF module shouldn't have to weaken its character set.
- Not a security bug at 64 chars but flag for the next refactor.

### M2 — `aws_ssm_parameter` resources use `tier = "Standard"` for `SECRET_KEY`
File: `infra/modules/secrets/main.tf:111`
- Standard SSM parameters cap at 4096 bytes — fine for a 64-byte key. The issue is the lack of `ChangeTime` / value-history retention beyond the default that SSM keeps for free-tier Standard parameters (history grows but you can't `aws ssm get-parameter-history` for an arbitrary point in time after 100 entries are exceeded). For a key that's supposed to be rotated yearly with `lifecycle.ignore_changes = [value]`, you may want `Advanced` tier just for the longer history — `[VERIFY]` against your incident-response runbook.

### M3 — `kms-decrypt.json` allows `kms:Decrypt` on `*` for parameters under `/flowin/${environment}/*`, but does NOT enforce that decryption only happens via the SSM service principal
File: `infra/policies/kms-decrypt.json:6-14`
- The first statement (`DecryptSsmSecureStrings`) has `Resource = "${kms_key_arn}"` (good) and a `kms:EncryptionContext:PARAMETER_ARN` condition (good). But it does NOT set `kms:ViaService = ssm.<region>.amazonaws.com`. So if any other AWS service holds a value encrypted with the same key and the same encryption-context key, it could be decrypted via this statement. Other SSM-via paths (DecryptEbsViaEc2 at `:16-29`, DecryptBackupS3ViaService at `:31-44`) all do enforce `kms:ViaService`. The SSM statement is the odd one out.
- Defence-in-depth — current attack vector is narrow because the encryption context is parameter-ARN-scoped, but adding `kms:ViaService = ssm.<region>.amazonaws.com` costs nothing.

### M4 — KMS key policy does NOT explicitly authorise SSM service to encrypt/decrypt SecureStrings
File: `infra/modules/kms/main.tf:9-168`
- Statements exist for: root, EBS via service-linked role, CloudWatch Logs, SNS, S3, AWS Backup, plus arbitrary `additional_principals`. **None** allow `ssm.<region>.amazonaws.com` directly.
- This works today because SSM PutParameter with a customer-managed key uses the **caller's** credentials (the Terraform-runner / operator) to encrypt at write time, and the EC2 instance role with `kms-decrypt.json` decrypts at read time. So the SSM service principal never needs key access.
- BUT: if a future SSM feature (parameter-policy expiry, cross-account share, automated rotation) starts to require service-principal access, the missing grant will surface as a runtime denial. Worth a `[VERIFY]` against the SSM Parameter Store rotation feature you'll need for SECRET_KEY rotation.

### M5 — Lazy GC of `revoked_tokens` runs with probability 0.001 inside the request path
File: `backend/app/core/dependencies.py:114-122`, `backend/app/models/revoked_token.py:43-61`
- `_maybe_run_lazy_gc` runs `cleanup_expired_revocations(db)` with `random.random() < 0.001`. Two issues:
  - **Latency cliff**: the unlucky 1-in-1000 request pays the cost of a DELETE over potentially the full expired set. With many revoked tokens this is a multi-second tail on a request that should be 5 ms. No batching, no LIMIT.
  - **Drift on small-traffic deployments**: if the deployment sees <1000 authenticated requests in a JWT lifetime, the table grows monotonically. The 24 h `exp` makes this a slow leak, but on a low-traffic staging box it leaks.
- Comment correctly flags this for replacement with a sidecar/cron at scale (`revoked_token.py:50-52`), so already on the radar.

### M6 — `auth.py:117` defensively skips revocation when `jti` is missing — but `create_access_token` always emits one, so this is unreachable code (legacy tokens) — and it logs nothing
File: `backend/app/api/auth.py:117-118`
- "if the token somehow has no jti (legacy token issued before this change), there's nothing we can revoke." OK, but the comment is the only audit signal — no `logger.warning("logout with jtiless token user_id=…")`. If the path becomes reachable due to a future bug it will be invisible.

### M7 — `password_changed_at` is on the user row, but never set at registration → never rotates the initial token
File: `backend/app/models/user.py:24`, `backend/app/api/auth.py:24-53`
- At registration, `password_changed_at` is left NULL (`user.py:24`). The dependency `_check_password_change_revocation` returns early at `dependencies.py:91-94` when this is NULL. Fine.
- BUT: a user who registers and never rotates their password has no `password_changed_at` ever set. If you later want to force "all tokens issued before today are invalid" (security-incident response, mass-rotation), you have to UPDATE every user row, AND the integer-second precision rule (H9) means same-second issued tokens survive.
- Could be addressed by setting `password_changed_at = datetime.now()` at registration so the comparison is always meaningful.

### M8 — `EmailStr` validation is not normalised (case/whitespace) before duplicate check
File: `backend/app/api/auth.py:33-38`
- `db.query(User).filter(User.email == request.email)` is a literal equality. EmailStr does normalise whitespace but does NOT lowercase the local part (RFC-compliant — the local part is case-sensitive). However the practical world treats `Alice@example.com` and `alice@example.com` as the same address. The current code allows two distinct users with the same address differing only in case. Login lookup at `auth.py:64` has the same issue — a user who registered with `Alice@…` and tries to log in with `alice@…` gets 401.

### M9 — Race on signup: concurrent POST /register with the same email can produce a 500 instead of a deterministic 409
File: `backend/app/api/auth.py:32-44`
- The handler reads-then-inserts. Two concurrent registrations for the same email both pass the "no existing user" check, both call `db.add`, both `db.commit`. The unique index on `users.email` (alembic 0001 line 62, `unique=True`) makes the second commit raise `IntegrityError`. The handler does NOT catch this — it bubbles up as a 500. `register` already imports `IntegrityError` because of the related logout path, but `register` does not catch.
- Fix is trivial: catch IntegrityError around the commit and return 409. Risk is low (would require concurrent signups inside one DB-commit window) but worth a defensive try/except.

### M10 — `/api/auth/me` and other authenticated endpoints rely on `HTTPBearer()` whose default returns 403 (not 401) when the header is missing
File: `backend/app/core/dependencies.py:17` (`bearer_scheme = HTTPBearer()`)
- See `tests/unit/test_logout.py:151` — the test already acknowledges this: "tolerate either 401 or 403". The Bearer scheme defaults `auto_error=True` which returns 403. For a "you didn't authenticate" error the correct status is 401 with `WWW-Authenticate: Bearer`. Frontend won't distinguish, but it makes scraping logs harder ("how many 401s today?" undercounts unauth attempts).

## LOW

### L1 — Frontend `register/page.tsx` posts the password into a request body that *is* JSON, but uses `autoComplete="new-password"` only on register — on login it uses `current-password`. Good — but neither page enforces `inputmode=` / `maxlength=` so paste-bombing a multi-MB password is possible
File: `frontend/src/app/login/page.tsx:99-108`, `frontend/src/app/register/page.tsx:141-150`
- Add `maxLength={128}` to align with the server-side max-length cap recommended in H1.

### L2 — `/api/auth/logout` accepts an unauthenticated request as 401, but does not 401 on a fundamentally malformed token (it goes through HTTPBearer first which returns 401, then fails decode)
File: `backend/app/api/auth.py:93-143`, behaviour confirmed by `tests/unit/test_logout.py:147-151`.

### L3 — `users.email` is indexed with `unique=True` but the index is NOT case-insensitive (see M8)
File: `backend/alembic/versions/0001_initial_schema.py:62`
- A future migration adding a citext column / functional unique index `lower(email)` is needed.

### L4 — `User.id = uuid.uuid4()` (`backend/app/models/user.py:17`) is a random UUIDv4 — strong, but the JWT `sub` is this user id, so the user id leaks into every token. Combined with the `Authorization` header logging that nginx does by default (`bootstrap-ec2.sh` does not disable nginx access logging) the user id flows into access logs. Not catastrophic, but the JWT `sub` could be a separate opaque "session subject id" with a server-side mapping if you want to break the link.

### L5 — `frontend/src/lib/api.ts:18` uses `TOKEN_KEY = "auth_token"` — a predictable key name an XSS attacker can target without inspection. Cosmetic.

### L6 — `changePassword` in `frontend/src/lib/api.ts:352-370` re-implements the request boilerplate instead of going through `request<T>()`. Same shape, slightly different error path. Cosmetic but invites drift.

### L7 — `useWebSocket.ts:128-136` redirects to /login via `window.location.href = "/login"` which is a full page reload. Acceptable but inconsistent with Next.js's `router.replace("/login")` used elsewhere (Phase A's push/replace point applies here too — neither is wrong, but a mix is).

### L8 — `backend/app/api/auth.py` has zero type annotation on `db: Session = Depends(get_db)` parameters' return — minor; mypy strictness setting was probably not pinned. Confirmed at `:25`, `:57`, `:95`, `:154`.

## TF concerns

### TF1 — `SECRET_KEY` rotation has no automation, no operator reminder, no documented runbook step
File: `infra/modules/secrets/main.tf:104-122`
- `description = "JWT signing key. Rotate yearly; rotation logs all users out."`
- `lifecycle.ignore_changes = [value]` — so a fresh `terraform apply` will NOT regenerate, even if the operator deletes the random_password resource's state. The intent is "rotation is operator-driven", but there is no terraform-side, AWS-side, or documented-side notification: no SSM parameter-policy `expiration`, no CloudWatch alarm on key age, no CloudTrail metric filter on `kms:Decrypt` against the parameter ARN with a year-old encryption timestamp.
- Even if the operator never rotates, the same key signs JWTs for years. If the key was ever logged or leaked once, that exposure is permanent.
- Suggest: add an SSM `parameter_policies` block with `Expiration` set to one year + a `NoChangeNotification` event-bridge rule to alert before expiry.

### TF2 — `SECRET_KEY` SSM SecureString stores plaintext in Terraform state
File: `infra/modules/secrets/main.tf:104-122`
- `aws_ssm_parameter.app_secret_key` with `value = random_password.app_secret_key.result` → both the `random_password` resource and the `aws_ssm_parameter` resource will store the *plaintext* SECRET_KEY in the Terraform state file.
- If `backend.tf` for prod writes state to S3 with `kms_key_id` set (`[VERIFY]` from `infra/envs/prod/backend.tf`) this is encrypted at rest in S3, but anyone with `terraform state pull` access has cleartext access.
- Operators using this module need to pin Terraform state IAM policy and audit `state pull` calls.

### TF3 — KMS key is `multi_region = false`, `customer_master_key_spec = SYMMETRIC_DEFAULT`
File: `infra/modules/kms/main.tf:13-15`
- Single-region symmetric key. For DR (region failover) the SSM SecureStrings cannot be decrypted in another region. Acceptable for the current single-region eu-central-1 deployment, but flags any DR runbook that names a second region as recovery target. `[VERIFY]` against your DR plan.

### TF4 — `enable_key_rotation = true` on the KMS key (`kms/main.tf:12`) rotates the underlying KMS material, NOT the SSM parameter value
File: `infra/modules/kms/main.tf:12`
- This rotates AWS's data-key encryption, which is good for compliance, but the *SECRET_KEY itself* (the plaintext value stored in the SecureString) is unchanged. KMS rotation alone does not invalidate JWTs.
- The combined misimpression "we rotate keys" + "we don't actually rotate SECRET_KEY" should be documented in the audit trail.

### TF5 — `ssm-read.json` IAM permission allows `ssm:GetParameter*` over the whole `/flowin/${environment}/*` namespace
File: `infra/policies/ssm-read.json:7-15`
- The EC2 instance role can read EVERY parameter under that prefix — including the database password and the LangSmith API key. The application process running inside that role can therefore read anything the role can read; a code-injection / SSRF inside the backend can shell out to `aws ssm get-parameter --name /flowin/prod/SECRET_KEY` and exfiltrate the JWT signing key without touching disk.
- A tighter design uses parameter-specific IAM policies for each consumer (the bootstrap loader needs everything once at boot; the application process arguably only needs `BEDROCK_MODEL_ID` at request time). Current code reads everything at boot into env vars (`bootstrap-ec2.sh:478-495`) and the process has direct env access without needing further IAM. The IAM is broader than the runtime needs.

### TF6 — No CloudTrail data-events monitoring on the SSM parameter or KMS key
File: `infra/modules/secrets/main.tf` (no `aws_cloudtrail_event_data_store` / `aws_cloudwatch_event_rule`)
- A `GetParameter` for `/flowin/prod/SECRET_KEY` from anything other than the EC2 instance role should page somebody. Currently there is no alarm, no monitoring. CloudTrail captures the call (default management-events) but no actionable signal goes to the alert-email pipeline (`infra/modules/monitoring/`).
- Suggest: add an EventBridge rule on `eventName = GetParameter, requestParameters.name = /flowin/${environment}/SECRET_KEY, userIdentity.arn != <instance role ARN>` → SNS.

### TF7 — `random_password.app_secret_key.length = 64` — fine, but no `keepers` block. If the resource is replaced (e.g. operator runs `terraform taint`) the SSM parameter's `lifecycle.ignore_changes = [value]` means the new value would NOT propagate
File: `infra/modules/secrets/main.tf:18-22`, `:116-121`
- This is actually a desired interaction (defensive against tainting), but worth noting: a taint of `random_password.app_secret_key` is a no-op for the live system. The only way to rotate is to (a) regenerate manually, (b) `aws ssm put-parameter --overwrite`, (c) remove the lifecycle ignore. The path is not documented.

### TF8 — `infra/modules/secrets/outputs.tf` outputs only ARNs, not values (correct), but does NOT output `kms_key_id` so consumers can't recompose `kms:EncryptionContext:PARAMETER_ARN` without knowing the prefix
File: `infra/modules/secrets/outputs.tf:1-13`
- Minor — `parameter_path_prefix` is exposed, so downstream can build the ARN. Not a security issue, just makes the API of the module less self-contained.

---

## Summary of high-impact themes

1. **Auth telemetry is missing across the board.** Zero log lines in `auth.py` and `dependencies.py`. Combined with no rate-limiting (Phase A) the platform is invisible to credential-spray attacks. (H6 + Phase A.)
2. **Symmetric HS256 + 24 h JWTs + key reads into process env + no audience claim** make a single host compromise catastrophic. (C1, C2, C3, C4, TF5, TF6.)
3. **Password policy is minimal (8 chars, no complexity, no breach check, no history, no lockout)** — a textbook OWASP-Top-10 cluster. (H1, H2, H3, H8.)
4. **Password change has two exploitable quirks**: same-second-precision rule allows the calling token to survive (H9), and same-password "rotation" can be weaponised to log other sessions out (H8).
5. **Email is unverified and unnormalised** (H4, M8).
6. **SECRET_KEY rotation is documented but unwired** (TF1, TF4).
7. **Backend has no CSP / security-header middleware** so internal/dev requests bypass nginx's headers (C5).
8. **WebSocket auth gate duplicates HTTP logic inline**, inviting protocol-divergence drift (H12).

The Phase A findings remain valid as listed at the top; the new findings here add an order of magnitude more surface area, with C1–C5 being the high-impact items to address first.

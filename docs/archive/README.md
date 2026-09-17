# ARCHIVED — DO NOT USE FOR IMPLEMENTATION

This document describes the retired dual-provider (local + Cognito) design, including break-glass and bootstrap-admin, all of which were removed. Current design: docs/architecture/authentication-and-authorization.md. Current operations: docs/runbooks/.

## Archived Files

| File | Reason |
|------|--------|
| `2026-cognito-migration-plan.md` | Original migration plan with revoked decisions (Decision 12 break-glass, pre-JIT assumptions); superseded by Cognito-only implementation |
| `2026-cognito-cutover-runbook-old.md` | Dual-provider cutover procedure; obsolete after Cognito-only transition (bootstrap step, local-auth fallback, break-glass flow removed) |
| `2026-bootstrap-admin-setup.md` | Removed bootstrap feature (`bootstrap_admin.py`, `BOOTSTRAP_ADMIN_EMAIL`/`PASSWORD` SSM params, related CLI); first admin now created directly in Cognito pool |

## Why These Are Archived

- Local password authentication (`bcrypt`, `password_hash`) — **removed**
- HS256 token signing and dual-accept window — **removed**
- Bootstrap admin and `bootstrap_admin.py` script — **removed**
- Break-glass admin account and `create_break_glass_admin.py` script — **removed**
- `AUTH_PROVIDER`, `AUTH_ALLOW_LEGACY_JWT`, `BREAK_GLASS_ENABLED` SSM parameters — **removed**
- Admin recovery via local password — **removed**

## Current Implementation

- **Authentication:** Cognito `AdminInitiateAuth` + RS256 token verification via JWKS
- **Authorization:** `cognito:groups` (e.g., `flowin-admins`, `flowin-tier-enterprise`)
- **Provisioning:** Just-in-time on login or first token verification
- **Admin lifecycle:** Invite-only, disable-before-delete, last-admin protection via live group check
- **Recovery:** AWS-IAM-side operator action (`AdminSetUserPassword`, etc.) — see `docs/runbooks/admin-recovery.md`

For implementation guidance, read:
1. `docs/architecture/authentication-and-authorization.md` — current design and verification rules
2. `docs/runbooks/admin-recovery.md` — recovery scenarios
3. `docs/runbooks/cognito-cutover.md` — historical cutover procedure (informational)
4. `.kiro/steering/authentication-and-authorization.md` — agent implementation guidance

Do not follow procedures or configurations from the files in this directory.

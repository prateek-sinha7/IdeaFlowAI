---
id: TEST-1-3
type: test
status: done
area: [workflow, auth]
summary: >-
  1.3 Auth & seed user — PREREQUISITE GAP
source: .planning/TEST-REGISTER.md#1-3-auth-seed-user-prerequisite-gap
---

### 1.3 Auth & seed user — **PREREQUISITE GAP**

- JWT lives in `localStorage["auth_token"]`. Login: `POST /api/auth/login {email,password}` → `{token,user:{id,email,tier,is_admin}}` (24h). `GET /api/auth/me` returns the user. WS auth = subprotocol `["bearer.<jwt>","flowin.v1"]` (transitional `?token=<jwt>` still accepted; close code **4001** = expired → redirect `/login`).
- ⚠️ **Self-registration is 403-disabled** (`POST /api/auth/register` → 403). Users are **admin-only** via `POST /api/admin/users` (needs an existing admin JWT). **There is no seed script.** → **Playwright login needs an out-of-band pre-seeded user** (direct DB insert with `app.core.security.hash_password`, or a manually-bootstrapped admin who creates the test users). **Create at least 3 fixtures: a `basic`, a `pro`, and an `enterprise` user** (tier drives workflow entitlement — §3 TS-B).

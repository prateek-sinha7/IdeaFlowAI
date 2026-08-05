---
id: TEST-16
type: test
status: done
area: [auth]
summary: >-
  TS-A — Authentication, routing & tier entitlement
source: .planning/TEST-REGISTER.md#ts-a-authentication-routing-tier-entitlement
covers: [TS-A-01, TS-A-02, TS-A-03, TS-A-04, TS-A-05, TS-A-06]
---

### TS-A — Authentication, routing & tier entitlement

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-A-01 | Unauth redirect | GET `/` unauthenticated | 307/redirect to `/login`; `/dashboard` also bounces to `/login` | 🔴 |
| TS-A-02 | Login persists JWT | `POST`-style login via the form (pre-seeded user) | `localStorage["auth_token"]` set; lands on `/dashboard` `home`; `getByText("What would you like to build today?")` visible | 🔴 |
| TS-A-03 | WS connects w/ subprotocol | After login, observe the WS handshake | WS opens with subprotocols `["bearer.<jwt>","flowin.v1"]`; **no token in URL**; server echoes `flowin.v1` | 🔴 |
| TS-A-04 | JWT-expired logout | Force a 4001 close (expired token) | redirect to `/login`; banner/`lastError` `Your session has expired. Please log in again.` | 🔴 |
| TS-A-05 | Tier gating (basic) | Login as **basic** user, view CreationHub | `app_builder`/`migration`/`custom` rows are `disabled`, `opacity-60`, show `Requires Pro plan`/`Requires Enterprise plan`; clicking them does nothing | 🔴 |
| TS-A-06 | Tier gating (enterprise) | Login as **enterprise** user | All 6 rows enabled; `custom`+`migration` clickable; migration row shows `NEW` pill | 🔴 |

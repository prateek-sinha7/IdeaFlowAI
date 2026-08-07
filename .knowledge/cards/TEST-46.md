---
id: TEST-46
type: test
status: done
area: [backend, auth]
files:
  - backend/scripts/seed_test_users.py
summary: >-
  G2 — Seed users (hard prerequisite)
source: .planning/TEST-REGISTER.md#g2-seed-users-hard-prerequisite
---

### G2 — Seed users (hard prerequisite)

Registration is 403-disabled, user creation is admin-only, **no seed script exists**. Add `backend/scripts/seed_test_users.py` (direct insert via `app.core.security.hash_password`) creating `qa-basic@`, `qa-pro@`, `qa-enterprise@`, and an admin. Playwright `fixtures/auth.ts` logs in via `POST /api/auth/login` and stores per-tier `storageState`.

# Resolved: the suite could not authenticate for ~2 hours

**Found:** 2026-08-27, ~05:10, while verifying `19_toasts_and_dialogs`.
**Resolved:** the same session, once the real cause was understood.
Kept as a record because both causes are worth knowing about.

## The real cause: a second admin locks every admin out — D-31

`S-19-07` granted admin to `qa-pro@flowinqa.com` so it could assert the success
toast. The grant succeeded. Every request after it answered
`401 {"detail":"Invalid token"}`, and the client reported an **expired session**.

The server-side reason never reaches the client:

```json
{"auth_event":"break_glass_invariant_violated",
 "reason":"unexpected_local_admin_count","local_admin_count":2}
```

Two local admins violate the break-glass invariant, so `resolve_principal`
returns `None` for **every** local-admin credential — including brand-new ones.
`POST /api/auth/login` keeps answering 200 with a valid token; nothing that
token is used for will work.

The test's own cleanup could not run: it needed the admin session the grant had
just destroyed. Recovery was a direct database write:

```sql
update users set is_admin = false where email = 'qa-pro@flowinqa.com';
```

`S-19-07` now skips its grant and revoke rows. **No offline test may create a
second admin.** Full write-up in `DEFECTS-OBSERVED.md` as D-31.

## The red herring: two backends on port 8000

Real, and worth fixing, but not what broke the suite. For about ninety minutes
two uvicorn servers were listening on 8000:

| PID | Started | cwd | Bound to |
|---|---|---|---|
| 195 | 00:25:53 | `VELOCITY-AI-feat-impeccable-improvements/backend` | `127.0.0.1:8000` |
| 42333 | 03:32:05 | `VELOCITY-AI/backend` | `*:8000` |

Their `backend/.env` files differ in both `SECRET_KEY` and `DATABASE_URL`, so
requests split between two servers that could not read each other's tokens. PID
195 exited on its own and the collision went with it — but the 401s continued,
which is what finally pointed at the invariant instead.

**If sign-in fails again, check both:** `lsof -nP -iTCP:8000 -sTCP:LISTEN`
should list one server (plus its reload child), and
`select email from users where is_admin` should return exactly one row.

## State restored

The four seeded accounts match `seed_test_users.py` exactly: `qa-admin`
admin/enterprise, `qa-pro` pro, `qa-enterprise` enterprise, `qa-basic` basic.

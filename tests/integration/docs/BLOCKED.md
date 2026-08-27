# Blocked: two backends are sharing port 8000

**Found:** 2026-08-27, ~05:10, while verifying `19_toasts_and_dialogs`.
**Effect:** every test that signs in fails. The suite cannot be verified until
this is resolved. Nothing about it is caused by the tests.

## What is happening

Two uvicorn servers are listening on port 8000, from two different worktrees:

| PID | Started | cwd | Bound to |
|---|---|---|---|
| 195 | 00:25:53 | `VELOCITY-AI-feat-impeccable-improvements/backend` | `127.0.0.1:8000` |
| 42333 (+ child 49727) | 03:32:05 | `VELOCITY-AI/backend` (main checkout) | `*:8000` |

Their `backend/.env` files differ in **both** `SECRET_KEY` and `DATABASE_URL`.

Requests to `localhost:8000` are split between them, so:

```
POST /api/auth/login   -> 200, token signed with the MAIN checkout's SECRET_KEY
GET  /api/auth/me      -> 401 {"detail":"Invalid token"}
```

Ten consecutive login-then-verify pairs failed. A token minted directly with the
main checkout's `SECRET_KEY` is also refused, and `verify_credential` accepts
that same token when called in-process against the main checkout's settings —
which is only possible if the two calls are being answered by two processes.

The first backend was already running when this session started; the second
appeared at **03:32**, which is exactly when the suite stopped being able to
sign in. Everything committed before that point was verified green against a
single server.

## The fix

Stop one of them, then restart the other so it owns the port cleanly:

```sh
kill 42333            # or 195 — whichever backend is not the one you want
```

Neither process was started by this session, so neither has been touched here.

## State this session changed and put back

`S-19-07` granted admin to `qa-pro@flowinqa.com` and its cleanup could not run,
because the page had already stopped authenticating. The row was restored
directly:

```sql
update users set is_admin = false where email = 'qa-pro@flowinqa.com';
```

The four seeded accounts now match `seed_test_users.py` exactly —
`qa-admin` admin/enterprise, `qa-pro` pro, `qa-enterprise` enterprise,
`qa-basic` basic.

## What to do after the restart

```sh
sh tests/integration/scripts/run-all-offline.sh
```

`19_toasts_and_dialogs` is committed but **never ran green** — it is the one
module in the suite that has not been verified end to end. Everything from
`17_theme_and_tiers` backwards was verified before the collision.

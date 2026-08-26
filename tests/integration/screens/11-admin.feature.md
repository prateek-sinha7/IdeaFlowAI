# Feature: Admin dashboard

User management. Its own shell — no app nav, no account menu.

**Route:** `/admin`
**Screenshot:** `36-admin.png`
**Source:** `frontend/src/app/admin/page.tsx` (a static page, **not** the catch-all)

**Screenshots:** `09-admin/p48`

---

## Routing note

`/admin` is served by a static route that takes precedence over the `[...view]`
catch-all. Both `routes.admin()` and `parseViewPath`'s `admin` case are therefore
**unreachable dead code**, and both files say so in a comment. The screen is real;
the parser entry is documentation only.

Consequence for tests: `/admin` does not participate in the shared shell. It has
its own header (`ADMIN` badge, "VelocityAI · User Management"), its own
`← Back to app`, and its own `Logout`.

---

## What is on the screen

**H1** "Admin Dashboard".

**Stat tiles:** `TOTAL USERS 4`, `BASIC 1`, `PRO 1`, `ENTERPRISE 2`, `ADMINS 1`.

**Users table** — heading `Users <n>`, an `Add user` button, a search
(`input[name="admin-user-search"]`), and columns:

| Column | Content |
|---|---|
| USER | avatar initial, email, truncated id (`6b5d63ea…`) |
| PLAN | tier badge — `ENTERPRISE`, `PRO`, `BASIC` |
| RUNS | lifetime run count |
| ROLE | `ADMIN` or `User` |
| JOINED | date |
| ACTIONS | `button[aria-label="Delete <email>"]` |

**The signed-in admin's own row has no delete button.** Only the other three carry
`Delete <email>`. That is the self-action guard, and it is the highest-value
assertion on this screen.

---

## Two guards this screen must never lose

**FIX-310 — self-tier.** `update_user_tier` had no self-action guard: an admin
could change their own tier and got a 200. Its two siblings had one all along
(`admin.py:329` self-demote, `admin.py:616` self-delete); only the tier route was
missed. `git log -S'own tier'` is empty, so Requirement 5.9 was **written and
never built** — it never regressed because it never worked. There is no unit test
that would have caught it from the UI side.

**Role gating.** Only `is_admin` users may reach this surface at all. Three of the
four seeded accounts are not admins and must be refused.

---

## Resetting another user's password

`adminResetUserPassword` → `POST /api/admin/users/{id}/reset-password`.

**This is the ONLY reset path when the pool uses email MFA.** AWS disqualifies email
as an account-recovery channel whenever it is also a second factor, so
`/api/auth/forgot-password` correctly refuses in that configuration and the sign-in
screen has no "forgot password" link (see `09-settings` § Security).

| | |
|---|---|
| `permanent` | defaults to **false** |
| false → | a **temporary** password; the user must choose their own at next sign-in |
| true → | a permanent password the admin now knows |
| either way | the target's **existing sessions are revoked** |
| response | `requires_new_password_at_next_login` |

The default matters: with `permanent=false` **the admin never ends up knowing a live
credential for someone else's account**. That is a security property, not a
convenience, and it is what makes the `NEW_PASSWORD_REQUIRED` challenge in `01-auth`
reachable in normal operation.

---

```gherkin
Feature: Admin dashboard

  Background:
    Given I am signed in as "qa-admin@flowinqa.com" with is_admin true

  Scenario: The admin dashboard renders its own shell
    When I cold-load "/admin"
    Then I see the heading "Admin Dashboard"
    And I see an "ADMIN" badge and the subtitle "VelocityAI · User Management"
    And I see a "← Back to app" control and a "Logout" control
    And I do NOT see the main app nav (Home / Library / My Workflows)
    And I do NOT see the account menu

  Scenario: The stat tiles agree with the table
    When I cold-load "/admin"
    Then TOTAL USERS equals the number of rows in the users table
    And BASIC + PRO + ENTERPRISE equals TOTAL USERS
    And ADMINS equals the number of rows whose ROLE is "ADMIN"

  Scenario: Every user row carries its full record
    When I cold-load "/admin"
    Then each row shows an email, a truncated id, a plan badge, a run count, a role and a joined date

  # ---- The guards ----

  Scenario: An admin cannot delete their own account
    When I cold-load "/admin"
    Then no delete control exists for "qa-admin@flowinqa.com"
    And a delete control exists for each of the other users
    # admin.py:616. The absence of the control on your own row IS the guard's
    # visible half.

  Scenario: An admin cannot change their own tier
    When I cold-load "/admin"
    And I attempt to change my own row's plan
    Then the change is refused
    And my tier is unchanged after a reload
    # FIX-310. This is the one to write FIRST. update_user_tier shipped with no
    # self-action guard while its two siblings had one — Requirement 5.9 was
    # written and never built, so it never "regressed" and no test ever failed.
    # Assert the API's refusal, not just the control's absence: the UI may hide
    # the affordance while the endpoint still accepts the call.

  Scenario: An admin cannot demote themselves
    When I cold-load "/admin"
    And I attempt to remove my own ADMIN role
    Then the change is refused
    # admin.py:329.

  Scenario Outline: A non-admin cannot reach the admin dashboard
    Given I am signed in as "<email>" with is_admin false
    When I cold-load "/admin"
    Then I do not see the heading "Admin Dashboard"
    And I do not see any other user's email address

    Examples:
      | email                      |
      | qa-enterprise@flowinqa.com |
      | qa-pro@flowinqa.com        |
      | qa-basic@flowinqa.com      |
    # qa-enterprise is the important row: same tier as the admin, no admin flag.
    # It proves the gate is on the role, not on the tier.

  Scenario: An anonymous visitor cannot reach the admin dashboard
    Given I have no auth token
    When I cold-load "/admin"
    Then I do not see the users table
    And I end up on the sign-in screen

  Scenario: The admin API refuses a non-admin directly
    Given I hold a valid token for "qa-basic@flowinqa.com"
    When I call the admin users endpoint with that token
    Then the response is a 403
    # Drive the API, not the UI. A hidden route is not an access control.

  # ---- Ordinary operations ----

  Scenario: Search filters the users table
    When I cold-load "/admin"
    And I type "qa-pro" into the user search
    Then only matching rows remain
    When I clear the search
    Then all rows return

  Scenario: The account menu is the way in
    Given I am signed in as an admin
    When I open the account menu
    Then I see "Admin Dashboard"
    When I click it
    Then I land on "/admin"

  Scenario: A non-admin is not offered the entry point
    Given I am signed in as "qa-pro@flowinqa.com"
    When I open the account menu
    Then I do NOT see "Admin Dashboard"

  Scenario: Back to app returns to the main shell
    When I cold-load "/admin"
    And I click "← Back to app"
    Then I land back in the main application shell

  Scenario: Logout from the admin shell clears the session
    When I cold-load "/admin"
    And I click "Logout"
    Then the auth token is removed
    And I end up on the sign-in screen

  @destructive
  Scenario: Adding a user creates an account at the chosen tier
    When I cold-load "/admin"
    And I click "Add user"
    And I create a disposable user at tier "basic"
    Then that user appears in the table with plan "BASIC" and role "User"
    And TOTAL USERS increases by one
    And BASIC increases by one

  @destructive
  Scenario: Deleting a user removes them
    Given a disposable user exists
    When I cold-load "/admin"
    And I click "Delete <that user's email>"
    And I confirm
    Then that row is gone
    And TOTAL USERS decreases by one
    # Scope the delete by the target's email — the aria-label is
    # "Delete <email>", which is unique. Do not click by row index.

  @destructive
  @sourced
  @destructive
  Scenario: An admin resets another user's password to a temporary one
    Given I am an admin on "/admin"
    When I reset another user's password without marking it permanent
    Then the response reports requires_new_password_at_next_login
    And that user's existing sessions are revoked
    When that user next signs in
    Then they are challenged with NEW_PASSWORD_REQUIRED
    # The default is `permanent=false` SO THAT the admin never ends up knowing a
    # live credential for someone else's account. That is a security property.
    # It is also how the first-sign-in challenge in 01-auth is reached in normal
    # operation.

  @sourced
  @destructive
  Scenario: A permanent reset skips the challenge but is knowable
    Given I am an admin on "/admin"
    When I reset another user's password with permanent=true
    Then that user signs in with it directly, with no challenge
    And their existing sessions are still revoked
    # Recorded so the trade-off is explicit: convenience for the admin, at the
    # cost of the admin knowing a live credential. Prefer the default.

  @sourced
  Scenario: Admin reset is the only recovery path under email MFA
    Given the pool uses email as a second factor
    When a user requests a password reset via /api/auth/forgot-password
    Then it is refused
    # AWS disqualifies email as a recovery channel whenever it is also a second
    # factor. This is correct behaviour, not a bug — and it is why the sign-in
    # screen offers no "forgot password" link at all.

  Scenario: Changing another user's tier takes effect
    Given a disposable user at tier "basic"
    When I change their plan to "pro"
    Then their row shows "PRO"
    And signing in as that user offers the pro catalog
    # The end-to-end half: a tier change must actually change what they can run,
    # not just the badge.
```

## Notes for phase 2

- **Never run the destructive scenarios against the four seeded accounts.** They
  are the fixtures for every other feature file. Create and delete your own.
- The self-action guards must be asserted **at the API**, not only by the absence
  of a UI control. FIX-310's whole shape was a missing server-side check while the
  siblings had one — a UI-only test would have passed.
- `/admin` bypasses the catch-all, so nothing about the shared shell applies here.
  Give it its own page object.

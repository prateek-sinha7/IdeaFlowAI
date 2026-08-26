# Feature: Authentication

Sign-in is the only way into the product. Self-registration is disabled by design
— accounts are created by an administrator.

**Routes:** `/login`, `/login?expired=true`, `/register`
**Screenshots:** `01-auth/` — p01 login, p02 expired banner, p03 expired=1 (no banner), p04 register stub, p05 root redirect
**Source:** `frontend/src/app/login/page.tsx`, `frontend/src/app/register/page.tsx`

---

## The sign-in screen

Two panes. The left is a static marketing rail; the right is the form.

| Region | Content |
|---|---|
| Brand rail (left) | Hexaware logo, wordmark "VelocityAI" |
| Rail eyebrow | `AI DELIVERY, ORCHESTRATED` |
| Rail heading | "Ship faster with your agent workforce." |
| Rail body | "Compose, run, and review delivery workflows — every step traceable, every artifact yours." |
| Rail chips | `Audit trail`, `Role-based access`, `Invitation-only` |
| Form heading | "Welcome back" |
| Form body | "Sign in to continue building with your AI delivery agents." |
| Fields | `Email` (placeholder `you@example.com`), `Password` (placeholder `••••••••`) |
| Submit | `Sign in` |
| Footer | "Access is by invitation. Contact your administrator for an account." |

There is no "forgot password", no "sign up", and no SSO button. The footer text is
the entire account-recovery story.

**Selectors:** `input[type="email"]`, `input[type="password"]`,
`button:has-text("Sign in")`.

---

```gherkin
Feature: Signing in

  Background:
    Given the frontend is served at http://localhost:3000
    And the backend is served at http://localhost:8000

  Scenario: The sign-in screen renders for an anonymous visitor
    Given I have no auth token
    When I cold-load "/login"
    Then I see the heading "Welcome back"
    And I see an email field and a password field
    And I see a "Sign in" button
    And I see the text "Access is by invitation. Contact your administrator for an account."
    And I do NOT see any link offering to create an account

  Scenario: Signing in with valid credentials lands on the dashboard
    Given I have no auth token
    When I cold-load "/login"
    And I fill the email field with "qa-admin@flowinqa.com"
    And I fill the password field with the seeded password
    And I click "Sign in"
    Then the URL becomes "/dashboard"
    And an auth token is present in localStorage under the key "auth_token"
    And I see the heading "What would you like to build today?"

  # An admin lands on /dashboard like everyone else. Do not expect /admin —
  # the admin surface is reached from the account menu, not from login.
  Scenario: An administrator is not redirected to the admin surface
    When I sign in as "qa-admin@flowinqa.com"
    Then the URL becomes "/dashboard"
    And the URL is NOT "/admin"

  Scenario Outline: Every seeded tier can sign in
    When I sign in as "<email>"
    Then the URL becomes "/dashboard"
    And an auth token is present

    Examples:
      | email                      | tier       | admin |
      | qa-admin@flowinqa.com      | enterprise | yes   |
      | qa-enterprise@flowinqa.com | enterprise | no    |
      | qa-pro@flowinqa.com        | pro        | no    |
      | qa-basic@flowinqa.com      | basic      | no    |

  Scenario: Signing in with a bad password is refused
    When I cold-load "/login"
    And I fill the email field with "qa-admin@flowinqa.com"
    And I fill the password field with "not-the-password"
    And I click "Sign in"
    Then I remain on "/login"
    And no auth token is written to localStorage
    And an error is shown to the user

  Scenario: An expired session is explained on the sign-in screen
    When I cold-load "/login?expired=true"
    Then I see the text "Your session expired. Please sign in again."
    And I still see the email and password fields

  @defect
  # D-03. The banner is gated on the literal string "true". Any other truthy
  # value renders a plain sign-in screen with no explanation of why the user is
  # here. routes.login({expired:true}) always emits "true", so only a
  # hand-written or external link degrades. Recorded as-is; see DEFECTS-OBSERVED.
  Scenario: An expired-session link with a non-"true" value shows no banner
    When I cold-load "/login?expired=1"
    Then I do NOT see the text "Your session expired"
    And the screen is indistinguishable from a plain "/login"

  Scenario: Self-registration is closed and redirects to sign-in
    When I cold-load "/register"
    Then the URL becomes "/login"
    And I briefly see the text "Redirecting…"
    # register/page.tsx keeps the route alive rather than 404ing so cached
    # external links land somewhere sensible. It is a stub, not a screen.

  Scenario: The bare root is not a way in
    # Quirk `rootRedirect`: "/" redirects to /login unconditionally, regardless
    # of auth state. It is a routing bug, not a logout. Never treat "/" as home.
    Given I am signed in
    When I cold-load "/"
    Then the URL becomes "/login"
    And my auth token is still present in localStorage

  Scenario: An unauthenticated cold load of a protected screen is bounced
    Given I have no auth token
    When I cold-load "/dashboard"
    Then I am not shown the dashboard content
    And I end up on the sign-in screen

  Scenario: Signing out clears the session
    Given I am signed in
    When I open the account menu
    And I click "Log out"
    Then the auth token is removed from localStorage
    And I end up on the sign-in screen
```

## Notes for phase 2

- **Do not assert on the token's value**, only its presence. It is a bearer
  credential; a failing assertion would print it into CI logs.
- The dev password is `flowin-e2e-pass`, overridable via `E2E_BASE_PASSWORD`.
  Read it from the env in tests rather than hardcoding it.
- Sign-in is the slowest step in the suite. Prefer seeding the token directly into
  `localStorage` for scenarios whose subject is not authentication — but keep at
  least the scenarios above driving the real form, or the login path itself goes
  untested.

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

## Cognito auth challenges — an entire flow with no spec until sweep 7

Sign-in is not one form. `login/page.tsx` renders a `ChallengeForm` for five distinct
Cognito challenges, each with its own copy, reusing the same shell "so a challenge
never looks like a different app".

| Challenge | Title | Subtitle |
|---|---|---|
| `NEW_PASSWORD_REQUIRED` | *(first sign-in)* | "This is your first sign-in. Choose a permanent password to continue." |
| `SOFTWARE_TOKEN_MFA` | "Enter your authentication code" | "Enter the 6-digit code from your authenticator app." |
| `EMAIL_OTP` | "Check your email" | "We sent you a 6-digit code. Enter it below to finish signing in." |
| `SELECT_MFA_TYPE` | "Choose a verification method" | "How would you like to receive your code?" |
| `MFA_SETUP` | "Two-factor setup required" | "This account needs two-factor authentication set up before it can sign in. Contact your administrator to finish setup." |

Unknown kinds fall back to **"Additional verification required"**.

**Two traps:**

1. **`EMAIL_MFA` vs `EMAIL_OTP`.** The factor is `EMAIL_OTP` everywhere except the
   `SELECT_MFA_TYPE` answer, where Cognito expects `EMAIL_MFA`. The source calls this
   "Cognito's own asymmetry". One constant reused for both fails on exactly one step
   and looks like a backend bug.
2. **`MFA_SETUP` is a dead end by design.** It needs a three-call Cognito session
   chain the single-shot `/login/challenge` endpoint cannot express, and **the backend
   answers 501**. The UI renders the explanation rather than a code field that would
   collect a code and then fail.

`EMAIL_OTP` names the mailbox when Cognito reports one — "We sent a 6-digit code to
`<masked address>`" — because "Check your email" is unhelpful when the address on file
is not the one the user expected. AWS does the masking.

Controls: `input[name="mfa-factor"]` (one radio per choice), the code field, and a
submit reading **"Continue"** / **"Verifying…"**. There is a cancel path back.

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

  Scenario Outline: The bare root branches on whether a token exists
    Given I am "<state>"
    When I cold-load "/"
    Then the URL becomes "<lands>"

    Examples:
      | state       | lands      |
      | signed in   | /dashboard |
      | signed out  | /login     |
    # CORRECTED (C-3). An earlier sweep recorded this as an unconditional
    # redirect to /login and called it a routing bug. app/page.tsx is
    # `getToken() ? routes.home() : routes.login()`. The branch is on token
    # PRESENCE only — an expired or forged token still routes to /dashboard, and
    # the API 401 is what actually stops you.
    # It renders null while deciding, so wait for the settled URL, not the first
    # paint.

  Scenario: An unauthenticated cold load of a protected screen is bounced
    Given I have no auth token
    When I cold-load "/dashboard"
    Then I am not shown the dashboard content
    And I end up on the sign-in screen

  # ---------- Cognito challenges ----------

  @sourced
  Scenario: First sign-in demands a permanent password
    Given an account whose password must be changed
    When I sign in
    Then I am told this is my first sign-in
    And I am asked to choose and confirm a permanent password

  @sourced
  Scenario Outline: A code challenge asks for six digits
    Given an account challenged with "<challenge>"
    When I sign in
    Then I see the heading "<title>"
    And I am asked for a 6-digit code
    And the submit reads "Continue", and "Verifying…" while in flight

    Examples:
      | challenge          | title                          |
      | SOFTWARE_TOKEN_MFA | Enter your authentication code |
      | EMAIL_OTP          | Check your email               |

  @sourced
  Scenario: An email code names the mailbox it went to
    Given an EMAIL_OTP challenge whose delivery address Cognito reported
    Then the subtitle reads "We sent a 6-digit code to <masked address>"
    And the address stays masked
    # AWS masks it. Do not unmask it, and do not replace this with the generic
    # "Check your email" — the whole point is telling the user WHICH mailbox.

  @sourced
  Scenario: Choosing a verification method offers both factors
    Given a SELECT_MFA_TYPE challenge
    Then I see "Choose a verification method"
    And I can pick "Email me a code" or "Use my authenticator app"
    And each is a radio named "mfa-factor"

  @sourced
  Scenario: The email factor submits a different value than its challenge name
    Given a SELECT_MFA_TYPE challenge
    When I choose "Email me a code"
    Then the value submitted is "EMAIL_MFA"
    And the challenge it leads to is "EMAIL_OTP"
    # Cognito's asymmetry, flagged in the source. Reusing one constant for both
    # fails on exactly one step.

  @sourced
  Scenario: MFA setup is a dead end that explains itself
    Given an account challenged with MFA_SETUP
    When I sign in
    Then I see "Two-factor setup required"
    And I am told to contact my administrator
    And I am NOT offered a code field
    # The backend answers 501 for this path. A code field here would collect a
    # code and then fail — the explanation is the correct behaviour.

  @sourced
  Scenario: An unrecognised challenge still renders something usable
    Given a challenge kind the UI does not know
    Then I see "Additional verification required"
    And I am told to follow the prompt below

  @sourced
  Scenario: A challenge can be abandoned
    Given I am part-way through a challenge
    When I activate "Back to sign in"
    Then I return to the plain sign-in form
    And no partially-entered code or password is retained

  @sourced
  Scenario: A challenge looks like the sign-in screen, not a different app
    Given any challenge
    Then it renders inside the same shell as the sign-in form
    # Stated as intent in the source. A verification step that looks like a
    # different app reads as a phishing page — worth pinning.

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

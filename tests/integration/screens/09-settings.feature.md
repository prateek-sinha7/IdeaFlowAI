# Feature: Account settings

Five tabs behind `/settings/{tab}`, uniformly addressable.

**Routes:** `/settings/profile`, `/settings/ai-model`, `/settings/usage`,
`/settings/constitution`, `/settings/security`
**Screenshots:** `07-settings/` — p41 profile, p42 ai-model, p43 usage, p44 constitution, p45 security, p46 bare redirect

---

## Shared chrome

H1 "Account Settings", subtitle "Profile, model preference, usage limits, your
agent constitution and sign-in security."

| Tab | Testid | Route |
|---|---|---|
| Profile | `tab-profile` | `/settings/profile` |
| AI Model | `tab-model` | `/settings/ai-model` |
| Usage & Limits | `tab-limits` | `/settings/usage` |
| Constitution | `tab-constitution` | `/settings/constitution` |
| Security | `tab-security` | `/settings/security` |

The tab testids do **not** match their route segments (`tab-model` ↔ `ai-model`,
`tab-limits` ↔ `usage`). Map them explicitly.

**`/settings` with no tab lands on `/settings/profile`.** `parseViewPath` does
return `{screen:'unknown'}` for it — that much is true and commented in
`routes.ts` — but the page does not stop there: it redirects to profile. The
first sweep read the parser and wrote down that the user sees the 404. Captured
directly, they do not (`capture/p46-settings-bare-redirect.json`). Read the
parser for what it parses, never for what the user ends up seeing.

Security was once a standalone page. The page is gone; the URL stays so the tab is
addressable exactly like the other four. The source explains why: the standalone
page duplicated the chrome the settings surface already provides and split account
concerns across two navigation models.

### Security is second-factor management, and it had no spec until sweep 8

`SecuritySection` exists because the backend's MFA endpoints previously had **no
enrolment surface at all** — which made `ADMIN_MFA_REQUIRED` "a lockout switch rather
than a control, because the 403 it raises points at an endpoint no screen calls".

Two methods, deliberately asymmetric:

| Method | Row title | Control |
|---|---|---|
| Email codes (`EMAIL_OTP`) | **"Email codes"** | a **toggle** |
| Authenticator app (`SOFTWARE_TOKEN_MFA`) | **"Authenticator app"** | **none — status only** |

**The asymmetry is real, not a shortcut.** Cognito provisions no secret for email
codes (the mailbox is already the pool's verified sign-in identifier), so there is
nothing to display, scan or confirm — enabling it is a single preference write. TOTP
would need a wizard, and while `/api/auth/mfa/totp/associate` and `/verify` exist,
**this screen deliberately exposes no control for them**.

State comes from `status.factors` and `status.enabled`, modelled as a discriminated
union so "loaded but also erroring" is unrepresentable.

Two conditional messages:

- Neither method available and TOTP off → *"No two-factor methods are enabled for
  this environment yet. Contact your administrator if you need one."*
- Email available → *"Because sign-in codes go to your email address, password resets
  are handled by an administrator rather than by email."*

That second line is the **account-recovery story**, and it corrects what
`01-auth` used to imply. `/api/auth/forgot-password` exists but **correctly refuses**
when the pool uses email MFA: AWS disqualifies email as a recovery channel whenever
it is also a second factor. Admin reset is then the only path — see `11-admin`.

---

## Per tab

**Profile** — identity card (initials, plan, "Signed in to VelocityAI"), a
read-only `Email` field, a `Plan` field, then a `PASSWORD` block with `Current
password`, `New password`, `Confirm new password` and a `Change Password` button.
All three password fields are `input[type=password]` with no `name` — index or
label them.

**AI Model** — helper text: "The default reasoning model applied across all your
runs. Individual agents can still override this in the workflow composer."
`select[name="default-model"]` under a `PIPELINE MODEL` label, plus `Save`.
Options seen: System Default (Claude Haiku 4.5), Claude Haiku 4.5 · fast,
Claude Haiku 3.5 · fast, Claude Sonnet 4.5 · balanced, Claude Sonnet 4.6 · balanced,
Claude Sonnet 5 (US) · balanced, Claude Sonnet 4 · balanced,
Claude Opus 4.5 · powerful, Claude Opus 4.6 · powerful. Selecting one shows a
description ("Fastest and most cost-efficient. Great for high-volume tasks.").

**Usage & Limits** — plan name, "Your plan determines which deliverables you can
run and the features available to you.", `Manage plan`, then `DELIVERABLE ACCESS`:
Product Requirements, Presentation, Interactive Prototype, App Builder, Custom
Workflow, Platform Workflows, Mulesoft Migration, .NET Migration.

This list is the user-facing face of `TIER_PIPELINES`. Notably it does **not**
list the seven `ex_A*` fixtures, even though the enterprise tier is entitled to
them and they appear on the home catalog — a second inconsistency behind D-04.

**Constitution** — "Your constitution is prepended to every agent on every run.
Use it for standing instructions — tone, house rules, tech constraints, things you
never want to repeat." `textarea[name="constitution"]` labelled `Global
instructions`, a `0 / 4000 chars` counter, and `Save constitution`.

**Security** — "Add a second step to sign-in so a stolen password isn't enough on
its own." For a Cognito-managed account: "Not available for this account" /
"This account's credentials are managed outside the application, so two-factor
authentication is configured separately." No inputs, no buttons.

---

```gherkin
Feature: Account settings

  Background:
    Given I am signed in as "qa-admin@flowinqa.com" with tier "enterprise"

  Scenario Outline: Every tab is addressable by URL
    When I cold-load "<route>"
    Then I see the heading "Account Settings"
    And the "<tab>" tab is selected
    And that tab's panel is rendered

    Examples:
      | route                    | tab            |
      | /settings/profile        | Profile        |
      | /settings/ai-model       | AI Model       |
      | /settings/usage          | Usage & Limits |
      | /settings/constitution   | Constitution   |
      | /settings/security       | Security       |

  Scenario Outline: Clicking a tab pushes its URL
    Given I am on "/settings/profile"
    When I click the tab with testid "<testid>"
    Then the URL becomes "<route>"

    Examples:
      | testid            | route                  |
      | tab-model         | /settings/ai-model     |
      | tab-limits        | /settings/usage        |
      | tab-constitution  | /settings/constitution |
      | tab-security      | /settings/security     |
      | tab-profile       | /settings/profile      |
    # The testids do not match the route segments. tab-model ↔ ai-model and
    # tab-limits ↔ usage. Map them; do not derive one from the other.

  Scenario: A bare /settings lands on Profile
    When I cold-load "/settings"
    Then I land on "/settings/profile"
    And the Profile tab is selected
    # CORRECTED. parseViewPath does return `unknown` for a bare /settings, but
    # the page redirects to profile rather than rendering the 404. The first
    # sweep asserted the 404 from reading the parser alone. Assert the settled
    # URL, not the first paint — the redirect is client-side.

  # ---- Profile ----

  Scenario: Profile shows identity and plan, with email read-only
    When I cold-load "/settings/profile"
    Then I see my email address
    And the email field is marked read only
    And I see my plan
    And I see a "PASSWORD" section with three password fields
    And I see a "Change Password" button

  @destructive
  Scenario: Changing the password requires the current one and a confirmation
    When I cold-load "/settings/profile"
    And I submit a new password without the current one
    Then the change is refused
    When I submit a new password whose confirmation does not match
    Then the change is refused
    # Do not run this against a shared seeded account — it locks the fixture out
    # for every other scenario.

  # ---- AI Model ----

  Scenario: The model preference lists the available models
    When I cold-load "/settings/ai-model"
    Then I see a model selector named "default-model"
    And its options include a "System Default" entry
    And its options include Haiku, Sonnet and Opus tiers
    And I see the note that individual agents can override this in the composer

  Scenario: Selecting a model shows its description
    When I cold-load "/settings/ai-model"
    And I select a model
    Then a description of that model is shown
    And a "Save" button is available

  @destructive
  Scenario: Saving a model preference persists it
    When I cold-load "/settings/ai-model"
    And I select a model different from the current one
    And I click "Save"
    And I reload the page
    Then that model is still selected
    # Restore the original value in teardown.

  # ---- Usage & Limits ----

  Scenario: Usage shows the plan and its deliverable access
    When I cold-load "/settings/usage"
    Then I see my plan name
    And I see a "DELIVERABLE ACCESS" list
    And I see a "Manage plan" control

  Scenario Outline: Deliverable access reflects the tier
    Given I am signed in as "<email>"
    When I cold-load "/settings/usage"
    Then the deliverable access list includes "<included>"
    And it does not include "<excluded>"

    Examples:
      | email                      | included              | excluded         |
      | qa-basic@flowinqa.com      | Product Requirements  | Custom Workflow  |
      | qa-enterprise@flowinqa.com | Custom Workflow       |                  |
    # This list is the user-facing face of TIER_PIPELINES. It should not
    # contradict which cards the home catalog offers the same user — see D-04,
    # where it does: the ex_A* fixtures are launchable but not listed here.

  # ---- Constitution ----

  Scenario: The constitution editor enforces its limit
    When I cold-load "/settings/constitution"
    Then I see a textarea named "constitution"
    And I see a character counter with a 4000-character ceiling
    And I see a "Save constitution" button
    When I type into it
    Then the counter increases

  @destructive
  Scenario: A saved constitution persists across a reload
    When I cold-load "/settings/constitution"
    And I enter a distinctive instruction
    And I click "Save constitution"
    And I reload the page
    Then that instruction is still present
    # Clear it in teardown — the constitution is prepended to EVERY agent on
    # EVERY run, so a leftover fixture value contaminates every other scenario
    # in the suite.

  # ---- Security ----

  Scenario: MFA is unavailable for an externally-managed account
    When I cold-load "/settings/security"
    Then I see the explanation that credentials are managed outside the application
    And I see "Not available for this account"
    And no MFA enrolment control is offered
    # True for Cognito-backed accounts, which is every seeded QA user. If the
    # app ever supports local credentials, this scenario needs a second variant.

  @sourced
  Scenario: Security lists both second-factor methods
    When I cold-load "/settings/security"
    Then I see a method row titled "Email codes"
    And I see a method row titled "Authenticator app"
    And each row states whether it is active

  @sourced
  Scenario: Email codes are a toggle, not a wizard
    Given email MFA is available for my pool
    When I cold-load "/settings/security"
    Then "Email codes" offers a toggle
    And enabling it needs no secret, no QR code and no confirmation step
    # Deliberate, and explained in the source: Cognito provisions no secret for
    # email codes because the mailbox is already the pool's verified sign-in
    # identifier. There is nothing to display, scan or confirm.

  @sourced
  Scenario: The authenticator row offers no control at all
    When I cold-load "/settings/security"
    Then "Authenticator app" shows its status
    And it offers NO enrolment control
    # /api/auth/mfa/totp/associate and /verify both EXIST. This screen
    # deliberately does not call them — TOTP needs a wizard nobody has built.
    # Asserted so the absence stays a decision rather than becoming a bug report.

  @sourced
  Scenario: An environment with no methods says so
    Given neither email MFA nor TOTP is available
    When I cold-load "/settings/security"
    Then I see "No two-factor methods are enabled for this environment yet."
    And I am told to contact my administrator

  @sourced
  Scenario: Email MFA changes the account-recovery story
    Given email MFA is available
    When I cold-load "/settings/security"
    Then I am told password resets are handled by an administrator rather than by email
    # This is the whole recovery story, and it is why the sign-in screen has no
    # "forgot password" link. /api/auth/forgot-password exists but correctly
    # REFUSES in this configuration: AWS disqualifies email as a recovery
    # channel whenever it is also a second factor. See 11-admin for the path
    # that does work.

  @sourced
  Scenario: Security is a tab, not a page
    When I cold-load "/settings/security"
    Then the settings header, back affordance and tab strip are the parent's
    And this section renders body content only
    # The standalone page was removed because it duplicated that chrome and
    # split account concerns across two navigation models. The URL survives so
    # the tab stays addressable.
```

## Notes for phase 2

- **Password fields carry no `name`.** Select by label association or by index
  within the PASSWORD section; do not use a bare `input[type=password]`.
- Three tabs are destructive (profile password, model preference, constitution).
  Give them their own account or restore state in teardown. The constitution is
  the most contaminating — it is injected into every agent on every run.
- The tab testids are the stable handle; labels contain an ampersand
  ("Usage & Limits") that trips naive text matching.

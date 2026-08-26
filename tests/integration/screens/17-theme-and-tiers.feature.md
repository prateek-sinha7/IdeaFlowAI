# Feature: Theme and tier variants

Two cross-cutting dimensions that change what a user sees on screens already
specified elsewhere.

**Screenshots:** `59`–`62` (dark), `64`–`68` (tiers)

---

## Theme

Toggled from the account menu. The control is labelled **"Dark mode" in both
states** — it names the target, not the current theme — so its text is not a way to
read which theme is active.

| | |
|---|---|
| Attribute | `data-theme` on `<html>` |
| Light | `data-theme="light"`, body `rgb(240, 238, 231)` |
| Dark | `data-theme="dark"`, body `rgb(13, 13, 13)` |
| Persistence | survives reload, per browser profile |

Captured in dark: dashboard, run steps, composer canvas, library.

## Tiers

Four seeded accounts. The **role** gate (`is_admin`) is independent of the **tier**
gate — `qa-enterprise` has the same entitlements as `qa-admin` but no admin access,
which is what makes it the useful control.

| Account | Tier | Admin | Account menu | Admin route |
|---|---|---|---|---|
| qa-admin | enterprise | yes | 6 items | reachable |
| qa-enterprise | enterprise | no | 5 items | redirects to `/dashboard` |
| qa-pro | pro | no | 5 items | redirects |
| qa-basic | basic | no | 5 items | redirects |

**Observed lock matrix** (from `capture/64`, `67`, `68`):

| Card | basic | pro | enterprise |
|---|---|---|---|
| Generate product requirements | — | — | — |
| Pitch an idea | Pro | — | — |
| Pitch an idea (v2) | Pro | — | — |
| Build an interactive prototype | Pro | — | — |
| Build an end-to-end application | Pro | — | — |
| Compose a custom workflow | Enterprise | Enterprise | — |
| Retry Until It Passes | Enterprise | Enterprise | — |
| Branch by Language | Enterprise | Enterprise | — |
| Spanish Greeter | Enterprise | Enterprise | — |
| Dutch Greeter | Enterprise | Enterprise | — |
| Hand Off to Another Workflow | Enterprise | Enterprise | — |
| Ask a Human, Then Hand Off | Enterprise | Enterprise | — |
| Ask a Human, Then Decide | Enterprise | Enterprise | — |

(— = unlocked. Coming Soon cards carry no lock badge; they are gated separately.)

**Deliverable access** on `/settings/usage` per tier: basic lists Product
Requirements and Presentation; enterprise lists those plus Interactive Prototype,
App Builder, Custom Workflow, Platform Workflows, Mulesoft Migration and
.NET Migration.

Note the two lists disagree with the catalog: the seven `ex_A*` fixtures are
launchable for enterprise but appear nowhere in Deliverable Access (D-04).

---

```gherkin
Feature: Theme

  Scenario: Dark mode applies and persists
    Given I am signed in
    When I open the account menu and click "Dark mode"
    Then the root element's data-theme becomes "dark"
    And the page background becomes the dark surface colour
    When I reload the page
    Then data-theme is still "dark"

  Scenario: The theme control names the target, not the state
    Given the theme is dark
    When I open the account menu
    Then the control still reads "Dark mode"
    # It is not a state label. Read data-theme to know which theme is active;
    # a test that reads the menu text will always see "Dark mode".

  Scenario Outline: Every major surface renders in both themes
    Given the theme is "<theme>"
    When I cold-load "<route>"
    Then the page renders with the "<theme>" palette
    And no text is rendered in a colour matching its own background

    Examples:
      | theme | route                    |
      | dark  | /dashboard               |
      | dark  | /runs/{id}/steps         |
      | dark  | /workflows/ppt/canvas    |
      | dark  | /library                 |
      | light | /dashboard               |

  Scenario: Theme is a per-browser preference, not per-account
    Given I set dark mode as one user
    When I sign out and sign in as a different user in the same browser
    Then the theme is still dark
    # Persisted client-side. Reset it in teardown or every later screenshot in
    # the run is themed differently.


Feature: Tier and role gating

  Scenario Outline: The account menu reflects the role, not the tier
    Given I am signed in as "<email>"
    When I open the account menu
    Then it has <count> items
    And "Admin Dashboard" is "<admin>"

    Examples:
      | email                      | count | admin   |
      | qa-admin@flowinqa.com      | 6     | present |
      | qa-enterprise@flowinqa.com | 5     | absent  |
      | qa-pro@flowinqa.com        | 5     | absent  |
      | qa-basic@flowinqa.com      | 5     | absent  |
    # qa-enterprise is the control: same tier as the admin, no admin flag. It
    # proves the gate is on is_admin and not on entitlement.

  Scenario Outline: A non-admin is redirected away from the admin surface
    Given I am signed in as "<email>"
    When I cold-load "/admin"
    Then I land on "/dashboard"
    And no other user's email address appears anywhere on the page

    Examples:
      | email                      |
      | qa-enterprise@flowinqa.com |
      | qa-pro@flowinqa.com        |
      | qa-basic@flowinqa.com      |

  Scenario Outline: Deliverable access matches the tier
    Given I am signed in as "<email>"
    When I cold-load "/settings/usage"
    Then the plan reads "<plan>"
    And Deliverable Access includes "<includes>"

    Examples:
      | email                      | plan       | includes              |
      | qa-basic@flowinqa.com      | Basic      | Product Requirements  |
      | qa-enterprise@flowinqa.com | Enterprise | Custom Workflow       |

  @defect
  # D-04. Deliverable Access and the home catalog disagree for enterprise: the
  # seven ex_A* fixtures are launchable on the catalog but listed nowhere here.
  # One of the two surfaces is wrong about what the plan includes.
  Scenario: Deliverable Access omits workflows the catalog offers
    Given I am signed in as "qa-enterprise@flowinqa.com"
    When I cold-load "/dashboard"
    Then "Branch by Language" is launchable
    When I cold-load "/settings/usage"
    Then Deliverable Access does NOT mention it

  Scenario: Entitlement is enforced by the backend, not only the badge
    Given I hold a valid token for "qa-basic@flowinqa.com"
    When I request a launch of a pipeline my tier does not cover
    Then the backend refuses it
    # ISS-055 recorded a period where launch never checked entitlement at all
    # and any user could run any pipeline. The badge is presentation; this is
    # the control.

  Scenario: One user's runs are invisible to another
    Given "qa-pro@flowinqa.com" has runs
    When I cold-load "/runs" as "qa-basic@flowinqa.com"
    Then none of those runs are listed
    And opening one of their run URLs directly does not reveal its contents
```

## Notes for phase 2

- **Reset the theme in teardown.** It persists per browser profile and will silently
  theme every later screenshot in the run.
- The tier scenarios need four real sessions. Sign-in is the slowest step in the
  suite — seed tokens directly for everything except the auth feature file itself.
- `qa-enterprise` is the highest-value fixture in this file. It is the only account
  that separates *what you may run* from *what you may administer*.

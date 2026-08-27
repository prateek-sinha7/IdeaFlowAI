# Feature: Theme and tier variants

Two cross-cutting dimensions that change what a user sees on screens already
specified elsewhere.

**Screenshots:** `13-states/` — 59 dark dashboard, 60 dark run steps, 61 dark canvas, 62 dark library; 64, 65 basic, 67 pro, 68 enterprise non-admin

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

**There are four tiers, not three, and they are not a chain.** The admin
Create-User dialog offers Basic, Pro, Enterprise and **Hexaware**, and `hexaware`
is a first-class tier in both `entitlements.py` and `entitlements.ts`.

| Pipeline family | basic | hexaware | pro | enterprise |
|---|---|---|---|---|
| user_stories | ✓ | ✓ | ✓ | ✓ |
| ppt | ✓ | **✗** | ✓ | ✓ |
| prototype | ✗ | **✓** | ✓ | ✓ |
| app_builder | ✗ | ✗ | ✓ | ✓ |

`hexaware` sits *sideways*: it gains prototype over basic but **loses ppt**.
`UPGRADE_PATH` sends it straight to `enterprise`, skipping pro. Moving a user from
basic to hexaware therefore takes away their ability to make presentations.

`entitlements.py` says this is deliberate (KAN-161 / ISS-055 — a scoped tier for
deployments needing prototype + user_stories only). The gap is in these specs, not
in the code: everything below was written assuming a totally-ordered basic → pro →
enterprise ladder, and there is **no seeded hexaware account** to test against.
See D-16.

The **role** gate (`is_admin`) is independent of the **tier** gate —
`qa-enterprise` has the same entitlements as `qa-admin` but no admin access, which
is what makes it the useful control.

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

**The matrix has no `hexaware` column** because no hexaware account is seeded. From
`TIER_PIPELINES` it would sit between basic and pro on prototype and *below* basic
on ppt — the one column that would disprove "higher tier ⇒ more cards". Fill it in
once a fixture exists (D-16).

**Deliverable access** on `/settings/usage` per tier: basic lists Product
Requirements and Presentation; enterprise lists those plus Interactive Prototype,
App Builder, Custom Workflow, Platform Workflows, Mulesoft Migration and
.NET Migration.

Note the two lists disagree with the catalog: the seven `ex_A*` fixtures are
launchable for enterprise but appear nowhere in Deliverable Access (D-04).

---

```gherkin
Feature: Theme

  @S-17-01
  Scenario: Dark mode applies and persists
    Given I am signed in
    When I open the account menu and click "Dark mode"
    Then the root element's data-theme becomes "dark"
    And the page background becomes the dark surface colour
    When I reload the page
    Then data-theme is still "dark"

  @S-17-02
  Scenario: The theme control names the target, not the state
    Given the theme is dark
    When I open the account menu
    Then the control still reads "Dark mode"
    # It is not a state label. Read data-theme to know which theme is active;
    # a test that reads the menu text will always see "Dark mode".

  @S-17-03
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

  @S-17-04
  Scenario: Theme is a per-browser preference, not per-account
    Given I set dark mode as one user
    When I sign out and sign in as a different user in the same browser
    Then the theme is still dark
    # Persisted client-side. Reset it in teardown or every later screenshot in
    # the run is themed differently.


Feature: Tier and role gating

  @S-17-05
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

  @S-17-06
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

  @S-17-07
  Scenario Outline: Deliverable access matches the tier
    Given I am signed in as "<email>"
    When I cold-load "/settings/usage"
    Then the plan reads "<plan>"
    And Deliverable Access includes "<includes>"

    Examples:
      | email                      | plan       | includes              |
      | qa-basic@flowinqa.com      | Basic      | Product Requirements  |
      | qa-enterprise@flowinqa.com | Enterprise | Custom Workflow       |

  @S-17-08
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

  @S-17-09
  @defect
  # D-16. The tier lattice is not a chain, and nothing here tests that.
  Scenario: A hexaware user gains prototype and loses presentations
    Given a user on the "hexaware" tier
    When I cold-load "/dashboard"
    Then "Build an interactive prototype" is launchable
    And "Pitch an idea" is locked
    # This is the case that breaks every other scenario in this file. Basic can
    # make presentations; hexaware cannot. A test that assumes higher tier ⇒
    # superset of entitlements passes vacuously against basic/pro/enterprise
    # and is wrong about the one tier that matters.
    # BLOCKED: no hexaware account is seeded. Phase 2 needs one before this can
    # run — create it through the admin Create-User dialog, which offers the
    # tier, or extend the seed script.

  @S-17-10
  Scenario: The admin dialog offers every tier the backend knows
    Given I am signed in as an admin
    When I open "Add user" on "/admin"
    Then the plan select offers "basic", "pro", "enterprise" and "hexaware"
    # Guards the two TIER_PIPELINES maps and this select against drifting
    # apart. test_entitlement_parity already keeps the backend and frontend
    # maps in sync; nothing currently keeps the admin UI in sync with either.

  @S-17-11
  Scenario: Entitlement is enforced by the backend, not only the badge
    Given I hold a valid token for "qa-basic@flowinqa.com"
    When I request a launch of a pipeline my tier does not cover
    Then the backend refuses it
    # ISS-055 recorded a period where launch never checked entitlement at all
    # and any user could run any pipeline. The badge is presentation; this is
    # the control.

  @S-17-12
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

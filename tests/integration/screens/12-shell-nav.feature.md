# Feature: Application shell and navigation

The persistent chrome around every authenticated screen, and the two overlays it
owns.

**Screenshots:** `37-account-menu.png`, `38-notifications.png`
**Source:** `AppHeader` in `frontend/src/components/layout/`

---

## The header

| Element | Selector | Notes |
|---|---|---|
| Wordmark | text "VelocityAI" | |
| Home | `button` "Home" | → `/dashboard` |
| Library | `button` "Library" | → `/library` |
| My Workflows | `button` "My Workflows" | → `/workflows` |
| Running-pipeline badge | `button` `<Workflow> <done>/<total>` | e.g. `Pitch an idea (v2) 0/4`; only while a run is live |
| Notifications | `button[aria-label="Notifications"]` | |
| Account menu | `button[aria-label="Account menu"]` | |

Nav items are **buttons, not links** — there are no `<a href>` elements in the
header. Any test that enumerates navigation by anchor will find nothing.

The shell is absent on: `/login`, `/register`, `/admin`, `/workflows/{id}`, and the
two legacy wizards (`/create/ppt`, `/create/prototype`), which replace it with
`Back to dashboard`.

## Account menu

Six items, each `[role="menuitem"]`, inside one `[role="menu"]`:

`Account Settings` · `Analytics` · `Run History` · `Admin Dashboard` · `Dark mode` · `Log out`

`Admin Dashboard` appears **only** for `is_admin` users.

Quirks that matter: menu items are `[role="menuitem"]` elements, and plain text
clicks fail intermittently on them — `Analytics` and `Dark mode` most often. Find
by role + text and call `.click()` rather than guessing a route (`/history` is not
a route; it 404s).

## Notifications panel

Header "Notifications". Empty state: "No notifications yet" / "Pipeline completions
will appear here". The panel overlays the current screen without changing the URL.

## Theme

`Dark mode` toggles `data-theme` on `<html>` and persists across reloads in the
same browser profile.

---

```gherkin
Feature: Shell and navigation

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  Scenario: The header is present on every authenticated screen
    When I cold-load "/dashboard"
    Then I see "Home", "Library" and "My Workflows"
    And I see a Notifications control and an Account menu control

  Scenario Outline: Each nav item routes to its screen
    Given I am on "/dashboard"
    When I click "<item>"
    Then the URL becomes "<route>"
    And that screen renders

    Examples:
      | item         | route      |
      | Library      | /library   |
      | My Workflows | /workflows |
      | Home         | /dashboard |

  Scenario: Nav items are buttons, not links
    When I cold-load "/dashboard"
    Then the header contains no anchor elements
    # There are no <a href> nodes in the header. Enumerating nav by anchor
    # returns an empty list and a test built that way silently passes.

  Scenario: The active screen is indicated in the nav
    When I cold-load "/library"
    Then "Library" is shown as the current screen

  Scenario Outline: The shell is absent where it should be
    When I cold-load "<route>"
    Then the main nav is not rendered

    Examples:
      | route             |
      | /login            |
      | /admin            |
      | /create/ppt       |
      | /create/prototype |
    # The two wizards and the admin shell substitute their own back control.

  # ---- Account menu ----

  Scenario: The account menu lists its items
    When I cold-load "/dashboard"
    And I click the Account menu control
    Then a menu opens
    And it contains "Account Settings", "Analytics", "Run History", "Dark mode" and "Log out"

  Scenario: An admin additionally sees the admin entry
    Given I am signed in as an admin
    When I open the account menu
    Then I also see "Admin Dashboard"

  Scenario: A non-admin does not
    Given I am signed in as "qa-pro@flowinqa.com"
    When I open the account menu
    Then I do NOT see "Admin Dashboard"

  Scenario Outline: Each menu item routes correctly
    When I open the account menu
    And I click the menu item "<item>"
    Then the URL becomes "<route>"

    Examples:
      | item             | route             |
      | Account Settings | /settings/profile |
      | Analytics        | /analytics        |
      | Run History      | /runs             |
      | Admin Dashboard  | /admin            |
    # Quirks `runHistoryMenuitem` and `accountMenuItemClickability`: these are
    # [role="menuitem"] elements and a plain text click fails intermittently,
    # Analytics worst of all. Locate by role + exact text and call .click().
    # There is no "/history" route — do not guess one; it 404s.

  Scenario: Escape closes the account menu
    When I open the account menu
    And I press Escape
    Then the menu closes
    And the URL is unchanged

  # ---- Notifications ----

  Scenario: The notifications panel opens with an empty state
    When I cold-load "/dashboard"
    And I click the Notifications control
    Then I see "Notifications"
    And I see "No notifications yet"
    And I see "Pipeline completions will appear here"
    And the URL is unchanged

  Scenario: A completed run produces a notification
    Given a run of mine has just completed
    When I open the notifications panel
    Then that completion is listed

  # ---- Running-pipeline badge ----

  Scenario: A live run surfaces in the header with its progress
    Given I have a run in progress
    When I cold-load "/dashboard"
    Then the header shows a badge naming that workflow
    And the badge shows completed-of-total agents

  Scenario: The badge opens the live run
    Given the header shows a running-pipeline badge
    When I click it
    Then I land on that run's surface

  Scenario: The badge is absent when nothing is running
    Given I have no run in progress
    When I cold-load "/dashboard"
    Then no running-pipeline badge is shown

  # ---- Theme ----

  Scenario: Dark mode toggles and persists
    When I open the account menu
    And I click "Dark mode"
    Then the root element's data-theme attribute changes
    When I reload the page
    Then the theme is still applied
    # Persisted per browser profile. Reset it in teardown or every subsequent
    # screenshot in the run is themed differently.

  # ---- Cross-cutting routing ----

  Scenario: Browser back and forward work across top-level screens
    Given I am on "/dashboard"
    When I navigate to "/library"
    And I navigate to "/workflows"
    And I press browser Back
    Then I am on "/library"
    When I press browser Forward
    Then I am on "/workflows"

  Scenario: Every top-level screen survives a hard refresh
    When I cold-load "/library?tab=hooks"
    And I reload the page
    Then the Hooks tab is still selected
    # Spec 015's core promise: every screen is addressable and cold-loadable.
    # Repeat this for /workflows, /runs, /analytics and each /settings tab.

  Scenario: An expired session sends me to sign-in with an explanation
    Given my auth token has expired
    When I click any nav item
    Then I land on "/login?expired=true"
    And I see "Your session expired. Please sign in again."
    # ADR-0019: session expiry is handled by ONE guarded fetch wrapper, not at
    # each call site. ADR-0024: on a 401 the REST client refreshes once first,
    # and only treats the session as expired when that refresh fails. So this
    # scenario needs a token that cannot be refreshed, not merely an expired one.
```

## Notes for phase 2

- Account-menu items need role-based location and a direct `.click()`. Text
  clicking is flaky on them — this is documented, not speculative.
- The running-pipeline badge is the only header element that depends on live state.
  Scenarios asserting its absence must ensure no other scenario left a run going.
- Dark mode persists per browser profile. Reset it in teardown.

# Feature: Home — the workflow catalog

The landing screen after sign-in. A data-driven grid of every workflow the signed-in
user's tier entitles them to launch, plus a locked "Coming Soon" section and a
"Jump back in" strip of recent runs.

**Routes:** `/dashboard`, `/create`
**Screenshots:** `02-home/` — p06 dashboard, p07 /create · `13-states/` — 64, 67, 68 (tier lock matrix)
**Source:** `HomeLaunchGrid`, fed by `GET /api/workflows`

---

## `/create` and `/dashboard` are the same screen

`initialMainViewFor` maps **both** `home` and `create` to the `MainView` `"home"`.
The file explains why: the `UXFIX-03`/`D-20` redesign — those are upstream design-doc
ticket ids, unrelated to this suite's `D-NN` defect numbering — folded the create catalog into
the home screen, and the `"catalog"` MainView member it would otherwise point at
has no render branch anywhere in the app. Mapping `/create` to `"catalog"` would
render a blank pane.

So the two URLs are interchangeable and the capture confirms it — identical H1,
identical card set. This is deliberate, not a bug, and phase 2 should assert the
equivalence so a future refactor cannot silently split them.

---

## What is on the screen

**Heading:** `What would you like to build today?` (H1), under an eyebrow `VELOCITYAI`.

**Launchable cards** (enterprise tier, 14 of them). Each card is a `<button>` whose
accessible name is the title + description + agent/duration estimate, and each has a
sibling `button[aria-label="Inspect <title> details"]`.

| Card | Description | Estimate |
|---|---|---|
| Build an end-to-end application | Full-stack code, tests, and infrastructure from a single requirement. | ~1 agents · ~33m |
| Retry Until It Passes | Smallest possible example of a conditional gate looping back to an earlier step. | ~4 agents |
| Branch by Language | Smallest possible example of a conditional gate picking one of three forward branches. | ~5 agents |
| Spanish Greeter | The plain workflow ex_A3_divert diverts into for the "spanish" outcome. | ~1 agents |
| Dutch Greeter | The plain workflow ex_A3_divert diverts into for the "dutch" outcome. | ~1 agents |
| Hand Off to Another Workflow | Smallest possible example of a conditional gate that stays in-run for one outcome and diverts to a separate workflow for the others. | ~3 agents |
| Ask a Human, Then Hand Off | A human chooses at a review gate which separate workflow the run hands off to. | ~3 agents |
| Ask a Human, Then Decide | Smallest example of a human choosing the branch at a review gate. | ~5 agents · ~1m |
| Pitch an idea | Executive-grade deck with charts, data, and a clear narrative. | ~3 agents · ~8m |
| Pitch an idea (v2) | Executive-grade deck, delivered as a rendered HTML deck and a real editable PowerPoint file. | ~4 agents · ~8m |
| Build an interactive prototype | Navigable, high-fidelity HTML prototype from a brief or story set. | ~2 agents · ~21m |
| Generate product requirements | Epics, user stories, and Gherkin acceptance criteria — ready for Jira. | ~7 agents · ~5m |
| Compose a custom workflow | Assemble specialist agents for tasks outside the standard pipelines. | ~9 agents · ~3m |

Rows 2–8 are the **spec-014 test fixtures** — see D-04. Their descriptions are
engineer-facing and one names an internal manifest id (`ex_A3_divert`) in
user-visible copy.

**Coming Soon** (H3), subtitle "Not yet available on any plan" — `.NET to Azure`,
`MuleSoft to Spring Boot`, `Reverse engineer a codebase`, `Sub-agents in parallel`.
These render as cards but are not launchable.

**Jump back in** — a strip of recent runs below the fold, each a button whose name
is `<STATUS> <age> <brief-excerpt> <workflow>`, e.g.
`WAITING_FOR_USER 2m ago Create a pitch deck…`, `DONE 1h ago hello Ask a Human, Then Decide`.

---

```gherkin
Feature: The home catalog

  Background:
    Given I am signed in as "qa-admin@flowinqa.com" with tier "enterprise"

  @S-02-01
  Scenario: The catalog renders on a cold dashboard load
    When I cold-load "/dashboard"
    Then I see the heading "What would you like to build today?"
    And I see a "Coming Soon" section
    And every launchable card has an "Inspect <title> details" button beside it

  @S-02-02
  Scenario: /create renders the identical catalog
    When I cold-load "/create"
    Then I see the heading "What would you like to build today?"
    And the set of launchable card titles equals the set shown at "/dashboard"
    # Both routes map to MainView "home" on purpose. Assert the equivalence so a
    # refactor cannot split them without a failing test.

  @S-02-03
  Scenario: Coming Soon cards are present but not launchable
    When I cold-load "/dashboard"
    Then I see "Reverse engineer a codebase" under "Coming Soon"
    And clicking it does not navigate away from "/dashboard"

  @S-02-04
  Scenario: A launchable card opens that workflow's launch surface
    When I cold-load "/dashboard"
    And I click the card "Generate product requirements"
    Then I land on a launch surface for "user_stories"
    And the surface names that workflow, not a different one

  @S-02-05
  Scenario: The inspect affordance opens details without launching
    When I cold-load "/dashboard"
    And I click "Inspect Pitch an idea details"
    Then I see details for that workflow
    And no run has been started

  @S-02-06
  # CORRECTED after the tier sweep (see DEFECTS-OBSERVED D-09). Cards are NEVER
  # hidden by tier — every card renders for every user, and entitlement shows as
  # a "Requires <Plan> plan" badge. The first draft of this file asserted absence,
  # which would have passed vacuously and tested nothing.
  Scenario: Every catalog card renders regardless of tier
    Given I am signed in as "qa-basic@flowinqa.com"
    When I cold-load "/dashboard"
    Then I see all 13 launchable card titles
    And the ones my tier does not cover carry a "Requires ... plan" badge

  @S-02-07
  Scenario Outline: The lock badge names the tier a card needs
    Given I am signed in as "<email>"
    When I cold-load "/dashboard"
    Then the card "<card>" shows lock "<lock>"

    Examples:
      | email                      | card                          | lock       |
      | qa-basic@flowinqa.com      | Generate product requirements | (unlocked) |
      | qa-basic@flowinqa.com      | Pitch an idea                 | Pro        |
      | qa-basic@flowinqa.com      | Compose a custom workflow     | Enterprise |
      | qa-pro@flowinqa.com        | Pitch an idea                 | (unlocked) |
      | qa-pro@flowinqa.com        | Build an end-to-end application | (unlocked) |
      | qa-pro@flowinqa.com        | Compose a custom workflow     | Enterprise |
      | qa-pro@flowinqa.com        | Branch by Language            | Enterprise |
      | qa-enterprise@flowinqa.com | Compose a custom workflow     | (unlocked) |
      | qa-enterprise@flowinqa.com | Branch by Language            | (unlocked) |
    # Source of truth is TIER_PIPELINES in BOTH frontend/src/lib/entitlements.ts
    # and backend/app/core/entitlements.py. test_entitlement_parity keeps them
    # equal; FIX-315 exists because they had drifted. This is the end-to-end half
    # of that guard. Full observed matrix: capture/64, 67, 68.

  @S-02-08
  Scenario: A locked card cannot be launched
    Given I am signed in as "qa-basic@flowinqa.com"
    When I cold-load "/dashboard"
    And I click a card badged "Requires Enterprise plan"
    Then no run is started
    And I am not taken to that workflow's launch panel

  @S-02-09
  Scenario: The backend refuses a launch the badge says is locked
    Given I hold a valid token for "qa-basic@flowinqa.com"
    When I POST a run for a pipeline my tier does not cover
    Then the response is refused
    # The badge is presentation. Assert the server enforces it too — ISS-055
    # recorded a period where launch never checked entitlement at all.

  @S-02-10
  @defect
  # D-04 / ISS-187. Recorded as current behaviour, NOT as correct behaviour.
  # If the fixtures are hidden from the catalog, rewrite this scenario to assert
  # their absence and drop the tag.
  Scenario: spec-014 test fixtures appear as launchable product cards
    Given I am signed in as "qa-enterprise@flowinqa.com"
    When I cold-load "/dashboard"
    Then I see the launchable card "Retry Until It Passes"
    And I see the launchable card "Branch by Language"
    And I see the launchable card "Spanish Greeter"
    And I see the launchable card "Dutch Greeter"
    And I see the launchable card "Hand Off to Another Workflow"
    And I see the launchable card "Ask a Human, Then Hand Off"
    And I see the launchable card "Ask a Human, Then Decide"
    And the description of "Spanish Greeter" contains the internal id "ex_A3_divert"

  @S-02-11
  Scenario: Jump back in lists recent runs and opens them
    Given at least one run exists for my account
    When I cold-load "/dashboard"
    And I scroll to the recent-runs strip
    Then each entry shows a status, an age, and a brief excerpt
    When I click the first entry
    Then I land on that run's detail surface
    And the URL contains that run's id

  @S-02-12
  Scenario: A live run is distinguishable from a finished one
    Given I have a run in state "waiting_for_user"
    When I cold-load "/dashboard"
    Then that run's entry shows the status "WAITING_FOR_USER"
    And a completed run's entry shows "DONE"

  @S-02-13
  @defect @unverified
  # D-10. The same card advertises a different agent count depending on whether
  # the signed-in user has a saved override of that built-in. qa-basic (no
  # override) sees "~15 agents"; qa-admin (override "My app_builder", 1 agent)
  # sees "~1 agents · ~33m" — and the duration did not scale with the count.
  # Possibly intended (the card predicts YOUR run), possibly a leak of per-user
  # state into a catalog estimate. Recorded, not judged.
  Scenario: A saved override changes the catalog card's agent estimate
    Given "qa-basic@flowinqa.com" has no override of "app_builder"
    And "qa-admin@flowinqa.com" has a 1-step override of "app_builder"
    When each signs in and cold-loads "/dashboard"
    Then qa-basic sees "Build an end-to-end application" reporting "~15 agents"
    And qa-admin sees the same card reporting "~1 agents"
```

## Notes for phase 2

- **The card set is data-driven** (`GET /api/workflows` filtered by entitlement).
  Do not hardcode the 14 titles as an exact-equality assertion — it will break
  every time a manifest is added. Assert on presence of specific cards, and on
  the tier-gating relationship, which is the actual invariant.
- Card buttons carry the whole card text as their accessible name, so
  `getByRole('button', { name: /Pitch an idea/ })` matches both "Pitch an idea"
  and "Pitch an idea (v2)". Anchor on the heading element or use an exact match.
- The recent-runs strip is **below the fold** at 1080p. Scroll before asserting.

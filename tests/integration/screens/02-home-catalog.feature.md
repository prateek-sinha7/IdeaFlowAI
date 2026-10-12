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
| Retry until it passes | A step that loops back and tries again until a check passes. | ~4 agents |
| Branch on a decision | An agent reads your message, picks a language, and the run follows that branch. | ~5 agents |
| Handoff target: Spanish reply | Where a branching workflow hands off when it picks the Spanish outcome. | ~1 agents |
| Handoff target: Dutch reply | Where a branching workflow hands off when it picks the Dutch outcome. | ~1 agents |
| Hand off to another workflow | Continues in the same run for one outcome and hands off to a separate workflow for the others. | ~3 agents |
| Let a reviewer choose the handoff | A person at a review gate picks which separate workflow the run hands off to. | ~3 agents |
| Let a reviewer choose the path | The run pauses at a review gate and a person picks which branch comes next. | ~5 agents · ~1m |
| Pitch an idea (Fast) | Executive-grade deck with charts, data, and a clear narrative. | ~3 agents · ~8m |
| Pitch an idea (Detailed) | Executive-grade deck, delivered as a rendered HTML deck and a real editable PowerPoint file. | ~4 agents · ~8m |
| Build an interactive prototype (Fast) | Navigable, high-fidelity HTML prototype from a brief or story set. | ~2 agents · ~21m |
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
    Given I am signed in as "admin@velocity.ai" with tier "enterprise"

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
    And I click "Inspect Pitch an idea (Fast) details"
    Then I see details for that workflow
    And no run has been started

  @S-02-06
  # CORRECTED after the tier sweep (see DEFECTS-OBSERVED D-09). Cards are NEVER
  # hidden by tier — every card renders for every user, and entitlement shows as
  # a "Requires <Plan> plan" badge. The first draft of this file asserted absence,
  # which would have passed vacuously and tested nothing.
  Scenario: Every catalog card renders regardless of tier
    Given I am signed in as "basic@velocity.ai"
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
      | basic@velocity.ai      | Generate product requirements | (unlocked) |
      | basic@velocity.ai      | Pitch an idea (Fast)                 | Pro        |
      | basic@velocity.ai      | Compose a custom workflow     | Enterprise |
      | pro@velocity.ai        | Pitch an idea (Fast)                 | (unlocked) |
      | pro@velocity.ai        | Build an end-to-end application | (unlocked) |
      | pro@velocity.ai        | Compose a custom workflow     | Enterprise |
      | pro@velocity.ai        | Branch on a decision           | Enterprise |
      | enterprise@velocity.ai | Compose a custom workflow     | (unlocked) |
      | enterprise@velocity.ai | Branch on a decision           | (unlocked) |
    # Source of truth is TIER_PIPELINES in BOTH frontend/src/lib/entitlements.ts
    # and backend/app/core/entitlements.py. test_entitlement_parity keeps them
    # equal; FIX-315 exists because they had drifted. This is the end-to-end half
    # of that guard. Full observed matrix: capture/64, 67, 68.

  @S-02-08
  Scenario: A locked card cannot be launched
    Given I am signed in as "basic@velocity.ai"
    When I cold-load "/dashboard"
    And I click a card badged "Requires Enterprise plan"
    Then no run is started
    And I am not taken to that workflow's launch panel

  @S-02-09
  Scenario: The backend refuses a launch the badge says is locked
    Given I hold a valid token for "basic@velocity.ai"
    When I POST a run for a pipeline my tier does not cover
    Then the response is refused
    # The badge is presentation. Assert the server enforces it too — ISS-055
    # recorded a period where launch never checked entitlement at all.

  @S-02-10
  # D-04 / ISS-187, resolved: the spec-014 test fixtures moved out of the product
  # grid into a collapsed "Engine examples" section (id prefix ex_/sample_/sc001).
  # They stay launchable; the internal id no longer appears in their copy.
  Scenario: spec-014 test fixtures are launchable under Engine examples
    Given I am signed in as "enterprise@velocity.ai"
    When I cold-load "/dashboard"
    And I open the "Engine examples" section
    Then I see the launchable card "Retry until it passes"
    And I see the launchable card "Branch on a decision"
    And I see the launchable card "Handoff target: Spanish reply"
    And I see the launchable card "Handoff target: Dutch reply"
    And I see the launchable card "Hand off to another workflow"
    And I see the launchable card "Let a reviewer choose the handoff"
    And I see the launchable card "Let a reviewer choose the path"
    And the description of "Handoff target: Spanish reply" does not contain the internal id "ex_A3_divert"

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
  # the signed-in user has a saved override of that built-in. basic@velocity.ai (no
  # override) sees "~15 agents"; admin@velocity.ai (override "My app_builder", 1 agent)
  # sees "~1 agents · ~33m" — and the duration did not scale with the count.
  # Possibly intended (the card predicts YOUR run), possibly a leak of per-user
  # state into a catalog estimate. Recorded, not judged.
  Scenario: A saved override changes the catalog card's agent estimate
    Given "basic@velocity.ai" has no override of "app_builder"
    And "admin@velocity.ai" has a 1-step override of "app_builder"
    When each signs in and cold-loads "/dashboard"
    Then basic@velocity.ai sees "Build an end-to-end application" reporting "~15 agents"
    And admin@velocity.ai sees the same card reporting "~1 agents"
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

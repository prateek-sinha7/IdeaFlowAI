# Feature: My Workflows

The user's saved workflows — custom compositions built from scratch, and overrides
bound to a built-in.

**Routes:** `/workflows`, `/workflows/{id}`, `/workflows/{id}/run`
**Screenshots:** `04-workflows/` — p15 list, p17 detail · `12-overlays/69` actions menu

---

## The list — `/workflows`

| Region | Content |
|---|---|
| Eyebrow / H1 | `VELOCITYAI` / "My Workflows" |
| Subtitle | "Your saved custom workflows — launch, manage and reuse them." |
| Stats | `<N> workflows`, `<N> total agents` |
| Search | `input[name="saved-workflows-search"]` |
| Primary action | `New workflow` |

Each card carries:

| Field | Example |
|---|---|
| Monogram | `MP` |
| Type badge | `PRESENTATION`, `CUSTOM`, `.NET → AZURE`, `MULESOFT → SPRING BOOT`, `APP BUILDER`, `PROTOTYPE`, `USER STORIES` |
| Title | "My presentation" |
| Description | "Your saved version of this workflow." |
| Agent count | `4 agents` |
| Age | `1h ago` |
| Actions | `button[aria-label="Workflow actions"]`, `Run workflow` |

**Two provenances are visible in the copy.** Overrides of a built-in say *"Your
saved version of this workflow."* and carry the built-in's type badge. Compositions
built from scratch carry the `CUSTOM` badge and their author's own description
(e.g. "5 gates, 3 nesting levels, 2 backward loops, 3 diverts, 14 nodes").

`Workflow actions` is **not unique** — one per card. Quirk `multipleIdenticalLabels`:
a bare click hits whichever matches first in DOM order. Always scope to the card by
its title.

## The detail view — `/workflows/{id}`

Minimal and read-only. No app shell nav in the capture.

| Region | Content |
|---|---|
| Type badge | `PRESENTATION` |
| H1 | "My presentation" |
| Description | "Your saved version of this workflow." |
| Roster | `4 AGENTS`, then the agent ids: report-generator, ppt-brief-analyst, ppt-composer, ppt-validator |
| Actions | `Edit`, `Run` |

The roster lists **agent ids**, not display names — the same steps render as
"Executive Reporting", "Presentation Strategist", "Deck Engineer", "Deck QA" on the
canvas. Both are correct views of one manifest; a test must not expect one on the
other's screen.

`initialMainViewFor` maps `workflow` to `saved-workflows`, with a note that no
MainView exists for the read view yet (data-model.md T4) — so it falls back to the
list rather than inventing one.

## The launch view — `/workflows/{id}/run`

Redirects into the **base workflow's launch panel**. For a ppt-based override this
is the full ppt wizard: `NEW PRESENTATION`, template gallery, `Advanced 3 agents`.

---

```gherkin
Feature: Saved workflows

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"
    And I own at least one saved workflow

  @S-05-01
  Scenario: The list renders with stats and a create affordance
    When I cold-load "/workflows"
    Then I see the heading "My Workflows"
    And I see the subtitle "Your saved custom workflows — launch, manage and reuse them."
    And I see a workflow count and a total-agent count
    And I see a "New workflow" button
    And I see a search input named "saved-workflows-search"

  @S-05-02
  Scenario: The stats agree with the cards
    When I cold-load "/workflows"
    Then the workflow count equals the number of cards
    And the total-agent count equals the sum of the cards' agent counts

  @S-05-03
  Scenario: Every card exposes its own actions
    When I cold-load "/workflows"
    Then each card shows a type badge, a title, an agent count and an age
    And each card has its own "Workflow actions" control
    And each card has its own "Run workflow" button

  @S-05-04
  Scenario: Search narrows the list by title
    Given I own a workflow whose title contains "presentation"
    When I cold-load "/workflows"
    And I type "presentation" into the search
    Then every visible card's title contains "presentation", case-insensitively
    When I clear the search
    Then the full list returns

  @S-05-05
  Scenario: New workflow opens the empty composer
    When I cold-load "/workflows"
    And I click "New workflow"
    Then I land on "/workflows/new"
    And the composer reports "0 agents"

  @S-05-06
  Scenario: A card opens its detail view
    When I cold-load "/workflows"
    And I open the card titled "<title>"
    Then the URL becomes "/workflows/{id}"
    And I see the heading "<title>"
    And I see its agent roster
    And I see "Edit" and "Run"

  @S-05-07
  Scenario: The detail view lists agent IDs, not display names
    Given a saved workflow whose base is "ppt"
    When I cold-load "/workflows/{id}"
    Then the roster lists agent identifiers such as "ppt-composer"
    And the roster does NOT list canvas display names such as "Deck Engineer"
    # Two views of one manifest. Assert the right vocabulary per screen.

  @S-05-08
  Scenario: Edit opens the composer bound to this row
    When I cold-load "/workflows/{id}"
    And I click "Edit"
    Then I land on "/workflows/{id}/edit"
    And the primary action is "Save workflow"
    And it is NOT "Save as copy"
    # A saved row is overwritable; a built-in is not. See 04-composer-canvas.

  @S-05-09
  Scenario: Run opens the base workflow's launch panel
    Given a saved workflow whose base is "ppt"
    When I cold-load "/workflows/{id}/run"
    Then I see the ppt launch panel with its template gallery
    And I see the eyebrow "NEW PRESENTATION"

  @S-05-10
  @unverified @defect
  # D-05. The row reports 4 agents; its run panel reports 3, which is the BASE
  # manifest's count. Whether the launch then runs 4 steps or 3 is unknown — the
  # capture sweep did not launch. If it runs 3, the override is ignored at launch
  # and this is serious. Phase 2 must settle it by launching and counting the
  # dispatched agents, not by reading the label.
  Scenario: A saved override's run panel reports the base agent count
    Given a saved workflow "My presentation" with 4 steps, based on "ppt"
    When I cold-load "/workflows/{id}"
    Then the roster reports 4 agents
    When I cold-load "/workflows/{id}/run"
    Then the panel reports "Advanced 3 agents"
    # THE ACTUAL QUESTION phase 2 must answer:
    #   When I launch from that panel
    #   Then the run dispatches 4 agents, not 3

  @S-05-11
  @destructive
  Scenario: A workflow can be deleted from its card menu
    Given I own a disposable saved workflow
    When I cold-load "/workflows"
    And I open the "Workflow actions" menu ON THAT CARD, scoped by its title
    And I click "Delete"
    And I confirm the deletion
    Then that card is gone from the list
    And the workflow count decreases by one
    # Scope the menu click by the card's unique title. "Workflow actions" repeats
    # once per card, and an unscoped click deletes the wrong workflow.

  @S-05-12
  @destructive
  Scenario: Running from a card starts a run of that workflow
    When I cold-load "/workflows"
    And I click "Run workflow" on a specific card, scoped by its title
    Then I reach a launch surface for that workflow
    And the surface names that workflow

  @S-05-13
  Scenario: An override can be reverted to the original built-in
    Given I own an override of the built-in "user_stories"
    When I open that built-in's launch surface
    Then my version is shown
    And a control is offered to use the original instead
    When I select the original
    Then the built-in's own steps are shown
    # Spec 016. Per user, per built-in. Only the STEPS are overridden —
    # deliverable, context providers, planner, clarify and limits always come
    # from the file manifest, on every run.
```

## Notes for phase 2

- **Never assert on the dev database's workflow list.** The capture saw 31
  workflows including stress-test rows ("BRUTAL 5 gates 3 levels deep"). Create
  your own fixtures and assert relatively (count before/after).
- The type badge is derived from `base_pipeline_type`. Rows built from scratch are
  `CUSTOM`; rows bound to a built-in carry that built-in's badge. That relationship
  is worth asserting — it is what makes an override recognisable in the list.
- `/workflows/{id}` renders without the app shell nav in the capture. If a test
  needs to navigate away from it, use the URL, not a nav link.

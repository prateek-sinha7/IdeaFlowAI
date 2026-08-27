# Feature: Launch panels

Where a brief is written and a run is started. There are **two different shells**
behind the `/create/*` URLs, and they do not look alike.

**Routes:** `/create/ppt`, `/create/prototype`, `/create/app`, `/create/user-stories`, `/create/{type}`
**Screenshots:** `03-create/` — p08 ppt, p09 prototype, p10 app (D-01), p11 user-stories, p12 catalog workflow, p13/p14 legacy redirects · `04-workflows/p20` saved-workflow launch · `13-states/` — 74, 75 (prototype tabs)

---

## Two shells

**Shell A — the wizard** (`/create/ppt`, `/create/prototype`). A stepped
configuration surface with a tab strip, a template gallery, and Back/Next.

`routes.ts` still carries a `workflowCreateLegacy` builder for the older path
`/workflow/create?mode=…`, with a comment saying FR-007/T17 retired it in favour
of the named routes and it is "kept as a builder until that redirect lands".
**That comment is stale — the redirect has landed.** Captured directly:
`/workflow/create?mode=ppt` → `/create/ppt`, `/workflow/create?mode=prototype`
→ `/create/prototype`. The named routes are the only ones that render.

**Shell B — the simple panel** (`/create/app`, `/create/user-stories`,
`/create/{type}`). `MainView` `"input"`. One brief textarea, an Advanced control,
a review-gates control, and a Run button. No tabs, no templates.

Phase 2 must not share a page object between them.

---

## Shell A — `/create/ppt`

| Region | Content |
|---|---|
| Eyebrow / H1 | `NEW PRESENTATION` / "Configure your presentation" |
| Section H2 | "Describe your presentation" |
| Brief | `textarea[name="brief"]` |
| Attachments | `+ Attach file` → `input[type=file]`, `Voice` |
| Agents | `Advanced 3 agents` (opens the agents modal) |
| Tabs | `Template` only — `[data-testid="tab-template"]` |
| Category pills | All, Pitch Deck, Business, Tech, Editorial, Creative, Minimal, Custom |
| Template search | `input[name="ppt-template-search"]` |
| Upload | `Upload custom` |
| Gallery | 52 templates, each labelled `<name> DECK`, footer "52 templates" |
| Gates | H2 "Review gates", subtitle "Optionally pause the pipeline for your review after specific agents.", current value `no gates` |
| Footer hints | "Add a brief", "Pick a template" |
| Actions | `Save workflow`, `Save as my version`, `Continue` |

## Shell A — `/create/prototype`

Same shape, different content and **three** tabs.

| Region | Content |
|---|---|
| Eyebrow / H1 | `NEW PROTOTYPE` / "Configure your prototype" |
| Section H2 | "Describe what you're building" |
| Agents | `Advanced 2 agents` |
| Tabs | `Template`, `Design System`, `Discovery` — testids `tab-template`, `tab-design-system`, `tab-discovery` |
| Category pills | All, Design, Marketing, Operations, Engineering, Product, Finance & HR, Custom |
| Template search | `input[name="template-search"]` (note: **not** the ppt one) |
| Gallery | 46 templates + a `No template / BLANK CANVAS` entry; each tagged `DESKTOP`, `MOBILE` or `AUTO` |
| Nav | `Back`, `Next` |
| Gates | `1 agent pause for review` — prototype ships with a gate on by default |
| Actions | `Save workflow`, `Save as my version`, `Continue` |

The two template search inputs have **different `name` attributes**. A shared
selector will silently match nothing on one of the two screens.

## Shell B — `/create/user-stories`, `/create/{type}`

| Region | Content |
|---|---|
| Eyebrow | The workflow's display name, uppercased — `GENERATE PRODUCT REQUIREMENTS`, `BRANCH BY LANGUAGE` |
| H1 | "Provide the brief" |
| Subtitle | The workflow's catalog description |
| Brief | `textarea[name="brief"]` |
| Attachments | `+ Attach file`, `Voice` |
| Agents | `Advanced <N> agents` — 7 for user_stories, 5 for ex_A2_branch |
| Gates | `Review gates no gates` |
| Actions | `Save workflow`, `Save as my version`, `Run workflow` |

The app shell (Home / Library / My Workflows nav, notifications, account menu)
stays visible on Shell B. Shell A replaces it with a `Back to dashboard` button.

---

```gherkin
Feature: Launching a workflow

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  # ---------- Shell A: the wizard ----------

  @S-03-01
  Scenario: The presentation wizard renders its template gallery
    When I cold-load "/create/ppt"
    Then I see the eyebrow "NEW PRESENTATION"
    And I see the heading "Configure your presentation"
    And I see a brief textarea named "brief"
    And I see a "Template" tab
    And I see the category pills "All", "Pitch Deck", "Business", "Tech", "Editorial", "Creative", "Minimal", "Custom"
    And I see a template search input named "ppt-template-search"
    And the gallery footer reports a template count

  @S-03-02
  Scenario: Filtering the template gallery by category narrows it
    When I cold-load "/create/ppt"
    And I note the number of template tiles
    And I click the category pill "Minimal"
    Then fewer template tiles are shown than before
    And every visible tile belongs to that category

  @S-03-03
  Scenario: Searching templates filters by name
    When I cold-load "/create/ppt"
    And I type "keynote" into the template search
    Then every visible template tile's name contains "keynote", case-insensitively

  @S-03-04
  Scenario: The prototype wizard offers three tabs and a blank-canvas option
    When I cold-load "/create/prototype"
    Then I see the eyebrow "NEW PROTOTYPE"
    And I see tabs "Template", "Design System", "Discovery"
    And I see a template tile "No template" tagged "BLANK CANVAS"
    And the review-gates control reads "1 agent pause for review"

  @S-03-05
  Scenario: The prototype template search uses its own field name
    When I cold-load "/create/prototype"
    Then a search input named "template-search" exists
    And no input named "ppt-template-search" exists
    # These two wizards do NOT share a search selector. Guard it here so a
    # phase-2 page object cannot quietly unify them.

  @S-03-06
  Scenario Outline: Each wizard tab reveals its own panel
    When I cold-load "/create/prototype"
    And I click the tab "<tab>"
    Then the panel for "<tab>" is shown
    And the other two panels are hidden

    Examples:
      | tab           |
      | Template      |
      | Design System |
      | Discovery     |

  # ---------- Shell B: the simple launch panel ----------

  @S-03-07
  Scenario: The user-stories panel names its own workflow
    When I cold-load "/create/user-stories"
    Then I see the eyebrow "GENERATE PRODUCT REQUIREMENTS"
    And I see the heading "Provide the brief"
    And I see the agent control "Advanced 7 agents"
    And I see the buttons "Save workflow", "Save as my version", "Run workflow"

  @S-03-08
  Scenario: A catalog workflow cold-loads onto the right panel
    When I cold-load "/create/ex_A2_branch"
    Then I see the eyebrow "BRANCH BY LANGUAGE"
    And I see the agent control "Advanced 5 agents"
    # This is the create-workflow branch of parseViewPath, which carries the raw
    # pipelineType through initialWorkflowTypeFor. It is the ONLY create route
    # that resolves its type correctly on a cold load — see the next scenario.

  @S-03-09
  @defect
  # D-01. /create/app is supposed to launch app_builder. It renders the
  # user_stories panel instead, because initialWorkflowTypeFor
  # (app/[...view]/page.tsx:307) returns a type only for `create-workflow`, so
  # the two hand-written screens reach the panel with no type and fall back to
  # the default. Written to today's behaviour so the fix turns this red.
  Scenario: Cold-loading /create/app shows the user-stories panel
    When I cold-load "/create/app"
    Then I see the eyebrow "GENERATE PRODUCT REQUIREMENTS"
    And I see the agent control "Advanced 7 agents"
    And the screen is identical to "/create/user-stories"
    # CORRECT behaviour, once fixed:
    #   Then I see the eyebrow "BUILD AN END-TO-END APPLICATION"
    #   And I see the agent control "Advanced 1 agents"

  # ---------- Shared behaviour ----------

  @S-03-10
  Scenario: Run is disabled until the brief is long enough
    When I cold-load "/create/user-stories"
    Then the "Run workflow" button is disabled
    When I type "Build a hello world service" into the brief
    Then the "Run workflow" button is enabled

  @S-03-11
  Scenario: The Advanced control opens the agent roster
    When I cold-load "/create/user-stories"
    And I click "Advanced 7 agents"
    Then a modal opens listing the workflow's agents
    And the number of agents listed matches the control's label
    When I press Escape
    Then the modal closes

  @S-03-12
  Scenario: Review gates can be set before launch
    When I cold-load "/create/user-stories"
    Then the review-gates control reads "no gates"
    When I open the review-gates control
    And I mark one agent to pause for review
    Then the control reports one gate

  @S-03-13
  Scenario: Attaching a file is offered on every launch panel
    When I cold-load "/create/user-stories"
    Then I see "+ Attach file"
    And a file input exists

  @S-03-14
  @live
  # live: dispatches a real run, so it cannot run in the offline tier.
  @destructive
  Scenario: Launching a run navigates to its live surface
    Given a disposable brief
    When I cold-load "/create/user-stories"
    And I type the brief
    And I click "Run workflow"
    Then a run is created
    And I land on that run's surface with its id in the URL
    And the header names the workflow I launched, not a different one
    # This is FIX-302's regression guard: a freshly launched run must not render
    # as "USER STORIES" when it is something else. Launch a PPT run to test it
    # properly — the bug only showed on a non-default type.

  @S-03-15
  @destructive
  Scenario: Save as my version creates a user override of a built-in
    When I cold-load "/create/user-stories"
    And I click "Save as my version"
    Then a saved workflow is created bound to the built-in "user_stories"
    And re-opening "/create/user-stories" shows my version
    And a control is offered to revert to the original
    # Spec 016. Only the STEPS are the user's — deliverable, context providers,
    # planner, clarify and limits always come from the file manifest.
```

## Notes for phase 2

- `/create/ppt` and `/create/prototype` render the **legacy wizard**. If the
  FR-007/T17 redirect ever lands, these scenarios move to shell B wholesale — that
  is a deliberate product change and the tests should be the thing that notices.
- The `Advanced <N> agents` label is a useful invariant: it must equal the roster
  length the modal shows, and for a saved override it must equal the override's
  step count (see D-05, which suggests it currently does not).
- Do not click template tiles by name alone. Several names repeat across the ppt
  and prototype galleries.

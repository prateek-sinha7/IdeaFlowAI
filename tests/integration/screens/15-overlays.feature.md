# Feature: Modals, drawers, popovers and menus

21 overlay surfaces, enumerated from source rather than found by clicking:

```
grep -rlE 'fixed inset-0|role="dialog"' frontend/src --include=*.tsx
```

**Screenshots:** `37`, `38`, `49`–`53`, `69`–`71`

---

## Coverage

| Overlay | Opened by | Captured |
|---|---|---|
| Account menu | `button[aria-label='Account menu']` | ✅ `37` |
| Notifications | `button[aria-label='Notifications']` | ✅ `38` |
| Workflow inspect | `Inspect <title> details` | ✅ `49` |
| Advanced config | `Advanced <N> agents` | ✅ `50`, `51` |
| Save-as-new-workflow | Save / Save as my version | ✅ `52` |
| Add-agent library | `button[aria-label='Add agent']` | ✅ `53` |
| Library item drawer | card / `Configure →` | ✅ `27`–`29`, `73` |
| Workflow actions | per-card `Workflow actions` | ✅ `69` |
| Run actions | per-row `Run actions` | ✅ `70` |
| Version picker | `Version v<n>` | ✅ `71` |
| PPT template upload | `Upload custom` (ppt) | ⬜ |
| Prototype template detail | template tile | ⬜ |
| Prototype custom template | `Upload custom` (prototype) | ⬜ |
| Design-system detail | design-system tile | ⬜ |
| Custom design system | custom design system | ⬜ |
| Agent skills picker | node → Skills | ⬜ |
| Workflow picker (divert) | divert target | ⬜ |
| Skill manager | skill management | ⬜ |
| Workflow dialog | — | ⬜ |
| Admin add-user + toast | `Add user` | ⬜ |
| Prototype preview source/tweaks | preview controls | ⬜ |

**11 of 21.** The uncaptured ones are mostly deeper inside the prototype wizard and
the composer node inspector.

---

## Observed contents

**Workflow inspect** (`role="dialog"`, one `Close` button) — heading is the workflow
name; body is the step chain (`4-step workflow: A -> B -> C -> D`), then
`CONTEXT PROVIDERS`, `CAPABILITIES`, `COMPACTION`. Empty sections say so
("No capabilities declared.").

**Advanced config** — **not** a `role="dialog"`; a full-screen inline layer. Header
`Advanced Workflow Configuration — <Workflow>`, a **`Use my version`** toggle (the
spec-016 override affordance), `Open in full canvas`, tabs `Agents (N)` / `Workflow`,
legend `CORE = LOCKED`, `BROWSE AGENT LIBRARY →`, and the same canvas node controls
as the composer. The Workflow tab exposes `deliverable-strategy`, `output`,
`output-format` and the three capability switches.

**Save-as-new-workflow** — nested inside the Advanced layer. `input#nwm-name`
(placeholder "e.g. Competitive research") and `textarea#nwm-description`
("What does this workflow produce?").

**Add-agent library** — search `input[data-testid="agent-search"]`, category rail
(All, User Stories, PPT, Prototype, App Builder, MuleSoft to Spring Boot,
.NET to Azure, Custom), and cards with **`data-testid="library-card-<agentId>"`**,
each carrying `+ Add` and a `title="View capabilities"` button.

**Workflow actions** — `Edit`, `Rename`, `Duplicate`, `Delete`.
**Run actions** — `Delete` only.

---

```gherkin
Feature: Overlays

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  Scenario: Inspecting a catalog workflow describes it without launching
    When I cold-load "/dashboard"
    And I click "Inspect Pitch an idea (v2) details"
    Then a dialog opens headed with that workflow's name
    And it shows the ordered step chain
    And it shows CONTEXT PROVIDERS, CAPABILITIES and COMPACTION sections
    And a section with nothing to show says so explicitly
    And no run has been started
    When I press Escape
    Then the dialog closes

  Scenario: The Advanced control opens the full agent configuration
    When I cold-load "/create/user-stories"
    And I click "Advanced 7 agents"
    Then a configuration layer opens headed "Advanced Workflow Configuration — User Stories"
    And it lists 7 agents, matching the control's label
    And I see a "Use my version" toggle
    And I see "Open in full canvas"
    And built-in agents are marked CORE and the legend reads "CORE = LOCKED"

  Scenario: The Advanced layer's Workflow tab exposes the deliverable settings
    Given the Advanced layer is open
    When I select its "Workflow" tab
    Then I see a deliverable-strategy selector
    And I see output filename and format controls
    And I see the Smart planning, Confirm requirements first and Internet access switches

  Scenario: Open in full canvas escalates to the composer
    Given the Advanced layer is open
    When I click "Open in full canvas"
    Then I land on a composer URL for that workflow

  @destructive
  Scenario: Saving from the Advanced layer names the new workflow
    Given the Advanced layer is open
    When I choose to save it as a new workflow
    Then a naming dialog opens with a name field and a description field
    And the name field is required before the save can complete

  Scenario: The add-agent modal lists agents by category
    When I cold-load "/workflows/new"
    And I click the "Add agent" control
    Then a library layer opens headed "Add agent"
    And I see the category rail: All, User Stories, PPT, Prototype, App Builder, MuleSoft to Spring Boot, .NET to Azure, Custom
    And I see a search input with testid "agent-search"
    And each agent card has testid "library-card-<agentId>"

  Scenario: Each agent card is individually addressable
    Given the add-agent modal is open
    Then clicking the "+ Add" inside "library-card-domain-analyst" adds THAT agent
    And no other agent is added
    # Use the per-card testid. The older clickNear-on-title workaround exists
    # only because "+ Add" repeats; the testid removes the ambiguity entirely.

  @defect
  # D-07. The modal's only close control has no accessible name, and Escape does
  # not close it — both contrary to the ba-browser definition's
  # `addAgentModalStaysOpen` quirk, which has now been corrected.
  Scenario: The add-agent modal cannot be closed by name or by Escape
    Given the add-agent modal is open
    When I press Escape
    Then the modal is STILL open
    And its only close control has no accessible name, no aria-label and no title
    # Expected once fixed: aria-label="Close" (or similar) AND Escape closes it.

  Scenario: The library item drawer opens beside the list, not over it
    When I cold-load "/library/agents/material-analyzer"
    Then a drawer with testid "agent-drawer" is shown
    And the library list behind it is still rendered
    And no element with role "dialog" is present

  Scenario Outline: The agent drawer's tabs each show their own panel
    When I cold-load "/library/agents/material-analyzer"
    And I click the drawer tab "<tab>"
    Then I see "<content>"

    Examples:
      | tab      | content                                                  |
      | Overview | WHAT IT DOES and ROLE IN PIPELINE                        |
      | Skills   | a category-filtered list of attachable skills            |
      | Hooks    | suggested hooks, or an explicit empty state              |
      | Config   | per-agent overrides for prompt, model, validator, gates and retry |

  Scenario: An agent with no suggested hooks says so
    When I open an agent drawer whose Hooks tab has nothing to show
    Then I see "No suggested hooks"
    And I see that there are no pre-built hooks recommended for this agent

  Scenario: The agent Config tab exposes the gate overrides
    When I open an agent drawer and select "Config"
    Then I can set a System Prompt override
    And I can set a Model override
    And I can set a Validator
    And I see BEFORE EXECUTE controls including a Human gate
    And I see AFTER EXECUTE controls including a Conditional gate and a Human gate
    And I see a Retry setting, a Reset control and a Save control
    And each override is described as inheriting from the workflow by default

  Scenario: The workflow actions menu offers the four row operations
    When I cold-load "/workflows"
    And I open the "Workflow actions" menu on a specific card
    Then the menu contains exactly: Edit, Rename, Duplicate, Delete

  Scenario: The run actions menu offers only delete
    When I cold-load "/runs"
    And I open the "Run actions" menu on a specific row
    Then the menu contains exactly: Delete

  Scenario: The version picker lists a run's artifact versions
    Given a completed run
    When I cold-load its detail URL
    And I click the version control
    Then the available versions are listed
    And the current version is indicated
    # A scrim covers the page while it is open — dismiss it before clicking
    # anything else in the header, or the click is intercepted.

  Scenario: Share copies a link rather than opening a dialog
    Given a completed run
    When I cold-load its detail URL
    Then the Share control's accessible name is "Copy a link to this run"
    When I activate it
    Then a link to the run is placed on the clipboard
    And no dialog opens

  Scenario Outline: Menus and drawers close without navigating
    Given "<overlay>" is open on "<route>"
    When I dismiss it
    Then it closes
    And the URL is unchanged

    Examples:
      | overlay              | route      |
      | the account menu     | /dashboard |
      | the notifications panel | /dashboard |
      | the workflow actions menu | /workflows |
      | the run actions menu | /runs      |
```

## Notes for phase 2

- **`role="dialog"` is not a reliable handle here.** Only the catalog inspect
  overlay sets it. The Advanced layer, the add-agent modal and the library drawer
  are all plain fixed-position layers. Target them by their content or testid.
- Overlays nest: Save-as-new-workflow opens **inside** the Advanced layer. A
  teardown that dismisses "the modal" once may leave the outer one open.
- Escape closes the account menu, the notifications panel and the inspect dialog,
  but **not** the add-agent modal (D-07). Do not assume a uniform dismiss.
- The 10 uncaptured overlays in the table above are the next capture increment;
  most sit inside the prototype wizard's Template / Design System galleries and
  the composer's node inspector.

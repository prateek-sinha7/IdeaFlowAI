# Feature: Modals, drawers, popovers and menus

21 overlay surfaces, enumerated from source rather than found by clicking:

```
grep -rlE 'fixed inset-0|role="dialog"' frontend/src --include=*.tsx
```

**Screenshots:** `12-overlays/` — 37 account menu, 38 notifications, 49 inspect dialog, 50–51 advanced, 52 save-as, 53 add-agent, 69 workflow actions, 70 run actions, 71 version picker, 76–80 wizard galleries, 81 admin add-user, 86 legacy add-agent (empty), 87 divert picker

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
| PPT template upload | `Upload custom` (ppt) | ✅ `80` |
| Prototype template detail | template tile | ✅ `76` |
| Prototype custom template | `Upload custom` (prototype) | ✅ `77` |
| Design-system detail | design-system tile | ✅ `78` |
| Custom design system | `Upload custom` (design system) | ✅ `79` |
| Admin add-user | `Add user` on `/admin` | ✅ `81` |
| Legacy builder add-agent | `Add Agent` on `/workflow` | ✅ `86` — **empty for every category (D-17)** |
| Workflow picker (divert) | ROUTE node → rail `Agent` → `Config` → outcome Target | ✅ `87` |
| Workflow dialog | `Inspect <title> details` | ✅ `49` — **same component as the catalog inspect dialog** |
| Agent skills picker | Agent rail → Skills | ➖ **not an overlay** — inline in the config rail (`83`) |
| Skill manager | `Manage skill` on an AgentNode | ⛔ **unreachable — D-17** |
| Prototype preview source/tweaks | preview controls | ⛔ **never mounts — D-18** |

**19 of 19 reachable overlays captured.** The original count of 21 was wrong twice:

- **Workflow dialog and the catalog inspect dialog are one component.**
  `HomeLaunchGrid.tsx:362` mounts `WorkflowDialog` on `inspectId`. Two rows, one
  overlay, double-counted since sweep 2.
- **The agent skills picker is not an overlay.** The manifest classified it from a
  `fixed inset-0` match in its source; at runtime it renders inline in the config
  rail, so opening dialogs was never going to find it.

That leaves 19 real overlays. Two of them **cannot be opened by any user**, and both
are defects rather than coverage gaps — see D-17 and D-18. Every overlay a user can
actually reach is captured.

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

  # ---------- The wizard galleries ----------

  Scenario: A template tile opens a detail modal with a live preview
    When I cold-load "/create/prototype"
    And I click the template tile "AI Coach Hub"
    Then a modal opens showing that template's name, device tag and description
    And it offers "Use this template"
    And its icon controls are addressable by title: "Open in new tab",
        "Fullscreen", "Close"
    # Those three have no text and no aria-label. They DO have a title, unlike
    # the add-agent modal's close control (D-07). Use title here; there is
    # nothing else.

  Scenario: The gallery mounts one live iframe per tile
    When I cold-load "/create/prototype"
    Then each of the 46 template tiles renders its own iframe preview
    # 46 iframes on one page. Budget for it: this screen is slow to settle, and
    # a naive "wait for network idle" may never resolve.

  Scenario Outline: Custom upload is offered on both wizards, HTML only
    When I cold-load "<route>"
    And I click "Upload custom"
    Then a modal titled "Upload custom template" opens
    And it offers the tabs "Upload HTML file" and "From URL"
    And its file input accepts ".html,.htm" with a 2 MB limit
    And it requires a template name

    Examples:
      | route              |
      | /create/prototype  |
      | /create/ppt        |
    # The PRESENTATION wizard's custom upload accepts .html, not .pptx — it is
    # the prototype modal reused verbatim. Recorded as observed; whether a deck
    # wizard should accept an HTML file is a product question.

  Scenario: A design-system tile shows its full DESIGN.md
    When I cold-load "/create/prototype"
    And I open the "Design System" tab
    And I click a design-system tile
    Then a modal opens rendering that system's DESIGN.md inline
    And it offers "Use this system"

  Scenario: A custom design system is pasted, not uploaded
    When I cold-load "/create/prototype"
    And I open the "Design System" tab
    And I click "Upload custom"
    Then a modal titled "Add custom design system" opens
    And it takes a name and a DESIGN.md textarea capped at 80,000 characters
    And it offers "Load example"
    # Note the asymmetry: templates are uploaded as a file, design systems are
    # pasted as text. Two different modals, two different input models.

  # ---------- Admin ----------

  Scenario: Add user collects credentials, plan and the admin flag
    Given I am signed in as an admin
    When I click "Add user" on "/admin"
    Then a modal titled "Create New User" opens
    And it has an email field, a password field requiring 8+ characters,
        a plan select named "new-user-tier" and a checkbox named "new-user-is-admin"
    And the plan select offers "basic", "pro", "enterprise" and "hexaware"

  @defect
  # The dialog has no Cancel. Its only dismissal is an unnamed icon button.
  Scenario: The create-user dialog can be abandoned
    Given the "Create New User" dialog is open
    Then I can dismiss it without creating a user
    And that control has an accessible name
    # Today there is no Cancel button and the close control has no text, no
    # aria-label and no title — the same shape as D-07. A user who opens this
    # dialog by mistake has no labelled way out.

  # ---------- The divert target picker ----------

  Scenario: The divert picker opens from the config rail, not the canvas
    When I cold-load "/workflows/ex_A3_divert/canvas"
    And I click the ROUTE node "Pick Language"
    And I open the rail tab "Agent" then the sub-tab "Config"
    Then each outcome whose Type is "Workflow" has a Target button
    When I activate one
    Then a modal opens reading "Pick a workflow"
    And it explains "This outcome stops the current run and hands off to the workflow you choose."
    # The button is data-testid="workflow-target-button", below the rail's fold —
    # scroll it into view first. It is a MODAL ON TOP OF A MODAL: two overlay
    # layers are present while it is open.

  Scenario: The divert picker groups and searches the catalogue
    Given the divert picker is open
    Then I see the group chips "All", "System", "Revision" and "Yours" with counts
    And I see a search input labelled "Search workflows"
    And each row shows a name, a type slug, a description and a step count
    # Revision variants are listed deliberately — see WorkflowTargetPicker's own
    # comment. Do not "fix" the count by filtering them out.

  @unverified
  Scenario: A failed workflow fetch degrades to free text
    Given the workflow list cannot be fetched
    When I open a divert outcome's Target
    Then I get a plain text input placeholder "workflow id / self"
    And I am told "Couldn't load workflows — enter the target id directly."
    # A second state of the same control, from PrototypePreview's sibling
    # WorkflowTargetPicker. Needs request interception to reach.

  # ---------- Two overlays no user can open ----------

  @defect
  # D-17. SkillManager's only host page cannot create the node that opens it.
  Scenario: The skill manager is reachable
    Given a workflow with at least one idle agent node
    When I activate "Manage skill" on that node
    Then the skill manager opens
    # Today: its only mount root is /workflow, the orphaned legacy builder, whose
    # "Add Agent" picker returns "No agents found" for ALL SIX categories. With
    # no node there is no button, so this overlay cannot be opened by anyone.
    # Written as it SHOULD be.

  @defect
  # D-18. PrototypePreview never mounts, so none of its controls exist.
  Scenario: A prototype deliverable offers source and tweaks
    Given a completed prototype run whose deliverable is validated HTML
    When I cold-load "/runs/{id}" and select the "Prototype" renderer
    Then the prototype renders in an iframe
    And I see controls titled "View source", "Open tweaks panel" and "Open in new tab"
    # Today the Preview tab renders the SPEC AGENT'S MARKDOWN as plain text while
    # the Files tab reports prototype.html · validated. Zero iframes, none of the
    # controls in the DOM. The overlay is uncapturable because the feature under
    # it is broken, not because the sweep missed it.

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
- **Escape is not a uniform dismiss.** It closes the account menu, the
  notifications panel, the inspect dialog and every prototype/ppt gallery modal —
  but **not** the add-agent modal (D-07). Verified individually, not assumed.
- **Icon-only controls fall into two camps.** The gallery modals label theirs with
  `title` ("Open in new tab", "Fullscreen", "Close"); the add-agent modal (D-07)
  and the admin create-user dialog label theirs with nothing at all. Check before
  writing a selector — there is no house style to rely on.
- The three overlays still uncaptured need fixtures this dev database lacks: a
  workflow containing a divert step (workflow picker), and a completed prototype
  run (preview source / tweaks). The skill manager and workflow dialog were not
  reachable from any surface walked in four sweeps — they may be dead code, which
  is worth confirming before writing a test for them.

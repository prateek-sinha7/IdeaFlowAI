# Feature: The control inventory — every addressable element

**Screenshots:** none. `@sourced` throughout — read from source, not yet seen.

---

## Why this file exists

Sweeps 1–6 specified **pages, overlays and features**. `_coverage.py` then asked a
different question: *of every element a test can actually address — every
`data-testid`, `aria-label` and form `name` — how many appear in a spec?*

The answer was **49%**. 150 of 298 controls were named nowhere. A page can be fully
specified and still leave most of its buttons untargetable.

This file covers the remainder, grouped by the feature each belongs to. Run

```
python3 tests/integration/capture/_coverage.py
```

to re-check; it exits non-zero while anything is uncovered.

---

## 1. Revision — the same control on five preview types

Every deliverable type can be revised in place, through a differently-**named** field
with an identical `aria-label`:

| Preview | Field name |
|---|---|
| Prototype | `prototype-revision` |
| App Builder | `app-revision` |
| PPT | `ppt-revision` |
| Markdown | `markdown-revision` |
| User story | `user-story-revision` |
| Run history | `revision-instructions` |

All six carry `aria-label="Revision instructions"` and submit on **Enter** when the
text is non-empty. **Select by `aria-label`, not by name** — the names differ per
type and a shared page object keyed on the name will silently match nothing on four
of the five.

This is the mechanism behind the whole of `21-run-families-and-versions`: submitting
one creates the next version in a family.

## 2. Chat lane — proposals, refinements and modes

`18-chat-lane` covered the transcript and composer. It did not cover:

| testid | What |
|---|---|
| `chat-proposals` | a group of proposed actions |
| `chat-proposal-confirm` | accept one (carries `data-proposal-id`) |
| `chat-proposal-reject` | decline one |
| `chat-refinement-chip` | a suggested refinement |
| `chat-refinement-confirm` / `-dismiss` | act on it |
| `chat-chain-picker` / `-chip` | pick a follow-on workflow |
| `chat-thinking-block` | the agent's reasoning, collapsible |
| `chat-tool-card` | one tool invocation |
| `chat-file-ops` | a file-operations summary |
| `chat-token-widget`, `chat-context-usage` | token/context meter |
| `chat-terminal-cancelled`, `chat-terminal-degraded` | terminal banners |
| `chat-compact` | compact lane mode |
| `typing-indicator`, `lane-reading-indicator` | activity |
| `chat-attach-dropzone`, `chat-attach-chip` | attachments |
| `lane-run-attachments`, `-attach-chip`, `-attach-remove` | per-run attachments |
| *(aria)* `Open mode menu`, `Remove mode` | chat modes |
| *(aria)* `Copy message`, `Edit message`, `Regenerate response` | message actions |
| `name="edit-message"` | the edit field |

A **proposal** is the agent asking permission to act; `chat-proposal-confirm` carries
`data-proposal-id`, so proposals are individually addressable. Note `chat-terminal-degraded`
— a terminal state **no run state table anywhere else in this suite mentions**.

## 3. Composer canvas — routing, sub-agents and limits

`04-composer-canvas` covered nodes, the rail and its tabs. Not covered:

| Control | What |
|---|---|
| `canvas-node-route`, `canvas-route-edge`, `-label` | conditional routing on the canvas |
| `canvas-rail-route`, `-route-add` | route outcomes in the rail |
| `canvas-node-detached` | a node with no parent |
| `canvas-edge-grab`, `canvas-chain-connect-preview` | edge drag/reparent |
| `canvas-declared-capabilities` | what a node declares |
| `subagent-row`, `name="subagent-strategy"`, *(aria)* `Add sub-agent to`, `Sub-agent strategy` | sub-agents |
| *(aria)* `Increase/Decrease retries`, `Increase/Decrease max parallel`, `Max loop count` | numeric steppers |
| *(aria)* `Condition source`, `Source list from`, `Default (no match)`, `Remove outcome` | route configuration |
| *(aria)* `Agent name`, `Confirm rename`, `name="agent-rename"` | inline rename |
| `name="agent-model"`, `agent-gate`, `agent-prompt`, `canvas-agent-prompt`, `fanout-source` | per-agent config |
| *(aria)* `Output file name`, `Workflow description` | workflow config |

The **stepper pairs are the risk**: `Increase retries` / `Decrease retries` and the
max-parallel pair are four separate controls whose accessible names differ only by a
verb. A selector matching `/retries/` hits both.

## 4. AgentsPopup — per-agent capability config

Templated accessible names, one per agent: `Model for <agent>`, `Gate for <agent>`,
`Retry for <agent>`, `Validator for <agent>`, `Source list for <agent>`,
`Fan out over a list for <agent>`, `Configuration for <agent>`, `Custom agent prompt`.
Plus `Search hooks` and `name="hook-search"`.

**Every one is scoped by agent name.** An unscoped selector matches every row.

## 5. Audit tab — export and monitoring

| Control | What |
|---|---|
| `audit-export-csv`, `-json`, `-report` | three export formats |
| `audit-live-badge` | live-tailing indicator |
| `audit-monitoring-banner` | monitoring notice |
| `audit-elapsed` | elapsed time |
| *(aria)* `Search audit log` | search |

`07-run-detail` covered the audit **filters**. The exports are the compliance story
and had no spec.

## 6. Search — nine inputs, nine different names

`Search agents`, `Search hooks`, `Search skills`, `Search users`, `Search files`,
`Search audit log`, `Search design systems`, `Search templates`, `Search projects`;
`name=` variants `file-search`, `hook-search`, `skills-search`, `sidebar-search`,
`agent-skills-search`, `model-filter`.

Already known from `03-launch-panels`: the two template searches use **different**
`name` attributes. That pattern holds across the app — there is no shared search
component, so there is no shared selector.

## 7. Analytics — a second filter

`Filter by pipeline` was captured. **`Filter by model`** (`name="model-filter"`) was
not; nor were `bar-chart-bar` or `cache-delta`.

## 8. Prototype design systems

`ds-band-card`, `ds-band-select`, `ds-swatch-band`, *(aria)* `Clear selection`,
`Search design systems`. `15-overlays` covered the *detail modal*; the picker's own
band controls were missed.

## 9. Preview extras

`preview-progress`, `steps-review-dot`, `steps-divert-link-row`, `files-building-hero`,
`artifact-version-picker`, *(aria)* `Download the deliverable`, `Run versions`,
`Edit HTML directly` (`name="tweak-html"`), `Search files`, `Auto-refresh interval`.

## 10. Elsewhere

`construction-block`, `-empty`, `-progress`, `-task-row` (agent detail);
`ClarificationsCard`'s `Clarifications, <n>`; `StartingPointCard`'s
`Show context from previous workflow` and `Show original brief version 1`;
`NotificationPanel`'s `Dismiss notification for <x>`; `library-add-sub`;
`not-found-brand-panel`; `Deliverable family` (WizardStepper);
`Constitution content` (settings); `Brief description`; `Sort by` / `Sort runs`;
`Select plan tier` (admin); `Template URL` (`name="template-url"`);
`API key name` and `GitHub personal access token` (IntegrationsCard);
`auto-follow` (handoff); `Artifact: <name>` and `Download file` (ArtifactCard);
`Chat transcript` (ChatPanel).

**`Sort by` and `Sort runs` both exist** in `WorkflowHistory` — two accessible names
for what a user reads as one control. Read the source before choosing.

---

```gherkin
Feature: Revising a deliverable

  @sourced
  Scenario Outline: Every deliverable type can be revised in place
    Given a completed run whose deliverable is "<type>"
    When I cold-load "/runs/{id}"
    Then a field labelled "Revision instructions" is offered
    And its name attribute is "<name>"
    When I enter instructions and press Enter
    Then a revision is requested

    Examples:
      | type        | name                 |
      | prototype   | prototype-revision   |
      | app         | app-revision         |
      | deck        | ppt-revision         |
      | markdown    | markdown-revision    |
      | user story  | user-story-revision  |

  @sourced
  Scenario: Revision fields share an accessible name but not a name attribute
    Then all five carry aria-label "Revision instructions"
    And no two share a name attribute
    # Select by aria-label. A page object keyed on the name matches nothing on
    # four of the five types, and does so silently.

  @sourced
  Scenario: An empty revision does nothing
    Given a revision field
    When I press Enter with it empty or whitespace-only
    Then no revision is requested
    # Guarded on revisionText.trim() in every implementation.

  @sourced
  Scenario: Submitting a revision clears the field
    Given a revision field with text
    When I press Enter
    Then the field is emptied
    # So a second Enter cannot resubmit the same instructions.


Feature: Chat lane proposals, refinements and modes

  @sourced
  Scenario: An agent proposal can be confirmed or rejected
    Given a run whose agent has proposed an action
    Then "chat-proposals" lists it
    And each carries "chat-proposal-confirm" and "chat-proposal-reject"
    And the confirm control carries that proposal's data-proposal-id
    # Address a specific proposal by its data-proposal-id; the testid repeats.

  @sourced
  Scenario: Confirming a proposal disables it while it runs
    Given a proposal
    When I confirm it
    Then the confirm control is disabled until it resolves
    # Guards double-submission. Assert it — a re-enabled button mid-flight means
    # the same action can be dispatched twice.

  @sourced
  Scenario: A refinement chip can be accepted or dismissed
    Given a run offering a refinement
    Then "chat-refinement-chip" is shown
    And it offers "chat-refinement-confirm" and "chat-refinement-dismiss"

  @sourced
  Scenario: The chain picker offers follow-on workflows
    When I open "chat-chain-picker"
    Then one "chat-chain-picker-chip" is offered per candidate
    And "Dismiss chain picker" closes it
    # Distinct from the "TAKE THIS FURTHER" chips in 18-chat-lane: those are
    # inline suggestions, this is a picker.

  @sourced
  Scenario: An agent's reasoning is collapsible
    Given a message with reasoning
    Then "chat-thinking-block" is collapsed by default
    And it can be expanded

  @sourced
  Scenario: Tool calls and file operations are shown as cards
    Given a run whose agent called a tool
    Then "chat-tool-card" describes the invocation
    And "chat-file-ops" summarises any file operations

  @sourced
  Scenario: Token and context usage are visible
    Then "chat-token-widget" reports token usage
    And "chat-context-usage" reports context consumption

  @sourced
  Scenario Outline: Terminal runs show a terminal banner
    Given a run that ended "<how>"
    Then "<banner>" is shown

    Examples:
      | how       | banner                    |
      | cancelled | chat-terminal-cancelled   |
      | degraded  | chat-terminal-degraded    |
    # "degraded" appears in NO run-state table elsewhere in this suite — not in
    # MANIFEST group D, not in 14-run-states. Establish what produces it.

  @sourced
  Scenario: A message can be copied, edited or regenerated
    Given a message in the transcript
    Then it offers "Copy message", "Edit message" and "Regenerate response"
    When I choose "Edit message"
    Then a field named "edit-message" is offered

  @sourced
  Scenario: Chat modes can be added and removed
    Then "Open mode menu" offers the available modes
    And a selected mode offers "Remove mode"

  @sourced
  Scenario: Files can be attached by drop or by chip
    Then "chat-attach-dropzone" accepts a dropped file
    And each attachment shows as "chat-attach-chip"
    And a run's own attachments are listed in "lane-run-attachments"
    And each shows as "lane-run-attach-chip" offering "lane-run-attach-remove"

  @sourced
  Scenario: Activity is indicated while waiting
    Then "typing-indicator" shows while the agent composes
    And "lane-reading-indicator" shows while it reads


Feature: Composer routing, sub-agents and limits

  @sourced
  Scenario: A conditional route renders as a labelled edge
    Given a workflow with a routing node
    When I cold-load its canvas
    Then "canvas-node-route" marks the node
    And each outcome draws a "canvas-route-edge" with a "canvas-route-edge-label"

  @sourced
  Scenario: Route outcomes are edited in the rail
    Given a routing node is selected
    Then "canvas-rail-route" lists its outcomes
    And "canvas-rail-route-add" adds one
    And each offers "Remove outcome"
    And a "Default (no match)" outcome is configurable

  @sourced
  Scenario: A route outcome names its condition source
    Given a route outcome
    Then "Condition source" selects what it tests
    And "Source list from" selects the list it draws on

  @sourced
  Scenario: A detached node is marked as such
    Given a node with no parent
    Then it carries "canvas-node-detached"

  @sourced
  Scenario: Edges can be regrabbed to reparent a node
    Given a node with a parent
    When I drag its top port
    Then "canvas-edge-grab" is active
    And "canvas-chain-connect-preview" previews the new connection
    # The canvas's own hint says "drag a top port to reparent".

  @sourced
  Scenario: Sub-agents are added under a node
    Given an agent node
    When I activate "Add sub-agent to <agent>"
    Then a "subagent-row" appears beneath it
    And "Sub-agent strategy" (name="subagent-strategy") selects how they run

  @sourced
  Scenario Outline: Numeric limits step up and down
    Given an agent node is selected
    Then "<increase>" and "<decrease>" adjust "<setting>"

    Examples:
      | setting      | increase              | decrease              |
      | retries      | Increase retries      | Decrease retries      |
      | max parallel | Increase max parallel | Decrease max parallel |
    # Two pairs, four controls, names differing only by a verb. A selector
    # matching /retries/ hits both members of that pair.

  @sourced
  Scenario: A loop node caps its iterations
    Given a node that loops back
    Then "Max loop count" bounds it
    # Without a cap a conditional gate looping to an earlier step runs forever.

  @sourced
  Scenario: An agent can be renamed inline
    Given an agent node
    When I edit "Agent name" (name="agent-rename")
    And I activate "Confirm rename"
    Then the node's label updates
    And every per-node aria-label derived from it updates too
    # 04-composer-canvas already warns that node aria-labels derive from the
    # display name. This is the control that changes it.

  @sourced
  Scenario: A node declares its capabilities
    Then "canvas-declared-capabilities" lists what it declares


Feature: Per-agent capability configuration

  @sourced
  Scenario Outline: Each capability is configured per agent, by name
    Given the agents popup is open
    Then "<control> for <agent>" configures that agent alone

    Examples:
      | control              |
      | Model                |
      | Gate                 |
      | Retry                |
      | Validator            |
      | Source list          |
      | Fan out over a list  |
      | Configuration        |
    # EVERY one of these is templated on the agent name. An unscoped selector
    # matches every row in the popup and edits whichever comes first.

  @sourced
  Scenario: An agent's prompt can be overridden
    Then "Custom agent prompt" (name="agent-prompt") accepts an override

  @sourced
  Scenario: Hooks can be searched
    Then "Search hooks" (name="hook-search") filters the hook list

  @sourced
  Scenario: An agent's skills are chosen from the rail, not a modal
    Given an agent node is selected on the canvas
    When I open the rail's "Skills" sub-tab
    Then "agent-skills-picker" is rendered INLINE in the rail
    And "agent-skills-search" (name="skills-search") filters the catalogue
    And no overlay has opened
    # Restates 04-composer-canvas's finding at the control level: the surface
    # manifest classified this as an overlay from a `fixed inset-0` match in its
    # source. At runtime it is a rail panel.


Feature: Audit export and monitoring

  @sourced
  Scenario Outline: The audit log exports in three formats
    Given a run with audit records
    When I cold-load "/runs/{id}/audit"
    And I activate "<control>"
    Then an export in that format is produced

    Examples:
      | control            |
      | audit-export-csv   |
      | audit-export-json  |
      | audit-export-report|
    # The compliance story of the product, and it had no spec. Note FilesTab
    # raises a native alert when an export fails (19-toasts-and-dialogs) — an
    # unhandled dialog here hangs the run.

  @sourced
  Scenario: A live run's audit tab says it is live
    Given a run still generating
    When I open its audit tab
    Then "audit-live-badge" is shown
    And "audit-elapsed" counts up
    And "audit-monitoring-banner" explains the tail

  @sourced
  Scenario: The audit log can be searched
    Then "Search audit log" filters the records


Feature: Search and filter controls

  @sourced
  Scenario Outline: Each list has its own search input
    Given I am on "<surface>"
    Then a search labelled "<label>" filters it

    Examples:
      | surface                | label                 |
      | the agent library      | Search agents         |
      | the agents popup hooks | Search hooks          |
      | the agent skills rail  | Search skills         |
      | /admin                 | Search users          |
      | an App Builder preview | Search files          |
      | a run's audit tab      | Search audit log      |
      | the design system tab  | Search design systems |
      | a template gallery     | Search templates      |
    # NINE search inputs, nine different name attributes, no shared component.
    # There is no single search selector for this product — do not write one.

  @sourced
  Scenario: Analytics filters by model as well as pipeline
    When I cold-load "/analytics"
    Then "Filter by pipeline" narrows by pipeline type
    And "Filter by model" (name="model-filter") narrows by model
    # Only the pipeline filter was captured. The model filter was missed
    # entirely — and per-model cost is the reason this page exists.

  @sourced
  Scenario: Run history sort has two accessible names
    When I cold-load "/runs"
    Then controls named "Sort by" and "Sort runs" both exist
    # Both are in WorkflowHistory. Read the source before choosing which to
    # target — a user sees one control.


Feature: Design system picker

  @sourced
  Scenario: Design systems are shown as colour bands
    Given the Design System tab
    Then each system renders a "ds-band-card" with a "ds-swatch-band"
    And "ds-band-select" chooses it
    And "Clear selection" unselects

Feature: Preview chrome and artifacts

  @sourced
  Scenario: A generating preview shows progress
    Given a run still generating a deliverable
    Then "preview-progress" reports progress
    And "files-building-hero" is shown on the Files tab

  @sourced
  Scenario: The artifact version picker is addressable
    Then "artifact-version-picker" selects a version
    And "Run versions" opens the version list

  @sourced
  Scenario: A deliverable can be downloaded from the header
    Then "Download the deliverable" downloads it
    # Register a dialog handler: PreviewPanel alerts on failure.

  @sourced
  Scenario: A prototype's HTML can be edited directly
    Given the tweaks panel is open
    Then "Edit HTML directly" (name="tweak-html") accepts raw HTML
    # BLOCKED by D-18 — PrototypePreview never mounts, so neither does this.

  @sourced
  Scenario: Steps show review and divert markers
    Then "steps-review-dot" marks a step that was reviewed
    And "steps-divert-link-row" links a step to the run it diverted into

  @sourced
  Scenario: A run detail can auto-refresh
    Then "Auto-refresh interval" selects the polling interval


Feature: Remaining controls

  @sourced
  Scenario: Agent construction progress is reported
    Given an agent building a deliverable
    Then "construction-progress" reports progress
    And "construction-task-row" lists each task
    And "construction-empty" is shown when there is nothing yet

  @sourced
  Scenario: Clarifications are summarised with a count
    Then a card labelled "Clarifications, <n>" summarises them

  @sourced
  Scenario: A chained run shows where it came from
    Given a run started from another workflow
    Then "Show context from previous workflow" reveals that context
    And "Show original brief version 1" reveals the original brief

  @sourced
  Scenario: A notification can be dismissed individually
    Given the notification panel is open
    Then each entry offers "Dismiss notification for <x>"

  @sourced
  Scenario: The admin table can be searched and its tier set
    When I cold-load "/admin"
    Then "Search users" filters the table
    And "Select plan tier" sets a user's plan

  @sourced
  Scenario: A custom template can be taken from a URL
    Given the custom template modal, "From URL" tab
    Then "Template URL" (name="template-url") accepts a URL

  @sourced
  Scenario: Handoff credentials are labelled
    Then "GitHub personal access token" and "API key name" are labelled fields
    And the handoff preview offers "auto-follow"

  @sourced
  Scenario: An artifact card names and downloads its file
    Then "Artifact: <name>" identifies it
    And "Download file" downloads it

  @sourced
  Scenario: The 404 page carries the brand panel
    When I cold-load an unknown route
    Then "not-found-brand-panel" is present


Feature: Controls addressable only by their text

  Four controls carry no testid and no aria-label. They are still addressable — by
  text — and were invisible to the first version of the coverage gate for exactly
  that reason.

  @sourced
  Scenario: A dropped realtime connection offers a reconnect
    Given the app's realtime connection drops
    Then a "Reconnect" control is offered in the shell
    When I activate it
    Then the connection is re-established without a page reload
    # DashboardLayout. Nothing else in this suite covers connection loss — the
    # run page streams over a live connection, so this is the affordance a user
    # meets when a run appears to stall.

  @sourced
  Scenario: An empty run history invites a first run
    Given a user with no runs
    When I cold-load "/runs"
    Then a "Start a run" control is offered
    When I activate it
    Then I land on a launch surface
    # The empty-state CTA. Reachable today with qa-pro/basic/enterprise, all of
    # which have zero runs.

  @sourced
  Scenario: An edited message is saved and resent in one action
    Given I am editing a message in the chat lane
    Then the commit control reads "Save & Send"
    When I activate it
    Then the edited text is saved AND resent
    # One control, two effects. A test that asserts only the save will pass
    # while the resend is broken.


Feature: Controls inside unreachable code

  These exist and are addressable in source, but no user can reach them. They are
  listed so the inventory is complete and so nobody writes a test against them
  expecting it to run.

  @unverified
  Scenario: The skill manager's editor
    Given the skill manager could be opened
    Then "Skill content" (name="skill-content") edits the skill
    # UNREACHABLE — D-17. Its only mount root is /workflow's AgentNode, and that
    # page's Add Agent picker returns "No agents found" for all six categories,
    # so no node ever exists to open it from.

  @unverified
  Scenario: The sidebar's controls
    Given the sidebar were mounted
    Then "Close sidebar" collapses it
    And "Search projects" (name="sidebar-search") filters its list
    And each entry is a chat session row
    # UNMOUNTABLE — components/sidebar/Sidebar.tsx and ChatSessionItem.tsx are
    # imported by no source file (see GAPS.md §9). Together they imply a
    # chat-session sidebar that was removed or never finished. Recorded for the
    # inventory; do NOT write a runnable test for it.
```

## Notes for phase 2

- **Run `_coverage.py` in CI.** It exits non-zero while any control is unspecified,
  which is what stops this suite drifting back to 49% the next time a feature lands.
- Three families need **scoped** selectors or they silently act on the wrong element:
  the per-agent capability controls (`… for <agent>`), the stepper pairs
  (`Increase/Decrease retries`, `… max parallel`), and the revision fields (same
  aria-label, five different names).
- **`chat-terminal-degraded` is a run state nothing else in this suite knows about.**
  Establish what produces it before writing the run-state table off as complete.
- `Filter by model` on analytics was missed by every sweep, and per-model cost is the
  reason that page exists.

# Feature: Composer and canvas

Where workflows are authored. One component (`ComposerPage`) serves three routes
that differ in **what Save does**.

**Routes:** `/workflows/new`, `/workflows/{id}/edit`, `/workflows/{type}/canvas`
**Screenshots:** `04-workflows/` — p16 new, p18 edit, p19 built-in canvas · `13-states/` — 54 simple view, 61 dark canvas

---

## The three modes

| Route | Header | Save button | Save means |
|---|---|---|---|
| `/workflows/new` | `CUSTOM · COMPOSER` · 0 agents | `Save workflow` | `POST /api/user-workflows` → new row |
| `/workflows/{id}/edit` | `CUSTOM · COMPOSER` · N agents | `Save workflow` | `PATCH /api/user-workflows/{id}` → overwrite |
| `/workflows/{type}/canvas` | `PPT · COPY` · N agents | **`Save as copy`** | new row; the built-in is a file on disk, there is nothing to write back to |

ADR-0014: a built-in opens on the canvas at its own URL and can only be saved as a
copy. The differing Save label is the whole tell, and it is the single highest-value
assertion on this surface.

`/workflows/{id}/edit` shows `CUSTOM · COMPOSER` **even for a ppt-based override** —
`ComposerPage` hardcodes `base_pipeline_type` to `"custom"` (ISS-183: `workflowType`
is a shared mutable other screens set, and trusting it here once persisted a stale
type as a saved workflow's permanent base). Recorded, not asserted as correct.

---

## Layout

**Header:** `<TYPE> · <MODE>`, then `N agents`, `N review gates`, an estimate.
Testid `composer-header-summary`.

**View toggle:** `Simple` | `Canvas`.

**Actions:** `Run once`, and the Save button per the table above.

**Canvas** (`[data-testid="canvas-view"]`):
- A `BRIEF` node — "What to build / the run input" (`canvas-brief`)
- One node per agent: `canvas-node-wrap-<agentId>` wrapping `canvas-node-<agentId>`
- Edges: `canvas-edge`
- Per-node controls, each `aria-label`led with the agent's display name:
  `Move <Name> Agent earlier` / `later`, `Rename <Name> Agent`, `Remove <Name> Agent`
  (testids `canvas-move-earlier-<id>`, `canvas-move-later-<id>`, `canvas-rename-<id>`)
- Per-node attach affordances: `Gate`, `Sub-agent`
- Per-node badges: `Default`, `Validator`, `Gate`, `Retry`, `Sub-agent`; built-ins
  additionally carry a `CORE` badge
- Canvas chrome: `Add agent` (aria-label), `Zoom out`, `Zoom in`, `Fit`,
  `Auto-arrange`, and a zoom percentage readout
- Hints: "Click a node to configure", "Drag to move · drag a top port to reparent",
  "Hold Space + drag to pan"

**Config rail** — tabs `Workflow` | `Agent`, plus `Reset to default`.

The **Agent** tab is not one panel but five sub-tabs of its own — `Overview`,
`Skills`, `Hooks`, `Tools`, `Config` — headed by
`Agent · step <n> of <total> · <agent title>` and carrying
`input[name="agent-name"]`. Its `Skills` sub-tab renders the full skill catalogue
**inline in the rail**, not as a modal; the surface manifest had it listed as an
overlay, which is why four sweeps never found it by opening dialogs.

The **Workflow** tab's controls:

| Control | Selector | Notes |
|---|---|---|
| Workflow name | `input[name="workflow-name"]` | |
| Description | `input[name="workflow-description"]` | |
| Brief | `textarea[name="brief"]` | "3 more characters to enable Run" |
| Attach | `input[type=file]` behind `+ Attach file` | |
| Smart planning | `button[role="switch"][aria-label="Smart planning"]` | ON runs a planning agent that breaks the brief into a task plan first |
| Confirm requirements first | `button[role="switch"][aria-label="Confirm requirements first"]` | ON pauses to ask clarifying questions |
| Internet access | `button[role="switch"][aria-label="Internet access"]` | |
| Deliverable strategy | `select[name="deliverable-strategy"]` | Streamed text / Single file / Serialized sandbox |
| Output filename | `input[name="output-filename"]` | |
| Output format | `select[name="output-format"]` | Markdown (.md) / HTML (.html) |

**Deliverable strategies**, verbatim from the UI:
- *Streamed text* — uses the agent's raw output
- *Single file* — reads back one named file from the workspace
- *Serialized sandbox* — zips the whole workspace

**Last-step guard** (built-in canvas, last-streamed deliverables): "The last step's
output is this workflow's deliverable (output.md). Adding a step after it would
replace output.md with the new step's output — insert it before another step
instead." Spec 016 ships this so an append cannot silently destroy the deliverable.

---

```gherkin
Feature: Composing a workflow

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  Scenario: A brand-new composer opens empty
    When I cold-load "/workflows/new"
    Then the header reads "CUSTOM · COMPOSER"
    And the header summary reports "0 agents" and "0 review gates"
    And I see a BRIEF node
    And I see no agent nodes
    And the primary action is "Save workflow"
    # ComposerPage seeds pipelineAgents ONLY from initialManifestSteps /
    # initialAgentIds, which is how DashboardLayout drives it. A bare mount
    # really does render an empty composer — that is the contract, not a bug.

  Scenario: Editing a saved workflow loads its steps
    Given I own a saved workflow with 4 steps
    When I cold-load "/workflows/{id}/edit"
    Then the header summary reports "4 agents"
    And I see one canvas node per step, in manifest order
    And the primary action is "Save workflow"

  Scenario: A built-in opens read-to-copy, not read-to-overwrite
    When I cold-load "/workflows/ppt/canvas"
    Then the header reads "PPT · COPY"
    And the primary action is "Save as copy"
    And NO button labelled exactly "Save workflow" is present
    And each built-in agent node carries a "CORE" badge
    # ADR-0014. This is the single most important assertion on this surface:
    # a built-in must never be overwritable in place.

  Scenario: A built-in canvas survives a hard refresh
    When I cold-load "/workflows/ppt/canvas"
    And I reload the page
    Then the header still reads "PPT · COPY"
    And the same agent nodes are present
    # The pipeline_type is carried in the URL precisely so the composer can
    # rebuild from the API on any mount. There is no sessionStorage handoff.

  Scenario: Switching between Simple and Canvas keeps the roster
    When I cold-load "/workflows/ppt/canvas"
    And I note the agent names
    And I click "Simple"
    Then the same agents are listed
    When I click "Canvas"
    Then the same agent nodes are shown, in the same order

  Scenario: Adding an agent from the library modal
    When I cold-load "/workflows/new"
    And I click the "Add agent" control
    Then a library modal opens
    When I add the "Custom Agent" template
    Then a node for it appears on the canvas
    And the header summary reports "1 agents"
    And the modal is still open
    When I press Escape
    Then the modal closes
    # Quirk `addAgentModalStaysOpen`: the modal does NOT auto-close after an add.
    # Its search input shifts nth-index selectors, so close it before touching
    # anything else. Quirk `multipleIdenticalLabels`: "+ Add" repeats once per
    # card — always scope the click to the card's unique title.

  Scenario: Reordering a node moves it in the plan
    Given a composer with agents A, B, C in order
    When I click "Move B Agent earlier"
    Then the order becomes B, A, C
    When I click "Move B Agent later"
    Then the order returns to A, B, C

  Scenario: Removing a node drops it from the summary
    Given a composer with 3 agents
    When I click "Remove <name> Agent"
    Then that node disappears
    And the header summary reports "2 agents"

  Scenario: Renaming a node updates its label and its control names
    Given a composer with an agent named "Deck QA"
    When I rename it to "Deck Review"
    Then the node label reads "Deck Review"
    And a control "Rename Deck Review Agent" exists
    And no control "Rename Deck QA Agent" remains
    # The per-node aria-labels are derived from the display name. Any phase-2
    # helper that caches them must re-read after a rename.

  Scenario: The config rail's Agent tab has five sub-tabs of its own
    When I cold-load "/workflows/ppt/canvas"
    And I click the rail tab "Agent"
    Then the rail heading reads "Agent · step 1 of 3 · <the first agent's title>"
    And I see the sub-tabs "Overview", "Skills", "Hooks", "Tools", "Config"
    And an input named "agent-name" is present

  Scenario: The agent Skills picker is part of the rail, not a modal
    When I cold-load "/workflows/ppt/canvas"
    And I click the rail tab "Agent"
    And I click the sub-tab "Skills"
    Then the skill catalogue is listed inside the rail
    And no overlay or dialog has opened
    # Recorded because the surface manifest classified this as an overlay from a
    # `fixed inset-0` match in its source. At runtime it is inline. A phase-2
    # helper that waits for a dialog here waits forever.

  Scenario Outline: Each capability toggle flips independently
    When I cold-load "/workflows/new"
    And I toggle the switch "<switch>"
    Then that switch reports the opposite state
    And the other switches are unchanged

    Examples:
      | switch                     |
      | Smart planning             |
      | Confirm requirements first |
      | Internet access            |
    # Quirk `toolsToggleTiming`: clicking several toggles in one evaluate keeps
    # only the LAST click — React batches them. Click one at a time and wait
    # ~400-500ms between each.

  Scenario Outline: Choosing a deliverable strategy reveals its own fields
    When I cold-load "/workflows/new"
    And I select the deliverable strategy "<strategy>"
    Then the helper text reads "<helper>"

    Examples:
      | strategy           | helper                                        |
      | Streamed text      | uses the agent's raw output                   |
      | Single file        | reads back one named file from the workspace  |
      | Serialized sandbox | zips the whole workspace                      |

  Scenario: Run is gated on a long-enough brief
    When I cold-load "/workflows/new"
    Then I see the hint "3 more characters to enable Run"
    And "Run once" is disabled
    When I type a brief of at least 3 characters
    Then "Run once" is enabled

  Scenario: A last-streamed built-in refuses an append-after-final-step slot
    When I cold-load "/workflows/ppt/canvas"
    Then I see the guidance that the last step's output IS the deliverable
    And no append-after-final-step slot is offered
    # Spec 016. Appending would silently replace output.md. Sandbox-readback
    # deliverables keep the slot; last-streamed ones do not.

  @defect
  # ISS-183. A ppt-based override still labels itself CUSTOM on the composer,
  # because base_pipeline_type is hardcoded to "custom" there. Recorded as
  # current behaviour.
  Scenario: A ppt-based override's editor calls itself CUSTOM
    Given I own a saved workflow whose base is "ppt"
    When I cold-load "/workflows/{id}/edit"
    Then the header reads "CUSTOM · COMPOSER"
    And it does NOT read "PRESENTATION · COMPOSER"

  @destructive
  Scenario: Saving a copy of a built-in creates a new row and leaves the original alone
    When I cold-load "/workflows/ppt/canvas"
    And I rename the workflow to a unique name
    And I click "Save as copy"
    Then a new saved workflow exists with that name
    And "/workflows/ppt/canvas" still shows the original built-in steps

  @destructive
  Scenario: The blank custom-agent template is withheld when authoring an override
    Given I am authoring an override of a built-in
    When I open the add-agent library modal
    Then the blank "Custom Agent" template is NOT offered
    # FIX-306. A blank custom agent mints a dynamic id with no AGENT.md on disk,
    # so such an override saves and renders and then 400s with invalid_agent_ids
    # on every launch. Withholding the template is the guard.

  @destructive
  Scenario: A saved composition can be launched from the composer
    Given a composer with at least one agent and a valid brief
    When I click "Run once"
    Then a run starts
    And I land on that run's surface
    # Quirk `runOnceNoFeedback`: the button gives no immediate visual feedback.
    # Wait on the URL or on run state, never on a spinner.
```

## Notes for phase 2

- **`Save workflow` vs `Save as copy` is the mode discriminator.** Assert on the
  exact label, not on "a save button exists" — that would pass in all three modes
  and catch nothing.
- Node testids are keyed by **agent id** (`canvas-node-ppt-composer`), while the
  control aria-labels are keyed by **display name** (`Rename Deck QA Agent`). Both
  appear on the same node. Prefer the testid; it survives a rename.
- Quirk `composerRailScreenshot`: the config rail sometimes fails to appear in a
  screenshot even though it is present and interactive. Verify it with a DOM query
  (`button[role="switch"]`), never from a screenshot.
- New node instance ids are shaped `<shortUserSegment>-<random6>`, never the legacy
  `agent-N`. Do not write a selector that assumes the old shape.

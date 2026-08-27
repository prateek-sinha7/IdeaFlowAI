# Feature: The concierge chat lane

**Routes:** every run-detail URL — `/runs/{id}`, `/steps`, `/steps/{agentId}`, `/files`, `/workspace`, `/audit`, `/preview/full`, `/stream`, `/versions/{v}`
**Screenshots:** `14-chat-lane/` — c01 completed prototype, c02 cancelled (read-only), c03 failed, c04 diverted, c05 completed with clarifications

---

## What it is, and what it is not

The chat lane is the **left column of the run page**. The tab strip
(Preview / Steps / Files / Workspace / Audit) is the *right* pane. The lane sits
beside it and **persists across every tab and every run-detail URL** — verified on
`/audit` and `/files`, not just the default route.

It is not a tab, not a modal, and not a panel that opens. It is always there. Any
phase-2 page object that treats the run page as "a tab strip" will miss half the
screen.

The run's identity lives in the lane, not in the tab pane:

| Element | testid |
|---|---|
| Container | `run-chat-lane` (also `execution-chat-lane`) |
| Back | `lane-back` |
| Pipeline type | `lane-run-type` |
| Status | `lane-run-status` |
| Title | `lane-run-title` |
| Meta (age · duration · tokens) | `lane-run-meta` |

**Read the run's status from `lane-run-status`,** not from a card in the tab pane.

## The transcript

| Element | testid |
|---|---|
| Scroller | `chat-lane-transcript`, `chat-transcript` |
| One message | `chat-message` |
| Its card | `chat-result-card` |
| A link inside a card | `chat-result-card-link` |

Every message carries two data attributes:

```
data-role="narrator"
data-message-id="chat_reply:<uuid>"
data-message-id="chat_reply:pipeline_start:run:<runId>"
```

**Every message on every seeded run was `data-role="narrator"`.** No `user` or
`assistant` message exists in the dev database, because producing one requires
sending a message, which is a live LLM turn. The role attribute is the right hook
for phase 2 — but the non-narrator branches are unverified.

### The narrator's vocabulary, verbatim

| Message | Action offered |
|---|---|
| "Before I build, I need to lock a few things down." | `Answer in Steps` |
| "Clarifications answered" | `Answer in Steps` |
| "Run started" | `Open in Steps` |
| "Review approved — build continues" | *(none)* |
| "Cancelled by you" | `Open in Steps` |
| "What went wrong" | `Open in Steps` |
| "Deliverable" / "Delivered — open in Preview →" | `Open in Preview` |

Note every action sends the user to a **tab**, never elsewhere. The lane narrates;
the tabs hold the detail.

## Adornments — the collapsible run summary

`lane-adornments-toggle` carries `aria-expanded`. Its label is
`Run summary` + `<n> agents · <deliverable filename>` and **does not change between
states** — only `aria-expanded` does.

Expanding reveals `lane-pipeline-mini` (a `PIPELINE · N AGENTS` strip with per-agent
durations and `Open Steps →`) and `lane-deliverable` (the filename and
`open in preview →`).

**`lane-adornments` is in the DOM in both states.** Assert on `aria-expanded`, or on
`lane-pipeline-mini`; asserting on `lane-adornments` being present proves nothing.

## Chaining — "TAKE THIS FURTHER"

| Element | testid |
|---|---|
| Group | `chat-chain-suggestions` |
| A chip | `chat-chain-suggestion-chip` |
| A not-yet-available chip | `chat-chain-suggestion-chip-beta` |

Observed on the completed prototype run: *Pitch an idea*, *Generate product
requirements* (both live) and *Build an end-to-end application* badged `SOON` (beta).

**The beta chip is a different testid, not a modifier.** A selector on
`chat-chain-suggestion-chip` alone silently misses it. Use a prefix selector when
counting, an exact one when clicking.

The chips appeared on **one** of six runs captured. Whatever governs them is not
"the run completed" — a completed PPT V2 run and a completed human-gate run both
showed none.

## The composer

| Element | Selector |
|---|---|
| Input | `textarea[name="run-chat-message"]`, `aria-label="Chat message input"` |
| Placeholder | `Ask for a change or a follow-up…` |
| Attachments | `chat-attachments` → `input[type=file]`, labelled `Attach files` |
| Voice | `Voice · transcribe` |
| Send | `chat-send`, `aria-label="Send message"` |

`chat-send` is **disabled while the textarea is empty**, enables on the first
character, and disables again when cleared. Verified by dispatching input events
without sending.

## Composer availability by run state — the important table

| Status | Lane | `chat-composer` | textarea | send | Messages | Chain chips |
|---|---|---|---|---|---|---|
| Done (prototype) | ✓ | ✓ | ✓ enabled | ✓ | 7 | 3 |
| Done (ppt_v2) | ✓ | ✓ | ✓ enabled | ✓ | 4 | 0 |
| Done (human gate) | ✓ | ✓ | ✓ enabled | ✓ | 3 | 0 |
| **Failed** | ✓ | ✓ | **✓ enabled** | ✓ | 2 | 0 |
| **Cancelled** | ✓ | ✓ | **✗ absent** | ✗ | 2 | 0 |
| **Diverted** | ✓ | ✓ | **✗ absent** | ✗ | 2 | 0 |

Three terminal states, two different contracts — see D-19. Note also that
`chat-composer` is present in **all six**; it is the textarea and send button that
disappear. Asserting on `chat-composer` tells you nothing about whether the user can
type.

---

```gherkin
Feature: The concierge chat lane

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  # ---------- Structure ----------

  @S-18-01
  Scenario: The lane is present on every run-detail surface
    Given a completed run
    When I cold-load "/runs/{id}"
    Then the chat lane is present
    And it carries the run's type, status, title and meta

  @S-18-02
  Scenario Outline: The lane survives every tab
    Given a completed run
    When I cold-load "<route>"
    Then the chat lane is still present with the same transcript
    And the tab pane shows "<tab>"

    Examples:
      | route                  | tab       |
      | /runs/{id}             | Preview   |
      | /runs/{id}/steps       | Steps     |
      | /runs/{id}/files       | Files     |
      | /runs/{id}/workspace   | Workspace |
      | /runs/{id}/audit       | Audit     |
    # The lane is the left column, not a tab. A page object that models the run
    # page as a tab strip misses half the screen.

  @S-18-03
  Scenario: Run status is read from the lane, not the tab pane
    Given a failed run
    When I cold-load "/runs/{id}"
    Then the element with testid "lane-run-status" reads "Failed"

  @S-18-04
  Scenario: Back returns to run history without losing the filter
    Given I reached a run from "/runs?type=custom"
    When I activate "lane-back"
    Then I return to run history

  # ---------- Transcript ----------

  @S-18-05
  Scenario: Every message declares its role and a stable id
    Given a completed run
    When I cold-load "/runs/{id}"
    Then each "chat-message" has a "data-role"
    And each has a "data-message-id" matching "chat_reply:*"
    # Seeded runs only ever produce data-role="narrator". Assert the attribute
    # exists; do not assume the value until a user turn has been created.

  @S-18-06
  Scenario Outline: The narrator names each lifecycle event
    Given a run in state "<state>"
    When I cold-load "/runs/{id}"
    Then the transcript contains "<message>"
    And that message offers "<action>"

    Examples:
      | state     | message                                | action           |
      | completed | Run started                            | Open in Steps    |
      | completed | Delivered — open in Preview →          | Open in Preview  |
      | cancelled | Cancelled by you                       | Open in Steps    |
      | failed    | What went wrong                        | Open in Steps    |

  @S-18-07
  Scenario: A clarification request points at Steps
    Given a run whose workflow asked for clarifications
    When I cold-load "/runs/{id}"
    Then the transcript contains "Before I build, I need to lock a few things down."
    And it offers "Answer in Steps"
    And activating it opens the Steps tab
    # The lane ASKS but does not COLLECT. The answer is given in Steps. Any test
    # that expects to type the answer into the lane composer is wrong.

  @S-18-08
  @defect
  # D-21. The prototype run's transcript repeats itself.
  Scenario: The clarification exchange is not duplicated
    Given the completed prototype run
    When I cold-load "/runs/{id}"
    Then "Before I build, I need to lock a few things down." appears once
    And "Clarifications answered" appears once
    # Today each appears TWICE, with different data-message-ids and identical
    # text and actions. Two clarification rounds would explain it; two identical
    # rounds reading as a repeat is the defect. Written as it SHOULD be, so this
    # is red until resolved either way.

  @S-18-09
  @unverified
  # A diverted run's lane never names where the run went.
  Scenario: A diverted run links to the workflow it handed off to
    Given a diverted run
    When I cold-load "/runs/{id}"
    Then the transcript names the workflow it diverted to
    And offers a way to open the resulting run
    # Today its last message is "Review approved — build continues" — the same
    # thing a NON-diverted gate approval says. The lane gives the user no way to
    # follow the handoff. Recorded as a question for the product owner.

  # ---------- Adornments ----------

  @S-18-10
  Scenario: The run summary collapses and expands
    Given a completed run
    When I cold-load "/runs/{id}"
    Then "lane-adornments-toggle" has aria-expanded "false"
    When I activate it
    Then aria-expanded becomes "true"
    And "lane-pipeline-mini" is shown with one entry per agent
    And "lane-deliverable" names the deliverable file
    # "lane-adornments" is in the DOM in BOTH states. Assert aria-expanded or
    # lane-pipeline-mini — its presence alone proves nothing.

  @S-18-11
  Scenario: The summary label does not announce its own state
    Given the adornments are expanded
    Then the toggle still reads "Run summary"
    # Same trap as the "Dark mode" control in 17-theme-and-tiers: the label names
    # the thing, not the state. Read aria-expanded.

  # ---------- Composer ----------

  @S-18-12
  Scenario: Send is gated on non-empty input
    Given a completed run
    When I cold-load "/runs/{id}"
    Then "chat-send" is disabled
    When I type "a" into the chat message input
    Then "chat-send" is enabled
    When I clear the input
    Then "chat-send" is disabled again

  @S-18-13
  Scenario: The composer offers attachments and voice
    Given a completed run
    When I cold-load "/runs/{id}"
    Then I see a file input behind "Attach files"
    And I see a "Voice · transcribe" control

  @S-18-14
  Scenario Outline: Whether the user can reply depends on the run's state
    Given a run in state "<state>"
    When I cold-load "/runs/{id}"
    Then a chat message input is "<input>"

    Examples:
      | state     | input   |
      | completed | present |
      | failed    | present |
      | cancelled | absent  |
      | diverted  | absent  |

  @S-18-15
  @defect
  # D-19. Three terminal states, two contracts, no visible rule.
  Scenario: Terminal runs agree on whether they can be replied to
    Given a failed run and a cancelled run
    When I cold-load each
    Then both offer the same reply affordance
    # Today a FAILED run has a fully enabled composer while CANCELLED and
    # DIVERTED runs have none — and "chat-composer" is in the DOM for all three,
    # so the container is not the signal. Written as it SHOULD be.

  @S-18-16
  @live
  # live: sending triggers a real LLM turn, so it cannot run in the offline tier.
  @destructive
  @unverified
  Scenario: Sending a message adds a user turn and a reply
    Given a completed run
    When I type a follow-up and send it
    Then a message with data-role="user" is appended
    And the concierge replies in the same transcript
    # NOT CAPTURED. Sending triggers a live LLM turn — real cost, and on a gated
    # workflow it can create a gate only a human should answer. The user and
    # assistant role branches are therefore unverified; only "narrator" is.

  # ---------- Chaining ----------

  @S-18-17
  Scenario: A chainable run offers follow-on workflows
    Given the completed prototype run
    When I cold-load "/runs/{id}"
    Then I see the heading "TAKE THIS FURTHER"
    And I see chips "Pitch an idea" and "Generate product requirements"
    And I see a chip "Build an end-to-end application" badged "SOON"

  @S-18-18
  Scenario: The unavailable chip has its own testid
    Given the chain suggestions are shown
    Then the "SOON" chip's testid is "chat-chain-suggestion-chip-beta"
    And it is NOT "chat-chain-suggestion-chip"
    # A selector on the base testid silently misses it. Use a prefix selector to
    # count, an exact one to click.

  @S-18-19
  @unverified
  Scenario: Chain suggestions appear only where they are meaningful
    # Observed on 1 of 6 runs. A completed PPT V2 run and a completed human-gate
    # run both showed none, so "the run completed" is not the rule. What governs
    # them was not determined — phase 2 should establish it before asserting
    # absence anywhere.
```

## Notes for phase 2

- **The lane is the best-instrumented surface in the product.** 20+ testids, on a
  page whose sibling `/runs` list has literally zero (D-14). Use them.
- **`chat-composer` is not a proxy for "the user can type."** It is present on
  cancelled and diverted runs that have no input at all. Assert on the textarea.
- **Do not send a message in an automated run.** It costs an LLM call and, on a
  gated workflow, can create a review gate that only a human should answer. The
  `@destructive` scenario above needs an explicit opt-in and its own fixture.
- The lane narrates and links; it never collects. Clarifications are *answered in
  Steps*. Keep that boundary in the page object or tests will look for inputs the
  lane does not have.
- `tab-thinking` is still the Steps tab's testid (D-08). Map it explicitly.

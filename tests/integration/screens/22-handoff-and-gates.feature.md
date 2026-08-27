# Feature: The IDE handoff, and human-in-the-loop gates

**Screenshots:** `10-handoff/p49-handoff-settings.png`, `p50-handoff-token-invalid.png`
— the settings page and the invalid-token state only. Everything a **valid** token
mounts, and every gate control, is `@sourced`: read from the components, never
rendered in any sweep.

Two features, one file, because both are gated behind a fixture nobody has: a valid
handoff token, and a run sitting at `waiting_for_user`.

---

## Part 1 — `/handoff/{token}` with a valid token

`p50` captured the failure state. A valid token mounts roughly **1,400 lines** that
no sweep has seen:

| Component | LOC | Role |
|---|---:|---|
| `HandoffWorkflow` | 367 | the shell and its three states |
| `HandoffAgentPanel` | 252 | left rail, 320px, agent list |
| `HandoffPreviewPanel` | 171 | right pane |
| `DiffView` | 197 | the proposed change |
| `ReportViews` | 253 | `TestReportView`, `ComplianceReportView` |
| `IntegrationsCard` | 399 | shared with `/handoff/settings` |

### Three states, verbatim from source

**1 — Not found / expired token** (captured, `p50`):

> **Handoff not found**
> "This handoff token doesn't exist, has expired, or belongs to a different account."
> → `Back to dashboard`

Note the copy names **three** distinct causes — nonexistent, expired, *someone
else's*. The user cannot tell which, which is deliberate: it does not confirm to a
stranger that a token exists.

**2 — Onboarding, when no GitHub PAT is saved:**

> **One more step before this can run**
> "VelocityAI needs a GitHub PAT (with `repo` scope) to clone `<repo_url>` and open
> the pull request. Add one below — it's saved encrypted and never returned by any
> API."
> …then `IntegrationsCard` inline, and:
> "After saving, the **Start pipeline** button in the top bar will activate."

**3 — Expired session:**

> **This handoff has expired**
> "Handoff URLs are good for one hour. Re-run `/flowin-handoff` from your IDE to mint
> a new one."

`canStart` is `session.status === "pending" || "failed"` — so **a failed handoff can
be restarted**, a completed one cannot.

## Part 2 — the gate and clarify controls

`InlineGateActions` (460 loc) and `InlineClarifyActions` (304 loc) mount in the chat
lane. `18-chat-lane` captured only their **aftermath** — "Clarifications answered",
"Review approved — build continues". The controls a human actually uses have never
been rendered.

### Gate testids, verbatim

| testid | Control |
|---|---|
| `chat-gate-actions` | container |
| `chat-gate-approve` | approve, continue |
| `chat-gate-request-changes` | ask for changes |
| `chat-gate-revision` | revision input |
| `chat-gate-preview` | preview the gated content |
| `chat-gate-choice-prompt` | the question, when the gate is a choice |
| `chat-gate-choice-<choice>` | one option per choice |
| `chat-gate-update-specs` | update the specs |
| `chat-gate-redo` | redo, with instructions |
| `chat-gate-reject` | reject |
| `chat-gate-cancel` | **`Cancel run`** — opens a two-step confirm (KAN-95) |
| *(aria)* `Edit gate content` | edit control |
| *(aria)* `Additional instructions for redo` | redo textarea |

### The evidence block — `GateWell`

Rendered inside `InlineGateActions`: *what the run produced*, shown as what it is.
Capped in height and internally scrolling **by design** — this is the evidence a
decision is checked against, not the reading surface.

| testid | Control |
|---|---|
| `gate-well` | the block. `data-well-kind` is `code` or `prose` |
| `gate-well-copy` | copy the source, on a code artifact. Label flips to `Copied` for 1.5s |
| `gate-well-verdict` | the readiness banner. `data-verdict-tone` is `ready`, `caution`, `revision` or neutral |

`gate-well-verdict` hoists the analyzer's readiness line **out of the prose and
above it**. `AnalysisPreview` always did this and the gate lost it when it stopped
using that renderer — the worst place to lose it, because on an approval gate
"CAUTION advised" is the single most decision-relevant line in the artifact, and
buried in the body it reads as ordinary text.

### Clarify testids

| testid | Control |
|---|---|
| `chat-clarify-actions` | container |
| `chat-clarify-chip` | a suggested answer |
| `chat-clarify-text` | free-text answer. Typing **replaces** a chip selection |
| `chat-clarify-submit` | submit answers |
| `chat-clarify-skip-all` | skip every question |
| `chat-clarify-cancel-workflow` | **cancel the whole run** |

`chat-gate-choice-<choice>` is a **templated testid** — the suffix is the choice
value, so the set is data-dependent. Enumerate from `chat-gate-choice-prompt`'s
options rather than hard-coding.

`chat-clarify-text` exists because `clarify_engine.py` has two modes that offer no
chips at all: `short_text` ("user types freely") and `hybrid` ("MCQ suggestions plus
the free-text field will be shown automatically"). Before it, a `short_text`
question rendered as a question with nothing to answer it with.

---

```gherkin
Feature: IDE handoff with a valid token

  @S-22-01
  @sourced
  Scenario: A valid handoff opens the workflow for its run
    Given a valid, unexpired handoff token for my account
    When I cold-load "/handoff/{token}"
    Then I see the handoff shell with a header
    And I see the agent panel on the left
    And I see the preview panel on the right

  @S-22-02
  Scenario: An invalid token is refused without confirming anything
    When I cold-load "/handoff/invalid-token"
    Then I see "Handoff not found"
    And I am told it may not exist, may have expired, or may belong to another account
    And I see a link back to the dashboard
    # VERIFIED (p50). The three-cause message is deliberate: it must not confirm
    # to a stranger that a given token exists. Do not "improve" it into a
    # specific error.

  @S-22-03
  Scenario: Another user's handoff token is refused identically
    Given a handoff token issued to a different account
    When I cold-load it as myself
    Then I see exactly the "Handoff not found" screen
    And no detail of that handoff is revealed
    # Same screen, deliberately. This is the security assertion of the feature.

  @S-22-04
  @sourced
  Scenario: A handoff without a saved GitHub PAT asks for one first
    Given a valid handoff token
    And I have no GitHub token saved
    When I cold-load "/handoff/{token}"
    Then I see "One more step before this can run"
    And I am told the PAT needs "repo" scope
    And I am told the repository it will clone
    And I am told it is saved encrypted and never returned by any API
    And the integrations card is shown inline
    And I am told the "Start pipeline" button will activate after saving

  @S-22-05
  @sourced
  Scenario: Start pipeline is inert until a PAT exists
    Given a valid handoff token and no saved GitHub PAT
    Then "Start pipeline" is not actionable
    When I save a valid PAT
    Then "Start pipeline" becomes actionable

  @S-22-06
  @sourced
  Scenario: An expired handoff explains how to mint a new one
    Given a handoff token older than one hour
    When I cold-load "/handoff/{token}"
    Then I see "This handoff has expired"
    And I am told handoff URLs last one hour
    And I am told to re-run "/flowin-handoff" from my IDE

  @S-22-07
  @sourced
  Scenario Outline: Only a pending or failed handoff can be started
    Given a handoff whose status is "<status>"
    Then starting it is "<allowed>"

    Examples:
      | status    | allowed     |
      | pending   | offered     |
      | failed    | offered     |
      | running   | not offered |
      | completed | not offered |
    # canStart = pending || failed. A FAILED handoff is restartable — that is the
    # non-obvious half and the one worth a test.

  @S-22-08
  @sourced
  Scenario: The handoff shows the change it proposes
    Given a running handoff
    Then the preview panel shows a diff of the proposed change
    And I can select an agent to see its own output

  @S-22-09
  @sourced
  Scenario: Test and compliance reports render when produced
    Given a handoff that produced a test report
    Then a test report view is shown
    Given a handoff that produced a compliance report
    Then a compliance report view is shown
    # ReportViews exports both. Neither has been rendered.


Feature: Review gates

  @S-22-10
  @sourced
  Scenario: A run waiting at a gate offers the decision in the lane
    Given a run whose status is "waiting_for_user" at a review gate
    When I cold-load "/runs/{id}"
    Then "chat-gate-actions" is shown in the chat lane
    And I can approve, request changes, or reject

  @S-22-11
  @sourced
  Scenario: Approving continues the run
    Given a run waiting at a review gate
    When I activate "chat-gate-approve"
    Then the run continues
    And the lane records "Review approved — build continues"
    # That message IS captured (18-chat-lane) — its aftermath is all any sweep
    # has seen. This scenario covers the act that produces it.

  @S-22-12
  @sourced
  Scenario: Requesting changes takes instructions
    Given a run waiting at a review gate
    When I activate "chat-gate-request-changes"
    Then I can enter revision instructions
    And submitting them sends the run back for revision

  @S-22-13
  @sourced
  Scenario: A redo takes additional instructions
    Given a run waiting at a review gate
    When I choose to redo
    Then a field labelled "Additional instructions for redo" is offered
    And that field is named "redo-instructions"
    And "chat-gate-redo" submits it

  @S-22-14
  @sourced
  Scenario: The gated content itself is editable before approval
    Given a run waiting at a review gate
    Then the gated content is held in a field named "gate-content"
    And "Edit gate content" makes it editable
    # Approving edits the artifact as well as unblocking the run — the human is
    # not just a rubber stamp. Assert the edited content is what continues.

  @S-22-15
  @sourced
  Scenario: A choice gate presents its options
    Given a run waiting at a gate that asks the human to choose
    Then "chat-gate-choice-prompt" states the question
    And one "chat-gate-choice-<value>" control exists per option
    # The testid is TEMPLATED on the choice value, so the set is data-dependent.
    # Enumerate from the prompt's options; never hard-code the suffixes.

  @S-22-16
  @sourced
  Scenario: The gated content can be previewed before deciding
    Given a run waiting at a review gate
    Then "chat-gate-preview" shows what is being approved
    And "Edit gate content" allows amending it before approval

  @S-22-17
  @sourced
  Scenario: Rejecting ends the run
    Given a run waiting at a review gate
    When I activate "chat-gate-reject"
    Then the run does not continue
    And its terminal state reflects the rejection

  @S-22-18
  @sourced
  @destructive
  Scenario: Cancelling the run from a gate takes two steps
    Given a run waiting at a review gate
    When I activate "chat-gate-cancel"
    Then a confirmation opens in the slot below the decision
    And the run is still live until I confirm
    When I confirm
    Then the run is cancelled
    # KAN-95 made this a two-step confirm. `Cancel run` sits inline among the
    # ordinary gate decisions, and it is the only destructive one there.

  @S-22-19
  @sourced
  Scenario: The gate shows the evidence the decision is about
    Given a run waiting at a review gate
    Then "gate-well" holds what the run produced
    And its "data-well-kind" is "code" or "prose"
    And the block is height-capped and scrolls internally
    # Deliberately capped: this is evidence to check a decision against, not a
    # reading surface.

  @S-22-20
  @sourced
  Scenario: A code artifact can be copied out of the gate
    Given a run waiting at a gate whose artifact is code
    Then "gate-well" has "data-well-kind" of "code"
    When I activate "gate-well-copy"
    Then the artifact source is on the clipboard
    And the control reads "Copied" for about 1.5 seconds

  @S-22-21
  @sourced
  Scenario Outline: A readiness verdict is hoisted above the prose
    Given a run waiting at a gate whose artifact states "<verdict>"
    Then "gate-well-verdict" is shown above the artifact body
    And its "data-verdict-tone" is "<tone>"

    Examples:
      | verdict          | tone     |
      | READY            | ready    |
      | CAUTION advised  | caution  |
      | REVISION needed  | revision |
    # On an approval gate this is the most decision-relevant line in the whole
    # artifact. Left inside the body it reads as ordinary prose, which is how
    # it was lost once already.

  @S-22-22
  @sourced
  Scenario: A gate decision is the human's alone in the product
    Given a run waiting at a review gate
    Then nothing in the product answers the gate automatically
    # The PRODUCT never self-approves. Note that the phase-2 suite DOES answer
    # gates — see "Notes for phase 2" — because a smoke test cannot park
    # forever. That is a test fixture supplying a human's input, not the
    # product deciding for itself. The two are different claims and this
    # scenario only makes the first.


Feature: Clarifying questions

  @S-22-23
  @sourced
  Scenario: A run asking for clarifications offers them in the lane
    Given a run that has asked clarifying questions
    When I cold-load "/runs/{id}"
    Then "chat-clarify-actions" is shown
    And the lane message reads
        "Before I build, I need to lock a few things down."

  @S-22-24
  @sourced
  Scenario: Suggested answers are offered as chips
    Given a run asking clarifying questions
    Then one "chat-clarify-chip" is offered per suggestion
    When I select chips and submit with "chat-clarify-submit"
    Then the run continues
    And the lane records "Clarifications answered"

  @S-22-25
  @sourced
  Scenario: A free-text question can be answered without chips
    Given a run asking a "short_text" clarifying question
    Then no "chat-clarify-chip" is offered
    And "chat-clarify-text" accepts an answer
    When I type an answer and submit
    Then the run continues
    # `short_text` and `hybrid` offer no chips. Without this field the question
    # rendered with nothing to answer it with.

  @S-22-26
  @sourced
  Scenario: Typing overrides a selected chip
    Given a run asking a "hybrid" clarifying question
    When I select a "chat-clarify-chip"
    And I then type into "chat-clarify-text"
    Then the typed answer replaces the chip selection
    And only the typed answer is submitted

  @S-22-27
  @sourced
  Scenario: Every question can be skipped at once
    Given a run asking clarifying questions
    When I activate "chat-clarify-skip-all"
    Then the run continues without my answers

  @S-22-28
  @sourced
  @destructive
  Scenario: The whole run can be cancelled from the clarify prompt
    Given a run asking clarifying questions
    When I activate "chat-clarify-cancel-workflow"
    Then the run is cancelled
    And its lane reads "Cancelled by you"
    # This control CANCELS THE RUN from what looks like a question prompt. It
    # sits beside "skip all", which does the opposite. Worth its own test purely
    # because the two are adjacent and one is destructive.
```

## Notes for phase 2

- **Both halves need a fixture no seeded data provides.** Handoff needs a token
  minter; gates need a run parked at `waiting_for_user`. The gate fixture costs a
  live LLM run, and the run it produces must be answered by a human — which is the
  point of the feature, and why no sweep has produced one.
- **The suite answers gates — decided, with the reason.** An earlier draft here said
  not to build an auto-approver. That was overruled: a live smoke test cannot park
  forever waiting for a person, and `ex_A4_human_gate` and `ex_A4_human_divert` exist
  precisely to exercise this path. `approve_gate()` waits for the prompt, screenshots
  it **before** touching anything, clicks approve, and screenshots again — so the run
  folder holds proof of what was asked and what was answered.

  Two limits keep it honest. It answers only what a fixture is entitled to answer:
  the *approve* path on a workflow whose gate exists to be exercised. It never
  asserts that a gate can be bypassed, and the scenario above still pins that the
  product never self-approves. Reject and revise are separate tests, not something
  the helper does on the way past.
- `IntegrationsCard` is shared between `/handoff/settings` (captured, `p49`) and the
  handoff onboarding state. Its security scenarios live in
  `16-pages-outside-routes` — token never echoed, key shown once, no cross-account
  leakage — and apply to both mount points.
- The invalid-token screen is the security boundary. Its vagueness is a feature; the
  scenario above pins it so a future "clearer error" does not turn it into a token
  oracle.

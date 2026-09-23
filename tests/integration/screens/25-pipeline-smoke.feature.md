# Feature: Pipeline smoke

Every other spec in this directory asks a question about a **screen**. This one
asks the only question none of them do: **does the pipeline actually run?**

The 24 screen specs name the workflows constantly — as a card in the catalogue,
a heading on a launch panel, a label on a run row — but always as catalogue
*content*. Not one of them launches a pipeline and looks at what came out. A
suite can be complete against those specs and still have never proved that
`ppt` produces a deck.

**Scope: the five first-party pipelines.** The `ex_A*` fixtures, the `*_revision`
variants and the Coming Soon set are deliberately out of scope — those exercise
gate and branch mechanics, which belong with 22-handoff-and-gates.

| Workflow | Catalogue card | Deliverable strategy | Delivers |
|---|---|---|---|
| `ppt` | Pitch an idea | `ppt` | `presentation.pptx` |
| `ppt_v2` | Pitch an idea (v2) | `single_file` | `presentation.html` |
| `user_stories` | Generate product requirements | `streamed_text` | `user_stories.md` |
| `prototype` | Build an interactive prototype | `single_file` | `prototype.html` |
| `app_builder` | Build an end-to-end application | `serialized_sandbox` | a sandbox tree |

**Every scenario here is `@live` and `@destructive`.** Each one dispatches a real
run against a real model and leaves a real row in the history. None of them can
run in the offline tier, and the tier is skipped by default.

**Gates are answered, not avoided.** A pipeline that stops for a human is only
smoke-tested if something makes the decision, so the harness approves approval
gates and takes the first offered branch on a choice gate. Which branch runs is
not what a smoke test is asking; that a gated run *resumes at all* is.

**Briefs are hello-world scale on purpose.** The question is whether the pipeline
runs, gates, resumes and delivers — never whether the model wrote anything good.
Asserting on generated prose would make these tests fail on model drift, which
is the opposite of a smoke test.

**"Completed" is not the assertion.** A run can report completed while an agent
silently no-op'd, and it can write a correctly-named file with nothing in it.
Both read as green to a status check, so each scenario proves three separate
things:

| | What it catches |
|---|---|
| every roster agent reported, none errored, each consumed tokens | a step that was skipped or never reached the model |
| the deliverable is not zero bytes | a named empty file — the failure this suite exists for |
| the deliverable is structurally what it claims | a `.pptx` that is really a stack trace |

The structural check is deliberately shallow, and is **structure only**:

| | Must be |
|---|---|
| `.pptx` | a ZIP (`PK\x03\x04`) naming `ppt/presentation.xml` among its entries |
| `.html` | an `<html>` document with a `<body>` |
| `.md` | markdown carrying at least one ATX heading |

Nothing reads what the model wrote, so model drift can never fail these.

**Launching is driven from the UI, never the API.** `POST /api/runs` skips the
wizard's launch assembly — template choice, design system, the agent roster the
panel compiles — so an API-launched run does not exercise what a user's launch
does. Two of these five (`ppt`, `prototype`) are wizards.

**Screenshots:** none. These runs are non-deterministic by construction and a
fingerprint of one would be noise.

---

## Scenarios

  @S-25-01
  @live
  @destructive
  # live: dispatches a real run, so it cannot run in the offline tier.
  Scenario: Pitch an idea runs end to end and delivers a deck
    Given the catalogue card "Pitch an idea"
    When I launch it with a one-sentence brief
    And I answer every gate it stops at
    Then the run reaches a completed state
    And every agent in the roster ran without error
    And the run header names the workflow I launched
    And the workspace holds a non-empty deliverable named "presentation.pptx"
    And that file is a ZIP naming "ppt/presentation.xml"

  @S-25-02
  @live
  @destructive
  # live: dispatches a real run, so it cannot run in the offline tier.
  Scenario: Pitch an idea v2 runs end to end and delivers a deck
    Given the catalogue card "Pitch an idea (v2)"
    When I launch it with a one-sentence brief
    And I answer every gate it stops at
    Then the run reaches a completed state
    And every agent in the roster ran without error
    And the run header names the workflow I launched
    And the workspace holds a non-empty deliverable named "presentation.html"
    And that file is an HTML document with a body

  @S-25-03
  @live
  @destructive
  # live: dispatches a real run, so it cannot run in the offline tier.
  Scenario: Generate product requirements runs end to end and delivers a story set
    Given the catalogue card "Generate product requirements"
    When I launch it with a one-sentence brief
    And I answer every gate it stops at
    Then the run reaches a completed state
    And every agent in the roster ran without error
    And the run header names the workflow I launched
    And the workspace holds a non-empty deliverable named "user_stories.md"
    And that file carries at least one markdown heading

  @S-25-04
  @live
  @destructive
  # live: dispatches a real run, so it cannot run in the offline tier.
  Scenario: Build an interactive prototype runs end to end and delivers a page
    Given the catalogue card "Build an interactive prototype"
    When I launch it with a one-sentence brief
    And I answer every gate it stops at
    Then the run reaches a completed state
    And every agent in the roster ran without error
    And the run header names the workflow I launched
    And the workspace holds a non-empty deliverable named "prototype.html"
    And that file is an HTML document with a body

  @S-25-05
  @live
  @destructive
  # live: dispatches a real run, so it cannot run in the offline tier.
  Scenario: Build an end-to-end application runs end to end and delivers a sandbox
    Given the catalogue card "Build an end-to-end application"
    When I launch it with a one-sentence brief
    And I answer every gate it stops at
    Then the run reaches a completed state
    And every agent in the roster ran without error
    And the run header names the workflow I launched
    And the workspace holds at least one non-empty deliverable file

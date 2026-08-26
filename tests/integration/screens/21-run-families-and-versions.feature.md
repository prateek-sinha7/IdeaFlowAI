# Feature: Run families, versions and divert links

**Screenshots:** none — the dev DB has no multi-version run family, so the grouped
form of run history has never been rendered. `@sourced` throughout: selectors and
labels are read from `components/history/RevisionFamilyView.tsx` (811 loc, live —
imported by `WorkflowHistory` and `RunDetailPage`).

---

## Why this was missed for five sweeps

`/runs` was captured as a **flat list of 50 runs**, because every seeded run is a
family of one. `RevisionFamilyView` exports the whole grouped presentation —
`groupRunsByFamily`, `FamilyGroupCard`, `bucketAndSortFamilies`, `buildDivertLinks`,
`VersionTimeline` — and **none of it renders until a run has a revision**.

This is the largest body of unexercised UI logic in the product that is not behind a
defect.

## The pieces

| Export | Where it renders |
|---|---|
| `groupRunsByFamily` | collapses runs sharing a root into one family |
| `bucketAndSortFamilies` | date buckets (`TODAY`, …) × sort key |
| `FamilyGroupCard` | one row per family on `/runs` |
| `VersionTimeline` | the version strip on a run's detail page |
| `buildDivertLinks` | the two-way link between a diverting run and its target |
| `baseWorkflowType`, `filterBucketFor` | map a raw type onto a filter chip |

## Accessible names, verbatim from source

| Control | Accessible name |
|---|---|
| Per-row actions | `Run actions` |
| A single run row | `Open <title>, <status>` |
| A family's latest | `Open <title> (latest version), <status>` |
| Expand versions | `Show versions` / `Collapse versions` |
| Version count badge | `<n> versions`, rendered as `v<n>` |
| A version inside a family | `Version <i>, <status>` |
| A version on the timeline | `Version <i>, revises version <i-1>, <status>` |
| Timeline container | `Workflow versions` |
| Divert link (source) | `Diverted to <label>, open triggered run` |
| Divert link (target) | `Continued from <label>, open originating run` |

Note the **`v<n>` text and the `<n> versions` accessible name differ** — read the
aria-label, not the visible text.

## What `filterBucketFor` implies

`baseWorkflowType` strips revision suffixes so a family of `prototype` +
`prototype_revision` filters as one type. This is also the mechanism behind **D-15**
(`?type=presentation` matches nothing while the chip says `ppt`) and **D-11**
(analytics lists `PROTOTYPE` twice) — one mapping, three symptoms.

---

```gherkin
Feature: Run families on run history

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  @sourced
  Scenario: Runs sharing a root collapse into one family row
    Given a run that has been revised twice
    When I cold-load "/runs"
    Then those three runs appear as ONE row, not three
    And that row is labelled "Open <title> (latest version), <status>"
    And it shows a version badge reading "v3"

  @sourced
  Scenario: The version badge's accessible name is not its text
    Given a family of 3 versions
    Then the badge's visible text is "v3"
    And its accessible name is "3 versions"
    # Read the aria-label. A test matching on "v3" is matching presentation.

  @sourced
  Scenario: A family expands to show every version
    Given a family row with 3 versions
    When I activate "Show versions"
    Then I see 3 entries, each named "Version <i>, <status>"
    And the control becomes "Collapse versions"

  @sourced
  Scenario: A family of one renders as a plain row
    Given a run with no revisions
    When I cold-load "/runs"
    Then it appears as a single row named "Open <title>, <status>"
    And no version badge is shown
    And no expand control is shown
    # This is the ONLY shape any sweep has seen — all 50 seeded runs are families
    # of one. Everything above it is unrendered logic.

  @sourced
  Scenario: The family counts as one against a filter chip
    Given a family of a prototype run plus two prototype revisions
    When I cold-load "/runs"
    Then the Prototype chip counts that family ONCE
    # baseWorkflowType strips the _revision suffix. The chip counts families,
    # not runs — worth pinning, because "50 runs" and the chip totals are then
    # counting different things.

  @sourced
  Scenario Outline: Families bucket by date and reorder by sort
    Given families started on different days
    When I cold-load "/runs?sort=<sort>"
    Then families are grouped under date headings
    And within each heading they are ordered by "<key>"

    Examples:
      | sort     | key           |
      | (none)   | most recent   |
      | duration | longest first |
      | tokens   | most tokens   |
    # bucketAndSortFamilies does both at once. Sorting must not flatten the date
    # buckets, and a family's position should follow its LATEST member.


Feature: The version timeline on a run

  @sourced
  Scenario: A revised run shows its version timeline
    Given a run that is version 2 of a family
    When I cold-load "/runs/{id}"
    Then a region labelled "Workflow versions" is shown
    And it lists both versions

  @sourced
  Scenario: A timeline entry names what it revises
    Given a family of 3 versions
    When I open the timeline
    Then version 2 is named "Version 2, revises version 1, <status>"
    And version 1 is named "Version 1, <status>" with no revises clause
    # The first version has no parent_run_id, so its name has no revises clause.
    # A test asserting a uniform name shape fails on version 1 only.

  @sourced
  Scenario: Selecting a version navigates to it
    Given the version timeline is open
    When I select version 1
    Then I land on that version's run
    And its artifact is the one shown

  @defect
  # D-12, restated where the version UI is specified.
  Scenario: A version that does not exist is refused
    Given a run whose family has 2 versions
    When I cold-load "/runs/{id}/versions/99"
    Then I am told that version does not exist
    # Today it silently serves v1 with the URL still reading 99 — a shared link
    # to a removed version shows the wrong content with no indication.

  @sourced
  Scenario: A single-version run shows no timeline
    Given a run with no revisions
    When I cold-load "/runs/{id}"
    Then no "Workflow versions" region is shown
    # The shape every capture has seen.


Feature: Divert links

  @sourced
  Scenario: A diverting run links forward to the run it triggered
    Given a run that diverted into another workflow
    When I cold-load "/runs"
    Then its row carries a control named
         "Diverted to <label>, open triggered run"
    When I activate it
    Then I land on the triggered run

  @sourced
  Scenario: The triggered run links back to its origin
    Given a run that was started by a divert
    When I cold-load "/runs"
    Then its row carries a control named
         "Continued from <label>, open originating run"
    When I activate it
    Then I land on the originating run

  @sourced
  Scenario: The two directions are distinguishable
    Given both ends of a divert pair
    Then the source's link says "Diverted to"
    And the target's link says "Continued from"
    # buildDivertLinks assigns a direction per run. One shared assertion on
    # "divert" matches both and proves neither.

  @defect
  # Filed in 18-chat-lane. Restated here because this is where the fix belongs.
  Scenario: A diverted run's chat lane names its target
    Given a diverted run
    When I cold-load "/runs/{id}"
    Then the lane names the workflow it handed off to
    And offers a way to open the resulting run
    # Run history builds these links; the lane does not use them. Its last
    # message is "Review approved — build continues", identical to an ordinary
    # gate approval, so from the run page the handoff is invisible.
```

## Notes for phase 2

- **Everything in this file needs one fixture: a run family with revisions.** The dev
  DB has none, so all of it is unrendered. Creating one means running a workflow and
  then revising it — an LLM cost, but a *one-off* one that unlocks this entire file,
  the `Slides`/renderer variants, and D-12's real test.
- Assert on **accessible names, not visible text**. `v3` and `3 versions` are the
  same badge; the family/single distinction is carried entirely in the aria-label.
- The divert pair needs both ends, so the fixture is a divert workflow run to
  completion — `ex_A3_divert` exists and its target workflows (`Spanish Greeter`,
  `Dutch Greeter`) are seeded.
- `baseWorkflowType` is the shared root of D-11, D-15 and the family-counting
  behaviour above. Fixing the type mapping should be checked against all three.

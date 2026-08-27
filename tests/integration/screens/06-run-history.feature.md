# Feature: Run history

Every run the signed-in user has started, searchable, filterable by workflow type,
sortable, and grouped by time.

**Route:** `/runs` (accepts `?type=` and `?sort=`)
**Screenshot:** `16-run-history.png`

**Screenshots:** `05-runs/p22` history · `12-overlays/70` run actions menu

---

## What is on the screen

| Region | Content |
|---|---|
| H1 | "Run History" |
| Count | `<N> runs` |
| Refresh | `Refresh` button + an auto-refresh `<select>`: `Off`, `Every 10s`, `Every 15s`, `Every 30s`, `Every 1m` |
| Search | `input[name="history-search"]` |
| Type filters | `All <n>`, `User Stories <n>`, `Presentation <n>`, `Prototype <n>`, `App Builder <n>`, `Custom <n>` — each with a live count |
| Sort | `Newest`, `Longest`, `Tokens` |
| Groups | Date headers — `TODAY <n>`, then older groups |

Each row shows the brief excerpt, `<Workflow> · <N> agents`, an age, and — when
finished — a duration and token total. A running row shows `Running` instead.
Each row has a `button[aria-label="Run actions"]`.

**Divert adornments.** Rows in a divert relationship carry a badge:

- On the child: `← Continued from Human Handoff, step pick-language`
- On the parent: `Diverted to Dutch Greeter →`

The badge names the other run's **workflow**, not its title — deliberate, and it
stays that way. The `, step <id>` clause comes from the parent's persisted
`divertedAtStepId`; FIX-312 exists because `DivertBadge` never read it and the
clause was silently missing. **That clause is this screen's highest-value
assertion** — it regressed once and the unit tests passed throughout.

**Type filter vocabulary.** The filters use display names (`Presentation`), while
the rows name workflows (`PPT v2`, `Human Gate`). The six filters do not cover
every workflow that can appear — the capture showed 39 of 50 runs under `Custom`,
including all the conditional-gate fixtures.

---

```gherkin
Feature: Run history

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"
    And I have runs in more than one state

  @S-06-01
  Scenario: The history renders with its controls
    When I cold-load "/runs"
    Then I see the heading "Run History"
    And I see a run count
    And I see a search input named "history-search"
    And I see the sort controls "Newest", "Longest", "Tokens"
    And I see an auto-refresh selector defaulting to "Off"

  @S-06-02
  Scenario: Runs are grouped by time
    When I cold-load "/runs"
    Then I see a "TODAY" group header with a count
    And each group's header count equals the number of rows beneath it

  @S-06-03
  Scenario: A finished row shows its cost, a running row does not
    Given I have a completed run and a running run
    When I cold-load "/runs"
    Then the completed row shows a duration and a token total
    And the running row shows "Running" and no token total

  @S-06-04
  Scenario: Type filter counts sum to the total
    When I cold-load "/runs"
    Then the "All" filter's count equals the total run count
    And the sum of the other filters' counts equals the "All" count

  @S-06-05
  Scenario Outline: Filtering by type narrows the list
    When I cold-load "/runs"
    And I click the filter "<filter>"
    Then every visible row belongs to that workflow family
    And the visible row count equals the filter's own count

    Examples:
      | filter        |
      | User Stories  |
      | Presentation  |
      | Prototype     |
      | App Builder   |
      | Custom        |

  @S-06-06
  Scenario: The type filter is addressable by URL
    When I cold-load "/runs?type=ppt"
    Then the history is filtered to that type on a cold load
    And exactly 7 rows are shown, matching the Presentation chip's count
    # routes.runHistory({type, sort}) builds these params. A cold load must
    # honour them — this is the class of gap spec 015 closed elsewhere.
    # VERIFIED: ?type=custom → 39 rows, ?type=ppt → 7 rows, both matching
    # their chips. The filters do narrow correctly.

  @S-06-07
  Scenario: The chip label and its URL value are different words
    When I click the filter "Presentation"
    Then the URL becomes "/runs?type=ppt"
    # The chip says Presentation; the param says ppt. Do not derive one from
    # the other — the same mismatch that makes the next scenario a trap.

  @S-06-08
  @defect
  # D-15. An unrecognised type is treated as a filter matching nothing.
  Scenario: An unrecognised type shows an empty list rather than an error
    When I cold-load "/runs?type=presentation"
    Then I see "No runs match this filter"
    And the "Presentation" chip beside it still reads a count of 7
    # `presentation` is the obvious guess and what a stale link would carry.
    # The page shows an empty history that reads as data loss, while the chip
    # one line above contradicts it.
    # Expected once fixed: fall back to All, or say the filter is not
    # recognised. Not silence.

  @S-06-09
  Scenario: Sort is addressable by URL and composes with type
    When I cold-load "/runs?type=custom&sort=duration"
    Then the history is filtered to Custom and ordered by duration
    # Newest omits the param entirely — it is the default. A test asserting
    # "?sort=recent" after clicking Newest will fail; assert its absence.

  @S-06-10
  Scenario Outline: Sorting reorders the list
    When I cold-load "/runs"
    And I click "<sort>"
    Then the rows are ordered by "<key>", descending

    Examples:
      | sort    | key             |
      | Newest  | start time      |
      | Longest | duration        |
      | Tokens  | total tokens    |

  @S-06-11
  Scenario: Search filters by brief text
    When I cold-load "/runs"
    And I type a distinctive word from one run's brief into the search
    Then only rows whose brief contains that word remain
    When I clear the search
    Then the full list returns

  @S-06-12
  Scenario: Auto-refresh can be enabled and reports its interval
    When I cold-load "/runs"
    And I set auto-refresh to "Every 10s"
    Then the control reports "Every 10s"
    And the list refreshes without a full page reload

  @S-06-13
  Scenario: Refresh re-reads without losing filters
    When I cold-load "/runs"
    And I filter by "Presentation"
    And I click "Refresh"
    Then the "Presentation" filter is still applied

  @S-06-14
  Scenario: Opening a row lands on that run
    When I cold-load "/runs"
    And I click the first row
    Then the URL contains that run's id
    And I see that run's detail surface

  @S-06-15
  Scenario: A diverted child names its parent and the branching step
    Given a run that was diverted into from a parent run
    When I cold-load "/runs"
    Then that row shows a badge reading "← Continued from <parent workflow>, step <stepId>"
    And the step clause is present, not omitted
    # FIX-312. buildDivertLinks set stepId correctly and its unit tests passed —
    # DivertBadge just never read it, so the badge said "Continued from X" with
    # no indication of WHERE the parent branched. Unit tests cannot catch this.

  @S-06-16
  Scenario: A diverting parent names its child
    Given a run that diverted into a child workflow
    When I cold-load "/runs"
    Then that row shows a badge reading "Diverted to <child workflow> →"

  @S-06-17
  Scenario: The divert badge names the workflow, not the run title
    Given a divert pair
    When I cold-load "/runs"
    Then the badge text contains the other run's WORKFLOW name
    And it does NOT contain the other run's title
    # Deliberate and staying that way. Asserted so nobody "fixes" it.

  @S-06-18
  Scenario: Run actions are per-row
    When I cold-load "/runs"
    Then each row has its own "Run actions" control
    When I open the control on a specific row, scoped by that row's brief
    Then a menu of actions for THAT run opens

  @S-06-19
  Scenario: An empty history is explained
    Given I am signed in as a user with no runs
    When I cold-load "/runs"
    Then the run count reads zero
    And I am told there is nothing here yet, rather than shown a blank pane

  @S-06-20
  @defect
  # D-14. Run cards are div[role="button"], not links.
  Scenario: A run card can be opened in a new tab
    When I cold-load "/runs"
    Then each run row is an anchor whose href is that run's URL
    And ⌘-clicking a row opens it in a new tab
    And the run's URL is visible on hover
    # Written as the product SHOULD behave, not as it does — this one is a
    # capability the user does not have today, so there is no baseline to
    # record. Today every row is a div[role="button"] with a click handler:
    # no middle-click, no "Open in new tab", no copyable link.

  @S-06-21
  @defect
  # D-14, second half. The whole page has zero data-testid attributes.
  Scenario: Run history rows are addressable by a stable hook
    When I cold-load "/runs"
    Then each row carries a data-testid identifying its run
    # document.querySelectorAll('[data-testid]').length is 0 for this page.
    # Until that changes, every assertion here goes through text or DOM
    # structure and will break on a copy edit or a restyle.
```

## Notes for phase 2

- **The counts move.** Any run started by another scenario changes them. Capture
  the counts at the start of a scenario and assert relatively, or run this feature
  against an isolated account.
- The type-filter labels are display names, the row labels are workflow names.
  Do not cross them.
- `Run actions` repeats per row — same scoping hazard as `Workflow actions` on the
  saved-workflow cards.
- The auto-refresh select has no `name` in the capture (it appeared as
  `select[?]`). Give it one, or select it by its options, before writing a stable
  test against it.

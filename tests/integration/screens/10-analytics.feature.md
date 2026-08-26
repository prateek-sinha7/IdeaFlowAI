# Feature: Analytics

Token usage, cost and pipeline performance for the signed-in user.

**Route:** `/analytics` (accepts `?range=` and `?pipeline=`)
**Screenshot:** `35-analytics.png`

---

## What is on the screen

**H1** "Analytics", subtitle "Token usage · Cost · Pipeline performance".

**Range selector:** `Today`, `3d`, `7d`, `30d`, `90d`, `All`.
**Pipeline filter:** `select[name="pipeline-filter"]` — All pipelines, User Stories,
Presentation, Prototype, App Builder, Custom.

**Stat tiles:**

| Tile | Example | Sub-line |
|---|---|---|
| TOTAL TOKENS | 54.7M | 52.0M in · 2.8M out |
| EST. COST | $30.16 | across 140 completed runs |
| AVG / RUN | 227.1K | tokens per run |
| TOTAL RUNS | 241 | 140 completed · 33 failed |

**Daily Activity** — a bar chart, "Last 30 days", series `Tokens`, one datum per
active day.

**Success rate** — a percentage plus Completed / Failed / Total.

**By Pipeline Type** — one row per type: `<TYPE> <n> runs · <tokens> $<cost>`.
The capture showed APP BUILDER, PROTOTYPE, CUSTOM, .NET MIGRATION, MULESOFT
MIGRATION, PPT_V2, PRESENTATION, PROTOTYPE (again), USER STORIES.

---

## Two arithmetic oddities worth watching

1. **`PROTOTYPE` appeared twice** with different numbers (12 runs / 11.4M / $4.49
   and 8 runs / 2.4M / $0.86). Two distinct underlying pipeline types are almost
   certainly collapsing to one display label — most likely `prototype` and one of
   the tiered revision manifests (`prototype_large_revision`,
   `prototype_feature_revision`). Worth confirming, not yet filed.

2. **Success rate does not account for every run.** 140 completed + 33 failed = 173,
   against 241 total. 58% is 140/241, so the percentage is right and the
   Completed/Failed breakdown simply omits the other 68 (cancelled, running,
   waiting). The tile reads as if it were exhaustive.

3. **`PPT_V2` is displayed raw**, snake-cased and uppercased, next to properly
   labelled neighbours like `PRESENTATION` and `.NET MIGRATION`. A missing entry
   in the display-name map.

---

```gherkin
Feature: Analytics

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"
    And I have completed runs across more than one pipeline type

  Scenario: The analytics screen renders its tiles and controls
    When I cold-load "/analytics"
    Then I see the heading "Analytics"
    And I see the range controls "Today", "3d", "7d", "30d", "90d", "All"
    And I see a pipeline filter named "pipeline-filter"
    And I see tiles for TOTAL TOKENS, EST. COST, AVG / RUN and TOTAL RUNS

  Scenario: The token tile's in/out split sums to its total
    When I cold-load "/analytics"
    Then the TOTAL TOKENS sub-line's input and output values sum to the headline

  Scenario: Average per run is consistent with the totals
    When I cold-load "/analytics"
    Then AVG / RUN is approximately TOTAL TOKENS divided by the run count it cites

  Scenario: The success rate matches the run counts
    When I cold-load "/analytics"
    Then the success percentage equals completed divided by total, rounded
    # 140/241 = 58%. Note the Completed + Failed breakdown does NOT sum to Total
    # — cancelled, running and waiting runs are excluded from the breakdown but
    # included in Total. Assert the percentage against TOTAL, not against
    # completed + failed.

  Scenario Outline: Changing the range changes the data
    When I cold-load "/analytics"
    And I select the range "<range>"
    Then the tiles update
    And the daily activity chart covers that range

    Examples:
      | range |
      | Today |
      | 3d    |
      | 7d    |
      | 30d   |
      | 90d   |
      | All   |

  Scenario: Ranges are nested — a wider range never reports less
    When I cold-load "/analytics"
    And I note TOTAL RUNS for the range "7d"
    And I select the range "30d"
    Then TOTAL RUNS is greater than or equal to the 7d figure
    When I select the range "All"
    Then TOTAL RUNS is greater than or equal to the 30d figure
    # A monotonicity check. It needs no fixed fixture data and it catches
    # off-by-one range boundaries, which is the usual bug here.

  Scenario: The range is addressable by URL
    When I cold-load "/analytics?range=7d"
    Then the "7d" range is selected on a cold load

  Scenario: The pipeline filter narrows every tile
    When I cold-load "/analytics"
    And I select the pipeline "Presentation"
    Then every tile reflects only that pipeline
    And the By Pipeline Type breakdown shows only that type

  Scenario: The pipeline filter is addressable by URL
    When I cold-load "/analytics?pipeline=ppt"
    Then that pipeline filter is applied on a cold load

  Scenario: The pipeline breakdown sums to the totals
    When I cold-load "/analytics"
    And I select the range "All"
    Then the run counts in By Pipeline Type sum to TOTAL RUNS
    And the token figures sum to TOTAL TOKENS

  Scenario: Daily activity plots one bar per active day
    When I cold-load "/analytics"
    Then the chart is labelled "Last 30 days"
    And each plotted day carries a token figure
    And a day with no runs plots zero rather than being omitted

  @defect
  # Two display-layer bugs found in the capture. Neither is filed yet; both are
  # recorded here so phase 2 either confirms or clears them.
  Scenario: The pipeline breakdown shows a duplicated and a raw label
    When I cold-load "/analytics"
    And I select the range "All"
    Then the By Pipeline Type list contains "PROTOTYPE" more than once
    And it contains the raw identifier "PPT_V2" rather than a display name
    # Expected once fixed: each pipeline type appears exactly once, and every
    # label is a display name. The duplicate is most likely `prototype` and a
    # tiered revision manifest collapsing to the same label.

  Scenario: A user with no runs sees an empty state
    Given I am signed in as "qa-basic@flowinqa.com" with no runs
    When I cold-load "/analytics"
    Then all tiles report zero
    And I am shown an empty state rather than a broken chart

  Scenario: Analytics is scoped to the signed-in user
    Given another user has completed runs
    When I cold-load "/analytics" as a user with none
    Then I do not see the other user's totals
```

## Notes for phase 2

- **Assert relationships, never absolute figures.** Every number here moves with
  each run the suite itself starts. The tile-consistency and range-monotonicity
  scenarios above are designed to hold regardless of data.
- The `EST. COST` figure depends on model pricing; do not assert a currency value.
- The scoping scenario needs two accounts and is the only real security assertion
  on this screen — worth keeping.

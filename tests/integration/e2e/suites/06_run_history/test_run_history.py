"""Implements ../../../screens/06-run-history.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Nothing here asserts an absolute count.** Every run any other scenario starts
lands on this screen, so each test reads the chip or the headline first and
asserts the relationship between that and what is rendered.

Three divert scenarios (S-06-15..17) skip: this account's history holds no
divert pair, and one cannot be manufactured offline. The live tier creates one
in 22_handoff_and_gates.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_history as L


def open_history(page, query: str = "") -> None:
    page.goto(f"/runs{query}")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
    # The list arrives after the heading. Either a row or the empty-state line
    # means the fetch has settled — waiting on rows alone hangs on an empty
    # history.
    page.wait_for_function(
        """() => document.querySelector('div[role=button][aria-label^="Open "]')
                || /No runs|runs?\\b/.test(document.body.innerText)"""
    )
    page.wait_for_timeout(settings.SETTLE_MS // 4)


@pytest.mark.scenario("S-06-01")
def test_the_history_renders_with_its_controls(page, shot):
    """Scenario: The history renders with its controls"""
    with shot("run-history", 'When I cold-load "/runs"'):
        open_history(page)

    assert L.total(page) >= 0
    expect(page.locator(L.SEARCH)).to_be_visible()
    for label, accessible in L.SORTS.items():
        expect(page.get_by_role("button", name=accessible, exact=True)).to_be_visible()

    auto = page.locator(L.AUTO_REFRESH)
    expect(auto).to_be_visible()
    # The default is the FIRST option, whose text carries the control's own
    # label ("Auto-refresh: Off") rather than a bare "Off".
    assert "Off" in auto.locator("option").first.inner_text()


@pytest.mark.scenario("S-06-02")
def test_runs_are_grouped_by_time(page, shot):
    """Scenario: Runs are grouped by time"""
    with shot("groups", 'When I cold-load "/runs"'):
        open_history(page)

    groups = L.group_counts(page)
    assert groups, "the history rendered no date groups"
    # Per-group row counting would need a hook the page does not have (D-14),
    # so the assertion is that the groups between them account for every row —
    # which fails just as loudly if one group's header lies.
    assert sum(groups) == len(L.rows(page)), (
        f"the group headers claim {sum(groups)} runs, {len(L.rows(page))} rows are drawn"
    )


@pytest.mark.scenario("S-06-03")
def test_a_finished_row_shows_its_cost_a_running_row_does_not(page, shot):
    """Scenario: A finished row shows its cost, a running row does not"""
    with shot("row-costs", 'When I cold-load "/runs"'):
        open_history(page)

    labels, texts = L.rows(page), L.row_texts(page)
    done = [t for label, t in zip(labels, texts) if L.status_of(label) == "completed"]
    assert done, "no completed run in this history to assert against"
    for text in done:
        assert L.duration_seconds(text) is not None, f"a completed row has no duration: {text!r}"
        assert L.tokens(text) is not None, f"a completed row has no token total: {text!r}"

    running = [t for label, t in zip(labels, texts) if L.status_of(label) == "running"]
    if not running:
        pytest.skip("no run is in flight; the running half belongs to the live tier")
    for text in running:
        assert "Running" in text
        assert L.tokens(text) is None, f"a running row published a token total: {text!r}"


@pytest.mark.scenario("S-06-04")
def test_type_filter_counts_sum_to_the_total(page, shot):
    """Scenario: Type filter counts sum to the total"""
    with shot("type-filters", 'When I cold-load "/runs"'):
        open_history(page)

    all_count = L.chip_count(page, "All")
    assert all_count == L.total(page)
    named = sum(L.chip_count(page, label) for label in L.TYPE_PARAMS)
    assert named == all_count, (
        f"the named filters account for {named} of {all_count} runs — a run that "
        "belongs to no chip cannot be found by filtering"
    )


@pytest.mark.scenario("S-06-05")
@pytest.mark.parametrize("label", list(L.TYPE_PARAMS))
def test_filtering_by_type_narrows_the_list(page, shot, label):
    """Scenario: Filtering by type narrows the list"""
    open_history(page)
    expected = L.chip_count(page, label)

    with shot(f"filter-{L.TYPE_PARAMS[label]}", f'When I click the filter "{label}"'):
        L.chip(page, label).first.click()
        page.wait_for_url(f"**type={L.TYPE_PARAMS[label]}")
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    assert len(L.rows(page)) == expected, (
        f"the {label} chip promised {expected} rows, the list drew {len(L.rows(page))}"
    )


@pytest.mark.scenario("S-06-06")
def test_the_type_filter_is_addressable_by_url(page, shot):
    """Scenario: The type filter is addressable by URL"""
    with shot("type-cold", 'When I cold-load "/runs?type=ppt"'):
        open_history(page, "?type=ppt")

    # The chip's own count, not the spec's literal 7 — every run the suite
    # starts moves it.
    assert len(L.rows(page)) == L.chip_count(page, "Presentation")


@pytest.mark.scenario("S-06-07")
def test_the_chip_label_and_its_url_value_are_different_words(page, shot):
    """Scenario: The chip label and its URL value are different words"""
    open_history(page)

    with shot("chip-param", 'When I click the filter "Presentation"'):
        L.chip(page, "Presentation").first.click()
        page.wait_for_url("**type=ppt")

    assert "type=ppt" in page.url and "type=presentation" not in page.url


@pytest.mark.scenario("S-06-08")
@pytest.mark.defect
def test_an_unrecognised_type_shows_an_empty_list_rather_than_an_error(page, shot):
    """Scenario: An unrecognised type shows an empty list rather than an error

    Asserts TODAY'S behaviour — D-15. `presentation` is the obvious guess and
    what a stale link carries; the page answers with an empty history that reads
    as data loss, while the chip one line above still reports a non-zero count.
    """
    with shot("unrecognised-type", 'When I cold-load "/runs?type=presentation"'):
        open_history(page, "?type=presentation")

    expect(page.get_by_text(L.EMPTY_FILTER)).to_be_visible()
    assert L.chip_count(page, "Presentation") > 0, (
        "the Presentation chip now reads zero as well — the contradiction D-15 "
        "records has gone, so re-read that defect before changing this test"
    )


@pytest.mark.scenario("S-06-09")
def test_sort_is_addressable_by_url_and_composes_with_type(page, shot):
    """Scenario: Sort is addressable by URL and composes with type"""
    with shot("type-and-sort", 'When I cold-load "/runs?type=custom&sort=duration"'):
        open_history(page, "?type=custom&sort=duration")

    assert len(L.rows(page)) == L.chip_count(page, "Custom")
    # Within each date group, not across the list — see `L.segments`.
    for group in L.segments(page):
        durations = [d for d in (L.duration_seconds(t) for t in group) if d is not None]
        assert durations == sorted(durations, reverse=True), (
            f"a date group is not ordered by duration: {durations}"
        )


@pytest.mark.scenario("S-06-10")
@pytest.mark.parametrize(
    ("label", "read"),
    [("Newest", "age"), ("Longest", "duration"), ("Tokens", "tokens")],
)
def test_sorting_reorders_the_list(page, shot, label, read):
    """Scenario: Sorting reorders the list"""
    open_history(page)

    with shot(f"sort-{read}", f'When I click "{label}"'):
        # By accessible name: the aria-label ("Sort by duration") overrides the
        # visible text ("Longest"), so a text match finds nothing.
        page.get_by_role("button", name=L.SORTS[label], exact=True).click()
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    reader = {"age": L.age_minutes, "duration": L.duration_seconds, "tokens": L.tokens}[read]
    groups = [
        [v for v in (reader(t) for t in group) if v is not None] for group in L.segments(page)
    ]
    assert sum(len(g) for g in groups) > 1, f"too few rows carry a {read} to check the ordering"

    for values in groups:
        # The sort applies WITHIN a date group. A run from today that took five
        # minutes still sits above one from last week that took forty-five, so a
        # monotonic check over the flat list fails on correctly-ordered data.
        expected = sorted(values) if read == "age" else sorted(values, reverse=True)
        assert values == expected, f"a date group is not ordered by {read}: {values}"


@pytest.mark.scenario("S-06-11")
def test_search_filters_by_brief_text(page, shot):
    """Scenario: Search filters by brief text"""
    open_history(page)
    before = len(L.rows(page))
    # Taken from a row that is actually on the screen rather than hard-coded:
    # the seed data is not fixed.
    word = max(L.rows(page)[0].split(",")[0].replace("Open ", "").split(), key=len)

    with shot("search", f'When I search for "{word}"'):
        page.fill(L.SEARCH, word)
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    matched = L.rows(page)
    assert 0 < len(matched) <= before
    for label in matched:
        assert word.lower() in label.lower(), f"unmatched row survived: {label!r}"

    with shot("search-cleared", "When I clear the search"):
        page.fill(L.SEARCH, "")
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    assert len(L.rows(page)) == before


@pytest.mark.scenario("S-06-12")
def test_auto_refresh_can_be_enabled_and_reports_its_interval(page, shot):
    """Scenario: Auto-refresh can be enabled and reports its interval"""
    open_history(page)
    auto = page.locator(L.AUTO_REFRESH)

    try:
        with shot("auto-refresh", 'When I set auto-refresh to "Every 10s"'):
            auto.select_option(label="Every 10s")
            page.wait_for_timeout(settings.SETTLE_MS // 3)

        assert auto.locator("option:checked").inner_text() == "Every 10s"
        # No full page reload: the heading node survives, which it would not
        # across a navigation.
        expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
        assert len(L.rows(page)) > 0
    finally:
        # A 10s poll left running would keep re-rendering under every later
        # scenario in this module.
        auto.select_option(index=0)


@pytest.mark.scenario("S-06-13")
def test_refresh_re_reads_without_losing_filters(page, shot):
    """Scenario: Refresh re-reads without losing filters"""
    open_history(page)
    expected = L.chip_count(page, "Presentation")
    L.chip(page, "Presentation").first.click()
    page.wait_for_url("**type=ppt")

    with shot("refresh", 'When I click "Refresh"'):
        page.click(L.REFRESH)
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert "type=ppt" in page.url
    assert len(L.rows(page)) == expected


@pytest.mark.scenario("S-06-14")
def test_opening_a_row_lands_on_that_run(page, shot):
    """Scenario: Opening a row lands on that run"""
    open_history(page)
    first = page.locator(L.ROW).first
    label = first.get_attribute("aria-label")

    with shot("open-row", "When I click the first row"):
        first.click()
        page.wait_for_url(lambda url: "/runs/" in url or "/results" in url)

    assert page.url.rstrip("/") != f"{settings.BASE_URL}/runs"
    excerpt = label.replace("Open ", "").rsplit(",", 1)[0]
    expect(page.get_by_text(excerpt[:40], exact=False).first).to_be_visible()


# ── divert adornments ────────────────────────────────────────────────────────

_NO_DIVERT = "this account's history holds no divert pair; 22_handoff_and_gates makes one live"


@pytest.mark.scenario("S-06-15")
@pytest.mark.skip(reason=_NO_DIVERT)
def test_a_diverted_child_names_its_parent_and_the_branching_step(page, shot):
    """Scenario: A diverted child names its parent and the branching step"""


@pytest.mark.scenario("S-06-16")
@pytest.mark.skip(reason=_NO_DIVERT)
def test_a_diverting_parent_names_its_child(page, shot):
    """Scenario: A diverting parent names its child"""


@pytest.mark.scenario("S-06-17")
@pytest.mark.skip(reason=_NO_DIVERT)
def test_the_divert_badge_names_the_workflow_not_the_run_title(page, shot):
    """Scenario: The divert badge names the workflow, not the run title"""


# ── per-row controls, empty state, and the two recorded gaps ─────────────────


@pytest.mark.scenario("S-06-18")
def test_run_actions_are_per_row(page, shot):
    """Scenario: Run actions are per-row"""
    open_history(page)
    rows = L.rows(page)
    assert page.locator(L.RUN_ACTIONS).count() == len(rows), (
        "the Run actions control does not repeat once per row"
    )

    # Scoped by the row's own aria-label, not by index: the list re-sorts and a
    # positional lookup would open a different run's menu.
    with shot("run-actions", "When I open the control on a specific row"):
        # `.first` on both: two runs launched from the same brief share an
        # aria-label, so the row selector is not unique either.
        page.locator(f'{L.ROW}[aria-label="{rows[1]}"]').first.locator(
            L.RUN_ACTIONS
        ).first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    expect(page.locator('[role="menu"], [role="menuitem"]').first).to_be_visible()


@pytest.mark.scenario("S-06-19")
@pytest.mark.role("basic")
def test_an_empty_history_is_explained(page, shot):
    """Scenario: An empty history is explained"""
    with shot("empty-history", 'When I cold-load "/runs" as a user with no runs'):
        open_history(page)

    if L.total(page) != 0:
        pytest.skip("the basic account has runs; this scenario needs an untouched user")

    expect(page.locator(L.ROW)).to_have_count(0)
    body = page.evaluate("() => document.body.innerText")
    assert any(
        phrase in body for phrase in ("No runs", "nothing here", "haven't run", "Get started")
    ), "an empty history rendered a blank pane with no explanation"


@pytest.mark.scenario("S-06-20")
@pytest.mark.defect
def test_a_run_card_can_be_opened_in_a_new_tab(page, shot):
    """Scenario: A run card can be opened in a new tab

    Asserts TODAY'S behaviour, which is the ABSENCE of the capability — D-14.
    Every row is a `div[role="button"]` with a click handler: no middle-click,
    no "Open in new tab", no copyable link. When rows become anchors this test
    fails, which is the intended signal to rewrite it as the spec's version.
    """
    with shot("rows-are-not-links", 'When I cold-load "/runs"'):
        open_history(page)

    assert page.locator(f"{L.ROW} a[href], a[href*='/runs/']").count() == 0, (
        "run rows now expose an href — D-14 is fixed; rewrite this test as the "
        "spec's S-06-20, which asserts the anchor"
    )
    assert len(L.rows(page)) > 0


@pytest.mark.scenario("S-06-21")
@pytest.mark.defect
def test_run_history_rows_are_addressable_by_a_stable_hook(page, shot):
    """Scenario: Run history rows are addressable by a stable hook

    Asserts TODAY'S behaviour — D-14, second half. The screen carries no
    `data-testid` at all, which is why every locator in this module goes through
    an aria-label or the rendered text.
    """
    with shot("no-testids", 'When I cold-load "/runs"'):
        open_history(page)

    assert page.locator("main [data-testid]").count() == 0, (
        "the run history grew testids — D-14 is fixed; move this module's "
        "locators onto them and rewrite this test"
    )

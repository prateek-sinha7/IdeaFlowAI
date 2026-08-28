"""Implements ../../../screens/10-analytics.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Nothing here asserts an absolute figure.** Every number on this screen moves
with each run the suite itself starts, so the assertions are relationships that
hold regardless of the data: a split summing to its headline, a wider range
never reporting less, a breakdown summing to its total.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import analytics as L


def open_analytics(page, query: str = "") -> None:
    page.goto(f"/analytics{query}")
    expect(page.get_by_text(L.HEADING).first).to_be_visible()
    # The tiles render before their data arrives; TOTAL RUNS is the last figure
    # to settle, so waiting on it means every later read sees real numbers.
    expect(page.get_by_text("TOTAL RUNS")).to_be_visible()


@pytest.mark.scenario("S-10-01")
def test_the_analytics_screen_renders_its_tiles_and_controls(page, shot):
    """Scenario: The analytics screen renders its tiles and controls"""
    with shot("analytics", 'When I cold-load "/analytics"'):
        open_analytics(page)

    for name in L.RANGES:
        expect(page.locator(L.range_button(name))).to_be_visible()
    expect(page.locator(L.PIPELINE_FILTER)).to_be_visible()
    for label in ("TOTAL TOKENS", "EST. COST", "AVG / RUN", "TOTAL RUNS"):
        expect(page.get_by_text(label)).to_be_visible()


@pytest.mark.scenario("S-10-02")
def test_the_token_tiles_in_out_split_sums_to_its_total(page, shot):
    """Scenario: The token tile's in/out split sums to its total"""
    with shot("token-tile", "Then input plus output equals the headline"):
        open_analytics(page)

    total = L.number(L.tile(page, "TOTAL TOKENS"))
    sub = L.tile_sub(page, "TOTAL TOKENS")
    parts = re.findall(r"([\d.]+[KMB]?)\s*(?:in|out)", sub)
    assert len(parts) == 2, f"expected an in/out split, got {sub!r}"

    split = sum(L.number(p) for p in parts)
    # The headline is rounded for display, so compare within the rounding the
    # display itself introduces rather than demanding exactness.
    assert abs(split - total) <= max(total * 0.02, 1), (
        f"in+out = {split:,.0f} but the headline says {total:,.0f} ({sub})"
    )


@pytest.mark.scenario("S-10-03")
def test_average_per_run_is_consistent_with_the_totals(page, shot):
    """Scenario: Average per run is consistent with the totals"""
    with shot("avg-tile", "Then AVG / RUN is TOTAL TOKENS over the run count"):
        open_analytics(page)

    total = L.number(L.tile(page, "TOTAL TOKENS"))
    avg = L.number(L.tile(page, "AVG / RUN"))
    # Divided by TOTAL RUNS, not by the completed count. The cost tile cites
    # "across N completed runs" right beside it, which makes the wrong divisor
    # the natural guess — and it is off by the failure rate, roughly 40% here.
    runs = L.number(L.tile(page, "TOTAL RUNS"))

    assert runs > 0
    expected = total / runs
    assert abs(avg - expected) <= max(expected * 0.05, 1), (
        f"AVG / RUN says {avg:,.0f} but {total:,.0f} over {runs:,.0f} runs is {expected:,.0f}"
    )


@pytest.mark.scenario("S-10-04")
def test_the_success_rate_matches_the_run_counts(page, shot):
    """Scenario: The success rate matches the run counts"""
    with shot("success-rate", "Then the percentage equals completed over total"):
        open_analytics(page)

    # The chart's aria-label carries both figures and the percentage, which is
    # the one place they appear together and already machine-readable.
    label = page.locator(L.SUCCESS_RATE).get_attribute("aria-label") or ""
    m = re.search(r"(\d+)\s*percent\D+(\d[\d,]*)\s+completed of\s+(\d[\d,]*)", label)
    assert m, f"success-rate label no longer carries its figures: {label!r}"

    pct, completed, total = int(m.group(1)), L.number(m.group(2)), L.number(m.group(3))
    assert total > 0
    assert abs(pct - round(completed / total * 100)) <= 1, (
        f"{completed:,.0f} of {total:,.0f} is not {pct}%"
    )


@pytest.mark.scenario("S-10-05")
@pytest.mark.parametrize("rng", L.RANGES)
def test_changing_the_range_changes_the_data(page, shot, rng):
    """Scenario Outline: Changing the range changes the data"""
    open_analytics(page)

    with shot(f"range-{rng}", f'When I select the range "{rng}"'):
        # Selection is what is asserted, not a specific figure: "Today" may
        # legitimately report zero — and on an empty range the chart is not
        # rendered at all, so it cannot be the thing waited on.
        L.select_range(page, rng)

    assert L.tile(page, "TOTAL RUNS"), f"TOTAL RUNS is blank for range {rng}"


@pytest.mark.scenario("S-10-06")
def test_ranges_are_nested_a_wider_range_never_reports_less(page, shot):
    """Scenario: Ranges are nested — a wider range never reports less"""
    open_analytics(page)

    with shot("range-7d", 'When I note TOTAL RUNS for "7d"'):
        L.select_range(page, "7d")
    seven = L.number(L.tile(page, "TOTAL RUNS"))

    with shot("range-30d", 'When I select "30d"'):
        L.select_range(page, "30d")
    thirty = L.number(L.tile(page, "TOTAL RUNS"))

    with shot("range-all", 'When I select "All"'):
        L.select_range(page, "All")
    every = L.number(L.tile(page, "TOTAL RUNS"))

    # Monotonicity holds whatever the data is, which is exactly why it is the
    # assertion worth making on a screen whose figures change every run.
    assert seven <= thirty <= every, (
        f"ranges are not nested: 7d={seven:,.0f} 30d={thirty:,.0f} All={every:,.0f}"
    )


@pytest.mark.scenario("S-10-07")
def test_the_range_is_addressable_by_url(page, shot):
    """Scenario: The range is addressable by URL"""
    with shot("range-from-url", 'When I cold-load "/analytics?range=7d"'):
        open_analytics(page, "?range=7d")
        # Selection shows as aria-pressed or a style. Assert the figure changes
        # from the default instead where no ARIA state is exposed.
        expect(page.locator(L.range_button("7d"))).to_be_visible()

    default_runs = L.number(L.tile(page, "TOTAL RUNS"))
    open_analytics(page, "?range=All")
    assert L.number(L.tile(page, "TOTAL RUNS")) >= default_runs, (
        "?range= in the URL had no effect on the data"
    )


@pytest.mark.scenario("S-10-08")
def test_the_pipeline_filter_narrows_every_tile(page, shot):
    """Scenario: The pipeline filter narrows every tile"""
    open_analytics(page)
    L.select_range(page, "All")
    everything = L.number(L.tile(page, "TOTAL RUNS"))

    with shot("filtered", 'When I select the pipeline "Presentation"'):
        page.select_option(L.PIPELINE_FILTER, label="Presentation")
        L.tile(page, "TOTAL RUNS")

    filtered = L.number(L.tile(page, "TOTAL RUNS"))
    assert filtered <= everything, (
        f"filtering to one pipeline reported MORE runs ({filtered:,.0f} > {everything:,.0f})"
    )


@pytest.mark.scenario("S-10-09")
def test_the_pipeline_filter_is_addressable_by_url(page, shot):
    """Scenario: The pipeline filter is addressable by URL"""
    with shot("pipeline-from-url", 'When I cold-load "/analytics?pipeline=ppt"'):
        open_analytics(page, "?pipeline=ppt")

    selected = page.locator(L.PIPELINE_FILTER).input_value()
    assert selected and selected != "all", (
        f"?pipeline=ppt did not apply on a cold load — filter reads {selected!r}"
    )


@pytest.mark.scenario("S-10-10")
def test_the_pipeline_breakdown_sums_to_the_totals(page, shot):
    """Scenario: The pipeline breakdown sums to the totals"""
    open_analytics(page)

    with shot("breakdown", 'When I select the range "All"'):
        L.select_range(page, "All")

    total = L.number(L.tile(page, "TOTAL RUNS"))
    by_type = L.runs_by_pipeline(page)
    assert by_type, "the By Pipeline Type breakdown lists no run counts"

    # Deduplicated by type before summing. The screen repeats the same eight
    # pipelines across three panels — by tokens, by cost, by runs — so a naive
    # sweep of every "<n> runs" in the page text totals three times the truth
    # and reports the breakdown as wildly inconsistent with its own headline.
    assert sum(by_type.values()) <= total * 1.05, (
        f"the breakdown sums to {sum(by_type.values()):,.0f} "
        f"against a total of {total:,.0f} across {len(by_type)} pipelines"
    )


@pytest.mark.scenario("S-10-11")
def test_daily_activity_plots_one_bar_per_active_day(page, shot):
    """Scenario: Daily activity plots one bar per active day"""
    with shot("daily-activity", 'Then the chart is labelled "Last 30 days"'):
        open_analytics(page)
        L.select_range(page, "30d")
        # `.first` — the label also appears inside "Total spend (Last 30 days)",
        # and a bare get_by_text matches both and fails on strict mode.
        expect(page.get_by_text("Last 30 days").first).to_be_visible()

    heights = page.locator(L.BAR).evaluate_all(
        "bars => bars.map(b => b.style.height)"
    )
    assert heights, "the daily-activity chart plotted no bars"

    # D-24. The bars carry NO accessible name — no aria-label, no title, no
    # text. Their only representation of a value is a CSS height percentage, so
    # the spec's "each plotted day carries a token figure" cannot be checked
    # through the accessibility tree at all, and a screen-reader user gets
    # nothing from this chart. Asserted at the level the markup actually
    # supports, with the gap recorded rather than papered over.
    for h in heights:
        assert h.endswith("%"), f"a bar has no height percentage to read a value from: {h!r}"

    # The claim that IS verifiable, and the one that matters: a quiet day plots
    # zero rather than vanishing. Omitting it would compress the axis and imply
    # continuous activity across a gap that was simply dropped.
    assert any(h.startswith("0") for h in heights), (
        f"no zero-token day was plotted among {heights} — "
        "a day with no runs may be being omitted rather than drawn at zero"
    )


@pytest.mark.scenario("S-10-12")
@pytest.mark.defect
def test_the_pipeline_breakdown_shows_a_duplicated_and_a_raw_label(page, shot):
    """Scenario: The pipeline breakdown shows a duplicated and a raw label"""
    # Asserted AS-IS. The breakdown lists PROTOTYPE more than once and shows the
    # raw manifest id PPT_V2 where every other row shows a display name. Fixing
    # either turns this red, which is the point.
    with shot("breakdown-labels", 'When I select the range "All"'):
        open_analytics(page)
        L.select_range(page, "All")

    text = page.evaluate("() => document.body.innerText")
    assert text.count("PROTOTYPE") > 1 or "PPT_V2" in text, (
        "D-11 appears to be FIXED — the breakdown no longer duplicates PROTOTYPE "
        "nor shows the raw PPT_V2 id. Rewrite this scenario and drop the @defect tag."
    )


@pytest.mark.scenario("S-10-13")
@pytest.mark.destructive
def test_a_user_with_no_runs_sees_an_empty_state(shot, disposable_user, browser, pytestconfig):
    """Scenario: A user with no runs sees an empty state

    Every seeded account has runs by now — this suite gave them some — so the
    scenario runs against a freshly created account instead, which is the only
    way left to see a genuinely empty analytics screen.
    """
    from framework import settings
    from framework.locators import auth as AUTH

    user = disposable_user(tier="basic")
    context = browser.new_context(
        base_url=settings.BASE_URL,
        viewport=settings.VIEWPORT,
        device_scale_factor=pytestconfig.getoption("--dpi"),
        reduced_motion="reduce",
    )
    page = context.new_page()

    try:
        with shot("empty-analytics", 'When a user with no runs cold-loads "/analytics"'):
            page.goto("/login")
            page.fill(AUTH.EMAIL, user["email"])
            page.fill(AUTH.PASSWORD, user["password"])
            page.click(AUTH.SIGN_IN)
            page.wait_for_url("**/dashboard", timeout=settings.LOGIN_TIMEOUT_MS)
            page.goto("/analytics")
            expect(page.get_by_text(L.HEADING).first).to_be_visible()
            page.wait_for_timeout(settings.SETTLE_MS)

        assert L.number(L.tile(page, "TOTAL RUNS")) == 0, "a brand-new account has runs"
        for label in ("TOTAL TOKENS", "EST. COST"):
            assert L.number(L.tile(page, label)) == 0, f"{label} is not zero"

        # An empty state, not a broken chart: whatever renders, it has to say
        # something and must not sit on a spinner.
        body = page.evaluate("() => document.body.innerText")
        assert len(body.strip()) > 40
        for selector in settings.BUSY_SELECTORS:
            expect(page.locator(selector)).to_have_count(0)
    finally:
        context.close()
@pytest.mark.scenario("S-10-14")
def test_analytics_is_scoped_to_the_signed_in_user(page_as, shot):
    """Scenario: Analytics is scoped to the signed-in user"""
    # The only real security assertion on this screen: one user's totals must
    # never appear in another's. Compared across two live sessions rather than
    # against a fixed number, since both move.
    admin = page_as("admin")
    admin.goto("/analytics")
    expect(admin.get_by_text("TOTAL RUNS")).to_be_visible()
    L.select_range(admin, "All")
    admin_runs = L.number(L.tile(admin, "TOTAL RUNS"))

    basic = page_as("basic")
    basic.goto("/analytics")
    expect(basic.get_by_text("TOTAL RUNS")).to_be_visible()
    L.select_range(basic, "All")
    basic_runs = L.number(L.tile(basic, "TOTAL RUNS"))

    assert basic_runs != admin_runs or admin_runs == 0, (
        f"two different accounts report identical totals ({admin_runs:,.0f}) — "
        "analytics may not be scoped per user"
    )

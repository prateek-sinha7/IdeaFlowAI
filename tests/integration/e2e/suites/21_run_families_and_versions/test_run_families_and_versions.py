"""Implements ../../../screens/21-run-families-and-versions.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Every run in this database is a family of one.** No run has been revised and
no run has diverted, so the collapse, the version timeline and the divert links
are all unrendered logic. What CAN be asserted is the degenerate shape — and,
just as usefully, that it really is degenerate: S-21-04 and S-21-11 fail the day
a family of two appears, which is the signal that the rest of this module can be
written properly.

The version badge's accessible name is "3 versions" while its visible text is
"v3". A test matching on "v3" is matching presentation.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD
from framework.locators import run_history as RH

VERSIONS_REGION = "Workflow versions"

_NO_FAMILY = (
    "every run in this history is a family of one — no run has been revised, so "
    "the family UI never renders"
)
_NO_DIVERT = (
    "no run in this history diverted — 22_handoff_and_gates creates the pair in "
    "the live tier"
)


def open_history(page, query: str = "") -> None:
    page.goto(f"/runs{query}")
    expect(page.locator(RH.ROW).first).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)


def a_run(page) -> str:
    open_history(page)
    page.locator(RH.ROW).first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


# ── families on run history ──────────────────────────────────────────────────


@pytest.mark.scenario("S-21-01")
@pytest.mark.skip(reason=_NO_FAMILY)
def test_runs_sharing_a_root_collapse_into_one_family_row(page, shot):
    """Scenario: Runs sharing a root collapse into one family row"""


@pytest.mark.scenario("S-21-02")
@pytest.mark.skip(reason=_NO_FAMILY)
def test_the_version_badges_accessible_name_is_not_its_text(page, shot):
    """Scenario: The version badge's accessible name is not its text"""


@pytest.mark.scenario("S-21-03")
@pytest.mark.skip(reason=_NO_FAMILY)
def test_a_family_expands_to_show_every_version(page, shot):
    """Scenario: A family expands to show every version"""


@pytest.mark.scenario("S-21-04")
def test_a_family_of_one_renders_as_a_plain_row(page, shot):
    """Scenario: A family of one renders as a plain row

    The only shape any sweep has seen, and the only one this database can
    produce. It fails the day a revised run appears — which is exactly the
    signal that S-21-01..03 can be written for real.
    """
    with shot("family-of-one", 'When I cold-load "/runs"'):
        open_history(page)

    labels = RH.rows(page)
    assert labels, "no runs to look at"
    for label in labels:
        assert "latest version" not in label, (
            f"a family row appeared: {label!r}. Revised runs now exist — write "
            "S-21-01, S-21-02 and S-21-03 against them."
        )

    assert page.get_by_text(re.compile(r"^Show versions$")).count() == 0
    assert page.locator('[aria-label*="versions"]').count() == 0


@pytest.mark.scenario("S-21-05")
def test_the_family_counts_as_one_against_a_filter_chip(page, shot):
    """Scenario: The family counts as one against a filter chip

    `baseWorkflowType` strips the `_revision` suffix, so the chips count
    FAMILIES while the headline counts runs. With every family size 1 the two
    agree, and this asserts that agreement — the day they diverge, either a
    family appeared (good, write S-21-01) or the chip stopped collapsing
    revisions (bad).
    """
    with shot("chips-count-families", 'When I cold-load "/runs"'):
        open_history(page)

    rows = len(RH.rows(page))
    named = sum(RH.chip_count(page, label) for label in RH.TYPE_PARAMS)
    assert named == rows == RH.chip_count(page, "All"), (
        f"{rows} rows, {named} across the chips, {RH.chip_count(page, 'All')} on "
        "All — with every family a single run these must agree"
    )


@pytest.mark.scenario("S-21-06")
@pytest.mark.parametrize(("sort", "reader"), [("", "age"), ("duration", "duration"), ("tokens", "tokens")])
def test_families_bucket_by_date_and_reorder_by_sort(page, shot, sort, reader):
    """Scenario: Families bucket by date and reorder by sort

    `bucketAndSortFamilies` does both at once, so sorting must not flatten the
    date buckets. That is the half this can check while every family is one run.
    """
    query = f"?sort={sort}" if sort else ""

    with shot(f"buckets-{reader}", f'When I cold-load "/runs{query}"'):
        open_history(page)
        if sort:
            page.goto(f"/runs{query}")
            expect(page.locator(RH.ROW).first).to_be_visible()
            page.wait_for_timeout(settings.SETTLE_MS // 2)

    groups = RH.group_counts(page)
    assert groups, "sorting flattened the date buckets"
    assert sum(groups) == len(RH.rows(page))

    read = {"age": RH.age_minutes, "duration": RH.duration_seconds, "tokens": RH.tokens}[reader]
    for segment in RH.segments(page):
        values = [v for v in (read(t) for t in segment) if v is not None]
        expected = sorted(values) if reader == "age" else sorted(values, reverse=True)
        assert values == expected, f"a bucket is not ordered by {reader}: {values}"


# ── the version timeline ─────────────────────────────────────────────────────


@pytest.mark.scenario("S-21-07")
@pytest.mark.skip(reason=_NO_FAMILY)
def test_a_revised_run_shows_its_version_timeline(page, shot):
    """Scenario: A revised run shows its version timeline"""


@pytest.mark.scenario("S-21-08")
@pytest.mark.skip(reason=_NO_FAMILY)
def test_a_timeline_entry_names_what_it_revises(page, shot):
    """Scenario: A timeline entry names what it revises"""


@pytest.mark.scenario("S-21-09")
@pytest.mark.skip(reason=_NO_FAMILY)
def test_selecting_a_version_navigates_to_it(page, shot):
    """Scenario: Selecting a version navigates to it"""


@pytest.mark.scenario("S-21-10")
@pytest.mark.defect
def test_a_version_that_does_not_exist_is_refused(page, shot):
    """Scenario: A version that does not exist is refused

    Asserts TODAY'S behaviour — D-12, restated here because this is where the
    version UI is specified. A shared link to a removed version shows the wrong
    content with nothing to say so.
    """
    run_id = a_run(page)

    with shot("version-99", 'When I cold-load "/runs/{id}/versions/99"'):
        page.goto(f"/runs/{run_id}/versions/99")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    if page.get_by_text("Page not found.").count():
        pytest.skip("this run has no artifact to version, so the fallback never runs")

    assert page.url.endswith("/versions/99"), page.url
    body = page.evaluate("() => document.body.innerText")
    assert not any(
        phrase in body.lower()
        for phrase in ("does not exist", "not available", "no such version")
    ), f"the page now says the version is missing — D-12 is fixed: {body[:200]!r}"


@pytest.mark.scenario("S-21-11")
def test_a_single_version_run_shows_no_timeline(page, shot):
    """Scenario: A single-version run shows no timeline"""
    run_id = a_run(page)

    with shot("no-timeline", 'When I cold-load "/runs/{id}"'):
        page.goto(f"/runs/{run_id}")
        expect(page.locator(RD.LANE)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert page.get_by_text(VERSIONS_REGION).count() == 0, (
        "a version timeline rendered on a run with no revisions"
    )
    # The header still reports the version it IS.
    assert re.search(r"Version\s+v?1", page.evaluate("() => document.body.innerText")), (
        "the run reports no version at all"
    )


# ── divert links ─────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-21-12")
@pytest.mark.skip(reason=_NO_DIVERT)
def test_a_diverting_run_links_forward_to_the_run_it_triggered(page, shot):
    """Scenario: A diverting run links forward to the run it triggered"""


@pytest.mark.scenario("S-21-13")
@pytest.mark.skip(reason=_NO_DIVERT)
def test_the_triggered_run_links_back_to_its_origin(page, shot):
    """Scenario: The triggered run links back to its origin"""


@pytest.mark.scenario("S-21-14")
@pytest.mark.skip(reason=_NO_DIVERT)
def test_the_two_directions_are_distinguishable(page, shot):
    """Scenario: The two directions are distinguishable"""


@pytest.mark.scenario("S-21-15")
@pytest.mark.defect
@pytest.mark.skip(reason=_NO_DIVERT)
def test_a_diverted_runs_chat_lane_names_its_target(page, shot):
    """Scenario: A diverted run's chat lane names its target"""

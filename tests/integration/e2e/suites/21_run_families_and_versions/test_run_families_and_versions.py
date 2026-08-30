"""Implements ../../../screens/21-run-families-and-versions.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**This history holds both shapes.** It used to hold only families of one, and
S-21-04/S-21-11 were written as tripwires for the day that stopped being true.
They fired: the ISS-230 fixture family (root `77f74563`, one revision) is a real
family of two, so the collapse, the version badge and the version timeline are
live rendered logic and S-21-01..03 and S-21-07..09 are written against them.

Nothing here hardcodes that fixture. Every test finds its own subject on the
page — `_a_family` for the family shape, `a_run` for the single-version shape —
so a second family appearing, or that one being revised again, changes no test.
The divert links remain unrendered (S-21-12..14): no run in this history
diverted.

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

_NEEDS_FAMILY = (
    "no revised run on this page — every run is a family of one again, so the "
    "family UI never renders. Restore a revision family (the ISS-230 fixture is "
    "root 77f74563 plus one revision) or these scenarios cannot be exercised."
)
_NO_TIMELINE_SURFACE = (
    'the "Workflow versions" region these scenarios name lives in RunDetailPage, '
    "which no user path mounts: WorkflowHistory.handleSelectRun routes every tap "
    "to the shared run screen instead (BUG-002), whose version control is "
    "RunHeader's Version MENU, not a timeline region. Retiring the internal "
    "detail is the open INV-3 follow-up — until then these three describe a "
    "surface the app never renders. The menu's own behaviour IS covered, by "
    "21's ISS-230 / ISS-296 / ISS-607 tests."
)
_NO_DIVERT = (
    "no run in this history diverted — 22_handoff_and_gates creates the pair in "
    "the live tier"
)


def open_history(page, query: str = "") -> None:
    page.goto(f"/runs{query}")
    expect(page.locator(RH.ROW).first).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)


def _rows(page) -> list[tuple[int, str, int]]:
    """Every run-history row as (index, aria-label, version count).

    Read in ONE pass inside the page. A row's aria-label is a free-text brief
    excerpt — quoting it back into a selector breaks on the first apostrophe,
    and several briefs carry one. The index is what scopes a locator afterwards.

    A row with no `N versions` badge is a family of one, which is a count of 1.
    """
    return [
        (i, label, n)
        for i, label, n in page.locator(RH.ROW).evaluate_all(
            """els => els.map((e, i) => {
                const badge = e.querySelector('span[aria-label$=" versions"]');
                return [i, e.getAttribute("aria-label"),
                        badge ? parseInt(badge.getAttribute("aria-label"), 10) : 1];
            })"""
        )
    ]


def _a_family(page) -> tuple[int, str, int]:
    """The first row holding more than one version."""
    for row in _rows(page):
        if row[2] > 1:
            return row
    pytest.fail(_NEEDS_FAMILY)


def _wrapper(page, index: int):
    """The div holding a family's root row AND its expanded member rows."""
    return page.locator(RH.ROW).nth(index).locator("xpath=..")


def a_run(page) -> str:
    """A COMPLETED run that is a FAMILY OF ONE.

    A live one reports "v1 draft" and redirects to /stream, and a family row
    opens its newest member — which has a version timeline. Both answer a
    different question from the one S-21-10 and S-21-11 ask.
    """
    open_history(page)
    done = [
        (i, label)
        for i, label, n in _rows(page)
        if n == 1 and RH.status_of(label) == "completed"
    ]
    assert done, "no completed single-version run"
    page.locator(RH.ROW).nth(done[0][0]).click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


# ── families on run history ──────────────────────────────────────────────────


@pytest.mark.scenario("S-21-01")
def test_runs_sharing_a_root_collapse_into_one_family_row(page, shot):
    """Scenario: Runs sharing a root collapse into one family row

    Collapse is the gap between the two counts the page itself reports: the
    header counts RUNS, the list renders one row per FAMILY. A family of N
    leaves the list N-1 rows shorter, and its members appear nowhere in it —
    they exist only behind the expander (S-21-03).
    """
    with shot("family-collapses", 'When I cold-load "/runs"'):
        open_history(page)

    index, label, count = _a_family(page)
    rows = _rows(page)

    assert [l for _, l, _ in rows].count(label) == 1, (
        f"the family root appears more than once in the list: {label!r}"
    )
    assert len(rows) == RH.total(page) - sum(n - 1 for _, _, n in rows), (
        f"{len(rows)} rows for {RH.total(page)} runs does not account for the "
        f"families on the page: {[(l, n) for _, l, n in rows if n > 1]}"
    )
    assert count > 1
    # Members are not top-level rows: nothing in the list carries a bare
    # "Version N" name, which is what an expanded member row is called.
    assert page.locator(f'{RH.ROW}[aria-label^="Version "]').count() == 0


@pytest.mark.scenario("S-21-02")
def test_the_version_badges_accessible_name_is_not_its_text(page, shot):
    """Scenario: The version badge's accessible name is not its text

    A screen reader announces "3 versions"; the pill paints "v3". A test that
    matches on "v3" is matching presentation, so this pins BOTH and asserts
    they differ.
    """
    with shot("version-badge", 'When I cold-load "/runs"'):
        open_history(page)

    index, _, count = _a_family(page)
    badge = page.locator(RH.ROW).nth(index).locator('span[aria-label$=" versions"]')
    expect(badge).to_be_visible()

    name = badge.get_attribute("aria-label")
    assert name == f"{count} versions", f"badge accessible name is {name!r}"
    assert badge.inner_text().strip() == f"v{count}", (
        f"the badge paints {badge.inner_text()!r} and announces {name!r} — the "
        "two must not be the same string, or the a11y name adds nothing"
    )


@pytest.mark.scenario("S-21-03")
def test_a_family_expands_to_show_every_version(page, shot):
    """Scenario: A family expands to show every version"""
    open_history(page)
    index, label, count = _a_family(page)

    row = page.locator(RH.ROW).nth(index)
    expander = row.locator('[aria-label="Show versions"]')
    assert expander.count() == 1, f"a family offers no expander: {label!r}"
    assert _wrapper(page, index).locator('button[aria-label^="Version "]').count() == 0, (
        "the member rows are rendered before the family is expanded"
    )

    with shot("family-expanded", "When I expand a family's versions"):
        expander.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    members = _wrapper(page, index).locator('button[aria-label^="Version "]')
    expect(members).to_have_count(count)
    expect(row.locator('[aria-label="Collapse versions"]')).to_have_count(1)

    names = members.evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")
    assert [n.split(",")[0] for n in names] == [f"Version {i + 1}" for i in range(count)], (
        f"the expanded rows are not v1..v{count} in order: {names}"
    )


@pytest.mark.scenario("S-21-04")
def test_a_family_of_one_renders_as_a_plain_row(page, shot):
    """Scenario: A family of one renders as a plain row

    An unrevised run carries no version affordance at all — no count badge, no
    expander — and does not call itself the latest of anything. Asserted in
    both directions, so neither a badge without the label nor a label without
    the badge can slip through.
    """
    with shot("family-of-one", 'When I cold-load "/runs"'):
        open_history(page)

    rows = _rows(page)
    assert rows, "no runs to look at"
    plain = [(i, label) for i, label, n in rows if n == 1]
    assert plain, "every run on this page is a family — none left to check"

    for index, label in plain:
        assert "(latest version)" not in label, (
            f"a row with no version badge still calls itself a family: {label!r}"
        )
        row = page.locator(RH.ROW).nth(index)
        assert row.locator('[aria-label="Show versions"]').count() == 0, (
            f"a single-version run offers a version expander: {label!r}"
        )

    for index, label, n in rows:
        if n > 1:
            assert "(latest version)" in label, (
                f"a family row does not name itself the latest version: {label!r}"
            )


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
@pytest.mark.skip(reason=_NO_TIMELINE_SURFACE)
def test_a_revised_run_shows_its_version_timeline(page, shot):
    """Scenario: A revised run shows its version timeline"""


@pytest.mark.scenario("S-21-08")
@pytest.mark.skip(reason=_NO_TIMELINE_SURFACE)
def test_a_timeline_entry_names_what_it_revises(page, shot):
    """Scenario: A timeline entry names what it revises"""


@pytest.mark.scenario("S-21-09")
@pytest.mark.skip(reason=_NO_TIMELINE_SURFACE)
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

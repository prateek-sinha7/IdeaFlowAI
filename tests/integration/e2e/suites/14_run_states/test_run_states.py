"""Implements ../../../screens/14-run-states.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Every scenario here needs a run in a particular state, and which states exist
depends on the database rather than on anything the offline tier can arrange.
`a_run_with_status` finds one or skips with the reason — the alternative is a
module that passes because it never looked.

`diverted` and `generating` are not reachable offline at all: one needs a divert
pair, the other needs a run in flight.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as L
from framework.locators import run_history as RH

CHIPS = {
    "completed": "Done",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "diverted": "Diverted",
    "generating": "Running",
}


def a_run_with_status(page, status: str) -> str:
    """Open a run in `status` and return its id, or skip."""
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    match = next((label for label in RH.rows(page) if RH.status_of(label) == status), None)
    if not match:
        pytest.skip(f"no run in this history has status {status!r}")

    page.locator(f'{RH.ROW}[aria-label="{match}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(L.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


def tab_strip(page) -> dict[str, str]:
    return {
        row["testid"]: row["label"]
        for row in page.evaluate(
            """() => [...document.querySelectorAll('[data-testid^="tab-"]')]
                 .map(e => ({ testid: e.dataset.testid, label: e.innerText.trim() }))"""
        )
    }


@pytest.mark.scenario("S-14-01")
def test_a_failed_run_explains_itself_and_offers_a_way_forward(page, shot):
    """Scenario: A failed run explains itself and offers a way forward"""
    with shot("failed-run", "When I cold-load a failed run"):
        a_run_with_status(page, "failed")

    expect(page.locator(L.RUN_STATUS)).to_have_text(re.compile("failed", re.I))
    body = page.evaluate("() => document.body.innerText")
    assert "What went wrong" in body, "no failure panel"
    for control in ("Reopen & fix from the failed step", "Edit brief & run again"):
        assert control in body, f"the failed run offers no {control!r}"


@pytest.mark.scenario("S-14-02")
def test_a_failed_run_has_no_preview_tab(page, shot):
    """Scenario: A failed run has no Preview tab

    CORRECTED. The strip is not status-dependent — this failed run reached
    "Delivered — open in Preview →" before failing, and keeps its Preview tab.
    What the scenario is really guarding is the same either way: the tab strip's
    LENGTH is variable, so nothing may index it positionally.
    """
    with shot("failed-tabs", "When I cold-load a failed run"):
        a_run_with_status(page, "failed")

    strip = tab_strip(page)
    for testid in ("tab-thinking", "tab-files", "tab-workspace", "tab-audit"):
        assert testid in strip, f"a failed run is missing {testid}"
    # Recorded rather than asserted absent: whether Preview is offered follows
    # the deliverable, not the status.
    assert strip.get("tab-thinking") == "Steps", (
        f"the Steps tab is labelled {strip.get('tab-thinking')!r} — its testid is "
        "`tab-thinking` and always has been, but the LABEL is what D-08's copy "
        "should be pointing at"
    )


@pytest.mark.scenario("S-14-03")
def test_a_cancelled_run_offers_to_resume(page, shot):
    """Scenario: A cancelled run offers to resume"""
    with shot("cancelled-run", "When I cold-load a cancelled run"):
        a_run_with_status(page, "cancelled")

    expect(page.locator(L.RUN_STATUS)).to_have_text(re.compile("cancelled", re.I))
    body = page.evaluate("() => document.body.innerText")
    assert "Run Again" in body, "a cancelled run offers no way to resume"
    assert "where it left off" in body, (
        "the run does not say it will resume from where it stopped"
    )


@pytest.mark.scenario("S-14-04")
@pytest.mark.defect
def test_the_cancelled_empty_state_names_a_tab_that_does_not_exist(page, shot):
    """Scenario: The cancelled empty-state names a tab that does not exist

    Asserts TODAY'S behaviour — D-08. The copy points at a "Thinking" tab; the
    tab is labelled Steps and only its testid still says thinking.
    """
    with shot("cancelled-copy", "When I cold-load a cancelled run"):
        a_run_with_status(page, "cancelled")

    body = page.evaluate("() => document.body.innerText")
    strip = tab_strip(page)
    assert "Thinking" not in strip.values(), "a tab is now labelled Thinking"

    if "Thinking tab" not in body:
        pytest.skip("this cancelled run does not render the empty state D-08 describes")
    assert "Open the Thinking tab" in body, (
        "the copy changed — if it now says Steps, D-08 is fixed"
    )


@pytest.mark.scenario("S-14-05")
@pytest.mark.skip(reason="no run in this history is diverted; 22_handoff_and_gates makes one")
def test_a_diverted_run_points_at_its_continuation(page, shot):
    """Scenario: A diverted run points at its continuation"""


@pytest.mark.scenario("S-14-06")
@pytest.mark.live
@pytest.mark.skip(reason="needs a run in flight; live tier")
def test_a_live_run_streams_and_can_be_stopped(page, shot):
    """Scenario: A live run streams and can be stopped"""


@pytest.mark.scenario("S-14-07")
@pytest.mark.defect
@pytest.mark.live
@pytest.mark.skip(reason="needs a run in flight to reproduce the /stream override; live tier")
def test_a_live_run_cannot_deep_link_any_tab(page, shot):
    """Scenario: A live run cannot deep-link any tab"""


@pytest.mark.scenario("S-14-08")
def test_the_same_tab_urls_work_once_the_run_finishes(page, shot):
    """Scenario: The same tab URLs work once the run finishes

    The control for S-14-07. Both belong in the suite, or D-06 reads as "tab
    routing is broken" rather than "it is broken while a run is live".
    """
    run_id = a_run_with_status(page, "completed")

    with shot("completed-audit-url", 'When I cold-load "/runs/{id}/audit"'):
        page.goto(f"/runs/{run_id}/audit")
        expect(page.locator(L.HEADER)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert page.url.endswith(f"/runs/{run_id}/audit"), (
        f"a completed run's audit URL was overridden to {page.url}"
    )
    expect(page.locator(L.tab("tab-audit"))).to_have_attribute("aria-selected", "true")


@pytest.mark.scenario("S-14-09")
def test_a_failed_runs_audit_reports_its_governance_totals(page, shot):
    """Scenario: A failed run's audit reports its governance totals"""
    run_id = a_run_with_status(page, "failed")

    with shot("failed-audit", "When I open its Audit tab"):
        page.goto(f"/runs/{run_id}/audit")
        expect(page.locator(L.AUDIT_PILL)).to_be_visible(timeout=20000)
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    def stat(name: str) -> int:
        text = page.locator(f'[data-testid="audit-stat-{name}"]').inner_text()
        m = re.search(r"(\d[\d,]*)", text.replace("\n", " "))
        assert m, f"the {name} stat carries no number: {text!r}"
        return int(m.group(1).replace(",", ""))

    checks = stat("checks")
    parts = sum(stat(name) for name in ("passed", "warnings", "blocked", "denied"))
    assert parts == checks, (
        f"passed+warnings+blocked+denied = {parts} but Checks = {checks}"
    )


@pytest.mark.scenario("S-14-10")
@pytest.mark.parametrize("category", ["All", "Governance", "Security", "Activity"])
def test_audit_categories_filter_the_trail(page, shot, category):
    """Scenario: Audit categories filter the trail"""
    run_id = a_run_with_status(page, "completed")
    page.goto(f"/runs/{run_id}/audit")
    expect(page.locator(L.AUDIT_PILL)).to_be_visible(timeout=20000)
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    expected = L.filter_count(page, category)

    with shot(f"audit-{category.lower()}", f'When I select the category "{category}"'):
        page.click(L.AUDIT_FILTERS[category])
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    if expected == 0:
        assert "No records match the active filters." in body, (
            f"{category} has no records and shows no empty state: {body[-300:]!r}"
        )
    else:
        assert "No records match the active filters." not in body, (
            f"{category} reports {expected} records and shows the empty state"
        )


@pytest.mark.scenario("S-14-11")
def test_a_secret_scan_appears_as_a_security_record(page, shot):
    """Scenario: A secret scan appears as a security record"""
    run_id = a_run_with_status(page, "completed")
    page.goto(f"/runs/{run_id}/audit")
    expect(page.locator(L.AUDIT_PILL)).to_be_visible(timeout=20000)
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    if (L.filter_count(page, "Security") or 0) == 0:
        pytest.skip("this run recorded no security events")

    with shot("audit-security", 'When I select "Security"'):
        page.click(L.AUDIT_FILTERS["Security"])
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    assert "Secret scan" in body, f"no secret-scan record among the security ones: {body[-400:]!r}"


@pytest.mark.scenario("S-14-12")
@pytest.mark.parametrize("status", list(CHIPS))
def test_run_history_shows_the_right_status_chip(page, shot, status):
    """Scenario: Run history shows the right status chip"""
    with shot(f"chip-{status}", 'When I cold-load "/runs"'):
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    labels = RH.rows(page)
    match = next((label for label in labels if RH.status_of(label) == status), None)
    if not match:
        pytest.skip(f"no run in this history has status {status!r}")

    row = page.locator(f'{RH.ROW}[aria-label="{match}"]').first.inner_text()
    assert CHIPS[status] in row, (
        f"a {status!r} run's row reads {row.splitlines()[-1]!r}, not {CHIPS[status]!r}"
    )


@pytest.mark.scenario("S-14-13")
@pytest.mark.skip(
    reason="needs a run parked at a human gate; creating one costs a real LLM run "
    "and leaves a gate a human must answer. 22_handoff_and_gates makes it in the live tier"
)
def test_a_run_parked_at_a_human_gate_is_answerable(page, shot):
    """Scenario: A run parked at a human gate is answerable"""

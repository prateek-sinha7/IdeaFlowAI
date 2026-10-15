"""BUGS.md#qa-kb-067 — A history click on a completed run runs the whole
reopen twice (click-time handleSelectWorkflowRun on the page instance that
router.push destroys, then the deep-link effect's call on the remounted page).

Card:
- ISS-840 — expected: one GET /api/runs/{id} and one events?after=0 replay
  per history click; /family is allowed up to 2 (ISS-804 pair, still open).

Not part of a screens/*.feature.md — no `scenario` marker.
"""

from __future__ import annotations

import re

import pytest

from playwright.sync_api import expect

from framework import settings
from framework.locators import run_history as RH


def a_completed_run(page, requests: list[str]) -> None:
    """Cold /dashboard -> /runs, clear `requests`, click first completed row."""
    page.goto("/dashboard")
    page.wait_for_timeout(500)
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    labels = page.locator(RH.ROW).evaluate_all(
        "els => els.map(e => e.getAttribute('aria-label'))"
    )
    done = [i for i, l in enumerate(labels) if RH.status_of(l) == "completed"]
    assert done, "no completed run in history to open"
    page.wait_for_timeout(settings.SETTLE_MS)
    requests.clear()
    page.locator(RH.ROW).nth(done[0]).click()
    page.wait_for_url(lambda url: "/runs/" in url)


@pytest.mark.issue("ISS-840")
def test_history_click_reopens_completed_run_once(page):
    """ISS-840 — one history click must fetch the run and its events replay
    exactly once, not once per remount."""
    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    a_completed_run(page, requests)
    page.wait_for_timeout(4000)

    m = re.search(r"/runs/([^/?#]+)", page.url)
    assert m, f"not on a run URL: {page.url}"
    run_id = m.group(1)

    run_gets = [u for u in requests if re.search(rf"/api/runs/{run_id}(\?|$)", u)]
    replays = [u for u in requests if f"/api/runs/{run_id}/events" in u and "after=0" in u]
    family = [u for u in requests if f"/api/runs/{run_id}/family" in u]

    assert len(run_gets) == 1, f"GET /api/runs/{run_id} x{len(run_gets)}, expected 1"
    assert len(replays) == 1, f"events?after=0 x{len(replays)}, expected 1"
    assert len(family) <= 2, f"/family x{len(family)}, expected <= 2"

"""BUGS.md#qa-ps-038 — Opening a run detail page from history fires
~40-50 API requests — runs?limit=50 called 12+ times as durable replay
events trigger live-run refetch logic.

Card:
- ISS-785 — `handleWebSocketMessage` (`frontend/src/app/[...view]/page.tsx`)
  has 12 `getWorkflows(limit: 50)` bindings on SSE event types with no
  live-vs-replay signal. `handleSelectWorkflowRun`'s durable-replay loop
  feeds every historical event from a completed run through that same
  handler on every history-reopen, so each matching event still fires its
  `runs?limit=50` refetch — 8-14 calls per open instead of the ~1 expected
  at mount.

Not part of a screens/*.feature.md — no `scenario` marker.
"""

from __future__ import annotations

import pytest

from framework import settings
from framework.locators import run_history as RH


def a_completed_run(page, requests: list[str]) -> None:
    """Navigate cold to /runs and click the first completed run's row.

    Mirrors ISS-785's repro: fresh nav to /dashboard -> /runs -> click a
    completed run. `requests` is emptied once /runs has settled, just before
    the click, so it holds only what opening the run fetched — not the app
    shell's per-document run-list fetches from the two cold loads before it.
    """
    page.goto("/dashboard")
    page.wait_for_timeout(500)
    page.goto("/runs")
    from playwright.sync_api import expect

    expect(page.locator(RH.ROW).first).to_be_visible()
    rows_info = page.locator(RH.ROW).evaluate_all(
        """els => els.map((e, i) => e.getAttribute('aria-label'))"""
    )
    done = [
        (i, label)
        for i, label in enumerate(rows_info)
        if RH.status_of(label) == "completed"
    ]
    assert done, "no completed run in history to open"
    idx, _ = done[0]
    page.wait_for_timeout(settings.SETTLE_MS)
    requests.clear()
    page.locator(RH.ROW).nth(idx).click()
    page.wait_for_url(lambda url: "/runs/" in url)


@pytest.mark.issue("ISS-785")
def test_opening_completed_run_from_history_fetches_runs_list_once(page):
    """ISS-785 — opening a completed run's detail page from history must
    fetch the run list AT MOST ONCE, not 8-14x from durable replay events
    being fed through the live-run refetch handler. Decision 2026-09-23
    (option a, ESCALATIONS.md#qa-ps-038): the app shell's own per-document
    run-list fetch is intended, so only the click is counted."""
    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    a_completed_run(page, requests)
    page.wait_for_timeout(3000)

    runs_list_calls = [u for u in requests if "/api/runs?" in u and "limit=" in u]

    assert len(runs_list_calls) <= 1, (
        "opening a completed run from history should fetch the run list "
        f"at most once, saw {len(runs_list_calls)}: {runs_list_calls}"
    )

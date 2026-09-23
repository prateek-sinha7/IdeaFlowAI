"""ISS-741 — Back must move backward through history, not loop between the
run detail and Run History pages.

`DashboardLayout.tsx`'s `onBackToHistory` (the handler behind the run-detail
lane's Back button, `[data-testid="lane-back"]`) calls
`router.push(routes.runHistory())` instead of `router.back()`. Opening a run
from `/runs` already pushes `/runs/{id}`, so the stack after that push reads
`[..., /runs, /runs/{id}, /runs]` — one extra `/runs` entry — instead of
popping back to the `/runs` entry that already exists. The Run History page's
OWN Back button is correctly implemented with `router.back()`
(`handleBackNav`, `DashboardLayout.tsx:1806-1822`), so it legitimately pops to
that just-repushed `/runs/{id}`, producing QA-SG-003's loop: Back on the run
detail page, then Back on Run History, lands right back on the run detail
page instead of continuing to whatever came before it (e.g. `/dashboard`).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import run_detail as L
from framework.locators import run_history as RH


def _click_history_page_back_button(page) -> None:
    """The Run History page's own Back arrow-left icon button carries no
    testid or aria-label (D-14) — it is the first `<button>` next to the
    "Run History" `<h1>`."""
    page.locator("h1", has_text="Run History").locator(
        "xpath=ancestor::div[contains(@class,'items-center')][1]//button"
    ).first.click()


@pytest.mark.issue("ISS-741")
def test_back_from_run_detail_then_back_from_history_does_not_loop(page, shot):
    """Open a run from Run History, click the run detail page's Back button
    (lands on Run History, as expected), then click Run History's own Back
    button. That second click must continue backward — NOT land on the same
    run detail page again."""
    page.goto("/dashboard")
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    row = page.locator(RH.ROW).first
    run_id = row.get_attribute("aria-label")
    row.click()
    page.wait_for_url(lambda url: "/runs/" in url)

    with shot("back-from-run-detail", 'When I click Back on the run detail page'):
        page.locator(L.BACK).click()
        page.wait_for_url(lambda url: url.rstrip("/").endswith("/runs"))

    with shot("back-from-history", 'When I click Back again on Run History'):
        _click_history_page_back_button(page)

    assert "/runs/" not in page.url, (
        f"Back looped back into the run detail page ({page.url!r}) instead of "
        f"continuing backward past it (run: {run_id!r})"
    )

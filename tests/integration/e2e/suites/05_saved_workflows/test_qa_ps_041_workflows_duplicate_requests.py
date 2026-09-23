"""BUGS.md#qa-ps-041 — My Workflows page calls GET /api/user-workflows four
times and loads run history (37 KB) not displayed on this page.

Cards:
- ISS-788 — root. `/workflows` fires `GET /api/user-workflows` 2x-4x (no
  shared cache for the mount-effect fetch) and an unused `GET /api/runs`
  (`RunConnectionProvider`'s app-wide `refreshLiveRuns`), on a page that shows
  neither run history nor a second copy of the saved-workflow list.
- ISS-813 — INFERRED sibling. `/workflows/{id}` and `/workflows/{id}/edit`
  each independently call `userWorkflowsApi.get(workflowId)` on an unguarded
  mount effect, the same no-dedupe shape ISS-788 proved for the list page.
- ISS-815 — INFERRED sibling. `SavedWorkflowsPage`'s "Duplicate" kebab item
  has no in-flight guard: the trigger button stays enabled through the
  `await createUserWorkflow(...)`, so reopening the menu and clicking again
  mid-request fires a second `POST /api/user-workflows`.
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import saved_workflows as L

from .test_saved_workflows import open_list, workflow_id


def _collect_requests(page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))
    return seen


def _count(urls: list[str], path: str) -> int:
    return sum(1 for u in urls if path in u)


@pytest.mark.issue("ISS-788")
def test_workflows_list_fetches_user_workflows_once_and_no_run_history(page):
    """ISS-788 — `/workflows` shows only saved-workflow cards, so it must
    fetch `/api/user-workflows` exactly once and `/api/runs` AT MOST ONCE.
    Decision 2026-09-23 (option a, ESCALATIONS.md#qa-ps-041): that one run-list
    call is the app shell's (AppHeader's "N Running" badge, the SSE re-attach),
    intended on every route — only a duplicate is a defect."""
    requests = _collect_requests(page)

    page.goto("/workflows")
    page.wait_for_timeout(settings.SETTLE_MS)

    uw_count = _count(requests, "/api/user-workflows")
    runs_calls = [u for u in requests if "/api/runs" in u]

    assert uw_count == 1 and len(runs_calls) <= 1, (
        f"/workflows fetched user-workflows {uw_count}x and runs={runs_calls} "
        f"— requests: {requests}"
    )


@pytest.mark.issue("ISS-813")
@pytest.mark.xfail(reason="ISS-813 unfixed", strict=True)
def test_workflow_detail_view_fetches_the_row_once(page):
    """ISS-813 — a cold load of `/workflows/{id}` must fetch
    `GET /api/user-workflows/{id}` exactly once."""
    wid = workflow_id(page, L.OVERRIDE_TITLE)

    requests = _collect_requests(page)
    page.goto(f"/workflows/{wid}")
    expect(page.get_by_role("heading", name=L.OVERRIDE_TITLE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, f"/api/user-workflows/{wid}")
    assert count == 1, (
        f"/workflows/{wid} fetched its own row {count}x — requests: {requests}"
    )


@pytest.mark.issue("ISS-813")
@pytest.mark.xfail(reason="ISS-813 unfixed", strict=True)
def test_workflow_edit_view_fetches_the_row_once(page):
    """ISS-813 — a cold load of `/workflows/{id}/edit` must fetch
    `GET /api/user-workflows/{id}` exactly once, the same no-dedupe shape as
    the read-only detail view but on the distinct edit route."""
    wid = workflow_id(page, L.OVERRIDE_TITLE)

    requests = _collect_requests(page)
    page.goto(f"/workflows/{wid}/edit")
    expect(page.locator(L.SAVE_WORKFLOW)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, f"/api/user-workflows/{wid}")
    assert count == 1, (
        f"/workflows/{wid}/edit fetched its own row {count}x — requests: {requests}"
    )


@pytest.mark.issue("ISS-815")
@pytest.mark.destructive
@pytest.mark.xfail(reason="ISS-815 unfixed", strict=True)
def test_reopening_duplicate_menu_mid_request_does_not_double_post(page):
    """ISS-815 — the kebab "Duplicate" trigger stays enabled through the
    in-flight `createUserWorkflow` call. Throttling that POST and reopening
    the menu to click Duplicate again while it is still in flight must NOT
    fire a second `POST /api/user-workflows` for one duplicate intent."""
    open_list(page)
    before = page.locator(L.CARD).count()

    posts: list[str] = []

    def _capture(route):
        if route.request.method == "POST":
            posts.append(route.request.url)
            time.sleep(2)
        route.continue_()

    # Excludes "(copy)" so this always resolves to the ORIGINAL row, even
    # after the first Duplicate prepends a new "... (copy)" card that also
    # contains OVERRIDE_TITLE as a substring — `.filter(has_text=...).first`
    # would otherwise start matching the copy instead once it exists.
    original = page.locator(L.CARD).filter(has_text=L.OVERRIDE_TITLE).filter(has_not_text="(copy)").first

    page.route("**/api/user-workflows", _capture)
    try:
        original.locator(L.ACTIONS).click()
        page.get_by_role("menuitem", name="Duplicate").click()

        # The first POST is now throttled in flight. Reopen the SAME
        # (original, non-copy) card's menu and click Duplicate again before
        # it resolves.
        page.wait_for_timeout(300)
        original.locator(L.ACTIONS).click()
        page.get_by_role("menuitem", name="Duplicate").click()

        page.wait_for_timeout(3000)
    finally:
        page.unroute("**/api/user-workflows", _capture)

    # Clean up whatever landed BEFORE asserting, so a failed (expected-red)
    # assertion still leaves the seeded count restored.
    page.reload()
    expect(page.locator(L.CARD).first).to_be_visible()
    copies = page.locator(L.CARD).filter(has_text="(copy)")
    while copies.count() > 0:
        copies.first.locator(L.ACTIONS).click()
        page.get_by_role("menuitem", name="Delete").click()
        page.get_by_role("button", name="Delete", exact=True).last.click()
        page.wait_for_timeout(500)
    assert page.locator(L.CARD).count() == before, (
        "cleanup did not restore the seeded workflow count"
    )

    assert len(posts) == 1, (
        f"reopening the Duplicate menu mid-request fired {len(posts)} "
        f"POST /api/user-workflows calls, expected 1: {posts}"
    )

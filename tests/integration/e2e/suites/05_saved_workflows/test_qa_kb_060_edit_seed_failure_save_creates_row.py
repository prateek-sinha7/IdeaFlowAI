"""BUGS.md#qa-kb-060 — a transient GET failure on /workflows/{id}/edit leaves
Save workflow creating a new row instead of updating.

Cards:
- ISS-923 — root. `page.tsx`'s /edit effect handles only 401/403/404; any other
  failure leaves a blank create-mode composer whose Save POSTs a new row.
- ISS-1033 — sibling. While the GET is still in flight the composer is editable
  and savable, and Save takes the create path.

The POST is intercepted and answered 500, so the test never creates a row.
"""

from __future__ import annotations

import pytest

from framework.locators import composer as L
from framework.locators import saved_workflows as SL

from .test_saved_workflows import workflow_id


def _fill_and_save(page, posts: list[str]) -> None:
    page.locator(L.WORKFLOW_NAME).fill("e2e-kb-060-should-not-exist")
    page.locator(L.ADD_AGENT).first.click()
    page.locator(L.ADD_TO_PLAN).first.wait_for(timeout=15000)
    page.locator(L.ADD_TO_PLAN).first.click()
    page.keyboard.press("Escape")
    save = page.locator(L.SAVE_WORKFLOW)
    if save.count() and save.is_enabled():
        save.click()
        page.wait_for_timeout(1500)


def _block_post(page, posts: list[str]) -> None:
    def handler(route):
        if route.request.method == "POST":
            posts.append(route.request.url)
            route.fulfill(status=500, body="{}")
        else:
            route.continue_()

    page.route("**/api/user-workflows", handler)


@pytest.mark.issue("ISS-923")
def test_failed_edit_seed_never_lets_save_create_a_new_row(page):
    """ISS-923 — with the row GET failing (network error), Save workflow must
    not POST a new workflow."""
    wid = workflow_id(page, SL.OVERRIDE_TITLE)
    posts: list[str] = []
    _block_post(page, posts)
    page.route(f"**/api/user-workflows/{wid}", lambda r: r.abort("failed")
               if r.request.method == "GET" else r.continue_())

    page.goto(f"/workflows/{wid}/edit")
    page.wait_for_timeout(2000)
    _fill_and_save(page, posts)

    assert posts == [], f"Save on a failed /edit seed POSTed a new row: {posts}"


@pytest.mark.issue("ISS-1033")
def test_save_during_pending_edit_seed_never_creates_a_new_row(page):
    """ISS-1033 — while the row GET is still in flight, Save workflow must not
    POST a new workflow."""
    wid = workflow_id(page, SL.OVERRIDE_TITLE)
    posts: list[str] = []
    _block_post(page, posts)
    held: list = []
    page.route(f"**/api/user-workflows/{wid}", lambda r: held.append(r)
               if r.request.method == "GET" else r.continue_())

    page.goto(f"/workflows/{wid}/edit", wait_until="commit")
    page.locator(L.WORKFLOW_NAME).wait_for(timeout=15000)
    _fill_and_save(page, posts)

    assert posts == [], f"Save while /edit seed pending POSTed a new row: {posts}"

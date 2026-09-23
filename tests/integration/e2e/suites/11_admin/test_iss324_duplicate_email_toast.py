"""ISS-324 — the Create-User dialog on /admin silently swallows a
duplicate-email 409, giving the admin zero feedback that submission failed.

`handleCreateUser` (`frontend/src/app/admin/page.tsx`) catches the 409
`ApiError` and calls `showToast("error", err.message)` with the correct
server detail, but the message is erased before an admin realistically
reads it. See `bug-hunter/ledger.md` §
`BUG-20260828-103434-admin` and `.knowledge/cards/20260828-1815-ISS-324.md`.

Root cause per the card: `showToast` schedules `setTimeout(() =>
setToast(null), 3500)` with no `useRef`/`clearTimeout` to cancel a prior
still-pending timer, so a second `showToast` call within ~3.5s of an earlier
one (exactly the create-once-then-duplicate repro) has its toast erased.

Cleanup mirrors `_delete_by_email` in test_create_user_email_validation.py.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from playwright.sync_api import expect

from framework import accounts, api
from framework.locators import admin as L


def _delete_by_email(admin_page, address: str) -> None:
    listing = api.full(admin_page, "GET", "/api/admin/users")
    if listing["status"] != 200:
        return
    rows = json.loads(listing["body"])
    rows = rows["users"] if isinstance(rows, dict) else rows
    for row in rows:
        if row.get("email") == address:
            api.full(admin_page, "DELETE", f"/api/admin/users/{row['id']}")


@pytest.mark.issue("ISS-324")
@pytest.mark.destructive
def test_duplicate_email_create_shows_an_error_toast(page, shot):
    """Resubmitting an already-used email must surface the server's 409
    message to the admin, not fail silently."""
    dup_email = f"zz-iss324-{uuid.uuid4().hex[:8]}@flowinqa.com"

    page.goto("/admin")
    expect(page.get_by_text(L.HEADING)).to_be_visible()

    try:
        # First create succeeds — its own showToast schedules an unguarded
        # setTimeout(() => setToast(null), 3500) with no clearTimeout, which
        # is the stale timer that later clobbers the second toast. The 3.5s
        # window starts when showToast("success", ...) actually runs, i.e.
        # once the create response resolves — not when the dialog opens.
        page.click(L.ADD_USER)
        expect(page.get_by_text("Create New User")).to_be_visible()
        page.fill('input[type="email"]', dup_email)
        page.fill('input[type="password"]', accounts.PASSWORD)
        with page.expect_response(
            lambda r: r.url.endswith("/api/admin/users") and r.request.method == "POST"
        ):
            page.get_by_role("button", name="Create User").click()
        t0 = time.time()
        expect(page.get_by_text("Create New User")).to_have_count(0)

        # Second create with the same email, fired well inside the first
        # toast's 3.5s window — backend rejects with 409.
        page.click(L.ADD_USER)
        expect(page.get_by_text("Create New User")).to_be_visible()
        page.fill('input[type="email"]', dup_email)
        page.fill('input[type="password"]', accounts.PASSWORD)

        with page.expect_response(
            lambda r: r.url.endswith("/api/admin/users") and r.request.method == "POST"
        ) as resp_info:
            page.get_by_role("button", name="Create User").click()
        assert resp_info.value.status == 409, (
            f"expected the duplicate create to 409, got {resp_info.value.status}"
        )

        toast = page.locator(".fixed.bottom-6.right-6")
        with shot("duplicate-email-toast", "Then an error toast reports the failure"):
            expect(toast).to_be_visible(timeout=3000)
        expect(page.get_by_text("already exists")).to_be_visible()

        # The error toast must live out its OWN 3.5s window. The bug is the
        # first (success) toast's uncancelled timer firing setToast(null) at
        # t0+3.5s and erasing the second toast early — so wait until just
        # past that deadline and confirm the error toast (which appeared
        # later than t0) is still up, not prematurely wiped by the earlier
        # call's stale timer.
        remaining = (t0 + 4.2) - time.time()
        if remaining > 0:
            page.wait_for_timeout(remaining * 1000)
        with shot("toast-survives-stale-timer", "Then the toast is not erased by the first call's timer"):
            expect(page.get_by_text("already exists")).to_be_visible()
    finally:
        _delete_by_email(page, dup_email)

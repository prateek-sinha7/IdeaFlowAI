"""ISS-295 — the Create-User dialog on /admin must not accept/persist a
malformed email (no `@`, no domain).

Today `handle CreateUser` and the "Create User" button's `disabled` prop gate
on presence only (`!newEmail || !newPassword`), never format, and the backend
schema (`CreateUserRequest.email: str`) has no format validator either — so a
value like `not-an-email` is created and persisted verbatim
(`bug-hunter/ledger.md` § BUG-20260828-033400-admin).

Cleanup is best-effort via the API, mirroring `_delete_by_email` in
test_admin.py — if the bug is unfixed the malformed user IS created and must
be removed so it doesn't linger as an orphaned row for other suites.
"""

from __future__ import annotations

import json
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


@pytest.mark.issue("ISS-295")
@pytest.mark.destructive
def test_create_user_dialog_rejects_email_with_no_at_or_domain(page, shot):
    """A malformed email (no @, no domain) must not create a user row."""
    malformed = f"not-an-email-{uuid.uuid4().hex[:8]}"

    page.goto("/admin")
    expect(page.get_by_text(L.HEADING)).to_be_visible()

    try:
        with shot("add-user-dialog", 'When I click "Add user"'):
            page.click(L.ADD_USER)
            expect(page.get_by_text("Create New User")).to_be_visible()

        page.fill('input[type="email"]', malformed)
        page.fill('input[type="password"]', accounts.PASSWORD)

        create_button = page.get_by_role("button", name="Create User")
        with shot("malformed-email-blocked", "Then Create User stays disabled"):
            expect(create_button).to_be_disabled()
    finally:
        _delete_by_email(page, malformed)

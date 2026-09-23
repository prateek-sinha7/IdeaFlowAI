"""BUG-20260828-032424-settings-security — ISS-404.

The Security tab's `!status.supported` branch (`SecuritySection.tsx:233-243`)
tells a break-glass/local account "This account's credentials are managed
outside the application, so two-factor authentication is configured
separately." That claim is false for this account: `password_hash`
(`backend/app/models/user.py:28-33`) is a column on the app's OWN `User` row,
verified and rewritten in place by this app's own
`POST /api/auth/change-password` (`auth.py:1254-1269`) — reachable from this
very settings shell's Profile tab.

`qa-admin` is confirmed break-glass/local for this pool: `GET /api/auth/mfa`
returns `supported: false` (verified live via curl, 2026-08-28), contradicting
`test_settings.py`'s header comment that "every seeded QA account is
Cognito-managed" — S-09-13's `EXTERNALLY_MANAGED` assertion currently encodes
this bug's wrong copy as correct; this test asserts what the copy should say
instead and is intentionally in a separate file rather than edited into that
scenario's assertion.

See `bug-hunter/ledger.md`'s `BUG-20260828-032424-settings-security` entry and
`.knowledge/cards/20260828-2120-ISS-404.md`.

Not part of screens/09-settings.feature.md — no `scenario` marker.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from framework import api
from framework.locators import settings_page as L


@pytest.mark.issue("ISS-404")
def test_security_unavailable_copy_does_not_claim_external_management(page, shot):
    """ISS-404 — for a break-glass/local account, the MFA-unavailable message
    must not claim credentials are "managed outside the application": this
    app's own database stores and rewrites that account's password.
    """
    with shot("iss404-security-copy", 'When I cold-load "/settings/security"'):
        page.goto("/settings/security")
        expect(page.get_by_text(L.HEADING).first).to_be_visible()

    res = api.request(page, "GET", "/api/auth/mfa")
    assert res["status"] == 200, f"/api/auth/mfa returned {res['status']}: {res['body']}"
    status = json.loads(res["body"])
    assert status.get("supported") is False, (
        "qa-admin is expected to be break-glass/local (supported=false); "
        f"got {status} — this test needs that account shape"
    )

    expect(page.get_by_text(L.NOT_AVAILABLE)).to_be_visible()
    # The false claim must be gone...
    expect(page.get_by_text(L.EXTERNALLY_MANAGED)).to_have_count(0)
    # ...replaced by wording that does not assert external credential
    # management for an account whose password this application itself
    # verifies and rewrites (auth.py's "local" change-password branch).
    assert "outside the application" not in page.locator("body").inner_text()

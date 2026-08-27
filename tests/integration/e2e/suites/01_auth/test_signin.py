"""Implements ../../../screens/01-auth.feature.md — the sign-in scenarios.

Each test carries the `scenario` marker naming the Gherkin scenario it
implements. `../../../capture/_scenarios.py` checks both directions of that link.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import auth as L
from framework import accounts


@pytest.mark.anonymous
@pytest.mark.scenario("S-01-02")
def test_signing_in_with_valid_credentials_lands_on_the_dashboard(page, shot):
    """Scenario: Signing in with valid credentials lands on the dashboard."""
    with shot("sign-in-form", 'When I cold-load "/login"'):
        page.goto("/login")
        expect(page.get_by_role("heading", name=L.WELCOME_HEADING)).to_be_visible()

    with shot("credentials-entered", "And I fill the email and password fields"):
        page.fill(L.EMAIL, accounts.ADMIN)
        page.fill(L.PASSWORD, accounts.PASSWORD)

    with shot("dashboard", 'Then the URL becomes "/dashboard"'):
        page.click(L.SIGN_IN)
        # expect() polls until it matches, so this is the wait AND the assertion.
        # No sleep: faster when the app is quick, still correct when it is slow.
        expect(page).to_have_url(re.compile(r"/dashboard"))
        expect(page.get_by_text(L.DASHBOARD_HEADING)).to_be_visible()

    # Asserted as a BOOLEAN. Returning the token would write a live credential
    # into this run's steps.json, which is an artifact anyone may read.
    assert page.evaluate(f"!!localStorage.getItem('{accounts.AUTH_TOKEN_KEY}')"), (
        "signed in but no auth token was written to localStorage"
    )

    # An admin lands on /dashboard like everyone else — the admin surface is
    # reached from the account menu, not from login.
    assert "/admin" not in page.url

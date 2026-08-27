"""Proves the shared-session fixture: these tests never touch the login form."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import auth as L


@pytest.mark.scenario("S-01-11")
def test_a_signed_in_visitor_reaching_login_is_sent_on(page, shot):
    """Scenario: A signed-in visitor reaching /login is sent onward."""
    with shot("dashboard", "Then I land on the dashboard already signed in"):
        page.goto("/dashboard")
        expect(page.get_by_text(L.DASHBOARD_HEADING)).to_be_visible()

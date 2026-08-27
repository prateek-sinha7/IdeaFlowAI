"""Implements ../../../screens/12-shell-nav.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-12-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_header_is_present_on_every_authenticated_screen(page, shot):
    """Scenario: The header is present on every authenticated screen"""


@pytest.mark.scenario("S-12-02")
@pytest.mark.skip(reason="not yet implemented")
def test_each_nav_item_routes_to_its_screen(page, shot):
    """Scenario: Each nav item routes to its screen"""


@pytest.mark.scenario("S-12-03")
@pytest.mark.skip(reason="not yet implemented")
def test_nav_items_are_buttons_not_links(page, shot):
    """Scenario: Nav items are buttons, not links"""


@pytest.mark.scenario("S-12-04")
@pytest.mark.skip(reason="not yet implemented")
def test_the_active_screen_is_indicated_in_the_nav(page, shot):
    """Scenario: The active screen is indicated in the nav"""


@pytest.mark.scenario("S-12-05")
@pytest.mark.skip(reason="not yet implemented")
def test_the_shell_is_absent_where_it_should_be(page, shot):
    """Scenario: The shell is absent where it should be"""


@pytest.mark.scenario("S-12-06")
@pytest.mark.skip(reason="not yet implemented")
def test_the_account_menu_lists_its_items(page, shot):
    """Scenario: The account menu lists its items"""


@pytest.mark.scenario("S-12-07")
@pytest.mark.skip(reason="not yet implemented")
def test_an_admin_additionally_sees_the_admin_entry(page, shot):
    """Scenario: An admin additionally sees the admin entry"""


@pytest.mark.scenario("S-12-08")
@pytest.mark.skip(reason="not yet implemented")
def test_a_non_admin_does_not(page, shot):
    """Scenario: A non-admin does not"""


@pytest.mark.scenario("S-12-09")
@pytest.mark.skip(reason="not yet implemented")
def test_each_menu_item_routes_correctly(page, shot):
    """Scenario: Each menu item routes correctly"""


@pytest.mark.scenario("S-12-10")
@pytest.mark.skip(reason="not yet implemented")
def test_escape_closes_the_account_menu(page, shot):
    """Scenario: Escape closes the account menu"""


@pytest.mark.scenario("S-12-11")
@pytest.mark.skip(reason="not yet implemented")
def test_the_notifications_panel_opens_with_an_empty_state(page, shot):
    """Scenario: The notifications panel opens with an empty state"""


@pytest.mark.scenario("S-12-12")
@pytest.mark.skip(reason="not yet implemented")
def test_a_completed_run_produces_a_notification(page, shot):
    """Scenario: A completed run produces a notification"""


@pytest.mark.scenario("S-12-13")
@pytest.mark.skip(reason="not yet implemented")
def test_a_live_run_surfaces_in_the_header_with_its_progress(page, shot):
    """Scenario: A live run surfaces in the header with its progress"""


@pytest.mark.scenario("S-12-14")
@pytest.mark.skip(reason="not yet implemented")
def test_the_badge_opens_the_live_run(page, shot):
    """Scenario: The badge opens the live run"""


@pytest.mark.scenario("S-12-15")
@pytest.mark.skip(reason="not yet implemented")
def test_the_badge_is_absent_when_nothing_is_running(page, shot):
    """Scenario: The badge is absent when nothing is running"""


@pytest.mark.scenario("S-12-16")
@pytest.mark.skip(reason="not yet implemented")
def test_dark_mode_toggles_and_persists(page, shot):
    """Scenario: Dark mode toggles and persists"""


@pytest.mark.scenario("S-12-17")
@pytest.mark.skip(reason="not yet implemented")
def test_browser_back_and_forward_work_across_top_level_screens(page, shot):
    """Scenario: Browser back and forward work across top-level screens"""


@pytest.mark.scenario("S-12-18")
@pytest.mark.skip(reason="not yet implemented")
def test_every_top_level_screen_survives_a_hard_refresh(page, shot):
    """Scenario: Every top-level screen survives a hard refresh"""


@pytest.mark.scenario("S-12-19")
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_session_sends_me_to_sign_in_with_an_explanation(page, shot):
    """Scenario: An expired session sends me to sign-in with an explanation"""

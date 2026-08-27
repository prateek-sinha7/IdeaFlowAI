"""Implements ../../../screens/11-admin.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-11-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_admin_dashboard_renders_its_own_shell(page, shot):
    """Scenario: The admin dashboard renders its own shell"""


@pytest.mark.scenario("S-11-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_stat_tiles_agree_with_the_table(page, shot):
    """Scenario: The stat tiles agree with the table"""


@pytest.mark.scenario("S-11-03")
@pytest.mark.skip(reason="not yet implemented")
def test_every_user_row_carries_its_full_record(page, shot):
    """Scenario: Every user row carries its full record"""


@pytest.mark.scenario("S-11-04")
@pytest.mark.skip(reason="not yet implemented")
def test_an_admin_cannot_delete_their_own_account(page, shot):
    """Scenario: An admin cannot delete their own account"""


@pytest.mark.scenario("S-11-05")
@pytest.mark.skip(reason="not yet implemented")
def test_an_admin_cannot_change_their_own_tier(page, shot):
    """Scenario: An admin cannot change their own tier"""


@pytest.mark.scenario("S-11-06")
@pytest.mark.skip(reason="not yet implemented")
def test_an_admin_cannot_demote_themselves(page, shot):
    """Scenario: An admin cannot demote themselves"""


@pytest.mark.scenario("S-11-07")
@pytest.mark.skip(reason="not yet implemented")
def test_a_non_admin_cannot_reach_the_admin_dashboard(page, shot):
    """Scenario: A non-admin cannot reach the admin dashboard"""


@pytest.mark.scenario("S-11-08")
@pytest.mark.skip(reason="not yet implemented")
def test_an_anonymous_visitor_cannot_reach_the_admin_dashboard(page, shot):
    """Scenario: An anonymous visitor cannot reach the admin dashboard"""


@pytest.mark.scenario("S-11-09")
@pytest.mark.skip(reason="not yet implemented")
def test_the_admin_api_refuses_a_non_admin_directly(page, shot):
    """Scenario: The admin API refuses a non-admin directly"""


@pytest.mark.scenario("S-11-10")
@pytest.mark.skip(reason="not yet implemented")
def test_search_filters_the_users_table(page, shot):
    """Scenario: Search filters the users table"""


@pytest.mark.scenario("S-11-11")
@pytest.mark.skip(reason="not yet implemented")
def test_the_account_menu_is_the_way_in(page, shot):
    """Scenario: The account menu is the way in"""


@pytest.mark.scenario("S-11-12")
@pytest.mark.skip(reason="not yet implemented")
def test_a_non_admin_is_not_offered_the_entry_point(page, shot):
    """Scenario: A non-admin is not offered the entry point"""


@pytest.mark.scenario("S-11-13")
@pytest.mark.skip(reason="not yet implemented")
def test_back_to_app_returns_to_the_main_shell(page, shot):
    """Scenario: Back to app returns to the main shell"""


@pytest.mark.scenario("S-11-14")
@pytest.mark.skip(reason="not yet implemented")
def test_logout_from_the_admin_shell_clears_the_session(page, shot):
    """Scenario: Logout from the admin shell clears the session"""


@pytest.mark.scenario("S-11-15")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_adding_a_user_creates_an_account_at_the_chosen_tier(page, shot):
    """Scenario: Adding a user creates an account at the chosen tier"""


@pytest.mark.scenario("S-11-16")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_deleting_a_user_removes_them(page, shot):
    """Scenario: Deleting a user removes them"""


@pytest.mark.scenario("S-11-17")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_an_admin_resets_another_user_s_password_to_a_temporary_one(page, shot):
    """Scenario: An admin resets another user's password to a temporary one"""


@pytest.mark.scenario("S-11-18")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_a_permanent_reset_skips_the_challenge_but_is_knowable(page, shot):
    """Scenario: A permanent reset skips the challenge but is knowable"""


@pytest.mark.scenario("S-11-19")
@pytest.mark.skip(reason="not yet implemented")
def test_admin_reset_is_the_only_recovery_path_under_email_mfa(page, shot):
    """Scenario: Admin reset is the only recovery path under email MFA"""


@pytest.mark.scenario("S-11-20")
@pytest.mark.skip(reason="not yet implemented")
def test_changing_another_user_s_tier_takes_effect(page, shot):
    """Scenario: Changing another user's tier takes effect"""

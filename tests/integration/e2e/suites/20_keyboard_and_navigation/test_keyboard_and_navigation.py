"""Implements ../../../screens/20-keyboard-and-navigation.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-20-01")
@pytest.mark.skip(reason="not yet implemented")
def test_escape_closes_an_overlay(page, shot):
    """Scenario: Escape closes an overlay"""


@pytest.mark.scenario("S-20-02")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_escape_closes_the_add_agent_modal(page, shot):
    """Scenario: Escape closes the add-agent modal"""


@pytest.mark.scenario("S-20-03")
@pytest.mark.skip(reason="not yet implemented")
def test_holding_space_pans_the_canvas(page, shot):
    """Scenario: Holding Space pans the canvas"""


@pytest.mark.scenario("S-20-04")
@pytest.mark.skip(reason="not yet implemented")
def test_space_still_types_a_space_in_a_text_field(page, shot):
    """Scenario: Space still types a space in a text field"""


@pytest.mark.scenario("S-20-05")
@pytest.mark.skip(reason="not yet implemented")
def test_space_to_pan_releases_on_keyup(page, shot):
    """Scenario: Space-to-pan releases on keyup"""


@pytest.mark.scenario("S-20-06")
@pytest.mark.skip(reason="not yet implemented")
def test_modifier_shortcuts_behave_as_advertised(page, shot):
    """Scenario: Modifier shortcuts behave as advertised"""


@pytest.mark.scenario("S-20-07")
@pytest.mark.skip(reason="not yet implemented")
def test_submitting_a_chat_message_by_keyboard(page, shot):
    """Scenario: Submitting a chat message by keyboard"""


@pytest.mark.scenario("S-20-08")
@pytest.mark.skip(reason="not yet implemented")
def test_every_route_survives_a_cold_load(page, shot):
    """Scenario: Every route survives a cold load"""


@pytest.mark.scenario("S-20-09")
@pytest.mark.skip(reason="not yet implemented")
def test_an_in_app_affordance_lands_where_its_url_claims(page, shot):
    """Scenario: An in-app affordance lands where its URL claims"""


@pytest.mark.scenario("S-20-10")
@pytest.mark.skip(reason="not yet implemented")
def test_back_returns_to_where_i_came_from(page, shot):
    """Scenario: Back returns to where I came from"""


@pytest.mark.scenario("S-20-11")
@pytest.mark.skip(reason="not yet implemented")
def test_a_new_tab_affordance_opens_a_new_tab(page, shot):
    """Scenario: A new-tab affordance opens a new tab"""


@pytest.mark.scenario("S-20-12")
@pytest.mark.skip(reason="not yet implemented")
def test_a_session_that_cannot_be_refreshed_forces_a_hard_reload_to_sign_in(page, shot):
    """Scenario: A session that cannot be refreshed forces a hard reload to sign-in"""


@pytest.mark.scenario("S-20-13")
@pytest.mark.skip(reason="not yet implemented")
def test_a_route_level_render_error_is_caught_and_explained(page, shot):
    """Scenario: A route-level render error is caught and explained"""


@pytest.mark.scenario("S-20-14")
@pytest.mark.skip(reason="not yet implemented")
def test_recovering_from_an_error_boundary_does_a_full_reload(page, shot):
    """Scenario: Recovering from an error boundary does a full reload"""


@pytest.mark.scenario("S-20-15")
@pytest.mark.skip(reason="not yet implemented")
def test_a_root_level_failure_still_renders_something(page, shot):
    """Scenario: A root-level failure still renders something"""


@pytest.mark.scenario("S-20-16")
@pytest.mark.skip(reason="not yet implemented")
def test_a_server_500_does_not_leave_the_user_on_a_blank_page(page, shot):
    """Scenario: A server 500 does not leave the user on a blank page"""

"""Implements ../../../screens/16-pages-outside-routes.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-16-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_legacy_workflow_builder_is_reachable_by_url(page, shot):
    """Scenario: The legacy workflow builder is reachable by URL"""


@pytest.mark.scenario("S-16-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_legacy_builder_is_not_the_composer(page, shot):
    """Scenario: The legacy builder is not the composer"""


@pytest.mark.scenario("S-16-03")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_legacy_builder_cannot_add_an_agent(page, shot):
    """Scenario: The legacy builder cannot add an agent"""


@pytest.mark.scenario("S-16-04")
@pytest.mark.skip(reason="not yet implemented")
def test_the_legacy_wizard_path_redirects_to_the_named_create_route(page, shot):
    """Scenario: The legacy wizard path redirects to the named create route"""


@pytest.mark.scenario("S-16-05")
@pytest.mark.skip(reason="not yet implemented")
def test_a_runid_deep_link_redirects_to_the_run_s_full_preview(page, shot):
    """Scenario: A runId deep-link redirects to the run's full preview"""


@pytest.mark.scenario("S-16-06")
@pytest.mark.skip(reason="not yet implemented")
def test_the_bare_path_with_no_payload_falls_back_to_run_history(page, shot):
    """Scenario: The bare path with no payload falls back to run history"""


@pytest.mark.scenario("S-16-07")
@pytest.mark.skip(reason="not yet implemented")
def test_an_oversized_project_explains_itself_and_offers_a_way_out(page, shot):
    """Scenario: An oversized project explains itself and offers a way out"""


@pytest.mark.scenario("S-16-08")
@pytest.mark.skip(reason="not yet implemented")
def test_the_app_builder_full_screen_button_hands_files_over_in_sessionstorage(page, shot):
    """Scenario: The App Builder full-screen button hands files over in sessionStorage"""


@pytest.mark.scenario("S-16-09")
@pytest.mark.skip(reason="not yet implemented")
def test_handoff_settings_offers_the_install_command(page, shot):
    """Scenario: Handoff settings offers the install command"""


@pytest.mark.scenario("S-16-10")
@pytest.mark.skip(reason="not yet implemented")
def test_a_github_token_can_be_saved_and_is_never_read_back(page, shot):
    """Scenario: A GitHub token can be saved and is never read back"""


@pytest.mark.scenario("S-16-11")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_a_saved_github_token_is_not_echoed_to_the_client(page, shot):
    """Scenario: A saved GitHub token is not echoed to the client"""


@pytest.mark.scenario("S-16-12")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_an_api_key_is_shown_once_and_never_again(page, shot):
    """Scenario: An API key is shown once and never again"""


@pytest.mark.scenario("S-16-13")
@pytest.mark.skip(reason="not yet implemented")
def test_handoff_settings_requires_authentication(page, shot):
    """Scenario: Handoff settings requires authentication"""


@pytest.mark.scenario("S-16-14")
@pytest.mark.skip(reason="not yet implemented")
def test_one_user_cannot_see_another_s_handoff_credentials(page, shot):
    """Scenario: One user cannot see another's handoff credentials"""


@pytest.mark.scenario("S-16-15")
@pytest.mark.skip(reason="not yet implemented")
def test_an_invalid_handoff_token_is_refused_clearly(page, shot):
    """Scenario: An invalid handoff token is refused clearly"""


@pytest.mark.scenario("S-16-16")
@pytest.mark.skip(reason="not yet implemented")
def test_a_valid_handoff_token_opens_the_handoff_workflow(page, shot):
    """Scenario: A valid handoff token opens the handoff workflow"""


@pytest.mark.scenario("S-16-17")
@pytest.mark.skip(reason="not yet implemented")
def test_a_handoff_token_belonging_to_another_user_is_refused(page, shot):
    """Scenario: A handoff token belonging to another user is refused"""

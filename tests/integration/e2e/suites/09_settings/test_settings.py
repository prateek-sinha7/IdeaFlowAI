"""Implements ../../../screens/09-settings.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-09-01")
@pytest.mark.skip(reason="not yet implemented")
def test_every_tab_is_addressable_by_url(page, shot):
    """Scenario: Every tab is addressable by URL"""


@pytest.mark.scenario("S-09-02")
@pytest.mark.skip(reason="not yet implemented")
def test_clicking_a_tab_pushes_its_url(page, shot):
    """Scenario: Clicking a tab pushes its URL"""


@pytest.mark.scenario("S-09-03")
@pytest.mark.skip(reason="not yet implemented")
def test_a_bare_settings_lands_on_profile(page, shot):
    """Scenario: A bare /settings lands on Profile"""


@pytest.mark.scenario("S-09-04")
@pytest.mark.skip(reason="not yet implemented")
def test_profile_shows_identity_and_plan_with_email_read_only(page, shot):
    """Scenario: Profile shows identity and plan, with email read-only"""


@pytest.mark.scenario("S-09-05")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_changing_the_password_requires_the_current_one_and_a_confirmation(page, shot):
    """Scenario: Changing the password requires the current one and a confirmation"""


@pytest.mark.scenario("S-09-06")
@pytest.mark.skip(reason="not yet implemented")
def test_the_model_preference_lists_the_available_models(page, shot):
    """Scenario: The model preference lists the available models"""


@pytest.mark.scenario("S-09-07")
@pytest.mark.skip(reason="not yet implemented")
def test_selecting_a_model_shows_its_description(page, shot):
    """Scenario: Selecting a model shows its description"""


@pytest.mark.scenario("S-09-08")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_saving_a_model_preference_persists_it(page, shot):
    """Scenario: Saving a model preference persists it"""


@pytest.mark.scenario("S-09-09")
@pytest.mark.skip(reason="not yet implemented")
def test_usage_shows_the_plan_and_its_deliverable_access(page, shot):
    """Scenario: Usage shows the plan and its deliverable access"""


@pytest.mark.scenario("S-09-10")
@pytest.mark.skip(reason="not yet implemented")
def test_deliverable_access_reflects_the_tier(page, shot):
    """Scenario: Deliverable access reflects the tier"""


@pytest.mark.scenario("S-09-11")
@pytest.mark.skip(reason="not yet implemented")
def test_the_constitution_editor_enforces_its_limit(page, shot):
    """Scenario: The constitution editor enforces its limit"""


@pytest.mark.scenario("S-09-12")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_a_saved_constitution_persists_across_a_reload(page, shot):
    """Scenario: A saved constitution persists across a reload"""


@pytest.mark.scenario("S-09-13")
@pytest.mark.skip(reason="not yet implemented")
def test_mfa_is_unavailable_for_an_externally_managed_account(page, shot):
    """Scenario: MFA is unavailable for an externally-managed account"""


@pytest.mark.scenario("S-09-14")
@pytest.mark.skip(reason="not yet implemented")
def test_security_lists_both_second_factor_methods(page, shot):
    """Scenario: Security lists both second-factor methods"""


@pytest.mark.scenario("S-09-15")
@pytest.mark.skip(reason="not yet implemented")
def test_email_codes_are_a_toggle_not_a_wizard(page, shot):
    """Scenario: Email codes are a toggle, not a wizard"""


@pytest.mark.scenario("S-09-16")
@pytest.mark.skip(reason="not yet implemented")
def test_the_authenticator_row_offers_no_control_at_all(page, shot):
    """Scenario: The authenticator row offers no control at all"""


@pytest.mark.scenario("S-09-17")
@pytest.mark.skip(reason="not yet implemented")
def test_an_environment_with_no_methods_says_so(page, shot):
    """Scenario: An environment with no methods says so"""


@pytest.mark.scenario("S-09-18")
@pytest.mark.skip(reason="not yet implemented")
def test_email_mfa_changes_the_account_recovery_story(page, shot):
    """Scenario: Email MFA changes the account-recovery story"""


@pytest.mark.scenario("S-09-19")
@pytest.mark.skip(reason="not yet implemented")
def test_security_is_a_tab_not_a_page(page, shot):
    """Scenario: Security is a tab, not a page"""

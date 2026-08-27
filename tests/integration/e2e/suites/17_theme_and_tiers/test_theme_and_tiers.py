"""Implements ../../../screens/17-theme-and-tiers.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-17-01")
@pytest.mark.skip(reason="not yet implemented")
def test_dark_mode_applies_and_persists(page, shot):
    """Scenario: Dark mode applies and persists"""


@pytest.mark.scenario("S-17-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_theme_control_names_the_target_not_the_state(page, shot):
    """Scenario: The theme control names the target, not the state"""


@pytest.mark.scenario("S-17-03")
@pytest.mark.skip(reason="not yet implemented")
def test_every_major_surface_renders_in_both_themes(page, shot):
    """Scenario: Every major surface renders in both themes"""


@pytest.mark.scenario("S-17-04")
@pytest.mark.skip(reason="not yet implemented")
def test_theme_is_a_per_browser_preference_not_per_account(page, shot):
    """Scenario: Theme is a per-browser preference, not per-account"""


@pytest.mark.scenario("S-17-05")
@pytest.mark.skip(reason="not yet implemented")
def test_the_account_menu_reflects_the_role_not_the_tier(page, shot):
    """Scenario: The account menu reflects the role, not the tier"""


@pytest.mark.scenario("S-17-06")
@pytest.mark.skip(reason="not yet implemented")
def test_a_non_admin_is_redirected_away_from_the_admin_surface(page, shot):
    """Scenario: A non-admin is redirected away from the admin surface"""


@pytest.mark.scenario("S-17-07")
@pytest.mark.skip(reason="not yet implemented")
def test_deliverable_access_matches_the_tier(page, shot):
    """Scenario: Deliverable access matches the tier"""


@pytest.mark.scenario("S-17-08")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_deliverable_access_omits_workflows_the_catalog_offers(page, shot):
    """Scenario: Deliverable Access omits workflows the catalog offers"""


@pytest.mark.scenario("S-17-09")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_hexaware_user_gains_prototype_and_loses_presentations(page, shot):
    """Scenario: A hexaware user gains prototype and loses presentations"""


@pytest.mark.scenario("S-17-10")
@pytest.mark.skip(reason="not yet implemented")
def test_the_admin_dialog_offers_every_tier_the_backend_knows(page, shot):
    """Scenario: The admin dialog offers every tier the backend knows"""


@pytest.mark.scenario("S-17-11")
@pytest.mark.skip(reason="not yet implemented")
def test_entitlement_is_enforced_by_the_backend_not_only_the_badge(page, shot):
    """Scenario: Entitlement is enforced by the backend, not only the badge"""


@pytest.mark.scenario("S-17-12")
@pytest.mark.skip(reason="not yet implemented")
def test_one_user_s_runs_are_invisible_to_another(page, shot):
    """Scenario: One user's runs are invisible to another"""

"""Implements ../../../screens/02-home-catalog.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-02-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_catalog_renders_on_a_cold_dashboard_load(page, shot):
    """Scenario: The catalog renders on a cold dashboard load"""


@pytest.mark.scenario("S-02-02")
@pytest.mark.skip(reason="not yet implemented")
def test_create_renders_the_identical_catalog(page, shot):
    """Scenario: /create renders the identical catalog"""


@pytest.mark.scenario("S-02-03")
@pytest.mark.skip(reason="not yet implemented")
def test_coming_soon_cards_are_present_but_not_launchable(page, shot):
    """Scenario: Coming Soon cards are present but not launchable"""


@pytest.mark.scenario("S-02-04")
@pytest.mark.skip(reason="not yet implemented")
def test_a_launchable_card_opens_that_workflow_s_launch_surface(page, shot):
    """Scenario: A launchable card opens that workflow's launch surface"""


@pytest.mark.scenario("S-02-05")
@pytest.mark.skip(reason="not yet implemented")
def test_the_inspect_affordance_opens_details_without_launching(page, shot):
    """Scenario: The inspect affordance opens details without launching"""


@pytest.mark.scenario("S-02-06")
@pytest.mark.skip(reason="not yet implemented")
def test_every_catalog_card_renders_regardless_of_tier(page, shot):
    """Scenario: Every catalog card renders regardless of tier"""


@pytest.mark.scenario("S-02-07")
@pytest.mark.skip(reason="not yet implemented")
def test_the_lock_badge_names_the_tier_a_card_needs(page, shot):
    """Scenario: The lock badge names the tier a card needs"""


@pytest.mark.scenario("S-02-08")
@pytest.mark.skip(reason="not yet implemented")
def test_a_locked_card_cannot_be_launched(page, shot):
    """Scenario: A locked card cannot be launched"""


@pytest.mark.scenario("S-02-09")
@pytest.mark.skip(reason="not yet implemented")
def test_the_backend_refuses_a_launch_the_badge_says_is_locked(page, shot):
    """Scenario: The backend refuses a launch the badge says is locked"""


@pytest.mark.scenario("S-02-10")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_spec_014_test_fixtures_appear_as_launchable_product_cards(page, shot):
    """Scenario: spec-014 test fixtures appear as launchable product cards"""


@pytest.mark.scenario("S-02-11")
@pytest.mark.skip(reason="not yet implemented")
def test_jump_back_in_lists_recent_runs_and_opens_them(page, shot):
    """Scenario: Jump back in lists recent runs and opens them"""


@pytest.mark.scenario("S-02-12")
@pytest.mark.skip(reason="not yet implemented")
def test_a_live_run_is_distinguishable_from_a_finished_one(page, shot):
    """Scenario: A live run is distinguishable from a finished one"""


@pytest.mark.scenario("S-02-13")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_saved_override_changes_the_catalog_card_s_agent_estimate(page, shot):
    """Scenario: A saved override changes the catalog card's agent estimate"""

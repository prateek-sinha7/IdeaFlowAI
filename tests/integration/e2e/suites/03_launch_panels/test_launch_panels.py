"""Implements ../../../screens/03-launch-panels.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-03-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_presentation_wizard_renders_its_template_gallery(page, shot):
    """Scenario: The presentation wizard renders its template gallery"""


@pytest.mark.scenario("S-03-02")
@pytest.mark.skip(reason="not yet implemented")
def test_filtering_the_template_gallery_by_category_narrows_it(page, shot):
    """Scenario: Filtering the template gallery by category narrows it"""


@pytest.mark.scenario("S-03-03")
@pytest.mark.skip(reason="not yet implemented")
def test_searching_templates_filters_by_name(page, shot):
    """Scenario: Searching templates filters by name"""


@pytest.mark.scenario("S-03-04")
@pytest.mark.skip(reason="not yet implemented")
def test_the_prototype_wizard_offers_three_tabs_and_a_blank_canvas_option(page, shot):
    """Scenario: The prototype wizard offers three tabs and a blank-canvas option"""


@pytest.mark.scenario("S-03-05")
@pytest.mark.skip(reason="not yet implemented")
def test_the_prototype_template_search_uses_its_own_field_name(page, shot):
    """Scenario: The prototype template search uses its own field name"""


@pytest.mark.scenario("S-03-06")
@pytest.mark.skip(reason="not yet implemented")
def test_each_wizard_tab_reveals_its_own_panel(page, shot):
    """Scenario: Each wizard tab reveals its own panel"""


@pytest.mark.scenario("S-03-07")
@pytest.mark.skip(reason="not yet implemented")
def test_the_user_stories_panel_names_its_own_workflow(page, shot):
    """Scenario: The user-stories panel names its own workflow"""


@pytest.mark.scenario("S-03-08")
@pytest.mark.skip(reason="not yet implemented")
def test_a_catalog_workflow_cold_loads_onto_the_right_panel(page, shot):
    """Scenario: A catalog workflow cold-loads onto the right panel"""


@pytest.mark.scenario("S-03-09")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_cold_loading_create_app_shows_the_user_stories_panel(page, shot):
    """Scenario: Cold-loading /create/app shows the user-stories panel"""


@pytest.mark.scenario("S-03-10")
@pytest.mark.skip(reason="not yet implemented")
def test_run_is_disabled_until_the_brief_is_long_enough(page, shot):
    """Scenario: Run is disabled until the brief is long enough"""


@pytest.mark.scenario("S-03-11")
@pytest.mark.skip(reason="not yet implemented")
def test_the_advanced_control_opens_the_agent_roster(page, shot):
    """Scenario: The Advanced control opens the agent roster"""


@pytest.mark.scenario("S-03-12")
@pytest.mark.skip(reason="not yet implemented")
def test_review_gates_can_be_set_before_launch(page, shot):
    """Scenario: Review gates can be set before launch"""


@pytest.mark.scenario("S-03-13")
@pytest.mark.skip(reason="not yet implemented")
def test_attaching_a_file_is_offered_on_every_launch_panel(page, shot):
    """Scenario: Attaching a file is offered on every launch panel"""


@pytest.mark.scenario("S-03-14")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_launching_a_run_navigates_to_its_live_surface(page, shot):
    """Scenario: Launching a run navigates to its live surface"""


@pytest.mark.scenario("S-03-15")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_save_as_my_version_creates_a_user_override_of_a_built_in(page, shot):
    """Scenario: Save as my version creates a user override of a built-in"""

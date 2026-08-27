"""Implements ../../../screens/04-composer-canvas.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-04-01")
@pytest.mark.skip(reason="not yet implemented")
def test_a_brand_new_composer_opens_empty(page, shot):
    """Scenario: A brand-new composer opens empty"""


@pytest.mark.scenario("S-04-02")
@pytest.mark.skip(reason="not yet implemented")
def test_editing_a_saved_workflow_loads_its_steps(page, shot):
    """Scenario: Editing a saved workflow loads its steps"""


@pytest.mark.scenario("S-04-03")
@pytest.mark.skip(reason="not yet implemented")
def test_a_built_in_opens_read_to_copy_not_read_to_overwrite(page, shot):
    """Scenario: A built-in opens read-to-copy, not read-to-overwrite"""


@pytest.mark.scenario("S-04-04")
@pytest.mark.skip(reason="not yet implemented")
def test_a_built_in_canvas_survives_a_hard_refresh(page, shot):
    """Scenario: A built-in canvas survives a hard refresh"""


@pytest.mark.scenario("S-04-05")
@pytest.mark.skip(reason="not yet implemented")
def test_switching_between_simple_and_canvas_keeps_the_roster(page, shot):
    """Scenario: Switching between Simple and Canvas keeps the roster"""


@pytest.mark.scenario("S-04-06")
@pytest.mark.skip(reason="not yet implemented")
def test_adding_an_agent_from_the_library_modal(page, shot):
    """Scenario: Adding an agent from the library modal"""


@pytest.mark.scenario("S-04-07")
@pytest.mark.skip(reason="not yet implemented")
def test_reordering_a_node_moves_it_in_the_plan(page, shot):
    """Scenario: Reordering a node moves it in the plan"""


@pytest.mark.scenario("S-04-08")
@pytest.mark.skip(reason="not yet implemented")
def test_removing_a_node_drops_it_from_the_summary(page, shot):
    """Scenario: Removing a node drops it from the summary"""


@pytest.mark.scenario("S-04-09")
@pytest.mark.skip(reason="not yet implemented")
def test_renaming_a_node_updates_its_label_and_its_control_names(page, shot):
    """Scenario: Renaming a node updates its label and its control names"""


@pytest.mark.scenario("S-04-10")
@pytest.mark.skip(reason="not yet implemented")
def test_the_config_rail_s_agent_tab_has_five_sub_tabs_of_its_own(page, shot):
    """Scenario: The config rail's Agent tab has five sub-tabs of its own"""


@pytest.mark.scenario("S-04-11")
@pytest.mark.skip(reason="not yet implemented")
def test_the_agent_skills_picker_is_part_of_the_rail_not_a_modal(page, shot):
    """Scenario: The agent Skills picker is part of the rail, not a modal"""


@pytest.mark.scenario("S-04-12")
@pytest.mark.skip(reason="not yet implemented")
def test_each_capability_toggle_flips_independently(page, shot):
    """Scenario: Each capability toggle flips independently"""


@pytest.mark.scenario("S-04-13")
@pytest.mark.skip(reason="not yet implemented")
def test_choosing_a_deliverable_strategy_reveals_its_own_fields(page, shot):
    """Scenario: Choosing a deliverable strategy reveals its own fields"""


@pytest.mark.scenario("S-04-14")
@pytest.mark.skip(reason="not yet implemented")
def test_run_is_gated_on_a_long_enough_brief(page, shot):
    """Scenario: Run is gated on a long-enough brief"""


@pytest.mark.scenario("S-04-15")
@pytest.mark.skip(reason="not yet implemented")
def test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot(page, shot):
    """Scenario: A last-streamed built-in refuses an append-after-final-step slot"""


@pytest.mark.scenario("S-04-16")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_ppt_based_override_s_editor_calls_itself_custom(page, shot):
    """Scenario: A ppt-based override's editor calls itself CUSTOM"""


@pytest.mark.scenario("S-04-17")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_saving_a_copy_of_a_built_in_creates_a_new_row_and_leaves_the_original_alone(page, shot):
    """Scenario: Saving a copy of a built-in creates a new row and leaves the original alone"""


@pytest.mark.scenario("S-04-18")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_the_blank_custom_agent_template_is_withheld_when_authoring_an_override(page, shot):
    """Scenario: The blank custom-agent template is withheld when authoring an override"""


@pytest.mark.scenario("S-04-19")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_a_saved_composition_can_be_launched_from_the_composer(page, shot):
    """Scenario: A saved composition can be launched from the composer"""

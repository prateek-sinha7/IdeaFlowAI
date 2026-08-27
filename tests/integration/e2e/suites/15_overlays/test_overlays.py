"""Implements ../../../screens/15-overlays.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-15-01")
@pytest.mark.skip(reason="not yet implemented")
def test_inspecting_a_catalog_workflow_describes_it_without_launching(page, shot):
    """Scenario: Inspecting a catalog workflow describes it without launching"""


@pytest.mark.scenario("S-15-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_advanced_control_opens_the_full_agent_configuration(page, shot):
    """Scenario: The Advanced control opens the full agent configuration"""


@pytest.mark.scenario("S-15-03")
@pytest.mark.skip(reason="not yet implemented")
def test_the_advanced_layer_s_workflow_tab_exposes_the_deliverable_settings(page, shot):
    """Scenario: The Advanced layer's Workflow tab exposes the deliverable settings"""


@pytest.mark.scenario("S-15-04")
@pytest.mark.skip(reason="not yet implemented")
def test_open_in_full_canvas_escalates_to_the_composer(page, shot):
    """Scenario: Open in full canvas escalates to the composer"""


@pytest.mark.scenario("S-15-05")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_saving_from_the_advanced_layer_names_the_new_workflow(page, shot):
    """Scenario: Saving from the Advanced layer names the new workflow"""


@pytest.mark.scenario("S-15-06")
@pytest.mark.skip(reason="not yet implemented")
def test_the_add_agent_modal_lists_agents_by_category(page, shot):
    """Scenario: The add-agent modal lists agents by category"""


@pytest.mark.scenario("S-15-07")
@pytest.mark.skip(reason="not yet implemented")
def test_each_agent_card_is_individually_addressable(page, shot):
    """Scenario: Each agent card is individually addressable"""


@pytest.mark.scenario("S-15-08")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_add_agent_modal_cannot_be_closed_by_name_or_by_escape(page, shot):
    """Scenario: The add-agent modal cannot be closed by name or by Escape"""


@pytest.mark.scenario("S-15-09")
@pytest.mark.skip(reason="not yet implemented")
def test_the_library_item_drawer_opens_beside_the_list_not_over_it(page, shot):
    """Scenario: The library item drawer opens beside the list, not over it"""


@pytest.mark.scenario("S-15-10")
@pytest.mark.skip(reason="not yet implemented")
def test_the_agent_drawer_s_tabs_each_show_their_own_panel(page, shot):
    """Scenario: The agent drawer's tabs each show their own panel"""


@pytest.mark.scenario("S-15-11")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_with_no_suggested_hooks_says_so(page, shot):
    """Scenario: An agent with no suggested hooks says so"""


@pytest.mark.scenario("S-15-12")
@pytest.mark.skip(reason="not yet implemented")
def test_the_agent_config_tab_exposes_the_gate_overrides(page, shot):
    """Scenario: The agent Config tab exposes the gate overrides"""


@pytest.mark.scenario("S-15-13")
@pytest.mark.skip(reason="not yet implemented")
def test_the_workflow_actions_menu_offers_the_four_row_operations(page, shot):
    """Scenario: The workflow actions menu offers the four row operations"""


@pytest.mark.scenario("S-15-14")
@pytest.mark.skip(reason="not yet implemented")
def test_the_run_actions_menu_offers_only_delete(page, shot):
    """Scenario: The run actions menu offers only delete"""


@pytest.mark.scenario("S-15-15")
@pytest.mark.skip(reason="not yet implemented")
def test_the_version_picker_lists_a_run_s_artifact_versions(page, shot):
    """Scenario: The version picker lists a run's artifact versions"""


@pytest.mark.scenario("S-15-16")
@pytest.mark.skip(reason="not yet implemented")
def test_share_copies_a_link_rather_than_opening_a_dialog(page, shot):
    """Scenario: Share copies a link rather than opening a dialog"""


@pytest.mark.scenario("S-15-17")
@pytest.mark.skip(reason="not yet implemented")
def test_a_template_tile_opens_a_detail_modal_with_a_live_preview(page, shot):
    """Scenario: A template tile opens a detail modal with a live preview"""


@pytest.mark.scenario("S-15-18")
@pytest.mark.skip(reason="not yet implemented")
def test_the_gallery_mounts_one_live_iframe_per_tile(page, shot):
    """Scenario: The gallery mounts one live iframe per tile"""


@pytest.mark.scenario("S-15-19")
@pytest.mark.skip(reason="not yet implemented")
def test_custom_upload_is_offered_on_both_wizards_html_only(page, shot):
    """Scenario: Custom upload is offered on both wizards, HTML only"""


@pytest.mark.scenario("S-15-20")
@pytest.mark.skip(reason="not yet implemented")
def test_a_design_system_tile_shows_its_full_design_md(page, shot):
    """Scenario: A design-system tile shows its full DESIGN.md"""


@pytest.mark.scenario("S-15-21")
@pytest.mark.skip(reason="not yet implemented")
def test_a_custom_design_system_is_pasted_not_uploaded(page, shot):
    """Scenario: A custom design system is pasted, not uploaded"""


@pytest.mark.scenario("S-15-22")
@pytest.mark.skip(reason="not yet implemented")
def test_add_user_collects_credentials_plan_and_the_admin_flag(page, shot):
    """Scenario: Add user collects credentials, plan and the admin flag"""


@pytest.mark.scenario("S-15-23")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_create_user_dialog_can_be_abandoned(page, shot):
    """Scenario: The create-user dialog can be abandoned"""


@pytest.mark.scenario("S-15-24")
@pytest.mark.skip(reason="not yet implemented")
def test_the_divert_picker_opens_from_the_config_rail_not_the_canvas(page, shot):
    """Scenario: The divert picker opens from the config rail, not the canvas"""


@pytest.mark.scenario("S-15-25")
@pytest.mark.skip(reason="not yet implemented")
def test_the_divert_picker_groups_and_searches_the_catalogue(page, shot):
    """Scenario: The divert picker groups and searches the catalogue"""


@pytest.mark.scenario("S-15-26")
@pytest.mark.skip(reason="not yet implemented")
def test_a_failed_workflow_fetch_degrades_to_free_text(page, shot):
    """Scenario: A failed workflow fetch degrades to free text"""


@pytest.mark.scenario("S-15-27")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_skill_manager_is_reachable(page, shot):
    """Scenario: The skill manager is reachable"""


@pytest.mark.scenario("S-15-28")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_prototype_deliverable_offers_source_and_tweaks(page, shot):
    """Scenario: A prototype deliverable offers source and tweaks"""


@pytest.mark.scenario("S-15-29")
@pytest.mark.skip(reason="not yet implemented")
def test_menus_and_drawers_close_without_navigating(page, shot):
    """Scenario: Menus and drawers close without navigating"""

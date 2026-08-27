"""Implements ../../../screens/23-controls-inventory.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-23-01")
@pytest.mark.skip(reason="not yet implemented")
def test_every_deliverable_type_can_be_revised_in_place(page, shot):
    """Scenario: Every deliverable type can be revised in place"""


@pytest.mark.scenario("S-23-02")
@pytest.mark.skip(reason="not yet implemented")
def test_revision_fields_share_an_accessible_name_but_not_a_name_attribute(page, shot):
    """Scenario: Revision fields share an accessible name but not a name attribute"""


@pytest.mark.scenario("S-23-03")
@pytest.mark.skip(reason="not yet implemented")
def test_an_empty_revision_does_nothing(page, shot):
    """Scenario: An empty revision does nothing"""


@pytest.mark.scenario("S-23-04")
@pytest.mark.skip(reason="not yet implemented")
def test_submitting_a_revision_clears_the_field(page, shot):
    """Scenario: Submitting a revision clears the field"""


@pytest.mark.scenario("S-23-05")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_proposal_can_be_confirmed_or_rejected(page, shot):
    """Scenario: An agent proposal can be confirmed or rejected"""


@pytest.mark.scenario("S-23-06")
@pytest.mark.skip(reason="not yet implemented")
def test_confirming_a_proposal_disables_it_while_it_runs(page, shot):
    """Scenario: Confirming a proposal disables it while it runs"""


@pytest.mark.scenario("S-23-07")
@pytest.mark.skip(reason="not yet implemented")
def test_a_refinement_chip_can_be_accepted_or_dismissed(page, shot):
    """Scenario: A refinement chip can be accepted or dismissed"""


@pytest.mark.scenario("S-23-08")
@pytest.mark.skip(reason="not yet implemented")
def test_the_chain_picker_offers_follow_on_workflows(page, shot):
    """Scenario: The chain picker offers follow-on workflows"""


@pytest.mark.scenario("S-23-09")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_s_reasoning_is_collapsible(page, shot):
    """Scenario: An agent's reasoning is collapsible"""


@pytest.mark.scenario("S-23-10")
@pytest.mark.skip(reason="not yet implemented")
def test_tool_calls_and_file_operations_are_shown_as_cards(page, shot):
    """Scenario: Tool calls and file operations are shown as cards"""


@pytest.mark.scenario("S-23-11")
@pytest.mark.skip(reason="not yet implemented")
def test_token_and_context_usage_are_visible(page, shot):
    """Scenario: Token and context usage are visible"""


@pytest.mark.scenario("S-23-12")
@pytest.mark.skip(reason="not yet implemented")
def test_terminal_runs_show_a_terminal_banner(page, shot):
    """Scenario: Terminal runs show a terminal banner"""


@pytest.mark.scenario("S-23-13")
@pytest.mark.skip(reason="not yet implemented")
def test_a_message_can_be_copied_edited_or_regenerated(page, shot):
    """Scenario: A message can be copied, edited or regenerated"""


@pytest.mark.scenario("S-23-14")
@pytest.mark.skip(reason="not yet implemented")
def test_chat_modes_can_be_added_and_removed(page, shot):
    """Scenario: Chat modes can be added and removed"""


@pytest.mark.scenario("S-23-15")
@pytest.mark.skip(reason="not yet implemented")
def test_files_can_be_attached_by_drop_or_by_chip(page, shot):
    """Scenario: Files can be attached by drop or by chip"""


@pytest.mark.scenario("S-23-16")
@pytest.mark.skip(reason="not yet implemented")
def test_activity_is_indicated_while_waiting(page, shot):
    """Scenario: Activity is indicated while waiting"""


@pytest.mark.scenario("S-23-17")
@pytest.mark.skip(reason="not yet implemented")
def test_a_conditional_route_renders_as_a_labelled_edge(page, shot):
    """Scenario: A conditional route renders as a labelled edge"""


@pytest.mark.scenario("S-23-18")
@pytest.mark.skip(reason="not yet implemented")
def test_route_outcomes_are_edited_in_the_rail(page, shot):
    """Scenario: Route outcomes are edited in the rail"""


@pytest.mark.scenario("S-23-19")
@pytest.mark.skip(reason="not yet implemented")
def test_a_route_outcome_names_its_condition_source(page, shot):
    """Scenario: A route outcome names its condition source"""


@pytest.mark.scenario("S-23-20")
@pytest.mark.skip(reason="not yet implemented")
def test_a_detached_node_is_marked_as_such(page, shot):
    """Scenario: A detached node is marked as such"""


@pytest.mark.scenario("S-23-21")
@pytest.mark.skip(reason="not yet implemented")
def test_edges_can_be_regrabbed_to_reparent_a_node(page, shot):
    """Scenario: Edges can be regrabbed to reparent a node"""


@pytest.mark.scenario("S-23-22")
@pytest.mark.skip(reason="not yet implemented")
def test_sub_agents_are_added_under_a_node(page, shot):
    """Scenario: Sub-agents are added under a node"""


@pytest.mark.scenario("S-23-23")
@pytest.mark.skip(reason="not yet implemented")
def test_numeric_limits_step_up_and_down(page, shot):
    """Scenario: Numeric limits step up and down"""


@pytest.mark.scenario("S-23-24")
@pytest.mark.skip(reason="not yet implemented")
def test_a_loop_node_caps_its_iterations(page, shot):
    """Scenario: A loop node caps its iterations"""


@pytest.mark.scenario("S-23-25")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_can_be_renamed_inline(page, shot):
    """Scenario: An agent can be renamed inline"""


@pytest.mark.scenario("S-23-26")
@pytest.mark.skip(reason="not yet implemented")
def test_a_node_declares_its_capabilities(page, shot):
    """Scenario: A node declares its capabilities"""


@pytest.mark.scenario("S-23-27")
@pytest.mark.skip(reason="not yet implemented")
def test_each_capability_is_configured_per_agent_by_name(page, shot):
    """Scenario: Each capability is configured per agent, by name"""


@pytest.mark.scenario("S-23-28")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_s_prompt_can_be_overridden(page, shot):
    """Scenario: An agent's prompt can be overridden"""


@pytest.mark.scenario("S-23-29")
@pytest.mark.skip(reason="not yet implemented")
def test_hooks_can_be_searched(page, shot):
    """Scenario: Hooks can be searched"""


@pytest.mark.scenario("S-23-30")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_s_skills_are_chosen_from_the_rail_not_a_modal(page, shot):
    """Scenario: An agent's skills are chosen from the rail, not a modal"""


@pytest.mark.scenario("S-23-31")
@pytest.mark.skip(reason="not yet implemented")
def test_the_audit_log_exports_in_three_formats(page, shot):
    """Scenario: The audit log exports in three formats"""


@pytest.mark.scenario("S-23-32")
@pytest.mark.skip(reason="not yet implemented")
def test_a_live_run_s_audit_tab_says_it_is_live(page, shot):
    """Scenario: A live run's audit tab says it is live"""


@pytest.mark.scenario("S-23-33")
@pytest.mark.skip(reason="not yet implemented")
def test_the_audit_log_can_be_searched(page, shot):
    """Scenario: The audit log can be searched"""


@pytest.mark.scenario("S-23-34")
@pytest.mark.skip(reason="not yet implemented")
def test_each_list_has_its_own_search_input(page, shot):
    """Scenario: Each list has its own search input"""


@pytest.mark.scenario("S-23-35")
@pytest.mark.skip(reason="not yet implemented")
def test_analytics_filters_by_model_as_well_as_pipeline(page, shot):
    """Scenario: Analytics filters by model as well as pipeline"""


@pytest.mark.scenario("S-23-36")
@pytest.mark.skip(reason="not yet implemented")
def test_run_history_sort_has_two_accessible_names(page, shot):
    """Scenario: Run history sort has two accessible names"""


@pytest.mark.scenario("S-23-37")
@pytest.mark.skip(reason="not yet implemented")
def test_design_systems_are_shown_as_colour_bands(page, shot):
    """Scenario: Design systems are shown as colour bands"""


@pytest.mark.scenario("S-23-38")
@pytest.mark.skip(reason="not yet implemented")
def test_a_generating_preview_shows_progress(page, shot):
    """Scenario: A generating preview shows progress"""


@pytest.mark.scenario("S-23-39")
@pytest.mark.skip(reason="not yet implemented")
def test_the_artifact_version_picker_is_addressable(page, shot):
    """Scenario: The artifact version picker is addressable"""


@pytest.mark.scenario("S-23-40")
@pytest.mark.skip(reason="not yet implemented")
def test_a_deliverable_can_be_downloaded_from_the_header(page, shot):
    """Scenario: A deliverable can be downloaded from the header"""


@pytest.mark.scenario("S-23-41")
@pytest.mark.skip(reason="not yet implemented")
def test_a_prototype_s_html_can_be_edited_directly(page, shot):
    """Scenario: A prototype's HTML can be edited directly"""


@pytest.mark.scenario("S-23-42")
@pytest.mark.skip(reason="not yet implemented")
def test_steps_show_review_and_divert_markers(page, shot):
    """Scenario: Steps show review and divert markers"""


@pytest.mark.scenario("S-23-43")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_detail_can_auto_refresh(page, shot):
    """Scenario: A run detail can auto-refresh"""


@pytest.mark.scenario("S-23-44")
@pytest.mark.skip(reason="not yet implemented")
def test_agent_construction_progress_is_reported(page, shot):
    """Scenario: Agent construction progress is reported"""


@pytest.mark.scenario("S-23-45")
@pytest.mark.skip(reason="not yet implemented")
def test_clarifications_are_summarised_with_a_count(page, shot):
    """Scenario: Clarifications are summarised with a count"""


@pytest.mark.scenario("S-23-46")
@pytest.mark.skip(reason="not yet implemented")
def test_a_chained_run_shows_where_it_came_from(page, shot):
    """Scenario: A chained run shows where it came from"""


@pytest.mark.scenario("S-23-47")
@pytest.mark.skip(reason="not yet implemented")
def test_a_notification_can_be_dismissed_individually(page, shot):
    """Scenario: A notification can be dismissed individually"""


@pytest.mark.scenario("S-23-48")
@pytest.mark.skip(reason="not yet implemented")
def test_the_admin_table_can_be_searched_and_its_tier_set(page, shot):
    """Scenario: The admin table can be searched and its tier set"""


@pytest.mark.scenario("S-23-49")
@pytest.mark.skip(reason="not yet implemented")
def test_a_custom_template_can_be_taken_from_a_url(page, shot):
    """Scenario: A custom template can be taken from a URL"""


@pytest.mark.scenario("S-23-50")
@pytest.mark.skip(reason="not yet implemented")
def test_handoff_credentials_are_labelled(page, shot):
    """Scenario: Handoff credentials are labelled"""


@pytest.mark.scenario("S-23-51")
@pytest.mark.skip(reason="not yet implemented")
def test_an_artifact_card_names_and_downloads_its_file(page, shot):
    """Scenario: An artifact card names and downloads its file"""


@pytest.mark.scenario("S-23-52")
@pytest.mark.skip(reason="not yet implemented")
def test_the_404_page_carries_the_brand_panel(page, shot):
    """Scenario: The 404 page carries the brand panel"""


@pytest.mark.scenario("S-23-53")
@pytest.mark.skip(reason="not yet implemented")
def test_a_dropped_realtime_connection_offers_a_reconnect(page, shot):
    """Scenario: A dropped realtime connection offers a reconnect"""


@pytest.mark.scenario("S-23-54")
@pytest.mark.skip(reason="not yet implemented")
def test_an_empty_run_history_invites_a_first_run(page, shot):
    """Scenario: An empty run history invites a first run"""


@pytest.mark.scenario("S-23-55")
@pytest.mark.skip(reason="not yet implemented")
def test_an_edited_message_is_saved_and_resent_in_one_action(page, shot):
    """Scenario: An edited message is saved and resent in one action"""


@pytest.mark.scenario("S-23-56")
@pytest.mark.skip(reason="not yet implemented")
def test_the_skill_manager_s_editor(page, shot):
    """Scenario: The skill manager's editor"""


@pytest.mark.scenario("S-23-57")
@pytest.mark.skip(reason="not yet implemented")
def test_the_sidebar_s_controls(page, shot):
    """Scenario: The sidebar's controls"""

"""Implements ../../../screens/07-run-detail.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-07-01")
@pytest.mark.skip(reason="not yet implemented")
def test_a_cold_load_of_a_run_shows_its_header_and_deliverable(page, shot):
    """Scenario: A cold load of a run shows its header and deliverable"""


@pytest.mark.scenario("S-07-02")
@pytest.mark.skip(reason="not yet implemented")
def test_every_tab_has_an_addressable_url(page, shot):
    """Scenario: Every tab has an addressable URL"""


@pytest.mark.scenario("S-07-03")
@pytest.mark.skip(reason="not yet implemented")
def test_clicking_a_tab_pushes_its_url(page, shot):
    """Scenario: Clicking a tab pushes its URL"""


@pytest.mark.scenario("S-07-04")
@pytest.mark.skip(reason="not yet implemented")
def test_switching_tabs_does_not_wipe_run_state(page, shot):
    """Scenario: Switching tabs does not wipe run state"""


@pytest.mark.scenario("S-07-05")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_parked_at_a_human_gate_stays_answerable_after_a_tab_click(page, shot):
    """Scenario: A run parked at a human gate stays answerable after a tab click"""


@pytest.mark.scenario("S-07-06")
@pytest.mark.skip(reason="not yet implemented")
def test_browser_back_and_forward_move_between_tabs_without_remounting_the_run(page, shot):
    """Scenario: Browser back and forward move between tabs without remounting the run"""


@pytest.mark.scenario("S-07-07")
@pytest.mark.skip(reason="not yet implemented")
def test_a_hard_refresh_on_any_tab_restores_that_tab(page, shot):
    """Scenario: A hard refresh on any tab restores that tab"""


@pytest.mark.scenario("S-07-08")
@pytest.mark.skip(reason="not yet implemented")
def test_the_workspace_tab_is_in_the_routing_contract(page, shot):
    """Scenario: The Workspace tab is in the routing contract"""


@pytest.mark.scenario("S-07-09")
@pytest.mark.skip(reason="not yet implemented")
def test_steps_lists_every_roster_agent_and_marks_the_untaken_branches(page, shot):
    """Scenario: Steps lists every roster agent and marks the untaken branches"""


@pytest.mark.scenario("S-07-10")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_row_is_addressable_by_url(page, shot):
    """Scenario: An agent row is addressable by URL"""


@pytest.mark.scenario("S-07-11")
@pytest.mark.skip(reason="not yet implemented")
def test_the_starting_point_shows_the_brief(page, shot):
    """Scenario: The starting point shows the brief"""


@pytest.mark.scenario("S-07-12")
@pytest.mark.skip(reason="not yet implemented")
def test_files_groups_the_deliverable_apart_from_intermediates(page, shot):
    """Scenario: Files groups the deliverable apart from intermediates"""


@pytest.mark.scenario("S-07-13")
@pytest.mark.skip(reason="not yet implemented")
def test_the_deliverable_reports_its_own_validation_state(page, shot):
    """Scenario: The deliverable reports its own validation state"""


@pytest.mark.scenario("S-07-14")
@pytest.mark.skip(reason="not yet implemented")
def test_workspace_lists_the_run_s_files_and_starts_unselected(page, shot):
    """Scenario: Workspace lists the run's files and starts unselected"""


@pytest.mark.scenario("S-07-15")
@pytest.mark.skip(reason="not yet implemented")
def test_artifacts_opens_expanded_all_files_opens_collapsed(page, shot):
    """Scenario: Artifacts opens expanded, All files opens collapsed"""


@pytest.mark.scenario("S-07-16")
@pytest.mark.skip(reason="not yet implemented")
def test_only_all_files_offers_sort_and_bulk_expand(page, shot):
    """Scenario: Only All files offers sort and bulk expand"""


@pytest.mark.scenario("S-07-17")
@pytest.mark.skip(reason="not yet implemented")
def test_the_viewer_renders_each_file_kind_as_what_it_is(page, shot):
    """Scenario: The viewer renders each file kind as what it is"""


@pytest.mark.scenario("S-07-18")
@pytest.mark.skip(reason="not yet implemented")
def test_markdown_and_html_can_be_toggled_between_source_and_rendered(page, shot):
    """Scenario: Markdown and HTML can be toggled between source and rendered"""


@pytest.mark.scenario("S-07-19")
@pytest.mark.skip(reason="not yet implemented")
def test_download_all_zips_the_whole_workspace(page, shot):
    """Scenario: Download all zips the whole workspace"""


@pytest.mark.scenario("S-07-20")
@pytest.mark.skip(reason="not yet implemented")
def test_a_ppt_v2_run_shows_both_artifacts_in_one_view(page, shot):
    """Scenario: A ppt_v2 run shows both artifacts in one view"""


@pytest.mark.scenario("S-07-21")
@pytest.mark.skip(reason="not yet implemented")
def test_each_empty_state_says_which_one_it_is(page, shot):
    """Scenario: Each empty state says which one it is"""


@pytest.mark.scenario("S-07-22")
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_workspace_says_where_the_deliverable_still_is(page, shot):
    """Scenario: An expired workspace says where the deliverable still is"""


@pytest.mark.scenario("S-07-23")
@pytest.mark.skip(reason="not yet implemented")
def test_a_workspace_with_no_top_level_output_offers_a_way_to_its_files(page, shot):
    """Scenario: A workspace with no top-level output offers a way to its files"""


@pytest.mark.scenario("S-07-24")
@pytest.mark.skip(reason="not yet implemented")
def test_audit_filters_by_category(page, shot):
    """Scenario: Audit filters by category"""


@pytest.mark.scenario("S-07-25")
@pytest.mark.skip(reason="not yet implemented")
def test_audit_records_the_human_and_conditional_gates_of_a_gated_run(page, shot):
    """Scenario: Audit records the human and conditional gates of a gated run"""


@pytest.mark.scenario("S-07-26")
@pytest.mark.skip(reason="not yet implemented")
def test_blocked_only_narrows_the_audit_to_denials(page, shot):
    """Scenario: Blocked-only narrows the audit to denials"""


@pytest.mark.scenario("S-07-27")
@pytest.mark.skip(reason="not yet implemented")
def test_the_preview_renderer_can_be_switched(page, shot):
    """Scenario: The preview renderer can be switched"""


@pytest.mark.scenario("S-07-28")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_choosing_html_for_a_markdown_deliverable_renders_nothing(page, shot):
    """Scenario: Choosing HTML for a markdown deliverable renders nothing"""


@pytest.mark.scenario("S-07-29")
@pytest.mark.skip(reason="not yet implemented")
def test_a_prototype_run_offers_its_own_renderer_mode(page, shot):
    """Scenario: A prototype run offers its own renderer mode"""


@pytest.mark.scenario("S-07-30")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_prototype_run_previews_its_validated_deliverable(page, shot):
    """Scenario: A prototype run previews its validated deliverable"""


@pytest.mark.scenario("S-07-31")
@pytest.mark.skip(reason="not yet implemented")
def test_a_deck_run_offers_slides_and_full_screen(page, shot):
    """Scenario: A deck run offers Slides and Full Screen"""


@pytest.mark.scenario("S-07-32")
@pytest.mark.skip(reason="not yet implemented")
def test_full_preview_is_its_own_url(page, shot):
    """Scenario: Full preview is its own URL"""


@pytest.mark.scenario("S-07-33")
@pytest.mark.skip(reason="not yet implemented")
def test_the_run_chat_lane_accepts_a_follow_up(page, shot):
    """Scenario: The run chat lane accepts a follow-up"""


@pytest.mark.scenario("S-07-34")
@pytest.mark.skip(reason="not yet implemented")
def test_back_to_history_returns_to_the_list(page, shot):
    """Scenario: Back to history returns to the list"""


@pytest.mark.scenario("S-07-35")
@pytest.mark.skip(reason="not yet implemented")
def test_a_specific_run_version_is_addressable(page, shot):
    """Scenario: A specific run version is addressable"""


@pytest.mark.scenario("S-07-36")
@pytest.mark.skip(reason="not yet implemented")
def test_a_live_run_streams_into_the_same_surface(page, shot):
    """Scenario: A live run streams into the same surface"""

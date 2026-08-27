"""Implements ../../../screens/05-saved-workflows.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-05-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_list_renders_with_stats_and_a_create_affordance(page, shot):
    """Scenario: The list renders with stats and a create affordance"""


@pytest.mark.scenario("S-05-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_stats_agree_with_the_cards(page, shot):
    """Scenario: The stats agree with the cards"""


@pytest.mark.scenario("S-05-03")
@pytest.mark.skip(reason="not yet implemented")
def test_every_card_exposes_its_own_actions(page, shot):
    """Scenario: Every card exposes its own actions"""


@pytest.mark.scenario("S-05-04")
@pytest.mark.skip(reason="not yet implemented")
def test_search_narrows_the_list_by_title(page, shot):
    """Scenario: Search narrows the list by title"""


@pytest.mark.scenario("S-05-05")
@pytest.mark.skip(reason="not yet implemented")
def test_new_workflow_opens_the_empty_composer(page, shot):
    """Scenario: New workflow opens the empty composer"""


@pytest.mark.scenario("S-05-06")
@pytest.mark.skip(reason="not yet implemented")
def test_a_card_opens_its_detail_view(page, shot):
    """Scenario: A card opens its detail view"""


@pytest.mark.scenario("S-05-07")
@pytest.mark.skip(reason="not yet implemented")
def test_the_detail_view_lists_agent_ids_not_display_names(page, shot):
    """Scenario: The detail view lists agent IDs, not display names"""


@pytest.mark.scenario("S-05-08")
@pytest.mark.skip(reason="not yet implemented")
def test_edit_opens_the_composer_bound_to_this_row(page, shot):
    """Scenario: Edit opens the composer bound to this row"""


@pytest.mark.scenario("S-05-09")
@pytest.mark.skip(reason="not yet implemented")
def test_run_opens_the_base_workflow_s_launch_panel(page, shot):
    """Scenario: Run opens the base workflow's launch panel"""


@pytest.mark.scenario("S-05-10")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_saved_override_s_run_panel_reports_the_base_agent_count(page, shot):
    """Scenario: A saved override's run panel reports the base agent count"""


@pytest.mark.scenario("S-05-11")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_a_workflow_can_be_deleted_from_its_card_menu(page, shot):
    """Scenario: A workflow can be deleted from its card menu"""


@pytest.mark.scenario("S-05-12")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_running_from_a_card_starts_a_run_of_that_workflow(page, shot):
    """Scenario: Running from a card starts a run of that workflow"""


@pytest.mark.scenario("S-05-13")
@pytest.mark.skip(reason="not yet implemented")
def test_an_override_can_be_reverted_to_the_original_built_in(page, shot):
    """Scenario: An override can be reverted to the original built-in"""

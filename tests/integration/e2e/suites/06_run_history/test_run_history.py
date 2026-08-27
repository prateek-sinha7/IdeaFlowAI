"""Implements ../../../screens/06-run-history.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-06-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_history_renders_with_its_controls(page, shot):
    """Scenario: The history renders with its controls"""


@pytest.mark.scenario("S-06-02")
@pytest.mark.skip(reason="not yet implemented")
def test_runs_are_grouped_by_time(page, shot):
    """Scenario: Runs are grouped by time"""


@pytest.mark.scenario("S-06-03")
@pytest.mark.skip(reason="not yet implemented")
def test_a_finished_row_shows_its_cost_a_running_row_does_not(page, shot):
    """Scenario: A finished row shows its cost, a running row does not"""


@pytest.mark.scenario("S-06-04")
@pytest.mark.skip(reason="not yet implemented")
def test_type_filter_counts_sum_to_the_total(page, shot):
    """Scenario: Type filter counts sum to the total"""


@pytest.mark.scenario("S-06-05")
@pytest.mark.skip(reason="not yet implemented")
def test_filtering_by_type_narrows_the_list(page, shot):
    """Scenario: Filtering by type narrows the list"""


@pytest.mark.scenario("S-06-06")
@pytest.mark.skip(reason="not yet implemented")
def test_the_type_filter_is_addressable_by_url(page, shot):
    """Scenario: The type filter is addressable by URL"""


@pytest.mark.scenario("S-06-07")
@pytest.mark.skip(reason="not yet implemented")
def test_the_chip_label_and_its_url_value_are_different_words(page, shot):
    """Scenario: The chip label and its URL value are different words"""


@pytest.mark.scenario("S-06-08")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_an_unrecognised_type_shows_an_empty_list_rather_than_an_error(page, shot):
    """Scenario: An unrecognised type shows an empty list rather than an error"""


@pytest.mark.scenario("S-06-09")
@pytest.mark.skip(reason="not yet implemented")
def test_sort_is_addressable_by_url_and_composes_with_type(page, shot):
    """Scenario: Sort is addressable by URL and composes with type"""


@pytest.mark.scenario("S-06-10")
@pytest.mark.skip(reason="not yet implemented")
def test_sorting_reorders_the_list(page, shot):
    """Scenario: Sorting reorders the list"""


@pytest.mark.scenario("S-06-11")
@pytest.mark.skip(reason="not yet implemented")
def test_search_filters_by_brief_text(page, shot):
    """Scenario: Search filters by brief text"""


@pytest.mark.scenario("S-06-12")
@pytest.mark.skip(reason="not yet implemented")
def test_auto_refresh_can_be_enabled_and_reports_its_interval(page, shot):
    """Scenario: Auto-refresh can be enabled and reports its interval"""


@pytest.mark.scenario("S-06-13")
@pytest.mark.skip(reason="not yet implemented")
def test_refresh_re_reads_without_losing_filters(page, shot):
    """Scenario: Refresh re-reads without losing filters"""


@pytest.mark.scenario("S-06-14")
@pytest.mark.skip(reason="not yet implemented")
def test_opening_a_row_lands_on_that_run(page, shot):
    """Scenario: Opening a row lands on that run"""


@pytest.mark.scenario("S-06-15")
@pytest.mark.skip(reason="not yet implemented")
def test_a_diverted_child_names_its_parent_and_the_branching_step(page, shot):
    """Scenario: A diverted child names its parent and the branching step"""


@pytest.mark.scenario("S-06-16")
@pytest.mark.skip(reason="not yet implemented")
def test_a_diverting_parent_names_its_child(page, shot):
    """Scenario: A diverting parent names its child"""


@pytest.mark.scenario("S-06-17")
@pytest.mark.skip(reason="not yet implemented")
def test_the_divert_badge_names_the_workflow_not_the_run_title(page, shot):
    """Scenario: The divert badge names the workflow, not the run title"""


@pytest.mark.scenario("S-06-18")
@pytest.mark.skip(reason="not yet implemented")
def test_run_actions_are_per_row(page, shot):
    """Scenario: Run actions are per-row"""


@pytest.mark.scenario("S-06-19")
@pytest.mark.skip(reason="not yet implemented")
def test_an_empty_history_is_explained(page, shot):
    """Scenario: An empty history is explained"""


@pytest.mark.scenario("S-06-20")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_card_can_be_opened_in_a_new_tab(page, shot):
    """Scenario: A run card can be opened in a new tab"""


@pytest.mark.scenario("S-06-21")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_run_history_rows_are_addressable_by_a_stable_hook(page, shot):
    """Scenario: Run history rows are addressable by a stable hook"""

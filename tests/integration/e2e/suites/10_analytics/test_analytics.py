"""Implements ../../../screens/10-analytics.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-10-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_analytics_screen_renders_its_tiles_and_controls(page, shot):
    """Scenario: The analytics screen renders its tiles and controls"""


@pytest.mark.scenario("S-10-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_token_tile_s_in_out_split_sums_to_its_total(page, shot):
    """Scenario: The token tile's in/out split sums to its total"""


@pytest.mark.scenario("S-10-03")
@pytest.mark.skip(reason="not yet implemented")
def test_average_per_run_is_consistent_with_the_totals(page, shot):
    """Scenario: Average per run is consistent with the totals"""


@pytest.mark.scenario("S-10-04")
@pytest.mark.skip(reason="not yet implemented")
def test_the_success_rate_matches_the_run_counts(page, shot):
    """Scenario: The success rate matches the run counts"""


@pytest.mark.scenario("S-10-05")
@pytest.mark.skip(reason="not yet implemented")
def test_changing_the_range_changes_the_data(page, shot):
    """Scenario: Changing the range changes the data"""


@pytest.mark.scenario("S-10-06")
@pytest.mark.skip(reason="not yet implemented")
def test_ranges_are_nested_a_wider_range_never_reports_less(page, shot):
    """Scenario: Ranges are nested — a wider range never reports less"""


@pytest.mark.scenario("S-10-07")
@pytest.mark.skip(reason="not yet implemented")
def test_the_range_is_addressable_by_url(page, shot):
    """Scenario: The range is addressable by URL"""


@pytest.mark.scenario("S-10-08")
@pytest.mark.skip(reason="not yet implemented")
def test_the_pipeline_filter_narrows_every_tile(page, shot):
    """Scenario: The pipeline filter narrows every tile"""


@pytest.mark.scenario("S-10-09")
@pytest.mark.skip(reason="not yet implemented")
def test_the_pipeline_filter_is_addressable_by_url(page, shot):
    """Scenario: The pipeline filter is addressable by URL"""


@pytest.mark.scenario("S-10-10")
@pytest.mark.skip(reason="not yet implemented")
def test_the_pipeline_breakdown_sums_to_the_totals(page, shot):
    """Scenario: The pipeline breakdown sums to the totals"""


@pytest.mark.scenario("S-10-11")
@pytest.mark.skip(reason="not yet implemented")
def test_daily_activity_plots_one_bar_per_active_day(page, shot):
    """Scenario: Daily activity plots one bar per active day"""


@pytest.mark.scenario("S-10-12")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_pipeline_breakdown_shows_a_duplicated_and_a_raw_label(page, shot):
    """Scenario: The pipeline breakdown shows a duplicated and a raw label"""


@pytest.mark.scenario("S-10-13")
@pytest.mark.skip(reason="not yet implemented")
def test_a_user_with_no_runs_sees_an_empty_state(page, shot):
    """Scenario: A user with no runs sees an empty state"""


@pytest.mark.scenario("S-10-14")
@pytest.mark.skip(reason="not yet implemented")
def test_analytics_is_scoped_to_the_signed_in_user(page, shot):
    """Scenario: Analytics is scoped to the signed-in user"""

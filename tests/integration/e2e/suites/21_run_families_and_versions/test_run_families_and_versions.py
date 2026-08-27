"""Implements ../../../screens/21-run-families-and-versions.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-21-01")
@pytest.mark.skip(reason="not yet implemented")
def test_runs_sharing_a_root_collapse_into_one_family_row(page, shot):
    """Scenario: Runs sharing a root collapse into one family row"""


@pytest.mark.scenario("S-21-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_version_badge_s_accessible_name_is_not_its_text(page, shot):
    """Scenario: The version badge's accessible name is not its text"""


@pytest.mark.scenario("S-21-03")
@pytest.mark.skip(reason="not yet implemented")
def test_a_family_expands_to_show_every_version(page, shot):
    """Scenario: A family expands to show every version"""


@pytest.mark.scenario("S-21-04")
@pytest.mark.skip(reason="not yet implemented")
def test_a_family_of_one_renders_as_a_plain_row(page, shot):
    """Scenario: A family of one renders as a plain row"""


@pytest.mark.scenario("S-21-05")
@pytest.mark.skip(reason="not yet implemented")
def test_the_family_counts_as_one_against_a_filter_chip(page, shot):
    """Scenario: The family counts as one against a filter chip"""


@pytest.mark.scenario("S-21-06")
@pytest.mark.skip(reason="not yet implemented")
def test_families_bucket_by_date_and_reorder_by_sort(page, shot):
    """Scenario: Families bucket by date and reorder by sort"""


@pytest.mark.scenario("S-21-07")
@pytest.mark.skip(reason="not yet implemented")
def test_a_revised_run_shows_its_version_timeline(page, shot):
    """Scenario: A revised run shows its version timeline"""


@pytest.mark.scenario("S-21-08")
@pytest.mark.skip(reason="not yet implemented")
def test_a_timeline_entry_names_what_it_revises(page, shot):
    """Scenario: A timeline entry names what it revises"""


@pytest.mark.scenario("S-21-09")
@pytest.mark.skip(reason="not yet implemented")
def test_selecting_a_version_navigates_to_it(page, shot):
    """Scenario: Selecting a version navigates to it"""


@pytest.mark.scenario("S-21-10")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_version_that_does_not_exist_is_refused(page, shot):
    """Scenario: A version that does not exist is refused"""


@pytest.mark.scenario("S-21-11")
@pytest.mark.skip(reason="not yet implemented")
def test_a_single_version_run_shows_no_timeline(page, shot):
    """Scenario: A single-version run shows no timeline"""


@pytest.mark.scenario("S-21-12")
@pytest.mark.skip(reason="not yet implemented")
def test_a_diverting_run_links_forward_to_the_run_it_triggered(page, shot):
    """Scenario: A diverting run links forward to the run it triggered"""


@pytest.mark.scenario("S-21-13")
@pytest.mark.skip(reason="not yet implemented")
def test_the_triggered_run_links_back_to_its_origin(page, shot):
    """Scenario: The triggered run links back to its origin"""


@pytest.mark.scenario("S-21-14")
@pytest.mark.skip(reason="not yet implemented")
def test_the_two_directions_are_distinguishable(page, shot):
    """Scenario: The two directions are distinguishable"""


@pytest.mark.scenario("S-21-15")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_diverted_run_s_chat_lane_names_its_target(page, shot):
    """Scenario: A diverted run's chat lane names its target"""

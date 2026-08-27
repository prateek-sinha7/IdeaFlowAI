"""Implements ../../../screens/14-run-states.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-14-01")
@pytest.mark.skip(reason="not yet implemented")
def test_a_failed_run_explains_itself_and_offers_a_way_forward(page, shot):
    """Scenario: A failed run explains itself and offers a way forward"""


@pytest.mark.scenario("S-14-02")
@pytest.mark.skip(reason="not yet implemented")
def test_a_failed_run_has_no_preview_tab(page, shot):
    """Scenario: A failed run has no Preview tab"""


@pytest.mark.scenario("S-14-03")
@pytest.mark.skip(reason="not yet implemented")
def test_a_cancelled_run_offers_to_resume(page, shot):
    """Scenario: A cancelled run offers to resume"""


@pytest.mark.scenario("S-14-04")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_cancelled_empty_state_names_a_tab_that_does_not_exist(page, shot):
    """Scenario: The cancelled empty-state names a tab that does not exist"""


@pytest.mark.scenario("S-14-05")
@pytest.mark.skip(reason="not yet implemented")
def test_a_diverted_run_points_at_its_continuation(page, shot):
    """Scenario: A diverted run points at its continuation"""


@pytest.mark.scenario("S-14-06")
@pytest.mark.skip(reason="not yet implemented")
def test_a_live_run_streams_and_can_be_stopped(page, shot):
    """Scenario: A live run streams and can be stopped"""


@pytest.mark.scenario("S-14-07")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_live_run_cannot_deep_link_any_tab(page, shot):
    """Scenario: A live run cannot deep-link any tab"""


@pytest.mark.scenario("S-14-08")
@pytest.mark.skip(reason="not yet implemented")
def test_the_same_tab_urls_work_once_the_run_finishes(page, shot):
    """Scenario: The same tab URLs work once the run finishes"""


@pytest.mark.scenario("S-14-09")
@pytest.mark.skip(reason="not yet implemented")
def test_a_failed_run_s_audit_reports_its_governance_totals(page, shot):
    """Scenario: A failed run's audit reports its governance totals"""


@pytest.mark.scenario("S-14-10")
@pytest.mark.skip(reason="not yet implemented")
def test_audit_categories_filter_the_trail(page, shot):
    """Scenario: Audit categories filter the trail"""


@pytest.mark.scenario("S-14-11")
@pytest.mark.skip(reason="not yet implemented")
def test_a_secret_scan_appears_as_a_security_record(page, shot):
    """Scenario: A secret scan appears as a security record"""


@pytest.mark.scenario("S-14-12")
@pytest.mark.skip(reason="not yet implemented")
def test_run_history_shows_the_right_status_chip(page, shot):
    """Scenario: Run history shows the right status chip"""


@pytest.mark.scenario("S-14-13")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_parked_at_a_human_gate_is_answerable(page, shot):
    """Scenario: A run parked at a human gate is answerable"""

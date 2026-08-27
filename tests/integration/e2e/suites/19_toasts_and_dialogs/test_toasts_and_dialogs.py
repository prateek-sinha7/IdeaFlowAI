"""Implements ../../../screens/19-toasts-and-dialogs.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-19-01")
@pytest.mark.skip(reason="not yet implemented")
def test_a_completed_run_raises_a_toast_with_a_way_into_the_result(page, shot):
    """Scenario: A completed run raises a toast with a way into the result"""


@pytest.mark.scenario("S-19-02")
@pytest.mark.skip(reason="not yet implemented")
def test_a_failed_run_names_the_workflow_in_the_toast(page, shot):
    """Scenario: A failed run names the workflow in the toast"""


@pytest.mark.scenario("S-19-03")
@pytest.mark.skip(reason="not yet implemented")
def test_a_completion_toast_dismisses_itself_after_7_seconds(page, shot):
    """Scenario: A completion toast dismisses itself after 7 seconds"""


@pytest.mark.scenario("S-19-04")
@pytest.mark.skip(reason="not yet implemented")
def test_a_toast_can_be_dismissed_early(page, shot):
    """Scenario: A toast can be dismissed early"""


@pytest.mark.scenario("S-19-05")
@pytest.mark.skip(reason="not yet implemented")
def test_toasts_stack_rather_than_replace(page, shot):
    """Scenario: Toasts stack rather than replace"""


@pytest.mark.scenario("S-19-06")
@pytest.mark.skip(reason="not yet implemented")
def test_a_toast_does_not_block_the_page_beneath_it(page, shot):
    """Scenario: A toast does not block the page beneath it"""


@pytest.mark.scenario("S-19-07")
@pytest.mark.skip(reason="not yet implemented")
def test_admin_actions_confirm_themselves_by_toast(page, shot):
    """Scenario: Admin actions confirm themselves by toast"""


@pytest.mark.scenario("S-19-08")
@pytest.mark.skip(reason="not yet implemented")
def test_an_admin_failure_is_reported_not_swallowed(page, shot):
    """Scenario: An admin failure is reported, not swallowed"""


@pytest.mark.scenario("S-19-09")
@pytest.mark.skip(reason="not yet implemented")
def test_the_two_toast_families_use_different_timeouts(page, shot):
    """Scenario: The two toast families use different timeouts"""


@pytest.mark.scenario("S-19-10")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_deleting_a_user_requires_confirmation(page, shot):
    """Scenario: Deleting a user requires confirmation"""


@pytest.mark.scenario("S-19-11")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_cancelling_a_delete_leaves_the_user_intact(page, shot):
    """Scenario: Cancelling a delete leaves the user intact"""


@pytest.mark.scenario("S-19-12")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_clicking_the_scrim_cancels_the_delete(page, shot):
    """Scenario: Clicking the scrim cancels the delete"""


@pytest.mark.scenario("S-19-13")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_confirming_removes_the_user_and_says_so(page, shot):
    """Scenario: Confirming removes the user and says so"""


@pytest.mark.scenario("S-19-14")
@pytest.mark.skip(reason="not yet implemented")
def test_an_admin_cannot_delete_themselves_into_lockout(page, shot):
    """Scenario: An admin cannot delete themselves into lockout"""


@pytest.mark.scenario("S-19-15")
@pytest.mark.skip(reason="not yet implemented")
def test_a_failed_download_reports_itself_through_window_alert(page, shot):
    """Scenario: A failed download reports itself through window.alert"""


@pytest.mark.scenario("S-19-16")
@pytest.mark.skip(reason="not yet implemented")
def test_every_test_that_can_trigger_a_download_registers_a_dialog_handler(page, shot):
    """Scenario: Every test that can trigger a download registers a dialog handler"""


@pytest.mark.scenario("S-19-17")
@pytest.mark.skip(reason="not yet implemented")
def test_download_failures_are_the_only_native_dialogs_in_the_product(page, shot):
    """Scenario: Download failures are the only native dialogs in the product"""

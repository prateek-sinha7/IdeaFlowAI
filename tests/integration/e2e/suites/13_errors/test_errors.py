"""Implements ../../../screens/13-errors.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-13-01")
@pytest.mark.skip(reason="not yet implemented")
def test_an_unrecognised_url_shows_the_404_screen(page, shot):
    """Scenario: An unrecognised URL shows the 404 screen"""


@pytest.mark.scenario("S-13-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_404_offers_a_way_back_that_works(page, shot):
    """Scenario: The 404 offers a way back that works"""


@pytest.mark.scenario("S-13-03")
@pytest.mark.skip(reason="not yet implemented")
def test_the_404_create_action_reaches_the_composer(page, shot):
    """Scenario: The 404 create action reaches the composer"""


@pytest.mark.scenario("S-13-04")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_404_offers_sign_in_to_an_already_authenticated_user(page, shot):
    """Scenario: The 404 offers Sign in to an already-authenticated user"""


@pytest.mark.scenario("S-13-05")
@pytest.mark.skip(reason="not yet implemented")
def test_malformed_routes_fall_back_rather_than_crash(page, shot):
    """Scenario: Malformed routes fall back rather than crash"""


@pytest.mark.scenario("S-13-06")
@pytest.mark.skip(reason="not yet implemented")
def test_a_bare_settings_redirects_to_profile(page, shot):
    """Scenario: A bare /settings redirects to Profile"""


@pytest.mark.scenario("S-13-07")
@pytest.mark.skip(reason="not yet implemented")
def test_legacy_library_list_urls_are_redirected_not_404_d(page, shot):
    """Scenario: Legacy library list URLs are redirected, not 404'd"""


@pytest.mark.scenario("S-13-08")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_id_that_does_not_exist_falls_back_to_the_generic_404(page, shot):
    """Scenario: A run id that does not exist falls back to the generic 404"""


@pytest.mark.scenario("S-13-09")
@pytest.mark.skip(reason="not yet implemented")
def test_a_workflow_id_that_does_not_exist_falls_back_to_the_generic_404(page, shot):
    """Scenario: A workflow id that does not exist falls back to the generic 404"""


@pytest.mark.scenario("S-13-10")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_missing_resource_errors_are_indistinguishable_from_a_bad_url(page, shot):
    """Scenario: Missing-resource errors are indistinguishable from a bad URL"""


@pytest.mark.scenario("S-13-11")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_a_nonexistent_artifact_version_falls_back_to_v1_without_saying_so(page, shot):
    """Scenario: A nonexistent artifact version falls back to v1 without saying so"""


@pytest.mark.scenario("S-13-12")
@pytest.mark.skip(reason="not yet implemented")
def test_an_oversized_full_screen_preview_explains_itself(page, shot):
    """Scenario: An oversized full-screen preview explains itself"""


@pytest.mark.scenario("S-13-13")
@pytest.mark.skip(reason="not yet implemented")
def test_another_user_s_run_is_not_readable(page, shot):
    """Scenario: Another user's run is not readable"""


@pytest.mark.scenario("S-13-14")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_file_cannot_be_fetched_across_an_ownership_boundary(page, shot):
    """Scenario: A run file cannot be fetched across an ownership boundary"""


@pytest.mark.scenario("S-13-15")
@pytest.mark.skip(reason="not yet implemented")
def test_a_request_with_no_credentials_is_answered_401_not_403(page, shot):
    """Scenario: A request with no credentials is answered 401, not 403"""


@pytest.mark.scenario("S-13-16")
@pytest.mark.skip(reason="not yet implemented")
def test_a_request_with_a_malformed_token_is_answered_401(page, shot):
    """Scenario: A request with a malformed token is answered 401"""


@pytest.mark.scenario("S-13-17")
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_session_is_recovered_once_before_being_surrendered(page, shot):
    """Scenario: An expired session is recovered once before being surrendered"""


@pytest.mark.scenario("S-13-18")
@pytest.mark.skip(reason="not yet implemented")
def test_an_unrefreshable_session_ends_at_sign_in_with_an_explanation(page, shot):
    """Scenario: An unrefreshable session ends at sign-in with an explanation"""


@pytest.mark.scenario("S-13-19")
@pytest.mark.skip(reason="not yet implemented")
def test_a_backend_outage_is_reported_not_swallowed(page, shot):
    """Scenario: A backend outage is reported, not swallowed"""


@pytest.mark.scenario("S-13-20")
@pytest.mark.skip(reason="not yet implemented")
def test_a_failed_run_is_presented_as_failed(page, shot):
    """Scenario: A failed run is presented as failed"""

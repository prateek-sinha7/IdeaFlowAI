"""Implements ../../../screens/24-api-contract.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-24-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_endpoint_inventory_matches_the_snapshot(page, shot):
    """Scenario: The endpoint inventory matches the snapshot"""


@pytest.mark.scenario("S-24-02")
@pytest.mark.skip(reason="not yet implemented")
def test_no_endpoint_loses_its_authentication_silently(page, shot):
    """Scenario: No endpoint loses its authentication silently"""


@pytest.mark.scenario("S-24-03")
@pytest.mark.skip(reason="not yet implemented")
def test_the_public_list_is_exactly_eighteen_and_each_is_deliberate(page, shot):
    """Scenario: The public list is exactly eighteen, and each is deliberate"""


@pytest.mark.scenario("S-24-04")
@pytest.mark.skip(reason="not yet implemented")
def test_a_request_with_no_credentials_is_answered_401_not_403(page, shot):
    """Scenario: A request with no credentials is answered 401, not 403"""


@pytest.mark.scenario("S-24-05")
@pytest.mark.skip(reason="not yet implemented")
def test_registration_is_permanently_closed(page, shot):
    """Scenario: Registration is permanently closed"""


@pytest.mark.scenario("S-24-06")
@pytest.mark.skip(reason="not yet implemented")
def test_login_returns_either_a_session_or_a_challenge(page, shot):
    """Scenario: Login returns either a session or a challenge"""


@pytest.mark.scenario("S-24-07")
@pytest.mark.skip(reason="not yet implemented")
def test_a_challenge_is_answered_on_its_own_endpoint(page, shot):
    """Scenario: A challenge is answered on its own endpoint"""


@pytest.mark.scenario("S-24-08")
@pytest.mark.skip(reason="not yet implemented")
def test_logout_works_with_an_already_invalid_token(page, shot):
    """Scenario: Logout works with an already-invalid token"""


@pytest.mark.scenario("S-24-09")
@pytest.mark.skip(reason="not yet implemented")
def test_password_recovery_refuses_when_email_is_a_second_factor(page, shot):
    """Scenario: Password recovery refuses when email is a second factor"""


@pytest.mark.scenario("S-24-10")
@pytest.mark.skip(reason="not yet implemented")
def test_second_factor_management_requires_a_session(page, shot):
    """Scenario: Second-factor management requires a session"""


@pytest.mark.scenario("S-24-11")
@pytest.mark.skip(reason="not yet implemented")
def test_every_admin_endpoint_requires_an_admin(page, shot):
    """Scenario: Every admin endpoint requires an admin"""


@pytest.mark.scenario("S-24-12")
@pytest.mark.skip(reason="not yet implemented")
def test_creating_a_user_answers_201_with_the_created_user(page, shot):
    """Scenario: Creating a user answers 201 with the created user"""


@pytest.mark.scenario("S-24-13")
@pytest.mark.skip(reason="not yet implemented")
def test_deleting_a_user_answers_204_with_no_body(page, shot):
    """Scenario: Deleting a user answers 204 with no body"""


@pytest.mark.scenario("S-24-14")
@pytest.mark.skip(reason="not yet implemented")
def test_role_and_tier_changes_return_the_updated_user(page, shot):
    """Scenario: Role and tier changes return the updated user"""


@pytest.mark.scenario("S-24-15")
@pytest.mark.skip(reason="not yet implemented")
def test_template_previews_load_without_a_token(page, shot):
    """Scenario: Template previews load without a token"""


@pytest.mark.scenario("S-24-16")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_the_asset_route_refuses_path_traversal(page, shot):
    """Scenario: The asset route refuses path traversal"""


@pytest.mark.scenario("S-24-17")
@pytest.mark.skip(reason="not yet implemented")
def test_a_missing_asset_is_a_404_not_a_500(page, shot):
    """Scenario: A missing asset is a 404, not a 500"""


@pytest.mark.scenario("S-24-18")
@pytest.mark.skip(reason="not yet implemented")
def test_handoff_creation_is_authenticated_by_api_key_not_by_jwt(page, shot):
    """Scenario: Handoff creation is authenticated by API key, not by JWT"""


@pytest.mark.scenario("S-24-19")
@pytest.mark.skip(reason="not yet implemented")
def test_handoff_creation_without_a_valid_key_is_refused(page, shot):
    """Scenario: Handoff creation without a valid key is refused"""


@pytest.mark.scenario("S-24-20")
@pytest.mark.skip(reason="not yet implemented")
def test_a_github_pat_is_not_required_to_create_a_handoff(page, shot):
    """Scenario: A GitHub PAT is not required to create a handoff"""


@pytest.mark.scenario("S-24-21")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_is_readable_only_by_its_owner(page, shot):
    """Scenario: A run is readable only by its owner"""


@pytest.mark.scenario("S-24-22")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_s_files_cannot_be_fetched_across_an_ownership_boundary(page, shot):
    """Scenario: A run's files cannot be fetched across an ownership boundary"""


@pytest.mark.scenario("S-24-23")
@pytest.mark.skip(reason="not yet implemented")
def test_the_listing_describes_the_whole_workspace(page, shot):
    """Scenario: The listing describes the whole workspace"""


@pytest.mark.scenario("S-24-24")
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_workspace_is_stated_not_inferred(page, shot):
    """Scenario: An expired workspace is stated, not inferred"""


@pytest.mark.scenario("S-24-25")
@pytest.mark.skip(reason="not yet implemented")
def test_the_reserved_subtrees_are_never_listed(page, shot):
    """Scenario: The reserved subtrees are never listed"""


@pytest.mark.scenario("S-24-26")
@pytest.mark.skip(reason="not yet implemented")
def test_an_html_workspace_file_is_never_served_inline(page, shot):
    """Scenario: An HTML workspace file is never served inline"""


@pytest.mark.scenario("S-24-27")
@pytest.mark.skip(reason="not yet implemented")
def test_text_extensions_come_back_inline_as_plain_text(page, shot):
    """Scenario: Text extensions come back inline as plain text"""


@pytest.mark.scenario("S-24-28")
@pytest.mark.skip(reason="not yet implemented")
def test_the_path_parameter_refuses_to_leave_the_run_directory(page, shot):
    """Scenario: The path parameter refuses to leave the run directory"""


@pytest.mark.scenario("S-24-29")
@pytest.mark.skip(reason="not yet implemented")
def test_a_symlink_cannot_be_used_to_read_outside_the_run_directory(page, shot):
    """Scenario: A symlink cannot be used to read outside the run directory"""


@pytest.mark.scenario("S-24-30")
@pytest.mark.skip(reason="not yet implemented")
def test_a_file_too_large_to_preview_is_refused_not_streamed(page, shot):
    """Scenario: A file too large to preview is refused, not streamed"""


@pytest.mark.scenario("S-24-31")
@pytest.mark.skip(reason="not yet implemented")
def test_the_zip_holds_exactly_what_the_listing_showed(page, shot):
    """Scenario: The zip holds exactly what the listing showed"""


@pytest.mark.scenario("S-24-32")
@pytest.mark.skip(reason="not yet implemented")
def test_an_oversized_workspace_is_refused_rather_than_archived(page, shot):
    """Scenario: An oversized workspace is refused rather than archived"""


@pytest.mark.scenario("S-24-33")
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_workspace_has_nothing_to_serve(page, shot):
    """Scenario: An expired workspace has nothing to serve"""


@pytest.mark.scenario("S-24-34")
@pytest.mark.skip(reason="not yet implemented")
def test_the_sandbox_is_unreachable_across_an_ownership_boundary(page, shot):
    """Scenario: The sandbox is unreachable across an ownership boundary"""

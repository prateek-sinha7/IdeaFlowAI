"""Implements ../../../screens/01-auth.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-01-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_sign_in_screen_renders_for_an_anonymous_visitor(page, shot):
    """Scenario: The sign-in screen renders for an anonymous visitor"""


@pytest.mark.scenario("S-01-03")
@pytest.mark.skip(reason="not yet implemented")
def test_an_administrator_is_not_redirected_to_the_admin_surface(page, shot):
    """Scenario: An administrator is not redirected to the admin surface"""


@pytest.mark.scenario("S-01-04")
@pytest.mark.skip(reason="not yet implemented")
def test_every_seeded_tier_can_sign_in(page, shot):
    """Scenario: Every seeded tier can sign in"""


@pytest.mark.scenario("S-01-05")
@pytest.mark.skip(reason="not yet implemented")
def test_signing_in_with_a_bad_password_is_refused(page, shot):
    """Scenario: Signing in with a bad password is refused"""


@pytest.mark.scenario("S-01-06")
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_session_is_explained_on_the_sign_in_screen(page, shot):
    """Scenario: An expired session is explained on the sign-in screen"""


@pytest.mark.scenario("S-01-07")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_session_link_with_a_non_true_value_shows_no_banner(page, shot):
    """Scenario: An expired-session link with a non-"true" value shows no banner"""


@pytest.mark.scenario("S-01-08")
@pytest.mark.skip(reason="not yet implemented")
def test_self_registration_is_closed_and_redirects_to_sign_in(page, shot):
    """Scenario: Self-registration is closed and redirects to sign-in"""


@pytest.mark.scenario("S-01-09")
@pytest.mark.skip(reason="not yet implemented")
def test_the_bare_root_branches_on_whether_a_token_exists(page, shot):
    """Scenario: The bare root branches on whether a token exists"""


@pytest.mark.scenario("S-01-10")
@pytest.mark.skip(reason="not yet implemented")
def test_an_unauthenticated_cold_load_of_a_protected_screen_is_bounced(page, shot):
    """Scenario: An unauthenticated cold load of a protected screen is bounced"""


@pytest.mark.scenario("S-01-12")
@pytest.mark.skip(reason="not yet implemented")
def test_a_code_challenge_asks_for_six_digits(page, shot):
    """Scenario: A code challenge asks for six digits"""


@pytest.mark.scenario("S-01-13")
@pytest.mark.skip(reason="not yet implemented")
def test_an_email_code_names_the_mailbox_it_went_to(page, shot):
    """Scenario: An email code names the mailbox it went to"""


@pytest.mark.scenario("S-01-14")
@pytest.mark.skip(reason="not yet implemented")
def test_choosing_a_verification_method_offers_both_factors(page, shot):
    """Scenario: Choosing a verification method offers both factors"""


@pytest.mark.scenario("S-01-15")
@pytest.mark.skip(reason="not yet implemented")
def test_the_email_factor_submits_a_different_value_than_its_challenge_name(page, shot):
    """Scenario: The email factor submits a different value than its challenge name"""


@pytest.mark.scenario("S-01-16")
@pytest.mark.skip(reason="not yet implemented")
def test_mfa_setup_is_a_dead_end_that_explains_itself(page, shot):
    """Scenario: MFA setup is a dead end that explains itself"""


@pytest.mark.scenario("S-01-17")
@pytest.mark.skip(reason="not yet implemented")
def test_an_unrecognised_challenge_still_renders_something_usable(page, shot):
    """Scenario: An unrecognised challenge still renders something usable"""


@pytest.mark.scenario("S-01-18")
@pytest.mark.skip(reason="not yet implemented")
def test_a_challenge_can_be_abandoned(page, shot):
    """Scenario: A challenge can be abandoned"""


@pytest.mark.scenario("S-01-19")
@pytest.mark.skip(reason="not yet implemented")
def test_a_challenge_looks_like_the_sign_in_screen_not_a_different_app(page, shot):
    """Scenario: A challenge looks like the sign-in screen, not a different app"""


@pytest.mark.scenario("S-01-20")
@pytest.mark.skip(reason="not yet implemented")
def test_signing_out_clears_the_session(page, shot):
    """Scenario: Signing out clears the session"""

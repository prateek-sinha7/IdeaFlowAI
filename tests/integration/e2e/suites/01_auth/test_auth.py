"""Implements ../../../screens/01-auth.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**These scenarios drive the login form for real.** Everywhere else in the suite
a session is injected once per role via `storage_state` — but a fixture that
hides the thing under test proves nothing, so this module opts out with
`@pytest.mark.anonymous` and types the credentials itself.

The token is only ever asserted as a BOOLEAN. It is a bearer credential, and a
failing assertion would print it into the run's steps.json and the CI log.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import accounts
from framework.locators import auth as L

pytestmark = pytest.mark.anonymous


def has_token(page) -> bool:
    return page.evaluate(f"!!localStorage.getItem('{accounts.AUTH_TOKEN_KEY}')")


def sign_in_form(page, email: str, password: str) -> None:
    page.fill(L.EMAIL, email)
    page.fill(L.PASSWORD, password)
    page.click(L.SIGN_IN)


# ── the sign-in screen ───────────────────────────────────────────────────────


@pytest.mark.scenario("S-01-01")
def test_the_sign_in_screen_renders_for_an_anonymous_visitor(page, shot):
    """Scenario: The sign-in screen renders for an anonymous visitor"""
    with shot("sign-in", 'When I cold-load "/login"'):
        page.goto("/login")
        expect(page.get_by_role("heading", name=L.WELCOME_HEADING)).to_be_visible()

    with shot("form-and-footer", "Then I see the fields, the button and the footer"):
        expect(page.locator(L.EMAIL)).to_be_visible()
        expect(page.locator(L.PASSWORD)).to_be_visible()
        expect(page.locator(L.SIGN_IN)).to_be_visible()
        expect(page.get_by_text(L.INVITE_ONLY_FOOTER)).to_be_visible()

    # The absence is the point: no "forgot password", no "sign up", no SSO. The
    # footer text is the entire account-recovery story, and a link appearing here
    # would be a product change, not a cosmetic one.
    assert page.get_by_role("link", name=re.compile(r"sign ?up|create.*account", re.I)).count() == 0


@pytest.mark.scenario("S-01-02")
def test_signing_in_with_valid_credentials_lands_on_the_dashboard(page, shot):
    """Scenario: Signing in with valid credentials lands on the dashboard"""
    with shot("sign-in-form", 'When I cold-load "/login"'):
        page.goto("/login")
        expect(page.get_by_role("heading", name=L.WELCOME_HEADING)).to_be_visible()

    with shot("credentials-entered", "And I fill the email and password fields"):
        page.fill(L.EMAIL, accounts.ADMIN)
        page.fill(L.PASSWORD, accounts.PASSWORD)

    with shot("dashboard", 'Then the URL becomes "/dashboard"'):
        page.click(L.SIGN_IN)
        # expect() polls until it matches, so this is the wait AND the assertion.
        # No sleep: faster when the app is quick, still correct when it is slow.
        expect(page).to_have_url(re.compile(r"/dashboard"))
        expect(page.get_by_text(L.DASHBOARD_HEADING)).to_be_visible()

    assert has_token(page), "signed in but no auth token was written to localStorage"


@pytest.mark.scenario("S-01-03")
def test_an_administrator_is_not_redirected_to_the_admin_surface(page, shot):
    """Scenario: An administrator is not redirected to the admin surface"""
    with shot("dashboard", "Then an admin lands on /dashboard like everyone else"):
        page.goto("/login")
        sign_in_form(page, accounts.ADMIN, accounts.PASSWORD)
        expect(page).to_have_url(re.compile(r"/dashboard"))

    # The admin surface is reached from the account menu, not from login.
    assert "/admin" not in page.url


@pytest.mark.scenario("S-01-04")
@pytest.mark.parametrize("role", ["admin", "enterprise", "pro", "basic"])
def test_every_seeded_tier_can_sign_in(page, shot, role):
    """Scenario Outline: Every seeded tier can sign in"""
    with shot(f"dashboard-{role}", f'Then "{role}" reaches the dashboard'):
        page.goto("/login")
        sign_in_form(page, accounts.BY_ROLE[role], accounts.PASSWORD)
        expect(page).to_have_url(re.compile(r"/dashboard"))

    assert has_token(page), f"{role} signed in but no auth token was written"


@pytest.mark.scenario("S-01-05")
def test_signing_in_with_a_bad_password_is_refused(page, shot):
    """Scenario: Signing in with a bad password is refused"""
    with shot("bad-password-entered", 'And I fill the password with the wrong value'):
        page.goto("/login")
        page.fill(L.EMAIL, accounts.ADMIN)
        page.fill(L.PASSWORD, "not-the-password")

    with shot("refused", 'Then I remain on "/login" and an error is shown'):
        page.click(L.SIGN_IN)
        # Assert the token is still absent AFTER the attempt has resolved, not
        # merely that the URL has not changed yet — the latter passes while a
        # successful sign-in is still in flight.
        expect(page.locator(L.SIGN_IN)).to_be_enabled()
        expect(page).to_have_url(re.compile(r"/login"))

    assert not has_token(page), "a rejected sign-in wrote an auth token"


# ── the expired-session banner ───────────────────────────────────────────────


@pytest.mark.scenario("S-01-06")
def test_an_expired_session_is_explained_on_the_sign_in_screen(page, shot):
    """Scenario: An expired session is explained on the sign-in screen"""
    with shot("expired-banner", 'When I cold-load "/login?expired=true"'):
        page.goto("/login?expired=true")
        expect(page.get_by_text(L.EXPIRED_BANNER)).to_be_visible()
        expect(page.locator(L.EMAIL)).to_be_visible()
        expect(page.locator(L.PASSWORD)).to_be_visible()


@pytest.mark.scenario("S-01-07")
@pytest.mark.defect
def test_an_expired_session_link_with_a_non_true_value_shows_no_banner(page, shot):
    """Scenario: An expired-session link with a non-"true" value shows no banner"""
    # D-03. The banner is gated on the literal string "true". Any other truthy
    # value renders a plain sign-in screen with no explanation of why the user is
    # here. routes.login({expired:true}) always emits "true", so only a
    # hand-written or external link degrades. Asserted AS-IS: this pins today's
    # wrong behaviour so the fix shows up as a failing test, not a silent change.
    with shot("no-banner", 'When I cold-load "/login?expired=1"'):
        page.goto("/login?expired=1")
        expect(page.get_by_role("heading", name=L.WELCOME_HEADING)).to_be_visible()
        expect(page.get_by_text("Your session expired")).to_have_count(0)


# ── routes around sign-in ────────────────────────────────────────────────────


@pytest.mark.scenario("S-01-08")
def test_self_registration_is_closed_and_redirects_to_sign_in(page, shot):
    """Scenario: Self-registration is closed and redirects to sign-in"""
    with shot("register-redirect", 'When I cold-load "/register"'):
        page.goto("/register")
        expect(page).to_have_url(re.compile(r"/login"))
        expect(page.get_by_role("heading", name=L.WELCOME_HEADING)).to_be_visible()
    # register/page.tsx keeps the route alive rather than 404ing so cached
    # external links land somewhere sensible. It is a stub, not a screen.


@pytest.mark.scenario("S-01-09")
def test_the_bare_root_branches_on_whether_a_token_exists(page, shot, page_as):
    """Scenario Outline: The bare root branches on whether a token exists"""
    with shot("root-signed-out", 'Given signed out, "/" lands on /login'):
        page.goto("/")
        expect(page).to_have_url(re.compile(r"/login"))

    # CORRECTED (C-3). An earlier sweep called this an unconditional redirect to
    # /login and reported it as a routing bug. app/page.tsx is
    # `getToken() ? routes.home() : routes.login()` — the branch is on token
    # PRESENCE only. It renders null while deciding, so wait for the settled
    # URL, never the first paint.
    signed_in = page_as("admin")
    with shot("root-signed-in", 'Given signed in, "/" lands on /dashboard'):
        signed_in.goto("/")
        expect(signed_in).to_have_url(re.compile(r"/dashboard"))


@pytest.mark.issue("ISS-191")
def test_an_authenticated_user_on_plain_login_is_redirected_to_dashboard(page, shot, page_as):
    """ISS-191 — an already-signed-in user landing on plain /login must be
    bounced to /dashboard, not shown the sign-in form."""
    signed_in = page_as("admin")
    with shot("plain-login-redirected", 'Given signed in, "/login" lands on /dashboard'):
        signed_in.goto("/login")
        expect(signed_in).to_have_url(re.compile(r"/dashboard"))


@pytest.mark.issue("ISS-191")
def test_an_authenticated_user_on_expired_login_is_redirected_to_dashboard(page, shot, page_as):
    """ISS-191 — an already-signed-in user landing on /login?expired=true must
    be bounced to /dashboard, not shown the stale "session expired" form."""
    signed_in = page_as("admin")
    with shot("expired-login-redirected", 'Given signed in, "/login?expired=true" lands on /dashboard'):
        signed_in.goto("/login?expired=true")
        expect(signed_in).to_have_url(re.compile(r"/dashboard"))


@pytest.mark.scenario("S-01-10")
def test_an_unauthenticated_cold_load_of_a_protected_screen_is_bounced(page, shot):
    """Scenario: An unauthenticated cold load of a protected screen is bounced"""
    with shot("bounced-to-login", 'When I cold-load "/dashboard" with no token'):
        page.goto("/dashboard")
        expect(page).to_have_url(re.compile(r"/login"))
        expect(page.get_by_text(L.DASHBOARD_HEADING)).to_have_count(0)


# ── Cognito challenges ───────────────────────────────────────────────────────
#
# All nine need an account parked in a specific Cognito challenge state. The
# seed script provisions four ordinary accounts and no challenged ones, and a
# challenge cannot be induced from the UI — NEW_PASSWORD_REQUIRED needs an admin
# reset with permanent=false, the MFA ones need enrolment against a real pool.
#
# They are the reason `09-settings` matters: /settings/security is where email
# MFA is enabled, which is what would produce an EMAIL_OTP challenge to test.
#
# Unskip these by seeding challenged accounts, not by mocking the challenge —
# the traps these scenarios pin (EMAIL_MFA vs EMAIL_OTP, the 501 on MFA_SETUP)
# live in Cognito's own behaviour and a mock would assert our idea of it.

_CHALLENGE_BLOCKER = "fixture: no account parked in a Cognito challenge state"


@pytest.mark.scenario("S-01-11")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_first_sign_in_demands_a_permanent_password(page, shot):
    """Scenario: First sign-in demands a permanent password"""


@pytest.mark.scenario("S-01-12")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_a_code_challenge_asks_for_six_digits(page, shot):
    """Scenario Outline: A code challenge asks for six digits"""


@pytest.mark.scenario("S-01-13")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_an_email_code_names_the_mailbox_it_went_to(page, shot):
    """Scenario: An email code names the mailbox it went to"""


@pytest.mark.scenario("S-01-14")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_choosing_a_verification_method_offers_both_factors(page, shot):
    """Scenario: Choosing a verification method offers both factors"""


@pytest.mark.scenario("S-01-15")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_the_email_factor_submits_a_different_value_than_its_challenge_name(page, shot):
    """Scenario: The email factor submits a different value than its challenge name"""


@pytest.mark.scenario("S-01-16")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_mfa_setup_is_a_dead_end_that_explains_itself(page, shot):
    """Scenario: MFA setup is a dead end that explains itself"""


@pytest.mark.scenario("S-01-17")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_an_unrecognised_challenge_still_renders_something_usable(page, shot):
    """Scenario: An unrecognised challenge still renders something usable"""


@pytest.mark.scenario("S-01-18")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_a_challenge_can_be_abandoned(page, shot):
    """Scenario: A challenge can be abandoned"""


@pytest.mark.scenario("S-01-19")
@pytest.mark.skip(reason=_CHALLENGE_BLOCKER)
def test_a_challenge_looks_like_the_sign_in_screen_not_a_different_app(page, shot):
    """Scenario: A challenge looks like the sign-in screen, not a different app"""


# ── signing out ──────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-01-20")
def test_signing_out_clears_the_session(page, shot):
    """Scenario: Signing out clears the session"""
    with shot("signed-in", "Given I am signed in"):
        page.goto("/login")
        sign_in_form(page, accounts.ADMIN, accounts.PASSWORD)
        expect(page).to_have_url(re.compile(r"/dashboard"))
    assert has_token(page)

    with shot("account-menu", "When I open the account menu"):
        page.click(L.ACCOUNT_MENU)
        expect(page.locator(L.LOG_OUT)).to_be_visible()

    with shot("signed-out", 'Then I end up on the sign-in screen'):
        page.click(L.LOG_OUT)
        expect(page).to_have_url(re.compile(r"/login"))

    assert not has_token(page), "logged out but the auth token survived in localStorage"


# ── ISS-245: duplicate submissions from rapid repeated clicks ───────────────


@pytest.mark.issue("ISS-245")
def test_rapid_repeated_clicks_on_sign_in_fire_only_one_login_request(page, shot):
    """ISS-245 — the Sign in button must gate synchronous rapid clicks so only
    one POST /api/auth/login is sent per submit attempt."""
    with shot("sign-in-form", 'When I cold-load "/login"'):
        page.goto("/login")
        page.fill(L.EMAIL, accounts.ADMIN)
        page.fill(L.PASSWORD, accounts.PASSWORD)

    login_requests = []
    page.on("request", lambda req: login_requests.append(req)
             if req.method == "POST" and "/auth/login" in req.url else None)

    with shot("rapid-triple-click", "When I click Sign in three times synchronously"):
        page.eval_on_selector(
            L.SIGN_IN,
            "btn => { btn.click(); btn.click(); btn.click(); }",
        )
        expect(page).to_have_url(re.compile(r"/dashboard"))

    assert len(login_requests) == 1, (
        f"expected exactly 1 POST /api/auth/login from a rapid triple-click, "
        f"got {len(login_requests)}"
    )

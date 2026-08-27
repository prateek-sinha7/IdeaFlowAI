"""Implements ../../../screens/11-admin.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**The self-action guards are asserted at the API, not only by the absence of a
UI control.** FIX-310's whole shape was a missing server-side check while its
siblings had one — a test that only looked for a hidden button would have passed
throughout.

**Nothing here mutates the four seeded accounts.** They are the fixtures every
other feature file depends on; the destructive scenarios create and delete their
own users.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import accounts, api
from framework.locators import admin as L
from framework.locators import auth as AUTH
from framework.locators import shell as SHELL


def open_admin(page) -> None:
    page.goto("/admin")
    expect(page.get_by_text(L.HEADING)).to_be_visible()
    expect(page.locator(L.row(accounts.ADMIN))).to_be_visible()


def tile(page, label: str) -> int:
    """The figure under a stat tile's caption."""
    lines = [
        line.strip()
        for line in page.evaluate("() => document.body.innerText").splitlines()
        if line.strip()
    ]
    assert label in lines, f"the {label} tile is not on screen"
    value = lines[lines.index(label) + 1]
    m = re.match(r"^([\d,]+)", value)
    assert m, f"the {label} tile shows {value!r}, not a number"
    return int(m.group(1).replace(",", ""))


# ── the shell ────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-11-01")
def test_the_admin_dashboard_renders_its_own_shell(page, shot):
    """Scenario: The admin dashboard renders its own shell"""
    with shot("admin", 'When I cold-load "/admin"'):
        open_admin(page)

    expect(page.get_by_text(L.SUBTITLE)).to_be_visible()
    expect(page.locator(L.BACK_TO_APP)).to_be_visible()
    expect(page.locator(L.LOGOUT)).to_be_visible()

    # /admin bypasses the catch-all and renders its own chrome. The main nav and
    # account menu must be ABSENT — their presence would mean the admin surface
    # had been folded into the shared shell, which is a routing change.
    for item in SHELL.NAV_ITEMS:
        expect(SHELL.nav(page, item)).to_have_count(0)
    expect(page.locator(AUTH.ACCOUNT_MENU)).to_have_count(0)


@pytest.mark.scenario("S-11-02")
def test_the_stat_tiles_agree_with_the_table(page, shot):
    """Scenario: The stat tiles agree with the table"""
    with shot("tiles", "Then the tiles agree with the rows"):
        open_admin(page)

    total = tile(page, "TOTAL USERS")
    rows = page.locator("tbody tr").count()
    assert total == rows, f"TOTAL USERS says {total} but the table has {rows} rows"

    by_tier = sum(tile(page, t) for t in ("BASIC", "PRO", "ENTERPRISE"))
    # A user on the fourth tier — `hexaware` — would break this, which is
    # exactly what makes it worth asserting: D-16 records that tier as one the
    # UI's three-way split does not account for.
    assert by_tier == total, (
        f"BASIC+PRO+ENTERPRISE = {by_tier} but TOTAL USERS = {total}. "
        "A user on a tier the tiles do not count (e.g. hexaware) would do this."
    )

    admins = tile(page, "ADMINS")
    admin_rows = page.locator('tbody tr:has-text("ADMIN")').count()
    assert admins == admin_rows, f"ADMINS says {admins}, {admin_rows} rows show the role"


@pytest.mark.scenario("S-11-03")
def test_every_user_row_carries_its_full_record(page, shot):
    """Scenario: Every user row carries its full record"""
    with shot("rows", "Then each row shows its full record"):
        open_admin(page)

    for email in accounts.BY_ROLE.values():
        text = page.locator(L.row(email)).inner_text()
        assert email in text
        assert re.search(r"BASIC|PRO|ENTERPRISE|HEXAWARE", text), f"{email} row has no plan badge"
        assert re.search(r"\d", text), f"{email} row shows no run count or date"


# ── the self-action guards ───────────────────────────────────────────────────


@pytest.mark.scenario("S-11-04")
def test_an_admin_cannot_delete_their_own_account(page, shot):
    """Scenario: An admin cannot delete their own account"""
    with shot("no-self-delete", "Then no delete control exists for my own row"):
        open_admin(page)
        expect(page.locator(L.delete_user(accounts.ADMIN))).to_have_count(0)

    # The control's absence proves the UI. The API is the boundary that matters:
    # FIX-310 was a missing server-side check while the siblings had one.
    res = api.request(page, "DELETE", f"/api/admin/users/{_own_id(page)}")
    assert res["status"] in (400, 403, 409, 422), (
        f"the API allowed an admin to delete their own account — got {res['status']}"
    )

    # And for every other user the control IS offered.
    for email in (accounts.ENTERPRISE, accounts.PRO, accounts.BASIC):
        expect(page.locator(L.delete_user(email))).to_have_count(1)


def _own_id(page) -> str:
    """The signed-in admin's user id, read from the API rather than the table.

    The table truncates ids for display, and a truncated id in a DELETE would
    404 for the wrong reason — making a self-delete guard look enforced when it
    was never actually reached.
    """
    me = api.request(page, "GET", "/api/auth/me")
    m = re.search(r'"id"\s*:\s*"([^"]+)"', me["body"])
    assert m, f"could not read my own user id: {me['body'][:120]}"
    return m.group(1)


@pytest.mark.scenario("S-11-05")
def test_an_admin_cannot_change_their_own_tier(page, shot):
    """Scenario: An admin cannot change their own tier"""
    with shot("own-row", "When I attempt to change my own plan"):
        open_admin(page)

    before = page.locator(L.row(accounts.ADMIN)).inner_text()
    res = api.request(
        page, "PATCH", f"/api/admin/users/{_own_id(page)}/tier", {"tier": "basic"}
    )
    assert res["status"] in (400, 403, 409, 422), (
        f"an admin changed their own tier — got {res['status']}"
    )

    with shot("unchanged", "Then my tier is unchanged after a reload"):
        page.reload()
        expect(page.locator(L.row(accounts.ADMIN))).to_be_visible()

    assert "ENTERPRISE" in page.locator(L.row(accounts.ADMIN)).inner_text(), (
        f"the admin's tier changed despite the refusal (was {before!r})"
    )


@pytest.mark.scenario("S-11-06")
def test_an_admin_cannot_demote_themselves(page, shot):
    """Scenario: An admin cannot demote themselves"""
    with shot("own-role", "When I attempt to remove my own ADMIN role"):
        open_admin(page)

    res = api.request(
        page, "PATCH", f"/api/admin/users/{_own_id(page)}/role", {"is_admin": False}
    )
    assert res["status"] in (400, 403, 409, 422), (
        f"an admin demoted themselves — got {res['status']}. "
        "That is a lockout: the last admin could remove every route back in."
    )


# ── authorization ────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-11-07")
@pytest.mark.parametrize("role", ["enterprise", "pro", "basic"])
def test_a_non_admin_cannot_reach_the_admin_dashboard(page_as, shot, role):
    """Scenario Outline: A non-admin cannot reach the admin dashboard"""
    page = page_as(role)
    page.goto("/admin")
    expect(page.get_by_text(L.HEADING)).to_have_count(0)

    # The sharper half: not merely that the heading is missing, but that no
    # other user's email is on screen. A partially-rendered admin table that
    # simply lacks its title would still be a disclosure.
    body = page.evaluate("() => document.body.innerText")
    for email in accounts.BY_ROLE.values():
        if email == accounts.BY_ROLE[role]:
            continue
        assert email not in body, f"a {role} account can see {email} on /admin"


@pytest.mark.scenario("S-11-08")
@pytest.mark.anonymous
def test_an_anonymous_visitor_cannot_reach_the_admin_dashboard(page, shot):
    """Scenario: An anonymous visitor cannot reach the admin dashboard"""
    with shot("bounced", 'When I cold-load "/admin" with no token'):
        page.goto("/admin")
        expect(page.get_by_role("heading", name=AUTH.WELCOME_HEADING)).to_be_visible()

    expect(page.locator("tbody tr")).to_have_count(0)


@pytest.mark.scenario("S-11-09")
def test_the_admin_api_refuses_a_non_admin_directly(page_as, shot):
    """Scenario: The admin API refuses a non-admin directly"""
    # The UI guard is presentation. This is the one that matters — the endpoint
    # is reachable by anyone holding any valid token.
    page = page_as("basic")
    page.goto("/dashboard")
    res = api.request(page, "GET", "/api/admin/users")
    assert res["status"] == 403, (
        f"a basic account reached the admin users endpoint — got {res['status']}"
    )


# ── the table ────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-11-10")
def test_search_filters_the_users_table(page, shot):
    """Scenario: Search filters the users table"""
    open_admin(page)
    everyone = page.locator("tbody tr").count()

    with shot("filtered", 'When I type "qa-pro" into the user search'):
        page.fill(L.SEARCH, "qa-pro")
        expect(page.locator("tbody tr")).to_have_count(1)

    expect(page.locator(L.row(accounts.PRO))).to_be_visible()

    with shot("cleared", "When I clear the search then all rows return"):
        page.fill(L.SEARCH, "")
        expect(page.locator("tbody tr")).to_have_count(everyone)


# ── the way in and out ───────────────────────────────────────────────────────


@pytest.mark.scenario("S-11-11")
def test_the_account_menu_is_the_way_in(page, shot):
    """Scenario: The account menu is the way in"""
    page.goto("/dashboard")

    with shot("account-menu", "When I open the account menu"):
        page.click(AUTH.ACCOUNT_MENU)
        expect(page.get_by_text(L.HEADING)).to_be_visible()

    with shot("admin", 'When I click it then I land on "/admin"'):
        page.click(f'button:has-text("{L.HEADING}")')
        expect(page).to_have_url(re.compile(r"/admin"))


@pytest.mark.scenario("S-11-12")
@pytest.mark.role("pro")
def test_a_non_admin_is_not_offered_the_entry_point(page, shot):
    """Scenario: A non-admin is not offered the entry point"""
    page.goto("/dashboard")

    with shot("no-admin-entry", "Then the account menu does not offer Admin Dashboard"):
        page.click(AUTH.ACCOUNT_MENU)
        expect(page.locator(AUTH.LOG_OUT)).to_be_visible()
        expect(page.get_by_text(L.HEADING)).to_have_count(0)


@pytest.mark.scenario("S-11-13")
def test_back_to_app_returns_to_the_main_shell(page, shot):
    """Scenario: Back to app returns to the main shell"""
    open_admin(page)

    with shot("back-to-app", 'When I click "← Back to app"'):
        page.click(L.BACK_TO_APP)
        # The main shell is back: its nav is the thing /admin deliberately
        # lacks. Waited on rather than read — the route changes before the
        # shell has mounted, so an immediate check finds neither.
        expect(SHELL.nav(page, "Library")).to_be_visible(timeout=20_000)

    expect(page).not_to_have_url(re.compile(r"/admin"))


@pytest.mark.scenario("S-11-14")
@pytest.mark.anonymous
def test_logout_from_the_admin_shell_clears_the_session(page, shot):
    """Scenario: Logout from the admin shell clears the session"""
    # `anonymous`, and signs in for itself. Logging out REVOKES THE TOKEN
    # SERVER-SIDE, so running this against the shared per-role session would
    # invalidate the `storage_state` every other admin test replays — they then
    # bounce to /login?expired=true and fail for a reason that has nothing to do
    # with what they assert. Any test that ends a session must own that session.
    with shot("signed-in", "Given I am signed in as an admin"):
        page.goto("/login")
        page.fill(AUTH.EMAIL, accounts.ADMIN)
        page.fill(AUTH.PASSWORD, accounts.PASSWORD)
        page.click(AUTH.SIGN_IN)
        expect(page).to_have_url(re.compile(r"/dashboard"))

    open_admin(page)

    with shot("logged-out", 'When I click "Logout"'):
        page.click(L.LOGOUT)
        expect(page).to_have_url(re.compile(r"/login"))

    assert not page.evaluate(
        f"!!localStorage.getItem('{accounts.AUTH_TOKEN_KEY}')"
    ), "logging out of the admin shell left the auth token behind"


# ── user lifecycle ───────────────────────────────────────────────────────────
#
# These create and delete their OWN users. Never the four seeded accounts —
# they are the fixtures every other feature file depends on.


@pytest.mark.scenario("S-11-15")
@pytest.mark.destructive
@pytest.mark.skip(reason="destructive: creates a real account; needs a disposable-user fixture")
def test_adding_a_user_creates_an_account_at_the_chosen_tier(page, shot):
    """Scenario: Adding a user creates an account at the chosen tier"""
    # Creating a user provisions it in Cognito, which the suite cannot then
    # reliably tear down — a failed delete leaves a real account behind in a
    # shared pool. Needs a disposable-user fixture with guaranteed cleanup.


@pytest.mark.scenario("S-11-16")
@pytest.mark.destructive
@pytest.mark.skip(reason="destructive: depends on the disposable user S-11-15 would create")
def test_deleting_a_user_removes_them(page, shot):
    """Scenario: Deleting a user removes them"""


@pytest.mark.scenario("S-11-17")
@pytest.mark.destructive
@pytest.mark.skip(reason="destructive: would revoke a seeded account's sessions mid-run")
def test_an_admin_resets_another_users_password_to_a_temporary_one(page, shot):
    """Scenario: An admin resets another user's password to a temporary one"""
    # A reset revokes that user's existing sessions — including the
    # storage_state this suite injects for that role, which would fail every
    # other test using it. Needs a disposable user.


@pytest.mark.scenario("S-11-18")
@pytest.mark.destructive
@pytest.mark.skip(reason="destructive: would change a seeded account's password")
def test_a_permanent_reset_skips_the_challenge_but_is_knowable(page, shot):
    """Scenario: A permanent reset skips the challenge but is knowable"""


@pytest.mark.scenario("S-11-19")
def test_admin_reset_is_the_only_recovery_path_under_email_mfa(page, shot):
    """Scenario: Admin reset is the only recovery path under email MFA"""
    # AWS disqualifies email as a recovery channel whenever it is also a second
    # factor, so /api/auth/forgot-password refuses. That refusal is WHY admin
    # reset exists, and asserting it keeps the two specs describing one
    # mechanism rather than drifting apart.
    with shot("dashboard", "Given the pool uses email as a second factor"):
        page.goto("/dashboard")
        expect(page.get_by_text("What would you like to build today?")).to_be_visible()

    # Conditional on the pool, because the refusal IS conditional on the pool.
    # This dev pool reports {"supported": false} — no MFA at all — and there
    # forgot-password correctly answers 202. Asserting an unconditional refusal
    # would fail against correct behaviour and teach the next reader that the
    # endpoint is broken.
    mfa = api.request(page, "GET", "/api/auth/mfa")
    email_mfa_on = '"email_available":true' in mfa["body"] and '"enabled":true' in mfa["body"]

    res = api.request(page, "POST", "/api/auth/forgot-password", {"email": accounts.BASIC})

    if email_mfa_on:
        assert res["status"] >= 400, (
            f"email is a second factor on this pool, so AWS disqualifies it as a "
            f"recovery channel — forgot-password should refuse, got {res['status']}"
        )
    else:
        # The other half of the same contract: with MFA off there IS a self-serve
        # path, and it answers 202 Accepted rather than confirming whether the
        # address exists.
        assert res["status"] == 202, (
            f"with MFA off, forgot-password should answer 202 Accepted — got {res['status']}"
        )
        pytest.skip(
            "this pool reports MFA unsupported, so the admin-reset-only path "
            "cannot be exercised here; the 202 branch was asserted instead"
        )


@pytest.mark.scenario("S-11-20")
@pytest.mark.destructive
@pytest.mark.skip(reason="destructive: changing a seeded tier breaks the entitlement fixtures")
def test_changing_another_users_tier_takes_effect(page, shot):
    """Scenario: Changing another user's tier takes effect"""
    # The four seeded tiers are what 02-home-catalog's entitlement matrix is
    # asserted against. Moving one would break those tests rather than this one.

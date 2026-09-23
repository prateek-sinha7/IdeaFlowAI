"""Implements ../../../screens/17-theme-and-tiers.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Every theme test restores the theme it found.** It is persisted per browser
profile, so a test that leaves dark mode on changes every screenshot taken after
it in the same run.

**The tier lattice is not a chain.** `hexaware` gains prototype over basic and
loses ppt, so nothing here is written as "higher tier ⇒ superset" — an
assertion in that shape passes vacuously against basic/pro/enterprise and is
wrong about the one tier that matters (D-16).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import accounts, api, settings
from framework.locators import admin as ADMIN
from framework.locators import run_history as RH
from framework.locators import settings_page as SET
from framework.locators import shell as SHELL
from framework.locators import theme as L


def open_menu(page) -> None:
    page.click(SHELL.ACCOUNT_MENU)
    expect(page.locator(SHELL.MENU)).to_be_visible()


def close_menu(page) -> None:
    page.keyboard.press("Escape")
    expect(page.locator(SHELL.MENU)).to_have_count(0)


# ── theme ────────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-17-01")
def test_dark_mode_applies_and_persists(page, shot):
    """Scenario: Dark mode applies and persists"""
    page.goto("/dashboard")
    expect(SHELL.nav(page, "Home")).to_be_visible()
    original = L.read(page)

    try:
        with shot("dark-mode", 'When I click "Dark mode"'):
            L.set_theme(page, "dark", open_menu, SHELL.menu_item)

        assert L.read(page) == "dark"
        assert page.evaluate(L.BODY_BG) == L.BACKGROUNDS["dark"], (
            f"data-theme says dark but the body is {page.evaluate(L.BODY_BG)}"
        )

        with shot("dark-after-reload", "When I reload the page"):
            page.reload()
            expect(SHELL.nav(page, "Home")).to_be_visible()

        assert L.read(page) == "dark"
    finally:
        L.set_theme(page, original, open_menu, SHELL.menu_item)


@pytest.mark.scenario("S-17-02")
def test_the_theme_control_names_the_target_not_the_state(page, shot):
    """Scenario: The theme control names the target, not the state"""
    page.goto("/dashboard")
    expect(SHELL.nav(page, "Home")).to_be_visible()
    original = L.read(page)

    try:
        L.set_theme(page, "dark", open_menu, SHELL.menu_item)

        with shot("dark-menu-label", "When I open the account menu in dark mode"):
            open_menu(page)

        # Still "Dark mode" — it is not a state label, which is why every other
        # test here reads data-theme instead.
        expect(SHELL.menu_item(page, "Dark mode")).to_be_visible()
        assert L.read(page) == "dark"
        close_menu(page)
    finally:
        L.set_theme(page, original, open_menu, SHELL.menu_item)


@pytest.mark.scenario("S-17-03")
@pytest.mark.parametrize(
    ("theme", "route"),
    [
        ("dark", "/dashboard"),
        ("dark", "/runs"),
        ("dark", "/workflows/ppt/canvas"),
        ("dark", "/library"),
        ("light", "/dashboard"),
    ],
)
def test_every_major_surface_renders_in_both_themes(page, shot, theme, route):
    """Scenario: Every major surface renders in both themes

    `/runs` stands in for the spec's `/runs/{id}/steps`: a run id is not stable
    across databases, and the palette question is about the surface, not about
    one run.
    """
    page.goto("/dashboard")
    expect(SHELL.nav(page, "Home")).to_be_visible()
    original = L.read(page)

    try:
        L.set_theme(page, theme, open_menu, SHELL.menu_item)

        with shot(f"{theme}{route.replace('/', '-')}", f'When I cold-load "{route}" in {theme}'):
            page.goto(route)
            page.wait_for_load_state("load")
            page.wait_for_timeout(settings.SETTLE_MS)

        assert L.read(page) == theme, "the theme did not survive the navigation"
        assert page.evaluate(L.BODY_BG) == L.BACKGROUNDS[theme]

        unreadable = L.unreadable_text(page)
        assert not unreadable, (
            f"{route} in {theme} renders text the same colour as its own "
            f"background: {unreadable}"
        )
    finally:
        page.goto("/dashboard")
        expect(SHELL.nav(page, "Home")).to_be_visible()
        L.set_theme(page, original, open_menu, SHELL.menu_item)


@pytest.mark.scenario("S-17-04")
@pytest.mark.anonymous
def test_theme_is_a_per_browser_preference_not_per_account(page, shot):
    """Scenario: Theme is a per-browser preference, not per-account

    `anonymous` and signs in for itself twice: the point is that ONE browser
    profile carries the preference across two accounts, which a shared
    storage_state cannot demonstrate.
    """
    from framework.locators import auth as AUTH

    def sign_in(email: str) -> None:
        page.goto("/login")
        page.fill(AUTH.EMAIL, email)
        page.fill(AUTH.PASSWORD, accounts.PASSWORD)
        page.click(AUTH.SIGN_IN)
        page.wait_for_url("**/dashboard", timeout=settings.LOGIN_TIMEOUT_MS)
        expect(SHELL.nav(page, "Home")).to_be_visible()

    sign_in(accounts.ADMIN)
    original = L.read(page)

    try:
        with shot("dark-as-admin", "Given I set dark mode as one user"):
            L.set_theme(page, "dark", open_menu, SHELL.menu_item)

        with shot("signed-out", "When I sign out"):
            open_menu(page)
            page.locator(SHELL.LOG_OUT).click()
            page.wait_for_url("**/login**", timeout=settings.LOGIN_TIMEOUT_MS)

        with shot("dark-as-other-user", "And I sign in as a different user"):
            sign_in(accounts.PRO)

        assert L.read(page) == "dark", "the theme did not survive the account change"
    finally:
        L.set_theme(page, original, open_menu, SHELL.menu_item)


# ── tier and role gating ─────────────────────────────────────────────────────


@pytest.mark.scenario("S-17-05")
@pytest.mark.parametrize(
    ("role", "count", "admin_entry"),
    [("admin", 6, True), ("enterprise", 5, False), ("pro", 5, False), ("basic", 5, False)],
)
def test_the_account_menu_reflects_the_role_not_the_tier(page_as, shot, role, count, admin_entry):
    """Scenario: The account menu reflects the role, not the tier

    qa-enterprise is the control: the same entitlements as qa-admin, no admin
    flag. It is what proves the gate is on `is_admin` and not on the tier.
    """
    page = page_as(role)
    page.goto("/dashboard")
    expect(SHELL.nav(page, "Home")).to_be_visible()

    with shot(f"menu-{role}", f"When I open the account menu as {role}"):
        open_menu(page)

    assert page.locator('[role="menuitem"]').count() == count
    expect(SHELL.menu_item(page, SHELL.ADMIN_MENU_ITEM)).to_have_count(1 if admin_entry else 0)


@pytest.mark.scenario("S-17-06")
@pytest.mark.parametrize("role", ["enterprise", "pro", "basic"])
def test_a_non_admin_is_redirected_away_from_the_admin_surface(page_as, shot, role):
    """Scenario: A non-admin is redirected away from the admin surface"""
    page = page_as(role)

    with shot(f"admin-blocked-{role}", f'When I cold-load "/admin" as {role}'):
        page.goto("/admin")
        page.wait_for_url("**/dashboard", timeout=settings.LOGIN_TIMEOUT_MS)
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.url.endswith("/dashboard")
    body = page.evaluate("() => document.body.innerText")
    # Not one other seeded address may appear — a redirect that still painted
    # the user table for a frame would have leaked it.
    for email in accounts.BY_ROLE.values():
        if email != accounts.BY_ROLE[role]:
            assert email not in body, f"{role} can see {email} on /dashboard"
    expect(page.get_by_text(ADMIN.HEADING)).to_have_count(0)


@pytest.mark.scenario("S-17-07")
@pytest.mark.parametrize(
    ("role", "plan", "includes"),
    [("basic", "Basic", "Product Requirements"), ("enterprise", "Enterprise", "Custom Workflow")],
)
def test_deliverable_access_matches_the_tier(page_as, shot, role, plan, includes):
    """Scenario: Deliverable access matches the tier"""
    page = page_as(role)

    with shot(f"usage-{role}", f'When I cold-load "/settings/usage" as {role}'):
        page.goto("/settings/usage")
        expect(page.get_by_text(SET.DELIVERABLE_ACCESS)).to_be_visible()

    expect(page.get_by_text(f"{plan} plan")).to_be_visible()
    expect(page.get_by_text(includes, exact=True)).to_be_visible()


@pytest.mark.scenario("S-17-08")
@pytest.mark.defect
@pytest.mark.role("enterprise")
def test_deliverable_access_omits_workflows_the_catalog_offers(page, shot):
    """Scenario: Deliverable Access omits workflows the catalog offers

    Asserts TODAY'S behaviour — D-04. The catalogue offers "Branch by Language"
    to an enterprise user and Deliverable Access does not mention it, so the two
    surfaces disagree about what the plan includes.
    """
    with shot("catalog-offers", 'When I cold-load "/dashboard" as enterprise'):
        page.goto("/dashboard")
        expect(page.get_by_text("Branch by Language")).to_be_visible()

    with shot("usage-omits", 'When I cold-load "/settings/usage"'):
        page.goto("/settings/usage")
        expect(page.get_by_text(SET.DELIVERABLE_ACCESS)).to_be_visible()

    assert "Branch by Language" not in page.evaluate("() => document.body.innerText"), (
        "Deliverable Access now lists it — D-04's two surfaces agree. Re-read "
        "the defect before changing this test."
    )


@pytest.mark.scenario("S-17-09")
@pytest.mark.destructive
def test_a_hexaware_user_gains_prototype_and_loses_presentations(browser, shot, disposable_user, pytestconfig):
    """Scenario: A hexaware user gains prototype and loses presentations

    **The case that breaks every other scenario in this file.** `hexaware` sits
    sideways in the lattice: it gains `prototype` over basic and LOSES `ppt`,
    and `UPGRADE_PATH` sends it straight to enterprise, skipping pro. Moving a
    user from basic to hexaware therefore takes away their ability to make
    presentations.

    An assertion shaped "higher tier implies superset" passes vacuously against
    basic, pro and enterprise and is wrong about exactly this one — which is
    D-16, and why the account is created here rather than the scenario being
    skipped for want of a seeded one.

    The user is created through the admin API and deleted in the fixture's
    teardown. Never `is_admin=True` — see D-31.
    """
    from framework.locators import auth as AUTH
    from framework.locators import home_catalog as HOME

    user = disposable_user(tier="hexaware")
    context = browser.new_context(
        base_url=settings.BASE_URL,
        viewport=settings.VIEWPORT,
        device_scale_factor=pytestconfig.getoption("--dpi"),
        reduced_motion="reduce",
    )
    page = context.new_page()

    try:
        with shot("hexaware-signs-in", 'Given a user on the "hexaware" tier'):
            page.goto("/login")
            page.fill(AUTH.EMAIL, user["email"])
            page.fill(AUTH.PASSWORD, user["password"])
            page.click(AUTH.SIGN_IN)
            page.wait_for_url("**/dashboard", timeout=settings.LOGIN_TIMEOUT_MS)
            expect(page.get_by_text(HOME.HEADING)).to_be_visible()
            page.wait_for_timeout(settings.SETTLE_MS)

        prototype = page.locator(HOME.card("Build an interactive prototype"))
        presentation = page.locator(HOME.card("Pitch an idea"))
        expect(prototype).to_be_visible()
        expect(presentation).to_be_visible()

        with shot("hexaware-entitlements", "Then prototype is launchable and ppt is locked"):
            prototype_locked = "Requires" in prototype.inner_text()
            presentation_locked = "Requires" in presentation.inner_text()

        assert not prototype_locked, (
            "a hexaware user cannot launch a prototype — the tier gained nothing "
            "over basic, which is not what entitlements.py says"
        )
        assert presentation_locked, (
            "a hexaware user CAN launch a presentation. The lattice is a chain "
            "again, and every 'higher tier implies superset' assumption in this "
            "suite is now safe — re-read D-16 before believing that."
        )

        with shot("hexaware-usage", 'When I cold-load "/settings/usage"'):
            page.goto("/settings/usage")
            expect(page.get_by_text(SET.DELIVERABLE_ACCESS)).to_be_visible()

        access = page.evaluate("() => document.body.innerText")
        assert "Interactive Prototype" in access, (
            "Deliverable Access does not list the prototype the catalogue offers"
        )
        assert "Presentation" not in access.split(SET.DELIVERABLE_ACCESS, 1)[1], (
            "Deliverable Access lists Presentation for a hexaware plan"
        )
    finally:
        context.close()


@pytest.mark.scenario("S-17-10")
def test_the_admin_dialog_offers_every_tier_the_backend_knows(page, shot):
    """Scenario: The admin dialog offers every tier the backend knows

    Guards the two `TIER_PIPELINES` maps and this select against drifting apart.
    `test_entitlement_parity` already keeps the backend and frontend maps in
    sync; nothing else keeps the admin UI in sync with either.
    """
    page.goto("/admin")
    expect(page.get_by_text(ADMIN.HEADING)).to_be_visible()

    with shot("add-user", 'When I open "Add user" on "/admin"'):
        page.click(ADMIN.ADD_USER)
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    options = page.locator("select option").evaluate_all(
        "opts => opts.map(o => (o.value + ' ' + o.text).toLowerCase())"
    )
    for tier in L.TIERS:
        assert any(tier in text for text in options), (
            f"the plan select does not offer {tier!r}: {options}"
        )


@pytest.mark.scenario("S-17-11")
@pytest.mark.role("basic")
def test_entitlement_is_enforced_by_the_backend_not_only_the_badge(page, shot):
    """Scenario: Entitlement is enforced by the backend, not only the badge

    ISS-055 recorded a period where launch never checked entitlement at all and
    any user could run any pipeline. The badge is presentation; this is the
    control.

    The request goes to `settings.API_URL` absolutely. A relative `/api/runs`
    reaches Next.js on :3000 and answers 200 with a page — which reads as "a
    basic account was allowed to launch a pipeline it does not hold".
    """
    with shot("entitlement-refused", "When I request a launch my tier does not cover"):
        page.goto("/dashboard")
        result = api.request(
            page,
            "POST",
            "/api/runs",
            {"pipeline_type": "app_builder", "message": "hello"},
        )

    assert result["status"] in (402, 403), (
        f"a basic account's app_builder launch answered {result['status']}: "
        f"{result['body'][:200]!r}"
    )


@pytest.mark.scenario("S-17-12")
@pytest.mark.role("basic")
def test_one_users_runs_are_invisible_to_another(page, shot, page_as):
    """Scenario: One user's runs are invisible to another"""
    owner = page_as("admin")
    owner.goto("/runs")
    expect(owner.locator(RH.ROW).first).to_be_visible()
    theirs = set(RH.rows(owner))
    owner.locator(RH.ROW).first.click()
    owner.wait_for_url(lambda url: "/runs/" in url)
    stolen = owner.url

    with shot("foreign-runs-hidden", 'When I cold-load "/runs" as another user'):
        page.goto("/runs")
        expect(page.get_by_role("heading", name=RH.HEADING)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    mine = set(RH.rows(page))
    assert not (mine & theirs), f"another user's runs are listed: {sorted(mine & theirs)[:2]}"

    with shot("foreign-run-url", "And opening one of their run URLs directly"):
        page.goto(stolen.replace(settings.BASE_URL, ""))
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    assert "Page not found." in body or "forbidden" in body.lower(), (
        f"another user's run rendered its contents: {body[:200]!r}"
    )

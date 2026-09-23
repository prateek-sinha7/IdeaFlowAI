"""Implements ../../../screens/12-shell-nav.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Two rules this file exists to protect:

**Nav items are buttons.** There is not one `<a href>` in the header, so a test
that enumerates navigation by anchor finds an empty list and passes without
asserting anything. S-12-03 pins that.

**Account-menu items are located by role, never by text.** A plain text click on
a `[role="menuitem"]` fails intermittently here — Analytics most often — and the
route is never derivable from the label (`/history` does not exist; Run History
is `/runs`).
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import nav as NAV
from framework import settings
from framework.locators import auth as AUTH
from framework.locators import shell as L


def open_menu(page) -> None:
    page.click(L.ACCOUNT_MENU)
    expect(page.locator(L.MENU)).to_be_visible()


# ── the header ───────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-12-01")
def test_the_header_is_present_on_every_authenticated_screen(page, shot):
    """Scenario: The header is present on every authenticated screen"""
    with shot("header", 'When I cold-load "/dashboard"'):
        page.goto("/dashboard")
        expect(L.nav(page, "Home")).to_be_visible()

    for label in L.NAV_ITEMS:
        expect(L.nav(page, label)).to_be_visible()
    expect(page.locator(L.NOTIFICATIONS)).to_be_visible()
    expect(page.locator(L.ACCOUNT_MENU)).to_be_visible()


@pytest.mark.scenario("S-12-02")
@pytest.mark.parametrize(
    ("item", "route"),
    [("Library", "/library"), ("My Workflows", "/workflows"), ("Home", "/dashboard")],
)
def test_each_nav_item_routes_to_its_screen(page, shot, item, route):
    """Scenario: Each nav item routes to its screen"""
    with shot("nav-start", 'Given I am on "/dashboard"'):
        page.goto("/dashboard")
        expect(L.nav(page, item)).to_be_visible()

    with shot(f"nav-{item.replace(' ', '-').lower()}", f'When I click "{item}"'):
        L.nav(page, item).click()
        page.wait_for_url(f"**{route}")

    # "and that screen renders" — the nav marking itself current is the shell's
    # own statement that it finished the transition, not merely that the URL
    # changed.
    expect(page.locator(L.CURRENT)).to_have_text(item)


@pytest.mark.scenario("S-12-03")
def test_nav_items_are_buttons_not_links(page, shot):
    """Scenario: Nav items are buttons, not links"""
    with shot("header-anchors", 'When I cold-load "/dashboard"'):
        page.goto("/dashboard")
        expect(L.nav(page, "Home")).to_be_visible()

    assert page.locator("header a[href]").count() == 0, (
        "the header grew an anchor — every nav test in this suite locates by "
        "button role and would silently stop covering it"
    )
    for label in L.NAV_ITEMS:
        expect(L.nav(page, label)).to_be_visible()


@pytest.mark.scenario("S-12-04")
def test_the_active_screen_is_indicated_in_the_nav(page, shot):
    """Scenario: The active screen is indicated in the nav"""
    with shot("nav-current", 'When I cold-load "/library"'):
        page.goto("/library")
        expect(page.get_by_role("heading", name="Library")).to_be_visible()

    current = page.locator(L.CURRENT)
    expect(current).to_have_count(1)
    expect(current).to_have_text("Library")


@pytest.mark.scenario("S-12-05")
@pytest.mark.parametrize("route", ["/login", "/admin", "/create/ppt", "/create/prototype"])
def test_the_shell_is_absent_where_it_should_be(page, shot, route):
    """Scenario: The shell is absent where it should be"""
    with shot(f"no-shell{route.replace('/', '-')}", f'When I cold-load "{route}"'):
        page.goto(route)
        page.wait_for_load_state("load")

    # The wizards and the admin shell substitute their own back control, so the
    # absence is asserted on the nav items rather than on a header element that
    # several of these screens legitimately still render.
    for label in L.NAV_ITEMS:
        expect(L.nav(page, label)).to_have_count(0)


# ── the account menu ─────────────────────────────────────────────────────────


@pytest.mark.scenario("S-12-06")
def test_the_account_menu_lists_its_items(page, shot):
    """Scenario: The account menu lists its items"""
    page.goto("/dashboard")
    with shot("account-menu", "When I click the Account menu control"):
        open_menu(page)

    expect(page.locator(L.MENU)).to_have_count(1)
    for label in L.MENU_ITEMS:
        expect(L.menu_item(page, label)).to_be_visible()


@pytest.mark.scenario("S-12-07")
def test_an_admin_additionally_sees_the_admin_entry(page, shot):
    """Scenario: An admin additionally sees the admin entry"""
    page.goto("/dashboard")
    with shot("account-menu-admin", "When I open the account menu as an admin"):
        open_menu(page)

    expect(L.menu_item(page, L.ADMIN_MENU_ITEM)).to_be_visible()


@pytest.mark.scenario("S-12-08")
@pytest.mark.role("pro")
def test_a_non_admin_does_not(page, shot):
    """Scenario: A non-admin does not"""
    page.goto("/dashboard")
    with shot("account-menu-pro", "When I open the account menu as qa-pro"):
        open_menu(page)

    # The rest of the menu is still there — the assertion is about ONE missing
    # entry, not about a menu that failed to open.
    expect(L.menu_item(page, "Account Settings")).to_be_visible()
    expect(L.menu_item(page, L.ADMIN_MENU_ITEM)).to_have_count(0)


@pytest.mark.scenario("S-12-09")
@pytest.mark.parametrize("item", list(L.MENU_ROUTES))
def test_each_menu_item_routes_correctly(page, shot, item):
    """Scenario: Each menu item routes correctly"""
    route = L.MENU_ROUTES[item]
    page.goto("/dashboard")
    with shot(f"menu-{item.replace(' ', '-').lower()}", f'When I click "{item}"'):
        open_menu(page)
        L.menu_item(page, item).click()
        page.wait_for_url(f"**{route}")

    assert page.url.endswith(route), f'"{item}" landed on {page.url}, not {route}'


@pytest.mark.scenario("S-12-10")
def test_escape_closes_the_account_menu(page, shot):
    """Scenario: Escape closes the account menu"""
    page.goto("/dashboard")
    open_menu(page)
    before = page.url

    with shot("menu-escaped", "When I press Escape"):
        page.keyboard.press("Escape")
        expect(page.locator(L.MENU)).to_have_count(0)

    assert page.url == before, "Escape navigated as well as closing"


# ── notifications ────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-12-11")
@pytest.mark.destructive
def test_the_notifications_panel_opens_with_an_empty_state(
    shot, disposable_user, browser, pytestconfig
):
    """Scenario: The notifications panel opens with an empty state

    Against a freshly created account, for the same reason S-10-13 is: a
    notification is raised by a run COMPLETING, and every seeded account has
    completed runs by now — the live tier and this suite both leave some. On a
    seeded session the panel legitimately renders its populated state, so
    asserting the empty copy there fails on correct behaviour.

    The empty state is still worth a scenario; it just needs an account that
    has never run anything, and creating one is the only way left to get it.
    """
    user = disposable_user(tier="basic")
    context = browser.new_context(
        base_url=settings.BASE_URL,
        viewport=settings.VIEWPORT,
        device_scale_factor=pytestconfig.getoption("--dpi"),
        reduced_motion="reduce",
    )
    page = context.new_page()
    shot.retarget(page)

    try:
        page.goto("/login")
        page.fill(AUTH.EMAIL, user["email"])
        page.fill(AUTH.PASSWORD, user["password"])
        page.click(AUTH.SIGN_IN)
        page.wait_for_url("**/dashboard", timeout=settings.LOGIN_TIMEOUT_MS)
        before = page.url

        with shot("notifications", "When I click the Notifications control"):
            page.click(L.NOTIFICATIONS)
            expect(page.get_by_text(L.NO_NOTIFICATIONS)).to_be_visible()

        expect(page.get_by_text(L.NOTIFICATIONS_HEADING, exact=True)).to_be_visible()
        expect(page.get_by_text(L.NOTIFICATIONS_HINT)).to_be_visible()
        assert page.url == before, "the panel changed the URL; it overlays the screen"
    finally:
        context.close()


@pytest.mark.scenario("S-12-12")
@pytest.mark.live
@pytest.mark.skip(reason="needs a run to complete; belongs to the live tier")
def test_a_completed_run_produces_a_notification(page, shot):
    """Scenario: A completed run produces a notification"""


# ── the running-pipeline badge ───────────────────────────────────────────────


@pytest.mark.scenario("S-12-13")
@pytest.mark.live
@pytest.mark.skip(reason="needs a run in progress; belongs to the live tier")
def test_a_live_run_surfaces_in_the_header_with_its_progress(page, shot):
    """Scenario: A live run surfaces in the header with its progress"""


@pytest.mark.scenario("S-12-14")
@pytest.mark.live
@pytest.mark.skip(reason="needs a run in progress; belongs to the live tier")
def test_the_badge_opens_the_live_run(page, shot):
    """Scenario: The badge opens the live run"""


@pytest.mark.scenario("S-12-15")
def test_the_badge_is_absent_when_nothing_is_running(page, shot):
    """Scenario: The badge is absent when nothing is running"""
    with shot("no-badge", 'When I cold-load "/dashboard" with nothing running'):
        page.goto("/dashboard")
        expect(L.nav(page, "Home")).to_be_visible()

    # The badge is the only header button that is neither a nav item nor one of
    # the two icon controls, so "nothing extra" is the assertion. Naming it by
    # its label is impossible — the label is whichever workflow is running.
    labels = [
        (t or "").strip()
        for t in page.locator("header nav button, header > div button").all_text_contents()
    ]
    unexpected = [t for t in labels if t and t not in L.NAV_ITEMS]
    if unexpected:
        # The premise is "no run in progress", and this suite cannot guarantee
        # it — another session, or the live tier, may have one in flight. A
        # badge shaped `<workflow> <done>/<total>` means the premise is false,
        # not that the assertion is.
        assert any(re.search(r"\d+\s*/\s*\d+", t) for t in unexpected), (
            f"the header shows {unexpected}, which is neither a nav item nor a "
            "running-pipeline badge"
        )
        pytest.skip(f"a run is in progress ({unexpected}); the badge is correct")


# ── theme ────────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-12-16")
def test_dark_mode_toggles_and_persists(page, shot):
    """Scenario: Dark mode toggles and persists"""
    page.goto("/dashboard")
    # `|| 'light'` because the attribute is ABSENT until something sets it —
    # comparing against a bare null makes every later check ambiguous.
    theme = "() => document.documentElement.getAttribute('data-theme') || 'light'"
    before = page.evaluate(theme)
    target = "dark" if before == "light" else "light"

    try:
        with shot("dark-mode", 'When I click "Dark mode"'):
            open_menu(page)
            L.menu_item(page, "Dark mode").click()
            page.wait_for_function(
                f"() => document.documentElement.getAttribute('data-theme') === '{target}'"
            )

        with shot("dark-mode-after-reload", "When I reload the page"):
            page.reload()
            expect(L.nav(page, "Home")).to_be_visible()

        assert page.evaluate(theme) == target, "the theme did not survive a reload"
    finally:
        # Persisted per browser profile. Left set, every later screenshot in the
        # run would be themed differently from the ones before it.
        if page.evaluate(theme) != before:
            open_menu(page)
            L.menu_item(page, "Dark mode").click()
            page.wait_for_function(
                f"() => (document.documentElement.getAttribute('data-theme') || 'light')"
                f" === '{before}'"
            )


# ── cross-cutting routing ────────────────────────────────────────────────────


@pytest.mark.scenario("S-12-17")
def test_browser_back_and_forward_work_across_top_level_screens(page, shot):
    """Scenario: Browser back and forward work across top-level screens"""
    page.goto("/dashboard")
    L.nav(page, "Library").click()
    page.wait_for_url("**/library")
    L.nav(page, "My Workflows").click()
    page.wait_for_url("**/workflows")

    with shot("back", "When I press browser Back"):
        page.go_back()
        page.wait_for_url("**/library")

    with shot("forward", "When I press browser Forward"):
        page.go_forward()
        page.wait_for_url("**/workflows")

    assert page.url.endswith("/workflows")


@pytest.mark.issue("ISS-190")
@pytest.mark.xfail(reason="ISS-190 unfixed", strict=True)
def test_forward_navigation_to_prototype_wizard_rehydrates(page, shot):
    """ISS-190 — Back-then-Forward to /create/prototype must render the wizard,
    not leave the un-hydrated RSC stream as a blank body.

    Reproduces the exact CONFIRMED 3/3 sequence from the card: fresh nav to
    /create/prototype -> Back (to /dashboard) -> Forward (back to
    /create/prototype), using real `page.go_back()`/`page.go_forward()`, not
    scripted `history.forward()`.
    """
    page.goto("/dashboard")
    page.goto("/create/prototype")
    page.wait_for_load_state("load")
    expect(page.locator("input[name='template-search']")).to_be_visible()

    with shot("prototype-back", "When I press browser Back"):
        page.go_back()
        page.wait_for_url("**/dashboard")

    with shot("prototype-forward", "When I press browser Forward"):
        page.go_forward()
        page.wait_for_url("**/create/prototype")

    # The card's own signature of the failure: body.innerText is empty while
    # body.innerHTML is full of raw, un-executed RSC stream text.
    expect(page.locator("input[name='template-search']")).to_be_visible()
    body_text_len = page.evaluate("() => document.body.innerText.length")
    assert body_text_len > 0, (
        "the wizard rehydrated to a blank body on Forward navigation "
        f"(body.innerText.length == {body_text_len})"
    )


@pytest.mark.scenario("S-12-18")
@pytest.mark.parametrize(
    ("route", "marker"),
    [
        ("/library?tab=hooks", '[data-testid="tab-hooks"]'),
        ("/workflows", None),
        ("/runs", None),
        ("/analytics", None),
        ("/settings/constitution", '[data-testid="tab-constitution"]'),
    ],
)
def test_every_top_level_screen_survives_a_hard_refresh(page, shot, route, marker):
    """Scenario: Every top-level screen survives a hard refresh"""
    page.goto(route)
    page.wait_for_load_state("load")
    before = page.evaluate("() => document.body.innerText.length")
    assert before > 0

    with shot(f"refresh{route.replace('/', '-').replace('?', '-')}", f'When I reload "{route}"'):
        page.reload()
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.url.endswith(route), f"{route} became {page.url} on reload"
    if marker:
        # The selected tab is the part a client-side router most easily loses:
        # the URL survives while the component remounts on its default.
        expect(page.locator(marker)).to_have_attribute("aria-selected", "true")


@pytest.mark.scenario("S-12-19")
def test_an_expired_session_sends_me_to_sign_in_with_an_explanation(page, shot):
    """Scenario: An expired session sends me to sign-in with an explanation

    ADR-0024 makes a 401 refresh ONCE before the session counts as expired, and
    the refresh call authenticates with the same access token. Replacing that
    token with a value the backend cannot accept therefore fails both halves of
    the ladder — which is what this scenario needs, and what merely waiting for
    an expiry would not reliably give.
    """
    page.goto("/dashboard")
    expect(L.nav(page, "Home")).to_be_visible()

    with shot("token-unusable", "Given my auth token can no longer be refreshed"):
        page.evaluate("() => localStorage.setItem('auth_token', 'not-a-usable-token')")

    with shot("expired-redirect", "When I click any nav item"):
        # The click may never land: the shell polls, so its own next request can
        # meet the 401 first and redirect out from under the button. Either path
        # is the scenario — the assertion is the destination, not the click.
        try:
            L.nav(page, "Library").click(timeout=5000)
        except Exception:
            pass
        # Polled, not `wait_for_url`: that attaches to the in-flight navigation
        # and raises ERR_ABORTED when the sign-in screen redirects again on
        # arrival. See framework/nav.py.
        NAV.wait_for_url_containing(page, "/login?expired=true")
        NAV.settle_after_redirect(page)

    expect(page.get_by_text(AUTH.EXPIRED_BANNER)).to_be_visible()
    # The stored token is cleared as well as the redirect fired — leaving it
    # would put the next screen into the same loop.
    assert page.evaluate("() => !localStorage.getItem('auth_token')")

"""Implements ../../../screens/13-errors.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**The 404 screen cannot identify itself.** A bad URL, a missing run and a
missing workflow all render the same markup, so every assertion here is anchored
on the URL the test navigated from rather than on anything the page says.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api, settings
from framework.locators import errors as L
from framework.locators import run_history as RH
from framework.locators import shell as SHELL


def cold(page, route: str) -> None:
    page.goto(route)
    page.wait_for_load_state("load")
    page.wait_for_timeout(settings.SETTLE_MS // 2)


def expect_404(page) -> None:
    expect(page.get_by_text(L.NOT_FOUND).first).to_be_visible()
    expect(page.get_by_text(L.CODE).first).to_be_visible()


@pytest.mark.scenario("S-13-01")
def test_an_unrecognised_url_shows_the_404_screen(page, shot):
    """Scenario: An unrecognised URL shows the 404 screen"""
    with shot("not-found", 'When I cold-load "/this-route-does-not-exist"'):
        cold(page, "/this-route-does-not-exist")

    expect_404(page)
    for label in L.ACTIONS:
        expect(page.get_by_text(label).first).to_be_visible()
    # Rendered outside the shell: no nav at all.
    for item in SHELL.NAV_ITEMS:
        expect(SHELL.nav(page, item)).to_have_count(0)


@pytest.mark.scenario("S-13-02")
def test_the_404_offers_a_way_back_that_works(page, shot):
    """Scenario: The 404 offers a way back that works"""
    cold(page, "/this-route-does-not-exist")

    with shot("back-to-dashboard", 'When I click "Back to dashboard"'):
        page.get_by_text("Back to dashboard").first.click()
        page.wait_for_url("**/dashboard")

    assert page.url.endswith("/dashboard")


@pytest.mark.scenario("S-13-03")
def test_the_404_create_action_reaches_the_composer(page, shot):
    """Scenario: The 404 create action reaches the composer"""
    cold(page, "/this-route-does-not-exist")

    with shot("create-a-workflow", 'When I click "Create a workflow"'):
        page.get_by_text("Create a workflow").first.click()
        page.wait_for_url(lambda url: "/workflows" in url or "/create" in url)

    assert "/workflows" in page.url or "/create" in page.url


@pytest.mark.scenario("S-13-04")
@pytest.mark.defect
def test_the_404_offers_sign_in_to_an_already_authenticated_user(page, shot):
    """Scenario: The 404 offers Sign in to an already-authenticated user

    Asserts TODAY'S behaviour. The 404 renders outside the shell and does not
    read the session, so it offers "Sign in" to someone who is already signed
    in. Harmless — the link lands on /login, which bounces an authenticated user
    onward — but confusing.
    """
    with shot("sign-in-when-signed-in", 'When I cold-load a bad URL while signed in'):
        cold(page, "/this-route-does-not-exist")

    assert page.evaluate("() => !!localStorage.getItem('auth_token')"), (
        "this test needs a live session to be meaningful"
    )
    expect(page.get_by_text("Sign in").first).to_be_visible()


@pytest.mark.scenario("S-13-05")
@pytest.mark.parametrize(
    "route",
    [
        "/workflows/some-id/nonsense",
        "/runs/some-id/nonsense",
        "/library/widgets/some-slug",
        "/create/",
    ],
)
def test_malformed_routes_fall_back_rather_than_crash(page, shot, route):
    """Scenario: Malformed routes fall back rather than crash

    CORRECTED for `/create/`. The trailing slash is normalised to `/create` and
    the home catalogue renders — it does not 404. The scenario's real claim
    survives: every malformed shape falls back to something, and none of them
    logs an unhandled error.
    """
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    with shot(f"malformed{route.replace('/', '-')}", f'When I cold-load "{route}"'):
        cold(page, route)

    if route == "/create/":
        assert page.url.rstrip("/").endswith("/create")
        expect(page.get_by_text("What would you like to build today?")).to_be_visible()
    else:
        expect_404(page)

    assert not errors, f"{route} logged {len(errors)} console error(s): {errors[:2]}"


@pytest.mark.scenario("S-13-06")
def test_a_bare_settings_redirects_to_profile(page, shot):
    """Scenario: A bare /settings redirects to Profile

    CORRECTED in the spec already, and worth restating: `parseViewPath` really
    does return `unknown` here, and the page redirects anyway. The parser's
    return value and the user's destination are two different things.
    """
    with shot("bare-settings", 'When I cold-load "/settings"'):
        page.goto("/settings")
        page.wait_for_url("**/settings/profile")

    assert page.url.endswith("/settings/profile")
    expect(page.get_by_text(L.NOT_FOUND)).to_have_count(0)


@pytest.mark.scenario("S-13-07")
def test_legacy_library_list_urls_are_redirected_not_404d(page, shot):
    """Scenario: Legacy library list URLs are redirected, not 404'd"""
    with shot("legacy-library", 'When I cold-load "/library/agents"'):
        page.goto("/library/agents")
        page.wait_for_url("**/library**")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    # next.config.ts intercepts the legacy two-segment shape before it reaches
    # parseViewPath, which would classify it as unknown.
    expect(page.get_by_text(L.NOT_FOUND)).to_have_count(0)
    expect(page.locator('[data-testid="tab-agents"]')).to_have_attribute(
        "aria-selected", "true"
    )


@pytest.mark.scenario("S-13-08")
def test_a_run_id_that_does_not_exist_falls_back_to_the_generic_404(page, shot):
    """Scenario: A run id that does not exist falls back to the generic 404"""
    with shot("missing-run", "When I cold-load a run id that does not exist"):
        cold(page, f"/runs/{L.NONEXISTENT_UUID}")

    expect_404(page)
    # Never a blank pane or a spinner that never resolves.
    for selector in settings.BUSY_SELECTORS:
        expect(page.locator(selector)).to_have_count(0)


@pytest.mark.scenario("S-13-09")
def test_a_workflow_id_that_does_not_exist_falls_back_to_the_generic_404(page, shot):
    """Scenario: A workflow id that does not exist falls back to the generic 404"""
    with shot("missing-workflow", "When I cold-load a workflow id that does not exist"):
        cold(page, f"/workflows/{L.NONEXISTENT_UUID}")

    expect_404(page)


@pytest.mark.scenario("S-13-10")
@pytest.mark.defect
def test_missing_resource_errors_are_indistinguishable_from_a_bad_url(page, shot):
    """Scenario: Missing-resource errors are indistinguishable from a bad URL

    Recorded as an observation, not a demand to change it — but it is the reason
    every other test in this module anchors on the URL it navigated from.
    """
    screens = []
    for route in (
        "/this-route-does-not-exist",
        f"/runs/{L.NONEXISTENT_UUID}",
        f"/workflows/{L.NONEXISTENT_UUID}",
    ):
        with shot(f"identical{route.replace('/', '-')[:40]}", f'When I cold-load "{route}"'):
            cold(page, route)
        expect_404(page)
        screens.append(page.evaluate("() => document.body.innerText"))

    assert screens[0] == screens[1] == screens[2], (
        "the three failures now render different screens — one of them names "
        "the resource. Re-read this defect before changing the test."
    )
    for text in screens[1:]:
        assert "run" not in text.lower().split("workforce")[0], text[:120]


@pytest.mark.scenario("S-13-11")
@pytest.mark.defect
def test_a_nonexistent_artifact_version_falls_back_to_v1_without_saying_so(page, shot):
    """Scenario: A nonexistent artifact version falls back to v1 without saying so

    Asserts TODAY'S behaviour — D-12.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    completed = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    assert completed, "no completed run to ask for a version of"
    page.locator(f'{RH.ROW}[aria-label="{completed[0]}"]').click()
    page.wait_for_url(lambda url: "/runs/" in url)
    run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]

    with shot("version-99", 'When I cold-load "/runs/{id}/versions/99"'):
        cold(page, f"/runs/{run_id}/versions/99")

    if page.get_by_text(L.NOT_FOUND).count():
        pytest.skip("this run has no artifact to version; D-12 needs one that has")

    # The URL keeps the version that was asked for, and nothing on the page says
    # it was not the version served.
    assert page.url.endswith("/versions/99")
    body = page.evaluate("() => document.body.innerText")
    assert "v1" in body.lower(), body[:200]
    assert not any(
        phrase in body.lower()
        for phrase in ("does not exist", "not available", "unavailable", "instead")
    ), f"the page now explains the fallback — D-12 is fixed: {body[:200]!r}"


@pytest.mark.scenario("S-13-12")
def test_an_oversized_full_screen_preview_explains_itself(page, shot):
    """Scenario: An oversized full-screen preview explains itself

    No heading element on this page — match on text, not `get_by_role`.
    """
    with shot("quota", 'When I cold-load "/preview-fullscreen?error=quota"'):
        cold(page, "/preview-fullscreen?error=quota")

    expect(page.get_by_text("Project too large for full screen")).to_be_visible()
    expect(page.get_by_text("~5MB")).to_be_visible()
    expect(page.get_by_text("Download ZIP")).to_be_visible()


@pytest.mark.scenario("S-13-13")
@pytest.mark.role("basic")
def test_another_users_run_is_not_readable(page, shot, page_as):
    """Scenario: Another user's run is not readable

    FIX-309's UI half: `previous_run.py` ran `assert_owns` AFTER
    `_seed_existing_artifact`, on the belief that the helper was
    parent-independent. The Concierge fallback had since added a
    `read_parent_file` call inside it, so a parent sandbox was read before
    ownership was established.

    Uses qa-admin's run rather than qa-pro's — same ownership boundary, and
    qa-admin is the account this suite knows holds runs.
    """
    owner = page_as("admin")
    owner.goto("/runs")
    expect(owner.locator(RH.ROW).first).to_be_visible()
    owner.locator(RH.ROW).first.click()
    owner.wait_for_url(lambda url: "/runs/" in url)
    stolen = owner.url

    with shot("foreign-run", "When I cold-load that run's URL as another user"):
        cold(page, stolen.replace(settings.BASE_URL, ""))

    body = page.evaluate("() => document.body.innerText")
    assert L.NOT_FOUND in body or "forbidden" in body.lower() or "not authorized" in body.lower(), (
        f"another user's run rendered its contents: {body[:200]!r}"
    )


@pytest.mark.scenario("S-13-14")
@pytest.mark.role("basic")
def test_a_run_file_cannot_be_fetched_across_an_ownership_boundary(page, shot, page_as):
    """Scenario: A run file cannot be fetched across an ownership boundary"""
    owner = page_as("admin")
    owner.goto("/runs")
    expect(owner.locator(RH.ROW).first).to_be_visible()
    owner.locator(RH.ROW).first.click()
    owner.wait_for_url(lambda url: "/runs/" in url)
    run_id = owner.url.split("/runs/")[1].split("/")[0].split("?")[0]

    with shot("foreign-run-file", "When I request one of its files with my own token"):
        page.goto("/dashboard")
        # Every read path onto another user's run, not just one: the run record,
        # its artifacts, and a file out of its sandbox. `/files` is POST-only
        # (uploads) and answers 405 to a GET, which is not an ownership result.
        results = {
            path: api.request(page, "GET", f"/api/runs/{run_id}{path}")
            for path in ("", "/artifacts", "/sandbox/file?path=output.md")
        }

    for path, result in results.items():
        assert result["status"] in (401, 403, 404), (
            f"a foreign run's {path or '/'} answered {result['status']}: "
            f"{result['body'][:200]!r}"
        )

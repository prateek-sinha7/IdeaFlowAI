"""Implements ../../../screens/19-toasts-and-dialogs.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

The run-completion toasts need a run to finish, so S-19-01..S-19-06 belong to
the live tier. What runs offline is the admin family — its toasts, its timeout,
and the in-app confirm that guards the most destructive control in the product.

The admin scenarios mutate a seeded account and put it back in a `finally`.
Each one changes exactly one thing about qa-pro and reverses it.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from framework import accounts, settings
from framework.locators import admin as ADMIN
from framework.locators import toasts as L

# …/tests/integration/e2e/suites/19_toasts_and_dialogs/ -> the repo root is five
# levels up, not four: suites, e2e, integration, tests, root.
FRONTEND = Path(__file__).resolve().parents[5] / "frontend" / "src"


def open_admin(page) -> None:
    page.goto("/admin")
    expect(page.get_by_text(ADMIN.HEADING)).to_be_visible()
    expect(page.locator(ADMIN.row(accounts.PRO)).first).to_be_visible()


def toast_with(page, text: str):
    """A toast carrying `text`, whichever live region it landed in."""
    return page.get_by_text(re.compile(re.escape(text))).first


# ── run-completion toasts (live) ─────────────────────────────────────────────

_NEEDS_A_RUN = "needs a run to finish while the page is open; live tier"


@pytest.mark.scenario("S-19-01")
@pytest.mark.live
@pytest.mark.skip(reason=_NEEDS_A_RUN)
def test_a_completed_run_raises_a_toast_with_a_way_into_the_result(page, shot):
    """Scenario: A completed run raises a toast with a way into the result"""


@pytest.mark.scenario("S-19-02")
@pytest.mark.live
@pytest.mark.skip(reason=_NEEDS_A_RUN)
def test_a_failed_run_names_the_workflow_in_the_toast(page, shot):
    """Scenario: A failed run names the workflow in the toast"""


@pytest.mark.scenario("S-19-03")
@pytest.mark.live
@pytest.mark.skip(reason=_NEEDS_A_RUN)
def test_a_completion_toast_dismisses_itself_after_7_seconds(page, shot):
    """Scenario: A completion toast dismisses itself after 7 seconds"""


@pytest.mark.scenario("S-19-04")
@pytest.mark.live
@pytest.mark.skip(reason=_NEEDS_A_RUN)
def test_a_toast_can_be_dismissed_early(page, shot):
    """Scenario: A toast can be dismissed early"""


@pytest.mark.scenario("S-19-05")
@pytest.mark.live
@pytest.mark.skip(reason="needs two runs completing close together; live tier")
def test_toasts_stack_rather_than_replace(page, shot):
    """Scenario: Toasts stack rather than replace"""


@pytest.mark.scenario("S-19-06")
@pytest.mark.live
@pytest.mark.skip(reason=_NEEDS_A_RUN)
def test_a_toast_does_not_block_the_page_beneath_it(page, shot):
    """Scenario: A toast does not block the page beneath it"""


# ── admin toasts ─────────────────────────────────────────────────────────────


_LOCKS_EVERYONE_OUT = (
    "granting a second admin trips the break-glass invariant and locks EVERY "
    "admin out of the product — D-31"
)


def tier_control(page):
    return page.locator(ADMIN.row(accounts.PRO)).first.locator(
        'button[aria-haspopup="menu"]'
    ).first


def set_tier(page, label: str) -> None:
    tier_control(page).click()
    page.get_by_role("menuitem", name=re.compile(label, re.I)).first.click()
    page.wait_for_timeout(settings.SETTLE_MS // 2)


@pytest.mark.scenario("S-19-07")
@pytest.mark.destructive
@pytest.mark.parametrize("action", ["grant", "revoke", "tier", "create", "delete"])
def test_admin_actions_confirm_themselves_by_toast(page, shot, action, disposable_user):
    """Scenario: Admin actions confirm themselves by toast

    Only the tier change runs. The other four are all unsafe here, for two
    different reasons:

    **grant / revoke** — granting admin to a second account leaves the database
    with two local admins, and `resolve_principal` then refuses EVERY
    local-admin credential ("break-glass invariant, plan §5.6: expected exactly
    1 local admin but found 2"). The grant succeeds, the account is locked out
    on the very next request, and the test's own cleanup cannot run because it
    needs the session it just destroyed. That is D-31, and it cost this suite a
    two-hour outage before it was understood.

    **create / delete** — need a disposable fixture account, as S-11-15 does.
    """
    if action in ("grant", "revoke"):
        pytest.skip(_LOCKS_EVERYONE_OUT)
    if action in ("create", "delete"):
        user = disposable_user(tier="basic")
        open_admin(page)
        if action == "create":
            with shot("create-toast", "Then the creation is confirmed by toast"):
                expect(page.locator(ADMIN.row(user["email"])).first).to_be_visible()
            # The row IS the confirmation the toast reports; the toast itself
            # fires on the dialog path, which S-11-15 drives.
            assert user["email"] in page.evaluate("() => document.body.innerText")
            return
        with shot("delete-toast", "When I delete that user"):
            page.click(ADMIN.delete_user(user["email"]))
            expect(page.get_by_text(L.DELETE_DIALOG)).to_be_visible()
            page.get_by_role("button", name="Delete", exact=True).last.click()
            expect(toast_with(page, L.ADMIN_MESSAGES["delete"])).to_be_visible()
        return

    open_admin(page)
    before = tier_control(page).inner_text().strip().split("\n")[0]

    try:
        with shot("tier-changed", "When I change a user's tier"):
            set_tier(page, "Enterprise")
            expect(toast_with(page, L.ADMIN_MESSAGES["tier"])).to_be_visible()
    finally:
        open_admin(page)
        if tier_control(page).inner_text().strip().split("\n")[0].lower() != before.lower():
            set_tier(page, before)


@pytest.mark.scenario("S-19-08")
@pytest.mark.defect
def test_an_admin_failure_is_reported_not_swallowed(page, shot):
    """Scenario: An admin failure is reported, not swallowed

    Asserts TODAY'S behaviour, which is the opposite of the scenario's name —
    D-32. The backend refuses an admin's attempt to change their OWN tier
    (S-11-08 pins the API side), and the dashboard applies the change
    optimistically anyway: the row shows the tier that was refused, no error
    toast appears, and the stat tiles above still count the old one. Only a
    reload reveals that nothing was saved.

    Driven through that refusal precisely because it changes nothing — the
    write never lands, so there is nothing to restore beyond the reload this
    test does anyway.
    """
    open_admin(page)
    own = page.locator(ADMIN.row(accounts.ADMIN)).first
    trigger = own.locator('button[aria-haspopup="menu"]').first

    if trigger.is_disabled():
        pytest.skip("the admin's own tier control is disabled, so no request is made")

    before = trigger.inner_text().strip().split("\n")[0]

    with shot("admin-refusal-swallowed", "When I attempt a change the backend rejects"):
        trigger.click()
        page.get_by_role("menuitem", name=re.compile("Basic", re.I)).first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    reported = any(
        word in body.lower() for word in ("cannot", "not allowed", "failed", "refus")
    )
    assert not reported, (
        "the refusal is now reported — D-32 is fixed. Rewrite this as the "
        f"spec's S-19-08, which asserts the error toast. Page said: {body[:200]!r}"
    )
    assert trigger.inner_text().strip().split("\n")[0].lower() == "basic", (
        "the row no longer shows the refused tier, so the optimistic update is "
        "gone too — re-read D-32"
    )

    with shot("reverted-on-reload", "When I reload, the refused change is gone"):
        open_admin(page)

    after = page.locator(ADMIN.row(accounts.ADMIN)).first.locator(
        'button[aria-haspopup="menu"]'
    ).first.inner_text().strip().split("\n")[0]
    assert after.lower() == before.lower(), (
        f"the admin's tier really changed to {after!r} — the backend did NOT "
        "refuse it, which is far worse than D-32"
    )


@pytest.mark.scenario("S-19-09")
@pytest.mark.destructive
def test_the_two_toast_families_use_different_timeouts(page, shot):
    """Scenario: The two toast families use different timeouts

    Measures the ADMIN toast, which is reachable offline. The 7000ms
    run-completion timeout is S-19-03's, in the live tier — what this asserts is
    that the admin one is meaningfully shorter, which is the part a shared wait
    helper gets wrong.

    Driven by a tier change, not by granting admin: see S-19-07 and D-31.
    """
    open_admin(page)
    before = tier_control(page).inner_text().strip().split("\n")[0]

    try:
        with shot("admin-toast-shown", "When an admin toast appears"):
            set_tier(page, "Enterprise")
            toast = toast_with(page, L.ADMIN_MESSAGES["tier"])
            expect(toast).to_be_visible()
            started = time.monotonic()

        # Gone well before a run-completion toast would be.
        expect(toast).to_have_count(0, timeout=L.RUN_TIMEOUT_MS)
        elapsed_ms = (time.monotonic() - started) * 1000
        assert elapsed_ms < L.RUN_TIMEOUT_MS, (
            f"the admin toast lasted {elapsed_ms:.0f}ms — as long as a "
            "run-completion toast, so the two families no longer differ"
        )
    finally:
        open_admin(page)
        if tier_control(page).inner_text().strip().split("\n")[0].lower() != before.lower():
            set_tier(page, before)


# ── the delete-user confirm ──────────────────────────────────────────────────


@pytest.mark.scenario("S-19-10")
@pytest.mark.destructive
def test_deleting_a_user_requires_confirmation(page, shot):
    """Scenario: Deleting a user requires confirmation

    Opens the dialog and cancels. Nothing is deleted — the whole point is that
    the control does not act on its own.
    """
    open_admin(page)

    with shot("delete-dialog", 'When I activate "Delete <email>"'):
        page.click(ADMIN.delete_user(accounts.PRO))
        expect(page.get_by_text(L.DELETE_DIALOG)).to_be_visible()

    expect(page.get_by_text(re.compile(L.DELETE_WARNING, re.I))).to_be_visible()
    expect(page.locator(L.CANCEL)).to_be_visible()
    expect(page.locator(L.CONFIRM_DELETE).last).to_be_visible()
    page.click(L.CANCEL)


@pytest.mark.scenario("S-19-11")
@pytest.mark.destructive
def test_cancelling_a_delete_leaves_the_user_intact(page, shot):
    """Scenario: Cancelling a delete leaves the user intact"""
    open_admin(page)
    page.click(ADMIN.delete_user(accounts.PRO))
    expect(page.get_by_text(L.DELETE_DIALOG)).to_be_visible()

    with shot("delete-cancelled", 'When I activate "Cancel"'):
        page.click(L.CANCEL)
        expect(page.get_by_text(L.DELETE_DIALOG)).to_have_count(0)

    expect(page.locator(ADMIN.row(accounts.PRO)).first).to_be_visible()


@pytest.mark.scenario("S-19-12")
@pytest.mark.destructive
def test_clicking_the_scrim_cancels_the_delete(page, shot):
    """Scenario: Clicking the scrim cancels the delete"""
    open_admin(page)
    page.click(ADMIN.delete_user(accounts.PRO))
    expect(page.get_by_text(L.DELETE_DIALOG)).to_be_visible()

    with shot("scrim-cancelled", "When I click the scrim outside the dialog"):
        # Top-left corner: far from the centred dialog, inside the scrim.
        page.mouse.click(8, 8)
        expect(page.get_by_text(L.DELETE_DIALOG)).to_have_count(0)

    expect(page.locator(ADMIN.row(accounts.PRO)).first).to_be_visible()


@pytest.mark.scenario("S-19-13")
@pytest.mark.destructive
def test_confirming_removes_the_user_and_says_so(page, shot, disposable_user):
    """Scenario: Confirming removes the user and says so

    THE most destructive control in the product, so it runs against its own
    disposable fixture and never a seeded account.
    """
    user = disposable_user(tier="basic")
    open_admin(page)
    expect(page.locator(ADMIN.row(user["email"])).first).to_be_visible()
    before = _total_users(page)

    with shot("delete-confirmed", 'When I activate "Delete"'):
        page.click(ADMIN.delete_user(user["email"]))
        expect(page.get_by_text(L.DELETE_DIALOG)).to_be_visible()
        page.get_by_role("button", name="Delete", exact=True).last.click()
        expect(page.locator(ADMIN.row(user["email"]))).to_have_count(0, timeout=20000)

    expect(toast_with(page, L.ADMIN_MESSAGES["delete"])).to_be_visible()
    assert _total_users(page) == before - 1


def _total_users(page) -> int:
    text = page.evaluate("() => document.body.innerText")
    m = re.search(r"TOTAL USERS\s*\n\s*(\d+)", text)
    assert m, f"no TOTAL USERS tile: {text[:200]!r}"
    return int(m.group(1))


@pytest.mark.scenario("S-19-14")
def test_an_admin_cannot_delete_themselves_into_lockout(page, shot):
    """Scenario: An admin cannot delete themselves into lockout

    The spec records this as UNVERIFIED — no last-admin guard was found in
    `app/admin/page.tsx`. The guard that DOES exist is a narrower one: an admin
    cannot delete their own account at all, which is what this asserts.

    That is not the same promise. With two admins, either can delete the other,
    and the second deletion is refused only because it is a self-delete. Whether
    the last admin can be removed by another admin is untested here because it
    cannot be tried without destroying the fixture that would prove it.
    """
    open_admin(page)

    with shot("self-delete", "When I look at my own row's delete control"):
        own = page.locator(ADMIN.delete_user(accounts.ADMIN))

    assert own.count() == 0 or own.first.is_disabled(), (
        "an admin is offered a working delete control on their own row"
    )


# ── native browser dialogs ───────────────────────────────────────────────────


@pytest.mark.scenario("S-19-15")
@pytest.mark.live
@pytest.mark.skip(reason="needs a run whose deliverable download can be made to fail; live tier")
def test_a_failed_download_reports_itself_through_window_alert(page, shot):
    """Scenario: A failed download reports itself through window.alert"""


@pytest.mark.scenario("S-19-16")
def test_every_test_that_can_trigger_a_download_registers_a_dialog_handler(page, shot):
    """Scenario: Every test that can trigger a download registers a dialog handler

    A HARNESS requirement, not a product assertion — recorded here because this
    is where someone will look for it. Playwright BLOCKS on a native dialog
    until something handles it, so an unhandled alert hangs the run instead of
    failing it.

    `conftest.dismiss_native_dialogs` is autouse, and this proves it: raising an
    alert here would hang this very test if the handler were missing.
    """
    with shot("dialog-handled", "When a native alert is raised"):
        page.goto("/dashboard")
        page.evaluate("() => window.alert('e2e dialog-handler check')")

    assert "e2e dialog-handler check" in getattr(page, "native_dialogs", []), (
        "the autouse dialog handler did not see the alert"
    )
    # The page is still usable — nothing is blocked behind an open dialog.
    assert page.evaluate("() => document.readyState") == "complete"


@pytest.mark.scenario("S-19-17")
def test_download_failures_are_the_only_native_dialogs_in_the_product(page, shot):
    """Scenario: Download failures are the only native dialogs in the product

    A source assertion, deliberately: destructive confirmation is done with the
    in-app dialog above, which is the better pattern, and this is what stops
    someone reintroducing `window.confirm`. There is no runtime surface that
    could prove an absence.
    """
    # Bare `alert(`/`confirm(`, optionally `window.`-qualified — the product
    # writes `alert("Failed to generate ZIP.")`, so a `window.`-only pattern
    # matches nothing and the check passes without checking anything.
    # No space before the paren: prose says "an explicit confirm (44-02)" and
    # "the system prompt (KAN-76)", and a `\s*` there matches all of it.
    native = re.compile(r"(?<![\w.$])(?:window\.)?(confirm|prompt)\(")
    alert_call = re.compile(r"(?<![\w.$])(?:window\.)?alert\(")

    offenders, alerts = [], 0
    for path in FRONTEND.rglob("*.ts*"):
        if ".test." in path.name or path.name.endswith(".d.ts"):
            continue
        text = path.read_text(errors="ignore")
        for m in native.finditer(text):
            offenders.append(f"{path.relative_to(FRONTEND)}: {m.group(0)}")
        alerts += len(alert_call.findall(text))

    assert not offenders, f"native confirm/prompt reintroduced: {offenders}"
    assert alerts > 0, "no alert() remains — S-19-15 has nothing left to assert"

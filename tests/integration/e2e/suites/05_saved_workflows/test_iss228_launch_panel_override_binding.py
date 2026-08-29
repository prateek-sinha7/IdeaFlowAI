"""BUG-20260828-073900-workflows-id-run-r2 — ISS-228 / ISS-283 / ISS-284.

A saved workflow's launch panel loses its override entirely and renders the
generic base-type wizard, with no trace anywhere on the page that this is a
saved override rather than a brand-new blank launch. See
`bug-hunter/ledger.md`'s `BUG-20260828-073900-workflows-id-run-r2` entry for
the full root-cause analysis (a same-commit React effect-ordering race in
`LaunchWizard.tsx`).

Fixture: the seeded `"My prototype"` override
(`656ca387-e69c-474d-b7ff-5fd9eb017cc0`, `agent_ids: ["documentation-agent",
"prototype-specify"]`, confirmed alive via `GET /api/user-workflows/{id}`).

NO TEST HERE FOR ISS-284. That card predicts "Save as my version" clicked
mid-race silently persists a race-clobbered default roster back to the
server. Live-verified (cold /workflows/{id}/run mount, click "Save as my
version" as the very next action, diff GET /api/user-workflows/{id} before
and after): the response and the persisted `agent_ids`/`manifest` both stay
exactly `["documentation-agent", "prototype-specify"]` — the save is
correct. A `--runxfail` run of that exact assertion PASSES today, so an
`xfail`-marked test for it would never legitimately observe red; per the
test-writer's own instruction not to ship a test never seen to fail, ISS-284
is left untested here. See this run's NOTE for the 5-fixer/6-verifier.
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import expect

PROTO_ID = "656ca387-e69c-474d-b7ff-5fd9eb017cc0"
PROTO_NAME = "My prototype"


@pytest.mark.issue("ISS-228")
@pytest.mark.xfail(reason="ISS-228 unfixed", strict=True)
def test_cold_launch_panel_shows_the_saved_overrides_own_name(page, shot):
    """ISS-228 — a cold direct navigation to a saved workflow's own
    /workflows/{id}/run must give some visible indication it is bound to
    THAT workflow ("My prototype"), not render as an anonymous generic
    wizard with no trace of the saved override anywhere on the page."""
    with shot("cold-launch", f'When I cold-load "/workflows/{PROTO_ID}/run"'):
        page.goto(f"/workflows/{PROTO_ID}/run")
        expect(page.get_by_text("Configure your prototype")).to_be_visible()

    body = page.evaluate("() => document.body.innerText")
    assert PROTO_NAME in body, (
        f"the override's own name {PROTO_NAME!r} never appears anywhere on "
        f"the launch panel — the page gives no indication this is a saved "
        f"override at all: {body[:200]!r}"
    )


@pytest.mark.issue("ISS-283")
@pytest.mark.xfail(reason="ISS-283 unfixed", strict=True)
def test_click_through_run_shows_the_saved_overrides_own_name_even_mid_race(page, shot):
    """ISS-283 — clicking "Run workflow" on a saved prototype override
    BEFORE GET /api/agents/library has resolved must still surface the same
    override binding as a direct /workflows/{id}/run deep link, not a wizard
    with no trace of the saved workflow at all."""

    def _slow(route):
        time.sleep(2)
        route.continue_()

    page.route("**/api/agents/library", _slow)
    try:
        with shot(
            "run-from-list",
            f'When I click "Run workflow" on "{PROTO_NAME}" before the library loads',
        ):
            page.goto("/workflows")
            page.fill('input[name="saved-workflows-search"]', PROTO_NAME)
            card = page.locator("div.bg-surface-card.group").filter(has_text=PROTO_NAME).first
            card.locator('button:has-text("Run workflow")').click()
            page.wait_for_url("**/create/prototype**", timeout=15_000)
            page.wait_for_timeout(3_000)
    finally:
        page.unroute("**/api/agents/library", _slow)

    body = page.evaluate("() => document.body.innerText")
    assert PROTO_NAME in body, (
        f"the override's own name {PROTO_NAME!r} never appears after a "
        f"click-through Run made while the agent library was still "
        f"loading: {body[:200]!r}"
    )

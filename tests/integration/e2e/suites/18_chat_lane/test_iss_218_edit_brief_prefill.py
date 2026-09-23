"""ISS-218 / ISS-235 — "Edit brief & run again" on a failed run must open the
composer with the FAILED RUN'S OWN brief pre-filled, never blank and never a
leftover value from somewhere else.

ISS-218 pins the reproduced case: the composer opened blank. `handleEditBrief`
read the brief off `recentRuns`, but `GET /api/runs` deliberately omits the
heavy `input`/`output`/`agent_outputs` columns ("Heavy fields ... are excluded
— fetch the full run", backend/app/api/runs.py), so that lookup was `undefined`
for every run and fell through to an empty string. A second defect sat behind
it: the wizard hand-off was gated on `selectWorkflowWizardPath`, whose table
omits `prototype_v2` even though `wizardModeFor` renders the wizard for it, so
for that type the brief was written to a slot nothing on the route reads.

ISS-235 is the sibling: the brief shown must always belong to the run currently
being edited, never leak from a previous edit-brief click. The originally
imagined trigger (typing into the Home page's own brief textbox) is no longer
reachable — that textarea was removed by FIX-181 — so this proves the same
property with two different failed runs clicked in the same session.

FIXTURES ARE DISCOVERED AT RUNTIME, deliberately. This file used to hardcode
two run ids and their expected brief TEXT. Both ids still resolved after a
later reseed, but to entirely different runs — both `completed`, so the failed
lane that owns the button never rendered and the scenarios timed out hunting a
`chat-relaunch-secondary` that was never going to appear. A fixture that rots
into a different run is worse than one that rots into a 404, because it fails
for a reason that looks like a product bug. The brief is now read from the run
itself, so there is no expected-text constant left to drift.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api, settings
from framework.locators import run_detail as RD


def _failed_runs_with_briefs(page, how_many: int) -> list[tuple[str, str]]:
    """`how_many` failed runs carrying DISTINCT briefs, as (run_id, brief).

    The brief comes from `GET /api/runs/{id}`, not from the list: the list
    endpoint omits `input` by design, which is the very bug ISS-218 is about.

    Distinct is a requirement, not a nicety. This history holds several failed
    runs of the same brief (repeat attempts at one prototype), and ISS-235 asks
    whether the SECOND click shows the second run's brief or leaks the first's —
    a question two identical briefs cannot answer either way.
    """
    # api.json_body reads the bearer token out of localStorage, which throws a
    # SecurityError on the blank document a fresh page fixture starts on. Land
    # on an app-origin page first — the same order a_run_with_files uses.
    if "/runs" not in page.url:
        page.goto("/runs")
        expect(page.locator(RD.LANE).or_(page.locator("body"))).to_be_visible()
    listing = api.json_body(page, "GET", "/api/runs?limit=50")
    rows = listing if isinstance(listing, list) else listing.get("runs", listing.get("items", []))
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("status") != "failed":
            continue
        brief = (api.json_body(page, "GET", f"/api/runs/{row['id']}").get("input") or "").strip()
        if not brief or brief in seen:
            continue
        seen.add(brief)
        found.append((row["id"], brief))
        if len(found) == how_many:
            return found
    pytest.skip(
        f"need {how_many} failed run(s) with DISTINCT briefs; this history has {len(found)}"
    )


def _norm(text: str) -> str:
    """Line-ending-normalised text, for comparing a brief against a textarea.

    Not a loosened comparison — the HTML spec defines a textarea's API value as
    using LF, so a brief stored with CRLF (these briefs embed an attached CSV,
    which carries CRLF) comes back out with the CRs stripped. Comparing raw
    fails at the first embedded newline, 407 characters in, on a value that is
    otherwise byte-identical. Everything else still has to match exactly.
    """
    return text.replace("\r\n", "\n").strip()


def _click_edit_brief_and_run_again(page, run_id: str) -> None:
    page.goto(f"/runs/{run_id}")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    page.locator('[data-testid="chat-relaunch-secondary"]').click()
    page.wait_for_url(lambda url: "/create/" in url)
    page.wait_for_timeout(settings.SETTLE_MS)


@pytest.mark.issue("ISS-218")
def test_edit_brief_and_run_again_prefills_the_original_brief(page, shot):
    """The composer opened by "Edit brief & run again" on a FAILED run must
    show that run's own brief text, not a blank textarea."""
    run_id, brief = _failed_runs_with_briefs(page, 1)[0]

    with shot("edit-brief-prefill", 'When I click "Edit brief & run again" on a failed run'):
        _click_edit_brief_and_run_again(page, run_id)

    textarea_value = page.locator("textarea").first.input_value()
    assert _norm(textarea_value) == _norm(brief), (
        f"expected the failed run's own brief to be pre-filled, got "
        f"{textarea_value!r} (run {run_id} brief is {brief!r})"
    )


@pytest.mark.issue("ISS-235")
def test_edit_brief_shows_the_currently_viewed_runs_own_brief_not_a_leftover(page, shot):
    """Clicking "Edit brief & run again" on one failed run and then on a
    DIFFERENT failed run must show each run's OWN brief every time — never a
    value left over from the previous run's edit-brief click."""
    (run_a, brief_a), (run_b, brief_b) = _failed_runs_with_briefs(page, 2)

    _click_edit_brief_and_run_again(page, run_a)
    first_value = page.locator("textarea").first.input_value()
    assert _norm(first_value) == _norm(brief_a), f"setup failed: got {first_value[:120]!r} for run A"

    with shot(
        "edit-brief-second-run",
        'When I then click "Edit brief & run again" on a DIFFERENT failed run',
    ):
        _click_edit_brief_and_run_again(page, run_b)

    second_value = page.locator("textarea").first.input_value()
    assert _norm(second_value) == _norm(brief_b), (
        f"expected run B's own brief, got {second_value[:160]!r} — "
        f"(run A's brief began {first_value[:160]!r})"
    )
    assert second_value != first_value, (
        "the second run's composer shows the SAME value as the first run's — "
        "the brief is leaking across edit-brief clicks instead of tracking the "
        "currently viewed run"
    )

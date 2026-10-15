"""ISS-606 / ISS-609 — BUG-20260829-135100-runs-id-versions.

The Steps tab's pipeline summary/agent list and the Audit tab's own fetches
both ignore the URL's version pin, unlike `effUserStoryContent` et al. (the
Preview-tab content, already version-aware per FIX-334).

Same discovered family as ISS-230's suite file (`a_revised_family`): its root
is v1 and its second member is v2.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD

from .test_run_families_and_versions import a_revised_family


@pytest.mark.issue("ISS-606")
def test_steps_tab_shows_the_pinned_versions_own_agent_count(page, shot):
    """The Steps tab's "N / N agents" summary must reflect the PINNED
    version's own agent_count, not the root run's. This is tested by reading
    the root's agent count first, then navigating to v2 and asserting that
    the displayed count is the PINNED version's own (i.e., they differ or
    both are the same and truly the v2 count)."""
    root, members = a_revised_family(page)
    v2 = members[1]["id"]

    def roster_at(url: str, label: str) -> int:
        """The roster size the Steps tab reports for whatever run `url` shows."""
        page.goto(url)
        expect(page.locator(RD.LANE)).to_be_visible()
        page.get_by_text("agents").first.wait_for(state="visible")
        page.wait_for_timeout(settings.SETTLE_MS)
        body = page.evaluate("() => document.body.innerText")
        progress = RD.steps_progress(body)
        assert progress, f"no agent-count summary on {label}: {body[:300]!r}"
        return progress[1]

    # The revision's OWN page is the source of truth for its roster. Deriving the
    # expectation this way (rather than from the root) is what makes the check
    # survive a fixture swap: whatever family this points at, v2's own page and
    # the pinned view must agree.
    v2_own = roster_at(f"/runs/{v2}/steps", "the revision's own page")
    root_roster = roster_at(f"/runs/{root}/steps", "the root")

    with shot("iss606-steps-v2", "When I cold-load the Steps tab pinned to v2"):
        pinned = roster_at(f"/runs/{root}/versions/2/steps", "the pinned view")

    # ISS-606 is the pinned view rendering the ROOT's roster instead of its own.
    # Assert against the revision's own figure — comparing pinned-vs-root instead
    # would pass whenever the two happen to be equal, and would go quiet exactly
    # when the bug is present (a pinned view showing root data looks identical to
    # the root by definition).
    assert pinned == v2_own, (
        f"Steps tab pinned to v2 shows {pinned} agents, but the revision's own "
        f"page reports {v2_own} (the root reports {root_roster}) — the pinned "
        "view is not showing the pinned version's own roster"
    )
    if root_roster == v2_own:
        # Not a failure: the assertion above is still correct and still ran. But
        # with identical rosters it cannot tell "showed v2" from "showed root",
        # so say so rather than banking a green that proved nothing.
        print(
            f"NOTE: root and v2 both report {v2_own} agents, so this run of the "
            "scenario cannot discriminate between them. A family whose revision "
            "changes the roster size would make it meaningful again."
        )


@pytest.mark.issue("ISS-609")
def test_audit_tab_fetches_the_pinned_versions_own_run_id(page, shot):
    """The Audit tab's gate/validation/exec/hook-run fetches must be keyed on
    the PINNED version's run id, not the live/root run's."""
    root, members = a_revised_family(page)
    v2 = members[1]["id"]
    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("iss609-audit-v2", "When I cold-load the Audit tab pinned to v2"):
        page.goto(f"/runs/{root}/versions/2/audit")
        expect(page.locator(RD.LANE)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    fetched_v2_gate_events = any(
        f"/api/runs/{v2}/gate-events" in u for u in requests
    )

    assert fetched_v2_gate_events, (
        f"Audit tab pinned to v2 never fetched the pinned revision's own "
        f"gate-events ({v2}) — requests seen: {requests}"
    )

    # Deliberately NOT `assert not fetched_root_gate_events`, for the same reason
    # the matching assertion was dropped from ISS-230's
    # test_tab_switch_keeps_fetching_the_pinned_revisions_run_id: a pinned deep
    # link MOUNTS THE FAMILY ROOT in the shell, so the shell issues the root's
    # own fetches — gate-events included — regardless of what is pinned.
    #
    # It is also a race rather than a check. This assertion passed only while the
    # root's gate-events request happened to land outside the settle window;
    # removing two seeded chat events from the family shortened transcript
    # seeding, the root's request moved earlier, and it began failing on every
    # run without a line of product code changing. What ISS-609 actually claims —
    # that the PINNED revision's own audit data is fetched — is the assertion
    # above, and it fails whenever the pin is ignored.

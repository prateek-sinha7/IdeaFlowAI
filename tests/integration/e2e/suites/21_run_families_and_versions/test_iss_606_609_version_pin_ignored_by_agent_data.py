"""ISS-606 / ISS-609 — BUG-20260829-135100-runs-id-versions.

The Steps tab's pipeline summary/agent list and the Audit tab's own fetches
both ignore the URL's version pin, unlike `effUserStoryContent` et al. (the
Preview-tab content, already version-aware per FIX-334).

Same 2-member family as ISS-230's suite file (see that file's own docstring):
root run `77f74563-fa19-4f0b-84fd-d0224f89a54a` (v1, 5 agents, 3164.1s),
revision `ef86e750-bbcd-404f-855a-fb0d5bee63f5` (v2, 2 agents, 371s) — ground
truth confirmed via `GET /api/runs/{id}`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD

ROOT_RUN_ID = "77f74563-fa19-4f0b-84fd-d0224f89a54a"
V2_RUN_ID = "ef86e750-bbcd-404f-855a-fb0d5bee63f5"


@pytest.mark.issue("ISS-606")
def test_steps_tab_shows_the_pinned_versions_own_agent_count(page, shot):
    """The Steps tab's "N / N agents" summary must reflect the PINNED
    version's own agent_count (v1=5, v2=2), not always the root run's."""
    page.goto(f"/runs/{ROOT_RUN_ID}/versions/2/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.get_by_text("agents").first.wait_for(state="visible")
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("iss606-steps-v2", "When I cold-load the Steps tab pinned to v2"):
        body = page.evaluate("() => document.body.innerText")

    import re

    m = re.search(r"(\d+)\s*/\s*(\d+)\s*agents", body)
    assert m, f"could not find the agent-count summary in: {body[:300]!r}"
    assert m.group(1) == "2" and m.group(2) == "2", (
        f"Steps tab pinned to v2 (agent_count=2) shows {m.group(0)!r} — "
        "this is the ROOT run's agent count (5), not the pinned version's own"
    )


@pytest.mark.issue("ISS-609")
def test_audit_tab_fetches_the_pinned_versions_own_run_id(page, shot):
    """The Audit tab's gate/validation/exec/hook-run fetches must be keyed on
    the PINNED version's run id, not the live/root run's."""
    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("iss609-audit-v2", "When I cold-load the Audit tab pinned to v2"):
        page.goto(f"/runs/{ROOT_RUN_ID}/versions/2/audit")
        expect(page.locator(RD.LANE)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    fetched_v2_gate_events = any(
        f"/api/runs/{V2_RUN_ID}/gate-events" in u for u in requests
    )
    fetched_root_gate_events = any(
        f"/api/runs/{ROOT_RUN_ID}/gate-events" in u for u in requests
    )

    assert fetched_v2_gate_events, (
        f"Audit tab pinned to v2 never fetched the pinned revision's own "
        f"gate-events ({V2_RUN_ID}) — requests seen: {requests}"
    )
    assert not fetched_root_gate_events, (
        f"Audit tab pinned to v2 fetched the ROOT run's gate-events "
        f"({ROOT_RUN_ID}) instead of the pinned revision's"
    )

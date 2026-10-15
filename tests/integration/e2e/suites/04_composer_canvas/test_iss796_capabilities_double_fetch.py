"""ISS-796, sibling of ISS-782 (QA-PS-036, `BUGS.md#qa-ps-036`).
`useAgentCapabilities` (`AgentsPopup.tsx:1525`) is a plain hook with no shared
cache across its own call sites — every caller gets its own
`useState`/`useEffect` pair. `CanvasView.tsx:304` already calls it once on
mount (comment there: "Lifted here ... so every CanvasNode's model pill
reads the SAME fetched catalog"), but its own child `CanvasConfigRail.tsx:162`
calls the same hook again, so opening any agent's config tab fires a second,
independent `GET /api/capabilities`.

See `.knowledge/cards/20260922-1825-ISS-796.md`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import composer as L


@pytest.mark.issue("ISS-796")
def test_opening_the_agent_config_tab_reuses_the_capabilities_fetch(page, shot):
    """ISS-796 — opening an agent's config tab on the canvas must not fire a
    second /api/capabilities request; CanvasView already fetched it once on
    mount and CanvasConfigRail should read the same shared result."""
    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url)
        if "/api/capabilities" in req.url
        else None,
    )

    page.goto("/workflows/ppt/canvas")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()
    expect(page.locator(L.BRIEF_NODE)).to_be_visible()
    L.wait_for_nodes(page, len(L.PPT_AGENT_IDS))
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    before = len(requests)

    with shot("rail-agent", 'When I click the rail tab "Agent" to open its config'):
        page.click(L.RAIL_AGENT)
        expect(page.locator(L.AGENT_NAME)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    after = len(requests)

    assert after == before, (
        f"ISS-796: opening the agent config tab fired "
        f"{after - before} new /api/capabilities request(s) "
        f"(CanvasView already fetched it once on mount, CanvasConfigRail "
        f"should reuse it, not refetch): {requests}"
    )

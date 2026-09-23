"""QA-PS-059 (`BUGS.md#qa-ps-059`) — ISS-812 / ISS-839.

ISS-812 validated (2026-09-22, 3/3 cold starts) that opening the Library
agent detail's Config tab fired `GET /api/capabilities` twice:
`ConfigLeversFlat` (`AgentsPopup.tsx:1717`) has exactly one call site of
`useAgentCapabilities` (`:1730`), so a single request is what the component
tree implies. Root cause traced to `useAgentCapabilities`
(`AgentsPopup.tsx:1530`) calling `getCapabilities` with no in-flight/shared
cache, so React 18 dev StrictMode's mount-effect double-invoke fired it
twice.

ISS-839 (2026-09-22, 20:22) confirmed the fix landed: `getCapabilities`
(`frontend/src/lib/api.ts:1815-1822`) now returns
`cachedGet("/api/capabilities", token)` (FIX-617), verified generically by
`frontend/src/lib/api.sharedGetCache.test.ts`. ISS-839's own "TEST COVERAGE"
section flagged that no e2e case targets the Library Config tab
specifically (only ISS-796's composer surface has one) and left that gap
for the test-writer phase — this is that test.

This is a REGRESSION GUARD, not a red-then-green proof: live re-verification
this session (lane7, cold nav to `/library/agents/material-analyzer`,
Config tab clicked) shows `/api/capabilities` firing exactly once, matching
`api.sharedGetCache.test.ts`'s already-passing result. No `xfail` marker —
the defect does not reproduce against the current source tree.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import library as L


@pytest.mark.issue("ISS-812")
@pytest.mark.issue("ISS-839")
def test_opening_the_library_config_tab_fetches_capabilities_once(page):
    """ISS-812/ISS-839 — opening the Library agent detail Config tab must
    fire /api/capabilities exactly once; ConfigLeversFlat has one call site
    of useAgentCapabilities so a single request is what the tree implies."""
    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url)
        if "/api/capabilities" in req.url
        else None,
    )

    page.goto(f"/library/agents/{L.AGENT_SLUG}")
    drawer = page.locator(L.AGENT_DRAWER)
    expect(drawer).to_be_visible()
    drawer.get_by_role("tab", name="Config", exact=True).click()
    page.wait_for_timeout(1500)

    assert len(requests) == 1, (
        f"expected exactly 1 /api/capabilities request on Config-tab open, "
        f"got {len(requests)}: {requests}"
    )

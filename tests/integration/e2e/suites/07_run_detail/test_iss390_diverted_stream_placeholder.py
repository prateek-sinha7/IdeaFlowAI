"""ISS-390 (root, supersedes ISS-282) — a diverted run's Preview tab must not
show the generic live-streaming "Output will appear here" placeholder.

Root cause is two gates in series, both required for a fix:
  1. `frontend/src/app/[...view]/page.tsx:3035-3041` narrows
     `reopenedRunStatus` to "failed"/"cancelled"/"degraded" only, so it is
     always `undefined` for a diverted run.
  2. `PreviewPanel.tsx:696-699`'s own `reopenFailureSignal` check
     independently omits "diverted" from the same triad (this half was
     originally filed as ISS-282, now superseded by ISS-390).

The run is discovered rather than pinned: any `diverted` run (terminal, e.g.
an "Ex A4 Human Divert"). The pinned one went with a reseed and the page then
had nothing to render, so this passed vacuously (ISS-1188).

Contrast (not asserted here, documented in the card): the cancelled run
28a318c9-d207-4e2a-bce8-c3260d4c57f2 already shows a status-aware message
("This run was cancelled...") on the identical route, proving the mechanism
exists and simply omits "diverted".
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api


def _a_diverted_run(page) -> str:
    page.goto("/dashboard")
    rows = api.json_body(page, "GET", "/api/runs?limit=100&status_filter=diverted")
    if not rows:
        pytest.skip("no run in this history diverted")
    return rows[0]["id"]


@pytest.mark.issue("ISS-390")
def test_diverted_run_preview_is_not_the_live_waiting_placeholder(page):
    """A permanently-terminal diverted run's Preview tab must show a
    state-aware terminal message, not the neutral live-streaming placeholder
    that implies output is still forthcoming."""
    run_id = _a_diverted_run(page)
    page.goto(f"/runs/{run_id}/stream")
    page.wait_for_load_state("networkidle")

    preview_tab = page.locator('[data-testid="tab-preview"]')
    expect(preview_tab).to_have_attribute("aria-selected", "true")

    # The live-streaming neutral placeholder must not be shown for a run that
    # will never produce further output.
    expect(page.get_by_text("Output will appear here")).not_to_be_visible()

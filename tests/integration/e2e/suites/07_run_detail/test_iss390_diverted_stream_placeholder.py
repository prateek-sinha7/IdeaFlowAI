"""ISS-390 (root, supersedes ISS-282) — a diverted run's Preview tab must not
show the generic live-streaming "Output will appear here" placeholder.

Root cause is two gates in series, both required for a fix:
  1. `frontend/src/app/[...view]/page.tsx:3035-3041` narrows
     `reopenedRunStatus` to "failed"/"cancelled"/"degraded" only, so it is
     always `undefined` for a diverted run.
  2. `PreviewPanel.tsx:696-699`'s own `reopenFailureSignal` check
     independently omits "diverted" from the same triad (this half was
     originally filed as ISS-282, now superseded by ISS-390).

Run used: 940ca699-b21b-4666-8e44-3370a08a4561 ("Ex A4 Human Divert"),
status `diverted`, `completed_at` set (terminal), `output`/
`deliverable_filename` both null, only 2/3 agents ran.

Contrast (not asserted here, documented in the card): the cancelled run
a8dfa959-e233-4ddf-87ce-d9a942cefde3 already shows a status-aware message
("This run was cancelled...") on the identical route, proving the mechanism
exists and simply omits "diverted".
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

DIVERTED_RUN = "940ca699-b21b-4666-8e44-3370a08a4561"


@pytest.mark.issue("ISS-390")
def test_diverted_run_preview_is_not_the_live_waiting_placeholder(page):
    """A permanently-terminal diverted run's Preview tab must show a
    state-aware terminal message, not the neutral live-streaming placeholder
    that implies output is still forthcoming."""
    page.goto(f"/runs/{DIVERTED_RUN}/stream")
    page.wait_for_load_state("networkidle")

    preview_tab = page.locator('[data-testid="tab-preview"]')
    expect(preview_tab).to_have_attribute("aria-selected", "true")

    # The live-streaming neutral placeholder must not be shown for a run that
    # will never produce further output.
    expect(page.get_by_text("Output will appear here")).not_to_be_visible()

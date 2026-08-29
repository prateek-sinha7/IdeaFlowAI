"""ISS-356 — Diverted run's Workspace tab falsely claims "the deliverable is
still on the Preview and Files tabs" when no deliverable was ever produced.

Root cause: `frontend/src/components/results/SandboxTab.tsx:1037-1043` — the
`expired` branch hardcodes "The deliverable is still on the Preview and Files
tabs" with no check on the run's `output`/`deliverable_filename`/status.
`SandboxTabProps` (`:842-849`) receives only `runId`/`agentNameById`, nothing
describing deliverable presence, even though `PreviewPanel.tsx` (the sole
render call site, `:1406`) already computes `hasContent`/`isDivertedTerminal`/
`terminalFailureNoDeliverable`/`isCancelledTerminal` for this exact pattern.

Run used: 940ca699-b21b-4666-8e44-3370a08a4561, status `diverted`,
confirmed via `GET /api/runs/940ca699-...`: `output: null`,
`deliverable_filename: null`; confirmed via `GET /api/runs/940ca699-.../sandbox`:
`expired: true` (workspace already TTL-swept in this environment).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

DIVERTED_RUN_NO_DELIVERABLE = "940ca699-b21b-4666-8e44-3370a08a4561"


@pytest.mark.issue("ISS-356")
def test_expired_workspace_does_not_claim_deliverable_exists_when_none_was_produced(page):
    """A diverted run that never produced a deliverable must not have its
    expired-workspace empty state assert one is available on Preview/Files."""
    page.goto(f"/runs/{DIVERTED_RUN_NO_DELIVERABLE}/workspace")

    expect(page.get_by_text("Workspace expired")).to_be_visible(timeout=15000)
    expect(
        page.get_by_text("The deliverable is still on the Preview and Files tabs")
    ).not_to_be_visible()

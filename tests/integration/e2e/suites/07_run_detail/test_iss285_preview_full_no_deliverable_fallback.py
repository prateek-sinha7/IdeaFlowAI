"""ISS-285 — `/runs/{id}/preview/full` on a failed run with no deliverable
must not silently render the Audit tab in Preview's place.

`reopenTabFor` (`frontend/src/app/[...view]/page.tsx:228-244`) has no case for
the `run-preview-full` screen, so it falls through to `undefined` and neither
call site ever tells `PreviewPanel` this route's whole purpose is forcing
Preview open. `PreviewPanel`'s state-keyed default-tab effect then maps a
terminal-failed-no-deliverable run straight to `"audit"` with no banner
explaining the substitution — a materially different tab (a 32-record
governance/security log) is rendered in place of the requested Preview with
zero visual or textual indication that a fallback occurred.

The run is discovered rather than pinned: the pinned one went with a reseed
and the page then had nothing to render, so this passed vacuously (ISS-1188).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api


def _a_failed_run_with_no_deliverable(page) -> str:
    """A failed run that produced nothing: no output and no deliverable file."""
    page.goto("/dashboard")
    for row in api.json_body(page, "GET", "/api/runs?limit=100&status_filter=failed"):
        run = api.json_body(page, "GET", f"/api/runs/{row['id']}")
        if not (run.get("output") or "").strip() and not run.get("deliverable_filename"):
            return row["id"]
    pytest.skip("no failed run in this history is without a deliverable")


@pytest.mark.issue("ISS-285")
def test_preview_full_does_not_silently_substitute_audit(page):
    """Requesting the dedicated Preview route for a failed run with no
    deliverable must not land on the unrelated Audit tab with no
    explanation — either no tab is selected (mirroring the plain /runs/{id}
    route for the same run) or an explicit fallback message is shown."""
    run_id = _a_failed_run_with_no_deliverable(page)
    page.goto(f"/runs/{run_id}/preview/full")
    page.wait_for_load_state("networkidle")

    audit_tab = page.locator('[data-testid="tab-audit"]')
    expect(audit_tab).not_to_have_attribute("aria-selected", "true")

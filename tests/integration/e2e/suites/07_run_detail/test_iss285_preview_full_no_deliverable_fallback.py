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

Run used: 826d09f0-21b0-4b8f-a79f-843fc5c82adb (status `failed`, confirmed via
`GET /api/runs/826d09f0-...`; no Preview tab in its tablist).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

FAILED_RUN_NO_DELIVERABLE = "826d09f0-21b0-4b8f-a79f-843fc5c82adb"


@pytest.mark.issue("ISS-285")
def test_preview_full_does_not_silently_substitute_audit(page):
    """Requesting the dedicated Preview route for a failed run with no
    deliverable must not land on the unrelated Audit tab with no
    explanation — either no tab is selected (mirroring the plain /runs/{id}
    route for the same run) or an explicit fallback message is shown."""
    page.goto(f"/runs/{FAILED_RUN_NO_DELIVERABLE}/preview/full")
    page.wait_for_load_state("networkidle")

    audit_tab = page.locator('[data-testid="tab-audit"]')
    expect(audit_tab).not_to_have_attribute("aria-selected", "true")

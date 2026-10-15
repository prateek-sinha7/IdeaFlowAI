"""ISS-313 — Preview toolbar "Download the deliverable" button must not stay
permanently disabled on a completed run whose deliverable is fully rendered,
just because the backend never populated `deliverable_filename`.

Root cause (confirmed, see ISS-313): `WorkflowCompiler._compile_deliverable`
(`backend/agents/workflows/compiler.py:1446-1451`) copies `deliverable.name`
verbatim from the manifest with no fallback when the manifest declares
`deliverable.strategy` without `deliverable.name` — unlike `mimetype`, which
gets a computed per-strategy default. `ex_playwright_smoke_test/workflow.yaml`
is exactly such a manifest, and it is `user_launchable: true`, so any run of
it completes with `deliverable_mimetype` set but `deliverable_filename` null.
`PreviewPanel.tsx`'s toolbar-download effect gates the button on that name
resolving in the workspace listing, so it never enables.

The run is discovered rather than pinned: the pinned one went with a reseed
and the page rendered a 404 (ISS-1188).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api


def _a_completed_run_with_no_deliverable_filename(page) -> str:
    """A completed run with a deliverable mimetype but no `deliverable_filename`."""
    page.goto("/dashboard")
    for row in api.json_body(page, "GET", "/api/runs?limit=100&status_filter=completed"):
        if row.get("deliverable_mimetype") and not row.get("deliverable_filename"):
            return row["id"]
    pytest.skip(
        "no completed run in this history has a deliverable but no "
        "deliverable_filename (e.g. an ex_playwright_smoke_test run)"
    )


@pytest.mark.issue("ISS-313")
def test_toolbar_download_enabled_when_deliverable_filename_missing(page):
    """A completed run with a fully rendered deliverable must offer a working
    toolbar Download button, even when the backend never wrote
    `deliverable_filename` for that run's manifest."""
    run_id = _a_completed_run_with_no_deliverable_filename(page)
    page.goto(f"/runs/{run_id}/stream")
    page.wait_for_load_state("networkidle")

    download_button = page.get_by_role(
        "button", name="Download the deliverable"
    )
    expect(download_button).to_be_visible()
    expect(download_button).to_be_enabled()

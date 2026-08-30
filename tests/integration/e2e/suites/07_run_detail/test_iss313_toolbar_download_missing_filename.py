"""ISS-313 — Preview toolbar "Download the deliverable" button must not stay
permanently disabled on a completed run whose deliverable is fully rendered,
just because the backend never populated `deliverable_filename`.

Root cause (confirmed, see ISS-313): `WorkflowCompiler._compile_deliverable`
(`backend/agents/workflows/compiler.py:1446-1451`) copies `deliverable.name`
verbatim from the manifest with no fallback when the manifest declares
`deliverable.strategy` without `deliverable.name` — unlike `mimetype`, which
gets a computed per-strategy default. `playwright_smoke_test/workflow.yaml`
is exactly such a manifest, and it is `user_launchable: true`, so any run of
it completes with `deliverable_mimetype` set but `deliverable_filename` null.
`PreviewPanel.tsx`'s toolbar-download effect gates the button on that name
resolving in the workspace listing, so it never enables.

Run used: 649e56cf-ce0f-4a0f-91fa-4e75a971a980 (Playwright Smoke Test,
status `completed`, confirmed via `GET /api/runs/649e56cf-...`:
`deliverable_mimetype: "application/zip"`, `deliverable_filename: null`).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

RUN_WITH_NULL_DELIVERABLE_FILENAME = "649e56cf-ce0f-4a0f-91fa-4e75a971a980"


@pytest.mark.issue("ISS-313")
def test_toolbar_download_enabled_when_deliverable_filename_missing(page):
    """A completed run with a fully rendered deliverable must offer a working
    toolbar Download button, even when the backend never wrote
    `deliverable_filename` for that run's manifest."""
    page.goto(f"/runs/{RUN_WITH_NULL_DELIVERABLE_FILENAME}/stream")
    page.wait_for_load_state("networkidle")

    download_button = page.get_by_role(
        "button", name="Download the deliverable"
    )
    expect(download_button).to_be_visible()
    expect(download_button).to_be_enabled()

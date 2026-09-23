"""ISS-273 — a nonexistent/malformed workflow id on `/workflows/{id}/run`
must not silently render the Dashboard under the unchanged bogus URL.

`frontend/src/app/[...view]/page.tsx`'s workflow-run cold-mount catch
(`:3692-3707`) sets `workflowRunFailed` on a 404 from
`GET /api/user-workflows/{id}`, but the render gate (`:3785-3791`) only uses
that flag to stop the loading-`null` return — it never calls `notFound()`,
unlike its 3 sibling identity-fetch-failure gates in the same file. Execution
falls through to the unconditional `<DashboardLayout />` return, so the full
authenticated Dashboard catalog renders while `location.href` stays on the
original, unresolvable `/workflows/{id}/run` path indefinitely.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

NONEXISTENT_UUID = "00000000-0000-0000-0000-000000000000"
MALFORMED_ID = "not-a-valid-uuid"


@pytest.mark.issue("ISS-273")
def test_nonexistent_workflow_id_run_shows_not_found_not_dashboard(page):
    """A well-formed but nonexistent workflow id must not fall through to
    the Dashboard catalog while the URL stays on the bogus /run path."""
    page.goto(f"/workflows/{NONEXISTENT_UUID}/run")
    page.wait_for_load_state("networkidle")

    assert f"/workflows/{NONEXISTENT_UUID}/run" in page.url, (
        "test setup: expected to still be on the requested /run URL"
    )

    heading = page.locator("h1")
    expect(heading).not_to_have_text("What would you like to build today?")


@pytest.mark.issue("ISS-273")
def test_malformed_workflow_id_run_shows_not_found_not_dashboard(page):
    """A syntactically malformed workflow id must produce the same
    not-found behaviour as a nonexistent-but-well-formed one, not the
    Dashboard catalog under the unchanged bogus URL."""
    page.goto(f"/workflows/{MALFORMED_ID}/run")
    page.wait_for_load_state("networkidle")

    assert f"/workflows/{MALFORMED_ID}/run" in page.url, (
        "test setup: expected to still be on the requested /run URL"
    )

    heading = page.locator("h1")
    expect(heading).not_to_have_text("What would you like to build today?")

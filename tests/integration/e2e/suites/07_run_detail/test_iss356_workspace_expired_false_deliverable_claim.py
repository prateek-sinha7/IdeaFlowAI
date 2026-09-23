"""ISS-356 — the expired-Workspace empty state must not claim a deliverable is
waiting on the Preview and Files tabs when the run never produced one.

The `expired` branch used to hardcode "The deliverable is still on the Preview
and Files tabs" with no check on the run's output, so a diverted or failed run
that produced nothing still told the user to go and find it. The sentence is
now gated on `hasDeliverable` (SandboxTab.tsx), and this pins that gate.

`expired` is the backend's own directory-existence flag from
`GET /api/runs/{id}/sandbox` — run workspaces are swept after a retention
period, so WHICH runs are expired changes with the clock and cannot be named in
advance. This used to pin `a40d0f2b-901e-4847-85ba-c205f4a41f16`; that run still
exists but its workspace has not been swept, so the expired branch never
rendered and the scenario failed looking for "Workspace expired" — a missing
precondition reported as a missing element.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api, settings
from framework.locators import run_history as RH

DELIVERABLE_CLAIM = "The deliverable is still on the Preview and Files tabs"


def _a_run_with_an_expired_workspace(page) -> tuple[str, bool]:
    """A run whose sandbox reports `expired`, plus whether it HAS a deliverable.

    Both halves matter: the claim is correct for a run that produced one and
    wrong only for a run that did not, so the test has to know which it found.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    for index in range(len(RH.rows(page))):
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.locator(RH.ROW).nth(index).click()
        page.wait_for_url(lambda url: "/runs/" in url)
        run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]
        sandbox = api.json_body(page, "GET", f"/api/runs/{run_id}/sandbox")
        if not sandbox.get("expired"):
            continue
        run = api.json_body(page, "GET", f"/api/runs/{run_id}")
        has_deliverable = bool((run.get("output") or "").strip()) or bool(
            run.get("deliverable_filename")
        )
        return run_id, has_deliverable
    pytest.skip(
        "no run in this history has an expired workspace, so the expired empty "
        "state never renders — workspaces are swept on a retention timer, not "
        "on demand"
    )


@pytest.mark.issue("ISS-356")
def test_expired_workspace_does_not_claim_deliverable_exists_when_none_was_produced(page):
    """A run that never produced a deliverable must not have its
    expired-workspace empty state assert one is available on Preview/Files."""
    run_id, has_deliverable = _a_run_with_an_expired_workspace(page)

    page.goto(f"/runs/{run_id}/workspace")
    expect(page.get_by_text("Workspace expired")).to_be_visible(timeout=15000)
    page.wait_for_timeout(settings.SETTLE_MS)

    claim = page.get_by_text(DELIVERABLE_CLAIM)
    if has_deliverable:
        # The sentence is TRUE for this run, so its presence is correct — assert
        # that rather than skipping, so the gate is pinned in both directions.
        expect(claim).to_be_visible()
    else:
        expect(claim).not_to_be_visible()

"""BUG-20260828-051530-create — ISS-225 / ISS-254 / ISS-263.

`selectionsRef` in `IdeaInputPage.tsx` is seeded only from `cleanSelections`
and mutated only by explicit user edits — never merged with
`manifestSelections`, the gates a manifest's own steps declare. "Save as my
version" (`handleSaveAsOverride`) serializes `selectionsRef.current` straight
into the outgoing `manifest:`, so an untouched step with `route:` goes out
with `gates: []` and the backend's R-03 cross-field check 422s it (ISS-225),
identically on every other built-in whose manifest declares `route:`
(ISS-254). "Save workflow" reads the same empty ref but sends `selections:`
instead of `manifest:`, which short-circuits validation entirely on an empty
map — so it reports success while silently dropping the routed step's
gates/route from what gets persisted (ISS-263).
"""

from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L

SAVE_CONFIRM = 'button:text-is("Save")'

# The four other shipped examples whose own workflow.yaml declares `route:`
# on a step (grep -rl "route:" backend/agents/workflows/*/workflow.yaml,
# minus ex_A4_human_divert itself which ISS-225 covers directly).
OTHER_ROUTE_EXAMPLES = [
    "ex_A1_loop",
    "ex_A2_branch",
    "ex_A3_divert",
    "ex_A4_human_gate",
]


@pytest.mark.issue("ISS-225")
def test_save_as_my_version_succeeds_on_unmodified_route_declaring_example(page, shot):
    """ISS-225 — an unmodified seeded example whose own manifest already
    satisfies R-03 must save, since the user made no gate-related edits."""
    with shot("panel", 'When I cold-load "/create/ex_A4_human_divert"'):
        page.goto("/create/ex_A4_human_divert")
        page.fill(L.BRIEF, "Test brief for ex_A4_human_divert save")
        expect(page.locator(L.SAVE_AS_MY_VERSION)).to_be_enabled(timeout=15_000)

    with shot("saved", 'And I click "Save as my version"'):
        with page.expect_response(re.compile(r"/api/user-workflows$")) as resp_info:
            page.click(L.SAVE_AS_MY_VERSION)
        response = resp_info.value

    assert response.status < 400, (
        f"Save as my version failed on an unmodified seeded example: "
        f"{response.status} {response.text()[:300]}"
    )


@pytest.mark.issue("ISS-254")
@pytest.mark.parametrize("workflow_id", OTHER_ROUTE_EXAMPLES)
def test_save_as_my_version_succeeds_on_every_route_declaring_example(page, shot, workflow_id):
    """ISS-254 — the same R-03 422 ISS-225 documented for ex_A4_human_divert
    fires identically on every other built-in whose manifest declares
    `route:` on a step, since the broken code path is shared, not per-example."""
    with shot(f"panel-{workflow_id}", f'When I cold-load "/create/{workflow_id}"'):
        page.goto(f"/create/{workflow_id}")
        page.fill(L.BRIEF, f"Test brief for {workflow_id} save")
        expect(page.locator(L.SAVE_AS_MY_VERSION)).to_be_enabled(timeout=15_000)

    with shot("saved", 'And I click "Save as my version"'):
        with page.expect_response(re.compile(r"/api/user-workflows$")) as resp_info:
            page.click(L.SAVE_AS_MY_VERSION)
        response = resp_info.value

    assert response.status < 400, (
        f"Save as my version failed on {workflow_id}: "
        f"{response.status} {response.text()[:300]}"
    )


@pytest.mark.issue("ISS-263")
@pytest.mark.destructive
@pytest.mark.xfail(reason="ISS-263 unfixed", strict=True)
def test_save_workflow_captures_the_routed_steps_gates(page, shot):
    """ISS-263 — "Save workflow" must not report success while silently
    dropping a routed step's gates just because the user never touched the
    Advanced popup. Either it captures the route/gates faithfully, or it
    refuses the save the way "Save as my version" does — it must not be
    silently incomplete."""
    with shot("panel", 'When I cold-load "/create/ex_A4_human_divert"'):
        page.goto("/create/ex_A4_human_divert")
        page.fill(L.BRIEF, "Test brief for ex_A4_human_divert Save workflow")
        expect(page.locator(L.SAVE_WORKFLOW)).to_be_enabled(timeout=15_000)
        page.click(L.SAVE_WORKFLOW)

    name = f"ISS-263 probe {uuid.uuid4().hex[:8]}"
    with shot("save-modal", 'When I name and confirm "Save workflow"'):
        page.fill("#nwm-name", name)
        with page.expect_response(re.compile(r"/api/user-workflows$")) as resp_info:
            page.click(SAVE_CONFIRM)
        created = resp_info.value

    assert created.status < 400, f"Save workflow failed outright: {created.status}"
    body = created.json()
    selections = body.get("selections") or {}

    assert any(
        "route" in (sel or {}) or "gates" in (sel or {})
        for sel in selections.values()
    ), (
        f"Save workflow silently dropped the routed step's route/gates — "
        f"persisted selections carry no trace of them: {selections!r}"
    )

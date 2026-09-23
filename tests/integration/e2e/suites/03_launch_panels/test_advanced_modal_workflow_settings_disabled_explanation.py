"""ISS-246 — Advanced modal's Workflow-tab controls are permanently disabled
for built-in launches with zero UI affordance explaining why.

`LaunchWizard.tsx` never forwards `onRunConfigChange`/`onCapabilitiesChange`
for a built-in launch, so `CanvasView.tsx` disables all six Workflow-tab
controls (Smart planning, Confirm requirements first, Deliverable strategy,
Output file name, Output format, Internet access) via a bare `disabled`
attribute — no lock icon, no tooltip, no `title`, no explanatory copy. The
sibling "Execute commands" toggle in `CanvasConfigRail.tsx` disables the same
way but pairs it with visible `<InfoHint>` copy, proving the app already has
this pattern — just not applied here.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L

# Every disabled Workflow-tab control read via direct DOM property, per the
# card's own repro (title/aria-describedby are the accessible-name channels a
# native disabled control would use to explain itself).
WORKFLOW_TAB_DISABLED_READ = """() => {
    const switches = Array.from(document.querySelectorAll('[role="switch"]'));
    const controls = [
        ...switches,
        document.querySelector('select[name=deliverable-strategy]'),
        document.querySelector('select[name=output-format]'),
        document.querySelector('input[name=output-filename]'),
    ].filter(Boolean);
    return controls.map(el => ({
        disabled: el.disabled,
        title: el.title || '',
        ariaDescribedBy: el.getAttribute('aria-describedby') || '',
    }));
}"""


@pytest.mark.issue("ISS-246")
def test_disabled_workflow_settings_carry_an_explanation(page, shot):
    """A disabled Workflow-tab control must explain why via title/aria-describedby
    (or equivalent visible copy) — not render disabled with zero affordance."""
    page.goto("/create/user-stories")
    expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()

    with shot("advanced-modal", 'When I open "Advanced N agents" with no node selected'):
        page.click(L.ADVANCED)
        expect(page.locator(L.CANVAS_VIEW)).to_be_visible()

    controls = page.evaluate(WORKFLOW_TAB_DISABLED_READ)
    assert controls, "expected the six Workflow-tab controls to be present in the DOM"

    disabled_without_reason = [
        c for c in controls
        if c["disabled"] and not c["title"] and not c["ariaDescribedBy"]
    ]
    assert not disabled_without_reason, (
        "ISS-246: these Workflow-tab controls are disabled with no title/"
        f"aria-describedby explaining why: {disabled_without_reason}"
    )

"""ISS-321 — `/create/<type>` performs no client-side tier gating at all.

The dashboard catalog correctly disables the "Build an interactive prototype"
card for a basic-tier account with a "Requires Pro plan" lock badge. But
`/create/prototype` itself (`[...view]/page.tsx`'s `wizardMode` branch) never
calls `canRunPipeline`/`can_run_pipeline` before rendering `<LaunchWizard>`, so
a basic-tier session reaching the route directly gets the identical,
fully-interactive wizard a Pro/Enterprise account gets — brief textarea,
template gallery, and (after typing a brief) an enabled "Continue" button.
Nothing in the flow indicates the account is not entitled.

Backend launch endpoints DO still enforce `can_run_pipeline` at run creation
(`run_commands.py::_require_tier_entitlement`, covered by
`test_theme_and_tiers.py::test_entitlement_is_enforced_by_the_backend_not_only_the_badge`)
so this is a client-side-only gap.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L

BRIEF_TEXT = "Build a test app with enough characters to satisfy validation"


@pytest.mark.issue("ISS-321")
@pytest.mark.role("basic")
def test_basic_tier_cannot_reach_submit_ready_prototype_wizard(page, shot):
    """A basic-tier session navigating directly to /create/prototype (a
    deliverable its own /settings/usage page says it does not have) must not
    reach a submit-ready wizard — it should see the same locked/upgrade
    state the dashboard catalog card already shows for this tier, not an
    enabled Continue button."""
    with shot("prototype-basic", 'When I cold-load "/create/prototype" as basic'):
        page.goto("/create/prototype")

    with shot("brief-filled", "And I type a full brief"):
        page.fill(L.BRIEF, BRIEF_TEXT)

    continue_button = page.get_by_role("button", name="Continue")
    expect(continue_button).to_be_disabled()

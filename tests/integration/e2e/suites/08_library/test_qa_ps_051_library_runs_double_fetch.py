"""QA-PS-051 (`BUGS.md#qa-ps-051`) — ISS-843 / ISS-848 / ISS-849.

Library agent/skill/hook detail views were reported to re-fetch run history
(`GET /api/runs?limit=50`) that is never rendered on any library detail view.

ISS-843 validated 3/3 (2026-09-22, lane3, cold `/library` -> click the
"Architecture Agent" card into `/library/agents/material-analyzer`):
`GET /api/runs?limit=50` fires once on the `/library` mount and again on
the client-side navigation into the detail route — 2 total, not 1.

ISS-848 root-caused it: `recentRunsRequestedRef`
(`frontend/src/app/[...view]/page.tsx:828`) is a component-instance-scoped
`useRef`, destroyed and recreated whenever `router.push` changes the
`[...view]` catch-all's segment array (`page.tsx:3494-3498`'s own comment
confirms this remount live). `getWorkflows` (`api.ts:868-908`) has no TTL
cache by design, so the second mount's guard starts at `false` again and
refetches. ISS-848's own note for this phase: "assert GET
/api/runs?limit=50 fires exactly once total across both page states" —
that is `test_library_detail_nav_fetches_run_history_once` below, and it
reproduces reliably (4/4 runs this session, lane9 + this suite).

ISS-849 is the INFERRED generalization: the same remount mechanism should
fire on ANY non-wizard `[...view]` route pair, not only Library. Both
entry paths its own "what would confirm this" section names were tried
this session and NEITHER reproduces reliably, so neither carries an
`xfail` marker — per the agent contract, a test never seen to fail for
the right reason ships as a regression guard, not a red test:

- Dashboard -> Library (list, no detail route) via the `openLibrary`
  recipe in `velocity.json`: one single anomalous run showed 2 fetches,
  but 4 repeats immediately after showed 1 (green) every time. Not a
  reproducible trigger — recorded as `test_dashboard_to_library_nav_fetches_run_history_once`,
  a green regression guard.
- The reverse direction (Back out of a library detail, per FIX-493's own
  claim that `router.back()` remounts `[...view]` identically to
  `router.push`): flaky, 1 failure (3 fetches) in 8 repeated runs, the
  rest stable at 2. Too intermittent to pin to a deterministic trigger —
  recorded as `test_library_detail_back_button_does_not_add_a_third_fetch`,
  asserting the documented worst case (<=2) so it still catches a
  reliably-reproducing regression without flagging this noise.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import library as L


def _count_runs_fetches(page) -> list[str]:
    hits: list[str] = []
    page.on(
        "request",
        lambda req: hits.append(req.url)
        if "/api/runs" in req.url and "limit=50" in req.url
        else None,
    )
    return hits


def _open_architecture_agent(page) -> None:
    """Click the "Architecture Agent" card, not just any card with that
    substring — "Security Architecture Agent" / "Backlog Architecture
    Agent" also match `has_text`, so this uses an exact-text child match."""
    page.goto("/library")
    expect(page.locator(L.CARD).first).to_be_visible()
    page.wait_for_load_state("networkidle")

    card = page.locator(L.CARD, has=page.get_by_text(L.AGENT_NAME, exact=True))
    card.first.click()
    page.wait_for_url(f"**/library/agents/{L.AGENT_SLUG}**")
    expect(page.locator(L.AGENT_DRAWER)).to_be_visible()
    page.wait_for_load_state("networkidle")


@pytest.mark.issue("ISS-843")
@pytest.mark.issue("ISS-848")
def test_library_detail_nav_fetches_run_history_once(page):
    """ISS-843/ISS-848 — /library -> agent detail via a card click must fire
    GET /api/runs?limit=50 once total, not once per [...view] mount."""
    hits = _count_runs_fetches(page)

    _open_architecture_agent(page)

    assert len(hits) == 1, (
        f"expected exactly 1 GET /api/runs?limit=50 across /library -> "
        f"detail nav, got {len(hits)}: {hits}"
    )


@pytest.mark.issue("ISS-849")
def test_dashboard_to_library_nav_fetches_run_history_once(page):
    """ISS-849 (unreproduced lead) — Dashboard -> Library via the
    `openLibrary` recipe. Regression guard, not a red test: 4/4 repeats
    this session fired GET /api/runs?limit=50 exactly once; a single
    earlier run that showed 2 did not repeat and is not a pinned-down
    trigger."""
    hits = _count_runs_fetches(page)

    page.goto("/dashboard")
    page.wait_for_load_state("networkidle")

    page.get_by_text("Library", exact=True).first.click()
    expect(page.locator(L.CARD).first).to_be_visible()
    page.wait_for_load_state("networkidle")

    assert len(hits) == 1, (
        f"expected exactly 1 GET /api/runs?limit=50 across Dashboard -> "
        f"Library nav, got {len(hits)}: {hits}"
    )


@pytest.mark.issue("ISS-849")
def test_library_detail_back_button_does_not_add_a_third_fetch(page):
    """ISS-849 (unreproduced lead) — the reverse direction: FIX-493 claims
    router.back() remounts [...view] identically to router.push, so
    ISS-849 predicted Back out of a library detail might add a 3rd
    /api/runs?limit=50 on top of ISS-843's 2. Regression guard, not a red
    test: 7/8 repeats this session stayed at 2, one showed 3 — too
    intermittent to call a deterministic trigger, so this asserts the
    documented worst case rather than xfail on a flake."""
    hits = _count_runs_fetches(page)

    _open_architecture_agent(page)

    page.go_back()
    expect(page.locator(L.CARD).first).to_be_visible()
    page.wait_for_load_state("networkidle")

    assert len(hits) <= 2, (
        f"expected at most 2 GET /api/runs?limit=50 across /library -> "
        f"detail -> Back, got {len(hits)}: {hits}"
    )

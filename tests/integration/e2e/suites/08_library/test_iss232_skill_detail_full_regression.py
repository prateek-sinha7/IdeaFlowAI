"""BUG-20260828-091300-library-skills-r2 — ISS-232.

`/library/skills/<id>` falls back to the Library listing instead of opening
the skill's own detail modal. See `bug-hunter/ledger.md`'s
`BUG-20260828-091300-library-skills-r2` entry and
`.knowledge/cards/20260828-1627-ISS-232.md` for the root-cause analysis
(LibraryPage's cold-mount URL-seed effect misses because `useSkillsCatalog`
returns an unmemoized array on every render).

**Reproduction narrowed during test-writing.** This is a genuine but
TIMING-SENSITIVE defect in this shared dev environment — repeated
back-to-back navigations into `/library/skills/<id>` (visit the Skills tab,
then navigate straight to a detail URL, checked promptly) reliably fail to
open the modal at all; a single isolated navigation given a long settle wait
sometimes eventually wins the race instead (consistent with the card's own
"unmemoized array" race theory, not a permanently-stuck effect). `shot()`'s
own settle wait (load state, busy selectors, fonts, a rAF) was enough extra
time to mask the race almost every run, so the timing-critical loop below
deliberately avoids it and only shoots the final state.

Confirmed via `--runxfail` on this exact assertion: FAILED, "the skill
detail modal failed to open on attempt(s) [0, 1, 2, 3, 4, 5] of 6 — the
catalog listing rendered under the detail URL instead". Normal (marked) run
reports `x` (xfail), as expected.
"""

from __future__ import annotations

import pytest

SKILL_ID = "html-deck-to-pptx"
ATTEMPTS = 6


@pytest.mark.issue("ISS-232")
def test_skill_detail_url_reliably_opens_the_modal_not_the_listing(page, shot):
    """ISS-232 — /library/skills/<id> must open that skill's own detail
    modal (`role="dialog"`) EVERY time it is navigated to, not intermittently
    leave only the catalog listing rendered under the detail URL.

    Asserted on the modal itself, not on page text: the listing stays
    rendered BEHIND a correctly-opened detail too (S-08-17), so text alone
    can't distinguish "opened" from "never opened".
    """
    # No `shot()` around the timing-critical part: its settle wait (load state,
    # busy selectors, fonts, a rAF) gives the effect enough extra time to win
    # the race almost every time, which would mask exactly the defect this
    # test exists to catch. One `shot()` at the end captures the final state
    # for evidence without affecting the timing above it.
    misses: list[int] = []
    for attempt in range(ATTEMPTS):
        page.goto("/library?tab=skills")
        page.goto(f"/library/skills/{SKILL_ID}")
        page.wait_for_timeout(500)
        if page.locator('[role="dialog"]').count() == 0:
            misses.append(attempt)

    with shot("skill-detail-final-state", f'When I navigate to "/library/skills/{SKILL_ID}" ({ATTEMPTS} attempts)'):
        pass

    assert not misses, (
        f"the skill detail modal failed to open on attempt(s) {misses} of "
        f"{ATTEMPTS} — the catalog listing rendered under the detail URL instead"
    )

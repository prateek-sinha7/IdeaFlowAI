"""Proves BUG-20260828-011500-runs — Run History caps at 50 runs, mislabels the
capped count as the true total, and every consumer built on the capped `runs`
array (search, sort, delete bookkeeping, type chips) silently misbehaves once
an account's history exceeds that page.

Each test carries `@pytest.mark.issue("ISS-NNN")` and is `xfail(strict=True)`:
red today, and the moment the fix lands an unexpected pass turns loud so the
marker gets removed. See `.knowledge/cards/` for the ISS cards and
`bug-hunter/ledger.md`'s BUG-20260828-011500-runs entry for the root cause.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api
from framework.locators import run_history as L

from .test_run_history import open_history


def true_total(page) -> int:
    """The account's real run count, from the `X-Total-Count` header — never
    from the capped page body, which is exactly what this bug set is about."""
    res = api.full(page, "GET", "/api/runs?limit=1")
    assert res["status"] == 200, res
    return int(res["headers"]["x-total-count"])


@pytest.mark.issue("ISS-198")
@pytest.mark.xfail(reason="ISS-198 unfixed", strict=True)
def test_header_count_reflects_the_true_total_not_the_capped_page(page, shot):
    """ISS-198 — the "<N> runs" headline must show the account's real total,
    not merely the size of the first fetched page."""
    with shot("header-total", 'When I cold-load "/runs"'):
        open_history(page)

    total = true_total(page)
    assert total > 50, f"seed data no longer exceeds one page ({total}); test needs re-basing"
    assert L.total(page) == total, (
        f"the header reads {L.total(page)} runs but the account holds {total} — "
        "it is showing the capped first page, not the true total"
    )


@pytest.mark.issue("ISS-198")
@pytest.mark.xfail(reason="ISS-198 unfixed", strict=True)
def test_scrolling_to_the_bottom_loads_more_runs(page, shot):
    """ISS-198 — handleLoadMore exists and is correct but is wired to nothing;
    scrolling the list to its bottom must fetch and append the next page."""
    open_history(page)
    total = true_total(page)
    assert total > 50, f"seed data no longer exceeds one page ({total}); test needs re-basing"
    before = len(L.rows(page))
    assert before <= 50

    with shot("scroll-load-more", "When I scroll the run list to the bottom"):
        page.evaluate(
            """() => {
                const el = document.querySelector('.flex-1.overflow-y-auto');
                if (el) el.scrollTop = el.scrollHeight;
            }"""
        )
        page.wait_for_timeout(1500)

    assert len(L.rows(page)) > before, (
        "scrolling to the bottom fetched no additional rows — Load More is dead code"
    )


@pytest.mark.issue("ISS-207")
@pytest.mark.xfail(reason="ISS-207 unfixed", strict=True)
def test_search_finds_a_run_outside_the_first_fifty(page, shot):
    """ISS-207 — search must consider the account's full history, not just the
    50 most-recently-created runs currently loaded into the page."""
    open_history(page)

    import json as _json

    first_page_titles = " ".join(
        r["title"].lower() for r in _json.loads(api.full(page, "GET", "/api/runs?limit=50")["body"])
    )
    older = _json.loads(api.full(page, "GET", "/api/runs?limit=100&offset=150")["body"])
    assert older, "account does not hold 150+ runs; test needs re-basing"

    # A word that is distinctive to ONE older run and absent from the whole
    # loaded first page, so a match cannot be a coincidental hit on a row
    # that's already visible.
    word = None
    for run in older:
        for candidate in run["title"].split():
            if len(candidate) >= 5 and candidate.lower() not in first_page_titles:
                word = candidate
                break
        if word:
            break
    assert word, "no older-run word is distinctive from the first page; test needs re-basing"

    with shot("search-old-run", f'When I search for "{word}" from an old run'):
        page.fill(L.SEARCH, word)
        page.wait_for_timeout(600)

    matched = L.rows(page)
    assert any(word.lower() in label.lower() for label in matched), (
        f"searching for {word!r} (from a run outside the loaded 50) found nothing — "
        "search only considers the capped page, a false negative for a run that exists"
    )


def _total_tokens(run: dict) -> float | None:
    raw = run.get("token_usage")
    if not raw:
        return None
    try:
        return _json_module.loads(raw).get("total_tokens")
    except Exception:
        return None


import json as _json_module  # noqa: E402 — used by _total_tokens above


@pytest.mark.issue("ISS-208")
@pytest.mark.xfail(reason="ISS-208 unfixed", strict=True)
def test_tokens_sort_surfaces_the_true_highest_token_run(page, shot):
    """ISS-208 — "Tokens" sort must rank the account's actual highest-token
    run to the top, not merely the highest among the 50 most-recently-created
    rows. (Duration doesn't separate this seed data — the true-longest run is
    already recent enough to sit in the first page — but token usage does.)"""
    open_history(page)

    res = api.full(page, "GET", "/api/runs?limit=50")
    first_page = [r for r in _json_module.loads(res["body"])]
    max_first_page = max((t for r in first_page if (t := _total_tokens(r)) is not None), default=0)

    older_runs = []
    for offset in range(50, 300, 100):
        res = api.full(page, "GET", f"/api/runs?limit=100&offset={offset}")
        batch = _json_module.loads(res["body"])
        if not batch:
            break
        older_runs.extend(batch)
    older_scored = [(t, r) for r in older_runs if (t := _total_tokens(r)) is not None]
    assert older_scored, "no token-scored runs beyond the first page; test needs re-basing"
    highest_old_tokens, _ = max(older_scored, key=lambda pair: pair[0])
    assert highest_old_tokens > max_first_page, (
        "seed data's true highest-token run is already inside the first page; test needs re-basing"
    )

    with shot("sort-tokens", 'When I click "Tokens"'):
        page.get_by_role("button", name=L.SORTS["Tokens"], exact=True).click()
        page.wait_for_timeout(600)

    shown = [t for t in (L.tokens(text) for text in L.row_texts(page)) if t is not None]
    assert shown, "no row carries a token total to check the sort against"
    # L.tokens() parses a one-decimal-place K/M display, so allow a small
    # rounding margin rather than requiring an exact match.
    assert max(shown) >= highest_old_tokens * 0.99, (
        f"the account's true highest-token run ({highest_old_tokens} tokens) never appears "
        f"in the 'Tokens' sort — it only ranks the loaded 50 (max shown: {max(shown)})"
    )


# ISS-209 (totalRuns not decremented on delete) has no test here — see the
# suite's module docstring / the test-writer's NOTE. `totalRuns` (WorkflowHistory.tsx:158)
# has exactly three references, all inside `handleLoadMore` (:289-299), and
# `handleLoadMore` has zero triggers anywhere in the component (no button, no
# scroll listener, no IntersectionObserver — confirmed via
# `grep -n "scroll\|Intersection" WorkflowHistory.tsx`, no hits). The header and
# every filter chip read `runs.length`/`families.length`, never `totalRuns`
# (ISS-198's own root cause). So there is no DOM state, anywhere, that exposes
# `totalRuns` today — a delete-then-assert test against the rendered UI is
# green regardless of whether the fix ships, which proves nothing. This card
# is genuinely unreachable by an external test until ISS-198 wires a Load More
# trigger, exactly as the card's own "currently masked" note says.


def _bucket_of(run_type: str) -> str:
    """Mirrors `filterBucketFor` (RevisionFamilyView.tsx:100-103): strip only
    `_revision`, fold anything outside the four framework bases into custom."""
    base = run_type.replace("_revision", "")
    return base if base in {"user_stories", "ppt", "prototype", "app_builder"} else "custom"


@pytest.mark.issue("ISS-213")
@pytest.mark.xfail(reason="ISS-213 unfixed", strict=True)
def test_a_type_chips_count_reflects_the_true_account_total(page, shot):
    """ISS-213 — a type-filter chip's count must reflect the account's true
    per-type total, not just how many of that type sit inside the loaded
    50-row window. (This account's first page happens to include at least one
    run of every bucket, so the chip never fully vanishes here — but every
    bucket is still severely undercounted, which is the card's primary claim.)"""
    import json as _json

    open_history(page)

    older_runs = []
    for offset in range(50, 300, 100):
        res = api.full(page, "GET", f"/api/runs?limit=100&offset={offset}")
        batch = _json.loads(res["body"])
        if not batch:
            break
        older_runs.extend(batch)
    assert older_runs, "account does not exceed the first page; test needs re-basing"

    from collections import Counter

    true_counts = Counter(_bucket_of(r["type"]) for r in older_runs)
    label, param = max(L.TYPE_PARAMS.items(), key=lambda kv: true_counts[kv[1]])
    extra_beyond_page_one = true_counts[param]
    assert extra_beyond_page_one > 0, "no type has any hits beyond the first page; test needs re-basing"

    with shot("chip-undercount", f'When I read the "{label}" filter chip'):
        shown = L.chip_count(page, label)

    assert shown >= extra_beyond_page_one, (
        f"the {label!r} chip reads {shown}, but at least {extra_beyond_page_one} more runs of "
        "that type exist beyond the loaded 50-row window — the chip only tallies the capped page"
    )

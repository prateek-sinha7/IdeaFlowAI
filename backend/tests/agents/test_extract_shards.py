"""tests/agents/test_extract_shards.py — mechanical sharding in the extract tool.

Sharding is arithmetic: pages in, page ranges out. Doing it in the tool means the
planner reads a number instead of deriving one, and the same division cannot come
out differently on two runs of the same document.

Basis (SHARDING.md): usable = 120,000 safe budget - 15,000 measured agent reserve.
"""

from __future__ import annotations

import pytest

from app.agents.tools.file_extract_tools import (
    _SHARD_PAGE_CAP,
    _SHARD_RESERVE_TOKENS,
    _SHARD_SAFE_BUDGET,
    _build_shards,
)

USABLE = _SHARD_SAFE_BUDGET - _SHARD_RESERVE_TOKENS


def _pages(n: int, tokens: int) -> tuple[list[int], dict[int, int]]:
    return list(range(1, n + 1)), {i: tokens for i in range(1, n + 1)}


def test_a_small_document_is_one_shard():
    pages, tok = _pages(13, 700)
    shards = _build_shards("1-crimson", "pdf", pages, tok)
    assert len(shards) == 1
    assert shards[0]["id"] == "1-crimson-s01"
    assert shards[0]["pages"] == pages
    assert shards[0]["page_range"] == "1-13"
    assert shards[0]["est_tokens"] == 13 * 700
    assert shards[0]["out"] == "shards/1-crimson-s01/"
    assert shards[0]["over_budget"] is False


def test_it_splits_exactly_when_the_budget_runs_out():
    # 2,250 tok/page (a dense PDF) -> floor(105000/2250) = 46 pages per shard.
    per_page = 2_250
    assert USABLE // per_page == 46
    pages, tok = _pages(120, per_page)
    shards = _build_shards("big", "pdf", pages, tok)

    assert [len(s["pages"]) for s in shards] == [46, 46, 28]
    assert [s["page_range"] for s in shards] == ["1-46", "47-92", "93-120"]
    assert all(s["est_tokens"] <= USABLE for s in shards)


def test_every_page_lands_in_exactly_one_shard():
    pages, tok = _pages(200, 1_400)
    shards = _build_shards("x", "docx", pages, tok)
    seen = [p for s in shards for p in s["pages"]]
    assert seen == pages, "pages must be contiguous, ordered, and neither lost nor duplicated"


def test_ids_are_sequential_and_slug_scoped():
    pages, tok = _pages(100, 3_000)
    shards = _build_shards("4-azure", "xlsx", pages, tok)
    assert [s["id"] for s in shards] == [f"4-azure-s{i:02d}" for i in range(1, len(shards) + 1)]
    assert {s["slug"] for s in shards} == {"4-azure"}
    assert {s["format"] for s in shards} == {"xlsx"}


def test_the_page_cap_binds_before_the_token_budget():
    # Cheap pages: the budget would allow far more than the API accepts per request.
    pages, tok = _pages(250, 190)          # a PPTX deck
    assert USABLE // 190 > _SHARD_PAGE_CAP
    shards = _build_shards("deck", "pptx", pages, tok)
    assert max(len(s["pages"]) for s in shards) == _SHARD_PAGE_CAP


def test_one_oversized_page_is_kept_and_flagged():
    """Dropping it would lose content silently — emit it, and say it is over."""
    shards = _build_shards("huge", "pdf", [1], {1: USABLE + 50_000})
    assert len(shards) == 1
    assert shards[0]["pages"] == [1]
    assert shards[0]["over_budget"] is True


def test_a_document_with_no_complete_pages_shards_to_nothing():
    assert _build_shards("empty", "pdf", [], {}) == []


def test_a_page_missing_from_the_token_map_costs_nothing_rather_than_crashing():
    shards = _build_shards("gappy", "pdf", [1, 2, 3], {1: 500})
    assert [p for s in shards for p in s["pages"]] == [1, 2, 3]


class TestParameters:
    """Model, page cap and reserve are parameters — Haiku is only the default."""

    def test_the_default_is_haiku(self):
        from app.agents.tools.file_extract_tools import (
            _SHARD_DEFAULT_MODEL, _SHARD_SAFE_BUDGETS,
        )
        assert _SHARD_DEFAULT_MODEL == "haiku-4.5"
        assert _SHARD_SAFE_BUDGETS["haiku-4.5"] == 120_000

    def test_a_bigger_model_needs_fewer_shards_for_the_same_document(self):
        pages, tok = _pages(120, 2_250)
        haiku = _build_shards("x", "pdf", pages, tok)
        sonnet = _build_shards("x", "pdf", pages, tok, model="sonnet-4.6")
        assert len(haiku) == 3          # 46 pages per shard
        assert len(sonnet) == 2         # 585,000 usable, but the page cap binds at 100
        assert [len(s["pages"]) for s in sonnet] == [100, 20]

    def test_an_unknown_model_falls_back_to_the_default_rather_than_guessing(self):
        pages, tok = _pages(120, 2_250)
        assert (_build_shards("x", "pdf", pages, tok, model="not-a-model")
                == _build_shards("x", "pdf", pages, tok))

    def test_page_cap_is_a_parameter(self):
        pages, tok = _pages(30, 100)
        shards = _build_shards("x", "pptx", pages, tok, page_cap=10)
        assert [len(s["pages"]) for s in shards] == [10, 10, 10]

    def test_a_larger_measured_reserve_shrinks_the_shard(self):
        pages, tok = _pages(100, 2_250)
        lean = _build_shards("x", "pdf", pages, tok, reserve=0)
        fat = _build_shards("x", "pdf", pages, tok, reserve=60_000)
        assert len(lean[0]["pages"]) == 120_000 // 2_250       # 53 — the doc's figure
        assert len(fat[0]["pages"]) == 60_000 // 2_250         # 26

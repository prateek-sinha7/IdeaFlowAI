"""Property tests for agents/capabilities/token_usage.py — pricing invariants.

The pricing subsets (``long_context``, ``fallback_usage``) refine HOW the same
counts are priced. These properties pin what must hold for any counts:

* a record without subsets prices exactly as ``estimate_cost_usd`` (parity);
* pricing an agent's summed calls equals pricing each call (the long-context
  tier is per call, so the sum must carry it, not re-derive it);
* a stored subset can never price more than the record holds;
* ``normalize_usage`` is idempotent on current-version records.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agents.capabilities.model_pricing import estimate_cost_usd
from agents.capabilities.token_usage import (
    USAGE_VERSION,
    add_long_context,
    normalize_usage,
    usage_cost_usd,
    usage_from_metadata,
)

_TIERED = "eu.anthropic.claude-haiku-5-5"
_MODELS = st.sampled_from(
    [
        _TIERED,
        "eu.anthropic.claude-sonnet-5-5",
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        "global.openai.gpt-5.6-luna",
    ]
)
_COUNT = st.integers(min_value=0, max_value=400_000)


@st.composite
def _metadata(draw: st.DrawFn) -> dict:
    """A LangChain usage_metadata dict: input folds uncached + cache read + write."""
    cache_read = draw(_COUNT)
    cache_write = draw(_COUNT)
    uncached = draw(_COUNT)
    return {
        "input_tokens": uncached + cache_read + cache_write,
        "output_tokens": draw(st.integers(min_value=0, max_value=50_000)),
        "input_token_details": {
            "cache_read": cache_read,
            "cache_creation": cache_write,
        },
    }


@settings(max_examples=100, deadline=None)
@given(meta=_metadata(), model=_MODELS)
def test_usage_cost_usd_matches_estimate_when_record_has_no_subsets(
    meta: dict, model: str
) -> None:
    record = usage_from_metadata(meta)  # no model → no classification
    assert usage_cost_usd(model, record) == estimate_cost_usd(
        model,
        input_tokens=record["input_tokens"] - record["cache_write_tokens"],
        output_tokens=record["output_tokens"],
        cache_read_tokens=record["cache_read_tokens"],
        cache_write_tokens=record["cache_write_tokens"],
    )


@settings(max_examples=100, deadline=None)
@given(calls=st.lists(_metadata(), min_size=1, max_size=6))
def test_usage_cost_usd_is_additive_when_tiered_calls_are_summed(
    calls: list[dict],
) -> None:
    # Arrange: classify each call, then fold them the way the engine does.
    records = [usage_from_metadata(m, _TIERED) for m in calls]
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    total: dict = {k: sum(r[k] for r in records) for k in keys}
    long_ctx = None
    for r in records:
        long_ctx = add_long_context(long_ctx, r)
    if long_ctx is not None:
        total["long_context"] = long_ctx
    # Act + Assert: per-part rounding to 6 dp is the only allowed drift.
    assert usage_cost_usd(_TIERED, total) == pytest.approx(
        sum(usage_cost_usd(_TIERED, r) for r in records), abs=1e-5
    )


@settings(max_examples=100, deadline=None)
@given(
    meta=_metadata(),
    junk=st.fixed_dictionaries(
        {
            k: st.integers(min_value=0, max_value=10**9)
            for k in ("input_tokens", "output_tokens")
        }
    ),
)
def test_usage_cost_usd_never_exceeds_all_long_tier_when_subset_is_malformed(
    meta: dict, junk: dict
) -> None:
    record = {**usage_from_metadata(meta), "long_context": junk}
    everything_long = {
        **usage_from_metadata(meta),
        "long_context": usage_from_metadata(meta),
    }
    assert (
        0
        <= usage_cost_usd(_TIERED, record)
        <= usage_cost_usd(_TIERED, everything_long) + 1e-6
    )


@settings(max_examples=100, deadline=None)
@given(meta=_metadata())
def test_normalize_usage_is_idempotent_when_record_is_current_version(
    meta: dict,
) -> None:
    once = normalize_usage(
        {**usage_from_metadata(meta, _TIERED), "usage_version": USAGE_VERSION}
    )
    twice = normalize_usage({**once, "usage_version": USAGE_VERSION})
    assert twice == once

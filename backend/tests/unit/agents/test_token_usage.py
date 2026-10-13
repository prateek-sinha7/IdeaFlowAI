"""agents/capabilities/token_usage.py — the one usage record and its cost."""

from __future__ import annotations

import pytest

from agents.capabilities.model_pricing import estimate_cost_usd
from agents.capabilities.token_usage import (
    USAGE_VERSION,
    normalize_usage,
    usage_cost_full_usd,
    usage_cost_usd,
    usage_from_metadata,
)

SONNET = "eu.anthropic.claude-sonnet-4-6"
HAIKU = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
# Bedrock: 5 uncached, 10 cache read, 5 cache write, 5 output.
META = {
    "input_tokens": 20,
    "output_tokens": 5,
    "input_token_details": {"cache_read": 10, "cache_creation": 5},
}


def test_record_keeps_cache_reads_out_of_input_and_total() -> None:
    assert usage_from_metadata(META) == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cache_read_tokens": 10,
        "cache_write_tokens": 5,
    }


@pytest.mark.parametrize("meta", [None, {}, {"input_token_details": None}])
def test_missing_metadata_is_zeros(meta: object) -> None:
    assert usage_from_metadata(meta)["total_tokens"] == 0


def test_normalize_converts_old_records_and_leaves_new_ones() -> None:
    new = usage_from_metadata(META)
    assert normalize_usage({**new, "usage_version": USAGE_VERSION}) == new
    old = {
        "input_tokens": 20,
        "output_tokens": 5,
        "total_tokens": 25,
        "cache_read_tokens": 10,
        "cache_write_tokens": 5,
    }
    assert normalize_usage(old) == new
    run_row = {
        "total_input_tokens": 20,
        "total_output_tokens": 5,
        "total_cache_read_tokens": 10,
        "total_cache_write_tokens": 5,
    }
    assert normalize_usage(run_row, prefix="total_") == new


def test_cost_prices_each_count_at_its_rate_on_its_model() -> None:
    u = usage_from_metadata(META)
    for model in (SONNET, HAIKU):
        assert usage_cost_usd(model, u) == estimate_cost_usd(
            model,
            input_tokens=5,
            output_tokens=5,
            cache_read_tokens=10,
            cache_write_tokens=5,
        )
    assert usage_cost_usd(SONNET, u) > usage_cost_usd(HAIKU, u)
    # the as-if-uncached counterfactual: all 20 input tokens at 1x
    assert usage_cost_full_usd(SONNET, u) == estimate_cost_usd(SONNET, 20, 5)

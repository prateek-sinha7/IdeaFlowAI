"""agents/capabilities/token_usage.py — the one usage record and its cost."""

from __future__ import annotations

import pytest

from agents.capabilities.model_pricing import estimate_cost_usd
from agents.capabilities.token_usage import (
    USAGE_VERSION,
    add_long_context,
    add_model_usage,
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


# ---------------------------------------------------------------------------
# Long-context tier (Claude Haiku 5.5: prompts over 100K tokens bill at 5x)
# ---------------------------------------------------------------------------
HAIKU_55 = "eu.anthropic.claude-haiku-5-5"
SONNET_55 = "eu.anthropic.claude-sonnet-5-5"


def _meta(prompt: int, output: int = 10, cache_read: int = 0) -> dict:
    return {
        "input_tokens": prompt,
        "output_tokens": output,
        "input_token_details": {"cache_read": cache_read, "cache_creation": 0},
    }


def test_usage_from_metadata_copies_record_to_long_context_when_prompt_exceeds_threshold() -> (
    None
):
    record = usage_from_metadata(_meta(150_000), HAIKU_55)
    assert record["long_context"] == {
        "input_tokens": 150_000,
        "output_tokens": 10,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


def test_usage_from_metadata_counts_cached_prompt_toward_threshold_when_mostly_cached() -> (
    None
):
    # 10K new + 140K cache read = a 150K prompt: the provider tiers on the full prompt.
    record = usage_from_metadata(_meta(150_000, cache_read=140_000), HAIKU_55)
    assert record["long_context"]["cache_read_tokens"] == 140_000


@pytest.mark.parametrize(
    "prompt, model",
    [
        (100_000, HAIKU_55),  # exactly the threshold is still the base tier
        (150_000, SONNET_55),  # flat-priced model
        (150_000, "some-unknown-model"),  # unrecognised: priced by a guess
        (150_000, None),  # no model to classify against
    ],
    ids=["at-threshold", "flat-model", "unknown-model", "no-model"],
)
def test_usage_from_metadata_omits_long_context_when_not_a_tiered_call(
    prompt: int, model: str | None
) -> None:
    assert "long_context" not in usage_from_metadata(_meta(prompt), model)


def test_usage_cost_usd_prices_long_context_counts_at_long_tier_when_present() -> None:
    small = usage_from_metadata(_meta(50_000, output=1000), HAIKU_55)
    big = usage_from_metadata(_meta(150_000, output=1000), HAIKU_55)
    # $0.10/$0.50 below 100K, $0.50/$2.50 above; eu. profile adds 10%.
    assert usage_cost_usd(HAIKU_55, small) == pytest.approx(
        (50_000 * 0.1e-6 + 1000 * 0.5e-6) * 1.1
    )
    assert usage_cost_usd(HAIKU_55, big) == pytest.approx(
        (150_000 * 0.5e-6 + 1000 * 2.5e-6) * 1.1
    )


def test_usage_cost_usd_equals_sum_of_calls_when_tiered_calls_are_summed() -> None:
    # Arrange: an agent's totals = one base-tier call + one long-context call.
    small = usage_from_metadata(_meta(50_000), HAIKU_55)
    big = usage_from_metadata(_meta(150_000), HAIKU_55)
    total = {
        k: small[k] + big[k]
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    }
    total["long_context"] = add_long_context(add_long_context(None, small), big)
    # Act + Assert: pricing the sum equals pricing each call.
    assert usage_cost_usd(HAIKU_55, total) == pytest.approx(
        usage_cost_usd(HAIKU_55, small) + usage_cost_usd(HAIKU_55, big)
    )


def test_add_long_context_returns_total_unchanged_when_record_has_none() -> None:
    assert add_long_context(None, usage_from_metadata(META)) is None


def test_usage_cost_usd_caps_subset_at_record_when_stored_subset_is_malformed() -> None:
    # A stored subset larger than its record must not inflate the cost.
    record = {
        "input_tokens": 10,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "long_context": {"input_tokens": 999_999},
    }
    assert usage_cost_usd(HAIKU_55, record) == estimate_cost_usd(
        HAIKU_55, 10, 0, long_context=True
    )


def test_usage_cost_usd_ignores_long_context_when_model_is_flat_priced() -> None:
    plain = usage_from_metadata(_meta(150_000))
    tagged = {
        **plain,
        "long_context": usage_from_metadata(_meta(150_000), HAIKU_55)["long_context"],
    }
    assert usage_cost_usd(SONNET_55, tagged) == usage_cost_usd(SONNET_55, plain)


# ---------------------------------------------------------------------------
# Fallback-model subset
# ---------------------------------------------------------------------------


def test_usage_cost_usd_prices_fallback_part_on_its_model_when_record_has_fallback() -> (
    None
):
    # Arrange: a Sonnet 5.5 step; half its tokens came from a Haiku 5.5 fallback.
    primary_part = usage_from_metadata(_meta(1000, output=100))
    fallback_part = usage_from_metadata(_meta(1000, output=100))
    record = {
        k: primary_part[k] + fallback_part[k]
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    }
    record["fallback_usage"] = add_model_usage(None, HAIKU_55, fallback_part)
    # Act + Assert
    assert usage_cost_usd(SONNET_55, record) == pytest.approx(
        usage_cost_usd(SONNET_55, primary_part)
        + usage_cost_usd(HAIKU_55, fallback_part)
    )
    assert usage_cost_full_usd(SONNET_55, record) == pytest.approx(
        usage_cost_full_usd(SONNET_55, primary_part)
        + usage_cost_full_usd(HAIKU_55, fallback_part)
    )


def test_add_model_usage_accumulates_counts_and_long_context_when_called_twice() -> (
    None
):
    first = usage_from_metadata(_meta(150_000), HAIKU_55)
    second = usage_from_metadata(_meta(1000), HAIKU_55)
    by_model = add_model_usage(add_model_usage(None, HAIKU_55, first), HAIKU_55, second)
    assert by_model[HAIKU_55]["input_tokens"] == 151_000
    assert by_model[HAIKU_55]["long_context"]["input_tokens"] == 150_000


def test_normalize_usage_carries_subsets_when_record_has_them() -> None:
    lc = usage_from_metadata(_meta(150_000), HAIKU_55)["long_context"]
    stored = {
        **usage_from_metadata(_meta(150_000), HAIKU_55),
        "usage_version": USAGE_VERSION,
        "fallback_usage": {HAIKU_55: {**lc, "long_context": lc}, 7: "junk"},
    }
    out = normalize_usage(stored)
    assert out["long_context"] == lc
    # The junk entry (non-string key, non-mapping value) is dropped, never raised.
    assert out["fallback_usage"] == {HAIKU_55: {**lc, "long_context": lc}}


def test_usage_cost_usd_is_unchanged_when_record_has_no_subsets() -> None:
    # Parity: a flat, single-model record prices exactly as estimate_cost_usd.
    u = usage_from_metadata(META)
    assert usage_cost_usd(SONNET, u) == estimate_cost_usd(
        SONNET,
        input_tokens=5,
        output_tokens=5,
        cache_read_tokens=10,
        cache_write_tokens=5,
    )

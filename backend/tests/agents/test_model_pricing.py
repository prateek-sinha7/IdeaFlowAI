"""Offline unit + reconciliation + INV-12 both-sites coverage for model_pricing.

Fully offline: no network, no DB, no Bedrock. Pins the per-family base rates, the
regional premium, ``_canonical`` mapping (incl. unknown→fallback), the cache tiers,
the reconciliation pin, and — by reading the two source files off disk — the INV-12
contract that BOTH cost sites route through the shared ``estimate_cost_usd``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.model_pricing import (
    MODEL_PRICING,
    Price,
    _canonical,
    _regional_premium,
    estimate_cost_usd,
)

_BACKEND = Path(__file__).resolve().parents[2]
_ENGINE = _BACKEND / "agents" / "execution_engine" / "engine.py"
_WEBSOCKET = _BACKEND / "app" / "api" / "websocket.py"


# ---------------------------------------------------------------------------
# Per-family base rates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "family,expected",
    [
        ("claude-haiku-4-5", Price(1e-6, 5e-6, 0.1e-6, 1.25e-6, 2e-6)),
        ("claude-sonnet-4-5", Price(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6)),
        ("claude-sonnet-4-6", Price(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6)),
        ("claude-opus-4-5", Price(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6)),
        ("claude-opus-4-6", Price(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6)),
    ],
)
def test_per_family_base_rates(family: str, expected: Price) -> None:
    p = MODEL_PRICING[family]
    assert p.input == expected.input
    assert p.output == expected.output
    assert p.cache_read == expected.cache_read
    assert p.cache_write_5m == expected.cache_write_5m
    assert p.cache_write_1h == expected.cache_write_1h


def test_pricing_covers_exactly_five_families() -> None:
    assert set(MODEL_PRICING) == {
        "claude-haiku-4-5",
        "claude-sonnet-4-5",
        "claude-sonnet-4-6",
        "claude-opus-4-5",
        "claude-opus-4-6",
    }


# ---------------------------------------------------------------------------
# Regional premium
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("eu.anthropic.claude-haiku-4-5-20251001-v1:0", 1.10),
        ("us.anthropic.claude-sonnet-4-5", 1.10),
        ("apac.anthropic.claude-opus-4-6-v1", 1.10),
        ("global.anthropic.claude-sonnet-4-5-20250929-v1:0", 1.0),
        ("anthropic.claude-haiku-4-5", 1.0),
        ("claude-haiku-4-5", 1.0),
        ("", 1.0),
    ],
)
def test_regional_premium(model_id: str, expected: float) -> None:
    assert _regional_premium(model_id) == expected


# ---------------------------------------------------------------------------
# _canonical family mapping
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "model_id,family",
    [
        ("eu.anthropic.claude-haiku-4-5-20251001-v1:0", "claude-haiku-4-5"),
        ("eu.anthropic.claude-sonnet-4-6", "claude-sonnet-4-6"),
        ("eu.anthropic.claude-opus-4-6-v1", "claude-opus-4-6"),
        ("eu.anthropic.claude-opus-4-5-20251101-v1:0", "claude-opus-4-5"),
        ("global.anthropic.claude-sonnet-4-5-20250929-v1:0", "claude-sonnet-4-5"),
    ],
)
def test_canonical_known_families(model_id: str, family: str) -> None:
    assert _canonical(model_id) == family


def test_canonical_unknown_falls_back_to_haiku() -> None:
    assert _canonical("nonsense-model") == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Reconciliation pin
# ---------------------------------------------------------------------------
def test_reconciliation_pin() -> None:
    cost = estimate_cost_usd(
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0", 21_460_378, 225_860
    )
    assert cost == pytest.approx(24.85, abs=0.01)


def test_none_model_prices_as_haiku_1x() -> None:
    assert estimate_cost_usd(None, 1_000_000, 0) == round(1.0, 6)


# ---------------------------------------------------------------------------
# Cache tiers
# ---------------------------------------------------------------------------
def test_cache_read_priced_at_tenth_of_input_on_haiku() -> None:
    # haiku base input=1e-6; cache_read=0.1e-6/tok → 1M cache-read tokens = 0.1 USD
    assert estimate_cost_usd(
        "claude-haiku-4-5", 0, 0, cache_read_tokens=1_000_000
    ) == pytest.approx(0.1, abs=1e-9)


def test_cache_write_tier_delta_between_5m_and_1h() -> None:
    tokens = 1_000_000
    cost_5m = estimate_cost_usd(
        "claude-haiku-4-5", 0, 0, cache_write_tokens=tokens, cache_ttl="5m"
    )
    cost_1h = estimate_cost_usd(
        "claude-haiku-4-5", 0, 0, cache_write_tokens=tokens, cache_ttl="1h"
    )
    # 5m tier = 1.25e-6/tok → 1.25 ; 1h tier = 2e-6/tok → 2.0
    assert cost_5m == pytest.approx(1.25, abs=1e-9)
    assert cost_1h == pytest.approx(2.0, abs=1e-9)
    assert cost_1h > cost_5m


# ---------------------------------------------------------------------------
# Regional premium compounds exactly 1.10x
# ---------------------------------------------------------------------------
def test_regional_premium_compounds_on_opus() -> None:
    tokens_in, tokens_out = 500_000, 100_000
    global_cost = estimate_cost_usd(
        "global.anthropic.claude-opus-4-6-v1", tokens_in, tokens_out
    )
    us_cost = estimate_cost_usd(
        "us.anthropic.claude-opus-4-6-v1", tokens_in, tokens_out
    )
    assert us_cost == pytest.approx(global_cost * 1.10, rel=1e-9)


# ---------------------------------------------------------------------------
# INV-12: both cost sites route through the shared function
# ---------------------------------------------------------------------------
def test_engine_cost_site_uses_shared_function() -> None:
    src = _ENGINE.read_text(encoding="utf-8")
    assert "estimate_cost_usd" in src
    assert "0.00000025" not in src and "0.00000125" not in src


def test_websocket_cost_site_uses_shared_function() -> None:
    src = _WEBSOCKET.read_text(encoding="utf-8")
    assert "estimate_cost_usd" in src
    assert "0.00000025" not in src and "0.00000125" not in src

"""Offline unit + reconciliation + INV-12 both-sites coverage for model_pricing.

Fully offline: no network, no DB, no Bedrock. Pins the catalog-derived per-model
base rates, the regional premium, the three-tier ``_resolve_pricing`` behavior
(exact / region-version-normalized / unknown→cheap fallback), the cache tiers, the
reconciliation pin, and — by reading the two source files off disk — the INV-12
contract that BOTH cost sites route through the shared ``estimate_cost_usd``.

Model-id literals are permitted HERE (test files): ``test_single_source_grep`` scans
only ``app/api`` + ``agents/capabilities``, NOT ``tests/``. The rates live in exactly
one maintained list — ``model_catalog.py`` — which these tests assert against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.model_catalog import ModelCatalog, Pricing
from agents.capabilities.model_pricing import (
    _regional_premium,
    _resolve_pricing,
    estimate_cost_usd,
)

_BACKEND = Path(__file__).resolve().parents[2]
#: The TWO run-cost sites. ``engine.py`` prices the LIVE ``pipeline_complete`` event;
#: ``run_commands.py`` prices the DURABLE ``workflow_runs.token_usage`` row.
#:
#: This second path used to read ``app/api/websocket.py``. Phase 44's SSE cutover
#: DELETED that file, so from then until FIX-230 the guard raised ``FileNotFoundError``
#: instead of checking anything — the INV-12 contract for the persistence site was
#: unenforced. The existence assertion in ``_read_cost_site`` is what stops the next
#: file move from killing the guard silently again.
_ENGINE = _BACKEND / "agents" / "execution_engine" / "engine.py"
_RUN_COMMANDS = _BACKEND / "app" / "api" / "run_commands.py"

#: The shared cost function's canonical import line. A cost site must IMPORT it —
#: matching the mere string ``estimate_cost_usd`` would be satisfied by a comment.
_SHARED_IMPORT = "from agents.capabilities.model_pricing import estimate_cost_usd"

#: Per-token rate literals. Their presence at a cost site means a second, hand-rolled
#: pricing implementation has appeared (the INV-12 violation this guard exists for).
_RATE_LITERALS = ("0.00000025", "0.00000125", "0.000001", "0.000005")


def _read_cost_site(path: Path) -> str:
    assert path.is_file(), (
        f"INV-12 cost-site guard points at a file that does not exist: {path}. "
        "A cost site moved or was deleted — REPOINT this guard rather than deleting "
        "it, or the 'both cost sites share one pricing implementation' contract "
        "silently stops being checked (which is exactly what the SSE cutover did to "
        "the old app/api/websocket.py path)."
    )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-model base rates live in the catalog (the single source, INV-12)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "model_id,expected",
    [
        (
            "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
            Pricing(1e-6, 5e-6, 0.1e-6, 1.25e-6, 2e-6),
        ),
        (
            "us.anthropic.claude-3-5-haiku-20241022-v1:0",
            Pricing(0.8e-6, 4e-6, 0.08e-6, 1e-6, 1.6e-6),
        ),
        (
            "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
            Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        ),
        (
            "eu.anthropic.claude-sonnet-4-6",
            Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        ),
        (
            "eu.anthropic.claude-sonnet-4-20250514-v1:0",
            Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        ),
        (
            "eu.anthropic.claude-opus-4-5-20251101-v1:0",
            Pricing(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6),
        ),
        (
            "eu.anthropic.claude-opus-4-6-v1",
            Pricing(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6),
        ),
    ],
)
def test_catalog_carries_base_rates(model_id: str, expected: Pricing) -> None:
    entry = ModelCatalog().get(model_id)
    assert entry is not None
    assert entry.pricing == expected


def test_pricing_covers_every_catalog_model() -> None:
    entries = ModelCatalog().list()
    assert len(entries) == 7
    for entry in entries:
        assert isinstance(entry.pricing, Pricing)


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
# _resolve_pricing three-tier behavior (exact / normalized / fallback)
# ---------------------------------------------------------------------------
def test_resolve_exact_catalog_id() -> None:
    # (a) an exact catalog id returns that entry's pricing verbatim.
    for entry in ModelCatalog().list():
        assert _resolve_pricing(entry.id) == entry.pricing


@pytest.mark.parametrize(
    "variant_id,seed_id",
    [
        # (b) region/version-normalized variants resolve to the seed entry's pricing.
        ("us.anthropic.claude-haiku-4-5-20251001-v1:0", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
        ("claude-opus-4-5", "eu.anthropic.claude-opus-4-5-20251101-v1:0"),
        ("global.anthropic.claude-sonnet-4-5-20250929-v1:0", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"),
        ("apac.anthropic.claude-opus-4-6-v1", "eu.anthropic.claude-opus-4-6-v1"),
    ],
)
def test_resolve_normalized_variant(variant_id: str, seed_id: str) -> None:
    seed = ModelCatalog().get(seed_id)
    assert seed is not None
    assert _resolve_pricing(variant_id) == seed.pricing


def test_resolve_unknown_falls_back_to_cheap() -> None:
    # (c) an unknown id resolves to the catalog's cheap (Haiku) tier.
    cheap = next(e for e in ModelCatalog().list() if e.cost_class == "cheap")
    assert _resolve_pricing("nonsense-model") == cheap.pricing
    assert _resolve_pricing("") == cheap.pricing


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
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        0,
        0,
        cache_read_tokens=1_000_000,
    ) == pytest.approx(0.11, abs=1e-9)  # 0.1 base × 1.10 eu premium


def test_cache_read_tenth_of_input_no_premium() -> None:
    # bare haiku family (no regional premium) → exactly 0.1 USD for 1M cache-reads.
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
    # 5m tier = 1.25e-6/tok → 1.25 ; 1h tier = 2e-6/tok → 2.0 (no regional premium)
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
@pytest.mark.parametrize(
    "site",
    [
        pytest.param(_ENGINE, id="live-pipeline_complete"),
        pytest.param(_RUN_COMMANDS, id="durable-workflow_runs"),
    ],
)
def test_both_cost_sites_use_the_shared_pricing_function(site: Path) -> None:
    """Each run-cost site imports the ONE shared ``estimate_cost_usd`` and carries no
    per-token rate literal of its own — so a rate change has exactly one home
    (``agents/capabilities/model_catalog.py``) and the two sites cannot drift."""
    src = _read_cost_site(site)
    assert _SHARED_IMPORT in src, (
        f"{site.name} must import the shared pricing function ({_SHARED_IMPORT})"
    )
    found = [lit for lit in _RATE_LITERALS if lit in src]
    assert not found, f"{site.name} carries hand-rolled rate literal(s) {found}"

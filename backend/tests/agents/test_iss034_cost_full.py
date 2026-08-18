"""tests/agents/test_iss034_cost_full.py — ISS-034 offline proof.

Offline (no network / DB / Bedrock) coverage of the as-if-UNCACHED counterfactual
``estimated_cost_full_usd`` — the SIGNED effect of Bedrock prompt caching on a run:

  1. Both cost sites emit the key (source-pin) — the LIVE ``pipeline_complete`` in
     ``engine.py`` and the DURABLE ``workflow_runs.token_usage`` row in
     ``run_commands.py`` — still routing through the ONE shared ``estimate_cost_usd``
     with no rate literal of their own (INV-12; the sibling guard in
     ``test_model_pricing.py`` pins the import + no-literal half).
  2. The counterfactual is the SAME token base with the cache tiers switched OFF —
     no estimate, no proxy, no fudge factor. Every input is a token the model
     actually reported.
  3. **Sign coverage in BOTH directions**, anchored to OBSERVED runs, because a
     renderer that can only say "saved" is wrong on the majority of runs in the only
     dataset that exists: 6 of 11 persisted runs are strictly NEGATIVE. A run that
     writes cache entries it never re-reads pays the ``cache_write_5m`` 1.25x premium
     for nothing.
  4. Normalizer strips the new key — so the 5 characterization event goldens stay
     byte-identical with ZERO regeneration (INV-3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.model_pricing import estimate_cost_usd
from tests.agents.characterization._normalize import (
    _VOLATILE_STRIP_KEYS,
    _normalize_event,
)

_HAIKU_EU = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

_BACKEND = Path(__file__).resolve().parents[2]
_ENGINE = _BACKEND / "agents" / "execution_engine" / "engine.py"
_RUN_COMMANDS = _BACKEND / "app" / "api" / "run_commands.py"

_KEY = "estimated_cost_full_usd"


# ── 1. Both cost sites emit the key (source-pin) ────────────────────────────


def test_engine_cost_site_emits_full_cost_key() -> None:
    src = _ENGINE.read_text(encoding="utf-8")
    assert f'"{_KEY}"' in src, (
        "the LIVE pipeline_complete cost site must emit the as-if-uncached "
        "counterfactual alongside estimated_cost_usd"
    )


def test_run_commands_cost_site_emits_full_cost_key() -> None:
    src = _RUN_COMMANDS.read_text(encoding="utf-8")
    assert f'"{_KEY}"' in src, (
        "the DURABLE workflow_runs.token_usage writer must persist the "
        "as-if-uncached counterfactual alongside estimated_cost_usd"
    )


# ── 2. The counterfactual is the same base with cache tiers OFF ─────────────


def test_full_cost_is_every_input_token_at_1x() -> None:
    # Bedrock reports input_tokens as the TOTAL including cache, so pricing that
    # same total with no cache args IS the as-if-uncached price of an identical
    # run — not an approximation of one.
    tin, tout = 90_159, 40_170
    full = estimate_cost_usd(_HAIKU_EU, input_tokens=tin, output_tokens=tout)
    expected = (tin * 1e-6 + tout * 5e-6) * 1.10
    assert full == round(expected, 6)


# ── 3. Sign coverage — BOTH directions, anchored to observed runs ───────────


def _cached_vs_full(
    tin: int, tout: int, cache_read: int, cache_write: int
) -> tuple[float, float]:
    cached = estimate_cost_usd(
        _HAIKU_EU,
        input_tokens=max(0, tin - cache_read - cache_write),
        output_tokens=tout,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cache_ttl="5m",
    )
    full = estimate_cost_usd(_HAIKU_EU, input_tokens=tin, output_tokens=tout)
    return cached, full


def test_short_run_that_never_re_reads_its_cache_costs_MORE() -> None:
    """Run ``a7dba362`` (observed): cache_read=0, cache_write=86,976 → NEGATIVE.

    This is the case the UI must never label "saved". The delta is signed, and on
    this run — and on 6 of the 11 persisted runs — the sign is negative.
    """
    cached, full = _cached_vs_full(90_159, 40_170, 0, 86_976)
    assert cached == 0.344028
    assert full == 0.320110
    # Caching COST money here: the as-if-uncached price is LOWER than what we paid.
    assert full < cached
    delta = full - cached
    assert delta == pytest.approx(-0.023918, abs=1e-9)
    assert round(delta / full * 100, 2) == -7.47


def test_long_run_that_re_reads_its_cache_SAVES() -> None:
    """Run ``6e38b9a7`` (observed): 35.8M cache-reads → strongly POSITIVE."""
    cached, full = _cached_vs_full(37_069_667, 258_224, 35_827_675, 1_241_027)
    assert cached == 7.068750
    assert full == 42.196866
    assert full > cached
    assert round((full - cached) / full * 100, 2) == 83.25


def test_run_with_no_cache_activity_has_exactly_zero_delta() -> None:
    """Run ``0a27b397`` (observed): cache_read == cache_write == 0.

    The counterfactual collapses onto the real price, so the delta is EXACTLY
    zero — which the renderer must show as nothing at all, never a "0%" that
    implies caching ran.
    """
    cached, full = _cached_vs_full(17_682, 39_692, 0, 0)
    assert cached == full == 0.237756


# ── 4. Normalizer strips the new key (INV-3, zero regeneration) ─────────────


def test_normalizer_strips_full_cost_key() -> None:
    assert {_KEY} <= _VOLATILE_STRIP_KEYS


def test_normalize_drops_pipeline_complete_full_cost_key() -> None:
    event = {
        "type": "pipeline_complete",
        "data": {
            "pipeline_type": "prototype",
            "agents_completed": 1,
            "agents_total": 1,
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost_usd": 0.000165,
            _KEY: 0.000165,
        },
    }
    norm = _normalize_event(event)
    assert _KEY not in norm["data"]
    # The sibling cost key was already stripped; both go, so the goldens hold.
    assert "estimated_cost_usd" not in norm["data"]

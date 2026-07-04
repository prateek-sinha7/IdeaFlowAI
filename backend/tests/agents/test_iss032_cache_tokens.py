"""tests/agents/test_iss032_cache_tokens.py — ISS-032 / FIX-036 offline proof.

Offline (no network / DB / Bedrock) coverage of the prompt-cache token surfacing:

  1. Runner extraction — ``_cache_token_counts`` pulls the Bedrock cache split from
     ``usage_metadata["input_token_details"]`` and defaults to ``(0, 0)`` on any
     absent/None shape (never raises).
  2. Usage-event wiring (source-pin) — the ``on_chat_model_end`` usage-emit in the
     runner references BOTH ``cache_read_tokens`` and ``cache_write_tokens`` (locks
     the emitted-event contract without driving the heavy deepagents graph; mirrors
     the t2x both-call-sites source-pin).
  3. Cost split (no double-count) — pricing the UNCACHED portion (input − cache)
     plus the cache tiers via the shared ``estimate_cost_usd`` costs MUCH less than
     pricing every input token at 1x, and equals the exact hand-computed value.
  4. Normalizer strips the 4 new keys — so the characterization event goldens stay
     byte-identical (INV-3).
"""

from __future__ import annotations

import pathlib

import pytest

from agents.capabilities.model_pricing import estimate_cost_usd
from app.agents.deep_agent_runner import _cache_token_counts
from tests.agents.characterization._normalize import (
    _VOLATILE_STRIP_KEYS,
    _normalize_event,
)

_HAIKU_EU = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


# ── 1. Runner extraction ───────────────────────────────────────────────────


def test_cache_token_counts_extracts_split() -> None:
    assert _cache_token_counts(
        {"input_token_details": {"cache_read": 60000, "cache_creation": 5000}}
    ) == (60000, 5000)


@pytest.mark.parametrize(
    "meta",
    [
        {"input_token_details": None},  # Bedrock turn with no cache
        {},  # ChatAnthropic / scripted (no details block)
        None,  # meta absent entirely
        {"input_token_details": {}},  # empty details
    ],
)
def test_cache_token_counts_defaults_zero(meta: object) -> None:
    assert _cache_token_counts(meta) == (0, 0)


def test_cache_token_counts_partial_dict_defaults_missing() -> None:
    # Only cache_read present → cache_write (cache_creation) defaults 0, no raise.
    assert _cache_token_counts(
        {"input_token_details": {"cache_read": 1234}}
    ) == (1234, 0)
    # None-valued sub-keys degrade to 0 (int(... or 0)), never raises.
    assert _cache_token_counts(
        {"input_token_details": {"cache_read": None, "cache_creation": None}}
    ) == (0, 0)


# ── 2. Usage-event wiring (source-pin) ─────────────────────────────────────


def test_usage_event_emits_both_cache_keys_source_pin() -> None:
    src = pathlib.Path(
        "app/agents/deep_agent_runner.py"
    ).read_text(encoding="utf-8")
    # The on_chat_model_end usage-emit dict must carry both cache keys.
    assert '"cache_read_tokens": _cr' in src
    assert '"cache_write_tokens": _cw' in src
    # And the helper is the single extraction seam.
    assert "def _cache_token_counts" in src


# ── 3. Cost split (no double-count) ────────────────────────────────────────


def test_cost_split_is_less_than_all_at_1x_and_exact() -> None:
    # A 70k-input turn: 5k uncached, 60k cache-read, 5k cache-write.
    uncached, cache_read, cache_write = 5000, 60000, 5000
    total_input = uncached + cache_read + cache_write  # 70000

    split = estimate_cost_usd(
        _HAIKU_EU,
        input_tokens=uncached,
        output_tokens=0,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cache_ttl="5m",
    )
    all_at_1x = estimate_cost_usd(_HAIKU_EU, total_input, 0)

    # The discount is real and large — cache-reads bill at 0.1x, not 1x.
    assert split < all_at_1x * 0.5

    # Exact no-double-count value: uncached input at 1x + cache_read at 0.1x +
    # cache_write_5m at 1.25e-6, all ×1.10 regional premium. The uncached input is
    # NOT re-added on top of the total.
    expected = (
        uncached * 1e-6 + cache_read * 0.1e-6 + cache_write * 1.25e-6
    ) * 1.10
    assert split == pytest.approx(expected, rel=1e-6)


def test_cost_split_no_cache_equals_baseline() -> None:
    # cache=0 (the scripted characterization case) → uncached == total, so the
    # split cost equals the old 2-arg pricing exactly (goldens stay identical).
    total_input = 12345
    split = estimate_cost_usd(
        _HAIKU_EU,
        input_tokens=max(0, total_input - 0 - 0),
        output_tokens=678,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cache_ttl="5m",
    )
    baseline = estimate_cost_usd(_HAIKU_EU, total_input, 678)
    assert split == baseline


# ── 4. Normalizer strips the 4 new keys ────────────────────────────────────


def test_normalizer_strips_new_cache_keys() -> None:
    assert {
        "cache_read_tokens",
        "cache_write_tokens",
        "total_cache_read_tokens",
        "total_cache_write_tokens",
    } <= _VOLATILE_STRIP_KEYS


def test_normalize_drops_agent_complete_cache_keys() -> None:
    event = {
        "type": "agent_complete",
        "data": {
            "agent_id": "domain-analyst",
            "name": "Domain Analyst",
            "duration": 1.0,
            "output_length": 42,
            "index": 0,
            "total": 1,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "cache_read_tokens": 60000,
            "cache_write_tokens": 5000,
        },
    }
    norm = _normalize_event(event)
    assert "cache_read_tokens" not in norm["data"]
    assert "cache_write_tokens" not in norm["data"]
    # Structural keys survive the strip (input_tokens is volatile-required → its
    # slot is kept and sentinel-normalized, not dropped like the cache keys).
    assert "input_tokens" in norm["data"]


def test_normalize_drops_pipeline_complete_total_cache_keys() -> None:
    event = {
        "type": "pipeline_complete",
        "data": {
            "pipeline_type": "prototype",
            "agents_completed": 1,
            "agents_total": 1,
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_tokens": 150,
            "total_cache_read_tokens": 60000,
            "total_cache_write_tokens": 5000,
        },
    }
    norm = _normalize_event(event)
    assert "total_cache_read_tokens" not in norm["data"]
    assert "total_cache_write_tokens" not in norm["data"]

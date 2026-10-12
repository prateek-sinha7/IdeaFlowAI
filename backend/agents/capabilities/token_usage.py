"""agents/capabilities/token_usage.py — the ONE definition of a model call's token usage.

Bedrock reports four counts per call: uncached input, cache read, cache write, output.
``langchain_aws`` folds three of them into ``usage_metadata["input_tokens"]`` (uncached +
cache read + cache write) and puts the cache split in ``input_token_details``. Taken as
is, a cache read — the same context re-sent on every call — counts as new input, and a
run's "total" becomes mostly repeats (run c4cbd381: 92.6M total, 6.4M of it new).

The usage record every layer carries (runner events, agent_complete, pipeline_complete,
the persisted run row) is therefore:

    input_tokens        uncached input + cache write   (everything new the model read)
    output_tokens       output
    total_tokens        input_tokens + output_tokens
    cache_read_tokens   cache read — never inside input or total; Analytics shows it
    cache_write_tokens  cache write — also inside input_tokens

Every producer builds it with :func:`usage_from_metadata`; everything downstream only
sums. Cost comes from the four counts via :func:`usage_cost_usd`. Records carrying
``usage_version: 2`` use this meaning; older ones (no version) have cache reads inside
``input_tokens`` / ``total_tokens`` — :func:`normalize_usage` converts them.

Pure stdlib (+ the sibling pricing module). Never raises.
"""
from __future__ import annotations

from typing import Any

from agents.capabilities.model_pricing import estimate_cost_usd

USAGE_VERSION = 2


def usage_from_metadata(meta: Any) -> dict[str, int]:
    """A LangChain ``usage_metadata`` dict → the usage record. Missing → zeros."""
    meta = meta if isinstance(meta, dict) else {}
    details = meta.get("input_token_details") or {}
    cache_read = int(details.get("cache_read", 0) or 0)
    cache_write = int(details.get("cache_creation", 0) or 0)
    input_tokens = max(0, int(meta.get("input_tokens", 0) or 0) - cache_read)
    output_tokens = int(meta.get("output_tokens", 0) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }


def normalize_usage(record: dict, *, prefix: str = "") -> dict[str, int]:
    """Any stored usage record → the current meaning. ``prefix`` reads run-level keys
    (``total_input_tokens`` …). A record without ``usage_version`` predates this module:
    its input and total still hold the cache reads, so they are subtracted here."""
    def num(key: str) -> int:
        try:
            return int(record.get(f"{prefix}{key}", 0) or 0)
        except (TypeError, ValueError):
            return 0

    cache_read, cache_write = num("cache_read_tokens"), num("cache_write_tokens")
    input_tokens, output_tokens = num("input_tokens"), num("output_tokens")
    if record.get("usage_version") != USAGE_VERSION:
        input_tokens = max(0, input_tokens - cache_read)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }


def usage_cost_usd(model_id: str | None, usage: dict, *, cache_ttl: str = "5m") -> float:
    """What a usage record cost on ``model_id``, each of the four counts at its own rate."""
    cache_write = int(usage.get("cache_write_tokens", 0) or 0)
    return estimate_cost_usd(
        model_id,
        input_tokens=max(0, int(usage.get("input_tokens", 0) or 0) - cache_write),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        cache_read_tokens=int(usage.get("cache_read_tokens", 0) or 0),
        cache_write_tokens=cache_write,
        cache_ttl=cache_ttl,
    )


def usage_cost_full_usd(model_id: str | None, usage: dict) -> float:
    """The as-if-uncached counterfactual: every input token (cache read included) at 1x."""
    return estimate_cost_usd(
        model_id,
        input_tokens=int(usage.get("input_tokens", 0) or 0) + int(usage.get("cache_read_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
    )


if __name__ == "__main__":
    # Bedrock call: 5 uncached, 10 cache read, 5 cache write, 5 output.
    u = usage_from_metadata({"input_tokens": 20, "output_tokens": 5,
                             "input_token_details": {"cache_read": 10, "cache_creation": 5}})
    assert u == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                 "cache_read_tokens": 10, "cache_write_tokens": 5}, u
    assert normalize_usage({**u, "usage_version": 2}) == u
    assert normalize_usage({"input_tokens": 20, "output_tokens": 5, "cache_read_tokens": 10,
                            "cache_write_tokens": 5}) == u
    assert usage_from_metadata(None)["total_tokens"] == 0
    print("ok")

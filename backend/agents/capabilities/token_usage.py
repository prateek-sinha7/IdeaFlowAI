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

Two optional nested subsets refine how the SAME counts are priced. Neither changes a
token total, and each is written only when non-empty, so a record for a flat-priced,
single-model call is byte-identical to before (INV-3):

    long_context    the part billed at the model's long-context tier — calls whose
                    prompt exceeded its threshold (e.g. >100K on Claude Haiku 5.5).
                    Classified per call in :func:`usage_from_metadata`, because the
                    threshold applies to one request, never to a sum.
    fallback_usage  ``{model_id: counts}`` — the part produced by a model OTHER than
                    the record's own ``model_id`` (an engine fallback after a
                    throttle), so it is priced on the model that actually ran.

Every producer builds the record with :func:`usage_from_metadata`; everything downstream
only sums. Cost comes from the counts via :func:`usage_cost_usd`. Records carrying
``usage_version: 2`` use this meaning; older ones (no version) have cache reads inside
``input_tokens`` / ``total_tokens`` — :func:`normalize_usage` converts them.

Pure stdlib (+ the sibling pricing module). Never raises.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NotRequired, TypedDict

from agents.capabilities.model_pricing import estimate_cost_usd
from agents.capabilities.model_pricing import long_context_threshold

USAGE_VERSION = 2

LONG_CONTEXT_KEY = "long_context"
FALLBACK_USAGE_KEY = "fallback_usage"


class UsageCounts(TypedDict):
    """The four billable counts."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


class ModelUsage(UsageCounts):
    """The counts ONE other model produced inside a record (``fallback_usage``)."""

    long_context: NotRequired[UsageCounts]


class UsageRecord(TypedDict):
    """The usage record (module docstring)."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    long_context: NotRequired[UsageCounts]
    fallback_usage: NotRequired[dict[str, ModelUsage]]


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _counts(source: Any) -> UsageCounts:
    """The four counts of any mapping; a non-mapping or a bad value reads as 0."""
    src: Mapping[str, Any] = source if isinstance(source, Mapping) else {}
    return {
        "input_tokens": _int(src.get("input_tokens")),
        "output_tokens": _int(src.get("output_tokens")),
        "cache_read_tokens": _int(src.get("cache_read_tokens")),
        "cache_write_tokens": _int(src.get("cache_write_tokens")),
    }


def _plus(a: UsageCounts | None, b: UsageCounts) -> UsageCounts:
    if a is None:
        return _counts(b)
    return {
        "input_tokens": a["input_tokens"] + b["input_tokens"],
        "output_tokens": a["output_tokens"] + b["output_tokens"],
        "cache_read_tokens": a["cache_read_tokens"] + b["cache_read_tokens"],
        "cache_write_tokens": a["cache_write_tokens"] + b["cache_write_tokens"],
    }


def _minus(a: UsageCounts, b: UsageCounts) -> UsageCounts:
    """``a - b`` per count, never below 0."""
    return {
        "input_tokens": max(0, a["input_tokens"] - b["input_tokens"]),
        "output_tokens": max(0, a["output_tokens"] - b["output_tokens"]),
        "cache_read_tokens": max(0, a["cache_read_tokens"] - b["cache_read_tokens"]),
        "cache_write_tokens": max(0, a["cache_write_tokens"] - b["cache_write_tokens"]),
    }


def _capped(part: UsageCounts, whole: UsageCounts) -> UsageCounts:
    """``part`` limited to ``whole`` per count: a subset can never exceed its record,
    so a malformed stored subset cannot inflate a cost."""
    return {
        "input_tokens": min(part["input_tokens"], whole["input_tokens"]),
        "output_tokens": min(part["output_tokens"], whole["output_tokens"]),
        "cache_read_tokens": min(part["cache_read_tokens"], whole["cache_read_tokens"]),
        "cache_write_tokens": min(
            part["cache_write_tokens"], whole["cache_write_tokens"]
        ),
    }


def _is_empty(counts: UsageCounts) -> bool:
    return not any(
        (
            counts["input_tokens"],
            counts["output_tokens"],
            counts["cache_read_tokens"],
            counts["cache_write_tokens"],
        )
    )


def usage_from_metadata(meta: Any, model_id: str | None = None) -> UsageRecord:
    """A LangChain ``usage_metadata`` dict → the usage record. Missing → zeros.

    ``model_id`` (optional) classifies this ONE request for tiered pricing: when
    its prompt exceeds the model's long-context threshold, the whole record is
    also copied under ``long_context``. Without a model id nothing is classified.
    """
    meta = meta if isinstance(meta, dict) else {}
    details = meta.get("input_token_details") or {}
    cache_read = int(details.get("cache_read", 0) or 0)
    cache_write = int(details.get("cache_creation", 0) or 0)
    raw_input = int(meta.get("input_tokens", 0) or 0)
    input_tokens = max(0, raw_input - cache_read)
    output_tokens = int(meta.get("output_tokens", 0) or 0)
    record: UsageRecord = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }
    threshold = long_context_threshold(model_id)
    # langchain_aws folds uncached + cache read + cache write into input_tokens,
    # so ``raw_input`` is the full prompt size the provider tiers on.
    if threshold is not None and raw_input > threshold:
        record["long_context"] = _counts(record)
    return record


def add_long_context(
    total: UsageCounts | None, record: Mapping[str, Any]
) -> UsageCounts | None:
    """Fold ``record``'s ``long_context`` subset into ``total``.

    Returns ``total`` unchanged (possibly ``None``) when ``record`` has none, so an
    accumulator stays ``None`` — and its key absent — for flat-priced calls.
    """
    part = record.get(LONG_CONTEXT_KEY) if isinstance(record, Mapping) else None
    if not isinstance(part, Mapping):
        return total
    return _plus(total, _counts(part))


def add_model_usage(
    by_model: dict[str, ModelUsage] | None,
    model_id: str,
    record: Mapping[str, Any],
) -> dict[str, ModelUsage]:
    """Fold one usage event that ``model_id`` produced into a ``fallback_usage`` map."""
    out: dict[str, ModelUsage] = dict(by_model or {})
    prev = out.get(model_id)
    counts = _plus(_counts(prev) if prev is not None else None, _counts(record))
    entry: ModelUsage = {
        "input_tokens": counts["input_tokens"],
        "output_tokens": counts["output_tokens"],
        "cache_read_tokens": counts["cache_read_tokens"],
        "cache_write_tokens": counts["cache_write_tokens"],
    }
    long_ctx = add_long_context(
        prev.get("long_context") if prev is not None else None, record
    )
    if long_ctx is not None:
        entry["long_context"] = long_ctx
    out[model_id] = entry
    return out


def _model_usages(raw: Any) -> dict[str, ModelUsage]:
    """A stored ``fallback_usage`` value → clean per-model counts (bad entries dropped)."""
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, ModelUsage] = {}
    for model_id, part in raw.items():
        if (
            not isinstance(model_id, str)
            or not model_id
            or not isinstance(part, Mapping)
        ):
            continue
        counts = _counts(part)
        entry: ModelUsage = {
            "input_tokens": counts["input_tokens"],
            "output_tokens": counts["output_tokens"],
            "cache_read_tokens": counts["cache_read_tokens"],
            "cache_write_tokens": counts["cache_write_tokens"],
        }
        if isinstance(part.get(LONG_CONTEXT_KEY), Mapping):
            entry["long_context"] = _counts(part.get(LONG_CONTEXT_KEY))
        out[model_id] = entry
    return out


def normalize_usage(record: Mapping[str, Any], *, prefix: str = "") -> UsageRecord:
    """Any stored usage record → the current meaning. ``prefix`` reads run-level keys
    (``total_input_tokens`` …). A record without ``usage_version`` predates this module:
    its input and total still hold the cache reads, so they are subtracted here.
    The ``long_context`` / ``fallback_usage`` subsets are carried through for pricing
    (only current-version producers write them, so they need no conversion)."""

    def num(key: str) -> int:
        try:
            return int(record.get(f"{prefix}{key}", 0) or 0)
        except (TypeError, ValueError):
            return 0

    cache_read, cache_write = num("cache_read_tokens"), num("cache_write_tokens")
    input_tokens, output_tokens = num("input_tokens"), num("output_tokens")
    if record.get("usage_version") != USAGE_VERSION:
        input_tokens = max(0, input_tokens - cache_read)
    out: UsageRecord = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }
    long_ctx = record.get(f"{prefix}{LONG_CONTEXT_KEY}")
    if isinstance(long_ctx, Mapping):
        out["long_context"] = _counts(long_ctx)
    by_model = _model_usages(record.get(f"{prefix}{FALLBACK_USAGE_KEY}"))
    if by_model:
        out["fallback_usage"] = by_model
    return out


def _partitions(
    model_id: str | None, usage: Mapping[str, Any]
) -> list[tuple[str | None, UsageCounts, UsageCounts]]:
    """Split a record into ``(model, counts, long_context_counts)`` parts that are
    each priced on one model: the record's own model, then each fallback model.

    Subsets are capped to what remains of the record, so a malformed subset can
    never price more tokens than the record holds.
    """
    remaining = _counts(usage)
    remaining_long = _capped(_counts(usage.get(LONG_CONTEXT_KEY)), remaining)
    parts: list[tuple[str | None, UsageCounts, UsageCounts]] = []
    for other_model, part in _model_usages(usage.get(FALLBACK_USAGE_KEY)).items():
        counts = _capped(_counts(part), remaining)
        long_counts = _capped(_counts(part.get("long_context")), counts)
        long_counts = _capped(long_counts, remaining_long)
        parts.append((other_model, counts, long_counts))
        remaining = _minus(remaining, counts)
        remaining_long = _minus(remaining_long, long_counts)
    parts.insert(0, (model_id, remaining, _capped(remaining_long, remaining)))
    return parts


def _priced(
    model_id: str | None,
    counts: UsageCounts,
    *,
    cache_ttl: str,
    long_context: bool,
) -> float:
    cache_write = counts["cache_write_tokens"]
    return estimate_cost_usd(
        model_id,
        input_tokens=max(0, counts["input_tokens"] - cache_write),
        output_tokens=counts["output_tokens"],
        cache_read_tokens=counts["cache_read_tokens"],
        cache_write_tokens=cache_write,
        cache_ttl=cache_ttl,
        long_context=long_context,
    )


def usage_cost_usd(
    model_id: str | None, usage: Mapping[str, Any], *, cache_ttl: str = "5m"
) -> float:
    """What a usage record cost, each of the four counts at its own rate.

    Each part is priced on the model that produced it (``fallback_usage``), and
    its ``long_context`` counts at that model's long-context tier.
    """
    cost = 0.0
    for part_model, counts, long_counts in _partitions(model_id, usage):
        base = _minus(counts, long_counts)
        cost += _priced(part_model, base, cache_ttl=cache_ttl, long_context=False)
        if not _is_empty(long_counts):
            cost += _priced(
                part_model, long_counts, cache_ttl=cache_ttl, long_context=True
            )
    return round(cost, 6)


def usage_cost_full_usd(model_id: str | None, usage: Mapping[str, Any]) -> float:
    """The as-if-uncached counterfactual: every input token (cache read included) at 1x."""
    cost = 0.0
    for part_model, counts, long_counts in _partitions(model_id, usage):
        for part, is_long in (
            (_minus(counts, long_counts), False),
            (long_counts, True),
        ):
            if is_long and _is_empty(part):
                continue
            cost += estimate_cost_usd(
                part_model,
                input_tokens=part["input_tokens"] + part["cache_read_tokens"],
                output_tokens=part["output_tokens"],
                long_context=is_long,
            )
    return round(cost, 6)


if __name__ == "__main__":
    # Bedrock call: 5 uncached, 10 cache read, 5 cache write, 5 output.
    u = usage_from_metadata(
        {
            "input_tokens": 20,
            "output_tokens": 5,
            "input_token_details": {"cache_read": 10, "cache_creation": 5},
        }
    )
    assert u == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cache_read_tokens": 10,
        "cache_write_tokens": 5,
    }, u
    assert normalize_usage({**u, "usage_version": 2}) == u
    assert (
        normalize_usage(
            {
                "input_tokens": 20,
                "output_tokens": 5,
                "cache_read_tokens": 10,
                "cache_write_tokens": 5,
            }
        )
        == u
    )
    assert usage_from_metadata(None)["total_tokens"] == 0
    print("ok")

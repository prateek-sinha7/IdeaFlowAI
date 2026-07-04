"""agents/capabilities/model_pricing.py — the single source of run-cost rates (INV-12).

Kernel-pure DATA + PURE-FN module (mirrors the sibling ``model_catalog.py``):
per-family token prices + a regional premium + cache tiers, exposed through one
``estimate_cost_usd`` that BOTH cost sites (the engine ``pipeline_complete`` event
and the persisted ``workflow_runs.token_usage``) share — so run cost can never
silently diverge between the two again (INV-12; SC-001: no per-model branch at the
call sites — all model-keyed logic lives here).

Scope guards:
  - DATA + pure functions only. stdlib-only imports (``dataclasses``, ``re``,
    ``logging``, ``__future__``).
  - MUST NOT import ``app.*``, ``agents.execution_engine``, or ``agents.workflows``
    (import-linter contract "agents.capabilities must not import the execution
    kernel or the web layer"). The kernel/web layers import THIS module, never the
    reverse.
  - Never raises on a bad model id: ``_canonical`` degrades an unknown family to
    ``_FALLBACK`` (warn-once), and ``None`` model ids are guarded at the boundary,
    so the cost calc always returns a number.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Price:
    """Immutable per-SINGLE-token USD rates for one model family.

    Every field is a USD price per ONE token (input / output / cache-read /
    cache-write at the 5-minute and 1-hour TTL tiers).
    """

    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


# ---------------------------------------------------------------------------
# The authoritative per-family run-cost rates (the ONE source of truth, INV-12).
# Keyed by FAMILY id (the geo/provider prefix + version/date suffix stripped by
# ``_canonical``). Rates are verified base Anthropic-direct / Bedrock-global $/tok.
#
# NOTE: Opus 4.6 / Sonnet 4.6 Bedrock $ are DERIVED — operator confirm on the
# live AWS pricing page (they mirror the 4.5 tier pending published Bedrock rates).
# ---------------------------------------------------------------------------
MODEL_PRICING: dict[str, Price] = {
    "claude-haiku-4-5": Price(1e-6, 5e-6, 0.1e-6, 1.25e-6, 2e-6),
    "claude-sonnet-4-5": Price(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
    "claude-sonnet-4-6": Price(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
    "claude-opus-4-5": Price(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6),
    "claude-opus-4-6": Price(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6),
}

_FALLBACK = "claude-haiku-4-5"

# Leading geographic/provider prefix tokens stripped (iteratively) by _canonical,
# so ``eu.anthropic.`` fully reduces to the bare family key.
_PREFIXES = ("eu.", "us.", "apac.", "global.", "anthropic.")

# Regional inference profiles carry a +10% premium; global./anthropic-direct/bare
# do not.
_PREMIUM_PREFIXES = ("eu.", "us.", "apac.")

# Version/date suffixes: ``-vN``, ``-vN:0``, ``-YYYYMMDD``, ``-YYYYMMDD-vN:0``.
_SUFFIX_RE = re.compile(r"(-\d{8})?(-v\d+(?::\d+)?)?$")

# Dedupe the warn-once-per-unknown-family log.
_WARNED_UNKNOWN: set[str] = set()


def _canonical(model_id: str) -> str:
    """Reduce a full model id to its pricing FAMILY key, else ``_FALLBACK``.

    Iteratively strips any leading geo/provider prefix (so ``eu.anthropic.`` fully
    strips), then strips a trailing version/date suffix. Returns the family key iff
    it is in ``MODEL_PRICING``; otherwise warns ONCE and returns ``_FALLBACK``.
    """
    key = model_id
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if key.startswith(prefix):
                key = key[len(prefix):]
                changed = True
    key = _SUFFIX_RE.sub("", key)
    if key in MODEL_PRICING:
        return key
    if model_id not in _WARNED_UNKNOWN:
        _WARNED_UNKNOWN.add(model_id)
        logger.warning(
            "model_pricing: unknown model family for %r → pricing as fallback %r",
            model_id,
            _FALLBACK,
        )
    return _FALLBACK


def _regional_premium(model_id: str) -> float:
    """Return 1.10 for eu./us./apac. inference profiles, else 1.0.

    global./anthropic-direct/bare ``claude-`` ids and the empty string are 1.0.
    """
    if model_id.startswith(_PREMIUM_PREFIXES):
        return 1.10
    return 1.0


def estimate_cost_usd(
    model_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    *,
    cache_ttl: str = "5m",
) -> float:
    """Estimate run cost in USD for ``model_id`` at the given token counts.

    Prices per the model's family (``_canonical``) scaled by its regional premium
    (``_regional_premium``). ``cache_ttl`` selects the 1h vs 5m cache-write tier.
    A ``None`` model id prices as ``_FALLBACK`` at 1.0x. Never raises.
    """
    p = MODEL_PRICING[_canonical(model_id or _FALLBACK)]
    mult = _regional_premium(model_id or "")
    write_rate = p.cache_write_1h if cache_ttl == "1h" else p.cache_write_5m
    usd = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * write_rate
    ) * mult
    return round(usd, 6)

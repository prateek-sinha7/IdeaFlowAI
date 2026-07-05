"""agents/capabilities/model_pricing.py — run-cost rates DERIVED from the catalog.

Kernel-pure PURE-FN module (mirrors the sibling ``model_catalog.py``): it holds NO
model-id literals of its own. Every model's per-token rates come from
``model_catalog.py`` — the ONE authoritative model-id list (INV-12) — via the
co-located ``Pricing`` dataclass on each ``ModelEntry``. The regional premium and
cache tiers are applied here, exposed through one ``estimate_cost_usd`` that BOTH
cost sites (the engine ``pipeline_complete`` event and the persisted
``workflow_runs.token_usage``) share — so run cost can never silently diverge
between the two again (INV-12; SC-001: no per-model branch at the call sites — all
model-keyed logic lives here, keyed off ``model_id`` + region only).

Scope guards:
  - PURE functions only. Imports the catalog (``ModelCatalog`` / ``Pricing``) plus
    stdlib (``re``, ``logging``, ``__future__``).
  - MUST NOT import ``app.*``, ``agents.execution_engine``, or ``agents.workflows``
    (import-linter contract "agents.capabilities must not import the execution
    kernel or the web layer"). The kernel/web layers import THIS module, never the
    reverse. ``model_catalog`` is a sibling in ``agents.capabilities`` — allowed.
  - Never raises on a bad model id: ``_resolve_pricing`` degrades an unknown id to
    the catalog's cheap tier (warn-once), and ``None`` model ids are guarded at the
    boundary, so the cost calc always returns a number.
"""

from __future__ import annotations

import logging
import re

from agents.capabilities.model_catalog import ModelCatalog, Pricing

logger = logging.getLogger(__name__)

# Leading geographic/provider prefix tokens stripped (iteratively) when
# normalizing an id for the fallback match, so ``eu.anthropic.`` fully reduces.
_PREFIXES = ("eu.", "us.", "apac.", "global.", "anthropic.")

# Regional inference profiles carry a +10% premium; global./anthropic-direct/bare
# do not.
_PREMIUM_PREFIXES = ("eu.", "us.", "apac.")

# Version/date suffixes: ``-vN``, ``-vN:0``, ``-YYYYMMDD``, ``-YYYYMMDD-vN:0``.
_SUFFIX_RE = re.compile(r"(-\d{8})?(-v\d+(?::\d+)?)?$")

# Dedupe the warn-once-per-unknown-id log.
_WARNED_UNKNOWN: set[str] = set()


def _normalize(model_id: str) -> str:
    """Reduce a full model id to its bare family form for fallback matching.

    Iteratively strips any leading geo/provider prefix (so ``eu.anthropic.`` fully
    strips), then strips a trailing version/date suffix. Carries NO model-id
    literal — it only manipulates prefix/suffix tokens.
    """
    key = model_id
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if key.startswith(prefix):
                key = key[len(prefix):]
                changed = True
    return _SUFFIX_RE.sub("", key)


def _cheap_pricing(catalog: ModelCatalog) -> Pricing:
    """Return the catalog's cheap-tier ``Pricing`` (located by cost_class, not id)."""
    for entry in catalog.list():
        if entry.cost_class == "cheap":
            return entry.pricing
    # Defensive: no cheap tier declared — fall back to the first entry.
    return catalog.list()[0].pricing


def _resolve_pricing(model_id: str) -> Pricing:
    """Resolve a model's ``Pricing`` FROM the catalog, in three tiers.

    (a) EXACT: an entry whose id equals ``model_id``.
    (b) NORMALIZED: region/version-normalize BOTH the input id and each catalog id
        and match on the bare family form (so ``us.…-v1`` maps to the ``eu.…`` seed).
    (c) DEFAULT: the catalog's cheap tier (warn-once for an unknown id).
    """
    catalog = ModelCatalog()

    exact = catalog.get(model_id)
    if exact is not None:
        return exact.pricing

    normalized = _normalize(model_id)
    if normalized:
        for entry in catalog.list():
            if _normalize(entry.id) == normalized:
                return entry.pricing

    if model_id not in _WARNED_UNKNOWN:
        _WARNED_UNKNOWN.add(model_id)
        logger.warning(
            "model_pricing: unknown model id %r → pricing as the catalog cheap tier",
            model_id,
        )
    return _cheap_pricing(catalog)


def _regional_premium(model_id: str) -> float:
    """Return 1.10 for eu./us./apac. inference profiles, else 1.0.

    global./anthropic-direct/bare ids and the empty string are 1.0. Region strings
    are not model-id literals.
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

    Prices per the model's catalog-derived ``Pricing`` (``_resolve_pricing``) scaled
    by its regional premium (``_regional_premium``). ``cache_ttl`` selects the 1h vs
    5m cache-write tier. A ``None`` / unknown model id prices as the cheap (Haiku)
    tier at 1.0x. Never raises.
    """
    p = _resolve_pricing(model_id or "")
    mult = _regional_premium(model_id or "")
    write_rate = p.cache_write_1h if cache_ttl == "1h" else p.cache_write_5m
    usd = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * write_rate
    ) * mult
    return round(usd, 6)

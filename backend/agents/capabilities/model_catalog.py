"""agents/capabilities/model_catalog.py — the single source of model metadata (MODEL-04).

Kernel-pure data module (D-03): enumerates the selectable Claude models with their
display + policy metadata. This is the ONE authoritative model-id list (INV-12) —
``app/api/settings.py::AVAILABLE_MODELS`` and ``_VALID_MODEL_IDS`` are derived
projections over this catalog, not a second hand-maintained list.

Scope guards:
  - DATA only. No behavior port, no Protocol in ``base.py`` (RESEARCH #3 — the
    catalog is static data, not a capability behavior). It mirrors the pure-data
    shape of ``agents/capabilities/registry.py::_KNOWN``.
  - MUST NOT import ``app.*`` or ``agents.execution_engine`` (import-linter contract
    "agents.capabilities must not import the execution kernel or the web layer").
    The module is self-contained — the resolver (06-03), override-validator (06-04),
    and loader (06-02) all import it from the kernel side.
  - No per-owner trust enforcement / ``user_allowed`` gating here (Phase 8, N11):
    every entry is ``user_allowed=True`` today, including both Opus tiers.

``tier`` (legacy/display) and ``cost_class`` (canonical) are BOTH stored (D-04):
the ``/api/settings`` projection keeps ``tier`` for the frontend ``ModelOption``
shape, while resolution/fallback policy keys off ``cost_class``. The two are kept
consistent (fast↔cheap, balanced↔standard, powerful↔premium).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Pricing:
    """Immutable per-SINGLE-token USD rates for one model.

    Every field is a USD price per ONE token — the base / Anthropic-direct /
    Bedrock-global rate, BEFORE any regional inference-profile premium. Fields:
    ``input`` / ``output`` / ``cache_read`` / ``cache_write`` at the 5-minute and
    1-hour TTL tiers.
    """

    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


# Leading geographic/provider prefix tokens stripped (iteratively) when
# normalizing an id, so ``eu.anthropic.`` fully reduces. Moved here from
# model_pricing so the catalog lookup and the pricing lookup share ONE
# normalizer — two copies of this is how the thinking-fragment tuples drifted.
_PREFIXES = ("eu.", "us.", "apac.", "global.", "anthropic.")

# Version/date suffixes: ``-vN``, ``-vN:0``, ``-YYYYMMDD``, ``-YYYYMMDD-vN:0``.
_SUFFIX_RE = re.compile(r"(-\d{8})?(-v\d+(?::\d+)?)?$")


def normalize_model_id(model_id: str) -> str:
    """Reduce a full model id to its bare family form for fallback matching.

    Iteratively strips any leading geo/provider prefix (so ``eu.anthropic.``
    fully strips), then a trailing version/date suffix. Carries NO model-id
    literal — it only manipulates prefix/suffix tokens.
    """
    key = model_id
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if key.startswith(prefix):
                key = key[len(prefix) :]
                changed = True
    return _SUFFIX_RE.sub("", key)


# Reasoning-effort levels OpenAI documents for the GPT-5.6 family, and the
# superset any `Reasoning.levels` is drawn from. Confirmed against Bedrock
# 2026-09-22: Sol and Luna accept exactly these six and reject anything else
# with a ValidationException, so this list is a UI contract and a better error
# message, not the only guard.
REASONING_EFFORT_LEVELS: tuple[str, ...] = (
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


@dataclass(frozen=True)
class Reasoning:
    """How a model exposes reasoning, and what a UI may offer for it (spec 020).

    Replaces THREE id-substring tuples that had already drifted apart:
    ``model_factory._ADAPTIVE_THINKING_MODEL_FRAGMENTS`` and
    ``api/capabilities._THINKING_FRAGMENTS`` differed by ``"opus-4"`` under a
    comment conceding they were "kept in sync by grep", and the second fed the
    Analytics page's "Thinking: Adaptive" row — so the UI contradicted the
    runtime about Opus 4.5/4.6.

    ``mode`` selects the wire shape in ``additionalModelRequestFields``:
      - ``effort``   -> {"reasoning": {"effort": <level>}}        (GPT-5.6)
      - ``adaptive`` -> {"thinking": {"type": "adaptive"}}        (Sonnet 5)
      - ``budget``   -> {"thinking": {"type": "enabled", ...}}    (Claude <= 4.6)
      - ``none``     -> nothing is sent                           (Haiku 3.5)

    ``levels`` is what a picker may offer; ``()`` means no control at all. The
    two Claude modes carry ``("none", "on")`` rather than the full six because
    the thinking budget is pinned at maximum, so low..max would produce
    byte-identical requests — six labels for two behaviours is a control that
    lies. Sonnet 5 gains real levels once langchain-aws is upgraded (spec §7),
    by changing one row here and nothing else.
    """

    mode: str
    levels: tuple[str, ...]


@dataclass(frozen=True)
class ModelEntry:
    """An immutable catalog record for one selectable model (MODEL-04 field set)."""

    id: str
    label: str
    description: str
    tier: str
    cost_class: str
    # The TRANSPORT (which SDK/API carries the call) — "bedrock" for every entry
    # today. NOT the model's maker: nothing needs that, and a field every new
    # entry must fill but no code reads is how a catalog rots.
    provider: str
    context_window: int
    user_allowed: bool
    pricing: Pricing
    # Vision-capability flag — gates image input at ingress (IMAGE-INPUT §3 Layer 5):
    # `_validate_images` rejects an image set unless every effective run-level model
    # is a catalog entry with `vision=True` (closes the raw-config escape hatch).
    vision: bool
    # Bedrock prompt-caching support (spec 020 / FR-21). Gates
    # `_BedrockCachePointsMiddleware`, which previously keyed off the TRANSPORT
    # (`isinstance(model, ChatBedrockConverse)`) and so injected a `cachePoint`
    # into every Bedrock model — including OpenAI's, which support caching on the
    # Responses API only. Measured: GPT-5.6 Luna + cachePoint returns
    # AccessDeniedException ("unsupported model or your request did not allow
    # prompt caching") while Claude Haiku 4.5 accepts the identical call.
    supports_prompt_caching: bool
    # How this model does reasoning, and what the composer may offer for it.
    # No default: a new entry must state it, or it silently inherits a wire shape
    # its provider may not accept.
    reasoning: Reasoning


# ---------------------------------------------------------------------------
# The authoritative model list — the ONE hand-maintained model-id list (INV-12).
# Ids/labels/descriptions are verbatim from the former settings.py seed list.
# context_window numerics are [ASSUMED] metadata (RESEARCH A1) — they do not
# affect resolution/fallback, which key off id / cost_class.
# ---------------------------------------------------------------------------
_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        id="eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        label="Claude Haiku 4.5",
        description="Fastest and most cost-efficient. Great for high-volume tasks.",
        tier="fast",
        cost_class="cheap",
        provider="bedrock",
        context_window=200000,
        user_allowed=True,
        pricing=Pricing(1e-6, 5e-6, 0.1e-6, 1.25e-6, 2e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="budget", levels=("none", "on")),
    ),
    ModelEntry(
        # US cross-region inference profile for Haiku 4.5 — use when the
        # deployment region is us-east-1 / us-east-2 / us-west-2 (e.g. local dev).
        # Geo-prefix normalization in model_policy.py auto-selects this entry when
        # AWS_REGION is a US region.
        id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        label="Claude Haiku 4.5",
        description="Fastest and most cost-efficient. Great for high-volume tasks.",
        tier="fast",
        cost_class="cheap",
        provider="bedrock",
        context_window=200000,
        user_allowed=True,
        pricing=Pricing(1e-6, 5e-6, 0.1e-6, 1.25e-6, 2e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="budget", levels=("none", "on")),
    ),
    # --- OpenAI GPT-5.6 (spec 020) ------------------------------------------
    # NOT FIRST IN THIS TUPLE, deliberately: model_pricing._resolve_pricing
    # degrades an unknown id to the FIRST cost_class="cheap" entry, so a leading
    # Luna would silently reprice every unknown model from $1.00/1M to $0.20/1M —
    # a 5x under-estimate caught only by test_none_model_prices_as_haiku_1x.
    #
    # GLOBAL CRIS is the only option for both from eu-north-1: AWS publishes no
    # in-Region and no `eu.` profile on bedrock-runtime (the geo ids are us./in.
    # only). Consequence: requests route WORLDWIDE, so these entries do NOT
    # preserve the EU data residency the eu.anthropic.* entries give you.
    # `global.` is passed through untouched by _normalize_geo_prefix, so no
    # geo-swap logic applies.
    ModelEntry(
        id="global.openai.gpt-5.6-luna",
        label="GPT-5.6 Luna",
        description="Fastest and most cost-efficient, 1M context. High-volume tasks.",
        tier="fast",
        cost_class="cheap",
        # Served over the bedrock-runtime Converse API, the same transport as
        # every Claude entry — NOT a direct OpenAI API integration.
        provider="bedrock",
        context_window=1000000,
        user_allowed=True,
        # Global CRIS rates, short-context tier (<=272K input). Long context is
        # charged ~2x and is NOT modelled — Pricing carries one input rate.
        # The cache fields are unreachable here (see supports_prompt_caching);
        # they carry the published 30m cache-write rate so the shape stays valid.
        pricing=Pricing(0.2e-6, 1.2e-6, 0.02e-6, 0.25e-6, 0.25e-6),
        vision=True,
        # Bedrock supports prompt caching for this model on the Responses API
        # ONLY. A cachePoint on Converse returns AccessDeniedException — measured.
        supports_prompt_caching=False,
        reasoning=Reasoning(mode="effort", levels=REASONING_EFFORT_LEVELS),
    ),
    ModelEntry(
        id="global.openai.gpt-5.6-sol",
        label="GPT-5.6 Sol",
        description="Frontier reasoning and agentic performance. 1M token context.",
        tier="powerful",
        cost_class="premium",
        provider="bedrock",
        context_window=1000000,
        user_allowed=True,
        pricing=Pricing(4e-6, 20e-6, 0.4e-6, 5e-6, 5e-6),
        vision=True,
        supports_prompt_caching=False,
        reasoning=Reasoning(mode="effort", levels=REASONING_EFFORT_LEVELS),
    ),
    # REMOVED 2026-09-22 — Claude Haiku 3.5. AWS does not serve it in eu-north-1
    # in ANY form: `list_foundation_models` returns zero `claude-3-5-haiku` rows
    # and there is no eu./global. inference profile, only us. The entry predated
    # GEO-01 (added 2026-08-14, normalizer 2026-08-27), which then rewrote its
    # us. prefix to an eu. profile that has never existed — so selecting it
    # failed at the Bedrock call while looking like an ordinary catalog row.
    # Verified 0 references in the database before removal. Re-add only with a
    # profile id confirmed present in the deployment region.
    ModelEntry(
        id="eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        label="Claude Sonnet 4.5",
        description="Balanced speed and intelligence. Ideal for most pipelines.",
        tier="balanced",
        cost_class="standard",
        provider="bedrock",
        context_window=200000,
        user_allowed=True,
        pricing=Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="budget", levels=("none", "on")),
    ),
    ModelEntry(
        id="eu.anthropic.claude-sonnet-4-6",
        label="Claude Sonnet 4.6",
        description="Best combination of speed and intelligence. 1M token context.",
        tier="balanced",
        cost_class="standard",
        provider="bedrock",
        context_window=1000000,
        user_allowed=True,
        # NOTE: Opus 4.6 / Sonnet 4.6 Bedrock $ are DERIVED — operator confirm on
        # the live AWS pricing page (they mirror the 4.5 tier pending published
        # Bedrock rates).
        pricing=Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="budget", levels=("none", "on")),
    ),
    ModelEntry(
        # US cross-region inference profile for Sonnet 5 — use when the
        # deployment region is us-east-1 / us-east-2 / us-west-2 (e.g. the
        # local dev environment at AWS_REGION=us-east-2). The `eu.` Sonnet 4.6
        # variant is routed through EU regions; this entry uses the US CRIS prefix.
        id="us.anthropic.claude-sonnet-5",
        label="Claude Sonnet 5",
        description="Most capable Sonnet model. Near-Opus intelligence for coding, agents, and professional work. 1M token context.",
        tier="balanced",
        cost_class="standard",
        provider="bedrock",
        context_window=1000000,
        user_allowed=True,
        pricing=Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="adaptive", levels=("none", "on")),
    ),
    ModelEntry(
        # EU cross-region inference profile for Sonnet 5 — use when the
        # deployment region is eu-central-1 / eu-west-1 / eu-west-2 etc.
        # (production deployment at AWS_REGION=eu-central-1). Keeps data
        # within EU regions. Geo-prefix normalization in model_policy.py
        # auto-selects this entry when AWS_REGION is an EU region, so
        # AGENT.md files never need a region-specific literal.
        id="eu.anthropic.claude-sonnet-5",
        label="Claude Sonnet 5",
        description="Most capable Sonnet model. Near-Opus intelligence for coding, agents, and professional work. 1M token context.",
        tier="balanced",
        cost_class="standard",
        provider="bedrock",
        context_window=1000000,
        user_allowed=True,
        pricing=Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="adaptive", levels=("none", "on")),
    ),
    ModelEntry(
        # Deprecated (not retired) per AWS's Bedrock lifecycle table — prefer
        # Sonnet 4.5/4.6. Kept `eu.`-prefixed for parity with the rest of
        # this catalog (unlike Haiku 3.5 above, an `eu.` inference profile
        # exists for this one).
        id="eu.anthropic.claude-sonnet-4-20250514-v1:0",
        label="Claude Sonnet 4",
        description="Prior-generation balanced model. Deprecated — prefer Sonnet 4.5.",
        tier="balanced",
        cost_class="standard",
        provider="bedrock",
        context_window=200000,
        user_allowed=True,
        pricing=Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="budget", levels=("none", "on")),
    ),
    ModelEntry(
        id="eu.anthropic.claude-opus-4-5-20251101-v1:0",
        label="Claude Opus 4.5",
        description="Most powerful. Best for complex reasoning and coding tasks.",
        tier="powerful",
        cost_class="premium",
        provider="bedrock",
        context_window=200000,
        user_allowed=True,
        pricing=Pricing(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="budget", levels=("none", "on")),
    ),
    ModelEntry(
        id="eu.anthropic.claude-opus-4-6-v1",
        label="Claude Opus 4.6",
        description="Most intelligent broadly available model. Exceptional coding.",
        tier="powerful",
        cost_class="premium",
        provider="bedrock",
        context_window=200000,
        user_allowed=True,
        # Opus 4.6 Bedrock $ DERIVED (mirrors 4.5 premium tier) — operator confirm.
        pricing=Pricing(5e-6, 25e-6, 0.5e-6, 6.25e-6, 10e-6),
        vision=True,
        supports_prompt_caching=True,
        reasoning=Reasoning(mode="budget", levels=("none", "on")),
    ),
)


class ModelCatalog:
    """Read-only accessor over the authoritative model list (MODEL-04).

    Pure data — ``list``/``get``/``is_allowed``/``ids`` are deterministic lookups
    with no I/O, no DB, no ``app.*`` reach. Constructing it is cheap; callers may
    instantiate freely.
    """

    def list(self) -> list[ModelEntry]:
        """Return all catalog entries in declaration order."""
        return list(_ENTRIES)

    def get(self, model_id: str) -> ModelEntry | None:
        """Return the entry for ``model_id``, or ``None`` if unknown."""
        for entry in _ENTRIES:
            if entry.id == model_id:
                return entry
        return None

    def resolve(self, model_id: str) -> ModelEntry | None:
        """Return the entry for ``model_id``, exact first then normalized.

        ``get`` is exact-match, which is right for validation but wrong for a
        capability lookup: ``build_model`` may hold a BARE id on the ChatAnthropic
        local-dev path (``claude-sonnet-5``) where the catalog stores the
        qualified profile (``eu.anthropic.claude-sonnet-5``). Both reduce to the
        same family form, so the normalized pass finds it.

        Returns ``None`` for a genuinely unknown model — callers decide what a
        miss means; this does NOT fall back to a default entry.
        """
        exact = self.get(model_id)
        if exact is not None:
            return exact
        key = normalize_model_id(model_id)
        if not key:
            return None
        for entry in self.list():
            if normalize_model_id(entry.id) == key:
                return entry
        return None

    def is_allowed(self, model_id: str) -> bool:
        """Return ``True`` iff ``model_id`` is a known, user-allowed model."""
        entry = self.get(model_id)
        return entry is not None and entry.user_allowed

    def ids(self) -> list[str]:
        """Return the model ids in declaration order."""
        return [entry.id for entry in _ENTRIES]

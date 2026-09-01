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


@dataclass(frozen=True)
class ModelEntry:
    """An immutable catalog record for one selectable model (MODEL-04 field set)."""

    id: str
    label: str
    description: str
    tier: str
    cost_class: str
    provider: str
    context_window: int
    user_allowed: bool
    pricing: Pricing
    # Vision-capability flag — gates image input at ingress (IMAGE-INPUT §3 Layer 5):
    # `_validate_images` rejects an image set unless every effective run-level model
    # is a catalog entry with `vision=True` (closes the raw-config escape hatch).
    vision: bool


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
    ),
    ModelEntry(
        # Deprecated (not retired) per AWS's Bedrock lifecycle table — still
        # invocable, but no `eu.`/`global.` inference profile exists for it,
        # only `us.` (unlike every other entry in this catalog). Included
        # since it's the only remaining Haiku generation below 4.5 that AWS
        # still serves.
        id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        label="Claude Haiku 3.5",
        description="Prior-generation fast model. Deprecated — prefer Haiku 4.5.",
        tier="fast",
        cost_class="cheap",
        provider="bedrock",
        context_window=200000,
        user_allowed=True,
        pricing=Pricing(0.8e-6, 4e-6, 0.08e-6, 1e-6, 1.6e-6),
        vision=True,
    ),
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
    ),
    ModelEntry(
        # US cross-region inference profile for Sonnet 5 — use when the
        # deployment region is us-east-1 / us-east-2 / us-west-2 (e.g. the
        # local dev environment at AWS_REGION=us-east-2). The `eu.` Sonnet 4.6
        # variant is routed through EU regions; this entry uses the US CRIS prefix.
        id="us.anthropic.claude-sonnet-5",
        label="Claude Sonnet 5 (US)",
        description="Most capable Sonnet model. Near-Opus intelligence for coding, agents, and professional work. 1M token context.",
        tier="balanced",
        cost_class="standard",
        provider="bedrock",
        context_window=1000000,
        user_allowed=True,
        pricing=Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        vision=True,
    ),
    ModelEntry(
        # EU cross-region inference profile for Sonnet 5 — use when the
        # deployment region is eu-central-1 / eu-west-1 / eu-west-2 etc.
        # (production deployment at AWS_REGION=eu-central-1). Keeps data
        # within EU regions. Geo-prefix normalization in model_policy.py
        # auto-selects this entry when AWS_REGION is an EU region, so
        # AGENT.md files never need a region-specific literal.
        id="eu.anthropic.claude-sonnet-5",
        label="Claude Sonnet 5 (EU)",
        description="Most capable Sonnet model. Near-Opus intelligence for coding, agents, and professional work. 1M token context.",
        tier="balanced",
        cost_class="standard",
        provider="bedrock",
        context_window=1000000,
        user_allowed=True,
        pricing=Pricing(3e-6, 15e-6, 0.3e-6, 3.75e-6, 6e-6),
        vision=True,
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

    def is_allowed(self, model_id: str) -> bool:
        """Return ``True`` iff ``model_id`` is a known, user-allowed model."""
        entry = self.get(model_id)
        return entry is not None and entry.user_allowed

    def ids(self) -> list[str]:
        """Return the model ids in declaration order."""
        return [entry.id for entry in _ENTRIES]

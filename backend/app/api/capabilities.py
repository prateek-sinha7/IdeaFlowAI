"""Capability-registry palette API (API-02 / D-11).

This router surfaces the **hardened capability registry** to the composer: a
single authenticated ``GET /api/capabilities`` returns the palette the frontend
renders (the capability palette panel + the per-agent model picker). For every
registered ``(kind, name)`` it reports:

  * ``kind`` / ``name``  — the registry coordinate;
  * ``user_allowed``     — the CAP-03 trust flag (``is_user_allowed``): privileged
    kinds (exec/secrets/spawn/runtimes) surface ``False`` and the UI gates them
    off the user-grantable palette (T-08-08-ID);
  * ``description``      — a concise human-readable blurb, authored on the
    capability's ``@register`` decorator and projected from the registry's
    ``_META`` via ``describe`` (SURF-02 / D-08 — registry self-describes);
  * ``security_gated``   — a DERIVED flag (``not user_allowed``): privileged
    capabilities the user palette gates off (RESEARCH discretion A2 — no second
    stored source);
  * ``config_schema``    — a per-capability config slot, populated from the
    registry (D-09): JSON-Schema-lite for caps that take config, legitimately
    ``{}`` for caps that take none. Surfaced via ``describe`` — the registry is
    the single source of truth (NO static metadata map in this API layer, D-08).

The model catalog (the ``model_catalog`` kind) is surfaced **expanded** under a
separate ``model_catalog`` key — the per-model records from
``ModelCatalog`` (id/label/tier/cost_class/provider/context_window/user_allowed)
that the per-agent model picker renders.

Source of truth is the **registry** (``_KNOWN`` post-``discover()``), enumerated
live — NOT a hardcoded list — so a newly ``@register``'d capability appears with
NO endpoint edit (API-02).

Security (T-08-08-auth):
  * JWT-only (``Depends(get_current_user)``) — the same posture as every other
    read endpoint (``app/api/workflows.py``). An unauthenticated client gets 401
    and never reads the palette.

WS events (API-03): the new ``validator_result``/``validation_warning``/``gate_*``
run-stream events are **additive only** — they flow through the generic
``app/api/websocket.py`` forward (``{"type": event["type"], ...}``) with NO
``websocket.py`` edit for the new event TYPES and NO existing event renamed or
removed. This router does not touch the WS path; the additivity is proven in
``tests/unit/test_capabilities_api.py`` + the characterization parity suite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.capabilities import registry as registry_mod
from agents.capabilities.model_catalog import ModelCatalog
from agents.capabilities.registry import CapabilityRegistry
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


# --- Response Schemas ---


class CapabilityEntry(BaseModel):
    """One palette entry — a registered ``(kind, name)`` with its trust + metadata.

    All fields beyond ``kind``/``name``/``user_allowed`` are ADDITIVE (SURF-02 /
    D-10): the API-02 contract keeps every existing key. ``description`` and
    ``config_schema`` are projected from the registry's ``_META`` via
    ``describe`` (D-08 — the registry self-describes; there is NO static metadata
    map here). ``security_gated`` is DERIVED from the trust flag (``not
    user_allowed``, RESEARCH discretion A2) — no second stored source.
    """

    kind: str
    name: str
    user_allowed: bool
    # Concise human-readable blurb, authored on the capability's @register
    # decorator and surfaced via ``registry.describe`` (D-08).
    description: str = ""
    # Derived security flag: a capability that is NOT user-grantable is gated off
    # the user palette (``not user_allowed``). Test-assertable, no second source.
    security_gated: bool = False
    # Per-capability config slot, populated from ``registry.describe`` (D-09):
    # JSON-Schema-lite for caps that take config, legitimately ``{}`` for caps
    # that take none. No longer the literal ``{}`` stub.
    config_schema: dict = {}


class ModelCatalogEntry(BaseModel):
    """One model-picker entry, projected from ``ModelCatalog`` (MODEL-04).

    RFN-002b: pricing rates added (USD per 1 M tokens, scaled from the catalog's
    per-single-token ``Pricing`` dataclass × 1 000 000) so the Analytics page can
    build a fully dynamic model-details panel without a hardcoded rate table.
    ``thinking_supported`` flags models whose id contains an adaptive-thinking
    fragment (claude-sonnet-5, claude-opus-*) so the UI can surface a note.
    All new fields have safe defaults so existing callers that don't read them
    are unaffected (purely additive).
    """

    id: str
    label: str
    description: str
    tier: str
    cost_class: str
    provider: str
    context_window: int
    user_allowed: bool
    # RFN-002b — pricing rates in USD per 1 M tokens (catalog Pricing × 1e6).
    # 5-minute cache-write TTL is the default; 1-hour rate omitted (rare usage).
    input_rate_per_1m: float = 0.0
    output_rate_per_1m: float = 0.0
    cache_read_rate_per_1m: float = 0.0
    cache_write_5m_rate_per_1m: float = 0.0
    # True for models that support adaptive/extended thinking
    # (claude-sonnet-5, claude-opus-*).  Haiku and older Sonnets use budget_tokens
    # thinking or thinking-off; only these newer models use effort="max".
    thinking_supported: bool = False


class CapabilitiesPalette(BaseModel):
    """The full palette payload the composer renders (capabilities + models)."""

    capabilities: list[CapabilityEntry]
    model_catalog: list[ModelCatalogEntry]


# --- Endpoint ---


@router.get("", response_model=CapabilitiesPalette)
def list_capabilities(
    current_user: User = Depends(get_current_user),
) -> CapabilitiesPalette:
    """Return the registry palette + model catalog (auth-gated, API-02).

    Enumerates the registry live (``_KNOWN`` after ``discover()``) so a freshly
    registered capability appears with no endpoint edit. ``model_catalog``
    entries are excluded from the per-capability list (they are surfaced
    expanded under ``model_catalog``).
    """
    registry = CapabilityRegistry()
    # Ensure the impl modules + their trust flags are bound before reading them.
    registry_mod.discover()

    capabilities: list[CapabilityEntry] = []
    for kind, name in sorted(registry_mod._KNOWN):
        if kind == "model_catalog":
            # Surfaced expanded under model_catalog below — not as a single
            # opaque palette row.
            continue
        meta = registry.describe(kind, name)
        user_allowed = registry.is_user_allowed(kind, name)
        capabilities.append(
            CapabilityEntry(
                kind=kind,
                name=name,
                user_allowed=user_allowed,
                description=meta["description"],
                # Derived from the trust flag (D-02) — no separate stored source.
                security_gated=not user_allowed,
                config_schema=meta["config_schema"],
            )
        )

    # Models whose id contains one of these fragments support adaptive thinking
    # (effort="max" in build_model).  Mirrors the _ADAPTIVE_THINKING_MODEL_FRAGMENTS
    # tuple in model_factory.py — kept in sync by grep rather than a shared import
    # (model_factory is app-layer, not capabilities-layer).
    _THINKING_FRAGMENTS = ("sonnet-5", "opus-5", "fable-5", "mythos-5", "opus-4")

    model_catalog = [
        ModelCatalogEntry(
            id=m.id,
            label=m.label,
            description=m.description,
            tier=m.tier,
            cost_class=m.cost_class,
            provider=m.provider,
            context_window=m.context_window,
            user_allowed=m.user_allowed,
            # RFN-002b — scale per-single-token rates → per-1M-token rates.
            # The regional inference-profile +10 % premium is NOT applied here
            # because the analytics page shows catalog base rates (operator info),
            # not per-run billed amounts (which already live in token_usage.estimated_cost_usd).
            input_rate_per_1m=round(m.pricing.input * 1_000_000, 4),
            output_rate_per_1m=round(m.pricing.output * 1_000_000, 4),
            cache_read_rate_per_1m=round(m.pricing.cache_read * 1_000_000, 4),
            cache_write_5m_rate_per_1m=round(m.pricing.cache_write_5m * 1_000_000, 4),
            thinking_supported=any(frag in m.id for frag in _THINKING_FRAGMENTS),
        )
        for m in ModelCatalog().list()
    ]

    return CapabilitiesPalette(
        capabilities=capabilities, model_catalog=model_catalog
    )

"""Capability-registry palette API (API-02 / D-11).

This router surfaces the **hardened capability registry** to the composer: a
single authenticated ``GET /api/capabilities`` returns the palette the frontend
renders (the capability palette panel + the per-agent model picker). For every
registered ``(kind, name)`` it reports:

  * ``kind`` / ``name``  — the registry coordinate;
  * ``user_allowed``     — the CAP-03 trust flag (``is_user_allowed``): privileged
    kinds (exec/secrets/spawn/runtimes) surface ``False`` and the UI gates them
    off the user-grantable palette (T-08-08-ID);
  * ``config_schema``    — a forward-compat per-capability config slot. The
    capability ports (``base.py``) are one-method Protocols with no declared
    config schema today, so this is an empty object now; it is the stable place
    a future per-capability JSON schema lands without an API-shape change.

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
    """One palette entry — a registered ``(kind, name)`` with its trust flag."""

    kind: str
    name: str
    user_allowed: bool
    # Forward-compat per-capability config slot. Empty today (the ports declare
    # no config schema); the stable place a future JSON schema lands.
    config_schema: dict = {}


class ModelCatalogEntry(BaseModel):
    """One model-picker entry, projected from ``ModelCatalog`` (MODEL-04)."""

    id: str
    label: str
    description: str
    tier: str
    cost_class: str
    provider: str
    context_window: int
    user_allowed: bool


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
        capabilities.append(
            CapabilityEntry(
                kind=kind,
                name=name,
                user_allowed=registry.is_user_allowed(kind, name),
                config_schema={},
            )
        )

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
        )
        for m in ModelCatalog().list()
    ]

    return CapabilitiesPalette(
        capabilities=capabilities, model_catalog=model_catalog
    )

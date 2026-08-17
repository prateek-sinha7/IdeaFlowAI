"""Tests for the ModelCatalog data capability (MODEL-04) and its INV-12 projections.

Covers the kernel-pure catalog field set, lookup behavior, cost_class assignment
(N11), tier↔cost_class consistency, user_allowed-all-true (incl. Opus), kernel
import purity, plus the Task-2 registry-membership + AVAILABLE_MODELS-projection +
single-source-grep (INV-12) assertions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from agents.capabilities.model_catalog import ModelCatalog, ModelEntry

# The seven selectable model ids (authoritative — sourced from the catalog itself).
_EXPECTED_IDS = {
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu.anthropic.claude-sonnet-4-6",
    "eu.anthropic.claude-sonnet-4-20250514-v1:0",
    "eu.anthropic.claude-opus-4-5-20251101-v1:0",
    "eu.anthropic.claude-opus-4-6-v1",
}

# Canonical tier↔cost_class mapping (D-04 store-both consistency).
_TIER_TO_COST_CLASS = {
    "fast": "cheap",
    "balanced": "standard",
    "powerful": "premium",
}

_FIELDS = {
    "id",
    "label",
    "description",
    "tier",
    "cost_class",
    "provider",
    "context_window",
    "user_allowed",
    "vision",
}


# --- Test 1: field set ------------------------------------------------------


def test_catalog_lists_five_fully_fielded_entries() -> None:
    entries = ModelCatalog().list()
    assert len(entries) == 7
    for entry in entries:
        assert isinstance(entry, ModelEntry)
        for field in _FIELDS:
            assert hasattr(entry, field), f"{entry.id} missing field {field}"
        assert isinstance(entry.id, str) and entry.id
        assert isinstance(entry.label, str) and entry.label
        assert isinstance(entry.description, str) and entry.description
        assert isinstance(entry.context_window, int) and entry.context_window > 0
        # Every catalog model (Claude 4.5/4.6) is vision-capable (IMAGE-INPUT §3
        # Layer 5) — vision gates image input at ingress.
        assert entry.vision is True, f"{entry.id} must be vision-capable"


# --- Test 2: ids / get / is_allowed -----------------------------------------


def test_ids_get_and_is_allowed() -> None:
    catalog = ModelCatalog()
    assert set(catalog.ids()) == _EXPECTED_IDS
    assert len(catalog.ids()) == 7  # no duplicates

    for model_id in _EXPECTED_IDS:
        assert catalog.is_allowed(model_id) is True
        entry = catalog.get(model_id)
        assert entry is not None and entry.id == model_id

    assert catalog.is_allowed("garbage") is False
    assert catalog.get("garbage") is None
    # Opus 4.6 specifically is allowed (no gate, N11).
    assert catalog.is_allowed("eu.anthropic.claude-opus-4-6-v1") is True
    assert catalog.is_allowed("not-a-model") is False


# --- Test 3: cost_class assignment (N11) ------------------------------------


def test_cost_class_assignment() -> None:
    by_id = {e.id: e for e in ModelCatalog().list()}
    assert by_id["eu.anthropic.claude-haiku-4-5-20251001-v1:0"].cost_class == "cheap"
    assert by_id["us.anthropic.claude-3-5-haiku-20241022-v1:0"].cost_class == "cheap"
    assert by_id["eu.anthropic.claude-sonnet-4-5-20250929-v1:0"].cost_class == "standard"
    assert by_id["eu.anthropic.claude-sonnet-4-6"].cost_class == "standard"
    assert by_id["eu.anthropic.claude-sonnet-4-20250514-v1:0"].cost_class == "standard"
    assert by_id["eu.anthropic.claude-opus-4-5-20251101-v1:0"].cost_class == "premium"
    assert by_id["eu.anthropic.claude-opus-4-6-v1"].cost_class == "premium"


# --- Test 4: tier↔cost_class consistency ------------------------------------


def test_tier_cost_class_consistency() -> None:
    for entry in ModelCatalog().list():
        assert entry.tier in _TIER_TO_COST_CLASS, f"unknown tier {entry.tier}"
        assert (
            _TIER_TO_COST_CLASS[entry.tier] == entry.cost_class
        ), f"{entry.id}: tier {entry.tier} ↔ cost_class {entry.cost_class} violates mapping"


# --- Test 5: user_allowed all true (incl. both Opus) ------------------------


def test_all_entries_user_allowed() -> None:
    entries = ModelCatalog().list()
    assert all(e.user_allowed for e in entries)
    opus = [e for e in entries if "opus" in e.id]
    assert len(opus) == 2
    assert all(e.user_allowed for e in opus)


# --- Test 6: kernel purity (no app.* import) --------------------------------


def test_catalog_is_kernel_pure() -> None:
    import agents.capabilities.model_catalog as module

    src = Path(module.__file__).read_text()
    # No app.* import anywhere in the module source.
    assert not re.search(r"^\s*(from|import)\s+app(\.|\s|$)", src, re.MULTILINE)
    # And the imported module graph carries no app.* dependency pulled by it.
    assert "app" not in {
        name.split(".")[0]
        for name in sys.modules
        if name.startswith("app.") and "model_catalog" in repr(sys.modules.get(name, ""))
    }


# --- Task 2: AVAILABLE_MODELS is a projection over the catalog (INV-12) ------


def test_available_models_is_projection() -> None:
    from app.api.settings import AVAILABLE_MODELS, _VALID_MODEL_IDS

    expected = [
        {"id": m.id, "name": m.label, "description": m.description, "tier": m.tier}
        for m in ModelCatalog().list()
    ]
    assert AVAILABLE_MODELS == expected
    # /api/settings response shape unchanged: EXACTLY {id, name, description, tier}.
    for model in AVAILABLE_MODELS:
        assert set(model.keys()) == {"id", "name", "description", "tier"}
    assert _VALID_MODEL_IDS == set(ModelCatalog().ids())


# --- Task 2: registry knows ('model_catalog','default') ---------------------


def test_registry_membership() -> None:
    from agents.capabilities.registry import CapabilityRegistry

    registry = CapabilityRegistry()
    assert registry.is_registered("model_catalog", "default") is True
    assert registry.is_registered("model_catalog", "garbage") is False


# --- Task 2: INV-12 single-source grep --------------------------------------


def test_single_source_grep() -> None:
    """Model-id literals appear in exactly ONE maintained list across
    backend/app/api + backend/agents/capabilities, namely model_catalog.py."""
    backend = Path(__file__).resolve().parents[2]
    roots = [backend / "app" / "api", backend / "agents" / "capabilities"]
    pattern = re.compile(r"claude-(haiku|sonnet|opus)-4")

    hits: set[str] = set()
    for root in roots:
        for py in root.rglob("*.py"):
            for line in py.read_text().splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if pattern.search(line):
                    hits.add(py.name)
                    break

    assert hits == {"model_catalog.py"}, f"model-id literals leaked into: {hits}"

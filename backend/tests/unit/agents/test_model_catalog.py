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

from agents.capabilities.model_catalog import (
    REASONING_EFFORT_LEVELS,
    ModelCatalog,
    ModelEntry,
    Reasoning,
)

# The eleven selectable model ids (authoritative — sourced from the catalog itself).
# GEO-01: eu.anthropic.claude-sonnet-5 added alongside the us. entry so the
# geo-prefix normalizer can validate the EU variant and manual EU overrides work.
_EXPECTED_IDS = {
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    # Pre-dates spec 020 — the US Haiku profile was added without bumping
    # this set or the counts below, so these two assertions were already red.
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    # spec 020 — Global-CRIS only; Terra is deliberately not offered.
    "global.openai.gpt-5.6-luna",
    "global.openai.gpt-5.6-sol",
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-sonnet-5",
    "eu.anthropic.claude-sonnet-5",
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
    "supports_prompt_caching",
    "reasoning",
}


# --- Test 1: field set ------------------------------------------------------


def test_catalog_lists_five_fully_fielded_entries() -> None:
    entries = ModelCatalog().list()
    # 11 = 9 Claude (incl. the us. Haiku 4.5 + us. Sonnet 5 geo twins) + 2 GPT-5.6.
    # Haiku 3.5 was removed 2026-09-22 — AWS serves it in no form in eu-north-1.
    assert len(entries) == 11
    for entry in entries:
        assert isinstance(entry, ModelEntry)
        for field in _FIELDS:
            assert hasattr(entry, field), f"{entry.id} missing field {field}"
        assert isinstance(entry.id, str) and entry.id
        assert isinstance(entry.label, str) and entry.label
        assert isinstance(entry.description, str) and entry.description
        assert isinstance(entry.context_window, int) and entry.context_window > 0
        # Every catalog model is vision-capable (IMAGE-INPUT §3 Layer 5) — vision
        # gates image input at ingress. Both GPT-5.6 models accept image input too.
        assert entry.vision is True, f"{entry.id} must be vision-capable"
        # spec 020 — reasoning is declared, never defaulted. A new entry that
        # forgot it would otherwise inherit a wire shape its provider may reject.
        assert isinstance(entry.reasoning, Reasoning), f"{entry.id} missing reasoning"
        assert entry.reasoning.mode in {"effort", "adaptive", "budget", "none"}
        # levels must be drawn from the documented superset, and `none` mode
        # must offer nothing at all.
        assert set(entry.reasoning.levels) <= set(REASONING_EFFORT_LEVELS) | {"on"}
        if entry.reasoning.mode == "none":
            assert entry.reasoning.levels == ()


# --- Test 2: ids / get / is_allowed -----------------------------------------


def test_ids_get_and_is_allowed() -> None:
    catalog = ModelCatalog()
    assert set(catalog.ids()) == _EXPECTED_IDS
    assert len(catalog.ids()) == 11  # no duplicates

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
    assert (
        by_id["eu.anthropic.claude-sonnet-4-5-20250929-v1:0"].cost_class == "standard"
    )
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

    src = Path(module.__file__).read_text(encoding="utf-8")
    # No app.* import anywhere in the module source.
    assert not re.search(r"^\s*(from|import)\s+app(\.|\s|$)", src, re.MULTILINE)
    # And the imported module graph carries no app.* dependency pulled by it.
    assert "app" not in {
        name.split(".")[0]
        for name in sys.modules
        if name.startswith("app.")
        and "model_catalog" in repr(sys.modules.get(name, ""))
    }


# --- Task 2: AVAILABLE_MODELS is a projection over the catalog (INV-12) ------


def test_available_models_is_projection() -> None:
    """AVAILABLE_MODELS projects the PICKER view; _VALID_MODEL_IDS stays complete.

    Spec 020 split the two. The picker shows one row per model
    (``selectable_models()`` drops the us./eu. duplicates, which GEO-01 collapses
    at resolve time anyway), while validation must keep accepting every catalog
    id — a saved workflow or an AGENT.md may name the hidden prefix.
    """
    from agents.model_policy import selectable_models
    from app.api.settings import AVAILABLE_MODELS, _VALID_MODEL_IDS

    expected = [
        {"id": m.id, "name": m.label, "description": m.description, "tier": m.tier}
        for m in selectable_models()
    ]
    assert AVAILABLE_MODELS == expected
    # /api/settings response shape unchanged: EXACTLY {id, name, description, tier}.
    for model in AVAILABLE_MODELS:
        assert set(model.keys()) == {"id", "name", "description", "tier"}
    # Still a projection OVER the catalog — never an id the catalog does not have.
    assert {m["id"] for m in AVAILABLE_MODELS} <= set(ModelCatalog().ids())
    # Validation is the COMPLETE set. If this ever narrows to the picker view,
    # every workflow saved against a hidden prefix starts 422-ing.
    assert _VALID_MODEL_IDS == set(ModelCatalog().ids())


def test_selectable_models_is_alphabetical() -> None:
    """The picker is alphabetical by label — the order a reader can predict.

    Pins the ORDER, not just the membership: ``_ENTRIES`` is authoring order and
    this projection is the only thing making it legible. A comparator change that
    silently reverts to catalog order fails here rather than in the dropdown.
    "Default" is not asserted because it is not in this list — every picker
    prepends it as its own first option.
    """
    from agents.model_policy import selectable_models

    labels = [m.label for m in selectable_models()]
    assert labels == sorted(labels), labels
    assert labels == [
        "Claude Haiku 4.5",
        "Claude Opus 4.5",
        "Claude Opus 4.6",
        "Claude Sonnet 4",
        "Claude Sonnet 4.5",
        "Claude Sonnet 4.6",
        "Claude Sonnet 5",
        "GPT-5.6 Luna",
        "GPT-5.6 Sol",
    ], labels


def test_selectable_models_hides_only_geo_duplicates() -> None:
    """Every hidden entry is a geo-variant of a shown one — nothing is lost.

    The guard that matters: hiding a model with no twin would silently remove it
    from every picker while leaving it valid, which reads as "the model vanished".
    """
    from agents.capabilities.model_catalog import normalize_model_id
    from agents.model_policy import selectable_models

    shown = selectable_models()
    shown_keys = {normalize_model_id(m.id) for m in shown}

    # One row per family, and every family still represented.
    assert len(shown) == len(
        shown_keys
    ), "selectable_models returned a duplicate family"
    assert shown_keys == {normalize_model_id(m.id) for m in ModelCatalog().list()}

    # And the ones it hid are geo-prefix variants, not distinct models.
    hidden = [m for m in ModelCatalog().list() if m not in shown]
    for h in hidden:
        assert any(
            normalize_model_id(s.id) == normalize_model_id(h.id) for s in shown
        ), h.id


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
    backend = Path(__file__).resolve().parents[3]
    roots = [backend / "app" / "api", backend / "agents" / "capabilities"]
    pattern = re.compile(r"claude-(haiku|sonnet|opus)-4")

    hits: set[str] = set()
    for root in roots:
        for py in root.rglob("*.py"):
            for line in py.read_text(encoding="utf-8").splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if pattern.search(line):
                    hits.add(py.name)
                    break

    assert hits == {"model_catalog.py"}, f"model-id literals leaked into: {hits}"

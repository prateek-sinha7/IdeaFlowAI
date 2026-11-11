"""Unit tests for the model projection in ``app.api.capabilities``.

Requirements: 41.7 (the builder flags stay out of the model-listing responses),
41.14 (the builder reuses the same projection), 49.2.
"""

from __future__ import annotations

import dataclasses

from agents.capabilities.model_catalog import ModelCatalog
from app.api.capabilities import ModelCatalogEntry, project_model_entry

_SONNET_5_5 = "eu.anthropic.claude-sonnet-5-5"

_EXPECTED_FIELDS = {
    "id",
    "label",
    "description",
    "tier",
    "cost_class",
    "provider",
    "context_window",
    "user_allowed",
    "input_rate_per_1m",
    "output_rate_per_1m",
    "cache_read_rate_per_1m",
    "cache_write_5m_rate_per_1m",
    "reasoning_mode",
    "reasoning_levels",
}


def test_model_catalog_entry_model_fields_have_no_builder_key_when_class_defined() -> (
    None
):
    assert [k for k in ModelCatalogEntry.model_fields if k.startswith("builder_")] == []


def test_model_catalog_entry_model_fields_match_pinned_set_when_class_defined() -> None:
    assert set(ModelCatalogEntry.model_fields) == _EXPECTED_FIELDS


def test_project_model_entry_output_is_unchanged_when_projecting_sonnet_5_5() -> None:
    entry = ModelCatalog().get(_SONNET_5_5)
    assert entry is not None

    projected = project_model_entry(entry).model_dump()

    assert projected == {
        "id": _SONNET_5_5,
        "label": "Claude Sonnet 5.5",
        "description": entry.description,
        "tier": "balanced",
        "cost_class": "standard",
        "provider": "bedrock",
        "context_window": 1000000,
        "user_allowed": True,
        "input_rate_per_1m": 2.0,
        "output_rate_per_1m": 10.0,
        "cache_read_rate_per_1m": 0.1,
        "cache_write_5m_rate_per_1m": 2.5,
        "reasoning_mode": "adaptive",
        "reasoning_levels": ["none", "low", "medium", "high", "xhigh", "max"],
    }


def test_project_model_entry_ignores_builder_flags_when_flags_differ() -> None:
    for entry in ModelCatalog().list():
        cleared = dataclasses.replace(
            entry,
            builder_chat=False,
            builder_step=False,
            builder_default_chat=False,
        )
        flagged = dataclasses.replace(
            entry,
            builder_chat=True,
            builder_step=True,
            builder_default_chat=True,
        )

        assert project_model_entry(flagged) == project_model_entry(cleared), entry.id


def test_project_model_entry_has_no_builder_key_when_dumped_for_any_entry() -> None:
    for entry in ModelCatalog().list():
        dumped = project_model_entry(entry).model_dump()

        assert [k for k in dumped if k.startswith("builder_")] == [], entry.id

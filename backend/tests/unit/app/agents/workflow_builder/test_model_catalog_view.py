"""Unit tests for ``app.agents.workflow_builder.model_catalog_view``.

Requirements: 41.8 (startup check on the default chat model), 41.13 (lists are
filtered by the tier's cost classes), 45.1 (no GPT flag), 49.2.
"""

from __future__ import annotations

import dataclasses

import pytest

from agents.capabilities.model_catalog import ModelCatalog
from app.agents.workflow_builder import model_catalog_view
from app.agents.workflow_builder.model_catalog_view import (
    assert_builder_catalog_valid,
    builder_models,
)

_HAIKU_5_5 = "eu.anthropic.claude-haiku-5-5"
_SONNET_5_5 = "eu.anthropic.claude-sonnet-5-5"
_OPUS_4_6 = "eu.anthropic.claude-opus-4-6-v1"
_GPT_LUNA = "global.openai.gpt-5.6-luna"


def _ids(entries) -> list[str]:
    return [e.id for e in entries]


def _entry(model_id: str):
    entry = ModelCatalog().get(model_id)
    assert entry is not None
    return entry


# --- builder_models: tier filtering -----------------------------------------


def test_builder_models_excludes_premium_models_when_tier_is_basic() -> None:
    view = builder_models("basic")

    assert _ids(view.chat) == [_HAIKU_5_5, _SONNET_5_5]
    assert _ids(view.step) == [_HAIKU_5_5, _SONNET_5_5]


@pytest.mark.parametrize("tier", ["pro", "hexaware", "enterprise"])
def test_builder_models_includes_premium_models_when_tier_allows_premium(
    tier: str,
) -> None:
    # Opus 4.6 is removed from the builder, so a premium tier gets the same lists as basic.
    view = builder_models(tier)

    assert _ids(view.chat) == [_HAIKU_5_5, _SONNET_5_5]
    assert _ids(view.step) == [_HAIKU_5_5, _SONNET_5_5]


def test_builder_models_treats_tier_as_basic_when_tier_is_unknown() -> None:
    assert builder_models("no-such-tier") == builder_models("basic")


@pytest.mark.parametrize("tier", ["basic", "pro", "hexaware", "enterprise"])
def test_builder_models_offers_no_gpt_model_when_any_tier(tier: str) -> None:
    view = builder_models(tier)

    assert all(".openai." not in e.id for e in (*view.chat, *view.step))


def test_builder_models_returns_catalog_entries_when_listing_chat() -> None:
    view = builder_models("pro")

    assert view.chat == (_entry(_HAIKU_5_5), _entry(_SONNET_5_5))


# --- builder_models: default chat model -------------------------------------


def test_builder_models_picks_sonnet_5_5_default_when_no_preference() -> None:
    assert builder_models("pro").default_chat_id == _SONNET_5_5


def test_builder_models_picks_preferred_model_when_it_is_offered() -> None:
    assert builder_models("pro", _HAIKU_5_5).default_chat_id == _HAIKU_5_5


def test_builder_models_ignores_preference_when_model_is_not_offered() -> None:
    # Opus 4.6 is not on the Chat_List for any tier, and GPT is never offered.
    assert builder_models("basic", _OPUS_4_6).default_chat_id == _SONNET_5_5
    assert builder_models("pro", _OPUS_4_6).default_chat_id == _SONNET_5_5
    assert builder_models("pro", _GPT_LUNA).default_chat_id == _SONNET_5_5


def test_builder_models_falls_back_to_first_offered_when_tier_lacks_standard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        model_catalog_view.TIER_MODEL_COST_CLASSES, "cheap-only", {"cheap"}
    )

    view = builder_models("cheap-only")

    assert _ids(view.chat) == [_HAIKU_5_5]
    assert view.default_chat_id == _HAIKU_5_5


def test_builder_models_returns_empty_default_when_tier_offers_no_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        model_catalog_view.TIER_MODEL_COST_CLASSES, "premium-only", {"premium"}
    )

    view = builder_models("premium-only")

    assert view.chat == ()
    assert view.step == ()
    assert view.default_chat_id == ""


# --- assert_builder_catalog_valid -------------------------------------------


def test_assert_builder_catalog_valid_passes_when_catalog_is_the_real_one() -> None:
    assert_builder_catalog_valid(ModelCatalog().list())


def test_assert_builder_catalog_valid_raises_when_no_default_chat_model() -> None:
    entries = [
        dataclasses.replace(e, builder_default_chat=False)
        for e in ModelCatalog().list()
    ]

    with pytest.raises(RuntimeError, match="exactly one builder_default_chat"):
        assert_builder_catalog_valid(entries)


def test_assert_builder_catalog_valid_raises_when_two_default_chat_models() -> None:
    entries = [
        dataclasses.replace(e, builder_chat=True, builder_default_chat=True)
        if e.id == _OPUS_4_6
        else e
        for e in ModelCatalog().list()
    ]

    with pytest.raises(RuntimeError, match="exactly one builder_default_chat"):
        assert_builder_catalog_valid(entries)


def test_assert_builder_catalog_valid_raises_when_default_is_not_on_chat_list() -> None:
    entries = [
        dataclasses.replace(e, builder_chat=False) if e.id == _SONNET_5_5 else e
        for e in ModelCatalog().list()
    ]

    with pytest.raises(RuntimeError, match="must also set builder_chat"):
        assert_builder_catalog_valid(entries)


@pytest.mark.parametrize("flag", ["builder_chat", "builder_step"])
def test_assert_builder_catalog_valid_raises_when_gpt_model_carries_flag(
    flag: str,
) -> None:
    entries = [
        dataclasses.replace(e, **{flag: True}) if e.id == _GPT_LUNA else e
        for e in ModelCatalog().list()
    ]

    with pytest.raises(RuntimeError, match=r"GPT models must not carry builder flags"):
        assert_builder_catalog_valid(entries)

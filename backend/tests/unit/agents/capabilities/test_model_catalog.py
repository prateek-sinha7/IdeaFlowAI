"""Unit tests for the AI Workflow Builder flags on ``ModelEntry``.

Requirements: 41.2 (Chat_List members and the default), 41.4 (Step_List members),
41.5 (flags are opt-in and off by default), 45.1 (no GPT entry carries a flag).

Decided: Haiku 5.5 is on the Chat_List and the Step_List; Opus 4.6 carries no
builder flags. Q-59 (Opus on the Chat_List) remains open.
"""

from __future__ import annotations

from agents.capabilities.model_catalog import (
    ModelCatalog,
    ModelEntry,
    Pricing,
    Reasoning,
)

_SONNET_5_5 = "eu.anthropic.claude-sonnet-5-5"
_HAIKU_5_5 = "eu.anthropic.claude-haiku-5-5"

_BUILDER_FLAGS = ("builder_chat", "builder_step", "builder_default_chat")


def _ids_with(flag: str) -> set[str]:
    return {e.id for e in ModelCatalog().list() if getattr(e, flag)}


def test_builder_chat_flag_marks_sonnet_and_haiku_only_when_catalog_loaded() -> None:
    assert _ids_with("builder_chat") == {_SONNET_5_5, _HAIKU_5_5}


def test_builder_chat_flag_excludes_opus_4_6_when_catalog_loaded() -> None:
    opus = ModelCatalog().get("eu.anthropic.claude-opus-4-6-v1")

    assert opus is not None
    assert opus.builder_chat is False


def test_builder_step_flag_marks_haiku_and_sonnet_when_catalog_loaded() -> None:
    assert _ids_with("builder_step") == {_HAIKU_5_5, _SONNET_5_5}


def test_builder_default_chat_flag_marks_sonnet_5_5_alone_when_catalog_loaded() -> None:
    assert _ids_with("builder_default_chat") == {_SONNET_5_5}


def test_builder_default_chat_flag_implies_builder_chat_when_catalog_loaded() -> None:
    defaults = [e for e in ModelCatalog().list() if e.builder_default_chat]

    assert defaults
    assert all(e.builder_chat for e in defaults)


def test_builder_flags_carry_no_flag_when_entry_is_a_gpt_model() -> None:
    gpt_entries = [e for e in ModelCatalog().list() if ".openai." in e.id]

    assert gpt_entries, "the catalog is expected to hold GPT entries"
    for entry in gpt_entries:
        assert [f for f in _BUILDER_FLAGS if getattr(entry, f)] == [], entry.id


def test_model_entry_builder_flags_default_to_false_when_not_passed() -> None:
    entry = ModelEntry(
        id="test.model",
        label="Test",
        description="",
        tier="fast",
        cost_class="cheap",
        provider="bedrock",
        context_window=1,
        user_allowed=True,
        pricing=Pricing(0.0, 0.0, 0.0, 0.0, 0.0),
        vision=False,
        supports_prompt_caching=False,
        reasoning=Reasoning(mode="none", levels=(), default_effort=None),
    )

    assert [getattr(entry, f) for f in _BUILDER_FLAGS] == [False, False, False]


def test_model_catalog_flags_stay_off_when_entry_is_neither_builder_model() -> None:
    flagged = _ids_with("builder_chat") | _ids_with("builder_step")
    unflagged = [e for e in ModelCatalog().list() if e.id not in flagged]

    assert unflagged
    for entry in unflagged:
        assert [f for f in _BUILDER_FLAGS if getattr(entry, f)] == [], entry.id

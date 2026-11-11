"""Property tests for the builder model and effort admission checks.

# Feature: ai-workflow-builder, Property 19: Model and effort checks follow the filtered catalog

For any tier, model id and effort, ``check_chat_choice`` accepts a message if
and only if the model is on that tier's filtered Chat_List and the effort is
one of its levels (or ``None`` when it has none). For any tier, both lists
contain only entries whose cost class the tier allows, and never a GPT entry.

**Validates: Requirements 26.1, 26.3, 41.13, 45.1**

The expected outcome is computed from the raw catalog entries, their builder
flags and ``TIER_MODEL_COST_CLASSES``, not from the view under test.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agents.capabilities.model_catalog import ModelCatalog, ModelEntry
from app.agents.workflow_builder.model_catalog_view import (
    EFFORT_NOT_ALLOWED,
    MODEL_NOT_ALLOWED,
    MODEL_NOT_ENTITLED,
    builder_models,
    check_chat_choice,
)
from app.core.entitlements import TIER_MODEL_COST_CLASSES

_ENTRIES: tuple[ModelEntry, ...] = tuple(ModelCatalog().list())
_CATALOG_IDS: tuple[str, ...] = tuple(e.id for e in _ENTRIES)
_ALL_LEVELS: tuple[str, ...] = tuple(
    sorted({level for e in _ENTRIES for level in e.reasoning.levels})
)

# Real tiers plus an unknown one, which must fail closed to ``basic``.
_TIERS = st.sampled_from([*TIER_MODEL_COST_CLASSES, "unknown-tier"])
_MODEL_IDS = st.one_of(
    st.sampled_from(_CATALOG_IDS),
    st.text(min_size=0, max_size=20),
)
_EFFORTS = st.one_of(
    st.none(),
    st.sampled_from(_ALL_LEVELS),
    st.text(min_size=0, max_size=10),
)


def _is_gpt(entry: ModelEntry) -> bool:
    return ".openai." in entry.id


def _allowed_classes(tier: str) -> set[str]:
    return TIER_MODEL_COST_CLASSES.get(tier, TIER_MODEL_COST_CLASSES["basic"])


def _expected_code(tier: str, model_id: str, effort: str | None) -> str | None:
    """The refusal code the spec demands, derived from the raw catalog."""
    entry = next((e for e in _ENTRIES if e.id == model_id), None)
    if entry is None or _is_gpt(entry) or not entry.builder_chat:
        return MODEL_NOT_ALLOWED
    if entry.cost_class not in _allowed_classes(tier):
        return MODEL_NOT_ENTITLED
    levels = entry.reasoning.levels
    effort_ok = effort is None if not levels else effort in levels
    return None if effort_ok else EFFORT_NOT_ALLOWED


# Feature: ai-workflow-builder, Property 19: Model and effort checks follow the filtered catalog
@settings(max_examples=100)
@given(tier=_TIERS, model_id=_MODEL_IDS, effort=_EFFORTS)
def test_check_chat_choice_accepts_only_when_model_and_effort_are_offered(
    tier: str, model_id: str, effort: str | None
) -> None:
    view = builder_models(tier)

    refusal = check_chat_choice(_ENTRIES, view, model_id, effort)

    expected = _expected_code(tier, model_id, effort)
    assert (refusal.code if refusal else None) == expected


# Feature: ai-workflow-builder, Property 19: Model and effort checks follow the filtered catalog
@settings(max_examples=100)
@given(tier=_TIERS, model_id=_MODEL_IDS, effort=_EFFORTS)
def test_check_chat_choice_accepts_iff_choice_is_on_filtered_chat_list(
    tier: str, model_id: str, effort: str | None
) -> None:
    view = builder_models(tier)
    on_chat_list = {e.id: e for e in view.chat}

    refusal = check_chat_choice(_ENTRIES, view, model_id, effort)

    entry = on_chat_list.get(model_id)
    if entry is None:
        assert refusal is not None
    else:
        levels = entry.reasoning.levels
        effort_ok = effort is None if not levels else effort in levels
        assert (refusal is None) is effort_ok


# Feature: ai-workflow-builder, Property 19: Model and effort checks follow the filtered catalog
@settings(max_examples=100)
@given(tier=_TIERS)
def test_builder_models_lists_only_allowed_cost_classes_and_no_gpt_when_any_tier(
    tier: str,
) -> None:
    view = builder_models(tier)
    allowed = _allowed_classes(tier)

    for entry in (*view.chat, *view.step):
        assert entry.cost_class in allowed
        assert not _is_gpt(entry)
    assert all(e.builder_chat for e in view.chat)
    assert all(e.builder_step for e in view.step)

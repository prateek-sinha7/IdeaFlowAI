"""Property tests for ``assert_builder_catalog_valid``.

# Feature: ai-workflow-builder, Property 20: Catalog flags are valid or startup fails

For any assignment of builder flags to catalog entries,
``assert_builder_catalog_valid`` raises if and only if there is not exactly one
default chat model, the default is not on the Chat_List, or a GPT entry
carries any builder flag.

**Validates: Requirements 41.8, 41.9**

Entries are copies of a real catalog entry with the id and the three builder
flags replaced, so the check runs on genuine ``ModelEntry`` objects. Ids are
unique within one example.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from agents.capabilities.model_catalog import ModelCatalog, ModelEntry
from app.agents.workflow_builder.model_catalog_view import (
    assert_builder_catalog_valid,
)

_BASE_ENTRY: ModelEntry = ModelCatalog().list()[0]


@dataclass(frozen=True)
class _Spec:
    """Flags and provider kind for one generated entry."""

    is_gpt: bool
    chat: bool
    step: bool
    default: bool


def _build(specs: list[_Spec]) -> list[ModelEntry]:
    return [
        replace(
            _BASE_ENTRY,
            id=f"global.openai.model-{i}" if s.is_gpt else f"eu.anthropic.model-{i}",
            builder_chat=s.chat,
            builder_step=s.step,
            builder_default_chat=s.default,
        )
        for i, s in enumerate(specs)
    ]


def _expected_valid(specs: list[_Spec]) -> bool:
    """Independent statement of the rule, written from the property text."""
    defaults = [s for s in specs if s.default]
    if len(defaults) != 1:
        return False
    if not defaults[0].chat:
        return False
    return not any(s.is_gpt and (s.chat or s.step or s.default) for s in specs)


_ANY_SPEC = st.builds(
    _Spec,
    is_gpt=st.booleans(),
    chat=st.booleans(),
    step=st.booleans(),
    default=st.booleans(),
)

# Arbitrary flag assignments, including empty catalogs.
_ANY_SPECS = st.lists(_ANY_SPEC, min_size=0, max_size=6)

# A catalog that satisfies every rule: one chat-flagged default, other
# Claude entries with any flags, GPT entries with none.
_VALID_SPECS = st.tuples(
    st.builds(
        _Spec,
        is_gpt=st.just(False),
        chat=st.just(True),
        step=st.booleans(),
        default=st.just(True),
    ),
    st.lists(
        st.builds(
            _Spec,
            is_gpt=st.just(False),
            chat=st.booleans(),
            step=st.booleans(),
            default=st.just(False),
        ),
        max_size=4,
    ),
    st.lists(
        st.builds(
            _Spec,
            is_gpt=st.just(True),
            chat=st.just(False),
            step=st.just(False),
            default=st.just(False),
        ),
        max_size=3,
    ),
).flatmap(lambda parts: st.permutations([parts[0], *parts[1], *parts[2]]))


@settings(max_examples=100)
@given(specs=_ANY_SPECS)
def test_assert_builder_catalog_valid_raises_iff_flags_break_a_rule_when_flags_are_arbitrary(
    specs: list[_Spec],
) -> None:
    entries = _build(specs)

    if _expected_valid(specs):
        assert_builder_catalog_valid(entries)
    else:
        with pytest.raises(RuntimeError):
            assert_builder_catalog_valid(entries)


@settings(max_examples=100)
@given(specs=_VALID_SPECS)
def test_assert_builder_catalog_valid_passes_when_catalog_satisfies_every_rule(
    specs: list[_Spec],
) -> None:
    assert_builder_catalog_valid(_build(list(specs)))


@settings(max_examples=100)
@given(
    specs=_VALID_SPECS,
    flag=st.sampled_from(["builder_chat", "builder_step", "builder_default_chat"]),
)
def test_assert_builder_catalog_valid_raises_when_a_gpt_entry_gains_any_flag(
    specs: list[_Spec], flag: str
) -> None:
    entries = _build(list(specs))
    entries.append(replace(_BASE_ENTRY, id="global.openai.extra", **{flag: True}))

    with pytest.raises(RuntimeError):
        assert_builder_catalog_valid(entries)

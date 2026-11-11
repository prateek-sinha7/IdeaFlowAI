"""Properties of ADF conversion: plain text survives the round trip (normalized)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.connectors.tools.adf import adf_to_text, text_to_adf

_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029",
    ),
    max_size=200,
)


def _normalized(text: str) -> str:
    """Paragraphs are runs of non-blank lines; paragraphs join with a blank line."""
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    return "\n\n".join("\n".join(lines) for lines in paragraphs)


@settings(max_examples=300)
@given(text=_TEXT)
def test_adf_to_text_keeps_the_text_when_text_goes_through_adf(text: str) -> None:
    assert adf_to_text(text_to_adf(text)) == _normalized(text)


@settings(max_examples=300)
@given(text=_TEXT)
def test_text_to_adf_emits_only_non_empty_text_nodes_when_given_any_text(
    text: str,
) -> None:
    doc = text_to_adf(text)

    assert doc["type"] == "doc" and doc["version"] == 1
    for paragraph in doc["content"]:
        assert paragraph["type"] == "paragraph"
        for node in paragraph["content"]:
            assert node["type"] in {"text", "hardBreak"}
            if node["type"] == "text":
                assert node["text"].strip()


@settings(max_examples=200)
@given(text=_TEXT)
def test_text_to_adf_is_stable_when_converted_twice(text: str) -> None:
    once = adf_to_text(text_to_adf(text))

    assert adf_to_text(text_to_adf(once)) == once

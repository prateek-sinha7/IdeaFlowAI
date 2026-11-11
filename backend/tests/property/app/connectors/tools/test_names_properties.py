"""Properties of namespaced connector tool names: round trip, rejection and length bound."""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from app.connectors.tools.names import (
    MAX_TOOL_NAME_LENGTH,
    SEPARATOR,
    format_tool_name,
    parse_tool_name,
)

_KEY = st.from_regex(r"^[a-z][a-z0-9]{1,31}$", fullmatch=True)
_SOURCE = st.from_regex(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,60}$", fullmatch=True)
_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@settings(max_examples=300)
@given(key=_KEY, source=_SOURCE)
def test_format_tool_name_round_trips_through_parse_when_name_fits(
    key: str, source: str
) -> None:
    name = f"{key}{SEPARATOR}{source}"
    if len(name) > MAX_TOOL_NAME_LENGTH:
        return

    assert format_tool_name(key, source) == name
    assert parse_tool_name(name) == (key, source)


@settings(max_examples=300)
@given(key=_KEY, source=_SOURCE)
def test_format_tool_name_never_exceeds_limit_when_it_returns(
    key: str, source: str
) -> None:
    try:
        name = format_tool_name(key, source)
    except ValueError:
        assert len(f"{key}{SEPARATOR}{source}") > MAX_TOOL_NAME_LENGTH
        return

    assert len(name) <= MAX_TOOL_NAME_LENGTH


@settings(max_examples=300)
@given(key=_KEY, source=st.text(max_size=40))
def test_format_tool_name_rejects_source_when_it_breaks_the_rule(
    key: str, source: str
) -> None:
    if (
        _SOURCE_RE.match(source)
        and len(key) + len(SEPARATOR) + len(source) <= MAX_TOOL_NAME_LENGTH
    ):
        return

    try:
        format_tool_name(key, source)
    except ValueError:
        return
    raise AssertionError("an invalid source name was accepted")


@settings(max_examples=300)
@given(name=st.text(max_size=80))
def test_parse_tool_name_returns_valid_parts_or_none_when_given_any_text(
    name: str,
) -> None:
    parsed = parse_tool_name(name)

    if parsed is None:
        return
    key, source = parsed
    assert format_tool_name(key, source) == name
    assert len(name) <= MAX_TOOL_NAME_LENGTH

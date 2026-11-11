"""Namespaced tool names: format, parse and the rejection rules."""

from __future__ import annotations

import pytest

from app.connectors.tools.names import (
    MAX_TOOL_NAME_LENGTH,
    format_tool_name,
    parse_tool_name,
)


class TestFormatToolName:
    def test_format_tool_name_joins_with_double_underscore_when_valid(self) -> None:
        assert format_tool_name("github", "create_pull_request") == (
            "github__create_pull_request"
        )

    @pytest.mark.parametrize("key", ["", "G", "1jira", "j", "ji-ra", "ji_ra", "a" * 33])
    def test_format_tool_name_raises_when_key_invalid(self, key: str) -> None:
        with pytest.raises(ValueError, match="connector key"):
            format_tool_name(key, "tool")

    @pytest.mark.parametrize("source", ["", "_lead", "-lead", "has space", "dot.name"])
    def test_format_tool_name_raises_when_source_invalid(self, source: str) -> None:
        with pytest.raises(ValueError, match="tool name"):
            format_tool_name("github", source)

    def test_format_tool_name_raises_when_longer_than_limit(self) -> None:
        source = "t" * (MAX_TOOL_NAME_LENGTH - len("github__") + 1)

        with pytest.raises(ValueError, match="too long"):
            format_tool_name("github", source)

    def test_format_tool_name_accepts_exactly_the_limit_when_name_is_64_long(
        self,
    ) -> None:
        source = "t" * (MAX_TOOL_NAME_LENGTH - len("github__"))

        assert len(format_tool_name("github", source)) == MAX_TOOL_NAME_LENGTH


class TestParseToolName:
    def test_parse_tool_name_splits_at_first_separator_when_source_has_underscores(
        self,
    ) -> None:
        assert parse_tool_name("jira__search__issues") == ("jira", "search__issues")

    @pytest.mark.parametrize(
        "name",
        ["jira", "jira_search", "__x", "Jira__x", "jira__", "jira__ x", "x" * 70],
    )
    def test_parse_tool_name_returns_none_when_name_invalid(self, name: str) -> None:
        assert parse_tool_name(name) is None

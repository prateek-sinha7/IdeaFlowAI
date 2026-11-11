"""ADF conversion: plain text to a minimal document and arbitrary ADF to plain text."""

from __future__ import annotations

from typing import Any

from app.connectors.tools.adf import MAX_ADF_DEPTH, adf_to_text, text_to_adf
from tests.fakes.jira_api import load_fixture


class TestTextToAdf:
    def test_text_to_adf_builds_one_paragraph_when_text_is_one_line(self) -> None:
        doc = text_to_adf("hello")

        assert doc == {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}
            ],
        }

    def test_text_to_adf_splits_paragraphs_when_text_has_blank_lines(self) -> None:
        doc = text_to_adf("one\n\n\ntwo")

        assert [p["content"][0]["text"] for p in doc["content"]] == ["one", "two"]

    def test_text_to_adf_uses_hard_breaks_when_lines_are_consecutive(self) -> None:
        doc = text_to_adf("a\nb")

        assert doc["content"][0]["content"] == [
            {"type": "text", "text": "a"},
            {"type": "hardBreak"},
            {"type": "text", "text": "b"},
        ]

    def test_text_to_adf_returns_empty_content_when_text_is_blank(self) -> None:
        assert text_to_adf(" \n\t\n")["content"] == []

    def test_text_to_adf_treats_windows_line_endings_as_newlines_when_present(
        self,
    ) -> None:
        assert adf_to_text(text_to_adf("a\r\nb\r\n\r\nc")) == "a\nb\n\nc"

    def test_text_to_adf_never_emits_empty_text_nodes_when_lines_are_blank(
        self,
    ) -> None:
        doc = text_to_adf("a\n   \nb")

        texts = [n["text"] for p in doc["content"] for n in p["content"]]
        assert all(texts)


class TestAdfToText:
    def test_adf_to_text_returns_empty_when_value_is_not_adf(self) -> None:
        for value in (None, "plain", 3, [], {"type": "unknown"}):
            assert adf_to_text(value) == ""

    def test_adf_to_text_renders_lists_and_paragraphs_when_issue_description(
        self,
    ) -> None:
        issue: dict[str, Any] = load_fixture("jira_issue.json")

        text = adf_to_text(issue["fields"]["description"])

        assert text == (
            "Users see a 500 after sign in.\n\n- Reproduce on staging\n- Check the auth logs"
        )

    def test_adf_to_text_renders_hard_breaks_when_comment_body(self) -> None:
        comments: dict[str, Any] = load_fixture("jira_comments.json")

        assert (
            adf_to_text(comments["comments"][0]["body"])
            == "Seen on staging\nand in production"
        )

    def test_adf_to_text_numbers_ordered_lists_when_items_present(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": t}],
                                }
                            ],
                        }
                        for t in ("first", "second")
                    ],
                }
            ],
        }

        assert adf_to_text(doc) == "1. first\n2. second"

    def test_adf_to_text_uses_mention_and_card_attributes_when_inline_nodes(
        self,
    ) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "mention", "attrs": {"text": "@ada"}},
                        {"type": "text", "text": " see "},
                        {"type": "inlineCard", "attrs": {"url": "https://x.example/1"}},
                    ],
                }
            ],
        }

        assert adf_to_text(doc) == "@ada see https://x.example/1"

    def test_adf_to_text_stops_at_depth_limit_when_document_is_deeply_nested(
        self,
    ) -> None:
        node: dict[str, Any] = {"type": "text", "text": "deep"}
        for _ in range(MAX_ADF_DEPTH + 5):
            node = {"type": "blockquote", "content": [node]}

        assert adf_to_text(node) == ""

    def test_adf_to_text_skips_non_text_children_when_content_is_malformed(
        self,
    ) -> None:
        doc = {
            "type": "doc",
            "content": [
                "junk",
                {"type": "paragraph", "content": [{"type": "text", "text": 5}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "ok"}]},
            ],
        }

        assert adf_to_text(doc) == "ok"

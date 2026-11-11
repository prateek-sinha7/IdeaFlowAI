"""Atlassian Document Format (ADF) conversion for the Jira tools.

``text_to_adf`` turns plain text into a minimal ADF document: blank lines separate
paragraphs and a single newline becomes a hard break. ``adf_to_text`` flattens any
ADF value Jira returns (comments, descriptions) to plain text; node types it does
not know contribute their text children, so unfamiliar content degrades to text
instead of failing.
"""

from __future__ import annotations

from typing import Any, Final

#: Deepest ADF nesting ``adf_to_text`` follows (a hostile document cannot recurse forever).
MAX_ADF_DEPTH: Final = 40

_INLINE_ATTR_TEXT: Final = {"mention": "text", "emoji": "text", "status": "text"}
_LIST_TYPES: Final = {"bulletList", "orderedList"}
_BLOCK_SEPARATOR: Final = "\n\n"


def text_to_adf(text: str) -> dict[str, Any]:
    """Return an ADF document for plain ``text``.

    Consecutive non-blank lines form one paragraph (joined by hard breaks); blank
    lines separate paragraphs. Text with no visible content gives an empty document.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in normalized.split("\n"):
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)

    content: list[dict[str, Any]] = []
    for lines in paragraphs:
        inline: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            if index:
                inline.append({"type": "hardBreak"})
            inline.append({"type": "text", "text": line})
        content.append({"type": "paragraph", "content": inline})
    return {"type": "doc", "version": 1, "content": content}


def adf_to_text(node: object) -> str:
    """Return the plain text of an ADF value (``None`` and non-ADF values give ``""``)."""
    return _render(node, 0).strip("\n")


def _render(node: object, depth: int) -> str:
    if depth > MAX_ADF_DEPTH or not isinstance(node, dict):
        return ""
    node_type = node.get("type")
    if node_type == "text":
        text = node.get("text")
        return text if isinstance(text, str) else ""
    if node_type == "hardBreak":
        return "\n"
    if node_type in _INLINE_ATTR_TEXT:
        attrs = node.get("attrs")
        value = (
            attrs.get(_INLINE_ATTR_TEXT[node_type]) if isinstance(attrs, dict) else None
        )
        return value if isinstance(value, str) else ""
    if node_type == "inlineCard":
        attrs = node.get("attrs")
        url = attrs.get("url") if isinstance(attrs, dict) else None
        return url if isinstance(url, str) else ""

    children = node.get("content")
    if not isinstance(children, list):
        return ""
    if node_type in _LIST_TYPES:
        return _render_list(children, depth, ordered=node_type == "orderedList")
    parts = [_render(child, depth + 1) for child in children]
    if node_type in {"paragraph", "heading", "codeBlock", "tableCell", "tableHeader"}:
        return "".join(parts)
    if node_type in {"listItem", "tableRow"}:
        return "\n".join(part for part in parts if part)
    # doc, blockquote, panel, table and unknown containers: blocks apart by a blank line.
    return _BLOCK_SEPARATOR.join(part for part in parts if part)


def _render_list(items: list[Any], depth: int, *, ordered: bool) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        marker = f"{index}. " if ordered else "- "
        body = _render(item, depth + 1)
        if body:
            lines.append(marker + body.replace("\n", "\n  "))
    return "\n".join(lines)

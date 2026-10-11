"""``_tool_result_text`` — the ``tool_result`` event never carries base64."""

from __future__ import annotations

import base64

from app.agents.deep_agent_runner import _tool_result_text


def test_plain_string_passes_through_unchanged() -> None:
    assert _tool_result_text("✓ done") == "✓ done"
    assert _tool_result_text("") == ""


def test_block_list_without_media_keeps_legacy_str() -> None:
    blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert _tool_result_text(blocks) == str(blocks)


def test_image_block_becomes_a_marker_not_base64() -> None:
    b64 = base64.b64encode(b"\x89PNG" + b"\0" * 4096).decode()
    out = _tool_result_text(
        [{"type": "image", "base64": b64, "mime_type": "image/png"}]
    )
    assert out == "[image image/png 4 KB]"
    assert b64 not in out


def test_text_blocks_survive_next_to_media() -> None:
    out = _tool_result_text(
        [
            {"type": "text", "text": "pages/05/image-2.png"},
            {"type": "image", "base64": "AAAA", "mime_type": "image/png"},
        ]
    )
    assert out == "pages/05/image-2.png\n[image image/png 0 KB]"

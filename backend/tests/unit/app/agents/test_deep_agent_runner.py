"""Unit tests for ``app/agents/deep_agent_runner.py``.

Covers the reserved-path READ denial text (the denial message must list every
agent-readable reserved prefix, derived from ``AGENT_READABLE_RESERVED`` itself,
so it cannot drift from what the guard allows) and the image-payload guard's
per-image ceilings: a block over the base64 byte limit or with a side over
8000 px is replaced by a placeholder that never invites a re-read (FIX-550).
"""

from __future__ import annotations

import base64
import io
import struct
import zlib
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from PIL import Image, features

from app.agents.deep_agent_runner import (
    _DUPLICATE_IMAGE_PLACEHOLDER,
    _OVERSIZED_IMAGE_PLACEHOLDER,
    _OVERSIZED_SIDE_PLACEHOLDER,
    _ImagePayloadGuardMiddleware,
    _largest_media_side,
    _read_denied_message,
    _ReservedPathGuardMiddleware,
)
from app.agents.sandbox import AGENT_READABLE_RESERVED


def test_read_denied_message_lists_every_agent_readable_prefix_when_built():
    message = _read_denied_message("ls", "/.logs")

    assert message.startswith("Tool 'ls' is not permitted to read '/.logs'")
    for prefix in AGENT_READABLE_RESERVED:
        assert prefix in message
    assert ".chain/" not in message


def test_refusal_returns_listing_message_when_reading_unreadable_reserved_path():
    request = SimpleNamespace(
        tool_call={"name": "ls", "args": {"path": "/.logs"}, "id": "call-1"}
    )

    refusal = _ReservedPathGuardMiddleware()._refusal(request)

    assert refusal is not None
    assert refusal.content == _read_denied_message("ls", "/.logs")


# ── image-payload guard ──────────────────────────────────────────────────────


def _b64_image(width: int, height: int, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 100, 50)).save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _image_msg(path: str, tool_call_id: str, payload: str) -> ToolMessage:
    """A ToolMessage shaped like deepagents' binary ``read_file`` result."""
    return ToolMessage(
        content=[{"type": "image", "base64": payload, "mime_type": "image/png"}],
        tool_call_id=tool_call_id,
        name="read_file",
        additional_kwargs={"read_file_path": path, "read_file_media_type": "image/png"},
    )


class _Request:
    """Minimal ModelRequest stand-in — only `messages` + `override` are used."""

    def __init__(self, messages):
        self.messages = messages

    def override(self, **kw):
        return _Request(kw.get("messages", self.messages))


def _prune(messages: list) -> list:
    return _ImagePayloadGuardMiddleware(keep=2)._prune(_Request(messages)).messages


def _kept_image(msg: ToolMessage) -> bool:
    return isinstance(msg.content, list) and any(
        b.get("type") == "image" for b in msg.content
    )


def test_prune_replaces_block_with_size_placeholder_when_base64_exceeds_limit():
    out = _prune([_image_msg("/a.png", "c1", "A" * 5_000_001), AIMessage("noted")])

    assert out[0].content == _OVERSIZED_IMAGE_PLACEHOLDER.format(path="/a.png")


def test_prune_keeps_block_when_base64_is_exactly_at_limit():
    out = _prune([_image_msg("/a.png", "c1", "A" * 5_000_000), AIMessage("noted")])

    assert _kept_image(out[0])


def test_prune_replaces_block_with_side_placeholder_when_height_exceeds_8000_px():
    out = _prune(
        [_image_msg("/tall.png", "c1", _b64_image(10, 8001)), AIMessage("noted")]
    )

    assert out[0].content == _OVERSIZED_SIDE_PLACEHOLDER.format(path="/tall.png")


def test_prune_replaces_block_with_side_placeholder_when_width_exceeds_8000_px():
    out = _prune(
        [_image_msg("/wide.png", "c1", _b64_image(8001, 10)), AIMessage("noted")]
    )

    assert out[0].content == _OVERSIZED_SIDE_PLACEHOLDER.format(path="/wide.png")


def test_prune_keeps_block_when_longest_side_is_8000_px():
    out = _prune(
        [_image_msg("/ok.png", "c1", _b64_image(10, 8000)), AIMessage("noted")]
    )

    assert _kept_image(out[0])


@pytest.mark.parametrize("payload", ["iVBORw0KGgo" + "A" * 512, "!!!not-base64"])
def test_prune_keeps_block_when_image_header_is_undecodable(payload: str):
    out = _prune([_image_msg("/bad.png", "c1", payload), AIMessage("noted")])

    assert _kept_image(out[0])


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "GIF", "WEBP"])
def test_largest_media_side_reads_size_when_block_is_png_jpeg_gif_or_webp(fmt: str):
    if fmt == "WEBP" and not features.check("webp"):
        pytest.skip("Pillow built without WebP")

    msg = _image_msg("/x", "c1", _b64_image(40, 8100, fmt))

    assert _largest_media_side(msg) == 8100


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def test_largest_media_side_returns_over_limit_when_header_is_a_decompression_bomb():
    ihdr = struct.pack(">IIBBBBB", 20_000, 10_000, 8, 2, 0, 0, 0)
    header = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", b"")
        + _png_chunk(b"IEND", b"")
    )
    msg = _image_msg("/bomb.png", "c1", base64.b64encode(header).decode("ascii"))

    assert _largest_media_side(msg) > 8000


def test_prune_retains_one_block_when_same_small_path_is_read_twice():
    small = _b64_image(10, 10)
    out = _prune(
        [
            _image_msg("/p.png", "c1", small),
            _image_msg("/p.png", "c2", small),
            AIMessage("noted"),
        ]
    )

    assert sum(1 for m in out if isinstance(m, ToolMessage) and _kept_image(m)) == 1
    assert out[0].content == _DUPLICATE_IMAGE_PLACEHOLDER.format(path="/p.png")
    assert _kept_image(out[1])


@pytest.mark.parametrize(
    "placeholder", [_OVERSIZED_IMAGE_PLACEHOLDER, _OVERSIZED_SIDE_PLACEHOLDER]
)
def test_prune_placeholders_never_invite_a_re_read_when_image_is_oversized(
    placeholder: str,
):
    text = placeholder.format(path="/a.png")

    assert "Do NOT read it again" in text
    assert "re-read" not in text.lower()

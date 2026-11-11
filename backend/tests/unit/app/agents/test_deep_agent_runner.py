"""Unit tests for ``app/agents/deep_agent_runner.py``.

Covers the reserved-path READ denial text (the denial message must list every
agent-readable reserved prefix, derived from ``AGENT_READABLE_RESERVED`` itself,
so it cannot drift from what the guard allows) and the image-payload guard's
per-image ceilings: a block over the base64 byte limit or with a side over
8000 px is replaced by a placeholder that never invites a re-read (FIX-550).
Also covers the additive ``backend`` / ``extra_middleware`` / ``history``
parameters (AI workflow builder, design §2.4): omitted, the middleware list and
the first-call messages are unchanged.
"""

from __future__ import annotations

import base64
import io
import struct
import zlib
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from PIL import Image, features

from app.agents import deep_agent_runner as runner_module
from app.agents.deep_agent_runner import (
    _DUPLICATE_IMAGE_PLACEHOLDER,
    _OVERSIZED_IMAGE_PLACEHOLDER,
    _OVERSIZED_SIDE_PLACEHOLDER,
    _RESERVED_PATH_GUARD_SENTINEL,
    DeepAgentRunner,
    _BedrockCachePointsMiddleware,
    _ImagePayloadGuardMiddleware,
    _largest_media_side,
    _read_denied_message,
    _ReservedPathGuardMiddleware,
    _ToolFilterMiddleware,
    _TruncatedWriteGuardMiddleware,
)
from app.agents.sandbox import AGENT_READABLE_RESERVED
from app.agents.tool_recovery import ToolFailureRecoveryMiddleware


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


# ---------------------------------------------------------------------------
# Additive DeepAgentRunner parameters: backend / extra_middleware / history
# (AI workflow builder, design §2.4). With none of them supplied the graph, the
# middleware list and the input messages must be exactly what they were before.
# ---------------------------------------------------------------------------

#: Middleware classes every runner gets today, in order, with no sandbox and no
#: path-guard sentinel.
_BASE_MIDDLEWARE = [
    _ToolFilterMiddleware,
    _ImagePayloadGuardMiddleware,
    _BedrockCachePointsMiddleware,
    _TruncatedWriteGuardMiddleware,
]


class _CapturingModel(BaseChatModel):
    """In-memory chat model that records the messages of every model call."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, calls: list[list[BaseMessage]], **kwargs: Any) -> None:
        super().__init__(disable_streaming=True, **kwargs)
        object.__setattr__(self, "_calls", calls)

    @property
    def _llm_type(self) -> str:
        return "capturing-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_CapturingModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # type: ignore[override]
        self._calls.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage("ok"))])


class _TaggedMiddleware(AgentMiddleware[Any, Any, Any]):
    """No-op middleware used to observe where ``extra_middleware`` lands."""


class _OtherTaggedMiddleware(AgentMiddleware[Any, Any, Any]):
    """Second no-op middleware, to observe ordering among extras."""


@pytest.fixture
def captured_graph_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``create_deep_agent`` with a recorder (no graph is compiled)."""
    captured: dict[str, Any] = {}

    def _fake_create_deep_agent(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(runner_module, "create_deep_agent", _fake_create_deep_agent)
    return captured


def _build_runner(**kwargs: Any) -> DeepAgentRunner:
    return DeepAgentRunner(
        "sys",
        kwargs.pop("tools", []),
        model=_CapturingModel([]),
        exclude_builtin_tools=True,
        **kwargs,
    )


def _classes(captured: dict[str, Any]) -> list[type]:
    return [type(m) for m in captured["middleware"]]


def test_init_builds_todays_middleware_list_when_new_arguments_are_omitted(
    captured_graph_kwargs: dict[str, Any],
):
    _build_runner()

    # Tool-failure recovery is on by default; it is the only addition to the base list.
    assert _classes(captured_graph_kwargs) == [
        *_BASE_MIDDLEWARE,
        ToolFailureRecoveryMiddleware,
    ]
    assert captured_graph_kwargs["backend"] is None


def test_init_builds_todays_middleware_list_when_new_arguments_are_empty(
    captured_graph_kwargs: dict[str, Any],
):
    _build_runner(extra_middleware=(), backend=None)

    assert _classes(captured_graph_kwargs) == [
        *_BASE_MIDDLEWARE,
        ToolFailureRecoveryMiddleware,
    ]
    assert captured_graph_kwargs["backend"] is None


def test_init_omits_tool_recovery_when_recover_tool_failures_is_false(
    captured_graph_kwargs: dict[str, Any],
):
    """The workflow builder opts out: its tool results stay byte for byte as before."""
    _build_runner(recover_tool_failures=False)

    assert _classes(captured_graph_kwargs) == _BASE_MIDDLEWARE


def test_init_appends_extra_middleware_after_path_guard_when_guard_is_attached(
    captured_graph_kwargs: dict[str, Any],
):
    extras = [_TaggedMiddleware(), _OtherTaggedMiddleware()]

    # The guard sentinel attaches the path guard without needing a sandbox.
    _build_runner(tools=[_RESERVED_PATH_GUARD_SENTINEL], extra_middleware=extras)

    # Recovery sits after the guard (a refusal is never rewritten) and before the extras
    # (a caller's observer stays inside it and still sees the raw exception).
    assert _classes(captured_graph_kwargs) == [
        *_BASE_MIDDLEWARE,
        _ReservedPathGuardMiddleware,
        ToolFailureRecoveryMiddleware,
        _TaggedMiddleware,
        _OtherTaggedMiddleware,
    ]
    assert captured_graph_kwargs["middleware"][-2:] == extras


def test_init_appends_extra_middleware_last_when_no_path_guard_is_attached(
    captured_graph_kwargs: dict[str, Any],
):
    _build_runner(extra_middleware=[_TaggedMiddleware()])

    assert _classes(captured_graph_kwargs) == [
        *_BASE_MIDDLEWARE,
        ToolFailureRecoveryMiddleware,
        _TaggedMiddleware,
    ]


def test_init_keeps_extra_middleware_last_when_recovery_is_off(
    captured_graph_kwargs: dict[str, Any],
):
    _build_runner(extra_middleware=[_TaggedMiddleware()], recover_tool_failures=False)

    assert _classes(captured_graph_kwargs) == [*_BASE_MIDDLEWARE, _TaggedMiddleware]


def test_init_uses_backend_verbatim_when_backend_is_given(
    captured_graph_kwargs: dict[str, Any],
):
    backend = object()

    _build_runner(backend=backend)

    assert captured_graph_kwargs["backend"] is backend
    assert _ReservedPathGuardMiddleware not in _classes(captured_graph_kwargs)


def test_init_raises_value_error_when_backend_and_run_sandbox_are_both_given(
    captured_graph_kwargs: dict[str, Any],
):
    with pytest.raises(ValueError, match="not both"):
        _build_runner(backend=object(), run_sandbox=SimpleNamespace(root="unused"))

    assert captured_graph_kwargs == {}  # nothing was built


async def _model_calls(history: list[BaseMessage] | None) -> list[list[BaseMessage]]:
    calls: list[list[BaseMessage]] = []
    runner = DeepAgentRunner(
        "sys",
        [],
        model=_CapturingModel(calls),
        exclude_builtin_tools=True,
        thread_id="additive-test",
    )
    kwargs: dict[str, Any] = {} if history is None else {"history": history}
    _ = [event async for event in runner.astream_events("now", **kwargs)]
    return calls


def _without_system(messages: list[BaseMessage]) -> list[tuple[str, Any]]:
    return [(m.type, m.content) for m in messages if m.type != "system"]


@pytest.mark.asyncio
async def test_astream_events_sends_only_the_human_message_when_history_is_omitted():
    calls = await _model_calls(None)

    assert _without_system(calls[0]) == [("human", "now")]


@pytest.mark.asyncio
async def test_astream_events_sends_only_the_human_message_when_history_is_none():
    calls: list[list[BaseMessage]] = []
    runner = DeepAgentRunner(
        "sys",
        [],
        model=_CapturingModel(calls),
        exclude_builtin_tools=True,
        thread_id="additive-test",
    )

    _ = [event async for event in runner.astream_events("now", history=None)]

    assert _without_system(calls[0]) == [("human", "now")]


@pytest.mark.asyncio
async def test_astream_events_preserves_history_order_before_the_human_message():
    history: list[BaseMessage] = [
        HumanMessage("first question"),
        AIMessage("first answer"),
        HumanMessage("second question"),
        AIMessage("second answer"),
    ]

    calls = await _model_calls(history)

    assert _without_system(calls[0]) == [
        ("human", "first question"),
        ("ai", "first answer"),
        ("human", "second question"),
        ("ai", "second answer"),
        ("human", "now"),
    ]


@pytest.mark.asyncio
async def test_astream_events_keeps_message_id_when_a_human_message_is_given():
    calls: list[list[BaseMessage]] = []
    runner = DeepAgentRunner(
        "sys",
        [],
        model=_CapturingModel(calls),
        exclude_builtin_tools=True,
        thread_id="additive-test",
    )

    _ = [
        event
        async for event in runner.astream_events(
            HumanMessage("now", id="turn:abc"), history=[AIMessage("earlier")]
        )
    ]

    humans = [m for m in calls[0] if m.type == "human"]
    assert [(m.id, m.content) for m in humans] == [("turn:abc", "now")]


class _ReasoningModel(_CapturingModel):
    """Fake model whose reply carries both visible text and reasoning content."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # type: ignore[override]
        reply = AIMessage(
            "reply-marker", additional_kwargs={"reasoning_content": "reasoning-marker"}
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])


async def _model_output_records(
    caplog: pytest.LogCaptureFixture, **runner_kwargs: Any
) -> list[str]:
    """Run one turn and return the messages logged on ``app.agents.model_output``."""
    runner = DeepAgentRunner(
        "sys",
        [],
        model=_ReasoningModel([]),
        exclude_builtin_tools=True,
        thread_id="log-test",
        **runner_kwargs,
    )
    with caplog.at_level("DEBUG", logger="app.agents.model_output"):
        _ = [event async for event in runner.astream_events("now")]
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.agents.model_output"
    ]


@pytest.mark.asyncio
async def test_astream_events_logs_thinking_and_output_when_log_model_output_is_default(
    caplog: pytest.LogCaptureFixture,
):
    messages = await _model_output_records(caplog)

    assert "output: reply-marker" in messages
    assert "thinking reasoning-marker" in messages


@pytest.mark.asyncio
async def test_astream_events_logs_no_thinking_or_output_when_log_model_output_is_false(
    caplog: pytest.LogCaptureFixture,
):
    messages = await _model_output_records(caplog, log_model_output=False)

    assert not any(m.startswith(("thinking", "output:")) for m in messages)
    assert "reply-marker" not in caplog.text
    assert "reasoning-marker" not in caplog.text

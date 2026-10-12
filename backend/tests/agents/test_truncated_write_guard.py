"""A write cut off at the output token limit gets an error naming the cause (run 7ef4faf8)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.deep_agent_runner import TRUNCATED_WRITE_MESSAGE, _TruncatedWriteGuardMiddleware


def _request(name, args, stop):
    call = {"name": name, "args": args, "id": "call-1"}
    turn = AIMessage(content="", tool_calls=[call], response_metadata={"stopReason": stop})
    return SimpleNamespace(tool_call=call, state={"messages": [turn]})


def _run(request):
    ran = []

    def handler(req):
        ran.append(req)
        return "written"

    return _TruncatedWriteGuardMiddleware().wrap_tool_call(request, handler), ran


def test_a_truncated_write_gets_the_explicit_error():
    for name in ("write_file", "edit_file"):
        result, ran = _run(_request(name, {"file_path": "synthesis.md"}, "max_tokens"))
        assert not ran
        assert isinstance(result, ToolMessage) and result.status == "error"
        assert result.content == TRUNCATED_WRITE_MESSAGE


def test_the_anthropic_stop_reason_key_is_read_too():
    call = {"name": "write_file", "args": {"file_path": "a.md", "content": ""}, "id": "c"}
    turn = AIMessage(content="", tool_calls=[call], response_metadata={"stop_reason": "max_tokens"})
    result, ran = _run(SimpleNamespace(tool_call=call, state={"messages": [turn]}))
    assert not ran and result.content == TRUNCATED_WRITE_MESSAGE


def test_normal_writes_are_unchanged():
    # A complete write, a truncated turn whose write still carried its content, a
    # write missing content on a normal turn (the tool's own error applies), and
    # any other tool: all go to the tool as before.
    for request in (
        _request("write_file", {"file_path": "a.md", "content": "# A"}, "tool_use"),
        _request("write_file", {"file_path": "a.md", "content": "# A"}, "max_tokens"),
        _request("write_file", {"file_path": "a.md"}, "tool_use"),
        _request("read_file", {"file_path": "a.md"}, "max_tokens"),
    ):
        result, ran = _run(request)
        assert ran and result == "written"


def test_the_async_path_guards_too():
    async def handler(req):
        return "written"

    result = asyncio.run(_TruncatedWriteGuardMiddleware().awrap_tool_call(
        _request("write_file", {"file_path": "a.md"}, "max_tokens"), handler))
    assert result.content == TRUNCATED_WRITE_MESSAGE

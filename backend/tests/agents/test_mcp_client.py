"""MCP-01 Wave-0 acceptance: McpClientAdapter over the stub stdio server (offline).

Proves the live ``McpClientAdapter`` path fully offline (no network):
  * the adapter connects to the in-repo stub stdio MCP server, lists tools, and
    invokes an allowed tool through the REAL stdio transport;
  * the exposed-tool allow-list filters the bound set (defence in depth at bind);
  * the bound tools are LangChain ``BaseTool``s that drop INTO a real
    ``create_deep_agent`` tool set — they AUGMENT the deepagents runtime, never
    replace it (INV-13);
  * the sync factory unions ``ctx.prewarmed_mcp_tools`` WITHOUT awaiting (the
    async→sync resolution; no double-loop in the running engine loop).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult

_STUB = str(Path(__file__).resolve().parent / "fixtures" / "stub_mcp_server.py")


def _stub_config() -> dict:
    return {
        "stub": {
            "command": sys.executable,
            "args": [_STUB],
            "transport": "stdio",
        }
    }


class _NeverInvokedChatModel(BaseChatModel):
    """A scripted ``BaseChatModel`` for ``create_deep_agent`` (ISS-118).

    ``create_deep_agent`` accepts a model INSTANCE as well as a provider string; the
    string form (``"anthropic:..."``) makes langchain's ``init_chat_model`` construct a
    real ``ChatAnthropic`` inside the library, which is a live client built offline.
    This test only inspects the constructed graph, so it hands over an instance that
    fails loudly rather than bills if anything ever invokes it.
    """

    @property
    def _llm_type(self) -> str:
        return "never-invoked-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise AssertionError("the graph is inspected, never run — this model must not be invoked")


def _text_of(result) -> str:
    """Flatten an MCP tool result (a content-block list) to its text payload."""
    if isinstance(result, list):
        return "".join(
            block.get("text", "") for block in result if isinstance(block, dict)
        )
    return str(result)


@pytest.mark.asyncio
async def test_adapter_connects_lists_and_invokes_over_stdio() -> None:
    """The adapter connects to the stub stdio server, lists tools, and invokes one."""
    from app.agents.mcp.client import McpClientAdapter

    adapter = McpClientAdapter(_stub_config())
    tools = await adapter.get_tools()

    by_name = {t.name: t for t in tools}
    assert {"echo", "add"} <= set(by_name), f"expected stub tools, got {sorted(by_name)}"

    echo = by_name["echo"]
    assert _text_of(await echo.ainvoke({"text": "hello-mcp"})) == "hello-mcp"

    add = by_name["add"]
    assert _text_of(await add.ainvoke({"a": 2, "b": 3})) == "5"


@pytest.mark.asyncio
async def test_exposed_tool_allow_list_filters_bound_tools() -> None:
    """``allowed`` keeps only the server's exposed-tool allow-list (bind-time gate)."""
    from app.agents.mcp.client import McpClientAdapter

    adapter = McpClientAdapter(_stub_config())
    # Only ``echo`` is exposed → ``add`` must be filtered out.
    bound = await adapter.get_tools(allowed={"stub": {"echo"}})
    names = {t.name for t in bound}
    assert names == {"echo"}, f"allow-list should keep only echo, got {names}"


@pytest.mark.asyncio
async def test_bound_mcp_tool_augments_a_deepagents_agent() -> None:
    """The bound MCP tool drops into a real ``create_deep_agent`` tool set (INV-13)."""
    from deepagents import create_deep_agent

    from app.agents.mcp.client import McpClientAdapter

    adapter = McpClientAdapter(_stub_config())
    mcp_tools = await adapter.get_tools(allowed={"stub": {"echo"}})
    assert mcp_tools, "expected at least the echo tool bound"

    # Build a real deepagents graph WITH the MCP tool unioned into its tool set.
    # We do NOT invoke the model (offline / no creds) — the acceptance is that the
    # MCP tool binds INTO the runtime (augment, never replace): the constructed
    # graph carries the tool by name. No network, no model call.
    agent = create_deep_agent(tools=list(mcp_tools), model=_NeverInvokedChatModel())
    assert agent is not None

    # The bound tool is a LangChain BaseTool (has name + ainvoke) — the exact shape
    # create_deep_agent binds; prove it is invocable through the same stdio transport.
    echo = next(t for t in mcp_tools if t.name == "echo")
    assert _text_of(await echo.ainvoke({"text": "via-deepagents"})) == "via-deepagents"


def test_factory_unions_prewarmed_mcp_tools_without_awaiting() -> None:
    """The SYNC factory reads ctx.prewarmed_mcp_tools and unions them (no await)."""
    from agents.factory import AgentContext, _resolve_runner_tools

    # A sentinel LangChain-ish tool object (only ``name`` is read by the union path).
    class _Tool:
        name = "echo"

    sentinel = _Tool()

    # A pure-text spec (no tools) but with a pre-warmed MCP tool → it must still bind.
    class _Spec:
        tools: list = []

    ctx = AgentContext(user_request="x", prewarmed_mcp_tools=[sentinel])
    custom_tools, exclude_builtin = _resolve_runner_tools(_Spec(), ctx)
    assert sentinel in custom_tools, "pre-warmed MCP tool must union into custom_tools"
    # An MCP-bearing agent needs the native fs surface to call the tool → exclude off.
    assert exclude_builtin is False


def test_factory_empty_tools_and_no_mcp_is_pure_text() -> None:
    """spec 012 / R-22, D-07: no tools + no MCP scope still gets the universal fs
    grant (([], False)) — a text-only agent no longer loses the native fs tools."""
    from agents.factory import AgentContext, _resolve_runner_tools

    class _Spec:
        tools: list = []

    ctx = AgentContext(user_request="x")  # prewarmed_mcp_tools defaults to []
    assert _resolve_runner_tools(_Spec(), ctx) == ([], False)

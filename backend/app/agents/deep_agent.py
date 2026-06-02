"""DeepAgent — LangGraph ReAct agent with tool-calling support.

Drop-in replacement for BaseAgent when an agent needs to:
  - Read files dynamically (template seeds, layout references)
  - Write multiple files (code generation)
  - Loop back based on tool results (lint → fix → re-check)
  - Decompose tasks visibly (todo_write)

Architecture (matches OpenDesign's daemon model):
  1. One agent session (analogous to one Claude Code process)
  2. Multiple tool calls within that session
  3. Each tool result feeds back into the same LLM context
  4. Streaming: text chunks AND tool events are yielded live

Usage:
    from app.agents.tools.workspace import AgentWorkspace, make_workspace_tools
    from app.agents.deep_agent import DeepAgent

    ws = AgentWorkspace()
    agent = DeepAgent(
        system_prompt="You are a code generator...",
        tools=make_workspace_tools(ws),
        max_tokens=60000,
    )
    async for event in agent.astream_events("Write a React dashboard"):
        if event["type"] == "chunk":
            yield event["chunk"]
        elif event["type"] == "tool_call":
            yield {"type": "tool_call", "tool": event["tool"], ...}

    final_output = ws.to_final_output()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings

logger = logging.getLogger("app.agents.deep_agent")


class DeepAgentConfigurationError(Exception):
    pass


class DeepAgent:
    """LangGraph ReAct agent that can call tools within a single session.

    Compared to BaseAgent (which does exactly one LLM call), DeepAgent runs
    an agentic loop: the LLM decides whether to call a tool, calls it, gets
    the result, and continues until it produces a final answer or reaches
    max_iterations.

    Auto-selects provider:
    - ANTHROPIC_API_KEY set → langchain-anthropic (local dev)
    - Otherwise            → langchain-aws ChatBedrockConverse (production)
    """

    def __init__(
        self,
        system_prompt: str,
        tools: list,
        max_tokens: int = 60000,
        max_iterations: int = 20,
        model: str | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = tools
        self.max_iterations = max_iterations

        if settings.ANTHROPIC_API_KEY:
            # Local dev — use Anthropic direct API
            from langchain_anthropic import ChatAnthropic
            model_id = model or settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5-20251001"
            self.model_id = model_id
            llm = ChatAnthropic(
                model=model_id,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=max_tokens,
            )
        else:
            # Production — use AWS Bedrock
            from langchain_aws import ChatBedrockConverse
            model_id = model or settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID
            region = settings.AWS_REGION
            if not model_id or not region:
                raise DeepAgentConfigurationError(
                    "No LLM configured. Set ANTHROPIC_API_KEY for local dev or "
                    "BEDROCK_INFERENCE_PROFILE_ID + AWS_REGION for production."
                )
            self.model_id = model_id
            llm = ChatBedrockConverse(
                model=model_id,
                region_name=region,
                max_tokens=max_tokens,
            )

        # Bind tools to the LLM so the provider knows the function signatures
        self.llm_with_tools = llm.bind_tools(tools) if tools else llm

        logger.debug(
            "DeepAgent init: model=%s tools=%d max_iter=%d",
            self.model_id, len(tools), max_iterations,
        )

    # -----------------------------------------------------------------------
    # Main streaming interface
    # -----------------------------------------------------------------------

    async def astream_events(
        self, user_message: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the ReAct loop and yield structured events.

        Event shapes:
          {type: "chunk",       chunk: str}             — LLM text token
          {type: "tool_call",   tool: str, args: dict}  — agent calling a tool
          {type: "tool_result", tool: str, result: str} — tool execution result
          {type: "done",        output: str}             — final text output
          {type: "error",       error: str}

        THREADING MODEL:
        Each LLM call runs in asyncio.to_thread() to prevent blocking the event loop.
        Both langchain_anthropic and langchain_aws (boto3) can block the event loop
        during large-input calls — serialization, token counting, and sometimes the
        HTTP streaming itself runs synchronously. Running in a thread ensures:
          - asyncio.timeout() in the caller ALWAYS fires on schedule
          - Heartbeats, reconnect handlers, and other coroutines keep running
          - No event loop freeze regardless of input size or model response time
        """
        from langchain_core.messages import ToolMessage

        messages: list = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message),
        ]

        tool_map = {t.name: t for t in self.tools}
        full_output = ""

        for iteration in range(self.max_iterations):
            # ── LLM call in thread — never blocks the event loop ──────────
            # We run the synchronous .stream() (not .astream()) in a thread.
            # This is correct even for langchain_anthropic: under the hood,
            # astream() calls the sync stream() via run_in_executor anyway,
            # but with extra overhead. Using to_thread directly is cleaner and
            # guarantees the event loop is free during the entire call.
            #
            # The thread returns (chunks, ai_message, error) as a tuple.
            # We then yield the chunks from the event loop (safe — no thread access).
            ai_message_container: list = []  # [ai_msg] or []
            error_container: list = []       # [exc] or []
            chunks_container: list = []      # [chunk_str, ...]

            def _sync_llm_iteration(msgs: list) -> None:
                """Run one LLM iteration synchronously in a thread."""
                try:
                    ai_msg = None
                    for chunk in self.llm_with_tools.stream(msgs):
                        text = _extract_text(chunk.content)
                        if text:
                            chunks_container.append(text)
                        if ai_msg is None:
                            ai_msg = chunk
                        else:
                            try:
                                ai_msg = ai_msg + chunk
                            except Exception:
                                pass  # some chunk types don't support +
                    if ai_msg is not None:
                        ai_message_container.append(ai_msg)
                except Exception as exc:
                    error_container.append(exc)

            # Run in thread with a generous per-call timeout.
            # The timeout here uses asyncio.wait_for on the to_thread coroutine,
            # which ALWAYS works because to_thread is a proper coroutine that
            # yields control to the event loop.
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(_sync_llm_iteration, list(messages)),
                    timeout=300,  # 5 min max per LLM call — enough for any size
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "LLM call timed out (5min) on iteration %d — using partial output",
                    iteration,
                )
                if full_output:
                    yield {"type": "done", "output": full_output}
                else:
                    yield {"type": "error", "error": "LLM call timed out after 5 minutes"}
                return

            # Check for error from thread
            if error_container:
                exc = error_container[0]
                logger.exception("LLM call failed on iteration %d: %s", iteration, exc)
                yield {"type": "error", "error": str(exc)}
                return

            # Yield all accumulated text chunks
            for text in chunks_container:
                full_output += text
                yield {"type": "chunk", "chunk": text}

            if not ai_message_container:
                break

            ai_message = ai_message_container[0]
            messages.append(ai_message)

            # ── Emit token usage for this iteration ───────────────────────
            meta = getattr(ai_message, "usage_metadata", None)
            if meta:
                yield {
                    "type": "usage",
                    "input_tokens": meta.get("input_tokens", 0),
                    "output_tokens": meta.get("output_tokens", 0),
                }

            # ── Check for tool calls ──────────────────────────────────────
            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                # No tool calls → final response
                yield {"type": "done", "output": full_output}
                return

            # ── Execute each tool call (also in thread for safety) ────────
            for tc in tool_calls:
                tool_name = tc.get("name") or tc.get("function", {}).get("name", "unknown")
                tool_args = tc.get("args") or tc.get("function", {}).get("arguments", {})
                tool_id = tc.get("id", "")

                yield {"type": "tool_call", "tool": tool_name, "args": tool_args}

                if tool_name in tool_map:
                    try:
                        # Run tool in thread — tools may do file I/O or heavy computation
                        result = await asyncio.to_thread(tool_map[tool_name].invoke, tool_args)
                        result_str = str(result)
                    except Exception as exc:
                        result_str = f"Tool error: {exc}"
                else:
                    result_str = f"Unknown tool: {tool_name}"

                yield {"type": "tool_result", "tool": tool_name, "result": result_str}

                messages.append(
                    ToolMessage(content=result_str, tool_call_id=tool_id)
                )

        # Hit max_iterations — yield whatever we have
        yield {"type": "done", "output": full_output}

    async def astream(self, user_message: str) -> AsyncGenerator[str, None]:
        """Simplified interface: yield only text chunks (compatible with BaseAgent).

        Tool calls happen silently — callers that only care about the text
        output (e.g. the existing orchestrator_v2 context builder) can use
        this and it Just Works.
        """
        async for event in self.astream_events(user_message):
            if event["type"] == "chunk":
                yield event["chunk"]

    async def astream_with_usage(
        self, user_message: str
    ) -> AsyncGenerator[Any, None]:
        """Stream text chunks then yield a final TokenUsage — mirrors BaseAgent.

        The orchestrator calls this for text-only agents (tools=[]).
        Runs in asyncio.to_thread() to prevent blocking the event loop.
        """
        from app.agents.base import TokenUsage

        messages: list = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message),
        ]

        chunks_out: list[str] = []
        last_chunk_container: list = []

        def _sync_stream() -> None:
            last = None
            for chunk in self.llm_with_tools.stream(messages):
                text = _extract_text(chunk.content)
                if text:
                    chunks_out.append(text)
                last = chunk
            if last is not None:
                last_chunk_container.append(last)

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_sync_stream),
                timeout=300,
            )
        except asyncio.TimeoutError:
            logger.warning("astream_with_usage timed out after 5min")

        for text in chunks_out:
            yield text

        usage = TokenUsage()
        if last_chunk_container:
            meta = getattr(last_chunk_container[0], "usage_metadata", None)
            if meta:
                usage = TokenUsage(
                    input_tokens=meta.get("input_tokens", 0),
                    output_tokens=meta.get("output_tokens", 0),
                    total_tokens=meta.get("total_tokens", 0),
                    cache_read_tokens=meta.get("cache_read_input_tokens", 0),
                    cache_write_tokens=meta.get("cache_creation_input_tokens", 0),
                )
                if usage.total_tokens == 0:
                    usage.total_tokens = usage.input_tokens + usage.output_tokens
        yield usage

    async def run(self, user_message: str) -> str:
        """Run to completion and return the full text output."""
        output = ""
        async for event in self.astream_events(user_message):
            if event["type"] == "chunk":
                output += event["chunk"]
        return output


# ---------------------------------------------------------------------------
# Helper: extract text from a chunk (mirrors BaseAgent._extract_text)
# ---------------------------------------------------------------------------


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""

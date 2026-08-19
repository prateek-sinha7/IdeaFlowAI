"""app/agents/deep_agent_runner.py — Phase-1 adapter over a ``deepagents`` graph.

This is the **heart of the deepagents migration** (spec
``specs/002-deepagents-migration/plan.md`` → Phase 1). It wraps a
``deepagents.create_deep_agent`` ``CompiledStateGraph`` and re-exposes the
*exact* streaming contract the execution engine already consumes from the
legacy ``app/agents/deep_agent.DeepAgent``, so a later phase can swap the
implementation in with a single dispatch change.

Status / scope (read before extending):
  - **Purely additive.** This module is NOT wired into ``agents/factory.py`` or
    ``agents/execution_engine/engine.py`` yet. The factory keeps returning the
    legacy ``DeepAgent`` until Phase 2; the engine keeps its current dispatch
    until Phase 3.
  - **No legacy / back-compat shims** (per the plan's hard invariants). The one
    local middleware below is a *forward* implementation that owns a stable
    public-API equivalent of a deepagents-private class — see its docstring.
  - This task (#24) fully implements ``__init__`` and the class's public shape;
    the streaming methods are deliberate stubs filled by tasks #26–#28.

Engine contract this class reproduces (verified against
``app/agents/deep_agent.py`` and ``agents/execution_engine/engine.py:742–832,
1088–1098``). The engine consumes an agent object via:
  - ``agent.astream_events(msg)`` → async-yields dicts with a ``type`` key:
    ``{"type":"chunk","chunk":str}``,
    ``{"type":"usage","input_tokens":int,"output_tokens":int,"cache_read_tokens":int,"cache_write_tokens":int}``,
    ``{"type":"tool_call","tool":str,"args":dict}``,
    ``{"type":"tool_result","tool":str,"result":str}``,
    ``{"type":"done","output":str}``, ``{"type":"error","error":str}``.
    (The engine builds output from ``chunk`` events and does not read ``done``;
    ``tool=="report_task_complete"`` drives the ``task_progress`` sentinel.)
  - ``agent.astream_with_usage(msg)`` → text chunks (str) then a final
    ``TokenUsage`` (``app/agents/types.py``) — used for text-only agents
    (``tools == []``).
  - ``agent.astream(msg)`` → text chunks only.
  - ``agent.run(msg)`` → the full text ``str``.
  - ``agent.model_id: str`` and ``agent.tools: list`` attributes.

Construction (per plan §4 / Phase 1):
  ``create_deep_agent(model=build_model(model)|<instance>, tools=tools,
  system_prompt=system_prompt, subagents=None, <task-tool excluded>,
  backend=FilesystemBackend(root_dir=<RunSandbox.root>, virtual_mode=True),
  checkpointer=<Phase-0 factory>, interrupt_on=…)`` driven with
  ``config={"configurable":{"thread_id": run_id},
  "recursion_limit": settings.AGENT_RECURSION_LIMIT}``.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, AsyncGenerator, Awaitable, Callable

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import AgentMiddleware

from app.agents.model_factory import build_model, model_identifier
from app.core.config import settings

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langchain_core.language_models import BaseChatModel

    from app.agents.sandbox import RunSandbox

logger = logging.getLogger("app.agents.deep_agent_runner")
model_logger = logging.getLogger("app.agents.model_output")
tool_logger = logging.getLogger("app.agents.tool_output")


def _one_line(text: str, limit: int) -> str:
    """Collapse whitespace and truncate — trace lines must stay one line."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "..."


# ---------------------------------------------------------------------------
# Built-in tool names + exclusion sets
# ---------------------------------------------------------------------------
#
# ``create_deep_agent`` always injects a built-in tool suite via its mandatory
# middleware and auto-adds a "general-purpose" sub-agent that exposes the
# ``task`` tool. Passing ``subagents=None`` does NOT remove ``task`` — verified
# empirically: the auto-added GP sub-agent re-introduces it. The robust,
# model-agnostic way to drop tools from what the model actually sees is a
# late-stack tool-filter middleware (this is the same approach the library uses
# internally via its private ``_ToolExclusionMiddleware``). See ``_ToolFilterMiddleware``.

#: The library sub-agent dispatch tool. Excluded ALWAYS so the model can never
#: spawn its own sub-agents — the engine orchestrates per-task sub-agents itself
#: (plan Phase 4). This is the only exclusion task #24 needs.
_LIBRARY_SUBAGENT_TOOL: str = "task"

#: The full built-in tool suite ``create_deep_agent`` can inject (filesystem +
#: planning + sub-agent dispatch + sandbox execute). ``execute`` is only exposed
#: when the backend is a sandbox backend; ``FilesystemBackend`` is not, so it is
#: a harmless no-op in the set today, kept for forward-compatibility.
#:
#: **Task #25 hook:** text-only agents (``tools == []``) must exclude this entire
#: set so they stream pure text (no tool chips leak into the UI). That is exactly
#: what ``exclude_builtin_tools=True`` does below.
_BUILTIN_TOOLS: frozenset[str] = frozenset(
    {
        "task",
        "write_todos",
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
    }
)


# F4 (13-02): fabricated tool-call XML spans live Haiku emits AS PLAIN TEXT when a
# tool-less prompt implies file/tool actions. Non-greedy ``[\s\S]*?`` spans (DOTALL-
# equivalent) — linear on max_tokens-capped model output, no nested quantifiers
# (T-13-02-04 ReDoS disposition).
_FABRICATED_TOOL_XML_RE: re.Pattern[str] = re.compile(
    r"<function_calls>[\s\S]*?</function_calls>"
    r"|<invoke\b[^>]*>[\s\S]*?</invoke>"
)

# WR-01 (13 review fix): a TRUNCATED span — output cut at max_tokens mid-XML — has
# no closing tag, so the paired regex above leaves it intact. Any opener that
# SURVIVES the paired sub is by definition unmatched; strip from it to
# end-of-string. ``<invoke\b`` (no ``>`` required) also catches a cut mid-attribute
# (e.g. ``<invoke name="wri``). Linear — single pass, no nested quantifiers.
_UNTERMINATED_TOOL_XML_RE: re.Pattern[str] = re.compile(
    r"(?:<function_calls>|<invoke\b)[\s\S]*\Z"
)


def _strip_fabricated_tool_xml(text: str) -> str:
    """Strip fabricated tool-call XML spans from a TOOL-LESS agent's output (F4).

    Removes ``<function_calls>...</function_calls>`` spans and standalone fabricated
    ``<invoke ...>...</invoke>`` spans, plus an UNTERMINATED trailing span (output
    truncated at max_tokens mid-XML — WR-01). Applied ONLY to the authoritative
    output of agents constructed with ``exclude_builtin_tools=True`` and zero custom
    tools — a tool-using agent's legitimate output is never touched.

    Streamed ``chunk`` events are intentionally NOT filtered: this defense-in-depth
    targets the AUTHORITATIVE output that feeds downstream agent context and
    deliverables, not the live UI token stream. The engine applies the SAME
    transform to its chunk-joined output via :meth:`DeepAgentRunner.sanitize_output`
    (WR-01 — the engine never consumes the ``done`` event).

    When the pattern is absent the input is returned unchanged (same object), so
    scripted-model characterization outputs (which never contain the pattern) stay
    byte-identical.
    """
    if "<function_calls>" not in text and "<invoke" not in text:
        return text
    cleaned = _FABRICATED_TOOL_XML_RE.sub("", text)
    return _UNTERMINATED_TOOL_XML_RE.sub("", cleaned)


def _tool_name(tool: Any) -> str | None:
    """Best-effort tool name from a ``BaseTool`` or a dict tool spec."""
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


class _ToolFilterMiddleware(AgentMiddleware[Any, Any, Any]):
    """Strip named tools from the model request, before the model sees them.

    Functionally identical to deepagents' own private
    ``deepagents.middleware._tool_exclusion._ToolExclusionMiddleware``: it runs
    late in the assembled stack (deepagents inserts caller ``middleware=`` after
    the tool-injecting middleware) and filters ``request.tools`` by name, so it
    removes both caller tools and middleware-injected built-ins (``task``, the
    filesystem suite, …) from what the model is offered.

    We own a local copy rather than importing the library's underscore-prefixed
    class so the adapter does not depend on a private, non-exported symbol that
    could move between ``deepagents`` releases. It is built only on stable,
    public LangChain middleware APIs (``AgentMiddleware``,
    ``ModelRequest.override``). This is a *forward* implementation, not a
    legacy/back-compat shim — there is no old code path it bridges to.
    """

    def __init__(self, *, excluded: frozenset[str]) -> None:
        self._excluded = excluded

    def _filter(self, request: "ModelRequest") -> "ModelRequest":
        if not self._excluded:
            return request
        kept = [t for t in request.tools if _tool_name(t) not in self._excluded]
        return request.override(tools=kept)

    def wrap_model_call(
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], "ModelResponse"],
    ) -> "ModelResponse":
        return handler(self._filter(request))

    async def awrap_model_call(
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], Awaitable["ModelResponse"]],
    ) -> "ModelResponse":
        return await handler(self._filter(request))


class _BedrockCachePointsMiddleware(AgentMiddleware[Any, Any, Any]):
    """Inject a per-call ``cache_control`` dict on ChatBedrockConverse requests.

    Bedrock prompt caching (langchain_aws ``_apply_cache_points``) fires ONLY
    when the per-call ``model_settings`` carry a NON-EMPTY ``cache_control``
    dict — ``_apply_cache_points`` early-returns on a falsy value, and reads
    only ``ttl`` off it (``type`` is ignored; Converse always uses "default").
    deepagents' built-in ``AnthropicPromptCachingMiddleware`` caches ONLY
    ``ChatAnthropic``, so in production (which runs ``ChatBedrockConverse``)
    prompt caching is silently OFF and every build re-sends its large fixed
    prefix uncached. This middleware is **Bedrock-only** and therefore
    *complements* — never double-applies with — that built-in ChatAnthropic
    path: on a ChatAnthropic (or scripted-fake) request it is a pass-through
    no-op. Gated by ``settings.BEDROCK_PROMPT_CACHE_ENABLED`` (default ON).

    Built on the stable, public LangChain middleware APIs (``AgentMiddleware``,
    ``ModelRequest.override``), mirroring ``_ToolFilterMiddleware`` — a *forward*
    implementation, not a legacy/back-compat shim.
    """

    def _maybe_apply(self, request: "ModelRequest") -> "ModelRequest":
        # Read ``settings.`` at CALL time so tests can monkeypatch the flag.
        if not settings.BEDROCK_PROMPT_CACHE_ENABLED:
            return request
        # langchain_aws is heavy — keep the import lazy (matches build_model's
        # local-import style). Bedrock-only: no-op on any non-Bedrock model so
        # ChatAnthropic keeps deepagents' built-in caching (no double-apply).
        from langchain_aws import ChatBedrockConverse

        if not isinstance(request.model, ChatBedrockConverse):
            return request
        return request.override(
            model_settings={
                **request.model_settings,
                "cache_control": {
                    "type": "ephemeral",
                    "ttl": settings.BEDROCK_PROMPT_CACHE_TTL,
                },
            }
        )

    def wrap_model_call(
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], "ModelResponse"],
    ) -> "ModelResponse":
        return handler(self._maybe_apply(request))

    async def awrap_model_call(
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], Awaitable["ModelResponse"]],
    ) -> "ModelResponse":
        return await handler(self._maybe_apply(request))


class DeepAgentRunner:
    """Adapter exposing the engine's agent contract over a ``deepagents`` graph.

    Build one per agent invocation. ``__init__`` assembles the
    ``create_deep_agent`` graph (this task, #24); the streaming methods map the
    LangGraph event stream back to the engine's event vocabulary (tasks #26–#28).

    Args:
        system_prompt: Composed system prompt for the agent (caller instructions;
            ``create_deep_agent`` prepends it to the SDK base prompt).
        tools: LangChain tools to expose, in addition to deepagents' built-ins.
            An empty list means a text-only agent; pair it with
            ``exclude_builtin_tools=True`` so no tool chips surface in the UI.
        model: Either a model id ``str`` (or ``None``) → resolved via
            :func:`app.agents.model_factory.build_model`, OR an already-built
            ``BaseChatModel`` instance → used as-is. The instance path is what the
            Phase-1 parity test injects (a scripted fake model).
        max_tokens: Output-token ceiling forwarded to ``build_model`` (ignored
            when a model instance is supplied — that instance owns its own cap).
        run_sandbox: Optional :class:`app.agents.sandbox.RunSandbox`. When given,
            the graph's filesystem backend is rooted at ``run_sandbox.root``
            (traversal-proof, per-user/per-run). When ``None``, deepagents uses
            its default in-state backend.
        checkpointer: Optional LangGraph checkpointer (from
            :func:`app.agents.checkpointer.get_checkpointer`). Required for HITL
            interrupts and durable resume.
        thread_id: Conversation/run id placed in the run ``config`` under
            ``configurable.thread_id`` (the engine uses the pipeline run id).
        interrupt_on: Optional ``{tool_name: True | InterruptOnConfig}`` mapping
            enabling HITL pauses (requires ``checkpointer``).
        exclude_builtin_tools: When ``True``, exclude the *entire* built-in tool
            suite (:data:`_BUILTIN_TOOLS`) so the agent streams pure text. This is
            the **Task #25 hook** for text-only (``tools == []``) agents. When
            ``False`` (default) only the ``task`` tool is excluded — library
            sub-agents are off but the file/todo tools remain available.
        skills_sources: POSIX directory sources (e.g. ``["/skills"]``) handed to
            deepagents' ``SkillsMiddleware`` as its ``sources``, resolved by the
            ``FilesystemBackend`` against the run sandbox root. ``None`` (the
            default) means no ``SkillsMiddleware`` is constructed at all.
    """

    def __init__(
        self,
        system_prompt: str,
        tools: list,
        *,
        model: "str | BaseChatModel | None" = None,
        max_tokens: int | None = None,
        run_sandbox: "RunSandbox | None" = None,
        checkpointer: Any = None,
        thread_id: str | None = None,
        interrupt_on: dict[str, Any] | None = None,
        exclude_builtin_tools: bool = False,
        # ISS-004: None == derive it the pre-012 way (back-compat for the many
        # tests that construct a runner directly). The factory passes it
        # explicitly, keyed on the agent's DECLARED tools.
        sanitize_fabricated_xml: bool | None = None,
        skills_sources: list[str] | None = None,
        # denied_tools: native tool names the STEP's compiled permissions do not
        # grant (``agents/factory.py::_denied_tools_for``). Unioned into the
        # exclusion set below and applied LAST, so a permission the manifest did
        # not grant cannot be handed back by any other branch — including skills
        # staging. Empty/None ⇒ nothing extra denied (every direct-construction
        # test path is unaffected).
        denied_tools: frozenset[str] | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = list(tools or [])

        # ── Resolve the chat model ────────────────────────────────────────
        # A plain ``BaseChatModel`` instance is used verbatim (the parity test
        # injects a fake here); a ``str``/``None`` goes through the Phase-0
        # factory so provider selection + botocore reliability tuning live in
        # exactly one place. We avoid importing BaseChatModel at module top
        # (heavy) — duck-type on it instead via the factory boundary.
        if isinstance(model, str) or model is None:
            self._model = build_model(model, max_tokens=max_tokens)
        else:
            self._model = model
        self.model_id: str = model_identifier(self._model)

        # ── Tool exclusion: library sub-agents OFF (always), built-ins off
        #    for text-only agents (Task #25) ──────────────────────────────
        excluded = _BUILTIN_TOOLS if exclude_builtin_tools else frozenset({_LIBRARY_SUBAGENT_TOOL})
        if skills_sources:
            # A run with staged skills must leave the filesystem tools bound —
            # the agent has to be able to CARRY OUT the skill's procedure, not
            # merely read it — so only `task` (library sub-agents, always off)
            # and `execute` are excluded. `execute` is excluded because the
            # stock deepagents skills preamble advertises script execution that
            # no agent here is given. `execute` is already a no-op under
            # FilesystemBackend (not a sandbox backend), so this is
            # forward-protection against a future sandbox backend, not a
            # change in bound tools today.
            excluded = frozenset({_LIBRARY_SUBAGENT_TOOL, "execute"})

        # ── The manifest has the last word ───────────────────────────────────
        # ``denied_tools`` is decided by ``agents/workflows/permission_caps.py``
        # and passed in — the runner does not compute or reinterpret it. Applied
        # AFTER every branch above, so a tool the step's permissions did not grant
        # cannot be reinstated by skills staging or by any future branch added
        # here. This is where the manifest's ``tools:`` block takes effect.
        if denied_tools:
            excluded = excluded | frozenset(denied_tools)

        logger.debug(
            "bound_tools %s: %s",
            (thread_id or "?").split(":")[-1],
            ",".join(sorted(_BUILTIN_TOOLS - excluded)) or "-",
        )

        # F4 (13-02) / ISS-004: sanitize fabricated tool-call XML from the
        # streamed + terminal output ONLY for agents DECLARED text-only
        # (``tools: []`` in AGENT.md). Tool-using agents' legitimate output is
        # never touched.
        #
        # This used to be derived as ``exclude_builtin_tools and not self.tools``.
        # Spec 012's universal-filesystem grant (D-07) made every text-only agent
        # resolve ``exclude_builtin_tools=False``, which silently disabled the
        # sanitizer for exactly the agents it protects — fabricated
        # ``<function_calls>`` XML began leaking into the user-visible chunk
        # stream. Post-grant a text-only agent and a ``workspace`` agent are
        # indistinguishable here (both: no custom tools, builtins bound), so the
        # caller must state the fact rather than the runner infer it.
        self._sanitize_fabricated_xml: bool = (
            sanitize_fabricated_xml
            if sanitize_fabricated_xml is not None
            else (exclude_builtin_tools and not self.tools)
        )

        # ── Disk filesystem backend (per-run sandbox), when provided ──────
        backend = None
        if run_sandbox is not None:
            backend = FilesystemBackend(root_dir=str(run_sandbox.root), virtual_mode=True)

        # ── Assemble the graph ────────────────────────────────────────────
        # subagents=None + the tool-filter middleware together guarantee the
        # ``task`` tool is never offered to the model (subagents=None alone is
        # NOT sufficient — the auto-added GP sub-agent re-adds it). FilesystemMiddleware
        # and SubAgentMiddleware are mandatory and left in place; we only filter
        # the *tools* they would expose. Summarization stays on (base-stack default).
        self._graph = create_deep_agent(
            model=self._model,
            tools=self.tools,
            system_prompt=system_prompt,
            subagents=None,
            middleware=[_ToolFilterMiddleware(excluded=excluded), _BedrockCachePointsMiddleware()],
            backend=backend,
            checkpointer=checkpointer,
            interrupt_on=interrupt_on,
            skills=skills_sources,
        )

        # Confirm hooks/override actually reached the model prompt
        has_hooks = "## Active Behavioral Hooks" in system_prompt
        has_override = "PROMPT_OVERRIDE" not in system_prompt  # override replaces body; base has no marker
        prompt_chars = len(system_prompt)
        hook_section_start = system_prompt.find("## Active Behavioral Hooks")
        hook_preview = (
            system_prompt[hook_section_start:hook_section_start + 120].replace("\n", " ")
            if hook_section_start != -1 else ""
        )
        logger.debug(
            "DeepAgentRunner system_prompt: agent=%s chars=%d has_hooks=%s hook_preview='%s'",
            (thread_id or "").split(":")[-1],
            prompt_chars,
            has_hooks,
            hook_preview,
        )

        # ── HITL armed? Only then is a post-loop ``gate`` possible (task #27). ──
        # ``HumanInTheLoopMiddleware`` is wired by ``create_deep_agent`` only when
        # ``interrupt_on`` is non-empty, and it requires a checkpointer to persist
        # the pause. When OFF there is no checkpointer, so ``aget_state`` would
        # raise — the post-loop detector short-circuits on this flag to keep the
        # no-interrupt path (the common case) cheap and exception-free.
        self._hitl_armed: bool = bool(interrupt_on) and checkpointer is not None

        # ── Run config: thread id + recursion backstop (no per-agent iter cap) ──
        self.thread_id = thread_id
        self.config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.AGENT_RECURSION_LIMIT,
        }

        # No write-scope/target-file value is known at this layer (the runner
        # only sees the tool list, never a single write target), so that field
        # is omitted rather than invented.
        logger.debug(
            "create_deep_agent %s tools=+%d",
            (thread_id or "").split(":")[-1] or "?",
            len(self.tools),
        )

        logger.debug(
            "DeepAgentRunner init: model_id=%s tools=%d excluded=%s sandbox=%s "
            "checkpointer=%s interrupt_on=%s thread_id=%s",
            self.model_id,
            len(self.tools),
            sorted(excluded),
            bool(run_sandbox),
            type(checkpointer).__name__ if checkpointer is not None else None,
            bool(interrupt_on),
            thread_id,
        )

    # -----------------------------------------------------------------------
    # Streaming interface — stubs filled by Phase-1 tasks #26–#28
    # -----------------------------------------------------------------------

    async def astream_events(
        self, user_message: "str | list"
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Drive the graph and re-emit the engine's event vocabulary.

        IMPLEMENTATION GUIDE (Phase-1 tasks #26 gate-stream + #27 gate-detect).
        Drive the graph with::

            self._graph.astream_events(
                {"messages": [HumanMessage(user_message)]},
                config=self.config,
                version="v2",
            )

        accumulate ``full_output`` from chunk text, and map LangGraph events to
        our events per this table (from the plan, Phase 1):

        | LangGraph event        | Our event              | Notes                                                          |
        |------------------------|------------------------|----------------------------------------------------------------|
        | ``on_chat_model_stream`` | ``chunk{chunk}``       | ``_extract_text(data["chunk"].content)``; accumulate ``full_output`` |
        | ``on_chat_model_end``    | ``usage{input,output}``| read ``data["output"].usage_metadata`` (reliable on Bedrock)   |
        | ``on_tool_start``        | ``tool_call{tool,args}``| ``tool=event["name"]``, ``args=data["input"]``                 |
        | ``on_tool_end``          | ``tool_result{tool,result}``| ``result=str(data["output"])``; ``report_task_complete`` passes through → engine sentinel fires |
        | stream end, no interrupt | ``done{output}``       | ``output=full_output``                                         |
        | pending interrupt        | ``gate{interrupt,thread_id}``| post-loop ``await self._graph.aget_state(self.config)``; payload = HITL ``ActionRequest`` (consumed Phase 3) |
        | exception                | ``error{error}``       | mirror the legacy swallow; Phase 3 promotes to ``raise``       |

        Notes for the implementer:
          - ``usage_metadata`` zeros have been seen before — read it off
            ``on_chat_model_end`` first, fall back to the last chunk.
          - Interrupts are not first-class in ``astream_events``: detect a
            pending interrupt AFTER the loop via ``aget_state(self.config)``
            (``state.next`` non-empty + ``state.interrupts`` /
            ``state.tasks[*].interrupts``) — implemented in :meth:`_gate_payload`.
            (``aget_state`` here was sufficient; the documented
            ``astream(stream_mode=["messages","updates","values"])`` fallback was
            not needed.)
          - **Resume (Phase 3 / task #30):** a paused graph is resumed with
            ``await self._graph.ainvoke(Command(resume={"decisions": [<Decision>]}),
            self.config)`` (or ``astream`` for streamed resume). Each ``Decision``
            is one of ``{"type":"approve"}`` / ``{"type":"edit","edited_action":{…}}``
            / ``{"type":"reject","message":…}`` / ``{"type":"respond","message":…}``
            and there must be exactly ONE decision per pending ``action_request``
            (the middleware validates the counts). ``Command(resume=…)`` accepts a
            single value (resumes the one pending interrupt) or a
            ``{interrupt_id: value}`` mapping; the ``gate`` payload carries
            ``interrupt_ids``/``review_configs`` so Phase 3 can build either.
          - Watch for Bedrock async streaming blocking the loop (the reason the
            legacy runtime used ``to_thread``) — verify the native async path,
            offload to a thread if needed.
        """
        # Local import (matches the legacy module's import style; keeps the
        # module top light and avoids importing message classes we don't use).
        from langchain_core.messages import HumanMessage

        full_output = ""
        # Did the CURRENT model turn surface any ``on_chat_model_stream`` text?
        # Reset at ``on_chat_model_start``; set on the first streamed delta. When
        # a turn ends having streamed nothing (a Bedrock no-delta turn), we fall
        # back to the ``on_chat_model_end`` message content (below) so output is
        # never silently empty — otherwise a Human review gate opens with nothing
        # to review and the live agent output is blank.
        turn_streamed_text = False
        # ── Trace-only counters (DEBUG graph tracing) — no effect on control flow ──
        agent_label = (self.thread_id or "").split(":")[-1] or "?"
        turn_reasoning = ""
        model_turn = 0
        try:
            # ``astream_events`` v2 fires for EVERY model/tool in the assembled
            # graph (including middleware-internal model calls). We deliberately
            # do NOT special-case node names — we filter purely on the event
            # *type*, which yields Phase-1 parity with the legacy single-loop
            # vocabulary (chunk / usage / tool_call / tool_result).
            async for event in self._graph.astream_events(
                {"messages": [HumanMessage(content=user_message)]},
                config=self.config,
                version="v2",
            ):
                etype = event["event"]

                if etype == "on_chat_model_start":
                    # A new model turn begins — it has streamed no text yet.
                    turn_streamed_text = False
                    turn_reasoning = ""
                    model_turn += 1
                    logger.debug("graph_model_call %s turn %d", agent_label, model_turn)

                elif etype == "on_chat_model_stream":
                    # Assistant text token. A tool-call turn emits text AND tool
                    # calls; the text still maps to ``chunk`` and accumulates
                    # into ``full_output`` (mirrors the legacy loop, which
                    # accumulated every iteration's text).
                    text = _extract_text(event["data"]["chunk"].content)
                    if text:
                        turn_streamed_text = True
                        full_output += text
                        yield {"type": "chunk", "chunk": text}
                    # Live reasoning stream (e.g. langchain_ollama with
                    # reasoning=True puts it in additional_kwargs["reasoning_content"]
                    # on chunks where ``content`` is empty while reasoning streams).
                    # Yielded live, same per-delta granularity as the ``chunk`` text
                    # above — not buffered until turn-end. Also still accumulated
                    # into ``turn_reasoning`` for the existing end-of-turn debug
                    # trace line below. Never raises — a missing/oddly-shaped dict
                    # just yields nothing.
                    try:
                        chunk_kwargs = getattr(event["data"]["chunk"], "additional_kwargs", {}) or {}
                        chunk_reasoning = chunk_kwargs.get("reasoning_content")
                        if chunk_reasoning:
                            turn_reasoning += str(chunk_reasoning)
                            yield {"type": "thinking", "thinking": str(chunk_reasoning)}
                    except Exception:
                        pass

                elif etype == "on_chat_model_end":
                    # Token usage — read off the END event's output message.
                    # This is reliable on Bedrock, where merging streamed chunks
                    # (the legacy ``ai_msg + chunk``) could silently drop
                    # ``usage_metadata`` and report 0 tokens.
                    msg = event["data"]["output"]
                    meta = getattr(msg, "usage_metadata", None)
                    if meta:
                        # ISS-032: input_tokens stays the TOTAL (incl. cache); the
                        # cache split rides alongside so the cost sites can price the
                        # UNCACHED portion. Absent input_token_details → (0, 0).
                        _cr, _cw = _cache_token_counts(meta)
                        yield {
                            "type": "usage",
                            "input_tokens": meta.get("input_tokens", 0),
                            "output_tokens": meta.get("output_tokens", 0),
                            "cache_read_tokens": _cr,
                            "cache_write_tokens": _cw,
                        }
                    # No-delta fallback: if this turn surfaced NO
                    # ``on_chat_model_stream`` text (a documented Bedrock case),
                    # the end event still carries the full assistant message.
                    # Use its text so output is never silently empty (otherwise a
                    # review gate opens blank). Emit it as a ``chunk`` too, so the
                    # engine's chunk-join AND the live UI both receive it. A
                    # tool-call turn's message has empty text content here, so this
                    # never duplicates or fabricates output for tool turns.
                    if not turn_streamed_text:
                        end_text = _extract_text(getattr(msg, "content", "") or "")
                        if end_text:
                            full_output += end_text
                            yield {"type": "chunk", "chunk": end_text}
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    logger.debug(
                        "graph_model_done %s in=%s out=%s next=%s",
                        agent_label,
                        meta.get("input_tokens", 0) if meta else 0,
                        meta.get("output_tokens", 0) if meta else 0,
                        "tool" if tool_calls else "end",
                    )
                    # Trace-only: model thinking/output lines under the `model`
                    # component. Prefer the accumulated stream reasoning; fall
                    # back to the end message's own additional_kwargs (a
                    # non-streaming path only populates it there). Guarded so a
                    # missing/oddly-shaped additional_kwargs can never raise.
                    try:
                        reasoning = turn_reasoning
                        if not reasoning:
                            end_kwargs = getattr(msg, "additional_kwargs", {}) or {}
                            reasoning = end_kwargs.get("reasoning_content") or ""
                        if reasoning:
                            model_logger.debug("thinking %s", _one_line(reasoning, 800))
                    except Exception:
                        pass
                    try:
                        end_msg_text = _extract_text(getattr(msg, "content", "") or "")
                        if end_msg_text:
                            model_logger.debug("output: %s", _one_line(end_msg_text, 400))
                    except Exception:
                        pass

                elif etype == "on_tool_start":
                    # Tool invocation. ``event["name"]`` is the tool name and
                    # MUST pass through unchanged so the engine's
                    # ``report_task_complete`` sentinel still fires.
                    tool_args = event["data"].get("input", {})
                    # Skill activation signal: the model reading a staged skill's
                    # SKILL.md is the moment a skill actually gets used (vs. merely
                    # advertised in the prompt) — log it at INFO so it's visible
                    # without turning on full DEBUG tracing.
                    if event["name"] == "read_file":
                        path_arg = tool_args.get("file_path") or tool_args.get("path") or ""
                        skill_match = re.match(r'^\.?/?skills/([^/]+)/SKILL\.md$', path_arg)
                        if skill_match:
                            logger.info(
                                "skill_used: agent read skill %s (%s)",
                                skill_match.group(1), path_arg,
                            )
                            # No sandbox reference is held by this runner (only
                            # used transiently in __init__ to build the
                            # FilesystemBackend), so this cannot call
                            # ``sandbox.audit_log`` without plumbing one through —
                            # emit the same structured info as a plain debug line.
                            logger.debug(
                                "audit_log skill_used %s",
                                {"agent": agent_label, "skill": skill_match.group(1), "file": path_arg},
                            )
                    logger.debug("graph_tool_node %s -> %s", agent_label, event["name"])
                    tool_logger.debug(
                        "tool_call: %s args=%.120s",
                        event["name"], tool_args,
                    )
                    yield {
                        "type": "tool_call",
                        "tool": event["name"],
                        "args": tool_args,
                    }

                elif etype == "on_tool_end":
                    # Tool result. Name passes through unchanged (sentinel). On the
                    # LangGraph path ``data["output"]`` is a ``ToolMessage``; we
                    # extract its ``.content`` so the stringified result is the tool's
                    # RAW return (e.g. ``"✓ done"``) — byte-identical to the legacy
                    # ``str(result)`` (``result = tool.invoke(args)``) and to what the
                    # engine forwards into the UI ``tool_result`` payload. ``getattr``
                    # falls back to the value itself if it is already a plain return.
                    output = event["data"].get("output", "")
                    result_text = str(getattr(output, "content", output))
                    tool_logger.debug("tool_result: %s -> %.120s", event["name"], result_text)
                    yield {
                        "type": "tool_result",
                        "tool": event["name"],
                        "result": result_text,
                    }

            logger.debug(
                "graph_done %s: %d model turn(s), %d chars of reply",
                agent_label, model_turn, len(full_output),
            )

            # ── End of the event stream — HITL interrupt detection (task #27) ──
            # ``astream_events`` does NOT surface interrupts as events: when HITL
            # is armed (``interrupt_on=…`` + a checkpointer), ``HumanInTheLoopMiddleware``
            # calls ``langgraph.types.interrupt(...)`` inside ``after_model`` — AFTER
            # the model emits tool calls but BEFORE the tool node runs. The stream
            # then ENDS NORMALLY (no exception, no ``on_tool_*`` for the gated
            # call). So we inspect the persisted graph state post-loop and, if a
            # pause is pending, emit ``gate`` INSTEAD of ``done`` (mutually
            # exclusive — never both). Verified empirically against deepagents
            # 0.6.7 / langgraph 1.2.4: the pending interrupt is exposed both at the
            # top-level ``StateSnapshot.interrupts`` tuple and at
            # ``state.tasks[*].interrupts``; ``state.next`` is the paused node.
            interrupt_payload = await self._gate_payload()
            if interrupt_payload is not None:
                # Paused for human review. Carry the reviewable tool call(s) +
                # the resume handle; Phase 3 bridges this to the engine's
                # ``_run_review_gate`` and resumes via ``Command(resume=…)``.
                yield {
                    "type": "gate",
                    "interrupt": interrupt_payload,
                    "thread_id": self.thread_id,
                }
                return

            # F4 (13-02): for TOOL-LESS agents only, strip fabricated tool-call
            # XML from the authoritative done output (no-op when absent —
            # characterization outputs stay byte-identical).
            if self._sanitize_fabricated_xml:
                full_output = _strip_fabricated_tool_xml(full_output)
            yield {"type": "done", "output": full_output}

        except Exception as exc:  # noqa: BLE001 — mirror the legacy swallow
            # B1 (06-05 / MODEL-02, APPROACH B): a classified TRANSIENT THROTTLE is
            # RE-RAISED so the engine's rebuild-and-retry loop can advance the model
            # resolver to the next fallback chain id and re-invoke. This is the
            # documented "promote to raise" the docstring above (and 451/307) already
            # anticipates — scoped STRICTLY to transient throttles. Everything else
            # (validation/auth/generic errors) keeps the existing swallow path:
            # ``yield {"type":"error", ...}`` UNCHANGED. Phase 16 (ISS-016) REVERSED
            # the old assumption: the engine's ``_run_agent`` consume loop now has an
            # ``error`` arm that turns this yield into a recoverable ``agent_error``
            # (and a ``pipeline_failed`` / ``status:degraded`` terminal) — it no longer
            # ignores the event. INV-3 parity for the non-throttle path therefore holds
            # NOT because the engine drops the event, but because the scripted golden
            # model never raises, so this swallow (and the engine's new arm) is DORMANT
            # on every characterization golden — the runner's output bytes are unchanged.
            from agents.model_policy import _is_transient_throttle

            if _is_transient_throttle(exc):
                logger.warning(
                    "DeepAgentRunner.astream_events: re-raising transient throttle "
                    "for engine fallback (model=%s): %s",
                    self.model_id, exc,
                )
                raise
            logger.exception("DeepAgentRunner.astream_events failed: %s", exc)
            yield {"type": "error", "error": str(exc)}

    def sanitize_output(self, text: str) -> str:
        """Sanitize an externally-assembled authoritative output (WR-01, 13 review fix).

        The engine builds each agent's authoritative output from the streamed
        ``chunk`` events (never from ``done``), so the done-event sanitization
        above never reaches the pipeline path. The engine calls THIS method
        (duck-typed — no kernel import of this module) on its chunk-joined
        output. Identity for tool-using agents (``_sanitize_fabricated_xml`` is
        False) and for clean text (same-object return), so characterization
        outputs stay byte-identical.
        """
        if self._sanitize_fabricated_xml and text:
            return _strip_fabricated_tool_xml(text)
        return text

    async def _gate_payload(self) -> dict[str, Any] | None:
        """Return a JSON-serializable HITL ``gate`` payload, or ``None`` if not paused.

        Called once after :meth:`astream_events`' event loop completes. Inspects
        the persisted graph state for a pending ``HumanInTheLoopMiddleware``
        interrupt and, when present, normalizes it into the payload Phase 3 hands
        to the engine's review gate.

        Detection (proven against deepagents 0.6.7 / langgraph 1.2.4):
          - ``state = await self._graph.aget_state(self.config)``.
          - A pause is signalled by a non-empty ``state.next`` AND one or more
            ``Interrupt`` objects. The interrupts are exposed at the top-level
            ``state.interrupts`` tuple; we also scan ``state.tasks[*].interrupts``
            as a defensive fallback (same objects, but robust if a future release
            only populates the per-task field).
          - Each ``Interrupt.value`` is the middleware's ``HITLRequest`` dict:
            ``{"action_requests": [{"name", "args", "description"}, …],
               "review_configs": [{"action_name", "allowed_decisions"}, …]}``.

        Returns ``None`` when there is no pending interrupt (the happy path — the
        caller then emits ``done``). When paused, returns::

            {
              "action_requests": [               # flattened across all pending interrupts
                {"name": str, "args": dict, "description": str | None}, …
              ],
              "review_configs": [ … ],           # allowed decisions per action (resume hints)
              "interrupt_ids": [str, …],          # resume handles (Command(resume=…) targeting)
              "next": [str, …],                   # paused node name(s), for debugging
            }

        The payload is intentionally a plain ``dict`` (no langgraph objects) so it
        survives JSON serialization onto the WebSocket. ``review_configs`` and
        ``interrupt_ids`` tell Phase 3 which decisions are valid and how to build
        the resume ``Command``; see :meth:`astream_events` for the resume shape.
        """
        # ``aget_state`` requires a checkpointer; without HITL armed there is none
        # and the call would raise. Guard so the no-interrupt path stays cheap and
        # exception-free (the common case is HITL OFF → no checkpointer).
        if not self._hitl_armed:
            return None

        state = await self._graph.aget_state(self.config)

        # A normal completion leaves ``next`` empty. A pause leaves the gated node
        # queued in ``next`` with the interrupt parked on the snapshot.
        if not getattr(state, "next", None):
            return None

        # Collect pending interrupts: prefer the top-level aggregate, fall back to
        # the per-task field (both observed to hold the same objects).
        interrupts = list(getattr(state, "interrupts", ()) or ())
        if not interrupts:
            for task in getattr(state, "tasks", ()) or ():
                interrupts.extend(getattr(task, "interrupts", ()) or ())
        if not interrupts:
            # ``next`` is set but no interrupt is parked — not a HITL pause we can
            # surface (e.g. a recursion-limit stop). Let the caller emit ``done``.
            return None

        action_requests: list[dict[str, Any]] = []
        review_configs: list[dict[str, Any]] = []
        interrupt_ids: list[str] = []

        for itr in interrupts:
            interrupt_ids.append(getattr(itr, "id", None))
            value = getattr(itr, "value", None)
            if isinstance(value, dict):
                for req in value.get("action_requests", []) or []:
                    if isinstance(req, dict):
                        action_requests.append(
                            {
                                # The middleware uses ``name``; accept ``action``
                                # too in case a future shape renames it.
                                "name": req.get("name") or req.get("action"),
                                "args": req.get("args", {}),
                                "description": req.get("description"),
                            }
                        )
                    else:  # pragma: no cover — defensive
                        action_requests.append({"name": None, "args": {}, "raw": str(req)})
                for cfg in value.get("review_configs", []) or []:
                    if isinstance(cfg, dict):
                        review_configs.append(
                            {
                                "action_name": cfg.get("action_name"),
                                "allowed_decisions": cfg.get("allowed_decisions", []),
                            }
                        )
            elif value is not None:  # pragma: no cover — non-HITL interrupt shape
                # An interrupt whose value isn't a HITLRequest dict; surface it
                # stringified so Phase 3 at least sees *something* to review.
                action_requests.append({"name": None, "args": {}, "raw": str(value)})

        return {
            "action_requests": action_requests,
            "review_configs": review_configs,
            "interrupt_ids": interrupt_ids,
            "next": list(state.next),
        }

    async def astream_with_usage(
        self, user_message: "str | list"
    ) -> AsyncGenerator[Any, None]:
        """Stream text chunks then yield exactly one final ``TokenUsage``.

        The engine's text-only path (``tools == []``, ``use_deep=False``)
        consumes this: it appends every non-``TokenUsage`` item as output text
        and, on the ``TokenUsage`` instance, reads ``.input_tokens`` /
        ``.output_tokens`` and breaks (``engine.py:822–828``). We therefore
        reproduce the legacy ``DeepAgent.astream_with_usage`` contract exactly:
        **all text chunks first, then one and only one** ``TokenUsage``.

        Implementation: delegate to :meth:`astream_events` (the single source of
        truth). For each ``chunk`` event yield its text; for each ``usage`` event
        SUM ``input_tokens`` / ``output_tokens`` (one ``usage`` per model turn —
        a tool-calling agent emits several, which must total). Stop iterating on
        the first terminal event (``done`` / ``gate`` / ``error``); ``gate`` and
        ``error`` already ``return`` inside ``astream_events`` so the loop simply
        ends.

        ``TokenUsage`` always carries ``total_tokens = input + output``. Since
        ISS-032 the ``cache_read_tokens`` / ``cache_write_tokens`` fields are SUMMED
        from the ``usage`` events' cache split (which :meth:`astream_events` now
        surfaces from ``usage_metadata["input_token_details"]`` — the Bedrock
        cache_read/cache_creation counts, 0 on ChatAnthropic/scripted/no-cache
        turns). ``total_tokens`` stays ``input + output`` (the input count remains
        the TOTAL incl. cache); the cache fields are additive telemetry the cost
        sites use to price the uncached split.

        Error path: if the stream ends via an ``error`` event we still yield the
        final ``TokenUsage`` with whatever was accumulated — matching the legacy
        "emit partial text, then usage" spirit (the legacy swallows a timeout and
        falls through to its ``yield usage``). The engine never raises on this
        path; it just stops at the ``TokenUsage``.
        """
        from app.agents.types import TokenUsage

        sum_in = 0
        sum_out = 0
        sum_cache_read = 0
        sum_cache_write = 0
        async for event in self.astream_events(user_message):
            etype = event["type"]
            if etype == "chunk":
                yield event["chunk"]
            elif etype == "usage":
                sum_in += event.get("input_tokens", 0) or 0
                sum_out += event.get("output_tokens", 0) or 0
                # ISS-032: sum the per-turn cache split so the text-only path's
                # TokenUsage carries the same cache telemetry as the event path.
                sum_cache_read += event.get("cache_read_tokens", 0) or 0
                sum_cache_write += event.get("cache_write_tokens", 0) or 0
            elif etype in ("done", "gate", "error"):
                # Terminal — no further chunks/usage follow. (``gate``/``error``
                # already returned upstream; ``done`` is the last yield.)
                break

        yield TokenUsage(
            input_tokens=sum_in,
            output_tokens=sum_out,
            total_tokens=sum_in + sum_out,
            cache_read_tokens=sum_cache_read,
            cache_write_tokens=sum_cache_write,
        )

    async def astream(self, user_message: "str | list") -> AsyncGenerator[str, None]:
        """Stream only text chunks (mirrors the legacy text-only interface).

        Delegates to :meth:`astream_events` and yields ``event["chunk"]`` for
        every ``chunk`` event, ignoring all other event types (``usage`` /
        ``tool_call`` / ``tool_result`` / ``done`` / ``gate`` / ``error``). Like
        the legacy ``DeepAgent.astream``, it simply ends when the stream ends —
        an ``error`` event just terminates the useful output without raising.
        """
        async for event in self.astream_events(user_message):
            if event["type"] == "chunk":
                yield event["chunk"]

    async def run(self, user_message: "str | list") -> str:
        """Run to completion and return the full concatenated text output.

        Mirrors the legacy ``DeepAgent.run``: accumulate every ``chunk`` event's
        text from :meth:`astream_events` into one string and return it. A stream
        that ends via ``error`` returns whatever text was produced before the
        error (no raise), matching the legacy behaviour.
        """
        output = ""
        async for event in self.astream_events(user_message):
            if event["type"] == "chunk":
                output += event["chunk"]
        return output


# ---------------------------------------------------------------------------
# Helper: extract text from an AIMessage(Chunk).content payload.
# Mirrors ``app/agents/deep_agent._extract_text`` so the stream-mapping code in
# tasks #26–#28 has the identical text-extraction semantics.
# ---------------------------------------------------------------------------


def _extract_text(content: Any) -> str:
    """Pull plain text out of a message content payload (str or list-of-blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _cache_token_counts(meta: Any) -> tuple[int, int]:
    """Extract the prompt-cache split (cache_read, cache_write) from usage_metadata.

    ISS-032: ``langchain_aws`` (Bedrock ``ChatBedrockConverse``) reports
    ``usage_metadata["input_tokens"]`` as the TOTAL input (cached + uncached) and
    puts the split in ``input_token_details = {"cache_read": N, "cache_creation": M}``
    (see ``langchain_aws/chat_models/bedrock_converse.py``). ChatAnthropic (local),
    scripted characterization models, and any no-cache turn OMIT the
    ``input_token_details`` block entirely (or set it to ``None``), so this returns
    ``(0, 0)`` for them.

    Degrade-not-crash: a ``None``/absent ``meta``, a ``None`` ``input_token_details``,
    or a missing/``None`` sub-key all yield ``0`` via ``int(... or 0)`` — never raises.
    """
    details = (meta or {}).get("input_token_details") or {}
    cache_read = int(details.get("cache_read", 0) or 0)
    cache_write = int(details.get("cache_creation", 0) or 0)
    return cache_read, cache_write

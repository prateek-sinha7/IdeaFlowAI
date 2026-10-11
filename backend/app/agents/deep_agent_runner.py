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
  backend=ValidatingFilesystemBackend(root_dir=<RunSandbox.root>, virtual_mode=True),
  checkpointer=<Phase-0 factory>, interrupt_on=…)`` driven with
  ``config={"configurable":{"thread_id": run_id},
  "recursion_limit": settings.AGENT_RECURSION_LIMIT}``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import posixpath
import re
from typing import TYPE_CHECKING, Any, AsyncGenerator, Awaitable, Callable

from deepagents import create_deep_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

from agents.capabilities.model_catalog import ModelCatalog
from app.agents.model_factory import build_model, model_identifier
from app.agents.validating_backend import ValidatingFilesystemBackend
from app.agents.sandbox import AGENT_READABLE_RESERVED, RESERVED_PATHS
from app.core.config import settings

if TYPE_CHECKING:
    from langchain.agents.middleware.types import (
        ModelRequest,
        ModelResponse,
        # Used unquoted in annotations below: safe under ``from __future__ import
        # annotations``, and visible to vulture (no ignore_names entry needed).
        ToolCallRequest,
    )
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
# Same-model retry with backoff (the incident this fixes): AWS Bedrock put a
# classified-transient error frame (``botocore.exceptions.EventStreamError``,
# ``internalServerException`` — "Try your request again") on an OPEN
# ``ConverseStream`` after 1173 thinking deltas / 98s. The engine's OWN
# model-fallback loop (``agents/execution_engine/engine.py``) only ADVANCES TO
# A CHEAPER MODEL and has no sleep/backoff — for a ``cost_class="cheap"`` model
# (the builders' Haiku) the tier-descent chain is empty, so it exhausts on
# attempt 1. Retrying the SAME model with backoff is exactly what "try your
# request again" asks for, and only the runner (which owns the model call) can
# do it. 3 total attempts (1 initial + 2 retries); full-jitter exponential
# backoff so concurrent workers don't retry in lockstep.
# ---------------------------------------------------------------------------
_MAX_MODEL_CALL_ATTEMPTS: int = 3
_RETRY_BASE_SECONDS: float = 2.0
_RETRY_FACTOR: int = 2
_RETRY_CAP_SECONDS: float = 30.0


def _retry_delay_seconds(attempt: int) -> float:
    """Full-jitter exponential backoff delay (seconds) for retry number ``attempt`` (0-indexed).

    ``actual sleep = random.uniform(0, min(cap, base * factor**attempt))`` — the
    AWS-recommended "full jitter" shape: bounded by an exponentially growing
    ceiling, but uniformly random within it (not a fixed exponential delay), so
    many workers retrying the same transient fault don't all wake up at once.
    """
    ceiling = min(_RETRY_CAP_SECONDS, _RETRY_BASE_SECONDS * (_RETRY_FACTOR**attempt))
    return random.uniform(0, ceiling)


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
    r"<function_calls>[\s\S]*?</function_calls>" r"|<invoke\b[^>]*>[\s\S]*?</invoke>"
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

    # ── ISS-171: refuse the CALL, not just the offer ─────────────────────────
    # ``_filter`` above only strips tools from the model REQUEST. That decides
    # what the model is offered; it does not unregister anything from the graph,
    # so a model that names an excluded tool anyway still reached a live
    # implementation — and did: steps compiled with ``read_files: false`` were
    # observed running ``ls`` and ``read_file`` against the run sandbox and
    # getting real directory listings back (ISS-171).
    #
    # The model names them because deepagents' own built-in system prompt
    # documents the filesystem tools; stripping the binding does not unsay that.
    # ``request.tools`` filtering is therefore a UX narrowing, and a permission
    # the manifest withheld needs an enforcement point at EXECUTION. This is it:
    # the tool never runs, and the model is told plainly so it stops retrying.
    def _refusal(self, request: ToolCallRequest) -> ToolMessage | None:
        """A denial ``ToolMessage`` when this call is excluded, else ``None``."""
        call = getattr(request, "tool_call", None)
        if not self._excluded or not isinstance(call, dict):
            return None
        name = call.get("name")
        if name not in self._excluded:
            return None
        logger.warning(
            "tool %r DENIED at execution — not granted by this step's permissions",
            name,
        )
        return ToolMessage(
            content=(
                f"Tool '{name}' is not available to this step. Do not try to "
                f"call it again; continue with what you already have."
            ),
            name=name,
            tool_call_id=call.get("id") or "",
            status="error",
        )

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        refusal = self._refusal(request)
        return refusal if refusal is not None else handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        refusal = self._refusal(request)
        return refusal if refusal is not None else await handler(request)


# ── Image-payload guard (run b0642e0f: prototype-validate "model rejected") ──
# Nine 1280x720 PNG screenshots (744KB on disk, ~1MB as base64) accumulated in
# ONE agent's conversation and the provider refused the request. The agent was
# not misbehaving: `playwright_take_screenshot` deliberately returns only a PATH
# (app/agents/tools/playwright.py — "the tool returns the relative path"), but the
# same agent also holds the native `read_file`, and deepagents' filesystem
# middleware turns any binary read into a base64 image CONTENT BLOCK
# (middleware/filesystem.py:911-915). So `screenshot -> read_file(path)` re-inlines
# the very bytes the path-return was avoiding, and every image then rides along in
# EVERY subsequent turn — the cost is cumulative, not per-call.
#
# deepagents' own eviction cannot help: `_build_evicted_content`
# (middleware/_message_eviction.py) replaces text blocks but deliberately PRESERVES
# `media_blocks`, so images survive exactly the mechanism that bounds everything else.
#
# This keeps the N most recent images and replaces older ones with a one-line text
# placeholder naming the file. Screenshots are looked at once, to decide the next
# click; the 9th does not need the 1st still in frame. Dormant for every agent that
# reads no binaries (the overwhelming majority) — the walk finds no media blocks and
# returns the request unchanged.
_MAX_RETAINED_IMAGE_BLOCKS = 2

# Both placeholders state the image was ALREADY SEEN and must not be fetched
# again. Wording is load-bearing — see the note in _prune about run 50df89da.
_EVICTED_IMAGE_PLACEHOLDER = (
    "[{path} — you already viewed this image earlier in this conversation; its "
    "pixels were removed here to bound the request payload. Do NOT read it again "
    "— work from what you already recorded about it.]"
)
_DUPLICATE_IMAGE_PLACEHOLDER = (
    "[{path} — duplicate read; this image is still shown once later in this "
    "conversation. Do NOT read it again.]"
)


def _media_blocks_in(message: Any) -> int:
    """Count non-text content blocks on a ToolMessage (0 for plain-string content)."""
    if not isinstance(getattr(message, "content", None), list):
        return 0
    try:
        return sum(1 for b in message.content_blocks if b.get("type") != "text")
    except Exception:  # noqa: BLE001 — a malformed block must never break a dispatch
        return 0


class _ImagePayloadGuardMiddleware(AgentMiddleware[Any, Any, Any]):
    """Bound the number of base64 image blocks carried in the model request.

    Keyed purely on content SHAPE (a tool message carrying non-text blocks) — no
    tool-name, agent-id or workflow literal (SC-001), so it applies wherever the
    pattern arises rather than to the one agent that happened to hit it.
    """

    def __init__(self, *, keep: int = _MAX_RETAINED_IMAGE_BLOCKS) -> None:
        self._keep = keep

    def _prune(self, request: "ModelRequest") -> "ModelRequest":
        messages = list(getattr(request, "messages", None) or [])
        # Walk NEWEST-first so "keep the most recent N" needs one pass and no
        # second reversal; collect indices to rewrite, then rebuild in order.
        budget = self._keep
        rewrite: dict[int, str] = {}
        # Paths whose image is already retained NEWER in this walk. A model that
        # re-reads the same file gets the block ONCE (the latest copy) and a
        # placeholder for every older duplicate, so N repeat reads of one page
        # cost one image, not N. Without this, run 50df89da's reader cycled
        # pages 04→05→06 forty-one times and grew the request until the provider
        # refused it — the loop below is what that dedupe stops paying for.
        seen_paths: set[str] = set()
        # Every ToolMessage AFTER the last AIMessage answers THAT turn's tool
        # calls and has never been inside a request: the model has not seen it.
        # Those are kept whole and cost no budget — evicting one would tell the
        # model it "already viewed" a picture it never received. Run 8a992018:
        # a reader called read_file on ten PNGs in one turn, the guard kept two,
        # and the notes for the other eight said "Screenshot of clone action".
        # The bound applies to images from EARLIER turns only.
        last_ai = max(
            (i for i, m in enumerate(messages) if isinstance(m, AIMessage)), default=-1
        )
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if not isinstance(msg, ToolMessage):
                continue
            n = _media_blocks_in(msg)
            if n == 0:
                continue
            path = (msg.additional_kwargs or {}).get("read_file_path") or "binary file"
            # A newer read of the SAME path already carries this image — drop the
            # older copy regardless of budget, and don't spend budget on it.
            if path in seen_paths:
                rewrite[i] = _DUPLICATE_IMAGE_PLACEHOLDER.format(path=path)
                continue
            seen_paths.add(path)
            if i > last_ai:
                continue  # unseen this turn — never evict, never charge
            if budget > 0:
                budget -= 1
                continue
            # NOTE: this text must NEVER invite a re-read. The first version said
            # "re-read it if you need to look at it again", which livelocked run
            # 50df89da: with keep=2 and three pages wanted, each new read evicted
            # the oldest, the placeholder told the model to fetch it back, and the
            # reader cycled the same three PNGs 122 times until the request was
            # rejected. The model has already SEEN this image — point it at its own
            # notes, not back at the file.
            rewrite[i] = _EVICTED_IMAGE_PLACEHOLDER.format(path=path)
        if not rewrite:
            return request

        pruned = list(messages)
        for i, text in rewrite.items():
            old = pruned[i]
            pruned[i] = ToolMessage(
                content=text,
                tool_call_id=old.tool_call_id,
                name=old.name,
                id=old.id,
                status=old.status,
                additional_kwargs=dict(old.additional_kwargs or {}),
            )
        logger.info(
            "image-payload guard: dropped %d stale image block(s), kept the %d most recent",
            len(rewrite),
            self._keep,
        )
        return request.override(messages=pruned)

    def wrap_model_call(
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], "ModelResponse"],
    ) -> "ModelResponse":
        return handler(self._prune(request))

    async def awrap_model_call(
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], Awaitable["ModelResponse"]],
    ) -> "ModelResponse":
        return await handler(self._prune(request))


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
        # ...but being a ChatBedrockConverse is a TRANSPORT fact, not a capability
        # one (spec 020 / FR-21). OpenAI's models are served over this same client
        # and support prompt caching on the Responses API ONLY — a `cachePoint` on
        # Converse returns AccessDeniedException ("You invoked an unsupported model
        # or your request did not allow prompt caching"), measured against
        # global.openai.gpt-5.6-luna while Claude Haiku 4.5 accepted the identical
        # call. With this flag defaulting ON that would fail 100% of GPT requests,
        # so the second gate asks the catalog rather than the client class.
        #
        # An id absent from the catalog keeps caching ON: fail-open preserves
        # today's behaviour for anything uncatalogued, where fail-closed would
        # silently disable caching on a model that had been relying on it.
        entry = ModelCatalog().get(model_identifier(request.model))
        if entry is not None and not entry.supports_prompt_caching:
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


# ---------------------------------------------------------------------------
# Reserved-path guard (Requirement 18 AC 3, V2-Q7 — SGV2-GAP-001/002 closure)
# ---------------------------------------------------------------------------


class _ReservedPathGuardMiddleware(AgentMiddleware[Any, Any, Any]):
    """Intercept agent filesystem tool calls and enforce the reserved-path registry.

    This middleware enforces two rules declared in Requirement 18 AC 3 and V2-Q7:

    **WRITE guard** — tools that mutate the sandbox (``write_file``, ``edit_file``,
    ``create_directory``) are **refused** when their target path's normalised prefix
    falls under any entry in ``RESERVED_PATHS`` (imported from
    ``app.agents.sandbox``).  The agent is told plainly and asked not to retry.

    **READ guard** — tools that read from the sandbox (``read_file``, ``ls``,
    ``glob``, ``grep``) are refused for any path under ``RESERVED_PATHS`` UNLESS the
    normalised prefix is in ``AGENT_READABLE_RESERVED`` (i.e. ``.context/`` only).
    ``.chain/`` is deliberately NOT in ``AGENT_READABLE_RESERVED``; an agent cannot
    read it directly — only authorized Workspace surfaces may (Requirement 18 AC 8).

    **What "normalised prefix" means here:** the tool argument is resolved to a
    POSIX relative path (leading ``/`` and ``./`` stripped), then checked against
    each registry entry (which all end with ``/`` or are bare names).  Both the
    trailing-slash form and the bare name match.

    The guard operates on EXECUTION (``wrap_tool_call`` / ``awrap_tool_call``), not
    on the model-offer level: a model that hallucinates a reserved path is refused
    at call time and told so, consistent with the ``_ToolFilterMiddleware`` pattern
    (ISS-171).

    Constants are imported from ``app.agents.sandbox``, the single canonical source
    (V2-Q7).  This module is in ``app.*`` so the ``app.agents.sandbox`` import is
    legal (the import-linter contract only forbids ``agents.capabilities`` → ``app``).
    """

    # Tools that write or mutate content in the sandbox.
    _WRITE_TOOLS: frozenset[str] = frozenset(
        {"write_file", "edit_file", "create_directory"}
    )
    # Tools that read from the sandbox (and therefore subject to the read guard).
    _READ_TOOLS: frozenset[str] = frozenset({"read_file", "ls", "glob", "grep"})

    def _extract_path(self, call: dict) -> str | None:
        """Pull the first path-like argument from a tool call dict.

        Deepagents tool arguments are passed as a dict under ``"args"``; the
        primary path parameter is named ``"path"`` for ``read_file``, ``"file_path"``
        for ``write_file``/``edit_file``, ``"directory"`` for ``ls``/``create_directory``,
        and ``"pattern"`` for ``glob``/``grep``.  We check the common names in order
        and return the first non-empty string found.
        """
        args = call.get("args") or {}
        for key in ("path", "file_path", "directory", "pattern"):
            val = args.get(key)
            if isinstance(val, str) and val:
                return val
        return None

    @staticmethod
    def _normalise(path: str) -> str:
        """Normalise a path so bypass attempts are collapsed before the prefix check.

        Strips leading slashes and ``./`` (so ``/path`` == ``path`` == ``./path``),
        then uses :func:`posixpath.normpath` to collapse embedded ``..`` segments
        (so ``sub/../.chain/x`` → ``.chain/x``).  Without this step an agent
        could reach any reserved prefix through a ``sub/../<reserved>/`` detour.

        ``posixpath.normpath`` is used unconditionally — on Windows the guard
        still operates on POSIX-style relative paths supplied by the agent tool
        call, not on OS-native paths.
        """
        p = path.lstrip("/")
        if p.startswith("./"):
            p = p[2:]
        # Collapse embedded .. so  sub/../.chain/x → .chain/x.
        # normpath("") → "." and normpath(".") → "."; treat both as empty.
        p = posixpath.normpath(p) if p and p != "." else ""
        # normpath can reintroduce a leading "./" if the result starts with ".";
        # strip it once more so the prefix check stays consistent.
        if p.startswith("./"):
            p = p[2:]
        return p

    def _is_reserved(self, path: str) -> bool:
        """Return True when *path* falls under any entry in ``RESERVED_PATHS``."""
        norm = self._normalise(path)
        for entry in RESERVED_PATHS:
            # Entries end with ``/`` (directory prefixes) or are bare names.
            bare = entry.rstrip("/")
            if norm == bare or norm.startswith(bare + "/") or norm.startswith(entry):
                return True
        return False

    def _is_agent_readable(self, path: str) -> bool:
        """Return True when *path* is under a prefix in ``AGENT_READABLE_RESERVED``."""
        norm = self._normalise(path)
        for entry in AGENT_READABLE_RESERVED:
            bare = entry.rstrip("/")
            if norm == bare or norm.startswith(bare + "/") or norm.startswith(entry):
                return True
        return False

    def _refusal(self, request: ToolCallRequest) -> "ToolMessage | None":
        """Return a denial ToolMessage when this call violates the guard, else None."""
        call = getattr(request, "tool_call", None)
        if not isinstance(call, dict):
            return None
        name = call.get("name")
        if name not in self._WRITE_TOOLS and name not in self._READ_TOOLS:
            return None

        path = self._extract_path(call)
        if path is None:
            return None

        if name in self._WRITE_TOOLS:
            if self._is_reserved(path):
                logger.warning(
                    "reserved-path WRITE DENIED: tool=%r path=%r (RESERVED_PATHS)",
                    name,
                    path,
                )
                return ToolMessage(
                    content=(
                        f"Tool '{name}' is not permitted to write to '{path}': "
                        f"that path is engine-reserved and may not be modified by agents. "
                        f"Do not attempt to write to reserved paths."
                    ),
                    name=name,
                    tool_call_id=call.get("id") or "",
                    status="error",
                )
        elif name in self._READ_TOOLS:  # noqa: RET505
            if self._is_reserved(path) and not self._is_agent_readable(path):
                logger.warning(
                    "reserved-path READ DENIED: tool=%r path=%r (not in AGENT_READABLE_RESERVED)",
                    name,
                    path,
                )
                return ToolMessage(
                    content=(
                        f"Tool '{name}' is not permitted to read '{path}': "
                        f"that path is engine-reserved. "
                        f"Only paths under .context/ are readable by agents."
                    ),
                    name=name,
                    tool_call_id=call.get("id") or "",
                    status="error",
                )
        return None

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        refusal = self._refusal(request)
        return refusal if refusal is not None else handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        refusal = self._refusal(request)
        return refusal if refusal is not None else await handler(request)


# Sentinel object returned by the factory when it resolves the
# ``TOOL_RESERVED_PATH_GUARD`` key.  ``DeepAgentRunner.__init__`` checks for
# this sentinel in the resolved tools list and activates the guard middleware;
# the sentinel is then removed from the tool list so it is never handed to the
# model.  Using a typed sentinel rather than a plain string keeps the resolution
# type-safe and avoids accidental string collisions.
class _ReservedPathGuardSentinel:
    """Marker object — not a real tool, never passed to the model."""

    name: str = "__reserved_path_guard__"


_RESERVED_PATH_GUARD_SENTINEL = _ReservedPathGuardSentinel()


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
        # Per-step reasoning level (spec 020). Ignored when ``model`` is already a
        # BaseChatModel instance — that client is used verbatim and was built
        # elsewhere, so there is nothing left to configure.
        effort: str | None = None,
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
            self._model = build_model(model, max_tokens=max_tokens, effort=effort)
        else:
            self._model = model
        # Prefer the model string we already know (the caller-supplied ``model``
        # or the settings default) over a post-hoc attribute probe — the LangChain
        # object may not expose it reliably for every provider, and
        # ``model_identifier`` falls back to the literal string "unknown" which
        # then propagates into agent_complete.model_id and analytics.
        if isinstance(model, str) and model:
            self.model_id: str = model
        else:
            resolved = model_identifier(self._model)
            if resolved == "unknown":
                # Last resort: use the configured inference profile so the
                # analytics "By Model" section shows a real model label rather
                # than the sentinel.
                resolved = (
                    settings.BEDROCK_INFERENCE_PROFILE_ID
                    or settings.BEDROCK_MODEL_ID
                    or "unknown"
                )
            self.model_id = resolved

        # ── Tool exclusion: library sub-agents OFF (always), built-ins off
        #    for text-only agents (Task #25) ──────────────────────────────
        excluded = (
            _BUILTIN_TOOLS
            if exclude_builtin_tools
            else frozenset({_LIBRARY_SUBAGENT_TOOL})
        )
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
            backend = ValidatingFilesystemBackend(
                root_dir=str(run_sandbox.root), virtual_mode=True
            )

        # ── Reserved-path guard (Requirement 18 AC 3, V2-Q7) ─────────────
        # Detect the sentinel emitted by filesystem-capable tool providers
        # (``TOOL_RESERVED_PATH_GUARD`` key resolved by the factory to
        # ``_RESERVED_PATH_GUARD_SENTINEL``).  Remove the sentinel from the tool
        # list (it is NOT a real tool and must never be passed to the model), and
        # activate the guard middleware unconditionally when a sandbox is present:
        # a sandbox-less agent has no filesystem to guard, but a sandboxed agent
        # with fs tools bound must always have the guard active — even if the
        # provider key was absent (defence in depth), since the middleware is
        # cheap and harmless when the agent has no write tools.
        #
        # The guard activates when EITHER condition is true:
        #   a) the provider explicitly emitted the guard sentinel, OR
        #   b) a run_sandbox is present (every sandboxed agent should have it).
        # This ensures that direct DeepAgentRunner construction with a sandbox
        # (e.g. test paths that bypass the factory) also gets the guard.
        _guard_requested = any(
            isinstance(t, _ReservedPathGuardSentinel) for t in self.tools
        )
        # Remove sentinels from the tool list — they are metadata, not tools.
        self.tools = [
            t for t in self.tools if not isinstance(t, _ReservedPathGuardSentinel)
        ]
        _attach_path_guard: bool = _guard_requested or (run_sandbox is not None)

        # ── Assemble the graph ────────────────────────────────────────────
        # subagents=None + the tool-filter middleware together guarantee the
        # ``task`` tool is never offered to the model (subagents=None alone is
        # NOT sufficient — the auto-added GP sub-agent re-adds it). FilesystemMiddleware
        # and SubAgentMiddleware are mandatory and left in place; we only filter
        # the *tools* they would expose. Summarization stays on (base-stack default).
        #
        # ``_ReservedPathGuardMiddleware`` is appended AFTER ``_ToolFilterMiddleware``
        # so that tools already excluded by permissions never reach the path check
        # (defence in depth: an excluded tool cannot bypass the guard by accident).
        _middleware: list = [
            _ToolFilterMiddleware(excluded=excluded),
            _ImagePayloadGuardMiddleware(),
            _BedrockCachePointsMiddleware(),
        ]
        if _attach_path_guard:
            _middleware.append(_ReservedPathGuardMiddleware())
            logger.debug(
                "reserved_path_guard ACTIVE for agent %s",
                (thread_id or "?").split(":")[-1],
            )

        self._graph = create_deep_agent(
            model=self._model,
            tools=self.tools,
            system_prompt=system_prompt,
            subagents=None,
            middleware=_middleware,
            backend=backend,
            checkpointer=checkpointer,
            interrupt_on=interrupt_on,
            skills=skills_sources,
        )

        # Confirm hooks/override actually reached the model prompt
        has_hooks = "## Active Behavioral Hooks" in system_prompt
        prompt_chars = len(system_prompt)
        hook_section_start = system_prompt.find("## Active Behavioral Hooks")
        hook_preview = (
            system_prompt[hook_section_start : hook_section_start + 120].replace(
                "\n", " "
            )
            if hook_section_start != -1
            else ""
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
        """Drive the graph, retrying a SAME-model transient throttle with backoff.

        Thin retry wrapper over :meth:`_astream_events_once` (the real
        event-mapping implementation below — see its docstring for the full
        LangGraph→engine event table). The incident this exists for: Bedrock
        put a classified-transient fault (``internalServerException`` via
        ``botocore.exceptions.EventStreamError`` — "Try your request again")
        on an OPEN ``ConverseStream``. The engine's OWN model-fallback loop
        (``agents/execution_engine/engine.py``) only steps DOWN to a cheaper
        model with no backoff, and for a ``cost_class="cheap"`` model (the
        builders' Haiku) the tier-descent chain is empty — it exhausts on
        attempt 1. Retrying the SAME model with backoff, here, is what "try
        your request again" actually asks for, and only the runner (which
        owns the model call) can do it.

        SAFETY — mid-stream duplicate events (deliberately narrow, read this
        before widening it): ``_astream_events_once`` forwards
        ``chunk``/``thinking``/``tool_call``/``tool_result`` events to the
        caller AS THEY HAPPEN — the engine forwards them live over the
        WebSocket and accumulates them into the agent's one authoritative
        ``output_chunks`` list for THIS attempt
        (``agents/execution_engine/engine.py`` ~5970-5987). Once anything has
        been yielded, a silent re-run would DUPLICATE that content into the
        same accumulator and re-send it live — the engine has no per-event
        "discard this" signal for content already forwarded; its ONLY reset
        mechanism is its own ``agent_model_fallback`` / ``reset_output``
        event (~6227-6242), which fires at a DIFFERENT layer (a full
        model-switch rebuild, not a same-model in-place retry) and is not
        something this method can safely emit through the existing event
        vocabulary. So this retries ONLY when the current attempt has
        yielded NOTHING yet — the fault happened before the first
        chunk/thinking/tool event reached the caller.

        This is deliberately narrow: on its own it would NOT have retried the
        exact production incident this fixes (1173 thinking deltas already
        streamed before the fault) — that case still propagates to the
        engine exactly as before, where Change 1 (the classifier fix) now
        correctly marks it transient for the engine's OWN fallback loop. What
        this DOES catch — per the engine's own "Pitfall 4" comment, the
        common Bedrock case — is a fault before any token streams, without
        even bothering the engine or stepping down to a cheaper model.
        """
        from agents.model_policy import mark_model_proven

        attempt = 0
        yielded_any = False
        while True:
            attempt += 1
            try:
                async for event in self._astream_events_once(user_message):
                    if not yielded_any:
                        # This model just resolved and produced output — remember it,
                        # so a later "ARN not found" for it is read as a provider lie
                        # rather than a permanent misconfiguration.
                        mark_model_proven(self.model_id)
                    yielded_any = True
                    yield event
                return
            except Exception as exc:  # noqa: BLE001 — see _astream_events_once: only a
                # classified transient throttle ever escapes it (everything else is
                # swallowed internally into an {"type":"error"} yield), so reaching
                # here always means a transient fault worth retrying if it's safe to.
                if yielded_any or attempt >= _MAX_MODEL_CALL_ATTEMPTS:
                    raise
                delay = _retry_delay_seconds(attempt - 1)
                logger.warning(
                    "DeepAgentRunner.astream_events: transient throttle on attempt "
                    "%d/%d (model=%s) — retrying same model in %.2fs: %s",
                    attempt,
                    _MAX_MODEL_CALL_ATTEMPTS,
                    self.model_id,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

    async def _astream_events_once(
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
                    # Live reasoning stream. ChatAnthropic / ChatBedrockConverse
                    # (extended thinking) stream reasoning as a content BLOCK, not
                    # additional_kwargs — see _extract_thinking. The additional_kwargs
                    # check below is a defensive fallback for providers that shape
                    # reasoning that way instead.
                    # Yielded live, same per-delta granularity as the ``chunk`` text
                    # above — not buffered until turn-end. Also still accumulated
                    # into ``turn_reasoning`` for the existing end-of-turn debug
                    # trace line below. Never raises — a missing/oddly-shaped dict
                    # just yields nothing.
                    try:
                        chunk_kwargs = (
                            getattr(event["data"]["chunk"], "additional_kwargs", {})
                            or {}
                        )
                        chunk_reasoning = chunk_kwargs.get(
                            "reasoning_content"
                        ) or _extract_thinking(event["data"]["chunk"].content)
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
                            model_logger.debug(
                                "output: %s", _one_line(end_msg_text, 400)
                            )
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
                        path_arg = (
                            tool_args.get("file_path") or tool_args.get("path") or ""
                        )
                        skill_match = re.match(
                            r"^\.?/?skills/([^/]+)/SKILL\.md$", path_arg
                        )
                        if skill_match:
                            logger.info(
                                "skill_used: agent read skill %s (%s)",
                                skill_match.group(1),
                                path_arg,
                            )
                            # No sandbox reference is held by this runner (only
                            # used transiently in __init__ to build the
                            # FilesystemBackend), so this cannot call
                            # ``sandbox.audit_log`` without plumbing one through —
                            # emit the same structured info as a plain debug line.
                            logger.debug(
                                "audit_log skill_used %s",
                                {
                                    "agent": agent_label,
                                    "skill": skill_match.group(1),
                                    "file": path_arg,
                                },
                            )
                    logger.debug("graph_tool_node %s -> %s", agent_label, event["name"])
                    tool_logger.debug(
                        "tool_call: %s args=%.120s",
                        event["name"],
                        tool_args,
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
                    result_text = _tool_result_text(getattr(output, "content", output))
                    tool_logger.debug(
                        "tool_result: %s -> %.120s", event["name"], result_text
                    )
                    yield {
                        "type": "tool_result",
                        "tool": event["name"],
                        "result": result_text,
                    }

            logger.debug(
                "graph_done %s: %d model turn(s), %d chars of reply",
                agent_label,
                model_turn,
                len(full_output),
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

            if _is_transient_throttle(exc, self.model_id):
                logger.warning(
                    "DeepAgentRunner.astream_events: re-raising transient throttle "
                    "for engine fallback (model=%s): %s",
                    self.model_id,
                    exc,
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
                        action_requests.append(
                            {"name": None, "args": {}, "raw": str(req)}
                        )
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


def _tool_result_text(content: Any) -> str:
    """Stringify a tool result for the ``tool_result`` event.

    A plain string passes through unchanged, and a block list with no media block
    keeps the legacy ``str(list)`` — both byte-identical to before. Only a block
    list carrying media (a binary ``read_file``: deepagents returns
    ``{"type":"image","base64":...,"mime_type":...}``) is rewritten: text blocks
    stay, every media block becomes a one-line marker with its type, mime and
    size. The model still receives the pixels (that is the ``ToolMessage``, not
    this string); this only keeps megabytes of base64 out of the SSE stream and
    the persisted output, where the UI could not render it anyway.
    """
    if not isinstance(content, list) or not any(
        isinstance(b, dict) and b.get("type") not in (None, "text") for b in content
    ):
        return content if isinstance(content, str) else str(content)
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
        elif block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        else:
            data = block.get("base64") or block.get("data") or ""
            kb = len(data) * 3 // 4 // 1024 if isinstance(data, str) else 0
            mime = block.get("mime_type") or block.get("mimeType") or ""
            parts.append(f"[{block.get('type')} {mime} {kb} KB]".replace("  ", " "))
    return "\n".join(p for p in parts if p)


def _extract_thinking(content: Any) -> str:
    """Pull streamed extended-thinking text out of a message content payload.

    Extended thinking arrives as a content BLOCK (never in ``additional_kwargs``),
    in one of two shapes depending on provider:
      - ChatAnthropic:        {"type": "thinking", "thinking": "<delta>"}
      - ChatBedrockConverse:  {"type": "reasoning_content",
                                "reasoning_content": {"type": "text", "text": "<delta>"}}
    A plain string ``content`` (no blocks) carries no thinking, so returns "".
    """
    if not isinstance(content, list):
        return ""
    out = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "thinking":
            out.append(block.get("thinking", ""))
        elif block.get("type") == "reasoning_content":
            rc = block.get("reasoning_content")
            if isinstance(rc, dict):
                out.append(rc.get("text", ""))
    return "".join(out)


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

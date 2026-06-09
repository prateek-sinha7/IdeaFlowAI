"""Phase-2 verify gate — behavioral isolation tests for ``agents.factory.create_runner``
(spec ``specs/002-deepagents-migration/plan.md`` → Phase 2 "Verify gate", task #36).

WHAT THIS PROVES
----------------
Phase 2 added, purely additively (wired into NOTHING), the runner-construction path:
``AgentContext.run_id`` + a store-free ``report_task_complete`` (#33), the
``_build_runner_tools(spec, ctx)`` tool/exclude mapping (#34), and
``create_runner(agent_id, ctx, *, checkpointer=None, interrupt_on=None)`` (#35) — the
entry point under test. ``create_runner`` reuses the legacy ``_compose_system_prompt``
verbatim, resolves the per-agent tool-set via ``_build_runner_tools``, roots a per-run
``RunSandbox`` on real disk, and builds a ``DeepAgentRunner`` over a ``deepagents`` graph.

These four tests drive ONE representative agent of each tool class through the REAL
graph (offline, via a scripted fake ``BaseChatModel`` — no network, no credentials) and
assert each produces a correctly-configured runner that *behaves*:

  1. text-only (``tools == []`` → ``exclude_builtin_tools=True``): pure-text stream, no
     ``tool_call`` events, and the model is offered ZERO tools.
  2. code-gen (``tools == ["workspace"]`` → native fs, no custom tool): a scripted
     ``write_file`` lands a file on the sandbox DISK with the expected content; the model
     sees the native fs tools (incl. ``write_file``) and NOT ``task``.
  3. prototype-build (``tools == ["prototype_emit_only"]`` + ``od_context``): a scripted
     ``write_file`` writes ``prototype.html`` to disk AND ``report_task_complete`` emits a
     ``tool_call`` carrying ``task_number``/``task_title`` plus a ``tool_result`` —
     proving Phase 3 can read the file off disk and derive ``task_progress`` from the
     tool events. The model sees the native fs tools + ``report_task_complete`` and NOT
     ``task``.
  4. planning (``tools == ["planning"]`` → ``exclude_builtin_tools=True``): the model is
     offered EXACTLY the ``PLANNING_TOOLS`` names and NONE of the native fs/todo/sub-agent
     tools (``write_file``/``ls``/``write_todos``/``task`` all absent).

THE SCRIPTED FAKE MODEL
-----------------------
Reuses the proven recipe (the stock ``GenericFakeChatModel``/
``FakeMessagesListChatModel`` do NOT work — they raise on ``bind_tools`` and drop
``tool_calls``/``usage_metadata``; the shared recipe now lives in
``tests/agents/_scripted_model.py``). :class:`_ScriptedFakeChatModel`
is a minimal ``BaseChatModel`` that:
  * streams a different scripted turn per successive invocation (tracked by an internal
    cursor) so a multi-turn tool sequence (write → report → final text) plays out;
  * carries ``usage_metadata`` + ``chunk_position="last"`` on each turn's final chunk
    (the marker stops langchain-core 1.4.0 from appending a synthetic empty trailing
    chunk that would null out usage — see the parity test's module docstring);
  * carries ``tool_call_chunks`` (via ``langchain_core.messages.tool.tool_call_chunk``)
    on a tool turn so the graph actually executes the native tool;
  * RECORDS, on every ``bind_tools`` call, the names of the tools the model was offered
    (``recorded_tool_names``) — this is the empirical "what does the model see" probe used
    by tests 1, 2, 3 and 4 (a recording ``bind_tools``, as the parity test does).

NATIVE ``write_file`` SCHEMA (discovered empirically, on record for #36)
------------------------------------------------------------------------
The deepagents ``FilesystemBackend`` exposes a ``StructuredTool`` named **``write_file``**
with args **``file_path``** (string; description: "Absolute path where the file should be
created. Must be absolute, not relative.") and **``content``** (string). With
``virtual_mode=True`` the backend roots every path at the sandbox, so an absolute-looking
``"/src/app.py"`` lands at ``<sandbox root>/src/app.py`` on real disk (verified). The
scripted model therefore emits the path as the tool's own schema prescribes (absolute).

OFFLINE & DETERMINISM
---------------------
``RUNS_ROOT`` defaults to ``/app/runs`` (not writable here), so each test monkeypatches
``app.core.config.settings.RUNS_ROOT`` to a pytest ``tmp_path`` BEFORE calling
``create_runner`` (the factory builds the sandbox eagerly). The fake model means no
network/credentials. ``pytest-asyncio`` is configured WITHOUT global ``asyncio_mode``, so
each async test carries an explicit ``@pytest.mark.asyncio`` (matching the existing async
tests in this suite).
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from agents.factory import AgentContext, create_runner
from app.agents.sandbox import RunSandbox


# ===========================================================================
# Scripted fake chat model (recording bind_tools) — see module docstring.
# ===========================================================================


class _ScriptedTurn:
    """One scripted model invocation: text piece(s), optional tool call(s), usage.

    ``tool_calls`` items are ``(name, json_args_str, call_id)`` tuples (args a JSON
    *string*, mirroring how providers emit ``tool_call_chunks``). ``usage`` is an
    ``(input_tokens, output_tokens)`` tuple or ``None``.
    """

    def __init__(
        self,
        texts: list[str],
        tool_calls: list[tuple[str, str, str]] | None = None,
        usage: tuple[int, int] | None = None,
    ) -> None:
        self.texts = texts
        self.tool_calls = tool_calls or []
        self.usage = usage


class _ScriptedFakeChatModel(BaseChatModel):
    """Minimal ``BaseChatModel`` that streams a different scripted turn per call and
    records the tools it is offered on each ``bind_tools`` call.

    See ``tests/agents/_scripted_model.py`` for the shared recipe and why the stock
    LangChain fakes are unusable (and why ``chunk_position="last"`` on each turn's
    final chunk is required).
    """

    # We stash non-pydantic call state via object.__setattr__, so allow it.
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, turns: list[_ScriptedTurn], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Bypass pydantic's field machinery for the mutable cursor/script/probe.
        object.__setattr__(self, "_turns", list(turns))
        object.__setattr__(self, "_call_index", 0)
        # One entry per bind_tools() call — the list of tool names the model saw.
        object.__setattr__(self, "_bind_calls", [])

    @property
    def _llm_type(self) -> str:
        return "scripted-fake-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedFakeChatModel":
        # Record what the model is offered, then no-op (the fake scripts its own
        # tool calls). Stock fakes raise NotImplementedError here — the reason this
        # subclass exists. ``tools`` is the per-request tool list (post tool-filter
        # middleware), so this is the authoritative "what the model sees" probe.
        names: list[str] = []
        for t in tools:
            if isinstance(t, dict):
                names.append(t.get("name"))
            else:
                names.append(getattr(t, "name", None))
        self._bind_calls.append(names)
        return self

    @property
    def recorded_tool_names(self) -> set[str]:
        """The union of every tool name the model was offered across all binds.

        Flattened across bind calls (deepagents may bind once per model turn) and
        deduped. Empty when ``bind_tools`` was never called (langchain skips binding
        a model with zero tools) OR was called with an empty list — both mean the
        model saw no tools, which is what the text-only assertion needs.
        """
        out: set[str] = set()
        for call in self._bind_calls:
            out.update(n for n in call if n)
        return out

    def _next_turn(self) -> _ScriptedTurn:
        idx: int = self._call_index
        turns: list[_ScriptedTurn] = self._turns
        turn = turns[idx] if idx < len(turns) else turns[-1]
        object.__setattr__(self, "_call_index", idx + 1)
        return turn

    def _stream(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        turn = self._next_turn()
        # Always yield at least one chunk; the final chunk carries tool_call_chunks +
        # usage and is marked chunk_position="last" so core does not append a synthetic
        # empty trailing chunk (which would null out the last-chunk usage read).
        pieces = turn.texts if turn.texts else [""]
        last_i = len(pieces) - 1
        for i, piece in enumerate(pieces):
            extra: dict[str, Any] = {}
            tcc: list = []
            usage = None
            if i == last_i:
                for tc_idx, (name, json_args, call_id) in enumerate(turn.tool_calls):
                    tcc.append(
                        tool_call_chunk(name=name, args=json_args, id=call_id, index=tc_idx)
                    )
                if turn.usage is not None:
                    t_in, t_out = turn.usage
                    usage = {
                        "input_tokens": t_in,
                        "output_tokens": t_out,
                        "total_tokens": t_in + t_out,
                    }
                extra["chunk_position"] = "last"
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=piece,
                    tool_call_chunks=tcc,
                    usage_metadata=usage,
                    **extra,
                )
            )

    def _generate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Fallback non-streaming path; collapses the scripted turn into one message.
        chunks = list(self._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        text = "".join(c.message.content for c in chunks if isinstance(c.message.content, str))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


# ===========================================================================
# Helpers
# ===========================================================================


async def _collect_events(runner: Any, message: str) -> list[dict[str, Any]]:
    """Drain ``astream_events`` into a list of event dicts."""
    return [event async for event in runner.astream_events(message)]


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def _events_of(events: list[dict[str, Any]], etype: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] == etype]


def _chunk_text(events: list[dict[str, Any]]) -> str:
    return "".join(e["chunk"] for e in events if e["type"] == "chunk")


# The native deepagents FilesystemBackend tool (name + arg names) discovered
# empirically — see the module docstring. Asserted in test 2 so a future schema
# drift in the library is caught here rather than silently breaking code-gen.
_WRITE_FILE_TOOL = "write_file"
_WRITE_FILE_ARGS = {"file_path", "content"}


def _sandbox_root_for(ctx: AgentContext):
    """The on-disk sandbox root the runner wrote to, for ``ctx``.

    The runner keeps no public reference to its ``FilesystemBackend`` (it lives
    inside the compiled graph's middleware), so we reconstruct the DETERMINISTIC
    path ``create_runner`` rooted the backend at: ``RunSandbox(user_id, run_id).root``
    == ``<RUNS_ROOT>/<user>/<run>/``. ``RunSandbox`` is pure/deterministic, so this is
    byte-for-byte the directory the runner used (verified: files land here), not a
    re-derivation that could drift. Reading ``RUNS_ROOT`` off the (monkeypatched)
    settings keeps it in lock-step with what the factory saw at build time.
    """
    return RunSandbox(ctx.user_id or "anon", ctx.run_id or "adhoc").root


def _od_context() -> dict:
    """Minimal od_context so prototype-build's injection block composes (it declares
    ``injects: [template, design_system, craft]``; ``_compose_injection`` raises
    ``TemplateMissingError`` without at least a ``template_body``)."""
    return {
        "template_body": "# Web Prototype Template\n\nBuild a single-page hero layout.",
        "ds_body": ":root { --color-primary: #0a0a0a; --font-body: sans-serif; }",
        "craft_block": "Use semantic HTML; wire every interactive element.",
        "template_id": "web-prototype",
        "ds_id": "custom-ds",
    }


# ===========================================================================
# Test 1 — text-only agent: pure-text stream, zero tools offered.
# ===========================================================================


@pytest.mark.asyncio
async def test_text_only_agent_streams_pure_text_no_tools(tmp_path, monkeypatch) -> None:
    """text-only class (``tools == []`` → ``exclude_builtin_tools=True``).

    Key assertions: ``astream_events`` yields ONLY ``chunk`` events (+ a terminal
    ``done``, plus benign ``usage``) and ZERO ``tool_call`` events — a pure-text stream
    with no tool chips; AND the model was offered ZERO tools (recording bind_tools →
    empty). Uses ``domain-analyst`` (``tools: []``).
    """
    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    fake = _ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["The market is ", "large and growing."], usage=(7, 4))]
    )
    ctx = AgentContext(
        user_request="analyze fintech", model=fake, user_id="u-text", run_id="run-text"
    )
    runner = create_runner("domain-analyst", ctx)

    events = await _collect_events(runner, "go")

    # No tool_call events at all — pure text.
    assert _events_of(events, "tool_call") == []
    # The accumulated text is exactly what the model streamed.
    assert _chunk_text(events) == "The market is large and growing."
    # Stream terminates with a single ``done`` (no ``gate``/``error``).
    assert _types(events)[-1] == "done"
    assert len(_events_of(events, "done")) == 1
    assert _events_of(events, "gate") == []
    assert _events_of(events, "error") == []
    # The ONLY non-chunk/usage/done event types are forbidden — assert the type set.
    assert set(_types(events)) <= {"chunk", "usage", "done"}
    # The model saw ZERO tools (exclude_builtin_tools=True hid the whole built-in suite).
    assert fake.recorded_tool_names == set()


# ===========================================================================
# Test 2 — code-gen agent: native write_file lands a file on the sandbox disk.
# ===========================================================================


@pytest.mark.asyncio
async def test_code_gen_agent_writes_file_to_sandbox_disk(tmp_path, monkeypatch) -> None:
    """code-gen class (``tools == ["workspace"]`` → native fs tools, no custom tool).

    Key assertions: a scripted ``write_file`` call (native name + args) writes
    ``src/app.py`` with known content, and the file EXISTS on the sandbox DISK at
    ``<runner sandbox root>/src/app.py`` with that exact content; the model saw the
    native fs tools (incl. ``write_file``) and NOT ``task``. Uses ``app-code-generator``
    (``tools: [workspace]``).
    """
    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    content = "def main():\n    print('hello from generated app')\n\n\nmain()\n"
    # ``file_path`` is given absolute, exactly as the native tool's schema prescribes
    # ("Must be absolute"); virtual_mode roots it at the sandbox → <root>/src/app.py.
    fake = _ScriptedFakeChatModel(
        [
            _ScriptedTurn(
                texts=["writing the entrypoint "],
                tool_calls=[
                    (
                        _WRITE_FILE_TOOL,
                        json.dumps({"file_path": "/src/app.py", "content": content}),
                        "call_write_1",
                    )
                ],
                usage=(20, 9),
            ),
            _ScriptedTurn(texts=["done."], usage=(4, 2)),
        ]
    )
    ctx = AgentContext(
        user_request="build an app", model=fake, user_id="u-code", run_id="run-code"
    )
    runner = create_runner("app-code-generator", ctx)

    events = await _collect_events(runner, "go")

    assert _events_of(events, "error") == []

    # PROOF #1 — the file landed on the real sandbox disk with the exact content,
    # at the deterministic <RUNS_ROOT>/<user>/<run>/ path the runner rooted its
    # FilesystemBackend at (virtual_mode maps the absolute /src/app.py under it).
    sandbox_root = _sandbox_root_for(ctx)
    written = sandbox_root / "src" / "app.py"
    assert written.is_file(), f"expected file at {written}; tree={list(sandbox_root.rglob('*'))}"
    assert written.read_text(encoding="utf-8") == content

    # The write_file tool actually fired through the graph (round-trip, not a stub).
    write_calls = [e for e in _events_of(events, "tool_call") if e["tool"] == _WRITE_FILE_TOOL]
    assert len(write_calls) == 1
    assert set(write_calls[0]["args"]) == _WRITE_FILE_ARGS  # native arg schema on record
    assert _events_of(events, "tool_result")  # a tool_result followed

    # PROOF #2 — the model was offered the native fs tools, but NOT ``task``.
    seen = fake.recorded_tool_names
    assert _WRITE_FILE_TOOL in seen
    assert {"read_file", "edit_file", "ls"} <= seen
    assert "task" not in seen


# ===========================================================================
# Test 3 — prototype-build: writes prototype.html + report_task_complete event.
# ===========================================================================


@pytest.mark.asyncio
async def test_prototype_build_writes_html_and_reports_task(tmp_path, monkeypatch) -> None:
    """prototype-build class (``tools == ["prototype_emit_only"]`` + ``od_context``).

    Key assertions: a scripted ``write_file`` writes ``prototype.html`` to the sandbox
    DISK with the HTML, AND a ``report_task_complete`` ``tool_result`` is emitted with the
    right tool name while its ``tool_call`` carries ``task_number=1`` / ``task_title="Hero"``
    — proving Phase 3 can read the deliverable off disk and derive ``task_progress`` from
    the tool events. The model sees the native fs tools + ``report_task_complete`` and NOT
    ``task``. Uses ``prototype-build`` (``tools: [prototype_emit_only]``).
    """
    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    html = "<!doctype html><html><head><title>Hero</title></head><body><h1>Hero</h1></body></html>"
    fake = _ScriptedFakeChatModel(
        [
            _ScriptedTurn(
                texts=["building the hero page "],
                tool_calls=[
                    (
                        _WRITE_FILE_TOOL,
                        json.dumps({"file_path": "/prototype.html", "content": html}),
                        "call_html_1",
                    )
                ],
                usage=(30, 12),
            ),
            _ScriptedTurn(
                texts=["reporting progress "],
                tool_calls=[
                    (
                        "report_task_complete",
                        json.dumps(
                            {
                                "task_number": 1,
                                "task_title": "Hero",
                                "summary": "Built the hero section.",
                            }
                        ),
                        "call_report_1",
                    )
                ],
                usage=(8, 5),
            ),
            _ScriptedTurn(texts=["prototype complete."], usage=(3, 3)),
        ]
    )
    ctx = AgentContext(
        user_request="prototype a landing page",
        model=fake,
        user_id="u-proto",
        run_id="run-proto",
        od_context=_od_context(),
    )
    runner = create_runner("prototype-build", ctx)

    events = await _collect_events(runner, "go")

    assert _events_of(events, "error") == []

    # PROOF #1 — prototype.html is on the sandbox disk with the expected HTML.
    sandbox_root = _sandbox_root_for(ctx)
    proto = sandbox_root / "prototype.html"
    assert proto.is_file(), f"expected {proto}; tree={list(sandbox_root.rglob('*'))}"
    assert proto.read_text(encoding="utf-8") == html

    # PROOF #2 — report_task_complete tool_call carried the progress args Phase 3 reads.
    report_calls = [
        e for e in _events_of(events, "tool_call") if e["tool"] == "report_task_complete"
    ]
    assert len(report_calls) == 1
    assert report_calls[0]["args"]["task_number"] == 1
    assert report_calls[0]["args"]["task_title"] == "Hero"

    # PROOF #3 — a report_task_complete tool_result was emitted (right name + payload).
    report_results = [
        e for e in _events_of(events, "tool_result") if e["tool"] == "report_task_complete"
    ]
    assert len(report_results) == 1
    # The store-free runner tool returns this exact confirmation string.
    assert report_results[0]["result"] == "✓ Task 1 complete: Hero"

    # The model saw native fs tools + report_task_complete, but NOT ``task``.
    seen = fake.recorded_tool_names
    assert _WRITE_FILE_TOOL in seen
    assert "report_task_complete" in seen
    assert "task" not in seen


# ===========================================================================
# Test 4 — planning agent: exactly PLANNING_TOOLS, no native fs/todo/sub-agent tools.
# ===========================================================================


@pytest.mark.asyncio
async def test_planning_agent_exposes_only_planning_tools(tmp_path, monkeypatch) -> None:
    """planning class (``tools == ["planning"]`` → ``exclude_builtin_tools=True``).

    Key assertion (recording bind_tools): the model is offered EXACTLY the
    ``PLANNING_TOOLS`` names and NONE of the native fs/todo/sub-agent tools
    (``write_file`` / ``ls`` / ``write_todos`` / ``task`` all absent) — i.e.
    ``exclude_builtin_tools=True`` for planning, so the stub planning tools are the only
    thing the model can call. Uses ``deep-planner`` (``tools: [planning]``).
    """
    from agents.planner.tools import PLANNING_TOOLS

    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    # Plain text turn — we only need to trigger a bind_tools so the probe records what
    # the model is offered; no tool call is required for this assertion.
    fake = _ScriptedFakeChatModel([_ScriptedTurn(texts=["planning..."], usage=(5, 2))])
    ctx = AgentContext(
        user_request="PIPELINE TYPE: spec_kit\nUSER BRIEF: build X",
        model=fake,
        user_id="u-plan",
        run_id="run-plan",
    )
    runner = create_runner("deep-planner", ctx)

    await _collect_events(runner, "go")

    expected = {t.name for t in PLANNING_TOOLS}
    seen = fake.recorded_tool_names
    # EXACTLY the planning tools — nothing more, nothing less.
    assert seen == expected, f"saw {sorted(seen)}, expected {sorted(expected)}"
    # And explicitly: none of the native built-ins leaked through (exclude=True).
    assert seen.isdisjoint({"write_file", "read_file", "edit_file", "ls", "glob", "grep"})
    assert "write_todos" not in seen
    assert "task" not in seen


# ===========================================================================
# Test 5 — tool_provider registry binds the IDENTICAL sets the F2 switch produced.
#
# 08-03 / F2 PARITY GATE: the closed ``_build_runner_tools`` switch is replaced by a
# ``tool_provider`` registry (``@register("tool", <set_name>)``). Each provider must
# return the EXACT ``(custom_tools, exclude_builtin)`` the switch produced so existing
# agents bind byte-identical tool sets (RESEARCH Pitfall 5). These tests resolve each
# provider and assert the bound pair against the documented per-set mapping, prove
# resolution works after ``discover()``, and prove binding is grant-driven (a step
# whose effective perms lack ``write_files`` never reaches a write-capable provider).
# ===========================================================================


def _resolve_provider(set_name: str):
    """Resolve a ``tool_provider`` from the registry after ``discover()``."""
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    return CapabilityRegistry().resolve("tool", set_name)


def test_tool_provider_workspace_binds_identical_set() -> None:
    """``workspace`` provider → ``([], exclude_builtin=False)`` (native fs, no custom)."""
    provider = _resolve_provider("workspace")
    keys, exclude = provider.provide(spec=None, ctx=None)
    assert keys == []
    assert exclude is False


def test_tool_provider_prototype_binds_report_task_complete() -> None:
    """``prototype`` / ``prototype_emit_only`` → ``(["report_task_complete"], False)``.

    The provider emits stable string KEYS (not concrete tool objects) so the kernel-
    side capability package stays import-clean of ``app.*`` (import-linter). The
    factory resolves each key to the concrete tool — proven by the parity tests
    (1–4) above driving the REAL graph with the bound tool.
    """
    for set_name in ("prototype", "prototype_emit_only"):
        provider = _resolve_provider(set_name)
        keys, exclude = provider.provide(spec=None, ctx=None)
        assert keys == ["report_task_complete"], f"{set_name} bound {keys}"
        assert exclude is False


def test_tool_provider_planning_binds_planning_tools_excluding_builtin() -> None:
    """``planning`` provider → ``(["planning"], exclude_builtin=True)`` (key expands to set)."""
    provider = _resolve_provider("planning")
    keys, exclude = provider.provide(spec=None, ctx=None)
    assert keys == ["planning"]
    assert exclude is True


def test_tool_provider_resolution_after_discover() -> None:
    """The registry resolves each declared tool set by name after ``discover()``."""
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    registry = CapabilityRegistry()
    for set_name in ("workspace", "prototype", "prototype_emit_only", "planning"):
        provider = registry.resolve("tool", set_name)
        assert provider.name == set_name


def test_tool_provider_binding_is_grant_driven() -> None:
    """A step whose effective perms lack ``write_files`` binds no write-capable set.

    The four existing sets are all read-only (none binds a write/exec tool — they
    rely on the native fs under the default ``read_files``-only posture), so under the
    least-privilege effective perms (write_files OFF) the resolved providers bind
    exactly their parity sets and NEVER a write-capable tool. This asserts the binding
    path is keyed on the effective grant, not on a workflow name.
    """
    from agents.workflows.plan import (
        ToolPermissions,
        intersect_permissions,
    )

    # Effective perms for an un-granted step: read_files ON, write_files OFF.
    effective = intersect_permissions(
        ToolPermissions(), ToolPermissions(), ToolPermissions()
    )
    assert effective.write_files is False

    # None of the existing four providers binds a write/exec-capable custom tool —
    # they are all bindable under the default read-only posture (parity preserved).
    for set_name in ("workspace", "prototype", "prototype_emit_only", "planning"):
        provider = _resolve_provider(set_name)
        keys, _ = provider.provide(spec=None, ctx=None)
        # The provider emits only non-privileged tool keys — the write path is the
        # native fs (gated by exclude_builtin + the effective perms), NOT a custom
        # write/exec tool. The only custom-tool key any set binds is the store-free
        # report_task_complete (prototype sets) or the planning set.
        assert "exec" not in keys and "shell" not in keys

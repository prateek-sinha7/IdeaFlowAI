"""agents/capabilities/tools/providers.py — the tool_provider capabilities (08-03 / F2 / §30).

Lifts the closed factory tool-binding switch (F2) into registered
``ToolProvider`` capabilities — one per AGENT.md tool-set name (``workspace`` /
``prototype`` / ``prototype_emit_only`` / ``planning``). Each ``@register("tool",
<set_name>)`` and satisfies the ``ToolProvider`` port (``provide(spec, ctx) ->
(custom_tool_keys, exclude_builtin)``), reproducing the EXACT tool binding the switch
produced so existing agents bind BYTE-IDENTICAL tool sets (parity per RESEARCH
Pitfall 5):

  * ``workspace``           → ``([reserved_path_guard], exclude_builtin=False)`` — native fs
                              writes the deliverable to the run sandbox; the guard key
                              activates the ``_ReservedPathGuardMiddleware`` in the runner
                              (Requirement 18, V2-Q7).
  * ``prototype`` /
    ``prototype_emit_only`` → ``(["report_task_complete", reserved_path_guard], False)`` — the
                              agent writes ``prototype.html`` via native write_file/edit_file;
                              the one surviving custom tool is store-free
                              ``report_task_complete``.  The guard key is included because
                              native fs tools are still bound (``exclude_builtin=False``).
  * ``planning``            → ``(["planning"], True)`` — the stub PLANNING_TOOLS, no disk.
                              No guard key: ``exclude_builtin=True`` means no fs tools.

The provider returns custom-tool KEYS (stable string ids), NOT concrete tool objects:
the concrete ``@tool`` implementations live in the app layer
(``app/agents/tools/runner_tools.py``) and the kernel-side capability package MUST NOT
import ``app.*`` (import-linter: ``agents.capabilities`` ↛ ``app``). The factory (which
IS allowed to import ``app`` — it is the composition root) resolves each key to the
concrete tool via its ``_CUSTOM_TOOL_RESOLVERS`` map. This keeps the hexagonal
direction one-way (capability ↛ app) while preserving byte-identical binding.

The text-only ``[]`` case (``exclude_builtin=True``, no custom tool) is NOT a named
provider — it is the ABSENCE of a tool set, handled by the factory's binding loop
(no set to resolve ⇒ pure-text). The named providers above are the lifted switch.

Grant-driven binding (D-07): the factory intersects the step's effective
``ToolPermissions`` BEFORE resolving providers — a step whose effective perms lack
``write_files`` never reaches a write-capable provider. None of the four existing
sets is write/exec-privileged (they all bind under the default ``read_files``-only
posture, preserving parity), but the structure supports a privileged set registering
``user_allowed=False`` so it stays off the user palette.

Reserved-path guard (Requirement 18 AC 3, V2-Q7 — SGV2-GAP-002 closure):
All filesystem-capable tool sets emit ``TOOL_RESERVED_PATH_GUARD`` as an extra key.
The factory resolves this key to a sentinel object that signals ``DeepAgentRunner``
to attach a ``_ReservedPathGuardMiddleware`` (app-side, imported from
``app.agents.deep_agent_runner``).  That middleware:
  * Refuses WRITES (``write_file``, ``edit_file``, ``create_directory``) to any path
    whose normalised prefix matches ``RESERVED_PATHS`` from ``app.agents.sandbox``.
  * Refuses READS (``read_file``, ``ls``, ``glob``, ``grep``) to reserved paths
    UNLESS the prefix is in ``AGENT_READABLE_RESERVED`` (i.e. ``.context/`` only;
    ``.chain/`` is deliberately excluded — Requirement 18 AC 8).
The constants are imported in the app-layer module (``app.agents.deep_agent_runner``)
where the ``app.*`` import boundary allows it.  This file only names the key.

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing —
NO ``app.*`` import, NO kernel import. The concrete-tool resolution is the factory's job.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

# Stable custom-tool KEYS the providers emit (resolved to concrete tools by the
# factory's _CUSTOM_TOOL_RESOLVERS map). String keys keep the kernel-side provider
# import-clean of the app-layer concrete tools (import-linter: capability ↛ app).
TOOL_REPORT_TASK_COMPLETE = "report_task_complete"
TOOL_PLANNING_SET = "planning"
TOOL_SPAWN_SUBAGENTS = "spawn_subagents"  # Phase 11 / FANOUT-01 (user_allowed=False)
TOOL_ASK_USER = "ask_user"                # HITL request emitter (user_allowed=False)

# Reserved-path guard key (Requirement 18 AC 3, V2-Q7 — SGV2-GAP-002 closure).
#
# Emitted by every filesystem-capable tool set (``workspace``, ``prototype``,
# ``prototype_emit_only``).  The factory resolves this key to the
# ``_RESERVED_PATH_GUARD_SENTINEL`` object defined in
# ``app.agents.deep_agent_runner``, which signals ``DeepAgentRunner.__init__``
# to attach the ``_ReservedPathGuardMiddleware``.
#
# The middleware enforces the two rules of Requirement 18 AC 3:
#   • WRITES (write_file, edit_file, create_directory) → refused for any path
#     under any entry in ``RESERVED_PATHS`` (app.agents.sandbox).
#   • READS (read_file, ls, glob, grep) → refused for any path under
#     ``RESERVED_PATHS`` UNLESS the prefix is in ``AGENT_READABLE_RESERVED``
#     (i.e. ``.context/`` only; ``.chain/`` is deliberately NOT readable).
#
# The import of ``RESERVED_PATHS`` and ``AGENT_READABLE_RESERVED`` from
# ``app.agents.sandbox`` happens in the app-layer runner module where the
# ``app.*`` import is legal — this module only names the key.
TOOL_RESERVED_PATH_GUARD = "reserved_path_guard"


@register(
    "tool",
    "workspace",
    user_allowed=True,
    description="Code-gen workspace: native filesystem tools writing deliverables to the run sandbox.",
)
class WorkspaceToolProvider:
    """Code-gen tool set: native fs tools only (``name='workspace'``).

    Returns ``([reserved_path_guard], exclude_builtin=False)`` — no custom
    file-write tool; the native deepagents filesystem tools write the deliverable
    to the run sandbox disk (``serialize_sandbox_deliverable`` turns them into the
    ``filename:``-block output).

    ``TOOL_RESERVED_PATH_GUARD`` is emitted so the factory activates the
    ``_ReservedPathGuardMiddleware`` in ``DeepAgentRunner``, enforcing that agent
    tools cannot read or write any path listed in ``RESERVED_PATHS``, except that
    reads under ``AGENT_READABLE_RESERVED`` (``.context/``) are permitted
    (Requirement 18 AC 3, V2-Q7).
    """

    name = "workspace"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_RESERVED_PATH_GUARD], False)


@register(
    "tool",
    "prototype",
    user_allowed=True,
    description="Prototype tool set: native filesystem tools plus the report_task_complete progress signal.",
)
class PrototypeToolProvider:
    """Prototype tool set: ``report_task_complete`` + native fs (``name='prototype'``).

    Returns ``(["report_task_complete", reserved_path_guard], exclude_builtin=False)``
    — the agent writes ``prototype.html`` via native write_file/edit_file; the one
    surviving custom tool is the store-free ``report_task_complete`` (drives
    ``task_progress``).

    ``TOOL_RESERVED_PATH_GUARD`` is included because native fs tools remain bound
    (``exclude_builtin=False``); the guard activates ``_ReservedPathGuardMiddleware``
    in the runner (Requirement 18 AC 3, V2-Q7).
    """

    name = "prototype"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_REPORT_TASK_COMPLETE, TOOL_RESERVED_PATH_GUARD], False)


@register(
    "tool",
    "prototype_emit_only",
    user_allowed=True,
    description="Emit-only prototype tool set: same bindings as prototype (report_task_complete plus native fs).",
)
class PrototypeEmitOnlyToolProvider:
    """Prototype-emit tool set — same binding as ``prototype`` (``name='prototype_emit_only'``).

    The closed switch mapped ``prototype`` and ``prototype_emit_only`` to the SAME
    ``([report_task_complete], False)`` pair; this provider reproduces that exactly,
    with ``TOOL_RESERVED_PATH_GUARD`` added alongside (Requirement 18 AC 3, V2-Q7).
    """

    name = "prototype_emit_only"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_REPORT_TASK_COMPLETE, TOOL_RESERVED_PATH_GUARD], False)


@register(
    "tool",
    "planning",
    user_allowed=True,
    description="Planning tool set: the deep-planner stub tools only, with no disk access.",
)
class PlanningToolProvider:
    """Planning tool set: the stub ``PLANNING_TOOLS``, no disk (``name='planning'``).

    Returns ``(["planning"], exclude_builtin=True)`` — the model sees EXACTLY the
    planning tools and none of the native fs/todo/sub-agent tools. The ``"planning"``
    key expands to the whole ``PLANNING_TOOLS`` list in the factory resolver.
    """

    name = "planning"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_PLANNING_SET], True)


@register(
    "tool",
    "spawn_subagents",
    user_allowed=False,
    description="Privileged fan-out request emitter; the engine fulfils spawns via the single kernel run_fanout path.",
)
class SpawnSubagentsToolProvider:
    """Fan-out request-emitter tool set (``name='spawn_subagents'``, FANOUT-01).

    Returns ``(["spawn_subagents"], exclude_builtin=False)`` — the agent gets the
    store-free / spawn-free ``spawn_subagents`` request emitter (it returns a JSON
    request only; the engine derives the request and fulfils it via the SINGLE kernel
    ``run_fanout`` spawn path). ``user_allowed=False`` (CAP-03 / T-11-01-01): the
    compiler rejects any user/db manifest that grants this tool, so spawn power stays
    off the user palette. The capability layer imports NO concrete tool (the
    ``PrototypeToolProvider`` precedent) — the factory resolves the key.
    """

    name = "spawn_subagents"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_SPAWN_SUBAGENTS], False)


@register(
    "tool",
    "ask_user",
    user_allowed=False,
    description="Privileged HITL request emitter; the engine fulfils the pause via ClarifyEngine.",
)
class AskUserToolProvider:
    """Ask-the-user request-emitter tool set (``name='ask_user'``).

    Returns ``(["ask_user"], exclude_builtin=False)`` — the agent gets the
    store-free ``ask_user`` request emitter (it returns a JSON request only; the
    ENGINE derives the request from the tool's result event and fulfils it by
    running the existing ``ClarifyEngine``, which owns the emit/pause/merge).
    ``user_allowed=False``: pausing a run for a human is privileged, so it stays
    off the user palette exactly as ``spawn_subagents`` does. The capability layer
    imports NO concrete tool — the factory resolves the key.
    """

    name = "ask_user"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_ASK_USER], False)

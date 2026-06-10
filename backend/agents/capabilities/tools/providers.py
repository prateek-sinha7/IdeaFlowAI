"""agents/capabilities/tools/providers.py — the tool_provider capabilities (08-03 / F2 / §30).

Lifts the closed factory tool-binding switch (F2) into registered
``ToolProvider`` capabilities — one per AGENT.md tool-set name (``workspace`` /
``prototype`` / ``prototype_emit_only`` / ``planning``). Each ``@register("tool",
<set_name>)`` and satisfies the ``ToolProvider`` port (``provide(spec, ctx) ->
(custom_tool_keys, exclude_builtin)``), reproducing the EXACT tool binding the switch
produced so existing agents bind BYTE-IDENTICAL tool sets (parity per RESEARCH
Pitfall 5):

  * ``workspace``           → ``([], exclude_builtin=False)`` — native fs writes the
                              deliverable to the run sandbox; no custom tool.
  * ``prototype`` /
    ``prototype_emit_only`` → ``(["report_task_complete"], False)`` — the agent writes
                              ``prototype.html`` via native write_file/edit_file; the
                              one surviving custom tool is store-free
                              ``report_task_complete``.
  * ``planning``            → ``(["planning"], True)`` — the stub PLANNING_TOOLS, no disk.

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


@register("tool", "workspace", user_allowed=True)
class WorkspaceToolProvider:
    """Code-gen tool set: native fs tools only (``name='workspace'``).

    Returns ``([], exclude_builtin=False)`` — no custom tool; the native deepagents
    filesystem tools write the deliverable to the run sandbox disk
    (``serialize_sandbox_deliverable`` turns them into the ``filename:``-block output).
    """

    name = "workspace"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([], False)


@register("tool", "prototype", user_allowed=True)
class PrototypeToolProvider:
    """Prototype tool set: ``report_task_complete`` + native fs (``name='prototype'``).

    Returns ``(["report_task_complete"], exclude_builtin=False)`` — the agent writes
    ``prototype.html`` via native write_file/edit_file; the one surviving custom tool
    is the store-free ``report_task_complete`` (drives ``task_progress``).
    """

    name = "prototype"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_REPORT_TASK_COMPLETE], False)


@register("tool", "prototype_emit_only", user_allowed=True)
class PrototypeEmitOnlyToolProvider:
    """Prototype-emit tool set — same binding as ``prototype`` (``name='prototype_emit_only'``).

    The closed switch mapped ``prototype`` and ``prototype_emit_only`` to the SAME
    ``([report_task_complete], False)`` pair; this provider reproduces that exactly.
    """

    name = "prototype_emit_only"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_REPORT_TASK_COMPLETE], False)


@register("tool", "planning", user_allowed=True)
class PlanningToolProvider:
    """Planning tool set: the stub ``PLANNING_TOOLS``, no disk (``name='planning'``).

    Returns ``(["planning"], exclude_builtin=True)`` — the model sees EXACTLY the
    planning tools and none of the native fs/todo/sub-agent tools. The ``"planning"``
    key expands to the whole ``PLANNING_TOOLS`` list in the factory resolver.
    """

    name = "planning"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_PLANNING_SET], True)


@register("tool", "spawn_subagents", user_allowed=False)
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

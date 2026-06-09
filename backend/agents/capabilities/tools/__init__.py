"""agents/capabilities/tools/ — the ToolProvider capability package (08-03 / F2 / §30).

Importing this package imports ``providers``, firing each
``@register("tool", <set_name>)`` decorator so ``discover()`` (which best-effort
imports this package) binds every tool set into the registry. The lifted F2 switch
becomes four registered ``ToolProvider`` impls:

  * ``workspace``           — native fs only (code-gen deliverables)
  * ``prototype`` /
    ``prototype_emit_only`` — ``report_task_complete`` + native fs
  * ``planning``            — the stub ``PLANNING_TOOLS``, no disk

Each ``provide(spec, ctx)`` returns the ``(custom_tool_keys, exclude_builtin)`` pair
the closed factory tool switch (F2) produced (byte-identical parity). The
text-only ``[]`` case is the absence of a tool set (handled by the factory's binding
loop), NOT a named provider.
"""

from __future__ import annotations

from agents.capabilities.tools import providers  # noqa: F401 — import side effect: @register

__all__ = ["providers"]

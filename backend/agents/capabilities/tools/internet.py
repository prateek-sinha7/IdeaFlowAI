"""agents/capabilities/tools/internet.py — the ``internet`` tool_provider capability (R-25 / Q7).

Registers ``@register("tool", "internet", user_allowed=True)`` binding two
LangChain ``@tool`` STUBS — ``web_search`` and ``web_fetch`` — both of which
return the fixed string ``"internet access is not yet available."`` and never
raise.

This is deliberately a STUB, not a provider (Q7): no web tool of any kind
exists in the backend today, so this is net-new capability rather than a
toggle over something already built. Provider selection, API-key handling,
and egress policy deserve their own spec. Accordingly this module contains
NO network call, NO http client import, NO API key read, and NO egress of
any kind — the switch ships here; the real provider lands in a later spec.

Mirrors the ``providers.py`` idiom (same ``@register("tool", ...)`` shape,
same ``provide(spec, ctx) -> (custom_tool_keys, exclude_builtin)`` contract)
so a future concrete provider is a drop-in replacement. Returns the two tool
KEYS (not tool objects) as string ids, matching ``ToolProvider.provide``'s
existing key-based resolution style in ``providers.py``.

Binding site (documented, not wired here — see this task's report): the
manifest's ``capabilities: {internet: true}`` flag must be intersected in
``agents/factory.py`` alongside the existing tool-set resolution
(``_resolve_runner_tools`` / ``_resolve_custom_tool_keys``) so
``compiled.capabilities.get("internet")`` gates whether this provider's keys
are resolved. This file registers the provider only; the engine/factory
binding is out of scope for this task (other agents are editing those files).

Import purity (import-linter): imports ONLY the registry decorator +
``langchain_core.tools`` (already used kernel-side, e.g.
``agents/planner/tools.py``) — NO ``app.*`` import, NO network library.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from agents.capabilities.registry import register

# Stable custom-tool KEYS this provider emits, mirroring providers.py's
# key-based ``provide()`` contract (the factory resolves keys -> concrete
# tools; see the binding-site note above).
TOOL_WEB_SEARCH = "web_search"
TOOL_WEB_FETCH = "web_fetch"

_NOT_AVAILABLE = "internet access is not yet available."


@tool
def web_search(query: str) -> str:
    """Search the web for ``query``. Stub: internet access is not yet available."""
    return _NOT_AVAILABLE


@tool
def web_fetch(url: str) -> str:
    """Fetch the contents of ``url``. Stub: internet access is not yet available."""
    return _NOT_AVAILABLE


@register(
    "tool",
    "internet",
    user_allowed=True,
    description="Internet access stub: web_search/web_fetch always return "
    "'internet access is not yet available.' No network egress exists yet (R-25).",
)
class InternetToolProvider:
    """Internet tool set: ``web_search`` + ``web_fetch`` stubs (``name='internet'``).

    Bound only when the workflow declares ``capabilities: {internet: true}``
    (R-25). Returns ``(["web_search", "web_fetch"], exclude_builtin=False)`` —
    native fs/todo tools stay available alongside the two stubs. Neither stub
    ever raises; with the flag off the tools are simply absent.
    """

    name = "internet"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_WEB_SEARCH, TOOL_WEB_FETCH], False)

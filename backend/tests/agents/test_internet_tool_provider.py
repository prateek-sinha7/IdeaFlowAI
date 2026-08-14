"""Tests for the ``internet`` tool_provider capability stub (R-25 / AC-16 / Q7).

Covers:
  - the capability registers and resolves via ``CapabilityRegistry``;
  - ``provide()`` returns the two tool keys (with the "flag on" binding);
  - ``web_search``/``web_fetch`` each return the exact stub message and never
    raise (the "flag off" case is simply the tools being absent — this
    module's ``provide()`` is the only thing gated, and that gate lives
    outside this file per the task's binding-site note);
  - the module never imports a network library — a blunt but real guard that
    this stays a stub (no egress, per Q7).
"""

from __future__ import annotations

import inspect

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.capabilities.tools.internet import (
    TOOL_WEB_FETCH,
    TOOL_WEB_SEARCH,
    InternetToolProvider,
    web_fetch,
    web_search,
)

_NOT_AVAILABLE = "internet access is not yet available."


@pytest.fixture()
def reg() -> CapabilityRegistry:
    discover()
    return CapabilityRegistry()


def test_internet_capability_registers_and_resolves(reg: CapabilityRegistry) -> None:
    impl = reg.resolve("tool", "internet")
    assert isinstance(impl, InternetToolProvider)
    assert impl.name == "internet"


def test_internet_capability_is_user_allowed(reg: CapabilityRegistry) -> None:
    assert reg.is_registered("tool", "internet")


def test_provide_returns_both_tool_keys() -> None:
    provider = InternetToolProvider()
    keys, exclude_builtin = provider.provide(spec=None, ctx=None)
    assert keys == [TOOL_WEB_SEARCH, TOOL_WEB_FETCH]
    assert exclude_builtin is False


def test_web_search_returns_exact_message() -> None:
    assert web_search.invoke({"query": "anything"}) == _NOT_AVAILABLE


def test_web_fetch_returns_exact_message() -> None:
    assert web_fetch.invoke({"url": "https://example.com"}) == _NOT_AVAILABLE


def test_web_search_never_raises_on_empty_input() -> None:
    assert web_search.invoke({"query": ""}) == _NOT_AVAILABLE


def test_web_fetch_never_raises_on_empty_input() -> None:
    assert web_fetch.invoke({"url": ""}) == _NOT_AVAILABLE


def test_module_imports_no_network_library() -> None:
    """Blunt source-inspection guard (Q7): this file must never gain egress."""
    import agents.capabilities.tools.internet as mod

    src = inspect.getsource(mod)
    for banned in ("requests", "httpx", "urllib", "aiohttp"):
        assert banned not in src, f"internet.py must not import/reference {banned!r}"

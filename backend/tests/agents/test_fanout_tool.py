"""tests/agents/test_fanout_tool.py — the spawn_subagents request-emitter tool (FANOUT-01).

Proves the runtime fan-out entry point is permission-bound AND spawn-free:

  * the ``spawn_subagents`` capability provider is registered ``user_allowed=False``
    (CAP-03 — never on the user palette, T-11-01-01);
  * the concrete ``@tool spawn_subagents`` is a STORE-FREE / SPAWN-FREE request
    emitter — its body returns a structured JSON request ONLY (no asyncio, no
    run_fanout import, no kernel import — T-11-01-04 / FANOUT-01 grep);
  * a step without ``tools.spawn_subagents`` never binds the tool (the standard
    tool-set binding mechanism — a tool set only binds when declared in spec.tools).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


def test_spawn_subagents_provider_is_not_user_allowed():
    from agents.capabilities.registry import discover, CapabilityRegistry

    discover()
    registry = CapabilityRegistry()
    assert registry.is_registered("tool", "spawn_subagents")
    # CAP-03 / T-11-01-01: privileged — never on the user palette.
    assert registry.is_user_allowed("tool", "spawn_subagents") is False


def test_spawn_subagents_provider_emits_the_key():
    from agents.capabilities.registry import discover, CapabilityRegistry

    discover()
    registry = CapabilityRegistry()
    provider = registry.resolve("tool", "spawn_subagents")
    keys, exclude_builtin = provider.provide(None, None)
    assert keys == ["spawn_subagents"]
    assert exclude_builtin is False


def test_spawn_subagents_tool_emits_structured_request_only():
    """The tool body returns the JSON request and spawns NOTHING (FANOUT-01)."""
    from app.agents.tools.runner_tools import spawn_subagents

    result = spawn_subagents.invoke({"tasks": ["a", "b", "c"], "mode": "parallel"})
    payload = json.loads(result)
    assert payload["fanout_request"] == ["a", "b", "c"]
    assert payload["mode"] == "parallel"


def test_spawn_subagents_tool_module_is_spawn_free():
    """FANOUT-01 / T-11-01-04: the tool module imports no spawn machinery."""
    mod = Path(__file__).resolve().parents[2] / "app" / "agents" / "tools" / "runner_tools.py"
    src = mod.read_text()
    # No asyncio / run_fanout / kernel import anywhere in the tool module.
    body = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    assert "asyncio" not in body, "spawn_subagents must not import/use asyncio (spawn-free)"
    assert "run_fanout" not in body, "spawn_subagents must not reference run_fanout (spawn-free)"
    assert "execution_engine" not in body, "the tool module must not import the kernel"


def test_tool_spawn_subagents_constant_present():
    import app.agents.tools.runner_tools as rt

    assert getattr(rt, "TOOL_SPAWN_SUBAGENTS", None) == "spawn_subagents"

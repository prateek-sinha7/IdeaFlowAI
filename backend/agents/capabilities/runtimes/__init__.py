"""agents/capabilities/runtimes/ — the AgentRuntimeAdapter capability package (08-05 / F5 / §30).

Importing this package imports ``langchain_deepagents``, firing its
``@register("runtime", "langchain_deepagents")`` decorator so ``discover()`` (which
best-effort imports this package) binds the runtime adapter into the registry.

F5 lift (D-08 / INV-13): the factory's hardcoded ``DeepAgentRunner`` build becomes a
registry-resolved ``AgentRuntimeAdapter``. The ``langchain_deepagents`` adapter
SELECTS/WRAPS ``DeepAgentRunner`` — it never re-implements the agent loop and never
itself imports ``app.*`` or calls ``create_deep_agent`` (the canonical
``from deepagents import create_deep_agent`` stays inside the allow-listed
``app/agents/deep_agent_runner.py`` per ``test_banned_patterns.py``; the runtime
capability reaches the runner construction through a factory-supplied build seam,
keeping the kernel→app import direction one-way — import-linter:
``agents.capabilities`` ↛ ``app``).

Future runtimes (``claude_code_cli`` / ``custom_runner``) slot in by registering the
same port with NO kernel edit.
"""

from __future__ import annotations

from agents.capabilities.runtimes import (  # noqa: F401 — import side effect: @register
    langchain_deepagents,
)

__all__ = ["langchain_deepagents"]

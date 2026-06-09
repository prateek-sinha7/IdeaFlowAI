"""agents/capabilities/runtimes/langchain_deepagents.py — the F5 runtime adapter (08-05 / §30).

Lifts the factory's hardcoded ``DeepAgentRunner`` construction (F5) into a registered
``AgentRuntimeAdapter`` capability. ``create_runner`` resolves this adapter via
``resolve("runtime", <id>)`` (defaulting to ``langchain_deepagents``) instead of
building the runner inline — so a future ``claude_code_cli`` / ``custom_runner`` slots
in by registering the same port with NO kernel edit.

INV-13 (deepagents-only) — WRAP, NEVER REPLACE
----------------------------------------------
The canonical ``from deepagents import create_deep_agent`` call lives ONLY inside the
allow-listed ``app/agents/deep_agent_runner.py`` (``DeepAgentRunner.__init__``;
``test_banned_patterns.py`` ``_ALLOWED_CREATE_DEEP_AGENT``). This adapter does NOT call
``create_deep_agent`` and does NOT import ``app.*`` — it SELECTS/WRAPS the runner by
invoking a factory-supplied ``build`` callable that performs the actual (app-side)
``DeepAgentRunner(...)`` construction. The composition root (``agents/factory.py``, which
IS permitted to import ``app``) does the spec-load / prompt-compose / tool-resolve /
sandbox-build and passes the bound construction down as the ``build`` seam in ``ctx``.

This keeps two invariants simultaneously:
  * INV-13 / F5 CHECK gate — ``create_deep_agent`` reached only inside the allow-listed
    adapter module; the banned-pattern ratchet stays green (allow-list unchanged).
  * Hexagonal / import-linter — the kernel-side runtime capability never imports
    ``app.*`` (``agents.capabilities`` ↛ ``app``); it reaches runner construction
    through the handle/seam.

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing —
NO ``app.*`` import, NO ``create_deep_agent`` import/call, NO kernel-engine import.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register


@register("runtime", "langchain_deepagents", user_allowed=False)
class LangChainDeepAgentsRuntime:
    """The default ``AgentRuntimeAdapter`` — wraps ``DeepAgentRunner`` (INV-13).

    ``user_allowed=False``: the runtime is a privileged capability (it selects the
    agent execution engine) and stays off the user palette (D-02). Satisfies the
    ``AgentRuntimeAdapter`` port (``create(agent_id, ctx) -> runner``).

    The adapter is intentionally THIN: the composition root supplies a fully-bound
    ``build`` callable on ``ctx`` (a ``RuntimeBuildContext``) that constructs the
    app-side ``DeepAgentRunner`` from the pre-composed prompt / resolved tools /
    sandbox. The adapter SELECTS this runtime by invoking that seam — it never
    re-implements the loop nor reaches ``app``/``create_deep_agent`` itself.
    """

    name = "langchain_deepagents"

    def create(self, agent_id: str, ctx: Any) -> Any:
        """Return the runner for ``agent_id`` by invoking the factory build seam.

        ``ctx`` is a ``RuntimeBuildContext`` carrying the bound ``build`` callable
        (closing over the composition-root work the factory already did). The adapter
        merely SELECTS this runtime and delegates construction — wrap, never replace.
        """
        build = getattr(ctx, "build", None)
        if build is None or not callable(build):
            raise RuntimeError(
                "langchain_deepagents adapter: ctx is missing the factory 'build' "
                "seam — the runtime capability never constructs the runner itself "
                "(it must not import app/create_deep_agent); the composition root "
                "(agents.factory) supplies the bound build callable."
            )
        return build()

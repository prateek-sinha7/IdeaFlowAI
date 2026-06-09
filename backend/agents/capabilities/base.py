"""agents/capabilities/base.py — capability Protocol ports (MAN-03 / §6).

The hexagonal port boundary (Ports & Adapters): the kernel depends ONLY on
these ``typing.Protocol`` ports; concrete capability implementations (Phase 7)
self-register and satisfy them structurally. Adding a capability = add a module
that implements a port + register it — no kernel edit (§32).

Scope (Phase 4 / 1A):
  - Interface-only. No bodies, no implementations (impls are Phase 7).
  - This module imports ONLY stdlib ``typing``. It must not import the kernel
    engine package or the web/API layer — the import-linter contract keeps the
    kernel->ports direction one-way (§32 / SAFE-05).

The runtime objects a port method receives/returns (``Step``, ``ExecutionContext``,
``Task``, ``Issue``, deliverable refs, gate outcomes) are the typed dataclasses
defined in ``agents/workflows/plan.py`` (authored in 04-02). To keep this port
module free of an inbound dependency on the not-yet-authored plan types, the
signatures below type those positions as ``Any``; the concrete types are bound
when ``plan.py`` lands and the impls (Phase 7) reference them directly.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class TaskParser(Protocol):
    """Adapter that parses raw planner text into canonical ``Task`` objects (Q11).

    Variants: ``heading_tasks`` | ``json_tasks`` | ``bracket_p`` (names only in
    Phase 4; impls Phase 7).
    """

    name: str

    def parse(self, text: str) -> list[Any]:
        """Parse ``text`` into a list of canonical ``Task`` objects."""
        ...


@runtime_checkable
class ExecutionStrategy(Protocol):
    """"How a step runs" — single_shot | task_loop | fanout_batch | wave_scheduler (Q8)."""

    name: str

    def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        """Drive one step, yielding the engine's event dicts."""
        ...


@runtime_checkable
class Validator(Protocol):
    """A deliverable validator producing ``Issue`` records (Q21)."""

    name: str

    async def validate(self, target: Any) -> list[Any]:
        """Validate a deliverable context, returning a list of ``Issue``."""
        ...


@runtime_checkable
class DeliverableResolver(Protocol):
    """Resolves a run's final deliverable from the execution context (Q26)."""

    name: str

    def resolve(self, ctx: Any) -> Any:
        """Return the deliverable as a string or an ``ArtifactRef``."""
        ...


@runtime_checkable
class ContextProvider(Protocol):
    """Loads named context blocks injected into agents (Q28)."""

    name: str

    async def load(self, ctx: Any) -> dict[str, str]:
        """Return a mapping of block-name -> content."""
        ...


@runtime_checkable
class PostStep(Protocol):
    """A declared after-step behavior run once the step's agent has finished (§9 / CR-06).

    The kernel resolves it by name from ``Step.post_step`` and invokes ``run(step,
    ctx)`` after the step's execution strategy completes — replacing the
    kernel-resident prototype-revision validation block. Phase 8 makes
    Validator/GateHandler formal; this phase preserves the BEHAVIOR behind a
    declared, registered capability.
    """

    name: str

    async def run(self, step: Any, ctx: Any) -> None:
        """Run the post-step behavior (no events; side effects only)."""
        ...


@runtime_checkable
class GateHandler(Protocol):
    """A step gate — human | validation | approval | security (§9)."""

    name: str  # capability name, e.g. "human" | "validation" | "approval" | "security"

    async def evaluate(self, step: Any, ctx: Any) -> Any:
        """Evaluate the gate, returning a gate outcome (pass | block | wait_human)."""
        ...


# ---------------------------------------------------------------------------
# Phase 8 ports (§6 / §30) — the new tool/skill/hook/runtime kinds + the F1–F5
# factory-lift abstractions. Interface-only, same one-method-Protocol idiom: a
# ``name: str`` attribute, ONE declared method, a ``...`` body, runtime objects
# typed ``Any`` (stdlib ``typing`` only — the import-linter keeps kernel->ports
# one-way; no kernel/app import). Impls self-register in 08-02..08-07.
# ---------------------------------------------------------------------------


@runtime_checkable
class PromptAssemblyPolicy(Protocol):
    """Composes a named-block mapping into the final system prompt str (F1 / §6).

    Replaces the factory's hardcoded ``blocks.append`` order
    (``injects -> guardrails -> skills -> hooks -> constitution -> prompt_body``);
    the default order constant lives with the impl (08-05).
    """

    name: str

    def assemble(self, blocks: dict[str, Any], ctx: Any) -> str:
        """Transform a named-block mapping into the composed prompt string."""
        ...


@runtime_checkable
class AgentRuntimeAdapter(Protocol):
    """Selects/wraps the per-agent runner (F5 / AGENTRT-01..06 / §30).

    The ``langchain_deepagents`` impl WRAPS ``DeepAgentRunner`` /
    ``create_deep_agent`` — never re-implements the agent loop (INV-13).
    """

    name: str

    def create(self, agent_id: str, ctx: Any) -> Any:
        """Return the runner for ``agent_id`` (wrapping the selected runtime)."""
        ...


@runtime_checkable
class HookHandler(Protocol):
    """An executable lifecycle/tool-call hook (HOOK-01..04 / §30 / N12).

    Bound to one or more lifecycle ``events`` (``before/after_run·step·tool_call·
    write``, ``post_task``, ``pre/post_commit``, ``on_validation``, ``*``);
    ``handle`` returns an outcome ``continue | warn | block`` (a blocking outcome
    halts the offending action). ``required_permission`` is the permission the
    hook needs to fire (e.g. ``read_files`` for a scanner, ``exec`` for a command
    hook), or ``None`` for a non-privileged hook.
    """

    name: str
    events: list[str]
    required_permission: str | None

    async def handle(self, event: Any, ctx: Any) -> Any:
        """Handle a fired ``event``, returning a hook outcome (continue|warn|block)."""
        ...


@runtime_checkable
class ToolProvider(Protocol):
    """Provides the tool set bound to an agent (F2 / TOOLPERM-01..03 / §8).

    Replaces the factory's closed ``_build_runner_tools`` switch: returns the
    ``(custom_tools, exclude_builtin)`` tuple for one granted tool set.
    """

    name: str

    def provide(self, spec: Any, ctx: Any) -> Any:
        """Return the ``(custom_tools, exclude_builtin)`` tuple for a tool set."""
        ...


@runtime_checkable
class SkillProvider(Protocol):
    """Provides versioned skill blocks injected into a prompt (F3 / SKILL-01 / §30).

    Variants: ``ui`` | ``disk`` | ``template`` | ``repo``; each returned item
    carries a ``version`` notion so a stale skill block is detectable.
    """

    name: str

    async def provide(self, ctx: Any) -> list[Any]:
        """Return the versioned skill blocks for this provider."""
        ...


@runtime_checkable
class HookProvider(Protocol):
    """Provides hook descriptors for an agent run (F3 / HOOK-01 / §30).

    Returns hook descriptors including the ``behavioral`` non-executable
    sub-type block (the legacy prompt-only ``## Active Behavioral Hooks`` render).
    """

    name: str

    async def provide(self, ctx: Any) -> list[Any]:
        """Return the hook descriptors (incl. the ``behavioral`` sub-type)."""
        ...

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
class GateHandler(Protocol):
    """A step gate — human | validation | approval | security (§9)."""

    kind: str

    async def evaluate(self, step: Any, ctx: Any) -> Any:
        """Evaluate the gate, returning a gate outcome (pass | block | wait_human)."""
        ...

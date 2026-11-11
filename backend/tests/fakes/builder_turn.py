"""In-memory ``TurnPort`` for the workflow builder's agent-layer tests.

``FakeTurnPort`` implements :class:`app.agents.workflow_builder.ports.TurnPort`
without a Session_Store or a stream. It records what the middleware and tools do
to the turn: published events, stage signals, the stop reason, finished tool
calls and workflow writes. Limits are generous by default so a test sees no
limit behaviour unless it passes its own.

Nothing here asserts.
"""

from __future__ import annotations

from typing import Any

from app.agents.workflow_builder.events import BuilderEvent, StopReason
from app.agents.workflow_builder.ports import (
    AcceptedDraft,
    FinishedToolCall,
    TurnLimits,
)
from app.agents.workflow_builder.stages import Signal

__all__ = ["FakeTurnPort", "generous_limits"]


def generous_limits() -> TurnLimits:
    """Return limits that a small test cannot reach."""
    return TurnLimits(
        timeout_seconds=3600,
        max_tool_calls=100_000,
        max_gate_rejections=2,
        warning_fraction=0.8,
    )


class FakeTurnPort:
    """A ``TurnPort`` that records every call.

    Attributes:
        events: Published events, in order.
        signals: Stage signals, in order.
        stop_reasons: Reasons passed to ``stop``, in order.
        finished: Finished tool calls, in order.
        workflow_writes: Paths passed to ``record_workflow_write``.
        accepted: Drafts passed to ``accept_draft``, in order.
    """

    def __init__(
        self,
        *,
        turn_id: str = "turn-1",
        limits: TurnLimits | None = None,
        canvas_state: dict[str, Any] | None = None,
    ) -> None:
        """Create a turn with ``turn_id``, ``limits`` and ``canvas_state``."""
        self._turn_id = turn_id
        self._limits = limits if limits is not None else generous_limits()
        self._tool_calls = 0
        self._gate_rejections = 0
        self._canvas_state = canvas_state
        self._accepted_revision: int | None = None
        self.accepted: list[AcceptedDraft] = []
        self.events: list[BuilderEvent] = []
        self.signals: list[Signal] = []
        self.stop_reasons: list[StopReason] = []
        self.finished: list[FinishedToolCall] = []
        self.workflow_writes: list[str] = []

    @property
    def turn_id(self) -> str:
        """The turn id."""
        return self._turn_id

    @property
    def stopping(self) -> bool:
        """True once ``stop`` has been called."""
        return bool(self.stop_reasons)

    @property
    def canvas_state(self) -> dict[str, Any] | None:
        """The canvas state the turn was created with, if any."""
        return self._canvas_state

    @property
    def limits(self) -> TurnLimits:
        """The turn limits."""
        return self._limits

    @property
    def accepted_revision(self) -> int | None:
        """The revision of the last accepted draft, or ``None``."""
        return self._accepted_revision

    async def publish(self, event: BuilderEvent) -> None:
        """Record ``event``."""
        self.events.append(event)

    async def signal_stage(self, signal: Signal) -> None:
        """Record ``signal``."""
        self.signals.append(signal)

    def stop(self, reason: StopReason) -> None:
        """Record ``reason``."""
        self.stop_reasons.append(reason)

    def count_tool_call(self) -> int:
        """Count one call and return the total."""
        self._tool_calls += 1
        return self._tool_calls

    async def record_tool_call(self, finished: FinishedToolCall) -> None:
        """Record ``finished``."""
        self.finished.append(finished)

    def record_workflow_write(self, path: str) -> None:
        """Record ``path``."""
        self.workflow_writes.append(path)

    def report_gate_rejection(self) -> int:
        """Count one rejection and return the total."""
        self._gate_rejections += 1
        return self._gate_rejections

    async def accept_draft(self, draft: AcceptedDraft) -> int:
        """Record ``draft`` and return the next revision number (1, 2, ...)."""
        self.accepted.append(draft)
        self._accepted_revision = len(self.accepted)
        return self._accepted_revision

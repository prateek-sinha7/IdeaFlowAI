"""Ports through which the Builder_Agent reaches the platform.

Two protocols and their value types live here so the agent layer (the observer
middleware, the script tool and ``propose_draft``) never imports ``app.api``
(Req 48.5, 48.6, design sections 3.5.1 and 3.1.4):

* :class:`GatePort`, the Server_Gate. The API layer supplies the adapter
  (``app.api.workflow_builder.gate.ServerGate``). It reuses the save check and
  therefore ``_compile_check_manifest``, so the engine import stays where it
  already is and ``app.*`` gains no second place that imports it.
* :class:`TurnPort`, the live Turn. The API layer's ``TurnRunner`` implements
  it. Everything a tool or middleware does to the running turn goes through
  this protocol: publishing events, stage signals, stopping, counting and
  recording tool calls, recording writes and gate rejections, accepting a
  draft, and reading the turn's ``canvas_state`` and limits.

Nothing here does I/O. The module holds protocols and plain value types only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from app.agents.workflow_builder.adherence import ToolCall
    from app.agents.workflow_builder.events import (
        BuilderEvent,
        ChangeSummary,
        LaunchNeed,
        StopReason,
        TargetTrust,
        ToolActivity,
    )
    from app.agents.workflow_builder.stages import Signal

__all__ = [
    "AcceptedDraft",
    "FinishedToolCall",
    "GateIssue",
    "GatePort",
    "GateResult",
    "GateRule",
    "TurnLimits",
    "TurnPort",
]

GateRule = Literal[
    "save_check",
    "agent_allow_list",
    "model_entitlement",
    "step_model",
    "effort",
    "forbidden_feature",
    "irreversible_gate",
    "fact_propagation",
    "placeholder",
]


# --- Server_Gate (design 3.5.1) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class GateIssue:
    """One reason the Server_Gate refused a draft.

    Attributes:
        rule: Which check found it.
        path: Where in the manifest, for example ``steps[2].tools.exec``. Empty
            when the issue concerns the manifest as a whole.
        message: What is wrong, in words the agent can act on. It holds no
            user prompt text.
    """

    rule: GateRule
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class GateResult:
    """The Server_Gate's verdict on one draft.

    Attributes:
        accepted: True when the draft passed every check.
        trust: The trust the draft was accepted at. ``None`` when rejected.
        issues: Every issue found. Empty when accepted.
    """

    accepted: bool
    trust: TargetTrust | None
    issues: tuple[GateIssue, ...]


class GatePort(Protocol):
    """The Server_Gate as the agent layer sees it."""

    async def check(
        self, manifest: dict[str, Any], *, requested_trust: TargetTrust
    ) -> GateResult:
        """Check ``manifest`` the way Save does, plus the Builder_Rules.

        Args:
            manifest: The parsed workflow manifest.
            requested_trust: The trust the agent asked for. The gate may accept
                at a lower trust, never at a higher one.
        """
        ...

    async def dry_run(
        self, manifest_path: Path, *, requested_trust: TargetTrust
    ) -> GateResult:
        """Read the file at ``manifest_path`` and run the same check.

        Stores nothing, sends no event and never counts as a rejection
        (Req 36.2).
        """
        ...


# --- Live turn (design 3.1.4) -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TurnLimits:
    """The limits of one Turn, read from settings when the turn starts.

    Attributes:
        timeout_seconds: Wall-clock cap (``BUILDER_TURN_TIMEOUT_SECONDS``).
        max_tool_calls: Tool-call cap; the call after it is refused.
        max_gate_rejections: Rejections after which the turn stops.
        warning_fraction: Share of a limit at which ``limit_warning`` is sent.
        token_budget: Token budget of the turn, or ``None`` when unenforced.
    """

    timeout_seconds: int
    max_tool_calls: int
    max_gate_rejections: int
    warning_fraction: float
    token_budget: int | None = None


@dataclass(frozen=True, slots=True)
class FinishedToolCall:
    """A finished tool call, for the stored tool row and the adherence record.

    Attributes:
        activity: The call as the transcript shows it.
        call: The same call in the form the adherence record reads.
        result: The tool result text. The port cuts it before storing it.
    """

    activity: ToolActivity
    call: ToolCall
    result: str


@dataclass(frozen=True, slots=True)
class AcceptedDraft:
    """A draft the Server_Gate accepted, to be stored as a revision.

    Attributes:
        manifest: The accepted manifest.
        trust: The trust the gate accepted it at.
        source_file: The ``/workflows/`` path the agent proposed.
        change_summary: What changed against the turn's ``canvas_state``.
        launch_needs: What the user must provide before launching.
    """

    manifest: dict[str, Any]
    trust: TargetTrust
    source_file: str
    change_summary: ChangeSummary
    launch_needs: tuple[LaunchNeed, ...]


class TurnPort(Protocol):
    """The live Turn as the middleware and tools see it.

    Methods that only change in-memory turn state are synchronous. Methods
    that publish an event or store a row are asynchronous.
    """

    @property
    def turn_id(self) -> str:
        """The id of the Turn, equal to its assistant message id."""
        ...

    @property
    def stopping(self) -> bool:
        """True once the turn has a stop reason. A stopping turn applies nothing."""
        ...

    @property
    def canvas_state(self) -> dict[str, Any] | None:
        """The Canvas state the user's message was sent with, if any."""
        ...

    @property
    def limits(self) -> TurnLimits:
        """The limits that apply to this turn."""
        ...

    @property
    def accepted_revision(self) -> int | None:
        """The revision number this turn already accepted, or ``None``."""
        ...

    async def publish(self, event: BuilderEvent) -> None:
        """Publish ``event`` on the Session_Stream.

        The port assigns ``turn_id`` and ``seq`` of a turn-scoped event before
        it publishes, so all subscribers see one order (Req 40.5). A caller
        passes any valid placeholder for those two fields.
        """
        ...

    async def signal_stage(self, signal: Signal) -> None:
        """Feed ``signal`` to ``derive_stage`` and publish a stage event if it changes."""
        ...

    def stop(self, reason: StopReason) -> None:
        """Stop the turn. The first reason wins; later calls change nothing."""
        ...

    def count_tool_call(self) -> int:
        """Count one tool call and return how many the turn has made so far."""
        ...

    async def record_tool_call(self, finished: FinishedToolCall) -> None:
        """Store one finished tool call and keep it for the turn's adherence record."""
        ...

    def record_workflow_write(self, path: str) -> None:
        """Remember a successful write of a ``/workflows/*.workflow.json`` file."""
        ...

    def report_gate_rejection(self) -> int:
        """Count one gate rejection and return how many the turn has had so far."""
        ...

    async def accept_draft(self, draft: AcceptedDraft) -> int:
        """Store ``draft`` as an accepted revision and return its revision number."""
        ...

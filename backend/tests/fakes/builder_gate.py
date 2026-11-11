"""In-memory ``GatePort`` for the workflow builder's agent-layer tests.

``FakeGate`` implements :class:`app.agents.workflow_builder.ports.GatePort`
without the save check or the engine. Verdicts are scripted per method: each call
to ``check`` or ``dry_run`` takes the next queued item. An item is a
:class:`GateResult` to return, or an exception to raise (the runner must survive
a failing gate). When the queue is empty the gate accepts at the requested trust.
Every call is recorded in ``check_calls`` and ``dry_run_calls``.

Nothing here asserts and nothing reads the manifest file.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.workflow_builder.events import TargetTrust
from app.agents.workflow_builder.ports import GateIssue, GateResult, GateRule

__all__ = [
    "CheckCall",
    "DryRunCall",
    "FakeGate",
    "accepted_result",
    "rejected_result",
]

Verdict = GateResult | BaseException


@dataclass(frozen=True)
class CheckCall:
    """One recorded ``check`` call."""

    manifest: dict[str, Any]
    requested_trust: TargetTrust


@dataclass(frozen=True)
class DryRunCall:
    """One recorded ``dry_run`` call."""

    manifest_path: Path
    requested_trust: TargetTrust


def accepted_result(trust: TargetTrust = "user") -> GateResult:
    """Return an accepted verdict at ``trust``."""
    return GateResult(True, trust, ())


def rejected_result(
    message: str = "rejected by the fake gate",
    *,
    rule: GateRule = "save_check",
    path: str = "",
) -> GateResult:
    """Return a rejected verdict with one issue."""
    return GateResult(False, None, (GateIssue(rule, path, message),))


class FakeGate:
    """A ``GatePort`` with scripted verdicts and recorded calls.

    Attributes:
        check_calls: Every ``check`` call, in order.
        dry_run_calls: Every ``dry_run`` call, in order.
    """

    def __init__(
        self,
        *,
        check: Verdict | list[Verdict] | None = None,
        dry_run: Verdict | list[Verdict] | None = None,
    ) -> None:
        """Create a gate.

        Args:
            check: Verdict, or ordered verdicts, for ``check`` calls.
            dry_run: Verdict, or ordered verdicts, for ``dry_run`` calls.
        """
        self._check: deque[Verdict] = deque(_as_list(check))
        self._dry_run: deque[Verdict] = deque(_as_list(dry_run))
        self.check_calls: list[CheckCall] = []
        self.dry_run_calls: list[DryRunCall] = []

    async def check(
        self, manifest: dict[str, Any], *, requested_trust: TargetTrust
    ) -> GateResult:
        """Record the call and return or raise the next scripted verdict."""
        self.check_calls.append(CheckCall(manifest, requested_trust))
        return _next(self._check, requested_trust)

    async def dry_run(
        self, manifest_path: Path, *, requested_trust: TargetTrust
    ) -> GateResult:
        """Record the call and return or raise the next scripted verdict."""
        self.dry_run_calls.append(DryRunCall(manifest_path, requested_trust))
        return _next(self._dry_run, requested_trust)


def _as_list(verdicts: Verdict | list[Verdict] | None) -> list[Verdict]:
    if verdicts is None:
        return []
    return list(verdicts) if isinstance(verdicts, list) else [verdicts]


def _next(queue: deque[Verdict], requested_trust: TargetTrust) -> GateResult:
    if not queue:
        return accepted_result(requested_trust)
    verdict = queue.popleft()
    if isinstance(verdict, BaseException):
        raise verdict
    return verdict

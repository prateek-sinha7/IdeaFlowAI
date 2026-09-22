"""Stand-ins for the validator seam: static/render results, a deliverable target, runner.

Extracted from ``tests/unit/agents/test_validators.py`` in Batch 6, when the eight
database-backed validator tests moved to
``tests/integration/agents/test_validators_db.py``. Both halves need the same
stand-ins, and duplicating them would let the two files drift apart silently.

Nothing here touches a database or a network: ``FakeValidationRunner`` writes through
whatever store it is handed, so the unit half can pass a fake and the integration half
a real ``ScopedStore``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StaticCheckResultStub:
    """What ``static_check`` returns: ok + fatal issues + advisory warnings."""

    ok: bool
    issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class NavResultStub:
    """One navigation probe from a render: the href and whether it resolved."""

    href: str
    ok: bool


@dataclass
class RenderResultStub:
    """What ``render_check`` returns, including ``available`` (browser present)."""

    ok: bool = True
    available: bool = True
    console_errors: list = field(default_factory=list)
    page_errors: list = field(default_factory=list)
    nav_results: list = field(default_factory=list)


class FakeValidationRunner:
    """Minimal KernelServices stand-in: static/render checks + the validation writer.

    Records every ``record_validation_result`` call on ``records`` AND forwards it to
    the store it was constructed with, so an integration test can hand in a real
    ``ScopedStore`` and assert on the persisted row while a unit test can hand in a
    fake and assert on the recorded call.
    """

    def __init__(self, *, static_result, render_result, store, run_id):
        self._static = static_result
        self._render = render_result
        self._store = store
        self.run_id = run_id
        self.records: list[dict] = []

    def static_check(self, path):
        return self._static

    async def render_check(self, path):
        return self._render

    async def record_validation_result(
        self, step, validator, *, severity=None, attempt=0, issues=None
    ):
        self.records.append(
            {
                "step": step,
                "validator": validator,
                "severity": severity,
                "attempt": attempt,
                "issues": issues,
            }
        )
        return await self._store.record_validation_result(
            self.run_id,
            step,
            validator,
            severity=severity,
            attempt=attempt,
            issues=issues,
        )


@dataclass
class DeliverableTargetStub:
    """DeliverableContext stand-in (the kernel builds the real one)."""

    name: str
    runner: object
    path: object = None
    step: str = "prototype-build"
    task_meta: dict = field(default_factory=dict)
    content: str = ""


# Legacy private aliases — the call sites predate the extraction.
_StaticResult = StaticCheckResultStub
_NavResult = NavResultStub
_RenderResult = RenderResultStub
_FakeRunner = FakeValidationRunner
_Target = DeliverableTargetStub

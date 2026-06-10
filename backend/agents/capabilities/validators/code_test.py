"""agents/capabilities/validators/code_test.py — the code_test validator (EXEC-02).

A kernel-side, pure-stdlib registered ``Validator`` (modeled VERBATIM on
``spec_plan_coverage.py``) that runs the run's test suite via
``pytest -p no:cacheprovider`` — reaching exec ONLY through the runner/workspace
handle (``target.runner.workspace.exec_command(argv)``). It NEVER imports ``app.*``
and NEVER spawns a child process directly: the ``Workspace`` is the SINGLE owner of
the process surface so the policy enforces allow/deny and the recorder audits.

``-p no:cacheprovider`` (RESEARCH Pitfall 2) prevents pytest-inside-pytest cache
recursion; the run is bounded by the 10-01 policy caps (cpu=60s, wall=120s) so a
runaway is killed. The hardened ``exec_command`` returns only stdout — pytest's
short summary (``N failed`` / ``N passed``) lands on stdout, so a failure is
detectable through the handle.

VALIDATOR-DENY (T-10-04-02): exec ungranted → an explicit refusal ``Issue``, ZERO
spawns, never a silent pass. A ``PermissionError`` is caught + mapped (it never
escapes). A failing/erroring run becomes a P0 issue. Severity maps through the
SINGLE imported ``map_severity`` (VALID-03). Each run writes a ``validation_results``
row via the handle (best-effort).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any

from agents.capabilities.registry import register
from agents.capabilities.validators.severity import map_severity  # single source (08-01)
from agents.capabilities.validators._exec_support import (
    exec_granted,
    workspace_of,
)


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = "code_test"


_FAILED_RE = re.compile(r"\b(\d+)\s+(failed|error|errors)\b")
_FAILED_LINE_RE = re.compile(r"^FAILED\s+\S+", re.MULTILINE)


@register("validator", "code_test", user_allowed=True)
class CodeTestValidator:
    """Run the run's tests via ``pytest -p no:cacheprovider`` (``name='code_test'``).

    Reaches exec ONLY through the ``Workspace`` handle. Refuses explicitly (no
    spawn) when exec is ungranted (VALIDATOR-DENY).
    """

    name = "code_test"

    async def validate(self, target: Any) -> list[Issue]:
        ws = workspace_of(getattr(target, "runner", None))
        if ws is None or not exec_granted(ws):
            issue = Issue(
                severity="P1",
                message="code_test skipped: exec not granted (no workspace / policy.exec OFF)",
            )
            await _record(target, "code_test", [issue])
            return [issue]

        issues: list[Issue] = []
        try:
            # Run from the workspace root (cwd is the run root). "." keeps pytest
            # rootdir at the tiny fixture; -p no:cacheprovider avoids cache recursion.
            out = ws.exec_command(["pytest", "-p", "no:cacheprovider", "-q", "."]) or ""
            issues = _parse(out)
        except PermissionError as exc:  # never escapes (VALIDATOR-DENY safety net)
            issues = [Issue(severity="P1", message=f"code_test exec denied: {exc}")]
        except subprocess.TimeoutExpired:
            issues = [Issue(severity="P1", message="code_test timed out (policy wall-clock cap)")]

        await _record(target, "code_test", issues)
        return issues


def _parse(out: str) -> list[Issue]:
    """Parse pytest's STDOUT short summary into ``Issue``s (P0 on any failure/error)."""
    issues: list[Issue] = []
    failed_lines = _FAILED_LINE_RE.findall(out)
    summary = _FAILED_RE.search(out)
    if failed_lines:
        for line in failed_lines:
            issues.append(Issue(severity="P0", message=line.strip()[:512]))
    elif summary:
        issues.append(Issue(severity="P0", message=f"pytest reported failures: {summary.group(0)}"))
    return issues


_SEVERITY_ORDER = ("P0", "P1", "P2", "P3")


def _worst_label(issues: list[Issue]) -> str | None:
    for sev in _SEVERITY_ORDER:
        if any(i.severity == sev for i in issues):
            return map_severity(sev)
    return None


async def _record(target: Any, validator: str, issues: list[Issue]) -> None:
    """Write a ``validation_results`` row via the handle (best-effort, D-10)."""
    runner = getattr(target, "runner", None)
    if runner is None:
        return
    record = getattr(runner, "record_validation_result", None)
    if record is None:
        return
    severity = _worst_label(issues)
    step = getattr(target, "step", "") or ""
    attempt = int((getattr(target, "task_meta", None) or {}).get("attempt", 0))
    payload = [{"severity": i.severity, "message": i.message} for i in issues]
    await record(step, validator, severity=severity, attempt=attempt, issues=payload)

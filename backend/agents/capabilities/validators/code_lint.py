"""agents/capabilities/validators/code_lint.py — the code_lint validator (EXEC-02).

A kernel-side, pure-stdlib registered ``Validator`` (modeled VERBATIM on
``spec_plan_coverage.py``) that lints the run's Python files via ``ruff check`` —
reaching exec ONLY through the runner/workspace handle
(``target.runner.workspace.exec_command(argv)``). It NEVER imports ``app.*`` and
NEVER spawns a child process directly: the ``Workspace`` is the SINGLE owner of the
process surface so the policy enforces allow/deny and the recorder audits.

``ruff check`` prints its findings to stdout (the stream ``exec_command`` returns),
one ``path:line:col: CODE message`` per violation. Each finding becomes an ``Issue``
whose internal severity (P0 for a syntax error, P2 for an ordinary lint finding) is
mapped to a UI label through the SINGLE imported ``map_severity`` (VALID-03 single
source) — NEVER a local ladder.

VALIDATOR-DENY (T-10-04-02): workspace absent OR exec ungranted → an explicit
refusal ``Issue``, ZERO spawns, never a silent pass. A ``PermissionError`` is caught
+ mapped (it never escapes). Each run writes a ``validation_results`` row via the
handle (best-effort).
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
    target_py_files,
    workspace_of,
)


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = "code_lint"


# A ruff finding line: ``path:line:col: CODE message`` (CODE may be a rule like
# ``F401`` or ``SyntaxError``). The ``-q`` flag suppresses the summary so only the
# finding lines remain.
_FINDING_RE = re.compile(r"^(?P<path>[^:\s][^:]*):(?P<line>\d+):(?P<col>\d+):\s+(?P<rest>.+)$")


@register(
    "validator",
    "code_lint",
    user_allowed=True,
    description="Run ruff lint over the generated code via the exec handle and surface findings as issues.",
    config_schema={
        "type": "object",
        "properties": {
            "timeout_s": {
                "type": "integer",
                "description": "Wall-clock cap for the lint run, in seconds.",
                "minimum": 1,
            },
        },
    },
)
class CodeLintValidator:
    """Lint the run's Python files via ``ruff check`` (``name='code_lint'``).

    Reaches exec ONLY through the ``Workspace`` handle. Refuses explicitly (no
    spawn) when exec is ungranted (VALIDATOR-DENY).
    """

    name = "code_lint"

    async def validate(self, target: Any) -> list[Issue]:
        ws = workspace_of(getattr(target, "runner", None))
        if ws is None or not exec_granted(ws):
            issue = Issue(
                severity="P1",
                message="code_lint skipped: exec not granted (no workspace / policy.exec OFF)",
            )
            await _record(target, "code_lint", [issue])
            return [issue]

        py_files = target_py_files(target)
        if not py_files:
            issues: list[Issue] = []
            await _record(target, "code_lint", issues)
            return issues

        issues = []
        try:
            # --output-format=concise + -q → one finding per line, no summary noise.
            out = ws.exec_command(
                ["ruff", "check", "--output-format=concise", "-q", *py_files]
            ) or ""
            issues = _parse(out)
        except PermissionError as exc:  # never escapes (VALIDATOR-DENY safety net)
            issues = [Issue(severity="P1", message=f"code_lint exec denied: {exc}")]
        except subprocess.TimeoutExpired:
            issues = [Issue(severity="P1", message="code_lint timed out (policy wall-clock cap)")]

        await _record(target, "code_lint", issues)
        return issues


def _parse(out: str) -> list[Issue]:
    """Parse ruff's STDOUT findings into ``Issue``s (P0 for syntax, else P2)."""
    issues: list[Issue] = []
    for raw in out.splitlines():
        m = _FINDING_RE.match(raw.strip())
        if not m:
            continue
        rest = m.group("rest")
        # A syntax error is a P0 (compile-fatal); an ordinary lint finding is a P2.
        severity = "P0" if "syntaxerror" in rest.lower() else "P2"
        # Validate the label flows through the single source (raises on a bad ladder).
        _ = map_severity(severity)
        issues.append(
            Issue(
                severity=severity,
                message=f"{m.group('path')}:{m.group('line')}:{m.group('col')}: {rest}"[:512],
            )
        )
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

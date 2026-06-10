"""agents/capabilities/validators/code_compile.py — the code_compile validator (EXEC-02).

A kernel-side, pure-stdlib registered ``Validator`` (modeled VERBATIM on
``spec_plan_coverage.py``) that compiles the run's Python files via ``py_compile`` —
reaching exec ONLY through the runner/workspace handle
(``target.runner.workspace.exec_command(argv)`` — the ``repo_diff._workspace``
reach). It NEVER imports ``app.*`` and NEVER spawns a child process directly: the
``Workspace`` is the SINGLE owner of the process surface so the policy enforces
allow/deny and the recorder audits every outcome (bypass-proof, T-10-04-01).

The hardened ``exec_command`` returns only the child's stdout (stderr + exit code
are audited, not returned — 10-01). ``py_compile -m`` writes its SyntaxError to
stderr, so this validator drives an inline ``python -c`` compile driver that prints
its verdict to STDOUT (``COMPILE_OK`` / ``COMPILE_FAIL <file>: …``) — keeping the
failure detectable through the handle without changing the exec_command contract.

VALIDATOR-DENY (T-10-04-02): workspace absent OR exec ungranted → an explicit
refusal ``Issue`` naming the missing exec grant, ZERO spawns, never a silent pass.
A ``PermissionError`` from the handle is caught + mapped (it never escapes). A
compile failure becomes a P0 issue naming the offending file. Severity maps through
the SINGLE imported ``map_severity`` (VALID-03 single source). Each run writes a
``validation_results`` row via the handle (best-effort).
"""

from __future__ import annotations

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
    validator: str = "code_compile"


# An inline compile driver run via the allow-listed ``python`` interpreter: it
# compiles each argv-supplied file with ``py_compile.compile(doraise=True)`` and
# prints its verdict to STDOUT (the only stream exec_command returns) so a failure
# is detectable through the handle. Pure stdlib; no file write-back.
_DRIVER = (
    "import py_compile,sys\n"
    "bad=[]\n"
    "for f in sys.argv[1:]:\n"
    "    try:\n"
    "        py_compile.compile(f, doraise=True)\n"
    "    except py_compile.PyCompileError as e:\n"
    "        bad.append((f, str(e).strip().splitlines()[-1] if str(e).strip() else 'SyntaxError'))\n"
    "    except Exception as e:\n"
    "        bad.append((f, type(e).__name__ + ': ' + str(e)))\n"
    "if bad:\n"
    "    for f,msg in bad:\n"
    "        print('COMPILE_FAIL ' + f + ': ' + msg)\n"
    "else:\n"
    "    print('COMPILE_OK')\n"
)


@register("validator", "code_compile", user_allowed=True)
class CodeCompileValidator:
    """Compile the run's Python files via ``py_compile`` (``name='code_compile'``).

    Reaches exec ONLY through the ``Workspace`` handle. Refuses explicitly (no
    spawn) when exec is ungranted (VALIDATOR-DENY).
    """

    name = "code_compile"

    async def validate(self, target: Any) -> list[Issue]:
        ws = workspace_of(getattr(target, "runner", None))
        if ws is None or not exec_granted(ws):
            issue = Issue(
                severity="P1",
                message="code_compile skipped: exec not granted (no workspace / policy.exec OFF)",
            )
            await _record(target, "code_compile", [issue])
            return [issue]

        py_files = target_py_files(target)
        if not py_files:
            issues: list[Issue] = []
            await _record(target, "code_compile", issues)
            return issues

        issues = []
        try:
            out = ws.exec_command(["python3", "-c", _DRIVER, *py_files]) or ""
            issues = _parse(out)
        except PermissionError as exc:  # never escapes (VALIDATOR-DENY safety net)
            issues = [Issue(severity="P1", message=f"code_compile exec denied: {exc}")]
        except subprocess.TimeoutExpired:
            issues = [Issue(severity="P1", message="code_compile timed out (policy wall-clock cap)")]

        await _record(target, "code_compile", issues)
        return issues


def _parse(out: str) -> list[Issue]:
    """Parse the driver's STDOUT verdict into ``Issue``s (P0 per failing file)."""
    issues: list[Issue] = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("COMPILE_FAIL "):
            issues.append(Issue(severity="P0", message=line[len("COMPILE_FAIL ") :].strip()))
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

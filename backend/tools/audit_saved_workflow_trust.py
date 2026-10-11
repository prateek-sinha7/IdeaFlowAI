"""Read-only audit: which SAVED workflows break under ADR-0054's saved-trust posture?

ADR-0039 compiled saved rows (``workflows.source = 'user'`` — Composer workflows
and built-in step overrides) as fully trusted, so a saved step could grant
``tools.exec`` / ``network`` / ``secrets``, declare the ``security`` / ``approval``
gates, or bind the powerful ``filesystem`` / ``postgres`` MCP servers. ADR-0054
takes those away from saved rows. Any row that relies on them will start failing
at launch (the compiler raises), and any that exist are worth a human look —
they are either a legitimate use nobody documented or an attempted escalation.

For every saved row this reports:

  * ``flags``  — host-reaching declarations found by a plain scan of the stored
                 manifest (independent of the compiler, so it still reports on a
                 row the compiler cannot even parse);
  * ``compile``— ``ok`` or the compiler's rejection when the row is compiled the
                 way the launch path compiles it (``trust="db"``).

It prints row ids, owner ids and reasons ONLY — never prompts or other step
content (user data; LOG_LEVEL_APP discipline). It never writes: the session is
rolled back and closed, and no row is modified.

Usage (from ``backend/``, against the DB in ``DATABASE_URL``)::

    uv run python -m tools.audit_saved_workflow_trust
    uv run python -m tools.audit_saved_workflow_trust --only-problems

Exit status: 0 when no row is flagged or rejected, 1 otherwise (so it can gate a
release checklist), 2 on a connection/setup error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field

#: Host-reaching step grants ADR-0054 removes from saved rows.
_HOST_GRANTS: tuple[str, ...] = ("exec", "network", "secrets")
#: Gates that stay engineer-only.
_PRIVILEGED_GATES: frozenset[str] = frozenset({"security", "approval"})
#: MCP servers registered ``powerful=True`` / ``user_allowed=False``.
_POWERFUL_MCP: frozenset[str] = frozenset({"filesystem", "postgres"})


@dataclass
class RowReport:
    """The audit verdict for one saved row (ids + reasons, no user content)."""

    row_id: str
    user_id: str | None
    overrides: str | None
    flags: list[str] = field(default_factory=list)
    compile: str = "ok"

    @property
    def is_problem(self) -> bool:
        """True when the row declares a host-reaching grant or no longer compiles."""
        return bool(self.flags) or self.compile != "ok"


def _walk_steps(steps: object) -> Iterable[dict]:
    """Yield every step dict, descending into ``subagents.steps``."""
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        subagents = step.get("subagents")
        if isinstance(subagents, dict):
            yield from _walk_steps(subagents.get("steps"))


def scan_manifest(manifest: object) -> list[str]:
    """Return the host-reaching declarations in a stored manifest, one per finding."""
    if not isinstance(manifest, dict):
        return []
    findings: list[str] = []
    for step in _walk_steps(manifest.get("steps")):
        where = str(step.get("instance_id") or step.get("agent") or "?")
        tools = step.get("tools") if isinstance(step.get("tools"), dict) else {}
        for grant in _HOST_GRANTS:
            if tools.get(grant):
                findings.append(f"{where}: tools.{grant}")
        for ref in tools.get("mcp") or []:
            server = str(ref).partition(".")[0]
            if server in _POWERFUL_MCP:
                findings.append(f"{where}: tools.mcp {server}")
        for gate in step.get("gates") or []:
            if gate in _PRIVILEGED_GATES:
                findings.append(f"{where}: gates {gate}")
    return findings


def compile_verdict(manifest: object, label: str) -> str:
    """Compile ``manifest`` as the launch path does (trust='db'); ``ok`` or the reason."""
    from agents.execution_engine.engine import _CAPABILITY_REGISTRY, _WORKFLOW_COMPILER
    from agents.workflows.compiler import CompilerError
    from agents.workflows.manifest import (
        ManifestValidationError,
        build_manifest_from_dict,
    )

    if not isinstance(manifest, dict) or not manifest.get("steps"):
        return "ok"  # a selections-only / empty row carries no step grants
    raw = dict(manifest)
    # Same synthesized top-level fallbacks as user_workflows._compile_check_manifest.
    raw.setdefault("id", "saved-workflow-audit")
    raw.setdefault("deliverable", {"strategy": "streamed_text", "name": "output.md"})
    raw.setdefault("planner", "skip")
    raw.setdefault("clarify", {"mode": "skip", "defaults": []})
    raw.setdefault("capabilities", {})
    try:
        parsed = build_manifest_from_dict(raw, label)
        _WORKFLOW_COMPILER.compile(parsed, _CAPABILITY_REGISTRY, trust="db")
    except (ManifestValidationError, CompilerError) as exc:
        return f"rejected: {type(exc).__name__}: {exc}"
    return "ok"


def audit(session) -> list[RowReport]:
    """Audit every ``source='user'`` workflows row (read-only)."""
    from app.models.workflow_definition import WorkflowDefinition

    rows = (
        session.query(WorkflowDefinition)
        .filter(WorkflowDefinition.source == "user")
        .order_by(WorkflowDefinition.id)
        .all()
    )
    reports: list[RowReport] = []
    for row in rows:
        report = RowReport(
            row_id=str(row.id),
            user_id=getattr(row, "user_id", None),
            overrides=getattr(row, "overrides_pipeline_type", None),
        )
        report.flags = scan_manifest(row.manifest_json)
        report.compile = compile_verdict(row.manifest_json, f"audit:{row.id}")
        reports.append(report)
    return reports


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit status (see module docstring)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only-problems", action="store_true", help="print flagged/rejected rows only"
    )
    args = parser.parse_args(argv)

    try:
        from app.models.database import SessionLocal

        session = SessionLocal()
    except Exception as exc:  # noqa: BLE001 — setup failure is reported, not raised
        print(f"setup error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        reports = audit(session)
    except Exception as exc:  # noqa: BLE001
        print(f"query error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        session.rollback()
        session.close()

    problems = [r for r in reports if r.is_problem]
    for r in reports:
        if args.only_problems and not r.is_problem:
            continue
        kind = f"override:{r.overrides}" if r.overrides else "workflow"
        print(f"{r.row_id}  user={r.user_id}  {kind}  compile={r.compile}")
        for flag in r.flags:
            print(f"    - {flag}")
    print(f"\n{len(reports)} saved row(s); {len(problems)} flagged or rejected")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

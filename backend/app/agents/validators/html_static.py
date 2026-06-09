"""app/agents/validators/html_static.py — the ``html_static`` registered Validator (D-04).

Migrates the prototype build loop's stdlib ``static_check`` into a registered
``Validator`` capability (VALID-01/04). It lives APP-side because ``static_check``
is a heavy/app dependency; it imports the kernel PORT
(``agents.capabilities.base.Validator``) + the ``@register`` decorator — the
import-linter-LEGAL direction (app → capabilities). It NEVER imports the kernel:
it reaches ``static_check`` through the KernelServices handle
(``target.runner.static_check(target.path)``), so there is no kernel→app edge.

Severity mapping uses the SINGLE canonical ``map_severity`` IMPORTED from
``agents.capabilities.validators.severity`` (08-01, VALID-03 single source) — this
module does NOT define a second mapping. ``static_check`` issues are structural
defects that fail the page → internal P0 (CRITICAL); ``static_check`` warnings are
advisory (orphan sections) → internal P3 (LOW).

Each run writes one ``validation_results`` row via the handle's
``record_validation_result`` (owner/workspace-scoped, D-10) — best-effort, never
aborts the validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.capabilities.base import Validator  # port import — import-linter LEGAL
from agents.capabilities.registry import register
# THE single canonical severity mapping (VALID-03 / 08-01) — IMPORTED, never
# re-defined here. validators.severity is import-clean of any @register/discover()
# side-effect, so importing it at module import is safe.
from agents.capabilities.validators.severity import map_severity


@dataclass
class Issue:
    """One validator issue: internal P0–P3 severity + message + the source check."""

    severity: str          # internal P0–P3 (mapped to a UI label by map_severity)
    message: str
    validator: str = "html_static"


# The internal-severity order (most→least severe) for picking the row's worst label.
_SEVERITY_ORDER = ("P0", "P1", "P2", "P3")


def _worst_label(issues: list[Issue]) -> str | None:
    """Return the UI label of the most-severe issue (via the imported map_severity)."""
    for sev in _SEVERITY_ORDER:
        if any(i.severity == sev for i in issues):
            return map_severity(sev)
    return None


@register("validator", "html_static", user_allowed=True)
class HtmlStaticValidator:
    """Wraps ``static_check`` as a registered ``Validator`` (``name='html_static'``).

    Satisfies the ``Validator`` Protocol (``name`` + ``async validate``).
    """

    name = "html_static"

    async def validate(self, target: Any) -> list[Issue]:
        """Run ``static_check`` via the handle, returning mapped ``Issue`` records.

        ``target`` is a ``DeliverableContext`` (kernel-side): it carries ``path``
        (the on-disk deliverable), ``runner`` (the KernelServices handle), ``step``
        (the validation_results key) and ``task_meta`` (attempt number). The heavy
        check is reached ONLY through ``target.runner.static_check`` (NO kernel/app
        import here).
        """
        runner = getattr(target, "runner", None)
        if runner is None:
            return []
        result = runner.static_check(target.path)

        issues: list[Issue] = []
        # static_check issues are fatal structural defects → P0 (CRITICAL).
        for msg in getattr(result, "issues", None) or []:
            issues.append(Issue(severity="P0", message=str(msg)))
        # static_check warnings are advisory (orphan sections) → P3 (LOW).
        for msg in getattr(result, "warnings", None) or []:
            issues.append(Issue(severity="P3", message=str(msg)))

        await _record(target, "html_static", issues)
        return issues


async def _record(target: Any, validator: str, issues: list[Issue]) -> None:
    """Write a ``validation_results`` row via the handle (best-effort, D-10).

    Reaches ``record_validation_result`` off ``target.runner`` (the KernelServices
    handle) so the row carries the run's owner/workspace; a missing handle (offline
    unit fake) or a persist failure is a silent no-op (the audit write must never
    abort the validator — INV-3).
    """
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

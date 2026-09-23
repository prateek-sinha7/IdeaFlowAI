"""agents/capabilities/validators/screens_plan_coverage.py — the ``screens_plan_coverage``
validator.

A pure-stdlib, KERNEL-side registered ``Validator``. Runs after the Architect's
screen-plan step to catch the plan silently dropping a screen the spec declared —
the Builders task parser (``screen_plan``) expands one builder task per
``build/screens.json`` entry, so a screen missing from that file is a screen no
builder ever gets a task for, and nothing downstream would otherwise notice.

Reaches the sandbox directly via ``target.runner.sandbox.root`` (D-04 handle
reach), the same seam ``fragment_field_coverage`` uses — ``spec.md`` and
``build/screens.json`` are sibling files, not the run's single declared
deliverable.

Spec screen-id resolution: a spec section heading of the shape
``### <id> — <Name>`` (an em dash, not a hyphen) declares one screen. This
excludes ``### UC-<n> — ...`` use-case headings (uppercase ``UC`` never matches
the lowercase-anchored id pattern) and ``### Flow <n>: ...`` flow headings (no
em dash at all) — both are spec sections, but neither is a screen.

``build/screens.json`` is parsed through ``screen_inventory.parse_inventory``
(the single source of truth for that file's shape) — this module does not
re-implement JSON/fence parsing.

Every issue names the concrete missing screen id(s) so a ``fix: {max_attempts:
N}`` re-run can act on the feedback directly.

Severity maps through the SINGLE imported ``map_severity`` (VALID-03 single
source). Each run writes a ``validation_results`` row via the handle
(best-effort).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.capabilities.base import Validator  # port
from agents.capabilities.registry import register
from agents.capabilities.screen_inventory import InventoryError, parse_inventory
from agents.capabilities.validators.severity import map_severity  # single source

_SCREEN_HEADING_RE = re.compile(r"^###\s+(?P<id>[a-z0-9][a-z0-9-]*)\s+—\s", re.MULTILINE)
_MAX_LISTED = 20


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = "screens_plan_coverage"


def _sandbox_root(target: Any) -> Path | None:
    """Resolve the run sandbox root off ``target.runner.sandbox`` (D-04 handle reach)."""
    runner = getattr(target, "runner", None)
    sandbox = getattr(runner, "sandbox", None)
    root = getattr(sandbox, "root", None)
    if root is None:
        return None
    p = Path(root)
    return p if p.is_dir() else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _spec_screen_ids(text: str) -> list[str]:
    """Screen ids the spec declares, in spec order (``### <id> — <Name>`` headings)."""
    ids: list[str] = []
    seen: set[str] = set()
    for m in _SCREEN_HEADING_RE.finditer(text or ""):
        sid = m.group("id")
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


@register(
    "validator",
    "screens_plan_coverage",
    user_allowed=True,
    description="Verify build/screens.json (the Architect's screen plan) covers every screen spec.md declares, naming any missing screen id(s).",
)
class ScreensPlanCoverageValidator:
    """Post screen-plan Architect step coverage checker (``name='screens_plan_coverage'``)."""

    name = "screens_plan_coverage"

    async def validate(self, target: Any) -> list[Issue]:
        issues: list[Issue] = []
        root = _sandbox_root(target)
        if root is None:
            await _record(target, "screens_plan_coverage", issues)
            return issues

        spec_text = _read(root / "spec.md")
        if not spec_text.strip():
            await _record(target, "screens_plan_coverage", issues)
            return issues

        spec_ids = _spec_screen_ids(spec_text)
        if not spec_ids:
            await _record(target, "screens_plan_coverage", issues)
            return issues

        screens_path = root / "build" / "screens.json"
        raw = _read(screens_path)
        if not raw.strip():
            issues.append(
                Issue(
                    severity="P0",
                    message=(
                        "build/screens.json was not written — this is the file the "
                        "Builders step reads to expand one task per screen"
                    ),
                )
            )
            await _record(target, "screens_plan_coverage", issues)
            return issues

        try:
            inventory = parse_inventory(raw)
        except InventoryError as exc:
            issues.append(
                Issue(
                    severity="P0",
                    message=f"build/screens.json could not be parsed: {exc}",
                )
            )
            await _record(target, "screens_plan_coverage", issues)
            return issues

        inventory_ids = {s.id for s in inventory.screens}
        missing = [sid for sid in spec_ids if sid not in inventory_ids]
        if missing:
            shown = missing[:_MAX_LISTED]
            message = (
                "build/screens.json is missing screen(s) the spec declares: "
                + ", ".join(shown)
            )
            remainder = len(missing) - len(shown)
            if remainder > 0:
                message += f" (and {remainder} more)"
            issues.append(Issue(severity="P0", message=message))

        await _record(target, "screens_plan_coverage", issues)
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

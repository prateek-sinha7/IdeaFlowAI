"""agents/capabilities/validators/task_done_when.py — Tier#5 validator (D-05).

A pure-stdlib, KERNEL-side registered ``Validator`` (no heavy dep → it lives here,
not app-side; D-05 placement call). Tier#5 is a PER-TASK acceptance check: it
verifies the current task's declared ``done_when`` acceptance criteria are evidenced
in the deliverable the task produced.

Heuristic (stdlib only): the task's acceptance criteria ride on
``target.task_meta["done_when"]`` (a list of short criteria strings). For each
criterion, its salient keywords must appear in ``target.content`` (the produced
deliverable); a criterion with no evidence is an internal P1 (HIGH) unmet-acceptance
issue. No declared criteria → no issues (the check degrades, never crashes).

Severity maps through the SINGLE imported ``map_severity`` (08-01, VALID-03 single
source) — no local mapping. Each run writes a ``validation_results`` row via the
handle (best-effort).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agents.capabilities.base import Validator  # port
from agents.capabilities.registry import register
from agents.capabilities.validators.severity import map_severity  # single source (08-01)


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = "task_done_when"


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 4}


@register("validator", "task_done_when", user_allowed=True)
class TaskDoneWhenValidator:
    """Tier#5 per-task acceptance checker (``name='task_done_when'``)."""

    name = "task_done_when"

    async def validate(self, target: Any) -> list[Issue]:
        """Flag declared done_when criteria with no evidence in the deliverable (P1)."""
        meta = getattr(target, "task_meta", None) or {}
        criteria = list(meta.get("done_when", []) or [])
        content_kw = _keywords(getattr(target, "content", "") or "")

        issues: list[Issue] = []
        for criterion in criteria:
            kw = _keywords(str(criterion))
            if kw and not (kw & content_kw):
                issues.append(
                    Issue(
                        severity="P1",
                        message=f"acceptance criterion not evidenced: '{criterion}'",
                    )
                )

        await _record(target, "task_done_when", issues)
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

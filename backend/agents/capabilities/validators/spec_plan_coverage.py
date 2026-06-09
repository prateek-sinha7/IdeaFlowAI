"""agents/capabilities/validators/spec_plan_coverage.py — Tier#4 validator (D-05).

A pure-stdlib, KERNEL-side registered ``Validator`` (no heavy dep → it lives here,
not app-side; D-05 placement call). Tier#4 is a PRE-BUILD analyze check: it
inspects whether the planner's task plan covers the spec's declared requirements —
a coverage gap is a planning omission worth surfacing.

Heuristic (stdlib only): extract the spec's requirement headings / bullet items and
the plan's task headings from the ``DeliverableContext`` (the spec + plan text are
reached via ``target.task_meta`` / ``target.content``); a spec section with NO
matching plan task is an internal P1 (HIGH) coverage gap. Absent spec/plan text → no
issues (the check degrades, never crashes).

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
    validator: str = "spec_plan_coverage"


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$", re.MULTILINE)


def _topics(text: str) -> list[str]:
    """Extract heading/bullet topic tokens from markdown-ish text (stdlib only)."""
    topics: list[str] = []
    for m in _HEADING_RE.finditer(text or ""):
        topics.append(m.group(1).strip().lower())
    for m in _BULLET_RE.finditer(text or ""):
        topics.append(m.group(1).strip().lower())
    return topics


def _keywords(topic: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", topic) if len(w) >= 4}


@register("validator", "spec_plan_coverage", user_allowed=True)
class SpecPlanCoverageValidator:
    """Tier#4 pre-build coverage analyzer (``name='spec_plan_coverage'``)."""

    name = "spec_plan_coverage"

    async def validate(self, target: Any) -> list[Issue]:
        """Flag spec requirements with no matching plan task (internal P1)."""
        meta = getattr(target, "task_meta", None) or {}
        spec_text = str(meta.get("spec_text", "") or "")
        plan_text = str(meta.get("plan_text", "") or getattr(target, "content", "") or "")

        issues: list[Issue] = []
        spec_topics = _topics(spec_text)
        plan_kw = set()
        for t in _topics(plan_text):
            plan_kw |= _keywords(t)

        for topic in spec_topics:
            kw = _keywords(topic)
            if kw and not (kw & plan_kw):
                issues.append(
                    Issue(
                        severity="P1",
                        message=f"spec requirement '{topic}' has no matching plan task",
                    )
                )

        await _record(target, "spec_plan_coverage", issues)
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

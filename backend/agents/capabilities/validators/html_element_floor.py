"""agents/capabilities/validators/html_element_floor.py — the ``html_element_floor`` validator (A1).

A pure-stdlib, KERNEL-side registered ``Validator``. Runs after any step that
produces a new ``draft.v<N>.html`` (story-layer, assembler, structure-check) to
catch the exact defect STABILIZATION.md traced to story-layer: a
``read_file -> write_file`` "save" pass that re-authors the draft from memory
instead of copying it, silently truncating it (7e8a8e71: v2=89 KB/11 sections/30
inputs -> v3=29 KB/1/0; a786cc27: v2=66 KB -> v3=19 KB/1/0).

Reaches the sandbox directly via ``target.runner.sandbox.root`` (the same reach as
``journeys_coverage``) — the drafts are versioned SIBLING files, not the run's
single declared deliverable ``target.path`` resolves to. Compares the
highest-numbered ``draft.v*.html`` (numeric sort — ``draft.v10.html`` outranks
``draft.v9.html``) against the PREVIOUS version. Fewer than two drafts on disk (a
seed-only history) degrades to no issues, never crashes.

Fails when any of ``<section data-page=``, ``<input``, ``<select``, ``<button``,
``<textarea`` DROPS between the previous and highest draft, or when the highest
draft is smaller than 40% of the previous by UTF-8 byte size. Every issue names
the before/after counts (or byte sizes) and the two file names, so a
``fix: {max_attempts: N}`` re-run (once wired — see the A1 proposal) can act on
the feedback directly.

Severity maps through the SINGLE imported ``map_severity`` (VALID-03 single
source). Each run writes a ``validation_results`` row via the handle
(best-effort).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.capabilities.registry import register
from agents.capabilities.validators.severity import map_severity  # single source

_DRAFT_RE = re.compile(r"^draft\.v(\d+)\.html$", re.IGNORECASE)
_TRACKED_NEEDLES: tuple[str, ...] = (
    "<section data-page=",
    "<input",
    "<select",
    "<button",
    "<textarea",
)
# The floor: a highest draft under 40% of the previous draft's bytes is treated as
# truncated, not edited (matches the observed 89KB->29KB / 66KB->19KB defects,
# both ~30% of the prior size).
_MIN_BYTE_RATIO = 0.4


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = "html_element_floor"


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


def _ordered_drafts(root: Path) -> list[tuple[int, Path]]:
    """Every ``draft.v<N>.html`` under root, sorted HIGHEST-first (numeric, not lexicographic)."""
    drafts: list[tuple[int, Path]] = []
    for p in root.glob("draft.v*.html"):
        m = _DRAFT_RE.match(p.name)
        if m:
            drafts.append((int(m.group(1)), p))
    drafts.sort(key=lambda t: t[0], reverse=True)
    return drafts


@register(
    "validator",
    "html_element_floor",
    user_allowed=True,
    description="Compare the highest draft.v*.html against the previous version and flag any drop in interactive-element counts or a >60% byte-size collapse.",
)
class HtmlElementFloorValidator:
    """Detects a story-layer/assembler/structure-check pass that truncated the draft (``name='html_element_floor'``)."""

    name = "html_element_floor"

    async def validate(self, target: Any) -> list[Issue]:
        issues: list[Issue] = []
        root = _sandbox_root(target)
        if root is None:
            await _record(target, "html_element_floor", issues)
            return issues

        drafts = _ordered_drafts(root)
        if len(drafts) < 2:
            await _record(target, "html_element_floor", issues)
            return issues

        _, highest_path = drafts[0]
        _, prev_path = drafts[1]
        highest = _read(highest_path)
        prev = _read(prev_path)

        for needle in _TRACKED_NEEDLES:
            before = prev.lower().count(needle.lower())
            after = highest.lower().count(needle.lower())
            if after < before:
                issues.append(
                    Issue(
                        severity="P0",
                        message=(
                            f"{needle!r} count dropped from {before} in "
                            f"{prev_path.name} to {after} in {highest_path.name}"
                        ),
                    )
                )

        before_bytes = len(prev.encode("utf-8"))
        after_bytes = len(highest.encode("utf-8"))
        if before_bytes > 0 and after_bytes < _MIN_BYTE_RATIO * before_bytes:
            issues.append(
                Issue(
                    severity="P0",
                    message=(
                        f"{highest_path.name} is {after_bytes} bytes, under "
                        f"{int(_MIN_BYTE_RATIO * 100)}% of {prev_path.name}'s "
                        f"{before_bytes} bytes — the draft looks truncated, not edited."
                    ),
                )
            )

        await _record(target, "html_element_floor", issues)
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

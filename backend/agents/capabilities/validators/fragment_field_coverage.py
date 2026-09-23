"""agents/capabilities/validators/fragment_field_coverage.py — the ``fragment_field_coverage`` validator (A1).

A pure-stdlib, KERNEL-side registered ``Validator``. Runs after screen-builder
(the initial wave) and after review-revision (the repair wave) to catch the exact
defects STABILIZATION.md traced to those steps: a fragment shipped without a field
its journeys.md section names (5130337e: screen 6 shipped without "Bundle with Home
Policy" / "Paperless Billing" / "Good Student Discount"), or a worker writing to the
wrong target file entirely (a786cc27 pass 3: ``screens/2_fixed.html``, a sidecar
nothing downstream ever reads).

Reaches the sandbox directly via ``target.runner.sandbox.root`` — ``screens/*.html``
and ``journeys.md`` are sibling files, not the run's single declared deliverable
``target.path`` resolves to (that's ``prototype.html``).

Screen-id resolution: matches a fragment's id against a ``journeys.md`` heading
containing "Screen <id>" (the same sectionizer ``journeys_coverage`` uses). This
workflow's page ids ARE the screen numbers 1:1 (plan-lead's task builder names
``targets: ["screens/<page-id>.html"]`` where ``<page-id>`` is literally the screen
number from the PAGE INVENTORY), so the direct heading match already covers the
task brief's "by page id from build/digest.md PAGE INVENTORY" case without needing
a second digest.md parser for the same 1:1 mapping — a genuine id/number divergence
would need that second path; skipped here as unneeded complexity for this workflow
(flagged in the A1 proposal).

Every issue names the screen id and the missing field label(s), or the sidecar path
and its correct target, so a ``fix: {max_attempts: N}`` re-run (once wired — see the
A1 proposal) can act on the feedback directly.

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
from agents.capabilities.validators.severity import map_severity  # single source

_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+(.*)$")
_SCREEN_NUM_RE = re.compile(r"screen\s+(\w+)\b", re.IGNORECASE)
_FIELDS_MARKER_RE = re.compile(r"\*{0,2}FIELDS\*{0,2}", re.IGNORECASE)
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
# A legitimate fragment target is exactly "screens/<id>.html" (id = letters/digits
# only). A sidecar like "2_fixed.html" carries an underscore after the id — a
# worker wrote to the wrong file instead of editing/creating "screens/2.html".
_FRAGMENT_RE = re.compile(r"^([A-Za-z0-9]+)\.html$")
_SIDECAR_RE = re.compile(r"^([A-Za-z0-9]+)_.+\.html$")


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = "fragment_field_coverage"


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


def _screen_sections(text: str) -> dict[str, str]:
    """Split journeys.md-shaped markdown into ``{screen_id: section_body}``.

    Mirrors ``journeys_coverage._screen_sections`` (duplicated on purpose — matches
    this codebase's convention of self-contained validator modules with no shared
    markdown-parsing helper module).
    """
    lines = (text or "").splitlines()
    heading_idx = [i for i, ln in enumerate(lines) if _HEADING_LINE_RE.match(ln)]
    sections: dict[str, str] = {}
    for pos, idx in enumerate(heading_idx):
        m = _SCREEN_NUM_RE.search(lines[idx])
        if not m or m.group(1) in sections:
            continue
        end = heading_idx[pos + 1] if pos + 1 < len(heading_idx) else len(lines)
        sections[m.group(1)] = "\n".join(lines[idx:end])
    return sections


def _journeys_field_labels(section: str) -> list[str]:
    """Return the FIELDS table's data-row label cells for one journeys.md section."""
    lines = section.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if _FIELDS_MARKER_RE.search(ln) and "|" not in ln:
            start = i + 1
            break
    if start is None:
        return []
    labels: list[str] = []
    seen_header = False
    for ln in lines[start:]:
        if not ln.strip():
            if seen_header:
                break
            continue
        if _TABLE_SEP_RE.match(ln):
            continue
        m = _TABLE_ROW_RE.match(ln)
        if not m:
            if seen_header:
                break
            continue
        if not seen_header:
            seen_header = True  # the header row (Label | Type | ...) itself
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if cells and cells[0]:
            labels.append(cells[0])
    return labels


@register(
    "validator",
    "fragment_field_coverage",
    user_allowed=True,
    description="For each screens/<id>.html fragment, verify every FIELDS-table label from its journeys.md section appears in the fragment, and flag any <id>_*.html sidecar (a worker writing to the wrong target).",
)
class FragmentFieldCoverageValidator:
    """Post screen-builder / post review-revision fragment checker (``name='fragment_field_coverage'``)."""

    name = "fragment_field_coverage"

    async def validate(self, target: Any) -> list[Issue]:
        issues: list[Issue] = []
        root = _sandbox_root(target)
        if root is None:
            await _record(target, "fragment_field_coverage", issues)
            return issues

        screens_dir = root / "screens"
        if not screens_dir.is_dir():
            await _record(target, "fragment_field_coverage", issues)
            return issues

        sections = _screen_sections(_read(root / "journeys.md"))

        for path in sorted(screens_dir.glob("*.html")):
            sidecar_m = _SIDECAR_RE.match(path.name)
            if sidecar_m:
                screen_id = sidecar_m.group(1)
                issues.append(
                    Issue(
                        severity="P0",
                        message=(
                            f"screens/{path.name} is a sidecar file — a worker "
                            f"wrote to the wrong target; the only valid path for "
                            f"screen {screen_id} is screens/{screen_id}.html"
                        ),
                    )
                )
                continue

            frag_m = _FRAGMENT_RE.match(path.name)
            if not frag_m:
                continue
            screen_id = frag_m.group(1)
            section = sections.get(screen_id, "")
            if not section:
                continue  # no journeys.md section to check coverage against
            labels = _journeys_field_labels(section)
            if not labels:
                continue
            fragment_lower = _read(path).lower()
            missing = [lbl for lbl in labels if lbl.lower() not in fragment_lower]
            if missing:
                issues.append(
                    Issue(
                        severity="P0",
                        message=(
                            f"screens/{screen_id}.html is missing field label(s) "
                            f"from journeys.md: {', '.join(missing)}"
                        ),
                    )
                )

        await _record(target, "fragment_field_coverage", issues)
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

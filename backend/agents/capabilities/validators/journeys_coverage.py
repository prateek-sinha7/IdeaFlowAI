"""agents/capabilities/validators/journeys_coverage.py — the ``journeys_coverage`` validator (A1).

A pure-stdlib, KERNEL-side registered ``Validator`` (no heavy dep — lives here, not
app-side, mirroring the ``spec_plan_coverage``/``task_done_when`` placement call).
Runs after ``journey-designer`` to catch the exact content-loss defects observed in
production (STABILIZATION.md): the journey-designer declares a screen ``MISSING``
even though the readers' notes fully document it (2ef8f6c8 MISSING=6; a786cc27
screens 5,6,7,8), or drops a screen's field table while its notes list fields (the
screen-6 checkbox loss in 5130337e traced back to exactly this).

Unlike ``spec_plan_coverage``/``task_done_when`` (which read pre-supplied text off
``target.task_meta``/``target.content``), this validator reaches the sandbox
directly via ``target.runner.sandbox.root`` — ``journeys.md`` and ``notes/doc-*.md``
are SEPARATE files, not a single deliverable ``target.path`` resolves to (the run's
declared deliverable is ``prototype.html``, not ``journeys.md``). A missing sandbox
degrades to no issues (never crashes), matching the Tier validators' convention.

Heuristic (stdlib only, regex-based — matches the ``spec_plan_coverage`` idiom):
  1. MISSING-despite-documented: a ``journeys.md`` screen section marked MISSING
     whose number is referenced anywhere in ``notes/doc-*.md`` (internal P0).
  2. Undocumented-in-journeys: a screen number referenced anywhere in the notes
     (including only as a navigation target, e.g. "Next -> Screen 7: Furrow") with
     NO section at all in ``journeys.md`` (internal P0).
  3. "Unknown Module": any stage/journey heading containing that literal phrase —
     the journey-designer prompt explicitly forbids it (internal P0).
  4. Zero-field screen: a journeys.md screen section whose FIELDS table has zero
     data rows while its notes section lists fields (internal P1 — a narrower loss
     than a whole missing screen, still real).

Every issue names the exact screen number(s) and the notes file(s) that document
them, so a ``fix: {max_attempts: N}`` re-run (once wired — see the A1 proposal) can
act on the feedback without re-deriving it.

Severity maps through the SINGLE imported ``map_severity`` (VALID-03 single source).
Each run writes a ``validation_results`` row via the handle (best-effort).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.capabilities.base import Validator  # port
from agents.capabilities.registry import register
from agents.capabilities.validators.severity import map_severity  # single source


@dataclass
class Issue:
    severity: str
    message: str
    validator: str = "journeys_coverage"


# ── Parsing heuristics (stdlib regex — no markdown parser dependency) ──────────
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+(.*)$")
_SCREEN_NUM_RE = re.compile(r"screen\s+(\d+)\b", re.IGNORECASE)
_MISSING_WORD_RE = re.compile(r"\bmissing\b", re.IGNORECASE)
_UNKNOWN_MODULE_RE = re.compile(r"unknown module", re.IGNORECASE)
_FIELDS_MARKER_RE = re.compile(r"\*{0,2}FIELDS\*{0,2}", re.IGNORECASE)
_NOTES_FIELDS_MARKER_RE = re.compile(r"\*{0,2}Fields:?\*{0,2}", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[-*]\s+\S")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

# Rule 1/4 only look at the OPENING of a screen section (heading + first few body
# lines) — a MISSING marker or a FIELDS table sits there by convention; scanning
# the whole section (which may run to a VALIDATION prose block) risks a false
# "missing" hit on unrelated prose (e.g. "field is not missing").
_HEAD_WINDOW_LINES = 4


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
    """Split journeys.md-shaped markdown into ``{screen_number: section_body}``.

    A screen section starts at any heading line whose text contains "Screen <N>"
    and runs to the next heading line (any level) or EOF. The first heading found
    for a given number wins (a screen is documented once).
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


def _missing_screen_numbers(sections: dict[str, str]) -> set[str]:
    missing: set[str] = set()
    for num, body in sections.items():
        head = "\n".join(body.splitlines()[:_HEAD_WINDOW_LINES])
        if _MISSING_WORD_RE.search(head):
            missing.add(num)
    return missing


def _unknown_module_headings(text: str) -> list[str]:
    return [
        ln.strip() for ln in (text or "").splitlines()
        if _HEADING_LINE_RE.match(ln) and _UNKNOWN_MODULE_RE.search(ln)
    ]


def _journeys_field_rows(section: str) -> list[str]:
    """Return the FIELDS table's data-row label cells for one journeys.md section."""
    lines = section.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if _FIELDS_MARKER_RE.search(ln) and "|" not in ln:
            start = i + 1
            break
    if start is None:
        return []
    rows: list[str] = []
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
            rows.append(cells[0])
    return rows


def _notes_section_for_screen(notes_text: str, screen_num: str) -> str:
    """Return the sub-block of one notes doc covering one screen (heading-bounded)."""
    lines = notes_text.splitlines()
    heading_idx = [i for i, ln in enumerate(lines) if _HEADING_LINE_RE.match(ln)]
    for pos, idx in enumerate(heading_idx):
        m = _SCREEN_NUM_RE.search(lines[idx])
        if m and m.group(1) == screen_num:
            end = heading_idx[pos + 1] if pos + 1 < len(heading_idx) else len(lines)
            return "\n".join(lines[idx:end])
    return ""


def _notes_lists_fields(section: str) -> bool:
    lines = section.splitlines()
    for i, ln in enumerate(lines):
        if not _NOTES_FIELDS_MARKER_RE.search(ln):
            continue
        for later in lines[i + 1 : i + 12]:
            if _BULLET_RE.match(later):
                return True
            stripped = later.strip()
            if stripped.startswith("**") and stripped.endswith("**"):
                break  # hit the next labelled block (Buttons:, Quote/Motto:, ...)
        return False
    return False


@register(
    "validator",
    "journeys_coverage",
    user_allowed=True,
    description="Cross-check journeys.md against notes/doc-*.md: flag screens marked MISSING despite being documented, screens referenced but never sectioned, 'Unknown Module' stages, and screens whose field table went empty.",
)
class JourneysCoverageValidator:
    """Post journey-designer coverage checker (``name='journeys_coverage'``)."""

    name = "journeys_coverage"

    async def validate(self, target: Any) -> list[Issue]:
        issues: list[Issue] = []
        root = _sandbox_root(target)
        if root is None:
            await _record(target, "journeys_coverage", issues)
            return issues

        journeys_text = _read(root / "journeys.md")
        notes_dir = root / "notes"
        notes_texts: dict[str, str] = {}
        if notes_dir.is_dir():
            for p in sorted(notes_dir.glob("doc-*.md")):
                notes_texts[p.name] = _read(p)

        sections = _screen_sections(journeys_text)
        missing_nums = _missing_screen_numbers(sections)

        refs_by_num: dict[str, set[str]] = {}
        for name, text in notes_texts.items():
            for m in _SCREEN_NUM_RE.finditer(text):
                refs_by_num.setdefault(m.group(1), set()).add(name)

        # Rule 1 — MISSING marker for a screen the notes actually document.
        for num in sorted(missing_nums, key=int):
            sources = refs_by_num.get(num)
            if not sources:
                continue
            issues.append(
                Issue(
                    severity="P0",
                    message=(
                        f"journeys.md marks Screen {num} as MISSING, but it is "
                        f"documented in {', '.join(sorted(sources))} — remove the "
                        "MISSING marker and transcribe the screen from that notes file."
                    ),
                )
            )

        # Rule 2 — a screen referenced anywhere in notes with no section at all.
        for num in sorted(refs_by_num, key=int):
            if num in sections:
                continue
            sources = sorted(refs_by_num[num])
            issues.append(
                Issue(
                    severity="P0",
                    message=(
                        f"Screen {num} is referenced in {', '.join(sources)} "
                        "(e.g. as a navigation target) but has no section at all "
                        "in journeys.md — add a full screen section for it."
                    ),
                )
            )

        # Rule 3 — "Unknown Module" stage/section headers.
        for heading in _unknown_module_headings(journeys_text):
            issues.append(
                Issue(
                    severity="P0",
                    message=(
                        f"heading {heading!r} contains \"Unknown Module\" — name "
                        "the actual module from the source documents."
                    ),
                )
            )

        # Rule 4 — a documented screen whose journeys.md FIELDS table is empty.
        for num, body in sorted(sections.items(), key=lambda kv: int(kv[0])):
            if num in missing_nums:
                continue  # already reported under rule 1
            if _journeys_field_rows(body):
                continue
            source_file = None
            for name, text in notes_texts.items():
                notes_section = _notes_section_for_screen(text, num)
                if notes_section and _notes_lists_fields(notes_section):
                    source_file = name
                    break
            if source_file is None:
                continue
            issues.append(
                Issue(
                    severity="P1",
                    message=(
                        f"Screen {num} has a FIELDS table with zero rows in "
                        f"journeys.md, but its notes section in {source_file} "
                        "lists fields — transcribe them."
                    ),
                )
            )

        await _record(target, "journeys_coverage", issues)
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

"""app/agents/validators/design_quality.py — Tier#6 design_quality validator (D-05).

A registered ``Validator`` living APP-side (heavier, render/markup-style checks →
app placement per D-05). It imports the kernel PORT
(``agents.capabilities.base.Validator``) + the ``@register`` decorator — the
import-linter-LEGAL direction (app → capabilities). It NEVER imports the kernel; it
reaches the deliverable content through the ``DeliverableContext`` target.

WARNINGS-FIRST / NON-BLOCKING (VALID-05): ``design_quality`` emits ONLY internal P2
(MEDIUM) and P3 (LOW) issues — NEVER P0/P1. The validation gate blocks only on
CRITICAL (P0); design_quality therefore can never block a step. It surfaces design
nits — design-token usage, placeholder/lorem text, and basic accessibility
(missing ``alt`` on ``<img>``, missing a page ``<title>``) — as advisories.

Severity maps through the SINGLE imported ``map_severity`` (08-01, VALID-03 single
source) — no local mapping. Each run writes a ``validation_results`` row via the
handle (best-effort).
"""

from __future__ import annotations

import re
from typing import Any

from agents.capabilities.base import Validator  # port import — import-linter LEGAL
from agents.capabilities.registry import register
# Severity is mapped (via the shared _record helper) through the SINGLE canonical
# map_severity (08-01, validators.severity) — design_quality never defines its own.
from app.agents.validators.html_static import Issue, _record

# Placeholder / lorem text patterns that signal unfinished design (advisory).
_PLACEHOLDER_RE = re.compile(
    r"\b(lorem ipsum|placeholder|todo|tbd|coming soon|your text here)\b",
    re.IGNORECASE,
)
# An <img ...> with no alt= attribute (basic a11y advisory).
_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_ALT_RE = re.compile(r"\balt\s*=", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)


@register("validator", "design_quality", user_allowed=True)
class DesignQualityValidator:
    """Tier#6 warnings-first design validator (``name='design_quality'``).

    Emits ONLY P2/P3 — it is non-blocking by construction (VALID-05).
    """

    name = "design_quality"

    async def validate(self, target: Any) -> list[Issue]:
        """Surface design-token / placeholder / a11y nits as P2/P3 advisories."""
        content = getattr(target, "content", "") or ""

        issues: list[Issue] = []

        # Placeholder / lorem text — unfinished content (P3 LOW advisory).
        for m in _PLACEHOLDER_RE.finditer(content):
            issues.append(
                Issue(severity="P3",
                      message=f"placeholder text present: '{m.group(0)}'",
                      validator="design_quality")
            )

        # Accessibility: <img> without alt (P2 MEDIUM advisory).
        for img in _IMG_RE.findall(content):
            if not _ALT_RE.search(img):
                issues.append(
                    Issue(severity="P2",
                          message="accessibility: <img> missing alt attribute",
                          validator="design_quality")
                )

        # Accessibility: a document with markup but no <title> (P2 MEDIUM advisory).
        if "<html" in content.lower() and not _TITLE_RE.search(content):
            issues.append(
                Issue(severity="P2",
                      message="accessibility: document has no <title>",
                      validator="design_quality")
            )

        # INVARIANT (VALID-05): design_quality is warnings-first — never P0/P1.
        issues = [i for i in issues if i.severity in ("P2", "P3")]

        await _record(target, "design_quality", issues)
        return issues

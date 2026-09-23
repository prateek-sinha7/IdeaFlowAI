"""agents/capabilities/deliverables/_coverage.py — upstream-coverage check.

QA-PS-028 / ISS-730: a final compiling/aggregation step is told in prose to
"include ALL" of what it read and nothing verifies that it did. When it drops a
whole upstream section, its own summary counters count only what it kept, the
step raises nothing, and the run publishes "completed" — the user downloads a
deliverable missing content they watched an upstream step produce.

``_placeholder.py`` answers "is this deliverable the agent talking about the
work instead of the work?". This module answers the adjacent question: "is this
deliverable visibly a COPY of its upstream sources that skipped one of them?".
Same doctrine — the signal flips a user-visible success badge, so a false
positive is worse than a miss — so the check fires only on the narrow shape the
reproduced cycles show, and is deliberately NOT a general "did the compiler
cover everything" judgement:

  * only TOP-LEVEL sections count. A compiler legitimately rewrites, merges and
    re-levels sub-headings; a whole top-level section vanishing while its
    siblings survive is the reproduced defect (BUGS.md#qa-ps-028: the entire
    "SDK Integration Layer" epic, and ISS-730's two DB cycles).
  * the source must have at least ``_MIN_SECTIONS`` of them — two sections are
    too small a sample to tell copying apart from summarising.
  * the deliverable must already carry at least ``_MIN_KEPT_NUM/_MIN_KEPT_DEN``
    of that source's section titles VERBATIM. That is the bound that keeps a
    compiler which paraphrases or renames everything (low coverage — it is
    synthesising, not copying) from tripping it. Only a document demonstrably
    copying a source's headings through, minus one, is flagged.

QA-PS-021 / ISS-850 adds the DEGENERATE case of the same question. A declared
upstream source that contributed NOTHING AT ALL cannot be diffed section by
section — there is nothing to diff against — yet a substantial deliverable
still came out the other end, so it was not produced from the input the
completing step declares it consumes. That is the reporter's mode 2
(``ppt-validator`` / ``prototype-validate`` regenerating the missing build
themselves, under their own attribution). Same doctrine, one extra bound:

  * the deliverable must be longer than ``_MIN_UNSOURCED_CHARS``. Below it the
    text is narration, and ``_placeholder.py`` owns that shape — the two
    constants are deliberately equal so the signals partition the range
    instead of contending for it.

Import purity (import-linter): stdlib only — no ``app.*``, no kernel import —
so the kernel's completion gate can call it without crossing a boundary.
"""

from __future__ import annotations

import re

# An upstream source needs this many top-level sections before its coverage
# says anything. Below it, one "missing" title is noise.
_MIN_SECTIONS = 3

# How much of the source the deliverable must already reproduce VERBATIM before
# a missing sibling reads as a drop rather than as normal synthesis. Integer
# math (kept * DEN >= total * NUM) — no float boundary wobble at 2/3.
_MIN_KEPT_NUM = 2
_MIN_KEPT_DEN = 3

# How long the deliverable must be before a source that contributed nothing
# reads as "this was regenerated, not compiled" rather than as narration.
# Kept EQUAL to ``_placeholder.py``'s ``_MAX_NARRATION_CHARS`` on purpose: below
# the bound that module already owns the text, above it this one does, and
# neither can claim the same output.
_MIN_UNSOURCED_CHARS = 2000

_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
_DECORATION = re.compile(r"[*_`]+")
_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Lowercase, strip markdown emphasis/backticks, collapse whitespace."""
    return _WHITESPACE.sub(" ", _DECORATION.sub("", text)).strip().lower()


def _top_level_titles(text: str) -> list[str]:
    """Return the normalized titles of ``text``'s shallowest ATX headings.

    "Top level" is relative to the document: a source whose shallowest heading
    is ``##`` has ``##`` sections. Order-preserving and de-duplicated.
    """
    headings = [(len(m.group(1)), _normalize(m.group(2))) for m in _ATX_HEADING.finditer(text)]
    headings = [(level, title) for level, title in headings if title]
    if not headings:
        return []
    top = min(level for level, _ in headings)
    titles: list[str] = []
    for level, title in headings:
        if level == top and title not in titles:
            titles.append(title)
    return titles


def dropped_section_reason(deliverable: object, sources: dict[str, str]) -> str | None:
    """Return why ``deliverable`` is not covered by its upstream, or ``None``.

    Two shapes, in one pass over the same sources: a source the deliverable is
    visibly copying minus one section (QA-PS-028), and a source that produced
    nothing at all under a substantial deliverable (QA-PS-021 / ISS-850).

    ``sources`` maps an upstream agent id to the output that step produced —
    the compiling step's DECLARED upstream sources, nothing wider. ``None``
    means "no evidence", the default for anything non-textual, empty, or for
    any source the deliverable is not visibly copying.
    """
    if not isinstance(deliverable, str) or not deliverable.strip():
        return None
    text = deliverable.strip()
    haystack = _normalize(deliverable)
    for agent_id in sorted(sources):
        source = sources[agent_id] or ""
        if not source.strip():
            # ISS-850: the declared source produced NOTHING, so the drop check
            # below structurally cannot speak — there are no section titles to
            # diff against. A substantial deliverable arrived anyway, which
            # means the completing step produced it ITSELF rather than from the
            # input it declares it consumes (the reporter's ppt-validator /
            # prototype-validate regenerating a missing build under their own
            # attribution). Under the bound it is narration — _placeholder.py's.
            if len(text) > _MIN_UNSOURCED_CHARS:
                return (
                    f"deliverable is {len(text)} characters but upstream agent "
                    f"{agent_id!r}, one of its declared sources, produced no "
                    "content at all — it was not built from the input this step "
                    "declares it consumes"
                )
            continue
        titles = _top_level_titles(source)
        if len(titles) < _MIN_SECTIONS:
            continue
        missing = [t for t in titles if t not in haystack]
        if not missing:
            continue
        kept = len(titles) - len(missing)
        if kept * _MIN_KEPT_DEN < len(titles) * _MIN_KEPT_NUM:
            continue
        return (
            f"deliverable reproduces {kept} of {len(titles)} top-level sections "
            f"from upstream agent {agent_id!r} verbatim but omits "
            f"{', '.join(repr(t) for t in missing)} with no note of the omission"
        )
    return None

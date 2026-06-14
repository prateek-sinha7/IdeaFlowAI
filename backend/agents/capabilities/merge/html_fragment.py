"""agents/capabilities/merge/html_fragment.py — section-level HTML fragment composition.

A fan-out merge that composes DISJOINT HTML section fragments into a base document
(FANOUT-07). Registers to SATISFY FANOUT-07; NOTHING routes the ``prototype`` workflow
through it (Q33 / MERGE-01 v2 — prototype's per-task build loop writes one HTML file,
it does not fan out section fragments). It exists so a custom fan-out workflow CAN
compose section fragments by manifest + capability, with zero engine edit (SC-001).

Two fragments targeting the SAME section id with DIFFERING content are reported as a
conflict (never silently overwritten, Pitfall 6 / T-11-03-01). Pure stdlib — no kernel
import, no ``app.*`` import, no subprocess.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.merge.base import MergeResult
from agents.capabilities.registry import register

_SNIPPET_CAP = 256


def _sections_of(obj: Any) -> dict[str, str]:
    """Return the section-id → html map for a fragment/base (structural).

    A fragment exposes ``sections() -> dict[str, str]`` (section id → inner HTML); a
    plain dict is treated as that map directly. A None object is the empty map.
    """
    if obj is None:
        return {}
    sections = getattr(obj, "sections", None)
    if callable(sections):
        return dict(sections() or {})
    if isinstance(obj, dict):
        return dict(obj)
    return {}


def _name_of(obj: Any, fallback: str) -> str:
    return str(getattr(obj, "name", None) or fallback)


@register(
    "merge",
    "html_fragment",
    user_allowed=True,
    description="Merge fan-out worker outputs by concatenating their HTML fragments into one document.",
)
class HtmlFragmentMerge:
    """Compose disjoint HTML section fragments; same-section overlap → conflict.

    NOTE: nothing routes ``prototype`` through this strategy (Q33 / MERGE-01 v2). It
    satisfies FANOUT-07 for a custom section-fan-out workflow. Determinism: fragments
    + section ids iterate in sorted order so a disjoint composition is byte-stable.
    """

    name = "html_fragment"

    def merge(self, base: Any, fragments: Any) -> MergeResult:
        result = MergeResult()
        base_sections = _sections_of(base)
        # WR-08: the composed document must EXIST — prefer a structural
        # ``set_section(sid, html)`` writer on the base, falling back to a generic
        # ``write``; a plain dict base (offline tests) has neither and the typed
        # MergeResult is asserted directly.
        set_section = getattr(base, "set_section", None)
        writer = set_section if callable(set_section) else getattr(base, "write", None)
        claimed: dict[str, tuple[str, str]] = {}
        conflicted: set[str] = set()  # evicted sections are NEVER applied (no silent overwrite)

        ordered = sorted(list(fragments or []), key=lambda f: _name_of(f, ""))
        for fi, frag in enumerate(ordered):
            frag_name = _name_of(frag, f"fragment-{fi}")
            for sid in sorted(_sections_of(frag).keys()):
                html = _sections_of(frag)[sid]
                if sid in conflicted:
                    continue
                if sid in base_sections and base_sections[sid] != html:
                    result.conflicts.append(self._conflict(
                        sid, [("base", base_sections[sid]), (frag_name, html)]
                    ))
                    conflicted.add(sid)
                    claimed.pop(sid, None)
                    continue
                if sid in claimed:
                    prev_name, prev_html = claimed[sid]
                    if prev_html != html:
                        result.conflicts.append(self._conflict(
                            sid, [(prev_name, prev_html), (frag_name, html)]
                        ))
                        conflicted.add(sid)
                        claimed.pop(sid, None)
                    continue
                claimed[sid] = (frag_name, html)

        # Apply the non-conflicting sections in deterministic order — writing each
        # composed section onto the base so the merged document accumulates (WR-08).
        for sid in sorted(claimed.keys()):
            _src, html = claimed[sid]
            if callable(writer):
                writer(sid, html)
            result.applied.append(sid)
        return result

    @staticmethod
    def _conflict(section_id: str, sources: list[tuple[str, str]]) -> dict:
        return {
            "path": section_id,
            "sources": [name for name, _ in sources],
            "hunks": {name: (html or "")[:_SNIPPET_CAP] for name, html in sources},
        }

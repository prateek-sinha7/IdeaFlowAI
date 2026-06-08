"""agents/capabilities/deliverables/_artifact.py — shared deliverable transforms.

The ``_unwrap_artifact`` + ``_sanitize_carousel_deck_html`` transforms lifted
VERBATIM from ``engine.py`` (``_unwrap_artifact`` :427-444,
``_sanitize_carousel_deck_html`` :363-424) so the ``streamed_text`` + ``ppt``
resolvers share one byte-identical implementation (INV-12 move-don't-copy; the
engine call sites are deleted in 07-05). Import-pure: stdlib only, no kernel/app
import.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def unwrap_artifact(text: str) -> str:
    """Return the inner content of a single ``<artifact>…</artifact>`` wrapper.

    Some text agents (the PPT composer) emit their deliverable wrapped in an
    ``<artifact>`` tag. Return the unwrapped inner content; return ``text``
    unchanged when there is no wrapper.

    This is applied ONLY to a streamed-text deliverable — NEVER to a serialized
    code-gen bundle or a prototype's raw HTML, both of which can legitimately
    contain the literal substring ``<artifact>`` inside a file (e.g. an
    ``<artifact>`` *example* printed inside design.md). Stripping over those
    would extract the example and discard the real deliverable.

    Lifted verbatim from ``engine.py::_unwrap_artifact`` (INV-12).
    """
    if text and "<artifact" in text:
        m = re.search(r"<artifact[^>]*>\s*([\s\S]*?)\s*</artifact>", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return text


def sanitize_carousel_deck_html(html: str) -> str:
    """Strip slide-hiding CSS that contradicts a horizontal translateX carousel deck.

    The od_ppt composer LLM sometimes hallucinates ``.slide:not(.active){display:none}``
    and ``.slide.active{display:...}`` (and occasionally a bare ``.slide{...display:none...}``)
    on top of a pure-carousel template whose ``.stage`` navigates via
    ``transform: translateX(-i*100vw)`` while every ``.slide`` stays ``display:grid``.
    Those rules remove slides 2..N from layout, so only slide 1 ever renders.

    This is a deterministic backstop — the composer prompt forbids these rules, but LLM
    output is non-deterministic, so we also strip them here. We act ONLY when the deck is
    clearly a horizontal carousel, and we remove ONLY the conflicting rules — never the
    base ``.slide{display:grid}`` (the carousel relies on it) nor ``@media print`` rules
    (those use ``display:block``/``!important``, not ``display:none``).

    Returns the (possibly modified) HTML. No-op on non-carousel / non-HTML input.
    Scope this strictly to ppt/od_ppt output — never call it on prototype HTML.

    Lifted verbatim from ``engine.py::_sanitize_carousel_deck_html`` (INV-12).
    """
    if not html or "<style" not in html.lower():
        return html

    # Detect a horizontal carousel: a translateX(...vw) transform driving the stage,
    # plus the .stage/.slide structure it relies on. Whitespace-robust.
    has_translate_vw = re.search(r"translateX\s*\(\s*[^)]*vw", html, re.IGNORECASE) is not None
    has_stage_slide = (".stage" in html) and (".slide" in html)
    if not (has_translate_vw and has_stage_slide):
        return html

    original = html

    # 1) `.slide:not(.active) { ... }` — always a carousel-breaking hide rule. Remove it.
    html = re.sub(
        r"\.slide\s*:not\(\s*\.active\s*\)\s*\{[^}]*\}",
        "",
        html,
        flags=re.IGNORECASE,
    )

    # 2) `.slide.active { ... }` ONLY when it overrides `display` (fights the carousel).
    #    A cosmetic `.slide.active` rule (e.g. box-shadow) without `display` is left alone.
    html = re.sub(
        r"\.slide\.active\s*\{[^}]*\bdisplay\s*:[^}]*\}",
        "",
        html,
        flags=re.IGNORECASE,
    )

    # 3) A bare `.slide { ... display:none ... }` hide rule — never legitimate for a
    #    carousel (base is display:grid, print is display:block). The negative lookbehind
    #    keeps us off `.slide-inner`, `.slide.dark`, `.slide.active`, `.slide:not(...)`, etc.
    html = re.sub(
        r"(?<![\w.\-:])\.slide\s*\{[^}]*?\bdisplay\s*:\s*none\b[^}]*\}",
        "",
        html,
        flags=re.IGNORECASE,
    )

    if html != original:
        # Tidy up runs of blank lines left where rules were removed (cosmetic only).
        html = re.sub(r"[ \t]*\n([ \t]*\n){2,}", "\n\n", html)
        logger.info("Sanitized carousel deck: removed slide-hiding CSS (%d → %d chars)", len(original), len(html))
    return html

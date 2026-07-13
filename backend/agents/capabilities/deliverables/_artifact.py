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


def strip_pre_slide_body_text(html: str) -> str:
    """Strip any text or inline elements injected into ``<body>`` before the first slide.

    The od_ppt validator LLM non-deterministically injects its QA checklist
    results as visible text or HTML elements (``<p>``, ``<div>``, bullet lines, etc.)
    directly into the deck ``<body>`` — immediately before the ``.stage`` container
    or the first ``<section class="slide">`` element. This text then renders visibly
    in the iframe on top of the first presentation slide.

    This is the third deterministic backstop for validator output leakage
    (FIX-001 removed the preamble loophole; FIX-014 replaced checkbox syntax;
    this strips in-body injections that survive both earlier fixes — KAN-107).

    Strategy: find the ``<body>`` opening tag and the first real slide anchor
    (the ``.stage`` div or a ``<section class="slide"``). If there is non-whitespace
    content between those two points, remove it. This is a no-op when the body
    content begins with the slide container immediately (a correctly structured deck).
    Safe on non-HTML / non-ppt input.

    Scope: ONLY ppt/od_ppt deliverables. Never call on prototype HTML.
    """
    if not html:
        return html

    # Only act when we have a body tag and at least one slide indicator.
    body_lower = html.lower()
    has_body = "<body" in body_lower
    has_slide = ('<section class="slide"' in html or '<div class="stage"' in html)
    if not has_body or not has_slide:
        return html

    # Find the end of the <body ...> opening tag.
    body_tag_match = re.search(r"<body[^>]*>", html, re.IGNORECASE)
    if not body_tag_match:
        return html
    body_end = body_tag_match.end()  # index right after the <body...> closing >

    # Find the start of the first slide anchor — the earliest of:
    #   <div class="stage"   (carousel wrapper)
    #   <section class="slide"  (individual slide element)
    #   <div id="deck">  (some templates wrap slides in a deck div)
    #   <div class="deck"> or <div class="slides"> (alternate deck wrappers)
    # We search only in the substring after <body...> to avoid false matches in <head>.
    #
    # IMPORTANT: we treat all first-level deck structure elements as valid anchors.
    # This prevents stripping legitimate deck containers (e.g. <div id="deck">) that
    # appear immediately after <body> in templates that use custom wrapper elements.
    after_body = html[body_end:]

    stage_m = re.search(r'<div[^>]*class=["\'][^"\']*\bstage\b', after_body, re.IGNORECASE)
    slide_m = re.search(r'<section[^>]*class=["\'][^"\']*\bslide\b', after_body, re.IGNORECASE)
    # Also treat common deck-wrapper divs as valid slide anchors so we don't
    # strip the deck container itself (Broadside / templates using <div id="deck">).
    deck_id_m = re.search(r'<div[^>]*\bid=["\']deck["\']', after_body, re.IGNORECASE)
    deck_cls_m = re.search(r'<div[^>]*class=["\'][^"\']*\b(?:deck|slides|presentation)\b', after_body, re.IGNORECASE)

    # Take whichever valid slide/deck anchor comes first.
    candidates = [m.start() for m in (stage_m, slide_m, deck_id_m, deck_cls_m) if m is not None]
    if not candidates:
        return html
    first_slide_offset = min(candidates)

    # The preamble is the text between <body> and the first slide/deck anchor.
    preamble = after_body[:first_slide_offset]

    # Only act when the preamble contains non-whitespace TEXT content (not just
    # HTML tags). QA checklist text is plain text or <p>/<span> with text nodes;
    # legitimate decks start immediately with a structural element. If the preamble
    # contains only whitespace + HTML tags (e.g. a <script> or <style> block that
    # legitimately precedes the deck), skip the strip to avoid breaking the deck.
    preamble_stripped = preamble.strip()
    if not preamble_stripped:
        return html

    # Check if the preamble looks like QA text: contains alphanumeric content
    # that is NOT inside an HTML tag (i.e. actual visible text nodes).
    # A preamble that is only tags/whitespace is legitimate; one with text is QA leakage.
    preamble_text_only = re.sub(r"<[^>]+>", "", preamble_stripped).strip()
    if not preamble_text_only:
        # Preamble is only HTML elements (scripts, styles, etc.) — do NOT strip.
        return html

    original = html
    # Remove the preamble by splicing it out.
    slide_start_in_html = body_end + first_slide_offset
    html = html[:body_end] + "\n" + html[slide_start_in_html:]

    logger.info(
        "Stripped pre-slide body text from PPT deck (%d chars removed, text=%r…)",
        len(preamble),
        preamble_text_only[:80],
    )
    return html


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

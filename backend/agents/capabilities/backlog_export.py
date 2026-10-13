"""agents/capabilities/backlog_export.py — Backlog.pdf and Backlog.zip for the backlog workflow.

Two packagings of the same deliverables, written by the FINAL assemble step (after the
Reviewer), by code — no model involved:

  - ``Backlog.pdf``  one document for a person: a cover with the product's numbers, a
                     contents page with real page numbers, then every Markdown
                     deliverable as a chapter, printed by headless Chromium.
  - ``Backlog.zip``  every deliverable as its own file, plus ``Backlog.pdf``, for an
                     agent or tool that wants the separate files.

The PDF carries the Markdown documents. The data files (``backlog.csv``,
``backlog.json``, ``openapi.json``, ``schema.json``) hold the same content as
``backlog.md``, ``api.md`` and ``data-model.md`` in machine form; they ride in the zip.

Everything the PDF needs ships in ``vendor/``, so it prints with no network: Manrope
(the app's typeface) and Mermaid 11.17.2 (the version the UI draws diagrams with). A
diagram that does not parse is printed as its source under a note, never dropped.

Layout: the cover is printed on its own (full bleed, no footer) and prepended to the
body. The body is printed twice — the first pass only to read, from the PDF outline
Chromium builds out of the headings, which page each contents entry landed on.
"""

from __future__ import annotations

import base64
import datetime as _dt
import html
import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_VENDOR = Path(__file__).parent / "vendor"
MERMAID_JS = _VENDOR / "mermaid-11.17.2.min.js"

PDF_NAME = "Backlog.pdf"
ZIP_NAME = "Backlog.zip"

# Every deliverable of the backlog workflow, in the order the zip lists them.
DELIVERABLES = (
    "backlog.md",
    "backlog.csv",
    "backlog.json",
    "build-order.md",
    "solution.md",
    "architecture.md",
    "data-model.md",
    "schema.json",
    "api.md",
    "openapi.json",
    "integrations.md",
    "screens.md",
    "ui.md",
    "ux.md",
    "gaps.md",
)

# The Markdown deliverables in reading order — what it is, how it is built, then the
# backlog — each with the one line its chapter opener carries.
PDF_SECTIONS = (
    (
        "solution.md",
        "Solution",
        "What the product is — its features, roles, rules and scope.",
    ),
    (
        "architecture.md",
        "Architecture",
        "How it is built — context, containers, key flows and decisions.",
    ),
    (
        "data-model.md",
        "Data model",
        "The entities the product keeps, their attributes and relationships.",
    ),
    (
        "api.md",
        "API",
        "Every endpoint — its purpose, roles, rules and the stories it serves.",
    ),
    (
        "integrations.md",
        "Integrations",
        "The external systems the product talks to, and how.",
    ),
    (
        "screens.md",
        "Screens",
        "Every screen — how it is reached, its fields, actions and states.",
    ),
    (
        "ui.md",
        "UI",
        "How the product looks — palette, typography, components and every screen, as the prototype shows them.",
    ),
    (
        "ux.md",
        "UX",
        "How the product works — navigation, journeys, patterns, states and messages.",
    ),
    (
        "build-order.md",
        "Build order",
        "What to build first — milestones, waves and the dependencies between epics.",
    ),
    (
        "backlog.md",
        "Backlog",
        "Features, epics and user stories with requirements and acceptance criteria.",
    ),
    # Only when the final assembly left coverage items without a story.
    (
        "gaps.md",
        "Gaps",
        "The coverage items no story covers yet, and the coverage numbers.",
    ),
)

# Sub-headings listed under each chapter in the contents: h2 everywhere; the backlog
# also lists its epics (h3), which is how a reader navigates it.
_TOC_LEVELS = {"backlog.md": (2, 3)}
_TOC_DEFAULT_LEVELS = (2,)

# Neutrals from the app's own palette (frontend/src/styles/globals.css). The BRAND
# colours come from the prototype (build/ui/tokens.json, written by
# extract_prototype_ui) so the document carries the product's look; without one, the
# app's indigo.
DEFAULT_BRAND = "#3C2CDA"
INK_900, INK_800, INK_600, INK_500 = "#15161A", "#20222B", "#5B5C63", "#6E6F76"
WARM, LINE = "#F6F4EE", "#E6E3DB"
_GENERIC_FONTS = {
    "serif",
    "sans-serif",
    "monospace",
    "system-ui",
    "-apple-system",
    "blinkmacsystemfont",
    "ui-sans-serif",
    "ui-serif",
    "cursive",
    "fantasy",
    "inherit",
    "initial",
}


def _mix(color: str, other: str, t: float) -> str:
    a = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(
        f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b, strict=False)
    )


def _theme(sandbox: Any) -> dict[str, str]:
    """The PDF's brand colours and typeface, from the prototype when there is one."""
    from agents.capabilities.prototype_ui_extract import readable_on

    brand, font = DEFAULT_BRAND, ""
    try:
        tokens = json.loads(sandbox.read("build/ui/tokens.json") or "null") or {}
    except ValueError:
        tokens = {}
    if (tokens.get("brand") or {}).get("primary"):
        brand = tokens["brand"]["primary"]
    first = (
        str((tokens.get("body") or {}).get("font_family") or "")
        .split(",")[0]
        .strip()
        .strip("\"'")
    )
    if first and first.lower() not in _GENERIC_FONTS:
        font = f'"{first}", '
    # A light brand (yellow, cyan) cannot carry white cover text or read as heading
    # text on white paper: darken it until it can.
    for _ in range(6):
        if readable_on(brand) == "#FFFFFF":
            break
        brand = _mix(brand, "#000000", 0.18)
    return {
        "brand": brand,
        "dark": _mix(brand, "#000000", 0.28),
        "light": _mix(brand, "#FFFFFF", 0.22),
        "fill": _mix(brand, "#FFFFFF", 0.90),
        "tint": _mix(brand, "#FFFFFF", 0.95),
        "border": _mix(brand, "#FFFFFF", 0.80),
        "eyebrow": _mix(brand, "#FFFFFF", 0.72),
        "font": font,
    }


def _font_faces() -> str:
    faces = []
    for name, rng in (
        (
            "manrope-latin",
            "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, "
            "U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD",
        ),
        (
            "manrope-latin-ext",
            "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, "
            "U+1E00-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF",
        ),
    ):
        path = _VENDOR / f"{name}.woff2"
        if not path.exists():
            continue
        data = base64.b64encode(path.read_bytes()).decode()
        faces.append(
            "@font-face{font-family:Manrope;font-weight:200 800;font-style:normal;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');unicode-range:{rng};}}"
        )
    return "".join(faces)


def _css(t: dict[str, str]) -> str:
    BRAND, BRAND_FILL, BRAND_TINT, BRAND_BORDER, FONT = (
        t["brand"],
        t["fill"],
        t["tint"],
        t["border"],
        t["font"],
    )
    return f"""
@page {{ size: A4; margin: 20mm 17mm 20mm 17mm; }}
* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ margin: 0; font: 400 9.4pt/1.62 {FONT}Manrope, "Helvetica Neue", Arial, sans-serif; color: {INK_800};
        font-feature-settings: "tnum" 0; }}
a {{ color: {BRAND}; text-decoration: none; }}
p {{ margin: 0 0 7pt; }}
strong {{ color: {INK_900}; font-weight: 700; }}

/* ── chapter opener ─────────────────────────────── */
.chapter {{ break-before: page; }}
.opener {{ position: relative; margin: 0 0 22pt; padding: 26pt 0 18pt; border-bottom: 1px solid {LINE}; }}
.opener .num {{ position: absolute; right: 0; top: -6pt; font-size: 64pt; font-weight: 800; line-height: 1;
                color: {BRAND_FILL}; letter-spacing: -2pt; }}
.opener .eyebrow {{ font-size: 7.5pt; font-weight: 700; letter-spacing: 2.4pt; text-transform: uppercase; color: {BRAND}; }}
.opener h1 {{ margin: 6pt 0 5pt; font-size: 27pt; font-weight: 800; letter-spacing: -0.6pt; color: {INK_900}; line-height: 1.1; }}
.opener .lede {{ margin: 0; font-size: 11pt; color: {INK_600}; max-width: 125mm; }}
.opener .source {{ margin-top: 8pt; font-size: 8pt; color: {INK_500}; }}
.opener::after {{ content: ""; position: absolute; left: 0; bottom: -1px; width: 38mm; height: 3px; background: {BRAND}; }}

/* ── headings ───────────────────────────────────── */
h1, h2, h3, h4, h5, h6 {{ break-after: avoid; color: {INK_900}; }}
.doc h1 {{ font-size: 16pt; font-weight: 800; margin: 18pt 0 8pt; }}
.doc h2 {{ font-size: 14pt; font-weight: 700; color: {BRAND}; margin: 20pt 0 7pt; letter-spacing: -0.2pt;
           padding-bottom: 4pt; border-bottom: 1px solid {BRAND_BORDER}; }}
.doc h3 {{ font-size: 11.5pt; font-weight: 700; margin: 15pt 0 5pt; }}
.doc h4 {{ font-size: 10pt; font-weight: 700; margin: 16pt 0 6pt; padding: 6pt 10pt; border-radius: 6pt;
           background: {BRAND_TINT}; border-left: 3pt solid {BRAND}; break-inside: avoid; }}
.doc h5, .doc h6 {{ font-size: 9.4pt; font-weight: 700; margin: 10pt 0 4pt; color: {INK_800}; }}

/* ── lists, quotes, rules ───────────────────────── */
ul, ol {{ margin: 0 0 8pt; padding-left: 15pt; }}
li {{ margin: 1.5pt 0; }}
li::marker {{ color: {BRAND}; }}
blockquote {{ margin: 8pt 0; padding: 7pt 12pt; background: {BRAND_TINT}; border-left: 3pt solid {BRAND};
              border-radius: 0 6pt 6pt 0; color: {INK_800}; }}
blockquote p:last-child {{ margin: 0; }}
hr {{ border: 0; border-top: 1px solid {LINE}; margin: 14pt 0; }}

/* ── tables ─────────────────────────────────────── */
table {{ width: 100%; margin: 8pt 0 12pt; border-collapse: separate; border-spacing: 0; font-size: 8.2pt;
         line-height: 1.45; border: 1px solid {LINE}; border-radius: 6pt; overflow: hidden; }}
thead th {{ background: {BRAND}; color: #fff; font-weight: 700; text-align: left; padding: 5pt 7pt;
            letter-spacing: 0.2pt; }}
td {{ padding: 4.5pt 7pt; vertical-align: top; border-top: 1px solid {LINE}; word-break: break-word; }}
tbody tr:nth-child(even) td {{ background: {WARM}; }}
td.nw {{ white-space: nowrap; word-break: normal; }}
tr {{ break-inside: avoid; }}
thead {{ display: table-header-group; }}

/* ── code, gherkin ──────────────────────────────── */
code {{ font: 8.2pt/1.5 "SF Mono", Menlo, Consolas, monospace; background: {WARM}; color: {INK_900};
        padding: 0.5pt 3pt; border-radius: 3pt; }}
pre {{ margin: 8pt 0 12pt; padding: 9pt 11pt; background: {WARM}; border: 1px solid {LINE};
       border-left: 3pt solid {BRAND}; border-radius: 0 6pt 6pt 0; white-space: pre-wrap; word-break: break-word; }}
pre code {{ background: none; padding: 0; font-size: 7.9pt; color: {INK_800}; }}
.gk-kw {{ color: {BRAND}; font-weight: 700; }}
.gk-head {{ color: {INK_900}; font-weight: 700; }}
.gk-tag {{ color: #8A5CF6; }}
.gk-str {{ color: #0F7B5F; }}

/* ── diagrams ───────────────────────────────────── */
figure.diagram {{ margin: 10pt 0 14pt; padding: 12pt; border: 1px solid {LINE}; border-radius: 8pt;
                  background: #fff; break-inside: avoid; text-align: center; }}
figure.diagram svg {{ max-width: 100%; height: auto; max-height: 215mm; }}
figure.diagram figcaption {{ margin-top: 8pt; font-size: 7.5pt; letter-spacing: 1.4pt; text-transform: uppercase;
                             color: {INK_500}; }}
.diagram-note {{ color: {INK_500}; font-size: 8pt; margin: 6pt 0 2pt; }}
.doc img {{ display: block; max-width: 100%; max-height: 190mm; margin: 8pt 0 12pt; border: 1px solid {LINE};
            border-radius: 6pt; break-inside: avoid; }}
.sw {{ display: inline-block; width: 9pt; height: 9pt; margin-right: 5pt; vertical-align: -1pt;
       border-radius: 2.5pt; border: 1px solid rgba(0,0,0,.12); }}

/* ── contents ───────────────────────────────────── */
.toc {{ position: relative; padding-left: 14pt; }}
.toc::before {{ content: ""; position: absolute; left: 0; top: 2pt; width: 3pt; height: 64pt; background: {BRAND};
                border-radius: 2pt; }}
.toc .eyebrow {{ font-size: 7.5pt; font-weight: 700; letter-spacing: 2.4pt; text-transform: uppercase; color: {BRAND}; }}
.toc .title {{ margin: 6pt 0 20pt; font-size: 26pt; font-weight: 800; letter-spacing: -0.6pt; color: {INK_900}; }}
.toc ol {{ list-style: none; margin: 0; padding: 0; }}
.toc li {{ margin: 0; }}
.toc a {{ display: flex; align-items: baseline; color: {INK_800}; padding: 2.6pt 0; }}
.toc .lvl1 > a {{ margin-top: 11pt; padding: 4pt 0; font-size: 11pt; font-weight: 700; color: {INK_900}; }}
.toc .lvl1 .n {{ display: inline-block; min-width: 20pt; color: {BRAND}; font-weight: 800; }}
.toc .lvl2 > a {{ padding-left: 20pt; font-size: 9pt; }}
.toc .lvl3 > a {{ padding-left: 34pt; font-size: 8.4pt; color: {INK_600}; }}
.toc .t {{ flex: 0 1 auto; max-width: 140mm; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }}
.toc .dots {{ flex: 1 1 auto; margin: 0 6pt; border-bottom: 1px dotted {BRAND_BORDER}; transform: translateY(-3pt); }}
.toc .p {{ flex: 0 0 auto; min-width: 18pt; text-align: right; color: {BRAND}; font-weight: 700;
           font-variant-numeric: tabular-nums; }}
"""


def _cover_css(t: dict[str, str]) -> str:
    BRAND, BRAND_DARK, FONT = t["brand"], t["dark"], t["font"]
    return f"""
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ margin: 0; font-family: {FONT}Manrope, "Helvetica Neue", Arial, sans-serif; }}
.cover {{ position: relative; width: 210mm; height: 297mm; overflow: hidden; color: #fff;
          background: radial-gradient(120% 90% at 85% 10%, {t["light"]} 0%, {BRAND} 42%, {BRAND_DARK} 100%); }}
.ring {{ position: absolute; border-radius: 50%; border: 1px solid rgba(255,255,255,.14); }}
.r1 {{ width: 170mm; height: 170mm; right: -62mm; top: -48mm; }}
.r2 {{ width: 120mm; height: 120mm; right: -37mm; top: -23mm; border-color: rgba(255,255,255,.10); }}
.r3 {{ width: 70mm; height: 70mm; right: -12mm; top: 2mm; background: rgba(255,255,255,.05); border: 0; }}
.top {{ position: absolute; left: 22mm; top: 22mm; font-size: 8pt; font-weight: 700; letter-spacing: 3pt;
        text-transform: uppercase; color: rgba(255,255,255,.78); }}
.main {{ position: absolute; left: 22mm; right: 22mm; top: 88mm; }}
.eyebrow {{ font-size: 9pt; font-weight: 700; letter-spacing: 3.2pt; text-transform: uppercase; color: {t["eyebrow"]}; }}
.bar {{ width: 22mm; height: 3px; background: #fff; margin: 10pt 0 16pt; border-radius: 2px; }}
h1 {{ margin: 0; font-size: 40pt; line-height: 1.05; font-weight: 800; letter-spacing: -1.2pt; }}
.sub {{ margin: 12pt 0 0; font-size: 13pt; line-height: 1.5; color: rgba(255,255,255,.86); max-width: 140mm; }}
.stats {{ position: absolute; left: 22mm; right: 22mm; top: 176mm; display: grid;
          grid-template-columns: repeat(4, 1fr); gap: 7pt; }}
.stat {{ padding: 11pt 12pt; border-radius: 10pt; background: rgba(255,255,255,.09);
         border: 1px solid rgba(255,255,255,.16); }}
.stat b {{ display: block; font-size: 22pt; font-weight: 800; letter-spacing: -0.6pt; line-height: 1.05; }}
.stat span {{ font-size: 7.6pt; font-weight: 600; letter-spacing: 1.2pt; text-transform: uppercase;
              color: rgba(255,255,255,.72); }}
.foot {{ position: absolute; left: 22mm; right: 22mm; bottom: 20mm; display: flex; justify-content: space-between;
         padding-top: 10pt; border-top: 1px solid rgba(255,255,255,.22); font-size: 8.5pt; color: rgba(255,255,255,.78); }}
.foot b {{ color: #fff; font-weight: 700; }}
"""


def _markdown() -> Any:
    from markdown_it import MarkdownIt

    # html=False: agent-written Markdown is data, never markup injected into the page.
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    default_fence = md.renderer.rules["fence"]

    def fence(tokens, idx, options, env):  # noqa: ANN001 — markdown-it renderer signature
        lang = tokens[idx].info.strip().lower()
        if lang == "mermaid":
            # Drawn in the page by _DRAW_DIAGRAMS; the escaped source is its input.
            return f'<pre class="mermaid-src">{html.escape(tokens[idx].content)}</pre>'
        if lang in ("gherkin", "feature", "cucumber"):
            return f"<pre><code>{_gherkin(tokens[idx].content)}</code></pre>"
        return default_fence(tokens, idx, options, env)

    md.renderer.rules["fence"] = fence
    return md


_GK_HEAD = re.compile(
    r"^(\s*)(Feature|Background|Scenario Outline|Scenario Template|Scenario|Rule|Examples|Scenarios):"
)
_GK_STEP = re.compile(r"^(\s*)(Given|When|Then|And|But)\b")


def _gherkin(source: str) -> str:
    """Escaped Gherkin with its keywords, tags and quoted values marked for colour."""
    out = []
    for line in html.escape(source).splitlines():
        line = re.sub(r"(&quot;[^&]*?&quot;)", r'<span class="gk-str">\1</span>', line)
        if line.lstrip().startswith("@"):
            line = re.sub(r"(@[\w.-]+)", r'<span class="gk-tag">\1</span>', line)
        line = _GK_HEAD.sub(r'\1<span class="gk-head">\2:</span>', line)
        line = _GK_STEP.sub(r'\1<span class="gk-kw">\2</span>', line)
        out.append(line)
    return "\n".join(out) + "\n"


_HEADING = re.compile(r"<h([1-6])>(.*?)</h\1>", re.S)
_SHORT_CELL = re.compile(r"<td>([^<\s]{1,18})</td>")
_CELL = re.compile(r"(<td[^>]*>)(.*?)(</td>)", re.S)
_HEX_COLOR = re.compile(r"(?<![&\w])#([0-9A-Fa-f]{6})\b")
_IMG = re.compile(r'(<img src=")([^"]+)(")')


def _strip_tags(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _chapter(
    index: int, name: str, title: str, lede: str, text: str, md: Any, embed: Any = None
) -> tuple[str, list[tuple]]:
    """One chapter's HTML and its contents entries ``(level, anchor, title)``.

    The document's own first ``# heading`` becomes the opener's source line; the
    chapter title is the one ``PDF_SECTIONS`` gives, so every chapter reads the same."""
    rendered = md.render(text)
    first = re.match(r"\s*<h1>(.*?)</h1>", rendered, re.S)
    source = _strip_tags(first.group(1)) if first else ""
    if first:
        rendered = rendered[first.end() :]
    levels = _TOC_LEVELS.get(name, _TOC_DEFAULT_LEVELS)
    entries: list[tuple] = [(1, name, title)]
    count = 0

    def anchor(m: re.Match) -> str:
        nonlocal count
        level = int(m.group(1))
        count += 1
        hid = f"{name}-{count}"
        if level in levels:
            entries.append((level, hid, _strip_tags(m.group(2))))
        return f'<h{level} id="{hid}">{m.group(2)}</h{level}>'

    rendered = _HEADING.sub(anchor, rendered)
    # A short one-word cell (an id, a pattern name) stays on one line; wrapping
    # "REQ-23a-012" over three lines to widen a prose column reads as broken.
    rendered = _SHORT_CELL.sub(r'<td class="nw">\1</td>', rendered)
    # A colour in a table gets its swatch; an image path under build/ui/ is embedded.
    rendered = _CELL.sub(
        lambda m: m.group(1)
        + _HEX_COLOR.sub(
            r'<span class="sw" style="background:#\1"></span>#\1', m.group(2)
        )
        + m.group(3),
        rendered,
    )
    if embed is not None:
        rendered = _IMG.sub(
            lambda m: m.group(1) + embed(html.unescape(m.group(2))) + m.group(3),
            rendered,
        )
    opener = (
        f'<header class="opener"><div class="num">{index:02d}</div>'
        f'<div class="eyebrow">Chapter {index:02d}</div><h1>{html.escape(title)}</h1>'
        f'<p class="lede">{html.escape(lede)}</p>'
        + (
            f'<div class="source">{html.escape(source)} · {html.escape(name)}</div>'
            if source
            else ""
        )
        + "</header>"
    )
    return (
        f'<section class="chapter" id="{name}">{opener}<div class="doc">{rendered}</div></section>',
        entries,
    )


def _toc(entries: list[tuple], pages: dict[str, int] | None) -> str:
    rows, chapter = [], 0
    for level, hid, title in entries:
        page = str(pages.get(hid, "")) if pages is not None else "000"
        label = html.escape(title)
        if level == 1:
            chapter += 1
            label = f'<span class="n">{chapter:02d}</span>{label}'
        rows.append(
            f'<li class="lvl{level}"><a href="#{hid}"><span class="t">{label}</span>'
            f'<span class="dots"></span><span class="p">{page}</span></a></li>'
        )
    return (
        '<nav class="toc"><div class="eyebrow">Contents</div><div class="title">Table of contents</div>'
        f'<ol>{"".join(rows)}</ol></nav>'
    )


def _sections(sandbox: Any) -> list[tuple[str, str, str, str]]:
    present = [
        (name, title, lede, sandbox.read(name)) for name, title, lede in PDF_SECTIONS
    ]
    return [p for p in present if p[3]]


def build_html(
    sandbox: Any, pages: dict[str, int] | None = None
) -> tuple[str, list[tuple]]:
    """The body (contents + chapters) as one HTML page, and its contents entries.

    ``pages`` maps an entry's anchor to its printed page number; ``None`` prints a
    fixed-width placeholder so the first (measuring) pass paginates like the second."""
    md = _markdown()

    def embed(src: str) -> str:
        """A screenshot the UI/UX step placed by path, as a data URI; anything else
        (a remote URL, a path outside build/ui/) stays as written."""
        rel = src.lstrip("/")
        if not rel.startswith("build/ui/") or not rel.endswith(".png"):
            return html.escape(src)
        try:
            data = sandbox.path_for(rel).read_bytes()
        except (OSError, ValueError):
            return html.escape(src)
        return "data:image/png;base64," + base64.b64encode(data).decode()

    chapters, entries = [], []
    for i, (name, title, lede, text) in enumerate(_sections(sandbox), start=1):
        body, found = _chapter(i, name, title, lede, text, md, embed)
        chapters.append(body)
        entries.extend(found)
    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Backlog</title>'
        f"<style>{_font_faces()}{_css(_theme(sandbox))}</style></head><body>"
        f"{_toc(entries, pages)}{''.join(chapters)}</body></html>"
    )
    return page, entries


def _stats(sandbox: Any) -> tuple[str, list[tuple[str, int]]]:
    """The product name and the headline numbers, from ``backlog.json``."""
    try:
        data = json.loads(sandbox.read("backlog.json") or "{}")
    except ValueError:
        data = {}
    backlog, solution, stories = (
        data.get("backlog") or {},
        data.get("solution") or {},
        data.get("stories") or [],
    )

    def n(value: Any) -> int:
        return len(value) if isinstance(value, (list, dict)) else int(value or 0)

    points = sum(
        int(s.get("points") or 0)
        for s in stories
        if isinstance(s, dict) and str(s.get("points") or "0").isdigit()
    )
    stats = [
        ("Features", n(backlog.get("features"))),
        ("Epics", n(backlog.get("epics"))),
        ("User stories", len(stories)),
        (
            "Requirements",
            sum(
                len(s.get("requirements") or []) for s in stories if isinstance(s, dict)
            ),
        ),
        ("Story points", points),
        ("Endpoints", n(solution.get("endpoints"))),
        ("Screens", n(solution.get("screens"))),
        ("Entities", n(solution.get("entities"))),
    ]
    return str(backlog.get("product") or "Product backlog"), [s for s in stats if s[1]][
        :8
    ]


def build_cover(sandbox: Any, today: _dt.date | None = None) -> str:
    product, stats = _stats(sandbox)
    today = today or _dt.date.today()
    cells = "".join(
        f'<div class="stat"><b>{v:,}</b><span>{html.escape(k)}</span></div>'
        for k, v in stats
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<style>{_font_faces()}{_cover_css(_theme(sandbox))}</style></head><body><div class=\"cover\">"
        '<div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div>'
        '<div class="top">VelocityAI · Delivery pack</div>'
        '<div class="main"><div class="eyebrow">Product backlog</div><div class="bar"></div>'
        f"<h1>{html.escape(product)}</h1>"
        '<p class="sub">Solution, architecture, data model, API, integrations, screens and every '
        "user story with its acceptance criteria — in one document.</p></div>"
        f'<div class="stats">{cells}</div>'
        f'<div class="foot"><span><b>{today.strftime("%B")} {today.day}, {today.year}</b></span>'
        "<span>Generated by <b>VelocityAI</b></span></div>"
        "</div></body></html>"
    )


# Replaces every mermaid-src block with its drawn SVG in a captioned figure. A block
# that does not parse keeps its source under a note. Returns [drawn, failed].
_DRAW_DIAGRAMS = """async (theme) => {
  mermaid.initialize({startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables: theme,
                      flowchart: {htmlLabels: false}, fontFamily: "Manrope, Helvetica, Arial, sans-serif"});
  let drawn = 0, failed = 0, n = 0;
  for (const pre of document.querySelectorAll("pre.mermaid-src")) {
    const id = "diagram-" + (n++);
    try {
      const {svg} = await mermaid.render(id, pre.textContent.trim());
      const fig = document.createElement("figure");
      fig.className = "diagram";
      fig.innerHTML = svg + "<figcaption>Figure " + (drawn + 1) + "</figcaption>";
      pre.replaceWith(fig);
      drawn++;
    } catch (e) {
      document.getElementById("d" + id)?.remove();
      document.getElementById(id)?.remove();
      pre.insertAdjacentHTML("beforebegin",
        '<p class="diagram-note">Diagram could not be drawn — its source:</p>');
      failed++;
    }
  }
  return [drawn, failed];
}"""


def _mermaid_theme(t: dict[str, str]) -> dict[str, str]:
    return {
        "primaryColor": t["fill"],
        "primaryBorderColor": t["brand"],
        "primaryTextColor": INK_900,
        "secondaryColor": t["tint"],
        "tertiaryColor": WARM,
        "lineColor": INK_500,
        "textColor": INK_800,
        "mainBkg": t["fill"],
        "nodeBorder": t["brand"],
        "clusterBkg": t["tint"],
        "clusterBorder": t["border"],
        "actorBkg": t["fill"],
        "actorBorder": t["brand"],
        "signalColor": INK_600,
        "noteBkgColor": "#FFF8E1",
        "fontFamily": f"{t['font']}Manrope, Helvetica, Arial, sans-serif",
        "fontSize": "13px",
    }


_FOOTER = (
    '<div style="width:100%;margin:0 17mm;padding-top:5px;border-top:0.5px solid #E6E3DB;display:flex;'
    'justify-content:space-between;font:8px Helvetica,Arial,sans-serif;color:#8A8B82">'
    "<span>{product} · Product backlog</span>"
    '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
)


async def _print(
    browser: Any, page_html: str, *, footer: str | None, theme: dict[str, str] | None
) -> bytes:
    page = await browser.new_page()
    try:
        await page.set_content(page_html, wait_until="load", timeout=180_000)
        await page.evaluate("document.fonts.ready")
        if theme is not None and "mermaid-src" in page_html:
            await page.add_script_tag(path=str(MERMAID_JS))
            drawn, failed = await page.evaluate(_DRAW_DIAGRAMS, _mermaid_theme(theme))
            logger.info("backlog_export: diagrams drawn=%s failed=%s", drawn, failed)
        options: dict[str, Any] = {
            "format": "A4",
            "print_background": True,
            "prefer_css_page_size": True,
            "outline": True,
            "tagged": True,
        }
        if footer:
            options.update(
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=footer,
            )
        return await page.pdf(**options)
    finally:
        await page.close()


def _outline_pages(pdf: bytes, entries: list[tuple]) -> dict[str, int]:
    """Anchor → printed page, read from the outline Chromium built from the headings.

    Walked in order and matched by title, so two chapters' same-named headings (both
    "Overview") land on their own pages. An entry never matched is left unnumbered."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf))
    flat: list[tuple[str, int]] = []

    def walk(items: Any) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                flat.append(
                    (
                        " ".join(str(item.title).split()),
                        reader.get_destination_page_number(item) + 1,
                    )
                )

    walk(reader.outline)
    pages: dict[str, int] = {}
    cursor = 0
    for _level, hid, title in entries:
        want = " ".join(title.split())
        for i in range(cursor, len(flat)):
            if flat[i][0] == want:
                pages[hid], cursor = flat[i][1], i + 1
                break
    return pages


def _merge(cover: bytes, body: bytes, product: str) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(cover)), import_outline=False)
    writer.append(PdfReader(io.BytesIO(body)))
    writer.add_metadata(
        {
            "/Title": f"{product} — Product backlog",
            "/Author": "VelocityAI",
            "/Creator": "VelocityAI backlog workflow",
        }
    )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


async def render_pdf(sandbox: Any) -> bytes:
    """Cover + contents + chapters, printed by headless Chromium (the same Playwright
    the render check uses). Raises when no browser can launch; the caller degrades."""
    from playwright.async_api import async_playwright

    product, _ = _stats(sandbox)
    theme = _theme(sandbox)
    footer = _FOOTER.format(product=html.escape(product))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        try:
            first_html, entries = build_html(sandbox)
            first = await _print(browser, first_html, footer=footer, theme=theme)
            body_html, _ = build_html(sandbox, _outline_pages(first, entries))
            body = await _print(browser, body_html, footer=footer, theme=theme)
            cover = await _print(browser, build_cover(sandbox), footer=None, theme=None)
        finally:
            await browser.close()
    return _merge(cover, body, product)


def build_zip(sandbox: Any, pdf: bytes | None) -> bytes:
    """Every deliverable present on disk, each as its own entry, plus Backlog.pdf."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in DELIVERABLES:
            text = sandbox.read(name)
            if text is not None:
                zf.writestr(name, text)
        if pdf is not None:
            zf.writestr(PDF_NAME, pdf)
    return buf.getvalue()


def _keep_out_of_history(sandbox: Any, names: tuple[str, ...]) -> None:
    """Add ``/<name>`` to the sandbox ``.gitignore`` for each packaged binary.

    The run-history commit's binary scan refuses a PDF, and both files are rebuilt
    from the committed documents by every final assembly — so they stay out of git."""
    path = sandbox.path_for(".gitignore")
    lines = path.read_text().splitlines() if path.exists() else []
    missing = [f"/{n}" for n in names if f"/{n}" not in lines]
    if missing:
        path.write_text("\n".join(lines + missing) + "\n")


async def export_backlog(sandbox: Any) -> str:
    """Write Backlog.pdf and Backlog.zip into the sandbox root; return a one-line note.

    Never raises: packaging is a convenience on top of files already written, and a
    missing browser must not fail a backlog that assembled."""
    pdf: bytes | None = None
    note = ""
    try:
        _keep_out_of_history(sandbox, (PDF_NAME, ZIP_NAME))
    except Exception as exc:  # noqa: BLE001 — the commit scan then names them instead
        logger.warning("backlog_export: .gitignore not updated (%s)", exc)
    try:
        pdf = await render_pdf(sandbox)
        sandbox.path_for(PDF_NAME).write_bytes(pdf)
    except Exception as exc:  # noqa: BLE001 — degrade to a zip without the PDF
        logger.warning("backlog_export: %s not written (%s)", PDF_NAME, exc)
        note = f" {PDF_NAME} not written: {exc}."
    try:
        sandbox.path_for(ZIP_NAME).write_bytes(build_zip(sandbox, pdf))
    except Exception as exc:  # noqa: BLE001
        logger.warning("backlog_export: %s not written (%s)", ZIP_NAME, exc)
        return f"Export failed: {exc}."
    written = f"{PDF_NAME} and {ZIP_NAME}" if pdf is not None else ZIP_NAME
    return f"Wrote {written}.{note}"

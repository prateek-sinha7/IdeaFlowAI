---
name: doc-kami-parchment
zh_name: "Kami Parchment Document"
en_name: "Kami Parchment Document"
emoji: "📜"
description: "Warm parchment background (#f5f4ed) + ink-blue monochrome accent (#1B365D) + single serif typeface, editorial-grade typesetting"
category: doc
scenario: personal
aspect_hint: "A4 / Letter long page"
featured: 48
recommended: 3
tags: ["kami", "parchment", "serif", "editorial", "report", "letter", "one-pager"]
example_id: sample-kami-parchment
example_name: "Kami Parchment · One-Pager"
example_format: markdown
example_tagline: "Warm parchment + ink-blue monochrome + single serif"
example_desc: "A one-page Open Design Studio Issue No. 26 editorial-grade one-pager"
example_source_url: "https://github.com/tw93/kami"
example_source_label: "tw93/kami"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: personal
  featured: 0.04
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the \"Kami Parchment Document\" template to turn my content into a piece with a \"warm parchment background (#f5f4ed) + ink-blue monochrome accent (#1B365D) + single serif typeface, editorial-grade typesetting\". Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Kami Parchment Document]
[Intent] Serious editorial documents: one-pagers / long reports / letters / resumes / financial reports / changelogs / portfolios. Inspired by tw93/kami. Emphasizes "written like a page that's been typeset," not a dashboard, not a webpage.

[Hard visual signature -- do not change]
- **Canvas**: warm parchment `#f5f4ed` (never pure white `#fff`). Secondary background `#efeee5`.
- **Ink color**: primary text `#1f1d18` (near-black warm gray, not pure black `#000`). Secondary text `#6b665b`.
- **Sole accent color**: ink blue `#1B365D` -- every accent (links, tag outlines, emphasized numbers, blockquote left rule) may only use this one color; multiple accent colors are strictly forbidden.
- **Typography**: one serif per language, never mixed within a document:
  - English: `Charter` (fallback: `Source Serif Pro`, `Iowan Old Style`)
  - Chinese: `TsangerJinKai02 W04` (fallback: `Noto Serif SC`)
  - Japanese: `YuMincho` (fallback: `Noto Serif JP`)
  - Body 400, Heading 500 (no 700/800/900).
- **Line height**: headings 1.1-1.3, tight body copy 1.4-1.45, reading body copy 1.5-1.55.
- **Never**: drop-shadow / blur / border-radius >= 8px / gradients / neon colors / rgba (use solid hex).
- **Detail**: tags use solid hex background blocks (because WeasyPrint doesn't render rgba well); single-line geometric icons; edge 1px hairline `#d4d1c5` rule, length controlled so it doesn't touch the edge.

[Optional document types -- choose based on user content]
- **One-Pager** -- top logotype (Charter italic) + headline + lede + 3-column key points + footer metadata.
- **Long Doc** -- cover page (large title + subtitle + author + date) -> table of contents (kicker + page no.) -> chapters (folio corner mark + section rule + body) -> annotation footnotes + closing colophon.
- **Letter** -- letterhead address + date + recipient + body (left-aligned, 1.5em paragraph spacing) + signature line + signature placeholder.
- **Portfolio** -- project hero (large title + subtitle) + 1 full-width image (drawn as a CSS-block placeholder) + project description + role / timeframe / stack metadata row.
- **Resume** -- name at top (large type) + one-line tagline + contact row + main sections: experience (company / dates / title / bullets) + skills + education.
- **Slides** -- keynote style, page count determined by [user content] (short content starts at 6 pages, longer content should have more), each page fills the parchment canvas, large title + lede + corner page no., kept minimal enough to feel "printed."
- **Equity Report** -- company name + ticker + quarter x year + key metrics row (revenue / margin / yoy) + analysis body + chart (single-color SVG line chart).
- **Changelog** -- version number (large Charter italic) + date + change list (Added / Changed / Fixed), separated by a single rule.

[Design principles]
- "Composed pages, not dashboards." Don't stack KPI cards, don't stack emoji icons, don't use hero gradients.
- "Ring or whisper only, no hard drop shadows." Shadows may only be a hairline outline like `0 0 0 1px #d4d1c5`.
- Text hierarchy relies on **serif contrast + type size + whitespace**, not color.
- Single-file HTML, Tailwind CDN; when mixing languages in the same line, add proper spacing between scripts; no externally linked images -- use paper-tint color blocks with a 1px ink outline as placeholders.

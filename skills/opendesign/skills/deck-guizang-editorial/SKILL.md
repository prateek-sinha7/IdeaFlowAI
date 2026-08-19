---
name: deck-guizang-editorial
zh_name: "Guizang Editorial E-Ink Deck"
en_name: "Guizang Editorial E-Ink Deck"
emoji: "🖋️"
description: "Digital magazine × e-ink; 10 layouts + 5 palettes (Ink Classic/Indigo Porcelain/Forest Ink/Kraft Paper/Dune)"
category: slides
scenario: marketing
aspect_hint: "16:9 landscape, page-turn"
featured: 49
recommended: 1
tags: ["editorial", "e-ink", "magazine", "narrative", "guizang"]
example_id: sample-guizang-editorial
example_name: "Guizang Editorial E-Ink · Act Divider"
example_format: markdown
example_tagline: "Ink Classic palette + serif display"
example_desc: "L02 Act Divider chapter page + L03 Big Numbers Grid data cells, paper-print feel"
example_source_url: "https://github.com/op7418/guizang-ppt-skill"
example_source_label: "op7418/guizang-ppt-skill"
od:
  mode: deck
  surface: web
  scenario: marketing
  featured: 0.01
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Guizang Editorial E-Ink Deck' template to turn my content into a 'digital magazine × e-ink; 10 layouts + 5 palettes (Ink Classic/Indigo Porcelain/Forest Ink/Kraft Paper/Dune)' deck. Keep the template's visual signature, use real content and data, avoid lorem ipsum and placeholder images."
---

[Template: Guizang Editorial E-Ink Deck (Editorial × E-Ink)]
[Intent]Narrative, opinion, sharing, personal-voice expression. Ink-on-paper print feel, not techy. Inspired by op7418/guizang-ppt-skill Style A.

[Palette — pick 1 of 5, hex values must not change, never mix]
- 🖋 **Ink Classic Monocle** — ink `#0a0a0b`, paper `#f1efea`, paper-tint `#e8e5de`, ink-tint `#18181a`. Default / general business / tech.
- 🌊 **Indigo Porcelain** — ink `#0a1f3d`, paper `#f1f3f5`, paper-tint `#e4e8ec`, ink-tint `#152a4a`. Tech / research / data.
- 🌿 **Forest Ink** — ink `#1a2e1f`, paper `#f5f1e8`, paper-tint `#ece7da`, ink-tint `#253d2c`. Nature / sustainability / culture.
- 🍂 **Kraft Paper** — ink `#2a1e13`, paper `#eedfc7`, paper-tint `#e0d0b6`, ink-tint `#3a2a1d`. Nostalgic / humanities / literature.
- 🌙 **Dune** — ink `#1f1a14`, paper `#f0e6d2`, paper-tint `#e3d7bf`, ink-tint `#2d2620`. Art / design / fashion.

[Layout — 10 reusable tape-style layout pool; **quantity is decided by the [User Content]**, cover every point completely; short content starts at 6-12 slides, long content should have more (the same layout can repeat across different chapters)]
- **L01 Hero Cover** — centered large hero typography + kicker + subtitle + lead paragraph + bottom metadata row.
- **L02 Act Divider** — kicker + 8.5-10vw giant headline + one line of quote; chapter transitions can invert colors (ink ↔ paper).
- **L03 Big Numbers Grid** — 3×2 data cards (label / big number / annotation).
- **L04 Quote + Image** — left kicker + headline + body + callout; right 16:10 image (baseline-aligned, not top-aligned).
- **L05 Image Grid** — 3×2 or 3×1 equal-height image grid (26vh or 22vh); strictly uniform height.
- **L06 Pipeline / Flow** — horizontal numbered step group, each step: №X + title + description; supports step-by-step keyboard advance.
- **L07 Hero Question** — 7vw full-screen single question, line-broken by meaning, minimal surroundings.
- **L08 Big Quote** — 5.8vw giant serif quote + English translation + attribution + date.
- **L09 Before / After** — 1:1 split; left column opacity .55 (old/before); right column full brightness (new/after).
- **L10 Mixed Media** — 8:4 ratio; left large text block (kicker / headline / body / callout) + right 3:4 portrait image as support.

[Design Details]
- **Strictly forbidden**: gradients / drop-shadow / rounded corners / circular decorations / blur / SVG icon libraries / emoji decorations.
- **Fonts**: Display uses `Playfair Display` (Latin) / `Noto Serif SC` (CJK); Body uses `Inter` / `Noto Sans SC`; numbering / digits may occasionally use italic serif.
- **Magazine-feel details**: kicker in 11px uppercase letterspacing 0.12em; folio in bottom-right corner `01 / 12`; top hairline rule + masthead logo / topic.
- **Not allowed**: fabricated data, Lorem ipsum, placeholder image URLs. All images should be rendered purely in CSS / inline SVG (color blocks + simple line drawings).
- Keyboard ← / → to navigate; hash sync; single-file HTML.

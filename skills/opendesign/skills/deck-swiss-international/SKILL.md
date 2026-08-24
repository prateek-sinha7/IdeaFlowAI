---
name: deck-swiss-international
zh_name: "Swiss International Deck"
en_name: "Swiss International Deck"
emoji: "🟦"
description: "16-column grid + single saturated accent + 22 locked layouts (Klein Blue / Lemon / Mint / Safety Orange)"
category: slides
scenario: marketing
aspect_hint: "16:9 landscape, page-by-page"
featured: 1
recommended: 1
tags: ["swiss", "grid", "international", "ikb", "editorial", "facts"]
example_id: sample-swiss-international
example_name: "Swiss International · Product Roadmap"
example_format: markdown
example_tagline: "Klein Blue IKB + 16-column grid"
example_desc: "Two-page preview of S01 Cover + S06 KPI Tower, IKB full-bleed title + 4-bar KPI"
example_source_url: "https://github.com/op7418/guizang-ppt-skill"
example_source_label: "op7418/guizang-ppt-skill"
od:
  mode: deck
  surface: web
  scenario: marketing
  featured: 0.001
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Swiss International Deck' template to turn my content into a set with a '16-column grid + single saturated accent + 22 locked layouts (Klein Blue / Lemon / Mint / Safety Orange)'. Preserve the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Swiss International Deck]
[Intent] Expression for facts, products, analysis, and methodology. Extremely cool, rational, academic — no hand-drawn elements / noise / decoration. Inspired by op7418/guizang-ppt-skill Style B.

[Theme] **Pick exactly one of the 4 sets below — never mix them, never change the hex values**:
- 🔵 **Klein Blue (IKB)** — accent `#002FA7`, paper `#fafaf8`, ink `#0a0a0a`. Business / AI / design scenarios.
- 🟡 **Lemon Yellow** — accent `#FFD500`, paper `#f7f5ee` (pale cream), ink `#0a0a0a`. Youth / retail / sports. Text must be black (never white).
- 🟢 **Lemon Green / Neon** — accent `#C5E803`, paper `#f7f5ee`, ink `#0a0a0a`. Sustainability / tech startups / Gen-Z brands. Text must be black.
- 🟠 **Safety Orange** — accent `#FF6B35`, paper `#f7f5ee`, ink `#0a0a0a`. Industrial / automotive / urgent messaging. Text in white + bold ≥ 600.

[Layout — a pool of 22 reusable layouts; no new layouts and no reworking existing ones; **the slide count is driven by content**, cover the [user content] fully (short content starts at 6-10 slides; long content should go well beyond that; the same layout can repeat across different sections)]
- **S01 Cover** — full-bleed accent + breathing ASCII dot matrix + reversed-out title + metadata chrome (date / № / topic).
- **S02 Vertical Timeline** — dashed axis with dots on the left; nodes on the right = year + KPI + description.
- **S03 Statement** — 9.6vw centered giant text + large whitespace block on the left + bottom hairline + annotation.
- **S04 Six Cells** — 2×3 grid, each cell: icon + number + short title + single-line description.
- **S05 Three Sub-cards** — hero title on the left + 3 horizontally stacked gray cards on the right.
- **S06 KPI Tower** — 4 columns of varying-height blue bars; icon at bar top; large number + label at bar base.
- **S07 H-Bar Chart** — horizontal ranking bars, width reflects data, numbers labeled at the end.
- **S08 Duo Compare** — vertical divider line; Before on the left / After on the right.
- **S09 Closing Manifesto** — IKB block + ASCII dot matrix + manifesto on the left; white background + 3 key points on the right.
- **S10 Dot Matrix Statement** — centered manifesto + geometric dot matrix / ring matrix in the corner.
- **S11 Horizontal Timeline** — headline at top, hairline axis in the middle, evenly spaced nodes, step names below nodes.
- **S12 Manifesto + Ink Banner** — headline + explanation on top half; full-width black banner + reversed-out small text on bottom half.
- **S13 Three Forces Cards** — ink hero block on the left; 3 gray cards on the right, each card: large number + text.
- **S14 Loop Diagram** — numbered steps on the left; concentric SVG rings on the right; "LOOP" label at center.
- **S15 Image Matrix + Hero Stat** — 4×3 equal-height cards (12 items) + summary large number + label at the bottom.
- **S16 Multi-card Brief** — 3×2 micro-cards; main text top-left, footnote bottom-right, single card with accent highlight.
- **S17 System Diagram** — headline + 3 description paragraphs on the left; 3 concentric SVG circles + external labels on the right.
- **S18 Why Now** — 3 columns, each: category label + headline + description + number at the bottom (last column in accent color).
- **S19 Four Cards** — accent hairline + headline at top + 4 equal-width cards (metadata / title / body) below.
- **S20 Stacked KPI Ledger** — vertical rows + hairline dividers; large number on the left / label in the middle / icon on the right.
- **S21 Tech Spec Sheet** — title block on the left / 3 KPI hairlines in the middle / varying-height bars on the right / data at the bottom.
- **S22 Image Hero** — full-width image on top 60% + white title block overlay; explanation + 3-column KPI on bottom 40%.

[Design details — absolute rules]
- **Right angles only**: `border-radius: 0` throughout. Rounded corners = immediate violation.
- **1px hairline borders**, black or accent; shadows / gradients / blur are strictly forbidden.
- **16-column grid**: `grid-template-columns: repeat(16, 1fr); gap: 0`.
- **Fonts**: Inter Tight (Latin display) / Inter (body) / Noto Sans SC (CJK text) / JetBrains Mono (data); serif and decorative fonts are strictly forbidden.
- **Extreme size contrast**: 9.6vw display for cover, 14-16px body, 11px uppercase label with letterspacing 0.08em.
- **Keyboard ← / → navigation + hash sync**; fixed corner markers: `№N/N` bottom-right, topic label bottom-left.
- **No fabrication**: numbers must come from user input; chart bar heights = real data, proportionally scaled.
- Output a single HTML file, no external image URLs; decorative geometry (ASCII matrix / concentric circles) done with pure CSS or inline SVG.

---
name: deck-open-slide-canvas
zh_name: "Open-Slide 1920 Canvas Deck"
en_name: "Open-Slide 1920 Canvas Deck"
emoji: "🎨"
description: "Fixed 1920×1080 canvas, free composition at the React-component level, not tied to a template"
category: slides
scenario: design
aspect_hint: "1920×1080 (16:9)"
featured: 35
recommended: 9
tags: ["canvas", "open-slide", "freeform", "1920", "react"]
example_id: sample-deck-open-slide-canvas
example_name: "1920 Freeform Canvas · Sea Indigo"
example_format: markdown
example_tagline: "Fixed 1920×1080 + free composition"
example_desc: "Sea Indigo palette + a single large-type question slide with corner labels"
example_source_url: "https://github.com/1weiho/open-slide"
example_source_label: "1weiho/open-slide"
od:
  mode: deck
  surface: web
  scenario: design
  featured: 0.17
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Open-Slide 1920 Canvas Deck' template to turn my content into a deck with a 'fixed 1920×1080 canvas, free composition at the React-component level, not tied to a template'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Open-Slide 1920 Canvas Deck]
[Intent] For scenarios that don't want to be boxed in by a template (personal portfolios, unconventional talks, art / design-class decks). Provide a fixed 1920×1080 canvas plus very strong typography / palette constraints, and let the agent lay out each slide as freely as writing a React component, based on the content. Inspired by 1weiho/open-slide.

[Hard technical spec]
- Canvas: each slide is strictly `width: 1920px; height: 1080px;`, fitted to the viewport with `transform: scale(...)` (default `scale(0.7)`, centered).
- **Overflow is absolutely forbidden**: every slide's content must fit within 1920×1080 — no scrollbars allowed.
- Type scale (px): `2xs:18 · xs:22 · sm:28 · md:36 · lg:48 · xl:64 · 2xl:88 · 3xl:120 · 4xl:160 · 5xl:220`.
- Padding: pick one of three tiers — 96 / 128 / 160.
- Each slide has `<section class="slide" data-slide-id="<n>">`.

[Palette — pick 1 per deck, keep it consistent throughout]
- 🌫 **Ash & Lime** — bg `#f1efea`, ink `#161616`, accent `#c5e803`.
- 🌌 **Sea Indigo** — bg `#0a0e1a`, ink `#f5f5f7`, accent `#5ac8fa`.
- 🧉 **Mate Mocha** — bg `#1a1411`, ink `#f5e9d6`, accent `#d97757`.
- 🌸 **Pearl Rose** — bg `#fdf6f3`, ink `#1a1015`, accent `#ff5d8f`.

[Layout freedom — this is the core idea]
- No forced template — each slide picks its own layout based on **what the content is**: cover / question / quote / image-text / three-column / five-column / list / data card / full-bleed image.
- But every slide **must follow one rule**: exactly 1 visual hierarchy focus — one punchy line, one number, one image. Don't emphasize everything at once.
- Don't cram in two equally-weighted blocks of text; if you truly need parallel content, use a 3-column grid of equal weight.

[Typography]
- Latin: `Inter Tight` (display) + `Inter` (body); or `Source Serif Pro` for an editorial feel.
- CJK: `Noto Sans SC` (sans style) or `Noto Serif SC` (editorial style); don't mix sans + serif.
- Mono: `JetBrains Mono` for data / timestamps.

[Design details]
- No decorative emoji (emoji within actual content is fine); no multicolor rainbow effects; use only one accent color.
- No generic SVG icon libraries like lucide or feather — write inline SVG by hand.
- Add keyboard ← / → navigation with hash sync; fixed corner labels: bottom-right `№N/M`, bottom-left deck title.
- Must use the user's real content; lorem ipsum is strictly forbidden.
- Single-file HTML; Tailwind CDN; no externally linked images.

---
name: frame-data-chart-nyt
zh_name: "NYT-Style Data Chart Frame"
en_name: "NYT-Style Data Chart Frame"
emoji: "📈"
description: "NYT-newsroom layout + staggered reveal animation + editorial-grade charts (line/bar/range band)"
category: video
scenario: video
aspect_hint: "1920×1080 (16:9)"
featured: 46
tags: ["data", "chart", "nyt", "editorial", "frame"]
example_id: sample-frame-data-chart-nyt
example_name: "NYT-style line chart · global user count"
example_format: markdown
example_tagline: "Editorial-grade chart + staggered reveal"
example_desc: "8-year weekly active user line + NYT red accent + mono annotations"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · data-chart"
od:
  mode: video
  surface: video
  scenario: video
  featured: 46
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'NYT-Style Data Chart Frame' template to turn my content into an 'NYT-newsroom layout + staggered reveal animation + editorial-grade chart (line/bar/range band)'. Keep the template's visual signature, use real content and data, avoid lorem ipsum and placeholder images."
---

[Template: NYT-Style Data Chart Frame]
[Intent]Turn a piece of data (CSV / JSON / a one-line conclusion) into a New-York-Times-column-style single frame / animated chart, suitable for video clips or Twitter cards. Inspired by hyperframes data-chart.

[Canvas]1920×1080, pick either a warm-white background `#f7f5ee` or an ink-black background `#0e0e0e`; text color is the inverse of the background.

[Layout]
- **Top kicker** (11px uppercase letterspace 0.14em, color = accent red `#a91d1d` or mint `#5fb38a`): data source + category, e.g. "GLOBAL · WEEKLY ACTIVE USERS · 2018–2026".
- **Large title** (Cheltenham / Playfair / Source Serif Pro, 5.6vw, optional italic subtitle): one-sentence conclusion. **The conclusion must be distilled from the user's data**, not a description of the chart.
- **Chart area** (55-65% of canvas):
  - Line: 1-2 lines, primary line solid ink 2.5px, secondary line dashed 1.5px; data points as 6px solid circles; annotate key points with small black mono text like `2024 · 412M`.
  - Bar: all ink monochrome, or add 1 accent highlight bar; large number above each bar; italic category label below each bar (Cheltenham italic).
  - Range band: light gray fill `#e6e2d2` envelope + ink center line.
- **Bottom source + footnote** (10px mono, opacity 0.6): "Source: user data · Chart by html-anything".
- **Staggered reveal animation**: title fade-in (0s), kicker (200ms), line stroke-dashoffset 1.2s ease-out (400ms), data labels revealed one by one at 100ms intervals. Can be disabled via `prefers-reduced-motion`.

[Design Details]
- **Never**: use the chart.js / d3 library (unless imported via jsdelivr CDN); hand-written SVG is preferred, no more than 80 inline lines.
- Fonts: title in `Source Serif Pro` or `Cheltenham` (fall back to `Playfair Display`); body in `IBM Plex Sans` or `Inter`; data labels in `IBM Plex Mono`.
- 1 primary color (ink) + 1 accent (pick one of NYT red `#a91d1d` / editorial mint `#5fb38a` / warm orange `#d97757`).
- Y-axis ticks are hairline only, 3-4 ticks, labels outside the axis in mono.
- Strictly forbidden: full-screen grid lines, shadows, 3D bars; strictly forbidden: emoji.
- Must use the data provided by the user. If the input is a text conclusion, auto-estimate reasonable coordinates (but label it "schematic"); if it's CSV/JSON, plot it directly.
- Single-file HTML; annotation format next to data points: `<text class="annot">2024 · 412M</text>`.

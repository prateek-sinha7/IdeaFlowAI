---
name: frame-light-leak-cinema
zh_name: "Light-Leak Cinematic Frame"
en_name: "Light-Leak Cinematic Frame"
emoji: "🎞️"
description: "Film light leak + grain noise + 16:9 letterbox + large serif type, cinematic opener / chapter card"
category: video
scenario: video
aspect_hint: "2.39:1 letterbox (1920×800) or 16:9 (1920×1080)"
featured: 36
tags: ["cinema", "film", "light-leak", "grain", "letterbox", "frame"]
example_id: sample-frame-light-leak-cinema
example_name: "Light Leak · REEL 03"
example_format: markdown
example_tagline: "Warm orange light leak + 35mm grain"
example_desc: "2.39:1 letterbox + large italic serif type + film sprocket holes"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · light-leak"
od:
  mode: video
  surface: video
  scenario: video
  featured: 36
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Light-Leak Cinematic Frame' template to turn my content into a 'film light leak + grain noise + 16:9 letterbox + large serif type, cinematic opener / chapter card'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Light-Leak Cinematic Frame]
[Intent] A single opening frame for a documentary / personal short film / video chapter card — warm orange light leak + 35mm grain + large serif type, classic film texture. Inspired by hyperframes light-leak.

[Canvas]
- **2.39:1 letterbox** (recommended): 1920×800, 140px black bars top and bottom (`#000`).
- Or 16:9: 1920×1080, no letterbox.

[Background]
- Base layer: deep warm color (dark reddish-brown `#1a0d08` / ink green `#0a1410` / blue-violet `#0d0e1a`) or a depicted scene (CSS gradient simulating sky / indoor / outdoor).
- **Light Leak**: 2-3 large `radial-gradient(ellipse at top right, #ffb547 0%, transparent 50%)` + 1 bottom `linear-gradient(to top, #d97757 0%, transparent 30%)`; use warm orange / peach / rose / dark yellow, **never cool blue**.
- **35mm Grain**: a full-screen SVG turbulence noise overlay layer, opacity 14%, `mix-blend-mode: overlay`; can also use `background-image: url("data:image/svg+xml,...feTurbulence...")`.
- Optional: one `feDisplacementMap` pass to simulate film wobble (use sparingly).

[Text]
- Centered or bottom-left: large serif type (Source Serif Pro / Playfair Display / EB Garamond) 5-8vw, weight 500 italic; warm white `#f5e9d6` or cream color.
- Subtitle (24-28px) one line, opacity 0.7, same serif.
- Corner caption (uppercase letterspace 0.18em, 10-11px, mono, opacity 0.5): "REEL 03 · CH I · 1985".
- Bottom timecode + shooting location + date (mono, opacity 0.4).

[Optional extras]
- "Film scratches": a few 1-2px vertical white lines, opacity 0.2, irregular spacing (use multiple inset `box-shadow`s or multiple `<div>`s).
- "Film sprocket holes": inside the letterbox black bars, evenly spaced small white squares (CSS repeating-linear-gradient).
- Entrance animation: the whole frame goes from underexposed (brightness 0.3) → normal within 800ms; the light leak position drifts slowly on a 12s cycle.

[Design details]
- Never use more than 4 hues total (deep background + 2 warm light-leak colors + cream text).
- Strictly forbidden: blue-violet light leaks (breaks the film texture), emoji, neon colors, geometric dashboard decoration.
- For CJK text: `Noto Serif SC` has no italic variant → use `Noto Serif SC` regular with increased letter spacing instead.
- Must use the title provided by the user; auto-estimate reasonable "year / chapter / location" metadata (but derived from the user's content).
- Single-file HTML; disable animation via `prefers-reduced-motion`.

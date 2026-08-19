---
name: vfx-text-cursor
zh_name: "VFX Text Cursor"
en_name: "VFX Text Cursor"
emoji: "✨"
description: "Cursor light-trail + two-tone chromatic aberration + directional light leaks, ideal for revealing a headline quote character-by-character in a video intro"
category: video
scenario: video
aspect_hint: "1920×1080 (16:9)"
featured: 38
recommended: 7
tags: ["vfx", "text", "cursor", "chromatic", "reveal", "frame"]
example_id: sample-vfx-text-cursor
example_name: "VFX Cursor · Opening Quote"
example_format: markdown
example_tagline: "Character-by-character reveal + chromatic light trail"
example_desc: "Typing cursor with hot pink + cyan aberration, for video openings"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · vfx-text-cursor"
od:
  mode: video
  surface: video
  scenario: video
  featured: 0.15
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the \"VFX Text Cursor\" template to turn my content into a scene with \"a cursor light-trail + two-tone chromatic aberration + directional light leaks, ideal for revealing a headline quote character-by-character in a video intro\". Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: VFX Text Cursor]
[Intent] Video opening / hero frame — a cursor "types" across the canvas, text is revealed character by character, trailed by a chromatic aberration streak + directional light leaks. Inspired by hyperframes vfx-text-cursor.

[Canvas] 1920×1080, background `#06070a` dark matte black or `#0a0d12` (warm-blue tinted); add a subtle vignette.

[Content]
- One headline quote (any language), centered, font size 6-8vw, weight 700, typeface `Inter Tight` / `Source Sans 3` / `Noto Sans SC`.
- Reveal character by character, 80ms interval per character; the current character is followed by a cursor `▍` (or a thin vertical bar).
- Already-revealed text defaults to white `#f5f5f7`, opacity 1; the about-to-reveal position gets a chromatic ghost: a `text-shadow: 2px 0 #ff3b6f, -2px 0 #00d4ff` at the instant of reveal, converging back to normal within 200ms.
- The cursor itself: a 16px-wide rectangle, color = accent (pick one: hot pink `#ff3b6f` / cyan `#00d4ff` / amber `#ffb547`), blinking via `@keyframes` on a 1.0s cycle; trailing a 60-120px motion blur trail behind it (radial gradient to transparent).

[Light leaks / rays]
- Randomly generate 3-5 **directional light leaks** near the typing position: thin elongated rectangles using `linear-gradient(45deg, transparent, accent20, transparent)` + `mix-blend-mode: screen`, at irregular angles.
- When the text finishes typing, add a 0.5s shimmer sweep across the whole line (a band of light sweeping across).

[Fields]
- Top caption (uppercase letterspace 0.18em, 11px, opacity 0.5): "FRAME 01 · OPENING".
- Subtitle below the text (24-28px, opacity 0.6): source / chapter.
- Bottom-right timecode (`00:03:21` mono).

[Design details]
- **Never**: multicolor rainbow chromatic aberration (use only 1 pair, e.g. hot pink + cyan two-tone aberration, not full R/G/B).
- Fonts: Latin `Inter Tight` Bold; CJK `Noto Sans SC` Bold; serif fonts strictly forbidden.
- Motion via `@keyframes` + a JS timer (`setTimeout` per character), can be disabled by `prefers-reduced-motion` (show all text immediately).
- Must use the user-provided quote; do not fabricate one.
- Single-file HTML, no external resources besides fonts.

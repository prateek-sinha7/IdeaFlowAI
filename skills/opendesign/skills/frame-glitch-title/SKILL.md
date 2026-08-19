---
name: frame-glitch-title
zh_name: "Glitch Art Title Frame"
en_name: "Glitch Title Frame"
emoji: "⚡"
description: "Digital glitch / chromatic aberration / data-corruption title, for video transitions / cyberpunk hero shots"
category: video
scenario: video
aspect_hint: "1920×1080 (16:9)"
featured: 37
recommended: 6
tags: ["glitch", "cyberpunk", "title", "transition", "vfx", "frame"]
example_id: sample-frame-glitch-title
example_name: "Glitch Title · SIGNAL_LOST"
example_format: markdown
example_tagline: "cyan / magenta chromatic aberration + CRT scanlines"
example_desc: "Giant title + data-corruption artifacts + corner ASCII noise chunks"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · glitch"
od:
  mode: video
  surface: video
  scenario: video
  featured: 0.14
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Glitch Art Title Frame' template to turn my content into a 'digital glitch / chromatic aberration / data-corruption title, for video transitions / cyberpunk hero shots'. Keep the template's visual signature, use real content and data, avoid lorem ipsum and placeholder images."
---

[Template: Glitch Art Title Frame (Glitch Title)]
[Intent] A single-frame hero / video transition / cyberpunk-style title. Inspired by hyperframes glitch.

[Canvas] 1920×1080, near-black background `#070708` or CRT dark gray `#0d0e10`; add a 56px grid (5% opacity) + horizontal scanlines (8% opacity, 2px spacing).

[Main title]
- Centered, 6-9vw, weight 800/900, font `Space Grotesk Bold` / `Inter Tight Black` / `JetBrains Mono Bold`.
- Color: main layer `#f5f5f7`; behind it, 2 artifact layers:
  - cyan `#00f0ff` translate(`-3px`, `1px`).
  - magenta `#ff2bd6` translate(`3px`, `-1px`).
- Split the whole layer into 5-8 clip-path slices, each with `@keyframes` randomly translateX -10px → 10px, lasting 80-160ms, staggered playback, to create "data corruption" chromatic aberration.
- Every 1.5s trigger a "heavy glitch" — the whole title gets a 1-frame horizontal smear, via `filter: url(#displacementFilter)` or a simple CSS translate.

[Additional layers]
- Top caption line (uppercase mono, 11px, opacity 0.6): `>> SIGNAL_LOST · CH-04 · 14:32:08`.
- One subtitle line below the title (24-28px, mono, opacity 0.7), occasionally replaced with ` ̶▒̶` characters (fake corruption).
- Random `█▓▒░` ASCII noise chunks scattered in the corners.
- Bottom timecode (mono, opacity 0.4).
- A noise grain layer over the whole frame `background-image: url("data:image/svg+xml,...turbulence...")`, opacity 6%, mix-blend-mode overlay.

[SVG filter (optional)]
- Define `<filter id="rgbShift">` using `feColorMatrix` + `feOffset` + `feMerge` to shift the R/G/B channels; apply `filter: url(#rgbShift)` to the whole layer during the glitch moment.

[Design details]
- Colors limited to: black / white / cyan / magenta / a touch of amber warning color; no full rainbow.
- Fonts: Latin `Space Grotesk` or `JetBrains Mono` Bold; CJK `Noto Sans Mono CJK SC` or `Noto Sans SC` Bold.
- No lorem ipsum; must use the user's title + subtitle.
- Animation via `@keyframes`, disabled by `prefers-reduced-motion` (fall back to a static chromatic split).
- Single-file HTML.

Note: the `█▓▒░` glyphs and the ` ̶▒̶` corrupted-text marker above are decorative glitch-effect filler, not language content — left as-is by design.

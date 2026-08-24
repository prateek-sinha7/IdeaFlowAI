---
name: social-spotify-card
zh_name: "Spotify Now-Playing Card"
en_name: "Spotify Now-Playing Card"
emoji: "🎵"
description: "Spotify Now Playing style card: album art + progress bar + playback controls, fits video overlays / personal profile pages"
category: card
scenario: personal
aspect_hint: "1280×720 or 600×200"
featured: 43
tags: ["spotify", "music", "now-playing", "card", "overlay"]
example_id: sample-social-spotify-card
example_name: "Spotify Now Playing · Lo-Fi"
example_format: markdown
example_tagline: "Spotify classic dark card"
example_desc: "Lo-Fi Beats · Chillhop progress bar 1:24 / 3:42 + control row"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · spotify-card"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: personal
  featured: 43
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the \"Spotify Now-Playing Card\" template to turn my content into a \"Spotify Now Playing style card: album art + progress bar + playback controls, fits video overlays / personal profile pages\". Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Spotify Now-Playing Card]
[Intent] Render a song, a podcast episode, or a personal bio as a Spotify Now Playing card, suitable for video overlays / personal about pages / creator heroes. Inspired by hyperframes spotify-card.

[Canvas] Two sizes:
- Landscape video overlay: 1280×720, card centered or floating bottom-left.
- Compact bar widget: 600×200, can be embedded in any hero.

[Card structure]
- Outer frame: 12-16px rounded corners; bg uses a dark gradient sampled from the album art color (e.g. `linear-gradient(135deg, #1e3264 0%, #0d1f3d 100%)`) or Spotify's classic `#121212`; a subtle 1px border at the edge.
- Left side: **album art** (CSS gradient + a large monogram or abstract geometric illustration, no linked images allowed), 6px rounded corners, 60-200px square.
- Right side:
  - Top `NOW PLAYING` (uppercase letterspace 0.14em, 11px, green `#1DB954`).
  - **Track name / title** (Inter / Spotify Circular, 22-28px, weight 700, white).
  - **Artist / subtitle** (16px, weight 400, opacity 0.7).
  - Progress bar: 4px tall, rounded, gray background + white fill (`width: 38%`); timestamps on both ends `1:24 / 3:42` (mono, 11px, gray).
  - Control row: ⏮ ⏯ ⏭ icons (inline SVG, 24px, white fill), smaller shuffle / repeat icons.
- Top-right: Spotify logo (inline SVG, green `#1DB954` circle + three white sound-wave arcs).
- Optional: a small audio-wave animation bottom-right (3 bars via `@keyframes`).

[Fonts]
- Primary: `Spotify Circular` → fallback `Inter` / `Inter Tight`, weight 400 / 700.
- Numbers: same primary font, avoid overusing mono.

[Design details]
- Spotify classic dark mode: `#121212` bg, `#1DB954` accent, `#b3b3b3` secondary text.
- If the user input is text/a title → treat the "title" as the track name, "subtitle/author" as the artist, default the estimated "duration" to 3:42.
- If the user input is music-related → map it directly.
- Linked images are strictly forbidden; build the cover art with CSS gradients + a text logo / geometric illustration.
- Micro-animation: the audio-wave animation uses `@keyframes`, can be disabled by `prefers-reduced-motion`.
- Single-file HTML.

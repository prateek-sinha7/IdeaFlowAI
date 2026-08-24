---
name: social-x-post-card
zh_name: "X (Twitter) Post Card"
en_name: "X / Twitter Post Card"
emoji: "𝕏"
description: "Realistic X post card with engagement stats (likes/reposts/views), for video overlays or shareable image cards"
category: card
scenario: marketing
aspect_hint: "1280×720 or 1080×1080"
featured: 44
tags: ["twitter", "x", "social", "card", "overlay"]
example_id: sample-social-x-post-card
example_name: "X Post Card · AlchainHust quote"
example_format: markdown
example_tagline: "X dark mode + engagement stats"
example_desc: "A quotable tweet + 12.3K likes / 1.2K reposts + verified badge"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · x-post"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: marketing
  featured: 44
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'X (Twitter) Post Card' template to turn my content into a 'realistic X post card with engagement stats (likes/reposts/views), for video overlays or shareable image cards'. Keep the template's visual signature, use real content and data, avoid lorem ipsum and placeholder images."
---

[Template: X (Twitter) Post Card]
[Intent] Render a tweet (or a user's quotable line) as a highly realistic X post card, for video overlays, sharing on X, or knowledge capture. Inspired by hyperframes x-post.

[Canvas] 1280×720 or 1080×1080, dark background `#0f1419` or light background `#ffffff` (matching X's theme); card centered, soft shadow.

[Card structure]
- Outer frame: 16px rounded corners, 1px border `#2f3336` (dark) / `#eff3f4` (light), 16px padding.
- Top row: avatar (48×48 circle, CSS gradient placeholder) + display name + handle `@username` + verified badge + timestamp (mono, 12px, gray).
- Body: 17-22px, weight 400; links in X blue `#1d9bf0`; hashtags same color; mentions same color; 0.6em spacing between paragraphs.
- Optional: quote card (nested small card, gray background, 12px rounded corners).
- Optional: 1 image (CSS gradient + description placeholder, no external image links), 16:9 ratio, 12px rounded corners.
- Engagement row: 4 icons + counts (reply / repost / quote / like), inline SVG icons (X's official style), gray, colored on hover.
- X logo (single-line SVG) in the top-right corner.
- View count row: 👁️ + number (small text).

[Fonts]
- Latin: `Chirp` (X's font) → fallback `Inter` or `Segoe UI`.
- CJK: `Noto Sans SC` / `PingFang SC`.
- Numbers: same as the main font, not mono.

[Design details]
- Light palette: bg `#fff`, text `#0f1419`, secondary `#536471`, border `#eff3f4`, accent `#1d9bf0`.
- Dark palette (recommended for video overlays): bg `#000`, text `#e7e9ea`, secondary `#71767b`, border `#2f3336`, accent `#1d9bf0`.
- Number formatting: 1.2K / 4.5M (never raw 1234).
- Content must come from the user's input; never fabricate tweets.
- If the user's input is data → auto-summarize it into a single quotable tweet (≤ 280 characters).
- Single-file HTML; icons as inline SVG; no external image URLs.
- Optional: add a subtle radial highlight `radial-gradient(...)` behind the card to improve readability for video overlays.

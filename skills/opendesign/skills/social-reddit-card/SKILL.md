---
name: social-reddit-card
zh_name: "Reddit Post Card"
en_name: "Reddit Post Card"
emoji: "🔺"
description: "Realistic Reddit post card with up/down vote rail and comment count, for video overlays / story sharing"
category: card
scenario: marketing
aspect_hint: "1280×720 or 800×600"
featured: 42
tags: ["reddit", "social", "card", "overlay", "story"]
example_id: sample-social-reddit-card
example_name: "Reddit Post · r/programming"
example_format: markdown
example_tagline: "Reddit dark mode + vote rail"
example_desc: "An AITA-style story + 12.3k upvotes + 1.2k comments"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · reddit-post"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: marketing
  featured: 42
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Reddit Post Card' template to turn my content into a 'realistic Reddit post card with up/down vote rail and comment count, for video overlays / story sharing'. Keep the template's visual signature, use real content and data, avoid lorem ipsum and placeholder images."
---

[Template: Reddit Post Card]
[Intent] Render a story / question / joke as a Reddit post card, for video overlays and social story sharing. Inspired by hyperframes reddit-post.

[Canvas] 1280×720 (video overlay) or 800×600 (single card share); transparent or dark background `#0b1416`.

[Card structure]
- Outer frame: 16px rounded corners, bg white `#ffffff` (light) or `#1a1a1b` (dark, recommended for video overlay), border 1px `#edeff1` / `#343536`.
- Left **vote rail** (40-56px wide):
  - Up arrow ▲ (16px, `#878a8c`, orange `#ff4500` on hover).
  - Vote count (Inter, 17px, weight 700, centered, color: gray at 0 / orange positive / blue negative); large numbers formatted as `12.3k`.
  - Down arrow ▼ (blue `#7193ff` on hover).
- Main body:
  - Top meta row: subreddit icon (CSS circle + letter) + `r/subreddit` (bold) + `· Posted by u/username · 3h` (small gray text).
  - **Title** (Inter / IBM Plex Sans, 22-28px, weight 500, dark text).
  - Content: 16px body, or a quote block, or 1 image (CSS gradient placeholder).
  - Bottom action row: 💬 `1.2k Comments` · 🏆 Awards · ⤴️ Share · ⋯ icon.
- Reddit Snoo logo (inline SVG, orange `#ff4500`) in the top-right corner.

[Fonts]
- Primary: `IBM Plex Sans` → fallback `Inter`, weight 400/500/700.
- Numbers: same as the primary font.
- CJK: `Noto Sans SC`.

[Design details]
- Light mode: bg `#fff`, text `#1c1c1c`, secondary `#7c7c7c`.
- Dark mode (recommended): bg `#1a1a1b`, text `#d7dadc`, secondary `#818384`, border `#343536`.
- Vote count color: positive = `#ff4500`, negative = `#7193ff`, zero = `#878a8c`.
- The title's clickable area can get a subtle hover background.
- No external image links; use CSS gradient placeholders with a description instead.
- Must use content the user provided; auto-generate a plausible subreddit / username / vote count.
- Single-file HTML; icons as inline SVG (up/down arrows, comment bubble, trophy).

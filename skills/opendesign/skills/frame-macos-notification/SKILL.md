---
name: frame-macos-notification
zh_name: "macOS Notification Banner"
en_name: "macOS Notification Banner"
emoji: "🔔"
description: "Realistic macOS notification banner + app icon + title/body, great for video overlay / product launch teasers"
category: card
scenario: video
aspect_hint: "1920×1080 video or 480×120 banner"
featured: 41
tags: ["macos", "notification", "banner", "overlay", "frame"]
example_id: sample-frame-macos-notification
example_name: "macOS Notification · New Feature Launch"
example_format: markdown
example_tagline: "Big Sur frosted-glass banner"
example_desc: "App icon + title + two-line body, for video corner overlay"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · macos-notification"
od:
  mode: video
  surface: video
  scenario: video
  featured: 41
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'macOS Notification Banner' template to turn my content into a 'realistic macOS notification banner + app icon + title/body, great for video overlay / product launch teasers'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: macOS Notification Banner]
[Intent] Render an announcement / message / alert as a macOS Big Sur+ style notification banner, suited for video corner overlays, product launch teasers, and social media graphics. Inspired by hyperframes macos-notification.

[Canvas] Two use cases:
- Video overlay 1920×1080, notification placed in the top-right corner, transparent surroundings.
- Standalone banner 480×120, centered output.

[Banner structure]
- Outer frame: 14px corner radius (macOS Big Sur standard), 480×120 (or taller, 480×180, with body text), 12-16px padding.
- Background: **frosted glass** effect — `background: rgba(245,245,247,0.78)` + `backdrop-filter: blur(40px) saturate(180%)`; dark mode `rgba(28,28,30,0.78)`.
- Border: 1px `rgba(0,0,0,0.06)` (light) / `rgba(255,255,255,0.08)` (dark); add a 1px bright highlight `rgba(255,255,255,0.5)` at the top.
- Shadow: `0 10px 40px rgba(0,0,0,0.18), 0 2px 6px rgba(0,0,0,0.08)`.

[Content]
- Left: **App icon** (44×44, 10px corner radius, CSS gradient + a single emoji or monogram letter, **no external image links**).
- Middle:
  - Top row: app name (SF Pro 13px, weight 600) + `now` or a specific time (12px, opacity 0.6) — space-between alignment.
  - Title (15px, weight 600, 1 line truncated).
  - Body (13px, weight 400, 1-2 lines truncated, line-height 1.35).
- Right (optional): action button "Open" or "Reply" (capsule, light gray background).

[Fonts]
- Primary: `SF Pro Text` → fallback `Inter` / `system-ui`; for CJK text use `PingFang SC` / `Noto Sans SC`.

[Optional extras]
- Stacked notifications: the first one in front, the next 2 recede back and down (scale 0.96 + opacity 0.6 + translateY).
- Entrance animation: slides in from off-screen right `transform: translateX(110%)→0`, 200ms ease-out; can be disabled via `prefers-reduced-motion`.
- Top-right control chip "Clear" (shown on hover, opacity 0 by default).

[Design details]
- Light mode uses a white frosted background; dark mode (recommended for video) uses a near-black frosted background.
- The icon must not use externally linked emoji images — use a unicode emoji or a CSS-drawn shape instead.
- Must use content provided by the user; the title + body should clearly derive from the user's input.
- Single-file HTML; note that `backdrop-filter` needs the `-webkit-` prefix for Safari.

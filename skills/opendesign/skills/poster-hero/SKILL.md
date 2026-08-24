---
name: poster-hero
zh_name: "Marketing Poster"
en_name: "Marketing Poster"
emoji: "🖼️"
description: "Vertical poster / social-share image with strong visual impact"
category: poster
scenario: marketing
aspect_hint: "1080×1920 portrait"
tags: ["poster", "social-share", "vertical"]
example_id: sample-poster-launch
example_name: "Marketing Poster · Product Launch"
example_format: markdown
example_tagline: "9:16 social-share image"
example_desc: "High-contrast launch poster with a QR code placeholder + gradient mesh + noise texture"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: marketing
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the \"Marketing Poster\" template to turn my content into a \"vertical poster / social-share image with strong visual impact\". Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Marketing Poster]
- Container `w-[1080px] h-[1920px] mx-auto`, full-screen gradient / mesh background.
- Top 30% whitespace + one large emoji or abstract geometric shape.
- Middle: main headline occupies the visual center (text-8xl, font-black), one-line subheadline.
- Bottom: info cards with 3-5 core points, each with an icon + short phrase.
- Bottom-right corner: brand mark / QR code (use an SVG placeholder).
- Use bold colors: gradient background (e.g. from-violet-500 via-fuchsia-500 to-indigo-500), white text + one contrasting highlight color.
- Use SVG for decorative elements (circles / triangles / waves / noise texture).

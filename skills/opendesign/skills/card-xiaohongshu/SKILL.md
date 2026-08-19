---
name: card-xiaohongshu
zh_name: "Xiaohongshu Card"
en_name: "Xiaohongshu Card"
emoji: "📱"
description: "Xiaohongshu (RED)-style knowledge cards, a swipeable multi-card carousel"
category: card
scenario: marketing
aspect_hint: "1080x1440 (3:4)"
featured: 24
tags: ["xhs", "Xiaohongshu (RED)", "carousel", "graphic cards"]
example_id: sample-xhs-ai-habits
example_name: "Xiaohongshu (RED) Card · AI Tool Habits"
example_format: markdown
example_tagline: "7-card carousel, Morandi gradient"
example_desc: "A collection of tip cards, great for screenshotting to Xiaohongshu (RED) / Moments"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: marketing
  featured: 24
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Xiaohongshu (RED) Card' template to turn my content into a 'Xiaohongshu (RED)-style knowledge card set, a swipeable multi-card carousel'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Xiaohongshu (RED) Card]
- Output N sequential cards, each `w-[1080px] h-[1440px]`, arranged vertically with flex so the whole set can be screenshotted together or one card at a time. N is determined by how much content the user provides: short content starts at 3-6 cards, longer content should use more (Xiaohongshu (RED) posts allow up to 18 images, but 9 or fewer is usually best); each card should carry only one core idea.
- The first card is the cover: a huge title + a one-line subtitle + an attention-grabbing tag (like "Must-read tips" / "Save this").
- The middle cards expand on the content, one core idea per card, with an emoji + a short sentence + 1-2 examples.
- The last card is a summary + call to action (follow / save / comment).
- Color palette: choose soft Morandi tones or pinks; rounded elements, generous whitespace.
- Large font size, wide line spacing, strong contrast (Xiaohongshu (RED) is viewed on mobile, so small text is unreadable).
- A small watermark in the bottom-right corner of each card (author name / date).

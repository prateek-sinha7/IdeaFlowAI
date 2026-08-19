---
name: card-twitter
zh_name: "Twitter Share Card"
en_name: "Twitter Share Card"
emoji: "🐦"
description: "Twitter quote / data card, great for pairing with a tweet"
category: card
scenario: marketing
aspect_hint: "1600×900 (16:9)"
tags: ["twitter", "x", "quote", "quote-card"]
example_id: sample-twitter-quote
example_name: "Twitter Card · Quote"
example_format: text
example_tagline: "16:9 dark quote card, screenshot straight into a tweet"
example_desc: "High-contrast quote template with a grid pattern + gradient glow background"
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
  example_prompt: "Use the 'Twitter Share Card' template to turn my content into a 'Twitter quote / data card, great for pairing with a tweet'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Twitter Share Card]
- Container `w-[1600px] h-[900px]`, dark / light — pick one based on the content's mood.
- A single hero quote centered (text-6xl, font-semibold, limited to 2-3 lines).
- Below it, author byline + avatar placeholder + handle.
- Small tag top-left (type: "Insight" / "Data" / "Quote").
- Brand watermark bottom-right.
- The whole card has a subtle texture (grid pattern / noise / dot pattern).
- Screenshot it and post directly alongside a tweet — visually clean and punchy.

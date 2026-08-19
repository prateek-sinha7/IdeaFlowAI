---
name: frame-liquid-bg-hero
zh_name: "Liquid Background Hero"
en_name: "Liquid Background Hero"
emoji: "🌊"
description: "WebGL-style liquid-displacement background + overlaid tagline, suitable for video intros / landing hero / posters"
category: poster
scenario: video
aspect_hint: "1920×1080 (16:9) or 1080×1920 (9:16)"
featured: 39
tags: ["liquid", "fluid", "background", "hero", "html-in-canvas", "vfx"]
example_id: sample-frame-liquid-bg-hero
example_name: "Liquid Background Hero · Tagline"
example_format: markdown
example_tagline: "Aurora Violet liquid"
example_desc: "Multi-layer radial-gradient breathing background + difference-blend text"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · vfx-liquid-background"
od:
  mode: video
  surface: video
  scenario: video
  featured: 39
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Liquid Background Hero' template to turn my content into a 'WebGL-style liquid-displacement background + overlaid tagline, suitable for video intros / landing hero / posters'. Keep the template's visual signature, use real content and data, avoid lorem ipsum and placeholder images."
---

[Template: Liquid Background Hero]
[Intent]Can serve as a video intro frame, SaaS landing top hero, or poster background. WebGL fluid feel, but rendered as a CSS / canvas fallback so a single file can still be opened by double-click. Inspired by hyperframes vfx-liquid-background.

[Canvas]Choose either 1920×1080 (landscape) or 1080×1920 (portrait). Background fills the full canvas.

[Liquid background — 3 implementations, pick based on user preference]
1. **CSS multi-layer radial-gradient staggered breathing** (most stable, default recommendation):
   - 3-5 large ellipses via `radial-gradient(...)`, colors taken from the palette.
   - Each ellipse wrapped in `@keyframes` translate + scale + hue-rotate, 8-14s period, staggered; the whole frame layered with `mix-blend-mode: screen` or `overlay`.
   - Add a top layer of `backdrop-filter: blur(80px)` to soften the edges further.
2. **Canvas + simple perlin noise** (intermediate):
   - ~80 lines of inline JS, draw metaballs or a simplex noise field with `requestAnimationFrame`.
   - Enable when performance allows; fall back to a static screenshot under `prefers-reduced-motion`.
3. **WebGL fragment shader** (advanced, use with caution):
   - Import `regl` via jsdelivr CDN, or inline plain WebGL.
   - Shader writes domain-warp noise; single quad, one `u_time` uniform.

[Top text layer]
- Centered or bottom-left: one giant tagline (5-7vw, serif or bold sans), fonts: `Source Serif Pro` / `Inter Tight` / `Manrope Black`.
- Text color is paper white `#fafaf8` or ink, depending on background lightness; add `mix-blend-mode: difference` so it stays readable over any liquid color.
- One subtitle line (small sans, opacity 0.7).
- Optional bottom CTA chip or hairline + metadata row.

[Palette — pick 1 of 4, no rainbow]
- 🌅 **Solar Peach** — `#ffb18a` + `#f78b4c` + `#d97757`, warm orange peach.
- 🌊 **Ocean Aqua** — `#5ac8fa` + `#0a84ff` + `#1e3a8a`, ocean blue.
- 🌌 **Aurora Violet** — `#a78bfa` + `#7c5cff` + `#1e1b4b`, aurora violet.
- 🌿 **Forest Mint** — `#86efac` + `#34d399` + `#065f46`, mossy forest.

[Design Details]
- Strictly forbidden: multi-color rainbow (>4 hues), PowerPoint gradients, neon glow overlays.
- Fonts: for CJK text use `Noto Serif SC` (display) / `Noto Sans SC` (subtitle).
- Strictly forbidden: external-linked images; everything must be CSS + SVG + optional canvas.
- Must use the tagline / title provided by the user; if the user's input is data → distill it into a tagline of ≤ 18 words.
- Single-file HTML, motion can be disabled via `prefers-reduced-motion`.

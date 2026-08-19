---
name: frame-logo-outro
zh_name: "Logo Outro Frame"
en_name: "Logo Outro Frame"
emoji: "🎬"
description: "Logo assembles from parts on entrance + glow bloom + tagline reveal, great for video outros / brand closers"
category: video
scenario: video
aspect_hint: "1920×1080 (16:9)"
featured: 40
recommended: 8
tags: ["logo", "outro", "branding", "end-card", "frame"]
example_id: sample-frame-logo-outro
example_name: "Logo Outro · HTML Anything"
example_format: markdown
example_tagline: "Midnight Indigo + glow bloom"
example_desc: "Logo assembly + brand name + tagline + CTA, for video outros"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · logo-outro"
od:
  mode: video
  surface: video
  scenario: video
  featured: 0.16
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Logo Outro Frame' template to turn my content into a 'logo assembles from parts on entrance + glow bloom + tagline reveal, great for video outros / brand closers'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Logo Outro Frame]
[Intent] A brand reveal frame for the end of a video — logo assembles from parts + glow bloom + tagline rises up + CTA. Inspired by hyperframes logo-outro.

[Canvas] 1920×1080, black `#08090c` or a dark brand background; add a subtle vignette `radial-gradient(...)` to brighten the center.

[Layout]
- **Center logo**: drawn with CSS / inline SVG; composed of 4-8 geometric pieces (circle / square / triangle / hairline).
  - Entrance animation: each piece slides in from off-screen (±100px, different directions) + scale 1.4→1.0 + opacity 0→1, staggered by 80ms; total duration 1.2s.
  - After the entrance finishes, add a glow bloom to the whole logo: `filter: drop-shadow(0 0 24px <accent>40)`; simultaneously a shimmer `mask-image` sweeps across the logo (500ms).
- **Brand name**: positioned 6-8% below the logo, large type (Inter Tight / SF Pro Display, 48-72px, weight 700, letter-spacing -0.02em), entrance: typewriter or fade-up after the logo bloom (starts at 1.4s).
- **Tagline**: one line below the brand name (24-28px, weight 400, opacity 0.7), fade in (1.8s).
- **Bottom CTA + metadata**: a two-line bottom row, e.g. `htmlanything.dev · @htmlanything · 2026`, 11px uppercase letter-spacing 0.16em, opacity 0.4 color, hairline divider.

[Color palette — pick 1 of 4, do not mix]
- Midnight Indigo — bg `#08090c`, accent `#7c5cff` (neon purple-blue glow).
- Solar Amber — bg `#0e0a08`, accent `#ffb547` (warm amber).
- Forest Mint — bg `#0a1410`, accent `#5fb38a` (mint green).
- Bone & Ink — bg `#f1efea`, accent `#0a0a0b` (no neon, editorial style, glow replaced with shadow).

[Design details]
- **Never**: use an externally linked logo image; the logo must be drawn purely with CSS / inline SVG geometry.
- Use `@keyframes` + `animation-delay` for the entrance animation; can be disabled via `prefers-reduced-motion`.
- Fonts: Latin `Inter Tight` / `SF Pro Display` / `Manrope`; CJK `Noto Sans SC` weight 700.
- Must use the brand name + tagline provided by the user; if none is given, fall back to "HTML Anything" / "Anything → beautiful HTML".
- Single-file HTML; freeze once the whole animation finishes (do not loop — this is a video end frame).
- An optional 5px top ribbon (accent color) can be added to boost brand recognition.

---
name: mockup-device-3d
zh_name: "iPhone × MacBook 3D Display Stand"
en_name: "Device 3D Showcase"
emoji: "📱"
description: "iPhone + MacBook pseudo-GLTF static display stand, real HTML content embedded in the screens, glass lens refraction, 360° turntable composition"
category: poster
scenario: product
aspect_hint: "1920×1080 (16:9)"
featured: 47
tags: ["device", "mockup", "iphone", "macbook", "html-in-canvas", "product"]
example_id: sample-mockup-device-3d
example_name: "iPhone × MacBook 3D Display Stand"
example_format: markdown
example_tagline: "HTML-in-Canvas Device Showcase"
example_desc: "Both the iPhone screen and MacBook screen embed real UI content, with glass lens refraction"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · vfx-iphone-device"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: product
  featured: 47
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the \"iPhone × MacBook 3D Display Stand\" template to turn my content into an \"iPhone + MacBook pseudo-GLTF static display stand, with real HTML content embedded in the screens, glass lens refraction, and 360° turntable composition\". Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Device 3D Showcase (Device 3D Showcase / HTML-in-Canvas)]
[Intent] Product launches, app demos, design mockup showcases. Real UI content supplied by the user is rendered onto the iPhone / MacBook "screens", surrounded by CSS 3D transforms simulating a GLTF model's glass / highlight / refraction. Inspired by hyperframes vfx-iphone-device.

[Hard composition rules]
- **Canvas**: 1920×1080, warm-gray gradient background `radial-gradient(#1a1a1f → #0a0a0f)`, reflective ground at the bottom (mirror gradient).
- **iPhone 15 Pro model**: left / center, `transform: rotateY(-12deg) rotateX(4deg) translateZ(40px)`; titanium-silver frame `#a8a8ad` (solid 4px) + 56px screen corner radius; an iframe-like div embedded in the screen that actually renders the user's HTML content (mobile viewport 375×812).
- **MacBook Pro 14"** (optional second device): right side, slightly smaller, `rotateY(8deg)`; the lid screen embeds desktop-viewport content (1440×900 scaled); the base's keyboard + trackpad are drawn with CSS shadow lines (no individual keycap detail).
- **Glass / lens flares**: add 2-3 elliptical highlights at the top using `radial-gradient(ellipse, rgba(255,255,255,0.4) 0%, transparent 60%)` to simulate a morphing glass lens.
- **Ground reflection**: below the device, `transform: scaleY(-1)` + `mask-image: linear-gradient(to bottom, rgba(0,0,0,0.4), transparent 70%)`.

[Screen content sources]
- If the user supplies text/data → auto-render it as a mock app UI (top status bar + title + body + bottom tab bar or home indicator).
- If the user supplies HTML → embed it as-is inside the screen div (use a scale transform so it fits the screen's width/height).
- UI inside the screen uses Tailwind; font sizes should match real mobile scale (text-sm / text-base, never text-9xl).

[Optional extra elements]
- Bottom-right "product slug" badge: large logo + one line of tagline + a hairline subtitle.
- A top caption line (English sans-serif, small size, 0.6 opacity): product codename / date / version.
- Add an 8s auto CSS turntable: `@keyframes turntable` rotateY -12 ↔ 12, ease-in-out infinite alternate; can be disabled via `prefers-reduced-motion`.

[Design details]
- **Never**: use external mockup image URLs (any unsplash / dribbble link) — draw the device entirely with CSS / SVG.
- Fonts: captions / logos outside the device use an `Inter Tight` / `SF Pro` style; content inside the device adapts to whatever the user provides.
- Background offers 4 optional palettes: charcoal / pearl / midnight blue / mocha; no rainbow gradients.
- Single-file HTML; don't nest iframes with srcdoc (prone to issues) — render content with `<div class="screen">` + Tailwind instead.
- Screen content must be filled with the user's real data; lorem ipsum or "Your text here" is strictly forbidden.

---
name: frame-flowchart-sticky
zh_name: "Sticky Flowchart Frame"
en_name: "Sticky Flowchart Frame"
emoji: "📝"
description: "SVG curved connectors + sticky-note nodes + cursor interaction, like a whiteboard brainstorm"
category: video
scenario: operations
aspect_hint: "1920×1080 (16:9)"
featured: 45
tags: ["flowchart", "diagram", "sticky", "whiteboard", "frame"]
example_id: sample-frame-flowchart-sticky
example_name: "Sticky-note flowchart · User onboarding"
example_format: markdown
example_tagline: "SVG curves + 4-color sticky notes"
example_desc: "6-node onboarding flow, handwritten font on a whiteboard-paper background"
example_source_url: "https://hyperframes.heygen.com/catalog"
example_source_label: "hyperframes · flowchart"
od:
  mode: video
  surface: video
  scenario: operations
  featured: 45
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Sticky Flowchart Frame' template to turn my content into a scene with 'SVG curved connectors + sticky-note nodes + cursor interaction, like a whiteboard brainstorm'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Sticky Flowchart Frame]
[Intent] Draw a process / system / workflow as a "whiteboard + sticky notes" scene, suited to onboarding videos, ops process explainers, and system architecture walkthroughs. Inspired by the hyperframes flowchart.

[Canvas] 1920×1080. Background: cream whiteboard paper `#f4ede1` or cool-gray whiteboard `#f0f2f4`; add a very faint hex grid `rgba(0,0,0,0.04)` to give it a whiteboard feel.

[Nodes (Sticky Notes)]
- Each node = one 240×180px sticky note, randomly assigned one of 4 color sets: yellow `#fcd34d` / peach `#fca5a5` / mint `#a7f3d0` / sky `#a5b4fc`.
- Sticky notes have a slight, inconsistent rotation `transform: rotate(±2deg)`, a drop shadow `drop-shadow(0 6px 14px rgba(0,0,0,0.12))`, and a decorative tape strip at the top with `linear-gradient(...)`.
- Node content: 1 emoji or single-line SVG icon + a large title (16-20px) + a one-line description (12px).
- Node font: `Kalam` / `Caveat` / `Patrick Hand` handwriting-style fonts (for CJK text use `Xiaolai` or `LXGW WenKai Screen` — kept as-is, these are real font names).

[Connectors (SVG)]
- Connect nodes with `<path>` Bezier curves, stroke `#2a2a2a`, width 2.5, `stroke-linecap: round`, `stroke-dasharray: 0` (solid) or `8 6` (dashed = conditional branch).
- Arrowheads via `marker-end`, small black triangle arrows.
- Complex nodes can loop or branch: 2 lines out of the same node (fork) or 2 lines into the same node (merge).

[Optional Interaction]
- Top caption (sans, 12px uppercase): "FLOW · MIGRATION · 2026".
- Mouse hover on a node: lift the shadow + scale 1.05, via CSS transition.
- A "cursor" decoration (`<svg>` arrow + name tag), floating near a node, mimicking a Figma collaboration cursor.

[Design Details]
- At least 5 nodes, at most 12.
- Don't center-align every node — give it some whiteboard-style "stuck on by hand" feel, but make sure the connectors stay clear and don't cross.
- Strictly forbidden: full-screen dark background, neon colors, corporate dashboard style.
- No Inter / serif fonts — must be handwriting-style.
- Single-file HTML, no external icon libraries (use inline SVG).
- Must use the user's real process content; node text comes directly from user input.

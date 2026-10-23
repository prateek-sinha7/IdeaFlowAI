---
name: design-ingestor
display_name: Design Ingestor
description: Scripts for extracting structured design tokens and HTML scaffold from Figma frame exports or custom HTML uploads. Run figma_extract.py after visual observation of Figma frames, then make_ds.py for tokens.css, then figma_to_html.py for example.html. For HTML uploads, extracts CSS variables directly from the uploaded file.
category: workflow
isBeta: false
tags:
  - design
  - figma
  - html
  - ingestor
---

# Design Ingestor Scripts

Three pure-stdlib Python scripts that convert your structured visual observations
into catalog-quality design artefacts. Run them in order after the vision phase.

## Script 1 — `figma_extract.py` (observations → source.json + mapping.json)

```bash
python3 skills/figma-ingestor/scripts/figma_extract.py \
    --manifest .figma/manifest.json \
    --obs context/design/observations.json \
    --out context/design/
```

**Input**: `observations.json` written by you in Phase A1b (structured hex values per
frame). **Output**: `context/design/source.json` (read_source.py-compatible) and
`context/design/mapping.json` (make_ds.py input).

## Script 2 — `make_ds.py` (mapping.json → tokens.css + components.html)

```bash
OD_SCHEMA_PATH=skills/figma-ingestor/scripts/schema \
python3 skills/figma-ingestor/scripts/make_ds.py \
    context/design/mapping.json \
    --dest context/design/
```

**Input**: `mapping.json` from Script 1. **Output**: `context/design/tokens.css`
(full `:root` block, all 56 schema tokens) and `context/design/components.html`
(component reference page using `var(--*)` only).

Note: `--dest` folder name must equal the `id` field in `mapping.json`. Script 2
uses `OD_SCHEMA_PATH` to find the bundled `tokens.schema.ts`.

## Script 3 — `figma_to_html.py` (frames.json + tokens.css → example.html)

```bash
python3 skills/figma-ingestor/scripts/figma_to_html.py \
    --frames context/design/template/figma/frames.json \
    --tokens context/design/tokens.css \
    --prefix fg \
    --out context/design/template/example.html
```

**Input**: `frames.json` (written in Phase A3) and `tokens.css` (from Script 2).
**Output**: `context/design/template/example.html` — a template-contract-compliant
scaffold with `.nav-item[data-go]` nav, `section.pattern[data-pattern]` per screen,
and all CSS vars from `tokens.css` in `:root`.

## observations.json schema

Write this file in Phase A1b **before** running Script 1:

```json
{
  "frames": [
    {
      "index": 0,
      "name": "frame-1.png",
      "screen": "Dashboard",
      "layout": "sidebar-nav",
      "bg": "#hex",
      "fg": "#hex",
      "accent": "#hex",
      "surface": "#hex",
      "surface_2": "#hex",
      "border": "#hex",
      "muted": "#hex",
      "on_accent": "#ffffff",
      "font_weight": "medium",
      "font_density": "compact",
      "font_family_hint": "Inter, system-ui, sans-serif"
    }
  ],
  "dominant_layout": "sidebar-nav",
  "color_scheme": "dark",
  "suggested_name": "MyApp Design"
}
```

Layout values: `sidebar-nav` | `topbar-nav` | `centered` | `dashboard` | `split`  
Font weight values: `light` | `regular` | `medium` | `semibold`  
Font density values: `compact` | `comfortable` | `spacious`

# DESIGN.md skeleton (long form, the convention of 57 + 11 full systems)

The first three lines are parsed by `od_loader.py:405-408`:
- the H1 is the name; the picker shows it exactly as written
- `> Category:` is the tab
- the next `>` line is the description

The nine `##` headings must be exactly these, in this order.
`validate_design_system.py` checks them. Model: `OD/design-systems/iberia/DESIGN.md`.

```markdown
# Design System Inspired by <Name>

> Category: <Category>
> <One line: what the product is and its visual signature, ≤ 160 chars.>

## 1. Visual Theme & Atmosphere

<2-4 paragraphs: the products/surfaces it is for, the overall feel, density,
the one or two rules that define the brand (for example "red means the brand, not danger").>

**Key characteristics:**
- <6-10 bullets with concrete values: canvas colour, card treatment, accent use, type pairing, radius>

**Provenance:** <what came from the source (export file / site / spec) vs what was
authored here. Example: "Colours, type scale and radii are from the export's
tokens/*.css; breakpoints and the 32px H1 step are authored.">

## 2. Color Palette & Roles

### Primary
- **<Role name>** (`#XXXXXX`): <where it is used, contrast notes>

### Surfaces & neutrals
- **Canvas** (`#…`): page background (`--bg`)
- **Card** (`#…`): `--surface` · **Panel** (`#…`): `--surface-warm`
- **Ink** (`#…`) `--fg` · **Muted** (`#…`) `--muted` · **Line** (`#…`) `--border`

### Semantic
- **Success** (`#…`) · **Warning** (`#…`) · **Danger / critical** (`#…`) · **Info** (`#…`)

### <Themes, tiers or gradients the brand has (dark/ops theme, loyalty tiers)>

## 3. Typography Rules

### Font family
- **Display**: <family> (<open substitute for a proprietary face>), weights <…>
- **Body**: <family>, weights <…>
- **Mono**: <family>, used for <numbers, codes, times>

### Hierarchy
| Role | Font | Size | Weight | Line height | Letter spacing | Notes |
|---|---|---|---|---|---|---|
| Display | | 40px | 700 | 1.2 | -0.01em | |
| H1 … Caption … Micro | | | | | | |

## 4. Component Stylings

### Buttons
<Primary / secondary / ghost / destructive: colours, height, padding, radius,
hover and focus.>

### <Brand bar / navigation> · ### Inputs · ### Chips & badges · ### Cards · ### Tables
<For each: concrete values and states.>

### <Domain components (flight row, seat map, KPI tile …) when the source has them>

## 5. Layout Principles
- Spacing scale (px): <4 8 12 16 24 32 48 …>
- Containers: <max widths>, gutters <desktop/tablet/phone>
- Grid and density rules: <compact vs comfortable, row heights>

## 6. Depth & Elevation
| Level | Shadow | Use |
|---|---|---|
| Flat | none | |
| Ring | 0 0 0 1px <border> | |
| Raised | <value> | |

<Focus ring, motion durations and easing, reduced-motion rule.>

## 7. Do's and Don'ts

### Do
- <Concrete rules carried over from the source>

### Don't
- <Concrete anti-patterns>

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Key changes |
|---|---|---|
| Phone | < 640px | |
| Tablet | 640–1023px | |
| Desktop | ≥ 1024px | |

<Touch targets, how navigation collapses, how tables adapt. Mark authored
breakpoints when the source had none.>

## 9. Agent Prompt Guide

### Quick color reference
- Brand / accent: <Name> (`#…`)
- Canvas: `#…` · Card: `#…` · Text: `#…` · Muted: `#…` · Border: `#…`
- Success `#…` · Warning `#…` · Danger `#…`

### Example component prompts
- "<A prompt naming exact values, for example: Create a primary button: #… background, white 600 15px Open Sans, 40px tall, 4px radius.>"
- <3-5 more>

### Iteration guide
1. <The 5-8 rules an agent must not break>

### Known gaps
- <What the source did not define and how it was filled>
```

## Mapping a Claude Design export

| Export | Goes to |
|---|---|
| `tokens/colors.css` `:root` raw palette (`--<x>-red`, `--<x>-ink` …) | §2 values and `tokens.css` A1/A2 colours, mapped by meaning |
| `tokens/colors.css` semantic aliases (`--text-*`, `--surface-*`, `--action-*`, `--focus-ring`) | role hints only; do not copy the names (collisions) |
| `[data-theme="…"]` blocks | `themes` in mapping.json, plus prose in §2 |
| `tokens/typography.css` (in `source.json` `type_roles`) | §3 table copied from the rules, `--font-*`, `--text-*` by role, `--leading-*`, `--tracking-display` |
| `tokens/spacing.css` | `--space-N` by px value (N×4px), `--radius-*`, `--elev-*`, `--motion-*`, `--container-*`, §5 and §6 |
| `tokens/density.css` | §5 density rules (no schema tokens) |
| `tokens/fonts.css` Google imports | `fonts_href` |
| `components/components.css`, `*.prompt.md`, `ui_kits/` | §4 component values and §9 prompts |
| `readme.md`, `SKILL.md`, `uploads/*.md` | §1 atmosphere, §7 do's and don'ts, provenance and known gaps |
| `_ds_manifest.json` `tokens` | a cross-check that no token was missed |

## Marking authored values

Any value DESIGN.md states that the source does not contain gets `(authored)`
right after it, for example `| Tablet | 640–1023px (authored) |` or
`**Info** (#1f5fa8, authored)`. The §1 provenance paragraph summarises which
groups are sourced and which are authored. In `mapping.json` the marker goes in
`notes` only. Token values must stay plain CSS: `make_ds.py` rejects `96px (authored)`.
A value is authored only if it is absent from every extracted file.

## Mapping a website (`site.json`: page 0 is at the top level, all pages are in `pages[]`)

| site.json | Goes to |
|---|---|
| `colors.background[0]` | `--bg`. Next lighter or darker tier: `--surface` / `--surface-warm` |
| `colors.text[0]` / `[1]` | `--fg` / `--muted` |
| `colors.border[0]` | `--border` |
| `accents[0]`, `samples.buttons_filled[0].backgroundColor` | `--accent`; the button `color` is `--accent-on` |
| `type.families` | `--font-body`; the `samples.h1.fontFamily` gives `--font-display` |
| `type.sizes` (ranked) | `--text-*` by role (samples.h1 → 3xl, h2 → xl/2xl, body → base). Never drop the most-used display size |
| `shape.radius`, `shape.shadow`, `shape.spacing` | `--radius-*`, `--elev-*`, `--space-*` |
| `breakpoints` | §8 table |
| `copy` | §7 voice notes and §9 prompts |
| `root_vars` | when the site exposes its own tokens, prefer them |
| Semantic colours (usually absent) | author them, and mark them authored |

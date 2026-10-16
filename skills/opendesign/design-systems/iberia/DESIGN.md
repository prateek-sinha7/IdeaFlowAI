# Design System Inspired by Iberia Airlines

> Category: Travel & Aviation
> Spanish flag carrier. Iberia red and gold, square brand bar, data-dense airline consoles.

## 1. Visual Theme & Atmosphere

Iberia's digital language is warm, Spanish and confident, but in the product it behaves like
operational software rather than a travel brochure. A square-cornered brand bar in Iberia red
(`#D7192D`) anchors every screen; below it the canvas is calm off-white (`#FAFAFA`) with white
cards, light-grey panels and a near-black ink (`#333333`) that carries almost all text. The
gold of the livery (`#FCD100`) appears only as a highlight fill — a tier badge, an active-nav
underline, an environment marker — never as text.

The system serves three surfaces with one token set: airport and call-centre **agent consoles**
(compact, keyboard-first, data-dense), **operations-control wall screens** (the same components
in an `ops-dark` theme) and **passenger mobile web** (comfortable density, larger touch
targets, the brand gradient allowed in hero bands). Flight numbers, booking codes, times and
seats are always set in a monospace face with tabular figures so columns of operational data
line up.

The defining rule is **red means Iberia, not danger**. Brand red marks primary actions, links,
the selected seat and the active step. Cancelled flights, blocking errors and destructive
actions use a separate, darker critical red (`#8E0F14`) — always with an icon and a label —
so an Iberia screen full of red buttons never reads as a screen full of alarms.

Values come from iberia.com's production stylesheet (brand and neutral colours, font family
names, type scale, radii); semantic colours, density modes, the ops-dark theme and component
rules are authored on top of it. Iberia's own typefaces (`iberiaheadline`, `iberiatext`) are
proprietary: artifacts use Montserrat and Open Sans as substitutes, Roboto Mono for data.

## 2. Color Palette & Roles

> **Source:** iberia.com `/akastatic/css/modules.css` (brand + neutrals, ranked by frequency of use). Semantic, tier and dark values are authored.

### Primary
- **Iberia Red** (`#D7192D`): The most-used colour on iberia.com. Brand bar, primary buttons, links, selected seat, active stepper step, focus ring. 5.2:1 on white.
- **Iberia Red Dark** (`#A8191A`): Hover and pressed state for every red element; headings on red tint.
- **Ink** (`#333333`): Primary text — the most-used text colour on the live site. 12.1:1 on the canvas.

### Secondary & Accent
- **Iberia Gold** (`#FCD100`): Highlight fill only — Iberia Plus Oro badge, active-nav underline, environment badge. Fails as text on white (1.5:1); as a fill under `#333333` text it gives 8.6:1.
- **Iberia Orange** (`#F08400`): Gradient mid-tone and the warning *fill*.
- **Red Deep** (`#BE192C`): Focus ring on red surfaces.
- **Red Tint** (`#F3CDD1`): Selected table row, red-tinted callout background.

### Surface & Background
- **Canvas** (`#FAFAFA`): App background.
- **White** (`#FFFFFF`): Cards, inputs, drawers.
- **Panel Grey** (`#F5F5F5`): Side panels, table headers, the AI assistant panel.
- **Sunken Grey** (`#EEEEEE`): Section backgrounds, disabled fills.

### Neutrals & Text
- **Muted Grey** (`#6B6B6B`): Secondary text, labels, helper text. (iberia.com uses `#777777`, which is 4.48:1 — darkened to pass AA.)
- **Strong Black** (`#000000`): Large data figures only.
- **Line** (`#D0D0D0`): Control borders, table frames.
- **Line Soft** (`#E5E5E5`): Row dividers, card edges.

### Semantic & Accent
- **Success** (`#2E7D32` on `#E8F5E9`): On time, confirmed, checked in.
- **Warning** (`#9A4F00` text on `#FFF3E0`; fill `#F08400`): Delayed, at risk, needs review.
- **Critical** (`#8E0F14` on `#FDECEC`): Cancelled, missed connection, blocking error, destructive action. Never brand red.
- **Info** (`#1F5FA8` on `#E8F0FA`): Informational notes, links inside dense tables.
- **Iberia Plus tiers:** Clásica `#E5E5E5`, Plata `#A7A9AC`, Oro `#FCD100`, Platino `#5B5B5B`, Infinita `#000000`, Infinita Prime `#000000` with a gold border.

### Ops-dark (control-room wall screens)
- Canvas `#14161A`, surface `#1E2127`, line `#2E323A`, ink `#ECEDEF`, muted `#A0A4AC`.
- Red lifts to `#F25C6A` (5.0:1 on the dark surface) with dark text on red buttons; semantic colours lift too. The brand bar stays `#D7192D` in both themes.

### Gradient System
- **Brand gradient** `linear-gradient(90deg, #A8191A 0%, #D7192D 35%, #F08400 75%, #FCD100 100%)`, taken from the logo. Passenger hero and brand bands only — never behind data, never in agent or ops screens.

## 3. Typography Rules

### Font Family
- **Headline:** `iberiaheadline` on iberia.com → **Montserrat** 600/700 in artifacts.
- **Text / UI:** `iberiatext` (+ bold/italic cuts) → **Open Sans** 400/600.
- **Data:** **Roboto Mono** 500 with `font-variant-numeric: tabular-nums` — flight numbers, booking codes, times, seats, bag tags, KPI figures.
- **Fallback:** `Verdana, Geneva, Tahoma, sans-serif` (the live site's own fallback).
- Load from Google Fonts: `Montserrat:wght@600;700`, `Open+Sans:wght@400;600;700`, `Roboto+Mono:wght@500;600`.

### Hierarchy
| Role | Font | Size | Weight | Line height | Notes |
|---|---|---|---|---|---|
| Display | Montserrat | 40px | 700 | 1.15 | Passenger hero only, -0.01em |
| H1 | Montserrat | 26px | 700 | 1.2 | Page title |
| H2 | Montserrat | 24px | 600 | 1.2 | Section title |
| H3 | Montserrat | 20px | 600 | 1.3 | Card title |
| H4 | Open Sans | 18px | 600 | 1.35 | Sub-section |
| Body | Open Sans | 16px | 400 | 1.5 | Default |
| Body small | Open Sans | 14px | 400 | 1.45 | Tables, dense UI |
| Caption | Open Sans | 13px | 400 | 1.4 | Labels, helper text — the most-used size on iberia.com |
| Micro | Open Sans | 12px | 600 | 1.2 | UPPERCASE, +0.04em — status chips, column headers |
| Data | Roboto Mono | 13–26px | 500 | 1.2 | Tabular figures, never letter-spaced |

### Principles
- Sentence case for headings and buttons ("Confirmar y facturar"). Uppercase only through the micro style.
- Times are 24-hour with the airport code: `10:45 MAD`. Routes are written `MAD → JFK`.
- Spanish first (es-ES) with an English toggle; design for +30% text expansion.

## 4. Component Stylings

### Buttons
- **Primary:** Iberia red fill, white label, 4px radius, 48px tall (44px compact — never smaller), Open Sans 600. Hover `#A8191A`. Disabled `#EEEEEE` with muted label.
- **Secondary:** White fill, 1px red border, red label; hover gets the panel grey and darker red.
- **Tertiary / link:** Red text, underline on hover.
- **Destructive:** Critical red `#8E0F14` fill, white label; always followed by a confirm dialog.

### Brand Bar
- 56px, square corners, `#D7192D` in every theme. White "IBERIA" text wordmark (Montserrat 700, +0.14em) on the left — a placeholder; the real logo is a trademark and is never drawn. Station, position, user and the ES/EN toggle on the right. System banners stack directly beneath it, full width.

### Inputs
- 48px (40px compact), 1px `#D0D0D0`, 4px radius, label above in caption muted, helper text below. Focus: 2px red outline with 2px offset. Error: critical border, icon and message.

### Status Chips
- Pill (999px), micro text, tinted background plus a coloured dot or icon. States: On time, Boarding, Delayed, Cancelled, Diverted, Checked in, Not checked in, Rebooked, Pending. Status is never colour alone.

### Cards
- White, 1px `#E5E5E5` border, 6px radius, shadow `0 1px 2px rgba(0,0,0,.08)`. Selected: red 1px border plus a 1px red ring. No coloured left-border accents.
- **Flight card:** flight number (mono) + `MAD → JFK`, STD/ETD, gate, aircraft, status chip, passenger counts.
- **KPI tile:** big mono figure (26px), caption label, trend delta, optional sparkline.

### Data Tables
- Sticky header in micro uppercase on panel grey, 48px rows (36px compact), zebra off, row hover canvas tint, selected row red tint, checkbox column for bulk select.
- **Passenger row:** `APELLIDOS, Nombre`, booking code (mono), tier badge, cabin, special-service icons (UMNR, WCHR, infant, pet), connection risk, action menu.

### Airline-specific
- **Tier badge:** 4px radius, Iberia Plus colours from §2.
- **Seat map:** cabins, row numbers, exits; seat states free, occupied, blocked, selected (red), extra legroom, PRM-suitable, bassinet. Screen-reader label on every seat.
- **Stepper:** horizontal, numbered circles, red active step, check for completed steps.
- **Drawer:** 480px right drawer for detail and the AI assistant, 32% black scrim.
- **AI assistant panel:** "Asistente IA", panel-grey background. Each proposed action is a card with "what will change", rule checks and **Aprobar / Editar / Rechazar**. Nothing executes without approval; blocked actions explain the rule.

## 5. Layout Principles

- 12-column grid, 24px gutters. Max width 1440px for consoles, 1200px for passenger web. Mobile: 4 columns, 16px margins.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64.
- Radius tiers: 0 for brand bar, banners and full-bleed bands (square is the brand default); 4px buttons, inputs and badges; 6px cards, modals and toasts; 999px chips; 50% avatars and status dots.
- **Density** is an attribute: comfortable (passenger, default) vs `data-density="compact"` (agent and ops — 40px inputs, 36px rows, 44px primary buttons).
- **Theme** is an attribute: `data-theme="ops-dark"` for wall screens.
- Fixed brand bar on top, optional left navigation for consoles, detail and AI in the right drawer.

## 6. Depth & Elevation

| Level | Shadow | Use |
|---|---|---|
| Flat | none | Brand bar, banners, table rows |
| e1 | `0 1px 2px rgba(0,0,0,.08)` | Cards, KPI tiles |
| e2 | `0 4px 12px rgba(0,0,0,.12)` | Popovers, toasts, hovered flight card |
| e3 | `0 12px 32px rgba(0,0,0,.18)` | Modals, overlay drawers |

- Ops-dark deepens the shadow alphas (.4 / .5 / .6).
- Motion is minimal: 120ms colour transitions, 200ms drawer slide, `cubic-bezier(.2,0,0,1)`, no bounce; `prefers-reduced-motion` disables all.
- No imagery, textures, patterns or glassmorphism in product UI.

## 7. Do's and Don'ts

### Do
- Use Iberia red for actions and brand chrome, and keep it scarce enough that the primary action is obvious.
- Use the critical red with an icon and a label for cancelled, blocking and destructive states.
- Set every flight number, booking code, time, seat and KPI in Roboto Mono with tabular figures.
- Write Spanish first, in the formal "usted" for passenger messages: apologise once, state the facts, give the next action, give the entitlement.
- Keep agent screens compact and keyboard-first, with visible focus and shortcut hints.
- Let AI propose and humans approve — show what will change before anything executes.

### Don't
- Don't use brand red to signal errors or danger.
- Don't put gold text on white, or the brand gradient behind data.
- Don't draw or approximate the Iberia logo; use the "IBERIA" text placeholder.
- Don't show passengers internal jargon (IROPS, SSR, PNR) — say "código de reserva / booking code".
- Don't round the brand bar or full-bleed bands.
- Don't use emoji or exclamation marks in service messages, or blame the passenger or a third party.

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|---|---|---|
| Phone | ≤ 639px | Passenger web: single column, 16px margins, stacked flight options, sticky primary action |
| Tablet | 640–1023px | Gate tablets (1280×800 landscape uses desktop grid with 48px touch targets) |
| Desktop | 1024–1439px | Agent consoles: left nav + content + right drawer |
| Wall | ≥ 1440px | Ops-control boards: KPI row + table + timeline, ops-dark |

### Touch Targets
- 48px minimum on passenger and gate-tablet screens; 44px minimum for primary buttons everywhere; seat-map seats ≥ 30px.

### Collapsing Strategy
- Tables collapse to stacked passenger/flight cards on phones; the right drawer becomes a full-screen sheet; the brand bar keeps the wordmark and language toggle and moves the rest into a menu.

## 9. Agent Prompt Guide

### Quick Color Reference
- Brand / primary action: **Iberia Red** (`#D7192D`), hover **Red Dark** (`#A8191A`)
- Text: **Ink** (`#333333`); secondary **Muted Grey** (`#6B6B6B`)
- Canvas **#FAFAFA**, cards **#FFFFFF**, panels **#F5F5F5**
- Highlight fill only: **Iberia Gold** (`#FCD100`)
- Critical / cancelled: **#8E0F14** on **#FDECEC**; warning **#9A4F00** on **#FFF3E0**; success **#2E7D32** on **#E8F5E9**

### Example Component Prompts
- "Design an Iberia agent console: square red brand bar (`#D7192D`, 56px) with an 'IBERIA' text wordmark, compact data table of flights with Roboto Mono flight numbers and times, status chips with dot + label, and a 480px right drawer."
- "Create an operations-control wall screen in ops-dark (`#14161A` canvas, `#1E2127` cards): KPI tiles with mono figures, disrupted-flights table, cancelled rows marked with the critical colour plus icon and label."
- "Build an Iberia passenger mobile page: comfortable density, brand gradient hero band, white cards with 6px radius, a red primary button 'Confirmar' (48px), Spanish copy in 'usted'."
- "Compose an AI assistant drawer titled 'Asistente IA' with action cards that show what will change and Aprobar / Editar / Rechazar buttons; a blocked action explains its rule."
- "Draw an A350 seat map with exits, extra-legroom and PRM-suitable seats; selected seat in Iberia red; every seat has a screen-reader label."

### Iteration Guide
1. Lock the neutral foundation (canvas, white cards, ink) before adding red.
2. Check that brand red marks only actions and brand chrome; move every error to the critical colour.
3. Switch all operational data to mono with tabular figures.
4. Set density per surface (compact for staff, comfortable for passengers) before tuning spacing.
5. Verify contrast: muted text `#6B6B6B`, gold only as a fill, white-on-red buttons 5.2:1.

### Known Gaps
- Iberia's proprietary fonts and icon font are substituted (Montserrat, Open Sans, Material Symbols Outlined).
- Semantic colours, tier colours and the ops-dark theme are authored, not taken from iberia.com.
- No official logo or imagery is included; use the text wordmark placeholder.

# Design System Inspired by Siemens Healthineers

> Category: Professional & Corporate
> Dark-navy enterprise compliance aesthetic for health-tech and regulated-industry back-office tools: deep charcoal surfaces, signature teal primary, warm orange accent, dense data tables, and semantic status chips.

## 1. Visual Theme & Atmosphere

Deep, controlled enterprise interface for compliance and clinical-data workflows.
The tone is authoritative without being cold — the teal primary brings a clinical
precision, while the warm orange accent marks critical interactive moments. Dark
surfaces reduce eye strain during long sessions in regulated environments.

- **Visual style:** dark enterprise, compliance-grade density, clinical precision
- **Color stance:** primary teal, accent orange, full semantic status palette (success / warning / danger / info / rework)
- **Design intent:** Every element should communicate hierarchy and status at a glance. Colour conveys state; typography conveys role; spacing conveys focus.

## 2. Color

### Core palette
- **Background:** `#1a1d21` — deepest layer; body background
- **Surface:** `#242830` — card and panel backgrounds
- **Surface elevated:** `#2d3340` — hover states, active rows, raised panels
- **Sidebar:** `#1e2228` — navigation rail
- **Header:** `#0a0f14` — topmost chrome; nearly black
- **Border:** `#2f3542` — all hairline dividers
- **Foreground:** `#e0e6ed` — primary body text
- **Muted:** `#8a9ab0` — secondary text, labels, placeholders, icons

### Brand
- **Primary:** `#009999` — Siemens Healthineers teal; CTAs, active nav, links, focus rings
- **Primary dark:** `#007777` — pressed / hover-dark variant of primary
- **Primary light:** `#00bbbb` — hover-light variant; hover links
- **Accent:** `#e87722` — warm orange; critical badges, the top-chrome accent bar, destructive-action highlights

### Semantic status
- **Success:** `#28a745` — approved, released, completed
- **Warning:** `#ffc107` — pending, submitted, awaiting review
- **Danger:** `#dc3545` — rejected, error, blocked
- **Info:** `#17a2b8` — forwarded, informational
- **Rework:** `#fd7e14` — rework-requested, returned
- **Purple:** `#8e5cf6` — outdated, superseded

### Status chip backgrounds (at 18% opacity over surface)
Each semantic color produces a matching chip: background at 18% opacity,
border at 30% opacity, text at full saturation. Keep chips to `9px`
uppercase bold text; never fill a large area with a status colour.

### Application rules
- Favour Primary (`#009999`) for the single most important interactive element per view.
- Use Accent (`#e87722`) sparingly: the header chrome bar, critical badges, and
  destructive-confirmation CTAs only. Never flood a panel with orange.
- Keep body copy on Foreground (`#e0e6ed`) over Surface (`#242830`) for WCAG AA.
- Status colours communicate state only — never use them for decoration.

## 3. Typography

- **Scale (px):** 10 / 11 / 12 / 13 / 14 / 16 / 18 / 22 — desktop-first, dense
- **Body family:** `'Segoe UI', system-ui, -apple-system, sans-serif`
- **Mono family:** `'Cascadia Code', 'Consolas', 'Courier New', monospace`
- **Weights used:** 400 (body), 500 (sub-labels, table content), 600 (card titles, sidebar items), 700 (page titles, section headings, badge text), 800 (brand wordmark, KPI values)

### Type roles
| Role | Size | Weight | Colour |
|---|---|---|---|
| Page title | 18 px | 700 | Foreground |
| Card/section title | 12 px | 700 | Foreground |
| Table header | 10 px | 700 | Muted, `uppercase`, `letter-spacing: 0.05em` |
| Table cell | 12 px | 400 | Foreground |
| Sidebar item | 12 px | 500 | Muted → Foreground on active |
| Label (form) | 11 px | 600 | Muted |
| Field value | 12 px | 400 | Foreground |
| Record ID | 12 px | 600 | Primary (monospace) |
| Status chip | 9 px | 700 | Semantic (uppercase) |
| KPI value | 22 px | 700 | Foreground |
| Muted sub-text | 11 px | 400 | Muted |

Monospace is load-bearing for record IDs, mandate codes, audit timestamps,
and reference numbers — it communicates that these values are structured data,
not prose.

## 4. Spacing & Grid

- **Base unit:** 4 px
- **Tight gap:** 4–6 px (badge groups, icon+label pairs)
- **Standard gap:** 8–13 px (between form fields, table cells, card body padding)
- **Section gap:** 14–18 px (between cards, page section padding)
- **Page margin:** 24 px (consistent on all main content areas)
- **Sidebar width:** 205 px fixed
- **Header height:** 58 px fixed
- **Border radius:** 6 px (all cards, inputs, buttons, badges)
- **Chip/badge radius:** 11 px (pill shape)

Keep vertical rhythm consistent: headings have no top margin inside a fresh
section; spacing is handled by the section's padding, not the element.

## 5. Layout & Composition

- **Shell:** fixed topbar (58 px) + fixed sidebar (205 px) + scrollable main content. Never use a full-width top-nav layout for dense workbench interfaces.
- **Main content areas:** fill the remaining viewport; overflow-y scroll only inside the content pane, never the page.
- **Cards:** `Surface` background, 1 px `Border` border, 6 px radius, `0 2px 12px rgba(0,0,0,.25)` shadow. Card header: 11–12 px padding, bottom border. Card body: 16 px padding.
- **Tables:** full-width, `border-collapse: collapse`. Header row: `rgba(0,0,0,.2)` background, `2px solid rgba(0,153,153,.3)` bottom border. Row hover: `rgba(0,153,153,.04)` tint. Cell padding: `9px 13px`.
- **Forms:** two-column grid for most field pairs (`grid-template-columns: 1fr 1fr`), three-column for compact triples. Full-width for textareas and long singles.
- **Stepper sidebar:** 195 px wide, sits inside the form view, lists all sections with numbered circles and completion state.
- **Detail view:** two-column grid of `dsec` (detail section) cards, with full-width sections for long content.
- **Hierarchy signal:** use left border accent (`3px solid var(--primary)`) for active sidebar items and focused comment threads. Use bottom border accent (`2px solid var(--accent)`) for the topbar chrome.

## 6. Components

### Buttons
Four variants, all `6px` radius, `12px` font, `500` weight, `6px 13px` padding:
- **Primary (`.b-p`):** gradient `primary → primary-dk`, white text, teal glow shadow.
- **Secondary (`.b-s`):** `Surface` background, `Border` border, foreground text.
- **Success (`.b-ok`):** `Success` fill, white text.
- **Outline (`.b-o`):** transparent, `Border` border, muted text.
Sizes: `.b-xs` (2 px 7 px), `.b-sm` (4 px 10 px), default, full.
Active state: `scale(0.97)`. Disabled: `opacity 0.45`, no pointer events.

### Inputs & selects
`Background` background, 1 px `Border` border, 6 px radius, 12 px font, `7px 11px` padding.
Focus: `border-color: primary`, `box-shadow: 0 0 0 3px rgba(0,153,153,.2)`.
Error: `border-color: danger`. Disabled: `opacity 0.55`.
Selects use a custom SVG caret icon; `appearance: none`; `padding-right: 28px`.

### Status badges / chips
`.bdg` base + status modifier. All `9px` font, `700` weight, `uppercase`,
`letter-spacing: 0.03em`, `2–8px` padding, `11px` border-radius.
Ten status classes: `s-cr` Created, `s-pu` Published, `s-su` Submitted,
`s-re` Released, `s-rj` Rejected, `s-rw` Rework, `s-ca` Cancelled,
`s-dr` De-registered, `s-ou` Outdated, `s-fw` Forwarded.

### Navigation items (sidebar)
`12px` font, `7px 10px` padding, `0 5px 5px 0` margin.
Inactive: Muted text, transparent left border.
Active (`.ni.on`): Primary text, `rgba(0,153,153,.12)` background,
`var(--accent)` left border (3 px).
Hover: `rgba(255,255,255,.04)` background, `rgba(0,153,153,.4)` left border,
`translateX(1px)`.
Notification badge: `.nb` — Accent fill, 9 px white bold text.

### Cards (`.card`)
Surface background, `Border` border, 6 px radius, `0 2px 12px rgba(0,0,0,.25)` shadow.
Card header (`.ch`): `11px 16px` padding, bottom border, flex space-between.
Card body (`.cb`): `16px` padding.

### Tables (`.tbl`)
Full width, collapsed. `th`: 10 px uppercase, Muted, `rgba(0,0,0,.2)` background,
`2px solid rgba(0,153,153,.3)` bottom. `td`: 12 px, `9px 13px` padding,
`rgba(47,53,66,.4)` row separator. Row hover: `rgba(0,153,153,.04)` tint.

### Alerts
Four variants: info (`rgba(23,162,184,…)`), warning (`rgba(255,193,7,…)`),
success (`rgba(40,167,69,…)`), error (`rgba(220,53,69,…)`). Each: 1 px border,
`9px 13px` padding, 11 px font, `1.5` line-height.

### Accordion
Header: `rgba(0,0,0,.2)` background, `Border` border, 10 px 14 px padding.
Open: top border becomes Primary, radius flattens on bottom corners.
Body: `rgba(0,0,0,.08)` background, Primary side border.

### Toggle groups
Flex row, `Background` fill, `Border` border, 6 px radius, overflow hidden.
Active button: Primary fill, white text. Inactive: transparent, Muted text.

### Progress bar
3 px height, `rgba(0,0,0,.3)` track, `linear-gradient(90deg, primary, accent)` fill.

## 7. Motion & Interaction

- **View transitions:** `opacity 0 → 1` + `translateY(4px → 0)` over `180ms ease`.
  Signals "content loaded" without being distracting.
- **Hover transitions:** `150ms` for colour and background changes on nav items and table rows.
- **Button active:** `scale(0.97)` on `:active`, no transition delay.
- **Accordion:** `transform: rotate(180deg)` on the caret over `180ms`.
- **Toast:** slides up from bottom-right; auto-dismisses after 3 s.
- Respect `prefers-reduced-motion`: collapse all transitions to instant when set.
- No bounces, no large-scale animations. The user is doing compliance work.

## 8. Voice & Brand

- Tone: **precise, authoritative, process-focused.** This is a professional tool
  for regulated workflows; microcopy should use the domain vocabulary exactly.
- Use formal terms: "Registration" not "Entry", "Mandate" not "Jurisdiction",
  "Release" not "Approve", "De-register" not "Archive".
- Status labels are title-cased gerunds or past participles: "Submitted",
  "Released", "Rework", "Cancelled".
- Numbers and codes use monospace; prose uses the body font.
- Error messages are specific: name the field, state the constraint, suggest a fix.
- Never use marketing language (Amazing, Powerful, Seamless) in a workbench.

## 9. Anti-patterns

- Do not introduce off-palette hex values when an existing `:root` token covers the need.
- Do not increase body font size or spacing to look "modern" — density is intentional.
- Do not use the accent colour (`#e87722`) for more than one or two elements per screen.
- Do not display raw status strings — always use the pill-chip component.
- Do not use colour as the only differentiator for status — the chip label is mandatory.
- Do not add shadows heavier than `0 2px 12px rgba(0,0,0,.25)` on cards.
- Do not use the Primary teal for text on a dark surface at small sizes — contrast at 10 px is insufficient; use Foreground or Muted instead.
- Do not collapse the sidebar into a hamburger menu — the navigation is the primary orientation tool for dense multi-view tools.
- Do not mix the dark-surface pattern with light-mode cards — keep the entire interface in one mode.

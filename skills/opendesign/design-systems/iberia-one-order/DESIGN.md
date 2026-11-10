# Iberia ONE Order Design System

> Category: Travel & Aviation
> Dual-surface booking and operations system — consumer red (#d71920) for the booking journey, Unisys navy (#142838) and teal (#007f80) for the backend workspace.

## 1. Visual Theme & Atmosphere

Two clearly distinct surfaces share one token set. The **consumer booking interface** is clean and warm: an Iberia-red masthead, off-white canvas, white cards, and generous spacing that guides passengers through search, seat selection, baggage, and payment. The **Unisys backend workspace** is purposeful and data-dense: a deep navy sidebar, teal accent actions, pale grey panels, structured tables, and status badges that give operations staff immediate situational awareness.

Red means primary action, not danger. Brand red (#d71920) marks buttons, links, the selected seat, and the active stepper step. Cancelled items and blocking errors use a separate darker critical red, always paired with an icon and a label.

## build/theme.json — Exact key mapping (copy verbatim, do not infer)

When writing `build/theme.json`, use these values with zero substitution:

| key | value |
|-----|-------|
| primary | #d71920 |
| primary_dark | #b50f18 |
| secondary | #007f80 |
| background | #f7f6f4 |
| surface | #ffffff |
| surface_2 | #f5f5f5 |
| border | #e5e2df |
| text | #29282b |
| text_muted | #777479 |
| on_primary | #ffffff |
| font_family | "Arial", Helvetica, sans-serif |
| border_radius | 6px |
| radius_interactive | 4px |

`primary` is **always** `#d71920` (Iberia red). `#142838` (navy) is a surface color for the Unisys backend, NOT the primary. Do not swap them.

---

## 2. Color Palette & Roles

### Consumer surface
- **Iberia Red** (`#d71920`): Primary buttons, active step, selected seat, links, focus ring. 5.2:1 on white.
- **Ink** (`#29282b`): Body text, headings, labels. Near-black for maximum legibility.
- **Muted** (`#777479`): Secondary text, helper copy, inactive labels.
- **Line** (`#e5e2df`): Borders, dividers, table rules.
- **Background** (`#f7f6f4`): Canvas and page background. Warm cream. Note: CSS defines `--bg:#f7f6f4` in a second `:root` block that overrides an initial `#f6f5f3`.

### Unisys backend surface
- **Navy** (`#142838`): Sidebar, section headers, primary text on dark surfaces.
- **Teal** (`#007f80`): Interactive actions, badges, highlights in the operations workspace.
- **White** (`#ffffff`): Cards, data panels, form inputs.
- **Pale Grey** (`#f5f5f5`): Table header rows, panel backgrounds.

### Semantic
- **Success**: Green tint for delivered/confirmed status badges.
- **Warning**: Amber for pending or at-risk states.
- **Critical Red** (`#8e0f14`): Cancellations, errors, destructive actions — never the brand red.

## 3. Typography

- **Body**: Arial, Helvetica, sans-serif — 15px / 1.5 line-height. Consumer pages use 14px (`font-size:14px` override in the consumer `:root` block). Backend uses 15px.
- **Data / Codes**: Monospace face with tabular figures for flight numbers (IB 0711), booking references (IB-ORD-26002), seat codes (12A), times (09:00), and prices (EUR 280.00). Columns line up reliably.
- **Scale**: 12px labels, 15px body, 18px section headings, 22px page titles. No decorative display fonts.
- **Focus ring**: `outline: 3px solid #e3a500` (amber/gold) on `:focus-visible` for all interactive elements. Not the brand red — so focus is distinguishable from selected state.

## 4. Icon System

All icons are inline SVG, 20×20px, `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="1.5"`. Named icon set:
- `plane`, `bag`, `seat`, `check`, `user`, `shield`, `arrow`, `clock`, `search`, `info`, `card`, `layers`, `download`, `close`, `filter`

Helper: `ic(name, cls='')` returns the SVG string. Usage: `${ic('plane')}`, `${ic('bag','large-icon')}`.
Never use emoji, image sprites or external icon fonts.

## 4. Spacing & Layout

- **Base unit**: 4px. Spacing values are multiples: 4, 8, 12, 16, 24, 32, 48.
- **Card radius**: 6px. Button radius: 4px. Badge radius: 100px (pill).
- **Consumer**: Single-column centred layout, max 680px content width. Generous padding (24–32px) creates breathing room.
- **Backend workspace**: Two-column layout — 280px fixed sidebar (navy) + fluid content area. Tables use compact 8px vertical padding for data density.
- **Stepper**: Horizontal progress indicator with numbered steps; active step highlighted in red. Preserves values across Back/Next navigation.

## 5. Component Patterns

### Consumer journey
- **Search form**: Route (FROM / TO), date picker, passenger count. Red submit button spans full width.
- **Offer card**: Fare class, price per adult, combined total. Selection ring in red. Clear price hierarchy (unit price large, total secondary).
- **Seat map**: Grid of seat buttons — available, occupied (disabled), selected (red fill). Passenger and flight switcher tabs above the map.
- **Service row**: Passenger name, flight leg, service type, quantity control, price. Independent per passenger-flight combination.
- **Review table**: Passenger-by-passenger breakdown — fare, seats, bags, per-passenger total. Edit links beside each line.
- **Payment form**: Simulated card entry with acknowledgement checkbox. Single confirm button; disabled after submission.
- **Confirmation card**: Order reference, both passengers, all services, payment status (Simulated paid), delivery status (Pending).

### Unisys backend
- **Order register**: Searchable table — reference, passenger name, status, total. Search clears cleanly.
- **Order workspace**: Accepted offer summary, passengers panel, flight-service association table, financial reconciliation row (order value = payment received = EUR 667).
- **Service inspector**: Expanding row or side panel — passenger ID, flight ID, service type, seat/bag detail, charge amount, delivery position (Pending).
- **Creation history**: Timeline of illustrative events — Submitted, Validated, Created, Payment simulated, Confirmed — with timestamps clearly labelled as illustrative.
- **Status badges**: Pill-shaped, colour-coded — Created (teal), Paid (green), Pending (amber), Cancelled (critical red).
- **Filter bar**: Passenger filter + flight filter side by side; clearing either resets to full order view.

## 6. Interaction & Accessibility

- All interactive elements are keyboard-accessible with visible focus (3px solid outline, red on consumer / teal on backend).
- Disabled states are visually distinct: occupied seats greyed out, submit button dimmed after confirmation.
- Form fields use explicit `<label>` association; error messages linked via `aria-describedby`.
- Seat conflict prevention: two passengers cannot select the same seat on the same flight; the conflict is flagged inline before progression.
- Modal dialogs trap focus and expose a close control; Escape dismisses.
- Tables remain inspectable on narrow viewports via horizontal scroll with sticky first column.

## 7. Data Integrity Rules

These are design-level constraints the UI enforces visually:
- Fares charged once per passenger per round trip, never once per segment.
- Seat charge applies only when a seat is actively selected.
- Bag charge applies only to the specific passenger-flight combination chosen.
- The confirmed order snapshot is frozen; no silent re-calculation after confirmation.
- Outstanding amount after successful payment: EUR 0.00.
- Delivery positions remain Pending until physically fulfilled; never label booked services as Delivered.

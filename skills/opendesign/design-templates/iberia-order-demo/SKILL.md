---
name: Iberia Unisys ONE Order
description: |
  Offline-capable standalone HTML prototype of an airline booking and order
  management scenario (ONE Order / NDC). Consumer booking journey across seven
  screens (search, offer selection, traveller forms, seat map, baggage, review
  and confirmation) plus three Unisys backend views (order register, order
  workspace and creation history). Two adult passengers, a return MAD–LHR flight,
  seat and baggage services and a consolidated order total. Payment is simulated.
  Use when the brief asks for an airline booking flow, order management console,
  NDC/ONE Order prototype, passenger service system, or a multi-passenger
  e-commerce checkout.
triggers:
  - "airline booking"
  - "flight booking"
  - "ONE Order"
  - "NDC"
  - "seat selection"
  - "baggage"
  - "passenger booking"
  - "order management"
  - "booking confirmation"
  - "e-commerce checkout"
  - "Iberia"
  - "Unisys"
od:
  mode: prototype
  platform: desktop
  scenario: operations
  preview:
    type: html
    entry: example.html
  design_system:
    requires: true
    recommended: iberia
    sections: [color, typography, layout, components]
  craft:
    requires: [state-coverage, accessibility-baseline, laws-of-ux, form-validation]
  outputs:
    primary: prototype.html
  example_prompt: "Build an airline booking prototype — flight search, return offer with per-adult pricing, traveller forms, interactive seat map, baggage options, a passenger-by-passenger review with simulated payment, and a confirmation screen. Add a Unisys ONE Order backend showing the order register and a full order workspace with passenger and service details."
  inputs:
    - "Route (origin and destination airports), travel dates and number of passengers"
    - "Fare and ancillary service pricing (base fare, seat charges, baggage fees)"
    - "Passenger names and seat preferences"
---

Iberia × Unisys ONE Order prototype
Build an offline-capable, standalone HTML demonstration of Scenario 02. Use prototype.html as the interactive implementation reference and example.html as the completed worked example. Treat the PNGs and PDF as raster design references that can be placed in Figma, not as editable Figma source files.

## Preserve the scenario
Use English, EUR and fictional data. Keep all operations local to the browser. Do not connect live airline, availability, payment or messaging services.
Use order reference IB-ORD-26002 and accepted offer IB-OFR-26002.
Include two adult passengers: Elena Ruiz and Alex Martin.
Use outbound MAD → LHR, 10 November 2026, IB 0711, 09:00–10:25 local.
Use return LHR → MAD, 13 November 2026, IB 0712, 17:10–20:35 local.
Price the complete return economy fare at €280 per adult, €560 combined, including taxes and cabin baggage.
Assign Elena 12A on both flights and Alex 12B on both flights. Charge €18 per selection, €72 for four seats.
Assign one 23 kg outbound checked bag to Elena only, costing €35.
Keep Alex's outbound and return checked baggage at zero and Elena's return checked baggage at zero.
Produce the baseline consolidated total €667, allocated €351 to Elena and €316 to Alex.
Show final order Created, payment Simulated paid, and service delivery Pending.

## Maintain the commercial record
Store a single order containing the accepted offer, passenger entities, flight entities, services, totals and payment. Use stable passenger and flight identifiers. Associate every flight, seat and baggage entitlement with both a passenger ID and flight ID.
Use the same confirmed order snapshot for consumer confirmation and all backend views. Do not maintain separate hard-coded confirmation and backend totals. Freeze the confirmed snapshot; require a deliberate demo reset before a new booking. Store the illustrative creation events alongside the confirmed order.
Calculate totals from line items. Charge return fares once per passenger, never once per segment. Add a seat charge only for a selected seat and a bag charge only for the chosen passenger-flight combination. Keep cabin baggage independent of optional checked baggage.
Prevent two passengers from selecting the same seat on the same flight. Allow the same seat number on different flights. Apply individual edits only to the addressed passenger and flight. Label scenario-fill shortcuts clearly; changing Elena's bag individually must never apply a journey-wide bag allowance.

## Build the required views
Create seven consumer views:
1. Journey search with route, dates and two adults.
2. Return offer selection with €280 per adult and €560 combined.
3. Separate traveller forms with editable fictional details.
4. Clickable seat map with passenger and flight switches.
5. Baggage options with independent passenger and flight switches.
6. Passenger-by-flight review, edit links and simulated payment.
7. Confirmation with both passengers, their services and the single order reference.

Create three distinct Unisys backend views:
1. Order register with reference/name search, clear search and open-order controls.
2. Order workspace with accepted offer, passengers, four flight-service associations, seats, baggage, payment and delivery positions. Include passenger and flight filters, service inspection, and financial reconciliation.
3. Creation history showing submission, validation, creation, simulated payment and confirmation. Clearly label the sequence and timestamps as illustrative.

Provide separate consumer/backend demo navigation and a demo guide. Preserve draft values across Back/Next, passenger changes, flight changes and refresh where browser storage permits. Offer an explicit completed-scenario shortcut for backend exploration before booking. Make clear that it replaces the current demo draft.

## Hard rules for the Builders (pb-build)

**Sandbox constraint — NO form submission, ever.**
The prototype is previewed inside an iframe with `sandbox="allow-scripts"` (no `allow-forms`). The browser's form submission algorithm checks for this flag BEFORE firing the submit event, so `document.addEventListener('submit', ...)` is never called. Any `<button type="submit">` is completely inert in the preview.

Rule: **every button that navigates or triggers an action must use `type="button"` and a `data-action` attribute**. Handle it in the central click dispatcher. This applies to every form action button — search, traveller details, order search, payment, etc.

Do NOT use `<form>` submit events for any navigation or data capture. If you need to collect form field values before navigation, read them from the DOM directly inside the click handler. Remove `document.addEventListener('submit', ...)` entirely.

WRONG: `<button type="submit">Search</button>`
CORRECT: `<button type="button" data-action="search">Search</button>`

Click handler pattern (reads form values, persists state — navigation is handled by the `data-goto` attribute already on the button):
```javascript
case 'search': {
  state.search.from = document.getElementById('from').value;
  state.search.to   = document.getElementById('to').value;
  persist();   // save state to localStorage before the shell navigates
  // data-goto="flights" on the Search button takes the user to the next screen
  break;
}
```

These rules apply to every screen fragment in this prototype:

**Step names** — the 7 consumer steps are named exactly:
`['Search', 'Flights', 'Travellers', 'Seats', 'Baggage', 'Review & pay', 'Confirmation']`

**Stepper navigation** — every stepper step element MUST be a `<button type="button">` with a `data-goto` pointing to its own screen ID, so clicking the step navigates to that screen. Never use a `<span>` for step items — spans have no click semantics and the shell runtime will not handle them.

WRONG: `<span class="step active"><i>1</i>Search</span>`
CORRECT:
```html
<button type="button" class="step active" aria-current="step" data-goto="journey-search"><i>1</i>Search</button>
<button type="button" class="step" data-goto="offer-selection"><i>2</i>Flights</button>
<button type="button" class="step" data-goto="traveller-details"><i>3</i>Travellers</button>
<button type="button" class="step" data-goto="seat-selection"><i>4</i>Seats</button>
<button type="button" class="step" data-goto="baggage-selection"><i>5</i>Baggage</button>
<button type="button" class="step" data-goto="review-payment"><i>6</i>Review &amp; pay</button>
<button type="button" class="step done" data-goto="confirmation"><i>7</i>Confirmation</button>
```
The active screen's step button carries `class="step active"` and `aria-current="step"`. Completed steps carry `class="step done"`. All seven step buttons must appear in every consumer screen fragment so the user sees the full stepper and can navigate to any step.

**Logo** — the Iberia masthead uses an **inline SVG** for the logo, not an `<img>` tag.
The logo SVG and the full masthead are provided by `assets/template.html` (the template frame) and appear automatically in every assembled screen. You do NOT need to include the header, logo, demo-bar, or footer in your `<section class="screen">` — the template frame injects them as shared chrome.

**What the template frame provides automatically (DO NOT include in your screen section):**
- The dark demo-bar at the very top (`<div class="demo-bar">`)
- The red iberia masthead header (the `<header>` with SVG logo and toplinks)
- The white nav bar (`<nav class="mainnav">`) with Consumer/Backend navigation
- The page footer (`<footer class="footer">`) with credit line

**What your screen section MUST include:**
- The horizontal stepper (see Stepper navigation above) — this is per-screen chrome
- Your screen's page content

Do not reference an external URL or use `<img src="...">` for the logo.

**Screen architecture** — in the `prototype_v2` workflow each builder writes **one `<section class="screen" id="…">` fragment**; the assembled prototype wires all screens together via the shell's routing runtime. Screen-to-screen navigation uses `data-goto="<screen-id>"` attributes on Next / Back / step buttons — the shell shows and hides screens automatically. **Do NOT use the template's `route()`, `progressTo()` or `render()` functions for navigation** — they render into `<div id="app">` which does not exist in the assembled prototype and will conflict with the shell.

The template's **utility functions are available** in the assembled prototype (they are injected before `</body>`): `EUR()`, `E()`, `persist()`, `defaultState()`, `showModal()`, `toast()`, `lines()`. Call them from your inline script without redefining them. Do not call `route()`, `render()` or `progressTo()` — these are the template's own SPA navigation functions and will not work in the shell context.

**Consumer screen IDs** (used in `data-goto` attributes): the Architect assigns the exact IDs, but they follow the step names below. Back/Next buttons carry `data-goto` to the previous/next screen ID.

**Backend screen IDs**: the Architect assigns IDs matching `register`, `workspace`, `history`.

**Modal system** — use the native `<dialog>` element with `.showModal()` and `.close()`.
Not a custom CSS overlay. A `showModal(title, html)` helper wraps the element creation.
Every modal has an × close button and closes on backdrop click.

**Page chrome is provided by the template frame** — the template frame (`assets/template.html`) automatically injects the demo-bar, iberia masthead, white nav bar, and footer into every assembled screen. Builders must NOT include any of these in their `<section class="screen">` fragments:
- ❌ No `<div class="demo-bar">` in your section
- ❌ No `<header>` or masthead HTML in your section
- ❌ No `<footer>` in your section
- ✅ DO include the stepper (7 `<button class="step" data-goto>` elements)
- ✅ DO include your screen's page content, title, and actions

**Backend layout** — the Unisys backend uses a two-column layout. Backend screen sections include a `<div class="back-layout">` with a `<div class="side">` sidebar and a `<div class="wrap">` main area. The backend sidebar navigation (register/workspace/history) belongs INSIDE the section fragment, not in the page chrome.

**localStorage** — all state persisted to `localStorage` under a versioned key.
`persist()` writes, `defaultState()` provides the initial shape.

**Interactive widgets — write custom JavaScript.**
For the seat selection screen: JavaScript handles seat button clicks, tracks per-passenger-per-flight selections, marks seats as selected/companion/available, prevents conflicts, updates the assignment table and running total on every change.

For the baggage selection screen: JavaScript tracks radio button state per passenger per flight independently, adds/removes charges, updates the assignment table and running total.

For every consumer screen that shows a running total: recalculate from line items using JavaScript constants, not hardcoded values.

**JavaScript must be inline** in the fragment, inside a `<script>` tag. No external dependencies.

**Dropdown arrows**: every `<select>` must have `appearance: none; -webkit-appearance: none` and a custom SVG chevron as `background-image` inline in its CSS.

---

## Hard rules for the Architect (pb-design)

These rules apply when building `design.md`, `build/screens.json` and `build/theme.json`:

**Navigation structure** — the consumer interface is a horizontal numbered stepper (7 steps). The Unisys backend uses a two-column layout (sidebar + main). Specifically:
- **Consumer views**: NO left sidebar. Vertical stack only: demo toolbar → masthead → nav bar → stepper → content → footer. The template frame (`assets/template.html`) is what eliminates the sidebar — it replaces the shell's default nav structure. **Consumer screens MUST have no `section` field** in `build/screens.json` (`"section": null` or omit it entirely). Consumer screens are reached only via the stepper step buttons and Next/Back buttons — do NOT assign sections to them.
- **Backend views**: HAS a left sidebar (`back-layout` + side nav). Assign `"section": "Backend"` to register, workspace and history screens so they appear as nav items in the top horizontal bar under a "Backend" heading.

**Exact screen IDs for build/screens.json** — consumer screens must use these exact IDs so stepper `data-goto` links work:
- `journey-search` (step 1 — Search)
- `offer-selection` (step 2 — Flights)
- `traveller-details` (step 3 — Travellers)
- `seat-selection` (step 4 — Seats)
- `baggage-selection` (step 5 — Baggage)
- `review-payment` (step 6 — Review & pay)
- `confirmation` (step 7 — Confirmation)

Backend screens: `order-register`, `order-workspace`, `creation-history`.

**CRITICAL: `section` field rules for build/screens.json:**
- Consumer screens (`journey-search`, `offer-selection`, `traveller-details`, `seat-selection`, `baggage-selection`, `review-payment`, `confirmation`): **MUST have NO `section` field** — do not set `"section"` at all. Setting any value (even `"consumer"` or `"consumer-booking"`) causes an unwanted section tab strip to appear above each screen.
- Consumer screens are reached ONLY via the stepper step buttons and Next/Back buttons, not via any section navigation.
- Backend screens only: set `"section": "Backend"` on `order-register`, `order-workspace`, `creation-history` only.

**Shell layout** — the template frame (`assets/template.html`) replaces the shell's default header, nav, and footer with the iberia masthead, white navigation bar, and iberia footer. The assembled prototype layout is: demo-bar → iberia masthead → white mainnav → per-screen stepper → screen content → iberia footer. There is no horizontal split and no aside. The shell's `#slot-nav` is made transparent by the template frame (`display:contents`) and the nav items it contains appear inside the iberia `mainnav` as horizontal links.

**Theme** — copy the `build/theme.json` mapping table from the DESIGN.md exactly. `primary` is `#d71920`. Do not infer a primary color from the design system prose.

---

## Apply the visual direction
Inspect Iberia.com's live public design before major visual revisions. Use the red masthead, white navigation, prominent flight search, destination photography and booking progression as references. Credit their source as Iberia.com. Keep the consumer interface explicitly identified as an independent concept demo.

Logo and image assets:
- **Iberia masthead logo**: Use the inline SVG from the template's `example.html` `header()` function. The SVG encodes the full Iberia wordmark (white text + yellow bird) and is embedded directly — do not use an `<img>` tag or external URL.
- **London destination hero image**: `https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=1200&q=80` as CSS `background-image` on the hero section, `cover`, centered.

Add a small credit line in the page footer: "Logo source: Iberia.com · Images: Unsplash · Independent concept demonstration."
Use warm white surfaces, restrained borders, generous spacing, readable flight times, red primary actions and clear price hierarchy. Use the existing consumer red #d71920 as a prototype token, rather than claiming it is a verified official brand specification.
Keep Unisys operations visually distinct with navy #142838, teal #007f80, pale grey backgrounds, status badges, structured tables and service inspection. Make the payment and delivery positions distinct.
Use labelled form fields, keyboard-accessible buttons, visible focus, real disabled states for unavailable seats, modal close controls and responsive layouts. Ensure tables remain inspectable on narrow displays. Implement every displayed action; avoid placeholder links or decorative buttons presented as functional controls.

## Simulate payment and state transitions
Require an acknowledgement that the booking is simulated. Use an internal demo token instead of real card details. Permit a declined-payment demonstration that preserves the draft and supports retry. Create the confirmed record only on successful simulation. Disable submission repetition after confirmation.
Record one consolidated simulated payment against the order. Keep the outstanding amount zero after successful payment and keep every service delivery position Pending. Do not label booked services as delivered.

## Validate before delivery
Check the actual UI as well as the data model:
- Confirm the €560 → €632 → €667 progression.
- Verify all four seat associations and same-flight seat conflict prevention.
- Remove Elena's outbound bag: expect €632; verify all other baggage entitlements stay zero. Restore it: expect €667.
- Change each passenger-flight bag separately; verify only that association and totals change.
- Confirm the review allocates €351 to Elena and €316 to Alex for the baseline.
- Test Back/Next, review edit links, field validation, passenger and flight switches, modal dismissal, reset and saved-state recovery.
- Test unsupported search inputs with a clear mock-scenario explanation and a restore-scenario action.
- Test declined payment, retry and successful confirmation.
- Match order reference, passengers, services, totals and statuses between confirmation and backend.
- Search/open the order, filter a passenger and flight, inspect their services and reconcile €667 payment against €667 order value.
- Check the five creation-history events and their order.
- Check generated HTML has inline styles, scripts and assets and no required external runtime dependencies.

Reference visuals: https://www.iberia.com/gb/ and https://www.iberia.com/gb/destination-guide/london/ (reviewed 4 November 2026).

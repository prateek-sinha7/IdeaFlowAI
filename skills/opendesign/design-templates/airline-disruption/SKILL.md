---
name: Airline Disruption
description: |
  Pipeline-ready rebuild of the Iberia Disruption Recovery Hub: the same look,
  frame, fonts and role simulator as the original, organised as one labelled
  pattern per screen with shared classes, so prototype builds reproduce it.
  A desktop operations console for recovering passengers when flights are
  cancelled, delayed or diverted — ten screens across five simulated roles:
  disruption board, flight impact by priority band, AI re-accommodation planner
  with a human approval gate, advance check-in, care & compensation, passenger
  communications, mobile self-service, passenger recovery card, agent desk and
  supervision & audit. Spanish/English. Use when the brief asks for an
  operations control centre, irregular-operations recovery, incident triage or
  any role-based console where staff review AI proposals before they execute.
triggers:
  - "disruption"
  - "irregular operations"
  - "IROPS"
  - "flight cancellation"
  - "rebooking"
  - "re-accommodation"
  - "operations control"
  - "recovery console"
  - "airline operations"
od:
  mode: prototype
  platform: desktop
  scenario: operations
  preview:
    type: html
    entry: example.html
  design_system:
    requires: true
    sections: [color, typography, layout, components]
  craft:
    requires: [state-coverage, accessibility-baseline, laws-of-ux, form-validation]
  outputs:
    primary: prototype.html
  example_prompt: "Build a disruption recovery console for an airline hub — disruption board, flight impact by priority band, AI rebooking planner with approval, EU261 calculator, passenger recovery card and a mobile self-service page."
  inputs:
    - "The operation being recovered (station, date, causes) and who runs it"
    - "The disrupted flights and the passengers on them, with priority groups"
    - "The rules the recovery must respect (passenger rights, minimum connection times, vulnerable passengers)"
    - "Which actions need a human approval before they are applied"
---

# Airline Disruption

## What this template is

A data-dense desktop console for an operations team recovering from disruption, plus one
mobile view for the people affected. Staff watch a live board, drill into one event, let an
AI assistant propose a recovery plan, approve it, and settle entitlements. It is compact,
keyboard-friendly and built for long shifts: calm surfaces, one accent colour for actions,
operational data set in the monospace face.

## Chrome

- **Brand bar** (56px, full width, accent fill, square corners): wordmark, product name, then
  on the right an environment badge, the live station clock, a language toggle and the signed-in
  user with role.
- **System banner** directly under the brand bar, full width, only while an integration is
  degraded: what failed, since when, that actions are queued, and a link to the queue.
- **Account control** at the right end of the brand bar: avatar, name and role. It opens a
  "Simulate role" menu; each role has its own home screen and its own set of screens, and
  role decides what a user may do (who approves, who only requests approval).
- **Language toggle** (ES / EN) in the brand bar; every label, message and number format
  follows it.
- **Left navigation** (~232px): the operating context on top (date · station · terminals),
  numbered sections (01, 02 …) with icons — only the screens the current role may use, in that
  role's order — the active item marked with a left accent border and tinted background, and a
  pinned footer showing the count of queued actions. Hidden for the passenger role.
- **Content area** fills the rest with 24px padding. Each screen opens with an H1 and one muted
  line of context.

## How the example is organised

`example.html` is the original console, rebuilt so a prototype build can copy it exactly:

- **Frame**: the brand bar, the system banner and the numbered left navigation sit outside
  `<main class="main">`. Navigation items are `button.nav-item` (the active one also
  `is-active`); its look comes from the `.nav-item.is-active` rule, never from the item itself.
- **Patterns**: inside `<main>`, one `<section class="pattern" data-pattern="…">` per screen kind,
  each opening with a comment naming what it is for: `board`, `impact`, `planner`,
  `planner-approved` (the state after approval), `approval-dialog`, `checkin`, `care`, `comms`,
  `card`, `desk`, `audit`, `self-service` (inside the phone frame), `role-switcher` (the account
  menu that simulates roles), `demo-states` (the one row for review-only state controls) and
  `field-group` (labelled inputs in a two-column grid, for the rare value a user must type). Build each screen of the product from the pattern of the same kind:
  same markup, same classes, real content from the brief.
- **Look**: every element is styled by classes. The `drc-*` classes are the original's own
  styles, one class per distinct style; `ib-*` are the design system's components. Never write a
  `style=` or invent a class: the same pattern in the example already has the class you need.
- **Theme**: colours and fonts resolve through `--accent`, `--accent-hover`, `--accent-on`, `--bg`,
  `--surface`, `--surface-warm`, `--fg`, `--fg-strong`, `--muted`, `--border`, `--border-soft`,
  `--font-display`, `--font-body`, `--font-mono`, so any design system re-themes the whole console.
  Fonts (Montserrat, Open Sans, Roboto Mono — the stand-ins for Iberia's proprietary faces) and the
  Material Symbols icon font load from the template's own stylesheet.

## Role simulator

The console is one product seen by five roles. Each role has a person, a home screen and its own
screens, in this order; the account menu switches between them (pattern `role-switcher`):

| Role | Person | Home | Screens |
|---|---|---|---|
| Duty manager | Marta Valcárcel — Hub Control Centre, approves batches and PSS writes | board | board, impact, planner, care, comms, card, audit, self |
| Recovery agent | Jordi Puig — T4S desk K3, rebooks and checks in, requests batch approval | desk | desk, card, impact, planner, checkin, care |
| Care specialist | Lucía Fernández — customer care, compensation, vouchers and comms | care | care, comms, card, self |
| Supervisor | Javier Morales — shift supervision, approvals, team and audit | audit | audit, board, desk, planner |
| Passenger | Sofía Herrera — what she sees on her phone | self | self (no left navigation) |

This template is a multi-role console: ALWAYS build the role simulator, with these five roles
unless the brief names its own. Give every role the same treatment: a person,
a home screen, the screens it may use, and what it may and may not do (who approves, who only
requests approval).

How to build the simulator with plain screens and links (no script):

- Add one page, **Choose role** (`role-select`, the entry page), built from the `role-switcher`
  pattern: one row per role with its avatar initials, person, role name and one line on what it
  does. Each row is a control that goes to that role's home screen.
- Every role's home screen opens with a one-line role strip under its heading — "Signed in as
  <person> · <role>" with a "Switch role" control back to `role-select` — so whoever is
  reviewing always knows which simulator they are in.
- A screen only one role uses says so in that strip; actions a role may not take are shown
  disabled with the reason ("Your role requests approval; the duty manager approves").
- The passenger role's home is the mobile self-service screen.

## Screen patterns

1. **Board (dashboard).** A row of 6 KPI tiles (label, big monospace figure, coloured delta
   line). Below, a two-column split: the main table of affected items (~1fr) with a segmented
   status filter and a search box in its header, and an alerts panel (~300px) listing
   timestamped alerts with a severity label and icon.
2. **Impact (grouped list).** H1 with the item identifier and a status chip, a summary line,
   then a row of priority-band pills with counts. The table is grouped by band: a band header
   row (numbered circle + band name + count) followed by its rows. Rows that travel together are
   one row. A selection bar above the table states what is selected and holds the primary action
   that moves the selection to the planner.
3. **Planner (AI proposals + approval).** Three columns: a strategy panel (~280px: priority
   slider between two goals, permission checkboxes, the list of hard rules that can never be
   broken) and two or three proposal cards. Each card: lettered title, a "Recommended" badge on
   one, the moves it makes, a 2×2 metrics block (delay, match, cost, liability), a plain-language
   "Why" and a choose button. A blocked option appears with a dashed critical callout naming the
   rule that blocks it. A full-width approval bar closes the screen: nothing is applied until a
   human approves.
4. **Calculator (rules made visible, no form).** Left: a fact strip (event, distance, cause, notice), the
   resulting amount in a large monospace figure with a readable explanation, then one row per
   rule with its result on the right (MET / NO / N/A / DUE), then reference bands with the
   applicable one highlighted. Right: action cards (issue vouchers) and an inventory table with
   capacity bars. The case is picked, not typed: the passenger or flight comes from the screen
   it was opened from (or a search box plus recent pills, as `card` does); distance, times and
   cause are shown as facts and the amount is already computed. Show the second case (e.g. an
   extraordinary-circumstance flight) as a second case tab or a `demo-states` button.
5. **Record card (detail).** Search box plus recent-item pills, then one card: avatar, name,
   identifiers and status chip; old → new comparison (old dashed and struck through, new with
   an accent border); three columns of facts (services and companions, entitlements and
   vouchers, messages sent); an action row with one primary and several secondary buttons.
6. **Self-service (mobile, 390px).** Shown inside a phone frame beside a short explanation:
   greeting, the airline's decision as the headline, a "what happened" card, the chosen option in
   a selected card with the primary action, then other options as tappable rows, then the
   entitlements and the refund route.

7. **Check-in (work list).** Selectable flight cards on the left (progress bar, "n of N
   checked in"), options as checkboxes below; on the right the groups of the selected flight
   with seats, a note and a per-row action, plus a whole-flight action.
8. **Composer (message + preview).** Template pills, language segment, channel checkboxes,
   editable text with variables, live preview with character count, recipients line and send;
   a delivery-status table below.
9. **Desk queue.** KPI row, then a queue table ordered by priority band and wait, one
   "Serve" action per row that opens the passenger's record.
10. **Supervision.** Pending-approval cards (approve / reject, locked for roles that cannot
    decide), a team-on-shift table and a read-only, hash-chained audit log where every action
    taken anywhere in the console appears as a new row.

The example implements the roles: duty manager, recovery agent, care specialist,
supervisor and passenger. Build the same role switch when the brief names more than one kind
of user.

## Components

- **KPI tile**: label, monospace figure, one-line delta coloured by direction.
- **Status chip**: pill with dot or icon plus an uppercase label; cancelled/critical, delayed/
  warning, on time/success, diverted or rebooked/info.
- **Data table**: sticky uppercase header on the panel surface, 40px rows, zebra off, selected
  rows tinted with the accent, group header rows for bands.
- **Segmented control** for mutually exclusive filters; **pills** for multi-select or recents.
- **Proposal card** with metrics block and "Why" text; selected card gets an accent border and
  ring.
- **Tier badge** for loyalty levels; the top tier uses the highlight colour as a fill.
- **Capacity bar** for inventory (hotel rooms, seats).

## Content voice

Real operational values, never placeholders: flight numbers like IB3166, routes as
`MAD → LHR`, 24-hour times with the station code (`11:42 MAD`), six-character booking codes,
passenger names as `SURNAME, Given name` in staff views, money as `€18,400`. Staff copy is
terse and data-first; passenger copy is plain, apologises once, states the facts, gives the next
action and the entitlement, and never shows internal codes.

## Interactions (every control does something visible)

Every button, chip, row and filter in `example.html` is wired with the attributes below — copy
them with the markup. A control that does nothing, or only shows a toast while the screen stays
the same, is wrong for this template.

| Attribute | What it does | Example in the template |
|---|---|---|
| `data-goto="<screen>"` | Opens another screen | table row → its detail, primary action → the next step |
| `data-submit="<screen>"` | Confirms and moves on | "Confirm and run" in a dialog → the approved state |
| `data-opens` / `data-closes` | Opens / closes a dialog or popover | "Approve" → summary dialog; account control → role menu |
| `data-show` / `data-hide="<id>"` | Reveals / hides an in-screen state (`class="state"`) | issued voucher appears, "Sent" banner, confirmation |
| `data-done="<label>"` | The button becomes its result and its row or card turns success | "Check in" → "Checked in" |
| `data-done-all="<selector>"` | Marks every matching row or button done | "Check in whole flight", "Approve pending" |
| `aria-pressed` | Single choice in a group; the selected look moves to the chosen item | segmented filters, case tabs, language, seats |
| `data-filter` / `data-search` with `data-tags` on rows | Filters the rows of the list in place | status segments, "With issues", search box |
| `data-choose` | Picks one card among several; the chosen card gets the accent ring | proposal cards |
| `data-select-all` | Selects every row checkbox | "Select all" |
| `data-count="<name>"` | Adds one to every `[data-counter=<name>]` figure | queued actions, boarded |
| `data-log="<text>"` | Adds the action as a new top row of the audit log (`[data-audit-log]`) | every approval, voucher, message |
| `data-role` + `data-role-title` + `data-role-screens` | Switches the simulated user: header name and role change, the menu keeps that role's screens | role menu rows |
| `data-toast="<text>"` | Confirms the action in a toast | alongside one of the above, never alone |

Rules: every action changes the screen (state, row, counter, log or another screen) and may add a
toast; nothing is a dead button. Results are pre-built in the markup as hidden `state` elements
and revealed — never described only in a toast.

## Hard rules

- DATA, NOT FORMS. This console SHOWS operational data: KPI tiles, fact grids (small uppercase
  label above a value), tables, chips, cards and timelines. A record, a passenger, a flight or a
  plan is shown as read-only text in those components — never as a column of input boxes.
  Inputs exist only where the original has them: the search box, filter segments and checkboxes,
  the calculator's few inputs (`care`), the message text and channel picks (`comms`), the
  planner's constraints. A screen with more than four text inputs is wrong for this template.
- MENU. One numbered left-navigation item per screen, in the role's order from the table above —
  never group screens into a few sections with page tabs. In the screen plan give every screen
  its own nav entry and section and no tab; a screen reached only from another (an approval
  dialog, a state) is not a menu item.
- ONE CONTROL PER CHOICE. Choosing between plans or options uses the planner's proposal cards
  (one Choose button per card, the chosen card gets the accent border) or tappable option rows
  in the phone — never a radio table, and never a radio button plus a Select/Choose button for
  the same option. A selectable table row has one checkbox column, no second selector.
- DEMO STATES. A control that exists only so a reviewer can see a state (empty list, warning,
  approved, error) goes in the `demo-states` bar at the top of the screen body, copied from that
  pattern — never as a loose text button in the content. Real actions that change a state
  (Approve, Choose, Calculate) stay where the pattern puts them and reveal the state themselves.
- INPUTS, WHEN UNAVOIDABLE, use the `field-group` pattern: `ib-field` labels over `ib-input`
  controls in the two-column `field-grid`, inside a card with its actions bottom right. Never a
  single column of full-width inputs, never an input for a value the screen already knows —
  show it as a fact (`ib-kv__k` label over `ib-kv__v` value) instead.
- FILTERS are never a form. A list or board filters with the pattern's segmented control
  (All / Cancelled / Delayed / …), a checkbox chip and a search box, all in the table panel's own
  header row — exactly as `board` does. No filter card, no column of dropdowns, no date pickers.
- A screen's facts (event, cause, station, times) sit in the pattern's fact grid or summary line
  under the heading, never as a list of bare label / value lines.
- SPACING. Every screen's content sits inside one `<div class="screen-body …">` copied from its
  pattern (24px padding, 16px between blocks); inside it, group content in the pattern's own
  card / panel wrappers, which carry their padding, border and gap. Never stack bare headings,
  labels and values directly in the screen, and never add margins of your own.

- The passenger / mobile / self-service screen is ALWAYS drawn inside the phone frame: copy the
  `self-service` pattern's markup (phone bezel, status bar, brand header, content) and put the
  explanation beside it, exactly as the pattern does. Never a plain desktop page.
- Every console screen copies the pattern of its kind whole — header line, chips row, selection
  bar, grouped table, alerts rail — not only its table.

- The accent marks actions, the brand bar and the current selection — never errors. Cancelled,
  blocking and destructive states use the danger colour with an icon and a label.
- Every identifier, time, seat and figure is in the monospace face with tabular numbers.
- AI output is always a proposal: shown with its reasoning, blocked when it breaks a hard rule,
  and applied only after an explicit human approval.
- States: loading uses skeleton rows in tables and tiles; empty tables say what would appear
  and why it is empty; errors appear in the system banner or inline next to the field; disabled
  buttons keep their label and explain why in a tooltip or helper line.
- No decorative imagery, gradients or illustrations inside the console.

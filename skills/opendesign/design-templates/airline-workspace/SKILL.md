---
name: Airline Workspace
description: |
  Pipeline-ready rebuild of the Iberia Airport Agent Workspace: the same look, frame,
  fonts and role simulator as the original, organised as one labelled pattern per screen
  with shared classes, so prototype builds reproduce it. A keyboard-first desktop workspace
  for airport agents on top of a legacy passenger system — sign-in and position, agent home
  with search, passenger record, guided check-in (documents, seats, bags, payment, boarding
  pass), seat map, special assistance, an AI assistant whose actions need approval, gate
  boarding, supervisor board, passenger list and audit log, across four simulated roles.
  Use when the brief asks for a front-line agent or counter workspace, check-in or boarding,
  a record-centred operations tool, or any console where an AI assistant proposes actions
  an agent approves.
triggers:
  - "check-in"
  - "boarding"
  - "airport agent"
  - "counter"
  - "gate"
  - "passenger record"
  - "agent workspace"
  - "seat map"
  - "special assistance"
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
  example_prompt: "Build an airport agent workspace — sign-in and position, passenger search, passenger record, guided check-in with document checks, seat map, special assistance, an AI assistant with approvals, gate boarding and a supervisor board."
  inputs:
    - "The station, the position (counter, gate, transfer desk) and the agent's role"
    - "The flights at that position and the passengers to serve, with their documents, seats and bags"
    - "The rules each step enforces (documents, exit rows, bag allowance, assistance, cut-offs)"
    - "Which actions the AI assistant may propose and who approves them"
---

# Airline Workspace

## What this template is

A compact, keyboard-first workspace for front-line agents serving one passenger at a time,
on top of a reliable but old system. The agent finds a passenger, sees the whole record at a
glance, is guided through check-in step by step, and approves what an AI assistant proposes.
Everything shown is a fact from the system; the agent confirms, scans or picks — rarely types.

## Chrome

- **Brand bar** (56px, accent fill, square): wordmark, product name ("Agent workspace"), then on
  the right an environment badge, the local station clock, an ES / EN toggle and the account
  control (avatar, person, position).
- **Account control** opens the role menu (`role-switcher`): one row per role with avatar,
  person and position; choosing one changes the menu, the home screen and what the user may do.
- **Left navigation** (~232px, white): "Navigation" label, one item per screen with an icon,
  the label and its keyboard shortcut (`Alt 1` …) on the right; the active item tinted with the
  accent. A pinned "Shortcuts" note at the bottom.
- **Content area** on the light canvas; each screen's content sits in `screen-body`.

## How the example is organised

`example.html` is the original workspace, rebuilt so a prototype build can copy it exactly:

- **Frame**: the brand bar, account control and navigation sit outside `<main class="main">`.
  Navigation items are `button.nav-item` with `data-go` naming their pattern; the active one also
  `is-active`, whose look comes from the `.nav-item.is-active` rule.
- **Patterns**: inside `<main>`, one `<section class="pattern" data-pattern="…">` per screen kind,
  each opening with a comment naming what it is for: `sign-in`, `home`, `passenger`, `checkin`
  (step 1, documents), `checkin-seats`, `checkin-bags`, `checkin-payment`,
  `checkin-boarding-pass`, `seat-map`, `assistance`, `assistant` (the AI drawer with action
  cards), `boarding`, `supervisor`, `passenger-list`, `audit`, `role-switcher` (the account menu),
  `demo-states` (the one row for review-only state controls) and `field-group` (labelled inputs
  in a two-column grid, for the rare value an agent must type). Build each screen of the product
  from the pattern of the same kind: same markup, same classes, real content from the brief.
- **Look**: every element is styled by classes. The `aw-*` classes are the original's own styles,
  one class per distinct style; `ib-*` are the design system's components. Never write a `style=`
  or invent a class: the same pattern in the example already has the class you need.
- **Theme**: colours and fonts resolve through `--accent`, `--accent-hover`, `--accent-on`, `--bg`,
  `--surface`, `--surface-warm`, `--fg`, `--fg-strong`, `--muted`, `--border`, `--border-soft`,
  `--success`, `--warn`, `--danger`, `--info`, `--font-display`, `--font-body`, `--font-mono`, so
  any design system re-themes the whole workspace. Fonts (Montserrat, Open Sans, Roboto Mono —
  stand-ins for Iberia's proprietary faces) and the Material Symbols icon font load from the
  template's own stylesheet.

## Role simulator

| Role | Person | Home | Screens |
|---|---|---|---|
| Check-in agent | Pilar Sánchez — Counter 812 | home | sign-in, home, passenger, check-in, seat map, assistance, AI assistant, passenger list |
| Gate agent | Raúl Domínguez — Gate S28 | boarding | sign-in, passenger, seat map, boarding, passenger list |
| Station supervisor | Elena Ortiz — T4S supervision | supervisor | every screen, plus supervisor and audit log |
| Trainee agent | Nerea Gil — Counter 813 (guided mode) | home | sign-in, home, passenger, check-in, seat map, assistance, AI assistant |

ALWAYS build the role simulator, with these roles unless the brief names its own:

- Add one page, **Choose role** (`role-select`, the entry page), built from the `role-switcher`
  pattern: one row per role with avatar initials, person, role and position. Each row goes to
  that role's home screen.
- Every role's home screen opens with a one-line role strip — "Signed in as <person> · <role>"
  with a "Switch role" control back to `role-select`.
- Actions a role may not take are shown disabled with the reason ("Only the supervisor can
  authorise an override").

## Screen patterns

1. **Sign-in & position.** One card: station name, title, one line on the session, one SSO
   action. Beside it, station messages as banners (warning / info). The position (station,
   terminal, counter, printer) is shown as facts once signed in — never a form of agent details.
2. **Home.** A search / scan card (one box, Search, Scan passport, "Try:" chips), a row of four
   KPI tiles, then the flights at this position as flight cards (number, status chip, route with
   cities and times, gate, aircraft, pax, checked-in) each with its counter open / close line.
3. **Passenger record.** Read-only header: SURNAME, Given name, status chip, booking, e-ticket,
   nationality, flight, alert chips on the right. Then two columns: itinerary card and baggage
   allowance table; documents (pass ticks with the detail), companions, special services,
   history. A sticky action bar: primary "Start check-in", secondary actions, AI assistant.
4. **Guided check-in.** Title with passenger and flight, counter-close time, a 5-step stepper.
   Each step shows what was checked, not a form: documents as PASS / FAIL rows with detail and
   the scanned MRZ; seats on the map with the rule checks; bags as rows with weight, allowance
   and fee and the total; payment by item with the card-terminal action; the boarding pass
   summary with print / Wallet. Back and Continue at the bottom. A failing check blocks
   Continue and offers "Request supervisor override".
5. **Seat map.** Cabin grid by class with exits and seat states (free, occupied, blocked,
   selected, extra legroom, PRM-suitable, bassinet); passenger switch chips; a side card with
   current / selected seat and the rule checks, and one confirm action.
6. **Special assistance.** Passenger header with service chip; mobility aid as choice chips and
   one capacity field; the rule result in a success / danger callout naming the rule; the
   request card with status and one send action; companions.
7. **AI assistant.** Right drawer: the agent's request, then one action card per proposal —
   what will change, the rule checks, the system transaction, Approve / Edit / Reject. A blocked
   card is marked in the danger colour with the rule and a suggested alternative.
8. **Gate boarding.** Flight header with a gate-close countdown, count tiles (booked, checked
   in, boarded, missing, standby), bag reconciliation, special services on board, inbound
   connections, boarding group progress, scan box, missing passengers with location, bags and
   offload, upgrade list, and a bottom bar with gate-check, offload and "Close flight".
9. **Supervisor.** KPI tiles, counters as small status cards (open, long queue, printer fault,
   closed), an escalations queue with resolve / reject per item, and a gates table.
10. **Passenger list.** Title with flight and counts, filter chips and search in the header, one
    row per passenger with tier badge, booking, cabin, seat, service icons and connection /
    status, and a row menu.
11. **Audit log.** Read-only, time-ordered rows: time, who, what, the system transaction.

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

- DATA, NOT FORMS. The workspace SHOWS the passenger system's data: facts, chips, tables, cards
  and check results. A passenger, flight, document or bag is read-only text in those components —
  never a column of input boxes. Inputs exist only where the original has them: the search /
  scan box, the seat on the map, the mobility-aid capacity, the AI request, a boarding-pass
  scan. A screen with more than four text inputs is wrong for this template.
- CHECKS, NOT ENTRY. Check-in steps show what was verified (PASS / FAIL with the detail and the
  rule) and the agent confirms with Continue. Never ask the agent to retype what the system or a
  scan already knows.
- MENU. One navigation item per screen, with its icon and `Alt n` shortcut, in the role's order —
  never group screens into sections with page tabs. In the screen plan give every screen its own
  nav entry and section and no tab; the check-in steps are one screen with a stepper, and
  dialogs or states are not menu items.
- ONE CONTROL PER CHOICE. Seats are picked on the map; proposals are action cards with Approve /
  Edit / Reject; options are chips. Never a radio button plus a button for the same choice.
- DEMO STATES. A control that only reveals a state for review (document fails, bag over limit,
  flight closed) goes in the `demo-states` bar at the top of the screen body — never as a loose
  text button. Real actions reveal their own result.
- INPUTS, WHEN UNAVOIDABLE, use the `field-group` pattern: `ib-field` labels over `ib-input`
  controls in the two-column `field-grid`, inside a card with its actions bottom right.
- FILTERS are chips and a search box in the list's own header — never a filter form.
- SPACING. Every screen's content sits inside one `<div class="screen-body">` (24px padding,
  16px between blocks); group content in the pattern's own cards. Never stack bare headings,
  labels and values, and never add margins of your own.
- Rule results are explicit: pass in the success colour, blocked in the danger colour with an
  icon, the rule text and the next action. The accent marks actions and the current selection —
  never errors.
- Every identifier, time, seat, weight and amount is in the monospace face.
- The AI assistant never acts on its own: every proposal shows what will change and the system
  transaction, and waits for Approve.
- No decorative imagery, gradients or illustrations.

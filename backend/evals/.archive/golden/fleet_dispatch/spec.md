<spec>
# Prototype Specification: Harbor Line Freight — Dispatch Console

## Template & Design System
- **Template**: none active — blank-canvas mode, full class system defined below
- **Design System**: Terminal Blue — cool neutral surfaces, deep freight-blue accent, high-contrast status badges, dense tabular layout built for a dispatcher scanning eighteen trucks at a glance
- **CSS Class System**: `.sidebar`, `.brand`, `.nav-link`, `.main`, `.page`, `.page-header`, `.page-title`, `.page-sub`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.row-link`, `.trip-link`, `.badge`, `.badge-enroute`, `.badge-loading`, `.badge-delayed`, `.badge-delivered`, `.card`, `.card-title`, `.grid-2`, `.detail-list`, `.timeline`, `.back-link`, `.delay-note`, `.form-group`, `.form-label`, `.form-input`, `.btn`, `.btn-primary`, `.empty-note`, `.save-note`
- **Color Tokens**: --bg=#f5f6f8, --fg=#16212e, --accent=#0b5fad, --surface=#ffffff, --border=#dce2e9, --muted=#5d6b7a, --ok=#1a7f37, --warn=#9a6700, --danger=#b3261e

## Overview
- **Product**: Internal day-of-operations dispatch console for Harbor Line Freight, an 18-truck regional carrier running lanes across California, Oregon, Nevada and Idaho
- **Target audience**: The two dispatchers on the Oakland Central Terminal day desk
- **Core purpose**: Watch every live trip on one board, drill into any trip's stops and check-ins, close out deliveries, and keep exceptions, driver duty status and tractor assignments consistent without re-keying anything
- **Total pages**: 6 (Board, Trip Detail, Drivers, Vehicles, Exceptions, Settings)

## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| board | `#/board` | Today's live trip table with search and status filters | toolbar + full-width table | Yes |
| trip-detail | `#/trip/:id` | One trip's facts, check-in timeline and delivery action, rendered for the clicked row | two-column detail cards | No |
| drivers | `#/drivers` | Duty roster with each driver's computed current trip and status | full-width table | No |
| vehicles | `#/vehicles` | Tractor fleet list with computed trip assignment per unit | full-width table | No |
| exceptions | `#/exceptions` | Only the Delayed trips, with reasons and slipped ETAs | full-width table | No |
| settings | `#/settings` | Dispatch desk preferences | stacked form card | No |

## Page Specifications

### Board (`#/board`)
**Layout**: toolbar (search + status filters) above a full-width trip table
**Template classes**: `.page-header`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.row-link`, `.trip-link`, `.badge`, `.empty-note`
**Components**:
  - Search box: text input, placeholder "Search driver or destination…", filters table rows as the user types (case-insensitive match on driver name and destination city)
  - Status filter: five buttons — All, En route, Loading, Delayed, Delivered — exactly one active at a time; combines with the search text (both conditions must hold)
  - Trip table: columns [Trip, Driver, Lane, Cargo, Weight, ETA / Delivered, Status], 8 rows for Tuesday 17 Mar 2026, rendered from the store:
    - TRP-7300, Tessa Grant, Oakland, CA → Hayward, CA, Shrink-wrapped appliance pallets, 12,900 lbs, Delivered 07:45, Delivered
    - TRP-7301, Marcus Bell, Oakland, CA → Reno, NV, Packaged beverages, 34,800 lbs, ETA 15:40, En route
    - TRP-7302, Dana Okoro, Stockton, CA → Fresno, CA, Palletized building materials, 41,200 lbs, ETA 18:20, Loading
    - TRP-7303, Felix Munoz, Portland, OR → Boise, ID, Chilled produce (reefer at 34°F), 37,600 lbs, ETA 21:45, Delayed
    - TRP-7304, Priya Nair, Salem, OR → Eugene, OR, Retail cartons, 18,950 lbs, Delivered 10:22, Delivered
    - TRP-7305, Jonah Reyes, Reno, NV → Elko, NV, Mining machinery parts, 22,300 lbs, ETA 17:05, En route
    - TRP-7306, Tessa Grant, Oakland, CA → San Jose, CA, E-commerce parcels, 26,450 lbs, ETA 16:50, Delayed
    - TRP-7307, Priya Nair, Eugene, OR → Salem, OR, LTL consolidation (backhaul), 4,100 lbs, ETA 19:40, Loading
  - Empty-state note: when search + filter match nothing, one row spans the table saying "No trips match."
**Interactions**:
  - typing in search → table re-filters on every keystroke
  - clicking a filter button → re-filters and moves the active highlight to that button
  - clicking any trip row → navigates to `#/trip/{that row's trip id}`
  - a trip delivered from Trip Detail shows its Delivered badge here immediately on return — same store, re-rendered on every navigation

### Trip Detail (`#/trip/:id`)
**Layout**: back link, page header with the trip id and lane, then two cards side by side (trip facts, stops & check-ins), action area under the facts card
**Template classes**: `.back-link`, `.page-header`, `.grid-2`, `.card`, `.card-title`, `.detail-list`, `.timeline`, `.badge`, `.btn-primary`, `.delay-note`, `.save-note`
**Components**:
  - Trip facts card: driver, tractor / trailer, lane, cargo, weight, ETA (or delivered time), status badge — pulled from the store for the `:id` in the route; all 8 trip ids (TRP-7300 through TRP-7307) render their own record
  - Delay note: Delayed trips additionally show reason and original vs current ETA — TRP-7303 "I-84 closed near Pendleton; rerouted via US-395 (original ETA 17:10)", TRP-7306 "Dock congestion at origin; departed 95 minutes late (original ETA 14:30)"
  - Stops & check-ins card: the trip's timestamped check-in timeline, e.g. TRP-7301 — "06:15 Departed Oakland Central Terminal, gate 1", "08:50 Fuel stop, Sacramento TA — 118 gal", "12:05 Chain-control check cleared, Truckee scale"
  - Mark delivered button: shown only while the trip's status is En route, Loading or Delayed
  - Delivered confirmation: a Delivered trip shows "Delivered — POD on file." instead of the button
  - Unknown-id fallback: a card saying "No trip found for this link." with the back link — never a crash
  - Back link: "← Back to board" navigating to `#/board`
**Interactions**:
  - the page renders whichever trip id the route carries — eight distinct records, never one hardcoded trip
  - Mark delivered → sets that trip's status to Delivered in the store, appends the check-in "Delivered — confirmed by dispatch", swaps the button for the confirmation line, and updates the status badge in place; the Board, Exceptions, Drivers and Vehicles pages all reflect it on next render
  - back link → navigates to `#/board`

### Drivers (`#/drivers`)
**Layout**: full-width table under a page header
**Template classes**: `.page-header`, `.table-wrap`, `.table`, `.trip-link`, `.badge`
**Components**:
  - Driver table: columns [Driver, CDL, Home terminal, HOS remaining, Current trip, Status], 7 rows:
    - Marcus Bell, CDL-A, Oakland, CA, 6h 40m, TRP-7301, En route
    - Dana Okoro, CDL-A, Stockton, CA, 8h 05m, TRP-7302, Loading
    - Felix Munoz, CDL-A, Portland, OR, 4h 15m, TRP-7303, Delayed
    - Priya Nair, CDL-A, Salem, OR, 7h 30m, TRP-7307, Loading
    - Jonah Reyes, CDL-A, Reno, NV, 5h 55m, TRP-7305, En route
    - Tessa Grant, CDL-A, Oakland, CA, 6h 05m, TRP-7306, Delayed
    - Omar Sadiq, CDL-B, Oakland, CA, 10h 00m, —, Available
  - Current trip and Status are computed from the trips in the store (a driver's non-Delivered trip; its status), never hand-copied — so a delivery closed on Trip Detail flips that driver to Available here
  - Current trip cell links to `#/trip/{id}` when the driver has one
**Interactions**:
  - clicking a current-trip link → navigates to that trip's detail

### Vehicles (`#/vehicles`)
**Layout**: full-width table under a page header
**Template classes**: `.page-header`, `.table-wrap`, `.table`, `.trip-link`, `.badge`
**Components**:
  - Tractor table: columns [Unit, Model, Odometer, Next service, Trailer, Assignment], 8 rows:
    - HLF-T02, Volvo VNL 760 (2023), 148,220 mi, 152,000 mi, TRL-2219, TRP-7307
    - HLF-T04, Freightliner Cascadia (2022), 201,540 mi, 205,000 mi, TRL-2214, TRP-7301
    - HLF-T07, Kenworth T680 reefer (2021), 262,910 mi, 265,000 mi, TRL-2208, TRP-7303
    - HLF-T09, Peterbilt 579 (2023), 121,470 mi, 125,000 mi, TRL-2226, TRP-7305
    - HLF-T11, Freightliner Cascadia (2020), 318,650 mi, 320,000 mi, TRL-2231, TRP-7302
    - HLF-T15, International LT (2022), 176,090 mi, 180,000 mi, TRL-2240, TRP-7306
    - HLF-T01, Volvo VNL 660 (2019), 402,330 mi, 405,000 mi, —, At yard
    - HLF-T12, Kenworth T680 (2024), 58,840 mi, 62,000 mi, —, At yard
  - Trailer and Assignment are computed from the store's active (non-Delivered) trips per unit; a unit with no active trip shows "—" and "At yard" — so closing a delivery frees its tractor here
  - Assignment cell links to `#/trip/{id}` when the unit is on one
**Interactions**:
  - clicking an assignment link → navigates to that trip's detail

### Exceptions (`#/exceptions`)
**Layout**: full-width table under a page header
**Template classes**: `.page-header`, `.table-wrap`, `.table`, `.trip-link`, `.badge`, `.empty-note`
**Components**:
  - Exception table: columns [Trip, Driver, Lane, Reason, Original ETA, Current ETA], computed as exactly the trips whose status is Delayed — initially 2 rows:
    - TRP-7303, Felix Munoz, Portland, OR → Boise, ID, I-84 closed near Pendleton; rerouted via US-395, 17:10, 21:45
    - TRP-7306, Tessa Grant, Oakland, CA → San Jose, CA, Dock congestion at origin; departed 95 minutes late, 14:30, 16:50
  - Empty-state note: when no trip is Delayed (e.g. after both are marked delivered), one row spans the table saying "No delayed trips right now."
**Interactions**:
  - clicking an exception row → navigates to `#/trip/{that trip's id}`
  - the table is recomputed from the store on every visit, so it can never disagree with the Board

### Settings (`#/settings`)
**Layout**: single form card
**Template classes**: `.card`, `.form-group`, `.form-label`, `.form-input`, `.btn-primary`, `.save-note`
**Components**:
  - Terminal name field, pre-filled "Oakland Central Terminal"
  - Dispatch day start field, pre-filled "05:30"
  - Delay alert threshold field, pre-filled "30 minutes"
  - Save preferences button → shows the inline confirmation "Preferences saved."
**Interactions**:
  - Save preferences → writes the three field values back to the store and the confirmation line under the button; no navigation

## State & Data Model
trips: array — the eight trips above, each carrying id, driverId, unit, trailer, origin, destination, cargo, weightLbs, status, eta, deliveredAt (Delivered trips), delay {reason, originalEta} (Delayed trips), and checkins [{t, d}] (2–3 timestamped entries per trip as specified); trailers per trip: TRP-7300 TRL-2201 (Tessa Grant's delivered morning run — HLF-T15 re-paired to TRL-2240 for TRP-7306), TRP-7301 TRL-2214, TRP-7302 TRL-2231, TRP-7303 TRL-2208, TRP-7304 and TRP-7307 TRL-2219 (Priya Nair's out-and-back on HLF-T02), TRP-7305 TRL-2226, TRP-7306 TRL-2240
drivers: array — seven records keyed by id (DRV-01 Marcus Bell, DRV-02 Dana Okoro, DRV-03 Felix Munoz, DRV-04 Priya Nair, DRV-05 Jonah Reyes, DRV-06 Tessa Grant, DRV-07 Omar Sadiq) with name, cdl, terminal, hosRemaining
vehicles: array — the eight tractors above with unit, model, odometer, nextService
filters: object — { query: "", status: "all" } driving the Board table
settings: object — { terminal: "Oakland Central Terminal", dayStart: "05:30", delayThreshold: "30 minutes" }
Derived, never stored: a driver's current trip and status, a vehicle's trailer and assignment, and the Exceptions rows are all computed from `trips` at render time — one source of truth, so Mark delivered propagates everywhere

## Navigation Flows
sidebar Board → `#/board`
sidebar Drivers → `#/drivers`
sidebar Vehicles → `#/vehicles`
sidebar Exceptions → `#/exceptions`
sidebar Settings → `#/settings`
board row (any) → `#/trip/{that row's trip id}`
exceptions row (any) → `#/trip/{that trip's id}`
drivers current-trip link → `#/trip/{id}`
vehicles assignment link → `#/trip/{id}`
trip detail back link → `#/board`

## Design Notes
- Color scheme: cool operational neutrals; freight-blue `--accent` reserved for the active nav item, active filter, links and the primary button; badge tints map En route to blue, Loading to amber, Delayed to red, Delivered to green
- Typography: single grotesque sans throughout; tabular numbers in every table so weights, odometers and ETAs align
- Density: compact rows (10px vertical padding) — eight trips, the toolbar and the header must fit one screen on the dispatch desk's 1080p monitor
</spec>

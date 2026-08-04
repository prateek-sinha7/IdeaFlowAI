<spec>
# Prototype Specification: Ridgeline Residential — Property Operations Console

## Template & Design System
- **Template**: none active — blank-canvas mode, full class system defined below
- **Design System**: Ridgeline Slate — cool paper-grey surfaces, deep indigo accent, semantic badge tints (green/amber/red/blue/grey), dense tables for rosters and a calm card rhythm for detail pages
- **CSS Class System**: `.sidebar`, `.brand`, `.nav-link`, `.main`, `.page`, `.page-header`, `.page-title`, `.page-sub`, `.kpi-grid`, `.kpi`, `.kpi-value`, `.kpi-label`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.row-link`, `.id-link`, `.badge`, `.badge-ok`, `.badge-warn`, `.badge-danger`, `.badge-info`, `.badge-neutral`, `.card`, `.card-title`, `.grid-2`, `.detail-list`, `.link-list`, `.back-link`, `.inline-form`, `.select-input`, `.form-group`, `.form-label`, `.form-input`, `.btn`, `.btn-primary`, `.btn-danger`, `.empty-note`, `.error-note`, `.save-note`
- **Color Tokens**: --bg=#f6f7f9, --fg=#20293a, --accent=#3d47c2, --surface=#ffffff, --border=#e0e4ec, --muted=#606a7b, --ok=#15803d, --warn=#996a13, --danger=#b3261e, --info=#0b62a4

## Overview
- **Product**: Internal operations console for Ridgeline Residential, manager of the 12-unit Summit Ridge portfolio — three buildings (Alder, Birch, Cedar), four units each
- **Target audience**: The property manager and the front-desk coordinator
- **Core purpose**: One store of record for units, tenants, work orders, vendors and payments — create and close out maintenance work, record rent, and keep every roster, KPI and count derived from the same data so nothing is ever re-keyed
- **Total pages**: 10 (Dashboard, Units, Unit Detail, Tenants, Tenant Detail, Work Orders, New Work Order, Work Order Detail, Vendors, Settings)

## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| dashboard | `#/dashboard` | Computed KPI tiles plus urgent-work and vacancy lists | KPI grid + two cards | Yes |
| units | `#/units` | All 12 units with building filter, status filter and search | toolbar + full-width table | No |
| unit-detail | `#/unit/:id` | One unit's facts, tenant and work-order history, rendered for the clicked row | two-column detail cards | No |
| tenants | `#/tenants` | Tenant roster with computed March payment status | toolbar + full-width table | No |
| tenant-detail | `#/tenant/:id` | One tenant's lease, balance and payment history, with a record-payment form | two-column detail cards | No |
| workorders | `#/workorders` | Work-order queue with status/priority filters, search and the create entry point | toolbar + full-width table | No |
| workorder-new | `#/workorders/new` | Form that creates a new work order in the store | stacked form card | No |
| workorder-detail | `#/workorder/:id` | One work order's facts, activity log and lifecycle actions | two-column detail cards | No |
| vendors | `#/vendors` | Vendor list with open-assignment counts derived from live work orders | full-width table | No |
| settings | `#/settings` | Office preferences | stacked form card | No |

## Page Specifications

### Dashboard (`#/dashboard`)
**Layout**: KPI grid of four tiles above two cards side by side (urgent work orders; move-outs & vacancies)
**Template classes**: `.page-header`, `.kpi-grid`, `.kpi`, `.kpi-value`, `.kpi-label`, `.grid-2`, `.card`, `.card-title`, `.link-list`, `.id-link`
**Components**:
  - KPI tiles, all computed from the store at render time, initially: Occupancy "10 / 12", Rent outstanding "$3,270", Open work orders "4", Vacant units "2"
  - Urgent work orders card: the not-Completed High-priority work orders — initially WO-1036 (B-102, kitchen sink leaking at trap) and WO-1038 (C-101, heat pump short-cycling) — each linking to `#/workorder/{id}`
  - Move-outs & vacancies card: Rosa Ibarra's notice (A-202, lease ends 31 Mar 2026, links to her tenant detail) and the two vacant units A-102 and B-201 (linking to their unit detail), plus a "Create work order →" link to `#/workorders/new`
**Interactions**:
  - clicking any listed work order, tenant or unit → navigates to that record's detail page
  - every number and list entry is recomputed on each visit, so a payment, assignment, completion, creation or cancellation made anywhere is reflected here immediately

### Units (`#/units`)
**Layout**: toolbar (search + building filters + status filters) above a full-width unit table
**Template classes**: `.page-header`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.row-link`, `.id-link`, `.badge`, `.empty-note`
**Components**:
  - Search box: text input, placeholder "Search unit or tenant…", filters rows as the user types (case-insensitive match on unit code and tenant name)
  - Building filter: four buttons — All, Alder, Birch, Cedar — exactly one active at a time
  - Status filter: four buttons — All, Occupied, Vacant, Notice — exactly one active at a time; search and both filter groups combine (all three conditions must hold)
  - Unit table: columns [Unit, Building, Beds, Sq ft, Rent, Tenant, Status], 12 rows:
    - A-101, Alder, 1, 640, $1,850, Maya Lindqvist, Occupied
    - A-102, Alder, 1, 655, $1,895, —, Vacant
    - A-201, Alder, 2, 840, $1,920, Devon Carter, Occupied
    - A-202, Alder, 2, 860, $1,980, Rosa Ibarra, Notice
    - B-101, Birch, 2, 905, $2,150, Kenji Mori, Occupied
    - B-102, Birch, 2, 890, $2,100, Fatima El-Amin, Occupied
    - B-201, Birch, 2, 915, $2,190, —, Vacant
    - B-202, Birch, 3, 1,010, $2,240, Grace Okonkwo, Occupied
    - C-101, Cedar, 3, 1,040, $2,350, Leo Brandt, Occupied
    - C-102, Cedar, 3, 1,050, $2,400, Sofia Marchetti, Occupied
    - C-201, Cedar, 3, 1,035, $2,380, Ethan Caldwell, Occupied
    - C-202, Cedar, 3, 1,045, $2,420, Nadia Rahim, Occupied
  - Empty-state note: when the filters and search match nothing, one row spans the table saying "No units match."
**Interactions**:
  - typing in search → table re-filters on every keystroke
  - clicking a building or status filter button → re-filters and moves that group's active highlight
  - clicking any unit row → navigates to `#/unit/{that row's unit code}`

### Unit Detail (`#/unit/:id`)
**Layout**: back link, page header with the unit code and building, then two cards (unit facts + tenant; work-order history)
**Template classes**: `.back-link`, `.page-header`, `.grid-2`, `.card`, `.card-title`, `.detail-list`, `.table`, `.id-link`, `.badge`, `.empty-note`
**Components**:
  - Unit facts card: building, beds, square footage, rent, status badge, and the current tenant as a link to `#/tenant/{id}` ("Vacant — ready to list" for A-102 and B-201)
  - Work-order history card: a table [Work order, Category, Priority, Status] of every work order for this unit, computed from the store (e.g. B-102 shows WO-1036; A-202 shows WO-1040), each id linking to its detail; when the unit has none, the note "No work orders for this unit yet." plus a "Create work order →" link to `#/workorders/new`
  - Unknown-id fallback: a card saying "No unit found for this link." with the back link — never a crash
  - Back link: "← Back to units" navigating to `#/units`
**Interactions**:
  - the page renders whichever unit code the route carries — all 12 codes render their own record
  - clicking the tenant link or a work-order id → navigates to that record's detail

### Tenants (`#/tenants`)
**Layout**: toolbar (search + payment-status filters) above a full-width tenant table
**Template classes**: `.page-header`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.row-link`, `.id-link`, `.badge`, `.empty-note`
**Components**:
  - Search box: placeholder "Search tenant or unit…", case-insensitive match on tenant name and unit code
  - Payment filter: four buttons — All, Paid, Partial, Overdue — exactly one active at a time; combines with the search
  - Tenant table: columns [Tenant, Unit, Lease ends, Rent, Paid this month, Status], 10 rows; "Paid this month" and Status are COMPUTED from each tenant's payments dated March 2026 versus their rent (Paid ≥ rent green, Partial amber, $0 Overdue red):
    - Maya Lindqvist, A-101, 30 Sep 2026, $1,850, $1,850, Paid
    - Devon Carter, A-201, 31 Jul 2026, $1,920, $0, Overdue
    - Rosa Ibarra, A-202, 31 Mar 2026, $1,980, $1,980, Paid
    - Kenji Mori, B-101, 31 Jan 2027, $2,150, $2,150, Paid
    - Fatima El-Amin, B-102, 30 Nov 2026, $2,100, $2,100, Paid
    - Grace Okonkwo, B-202, 31 Aug 2026, $2,240, $2,240, Paid
    - Leo Brandt, C-101, 30 Jun 2026, $2,350, $1,000, Partial
    - Sofia Marchetti, C-102, 28 Feb 2027, $2,400, $2,400, Paid
    - Ethan Caldwell, C-201, 31 Oct 2026, $2,380, $2,380, Paid
    - Nadia Rahim, C-202, 31 May 2026, $2,420, $2,420, Paid
  - Empty-state note: "No tenants match."
**Interactions**:
  - typing in search / clicking a payment filter → re-filters; both combine
  - clicking any tenant row → navigates to `#/tenant/{that tenant's id}` (ids T-01 through T-10 in the table order above)

### Tenant Detail (`#/tenant/:id`)
**Layout**: back link, page header with the tenant's name, then two cards (lease & balance; payment history with the record-payment form)
**Template classes**: `.back-link`, `.page-header`, `.grid-2`, `.card`, `.card-title`, `.detail-list`, `.table`, `.inline-form`, `.form-input`, `.select-input`, `.btn-primary`, `.badge`, `.empty-note`, `.error-note`
**Components**:
  - Lease & balance card: unit (link to its detail), lease end, phone, monthly rent, paid this month, balance remaining, and the computed status badge — e.g. Leo Brandt shows rent $2,350, paid $1,000, balance $1,350, Partial
  - Payment history card: a table [Date, Amount, Method] of that tenant's payments, newest first as stored — e.g. Maya Lindqvist: 02 Mar 2026 $1,850 ACH, then 03 Feb 2026 $1,850 ACH; Devon Carter shows only 05 Feb 2026 $1,920 Check
  - Record payment form (inline under the history table): amount input (placeholder "Amount, e.g. 1920"), method select (ACH / Check / Card), "Record payment" button
  - Validation: a non-numeric or non-positive amount shows the inline error "Enter a payment amount greater than zero." and adds nothing
  - Unknown-id fallback: "No tenant found for this link." card with the back link
  - Back link: "← Back to tenants" navigating to `#/tenants`
**Interactions**:
  - the page renders whichever tenant id the route carries — all ten ids (T-01 through T-10) render their own record
  - Record payment → appends {17 Mar 2026, the amount, the method} to that tenant's payments in the store, clears the amount field, and re-renders — paid-this-month, balance and the status badge update in place, and the Tenants roster and Dashboard rent-outstanding KPI agree on next visit

### Work Orders (`#/workorders`)
**Layout**: toolbar (search + status filters + priority filters + "New work order" link-button) above a full-width table
**Template classes**: `.page-header`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.btn-primary`, `.table-wrap`, `.table`, `.row-link`, `.id-link`, `.badge`, `.empty-note`
**Components**:
  - Search box: placeholder "Search work order, unit or description…", case-insensitive match on id, unit code and description
  - Status filter: four buttons — All, Open, In Progress, Completed; Priority filter: four buttons — All, High, Medium, Low; each group exclusive, both combine with the search
  - "New work order" button-styled link → `#/workorders/new`
  - Work-order table: columns [Work order, Unit, Category, Priority, Opened, Vendor, Status], 6 rows:
    - WO-1036, B-102, Plumbing, High, 14 Mar 2026, Delta Plumbing, In Progress
    - WO-1037, A-201, Appliance, Medium, 15 Mar 2026, —, Open
    - WO-1038, C-101, HVAC, High, 16 Mar 2026, —, Open
    - WO-1039, B-201, Paint, Low, 13 Mar 2026, BrightCoat Painting, In Progress
    - WO-1040, A-202, Electrical, Medium, 12 Mar 2026, Volt Electric, Completed
    - WO-1041, C-202, General, Low, 14 Mar 2026, Hearthstone Handywork, Completed
  - Empty-state note: "No work orders match."
**Interactions**:
  - typing in search / clicking a status or priority filter → re-filters; all three combine
  - clicking any row → navigates to `#/workorder/{that row's id}`
  - a work order created, completed or cancelled elsewhere appears, updates or disappears here on next render — the table is always the live store

### New Work Order (`#/workorders/new`)
**Layout**: back link, page header, single form card
**Template classes**: `.back-link`, `.page-header`, `.card`, `.form-group`, `.form-label`, `.form-input`, `.select-input`, `.btn-primary`, `.error-note`
**Components**:
  - Unit select: all 12 unit codes
  - Category select: Plumbing / Electrical / HVAC / Appliance / Paint / General
  - Priority select: High / Medium / Low
  - Description input: placeholder "e.g. Bathroom fan rattling"
  - "Create work order" button
  - Validation: an empty description shows the inline error "Enter a description before creating." and creates nothing
  - Back link: "← Back to work orders" navigating to `#/workorders`
**Interactions**:
  - Create work order → adds a work order to the store with the next sequential id (one more than the highest existing WO number — initially WO-1042), status Open, no vendor, opened 17 Mar 2026, and the activity-log entry "Created by front desk", then navigates to `#/workorder/{new id}` — the new row also appears on Work Orders, the unit's history and the Dashboard count
  - the form resets to its defaults each time the page is visited

### Work Order Detail (`#/workorder/:id`)
**Layout**: back link, page header with the id and unit, then two cards (facts + actions; activity log)
**Template classes**: `.back-link`, `.page-header`, `.grid-2`, `.card`, `.card-title`, `.detail-list`, `.link-list`, `.select-input`, `.btn-primary`, `.btn-danger`, `.badge`, `.save-note`, `.empty-note`
**Components**:
  - Facts card: unit (link to its detail), category, priority badge, opened date, vendor ("— unassigned" when none), status badge, description
  - Actions area, conditional on status:
    - not Completed and unassigned → Assign-vendor control: a select of all four vendors plus an "Assign vendor" button
    - not Completed → a "Mark complete" `.btn-primary` and a "Cancel work order" `.btn-danger`
    - Completed → the line "Completed on {date} — no further actions." and no buttons
  - Activity log card: timestamped entries from the store, e.g. WO-1036: "14 Mar 2026 — Reported by tenant (Fatima El-Amin)", "14 Mar 2026 — Assigned to Delta Plumbing", "16 Mar 2026 — Parts ordered, trap kit"
  - Unknown-id fallback: "No work order found for this link." card with the back link — this is also what a cancelled work order's old link shows
  - Back link: "← Back to work orders" navigating to `#/workorders`
**Interactions**:
  - the page renders whichever work-order id the route carries — every stored id renders its own record
  - Assign vendor → sets the chosen vendor, moves status Open → In Progress, appends the log entry "17 Mar 2026 — Assigned to {vendor name}", re-renders in place; the vendor's open-assignment count on Vendors rises by one
  - Mark complete → sets status Completed with completed-on 17 Mar 2026, appends "17 Mar 2026 — Completed — closed by property manager", swaps the buttons for the completed line; Dashboard's open count falls and the vendor's open count falls
  - Cancel work order → REMOVES the work order from the store, appends nothing, and navigates to `#/workorders`, where it no longer appears; its unit history, the Dashboard and Vendors all forget it, and revisiting its old link shows the not-found card

### Vendors (`#/vendors`)
**Layout**: full-width table under a page header
**Template classes**: `.page-header`, `.table-wrap`, `.table`, `.badge`
**Components**:
  - Vendor table: columns [Vendor, Trade, Contact, Phone, Open assignments], 4 rows; Open assignments is COMPUTED as that vendor's not-Completed work orders:
    - Volt Electric, Electrical, Ray Donnelly, (415) 555-0171, 0
    - Delta Plumbing, Plumbing, Marisol Vega, (415) 555-0184, 1
    - Hearthstone Handywork, General & appliance, Pete Kowal, (415) 555-0158, 0
    - BrightCoat Painting, Painting, Jun Park, (415) 555-0139, 1
**Interactions**:
  - none beyond navigation; the counts must always agree with the Work Orders table because they derive from it at render time

### Settings (`#/settings`)
**Layout**: single form card
**Template classes**: `.card`, `.form-group`, `.form-label`, `.form-input`, `.btn-primary`, `.save-note`
**Components**:
  - Office name field, pre-filled "Ridgeline Residential — Summit Ridge Office"
  - Rent due day field, pre-filled "1st of the month"
  - Work-order auto-close field, pre-filled "14 days after completion"
  - Save preferences button → shows the inline confirmation "Preferences saved."
**Interactions**:
  - Save preferences → writes the three field values back to the store and the confirmation line under the button; no navigation

## State & Data Model
units: array — the 12 units above with id (the unit code), building, beds, sqft, rent, status, tenantId (null for A-102 and B-201)
tenants: array — ten records T-01…T-10 (table order above) with name, unitId, leaseEnd, phone ((415) 555-01xx numbers), rent, and payments [{date, amount, method}]; seed payments: one March 2026 payment equal to rent for every Paid tenant (dates 01–06 Mar 2026), Leo Brandt (T-07) 05 Mar 2026 $1,000 Check, Devon Carter (T-02) only 05 Feb 2026 $1,920 Check, plus Maya Lindqvist's 03 Feb 2026 $1,850 ACH history row
workorders: array — the six work orders above with id, unitId, category, priority, status, opened, vendorId (V-01 Volt Electric, V-02 Delta Plumbing, V-03 Hearthstone Handywork, V-04 BrightCoat Painting; null when unassigned), completedOn (WO-1040 16 Mar 2026, WO-1041 15 Mar 2026), description — WO-1036 "Kitchen sink leaking at trap", WO-1037 "Dishwasher not draining", WO-1038 "Heat pump short-cycling", WO-1039 "Repaint before re-listing", WO-1040 "Replace hallway outlet", WO-1041 "Re-hang closet door" — and log [{t, d}] activity entries (2–3 per order)
vendors: array — the four vendors above with id, name, trade, contact, phone
filters: object — { units: {query, building, status}, tenants: {query, status}, workorders: {query, status, priority} }
settings: object — { office: "Ridgeline Residential — Summit Ridge Office", rentDueDay: "1st of the month", autoClose: "14 days after completion" }
TODAY constant: "17 Mar 2026" — stamped on recorded payments, assignments, completions and created work orders
Derived, never stored: every KPI, paid-this-month figure, balance, payment status, unit work-order history, vendor open-assignment count and dashboard list is computed from these arrays at render time — one source of truth, so create/assign/complete/cancel/record-payment propagate everywhere

## Navigation Flows
sidebar Dashboard → `#/dashboard`
sidebar Units → `#/units`
sidebar Tenants → `#/tenants`
sidebar Work Orders → `#/workorders`
sidebar Vendors → `#/vendors`
sidebar Settings → `#/settings`
units row (any) → `#/unit/{unit code}`
unit detail tenant link → `#/tenant/{id}`; unit detail work-order link → `#/workorder/{id}`
tenants row (any) → `#/tenant/{id}`
work orders row (any) → `#/workorder/{id}`
work orders "New work order" / dashboard & unit-detail create links → `#/workorders/new`
new work order Create → `#/workorder/{the new id}`; cancel Cancel → `#/workorders`
dashboard urgent list → `#/workorder/{id}`; dashboard move-out/vacancy list → `#/tenant/{id}` / `#/unit/{id}`
every detail back link → its list page

## Design Notes
- Color scheme: quiet paper-grey field; indigo `--accent` reserved for the active nav item, active filters, links and primary buttons; `.btn-danger` red is used once, on Cancel work order, so destructive action reads differently from everything else
- Badge semantics held constant everywhere: green ok (Occupied, Paid, Completed), amber warn (Notice, Partial, In Progress, Medium), red danger (Overdue, High), blue info (Open), grey neutral (Vacant, Low)
- Typography: single grotesque sans; tabular numbers in every table so rents, balances and counts align
- Density: compact rows (10px vertical padding); the 12-row unit table with its two filter groups must fit one screen without scrolling
</spec>

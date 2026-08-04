<tasks>
## Task 1: HTML Shell & Navigation Chrome

**Goal**: Build complete HTML skeleton with all 6 page placeholders, DS-mapped tokens as :root variables, persistent sidebar, sticky topbar, and hash router.

**DS Token Mapping** (from Apple DS → :root variables):
- `--bg: #ffffff` (Pure White Canvas)
- `--bg-light: #f5f5f7` (Pale Apple Gray)
- `--fg: #1d1d1f` (Near-Black Ink — primary text)
- `--fg-secondary: #6e6e73` (Secondary Neutral Gray)
- `--accent: #0071e3` (Apple Action Blue — actions/active states)
- `--accent-link: #0066cc` (Body Link Blue)
- `--surface: #f5f5f7` (card/panel background)
- `--border: #d2d2d7` (Soft Border Gray)
- `--border-strong: #86868b` (Mid Border Gray)
- `--bg-dark: #1d1d1f` (dark button background)
- `--status-available: #34c759` (green)
- `--status-in-shop: #ff9500` (orange)
- `--status-awaiting-parts: #ff3b30` (red)
- `--status-road-test: #0071e3` (blue)
- `--status-out-of-service: #8e8e93` (gray)

**Typography Setup** (font-family fallbacks from Apple DS):
- Display font: `SF Pro Display, 'Inter Tight', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif`
- Text font: `SF Pro Text, 'Inter', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif`
- Page title: Display, 48px, weight 600, line-height 1.08
- Section heading: Display, 28px, weight 600, line-height 1.14
- Table header: Text, 14px, weight 600, line-height 1.29
- Body: Text, 17px, weight 400, line-height 1.47
- Small/micro: Text, 12px, weight 400, line-height 1.33

**HTML Structure**:
- `<!doctype html>` through `</html>`, CSS in one `<style>` block
- Layout: CSS Grid with sidebar (240px, sticky left) + topbar (56px, sticky top) + main (scrollable)
- Semantic tags: `<aside class="sidebar">`, `<header class="topbar">`, `<main>`, `<section data-page="{id}" class="page">`
- Hash router: detect `window.location.hash` changes, show/hide pages via `is-active` class

**Sidebar** (240px fixed, sticky, left edge):
- Top: Northwind Logistics logo/text (bold, 18px, `--fg`)
- Nav items (6 total): Vehicles, Work Orders, Inspections, Parts & Costs, Settings, [Logout]
- Each nav item: `<a href="#/{route}" class="nav-item" data-page="{id}">` (text + icon emoji/symbol)
- Active nav item: uses `--accent` color for text
- Bottom: placeholder for user badge (avatar circle + "Admin" label, optional for now)

**Topbar** (56px height, sticky, horizontal flex):
- Left side: `<div class="topbar-title">` shows current page title (e.g., "Vehicles", "Work Orders")
- Right side: `<div class="topbar-actions">` contains search input (placeholder text varies per page) + user avatar icon
- Search input styling: white bg, `--border-strong` outline, 8px radius, padding 8-12px

**Main Content Area**:
- 6 empty `<section data-page="{id}" class="page">` elements:
  - `data-page="vehicles"` (with `is-active` class on initial load)
  - `data-page="vehicle-detail"`
  - `data-page="work-orders"`
  - `data-page="inspections"`
  - `data-page="parts-costs"`
  - `data-page="settings"`
- Each section: placeholder text "[Page {id} content — Task {N} fills this]" (temporary, will be replaced by subsequent tasks)

**Router & State**:
- Hash routes map: `{ vehicles: '/', 'vehicle-detail': '/vehicle/:id', 'work-orders': '/work-orders', inspections: '/inspections', 'parts-costs': '/parts-costs', settings: '/settings' }`
- Global state store (simple object): `{ currentPage, currentVehicleId, filters: { type, status, search }, ... }`
- Navigation handler: click nav links → parse `href` → update hash → trigger page switch + topbar title update
- First page loaded is `#/` (Vehicles, auto-active)

**Styling Skeleton**:
- Global: `:root` with all tokens, `body` uses `--bg` background + `--fg` text + system font stack
- Sidebar: `--bg-light` background, `--border` right edge, text `--fg` (active nav uses `--accent`)
- Topbar: `--bg` background, `--border` bottom edge
- Main: flex/grid layout, max-width ~1200px, padding 20px outer margins
- Page sections: display none by default, display block when `is-active`
- Buttons: `.btn-primary` uses `--accent` bg + white text + 8px radius; `.btn-secondary` uses `--border` outline + `--fg` text
- Cards: `.card` uses `--surface` bg, `--border` outline, 8-12px radius, padding 12-16px
- Tables: `.table` striped rows (white/`--bg-light` alternating), `--border` dividers, text 14px

**Script (inline `<script>` block)**:
- On load: detect hash, initialize router
- On hash change: update visible page, update sidebar active nav item, update topbar title
- Stub event handlers for page interactions (to be filled by subsequent tasks)

---

## Task 2: Vehicles Page (`#/`)

**Goal**: Fill the `data-page="vehicles"` section with complete vehicle list, type/status filters, unit-number search, and vehicle table with 12 rows of realistic data.

**Layout Pattern**: Sidebar + Topbar (with search) + sticky filter controls + scrollable vehicle table

**Template Classes Used**: `.app-shell`, `.sidebar`, `.topbar`, `.main`, `.section`, `.filter-group`, `.filter-pills`, `.filter-pill`, `.filter-pill--active`, `.table-container`, `.table`, `.table-header`, `.table-row`, `.table-cell`, `.badge`, `.badge--available`, `.badge--in-shop`, `.badge--awaiting-parts`, `.badge--road-test`, `.badge--out-of-service`, `.btn`, `.btn-link`

**Components**:

1. **Topbar Configuration** (Task 1 creates shell, this task specifies content):
   - Page title: "Vehicles"
   - Search input: placeholder "Search by unit (e.g., TRK-2026-0184)", `id="vehicleSearch"`, triggers real-time table filter

2. **Filter Controls** (sticky, below topbar, above table):
   - Label: "Type Filter:" (left-aligned, 14px, `--fg-secondary`)
   - Pill buttons (horizontal row): "All" (default active), "Box truck", "Tractor", "Cargo van", "Trailer"
   - Active pill: `--accent` bg + white text, 8px radius
   - Inactive pill: `--border` outline + `--fg` text, 8px radius
   - Each pill: `data-type-filter="{type}"`, click handler updates table

3. **Vehicle Table** (columns: Unit Number, Make/Model, Type, In-Service Date, Status, Days in Status, Actions):
   - 12 vehicle rows with realistic data:
     ```
     TRK-2026-0184 | Volvo VNL 860 | Tractor | 2021-03-15 | Available (green badge) | 2 | [Detail] [Flag Parts]
     BX-2024-0512 | Ford F-750 | Box truck | 2024-01-22 | In shop (orange badge) | 5 | [Detail] [Flag Parts]
     CG-2023-1047 | International CV | Cargo van | 2023-08-10 | Awaiting parts (red badge) | 12 | [Detail] [Flag Parts]
     TR-2022-0091 | Wabash Trailer | Trailer | 2022-06-05 | Road test (blue badge) | 1 | [Detail] [Flag Parts]
     TRK-2025-0203 | Peterbilt 579 | Tractor | 2025-02-01 | Available (green badge) | 0 | [Detail] [Flag Parts]
     BX-2023-0889 | Isuzu NPR-HD | Box truck | 2023-11-28 | Out of service (gray badge) | 45 | [Detail] [Flag Parts]
     CG-2024-0156 | Mercedes Sprinter | Cargo van | 2024-05-13 | In shop (orange badge) | 3 | [Detail] [Flag Parts]
     TR-2021-0504 | Great Dane Trailer | Trailer | 2021-09-20 | Available (green badge) | 0 | [Detail] [Flag Parts]
     TRK-2026-0445 | Volvo VNL 760 | Tractor | 2026-01-10 | Awaiting parts (red badge) | 8 | [Detail] [Flag Parts]
     BX-2025-0067 | Freightliner M2 | Box truck | 2025-04-03 | Available (green badge) | 1 | [Detail] [Flag Parts]
     CG-2022-0733 | Ford Transit | Cargo van | 2022-12-15 | In shop (orange badge) | 7 | [Detail] [Flag Parts]
     TR-2024-0298 | Kentucky Trailer | Trailer | 2024-07-09 | Available (green badge) | 0 | [Detail] [Flag Parts]
     ```
   - Status column: color-coded badge using `--status-*` tokens
   - Days-in-Status: if > 10 days, highlight with subtle `--status-awaiting-parts` background
   - Action buttons: `[Detail]` (link, `--accent-link` blue, href="#/vehicle/{id}") + `[Flag Parts]` (secondary outline button)
   - Table header: sticky, background `--surface`, 14px weight 600 text
   - Striped rows: alternating white/`--bg-light` backgrounds

**Interactions**:
- Type filter AND search logic: table updates when either filter changes (combined filter)
- Unit-number search: case-insensitive substring match on unitNumber column, updates in real-time
- [Detail] button: navigate to `#/vehicle/{vehicleId}` (id is unit number slug, e.g., "trk-2026-0184")
- [Flag Parts] button: opens inline form or modal (stub for now, shows success message "Parts flagged for TRK-2026-0184")

**JavaScript Event Handlers Needed**:
- `vehicleSearch` input: on change, filter table rows
- Type filter pills: on click, update filter state + table rows
- [Detail] buttons: on click, set currentVehicleId in state, navigate to `#/vehicle/:id`
- [Flag Parts] buttons: on click, show confirmation + add to work queue (stub response)

---

## Task 3: Vehicle Detail Page (`#/vehicle/:id`)

**Goal**: Fill the `data-page="vehicle-detail"` section with vehicle header, service checklist, technician notes per shop, work order history, and action buttons (Advance Status, Flag for Parts).

**Layout Pattern**: Sidebar + Topbar (showing "Vehicle: TRK-2026-0184 — Volvo VNL 860") + Detail sections (header card, service checklist, notes, work orders, actions)

**Template Classes Used**: `.app-shell`, `.sidebar`, `.topbar`, `.main`, `.section`, `.vehicle-header`, `.header-grid`, `.vehicle-info`, `.vehicle-meta`, `.service-checklist`, `.checklist-row`, `.notes-panel`, `.note-item`, `.shop-note`, `.work-order-history`, `.action-buttons`, `.btn-primary`, `.btn-secondary`, `.badge`, `.checkbox`

**Components**:

1. **Topbar Configuration**:
   - Page title: "Vehicle: {unitNumber} — {make} {model}" (e.g., "Vehicle: TRK-2026-0184 — Volvo VNL 860")
   - Back link: "[< Back to Vehicles]" on left

2. **Vehicle Header Card** (top of page, white bg, `--border` outline, 12px radius, padding 16px):
   - Left column: Unit Number (bold, 32px, `--fg`), Make/Model (20px, `--fg-secondary`), Type badge (e.g., "Tractor"), Status badge (color-coded), Days in Status (e.g., "2 days")
   - Right column: VIN (1VUJB5B32F1234567), Current Mileage (187,643 mi), Last Service Date (2026-01-15)
   - Grid layout: 2 columns, content vertically stacked within each

3. **Service Checklist Section** (below header, white bg, `--border` outline, 12px radius, padding 16px):
   - Label: "Service Checklist" (28px, weight 600, `--fg`)
   - Table: columns [Task, Last Completed, Interval, Next Due, Completed in this visit]
   - 6 checklist items with realistic data:
     ```
     Oil Change | 2026-01-15 | 15,000 mi | 2026-02-10 (202,643 mi est.) | [☐]
     Air Filter | 2025-11-20 | 20,000 mi | 2026-03-20 (207,643 mi est.) | [☐]
     Brake Inspection | 2025-12-05 | 10,000 mi | 2026-01-20 (197,643 mi est.) | [☐]
     Tire Rotation | 2026-01-08 | 8,000 mi | 2026-02-08 (195,643 mi est.) | [☐]
     Fluid Top-off | 2026-01-18 | 2,000 mi | 2026-01-27 (189,643 mi est.) | [☐]
     Coolant Flush | 2025-06-10 | 50,000 mi | 2026-03-10 (237,643 mi est.) | [☐]
     ```
   - Last Completed, Interval, Next Due: small text (12px, `--fg-secondary`)
   - Completed checkbox: toggleable (stub, no persistence needed for prototype)

4. **Technician Notes by Shop** (collapsible/expandable sections, one per shop):
   - Downtown Bay note: "Brake lines inspected 2026-01-18, wear evident. Recommend replacement in next service cycle. — Tech: Mike R., verified 14:32"
   - North Warehouse note: "Routine oil change completed 2026-01-15, mileage 187,643 mi. No issues noted. All fluids topped off. — Tech: Sarah L., verified 09:15"
   - East Terminal: "No service history at this location."
   - Each note: white card, `--border` outline, 12px radius, padding 12px, 17px body text, author + timestamp small text (12px, `--fg-secondary`)

5. **Work Order History** (expandable table, below notes):
   - Label: "Work Order History" (28px, weight 600)
   - Table: columns [WO #, Task, Shop, Status, Tech, Cost]
   - 5 work order rows (subset for TRK-2026-0184):
     ```
     WO-2026-0515 | Oil Change + Filter Replacement | Downtown Bay | In Progress | Mike R. | $245.00
     WO-2026-0512 | Oil Filter + Fluid Top | Downtown Bay | In Progress | Mike R. | $180.00
     WO-2026-0498 | Brake Inspection | North Warehouse | Completed | Sarah L. | $180.00
     WO-2026-0477 | Tire Rotation | East Terminal | Completed | Dave T. | $120.00
     WO-2026-0450 | Transmission Service | Downtown Bay | Completed | Mike R. | $420.00
     ```
   - Status badges: color-coded (In Progress = blue, Completed = green)
   - Cost: right-aligned, currency format
   - Clicking row (expandable): shows line items breakdown (parts + labor detail) — stub inline detail

6. **Action Buttons** (sticky, bottom right or fixed overlay, white bg, padding 16px):
   - `[Advance Status]` button (primary, `--accent` bg + white text, 8px radius): opens dropdown menu with valid next statuses
     - Available → In shop / Out of service
     - In shop → Available / Awaiting parts / Road test
     - Awaiting parts → In shop
     - Road test → Available / In shop
     - Out of service → Available / In shop
   - `[Flag for Parts]` button (secondary outline): opens inline form (part name input + qty + estimated cost) → confirm → adds to Parts & Costs
   - `[Back to Vehicles]` link (text, `--accent-link` blue)

**Interactions**:
- [Advance Status] → click → show dropdown → select status → update vehicle.status globally → reload Vehicles page table + Work Orders queues → show success toast "Status updated to In shop"
- [Flag for Parts] → click → open form → enter part details → confirm → add line item to work queue → update Parts & Costs totals → show success "Parts flagged for {vehicleId}"
- Work order row → click → expand inline detail showing labor hours, parts line items (part name, qty, unit cost, total)
- Shop note section → click → expand to show full note text

**JavaScript Event Handlers Needed**:
- Load vehicle detail from URL param (`#/vehicle/:id`) → populate header, checklist, notes, work orders
- [Advance Status] dropdown: on select, POST to state, reload tables
- [Flag for Parts] form: on submit, add line item, update costs
- Work order expansion: on click, toggle detail row
- Back button: navigate to `#/` with filter state preserved

---

## Task 4: Work Orders Page (`#/work-orders`)

**Goal**: Fill the `data-page="work-orders"` section with shop tabs, work order table showing 15 WOs across 3 shops, with status/priority badges and expandable detail rows.

**Layout Pattern**: Sidebar + Topbar (title: "Work Orders") + sticky shop tabs + scrollable work order table

**Template Classes Used**: `.app-shell`, `.sidebar`, `.topbar`, `.main`, `.section`, `.shop-tabs`, `.shop-tab`, `.shop-tab--active`, `.table-container`, `.table`, `.table-row`, `.table-row--expandable`, `.badge`, `.badge--queued`, `.badge--in-progress`, `.badge--completed`, `.badge--on-hold`, `.badge--normal`, `.badge--high`, `.btn-link`

**Components**:

1. **Topbar Configuration**:
   - Page title: "Work Orders"
   - Search/filter stub: optional (skip for now, table filtering via tabs)

2. **Shop Filter Tabs** (sticky, below topbar, horizontal flex):
   - Tabs: "All Shops" (default active), "Downtown Bay", "North Warehouse", "East Terminal"
   - Active tab: `--accent` underline or bg highlight + white text, 14px weight 600
   - Inactive tab: `--fg` text, 14px weight 400
   - Each tab: `data-shop-filter="{shop}"`, click updates table

3. **Work Order Table** (columns: WO #, Vehicle Unit, Task, Assigned Tech, Status, Days in Queue, Priority, Cost):
   - 15 work order rows across 3 shops (5 per shop):
     ```
     WO-2026-0515 | TRK-2026-0184 | Engine Oil Change | Mike R. | In Progress (blue badge) | 1 | Normal | $245.00
     WO-2026-0514 | BX-2024-0512 | Brake Pad Replacement | Sarah L. | Queued (gray badge) | 2 | High (orange bg) | $680.00
     WO-2026-0512 | TRK-2026-0184 | Oil Filter + Fluid Top | Mike R. | In Progress | 1 | Normal | $180.00
     WO-2026-0511 | CG-2024-0156 | Suspension Inspection | Dave T. | Queued | 3 | High | $420.00
     WO-2026-0510 | TR-2022-0091 | Trailer Light Repair | Mike R. | Completed (green badge) | 0 | Normal | $85.00
     [... shop filter changes which 5 are shown ...]
     ```
   - Status badges: Queued (gray text), In Progress (blue bg), Completed (green bg), On Hold (orange bg)
   - Priority badges: Normal (neutral text), High (red/orange bg)
   - Cost: right-aligned, currency format ($XXX.XX)
   - Table header: sticky, `--surface` bg, 14px weight 600
   - Rows: white/`--bg-light` striped, clickable (cursor pointer)

4. **Expandable Row Detail** (on row click):
   - Shows: task breakdown, labor hours, parts line items (part name, qty, unit cost, total), estimated completion, technician notes
   - Layout: indented below row, white bg, `--border` outline, padding 12px
   - Line items table: columns [Part Name, Qty, Unit Cost, Total]
   - [Update Status] button: dropdown to change WO status (Queued → In Progress → Completed)

**Interactions**:
- Shop tabs: on click, filter table to show only WOs for selected shop ("All Shops" shows all 15)
- Work order row: on click, expand detail row below (toggle on/off)
- [Update Status] dropdown: on select, update workOrder.status → reflect on Vehicles page (daysInStatus may change)
- Vehicle unit link: on click, navigate to `#/vehicle/:id`

**JavaScript Event Handlers Needed**:
- Shop tab click: update shop filter, re-render table rows
- Work order row click: toggle expandable detail row
- [Update Status] select: update WO status in state, trigger refresh of related vehicle/cost data
- Vehicle link click: navigate to `#/vehicle/{vehicleId}`

---

## Task 5: Inspections Page (`#/inspections`)

**Goal**: Fill the `data-page="inspections"` section with type filter pills and inspection table showing 10 inspection records with expandable findings detail.

**Layout Pattern**: Sidebar + Topbar (title: "Inspections") + sticky type filter + scrollable inspection table

**Template Classes Used**: `.app-shell`, `.sidebar`, `.topbar`, `.main`, `.section`, `.filter-group`, `.filter-pills`, `.filter-pill`, `.filter-pill--active`, `.table-container`, `.table`, `.table-row`, `.table-row--expandable`, `.badge`, `.badge--passed`, `.badge--failed`, `.badge--pending`, `.badge--na`, `.btn-link`

**Components**:

1. **Topbar Configuration**:
   - Page title: "Inspections"

2. **Inspection Type Filter** (sticky, below topbar):
   - Label: "Inspection Type Filter:" (14px, `--fg-secondary`)
   - Pills: "All Types" (default active), "Pre-trip", "Post-trip", "Annual Safety", "Emission", "DOT Compliance"
   - Active pill: `--accent` bg + white text, 8px radius
   - Inactive pill: `--border` outline + `--fg` text, 8px radius

3. **Inspection Table** (columns: Vehicle Unit, Inspection Type, Date, Technician, Findings, Status):
   - 10 inspection rows with realistic data:
     ```
     TRK-2026-0184 | Pre-trip | 2026-01-18 | Mike R. | Clean, no issues noted | Passed (green badge)
     BX-2024-0512 | DOT Compliance | 2026-01-17 | Sarah L. | Brake deficiency detected, flagged for repair | Failed (red badge)
     CG-2023-1047 | Annual Safety | 2026-01-16 | Dave T. | Tire wear within limits, suspension OK | Passed
     TR-2022-0091 | Post-trip | 2026-01-18 | Mike R. | Trailer lights functional, all connections secure | Passed
     TRK-2025-0203 | Pre-trip | 2026-01-18 | Sarah L. | Minor oil seep observed, monitor | Passed
     BX-2023-0889 | Annual Safety | 2025-06-10 | Dave T. | Multiple deficiencies, vehicle out of service | Failed
     CG-2024-0156 | Pre-trip | 2026-01-18 | Mike R. | All systems operational | Passed
     TR-2021-0504 | Emission | 2026-01-12 | Sarah L. | Emissions within limits, catalyst OK | Passed
     TRK-2026-0445 | Post-trip | 2026-01-18 | Dave T. | Engine knock detected, diagnostics recommended | Failed
     BX-2025-0067 | Pre-trip | 2026-01-18 | Mike R. | Clean inspection, no issues | Passed
     ```
   - Status badges: Passed (green bg), Failed (red bg), Pending (yellow bg), N/A (gray bg)
   - Findings column: truncated (first 50 chars), shows "..." with expandable detail
   - Table header: sticky, `--surface` bg, 14px weight 600
   - Rows: white/`--bg-light` striped, clickable

4. **Expandable Row Detail** (on row click):
   - Shows: full findings text, deficiency list (if Failed), photos (if present, stub), technician sign-off timestamp, corrective actions taken (if any)
   - Layout: indented below row, white bg, `--border` outline, padding 12px
   - Deficiency list (if Failed): bullet points with code, description, severity
   - Example Failed inspection detail:
     ```
     Brake system deficiency (Code: BRK-001, Severity: Critical)
     Coolant level low (Code: CL-002, Severity: Minor)
     ```

**Interactions**:
- Type filter pills: on click, filter table by inspection type
- Inspection row: on click, expand detail row below (toggle)
- Vehicle unit link: on click, navigate to `#/vehicle/:id`

**JavaScript Event Handlers Needed**:
- Type filter pill click: update filter, re-render table rows
- Inspection row click: toggle expandable detail
- Vehicle link click: navigate to `#/vehicle/{vehicleId}`

---

## Task 6: Parts & Costs Page (`#/parts-costs`)

**Goal**: Fill the `data-page="parts-costs"` section with 4 KPI cards (totals rolled up from work orders), cost aggregation table showing 8 vehicles with labor/parts breakdown, and 12-month trend bar chart.

**Layout Pattern**: Sidebar + Topbar (title: "Parts & Costs") + KPI card grid + cost aggregation table + inline SVG trend chart

**Template Classes Used**: `.app-shell`, `.sidebar`, `.topbar`, `.main`, `.section`, `.kpi-grid`, `.kpi-card`, `.kpi-value`, `.kpi-label`, `.kpi-delta`, `.table-container`, `.table`, `.table-row`, `.chart-wrap`, `.chart-title`

**Components**:

1. **Topbar Configuration**:
   - Page title: "Parts & Costs"

2. **KPI Card Grid** (4 columns, each card white bg, `--border` outline, 12px radius, padding 16px, centered text):
   - **Card 1: Total Fleet Maintenance Cost (This Month)**
     - Value: `$18,947` (bold, 32px, `--fg`)
     - Label: "Total Fleet Maintenance Cost (This Month)" (14px, `--fg-secondary`)
     - Delta: `+16% ↑` (orange text for up arrow, using `--status-in-shop` or similar)
     - Subtext: "vs. $16,320 last month" (12px, `--fg-secondary`)
   - **Card 2: Parts Inventory Value**
     - Value: `$24,560`
     - Label: "Parts Inventory Value"
     - Delta: `+12% ↑`
     - Subtext: "vs. $21,890 last month"
   - **Card 3: Avg Cost per Vehicle**
     - Value: `$1,579`
     - Label: "Average Cost per Vehicle"
     - Delta: `+16% ↑`
     - Subtext: "vs. $1,361 last month"
   - **Card 4: Open Work Order Cost**
     - Value: `$6,240`
     - Label: "Open Work Order Cost"
     - Delta: `+22% ↑`
     - Subtext: "vs. $5,100 last month"

3. **Cost Aggregation Table** (below KPI cards, columns: Vehicle Unit, Total Cost (This Month), Labor, Parts, Parts Count, Most Recent WO):
   - 8 vehicle rows, costs summed from work orders:
     ```
     TRK-2026-0184 | $1,245 | $420 | $825 | 3 | WO-2026-0515: Oil Change
     BX-2024-0512 | $1,950 | $680 | $1,270 | 2 | WO-2026-0514: Brake Pads
     CG-2023-1047 | $2,340 | $840 | $1,500 | 1 | WO-2026-0507: Tire Repl
     TR-2022-0091 | $580 | $180 | $400 | 1 | WO-2026-0510: Trailer Light
     TRK-2025-0203 | $420 | $240 | $180 | 1 | WO-2026-0504: Routine
     BX-2023-0889 | $8,500 | $3,200 | $5,300 | 1 | WO-2026-0505: Full Overhaul
     CG-2024-0156 | $892 | $340 | $552 | 2 | WO-2026-0511: Suspension
     TR-2021-0504 | $320 | $120 | $200 | 1 | WO-2026-0506: Hitch
     ```
   - All cost columns: right-aligned, currency format ($X,XXX.XX)
   - Table header: sticky, `--surface` bg, 14px weight 600
   - Rows: white/`--bg-light` striped
   - Subtotal row at bottom (sticky, white bg, bold): "Total: $18,947 | Labor: $6,620 | Parts: $12,327 | Parts Count: 12"

4. **Cost Trend Chart** (inline SVG, below table):
   - Type: horizontal bar chart
   - Title: "12-Month Cost Trend" (28px, weight 600, `--fg`)
   - X-axis: months (Jan 2025 through Jan 2026, 13 data points)
   - Y-axis: cost ($0 - $25,000), labels at $5k intervals
   - Data points (monthly total costs):
     ```
     Jan 2025: $8,500 | Feb: $9,200 | Mar: $10,100 | Apr: $11,300 | May: $12,800
     Jun: $14,200 | Jul: $15,600 | Aug: $16,100 | Sep: $15,800 | Oct: $17,200
     Nov: $18,500 | Dec: $16,320 | Jan 2026: $18,947 (highlight this bar in `--accent` blue)
     ```
   - SVG: `<svg viewBox="0 0 1000 400">` with bars rendered as `<rect>` elements
   - Current month bar (Jan 2026): `--accent` color (#0071e3)
   - Previous months: `--border` or `--status-in-shop` (orange/muted)
   - X-axis labels: month abbreviations (JAN, FEB, ..., JAN)
   - Y-axis labels: currency format ($0, $5K, $10K, ..., $25K)

**Interactions**:
- Clicking vehicle unit row: navigate to `#/vehicle/:id`
- Clicking work order link in "Most Recent WO" column: expand inline detail (WO breakdown: parts + labor)
- KPI cards: display-only, no interaction
- Chart: display-only, no interaction (could add hover tooltip stub, skip for MVP)

**JavaScript Event Handlers Needed**:
- Load cost aggregation data from work orders (sum labor + parts per vehicle)
- Vehicle row click: navigate to `#/vehicle/{vehicleId}`
- WO link click: expand inline detail row

---

## Task 7: Settings Page (`#/settings`)

**Goal**: Fill the `data-page="settings"` section with form groups for fleet config, shop management, notification rules, user preferences, and Save/Cancel actions with success toast feedback.

**Layout Pattern**: Sidebar + Topbar (title: "Settings") + main area with form sections + action buttons

**Template Classes Used**: `.app-shell`, `.sidebar`, `.topbar`, `.main`, `.section`, `.settings-group`, `.form-group`, `.form-label`, `.form-input`, `.form-select`, `.form-checkbox`, `.checkbox-label`, `.table-container`, `.table`, `.btn-primary`, `.btn-secondary`, `.btn-link`, `.toast`, `.toast--success`

**Components**:

1. **Topbar Configuration**:
   - Page title: "Settings"

2. **Fleet Settings Section** (white card, `--border` outline, 12px radius, padding 16px, margin-bottom 20px):
   - Section title: "Fleet Settings" (24px, weight 600, `--fg`)
   - Form group 1:
     - Label: "Fleet Name" (14px, weight 600, `--fg`)
     - Input: text field, value "Northwind Logistics", placeholder "Enter fleet name", padding 8-12px, `--border-strong` outline, 8px radius
   - Form group 2:
     - Label: "Total Vehicles" (14px, weight 600, `--fg`)
     - Display-only text: "52" (gray, `--fg-secondary`, no input)
   - Form group 3:
     - Label: "Headquarters Location" (14px, weight 600, `--fg`)
     - Input: text field, value "Chicago, IL 60601", padding 8-12px, `--border-strong` outline, 8px radius

3. **Shop Configuration Section** (white card, padding 16px):
   - Section title: "Shop Configuration" (24px, weight 600, `--fg`)
   - Table: columns [Shop Name, Manager, Address, Edit]
   - 3 shop rows:
     ```
     Downtown Bay | Mike Reynolds | 123 Main St, Chicago IL 60601 | [Edit]
     North Warehouse | Sarah Chen | 4567 Industrial Blvd, Chicago IL 60602 | [Edit]
     East Terminal | Dave Thompson | 8910 Distribution Rd, Chicago IL 60603 | [Edit]
     ```
   - [Edit] buttons: secondary style, small (14px text)
   - [Add New Shop] button (secondary outline, below table)
   - Edit form (stub): inline form with Shop Name, Manager, Address fields, [Save] + [Cancel]

4. **Notification Rules Section** (white card, padding 16px):
   - Section title: "Notification Rules" (24px, weight 600, `--fg`)
   - Checkboxes (all checked by default):
     - ☑ Alert when vehicle in same status > 14 days
     - ☑ Alert when parts on backorder
     - ☑ Alert when inspection fails
     - ☑ Alert when maintenance is overdue
     - ☑ Daily cost summary email (shop managers)
   - Each checkbox: label text 17px, `--fg`, styled checkbox (12px square with `--accent` on checked)

5. **User Preferences Section** (white card, padding 16px):
   - Section title: "User Preferences" (24px, weight 600, `--fg`)
   - Form group 1:
     - Label: "Default Shop View" (14px, weight 600, `--fg`)
     - Dropdown (select): options [All Shops, Downtown Bay, North Warehouse, East Terminal], default "All Shops"
   - Form group 2:
     - Label: "Cost Currency" (14px, weight 600, `--fg`)
     - Dropdown: options [USD, EUR, GBP], default "USD"
   - Form group 3:
     - Label: "Date Format" (14px, weight 600, `--fg`)
     - Dropdown: options [MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD], default "MM/DD/YYYY"

6. **Action Buttons** (sticky, bottom of page, white bg, padding 16px, flex layout):
   - `[Save Settings]` button (primary, `--accent` bg + white text, 8px radius, weight 600)
   - `[Cancel]` link (text, `--accent-link` blue, 14px)

7. **Success Toast** (hidden by default, appears on top-right after Save):
   - Message: "Settings saved successfully"
   - Background: green (`--status-available` or similar)
   - Text: white, 14px
   - Auto-hide after 3 seconds

**Interactions**:
- Text inputs: editable (no validation needed for prototype)
- Dropdowns: selectable, state changes reflected
- Checkboxes: toggle on/off
- [Edit] shop buttons: open inline form (stub, no save needed)
- [Add New Shop] button: show form stub (no save needed)
- [Save Settings] button: show success toast, persist to localStorage (optional for prototype)
- [Cancel] button: revert form to last saved state (stub)

**JavaScript Event Handlers Needed**:
- On page load: populate form fields from saved settings (or defaults)
- Form input changes: update local state
- Checkbox toggles: update state
- Dropdown selects: update state
- [Edit] shop button: toggle inline edit form
- [Add New Shop] button: show new shop form
- [Save Settings] button: save to localStorage, show toast, hide toast after 3s
- [Cancel] button: reload form from saved state

---

## Task 8: Final Wiring & Validation

**Goal**: Verify all 6 pages have complete content, validate DS tokens in :root, ensure navigation works smoothly, fix any placeholder text, and confirm all event handlers are wired.

**Validation Checks**:

1. **Page Content Completeness**:
   - [ ] Vehicles page: table with 12 rows, type filter, search, [Detail] + [Flag Parts] buttons functional
   - [ ] Vehicle Detail page: header card, service checklist (6 items), notes (3 shops), work order history (5 rows), [Advance Status] + [Flag Parts] action buttons functional
   - [ ] Work Orders page: shop tabs (4 tabs), work order table (15 rows), expandable rows with detail
   - [ ] Inspections page: type filter (6 types), inspection table (10 rows), expandable findings detail
   - [ ] Parts & Costs page: 4 KPI cards with deltas, cost table (8 vehicles + subtotal), 13-point bar chart
   - [ ] Settings page: 3 form sections (Fleet, Shops, Notifications, Preferences), [Save] + [Cancel] buttons, success toast

2. **Design System Token Compliance**:
   - [ ] All colors in `:root` match Apple DS tokens (verify #000000, #f5f5f7, #ffffff, #1d1d1f, #6e6e73, #0071e3, #0066cc, #d2d2d7, #86868b, status colors)
   - [ ] Accent color (`--accent: #0071e3`) used only on: sidebar active nav item, primary buttons, form focus, chart highlight (max 2-3 per page)
   - [ ] Typography: Display font for titles (48px, 28px), Text font for body/tables (17px, 14px, 12px)
   - [ ] Spacing: 8px unit system, 16-20px section gaps, 12-16px card padding, 240px sidebar, 56px topbar

3. **Navigation & Routing**:
   - [ ] All 6 nav links in sidebar functional: click → correct page loads with correct title
   - [ ] Hash routes correct: `#/` (vehicles), `#/vehicle/:id`, `#/work-orders`, `#/inspections`, `#/parts-costs`, `#/settings`
   - [ ] Back/forward browser buttons work (hash changes trigger page switch)
   - [ ] Page-to-page links functional: [Detail] buttons → vehicle detail, vehicle unit links → vehicle detail, back links return home
   - [ ] Sidebar + topbar sticky, main content scrolls independently

4. **State Consistency Across Pages**:
   - [ ] Type filter on Vehicles page persists when navigating away + returning (optional, not required for MVP but nice-to-have)
   - [ ] [Advance Status] on Vehicle Detail updates vehicle globally (reflected in Vehicles table on reload)
   - [ ] [Flag Parts] adds to Parts & Costs totals (KPI cards + cost table update when returning to Parts & Costs page)
   - [ ] Work order status changes reflect in Vehicles list (daysInStatus updates)

5. **Placeholder Text Removal**:
   - [ ] No "[Page {id} content — Task {N} fills this]" placeholder text remains
   - [ ] No "TODO", "STUB", or "FIX ME" comments in visible UI
   - [ ] All data is realistic and contextually accurate (dates, costs, unit numbers follow format)

6. **Event Handler Wiring**:
   - [ ] Vehicles page: search input filters table, type filter pills filter table, [Detail] buttons navigate
   - [ ] Vehicle Detail page: service checklist checkboxes toggle (no persistence needed), [Advance Status] dropdown shows valid transitions + updates state, [Flag Parts] form collects input + shows confirmation
   - [ ] Work Orders page: shop tabs filter rows, row click expands detail, [Update Status] dropdown updates WO status
   - [ ] Inspections page: type filter pills filter rows, row click expands findings
   - [ ] Parts & Costs page: vehicle rows link to detail, WO links expand detail
   - [ ] Settings page: form inputs/dropdowns/checkboxes update state, [Save] shows toast, [Cancel] reverts changes

7. **Visual Polish**:
   - [ ] Sidebar + topbar have consistent styling across all pages
   - [ ] All buttons have consistent sizing (primary 8px radius, secondary outline)
   - [ ] Badge colors match status enums (green/orange/red/blue/gray)
   - [ ] Table striping (white/`--bg-light` rows) consistent across all tables
   - [ ] Card shadows and borders are subtle (no heavy drop shadows)
   - [ ] Responsive layout preserves content on 1024px+ width (desktop-first)

8. **Fix Issues**:
   - For any failed checks above, provide specific fix instructions:
     - Missing data: add realistic values
     - Broken link: verify href and data-page attributes
     - Style inconsistency: apply correct DS token
     - Event handler: wire handler in JS block

**Sign-off**:
- All 6 pages functional and complete
- No placeholder text
- DS tokens verified
- Navigation smooth
- Prototype ready for user testing

</tasks>
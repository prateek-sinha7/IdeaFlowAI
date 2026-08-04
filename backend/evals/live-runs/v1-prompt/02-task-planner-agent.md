<tasks>

## Task 1: HTML Shell & Navigation Chrome

**Goal**: Build complete HTML skeleton with all page sections, DS-mapped :root tokens, sidebar + topbar navigation chrome, hash router, and state management.

**DS Token Mapping**:
- --bg: #ffffff (Pure White Canvas)
- --fg: #1d1d1f (Near-Black Ink, primary text)
- --accent: #0071e3 (Apple Action Blue)
- --surface: #f5f5f7 (Pale Apple Gray)
- --border: #d2d2d7 (Soft Border Gray)
- --border-strong: #86868b (Mid Border Gray)
- --muted: #6e6e73 (Secondary Neutral Gray)
- --status-available: #34C759 (green)
- --status-in-shop: #0071e3 (blue)
- --status-awaiting: #FF9500 (orange)
- --status-test: #9933FF (purple)
- --status-out: #FF3B30 (red)
- --status-complete: #34C759 (green)

**Template Classes**: `.sidebar`, `.sidebar-brand`, `.nav-item`, `.nav-item.active`, `.topbar`, `.topbar-left`, `.topbar-right`, `.search-input`, `.user-avatar`, `.main-content`, `.page`, `.page.is-active`, `.page-header`, `.page-title`, `.filter-bar`, `.filter-chip`, `.table`, `.card`, `.kpi-card`, `.grid-2`, `.grid-3`, `.grid-4`, `.modal`, `.modal-overlay`, `.btn`, `.btn-primary`, `.btn-secondary`, `.form-input`, `.form-select`, `.badge`, `.status-badge`, `.kanban-container`, `.kanban-column`, `.kanban-card`

**Chrome**:
- **Left Sidebar** (220px width, sticky, #f5f5f7 background):
  - Brand mark at top: "⬢ Northwind Fleet" (logo concept, 18px, weight 600, color --fg)
  - 6 main nav items (icons + label, 14px SF Pro Text):
    1. Vehicles (#/vehicles)
    2. Work Orders (#/work-orders)
    3. Inspections (#/inspections)
    4. Parts & Costs (#/parts-costs)
    5. Settings (#/settings)
  - Active nav item: background --accent, text white, left border 4px --accent
  - Hover: light background, cursor pointer

- **Top Bar** (height 64px, sticky, white background, border-bottom 1px --border):
  - Left: Page title placeholder (updated per page)
  - Center: (varies by page, e.g., shop selector, date range)
  - Right: Search input (if applicable) + User avatar (initials "MC" in circle) + Name "Marcus Chen"

**Pages** (6 total):
1. vehicles (#/vehicles)
2. vehicle-detail (#/vehicle/:id)
3. work-orders (#/work-orders)
4. inspections (#/inspections)
5. parts-costs (#/parts-costs)
6. settings (#/settings)

**Routes Map**:
```javascript
{
  vehicles: '/vehicles',
  work-orders: '/work-orders',
  inspections: '/inspections',
  parts-costs: '/parts-costs',
  settings: '/settings'
}
```

**Interactions**:
- Hash router: `window.location.hash` → parse route → show/hide page sections
- State store: global `appState` object with vehicles[], workOrders[], inspections[], parts[], settings, currentShop, uiState
- Nav links use `href="#/page"` format
- First page (vehicles) has `class="page is-active"` on load
- Clicking nav item updates active state, navigates to page

---

## Task 2: Vehicles Page (#/vehicles)

**Goal**: Render fleet overview with search, multi-select type filters, status dropdown, days-in-status range slider, and dense vehicle table with 12 realistic rows.

**Layout**: sidebar + topbar (with search + shop selector + export) + filter bar (sticky) + scrollable vehicle table

**Template Classes**: `.page`, `.page-header`, `.page-title`, `.topbar-left`, `.topbar-right`, `.search-input`, `.filter-bar`, `.filter-chip`, `.table`, `.table-row`, `.table-cell`, `.badge`, `.status-badge`, `.btn-secondary`

**Components**:

- **Page Title** (topbar left): "Vehicles" (32px, weight 600, --fg)

- **Topbar Right** (flex, gap 12px):
  - Search input: placeholder "Search by unit number...", onChange filters table rows (case-insensitive partial match on unitNumber)
  - Shop selector dropdown: [Main Garage, North Branch, Downtown Annex], onChange updates work orders and inspections filter globally
  - [Export] button (secondary, 14px)

- **Filter Bar** (sticky below topbar, --surface background, padding 12px 16px, border-bottom 1px --border):
  - Type filter chips (multi-select toggle):
    - "Box Truck" | "Tractor" | "Cargo Van" | "Trailer"
    - Unchosen: border 1px --border, --fg text, background transparent
    - Chosen: background --accent, white text
    - onChange updates table rows (multi-select OR logic)
  - Status dropdown (default "All Status"): [All Status, Available, In Shop, Awaiting Parts, Road Test, Out of Service]
    - onChange filters table to single status or all
  - Days in Status range slider (0–30 days): onChange filters to vehicles within range

- **Vehicle Table** (12 rows, dense 32px row height):
  - Column headers: Unit Number | Make/Model | Type | In-Service Date | Status | Days in Status | Mileage | Last Service | [View]
  - Table data rows (realistic data):
    1. TRK-2026-0184 | Freightliner Cascadia | Tractor | 2019-03-15 | Available (green badge) | 3 | 487,426 mi | 2025-01-10 | [View]
    2. BXX-2024-0917 | Isuzu NPR | Box Truck | 2022-08-20 | In Shop (blue badge) | 1 | 124,839 mi | 2025-01-09 | [View]
    3. VAN-2023-0451 | Ford Transit | Cargo Van | 2020-11-10 | Awaiting Parts (orange badge) | 5 | 203,457 mi | 2024-12-28 | [View]
    4. TRL-2025-0334 | Wabash 53ft Trailer | Trailer | 2018-06-02 | Road Test (purple badge) | 2 | 612,000 mi | 2025-01-08 | [View]
    5. TRK-2026-0185 | Volvo VNL | Tractor | 2021-01-08 | Available | 7 | 321,994 mi | 2025-01-05 | [View]
    6. BXX-2024-0918 | Hino 195 | Box Truck | 2023-02-14 | Available | 0 | 89,201 mi | 2025-01-13 | [View]
    7. VAN-2023-0452 | Mercedes Sprinter | Cargo Van | 2019-09-22 | In Shop | 2 | 445,832 mi | 2025-01-11 | [View]
    8. TRL-2025-0335 | Great Dane Dry Van | Trailer | 2017-12-30 | Out of Service (red badge) | 45 | 789,234 mi | 2024-11-20 | [View]
    9. TRK-2026-0186 | Peterbilt 389 | Tractor | 2022-05-11 | Available | 1 | 156,782 mi | 2025-01-12 | [View]
    10. BXX-2024-0919 | Mitsubishi Fuso | Box Truck | 2021-07-03 | Awaiting Parts | 3 | 267,541 mi | 2025-01-10 | [View]
    11. VAN-2023-0453 | Ford E-Transit | Cargo Van | 2024-01-16 | In Shop | 1 | 34,293 mi | 2025-01-12 | [View]
    12. TRL-2025-0336 | Hyster 40 Low Boy | Trailer | 2020-04-07 | Available | 12 | 567,829 mi | 2024-12-28 | [View]
  - Status badges: 4px radius, 6px horizontal padding, colored per status (--status-available, --status-in-shop, --status-awaiting, --status-test, --status-out)

**Interactions**:
- Search input onChange: filter table rows by partial unitNumber match (real-time, case-insensitive)
- Type filter chips: toggle on/off, multi-select, table re-renders to show only selected types
- Status dropdown: filter table to single status (or all if "All Status" selected)
- Days slider: filter table to vehicles with daysInStatus within range
- [View] button on each row: navigate to `#/vehicle/{unitNumber}` (e.g., `#/vehicle/TRK-2026-0184`)
- Shop selector: persists globally, filters work orders and inspections by shop

**Script handlers needed**:
- `filterTableBySearch()` — filters by unit number
- `toggleTypeFilter(type)` — toggle type selection, rebuild table
- `filterByStatus(status)` — filter table by status
- `filterByDaysInStatus(min, max)` — filter table by days range
- `navigateToVehicleDetail(vehicleId)` — navigate to `#/vehicle/:id`
- `changeShop(shopName)` — update global currentShop state

---

## Task 3: Vehicle Detail Page (#/vehicle/:id)

**Goal**: Render single vehicle details with service checklist, status history, technician notes, and modals for status advancement and parts flagging.

**Layout**: sidebar + topbar (breadcrumb + title + back button) + two-column layout (left: checklist card, right: status + notes + actions)

**Template Classes**: `.page`, `.page-header`, `.breadcrumb`, `.page-title`, `.grid-2`, `.card`, `.card-title`, `.checkbox`, `.status-badge`, `.btn-primary`, `.btn-secondary`, `.modal`, `.modal-overlay`, `.modal-header`, `.modal-body`, `.modal-footer`, `.form-group`, `.form-input`, `.form-select`, `.form-textarea`, `.form-radio`

**Components**:

- **Page Title Area** (topbar):
  - Breadcrumb: "Vehicles > TRK-2026-0184" (linked, left 12px)
  - Center title: "TRK-2026-0184 | Freightliner Cascadia" (28px, weight 600, --fg)
  - Right: [← Back to Vehicles] button (secondary)

- **Left Column: Service Checklist Card** (.card, 12px radius, 1px border --border, 16px padding, --surface background, max-width 400px):
  - Card title: "Service Checklist" (19px, weight 600, --fg)
  - Checklist items (SF Pro Text 14px, --fg):
    - ☑ Oil & Filter Change (Last: 2025-01-10)
    - ☑ Brake Inspection (Last: 2025-01-08)
    - ☑ Tire Rotation (Last: 2024-12-20)
    - ☐ Transmission Service (Due: 2025-04-15, color --muted for incomplete)
    - ☑ Fuel Filter Replacement (Last: 2024-11-30)
    - ☑ Air Filter Service (Last: 2025-01-05)
    - ☐ Suspension Inspection (Due: 2025-03-01, color --muted)
    - ☑ Light & Wiper Check (Last: 2025-01-12)
    - ☐ Battery Load Test (Due: 2025-02-28, color --muted)
    - ☑ Engine Coolant Level (Last: 2025-01-12)

- **Right Column** (flex column, gap 16px):

  - **Status Card** (.card, 12px radius, 1px border --border, 16px padding, white background):
    - Title: "Vehicle Status" (17px, weight 600, --fg)
    - Current status badge: "Available" (--status-available green, 6px h-padding, 4px radius)
    - Days in status: "3 days" (14px, --muted)
    - Status history (3 most recent, 12px SF Pro Text):
      - Available (3 days, 2025-01-10 → present)
      - Road Test (1 day, 2025-01-09 → 2025-01-10)
      - In Shop (2 days, 2025-01-07 → 2025-01-09)

  - **Technician Notes Card** (.card, styling same as Status Card):
    - Title: "Technician Notes (Main Garage)" (17px, weight 600, --fg)
    - Note item (14px SF Pro Text):
      - Technician: Marcus Chen | Date: 2025-01-10
      - Text: "Replaced worn brake pads, all rotors within spec. Coolant flushed. Vehicle ready for service."
      - [Edit] link (blue, 12px)

  - **Action Buttons** (button group, vertical stack, gap 8px):
    - [Advance Status] button (primary fill, 8px radius, 12px h-padding, 8px v-padding, white text, --accent background, cursor pointer)
    - [Flag for Parts] button (secondary, border 1px --border-strong, 8px radius, 12px h-padding, --fg text, transparent background)
    - [View Work Orders] button (link-style, blue #0066cc, 12px)

- **Modal: Advance Status**:
  - Overlay: semi-transparent black (rgba(0,0,0,0.4))
  - Modal box: 16px border-radius, white background, max-width 400px, centered
  - Header: "Move Vehicle Status" (24px, weight 600, --fg)
  - Body:
    - Instruction text: "Select new status and add optional notes." (14px, --muted)
    - Radio button options (17px SF Pro Text, margin-bottom 12px):
      - ○ In Shop
      - ○ Awaiting Parts
      - ○ Road Test
      - ○ Out of Service
    - Textarea: "Notes (optional)" (placeholder, 3 rows, border 1px --border-strong, 8px padding, 8px radius)
  - Footer: [Confirm] button (primary blue, 8px radius) | [Cancel] button (secondary)
  - On confirm: vehicle status updates in appState, modal closes, page re-renders with new status, change reflected on Vehicles and Work Orders pages

- **Modal: Flag for Parts**:
  - Header: "Flag for Parts" (24px, weight 600, --fg)
  - Body:
    - Form group: Label "Part Category" (14px, weight 600), Dropdown: [Engine, Transmission, Brake, Suspension, Electrical, Tires, Other]
    - Form group: Label "Part Name" (14px), Text input (placeholder "e.g., Brake Pad Set")
    - Form group: Label "Quantity" (14px), Number input (default 1, min 1)
    - Form group: Label "Estimated Unit Cost" (14px), Currency input (placeholder "$0.00")
    - Form group: Label "Notes" (14px), Textarea (placeholder "Describe part need...", 3 rows)
  - Footer: [Submit] button (primary blue) | [Cancel] button (secondary)
  - On submit: creates line item in work order, updates Parts & Costs aggregation, modal closes, shows success toast

**Interactions**:
- Breadcrumb "Vehicles" link: navigate back to `#/vehicles`
- [← Back to Vehicles] button: navigate to `#/vehicles`
- [Advance Status] button: open modal, on confirm update status globally, close modal, re-render page
- [Flag for Parts] button: open modal, on submit create line item, update aggregations, close modal
- [View Work Orders] link: navigate to `#/work-orders` (filtered to this vehicle's work orders if possible)

**Script handlers needed**:
- `openAdvanceStatusModal(vehicleId)` — show modal
- `confirmAdvanceStatus(newStatus, notes)` — update vehicle status, persist, close modal, trigger page updates
- `cancelModal()` — close modal
- `openFlagForPartsModal(vehicleId)` — show modal
- `submitFlagForParts(category, partName, qty, cost, notes)` — create line item, update aggregations, close modal
- `navigateToWorkOrders(vehicleId)` — navigate to work orders filtered by vehicle

---

## Task 4: Work Orders Page (#/work-orders)

**Goal**: Render Kanban-style work order queue with 5 status columns (Pending, In Shop, Awaiting Parts, Road Test, Complete), drag-to-advance vehicle cards, and click-for-details modal.

**Layout**: sidebar + topbar (shop selector + new work order button) + 5 equal-width Kanban columns (horizontal scrollable)

**Template Classes**: `.page`, `.page-header`, `.page-title`, `.topbar-center`, `.form-select`, `.btn-primary`, `.kanban-container`, `.kanban-column`, `.kanban-card`, `.card`, `.card-title`, `.badge`, `.status-badge`, `.modal`, `.modal-overlay`, `.modal-header`, `.modal-body`, `.modal-footer`, `.table`, `.form-group`, `.form-input`, `.form-select`, `.form-textarea`

**Components**:

- **Page Title** (topbar left): "Work Orders" (32px, weight 600, --fg)

- **Topbar Center**: Shop selector dropdown (default "Main Garage") → [Main Garage, North Branch, Downtown Annex]
  - onChange: re-render Kanban columns to show only selected shop's work orders

- **Topbar Right**: [+ New Work Order] button (primary blue, 14px)

- **Kanban Container** (horizontal flex, gap 16px, padding 16px, overflow-x auto, min-width 100%):

  - **Column 1: Pending** (width 20%, --surface background, 12px padding, 8px border-radius, min-height 600px):
    - Header: "Pending" (17px, weight 600, --fg, margin-bottom 12px)
    - Cards (3 total):
      - Card (white background, 12px radius, 1px border --border, 12px padding, cursor grab, margin-bottom 12px):
        - Vehicle unit: "TRK-2026-0187" (14px, weight 600, --fg)
        - Type icon: "🚛" (tractor symbol)
        - Text: "Scheduled: 2025-01-15" (12px, --muted)
        - Drag handle (≡ symbol, top-right, opacity 0.5)
      - Card: TRK-2026-0187, "Scheduled: 2025-01-15"
      - Card: BXX-2024-0920, "Scheduled: 2025-01-16"
      - Card: VAN-2023-0454, "Scheduled: 2025-01-17"

  - **Column 2: In Shop** (width 20%, header text blue --accent):
    - Header: "In Shop" (17px, weight 600, color --accent, margin-bottom 12px)
    - Cards (4 total):
      - TRK-2026-0184: "Work: Oil change + brake service ($465.00)"
      - BXX-2024-0918: "Work: Transmission inspection ($185.00)"
      - VAN-2023-0453: "Work: Engine diagnostics ($240.00)"
      - TRL-2025-0334: "Work: Brake system overhaul ($780.00)"

  - **Column 3: Awaiting Parts** (width 20%, header text orange #FF9500):
    - Header: "Awaiting Parts" (17px, weight 600, color #FF9500)
    - Cards (2 total):
      - VAN-2023-0452: "Parts: Transmission seal (Est. arrival: 2025-01-18)"
      - BXX-2024-0919: "Parts: Engine block (Est. arrival: 2025-01-20)"

  - **Column 4: Road Test** (width 20%, header text purple #9933FF):
    - Header: "Road Test" (17px, weight 600, color #9933FF)
    - Cards (1 total):
      - TRL-2025-0335: "Test: Post-service validation"

  - **Column 5: Complete** (width 20%, header text green --status-complete):
    - Header: "Complete" (17px, weight 600, color --status-complete)
    - Cards (8 total, opacity 0.7 for completed state):
      - TRK-2026-0188: "Completed: 2025-01-12"
      - BXX-2024-0921: "Completed: 2025-01-11"
      - VAN-2023-0455: "Completed: 2025-01-10"
      - (... 5 more completed cards)

- **Card Styling**:
  - Hover: box-shadow 0 2px 8px rgba(0,0,0,0.1), cursor grab
  - Drag state: cursor grabbing, transform scale(0.98)
  - Click: opens work order details modal

- **Modal: Work Order Details**:
  - Header: "Work Order WO-001" (24px, weight 600, --fg)
  - Body:
    - Vehicle info: "TRK-2026-0184 | Freightliner Cascadia" (17px, --fg)
    - Status badge: "In Shop" (blue, 4px radius)
    - Date created: "2025-01-10" (12px, --muted)
    - Estimated completion: "2025-01-14" (12px, --muted)
    - **Line Items Table**:
      - Headers: Description | Qty | Unit Cost | Total
      - Rows:
        | Oil & Filter Change | 1 | $45.00 | $45.00 |
        | Brake Pad Set | 1 | $120.00 | $120.00 |
        | Labor (4 hrs @ $75/hr) | 4 | $75.00 | $300.00 |
      - Total row: (bold, right-aligned) $465.00
    - Notes (read-only): "Replaced worn brake pads, all rotors within spec."
  - Footer: [Edit] button | [Delete] button | [Close] button

- **Modal: New Work Order**:
  - Header: "Create Work Order"
  - Body:
    - Form group: Label "Vehicle" (14px), Select dropdown (populated from vehicles list, required)
    - Form group: Label "Initial Status" (14px), Radio buttons: Pending | In Shop | Awaiting Parts | Road Test
    - Form group: Label "Estimated Completion" (14px), Date picker input
    - Form group: Label "Notes" (14px), Textarea (optional)
  - Footer: [Create] button (primary blue) | [Cancel] button

**Interactions**:
- Shop selector onChange: re-render columns filtered by shop
- Drag card from column A to column B: vehicle status updates (column status defines new status), reflected on Vehicles page immediately
- Click card: open work order details modal (read-only or editable)
- [+ New Work Order] button: open new work order form modal
- On new work order submit: create work order, add to Kanban column (initial status), re-render
- On work order drag-drop: update vehicle.currentStatus, update workOrder.status, persist state

**Script handlers needed**:
- `changeShop(shopName)` — filter Kanban by selected shop
- `dragCard(cardElement, fromColumn, toColumn)` — handle drag start/end, update status
- `dropCard(vehicleId, newStatus)` — update vehicle status and work order status in appState
- `openWorkOrderModal(workOrderId)` — show details modal
- `openNewWorkOrderModal()` — show form modal
- `submitNewWorkOrder(vehicleId, status, estimatedCompletion, notes)` — create work order, add to Kanban, close modal
- `deleteWorkOrder(workOrderId)` — remove work order, close modal

---

## Task 5: Inspections Page (#/inspections)

**Goal**: Render inspection table with multi-filter controls (status, type, date range), dense 15-row format, and modals for assignment, details, and scheduling.

**Layout**: sidebar + topbar (title + schedule button) + filter bar (sticky) + dense inspection table

**Template Classes**: `.page`, `.page-header`, `.page-title`, `.topbar-right`, `.btn-primary`, `.filter-bar`, `.filter-chip`, `.table`, `.table-row`, `.table-cell`, `.badge`, `.status-badge`, `.btn-secondary`, `.modal`, `.modal-overlay`, `.modal-header`, `.modal-body`, `.modal-footer`, `.form-group`, `.form-input`, `.form-select`, `.form-textarea`

**Components**:

- **Page Title** (topbar left): "Inspections" (32px, weight 600, --fg)

- **Topbar Right**: [+ Schedule Inspection] button (primary blue, 14px)

- **Filter Bar** (sticky, --surface background, padding 12px 16px, border-bottom 1px --border):
  - Status filter chips (multi-select): "All" | "Scheduled" | "In Progress" | "Completed"
    - Unchosen: border 1px --border, --fg text, background transparent
    - Chosen: background --accent, white text
  - Inspection type filter chips (multi-select): "All" | "Safety" | "Emissions" | "Routine" | "Annual"
  - Date range selector buttons: "This Week" | "This Month" | "Custom date range"

- **Inspections Table** (15 rows, row height 32px, dense):
  - Column headers: Unit Number | Vehicle Type | Inspection Type | Scheduled Date | Status | Inspector | Findings | [Actions]
  - Data rows (realistic):
    1. TRK-2026-0184 | Tractor | Routine | 2025-02-01 | Scheduled (gray badge) | [Unassigned] | — | [Assign] [View]
    2. BXX-2024-0917 | Box Truck | Safety | 2025-01-16 | In Progress (blue badge) | Sarah Martinez | — | [View] [Mark Complete]
    3. VAN-2023-0451 | Cargo Van | Emissions | 2025-01-14 | Completed (green badge) | James Park | Pass ✓ | [View]
    4. TRL-2025-0334 | Trailer | Routine | 2025-02-15 | Scheduled | [Unassigned] | — | [Assign] [View]
    5. TRK-2026-0185 | Tractor | Annual | 2025-03-01 | Scheduled | Marcus Chen | — | [View] [Mark In Progress]
    6. BXX-2024-0918 | Box Truck | Safety | 2025-01-13 | Completed | Marcus Chen | Pass ✓ | [View]
    7. VAN-2023-0452 | Cargo Van | Routine | 2025-02-05 | Scheduled | [Unassigned] | — | [Assign] [View]
    8. TRL-2025-0335 | Trailer | Emissions | 2025-01-18 | In Progress | David Lee | — | [View] [Mark Complete]
    9. TRK-2026-0186 | Tractor | Safety | 2025-02-08 | Scheduled | [Unassigned] | — | [Assign] [View]
    10. BXX-2024-0919 | Box Truck | Routine | 2025-02-10 | Scheduled | Sarah Martinez | — | [View]
    11. VAN-2023-0453 | Cargo Van | Annual | 2025-03-15 | Scheduled | [Unassigned] | — | [Assign] [View]
    12. TRL-2025-0336 | Trailer | Routine | 2025-02-12 | Scheduled | [Unassigned] | — | [Assign] [View]
    13. TRK-2026-0187 | Tractor | Emissions | 2025-01-17 | Completed | James Park | Pass ✓ | [View]
    14. BXX-2024-0920 | Box Truck | Safety | 2025-01-19 | In Progress | Marcus Chen | — | [View] [Mark Complete]
    15. VAN-2023-0454 | Cargo Van | Routine | 2025-02-20 | Scheduled | [Unassigned] | — | [Assign] [View]
  - Status badges: Scheduled=--muted, In Progress=--status-in-shop, Completed=--status-complete

- **Modal: Assign Inspector**:
  - Header: "Assign Inspector"
  - Body:
    - Vehicle (read-only): "TRK-2026-0184" (14px, --muted)
    - Form group: Label "Inspector" (14px), Dropdown: [Marcus Chen, Sarah Martinez, James Park, David Lee, Elena Rodriguez, Robert Brown]
  - Footer: [Assign] button (primary blue) | [Cancel]

- **Modal: Inspection Details**:
  - Header: "Inspection Details - TRK-2026-0184"
  - Body:
    - Type: "Routine" (14px)
    - Scheduled Date: "2025-02-01" (14px)
    - Status: "Scheduled" or "In Progress" or "Completed" (badge, 12px)
    - Inspector: "[Unassigned]" or name (14px)
    - Findings (if completed, 12px):
      - "Engine runs smoothly"
      - "Brake response time within spec"
      - "No fluid leaks detected"
    - Result: "Pass" or "Fail" badge
  - Footer: [Edit] | [Delete] | [Close]

- **Modal: Schedule Inspection**:
  - Header: "Schedule Inspection"
  - Body:
    - Form group: Label "Vehicle" (14px), Select dropdown (populated from vehicles)
    - Form group: Label "Inspection Type" (14px), Radio buttons: Safety | Emissions | Routine | Annual
    - Form group: Label "Scheduled Date" (14px), Date picker
    - Form group: Label "Assigned Inspector (optional)" (14px), Select dropdown
    - Form group: Label "Notes (optional)" (14px), Textarea
  - Footer: [Schedule] button (primary blue) | [Cancel]

**Interactions**:
- Status filter chips: toggle multi-select, table re-renders to show only selected statuses
- Inspection type filter chips: toggle multi-select, table re-renders
- Date range buttons: filter table to matching date ranges
- [Assign] button: open assign inspector modal, on submit update inspection, close modal
- [View] button: open inspection details modal (read-only)
- [Mark Complete] button: inline action to update status to Completed, open findings modal
- [Mark In Progress] button: inline action to update status to In Progress
- [+ Schedule Inspection] button: open schedule form modal, on submit create inspection, add to table

**Script handlers needed**:
- `toggleStatusFilter(status)` — toggle filter, rebuild table
- `toggleTypeFilter(type)` — toggle filter, rebuild table
- `filterByDateRange(range)` — filter table by date range
- `openAssignModal(inspectionId)` — show assign modal
- `submitAssign(inspectionId, inspector)` — update inspection, close modal
- `openDetailsModal(inspectionId)` — show details modal (read-only)
- `openScheduleModal()` — show schedule form modal
- `submitScheduleInspection(vehicleId, type, date, inspector, notes)` — create inspection, add to table
- `markInProgress(inspectionId)` — update status, persist
- `markComplete(inspectionId)` — update status, open findings modal

---

## Task 6: Parts & Costs Page (#/parts-costs)

**Goal**: Render KPI summary cards (Total Cost, WO Count, Avg Cost, Open Parts) and dense 18-row parts aggregation table with sorting and work order linkage.

**Layout**: sidebar + topbar (date range selector + export button) + 4 KPI cards (grid) + dense parts table

**Template Classes**: `.page`, `.page-header`, `.page-title`, `.topbar-center`, `.topbar-right`, `.btn-secondary`, `.kpi-card`, `.grid-4`, `.grid-2`, `.grid-3`, `.table`, `.table-row`, `.table-cell`, `.table-header.sortable`, `.btn-link`

**Components**:

- **Page Title** (topbar left): "Parts & Costs" (32px, weight 600, --fg)

- **Topbar Center**: Date range selector (buttons or dropdown):
  - "This Month" | "Last Month" | "Last 3 Months" | "Custom date range"
  - onChange: re-calculate KPI cards and update table data

- **Topbar Right**: [Export CSV] button (secondary, 14px)

- **KPI Cards** (grid-4, responsive, gap 16px, margin-bottom 24px):

  - **Card 1: Total Parts Cost**
    - Label: "Total Parts Cost" (SF Pro Text 14px, weight 400, color --muted)
    - Big number: "$12,847.50" (SF Pro Display 32px, weight 600, color --fg)
    - Delta: "+$847.50 vs. last month" (SF Pro Text 12px, color --status-available green)
    - Card styling: 12px radius, 1px border --border, 16px padding, --surface background

  - **Card 2: Work Order Count**
    - Label: "Work Order Count"
    - Big number: "24"
    - Delta: "+4 vs. last month" (green)

  - **Card 3: Avg Cost per Order**
    - Label: "Avg Cost per Order"
    - Big number: "$535.31"
    - Delta: "+$12 vs. last month" (green)

  - **Card 4: Open/Pending Parts**
    - Label: "Open/Pending Parts"
    - Big number: "7"
    - Delta: "+2 vs. last week" (orange #FF9500, indicating increase)

- **Parts Cost Breakdown Table** (18 rows, row height 32px, dense):
  - Column headers (sortable on click): Part Name | Category | Vendor | Unit Cost | Qty | Total Cost | Used in Work Orders | [View]
  - Data rows (aggregated from all work order line items):
    1. Brake Pad Set | Brake | Autopart Supply | $120.00 | 8 | $960.00 | WO-001, WO-005, WO-012, ... | [View]
    2. Transmission Seal | Transmission | Industrial Parts Co | $285.00 | 2 | $570.00 | WO-003, WO-009 | [View]
    3. Oil (Diesel, 5qt) | Engine | Quaker State | $18.50 | 32 | $592.00 | WO-001, WO-004, WO-007, ... | [View]
    4. Tire (11R24.5) | Tires | Goodyear | $475.00 | 4 | $1,900.00 | WO-002, WO-006, WO-014, ... | [View]
    5. Air Filter | Engine | Baldwin | $42.00 | 6 | $252.00 | WO-001, WO-007, WO-010, ... | [View]
    6. Fuel Filter | Engine | FLEETGUARD | $28.50 | 5 | $142.50 | WO-004, WO-008, WO-015, ... | [View]
    7. Coolant (50/50, gal) | Engine | Prestone | $22.00 | 12 | $264.00 | WO-001, WO-005, WO-011, ... | [View]
    8. Brake Fluid (DOT 4, qt) | Brake | ATE | $15.00 | 20 | $300.00 | WO-002, WO-006, WO-009, ... | [View]
    9. Wiper Blades (pair) | Body | Bosch | $35.00 | 14 | $490.00 | WO-001, WO-003, WO-005, ... | [View]
    10. Spark Plugs (set of 8) | Engine | NGK | $48.00 | 3 | $144.00 | WO-004, WO-008, WO-016 | [View]
    11. Battery (Heavy Duty) | Electrical | Optima | $285.00 | 2 | $570.00 | WO-010, WO-025 | [View]
    12. Radiator Cap | Engine | Stant | $18.00 | 4 | $72.00 | WO-007, WO-014, WO-021, ... | [View]
    13. Water Pump | Engine | Atsco | $195.00 | 1 | $195.00 | WO-019 | [View]
    14. Alternator | Electrical | Remy | $425.00 | 1 | $425.00 | WO-022 | [View]
    15. Serpentine Belt | Engine | Gates | $68.00 | 2 | $136.00 | WO-011, WO-023 | [View]
    16. Hose Kit (assorted) | Engine | Dayco | $85.00 | 3 | $255.00 | WO-005, WO-015, WO-030 | [View]
    17. Thermostat | Engine | Stant | $32.00 | 2 | $64.00 | WO-009, WO-020 | [View]
    18. Grease (cartridge) | Maintenance | NLGI-2 | $12.50 | 8 | $100.00 | WO-002, WO-006, WO-012, ... | [View]
  - Totals row (bold, sticky bottom): TOTAL | — | — | — | 152 | $12,847.50 | — | —
  - Table sorting: clicking column header toggles ascending/descending sort (Part Name, Total Cost, Qty, etc.)

**Interactions**:
- Date range selector onChange: re-calculate KPI cards, filter table data to date range
- Column header click (sortable): toggle sort ascending/descending, re-order table rows
- [View] link in "Used in Work Orders" column: navigate to `#/work-orders` page (highlight or filter to those work orders)
- [Export CSV] button: download CSV file with columns (Part Name, Category, Vendor, Unit Cost, Total Qty, Total Cost, Work Orders)

**Script handlers needed**:
- `changeDateRange(range)` — re-calculate KPIs, filter table, persist date selection
- `sortTableByColumn(columnName)` — toggle sort order, re-render table
- `navigateToWorkOrdersForPart(workOrderIds)` — navigate to `#/work-orders` filtered by those WO IDs
- `exportCSV()` — generate and download CSV file from table data

---

## Task 7: Settings Page (#/settings)

**Goal**: Render three-column form layout (Shop Configuration, User Preferences, System Settings) with individual Save buttons per column, Danger Zone at bottom, and success/error notifications.

**Layout**: sidebar + topbar (title + Save All button) + 3-column form grid + Danger Zone section

**Template Classes**: `.page`, `.page-header`, `.page-title`, `.topbar-right`, `.btn-primary`, `.grid-3`, `.card`, `.card-title`, `.form-group`, `.form-input`, `.form-label`, `.form-select`, `.form-radio`, `.form-checkbox`, `.form-textarea`, `.btn-secondary`, `.btn-destructive`, `.modal`, `.modal-overlay`, `.modal-header`, `.modal-body`, `.modal-footer`, `.toast`

**Components**:

- **Page Title** (topbar left): "Settings" (32px, weight 600, --fg)

- **Topbar Right**: [Save All] button (primary blue, 14px, initially disabled until any form change detected)

- **Three-Column Form Layout** (grid-3, gap 16px, responsive to 1 column on mobile, margin-bottom 32px):

  - **Column 1: Shop Configuration** (.card, 12px radius, 1px border --border, 16px padding, white background):
    - Card title: "Shop Configuration" (SF Pro Display 19px, weight 600, --fg)
    - Form group:
      - Label: "Shop Name" (SF Pro Text 14px, weight 600, --fg)
      - Input: text field, value "Main Garage", border 1px --border-strong, 8px padding, 8px radius
    - Form group:
      - Label: "Location" (14px)
      - Input: text field, value "123 Fleet Ave, City, State"
    - Form group:
      - Label: "Phone" (14px)
      - Input: tel field, value "(555) 123-4567"
    - Form group:
      - Label: "Hours of Operation" (14px)
      - Inputs: time range (From: 06:00, To: 18:00), gap 8px between fields
    - Form group:
      - Label: "Shop Manager" (14px)
      - Select dropdown: [Marcus Chen, Sarah Martinez, James Park, David Lee, Elena Rodriguez]
    - [Save] button (primary blue, 8px radius, 12px h-padding, 8px v-padding, 14px SF Pro Text)

  - **Column 2: User Preferences** (.card, styling same):
    - Card title: "User Preferences"
    - Form group: Label "Display Name" (14px), Input text, value "Marcus Chen"
    - Form group: Label "Email" (14px), Input email, value "marcus@northwindlogistics.com"
    - Form group: Label "Role" (14px), Select dropdown: [Technician, Shop Manager, Coordinator, Admin]
    - Form group: Label "Assigned Shop" (14px), Select dropdown: [Main Garage, North Branch, Downtown Annex]
    - Form group: Label "Theme" (14px), Radio buttons: ◉ Light (selected) | ○ Dark
    - Form group:
      - Label: "Notifications" (14px, font-weight 600)
      - Checkboxes (12px SF Pro Text, margin-top 8px):
        - ☑ Email on work order completion
        - ☑ Daily summary report
        - ☐ Low stock alerts
    - [Save] button

  - **Column 3: System Settings** (.card, styling same):
    - Card title: "System Settings"
    - Form group: Label "Maintenance Interval (hours)" (14px), Number input, value "500", min 100, max 2000
    - Form group: Label "Inspection Frequency (days)" (14px), Number input, value "90", min 30, max 365
    - Form group: Label "Work Order Auto-Archive (days)" (14px), Number input, value "30", min 7, max 365
    - Form group: Label "Low Stock Alert Threshold" (14px), Number input, value "5", min 1, max 100
    - Form group: Label "Default Hourly Labor Rate" (14px), Currency input (prefix "$"), value "75.00"
    - [Save] button

- **Danger Zone** (full-width card below form columns, border-top 2px --status-out red):
  - Card title: "Danger Zone" (SF Pro Display 17px, weight 600, color --status-out red)
  - Buttons (gap 8px):
    - [Clear All Data] button (destructive red background, white text, 8px radius)
    - [Export Fleet Data] button (secondary, 8px radius)
  - On [Clear All Data] click: open confirmation modal
  - On [Export Fleet Data] click: download JSON backup file

- **Modal: Clear Data Confirmation**:
  - Header: "Clear All Data?"
  - Body: "Are you sure? This action cannot be undone. All vehicles, work orders, inspections, and settings will be reset to defaults." (14px, --fg)
  - Footer: [Clear] button (destructive red) | [Cancel] button (secondary)
  - On [Clear] click: reset appState to defaults, close modal, show success toast

**Interactions**:
- Form inputs onChange: detect changes, enable [Save All] button if any changes
- [Save] button per column: validate form fields (required, email format, positive numbers), on valid → persist settings, show success toast "Settings saved"
- On validation error: show error toast with message (e.g., "Invalid email format")
- [Save All] button: save all three columns if changes detected, persist all, show success toast
- [Clear All Data] button: open confirmation modal
- On confirmation: reset appState to defaults, show success toast "Data cleared"
- [Export Fleet Data] button: generate JSON with all vehicles, work orders, inspections, parts, settings, download as fleet-backup-{date}.json

**Script handlers needed**:
- `detectFormChange()` — listen to all inputs, enable [Save All] when changes detected
- `saveShopConfig()` — validate, persist column 1 settings
- `saveUserPreferences()` — validate, persist column 2 settings
- `saveSystemSettings()` — validate, persist column 3 settings
- `saveAllSettings()` — validate and persist all three columns
- `openClearDataModal()` — show confirmation modal
- `confirmClearData()` — reset appState, show toast
- `exportFleetData()` — generate and download JSON backup
- `showToast(message, type)` — show success/error toast notification

---

## Task 8: Final Wiring & Validation

**Goal**: Verify all 6 pages have complete content (no placeholders), ensure DS tokens match ACTIVE DESIGN SYSTEM, fix nav link formatting, confirm first page is active on load, validate all buttons have handlers, and test state cascades across pages.

**Checks**:

1. **Page Content Validation**:
   - Vehicles page: table populated with 12 vehicle rows, all columns visible, filters functional
   - Vehicle Detail page: service checklist visible, status card visible, technician notes visible, action buttons present
   - Work Orders page: Kanban container with 5 columns, cards distributed across columns, drag-drop functional
   - Inspections page: table populated with 15 inspection rows, all columns visible, filters functional
   - Parts & Costs page: 4 KPI cards visible with values, parts table populated with 18 rows, sorting functional
   - Settings page: 3-column form layout visible, all form fields present and initialized with values, Danger Zone visible

2. **DS Token Verification**:
   - All colors in CSS come from spec's token mapping (--bg, --fg, --accent, --surface, --border, --border-strong, --muted, --status-*)
   - No hardcoded colors outside :root variables (except status-specific colors which are mapped)
   - Typography uses SF Pro Display and SF Pro Text with fallbacks
   - Spacing follows 8px base unit (8px, 12px, 16px, 24px, 32px)
   - Border radius follows tiers (4px pills, 8px controls, 12px cards, 16px modals)

3. **Navigation & Routing**:
   - All sidebar nav links use `href="#/page"` format (not `href="#page"`)
   - Vehicle Detail route is `#/vehicle/{unitNumber}` (parameterized)
   - Hash router correctly parses routes and shows/hides page sections
   - First page (vehicles) has `class="page is-active"` on initial load
   - Clicking nav item updates active state (highlight + underline or background color)
   - Breadcrumb links on Vehicle Detail page navigate correctly back to Vehicles

4. **Button & Form Handler Validation**:
   - All primary action buttons ([Advance Status], [Save], [Create], [Schedule], etc.) have click handlers defined
   - Form submit buttons validate input and prevent submission if invalid
   - Modal close buttons (X, [Cancel]) close modal without persisting
   - Modal action buttons ([Confirm], [Submit], [Create]) close modal and update state
   - Status update buttons trigger cascading updates (visible on Vehicles and Work Orders)
   - Success/error toasts appear after actions with appropriate messages

5. **State Cascade Verification**:
   - Update vehicle status in Vehicle Detail → status updates on Vehicles page table immediately
   - Drag work order card between Kanban columns → vehicle status updates, visible on Vehicles page
   - Flag for parts in Vehicle Detail → line item created, Parts & Costs table updated with new part aggregation
   - Schedule inspection → appears on Inspections table with correct date/type
   - Change shop selector on Work Orders → Work Orders page filters to selected shop, Inspections page filters by shop

6. **Data Consistency**:
   - Vehicle unit numbers in all pages match (TRK-2026-0184 appears consistently)
   - Work order line items sum correctly to total cost
   - Parts aggregation matches work order totals
   - Inspection assignments persist across page navigation
   - Technician notes remain visible on subsequent visits to Vehicle Detail

7. **Placeholder Text Removal**:
   - No "Lorem ipsum" or placeholder text in any table or card
   - All KPI card values are realistic numbers (not "N/A" or "TBD")
   - Modal form placeholders are helpful hints (e.g., "e.g., Brake Pad Set") not generic "Enter text"

8. **Responsive Behavior** (desktop-first):
   - All pages render correctly at 1024px+ width (primary target)
   - Tables and grids remain visible with horizontal scroll if needed on narrower screens
   - Filter bars remain sticky during vertical scroll
   - Modals center on screen and are keyboard-closable (Esc key)
   - Buttons maintain minimum 44px touch target height

**Validation Actions**:
- Load app in browser, verify first page is Vehicles and is active
- Click each sidebar nav item, verify correct page loads and nav item highlights
- Click [View] on a vehicle, verify navigation to `#/vehicle/{id}` works
- Click [Advance Status], modify status, click [Confirm], verify status updates on Vehicles page
- Drag a card in Work Orders Kanban from one column to another, verify vehicle status updates
- Flag for parts in Vehicle Detail, verify new part line appears on Parts & Costs page
- Change shop selector, verify Work Orders and Inspections filter to selected shop
- Try submitting form with missing required fields, verify validation error displays
- Close modal with [Cancel] or X button, verify state not persisted
- Refresh page (F5), verify state persists (if using localStorage) or defaults apply
- Test all [Export] and [Import] buttons, verify file operations work (CSV, JSON downloads)

</tasks>
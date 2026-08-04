<spec>
# Prototype Specification: Northwind Logistics Fleet Maintenance Console

## Template & Design System
- **Template**: dashboard (sidebar navigation + top bar + main content area) — adapted for multi-page fleet operations UI with persistent vehicle state across pages
- **Design System**: Apple — premium white space, SF Pro typography, neutral triad (#000000/#f5f5f7/#ffffff), blue accents (#0071e3) for actions and links, restrained depth using borders and surface stepping
- **CSS Class System**: `.sidebar`, `.topbar`, `.main-content`, `.page-header`, `.page-title`, `.search-input`, `.filter-chip`, `.filter-bar`, `.table`, `.table-row`, `.kpi-card`, `.grid-2`, `.grid-3`, `.grid-4`, `.card`, `.card-title`, `.badge`, `.status-badge`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-destructive`, `.modal`, `.modal-overlay`, `.form-group`, `.form-input`, `.form-select`, `.form-textarea`, `.kanban-container`, `.kanban-column`, `.kanban-card`
- **Color Tokens**: `--bg=#ffffff`, `--fg=#1d1d1f`, `--accent=#0071e3`, `--surface=#f5f5f7`, `--border=#d2d2d7`, `--border-strong=#86868b`, `--muted=#6e6e73`, `--status-available=#34C759`, `--status-in-shop=#0071e3`, `--status-awaiting=#FF9500`, `--status-test=#9933FF`, `--status-out=#FF3B30`, `--status-complete=#34C759`

## Overview
- **Product**: Fleet Maintenance Management Console for Northwind Logistics garage operations
- **Target audience**: Garage technicians, shop managers, fleet dispatchers
- **Core purpose**: Track vehicle status and health, manage multi-shop work order queues, log maintenance and inspections, aggregate parts costs, and coordinate vehicle state transitions across the maintenance pipeline
- **Total pages**: 6 (Vehicles, Vehicle Detail, Work Orders, Inspections, Parts & Costs, Settings)

## Pages & Navigation

| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| vehicles | `#/vehicles` | Fleet overview with status filtering, type/unit filtering, and search | sidebar + topbar with filters + dense table | Yes |
| vehicle-detail | `#/vehicle/:id` | Single vehicle service checklist, technician notes per shop, status actions | sidebar + topbar + two-column detail cards + modals | No |
| work-orders | `#/work-orders` | Work order queues organized by shop, Kanban-style status columns (Pending → In Shop → Awaiting Parts → Road Test → Complete) | sidebar + topbar with shop selector + 5 kanban columns | Yes |
| inspections | `#/inspections` | Scheduled and completed inspections with assignment, findings, and filtering | sidebar + topbar with filter bar + dense inspection table | Yes |
| parts-costs | `#/parts-costs` | Parts inventory and cumulative costs aggregated from work order line items; KPI summary and cost breakdown table | sidebar + topbar with date range + KPI cards + parts table | Yes |
| settings | `#/settings` | Shop configuration, user preferences, system settings, and system administration | sidebar + topbar + form panels (3-column layout) | Yes |

## Page Specifications

### Vehicles (`#/vehicles`)

**Layout**: sidebar + topbar + search/filter controls + dense scrollable table

**Template classes**: `.sidebar`, `.topbar`, `.page-header`, `.page-title`, `.search-input`, `.filter-bar`, `.filter-chip`, `.table`, `.table-row`, `.badge`, `.status-badge`, `.btn-secondary`

**Components**:

- **Top bar**:
  - Left: Page title "Vehicles" (SF Pro Display 32px, weight 600, color --fg)
  - Right: Search input (placeholder: "Search by unit number..."), Shop selector dropdown, Export button (secondary)

- **Filter bar** (below topbar, sticky):
  - Type filter chips (multi-select): "Box Truck" | "Tractor" | "Cargo Van" | "Trailer" (toggle state, unchosen = light gray border, chosen = blue fill)
  - Status filter dropdown: "All Status" | "Available" | "In Shop" | "Awaiting Parts" | "Road Test" | "Out of Service"
  - Days in status range slider: 0-30 days

- **Vehicle table** (12 rows of data, scrollable):
  - Columns: Unit Number | Make/Model | Type | In-Service Date | Status | Days in Status | Mileage | Last Service | [View]
  - Realistic data rows:
    | TRK-2026-0184 | Freightliner Cascadia | Tractor | 2019-03-15 | Available | 3 | 487,426 mi | 2025-01-10 | [View] |
    | BXX-2024-0917 | Isuzu NPR | Box Truck | 2022-08-20 | In Shop | 1 | 124,839 mi | 2025-01-09 | [View] |
    | VAN-2023-0451 | Ford Transit | Cargo Van | 2020-11-10 | Awaiting Parts | 5 | 203,457 mi | 2024-12-28 | [View] |
    | TRL-2025-0334 | Wabash 53ft Trailer | Trailer | 2018-06-02 | Road Test | 2 | 612,000 mi | 2025-01-08 | [View] |
    | TRK-2026-0185 | Volvo VNL | Tractor | 2021-01-08 | Available | 7 | 321,994 mi | 2025-01-05 | [View] |
    | BXX-2024-0918 | Hino 195 | Box Truck | 2023-02-14 | Available | 0 | 89,201 mi | 2025-01-13 | [View] |
    | VAN-2023-0452 | Mercedes Sprinter | Cargo Van | 2019-09-22 | In Shop | 2 | 445,832 mi | 2025-01-11 | [View] |
    | TRL-2025-0335 | Great Dane Dry Van | Trailer | 2017-12-30 | Out of Service | 45 | 789,234 mi | 2024-11-20 | [View] |
    | TRK-2026-0186 | Peterbilt 389 | Tractor | 2022-05-11 | Available | 1 | 156,782 mi | 2025-01-12 | [View] |
    | BXX-2024-0919 | Mitsubishi Fuso | Box Truck | 2021-07-03 | Awaiting Parts | 3 | 267,541 mi | 2025-01-10 | [View] |
    | VAN-2023-0453 | Ford E-Transit | Cargo Van | 2024-01-16 | In Shop | 1 | 34,293 mi | 2025-01-12 | [View] |
    | TRL-2025-0336 | Hyster 40 Low Boy | Trailer | 2020-04-07 | Available | 12 | 567,829 mi | 2024-12-28 | [View] |
  - Status badges colored: Available=#34C759 (green), In Shop=#0071e3 (blue), Awaiting Parts=#FF9500 (orange), Road Test=#9933FF (purple), Out of Service=#FF3B30 (red)

- **Interactions**:
  - Search input filters table rows by partial unit number match (case-insensitive, real-time)
  - Type filter chips toggle on/off; table updates to show only selected types (multi-select)
  - Status dropdown narrows table to single status (or "All")
  - Days slider filters to vehicles in status within range
  - [View] button on each row navigates to `#/vehicle/:id` where `:id` is the unit number (e.g., `#/vehicle/TRK-2026-0184`)
  - Shop selector persists across pages, filtering work orders and inspections by assigned shop

**Data Model**:
```
vehicles: [
  {
    id: "TRK-2026-0184",
    unitNumber: "TRK-2026-0184",
    vin: "1XPWD49X91D487426",
    make: "Freightliner",
    model: "Cascadia",
    type: "Tractor",
    inServiceDate: "2019-03-15",
    currentStatus: "Available",
    statusChangedDate: "2025-01-10",
    daysInStatus: 3,
    mileage: 487426,
    lastServiceDate: "2025-01-10",
    nextServiceDue: "2025-04-10",
    assignedShop: "Main Garage",
    serviceChecklist: [
      { item: "Oil & Filter Change", lastCompleted: "2025-01-10", completed: true },
      { item: "Brake Inspection", lastCompleted: "2025-01-08", completed: true },
      { item: "Tire Rotation", lastCompleted: "2024-12-20", completed: true },
      { item: "Transmission Service", dueDate: "2025-04-15", completed: false },
      { item: "Fuel Filter Replacement", lastCompleted: "2024-11-30", completed: true },
      { item: "Air Filter Service", lastCompleted: "2025-01-05", completed: true },
      { item: "Suspension Inspection", dueDate: "2025-03-01", completed: false },
      { item: "Light & Wiper Check", lastCompleted: "2025-01-12", completed: true },
      { item: "Battery Load Test", dueDate: "2025-02-28", completed: false },
      { item: "Engine Coolant Level", lastCompleted: "2025-01-12", completed: true }
    ],
    technicianNotes: [
      { shop: "Main Garage", technician: "Marcus Chen", date: "2025-01-10", text: "Replaced worn brake pads, all rotors within spec. Coolant flushed. Vehicle ready for service." }
    ]
  },
  // ... 11 more vehicles with similar structure
]
```

---

### Vehicle Detail (`#/vehicle/:id`)

**Layout**: sidebar + topbar + two-column detail (left: service checklist, right: technician notes + status info + action buttons)

**Template classes**: `.sidebar`, `.topbar`, `.page-header`, `.page-title`, `.grid-2`, `.card`, `.card-title`, `.status-badge`, `.btn-primary`, `.btn-secondary`, `.modal`, `.modal-overlay`, `.form-group`, `.form-input`, `.form-textarea`

**Components**:

- **Top bar**:
  - Left: Breadcrumb "Vehicles > TRK-2026-0184" (linked back to vehicles list on click)
  - Center: Vehicle title "TRK-2026-0184 | Freightliner Cascadia" (SF Pro Display 28px, weight 600, color --fg)
  - Right: [← Back to Vehicles] button (secondary)

- **Left column (Service Checklist Card)**:
  - Card title: "Service Checklist" (SF Pro Display 19px, weight 600)
  - Checklist items (SF Pro Text 14px):
    - ☑ Oil & Filter Change (Last: 2025-01-10)
    - ☑ Brake Inspection (Last: 2025-01-08)
    - ☑ Tire Rotation (Last: 2024-12-20)
    - ☐ Transmission Service (Due: 2025-04-15)
    - ☑ Fuel Filter Replacement (Last: 2024-11-30)
    - ☑ Air Filter Service (Last: 2025-01-05)
    - ☐ Suspension Inspection (Due: 2025-03-01)
    - ☑ Light & Wiper Check (Last: 2025-01-12)
    - ☐ Battery Load Test (Due: 2025-02-28)
    - ☑ Engine Coolant Level (Last: 2025-01-12)
  - Card padding: 16px; border-radius: 12px; border: 1px solid --border

- **Right column (Status & Actions)**:
  
  - **Status Card**:
    - Title: "Vehicle Status"
    - Current status: Available badge (green, --status-available)
    - Days in status: "3 days"
    - Status history (most recent 3):
      - Available (3 days, 2025-01-10 → present)
      - Road Test (1 day, 2025-01-09 → 2025-01-10)
      - In Shop (2 days, 2025-01-07 → 2025-01-09)
    - Card padding: 16px; border-radius: 12px; border: 1px solid --border
  
  - **Technician Notes Card**:
    - Title: "Technician Notes (Main Garage)"
    - Note items (SF Pro Text 14px):
      - Technician: Marcus Chen | Date: 2025-01-10
      - Note: "Replaced worn brake pads, all rotors within spec. Coolant flushed. Vehicle ready for service."
      - [Edit] button (link-style, blue)
    - Card padding: 16px; border-radius: 12px; border: 1px solid --border
  
  - **Action Buttons** (button group, stacked vertically):
    - [Advance Status] button (primary fill, blue #0071e3, white text, 8px radius, 12px padding horizontal/8px vertical)
    - [Flag for Parts] button (secondary, border-led, --border-strong, --fg text, 8px radius)
    - [View Work Orders] button (secondary, link-style, blue)

- **Modals**:

  - **Advance Status Modal**:
    - Title: "Move Vehicle Status" (SF Pro Display 24px, weight 600)
    - Instruction text: "Select new status and add optional notes." (SF Pro Text 14px, color --muted)
    - Radio button options (SF Pro Text 17px):
      - ○ In Shop
      - ○ Awaiting Parts
      - ○ Road Test
      - ○ Out of Service
    - Text field: "Notes (optional)" (textarea, 3 rows)
    - Button group: [Confirm] (primary blue) [Cancel] (secondary)
    - On confirm: vehicle status updates globally; reflected immediately on Vehicles page and Work Orders page; modal closes; page shows updated status
  
  - **Flag for Parts Modal**:
    - Title: "Flag for Parts" (SF Pro Display 24px, weight 600)
    - Form fields (SF Pro Text 14px):
      - Part Category dropdown: ["Engine", "Transmission", "Brake", "Suspension", "Electrical", "Tires", "Other"]
      - Part Name text input: placeholder "e.g., Brake Pad Set"
      - Quantity number input: default 1
      - Estimated Unit Cost currency input: placeholder "$0.00"
      - Notes textarea: placeholder "Describe part need..."
    - Button group: [Submit] (primary blue) [Cancel] (secondary)
    - On submit: creates line item in active work order for this vehicle; updates Parts & Costs page totals; creates/updates work order status if needed; modal closes; shows success toast

**Interactions**:
  - Breadcrumb link "Vehicles" → back to `#/vehicles`
  - [← Back to Vehicles] → back to `#/vehicles`
  - [Advance Status] button → opens modal → on confirm, status changes globally, visible on Vehicles and Work Orders pages
  - [Flag for Parts] button → opens modal → on submit, creates line item in work order, updates Parts & Costs aggregation
  - [View Work Orders] → navigates to `#/work-orders` filtered to this vehicle's active work orders

---

### Work Orders (`#/work-orders`)

**Layout**: sidebar + topbar with shop selector + 5 Kanban columns (Pending, In Shop, Awaiting Parts, Road Test, Complete)

**Template classes**: `.sidebar`, `.topbar`, `.page-header`, `.page-title`, `.kanban-container`, `.kanban-column`, `.kanban-card`, `.card`, `.badge`, `.status-badge`, `.btn-primary`, `.btn-secondary`, `.modal`, `.modal-overlay`, `.form-group`, `.form-input`, `.form-textarea`

**Components**:

- **Top bar**:
  - Left: Page title "Work Orders" (SF Pro Display 32px, weight 600)
  - Center: Shop selector dropdown ("Main Garage" | "North Branch" | "Downtown Annex") — work orders visible are scoped to selected shop
  - Right: [+ New Work Order] button (primary blue)

- **Kanban container** (5 equal-width columns, horizontal scrollable if needed):

  - **Column 1: Pending** (header light gray --surface, column width 20%)
    - Header: "Pending" (SF Pro Display 17px, weight 600)
    - Cards (3 total):
      - Card: Vehicle unit TRK-2026-0187 | Type icon (Tractor) | "Scheduled: 2025-01-15" | Drag handle
      - Card: Vehicle unit BXX-2024-0920 | Type icon (Box Truck) | "Scheduled: 2025-01-16" | Drag handle
      - Card: Vehicle unit VAN-2023-0454 | Type icon (Cargo Van) | "Scheduled: 2025-01-17" | Drag handle

  - **Column 2: In Shop** (header blue --accent, column width 20%, represents active queue)
    - Header: "In Shop" (SF Pro Display 17px, weight 600, blue text)
    - Cards (4 total):
      - Card: Vehicle unit TRK-2026-0184 | Type icon (Tractor) | "Work: Oil change + brake service ($465.00)" | Drag handle | Click for details
      - Card: Vehicle unit BXX-2024-0918 | Type icon (Box Truck) | "Work: Transmission inspection ($185.00)" | Drag handle
      - Card: Vehicle unit VAN-2023-0453 | Type icon (Cargo Van) | "Work: Engine diagnostics ($240.00)" | Drag handle
      - Card: Vehicle unit TRL-2025-0334 | Type icon (Trailer) | "Work: Brake system overhaul ($780.00)" | Drag handle

  - **Column 3: Awaiting Parts** (header orange, column width 20%)
    - Header: "Awaiting Parts" (SF Pro Display 17px, weight 600)
    - Cards (2 total):
      - Card: Vehicle unit VAN-2023-0452 | Type icon (Cargo Van) | "Parts: Transmission seal (Est. arrival: 2025-01-18)" | Drag handle
      - Card: Vehicle unit BXX-2024-0919 | Type icon (Box Truck) | "Parts: Engine block (Est. arrival: 2025-01-20)" | Drag handle

  - **Column 4: Road Test** (header purple, column width 20%)
    - Header: "Road Test" (SF Pro Display 17px, weight 600)
    - Cards (1 total):
      - Card: Vehicle unit TRL-2025-0335 | Type icon (Trailer) | "Test: Post-service validation" | Drag handle

  - **Column 5: Complete** (header green, column width 20%, shows recent completions with faded style)
    - Header: "Complete" (SF Pro Display 17px, weight 600)
    - Cards (8 total, scrollable):
      - Card: Vehicle unit TRK-2026-0188 | Type icon (Tractor) | "Completed: 2025-01-12" | opacity 0.7
      - Card: Vehicle unit BXX-2024-0921 | Type icon (Box Truck) | "Completed: 2025-01-11" | opacity 0.7
      - ... 6 more completed work orders

- **Card styling**:
  - Each card: 12px border-radius, 1px border --border, 12px padding, cursor: grab on hover, white background
  - Hover state: slight shadow (rgba(0,0,0,0.08))
  - Drag state: cursor: grabbing, scale: 0.98

- **Kanban column styling**:
  - Column background: very light gray (--surface)
  - Column padding: 12px
  - Border-radius: 8px
  - Min-height: 600px

- **Interactions**:
  - Shop selector changes displayed work orders scope (other shops' orders hidden)
  - Drag card between columns → vehicle status updates (column defines new status), reflected on Vehicles page immediately
  - Click on card → modal opens with work order details (line items, costs, notes, estimated completion)
  - [+ New Work Order] → modal form to select vehicle from dropdown and initial status; creates WO

- **Modals**:

  - **Work Order Details Modal**:
    - Title: "Work Order [WO-001]" (SF Pro Display 24px, weight 600)
    - Vehicle info: "TRK-2026-0184 | Freightliner Cascadia"
    - Status badge + date created + estimated completion
    - **Line Items Table**:
      - Columns: Description | Qty | Unit Cost | Total
      - Rows (3):
        | Oil & Filter Change | 1 | $45.00 | $45.00 |
        | Brake Pad Set | 1 | $120.00 | $120.00 |
        | Labor (4 hrs @ $75/hr) | 4 | $75.00 | $300.00 |
      - Total: $465.00
    - Notes field (read-only or editable)
    - Buttons: [Edit] [Delete] [Close]
  
  - **New Work Order Modal**:
    - Title: "Create Work Order"
    - Vehicle dropdown (populated from vehicles list)
    - Initial Status radio buttons: Pending, In Shop, Awaiting Parts, Road Test
    - Estimated Completion date picker
    - Notes textarea
    - Buttons: [Create] [Cancel]

**Data Model**:
```
workOrders: [
  {
    id: "WO-001",
    vehicleId: "TRK-2026-0184",
    vehicleUnit: "TRK-2026-0184",
    shop: "Main Garage",
    status: "In Shop",
    createdDate: "2025-01-10",
    estimatedCompletion: "2025-01-14",
    lineItems: [
      { id: "LI-001", description: "Oil & Filter Change", quantity: 1, unitCost: 45.00, cost: 45.00 },
      { id: "LI-002", description: "Brake Pad Set", quantity: 1, unitCost: 120.00, cost: 120.00 },
      { id: "LI-003", description: "Labor (4 hours @ $75/hr)", quantity: 4, unitCost: 75.00, cost: 300.00 }
    ],
    totalCost: 465.00,
    notes: "Replaced worn brake pads, all rotors within spec."
  },
  // ... more work orders (15 total across all shops and statuses)
]
```

---

### Inspections (`#/inspections`)

**Layout**: sidebar + topbar + filter bar + dense inspection table

**Template classes**: `.sidebar`, `.topbar`, `.page-header`, `.page-title`, `.filter-bar`, `.filter-chip`, `.table`, `.table-row`, `.badge`, `.status-badge`, `.btn-primary`, `.btn-secondary`, `.modal`, `.modal-overlay`, `.form-group`, `.form-select`, `.form-textarea`

**Components**:

- **Top bar**:
  - Left: Page title "Inspections" (SF Pro Display 32px, weight 600)
  - Right: [+ Schedule Inspection] button (primary blue)

- **Filter bar** (below topbar, sticky):
  - Status filter chips (multi-select): "All" | "Scheduled" | "In Progress" | "Completed"
  - Inspection type filter chips: "All" | "Safety" | "Emissions" | "Routine" | "Annual"
  - Date range selector: "This Week" | "This Month" | "Custom date range"

- **Inspections table** (15 rows, dense format):
  - Columns: Unit Number | Vehicle Type | Inspection Type | Scheduled Date | Status | Inspector | Findings | [Actions]
  - Data rows:
    | TRK-2026-0184 | Tractor | Routine | 2025-02-01 | Scheduled | [Unassigned] | — | [Assign] [View] |
    | BXX-2024-0917 | Box Truck | Safety | 2025-01-16 | In Progress | Sarah Martinez | — | [View] [Mark Complete] |
    | VAN-2023-0451 | Cargo Van | Emissions | 2025-01-14 | Completed | James Park | Pass ✓ | [View] |
    | TRL-2025-0334 | Trailer | Routine | 2025-02-15 | Scheduled | [Unassigned] | — | [Assign] [View] |
    | TRK-2026-0185 | Tractor | Annual | 2025-03-01 | Scheduled | Marcus Chen | — | [View] [Mark In Progress] |
    | BXX-2024-0918 | Box Truck | Safety | 2025-01-13 | Completed | Marcus Chen | Pass ✓ | [View] |
    | VAN-2023-0452 | Cargo Van | Routine | 2025-02-05 | Scheduled | [Unassigned] | — | [Assign] [View] |
    | TRL-2025-0335 | Trailer | Emissions | 2025-01-18 | In Progress | David Lee | — | [View] [Mark Complete] |
    | TRK-2026-0186 | Tractor | Safety | 2025-02-08 | Scheduled | [Unassigned] | — | [Assign] [View] |
    | BXX-2024-0919 | Box Truck | Routine | 2025-02-10 | Scheduled | Sarah Martinez | — | [View] |
    | VAN-2023-0453 | Cargo Van | Annual | 2025-03-15 | Scheduled | [Unassigned] | — | [Assign] [View] |
    | TRL-2025-0336 | Trailer | Routine | 2025-02-12 | Scheduled | [Unassigned] | — | [Assign] [View] |
    | TRK-2026-0187 | Tractor | Emissions | 2025-01-17 | Completed | James Park | Pass ✓ | [View] |
    | BXX-2024-0920 | Box Truck | Safety | 2025-01-19 | In Progress | Marcus Chen | — | [View] [Mark Complete] |
    | VAN-2023-0454 | Cargo Van | Routine | 2025-02-20 | Scheduled | [Unassigned] | — | [Assign] [View] |
  
  - Status badges: Scheduled=gray --muted, In Progress=blue --status-in-shop, Completed=green --status-complete
  - Row height: compact (8px base unit), 32px total with padding

- **Interactions**:
  - Filter chips toggle inspection visibility (multi-select within each filter group)
  - [Assign] button → modal to select inspector from dropdown (Marcus Chen, Sarah Martinez, James Park, David Lee, etc.)
  - [View] button → modal showing inspection details, findings, pass/fail result
  - [Mark Complete] button → inline action to mark inspection complete, opens findings modal
  - [Mark In Progress] button → inline action to change status
  - [+ Schedule Inspection] → modal form to select vehicle, inspection type, and date

- **Modals**:

  - **Assign Inspector Modal**:
    - Title: "Assign Inspector"
    - Vehicle: TRK-2026-0184 (read-only)
    - Inspector dropdown: [Marcus Chen, Sarah Martinez, James Park, David Lee, Elena Rodriguez, Robert Brown]
    - Buttons: [Assign] [Cancel]
  
  - **Inspection Details Modal**:
    - Title: "Inspection Details - TRK-2026-0184"
    - Type: Routine
    - Scheduled Date: 2025-02-01
    - Status: Scheduled (or In Progress / Completed)
    - Inspector: [Unassigned] or name
    - Findings (if completed):
      - "Engine runs smoothly"
      - "Brake response time within spec"
      - "No fluid leaks detected"
      - Result: Pass / Fail
    - Buttons: [Edit] [Delete] [Close]
  
  - **Schedule Inspection Modal**:
    - Title: "Schedule Inspection"
    - Vehicle dropdown (populated from vehicles list)
    - Inspection type radio buttons: Safety, Emissions, Routine, Annual
    - Scheduled date picker
    - Assigned Inspector dropdown (optional)
    - Notes textarea (optional)
    - Buttons: [Schedule] [Cancel]

**Data Model**:
```
inspections: [
  {
    id: "INS-001",
    vehicleId: "TRK-2026-0184",
    vehicleUnit: "TRK-2026-0184",
    type: "Routine",
    scheduledDate: "2025-02-01",
    status: "Scheduled",
    assignedInspector: null,
    findings: null,
    result: null,
    completedDate: null
  },
  // ... 14 more inspections
]
```

---

### Parts & Costs (`#/parts-costs`)

**Layout**: sidebar + topbar with date range + 4 KPI cards + dense parts cost aggregation table

**Template classes**: `.sidebar`, `.topbar`, `.page-header`, `.page-title`, `.kpi-card`, `.grid-4`, `.table`, `.table-row`, `.btn-secondary`, `.btn-destructive`

**Components**:

- **Top bar**:
  - Left: Page title "Parts & Costs" (SF Pro Display 32px, weight 600)
  - Right: Date range selector ("This Month" | "Last Month" | "Last 3 Months" | "Custom"), [Export CSV] button (secondary)

- **KPI Cards** (4 cards in a responsive grid, 16px padding each):

  - **Card 1: Total Parts Cost (This Month)**
    - Label: "Total Parts Cost" (SF Pro Text 14px, weight 400, color --muted)
    - Big number: "$12,847.50" (SF Pro Display 32px, weight 600, color --fg)
    - Delta: "+$847.50 vs. last month" (SF Pro Text 12px, color green #34C759)
    - Card: 12px radius, border 1px --border, --surface background

  - **Card 2: Work Order Count (This Month)**
    - Label: "Work Order Count"
    - Big number: "24"
    - Delta: "+4 vs. last month" (green)
    - Card styling same as above

  - **Card 3: Avg Cost per Order**
    - Label: "Avg Cost per Order"
    - Big number: "$535.31"
    - Delta: "+$12 vs. last month" (green)

  - **Card 4: Open/Pending Parts**
    - Label: "Open/Pending Parts"
    - Big number: "7"
    - Delta: "+2 vs. last week" (orange, indicating increase)

- **Parts Cost Breakdown Table** (18 rows, dense format):
  - Columns: Part Name | Category | Vendor | Unit Cost | Qty | Total Cost | Used in Work Orders | [View]
  - Data rows (aggregated from all work order line items):
    | Brake Pad Set | Brake | Autopart Supply | $120.00 | 8 | $960.00 | WO-001, WO-005, WO-012, WO-018, WO-021, WO-024, WO-027, WO-031 | [View] |
    | Transmission Seal | Transmission | Industrial Parts Co | $285.00 | 2 | $570.00 | WO-003, WO-009 | [View] |
    | Oil (Diesel, 5qt) | Engine | Quaker State | $18.50 | 32 | $592.00 | WO-001, WO-004, WO-007, WO-010, WO-013, WO-016, WO-019, WO-022, ... | [View] |
    | Tire (11R24.5) | Tires | Goodyear | $475.00 | 4 | $1,900.00 | WO-002, WO-006, WO-014, WO-028 | [View] |
    | Air Filter | Engine | Baldwin | $42.00 | 6 | $252.00 | WO-001, WO-007, WO-010, WO-013, WO-019, WO-025 | [View] |
    | Fuel Filter | Engine | FLEETGUARD | $28.50 | 5 | $142.50 | WO-004, WO-008, WO-015, WO-020, WO-026 | [View] |
    | Coolant (50/50, gal) | Engine | Prestone | $22.00 | 12 | $264.00 | WO-001, WO-005, WO-011, WO-017, WO-023, WO-029, WO-030, ... | [View] |
    | Brake Fluid (DOT 4, qt) | Brake | ATE | $15.00 | 20 | $300.00 | WO-002, WO-006, WO-009, WO-012, WO-018, WO-024, WO-027, WO-032, ... | [View] |
    | Wiper Blades (pair) | Body | Bosch | $35.00 | 14 | $490.00 | WO-001, WO-003, WO-005, WO-007, WO-009, WO-011, WO-013, WO-015, ... | [View] |
    | Spark Plugs (set of 8) | Engine | NGK | $48.00 | 3 | $144.00 | WO-004, WO-008, WO-016 | [View] |
    | Battery (Heavy Duty) | Electrical | Optima | $285.00 | 2 | $570.00 | WO-010, WO-025 | [View] |
    | Radiator Cap | Engine | Stant | $18.00 | 4 | $72.00 | WO-007, WO-014, WO-021, WO-032 | [View] |
    | Water Pump | Engine | Atsco | $195.00 | 1 | $195.00 | WO-019 | [View] |
    | Alternator | Electrical | Remy | $425.00 | 1 | $425.00 | WO-022 | [View] |
    | Serpentine Belt | Engine | Gates | $68.00 | 2 | $136.00 | WO-011, WO-023 | [View] |
    | Hose Kit (assorted) | Engine | Dayco | $85.00 | 3 | $255.00 | WO-005, WO-015, WO-030 | [View] |
    | Thermostat | Engine | Stant | $32.00 | 2 | $64.00 | WO-009, WO-020 | [View] |
    | Grease (cartridge) | Maintenance | NLGI-2 | $12.50 | 8 | $100.00 | WO-002, WO-006, WO-012, WO-018, WO-024, WO-027, WO-031, WO-033 | [View] |
  - Table totals row: TOTAL | — | — | — | 152 | $12,847.50 | — | — |
  - Row height: 32px (compact)

- **Interactions**:
  - Date range selector updates all KPI cards and table data retroactively
  - [View] links in "Used in Work Orders" → navigates to `#/work-orders` page, highlighting or filtering to those specific work orders
  - [Export CSV] downloads a CSV file with part names, categories, costs, and aggregation data
  - Table is sortable by clicking column headers (Part Name, Total Cost, Qty, etc.)

**Data Model**:
```
parts: [
  {
    id: "PT-001",
    name: "Brake Pad Set",
    category: "Brake",
    vendor: "Autopart Supply",
    unitCost: 120.00,
    totalQuantity: 8,
    totalCost: 960.00,
    lineItems: ["LI-001", "LI-005", "LI-012", ...],
    workOrders: ["WO-001", "WO-005", "WO-012", ...]
  },
  // ... 17 more parts with aggregated costs and usage tracking
]
```

---

### Settings (`#/settings`)

**Layout**: sidebar + topbar + three-column form panels (Shop Config | User Preferences | System Settings) with danger zone at bottom

**Template classes**: `.sidebar`, `.topbar`, `.page-header`, `.page-title`, `.grid-3`, `.form-group`, `.form-input`, `.form-select`, `.form-textarea`, `.btn-primary`, `.btn-secondary`, `.btn-destructive`, `.card`

**Components**:

- **Top bar**:
  - Left: Page title "Settings" (SF Pro Display 32px, weight 600)
  - Right: [Save All] button (primary blue, disabled until form changes detected)

- **Three-column form panel layout** (responsive to 1 column on smaller screens):

  - **Column 1: Shop Configuration** (.card, 12px radius, 1px border --border, 16px padding):
    - Section title: "Shop Configuration" (SF Pro Display 19px, weight 600)
    - Form group:
      - Label: "Shop Name" (SF Pro Text 14px, weight 600)
      - Input: text field, value "Main Garage"
    - Form group:
      - Label: "Location"
      - Input: text field, value "123 Fleet Ave, City, State"
    - Form group:
      - Label: "Phone"
      - Input: tel field, value "(555) 123-4567"
    - Form group:
      - Label: "Hours of Operation"
      - Input: time range (From: 06:00, To: 18:00)
    - Form group:
      - Label: "Shop Manager"
      - Select dropdown: [Marcus Chen, Sarah Martinez, James Park, David Lee, Elena Rodriguez]
    - [Save] button (primary blue, 8px radius, 12px padding)

  - **Column 2: User Preferences** (.card, styling same):
    - Section title: "User Preferences"
    - Form group:
      - Label: "Display Name"
      - Input: text field, value "Marcus Chen"
    - Form group:
      - Label: "Email"
      - Input: email field, value "marcus@northwindlogistics.com"
    - Form group:
      - Label: "Role"
      - Select dropdown: [Technician, Shop Manager, Coordinator, Admin]
    - Form group:
      - Label: "Assigned Shop"
      - Select dropdown: [Main Garage, North Branch, Downtown Annex]
    - Form group:
      - Label: "Theme"
      - Radio buttons: Light (selected) | Dark
    - Form group:
      - Label: "Notifications"
      - Checkboxes:
        - ☑ Email on work order completion
        - ☑ Daily summary report
        - ☐ Low stock alerts
    - [Save] button

  - **Column 3: System Settings** (.card, styling same):
    - Section title: "System Settings"
    - Form group:
      - Label: "Maintenance Interval (hours)"
      - Input: number field, value "500", min 100, max 2000
    - Form group:
      - Label: "Inspection Frequency (days)"
      - Input: number field, value "90", min 30, max 365
    - Form group:
      - Label: "Work Order Auto-Archive (days)"
      - Input: number field, value "30", min 7, max 365
    - Form group:
      - Label: "Low Stock Alert Threshold"
      - Input: number field, value "5", min 1, max 100
    - Form group:
      - Label: "Default Hourly Labor Rate"
      - Input: currency field, value "$75.00"
    - [Save] button

- **Danger Zone** (bottom, full-width card, red/destructive styling, border-top: 2px solid #FF3B30):
  - Title: "Danger Zone" (SF Pro Display 17px, weight 600, color #FF3B30)
  - [Clear All Data] button (destructive red, requires confirmation modal)
  - [Export Fleet Data] button (secondary, downloads JSON backup)
  - Confirmation modal on [Clear All Data]: "Are you sure? This cannot be undone." with [Clear] and [Cancel]

- **Interactions**:
  - Form fields update in real-time (controlled inputs)
  - [Save] button for each column persists that column's settings
  - Changes are validated (email format, positive numbers, etc.)
  - On successful save: green toast notification "Settings saved"
  - On error: red toast notification with error message
  - [Save All] saves all three columns if any changes detected
  - [Export Fleet Data] downloads JSON file with all vehicles, work orders, parts, inspections, settings
  - [Clear All Data] → modal confirmation → on confirm, resets all data to defaults (for testing)

**Data Model**:
```
settings: {
  shop: {
    name: "Main Garage",
    location: "123 Fleet Ave, City, State",
    phone: "(555) 123-4567",
    hoursOpen: "06:00",
    hoursClose: "18:00",
    manager: "Marcus Chen"
  },
  user: {
    displayName: "Marcus Chen",
    email: "marcus@northwindlogistics.com",
    role: "Shop Manager",
    assignedShop: "Main Garage",
    theme: "Light",
    notifications: {
      workOrderCompletion: true,
      dailySummary: true,
      lowStockAlerts: false
    }
  },
  system: {
    maintenanceInterval: 500,
    inspectionFrequency: 90,
    workOrderAutoArchiveDays: 30,
    lowStockThreshold: 5,
    defaultHourlyRate: 75.00
  }
}
```

---

## State & Data Model

**Global Application State**:
```
{
  vehicles: Vehicle[],
  workOrders: WorkOrder[],
  inspections: Inspection[],
  parts: Part[],
  settings: Settings,
  currentShop: string ("Main Garage" | "North Branch" | "Downtown Annex"),
  currentUser: User,
  currentPage: string (route hash),
  uiState: {
    selectedVehicleId: string | null,
    selectedWorkOrderId: string | null,
    modalOpen: boolean,
    modalType: string,
    filterVehicleType: string[],
    filterVehicleStatus: string,
    filterInspectionStatus: string,
    searchQuery: string
  }
}

type Vehicle = {
  id: string (unit number, e.g., "TRK-2026-0184")
  unitNumber: string
  vin: string (VIN-style, e.g., "1XPWD49X91D487426")
  make: string
  model: string
  type: "Tractor" | "Box Truck" | "Cargo Van" | "Trailer"
  inServiceDate: ISO date string
  currentStatus: "Available" | "In Shop" | "Awaiting Parts" | "Road Test" | "Out of Service"
  statusChangedDate: ISO date string
  daysInStatus: number (calculated)
  mileage: number
  lastServiceDate: ISO date string
  nextServiceDue: ISO date string
  assignedShop: string
  serviceChecklist: ServiceItem[]
  technicianNotes: TechnicianNote[]
}

type ServiceItem = {
  item: string
  lastCompleted: ISO date string | null
  completed: boolean
  dueDate: ISO date string | null
}

type TechnicianNote = {
  shop: string
  technician: string
  date: ISO date string
  text: string
}

type WorkOrder = {
  id: string (e.g., "WO-001")
  vehicleId: string
  vehicleUnit: string
  shop: string
  status: "Pending" | "In Shop" | "Awaiting Parts" | "Road Test" | "Complete"
  createdDate: ISO date string
  estimatedCompletion: ISO date string
  lineItems: LineItem[]
  totalCost: number (sum of line items)
  notes: string
}

type LineItem = {
  id: string (e.g., "LI-001")
  description: string
  quantity: number
  unitCost: number
  cost: number (quantity * unitCost)
}

type Inspection = {
  id: string (e.g., "INS-001")
  vehicleId: string
  vehicleUnit: string
  type: "Routine" | "Safety" | "Emissions" | "Annual"
  scheduledDate: ISO date string
  status: "Scheduled" | "In Progress" | "Completed"
  assignedInspector: string | null
  findings: string[] | null
  result: "Pass" | "Fail" | null
  completedDate: ISO date string | null
}

type Part = {
  id: string
  name: string
  category: string
  vendor: string
  unitCost: number
  totalQuantity: number
  totalCost: number
  lineItems: string[] (references to LineItem IDs)
  workOrders: string[] (references to WorkOrder IDs)
}

type Settings = {
  shop: ShopConfig
  user: UserPreferences
  system: SystemConfig
}

type ShopConfig = {
  name: string
  location: string
  phone: string
  hoursOpen: string
  hoursClose: string
  manager: string
}

type UserPreferences = {
  displayName: string
  email: string
  role: "Technician" | "Shop Manager" | "Coordinator" | "Admin"
  assignedShop: string
  theme: "Light" | "Dark"
  notifications: {
    workOrderCompletion: boolean
    dailySummary: boolean
    lowStockAlerts: boolean
  }
}

type SystemConfig = {
  maintenanceInterval: number
  inspectionFrequency: number
  workOrderAutoArchiveDays: number
  lowStockThreshold: number
  defaultHourlyRate: number
}
```

---

## Navigation Flows

**Navigation Map**:
1. **Vehicles page** (`#/vehicles`) → [View] button on any vehicle row → **Vehicle Detail** (`#/vehicle/:id`)
2. **Vehicle Detail** (`#/vehicle/:id`) → [Advance Status] button → modal → on confirm, vehicle status updates globally, immediately visible on Vehicles and Work Orders pages
3. **Vehicle Detail** → [Flag for Parts] button → modal → on submit, creates/updates line item in active work order, updates Parts & Costs totals
4. **Vehicle Detail** → [View Work Orders] link → **Work Orders** (`#/work-orders`) filtered to this vehicle
5. **Vehicle Detail** → breadcrumb "Vehicles" or [← Back to Vehicles] → back to **Vehicles** page
6. **Work Orders** (`#/work-orders`) → drag vehicle card between Kanban columns → vehicle status transitions, reflected on Vehicles page immediately
7. **Work Orders** → click vehicle card → modal with work order details, line items, costs
8. **Work Orders** → [+ New Work Order] → modal form to create new work order
9. **Work Orders** → shop selector dropdown → filters displayed work orders to selected shop
10. **Inspections** (`#/inspections`) → [Assign] button → modal to assign inspector
11. **Inspections** → [View] button → modal with inspection details and findings
12. **Inspections** → [+ Schedule Inspection] → modal form to schedule new inspection
13. **Parts & Costs** (`#/parts-costs`) → [View] link in work orders column → navigates to **Work Orders** page, filtered to those work orders
14. **Settings** (`#/settings`) → [Save] buttons persist settings globally
15. **Sidebar navigation** → click any nav item (Vehicles, Work Orders, Inspections, Parts & Costs, Settings) → navigate to that page

**Persistent Global State Cascades**:
- Vehicle status advance in Vehicle Detail immediately updates Vehicles table and Work Orders Kanban
- Drag-drop status transitions in Work Orders Kanban immediately update vehicle status on Vehicles page
- Work order line items added in Vehicle Detail immediately aggregate to Parts & Costs page totals
- Shop selector on Work Orders filters all subsequent work order views; persists across page navigation
- Settings changes persist globally across all pages

---

## Design Notes

- **Color scheme (Apple DS tokens → CSS :root variables)**:
  - `--bg`: #ffffff (Pure White Canvas, main content background)
  - `--fg`: #1d1d1f (Near-Black Ink, primary text on light surfaces)
  - `--accent`: #0071e3 (Apple Action Blue, primary actions, status in-shop, active nav items)
  - `--surface`: #f5f5f7 (Pale Apple Gray, secondary surfaces, filter sections, cards)
  - `--border`: #d2d2d7 (Soft Border Gray, subtle dividers, card borders)
  - `--border-strong`: #86868b (Mid Border Gray, input field borders, stronger outlines)
  - `--muted`: #6e6e73 (Secondary Neutral Gray, secondary text, helper labels)
  - `--status-available`: #34C759 (green, vehicle available, inspection complete)
  - `--status-in-shop`: #0071e3 (blue, work in progress, active Kanban column)
  - `--status-awaiting`: #FF9500 (orange, awaiting parts, alert state)
  - `--status-test`: #9933FF (purple, road test, secondary queue)
  - `--status-out`: #FF3B30 (red, out of service, critical state)

- **Typography** (Apple DS):
  - Display: `SF Pro Display`, weight 600, sizes 32px (page titles), 28px (card titles), 24px (section heads), 19px (subheads)
  - Body: `SF Pro Text`, weight 400, sizes 17px (standard body), 14px (compact labels, form fields), 12px (secondary metadata)
  - Line-height: 1.4-1.5 for body, 1.2 for display headings
  - Letter-spacing: tight for display, normal for body

- **Spacing & Density** (Apple DS):
  - Base unit: 8px
  - Sidebar width: 220px
  - Top bar height: 64px
  - Card padding: 12-16px
  - Section spacing: 16-24px
  - Table row height: 32px (compact)
  - Form field margin-bottom: 12px

- **Component Styling**:
  - Buttons: 8px border-radius, 12px horizontal padding, 8px vertical padding, SF Pro Text 14px weight 600
  - Primary buttons: background --accent (#0071e3), color white, cursor pointer
  - Secondary buttons: border 1px --border-strong, color --fg, background transparent
  - Destructive buttons: background #FF3B30, color white
  - Cards: 12px border-radius, 1px border --border, 16px padding, background --surface or white
  - Form inputs: 8px border-radius, 1px border --border-strong, 12px padding, background white
  - Modals: 16px border-radius, white background, semi-transparent overlay (rgba(0,0,0,0.4))
  - Status badges: 4px border-radius (pill), 6px horizontal padding, 3px vertical padding, white text on colored background

- **Responsive behavior**:
  - Desktop (1024px+): full three-column Settings layout, full Vehicles table visible, Kanban columns side-by-side
  - Tablet (641px-1023px): Settings panels stack to 2 columns, Vehicles table may scroll horizontally, Kanban columns scroll horizontally
  - Mobile (375px-640px): Settings panels stack to 1 column, Vehicles table scrolls horizontally with sticky left column, Kanban becomes vertical scroll

- **Interaction feedback**:
  - Hover states: buttons scale 0.98, cards show subtle shadow
  - Active states: sidebar nav item has background --accent and white text
  - Focus states: blue outline (#0071e3) on keyboard focus for accessibility
  - Loading states: spinner overlay on modal/form submit
  - Success/error toasts: positioned bottom-right, auto-dismiss after 4 seconds

- **Data consistency**:
  - Vehicle status changes sync across all pages in real-time (simulated via state updates)
  - Work order line items immediately aggregate to Parts & Costs totals
  - Technician notes and service checklist persist within vehicle detail
  - Inspection assignments and findings persist and update status
  - All form submissions validate input before persisting

</spec>
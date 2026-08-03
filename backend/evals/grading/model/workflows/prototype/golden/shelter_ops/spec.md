<spec>
# Prototype Specification: Harborview Animal Shelter — Intake & Adoption Console

## Template & Design System
- **Template**: None (blank-canvas mode) — custom sidebar-app layout invented below; plain, functional, admin-console style.
- **Design System**: "Harborview Console" — calm municipal palette: deep teal accent on near-white background, high-contrast slate text, compact-but-readable density, system font stack.
- **CSS Class System**:
  - Chrome: `.app` (grid: 220px sidebar + fluid main), `.sidebar`, `.sidebar-logo`, `.nav-link`, `.nav-link.active`, `.main`, `.page-header`, `.page-title`, `.page-sub`
  - Layout: `.grid-2`, `.grid-3`, `.grid-4` (responsive CSS grid, gap 16px), `.stack` (vertical flex, gap 12px), `.row` (horizontal flex, gap 8px, wrap)
  - Surfaces: `.card` (surface bg, 1px border, 8px radius, 16px padding), `.card-title` (13px uppercase muted label), `.kpi-value` (28px bold), `.kpi-note` (12px muted)
  - Tables: `.table-wrap` (overflow-x auto), `.table` (full-width, 1px row borders, 8px cell padding, left-aligned th in muted 12px uppercase), `.table tr.clickable:hover` (surface-hover bg, pointer cursor)
  - Filters: `.filter-bar` (flex row, gap 8px, wrap), `.chip` (pill button, border, surface bg), `.chip.active` (accent bg, white text), `.search-input` (bordered input, 8px padding, 240px wide)
  - Badges: `.badge` (pill, 12px, padded 2px 10px) with variants `.badge-available` (green tint), `.badge-hold` (amber tint), `.badge-adopted` (blue tint), `.badge-pending` (amber tint), `.badge-approved` (green tint), `.badge-denied` (red tint), `.badge-medical` (red tint)
  - Forms: `.form-group` (label + control stack, gap 4px), `.form-label` (13px, 600 weight), `.form-input`, `.form-select`, `.form-textarea` (bordered, 8px padding, full width), `.form-error` (red 12px inline message), `.form-hint` (muted 12px)
  - Buttons: `.btn` (bordered, surface), `.btn-primary` (accent bg, white), `.btn-success` (green bg, white), `.btn-danger` (red bg, white), `.btn-link` (accent text, no border)
  - Misc: `.timeline` (left-border list), `.timeline-item` (dot marker, date + text), `.notfound-card` (centered card with large icon, message, back button), `.empty-row` (muted centered td), `.alert-success` (green tint inline confirmation box), `.attention-item` (row with badge + link)
- **Color Tokens**: --bg=#f6f8f9, --fg=#1e2a32, --accent=#0f766e, --surface=#ffffff, --border=#d8e0e4, --muted=#64748b; extras: --green=#15803d, --amber=#b45309, --red=#b91c1c, --blue=#1d4ed8, tinted badge backgrounds at ~12% opacity of each.

## Overview
- **Product**: Intake-and-adoption console for Harborview Animal Shelter, a 40-kennel municipal shelter.
- **Target audience**: Shelter staff — intake officers, adoption coordinators, kennel techs.
- **Core purpose**: Track animals in care, process new intakes, and move adoption applications through approval — with kennel occupancy always accurate.
- **Total pages**: 7 (Dashboard, Animals, Animal Detail, New Intake, Applications, Application Detail, Settings)

## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| dashboard | `#/dashboard` | KPI overview + attention list | kpi-row + attention list card | Yes (default) |
| animals | `#/animals` | Filterable/searchable roster | filter-bar + data table | No |
| animal-detail | `#/animal/:id` | One animal's full record | two-column detail + timeline | No |
| new-intake | `#/intake` | Add an animal to the store | single-card form | No |
| applications | `#/applications` | Adoption application queue | filter-bar + data table | No |
| application-detail | `#/application/:id` | Review + approve/deny one application | two-column detail + action bar | No |
| settings | `#/settings` | Shelter preferences | single-card form | No |

Sidebar nav (always visible): Dashboard, Animals, New Intake, Applications, Settings. Dynamic routes are reached via row/link clicks; active nav link gets `.nav-link.active` (Animal Detail highlights Animals; Application Detail highlights Applications).

## Page Specifications

### Dashboard (`#/dashboard`)
**Layout**: page-header + `.grid-4` KPI row + `.grid-2` (attention list card, kennel snapshot card)
**Template classes**: `.page-header .grid-4 .card .kpi-value .kpi-note .grid-2 .attention-item .badge .btn-link`
**Components**:
  - KPI tile "Animals in Care": count of animals with status ≠ Adopted — computed live from the store (seed: 8).
  - KPI tile "Available for Adoption": count where status = Available (seed: 5).
  - KPI tile "Pending Applications": count of applications with status = Pending (seed: 3).
  - KPI tile "Kennels Free": `settings.totalKennels (40) − animals currently assigned a kennel` (Adopted animals have kennel = null; seed: 32 free). Note under value: "of 40 total".
  - "Needs Attention" card, list of 4 computed items, each an `.attention-item` linking into a detail page:
    - Biscuit (a3) — badge "Medical hold" → `#/animal/a3`
    - Application APP-104 (Priya Raman → Luna) — badge "Pending 6 days" → `#/application/104`
    - Pepper (a6) — badge "Hold expires Aug 2" → `#/animal/a6`
    - Application APP-106 (Dana Okafor → Milo) — badge "Pending" → `#/application/106`
  - "Kennel Snapshot" card: small list of occupied kennels with animal names (K-04 Luna, K-07 Rocky, K-09 Biscuit, K-12 Milo, K-15 Clementine, K-18 Pepper, K-21 Ziggy, K-23 Maple) — rendered from the store, each name links to its animal detail.
**Interactions**:
  - KPI tile "Animals in Care" → navigates to `#/animals`
  - KPI tile "Pending Applications" → navigates to `#/applications`
  - Each attention item / kennel snapshot name → navigates to the linked `#/animal/:id` or `#/application/:id`
  - All KPI values recompute on every render — after an approval or intake elsewhere, revisiting the Dashboard shows updated numbers.

### Animals (`#/animals`)
**Layout**: page-header (+ "New Intake" button) + `.filter-bar` + `.table-wrap` table
**Template classes**: `.page-header .btn-primary .filter-bar .chip .chip.active .search-input .table-wrap .table .badge .empty-row`
**Components**:
  - Species filter chips: All (default active) / Dogs / Cats / Small mammals.
  - Status filter chips: All (default active) / Available / Hold / Adopted.
  - Name search `.search-input`, placeholder "Search by name…", case-insensitive substring match on animal name, filters as you type.
  - All three filters compose with AND logic; state held in JS variables, table re-rendered on any change.
  - Animals table: columns [Name, Species, Breed, Age, Status, Kennel, Intake Date]; rows rendered from the store (8 seed rows, see data model). Status rendered as `.badge-available/-hold/-adopted`; kennel shows code (e.g. K-04) or "—" for adopted animals.
  - Empty state: when the filter combination matches nothing (e.g. Small mammals + Adopted), a single `.empty-row` td spanning all columns: "No animals match the current filters."
**Interactions**:
  - Any species/status chip → sets that filter, moves `.active`, re-renders table
  - Search input `input` event → re-renders table
  - Any table row click → navigates to `#/animal/{id}` for that row's animal
  - "New Intake" button → navigates to `#/intake`

### Animal Detail (`#/animal/:id`)
**Layout**: page-header (name + status badge) + `.grid-2` (profile card, kennel card) + timeline card
**Template classes**: `.page-header .badge .grid-2 .card .card-title .timeline .timeline-item .btn .notfound-card`
**Components**:
  - Renders the animal whose id is in the hash — looked up from the store on every route render, never hardcoded. After Approve elsewhere, revisiting shows status Adopted and kennel "—".
  - Profile card: Species, Breed, Sex, Age, Weight, Intake date, Microchip #, Notes.
  - Kennel card: assigned kennel code (e.g. "K-09") with line "Kennel block B, row 2"; if kennel is null (adopted): "No kennel — adopted" plus adoption note.
  - Timeline card "Intake & Medical History": rendered from the animal's `timeline` array (each animal has 3–5 entries), e.g. for Biscuit: 2026-07-12 "Stray intake — found near Harborview Pier", 2026-07-13 "Vet exam: underweight, dental disease", 2026-07-15 "Started antibiotics course", 2026-07-20 "Placed on medical hold". Entries added by Approve ("Adopted by {applicant}") appear here.
  - Not-found: unknown id (e.g. `#/animal/a99`) renders a `.notfound-card`: paw icon, "Animal not found", "No animal with id 'a99' exists in the roster.", button "Back to Animals" → `#/animals`. No crash, no console error.
**Interactions**:
  - "← Back to Animals" link → `#/animals`
  - Route change re-reads id from hash and re-renders

### New Intake (`#/intake`)
**Layout**: page-header + single centered `.card` form (max-width 560px)
**Template classes**: `.card .form-group .form-label .form-input .form-select .form-textarea .form-error .btn-primary .btn`
**Components**:
  - Fields: Name (text, required), Species (select: Dog / Cat / Small mammal, default Dog), Breed (text, e.g. "Terrier mix"), Age (text, e.g. "2 yr"), Sex (select: Male / Female), Kennel (select populated with free kennel codes computed from the store — K-01..K-40 minus occupied; defaults to first free), Intake notes (textarea).
  - Buttons: "Add Animal" (`.btn-primary`, submit) and "Cancel" (`.btn`, → `#/animals`).
**Interactions**:
  - Submit with empty/whitespace Name → inline `.form-error` under the Name field: "Name is required." Field gets a red border; no navigation, nothing added. Error clears on next input.
  - Valid submit → creates animal with next sequential id (`a{max+1}`, e.g. a9), status "Available", today's intake date (2026-07-30), chosen kennel, and a timeline seeded with one entry: "{date} — Intake: {notes or 'New intake processed'}"; pushes it into the store, then navigates to `#/animal/a9` where the new record renders fully. Dashboard KPIs and Animals roster reflect it immediately.

### Applications (`#/applications`)
**Layout**: page-header + `.filter-bar` + `.table-wrap` table
**Template classes**: `.filter-bar .chip .table-wrap .table .badge .empty-row`
**Components**:
  - Status filter chips: All (default) / Pending / Approved / Denied.
  - Applications table: columns [App #, Applicant, Animal, Submitted, Status]; 5 seed rows from the store (see data model). Animal cell shows the animal's name looked up by id; Status uses `.badge-pending/-approved/-denied`.
  - Empty state row: "No applications with this status." when a filter matches nothing.
**Interactions**:
  - Status chip → filters, re-renders
  - Row click → `#/application/{id}` (e.g. `#/application/104`)

### Application Detail (`#/application/:id`)
**Layout**: page-header (App # + status badge) + `.grid-2` (applicant card, animal card) + action bar card
**Template classes**: `.grid-2 .card .card-title .badge .btn-success .btn-danger .btn-link .alert-success .notfound-card`
**Components**:
  - Looked up from the store by id in the hash — never hardcoded.
  - Applicant card: Name, Email, Phone, Address, Housing ("Rents apartment, pet deposit paid"), Other pets, Submitted date.
  - Animal card: the applied-for animal's name (link → its `#/animal/:id`), species, breed, age, current status badge, kennel.
  - Action bar: "Approve Application" (`.btn-success`) and "Deny Application" (`.btn-danger`). If status is already Approved or Denied, buttons are hidden and an `.alert-success` (or muted note for Denied) shows "Decision: {status} on {date}".
  - Not-found: unknown id (e.g. `#/application/999`) renders `.notfound-card`: "Application not found", message naming the bad id, button "Back to Applications" → `#/applications`.
**Interactions**:
  - Approve → in one store update: application.status = "Approved" (decision date 2026-07-30); the animal's status = "Adopted"; the animal's kennel set to null (kennel freed); a timeline entry "2026-07-30 — Adopted by {applicant name}" pushed onto the animal. Page re-renders showing the Approved badge and confirmation. Effects are visible on next visit to the Dashboard (KPIs shift: in-care −1, available −1, pending −1, kennels free +1), the Animals roster (Adopted badge, kennel "—"), and that animal's detail page.
  - Deny → application.status = "Denied"; animal untouched; page re-renders with Denied badge.
  - Animal name link → `#/animal/{animalId}`; "← Back to Applications" → `#/applications`.

### Settings (`#/settings`)
**Layout**: page-header + single `.card` form (max-width 560px)
**Template classes**: `.card .form-group .form-input .form-select .btn-primary .alert-success`
**Components**:
  - Fields (pre-filled from store): Shelter name (text, "Harborview Animal Shelter"), Total kennels (number, 40 — feeds the Kennels Free KPI), Contact email ("frontdesk@harborview-shelter.gov"), Default hold period (select: 3 / 5 / 7 / 10 days, default 5), Adoption fee — dogs ($120), Adoption fee — cats ($90).
  - "Save Settings" button.
**Interactions**:
  - Save → writes values into the settings store object and shows an inline `.alert-success` above the form: "Settings saved at {time}." (auto-clears after ~3s or persists until next render — inline, no navigation). Changing Total kennels changes the Dashboard's Kennels Free computation.

## State & Data Model
All state in one in-memory JS `store` object; every page renders from it.

animals: array[8] — {id, name, species, breed, sex, age, weight, status, kennel, intakeDate, microchip, notes, timeline[]}
  - a1 Luna — Dog, Labrador mix, F, 3 yr, 58 lb, Available, K-04, 2026-07-08, chip 981-002-337, timeline: intake 07-08 (owner surrender), vet exam 07-09 (healthy), spay confirmed 07-10, made available 07-11
  - a2 Rocky — Dog, German Shepherd, M, 5 yr, 74 lb, Available, K-07, 2026-07-11, timeline: stray intake, vaccinated, made available
  - a3 Biscuit — Dog, Beagle, M, 7 yr, 26 lb, Hold, K-09, 2026-07-12, timeline: stray intake near Harborview Pier, vet exam (underweight, dental), antibiotics started, medical hold
  - a4 Milo — Cat, Domestic shorthair, M, 2 yr, 11 lb, Available, K-12, 2026-07-14, timeline: owner surrender, FVRCP vaccine, made available
  - a5 Clementine — Cat, Maine Coon mix, F, 4 yr, 13 lb, Available, K-15, 2026-07-16, timeline: transfer from Bayside County, exam clear, made available
  - a6 Pepper — Cat, Tuxedo, F, 1 yr, 8 lb, Hold, K-18, 2026-07-19, timeline: stray intake, stray-hold until 08-02
  - a7 Ziggy — Small mammal, Holland Lop rabbit, M, 2 yr, 4 lb, Available, K-21, 2026-07-21, timeline: owner surrender, nail trim, made available
  - a8 Maple — Small mammal, Guinea pig, F, 1 yr, 2 lb, Adopted→ seeded as Available? — No: seeded status Available, K-23, 2026-07-24, timeline: confiscation intake, exam clear, made available. (Adopted rows arise only through Approve actions, keeping seed KPIs consistent: in-care 8, available 6, holds 2.)

applications: array[5] — {id, applicant:{name,email,phone,address,housing,otherPets}, animalId, submitted, status, decisionDate}
  - 102 — Marcus Webb, m.webb@gmail.com, (415) 555-0142, 88 Foghorn Ln, Apt 3 — animal a2 Rocky — 2026-07-18 — Approved 2026-07-22? No: seeded Denied 2026-07-20 (landlord breed restriction) so seed animal statuses stay consistent
  - 104 — Priya Raman, priya.raman@outlook.com, (415) 555-0177, 210 Cliffside Ave — animal a1 Luna — 2026-07-24 — Pending
  - 105 — Tom Delgado, tdelgado@yahoo.com, (415) 555-0119, 4 Marina Ct — animal a5 Clementine — 2026-07-26 — Pending
  - 106 — Dana Okafor, dana.okafor@gmail.com, (415) 555-0163, 971 Lighthouse Rd — animal a4 Milo — 2026-07-28 — Pending
  - 101 — Sofia Marchetti, s.marchetti@icloud.com, (415) 555-0108, 356 Harbor View Dr — animal a7 Ziggy — 2026-07-15 — Denied 2026-07-17 (home visit declined)
  (Seed pending count = 3, matching the Dashboard KPI.)

settings: {shelterName:"Harborview Animal Shelter", totalKennels:40, contactEmail:"frontdesk@harborview-shelter.gov", holdPeriodDays:5, feeDog:120, feeCat:90}

router: hash-based; `parseHash()` splits `#/animal/a3` → {page:"animal", id:"a3"}; `hashchange` + initial load call `render()`; unknown static route falls back to `#/dashboard`; unknown dynamic id renders the not-found card.

## Navigation Flows
- Sidebar links → `#/dashboard`, `#/animals`, `#/intake`, `#/applications`, `#/settings`
- Dashboard KPI "Animals in Care" → `#/animals`; KPI "Pending Applications" → `#/applications`
- Dashboard attention items / kennel snapshot names → `#/animal/:id` or `#/application/:id`
- Animals row click → `#/animal/:id`; "New Intake" button → `#/intake`
- Animal Detail back link → `#/animals`; not-found button → `#/animals`
- Intake valid submit → `#/animal/{newId}`; Cancel → `#/animals`
- Applications row click → `#/application/:id`
- Application Detail animal link → `#/animal/:animalId`; back link → `#/applications`; not-found button → `#/applications`
- Approve/Deny/Settings-save stay on-page (in-place re-render)

## Design Notes
- Color scheme: --bg #f6f8f9 app background, --surface #ffffff cards/sidebar, --fg #1e2a32 text, --accent #0f766e (teal) for active nav, primary buttons, links; semantic green/amber/red/blue tints for badges at ~12% opacity backgrounds with full-strength text.
- Typography: system stack `-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`; page titles 22px/700, card titles 13px uppercase muted, body 14px, table 13.5px.
- Density: compact admin density — 16px card padding, 8px table cell padding, 16px grid gaps, 24px main-content padding; single-file HTML, all CSS/JS inline, no external assets.
</spec>

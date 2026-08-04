<tasks>
## Task 1: HTML Shell & Navigation Chrome
**Goal**: Build the complete HTML skeleton for the Harborview Animal Shelter console — DS-mapped tokens, full CSS class system, sidebar chrome, hash router, in-memory store, and empty page sections for all 7 pages.
**DS Token Mapping** (Harborview Console):
- --bg: #f6f8f9
- --fg: #1e2a32
- --accent: #0f766e
- --surface: #ffffff
- --border: #d8e0e4
- --muted: #64748b
- Extras: --green: #15803d, --amber: #b45309, --red: #b91c1c, --blue: #1d4ed8 (badge tints at ~12% opacity backgrounds with full-strength text)
**Template Classes**: No template (blank canvas) — implement the spec's class system on top of the scaffold: `.app` (grid: 220px sidebar + fluid main), `.sidebar`, `.sidebar-logo`, `.nav-link`, `.nav-link.active`, `.main`, `.page-header`, `.page-title`, `.page-sub`, `.grid-2/.grid-3/.grid-4` (gap 16px), `.stack`, `.row`, `.card`, `.card-title` (13px uppercase muted), `.kpi-value` (28px bold), `.kpi-note`, `.table-wrap` (overflow-x auto), `.table` (1px row borders, 8px cell padding, muted 12px uppercase th), `.table tr.clickable:hover`, `.filter-bar`, `.chip`, `.chip.active`, `.search-input` (240px), `.badge` + variants `.badge-available` (green tint), `.badge-hold`/`.badge-pending` (amber tint), `.badge-adopted` (blue tint), `.badge-approved` (green tint), `.badge-denied`/`.badge-medical` (red tint), `.form-group`, `.form-label`, `.form-input`, `.form-select`, `.form-textarea`, `.form-error`, `.form-hint`, `.btn`, `.btn-primary`, `.btn-success`, `.btn-danger`, `.btn-link`, `.timeline`, `.timeline-item`, `.notfound-card`, `.empty-row`, `.alert-success`, `.attention-item`.
**Typography**: system stack `-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`; page titles 22px/700, body 14px, table 13.5px; compact density (16px card padding, 8px cells, 16px gaps, 24px main padding).
**Chrome**: Left `.sidebar` (220px, surface bg) with `.sidebar-logo` "Harborview Shelter" and nav links: Dashboard → `#/dashboard`, Animals → `#/animals`, New Intake → `#/intake`, Applications → `#/applications`, Settings → `#/settings`. Active link gets `.nav-link.active`; Animal Detail highlights Animals, Application Detail highlights Applications.
**State store** (single in-memory `store` object):
- `store.animals` — array of 8 seed animals `{id, name, species, breed, sex, age, weight, status, kennel, intakeDate, microchip, notes, timeline[]}`:
  - a1 Luna, Dog, Labrador mix, F, 3 yr, 58 lb, Available, K-04, 2026-07-08, chip 981-002-337, timeline: 07-08 owner surrender intake, 07-09 vet exam healthy, 07-10 spay confirmed, 07-11 made available
  - a2 Rocky, Dog, German Shepherd, M, 5 yr, 74 lb, Available, K-07, 2026-07-11, timeline: stray intake, vaccinated, made available
  - a3 Biscuit, Dog, Beagle, M, 7 yr, 26 lb, Hold, K-09, 2026-07-12, timeline: 07-12 "Stray intake — found near Harborview Pier", 07-13 "Vet exam: underweight, dental disease", 07-15 "Started antibiotics course", 07-20 "Placed on medical hold"
  - a4 Milo, Cat, Domestic shorthair, M, 2 yr, 11 lb, Available, K-12, 2026-07-14, timeline: owner surrender, FVRCP vaccine, made available
  - a5 Clementine, Cat, Maine Coon mix, F, 4 yr, 13 lb, Available, K-15, 2026-07-16, timeline: transfer from Bayside County, exam clear, made available
  - a6 Pepper, Cat, Tuxedo, F, 1 yr, 8 lb, Hold, K-18, 2026-07-19, timeline: stray intake, stray-hold until 08-02
  - a7 Ziggy, Small mammal, Holland Lop rabbit, M, 2 yr, 4 lb, Available, K-21, 2026-07-21, timeline: owner surrender, nail trim, made available
  - a8 Maple, Small mammal, Guinea pig, F, 1 yr, 2 lb, Available, K-23, 2026-07-24, timeline: confiscation intake, exam clear, made available
- `store.applications` — array of 5: `{id, applicant:{name,email,phone,address,housing,otherPets}, animalId, submitted, status, decisionDate}`:
  - 101 Sofia Marchetti, s.marchetti@icloud.com, (415) 555-0108, 356 Harbor View Dr — a7 Ziggy — 2026-07-15 — Denied 2026-07-17 (home visit declined)
  - 102 Marcus Webb, m.webb@gmail.com, (415) 555-0142, 88 Foghorn Ln, Apt 3 — a2 Rocky — 2026-07-18 — Denied 2026-07-20 (landlord breed restriction)
  - 104 Priya Raman, priya.raman@outlook.com, (415) 555-0177, 210 Cliffside Ave — a1 Luna — 2026-07-24 — Pending
  - 105 Tom Delgado, tdelgado@yahoo.com, (415) 555-0119, 4 Marina Ct — a5 Clementine — 2026-07-26 — Pending
  - 106 Dana Okafor, dana.okafor@gmail.com, (415) 555-0163, 971 Lighthouse Rd — a4 Milo — 2026-07-28 — Pending
- `store.settings` — `{shelterName:"Harborview Animal Shelter", totalKennels:40, contactEmail:"frontdesk@harborview-shelter.gov", holdPeriodDays:5, feeDog:120, feeCat:90}`
**Router**: Hash-based (use the MANDATORY ROUTER TEMPLATE). `parseHash()` handles static routes and dynamic `#/animal/:id`, `#/application/:id` (e.g. `#/animal/a3` → `{page:"animal", id:"a3"}`). `hashchange` + initial load call `render()`. Unknown static route → fallback `#/dashboard`. Unknown dynamic id → not-found card (handled per-page). All page renders re-read from `store` every time.
**Pages**: dashboard, animals, animal (detail), intake, applications, application (detail), settings — one empty `<section data-page="{id}" class="page">` each; `dashboard` gets `is-active`. ROUTER RULE: `data-page` on `<section>` only, never on `<a>`.
**Routes**: { dashboard: '/dashboard', animals: '/animals', animal: '/animal/:id', intake: '/intake', applications: '/applications', application: '/application/:id', settings: '/settings' }

## Task 2: Dashboard Page (`#/dashboard`)
**Goal**: Fill the dashboard section with live-computed KPIs, Needs Attention list, and Kennel Snapshot.
**Layout**: page-header + `.grid-4` KPI row + `.grid-2` (attention card, kennel snapshot card)
**Template Classes**: `.page-header .page-title .grid-4 .card .card-title .kpi-value .kpi-note .grid-2 .attention-item .badge .btn-link`
**Components**:
- KPI "Animals in Care": count of store.animals with status ≠ Adopted (seed: 8) — clickable, → `#/animals`
- KPI "Available for Adoption": count status = Available (seed: 6 per store; label per spec)
- KPI "Pending Applications": count applications status = Pending (seed: 3) — clickable, → `#/applications`
- KPI "Kennels Free": `store.settings.totalKennels − animals.filter(a => a.kennel !== null).length` (seed: 40 − 8 = 32), `.kpi-note` "of 40 total" (note reads totalKennels live)
- "Needs Attention" card — 4 `.attention-item` rows, each with badge + link:
  - Biscuit (a3) — badge "Medical hold" (`.badge-medical`) → `#/animal/a3`
  - Application APP-104 (Priya Raman → Luna) — badge "Pending 6 days" (`.badge-pending`) → `#/application/104`
  - Pepper (a6) — badge "Hold expires Aug 2" (`.badge-hold`) → `#/animal/a6`
  - Application APP-106 (Dana Okafor → Milo) — badge "Pending" (`.badge-pending`) → `#/application/106`
- "Kennel Snapshot" card: occupied kennels rendered from the store — K-04 Luna, K-07 Rocky, K-09 Biscuit, K-12 Milo, K-15 Clementine, K-18 Pepper, K-21 Ziggy, K-23 Maple — each animal name a link → `#/animal/{id}`
**Interactions**:
- All KPI values recompute on every render — after intake/approval elsewhere, revisiting shows updated numbers
- Click KPI "Animals in Care" → `location.hash = '#/animals'`; KPI "Pending Applications" → `#/applications`
- Attention items / kennel names → their `#/animal/:id` or `#/application/:id`
**Script handlers needed**: [renderDashboard() — full recompute from store, called by router]

## Task 3: Animals Page (`#/animals`)
**Goal**: Fill the animals section with a filterable, searchable roster table.
**Layout**: page-header with "New Intake" button + `.filter-bar` + `.table-wrap` table
**Template Classes**: `.page-header .btn-primary .filter-bar .chip .chip.active .search-input .table-wrap .table .badge .badge-available .badge-hold .badge-adopted .empty-row`
**Components**:
- Species chips: All (default active) / Dogs / Cats / Small mammals
- Status chips: All (default active) / Available / Hold / Adopted
- `.search-input` placeholder "Search by name…" — case-insensitive substring on name, filters on `input` event
- Filter state in JS variables (e.g. `animalsFilter = {species:'All', status:'All', search:''}`); all three compose with AND logic
- Table "Animals": columns [Name, Species, Breed, Age, Status, Kennel, Intake Date]
  Rows: all 8 store animals, e.g. [Luna, Dog, Labrador mix, 3 yr, Available badge, K-04, 2026-07-08], [Rocky, Dog, German Shepherd, 5 yr, Available, K-07, 2026-07-11], [Biscuit, Dog, Beagle, 7 yr, Hold, K-09, 2026-07-12], [Milo, Cat, Domestic shorthair, 2 yr, Available, K-12, 2026-07-14], [Clementine, Cat, Maine Coon mix, 4 yr, Available, K-15, 2026-07-16], plus Pepper, Ziggy, Maple. Status as badge; kennel shows code or "—" when null (adopted). Rows get `.clickable`.
- Empty state: single `<td colspan="7" class="empty-row">No animals match the current filters.</td>` when zero matches (e.g. Small mammals + Adopted)
**Interactions**:
- Chip click → set filter, move `.active`, re-render table
- Search `input` → re-render table
- Row click → `#/animal/{id}`
- "New Intake" button → `#/intake`
**Script handlers needed**: [renderAnimals(), setSpeciesFilter(), setStatusFilter(), onAnimalSearch(), animal row click handler]

## Task 4: Animal Detail Page (`#/animal/:id`)
**Goal**: Fill the animal-detail section rendering one animal from the store by hash id, with not-found handling.
**Layout**: page-header (name + status badge + "← Back to Animals" link) + `.grid-2` (profile card, kennel card) + timeline card
**Template Classes**: `.page-header .badge .grid-2 .card .card-title .timeline .timeline-item .btn .btn-link .notfound-card`
**Components**:
- Look up `store.animals.find(a => a.id === routeId)` on EVERY route render — never hardcoded; after an Approve elsewhere, revisiting shows status Adopted and kennel "—"
- Profile card: Species, Breed, Sex, Age, Weight, Intake date, Microchip #, Notes
- Kennel card: kennel code (e.g. "K-09") with line "Kennel block B, row 2"; if kennel null: "No kennel — adopted" plus adoption note
- Timeline card "Intake & Medical History": rendered from the animal's `timeline[]` (3–5 entries; e.g. Biscuit: 2026-07-12 "Stray intake — found near Harborview Pier", 2026-07-13 "Vet exam: underweight, dental disease", 2026-07-15 "Started antibiotics course", 2026-07-20 "Placed on medical hold"). Entries added by Approve ("Adopted by {applicant}") appear here.
- Not-found (e.g. `#/animal/a99`): `.notfound-card` with paw icon 🐾, "Animal not found", "No animal with id 'a99' exists in the roster.", button "Back to Animals" → `#/animals`. No crash, no console error.
**Interactions**:
- "← Back to Animals" → `#/animals`
- Route change re-reads id from hash and re-renders
**Script handlers needed**: [renderAnimalDetail(id) with guarded lookup + not-found branch]

## Task 5: New Intake Page (`#/intake`)
**Goal**: Fill the intake section with the add-animal form, validation, and store mutation.
**Layout**: page-header + single centered `.card` form (max-width 560px)
**Template Classes**: `.card .form-group .form-label .form-input .form-select .form-textarea .form-error .form-hint .btn-primary .btn`
**Components**:
- Fields: Name (text, required), Species (select: Dog / Cat / Small mammal, default Dog), Breed (text, placeholder "Terrier mix"), Age (text, placeholder "2 yr"), Sex (select: Male / Female), Kennel (select of free codes computed from store: K-01..K-40 minus currently occupied, default first free — recomputed each render), Intake notes (textarea)
- Buttons: "Add Animal" (`.btn-primary`, submit) and "Cancel" (`.btn` → `#/animals`)
**Interactions**:
- Submit with empty/whitespace Name → inline `.form-error` under Name: "Name is required."; red border on the field; no navigation, nothing added; error clears on next `input`
- Valid submit → create `{id: 'a' + (maxNumericId+1)` (e.g. a9), name, species, breed, age, sex, status:"Available", kennel: chosen, intakeDate:"2026-07-30", timeline:[{date:"2026-07-30", text:"Intake: " + (notes || "New intake processed")}]}`, push into `store.animals`, then navigate `#/animal/a9` — new record renders fully; Dashboard KPIs and Animals roster reflect it immediately
**Script handlers needed**: [renderIntake() (recompute free kennels), onIntakeSubmit() with validation + store push + navigate, name input clear-error handler]

## Task 6: Applications Page (`#/applications`)
**Goal**: Fill the applications section with the status-filterable application queue.
**Layout**: page-header + `.filter-bar` + `.table-wrap` table
**Template Classes**: `.filter-bar .chip .chip.active .table-wrap .table .badge .badge-pending .badge-approved .badge-denied .empty-row`
**Components**:
- Status chips: All (default active) / Pending / Approved / Denied
- Table "Applications": columns [App #, Applicant, Animal, Submitted, Status]
  Rows (5, from store; Animal cell = name looked up by animalId): [APP-101, Sofia Marchetti, Ziggy, 2026-07-15, Denied], [APP-102, Marcus Webb, Rocky, 2026-07-18, Denied], [APP-104, Priya Raman, Luna, 2026-07-24, Pending], [APP-105, Tom Delgado, Clementine, 2026-07-26, Pending], [APP-106, Dana Okafor, Milo, 2026-07-28, Pending]. Status as badge; rows `.clickable`.
- Empty state: `.empty-row` "No applications with this status." when a filter matches nothing
**Interactions**:
- Status chip → set filter, move `.active`, re-render
- Row click → `#/application/{id}` (e.g. `#/application/104`)
**Script handlers needed**: [renderApplications(), setAppStatusFilter(), application row click handler]

## Task 7: Application Detail Page (`#/application/:id`)
**Goal**: Fill the application-detail section with review + approve/deny actions mutating the store atomically.
**Layout**: page-header (App # + status badge + "← Back to Applications" link) + `.grid-2` (applicant card, animal card) + action bar card
**Template Classes**: `.grid-2 .card .card-title .badge .btn-success .btn-danger .btn-link .alert-success .notfound-card`
**Components**:
- Look up application by id from the hash on every render — never hardcoded
- Applicant card: Name, Email, Phone, Address, Housing ("Rents apartment, pet deposit paid"), Other pets, Submitted date
- Animal card: applied-for animal's name as link → `#/animal/{animalId}`, species, breed, age, current status badge, kennel
- Action bar: "Approve Application" (`.btn-success`) + "Deny Application" (`.btn-danger`). If status already Approved or Denied: buttons hidden; `.alert-success` (Approved) or muted note (Denied) shows "Decision: {status} on {decisionDate}"
- Not-found (e.g. `#/application/999`): `.notfound-card` "Application not found", message naming the bad id, button "Back to Applications" → `#/applications`
**Interactions**:
- Approve → one store update: app.status = "Approved", app.decisionDate = "2026-07-30"; animal.status = "Adopted"; animal.kennel = null (kennel freed); push timeline entry `{date:"2026-07-30", text:"Adopted by {applicant name}"}` onto the animal; re-render in place showing Approved badge + confirmation. Effects visible on next Dashboard visit (in-care −1, available −1, pending −1, kennels free +1), Animals roster (Adopted badge, kennel "—"), and the animal's detail page.
- Deny → app.status = "Denied", decisionDate = "2026-07-30"; animal untouched; re-render with Denied badge
- Animal name link → `#/animal/{animalId}`; "← Back to Applications" → `#/applications`
**Script handlers needed**: [renderApplicationDetail(id) with not-found branch, onApprove(appId), onDeny(appId)]

## Task 8: Settings Page (`#/settings`)
**Goal**: Fill the settings section with the shelter-preferences form wired to the settings store.
**Layout**: page-header + single `.card` form (max-width 560px)
**Template Classes**: `.card .form-group .form-label .form-input .form-select .btn-primary .alert-success`
**Components**:
- Fields pre-filled from `store.settings` on every render: Shelter name (text, "Harborview Animal Shelter"), Total kennels (number, 40), Contact email ("frontdesk@harborview-shelter.gov"), Default hold period (select: 3 / 5 / 7 / 10 days, default 5), Adoption fee — dogs (120), Adoption fee — cats (90)
- "Save Settings" button (`.btn-primary`)
**Interactions**:
- Save → write all values into `store.settings` (parse Total kennels as number) and show inline `.alert-success` above the form: "Settings saved at {time}." (auto-clears after ~3s via setTimeout, or persists until next render). No navigation.
- Changing Total kennels changes the Dashboard's Kennels Free computation on next visit
**Script handlers needed**: [renderSettings(), onSettingsSave()]

## Task 9: Final Wiring & Validation
**Goal**: Validate all pages have content, verify DS tokens, fix navigation, confirm the cross-page state flows.
**Checks**:
- All 7 `<section data-page>` sections have content (dashboard, animals, animal, intake, applications, application, settings) — none empty
- `:root` tokens match the Harborview Console DS: --bg #f6f8f9, --fg #1e2a32, --accent #0f766e, --surface #ffffff, --border #d8e0e4, --muted #64748b
- Nav links use `href="#/path"` format (fix any `href="#page"`)
- Routes map complete, including dynamic `animal/:id` and `application/:id` parsing; unknown static route falls back to dashboard
- First page (dashboard) has `class="page is-active"`
- No placeholder text anywhere
- All buttons/chips/rows have handlers: KPI clicks, chip filters, search input, row clicks, intake submit/cancel + Name validation, Approve/Deny, settings save, all back links
- Dynamic-id not-found cards render for `#/animal/a99` and `#/application/999` without console errors
- Cross-page flow sanity: Approve APP-104 → Luna Adopted + kennel null + timeline entry; Dashboard KPIs shift (in-care 7, pending 2, kennels free 33); valid intake creates a9 and navigates to its detail
- `data-page` only on `<section>` elements, never on `<a>` tags
</tasks>

<spec>
# Prototype Specification: Cedar Family Clinic — Appointment Viewer

## Template & Design System
- **Template**: none active — blank-canvas mode, full class system defined below
- **Design System**: Clinic Calm — soft neutral surfaces, deep teal accent, high-legibility sans, compact-but-breathable density
- **CSS Class System**: `.sidebar`, `.nav-link`, `.main`, `.page`, `.page-header`, `.page-title`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.badge`, `.badge-confirmed`, `.badge-checkedin`, `.badge-noshow`, `.card`, `.grid-2`, `.detail-list`, `.form-group`, `.form-label`, `.form-input`, `.btn`, `.btn-primary`, `.empty-note`
- **Color Tokens**: --bg=#f6f7f6, --fg=#1c2b2a, --accent=#0f766e, --surface=#ffffff, --border=#dde3e2, --muted=#64748b

## Overview
- **Product**: Internal appointment viewer for Cedar Family Clinic, a two-provider family practice
- **Target audience**: Front-desk staff and the two providers (Dr. Amara Osei, Dr. Ben Kowalski)
- **Core purpose**: See today's schedule at a glance, find a patient fast, and check any patient's detail without leaving the tool
- **Total pages**: 4 (Schedule, Patient Detail, Providers, Settings)

## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| schedule | `#/schedule` | Today's appointment table with live search and status filter | toolbar + full-width table | Yes |
| patient-detail | `#/patient/:id` | One patient's record and visit context, rendered for the clicked row | two-column detail cards | No |
| providers | `#/providers` | The clinic's two providers with today's load | full-width table | No |
| settings | `#/settings` | Clinic display preferences | stacked form card | No |

## Page Specifications

### Schedule (`#/schedule`)
**Layout**: toolbar (search + status filters) above a full-width appointment table
**Template classes**: `.page-header`, `.toolbar`, `.search-input`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.badge`
**Components**:
  - Search box: text input, placeholder "Search patient or provider…", filters table rows as the user types (case-insensitive match on patient and provider names)
  - Status filter: four buttons — All, Confirmed, Checked-in, No-show — exactly one active at a time; combines with the search text
  - Appointment table: columns [Time, Patient, Provider, Reason, Status], 5 rows for Thursday 12 Mar 2026:
    - 08:30, Rosa Delgado, Dr. Amara Osei, Annual physical, Checked-in
    - 09:15, Marcus Webb, Dr. Ben Kowalski, Hypertension follow-up, Confirmed
    - 10:00, Lena Fischer, Dr. Amara Osei, Flu-like symptoms, Confirmed
    - 11:30, Tom Okafor, Dr. Ben Kowalski, Diabetes check (HbA1c review), No-show
    - 14:00, Priya Raman, Dr. Amara Osei, Prenatal visit — week 24, Confirmed
  - Empty-state note: when search + filter match nothing, one row spans the table saying "No appointments match."
**Interactions**:
  - typing in search → table re-filters on every keystroke
  - clicking a filter button → re-filters and moves the active highlight to that button
  - clicking any patient row → navigates to `#/patient/{id}` for that row's patient

### Patient Detail (`#/patient/:id`)
**Layout**: page header with the patient's name, then two cards side by side (record, today's visit)
**Template classes**: `.page-header`, `.grid-2`, `.card`, `.detail-list`, `.badge`
**Components**:
  - Patient record card: date of birth, phone, insurer, allergies — pulled from the store for the `:id` in the route (101 Rosa Delgado, 102 Marcus Webb, 103 Lena Fischer, 104 Tom Okafor, 105 Priya Raman)
  - Today's visit card: time, provider, reason, status badge for that patient's appointment
  - Back link: "← Back to schedule" navigating to `#/schedule`
**Interactions**:
  - the page renders whichever patient id the route carries — five distinct records, never one hardcoded patient
  - back link → navigates to `#/schedule`

### Providers (`#/providers`)
**Layout**: full-width table under a page header
**Template classes**: `.page-header`, `.table-wrap`, `.table`
**Components**:
  - Provider table: columns [Provider, Specialty, Room, Today's appointments], 2 rows:
    - Dr. Amara Osei, Family medicine & prenatal care, Room 2, 3 appointments
    - Dr. Ben Kowalski, Family medicine & chronic care, Room 4, 2 appointments
**Interactions**:
  - none beyond navigation; the counts must agree with the Schedule page's data

### Settings (`#/settings`)
**Layout**: single form card
**Template classes**: `.card`, `.form-group`, `.form-label`, `.form-input`, `.btn-primary`
**Components**:
  - Clinic name field, pre-filled "Cedar Family Clinic"
  - Working-day start field, pre-filled "08:00"
  - Reminder lead-time field, pre-filled "24 hours"
  - Save preferences button → shows the inline confirmation "Preferences saved."
**Interactions**:
  - Save preferences → writes the confirmation line under the button; no navigation

## State & Data Model
patients: array — five records keyed by id 101–105 with name, dob, phone, insurer, allergies
appointments: array — the five schedule rows, each carrying patientId, time, provider, reason, status
filters: object — { query: "", status: "all" } driving the Schedule table
settings: object — { clinicName: "Cedar Family Clinic", dayStart: "08:00", reminderLead: "24 hours" }

## Navigation Flows
sidebar Schedule → `#/schedule`
sidebar Providers → `#/providers`
sidebar Settings → `#/settings`
schedule row (any) → `#/patient/{that row's patientId}`
patient detail back link → `#/schedule`

## Design Notes
- Color scheme: calm clinical neutrals; teal `--accent` reserved for the active nav item, active filter and primary button
- Typography: single humanist sans for display and body; tabular numbers in the schedule table
- Density: compact rows (10px vertical padding) so five appointments and the toolbar fit without scrolling
</spec>

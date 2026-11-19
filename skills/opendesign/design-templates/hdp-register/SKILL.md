---
name: HDP Register
description: |
  A dark-themed enterprise compliance workbench for health-data privacy
  registers. Provides a sidebar-nav shell over a multi-view SPA: a dashboard
  KPI summary, a searchable registration list with status chips, an 11-section
  stepper form for record creation/editing, a role-differentiated detail view,
  a DPO review form, an audit trail, a document vault, and an admin panel
  (users, permissions, mandates, questionnaire). Built for GDPR/BDSG-style
  regulatory registers but adaptable to any regulated-record lifecycle where
  records pass through a creation → review → release workflow.
triggers:
  - "compliance workbench"
  - "data privacy register"
  - "GDPR register"
  - "regulatory workbench"
  - "health data register"
  - "data protection"
  - "registration lifecycle"
  - "record management"
  - "DPO workbench"
  - "compliance register"
  - "privacy register"
  - "medical device registry"
od:
  mode: prototype
  platform: desktop
  scenario: compliance
  preview:
    type: html
    entry: example.html
  design_system:
    requires: true
    sections: [color, typography, layout, components]
  craft:
    requires:
      - form-validation
      - state-coverage
      - accessibility-baseline
      - anti-ai-slop
  outputs:
    primary: prototype.html
  example_prompt: >
    Build an HDP register workbench for a pharmaceutical company — a
    registration list with GDPR/BDSG status chips, an 11-section stepper form
    covering data categories, legal basis, service providers, recipients, access
    controls, retention, and DPIA, plus DPO review, an audit trail, reports with
    KPI tiles, and an admin panel for users and mandates.
  inputs:
    - name: domain
      description: "The regulated domain (e.g. health data, financial data, HR data) and the governing regulation (GDPR, BDSG, HIPAA)"
    - name: register_columns
      description: "The columns of the main register and what each status chip means in the lifecycle"
    - name: form_sections
      description: "The sections of the multi-step registration form and the key fields in each"
    - name: roles
      description: "The user roles, their capabilities, and which views they can access"
    - name: reports_kpis
      description: "The KPI tiles shown in the reports view and what they measure"
---

# HDP Register Skill

Produce a single, self-contained HTML prototype of an **enterprise compliance
workbench** — a sidebar-nav shell over a multi-view SPA with a stepper-driven
registration form, role-based views, a DPO review workflow, an audit trail, and
reports. Compose it from the bundled `example.html` reference — **not** by
writing CSS from scratch. The reference already encodes the visual system (dark
navy chrome, teal primary, orange accent, pill status chips, monospace IDs) and
a complete inline-JS state machine. Your job is to re-skin the copy and
re-shape the domain data.

---

## What This Template Is

A dark-themed enterprise workbench for managing regulated data-processing
records through a formal lifecycle:

```
Created → Published → Submitted → Released
                              ↘ Rework → (back to Published/Submitted)
                              ↘ Rejected
                              ↘ Cancelled / De-registered
```

Each record is a structured registration form covering data categories, legal
basis, service providers, data recipients, access controls, retention/deletion
rules, and a DPIA assessment. A DPO reviews submitted records and releases them
(or returns them). Every state transition is logged to an immutable audit trail.

**When to use this:**
- GDPR / BDSG data-privacy registers (Art. 30 processing inventories)
- Health-data processing registers, clinical trial portals
- Internal HR-data or IT-system registers
- Any domain where records follow a create → submit → review → release cycle

**Reach for a different template when:** the brief is a generic analytics
dashboard (`dashboard`), a financial-transaction workbench
(`underwriting-workbench`), or a marketing page (`web-prototype`, `saas-landing`).

---

## Chrome — Shell Layout

The shell is a **fixed topbar (58 px)** + **fixed sidebar (205 px)** + a
**scrollable main content area** that fills the remaining viewport. Never
collapse this to a full-width top-nav — the sidebar is the primary orientation
tool for a dense multi-view tool.

```
┌─────────────────────────────────────────────────────────────┐
│  58 px HEADER — logo · title · role selector · avatar       │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  205 px      │  Main content area (scrollable per-view)    │
│  SIDEBAR     │                                              │
│  (fixed)     │  .view.on { display: flex; flex-dir: col }  │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

**Topbar (`.hdr`):** dark header background (`--header`), `2px solid var(--accent)`
bottom border. Left: logo + brand wordmark + divider + page title. Right: role
selector (`.role-sel`) + avatar (`.ava`).

**Sidebar (`.sb`):** sidebar background (`--sidebar`), `1px solid --border` right
border. Grouped with section labels (`.sb-lbl`). Each item is `.ni`; the active
item gets `.ni.on` with accent left-border and primary text.

**View container:** flex child, `overflow: hidden`, contains all `.view` divs.
Only the active view has `.view.on` (display: flex). Views animate in with
`opacity 0→1 + translateY(4px→0)` over 180 ms.

**Progress bar (`.pb-wrap`):** 3 px strip below topbar showing form completion.

---

## How the Example is Organised

```
example.html
├── <style>            Design tokens (:root), reset, shell, all component CSS
├── <svg style="display:none">   Inline icon sprite (SVG symbols)
├── <script 1>         seedData() — all seed records, mandates, users, notifs
├── <script 2>         Core globals — S (state), STATUS_CLS, CAPS, TRANS, utils
├── <script 3>         Validators — required fields, tristate logic, completeness %
├── <script 4>         Form helpers — section renderers for all 11 form steps
├── <script 5>         Paint functions — paintHome(), paintList(), paintDetail(),
│                      paintReview(), paintReports(), paintUsers(), etc.
├── <div class="hdr">  Topbar chrome
├── <div class="app">
│   ├── <nav class="sb">    Sidebar nav
│   └── <main class="main">
│       ├── <div class="view" id="home">    …
│       ├── <div class="view" id="list">    …
│       ├── <div class="view" id="form">    …
│       └── … (one .view per route)
├── <div class="toast-w" id="toasts">  Toast container
├── <div class="modal-overlay" id="modals">  Modal mount point
└── <script 6>         Boot — load S, wire events, navigate to first view
```

**State object `S`:** single global holding `role`, `records[]`, `mandates[]`,
`users[]`, `notifs[]`, `filters{}`, `cur` (selected record rid), `draft` (form
data), `step` (stepper step), and all admin/config sub-trees.

**Router:** `navigate(viewId)` sets `S.view`, re-paints the sidebar, toggles
`.view.on`, and calls `PAINT_FN[viewId]()` to inject HTML into the view div.

**Data flow:** Every user action → updates `S` → calls `persist()` to
`localStorage` → re-paints the affected view element (or the whole view if
structural).

---

## Screen Patterns

Ten routed views. Each view div has `id="<viewId>"` and `data-od-id="<viewId>"`.

| View id | Reached by | Key pattern |
|---|---|---|
| `home` | Sidebar click / boot | KPI tile row (`.krow`) + recent activity table |
| `list` | Sidebar click | Filter bar + toggle group + sortable `.tbl` with status chips |
| `form` | "New" button, record edit | Stepper sidebar (195 px) + 11-section scroll-form |
| `detail` | Row click / RID link | Two-column `.det-b` grid of `.dsec` detail-section cards |
| `review` | Sidebar "Review Queue" | Review box + legal-ref alert + DPO action buttons |
| `dpa-review` | DPA role only | DPA structured opinion form |
| `wc` | Works-council role | WC section checkbox + comment |
| `audit` | "Audit Trail" sidebar | Chronological event log with actor + timestamp |
| `docs` | "Documents" sidebar | File list table with section tag + authority flag |
| `notifications` | Bell icon / sidebar | Grouped notification rows + `.ndot` read state |
| `reports` | Sidebar click | 5 `.kpi` tiles + per-tab report tables (`.rcon`) |
| `users` | Admin sidebar | User table with role badges |
| `matrix` | Admin sidebar | Permission matrix table (role × permission) |
| `mandates` | Admin sidebar | Mandate management list |
| `prefs` | Admin sidebar | System preferences form |
| `questionnaire` | Admin sidebar | Pre-qualification question list |

**Form stepper (11 sections):**
1. General Information — application name, mandate, people, attachments
2. Data Categories & Purpose — affected groups, sensitive data, purpose
3. Legal Basis — GDPR legal basis checkboxes, legitimate interest description
4. Service Providers — provider accordion with DPA/TOM/assessment fields
5. Data Recipients — recipient table with transfer mechanism
6. Access Authorizations — access groups, auth concept, user count
7. Deletion & Retention — policy, auto-deletion, retention period + reason
8. Control Measures — CAP/TRA status + FAM (technical/organisational measures) accordions
9. DPIA — necessity, completed flag, attachment
10. Privacy by Design — 5 tristate questions (terms, cookies, privacy statement, etc.)
11. Additional Information — remarks, change description, extra attachments

**Status chip pattern:** `.bdg.s-<code>` — 9 px uppercase bold text, pill shape
(`border-radius: 11px`), background/border/text all derived from the same
semantic token at different opacities.

**Tristate control pattern (`.ts`):** three buttons — Yes / No / Inapplicable —
each with an active class (`ts-y` / `ts-n` / `ts-i`). Used for binary compliance
questions where "not applicable" is a valid third answer.

---

## Interactions

### Role-gated view changes
Changing the role selector re-paints sidebar nav (hiding/showing items the role
can't access), re-renders all action buttons in the current view, and clears any
in-progress operation that the new role can't complete.

### Status transitions
Transitions are defined in the `TRANS` map: each has `from[]`, `to`, `cap`,
`req` (comment required), and optionally `flag` (sets a boolean on the record).
Transition buttons appear in the detail/review view only when:
- `S.role` has the required `cap` in `CAPS[role]`
- `rec.status` is in `TRANS[action].from`
- `canEdit(rec)` returns true for edit actions

On confirmation: set `rec.status = TRANS[action].to`, append an audit entry,
call `persist()`, re-paint the view.

### Form validation
Each stepper section reports a completeness badge (count of filled required
fields). Sections with unfilled required fields show a warning dot. `Publish`
and `Submit` actions run a full-form validation sweep; a toast lists all missing
fields and blocks the transition.

### Accordion (FAM — Technical & Organisational Measures)
Each measure category is an accordion section. Clicking the header toggles
`.acc-b.op`. Checkboxes inside update `S.draft.tom.fam[category][]`.

### Modals
All modals mount into `#modals`. Pattern: overlay click / Escape / Cancel close
the modal. Confirm buttons trigger the action and close. Modal state lives in `S.modal`.

### Toast notifications
`toast(message, isError)` appends a `.toast` div to `#toasts`. Auto-removes
after 3 seconds. Used for: save confirmation, transition success, validation
failure, clipboard copy.

### Comments
Comments attach to a section of a record. `addComment(sec, text)` appends to
`rec.comments[]` with actor, role, section, timestamp. Comments render as
`.cmt-item` with left-primary border in the review and detail views.

---

## Hard Rules

- **Single self-contained `prototype.html`** — one inline `<style>` in `<head>`,
  one inline vanilla-JS `<script>` before `</body>`. No CDN, no framework, no
  build step. All SVG icons inline in an `<svg style="display:none">` sprite block.
- **System font stack** — `'Segoe UI', system-ui, sans-serif` for body text;
  `'Cascadia Code', 'Consolas', monospace` for record IDs, mandate codes, and
  audit timestamps. Monospace identifiers are load-bearing to the enterprise feel.
- **Sidebar layout is mandatory.** The sidebar is 205 px fixed; the content area
  takes the rest. Never collapse this to a top-nav layout.
- **`data-view` / `data-nav` attributes on the right elements.** `.view` divs get
  `id="<viewId>"`. Sidebar items get `data-nav="<viewId>"`. Each view must have
  a matching entry in `PAINT_FN`.
- **`data-od-id` on every top-level view** so comment mode can target sections.
- **State lives in `S`.** Every click handler reads from and writes to `S`, then
  calls `persist()`. No globals outside `S` and pure utility functions.
- **Density is the point.** 12–13 px body text in tables, 10 px uppercase table
  headers, 9 px status chip labels. Resist increasing spacing or font sizes.
- **Role-gating must work.** The role selector must immediately re-paint sidebar
  nav items (hiding those the role can't access), action buttons, and review panels.
- **Status chips only.** Never display raw status strings as plain text. Always
  use `bdg(status)` which renders the `.bdg.s-*` pill.
- **Audit trail is immutable.** Every status transition appends to `rec.audit[]`
  with `{ts, actor, role, type, action, from, to, section, comment}`. Do not
  update or delete existing audit entries.
- **Numbers must be internally consistent.** KPI tile counts must match the
  `S.records` array; status breakdown charts must add up to the totals.
- **Keep `assets/template.html` under 6,000 characters.** The seed is injected
  as `seed[:6000]` — anything past that is silently dropped mid-file.

---

## Output Contract

One self-contained document starting `<!DOCTYPE html>`, persisted to disk as
`prototype.html`. No markdown fences, no prose before or after the HTML inside
the file.

> The `od_prototype` pipeline's build agent writes the file with `write_file` /
> `edit_file` and the engine reads it back from disk. Do not stream HTML as
> chat text — in this pipeline the file on disk *is* the deliverable.

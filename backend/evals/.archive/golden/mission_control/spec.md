<spec>
# Prototype Specification: Mission Control — Meridian Program Transformation Suite

## Template & Design System
- **Template**: None (blank-canvas mode) — custom "command-center" layout: fixed left sidebar navigation + main content area, dark-accented executive dashboard aesthetic with diagram-first pages.
- **Design System**: "Meridian Ops" (invented) — deep navy/slate surfaces, electric-teal accent, amber/red/green status semantics, Inter-style sans for UI, tabular numerals for KPIs, medium density (consulting-grade PMO tool).
- **CSS Class System** (the build agent implements exactly these):
  - Chrome: `.app` (grid: 232px sidebar + 1fr main), `.sidebar`, `.sidebar-logo`, `.nav-item`, `.nav-item.active`, `.main`, `.page-header`, `.page-title`, `.page-sub`, `.crumb`
  - Layout: `.grid-2`, `.grid-3`, `.grid-4` (responsive CSS grids, 16px gap), `.row` (flex, gap 12px), `.section` (margin-bottom 24px)
  - Cards: `.card` (surface bg, 1px border, 10px radius, 16px padding), `.card-title`, `.kpi-tile`, `.kpi-value` (28px, tabular-nums), `.kpi-label`, `.kpi-delta` (`.up` green / `.down` red)
  - Status: `.badge` + variants `.badge-green`, `.badge-amber`, `.badge-red`, `.badge-blue`, `.badge-gray`; `.chip` (pill, accent-tinted) for the current-stage chip; `.delta-badge` variants `.delta-new`, `.delta-updated`, `.delta-unchanged`
  - Tables/lists: `.table`, `.table-wrap` (overflow-x auto), `.list`, `.list-item` (hover surface, cursor pointer for clickable rows)
  - Forms/buttons: `.btn`, `.btn-primary`, `.btn-danger`, `.btn-ghost`, `.form-group`, `.form-label`, `.form-input`, `.form-select`, `.form-check`, `.save-confirm` (inline green confirmation, fades in)
  - Diagrams: `.canvas-wrap` (overflow-x auto), `.gantt` (CSS grid rows), `.gantt-bar` (absolute-positioned rounded bar), `.gantt-bar.rippled` (amber outline pulse), `.today-line`, `.milestone` (rotated 45° square), `.legend`, `.legend-item`, `.checklist`, `.check-item` (`.done`, `.doing`, `.todo`), `.not-found-card` (centered friendly card with icon + back link)
  - SVG conventions: nodes `rect rx=8`, decision `polygon` diamonds, connectors `path` with `marker-end` arrowheads, animated flow edges via `stroke-dasharray: 6 6` + CSS `@keyframes dashflow { to { stroke-dashoffset: -24 } }` on class `.flow-edge`; gate status rings via `circle` stroke color; walkthrough highlight via class `.gate-current` (thick accent ring + soft glow).
- **Color Tokens**: --bg=#0d1420, --fg=#e8edf5, --accent=#2dd4bf, --surface=#16202f, --border=#263449, --muted=#8496ad; semantics: --green=#34d399, --amber=#fbbf24, --red=#f87171, --blue=#60a5fa.

## Overview
- **Product**: Mission Control — the program-transformation suite for Atlas Consumer Bank's "Meridian" core-banking modernization program.
- **Target audience**: Program director, transformation office (TMO), workstream leads, executive steering committee.
- **Core purpose**: One live operating picture of the Meridian program — health KPIs, the target operating-model canvas, workstream timelines, and the stage-gate approval chain — where every action (gate approval, milestone shift) propagates through a single store.
- **Total pages**: 7 — Dashboard, Program Canvas, Workstreams, Workstream Detail (dynamic), Gates, Gate Detail (dynamic), Settings.

## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| dashboard | `#/dashboard` | Executive KPIs, stage chip, attention list | kpi-row + grid-2 panels | Yes |
| canvas | `#/canvas` | Two-lane SVG operating-model process canvas with delta badges | full-width canvas card + legend | No |
| workstreams | `#/workstreams` | Gantt of 6 workstreams, milestones, dependencies, shift action | toolbar + gantt card | No |
| workstream-detail | `#/workstream/:id` | Dynamic detail: mini-Gantt, activities, risks, canvas steps | header + grid-2 detail cards | No |
| gates | `#/gates` | Stage-gate approval chain diagram + walkthrough player | player toolbar + chain SVG card + gate table | No |
| gate-detail | `#/gate/:id` | Dynamic gate detail: criteria, evidence, Approve / Send back | header + grid-2 detail cards | No |
| settings | `#/settings` | Program preferences form with inline save confirmation | single centered form card | No |

Sidebar shows 5 items (Dashboard, Program Canvas, Workstreams, Gates, Settings); the two dynamic routes highlight their parent nav item.

## Page Specifications

### Dashboard (`#/dashboard`)
**Layout**: page-header with current-stage chip + `.grid-4` KPI row + `.grid-2` (attention list | gate progress summary)
**Template classes**: `.page-header .chip .grid-4 .kpi-tile .grid-2 .card .list .list-item .badge`
**Components**:
  - Current-stage chip: "Current stage: {store.currentStage}" — seeded "Stage 3 — Build & Integrate"; recomputed from gates (last Approved gate + 1) so approving G3 on Gate Detail advances it to "Stage 4 — Test & Migrate".
  - KPI tiles (all computed from store, never hardcoded):
    1. **Program health** — worst-of workstream RAG (seed: Red, because Data Migration is Red — worst-of outranks the two Amber workstreams → shows "Red" with `.kpi-delta.down` "1 workstream red"). Compute: red if any ws.rag==='red', else amber if any amber, else green.
    2. **% complete** — mean of workstream percentComplete (seed values → 54%).
    3. **Open risks** — count of risks with status 'Open' across all workstreams (seed: 7).
    4. **Next gate** — earliest gate with status !== 'Approved': name + date (seed: "G3 — Build Complete · 12 Sep 2026"). Must re-render after milestone shift (+2 weeks → 26 Sep 2026) and after gate approval (advances to G4).
  - Attention list (`.card` "Needs attention", min 5 items, each a `.list-item` linking into detail pages):
    1. "Data Migration workstream is RED — reconciliation defect backlog growing" → `#/workstream/ws-data`
    2. "G3 — Build Complete gate review due 12 Sep 2026" → `#/gate/g3`
    3. "Risk: Temenos T24 licence renewal unsigned (Payments Migration)" → `#/workstream/ws-pay`
    4. "Core Ledger Replatform milestone 'Ledger cutover rehearsal' at risk" → `#/workstream/ws-core`
    5. "G2 — Design Complete approved 18 Apr 2026 — conditions closing" → `#/gate/g2`
     List is partially computed: red/amber workstreams and the next pending gate are always injected at the top.
  - Gate progress summary card: horizontal 5-segment stepper (G1–G5) rendered from store gate statuses — filled teal = Approved, amber ring = In review, gray = Not started; each segment clickable → its gate detail.
**Interactions**:
  - Each attention item → navigates to its target route.
  - Each KPI tile "Next gate" → `#/gate/{nextGateId}`.
  - Stepper segment → `#/gate/:id`.

### Program Canvas (`#/canvas`)
**Layout**: page-header + legend row + one full-width `.card > .canvas-wrap` containing a single inline `<svg>` (~1160×560)
**Template classes**: `.card .canvas-wrap .legend .legend-item .delta-badge`
**Components**:
  - Inline SVG operating-model canvas, two horizontal lanes with lane labels on the left:
    - **Business lane** (top): Customer Onboarding → Account Servicing → ◇ "Straight-through?" decision → Payments Initiation → Disputes & Complaints → Collections
    - **Technology lane** (bottom): Channel APIs → ◇ "Legacy or Meridian?" decision → Core Ledger (Meridian) → Payments Hub → Data & Reporting Platform → Batch Decommission
  - Each step node: `rect rx=8` + title + owning-workstream subtitle + a delta badge (small pill in the node's top-right corner): **New** (teal) on Channel APIs, Payments Hub, Data & Reporting Platform; **Updated** (amber) on Customer Onboarding, Payments Initiation, Core Ledger, Account Servicing; **Unchanged** (gray) on Disputes & Complaints, Collections, Batch Decommission (Batch Decommission additionally styled with a red "Retiring" sub-badge).
  - Connectors: solid arrows (marker-end) within lanes; **animated dashed `.flow-edge` arrows** crossing lanes (Payments Initiation → Payments Hub; Account Servicing → Core Ledger; Core Ledger → Data & Reporting Platform) with the dashflow keyframe animation.
  - Two decision diamonds (`polygon`) with Yes/No branch labels.
  - Legend: New / Updated / Unchanged delta badges, decision diamond, animated flow edge sample, plus "click a node to open its workstream".
  - Canvas data is rendered from `store.canvasSteps` (each step: id, lane, label, delta, workstreamId, x/y or index) — not hardcoded SVG markup, so Workstream Detail can reuse the same records.
**Interactions**:
  - Click any step node or diamond → `#/workstream/{step.workstreamId}` (e.g. Core Ledger node → `#/workstream/ws-core`).
  - Node hover: brighter border + cursor pointer (CSS).

### Workstreams (`#/workstreams`)
**Layout**: page-header + toolbar row (selected-workstream label + shift button) + full-width Gantt `.card` + legend
**Template classes**: `.card .gantt .gantt-bar .today-line .milestone .btn .btn-primary .legend .badge`
**Components**:
  - Gantt timeline of the 6 workstreams over program months **Jan 2026 – Jun 2027** (18 month columns, faint gridlines), rendered from `store.workstreams` — CSS grid rows with absolutely-positioned bars sized by start/end month fraction; bar color by RAG (green/amber/red tint), label + owner inside/beside bar:
    1. **ws-core** Core Ledger Replatform — owner Priya Raman — Feb 2026 → Feb 2027 — Amber — 58%
    2. **ws-pay** Payments Migration — owner Daniel Okafor — Mar 2026 → Mar 2027 — Amber — 47% — depends on ws-core
    3. **ws-data** Data Migration & Reconciliation — owner Sofia Marchetti — Apr 2026 → Apr 2027 — Red — 38% — depends on ws-core
    4. **ws-chan** Channels & API Enablement — owner James Whitfield — Jan 2026 → Nov 2026 — Green — 72%
    5. **ws-risk** Risk, Compliance & Controls — owner Amara Nwosu — Feb 2026 → May 2027 — Green — 61% — depends on ws-pay
    6. **ws-people** Operating Model & People Transition — owner Tomás Herrera — May 2026 → Jun 2027 — Green — 46% — depends on ws-data
  - Milestone diamonds on bars (from `ws.milestones`, each {label, date}), e.g. ws-core: "Ledger cutover rehearsal · 30 Oct 2026"; ws-pay: "Faster Payments live proving · 15 Dec 2026"; ws-data: "Full reconciliation pass · 20 Jan 2027"; ws-chan: "Open Banking APIs live · 01 Sep 2026"; ws-risk: "Reg sign-off pack submitted · 28 Feb 2027"; ws-people: "New TOM go-live · 01 Apr 2027".
  - Dependency arrows: thin SVG overlay connectors from predecessor bar end → dependent bar start (ws-core→ws-pay, ws-core→ws-data, ws-pay→ws-risk, ws-data→ws-people).
  - Today marker: vertical accent line at 30 Jul 2026 with "Today" tag.
  - Row click selects a workstream (highlighted row + toolbar shows "Selected: Core Ledger Replatform"); default selected: ws-core.
  - Toolbar button **"Shift milestone +2 weeks"** (`.btn-primary`).
**Interactions**:
  - Click a Gantt row label/bar once → selects it; click the workstream name link (or a dedicated "Open" chevron on the row) → `#/workstream/{id}`.
  - "Shift milestone +2 weeks" → store action `shiftWorkstream(selectedId, 14)`: moves the selected workstream's end date and milestone dates +14 days, then **ripples transitively** to all dependent workstreams (their start/end/milestones +14 days), and shifts any gate whose `linkedWorkstreamId` is affected (G3 is linked to ws-core) — bars re-render with `.rippled` amber pulse on every moved bar for 1.5s, and the Dashboard "Next gate" KPI shows the new date (12 Sep → 26 Sep 2026). Action is repeatable and cumulative.
  - Legend explains RAG colors, milestone diamond, dependency arrow, today line.

### Workstream Detail (`#/workstream/:id`)
**Layout**: page-header (name + RAG badge + owner + % complete) + `.grid-2` of four cards: mini-Gantt of activities | activity checklist | risks table | canvas steps list
**Template classes**: `.page-header .badge .crumb .grid-2 .card .gantt .checklist .check-item .table .table-wrap .delta-badge .not-found-card`
**Components** (ALL rendered from `store.workstreams[id]` — the route param — never a hardcoded record; every one of the 6 workstreams has full seed data for all four cards):
  - Breadcrumb "Workstreams / {name}" → `#/workstreams`.
  - Mini-Gantt card: the workstream's 4–6 activities as bars across its own date span, today line included. Example seed for ws-core: Design ledger target architecture (Feb–Apr 26, done), Build ledger services (Apr–Sep 26, in progress), Integrate GL feeds (Jun–Nov 26, in progress), Cutover rehearsal (Oct–Nov 26, not started), Production cutover (Jan–Feb 27, not started). (Analogous realistic activity sets seeded for ws-pay, ws-data, ws-chan, ws-risk, ws-people.)
  - Activity checklist card: the same activities as `.check-item`s with status badge Done / In progress / Not started; clicking a checkbox toggles Done ↔ In progress, and a Not started item goes straight to Done, then recomputes this workstream's percentComplete (done/total), which updates the Dashboard % complete KPI.
  - Risks table: columns [Risk, Severity, Owner, Status] — e.g. ws-core rows: "GL mapping gaps for suspense accounts · High · P. Raman · Open", "Cutover window exceeds 48h · High · M. Chen · Open", "Vendor SME availability in Q4 · Medium · P. Raman · Mitigating", "Interest accrual rounding variance · Medium · L. Novak · Open", "Dual-run cost overrun · Low · Finance TMO · Closed" (≥4 risks per workstream; 'Open' rows feed the Dashboard open-risk count).
  - Canvas steps card: list of the canvas steps owned by this workstream (filtered from `store.canvasSteps` by workstreamId) with their delta badges; each item → `#/canvas`.
**Interactions**:
  - Checklist toggle → store update → % KPI propagation.
  - Canvas step item → `#/canvas`; breadcrumb → `#/workstreams`.
  - **Unknown id** (e.g. `#/workstream/ws-zzz`) → `.not-found-card`: "Workstream not found — 'ws-zzz' isn't part of the Meridian program." with a "Back to Workstreams" `.btn` → `#/workstreams`. Never crashes.

### Gates (`#/gates`)
**Layout**: page-header + walkthrough player toolbar (Play / Next / Reset + step caption) + full-width chain SVG `.card` + gates summary table
**Template classes**: `.card .canvas-wrap .btn .btn-primary .btn-ghost .table .table-wrap .badge`
**Components**:
  - Stage-gate chain diagram (inline SVG, rendered from `store.gates`): 5 gate groups left→right joined by arrow connectors. Each group = the gate label ("G1 — Mobilization Complete" … "G5 — Benefits Realized") above a row of 3 approver nodes (circle avatar-initials + name + role): e.g. G3 approvers: Helena Voss (Program Director), Marcus Bell (CIO), Ingrid Salomon (Chief Risk Officer). Each gate's approver cluster is enclosed by a **status ring**: green solid = Approved (G1, G2), amber = In review (G3), gray dashed = Not started (G4, G5). Statuses come from the store, so approving G3 on Gate Detail re-renders this ring green and G4's amber.
  - Seed gates: **g1** "G1 — Mobilization Complete" (Approved 20 Dec 2025), **g2** "G2 — Design Complete" (Approved 18 Apr 2026), **g3** "G3 — Build Complete" (In review, due 12 Sep 2026, linked ws-core), **g4** "G4 — Migration Rehearsal Passed" (Not started, due 30 Jan 2027, linked ws-data), **g5** "G5 — Benefits Realized" (Not started, due 15 Jun 2027, linked ws-people).
  - Walkthrough player: **Play** auto-advances a `.gate-current` highlight (thick teal ring + glow) along G1→G5 at 1.2s intervals with a caption under the toolbar ("Step 2 of 5: G2 — Design Complete — approved by 3 of 3 approvers on 18 Apr 2026"); **Next** advances one step manually (Play pauses); **Reset** clears the highlight and caption. At the end, Play stops and the button reverts to "Play".
  - Gates table: columns [Gate, Status, Decision date / Due, Chair, Criteria met] with 5 rows (criteria met computed, e.g. "5/7" for G3); row click → gate detail.
**Interactions**:
  - Click any gate group in the SVG or table row → `#/gate/{id}`.
  - Play / Next / Reset behave as above (interval stored and cleared on navigation/Reset).

### Gate Detail (`#/gate/:id`)
**Layout**: page-header (gate name + status badge + due/decision date + chair) + `.grid-2`: criteria checklist card | evidence list card; action bar with Approve + Send back
**Template classes**: `.page-header .badge .crumb .grid-2 .card .checklist .check-item .list .btn-primary .btn-danger .not-found-card`
**Components** (rendered from `store.gates[id]` via the route param — all 5 gates fully seeded):
  - Breadcrumb "Gates / {gate.name}" → `#/gates`.
  - Criteria checklist (≥5 per gate; met/unmet with green check / gray circle). g3 seed: "All build epics closed in Jira (met)", "SIT defect count ≤ 25 open, 0 critical (met)", "Core ledger performance test ≥ 1,800 TPS (met)", "Payments hub certified against Faster Payments scheme (unmet)", "Data reconciliation variance < 0.01% (unmet)", "Security penetration test remediations closed (met)", "Runbook signed by Operations (met)".
  - Evidence list (≥4 items with doc name, owner, date): e.g. "SIT Exit Report v1.3 — QA Guild — 28 Aug 2026", "Performance Test Results — NFT Team — 25 Aug 2026", "Pen-Test Remediation Log — CISO Office — 20 Aug 2026", "Cutover Runbook v0.9 — Ops Readiness — 30 Aug 2026", "Architecture Compliance Memo — Design Authority — 15 Aug 2026".
  - Approvers row: this gate's 3 approvers with name + role and per-approver status badge (Approved / Pending).
  - Action bar: **"Approve gate"** (`.btn-primary`) and **"Send back"** (`.btn-danger`).
**Interactions**:
  - **Approve gate** → store action `approveGate(id)`: sets status 'Approved' with decision date = today (30 Jul 2026), marks all approvers Approved, sets the next Not-started gate to 'In review', and recomputes `currentStage` — Dashboard's stage chip and next-gate KPI update, and the Gates chain re-rings this gate green. Button then renders disabled "Approved ✓". Shows inline confirmation "Gate approved — program advanced to {new stage}".
  - **Send back** (enabled on any gate not yet Approved — an In review gate keeps that status, a Not started one such as g4/g5 moves to it) → sets status 'In review' with an inline amber note "Sent back to workstream lead {owner of linked workstream} with conditions", appends a criteria item "Address steering-committee conditions (unmet)", and unmet criteria count updates on the Gates table.
  - Already-approved gates (g1, g2) show Approve disabled and decision metadata.
  - **Unknown id** (e.g. `#/gate/g9`) → `.not-found-card`: "Gate not found — 'g9' isn't in the Meridian stage-gate plan." + "Back to Gates" button → `#/gates`. Never crashes.

### Settings (`#/settings`)
**Layout**: page-header + single centered `.card` form (max-width 560px)
**Template classes**: `.card .form-group .form-label .form-input .form-select .form-check .btn-primary .save-confirm`
**Components**:
  - Form fields (all labeled, seeded from `store.settings`):
    - Program name (text, "Meridian — Core Banking Modernization")
    - Program director (text, "Helena Voss")
    - Reporting cadence (select: Weekly / Fortnightly / Monthly — seed Fortnightly)
    - Fiscal year start (select: January / April / July — seed January)
    - RAG amber threshold, % variance (number, seed 10)
    - Email steering committee on gate decisions (checkbox, checked)
    - Show today marker on timelines (checkbox, checked)
  - **"Save preferences"** button.
**Interactions**:
  - Save → writes all values into `store.settings`, shows inline `.save-confirm` "✓ Preferences saved 30 Jul 2026, 14:05" — a deterministic demo stamp built from `todayISO` at a fixed 14:05, never the real clock — that fades in (and persists until next save); program name in the sidebar logo subtitle re-renders from the store; unchecking "Show today marker" hides the today line on both Gantt views.

## State & Data Model
One global `store` object (single source of truth) + `render()` re-run on every mutation and hashchange:
- `currentStage`: string — **derived** each render from gates: "Stage {n} — {label}" where n = (# Approved gates)+1; stage labels: 1 Mobilize, 2 Design, 3 Build & Integrate, 4 Test & Migrate, 5 Run & Realize. Seed derives to "Stage 3 — Build & Integrate".
- `todayISO`: '2026-07-30' — drives today markers and decision dates.
- `workstreams`: array[6] — {id, name, owner, rag, percentComplete, startISO, endISO, dependsOn: id[], milestones: [{label, dateISO}], activities: [{label, startISO, endISO, status}], risks: [{title, severity, owner, status}]} — full seed for all 6 as specified above.
- `gates`: array[5] — {id, name, status: 'Approved'|'In review'|'Not started', dueISO, decisionISO|null, chair, linkedWorkstreamId, approvers: [{name, role, approved}], criteria: [{label, met}], evidence: [{doc, owner, dateISO}]} — full seed for g1–g5.
- `canvasSteps`: array[12] — {id, lane: 'business'|'technology', label, kind: 'step'|'decision', delta: 'new'|'updated'|'unchanged', workstreamId, col} — seed per the Canvas page.
- `settings`: {programName, director, cadence, fyStart, amberThreshold, emailOnGate, showToday} — seeds per Settings page.
- `ui`: {selectedWorkstreamId: 'ws-core', walkthroughIndex: -1, walkthroughTimer: null, rippledIds: [], savedAt: null}.
- Actions (each mutates store then calls render): `shiftWorkstream(id, days)` (transitive dependents + linked gates), `approveGate(id)`, `sendBackGate(id)`, `toggleActivity(wsId, idx)`, `saveSettings(values)`, `selectWorkstream(id)`, walkthrough `play/next/reset`.
- Router: hashchange parser matching `#/workstream/:id` and `#/gate/:id` with a lookup; missing record → not-found card render path.

## Navigation Flows
- Sidebar items → `#/dashboard`, `#/canvas`, `#/workstreams`, `#/gates`, `#/settings` (active state; workstream/gate detail routes mark Workstreams/Gates active).
- Default route / unknown top-level hash → `#/dashboard`.
- Dashboard attention items → `#/workstream/ws-data`, `#/gate/g3`, `#/workstream/ws-pay`, `#/workstream/ws-core`, `#/gate/g2`.
- Dashboard next-gate KPI + stepper segments → `#/gate/:id`.
- Canvas node click → `#/workstream/{owning id}` (all 12 nodes wired).
- Workstreams row open → `#/workstream/:id`; breadcrumb back → `#/workstreams`.
- Workstream Detail canvas-step item → `#/canvas`.
- Gates SVG group / table row → `#/gate/:id`; breadcrumb back → `#/gates`.
- Not-found cards → back buttons to `#/workstreams` / `#/gates`.
- Propagation flows: Approve g3 → Dashboard stage chip + next-gate KPI + Gates ring colors; Shift milestone → Gantt bars/milestones + dependents ripple + Dashboard next-gate date; activity toggle → workstream % + Dashboard % complete; settings save → sidebar subtitle + today-marker visibility.

## Design Notes
- Color scheme: dark command-center — --bg #0d1420 page, --surface #16202f cards, --border #263449, --fg #e8edf5, --muted #8496ad, --accent #2dd4bf (teal) for actions/highlights/flow edges; RAG semantics green #34d399 / amber #fbbf24 / red #f87171, blue #60a5fa for informational badges.
- Typography: system UI sans stack ("Inter", -apple-system, "Segoe UI", sans-serif); page titles 20px/600, card titles 13px uppercase tracking-wide muted, KPI values 28px/700 with `font-variant-numeric: tabular-nums`; SVG labels 12px.
- Density: medium — 16px card padding, 12–16px grid gaps, 40px sidebar item height; Gantt rows 44px; diagrams get generous canvas cards with horizontal scroll (`.canvas-wrap`) so nothing squashes below ~1100px content width.
- Motion: `.flow-edge` dash animation (1.4s linear infinite), `.rippled` amber pulse keyframe (1.5s), walkthrough highlight transition 250ms, `.save-confirm` fade-in 300ms.
</spec>

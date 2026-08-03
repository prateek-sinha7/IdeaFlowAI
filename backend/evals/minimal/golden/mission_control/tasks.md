<tasks>
## Task 1: HTML Shell & Navigation Chrome
**Goal**: Build the complete HTML skeleton for Mission Control — Meridian Program Transformation Suite: DS-mapped `:root` tokens, full "Meridian Ops" CSS class system on top of the blank-canvas scaffold, sidebar chrome, hash router, global store, and empty page sections for all 7 pages.
**DS Token Mapping**:
- --bg: #0d1420
- --fg: #e8edf5
- --accent: #2dd4bf
- --surface: #16202f
- --border: #263449
- --muted: #8496ad
- Additional semantics: --green: #34d399, --amber: #fbbf24, --red: #f87171, --blue: #60a5fa
**Template Classes**: No template (blank canvas) — implement the spec's full "Meridian Ops" class system extending the scaffold:
- Chrome: `.app` (CSS grid: 232px sidebar + 1fr main), `.sidebar`, `.sidebar-logo` (title "Mission Control" + subtitle bound to `store.settings.programName`), `.nav-item`, `.nav-item.active`, `.main`, `.page-header`, `.page-title`, `.page-sub`, `.crumb`
- Layout: `.grid-2`, `.grid-3`, `.grid-4` (responsive grids, 16px gap), `.row` (flex, gap 12px), `.section` (margin-bottom 24px)
- Cards/KPI: `.card` (surface bg, 1px border var(--border), 10px radius, 16px padding), `.card-title` (13px uppercase tracking-wide muted), `.kpi-tile`, `.kpi-value` (28px/700, `font-variant-numeric: tabular-nums`), `.kpi-label`, `.kpi-delta` with `.up` (green) / `.down` (red)
- Status: `.badge` + `.badge-green .badge-amber .badge-red .badge-blue .badge-gray`; `.chip` (pill, accent-tinted); `.delta-badge` + `.delta-new` (teal) / `.delta-updated` (amber) / `.delta-unchanged` (gray)
- Tables/lists: `.table`, `.table-wrap` (overflow-x auto), `.list`, `.list-item` (hover surface, cursor pointer)
- Forms/buttons: `.btn`, `.btn-primary`, `.btn-danger`, `.btn-ghost`, `.form-group`, `.form-label`, `.form-input`, `.form-select`, `.form-check`, `.save-confirm` (green, 300ms fade-in)
- Diagrams: `.canvas-wrap` (overflow-x auto), `.gantt` (grid rows, 44px row height), `.gantt-bar` (absolute-positioned rounded bar), `.gantt-bar.rippled` (amber outline pulse keyframe 1.5s), `.today-line`, `.milestone` (rotated 45° square), `.legend`, `.legend-item`, `.checklist`, `.check-item` (`.done .doing .todo`), `.not-found-card` (centered card, icon + back link)
- SVG/animation CSS: `.flow-edge` (stroke-dasharray: 6 6; animation dashflow 1.4s linear infinite) with `@keyframes dashflow { to { stroke-dashoffset: -24 } }`; `.gate-current` (thick accent ring + soft glow, 250ms transition)
- Typography: font-family "Inter", -apple-system, "Segoe UI", sans-serif; page titles 20px/600; SVG labels 12px
**Chrome**: Fixed left sidebar with `.sidebar-logo` ("Mission Control" + program-name subtitle from store) and 5 `.nav-item` links: Dashboard → `#/dashboard`, Program Canvas → `#/canvas`, Workstreams → `#/workstreams`, Gates → `#/gates`, Settings → `#/settings`. Active-state logic: `#/workstream/:id` marks Workstreams active; `#/gate/:id` marks Gates active.
**Pages**: dashboard, canvas, workstreams, workstream-detail, gates, gate-detail, settings — one empty `<section data-page="{id}" class="page">` each; dashboard section gets `is-active`.
**Routes**: { dashboard: '/dashboard', canvas: '/canvas', workstreams: '/workstreams', 'workstream-detail': '/workstream/:id', gates: '/gates', 'gate-detail': '/gate/:id', settings: '/settings' } — use the MANDATORY ROUTER TEMPLATE; extend the hash parser to match `#/workstream/:id` and `#/gate/:id` (param captured into `store.ui` / passed to render); default and unknown top-level hashes → `#/dashboard`. ROUTER RULE: `data-page` only on `<section>` elements, never on `<a>`.
**Store (global single source of truth, defined in the shell `<script>`)**:
- `todayISO: '2026-07-30'`
- `workstreams`: array of 6 full records {id, name, owner, rag, percentComplete, startISO, endISO, dependsOn[], milestones[{label,dateISO}], activities[{label,startISO,endISO,status}], risks[{title,severity,owner,status}]}:
  1. ws-core "Core Ledger Replatform", Priya Raman, amber, 58, 2026-02-01→2027-02-28, dependsOn [], milestone "Ledger cutover rehearsal" 2026-10-30; activities: Design ledger target architecture (2026-02-01→2026-04-30, done), Build ledger services (2026-04-01→2026-09-30, doing), Integrate GL feeds (2026-06-01→2026-11-30, doing), Cutover rehearsal (2026-10-01→2026-11-30, todo), Production cutover (2027-01-01→2027-02-28, todo); risks: "GL mapping gaps for suspense accounts"/High/P. Raman/Open, "Cutover window exceeds 48h"/High/M. Chen/Open, "Vendor SME availability in Q4"/Medium/P. Raman/Mitigating, "Interest accrual rounding variance"/Medium/L. Novak/Open, "Dual-run cost overrun"/Low/Finance TMO/Closed
  2. ws-pay "Payments Migration", Daniel Okafor, amber, 47, 2026-03-01→2027-03-31, dependsOn [ws-core], milestone "Faster Payments live proving" 2026-12-15; 4–5 realistic activities (e.g. Payments hub design done, Scheme certification build doing, Faster Payments proving todo, Legacy payments decommission todo); ≥4 risks including "Temenos T24 licence renewal unsigned"/High/D. Okafor/Open (2 Open total)
  3. ws-data "Data Migration & Reconciliation", Sofia Marchetti, red, 38, 2026-04-01→2027-04-30, dependsOn [ws-core], milestone "Full reconciliation pass" 2027-01-20; 4–5 activities; ≥4 risks including "Reconciliation defect backlog growing"/High/S. Marchetti/Open (2 Open)
  4. ws-chan "Channels & API Enablement", James Whitfield, green, 72, 2026-01-01→2026-11-30, dependsOn [], milestone "Open Banking APIs live" 2026-09-01; 4–5 activities; ≥4 risks (0–1 Open)
  5. ws-risk "Risk, Compliance & Controls", Amara Nwosu, green, 61, 2026-02-01→2027-05-31, dependsOn [ws-pay], milestone "Reg sign-off pack submitted" 2027-02-28; 4–5 activities; ≥4 risks
  6. ws-people "Operating Model & People Transition", Tomás Herrera, green, 46, 2026-05-01→2027-06-30, dependsOn [ws-data], milestone "New TOM go-live" 2027-04-01; 4–5 activities; ≥4 risks
  Seed risk statuses so total Open across all workstreams = 7.
- `gates`: array of 5 full records {id, name, status, dueISO, decisionISO, chair, linkedWorkstreamId, approvers[3 {name,role,approved}], criteria[≥5 {label,met}], evidence[≥4 {doc,owner,dateISO}]}: g1 "G1 — Mobilization Complete" Approved 2025-12-20; g2 "G2 — Design Complete" Approved 2026-04-18; g3 "G3 — Build Complete" In review, due 2026-09-12, linked ws-core, chair Helena Voss, approvers Helena Voss (Program Director), Marcus Bell (CIO), Ingrid Salomon (Chief Risk Officer), criteria exactly the 7 g3 items from the spec (5 met / 2 unmet), evidence the 5 spec items; g4 "G4 — Migration Rehearsal Passed" Not started, due 2027-01-30, linked ws-data; g5 "G5 — Benefits Realized" Not started, due 2027-06-15, linked ws-people. Every gate fully seeded (approvers, ≥5 criteria, ≥4 evidence).
- `canvasSteps`: array of 12 {id, lane: 'business'|'technology', label, kind: 'step'|'decision', delta, workstreamId, col} — business: Customer Onboarding (updated, ws-chan), Account Servicing (updated, ws-core), "Straight-through?" decision (ws-chan), Payments Initiation (updated, ws-pay), Disputes & Complaints (unchanged, ws-people), Collections (unchanged, ws-people); technology: Channel APIs (new, ws-chan), "Legacy or Meridian?" decision (ws-core), Core Ledger (Meridian) (updated, ws-core), Payments Hub (new, ws-pay), Data & Reporting Platform (new, ws-data), Batch Decommission (unchanged + retiring flag, ws-data)
- `settings`: {programName: "Meridian — Core Banking Modernization", director: "Helena Voss", cadence: "Fortnightly", fyStart: "January", amberThreshold: 10, emailOnGate: true, showToday: true}
- `ui`: {selectedWorkstreamId: 'ws-core', walkthroughIndex: -1, walkthroughTimer: null, rippledIds: [], savedAt: null}
- Derived helper `currentStage()`: n = (# gates with status 'Approved') + 1; labels [1 Mobilize, 2 Design, 3 Build & Integrate, 4 Test & Migrate, 5 Run & Realize] → "Stage {n} — {label}" (seed derives "Stage 3 — Build & Integrate").
- Store actions (each mutates then calls `render()`): `shiftWorkstream(id, days)`, `approveGate(id)`, `sendBackGate(id)`, `toggleActivity(wsId, idx)`, `saveSettings(values)`, `selectWorkstream(id)`, `walkthroughPlay()/walkthroughNext()/walkthroughReset()`; date helpers `addDays(iso, n)` and `fmtDate(iso)` ("12 Sep 2026" style); `render()` re-runs on every mutation and on hashchange, clearing `walkthroughTimer` on navigation.
**Script handlers needed**: [router/parseHash, render, currentStage, addDays, fmtDate, all store actions above]

## Task 2: Dashboard Page (`#/dashboard`)
**Goal**: Fill the dashboard section with computed executive KPIs, stage chip, attention list, and gate stepper — all derived from the store on every render, never hardcoded.
**Layout**: `.page-header` with `.chip` + `.grid-4` KPI row + `.grid-2` (attention list card | gate progress card)
**Template Classes**: `.page-header .page-title .chip .grid-4 .kpi-tile .kpi-value .kpi-label .kpi-delta .grid-2 .card .card-title .list .list-item .badge`
**Components**:
- Stage chip in header: "Current stage: " + `currentStage()` — seed "Stage 3 — Build & Integrate"; must show "Stage 4 — Test & Migrate" after g3 approval.
- KPI tiles (computed each render):
  1. "Program health": red if any ws.rag==='red', else amber if any amber, else green — seed shows "Red" with `.kpi-delta.down` "1 workstream red"
  2. "% complete": Math.round(mean of workstream percentComplete) — seed 54%
  3. "Open risks": count of risks with status 'Open' across all workstreams — seed 7
  4. "Next gate": earliest gate with status !== 'Approved' — seed "G3 — Build Complete · 12 Sep 2026"; clickable → `#/gate/{nextGateId}`; must re-render to 26 Sep 2026 after the +2-week shift and advance to G4 after g3 approval
- "Needs attention" card, `.list` of ≥5 `.list-item`s (red/amber workstreams and next pending gate computed and injected at top; each item navigates on click):
  1. "Data Migration workstream is RED — reconciliation defect backlog growing" → `#/workstream/ws-data`
  2. "G3 — Build Complete gate review due 12 Sep 2026" → `#/gate/g3`
  3. "Risk: Temenos T24 licence renewal unsigned (Payments Migration)" → `#/workstream/ws-pay`
  4. "Core Ledger Replatform milestone 'Ledger cutover rehearsal' at risk" → `#/workstream/ws-core`
  5. "G2 — Design Complete approved 18 Apr 2026 — conditions closing" → `#/gate/g2`
- "Gate progress" card: horizontal 5-segment stepper G1–G5 rendered from store gate statuses — teal filled = Approved, amber ring = In review, gray = Not started; each segment clickable → `#/gate/{id}`.
**Interactions**:
- Attention item click → `location.hash = target route`
- Next-gate KPI tile click → `#/gate/{nextGateId}`
- Stepper segment click → `#/gate/{id}`
**Script handlers needed**: [renderDashboard (computes health/%/risks/nextGate/stage from store), attention + stepper click delegation]

## Task 3: Program Canvas Page (`#/canvas`)
**Goal**: Fill the canvas section with the two-lane SVG operating-model diagram rendered from `store.canvasSteps`, with delta badges, decision diamonds, animated cross-lane flow edges, and a legend.
**Layout**: `.page-header` + legend `.row` + full-width `.card > .canvas-wrap` containing one inline `<svg>` ~1160×560
**Template Classes**: `.card .canvas-wrap .legend .legend-item .delta-badge .delta-new .delta-updated .delta-unchanged .flow-edge`
**Components**:
- SVG generated by iterating `store.canvasSteps` (positions from lane + col — business lane top, technology lane bottom, lane labels on the left), NOT hardcoded markup:
  - Business lane: Customer Onboarding → Account Servicing → ◇ "Straight-through?" → Payments Initiation → Disputes & Complaints → Collections
  - Technology lane: Channel APIs → ◇ "Legacy or Meridian?" → Core Ledger (Meridian) → Payments Hub → Data & Reporting Platform → Batch Decommission
- Step nodes: `rect rx=8` + title + owning-workstream subtitle + top-right delta badge pill — New (teal): Channel APIs, Payments Hub, Data & Reporting Platform; Updated (amber): Customer Onboarding, Account Servicing, Payments Initiation, Core Ledger; Unchanged (gray): Disputes & Complaints, Collections, Batch Decommission; Batch Decommission additionally gets a red "Retiring" sub-badge.
- Decision diamonds: `polygon` shapes for the two decisions with Yes/No branch labels.
- Connectors: solid `path` arrows with `marker-end` arrowhead within each lane; three animated dashed `.flow-edge` cross-lane arrows: Payments Initiation → Payments Hub, Account Servicing → Core Ledger, Core Ledger → Data & Reporting Platform.
- Legend row: New / Updated / Unchanged delta badge samples, decision diamond sample, animated flow-edge sample, text "click a node to open its workstream".
- Hover CSS: brighter node border + cursor pointer.
**Interactions**:
- Click any node or diamond → `#/workstream/{step.workstreamId}` (all 12 wired; e.g. Core Ledger → `#/workstream/ws-core`)
**Script handlers needed**: [renderCanvas (SVG builder from canvasSteps), node click handlers via data-ws attributes]

## Task 4: Workstreams Page (`#/workstreams`)
**Goal**: Fill the workstreams section with an 18-month Gantt of all 6 workstreams, milestones, dependency arrows, today line, row selection, and the "Shift milestone +2 weeks" ripple action.
**Layout**: `.page-header` + toolbar `.row` (selected-workstream label + shift button) + full-width Gantt `.card` + `.legend`
**Template Classes**: `.card .canvas-wrap .gantt .gantt-bar .gantt-bar.rippled .today-line .milestone .btn .btn-primary .legend .legend-item .badge`
**Components**:
- Gantt from `store.workstreams`: 18 month columns Jan 2026 – Jun 2027 with faint gridlines and month labels; one 44px row per workstream; `.gantt-bar` absolutely positioned by (date − 2026-01-01)/546-day span fraction; bar tint by RAG (green/amber/red); label + owner on/beside bar; % complete badge. Rows (from seed): ws-core Feb 26→Feb 27 amber 58% Priya Raman; ws-pay Mar 26→Mar 27 amber 47% Daniel Okafor; ws-data Apr 26→Apr 27 red 38% Sofia Marchetti; ws-chan Jan 26→Nov 26 green 72% James Whitfield; ws-risk Feb 26→May 27 green 61% Amara Nwosu; ws-people May 26→Jun 27 green 46% Tomás Herrera.
- `.milestone` diamonds positioned on each bar from `ws.milestones` (the 6 seed milestones with dates), with title tooltip "{label} · {date}".
- SVG overlay with thin dependency arrows: ws-core→ws-pay, ws-core→ws-data, ws-pay→ws-risk, ws-data→ws-people (predecessor bar end → dependent bar start).
- `.today-line`: vertical accent line at 2026-07-30 with "Today" tag — rendered only if `store.settings.showToday`.
- Toolbar: "Selected: {name}" label (default "Core Ledger Replatform") + `.btn-primary` "Shift milestone +2 weeks".
- Row click → `selectWorkstream(id)` (highlighted row + toolbar update); each row also has an "Open" chevron/name link → `#/workstream/{id}`.
- Legend: RAG colors, milestone diamond, dependency arrow, today line.
**Interactions**:
- Row click → select; Open link → `#/workstream/{id}`
- "Shift milestone +2 weeks" → `shiftWorkstream(store.ui.selectedWorkstreamId, 14)`: add 14 days to the selected workstream's endISO + all milestone dates, then transitively to every dependent workstream's startISO/endISO/milestones (dependents of dependents too), and add 14 days to `dueISO` of any non-Approved gate whose `linkedWorkstreamId` is in the affected set (g3 linked to ws-core: 12 Sep → 26 Sep 2026). Set `store.ui.rippledIds` to all moved workstream ids → re-render bars with `.rippled` amber pulse, clear rippledIds after 1500ms via setTimeout + re-render. Repeatable and cumulative; Dashboard next-gate KPI reflects the new date.
**Script handlers needed**: [renderWorkstreams (Gantt geometry, dateToPct helper), selectWorkstream, shiftWorkstream (transitive ripple + linked-gate shift + ripple timeout), row/open click delegation]

## Task 5: Workstream Detail Page (`#/workstream/:id`)
**Goal**: Fill the workstream-detail section rendered entirely from `store.workstreams` by route param — mini-Gantt, toggleable activity checklist, risks table, owned canvas steps — plus a not-found path.
**Layout**: `.page-header` (crumb + name + RAG badge + owner + % complete) + `.grid-2` of four cards
**Template Classes**: `.page-header .crumb .badge .badge-green .badge-amber .badge-red .grid-2 .card .card-title .gantt .gantt-bar .today-line .checklist .check-item .table .table-wrap .delta-badge .not-found-card .btn`
**Components** (lookup `store.workstreams.find(w => w.id === param)`; works for all 6 ids):
- Breadcrumb "Workstreams / {name}" → `#/workstreams`; header shows RAG badge, "Owner: {owner}", "{percentComplete}% complete" (recomputed live).
- Mini-Gantt card: the workstream's activities as bars across the workstream's own startISO→endISO span, colored by status (done green / doing accent / todo gray), today line at 2026-07-30 (respecting `settings.showToday`). ws-core example: Design ledger target architecture (Feb–Apr 26, done), Build ledger services (Apr–Sep 26, doing), Integrate GL feeds (Jun–Nov 26, doing), Cutover rehearsal (Oct–Nov 26, todo), Production cutover (Jan–Feb 27, todo).
- Activity checklist card: same activities as `.check-item`s (`.done .doing .todo`) with badges Done / In progress / Not started; clicking a checkbox calls `toggleActivity(wsId, idx)` — toggles done ↔ doing (todo→done on check) and recomputes this workstream's percentComplete = round(done/total × 100), propagating to the Dashboard % KPI.
- Risks table: `.table` in `.table-wrap`, columns [Risk, Severity, Owner, Status] with severity/status badges — ws-core's 5 seeded rows as specified; every workstream shows its ≥4 seeded risks; Open rows feed the Dashboard open-risk count.
- Canvas steps card: `store.canvasSteps.filter(s => s.workstreamId === id)` as `.list-item`s with label + delta badge; each → `#/canvas`.
**Interactions**:
- Checklist toggle → `toggleActivity` → store update → % propagation
- Canvas step item → `#/canvas`; breadcrumb → `#/workstreams`
- Unknown id (e.g. `#/workstream/ws-zzz`) → render `.not-found-card`: "Workstream not found — '{id}' isn't part of the Meridian program." + `.btn` "Back to Workstreams" → `#/workstreams`. Never throws.
**Script handlers needed**: [renderWorkstreamDetail(param) with not-found guard, toggleActivity, checklist click delegation]

## Task 6: Gates Page (`#/gates`)
**Goal**: Fill the gates section with the stage-gate chain SVG rendered from `store.gates`, the walkthrough player (Play / Next / Reset), and the gates summary table.
**Layout**: `.page-header` + player toolbar `.row` (buttons + step caption) + full-width chain SVG `.card > .canvas-wrap` + gates `.table` card
**Template Classes**: `.card .canvas-wrap .btn .btn-primary .btn-ghost .table .table-wrap .badge .gate-current`
**Components**:
- Chain SVG from `store.gates`: 5 gate groups left→right joined by arrow connectors. Each group = gate label above a row of 3 approver nodes (circle with avatar initials + name + role text; e.g. g3: Helena Voss — Program Director, Marcus Bell — CIO, Ingrid Salomon — Chief Risk Officer). Each cluster enclosed by a status ring `circle`/rounded rect: green solid stroke = Approved (g1, g2), amber = In review (g3), gray dashed = Not started (g4, g5) — derived from store each render so approving g3 re-rings it green and g4 amber.
- Walkthrough player toolbar: `.btn-primary` "Play" (toggles to "Pause" while running), `.btn` "Next", `.btn-ghost` "Reset", plus caption line below, e.g. "Step 2 of 5: G2 — Design Complete — approved by 3 of 3 approvers on 18 Apr 2026" (status-appropriate captions for in-review/not-started gates).
- Play: interval 1200ms stored in `store.ui.walkthroughTimer`, advances `walkthroughIndex` 0→4 applying `.gate-current` (thick teal ring + glow) to the current group; at the end clears the interval and button reverts to "Play". Next: clears any running interval (pauses) and advances one step. Reset: clears interval, sets walkthroughIndex −1, clears caption. Timer also cleared on hashchange/navigation.
- Gates table: columns [Gate, Status, Decision date / Due, Chair, Criteria met] — 5 rows from store; Criteria met computed as "{met}/{total}" (g3 seed "5/7"); status as `.badge` (green/amber/gray); row click → `#/gate/{id}`.
**Interactions**:
- Click a gate group in the SVG or a table row → `#/gate/{id}`
- Play / Next / Reset per above
**Script handlers needed**: [renderGates (chain SVG builder + table), walkthroughPlay, walkthroughNext, walkthroughReset, gate group/row click delegation]

## Task 7: Gate Detail Page (`#/gate/:id`)
**Goal**: Fill the gate-detail section rendered from `store.gates` by route param — criteria checklist, evidence list, approvers row, Approve / Send back actions with full store propagation — plus a not-found path.
**Layout**: `.page-header` (crumb + gate name + status badge + due/decision date + chair) + `.grid-2` (criteria card | evidence card) + approvers row + action bar
**Template Classes**: `.page-header .crumb .badge .grid-2 .card .card-title .checklist .check-item .list .list-item .btn .btn-primary .btn-danger .not-found-card`
**Components** (lookup `store.gates.find(g => g.id === param)`; all 5 gates fully seeded):
- Breadcrumb "Gates / {gate.name}" → `#/gates`; header: status badge (Approved green / In review amber / Not started gray), "Due {due}" or "Decided {decisionISO}", "Chair: {chair}".
- Criteria checklist card (≥5 per gate): met → green check `.check-item.done`, unmet → gray circle `.todo`. g3 seed: the exact 7 criteria from the spec (5 met, 2 unmet: "Payments hub certified against Faster Payments scheme", "Data reconciliation variance < 0.01%").
- Evidence list card (≥4 items, doc — owner — date): g3 seed: "SIT Exit Report v1.3 — QA Guild — 28 Aug 2026", "Performance Test Results — NFT Team — 25 Aug 2026", "Pen-Test Remediation Log — CISO Office — 20 Aug 2026", "Cutover Runbook v0.9 — Ops Readiness — 30 Aug 2026", "Architecture Compliance Memo — Design Authority — 15 Aug 2026".
- Approvers row: the gate's 3 approvers with name + role + per-approver badge Approved (green) / Pending (gray).
- Action bar: `.btn-primary` "Approve gate" + `.btn-danger` "Send back". For already-Approved gates (g1, g2): Approve rendered disabled as "Approved ✓", decision metadata shown, Send back hidden or disabled.
**Interactions**:
- Approve → `approveGate(id)`: status='Approved', decisionISO='2026-07-30', all approvers approved=true, first gate with status 'Not started' set to 'In review'; derived `currentStage()` advances → Dashboard chip ("Stage 4 — Test & Migrate" after g3), next-gate KPI advances to G4, Gates chain ring turns green. Button re-renders disabled "Approved ✓"; inline green confirmation "Gate approved — program advanced to {new stage}".
- Send back → `sendBackGate(id)`: status stays/becomes 'In review'; inline amber note "Sent back to workstream lead {owner of gate.linkedWorkstreamId workstream} with conditions"; appends criteria item {label: "Address steering-committee conditions", met: false} → Gates-table "Criteria met" count updates (g3 → 5/8).
- Unknown id (e.g. `#/gate/g9`) → `.not-found-card`: "Gate not found — 'g9' isn't in the Meridian stage-gate plan." + "Back to Gates" `.btn` → `#/gates`. Never throws.
**Script handlers needed**: [renderGateDetail(param) with not-found guard, approveGate, sendBackGate, action button delegation]

## Task 8: Settings Page (`#/settings`)
**Goal**: Fill the settings section with the preferences form seeded from `store.settings`, with save propagation to the sidebar subtitle and today-marker visibility.
**Layout**: `.page-header` + single centered `.card` form, max-width 560px
**Template Classes**: `.card .form-group .form-label .form-input .form-select .form-check .btn-primary .save-confirm`
**Components** (values seeded from `store.settings` on every render):
- Program name (text, "Meridian — Core Banking Modernization")
- Program director (text, "Helena Voss")
- Reporting cadence (select: Weekly / Fortnightly / Monthly — selected Fortnightly)
- Fiscal year start (select: January / April / July — selected January)
- RAG amber threshold, % variance (number, 10)
- Email steering committee on gate decisions (checkbox, checked)
- Show today marker on timelines (checkbox, checked)
- `.btn-primary` "Save preferences" + `.save-confirm` region (hidden until saved)
**Interactions**:
- Save → `saveSettings(values)`: read all 7 fields, write into `store.settings`, set `store.ui.savedAt`, re-render → `.save-confirm` shows "✓ Preferences saved 30 Jul 2026, 14:05" with 300ms fade-in, persisting until the next save; sidebar logo subtitle re-renders from `store.settings.programName`; unchecking "Show today marker" hides `.today-line` on both the Workstreams Gantt and the Workstream Detail mini-Gantt.
**Script handlers needed**: [renderSettings, saveSettings (form read + store write + savedAt)]

## Task 9: Final Wiring & Validation
**Goal**: Validate all pages have content, verify DS tokens, fix navigation, and confirm every propagation flow works.
**Checks**:
- All 7 `<section data-page>` sections have complete content (no empty sections, no placeholder text)
- `:root` tokens exactly match the Meridian Ops DS: --bg #0d1420, --fg #e8edf5, --accent #2dd4bf, --surface #16202f, --border #263449, --muted #8496ad (+ green/amber/red/blue semantics)
- All nav/anchor links use `href="#/path"` format (fix any `href="#page"`); `data-page` only on `<section>` elements
- Routes map complete including the `#/workstream/:id` and `#/gate/:id` param routes; unknown top-level hash → dashboard; unknown workstream/gate ids render `.not-found-card` without console errors
- Dashboard section has `class="is-active"` on load; sidebar active state correct on all 7 routes (detail routes highlight Workstreams/Gates)
- All buttons have handlers: shift button, Play/Next/Reset, Approve/Send back, Save preferences, checklist toggles, all stepper/attention/canvas/table navigation clicks
- Propagation flows verified end-to-end: approveGate('g3') → stage chip "Stage 4 — Test & Migrate" + next-gate KPI → G4 + g3 ring green/g4 amber; shiftWorkstream('ws-core',14) → ws-pay/ws-data/ws-risk/ws-people ripple + g3 due 26 Sep 2026 on Dashboard; toggleActivity → workstream % + Dashboard % complete; saveSettings → sidebar subtitle + today-line visibility on both Gantts
- Walkthrough timer cleared on Reset and on navigation (no orphan intervals)
- Seed-derived values render correctly: health Red, 54% complete, 7 open risks, next gate "G3 — Build Complete · 12 Sep 2026", g3 criteria "5/7"
</tasks>

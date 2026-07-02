---
title: Workstream B — Revision Families FE — UI Design Contract
status: draft
phase: Workstream B (revision families FE)
source_plan: .planning/REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md (§5 deliverables 3–6, §7, §8)
discipline: REUSE-FIRST (Phase 20/21/22 UI-SPEC mandate — net-new visual language is a DEFECT)
date: 2026-07-02
---

# Workstream B — Revision Families FE — UI Design Contract

This contract governs the four NEW visual surfaces B2+B3 build (plan §5 deliverables 3, 4, 5, 6).
Every node below names its **exact existing analog with `file:line`**. There is **no net-new visual
language** — chips, pills, status dots, cards, expansion rows, dropdowns, amber notices, and the
cross-fade transition all already exist in this codebase and are inherited verbatim. If an executor
finds themselves inventing a hex value, a radius, a font size, or a motion curve, that is a defect —
stop and cite the analog instead.

All file:line anchors below were read from source on 2026-07-02.

---

## 0. Established design tokens (inherited — do NOT redefine)

These are the *existing* conventions read out of the real components. Reuse them exactly; declare no new ones.

### Color (60 / 30 / 10)
- **60% dominant surface:** `#f5f5f0` warm off-white page background — `WorkflowHistory.tsx:351,758`, `FilesTab.tsx:447`.
- **30% secondary surfaces:** `bg-white` panels + `border-gray-200` / `border-gray-100` dividers — `WorkflowHistory.tsx:353,569`, `PreviewPanel.tsx:522,524`.
- **10% accent (RESERVED):** navy `#1B2A4A` (hover `#2a3d5e`). Reserved EXCLUSIVELY for: the active/selected control, primary CTAs, and the "current version" fill. Anchors: active filter tab `WorkflowHistory.tsx:798`, active preview tab `PreviewPanel.tsx:561`, active toggle pill `PrototypePreview.tsx:533,545`, Send/approve buttons `WorkflowHistory.tsx:529`, `ReviewGatePanel.tsx:406`.
- **Semantic status colors (inherited maps — never invent a new one):**
  - completed / done → `text-emerald-700 bg-emerald-50 border-emerald-100` (badge) — `WorkflowHistory.tsx:370,900`; dot `bg-emerald-400` — `PrototypePreview.tsx:509`.
  - cancelled / degraded / caution → `text-amber-700 bg-amber-50 border-amber-100`; dot `bg-amber-400` — `WorkflowHistory.tsx:904`, `PrototypePreview.tsx:538`, `ReviewGatePanel.tsx:398`.
  - failed → `text-gray-500 bg-gray-100 border-gray-200` (history convention) — `WorkflowHistory.tsx:908`; red reserved for destructive only (`text-red-600 hover:bg-red-50` — `WorkflowHistory.tsx:937`).
  - running / revising → `text-blue-*` + `Loader2 animate-spin` — `Sidebar.tsx:66-73`, `WaveTreePanel.tsx:51-59`.
  - Canonical status→color maps to import from, NOT re-derive: `Sidebar.tsx:55-73` (`STATUS_ICON`/`STATUS_COLOR`), `WaveTreePanel.tsx:47-63` (`STATUS_STYLE`/`StatusBadge`).

### Spacing
- 4-based scale already in use: `gap-1 / 1.5 / 2 / 3`, `px-3 py-1.5`, `px-4 py-3`, `px-5/6`. No exceptions needed for this phase. Anchors: `WorkflowHistory.tsx:571,874`, `PreviewPanel.tsx:524,551`.

### Typography (inherited — 3 practical sizes + weights)
- Sizes in use: `text-[13px]` row title, `text-[11px]` control/body, `text-[10px]` meta, `text-[9px]` micro-badge — `WorkflowHistory.tsx:883-885,803`. Chips/pills use `text-[10px]`/`text-[9px]` `font-medium`/`font-semibold`.
- Weights: `font-semibold` (600) for titles/active, `font-medium` (500) for controls, regular (400) for meta. Line clamp/`truncate` for previews.

### Radius
- Pills/badges: `rounded-full` (status) or `rounded` (count) — `WorkflowHistory.tsx:900,803`. Cards/rows: `rounded-xl` — `WorkflowHistory.tsx:420`, `FilesTab.tsx:420`. Controls: `rounded-md`/`rounded-lg` — `PreviewPanel.tsx:552`.

### Motion idioms (inherited — reuse, do not author new curves)
- **Tab/panel cross-fade:** `AnimatePresence mode="wait"` + `motion.div` `initial/animate/exit opacity` `transition={{duration:0.15}}` — `PreviewPanel.tsx:586-594`. **This is THE version-switch transition.**
- **List row entrance:** `motion.div initial={{opacity:0}} animate={{opacity:1}} transition={{delay: idx*0.02}}` — `WorkflowHistory.tsx:868-872`; file row `y:6, delay idx*0.03` — `FilesTab.tsx:415-419`.
- **Dropdown open:** `motion.div initial={{opacity:0,scale:0.95,y:-4}} animate={{...1,0}} exit` `transition={{duration:0.1}}` inside `AnimatePresence`, panel `absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px]`, outside-click catcher `fixed inset-0 z-10` — `WorkflowHistory.tsx:925-944,961-963`.
- **Expand chevron rotate:** `ChevronRight ... group-open:rotate-90 transition-transform` (native `<details>`) — `WorkflowHistory.tsx:448`; or `ChevronDown ... rotate-180` — `AgentThinkingTab.tsx:164`.
- **Pulse / attention:** `animate-pulse` on the accent element — `PlannerCard` `AgentThinkingTab.tsx:123,163`. **This is THE "pill ticks v1→v2" pulse** — no new keyframes.

### Non-goals (apply to ALL four surfaces)
- No new hex values, gradients, radii, font sizes, shadows, or motion curves.
- No new component library, no new icon set (lucide-react only — already imported).
- No client-side family grouping logic beyond grouping on the server-supplied `root_run_id` / `/family` payload (plan D7).
- No workflow-name branching (SC-001) — key on `parent_run_id` / `revision_index` / the generic `_revision` suffix only.

---

## Surface 1 — History family grouping (deliverable 3)

**Where:** `WorkflowHistory.tsx` LIST VIEW, replacing the flat `filteredRuns.map` at `:862-951`.
**Data:** group `runs` by the plain `rootRunId` field (from Workstream A, normalized onto FE `WorkflowRun`). One card per family root.

### Analog
- **Family root card** clones the existing run row: `WorkflowHistory.tsx:867-948` (`motion.div` flex row, `w-9 h-9 rounded-xl bg-gray-100` icon, title `text-[13px] font-semibold`, meta line `text-[10px] text-gray-400`, status badge, `ChevronRight`).
- **"v{N}" count pill** clones the filter-tab count pill: `WorkflowHistory.tsx:803` — `text-[9px] font-semibold px-1 rounded bg-gray-200 text-gray-500`.
- **Latest status dot / badge** clones the status badge block `WorkflowHistory.tsx:899-915` (reuse the badge for the family's latest member).
- **Expandable version rows** clone the native `<details>/<summary>` agent-list expander `WorkflowHistory.tsx:420-455` (chevron rotate `:448`) OR the row-entrance `motion.div` (`:868-872`) for the indented children.
- **Version status dots** in child rows use `w-1.5 h-1.5 rounded-full bg-emerald-400|bg-amber-400` — `PrototypePreview.tsx:509,538`, colored via `Sidebar.tsx:66-73` map.

### Layout & states
- **Single-member family (no revisions):** render EXACTLY the current flat row unchanged (no pill, no expander). A family of one must be visually indistinguishable from today's list — zero regression.
- **Multi-member family — collapsed (default):** the root card row shows the family title, the type meta label, latest-member timestamp, a **"v{N}" count pill** (N = member count) beside the latest status badge, and a chevron.
  - hover: inherit `hover:bg-gray-50 transition-colors group` (`:874`); menu button fades in `opacity-0 group-hover:opacity-100` (`:921`).
- **Expanded:** chevron rotates (`group-open:rotate-90`); reveals indented child rows (indent via `pl-8`/`pl-12`, mirroring `PlannerCard` `pl-8` `AgentThinkingTab.tsx:119`). Each child row: a **v-chip** ("v1", "v2" … — count-pill style `:803`), title/timestamp meta (`formatDate` `:99`), a status dot, and — for revision members — the microcopy **"↳ revises v{n}"** in `text-[10px] text-gray-400` (n = 1-based index of the parent within the family). Clicking a child row calls the existing `handleSelectRun(childRun)` (`:151`).
- **loading:** reuse the existing skeleton block unchanged — `WorkflowHistory.tsx:814-856`.
- **empty (no runs):** reuse the existing empty state unchanged — `WorkflowHistory.tsx:857-861`.

### Interaction
- Clicking the collapsed root card: default action opens the **latest** member's detail (current `handleSelectRun` semantics) OR toggles expansion — pick one and be consistent; recommendation: chevron toggles expansion, clicking the card body opens latest (matches current row = open-detail behavior).
- Filter tabs (`:787-808`) and search (`:775-784`) operate on the family root (match if ANY member matches) — reuse existing `filteredRuns` predicate, applied post-grouping.

### A11y
- Expander is a real `<button>`/`<summary>` with `aria-expanded`; icon-only chevron carries `aria-label={expanded ? "Collapse versions" : "Show versions"}`.
- Count pill has `aria-label="{N} versions"`.
- Child rows are keyboard-focusable and Enter-activatable (reuse row semantics).

### UI-checkable acceptance
- [ ] A 1-run family renders byte-for-byte like today's flat row (no pill/expander).
- [ ] A multi-run family renders ONE root card with a "v{N}" pill using class `text-[9px] font-semibold px-1 rounded bg-gray-200 text-gray-500`.
- [ ] Expanding shows indented child rows each with a v-chip, status dot, and "↳ revises v{n}" microcopy on revision members.
- [ ] Status dot/badge colors come from the inherited emerald/amber/gray/blue maps — no new color literals.
- [ ] Skeleton + empty states are the unchanged existing blocks.

---

## Surface 2 — Detail version timeline (deliverable 4)

**Where:** `WorkflowHistory.tsx` DETAIL VIEW, a NEW chips row inserted ABOVE the existing tab bar at `:570-621` (between the tab-bar container and the agent-sidebar; place it as a full-width strip directly above `:571`).
**Data:** `getRunFamily(token, selectedRun.id)` → `{root_id, members:[{id,type,title,status,revision_index,parent_run_id,created_at,...}]}` (plan §4.3).

### Analog
- **Version chips row** clones the existing tab-bar pill group `PreviewPanel.tsx:552-568` (`flex gap-0.5 bg-gray-100 rounded-md p-0.5`) OR the detail tab buttons `WorkflowHistory.tsx:573-585`.
  - **active version = filled:** `bg-[#1B2A4A] text-white` (active-filter analog `WorkflowHistory.tsx:798`) — the accent-reserved fill.
  - **sibling versions = ghost:** `text-gray-500 hover:text-gray-700` / `text-gray-400 hover:text-gray-700` (inactive tab analog `PreviewPanel.tsx:561`, `WorkflowHistory.tsx:580`).
  - each chip carries a **status dot** (`w-1.5 h-1.5 rounded-full` + inherited color map).
- **Context line beneath** ("↳ Revises v{n-1} — '{instruction preview}'") clones the planner subtitle `text-[10px] text-gray-400 truncate` — `AgentThinkingTab.tsx:151-153`.
- **Cross-fade of the whole detail surface** clones the `AnimatePresence mode="wait"` opacity transition — `PreviewPanel.tsx:586-594`.

### Layout & states
- **chips row:** `flex items-center gap-1 px-5 py-2 border-b border-gray-100 bg-white` (mirrors the tab-bar container `:571`). Chips ordered by `revision_index` ASC: `v1  v2  v3 …`.
  - **default (sibling):** ghost chip `text-[11px] font-medium px-3 py-1.5 rounded-md` + status dot.
  - **hover (sibling):** `hover:text-gray-700` (+ subtle `hover:bg-gray-50` allowed, matches tab hover).
  - **active (current):** filled `bg-[#1B2A4A] text-white`.
  - **loading (switching):** while `getWorkflow(memberId)` is in flight, show the existing detail spinner `Loader2 h-5 w-5 animate-spin text-gray-300` (`:626-628`) over the content region; the chip being switched-to may show its own inline `Loader2` (reuse `:627`).
  - **empty (single-member / `/family` returns 1):** render NO chips row at all (a family of one is just a run — no version affordance). This is the same "hide when not a family" rule as Surface 3.
- **context line:** shown only for revision members: `↳ Revises v{n-1} — '{instructionPreview}'`, single line, `truncate`. `instructionPreview` source: see **Revision-instruction display** section below.
- **switching a version:** set `selectedRun` to the chosen member and load it via the EXISTING `getWorkflow(token, member.id)` path (`:163`) — Preview / Files / Thinking / Audit all re-render from the new `selectedRun`/`selectedOutput`, wrapped so the content region cross-fades via `AnimatePresence mode="wait"` keyed on `selectedRun.id`. It MUST feel like one workflow being versioned, not a navigation.

### A11y (plan §8 — MANDATORY)
- The chips row is a **`role="radiogroup"`** with `aria-label="Workflow versions"`. Each chip is **`role="radio"`** with `aria-checked={isActive}` and `aria-label="Version {n}{, revises version m}{, status}"`.
- **Keyboard nav:** Arrow Left/Right (and Up/Down) move selection between versions; Enter/Space activates; roving `tabIndex` (active chip `tabIndex=0`, others `-1`). (No existing radiogroup in the codebase — the ARIA wiring is net-new *behavior*, but the *visual* is 100% the inherited pill group; this is not net-new visual language.)
- **Managed focus on switch:** after a version switch completes, move focus to the newly active chip (or the detail region heading) so keyboard users are not stranded.
- Status dot is decorative (`aria-hidden`); status is conveyed in the chip's `aria-label`.

### UI-checkable acceptance
- [ ] Chips row appears only when `/family` has ≥2 members; ordered v1→vN.
- [ ] Active chip is `bg-[#1B2A4A] text-white`; siblings are ghost; each has a status dot from the inherited map.
- [ ] Selecting a sibling loads it via `getWorkflow` and cross-fades Preview/Files/Thinking/Audit together via `AnimatePresence mode="wait"` (duration 0.15) — no full remount/navigation flash.
- [ ] Revision members show "↳ Revises v{n-1} — '{preview}'" in `text-[10px] text-gray-400 truncate`.
- [ ] `role="radiogroup"`/`role="radio"`/`aria-checked` present; Arrow-key nav works; focus lands on the active chip after switch.

---

## Surface 3 — Live version chip (deliverable 5)

**Where:** `PreviewPanel.tsx` header, in the right-side control cluster beside Copy/Collapse at `:528-547` (insert the chip as the first control in the `flex items-center gap-1` group, before the Copy button).
**Data:** fetch `getRunFamily(token, contentSourceRunId)` once `contentSourceRunId` resolves (live `pipeline_complete` / reopen) and re-fetch after a revision completes. Show the chip ONLY when the family has ≥2 members (the on-screen content belongs to a family).

### Analog
- **"v{n} ▾" pill** clones the PrototypePreview browser-chrome toggle pill `PrototypePreview.tsx:529-539`: `flex h-6 items-center gap-1 rounded px-1.5 text-[10px] font-medium`, idle `text-gray-400 hover:bg-gray-100 hover:text-gray-700`, open/active `bg-[#1B2A4A] text-white`, with a trailing chevron (`ChevronDown` `AgentThinkingTab.tsx:164`).
- **Dropdown list of versions** clones the row-menu dropdown `WorkflowHistory.tsx:925-944` (`motion.div` scale-in, `absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px]`) + outside-click catcher `fixed inset-0 z-10` (`:961-963`). Each item is a version row (v-chip + status dot + timestamp), active item highlighted `bg-gray-100 text-gray-900` (active-tab analog).
- **Read-only amber banner** clones the ReviewGatePanel amber notice `ReviewGatePanel.tsx:398-403`: `flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2` + `text-[10px] text-amber-700`, leading amber icon (`Sparkles`/`AlertTriangle` `h-3.5 w-3.5 text-amber-600`). Placed as a slim strip directly under the PreviewPanel header (`:548`), above the tab bar (`:550`).
- **"pill ticks v1→v2" pulse** clones `animate-pulse` on the accent pill — `AgentThinkingTab.tsx:123,163`. Apply `animate-pulse` to the chip for ~1–2 render cycles when `revision_index` increments, then remove.
- **"tweaks/older" dot** on the chip when viewing a non-latest version clones the amber sub-dot `ml-0.5 h-1.5 w-1.5 rounded-full bg-amber-400` — `PrototypePreview.tsx:538`.

### Layout & states
- **hidden:** default. Chip absent when `contentSourceRunId` is unset OR `/family` has <2 members.
- **default (latest version on screen):** compact `v{n} ▾` pill, idle styling, no banner.
- **hover:** `hover:bg-gray-100 hover:text-gray-700` (inherited).
- **open (dropdown):** pill goes `bg-[#1B2A4A] text-white`; dropdown lists all versions (latest first or v1→vN — match Surface 2 ordering), active row highlighted, each row selectable.
- **viewing older version:** pill shows the amber sub-dot; the amber read-only banner appears: **"Viewing v{k} (read-only) — Back to latest →"**. The "Back to latest →" is a text button (link-style, `text-amber-700 font-medium`, reuse the amber palette) that reloads the latest member into the panel.
- **revision just completed:** pill label ticks `v{n}` → `v{n+1}` with a one-shot `animate-pulse`; family is re-fetched.
- **loading (family fetch / switch):** inline `Loader2 h-3.5 w-3.5 animate-spin` in place of the chevron (reuse `Loader2` spinner idiom, e.g. `WorkflowHistory.tsx:627`).

### Interaction
- Selecting a version from the dropdown swaps the on-screen content to that member (live surface). Selecting a non-latest → read-only banner shows and revise affordances are suppressed for that view (read-only). "Back to latest →" clears the read-only state.
- Dropdown closes on outside click (`fixed inset-0 z-10` catcher) and on Escape.

### A11y (plan §8)
- Chip is a `<button>` with `aria-haspopup="listbox"`, `aria-expanded`, and `aria-label="Current version v{n}, choose version"`. Icon-only chevron is inside the labelled button (no separate icon-only control).
- Dropdown is `role="listbox"`; items `role="option"` with `aria-selected`. Arrow-key nav + Enter to select + Escape to close; focus returns to the chip on close.
- Amber banner: `role="status"` (polite) so the read-only context is announced; "Back to latest" is a real focusable button with a text label.
- The pulse is purely visual (`aria-hidden` decoration) — the version change is announced via the updated `aria-label`.

### UI-checkable acceptance
- [ ] Chip renders only when on-screen content belongs to a ≥2-member family; hidden otherwise.
- [ ] Chip uses the `PrototypePreview` toggle-pill classes (`h-6 rounded px-1.5 text-[10px] font-medium`, active `bg-[#1B2A4A] text-white`) — no new pill styling.
- [ ] Dropdown uses the `WorkflowHistory` row-menu classes (`absolute right-0 top-8 z-20 … rounded-lg shadow-lg min-w-[120px]`) + `fixed inset-0 z-10` outside-click catcher.
- [ ] Viewing an older version shows the amber `bg-amber-50 border-amber-200 text-amber-700` banner with "Back to latest →"; revise actions suppressed.
- [ ] On revision-complete the pill label increments and pulses via `animate-pulse` (no custom keyframes).
- [ ] `aria-haspopup`/`aria-expanded`/`role="listbox"`/`role="option"` present; Escape closes; focus returns to chip.

---

## Surface 4 — Base-version Files section (deliverable 6)

**Where:** `FilesTab.tsx`, a NEW collapsed section rendered when `workflowType` ends in `_revision` (generic suffix check — SC-001, no name branch) and a `parentRunId` is available. Insert in the non-app-builder layout after the "Final output" / "Agent outputs" sections (`:500-525`), and analogously in the app-builder layout.
**Data:** lazy — on first expand, call `getWorkflow(token, parentRunId)` and derive its files with the SAME parsing already in `FilesTab` (reuse `renderFileRow` + the file-derivation memos).

### Analog
- **Section header** clones `SectionHeader` `FilesTab.tsx:152-159` (`text-[10px] uppercase tracking-wider text-gray-400 font-semibold` + count chip `text-[9px] bg-gray-100 px-1.5 py-0.5 rounded`) — used with label **"From v{n-1}"**. The plain uppercase label variant `:506,514` is also acceptable.
- **Collapse/expand affordance** clones the native `<details>`/chevron expander `WorkflowHistory.tsx:420-455` (chevron `group-open:rotate-90` `:448`) — or a controlled button with `ChevronDown rotate-180` (`AgentThinkingTab.tsx:164`).
- **Each base file row** clones `renderFileRow` `FilesTab.tsx:412-444` VERBATIM (`rounded-xl border border-gray-200 bg-white px-4 py-3`, `w-9 h-9 rounded-lg bg-gray-100` icon, name `text-[12px] font-semibold`, meta `text-[10px] text-gray-400`, download button). No new row shape.
- **loading (lazy fetch):** reuse the row-level spinner idiom `span h-3.5 w-3.5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin` (`FilesTab.tsx:438`) or `Loader2 animate-spin`.
- **empty (parent has no files):** reuse the muted empty copy pattern `text-sm text-gray-400` / `text-[11px] text-gray-400` — `FilesTab.tsx:404-406`.

### Layout & states
- **collapsed (default):** a single `SectionHeader`-style row labelled **"From v{n-1}"** with a chevron; body hidden; parent files NOT yet fetched.
- **hover:** header row `hover:bg-gray-50` (inherited).
- **expanded — loading:** chevron rotated; body shows the spinner idiom while `getWorkflow(parentId)` resolves.
- **expanded — loaded:** body renders the parent run's files via `renderFileRow`, each row a normal downloadable `FileItem`. A caption `text-[10px] text-gray-400` (like `:479,517`) reads e.g. "Files from the previous version (v{n-1}) this revision was based on."
- **expanded — empty:** "No files in the base version." in `text-[10px] text-gray-400`.
- **not a revision / no parent:** section absent entirely.

### A11y
- Section toggle is a real `<button>`/`<summary>` with `aria-expanded` and `aria-label="From version {n-1}"`; icon-only chevron carries an `aria-label`.
- Lazy-load loading state announced via `aria-busy` on the section while fetching.
- Download buttons keep the existing `title`/`aria` affordance (`FilesTab.tsx:435`).

### UI-checkable acceptance
- [ ] Section appears only in a `_revision` Files tab with a resolvable `parentRunId`; collapsed by default.
- [ ] Label reads "From v{n-1}" using the `SectionHeader` classes — no new header styling.
- [ ] Parent files are fetched ONLY on first expand (lazy), via `getWorkflow(parentId)` — verified no fetch on collapsed mount.
- [ ] Each base file row is the unmodified `renderFileRow` shape and is independently downloadable.
- [ ] Loading uses the existing FilesTab spinner idiom; empty uses the existing muted-gray copy.

---

## Revision-instruction display (shared micro-contract for Surfaces 1, 2, 3)

The "↳ revises v{n}" microcopy (Surface 1) and the "'{instruction preview}'" context line (Surfaces 2 & 3) need the revision instruction text.

- **Source (B scope):** the instruction comes from the `/family` member context (member `title` / the clean instruction stored on `run.input` for `run_revision` paths, `websocket.py:2257`) via a **simple inline extraction** — first non-marker line, stripped of any `=== EXISTING … ===` / `=== REVISION REQUEST ===` wrapper, `slice(0, ~60)` + ellipsis, rendered `truncate`.
- **DEPENDENCY FLAG (hand-off to Workstream C):** the canonical, format-tolerant `parseRunInput(input)` parser is **Workstream C** (plan §6.1). Workstream B MUST NOT author a second parser. B uses a minimal inline extraction ONLY for the short preview string; when C lands, these three call sites switch to `parseRunInput(...).revisionInstruction`. Do not duplicate C's marker-family logic in B — a preview-only `slice` is the sanctioned temporary shim (retired to `parseRunInput` in C, matching the INV-12 "three FE parser copies → one lib" net-negative-duplication mandate, §10).
- Instruction preview styling: `text-[10px] text-gray-400 truncate` (planner-subtitle analog `AgentThinkingTab.tsx:151-153`). No new styling.

---

## Reuse Analog Map

| New node | Existing analog (file:line) |
|---|---|
| Family root card (row shape) | `WorkflowHistory.tsx:867-948` |
| "v{N}" count pill | `WorkflowHistory.tsx:803` (filter count pill) |
| Family/version status badge | `WorkflowHistory.tsx:899-915` |
| Version status dot (v-chip) | `PrototypePreview.tsx:509,538` + color map `Sidebar.tsx:66-73` |
| Expandable child rows / chevron | `WorkflowHistory.tsx:420-455` (`<details>`, chevron `:448`) |
| Child indent | `AgentThinkingTab.tsx:119` (`pl-8`) |
| "↳ revises v{n}" microcopy style | `AgentThinkingTab.tsx:151-153` (`text-[10px] text-gray-400`) |
| Version chips row (pill group) | `PreviewPanel.tsx:552-568` / tabs `WorkflowHistory.tsx:573-585` |
| Active version fill (accent) | `WorkflowHistory.tsx:798` / `PreviewPanel.tsx:561` (`bg-[#1B2A4A] text-white`) |
| Ghost sibling version | `PreviewPanel.tsx:561` (`text-gray-500 hover:text-gray-700`) |
| Version-switch cross-fade | `PreviewPanel.tsx:586-594` (`AnimatePresence mode="wait"`, dur 0.15) |
| Detail load via getWorkflow | `WorkflowHistory.tsx:163` |
| Live "v{n} ▾" chip | `PrototypePreview.tsx:529-539` (toggle pill) + chevron `AgentThinkingTab.tsx:164` |
| Version dropdown / listbox | `WorkflowHistory.tsx:925-944` + outside-click `:961-963` |
| Read-only amber banner | `ReviewGatePanel.tsx:398-403` (`bg-amber-50 border-amber-200 text-amber-700`) |
| Chip v1→v2 pulse | `AgentThinkingTab.tsx:123,163` (`animate-pulse`) |
| Older-version amber sub-dot | `PrototypePreview.tsx:538` (`bg-amber-400`) |
| "From v{n-1}" section header | `FilesTab.tsx:152-159` (`SectionHeader`) |
| Base file row | `FilesTab.tsx:412-444` (`renderFileRow`) |
| Lazy-load / row spinner | `FilesTab.tsx:438` / `WorkflowHistory.tsx:627` (`Loader2`) |
| Files empty state | `FilesTab.tsx:401-409` |
| Instruction preview text style | `AgentThinkingTab.tsx:151-153` |
| Status→color source of truth | `Sidebar.tsx:55-73`, `WaveTreePanel.tsx:47-63` |
| Row-entrance motion | `WorkflowHistory.tsx:868-872`, `FilesTab.tsx:415-419` |

## No Analog Found

- **None visual.** Every visual/motion element maps to an existing analog above.
- **Behavior-only (not visual language):** the `role="radiogroup"`/`role="radio"`/`role="listbox"` + Arrow-key navigation + managed-focus wiring for the version switcher (Surfaces 2 & 3) has no existing codebase precedent to copy — but it is **ARIA/keyboard behavior on top of the inherited pill/dropdown visuals**, mandated by plan §8, not net-new styling. Flagged here for the executor to implement the wiring; the pixels are 100% reused.
- **Deferred dependency (not a defect):** the canonical `parseRunInput` for the revision-instruction preview belongs to Workstream C (§6.1). B uses a preview-only inline `slice` shim; no net-new parser. Flagged in the Revision-instruction section above.

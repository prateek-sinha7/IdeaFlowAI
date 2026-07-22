---
title: Workstream B — Revision Families FE — UI Review (closing gate)
status: complete
phase: Workstream B (revision families FE)
baseline: .planning/WORKSTREAM-B-UI-SPEC.md + REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md §8
audit_mode: CODE-ONLY (dev server auth-gated → no screenshots; Phase-21 precedent)
date: 2026-07-02
---

# Workstream B — Revision Families FE — UI Review

**Baseline:** WORKSTREAM-B-UI-SPEC.md (reuse-first contract) + plan §8 a11y mandate.
**Screenshots:** NOT captured — dev server is auth-gated offline. This is a **code-level**
audit (Tailwind-class fidelity, ARIA/role wiring, state coverage, microcopy). **Pixel /
render fidelity is explicitly deferred** to a live pass, per the Phase-21 code-only precedent.
**Files audited:** RevisionFamilyView.tsx, LiveVersionChip.tsx, WorkflowHistory.tsx (wiring),
PreviewPanel.tsx (wiring), FilesTab.tsx (base-version section), DashboardLayout.tsx (fetch seam).

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Typography | 4/4 | Only inherited 13/12/11/10/9px + semibold/medium scale; zero raw sizes |
| 2. Color | 4/4 | Only inherited navy `#1B2A4A`, amber-50/200/700, emerald/gray/blue status maps; zero new hex |
| 3. Spacing / Layout | 4/4 | 4-based scale throughout; timeline above tab bar, chip in header cluster before Copy |
| 4. Visual hierarchy | 4/4 | v-pill subordinate to status badge/title; active navy vs ghost chips; amber banner appropriately prominent |
| 5. Consistency | 3/4 | Strong cross-surface system; version-numbering **source** differs (createdAt vs revision_index) between B2 list and B2/B3 timeline |
| 6. Accessibility (§8) | 2/4 | Listbox keyboard nav is stranded (focus never enters listbox); history child rows are non-focusable `<div>`s |

**Overall: 21 / 24**

---

## Top 3 Priority Fixes

1. **LiveVersionChip dropdown strands keyboard users (a11y §8)** — `LiveVersionChip.tsx:135-150`.
   The `onKeyDown` handler is bound to the `role="listbox"` `motion.div`, but on open nothing
   moves focus into it and the div has no `tabIndex`; focus remains on the chip `<button>`, which
   is a *sibling* of the listbox, so its keydown never reaches the handler. Result: Arrow-key
   nav, Enter-to-select, and **Escape-to-close are all non-functional for keyboard users** — the
   spec's mandated "Arrow-key nav + Enter to select + Escape to close" (Surface 3 A11y) fails.
   *Fix:* add `tabIndex={-1}` to the listbox and `ref.focus()` it in a mount effect when `open`
   (or roving-focus the `role="option"` buttons and put the handler on each option / the chip).

2. **History child version rows are not keyboard-operable (a11y §8)** —
   `RevisionFamilyView.tsx:328-342`. Each expanded version row is a plain `<div onClick=…>` with
   no `role`, `tabIndex`, or key handler, violating Surface 1 A11y ("Child rows are
   keyboard-focusable and Enter-activatable"). Keyboard/AT users can expand the family but cannot
   reach or open a specific version. *Fix:* make each row a `<button>` (or add
   `role="button" tabIndex={0}` + Enter/Space handler) with `aria-label="Version {n}, {status}"`.

3. **Version-number source is inconsistent across surfaces (consistency)** — the B2 list child
   rows label `v{i+1}` on **createdAt-ASC** order (`RevisionFamilyView.tsx:322-334`,
   `groupRunsByFamily` sorts by `createdAt`), while the B2 detail timeline and B3 live chip label
   `v{i+1}` on **`revision_index`-ASC** order (`RevisionFamilyView.tsx:398-399`,
   `LiveVersionChip.tsx:70-71`). If createdAt ordering ever diverges from revision_index, the same
   run shows a different "v number" in the list vs the chip — breaking the "one workflow, one
   numbering" promise. *Fix:* have `groupRunsByFamily` sort members by `revision_index` (falling
   back to createdAt) so all three surfaces derive v-numbers from one ordering.

---

## Detailed Findings

### Pillar 1 — Typography (4/4)
- **PASS** — Every new node uses only the inherited scale: `text-[13px]` root title
  (`RevisionFamilyView.tsx:244,288`), `text-[12px]` child title (`:337`), `text-[11px]` chip/control
  (`:458`, `LiveVersionChip.tsx:161`), `text-[10px]` meta/context (`:338,340,472`), `text-[9px]`
  count pill (`:299,333`). Weights are `font-semibold`/`font-medium`/regular only. No raw font size
  outside the scale anywhere in the two new modules.

### Pillar 2 — Color (4/4)
- **PASS** — Active-version fill is the reserved navy `bg-[#1B2A4A] text-white`
  (`RevisionFamilyView.tsx:460`, `LiveVersionChip.tsx:124`). Status dots come from the inherited
  map via `statusDotClass` (`RevisionFamilyView.tsx:77-92`: emerald-400 / amber-400 / gray-300 /
  blue-400) — matching Sidebar/PrototypePreview conventions, not re-invented. Read-only banner is
  the inherited `bg-amber-50 border-amber-200 text-amber-700` + `text-amber-600` icon
  (`LiveVersionChip.tsx:196-198`). Older-version sub-dot `bg-amber-400` (`:130`). Count pill
  `bg-gray-200 text-gray-500` (`:299`). **No new hex value introduced** anywhere.
- **PASS (nit)** — `failed → bg-gray-300` for the dot (`RevisionFamilyView.tsx:86`) is a slightly
  darker gray than any dot literal cited in the spec, but the spec's failed convention is the gray
  family and no new *hue* is introduced. Acceptable.

### Pillar 3 — Spacing / Layout (4/4)
- **PASS** — 4-based rhythm only: `gap-1/1.5/2/3/4`, `px-5 py-2` chips row (`:445`), `px-6 py-4`
  root row (`:238,282`), `pl-8 pr-6 py-2.5` child rows (`:331`), `px-3 py-2` banner
  (`LiveVersionChip.tsx:196`), `mt-5` base section (`FilesTab.tsx:527`). `py-2.5` is an existing
  in-scale step, not net-new.
- **PASS** — VersionTimeline is rendered as a full-width strip **above** the tab bar
  (`WorkflowHistory.tsx:623-628` precedes the tab bar at `:630`). LiveVersionChip is the **first**
  control in the header cluster **before** Copy/Collapse (`PreviewPanel.tsx:613-620` precedes Copy
  at `:621`) — no crowding, matches Surface 3 "Where."
- **PASS** — Read-only banner sits as a slim strip directly under the header, above the tab bar
  (`PreviewPanel.tsx:642-648`), matching the spec placement.

### Pillar 4 — Visual hierarchy (4/4)
- **PASS** — The version affordance is discoverable but subordinate: the `v{N}` count pill is the
  smallest text (`text-[9px]`) and sits beside the louder status badge (`RevisionFamilyView.tsx:296-303`);
  the title stays `text-[13px] font-semibold`. Active chip is the navy focal fill vs ghost siblings
  (`:459-461`) — clear active/inactive read. The amber read-only banner is a full-width mode
  indicator with icon + action, appropriately prominent as a mode change (`LiveVersionChip.tsx:193-207`).

### Pillar 5 — Consistency (3/4)
- **PASS** — Both surfaces share one system: same `statusDotClass` import (LiveVersionChip pulls it
  from RevisionFamilyView, `LiveVersionChip.tsx:28`), same `v{n}` labelling, same navy active fill,
  same count-pill class for v-chips (`RevisionFamilyView.tsx:333`, `LiveVersionChip.tsx:165`), same
  dropdown/outside-click idiom. The "↳ revises v{n}" (list) and "↳ Revises v{n-1} — '{preview}'"
  (timeline) language rhymes.
- **FLAG (see Top Fix 3)** — v-number derivation differs: list uses createdAt order, timeline/chip
  use `revision_index`. Same-workflow numbering can diverge.
- **FLAG (minor)** — "↳ revises v{n}" (list, lowercase, no preview, `RevisionFamilyView.tsx:340`)
  vs "↳ Revises v{n-1} — '{preview}'" (timeline, capitalized, with preview, `:473`). Two spellings
  of the same relationship string. Recommend one canonical capitalization.

### Pillar 6 — Accessibility (2/4) — §8 scrutiny
- **PASS** — VersionTimeline is a real `role="radiogroup"` (`:442`) with `role="radio"` +
  `aria-checked` options (`:453-454`), roving `tabIndex` (`:456`), Arrow/Enter/Space handler
  (`:421-433`), and **managed focus that only fires after a user switch, never on mount**
  (`:394-411`) — a correct, thoughtful implementation of the §8 mandate. Status dot `aria-hidden`,
  status carried in `aria-label` (`:455,464`).
- **PASS** — LiveVersionChip button has `aria-haspopup="listbox"` + `aria-expanded` + descriptive
  `aria-label` (`:120-122`); chevron is `aria-hidden` inside the labelled button (`:132`).
  Options carry `role="option"` + `aria-selected` (`:157-158`). Focus returns to the chip on
  close/select (`:86,92`). Read-only banner is `role="status"` (`:195`). Base-version section
  toggle has `aria-expanded` + `aria-label`, with `aria-busy` on the section while fetching
  (`FilesTab.tsx:527,530-531`) — full §8 coverage for Surface 4.
- **BLOCK (a11y §8)** — LiveVersionChip listbox keyboard nav is dead: handler on the non-focusable
  listbox div, focus never enters it → Arrow/Enter/Escape inert for keyboard users
  (`LiveVersionChip.tsx:139-148`). See Top Fix 1. The visual/pointer path works; the mandated
  keyboard path does not. Classified BLOCK because Surface 3's a11y acceptance ("Escape closes;
  focus returns to chip; Arrow-key nav + Enter to select") cannot pass.
- **FLAG (a11y §8)** — History child version rows are non-focusable `<div onClick>` with no role or
  key handler (`RevisionFamilyView.tsx:328-342`), violating Surface 1 A11y. See Top Fix 2.
- **FLAG (minor)** — Root family card rows are also `<div onClick>` (`:233-238,277-282`); this
  matches the *existing* history-row pattern (zero-regression clone) so it is not a new defect, but
  the whole history surface remains mouse-only for row activation. Note for a future a11y sweep,
  not charged against B.

### Async / empty / error states
- **PASS** — Version switch shows the existing detail spinner via `setLoadingDetail(true)` around
  `getWorkflow` (`WorkflowHistory.tsx:201-211`); PreviewPanel switch cross-fades. Base-version lazy
  section shows the inherited spinner + "Loading base version…" (`FilesTab.tsx:539-543`), an empty
  "No files in the base version." (`:550`), and only fetches on first expand
  (`baseFetched` guard, `:244`). Family fetch is cancellable to avoid stale landings
  (`WorkflowHistory.tsx:190-194`).
- **FLAG (minor)** — Family fetch failure is swallowed to `setFamily(null)`
  (`WorkflowHistory.tsx:193`) and read-only/version fetch errors are empty `catch {}`
  (`:209`). This degrades gracefully (the version affordance simply hides), so no blank/broken
  screen — but there is **no** error signal at all if `/family` fails for a genuine multi-member
  family (the user silently loses the version switcher). Acceptable for ship; note for observability.

### Microcopy
- **PASS** — "v{N}", "↳ revises v{n}", "Viewing v{k} (read-only)" + "Back to latest →"
  (`LiveVersionChip.tsx:199-205`), "From v{n-1}"/"From version {n-1}" (`FilesTab.tsx:524-525`),
  "Files from the previous version this revision was based on." (`:547`) — all match the spec's
  copy contract. The instruction preview uses the sanctioned inline `slice` shim
  (`RevisionFamilyView.tsx:355-377`) with a clear Workstream-C hand-off comment — no second parser
  authored (INV-12 respected).

---

## Reuse-Fidelity Verdict

**REUSE-FIRST: HONORED.** The audit found **zero net-new visual language** — no new hex value,
radius, font size, shadow, or motion curve in either new module. Every visual node cites and
matches its UI-SPEC analog: toggle-pill (PrototypePreview), count pill (WorkflowHistory filter),
dropdown + outside-click catcher (WorkflowHistory row-menu), amber banner (ReviewGatePanel),
status dots (Sidebar/PrototypePreview map via `statusDotClass`), cross-fade (`AnimatePresence
mode="wait"` dur 0.15), and the `animate-pulse` tick. The one intentional, spec-sanctioned
divergence is the chevron rotate: controlled state `rotate-90` instead of `group-open:rotate-90`
(`RevisionFamilyView.tsx:313`), correctly documented because there is no native `<details>`
wrapper — this is a behavioral necessity, not new styling. The `role="radiogroup"`/`listbox`
wiring is net-new *behavior* on inherited *pixels*, exactly as the spec's "No Analog Found —
behavior-only" clause permits.

---

## Overall Verdict

**SHIP-WITH-FIXES (21/24).** Visual and reuse discipline is excellent — a clean, faithful,
reuse-first implementation that reads as one coherent version system across the history and live
surfaces. The gating issues are **accessibility keyboard-operability**, not visual: the live
listbox keyboard path is non-functional (BLOCK) and the history child rows are not keyboard
reachable (FLAG), both against the explicit §8 mandate. Fix those two before the a11y sign-off;
align the v-number ordering source for cross-surface correctness. Pixel fidelity remains to be
confirmed on a live, authenticated pass.

### Findings tally
- **BLOCK: 1** — LiveVersionChip listbox keyboard nav stranded (a11y §8).
- **FLAG: 4** — non-focusable history child rows; v-number source mismatch; microcopy
  capitalization split; silent family-fetch error (observability).
- **PASS:** typography, color, spacing/layout, visual hierarchy, reuse-fidelity, async/empty/lazy
  states, radiogroup wiring, Surface-4 a11y, microcopy contract.

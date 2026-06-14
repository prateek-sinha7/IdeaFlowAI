# Phase 21 — UI Review

**Audited:** 2026-06-14
**Baseline:** `21-UI-SPEC.md` (reuse-first design contract — "introduce NO new visual language; net-new styling is a defect")
**Screenshots:** Not captured — dev server on :3000 returns 307 → `/login` (auth-gated SPA; the saved-workflows surfaces sit behind authentication and are not reachable by an unauthenticated CLI capture). Code-only audit.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | Domain-specific copy throughout; no generic "Submit/OK"; spec'd empty/error/CTA labels present. |
| 2. Visuals | 3/4 | Hierarchy inherited cleanly; icon-only kebab has no aria-label (matches analog, but still a gap). |
| 3. Color | 4/4 | Zero net-new color. `#1B2A4A`/`#f5f5f0` are inherited catalog tokens; modal is pure gray-scale. |
| 4. Typography | 4/4 | Sizes/weights lifted verbatim from analogs (`text-[15px]` rows, `text-[13px]` modal title). |
| 5. Spacing | 4/4 | `p-6`/`gap-2`/`py-5`/`mt-12` all match the DeleteModal + catalog-row analogs; no arbitrary px spacing. |
| 6. Experience Design | 3/4 | Loading/error/empty/disabled/destructive-confirm all covered; no Esc-close / focus-trap (inherited gap, but UI-SPEC §4 names Esc explicitly). |

**Overall: 22/24**

---

## Top 3 Priority Fixes

1. **No Esc-to-close or focus-trap on `NameWorkflowModal` / delete-confirm / kebab menu** (WARNING) — keyboard users cannot dismiss the modal without mouse-clicking the backdrop, and focus is not trapped inside the dialog. UI-SPEC §4 explicitly requires "the modal traps focus / closes on Esc + backdrop like the analogs" and §5 lists "Save → modal → confirm … work with visible focus" as UI-checkable acceptance. The analogs (`DeleteModal`, WorkflowHistory kebab) also omit this, so the clone faithfully reproduced an analog gap — but the spec named Esc/focus as acceptance, so it is in-scope here. **Fix:** add a `useEffect` keydown listener (`e.key === "Escape" → onCancel`) and a minimal focus-trap (or `role="dialog" aria-modal="true"` + autofocus already present on the name input) to `NameWorkflowModal.tsx`; ideally backport to the analog so both stay identical.

2. **Icon-only kebab button has no accessible name** (WARNING) — `WorkflowCatalog.tsx:364-372` renders a `MoreHorizontal`-only `<button>` with no `aria-label`/`title`, so screen-reader users hear "button" with no indication it opens Rename/Duplicate/Delete. Matches the WorkflowHistory analog, but is still an a11y defect on a primary management affordance. **Fix:** add `aria-label="Workflow options"` to the kebab `<button>` (`WorkflowCatalog.tsx:364`).

3. **Saved-list error is non-dismissable and can persist stale** (WARNING) — `savedError` (`WorkflowCatalog.tsx:334-339`) renders a red banner that is only cleared on the next successful CRUD action; a failed rename/delete/duplicate leaves the banner up with no retry/dismiss affordance, and a transient fetch failure shows an error even after the list otherwise loads. **Fix:** add a dismiss affordance or auto-clear `savedError` after a timeout (mirror the composer's 2.5s `savedConfirm` pattern in `IdeaInputPage.tsx:296`).

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)
Strong, contract-compliant copy. Evidence:
- CTAs are specific: "Save workflow" / "Create workflow" / "Run workflow" — no generic "Submit/OK" (grep for generic labels returned none in the three new/modified files).
- Modal copy is purposeful: `NameWorkflowModal.tsx:63` "Name it to find it later", `:78` placeholder "e.g. Competitive research", `:91` "What does this workflow produce?".
- Destructive confirm copy is clear and honest: `WorkflowCatalog.tsx:449-455` "Delete workflow / This cannot be undone / The saved workflow will be permanently removed from your list."
- Empty/loading/error triad copy reused verbatim from the AgentModelPicker analog (`:249` "Loading workflows…", `:260` "No workflows available for your plan yet.").
- Success confirm "Saved" (`IdeaInputPage.tsx:451`) is concise. No defects.

### Pillar 2: Visuals (3/4)
Visual hierarchy is inherited cleanly — saved rows (`WorkflowCatalog.tsx:341-361`) reuse the built-in catalog row's `text-[15px] font-semibold italic` label + `text-[12px] italic text-gray-500` subtitle, so the "Your workflows" section is pixel-equivalent to the built-in list as §5 requires. The kebab sits in the right slot where the built-in row's `ArrowRight` lives (§2.1 satisfied). Focal point (the centered "What would you like to build today?" h1) is preserved.
- **WARNING:** the kebab `<button>` (`:364`) is icon-only (`MoreHorizontal`) with no `aria-label`/tooltip — fails the "icon-only buttons paired with aria-labels" check. (See Priority Fix 2.)
- Minor: kebab is `opacity-0 group-hover:opacity-100` (`:369`) — the management affordance is invisible until hover, which is the intended analog behavior but means touch/keyboard users get no persistent affordance. Inherited from the WorkflowHistory analog; noted, not scored as a blocker.

### Pillar 3: Color (4/4)
Zero net-new color introduced — the overriding spec mandate holds.
- `NameWorkflowModal.tsx`: hex/rgb grep returned **none**. Entirely gray-scale tokens (`bg-gray-100`, `text-gray-600`, `bg-gray-900`, `text-gray-400`) lifted from the DeleteModal analog.
- `WorkflowCatalog.tsx`: the only hardcoded hexes are `#f5f5f0` (canvas bg, `:212`) and `#1B2A4A` (navy accent, `:293/:302/:353`) — both are the EXISTING catalog tokens; the saved rows reuse `group-hover:text-[#1B2A4A]` exactly as the built-in rows do (`:293` vs `:353`). No new accent.
- `IdeaInputPage.tsx`: hexes at `:507-524` are pre-existing migration-picker tokens, untouched by this phase.
- Accent (navy `#1B2A4A`) usage stays confined to row-hover + tier-upgrade hints + the migration picker — same elements as before. 60/30/10: the surface is gray-scale-dominant with a single navy accent — compliant. No defects.

### Pillar 4: Typography (4/4)
Font sizes/weights are reused, not invented.
- Modal: `text-[13px] font-semibold` title, `text-[11px] text-gray-400` subtitle, `text-[10px] font-semibold uppercase` labels, `text-[12px]` input — these match the `AgentsPopup` input analog (`:374-393`) and DeleteModal header verbatim.
- Saved rows: `text-[15px] font-semibold italic` (`:353`) is byte-identical to the built-in row label (`:292`).
- Weight set across the new surfaces is `font-normal`/`font-medium`/`font-semibold` only (3 weights, all pre-existing in the analogs). Sizes are the established arbitrary-px scale the codebase already uses (`10/11/12/13/15px`), not new values. Within-contract.

### Pillar 5: Spacing (4/4)
- `NameWorkflowModal.tsx` shell: `p-6`, `mb-4`, `mb-3`, `mb-5`, `gap-2`, `px-4 py-2.5` — identical to the DeleteModal analog (`WorkflowHistory.tsx:932-965`). Card `max-w-[340px] w-full mx-4` matches exactly.
- Saved section: `mt-12` section gap, `py-5` rows, `divide-y divide-gray-200/70`, `px-3 -mx-3` row inset — all copied from the built-in catalog list (`:267` vs `:340`).
- Kebab dropdown: `top-8 min-w-[120px] py-1`, items `px-3 py-2` — identical to the WorkflowHistory menu analog (`:884-896`). No arbitrary one-off spacing introduced.

### Pillar 6: Experience Design (3/4)
Strong state coverage:
- **Loading:** `WorkflowCatalog.tsx:248` built-in list; the saved-list fetch is non-fatal by design (`:122-125`) so a saved-fetch failure never blocks the catalog (SC-001 no-regression — good).
- **Error:** built-in error banner (`:252`), saved error banner (`:334`), composer save error inline (`IdeaInputPage.tsx:483`).
- **Empty:** the "Your workflows" section is conditionally hidden when `userWorkflows.length === 0` (`:329`) — note this means there is NO "no saved workflows yet" empty-state copy, which UI-SPEC §1 row 6 said should "mirror the existing empty copy." Minor divergence: the section simply doesn't render rather than showing an empty message. Defensible (avoids clutter for users who never saved one), but it is a small contract deviation worth noting.
- **Disabled:** Save button disabled when no agents (`IdeaInputPage.tsx:457`); modal Save disabled on empty name (`NameWorkflowModal.tsx:106`, `disabled:opacity-30 disabled:cursor-not-allowed`).
- **Destructive confirm:** Delete routes through a DeleteModal-shell confirm (`:428-472`) — correct. Delete is also non-optimistic-on-failure (`:174-186` removes the row only after the server resolves), a deliberate correctness fix over naive optimism.
- **WARNING (score driver):** no Esc-close / focus-trap on any of the three overlays — see Priority Fix 1; UI-SPEC §4 names Esc + focus as acceptance.
- **WARNING:** `savedError` is sticky (Priority Fix 3).

Registry audit: `components.json` not present (no shadcn) — Registry Safety section skipped per spec.

---

## Files Audited
- `frontend/src/components/catalog/NameWorkflowModal.tsx` (new — Save/Rename modal)
- `frontend/src/components/catalog/WorkflowCatalog.tsx` ("Your workflows" section, kebab, delete-confirm, "+ Create workflow")
- `frontend/src/components/workflow/IdeaInputPage.tsx` (composer "Save workflow" button + handler)
- Analogs cross-checked for reuse fidelity: `frontend/src/components/history/WorkflowHistory.tsx` (DeleteModal `:923-969`, kebab `:872-918`), `frontend/src/components/workflow/AgentsPopup.tsx` (input styling `:374-393`)

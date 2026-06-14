# Phase 21 — Saved Workflows: UI Design Contract (UI-SPEC)

**Generated:** 2026-06-14 · **Mode:** reuse-first · **Source:** `21-SPEC.md` §4 FE reuse map.

> **Design principle (overriding):** introduce NO new visual language. Every new surface is copied from an existing component's markup/tokens. Net-new styling is a defect — the gsd-ui-checker should FLAG any color/spacing/typography not inherited from the reused components. There is no shared `<Modal>`/`<Menu>` kit — hand-rolled per existing convention.

---

## 1. Component inventory (every node → existing analog)

| New node | Reuse source (existing) | Contract |
|---|---|---|
| **NameWorkflowModal** (name + optional description → Save/Cancel) | `WorkflowHistory.tsx:923-969` `DeleteModal` shell (backdrop, header, two-button footer) + input styling from `AgentsPopup.tsx:374-393` | same backdrop/scale-in motion, same footer button pair; z-index ≥ `z-[80]` (opens over `AgentsPopup`). |
| **"Save workflow" button** (composer) | the existing toolbar/footer pill buttons — `IdeaInputPage.tsx:386-398` (Run) / `AgentsPopup.tsx:988-996` (Save changes) | reuse the gray-900 pill style verbatim; sits beside Run / in the popup footer. |
| **"+ Create workflow"** (catalog header) | `WorkflowCatalog.tsx:110-131` header block | a subtle top-right affordance in the existing centered column; matches the catalog's quiet style. |
| **"Your workflows" section** | `WorkflowCatalog.tsx:152-207` built-in row list (`divide-y` rows, `motion.div`, row `<button>`) | a second section under the built-in list; identical row markup; label = the saved `name`. |
| **Per-row kebab menu** (Rename / Duplicate / Delete) | `WorkflowHistory.tsx:872-899` (`MoreHorizontal` toggle + `AnimatePresence` dropdown) + `:916-918` dismiss layer | identical dropdown style; menu items reuse the history menu-item button style; Delete confirm → `DeleteModal`. |
| **Loading / error / empty** for the saved list | `WorkflowCatalog.tsx:134-149` (AgentModelPicker triad) | reuse verbatim; empty state for "no saved workflows yet" mirrors the existing empty copy. |

---

## 2. The six pillars (by reuse)
1. **Visual hierarchy** — saved rows inherit the catalog row hierarchy (label / description / right-affordance); the kebab sits where the catalog row's arrow is, OR beside it.
2. **Consistency** — colors/spacing/radius/typography come 100% from the reused components; the "Your workflows" section header matches the catalog's existing section/heading style.
3. **States** — loading/error/empty reuse the AgentModelPicker triad; a saved row mid-delete reuses the `DeleteModal`; rename reuses `NameWorkflowModal`. Built-in rows are unchanged (no kebab).
4. **Accessibility** — Save buttons + kebab + menu items are keyboard-activatable with the existing focus styles; the modal traps focus / closes on Esc + backdrop like the analogs.
5. **Motion** — reuse the existing `motion.div` enter/exit (rows) + modal scale-in + menu `AnimatePresence`; no new curves/durations.
6. **Responsive** — inherits the catalog column's existing responsiveness; the modal/menu use the existing fixed-overlay patterns.

---

## 3. Interaction flows (visual outcomes; logic in 21-SPEC §4)
- **Save from composer:** click "Save workflow" → NameWorkflowModal → enter name → Save → toast/inline confirm → it appears in the catalog "Your workflows" section.
- **Save from catalog:** "+ Create workflow" → routes into the custom composer (existing transition) → assemble → Save (as above).
- **Rename:** kebab → Rename → NameWorkflowModal prefilled → Save → row label updates optimistically.
- **Duplicate:** kebab → Duplicate → a new "(copy)" row appears.
- **Delete:** kebab → Delete → DeleteModal confirm → row removed optimistically.
- **Launch a saved workflow:** click the row → the composer opens **pre-loaded** with the saved agents/models (the user types the brief, then Run) — same run experience as any custom run.

---

## 4. Non-goals (defects if present)
- No new color/font/spacing/shadow/card shape; no bespoke modal/menu kit; no new icons beyond the existing set (`MoreHorizontal`, `Lock`, `ArrowRight`, etc.).
- Built-in (manifest) rows must NOT gain a kebab/rename (read-only).
- No raw API `name` rendering (catalog rule carries over).

---

## 5. Acceptance (UI-checkable)
- "Save workflow" is visually consistent with the existing pill buttons; NameWorkflowModal is visually a `DeleteModal` with a name field.
- The "Your workflows" rows are pixel-equivalent to built-in catalog rows (+ a kebab); the kebab dropdown is visually the `WorkflowHistory` menu.
- Rename/Delete reuse the existing modal; loading/error/empty reuse the AgentModelPicker triad.
- Keyboard: Save → modal → confirm, and kebab → menu → item, all work with visible focus.

# Phase 20 — Workflow Catalog: UI Design Contract (UI-SPEC)

**Generated:** 2026-06-14 · **Mode:** reuse-first (auto, on-chain) · **Source:** `20-SPEC.md` FE reuse map.

> **Design principle (overriding):** this view introduces **NO new visual language.** It reuses the existing dashboard's components, tokens, and motion verbatim. The contract below is therefore expressed as *which existing surface each pixel comes from*. Any net-new styling is a defect — the gsd-ui-checker should FLAG any color/spacing/typography not inherited from the reused components.

---

## 1. Component inventory (every node maps to an existing analog)

| Catalog node | Reuse source (existing) | Contract |
|---|---|---|
| Catalog view container | `DashboardLayout` home-view block (`:1047-1059`) wrapped in `motion.div key="catalog"` | identical entry/exit transition + padding as the `home`/`library` blocks; switched by the `MainView` state, not a route. |
| Workflow row/card | `CreationHub.tsx` row JSX (`:69-123`) | reuse verbatim — icon, title, description, hover, chevron. Only the data source changes (live fetch vs const). |
| Icon + friendly label | `WorkflowHistory.TYPE_META` (`:83-96`) + `useNotifications.WORKFLOW_LABELS` (`:19-32`) | render the mapped icon + label; NEVER the raw API `name` (title-cased id). |
| Tier lock / upgrade affordance | `CreationHub` gating (`canRunPipeline`/`getUpgradeTier`/`Lock` + "Requires {tier} plan") via `entitlements.ts` | reuse verbatim for gated-but-launchable rows. |
| Nav entry | `AppHeader` Library button (`:100-110`) | copy the button; same active/inactive style; wired to `onNavigate("catalog")`. |
| Section header / page chrome | the home/library view header pattern already in `DashboardLayout` | match heading size/weight/spacing of the existing views. |

---

## 2. The six pillars (by reuse)

1. **Visual hierarchy** — inherited from `CreationHub`: icon-left, title (primary), description (secondary, muted), affordance-right. No new hierarchy invented.
2. **Consistency** — colors, spacing, radius, typography come 100% from the reused components' existing Tailwind classes / tokens. The "Catalog" nav button is visually indistinguishable in style from "Home"/"Library".
3. **States** (reuse `AgentModelPicker` triad `:99-114`):
   - **Loading** — the existing spinner/skeleton style used by AgentModelPicker while fetching.
   - **Error** — the existing inline error style ("Couldn't load …" + retry affordance) from AgentModelPicker.
   - **Empty** — when no workflow is `user_launchable` ∧ tier-entitled, show the existing empty-state pattern (mirroring AgentModelPicker's no-agents / a library empty state), not a blank screen.
   - **Gated row** — existing lock + "Requires {tier} plan" from CreationHub (NOT hidden; shown disabled/locked so the upgrade path is discoverable).
   - **Loaded** — rows rendered identically to today's home tiles.
4. **Accessibility** — inherit CreationHub/AppHeader semantics: each row is a button (keyboard-activatable), focus-visible ring from the existing button styles, lock state announced via the existing affordance; nav button reachable by keyboard like Home/Library. No regression vs the surfaces being copied.
5. **Motion** — reuse the existing `AnimatePresence`/`motion.div` enter/exit used by the other `MainView` blocks (`DashboardLayout`); no new animation curves or durations.
6. **Responsive** — match the reused container's existing responsive behavior. If the simple list (data-driven CreationHub) is shipped, it inherits CreationHub's responsiveness; if the richer page is chosen, it inherits `LibraryPage`'s responsive grid (`:500`, 2/3/4-col).

---

## 3. Launch interaction (visual outcomes only — logic in 20-SPEC §3.3)

- **Tap a plain-run row** (`user_stories`/`app_builder`/`custom`/`migration`) → transitions to the existing `IdeaInputPage` (same transition as today's home→input). `custom` lands on the idea page with the existing "Add agents first" disabled-Run state (not an error).
- **Tap a wizard row** (`prototype`/`ppt`) → navigates to the existing template wizard (`/workflow/{type}/templates`); the catalog itself renders no wizard UI.
- **Tap a gated row** → the existing upgrade/lock affordance fires (no run starts), identical to CreationHub today.

---

## 4. Explicit non-goals (defects if present)

- No new color palette, font, spacing scale, card shape, or shadow.
- No bespoke loading/error/empty illustrations — reuse the existing ones.
- No new modal/drawer chrome — the catalog is a flat in-dashboard view.
- No raw API `name` rendered to the user.
- No `od_*` / `*_revision` / `sample_*` rows visible.

---

## 5. Acceptance (UI-checkable)

- The "Catalog" nav entry is visually consistent with Home/Library (same component, same active style).
- A loaded catalog row is pixel-equivalent to a current home tile (same component).
- Loading/error/empty states render via the reused AgentModelPicker patterns (no blank screen, no bespoke styling).
- A gated row shows the existing lock + "Requires {tier} plan" affordance.
- Keyboard: nav → catalog → row activation works with visible focus, matching the copied components.

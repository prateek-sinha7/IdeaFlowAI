---
phase: 35-shell-chrome-reskin-pages-b1
reviewed: 2026-07-09T00:00:00Z
depth: deep
files_reviewed: 16
files_reviewed_list:
  - frontend/src/components/layout/AppHeader.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/ui/NotificationPanel.tsx
  - frontend/src/components/settings/AccountSettings.tsx
  - frontend/src/components/workflow/prototype/TemplateGallery.tsx
  - frontend/src/components/workflow/prototype/TemplateDetailModal.tsx
  - frontend/src/components/workflow/prototype/CustomTemplateModal.tsx
  - frontend/src/components/workflow/prototype/TemplateCard.tsx
  - frontend/src/components/workflow/prototype/DesignSystemPicker.tsx
  - frontend/src/components/workflow/prototype/DesignSystemDetailModal.tsx
  - frontend/src/components/workflow/prototype/CustomDesignSystemModal.tsx
  - frontend/src/components/workflow/ReviewGatesSection.tsx
  - frontend/src/components/library/LibraryPage.tsx
  - frontend/src/app/login/page.tsx
  - frontend/src/app/register/page.tsx
  - frontend/src/app/admin/page.tsx
findings:
  critical: 0
  high: 0
  medium: 1
  low: 4
  total: 5
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-07-09
**Depth:** deep (cross-file: token layer, ui/ primitives, AnimatePresence wiring)
**Files Reviewed:** 16
**Status:** issues_found (no blockers)

## Summary

This is a disciplined, largely-mechanical reskin. Across all 16 files the wiring is
preserved: every `onNavigate` / `onSelect` / `onChange` / `onClick` / form `onSubmit`,
the login `handleSubmit` + `is_admin` redirect (untouched, above the diff), the admin
password-create modal + Runs/Role/Joined columns + `is_admin` gate + delete confirm, the
model save / password change / constitution save+delete handlers, the ReviewGates
`onChange`/`useCallback` contract, and all modal open/close state. The invariants hold:

- **INV-3 / LOCK-B** — all 16 files are frontend `.tsx`; no backend/Python/transport/SSE touched. PASS.
- **SC-001 / INV-1** — `AppHeader` nav is a generic `{key,label,Icon}` list keyed on page
  keys; `Badge`/`Button`/`Tabs`/`Pill`/`Card` take generic presentational props. No
  workflow-name keying introduced. PASS.
- **D-11** — nav relabel "Catalogue" → "My Workflows" while the page key stays
  `saved-workflows` and `onNavigate("saved-workflows")` is unchanged. PASS.
- **LOCK-F** — `DesignSystemPicker` counts render from real `customSystems.length` /
  `totalVisible`; no fabricated expansion. PASS.
- **ND-12** — login keeps its wired form; admin keeps the create-user modal + columns +
  gate; no SSO/Forgot/invite/suspend affordances added (left panel tags are static, no
  wiring). PASS.
- **a11y (D-15)** — `AppHeader` profile menu: `aria-haspopup="menu"`, `aria-expanded`
  correctly tracks `profileOpen`, `role=menu`/`menuitem` on all items, `aria-current` on
  active nav, and Escape closes + refocuses `triggerRef` via a wrapper `onKeyDown`. The
  `NotificationPanel` bell mirrors this (Escape refocuses `bellRef`). Aria wiring is
  functionally correct, not merely present.

Independent-of-tsc token audit: every `@theme` utility token (`brand`, `brand-fill`,
`brand-border`, `brand-on-dark`, `brand-pressed`, `brand-violet-tint`, `line-*`,
`surface-*`, `status-*`, `ink-300/800`) and every raw `var()` referenced in arbitrary
utilities (`--scrim`, `--radius-*`, `--elevation-*`, `--status-*-fill/-border`) and the
`.input-focus` helper resolve in `globals.css`. No silently-dropped styles found —
important because tsc does not validate Tailwind class names.

No correctness, security, or data-loss defects. The findings below are quality/consistency
items; the one Medium is a user-visible copy change hidden inside a styling diff (exactly
the class of change the reskin was asked to preserve), which should be confirmed as intended.

## Medium

### ME-01: NotificationPanel status label text changed by adopting `Badge` (content change in a styling diff)

**File:** `frontend/src/components/ui/NotificationPanel.tsx:171` (was ~155-165 pre-diff)
**Issue:** The status chip was replaced:
```diff
- <span ...>{n.status === "running" ? "Running" : n.status === "completed" ? "Completed"
-           : n.status === "failed" ? "Failed" : "Cancelled"}</span>
+ <Badge status={n.status} />
```
`Badge` normalizes `"completed"` → `"done"` and renders `label ?? key` in
`uppercase` (`Badge.tsx`). So the visible text changes from title-case
`Running / Completed / Failed / Cancelled` to `RUNNING / DONE / FAILED / CANCELLED`.
Notably `completed` now reads **"DONE"**, not "Completed" — a semantic copy change, not a
color/spacing change. The phase brief is reskin-only ("preserve existing behavior") and
explicitly asks to flag behavioral changes hidden inside styling diffs; this is one.
Colors and status→chip mapping are otherwise correct.
**Fix:** If the design-system copy is intended, no code change — record it as an accepted
copy change. If the prior wording must be preserved, pass explicit labels:
```tsx
const NOTIF_LABEL = { running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled" } as const;
<Badge status={n.status} label={NOTIF_LABEL[n.status]} />
```
(`Badge` still uppercases via CSS `uppercase`; drop `uppercase` from `Badge` or accept caps.)

## Low

### LW-01: LibraryPage skill/hook modals still wrapped in `<AnimatePresence>` after root changed to a plain `<div>` — dead wrapper + lost exit animation

**File:** `frontend/src/components/library/LibraryPage.tsx:607-612` (roots at 50 and 203)
**Issue:** `SkillDetailModal` and `HookDetailModal` had their root `motion.div`
(with `initial`/`animate`/`exit`) converted to a plain `div`, but they are still rendered
inside `<AnimatePresence>` (lines 607-612). `AnimatePresence` only defers unmount for
`motion` children, so the exit fade/scale now silently no-ops and the modals pop out
instantly. Functionally harmless (open/close is state-driven, `motion` import fully
removed, tsc clean), but it is an ineffective wrapper and an unintended animation
regression relative to the still-animated sibling `AgentCapabilitiesModal` (line 597).
**Fix:** Either drop the two now-pointless `AnimatePresence` wrappers, or restore
`motion.div` roots on the two modals if the exit animation was meant to be kept.

### LW-02: NotificationPanel dropdown uses `role="menu"` but its interactive children are not `menuitem`s

**File:** `frontend/src/components/ui/NotificationPanel.tsx:103` (the `motion.div role="menu"`)
**Issue:** The panel is a scrollable notification list whose "View progress"/"View
results" buttons and "Clear all" control are plain `<button>`s, not `role="menuitem"`,
and the container is not arrow-key navigable. A `role="menu"` container with
non-`menuitem` children is invalid ARIA and misleads AT users about the interaction model.
(Contrast `AppHeader`, where `role="menu"` is correct because every child is a
`role="menuitem"` button.) Low impact but a genuine a11y-correctness nit given the phase's
a11y focus.
**Fix:** Drop `role="menu"` here (a notification list is not a menu) — keep
`aria-haspopup`/`aria-expanded` on the bell and, if desired, label the panel with
`role="dialog"` + `aria-label="Notifications"`.

### LW-03: LibraryPage modal backdrops kept `bg-black/40` instead of the shared `var(--scrim)` token

**File:** `frontend/src/components/library/LibraryPage.tsx:51` and `:204`
**Issue:** Every other modal touched this phase (admin, TemplateDetailModal,
DesignSystemDetailModal, CustomTemplateModal, CustomDesignSystemModal) migrated the
overlay to `bg-[var(--scrim)]`, but these two skill/hook modal backdrops were left on the
stock `bg-black/40` utility. Not a retired-hex violation (so it passes the palette grep),
but an inconsistency in the same file’s reskin.
**Fix:** `className="... bg-[var(--scrim)] backdrop-blur-sm"` on both overlays.

### LW-04: `Badge` status primitive reused purely for color on non-status data (tiers / "current")

**File:** `frontend/src/app/admin/page.tsx:29-40` (`TIER_BADGE_STATUS` + `TierBadge`);
`frontend/src/components/settings/AccountSettings.tsx:513, 594` (`Badge status="running" label=...`)
**Issue:** `Badge` is documented as the canonical run-**status** chip keyed on the status
model. Here it is driven by an unrelated dimension — subscription tier
(`basic→queued`, `pro→running`, `enterprise→done`) and a literal `label="current"` — to
borrow its colors. Output is correct (explicit `label` is passed, colors resolve), so this
is not a bug, but it couples tier UI to the status ramp: a future change to status colors
will silently recolor tier chips, and the semantics read oddly (an "enterprise" plan chip
is the green "done" color). Consider a dedicated tint prop or a small `TierChip` if tier
coloring should evolve independently.
**Fix:** Optional. If kept, add a comment at the `Badge` call sites noting the status ramp
is being reused for color only, so the coupling is intentional and greppable.

---

_Reviewed: 2026-07-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

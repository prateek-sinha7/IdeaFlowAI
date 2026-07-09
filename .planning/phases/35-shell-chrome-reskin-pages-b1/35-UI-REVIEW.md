---
phase: 35-shell-chrome-reskin-pages-b1
audited: 2026-07-09
baseline: evidence 11 §B (shared-surface tokens/status model) · POR D-15 · mock 02 (shell) · mock 10 (login/admin)
screenshots: not captured (offline code-only audit — no dev server)
overall_score: 19/24
verdict: PASS (with FLAGs — no blockers)
files_audited: 12
---

# Phase 35 — UI Review (Shell Chrome + Reskin Pages [B1])

**Audited:** 2026-07-09
**Baseline:** evidence 11 §B (shared-surface tokens, status model B3, radius/elevation
ladders B2), POR D-15 (adopt visual language, keep richer behavior), mock `02` (shell
chrome canonical), mock `10` (login/admin). Mock HTML not in-repo — fidelity audited
against evidence 11 §B / 02 / 10, not a pixel diff.
**Screenshots:** not captured — offline audit. Rendered contrast, focus-trap, tab order
and SR announcements are marked **human-verify** below.
**Scope note:** token completeness (retired palette = 0, `@theme`+primitive usage) was
already verified per-file by the executor; this audit does NOT re-grep tokens — it scores
the 6 pillars and the things grep can't catch (contrast/WCAG-AA, a11y quality, status-color
correctness, typography/spacing idiom).

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Clear, deliberate labels; but profile-menu "Workflow History" contradicts the B5 canonical glossary ("Run History"). |
| 2. Visuals | 3/4 | Dark-shell idiom consistent across header/login/admin, clear hierarchy, icon-buttons labelled; wordmark under-specified vs B1. |
| 3. Color | 3/4 | Token adherence strong and status ramp correct; two deviations — 2 Library backdrops off-token, cancelled icon uses grey not amber. |
| 4. Typography | 3/4 | Consistent `font-sans`/weight usage; but a proliferation of ad-hoc px sizes and a non-spec wordmark. |
| 5. Spacing | 4/4 | Standard Tailwind scale throughout; radius ladder matches evidence B2 exactly (button 10 / card 14 / menu 12 / pill 999 / tag 5). |
| 6. Experience Design | 3/4 | Loading/error/empty states present, profile-menu a11y is genuinely correct; NotificationPanel `role=menu` is mis-modeled and a Library exit-animation regressed. |

**Overall: 19/24 — PASS (FLAG). No blockers.**

---

## Verdict: PASS (with FLAGs)

This is a disciplined, evidence-aligned reskin. Wiring is preserved, tokens resolve, the
dark surfaces pass WCAG AA (computed below), and the radius/elevation/status ladders match
evidence 11 §B. Every finding is a quality/consistency/a11y-correctness nit — none breaks
a user task, none is a security or data issue. Ship-eligible after confirming the two
copy/label items and, ideally, the two low-cost a11y/consistency fixes.

---

## WCAG-AA Contrast — dark token surfaces (computed, human-verify rendering)

The brief flagged the dark top bar (`#111114`) and the login dark brand panel. Computed
sRGB contrast ratios (all against `--surface-near-black #111114`):

| Element | Token / class | Fg color (effective) | Ratio | AA (small ≥4.5) |
|---|---|---|---|---|
| Wordmark, active nav, headings | `text-white` | `#FFFFFF` | ~19:1 | PASS |
| Inactive nav label / body | `text-white/60` | ≈`#A0A0A0` | ~7.2:1 | PASS |
| Bell icon | `text-ink-300 #9A9B92` | `#9A9B92` | ~6.6:1 | PASS |
| Login eyebrow | `text-brand-on-dark #8E88E8` (11px) | `#8E88E8` | ~6.1:1 | PASS |
| Login tags on `bg-white/5` | `text-white/60` | ≈`#A5A5A5` | ~7:1 | PASS |
| Admin subtitle | `text-white/50` (10px) | ≈`#888888` | ~5.3:1 | PASS (thinnest) |
| Notif badge count | `#FFF` on `bg-brand #3C2CDA` | `#FFFFFF` | ~8.2:1 | PASS |

**Result:** No AA text-contrast failure on the new dark surfaces. `text-white/50` (admin
subtitle) is the thinnest at ~5.3:1 and still clears AA for its 10px size. **Human-verify:**
confirm no OS/browser font-smoothing pushes the /50 and /60 greys below target on a real
display.

---

## Top Findings (ranked by severity, file:line)

### FLAG-1 — Terminology: "Workflow History" contradicts the B5 canonical glossary (WARNING)
**`AppHeader.tsx:247`** — the profile menu item reads **"Workflow History"**, but evidence
11 **§B5** makes the canonical term **"Run History"** ("Run History = past runs (was
'Workflow History')"). The phase correctly applied the sibling rename (Catalogue → "My
Workflows", D-11, `AppHeader.tsx:98`) but left the History label on the retired term. This
is the most concrete design-authority deviation in the phase.
**Fix:** relabel to `Run History` (page key/route unchanged, mirroring the My-Workflows
pattern).

### FLAG-2 — Status color: cancelled leading-icon is grey, not amber; disagrees with its own Badge (WARNING)
**`NotificationPanel.tsx:34`** — `StatusIcon` maps `cancelled → text-status-queued`
(grey `#9A9B92`). Evidence **§B3** assigns `cancelled → amber #9A6B1E`, and the sibling
chip on the same row (`Badge status={n.status}`, line 196) correctly renders cancelled as
amber (`Badge.tsx:27`). So a cancelled notification shows a **grey icon above an amber
badge** — an internal contradiction and a §B3 status-color miss. (running=blue and
queued/"Not run"=grey are otherwise correct per §B3.)
**Fix:** `if (status === "cancelled") return <XCircle className="... text-status-amber ..." />`.

### FLAG-3 — a11y: NotificationPanel `role="menu"` is mis-modeled (WARNING, confirms 35-REVIEW LW-02)
**`NotificationPanel.tsx:103` (+ bell `aria-haspopup="menu"` at :88)** — the dropdown is a
scrollable notification **list** whose children are plain `<button>`s ("View progress",
"View results", "Clear all"), not `role="menuitem"`, and the container is not arrow-key
navigable. A `role="menu"` with non-`menuitem` children is invalid ARIA and misdescribes
the interaction model to AT users. Contrast `AppHeader` (`:191`), where `role="menu"` is
correct because every child is a `role="menuitem"`.
**Fix:** drop `role="menu"` here and set the bell `aria-haspopup`/panel to a dialog/list
model — e.g. panel `role="dialog" aria-label="Notifications"`, bell `aria-haspopup="dialog"`.

### FLAG-4 — Animation regression: Library detail modals inert inside AnimatePresence (WARNING, confirms LW-01)
**`LibraryPage.tsx:606-611`** — `SkillDetailModal` and `HookDetailModal` are still rendered
inside `<AnimatePresence>`, but their root elements were converted from `motion.div` to
plain `<div>`. `AnimatePresence` only defers unmount for `motion` children, so the exit
fade/scale silently no-ops and both modals pop out instantly — inconsistent with the
still-animated sibling `AgentCapabilitiesModal` (`:597`). Functionally harmless (state-driven
open/close), but an unintended motion regression.
**Fix:** either drop the two now-inert `AnimatePresence` wrappers, or restore `motion.div`
roots on the two modals.

### FLAG-5 — Consistency: two Library backdrops off the `--scrim` token (WARNING, confirms LW-03)
**`LibraryPage.tsx:88` and `:235`** — both skill/hook modal overlays use `bg-black/40`,
while every other modal touched this phase (admin `:410/:474`, TemplateDetailModal,
DesignSystemDetailModal, CustomTemplateModal, CustomDesignSystemModal) migrated to
`bg-[var(--scrim)]` (`rgba(17,17,20,.5)`, evidence B2). Passes the retired-hex grep but is a
same-file reskin inconsistency and a slightly different scrim tone/opacity.
**Fix:** `bg-[var(--scrim)] backdrop-blur-sm` on both overlays.

### NOTE-6 — "DONE" copy in notifications is design-sanctioned, not a defect (confirm ME-01)
**`NotificationPanel.tsx:196`** — adopting `<Badge status={n.status} />` changes the
completed chip text from title-case "Completed" to uppercase **"DONE"** (`Badge` normalizes
`completed → done` and CSS-uppercases). Evidence **§B3 explicitly mandates** "Normalize
`completed → done`" and a single bordered-pill badge form. So this is **aligned with the
design authority** — record it as an accepted copy change, not a bug. (Caveat: the visual
jump title-case → ALL-CAPS is intentional per the DS chip idiom.)

### NOTE-7 — Badge status-ramp reused for tier/color chips (confirm LW-04)
**`admin/page.tsx:28-40`** (`TIER_BADGE_STATUS`: basic→queued, pro→running, enterprise→done)
and **`AccountSettings.tsx:513,594`** (`Badge status="running" label=…`). Output is correct
(explicit `label` passed, colors resolve), but tier UI is now coupled to the status ramp —
a future status-color change would silently recolor tier chips, and "enterprise = green
done-color" reads oddly. Optional: a dedicated tint prop / `TierChip`, or a greppable comment
marking the color-only reuse.

### LOW-8 — Wordmark fidelity vs B1 (informational)
**`AppHeader.tsx:105-110`, `login/page.tsx:46-52`** — B1 specifies the wordmark as
`Manrope 800 20px italic #FFFFFF + 5px #3C2CDA dot`. Implemented as `font-semibold` (600),
non-italic, ~16px (`text-base`), with a Zap icon (header) / 8px dot (login) in a brand
square. Brand-square treatment is a reasonable app-identity choice, but weight/size/italic
diverge from the mock wordmark spec. Low priority (mock HTML not in-repo; product name
differs).

### LOW-9 — Ad-hoc px font sizes instead of a tokenized ramp (informational)
Across the phase: `text-[8.5px]`, `[9px]`, `[10px]`, `[11px]`, `[12px]`, `[13px]`, `[14px]`,
`[15px]`, `[32px]`, `[36px]`, `[40px]`. Values are internally coherent and dense-by-design,
but there is no shared type scale — every size is a one-off arbitrary utility, which will
drift over time. Consider a small `text-*` token ramp if the reskin expands.

---

## Pillar Detail

### Pillar 1: Copywriting (3/4)
Deliberate, on-brand copy: "My Workflows" relabel (D-11), login "Welcome back" / "Access is
by invitation. Contact your administrator" (ND-12, no self-register), empty state "No
notifications yet / Pipeline completions will appear here", admin "User Management". The
`completed→DONE` change is design-sanctioned (NOTE-6). **Deduction:** FLAG-1 "Workflow
History" vs canonical "Run History" (§B5).

### Pillar 2: Visuals (3/4)
Consistent near-black shell idiom reused across header, login brand panel, and admin header
bar — good cross-surface cohesion (mock 02/10). Clear focal points (login hero heading,
admin table). Icon-only controls are labelled (bell `aria-label`, profile `aria-label`).
**Deduction:** wordmark under-specified vs B1 (LOW-8); cancelled icon/badge visual conflict
(FLAG-2).

### Pillar 3: Color (3/4)
Single-chroma brand `#3C2CDA`, warm ink, beige surfaces and the full status ramp
(running-blue / done-green / failed-red / cancelled-amber / queued-grey) all resolve in
`styles/globals.css` and match §B2/§B3. Purple-underline active nav (`border-brand`, §C
decision) applied uniformly. **Deductions:** FLAG-2 (cancelled icon grey ≠ amber) and FLAG-5
(2 Library backdrops `bg-black/40` off the `--scrim` token).

### Pillar 4: Typography (3/4)
`font-sans` + semibold/medium/bold used consistently; tabular numerals available.
**Deductions:** ad-hoc px size proliferation (LOW-9) and non-spec wordmark weight/size/italic
(LOW-8).

### Pillar 5: Spacing (4/4)
Standard Tailwind spacing scale throughout (no arbitrary px paddings/margins found in the
audited chrome). Radius ladder matches evidence B2 exactly: `--radius-button 10`,
`--radius-card 14`, `--radius-menu 12`, `--radius-pill 999`, `--radius-tag 5`. Elevation
tokens (`raised/menu/notif`) match B2 shadows. No finding.

### Pillar 6: Experience Design (3/4)
Loading ("Signing in…", spinner icons), error (login inline error card with
`--status-failed` tokens; admin `AlertCircle`), and empty (notifications) states are all
present. Profile-menu a11y is genuinely correct: `aria-haspopup="menu"` + `aria-expanded`
tracking state, `role=menu`/`menuitem` on every child, `aria-current` on active nav, Escape
closes + refocuses the trigger; the bell mirrors Escape→refocus. **Deductions:** FLAG-3
(NotificationPanel `role=menu` mis-modeled), FLAG-4 (Library exit-animation regressed).
**Human-verify (needs server):** modal focus-trap + initial focus, keyboard tab order,
SR announcement of the notification list, and that opening the bell auto-marking-all-read
(`NotificationPanel.tsx:72-78`) is the intended UX (it clears the unread badge on open).

---

## Files Audited
- `frontend/src/components/layout/AppHeader.tsx`
- `frontend/src/components/ui/NotificationPanel.tsx`
- `frontend/src/components/ui/Badge.tsx` (status map cross-check)
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/admin/page.tsx`
- `frontend/src/components/library/LibraryPage.tsx`
- `frontend/src/components/settings/AccountSettings.tsx` (Badge reuse cross-check)
- `frontend/src/components/workflow/prototype/{TemplateDetailModal,CustomTemplateModal,DesignSystemDetailModal,CustomDesignSystemModal}.tsx` (scrim consistency)
- `frontend/src/styles/globals.css` (token/contrast source of truth)

_No dev server; visual screenshots not captured. Contrast is computed, not rendered-measured._

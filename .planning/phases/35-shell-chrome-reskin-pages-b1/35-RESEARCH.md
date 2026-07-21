# Phase 35: Shell Chrome + Reskin Pages [B1] — Research

**Researched:** 2026-07-09
**Domain:** Frontend reskin (Next.js/React/Tailwind v4 `@theme`) — convert 10 shell/page surfaces onto the already-landed Phase-32 token+primitive layer; wire the few remaining static controls to EXISTING endpoints. No backend, no new packages.
**Confidence:** HIGH (all claims grounded in files read this session; token layer + primitives + analog verified by direct read).

## Summary

Phase 35 is a **pure frontend reskin** with a thin "keep-the-richer-behavior" wiring layer. The Phase-32 token layer (`globals.css` `@theme inline`) and the `components/ui/*` primitives (Button/Card/Tabs/Badge/Pill/NotificationPanel) are landed and verified — the destination language exists [VERIFIED: read globals.css:12-175, Button/Card/Tabs/Badge/Pill.tsx]. The mechanical recipe is: **replace ad-hoc hex/Tailwind-default classes with the token utility classes** (`bg-surface-card`, `text-ink-900`, `border-line-border`, `bg-brand`, `font-sans`, `rounded-[var(--radius-*)]`) and **swap ad-hoc elements for the ui primitives**. The single fully-worked, verified analog to copy is `src/components/results/AuditTab.tsx` (35 token-class usages, correct status/severity handling) — plus `AgentThinkingTab.tsx` and `chat/RunChatLane.tsx`.

**Critical correction to the task framing:** the two analogs named in the brief besides AuditTab — `preview/PrototypePreview.tsx` and `handoff/ReportViews.tsx` — are **NOT reskinned** and must NOT be used as exemplars. PrototypePreview still carries 4 retired-palette lines (`#f5f5f0`, `#1B2A4A`) and zero token classes; ReportViews uses raw `gray/green/purple` Tailwind defaults with zero token classes [VERIFIED: grep on both files, 2026-07-09]. Use **AuditTab / AgentThinkingTab / RunChatLane** as the copy source.

**Second correction:** Deliverable #2 ("make static mock fields REAL controls") is largely already done. The current-product `AccountSettings.tsx` is **fully wired** — email via `getMe`, password via `changePassword`, model via `getPreferences`/`updatePreferences`, constitution via raw `fetch('/api/settings/constitution')` GET/PUT/DELETE, limits from `TIER_PIPELINES` [VERIFIED: read AccountSettings.tsx:97-163, 636-686]. The "static fields" are in the *mock*, not the product. Account Settings is therefore a **RESKIN**, not a static→real build. Same story for Admin (fully wired) and Login (fully wired form).

**Primary recommendation:** Treat every target as "swap classes to tokens + swap elements to primitives, preserve all wiring and all `data-testid`/`id`/role selectors, add the login dark brand panel, rename the nav label Catalogue→My Workflows." Verify by delta against the pre-existing mocked-Playwright baseline + per-file retired-palette grep=0 + `tsc --noEmit`. The picker/gates paths in the brief are wrong — see corrected paths below.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Nav = Home · Library · My Workflows (D-11).** "Catalogue" reserved for the future marketplace — never label saved workflows "Catalogue". The `WorkflowCatalog`→`HomeLaunchGrid` rename is Phase 36 (NOT here).
- **Reskin-look, keep-behavior (D-15):** adopt the Workspace-v2 visual language on the Phase-32 tokens; REUSE existing components + the product's richer behavior; NO per-page palette fork. Shell-chrome canonical = Workspace v2 (evidence 02).
- **Login/Admin reskin-only (ND-12):** keep the product's richer wiring (password-create, Runs/Role/Joined columns); ADD the login dark brand panel; DROP the identity traps (SSO/SCIM/password-reset/email-invite/account-suspension — mock fiction, each a separate backend project); DEFER admin Status/Last-active + email-invite (additive backend, not this phase).
- **DS picker = the real ~14 count (LOCK-F)** — no catalog expansion; ignore the mock's "150 systems".
- **Resolved cosmetics (LOCK-F / ND-13.1-5):** running=blue `#3C2CDA` (`--color-status-running`), "Not run"=grey (`--color-status-queued`), nav active-state = purple-underline, avatar=rounded-square, radius buttons 10 / cards 14. NOT open questions.
- **Notifications PANEL is chrome-only**; the live feed is Phase 38.
- **INVARIANTS:** SC-001/INV-1 (nav/shell/pickers keyed on generic routes/data, NEVER a workflow-name branch), INV-3 (FE-only; the 5 backend goldens untouched by construction), token authority (consume Phase-32 `@theme` tokens + primitives; NO new hardcoded palette), a11y (nav/profile-menu/notifications/popover keyboard+aria), NO new backend (wire only to existing endpoints), LOCK-B (no transport touch).

### Claude's Discretion
- CONTEXT.md was auto-generated (discuss skipped). No explicit discretion list; treat cosmetic micro-decisions inside the locked token ladder as free (spacing, icon choice) provided token authority + behavior parity hold.

### Deferred Ideas (OUT OF SCOPE)
- Identity traps: SSO/SCIM, password reset, email invitations, account-suspension (DROPPED).
- Admin Status/Last-active columns + email-invite flow (additive backend — deferred).
- Live notifications FEED (Phase 38 — this phase does panel chrome only).
- Home/History/My-Workflows restructure + `WorkflowCatalog`→`HomeLaunchGrid` rename (Phase 36).
- Configure/Composer/Wizard (Phase 37). Analytics data (Phase 38). Run-detail / Agent drawer / Workflow dialog (Phase 36/37). Handoff screen (deferred post-v2.0). Concierge live-wiring (Phase 34).
</user_constraints>

<phase_requirements>
## Phase Requirements

Derived from CONTEXT.md deliverables (ROADMAP SC 1-2 + POR §82 + ND-12). No formal REQ-IDs supplied by the orchestrator; assigned local IDs for the planner/validation map.

| ID | Description | Research Support |
|----|-------------|------------------|
| B1-01 | Shell chrome: dark top bar `#111114` + centered nav pill (Home · Library · My Workflows) + profile menu + notifications panel, on tokens | AppHeader.tsx + NotificationPanel.tsx are the two files; recipe + a11y gaps documented below |
| B1-02 | Account Settings reskin (already-wired controls → token language) | AccountSettings.tsx fully wired; endpoint map below; RESKIN not static→real |
| B1-03 | Template picker, DS picker (~14 real count), Review-gates popover restyle | Corrected paths: `workflow/prototype/{TemplateGallery,DesignSystemPicker}.tsx`, `workflow/ReviewGatesSection.tsx` |
| B1-04 | Library (Agents/Skills/Hooks) restyle, real controls where mock was static | LibraryPage.tsx — search already wired; Tabs/Card primitives; data is local constants |
| B1-05 | Login reskin + add 46% dark brand panel, keep wired form (error/loading/redirect-by-is_admin) | login/page.tsx retired-token map + e2e selector-preservation list below |
| B1-06 | Register: no work (redirect stub already correct) | register/page.tsx — token swap of `#f5f5f0` only |
| B1-07 | Admin reskin (chrome/stats/table/tier-dropdown/delete/create-modal), keep Runs/Role/Joined + password-create | admin/page.tsx fully wired; defer Status/Last-active/email-invite |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Shell chrome / nav / profile menu / notifications panel | Browser/Client (React) | — | Pure presentation + client state; notifications feed data is Phase 38 |
| Account Settings controls | Browser/Client | API (existing `/api/settings/*`, `/api/auth/*`) | Controls already wired; reskin is client-only |
| Template/DS/Review-gates pickers | Browser/Client | — | Selection state is local; DS ~14 count is static/local data |
| Library browse | Browser/Client | — | Agent/skill/hook data are local constants in LibraryPage |
| Login / Register auth | Browser/Client | API (`/api/auth/login` existing) | Form already posts to existing endpoint; reskin adds brand panel only |
| Admin user management | Browser/Client | API (existing `/api/admin/*`) | Fully wired; reskin only, no new columns |

All capabilities live in the **Browser/Client** tier. **No API/DB/CDN tier work in this phase** (INV-3, NO new backend). This satisfies SC-001/INV-1: nav and pickers are keyed on generic routes/local data, never a workflow-name branch.

## Standard Stack

No new packages. Everything needed is already installed and landed.

### Core (existing, verified)
| Library / Asset | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Tailwind CSS v4 `@theme inline` | (in `globals.css:1` `@import "tailwindcss"`) | Token utility classes (`bg-surface-card`, `text-ink-900`, …) | Phase-32 token layer; the destination language [VERIFIED: globals.css:12-57] |
| `components/ui/Button.tsx` | landed | primary/secondary button, radius-10, Manrope 600 12.5px | Reuse instead of ad-hoc `<button>` [VERIFIED: read] |
| `components/ui/Card.tsx` | landed | surface-card + line-border + radius-14 | Reuse for all cards/panels [VERIFIED: read] |
| `components/ui/Tabs.tsx` | landed | underline tabs, active = ink-900 + 2px brand, `role=tablist/tab`, `data-testid=tab-{id}` | Reuse for Library/Settings tab bars [VERIFIED: read] |
| `components/ui/Badge.tsx` | landed | status chip; normalizes `completed→done`, unknown→queued | Reuse for status pills [VERIFIED: read] |
| `components/ui/Pill.tsx` | landed | radius-999 chip, white surface, line-control border | Reuse for filter/meta chips [VERIFIED: read] |
| `components/ui/NotificationPanel.tsx` | landed BUT NOT tokenized (8 retired lines) | the notifications bell+dropdown | Reskin target itself, not a clean primitive yet |
| `next/font` Manrope + Heebo | landed | `--font-manrope`→`--font-sans`, `--font-heebo`→`--font-serif` | [VERIFIED: layout.tsx:2-33, globals.css:14-15] |
| `motion/react` | installed (used everywhere) | existing entrance animations | Keep as-is; do not add new motion libs |
| `lucide-react` | installed | icons | Keep |

### Token utility class reference (the destination vocabulary)
From `globals.css` `@theme inline` (these generate Tailwind utilities):
- **Brand:** `bg-brand`, `text-brand`, `border-brand`, `hover:bg-brand-pressed`, `bg-brand-fill`, `border-brand-border`, `bg-brand-violet-tint`, `text-brand-on-dark`
- **Ink (text):** `text-ink-900 … text-ink-200` (900=`#15161A` headings, 500=`#6E6F76` muted, 400=`#8A8B82` faint)
- **Surface (bg):** `bg-surface-paper` (`#F0EEE7`), `bg-surface-warm` (`#F6F4EE`), `bg-surface-card` (`#FCFBF7`), `bg-surface-white`, `bg-surface-near-black` (`#111114` — the dark top bar), `bg-surface-ink-black`
- **Line (border):** `border-line-border`, `border-line-divider`, `border-line-control`, `border-line-faint-row`, `border-line-faint`
- **Status (text only via `@theme`):** `text-status-running` (blue `#3C2CDA`), `text-status-done`, `text-status-failed`, `text-status-amber`, `text-status-queued`
- **Status fill/border ramp** lives in `:root` (NOT `@theme`), so consumed via arbitrary var utilities: `bg-[var(--status-running-fill)]`, `border-[var(--status-running-border)]` (same pattern for done/failed/amber/queued). [VERIFIED: Badge.tsx:21-31, globals.css:94-108]
- **Radius:** `rounded-[var(--radius-button)]` (10), `-list-row` (11), `-menu` (12), `-card` (14), `-hero` (18), `-tag` (5), `-pill` (999)
- **Fonts:** `font-sans` (Manrope — headings/labels/numbers), `font-serif` (Heebo — body; note: current pages misuse `font-serif` italic for headings — mock uses Manrope/`font-sans` for headings, see Pitfall 4)

**Installation:** none. `## Package Legitimacy Audit` is N/A — this phase installs zero external packages [VERIFIED: no `npm install` in scope; all imports resolve to existing deps].

## Architecture Patterns

### System data-flow (reskin is presentation-only; wiring unchanged)

```
User ──▶ Next route / DashboardLayout mainView
          │
          ├─ app/login/page.tsx ──── login() ──▶ POST /api/auth/login ──▶ redirect by is_admin
          ├─ app/admin/page.tsx ──── adminListUsers/UpdateTier/CreateUser/DeleteUser ──▶ /api/admin/*
          ├─ layout/AppHeader.tsx ── onNavigate(page) ──▶ DashboardLayout view switch
          │        └─ ui/NotificationPanel.tsx (props: notifications[], unreadCount) [Phase-38 feed]
          ├─ settings/AccountSettings.tsx ── getMe / getPreferences / updatePreferences
          │        │                          changePassword / fetch(/api/settings/constitution)
          ├─ library/LibraryPage.tsx ─────── local constants (ALL_AGENTS_COMBINED/SKILLS/HOOKS)
          └─ workflow/prototype/{TemplateGallery,DesignSystemPicker}.tsx + workflow/ReviewGatesSection.tsx

Reskin changes ONLY the className/element layer of each box.
Data arrows (──▶) are untouched (INV-3, LOCK-B).
```

### The mechanical reskin recipe (copy from AuditTab.tsx)

**Rule:** every raw color/radius/font becomes a token utility. Concrete before→after, patterned on the verified analog `src/components/results/AuditTab.tsx`:

Card / panel:
```tsx
// BEFORE (ad-hoc — e.g. admin/page.tsx:250)
<div className="bg-white rounded-xl border border-gray-100 px-4 py-3.5 shadow-sm">
// AFTER (token language — matches AuditTab.tsx:182 idiom, or use <Card>)
<div className="bg-surface-card border border-line-border rounded-[var(--radius-card)] px-4 py-3.5">
//   …or import { Card } and use <Card className="px-4 py-3.5">
```

Primary button:
```tsx
// BEFORE (login/page.tsx:124)
className="w-full rounded-xl bg-[#1B2A4A] px-4 py-3 text-white hover:bg-[#243456]"
// AFTER — use the primitive
import { Button } from "@/components/ui/Button";
<Button type="submit" className="w-full">Sign in</Button>   // primary is default: bg-brand/white, radius-10
```

Text + muted:
```tsx
// BEFORE  text-gray-900 / text-gray-400 / text-gray-500
// AFTER   text-ink-900   / text-ink-400   / text-ink-500   (AuditTab.tsx:188-199)
```

Status pill (governance/run status):
```tsx
// Use the Badge primitive, or the AuditTab VerdictChip pattern (AuditTab.tsx:107-135):
<span className="… text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]">
```

Dark top bar (shell):
```tsx
// BEFORE (AppHeader.tsx:77)  bg-[#111827] border-b border-[#1f2937]
// AFTER                      bg-surface-near-black border-b border-line-border/10
//   (near-black = #111114, the canonical shell bar per evidence 02/11 §B1)
```

**Component-swap map (ad-hoc element → primitive):**
| Ad-hoc element found | Replace with |
|---|---|
| `<div className="bg-white rounded-xl border …">` cards | `<Card>` (`ui/Card.tsx`) |
| ad-hoc `<button className="bg-[#1B2A4A]…">` | `<Button variant="primary\|secondary">` |
| underline tab bars (Library, Settings tier tabs) | `<Tabs tabs=… active=… onChange=…>` (`ui/Tabs.tsx`) |
| status/role/tier chips | `<Badge status=…>` or `<Pill>` |
| meta/filter chips (counts, categories) | `<Pill>` |

### Anti-Patterns to Avoid
- **Copying PrototypePreview/ReportViews.** They are NOT reskinned (retired palette / raw Tailwind). Copy AuditTab/AgentThinkingTab/RunChatLane only.
- **Per-page palette fork** (D-15). No new hex; everything through `@theme`/`:root` vars.
- **Rebuilding to mock face value** — regresses richer product behavior (D-15). E.g. do NOT drop admin Runs/Role/Joined, do NOT swap admin password-create for an invite flow, do NOT make Library search inert.
- **Branching on workflow name** in nav/pickers (SC-001/INV-1).
- **Renaming `WorkflowCatalog`→`HomeLaunchGrid`** — that is Phase 36. Only change the nav *label* text.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Buttons / cards / tabs / chips | new styled elements | `ui/Button|Card|Tabs|Badge|Pill` | Landed, token-correct, `data-testid`/roles baked in |
| Status color mapping | a new status→color map | `Badge` (normalizes) or AuditTab's `VERDICT_CLASS` | Canonical §B3 already encoded [VERIFIED: Badge.tsx:21-42] |
| Fonts | new font imports | existing `--font-sans`/`--font-serif` | Manrope/Heebo already bound [VERIFIED: layout.tsx] |
| Auth / admin / settings data flow | new fetch code | existing `api.ts` functions (listed below) | Wiring is done and richer than mock |
| Constitution CRUD | new endpoint calls | existing `fetch('/api/settings/constitution')` GET/PUT/DELETE | Already implemented [VERIFIED: AccountSettings.tsx:640-686] |

**Key insight:** the value of this phase is *deletion of ad-hoc styling*, not new construction. Any new component or fetch is a smell.

## Account Settings static→real: EXISTING endpoints (deliverable B1-02)

All four sections are ALREADY backed by real functions [VERIFIED: AccountSettings.tsx + api.ts]:

| Section | Data source (existing function) | Endpoint | api.ts line |
|---------|--------------------------------|----------|-------------|
| Profile — email | `getMe(token)` → `user.email` | `GET /api/auth/me` | api.ts:131 |
| Profile — password | `changePassword(token, current, new)` | `POST /api/auth/change-password` | api.ts:442 |
| AI Model | `getPreferences(token)` + `updatePreferences(token, modelId)` | `GET`/`PUT /api/settings/preferences` | api.ts:476 / 483 |
| AI Model (rich metadata) | `getCapabilities(token)` → `model_catalog` | `GET /api/capabilities` | api.ts:598 |
| Usage & Limits | `TIER_PIPELINES` / `TIER_LABELS` (local, from `@/lib/entitlements`) | none (client) | AccountSettings.tsx:11,66 |
| Constitution | raw `fetch('/api/settings/constitution')` GET/PUT/DELETE | `/api/settings/constitution` | AccountSettings.tsx:640,655,675 |

Deliverable B1-02 is therefore **reskin-only**: no new controls, no new backend. (The usage-limits *numbers* like "50/500/Unlimited" are hardcoded display in the table AccountSettings.tsx:566-574 — leave as-is; a real usage-metering API is out of scope, mock-fiction.)

## Login reskin (B1-05): retired tokens + selector preservation

Current `login/page.tsx` is a real wired form (redirect by `data.user.is_admin`, error state, loading state) [VERIFIED: login/page.tsx:16-35]. Reskin = swap palette + add the 46% dark brand panel; keep wiring.

**Retired tokens present (4 grep hits + adjacent non-token classes) → replacement:**
| Current | Line | Replace with |
|---------|------|--------------|
| `style={{ background:"#f5f5f0" }}` | :40 | `className="bg-surface-paper"` (`#F0EEE7`) |
| `fontFamily:"var(--font-inter)"` (eyebrow) | :57 | `font-sans` (Manrope) |
| `fontFamily:"var(--font-fraunces)"` (H1) | :63 | `font-sans` (mock headings are Manrope, §B1) |
| `focus:border-[#1B2A4A] focus:ring-[#1B2A4A]/10` | :96,:113 | `focus:border-brand` + `.input-focus` util (globals.css:249) |
| `bg-[#1B2A4A] hover:bg-[#243456]` (Sign in) | :124 | `<Button type="submit">` (bg-brand) |
| `text-gray-*` throughout | many | `text-ink-*` |

**Add the dark brand panel (RESTRUCTURE, low effort):** left 46% `bg-surface-near-black` panel with wordmark (Manrope 800 italic + `#3C2CDA` dot), eyebrow, headline, subhead — mirror evidence 02 L26-40 / evidence 10 §2. Right column keeps the form. **DROP** the SSO button and "Forgot?" link (identity traps — no backend).

**MUST preserve for e2e (ts-a.auth.spec.ts) [VERIFIED: read spec]:**
- `id="email"` and `id="password"` (spec uses `page.locator("#email"/"#password")`, lines 18-19)
- Submit button accessible name exactly **"Sign in"** (line 20)
- Heading text exactly **"Welcome back"** (line 13) — the mock says "Sign in" for the heading; keep "Welcome back" or the auth spec regresses. (Reskin-by-delta: preserve the string.)
- Post-login heading on home is "What would you like to build today?" (line 21) — not this phase's surface, but don't break the redirect.

## Admin reskin (B1-07): keep richer wiring, defer backend columns

Current `admin/page.tsx` is fully wired [VERIFIED: read]: `adminListUsers` (api.ts:505), `adminUpdateTier` (:512), `adminCreateUser` (:524, email+password+plan+grant-admin), `adminDeleteUser` (:538); admin-gate via `getMe().is_admin`; search wired; toast/loading/empty states present.

**In scope (reskin only):** header bar (`bg-white`→ dark `bg-surface-near-black` + wordmark + "Admin" chip), 5 stat cards, users table, `TierDropdown`, create-user modal, delete-confirm modal, toast — all `#1B2A4A`/`gray-*`/`#E8EDF5`/`#F4F5F7` → tokens (11 retired-palette lines).
**KEEP (do NOT regress):** Runs (`workflow_run_count`), Role (`is_admin`), Joined (`created_at`) columns; the password-create modal (email+password+plan+grant-admin).
**DEFER (mock-only, backend-needed):** Status column, Last-active column, email-invite flow. The `AdminUser` type has NO `display_name`/`status`/`last_active_at` [VERIFIED: api.ts:496-503] — do not add columns for fields the API doesn't return.
**Copy-string note:** current delete copy "permanently delete the user and all their data" (admin/page.tsx:466) — keep the product's stronger copy; ignore the mock's "run history retained for audit."

## a11y for the interactive shell (deliverable B1-01 + pickers)

Baseline present vs. gaps to close (all verified by direct read):

| Surface | File | Present today | Gap to close (testable) |
|---------|------|---------------|--------------------------|
| Profile menu | AppHeader.tsx:160-245 | outside-click close; chevron rotate | no `aria-haspopup="menu"`, no `aria-expanded={profileOpen}`, no `role="menu"`/`menuitem`, no Escape-to-close, no focus-return. Add these. |
| Notifications bell | NotificationPanel.tsx:69-80 | `aria-label="Notifications"`; outside-click close | no `aria-expanded`, no `aria-haspopup`, no Escape, dropdown has no `role`. Add. |
| Nav pill | AppHeader.tsx:89-123 | `<button>` items (keyboard-focusable) | add `aria-current="page"` on the active item; active-state = **purple-underline** (LOCK-F), currently white-fill pill |
| Tier dropdown | admin/page.tsx:58-94 | `<button>` + overlay | no `aria-expanded`/`role=menu`/Escape. Add. |
| Review-gates | workflow/ReviewGatesSection.tsx:105-121 | already has `aria-expanded` on the disclosure; native `<input>` toggles | GOOD baseline — verify labels/`aria-controls`, add Escape if it becomes a popover |
| Tabs (Library/Settings) | ui/Tabs.tsx:26-48 | `role=tablist/tab` + `aria-selected` | GOOD — reuse the primitive rather than ad-hoc tab bars |

**Standard pattern to apply** (menu button): `aria-haspopup="menu"` + `aria-expanded={open}` on the trigger; `role="menu"` on the dropdown, `role="menuitem"` on rows; `onKeyDown` Escape→close+refocus trigger. Use a small shared hook or inline handler; do not add a menu library.

## Reuse map (all 10 targets → primitives/paths)

| # | Target (VERIFIED path) | Retired lines | Delta | Primitives to apply |
|---|------------------------|---------------|-------|---------------------|
| 1 | `components/layout/AppHeader.tsx` | 2 (+ many non-token gray/#111827/#1f2937/blue-600) | RESKIN + nav label + a11y | dark bar `bg-surface-near-black`; nav purple-underline; profile menu a11y; Button for actions |
| 2 | `components/layout/DashboardLayout.tsx` | 0 | RESKIN (host of settings/library views; check for ad-hoc chrome) | tokens where ad-hoc |
| 3 | `components/ui/NotificationPanel.tsx` | 8 | RESKIN (panel chrome only; feed = Phase 38) | tokens; Badge for status labels; a11y |
| 4 | `components/settings/AccountSettings.tsx` | 21 | RESKIN (already wired) | Card, Button, Tabs (tier tabs), Pill; token swap |
| 5 | `components/library/LibraryPage.tsx` | 8 | RESKIN (search already wired; data local) | Tabs (Agents/Skills/Hooks), Card (agent/skill/hook cards), Pill (filter chips) |
| 6 | `components/workflow/prototype/TemplateGallery.tsx` | 11 | RESKIN | Card, Button, Pill (path corrected from brief) |
| 7 | `components/workflow/prototype/DesignSystemPicker.tsx` | 12 | RESKIN; keep real ~14 count (LOCK-F) | Card, Button, Pill (path corrected) |
| 8 | `components/workflow/ReviewGatesSection.tsx` | 5 | RESKIN (a11y baseline good) | Card, token swap; keep `aria-expanded` |
| 9 | `app/login/page.tsx` | 4 | RESKIN + add brand panel; keep form | Button; preserve `#email`/`#password`/"Sign in"/"Welcome back" |
| 10 | `app/register/page.tsx` | 1 | trivial | swap `#f5f5f0`→`bg-surface-paper`; keep redirect stub |
| — | `app/admin/page.tsx` | 11 | RESKIN; keep Runs/Role/Joined + pw-create | Card, Button, Badge (tier/role), token swap; a11y on TierDropdown |

**Note on brief's paths:** the CONTEXT brief implied `components/workflow/{TemplateGallery,DesignSystemPicker}.tsx`; the real files are under `components/workflow/prototype/` [VERIFIED: find, 2026-07-09]. Sibling detail modals (`TemplateDetailModal`, `DesignSystemDetailModal`, `CustomDesignSystemModal`, `CustomTemplateModal`, `TemplateCard`, `PPTTemplateGallery`) also live there — the planner should decide whether the picker reskin includes these sibling modals (they render inside the picker flow).

## Runtime State Inventory

This is a reskin of styling + a nav-label string change. It is NOT a data/identifier rename.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no DB keys/collection names change. Verified: NO new backend (INV-3). | none |
| Live service config | None — no external service config touched. | none |
| OS-registered state | None. | none |
| Secrets/env vars | None — no env var names referenced by reskin. | none |
| Build artifacts | None — no package rename; no egg-info/binary equivalent for a CSS class swap. | none |

**Nav label "Catalogue"→"My Workflows"** (AppHeader.tsx:121) is a display-string change only; the route stays `saved-workflows` and the `onNavigate("saved-workflows")` handler is unchanged [VERIFIED: AppHeader.tsx:113-122]. Not a code identifier rename (the `WorkflowCatalog`→`HomeLaunchGrid` rename is Phase 36).

## Common Pitfalls

### Pitfall 1: Copying an un-reskinned "analog"
**What goes wrong:** using `PrototypePreview.tsx`/`ReportViews.tsx` as the pattern re-introduces retired palette / raw Tailwind and fails grep=0.
**How to avoid:** copy `results/AuditTab.tsx`, `results/AgentThinkingTab.tsx`, `chat/RunChatLane.tsx` only.
**Warning sign:** you typed `bg-[#…]` or `text-gray-…` in a touched file.

### Pitfall 2: Grep gate is a FLOOR, token-authority is the CEILING
**What goes wrong:** the retired-palette grep only matches `#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`. A file can score 0 yet still be full of non-token colors (`#111827`, `bg-blue-600`, `text-gray-400`) — e.g. AppHeader scores 2 on the gate but has ~30 non-token classes.
**How to avoid:** convert ALL ad-hoc colors/radii to tokens (D-15 token-authority), not just the six grep patterns. Verify with a broader grep (`bg-\[#|text-\[#|bg-(blue|gray|slate)-|#[0-9A-Fa-f]{6}`) as a self-check.

### Pitfall 3: Breaking e2e selectors during reskin
**What goes wrong:** renaming ids/roles/testids/heading strings silently breaks mocked-Playwright (auth, catalog, saved-workflows specs).
**How to avoid:** preserve `#email`/`#password`, `role=button name="Sign in"`, heading "Welcome back", `data-testid="tab-*"`, and any `getByRole/getByText` targets. Reskin classes, not selectors.
**Warning sign:** delta vs baseline shows a newly-failing auth/nav test.

### Pitfall 4: Heading font drift (Manrope vs Heebo)
**What goes wrong:** current pages use `font-serif` italic for headings; `font-serif` now = Heebo. The mock's headings are Manrope (`font-sans`). Blindly keeping `font-serif` keeps the wrong face.
**How to avoid:** set page headings/wordmarks to `font-sans` (Manrope) per evidence 11 §B1; reserve `font-serif` (Heebo) for body prose. Confirm against AuditTab (uses `font-sans` for labels).

### Pitfall 5: Regressing richer behavior to match the mock
**What goes wrong:** dropping admin Runs/Role/Joined, making Library search inert, swapping admin pw-create for invite, adding SSO/Forgot — all "face-value" mock rebuilds that regress (D-15/ND-12).
**How to avoid:** treat the mock as *visual language only*; keep every wired behavior the product already has.

## Code Examples

### Verified analog to copy — AuditTab token idioms
```tsx
// Source: src/components/results/AuditTab.tsx:182 (card), :188-199 (ink text), :107-135 (status chip)
<div className="bg-surface-card border border-line-border rounded-[var(--radius-list-row)] px-3 py-2.5">
  <span className="text-[12px] font-semibold text-ink-800 truncate">{label}</span>
  <span className="text-[10px] text-ink-500">{meta}</span>
</div>

// status chip (fill/border via :root vars; text via @theme utility)
<span className="… border rounded-[var(--radius-tag)] px-1.5 py-0.5
  text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]">
  {outcome}
</span>
```

### Menu-button a11y pattern to add (profile menu / tier dropdown)
```tsx
// trigger
<button aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(v=>!v)} …>
// dropdown
<div role="menu" onKeyDown={(e)=>{ if(e.key==="Escape"){ setOpen(false); triggerRef.current?.focus(); } }}>
  <button role="menuitem" …>Account Settings</button>
</div>
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Ad-hoc `#1B2A4A` navy + Inter/Fraunces (pre-Phase-32) | `@theme` token utilities + Manrope/Heebo | This phase completes the migration for shell/pages |
| Raw `<button>`/`<div>` styling | `ui/*` primitives | Fewer classes, guaranteed token correctness |

**Deprecated/outdated:** the navy palette (`#1B2A4A`), `#2563eb`, `#f5f5f0`, Inter, Fraunces, JetBrains — all must reach grep=0 in touched files (the #1 acceptance gate).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Nav active-state = purple-underline is FINAL (LOCK-F resolved it) | a11y / nav | Low — locked; if planner wants pill-fill, evidence 11 §C#1 is already decided as underline |
| A2 | Picker reskin scope includes the sibling detail modals under `workflow/prototype/` | Reuse map | Medium — if excluded, picker "Browse" detail views stay un-reskinned; planner should decide explicitly |
| A3 | The usage-limits numbers table in AccountSettings stays hardcoded (no usage API in scope) | B1-02 | Low — mock-fiction per evidence 02 §2.8; matches NO-new-backend |
| A4 | `DashboardLayout.tsx` needs little/no reskin (0 retired lines) but should be spot-checked for ad-hoc chrome around mounted views | Reuse map #2 | Low — 0 retired but may host non-token wrappers |

## Open Questions (RESOLVED)

1. **Picker sibling modals in/out of scope?** — **RESOLVED: IN scope.**
   - Known: `TemplateGallery`/`DesignSystemPicker` live in `workflow/prototype/` with sibling modals + `TemplateCard`.
   - Resolution: included explicitly as tasks in plans 35-03 (TemplateDetailModal, CustomTemplateModal, TemplateCard) and 35-04 (DesignSystemDetailModal, CustomDesignSystemModal) — they render in the same picker flow, so excluding them would leave "Browse" detail views un-reskinned.
2. **NotificationPanel: reskin now vs. promote to a clean `ui/` primitive?** — **RESOLVED: reskin in place this phase.**
   - Known: it lives in `ui/` but carries 8 retired lines and is imported by AppHeader.
   - Resolution: reskinned in place in plan 35-01 (panel chrome only); the live feed is left to Phase 38.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node/npm (frontend) | build/test | ✓ (repo builds) | per repo | — |
| `vitest` | unit/token tests | ✓ | configured (`vitest.config.ts`) | — |
| `playwright` mocked project | e2e delta | ✓ | `--project=mocked` exists | — |
| Live backend/server | — | ✗ (offline) | — | Not needed — verify by mocked delta + tsc + grep (do not chase live-green) |

**Missing with fallback:** live server — not required; all verification is offline (mocked Playwright delta, vitest, tsc, grep).
**Missing, blocking:** none.

## Validation Architecture

Nyquist validation ENABLED (no `nyquist_validation:false` found). Verify BY DELTA vs the pre-existing mocked baseline (DEF-29-06-1) — do NOT chase absolute-green.

### Test Framework
| Property | Value |
|----------|-------|
| Unit framework | Vitest — `vitest.config.ts`, `vitest.setup.ts` |
| e2e framework | Playwright — `playwright.config.ts`, project `mocked` (and `live`) |
| Quick unit run | `cd frontend && npm run test` (= `vitest --run`) |
| e2e (mocked) | `cd frontend && npm run e2e` (= `playwright test --project=mocked`) |
| Type identity | `cd frontend && npx tsc --noEmit` |
| Lint | `cd frontend && npm run lint` (= `eslint`) |
| Retired-palette gate (#1) | `grep -rEn '#1B2A4A\|#2563eb\|#f5f5f0\|\bInter\b\|\bFraunces\b\|\bJetBrains\b' <touched-file>` must = 0 |
| Token-authority self-check | `grep -rEn 'bg-\[#\|text-\[#\|#[0-9A-Fa-f]{6}\|bg-(blue\|gray\|slate\|indigo)-' <touched-file>` should trend to 0 |

### Per-deliverable evidence map (minimum "done" proof)
Each row = (grep-clean) + (primitive/token usage present) + (behavior-preserving test/mocked-delta clean) + (a11y assertion where interactive).

| Req | Behavior | Evidence commands | Baseline gap? |
|-----|----------|-------------------|---------------|
| B1-01 shell chrome | dark bar + nav Home·Library·My Workflows + profile menu + notif panel; a11y | grep=0 on AppHeader+NotificationPanel; assert `aria-expanded`/`aria-haspopup`/`role=menu`/Escape (new test); `npm run e2e` delta clean; `tsc` | Wave 0: add `AppHeader.a11y.test.tsx` + `NotificationPanel.a11y.test.tsx` |
| B1-01 nav label | label reads "My Workflows", routes to `saved-workflows` | grep for "Catalogue" = 0 in AppHeader; existing `ts-z2.saved-workflows.spec.ts` delta clean; `DashboardLayout.catalogHome.test.tsx` still green | existing test covers routing |
| B1-02 settings | reskin; wiring unchanged | grep=0 on AccountSettings; token usage present; `npm run test` (add render test asserting `getPreferences`/`changePassword` still called) | Wave 0: add `AccountSettings.render.test.tsx` (mock api) |
| B1-03 pickers | reskin; DS shows real ~14 count | grep=0 on the two `prototype/` files + ReviewGatesSection; `ReviewGatesSection.test.tsx` still green; assert DS count is local ~14 not "150" | existing ReviewGatesSection.test.tsx |
| B1-04 library | reskin; search still filters; Tabs primitive | grep=0 on LibraryPage; render test asserts typing in search filters agents; Tabs `role=tab` present | Wave 0: add `LibraryPage.reskin.test.tsx` |
| B1-05 login | reskin + brand panel; form still logs in + redirects | grep=0 on login/page.tsx; `ts-a.auth.spec.ts` delta clean (preserves `#email`/`#password`/"Sign in"/"Welcome back"); brand panel present | existing ts-a.auth covers form; add a render test for brand panel presence |
| B1-06 register | token swap only | grep=0 on register/page.tsx; still redirects to /login (existing behavior) | existing auth spec |
| B1-07 admin | reskin; Runs/Role/Joined + pw-create kept; no Status/Last-active | grep=0 on admin/page.tsx; render test asserts 6 columns incl. Runs/Role/Joined and create-modal has password field; TierDropdown `aria-expanded` | Wave 0: add `admin.reskin.test.tsx` |

### Sampling Rate
- **Per task commit:** `npx tsc --noEmit` + retired-palette grep on the file(s) touched.
- **Per wave merge:** `npm run test` (vitest) + `npm run e2e` (mocked) delta vs baseline.
- **Phase gate:** full mocked Playwright delta clean + all touched files grep=0 + `tsc` clean before `/gsd-verify-work`.

### Wave 0 Gaps (create before/with implementation)
- [ ] Capture the pre-existing mocked-Playwright baseline: `cd frontend && npm run e2e` on the current tree, save pass/fail set (DEF-29-06-1) to diff against post-reskin. (No new infra — framework exists.)
- [ ] `src/components/layout/AppHeader.a11y.test.tsx` — profile menu `aria-expanded`/`role=menu`/Escape.
- [ ] `src/components/ui/NotificationPanel.a11y.test.tsx` — bell `aria-expanded`/`aria-haspopup`/Escape.
- [ ] `src/components/settings/AccountSettings.render.test.tsx` — asserts existing api fns still called (behavior parity).
- [ ] `src/components/library/LibraryPage.reskin.test.tsx` — search filters; Tabs roles.
- [ ] `src/app/admin/admin.reskin.test.tsx` — columns + pw-create modal preserved.
- [ ] Framework install: none — Vitest + Playwright already configured.

*(A per-file token guard analogous to `src/styles/__tests__/token-layer.test.ts` could optionally assert grep=0 per touched file, mirroring that existing pattern.)*

## Security Domain

FE-only reskin; behavior preserved; no auth/session logic changes.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (reskin only) | Login form wiring unchanged (`login()` → existing endpoint); do NOT add SSO/reset (dropped traps) |
| V3 Session Management | no | token handling unchanged (`getToken`) |
| V4 Access Control | verify-only | admin gate `getMe().is_admin` must remain (admin/page.tsx:123-124); don't remove during reskin |
| V5 Input Validation | n/a-preserve | existing client validation (pw≥8) kept; no new inputs |
| V6 Cryptography | no | none |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Accidentally weakening admin gate during chrome reskin | Elevation of Privilege | Keep `is_admin` redirect (admin/page.tsx:124); assert in `admin.reskin.test.tsx` |
| Re-introducing an unauthenticated SSO/reset entry point | Spoofing | Explicitly DROP SSO/Forgot (ND-12); no new auth routes |
| Login selector/behavior regression hiding an auth break | Repudiation | ts-a.auth mocked spec must stay green (delta) |

## Sources

### Primary (HIGH confidence) — files read this session
- `.planning/phases/35-shell-chrome-reskin-pages-b1/35-CONTEXT.md` — phase boundary + locked decisions
- `.planning/v2.0-evidence/02-workspace-shell-teardown.md` — shell chrome canonical + file map
- `.planning/v2.0-evidence/10-login-admin-teardown.md` — login/admin reskin scope + backend gaps
- `.planning/v2.0-evidence/11-cross-mock-reconciliation.md §B` — canonical shared-surface spec
- `frontend/src/styles/globals.css:1-390` — token layer
- `frontend/src/components/ui/{Button,Card,Tabs,Badge,Pill,NotificationPanel}.tsx` — primitives
- `frontend/src/components/results/AuditTab.tsx` — the verified reskin analog
- `frontend/src/components/layout/AppHeader.tsx`, `settings/AccountSettings.tsx`, `library/LibraryPage.tsx`, `workflow/ReviewGatesSection.tsx`
- `frontend/src/app/{login,register,admin}/page.tsx`
- `frontend/src/lib/api.ts` (auth/settings/admin surface)
- `frontend/src/app/layout.tsx` (font binding)
- `frontend/package.json`, `playwright.config.*`, `vitest.config.ts`, `e2e/tests/ts-a.auth.spec.ts`, `src/styles/__tests__/token-layer.test.ts`
- `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §82 + ND-12 (grep)

### Verified by tool this session
- retired-palette per-file counts (grep 2026-07-09) — matched verified facts once picker paths corrected to `workflow/prototype/`
- PrototypePreview/ReportViews are NOT tokenized (grep) — correction to brief

## Metadata

**Confidence breakdown:**
- Standard stack / recipe: HIGH — token layer + primitives + analog read directly.
- Endpoint map (settings/admin/auth): HIGH — read api.ts + component call sites.
- a11y gaps: HIGH — read each trigger/dropdown.
- Picker sibling-modal scope: MEDIUM — flagged as open question A2.
- Validation architecture: HIGH — scripts + specs enumerated from repo.

**Research date:** 2026-07-09
**Valid until:** ~2026-08-09 (stable; internal codebase, no fast-moving external deps).

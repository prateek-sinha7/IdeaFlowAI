# Phase 35: Shell Chrome + Reskin Pages [B1] - Pattern Map

**Mapped:** 2026-07-09
**Files analyzed:** 11 targets (10 reskin surfaces + 1 confirm/no-work register)
**Analogs found:** 11 / 11 (one canonical token-layer analog + primitives)

> **CRITICAL VERIFIED FINDING — read before planning.** Of the four "already-reskinned Phase-32 analogs" named in the brief, only **`AuditTab.tsx` actually consumes the Phase-32 token layer** (71 token-class lines). `PrototypePreview.tsx`, `TweaksPanel.tsx`, and `ReportViews.tsx` have **0 token-class lines** — they still use the retired palette (`#1B2A4A`, `gray-*`, `emerald-*`, `JetBrains`). They are **pre-reskin** and MUST NOT be copied as token references (TweaksPanel/PrototypePreview theme the *generated deliverable*, not app chrome; ReportViews is old handoff UI). **The single canonical analog for every target in this phase is `frontend/src/components/results/AuditTab.tsx` + the five `ui/` primitives** (`Button`/`Card`/`Tabs`/`Badge`/`Pill`), which are themselves the token-layer reference implementations. Verified via `grep -Eoc 'surface-…|text-ink-…|line-…|status-…|--radius-|bg-brand|text-brand'`.

> **Token destination (verified present in `frontend/src/styles/globals.css`):** `@theme inline` exposes `--color-brand*`, `--color-ink-{200..900}`, `--color-surface-{paper,warm,card,white,near-black,ink-black}`, `--color-line-{border,divider,control,faint-row,faint}`, `--color-status-{running,done,failed,amber,queued}`, `--font-{sans=Manrope,serif=Heebo,mono}`. Tailwind utilities: `bg-surface-card`, `text-ink-700`, `border-line-border`, `text-status-done`, `bg-brand`, `font-sans`. Fill/border ramp + radius/elevation/scrim live in `:root` (lines 93–140) and are consumed via arbitrary utilities, e.g. `rounded-[var(--radius-card)]`, `bg-[var(--status-done-fill)]`, `shadow-[var(--elevation-menu)]`.

---

## File Classification

| Target file | Role | Data flow | Delta class | Closest reskinned analog | Match quality |
|-------------|------|-----------|-------------|--------------------------|---------------|
| `components/layout/AppHeader.tsx` (+ `DashboardLayout.tsx` mount L1386) | layout / chrome | event-driven (nav + dropdowns) | RESKIN + light RESTRUCTURE (relabel nav, dark bar tokens) | `ui/Tabs.tsx` (nav idiom) + `AuditTab.tsx` header (L370) | role-match |
| `components/ui/NotificationPanel.tsx` | component (popover) | event-driven (chrome only; feed = Phase 38) | RESKIN | `AuditTab.tsx` empty-state + list rows (L182, L351) | exact (popover/list) |
| `components/settings/AccountSettings.tsx` | component (settings form) | CRUD → existing endpoints | RESKIN (keep wired controls) | `AuditTab.tsx` (tabs, cards, chips) + `ui/Tabs.tsx` | role-match |
| `components/workflow/prototype/TemplateGallery.tsx` (+ `TemplateDetailModal.tsx`) | component (picker grid) | request-response (real templates) | RESKIN | `AuditTab.tsx` card grid + `ui/Card.tsx` | role-match |
| `components/workflow/prototype/DesignSystemPicker.tsx` | component (picker grid) | request-response (real ~14, LOCK-F) | RESKIN | `AuditTab.tsx` chips/filters (L406) + `ui/Pill.tsx` | role-match |
| `components/workflow/ReviewGatesSection.tsx` | component (expandable control) | event-driven (gate selection) | RESKIN | `AuditTab.tsx` header/rows + `ui/Badge.tsx` | exact (checkbox list) |
| `components/library/LibraryPage.tsx` | component (tabbed catalog) | request-response (agents/skills/hooks) | RESKIN + light RESTRUCTURE | `ui/Tabs.tsx` + `AuditTab.tsx` card grid | role-match |
| `app/login/page.tsx` | page (auth form) | request-response (login API) | RESKIN + RESTRUCTURE (add 46% brand panel) | `AuditTab.tsx` tokens + `ui/Button.tsx` | role-match |
| `app/register/page.tsx` | page (redirect stub) | none | **NO WORK** (confirm invite-only) | — (see below) | n/a |
| `app/admin/page.tsx` | page (user mgmt) | CRUD → admin API | RESKIN (keep Runs/Role/Joined + pw-create) | `AuditTab.tsx` + `ui/{Badge,Button,Card}.tsx` | role-match |
| `components/layout/DashboardLayout.tsx` | layout orchestrator | routing/state | light RESKIN (body surface only; retired=0 already) | `AuditTab.tsx` surfaces | partial |

---

## Shared Patterns (apply to ALL targets)

### S1 — Token/primitive usage (the whole point — INV token authority)
**Source of truth:** `frontend/src/components/results/AuditTab.tsx`. Copy these exact idioms; replace every retired hex/`gray-*`/`Inter`/`Fraunces`/`JetBrains` with a token utility.

Card surface (AuditTab L182):
```tsx
className="bg-surface-card border border-line-border rounded-[var(--radius-list-row)] px-3 py-2.5"
```
Section header + ink ramp + brand icon (AuditTab L370–374):
```tsx
<div className="flex-shrink-0 px-4 pt-3 pb-2.5 border-b border-line-divider bg-surface-white">
  <Shield className="h-3.5 w-3.5 text-brand flex-shrink-0" />
  <span className="text-[12px] font-semibold text-ink-700">Audit trail</span>
  <span className="ml-auto text-[10px] text-ink-400">{rows.length} records</span>
```
Filter/chip toggle, active = brand-fill (AuditTab L411–422):
```tsx
className={[
  "inline-flex items-center gap-1 border rounded-[var(--radius-tag)] px-1.5 py-0.5 ...",
  active ? "bg-brand-fill border-brand-border" : "bg-surface-white border-line-control hover:bg-surface-warm",
].join(" ")}
```
Coverage pill (AuditTab L385–389): `rounded-[var(--radius-pill)] border border-line-control bg-surface-white text-ink-600`.
Empty-state disc (AuditTab L354): `rounded-[var(--radius-menu)] bg-surface-warm` + `text-ink-400` icon.

### S2 — Primitive substitution table (replace ad-hoc elements)
| Current ad-hoc element (across targets) | Replace with primitive |
|---|---|
| `<button className="bg-[#1B2A4A] ... text-white">` / `bg-blue-600` | `ui/Button.tsx` `variant="primary"` (bg-brand) |
| `<button className="border border-gray-200 bg-white">` | `ui/Button.tsx` `variant="secondary"` |
| `rounded-2xl border border-gray-200 bg-white` panels/cards | `ui/Card.tsx` (radius-14, surface-card, line-border) |
| underline / segmented tab rows (`libTabBtn`, settings `setTabs`, admin filters) | `ui/Tabs.tsx` (active = ink-900 + 2px brand underline) |
| status/tier chips (`TierBadge`, notif status label, gate "default") | `ui/Badge.tsx` (status keys) or `ui/Pill.tsx` (neutral) |
| filter/category chips (Template/DS/Library) | `ui/Pill.tsx` or the AuditTab chip idiom (S1) |

### S3 — Status palette (evidence 11 §B3, already tokenized in Badge.tsx)
Use `ui/Badge.tsx` `status` keys: `running`→blue `#3C2CDA` (NOT amber), `done`→green, `failed`→red, `cancelled`→amber, `queued`→neutral-grey. "Not run" = grey (resolved cosmetic). `completed` normalizes to `done`. The `normalizeStatus` helper (Badge L34) already maps free strings — reuse it, do not re-implement.

### S4 — a11y (interactive shell — from CONTEXT INVARIANTS)
Nav/profile-menu/notifications/popover need keyboard + aria. AppHeader already has outside-click close (L66–74) and `AnimatePresence`; NotificationPanel same (L48–56); ReviewGatesSection uses `aria-expanded` (L109) and `sr-only` checkbox (L150) — preserve these on reskin. Tabs primitive already emits `role="tablist"/"tab"/aria-selected`.

### S5 — Retired-palette elimination gate (must = 0 per touched file)
Grep target: `#1B2A4A|#2563eb|#f5f5f0|\bInter\b|\bFraunces\b|\bJetBrains\b`. Per-target starting counts (verified 2026-07-09): AppHeader **2**, DashboardLayout 0, NotificationPanel **8**, AccountSettings **21**, LibraryPage **8**, TemplateGallery **11**, DesignSystemPicker **12**, ReviewGatesSection **5**, login **4**, register **1**, admin **11**. Note AppHeader also uses non-listed retired hex `#111827`/`#1f2937`/`bg-blue-600` (dark bar) → convert to `bg-surface-near-black`/`border-line`... on dark; those are not in the grep gate but violate token authority.

---

## Pattern Assignments

### 1. `components/layout/AppHeader.tsx` (+ DashboardLayout.tsx) — layout/chrome, RESKIN + light RESTRUCTURE

**Current structure (verified):** dark bar `bg-[#111827] border-[#1f2937]` (L77); left `bg-blue-600` logo + serif italic wordmark (L80–85); **center nav pill** `bg-[#1f2937] rounded-lg p-1` with 3 `<button>`s Home/Library/**"Catalogue"** (L89–123) each active = `bg-white text-gray-900`; right cluster = running-badge (L129) + `<NotificationPanel>` (L150) + **profile dropdown** (L160–245) with identity block (email + `Plan: {TIER_LABELS[userTier]}` + basic-tier Upgrade link) and items Account Settings / Analytics / Workflow History / Log out.

**RICHER behavior to PRESERVE (D-15 — do not regress):**
- The running-pipeline badge (L129–147): `isPipelineRunning` → pulsing dot + `getWorkflowLabel(pipelineType)` + `{completed}/{total}` → `onGoToPipeline`. This is the real "run in progress" affordance (mock's Live-only pill). Keep.
- Profile identity block: real `userEmail` + `TIER_LABELS[userTier]` + conditional Upgrade for basic tier (L197–204). Keep.
- Outside-click close + AnimatePresence (L66–74). Keep.
- `onNavigate` union type + `currentPage` active detection (L25–26). Nav is **route/page keyed, never workflow-name** (SC-001) — keep generic.

**REQUIRED CHANGES:**
- **D-11 nav relabel:** third item currently reads **"Catalogue"** with page key `saved-workflows` (L113/L121) — relabel the *visible text* to **"My Workflows"** (page key stays `saved-workflows`; the `WorkflowCatalog`→`HomeLaunchGrid` rename is Phase 36, out of scope). "Catalogue" is reserved for the future marketplace — must not remain.
- Analytics/History/Settings/Logout stay in the **profile menu** (already correct, L211–240) — do not promote to top nav. Admin console link + resolved cosmetics (avatar = rounded-square, nav = purple-underline active) per evidence 11 §B1.
- Dark bar → `bg-surface-near-black` (#111114) tokens; nav-pill active per resolved cosmetic (purple-underline OR pill-fill — CONTEXT locks nav=purple-underline).

**Analog excerpt (nav active idiom → `ui/Tabs.tsx` L44–47):**
```tsx
isActive ? "text-ink-900 border-brand" : "text-ink-400 border-transparent hover:text-ink-700"
```
**Mock fiction to NOT build:** nothing new — the mock's nav is a subset; no "Catalogue" marketplace.
**Primitives:** `ui/Tabs.tsx` (nav), `ui/Badge.tsx`/`ui/Pill.tsx` (running badge, plan chip).

---

### 2. `components/ui/NotificationPanel.tsx` — component/popover, RESKIN (chrome only)

**Current structure:** bell trigger `bg-[#1f2937]` + unread badge `bg-[#1B2A4A]` (L69–80); dropdown `rounded-xl border-gray-200 bg-white shadow-xl` (L90); header "Notifications" + "Clear all" (L93–112); list with per-notification `StatusIcon` (L28), running progress bar `bg-[#1B2A4A]` (L163), status label pill (L178–187), CTA "View progress/results" (L190–204); empty state (L116–125).

**RICHER behavior to PRESERVE:** `formatRelativeTime` (L18); running **progress bar** with `{completed} of {total} agents` + `%` (L151–168) and indeterminate pulse when total unknown (L170–174); mark-all-read on open (L58–64); status-driven CTA routing (`onGoToPipeline`/`onViewResults`). This is the live-feed wiring — **Phase 35 reskins CHROME only; the live feed is Phase 38** — keep all existing props/handlers intact.

**REQUIRED CHANGES:** convert 8 retired-hex occurrences → tokens; status colors via `ui/Badge.tsx` keys (running=blue, completed→done=green, failed=red, cancelled=grey — S3); dropdown elevation → `shadow-[var(--elevation-notif)]`.

**Analog excerpt (empty-state disc → AuditTab L353–361):**
```tsx
<div className="w-10 h-10 rounded-[var(--radius-menu)] bg-surface-warm flex items-center justify-center">
  <Shield className="h-5 w-5 text-ink-400" />
```
**Mock fiction to NOT build:** "Mark all read" as inert (mock L54) — current is already wired; keep wired. Do NOT wire a new live feed (Phase 38).
**Primitives:** `ui/Badge.tsx` (status label), `ui/Pill.tsx` (count chip).

---

### 3. `components/settings/AccountSettings.tsx` — settings form, RESKIN (CRUD on EXISTING endpoints)

**Current structure:** 4 sections `profile | model | limits | constitution` (L18) via tab state (L72); loads `getMe`/`getPreferences`/`getCapabilities` (L102–116); password-change form (real inputs L253–276 → `changePassword`); AI-model selection (`pendingModel`/`handleSaveModel` → `updatePreferences`, L121); limits tab (`TIER_PIPELINES`/`getBasePipelines`); constitution. Retired hex embedded in `TIER_DETAILS` (L37–50) + `#1B2A4A` throughout (21 occurrences).

**RICHER behavior to PRESERVE:** the wired controls are already real — password change (L253+), model preference save (L121–130), tier/entitlement display from `TIER_PIPELINES`. Keep every endpoint call.

**IMPORTANT scope correction (verified — avoid fiction):** the mock's "static profile fields" (Full name / Role / Organization) have **NO backing endpoint** (`getMe` returns email/tier/is_admin only; no `display_name`). The CONTEXT mandate "make static fields REAL controls on EXISTING endpoints" therefore resolves to: reskin + keep the **already-real** controls (password, model). Do **NOT** add name/org/role inputs — that is mock fiction (no server). Email stays a read-only display.

**Analog excerpt:** tabs → `ui/Tabs.tsx`; radio/model cards → AuditTab chip-select idiom (L411–422, active = `bg-brand-fill border-brand-border`).
**Mock fiction to NOT build (evidence 02 §5):** "Change photo", "Manage plan", inert "Save changes" for non-existent profile fields; usage-metering numbers with no API.
**Primitives:** `ui/Tabs.tsx`, `ui/Card.tsx`, `ui/Button.tsx`, `ui/Badge.tsx` (tier).

---

### 4. `components/workflow/prototype/TemplateGallery.tsx` (+ TemplateDetailModal.tsx) — picker grid, RESKIN

**Current structure:** category tabs (L34 `CATEGORIES`, 8 buckets incl. Custom) + real search `query` (L37) + upload; `getBucket` scenario→bucket mapping (L23); `filtered`/`filteredCustom` memos (L53–73) over **real `PrototypeTemplate[]`** with `has_preview` gate; `TemplateDetailModal` (L77) + `CustomTemplateModal` (L86) + localStorage custom templates (L44). Retired hex ×11 (e.g. `bg-[#1B2A4A]` tab count L118).

**RICHER behavior to PRESERVE:** real search (NOT the mock's inert search box), category filtering, custom-template upload + localStorage persistence, detail modal, `has_preview` filtering, `onSelect` wiring. The mock's picker cards are **unwired** (`onClick:()=>{}`) — current selection is real; keep it.

**Analog excerpt:** card grid → `ui/Card.tsx` + AuditTab row L182; tabs → `ui/Tabs.tsx`.
**Mock fiction to NOT build (evidence 02 §5 / §2.11):** unwired selection; "Browse full library" as decoration. Keep real selection.
**Primitives:** `ui/Tabs.tsx`, `ui/Card.tsx`, `ui/Pill.tsx` (category chips), `ui/Button.tsx`.

---

### 5. `components/workflow/prototype/DesignSystemPicker.tsx` — picker grid, RESKIN (LOCK-F: real ~14, NO expansion)

**Current structure:** category tabs derived from **real `systems`** (L48 `allCategories`) + real search (L27) + grouped-by-category chips (L54–76); custom DS via `CustomDesignSystemModal` + localStorage (L35/L87); `DesignSystemDetailModal` (L29); `onSelect`/`onSelectCustom` wiring. Retired hex ×12.

**RICHER behavior to PRESERVE:** real search + category grouping + custom DS create/edit/delete + detail modal + selection. All wired — keep.

**LOCK-F:** render the **real ~14 count** from the actual `systems` prop. Do **NOT** display the mock's fabricated "150 systems" header (evidence 02 §2.11 / §5 overstated count) — no catalog expansion.

**Analog excerpt:** grouped chip cloud → AuditTab filter chips (L406–428) + `ui/Pill.tsx`.
**Mock fiction to NOT build:** "150 systems" claim; inert chips (current chips are wired — keep).
**Primitives:** `ui/Pill.tsx` (system chips + swatch trio), `ui/Tabs.tsx`, `ui/Button.tsx`.

---

### 6. `components/workflow/ReviewGatesSection.tsx` — expandable control, RESKIN

**Current structure:** inline expandable (L102–121) header ShieldCheck + "Review gates" + `{n} agent(s) pause for review`; body = one checkbox per pipeline agent (L130–167); default-gated iff `gate === "Human_Gate"` (L40); "default" chip (L160). Retired hex ×5 (`#1B2A4A`, `#F1F4FB` hover).

**RICHER behavior to PRESERVE (load-bearing — see file docstring L11–24):** the `onChange(gateAgentIds, touched)` contract — caller sends `gate_agent_ids` ONLY when `touched`; `[]` means "no gates"; untouched omits → backend static default (byte-identical, Q3/INV-3). Re-seed on `agentsKey` change (L63–74). `initialGateIds` seeding from saved workflow. `aria-expanded` + `sr-only` checkbox a11y. **Do not touch any of this logic — reskin classNames only.**

**Analog excerpt:** header row → AuditTab L370; checkbox active state → brand tokens; "default" chip → `ui/Badge.tsx`/`ui/Pill.tsx`.
**Mock fiction to NOT build:** none — mock gates popover is already functional; this is a straight token swap.
**Primitives:** `ui/Badge.tsx` (default chip), checkbox stays custom (token colors).

---

### 7. `components/library/LibraryPage.tsx` — tabbed catalog, RESKIN + light RESTRUCTURE

**Current structure:** Agents/Skills/Hooks tabs; real data from `LIBRARY_AGENTS`/`CUSTOM_AGENTS` (L15), `SKILLS`/`SKILL_CATEGORIES` (L11), `HOOKS`/`HOOK_EVENTS` (L12); category chips; `SkillDetailModal` (L53, real markdown parsing + copy-to-clipboard L56) + `AgentCapabilitiesModal` (L10). `ICON_STYLES` ad-hoc tint array (L39, retired hex). Retired hex ×8.

**RICHER behavior to PRESERVE:** tab model, real catalog data + counts, skill/agent detail modals with copy, category filtering. CONTEXT: "real controls where the mock had static text" — the current search/filters may be inert placeholders in spots; where a control is decorative and a real filter is cheap on existing data, wire it (do not invent backend).

**Analog excerpt:** tabs → `ui/Tabs.tsx`; agent/skill cards → `ui/Card.tsx` + AuditTab L182; chips → `ui/Pill.tsx`.
**Mock fiction to NOT build (evidence 02 §5):** inert search box (L304 mock), `showAgentTint` editor toggle, per-agent `dur`/per-hook `trigger` strings with no API. The agent drawer (mock 2.9) is a separate build — out of scope.
**Primitives:** `ui/Tabs.tsx`, `ui/Card.tsx`, `ui/Pill.tsx`, `ui/Button.tsx`.

---

### 8. `app/login/page.tsx` — auth page, RESKIN + RESTRUCTURE (add 46% brand panel)

**Current structure:** single centered card on `#f5f5f0` (L40); serif/italic wordmark using `--font-fraunces`/`--font-inter` (L57/L63); real `<form>` (L84) → `login()` → redirect by `data.user.is_admin` (L23: admin→/admin else→/dashboard); error state (L74–82), loading state (L126), Mail/Lock icon inputs (L89/L106). Retired hex ×4.

**RICHER behavior to PRESERVE (ND-12 — do not regress):** the wired form — `login()` call, 401 → "Invalid email or password", generic ApiError handling (L24–31), loading disable, **redirect-by-is_admin** (L23). Invite-only footer copy (L132). This is functionally *ahead* of the mock (mock is static spans) — keep all of it.

**REQUIRED RESTRUCTURE:** add the **46% dark brand panel** (`bg-surface-near-black`, white wordmark, eyebrow, headline, subhead) on the left; form column on the right (evidence 10 §2). Swap fonts to `font-sans` (Manrope) / tokens; `#1B2A4A` focus ring → brand.

**DROP (identity traps — ND-12, mock fiction):** "Continue with SSO" button, "Forgot?" link — no backend (`auth.py` = login/register-403/me/logout/change-password only). Brand-panel "SSO & SCIM / Full audit trail" tags are marketing copy — render as static decoration only, wire nothing.

**Analog excerpt:** primary button → `ui/Button.tsx` `variant="primary"`; tokens per S1.
**Primitives:** `ui/Button.tsx`; inputs stay native `<input>` (token-styled — no input primitive exists; evidence 11 §6.11 flags this DS gap).

---

### 9. `app/register/page.tsx` — **NO WORK (confirm + record)**

**Verified:** L10–20 is a redirect stub — `useEffect(() => router.replace("/login"))` + "Redirecting…" on `#f5f5f0`. Backend `auth.py` register → 403. Evidence 10 §7 confirms: mock is invite-only (no register surface) → current behavior is already correct. **Only action:** optionally swap the `#f5f5f0` background literal (1 retired occurrence) to `bg-surface-paper` for gate compliance; otherwise no work. Record as confirmed-correct.

---

### 10. `app/admin/page.tsx` — user-mgmt page, RESKIN (keep richer data)

**Current structure:** admin gate via `getMe().is_admin` else redirect (L123–126); `adminListUsers`/`adminUpdateTier`/`adminCreateUser`/`adminDeleteUser` (L11); `TierDropdown` (L33–95, optimistic update + revert on error → `adminUpdateTier`); `TierBadge` (L25, retired hex `TIER_STYLES` L19–23); wired search (L101); create-user modal (email + **password** + tier + grant-admin); delete-confirm. Retired hex ×11.

**RICHER behavior to PRESERVE (ND-12 + evidence 10 §7 "loud warning"):**
- **Keep the backed columns the mock drops:** Runs (`workflow_run_count`), Role (`is_admin`), Joined (`created_at`).
- **Keep the password-create flow** (admin sets password ≥8) — do NOT swap for the mock's email-invite (no endpoint).
- Keep optimistic tier update + revert, wired search (mock's is inert), delete-confirm with self-delete guard, admin-access gate.

**REQUIRED CHANGES:** reskin chrome/stat-row/table/tier-dropdown/delete-modal to tokens. `TierBadge` → `ui/Badge.tsx`. Stat tiles → `ui/Card.tsx`. May add client-side tier **filter chips** (trivial on existing `tier` — evidence 10 §7).

**DEFER (additive backend — NOT this phase):** the mock's **Status** (active/invited/suspended) and **Last-active** columns (no `status`/`last_active_at` on `User`), and the **email-invite** flow (`display_name`/invite-token endpoint). Do not build.

**Analog excerpt:** tier badge → `ui/Badge.tsx`; dropdown elevation → `shadow-[var(--elevation-menu)]`; delete modal scrim → `bg-[var(--scrim)]`.
**Primitives:** `ui/Badge.tsx` (tier/role), `ui/Card.tsx` (stat tiles), `ui/Button.tsx`, `ui/Pill.tsx` (filter chips).

---

### 11. `components/layout/DashboardLayout.tsx` — orchestrator, light RESKIN

**Current structure:** 1740-line routing/state orchestrator; mounts `<AppHeader currentPage=… onNavigate=…>` (L1386). Retired-palette grep = **0** already; token-lines = 6. Mostly untouched by this phase except any body-surface background literal. Treat as light-touch: ensure page shell uses `bg-surface-paper`; do not restructure routing (SC-001 — page keys stay generic).

---

## No Analog Found

None. All targets map to `AuditTab.tsx` + the `ui/` primitives (both verified token-layer implementations). RESEARCH.md was not required — the token layer + primitives are present and are the concrete reference.

## Metadata

**Analog search scope:** `frontend/src/components/{results,preview,handoff,ui,layout,settings,library,workflow}`, `frontend/src/app/{login,register,admin}`, `frontend/src/styles/globals.css`.
**Files scanned:** 11 targets + 5 primitives + 4 candidate analogs + token layer.
**Verified:** token-class counts (grep), retired-palette counts (grep), AppHeader mount point, AccountSettings endpoint surface, all target current-structure reads.

---

## PATTERN MAPPING COMPLETE

**Phase:** 35 - shell-chrome-reskin-pages-b1
**Files classified:** 11 | **Analogs found:** 11/11

### Coverage
- Exact/role analog: 10 | No-work confirm: 1 (register) | No-analog: 0

### Key patterns identified
- **Only `AuditTab.tsx` is a real token-layer analog** — the other 3 named analogs (PrototypePreview/TweaksPanel/ReportViews) are pre-reskin (0 token-lines); use AuditTab + the 5 `ui/` primitives exclusively.
- Every reskin = token-utility swap (S1) + primitive substitution (S2) + status via `ui/Badge.tsx` (S3), verified by retired-palette grep = 0 (S5).
- **D-15 preservation is the main risk**: keep the wired-and-richer behavior (login redirect-by-is_admin, admin Runs/Role/Joined + pw-create, ReviewGates onChange contract, notif progress bar, real pickers) — a face-value mock rebuild regresses. Drop the identity traps (SSO/Forgot/invite/status/last-active) as fiction.

### Summary table
| Target | Current file | Analog | Primitives |
|---|---|---|---|
| Shell top bar/nav/profile | `components/layout/AppHeader.tsx` (+DashboardLayout L1386) | Tabs.tsx + AuditTab | Tabs, Badge, Pill |
| Notifications panel | `components/ui/NotificationPanel.tsx` | AuditTab | Badge, Pill |
| Account Settings | `components/settings/AccountSettings.tsx` | AuditTab + Tabs.tsx | Tabs, Card, Button, Badge |
| Template picker | `components/workflow/prototype/TemplateGallery.tsx` | AuditTab + Card.tsx | Tabs, Card, Pill, Button |
| Design-System picker | `components/workflow/prototype/DesignSystemPicker.tsx` | AuditTab + Pill.tsx | Pill, Tabs, Button |
| Review-gates | `components/workflow/ReviewGatesSection.tsx` | AuditTab + Badge.tsx | Badge |
| Library | `components/library/LibraryPage.tsx` | Tabs.tsx + AuditTab | Tabs, Card, Pill, Button |
| Login | `app/login/page.tsx` | AuditTab + Button.tsx | Button |
| Register | `app/register/page.tsx` | — (NO WORK) | — |
| Admin | `app/admin/page.tsx` | AuditTab + Badge/Card | Badge, Card, Button, Pill |
| Dashboard shell | `components/layout/DashboardLayout.tsx` | AuditTab | — |

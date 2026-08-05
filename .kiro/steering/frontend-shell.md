---
inclusion: fileMatch
fileMatchPattern: "frontend/src/components/layout/**,frontend/src/components/settings/**,frontend/src/components/library/**,frontend/src/components/analytics/**,frontend/src/app/login/**,frontend/src/app/register/**,frontend/src/app/admin/**,frontend/src/styles/globals.css,frontend/src/components/ui/**"
---

# Frontend — Shell, Settings & Design System Domain

> Loaded when editing layout, settings, library, analytics, auth pages, admin, design tokens, or UI primitives. See `invariants.md` for hard constraints.

---

## Design Token System (Phase 32)

Tokens live in `frontend/src/styles/globals.css` under `@theme inline` + `:root`. All component styles must reference tokens — **never raw hex**.

| Token family | Examples |
|---|---|
| Brand | `var(--brand)` = `#3C2CDA` (one-chroma) |
| Ink | `var(--ink-black)`, `var(--ink-secondary)` |
| Surface | `var(--surface-paper)`, `var(--surface-near-black)` |
| Status | `var(--status-running)`, `var(--status-done)`, `var(--status-failed)` |
| Severity | P0=critical red, P1=amber, P2=yellow, P3=gray |
| Radius | button=10px (`--radius-button`), card=14px (`--radius-card`), pill=9999px (`--radius-pill`) |

Retired palette (must NOT appear in new code):
- `#1B2A4A` (navy)
- `#2563eb` (blue)
- `#f5f5f0` (cream)
- Font: `Fraunces`, `JetBrains`, `Inter` (as font-family)

Active fonts: **Manrope** (headings) + **Heebo** (body).

**Governance-only exception:** the Audit tab governance status palette (green/amber/red) is the sole one-chroma carve-out allowed outside `var(--brand)`.

---

## UI Primitives (Phase 32)

Located in `frontend/src/components/ui/`:
- `Button.tsx` — must have `type` attribute (default is form-submit, which causes accidental form submission — LW-01 fix)
- `Card.tsx`
- `Tabs.tsx`
- `Badge.tsx` — `gate`/`review`/`paused` statuses map to amber ramp; tier chips use explicit `label=` override
- `Pill.tsx`
- `NotificationPanel.tsx` — bell + dropdown; `role="menu"` is wrong (should be list/dialog model — FLAG-3 carry-forward)

Every value in these primitives must resolve to a `var(--…)` token or a Tailwind utility that maps to one.

---

## `DashboardLayout` Navigation Rules (Phase 35)

- Nav = `{key, label, Icon}` data list — no workflow-name branches (SC-001).
- `"My Workflows"` nav label → key `"saved-workflows"` (D-11 rename; component = `HomeLaunchGrid` since Phase 36).
- "Catalogue" is reserved — do not use it as a nav label for user-facing surfaces.
- `mainView` type union: `home | input | history | saved-workflows | catalog | execution | composer` — never a workflow-name value.
- Profile menu: `aria-haspopup="menu"`, `aria-expanded`, `role="menu"` / `"menuitem"`, Escape-close + refocus.
- Notification bell: same menu-button a11y pattern.

---

## Account Settings Rules (Phase 35)

- 4 wired sections: profile (`getMe`), password (`changePassword`), AI model (`getPreferences`/`updatePreferences`), constitution (`fetch('/api/settings/constitution')`).
- AI-model control = native `<select>` (NOT the mock's chip "radio cards" — keeps real wiring, D-15).
- No unbacked fields (no Full name / Role / Organization inputs — fiction guard, ND-12).
- Category tabs use the `Tabs` primitive.

---

## Library Page Rules (Phase 35)

- Agents / Skills / Hooks tab bar → `Tabs` primitive.
- Real local-data search/category filters.
- Skill/Hook detail modals = `AnimatePresence` with `motion.div` root.
- `fetch(|/api/` grep must be 0 — no invented backend calls.

---

## Analytics Page Rules (Phase 38)

- Fetches from `GET /api/analytics/summary?range=<dateFilter>` — the **only** server re-fetch trigger.
- **No client-side 500-row rollup** — was the old pattern, now replaced by the endpoint.
- Pipeline/model filters narrow the already-fetched arrays client-side (intentional, not a gap).
- Charts = hand-rolled SVG — **no chart library** (D, locked decision).
- `DonutChart` / `BarChart` in `frontend/src/components/analytics/charts/`.
- By-Model breakdown bound to `models[]` from the endpoint.
- Estimates on `HomeLaunchGrid` cards: `~N agents` always; `~Xm` only when history exists — never fabricated.

---

## Login / Register Rules (Phase 35, ND-12)

- SSO button = **DELETED** (no backend).
- "Forgot?" link = **DELETED** (no backend).
- Login → two-column split: dark brand panel left + form right.
- `login()` → redirect by `is_admin`, 401 handling, loading/disable state preserved.
- e2e selectors preserved verbatim: `#email`, `#password`, submit name `"Sign in"`, heading `"Welcome back"`.

---

## Admin Page Rules (Phase 35, ND-12)

- Near-black header + `Card` stat cards / table.
- `TierDropdown`: same menu-button a11y contract as profile menu.
- Real wiring preserved: `adminListUsers` / `UpdateTier` / `CreateUser` / `DeleteUser`, `getMe().is_admin` gate.
- **Status / Last-active columns = DEFERRED** (no `AdminUser.status` / `last_active_at` backing fields).
- **Email-invite flow = DEFERRED** (no backend endpoint).

---

## Reskin Rule (D-15)

> Adopt the mock's visual language. **KEEP** the product's richer live-data behavior. **REUSE** existing components.

A face-value mock rebuild that drops live wiring is a regression. The design mocks are a visual authority, not a behavioral authority.

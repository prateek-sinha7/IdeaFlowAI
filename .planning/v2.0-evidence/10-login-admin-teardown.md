# Login/Register + Admin Teardown (auth/admin cluster)

> **Evidence doc — Milestone v2.0** (see `README.md` + POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a `ui-teardown` investigation agent, 2026-07-07 (second batch — the five sibling screens + cross-mock reconciliation). Feeds Phase 35 (reskin) + the identity-traps decision (drop SSO/SCIM/invite/reset).
> Anchors are as-of 2026-07-07; verify before acting.

---

I have everything needed for a rebuild-grade teardown. Final confirmations: the v2.0 token layer (`#3C2CDA`/Manrope/Heebo) does **not** exist in `frontend/src` — current tokens are `--font-inter`/`--font-fraunces` + `#1B2A4A` navy (`src/styles/globals.css:9-10`, `theme.ts`, `tailwind.config.ts:18`), and Phase 32 (which would land them) is **Not started**. Backend `auth.py` has only login/register(403)/me/logout/change-password — no SSO, no forgot/reset, no invite. Register is 403-disabled server-side + a redirect stub client-side. Here is the complete teardown.

---

# UI TEARDOWN — Auth/Admin Cluster (VelocityAI v2.0 mocks → Flowin)

**Sources torn down (read in full to EOF):**
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Login.dc.html` (73 lines)
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Admin.dc.html` (176 lines)

**Mapping targets (current product):**
- `frontend/src/app/login/page.tsx` (138) · `frontend/src/app/register/page.tsx` (21) · `frontend/src/app/admin/page.tsx` (504)
- Backend: `backend/app/api/auth.py`, `backend/app/api/admin.py`, `backend/app/models/user.py`, `backend/app/core/entitlements.py`
- Tokens: `frontend/src/styles/globals.css`, `frontend/src/app/layout.tsx`, `frontend/src/styles/theme.ts`, `frontend/tailwind.config.ts`

**Planning-level fiction flag (applies to BOTH screens — read first):** The brief states the reskin runs on "a token+primitive layer landed in Phase 32." It has **not landed.** `ROADMAP.md` shows *Phase 32: Run-Screen Redesign — 0/? — Not started*; `grep` for `3C2CDA|Manrope|Heebo` across `frontend/src` returns **zero** hits. Phase 32 SC-1 is the line item that *will* create these tokens. Both screens' RESKIN is therefore **blocked on Phase 32 landing first** — which is exactly why Phase 35 already declares `Depends on: Phase 32 (token layer)` (`ROADMAP.md:828`). Every RESKIN verdict below is "trivial *once tokens exist*," not "trivial today."

---
---

# FILE 1 — `Hexaware Login.dc.html` (sign-in)

## 1. Page/state inventory
**One page, zero states.** The DCLogic class is empty: `state = {}` and `renderVals(){ return {}; }` (L67-69). There are no `{{ bindings }}`, no `<sc-if>`, no `<sc-for>`, no handlers, no data arrays. **The entire screen is static markup** — every value is a literal in the HTML. Navigation off the page is via two `<a href="Hexaware Workspace v2.dc.html">` links (the "Sign in" and "SSO" buttons, L54/L58) that go to the same destination unconditionally. **No register/signup surface exists in this file** — it is explicitly invite-only (L46, L60).

## 2. Layout regions
Full-viewport split flex, `bg:#F0EEE7` (beige), `font-family:'Heebo'` (L23):
- **Left brand panel** — fixed 46% width, `bg:#111114` (near-black), white text (L26-40).
- **Right form column** — `flex:1`, centered, `max-width:380px`, `popIn` entrance animation (L43-62).

No header, nav, modal, drawer, or overlay. No responsive breakpoint (fixed 46/54 split).

## 3. Per-region element enumeration

**Left brand panel (L26-40)**
- L27 — decorative radial-gradient blob (`#3C2CDA55→transparent`), top-right, `overflow:hidden`. Pure decoration.
- L28-31 — wordmark: "HEXAWARE" (`Manrope 800 italic 22px`, white) + 5px blue dot (`#3C2CDA`, L30).
- L33 — eyebrow "VelocityAI" (`Manrope 600 11px`, `letter-spacing:.24em`, uppercase, `#8E88E8` lavender).
- L34 — headline "Agent workflows that ship real work." (`Manrope 300 38px`, white).
- L35 — subhead "Compose specialist agents, watch every step, and hand governed, audit-ready deliverables to your team." (`Heebo 15px`, `#9A9BA6`).
- L37-39 — trust row, three inert `<span>`s: "Enterprise-ready", "SSO & SCIM", "Full audit trail" (`Heebo 12px`, `#6A6B76`).

**Right form (L43-62)** — states: none (no default/hover/focus/error/loading; hover only via static `style-hover` attrs on the two links).
- L45 — heading "Sign in" (`Manrope 300 26px`).
- L46 — helper "VelocityAI is invite-only. Use the work email your admin provisioned." (`Heebo 13px`, `#8A8B82`).
- L48 — label "Work email" (`Manrope 500 11.5px`).
- **L49 — email "input": INERT.** A bordered `<div>` containing a mail SVG + a static `<span>` reading `ak@hexaware.com`. **Not an `<input>`** — cannot receive text.
- L51 — password label row: "Password" + **"Forgot?"** `<span>` (`#3C2CDA`, `cursor:pointer`, **no handler, no href**).
- **L52 — password "input": INERT.** Bordered `<div>` + lock SVG + static `<span>` of 10 bullet chars `••••••••••`. Not an `<input>`.
- **L54 — "Sign in" button:** actually `<a href="Hexaware Workspace v2.dc.html">`, `bg:#3C2CDA`, arrow SVG, `style-hover:#3324c4`. Navigates unconditionally; **performs no authentication.**
- L56 — "or" divider (two hairlines + label).
- **L58 — "Continue with SSO":** `<a href="Hexaware Workspace v2.dc.html">`, shield SVG, `bg:#FCFBF7` bordered. Same destination; **no SSO handshake.**
- L60 — footer "No account? VelocityAI is invite-only — ask your workspace admin to provision access."

## 4. Data contract
**None.** The screen consumes zero data fields. No entity, no API shape. (Contrast: the *current* product's login is a real `<form>` posting `{email, password}` to `/api/auth/login`.)

## 5. Design language
Tokens actually used: colors `#F0EEE7` (beige page), `#111114` (brand panel), `#3C2CDA` (one-blue accent — buttons, dot, blob, "Forgot?"), `#8E88E8` (lavender eyebrow), text greys `#15161A/#8A8B82/#9A9BA6/#6A6B76`, borders `#E0DDD3/#E2DFD6`, field bg `#fff/#FCFBF7`. Fonts: **Manrope** (display/headings/labels/buttons) + **Heebo** (body). Radii: 10-11px fields/buttons. Idioms: pill-icon field (SVG + text in a bordered row), split brand/form auth, gradient-blob decoration. `@keyframes popIn` entrance (L19).

## 6. Fiction register
The **entire screen is non-functional** — flag everything:
- Email + password fields are `<span>`s, not inputs (L49, L52) — no typing, no validation, no state.
- "Sign in" (L54) and "Continue with SSO" (L58) are both `<a>` to the *same* page — no auth, no credential check, no SSO.
- "Forgot?" (L51) — styled span, no handler, no reset flow.
- Brand claims "SSO & SCIM", "Full audit trail", "Enterprise-ready" (L38) — marketing text; SCIM has no product surface.
- No error, loading, disabled, or focus states (the current product *has* all of these — this mock is a *regression* in behavioral fidelity).

## 7. Current-product mapping + delta
| Mock element (Login) | Current home (`file:line`) | Delta |
|---|---|---|
| Split layout, dark brand panel | `login/page.tsx:38-70` — **single** centered card on `#f5f5f0`, no brand panel | **RESTRUCTURE** (add 46% left brand panel; low effort) |
| Palette `#3C2CDA` / Manrope+Heebo | `#1B2A4A` navy + `--font-fraunces`/`--font-inter` (`globals.css:9-10`, `layout.tsx:2`) | **RESKIN** — *blocked on Phase 32 tokens (not landed)* |
| Email + password entry | `login/page.tsx:84-128` — real wired `<form>` → `login()` (`api.ts:118`), redirect by `is_admin` (`login/page.tsx:23`) | **RESKIN** (current is functionally richer: error `:74-82`, loading `:126`) |
| "Continue with SSO" | *nothing* — no SSO/OIDC/SAML endpoint (`auth.py` has login/register(403)/me/logout/change-password only) | **NEW-BUILD + BACKEND-NEEDED** — mock decoration; a real auth project |
| "Forgot password?" | *nothing* — only authed `POST /api/auth/change-password` (`auth.py:137`); no unauth reset/token/email | **NEW-BUILD + BACKEND-NEEDED** — mock decoration |
| Invite-only messaging | `login/page.tsx:132-133` "Access is by invitation. Contact your administrator." | **RESKIN** (already present, near-identical copy) |
| Register / signup | Mock has **none** (invite-only). Current: `register/page.tsx:12` redirect→`/login`; `auth.py:23` register→**403** | **NO WORK** — mock confirms current behavior is correct |

---
---

# FILE 2 — `Hexaware Admin.dc.html` (user management)

## 1. Page/state inventory
**One page; two modal states + one inline-menu state.** Real DCLogic (L122-174). `state` (L124-134): `users[6]` (mock array), `filter:'all'`, `tierMenu:null` (which row's tier dropdown is open, keyed by email), `addOpen:false` (invite modal), `delEmail:null` (delete-confirm target). Derived views built in `renderVals` (L143-172). Modals toggle via `<sc-if>` on `addOpen` (L95) and `delOpen` (`!!delEmail`, L111); the per-row tier menu toggles via `<sc-if u.tierMenuOpen>` (L78). User navigates back to the app via `<a>` links (L31, L45).

## 2. Layout regions
Column flex, `bg:#F0EEE7`, `Heebo` (L27):
- **Top bar** — 58px, `bg:#111114` (L30-38): wordmark + "Admin" chip + spacer + avatar.
- **Scroll body** — `max-width:1100px`, centered (L40-92): page header, stat grid, toolbar, table.
- **Invite-user modal** — fixed overlay, `sc-if addOpen` (L95-108).
- **Delete-confirm modal** — fixed overlay, `sc-if delOpen` (L111-118).

## 3. Per-region element enumeration

**Top bar (L30-38)**
- L31-34 — HEXAWARE wordmark `<a>`→workspace + blue dot.
- L35 — "Admin" chip (`Manrope 600 10px`, `#8E88E8` on translucent lavender bg).
- L37 — avatar circle "AK" (`bg:#3C2CDA`, white). **INERT** — `cursor:pointer` but no handler, no profile menu.

**Page header (L43-50)**
- L45 — "Back to app" `<a>`→workspace (chevron SVG).
- L46 — H1 "User management" (`Manrope 300 26px`).
- L47 — sub "Provision access, set plan tiers and manage your workspace members."
- **L49 — "Invite user" button** — `onClick={{ openAdd }}` (real; opens modal), `bg:#3C2CDA`, add-user SVG.

**Stat row (L53-57)** — `<sc-for list="{{ stats }}">`, 4 tiles, each: uppercase `{{ k.label }}` + `{{ k.value }}` (`Manrope 700 22px`, `.tnum`). Placeholder count 4. Values derived live from `users` (L162): **Total members, Enterprise, Pro, Basic.**

**Toolbar (L60-63)**
- L61 — filter chips `<sc-for list="{{ filters }}">`: `{{ f.label }}` + `{{ f.count }}` span, `onClick={{ f.onClick }}`, `style={{ f.style }}`. **WIRED** (sets `filter`; active chip = dark `#15161A`). Chips: All / Enterprise / Pro / Basic (L148).
- **L62 — search box: INERT.** `<div>` + search SVG + static `<span>` "Search members…". Not an input, no handler.

**Table (L66-89)**
- L67-69 header: **Member | Tier | Status | Last active | (40px blank)**.
- L70-88 — `<sc-for list="{{ rows }}" as="u">` (placeholder 6). Per row:
  - L73 — avatar `<div style="{{ u.avatarStyle }}">{{ u.init }}` (grey circle, initials).
  - L74 — `{{ u.name }}` (`Manrope 600 13px`) + `{{ u.email }}` (`Heebo 11px`).
  - L76-83 — **Tier cell (interactive):** clickable pill `onClick={{ u.onToggleTier }}` = dot (`{{ u.tierDot }}`) + `{{ u.tierLabel }}` + chevron. `<sc-if u.tierMenuOpen>` → dropdown (L79-81): `<sc-for u.tiers as t>` each = dot + `{{ t.label }}` + `<sc-if t.sel>`✓. `onClick={{ t.onClick }}` = **WIRED** `setTier` (L139, mutates `users`).
  - L84 — **Status pill:** `{{ u.status }}` with `{{ u.statusStyle }}` (green/blue/red per `ST`, L146).
  - L85 — **Last active:** `{{ u.seen }}` (`.tnum`).
  - L86 — **delete button** `onClick={{ u.onDelete }}` (trash SVG; hover red `#F5E5E2/#A33A32`) → `askDelete` (L140).

**Invite-user modal (L95-108)** — states: open/closed.
- L96 scrim `onClick={{ closeAll }}`; L97 card `onClick={{ stop }}` (stopPropagation).
- L98 — H2 "Invite a user" + sub "They'll get an email to set a password and sign in."
- **L100-101 — email field: INERT.** `<div>` with static "name@hexaware.com". Not an input.
- **L102-103 — tier selector: INERT.** Three static `<span>` chips: **Pro** (pre-selected, `border:#3C2CDA`), Basic, Enterprise. No state, no `onClick`.
- L105 — Cancel `onClick={{ closeAll }}` + **"Send invite" `onClick={{ closeAll }}`** — closes modal, **creates/invites nothing.**

**Delete-confirm modal (L111-118)** — states: open/closed.
- L114 — trash-in-circle + H2 "Remove `{{ delName }}`?" + "They'll lose access immediately. Their run history is retained for audit."
- L115 — Cancel `onClick={{ closeAll }}` + **"Remove" `onClick={{ confirmDelete }}`** = **WIRED** (filters `users`, L141).

## 4. Data contract (mock)
**`User` entity** (`state.users`, L125-132) — 6 rows: `{ init, name, email, tier, status, seen }`.
- `init` — avatar initials (string, e.g. "AK").
- `name` — full display name (e.g. "Ayesha Khan"). **Mock-only.**
- `email` — work email.
- `tier` — `'basic' | 'pro' | 'enterprise'`.
- `status` — `'active' | 'invited' | 'suspended'`. **Mock-only.**
- `seen` — last-active relative string (`'now' | '2h ago' | '1d ago' | '—' | '3d ago' | '2w ago'`). **Mock-only, hardcoded (not timestamps).**

**`TIERS` constant** (L135): `[{id,label,c(color)}]` × basic/pro/enterprise.
**Derived (all computed from `users`, real-shaped):** `stats` (4 counts, L162), `filters` (4 counts, L150), `rows` (view models, L153-159), status palette `ST` (L146).

## 5. Design language
Adds to the Login system: scrollbar styling (L18-19), `.tnum` tabular numerals (L20), `@keyframes scrimIn/popIn` (L22-23). **Status palette exception (governance colors, L146):** active green `#1F7A4D/#E7F0EA`, invited blue `#3C2CDA/#ECEAFC`, suspended red `#A33A32/#F5E5E2` — the one place multi-hue is allowed. Idioms: KPI stat tile, filter pill (dark-when-active), dropdown menu w/ check, status pill, avatar circle, confirm-dialog with icon disc, scrim+card modal. Card surfaces `#FCFBF7` on beige `#F0EEE7`; blue `#3C2CDA` for all primary actions.

## 6. Fiction register
- **Search box INERT** (L62) — static span, no filtering. *(Current product's search IS wired — `admin/page.tsx:271-277`.)*
- **Top-bar avatar "AK"** (L37) — no profile menu/dropdown.
- **Invite modal email field INERT** (L101) — can't type.
- **Invite modal tier chips INERT** (L103) — no selection state; "Pro" hardcoded-highlighted.
- **"Send invite" is theater** (L105) — calls `closeAll`; no row added, no invite sent, no optimistic update. *(Current "Add user" actually creates the user — `admin/page.tsx:162`.)*
- **`status`** field (active/invited/suspended) — mock-only; 'invited'/'suspended' hardcoded on specific rows (L129, L131).
- **`seen`/Last active** — hardcoded strings, not derived from timestamps.
- **`name`** — mock-only display names.
- **Genuine (not fiction):** stats, filter counts, tier dropdown, and delete are all real and derived from the 6-row array — but every mutation is **local-only** (no persistence).

## 7. Current-product mapping + delta
Current admin (`admin/page.tsx`) is **fully wired to real APIs** (`adminListUsers/adminUpdateTier/adminCreateUser/adminDeleteUser`, `api.ts:505-541` → `admin.py`), with an `is_admin` access gate (`admin/page.tsx:118-127` ← `require_admin`, `admin.py:23`).

| Mock element (Admin) | Current home (`file:line`) | Delta |
|---|---|---|
| Dark top bar: wordmark + "Admin" chip + avatar | `admin/page.tsx:208-232` — white bar, Shield logo, "Admin Dashboard", Back-to-app + **Logout** | **RESKIN** (chrome restyle; avatar/profile-menu = minor NEW-BUILD) |
| Page H1 "User management" + Invite button | folded into table header "Users"/"Add user" (`:264`,`:285-290`) | **RESTRUCTURE-light** (promote to page header) + RESKIN |
| Stat row (4: Total/Ent/Pro/Basic) | `:237-256` (5: Total/Basic/Pro/Ent/**Admins**), all derived | **RESKIN** (drop/keep Admins, reorder; no backend gap) |
| Filter chips All/Ent/Pro/Basic | **absent** (current has email search only) | **NEW-BUILD** (small; client-side on existing `tier`) |
| Search box | `:271-277` wired (email filter) | **RESKIN** (current already functional > mock's inert) |
| Refresh button | `:279-284` | keep (current extra; mock lacks) |
| Avatar + name + email | `:326-337` avatar=`email[0]`, **email only, + id8** | **RESKIN** on email/avatar |
| **`name` column** | **no `name`/`display_name` on `User`** (`user.py:12-39`) | **BACKEND-NEEDED** (add `display_name`) |
| Tier dropdown (basic/pro/ent) | `TierDropdown` `:33-95` → `adminUpdateTier` (`admin.py:90`); validated vs `TIER_PIPELINES` | **RESKIN** (wired both sides; tiers are REAL/load-bearing — gate pipelines, `entitlements.py`) |
| **Status pill** (active/invited/suspended) | **no status column** on `User`; current shows Role (`is_admin`) instead (`:349-357`) | **BACKEND-NEEDED** (account lifecycle: invited/active/suspended) |
| **Last active** | **no `last_active_at`**; only `created_at`/`updated_at` (`user.py:28-36`) | **BACKEND-NEEDED** (`last_active_at`) |
| (mock omits Runs) | `:346-348` `workflow_run_count` — REAL aggregate (`admin.py:69-74`) | mock **drops backed data** — keep in current |
| (mock omits Role) | `:349-357` `is_admin` Admin/User | mock **drops backed data** — keep |
| (mock omits Joined) | `:358-362` `created_at` | mock **drops backed data** — keep |
| Invite modal (email + tier, "email to set password") | Create-user modal `:382-443`: email+**password**+plan+**grant-admin** → `adminCreateUser` (`admin.py:127`, pw≥8) | **RESKIN of shell + SEMANTIC MISMATCH.** Mock = email-invite flow (no such endpoint) → **BACKEND-NEEDED** (invite token + email). Current = admin-sets-password (more functional) |
| Delete confirm | `:446-480` → `adminDeleteUser` (`admin.py:178`; can't delete self `:185`; UI hides for admins `:364`) | **RESKIN** — note copy mismatch: mock "run history **retained** for audit" vs current "**permanently delete** user and all data" |
| Toast / Loading / Empty states | `:483-501` / `:295-304` | keep (current extra; mock static) |

---
---

# COMBINED DATA CONTRACT

**Auth (`POST /api/auth/login` → `AuthResponse`, `api.ts:118`)** — already backed:
`{ token, user: { id, email, tier, is_admin } }`. Login redirect keys off `user.is_admin` (`login/page.tsx:23`). **No fields missing for the login reskin.**

**Admin `User` — current `AdminUser`** (`api.ts:496-502` ≡ `admin.py:35-43`, backed by `users` table `user.py:12-39`):
| Field | Type | Backed? | Shown in current | Shown in mock |
|---|---|---|---|---|
| `id` | string(uuid) | ✅ | ✅ (8-char) | ✗ |
| `email` | string | ✅ | ✅ | ✅ |
| `tier` | `basic\|pro\|enterprise` | ✅ (load-bearing) | ✅ (dropdown) | ✅ (dropdown) |
| `is_admin` | bool | ✅ | ✅ (Role) | ✗ |
| `created_at` | datetime | ✅ | ✅ (Joined) | ✗ |
| `workflow_run_count` | int | ✅ (aggregate) | ✅ (Runs) | ✗ |
| **`display_name`/`name`** | string | ❌ **MISSING** | ✗ | ✅ |
| **`status`** (active/invited/suspended) | enum | ❌ **MISSING** | ✗ (Role instead) | ✅ (pill) |
| **`last_active_at`** | datetime | ❌ **MISSING** | ✗ | ✅ ("2h ago") |

**Backend gaps to close only if matching the mock literally** (all additive columns on existing `users` table — consistent with Q3 additive-migration rule): `display_name`, `status`, `last_active_at`; plus an **invite endpoint** (token + email; today `POST /api/admin/users` requires a password, `admin.py:151`). **No SSO/SCIM/forgot-password endpoints exist** (`auth.py` full route list: register→403, login, me, logout, change-password).

---

# SECTION 8 — CROSS-PAGE INVENTORY (combined; feeds phase planning)

| Screen | Current home | Overall delta | Backend gaps | Blocked on |
|---|---|---|---|---|
| **Login** | `frontend/src/app/login/page.tsx` | **RESKIN** + small **RESTRUCTURE** (add dark brand panel) | none for core; SSO + forgot-pw are BACKEND-NEEDED **but mock-fiction → drop/defer** | Phase 32 tokens (not landed) |
| **Register** | `frontend/src/app/register/page.tsx` (redirect stub; `auth.py:23`→403) | **NO WORK** — mock is invite-only, matches current | none | — |
| **Admin** | `frontend/src/app/admin/page.tsx` + `backend/app/api/admin.py` | **RESKIN** (chrome, stats, tier dropdown, search, delete, create-modal shell) + **RESTRUCTURE** (table column set) + **NEW-BUILD** (tier filter chips) | `display_name`, `status`, `last_active_at`, email-invite endpoint — **only if matching mock columns** | Phase 32 tokens |

---

# RECOMMENDATION (per screen)

**LOGIN → FOLD INTO PHASE 35 (as a reskin-only page).** The core (email/password) is already wired and functionally *ahead* of the mock (error/loading/redirect states). Work is: (a) token/font swap once Phase 32 lands, (b) add the 46% dark brand panel — a small, self-contained RESTRUCTURE. **Explicitly DROP or DEFER the SSO button and "Forgot password?" link** — both are backend-less decoration in the mock; shipping them is a real identity/auth project (OIDC/SAML, unauth reset-token + email), not a reskin, and nothing in the backend supports them. **Register needs zero work** (redirect stub + 403 already enforce invite-only, which is exactly what the mock advertises). Risk: low. This is the cheapest, safest screen to include.

**ADMIN → FOLD THE RESKIN SLICE INTO PHASE 35; CARVE OUT & DEFER THE BACKEND SLICE.** In-scope for 35 (all data already exists): restyle top bar/stat row/table/tier-dropdown/delete-modal/create-modal to tokens, keep the already-wired search, and add the tier **filter chips** (trivial client-side on existing `tier`). **Defer to a later backend phase:** the mock's **Status** and **Last-active** columns and the **email-invite** flow — each needs an additive `users` column or a new endpoint (`display_name`/`status`/`last_active_at`/invite-token). 

**Loud warning for the planner:** a *literal* mock rebuild is a **data regression** — the mock **hides three backed, useful columns** (Runs, Role, Joined) and **shows three unbacked ones** (Name, Status, Last-active). Recommend a **hybrid**: adopt the mock's visual language but keep Runs/Role/Joined, add `display_name` if cheap, and treat Status/Last-active/email-invite as an opt-in backend phase — do **not** let the reskin silently drop the real run-count/role/joined data or swap the working password-create flow for an invite flow that has no server.

**Cross-cutting fiction to log at the milestone level:** the mocks imply an identity surface the product does not have — **SSO & SCIM** (login brand panel + SSO button), **email invitations** (admin), **self-serve password reset** ("Forgot?"), and **account suspension/invited lifecycle** (admin status). Each is a backend project, not a reskin. These are the four biggest traps if Phase 35 is scoped from the mocks at face value.

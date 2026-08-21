# 015 — Frontend Routing: Implementation Plan

**Spec**: [spec.md](spec.md) (15 requirements, 9 success criteria, 2 clarification rounds)
**Grounding**: `VELOCITY_GO_LIVE/go-live-report.md` §5.2.1–§5.2.5 (routing audit + target route
map, now cross-annotated back to this spec)
**Root**: `frontend/src/app/`

---

## 1. Goal & scope

**Problem.** Ten distinct screens share one URL (`/dashboard`) via in-memory view-swap state in
a 2,862-line page component. No deep links, no refresh-survival (including mid-run streams), no
working back/forward, no page dimension for error tracking or analytics.

**Goal.** Every one of the 34 screens in spec.md §5's inventory gets a distinct, stable URL
(FR-001), with the supporting behaviors spec.md requires: correct root-auth routing (FR-002),
refresh-survival including mid-stream (FR-003), working back/forward (FR-004), URL-encoded list
filters (FR-005), shareable library-item pages (FR-006), redirects for retired paths (FR-007),
branded not-found/error pages (FR-008/FR-013), access-appropriate deep-link handling (FR-009),
run-launch auto-navigation (FR-010), saved-workflow edit entry (FR-011), a page dimension for
observability (FR-012), `/test-preview` removal (FR-014), and a session-expiry redirect
(FR-015).

**Non-goals (spec.md §6, restated for planning)**: splitting `DashboardLayout` into real
per-route segment files (that's this plan's phase-2 follow-on, not required to satisfy any FR);
all of 014's canvas/composer/divert-linking work; changing what data any screen shows; the
`/login` rendering bug (BLK-14); global-nav retention on `/workflow/create`; JWT httpOnly
migration. None of these are touched by any phase below.

---

## 2. Constitution check — this repo's locked frontend conventions

No separate constitution file exists for the frontend (same situation `014`'s plan.md notes for
backend — see its §2). Cross-checked against the conventions already established in
`frontend/src/app/` and `frontend/src/components/`:

| Convention | How this plan honors it |
|---|---|
| **App Router only, no new routing library** | `frontend/package.json` carries no `react-router`/`nuqs`/state-routing lib (verified this session). Every phase below uses only Next.js 16's own `useRouter`/`usePathname`/`useSearchParams`/`middleware.ts` — zero new dependencies. |
| **`DashboardLayout` is the existing shared shell** | Phase 1 reuses it unmodified inside a catch-all segment rather than forking it — matches spec.md §6's explicit deferral of the "split into real segments" restructuring to a later, optional phase. |
| **No dependency-free precedent broken** | Confirmed via `treeLayout.ts`'s comment (composer canvas, 014's territory) that this codebase prefers hand-rolled solutions over pulling in libraries where avoidable — routing needs none anyway, so this is a non-issue here, noted for consistency. |
| **Additive redirects, not breaking changes** | FR-007's redirects (`/workflow/create?mode=` → `/create/{mode}`, `/preview-fullscreen` → `/runs/{id}/preview/full`) are implemented as Next.js `redirects()` config or route-level 301s — old links keep working, never 404 (SC-004). |
| **Ownership/authz checks stay server/API-driven** | FR-009's access-appropriate messaging reuses the existing `ApiError`/401-handling pattern (`lib/api.ts`) already verified working (go-live report §1.3) — no new authz model invented on the frontend. |

**No constitution violations requiring justification.** This is additive routing infrastructure
around existing, unmodified screen components — confirmed again during planning.

---

## 3. Phase 0 — Research (unknowns resolved)

Spec.md's Clarifications section already resolved every scope-boundary question. Two
implementation-level decisions remain, both resolved here rather than left open:

- **DECISION-1 (routing mechanism)**: Use a required catch-all segment (`app/[...view]/`)
  that renders the existing `DashboardLayout`, mapping path segments to `mainView` + ids + tab,
  with `router.push` writing the path back on every view change — the approach the go-live
  report's own §5.2.3 already recommends (~1-2 dev-days, no component moves). The required form
  (single brackets) is used because optional catch-all segments create specificity conflicts
  with the root `page.tsx`, preventing correct routing. **Rejected alternative**: splitting
  `DashboardLayout` into real per-segment `page.tsx` files now — bigger, riskier, no user-visible
  benefit over the catch-all until FR-001 through FR-015 are all satisfied; deferred to an
  optional Phase 9 (§8 below), matching the report's own phase-2 framing ("pure refactor... can
  follow phase 1 at any point without further user-visible churn").
- **DECISION-2 (query-param mechanism, FR-005)**: Use Next.js's native `useSearchParams` +
  `router.push` directly — no `nuqs` or other query-param library. Confirmed this session:
  `frontend/package.json` has no such dependency today, and the filter/sort surface (run
  history's `type`/`sort`, one library category, analytics' `range`/`pipeline`) is small enough
  that hand-written `URLSearchParams` construction is simpler than adding a dependency for it
  (CLAUDE.md simplicity-first: no library for what three call sites can do directly).

**Output**: both resolved inline above — no separate unknowns block needed downstream.

---

## 4. Phase 1 — Catch-all route + path↔view mapping (core mechanism)

**Scope**: FR-001, FR-002, FR-003, FR-004. The load-bearing phase — every other phase adds a
specific screen or behavior on top of this mechanism.

1. **`frontend/src/app/dashboard/page.tsx` → `frontend/src/app/[...view]/page.tsx`**
   (relocated, not duplicated). **Corrected during implementation** (verified against the actual
   code, not assumed): `dashboard/page.tsx` — not `DashboardLayout` — is the real stateful owner
   (auth/token, run streaming, chat, ~40 `useState`s) and renders `<DashboardLayout>` as a child,
   passing everything down via props. `DashboardLayout` owns the `MainView` union
   (`"home"|"library"|"history"|"settings"|"analytics"|"input"|"execution"|"catalog"|
   "saved-workflows"|"composer"`, `:267`) and its `mainView === "..."` render branches (`:2301+`)
   but cannot mount standalone — it has no state of its own to seed. So the catch-all cannot be a
   *new* file that renders `DashboardLayout` fresh; it must *become* the relocated wrapper page,
   parsing `params.view` into the SAME `useState<MainView>` initializer (`:351`) that today only
   ever starts at `"home"`, plus seeding whatever `runId`/`workflowId`/tab state each view needs.
   `/dashboard` itself keeps working — it is simply the `view` param being empty/`["dashboard"]`,
   resolving to the `"home"` case, not a separate route.
2. **`DashboardLayout`** (existing, unchanged internals) — every internal view-change call site
   (`setMainView` and friends, still owned by the relocated wrapper page per task 1) additionally
   calls `router.push(pathFor(view, ids))` so the URL always reflects current view state.
   `pathFor` (in the new `frontend/src/lib/routes.ts`) is the pure inverse of the catch-all's
   parser — one source of truth for the path scheme (`data-model.md`'s Route→Screen table), not
   two drifting implementations.
3. **`frontend/src/app/page.tsx`** (existing root) — fix FR-002: check auth state before
   redirecting; authenticated → `/dashboard`, unauthenticated → `/login`. Today it always sends
   to `/login` regardless of auth state (spec.md §1) — this is a one-line conditional fix, not a
   new mechanism.
4. **Live-stream re-attach (FR-003's hardest case)**: `/runs/{id}/stream`'s view-mount effect
   must, on catch-all mount (including a hard refresh), re-open the existing SSE/websocket
   connection for `runId` from `params`, not only on a client-side `router.push` navigation —
   confirm the current stream-connection hook's dependency array covers a cold mount, not only a
   state transition (this is the one place a refresh legitimately differs from a `push`).
5. **Fetch-by-id for merged views (correction — see `data-model.md`'s Route → Screen table,
   verified against `DashboardLayout.tsx` during implementation kickoff, not assumed).**
   `"execution"` and `"composer"` are NOT one-screen-per-`MainView` — `execution` covers both the
   live stream and every reopened run-detail tab (Preview/Steps/Files/Audit/version/fullscreen),
   and `composer` covers both blank and edit. Setting `mainView` from the URL is necessary but
   NOT sufficient for those two: on a cold mount (direct URL open, not client-side navigation),
   the catch-all must ALSO fetch the run (`getRunSummary`, confirmed in `lib/api.ts`) or the
   saved workflow by id and populate the same state (`reopenedRunStatus`/`pipelineState`-adjacent
   for runs, `savedComposition`-adjacent for workflows) that a click-driven open would have set
   in memory — otherwise the correct `mainView` renders with no data. This is genuinely the
   bulk of Phase 1's real work for the `/runs/{id}*` and `/workflows/{id}/edit` rows, not a
   trivial addition to task 1. Two **TBD** rows remain in `data-model.md` (`/workflows/{id}`'s
   read view, `/workflows/{id}/run`) — resolve which `MainView`/state they need by reading
   `SavedWorkflowsPage`'s open/launch handlers at the start of this task, not assumed here.

**Accept**: pasting any of the 34 target URLs (spec.md §5) into a fresh tab restores that exact
screen WITH its data populated, not just the right empty shell (SC-001). Refreshing
`/runs/{id}/stream` mid-run re-attaches without losing the stream (SC-002). A cold-opened
`/runs/{id}` (no prior client-side navigation) shows that run's real Preview/Steps/Files/Audit
content, fetched fresh. Back/forward across 10 manual navigations shows the correct screen every
time (SC-003). Root `/` respects auth both ways.

---

## 5. Phase 2 — List-screen query params (FR-005)

**Scope**: run history's `?type=&sort=`, one library category's `?category=`, analytics'
`?range=&pipeline=`.

1. Each of the three list screens reads its filter/sort state from `useSearchParams` on mount
   and writes back via `router.push`/`router.replace` (replace, not push, for filter changes
   within the same screen — avoids polluting back-history with every keystroke/toggle) on
   change, using `URLSearchParams` directly (Phase 0 DECISION-2).

**Accept**: SC-005 — a URL carrying a filter/sort choice, opened by a second user/session,
reproduces the identical filtered view, verified for all three screens.

---

## 6. Phase 3 — Library item detail pages (FR-006)

**Scope**: agent/skill/hook detail, currently a modal (go-live report confirms these already
work as modals — §1.3), becomes additionally reachable at `/library/{type}/{slug}`.

1. Add the three detail routes to the catch-all's mapping table (Phase 1 task 1/2). The
   existing modal CONTENT component is reused, rendered full-page instead of in an overlay when
   reached via direct URL — no content redesign (spec.md §6: "any change to what data a screen
   shows" is explicitly out of scope).
2. From the library list screen, clicking an item still opens the existing modal (fast, no
   navigation) but the modal ALSO updates the URL via `router.push` (shallow), so closing and
   reopening via back/forward or a shared link both work — same one-URL-per-screen contract as
   every other screen.

**Accept**: `/library/agents/{slug}` (and skills/hooks equivalents) pasted into a fresh tab shows
that item's detail directly.

---

## 7. Phase 4 — Redirects for retired paths (FR-007)

**Scope**: `/workflow/create?mode=<t>` → `/create/{t}`, `/preview-fullscreen` →
`/runs/{id}/preview/full`.

1. Next.js `redirects()` in `next.config.js` for the static case, or a thin server-redirect
   page for the dynamic (`{id}`-bearing) case — confirm during implementation which of the two
   retired paths needs dynamic-segment handling (only `/preview-fullscreen` carries a run id
   today; confirm via its current query-param shape).

**Accept**: SC-004 — every retired path redirects successfully, verified against the full
retired-path list (spec.md §5's "Removed/redirected" table, mirrored in the go-live report).

---

## 8. Phase 5 — Not-found, error boundary, and `/test-preview` removal (FR-008, FR-013, FR-014)

**Scope**: three small, structurally identical App Router boundary files.

1. **`frontend/src/app/not-found.tsx`** (new) — branded "not found" page, path back into the
   app. *(FR-008, go-live report BLK-12)*
2. **`frontend/src/app/error.tsx` + `frontend/src/app/global-error.tsx`** (new) — branded error
   boundary distinct from the not-found state. *(FR-013, go-live report BLK-11)*
3. **`frontend/src/app/test-preview/`** (existing, 2,443-line mock fixture) — delete the
   directory entirely, not merely unlink it from navigation. *(FR-014, go-live report BLK-13)*

**Accept**: SC-007 (branded error page on a deliberate throw), SC-008 (`/test-preview` behaves
identically to any unrecognized URL, zero references left in the built bundle).

---

## 9. Phase 6 — Deep-link access control + session expiry (FR-009, FR-015)

**Scope**: two related but distinct behaviors — one for opening a link you shouldn't see, one
for a session that dies mid-use.

1. **FR-009**: the catch-all's data-fetching for id-bearing routes (`/runs/{id}`,
   `/workflows/{id}`, etc.) already goes through `lib/api.ts`'s existing `ApiError` path
   (Constitution Check §2) — on a 401, redirect to login; on a 403/404-equivalent ownership
   failure, render the not-found state from Phase 5 rather than a raw error.
2. **FR-015**: centralize the "session expired" redirect in the same `lib/api.ts` layer that
   already throws `ApiError` on a 401 (go-live report §1.3 confirms this class exists) — one
   interceptor-style handler, not per-screen duplication, so it fires "from any screen" as FR-015
   requires. Redirect target: `/login?expired=1`, with the login page showing a visible message
   for that query param.

**Accept**: SC-009 — an expired/invalid session from any of the 34 screens lands on `/login`
with a visible message, verified for one screen per area in spec.md §5's inventory.

---

## 10. Phase 7 — Run-launch navigation + saved-workflow edit entry (FR-010, FR-011)

**Scope**: two existing gaps the go-live report already named directly.

1. **FR-010**: every run-launch call site (`/workflows/{id}/run`, the creation flows) navigates
   to `/runs/{newId}/stream` immediately on run creation, reusing Phase 1's `pathFor` helper —
   not a new navigation mechanism.
2. **FR-011**: confirm `/workflows/{id}/edit`'s Phase 1 task 5 fetch-by-id (mapping table entry
   + `savedComposition` population) is reachable from an actual UI entry point on the saved-
   workflow's own screen (e.g. an "Edit" affordance on `/workflows/{id}`'s read view) — the
   mapping/fetch mechanism is Phase 1's job (moved there during this correction pass, since it's
   the same `composer` fetch-by-id work as the rest of that view group); this phase's job is
   closing the actual UI gap the go-live report named ("backend PATCH exists, no UI entry").

**Accept**: SC-002's "run launched from `/workflows/{id}/run` lands on `/runs/{newId}/stream`"
scenario passes; a saved workflow opens, edits, and re-saves successfully (go-live report
acceptance-gate item, now satisfied here).

---

## 11. Phase 8 — Observability page dimension (FR-012)

**Scope**: making the current screen identifiable wherever errors/analytics are recorded.

1. Derive a canonical `screen` label from the catch-all's parsed `mainView` (Phase 1's lookup
   table already names each screen — reuse those names verbatim, don't invent a second taxonomy)
   and thread it into whatever error-tracking/analytics call sites already exist. **Does not
   include standing up Sentry or a new analytics pipeline** — that's the go-live report's BLK-7/
   BLK-8/§5.2 observability items, explicitly not this spec's scope (spec.md §6 doesn't call
   this out explicitly but it follows the same "routing, not observability infrastructure"
   boundary as everything else this spec excludes).

**Accept**: SC-006 — a manual walkthrough of all 34 screens shows a distinct, correct screen
label wherever tracking already fires today.

---

## 12. File-by-file change map

| File | Phase | Change |
|---|---|---|
| `frontend/src/lib/routes.ts` | 1 | **NEW** — typed path builders + parser, single source of truth (both directions) |
| `frontend/src/app/dashboard/page.tsx` → `frontend/src/app/[...view]/page.tsx` | 1 | **RELOCATED** (not duplicated) — becomes the catch-all; parses `params.view` via `routes.ts` into the existing `MainView` state/ids at mount |
| `frontend/src/components/layout/DashboardLayout.tsx` | 1 | `router.push` (via `routes.ts`) on every view-change call site; `MainView` union/render branches otherwise unchanged |
| `frontend/src/app/page.tsx` | 1 | Fix root auth-conditional redirect (FR-002) |
| run-detail stream view / hook | 1 | Cold-mount re-attach for `/runs/{id}/stream` |
| run/workflow fetch-by-id (new helper, exact file TBD — likely inside the relocated wrapper or a new hook) | 1 | Populate `reopenedRunStatus`/`savedComposition`-equivalent state on cold mount for `/runs/{id}*` and `/workflows/{id}/edit` — see plan.md Phase 1 task 5 |
| run history / library category / analytics screens | 2 | `useSearchParams` read + `router.replace` write |
| library detail modal/screen component | 3 | Shallow `router.push` alongside existing modal open |
| `next.config.js` (or thin redirect pages) | 4 | `/workflow/create?mode=`, `/preview-fullscreen` redirects |
| `frontend/src/app/not-found.tsx` | 5 | **NEW** |
| `frontend/src/app/error.tsx`, `global-error.tsx` | 5 | **NEW** |
| `frontend/src/app/test-preview/` | 5 | **DELETE** |
| `frontend/src/lib/api.ts` | 6 | 401 → redirect-to-login interceptor; ownership-failure → not-found |
| `frontend/src/app/login/page.tsx` | 6 | `?expired=1` message rendering |
| run-launch call sites (creation flows, `/workflows/{id}/run`) | 7 | Navigate to `/runs/{newId}/stream` on creation |
| `SavedWorkflowsPage` / workflow read-view component | 7 | Add the actual "Edit" UI affordance calling Phase 1's `/workflows/{id}/edit` |
| error-tracking / analytics call sites | 8 | Thread `screen` label from Phase 1's names |

**Zero new dependencies across every phase** (Phase 0 DECISION-1/2) — no package.json change.

---

## 13. Risks

| Risk | Phase | Mitigation |
|---|---|---|
| **Stream re-attach on cold mount vs. warm navigation are genuinely different code paths** | 1 | Called out explicitly as task 4 — write a test that hard-reloads `/runs/{id}/stream` (not just `router.push`s to it) before considering Phase 1 done |
| **`pathFor`/parser drift** (two hand-written functions silently diverging) | 1 | Single lookup table shared by both directions (task 1/2), not two independently maintained switch statements |
| **`MainView` is coarser than "one screen, one view"** — `execution` and `composer` each cover multiple distinct routes (corrected this pass, verified against `DashboardLayout.tsx`, not assumed); a cold-mounted id-bearing route needs a real fetch to populate the same state a click-driven open would have set, or it renders the right shell with no data | 1 | Scoped as its own explicit task (task 5), not folded silently into the mapping-table task; two rows in `data-model.md` (`/workflows/{id}` read view, `/workflows/{id}/run`) are marked TBD rather than guessed, pending one more read of `SavedWorkflowsPage`'s handlers |
| **FR-005's filter state polluting back-history** | 2 | Explicit `router.replace` (not `push`) for in-screen filter changes, called out in task 1 |
| **Deleting `/test-preview` breaks something that quietly depended on it** | 5 | Grep the codebase for any reference to the route/component before deletion (SC-008 already requires a zero-reference bundle check) |
| **FR-009/FR-015 both touch `lib/api.ts`'s error handling — risk of one overwriting the other's logic** | 6 | Both land in the same phase deliberately, as one coordinated change to the same file, not two separate PRs racing each other |
| **The stateful owner is `dashboard/page.tsx`, not `DashboardLayout`** — corrected during implementation kickoff (Phase 1 task 1); the original draft assumed a lighter shell that could be wrapped from outside | 1 | Relocate the existing wrapper page itself rather than growing a second, parallel state tree — avoids two sources of truth for the same ~40 `useState`s |

---

## 14. Phase sequencing summary

```
Phase 1 (catch-all + path↔view core)
  │
  ├──> Phase 2 (query-param filters)
  ├──> Phase 3 (library detail pages)
  ├──> Phase 4 (legacy redirects)
  ├──> Phase 5 (not-found / error / test-preview removal)
  ├──> Phase 6 (deep-link access + session expiry)
  ├──> Phase 7 (run-launch nav + saved-workflow edit)
  └──> Phase 8 (observability screen label)
```

Phases 2–8 all depend only on Phase 1's mapping table existing; none depend on each other, so
they can run in parallel once Phase 1 lands. **Optional Phase 9** (not required by any FR/SC —
go-live report §5.2.4's "pure refactor"): split `DashboardLayout`'s view branches into real
per-segment `page.tsx` files, add `middleware.ts` for server-side auth redirects, delete the
catch-all. No URL changes, no user-visible churn — purely an internal-structure follow-on,
consistent with spec.md §6 leaving this decision to planning and this plan choosing to defer it.

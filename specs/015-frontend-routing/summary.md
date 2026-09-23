# Implementation Summary: Frontend Routing — one real URL per screen

**Status: DONE.** All 15 functional requirements and 9 success criteria are implemented and verified live. Every defect found across three independent verification passes (V7, the Final Audit, and the `ba-squad` follow-up) is fixed. See [`audit.md`](audit.md) for the full verification history and [`tasks.md`](tasks.md) for the task-by-task build log.

## What shipped

Before this spec, ten distinct screens — home, run history, run detail (five sub-tabs), saved workflows, workflow read/edit, library (three categories), settings (four tabs), and analytics — all lived inside one 2,862-line page sharing a single URL, `/dashboard`. Which screen showed was tracked only in in-memory component state. Refreshing lost your place; back/forward did nothing useful; nothing could be bookmarked, shared, or attributed in error tracking.

Every screen now has its own real, stable URL:

- **34 distinct screens** addressable at their own path, each restorable by pasting the URL into a fresh tab (FR-001, SC-001).
- **The live run stream is its own URL** (`/runs/{id}/stream`); launching a run navigates there immediately, and refreshing mid-run re-attaches to the same live stream instead of losing it (FR-003, FR-010, SC-002).
- **Back/forward navigation retraces real screen history** (FR-004, SC-003).
- **List filters and sort order live in the URL** — run history's type/sort, a library category filter, analytics' date range — so a shared link reproduces the same filtered view for another user (FR-005, SC-005).
- **Library item detail is a real page**, not a modal, independently linkable per item (FR-006).
- **Every retired ad-hoc path redirects** — `/workflow/create?mode=...` → `/create/{mode}`, `/preview-fullscreen` → the new run-preview flow, `/library`/`/settings` bare paths → their default tab (FR-007, SC-004).
- **A branded not-found page** for unrecognized URLs (FR-008, SC-008), and a **distinct branded error page** for unhandled application errors (FR-013, SC-007), replacing the framework defaults.
- **Deep links to inaccessible resources** (not logged in, not the owner) show an access-appropriate message rather than leaking data (FR-009).
- **A saved workflow is reachable in both a read view and an edit view** from its own URL — previously there was no editing entry point at all (FR-011).
- **The current screen carries a distinct, correct label** wherever the app records errors or usage events (FR-012, SC-006 — scoped: verified true for the app's two error boundaries; no broader analytics/tracking pipeline exists in the app to extend this into, confirmed by exhaustive sweep, and building one was explicitly out of scope).
- **`/test-preview` is fully removed** from the route tree, not just unlinked (FR-014).
- **Session expiry redirects to `/login` with a visible message from any screen**, not only the handful that already handled it — closed structurally via a shared `authedFetch()` guard after 9+ separate instance-level gaps were found and fixed one at a time (FR-015, SC-009).

## Architecture

- **`frontend/src/lib/routes.ts`** — the single source of truth for every URL. Typed builder functions (`routes.runDetail(id)`, `routes.settingsAiModel()`, etc.) on one side, and `parseViewPath()` — the inverse, turning a URL's path segments back into a typed screen descriptor — on the other. Every navigation in the app goes through a `routes.*` builder; a hand-written path literal outside this file is treated as a defect (enforced repeatedly across every verification pass).
- **`frontend/src/app/[...view]/page.tsx`** — a single required catch-all route (`[...view]`, not the optional `[[...view]]` form — the optional form conflicts with the root `page.tsx` at the same specificity, a bug fixed early in this spec's history) that renders all 34 screens behind one shared layout, per the spec's own explicit choice not to split the page into per-route file segments (out of scope, see spec.md §6).
- **`frontend/src/middleware.ts`** — handles the one redirect case `next.config.ts`'s static `redirects()` genuinely cannot: `/workflow/create?mode={t}` → `/create/{t}` without leaking the query string onto the destination (a real Next.js 16.2.4 framework limitation, not a config mistake — see `audit.md`'s F12 entry for the full root-cause trail). Must live inside `src/` for this project's `tsconfig` layout, not the project root.
- **`frontend/next.config.ts`** — static `redirects()` for the simpler cases: bare `/library` → `/library/agents`, bare `/settings` → `/settings/profile`.
- **`authedFetch()`** (`frontend/src/lib/api.ts`) — the structural fix for FR-015: a drop-in guarded fetch wrapper that centralizes the 401-triggers-logout-redirect behavior, replacing what had been ad hoc per-call-site handling that kept missing new call sites.

## Verification history (summary — see `audit.md` for full detail)

1. **V7** (this spec's own final acceptance hard gate) passed on its own criteria — all 15 FRs + 9 SCs checked, full test suite green.
2. **Final Audit** — an independent, adversarially-verified re-check commissioned specifically because this spec's history showed prior "PASS" verdicts weren't reliable (the FR-015 defect class alone was independently rediscovered multiple times by different checks). Found **21 confirmed defects**, including 4 genuine blockers V7's own sweep never caught — a live feature regression and a real contract violation among them.
3. **Audit-fixes pass** — automated, dependency-graph-scheduled fix run with adversarial re-verification. Closed 16 of 17 actionable findings; 1 (`?mode=` query-string leak) was deliberately left open rather than force-fixed once root-caused as a Next.js framework limitation needing a different mechanism.
4. **`ba-squad` follow-up** — closed that last item via `middleware.ts`, then ran an exhaustive live walkthrough (all 34 routes, actual session expiry, cross-account-access denial, the full back/forward sequence, launch and edit persistence) that surfaced **4 further findings** no prior pass had caught, including a second cold-mount data-loading gap that required tracing through two different sibling components for two different workflow types. All 4 fixed and independently re-verified live.

**Final health check:** `npx tsc --noEmit` — 38 pre-existing baseline errors (all in test files), zero new. `npx vitest run --no-coverage --maxWorkers=3` — **135/135 files, 1165/1165 tests passing**. `package.json` unchanged throughout (no routing library was added — Next.js App Router is the router, per this spec's own Phase 0 decision).

## What's explicitly out of scope (by the spec's own design, not a gap)

- Splitting the shared page component into per-route file segments.
- Any change to what data a screen shows.
- Spec 014's conditional-gates/canvas work.
- The pre-existing `/login` styling defect and the `/workflow/create` global-nav layout issue (both pre-existing, non-routing bugs).
- Migrating JWT storage from localStorage to httpOnly cookies.

See spec.md §6 for the complete, original list.

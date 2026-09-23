# Audit Log: 015-frontend-routing

Standalone log of the post-V7 Final Audit, its automated fix pass, and the `ba-squad` follow-up that closed the last item plus 4 more findings a live walkthrough surfaced. Full per-finding detail (evidence, defect text, file/line citations) lives in [`tasks.md`](tasks.md)'s [Final Audit](tasks.md#final-audit) section — this file is the compact, chronological record of what happened and why.

**Final status: closed.** Every finding from every pass — the original 21, plus the 5 handled in the squad follow-up — is fixed and independently live-verified, or resolved as correctly out of scope with reasoning recorded. See [`summary.md`](summary.md) for the implementation overview.

## Timeline

| Date | Event |
|---|---|
| 2026-08-21 | V7 (final acceptance, hard gate) PASSED on its own criteria — full vitest suite 1156/1156, tsc clean, `package.json` unchanged. |
| 2026-08-21 | **Final Audit** run: independent, adversarially-verified cross-check of spec.md/plan.md/data-model.md/contracts/route-map.md against the implementation, plus live re-exercise of prior "done" claims. 7 dimensions, 29 agents, finder-then-adversarial-verifier pipeline. **Result: 21 confirmed findings** (4 blocker · 9 real-but-minor · 8 worth-noting) that V7's own sweep missed. |
| 2026-08-21 | **Audit-fixes pass** run (`.claude/workflows/015-audit-fixes.js`, run `wf_6e4a513b-028`): 17 of the 21 findings were actionable and dispatched, dependency-graph-scheduled, file-collision-safe, 3-normal + 2-opus-escalated retry ladder per finding. **Result: 16/17 fixed and independently re-verified live**; 1 (`?mode=` leak) deliberately left open rather than force-fixed — see below. |
| 2026-08-21 | **`ba-squad` follow-up** run (qa-engineer + 2 junior-engineers + 1 senior-engineer, orchestrator-relayed): fixed the 1 remaining item via a different mechanism, then ran a T29-equivalent live walkthrough (all 34 routes) that surfaced and closed 4 further findings never caught by any prior pass. **Result: 5/5 fixed and independently re-verified live. Spec fully closed.** |

## Why the Final Audit happened

V7 verified all 15 FRs + 9 SCs and passed as a hard gate, but its own sweep never caught 4 genuine blockers — including a live feature regression (`/preview-fullscreen`'s "Full Screen" button silently broken) and a real contract violation (3 of 4 `/settings/*` routes ignoring the URL entirely). The Final Audit was commissioned specifically to adversarially re-check completed work rather than take prior PASS verdicts at face value, following this spec's own recurring pattern: the FR-015 session-expiry defect class was independently rediscovered and re-fixed multiple times earlier in this spec's history because each check only grepped for *existing* handling, never absence of handling.

## Findings, by dimension (21 total)

| # | Dimension | Clean / defects found |
|---|---|---|
| 1 | FR-001–005 vs code | 3 defects (1 blocker-elsewhere-dup, 2 minor/worth-noting) |
| 2 | FR-006–010 vs code | 4 defects (1 blocker, 2 minor, 1 worth-noting) |
| 3 | FR-011–015 vs code (highest risk) | 3 defects (1 minor, 2 worth-noting) |
| 4 | SC-001–005 vs live behavior | 2 defects (1 blocker, 1 minor) |
| 5 | SC-006–009 vs live behavior | 1 defect (minor) |
| 6 | Re-verify specific prior agent claims | 1 defect (blocker) |
| 7 | Hygiene, scope, contract-accuracy sweep | 7 defects (1 blocker-dup, 2 minor, 4 worth-noting) |

Severity mix: **4 blocker** (1 of the 4 rows is a duplicate of another blocker row, same fix) · **9 real-but-minor** · **8 worth-noting**. See `tasks.md`'s Final Audit tables for the full text of every row.

## Fix pass: what got fixed

Of 21 findings, 17 were actionable (4 duplicate/informational/already-resolved were excluded). **16 fixed, independently re-verified live:**

**Blockers (4/4 fixed):**
- `/preview-fullscreen` "Full Screen" feature regression — restored the `sessionStorage["__app_preview__"]` render path alongside the new `?runId=` redirect.
- 3 of 4 `/settings/*` routes ignoring the URL (always showed Profile tab) — `initialSection` now threaded from the URL through `page.tsx` → `DashboardLayout.tsx` → `AccountSettings`.
- Hard-refresh mid-run on a transient 403/404 permanently stranding a live run — added a `runConnection.liveRunIds` reconciliation/retry step before giving up.
- Bare `/library`/`/settings` 404ing instead of redirecting — two static `next.config.ts` redirects added.

**Real-but-minor / worth-noting (12/13 fixed):**
- `WorkflowHistory.tsx` stale-closure double-`router.replace` (same defect class as the earlier T13 fix).
- `/workflows/{id}` read-view catch block over-broadly treating any error as not-found — narrowed to 403/404 only.
- `AccountSettings.tsx`'s 3 Constitution-section `authedFetch` calls missing `${ENV.API_URL}` prefix (a 10th instance of the FR-015 defect class).
- `LaunchWizard.tsx`'s 2 hardcoded `/dashboard` literals → `routes.home()`.
- `admin/page.tsx`'s 3 hardcoded `/login` literals → `routes.login()`.
- `route-map.md` vs `next.config.ts` 301-vs-307 doc drift — judged 307 correct, doc corrected.
- `routes.ts` admin dead-code branch — explanatory comment added, no behavior change.
- `SavedWorkflowsPage.test.tsx` missing an Edit-action test — added.
- SC-006 (screen-label tracking) — confirmed no tracking pipeline exists anywhere outside the 2 error boundaries; documented as the actual current scope, no new pipeline invented (correctly out of scope).
- `plan.md`'s stale `[[...view]]` (optional catch-all) references — corrected to `[...view]`.
- `data-model.md`'s stale `/create/{mode}` row — corrected to match T4's already-resolved description.
- `page.tsx`'s 6 `console.error` calls carrying internal `[T7]`/`[T8]`/etc. task-ID tags — removed, descriptive text preserved.
- 9 leftover debug/scratch Playwright spec files (`_v2-debug*.spec.ts` etc.) — deleted directly, separately from the workflow, earlier the same session.

Verification: `V-BLOCKERS` validator re-exercised all 4 blockers live (Playwright/curl) — PASS. `V-FINAL` validator independently re-confirmed the other 12 fixes with fresh evidence (git diff + live re-run, not trusting the fixing agent's own self-report) — PASS for everything except the one open item below.

## F12 root-cause investigation (fixed in the squad follow-up below)

**`?mode=` query-string leak on the `/workflow/create` → `/create/{mode}` redirect** (`frontend/next.config.ts`). Live symptom: `/workflow/create?mode=ppt` lands on `/create/ppt?mode=ppt` instead of a clean `/create/ppt`.

Two independent senior-engineer attempts (plus a third stopped mid-investigation) tried to fix this via `next.config.ts`'s `redirects()` config and could not. Root cause, confirmed by reading Next.js 16.2.4's own source (`node_modules/next/dist/shared/lib/router/utils/prepare-destination.js`, line ~281-284): the framework unconditionally re-merges the original incoming request query into the final redirect destination query, regardless of whether that key was consumed via a `has` match and referenced by name in the destination path. This was verified two ways — reading the source directly, and empirically testing an alternate config (fully literal per-mode rules, no `:mode` placeholder at all) that leaked identically. **Not fixable via `next.config.ts` `redirects()` alone; needs a different mechanism** (e.g. a middleware-based redirect that can control the outgoing query explicitly).

Both investigation attempts self-reported reverting their experimental edits; one left a stray unreverted change (`destination: "/create/:mode?"` instead of `"/create/:mode"`, an unrelated optional-param syntax experiment) which was caught and reverted directly after the workflow was stopped. `next.config.ts` now carries only the 16 other fixes' changes.

**Scope note for whoever picks this up:** `?mode=` is intentionally ppt/prototype-only — `DashboardLayout.tsx` calls `routes.workflowCreateLegacy("ppt"/"prototype")` for those two modes specifically. `app` and `user-stories` never go through this redirect at all; they call `routes.createApp()`/`routes.createUserStories()` directly, which already produce clean `/create/app` and `/create/user-stories` paths. A fix for this should not touch `DashboardLayout.tsx` or try to unify the two conventions.

## Squad follow-up (2026-08-21) — closed the last item + 4 new ones

A `ba-squad` run (qa-engineer + 2 junior-engineers, escalating to senior-engineer as needed) was dispatched to take the one item left open above and sweep the rest of spec 015 for anything still unclosed, per the user's explicit "I want all things implemented and closed."

**F12 — `?mode=` query leak — now FIXED.** Resolved via `frontend/src/middleware.ts` (note: had to be placed inside `src/`, not the frontend project root — this project's `tsconfig.json` maps `@/*` → `./src/*`, and Next.js requires middleware to live inside `src/` for that layout; the first attempt at this location cost real debugging time before the location bug was found). The middleware intercepts `/workflow/create`, reads the `mode` param, and issues a redirect built from a fresh `URL` object containing only the destination pathname — no query string carried over. The now-redundant `/workflow/create` entry was removed from `next.config.ts`. Live-verified: `?mode=ppt` → 307 → `/create/ppt` (clean), `?mode=prototype` → 307 → `/create/prototype` (clean), `/library`/`/settings` redirects unaffected. Independently re-verified by qa-engineer with its own curl calls and a direct read of both files.

**A live qa-engineer walkthrough (T29-equivalent, all 34 routes + FR-015/SC-001–009 checks) then surfaced 4 further findings, none present in the original 21** — all now fixed and independently re-verified live:

| # | Finding | Fix | Status |
|---|---|---|---|
| 1 | Run-detail tab clicks (Preview/Steps/Files/Audit on `/runs/{id}`) never updated the URL — `PreviewPanel.tsx`'s `onTabSelect` prop had zero consumers anywhere in the codebase, breaking link-sharing and back/forward for the tab actually being viewed. | Added a handler in `DashboardLayout.tsx` mapping each tab to its `routes.ts` builder (`runDetail`/`runSteps`/`runFiles`/`runAudit`) and wired it to `<PreviewPanel onTabSelect=...>`. | ✅ Fixed — live-verified: all 4 tabs update the URL on click, and 4 consecutive browser-back presses each landed on the correct prior tab with the right one visually selected. |
| 2 | Cold-opening `/workflows/{id}/run` (hard reload, not client nav) showed an empty launch panel ("0 agents") despite the workflow having real agents in the DB — a cold-mount data-loading gap distinct from the already-fixed `/edit` route. | Two components needed the same fix, one per workflow type: **`LaunchWizard.tsx`** (ppt/prototype workflows) — added `libraryAgents` to the restore effect's dependency array, guarded restoration on `libraryAgents.length > 0`, deferred sessionStorage draft-clear until agents actually restore. **`IdeaInputPage.tsx`** (user_stories and other types) — the first fix attempt targeted only `LaunchWizard.tsx` and missed this sibling component entirely (different `base_pipeline_type` routes through a different component); a `useState` lazy initializer ran once at mount before `ALL_LIBRARY_AGENTS` had loaded and never retried. Added an `attemptedInitialRestoreRef` guard that retries the `initialAgentIds` → `ALL_LIBRARY_AGENTS` mapping once the library finishes loading. | ✅ Fixed — live-verified: hard-reloading the exact workflow originally reported (a 6-agent `user_stories` workflow) now shows all 6 agents pre-filled with correct names, "Save workflow" enabled, twice confirmed via both `page.goto()` and `window.location.reload()`. |
| 3 | `contracts/route-map.md` documented `/runs/{id}/preview/full` as a distinct "Fullscreen artifact" view, but it renders byte-identical to plain `/runs/{id}` — and the real "Full Screen" UI buttons don't navigate there at all, they open a `blob:` URL in a new tab. | Investigated and found 3 independent "Full Screen" mechanisms in the live UI, none of which route through `/runs/{id}/preview/full` — a genuine, deliberate `blob:`-new-tab pattern (implemented 3× independently, one site carries an explicit code comment explaining the rationale) that correctly serves live in-memory content a route-based fetch-by-id can't. Judged the doc wrong, not the code (same precedent as the earlier F5 finding) — corrected `contracts/route-map.md`'s row and `data-model.md`'s matching stale "+ fullscreen flag" claim. No code changed. | ✅ Resolved (doc-only) — independently re-verified: `git diff` confirms zero `.ts`/`.tsx` files touched; all cited component/function names and the "3 mechanisms, none routing through `preview/full`" claim independently re-confirmed by grep and direct code read. |
| 4 | `admin/page.tsx:161` — one more hardcoded `router.replace("/dashboard")` literal, distinct from the one already fixed at line 257. | Replaced with `routes.dashboard()`. | ✅ Fixed — grep-confirmed clean. |

**Final health check after this pass:** `npx tsc --noEmit` — 38 baseline errors, no new ones. `npx vitest run --no-coverage --maxWorkers=3` — **135/135 files, 1165/1165 tests passing**.

**One item intentionally not re-run:** SC-007's deliberate-throw test requires a temporary code edit (throw + revert) that qa-engineer isn't tool-permitted to make (no Write/Edit access, by design). The original Final Audit already performed this exact live test (real edit + revert, byte-identical confirmed) and nothing in that code path (`error.tsx`/`global-error.tsx`) has changed since — treated as still valid rather than redundant re-verification.

**Spec 015-frontend-routing status: all identified findings closed.**

## Sources

- Final Audit findings + evidence: `tasks.md` → [Final Audit](tasks.md#final-audit) section, dimensions 1-7.
- Fix-pass workflow script: `.claude/workflows/015-audit-fixes.js`.
- Fix-pass run journal: `wf_6e4a513b-028` (transcript dir under this session's `subagents/workflows/`).
- Squad follow-up: `ba-squad` run (qa-engineer + 2 junior-engineers + 1 senior-engineer, orchestrator-relayed), 2026-08-21.

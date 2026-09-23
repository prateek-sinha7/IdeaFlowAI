export const meta = {
  name: '015-audit-fixes',
  description: 'Fix all 17 actionable findings from the 015-frontend-routing full audit (4 blockers, 9 real-but-minor, 4 worth-noting) — dependency-graph scheduled, file-collision safe',
  phases: [
    { title: 'Fix', detail: '17 independent findings, file-collision serialized' },
    { title: 'Verify', detail: 'V-BLOCKERS (the 4 live regressions) + V-FINAL (full sweep)' },
  ],
}

// ---------------------------------------------------------------------------
// Source: the 015-frontend-routing full-audit workflow (29 agents, 21 findings,
// each independently adversarially re-verified with live reproduction before
// being counted as real). 2 of 21 already fixed by hand (leftover debug files,
// a stale tasks.md row) — this script covers the remaining 17 actionable ones.
// Finding #15 was a duplicate of #2 (found independently by a second auditor);
// #19 was explicitly confirmed NOT a regression and excluded entirely.
// ---------------------------------------------------------------------------

const REPO_NOTES = `
Repo: VELOCITY-AI frontend, Next.js 16 App Router, React 19, repo root /Users/bilala/Developer/Projects/VELOCITY-AI, work from frontend/.
Verify with: npx tsc --noEmit (type check) and npx vitest run --no-coverage --maxWorkers=3 <file> (scoped; --maxWorkers=3 avoids the worker-contention stalls this environment has shown on the full suite).
Full context: specs/015-frontend-routing/{spec.md,plan.md,data-model.md,contracts/route-map.md,tasks.md} — tasks.md has a "## Final Audit" section documenting exactly how each of these findings was discovered and verified; read the relevant part before starting your fix.

STANDING RULES:
1. Change only what your task names. Do not tidy adjacent code, comments, or imports you did not orphan.
2. Never run a state-changing git command (no stash/checkout--/reset/clean/restore). Read-only git is fine — git show <ref>:<path> to read historical file content is explicitly useful for finding #4.
3. Do not commit. Leave changes in the working tree.
4. If your anchor text/file is not found verbatim, do NOT guess — return status "blocked" with why.
5. Every path string goes through frontend/src/lib/routes.ts. A hand-written route literal anywhere else is a defect (this is literally what several of these findings are about — don't introduce a new one while fixing another).
6. Do NOT add a routing library or any new package.json dependency.
7. Do NOT edit specs/015-frontend-routing/tasks.md — a final step owns that file.
8. This spec's entire history is full of fixes that were self-reported "done" and later found still broken by stricter live verification. Whichever finding you're fixing was ALREADY live-reproduced once (the audit's own evidence trail explains exactly how) — re-run that same reproduction method yourself to confirm your fix actually closes it. A fix that only "looks right on reading the diff" is not acceptable here.
`.trim()

const TASK_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    taskId: { type: 'string' },
    status: { type: 'string', enum: ['done', 'blocked'] },
    filesChanged: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    acSelfCheck: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          met: { type: 'boolean' },
          note: { type: 'string' },
        },
        required: ['criterion', 'met'],
      },
    },
    blockers: { type: 'string' },
  },
  required: ['taskId', 'status', 'filesChanged', 'summary', 'acSelfCheck'],
}

const VALIDATOR_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    validatorId: { type: 'string' },
    pass: { type: 'boolean' },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          result: { type: 'string', enum: ['pass', 'fail'] },
          evidence: { type: 'string' },
        },
        required: ['criterion', 'result', 'evidence'],
      },
    },
    failedTasks: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['validatorId', 'pass', 'checks', 'failedTasks', 'summary'],
}

const VIEW_PAGE = 'frontend/src/app/[...view]/page.tsx'
const ROUTES_TS = 'frontend/src/lib/routes.ts'
const ROUTES_TEST = 'frontend/src/lib/routes.test.ts'
const NEXT_CONFIG = 'frontend/next.config.ts'
const ROUTE_MAP_MD = 'specs/015-frontend-routing/contracts/route-map.md'
const ACCOUNT_SETTINGS = 'frontend/src/components/settings/AccountSettings.tsx'
const ACCOUNT_SETTINGS_TEST = 'frontend/src/components/settings/AccountSettings.render.test.tsx'
const DASHBOARD_LAYOUT = 'frontend/src/components/layout/DashboardLayout.tsx'
const WORKFLOW_HISTORY = 'frontend/src/components/history/WorkflowHistory.tsx'
const PREVIEW_FULLSCREEN = 'frontend/src/app/preview-fullscreen/page.tsx'
const APP_BUILDER_PREVIEW = 'frontend/src/components/preview/AppBuilderPreview.tsx'
const PREVIEW_PANEL = 'frontend/src/components/preview/PreviewPanel.tsx'
const ERROR_TSX = 'frontend/src/app/error.tsx'
const GLOBAL_ERROR_TSX = 'frontend/src/app/global-error.tsx'
const RUN_CONNECTION_PROVIDER = 'frontend/src/components/RunConnectionProvider.tsx'

const NODES = {
  F1: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [WORKFLOW_HISTORY],
    file: WORKFLOW_HISTORY, traces: 'FR-005 — same defect class as T13 (already fixed once for LibraryPage.tsx)',
    desc: `WorkflowHistory.tsx has the exact stale-closure double-router.replace bug already found and fixed for LibraryPage.tsx/AnalyticsPage.tsx (T13). Two separate useEffects — a mount-read effect (reads searchParams, calls setFilterType/setSortKey, then sets initializedFromUrl.current=true) and a write-back effect (gated only on that ref, not on the state having actually committed) — run back-to-back in the same initial commit. The write-back effect's FIRST execution reads filterType/sortKey from its own stale closure (still the useState defaults), so it calls router.replace with the DEFAULT (empty) params, silently dropping the real query string that was in the address bar at mount. It self-corrects on the next render (a second replace() with the right values), so this is not user-visible in the steady state, but it produces two history.replaceState calls where one is correct. Fix: match LibraryPage.tsx's/AnalyticsPage.tsx's ALREADY-FIXED pattern exactly — read LibraryPage.tsx's current write logic (search for its filter onClick/onChange handlers) and do the same here: remove the separate reactive write-back effect entirely, and instead call router.replace inline, directly inside the filter/sort control's own onClick/onChange handler, alongside the setState calls.`,
    ac: [
      'The separate reactive write-back effect is gone; router.replace is called inline in the filter/sort handler(s) instead, matching LibraryPage.tsx/AnalyticsPage.tsx\'s pattern.',
      'Write and run a temporary test (delete after use) that mounts WorkflowHistory with useSearchParams returning non-default filter/sort values and spies on router.replace — confirm the FIRST and ONLY call already has the correct filter/sort params (no longer two calls, no longer a first bare-/runs call).',
      'Existing WorkflowHistory.test.tsx suite still passes.',
    ],
  },
  F2: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [NEXT_CONFIG],
    file: NEXT_CONFIG, traces: 'FR-001 — contract violation, confirmed blocker (2 independent auditors)',
    desc: `Bare /library and /settings currently 404 instead of redirecting to /library/agents and /settings/profile respectively, contradicting contracts/route-map.md's documented behavior (which lists both as "redirect only" in its live Screens table). Root cause: parseViewPath (routes.ts) returns {screen:'unknown'} for both bare paths, which the catch-all renders as notFound(). PREFERRED FIX (simpler, does not touch parseViewPath/routes.test.ts at all): add two static redirect entries to next.config.ts's redirects() array — { source: '/library', destination: '/library/agents', permanent: false } and { source: '/settings', destination: '/settings/profile', permanent: false } — matching the existing /workflow/create redirect's shape. Since both source paths are exact static segments (not dynamic), a next.config redirect handles them before the request ever reaches the catch-all/parseViewPath, so the underlying parseViewPath 'unknown' behavior for these two inputs can stay as-is (it's now simply never hit by real navigation) — do NOT change routes.ts or routes.test.ts unless you determine the next.config approach genuinely cannot work (state why, precisely, before falling back to a parseViewPath-level fix).`,
    ac: [
      'A live request to /library redirects to /library/agents; /settings redirects to /settings/profile — verified via a live dev-server curl or Playwright navigation, not just reading the config.',
      'No change to routes.ts/routes.test.ts unless the next.config approach was genuinely infeasible (and if so, explain precisely why in your summary).',
      'The existing /workflow/create?mode= redirect still works unchanged.',
    ],
  },
  F3: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: [ROUTES_TS],
    file: ROUTES_TS, traces: 'data-model.md consistency — worth-noting, not a functional bug',
    desc: `routes.admin() and parseViewPath's 'admin' branch are dead code — Next.js always resolves the pre-existing static frontend/src/app/admin/page.tsx ahead of the [...view] catch-all for the exact path /admin, so this branch never actually executes in the running app. This is not a functional bug (the real /admin page works fine). Add a short one-line comment directly above the 'admin' branch in parseViewPath (and above the routes.admin() builder if it has none) explaining it's intentionally unreachable dead code because a static app/admin/page.tsx takes precedence, kept only so routes.ts stays the complete documented map of every screen in the contract. Do not remove the branch/builder — removing it is a larger, riskier diff than a one-line comment for a purely cosmetic/documentation finding.`,
    ac: [
      'A clear comment exists above both the parseViewPath admin branch and the routes.admin() builder explaining they are intentionally unreachable and why.',
      'No behavior change — routes.ts still exports the same functions with the same signatures.',
      'npx tsc --noEmit clean for this file.',
    ],
  },
  F4: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [PREVIEW_FULLSCREEN, APP_BUILDER_PREVIEW, PREVIEW_PANEL, WORKFLOW_HISTORY],
    file: `${PREVIEW_FULLSCREEN} (+ ${APP_BUILDER_PREVIEW}, ${PREVIEW_PANEL}, ${WORKFLOW_HISTORY})`, traces: 'FR-007 — CONFIRMED BLOCKER: a real, live feature regression introduced by this spec',
    desc: `This spec's earlier T18 rewrite of /preview-fullscreen into a redirect-only page broke the LIVE App Builder "Full Screen" feature. Read git show 847f4c1f3:frontend/src/app/preview-fullscreen/page.tsx FIRST to see the exact pre-015 behavior you need to restore (it read a sessionStorage key "__app_preview__" containing {files, projectName} and rendered <AppBuilderPreview> directly with loading/quota/error states). Then read the CURRENT AppBuilderPreview.tsx's handleFullscreen (search for "__app_preview__" and "window.open") to confirm it still writes that same sessionStorage payload and opens /preview-fullscreen with NO query params — the current page.tsx only looks for ?runId= and, finding none, always falls back to router.replace(routes.runHistory()), silently breaking the feature for every real click.

Fix: rewrite preview-fullscreen/page.tsx to handle BOTH cases, not just one: (a) if a runId query param IS present, keep this spec's new redirect-to-/runs/{id}/preview/full behavior unchanged; (b) if NO runId is present, read sessionStorage's "__app_preview__" payload and render the fullscreen AppBuilderPreview view directly (restoring the pre-015 behavior), only falling back to router.replace(routes.runHistory()) if that sessionStorage key is ALSO missing/unparseable. Do not guess at the restored rendering logic — port it from the git history reference, adapted only as needed for anything that's genuinely changed since (e.g. if AppBuilderPreviewProps' shape has changed, adapt to the current props).`,
    ac: [
      'Clicking "Full Screen" in the live App Builder preview panel (verify via a live Playwright walk: open the app, get to a screen with AppBuilderPreview, trigger handleFullscreen, follow the window.open target) shows the actual preview content again, not a bounce to Run History.',
      'The NEW runId-bearing redirect behavior (this spec\'s own contract) still works unchanged for that case.',
      'No new sessionStorage key or contract invented — reuses the existing "__app_preview__" key/shape exactly as AppBuilderPreview.tsx already writes it.',
    ],
  },
  F5: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [NEXT_CONFIG, ROUTE_MAP_MD],
    file: `${NEXT_CONFIG} or ${ROUTE_MAP_MD} (pick whichever is actually correct)`, traces: 'FR-007 — doc-vs-implementation drift, worth-noting',
    desc: `The /workflow/create?mode= -> /create/{mode} redirect in next.config.ts uses permanent:false (served as a 307), but contracts/route-map.md documents it as "301" (permanent). Decide which is actually correct: a mode-based redirect where the mode segment could theoretically change in the future is arguably better as a temporary (307) redirect so browsers/CDNs don't cache it permanently — if you agree, fix route-map.md's documentation to say "307 (temporary)" instead of "301". If you conclude a permanent redirect is genuinely intended instead, change next.config.ts's permanent:false to permanent:true. State your reasoning explicitly in your summary either way — this is a judgment call, not a mechanical fix.`,
    ac: [
      'next.config.ts\'s redirect config and contracts/route-map.md\'s documented status code now agree with each other.',
      'Your summary states which side you changed and why (temporary-vs-permanent reasoning for a mode-parameterized redirect).',
      'Live-verified via curl -sD - -o /dev/null against the dev server that the actual served status code now matches what route-map.md says.',
    ],
  },
  F6: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/components/workflow/LaunchWizard.tsx'],
    file: 'frontend/src/components/workflow/LaunchWizard.tsx', traces: 'Rule 5 hygiene — real-but-minor',
    desc: `handleLaunch's post-launch navigation (around line 527) and the wizard's back button (around line 548) both call router.push("/dashboard") as a hardcoded string literal instead of using routes.ts. Import routes from "@/lib/routes" and replace both literals with routes.home() (or routes.dashboard() — they return the identical string; prefer routes.home() as that's the more commonly used name elsewhere in the codebase, but either is acceptable).`,
    ac: [
      'Both router.push("/dashboard") call sites now use a routes.ts builder instead of a hand-written literal.',
      'grep -n \'"/dashboard"\' on this file returns nothing after the fix.',
      'npx tsc --noEmit clean for this file; the wizard\'s launch and back-button behavior is otherwise unchanged.',
    ],
  },
  F7: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [VIEW_PAGE],
    file: VIEW_PAGE, traces: 'FR-009 — real-but-minor, UX inconsistency (not a security/leak issue)',
    desc: `T30's /workflows/{id} read-view cold-mount fetch catch block treats ANY fetch failure as not-found (setWorkflowDetail(null); setWorkflowDetailFailed(true) unconditionally for any non-401 error), unlike the narrower 403/404-only pattern already used elsewhere in this same file for the identical class of problem (find the pattern at the run-detail fetch's catch block, and T7/T8's /workflows/{id}/edit fetch's catch block — both explicitly check "err instanceof ApiError && (err.status === 403 || err.status === 404)" before setting their access-denied flag, letting every other error fall through to the pre-existing log-and-continue behavior). Narrow T30's /workflows/{id} read-view catch block to match that same narrower pattern exactly — a transient 5xx or network blip on a legitimately-owned, existing workflow should NOT render the not-found page.`,
    ac: [
      'The /workflows/{id} read-view catch block now only sets the access-denied/not-found state for a 403 or 404 ApiError, matching the exact pattern already used at the other two reference sites in this file.',
      'Any other error (5xx, network failure) falls through to a log-and-continue behavior instead, consistent with the sibling patterns.',
      'A genuinely-403/404 case (e.g. a nonexistent or other-account workflow id) still correctly shows not-found — do not weaken this while narrowing the check; verify both the fixed 5xx case AND the still-correct 403/404 case.',
    ],
  },
  F8: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [ACCOUNT_SETTINGS, ACCOUNT_SETTINGS_TEST],
    file: `${ACCOUNT_SETTINGS} + ${ACCOUNT_SETTINGS_TEST}`, traces: 'FR-015 — real-but-minor, local-dev-only gap',
    desc: `All 3 authedFetch() calls in AccountSettings.tsx's Constitution section (around lines 458, 473, 493) pass a bare relative path "/api/settings/constitution" with no \${ENV.API_URL} prefix. Every other authedFetch() call site in the codebase (RunConnectionProvider.tsx, SkillManager.tsx, PreviewPanel.tsx, PPTPreview.tsx, FilesTab.tsx, CustomTemplateModal.tsx, store/api/prototype.ts) prefixes with \${ENV.API_URL} — authedFetch is a drop-in for global fetch and does NOT auto-prepend the base URL, unlike request()/fetchWithAuth. In local dev this means these 3 calls hit the Next.js dev server's own origin instead of the real backend, so a real 401 can never be observed here and FR-015's session-expiry handling can't actually fire from this screen locally (production is unaffected since ENV.API_URL resolves to same-origin there). Fix: import ENV from "@/lib/env" and add the \${ENV.API_URL} prefix to all 3 calls, matching the established pattern exactly. AccountSettings.render.test.tsx currently has a mock/assertion (around lines 132-144) that pins the bare unprefixed path as the expected value — update that assertion to expect the prefixed URL instead; do not weaken it to a looser match, keep it asserting the exact expected URL string.`,
    ac: [
      'All 3 authedFetch calls in the Constitution section now use `${ENV.API_URL}/api/settings/constitution`, matching every other authedFetch call site\'s convention.',
      'AccountSettings.render.test.tsx is updated to assert the new prefixed URL and still passes (npx vitest run --no-coverage AccountSettings.render.test.tsx).',
      'No other authedFetch call site in this file (if any exist beyond the 3 named) was missed — grep the whole file for authedFetch( to confirm all instances are covered.',
    ],
  },
  F9: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx'],
    file: 'frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx', traces: 'test coverage gap — worth-noting',
    desc: `SavedWorkflowsPage.tsx's Edit action (handleEdit, already correct in source — calls router.push(routes.workflowEdit(row.id))) has no dedicated test asserting this navigation happens. The useRouter() mock in the test file exists only to prevent a render crash, never asserted against for Edit specifically. Add one new test case following the EXACT pattern of the existing Rename/Duplicate/Delete CRUD tests in this same file (open the kebab menu for a row, click "Edit", assert router.push was called with routes.workflowEdit(<that row's id>)).`,
    ac: [
      'A new test case exists that opens the kebab menu, clicks Edit, and asserts router.push was called with the correct routes.workflowEdit(id) URL.',
      'The new test follows the same structure/helpers (e.g. openKebabAndClick) as the existing Rename/Duplicate/Delete tests in the file, not a new ad hoc pattern.',
      'npx vitest run --no-coverage SavedWorkflowsPage.test.tsx passes with the new test included (was 8/8, should now be 9/9).',
    ],
  },
  F10: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/app/admin/page.tsx'],
    file: 'frontend/src/app/admin/page.tsx', traces: 'Rule 5 hygiene — worth-noting',
    desc: `This file has three raw "/login" string literals (around lines 156, 170, 220) instead of using routes.login() — it never imports routes.ts at all. Import routes from "@/lib/routes" and replace all three literals with routes.login().`,
    ac: [
      'All three raw "/login" literals are replaced with routes.login().',
      'grep -n \'"/login"\' on this file returns nothing after the fix.',
      'npx tsc --noEmit clean for this file; the auth-gate/redirect behavior is otherwise unchanged (this file\'s existing 401-vs-not-logged-in distinction, if any, is preserved exactly).',
    ],
  },
  F11: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [ACCOUNT_SETTINGS, DASHBOARD_LAYOUT, VIEW_PAGE],
    file: `${ACCOUNT_SETTINGS} + ${DASHBOARD_LAYOUT} + ${VIEW_PAGE}`, traces: 'SC-001 — CONFIRMED BLOCKER: 3 of 4 /settings/* routes ignore the URL entirely',
    desc: `Cold-opening 3 of the 4 /settings/* routes (ai-model, usage, constitution — only /settings/profile happens to work) always renders the Profile tab, because AccountSettings.tsx hardcodes useState<SettingsSection>("profile") with zero mechanism (no prop, nothing) to receive which tab the URL actually asked for. parseViewPath already correctly distinguishes all four settings-* screens — the information is thrown away between page.tsx's initialMainViewFor() (which currently collapses all four into one generic "settings" MainView with no tab info) and AccountSettings' hardcoded default.

Fix, three parts, in this order: (a) add an optional initialSection?: SettingsSection prop to AccountSettingsProps, and seed the existing useState with useState<SettingsSection>(initialSection ?? "profile") instead of the hardcoded literal; (b) in app/[...view]/page.tsx, thread the actual parsed settings sub-route through — add whatever piece of state is needed (e.g. an initialSettingsSection derived from parsedView, mirroring how other id/tab pieces of state are already seeded from parseViewPath elsewhere in this same file) so the specific settings-* screen the URL named is available; (c) in DashboardLayout.tsx, pass that value down to <AccountSettings initialSection={...} onBack={handleGoHome} /> (currently called with no tab prop at all).`,
    ac: [
      'Pasting each of the 4 /settings/* URLs directly (fresh tab / cold mount) opens on its correspondingly correct tab — verified live via Playwright for all 4, not just the 1 that already worked (check aria-selected on each tab, matching how this defect was originally live-reproduced).',
      'Existing click-driven in-app navigation to any settings tab still works unchanged.',
      'No change to AccountSettings\' behavior when initialSection is omitted (defaults to "profile", same as before) — this is purely additive.',
    ],
  },
  F12: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [NEXT_CONFIG],
    file: NEXT_CONFIG, traces: 'FR-007 — real-but-minor, cosmetic URL leak',
    desc: `The /workflow/create?mode={t} -> /create/{t} redirect rule in next.config.ts's redirects() leaks the original ?mode= query param onto the destination URL (ends up as /create/ppt?mode=ppt instead of a clean /create/ppt). Fix the redirects() rule so the matched query param is CONSUMED (used to build the destination path) rather than also being forwarded onto it — Next.js's redirects() supports named destination params via the "has" array with a query-param match plus a ":mode" placeholder in the destination that consumes it rather than appending it separately. Check Next.js 16's actual redirects() documentation/type definitions (or find another next.config.ts pattern in this repo, if one exists, that already does a clean param-consuming redirect) for the exact correct syntax — do not guess at syntax that might not exist in this Next.js version.

SCOPE NOTE: ?mode= is an intentional convention used ONLY for this one legacy entry point (DashboardLayout.tsx calls routes.workflowCreateLegacy("ppt"/"prototype") for those two modes specifically). The "app" and "user-stories" modes never go through this redirect at all — DashboardLayout.tsx calls routes.createApp()/routes.createUserStories() directly, which already produce clean /create/app and /create/user-stories paths with no query param. Do NOT touch DashboardLayout.tsx or try to unify these two conventions — that's a different, out-of-scope change. Fix only the query-param leak in this one next.config.ts redirect rule.`,
    ac: [
      'A live curl or Playwright navigation to /workflow/create?mode=ppt lands on exactly /create/ppt, with no lingering ?mode=ppt (or any other stray query string) on the final URL.',
      'Repeat-verified for ?mode=prototype too.',
      'The existing behavior (redirect target, which mode values are supported) is otherwise unchanged — this fixes only the leaked query param, not the redirect mapping itself.',
      'DashboardLayout.tsx and the app/user-stories creation paths were not touched.',
    ],
  },
  F13: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [ERROR_TSX, GLOBAL_ERROR_TSX, DASHBOARD_LAYOUT, VIEW_PAGE],
    file: `${ERROR_TSX} + ${GLOBAL_ERROR_TSX} (+ possibly ${DASHBOARD_LAYOUT} or ${VIEW_PAGE} if a real tracking call site is found there)`, traces: 'SC-006 — real-but-minor, investigate-then-fix-or-document',
    desc: `SC-006 (every screen fires a distinct, correct screen label for error/analytics tracking) is currently only observably true for the 2 error boundaries (error.tsx/global-error.tsx already call screenLabel()) — no actual analytics/tracking call fires screenLabel() during a NORMAL (non-error) screen visit, so SC-006 as literally written can't be exercised live outside the error-boundary case. Investigate: grep DashboardLayout.tsx and app/[...view]/page.tsx for any EXISTING analytics/tracking call (search for patterns like "analytics.track", "gtag(", "posthog", or any custom telemetry/logging call that already fires on normal navigation) that screenLabel() should be wired into but currently isn't. If you find one, wire screenLabel() into it (small, targeted change — do not invent a new tracking mechanism). If you find genuinely NONE exist anywhere in the app outside the 2 error boundaries, do not invent a new analytics pipeline (explicitly out of scope, per this spec's own T27/T28 constraint) — instead, state this finding explicitly and clearly in your summary, since that means SC-006 is currently satisfiable only in the error-boundary case, which should be documented as the actual current scope rather than left as an implied broader claim.`,
    ac: [
      'Either a real additional tracking call site was found and wired to screenLabel(), OR you explicitly confirm (with your grep evidence) that none exists anywhere in the app outside the 2 error boundaries and state that clearly.',
      'No new analytics/tracking pipeline was invented.',
      'If a change was made, verify live that the newly-wired call site actually fires with the correct label during normal navigation (not just an error).',
    ],
  },
  F14: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [VIEW_PAGE, RUN_CONNECTION_PROVIDER],
    file: `${VIEW_PAGE} (+ likely ${RUN_CONNECTION_PROVIDER})`, traces: 'SC-002/T11 — CONFIRMED BLOCKER: live-reproduced twice via Playwright',
    desc: `A hard refresh on /runs/{id}/stream that hits a transient 403/404 (e.g. because the run hasn't fully propagated to some backend read-path yet, even though its SSE stream is genuinely live) permanently strands the whole page behind Next's notFound() — there are only 2 setRunAccessDenied call sites in this file (false at one place, true at another), and NOTHING ever resets it back to false or retries the fetch before giving up permanently. This directly contradicts what T11/SC-002 are supposed to guarantee ("hard-refresh mid-run re-attaches, no restart, no blank"). Fix: before permanently setting runAccessDenied=true on a 403/404, add a reconciliation/retry step — check runConnection.liveRunIds (if the run id IS in that live set, the stream is genuinely active despite the REST 403/404, so do NOT set access-denied; instead retry the fetch once after a short delay, or trust the live-stream signal directly) before falling back to the permanent not-found state. Do NOT weaken the real case where a run genuinely IS inaccessible (deleted, wrong account) — that case (where liveRunIds does NOT contain the id, and a retry also 403/404s) must still correctly show not-found (this is FR-009, do not regress it while fixing this).`,
    ac: [
      'Live-reproduce the ORIGINAL bug first (the audit\'s own evidence trail describes the exact repro method — a launched run whose REST fetch 403/404s while its SSE stream is live) to confirm you understand the failure mode, then confirm your fix resolves it: the page no longer permanently shows not-found for this transient case.',
      'The genuine 403/404 case (a truly inaccessible/deleted/other-account run) still correctly shows not-found — verify both cases, not just the fixed one.',
      'No infinite retry loop — the reconciliation/retry is bounded (one retry, or a liveRunIds check, not an unbounded loop).',
    ],
  },
  F16: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['specs/015-frontend-routing/plan.md'],
    file: 'specs/015-frontend-routing/plan.md', traces: 'doc-only — worth-noting',
    desc: `plan.md documents the catch-all segment as the optional form [[...view]] (double brackets) in one or more places, but the actual, correct, shipped implementation is the required form [...view] (single brackets) — this rename was a deliberate bug fix earlier in this spec's history (the optional form conflicts with the root page.tsx as "same specificity" in Next.js). Find every reference to [[...view]] in plan.md and update it to [...view], and if there's surrounding prose that describes WHY the optional form was chosen, correct that reasoning too (briefly) to reflect the required-form decision instead.`,
    ac: [
      'grep -n "\\[\\[\\.\\.\\.view\\]\\]" specs/015-frontend-routing/plan.md returns nothing after the fix.',
      'Any surrounding prose explaining the catch-all choice is now accurate (required, not optional, and why).',
      'No other content in plan.md was changed.',
    ],
  },
  F17: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['specs/015-frontend-routing/data-model.md'],
    file: 'specs/015-frontend-routing/data-model.md', traces: 'doc-only — real-but-minor',
    desc: `data-model.md's /create/{mode} row still describes an earlier, abandoned, buggy router.push-based implementation plan rather than the actual current (fixed) direct-render implementation. Find T4's own resolved findings elsewhere in this same file (search for "TBD"/"resolved" near /create/{mode}) — T4 already traced and documented the ACTUAL correct current behavior with file:line citations. Update the /create/{mode} row itself to match what T4's own resolution already correctly describes, rather than leaving the row showing the old, superseded plan.`,
    ac: [
      'The /create/{mode} row in data-model.md\'s Route -> Screen table now describes the actual current implementation, consistent with T4\'s own resolved-findings text elsewhere in the same file (they should not contradict each other after this fix).',
      'No other row or content in data-model.md was changed.',
    ],
  },
  F20: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: [VIEW_PAGE],
    file: VIEW_PAGE, traces: 'code hygiene — worth-noting',
    desc: `Several console.error calls in this file have internal task-ID tags baked into the shipped message string (e.g. "[T7] ...", "[T24] ..."). These are meaningless to anyone outside this spec's own development history and shouldn't ship in production logs. Find every console.error call with a bracketed task-ID prefix (grep for patterns like "[T" followed by digits) and strip just the task-ID prefix, keeping the descriptive part of the message intact.`,
    ac: [
      'grep -n "console.error" on this file shows no remaining bracketed task-ID prefixes (e.g. no "[T7]", "[T24]", etc.).',
      'The descriptive content of each affected log message is otherwise unchanged — only the task-ID prefix was removed.',
      'npx tsc --noEmit clean for this file.',
    ],
  },

  'V-BLOCKERS': {
    kind: 'validator', agentType: 'qa-engineer', model: 'sonnet', phase: 'Verify',
    deps: ['F2', 'F4', 'F11', 'F14'],
    guards: ['F2', 'F4', 'F11', 'F14'],
    context: 'These 4 findings were CONFIRMED BLOCKERS in the full audit — each was independently live-reproduced before being counted as real (a broken redirect, a broken live feature, a broken settings tab, a permanently-stranded live run). Judge these with the same rigor: actually exercise the live behavior, do not accept a diff read as sufficient. This spec\'s whole history is full of fixes that looked right on paper and were not.',
    criteria: [
      'F2: a live request to /library redirects to /library/agents, and /settings redirects to /settings/profile — actually verified live (curl or Playwright), not inferred from config text.',
      'F4: the live App Builder "Full Screen" feature (triggered via AppBuilderPreview.tsx\'s handleFullscreen) actually shows the preview content again, not a bounce to Run History — actually trigger this flow live. The new runId-bearing redirect case also still works.',
      'F11: all 4 /settings/* routes, pasted cold into a fresh tab, each open on their own correct tab (not all defaulting to Profile) — verified live for all 4, individually.',
      'F14: the transient-403/404-on-a-live-run case no longer permanently strands the page (verify via the same reproduction method the audit used), AND the genuine inaccessible-run case still correctly shows not-found (verify both, not just one).',
    ],
  },

  'V-FINAL': {
    kind: 'validator', agentType: 'qa-engineer', model: 'sonnet', phase: 'Verify',
    deps: ['V-BLOCKERS', 'F1', 'F3', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F12', 'F13', 'F16', 'F17', 'F20'],
    guards: ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12', 'F13', 'F14', 'F16', 'F17', 'F20'],
    context: 'Final sweep across all 17 fixes. V-BLOCKERS already re-verified the 4 blockers in depth — for those, do a lighter spot-check rather than a full re-investigation (trust V-BLOCKERS\' PASS, but do glance at the actual diffs). Focus your own effort on the 13 non-blocker findings, which have not had a dedicated validator yet.',
    criteria: [
      'Every one of the 13 non-blocker findings (F1,F3,F5,F6,F7,F8,F9,F10,F12,F13,F16,F17,F20) is actually fixed per its own AC — spot-check each with real evidence (grep, a targeted test run, or reading the diff for the doc-only ones), not a blanket assumption.',
      'npx tsc --noEmit shows zero NEW errors — only the known pre-existing baseline (list what you see and compare to the ~38-73 count established earlier in this spec).',
      'npx vitest run --no-coverage --maxWorkers=3 (full suite) passes at or above the 1156/1156 baseline established after the FR-015 authedFetch migration — confirm nothing regressed.',
      'frontend/package.json is unchanged (git diff --stat -- frontend/package.json is empty).',
      'No new hand-written route literal was introduced by any of these fixes (grep -rn \'"/runs/\\|"/workflows/\\|"/library/\\|"/create/\\|"/dashboard"\\|"/login"\' frontend/src --include=*.tsx, cross-check every hit is inside routes.ts).',
      'No leftover temporary/scratch test files were left in the working tree by any task (check git status --porcelain for anything that looks like a debug/scratch file, matching this spec\'s prior history of exactly this leftover pattern).',
    ],
  },
}

// ---------------------------------------------------------------------------
// Scheduler — dependency graph + file-collision safety, crash-safe agent()
// wrapping, per-task escalation ladder (3 normal-role + 2 opus-escalated).
// ---------------------------------------------------------------------------

const MAX_PARALLEL = 8
const NORMAL_FIX_ATTEMPTS = 3
const ESCALATED_FIX_ATTEMPTS = 2
const MAX_TASK_FIX_ATTEMPTS = NORMAL_FIX_ATTEMPTS + ESCALATED_FIX_ATTEMPTS

const state = {}
const results = {}
const taskFailCount = {}
for (const id of Object.keys(NODES)) state[id] = 'pending'

async function safeAgent(prompt, opts) {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    log(`agent() threw for ${opts.label || '(unlabeled)'}: ${e?.message || e}`)
    return null
  }
}

async function safeAgentRetrying(prompt, opts, retries = 2) {
  for (let i = 0; i <= retries; i++) {
    const r = await safeAgent(prompt, i === 0 ? opts : { ...opts, label: `${opts.label}-infra-retry${i}` })
    if (r) return r
    if (i < retries) log(`${opts.label}: agent() call itself failed (infra/schema glitch) — retrying (${i + 1}/${retries})`)
  }
  return null
}

function isReady(id) {
  return state[id] === 'pending' && NODES[id].deps.every((d) => state[d] === 'done')
}

function filesInFlight() {
  const set = new Set()
  for (const [id, s] of Object.entries(state)) {
    if (s === 'running') for (const f of NODES[id].files || []) set.add(f)
  }
  return set
}

function collidesWithRunning(id) {
  const inFlight = filesInFlight()
  return (NODES[id].files || []).some((f) => inFlight.has(f))
}

function taskPrompt(id, feedback) {
  const t = NODES[id]
  const feedbackBlock = feedback ? `
==============================================================================
THIS IS A RETRY. A validator already REJECTED this task's work. Do not just repeat the same
approach — read the failure evidence below and fix the SPECIFIC problem it names.

Validator's failure report:
${feedback}
==============================================================================
` : ''
  return `
You are executing task ${id}, part of a fix-pass for confirmed audit findings in the
015-frontend-routing spec. Another agent will validate your work afterward against the
acceptance criteria below — be honest in your self-check, do not claim something passed if
you are unsure.

${REPO_NOTES}
${feedbackBlock}
TASK ${id}
File(s): ${t.file}
Traces to: ${t.traces}

Description:
${t.desc}

Acceptance criteria (self-check each one honestly before returning):
${t.ac.map((a, i) => `${i + 1}. ${a}`).join('\n')}

Do the work now using your file/bash tools. Then return the structured result: taskId="${id}",
status ("done" if you completed the work and believe the AC are met, "blocked" if you could not
proceed — explain why in "blockers"), filesChanged (the real list of paths you touched),
summary (what you actually did, 2-4 sentences), and acSelfCheck (one entry per AC line above,
with met:true/false and a short note).
`.trim()
}

function validatorPrompt(id) {
  const v = NODES[id]
  const reportsText = v.guards
    .map((gid) => {
      const r = results[gid]
      if (!r) return `${gid}: NOT YET RUN`
      if (typeof r === 'string') return `${gid}: ${r}`
      return `${gid} [${r.status || (r.pass ? 'pass' : 'fail')}] — ${r.summary}\n  filesChanged: ${(r.filesChanged || []).join(', ') || '(none reported)'}\n  self-check: ${JSON.stringify(r.acSelfCheck || r.checks)}`
    })
    .join('\n\n')
  return `
You are validator ${id} for the 015-frontend-routing audit-fixes pass. You guard: ${v.guards.join(', ')}.
Your job is to judge, by actually inspecting the code and running commands (including live
exercise where the finding was originally live-reproduced), whether these genuinely satisfy
the criteria below — do NOT just trust the task reports, they are context only.

${REPO_NOTES}

${v.context ? `IMPORTANT CONTEXT: ${v.context}\n` : ''}
TASK/GUARD REPORTS (context, verify independently):
${reportsText}

PASS requires ALL of the following (check each by inspection/exercise, not by reading the diff alone):
${v.criteria.map((c, i) => `${i + 1}. ${c}`).join('\n')}

For each criterion, actually check it. Where a criterion requires exercising live behavior,
do so directly — reason from code only as a last resort, and say so explicitly in "evidence"
when you do.

Return: validatorId="${id}", pass (true only if every criterion passes), checks (one entry per
criterion with result pass/fail and evidence), failedTasks (which of ${v.guards.join(', ')} are
responsible — empty array if pass), summary (2-4 sentences).
`.trim()
}

async function runNode(id) {
  const node = NODES[id]
  state[id] = 'running'
  log(`-> ${id} [${node.agentType}${node.model ? '/' + node.model : ''}] (${node.phase}) starting`)

  if (node.kind === 'task') {
    const report = await safeAgent(taskPrompt(id), {
      label: id, phase: node.phase, agentType: node.agentType, schema: TASK_RESULT_SCHEMA,
    })
    state[id] = report ? 'done' : 'error'
    results[id] = report
    log(`${state[id] === 'done' ? 'OK' : 'FAILED'} ${id}${report ? ` (self-reported: ${report.status})` : ' (no report)'}`)
    return
  }

  let result = await safeAgentRetrying(validatorPrompt(id), {
    label: id, phase: node.phase, agentType: node.agentType, model: node.model, schema: VALIDATOR_RESULT_SCHEMA,
  })

  let round = 0
  while (result && !result.pass && result.failedTasks?.length > 0) {
    const redoable = result.failedTasks.filter(
      (tid) => NODES[tid] && NODES[tid].kind === 'task' && (taskFailCount[tid] || 0) < MAX_TASK_FIX_ATTEMPTS
    )
    const exhausted = result.failedTasks.filter((tid) => (taskFailCount[tid] || 0) >= MAX_TASK_FIX_ATTEMPTS)
    const nonRedoable = result.failedTasks.filter((tid) => !NODES[tid])

    if (exhausted.length) {
      log(`${id}: ${exhausted.join(', ')} already exhausted ${MAX_TASK_FIX_ATTEMPTS}/${MAX_TASK_FIX_ATTEMPTS} attempts — not retrying again.`)
    }
    if (nonRedoable.length) {
      log(`${id}: FAIL names ${nonRedoable.join(', ')}, not a node this script owns — cannot auto-redo, needs orchestrator attention.`)
    }
    if (redoable.length === 0) {
      log(`${id}: nothing left this script can redo — stopping retries, reporting blocked.`)
      break
    }

    round++
    log(`VALIDATOR FAIL ${id} (round ${round}) — redoing ${redoable.join(', ')}`)

    const failedChecks = (result.checks || []).filter((c) => c.result === 'fail')
    const feedbackText = [
      result.summary || '',
      failedChecks.length
        ? `Failed criteria:\n${failedChecks.map((c) => `- ${c.criterion}\n  Evidence: ${c.evidence}`).join('\n')}`
        : '',
    ].filter(Boolean).join('\n\n')

    const redone = await parallel(
      redoable.map((tid) => async () => {
        taskFailCount[tid] = (taskFailCount[tid] || 0) + 1
        const attempt = taskFailCount[tid]
        const escalate = attempt > NORMAL_FIX_ATTEMPTS
        if (escalate) {
          log(`${tid}: attempt ${attempt}/${MAX_TASK_FIX_ATTEMPTS} — escalating to technical-lead/opus.`)
        }
        const r = await safeAgent(taskPrompt(tid, feedbackText), {
          label: `${tid}-retry${attempt}${escalate ? '-opus' : ''}`,
          phase: NODES[tid].phase,
          agentType: escalate ? 'technical-lead' : NODES[tid].agentType,
          model: escalate ? 'opus' : undefined,
          schema: TASK_RESULT_SCHEMA,
        })
        return [tid, r]
      })
    )
    for (const pair of redone.filter(Boolean)) {
      const [tid, r] = pair
      if (r) results[tid] = r
    }

    result = await safeAgentRetrying(validatorPrompt(id), {
      label: `${id}-recheck${round}`, phase: node.phase, agentType: node.agentType, model: node.model, schema: VALIDATOR_RESULT_SCHEMA,
    })
  }

  if (result && result.pass) {
    state[id] = 'done'
    results[id] = result
    log(`VALIDATOR PASS ${id}${round ? ` (after ${round} fix round${round === 1 ? '' : 's'})` : ''} — ${result.summary}`)
  } else {
    state[id] = 'error'
    results[id] = result
    log(`VALIDATOR ${id} still FAILING after ${round} fix round(s) — PHASE BLOCKED. ${result ? result.summary : '(no result)'}`)
  }
}

async function scheduler() {
  const active = new Map()

  while (true) {
    const remaining = Object.keys(NODES).filter((id) => state[id] !== 'done' && state[id] !== 'error')
    if (remaining.length === 0) break

    const anyRunning = active.size > 0
    const anyReady = remaining.some((id) => isReady(id) && !collidesWithRunning(id))
    if (!anyRunning && !anyReady) {
      const stuck = remaining.filter((id) => state[id] === 'pending')
      log(`Nothing left can become ready — ${stuck.length} node(s) permanently blocked: ${stuck.join(', ')}`)
      break
    }

    while (active.size < MAX_PARALLEL) {
      const next = Object.keys(NODES).find((id) => isReady(id) && !collidesWithRunning(id) && !active.has(id))
      if (!next) break
      const p = runNode(next)
        .catch((e) => { log(`runNode(${next}) threw unexpectedly: ${e?.message || e}`); state[next] = 'error' })
        .then(() => { active.delete(next) })
      active.set(next, p)
    }

    if (active.size === 0) break
    await Promise.race(active.values())
  }

  await Promise.all(active.values())
}

phase('Fix')
phase('Verify')

log('Dispatching all 17 fixes in one wave (up to 8 concurrent) — file-collision groups (next.config.ts: F2/F5/F12; [...view]/page.tsx: F7/F11/F13/F14/F20; AccountSettings.tsx: F8/F11; WorkflowHistory.tsx: F1/F4) serialize automatically, everything else runs fully parallel.')

await scheduler()

const done = Object.keys(NODES).filter((id) => state[id] === 'done')
const errored = Object.keys(NODES).filter((id) => state[id] === 'error')

log(`Finished: ${done.length}/${Object.keys(NODES).length} done, ${errored.length} error/blocked.`)
if (errored.length) log(`Blocked nodes: ${errored.join(', ')} — see their reports for what to fix.`)

log('Syncing specs/015-frontend-routing/tasks.md with this fix pass\'s outcome')

const ledgerSync = await safeAgent(`
You are updating specs/015-frontend-routing/tasks.md's "## Final Audit" section (added by the
prior audit workflow) to reflect this fix pass's outcome. Read that section first. For each of
the 17 findings (F1-F14,F16,F17,F20 in this run's numbering, matching the audit's #1-#14,#16,#17,#20),
update its row/entry to show it was fixed and verified (or, if still blocked, exactly why and
what remains). Do not touch task description/AC text elsewhere in the file, and do not touch
anything outside the Final Audit section. If V-BLOCKERS and V-FINAL both passed, add a clear
closing line stating the audit findings are now resolved and the spec can be considered for
re-closure (T29 would need re-running given F11's UI change touches a screen it walks).

Results (id -> done/blocked, or pass/fail for the two validators):
${JSON.stringify(Object.fromEntries(Object.keys(NODES).map((id) => [id, results[id]?.status ?? results[id]?.pass ?? 'no result'])), null, 2)}

Report a brief summary of what you changed.
`.trim(), { label: 'audit-fix-ledger-sync', phase: 'Verify', agentType: 'senior-engineer' })

log(`Ledger sync: ${ledgerSync}`)

return {
  done, errored, results,
  summary: `${done.length}/${Object.keys(NODES).length} nodes done. ` +
    (errored.length ? `Blocked at: ${errored.join(', ')}.` : 'All 17 findings fixed and verified.'),
}

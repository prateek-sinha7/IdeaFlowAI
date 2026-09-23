export const meta = {
  name: '015-frontend-routing',
  description: 'Execute specs/015-frontend-routing/tasks.md from V1 onward (T1-T3 already done): core routing hard gate, 4 parallel lanes with validators, final acceptance, ledger sync.',
  phases: [
    { title: 'V1', detail: 'Validate T1-T3 (routes.ts contract) — already implemented, verify now' },
    { title: 'Core Routing', detail: 'T4-T11 + V2 — catch-all relocation, fetch-by-id (HARD GATE)' },
    { title: 'Lane A', detail: 'T12-T16 + V3 — shareable views' },
    { title: 'Lane B', detail: 'T17-T21 + V4 — edges & boundaries' },
    { title: 'Lane C', detail: 'T22-T24 + V5 — access & session' },
    { title: 'Lane D', detail: 'T25-T28 + V6 — completion & observability' },
    { title: 'Acceptance', detail: 'V7 — full FR/SC sweep + ledger close-out' },
  ],
}

const REPO_NOTES = `
Repo: VELOCITY-AI frontend, Next.js 16 App Router, React 19. Run all commands from frontend/.
Verify with: npx tsc --noEmit (type check) and npm test -- <file> (vitest, scoped).
Full context: specs/015-frontend-routing/{spec.md,plan.md,data-model.md,contracts/route-map.md,tasks.md}.

STANDING RULES for every task:
1. Change only what your task names. Do not tidy adjacent code, comments, or imports you did not orphan.
2. Never run a state-changing git command (no stash/checkout--/reset/clean/restore). Read-only git is fine.
3. Do not commit. Leave changes in the working tree.
4. If your anchor text/file is not found verbatim, do NOT guess — return status "blocked" with why.
5. Every path string goes through frontend/src/lib/routes.ts (already built by T1/T2). A
   hand-written route literal anywhere else is a defect.
6. Do NOT add a routing library (no react-router, no nuqs, no new package.json dependency).
7. Do NOT edit specs/015-frontend-routing/tasks.md — the ledger-sync step owns that file.
   Do not touch files outside the ones your task names.
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

const TASKS = {
  T4: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'specs/015-frontend-routing/data-model.md (docs only — NO code changes)',
    traces: 'plan.md Phase 1 task 5',
    desc: 'Trace the real MainView mapping. data-model.md\'s Route -> Screen table has two TBD rows (/workflows/{id} read view, /workflows/{id}/run) and one uncertain row (/create/{mode}). Resolve all three by reading handleSelectFeature and handleLaunchSaved in frontend/src/components/layout/DashboardLayout.tsx, and SavedWorkflowsPage\'s open/launch props.',
    ac: [
      'All three rows state a real MainView value from the union at DashboardLayout.tsx:267, each with a file:line citation.',
      'If a row genuinely has no existing view, say so explicitly rather than inventing one.',
      'Zero files outside data-model.md are modified.',
    ],
  },
  T5: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'frontend/src/app/dashboard/page.tsx -> frontend/src/app/[...view]/page.tsx',
    traces: 'FR-001',
    desc: 'Relocate (move, do not duplicate) frontend/src/app/dashboard/page.tsx to frontend/src/app/[...view]/page.tsx — a REQUIRED catch-all (single brackets, [...view]), NOT an optional catch-all ([[...view]] with double brackets). This is deliberate: frontend/src/app/page.tsx already exists as the literal root page, and Next.js 16 rejects an optional catch-all coexisting with a literal root page as "same specificity" (a real build error, already hit and fixed once). A required catch-all does not match the empty/zero-segment path, so it does not conflict with root page.tsx. If you find an existing frontend/src/app/[[...view]]/ directory (double brackets) on disk, that is the bug — rename it to frontend/src/app/[...view]/ (single brackets) as part of this task; do not leave both existing. parseViewPath already treats undefined/["dashboard"] as home, so no parsing logic changes are needed for this rename. Make NO other behavior changes in this task beyond the relocation/rename.',
    ac: [
      'frontend/src/app/[...view]/ exists (single brackets, required catch-all) and frontend/src/app/[[...view]]/ (double brackets) does NOT exist — both cannot coexist.',
      '/dashboard still renders exactly as before (now params.view === ["dashboard"]).',
      'The moved file\'s contents are otherwise unchanged — no refactor, no behavior edits.',
      'frontend/src/app/dashboard/ no longer exists.',
      'npx tsc --noEmit clean; app boots on npm run dev.',
    ],
  },
  T6: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'frontend/src/app/[...view]/page.tsx (single brackets — see T5)',
    traces: 'FR-001, FR-003',
    desc: 'Call parseViewPath(params.view) (from frontend/src/lib/routes.ts) and seed the existing useState<MainView> initializer (currently always "home") plus any ids the descriptor carries. ADDITIONALLY (per data-model.md, T4\'s traced findings): for /create/ppt, /create/prototype, and the ppt/prototype branch of /workflows/{id}/run — these do NOT map to any MainView at all. On a cold mount of these paths, do NOT set a MainView; instead router.push to /workflow/create?mode=ppt or ?mode=prototype (mirroring the existing click-driven handleSelectFeature/handleLaunchSaved behavior in DashboardLayout.tsx), exactly as a click-driven open of these already does today.',
    ac: [
      'Opening each non-id route (/dashboard, /create, /runs, /workflows, /library/agents, /settings/profile, /analytics) directly lands on that screen, not home.',
      'Cold-opening /create/ppt and /create/prototype router.push to /workflow/create?mode=ppt / ?mode=prototype respectively — not falling back to home or any DashboardLayout MainView.',
      '{ screen: "unknown" } falls through to Next\'s not-found, not a blank render.',
      'Existing click-driven navigation is untouched and still works.',
    ],
  },
  T7: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'frontend/src/app/[...view]/page.tsx (single brackets — see T5)',
    traces: 'FR-003, SC-001',
    desc: '"execution" MainView covers both the live stream and every reopened run-detail tab, distinguished by fetched state — setting mainView alone renders the right shell with NO data. On a cold mount of /runs/{id}* (no prior in-memory pipelineState), fetch via getRunSummary (frontend/src/lib/api.ts:528) and populate the same state a click-driven open sets.',
    ac: [
      'Cold-opening /runs/{id} shows that run\'s real content — same as clicking through from /runs.',
      '/runs/{id}/steps, /files, /audit each open on the correct tab.',
      'Already-in-memory runs are NOT refetched (a client-side nav from /runs must not double-fetch).',
      'A fetch failure does not crash — leave a clearly-marked stub branch for T24 to fill (do not implement the full not-found UI here).',
    ],
  },
  T8: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'frontend/src/app/[...view]/page.tsx (single brackets — see T5)',
    traces: 'FR-011',
    desc: 'SEQUENTIAL AFTER T7 — same file. Same shape as T7 for "composer": /workflows/{id}/edit must populate the savedComposition-equivalent state (initialManifestSteps, initialSelections, initialName, initialUserWorkflowId, initialRunConfig — see DashboardLayout.tsx:2486+) by fetching the saved workflow by id.',
    ac: [
      'Cold-opening /workflows/{id}/edit loads the Composer pre-filled with real steps, name, and selections.',
      '/workflows/new still opens a blank Composer (same MainView, no fetch).',
      'initialManifestSteps takes precedence over initialAgentIds (see DashboardLayout.tsx:2513 comment for why).',
    ],
  },
  T9: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'frontend/src/components/layout/DashboardLayout.tsx',
    traces: 'FR-001, FR-004',
    desc: 'Every setMainView(...) call site additionally pushes the matching path via routes.* (from frontend/src/lib/routes.ts). Existing state-passing stays exactly as-is — this is purely additive.',
    ac: [
      'Every setMainView call site pushes a URL — grep-verify no setMainView( without an adjacent push.',
      'Path strings come from routes.* — zero hand-written literals.',
      'No setMainView call is removed or reordered; prop-passing behavior is byte-identical.',
      'Back/forward moves between visited screens correctly.',
    ],
  },
  T10: {
    agentType: 'junior-engineer', phase: 'Core Routing',
    file: 'frontend/src/app/page.tsx',
    traces: 'FR-002',
    desc: 'Check auth before redirecting: authenticated -> routes.home(), unauthenticated -> routes.login(). Today it always sends to /login. Follow the existing token-check pattern (getToken() then router.replace, as frontend/src/app/admin/page.tsx:154-162 does).',
    ac: [
      'Logged in, / -> /dashboard. Logged out, / -> /login.',
      'No flash of the wrong screen before the redirect resolves.',
    ],
  },
  T11: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'the run-stream hook/view (identify precisely — likely frontend/src/hooks/useRunStream.ts / useRunConnection)',
    traces: 'FR-003, SC-002',
    desc: 'A hard refresh on /runs/{id}/stream must re-open the live connection for runId from the URL, not only on client-side navigation. Confirm the connection effect\'s dependency array fires on a cold mount, not just a state transition.',
    ac: [
      'Launch a run, hard-refresh mid-run: the stream re-attaches and keeps updating. No restart, no blank.',
      'A terminal-state run opened at /stream shows the terminal state in place, not a dead connection.',
      'No duplicate connection when navigating client-side to a run already streaming.',
    ],
  },
  T30: {
    agentType: 'senior-engineer', phase: 'Core Routing',
    file: 'frontend/src/app/[...view]/page.tsx (single brackets — see T5), + a new minimal read-only view component if one does not already fit',
    traces: 'spec.md screen inventory (saved workflow read view), T4\'s finding in data-model.md',
    desc: 'T4 traced this and found /workflows/{id} (the saved-workflow READ view, distinct from /workflows/{id}/edit) has NO existing MainView to point at — SavedWorkflowsPage.tsx only exposes onLaunchSaved/onCreateNew, no per-row open/read-only affordance. This screen genuinely does not exist in the codebase yet and must be built, not mapped. On cold mount of /workflows/{id}, fetch the saved workflow by id (same userWorkflowsApi.get(id) call T8 already uses) and render a minimal read-only summary: name, description, and its step/agent list (reuse an existing display component if one already renders this shape read-only — e.g. something inside ComposerPage or SavedWorkflowsPage\'s own card — rather than building new UI from scratch if avoidable). Include "Edit" and "Run" actions linking to routes.workflowEdit(id) and routes.workflowRun(id). Keep this minimal — a read summary + two links, not a redesign.',
    ac: [
      'Cold-opening /workflows/{id} shows that specific workflow\'s real name, description, and step/agent list — not the saved-workflows list, not a blank page, not a redirect to /edit.',
      '"Edit" and "Run" actions are present and navigate to /workflows/{id}/edit and /workflows/{id}/run respectively.',
      'An unknown/nonexistent workflow id falls through to not-found (or a clear stub if not-found.tsx is not built yet), not a crash.',
      'No new component library or heavy new UI was introduced — this reuses existing display primitives (Card/Button/etc.) matching the app\'s existing idiom.',
    ],
  },
  T12: {
    agentType: 'junior-engineer', phase: 'Lane A',
    file: 'run-history component (frontend/src/components/history/)',
    traces: 'FR-005',
    desc: 'Encode ?type=&sort= on the run-history screen. Read filter/sort state from useSearchParams on mount and write back on change via routes.* + router.replace.',
    ac: [
      'router.replace, not push — an in-screen filter change must not add a back-history entry.',
      'Mount reads the URL; a URL with no params yields today\'s default view unchanged.',
      'Params come from routes.* builders, not hand-built strings.',
      'Omitted/empty params do not appear as bare ? or & in the URL.',
    ],
  },
  T13: {
    agentType: 'junior-engineer', phase: 'Lane A',
    file: 'frontend/src/components/library/LibraryPage.tsx',
    traces: 'FR-005',
    desc: 'Encode ?category= on frontend/src/components/library/LibraryPage.tsx. Same shape as T12.',
    ac: [
      'router.replace, not push.',
      'Mount reads the URL; no-params URL yields default view unchanged.',
      'Params come from routes.* builders.',
      'Omitted/empty params do not appear as bare ? or &.',
    ],
  },
  T14: {
    agentType: 'junior-engineer', phase: 'Lane A',
    file: 'frontend/src/components/analytics/AnalyticsPage.tsx',
    traces: 'FR-005',
    desc: 'Encode ?range=&pipeline= on frontend/src/components/analytics/AnalyticsPage.tsx. Same shape as T12.',
    ac: [
      'router.replace, not push.',
      'Mount reads the URL; no-params URL yields default view unchanged.',
      'Params come from routes.* builders.',
      'Omitted/empty params do not appear as bare ? or &.',
    ],
  },
  T15: {
    agentType: 'senior-engineer', phase: 'Lane A',
    file: 'frontend/src/components/library/LibraryPage.tsx (+ its item-detail component)',
    traces: 'FR-006',
    desc: '/library/{type}/{slug} renders the EXISTING modal content component full-page. No content redesign.',
    ac: [
      'All three types (agents, skills, hooks) open by slug directly in a fresh tab.',
      'The detail component itself is reused, not forked into a second copy.',
      'An unknown slug renders not-found (T19\'s page — if not built yet, leave a TODO comment pointing at it), not a blank panel.',
    ],
  },
  T16: {
    agentType: 'junior-engineer', phase: 'Lane A',
    file: 'frontend/src/components/library/LibraryPage.tsx',
    traces: 'FR-006',
    desc: 'SEQUENTIAL AFTER T15 — same file. Clicking an item still opens the existing modal (fast, no navigation) AND pushes routes.libraryItem(type, slug), so back/forward and link-sharing both work.',
    ac: [
      'Modal still opens instantly on click — no full navigation, no visible reload.',
      'URL updates to the item path; browser back closes the modal and returns to the list.',
      'The already-working modal-opens-on-tap behavior is not regressed.',
    ],
  },
  T17: {
    agentType: 'junior-engineer', phase: 'Lane B',
    file: 'frontend/next.config.js',
    traces: 'FR-007, SC-004',
    desc: 'Add the /workflow/create?mode={t} -> /create/{t} redirect via Next.js redirects() config (static case).',
    ac: [
      'Both /workflow/create?mode=ppt and ?mode=prototype redirect correctly to /create/ppt and /create/prototype.',
      'Neither 404s.',
    ],
  },
  T18: {
    agentType: 'junior-engineer', phase: 'Lane B',
    file: 'frontend/src/app/preview-fullscreen/page.tsx',
    traces: 'FR-007, SC-004',
    desc: 'Redirect /preview-fullscreen -> /runs/{id}/preview/full. Needs the run id — confirm its current query shape first; if the id is only in client state and cannot be resolved, redirect to /runs instead of guessing, and document that fallback in the file.',
    ac: [
      '/preview-fullscreen redirects; never 404s.',
      'If a run id cannot be resolved, falls back to /runs (documented in-file), not an error.',
    ],
  },
  T19: {
    agentType: 'junior-engineer', phase: 'Lane B',
    file: 'frontend/src/app/not-found.tsx (new)',
    traces: 'FR-008',
    desc: 'Create a branded not-found page using existing design tokens and Button/Card primitives — match frontend/src/app/login/page.tsx\'s idiom, do not invent a new visual language. Offer a path back into the app.',
    ac: [
      'Renders correctly in light and dark mode.',
      'Offers a clear path back into the app (e.g. a link to /dashboard or /login).',
      'Visually distinct from the error page (T20).',
    ],
  },
  T20: {
    agentType: 'junior-engineer', phase: 'Lane B',
    file: 'frontend/src/app/error.tsx and frontend/src/app/global-error.tsx (new)',
    traces: 'FR-013',
    desc: 'SEQUENTIAL AFTER T19 for design consistency. Create branded error boundary pages distinct from the not-found state.',
    ac: [
      'Visually distinct from not-found (T19), same design language.',
      'Renders correctly in light and dark mode.',
      'Offers a path back into the app.',
    ],
  },
  T21: {
    agentType: 'junior-engineer', phase: 'Lane B',
    file: 'frontend/src/app/test-preview/ (delete)',
    traces: 'FR-014',
    desc: 'Delete frontend/src/app/test-preview/ entirely — a 2,443-line mock hotel-app fixture. Not merely unlink it from navigation; remove the directory.',
    ac: [
      'grep -rn "test-preview" frontend/src returns nothing after this task.',
      'No other route regresses from the deletion (confirm nothing else imports from this directory first).',
    ],
  },
  T22: {
    agentType: 'senior-engineer', phase: 'Lane C',
    file: 'frontend/src/lib/api.ts',
    traces: 'FR-015',
    desc: 'Centralize the "session expired" redirect so it fires from any screen. ApiError already exists (api.ts:71) and carries status. On a 401 from the shared request path, redirect to routes.login({ expired: true }) and clear the stored token.',
    ac: [
      'Fires from ANY screen — one handler in the shared request path, not a per-screen duplicate.',
      'The stored token is cleared, so the user is genuinely logged out.',
      'A 401 from the login request itself does NOT redirect-loop — bad credentials must still show login/page.tsx\'s existing inline error (lines 26-28).',
    ],
  },
  T23: {
    agentType: 'junior-engineer', phase: 'Lane C',
    file: 'frontend/src/app/login/page.tsx',
    traces: 'FR-015',
    desc: 'Read ?expired=1 and show a visible "your session expired" message above the form, using the existing error-display element rather than a new component.',
    ac: [
      'Message shows only with the param present; a normal /login is unchanged.',
      'Uses the existing inline-error styling; no new component created.',
    ],
  },
  T24: {
    agentType: 'senior-engineer', phase: 'Lane C',
    file: 'frontend/src/app/[...view]/page.tsx (single brackets — see T5)',
    traces: 'FR-009',
    desc: 'Complete T7/T8\'s stubbed failure branch: a 403/404 on an id-bearing fetch renders not-found (frontend/src/app/not-found.tsx) — never another user\'s data, never a raw crash.',
    ac: [
      'A run id belonging to another account shows not-found/no-access, not that run\'s data.',
      'A deleted run id shows the same, not a crash.',
      '401 still routes to T22\'s login redirect — the two paths (401 vs 403/404) must not collide.',
    ],
  },
  T25: {
    agentType: 'senior-engineer', phase: 'Lane D',
    file: 'run-launch call sites (onStartPipeline seams in DashboardLayout.tsx, ComposerPage onRun, creation flows)',
    traces: 'FR-010',
    desc: 'On run creation, navigate to routes.runStream(newId) immediately at every launch path — composer run-once, saved-workflow launch, each creation flow, and revision launches.',
    ac: [
      'Every launch path lands on /runs/{newId}/stream — enumerate which you covered in your summary.',
      'The existing auto-transition to mainView="execution" is not duplicated or fought — the push replaces it, does not stack on it.',
      'Revision launches also land correctly.',
    ],
  },
  T26: {
    agentType: 'junior-engineer', phase: 'Lane D',
    file: 'frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx',
    traces: 'FR-011',
    desc: 'Add an "Edit" action per saved workflow that navigates to routes.workflowEdit(id). Match existing action styling on that card (delete confirm already lives there, SavedWorkflowsPage.tsx:394-425).',
    ac: [
      'Edit is reachable from the saved-workflows list without typing a URL.',
      'Matches existing action styling.',
      'Existing launch and delete actions are unchanged.',
    ],
  },
  T27: {
    agentType: 'junior-engineer', phase: 'Lane D',
    file: 'frontend/src/lib/routes.ts',
    traces: 'FR-012, SC-006',
    desc: 'Add screenLabel(parsed: ParsedView): string returning a stable, distinct name per screen. Reuse the mainView/screen vocabulary already in data-model.md — no second taxonomy.',
    ac: [
      'Labels are distinct per screen and stable (not derived from a mutable UI string).',
      'Reuses existing vocabulary, not a new taxonomy.',
    ],
  },
  T28: {
    agentType: 'senior-engineer', phase: 'Lane D',
    file: 'existing error/analytics call sites (identify during this task)',
    traces: 'FR-012, SC-006',
    desc: 'SEQUENTIAL AFTER T27. Thread screenLabel() into whatever tracking already fires. Does NOT stand up Sentry or a new analytics pipeline. If no tracking call site exists yet, say so explicitly rather than creating one.',
    ac: [
      'No new tracking dependency added (package.json unchanged).',
      'If no existing call site was found, this is stated explicitly in the summary, not silently skipped.',
    ],
  },
}

const VALIDATORS = {
  V1: {
    phase: 'V1', hardGate: false,
    guards: ['T1', 'T2', 'T3'],
    context: 'T1/T2/T3 were already completed and self-reported in a prior interactive session: T1 built frontend/src/lib/routes.ts with 36 route builders (34 contract routes + login/register) using a shared URLSearchParams helper; T2 added parseViewPath + a ParsedView discriminated union covering all 36 routes with undefined/["dashboard"] resolving home and unknown paths returning {screen:"unknown"}; T3 added frontend/src/lib/routes.test.ts with 55 passing round-trip tests. Both files exist on disk right now — verify them for real, do not just trust this summary.',
    criteria: [
      'Every route in contracts/route-map.md has a builder AND a parse case AND a test case — list any missing.',
      'No route exists in routes.ts that is absent from the contract (invented routes are a FAIL).',
      'parseViewPath is a true inverse — spot-check 5 routes by hand-tracing, including one with an id and one with a sub-tab.',
      'npx tsc --noEmit and npm test -- routes.test.ts both clean.',
      'frontend/package.json is unchanged (no routing library added).',
    ],
  },
  V2: {
    phase: 'Core Routing', hardGate: true,
    guards: ['T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T30'],
    criteria: [
      'All 34 routes open cold in a fresh tab and render the correct screen WITH DATA, not an empty shell. Id-bearing routes specifically: verify content, not just layout. This explicitly includes /create/ppt, /create/prototype (must router.push to /workflow/create?mode=...), /workflows/{id} (must show T30\'s new read view, not the list), and /workflows/{id}/run.',
      'data-model.md has zero remaining TBD rows, each with a file:line citation.',
      'grep -c "setMainView(" DashboardLayout.tsx — every occurrence has an adjacent routes.* push. Report the count and any misses.',
      'No hand-written route literal outside routes.ts.',
      'Hard-refresh on /runs/{id}/stream mid-run re-attaches (SC-002) — must be actually exercised.',
      'Back/forward across 10 navigations is correct (SC-003).',
      'npx tsc --noEmit clean; frontend/src/app/dashboard/ is gone; no second state tree was created.',
    ],
  },
  V3: {
    phase: 'Lane A', hardGate: false,
    guards: ['T12', 'T13', 'T14', 'T15', 'T16'],
    criteria: [
      'For each of the three list screens: set a filter, copy the URL, open in a fresh session -> identical filtered view (SC-005). Test all three.',
      'Filter changes use replace, not push — confirm by changing a filter 5x then pressing back once.',
      'All three library types open by direct slug URL.',
      'Modal-open still pushes a URL and back closes it.',
      'npx tsc --noEmit clean; no route literals introduced outside routes.ts.',
    ],
  },
  V4: {
    phase: 'Lane B', hardGate: false,
    guards: ['T17', 'T18', 'T19', 'T20', 'T21'],
    criteria: [
      'Every retired path redirects, verified individually (SC-004).',
      'A nonsense URL shows the branded not-found (SC-008 first half).',
      '/test-preview gives the same not-found as any unknown URL; grep -rn "test-preview" frontend/src is empty.',
      'A deliberate throw shows the branded error page, not the framework default (SC-007) — trigger it, confirm any temporary throw was reverted.',
      'Both boundary pages render correctly in dark mode.',
    ],
  },
  V5: {
    phase: 'Lane C', hardGate: false,
    guards: ['T22', 'T23', 'T24'],
    criteria: [
      'Expired/cleared session from at least one screen per area in spec.md §5 -> /login?expired=1 with a visible message (SC-009). Six checks minimum, listed individually.',
      'Bad credentials on /login still show the inline error and do NOT redirect-loop.',
      'A cross-account run id returns not-found and no run data appears in the response render or console.',
      'A 401 and a 403 take different paths (login vs not-found) — confirm both.',
      'The token is actually cleared on expiry (check storage), not just redirected past.',
    ],
  },
  V6: {
    phase: 'Lane D', hardGate: false,
    guards: ['T25', 'T26', 'T27', 'T28'],
    criteria: [
      'Every launch path lands on /runs/{newId}/stream — enumerate the paths found and confirm each.',
      'A saved workflow opens -> edits -> re-saves successfully, entirely through the UI.',
      'Screen labels are distinct across all 34 screens — no two screens share a label (SC-006).',
      'No new tracking dependency was added (package.json unchanged).',
    ],
  },
  V7: {
    phase: 'Acceptance', hardGate: true,
    guards: ['V3', 'V4', 'V5', 'V6'],
    criteria: [
      'Each of FR-001 through FR-015 demonstrably satisfied — one line of evidence each, no blanket claims.',
      'Each of SC-001 through SC-009 verified — SC-001 means all 34 routes actually opened, not sampled.',
      'frontend/package.json unchanged across the entire spec.',
      'npx tsc --noEmit clean; existing frontend test suite is at or above its pre-spec baseline (record both numbers).',
      'contracts/route-map.md still matches the implementation exactly; any drift means the contract or the code is wrong — say which.',
    ],
  },
}

function taskPrompt(id, feedback) {
  const t = TASKS[id]
  const feedbackBlock = feedback ? `
==============================================================================
THIS IS A RETRY. You (or another agent on this same task) already attempted ${id} and a
validator REJECTED it. Do not just repeat the same approach — read the failure evidence below,
figure out specifically what is still wrong, and fix THAT. If your own prior work is already
correct and the failure is actually caused by a different task, say so explicitly in your report
rather than making unrelated changes.

Validator's failure report on this group:
${feedback}
==============================================================================
` : ''
  return `
You are executing task ${id} from specs/015-frontend-routing/tasks.md, as one step of an
automated workflow. Another agent will validate your work afterward against the acceptance
criteria below — be honest in your self-check, do not claim something passed if you are unsure.

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

function validatorPrompt(id, taskReports) {
  const v = VALIDATORS[id]
  const reportsText = v.guards
    .map((tid) => {
      const r = taskReports[tid]
      if (!r) return `${tid}: NOT YET RUN`
      if (typeof r === 'string') return `${tid}: ${r}`
      return `${tid} [${r.status}] — ${r.summary}\n  filesChanged: ${(r.filesChanged || []).join(', ') || '(none reported)'}\n  self-check: ${JSON.stringify(r.acSelfCheck)}`
    })
    .join('\n\n')
  return `
You are validator ${id} for specs/015-frontend-routing. You guard: ${v.guards.join(', ')}.
Your job is to judge, by actually inspecting the code and running commands, whether these
genuinely satisfy the criteria below — do NOT just trust the task reports, they are context only.

${REPO_NOTES}

${v.context ? `IMPORTANT CONTEXT: ${v.context}\n` : ''}
TASK/GUARD REPORTS (context, verify independently):
${reportsText}

PASS requires ALL of the following (check each by inspection/exercise, not by reading the diff alone):
${v.criteria.map((c, i) => `${i + 1}. ${c}`).join('\n')}

For each criterion, actually check it — read the relevant files, run npx tsc --noEmit / npm test
as needed, and where a criterion requires exercising live behavior (opening a URL, refreshing,
back/forward) that you cannot directly run, reason carefully from the code and say explicitly in
"evidence" that this is inferred from code reading rather than observed directly.

Return: validatorId="${id}", pass (true only if every criterion passes), checks (one entry per
criterion with result pass/fail and evidence), failedTasks (which of ${v.guards.join(', ')} are
responsible — empty array if pass), summary (2-4 sentences).
`.trim()
}

async function runTask(id, feedback) {
  const t = TASKS[id]
  return agent(taskPrompt(id, feedback), {
    label: feedback ? `${id}-retry` : id,
    phase: t.phase,
    agentType: t.agentType,
    schema: TASK_RESULT_SCHEMA,
  })
}

async function runValidator(id, taskReports) {
  const v = VALIDATORS[id]
  return agent(validatorPrompt(id, taskReports), {
    label: id,
    phase: v.phase,
    agentType: 'qa-engineer',
    model: 'sonnet',
    schema: VALIDATOR_RESULT_SCHEMA,
  })
}

async function guardedGroup(groupLabel, validatorId, runGroupFn, maxRetries = 10) {
  let reports = await runGroupFn()
  let attempt = 0
  let result = await runValidator(validatorId, reports)
  let prevFailedKey = null

  while (!result.pass && attempt < maxRetries && result.failedTasks.length > 0) {
    attempt++
    log(`${groupLabel}: ${validatorId} FAILED (attempt ${attempt}/${maxRetries}) — redoing ${result.failedTasks.join(', ')}`)

    // Feed the validator's actual failure evidence back to the SAME task(s) that owned the
    // failing work, so the redo fixes the real problem instead of blindly repeating itself.
    const failedChecks = (result.checks || []).filter((c) => c.result === 'fail')
    const feedbackText = [
      result.summary || '',
      failedChecks.length
        ? `Failed criteria:\n${failedChecks.map((c) => `- ${c.criterion}\n  Evidence: ${c.evidence}`).join('\n')}`
        : '',
    ].filter(Boolean).join('\n\n')

    const redoable = result.failedTasks.filter((id) => TASKS[id])
    const redone = await parallel(
      redoable.map((id) => async () => {
        const r = await runTask(id, feedbackText)
        return [id, r]
      })
    )
    for (const pair of redone.filter(Boolean)) {
      const [id, r] = pair
      reports[id] = r
    }
    result = await runValidator(validatorId, reports)

    // If the exact same set of tasks fails on two consecutive attempts with the validator
    // reporting the identical summary, further identical retries are unlikely to help —
    // still respect maxRetries, but this makes stalling visible in the log rather than silent.
    const failedKey = `${result.failedTasks.slice().sort().join(',')}::${result.summary}`
    if (!result.pass && failedKey === prevFailedKey) {
      log(`${groupLabel}: ${validatorId} attempt ${attempt} made no visible progress vs. the previous attempt — continuing to retry (feedback loop may need a different angle).`)
    }
    prevFailedKey = failedKey
  }

  if (!result.pass) {
    log(`${groupLabel}: ${validatorId} still FAILING after ${attempt} retries — ${result.summary}`)
  } else {
    log(`${groupLabel}: ${validatorId} PASS after ${attempt} retr${attempt === 1 ? 'y' : 'ies'} — ${result.summary}`)
  }

  return { reports, validator: result }
}

// ── Main flow — T1/T2/T3 already done (verified on disk), start at V1 ─────

phase('V1')
log('T1/T2/T3 already complete (prior session) — verifying with V1 before Core Routing')

const t1t2t3Reports = {
  T1: 'routes.ts: 36 builders (34 contract routes + login/register), query params via shared URLSearchParams helper, tsc clean (self-reported, prior session).',
  T2: 'parseViewPath + ParsedView union covering all 36 routes, undefined/["dashboard"] -> home, unknown -> {screen:"unknown"} never throws, tsc clean (self-reported, prior session).',
  T3: 'routes.test.ts: 55 passing round-trip tests, one per route plus explicit undefined/["dashboard"]/unknown/all-params-omitted cases (self-reported, prior session).',
}
const v1 = await runValidator('V1', t1t2t3Reports)
log(v1.pass ? `V1 PASS — ${v1.summary}` : `V1 FAIL — ${v1.summary}`)

if (!v1.pass) {
  log('V1 did not pass. The route contract (T1-T3) is not trustworthy enough to build Core Routing on top of. Halting — needs human/senior-engineer attention on the specific failures listed above before this workflow should resume.')
  return { halted: 'V1', v1 }
}

phase('Core Routing')
log('Phase 2/7: catch-all relocation + fetch-by-id (T4-T11) — the load-bearing phase')

const coreRouting = await guardedGroup('Core Routing', 'V2', async () => {
  const t4 = await runTask('T4')
  const t5 = await runTask('T5')
  const t6 = await runTask('T6')

  const [chain, t9, t10] = await parallel([
    async () => {
      const t7 = await runTask('T7')
      const t8 = await runTask('T8')
      const t11 = await runTask('T11')
      const t30 = await runTask('T30')
      return { T7: t7, T8: t8, T11: t11, T30: t30 }
    },
    () => runTask('T9'),
    () => runTask('T10'),
  ])

  return {
    T4: t4, T5: t5, T6: t6,
    T7: chain?.T7, T8: chain?.T8, T11: chain?.T11, T30: chain?.T30,
    T9: t9, T10: t10,
  }
})

if (!coreRouting.validator.pass) {
  log('V2 is a HARD GATE. It did not pass after retries. Halting — Lanes A-D all assume this phase is sound.')
  return { halted: 'V2', v1, coreRouting }
}

log('V2 passed — fanning out into 4 parallel lanes')

const [laneA, laneB, laneC, laneD] = await parallel([
  () => {
    phase('Lane A')
    return guardedGroup('Lane A', 'V3', async () => {
      const [t12, t13, t14] = await parallel([
        () => runTask('T12'),
        () => runTask('T13'),
        () => runTask('T14'),
      ])
      const t15 = await runTask('T15')
      const t16 = await runTask('T16')
      return { T12: t12, T13: t13, T14: t14, T15: t15, T16: t16 }
    })
  },
  () => {
    phase('Lane B')
    return guardedGroup('Lane B', 'V4', async () => {
      const [t17, t18] = await parallel([
        () => runTask('T17'),
        () => runTask('T18'),
      ])
      const t19 = await runTask('T19')
      const t20 = await runTask('T20')
      const t21 = await runTask('T21')
      return { T17: t17, T18: t18, T19: t19, T20: t20, T21: t21 }
    })
  },
  () => {
    phase('Lane C')
    return guardedGroup('Lane C', 'V5', async () => {
      const t22 = await runTask('T22')
      const t23 = await runTask('T23')
      const t24 = await runTask('T24')
      return { T22: t22, T23: t23, T24: t24 }
    })
  },
  () => {
    phase('Lane D')
    return guardedGroup('Lane D', 'V6', async () => {
      const t25 = await runTask('T25')
      const t26 = await runTask('T26')
      const t27 = await runTask('T27')
      const t28 = await runTask('T28')
      return { T25: t25, T26: t26, T27: t27, T28: t28 }
    })
  },
])

phase('Acceptance')
log('All 4 lanes complete — running final acceptance sweep (V7)')

const allTaskReports = {
  ...t1t2t3Reports,
  ...coreRouting.reports,
  ...(laneA?.reports ?? {}),
  ...(laneB?.reports ?? {}),
  ...(laneC?.reports ?? {}),
  ...(laneD?.reports ?? {}),
}

const laneValidators = {
  V3: laneA?.validator, V4: laneB?.validator, V5: laneC?.validator, V6: laneD?.validator,
}

const v7 = await runValidator('V7', allTaskReports)

const unresolvedLanes = Object.entries(laneValidators)
  .filter(([, v]) => v && !v.pass)
  .map(([id]) => id)

if (unresolvedLanes.length > 0) {
  log(`Note: lane validator(s) ${unresolvedLanes.join(', ')} did not reach PASS even after in-lane retries.`)
}

log(v7.pass
  ? `V7 PASS — ${v7.summary}. Ready for T29 (user's own quickstart.md acceptance pass in a real browser).`
  : `V7 FAIL — ${v7.summary}. Surfacing the specific FR/SC gaps rather than claiming done.`)

log('Syncing specs/015-frontend-routing/tasks.md — status table + both mermaid graphs')

const ledgerStatus = Object.fromEntries(
  Object.entries(allTaskReports).map(([id, r]) => [
    id,
    typeof r === 'string' ? 'done' : (r?.status === 'done' ? 'done' : 'blocked'),
  ])
)
const validatorStatus = {
  V1: v1.pass, V2: coreRouting.validator.pass,
  V3: laneA?.validator?.pass, V4: laneB?.validator?.pass,
  V5: laneC?.validator?.pass, V6: laneD?.validator?.pass, V7: v7.pass,
}

const ledgerSync = await agent(`
You are updating specs/015-frontend-routing/tasks.md to reflect a completed automated workflow
run. Read the file first, then edit it precisely — do not rewrite sections you don't need to
touch, do not change any task's description/AC text, only status representations.

Task results (id -> "done" or "blocked"):
${JSON.stringify(ledgerStatus, null, 2)}

Validator results (id -> pass true/false):
${JSON.stringify(validatorStatus, null, 2)}

Update ALL of the following, consistently with each other:
1. The "Task ledger" table near the bottom — set each row's Status column (⬜ pending -> ✅ done
   or 🔴 blocked) and add a one-line Evidence note summarizing what happened.
2. The top overview mermaid graph (near the very top of the file, plain-circle nodes) — move
   each task/validator id into the correct classDef line (todo/done/error).
3. The detailed "Execution graph — LIVE STATUS" mermaid graph further down — update each node's
   text prefix and the classDef membership lines the same way.
4. The "Status as of ..." summary line just above the detailed graph — update the counts to
   match reality.
5. Do NOT mark a task's checkbox "- [ ]" as "- [x]" unless its status is "done" AND its guarding
   validator passed — leave unchecked with a note in Evidence otherwise.

Return a brief text summary of what you changed.
`.trim(), { label: 'ledger-sync', phase: 'Acceptance', agentType: 'senior-engineer' })

log(`Ledger sync: ${ledgerSync}`)

return {
  v1,
  coreRouting: coreRouting.validator,
  laneA: laneA?.validator,
  laneB: laneB?.validator,
  laneC: laneC?.validator,
  laneD: laneD?.validator,
  finalAcceptance: v7,
  allTaskReports,
  nextStep: v7.pass
    ? 'Run specs/015-frontend-routing/quickstart.md as T29 (human acceptance pass).'
    : `Fix the gaps V7 identified, then resume this workflow before T29.`,
}

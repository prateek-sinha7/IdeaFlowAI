export const meta = {
  name: '015-frontend-routing-followup',
  description: 'Fix + re-validate only the reopened work from the main 015 run: T6/T7/T9/T11 (V2 regression: launch flow 404s), T22 (V5 scope gap), T25 (at-risk re-verify), then V2/V5/V6/V7 re-run.',
  phases: [
    { title: 'Fix', detail: 'T6,T7,T9,T11 (race condition) + T22 (401 scope gap) + T25 (re-verify)' },
    { title: 'Re-validate', detail: 'V2 (hard gate) -> V5, V6 -> V7 (final sweep)' },
  ],
}

// ---------------------------------------------------------------------------
// Scoped follow-up to the main 015-frontend-routing workflow (run wf_a9f2dc04-a8a).
// That run's V2 hard gate passed once (attempt 7 of 8) then failed again on its
// most recent recheck (attempt 8) with a live, reproducible regression: launching
// a workflow lands on Next's 404 page instead of the execution view — a race
// between T9's router.push and the trackedRunIdRef guard inside T7/T11's
// cold-mount effects in frontend/src/app/[...view]/page.tsx. T6 (which wires the
// mainView seeding those effects depend on) is also named. Separately, V5 found
// a scope gap in T22: its 401 handler only covers lib/api.ts, not Library's
// separate axios pipeline (store/api/http.ts) or useHandoffSocket.ts's hardcoded
// bare /login redirect.
//
// This script does NOT re-run anything already validator-confirmed and never
// contradicted (T1-T5,T8,T10,T30,T12-T21,T23,T24,T26-T28,V1,V3,V4) — those are
// fed to the validators below as trusted context, not re-dispatched.
// ---------------------------------------------------------------------------

const REPO_NOTES = `
Repo: VELOCITY-AI frontend, Next.js 16 App Router, React 19. Run all commands from frontend/.
Verify with: npx tsc --noEmit (type check) and npm test -- <file> (vitest, scoped).
Full context: specs/015-frontend-routing/{spec.md,plan.md,data-model.md,contracts/route-map.md,tasks.md}.
tasks.md's ledger has full detail on WHY each of these tasks was reopened — read it first.

STANDING RULES:
1. Change only what your task names. Do not tidy adjacent code, comments, or imports you did not orphan.
2. Never run a state-changing git command (no stash/checkout--/reset/clean/restore). Read-only git is fine.
3. Do not commit. Leave changes in the working tree.
4. If your anchor text/file is not found verbatim, do NOT guess — return status "blocked" with why.
5. Every path string goes through frontend/src/lib/routes.ts. A hand-written route literal anywhere else is a defect.
6. Do NOT add a routing library or any new package.json dependency.
7. Do NOT edit specs/015-frontend-routing/tasks.md — the orchestrator owns that file for this follow-up.
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
const DASHBOARD_LAYOUT = 'frontend/src/components/layout/DashboardLayout.tsx'
const API_TS = 'frontend/src/lib/api.ts'
const HTTP_TS = 'frontend/src/store/api/http.ts'
const HANDOFF_SOCKET = 'frontend/src/hooks/useHandoffSocket.ts'

// Context fed to validators for tasks this script does NOT re-dispatch — already
// validator-confirmed in the main run and never contradicted by anything since.
const TRUSTED_CONTEXT = {
  T1: 'routes.ts: 36 builders, tsc clean (V1-confirmed, prior session).',
  T2: 'parseViewPath + ParsedView union (V1-confirmed, prior session).',
  T3: 'routes.test.ts: 55 passing round-trip tests (V1-confirmed, prior session).',
  T4: 'data-model.md TBD rows resolved with citations (main run, never contradicted).',
  T5: '[...view] required-catch-all relocation (main run, never contradicted since attempt 4 of V2).',
  T8: 'saved-workflow-by-id cold fetch (main run, never contradicted).',
  T10: 'root auth redirect (main run, never contradicted).',
  T30: 'new /workflows/{id} read view (main run, never contradicted).',
  T12: 'run-history query params (V3-confirmed PASS).',
  T13: 'library query params (V3-confirmed PASS).',
  T14: 'analytics query params (V3-confirmed PASS).',
  T15: 'library item detail pages (V3-confirmed PASS).',
  T16: 'shallow push on modal (V3-confirmed PASS).',
  T17: 'legacy 301 redirects (V4-confirmed PASS).',
  T18: 'preview-fullscreen redirect (V4-confirmed PASS).',
  T19: 'not-found.tsx (V4-confirmed PASS).',
  T20: 'error.tsx/global-error.tsx (V4-confirmed PASS).',
  T21: 'test-preview deletion (V4-confirmed PASS).',
  T24: 'ownership-failure not-found handling (V5-confirmed passing since attempt 1).',
  T26: 'Edit affordance on SavedWorkflowsPage (self-reported done, main run).',
  T27: 'screenLabel helper (dispatched manually outside the main workflow after being stuck; code confirmed already correct).',
  T28: 'screenLabel threaded into error.tsx/global-error.tsx console.error calls (dispatched manually outside the main workflow after being stuck; done).',
  V1: 'PASS (route contract).',
  V3: 'PASS (shareable views, Lane A).',
  V4: 'PASS (edges & boundaries, Lane B).',
}

const NODES = {
  T6: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [VIEW_PAGE],
    file: VIEW_PAGE, traces: 'FR-001, FR-003 — REOPENED',
    desc: `V2's latest (8th) recheck found a live, reproducible regression: launching a workflow through the normal home->input->run flow and letting T9's URL-funnel push fire lands on Next's 404 not-found page instead of the execution view. Confirmed 3/3 in ad-hoc Playwright testing AND by the pre-existing, unmodified e2e suite frontend/e2e/tests/ts-j.streaming.spec.ts (8/8 tests failing with the identical 404 render). Root cause per V2's evidence: a race between T9's router.push (in DashboardLayout.tsx) and the trackedRunIdRef guard inside T7/T11's cold-mount effects in this file. T6 owns the mainView-seeding logic those cold-mount effects and the URL-driven state sync depend on — read the actual current code (do not assume the old description of T6 is still accurate; T7/T8/T9/T11 have all been touched multiple times since) and find the real sequencing bug: most likely the cold-mount effect's guard (trackedRunIdRef) is set/checked in a way that a URL-driven navigation (via T9's push, which changes params.view) doesn't correctly reconcile with — e.g. the guard treats a client-side push-triggered remount as if it were already-tracked and skips re-running the fetch/attach logic, OR the reverse (params.view changes but the guard blocks the effect from running at all). Trace the ACTUAL current control flow end-to-end (T6's mainView-seeding effect, T9's push, T7/T11's cold-mount effects, the trackedRunIdRef guard) before changing anything — this is a real regression in interaction between multiple already-shipped tasks, not a single isolated bug. Run frontend/e2e/tests/ts-j.streaming.spec.ts yourself as your primary verification signal.`,
    ac: [
      'frontend/e2e/tests/ts-j.streaming.spec.ts passes (was 8/8 failing — must go to 8/8 passing, or explain exactly which subset is unrelated to this regression if not all 8 are).',
      'Launching a workflow via the normal home->input->run flow lands on /runs/{newId}/stream showing the live execution view, not a 404 — verified by actually running the flow (Playwright or equivalent live exercise), not just code reading.',
      'No regression to any of V2 attempt 7\'s previously-passing criteria (all 34 routes still cold-open correctly, back/forward still works, tsc clean).',
    ],
  },
  T7: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: ['T6'], files: [VIEW_PAGE],
    file: VIEW_PAGE, traces: 'FR-003, SC-001 — REOPENED',
    desc: `SEQUENTIAL AFTER T6 (same file) — the fix for T6 may already resolve this, but verify independently: this task's cold-mount run-fetch effect and its trackedRunIdRef guard are named by V2 as party to the launch-flow 404 regression. After T6's fix, re-check this effect's own logic specifically: does it correctly distinguish "cold mount from a hard refresh / initial URL" from "client-side navigation triggered by T9's router.push after a fresh launch"? If T6's fix alone doesn't resolve the regression when you test it, the bug may be here — read T7's actual current implementation in full before concluding it's fine.`,
    ac: [
      'frontend/e2e/tests/ts-j.streaming.spec.ts passes.',
      'Launching a workflow lands on the live execution view at /runs/{newId}/stream, verified by actually running the flow.',
      'Cold-opening an existing /runs/{id} (unrelated to a fresh launch) still works exactly as before — no regression to that separate path.',
    ],
  },
  T9: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [DASHBOARD_LAYOUT],
    file: DASHBOARD_LAYOUT, traces: 'FR-001, FR-004 — REOPENED',
    desc: `V2 names this task's router.push (fired on run launch, pushing routes.runStream(newId)) as the other half of the race with T7/T11's cold-mount guard in the catch-all page. Read the actual current call site(s) around run launch — there may now be more than one push happening (T9's general setMainView-adjacent push AND T25's launch-specific push, if T25 already landed) which could itself be the bug (two competing pushes, or a push firing before the new run id is actually ready). Trace this precisely rather than assuming the original single-push design is still what's in the code.`,
    ac: [
      'frontend/e2e/tests/ts-j.streaming.spec.ts passes.',
      'Launching a workflow lands on the live execution view, verified by actually running the flow — not a 404.',
      'No duplicate/competing router.push calls fire for a single launch (check via a quick console/network trace if needed).',
    ],
  },
  T11: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: ['T7'], files: [VIEW_PAGE],
    file: VIEW_PAGE, traces: 'FR-003, SC-002 — REOPENED',
    desc: `SEQUENTIAL AFTER T7 (same file). This task's stream-reattach cold-mount effect and its trackedRunIdRef guard are the other side of V2's named race. After T6/T7/T9's fixes land, verify this effect specifically still correctly re-attaches on an actual hard refresh (SC-002) AND does not incorrectly treat a fresh-launch client-side navigation as "already tracked, skip."`,
    ac: [
      'frontend/e2e/tests/ts-j.streaming.spec.ts passes.',
      'Hard-refresh mid-run on /runs/{id}/stream still re-attaches correctly (SC-002 — do not regress this while fixing the launch-flow race).',
      'Launching a workflow lands on the live execution view, verified by actually running the flow.',
    ],
  },
  T22: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: [API_TS, HTTP_TS, HANDOFF_SOCKET],
    file: `${API_TS} (already done) + ${HTTP_TS} (new) + ${HANDOFF_SOCKET} (new)`, traces: 'FR-015 — scope widened per V5\'s diagnosis',
    desc: `V5 found T22's original scope (lib/api.ts only) doesn't satisfy FR-015's "fires from ANY screen" requirement. Two concrete gaps, both confirmed by direct inspection: (1) Library's agent/skill/hook fetches run through ${HTTP_TS}'s axios pipeline, whose response interceptor has zero 401/ApiError handling — add the same "clear token + redirect to routes.login({expired:true})" behavior T22 already added to lib/api.ts's fetchWithAuth(), but wired into this axios instance's response interceptor instead. (2) ${HANDOFF_SOCKET} hardcodes a bare '/login' redirect with no ?expired=true — change it to use routes.login({expired:true}) (or the equivalent routes.ts builder) so the expiry message actually shows. Do not duplicate logic — extract a small shared helper if that avoids copy-pasting the redirect+clear-token behavior three times, but do not over-engineer a new abstraction beyond what's needed for these two call sites.`,
    ac: [
      'A 401 from a Library screen (agent/skill/hook fetch) redirects to /login?expired=true with the token cleared — verified live, not just by reading the interceptor code.',
      'A 401 in the handoff/auth flow (useHandoffSocket.ts) redirects with ?expired=true instead of a bare /login.',
      'lib/api.ts\'s existing behavior (already correct) is unchanged — no regression there.',
      'No new tracking/HTTP dependency added (package.json unchanged) — reuse the existing axios instance and existing routes.ts builders.',
    ],
  },
  T23: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/app/login/page.tsx'],
    file: 'frontend/src/app/login/page.tsx', traces: 'FR-015 — REOPENED, contradicts a prior false-positive',
    desc: `The main run's V5 previously reported this fixed and passing (attempt 3+), but the follow-up's own V5 live-reproduced that it is NOT actually fixed: line 13 currently reads \`const isExpired = searchParams.get("expired") === "1";\` — but every real redirect in the app goes through routes.ts's login() builder, which serializes the expired flag as the string "true", not "1". So isExpired is always false and the "Your session expired" message never shows. Fix the exact-string comparison to match what routes.ts actually emits — read routes.ts's login() builder first to confirm the exact string it produces, then match this check to it exactly (do not guess; do not change routes.ts itself, this task's file is login/page.tsx only).`,
    ac: [
      'searchParams.get("expired") comparison in login/page.tsx exactly matches the string routes.ts\'s login({expired:true}) builder actually produces — verified by reading routes.ts directly, not assumed.',
      'Opening /login with that real query string shows the "Your session expired" message; a normal /login (no param) does not.',
      'No new component created; uses the existing inline-error styling already in the file.',
    ],
  },
  T13: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/components/library/LibraryPage.tsx'],
    file: 'frontend/src/components/library/LibraryPage.tsx', traces: 'FR-005, SC-003 — REOPENED, contradicts a prior false-positive',
    desc: `The main run's V3 previously confirmed this passing, but this follow-up's own V2 (re-validating the Core Routing hard gate) live-reproduced a real, session-wide SC-003 regression rooted here: LibraryPage.tsx's URL-sync effect (the one added for ?category= query-param encoding) fires an unguarded router.replace() on EVERY fresh mount of the component — not only on a real filter/category change. Because router.replace() overwrites the current history entry instead of pushing a new one, this silently destroys whatever history entry was there before, breaking back/forward navigation across the WHOLE session, not just within the library screen. Find the effect (reads the current category/filter state and calls router.replace(routes.libraryAgents(...) or similar) and add a guard so it only replaces the URL when the filter state has actually CHANGED from what the URL already encodes on mount — not on every render/mount. Compare against how T12/T14's equivalent query-param effects in run-history/AnalyticsPage handle this (they were NOT flagged, so their guard logic — if any — is probably correct; match their pattern if it differs from LibraryPage's).`,
    ac: [
      'Mounting LibraryPage with a URL that already matches its current filter state does NOT call router.replace() at all.',
      'A real filter/category change still updates the URL via router.replace (unchanged behavior for the actual use case).',
      'Back/forward navigation across a full session (visit several unrelated screens, then use back repeatedly) is not broken by having visited the library screen at any point — verified live, not just by reading the diff.',
      'No regression to the ?category= encoding behavior itself (still round-trips correctly on a fresh session open).',
    ],
  },
  T25: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: ['T9'], files: [DASHBOARD_LAYOUT],
    file: 'run-launch call sites (DashboardLayout.tsx, ComposerPage onRun, creation flows)', traces: 'FR-010 — at-risk, defensive re-verify',
    desc: `SEQUENTIAL AFTER T9 (same file — T9's fix for the race condition may touch the same launch call sites T25 already wired). T25 was never itself named as failing by any validator, but its entire job (every launch path lands on /runs/{newId}/stream) is exactly the flow V2's regression breaks. After T9's fix, verify T25's own launch call sites (composer run-once, saved-workflow launch, each creation flow, revision launches) all still correctly land on the live execution view — do not assume T25's original work is untouched by T6/T7/T9/T11's fixes without checking.`,
    ac: [
      'Every launch path enumerated in T25\'s original work still lands on /runs/{newId}/stream, re-verified live after T9\'s fix (not just re-reading the diff).',
      'No duplicate or conflicting push between T9\'s general URL-sync push and T25\'s launch-specific push.',
      'frontend/e2e/tests/ts-j.streaming.spec.ts still passes after this task (should already be green from T6/T7/T9/T11 — this is a final confirmation, not a place to reintroduce the bug).',
    ],
  },

  T31: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/hooks/useRunStream.ts'],
    file: 'frontend/src/hooks/useRunStream.ts', traces: 'FR-015, SC-009 — V7 found a 4th undiscovered duplicate',
    desc: `V7's final sweep found that useRunStream.ts:215-225's own handleAuthExpiry() (the live SSE run-stream connection's auth-failure handler — actively used by app/[...view]/page.tsx, DashboardLayout.tsx, and RunConnectionProvider.tsx) bypasses the canonical handleSessionExpiry() helper T22 built and instead does a bare window.location redirect to /login with no ?expired=true, so the required session-expired message never shows for a session that expires mid-stream. This is the 4th place this exact defect has now been found (lib/api.ts, store/api/http.ts, useHandoffSocket.ts were the first three, all fixed by T22). Read handleSessionExpiry()'s actual current signature/location first (T22 built it — likely exported from lib/api.ts or a shared auth-helpers module), then call it from useRunStream.ts's handleAuthExpiry() the same way the other three call sites do, replacing the bare redirect.`,
    ac: [
      'useRunStream.ts\'s auth-expiry handler calls the same shared handleSessionExpiry() helper the other three call sites use — no bare window.location redirect remains.',
      'A session that expires while a live stream is open redirects to /login?expired=true with the token cleared, verified live if practical (or by direct code trace if a live SSE-expiry scenario is impractical to construct — state clearly which).',
      'No behavior change to the SSE connection/reconnect logic itself beyond the auth-expiry redirect path.',
    ],
  },
  T26: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx', 'frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx'],
    file: 'frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx + its test file', traces: 'FR-011 — V7 found a regression this follow-up introduced',
    desc: `V7's final sweep found that this task's earlier useRouter() addition (for the Edit affordance's navigation) broke 8 pre-existing tests in SavedWorkflowsPage.test.tsx that predate this spec and were never meant to be touched. Read the actual test failures first (npm test -- SavedWorkflowsPage.test.tsx) to see the exact errors — most likely the pre-existing tests don't mock next/navigation's useRouter and now crash on render. Fix by adding the missing mock/wrapper the OTHER already-passing tests in this codebase use for components that call useRouter (check a sibling test file that already handles this, e.g. one of the history/library test files, for the established pattern) — do not weaken or delete the pre-existing assertions themselves, only make the test environment support the router dependency the component now genuinely has.`,
    ac: [
      'npm test -- SavedWorkflowsPage.test.tsx is fully green (all previously-passing tests pass again, plus whatever this spec already added).',
      'No pre-existing test assertion was weakened, skipped, or deleted to make this pass — only the missing router mock/setup was added.',
      'The Edit affordance itself (this task\'s original deliverable) is unchanged and still works.',
    ],
  },
  T32: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/app/[...view]/terminalStatusReconcile.source.test.ts'],
    file: 'the test file with a hardcoded old dashboard/ path (identify exact filename — likely terminalStatusReconcile.source.test.ts, relocated alongside T5)', traces: 'housekeeping — V7 found a regression T5\'s relocation caused',
    desc: `V7's final sweep found that a test (terminalStatusReconcile.test.ts, or wherever it actually now lives after T5's relocation) does a readFileSync (or similar direct file read) against a hardcoded OLD path under frontend/src/app/dashboard/, which T5 legitimately relocated to frontend/src/app/[...view]/ earlier in this spec. Find the exact hardcoded path string in the failing test (run npm test to see the exact file and error first) and update it to the new [...view]/ location — this is a pure path-string fix, not a logic change.`,
    ac: [
      'The specific failing test (identify it exactly from the npm test output) passes again.',
      'No other test\'s hardcoded paths were touched beyond the one(s) actually referencing the old dashboard/ location.',
      'Full vitest suite pass count is at or above what V7 measured (1144 passed / 9 failed) minus the tests this task and T26 fix.',
    ],
  },
  T33: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Fix',
    deps: [], files: ['frontend/src/lib/api-handoff.ts'],
    file: 'frontend/src/lib/api-handoff.ts', traces: 'FR-015, SC-009 — V7 found a 5th duplicate',
    desc: `V7's final sweep found a 5th place this exact defect has now been found (after lib/api.ts, store/api/http.ts, useHandoffSocket.ts, and T31's useRunStream.ts fix): api-handoff.ts's authedJson() (lines 58-80) never calls the shared handleSessionExpiry() helper on a non-2xx/401 response — it just throws a generic Error. This backs getHandoff/startHandoff (called at HandoffWorkflow.tsx:78 on every /handoff/{token} page load — the auth gate at line 62-70 only checks a token EXISTS, not that it's still valid, so a stale token reaches this call) and getGithubPatStatus/listApiKeys (used by /handoff/settings's IntegrationsCard.tsx). Fix authedJson() to call handleSessionExpiry() on a 401, mirroring T31's exact fix pattern in useRunStream.ts. THEN, since this is now the 5th occurrence of the same missed-centralization defect, do one more thing before returning: grep the codebase for any OTHER fetch/axios/API call site that checks response.status/err.status for 401 without going through handleSessionExpiry() (search for patterns like "401" or "status === 401" or "err.status" near a catch block, excluding the 5 now-fixed sites and lib/api.ts/http.ts themselves which ARE the canonical implementations) — report explicitly whether you found any more, and fix them too if found, or state clearly "none found" if the sweep comes up empty. Do not create a general "audit everything" task beyond this specific, scoped grep.`,
    ac: [
      'authedJson() in api-handoff.ts calls handleSessionExpiry() on a 401, verified live or via a targeted test (mirroring how T31/T22 verified their fixes), not just code reading.',
      '/handoff/{token} with a stale/invalid token redirects to /login?expired=true with the token cleared.',
      '/handoff/settings\'s PAT/API-key management does the same on a 401.',
      'The codebase-wide grep for other unguarded 401 checks was actually performed and its result (found-and-fixed, or none-found) is stated explicitly in the summary — not silently skipped.',
    ],
  },
  V2: {
    kind: 'validator', agentType: 'qa-engineer', model: 'sonnet', phase: 'Re-validate',
    deps: ['T6', 'T7', 'T9', 'T11', 'T13'],
    guards: ['T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T30', 'T13'],
    context: `This is a RE-VALIDATION of the Core Routing hard gate from the main 015 run. It passed once before (attempt 7 of 8 in the main run's history) then FAILED on a later recheck (attempt 8) with a live regression: launching a workflow lands on a 404 instead of the execution view, root-caused to a race between T9's push and T7/T11's cold-mount trackedRunIdRef guard, naming T6/T7/T9/T11. Those four were redone. CORRECTION mid-run: after that fix, this follow-up's OWN first V2 recheck found the 404 regression genuinely gone (ts-j.streaming.spec.ts 8/8, ts-s.reconnect.spec.ts 4/5 expected) but could not pass anyway — it found a SEPARATE, session-wide SC-003 (back/forward) regression rooted in LibraryPage.tsx (T13, outside V2's original T4-T11/T30 roster, so it couldn't be named in that failedTasks list): an unguarded router.replace() firing on every mount was silently destroying history entries. T13 is now a real task here and has just been redone; T13 is added to this validator's own guards/deps so it CAN be named if still broken. T4,T5,T8,T10,T30 were never contradicted by any V2 attempt after their own initial fixes landed. Full trusted context for tasks NOT redispatched by this script:\n${JSON.stringify(TRUSTED_CONTEXT, null, 2)}`,
    criteria: [
      'All 34 routes open cold in a fresh tab and render the correct screen WITH DATA, not an empty shell.',
      'CRITICAL, the specific regression this re-validation exists to catch: launch a workflow through the normal home->input->run flow (or any equivalent launch path) and confirm it lands on the live execution view at /runs/{newId}/stream, NOT a 404. Actually run this, do not infer from code. Also run frontend/e2e/tests/ts-j.streaming.spec.ts and report its pass/fail count explicitly.',
      'Hard-refresh on /runs/{id}/stream mid-run re-attaches (SC-002) — must be actually exercised (run frontend/e2e/tests/ts-s.reconnect.spec.ts if it still exists and is relevant).',
      'Back/forward across 10 navigations is correct (SC-003).',
      'grep -c "setMainView(" DashboardLayout.tsx — every occurrence has an adjacent routes.* push, and no duplicate/competing pushes exist for a single action.',
      'No hand-written route literal outside routes.ts.',
      'npx tsc --noEmit clean.',
    ],
  },
  V5: {
    kind: 'validator', agentType: 'qa-engineer', model: 'sonnet', phase: 'Re-validate',
    deps: ['T22', 'T23'],
    guards: ['T22', 'T23', 'T24'],
    context: `Re-validation of Lane C (auth-boundary). CORRECTION mid-run: this follow-up's own first V5 check found T23 was NOT actually fixed despite the main run's ledger claiming it was (exact-string "expired" param mismatch — login/page.tsx checked "1", routes.ts emits "true") — that was a false-positive in the earlier validation, now caught and T23 redone for real. T24 remains confirmed passing (stable since V5 attempt 1 in the main run) — trust but spot-check, don't fully re-derive. T22 was redone to widen its scope to store/api/http.ts and useHandoffSocket.ts per the diagnosed gap. Given a previously "confirmed" task turned out to still be broken, verify T23's fix live yourself rather than assuming the task's self-report is correct this time either. Trusted context: T24=${TRUSTED_CONTEXT.T24}`,
    criteria: [
      'Expired/cleared session from at least one screen per area in spec.md §5 (auth, home/creation, runs, workflows, LIBRARY, settings/analytics, and the HANDOFF flow) -> /login?expired=true with a visible message. This time explicitly include a Library screen and the handoff flow — the two gaps that failed before.',
      'Bad credentials on /login still show the inline error and do NOT redirect-loop.',
      'A cross-account run id returns not-found and no run data leaks.',
      'A 401 and a 403 take different paths (login vs not-found).',
      'The token is actually cleared on expiry (check storage).',
    ],
  },
  V6: {
    kind: 'validator', agentType: 'qa-engineer', model: 'sonnet', phase: 'Re-validate',
    deps: ['V2', 'T25'],
    guards: ['T25', 'T26', 'T27', 'T28'],
    context: `First real run of V6 (never dispatched in the main run — it was gated on T27/T28, which got stuck and were dispatched manually outside the workflow). T26,T27,T28 are self-reported/confirmed done and not touched by this follow-up. T25 was just re-verified after T9's race-condition fix. Trusted context: T26=${TRUSTED_CONTEXT.T26} T27=${TRUSTED_CONTEXT.T27} T28=${TRUSTED_CONTEXT.T28}`,
    criteria: [
      'Every launch path lands on /runs/{newId}/stream — enumerate the paths found and confirm each, live.',
      'A saved workflow opens -> edits -> re-saves successfully, entirely through the UI.',
      'Screen labels are distinct across all 34 screens — no two screens share a label.',
      'No new tracking dependency was added (package.json unchanged) — including by T22\'s widened scope in this follow-up.',
    ],
  },
  V7: {
    kind: 'validator', agentType: 'qa-engineer', model: 'sonnet', phase: 'Re-validate',
    deps: ['V2', 'V5', 'V6', 'T31', 'T26', 'T32', 'T33'],
    guards: ['V2', 'V3', 'V4', 'V5', 'V6', 'T31', 'T26', 'T32', 'T33'],
    context: `Final acceptance sweep. V3 and V4 already passed in the main run and are not re-run here — trust their PASS but verify the FRs/SCs they cover still hold given everything else that changed. HISTORY: attempt 1 found T31/T26/T32 (all now fixed and confirmed). Attempt 2 was a stale/wrong replay (orchestrator independently disproved all 4 of its claims via fresh reads/test runs) — disregard its content entirely. Attempt 3 was genuinely fresh and correctly confirmed T31/T26/T32 all pass, but found a 5th duplicate of the session-expiry defect in api-handoff.ts's authedJson() (the handoff area's REST load path, in scope per spec.md despite being excluded from the 34-screen count) — now fixed as T33, which also swept for any further undiscovered duplicates of this same pattern. Verify T33's fix AND its sweep result for real — this defect has now recurred 5 times across this spec's history (lib/api.ts, http.ts, useHandoffSocket.ts, useRunStream.ts, api-handoff.ts), so scrutinize this specific area more than usual before declaring it closed. Full trusted context: ${JSON.stringify(TRUSTED_CONTEXT, null, 2)}`,
    criteria: [
      'Each of FR-001 through FR-015 demonstrably satisfied — one line of evidence each, no blanket claims. Pay special attention to FR-010 (launch navigation) and FR-015 (session expiry) given this follow-up run\'s history.',
      'Each of SC-001 through SC-009 verified — SC-001 means all 34 routes actually opened, not sampled.',
      'frontend/package.json unchanged across the entire spec, including this follow-up.',
      'npx tsc --noEmit has no NEW errors attributable to any task in this spec\'s scope — the ~73 pre-existing errors confined to unrelated *.test.tsx files (WorkflowHistory*, LibraryPage*, DashboardLayout.laneTitle, NotificationPanel.fix195, LaunchWizard) are a known, already-tolerated baseline per every prior validator in this spec (V1-V6) and are NOT this spec\'s responsibility to fix. Full vitest suite (not just the two named e2e specs) at or above its pre-follow-up baseline (1144 passed / 9 failed was the count V7 measured before T26/T32\'s fixes) — confirm the 9 known failures are now resolved and nothing else newly broke.',
      'contracts/route-map.md still matches the implementation exactly.',
    ],
  },
}

// ---------------------------------------------------------------------------
// Scheduler — identical to the main 015 script and the ba-workflow-generate
// skill's canonical template: dependency-graph + file-collision safety,
// crash-safe agent() wrapping, per-task escalation ladder (3 normal + 2 opus).
// ---------------------------------------------------------------------------

const MAX_PARALLEL = 6
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
You are executing task ${id}, part of a FOLLOW-UP workflow fixing reopened work from the main
015-frontend-routing run. Another agent will validate your work afterward — be honest in your
self-check.

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
      const r = results[gid] || TRUSTED_CONTEXT[gid]
      if (!r) return `${gid}: NOT YET RUN`
      if (typeof r === 'string') return `${gid}: ${r}`
      return `${gid} [${r.status || (r.pass ? 'pass' : 'fail')}] — ${r.summary}\n  filesChanged: ${(r.filesChanged || []).join(', ') || '(none reported)'}\n  self-check: ${JSON.stringify(r.acSelfCheck || r.checks)}`
    })
    .join('\n\n')
  return `
You are validator ${id}, re-validating reopened/incomplete work from the 015-frontend-routing
spec's follow-up workflow. You guard: ${v.guards.join(', ')}.
Your job is to judge, by actually inspecting the code and running commands (including live
browser/e2e exercise where the criteria call for it), whether these genuinely satisfy the
criteria below — do NOT just trust the task reports, they are context only.

${REPO_NOTES}

${v.context ? `IMPORTANT CONTEXT: ${v.context}\n` : ''}
TASK/GUARD REPORTS (context, verify independently):
${reportsText}

PASS requires ALL of the following (check each by inspection/exercise, not by reading the diff alone):
${v.criteria.map((c, i) => `${i + 1}. ${c}`).join('\n')}

For each criterion, actually check it. Where a criterion requires exercising live behavior, do so
directly (this spec's whole reopening was caused by a validator that previously passed on
insufficient live exercise) — reason from code only as a last resort, and say so explicitly in
"evidence" when you do.

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

    if (exhausted.length) {
      log(`${id}: ${exhausted.join(', ')} already exhausted ${MAX_TASK_FIX_ATTEMPTS}/${MAX_TASK_FIX_ATTEMPTS} attempts — not retrying again.`)
    }
    const nonRedoable = result.failedTasks.filter((tid) => !NODES[tid])
    if (nonRedoable.length) {
      log(`${id}: FAIL names ${nonRedoable.join(', ')}, which this follow-up doesn't own (not in its NODES table) — cannot auto-redo, needs orchestrator attention.`)
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
        if (escalate) log(`${tid}: attempt ${attempt}/${MAX_TASK_FIX_ATTEMPTS} — escalating to opus.`)
        const r = await safeAgent(taskPrompt(tid, feedbackText), {
          label: `${tid}-retry${attempt}${escalate ? '-opus' : ''}`,
          phase: NODES[tid].phase,
          agentType: NODES[tid].agentType,
          model: escalate ? 'opus' : NODES[tid].model,
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
phase('Re-validate')

log('Follow-up workflow: fixing T6,T7,T9,T11 (launch-flow 404 regression) + T22 (401 scope gap) + T25 (defensive re-verify), then re-validating V2 (hard gate) -> V5,V6 -> V7.')

await scheduler()

const done = Object.keys(NODES).filter((id) => state[id] === 'done')
const errored = Object.keys(NODES).filter((id) => state[id] === 'error')

log(`Finished: ${done.length}/${Object.keys(NODES).length} done, ${errored.length} error/blocked.`)
if (errored.length) log(`Blocked nodes: ${errored.join(', ')} — see their reports for what to fix.`)

const v7 = results.V7

log('Syncing specs/015-frontend-routing/tasks.md with this follow-up\'s outcome')

const ledgerSync = await safeAgent(`
You are updating specs/015-frontend-routing/tasks.md to reflect the FOLLOW-UP workflow's outcome
(the reopened-work fix pass, distinct from the original run). Read the file's own ## STATUS-SYNC
section first, then apply it: for each of T6,T7,T9,T11,T22,T25,V2,V5,V6,V7, update the ledger row
(flip 🔴 REOPENED / ⚠️ at-risk / 🔍 not run to ✅ done or leave as 🔴/blocked if still failing,
citing what actually happened) and both mermaid graphs' classDef membership + node prefixes
accordingly. Do not touch task description/AC text.

Results (id -> done/blocked, or pass/fail for validators):
${JSON.stringify(Object.fromEntries(Object.keys(NODES).map((id) => [id, results[id]?.status ?? results[id]?.pass ?? 'no result'])), null, 2)}

Verify fence balance and count consistency (37 total nodes) after editing. Report a brief summary.
`.trim(), { label: 'followup-ledger-sync', phase: 'Re-validate', agentType: 'senior-engineer' })

log(`Ledger sync: ${ledgerSync}`)

return {
  done, errored, results,
  v7,
  summary: `Follow-up: ${done.length}/${Object.keys(NODES).length} nodes done. ` +
    (errored.length ? `Still blocked: ${errored.join(', ')}.` : 'Regression fixed and re-validated end to end.'),
}

# Known Bugs

Canonical shared ledger for the autonomous browser bug hunt against Velocity (local dev,
`http://localhost:3000`).

Workers MUST read this file in full before any browser interaction, and MUST re-read it while
holding `bug-hunter/ledger.lock` immediately before recording a newly discovered issue.

Append only. Never rewrite or delete an existing entry. Evidence for each bug lives in
`bug-hunter/evidence/<page-slug>/<BUG-ID>/`. See `bug-hunter/README.md` for the full contract.

---

<!-- Bugs are appended below this line, newest last. -->

## BUG-20260828-040915-preview-fullscreen-quota — `?error=quota` always shows the "too large" dead-end even when a fully valid preview is sitting in sessionStorage

- **Page:** Fullscreen preview — quota error
- **Route:** /preview-fullscreen?error=quota
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 04:09 UTC
- **Found by:** bug-preview-fullscreen-quota-r1
- **Fingerprint:** `/preview-fullscreen|error-quota-flag-precedence|navigate-with-error=quota-while-valid-__app_preview__-payload-present-in-sessionStorage|quota-dead-end-shown-instead-of-working-preview-that-is-actually-cached`
- **Evidence:** `bug-hunter/evidence/preview-fullscreen-quota/BUG-20260828-040915-preview-fullscreen-quota/`
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic, pure client-side branch-order bug, no timing/entry-path dependency (varied cold plain-then-quota, cold direct deep-link to quota, full re-clear-and-reload — all 3/3)
- **Issue card:** [ISS-298](../.knowledge/cards/20260828-1729-ISS-298.md)
- **Fix card:** [FIX-369](../.knowledge/cards/20260829-0114-FIX-369.md) — quota flag no longer
  short-circuits the `__app_preview__` read in `frontend/src/app/preview-fullscreen/page.tsx`;
  the dead end is now the fallback when nothing usable is cached. Test
  `suites/07_run_detail/test_iss298_preview_fullscreen_quota_ignores_cache.py` XPASS(strict).
- **Root cause:** The `error === "quota"` branch (`frontend/src/app/preview-fullscreen/page.tsx:47-50`)
  returns unconditionally before the component ever reaches the `sessionStorage.getItem("__app_preview__")`
  read/parse that the plain (no-param) branch performs a few lines later (`page.tsx:56-69`). Both
  branches sit in the same top-level `useEffect` (lines 36-76). CONFIRMED by reading `page.tsx` in
  full and `AppBuilderPreview.tsx:406-421` (`handleFullscreen`, which writes `{files, projectName}`
  to `sessionStorage["__app_preview__"]` and opens `?error=quota` only when that write throws —
  `sessionStorage.setItem` is atomic, so an earlier successful write's data survives a later failed
  one untouched).
- **Blast radius:** Exactly one production caller triggers this state —
  `AppBuilderPreview.handleFullscreen()` (`AppBuilderPreview.tsx:419`) is the sole place
  `?error=quota` is opened, and `preview-fullscreen/page.tsx` is its sole consumer — so the fix is
  entirely local to that one file/useEffect, not fanned across many call sites. That said,
  `handleFullscreen` and the `__app_preview__` key it writes are shared by every
  `<AppBuilderPreview>` render site (`PreviewPanel.tsx:163`, `WorkflowHistory.tsx:833`,
  `WorkflowHistory.tsx:872`), which is what [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md)
  traces further.
- **Proposed fix:** Restructure `preview-fullscreen/page.tsx`'s `useEffect` so the quota and plain
  branches share the same `sessionStorage["__app_preview__"]` read/parse instead of the quota
  branch returning ahead of it — matching the precedence the page's own docstring (lines 27-29)
  already claims but the code does not implement. Belongs in this one file; no other caller needs
  a guard. Flagged for the fixer: `__app_preview__` carries no run/project identity
  ([ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md)), so simply rendering "whatever is
  cached" risks showing a stale, unrelated run's files as if they were the one that just hit quota
  — worth a conscious decision, not a silent side effect of the fix.
- **Issue cards:** [ISS-298](../.knowledge/cards/20260828-1729-ISS-298.md) (root),
  [ISS-407](../.knowledge/cards/20260828-2343-ISS-407.md) (sibling: plain route silently redirects
  to Run History with no error state on missing/corrupt sessionStorage — the inverse case),
  [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md) (sibling: `__app_preview__` is one
  unscoped global key shared by 3 render sites, so a stale write can be shown as the current run —
  INFERRED, unreproduced)
- **Verified:** 2026-08-29 —
  `suites/07_run_detail/test_iss298_preview_fullscreen_quota_ignores_cache.py` ran XPASS(strict)
  first (pass signal), `xfail` marker removed, re-run confirmed plain green (0.4s). Manual repro
  from this entry re-run by hand in Chrome (qa-admin, lane6): seeded `__app_preview__`, plain
  `/preview-fullscreen` rendered `"VerifierReproProject — IDE Preview"`, then
  `/preview-fullscreen?error=quota` in the same tab now also rendered that cached preview instead
  of the dead end — no console errors. Regression guard confirmed too: clearing
  `__app_preview__` and reloading `?error=quota` still shows "Project too large for full screen"
  (S-16-07 intact). `frontend/src/app/preview-fullscreen/page.tsx` has zero `tsc --noEmit`
  errors (pre-existing unrelated errors in `HomeLaunchGrid.crossAccountLeak.test.tsx` and
  `store/listenerMiddleware.test.ts` untouched). Backend `:8000/docs` → 200, no restart needed
  (frontend-only change). `lint-imports` from `backend/` shows the same pre-existing
  `kernel imports only capability ports` break, unrelated to this fix (no Python touched).
  Regression suite file `suites/16_pages_outside_routes/test_pages_outside_routes.py` run in
  full: S-16-05/S-16-06/S-16-07 (the three guards this fix names) all PASS; one unrelated
  failure, S-16-12 "An API key is shown once and never again", failing on a leftover
  `validator-handoff-fixture` API key from a prior run leaking into the handoff/settings list —
  a different feature area (API key handoff, not preview-fullscreen), not touched by FIX-369.

### Summary
`frontend/src/app/preview-fullscreen/page.tsx` checks `params.get("error") === "quota"` and, if
true, immediately renders the dead-end "Project too large for full screen" message and `return`s
— before ever looking at `sessionStorage["__app_preview__"]`. The plain (no-param) route by
contrast reads that same key and renders the full working IDE preview when it holds valid data.
Because `AppBuilderPreview.handleFullscreen()` opens the fullscreen tab via `window.open(...,
"_blank")` **without** `"noopener"` specifically so the new tab shares the opener's browsing
context (confirmed by the code's own comment), sessionStorage is shared between the two tabs.
`sessionStorage.setItem` is atomic — a `QuotaExceededError` throw leaves any previously-stored
value untouched. So the realistic sequence is: a user successfully opens Full Screen once
(`__app_preview__` now holds valid, renderable file data), then triggers a second Full Screen
attempt whose write throws quota-exceeded (larger project) — the catch block opens a new tab at
`?error=quota`. That new tab shares the exact same sessionStorage that still contains the
**earlier, fully valid and renderable** preview payload, yet the page shows only the unhelpful,
inapplicable "too large" message and never offers or falls back to the working cached preview it
has direct access to. This is demonstrated deterministically below by seeding
`__app_preview__` with a valid payload and comparing the plain route (renders it correctly) against
the same route with `?error=quota` appended (discards it, shows the dead end, while the payload
is still verifiably present and parseable in sessionStorage the whole time).

### Reproduction
1. Sign in as qa-admin. In `sessionStorage`, set a valid payload:
   `sessionStorage.setItem('__app_preview__', JSON.stringify({files:[{path:'index.html',
   content:'<h1>hello</h1>'}], projectName:'ValidCachedProject'}))`.
2. Navigate to `http://localhost:3000/preview-fullscreen` (no query params). Observe the page
   correctly renders the full IDE preview: title becomes `"ValidCachedProject — IDE Preview"`,
   file explorer shows `index.html`, content is visible. This confirms the cached payload is
   valid and renderable.
3. Navigate to `http://localhost:3000/preview-fullscreen?error=quota` (same tab/session, payload
   untouched). Observe the page instead shows "Project too large for full screen" / "The
   generated project exceeds the browser session storage limit (~5MB)..." — the dead-end error
   state, not the preview.
4. Confirm in the same page load that the valid data was never touched or consulted:
   `!!sessionStorage.getItem('__app_preview__')` is `true` and
   `JSON.parse(sessionStorage.getItem('__app_preview__')).files.length` is `1` — the exact data
   from step 1, fully intact and parseable, while the UI shows only the generic error.
5. Repeated with a second, independent payload (`{files:[{path:'app.js',...},{path:'style.css',
   ...}], projectName:'SecondRepro'}`) — identical result: `?error=quota` shows the dead end while
   `sessionDataStillPresent` reads `true` for the fresh, different payload.

### Expected
When `?error=quota` is present, the page should still check whether `__app_preview__` holds a
valid, parseable payload (the same check the plain route already performs) before giving up —
either rendering that last-known-good preview, or at minimum clarifying that a previous preview
is still available rather than unconditionally declaring the "too large" state on every load of
this URL regardless of what is actually sitting in the shared sessionStorage the two tabs
intentionally share.

### Actual
The `error === "quota"` branch returns unconditionally before any sessionStorage check, so a
tab that legitimately still holds a valid, viewable preview payload (from an earlier successful
Full Screen attempt in the same shared browsing context) is shown the generic, dead-end "too
large" message instead — discarding a working preview the app itself proves it can render, with
no way to reach it from this URL.

### Evidence
- Before (plain `/preview-fullscreen`, valid cached payload renders correctly): `bug-hunter/evidence/preview-fullscreen-quota/BUG-20260828-040915-preview-fullscreen-quota/01-before-valid-preview-renders.png`
- Failure (`?error=quota` with the same valid payload still in sessionStorage, dead end shown instead): `bug-hunter/evidence/preview-fullscreen-quota/BUG-20260828-040915-preview-fullscreen-quota/02-failure-quota-shown-despite-valid-cache.png`
- Reproduced with a second, independent payload: `bug-hunter/evidence/preview-fullscreen-quota/BUG-20260828-040915-preview-fullscreen-quota/03-repro2-different-cached-data.png`

### Browser Signals
- Console: no relevant error observed; the page renders its own hard-coded quota message
  entirely client-side.
- Network: no requests involved — this is a pure client-side branch order issue in a `useEffect`.
- State/URL: `location.href` stays on `/preview-fullscreen?error=quota` throughout;
  `sessionStorage.getItem('__app_preview__')` verified non-null and correctly parseable via
  direct `browser_evaluate` reads in both reproductions, proving the data was available and
  simply never consulted once the `error=quota` param was present.

## BUG-20260827-221400-dashboard — Escape does not close a catalog card's "Inspect" details modal

- **Page:** Dashboard (catalog)
- **Route:** /dashboard
- **Severity:** Low
- **Status:** CLOSED
- **Found at:** 2026-08-27 22:14 UTC
- **Found by:** bug-dashboard-r1
- **Fingerprint:** `/dashboard|catalog-card-inspect-modal|press-escape|dialog-remains-open`
- **Evidence:** `bug-hunter/evidence/dashboard/BUG-20260827-221400-dashboard/`
- **Verified:** 2026-08-29 by 6-verifier. `suites/15_overlays/test_iss326_inspect_escape.py` —
  XPASS(strict) confirmed (24.4s against a running dev server), then `xfail` marker removed and
  re-run plain green. Manual re-run of the ORIGINAL register reproduction in real Chrome
  (`mcp__lane5__*`, qa-admin, cold `/dashboard` nav): clicked "Inspect Retry Until It Passes
  details" -> "Retry Loop" dialog opened -> Escape -> `[role="dialog"]` count 0 (was 1); repeated
  on "Inspect Build an end-to-end application details" -> "App Builder" dialog -> Escape -> count
  0. Both cards match the original 3-cycle validation. No console errors/warnings on either card
  or on a hard `/dashboard` reload. `npx tsc --noEmit` and `npm run build` clean (the 9
  pre-existing tsc errors are all in unrelated test files, none in `WorkflowDialog.tsx` or
  `useEscapeToClose.ts`). `frontend/src/components/workflow/WorkflowDialog.test.tsx` 8/8 green,
  `frontend/src/components/catalog/HomeLaunchGrid.inspect.test.tsx` 2/2 green. Backend
  `:8000/docs` -> 200 (no backend file touched, no restart needed). `lint-imports` (run from
  `backend/`) shows one pre-existing broken contract (`agents.execution_engine.engine` ->
  `app.api`, unrelated to this frontend-only fix). `suites/15_overlays/test_overlays.py`
  (regression file) was run to scenario 20/36 before the 10-minute cap; only S-15-06 ("The
  add-agent modal lists agents by category", a `/workflows/new` composer scenario in
  `AgentsPopup.tsx`, a file this fix never touches) failed — unrelated to `WorkflowDialog.tsx`.
  `validate_links.py` shows 2 pre-existing broken links, neither on ISS-326/FIX-388.
- **Validated:** 3/3 on 2026-08-28, every cycle, cold start (fresh /dashboard nav) — reproduced on
  two different cards ("Retry Until It Passes" cycles 1-2, "Build an end-to-end application"
  cycle 3). Root cause: `frontend/src/components/workflow/WorkflowDialog.tsx` declares
  `role="dialog" aria-modal="true"` but has no Escape/keydown handler at all.
- **Root cause:** CONFIRMED — `WorkflowDialog.tsx` (`frontend/src/components/workflow/WorkflowDialog.tsx`)
  declares `role="dialog" aria-modal="true"` at lines 134-135; its only `useEffect` (lines 63-95) is
  a data-fetch effect for `getWorkflowDetail`/`getCapabilities`, not a key listener; a whole-file
  grep for `Escape`/`onKeyDown` returns zero matches. The dialog is dismissed only via the backdrop
  `onClick={onClose}` (line 131) or the Close button's `onClick={onClose}` (line 154) — no
  Escape/keydown handler exists anywhere in the file.
- **Blast radius:** `WorkflowDialog` has exactly one production caller —
  `frontend/src/components/catalog/HomeLaunchGrid.tsx:392` (confirmed by grepping every `.ts`/`.tsx`
  caller of `WorkflowDialog`) — so this specific component's blast radius is the dashboard catalog's
  Inspect affordance only. The ROOT CAUSE (a copy-pasted `role="dialog"` shell with no centralized
  Escape handling) recurs elsewhere in the same module: grepping every `role="dialog"` element under
  `frontend/src/components/workflow/` found two more instances with zero Escape/keydown/KeyboardEvent
  handling anywhere in their file — `AgentCapabilitiesModal` (`AgentsPopup.tsx:605-642`, mounted from
  `LaunchWizard.tsx`, `composer/ComposerPage.tsx`, `library/LibraryPage.tsx`, `AgentLibrary.tsx`) and
  `AgentSkillsPicker`'s skill-detail modal (`composer/AgentSkillsPicker.tsx:251-289`, mounted from
  `AgentsPopup.tsx:870`, `composer/AgentRow.tsx:267`, `composer/CanvasConfigRail.tsx:468`) — both
  INFERRED, not yet reproduced live.
- **Proposed fix:** extract ONE shared hook (e.g. `useEscapeToClose(onClose)`, modeled on the
  `document.addEventListener("keydown", ...)` pattern already used ad hoc in
  `TemplateDetailModal.tsx:29-38` and file-locally in `LibraryPage.tsx`'s `useDetailModalKeyboard`,
  [FIX-333](../.knowledge/cards/20260828-2131-FIX-333.md)) into `frontend/src/hooks/`, so
  `WorkflowDialog.tsx`, `AgentsPopup.tsx` and `composer/AgentSkillsPicker.tsx` all route their Escape
  handling through one place instead of each re-implementing (or omitting) it independently.
- **Issue card:** [ISS-326](../.knowledge/cards/20260828-ISS-326.md) (root),
  [ISS-489](../.knowledge/cards/20260829-0150-ISS-489.md) (sibling: AgentSkillsPicker skill-detail
  modal, INFERRED), [ISS-491](../.knowledge/cards/20260829-0149-ISS-491.md) (sibling:
  AgentCapabilitiesModal in AgentsPopup.tsx, INFERRED)
- **Fix card:** [FIX-388](../.knowledge/cards/20260829-0053-FIX-388.md) — new shared
  `frontend/src/hooks/useEscapeToClose.ts`, called as `useEscapeToClose(onClose, open)` from
  `WorkflowDialog.tsx`; `HomeLaunchGrid.tsx` needed no change (it already passes a correct
  `onClose`). Test `suites/15_overlays/test_iss326_inspect_escape.py` XPASS(strict). The sibling
  INFERRED cards ISS-489/ISS-491 are NOT fixed — their files are outside this card's globs; the
  hook they need now exists. The stale `@pytest.mark.defect` test in
  `suites/15_overlays/test_overlays.py::test_inspecting_a_catalog_workflow_describes_it_without_launching`
  now fails on its Escape half BY DESIGN (it asserts the old wrong behaviour) — left untouched
  for 6-verifier.

### Summary
Clicking the "Inspect <card> details" button on any dashboard catalog card opens a dialog
(`role="dialog"`, e.g. "App Builder workflow", "Retry Loop") showing context providers,
capabilities, and compaction info for that workflow. Pressing Escape while this dialog is
focused does not close it — the dialog remains open and the page stays visually dimmed/blurred
behind the backdrop. Only clicking the explicit "Close" (X) button dismisses it. This is a
distinct component from the already-documented Advanced workflow modal (D-22 in
DEFECTS-OBSERVED.md), which is reached via the "Advanced" button inside a launch panel/composer,
not via a catalog card's Inspect affordance on the dashboard itself.

### Reproduction
1. Sign in as qa-admin and land on /dashboard.
2. Click the "Inspect <card title> details" button on any catalog card (e.g. "Build an
   end-to-end application" or "Retry Until It Passes").
3. Observe the dialog opens (heading with workflow name, Context Providers / Capabilities /
   Compaction sections, an X close button top-right).
4. Press the Escape key.
5. Observe the dialog is still present and the page is still dimmed behind it.
6. Repeat steps 2-5 on a second, different card ("Retry Until It Passes" → "Retry Loop" dialog)
   — same result.

### Expected
Pressing Escape while a modal dialog is open should close it, matching standard modal dismissal
behavior and the accessible-dialog convention already used elsewhere in the app.

### Actual
Escape has no effect; the dialog remains open indefinitely until the user explicitly clicks the
"Close" (X) button.

### Evidence
- Before: `bug-hunter/evidence/dashboard/BUG-20260827-221400-dashboard/01-before-inspect-open.png`
- Failure (card 1, "App Builder"): `bug-hunter/evidence/dashboard/BUG-20260827-221400-dashboard/02-escape-pressed-modal-stays-open.png`
- Reproduction on card 2 ("Retry Loop"): `bug-hunter/evidence/dashboard/BUG-20260827-221400-dashboard/03-reproduced-second-card.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no request involved; purely client-side dialog state.
- State/URL: URL stays /dashboard throughout; dialog is a client-rendered overlay, not a route change.

## BUG-20260827-221730-library — Library search with no matches shows a blank page, no empty state

- **Page:** Library (Agents / Skills / Hooks catalog)
- **Route:** /library, /library?tab=skills, /library?tab=hooks
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-27 22:17 UTC
- **Found by:** bug-library-r1
- **Verified:** 2026-08-28 — ran
  `tests/integration/e2e/suites/08_library/test_iss231_search_empty_state.py` (.venv pytest,
  chrome channel, base-url http://localhost:3000): all 3 XPASS(strict) before the xfail markers
  were removed (agents/skills/hooks, 2.2s/2.0s/1.2s), then 3 passed plain-green after removal
  (1.9s/1.3s/0.8s). Re-ran the ORIGINAL reproduction by hand in real Chrome (lane4, qa-admin,
  light theme, cold /library -> /library?tab=skills -> /library?tab=hooks navigations, same
  non-matching queries as the register): Agents shows "No agents match "qqqqnomatch12345"" +
  Clear search, Skills shows "No skills match "zzzznonexistentquery"" + Clear search, Hooks
  shows "No hooks match "xyznohooksmatch999"" + Clear search — all three tabs now render the
  empty state instead of a blank grid. No console errors on any of the three loads. Backend
  /docs -> 200 (no Python touched, no restart needed). `npx tsc --noEmit` in frontend/: same 8
  pre-existing errors in HomeLaunchGrid.crossAccountLeak.test.tsx and listenerMiddleware.test.ts,
  none in LibraryPage.tsx. `npx vitest run src/components/library/LibraryPage.test.tsx`: 9
  passed. `lint-imports` from backend/: 3 kept / 1 broken, identical pre-existing contract break
  (agents.execution_engine -> app.api via kernel_services/revision_analyzer), unrelated to this
  fix. After-screenshots saved next to the original evidence:
  `bug-hunter/evidence/library/BUG-20260827-221730-library/05-after-agents-empty-state.png`,
  `06-after-skills-empty-state.png`, `07-after-hooks-empty-state.png`.
- **Fingerprint:** `/library|search-input|type-nonmatching-query|blank-results-no-empty-state`
- **Evidence:** `bug-hunter/evidence/library/BUG-20260827-221730-library/`
- **Validated:** 3/3 on 2026-08-28, every cycle, cold start (fresh /dashboard -> /library nav
  each time) — Agents tab default route, Skills tab via deep link, Hooks tab via deep link. No
  trigger conditions needed; reproduces unconditionally.
- **Issue card:** [ISS-231](../.knowledge/cards/20260828-1630-ISS-231.md)
- **Root cause:** `LibraryPage.tsx`'s three result grids (Agents/Skills/Hooks) each render via a
  ternary that special-cases only `*Status === "loading"` (lines 732, 793/815, 893/911); every
  other branch falls to a bare `.map()` over the filtered array (`filteredAgents.map` line 735,
  `activeSkills.map` line 818, `filteredHooks.map` line 914) with no `length === 0` case, so an
  empty result — from search, category filter, or a failed fetch — renders nothing at all. The
  header count (line 645/668) is a static unfiltered total, giving no signal a filter even ran.
- **Blast radius:** contained to `frontend/src/components/library/LibraryPage.tsx` — one mount
  point (`DashboardLayout.tsx:10`, `mainView === "library"`), all 3 in-file grids share the flaw
  (matches the hunter's 3/3 repro across tabs). Checked every other search/filter component in
  the frontend (Sidebar, AuditTab, WorkflowPickerModal, DesignSystemPicker, TemplateGallery,
  PPTTemplateGallery, WorkflowHistory, AppBuilderPreview, SavedWorkflowsPage, AgentLibrary,
  AgentsPopup, AgentSkillsPicker) — all already have their own empty-state branch; LibraryPage.tsx
  is the sole outlier (same anti-pattern was fixed once before elsewhere, in `AgentsPopup.tsx`,
  see [FIX-081](../.knowledge/cards/20260721-FIX-081.md)).
- **Proposed fix location:** inside `LibraryPage.tsx`, one local helper called from all 3 grid
  sites (735/818/914), keyed on the filtered array's `length`, not on whether a search string is
  present — no new shared component needed (every sibling component in this codebase already
  solves this locally, and the module's own architecture card documents single-file as
  proportionate here).
- **Issue cards:** [ISS-231](../.knowledge/cards/20260828-1630-ISS-231.md) (root, holds the full
  blast-radius + fix-location analysis), [ISS-335](../.knowledge/cards/20260828-2040-ISS-335.md)
  (sibling, INFERRED: category/event filter alone reaches the same unguarded map, no search text
  needed), [ISS-330](../.knowledge/cards/20260828-2041-ISS-330.md) (sibling, INFERRED: a failed
  agents/skills/hooks fetch renders the identical blank grid with zero error messaging)
- **Fix card:** [FIX-342](../.knowledge/cards/20260828-2238-FIX-342.md) — one local
  `EmptyGridState` (`LibraryPage.tsx:180`) called from a third ternary branch at all three grids
  (`filteredAgents.length === 0` `:805`, `filteredSkills.length === 0` `:891`,
  `filteredHooks.length === 0` `:993`), keyed on the array's length rather than on whether the
  search box holds text, so the category/event-filter path lands there too. Integration test
  `tests/integration/e2e/suites/08_library/test_iss231_search_empty_state.py` — 3 failed, all
  three `[XPASS(strict)]`, i.e. the pass signal (xfail markers left for the verifier); sibling
  `LibraryPage.test.tsx` 9 passed and `LibraryPage.reskin.test.tsx` 5 passed. ISS-335
  (category-only trigger) and ISS-330 (failed fetch, which now reads "No agents found" — wrong
  messaging for an error) were not verified here and stay open.

### Summary
Typing a search term into the library search box (`input[name='library-search']`) that matches
no items produces a completely blank content area below the category pills — no "no results
found" message, no suggestion to clear the search, no icon, nothing. The header text above still
reads "94 agents · 186 skills · 8 hooks · tap any item to see its capabilities" (an unfiltered,
static count), giving no indication that the search actually ran or why the list emptied. A user
cannot tell whether the app is broken, still loading, or genuinely has zero matches. This
reproduces identically on all three tabs (Agents, Skills, Hooks).

### Reproduction
1. Sign in as qa-admin and land on /library (Agents tab, 94 cards visible).
2. Type a non-matching string into the search box, e.g. `qqqqnomatch12345`.
3. Observe: all agent cards disappear, the category pills (All 94, App Builder 15, Retry Loop 0,
   …) remain visible and unchanged, but the area below them is entirely blank — no empty-state
   messaging of any kind.
4. Switch to the Skills tab (`[role="tab"]:nth-child(2)`) with a different non-matching string
   (`zzzznonexistentquery`) — same blank result, same absence of messaging.
5. Switch to the Hooks tab (`[role="tab"]:nth-child(3)`) while the search box still holds a
   non-matching value — same blank result.
6. Clear the search box — cards reappear normally, confirming the filter itself works and this
   is purely a missing-empty-state defect, not a broken search.

### Expected
When a search yields zero results, the page should show an explicit empty state (e.g. "No
agents match 'qqqqnomatch12345'" plus a way to clear the search), consistent with standard list/
search UX and with how the app should communicate a legitimate zero-result state versus a
loading or broken state.

### Actual
The results area renders completely blank with no text, icon, or affordance indicating why, on
all three library tabs.

### Evidence
- Before: `bug-hunter/evidence/library/BUG-20260827-221730-library/01-before-agents-loaded.png`
- Failure (Agents tab): `bug-hunter/evidence/library/BUG-20260827-221730-library/02-failure-agents-no-empty-state.png`
- Reproduced (Skills tab): `bug-hunter/evidence/library/BUG-20260827-221730-library/03-reproduced-skills-tab.png`
- Reproduced (Hooks tab): `bug-hunter/evidence/library/BUG-20260827-221730-library/04-reproduced-hooks-tab.png`

### Browser Signals
- Console: no relevant error observed.
- Network: filtering appears client-side; no failed request observed.
- State/URL: URL stays on the respective `/library` tab throughout; purely a rendering/empty-state gap in the results list component.

## BUG-20260827-222300-settings-profile — Password-mismatch error does not clear when the fields are corrected to match

- **Page:** Settings · Profile (Account Settings)
- **Route:** /settings/profile
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-27 22:23 UTC
- **Found by:** bug-settings-profile-r1
- **Fingerprint:** `/settings/profile|change-password-form|edit-confirm-field-after-mismatch-submit|stale-do-not-match-error-persists`
- **Evidence:** `bug-hunter/evidence/settings-profile/BUG-20260827-222300-settings-profile/`
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced on every cold-start cycle (fresh
  `/dashboard` -> `/settings/profile` nav each time), including one cycle typed via
  `pressSequentially` to rule out an event-wiring artifact. No narrowing needed.
- **Root cause:** `message` state (`AccountSettings.tsx:99`) is written only inside
  `handleChangePassword` (`AccountSettings.tsx:148-174`, mismatch branch at `:158-159`); the
  Current/New/Confirm password `onChange` handlers (`AccountSettings.tsx:284,296,307`) update
  only their own field and never call `setMessage(null)` or re-validate, so any banner set at
  submit time — success or error — survives every later edit until the next submit click.
  CONFIRMED by direct read of the cited lines.
- **Blast radius:** No shared function is called elsewhere — this is a component-local
  anti-pattern, not a shared-code defect. Grepped the whole frontend for every password-match
  check (`do not match` / `confirmPassword` / `ConfirmPassword`): exactly 2 hits exist.
  `AccountSettings.tsx` (this report) is one; `frontend/src/app/login/page.tsx`'s `ChallengeForm`
  (Cognito `NEW_PASSWORD_REQUIRED` step) independently reimplements the identical shape — its
  `error` state is written only inside `handleChangePassword`'s sibling `handleChallengeSubmit`
  (`login/page.tsx:98-121`, mismatch branch `"Passwords do not match."` at `:105-108`) and never
  cleared by any of its 4 field `onChange`s (`:453,469,495,514`). No third instance exists.
- **Fix location:** Belongs in each component's own field `onChange` handlers (or a shared
  "clear validation message on edit" hook introduced to cover both at once) — `AccountSettings.tsx`
  and `login/page.tsx` are separate component trees with separate state, so one shared-function
  guard cannot reach both; two call sites need the fix (or one shared hook both adopt).
- **Issue cards:** [ISS-244](../.knowledge/cards/20260828-1634-ISS-244.md) (root, CONFIRMED),
  [ISS-342](../.knowledge/cards/20260828-2059-ISS-342.md) (sibling: login.tsx ChallengeForm,
  INFERRED — unreproduced, same mechanism confirmed by code read only)
- **Fix card:** [FIX-341](../.knowledge/cards/20260828-2236-FIX-341.md) — `setMessage(null)` now
  runs in all three password `onChange` handlers (`AccountSettings.tsx:284,296,307`), so the
  submit-time banner cannot outlive the field values it asserts. Frontend test:
  `AccountSettings.password-mismatch.test.tsx` — `it.fails()` now reports "Expect test to fail"
  = 1 failed, i.e. the XPASS pass signal (marker left in place for the verifier); sibling
  `AccountSettings.render.test.tsx` 8 passed and `AccountSettings.test.tsx` 4 passed. ISS-342
  (login `ChallengeForm`) is a different file, outside ISS-244's globs, and stays open.
- **Verified:** `AccountSettings.password-mismatch.test.tsx` re-run — XPASS confirmed
  ("Error: Expect test to fail" = 1 failed, the pass signal), then `it.fails` marker removed and
  re-run for a plain green (1 passed). Regression files re-run clean:
  `AccountSettings.render.test.tsx` 8 passed, `AccountSettings.test.tsx` 4 passed. Manual repro
  by hand in Chrome (lane5) as qa-admin on `/settings/profile`: submitted New=`SecondTry999` /
  Confirm=`DifferentValue1`, "New passwords do not match" appeared; edited Confirm only to
  `SecondTry999` (DOM read confirmed both password fields byte-identical) and the banner cleared
  immediately, no submit click needed. No console errors on the page. `npx tsc --noEmit` clean
  for `AccountSettings.tsx` and the test file (pre-existing unrelated errors in
  `HomeLaunchGrid.crossAccountLeak.test.tsx` / `listenerMiddleware.test.ts` from other in-flight
  work, not touched by this fix). Backend `:8000/docs` and frontend `:3000` both 200
  (frontend-only fix, no restart needed). `lint-imports` (run from `backend/`) shows 1
  pre-existing broken contract (`agents.execution_engine.engine` -> `app.api`, kernel-layering)
  unrelated to this change — not touched here. Evidence:
  `bug-hunter/evidence/settings-profile/BUG-20260827-222300-settings-profile/04-after-fix-mismatch-shown.png`,
  `05-after-fix-banner-cleared.png`.

### Summary
On the Password card of /settings/profile, entering a New password and a Confirm new password
that differ and clicking "Change Password" correctly shows a client-side "New passwords do not
match" error (no network request fires — this validation is a good, working guard). However, if
the user then edits the Confirm field so it becomes byte-for-byte identical to the New password
field, the "New passwords do not match" message is never cleared. It remains on screen
indefinitely (verified via reading both `input[type=password]` DOM values directly — they are
identical) even though the stated condition for the error is no longer true. The error is only
ever computed at submit time, not reactively on input change, so once shown it is permanently
stale until the next submit click. A user who fixes their typo has no way to know, short of
clicking submit again, whether the form actually agrees with them.

### Reproduction
1. Sign in as qa-admin, land on /dashboard, navigate to /settings/profile.
2. In the Password card, fill Current password with the real current password, New password
   with `SecondTry999`, Confirm new password with a different value `DifferentValue1`.
3. Click "Change Password". Observe the error "New passwords do not match" appears (correct,
   expected behavior at this point).
4. Without touching New password, edit Confirm new password to `SecondTry999` (now identical to
   New password).
5. Observe: the "New passwords do not match" error is STILL displayed, unchanged, even though
   `document.querySelectorAll('input[type=password]')` confirms both the New and Confirm fields
   now hold the exact same string.
6. Reload and repeat with a different pair of values (`NewPass1234`/mismatch → corrected to
   match) — same result: the stale error persists after the fields are made to agree.

### Expected
Either the mismatch error should re-evaluate reactively as the user types (clearing as soon as
the fields agree), or at minimum should be cleared/hidden once the Confirm field is edited, so
the displayed validation state always reflects the current field contents.

### Actual
The error message is computed once, at the moment "Change Password" is clicked, and is never
recomputed or cleared on subsequent edits to the fields — it stays on screen showing a mismatch
that no longer exists until the user clicks submit again.

### Evidence
- Before: `bug-hunter/evidence/settings-profile/BUG-20260827-222300-settings-profile/01-before-fields-empty.png`
- Failure (repro 1): `bug-hunter/evidence/settings-profile/BUG-20260827-222300-settings-profile/02-failure-stale-error-repro1.png`
- Failure (repro 2, fresh reload, different values): `bug-hunter/evidence/settings-profile/BUG-20260827-222300-settings-profile/03-failure-stale-error-repro2.png`

### Browser Signals
- Console: no relevant error observed for this defect (a separate, unrelated 401/501 console
  error pair appears only when a wrong *current* password is submitted — not part of this bug).
- Network: no additional request fires between the initial failed submit and the field edit; the
  error is pure client-side state that is never invalidated.
- State/URL: URL stays on /settings/profile throughout; confirmed via direct DOM `value` reads
  that the two password fields are identical while the "do not match" message is still shown.

## BUG-20260827-222750-login — Sign in button is not disabled during the login request, allowing duplicate submissions

- **Page:** Login (sign-in form)
- **Route:** /login
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-27 22:27 UTC
- **Found by:** bug-login-r1
- **Fingerprint:** `/login|sign-in-button|rapid-repeated-click-with-valid-credentials|duplicate-login-requests-fired`
- **Evidence:** `bug-hunter/evidence/login/BUG-20260827-222750-login/`
- **Validated:** 3/3 on 2026-08-28, cycle 1 — synchronous rapid triple-click reproduces every
  cold-start cycle (cleared localStorage, fresh nav to /login); `disabled={isLoading}` never
  gates the click because React's state commit lands after the synchronous clicks, not before.
- **Issue card:** [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md)
- **Root cause (CONFIRMED, `frontend/src/app/login/page.tsx:76-93,306-313`):** the only guard on
  the Sign-in submit is `disabled={isLoading}`, a React-state prop; `setIsLoading(true)` is a
  state update, not a synchronous DOM mutation, so the button's real `disabled` attribute does
  not flip until React commits — a tick later than a same-task synchronous click. Any click that
  lands in that pre-commit window independently re-invokes `handleSubmit`, each firing its own
  `POST /api/auth/login`. There is no `useRef` (or other synchronous) lock closing the window.
- **Blast radius:** grepped every caller of `login()` and `respondToLoginChallenge()`
  (`frontend/src/lib/api.ts`) across `frontend/src/` — exactly one caller each, both in this same
  file, so the broken function itself has no other consumer. The FLAW (a mutating submit gated
  only by a React state `disabled` prop, no ref-based synchronous guard) independently recurs by
  the same code shape on 3 other controls read and confirmed during analysis: `ChallengeForm`'s
  Continue button (same file, `handleChallengeSubmit`), Composer's Save button
  (`ComposerPage.tsx` `handleSave` — worse consequence: persists a duplicate workflow row, not
  just a duplicate request), and Account Settings' email-MFA toggle (`SecuritySection.tsx`
  `toggleEmailMfa` — worse consequence: an out-of-order response can leave displayed MFA state
  wrong). Filed as siblings, all INFERRED pending their own reproduction.
- **Proposed fix — where it belongs:** a synchronous `useRef<boolean>` guard
  (check-and-set before `setIsLoading(true)`, cleared in `finally`) added directly inside
  `handleSubmit` AND `handleChallengeSubmit` in `frontend/src/app/login/page.tsx` — both handlers
  funnel every click for their respective forms, so the guard belongs there, not per-caller (there
  is only one caller of each). The 3 sibling components need the identical local guard in their
  own handlers; there is no shared submit hook in this codebase to centralize it in instead.
- **Fixed:** 2026-08-28 by 5-fixer. `frontend/src/app/login/page.tsx` only — a synchronous
  `submittingRef` check-and-set now gates `handleSubmit` (after `e.preventDefault()`, before
  `setIsLoading(true)`) and `handleChallengeSubmit` (after its validation early-returns, so a
  validation failure cannot latch the ref), both cleared in the existing `finally` beside
  `setIsLoading(false)`. `disabled={isLoading}` is kept for the visible pending label; the ref
  carries the correctness, because a ref mutates synchronously and a state commit does not.
  Tests: `tests/integration/e2e/suites/01_auth/test_auth.py` → 1 failed, 16 passed, 9 skipped
  in 41.41s, the one failure being `[XPASS(strict)] ISS-245 unfixed` on
  `test_rapid_repeated_clicks_on_sign_in_fire_only_one_login_request` — the strict-xfail pass
  signal; marker left in place for the verifier. The 9 skips are every ChallengeForm scenario
  ("fixture: no account parked in a Cognito challenge state") — pre-existing, so the
  `handleChallengeSubmit` half of the guard has no test behind it.
  `frontend/src/app/login/login.reskin.test.tsx`
  9/9 green (vitest). `npx tsc --noEmit` shows only the pre-existing HomeLaunchGrid/
  listenerMiddleware test-type errors, neither file touched here. Frontend-only: no backend
  restart needed, no migration, no engine or import-linter surface involved.
- **Fix card:** [FIX-345](../.knowledge/cards/20260828-2250-FIX-345.md) — resolves
  [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md) (status: resolved,
  verification: passed). The same edit also closes the code gap behind
  [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md) (ChallengeForm Continue, same file,
  named in ISS-245's own proposed fix); ISS-352 stays `open` because it was never reproduced
  and carries no test of its own. [ISS-353](../.knowledge/cards/20260828-2102-ISS-353.md)
  (Composer Save) and [ISS-354](../.knowledge/cards/20260828-2103-ISS-354.md) (Settings MFA
  toggle) live in other files and are UNTOUCHED — still open.
- **Issue cards:** [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md) (root),
  [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md) (sibling: ChallengeForm Continue
  button), [ISS-353](../.knowledge/cards/20260828-2102-ISS-353.md) (sibling: Composer Save
  button), [ISS-354](../.knowledge/cards/20260828-2103-ISS-354.md) (sibling: Account Settings
  MFA toggle)
- **Verified:** 2026-08-28 by 6-verifier. `tests/integration/e2e/suites/01_auth/test_auth.py`:
  `test_rapid_repeated_clicks_on_sign_in_fire_only_one_login_request` ran XPASS(strict)
  pre-fix-confirmation (1 failed, 16 passed, 9 skipped), `xfail` marker removed (`@pytest.mark.issue`
  kept), re-run plain green (17 passed, 9 skipped, 0 failed). `frontend/src/app/login/login.reskin.test.tsx`
  9/9 green (vitest). Manual re-run of the original register repro in real Chrome (lane6, qa-admin,
  cold nav, `localStorage.clear()` then fresh `/login`): instrumented `window.fetch` and triple-clicked
  the "Sign in" button synchronously (same technique the hunter used) — exactly 1 `POST /api/auth/login`
  fired (confirmed independently via `browser_network_requests`), landed cleanly on `/dashboard`, no
  new console errors. Health: backend `/docs` 200 (frontend-only fix, no restart needed); `npx tsc
  --noEmit` shows only the pre-existing `HomeLaunchGrid.crossAccountLeak.test.tsx`/`listenerMiddleware.test.ts`
  errors, neither touched here; `lint-imports` (run from `backend/`) shows the one pre-existing
  `kernel imports only capability ports` break, confirmed unrelated (this fix is frontend-only, no
  backend diff). Evidence: `bug-hunter/evidence/login/BUG-20260827-222750-login/04-after-fix-verified-single-login-request.png`.

### Summary
On the sign-in form, filling in valid credentials and clicking "Sign in" multiple times in
rapid succession (e.g. a fast triple click, or any repeat click before the async login request
resolves) fires one `POST /api/auth/login` request per click instead of being debounced to a
single request. The button never enters a `disabled` state and its label never changes to a
pending/loading state (verified via direct DOM reads of `button.disabled` and
`button.textContent` immediately before and after a synchronous triple click) — it stays exactly
"Sign in", fully clickable, for the entire duration of the pending request(s). This lets a user
accidentally send several concurrent authentication requests from one interaction.

### Reproduction
1. Ensure signed out: `localStorage.clear()` then navigate to /login.
2. Fill `input[type="email"]` with `qa-admin@flowinqa.com` and `input[type="password"]` with
   `flowin-e2e-pass` (valid credentials).
3. Programmatically click the "Sign in" button three times back-to-back with no delay between
   clicks (simulating a fast repeated/rapid click).
4. Inspect the network log filtered to `auth/login` — observe THREE separate
   `POST http://localhost:8000/api/auth/login` requests, each returning `200 OK`, instead of one.
5. Inspect `button.disabled` and `button.textContent` captured immediately before and
   immediately after the three clicks — both are unchanged (`disabled: false`,
   `text: "Sign in"`) at every point, confirming the button never disables or shows a pending
   state to prevent the extra clicks.
6. Reload, clear `localStorage`, and repeat steps 1-5 with different fresh state — same result:
   three duplicate `POST /api/auth/login` requests fire, all succeeding.

### Expected
The "Sign in" button should disable itself (and/or show a loading state) the instant the first
click starts the login request, so additional clicks before the response arrives are ignored and
at most one login request is sent per submission attempt.

### Actual
The button remains fully enabled and visually unchanged throughout the pending request, so every
extra click before the response returns fires its own independent `POST /api/auth/login` request.

### Evidence
- Before (form filled, not yet submitted): `bug-hunter/evidence/login/BUG-20260827-222750-login/01-before-filled-form.png`
- After (triple click resolved, landed on /dashboard): `bug-hunter/evidence/login/BUG-20260827-222750-login/02-after-triple-click-lands-dashboard.png`
- Network log excerpt: `bug-hunter/evidence/login/BUG-20260827-222750-login/network.log`

### Browser Signals
- Console: no relevant error observed.
- Network: three `POST /api/auth/login` requests fired from a single triple-click interaction,
  all `200 OK` (see network.log).
- State/URL: ends on /dashboard as expected once the (last) login response resolves; the
  duplication is in the number of requests fired, not the final navigation outcome.

## BUG-20260827-223300-login-expired-true — An already-authenticated user landing on /login is shown the sign-in form instead of being redirected to /dashboard

- **Page:** Login (session-expired variant)
- **Route:** /login?expired=true (also reproduces on plain /login)
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28 by 6-verifier. `tests/integration/e2e/suites/01_auth/test_auth.py`
  ran XPASS(strict) on both ISS-191 cases pre-fix-confirmation, `xfail` markers removed,
  re-run plain green (25 collected, all pass/skip, 0 fail). `frontend/src/app/login/login.reskin.test.tsx`
  9/9 green (vitest). Manual re-run of the original register repro in real Chrome
  (qa-admin, cold nav): corrupt-token -> 401 auto-redirect to `/login?expired=true` ->
  sign back in -> Back-navigation stays on `/dashboard` (no form flash) -> fresh direct
  nav to `/login?expired=true` settles on `/dashboard` -> fresh direct nav to plain
  `/login` settles on `/dashboard` -> `/register` hop (ISS-193) settles on `/dashboard`
  too. No console errors on the affected page. `npx tsc --noEmit` and `lint-imports`
  (run from `backend/`) both show pre-existing, unrelated failures only (HomeLaunchGrid/
  listenerMiddleware test-type errors, the documented kernel/app.api contract break from
  FIX-224's history) — none touch `frontend/src/app/login/page.tsx`. Evidence:
  `bug-hunter/evidence/login-expired-true/BUG-20260827-223300-login-expired-true/04-after-fix-verified-redirects-to-dashboard.png`.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduces on fresh cold-start navigation to /login?expired=true or plain /login while authenticated, no timing dependency
- **Root cause:** `frontend/src/app/login/page.tsx`'s `LoginForm` never imports or calls
  `useEffect` — no mount-time check for an existing `auth_token` exists before it renders
  the sign-in form unconditionally (CONFIRMED, full-file read). The inverse guard already
  exists elsewhere (`frontend/src/app/page.tsx:9-18` for `/`, `[...view]/page.tsx:805-811`
  for every protected screen) — only `/login`'s own "already signed in" case was never
  built.
- **Blast radius:** every code path that can land a browser on `/login` funnels through
  this one broken render — direct nav, Back-navigation (both already validated), and
  `frontend/src/app/register/page.tsx:12`, which redirects to `/login` unconditionally
  with no `getToken()` check (CONFIRMED read), unlike every other login-redirect call site
  in the codebase (`admin/page.tsx`, `handoff/settings/page.tsx`, `HandoffWorkflow.tsx`,
  `LaunchWizard.tsx`, `[...view]/page.tsx`, all of which gate on `!token` first).
- **Proposed fix:** add a mount-time `useEffect` in `LoginForm` (`frontend/src/app/login/page.tsx`)
  that calls `getToken()` and, if present, `router.replace(resolveRedirectTarget(searchParams.get("redirect")))`
  — reusing the file's own existing `goToDestination()`/`resolveRedirectTarget` primitives
  — gated behind a `checked` render-state (`handoff/settings/page.tsx`'s `authed` pattern)
  so the form does not flash before redirecting. Single-file fix; no shared hook needed,
  matching this codebase's existing per-page auth-check convention.
- **Issue cards:** [ISS-191](../.knowledge/cards/20260828-1330-ISS-191.md) (root — CONFIRMED
  root cause + blast radius + proposed fix), [ISS-193](../.knowledge/cards/20260828-1554-ISS-193.md)
  (sibling, INFERRED/unreproduced: an authenticated user on the literal `/register` route
  is bounced into this same missing-guard `/login` page)
- **Fix card:** [FIX-323](../.knowledge/cards/20260828-1629-FIX-323.md) — mount-time
  `getToken()` guard + `checked` render gate in `frontend/src/app/login/page.tsx`;
  ISS-191 and ISS-193 both resolved by that single file, no `register/page.tsx` change
- **Found at:** 2026-08-27 22:33 UTC
- **Found by:** bug-login-expired-true-r1
- **Fingerprint:** `/login|auth-guard|navigate-to-login-while-authenticated|login-form-shown-instead-of-redirect`
- **Evidence:** `bug-hunter/evidence/login-expired-true/BUG-20260827-223300-login-expired-true/`

### Summary
There is no client-side redirect guard on the login route for an already-authenticated user.
After a genuine session-expiry-and-recovery cycle (corrupt the stored token so a protected route
401s and the app auto-redirects to `/login?expired=true`, then sign back in successfully and land
on `/dashboard` with a real, working JWT in `auth_token`), returning to `/login?expired=true` —
either via the browser Back button or by navigating there directly while the valid token is still
in `localStorage` — renders the full sign-in form and the stale "Your session expired. Please
sign in again." banner instead of redirecting to `/dashboard`. The session is not actually
expired: `GET /api/runs?limit=50` made from that same page load returns `200 OK`, proving the
token is valid and the app has functioning credentials, yet the UI insists the user needs to sign
in again. This is not specific to the `expired=true` query variant — plain `/login` (no query
string) shows the identical failure for the same authenticated user in the same session, meaning
the login route has no "already signed in, skip the form" guard at all.

### Reproduction
1. Sign in as qa-admin, confirm `localStorage.getItem('auth_token')` is set, navigate to a
   protected route such as `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e`.
2. Overwrite the token to force an auth failure:
   `localStorage.setItem('auth_token', 'corrupted.invalid.token')`, then reload/navigate to the
   same protected route. The app's 401 ladder auto-redirects to `/login?expired=true`.
3. Fill valid credentials (`qa-admin@flowinqa.com` / `flowin-e2e-pass`) and click "Sign in".
   Observe a successful login: URL becomes `/dashboard`, a real JWT is now in `auth_token`.
4. Press the browser Back button. Observe: URL returns to `/login?expired=true`, but instead of
   immediately bouncing back to `/dashboard` (since the user is authenticated), the full sign-in
   form and the stale "session expired" banner are rendered and stay rendered (confirmed after a
   2s wait — no async redirect ever fires).
5. Separately, from `/dashboard` (still authenticated, token still valid), navigate directly to
   `http://localhost:3000/login?expired=true` via the address bar. Same result: sign-in form
   renders, no redirect to `/dashboard`, despite `GET /api/runs?limit=50` in that page load
   returning `200 OK` — proof the session is genuinely valid.
6. Repeat step 5 against plain `http://localhost:3000/login` (no query string) while still
   authenticated — identical failure: sign-in form renders instead of a redirect.

### Expected
An authenticated user (valid `auth_token`, working API session) who lands on `/login` or
`/login?expired=true` — by any navigation path — should be immediately redirected to
`/dashboard`, not shown the sign-in form. This is standard behavior for an auth page and is what
the app itself relies on to route a signed-out user (`/` → `/login` when no token, `/` →
`/dashboard` when a token exists per the `C-3` quirk); the inverse guard (signed-in user hitting
`/login`) is missing entirely.

### Actual
The login route renders the sign-in form and the (now factually incorrect) "session expired"
banner for a fully authenticated user with a verified-working token, with no redirect ever
firing, regardless of whether `/login` is reached via Back navigation or a fresh direct
navigation.

### Evidence
- Before (signed in, landed on /dashboard after successful login): `bug-hunter/evidence/login-expired-true/BUG-20260827-223300-login-expired-true/01-before-signed-in-on-dashboard.png`
- Failure (Back navigation to /login?expired=true while authenticated): `bug-hunter/evidence/login-expired-true/BUG-20260827-223300-login-expired-true/02-failure-back-nav-shows-login-form.png`
- Failure (fresh direct navigation to /login?expired=true while authenticated, /api/runs returns 200): `bug-hunter/evidence/login-expired-true/BUG-20260827-223300-login-expired-true/03-repro-direct-nav-authenticated.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs?limit=50` returns `200 OK` on the same page load that renders the
  sign-in form, confirming the session is valid and the failure is a missing client-side redirect
  guard, not an actual auth failure.
- State/URL: URL stays on `/login` (or `/login?expired=true`) indefinitely; `auth_token` in
  `localStorage` remains the valid JWT from the prior successful login throughout.

## BUG-20260827-231407-register — For an authenticated user, unmatched `/register/<sub-path>` URLs silently render the Dashboard instead of a 404 or a redirect

- **Page:** Register (redirect stub) — unmatched sub-routes
- **Route:** /register/anything, /register/abc123xyz (any nonexistent sub-path under /register)
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-28 (lane4). `frontend/src/lib/routes.test.ts` re-run: XPASS
  confirmed (`it.fails` reported "Expect test to fail" — 1 failed/58 passed), marker
  removed and re-run plain green (59/59). Manual repro re-driven in real Chrome as
  qa-admin (authenticated): `/register/anything` and `/register/abc123xyz` now both
  render an actual "Not found" page with `location.href` staying on the bogus URL
  (no dashboard fallthrough), no console errors. Exact `/register` (authenticated)
  still redirects to `/dashboard`, unaffected (regression check). `npx tsc --noEmit`
  clean on routes.ts/routes.test.ts. Backend `:8000/docs` → 200 (frontend-only change,
  no restart required). Regression file `suites/01_auth/test_auth.py` — 17 scenarios,
  all PASS including S-01-08 (register redirect stub). Evidence:
  `bug-hunter/evidence/register/BUG-20260827-231407-register/04-verified-fix-notfound-anything.png`.
  ISS-348/ISS-349/ISS-350 (login/admin/analytics siblings) remain open, unaffected by
  this fix — not in scope for this bug's card set.
- **Validated:** 3/3 on 2026-08-28, cold start each cycle (`/register/anything`,
  `/register/abc123xyz`, `/register/deep/nested/path`) — no axis variation needed; the
  trigger is simply authenticated + any `/register/<extra-segment(s)>` URL. Root cause:
  `routes.ts:219` `head === 'register'` matches any depth, and `[...view]/page.tsx` has
  no branch for `screen: 'register'`, so it falls through to the default dashboard render.
- **Root cause:** `frontend/src/lib/routes.ts:231-233` — the `register` branch of
  `parseViewPath` matches `head === 'register'` alone with no `segments.length === 1` guard
  (unlike the sibling `create`/`workflows`/`runs`/`library`/`settings` branches, which all
  check it), so `parseViewPath(['register', <anything>])` returns `{screen: 'register'}` for
  any depth. `frontend/src/app/[...view]/page.tsx` has zero branches anywhere checking
  `parsedView.screen === "register"` (confirmed by grep), so it never reaches the file's one
  hard-404 gate, `if (parsedView.screen === "unknown") { notFound(); }` at line 3724.
  `initialMainViewFor` (page.tsx:107-174) has no `case "register":` and falls to
  `default: return undefined;` (line 171-172); that `undefined` becomes the `initialMainView`
  prop DashboardLayout receives, and `DashboardLayout.tsx:515-530`'s `useState<MainView>`
  initializer defaults to `return "home";` when `initialMainView` is falsy and no
  wizard-pending sessionStorage flag is set — the exact line that renders dashboard content
  under the bogus URL. CONFIRMED by reading all three files directly.
- **Blast radius:** `parseViewPath` (routes.ts) is called from `[...view]/page.tsx` (the sole
  render consumer), `error.tsx`/`global-error.tsx` (error-boundary screen-label telemetry
  only), and `LibraryPage.tsx` (its own scoped call). The identical missing-depth-guard shape
  also exists on the `login` (routes.ts:224-229) and `admin` (routes.ts:423-425) branches —
  both have zero branches in page.tsx either (grep-confirmed), so `/login/<sub-path>` and
  `/admin/<sub-path>` authenticated fall through to the dashboard via the exact same mechanism
  (INFERRED, not yet reproduced — see ISS-348/ISS-349). The `analytics` branch
  (routes.ts:418-420) has the same missing guard but page.tsx DOES have an explicit
  `initialMainViewFor` case for it, so a bogus `/analytics/<sub-path>` renders the real
  Analytics page instead of the dashboard (INFERRED — see ISS-350). Nothing else in the
  frontend reads these screen discriminants (`grep -rn 'screen === "register"' frontend/src`
  and the login/admin/analytics equivalents all return zero hits outside `routes.ts`/`page.tsx`
  itself), so the fix is fully contained to `parseViewPath`.
- **Proposed fix:** add the same `segments.length === 1` guard already used by
  `create`/`workflows`/`runs`/`library`/`settings` to the `register`, `login`, and `admin`
  branches in `parseViewPath` (`routes.ts`), falling through to the function's existing
  `{screen: 'unknown'}` return otherwise — this is the single shared function every caller
  routes through, so one guard there (not a patch in `page.tsx` or `DashboardLayout.tsx`) fixes
  all three, and the existing `screen === "unknown"` → `notFound()` gate at page.tsx:3724
  handles the 404 with no new page-component branch needed. `analytics` has the same parser
  flaw but a milder consequence (a real screen renders, not the dashboard) — worth the same
  guard for consistency with ADR-0018, but is a product call rather than a hard defect.
- **Issue cards:** [ISS-238](../.knowledge/cards/20260828-1633-ISS-238.md) (root — `/register/<sub-path>`, CONFIRMED),
  [ISS-348](../.knowledge/cards/20260828-2102-ISS-348.md) (sibling: `/login/<sub-path>`, INFERRED),
  [ISS-349](../.knowledge/cards/20260828-2102-ISS-349.md) (sibling: `/admin/<sub-path>`, INFERRED),
  [ISS-350](../.knowledge/cards/20260828-2102-ISS-350.md) (sibling: `/analytics/<sub-path>` renders the wrong-but-real screen, INFERRED)
- **Fix card:** [FIX-344](../.knowledge/cards/20260828-2046-FIX-344.md) — one conjunct on the
  `register` branch of `parseViewPath` (`frontend/src/lib/routes.ts:231-236`,
  `head === 'register' && segments.length === 1`), so `/register/<sub-path>` falls through to
  the function's terminal `{ screen: 'unknown' }` and `page.tsx:3724`'s existing `notFound()`
  gate — no branch added to `page.tsx` or `DashboardLayout.tsx`. Frontend test
  `frontend/src/lib/routes.test.ts` — 59 tests, 1 failed / 58 passed; the one failure is the
  `it.fails('ISS-238: …')` case reporting "Expect test to fail", i.e. vitest's XPASS and the
  pass signal (marker left in place for the verifier). `npx tsc --noEmit` clean on routes.ts.
  ISS-348 / ISS-349 / ISS-350 (login, admin, analytics — same missing guard, all INFERRED,
  no tests, not in this fixer's card set) are deliberately LEFT OPEN; any fix for them edits
  this same file and must be serialized against FIX-344.
- **Found at:** 2026-08-27 23:14 UTC
- **Found by:** bug-register-r1
- **Fingerprint:** `/register/<sub-path>|route-resolution|authenticated-user-navigates-to-unmatched-register-subroute|url-shows-register-subpath-but-dashboard-content-renders`
- **Evidence:** `bug-hunter/evidence/register/BUG-20260827-231407-register/`, validator
  scratch: `bug-hunter/evidence/register/_scratch/`

### Summary
`/register` itself is a known, intentional redirect stub (out of scope here). But a nonexistent
sub-path under it, e.g. `/register/anything`, is a different code path entirely — for a
signed-out user it correctly falls through to `/login?redirect=%2Fregister%2Fanything` (an app
auth-guard behavior, not the register stub's own `router.replace('/login')`). For an
**authenticated** user, however, that same unmatched sub-path does not redirect and does not
404: the browser address bar stays on `/register/anything` (or any other nonexistent sub-path)
while the app fully renders the authenticated `/dashboard` catalog — workflow cards, "Jump back
in" run history, header nav with "Home" highlighted active — as if the URL were `/dashboard`.
This reproduces on a genuine hard/full-page navigation (not just client-side routing residue),
confirmed via `location.href` still reading the `/register/...` path while `document.title`,
`h1` text, and live API calls (`/api/runs`, `/api/workflows`, `/api/analytics/summary`, etc.,
all 200 OK) match the dashboard exactly. Distinct from D-03 (`?expired=1` no-op), D-25 (dead
validation code) and D-34 (logout 401) — none of which concern route resolution for unmatched
paths under `/register`. Also distinct from the ledger's existing
`BUG-20260827-223300-login-expired-true` (which is about the `/login` route failing to redirect
an authenticated user away from the sign-in form) — here the URL is `/register/...`, no sign-in
form is ever shown, and the failure is that the wrong page's content silently renders under the
wrong URL rather than the app failing to leave a login screen.

### Reproduction
1. Sign in as qa-admin (`localStorage.getItem('auth_token')` is set), confirm landing on
   `/dashboard`.
2. Navigate directly (full `page.goto`, real navigation) to `http://localhost:3000/register/anything`.
3. Observe: the address bar stays on `/register/anything`, but the rendered page is the full
   authenticated dashboard — heading "What would you like to build today?", the workflow catalog
   cards, header with "Home" nav active, "Jump back in" run history — identical to `/dashboard`.
4. Confirm via `location.href` (still `/register/anything`) and `document.querySelector('h1').textContent`
   (`"What would you like to build today?"`) that this is not a stale screenshot artifact.
5. Repeat with a second, different nonexistent sub-path, `http://localhost:3000/register/abc123xyz`
   — same result: URL stays on the bogus `/register/...` path, dashboard content renders.
6. For contrast, sign out (`localStorage.clear()`) and repeat step 2 — the unauthenticated case
   correctly falls through to `/login?redirect=%2Fregister%2Fanything`, confirming the defect is
   specific to the authenticated path through this route.

### Expected
An authenticated user hitting a nonexistent sub-path under `/register` should either receive a
proper 404/not-found page, or be redirected to a real destination (e.g. `/dashboard` via an
actual navigation/redirect, or back to `/register` itself) — with the URL and rendered content
agreeing with each other in either case.

### Actual
The URL bar permanently displays the bogus, nonexistent `/register/<sub-path>` while the
dashboard is fully rendered underneath it — an authenticated-only URL/content mismatch that
persists across hard reloads and is stable, not a transient loading flash.

### Evidence
- After login redirect lands here: `bug-hunter/evidence/register/BUG-20260827-231407-register/01-after-login-redirect-url-mismatch.png`
- Fresh hard reload, still mismatched: `bug-hunter/evidence/register/BUG-20260827-231407-register/02-fresh-hard-reload-still-dashboard.png`
- Second sub-path repro: `bug-hunter/evidence/register/BUG-20260827-231407-register/03-repro2-different-subpath.png`

### Browser Signals
- Console: no errors; only routine HMR/devtools info logs.
- Network: dashboard-only API calls (`/api/runs`, `/api/auth/me`, `/api/workflows`,
  `/api/analytics/summary`, `/api/agents/library`, `/api/skills/library`, `/api/hooks/library`)
  all return 200 OK on this URL, confirming the dashboard is genuinely rendering, not just a
  stale DOM.
- State/URL: `location.href` remains the nonexistent `/register/<sub-path>` throughout; no
  navigation event ever corrects it while authenticated.

## BUG-20260827-232305-root — Browser Back to `/` after the corrupt-token auth bounce leaves the app permanently blank instead of redirecting to `/login`

- **Page:** Root entry point (redirect stub)
- **Route:** `/`
- **Severity:** Medium
- **Status:** DUPLICATE
- **Duplicate of:** [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md) — validated 3/3 on 2026-08-28 (cycle 3 landed on `/dashboard` instead of `/` due to an extra history entry from a fresh login redirect, but the blank-body / `navType: back_forward` / `transferSize: 0` / no-hydration signature was identical in all three cycles); ISS-217 already documents this exact mechanism (React never hydrates on a `back_forward` navigation replay when bfcache is unavailable) reproducing on every route including `/login`, which has no auth gate at all — so this bug's `/` case is not a distinct defect, just another route hitting the same cause.
- **Found at:** 2026-08-27 23:23 UTC
- **Found by:** bug-root-r1
- **Fingerprint:** `/|root-redirect|browser-back-after-corrupt-token-bounce-chain|blank-page-stuck-forever-no-redirect`
- **Evidence:** `bug-hunter/evidence/root/BUG-20260827-232305-root/`

### Summary
Empirical check of the two conflicting docs (the `velocity.json` quirk claiming `/` unconditionally
redirects to `/login`, vs. `DEFECTS-OBSERVED.md` correction C-3 claiming it branches on token
presence): C-3 is correct — `/` reliably branches (`/dashboard` when a token exists, `/login` when
it does not) via a client-side `router.replace`, confirmed in both auth states, with no extra
history entry added (replace, not push) across many repeated fresh navigations. However, one
specific navigation path breaks this: after an invalid/corrupt token causes the app's normal
401-recovery bounce (`/` → `/dashboard` (401) → `/login?expired=true`, which also clears the bad
token from `localStorage`), pressing the browser **Back** button returns to the original `/` URL
via a genuine full network reload (`GET / => 200`, all JS chunks re-fetched, not a bfcache
restore) — but the client redirect logic never fires. The page renders a completely empty
`<body>` (0 characters of text, an untouched React root) and stays that way indefinitely (verified
at events out to 5+ seconds); `location.href` remains `/` and `localStorage.getItem('auth_token')`
is confirmed `null`, so the app has every fact it needs to redirect to `/login` and simply doesn't.
No console error is logged. A manual `location.reload()` on the exact same stuck URL immediately
and correctly redirects to `/login`, proving the redirect logic itself works and this is
specifically a Back-navigation trigger gap, not the C-3-corrected core behavior being wrong.

### Reproduction
1. Sign in as qa-admin, land on `/dashboard` (real, valid `auth_token` in `localStorage`).
2. Corrupt the token: `localStorage.setItem('auth_token', 'corrupted.invalid.token')`.
3. Navigate to `http://localhost:3000/` (a real, fresh navigation). Observe the app's normal
   bounce: `/` → briefly resolves `/dashboard` → `GET /api/runs` and `POST /api/auth/refresh`
   both `401` → lands on `/login?expired=true` with the session-expired banner, and the bad token
   is cleared from `localStorage` (confirmed `null`).
4. Press the browser **Back** button.
5. Observe: the URL becomes `http://localhost:3000/` again (a genuine full reload — Network shows
   `GET / => 200 OK` and every JS chunk re-fetched, not a bfcache restore), but the page renders
   nothing: `document.body.children.length` is non-zero (empty React root mounted) yet
   `document.body.innerText` is the empty string, and no visible content, form, or banner appears.
6. Wait 5+ seconds — the URL and blank state never change. `localStorage.getItem('auth_token')` is
   `null` the entire time, so the expected outcome (redirect to `/login`) is never triggered.
7. Confirm the redirect logic is otherwise intact: run `location.reload()` on this exact stuck
   `/` URL — it immediately redirects to `/login` correctly.
8. Repeated the full sequence (steps 1-6) a second time from a fresh `/dashboard` baseline — same
   result: permanent blank page at `/` after Back, requiring a manual reload to recover.

### Expected
Any load of `/` with no valid `auth_token` — whether reached by a fresh navigation, a client-side
route change, or the browser Back button — should redirect to `/login`, matching the app's own
correctly-working behavior for every other path to `/`.

### Actual
Specifically when `/` is reached via browser Back immediately after the corrupt-token bounce
chain, the redirect never fires: the page mounts an empty, contentless root and stays there
indefinitely with no error, no loading indicator, and no way to recover short of an explicit
manual reload or new navigation.

### Evidence
- Before (signed in, valid dashboard): `bug-hunter/evidence/root/BUG-20260827-232305-root/01-before-signed-in-dashboard.png`
- Corrupt-token bounce completes normally: `bug-hunter/evidence/root/BUG-20260827-232305-root/02-corrupt-token-bounce-to-login-expired.png`
- Failure (Back navigation, permanently blank `/`): `bug-hunter/evidence/root/BUG-20260827-232305-root/03-back-navigation-stuck-blank-root.png`

### Browser Signals
- Console: no errors or warnings logged during the stuck state.
- Network: the Back navigation fires a genuine `GET http://localhost:3000/ => 200 OK` (full chunk
  re-fetch, confirmed via `browser_network_requests`), so this is not a stale bfcache snapshot —
  the client bundle re-mounts fresh and still fails to redirect.
- State/URL: `location.href` stays `http://localhost:3000/` indefinitely; `auth_token` is
  confirmed `null` throughout; a manual `location.reload()` on the same URL immediately redirects
  to `/login`, isolating the defect to the Back-triggered load path specifically.
- **Issue card:** none minted — DUPLICATE of [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md).

## BUG-20260827-234030-create — "Jump back in" recent-runs cache is not scoped per user, leaking a previous account's run history into a different signed-in user's session

- **Page:** Create (catalog)
- **Route:** /create (reproduces identically on /dashboard — same underlying `HomeLaunchGrid` component)
- **Severity:** High
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, cycle 1 (deterministic, every cycle) — sign in as qa-admin, sign in as qa-basic without clearing sessionStorage, qa-basic's confirmed-empty live `/api/runs` response is still overridden by qa-admin's cached recents
- **Verified:** 2026-08-28 by verifier. Ran `frontend/src/components/catalog/HomeLaunchGrid.crossAccountLeak.test.tsx` (ISS-188, ISS-201) and `frontend/src/store/listenerMiddleware.test.ts` (ISS-200) individually — both XPASS'd (`it.fails` reported "Expect test to fail"), `it.fails` markers removed, re-run confirmed plain green (3/3 passed). Regression: `HomeLaunchGrid.test.tsx` (8 passed) + `HomeLaunchGrid.inspect.test.tsx` (2 passed), no failures. Health: `npm run build` compiled clean, `curl :8000/docs` → 200 (backend untouched by this fix, no restart needed), `lint-imports` from `backend/` → 3 kept / 1 broken, identical pre-existing break unrelated to this change. Manual re-run of the ORIGINAL repro in real Chrome via Playwright MCP: signed in qa-admin on `/create`, confirmed the recents cache is now written under a per-user key (`vlc_home_recents_v1:<jwt-sub>`, not the old global key); cleared only `localStorage.auth_token`, signed in qa-basic; confirmed live `GET /api/runs?limit=50` for qa-basic returns `count: 0`; navigated to `/create` — no "Jump back in" leak, none of qa-admin's run titles ("Say hello in one sentence.", "Smoke test run for bug hunt round 2") found anywhere on the page, sessionStorage held only qa-admin's own scoped key, no console errors/warnings. Screenshot: `bug-hunter/evidence/create/BUG-20260827-234030-create/04-verified-fixed-qa-basic-no-leak.png`.
- **Root cause:** `CACHE_KEY_RECENTS = "vlc_home_recents_v1"` (`frontend/src/components/catalog/HomeLaunchGrid.tsx:37`) is a single global `sessionStorage` key with no user/account/token component. The `recents` `useState` initializer (`HomeLaunchGrid.tsx:135-139`) falls back to `readCache(CACHE_KEY_RECENTS)` whenever both `recentRunsProp` and `reduxRecentRuns` are empty at mount — always true for an instant on every fresh sign-in. Neither of the two effects that can overwrite it (`:149-155`, `:159-166`) has an "else" branch, so a genuinely-empty live fetch can never clear a previously-cached non-empty value from a different account. `readCache`/`writeCache`/`CACHE_KEY_RECENTS` are private to this one file (confirmed via grep — no other caller), so the fix belongs entirely in `HomeLaunchGrid.tsx`: scope the key per user and/or add the missing empty-clears-cache branch to both effects.
- **Blast radius:** `HomeLaunchGrid.tsx` is the sole owner of this cache (no other file imports `readCache`/`writeCache`), so there are no sibling *callers* of the broken function — but the same missing-invalidation-on-account-switch shape recurs one layer up in Redux: `store/listenerMiddleware.ts`'s `signedIn` listener (:17-47) guards `fetchRecentRuns`/`fetchWorkflows` (and, identically, the Library's `fetchAgentLibrary`/`fetchSkills`/`fetchHooks`) on fetch *status* alone, never on user identity, and `authSlice.ts`'s `signedIn` reducer (:24-28) sets the new token unconditionally with no prior-token comparison — so a token swap that isn't preceded by `handleLogout`'s explicit `signedOut()` dispatch or `handleSessionExpiry`'s hard reload (the only two paths that reset this state) leaves Redux itself serving the previous account's data (ISS-200, INFERRED). Separately, the same 3-line fallback in `HomeLaunchGrid.tsx` is not conditioned on the new account being empty — it fires on every account switch, so even a newly-signed-in account with genuine run history gets at least one paint of the previous account's cards before its own fetch resolves (ISS-201, INFERRED).
- **Issue cards:** [ISS-188](../.knowledge/cards/20260828-1300-ISS-188.md) (root, CONFIRMED/validated),
  [ISS-200](../.knowledge/cards/20260828-1605-ISS-200.md) (sibling: Redux preload guard leaks the same way one layer up, INFERRED),
  [ISS-201](../.knowledge/cards/20260828-1607-ISS-201.md) (sibling: the same fallback flashes non-zero accounts too, INFERRED)
- **Found at:** 2026-08-27 23:40 UTC
- **Found by:** bug-create-r1
- **Fingerprint:** `/create|home-launch-grid-jump-back-in|sign-in-as-different-user-after-prior-session-cached-recents|stale-foreign-user-run-data-rendered-despite-empty-api-response`
- **Evidence:** `bug-hunter/evidence/create/BUG-20260827-234030-create/`

### Summary
The "Jump back in" recent-runs section on the Create/Dashboard catalog is backed by a
sessionStorage cache (`vlc_home_recents_v1`, `frontend/src/components/catalog/HomeLaunchGrid.tsx`)
that is keyed globally — not scoped to the signed-in user's id or token in any way. The
component's React state initializes directly from this cache on every mount
(`useState(() => ... readCache(CACHE_KEY_RECENTS))`), and the only two effects that can
overwrite it both require the freshly-fetched `recentRuns` to be **non-empty**
(`recentRunsProp.length > 0` / `reduxRecentRuns.length > 0`) — neither effect has an "else"
branch to clear the cache when the live API genuinely returns zero runs for the current user.
Consequence: if a browser tab signs in as User A (who has run history, which gets written to
this cache), then later signs in as a **different** User B in the same tab (e.g. after a
logout, or after the app's own documented token-clear-on-expiry behavior wipes only
`localStorage`), and User B has **zero** actual runs, the stale cache from User A is never
cleared and is rendered to User B as their own "Jump back in" history — even though the live
`GET /api/runs?limit=50` response for User B's session is a genuine, verified `[]`. This is a
cross-account data leak: the displayed cards include full run titles/briefs, workflow type, and
(for completed runs) exact token-usage and dollar-cost figures belonging to the other account.

### Reproduction
1. Sign in as qa-admin, land on `/create` (or `/dashboard`) — "Jump back in" shows qa-admin's
   real run history; this action causes `HomeLaunchGrid` to write that data into
   `sessionStorage['vlc_home_recents_v1']` (confirmed via direct read: the full run objects,
   including `tokenUsage`/`estimated_cost_usd`, are cached under this global, non-namespaced
   key).
2. Without clearing `sessionStorage` (only clear `localStorage.auth_token`, matching what the
   app's own corrupt-token/expiry recovery path does), navigate to `/login` and sign in as a
   **different** account with zero run history, e.g. `qa-basic@flowinqa.com`.
3. Navigate to `/create`. Confirm via a direct fetch with the new session's token that
   `GET /api/runs?limit=50` returns `[]` (verified: response body is exactly `[]`).
4. Observe: for a deterministic, controlled demonstration, set
   `sessionStorage.setItem('vlc_home_recents_v1', JSON.stringify([{id:'fake-leak-test-id',
   title:'LEAKED FOREIGN RUN TITLE', type:'ppt_v2', status:'completed',
   createdAt:<now>}]))` while signed in as the zero-run account, then reload `/create` — the
   "Jump back in" section renders a card titled "LEAKED FOREIGN RUN TITLE" even though the
   live API for this account returns `[]`. This isolates the exact defect: the cache is used
   verbatim whenever the live fetch resolves to empty, with no ownership check.
5. Reloaded `/create` a second time — the leaked card is still shown identically (deterministic,
   not a one-off race): the cache is never invalidated because the live empty response can never
   satisfy either overwrite guard.
6. Confirmed at the source (`frontend/src/components/catalog/HomeLaunchGrid.tsx:37-166`):
   `CACHE_KEY_RECENTS = "vlc_home_recents_v1"` has no user id/token component; `readCache`/
   `writeCache` operate on this single global key; the two effects that could refresh `recents`
   both gate on `.length > 0`, so a genuinely-empty fresh result is indistinguishable from "not
   fetched yet" and can never clear a previously-cached non-empty value.

### Expected
Cached "recent runs" data should be scoped to the currently authenticated user (e.g. keyed by
user id, or explicitly cleared on sign-out/sign-in of a different account), and a live fetch
that resolves to a genuine empty list should overwrite (clear) any stale cached entries rather
than being silently ignored.

### Actual
The recents cache is a single, unscoped sessionStorage key shared across whichever account is
signed in during that browser tab's lifetime. A user with no real runs of their own can be shown
another account's cached run history — including cost/token-usage details — with no code path
that ever clears it once the live API genuinely returns zero results.

### Evidence
- Before (qa-admin's own real "Jump back in" list, written into the shared cache): `bug-hunter/evidence/create/BUG-20260827-234030-create/01-admin-signed-in-jumpbackin.png`
- Failure (qa-basic session, live API confirmed `[]`, UI still shows a foreign/leaked entry): `bug-hunter/evidence/create/BUG-20260827-234030-create/02-basic-tier-shows-leaked-run.png`
- Reproduced again after a second fresh reload (deterministic, not a race): `bug-hunter/evidence/create/BUG-20260827-234030-create/03-reproduced-again-after-reload.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs?limit=50` for the second (zero-run) account returns `200 OK` with body
  `[]`, confirmed via `browser_network_request` on the response body, directly contradicting the
  rendered "Jump back in" content.
- State/URL: `sessionStorage['vlc_home_recents_v1']` persists across the account switch (logout
  alone does not clear it in the scenario tested — only clearing `localStorage.auth_token` was
  performed, mirroring the app's own documented corrupt-token recovery behavior); URL stays on
  `/create` throughout.

## BUG-20260827-234600-create-ppt — Selecting the "Investment Banking Pitch Book" template introduces an unsatisfiable "Pick a design system" requirement that permanently blocks Continue

- **Page:** PPT wizard shell (New presentation)
- **Route:** /create/ppt
- **Severity:** High
- **Status:** DUPLICATE
- **Found at:** 2026-08-27 23:46 UTC
- **Found by:** bug-create-ppt-r1
- **Fingerprint:** `/create/ppt|template-gallery-select-investment-banking-pitch-book|select-template-and-fill-brief|continue-permanently-disabled-no-design-system-ui-exists`
- **Evidence:** `bug-hunter/evidence/create-ppt/BUG-20260827-234600-create-ppt/`
- **Issue card:** [ISS-189](../.knowledge/cards/20260828-1457-ISS-189.md) (already covers this exact reproduction, root cause, and expected/actual; card body traces back to this register entry)

### Summary
On the PPT wizard's Template step, selecting the "Investment Banking Pitch Book" template (via
its preview modal's "Use this template" button) causes the page's unmet-requirements pill row to
show "Pick a design system" instead of clearing to a satisfied state, even though a template
selection is clearly recorded (checkmark badge on the card, "Use template example" prompt
updates to that template's brief). No other template tested (e.g. "Investor Pitch Deck") produces
this pill — selecting those simply clears the "Pick a template" pill as expected. Crucially,
there is no "design system" picker anywhere on the page: `document.body.innerText` contains the
string "design system" exactly once, inside the pill's own label. Clicking the pill does nothing
(no scroll, no modal, no highlight — confirmed via before/after screenshot). Filling the brief
textarea with a real, non-trivial value correctly clears the "Add a brief" pill, but "Pick a
design system" persists regardless, and the "Continue" button (`button.disabled === true`,
verified via DOM) can never be enabled for this template, permanently blocking the user from
proceeding past the Template step of the wizard.

### Reproduction
1. Sign in as qa-admin, navigate to `/create/ppt`.
2. In the Template gallery, search for or scroll to "Investment Banking Pitch Book" (Pitch Deck
   category) and click its card to open the preview modal.
3. Click "Use this template". Observe the card now shows a checkmark and the "Use template
   example" brief prompt updates to the Investment Banking brief text.
4. Observe the pill row below "Review gates": it now reads "Pick a design system" (orange/unmet)
   instead of clearing entirely, unlike selecting any other template.
5. Fill the "Describe your presentation" textarea with a real, non-empty brief (e.g. "A real
   pitch deck brief for testing purposes with enough length."). Observe "Add a brief" clears, but
   "Pick a design system" remains.
6. Inspect `button.disabled` on the "Continue" button — confirmed `true`; the button stays
   visually greyed out and unclickable.
7. Click directly on the "Pick a design system" pill itself — nothing happens (no navigation, no
   modal, no scroll, no new UI appears).
8. Search `document.body.innerText` for "design system" — it appears exactly once, only inside
   the pill's own label; no picker, section, or control for a "design system" exists anywhere on
   the rendered page.
9. Reloaded to a fresh `/create/ppt`, searched directly for "Investment Banking", selected only
   that template (skipping any other template first), and filled a different brief — identical
   result: `continueDisabled: true`, `designSystemPillFound: 1`, no design-system UI present.
   Deterministic across two independent attempts.

### Expected
Selecting any valid template plus a non-empty brief should satisfy the wizard's requirements and
enable "Continue" (as it does for every other template tested, e.g. "Investor Pitch Deck").  If a
"design system" selection is genuinely a required step for certain templates, the page must
render an actual picker control for it; a requirement pill with no corresponding UI is a dead end.

### Actual
For the "Investment Banking Pitch Book" template specifically, a phantom "Pick a design system"
requirement appears and can never be satisfied because no such control exists on the page,
permanently blocking the wizard's Continue action for that template.

### Evidence
- Before (template selected via preview modal, "Investor Pitch Deck" case for contrast): `bug-hunter/evidence/create-ppt/BUG-20260827-234600-create-ppt/01-before-preview-modal.png`
- Failure (Investment Banking Pitch Book selected, phantom pill appears): `bug-hunter/evidence/create-ppt/BUG-20260827-234600-create-ppt/02-selected-investment-banking-template.png`
- Failure (brief filled, pill and disabled Continue persist): `bug-hunter/evidence/create-ppt/BUG-20260827-234600-create-ppt/03-failure-brief-filled-continue-still-disabled.png`
- Reproduced independently on a fresh page load: `bug-hunter/evidence/create-ppt/BUG-20260827-234600-create-ppt/04-repro2-fresh-selection-same-deadend.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no failed request; this is purely client-side requirement-gating state tied to the
  selected template's metadata.
- State/URL: URL stays on `/create/ppt` throughout; `button.disabled` for Continue verified `true`
  via direct DOM read in both reproduction attempts; `document.body.innerText` confirmed to
  contain "design system" only within the pill label itself.

## BUG-20260827-235402-create-prototype — Browser Forward navigation to the prototype wizard leaves a permanently blank page

- **Page:** Prototype wizard shell
- **Route:** /create/prototype
- **Severity:** High
- **Status:** ESCALATED
- **Found at:** 2026-08-27 23:54 UTC
- **Found by:** bug-create-prototype-r1
- **Fingerprint:** `/create/prototype|wizard-shell|browser-back-then-forward|blank-page-no-hydration`
- **Evidence:** `bug-hunter/evidence/create-prototype/BUG-20260827-235402-create-prototype/`
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — Back-then-Forward sequence, not Back alone
- **Root cause:** `frontend/src/app/[...view]/page.tsx`'s single catch-all `DashboardPage` gates
  ALL rendering behind `if (!mounted || !isAuthenticated) return null` (`:3701`) — the FIRST
  render-level return in the whole 4107-line file. Both flags are set exactly once by mount-only
  `useEffect`s (`:416`/`:490-492` and `:431`/`:806-827`, the latter deps `[router, dispatch]`,
  stable for the SPA session) that never fire again once true, and `grep`ing the whole frontend
  for `pageshow`/`popstate`/`bfcache`/`back_forward` returns zero matches — nothing recovers a
  bfcache-style restore anywhere (CONFIRMED, file:line read + grep). Forward is the only step
  that reproduces the bug because it is the only one that re-initializes `DashboardPage` back to
  its `false`/`false` defaults without the mount effects ever re-running to flip them; which
  Next.js/browser mechanism does that (Router Cache miss vs. genuine bfcache restore) is
  INFERRED, not readable from this repo — see ISS-190's diagnostic for how to settle it.
- **Blast radius:** every one of the 34 `[...view]` screens shares this exact gate (ADR-0018),
  so Back-then-Forward to ANY route is exposed, not only `/create/prototype` (INFERRED, unverified
  on a second route). Two SEPARATE, independently-implemented copies of the identical anti-pattern
  also exist: `frontend/src/components/workflow/LaunchWizard.tsx` (`authChecked`, `:161`/
  `:259-270`/`:806`), which guards the actively-used legacy route `/workflow/create?mode=
  ppt|prototype` (call sites: `CreationHub.tsx:31,35`, `DashboardLayout.tsx:1530,1557`) WITHOUT
  going through `page.tsx`'s gate at all; and `frontend/src/app/handoff/settings/page.tsx`
  (`authed`, `:21`/`:32`). A `page.tsx`-only fix covers neither.
- **Proposed fix:** belongs in `frontend/src/app/[...view]/page.tsx`'s `DashboardPage` — the ONE
  catch-all every screen already routes through, not duplicated per-route. Candidate: register a
  `pageshow` listener once near the top of the component that forces `window.location.reload()`
  when `event.persisted` or `performance.getEntriesByType('navigation')[0]?.type ===
  'back_forward'` fires on an already-mounted instance (matches the manually-confirmed
  100%-reliable reload recovery). Alternative: derive `mounted`/`isAuthenticated` synchronously
  via a lazy `useState` initializer instead of a mount-only effect — needs care re: the
  SSR-hydration-mismatch tradeoff `:413`'s comment says the current code deliberately chose.
  `LaunchWizard.tsx`'s independent `authChecked` gate needs the SAME fix applied separately
  (see ISS-197).
- **5-fixer (2026-08-28): ESCALATED, no code changed.** The diagnostic ISS-190 itself asked for
  was run before editing anything, and it disproves the recorded root cause. Measured in real
  Chrome: the same Back-then-Forward sequence blanks EVERY route tried — `/dashboard`,
  `/handoff/settings`, and `/login` (which has no auth gate, no `mounted` flag and renders
  unconditionally) — so `page.tsx:3701`'s gate is not the mechanism. In the failure state
  `document` carries no `__reactContainer$*` key and `document.body` no `__reactFiber$*`: React
  never hydrates the app root, so `DashboardPage`/`LaunchWizard` never mount and NEITHER proposed
  fix (an in-component `pageshow` listener, a lazy `useState` initializer) can execute. `pageshow`
  reports `persisted: false`; the navigation is `type: "back_forward"` with `transferSize: 0` and
  a body size identical to the fresh load (`/login`: 18826 B == `curl … | wc -c`), i.e. a complete
  document replayed from Chrome's HTTP cache whose React streaming boundaries are never filled.
  With Chrome's back/forward cache ENABLED (Playwright disables it by default via
  `--disable-back-forward-cache`) the identical sequence renders correctly, `persisted: true` —
  Back `/dashboard` innerText 2749, Forward `/create/prototype` innerText 1481. Full evidence and
  the disposition questions a human must rule on:
  [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md). ISS-190 set to `superseded`; ISS-195's
  every-screen prediction is confirmed but wider than stated; ISS-197's `Loading…`-forever
  prediction is disproven. The xfail test is untouched and still red (1 xfailed).
- **Issue cards:** [ISS-190](../.knowledge/cards/20260828-1501-ISS-190.md) (root — CONFIRMED
  mechanism, INFERRED trigger + blast radius + proposed fix),
  [ISS-195](../.knowledge/cards/20260828-1558-ISS-195.md) (sibling, INFERRED/unreproduced: same
  gate blocks all 34 `[...view]` screens, not just `/create/prototype`),
  [ISS-197](../.knowledge/cards/20260828-1559-ISS-197.md) (sibling, INFERRED/unreproduced:
  `LaunchWizard.tsx` + `handoff/settings/page.tsx` independently copy the identical anti-pattern),
  [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md) (correction — the root cause above is
  disproven by measurement)

### Summary
Landing on `/create/prototype` normally, then pressing the browser **Back** button (returns to
`/dashboard`), then pressing browser **Forward** (returns to `/create/prototype`) leaves the page
completely blank — no header, no tabs, no template gallery, nothing. The URL and document title
are correct (`/create/prototype`, "VelocityAI"), `auth_token` remains valid the whole time, and
every underlying API call the page needs (`/api/workflows/prototype`, `/api/prototype/templates`,
`/api/prototype/design-systems`, etc.) returns 200 OK — the data layer is fine. But
`document.body.innerText` is the empty string and `document.body.innerHTML` contains only the raw,
un-executed Next.js RSC streaming payload as literal script/text content — the React tree never
hydrates into visible DOM. The page is stuck in this state indefinitely (verified 2+ seconds after
settle); only a manual reload (fresh `page.goto`) recovers it. Reproduced twice from a clean
Back→Forward sequence using real Playwright `page.goBack()`/`page.goForward()` calls (not just
`history.forward()`), so this is a genuine browser back-forward-cache/hydration defect on this
route, not an artifact of scripted navigation.

This is distinct from BUG-20260827-232305-root (blank `/` after a corrupt-token 401 bounce chain,
triggered by Back only, caused by a missing redirect call): this bug hits a different route
(`/create/prototype`, not `/`), needs no token corruption (a perfectly valid session the whole
time), is triggered by Back **then** Forward (not Back alone), and the failure mode is a stuck
unhydrated RSC payload rather than a missing client-side redirect.

### Reproduction
1. Sign in as qa-admin, land on `/dashboard`.
2. Navigate to `http://localhost:3000/create/prototype` — the wizard renders normally (Template
   tab, template gallery, Back/Next, etc.).
3. Press the browser **Back** button — lands back on `/dashboard`, renders normally.
4. Press the browser **Forward** button — URL becomes `/create/prototype` again, title is
   "VelocityAI", but the page renders nothing: no header, no textarea, no tabs, just the page
   background color.
5. Wait 2+ seconds — the blank state does not resolve on its own.
6. Inspect via console: `document.body.innerText` is `""`; `document.body.innerHTML` is ~24000
   characters of un-executed Next.js streaming script payload (RSC chunks), not rendered markup.
7. Repeated steps 2-6 a second time from a fresh `/dashboard` baseline — identical blank result
   both times.
8. Confirmed recovery: a fresh `page.goto('http://localhost:3000/create/prototype')` (equivalent
   to a manual reload) renders the wizard correctly again.

### Expected
Browser Forward navigation back to `/create/prototype` should render the wizard shell exactly as
a fresh visit does — same header, tabs, and template gallery.

### Actual
The page silently renders nothing: an empty, contentless body containing only the raw, un-hydrated
RSC payload, with no error, no loading indicator, and no way to recover except a full reload.

### Evidence
- Before (fresh load, wizard renders correctly): `bug-hunter/evidence/create-prototype/BUG-20260827-235402-create-prototype/01-before-back.png`
- Failure (after Back then Forward, blank page): `bug-hunter/evidence/create-prototype/BUG-20260827-235402-create-prototype/02-after-forward-blank.png`
- Second reproduction (blank again): `bug-hunter/evidence/create-prototype/BUG-20260827-235402-create-prototype/03-second-repro-blank.png`

### Browser Signals
- Console: no errors logged at the moment of the blank render; underlying API calls made during
  the page's own data-fetch lifecycle (`/api/workflows/prototype`, `/api/prototype/templates`,
  `/api/prototype/design-systems`, `/api/agents/library`, etc.) all returned 200 OK.
- Network: the Forward navigation itself was not accompanied by any failed request; the data the
  page needs was available, so this is a client-side hydration/rendering failure, not a fetch
  failure.
- State/URL: `location.href` correctly reads `http://localhost:3000/create/prototype` throughout;
  `localStorage.getItem('auth_token')` remains truthy the entire time (session never dropped).

## BUG-20260828-000100-create-app — Checking an agent in the composer's "Review gates" checklist does not set that agent's Gate in the Advanced modal's per-agent Config panel

- **Page:** Create app (simple launch panel — mislabeled as User Stories per known D-01)
- **Route:** /create/app
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 00:01 UTC
- **Found by:** bug-create-app-r1
- **Fingerprint:** `/create/app|review-gates-checklist-vs-advanced-config-gate-dropdown|check-agent-in-review-gates-popover|advanced-modal-per-agent-gate-still-reads-no-gate`
- **Evidence:** `bug-hunter/evidence/create-app/BUG-20260828-000100-create-app/`

### Summary
The launch panel exposes two separate controls for the same underlying concept — whether an
agent's step pauses the pipeline for human review. The top-level "Review gates" popover (a
checklist of the workflow's agents, "Checked agents pause the pipeline for your review after
they finish") and the "Advanced" modal's per-agent Config tab (`Gate` combobox: "No gate" /
"Conditional gate" / "Human gate"). Checking "Domain Discovery Agent" in the Review gates
checklist correctly updates the pill label to "1 agent pause for review" and persists the
checked state (re-opening the popover shows it still checked). But opening the Advanced modal,
selecting that exact same agent node, and viewing its Config tab shows `Gate: "No gate"`
selected — not "Human gate" as the checklist claims. The two controls disagree about the state
of the identical agent within the same page load, with no save/apply step between them (both
are live, un-submitted, in-session state on the same composer). This is independent of, and a
different mechanism from, D-22/D-23 (Advanced modal Escape/close-button issues) and D-05/D-10
(saved-override agent-count disagreements) — this defect is about a review-gate boolean, not a
modal-dismissal control or an agent-count estimate, and it reproduces before anything is ever
saved or an override is created.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/app` (fresh load — confirmed
   "Review gates" pill reads "no gates" and all 6 checklist checkboxes are unchecked).
2. Click the "Review gates" pill to open its checklist popover.
3. Click the "Domain Discovery Agent" row to check it. Observe the pill label immediately
   updates to "Review gates — 1 agent pause for review" and the checkbox is `checked` (confirmed
   via snapshot).
4. Press Escape / click elsewhere to close the popover (state persists — reopening confirms the
   checkbox stays checked).
5. Click the "Advanced" button to open "Advanced Workflow Configuration — User Stories".
6. Click the "Domain Discovery Agent" node on the canvas to select it, then click its "Config"
   tab in the right-hand rail.
7. Observe the `Gate` combobox for this exact agent: `option "No gate" [selected]` — not "Human
   gate" — even though the Review gates checklist (still checked, visible behind/beside the
   modal) says this agent is a review pause point.
8. Repeated the full sequence (steps 1-7) a second time from a fresh `/create/app` page load —
   identical result: checklist shows 1 agent checked and the pill updates, but the modal's
   per-agent Gate dropdown for that same agent still reads "No gate".

### Expected
Checking an agent in the "Review gates" checklist and viewing that same agent's Gate setting in
the Advanced modal should show a consistent state (e.g. "Human gate" selected), since both
controls describe the same underlying per-agent review-gate property on the same in-session
workflow configuration.

### Actual
The two controls disagree: the checklist reports the agent as gated ("1 agent pause for
review"), while the Advanced modal's own per-agent Config panel for the identical agent reports
"No gate" selected — a live, unresolved contradiction about the same field within the same page
session.

### Evidence
- Before (fresh page, "no gates", all unchecked): `bug-hunter/evidence/create-app/BUG-20260828-000100-create-app/01-before-fresh-no-gates.png`
- Checklist checked, pill reads "1 agent pause for review": `bug-hunter/evidence/create-app/BUG-20260828-000100-create-app/02-checklist-shows-1-agent-checked.png`
- Failure (Advanced modal Config tab for the same agent shows "No gate" selected): `bug-hunter/evidence/create-app/BUG-20260828-000100-create-app/03-failure-advanced-config-shows-no-gate.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no request involved for either control; both are purely client-side in-session state
  on the same composer page.
- State/URL: URL stays `/create/app` throughout; verified via direct DOM query that all six
  canvas nodes' "Gate" pill buttons render with identical, unstyled classes (no visual
  "active"/pressed indicator) regardless of the checklist's checked state, and the Config
  panel's `<select>`/combobox value for the checked agent is confirmed "No gate" via the
  accessibility tree, not just a screenshot read.

### Validation
- **Validated:** 3/3 on 2026-08-28, cold start each cycle — no timing/tier/theme variation
  needed; a structural state disconnect, not a race. Root cause: `ReviewGatesSection.tsx`
  writes `gateAgentIds` (submitted at launch as top-level `gate_agent_ids`), while
  `CanvasConfigRail.tsx`'s per-agent Gate combobox reads/writes an unrelated `agent.gates`
  array — the two are never synchronized.
- **Issue card:** [ISS-247](../.knowledge/cards/20260828-1637-ISS-247.md)

### Analysis
- **Root cause (CONFIRMED):** Two disjoint state stores back "does this agent pause for human
  review," with zero synchronization code in either direction. `ReviewGatesSection.tsx:36,83-86`
  reports checked ids upward via `onChange(gateAgentIds, touched)`, landing in a plain ref
  (`IdeaInputPage.tsx:912-915` `gateSelectionRef`) read only at submit time
  (`IdeaInputPage.tsx:1343` `gate_agent_ids`). `CanvasConfigRail.tsx`'s `Gate` combobox derives
  `chosenGate` purely from `sel.gates ?? []` (`CanvasConfigRail.tsx:248,253`) and its `selectGate`
  writes back only via `patch` -> `onSelection(agent.id, next)` (`CanvasConfigRail.tsx:354-357`)
  into the `selections` map `AgentsPopup.tsx`/`CanvasView.tsx` own — a field `ReviewGatesSection`
  never reads and never writes. Confirmed the render chain from the "Advanced" button
  (`IdeaInputPage.tsx:1841`) to the Gate combobox: `AgentsPopup.tsx:12` imports `CanvasView`,
  which imports and renders `CanvasConfigRail` (`CanvasView.tsx:11,2291`).
- **Blast radius:** `ReviewGatesSection` is rendered in exactly 2 places —
  `IdeaInputPage.tsx:1864` (this bug's `/create/app`, and every other non-ppt/prototype pipeline
  type it serves) and `LaunchWizard.tsx:1046` (ppt, prototype) — both wire the identical
  ref-then-submit-only pattern into the identical `AgentsPopup`->`CanvasView`->`CanvasConfigRail`
  chain (`LaunchWizard.tsx:243,583-584,1112-1125`). `ComposerPage.tsx`'s full-canvas mode does not
  render `ReviewGatesSection` at all (confirmed by ISS-247), so it is not affected — it never
  shows the checklist to disagree with the combobox in the first place. Backend-side,
  `gate_agent_ids` is genuinely honored at run time for these two launch flows (see
  `backend/app/api/run_commands.py`, `backend/CLAUDE.md:180`), so this is a display/consistency
  defect, not a silent failure of the human-gate feature itself for the reported flow.
- **Fix belongs in:** the shared `ReviewGatesSection.tsx` component's state model — it should
  derive/report checked state from the same `selections[agentId].gates` field
  `CanvasConfigRail.tsx` reads/writes, rather than each of its 2 callers maintaining a parallel,
  never-synced `gateSelectionRef`. One change in the shared component routes both callers
  through it; patching `IdeaInputPage.tsx` alone leaves `LaunchWizard.tsx` (ppt, prototype)
  broken.
- **Fixed:** 2026-08-28 by 5-fixer. Four frontend files, one mechanism — the per-step
  `selections` map moves out of `AgentsPopup`'s private mount-once `useState` up to the two
  launch panels, and the shared `ReviewGatesSection` writes into it. `ReviewGatesSection.tsx`
  gains optional `selections`/`onSelectionsChange` props plus a pure `withHumanGate()` helper,
  so `toggle` now also patches `selections[id].gates` (only `human` is added/removed —
  `validation`, `conditional` and `before-human` are carried through; an emptied step is
  deleted, the rule `handleCanvasSelection` already applies). `AgentsPopup.tsx` takes an
  optional controlled `selections` prop (`controlledSelections ?? ownSelections`) — absent, it
  behaves exactly as before. `IdeaInputPage.tsx` holds the live map as state seeded where the
  popup's private seed came from (`cleanSelections` + a `useEffect` folding `manifestSelections`
  in UNDER it, the precedence `mergedInitialSelections` had); `selectionsRef` is untouched as
  the launch-payload source, so an untouched run still omits `selections` (INV-3).
  `LaunchWizard.tsx` gets the same lift for ppt/prototype, with all six `selectionsRef.current =`
  writers routed through the one `handleSelectionsChange`. The checklist's local `checkedIds`
  seed and its `onChange(ids, touched)` contract are deliberately UNCHANGED — that is what keeps
  `gate_agent_ids` byte-identical on an untouched run. Sending both is safe: engine.py:6382-6405
  (WR-02) already skips a declared `human` gate when the inline `_should_gate` path fires for the
  same step, so there is no second pause on the shared `gate_key`.
  Tests: `tests/integration/e2e/suites/03_launch_panels/test_launch_panels.py::test_checking_a_review_gate_sets_that_agents_gate_in_the_advanced_modal`
  → `[XPASS(strict)] ISS-247 unfixed` on 6 of 6 standalone runs — the strict-xfail pass signal;
  marker left in place for the verifier. Whole file, `-m "not live and not destructive"`:
  15 passed, 2 deselected, 1 xfailed in 97.22s — that one xfail is the SAME test losing a
  read race under suite load, NOT the fix failing: it reads `gate.input_value()` immediately,
  while `chosenGate` stays `""` until the async `/api/capabilities` fetch populates
  `gateOptions` (`CanvasConfigRail.tsx:118,250-253`), and that run's own failure screenshot
  (`tests/integration/test-runs/2026-08-28T23-05-fix-iss-247-regress4/03-launch_panels/UNMARKED-checking-a-review-gate-sets-that-agents-gate-in-the-advanced-modal/03-advanced-config-FAILED.png`)
  shows Gate = "Human gate". The test was NOT edited — `expect(gate).not_to_have_value("")`
  would settle it, but that is the verifier's call.
  Vitest: ReviewGatesSection 12, AgentsPopup.reskin 14, IdeaInputPage.selections 4,
  LaunchWizard 19, CanvasConfigRail 31, AdvancedExpander 11, IdeaInputPage.modelOverrides 2 —
  all green. `npx tsc --noEmit` byte-identical to the pre-change baseline (9 lines, all in
  HomeLaunchGrid.crossAccountLeak/listenerMiddleware tests, neither touched). Frontend-only:
  no backend restart, no migration, no engine or import-linter surface involved.
- **Fix card:** [FIX-346](../.knowledge/cards/20260828-2314-FIX-346.md) — resolves
  [ISS-247](../.knowledge/cards/20260828-1637-ISS-247.md) (status: resolved, verification:
  passed). The same shared-component change also carries
  [ISS-361](../.knowledge/cards/20260828-2120-ISS-361.md) (LaunchWizard / ppt / prototype),
  which stays `open` because it was INFERRED, never reproduced, and carries no test — the
  ppt/prototype checklist was not driven here.
  [ISS-362](../.knowledge/cards/20260828-2121-ISS-362.md) (the INVERSE direction: setting
  Gate=Human in the modal does not tick the checklist) is UNTOUCHED and still open — deriving
  `checkedIds` from `selections` would change the untouched-default seeding that
  `ReviewGatesSection.test.tsx` pins and that `gate_agent_ids`' `touched` contract depends on,
  which is a design decision, not this fix.
- **Issue cards:** [ISS-247](../.knowledge/cards/20260828-1637-ISS-247.md) (root, pre-existing),
  [ISS-361](../.knowledge/cards/20260828-2120-ISS-361.md) (INFERRED sibling: `LaunchWizard.tsx`
  path, ppt/prototype, same mechanism unverified on those routes),
  [ISS-362](../.knowledge/cards/20260828-2121-ISS-362.md) (INFERRED sibling: inverse direction —
  setting Gate=Human in Advanced does not check the Review-gates checklist either).
- **Verified:** 2026-08-28 by 6-verifier. `suites/03_launch_panels/test_launch_panels.py::test_checking_a_review_gate_sets_that_agents_gate_in_the_advanced_modal`
  ran standalone: `[XPASS(strict)] ISS-247 unfixed` (confirmed the pass signal), then the
  `xfail` marker was removed and it re-ran plain green (1 passed). Whole-file regression run:
  16 passed, 1 deselected, 1 pre-existing failure
  (`test_the_advanced_control_opens_the_agent_roster` — "Advanced says 6 agents but the canvas
  renders 7 nodes"; confirmed pre-existing and unrelated by stashing the fix's 4 touched files
  and re-running that one test standalone — identical `7 == 6` failure with the fix absent, so
  it is the documented D-05/D-10 agent-count defect, not a regression from this change).
  Manual re-run of the original repro in the browser (qa-admin, fresh `/create/app` load,
  checked "Domain Discovery Agent" in Review gates, pill read "1 agent pause for review",
  opened Advanced, selected the same node, Config tab): `Gate` combobox now shows
  `option "Human gate" [selected]` — matches the checklist. No console errors/warnings on the
  page (0/0). `npx tsc --noEmit`: 9 pre-existing lines (HomeLaunchGrid.crossAccountLeak /
  listenerMiddleware tests, untouched by this fix) — unchanged from the fixer's baseline.
  Backend `:8000/docs` → 200 (frontend-only fix, no restart needed). `lint-imports` (run from
  `backend/`): 1 pre-existing broken contract (`agents.execution_engine.engine` -> `app.api`
  via `kernel_services`/`revision_analyzer`) — unrelated to this frontend change, not
  introduced by it. After screenshot:
  `bug-hunter/evidence/create-app/BUG-20260828-000100-create-app/04-after-fix-advanced-config-shows-human-gate.png`.

## BUG-20260828-000600-create-user-stories — The Advanced modal's Workflow-level settings (Smart planning, Confirm requirements first, Deliverable strategy, Internet access) are permanently disabled with no explanation

- **Page:** User-stories launch panel (Advanced Workflow Configuration modal)
- **Route:** /create/user-stories
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 00:06 UTC
- **Found by:** bug-create-user-stories-r1
- **Fingerprint:** `/create/user-stories|advanced-modal-workflow-tab|open-workflow-tab-no-node-selected|all-workflow-level-controls-permanently-disabled-no-affordance`
- **Evidence:** `bug-hunter/evidence/create-user-stories/BUG-20260828-000600-create-user-stories/`
- **Validated:** 3/3 on 2026-08-28, cycle 1 every attempt — cold nav to /create/user-stories,
  open Advanced modal, all 6 Workflow-tab controls disabled via DOM read; root cause in
  `frontend/src/components/workflow/LaunchWizard.tsx:234-240` (declaredRunConfig documented as
  read-only, no onRunConfigChange/onCapabilitiesChange forwarded) gating
  `frontend/src/components/workflow/composer/CanvasView.tsx`'s six controls.
- **Issue card:** [ISS-246](../.knowledge/cards/20260828-1657-ISS-246.md)

### Analysis
- **Root cause (CONFIRMED):** `frontend/src/components/workflow/AgentsPopup.tsx`'s own props
  interface (`AgentsPopupProps`, lines 43-146) never declares `onRunConfigChange`/
  `onCapabilitiesChange` at all — documented as deliberate at lines 71-80 ("Read-only here — no
  `onRunConfigChange` is forwarded, so the rail's controls stay disabled exactly as before").
  `AgentsPopup.tsx:2449-2469` renders `<CanvasView runConfig={runConfig} .../>` with no way to
  forward either callback, so inside `CanvasView.tsx` all six controls
  (`disabled={!onRunConfigChange}` at lines 1624/1639/1668/1703/1719,
  `disabled={!onCapabilitiesChange}` at line 1750) render unconditionally disabled. None of the
  six carries a lock icon/tooltip/`title` keyed off that condition — confirmed by contrast against
  `CanvasConfigRail.tsx:600-610`, which disables its own "Execute commands" toggle the identical
  way but DOES pair it with `<InfoHint>Not available to custom workflows.</InfoHint>` plus visible
  sub-text — proof the codebase already has the "disabled + reason" pattern, just never applied
  here.
- **Blast radius:** Every production render of `<CanvasView>` (`grep -rn "<CanvasView"
  frontend/src/`): (1) `AgentsPopup.tsx:2449` — reached via `LaunchWizard.tsx:1112` (every
  built-in `/create/<mode>` launch, not just user-stories) AND `IdeaInputPage.tsx:1870` (the
  compose-from-scratch entry) — both hit the identical no-explanation disabled state, since the
  gap is structural in `AgentsPopupProps`, not per-caller. (2) `ComposerPage.tsx:1111` — the only
  OTHER caller — unconditionally forwards both callbacks (`onCapabilitiesChange={setCapabilities}`
  line 1135, `onRunConfigChange={setRunConfig}` line 1137), so the full-canvas Composer is NOT
  affected. Traced the inverse case (does an edit that IS accepted actually take effect for a
  built-in override, per ADR-0027's "steps only" invariant) and ruled it out: ComposerPage's
  "Save as copy" for a `builtinCanvasType` forces a full manifest send
  (`needsFullManifestOnSave`, ComposerPage.tsx:93-105), so edited workflow-level fields DO persist
  and take effect on the new copy — not a second defect.
- **Fix belongs in:** `CanvasView.tsx`'s `workflowSettingsSection` (defined once at line 1611,
  rendered once at line 2288) — the single block every caller routes through. Adding the
  `InfoHint`/sub-text pattern already used by `CanvasConfigRail.tsx`'s "Execute commands",
  conditioned on `!onRunConfigChange`/`!onCapabilitiesChange`, there fixes both current callers
  (LaunchWizard's and IdeaInputPage's `AgentsPopup`) and any future one for free. Patching
  `AgentsPopup.tsx` alone would still leave `IdeaInputPage.tsx`'s identical usage unexplained.
  NOTE: the "Reset to default" button (`CanvasView.tsx:2249`) sits in the same right rail but
  OUTSIDE `workflowSettingsSection` (it's in the tab header, not the settings block) — the fixer
  should confirm the fix's reach covers it too, or add it separately (see ISS-368).
- **Issue cards:** [ISS-246](../.knowledge/cards/20260828-1657-ISS-246.md) (root, pre-existing),
  [ISS-368](../.knowledge/cards/20260828-1927-ISS-368.md) (INFERRED sibling: the "Reset to
  default" button shares the identical disabled-with-no-explanation flaw, outside ISS-246's
  verified 6-control scope).
- **Fixed:** 2026-08-28 by 5-fixer. `frontend/src/components/workflow/composer/CanvasView.tsx`
  only, +31 lines, no deletions. The rail's read-only state now names itself: two derived
  constants next to `formatLocked` (`runConfigLockedNote`/`capabilitiesLockedNote`, each the
  shared id `workflow-settings-locked-note` or `undefined`), a visible note at the head of
  `workflowSettingsSection` when either is set ("Read-only — these run settings come from this
  workflow's own configuration and cannot be changed here"), and `aria-describedby` pointing at
  it from all six controls (a new optional `describedBy` prop on the local `Toggle` carries it
  for the three switches) PLUS the tab-header "Reset to default" button, which the analysis
  flagged as sitting outside the settings block. Placed in `CanvasView` because that is where
  the `disabled` gate itself lives, so `IdeaInputPage`'s composer popup gets the same
  explanation from one edit; forwarding the callbacks from `AgentsPopup` instead would have made
  a built-in's workflow-level config editable from the launch panel, which ADR-0027 rules out —
  the read-only behaviour is deliberate and is unchanged. `ComposerPage` passes both callbacks,
  so both constants are `undefined` there and the full-page Composer renders identically.
  Tests: `suites/03_launch_panels/test_advanced_modal_workflow_settings_disabled_explanation.py`
  → XPASS(strict) ("[XPASS(strict)] ISS-246 unfixed", 1 failed of 1) — the pass signal; marker
  left in place for the verifier. Vitest `CanvasView.test.tsx` 24/24 green. `npx tsc --noEmit`
  reports nothing in CanvasView.tsx (the 6 remaining errors are in
  HomeLaunchGrid.crossAccountLeak/listenerMiddleware tests, untouched). `npx eslint` on the file:
  0 errors, 14 pre-existing `react-hooks/static-components` warnings. Frontend-only: no backend
  restart, no migration, no engine or import-linter surface involved.
- **Fix card:** [FIX-348](../.knowledge/cards/20260828-2321-FIX-348.md) — resolves
  [ISS-246](../.knowledge/cards/20260828-1657-ISS-246.md) (status: resolved, verification:
  passed). The same edit also covers
  [ISS-368](../.knowledge/cards/20260828-1927-ISS-368.md)'s "Reset to default" button, but that
  card stays `open`: it was INFERRED, never reproduced, carries no test, and was not this
  fixer's assigned card — the verifier should read that button's `.disabled` +
  `aria-describedby` while it is already in the modal and close it if confirmed.
- **Verified:** 2026-08-28 by 6-verifier. Ran
  `suites/03_launch_panels/test_advanced_modal_workflow_settings_disabled_explanation.py` alone
  (venv `tests/integration/e2e/.venv`) — first pass confirmed
  `[XPASS(strict)] ISS-246 unfixed` (the pass signal), removed the `xfail` marker (kept
  `@pytest.mark.issue("ISS-246")`), re-ran: plain green (1 passed, 12.3s). Manual re-run of the
  ORIGINAL repro by hand in Chrome (lane6, qa-admin, cold nav `/dashboard` → `/create/user-stories`
  → "Advanced 7 agents"): all six Workflow-tab controls (3 switches, 2 selects, 1 input) remain
  `disabled === true` (deliberate, per ADR-0027 — unchanged), but every one now carries
  `aria-describedby="workflow-settings-locked-note"`, and that element's text reads "Read-only —
  these run settings come from this workflow's own configuration and cannot be changed here." The
  "Brief instruction" textarea control stayed non-disabled throughout, ruling out a page-wide
  rendering fluke. Also confirmed the tab-header "Reset to default" button (ISS-368's scope, not
  this bug's assigned card) now carries the same `aria-describedby`. 0 console errors on the page.
  `npx tsc --noEmit` in `frontend/`: 0 errors in `CanvasView.tsx` (6 remaining errors are
  pre-existing, in `HomeLaunchGrid.crossAccountLeak.test.tsx`/`listenerMiddleware.test.ts`,
  untouched by this fix). `npx vitest run src/components/workflow/composer/CanvasView.test.tsx`:
  24/24 green. `backend/` `lint-imports`: 1 pre-existing broken contract
  (`agents.execution_engine.engine` → `app.api`, unrelated `kernel_services`/
  `revision_analyzer` import boundary) — confirmed pre-existing (no backend files touched by this
  fix, contract violation is in files this change never edits). Frontend-only fix, no backend
  restart required; `:8000/docs` confirmed 200. After-screenshot:
  `bug-hunter/evidence/create-user-stories/BUG-20260828-000600-create-user-stories/04-after-verified-locked-note.png`.

### Summary
Opening the "Advanced" modal and viewing its right-rail "Workflow" tab (the default view when no
agent node is selected on the canvas) renders four workflow-level settings — "Smart planning"
(switch), "Confirm requirements first" (switch), "Deliverable" strategy (combobox, plus its
dependent "Output file name" text input and "Output format" combobox), and "Internet access"
(switch) — all with the HTML `disabled` attribute set, verified via direct DOM reads
(`element.disabled === true` for every one of the six form controls). Nothing on the page
indicates why: no lock icon, no tooltip, no "upgrade to unlock" copy, no `title` attribute — each
control's only affordance is an `(i)` info icon whose tooltip explains what the setting *does*,
not why it cannot be changed. This is not a page-wide disabled state: in the same modal, the
"Brief instruction" textarea directly above these controls is fully interactive
(`textarea.disabled === false`), and selecting an agent node and switching to its own "Tools" tab
shows genuinely interactive switches ("Read files"/"Write files" enabled, only the
security-gated "Execute commands" disabled) — proving the app can and does render real,
togglable switches elsewhere in the identical modal. The Workflow tab's four settings are simply
inert controls masquerading as configurable options, on every fresh page load, with no code path
observed that ever enables them.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/user-stories` (fresh load).
2. Click the "Advanced 6 agents · ~35s" button to open "Advanced Workflow Configuration — User
   Stories".
3. With no agent node selected (default state), the right-rail "Workflow" tab is active. Observe
   "Smart planning", "Confirm requirements first", "Deliverable" (dropdown + filename + format),
   and "Internet access" are all visually greyed out.
4. Confirm via `document.querySelectorAll('[role="switch"]')` and the `<select>`/`<input>`
   elements under that panel that every one of the six controls has `disabled === true`.
5. For contrast, confirm the "Brief instruction" textarea in the same panel is NOT disabled
   (`disabled === false`), and that selecting an agent node and opening its own "Tools" tab shows
   "Read files"/"Write files" switches that ARE enabled — proving this is not a general modal
   rendering artifact.
6. Closed the modal via "Cancel", did a fresh full navigation to `/create/user-stories` again,
   reopened "Advanced", and re-checked the same six controls — identical result: all six still
   `disabled === true`, deterministic across two independent fresh loads.

### Expected
Workflow-level settings that are rendered as interactive switches/dropdowns should be editable by
an admin/enterprise user (or, if intentionally locked for this workflow, should carry a visible
reason — a lock icon, disabled-state tooltip, or explanatory copy — consistent with how the
canvas's own "Core = locked" agent badge explains its own lock state).

### Actual
All four workflow-level settings and their two dependent fields render as fully-styled, seemingly
interactive controls that are permanently `disabled`, with zero indication anywhere in the UI of
why, blocking a user from ever changing "Smart planning", "Confirm requirements first",
"Deliverable" output strategy/filename/format, or "Internet access" for this workflow.

### Evidence
- Before (fresh launch panel, modal closed): `bug-hunter/evidence/create-user-stories/BUG-20260828-000600-create-user-stories/01-before-launch-panel.png`
- Failure, repro 2 (fresh page load, Workflow tab, all six controls disabled): `bug-hunter/evidence/create-user-stories/BUG-20260828-000600-create-user-stories/02-repro2-fresh-load-workflow-tab-all-disabled.png`
- Failure, repro 1 (same result on the first investigation pass): `bug-hunter/evidence/create-user-stories/BUG-20260828-000600-create-user-stories/03-repro1-workflow-tab-all-disabled.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no request involved; this is static disabled-attribute rendering with no data-fetch
  dependency observed to ever flip it.
- State/URL: URL stays `/create/user-stories` throughout; verified via direct DOM
  `element.disabled` reads (not just visual/screenshot inspection) on two independent fresh page
  loads, and confirmed non-disabled sibling controls (Brief textarea, agent-level Tools switches)
  exist in the same modal session to rule out a page-wide rendering fluke.

## BUG-20260828-001100-create-ex-a2-branch — Advanced modal's "Cancel" button does not discard edits to a conditional-gate outcome's route

- **Page:** Branch by Language launch panel (Advanced Workflow Configuration modal)
- **Route:** /create/ex_A2_branch
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 00:11 UTC
- **Found by:** bug-create-ex-a2-branch-r1
- **Fingerprint:** `/create/ex_A2_branch|advanced-modal-conditional-gate-route-editor|change-outcome-type-and-target-then-click-cancel|edit-persists-across-modal-close-and-reopen`
- **Evidence:** `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-001100-create-ex-a2-branch/`

### Summary
`ex_A2_branch` ("Branch by Language") is a real branching fixture whose "Pick Language" agent
step has a Conditional gate with three outcomes (`english`/`spanish`/`dutch`), each routing to
a forward step. In the Advanced modal's per-agent Config tab, changing one outcome's "Type"
from "Step" to "Workflow" and picking a target workflow (e.g. "Spanish Greeter") via the "Pick a
workflow" dialog is a live, un-saved edit to that route. Clicking the modal's own "Cancel"
button is the documented way to discard such in-session edits without persisting them (no
network request is ever fired for either the edit or the Cancel — confirmed via
`browser_network_requests`, only background `GET`s are present). Instead, closing the modal via
Cancel and reopening "Advanced" shows the edit still applied: the canvas gains a new "Spanish
Greeter — Diverts run" node, the step legend changes from `english/spanish/dutch` to
`spanish/dutch` then back to including `english` once re-pointed, and the Config tab for "Pick
Language" still shows the `english` outcome's Type as "Workflow" and Target as "Spanish
Greeter". This reproduced twice in a row (Cancel → reopen → still present, Cancel again →
reopen → still present). A full page reload (`/create/ex_A2_branch` fresh navigation, not just
modal close) does correctly reset to the original 5-agent, no-divert state, confirming the edit
was never sent to the backend — it is purely un-discarded client-side component state that
"Cancel" fails to reset, unlike a real save. This is a different mechanism from the already-filed
`create-app`/`create-user-stories` Advanced-modal defects (per-agent Gate/Review-gates desync,
and permanently-disabled Workflow-tab controls) — this is about the modal's own Cancel action
failing to roll back an edit made inside the same modal session, specific to the conditional-gate
route editor that only branching fixtures like this one expose.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/ex_A2_branch` (fresh load).
   Confirm "Advanced 5 agents" and no divert node on the canvas.
2. Click "Advanced 5 agents" to open "Advanced Workflow Configuration — Language Branch".
3. Click the "Pick Language" node, then its "Route 3 outcomes" pill (Config tab, conditional
   gate route editor with `english`/`spanish`/`dutch` outcomes).
4. For the `english` outcome, change "Type" from "Step" to "Workflow". The "Target" control
   becomes a "Pick a workflow…" button.
5. Click it, select "Spanish Greeter" in the "Pick a workflow" dialog, click "Pick workflow" to
   confirm. Observe the Target now reads "Spanish Greeter" and a new "Spanish Greeter — Diverts
   run" node appears on the canvas.
6. Click the modal's "Cancel" button (bottom-right) to close it without saving.
7. Re-open "Advanced" (button still reads "5 agents" on the launch panel behind the modal).
   Observe the canvas still shows the "Spanish Greeter — Diverts run" node, and selecting "Pick
   Language" → Config → Route still shows `english` outcome Type "Workflow", Target "Spanish
   Greeter".
8. Repeated steps 6-7 a second time (Cancel again, reopen again) — identical result.
9. Did a full page reload (fresh navigation to the same URL, not just modal close/reopen) —
   the launch panel correctly resets to "5 agents" with no divert node, confirming the edit was
   never persisted server-side (no relevant POST/PUT/PATCH observed in
   `browser_network_requests` at any point in steps 4-8).

### Expected
Clicking "Cancel" in the Advanced modal should discard any edits made during that modal session
(here, the `english` outcome's Type/Target change), returning the canvas and Config panel to the
state they were in when the modal was opened — consistent with "Cancel" being offered as the
alternative to "Save workflow".

### Actual
"Cancel" closes the modal but does not roll back the route-editor edit; the changed outcome
Type/Target and the resulting extra canvas node persist across repeated close/reopen cycles
within the same page session, even though nothing was ever saved to the backend.

### Evidence
- Before (fresh load, no divert node): `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-001100-create-ex-a2-branch/01-before-fresh-load.png`
- Failure, repro 1 (after Cancel + reopen, Spanish Greeter divert node present): `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-001100-create-ex-a2-branch/02-after-cancel-reopen-shows-spanish-greeter-target.png`
- Failure, repro 2 (after a second Cancel + reopen, still present): `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-001100-create-ex-a2-branch/03-repro2-after-second-cancel-still-shows-spanish-greeter.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `browser_network_requests` showed only background `GET`s (`/api/workflows`,
  `/api/workflows/ex_A2_branch`, `/api/agents/library`, etc.) throughout the edit/Cancel/reopen
  cycle — no `POST`/`PUT`/`PATCH` fired, confirming the persisted edit is unsaved client state,
  not a silent server save.
- State/URL: URL stayed `/create/ex_A2_branch` throughout steps 1-8; a fresh full navigation in
  step 9 correctly reset the panel, isolating the defect to the modal's Cancel handler rather
  than a backend persistence bug.

- **Issue card:** [ISS-258](../.knowledge/cards/20260828-1650-ISS-258.md)
- **Root cause:** The embedded route/outcome editor writes through `onRouteChange`
  (`CanvasConfigRail.tsx:295`) → `onTreeChange` (`CanvasView.tsx:748-751`, wired at `:2302`) →
  the host's `onReorder` prop (`AgentsPopup.tsx:2462`) → `setPipelineAgents`
  (`IdeaInputPage.tsx:1540-1542`), the React state the canvas renders from. Cancel
  (`AgentsPopup.tsx:2492-2493`, `onClick={onClose}`) only flips `showAgents`
  (`IdeaInputPage.tsx:1882`, `() => setShowAgents(false)`) and never restores `pipelineAgents` —
  no snapshot of it is ever taken when the modal opens. This corrects ISS-258's own root-cause
  attribution (`AgentsPopup.tsx:2242-2248`'s `handleSelectionsChange`/`onSelectionsChange`/
  `selectionsRef`), which is real code with the identical defect shape but is wired to a
  different edit surface (the flat per-agent levers, not the route/outcome editor) — see ISS-364.
- **Blast radius:** both production callers of `AgentsPopup` — `IdeaInputPage.tsx:1870`
  (`/create/<id>`, this bug's own route) and `LaunchWizard.tsx:1112` (`/workflow/create` and the
  ppt/prototype branch of `/workflows/{id}/run`) — confirmed via
  `grep -rn "<AgentsPopup" frontend/src/ --include="*.tsx"` (2 production hits + 4 in
  `AgentsPopup.reskin.test.tsx`). Every other edit that funnels through the same `onTreeChange`/
  `onReorder` chain (add/remove/reorder agent) shares the identical un-restored Cancel, as does
  every edit through the adjacent `onSelectionsChange`/`selectionsRef` chain (Model/Validators/
  Gates/Retry levers).
- **Fix belongs in:** `AgentsPopup.tsx` itself, once — not in either host page. It already takes
  a one-time mount snapshot for `liveSelections` (`:2233-2241`); the same staged-copy-with-
  restore-on-Cancel needs to cover `agents`/`pipelineAgents`, with Cancel (`:2492-2493`)
  resetting both staged copies and re-emitting them to the host before calling `onClose`. One
  diff in the shared component fixes both hosts and every edit channel; patching either host
  page alone, or patching `handleSelectionsChange` alone per ISS-258's original fix sketch,
  would leave the reported route-editor case unfixed.
- **Issue cards:** [ISS-258](../.knowledge/cards/20260828-1650-ISS-258.md) (original — repro and
  evidence stand; root-cause mechanism superseded),
  [ISS-363](../.knowledge/cards/20260828-2129-ISS-363.md) (root — corrected mechanism),
  [ISS-364](../.knowledge/cards/20260828-2130-ISS-364.md) (sibling, INFERRED: flat-lever edits
  via `selectionsRef`),
  [ISS-365](../.knowledge/cards/20260828-2131-ISS-365.md) (sibling, INFERRED: add/remove/reorder-
  agent edits),
  [ISS-366](../.knowledge/cards/20260828-2132-ISS-366.md) (sibling, INFERRED: same defect via
  `LaunchWizard`'s `AgentsPopup` instance)
- **Fix card:** [FIX-349](../.knowledge/cards/20260828-2324-FIX-349.md)
- **Fixed:** `frontend/src/components/workflow/AgentsPopup.tsx` — the modal now snapshots the
  host's `agents` + `liveSelections` on the `isOpen` edge and re-emits that snapshot
  (`onReorder?.(snapshot.agents)` + `handleSelectionsChange(snapshot.selections)`) before
  `onClose()`, from a new `handleCancel` wired to the Cancel button, the header X and the
  backdrop. The post-save `onClose()` in `handleSaveWorkflow` is untouched. One diff in the
  shared component, so both hosts and every edit channel are covered.
- **Test:** `tests/integration/e2e/suites/03_launch_panels/test_iss258_advanced_modal_cancel_discards_route_edit.py`
  → **1 xfailed, NOT the XPASS a clean fix produces.** The remaining failure is entirely
  test-side: line 63 asserts `to_have_value("Step")` but the markup is
  `<option value="step">Step</option>` (`CanvasConfigRail.tsx:843`), so the value is `step`.
  Everything the bug is about passed on the same run — steps 1-3 ok, and the line-57
  `DIVERT_NODE count == 0` assertion passed, i.e. the cancelled route edit's divert node is
  gone after Cancel + reopen. Verifier: correct that one literal to `"step"` (a fixer does not
  edit a test to make it pass) and it XPASSes.
- **Verified (REOPENED):** Ran
  `suites/03_launch_panels/test_iss258_advanced_modal_cancel_discards_route_edit.py` with
  `--runxfail` three times (offline tier, real Chrome via pytest-playwright). Result was flaky
  across runs, not the single test-side label mismatch the fixer reported: 1/3 failed exactly as
  FIX-349 described (line 63 `to_have_value("Step")` vs actual `"step"`); the other 2/3 failed
  because the reopened modal showed **`0 agents`** and no `Pick Language` node at all — the
  divert-node edit was gone, but so was every other agent, not just the cancelled edit.
  Screenshot evidence:
  `tests/integration/test-runs/2026-08-28T23-39-local/03-launch_panels/UNMARKED-advanced-modal-cancel-discards-a-conditional-gate-route-edit/03-cancel-and-reopen.png`
  and the `2026-08-28T23-31-local` run's equivalent shot both show "0 AGENTS" on reopen. Root
  cause confirmed by reading `AgentsPopup.tsx:2377-2379`: `openSnapshot`'s `useEffect` depends
  only on `[isOpen]` and snapshots the live `agents`/`liveSelections` the instant `isOpen` flips
  true — if the modal is opened before the host's `pipelineAgents` has finished loading from its
  own async fetch (steps.json for the `23-39` run shows the "advanced-open" step completing only
  352ms after `page.goto`), the snapshot captures the still-empty initial array. `handleCancel`
  then calls `onReorder?.(snapshot.agents)` with that empty array, wiping every real agent from
  `pipelineAgents` — a regression strictly worse than the original bug (data loss vs. an
  un-discarded edit). A manual re-run in the browser with a deliberate wait for "5 agents" to
  render before opening the modal did NOT reproduce this (correctly showed 5 agents, no divert
  node, Type reset to "Step" on Cancel + reopen) — the defect is a load-order race, not
  present-100%-of-the-time, which is exactly why it survived FIX-349's own 3-run manual
  verification but shows up 2/3 in the faster automated test. xfail marker left in place; cards
  left `resolved`/`active` unchanged pending a real fix (snapshot must wait for `agents` to be
  populated, not just `isOpen`, before restoring on Cancel).
- **Re-fix card:** [FIX-365](../.knowledge/cards/20260829-0045-FIX-365.md) — the reopened
  regression, fixed in the same file FIX-349 touched
  (`frontend/src/components/workflow/AgentsPopup.tsx`, no other file). `openSnapshot` is no
  longer taken on the `isOpen` edge; it is STAGED by the first modal-initiated write, via a
  `stageEdit()` that reads the live `agents`/`liveSelections` at that moment. The
  `[isOpen]` effect now only CLEARS on close. Every in-modal write to host state routes
  through it: a new `handleTreeChange` wrapping `onReorder` (what `<CanvasView
  onTreeChange=…>` now receives — route/outcome editor, rename, reorder, reparent, the
  detach reconciler and `addSubAgent`), `handleSelectionsChange` (the flat levers),
  `handleRemove`, and the `AgentLibrary` add closure. A snapshot can therefore never capture
  a roster that has not arrived — a user cannot edit a tree that is not rendered — so the
  empty-array wipe is structurally impossible. `handleCancel` is unchanged apart from
  clearing the ref LAST (the restore runs through `handleSelectionsChange`, which would
  otherwise re-arm it), and `if (snapshot)` now means "nothing was edited, re-emit nothing".
  The post-save `onClose()` and "Open in full canvas" still keep their edits.
- **Re-verified:** `suites/03_launch_panels/test_iss258_advanced_modal_cancel_discards_route_edit.py`
  run 4x from `tests/integration/e2e` (offline tier, real Chrome). `--runxfail` x3: 3/3 failed
  at line 63 and ONLY line 63 — `AssertionError: Locator expected to have Value 'Step' /
  Actual value: step`, aria snapshot `combobox "Type": option "Step" [selected]`. The 2/3
  "0 agents" wipe is GONE: every run resolved `canvas-node-custom-agent:language` after the
  reopen and passed the line-57 `DIVERT_NODE count == 0` assertion. Plain run
  (`2026-08-29T00-42-local`): 1 xfailed, all three shot-steps ok; its
  `03-cancel-and-reopen.png` shows "5 AGENTS · EX_A2_BRANCH", all five nodes, the
  english/spanish/dutch route edges and no divert node. The remaining red line is still the
  test-side `to_have_value("Step")` vs the `<option value="step">` markup
  (`CanvasConfigRail.tsx:829`) — left for the verifier to correct, as a fixer does not edit a
  test to make it pass; xfail marker left in place. Regression guards:
  `AgentsPopup.reskin.test.tsx` 14/14 green; `tsc --noEmit` 6 errors, the identical
  pre-existing set FIX-349 recorded, zero in AgentsPopup.tsx; `eslint AgentsPopup.tsx`
  0 errors / 10 warnings, none in the changed region. Frontend-only — no backend restart, no
  migration, no engine or import-linter surface touched.
- **Verified:** 2026-08-29 by 6-verifier. Corrected the test-side literal on
  `suites/03_launch_panels/test_iss258_advanced_modal_cancel_discards_route_edit.py:63`
  from `to_have_value("Step")` to `to_have_value("step")` (matches
  `<option value="step">`, `CanvasConfigRail.tsx:829` — a fixer does not edit a test, so
  this was left for the verifier per FIX-365's own note). `--runxfail` x3: 3/3 XPASS clean
  (no failure at all, including the fast-open race that broke FIX-349). Removed the
  `xfail` marker, kept `@pytest.mark.issue("ISS-258")`, re-ran plain: 1 passed, 3 shots,
  9.4s. Manual re-run of the original repro by hand in the browser (qa-admin,
  `lane4`, fresh `/create/ex_A2_branch`): opened Advanced (5 agents, no divert node),
  changed the `english` outcome's Type to Workflow, picked "Spanish Greeter" — the
  "Spanish Greeter — Diverts run" node appeared as expected — clicked Cancel, reopened
  Advanced: canvas shows all 5 original agents, no divert node, "Route 3 outcomes" pill,
  and the `english` outcome's Config-tab Type combobox is back to `option "Step"
  [selected]`. No console errors/warnings (`browser_console_messages`: 0/0).
  Evidence: `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-001100-create-ex-a2-branch/04-verified-after-cancel-reopen-english-type-step.png`.
  Health: `frontend/tsc --noEmit` — same 6 pre-existing errors as FIX-365 recorded
  (`HomeLaunchGrid.crossAccountLeak.test.tsx` x4, `listenerMiddleware.test.ts` x2), zero
  in `AgentsPopup.tsx`. `backend` `:8000/docs` → 200 (no backend restart needed,
  frontend-only fix). `backend/ lint-imports` shows one broken contract
  (`agents.execution_engine.engine` → `app.api.*`), but it is entirely inside backend
  Python files this fix never touched (`AgentsPopup.tsx` is the fix's only diff) —
  unrelated to this bug, not evaluated further here. Regression:
  `frontend npx vitest run AgentsPopup.reskin.test.tsx` 14/14 green;
  `suites/03_launch_panels/test_launch_panels.py` whole-file run — the one FAILED
  (`test_the_advanced_control_opens_the_agent_roster`, "Advanced says 6 agents but the
  canvas renders 7 nodes" on `/create/user-stories`) is the documented pre-existing
  D-05/D-10 agent-count defect (already confirmed pre-existing via a stash test by the
  2026-08-28 ISS-247 verification above); the two ISS-306 xfails in that file are also
  pre-existing/unrelated. No regression traced to this fix.

## BUG-20260828-001420-workflow-create-ppt — `/workflow/create` never redirects when `mode` is absent or empty, leaving the legacy URL live and uncanonicalized

- **Page:** Legacy wizard entry URL (redirect stub)
- **Route:** /workflow/create (no query string), /workflow/create?mode= (empty value)
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 00:14 UTC
- **Found by:** bug-workflow-create-ppt-r1
- **Fingerprint:** `/workflow/create|legacy-wizard-redirect|navigate-with-no-mode-param-or-empty-mode-value|no-redirect-fires-legacy-url-serves-live-prototype-content`
- **Evidence:** `bug-hunter/evidence/workflow-create-ppt/BUG-20260828-001420-workflow-create-ppt/`
- **Validated:** 3/3 from cold start on 2026-08-28 — every cycle (bare URL, empty `mode=`, bare
  URL again) reproduced identically, no axis narrowing needed. Root cause:
  `frontend/src/app/workflow/create/page.tsx` `CreateRoute()` never calls `router.replace`
  for missing/empty `mode` — it only canonicalizes `raw === "ppt" || raw === "ppt_v2"` and
  silently renders the prototype wizard in place for everything else.
- **Root cause (analyzer, CONFIRMED):** `frontend/src/proxy.ts:8` — `if (mode) { return
  NextResponse.redirect(new URL(\`/create/${mode}\`, request.url)); }` else fall through
  unchanged (line 12's own comment: "If mode is missing, pass the request through
  unchanged"). This edge middleware (`matcher: ["/workflow/create"]`), not `page.tsx`, is
  the actual canonicalization layer — [ISS-227](../.knowledge/cards/20260828-1554-ISS-227.md)'s
  browser reproduction already proved this exact redirect fires for any truthy `mode`,
  which is why `?mode=ppt`/`?mode=prototype` do canonicalize. `searchParams.get("mode")`
  returns `null` (key absent) or `""` (key present, empty) — both falsy, both take the
  passthrough branch with zero fallback destination. `page.tsx`'s `CreateRoute()` is not
  itself a broken redirect stub; it is the passthrough content renderer for whatever
  `proxy.ts` declines to redirect, and never receives a truthy `raw` in current shipped
  behavior. `next.config.ts` (read in full) carries no `/workflow/create` rule — a comment
  in `[...view]/page.tsx:3583-3592` attributing the redirect to "next.config.ts's T17
  redirect" is stale documentation, not a functional issue.
- **Blast radius:** every in-app caller of `/workflow/create` (`CreationHub.tsx:31,35`,
  `DashboardLayout.tsx:1547,1574`, `globalSlice.ts`'s `WIZARD_ROUTES`) always passes a
  hardcoded truthy mode, so none can trigger the falsy branch — the only route in is
  external (bookmark/hand-typed/stale link), matching the hunter's direct-navigation repro
  method. Inverse direction (`/create/{mode}` redirecting back) checked and is fine — a
  deliberate non-redirect per `[...view]/page.tsx:3773-3774`'s own comment. No
  tier/theme/viewport dependency (edge-layer check, runs before auth/render).
- **Proposed fix location:** `frontend/src/proxy.ts` — extend the SAME mechanism already
  used for every other `mode` value (default the mode before building the redirect target)
  rather than adding a second, divergent client-side redirect path in `page.tsx`. See
  [ISS-227](../.knowledge/cards/20260828-1554-ISS-227.md) for the neighboring defect in the
  same function (truthy branch's destination is unsanitized) — do not reintroduce that gap
  while adding the default.
- **Issue cards:** [ISS-250](../.knowledge/cards/20260828-1645-ISS-250.md) (root — validator's
  original card, extended in this pass with the `proxy.ts` mechanism, blast radius and fix
  location), [ISS-376](../.knowledge/cards/20260828-2152-ISS-376.md) (sibling, INFERRED:
  `CreateRoute()` has no canonicalization fallback of its own — depends entirely on
  `proxy.ts` having already redirected before it renders; unreproduced, see card for what
  would confirm it)
- **Fix card:** [FIX-347](../.knowledge/cards/20260828-2318-FIX-347.md) — resolves
  [ISS-250](../.knowledge/cards/20260828-1645-ISS-250.md) (status: resolved, verification:
  passed). One line in `frontend/src/proxy.ts`: the `if (mode)` branch is gone and `mode`
  defaults — `searchParams.get("mode") || "prototype"` — before the destination is built,
  so every request matching `matcher: ["/workflow/create"]` now redirects (bare and
  `?mode=` both land on `/create/prototype`, the same wizard `page.tsx` rendered in place).
  The ISS-227 `encodeURIComponent` traversal guard on the truthy path is untouched; the
  default is a literal, not query input. Verified: `npx vitest run src/proxy.test.ts` from
  `frontend/` — both `it.fails` guards XPASS ("Error: Expect test to fail", 2 failed of 2),
  the marker left in place for the verifier. `npx eslint src/proxy.ts` clean.
  `frontend/src/app/workflow/create/page.tsx` deliberately NOT touched — that is
  [ISS-376](../.knowledge/cards/20260828-2152-ISS-376.md), INFERRED and unreproduced, still
  `open`. Frontend-only: no backend restart, no migration, no engine or import-linter
  surface involved.
- **Verified:** `cd frontend && npx vitest run src/proxy.test.ts` — both cases observed XPASS
  first ("Error: Expect test to fail", 2 failed of 2, confirming the pre-fix `it.fails`
  markers), then the `it.fails` wrappers removed and re-run: 1 file / 2 tests passed, plain
  green. Regression: `npx vitest run src/lib/routes.test.ts` — 59 passed. `npx tsc --noEmit`
  shows only pre-existing unrelated errors in `HomeLaunchGrid.crossAccountLeak.test.tsx` and
  `listenerMiddleware.test.ts` (neither touched by this fix). `npx eslint src/proxy.ts
  src/proxy.test.ts` clean. Backend `:8000/docs` → 200 (frontend-only fix, no restart
  needed). Manual re-run of the original repro in Chrome (lane5, qa-admin, signed in): bare
  `http://localhost:3000/workflow/create` now lands on `http://localhost:3000/create/prototype`;
  `?mode=` (empty) also lands on `/create/prototype`; baseline `?mode=ppt` still lands on
  `/create/ppt` (unchanged). No console errors/warnings on any of the three navigations.
  After-screenshot: `bug-hunter/evidence/workflow-create-ppt/BUG-20260828-001420-workflow-create-ppt/04-verified-bare-url-now-redirects-to-create-prototype.png`.

### Summary
C-1/the documented redirect behavior covers `/workflow/create?mode=ppt` and
`?mode=prototype`, both of which correctly `router.replace` to `/create/ppt` /
`/create/prototype` (verified as a working baseline in this investigation — see evidence
01). But the redirect only fires when `mode` carries a truthy value. Navigating to
`/workflow/create` with **no query string at all**, or with `?mode=` (present but empty),
never redirects — `location.href` stays on the legacy `/workflow/create` URL indefinitely
(confirmed after full navigation and settle, not just a client-side transition). Despite the
URL not canonicalizing, the page is not blank or broken: it silently renders the full
"Configure your prototype" wizard (h1 "Configure your prototype") with live, successful API
calls (`GET /api/workflows/prototype`, `/api/prototype/templates`, `/api/prototype/design-systems`
all 200 OK) — i.e. an undocumented default-to-prototype fallback that keeps the legacy URL
permanently alive and functional instead of ever canonicalizing to `/create/prototype`. This
means any old bookmark, external link, or hand-typed URL missing the `mode` param becomes a
permanent, un-redirected alias into current app functionality — the opposite of what a redirect
stub is supposed to guarantee (a single canonical live URL per feature).

### Reproduction
1. Signed in as qa-admin (session inherited, `auth_token` present).
2. Navigate to `http://localhost:3000/workflow/create?mode=ppt` — confirm baseline: URL becomes
   `/create/ppt` (redirect works correctly for a valid, non-empty mode).
3. Navigate to `http://localhost:3000/workflow/create` (bare, no query string at all, full
   `page.goto` navigation). Observe: URL stays `http://localhost:3000/workflow/create` — no
   redirect fires. `document.querySelector('h1').textContent` reads "Configure your prototype";
   network shows successful `GET /api/workflows/prototype`, `/api/prototype/templates`,
   `/api/prototype/design-systems` (all 200 OK) — the prototype wizard is fully live under the
   legacy URL.
4. Navigate to `http://localhost:3000/workflow/create?mode=` (mode present but empty). Observe
   the identical result: URL stays `/workflow/create?mode=`, h1 stays "Configure your prototype",
   same live wizard renders — reproducing the defect a second time with a slightly different
   trigger (empty string vs. entirely missing key).
5. Confirmed no console errors or warnings in either state.

### Expected
A redirect stub is expected to canonicalize every reachable variant of its route to the real
target URL, or otherwise fail cleanly (404/error state). At minimum, missing or empty `mode`
should not silently fall through to rendering full, live application content under the stale
legacy URL — either redirect to a sensible default (e.g. `/create/prototype` or `/create`), or
show an explicit "missing mode" error, consistent with how `?mode=ppt`/`?mode=prototype` behave.

### Actual
`/workflow/create` with no `mode` param, or with `mode` present but empty, never triggers the
redirect at all. The legacy URL stays in the address bar while the app quietly renders a fully
functional prototype wizard underneath it, giving the legacy route a permanent, working, second
identity for the same feature instead of ever being canonicalized away.

### Evidence
- Baseline (`?mode=ppt` redirects correctly to `/create/ppt`): `bug-hunter/evidence/workflow-create-ppt/BUG-20260828-001420-workflow-create-ppt/01-baseline-mode-ppt-redirects-correctly.png`
- Failure (bare `/workflow/create`, no query, stays on legacy URL, prototype wizard renders): `bug-hunter/evidence/workflow-create-ppt/BUG-20260828-001420-workflow-create-ppt/02-failure-bare-no-query-stays-on-legacy-url.png`
- Reproduced (`?mode=` empty value, same result): `bug-hunter/evidence/workflow-create-ppt/BUG-20260828-001420-workflow-create-ppt/03-repro2-empty-mode-param-same-result.png`

### Browser Signals
- Console: no relevant error observed in either failing state.
- Network: all API calls made by the fallback-rendered prototype wizard return 200 OK
  (`/api/workflows/prototype`, `/api/prototype/templates`, `/api/prototype/design-systems`),
  confirming this is a genuinely functional page, not a broken/error render — which is exactly
  what makes the missing canonicalization more likely to go unnoticed.
- State/URL: `location.href` never changes away from `/workflow/create` (with or without the
  empty `mode=`) in either reproduction, contrasted directly against the working `?mode=ppt`
  baseline captured in the same session.

## BUG-20260828-001720-workflow-create-prototype — Invalid `mode` value redirects into a permanently dead-end 0-agent composer with the underlying 404 silently swallowed

- **Page:** Legacy wizard entry URL for the prototype mode
- **Route:** /workflow/create?mode=nonsense (any unrecognized, non-empty `mode` value)
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 00:17 UTC
- **Found by:** bug-workflow-create-prototype-r1
- **Fingerprint:** `/workflow/create|mode-param-redirect|navigate-with-unrecognized-nonempty-mode-value|redirects-to-generic-0-agent-composer-permanently-disabled-no-error-shown`
- **Tests:** [ISS-374](../.knowledge/cards/20260828-2146-ISS-374.md) →
  `tests/integration/e2e/suites/03_launch_panels/test_iss374_unrecognized_slug_dead_end.py`;
  [ISS-375](../.knowledge/cards/20260828-2147-ISS-375.md) →
  `tests/integration/e2e/suites/03_launch_panels/test_iss375_transient_fetch_failure_dead_end.py`
  (both observed red, xfail strict pending fix)
- **Evidence:** `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-001720-workflow-create-prototype/`
- **Fixed:** 2026-08-28 by 5-fixer. [FIX-351](../.knowledge/cards/20260828-2347-FIX-351.md) —
  `IdeaInputPage.tsx`'s manifest-fetch `.catch()` now sets a rendered `loadError`
  (`"not-found"` vs `"failed"`, told apart by the new shared `isNotFoundError` predicate in
  `frontend/src/lib/api.ts`) instead of swallowing every rejection into "nothing declared".
  Shown beside the disabled buttons when the roster is empty; `migration` excluded, being the
  one `WorkflowType` that 404s by design. Observed: `test_iss374_unrecognized_slug_dead_end.py`
  and `test_iss375_transient_fetch_failure_dead_end.py` each 1 `[XPASS(strict)]` (the pass
  signal) + 1 still-xfail; markers left for 6-verifier. Live after the change, signed in as
  qa-admin: `/create/nonsense` shows "not found", `/create/migration`, `/create/custom` and
  `/create/prototype` show nothing.
- **For the verifier:** the SECOND test in each of those two files asserts `Save workflow`
  becomes ENABLED — a different remedy from the one ISS-374 §Fix and ISS-375 §Fix chose
  (surface the error, do not invent a roster). Both still xfail and were NOT edited.
  `/create/custom`'s Save is disabled on a fully successful fetch too
  (`IdeaInputPage.tsx:1246-1247`, KAN-112: custom starts blank by design), so that one
  cannot pass without breaking KAN-112. Choosing the fallback branch instead is a product
  decision, not a fix.
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — redirect fires, `GET /api/workflows/nonsense` 404s, no error text anywhere in `document.body.innerText`, and `Save workflow`/`Save as my version`/`Add agents first` stay `disabled === true` before and after filling a full brief. Trigger: any unrecognized, non-empty `mode`/slug value on `/workflow/create`.
- **Issue card:** [ISS-253](../.knowledge/cards/20260828-1646-ISS-253.md) (validator's reproduction record — superseded, see below)
- **Root cause:** `IdeaInputPage.tsx:1012` fetches `getWorkflowDetail`; its `.catch()` at
  `IdeaInputPage.tsx:1172-1181` swallows the 404 with no error state; the roster effect at
  `IdeaInputPage.tsx:1228-1264` then computes `pipelineAgents = manifestAgents ?? fromLibrary`
  = `[]` because both are empty, so `Save workflow`/`Save as my version`/Run stay
  `disabled={pipelineAgents.length === 0}` forever (`IdeaInputPage.tsx:1649,1664,1675`).
  Corrects [ISS-253](../.knowledge/cards/20260828-1646-ISS-253.md), which cited
  `ComposerPage.tsx` — that component is never rendered by this route (`/create/{slug}` maps
  to `mainView: "input"` → `IdeaInputPage`, not `"composer"` → `ComposerPage`).
- **Blast radius:** all 6 real callers of `getWorkflowDetail` checked. Broken the same way:
  `IdeaInputPage.tsx:1012` (this bug) and `page.tsx:452-499`'s `builtinCanvasType` effect
  (already tracked as [ISS-299](../.knowledge/cards/20260828-1730-ISS-299.md), a different
  bug). Not broken: `ComposerPage.tsx:410-439` (swallow doesn't gate Save),
  `LaunchWizard.tsx:373-412` (mode is a closed union, library fallback always non-empty),
  `IdeaInputPage.tsx:1436` (unreachable without a prior successful fetch),
  `WorkflowDialog.tsx:73-91` (already surfaces its error correctly). See
  [ISS-374](../.knowledge/cards/20260828-2146-ISS-374.md) for the full table.
- **Issue cards:** [ISS-374](../.knowledge/cards/20260828-2146-ISS-374.md) (root — corrects
  ISS-253, sets its status to superseded), [ISS-375](../.knowledge/cards/20260828-2147-ISS-375.md)
  (sibling, INFERRED: a real manifest-only/composed workflow would dead-end identically on any
  transient `getWorkflowDetail` failure, not only a nonexistent slug — the same catch never
  branches on `ApiError.status`)
- **Verified:** 2026-08-28 by 6-verifier. Ran `test_iss374_unrecognized_slug_dead_end.py`
  and `test_iss375_transient_fetch_failure_dead_end.py` individually — each file's first test
  (the one FIX-351 targeted) observed `[XPASS(strict)]` on the pre-change marker, `xfail`
  removed from that test, re-run gave a plain exit-0 pass for both files (second test in each
  file, which asserts the different "Save becomes enabled" remedy FIX-351 explicitly did not
  choose, correctly stays `xfail`; `@pytest.mark.issue` kept on all four). Manual repro from
  this entry's own Reproduction section, driven by hand in real Chrome (qa-admin, cold
  `/workflow/create?mode=nonsense` navigation, twice): redirect to `/create/nonsense` fires,
  `GET /api/workflows/nonsense` still 404s, but `document.body.innerText` now contains
  `Workflow "nonsense" not found — go back and pick one from the dashboard.` (was completely
  absent before the fix); the three action buttons remain `disabled === true`, matching
  FIX-351's documented scope (surfacing the error, not inventing a roster). Spot-checked
  `/create/custom` shows no false-positive banner on a healthy load. After-screenshot:
  `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-001720-workflow-create-prototype/04-after-verified-error-banner.png`.
  Health: `:8000/docs` → 200 (no restart needed, frontend-only change); `npx tsc --noEmit` →
  same 6 pre-existing errors in two other agents' untouched test files, zero in
  `IdeaInputPage.tsx`/`api.ts`; `lint-imports` (run from `backend/`) → 1 pre-existing broken
  contract (`agents.execution_engine.engine` → `app.api`), unrelated, no backend file touched
  by this fix; regression file `suites/03_launch_panels/test_launch_panels.py` → 2 failures,
  both the exact pre-existing order-dependent/read-race flakes FIX-351's own verification
  section already documents, not caused by this change.

### Summary
This is a distinct failure mode from the already-filed `BUG-20260828-001420-workflow-create-ppt`
(missing/empty `mode` never redirects and silently falls back to a fully functional prototype
wizard under the stale legacy URL). Here the trigger is different — an unrecognized but
**non-empty** `mode` value, e.g. `mode=nonsense` — and the symptom is different too: the redirect
DOES fire (`/workflow/create?mode=nonsense` → `/create/nonsense`, treating "nonsense" as a
workflow slug), but `/create/nonsense` is not a real workflow. `GET /api/workflows/nonsense`
returns `404 Not Found` (confirmed twice via console), yet the page renders a normal-looking
"Provide the brief" generic workflow composer with zero visible indication that anything failed
— no error banner, no toast, no "workflow not found" message anywhere in `document.body.innerText`.
The composer is permanently stuck at "0 agents": `Save workflow`, `Save as my version`, and
`Add agents first` all render with the HTML `disabled` attribute set and stay disabled even after
typing a full, valid, non-trivial brief into the textbox (verified via direct DOM `button.disabled`
reads before and after filling the brief). There is no way to add an agent, save, or run anything
— a genuine, silent dead end reachable via a completely ordinary-looking URL typo (a stray
character in `mode=`), with the only evidence of failure being a console 404 a typical user would
never see.

### Reproduction
1. Signed in as qa-admin (session inherited).
2. Navigate to `http://localhost:3000/workflow/create?mode=nonsense`. Observe the redirect fires
   to `/create/nonsense` (URL bar changes, confirming this is treated as a workflow-slug lookup,
   not the `mode=ppt`/`mode=prototype` special-cased redirect).
3. Observe the console: `GET http://localhost:8000/api/workflows/nonsense` returns `404 Not Found`.
4. Observe the rendered page: heading "Provide the brief", "Advanced 0 agents" button, and no
   error text anywhere in `document.body.innerText` — the 404 is completely invisible in the UI.
5. Confirm via DOM that `Save workflow`, `Save as my version`, and `Add agents first` all have
   `disabled === true`.
6. Type a full, valid brief ("Build a test app with enough characters to satisfy validation")
   into the "Brief description" textbox. Re-check the same three buttons — all three remain
   `disabled === true`, unchanged. There is no action on this page that can ever be completed.
7. Did a fresh, independent page navigation (not just a state re-check) to the same URL a second
   time — identical result: 404 in console, 0-agent dead-end composer, all three action buttons
   disabled, no error message, deterministic across both attempts.

### Expected
An unrecognized `mode`/workflow slug should either show an explicit "workflow not found" error
(with a way back to a valid start point), or fall back to a real, usable default (as the
missing-mode case does, however incorrectly, by defaulting to a working prototype wizard) —
either way, the resulting page should not silently present a normal-looking but permanently
non-functional composer with no indication that anything is wrong.

### Actual
The page renders what looks like an ordinary, empty workflow composer, giving no indication that
`/api/workflows/nonsense` 404'd. Every possible action (save, save-as, add agents) is permanently
disabled regardless of what the user types into the brief field, so the page is an unrecoverable
dead end reachable via nothing more than a mistyped `mode` query value.

### Evidence
- Before: `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-001720-workflow-create-prototype/01-before-mode-nonsense.png`
- Failure (brief filled, buttons still disabled): `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-001720-workflow-create-prototype/02-failure-brief-filled-still-disabled.png`
- Reproduced (fresh independent navigation): `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-001720-workflow-create-prototype/03-repro2-fresh-load.png`

### Browser Signals
- Console: `GET http://localhost:8000/api/workflows/nonsense` → `404 Not Found`, on both
  reproduction attempts, with no corresponding UI error surfaced.
- Network: same 404 confirmed via console entries; no other failed requests.
- State/URL: `location.href` settles on `/create/nonsense` (the redirect itself works); the defect
  is entirely in the resulting page's failure to reflect the 404 or offer any usable action.

## BUG-20260828-003300-workflows — Escape does not close a saved-workflow card's "Workflow actions" dropdown menu

- **Page:** My Workflows (saved workflows list)
- **Route:** /workflows
- **Severity:** Low
- **Status:** UNREPRODUCIBLE
- **Found at:** 2026-08-28 00:33 UTC
- **Found by:** bug-workflows-r1
- **Fingerprint:** `/workflows|workflow-actions-dropdown-menu|press-escape-while-menu-open|menu-remains-open-aria-expanded-stays-true`
- **Evidence:** `bug-hunter/evidence/workflows/BUG-20260828-003300-workflows/`

### Summary
Each saved-workflow card on `/workflows` has a `button[aria-label='Workflow actions']` that opens
a small dropdown menu (`Edit` / `Rename` / `Duplicate` / `Delete`). The menu is correctly
scoped per-card (opening it on "My presentation" only ever shows/affects "My presentation" —
verified separately) and it DOES close correctly when the page's invisible outside-click overlay
(`div.fixed.inset-0.z-10`, rendered behind the menu specifically to catch outside clicks) receives
a genuine mouse click. However, pressing the **Escape** key while the menu is open has no effect
at all: the trigger button's `aria-expanded` attribute stays `"true"` and the menu list stays
visually present and interactive. This was verified with real Playwright keyboard events
(`page.keyboard.press('Escape')`), not synthetic/no-op JS calls, and reproduced twice on two
different cards ("My presentation" and "My prototype"). This is a distinct component and route
from the already-filed `BUG-20260827-221400-dashboard` (Escape not closing the dashboard catalog
card's "Inspect details" modal, a full `role="dialog"` overlay with Context Providers/
Capabilities/Compaction sections on `/dashboard`) — here the affected control is a lightweight
per-card action dropdown on the My Workflows list, reachable only via `/workflows`, with a
completely different purpose (workflow management actions vs. a read-only info panel) and a
different close mechanism (an outside-click overlay that itself works fine, unlike the dashboard
modal's X-only close).

### Reproduction
1. Sign in as qa-admin, navigate to `/workflows`.
2. Locate the "My presentation" card and click its `button[aria-label='Workflow actions']`
   (scoped via the card's unique title text, per the definition's `deleteWorkflow` recipe
   approach). Observe the menu opens: `Edit`, `Rename`, `Duplicate`, `Delete`, and the trigger
   button's `aria-expanded` reads `"true"`.
3. Press the Escape key (`page.keyboard.press('Escape')`, a genuine keyboard event).
4. Observe: the menu is still fully visible and interactive; `aria-expanded` on the trigger button
   is still `"true"`.
5. For contrast, confirm the menu's own outside-click handling otherwise works: a genuine
   Playwright mouse click on the invisible `div.fixed.inset-0.z-10` overlay rendered behind the
   open menu correctly closes it (`aria-expanded` becomes `"false"`, no menu items visible).
6. Repeated steps 2-4 on a second, different card ("My prototype") — identical result: Escape has
   no effect, `aria-expanded` stays `"true"` after the key press.

### Expected
Pressing Escape while the "Workflow actions" dropdown is open should close it, consistent with
standard menu/dropdown dismissal behavior and with the fact that this same menu already responds
correctly to an outside click.

### Actual
Escape is not wired to the menu's close handler at all — the menu remains open indefinitely after
Escape, and only an outside click (or presumably selecting a menu item) dismisses it.

### Evidence
- Before (menu open on "My presentation"): `bug-hunter/evidence/workflows/BUG-20260828-003300-workflows/01-before-menu-open.png`
- Failure (Escape pressed, menu still open): `bug-hunter/evidence/workflows/BUG-20260828-003300-workflows/02-failure-escape-pressed-menu-still-open.png`
- Contrast (a genuine outside click on the overlay does close it): `bug-hunter/evidence/workflows/BUG-20260828-003300-workflows/03-outside-click-does-correctly-close-menu.png`
- Reproduction 2, before (menu open on "My prototype"): `bug-hunter/evidence/workflows/BUG-20260828-003300-workflows/04-repro2-before-escape-my-prototype.png`
- Reproduction 2, after (Escape pressed, still open): `bug-hunter/evidence/workflows/BUG-20260828-003300-workflows/05-repro2-after-escape-still-open.png`

### Validation (2026-08-28)
0/3 reproduced from a cold start using a genuine UI click (Playwright's `locator.click()`, a real
synthetic mouse event, not a JS `element.click()` call) to open the "Workflow actions" menu:

- Cycle 1: cold nav to `/workflows` -> real click on "My presentation" card's Workflow actions
  button (`aria-expanded` -> `"true"`) -> `page.keyboard.press('Escape')` -> menu closed,
  `aria-expanded` -> `"false"`. Screenshot confirms menu gone, trigger button shows a focus ring.
  Evidence: `bug-hunter/evidence/workflows/_scratch/attempt1-after-escape.png`.
- Cycle 2: cold nav -> real click on "My prototype" card's Workflow actions button -> Escape ->
  menu closed correctly.
- Cycle 3: cold nav -> real click on "My prototype" card again (fresh page load) -> Escape ->
  menu closed correctly. Also swept narrow viewport (1024x768) on a 4th open/close of "My
  presentation" — Escape still closed it.

Axes tried: entry mechanism (real click vs JS-dispatched `element.click()` via
`page.evaluate` — the latter, which does NOT move `document.activeElement` to the trigger
button in this app, is the one case where Escape failed to close the menu; evidence
`bug-hunter/evidence/workflows/_scratch/attempt2-after-escape-jsclick.png`), card (My
presentation, My prototype, first card in list), viewport (1280x800 default and 1024x768
narrow), timing (Escape pressed immediately after open, no settle delay). Theme was not swept
(default/light only) — implausible for a keydown-handler bug and out of scope given severity.

The only condition under which Escape appeared not to close the menu was opening it via a raw
JS `element.click()` call that leaves the trigger unfocused — not a path a real user (mouse or
keyboard) can reach; every genuine-click cold start (the standard reproduction method) closed
the menu correctly. This is UNREPRODUCIBLE via real user interaction; the original report's
finding is most likely an artifact of how the hunter agent dispatched the opening click, not a
real defect. No issue card minted. No duplicate check needed since nothing is being filed.

### Browser Signals
- Console: no relevant error observed.
- Network: no request involved; purely client-side dropdown/menu state.
- State/URL: URL stays `/workflows` throughout; `aria-expanded` on the `button[aria-label='Workflow actions']`
  trigger read directly via DOM both before and after the Escape key press to confirm the state
  change (or lack thereof), not just a screenshot read.

## BUG-20260828-003800-workflows-new — Leaving the new-workflow composer via its own "Back" control silently discards all unsaved work with no confirmation

- **Page:** Empty composer / canvas (new custom workflow)
- **Route:** /workflows/new
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 00:38 UTC
- **Found by:** bug-workflows-new-r1
- **Fingerprint:** `/workflows/new|composer-back-button|click-back-with-unsaved-agents-and-name|work-discarded-no-confirmation`
- **Evidence:** `bug-hunter/evidence/workflows-new/BUG-20260828-003800-workflows-new/`
- **Validated:** 3/3 on 2026-08-28, cycle 1 (also reproduced cycles 2 and 3, including with
  Back clicked immediately after the modal close with no settle wait) — the composer's own
  Back button discards unsaved name+agents unconditionally, no timing/entry-path dependency.
- **Root cause:** `ComposerPage`'s Back button (`frontend/src/components/workflow/composer/ComposerPage.tsx:979`,
  `onClick={onBack}`) has no dirty-check gate. `onBack` is the shared `handleBackNav`
  (`frontend/src/components/layout/DashboardLayout.tsx:1701-1712`), which unconditionally calls
  `router.back()` / `router.push(routes.home())` with zero visibility into any mounted child's
  uncommitted state — it only clears its own cross-cutting state (questionnaire, pending run).
- **Blast radius:** `handleBackNav` is wired as `onBack` to all 5 of `DashboardLayout`'s page
  mounts (confirmed via `grep -rn "onBack=" frontend/src`, excluding tests): `WorkflowHistory`
  (:2767), `AccountSettings` (:2849), `AnalyticsPage` (:2863), `IdeaInputPage` (:2893),
  `ComposerPage` (:2946 — shared by both `/workflows/new` and `/workflows/{id}/edit`). Every one
  calls `onBack` raw with no gate at its own call site either. `AnalyticsPage` is read-only (not
  at risk); `IdeaInputPage` (brief text + agent picks), `AccountSettings` (password-change fields
  + pending model pick), and the composer's `/workflows/{id}/edit` mount (edits to an
  already-saved workflow) all carry real unsaved user input behind the identical flaw.
- **Fixed:** 2026-08-28 by FIX-352 — `handleBackNav` (`DashboardLayout.tsx`) now confirms via
  `window.confirm` when the mounted page reports unsaved work, and `ComposerPage` feeds that
  signal through a new `onUnsavedChange` prop (name + roster snapshot vs a baseline rebaselined
  on library re-seed and on save). Verified by
  `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py::test_back_button_confirms_before_discarding_unsaved_work`
  → **XPASS(strict)** (the strict xfail marker is deliberately left in place for 6-verifier).
  Fix card: [FIX-352](../.knowledge/cards/20260828-2346-FIX-352.md)
- **Verified:** 2026-08-28 by 6-verifier — ran
  `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py::test_back_button_confirms_before_discarding_unsaved_work`
  standalone: XPASS(strict) confirmed with the xfail marker in place, marker removed,
  re-run plain green. Full-file regression run (24 scenarios): 22 passed, the same 2
  pre-existing failures FIX-352 already attributed to unrelated concurrent work
  (`test_editing_a_saved_workflow_loads_its_steps`, shared-fixture `assert 3 == 4`;
  `test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot`, BUG-20260828-005700
  guard-copy work) and nothing new. Manually re-ran the original repro by hand as qa-admin
  in the browser (lane6): named a workflow, added Domain Discovery Agent (unsaved, "1
  agents"), clicked the composer's own Back button — native `confirm()` fired with
  "You have unsaved changes. Leave anyway? Your work will be lost."; Cancel kept the
  page on `/workflows/new` with the name and agent intact. No console errors on the
  page. `tsc --noEmit` shows only the same 2 pre-existing errors FIX-352 already
  flagged as unrelated; `lint-imports` (run from `backend/`) shows one pre-existing
  broken contract unrelated to this frontend-only change (no backend `.py` touched).
  Evidence: `bug-hunter/evidence/workflows-new/BUG-20260828-003800-workflows-new/03-verify-before-back.png`,
  `04-after-fix-cancel-preserves-work.png`.
- **Fix belongs in:** `handleBackNav` itself (or a wrapper it calls) — the one place all 5
  callers already route through — fed by a per-child "is this dirty" signal, rather than a
  `confirm()` sprinkled into each of the 5 `onClick` handlers separately.
- **Issue cards:** [ISS-275](../.knowledge/cards/20260828-1855-ISS-275.md) (root — updated this
  pass with Blast radius + Fix-location sections and Related links),
  [ISS-371](../.knowledge/cards/20260828-2140-ISS-371.md) (sibling, INFERRED: IdeaInputPage),
  [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md) (sibling, INFERRED: AccountSettings),
  [ISS-373](../.knowledge/cards/20260828-2142-ISS-373.md) (sibling, INFERRED: composer edit-mode
  on `/workflows/{id}/edit`)

### Summary
On `/workflows/new`, after naming the workflow and adding an agent to the canvas (real,
unsaved, in-progress composer state — never persisted, since "Save workflow" was never
clicked), clicking the composer's own `button "Back"` control (top-left, immediately left of
the workflow name field) navigates straight to `/workflows` with zero confirmation prompt. All
in-progress work — the workflow name and every added agent node — is silently and irrecoverably
discarded. Returning to `/workflows/new` afterward shows a completely blank "Untitled workflow"
canvas with 0 agents; there is no draft-recovery mechanism. This reproduces identically via a
plain client-side route navigation (`page.goto`) to another in-app route while unsaved work is
present — neither the in-page Back button nor a direct navigation away triggers any
"unsaved changes" warning (no `beforeunload` prompt, no in-app confirm dialog).

### Reproduction
1. Sign in as qa-admin, navigate to `/workflows/new` (empty composer, 0 agents).
2. Type a name into the "Workflow name" textbox, e.g. "Bug Hunter Throwaway Draft".
3. Click "Add agent", add "Domain Discovery Agent" from the library modal, press Escape to
   close the modal. Canvas now shows the named workflow with 1 agent (`1 agents` in the header
   summary) — none of this has been saved (Save workflow was never clicked).
4. Click the composer's `button "Back"` (top-left, next to the workflow name field).
5. Observe: navigation to `/workflows` happens immediately with no confirmation dialog of any
   kind.
6. Navigate back to `/workflows/new`. Observe: the composer is completely reset — "Untitled
   workflow" placeholder, 0 agents, no trace of the name or the added agent.

### Expected
Either the "Back" control (and any other away-navigation while the composer has unsaved,
uncommitted agents/name) should prompt the user to confirm discarding their in-progress work
(a "You have unsaved changes — leave anyway?" dialog), or the composer should preserve/restore
a draft so returning to `/workflows/new` does not start from a totally blank canvas.

### Actual
The composer's own Back button discards all unsaved state (name + every added agent) with no
warning whatsoever, and there is no draft persisted anywhere the user can recover.

### Evidence
- Before leaving (named workflow with 1 agent, unsaved): `bug-hunter/evidence/workflows-new/BUG-20260828-003800-workflows-new/01-before-leave-with-work.png`
- After returning to /workflows/new (work gone, no warning was ever shown): `bug-hunter/evidence/workflows-new/BUG-20260828-003800-workflows-new/02-after-back-work-gone.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no request fired for the discarded work (never persisted, confirming it was pure
  client-side composer state that had no save/draft path at all).
- State/URL: URL transitions cleanly from `/workflows/new` to `/workflows` and back to
  `/workflows/new`; no dialog/alert intercepted the navigation at any point.

## BUG-20260828-004300-workflows-id — Saved-workflow detail view lists agents by raw internal slug instead of the friendly display name used everywhere else in the app

- **Page:** Saved workflow — read-only detail view
- **Route:** /workflows/{id}
- **Severity:** Low
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `frontend/src/components/savedworkflows/WorkflowDetailView.test.tsx`
  observed XPASS pre-removal (`npx vitest run` → "2 tests | 2 failed", each "Error: Expect test
  to fail"), `it.fails` markers removed, re-run plain green (2 passed). Neighbour regression file
  `SavedWorkflowsPage.test.tsx` 9/9 green. `npx tsc --noEmit -p tsconfig.json` → 9 pre-existing
  errors, none in `savedworkflows/` or naming `WorkflowDetailView.tsx` (login.a11y.test.tsx,
  HomeLaunchGrid.crossAccountLeak.test.tsx, api.sessionExpiryRedirect.test.ts,
  listenerMiddleware.test.ts — unrelated). `:3000/dashboard` and `:8000/docs` both 200 (frontend
  fix, no restart needed). Manual repro by hand in Chrome (lane4), signed in as qa-admin: first
  attempt hit a stale qa-basic session in this lane's profile and 404'd (qa-basic has no saved
  workflows) — re-signed-in as qa-admin, then navigated
  `/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` twice (cold nav + reload): both times the
  "2 AGENTS" list rendered "Documentation Agent" / "Spec Writer Agent" (real catalog names),
  never the raw `documentation-agent` / `prototype-specify` slugs. 0 console errors both loads.
  Screenshot: `bug-hunter/evidence/workflows-id/BUG-20260828-004300-workflows-id/03-after-fix-friendly-names.png`.
  ISS-490 (custom-agent manifest fallback) stays proven by unit test only — no seeded workflow
  with a renamed custom-agent instance existed to re-check live; not a blocker for this bug's
  root symptom.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic across cold navigation, dashboard-then-back nav, and full about:blank reload
- **Tested:** 2026-08-29 — `frontend/src/components/savedworkflows/WorkflowDetailView.test.tsx`,
  2 `it.fails` tests (ISS-327, ISS-490), both observed red for the documented reason
  (`npx vitest run` → "2 expected fail").
- **Issue card:** [ISS-327](../.knowledge/cards/20260828-2033-ISS-327.md)
- **Found at:** 2026-08-28 00:43 UTC
- **Found by:** bug-workflows-id-r1
- **Fingerprint:** `/workflows/{id}|agent-roster-list|render-saved-workflow-agent_ids|raw-agent-slug-shown-instead-of-friendly-name`
- **Evidence:** `bug-hunter/evidence/workflows-id/BUG-20260828-004300-workflows-id/`
- **Root cause:** CONFIRMED — `WorkflowDetailView.tsx:29,52-56` maps `workflow.agent_ids` straight
  into `<li>{id}</li>` with no lookup step at all. Every sibling surface (Library page, this same
  workflow's own Composer/`edit` view) instead resolves each id through `useAgentLibrary()`'s
  `allAgents` (Redux, populated from `GET /api/agents/library`) via `.find(a => a.id === id)` —
  see `ComposerPage.tsx:207,272-281` and `LibraryPage.tsx:497,592` for the established pattern.
  `WorkflowDetailView` never calls `useAgentLibrary()` at all.
- **Blast radius:** grepped every frontend consumer of `agent_ids` (`grep -rn "agent_ids"
  frontend/src`, 34 hits). `WorkflowDetailView.tsx` is the ONLY renderer of raw id strings — its
  single call site is `frontend/src/app/[...view]/page.tsx:3820`. `SavedWorkflowsPage.tsx`
  (`:255,329,380`) and `CanvasNode.tsx:126` also read `agent_ids` but only for a numeric count,
  confirmed safe. No other current broken caller.
- **Fix belongs in:** `WorkflowDetailView.tsx` itself (single call site) — call `useAgentLibrary()`
  and resolve each `agentIds` entry to its `AgentDef` the same way `ComposerPage`/`LibraryPage`
  already do, rendering `.name`/`.role` with the raw id only as a last-resort fallback.
- **Issue cards:** [ISS-327](../.knowledge/cards/20260828-2033-ISS-327.md) (root — pre-existing,
  root cause independently re-confirmed by this pass),
  [ISS-490](../.knowledge/cards/20260828-2351-ISS-490.md) (INFERRED sibling — a catalog-only fix
  still mislabels custom-agent instances, whose real name lives in `workflow.manifest.steps`, not
  the catalog `useAgentLibrary()` exposes)
- **Fix card:** [FIX-390](../.knowledge/cards/20260829-0303-FIX-390.md) — `WorkflowDetailView.tsx` now resolves each `agent_ids` entry through `useAgentLibrary()`'s
  `allAgents`, falling back to the workflow's own manifest (`manifestStepsToAgents` + `findAgentInTree`, de-prefixed with `CUSTOM_AGENT_PREFIX`) for
  `custom-agent:<instance_id>` steps the catalog cannot carry; the raw id survives only as the last-resort fallback. Both `it.fails` tests in
  `frontend/src/components/savedworkflows/WorkflowDetailView.test.tsx` now XPASS ("Error: Expect test to fail", 2/2) — markers left in place for the 6-verifier.
  ISS-490 stays proven by unit test only: no seeded workflow holds a renamed custom-agent instance, so its live browser check is still open.

### Summary
The read-only detail view for a saved workflow (`/workflows/{id}`) renders its agent roster by
printing the raw `agent_ids` values verbatim — e.g. `documentation-agent`, `prototype-specify` —
straight from `GET /api/user-workflows/{id}`, with no lookup against the agent catalog. Every
other place in the app that displays these same two agents resolves them to a human-readable
name and role/subtitle instead: the Library page shows "Documentation Agent" / "API & Technical
Writing", and this exact saved workflow's own Composer canvas (`/workflows/{id}/edit`) shows
"Documentation" / "API & Technical Writing" and "Spec Writer" / "Specification & Architecture"
for the identical `documentation-agent` / `prototype-specify` ids. The one screen whose entire
purpose is to summarize a saved workflow for a human reader is the one screen that fails to
resolve the names, showing raw internal identifiers instead. Confirmed against the live API
response (`agent_ids: ["documentation-agent", "prototype-specify"]`) so this is not a stale-data
issue — it is the display component itself never mapping the id to a label, unlike its sibling
composer view which clearly has that mapping available and uses it.

### Reproduction
1. Sign in as qa-admin, navigate directly to `http://localhost:3000/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0`
   ("My prototype", a seeded saved workflow — deep-link only, per known D-28).
2. Observe the "2 AGENTS" list renders two rows reading exactly `documentation-agent` and
   `prototype-specify` — raw, hyphenated, lower-case internal ids, not sentence-case names.
3. Click "Edit" to open the same workflow's Composer (`/workflows/{id}/edit`). Observe the canvas
   nodes for the identical two agents show friendly labels: "Documentation" (subtitle "API &
   Technical Writing") and "Spec Writer" (subtitle "Specification & Architecture").
4. For a third data point, navigate to `/library` and locate the `documentation-agent` card —
   it displays "Documentation Agent" / "API & Technical Writing", confirming the friendly-name
   mapping is a standard, app-wide convention for this exact agent id, not something specific to
   the composer.
5. Cross-checked the live API directly: `GET /api/user-workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0`
   returns `"agent_ids": ["documentation-agent", "prototype-specify"]` — confirming the detail
   view is printing the raw field value with no name resolution, while its sibling views resolve
   the same ids to display names.
6. Reloaded `/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` a second time — identical raw-slug
   rendering both times, deterministic.

### Expected
The saved-workflow detail view's agent roster should resolve each `agent_id` to the same
human-readable display name (and ideally role subtitle) that the Library page and this
workflow's own Composer/Edit view already show for the identical agents.

### Actual
The detail view prints the raw, internal `agent_id` strings verbatim (`documentation-agent`,
`prototype-specify`) with no name resolution, while every other agent-listing surface in the app
— including this exact workflow's own Edit page — shows friendly names for the same ids.

### Evidence
- Detail view showing raw agent slugs: `bug-hunter/evidence/workflows-id/BUG-20260828-004300-workflows-id/01-detail-raw-agent-slugs.png`
- Composer/Edit view for the same workflow showing friendly names for the same two agents: `bug-hunter/evidence/workflows-id/BUG-20260828-004300-workflows-id/02-composer-friendly-names-same-agents.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/user-workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` returns
  `agent_ids: ["documentation-agent", "prototype-specify"]` verbatim — matches what the detail
  view renders unresolved, confirming the gap is in the detail view's rendering, not the API.
- State/URL: URL stays `/workflows/{id}` throughout; the same session's `/workflows/{id}/edit`
  navigation (no reload of underlying data, same auth/session) shows the resolved names,
  isolating the defect to this one component.

## BUG-20260828-005500-workflows-id-edit — Simple view's per-agent "Configure →" panel has no Tools section at all, hiding an existing tool-grant override (e.g. Write files disabled) with no visibility or edit path

- **Page:** Saved workflow — edit composer
- **Route:** /workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/edit (composer PATCH mode, applies to any saved workflow)
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-28 — `frontend/src/components/workflow/composer/AgentRow.toolsVisibility.test.tsx`
  2/2 green (no xfail marker present in this vitest file, nothing to remove). Neighbours re-run
  one file at a time, all green: `AgentRow.test.tsx` 5/5, `AdvancedExpander.test.tsx` 11/11,
  `CanvasConfigRail.test.tsx` 31/31 (47/47 total across the three files). `tsc --noEmit`: same 6
  pre-existing errors as the fixer reported, all in `HomeLaunchGrid.crossAccountLeak.test.tsx`
  and `store/listenerMiddleware.test.ts` — untouched by this change. `lint-imports` (run from
  `backend/`) shows one broken contract (`kernel imports only capability ports`) — pre-existing
  backend architecture drift unrelated to this frontend-only fix, not caused by it. `:3000` and
  `:8000/docs` both 200. Manual repro by hand in Chrome (lane4): toggled "Write files" off for
  Documentation Agent in Canvas view's Tools tab, switched to Simple view — Documentation Agent's
  Overrides row now shows a fifth "Tools" pill, visually lit (`bg-ink-900`/filled) vs Spec Writer
  Agent's unlit "Tools" pill (unrestricted). Opened "Configure →" for Documentation Agent: the
  panel now renders "Read files" (checked), "Write files" (unchecked, matching the Canvas
  override), "Execute commands" (disabled) inline, outside the collapsed Advanced disclosure. No
  new console errors (0 errors, 0 warnings). Screenshot:
  `bug-hunter/evidence/workflows-id-edit/BUG-20260828-005500-workflows-id-edit/05-after-fix-simple-configure-panel-tools-section.png`.
- **Fix card:** [FIX-350](../.knowledge/cards/20260828-2340-FIX-350.md) — shared
  `TOOL_GRANT_LEVERS`/`effectiveToolGrants`/`hasToolOverride` in
  `frontend/src/components/workflow/AgentsPopup.tsx`; `AdvancedExpander` now renders a
  "Tool grants" block through the same `applyLeverPatch` write-through the Canvas rail
  uses, `AgentRow` gained the fifth `Tools` Overrides chip, and `CanvasConfigRail` reads
  the shared lever list instead of its own copy
- **Fixed:** 2026-08-28 — `frontend/src/components/workflow/composer/AgentRow.toolsVisibility.test.tsx`
  2 failed BEFORE the change, 2 passed after (no `it.fails` marker in this vitest file, so a
  working fix shows as plain green). Neighbours re-run one file at a time, all green:
  AgentRow.test.tsx 5/5, AdvancedExpander.test.tsx 11/11, AgentsPopup.reskin.test.tsx 14/14,
  CanvasConfigRail.test.tsx 31/31, ComposerPage.test.tsx 14/14. `tsc --noEmit` reports 6
  errors, all in files this change does not touch (HomeLaunchGrid.crossAccountLeak.test.tsx,
  store/listenerMiddleware.test.ts). `:3000/workflows/{id}/edit` and `:8000/docs` both 200.
- **Found at:** 2026-08-28 00:55 UTC
- **Found by:** bug-workflows-id-edit-r1
- **Fingerprint:** `/workflows/{id}/edit|simple-view-agent-configure-panel|toggle-tool-grant-in-canvas-then-inspect-simple-view|no-tools-section-or-indicator-exists-in-simple-view`
- **Evidence:** `bug-hunter/evidence/workflows-id-edit/BUG-20260828-005500-workflows-id-edit/`

### Summary
The composer's Canvas view exposes a full "Tools" tab in the per-agent config rail
(`Overview`/`Skills`/`Hooks`/`Tools`/`Config`) with three real, togglable switches — "Read
files", "Write files", "Execute commands" — that persist correctly in-session (verified: toggling
"Write files" off for one agent, switching to the other agent's Tools tab, and switching back
shows no leak and no reversion). The same composer's Simple view offers an equivalent per-agent
"Overrides" row with a "Configure →" button that opens an inline "Advanced — <Agent Name>" panel.
That panel's own subtitle explicitly enumerates its scope as "Validator · Gate · Model · Retry"
plus a Skills library below it — there is no Tools sub-section anywhere in it. Searching the
panel's full rendered text for "Tool grants" or "Read files" returns no match, for either agent,
on both a fresh page load and after toggling a tool grant in Canvas view first. This means: (1)
Simple view provides no way to view or edit an agent's tool-grant restrictions at all — a user
working only in Simple view cannot discover or set them; (2) after a tool-grant override is set
in Canvas view (e.g. disabling an agent's ability to write files, a meaningful capability
restriction that changes what artifacts that step can produce for later steps), Simple view's
"Overrides" pill row is identical for both agents (`Validator Gate Retry Skills Configure →`) with
no "Tools" pill or any other indicator that one agent now has a restricted tool set — the two
views disagree about what state exists for the same agent on the same in-session workflow.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/edit`
   (fresh load, Canvas view, "My prototype" — 2 agents: Documentation Agent, Spec Writer Agent).
2. Click the "Documentation Agent" node, open its "Tools" tab in the rail. Observe three switches:
   Read files (on), Write files (on), Execute commands (disabled/off). Toggle "Write files" off.
   Confirm via `[role=switch]` DOM reads: `Write files` now `aria-checked="false"`.
3. Click the "Spec Writer Agent" node — confirm its own Tools tab independently still shows
   "Write files" `true` (no state leak between nodes). Click back to "Documentation Agent" —
   confirm "Write files" is still `false` there (no reversion).
4. Switch to "Simple" view. Observe both agent cards' "Overrides" row reads identically
   `Validator | Gate | Retry | Skills | Configure →` — no visual difference between the
   now-restricted Documentation Agent and the unrestricted Spec Writer Agent, and no "Tools" pill
   exists at all.
5. Click "Configure →" on the Documentation Agent card. Observe the inline "Advanced —
   Documentation Agent" panel opens with subtitle "Validator · Gate · Model · Retry" followed by a
   Skills library browser — confirmed via `document.body.innerText` search: no occurrence of "Tool
   grants" or "Read files" anywhere in the panel.
6. Reloaded fresh (`/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/edit`, no prior edit this time),
   switched straight to Simple view, and opened "Configure →" for the Spec Writer Agent — identical
   result: no Tools section, confirming this is a structural gap in the Simple-view panel, not
   contingent on the specific override made in step 2.

### Expected
Either the Simple view's per-agent "Configure →" panel should expose the same Tools grants
(Read/Write files, Execute commands) that Canvas view's rail does — consistent with "Overrides"
already listing Validator/Gate/Retry/Skills as editable categories — or, at minimum, the Simple
view's Overrides row should visibly flag when an agent has a non-default tool-grant restriction
set elsewhere in the same composer session, so the two views never silently disagree about what
capabilities an agent actually has.

### Actual
Simple view has no Tools section anywhere in its per-agent configuration UI. A tool-grant
override made in Canvas view is real (persists correctly, is not lost) but is completely invisible
and unreachable from Simple view — no pill, no tab, no indicator of any kind — even though Simple
view is otherwise a full editing surface for the same in-session workflow.

### Evidence
- Canvas view, Tools tab, "Write files" toggled off for Documentation Agent: `bug-hunter/evidence/workflows-id-edit/BUG-20260828-005500-workflows-id-edit/01-canvas-tools-tab-write-files-off.png`
- Simple view, both agents' Overrides row identical, no Tools pill: `bug-hunter/evidence/workflows-id-edit/BUG-20260828-005500-workflows-id-edit/02-simple-view-overrides-row-no-tools-pill.png`
- Simple view, "Configure →" panel for Documentation Agent — no Tools section present: `bug-hunter/evidence/workflows-id-edit/BUG-20260828-005500-workflows-id-edit/03-simple-configure-panel-no-tools-section-doc-agent.png`
- Simple view, "Configure →" panel for Spec Writer Agent (fresh reload, second repro) — same gap: `bug-hunter/evidence/workflows-id-edit/BUG-20260828-005500-workflows-id-edit/04-simple-configure-panel-no-tools-section-specwriter.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no request involved; both the Canvas Tools toggle and the Simple "Configure →" panel
  are purely client-side in-session composer state, confirmed via `document.body.innerText`
  substring search for "Tool grants"/"Read files" returning no match in the Simple panel on two
  independent fresh-page-load reproductions.
- State/URL: URL stays `/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/edit` throughout; no
  changes were ever saved (Save workflow was never clicked), and the underlying
  `GET /api/user-workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` was confirmed unchanged
  (`updated_at` unchanged) after this investigation.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduces unconditionally on every cold load, no
  axis variation needed (root cause: `AgentRow.tsx` uses `AdvancedExpander`, not
  `CanvasConfigRail`, so Simple view never renders a Tools section at all).
- **Root cause:** `AgentRow.tsx:252-258` (Simple view's "Configure →" panel) opens
  `AdvancedExpander` (`AgentsPopup.tsx:1774-2184`), whose subtitle is hardcoded `Validator ·
  Gate · Model · Retry` (`AgentsPopup.tsx:1883`) and whose JSX never reads or writes
  `StepSelection.tools`. `StepSelection.tools?: AgentToolGrants` (`AgentsPopup.tsx:1372-1376`)
  is a normal field of the SAME `SelectionsMap` Canvas view's `CanvasConfigRail.tsx:550-613`
  writes through via the shared `applyLeverPatch` reducer — confirmed both views are wired to
  ONE shared `selections` state in `ComposerPage.tsx` (Canvas: `ComposerPage.tsx:1113-1115`;
  Simple/`AgentRow`: `ComposerPage.tsx:1304-1310`). So a Canvas-set restriction is real,
  shared, in-session state; `AdvancedExpander` simply never renders it. CONFIRMED via direct
  source read of all cited files.
- **Blast radius:** `AdvancedExpander` itself is mounted at exactly one JSX call site
  (`AgentRow.tsx:252`), so there is no second literal caller of the broken component — but
  grepping every OTHER renderer of the shared `StepSelection`/`applyLeverPatch` shape found two
  more surfaces with the identical drift: `ConfigLeversFlat` (`AgentsPopup.tsx:1620-1772`,
  backing `AgentCapabilitiesModal`'s Config tab, mounted from `LibraryPage.tsx:1001` and
  `AgentLibrary.tsx:335`) also renders only Model/Validator/Gate/Retry; and Canvas view's own
  node card (`CanvasNode.tsx:763-802`) computes only `validatorOn`/`gateOn`/`retryOn` for its
  at-a-glance chip row, so even a Canvas-only user gets no visible flag on the node itself —
  only the rail's dedicated Tools tab shows it. Both filed INFERRED (unreproduced in-browser).
- **Fix:** belongs in the shared lever-rendering path, not per-caller — either add a Tools
  section to `AdvancedExpander` (mirroring `CanvasConfigRail.tsx`'s Read files/Write files rows
  and reusing the same `patch({ tools: {...} })` write-through so Simple and Canvas can't drift
  again) or extract Tools into one shared sub-component both `AdvancedExpander` and
  `CanvasConfigRail` render, the same way `AgentSkillsPicker` is already shared between them
  (`AgentRow.tsx:259-262`) specifically to prevent this class of drift.
- **Issue cards:** [ISS-274](../.knowledge/cards/20260828-1854-ISS-274.md) (root — confirmed),
  [ISS-378](../.knowledge/cards/20260828-2006-ISS-378.md) (sibling, INFERRED: `ConfigLeversFlat`/
  `AgentCapabilitiesModal`, Library + Add-agent drawer, same missing Tools row),
  [ISS-382](../.knowledge/cards/20260828-2008-ISS-382.md) (sibling, INFERRED: Canvas node card's
  own override-chip row has no Tools indicator either)

## BUG-20260828-005700-workflows-ppt-canvas — "Save as copy" of the PPT built-in silently drops the manifest, converting the copy from a PPTX-generating workflow into a generic streamed-text/markdown workflow

- **Page:** Built-in workflow on the canvas
- **Route:** /workflows/ppt/canvas (and the resulting saved copy at /workflows/{id}/edit)
- **Severity:** High
- **Status:** ESCALATED
- **Fix card:** [FIX-325](../.knowledge/cards/20260828-1645-FIX-325.md) — new
  `needsFullManifestOnSave` gate + `seededRunConfig` resync effect in
  `frontend/src/components/workflow/composer/ComposerPage.tsx`; frontend mechanism confirmed
  working for the generic strategies (ISS-203/204), but the headline repro (ISS-196/206, the
  `ppt` built-in itself) still fails end-to-end against the real backend — see **Verified** below
- **Verified:** 2026-08-28, verification FAILED. Ran
  `frontend/src/components/workflow/composer/ComposerPage.manifestPersistence.test.tsx` —
  all 5 XPASS confirmed (mocked `saveUserWorkflow`, no real backend call), then reverted the
  `it.fails` markers since this is a reopen, not a close. `ComposerPage.test.tsx` (14/14) still
  green, `tsc --noEmit` shows only the 3 pre-existing unrelated errors the fixer already
  documented, `:8000/docs` and `:3000/` both 200. Manual repro (signed in as qa-admin, fresh
  session — the prior stale session was `qa-basic` and produced an unrelated 403) at
  `/workflows/ppt/canvas`: the Workflow tab now correctly shows "ppt — declared by this
  workflow" / `presentation.pptx` (mechanism-2 fix confirmed), and the `POST
  /api/user-workflows` body now DOES include the full manifest with `deliverable.strategy:
  "ppt"` (mechanism-1 fix confirmed) — but the backend's CAP-03 trust guard
  (`backend/app/api/user_workflows.py`) rejects it outright: `422 Unprocessable Entity`,
  `"capability ('deliverable', 'ppt') is not user-allowed in workflow
  'user-workflow-validate' — a user/db manifest may not reference it (CAP-03)"`. No copy is
  created at all. Reproduced twice, identically, both cleaned up (nothing persisted to clean —
  the save itself fails). Contrast: the same flow against `ppt_v2` (deliverable strategy
  `single_file`, one of the three generic user-allowed strategies) succeeds — `201 Created`,
  manifest persisted with `deliverable.strategy: "single_file"` — confirming ISS-203/204's
  mechanism is genuinely fixed for every built-in whose declared strategy is one of the three
  generic ones. The `ppt` (and, by the same trust registry, `ppt_v2`'s sibling `ppt` strategy
  wherever else it appears) built-in is the one case where CAP-03 makes the bug's own stated
  Expected outcome ("a copy of a PPTX-producing workflow still produces a PPTX") structurally
  unreachable via this fix alone: the frontend now honestly attempts to carry the privileged
  strategy forward, and the backend's pre-existing trust boundary correctly refuses to persist a
  user manifest declaring it. This was never exercised by FIX-325's test coverage — the vitest
  file mocks `saveUserWorkflow`, so CAP-03 never runs. Evidence: `04-after-fix-builtin-canvas-
  shows-ppt-deliverable.png`, `05-after-fix-save-as-copy-422-cap03-blocked.png` in
  `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-005700-workflows-ppt-canvas/`.
- **Found at:** 2026-08-28 00:57 UTC
- **Found by:** bug-workflows-ppt-canvas-r1
- **Fingerprint:** `/workflows/ppt/canvas|save-as-copy|click-save-as-copy-on-ppt-builtin|copy-loses-manifest-and-deliverable-strategy-becomes-generic`
- **Evidence:** `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-005700-workflows-ppt-canvas/`
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced identically on every cold-start attempt (fresh `/dashboard` -> `/workflows/ppt/canvas` load), no axis narrowing required
- **Root cause:** Two coupled `ComposerPage.tsx` defects. (1) `needsFullManifest(pipelineAgents)`
  (`ComposerPage.tsx:51-60`) — the sole gate deciding whether `handleSave` includes `{manifest:
  buildWorkflowManifest(...)}` in its POST (`ComposerPage.tsx:628-632`) — only inspects per-node
  custom flags (`isCustom`/`prompt`/`skills`/`children`/`route`) and never consults `runConfig`;
  an unmodified built-in's stock agents always fail every check, so `manifest` is omitted from
  the POST entirely (not sent as null — simply absent), and the backend column persists `NULL`.
  (2) `runConfig` is seeded once via a plain `useState(initialRunConfig ?? {hardcoded default})`
  (`ComposerPage.tsx:335-341`) with no resync effect — unlike its sibling states `pipelineAgents`/
  `selections`, which each have one (`ComposerPage.tsx:250-269`, `:305-329`) specifically for this
  documented "same race, different state." The built-in's real deliverable arrives asynchronously
  (`page.tsx:437-485`) and is correctly threaded down to `initialRunConfig`
  (`DashboardLayout.tsx:2943`), but `DashboardLayout`'s remount-by-`key` trick
  (`key={savedComposition?.id ?? "new"}`, `DashboardLayout.tsx:2906`) never fires for a built-in
  because `page.tsx:448-451` deliberately omits `id` from a built-in's seed — so `ComposerPage`
  never remounts and the hardcoded default sticks. Both must be fixed for the canvas to correctly
  display AND persist the built-in's real manifest; fixing either alone leaves the bug partially
  alive. Full trace: [ISS-206](../.knowledge/cards/20260828-1609-ISS-206.md).
- **Blast radius:** `handleSave` (the reported path) and `handleRunOnce` (shares the same
  `needsFullManifest` gate, `ComposerPage.tsx:798`) — every built-in reachable via
  `/workflows/{type}/canvas` whose declared `deliverable` differs from the composer's
  `streamed_text`/`output.md` default (confirmed via `backend/agents/workflows/*/workflow.yaml`:
  `ppt_v2`, `prototype`, `app_builder`, `dotnet_to_azure`, `mulesoft_to_springboot`, `user_stories`
  — [ISS-203](../.knowledge/cards/20260828-1610-ISS-203.md)); any from-scratch Composer save or
  re-save of an all-stock-agent workflow that only touches the Workflow tab, no built-in involved
  at all ([ISS-204](../.knowledge/cards/20260828-1611-ISS-204.md)); and "Run once" on a built-in
  canvas, whose `unmodifiedBuiltin` bypass (`ComposerPage.tsx:837-857`) is lost the instant ANY
  edit changes the agent-id list, even one unrelated to the deliverable
  ([ISS-205](../.knowledge/cards/20260828-1612-ISS-205.md)).
- **Fix belongs in:** `ComposerPage.tsx`, the one component every path above already shares — (1)
  broaden the persist-full-manifest decision at `ComposerPage.tsx:628` and `:798` so it also fires
  whenever `builtinCanvasType`/`initialManifestSteps` is set or `runConfig` differs from the
  from-scratch default, not just when `needsFullManifest(pipelineAgents)` is true; (2) add a
  `useEffect` resyncing `runConfig` from a later-arriving `initialRunConfig`, mirroring the
  existing `seededFromManifest` pattern (`ComposerPage.tsx:305-314`). `buildWorkflowManifest`
  already serializes everything correctly once invoked (`userWorkflows.ts:397-399`) — the gap is
  purely the decision to call it.
- **5-fixer (2026-08-28, pass 2): ESCALATED, no further code changed.** Every mechanism the five
  cards name is fixed and stays fixed — FIX-325's edit to `ComposerPage.tsx` is left in the
  working tree untouched, and re-running
  `frontend/src/components/workflow/composer/ComposerPage.manifestPersistence.test.tsx` gives
  `5 failed (5)`, each "Error: Expect test to fail" — all five XPASS, `it.fails` markers left in
  place for the verifier. What blocks the headline repro is not a defect and cannot be patched:
  `deliverable/ppt` is registered WITHOUT `user_allowed`
  (`backend/agents/capabilities/deliverables/ppt.py:47-51`; `is_user_allowed` defaults False), so
  `_validated_manifest` → `_compile_check_manifest` (`backend/app/api/user_workflows.py:137`,
  `:115`) compiles at `trust="db"` — untrusted (`compiler.py:204`) — and `_check_trust`
  (`compiler.py:418-441`) refuses it. Reproduced one layer below the browser, no UI needed:
  `_validated_manifest({"steps":[…3 ppt steps…], "deliverable":{"strategy":"ppt","name":"presentation.pptx"}})`
  → `HTTP 422 … capability ('deliverable', 'ppt') is not user-allowed … (CAP-03)`, while the same
  call with `single_file`/`presentation.html` returns ACCEPTED — the verifier's ppt vs ppt_v2
  contrast, measured deterministically. Decisively, [ADR-0027](../.knowledge/cards/20260825-2115-ADR-0027.md)
  (status `active`) already ruled on this exact question and rejected the obvious fix: "The
  alternatives were to make those capabilities user-grantable — widening the trust surface for
  every user manifest, not just overrides — or to special-case ppt", with the locked constraint
  "an override supplies `steps` and nothing else; deliverable … always come from the file
  manifest." This entry's Expected ("a copy of a PPTX-producing workflow still produces a PPTX")
  contradicts that constraint, so satisfying it means amending an ADR, not editing code. Three
  options with their tradeoffs, and the evidence above:
  [ISS-223](../.knowledge/cards/20260828-1735-ISS-223.md). Frontend-only change; no backend file
  touched, no restart needed.
- **Issue cards:** [ISS-196](../.knowledge/cards/20260828-1555-ISS-196.md) (validator's
  reproduction + first-pass hypothesis), [ISS-206](../.knowledge/cards/20260828-1609-ISS-206.md)
  (root — analyzer pass, corrects ISS-196's stated mechanism),
  [ISS-203](../.knowledge/cards/20260828-1610-ISS-203.md) (sibling: same loss on every other
  non-default-deliverable built-in — ppt_v2, prototype, app_builder, dotnet_to_azure,
  mulesoft_to_springboot, user_stories),
  [ISS-204](../.knowledge/cards/20260828-1611-ISS-204.md) (sibling: the same gate drops
  Workflow-tab changes on ANY composer save, not just built-in copies),
  [ISS-205](../.knowledge/cards/20260828-1612-ISS-205.md) (sibling: "Run once" loses its
  built-in bypass the moment any unrelated edit changes the agent list),
  [ISS-223](../.knowledge/cards/20260828-1735-ISS-223.md) (correction: the `ppt` deliverable is
  not `user_allowed`, so no user manifest may carry it — ADR-0027 already ruled; needs a human)

### Summary
The `ppt` built-in workflow's real manifest (`GET /api/workflows/ppt`) defines a specialized
deliverable — `{"strategy": "ppt", "name": "presentation.pptx"}` — plus explicit per-agent tool
grants for all three steps (`manifest_steps`, each with `read_files`/`write_files: true`). The
canvas's own "Workflow" settings tab never reflects this: its "Deliverable strategy" combobox has
only three generic options (Streamed text / Single file / Serialized sandbox), none of which is
the built-in's actual `"ppt"` strategy, so it silently falls back to displaying "Streamed text"
with an output filename of "output" and format ".md" — fully enabled, editable-looking controls
showing values that do not match the real built-in at all. This mismatched display is not just
cosmetic: clicking "Save as copy" (after providing a workflow name, required for the button to
act) fires `POST /api/user-workflows` with `base_pipeline_type: "custom"` and, critically,
`manifest: null` — the entire manifest (tool grants, deliverable strategy) is dropped, not
translated. Opening the resulting saved copy's own edit page confirms the loss end-to-end: its
Workflow tab shows the same generic "Streamed text" / "output" / ".md" deliverable, and
`document.body.innerText` contains no mention of "pptx" anywhere. A workflow whose entire purpose
is producing a `.pptx` deck, once copied via the page's only save affordance, becomes a workflow
that will stream raw text/markdown instead — a functional regression a user copying this
built-in would have no way to notice from the UI, since nothing on the canvas ever showed the
correct deliverable strategy to begin with. This is a materially different, more severe defect
than the already-known `ISS-183`/`composerAlwaysSaysCustom` quirk (which is only about the
`base_pipeline_type` label always being "custom"): here the loss is the entire per-agent tool
grant manifest and the deliverable strategy itself, verified via direct API diff, not merely a
type-label mismatch. The built-in itself was confirmed to remain fully pristine and immutable
throughout (`GET /api/workflows/ppt` unchanged, `deliverable.strategy` still `"ppt"`, after both
copy operations) — this bug is entirely in what the copy loses, not in any mutation of the
original.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/workflows/ppt/canvas` (fresh load).
2. Open the right-rail "Workflow" tab (default). Observe the "Deliverable" section: combobox
   reads "Streamed text — agent's raw output" (`value: "streamed_text"`), "Output file name"
   reads "output", "Output format" reads "Markdown (.md)" — all controls fully enabled
   (`disabled: false` on every one, confirmed via DOM read), none of which is the built-in's real
   `deliverable.strategy: "ppt"` / `presentation.pptx` (confirmed via `GET /api/workflows/ppt`
   in the same session).
3. Fill "Workflow name" with a throwaway name (e.g. "Bug Hunter PPT Copy Test") — required before
   "Save as copy" acts; without a name the button only focuses the name field.
4. Click "Save as copy". Observe the fired `POST /api/user-workflows` response body:
   `base_pipeline_type: "custom"`, `manifest: null`, `agent_ids` correctly lists the three PPT
   agents, but no manifest/deliverable data survives at all.
5. Navigate to the resulting copy's edit page, `/workflows/{new-id}/edit`. Observe the Workflow
   tab shows the identical generic "Streamed text" / "output" / ".md" deliverable, and
   `document.body.innerText` contains zero occurrences of "pptx" — the copy has no trace of ever
   having been a PPT deliverable workflow.
6. Repeated steps 1-5 a second time from a fresh `/workflows/ppt/canvas` load with a different
   throwaway name ("Bug Hunter PPT Copy Repro2") — identical result: `manifest: null`,
   `base_pipeline_type: "custom"`, generic deliverable on the copy's own edit page.
7. Confirmed the built-in itself was never mutated: `GET /api/workflows/ppt` immediately after
   both copy operations still returns `deliverable: {"strategy": "ppt", "name":
   "presentation.pptx"}` unchanged.
8. Cleaned up: deleted both throwaway copies via `DELETE /api/user-workflows/{id}` (204 confirmed
   for both).

### Expected
The canvas's Workflow tab should display the built-in's actual deliverable strategy (or, if the
UI's generic dropdown genuinely cannot represent a specialized strategy like `"ppt"`, it should
say so rather than silently defaulting to a plausible-looking wrong value). At minimum, "Save as
copy" should carry forward the full manifest — tool grants and deliverable strategy included —
from the built-in it forks from, so a copy of a PPTX-producing workflow still produces a PPTX.

### Actual
The canvas never shows the built-in's real deliverable strategy, and "Save as copy" persists
`manifest: null`, discarding the built-in's per-agent tool grants and its `"ppt"` deliverable
strategy entirely. The saved copy is left as a generic "Streamed text" workflow with no way,
short of manually reconfiguring the Deliverable section post-save, to recover PPTX generation.

### Evidence
- Built-in canvas, Workflow tab showing the wrong "Streamed text" deliverable before any save: `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-005700-workflows-ppt-canvas/01-builtin-canvas-deliverable-shows-streamed-text.png`
- Saved copy's own edit page — deliverable still "Streamed text", no "pptx" anywhere: `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-005700-workflows-ppt-canvas/02-saved-copy-edit-page-deliverable-still-streamed-text-no-pptx.png`
- Reproduced a second time, independent copy, same loss: `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-005700-workflows-ppt-canvas/03-repro2-second-copy-same-loss.png`
- API request/response excerpts (original manifest vs. both copies' `manifest: null`, and the
  built-in's post-copy pristine state): `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-005700-workflows-ppt-canvas/network.log`

### Browser Signals
- Console: no relevant error observed.
- Network: `POST /api/user-workflows` returns `201 Created` with `manifest: null` and
  `base_pipeline_type: "custom"` on both reproduction attempts; `GET /api/workflows/ppt`
  confirmed unchanged (`deliverable.strategy: "ppt"`) before and after both copy operations.
- State/URL: URL stays `/workflows/ppt/canvas` throughout the copy action (no navigation); the
  resulting copy is reachable at its own `/workflows/{id}/edit` URL and independently confirms
  the same lossy deliverable state via its own page load, not just the raw API response.

## BUG-20260828-010600-workflows-id-run — Loading a saved-workflow launch panel with a nonexistent or malformed workflow id silently renders the Dashboard under the unchanged bogus URL

- **Page:** Saved workflow's launch panel
- **Route:** /workflows/<nonexistent-uuid>/run, /workflows/<malformed-id>/run
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 01:06 UTC
- **Found by:** bug-workflows-id-run-r1
- **Fingerprint:** `/workflows/<id>/run|workflow-run-panel-cold-mount|navigate-with-nonexistent-or-malformed-workflow-id|api-404-caught-then-dashboard-silently-rendered-under-stale-url`
- **Evidence:** `bug-hunter/evidence/workflows-id-run/BUG-20260828-010600-workflows-id-run/`
- **Validated:** 3/3 from cold start on 2026-08-28 — reproduced for a nonexistent UUID, a
  malformed id, and a second distinct nonexistent UUID; console/DOM confirmed every cycle
- **Root cause:** `frontend/src/app/[...view]/page.tsx`'s workflow-run cold-mount catch
  (`:3692-3707`) sets `workflowRunFailed` on any 404/non-401 fetch error, but the render gate
  (`:3785-3791`) only reads that flag to stop the loading-`null` return — it never calls
  `notFound()`, unlike this exact file's 3 sibling identity-fetch-failure gates
  (`runAccessDenied` -> `:3734-3736`, `workflowEditAccessDenied` -> `:3741-3743`,
  `workflowDetailFailed` -> `:3751-3753`). Execution falls through to the unconditional
  `return <DashboardLayout .../>` with no `notFound()`/`router.push`/`router.replace` ever
  called, so `location.href` never moves off the bogus `/workflows/<id>/run` URL. (Corrects
  the original validator attribution to `LaunchWizard.tsx` — that component is never even
  rendered on this failure path; see ISS-273's appended analyzer section.)
- **Blast radius:** contained to this one file/effect — `userWorkflowsApi.get()` (the call
  that 404s) has exactly 3 call sites in the whole frontend, all inside
  `frontend/src/app/[...view]/page.tsx`; the other 2 (`/workflows/{id}/edit`,
  `/workflows/{id}` read view) are already correctly gated into `notFound()`. No other
  component fetches a saved workflow by id — the click-through launch path
  (`DashboardLayout.handleLaunchSaved`) already has the object in hand and never hits this
  fetch. Fix belongs entirely in this one cold-mount effect + render gate; there is no other
  caller to route through.
- **Fix card:** [FIX-355](../.knowledge/cards/20260828-2358-FIX-355.md) — workflowRunFailed
  now fires `notFound()` (page.tsx render gate), resets before each cold-mount fetch, and is
  set only on 403/404; resolves ISS-273 + siblings ISS-379/ISS-380 in one change
- **Issue cards:** [ISS-273](../.knowledge/cards/20260828-1653-ISS-273.md) (root — CONFIRMED,
  file attribution corrected from `LaunchWizard.tsx` to `page.tsx`),
  [ISS-379](../.knowledge/cards/20260828-2209-ISS-379.md) (sibling, INFERRED:
  `workflowRunFailed` never resets, so a stale `true` from a failed visit defeats the
  loading-gate on a later, valid `/workflows/{id2}/run` in the same SPA session),
  [ISS-380](../.knowledge/cards/20260828-2209-ISS-380.md) (sibling, INFERRED: the catch is
  unnarrowed to 403/404 like its 2 siblings, so a transient 5xx/network error on a VALID id
  gets today's identical wrong fallback, and would regress to a permanent not-found if the
  fix ships without narrowing it too)
- **Verified:** 2026-08-29 — ran
  `tests/integration/e2e/suites/05_saved_workflows/test_iss273_run_panel_bogus_id_dead_end.py`
  (`.venv/bin/python3 -m pytest ...`): both cases XPASS(strict) before the marker removal,
  plain green (2 passed) after removing `xfail`. Re-ran the original repro by hand in Chrome
  (lane4, qa-admin, cold nav) for both the nonexistent UUID and the malformed id: `h1` now
  reads "Not found" instead of "What would you like to build today?" for both, URL stays on
  the requested bogus `/run` path as expected for a Next.js `notFound()` render (no
  URL/content mismatch — content now correctly reflects the failure). Re-checked the valid
  saved workflow's own `/run` panel (`656ca387-...`) still loads "Configure your prototype"
  correctly — no regression. `npx tsc --noEmit`: only pre-existing unrelated errors in
  `HomeLaunchGrid.crossAccountLeak.test.tsx` / `listenerMiddleware.test.ts`, none in
  `page.tsx`. Backend `:8000/docs` 200. `lint-imports` (from `backend/`): 1 pre-existing
  broken contract (`agents.execution_engine.engine` -> `app.api`), unrelated to this
  frontend-only change. Regression file
  `suites/05_saved_workflows/test_saved_workflows.py`: 10/13 passed, 3 failed on the
  documented pre-existing D-05/D-10 agent-count defect (roster says 4, panel says 3 —
  unrelated to ISS-273's notFound() gate). Evidence:
  `bug-hunter/evidence/workflows-id-run/BUG-20260828-010600-workflows-id-run/04-after-fix-nonexistent-id-not-found.png`,
  `05-after-fix-malformed-id-not-found.png`.

### Summary
Navigating directly to a saved workflow's dedicated launch route (`/workflows/{id}/run`) with an
id that does not resolve to any saved workflow — either a well-formed but nonexistent UUID
(`00000000-0000-0000-0000-000000000000`) or a syntactically invalid id (`not-a-valid-uuid`) —
triggers a `GET /api/user-workflows/<id>` request that correctly 404s (`ApiError: Saved workflow
not found`, logged to console as `cold-mount workflow-run fetch failed`). Instead of showing a
not-found state, an error message, or performing an actual navigation to `/dashboard` or
`/workflows`, the page's error-handling path silently renders the full authenticated Dashboard
catalog content (`h1: "What would you like to build today?"`, workflow cards, "Jump back in") in
place while `location.href` remains the original, unresolvable `/workflows/<id>/run` URL. The
address bar and the rendered content permanently disagree — confirmed via direct `location.href`
reads immediately after the swap and again after a subsequent full page load of a different URL
and back. This reproduces identically for both a valid-shaped-but-nonexistent UUID and a
completely malformed id string, meaning the run panel's cold-mount fetch-failure handler falls
back to dashboard content unconditionally rather than surfacing the actual 404. This is a
different mechanism from the ledger's `BUG-20260827-231407-register` (which is Next.js route
resolution silently falling through to dashboard content for an *unmatched sub-path* under
`/register`, with no API call involved at all): here the route itself matches correctly, an actual
API request fires and genuinely 404s, and it is this page's own client-side error/not-found
handling that discards the failure and renders the wrong content without ever updating the URL.
It is also unrelated to D-05/D-10 (agent-count/estimate disagreements) and D-28 (the saved-workflow
detail view being unreachable) since a *valid* saved workflow's `/run` route (confirmed in the same
session against `656ca387-e69c-474d-b7ff-5fd9eb017cc0`, "My prototype") loads and binds correctly —
this defect is specific to the 404/not-found path for an id that does not resolve.

### Reproduction
1. Sign in as qa-admin. Confirm a real saved workflow's launch panel loads correctly:
   navigate to `http://localhost:3000/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/run` — the
   prototype wizard shell renders normally (h1 "Configure your prototype", Advanced button, etc.).
2. Navigate to `http://localhost:3000/workflows/00000000-0000-0000-0000-000000000000/run` (a
   well-formed UUID that matches no saved workflow).
3. Observe the console logs `Failed to load resource: ... 404 ... /api/user-workflows/00000000-...`
   and `cold-mount workflow-run fetch failed: ... ApiError: Saved workflow not found`.
4. Observe the rendered page: `document.querySelector('h1').textContent` reads "What would you
   like to build today?" and the body shows the full Dashboard catalog (workflow cards, "Jump
   back in"), while `location.href` still reads
   `http://localhost:3000/workflows/00000000-0000-0000-0000-000000000000/run` — confirmed via
   direct `location.href` read, not a stale screenshot.
5. Repeat with a syntactically malformed id: navigate to
   `http://localhost:3000/workflows/not-a-valid-uuid/run` — identical result: the same 404 +
   `cold-mount workflow-run fetch failed` console pair, Dashboard content rendered, URL stays on
   the bogus `/workflows/not-a-valid-uuid/run` path.
6. Repeated step 2 a second time from a fresh navigation — deterministic, same mismatch both
   times.

### Expected
An id that does not resolve to a real saved workflow should produce an explicit not-found state
(e.g. "This workflow no longer exists" plus a link back to `/workflows`) or an actual navigation
to a real destination, with the URL and the rendered content agreeing either way — consistent with
how a valid id's launch panel correctly renders its own content at its own URL.

### Actual
The page's own client-side handling of the `/api/user-workflows/<id>` 404 discards the error and
renders the Dashboard catalog's content in place, while `location.href` remains the original,
non-existent `/workflows/<id>/run` URL indefinitely — a persistent URL/content mismatch specific
to this route's not-found path.

### Evidence
- Before (valid saved workflow's own `/run` panel, for contrast): `bug-hunter/evidence/workflows-id-run/BUG-20260828-010600-workflows-id-run/01-before-valid-workflow-run-panel.png`
- Failure (nonexistent UUID, Dashboard renders under the bogus URL): `bug-hunter/evidence/workflows-id-run/BUG-20260828-010600-workflows-id-run/02-failure-nonexistent-id-dashboard-mismatch.png`
- Reproduced (malformed id, same mismatch): `bug-hunter/evidence/workflows-id-run/BUG-20260828-010600-workflows-id-run/03-repro2-malformed-id-dashboard-mismatch.png`
- Console excerpt: `bug-hunter/evidence/workflows-id-run/BUG-20260828-010600-workflows-id-run/console.log`

### Browser Signals
- Console: `GET /api/user-workflows/<id>` returns 404 in both cases; app logs
  `cold-mount workflow-run fetch failed: <id> ApiError: Saved workflow not found` for each,
  confirming the failure is caught but mishandled rather than silent/uncaught.
- Network: `GET http://localhost:8000/api/user-workflows/00000000-0000-0000-0000-000000000000` and
  `GET http://localhost:8000/api/user-workflows/not-a-valid-uuid` both return `404`.
- State/URL: `location.href` remains the requested, unresolvable `/workflows/<id>/run` path
  throughout in both cases; the rendered DOM (`h1`, catalog cards) matches `/dashboard` exactly,
  confirmed via direct DOM reads rather than a screenshot alone.

## BUG-20260828-011000-workflow — "Run Workflow" enables with zero agents attached and silently no-ops on click

- **Page:** Legacy workflow builder (unlinked, second/older builder)
- **Route:** /workflow
- **Severity:** Low
- **Status:** ESCALATED
- **Found at:** 2026-08-28 01:10 UTC
- **Found by:** bug-workflow-r1
- **Fingerprint:** `/workflow|run-workflow-button|type-brief-with-zero-agents-attached|button-enables-but-click-fires-no-request-and-does-nothing`
- **Evidence:** `bug-hunter/evidence/workflow/BUG-20260828-011000-workflow/`
- **Validated:** 3/3 on 2026-08-28, every cold cycle — no axis variation needed. Root cause:
  `frontend/src/components/workflow/WorkflowView.tsx:473` gates the "Run Workflow" button on
  `!ideaInput.trim()` only, never `pipelineAgents.length`; `handleRun` (`:161-167`) guards
  `onStartPipeline` with a bare `if`, so on this orphaned route where nothing wires that prop the
  click is a total silent no-op.
- **Issue card:** [ISS-328](../.knowledge/cards/20260828-1834-ISS-328.md)
- **Root cause (CONFIRMED):** two independent gaps in the same file/route pairing, both read
  directly. (1) `frontend/src/components/workflow/WorkflowView.tsx:473` —
  `disabled={!ideaInput.trim()}` never checks `pipelineAgents.length`, even though the count
  renders right beside it (`:406`). (2) `frontend/src/components/workflow/WorkflowView.tsx:161-167`
  `handleRun` guards the dispatch with `if (onStartPipeline)`, and the component's *only* caller —
  `frontend/src/app/workflow/page.tsx:58-62` (confirmed via `grep -rn "WorkflowView" frontend/src`,
  one import site) — never passes `onStartPipeline` (nor `pipelineState`, `onResetPipeline`,
  `onViewResults`). So even a correct `pipelineAgents.length` guard would not make Run functional
  on this route — the click is structurally inert regardless of agent count, because nothing ever
  supplies the callback. `/workflow` is also a hand-written Next.js route outside
  `frontend/src/lib/routes.ts`'s `[...view]` catch-all, violating `ADR-0018`'s locked constraint
  ("a hand-written path literal outside routes.ts is a defect"); its likely-intended replacement,
  `IdeaInputPage.tsx`, already implements the correct `pipelineAgents.length === 0` guard
  (`:1334`, `:1721`) that `WorkflowView.tsx` lacks.
- **Blast radius (CONFIRMED, `grep -rn "WorkflowView" frontend/src`):** exactly one caller,
  `frontend/src/app/workflow/page.tsx`. `handleRun`'s only two trigger paths (Run button `:472`,
  `Cmd+Enter` keyboard shortcut `:320`) both hit the identical broken function — same fix, no
  separate caller to patch. No other component imports `WorkflowView`.
- **Proposed fix:** in `WorkflowView.tsx`, add `pipelineAgents.length === 0` to the button's
  `disabled` condition (matching `IdeaInputPage.tsx:1334`/`:1721`'s existing pattern) — this alone
  satisfies the reported symptom (button must stay disabled at 0 agents). That does NOT restore
  working functionality at 1+ agents, since `onStartPipeline` is still unwired; either wire real
  callbacks into `<WorkflowView>` at `app/workflow/page.tsx:58-62`, or retire the route (redirect
  `/workflow` the way `proxy.ts` already redirects other legacy workflow URLs per ADR-0018) since
  its replacement `IdeaInputPage.tsx` already does this correctly and is reachable via the
  catch-all. Fix belongs in `WorkflowView.tsx` (+ `app/workflow/page.tsx` if functionality is to
  be restored rather than retired) — there is only the one caller, so no fan-out risk either way.
- **Issue cards:** [ISS-328](../.knowledge/cards/20260828-1834-ISS-328.md) (root — validator's
  original root-cause card), [ISS-492](../.knowledge/cards/20260829-0150-ISS-492.md) (sibling,
  INFERRED: same unwired-prop gap also makes Steps 3-4 — running/complete UI, View Results, Run
  Another Pipeline — permanently unreachable on `/workflow`)

- **Fix cards:** [FIX-391](../.knowledge/cards/20260829-0305-FIX-391.md) — resolves
  [ISS-328](../.knowledge/cards/20260828-1834-ISS-328.md) only
- **Fixed:** `WorkflowView.tsx:161` (handleRun floor) and `:473` (button disabled gate) now both
  carry `|| pipelineAgents.length === 0`, mirroring `IdeaInputPage.tsx:1343`/`:1730`. The floor is
  in `handleRun` because the `Cmd+Enter` shortcut (`:320`) calls it directly and a `disabled`
  attribute never intercepts a keydown — guarding only the button would have left that path open.
  `WorkflowView.zeroAgents.test.tsx` now XPASSes (vitest: "Error: Expect test to fail"); the
  `it.fails` marker is left in place for the 6-verifier.
- **Escalation (why not FIXED):** [ISS-492](../.knowledge/cards/20260829-0150-ISS-492.md) is
  unresolved and needs a route-lifecycle decision the cards deliberately leave open. Option A —
  wire `onStartPipeline`/`pipelineState` into `app/workflow/page.tsx:58-62` (what
  `app/workflow/page.test.tsx` asserts) — stands up a SECOND independent run-launch and
  run-state seam on an unlinked route, which is the fragmentation
  [ADR-0018](../.knowledge/cards/20260824-1631-ADR-0018.md) explicitly refused; and without the
  SSE fan-out that `[...view]/page.tsx` owns it would strand the user on a permanently empty
  "running" graph. Option B — retire `/workflow` via the `proxy.ts` matcher, exactly as
  `/workflow/create` already is — is 2 lines, matches ADR-0018, and would also close row 84's
  siblings, but deleting a route is not a fixer's call. Needs a human pick.

### Summary
On a fresh load of `/workflow` (the orphaned legacy builder, D-17's `/workflow`, unlinked from
`routes.ts`), "Run Workflow" starts correctly `disabled` while "Workflow Agents (0)" and the
brief textarea are both empty. Typing any non-empty text into "Describe your idea" — with the
agent count still genuinely `0` (`Workflow Agents (0)`, matching D-17's finding that this page's
`Add Agent` picker returns "No agents found" for every category, so 0 agents is not just the
starting state but the only reachable state) — flips "Run Workflow" to enabled
(`button.disabled === false`, confirmed via direct DOM read, not just a visual read). Clicking
the now-enabled button does nothing observable: no navigation, no toast/alert text, no console
error, and critically no network request at all — `browser_network_requests` shows no new
request fired by the click (confirmed by diffing the request list immediately before and after,
and by confirming `GET /api/runs?limit=50` count does not grow, i.e. no run was created). The
gating logic only checks the brief text's presence, not the agent count it displays right next to
it, so a workflow with literally zero configured agents presents as launchable and then quietly
fails to launch with no feedback to the user at all.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/workflow` (fresh load). Confirm
   "Workflow Agents (0)" and "Run Workflow" has the `disabled` attribute.
2. Type any non-empty text into "Describe your idea" (e.g.
   `zz-hunt-test legacy builder idea text for probing run workflow button state`).
3. Observe "Run Workflow" is no longer disabled (`button.disabled === false` via direct DOM
   read), while "Workflow Agents" still reads `(0)` — no agent was ever added.
4. Click "Run Workflow". Observe: URL stays `/workflow`, no toast/alert appears, no console
   message is logged, and `browser_network_requests` shows no new request fired by the click
   (the only requests present are the page's own initial load calls).
5. Reload to a fresh `/workflow`, repeat steps 2-4 with different brief text
   (`zz-hunt-repro2 second reproduction of run workflow enabled with zero agents`) — identical
   result: button enables on brief-text-only, click is a silent no-op, no request fires either
   time.

### Expected
"Run Workflow" should stay disabled (or clicking it should show a clear validation message, e.g.
"Add at least one agent") while the workflow has zero configured agents, since a 0-agent workflow
cannot meaningfully run. At minimum, if the button is going to be clickable, clicking it should
do *something* observable (an error, a toast, a request) rather than nothing at all.

### Actual
The button's enabled/disabled state is gated only on the brief textarea having content, ignoring
the agent count shown immediately beside it. With 0 agents it still enables, and clicking it is a
complete no-op — no request, no error, no feedback of any kind.

### Evidence
- Before (fresh page, 0 agents, button disabled): `bug-hunter/evidence/workflow/BUG-20260828-011000-workflow/01-before-brief-typed-enabled.png`
- Repro 2 (fresh reload, brief typed, button enabled with 0 agents): `bug-hunter/evidence/workflow/BUG-20260828-011000-workflow/02-repro2-enabled-zero-agents.png`
- After click (no visible change, no request fired): `bug-hunter/evidence/workflow/BUG-20260828-011000-workflow/03-after-click-silent-noop.png`

### Browser Signals
- Console: no relevant error or message logged on click, in either reproduction.
- Network: no new request of any kind fires from the click; `GET /api/runs?limit=50` count
  confirmed unchanged (no run created) — verified via `browser_network_requests` diff before/after.
- State/URL: URL stays `/workflow` throughout; `button.disabled` verified `false` via direct DOM
  read before each click, not inferred from a screenshot.

## BUG-20260828-011500-runs — Run History silently caps at 50 runs and mislabels it as the full total, with no pagination path to the remaining 223

- **Page:** Run History
- **Route:** /runs
- **Severity:** High
- **Status:** ESCALATED
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced on every cold navigation to
  /runs, no axis variation needed. Root cause: `frontend/src/components/history/WorkflowHistory.tsx`
  renders `runs.length` instead of the `totalRuns` state it already captures from the
  API's `total` field, and `handleLoadMore` is defined but never wired to any
  button/scroll/observer.
- **Root cause (CONFIRMED, `WorkflowHistory.tsx:973` + `:952` + `:289-299`):** the mount
  effect (`:203-214`) correctly captures the API's true count into `totalRuns` state
  (`setTotalRuns(total)`, `:210`), and `handleLoadMore` (`:289-299`) is a fully correct
  `limit=50&offset=runs.length` pagination call — but the header (`:973 <p>{runs.length}
  runs</p>`) and every filter chip's count (`:952-958 typeCounts`) render off the capped
  `runs`/`families` array instead of `totalRuns`, and `handleLoadMore` is never invoked
  by any button/scroll/observer (`grep -n "handleLoadMore"` — one hit, its own
  definition). Backend (`backend/app/api/runs.py:315-371 list_runs`) already supports
  `limit`/`offset` and returns `X-Total-Count` — confirmed not a blocker. Historical:
  `git show ce08bf542` (2026-08-17 revert) deleted a working Load-More footer as
  collateral damage of an unrelated backend de-dup revert; the header/chip mislabel
  predates that revert and was never fixed (commit `35b17ad1a`).
- **Blast radius (CONFIRMED via `grep -rln "getWorkflows(" frontend/src`, 6 callers):**
  confined to `WorkflowHistory.tsx` — the other 5 callers (`app/[...view]/page.tsx`,
  `providers/RunConnectionProvider.tsx`, `components/results/AgentThinkingTab.tsx`,
  `store/slices/globalSlice.ts`, `lib/api.ts` itself) fetch small fixed-limit "recents"
  lists and never destructure/render `total`, so none replicate this defect. Within
  `WorkflowHistory.tsx`, three further consumers of the same capped array are affected:
  search (`matchesFilter`), sort (`bucketAndSortFamilies`), delete
  (`handleDeleteConfirm` never decrements `totalRuns`), and per-type filter-chip counts
  (`typeCounts`) — each filed as an INFERRED sibling below.
- **Fix location:** entirely inside `WorkflowHistory.tsx` (no shared function needed —
  confirmed no other component shares this code path). See ISS-198's "Fix location"
  section for the 5-item breakdown.
- **5-fixer (2026-08-28): ESCALATED, no code changed.** Every recorded root cause holds
  (`WorkflowHistory.tsx:973` header, `:952-958` chips, `:289-299` dead `handleLoadMore`,
  `:415` missing `setTotalRuns` on delete) — but the fix cannot be applied without a units
  decision no card covers, and the two acceptance tests contradict each other. Measured on
  the live backend as qa-admin: `X-Total-Count` = **275** runs, which `groupRunsByFamily`
  collapses into **232** family cards (43 runs are revision members); per bucket
  custom 195/176, ppt 31/25, prototype 26/18, user_stories 14/10, app_builder 9/3. Rows are
  family cards (`RevisionFamilyView.tsx:539`/`:593`; expanded members render as `Version N`,
  `:663`, and are not rows). The green scenario suite requires @S-06-04 "the 'All' filter's
  count equals the total run count" AND @S-06-05 "the visible row count equals the filter's
  own count"; ISS-198's new test requires the header to equal `X-Total-Count`. Run-counted
  chips satisfy S-06-04 and ISS-213 but draw 25 rows against a chip of 31 (S-06-05 fails for
  all five types); card-counted chips satisfy S-06-05 but put "All 232" under a "275 runs"
  header (S-06-04 fails). Second, independent contradiction:
  `test_scrolling_to_the_bottom_loads_more_runs` needs the list capped (`rows <= 50` at rest)
  while ISS-213 + S-06-05 need it uncapped (176 Custom rows) — and a render cap also hides
  ISS-208's true highest-token run, which sits in the Older bucket behind Today 2 + Earlier
  190 (`bucketAndSortFamilies` sorts within a date bucket, never across). Options and the
  measured evidence: [ISS-219](../.knowledge/cards/20260828-1706-ISS-219.md). Baseline
  observed, unchanged: `test_run_history_pagination.py` 5 xfailed;
  `test_run_history.py -k "type_filter_counts_sum_to_the_total or filtering_by_type_narrows"`
  6 passed.
- **Issue cards:** [ISS-198](../.knowledge/cards/20260828-1400-ISS-198.md) (root),
  [ISS-207](../.knowledge/cards/20260828-1617-ISS-207.md) (sibling: search
  false-negatives past row 50), [ISS-208](../.knowledge/cards/20260828-1617-ISS-208.md)
  (sibling: Longest/Tokens sort ignores rows past 50),
  [ISS-209](../.knowledge/cards/20260828-1617-ISS-209.md) (sibling: delete never
  decrements totalRuns, desyncs future Load-More offset),
  [ISS-213](../.knowledge/cards/20260828-1618-ISS-213.md) (sibling: per-type filter
  chips undercount and can vanish entirely),
  [ISS-219](../.knowledge/cards/20260828-1706-ISS-219.md) (correction: the
  header/chip units decision this fix is blocked on)
- **Found at:** 2026-08-28 01:15 UTC
- **Found by:** bug-runs-r1
- **Fingerprint:** `/runs|run-list-fetch|load-full-history|hard-capped-at-50-mislabeled-as-total`
- **Evidence:** `bug-hunter/evidence/runs/BUG-20260828-011500-runs/`

### Summary
The Run History page always requests `GET /api/runs?limit=50` and never issues a follow-up
request with a higher `limit` or an `offset`, regardless of scrolling, filtering, sorting, or
auto-refresh. For the qa-admin account the backend actually holds 273 runs (verified via
`GET /api/runs?limit=100&offset=0/100/200` → 100 + 100 + 73 = 273), but the UI header reads
"50 runs" and the "All" filter chip reads "All 50" — both presented as if they were the true
total, when they are actually just the size of the single page fetched. There is no "Load more"
control, no infinite-scroll trigger, and no page-size selector anywhere on the page: scrolling
the run list's inner scroll container (`.flex-1.overflow-y-auto`, scrollHeight 3964 vs
clientHeight 894) all the way to the bottom fires zero additional network requests. The result
is that roughly 223 of 273 runs (82%) are permanently unreachable from this page — a user has no
way to find, filter, sort, or open any run outside the most-recent 50, and the UI actively
misrepresents the size of their own history as complete. This is a data-completeness defect
distinct from D-14 (missing links/testids on the cards that ARE shown) and D-15 (an unrecognized
filter value showing an empty list) — both of those concern the shown 50 rows, not the fact that
only 50 of 273 rows are ever fetched.

### Reproduction
1. Sign in as qa-admin (account with 273 seeded runs) and open /runs.
2. Observe the header: "Run History" / "50 runs", and the "All" filter chip reads "All 50".
3. Scroll the run list to the very bottom (`document.querySelector('.flex-1.overflow-y-auto')`,
   set `scrollTop = scrollHeight`) — the last row rendered is still within the same batch of 50;
   no new network request fires (confirmed via `browser_network_requests`, filter `runs`: every
   request logged for the whole session is `GET /api/runs?limit=50`, none with `offset`).
4. In parallel, call the backend directly with the same bearer token:
   `GET /api/runs?limit=100&offset=0` → 100 rows, `...offset=100` → 100 rows,
   `...offset=200` → 73 rows. Sum = 273, not 50.
5. Compare: the UI's declared total (50) is 18% of the actual total (273); the remaining 223
   runs are not visible, not searchable, not filterable, and not sortable from this page.

### Expected
The Run History page should either paginate/lazy-load through the full run history (with the
header count reflecting the true total, e.g. via a `total` field or a following batch of
requests as the user scrolls) or, at minimum, accurately label the count as "showing the 50 most
recent of N runs" rather than presenting 50 as the complete total.

### Actual
The page fetches exactly one page of 50 runs, never requests more regardless of scrolling, and
labels that partial set as the full total ("50 runs" / "All 50"), permanently hiding 223 of 273
runs with no user-facing way to reach them.

### Evidence
- Screenshot: `bug-hunter/evidence/runs/BUG-20260828-011500-runs/01-run-history-shows-50-runs.png`
  (header "Run History" / "50 runs", "All" chip "All 50")
- Network log: `bug-hunter/evidence/runs/BUG-20260828-011500-runs/network.log`

### Browser Signals
- Console: none observed
- Network: every `/api/runs` request from the page carries `limit=50` and no `offset`; confirmed
  via `mcp__plugin_playwright_playwright__browser_network_requests` across load, filter clicks,
  sort clicks, and a full scroll-to-bottom of the list container
- State/URL: URL and DOM never change on scroll; `.flex-1.overflow-y-auto` scrollHeight (3964)
  well exceeds clientHeight (894), confirming the container is scrollable and was actually
  scrolled, yet nothing loads beyond row 50

### Test coverage (4-writer, 2026-08-28)

All tests live in `tests/integration/e2e/suites/06_run_history/test_run_history_pagination.py`
(offline tier, `@pytest.mark.issue(...)` + `xfail(strict=True)`), run one file at a time and
observed red before marking:
- [ISS-198](../.knowledge/cards/20260828-1400-ISS-198.md) — 2 tests: header total vs.
  `X-Total-Count` (`50 == 276` failed), and scroll-to-bottom fetching nothing more
  (`50 > 50` failed).
- [ISS-207](../.knowledge/cards/20260828-1617-ISS-207.md) — search for a word unique to a run
  beyond the first page returns zero rows (false negative, confirmed).
- [ISS-208](../.knowledge/cards/20260828-1617-ISS-208.md) — duration didn't separate this seed
  data (the true-longest run is recent enough to already sit in page one), so the test uses
  token totals instead: "Tokens" sort never surfaces the account's true highest-token run
  (13.6M tokens, from 2026-08-14) — confirmed (`6000000.0 >= 13609205*0.99` failed).
- [ISS-213](../.knowledge/cards/20260828-1618-ISS-213.md) — every type-filter chip undercounts;
  this account's first 50 rows happen to include at least one hit per bucket (so a chip never
  fully vanishes here), so the test proves the milder, still-card-covered undercount claim
  instead (Custom chip read 37, ≥158 more custom-bucketed runs exist beyond the loaded page).
- [ISS-209](../.knowledge/cards/20260828-1617-ISS-209.md) — **no test written.** `totalRuns`
  (`WorkflowHistory.tsx:158`) has exactly 3 references, all inside `handleLoadMore`
  (`:289-299`), which has zero triggers anywhere in the component (no button, no scroll
  listener, no `IntersectionObserver` — confirmed via `grep -n "scroll\|Intersection"`, no
  hits) — and the header/chips never read `totalRuns` either (ISS-198's own root cause). So
  `totalRuns` is not exposed by any rendered state today; a delete-then-assert test against the
  DOM was tried and came back green for the wrong reason (the header tracks `runs.length`, which
  the delete DOES correctly shrink) rather than proving the `totalRuns` staleness the card
  describes. This card is genuinely unreachable by an external test until the ISS-198 fix wires
  a Load More trigger — exactly the "currently masked by ISS-198" note already on the card. The
  5-fixer should fix ISS-209 in the same change as ISS-198 per the card's own guidance, and a
  test can be written once Load More exists.

## BUG-20260828-011700-runs-id — Run detail header's relative timestamp is stuck on "just now" for a run that finished 11+ hours ago, disagreeing with the version picker's own age label

- **Page:** Completed run — Preview tab (run detail header)
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e (and its Preview URL)
- **Severity:** Medium
- **Status:** CLOSED
- **Fix card:** [FIX-354](../.knowledge/cards/20260828-2357-FIX-354.md) — deferred remainder: [ISS-413](../.knowledge/cards/20260828-2357-ISS-413.md)
- **Fixed:** 2026-08-29 — `backend/agents/execution_engine/engine.py` now stamps the run's real
  `created_at` on the `pipeline_start` frame (UTC-promoted, best-effort read via
  `scoped_store.get_run`), `backend/tests/agents/characterization/_normalize.py` adds
  `created_at` to `_VOLATILE_STRIP_KEYS` so the 5 event goldens stay byte-untouched, and
  `frontend/src/hooks/useWorkflow.ts:511` drops the `|| new Date().toISOString()` fallback so a
  replayed frame can no longer be dated to page-load time. Verified:
  `suites/07_run_detail/test_run_detail.py -k header_relative_age` → XPASS(strict) (the pass
  signal; xfail marker left for the verifier); header now reads "18m 54s · 3.1M tokens".
- **Verified:** 2026-08-29 — `/docs` → 200 (pure-`.py`+`.ts` change, no restart needed beyond
  the already-live `--reload`). `test_run_detail.py -k header_relative_age` re-run:
  XPASS(strict) confirmed by hand, `xfail` marker then removed, re-run → plain PASS (1 passed).
  Manual repro on run `b9feac1c-ec21-4531-8ba7-bb391786993e` in lane5 Chrome, cold nav
  `/dashboard` → `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e`: `lane-run-meta` reads
  `"18m 54s · 3.1M tokens"` — no "just now", no lying value (this run's `pipeline_start` row
  predates FIX-354, so per its documented, sanctioned degrade the age segment blanks rather than
  fabricating a wrong one); version picker independently confirmed `"Version v1 · 1d ago"` —
  the two labels no longer contradict each other. 0 new console errors (1 pre-existing sandboxed
  iframe warning, unrelated). Screenshot:
  `bug-hunter/evidence/runs-id/BUG-20260828-011700-runs-id/04-after-fix-header-blank-age-version-1d-ago.png`.
  Health: `frontend && npx tsc --noEmit` — pre-existing errors only, none in
  `useWorkflow.ts`/`LaneRunHeader.tsx`. `backend && ../venv/bin/lint-imports` — 3 kept/1 broken,
  same pre-existing `kernel imports only capability ports (scaffold)` contract FIX-354 already
  documented broken. Regression: `LaneRunHeader.test.tsx` 16/16 green,
  `useWorkflow.reconnect.test.ts` 6/6 green, `test_deliverable_mimetype.py` 19/19 green, full
  `suites/07_run_detail/test_run_detail.py` (49 scenarios) exit 0, all pass/skip-live, no
  failures.
- **Validated:** 3/3 on 2026-08-28, every cycle — cold-loads a completed run's detail page deterministically, no axis variation needed
- **Issue card:** [ISS-276](../.knowledge/cards/20260828-1700-ISS-276.md)
- **Root cause:** Backend `pipeline_start` never carries `created_at`
  (`backend/agents/execution_engine/engine.py:2346-2363`). The shared `pipeline_start` reducer
  (`frontend/src/hooks/useWorkflow.ts:511`,
  `createdAt: (msg.created_at as string) || prev.createdAt || new Date().toISOString()`) is fed
  by BOTH live SSE traffic and durable-event REST replay
  (`frontend/src/app/[...view]/page.tsx:2599-2610`, `getRunEvents` → `handleWebSocketMessage`
  → same reducer). On a cold load of a completed run `prev.createdAt` is undefined (fresh
  per-run state) and the replayed frame has no `created_at`, so the fallback stamps the
  client's current wall-clock at replay/hydration time. `LaneRunHeader.tsx:257`
  (`formatRelativeAge(pipelineState?.createdAt)`) then always computes <45s elapsed → "just
  now", regardless of the run's real age. Contrast: the version picker
  (`frontend/src/components/preview/RunHeader.tsx:156`) uses the same `formatRelativeAge`
  helper but feeds it `member.created_at` from the separately-fetched, DB-backed
  `getRunFamily` endpoint — never touching this reducer — which is why it's correct.
- **Blast radius:** `pipelineState?.createdAt` has exactly one consumer in the whole frontend
  (`LaneRunHeader.tsx:257`, confirmed by grep across `frontend/src`), and `LaneRunHeader` mounts
  exactly once (`RunChatLane.tsx:2144`) — so every completed/idle run's detail-page header, for
  every pipeline type (component is workflow-agnostic), hits this on a cold load; contained to
  that one header element. Three same-file sibling hypotheses were checked against the actual
  consuming code and refuted: `agent_complete` duration prefers a server-provided `msg.duration`
  (`useWorkflow.ts:657-662`, already guarded); `tool_call.timestamp`
  (`useWorkflow.ts:1030`, unconditionally `new Date().toISOString()`) is only read by a
  live-only activity indicator gated to currently-running agents
  (`StepsOverviewSpine.tsx:525-528`, never renders once an agent is "done"); `hook_run`'s
  `created_at` (`useWorkflow.ts:1075`) feeds `pipelineState.hookRuns`, which `AuditTab.tsx`
  declares as a prop but never reads (`AuditTab.tsx:51` is the only occurrence) — Audit rows
  come from a separate, correctly DB-backed REST endpoint (`getRunHookRuns`,
  `AuditTab.tsx:478,570-597`). No new sibling cards filed as a result — see note below.
- **Proposed fix:** Backend — add the run's real `created_at` to the `pipeline_start` event's
  `data` payload (`engine.py:2346-2363`), mirroring how `agent_complete` already sends
  `duration`; the existing frontend preference (`msg.created_at ||`) then picks it up with no
  further change for new runs. Frontend (needed regardless, for runs whose durable
  `pipeline_start` row was already persisted without it) — `useWorkflow.ts:511` should stop
  manufacturing "now" as a stand-in for a real timestamp; either drop the
  `|| new Date().toISOString()` fallback (`formatRelativeAge(undefined)` already returns `""`,
  which `metaParts.filter(Boolean)` already drops — a graceful blank instead of a wrong value),
  or better, have `LaneRunHeader`'s settled branch source the age from the same DB-backed field
  the version picker already uses instead of the replay-reconstructed `pipelineState`. Belongs
  in the shared reducer/backend event, not a `LaneRunHeader.tsx`-only patch — that would only
  hide the symptom in this one caller and leave `pipelineState.createdAt` wrong for any future
  consumer.
- **Found at:** 2026-08-28 01:17 UTC
- **Found by:** bug-runs-id-r1
- **Fingerprint:** `/runs/[id]|run-detail-header-relative-time|load-completed-run-11h-old|header-reads-just-now-while-version-picker-reads-11h-ago`
- **Evidence:** `bug-hunter/evidence/runs-id/BUG-20260828-011700-runs-id/`

### Summary
The run detail page's left-hand header (below the run title, `data-testid="lane-run-meta"` area)
shows a relative timestamp for when the run happened, followed by duration and token count (e.g.
"just now · 18m 54s · 3.1M tokens"). For run `b9feac1c-ec21-4531-8ba7-bb391786993e`
(`created_at: 2026-08-27T13:48:45Z`, `completed_at: 2026-08-27T14:07:40Z`, confirmed via
`GET /api/runs/{id}`), the browser's own clock at the time of testing was
`2026-08-28T01:16:56Z` — roughly 11 hours 9 minutes after the run completed. The header still
reads "just now", which is wrong by over 11 hours. In the same page, in the same header row's
"Version v1, choose version" dropdown, the app computes and displays the correct relative age for
the identical run: "Version v1 · 11h ago". Two labels on the same page, both meant to express how
long ago this run happened, disagree by 11+ hours — one is a live, correctly-computed value, the
other is a stale/frozen "just now" that never updates. Duration ("18m 54s") and token count
("3.1M tokens") next to the broken timestamp are both individually correct against the API
(`duration: 1134.4s`, `token_usage.total_tokens: 3105278`), so only the relative-time portion of
the header is defective, not the whole meta line.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e`
   (a completed run from the prior day).
2. Observe the header meta line directly under the run title/status pill: "just now · 18m 54s ·
   3.1M tokens".
3. Read `GET http://localhost:8000/api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e` — `created_at`
   is `2026-08-27T13:48:45.894220+00:00`, `completed_at` is `2026-08-27T14:07:40.345371+00:00`.
   Read the browser's own clock via `new Date().toISOString()` — confirmed far later
   (`2026-08-28T01:16:56Z` at the time of this test), i.e. the run is genuinely ~11 hours old, not
   seconds old.
4. Click the "Version v1, choose version" button in the same header row to open the version
   listbox. Observe its own entry for this exact run/version: "Version v1 · 11h ago" — the
   correct, freshly-computed relative age for the same underlying `completed_at`.
5. Close the version picker, hard-reload the page fresh (`page.goto` to the same URL, not a soft
   navigation). Observe the header still reads "just now" immediately on load — this is not a
   transient state that later corrects itself; it is the header's steady-state value.
6. Repeat step 4 after the fresh reload — the version picker again correctly shows "11h ago" for
   the same run, reconfirming the two labels disagree deterministically, not as a one-off race.

### Expected
The header's relative timestamp should reflect the same real elapsed time the rest of the page
computes correctly (e.g. "11h ago" or an equivalent accurate relative/absolute time), consistent
with the version picker's own correct label for the identical run.

### Actual
The header is frozen on "just now" regardless of how much real time has actually elapsed since
the run finished, while a different control in the same header row (the version picker) computes
and displays the correct ~11-hour age for the same run.

### Evidence
- Before: `bug-hunter/evidence/runs-id/BUG-20260828-011700-runs-id/01-before-run-detail-loaded.png`
- Failure (header "just now" next to version picker showing "11h ago"): `bug-hunter/evidence/runs-id/BUG-20260828-011700-runs-id/02-failure-header-vs-version-mismatch.png`
- Reproduced on a fresh hard reload: `bug-hunter/evidence/runs-id/BUG-20260828-011700-runs-id/03-repro-fresh-reload-still-just-now.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e` returns `200 OK` with accurate
  `created_at`/`completed_at` timestamps; the API itself is correct, so this is a client-side
  rendering/formatting defect (likely the header's relative-time value being computed once from a
  stale/incorrect source, e.g. session-start time instead of `completed_at`, while the version
  picker correctly derives its label from the run/version's own timestamp).
- State/URL: URL stays on `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e` throughout; verified via
  direct `new Date().toISOString()` read that the browser's system clock itself is far past the
  run's actual completion time, ruling out a client-clock-skew explanation.

## BUG-20260828-012500-runs-id-steps — Steps tab footer's "input" token figure is ~20x too low and its own breakdown does not sum to the stated total

- **Page:** Completed run — Steps tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 01:25 UTC
- **Found by:** bug-runs-id-steps-r1
- **Fingerprint:** `/runs/[id]/steps|token-usage-footer|load-completed-run-steps-tab|input-token-figure-far-below-actual-breakdown-does-not-sum-to-total`
- **Evidence:** `bug-hunter/evidence/runs-id-steps/BUG-20260828-012500-runs-id-steps/`

### Summary
The Steps tab's bottom-left "TOKEN USAGE" footer (`3.1M total · 141.3K input · 192.8K output`) is
meant to break the run's total token count down into input vs. output. Its own numbers do not
add up: `141.3K + 192.8K = 334.1K`, nowhere close to the stated `3.1M total` — a discrepancy of
roughly 2.77M tokens. Cross-checking against `GET /api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e`
confirms the real figures are `total_input_tokens: 2,915,058` (2.9M), `total_output_tokens:
190,220` (190.2K), `total_tokens: 3,105,278` (3.1M) — input + output does correctly sum to total
in the API data. So the "3.1M total" and "192.8K output" figures shown are each individually
close to correct, but the displayed "input" figure (141.3K) is wrong by roughly 20x. Tellingly,
the "141.3K input" element's own accessible/tooltip text reads "Total context sent: 2.9M (2.4M
cached)" — the component has access to the correct 2.9M value in its own tooltip copy, but
renders the wrong number (141.3K, which is closer to `input − cache_read − cache_write` =
2,915,058 − 2,443,873 − 332,250 = 138,935 ≈ 141.3K after rounding/estimation) as the primary
visible label with no "excludes cached context" qualifier. A user reading only the visible text
sees a self-contradictory breakdown: a stated total that its own two visible parts cannot produce.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps`
   (a completed 4-agent PPT run).
2. Observe the "TOKEN USAGE" line pinned to the bottom-left of the Steps panel: `3.1M total ·
   141.3K input · 192.8K output`.
3. Compute `141.3K + 192.8K = 334.1K` — confirm it does not approach `3.1M total`.
4. Fetch `GET /api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e` with the current auth token and read
   `token_usage`: `total_input_tokens: 2915058, total_output_tokens: 190220, total_tokens:
   3105278` — confirms the real input figure is ~2.9M, not 141.3K, and that input+output does sum
   to total in the underlying data.
5. Hover/inspect the "141.3K input" element directly — its own tooltip/aria text reads "Total
   context sent: 2.9M (2.4M cached)", i.e. the component itself holds the correct 2.9M value but
   displays a different, much smaller number as the visible label.
6. Reload the page fresh (`page.goto` to the same URL) and re-read the footer via direct DOM text
   (`element.innerText`) — identical result: `TOKEN USAGE\n3.1M total\n·\n141.3K input\n·\n192.8K
   output`, confirming this is deterministic, not a transient render race.

### Expected
The visible "input" figure should either show the real total input tokens (2.9M, matching the
API and the element's own tooltip) so that `input + output ≈ total`, or, if the intent is to show
only non-cached "new" input tokens, the label should say so explicitly (e.g. "141.3K new input")
rather than being presented unqualified next to a total it cannot reconstruct.

### Actual
The footer shows `3.1M total · 141.3K input · 192.8K output` — a self-contradictory breakdown
where input+output (334.1K) is roughly 9x smaller than the stated total (3.1M), while the actual
API-reported input token count (2.9M) matches what the same element's own tooltip already says.

### Evidence
- Before: `bug-hunter/evidence/runs-id-steps/BUG-20260828-012500-runs-id-steps/01-before-steps-tab.png`
- Failure (footer visible, tooltip shows the correct 2.9M contradicting the 141.3K label): `bug-hunter/evidence/runs-id-steps/BUG-20260828-012500-runs-id-steps/02-failure-input-141k-vs-tooltip-2.9M.png`
- After reload, still wrong: `bug-hunter/evidence/runs-id-steps/BUG-20260828-012500-runs-id-steps/03-after-reload-still-wrong.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e` returns `200 OK` with
  `token_usage.total_input_tokens = 2915058`, directly contradicting the rendered "141.3K input".
- State/URL: URL stays on `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps` throughout; confirmed
  via direct DOM `innerText` reads (not just screenshot) both before and after a fresh reload.

- **Validated:** 3/3 on 2026-08-28, every cycle from a cold `page.goto` — deterministic, no
  timing dependency. Root cause in `frontend/src/components/workflow/TokenUsageSummary.tsx:56`.
- **Root cause:** `TokenUsageSummary.tsx:56` renders `uncachedInput` (gross input minus
  cache_read/cache_write, `:32`) as the "input" label whenever caching is active, while `total`
  (`:26`) is computed from the FULL gross `input` — so input+output can never reconstruct the
  displayed total. The correct full figure is only ever shown in the element's own `title`
  tooltip (`:54`), proving the right value is in scope and simply not the one rendered.
- **Blast radius:** sole production caller is `AgentThinkingTab.tsx:321` (Steps tab) — renders
  for a run in ANY status (generating/completed/failed/gated), not only completed runs.
  `ChatTokenWidget.tsx:93-124` independently duplicates the identical formula (its own docstring
  says it "Mirrors TokenUsageSummary") — dormant/unmounted in production today (only its
  `composedContextUsage` helper is imported by `RunChatLane.tsx:67-71`) but will reproduce the
  same defect once wired into the chat lane. Checked and ruled out: backend
  `concierge.py get_token_usage()` (reports the plain gross figure, no subtraction) and
  `AnalyticsPage.tsx:224-232,604-619` (computes the same uncached value but labels it "New
  Input" inside a 4-segment breakdown that does reconcile to the total — the fix precedent).
- **Fix belongs in:** a shared helper (e.g. `{total, uncachedInput, cacheRead, cacheWrite,
  hasCaching}` from a `PipelineRunState`) called by both `TokenUsageSummary.tsx` and
  `ChatTokenWidget.tsx` instead of each hand-rolling the same subtraction, modeled on
  `AnalyticsPage.tsx`'s already-correct labeling.
- **Issue cards:** [ISS-278](../.knowledge/cards/20260828-1700-ISS-278.md) (root),
  [ISS-385](../.knowledge/cards/20260828-2225-ISS-385.md) (sibling: ChatTokenWidget.tsx
  duplicates the same formula, currently unmounted)
- **Fixed:** `TokenUsageSummary.tsx:56` now renders `{formatTokens(input)} input` — the same
  gross `totalInputTokens` the `total` beside it is derived from — so the footer's two visible
  parts reconstruct the stated total; the tooltip keeps the cached share. The orphaned
  `uncachedInput` local is gone. `ChatTokenWidget.tsx` (the dormant duplicate) got the same
  treatment: the `in` segment is unconditional and gross, only the amber `⚡ N cached (P%)`
  segment stays behind `hasCaching`. The shared helper both cards proposed was NOT created —
  with the subtraction deleted from both files there is no shared arithmetic left to extract,
  and the goal it served (no dormant copy) is met by fixing both call sites in one pass.
  Vitest: TokenUsageSummary.footerSum 2/2 XPASS ("Error: Expect test to fail" — the red run IS
  the pass signal, `it.fails` markers left in place for the verifier); TokenUsageSummary.cache
  5/5 green; ChatTokenWidget 6/6 green. `npx tsc --noEmit`: no error in either changed file
  (the 6 reported are HomeLaunchGrid.crossAccountLeak / listenerMiddleware tests, other work in
  this tree). eslint on both files: 0 errors, 1 pre-existing unused-`modelId` warning on the
  untouched props signature. Frontend-only: no backend restart, no migration, no engine or
  import-linter surface involved.
- **Fix card:** [FIX-353](../.knowledge/cards/20260828-2353-FIX-353.md) — resolves
  [ISS-278](../.knowledge/cards/20260828-1700-ISS-278.md) (status: resolved, verification:
  passed) and [ISS-385](../.knowledge/cards/20260828-2225-ISS-385.md) (status: resolved,
  verification: optional — the widget is still mounted nowhere, so its fix is settled by
  construction and by its own unit suite, not by a UI reproduction).
- **Verified:** `TokenUsageSummary.footerSum.test.tsx` (2 cases) confirmed XPASS
  ("Error: Expect test to fail" on both `it.fails`), `xfail`/`it.fails` markers removed,
  re-run plain green: `TokenUsageSummary.footerSum.test.tsx` + `TokenUsageSummary.cache.test.tsx`
  + `ChatTokenWidget.test.tsx` = 13/13 passed. Manual repro re-run by hand in Chrome
  (qa-admin, cold `page.goto` to `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps`): footer now
  reads `TOKEN USAGE · 3.1M total · 2.9M input · 192.8K output` — 2.9M + 192.8K reconstructs
  3.1M, and the tooltip ("Total context sent: 2.9M (2.4M cached)") now agrees with the visible
  label instead of contradicting it. `npx tsc --noEmit`: 0 errors in the two changed files (6
  pre-existing errors remain in unrelated `HomeLaunchGrid.crossAccountLeak.test.tsx` /
  `listenerMiddleware.test.ts`, confirmed at HEAD, not introduced by this fix). Backend
  `/docs` → 200 (frontend-only change, no restart needed). Regression:
  `AgentThinkingTab.test.tsx` (sole production caller's own suite) 6/6 green. No new console
  errors (1 pre-existing sandboxed-iframe warning, unrelated to this component). After
  screenshot: `bug-hunter/evidence/runs-id-steps/BUG-20260828-012500-runs-id-steps/04-after-fix-verified.png`.

## BUG-20260828-012700-runs-id-steps-agent — Deep-linking a specific agent's step URL never opens that agent's detail pane; it renders the plain unfiltered lane list instead

- **Page:** Completed run — one agent's step detail
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps/<agentId> (e.g. `/steps/ppt-brief-analyst`, `/steps/ppt-composer`)
- **Severity:** Medium
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, each from a cold start (fresh `page.goto`, not a soft nav) — real agent id `ppt-brief-analyst` (cycles 1 and 3), real agent id `ppt-composer` (cycle 2), all identical: bare unfiltered lane list, no breadcrumb, no detail. Manual click in cycle 3 confirmed the same root behaviour the hunter reported: detail renders on click but `location.href` stays byte-identical, verified via `page.evaluate`.
- **Fix card:** [FIX-359](../.knowledge/cards/20260829-0014-FIX-359.md)
- **Fixed:** 2026-08-29 — the deep-link seam now carries the agent the URL names.
  `TabDeepLinkTarget` gains an optional `agentId` and `requestOpenTab(tab, agentId?)` mints it
  (`frontend/src/hooks/useTabDeepLink.ts`); a new `deepLinkAgentIdFor(parsed)` selector
  (`frontend/src/app/[...view]/page.tsx:214-223`, mirroring `pinnedVersionFor`) feeds it at BOTH
  producer call sites (`:3220` shallow-nav/back-forward branch, `:3293` cold-mount `.finally()`);
  `PreviewPanel` forwards `initialAgentId={deepLinkTarget?.agentId}` to `<AgentThinkingTab>`,
  whose new optional `initialAgentId` prop seeds `selectedAgentId` and re-applies on a later
  deep link. Opaque id only, matched against the run's own `agents[].id` — no name branch
  (SC-001). Frontend-only: no backend file, no migration, no engine edit.
  Tests observed: `tests/integration/e2e/suites/07_run_detail/test_run_detail_agent_deeplink.py`
  → `[XPASS(strict)] ISS-277 unfixed` (the pass signal; xfail marker left for 6-verifier).
  Same suite by node id: S-07-10 SKIPPED (its own built-in fallback — rows carry no
  `data-agent-id`, pre-existing), S-07-11 PASS. Frontend unit: 36 tests green across
  `runTabShallowNav.test.ts` (3), `useTabDeepLink.test.ts` (4), `AgentThinkingTab.test.tsx` (6),
  `AgentThinkingTab.narrativeOrder`+`prototypePreamble` (4), `PreviewPanel.test.tsx` (19).
  `npx tsc --noEmit`: only the two failures this register already baselined as pre-existing
  (`HomeLaunchGrid.crossAccountLeak.test.tsx`, `listenerMiddleware.test.ts`), neither in a
  touched file. DISCLOSED TEST EDIT: `runTabShallowNav.test.ts:62` pins the deep-link call by
  exact source text; the card-mandated signature widening lengthened that call, so the literal
  was updated to `requestOpenTab(openTab, deepLinkAgentIdFor(parsedView))` — same guard intent,
  strictly stronger, no assertion weakened. NOT fixed here (still open, separate cards):
  ISS-387 (selection still never pushes history — the OUT direction) and ISS-386
  (`routes.runStepsAgent` still has no `version` param).
- **Verified:** 2026-08-29 —
  `tests/integration/e2e/suites/07_run_detail/test_run_detail_agent_deeplink.py::test_a_fresh_deeplink_to_steps_agent_opens_that_agents_detail_pane`
  ran XPASS(strict) confirming the fix, xfail marker removed, re-run plain green
  (issue marker kept). Manual re-run of the register's own repro in Chrome (lane6),
  same run `b9feac1c-ec21-4531-8ba7-bb391786993e`: fresh `page.goto` to
  `/steps/ppt-brief-analyst` now renders the "Steps / Presentation Strategist Agent"
  breadcrumb and detail pane directly, no manual click needed; a reload of the same
  URL still shows it; a second fresh nav to `/steps/ppt-composer` opens "Steps /
  Deck Engineer Agent" the same way. Regression, same suite by node id: S-07-10
  SKIPPED (pre-existing, own built-in fallback, unrelated), S-07-11 PASS. Frontend
  unit: 13/13 green across `runTabShallowNav.test.ts`, `useTabDeepLink.test.ts`,
  `AgentThinkingTab.test.tsx`. `npx tsc --noEmit`: only the same two pre-existing
  failures (`HomeLaunchGrid.crossAccountLeak.test.tsx`, `listenerMiddleware.test.ts`),
  neither touched by this fix. `lint-imports` (run from `backend/`): 1 pre-existing
  broken contract (`kernel imports only capability ports`), unrelated backend-only
  finding, not introduced by this frontend-only change. Backend not restarted —
  no `.py` file touched; `:8000/docs` confirmed 200. After-screenshot:
  `bug-hunter/evidence/runs-id-steps-agent/BUG-20260828-012700-runs-id-steps-agent/04-after-fix-fresh-deeplink-shows-detail.png`.
- **Issue card:** [ISS-277](../.knowledge/cards/20260828-1659-ISS-277.md)
- **Found at:** 2026-08-28 01:27 UTC
- **Found by:** bug-runs-steps-agent-r1
- **Fingerprint:** `/runs/[id]/steps/[agentId]|steps-tab-lane-detail-panel|fresh-navigation-or-reload-of-agent-deep-link|no-agent-detail-renders-only-list-view`
- **Evidence:** `bug-hunter/evidence/runs-id-steps-agent/BUG-20260828-012700-runs-id-steps-agent/`, `bug-hunter/evidence/runs-id-steps-agent/_scratch/`

### Summary
The Steps tab's URL scheme includes a per-agent segment (`/runs/{id}/steps/{agentId}`), and the
app itself generates and links to these URLs (e.g. the "Answer in Steps"/"Open in Steps" chat
buttons, and the breadcrumb "Steps / <Agent Name>" shown once an agent is selected). The clear
implication is that this URL should deep-link directly to that agent's own detail pane — its
reasoning, full input prompt, agent output, and context-received sources. It does not. A fresh
`page.goto` to any such URL (tested with all four real agent ids from this run — `ppt-brief-
analyst`, `ppt-composer` — plus a nonexistent id, `nonexistent-agent-xyz`) renders the Steps tab
correctly selected in the top tablist, but the content pane shows only the plain, unfiltered lane
list of all four agent buttons (Presentation Strategist Agent, Deck Engineer Agent, Deck QA
Agent, PPTX Code Generator) with no agent expanded, no breadcrumb, and no detail content —
identical regardless of which agent id (real or fake) is in the URL. The only way to see an
agent's detail is to manually click its row after the page has already loaded, at which point
the breadcrumb "Steps / Presentation Strategist Agent" appears and the detail pane (reasoning,
full input prompt, agent output, context sources) renders correctly — but this in-page click
never changes the URL, so the state that was just achieved cannot be reloaded, shared, or
bookmarked: reloading the exact same URL that is currently showing full agent detail throws that
detail away and reverts to the bare list.

### Reproduction
1. Sign in as qa-admin. Resolve real agent ids for run `b9feac1c-ec21-4531-8ba7-bb391786993e` via
   `GET /api/runs/{id}/events?after=0` (`agent_start` events give `ppt-brief-analyst`,
   `ppt-composer`, `ppt-deck-qa-v2`, `ppt-code-generator`, displayed as "Presentation Strategist
   Agent", "Deck Engineer Agent", "Deck QA Agent", "PPTX Code Generator" respectively).
2. Fresh `page.goto` to `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps/ppt-brief-analyst`.
   Wait 2+ seconds for full settle. Observe: "Steps" tab is selected in the tablist, but the pane
   shows only the plain lane list of all 4 agent buttons — no breadcrumb, no expanded detail for
   "Presentation Strategist Agent" even though it is named directly in the URL.
3. Manually click the "Presentation Strategist Agent" button in that same list. Observe: the
   breadcrumb "Steps / Presentation Strategist Agent" now appears, and the detail pane renders
   ("Reasoning" toggle, full JSON spec output, "Full input prompt 7,804 chars", "Agent output
   9.7k chars", "Context received — 2 sources fed in: prompt.md, Template: html-ppt-zhangzara-
   scatterbrain"). Confirm via the address bar that `location.href` did NOT change — it is still
   the exact same `/steps/ppt-brief-analyst` URL from step 2.
4. Fresh `page.goto` to that identical, unchanged URL again (equivalent to a reload). Observe:
   the detail pane just shown in step 3 is gone; the pane is back to the bare 4-button list with
   no breadcrumb and no selection — the same starting state as step 2, despite the URL never
   having changed and still literally naming this agent.
5. Repeated steps 2-4 on a second, different agent id, `/steps/ppt-composer` — identical result:
   fresh load shows only the bare list, manual click opens detail without changing the URL.
6. For contrast, navigated to a nonexistent agent id, `/steps/nonexistent-agent-xyz` — renders
   identically to the real ids on fresh load (bare list, Steps tab selected, no error, no 404),
   confirming the URL segment has no effect on the rendered content at all, valid or invalid.

### Expected
Loading `/runs/{id}/steps/{agentId}` — whether via a fresh navigation, a reload, or a shared/
bookmarked link — should deep-link directly to that agent's own detail pane (matching what a
manual click on that agent's row produces), since the app itself both names this URL shape and
generates links into it. At minimum, the manual "select an agent" client action should push/
replace the URL to reflect the selection it just made, so the resulting state is reloadable.

### Actual
The `{agentId}` URL segment is inert on load: every fresh navigation or reload renders the same
undifferentiated lane list regardless of which (or whether a valid) agent id is present. Detail
can only be reached by an in-page click, and that click never syncs the URL, so the detail view
is unreachable by direct navigation and is lost on reload.

### Evidence
- Before (fresh deep-link to `/steps/ppt-brief-analyst`, no detail shown): `bug-hunter/evidence/runs-id-steps-agent/BUG-20260828-012700-runs-id-steps-agent/01-before-fresh-deeplink-no-detail.png`
- Manual click on the same page reveals the detail, URL unchanged: `bug-hunter/evidence/runs-id-steps-agent/BUG-20260828-012700-runs-id-steps-agent/02-manual-click-shows-detail.png`
- Reloading that identical URL loses the detail again: `bug-hunter/evidence/runs-id-steps-agent/BUG-20260828-012700-runs-id-steps-agent/03-after-reload-still-list-only.png`

### Browser Signals
- Console: no relevant error observed on any of the fresh loads (real or fake agent id).
- Network: all page-load requests (`/api/runs/{id}`, `/api/runs/{id}/events?after=0`,
  `/api/runs/{id}/family`, `/api/runs/{id}/sandbox`, `/api/runs/{id}/gate-events`) return `200
  OK` identically for `ppt-brief-analyst`, `ppt-composer`, and `nonexistent-agent-xyz` — the data
  layer never distinguishes the URL's agent segment, confirming the gap is purely in client-side
  routing/selection logic, not a failed fetch.
- State/URL: `location.href` retains the full `/steps/{agentId}` path through every step,
  including immediately after the manual click that opens the detail pane — the URL is written
  once by navigation and never updated or read back by the selection logic.

- **Root cause:** `agentId` is dropped end-to-end, confirmed at every hop by direct read.
  `reopenTabFor(screen: ParsedView["screen"])` (`frontend/src/app/[...view]/page.tsx:228-234`)
  is typed to accept only the screen name, so it structurally cannot see `agentId` even though
  the full `parsedView` object (with `.agentId`) is in scope at both call sites
  (`page.tsx:3189`, `:3237`). `TabDeepLinkTarget` (`frontend/src/hooks/useTabDeepLink.ts:28-33`)
  carries only `{tab, nonce}` and `requestOpenTab` is typed `(tab: string) => void` (`:38-39`) —
  no field exists to carry an agent id even one layer downstream. `PreviewPanel`'s deep-link
  consumer effect (`PreviewPanel.tsx:814-837`) reads only `.tab` and calls `setActiveTab`; it
  invokes `<AgentThinkingTab>` with no agent-id-shaped prop at all (`:1360-1384`). Finally,
  `AgentThinkingTabProps` (`AgentThinkingTab.tsx:22-46`) has no such field, and
  `selectedAgentId` (`:84`) is plain `useState<string | null>(null)`, unconditionally `null` on
  every mount regardless of the URL. The reverse direction is equally absent: the manual click
  handler `onOpenAgent={(id) => { setSelectedAgentId(id); ... }}` (`:295`) and its task-level and
  `onBack` counterparts (`:254`, `:260`, `:282`) never call `router.push`/`replace` or
  `window.history.pushState`/`replaceState` — confirmed by grepping `AgentThinkingTab.tsx`,
  `StepsOverviewSpine.tsx`, and `AgentDetailPanel.tsx` for `router\.|useRouter|window.history|
  pushState|replaceState`: the only hit is an unrelated "divert to another run's live stream"
  push in `StepsOverviewSpine.tsx:43,52`.
- **Blast radius:** `routes.runStepsAgent` (the typed builder for this URL) has zero production
  callers today — `grep -rn "runStepsAgent" frontend/src/` matches only `routes.ts` itself and
  its own test. The "Answer in Steps"/"Open in Steps" chat CTAs named in this entry's Summary
  (`ResultCard.tsx:54-91`) call the generic `onRequestOpenTab("thinking")` directly — by design,
  per SC-001 (never key chat behavior on an agent/workflow name) — and never build or navigate
  to a `/steps/{agentId}` URL; likewise the breadcrumb (`AgentDetailPanel.tsx:994`) renders as a
  plain `<button>`, not a link. So the only path into this bug today is direct/shared/bookmarked
  navigation to the URL `routes.ts` itself defines and documents — a path ADR-0018 makes a
  first-class contract ("every URL... routes.ts is the single source for building and parsing
  it"), independent of caller count. Two further gaps surfaced from the same trace, filed as
  siblings: (1) the missing-history-push above also means the browser Back button, after a
  manual agent/task selection, skips the Steps list entirely and lands on whatever page preceded
  the Steps tab, since no history entry was ever created for the selection; (2)
  `routes.runStepsAgent` is the only run-tab builder in `routes.ts` with no `version` parameter
  (`routes.ts:72-89`), unlike `runSteps`/`runFiles`/`runWorkspace`/`runAudit`, even though
  `parseViewPath` (`:319-339`) already parses `/versions/{v}/steps/{agentId}` into a `version`
  field for this exact screen — the builder cannot construct what the parser already accepts.
- **Fix belongs in:** the shared `TabDeepLinkTarget`/`requestOpenTab` seam
  (`useTabDeepLink.ts`) — widen it to optionally carry an agent id, since every deep-link
  producer (page.tsx's cold-mount effect, and `ResultCard`'s chat CTAs) already routes through
  this one interface. Thread that value through `PreviewPanel`'s consumer effect into a new
  `AgentThinkingTab` prop (e.g. `initialAgentId`) that seeds `selectedAgentId`'s initial value.
  For the reverse direction, `onOpenAgent`/`onBack` in `AgentThinkingTab.tsx` need to call
  `router.push`/`replace` with `routes.runStepsAgent(runId, agentId)` (or `routes.runSteps(runId)`
  on back-to-list) so selection state and the URL/history stay in sync both ways. Not a
  page.tsx-only patch: `reopenTabFor`'s signature, `TabDeepLinkTarget`'s shape, and
  `AgentThinkingTab`'s prop surface all need the same new field so every existing caller keeps
  routing through one seam rather than growing a second, parallel channel.
- **Issue cards:** [ISS-277](../.knowledge/cards/20260828-1659-ISS-277.md) (root),
  [ISS-386](../.knowledge/cards/20260828-2228-ISS-386.md) (sibling: routes.runStepsAgent has no
  version param, unlike its four sibling builders), [ISS-387](../.knowledge/cards/20260828-2228-ISS-387.md)
  (sibling: no history entry on manual agent/task selection breaks the browser Back button)

## BUG-20260828-012900-runs-id-files — Files tab never lists the run's real PPTX binary deliverable; instead shows a scratch tmp/ HTML file mislabeled as "Final output"

- **Page:** Completed run — Files tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28. Ran `tests/integration/e2e/suites/07_run_detail/test_run_detail.py::test_a_ppt_v2_runs_final_output_is_the_declared_deliverable_not_a_tmp_scratch_file` (XPASS confirmed, xfail marker removed, re-run plain green), plus `frontend/src/components/results/FilesTab.baseVersion.test.tsx` and `frontend/src/components/history/WorkflowHistory.pptV2Files.test.tsx` (both XPASS on their ISS-215/ISS-214 guards; ISS-215's `it.fails` and ISS-214's first `it.fails` removed, both re-run green; ISS-214's second guard intentionally left `it.fails` per FIX-327 — that prop stays `undefined` by design once ppt_v2 no longer reaches the generic branch). Manually re-ran the original repro in the browser (lane4, signed in qa-admin, cold nav to `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files`): "Final output" now reads `presentation.pptx`, PPTX (.pptx), 159.9 KB, validated — matches the fixer's claim, no longer the tmp scratch HTML. "6 files available · 1 deliverable" unchanged. No new console errors. Regression: S-07-12/S-07-13 pass; frontend `FilesTab.test.tsx`, `FilesTab.runInput.test.tsx`, `WorkflowHistory.genericReopen.test.tsx`, `WorkflowHistory.test.tsx`, `api.test.ts` — 42/42 pass. Backend untouched (frontend-only fix), `/docs` 200. `lint-imports` (run from `backend/`) shows one broken contract (`kernel imports only capability ports`) confirmed pre-existing via `git status --porcelain backend/` (no backend diff in this tree). `npx tsc --noEmit` shows only the two pre-existing failures the fixer already noted (`HomeLaunchGrid.crossAccountLeak.test.tsx`, `listenerMiddleware.test.ts`), none in the touched files.
- **Root cause:** `frontend/src/app/[...view]/page.tsx:1470` (live `pipeline_complete` handler)
  and `:2985` (reopen handler, gated by `isContentTerminal` at :2980-2981 which covers both
  `completed` and `degraded`) both route `pipelineType`/`fullRun.type` in
  `{"ppt","ppt_v2","ppt_revision"}` into `setPptContent(finalOutput)` /
  `setPptContent(fullRun.output)` — the run's raw `output` field (`ctx.last_streamed`, the text
  the LAST agent streamed). For `ppt_v2` the last agent is step 4 ("PPTX Code Generator"), whose
  own streamed text is not `presentation.html` (written by step 3, only read by step 4 per
  ADR-0029's "one writer per file") and in this run matches the `tmp/` scratch file's content
  instead. `FilesTab.tsx`'s `deriveDeliverableFiles` (called at `FilesTab.tsx:547`) then builds
  the "Final output" row's name/size purely by regex-parsing that same wrong `pptContent` string
  (`<title>`/`<h1>` match, lines 393-399) — it never calls back to the run's workspace/sandbox
  listing (`GET /api/runs/{id}/sandbox`) to resolve the file the backend actually names
  `deliverable_filename`, unlike `PreviewPanel.tsx`'s header Download button, which already does
  exactly that (FIX-318, `PreviewPanel.tsx:846-910`: fetches `deliverableFilename`, lists the
  workspace via `getRunSandbox`, and picks a declared-extension-keyed sibling — declared `.html`
  prefers `<stem>.pptx` — gated on the file's actual presence in the listing). CONFIRMED by direct
  read of `page.tsx:1464-1477,2980-2988`, `FilesTab.tsx:390-400,543-547`, and
  `PreviewPanel.tsx:822-910,1280`.
- **Blast radius:** Grepped every non-test `<FilesTab` render and every
  `deriveDeliverableFiles`/`setPptContent` call site. Three callers share the identical flaw: (1)
  `PreviewPanel.tsx:1280` — the reported main run screen (root, ISS-199); (2)
  `WorkflowHistory.tsx:904` — the History browser's own detail panel, which additionally runs a
  SECOND, independently-drifted type check (`WorkflowHistory.tsx:542`'s `isPpt` omits `ppt_v2`
  entirely, landing it in the generic-deliverable branch with `filename: undefined` instead of
  even the mislabeled row — ISS-214); (3) `FilesTab.tsx:436-440` — the component's own lazily-
  fetched "From v{n-1}" base-version section, which passes `parentRun.type` RAW (no
  normalization) into the same helper and has no generic-deliverable fallback wired in at all, so
  a ppt_v2 base version renders zero file rows, silently (ISS-215). `setPptContent` has two more
  call sites (`page.tsx:1803,2482`) but both are gated behind an explicitly-commented "legacy chat
  mode" message shape (`chatDetail.final_output`/`msg.data` parsed as
  `{user_stories,ppt,prototype}` JSON) — a different, older architecture than the single-string
  `pipeline_type`/`final_output` run model `ppt_v2` uses; INFERRED unreachable for `ppt_v2`, not
  confirmed live. "Download" on the Final output row and "Download All" both consume the SAME
  derived `files` array (`FilesTab.tsx:504-568,662`), so they inherit the identical wrong content
  — not a separate defect. A dead `else if (file.id === "presentation-pptx")` handler
  (`FilesTab.tsx:611-652`, a client-side HTML→PPTX conversion via `POST /api/runs/export-pptx`) is
  CONFIRMED unreachable today — `deriveDeliverableFiles` never emits that id — but is a trap for
  the fix: adding a `presentation-pptx` row without touching this handler would round-trip the
  wrong HTML through a client-side reconversion endpoint instead of fetching the real binary via
  the same `getRunSandboxFileBlob` path the Workspace tab and header Download already use
  (FIX-316/FIX-318).
- **Fix belongs in:** FIX-318 already solved this exact class of problem for the header Download
  button by building a shared resolver — declared filename + workspace listing + extension-keyed
  sibling preference — but left it INLINED as a local `useEffect`/`useState` in
  `PreviewPanel.tsx:846-910`, not shared. The fix belongs in pulling that resolution into one
  exported function (e.g. alongside `getRunSandbox`/`getRunSandboxFileBlob` in
  `frontend/src/lib/api`, or exported from `FilesTab.tsx`) that `FilesTab.tsx:547`'s main
  derivation, `WorkflowHistory.tsx`'s `isPpt`/`isGeneric` block, and `FilesTab.tsx:436-440`'s
  base-version fetch all call instead of independently guessing from raw streamed content — one
  shared resolver is a smaller diff than patching three drifted call sites separately, and is the
  only way to stop a fourth caller from reintroducing the same guess. Must key on the declared
  file's EXTENSION, never the workflow-type string (SC-001) — `WorkflowHistory.tsx`'s and
  `FilesTab.tsx:436`'s own unnormalized type checks are what already produced ISS-214/ISS-215.
- **Validated:** 3/3 on 2026-08-28, every cycle (cold nav to /dashboard then to /runs/<id>/files) — deterministic, no timing/session dependency found
- **Issue card:** [ISS-199](../.knowledge/cards/20260828-1600-ISS-199.md)
- **Issue cards:** [ISS-199](../.knowledge/cards/20260828-1600-ISS-199.md) (root),
  [ISS-214](../.knowledge/cards/20260828-1633-ISS-214.md) (sibling: History browser's Files tab
  has no ppt_v2 normalization, drops to the generic-deliverable branch),
  [ISS-215](../.knowledge/cards/20260828-1633-ISS-215.md) (sibling: base-version "From v{n-1}"
  section drops a ppt_v2 parent to zero file rows)
- **Found at:** 2026-08-28 01:29 UTC
- **Found by:** bug-runs-id-files-r1
- **Fingerprint:** `/runs/[id]/files|files-tab-final-output-selection|open-ppt-v2-completed-run|real-pptx-binary-never-listed-tmp-html-shown-instead`
- **Evidence:** `bug-hunter/evidence/runs-id-files/BUG-20260828-012900-runs-id-files/`

### Summary
This is a "Ppt V2" run (4 agents: Presentation Strategist, Deck Engineer, Deck QA, PPTX Code
Generator) whose entire purpose is producing a `.pptx` deck. The backend's own sandbox listing
(`GET /api/runs/{id}/sandbox`) confirms a real, complete binary artifact exists on disk:
`presentation.pptx`, 163,771 bytes, `"kind":"binary"`, `"deliverable":true`. The run detail API
also independently names a canonical deliverable: `deliverable_mimetype: "text/html"`,
`deliverable_filename: "presentation.html"` (54,551 bytes, also `deliverable:true` in the sandbox
listing). Neither of these two legitimate candidates is what the Files tab actually shows. The
"Final output" card instead displays `kindred-a-custombuilt-social-network-pla.html` (53.2 KB) —
which, by matching size (54,588 bytes), is `tmp/kindred-pitch-deck.html`, a scratch/intermediate
file the Deck Engineer agent wrote mid-pipeline into a `tmp/` working directory, also marked
`deliverable:true` in the sandbox but clearly not the intended canonical output (it lives under
`tmp/`, and its filename doesn't match anything the run itself calls its deliverable). Both
"Download" on the Final output row and "Download All" confirm this: neither ever fetches
`presentation.pptx` or `presentation.html` — only the tmp HTML file, the 4 agent `.md` outputs,
and `prompt.md`. The one artifact that actually represents this workflow's stated purpose (a
PowerPoint file) is completely absent from the Files tab — not listed, not previewable, not
downloadable, individually or via "Download All" — despite existing, complete, and explicitly
flagged as a deliverable by the run's own backend.

### Reproduction
1. Sign in as qa-admin, navigate to `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files` (a
   completed "Ppt V2" run). Wait for settle.
2. Observe the "Files" panel: "6 files available · 1 deliverable", with "Final output" showing
   `kindred-a-custombuilt-social-network-pla.html`, HTML (.html), 53.2 KB, validated.
3. Independently inspect `GET /api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/sandbox` (fired by
   the page itself). It lists, among others: `presentation.pptx` (163,771 bytes,
   `kind:"binary"`, `deliverable:true`), `presentation.html` (54,551 bytes, `deliverable:true`),
   and `tmp/kindred-pitch-deck.html` (54,588 bytes, `deliverable:true`) — three separate
   deliverable-flagged candidates, none of which is `presentation.pptx` in the UI.
4. Inspect the run detail response: `deliverable_mimetype: "text/html"`,
   `deliverable_filename: "presentation.html"` — the backend's own canonical answer, which is
   also not what the Files tab shows as "Final output".
5. Click "Download" on the Final output row — the browser downloads
   `kindred-a-custombuilt-social-network-pla.html` (confirmed via the download event), matching
   `tmp/kindred-pitch-deck.html` by size — not `presentation.pptx`, not `presentation.html`.
6. Click "Download All" — confirmed downloads are exactly: the same tmp HTML file, the 4
   `NN-<agent>.md` agent-output files, and `prompt.md`. `presentation.pptx` is never among them.
7. Reload the page fresh (`page.goto` on the identical URL) and re-check the Files panel —
   identical result: "Final output" is still the tmp HTML file, `presentation.pptx` is still
   completely absent from the file list.

### Expected
The Files tab's "Final output"/deliverable should surface the artifact the run's own backend
names as canonical (`deliverable_filename: "presentation.html"`), or — given this is a PPTX-
producing workflow whose last agent is literally "PPTX Code Generator" — the actual
`presentation.pptx` binary that agent produced. At minimum, a complete, deliverable-flagged
`.pptx` binary that exists on the server should be listed and downloadable somewhere on this
page, not omitted entirely in favor of an intermediate scratch file from a `tmp/` directory.

### Actual
The Files tab labels a `tmp/`-directory scratch HTML file as "Final output" and never lists,
previews, or makes downloadable (individually or via "Download All") either of the two
legitimate deliverable candidates — the backend-declared `presentation.html` or the actual
`presentation.pptx` binary this PPT workflow exists to produce.

### Evidence
- Files tab, Final output shows the tmp HTML file, pptx nowhere in the list: `bug-hunter/evidence/runs-id-files/BUG-20260828-012900-runs-id-files/01-files-tab-final-output-is-tmp-html.png`
- Fresh reload, identical result: `bug-hunter/evidence/runs-id-files/BUG-20260828-012900-runs-id-files/02-after-reload-still-missing-pptx.png`
- Sandbox API excerpt showing the deliverable-flagged files vs. what the UI shows: `bug-hunter/evidence/runs-id-files/BUG-20260828-012900-runs-id-files/network.log`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs/{id}/sandbox` returns 200 OK with the full, correct file listing
  (including `presentation.pptx` and `presentation.html`, both `deliverable:true`); the mismatch
  is in client-side selection/rendering logic, not a failed or missing fetch.
- State/URL: URL stays on `/runs/{id}/files` throughout; reproduces identically on both the
  initial load and a completely fresh reload, so this is deterministic, not a race.

- **Issue card:** [ISS-199](../.knowledge/cards/20260828-1600-ISS-199.md)

## BUG-20260828-013500-runs-id-workspace — Workspace tab's "Code" file viewer is a live, freely-editable text editor with no read-only indication for a completed run

- **Page:** Completed run — Workspace tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/workspace
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 by the verifier —
  `frontend/src/components/results/SandboxTab.readOnlyIndicator.test.tsx` (`npx vitest run
  ... --no-coverage`): both ISS-383/ISS-597 cases XPASSed ("Error: Expect test to fail"), the
  `it.fails` markers were removed and a re-run confirmed plain green, 2/2 passed.
  `frontend/src/components/preview/PreviewPanel.workspaceDuringRun.test.tsx`: ISS-598 XPASSed the
  same way, marker removed, re-run confirmed plain green, 1/1 passed. Manual repro by hand in
  real Chrome (qa-admin, cold nav to
  `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/workspace`) now shows "Read-only scratchpad — edits
  are not saved" under the CodeMirror pane on both `.browser/deck-styles.json` (Code toggle) and
  `PLANNER.md` (Code toggle) — the doc is still editable by design (Replace still writes) but the
  indicator is now visible in both places the original repro hit. 0 new console errors (1
  pre-existing, unrelated iframe-sandbox warning). Regression files green:
  `SandboxTab.test.tsx` 37/37, `PreviewPanel.test.tsx` 19/19. `curl :8000/docs` → 200
  (frontend-only fix, no restart needed). `npx tsc --noEmit` shows 0 errors in the changed files.
  `lint-imports` from `backend/` shows the same pre-existing `kernel_services -> app.api` broken
  contract as before this fix (frontend-only change, not caused by it). Before/after screenshots:
  `bug-hunter/evidence/runs-id-workspace/BUG-20260828-013500-runs-id-workspace/05-after-json-code-view-readonly-indicator.png`
  and `06-after-md-code-view-readonly-indicator.png`.
- **Validated:** 3/3 on 2026-08-28, cold start each cycle, three different files
  (`PLANNER.md`, `01-ppt-brief-analyst.md`, `deck-styles.json`) — `.cm-content.isContentEditable`
  is `true` and typed text inserts live in every cycle, with no read-only indication.
  `SandboxTab.tsx`'s `CodeView` doc comment (line 476) states "CodeMirror 6, read-only" but the
  actual `EditorView` never sets a readOnly config and includes edit keymaps — the component's
  own documented contract is violated by its implementation.
- **Issue card:** [ISS-383](../.knowledge/cards/20260828-2021-ISS-383.md)
- **Root cause:** `CodeView`'s shared CodeMirror `EditorView` extensions array
  (`SandboxTab.tsx:675-701`) never sets `EditorState.readOnly.of(true)` /
  `EditorView.editable.of(false)`, contradicting its own top-of-file doc comment (`:476-491`,
  "read-only... edit keymaps... not pulled in"). But an inline comment (`:687-690`) and an
  EXISTING, PASSING test (`SandboxTab.test.tsx:375-410`, asserts `contenteditable === "true"` and
  a working Replace control) show the editable DOM is deliberate, to keep CodeMirror's ⌘F
  Find-and-Replace functional over a scratchpad copy that never persists — so the doc comment, not
  the implementation, is what is actually stale. A naive blanket `readOnly.of(true)` fix would
  block Replace's own dispatched transactions and fail that existing test; the real gap is a
  missing user-facing signal ("this is a throwaway scratchpad, not the file"), not a missing
  engine-level lock.
- **Blast radius:** both call sites of `CodeView` in `SandboxTab.tsx` — the "Code" toggle
  (`:1331`, the path actually tested) AND every fenced code block inside a markdown file's
  default, un-toggled Preview render (`:411`, via `MD_COMPONENTS.code`, untested) — reachable for
  a run in ANY status, including one still generating: `PreviewPanel.tsx:753-755` gates the
  Workspace tab purely on `workspaceRunId` truthiness, no run-status check, and `workspaceRunId`
  falls back to the live `pipelineState.pipelineRunId` (`:701` confirms `pipelineState.isRunning`
  is that same live object's own field).
- **Issue cards:** [ISS-383](../.knowledge/cards/20260828-2021-ISS-383.md) (root),
  [ISS-597](../.knowledge/cards/20260829-0135-ISS-597.md) (sibling: same unguarded CodeView
  reached via a markdown file's default Preview-mode fenced blocks, not just the Code toggle),
  [ISS-598](../.knowledge/cards/20260829-0136-ISS-598.md) (sibling: same unguarded CodeView
  reachable on a still-generating run's Workspace tab, no status gate)
- **Found at:** 2026-08-28 01:35 UTC
- **Fix card:** [FIX-409](../.knowledge/cards/20260829-0449-FIX-409.md) — one
  `Read-only scratchpad — edits are not saved` strip added inside `CodeView`
  (`SandboxTab.tsx`), the single function both call sites route through, so the Code toggle
  AND every markdown-Preview fence declare it. The doc stays writable on purpose: ⌘F Replace
  dispatches transactions, and `SandboxTab.test.tsx:375-410` asserts that contract. Resolves
  ISS-383, ISS-597, ISS-598. `PreviewPanel.tsx` unchanged — the defect is status-blind, so no
  status prop was threaded.
- **Found by:** bug-runs-id-workspace-r1
- **Fingerprint:** `/runs/[id]/workspace|workspace-file-viewer-code-mode|click-into-cm-content-and-type|editor-accepts-arbitrary-keystrokes-no-readonly-lock-no-save-affordance`
- **Evidence:** `bug-hunter/evidence/runs-id-workspace/BUG-20260828-013500-runs-id-workspace/`

### Summary
First established that the Workspace tab correctly bounds the already-filed Files-tab
deliverable bug (`BUG-20260828-012900-runs-id-files`): the run's real `presentation.pptx`
binary deliverable IS listed here (under "Deliverables · 2", alongside `presentation.html`),
opens a "binary file — use Download" message, and downloads correctly (confirmed via
`GET /api/runs/{id}/sandbox/file?path=presentation.pptx` => 200 and an actual browser download
event). The "All files" tree also matches the backend sandbox listing exactly — 36 files across
`ROOT`/`.agents`/`.browser`/`.verify`/`conversation_history`/`tmp`, matching
`GET /api/runs/{id}/sandbox`'s file count exactly. So the run's own deliverable IS reachable
somewhere in the UI (via Workspace), just not via Files.

While probing the file viewer itself, however, a separate defect surfaced. Selecting any text
file (`.json`, `.md` in its "Code" view — the raw-text mode toggled via the "Code"/"Preview"
button next to Download) renders the content inside a CodeMirror editor whose content root
(`.cm-content`) has `contentEditable === true` and a live text cursor. Clicking into it and
typing is accepted exactly like a real code editor: new characters are inserted at the cursor
position and the rendered text updates live. This reproduces on two independent files of two
different types — `.browser/deck-styles.json` (typing `BUGHUNTER_TEST_EDIT` inserted it
mid-line at the click position) and `PLANNER.md` in Code view (typing `MD_EDIT_TEST` inserted it
at the start of a line). Nothing on the page indicates the content is supposed to be read-only:
no lock icon, no "read-only" badge, no disabled/greyed styling, and critically no "unsaved
changes" indicator or Save/Discard control appears after typing — the UI gives no sign that
anything unusual just happened. The only two buttons present are "Code"/"Preview" (view-mode
toggle) and "Download". Switching to a different file and back re-fetches the original
(unmodified) content from the server — confirmed via `GET /api/runs/{id}/sandbox/file?path=...`
firing again on return — and no `PUT`/`POST`/`PATCH` request was ever observed after typing, so
the edit is not persisted server-side. But the client-side editing session itself has no
read-only guard, meaning a user who types into what is presented as an inert "file preview" for
a `Done` (immutable, completed) run gets no feedback that their keystrokes went anywhere, and
loses them the instant they navigate to a sibling file or leave the tab — a misleading,
silently-discarding "editor" masquerading as a passive viewer.

### Reproduction
1. Sign in as qa-admin, navigate to `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/workspace`
   (a completed "Ppt V2" run, header status "Done").
2. Click "All files" tab, expand `.browser`, click `deck-styles.json` to open it. Observe the
   Code-view pane renders with line numbers and syntax highlighting.
3. Run `document.querySelector('.cm-content').isContentEditable` in the console — confirmed
   `true`.
4. Click into the code pane at an arbitrary position and type `BUGHUNTER_TEST_EDIT`. Observe the
   text is inserted live into the rendered line (verified both via a DOM `textContent` check and
   a screenshot: `"borderRadiusPx": 0,BUGHUNTER_TEST_EDIT` appears on line 24). No read-only
   indicator, warning, or Save/Discard control appears anywhere before or after typing.
5. Click a different file (`PLANNER.md`), then click back to `deck-styles.json` — the injected
   text is gone; the file was silently re-fetched fresh from the server with no prompt about the
   discarded edit.
6. Repeated on a second, different file: open `PLANNER.md`, click its "Code" toggle button (next
   to Download) to switch from the default rendered-markdown Preview into raw Code view, click
   into `.cm-content` (confirmed `isContentEditable === true`), type `MD_EDIT_TEST ` — inserted
   live at the cursor position (confirmed via DOM text and screenshot).
7. Confirmed via `browser_network_requests` across both repro steps that only `GET
   /api/runs/{id}/sandbox/file?path=...` calls fired — no `PUT`/`POST`/`PATCH` request was ever
   made after typing, so the app never attempts to persist the edit; the defect is purely the
   unguarded client-side editable state and its silent-discard behavior.

### Expected
A file-preview pane for a completed, immutable run's workspace should render content read-only
(e.g. `contentEditable !== true`, or an explicit read-only CodeMirror configuration), or if
editing is an intentional feature, it should be clearly indicated (an "editing" label, a visible
Save/Discard affordance, and a warning before the edit is discarded by switching files).

### Actual
The Code-view file pane is a fully live, keystroke-accepting text editor with no read-only
enforcement, no visual indication that content is (or should be) immutable, and no warning that
typed edits are silently discarded the instant the user selects a different file — reproduced on
two different files and file types (`.json`, `.md`).

### Evidence
- Before (Deliverables list, `presentation.pptx` correctly present — establishes Workspace is
  NOT the materially-worse "nowhere in the UI" case): `bug-hunter/evidence/runs-id-workspace/BUG-20260828-013500-runs-id-workspace/01-before-deliverable-pptx-listed.png`
- Before (JSON file opened in Code view, unmodified): `bug-hunter/evidence/runs-id-workspace/BUG-20260828-013500-runs-id-workspace/02-before-json-code-view.png`
- Failure (typed text inserted into `deck-styles.json`, no read-only indication): `bug-hunter/evidence/runs-id-workspace/BUG-20260828-013500-runs-id-workspace/03-failure-json-accepts-typed-edit.png`
- Failure, second file/type (typed text inserted into `PLANNER.md` Code view): `bug-hunter/evidence/runs-id-workspace/BUG-20260828-013500-runs-id-workspace/04-failure-md-code-view-accepts-typed-edit.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs/{id}/sandbox/file?path=...` fires on every file selection (200 OK);
  no write-type request (`PUT`/`POST`/`PATCH`) was ever observed following a typed edit, in
  either repro.
- State/URL: URL stays on `/runs/{id}/workspace` throughout; `document.querySelector('.cm-content').isContentEditable`
  confirmed `true` on both files tested; re-selecting a previously-edited file re-fetches and
  shows the original, unmodified server content.

## BUG-20260828-013900-runs-id-audit — The Audit tab fabricates 96 "Governance/Gate" records from ordinary pipeline events; the backend's real gate-events endpoint reports zero for the same run

- **Page:** Completed run — Audit tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/audit
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28 by the verifier — `frontend/src/components/results/__tests__/AuditTab.test.tsx`
  run standalone via `npx vitest --run --no-coverage` from `frontend/`: the 3
  `it.fails` regression guards (ISS-202/ISS-212/ISS-211) XPASSed
  ("Error: Expect test to fail"), the `.fails` markers were then removed and a
  re-run confirmed plain green, 18/18 passed. Manual repro by hand in the
  browser (real Chrome, qa-admin, cold nav to
  `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/audit`) now shows "Governance 0
  / Security 4 / Activity 96" (was "Governance 96 / Security 4 / Activity 0"),
  and expanding two differently-labelled rows ("audit logger — before step" @
  01:50:11 PM vs. "audit logger — tool call" @ 01:56:11 PM) now shows distinct
  Agent/Tool/Summary detail per row instead of byte-identical boilerplate.
  `curl :8000/docs` → 200 (backend unchanged, frontend-only fix, no restart
  needed). `frontend && npm run build` compiles clean. `npx tsc --noEmit`
  shows no error in `AuditTab.tsx` (pre-existing errors in
  `HomeLaunchGrid.crossAccountLeak.test.tsx` and `listenerMiddleware.test.ts`
  are unrelated modified files, not touched by this fix). `lint-imports` from
  `backend/` reports the same pre-existing `kernel_services -> app.api`
  contract break as before this fix (frontend-only change, not caused by it).
  No new browser console errors on the Audit tab. Before/after screenshots:
  `bug-hunter/evidence/runs-id-audit/BUG-20260828-013900-runs-id-audit/01-before-audit-100-records.png`
  and `03-after-audit-governance-0-activity-96.png`.
- **Fix card:** [FIX-326](../.knowledge/cards/20260828-1656-FIX-326.md) — hook_runs rows now
  carry their own `"hook"` source category into `deriveFineCategory`, which falls back to
  `"activity"` (secret_scan still resolves to `"security"`, behavioral hooks to Governance);
  `buildHookDetailRows` also emits the payload's `agent_name`/`tool`/`summary` so two rows are
  no longer byte-identical, and `exportRows()` carries `fineCategory` into the CSV/JSON.
  ISS-202/211/212 all resolved by that one file, `frontend/src/components/results/AuditTab.tsx`
- **Root cause:** `AuditTab.tsx`'s hook_runs merge loop (`frontend/src/components/results/AuditTab.tsx:558-585`)
  hardcodes `category: "gate"` (line 574) and calls `deriveFineCategory("gate", hookName, step)`
  (line 568) for EVERY `hooksEnv.hook_runs` row, including the default `audit_logger` hook
  (backend `agents/capabilities/hooks/audit_logger.py`, injected on every step of every workflow
  per `_DEFAULT_AUDIT_HOOKS` in `backend/agents/workflows/compiler.py:830`) whose own docstring
  says it is non-blocking lifecycle logging, never a governance gate. `deriveFineCategory`
  (lines 281-295) only escalates to `"security"`/`"behavioral"` on a regex match against
  hook/step text and otherwise falls back to `source === "gate" ? "gate" : "validation"` — since
  hook_runs always passes `"gate"` as `source`, an `audit_logger` row can never land in the
  `"activity"` fine category that already exists in `FINE_CATEGORY_META` (lines 261-265) for
  exactly this kind of lifecycle event. `buildHookDetailRows` (lines 151-182) compounds this: it
  only special-cases `detail.detector`/`matched_keys`/`match`/`marker`/`action`/`reason`, never
  the `detail.summary` field the backend actually writes for `audit_logger`
  ("one-line narrative for the Audit tab UI" per its own docstring) — so every row falls to the
  same fallback `Action: allowed` / `Outcome: continue` text, which is why any two expanded rows
  are byte-identical regardless of label or timestamp. CONFIRMED by direct read of both files.
- **Blast radius:** `deriveFineCategory`/`buildHookDetailRows`/`buildHookLabel` are module-local
  to `AuditTab.tsx` (not exported) — their one call site is the hook_runs loop itself, mounted
  from exactly two places (`PreviewPanel.tsx:1341` — the reported `/runs/{id}/audit` surface —
  and `WorkflowHistory.tsx:901`, a run-history "quick view" of the same tab); both inherit the
  fix identically since they render the same component. The exported `rows` state also feeds
  `exportAuditCSV`/`exportAuditJSON` (`frontend/src/lib/exporters/auditExporter.ts:83-98`), a
  raw unfiltered pass-through, so the "exportable" CSV/JSON download carries the same fabricated
  rows (ISS-211, INFERRED — code-confirmed, no export file inspected). The fetch/merge effect
  (`AuditTab.tsx:451-597`) depends only on `workflowRunId`, never `isRunning` (used only for
  render-only badges at lines 723/812/849), so the same fabrication is state-independent and
  should reproduce identically on an in-progress run (ISS-212, INFERRED — not yet reproduced
  live). `RunChatLane.tsx`'s `deriveSecurityBullets` (line 451) was checked and is NOT affected —
  it filters `hookRuns` to `outcome === "block" && /secret|scan/i.test(hook)`, which excludes
  `audit_logger` correctly.
- **Fix belongs in:** `AuditTab.tsx`'s hook_runs loop (~line 558-585) — branch the `source`
  passed into `deriveFineCategory` (and the `category` field) on the hook name/event, so
  `audit_logger` telemetry routes to `"activity"` instead of being hardcoded to `"gate"`; and
  extend `buildHookDetailRows` to surface `detail.summary` when the detector/match/action/reason
  fields are absent. One shared fix here covers both AuditTab mount points and the CSV/JSON
  export automatically — no other caller needs its own patch.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic on every cold load of this run, no
  axis variation needed. Root cause: `AuditTab.tsx` (loop over `hooksEnv.hook_runs`, lines
  558-585) hardcodes `category: "gate"` for every hook_runs row regardless of `hook` name,
  including "audit logger" step/tool-call/tool-result telemetry markers that are not governance
  gates; `buildHookDetailRows` then falls back to identical boilerplate detail for any row whose
  `detail` object lacks detector/matched/action/reason fields.
- **Issue card:** [ISS-202](../.knowledge/cards/20260828-1409-ISS-202.md)
- **Issue cards:** [ISS-202](../.knowledge/cards/20260828-1409-ISS-202.md) (root),
  [ISS-211](../.knowledge/cards/20260828-1429-ISS-211.md) (sibling: CSV/JSON export inherits the
  fabricated rows), [ISS-212](../.knowledge/cards/20260828-1428-ISS-212.md) (sibling: same
  fabrication on an in-progress/live run, state-independent)
- **Found at:** 2026-08-28 01:39 UTC
- **Found by:** bug-runs-id-audit-r1
- **Fingerprint:** `/runs/{id}/audit|governance-gate-rows|expand-any-gate-labelled-entry|identical-fabricated-boilerplate-not-derived-from-real-gate-events`
- **Evidence:** `bug-hunter/evidence/runs-id-audit/BUG-20260828-013900-runs-id-audit/`

### Summary
The Audit tab's header copy promises "Full governance, security & activity log — every gate,
scan, validation and exec, attributed and exportable" and "Immutable, owner- and
workspace-attributed log · every entry carries severity + timestamp." For this completed run it
renders "100 records," split into "Governance 96" and "Security 4" (Activity 0). But the run's own
ground-truth event stream (`GET /api/runs/{id}/events?after=0`) contains exactly ONE real
`gate_status` event for the whole run, and the dedicated backend endpoint for this exact purpose,
`GET /api/runs/{id}/gate-events`, returns `{"gate_events":[]}` — an empty array — for this run. The
96 rows the UI labels "GATE"/"Governance"/"Passed" do not come from either of those sources; they
are synthesized client-side from ordinary `tool_call` (44 in the raw stream) and `tool_result` (44)
events plus "before step"/"after step" markers, none of which are gate events per the backend's own
data. Confirming the fabrication further: expanding ANY of these 96 rows — regardless of whether
its title says "before step," "after step," "tool call," or "tool result," and regardless of
timestamp — reveals byte-for-byte identical detail text: the same "WHAT IS THIS?" boilerplate
("A governance gate — a checkpoint where the run paused for a policy decision or a human approval
before it was allowed to continue."), the same `Action: allowed`, the same `Outcome: continue`, with
no tool name, no step name, no agent attribution, no arguments, and no actual result — despite the
page's own claim that entries are "attributed." A real governance/compliance log that invents gate
checkpoints which never occurred, and cannot distinguish one event from another once expanded, is
actively misleading rather than merely incomplete.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/audit`.
2. Observe the Audit trail header: "100 records," pill counts "Governance 96," "Security 4,"
   "Activity 0," and the compliance-oriented copy claiming an "attributed and exportable" log of
   "every gate, scan, validation and exec."
3. In a separate request (same session token), call `GET /api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/gate-events`.
   Observe the response body is `{"workflow_id":"b9feac1c-ec21-4531-8ba7-bb391786993e","gate_events":[]}`
   — zero real gate events for this run, despite the UI showing 96.
4. Call `GET /api/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/events?after=0` and count event types:
   only 1 `gate_status` event exists in the entire 9737-event raw stream; the 96 UI rows instead
   correspond in count to `tool_call` (44) + `tool_result` (44) + assorted before/after-step markers
   (8) = 96.
5. Back in the UI, expand the first row ("audit logger — before step," 01:50:11 PM). Note its detail
   panel: "Action: allowed / Outcome: continue" plus the generic governance-gate description.
6. Expand a row with a completely different label and a timestamp ~17 minutes later ("audit logger —
   tool call," 01:56:11 PM, or "audit logger — after step," 02:07:39 PM). Read the detail panel text
   via `element.parentElement.innerText` — byte-identical to step 5's text in every field.
7. Repeat on a fourth, different-labelled row ("audit logger — tool result") — same identical
   boilerplate again. No row in the Governance category shows anything event-specific once expanded.

### Expected
The Audit tab's "Governance"/"Gate" entries should reflect real governance-gate checkpoints from
the backend (matching `/gate-events` and the `gate_status` events in the raw stream), not be
synthesized from unrelated tool-call/tool-result telemetry. Each entry, once expanded, should show
detail specific to that event (e.g. which tool was called, what step ran, which agent was involved)
rather than one static, category-wide placeholder — especially given the log's own text promises
attribution and per-entry detail for compliance review.

### Actual
96 of the 100 displayed "audit trail" records are fabricated Governance/Gate rows with no backing
real gate event (the actual gate-events count for this run is 0, not 96), and every one of them
expands to identical, non-specific boilerplate text regardless of the underlying event's type,
label, or timestamp — the log cannot actually distinguish or attribute any of its own entries.

### Evidence
- Before (Audit tab loaded, "100 records," "Governance 96"): `bug-hunter/evidence/runs-id-audit/BUG-20260828-013900-runs-id-audit/01-before-audit-100-records.png`
- Failure (four differently-labelled, differently-timed rows expanded side by side, all identical detail text): `bug-hunter/evidence/runs-id-audit/BUG-20260828-013900-runs-id-audit/02-four-different-events-identical-payload.png`
- Network evidence (gate-events empty vs. raw event-type counts): `bug-hunter/evidence/runs-id-audit/BUG-20260828-013900-runs-id-audit/network.log`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs/{id}/gate-events` returns `200 OK` with an empty `gate_events` array;
  `GET /api/runs/{id}/events?after=0` returns `200 OK` with 9737 events, only 1 of type `gate_status`,
  confirming the UI's 96 "Governance" rows have no corresponding real gate data.
- State/URL: URL stays on `/runs/{id}/audit` throughout; the discrepancy is reproducible on every
  reload of the same completed run (deterministic, not a race).

## BUG-20260828-014416-runs-id-preview-full — For a failed run with no Preview tab, `/preview/full` silently renders the Audit trail instead of an honest "no deliverable" state

- **Page:** Full-bleed deliverable view
- **Route:** /runs/{id}/preview/full
- **Severity:** Medium
- **Status:** CLOSED
- **Fix card:** [FIX-358](../.knowledge/cards/20260829-0011-FIX-358.md)
- **Verified:** 2026-08-29 — `suites/07_run_detail/test_iss285_preview_full_no_deliverable_fallback.py`
  ran XPASS(strict) (observed: "[XPASS(strict)] ISS-285 unfixed", FAILED as expected under
  xfail=the pass signal); `xfail` marker removed, `issue("ISS-285")` kept, re-run PASSED plain
  green (4.8s). Manual re-run of the original repro from this ledger entry against run
  `826d09f0-21b0-4b8f-a79f-843fc5c82adb` in real Chrome (lane4): cold nav to the plain
  `/runs/{id}` route showed no tab selected and the honest "This run did not complete
  successfully / No deliverable was produced" copy (unchanged baseline); cold nav to
  `/runs/{id}/preview/full`, twice, showed the identical honest copy with Audit NOT selected —
  the silent Audit substitution is gone, deterministic across two fresh navigations. No new
  console errors/warnings on either page. `tsc --noEmit` clean on both touched files (pre-existing
  errors in `HomeLaunchGrid.crossAccountLeak.test.tsx` and `listenerMiddleware.test.ts` are
  unrelated to this diff). Regression: `vitest run PreviewPanel.degraded.test.tsx` 11/11 passed,
  `PreviewPanel.test.tsx` 19/19 passed, `runTabShallowNav.test.ts` 3/3 passed. `backend/`
  `lint-imports` shows a pre-existing broken contract (`agents.execution_engine.engine` ->
  `app.api.*`) unrelated to this frontend-only fix — not caused by FIX-358, not re-verified at
  a pre-change commit. After-screenshot:
  `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-014416-runs-id-preview-full/04-after-fix-preview-full-honest-no-deliverable.png`.
- **Fixed:** 2026-08-29 — `reopenTabFor` (`frontend/src/app/[...view]/page.tsx`) gains a
  `run-preview-full` case returning `"preview"`, so both call sites finally mint a deep-link
  nonce for the one route whose purpose is forcing Preview open; and PreviewPanel's Preview pane
  (`frontend/src/components/preview/PreviewPanel.tsx`) is gated on `showFailureAffordance ||
  showDivertedAffordance` instead of `showCancelledAffordance || showDivertedAffordance`, so that
  forced Preview renders the honest "No deliverable was produced" state rather than the generic
  per-state default silently substituting the Audit trail. The plain `/runs/{id}` screen is
  unchanged (Phase 42-03 §D still drops Preview and defaults to Audit with no deep link).
- **Fix verified by:** `tests/integration/e2e/suites/07_run_detail/`
  `test_iss285_preview_full_no_deliverable_fallback.py` → XPASS(strict) (the pass signal; xfail
  marker left in place for 6-verifier). Frontend regression: PreviewPanel.degraded.test.tsx 11
  passed, PreviewPanel.test.tsx 19 passed, runTabShallowNav.test.ts 3 passed, tsc clean on both
  touched files. Siblings ISS-388/ISS-389 are cured on the code path by the same change but were
  not re-driven in a browser — both remain open.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic across cold entry paths; register run
  id transitioned to `cancelled` in shared seed data, substituted run 826d09f0-21b0-4b8f-a79f-843fc5c82adb
  (status `failed`) reproduces the identical mechanism
- **Root cause:** `reopenTabFor` (`frontend/src/app/[...view]/page.tsx:228-244`) has no case for
  the `"run-preview-full"` screen — its switch covers only `run-steps`/`run-steps-agent`/
  `run-files`/`run-workspace`/`run-audit` and falls through to `undefined` for everything else,
  so neither call site (`page.tsx:3191` warm path, `:3264` cold path, both gated on
  `if (tab) requestOpenTab(tab)`) ever tells PreviewPanel that this route's whole purpose is
  forcing Preview open. PreviewPanel's own state-keyed default-tab effect
  (`PreviewPanel.tsx:812,830-831`) then unconditionally maps a terminal-failed-no-deliverable run
  (`terminalFailureNoDeliverable`, `:716`) to `"audit"` with no check of which route asked and no
  rendered affordance explaining the substitution. CONFIRMED via direct read of both files.
- **Blast radius:** `PreviewPanel` has exactly one JSX mount site (`DashboardLayout.tsx:3107`), so
  every "execution" screen funnels through the same effect — `run-detail`, `run-steps*`,
  `run-files`, `run-workspace`, `run-audit`, `run-stream`, `run-version`, `run-preview-full`. The
  fix belongs in PreviewPanel's default-tab effect / tab-content switch (or in `reopenTabFor` plus
  a `visibleTabs` check there), not duplicated per-route in `page.tsx`. The plain `/runs/{id}`
  route's differing observed behavior (no tab selected + neutral placeholder, vs. `/preview/full`'s
  Audit) could not be explained by any route-specific code found in either file — both take the
  identical `tab = undefined` cold-mount path — and remains INFERRED as a possible capture-timing
  artifact rather than a second mechanism (see ISS-285's Analyzer confirmation section).
- **Issue cards:** [ISS-285](../.knowledge/cards/20260828-1745-ISS-285.md) (root, CONFIRMED),
  [ISS-388](../.knowledge/cards/20260828-2234-ISS-388.md) (sibling, INFERRED: same gap on a
  still-building run lands on Steps instead of Preview),
  [ISS-389](../.knowledge/cards/20260828-2234-ISS-389.md) (sibling, INFERRED: same gap on a
  zero-audit-record failed run compounds into a content-free, unexplained Audit pane)
- **Found at:** 2026-08-28 01:44 UTC
- **Found by:** bug-runs-id-preview-full-r1
- **Fingerprint:** `/runs/{id}/preview/full|preview-tab-fallback|navigate-to-preview-full-for-failed-run-with-no-preview-tab|silently-renders-audit-tab-instead-of-empty-state`
- **Evidence:** `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-014416-runs-id-preview-full/`

### Summary
`/runs/{id}/preview/full` is the dedicated route whose entire purpose is to force-select and
show the run's Preview tab (the deliverable view). For a run whose pipeline failed before
producing any deliverable, no Preview tab exists at all — confirmed the run detail page's
tablist for this run is exactly `Steps | Files | Workspace | Audit`, no `Preview` entry. Two
different code paths handle "the tab this route wants doesn't exist" completely differently:
plain `/runs/{id}` (no query/sub-path) shows **no tab selected** and a neutral placeholder,
"Output will appear here" — an honest, uncommitted default. But `/runs/{id}/preview/full`
instead silently auto-selects the **Audit** tab and renders its full content (32 records, a
governance/security log unrelated to a "preview") with no banner, message, or visual cue
explaining that the requested Preview view isn't available and something else is being shown
instead. This is a different mechanism from the already-known D-13 (blank pane when an
incompatible renderer is force-selected on an existing Preview tab) and from the cancelled-run
case on this same route (which correctly shows an honest "This run was cancelled ... stopped
before producing a deliverable" empty state on the still-present Preview tab) — here there is no
Preview tab to show an empty state on, and the route quietly substitutes an entirely unrelated
tab's content instead of degrading honestly the way the cancelled-run case does one state over.

### Reproduction
1. Sign in as qa-admin. Navigate to `http://localhost:3000/runs/d6e425b6-df0d-4f54-9bba-f4a771e33812`
   (a failed PPT run, seeded fixture per the worker brief). Observe the tablist reads
   `Steps | Files | Workspace | Audit` (no Preview tab exists for this run), no tab shows
   `[selected]`, and the content area shows the neutral placeholder text "Output will appear
   here".
2. Navigate to `http://localhost:3000/runs/d6e425b6-df0d-4f54-9bba-f4a771e33812/preview/full`
   (same run, the dedicated full-preview route). Observe: the tablist is identical
   (`Steps | Files | Workspace | Audit`), but this time **Audit is `[selected]`** and the pane
   below renders a full Audit trail — "32 records", a governance/security/activity summary,
   Gate 32, and a scrollable list of 32 "audit logger" entries — with no text anywhere on the
   page indicating this is a fallback, or that a Preview was requested but is unavailable.
3. Reloaded (`page.goto`) the same `/preview/full` URL a second time — identical result: Audit
   tab selected, same 32-record trail rendered, deterministic across reloads.
4. For contrast, the cancelled run (`a8dfa959-e233-4ddf-87ce-d9a942cefde3`) on this exact same
   `/preview/full` route DOES keep the Preview tab selected and shows an honest inline message
   ("This run was cancelled / The run was stopped before producing a deliverable / Open the
   Thinking tab to view details") — confirming the route is capable of degrading honestly when a
   Preview tab exists; the failed-run case fails specifically because no Preview tab exists at
   all and the fallback logic picks Audit instead of mirroring the plain route's neutral,
   nothing-selected placeholder.

### Expected
When the requested Preview view has no tab to render (no deliverable was ever produced),
`/preview/full` should degrade the same way the plain `/runs/{id}` route already does — no tab
selected, neutral "nothing to show" placeholder — or explicitly explain why a different tab is
shown instead. It should not silently substitute a materially different tab's real content
(Audit) with no explanation.

### Actual
`/preview/full` auto-selects and fully renders the Audit tab for a failed run, with no visual or
textual indication that this happened, while the equivalent plain route for the identical run
correctly shows no tab selected and a neutral empty placeholder.

### Evidence
- Before (plain `/runs/{id}` route, no tab selected, neutral placeholder): `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-014416-runs-id-preview-full/01-before-plain-route-no-tab-selected.png`
- Failure (`/preview/full`, Audit tab silently selected with full trail content): `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-014416-runs-id-preview-full/02-failure-preview-full-shows-audit.png`
- Reproduced on a second fresh navigation: `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-014416-runs-id-preview-full/03-repro2-preview-full-shows-audit.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no failed request; both routes fetch the same run data successfully, the divergence
  is purely in client-side tab-selection/fallback logic.
- State/URL: `location.href` correctly stays on `/runs/{id}/preview/full` throughout; the tablist
  DOM confirmed via accessibility snapshot (`tab "Audit" [selected]`) on both reproduction
  attempts, versus no `[selected]` tab and a distinct placeholder string on the plain route for
  the identical run id.

## BUG-20260828-014937-runs-id-stream — Diverted run's Preview tab shows the "waiting for live output" placeholder even though the run is permanently terminal

- **Page:** Stream view (run detail, Preview tab)
- **Route:** /runs/{id}/stream
- **Severity:** Medium
- **Status:** CLOSED
- **Fix card:** [FIX-357](../.knowledge/cards/20260828-2210-FIX-357.md)
- **Verified:** 2026-08-29 — `suites/07_run_detail/test_iss390_diverted_stream_placeholder.py` ran
  XPASS(strict) with the xfail marker still in place ("[XPASS(strict)] ISS-390 unfixed"), marker
  then removed and the file re-run: plain green (5.0s). Regression guards
  `WorkflowHistory.iss391.test.tsx` + `RunDetailPage.iss395.test.tsx` (2/2 green via
  `npx vitest run --no-coverage`) and `PreviewPanel.degraded.test.tsx` +
  `RunDetailPage.test.tsx` (17/17 green). Manual repro by hand in Chrome (lane5) against
  `/runs/940ca699-b21b-4666-8e44-3370a08a4561/stream`, qa-admin, cold nav then a second cold
  reload: Preview tab stays `[selected]`, "Output will appear here" is gone, header now reads
  "This run did not complete successfully" / "The run was diverted to another workflow and will
  not resume. No deliverable was produced here." No console errors on the page.
  `npx tsc --noEmit` clean for the four edited files (page.tsx, PreviewPanel.tsx,
  WorkflowHistory.tsx, RunDetailPage.tsx); the 2 tsc errors elsewhere in the tree
  (HomeLaunchGrid.crossAccountLeak.test.tsx, listenerMiddleware.test.ts) and the backend
  `lint-imports` broken contract (kernel -> app.api) are pre-existing/unrelated to this
  frontend-only change. `validate_links.py`: 4 pre-existing broken links, none on
  ISS-390/391/395/FIX-357.
- **Fixed:** 2026-08-29 — both gates closed together. `frontend/src/app/[...view]/page.tsx`'s
  `setReopenedRunStatus` ternary now passes `"diverted"` through (it previously narrowed to
  failed/cancelled/degraded, so the prop was always `undefined` downstream), and
  `frontend/src/components/preview/PreviewPanel.tsx` gains `isDivertedTerminal` /
  `showDivertedAffordance` as their OWN branch beside `isCancelledTerminal` — deliberately NOT
  folded into `reopenFailureSignal`, which would have marked the header failed and dropped the
  Preview tab. `DegradedRunAffordance` takes a new `diverted` prop that swaps only the detail
  line ("The run was diverted to another workflow and will not resume."). The two inferred
  siblings are closed in the same diff: `WorkflowHistory.tsx:593-597` (ISS-391) and
  `RunDetailPage.tsx:230-234` (ISS-395) both take `"diverted"` into their triads.
  Tests: `suites/07_run_detail/test_iss390_diverted_stream_placeholder.py` → XPASS(strict)
  (the fix signal; marker left for 6-verifier); `WorkflowHistory.iss391.test.tsx` and
  `RunDetailPage.iss395.test.tsx` → green, and confirmed red first with only the two
  `"diverted"` predicates reverted; `PreviewPanel.degraded.test.tsx` + `RunDetailPage.test.tsx`
  → 19/19 green as regression guards.
- **Validated:** 3/3 on 2026-08-28, cold start every cycle (cycle 1: direct cold nav; cycle 2:
  nav-away then cold nav back; cycle 3: hard reload) — deterministic, no axis variation needed
- **Issue card:** [ISS-390](../.knowledge/cards/20260828-2048-ISS-390.md) (root, supersedes
  [ISS-282](../.knowledge/cards/20260828-1710-ISS-282.md)); siblings:
  [ISS-391](../.knowledge/cards/20260828-2049-ISS-391.md),
  [ISS-395](../.knowledge/cards/20260828-2050-ISS-395.md)
- **Root cause:** TWO gates in series, both required for a fix — `reopenedRunStatus` is
  narrowed to `"failed"/"cancelled"/"degraded"` (never `"diverted"`) at
  `frontend/src/app/[...view]/page.tsx:3035-3041` before it ever reaches
  `PreviewPanel.tsx`, and `PreviewPanel.tsx:696-699`'s own `reopenFailureSignal` check
  independently omits `"diverted"` from the same triad. ISS-282 (filed by validation)
  named only the second gate and its own recommended fix would not close the bug alone
  — corrected/superseded by ISS-390.
- **Blast radius:** the identical hand-copied `failed || cancelled || degraded` triad
  (with no shared helper) recurs in two more reopen-surface call sites beyond
  PreviewPanel.tsx: `WorkflowHistory.tsx:593-596` (History library's right-column
  deliverable pane shows generic "No preview available" for a diverted selection
  instead of being suppressed/explained — ISS-391) and `RunDetailPage.tsx:230-234`
  (History library's Agents tab lists a diverted run's partial agents with no
  diverted-aware banner, as if it completed normally — ISS-395). Both are INFERRED,
  not yet independently browser-reproduced. Ruled out: `useWorkflow.ts`'s
  `TERMINAL_MARKER_BY_STATUS`, `RevisionFamilyView.tsx`'s `statusDotClass`, and the
  backend's `TERMINAL_RUN_STATUSES` all already handle `"diverted"` correctly.
- **Found at:** 2026-08-28 01:49 UTC
- **Found by:** bug-runs-id-stream-r1
- **Fingerprint:** `/runs/{id}/stream|preview-tab-empty-state|load-stream-for-a-diverted-run|shows-generic-live-waiting-placeholder-instead-of-honest-terminal-message`
- **Evidence:** `bug-hunter/evidence/runs-id-stream/BUG-20260828-014937-runs-id-stream/`

### Summary
Loading `/stream` for a run whose status is `diverted` (the API confirms `status: "diverted"`
with `completed_at` already set — a permanently terminal state, not paused-and-resumable; only
2 of the run's 3 agents ever executed and `output`/`deliverable_filename` are both `null`)
auto-selects the Preview tab and renders the plain text "Output will appear here". That is the
exact same neutral placeholder a genuinely in-progress/live run shows while streaming output has
not arrived yet — it implies output is still forthcoming. For this run, nothing further will
ever arrive: the pipeline stopped for good at the divert point with no deliverable and no path
to auto-resume. Contrast with the sibling terminal state on the identical route: the cancelled
run (`a8dfa959-e233-4ddf-87ce-d9a942cefde3`) instead shows an explicit, run-status-aware message
("This run was cancelled / The run was stopped before producing a deliverable...") rather than
the generic live placeholder — proving the app is capable of degrading honestly for a terminal
state without a deliverable, and simply fails to do so for `diverted`. This is a different
mechanism from the already-filed `BUG-20260828-014416-runs-id-preview-full` (which is about
`/preview/full` silently substituting the Audit tab's content for a run with *no Preview tab at
all*); here the Preview tab genuinely exists, is correctly selected, and the bug is purely that
its empty-state copy is state-unaware and misleadingly implies the run is still live.

### Reproduction
1. Sign in as qa-admin. Navigate to
   `http://localhost:3000/runs/940ca699-b21b-4666-8e44-3370a08a4561/stream` (seeded diverted
   run "Ex A4 Human Divert", per the worker brief's resolved instances).
2. Observe the header badge reads "Diverted", "2/3 agents", and the transcript ends with "Run
   started" / "Review approved — build continues" with no further activity and no chat composer
   (consistent with D-19, not re-filed here).
3. Observe the Preview tab is `[selected]` in the tablist and the content pane shows only the
   plain-text placeholder "Output will appear here" — identical wording/markup to what an
   actively-streaming, in-progress run shows while awaiting its first output chunk.
4. Confirmed via `GET /api/runs/940ca699-b21b-4666-8e44-3370a08a4561`: `"status": "diverted"`,
   `"completed_at": "2026-08-24T13:27:57.322032+00:00"` (already set — terminal), `"output":
   null`, `"deliverable_filename": null`. Waited 30s on the page and re-checked
   `browser_network_requests`: no repeated polling of `/events` occurred, ruling out an active
   "still connecting" state client-side — the UI has already given up polling, yet still shows
   the "waiting" copy.
5. Reloaded the page (fresh `page.goto`) and repeated steps 2-4 — identical result both times.
6. For contrast, loaded `/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3/stream` (cancelled run):
   Preview tab is also `[selected]`, but the pane instead shows a status-specific message,
   "This run was cancelled — The run was stopped before producing a deliverable. Open the
   Thinking tab to view details." (the "Thinking tab" phrasing is the already-known D-08, not
   re-filed).

### Expected
A run in a permanently terminal state with no deliverable should show a state-aware empty
message on its Preview tab (as the cancelled run does), not the same "Output will appear here"
copy used for an actively streaming run whose output has simply not arrived yet.

### Actual
The diverted run's Preview tab renders the generic live-streaming placeholder text, giving no
indication that the run is over and no output is ever coming.

### Evidence
- Cancelled run's honest, status-specific empty state (for contrast):
  `bug-hunter/evidence/runs-id-stream/BUG-20260828-014937-runs-id-stream/01-cancelled-run-honest-empty-state.png`
- Diverted run showing the misleading generic "Output will appear here" placeholder:
  `bug-hunter/evidence/runs-id-stream/BUG-20260828-014937-runs-id-stream/02-diverted-run-live-placeholder.png`

### Browser Signals
- Console: none observed.
- Network: no SSE/WebSocket connection is opened for any tested run (completed, failed,
  cancelled, diverted) — all use polling `GET /api/runs/{id}/events?after=N`, and none of the
  four statuses showed a reconnect loop; polling correctly stops once settled.
- State/URL: `GET /api/runs/940ca699-b21b-4666-8e44-3370a08a4561` confirms `status: "diverted"`,
  `completed_at` set, `output: null`, `deliverable_filename: null`.

## BUG-20260828-015500-runs-failed — "Edit brief & run again" on a failed run opens a brand-new, completely blank composer instead of pre-filling the original brief

- **Page:** Failed run detail
- **Route:** /runs/{id} (failed run) → navigates to /create/ppt_v2
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28 — `tests/integration/e2e/suites/18_chat_lane/test_iss_218_edit_brief_prefill.py`
  both tests XPASS(strict) confirmed, then `xfail` markers removed and re-run plain green (2 passed).
  Manual re-repro in real Chrome (lane5, qa-admin) on failed run `72e2f445-2149-4623-b39b-f85d42f24f6a`:
  clicked `data-testid="chat-relaunch-secondary"` ("Edit brief & run again"), landed on
  `/create/ppt_v2`, textarea now reads "Create a pitch deck to propose a bespoke facebook for a
  client" (the run's own brief) instead of `""`. No new console errors (1 pre-existing iframe
  sandbox warning only). Frontend `npm run build` succeeded; `tsc --noEmit` shows the same 6
  pre-existing errors in unrelated test files, none in `DashboardLayout.tsx`.
  `DashboardLayout.catalogHome.test.tsx` + `DashboardLayout.fix194.test.tsx`: 13/13 green.
  `lint-imports` (run from `backend/`) shows 1 pre-existing broken contract unrelated to this
  frontend-only change (zero backend files touched).
- **Root cause:** `handleEditBrief` (`frontend/src/components/layout/DashboardLayout.tsx:2151-2157`)
  does `router.push(createRouteForType(effectiveReviseType))` with zero brief handoff. Its own
  preceding comment (`:2144-2145`) claims it "Pre-fills the brief from submittedBrief when
  available" but the callback body never references `submittedBrief` (or anything else) — CONFIRMED
  by reading the function verbatim, comment vs. body mismatch. `IdeaInputPage`'s `initialInput` prop,
  the composer's only textarea-seeding mechanism (`DashboardLayout.tsx:2860`,
  `initialInput={savedComposition?.brief ?? pendingHomeBrief}`), is fed by neither
  `savedComposition` (null on this path) nor `pendingHomeBrief` (never touched by `handleEditBrief`)
  — hence the blank textarea. `pendingHomeBrief` is the app's own working pattern for exactly this
  job (Home brief textbox → Input view, `setPendingHomeBrief` in `handleHomeSelectFeature`,
  `DashboardLayout.tsx:1465-1468`); `handleEditBrief` simply never calls it.
- **Blast radius:** `handleEditBrief` has exactly ONE reachable call site app-wide — RunChatLane's
  `data-testid="chat-relaunch-secondary"` button, rendered only in the FAILED terminal branch
  (`RunChatLane.tsx:1825-1832`). Cancelled/degraded/diverted terminal branches render via the shared
  `relaunch(label)` helper (`RunChatLane.tsx:1694-1704`), which wires only `onRelaunch`, never
  `onEditBrief` — confirmed by grepping `handleEditBrief`/`onEditBrief`/`createRouteForType`/
  `pendingHomeBrief` across `frontend/src`; no second caller shares the flaw. The underlying gap is
  broader than this one caller, though: `pendingHomeBrief` is cleared in exactly one place
  (`handleLaunchSaved`, `:1478`) and NOT by `handleRunPipeline`, `handleBackNav`, `handleGoHome`, or
  `handleEditBrief` itself — that's the mechanism ISS-235 (sibling, INFERRED) traces: a leftover
  Home-page draft can bleed into this same button instead of showing blank.
- **Fix belongs in:** `handleEditBrief` itself (`DashboardLayout.tsx:2151-2157`) — add
  `setPendingHomeBrief(viewedRun?.input || submittedBrief)` before the `router.push`, reusing the
  exact state slot `handleHomeSelectFeature` already proves for this job (same source
  `runHeaderTitleFull` already uses at `:2398`). Smallest diff, and setting it unconditionally also
  forecloses ISS-235's stale-bleed case in the same change. A query-param/URL approach would need
  `routes.ts` changes (ADR-0018: routes.ts owns every URL) and still would not itself clear
  `pendingHomeBrief`.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — unconditional, no cold-start axis needed
- **Issue card:** [ISS-218](../.knowledge/cards/20260828-1700-ISS-218.md)
- **Issue cards:** [ISS-218](../.knowledge/cards/20260828-1700-ISS-218.md) (root),
  [ISS-235](../.knowledge/cards/20260828-1830-ISS-235.md) (sibling: stale `pendingHomeBrief` from an
  un-launched Home-page draft can bleed into this same button, showing the WRONG brief instead of
  blank)
- **Fix card:** [FIX-331](../.knowledge/cards/20260828-2056-FIX-331.md) — `handleEditBrief`
  now stages the viewed run's own brief into BOTH prefill slots the push can land in:
  the wizard's one-shot `ppt.draft`/`prototype.draft` (the reported `ppt_v2` path renders
  `LaunchWizard`, NOT `IdeaInputPage` — a correction to the issue cards) and
  `pendingHomeBrief` for every non-wizard type.
- **Found at:** 2026-08-28 01:55 UTC
- **Found by:** bug-runs-failed-r1
- **Fingerprint:** `/runs/{id}|resume-options-edit-brief-and-run-again|click-edit-brief-run-again-on-failed-run|navigates-to-blank-composer-original-brief-discarded`
- **Evidence:** `bug-hunter/evidence/runs-failed/BUG-20260828-015500-runs-failed/`

### Summary
A FAILED run's "Resume options" panel offers two actions: "Reopen & fix from the failed step"
and "Edit brief & run again". The label of the second button strongly implies the user's original
brief will be carried over so they can edit and resubmit it — that is the whole point of the
action given the run already failed with a specific, non-trivial brief on file ("A pitch deck for
a bespoke social network platform — a custom-built Facebook-like platform tailored to a specific
client's needs...", 4 sentences long, confirmed via `GET /api/runs/{id}`). Clicking the button
instead performs a plain client-side navigation to `/create/ppt_v2` — a brand-new, completely
empty composer: the brief `<textarea>` is empty (`""`), no template is pre-selected, and the URL
carries no reference to the source run (no `?from=`, `?runId=`, or similar). No network request is
made to fetch or seed the original brief; the button is a bare route change with zero payload
carried across. The user's only path to actually "edit" the brief is to retype the entire thing
from memory or copy it manually from the run detail page before clicking.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/d6e425b6-df0d-4f54-9bba-f4a771e33812`
   (seeded failed `ppt_v2` run). Confirm the run's brief is visible and non-trivial: "A pitch deck
   for a bespoke social network platform — a custom-built Facebook-like platform tailored to a
   specific client's needs..." (also readable via `GET /api/runs/{id}`).
2. In the "Resume options" panel, click "Edit brief & run again".
3. Observe: URL becomes `http://localhost:3000/create/ppt_v2` (no query parameters), page title
   "Configure your presentation", and `document.querySelector('textarea').value` is the empty
   string `""`. No template is checked/selected. The template gallery, "Review gates", and every
   other field are in their default first-visit state.
4. Inspect the network log for the click — no request to any brief-fetch or prefill endpoint fires;
   this is a pure client-side route change with no data transfer.
5. Navigated back to the same failed run and repeated steps 2-4 a second time — identical result:
   a fresh, empty composer with no trace of the original brief or run.

### Expected
Clicking "Edit brief & run again" should open the composer with the failed run's original brief
text pre-filled in the textarea (and, ideally, the same template/config selected), so the user can
make a targeted edit and resubmit — matching what the button's own label promises.

### Actual
The button discards the original brief entirely and opens a blank `/create/ppt_v2` composer
identical to a fresh "New presentation" flow, with no reference to the source run and no way to
recover the original text except manually copying it beforehand.

### Evidence
- Before (failed run detail, brief visible): `bug-hunter/evidence/runs-failed/BUG-20260828-015500-runs-failed/01-before-failed-run-with-brief.png`
- Failure (blank composer after clicking "Edit brief & run again"): `bug-hunter/evidence/runs-failed/BUG-20260828-015500-runs-failed/02-after-edit-brief-blank-composer.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no request fetches or carries the original brief; the click produces only a client-side
  route change to `/create/ppt_v2` with no query string and no payload.
- State/URL: `location.href` becomes exactly `http://localhost:3000/create/ppt_v2` (no `?from=`/
  `?runId=` reference to the source run); `textarea.value` confirmed empty via direct DOM read on
  two independent reproductions.

### Investigation note (duplication question, resolved — not filed as a separate bug)
Per the round's direct handover: pulled the raw `GET /api/runs/{id}/events` for this run and
compared against the rendered chat transcript. The "quadrupled 'What went wrong'" and "doubled
clarification transcript" are **genuine backend data, not UI rendering duplication** — the raw
event stream contains 4 distinct `pipeline_failed` events (each with a unique `event_id`) tied to
3 `run_resuming` events, i.e. the run was retried 4 total times and failed identically
("The model rejected this request.") on every single agent, every single attempt. The 2 identical
clarification rounds (seq 6/8 and seq 10/12) are likewise 4 distinct `chat_reply` events with
unique `event_id`/`nonce` values, matching the D-21 shape exactly (same root cause, same run
family behavior) — not re-filed. The UI renders exactly what the backend emits, 1:1, with no
client-side replication. This is consistent with, and does not newly explain, D-21.

## BUG-20260828-015930-runs-cancelled — "Run Again" on a cancelled run leaves the live /stream view permanently stuck at "Running · 0/4 agents · Starting…" after the backend has already failed the pipeline

- **Page:** Cancelled run detail (stream view)
- **Route:** /runs/{id} → /runs/{id}/stream
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28. `frontend/src/providers/RunConnectionProvider.test.tsx` — all 3
  ISS-220/236/237 `it.fails` cases XPASS'd ("Error: Expect test to fail"), `xfail`-equivalent
  markers removed (`it.fails` → `it`), re-run clean: 9/9 green. Regression guard
  `frontend/src/app/[...view]/liveRunSwitch.fix201.test.ts` 26/26 green. `npx tsc --noEmit`:
  same 6 pre-existing errors as the fixer reported, all in unrelated test files
  (`HomeLaunchGrid.crossAccountLeak.test.tsx`, `store/listenerMiddleware.test.ts`), zero in
  `RunConnectionProvider.tsx`. Manual re-run of the register's own reproduction on the seeded
  `ppt_v2` run `a8dfa959-e233-4ddf-87ce-d9a942cefde3`: signed in qa-admin, clicked "Run Again"
  on the cancelled run twice (fixture was mid-reset by concurrent activity on the first attempt);
  the second attempt navigated to `/runs/{id}/stream` via the same `router.push` remount FIX-330
  targets, and the live view — without any manual reload — tracked the pipeline through
  "0/4 → 2/4 agents · Deck QA Agent · Writing…" to a full terminal "Done" state (17m37s runtime,
  4.0M tokens, deliverable rendered) entirely from the SSE stream. Backend `lint-imports` (run
  from `backend/`) shows 1 pre-existing broken contract (`agents.execution_engine.engine` →
  `app.api.*`) — unrelated to this frontend-only diff (zero Python touched), not introduced here.
  `backend/docs` 200, `frontend` build/typecheck clean for this file, no new console errors.
  Evidence: `bug-hunter/evidence/runs-cancelled/BUG-20260828-015930-runs-cancelled/04-verify-live-view-reached-done-no-reload.png`.
- **Validated:** 2/3 on 2026-08-28, cycles 2 and 3 — timing race between the resume-triggered
  `router.push` remount (DashboardLayout's `isRunning` effect) and the SSE reattach; cycle 1
  self-recovered by +12s, cycles 2/3 stayed frozen 15-30s+ post-`pipeline_failed`, always fixed by
  a manual reload. Issue card: [ISS-220](../.knowledge/cards/20260828-1712-ISS-220.md)
- **Found at:** 2026-08-28 01:59 UTC
- **Found by:** bug-runs-cancelled-r1
- **Fingerprint:** `/runs/{id}/stream|run-again-live-progress-panel|click-run-again-on-a-cancelled-run|live-view-never-updates-past-starting-after-backend-pipeline_failed`
- **Evidence:** `bug-hunter/evidence/runs-cancelled/BUG-20260828-015930-runs-cancelled/`
- **Root cause:** CONFIRMED. `DashboardLayout.tsx:735-769`'s `pipelineState?.isRunning` effect
  unconditionally `router.push`es to `/runs/{id}/stream` (line 768) with no pre-registration of
  page state, remounting `frontend/src/app/[...view]/page.tsx` (established mechanism, FIX-298 /
  BUG-030). That remount tears down the page-local SSE subscriber effect
  (`page.tsx:2195-2206`, the *sole* wiring from `RunConnectionProvider`'s fan-out to
  `pipelineState`) and rebuilds it; `RunConnectionProvider`'s `fanout`
  (`frontend/src/providers/RunConnectionProvider.tsx:331-339`) has zero buffering —
  `subscribersRef.current.forEach(...)` simply drops any frame fanned out while the page's
  handler is not currently subscribed. The one compensating mechanism, the T11 `liveRunIds`
  durable-replay fast path (`page.tsx:3285-3419`), is a single non-retried `getRunEvents`
  snapshot taken at mount time — it cannot recover an event the backend emits after that
  snapshot, which is exactly the shape of a pipeline that fails ~3-4s into the resumed run.
  Full trace in [ISS-220](../.knowledge/cards/20260828-1712-ISS-220.md)'s "Root cause —
  confirmed (analyzer pass)" section.
- **Blast radius:** every caller of `handleResumeRun` (`DashboardLayout.tsx:2253-2311`), the
  single funnel `onRelaunch` is wired to (`DashboardLayout.tsx:3012`) — `RunChatLane`'s
  cancelled-run "Run Again" (reproduced here), failed-run "Reopen & fix from the failed step"
  (`RunChatLane.tsx:1816-1824`), and degraded-run "Run again" (`RunChatLane.tsx:1845-1867`) all
  share the identical code path and are equally exposed to the same timing race.
- **Issue cards:** [ISS-220](../.knowledge/cards/20260828-1712-ISS-220.md) (root — confirmed
  mechanism added this pass), [ISS-236](../.knowledge/cards/20260828-1740-ISS-236.md) (sibling,
  INFERRED: failed-run "Reopen & fix" shares `handleResumeRun`),
  [ISS-237](../.knowledge/cards/20260828-1741-ISS-237.md) (sibling, INFERRED: degraded-run "Run
  again" shares `handleResumeRun`)
- **Fix card:** [FIX-330](../.knowledge/cards/20260828-2047-FIX-330.md) — `RunConnectionProvider.fanout` now buffers the frames it dispatches while
  `subscribersRef` is empty (the page.tsx remount gap a resume's `router.push` opens) and
  `subscribe` replays the still-fresh ones to the joining listener, bounded to 200 frames /
  15s. Fixed at the shared seam, so the failed-run "Reopen & fix" (ISS-236) and degraded-run
  "Run again" (ISS-237) paths are covered by the same diff. Verified: the 3 `it.fails` cases
  in `frontend/src/providers/RunConnectionProvider.test.tsx` now XPASS ("Expect test to
  fail"), 6 other cases in that file green, 26/26 green in
  `frontend/src/app/[...view]/liveRunSwitch.fix201.test.ts`.

### Summary
Clicking "Run Again" on cancelled run `a8dfa959-e233-4ddf-87ce-d9a942cefde3` (seeded `ppt_v2` run,
cancelled while awaiting clarification, per the worker brief's resolved instances) navigates to
`/runs/{id}/stream` and shows a live progress panel: header badge "Running", "0/4 agents", Steps
tab auto-selected showing "Pipeline running · 0/4", and "Presentation Strategist Agent · Starting…".
On the backend, the re-run fails almost immediately — `GET /api/runs/{id}/events` shows a
`pipeline_failed` event at `+3.78s` ("no agent completed", all 4 agents in `agents_failed`) followed
by a `chat_reply` event ("What went wrong"). The live `/stream` page never reflects this: it
remains showing "Running / 0/4 agents / Starting…" indefinitely (confirmed static for 10+ seconds
after the backend had already failed and moved on) with no error surfaced, no chat message
rendered, and the Steps lane frozen on the first agent's "Starting…" state. Only a full manual page
reload (fresh `page.goto` to the same URL) reveals the true state: duration "4s", a "What went
wrong" chat entry, and a "Failed agents" list of all 4 agents. This is a different mechanism from
the already-filed `BUG-20260828-014937-runs-id-stream` (diverted run's Preview tab shows a static,
state-unaware "Output will appear here" placeholder on a *fresh page load* of an already-terminal
run) — here the page is actively live-polling its own just-triggered run and simply stops
reflecting new events partway through, requiring a reload to recover, not a copy/wording defect on
initial load. Separately (not filed, for context): `GET /api/runs/{id}` also continued reporting
`"status": "cancelled"` throughout and after the re-run, with `error: null`, even though the
pipeline had already failed — the run's terminal status is never updated to `failed` by this
"Run Again" path, which the reload masks by deriving "Failed agents" from the event stream rather
than the run's own `status` field.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3`
   (seeded cancelled `ppt_v2` run). Confirm header shows "Cancelled" and the resume panel reads
   "The run was stopped. Click Run Again to resume from where it left off."
2. Click "Run Again". URL becomes `/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3/stream`; header shows
   "Running", "0/4 agents"; Steps tab shows "Pipeline running · 0/4 · BUILDING" and "Presentation
   Strategist Agent · Starting…".
3. Wait 10+ seconds without interacting. Independently poll `GET /api/runs/{id}/events` — observe
   `pipeline_failed` (seq 29, ~4s after start) and `chat_reply` ("What went wrong", seq 30) already
   present in the event stream.
4. Re-check the live page: still shows "Running / 0/4 agents / Starting…" — unchanged from step 2,
   with no failure indication anywhere on screen.
5. Perform a fresh navigation (`page.goto`) to the same `/runs/{id}/stream` URL. Now the page
   correctly shows duration "4s", a "What went wrong" chat entry, and a "Failed agents" list
   (Presentation Strategist Agent, Deck Engineer Agent, Deck QA Agent, PPTX Code Generator) — the
   true terminal state, only visible after a manual reload.

### Expected
The live `/stream` view should reflect the backend's own event stream in near-real-time (as it
does for a fresh run) — once `pipeline_failed` is emitted, the header, agent lane, and chat
transcript should update to show the failure without requiring the user to manually reload the
page.

### Actual
The live view freezes on the initial "Running / 0/4 agents / Starting…" state indefinitely; the
already-failed pipeline is invisible until the user reloads the page from scratch.

### Evidence
- Before (cancelled run, resume panel): `bug-hunter/evidence/runs-cancelled/BUG-20260828-015930-runs-cancelled/01-before-run-again.png`
- Stuck live view (10s+ after backend `pipeline_failed`, still "Starting…"): `bug-hunter/evidence/runs-cancelled/BUG-20260828-015930-runs-cancelled/02-stuck-running-after-backend-failed.png`
- After manual reload (correct "Failed agents" state, same URL): `bug-hunter/evidence/runs-cancelled/BUG-20260828-015930-runs-cancelled/03-after-reload-shows-failed-agents.png`

### Browser Signals
- Console: no relevant error observed.
- Network: none additionally captured for the stuck window (network log buffer had rolled over by
  inspection time); the event-content evidence above (via direct `GET .../events` polling) confirms
  the backend had already emitted the terminal events the live page failed to render.
- State/URL: `GET /api/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3` continued to report
  `"status": "cancelled"`, `"error": null` even after the re-run's `pipeline_failed`, only
  `completed_at`/`duration` were bumped (to `2026-08-28T01:57:41...` / `315.9`, then observed as
  "4s" in the UI's own duration display post-reload) — the run's own `status` field is never
  updated to `failed` by this path (noted for context, not filed as a separate defect here).

### Safety note
Per the round's explicit handover, this round's ONE permitted real re-run was used here to
establish this behaviour (clicking "Run Again" once on `a8dfa959-e233-4ddf-87ce-d9a942cefde3`). No
other run was cancelled, deleted, or re-run.

- **Issue card:** [ISS-220](../.knowledge/cards/20260828-1712-ISS-220.md)

## BUG-20260828-020430-runs-diverted — "Start a new run" on a diverted run's detail page calls the resume endpoint, which the backend correctly rejects, with no visible error shown to the user

- **Page:** Diverted run detail
- **Route:** /runs/{id} (diverted run)
- **Severity:** High
- **Status:** CLOSED
- **Found at:** 2026-08-28 02:04 UTC
- **Found by:** bug-runs-diverted-r1
- **Fingerprint:** `/runs/{id}|diverted-run-start-a-new-run-button|click-start-a-new-run|calls-resume-endpoint-409-rejected-silently-no-user-feedback`
- **Evidence:** `bug-hunter/evidence/runs-diverted/BUG-20260828-020430-runs-diverted/`
- **Validated:** 3/3 on 2026-08-28, cold start each cycle (cycle 3 clicked immediately with no settle wait) — unconditional, no axis dependence
- **Issue card:** [ISS-221](../.knowledge/cards/20260828-1718-ISS-221.md)
- **Root cause:** The shared `relaunch(label)` helper in `frontend/src/components/chat/RunChatLane.tsx:1694`
  renders only a `<Button>`, never the `relaunchError` amber-banner block. That block is hand-duplicated
  into only 2 of 4 terminal branches (`cancelled` at line 1722, `failed` at line 1808 — its own bespoke
  buttons, not `relaunch()`); the `degraded` branch (line 1865) and the "no marker" fallback (line 1871,
  `relaunch("Start a new run")`) both call the shared helper with no error rendering at all. A diverted
  run's only pipelineState marker is `divertedTo` (`frontend/src/hooks/useWorkflow.ts:911`; `diverted: null`
  in `TERMINAL_MARKER_BY_STATUS`, `useWorkflow.ts:329`) — never `cancelled`/`failed`/`degraded` — so it
  falls into the "no marker" branch, the one branch with zero error-rendering wired in, even though
  `DashboardLayout.tsx`'s `handleResumeRun` (line 2253-2311) already computes and stores the right message
  in `resumeError`, passed down as the `relaunchError` prop (`DashboardLayout.tsx:3014`) — it is simply
  never read on this path. CONFIRMED by direct source read.
- **Blast radius:** `postResume` (`frontend/src/lib/api.ts:1216`) has exactly one production caller
  (`handleResumeRun`); `handleResumeRun`/`onRelaunch` mount into exactly one production `<RunChatLane>`
  (`DashboardLayout.tsx:2974`); `resumeError`/`relaunchError` has one producer and one consumer, read in
  only 2 of the 4 terminal branches inside that one component. The bug is per-BRANCH inside one render
  function, not per-caller — every "resume rejected" scenario funnels through the same `relaunch()` helper.
- **Fix belongs in:** `RunChatLane.tsx`'s shared `relaunch(label)` helper (line 1694) — move the
  `relaunchError` banner block into the helper itself so both branches that call it (`degraded`,
  the diverted-landing fallback) pick it up in one diff, rather than patching each branch separately.
- **Issue cards:** [ISS-221](../.knowledge/cards/20260828-1718-ISS-221.md) (root, CONFIRMED),
  [ISS-233](../.knowledge/cards/20260828-1829-ISS-233.md) (sibling, INFERRED: the `degraded` branch
  shares the identical missing-relaunchError shape, so a resume rejection on a degraded run is silently
  swallowed the same way — not yet reproduced)
- **Fix card:** [FIX-329](../.knowledge/cards/20260828-2045-FIX-329.md) — relaunchError banner
  moved into RunChatLane.tsx's shared `relaunch()` helper (and out of the cancelled branch's
  duplicate), so the degraded and no-marker/diverted branches render the rejected resume
- **Verified:** `frontend/src/components/chat/__tests__/RunChatLane.terminal.test.tsx` — the two
  `it.fails` strict-xfail guards (ISS-221, ISS-233) XPASSed ("Error: Expect test to fail"),
  markers removed, re-run 7/7 green. Regression: `RunChatLane.test.tsx` 55/55 green. Manual
  repro re-run by hand in lane4 on the same diverted run
  `940ca699-b21b-4666-8e44-3370a08a4561`: clicked "Start a new run", same 409 + `postResume
  failed` console entries as the original repro, but the amber "Could not resume the run —
  please try again." banner now renders in place (before/after in
  `bug-hunter/evidence/runs-diverted/BUG-20260828-020430-runs-diverted/04-verify-before.png` and
  `05-verify-after.png`). Backend unchanged (frontend-only fix); `:8000/docs` → 200. `npx tsc
  --noEmit` shows pre-existing errors in unrelated files
  (`HomeLaunchGrid.crossAccountLeak.test.tsx`, `listenerMiddleware.test.ts`), none in
  RunChatLane.tsx. `lint-imports` (run from `backend/`) shows a pre-existing broken contract in
  `agents.execution_engine` unrelated to this frontend-only change.

### Summary
On a `diverted` run's detail page, the primary action button reads "Start a new run" — implying
it launches a fresh run (of the same or the diverted-to workflow). In reality, clicking it fires
`POST /api/runs/{id}/resume`, the same endpoint used for the "Run Again"/resume action on failed
or cancelled runs. The backend correctly rejects this for a diverted run
(`409 Conflict`, body `{"error":"Run is 'diverted'; only failed, degraded, or cancelled runs are
resumable","code":"run_not_resumable","recoverable":false}`), since a diverted run already handed
off its work to a successor run (confirmed via the backend's own `pipeline_diverted` event,
which carries `diverted_to_run_id`/`diverted_to_workflow`, and the Steps tab's own "Diverted to
<workflow> → open triggered run" link, which correctly navigates to that successor). But nothing
in the UI surfaces this rejection to the user: no toast, no inline error, no disabled/loading
state change on the button, no navigation. The button, chat transcript, tabs, and badge are
pixel-identical before and after the click (confirmed via before/after screenshot and full
snapshot diff) — the only trace of the failure is a console error and a `409` in the network log,
neither of which a user would ever see. The button silently does nothing, contradicting its own
label ("Start a new run" implies an action will occur) and giving no path to actually start a new
run of the original or target workflow from this page.

### Reproduction
1. Sign in as qa-admin. Navigate to `http://localhost:3000/runs/940ca699-b21b-4666-8e44-3370a08a4561`
   (seeded diverted run "Ex A4 Human Divert"). Confirm header badge reads "Diverted".
2. Take a baseline snapshot/screenshot of the page (chat transcript, "Start a new run" button,
   tabs, badge).
3. Click "Start a new run".
4. Observe: the page is visually and structurally unchanged — same URL, same badge text
   ("Diverted"), same chat transcript, no toast/banner/error message appears anywhere.
5. Inspect the network log and console: `POST http://localhost:8000/api/runs/940ca699-b21b-4666-8e44-3370a08a4561/resume`
   returned `409 Conflict` with body `{"error":"Run is 'diverted'; only failed, degraded, or
   cancelled runs are resumable","code":"run_not_resumable","recoverable":false}`; console logs
   `postResume failed ApiError: ...` for the same payload.
6. Repeated steps 1-5 a second time on the same run — identical result (409, no UI feedback).
7. Repeated on a second, independent diverted run,
   `http://localhost:3000/runs/277bc03a-d2ba-4405-876d-d0aa861bc9ed` — identical shape: `POST
   .../277bc03a.../resume` returns the same `409`/`run_not_resumable`, with no visible UI change,
   confirming this is systemic to the diverted-run detail page, not one seeded run's data.

### Expected
"Start a new run" on a diverted run should either genuinely start a new run (of the original
workflow, or of the workflow it diverted to — either is defensible, but it must actually launch
something), or, if resuming a diverted run is intentionally unsupported, the button should call
an endpoint appropriate to that action (or be removed/relabeled), and any rejection from the
backend must be surfaced to the user as a visible error, not swallowed silently.

### Actual
The button calls the resume endpoint, which the backend correctly refuses for a diverted run's
terminal state, and the frontend discards the resulting `409` with no user-visible feedback of
any kind — the button appears to do nothing when clicked.

### Evidence
- Before: `bug-hunter/evidence/runs-diverted/BUG-20260828-020430-runs-diverted/01-before.png`
- Failure (after click, no visible change): `bug-hunter/evidence/runs-diverted/BUG-20260828-020430-runs-diverted/02-failure-no-visible-change.png`
- Reproduced on a second diverted run: `bug-hunter/evidence/runs-diverted/BUG-20260828-020430-runs-diverted/03-repro-second-run.png`
- Console excerpt: `bug-hunter/evidence/runs-diverted/BUG-20260828-020430-runs-diverted/console.log`

### Browser Signals
- Console: `postResume failed ApiError: {"error":"Run is 'diverted'; only failed, degraded, or
  cancelled runs are resumable","code":"run_not_resumable","recoverable":false}` on both tested
  runs.
- Network: `POST /api/runs/{id}/resume` returns `409 Conflict` for both diverted runs tested.
- State/URL: `location.href` unchanged by the click in every trial; no toast/banner component
  renders; the run's own badge/status text (still "Diverted") is unaffected.

## BUG-20260828-020900-runs-id-versions — Version picker label is stuck on "Version v1" while viewing a real, distinct v2

- **Page:** Run detail pinned to an artifact version
- **Route:** /runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/versions/2 (root run has a genuine 2-member
  family: v1 `77f74563-fa19-4f0b-84fd-d0224f89a54a`, v2 `ef86e750-bbcd-404f-855a-fb0d5bee63f5`)
- **Severity:** Medium
- **Status:** DUPLICATE
- **Found at:** 2026-08-28 02:09 UTC
- **Found by:** bug-runs-id-versions-r1
- **Fingerprint:** `/runs/[id]/versions/2|version-picker-label|load-existing-second-version|header-and-picker-both-claim-v1-while-serving-v2-content`
- **Evidence:** `bug-hunter/evidence/runs-id-versions/BUG-20260828-020900-runs-id-versions/`
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduces on the very first cold render of
  `/versions/2`, no timing/entry-path variation needed. Root cause traced:
  `parsed.version` from `routes.ts:338` is never read again anywhere in the frontend
  (`reopenedRunIdFor` in `frontend/src/app/[...view]/page.tsx:182-196` drops it and always
  resolves the family ROOT run id, so `PreviewPanel`'s `activeIdx`/`headerVersionLabel` land on
  v1 regardless of the URL's version number).
- **Issue card:** [ISS-286](../.knowledge/cards/20260828-1712-ISS-286.md)
- **Root cause (CONFIRMED, re-verified by analyzer, 2026-08-28):** Byte-identical mechanism to
  [ISS-230](../.knowledge/cards/20260828-1805-ISS-230.md)/[ISS-294](../.knowledge/cards/20260828-1725-ISS-294.md):
  `reopenedRunIdFor` (`frontend/src/app/[...view]/page.tsx:182-196`) still resolves `run-version`
  to the family ROOT id only, so absent a separate pin `activeRunId`/`activeIdx` land on v1. Read
  fresh from the current (uncommitted) working tree: a NEW `pinnedVersionFor` (`page.tsx:208-210`)
  now reads `parsed.version` and threads it through `DashboardLayout.tsx:3134` into
  `PreviewPanel.tsx:604-621` (`pinnedMemberId` -> `viewingVersion` -> `activeRunId`/`activeIdx` at
  `PreviewPanel.tsx:539-540` -> `headerVersionLabel` at `PreviewPanel.tsx:844` -> `RunHeader`'s
  `VersionMenu` button/listbox at `RunHeader.tsx:34-53,103,108,127`) — this is
  [FIX-328](../.knowledge/cards/20260828-2014-FIX-328.md), already applied and, per this bug's own
  Verifier note under **BUG-20260828-090732-runs-id-versions** below, already confirmed by hand:
  "cold-loading `/runs/{rootId}/versions/2` now shows 'Version v2' immediately."
- **Blast radius (re-checked independently):** `grep -rn "reopenedRunIdFor\|pinnedVersionFor\|pinnedVersion\|headerVersionLabel" frontend/src`
  — `reopenedRunIdFor`/`pinnedVersionFor` each have exactly one call site in `page.tsx`;
  `pinnedVersion` has exactly one further hop (`DashboardLayout.tsx` -> `PreviewPanel.tsx`);
  `headerVersionLabel` is read only inside `PreviewPanel.tsx`. No caller exists outside the chain
  ISS-230/ISS-294/[ISS-296](../.knowledge/cards/20260828-1724-ISS-296.md) (inverse: menu write)/
  [ISS-300](../.knowledge/cards/20260828-1726-ISS-300.md) (Files tab) already mapped and fixed —
  those four exhaust the sibling axes this root cause implies, so no new ISS card was filed.
- **Duplicate of:** [ISS-230](../.knowledge/cards/20260828-1805-ISS-230.md) (root) /
  [ISS-294](../.knowledge/cards/20260828-1725-ISS-294.md) (the exact cold-mount/deep-link
  mechanism), resolved by [FIX-328](../.knowledge/cards/20260828-2014-FIX-328.md) under
  **BUG-20260828-090732-runs-id-versions** (Status: CLOSED, below) — found and validated
  independently before that bug's fix landed, so this is a race between two parallel discoveries
  of the same defect, not a filing error at validate time. [ISS-286](../.knowledge/cards/20260828-1712-ISS-286.md)
  itself is kept (now `status: resolved`, cross-linked to ISS-230/ISS-294/FIX-328) as the record of
  this bug's own independent discovery. No new fix needed.

### Summary
This is distinct from the already-known D-12 (a NONEXISTENT version like `/versions/99` silently
serving v1 with no error). Here the requested version genuinely exists and the CORRECT content is
served — the chat transcript, deliverable filename
(`luxury-asset-marketplace-jets-yachts-cars.html`), 5-agent pipeline, and rendered prototype all
correctly reflect the v2 revision (a "replace flat gray placeholders with inline SVG" pass). But
the version-picker control in the run-detail chrome — both its collapsed button (`aria-label`
"Version v1, choose version", visible text "Version v1") and its expanded listbox (option "Version
v1" marked `[active][selected]`, option "Version v2" NOT selected) — falsely claims the page is
showing v1, when it is actually showing v2. So the app doesn't just fail to error on a bad
request (D-12); when given a GOOD request for a real second version, it renders the right content
but mislabels which version that content is, in the one UI element whose entire job is to tell the
user which version they're looking at. This reproduced identically on the initial navigation and
again after a full page reload of `/versions/2`, so it is not a one-off render race.

### Reproduction
1. Sign in as qa-admin. Navigate directly to
   `http://localhost:3000/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/versions/1`. Confirm the
   picker button reads "Version v1" and the chat transcript shows the original "Luxury Asset
   Marketplace" prototype run (1 revision, "Delivered" once).
2. Navigate to `http://localhost:3000/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/versions/2`
   (fresh navigation, not a picker click).
3. Observe the chat transcript, deliverable filename, and 5-agent pipeline summary — all
   correctly reflect the v2 revision ("Replace every flat gray image placeholder..." run).
4. Observe the version-picker button next to Share/Download: it still reads "Version v1". Open it
   — the listbox shows "Version v1" as the selected/active option and "Version v2" as unselected,
   even though v2's content is what's on screen.
5. Reload the page at the same `/versions/2` URL — the mislabel persists identically.

### Expected
When `/versions/2` renders v2's content, the version-picker button and listbox should read/select
"Version v2", consistently with the URL and the content actually shown.

### Actual
The picker button and its listbox both claim "Version v1" is selected/current, while the visible
page content is unambiguously v2's.

### Evidence
- Before (v1, correct): `bug-hunter/evidence/runs-id-versions/BUG-20260828-020900-runs-id-versions/01-before-versions-1.png`
- Failure (v2 content, picker says v1): `bug-hunter/evidence/runs-id-versions/BUG-20260828-020900-runs-id-versions/02-failure-versions-2-picker-says-v1.png`
- After reload, still broken: `bug-hunter/evidence/runs-id-versions/BUG-20260828-020900-runs-id-versions/03-after-reload-still-broken.png`

### Browser Signals
- Console: none observed (0 errors)
- Network: `/api/runs/{root_id}` and `/api/runs/{root_id}/family` both return correct data
  (family confirms v1/v2 with correct `revision_index`); the version-number mismatch is a
  frontend label/state bug, not a backend data problem
- State/URL: URL correctly stays at `/versions/2` throughout; only the picker's own label/selection
  state is wrong

## BUG-20260828-021300-library-skills — Skill with an empty `category` field renders a blank category label and is unreachable through any category pill

- **Page:** Library — Skills tab
- **Route:** /library?tab=skills
- **Severity:** Low
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `backend/tests/agents/test_iss571_hook_empty_event.py`,
  `tests/integration/e2e/suites/08_library/test_iss329_skill_empty_category.py` (2 tests),
  `tests/integration/e2e/suites/08_library/test_iss570_agent_skills_picker_pill.py` all XPASS
  confirmed then plain green after the `xfail` markers were removed (the two e2e tests also
  needed their locator/assertion repaired — a broken pill-label regex and a Playwright glob
  quirk on `to_have_url`, both test-side, not app-side; ISS-570's test was rewritten to drive
  the composer's editable Canvas rail `AgentSkillsPicker` instead of the readOnly Library
  drawer, which disables every pill). Manual re-run of the register's original reproduction in
  real Chrome (qa-admin, `/library?tab=skills`): `GET /api/skills/library` now returns
  `html-deck-to-pptx` with `category: "uncategorized"` (was `""`); its card badge reads
  "uncategorized" (was blank); clicking the new "Uncategorized" pill filters to exactly that
  one card, confirming the skill is reachable via a specific pill — no longer only via "All" or
  search. Confirmed the same fix reaches the composer's `AgentSkillsPicker` (canvas rail, any
  agent's Skills tab) via ISS-570's mechanism. Health: backend `:8000/docs` → 200 (pure `.py`
  fix, `--reload` already applied, no restart needed); `cd backend && lint-imports` → 3 kept /
  1 broken, the same pre-existing "kernel imports only capability ports (scaffold)" contract
  break, unrelated to `skills_catalog.py`/`hooks_catalog.py`; no new browser console
  errors/warnings on `/library?tab=skills`. Regression:
  `backend/tests/unit/test_skills_catalog_compatible_agents.py` (6) +
  `backend/tests/agents/test_hooks_catalog_agent_ids.py` (1) all green;
  `tests/integration/e2e/suites/08_library/test_library.py` (24 scenarios) all green.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced on every cold-start attempt (fresh
  navigation `/dashboard` → `/library?tab=skills`), no axis narrowing needed
- **Root cause:** `backend/app/agents/skills_catalog.py:112` defaults `category` to `""` when a
  skill's `SKILL.md` frontmatter omits the field (`backend/skills/global/html-deck-to-pptx/SKILL.md`
  is the one skill with no `category` key); `backend/app/api/skills.py:35`
  (`categories = sorted({e.category for e in entries if e.category})`) then explicitly drops that
  empty string out of the pill list `GET /api/skills/library` returns, so no pill's filter value
  is ever `""`
- **Blast radius:** every consumer of `useSkillsCatalog()` — `LibraryPage.tsx` (reported symptom)
  AND `AgentSkillsPicker.tsx` (the composer's only skill-attachment UI: Canvas rail, Simple-view
  row, agent inspector drawer) share the identical filter-equality + pill-visibility mechanism;
  `AgentsPopup.tsx` and `backend/app/api/user_agents.py` also consume the catalog but never read
  `.category`, so they are unaffected. `backend/app/api/hooks.py:33` carries the identical
  `sorted({e.X for e in entries if e.X})` shape for the Hooks catalog's `event` field — latent
  today (0/8 hooks affected) but the same defect would reproduce there too.
- **Issue cards:** [ISS-329](../.knowledge/cards/20260828-1838-ISS-329.md) (root),
  [ISS-570](../.knowledge/cards/20260829-0004-ISS-570.md) (sibling: AgentSkillsPicker.tsx shares
  the unreachability in the composer's skill picker),
  [ISS-571](../.knowledge/cards/20260829-0004-ISS-571.md) (sibling: hooks.py's events pill-builder
  carries the identical latent pattern),
  [FIX-392](../.knowledge/cards/20260829-0119-FIX-392.md) (fix)
- **Found at:** 2026-08-28 02:13 UTC
- **Found by:** bug-library-skills-r1
- **Fingerprint:** `/library?tab=skills|skill-card-category-badge-and-category-pill-filter|render-card-for-skill-with-empty-category-field|blank-category-label-and-card-unreachable-by-any-specific-pill`
- **Evidence:** `bug-hunter/evidence/library-skills/BUG-20260828-021300-library-skills/`

### Summary
`GET /api/skills/library` returns 186 skills; `total_count` (186), the raw array length (186),
and the rendered card count (`document.querySelectorAll('div.cursor-pointer.p-4').length` = 186)
all agree — no cap or pagination gap at this scale (unlike the Run History 50/273 cap). The nine
category pills (Collaboration, Creative, Debugging, Planning, Research, Security, Specialist,
Testing, Workflow) are correctly derived from the categories actually present in the skill data,
and clicking each pill returns exactly the count of skills carrying that category value (verified
for Research: 2/2, and Testing: 48/48) — so this is NOT the same mechanism as the known D-26
(agents whose pills are built from an entirely different, mismatched source list, orphaning 52 of
93 agents). Here, exactly one skill record — `html-deck-to-pptx` (id `html-deck-to-pptx`) — has
`category: ""` (empty string) in the API response, and also `tags: []`. Its card renders in the
grid with a visibly blank category-badge line (the `<p class="...uppercase tracking-[0.1em]
font-semibold capitalize">` element that shows "TESTING"/"PLANNING"/etc. on every other card is
present but empty) and no tag chips. Because no category pill's filter value is an empty string,
this single skill can never be reached by clicking any specific category pill — only "All" (or
search by name) surfaces it.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/library?tab=skills` (All pill,
   186 cards).
2. Confirm scale integrity: `document.querySelectorAll('div.cursor-pointer.p-4').length` = 186;
   `GET /api/skills/library` response `total_count` = 186 and `skills.length` = 186 — all three
   agree, no pagination/cap defect at this page.
3. In that same API response, find the skill with `category: ""` — `html-deck-to-pptx`
   ("Turn a finished HTML slide deck into a real, editable PowerPoint file with PptxGenJS...").
4. On the "All" pill, use `browser_find` for "html-deck-to-pptx" — the card is present. Inspect
   its DOM: the category-badge `<p>` under the title is empty (`""`), unlike every neighboring
   card which shows its category in caps (e.g. "PLANNING", "TESTING").
5. Click the "Testing" category pill (URL becomes `?category=testing`). Card count is 48
   (matches the 48 skills whose `category === "testing"` in the API data exactly). Search
   `document.body.innerText` for "html-deck-to-pptx" — not found; confirmed absent.
6. Repeat against the "Research" pill (2/2 cards match exactly) for a second confirmation that
   pill filtering itself works correctly and is not the cause — the gap is specific to this one
   skill's missing category value.
7. Return to the "All" pill — the card reappears, confirming this is a stable, reproducible,
   category-specific reachability gap tied to the skill's own data, not a rendering race.

### Expected
Every skill should have a non-empty category so its card shows a real category badge and the
skill is reachable through the category pill that corresponds to it, consistent with every other
skill in the library.

### Actual
The `html-deck-to-pptx` skill has an empty `category` value, so its card renders a blank
category-badge line and the skill is permanently unreachable through any of the nine category
pills — only visible via "All" or by searching its name directly.

### Evidence
- Before (card visible under "All", scrolled into view): `bug-hunter/evidence/library-skills/BUG-20260828-021300-library-skills/01-before-card-visible-in-all.png`
- Failure (card's category-badge line is blank): `bug-hunter/evidence/library-skills/BUG-20260828-021300-library-skills/02-failure-blank-category-label.png`
- Unreachable via a specific pill ("Testing" selected, 48/48 other cards shown, this one absent): `bug-hunter/evidence/library-skills/BUG-20260828-021300-library-skills/03-unreachable-via-testing-pill.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET http://localhost:8000/api/skills/library` returns `200 OK`; response body
  confirms `total_count: 186`, `skills.length: 186`, and exactly one entry
  (`id: "html-deck-to-pptx"`) with `category: ""` and `tags: []`.
- State/URL: `?category=<slug>` query param updates correctly per pill click; the affected skill's
  card is absent under every specific `category=` value and present only under "All"/unfiltered.

## BUG-20260828-025500-library-hooks — Hook detail page's "Copy" button gives zero feedback that a copy occurred

- **Page:** Library — Hook detail
- **Route:** /library/hooks/<hook-id> (e.g. /library/hooks/post-design-quality, /library/hooks/post-quality-gate)
- **Severity:** Low
- **Status:** CLOSED
- **Fixed:** 2026-08-29 — one shared guard, `frontend/src/hooks/useClipboardCopy.ts` (new): `navigator.clipboard.writeText` in a `try/catch`, `{copied, failed, copy}`, `copied` only flips on a resolved write. 10 call sites across 7 files (`LibraryPage.tsx` x2, `AgentDetailPanel.tsx`, `AppBuilderPreview.tsx`, `MarkdownPreview.tsx` x2, `UserStoryPreview.tsx`, `PrototypePreview.tsx`, `IntegrationsCard.tsx` x2) now route through it and render a `Copy failed` state. Tests, one file at a time, `npx vitest --run` from `frontend/` — 7 of 9 `it.fails` guards XPASS ("Error: Expect test to fail"): AgentDetailPanel 1, AppBuilderPreview 1, MarkdownPreview 2, UserStoryPreview 1, PrototypePreview 1, IntegrationsCard 1 of 2. The other 2 (LibraryPage x2) plus IntegrationsCard's second cannot XPASS — harness defects recorded in ISS-600, app side proven by throwaway probes (corrected `useParams` deep-link mock -> `Tests 2 passed (2)`; key-copy button -> "Copy failed" on reject, "Copied" on resolve). No test file edited. Regression: LibraryPage.test.tsx 9 passed, HandoffWorkflow 2 passed, PrototypePreview.byteSize / AppBuilderPreview.byteSize / MarkdownPreview.security / AgentDetailPanel.artifactCards / PreviewPanel.genericDeliverable all passed. `npx tsc --noEmit` zero errors in the 8 touched files (4 unrelated pre-existing test-file errors persist); eslint 0 errors. Frontend-only — no backend restart needed. Cards: FIX-395; ISS-599 and ISS-600 opened for the deferred call sites and the two broken tests.
- **Verified:** 2026-08-29 — independently re-ran all 7 `*.copyFeedback.test.tsx` files one at a time with `npx vitest --run` from `frontend/`: reproduced the fixer's exact XPASS counts (AgentDetailPanel 1/1, AppBuilderPreview 1/1, MarkdownPreview 2/2, UserStoryPreview 1/1, PrototypePreview 1/1, IntegrationsCard 1/2, LibraryPage 0/2 — matches fixer's report exactly). Independently re-verified the LibraryPage harness-defect claim with my own throwaway probe (corrected `useParams` to a deep-link mock, dropped the tab/card clicks) -> XPASS, confirming the app fix is correct and the 2 remaining reds are ISS-600's tracked test-authoring bug, not an app regression. Converted the 6 fully-XPASS files' `it.fails` to `it` and IntegrationsCard's install-command test only, re-ran all 7 -> plain green (6 files fully green, IntegrationsCard 1 passed/1 still `it.fails` for the untouched selector bug, LibraryPage untouched, both left for ISS-600). Manual repro in real Chrome (lane6, qa-admin, cold deep-link to `/library/hooks/post-design-quality`, matching the original register reproduction): clicked "Copy" with the real clipboard -> button flipped to "Copied!" (before-fix evidence showed zero change); then patched `navigator.clipboard.writeText` in-page to reject and clicked again -> button showed "Copy failed". Both the success and failure paths now give visible feedback where none existed before. Screenshots: `bug-hunter/evidence/library-hooks/BUG-20260828-025500-library-hooks/06-verify-after-copy-click.png` (transient dev-server HMR blank, discarded), `07-verify-after-copy-shows-copied.png`, `08-verify-copy-failed-state.png`. No new console errors/warnings (0/0) on the page. Backend `:8000/docs` -> 200 (frontend-only fix, no restart needed). `npx tsc --noEmit`: same 4 pre-existing unrelated errors, zero in the 8 touched files. `npx next build` (frontend/): compiled successfully, zero errors. `lint-imports` (from `backend/`): same 1 pre-existing broken contract (`agents.execution_engine.engine` -> `app.api`), unrelated to this frontend-only change. Regression: `LibraryPage.test.tsx` 9/9 passed, `HandoffWorkflow.test.tsx` 2/2 passed.
- **Found at:** 2026-08-28 02:55 UTC
- **Found by:** bug-library-hooks-r2
- **Fingerprint:** `/library/hooks/<id>|hook-detail-copy-button|click-copy-button|no-visual-state-change-no-toast-no-confirmation`
- **Evidence:** `bug-hunter/evidence/library-hooks/BUG-20260828-025500-library-hooks/`
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — reproduces on two different hooks
  (`post-design-quality`, `post-quality-gate`), deep-link and revisit entry, no special timing/
  account/theme/viewport condition needed.
- **Root cause:** CONFIRMED — `HookDetailModal.handleCopy`
  (`frontend/src/components/library/LibraryPage.tsx:351-355`) `await`s
  `navigator.clipboard.writeText(copyText)` with no `try/catch` and no `.catch()`; any rejection
  leaves `setCopied(true)` unreached, the rejection unhandled, and the button silently stuck on
  "Copy" forever. Read the mount site (`LibraryPage.tsx:1070-1072`, no `key` prop) to rule out a
  remount/stale-closure alternative. What exact condition trips the rejection in the harness that
  reproduced this 3/3 is INFERRED, not settled (candidates: `document.hasFocus()` false,
  transient-user-activation on a synthetic click, a Permissions-Policy block) — orthogonal to the
  fix, which is to add the missing failure path regardless of the trigger.
- **Blast radius:** grepped every `navigator.clipboard.writeText` caller under `frontend/src` — 12
  call sites across 9 files. 2 already catch-and-log
  (`chat/ArtifactCard.tsx:62-74`, `chat/MessageBubble.tsx:171-176`, still no user-visible failure
  state). The other 10 call sites across 7 files share this defect or a worse false-positive
  variant (claims "Copied" even when the write silently failed): `LibraryPage.tsx` (`SkillDetailModal`,
  201-205), `results/AgentDetailPanel.tsx:446-450`, `preview/AppBuilderPreview.tsx:240-246`,
  `preview/MarkdownPreview.tsx:49-53,174-178`, `preview/UserStoryPreview.tsx:47-51`,
  `preview/PrototypePreview.tsx:391-398`, `handoff/IntegrationsCard.tsx:73-78,316-323`.
- **Fix belongs:** in one shared helper (`copyToClipboard(text): Promise<boolean>` or a
  `useClipboardCopy()` hook) under `frontend/src/hooks/` or `frontend/src/lib/`, wrapping
  `navigator.clipboard.writeText` in a `try/catch` so all 12 call sites route through one guard
  and render a failure state with the same inline icon/label-swap idiom each already uses for
  `copied` — not a patch to `HookDetailModal` alone, which would leave every sibling below broken.
- **Issue cards:** [ISS-331](../.knowledge/cards/20260828-1840-ISS-331.md) (root: HookDetailModal),
  [ISS-555](../.knowledge/cards/20260829-0208-ISS-555.md) (sibling: SkillDetailModal, same file),
  [ISS-556](../.knowledge/cards/20260829-0208-ISS-556.md) (sibling: AgentDetailPanel, false-positive variant),
  [ISS-557](../.knowledge/cards/20260829-0208-ISS-557.md) (sibling: AppBuilderPreview, false-positive variant),
  [ISS-558](../.knowledge/cards/20260829-0208-ISS-558.md) (sibling: MarkdownPreview x2, false-positive variant),
  [ISS-559](../.knowledge/cards/20260829-0208-ISS-559.md) (sibling: UserStoryPreview, false-positive variant),
  [ISS-560](../.knowledge/cards/20260829-0208-ISS-560.md) (sibling: PrototypePreview, silent-on-failure variant),
  [ISS-561](../.knowledge/cards/20260829-0208-ISS-561.md) (sibling: IntegrationsCard x2, silent + no-feedback-ever variant)

### Summary
Clicking a hook card in the Library's Hooks tab performs a genuine client-side route navigation
to `/library/hooks/<hook-id>` (a real page, not a modal), which renders the full hook detail
(event, trigger, "how to use" steps, compatible agents, tags) plus a "Copy" button in the header
next to the close (X) button. Clicking "Copy" (presumably intended to copy the hook's markdown
`content` field, which the `GET /api/hooks/library` response carries per-hook, to the clipboard)
produces absolutely no observable feedback: the button's text stays exactly "Copy" (never
"Copied!" or similar), its icon stays the same `lucide-copy` glyph (never swaps to a checkmark),
no toast/alert appears anywhere on the page, and `document.body.innerText` shows no new text
after the click. The only DOM change is a transient `:active` pseudo-state from the click itself.
A user has no way to tell, from the UI alone, whether the copy succeeded, failed, or did
anything at all. This reproduces identically on two different hooks (`post-design-quality` and
`post-quality-gate`), so it is the button component's own behavior, not a per-hook data issue.
This is a distinct control and mechanism from the ledger's other no-feedback findings: the
composer's documented "Run once" quirk (a run-launch action), and
`BUG-20260828-011000-workflow` (a "Run Workflow" button that is a complete no-op with zero
network activity on the orphaned `/workflow` legacy builder). Here the button is a client-side
clipboard-copy action on a completely different page (the new hook detail route), and the
underlying action may well succeed (browser clipboard permissions blocked a direct read-back
verification in this sandboxed session) — the defect is specifically the total absence of any
success/failure UI feedback for an action whose entire purpose is a one-shot, silent side effect
the user cannot otherwise verify.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/library?tab=hooks`.
2. Click the "Design Quality Check X" hook card — the app navigates to
   `/library/hooks/post-design-quality`, rendering the full hook detail panel with a "Copy"
   button (lucide copy icon + "Copy" label) in the top-right of the detail header.
3. Click "Copy". Observe: the button's accessible name and rendered text remain "Copy", its
   icon/outerHTML is unchanged aside from a transient `:active` state, and no toast, alert, or
   any new text appears anywhere in `document.body.innerText`.
4. Repeat on a second, different hook: navigate to `/library/hooks/post-quality-gate`, click its
   "Copy" button — identical result: button still reads "Copy", no confirmation of any kind.

### Expected
Clicking "Copy" should give the user some positive confirmation that the copy succeeded (e.g. the
label briefly changing to "Copied!", the icon swapping to a checkmark, or a toast), consistent
with standard copy-to-clipboard UX and with how a user is expected to trust that a silent,
one-shot action actually happened.

### Actual
The button gives no feedback whatsoever after being clicked — same label, same icon, no toast —
on every hook tested, leaving the user with no way to confirm the copy occurred.

### Evidence
- Before (Design Quality Check X detail, Copy button unclicked): `bug-hunter/evidence/library-hooks/BUG-20260828-025500-library-hooks/01-before-copy-click.png`
- After click, no visible change: `bug-hunter/evidence/library-hooks/BUG-20260828-025500-library-hooks/02-after-copy-click-no-change.png`
- Repro 2 (Quality Gate detail), before: `bug-hunter/evidence/library-hooks/BUG-20260828-025500-library-hooks/03-repro2-before-copy.png`
- Repro 2, after click, no visible change: `bug-hunter/evidence/library-hooks/BUG-20260828-025500-library-hooks/04-repro2-after-copy-no-change.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no request involved; this is a pure client-side clipboard action with no accompanying
  API call.
- State/URL: URL stays on `/library/hooks/<hook-id>` throughout; `button.outerHTML` read directly
  via DOM confirmed identical text/icon before and after the click in both reproductions.

## BUG-20260828-025521-library-hooks — Hook cards on the Hooks tab are not keyboard-operable

- **Page:** Library — Hooks tab
- **Route:** /library?tab=hooks
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28 — `tests/integration/e2e/suites/08_library/test_library_keyboard.py` all 4 tests XPASS(strict) on 3 consecutive full-file runs, xfail markers removed, re-run gave plain 4/4 PASS. Manual repro re-run by hand in Chrome (lane5, qa-admin, cold nav `/library?tab=hooks`): Tab from `input[name='library-search']` now lands directly on the first hook card (`role="button" tabindex="0"`), Enter navigates to `/library/hooks/post-design-quality`, and the opened panel is `role="dialog"` with focus inside it; Escape closes it back to `/library?tab=hooks`. Also spot-checked the Agents grid (`role="button" tabIndex="0"` present). No new console errors (0/0). `npx tsc --noEmit`: zero errors in `LibraryPage.tsx` (2 pre-existing unrelated errors in `HomeLaunchGrid.crossAccountLeak.test.tsx`/`listenerMiddleware.test.ts` persist, untouched by this fix). `lint-imports` (from `backend/`): 1 pre-existing broken contract (`agents.execution_engine.engine` → `app.api`), unrelated — this fix touched only `LibraryPage.tsx`. Regression: `suites/08_library/test_library.py` 21/24 PASS on first run, the 3 failures (`test_tab_badge_counts_agree_with_the_rendered_cards`, `test_each_agent_drawer_tab_shows_its_own_content[Overview]`, `test_closing_a_detail_returns_to_the_list_url`) all PASS when re-run in isolation — pre-existing catalog-load flake under parallel load (page shows "0 agents · 0 skills · 0 hooks"/"Loading workspace…"), not a regression; the fix only adds attributes/handlers and cannot zero a fetch. No backend/*.py changed, no restart required.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced identically on every cold-start cycle (no axis variation needed); cycle 2 additionally confirmed via real keyboard Tab-key presses (focus lands on document.body, never a card)
- **Root cause:** `Card` (`frontend/src/components/ui/Card.tsx:15-29`) is a plain, non-semantic `<div {...rest}>` wrapper; `LibraryPage.tsx:914-920`'s Hooks grid attaches `onClick` to it without `tabIndex`/`role="button"`/`onKeyDown`, so Tab skips every card — CONFIRMED via direct read.
- **Blast radius:** the same bare `Card`+`onClick` pattern, in the same file, on the Agents grid (`LibraryPage.tsx:735-758`) and the Skills tab's active-skills grid (`LibraryPage.tsx:818-848`) — both CONFIRMED by reading the code, neither yet reproduced live. Adjacent: both in-file detail modals (`SkillDetailModal`, `HookDetailModal`) have zero Escape/focus-trap/`role="dialog"` handling anywhere in the file (`grep` confirms zero matches) — INFERRED, not reproduced.
- **Fix belongs:** at each of the three `<Card onClick=...>` call sites in `LibraryPage.tsx` (add `role="button" tabIndex={0} onKeyDown` for Enter/Space, matching the idiom already used elsewhere in this codebase — e.g. `ArtifactCard.tsx:120-128`, `ChatSessionItem.tsx`), not inside `Card` itself (which is correctly non-semantic and used non-interactively elsewhere, e.g. `AccountSettings.tsx`, `admin/page.tsx`).
- **Issue cards:** [ISS-222](../.knowledge/cards/20260828-1534-ISS-222.md) (root: Hooks tab),
  [ISS-270](../.knowledge/cards/20260828-1850-ISS-270.md) (sibling: Agents tab, same pattern),
  [ISS-271](../.knowledge/cards/20260828-1851-ISS-271.md) (sibling: Skills tab, same pattern),
  [ISS-272](../.knowledge/cards/20260828-1852-ISS-272.md) (sibling: detail modals lack Escape/focus management)
- **Fixed:** 2026-08-28 — [FIX-333](../.knowledge/cards/20260828-2131-FIX-333.md); `frontend/src/components/library/LibraryPage.tsx` only: one `CARD_KEYBOARD_PROPS` object spread into all three grids (beta agent cards excluded — their onClick is already a no-op) and one `useDetailModalKeyboard` hook giving both detail modals Escape, `role="dialog"`/`aria-modal` and focus-on-open. `Card.tsx` deliberately untouched.
- **Fix verified:** `tests/integration/e2e/suites/08_library/test_library_keyboard.py` — 4/4 XPASS(strict) (xfail markers left in place for 6-verifier)
- **Found at:** 2026-08-28 02:55 UTC
- **Found by:** bug-library-hooks-r1
- **Fingerprint:** `/library?tab=hooks|hook-card-grid|tab-key-navigation|cards-unreachable-and-unactivatable-via-keyboard`
- **Evidence:** `bug-hunter/evidence/library-hooks/BUG-20260828-025521-library-hooks/`

### Summary
The Hooks tab's page copy reads "8 hooks · tap any item to see its capabilities", and the only
way to view a hook's detail (trigger, when-it-fires, compatible agents) is to open its card —
but the cards are plain, unstyled interactive `<div class="cursor-pointer p-4">` elements with
no `tabindex`, no `role="button"`, and no keydown handler for Enter/Space. This is true for all
8 cards without exception (verified via direct DOM inspection, not just visual/click testing).
A keyboard-only user (or anyone relying on Tab to navigate, including many assistive-tech users)
cannot reach or open any hook's detail on this page at all — Tab skips straight from the search
box, past the category-filter pills, past the entire 8-card grid, to the next focusable element
on the page (a top-nav button). There is no keyboard equivalent for the page's core interaction.

### Reproduction
1. Sign in as qa-admin, navigate to `/library?tab=hooks` (8 hook cards render normally, each
   visually styled with `cursor: pointer`, implying interactivity).
2. Run `document.querySelectorAll('.cursor-pointer.p-4')` in the page and inspect each card's
   `tabindex`, `role`, and `onkeydown` — all 8 return `tabindex: null`, `role: null`,
   `onkeydown: false`.
3. Focus the search input (`input[name='library-search']`) and press Tab repeatedly: focus
   moves through the search box, the Agents/Skills/Hooks tabs, and the 5 category pills, then
   jumps straight past the entire card grid to the top navigation bar — never landing on any
   card.
4. Confirm the same absence of `role`/`tabindex` holds for every card (Design Quality Check X,
   Quality Gate, Config Protection, GateGuard: Fact Force, Session Context Loader, Console.log
   Check, Format + Typecheck on Stop, Session State Persistence) — this is not a single-card
   fluke, it's the shared card component.

### Expected
Each hook card should be reachable via Tab and activatable via Enter/Space (e.g. rendered as a
`<button>`, or a `<div role="button" tabindex="0">` with a keydown handler), consistent with the
page's own instruction ("tap any item to see its capabilities") and with the fact that this is
the only affordance to view a hook's trigger/event/compatible-agents detail.

### Actual
Every hook card is keyboard-unreachable and keyboard-unactivatable; opening a hook's detail is
possible only via mouse/touch click.

### Evidence
- Before (card grid, normal render): `bug-hunter/evidence/library-hooks/BUG-20260828-025521-library-hooks/01-before-cards-visible.png`
- DOM inspection detail: `bug-hunter/evidence/library-hooks/BUG-20260828-025521-library-hooks/notes.md`

### Browser Signals
- Console: no relevant error observed.
- Network: not applicable — purely a client-side markup/interaction-model gap.
- State/URL: URL/tab state unaffected; the defect is in the DOM semantics of the card elements
  themselves (no `tabindex`, no `role`, no keyboard handler on `.cursor-pointer.p-4`).

## BUG-20260828-025950-library-agents-id — Library agent detail's "Save agent" Config override silently discards the change with no API call

- **Page:** Library — agent detail
- **Route:** /library/agents/<agentId> (e.g. /library/agents/material-analyzer)
- **Severity:** Medium
- **Status:** ESCALATED
- **Escalated:** 2026-08-29 by 5-fixer — NO code changed. The fix direction is a product decision
  the cards deliberately leave open, and the shipped test admits only the direction ISS-392
  advises against. ISS-392's "Where the fix belongs" frames it as a binary: **(a)** gate the
  Config-tab Model/Validator/Gate/Retry levers + "Save agent" READ-ONLY when no durable sink
  exists — matching the two precedents already in `AgentsPopup.tsx` (`AgentPromptSection`'s
  `surfaceOnly`, the Skills tab's `onSkillsChange` gate) — which the card calls the proportionate
  direction, since `MOD-frontend-src-components-library` documents `LibraryPage` as having "no
  server state"; or **(b)** build durable per-agent overrides as a real feature. Confirmed today
  that (b) needs a NEW backend endpoint: the only per-agent durable write in
  `backend/app/api/agents.py` is `/{agent_id}/prompt`, and `model_overrides` exists ONLY
  workflow-scoped (`app/models/workflow_definition.py:67`) and run-scoped
  (`app/models/run_capabilities.py:31`) — there is no per-user, per-catalog-agent sink.
  (`/api/settings/preferences` is a single GLOBAL `preferred_model` on `User`; writing a per-agent
  lever into it would be a worse bug.) And storing the override without also applying it at launch
  (`run_commands.py`'s `_validate_model_overrides` path) only moves the lie one layer down, so (b)
  is a feature, not a fix. `tests/integration/e2e/suites/08_library/test_iss287_agent_config_save_persists.py`
  asserts (b) in both scenarios — a PUT/POST/PATCH must fire, and the value must survive a fresh
  navigation — so direction (a) leaves both tests xfailing (under (a) the "Save agent" button the
  second scenario clicks no longer exists). Per the 5-fixer contract the test is NOT rewritten to
  match a direction the fixer picked. Needs a human call between (a) and (b); (a) would also close
  ISS-393 and is the same decision as the still-open ISS-318 one tab over.
- **Tests run (2026-08-29, no fix applied):**
  `tests/integration/e2e/suites/08_library/test_iss287_agent_config_save_persists.py` -> 2 xfailed.
  Both reach their asserts (neither fails on a locator), so the defect is live and the test file
  is executable as written — only its asserted direction is contested.
- **Root cause re-verified 2026-08-29 (5-fixer, source read):** ISS-392's mechanism still holds
  against current code — `LibraryPage.tsx:1030-1050` DOES pass `onSelectionsChange`, into
  `savedSelectionsRef` (a `useRef`, `:654-657`); the cold-mount/deep-link path (`:589-597`) never
  seeds `savedSelections`; `AgentsPopup.tsx` has no network call for Config-tab selections (every
  `/api/` hit is a comment or the `/api/capabilities` read); `AgentCapabilitiesModal` still has
  exactly 2 production call sites (`LibraryPage.tsx:1030`, `AgentLibrary.tsx:335` — the card says
  `:332`, line drift only).
- **Validated:** 3/3 on 2026-08-28, cycle 1 (deep-link cold load) — reproduced identically on
  cycle 2 (click-through entry via Configure →) and cycle 3 (different override value, Opus 4.5)
- **Found at:** 2026-08-28 02:59 UTC
- **Found by:** bug-library-agents-id-r1
- **Fingerprint:** `/library/agents/<id>|agent-detail-config-tab-save|change-model-then-save|change-not-persisted-no-network-call`
- **Evidence:** `bug-hunter/evidence/library-agents-id/BUG-20260828-025950-library-agents-id/`
- **Root cause:** `AgentCapabilitiesModal`'s Config tab (Model/Validator/Gate/Retry levers +
  "Save agent" button, `AgentsPopup.tsx:476-793`) has NO backend endpoint reachable at all — not
  a missing prop. `LibraryPage.tsx:1040-1043` DOES pass `onSelectionsChange` (correcting
  ISS-287's claim that it doesn't), but that callback only writes into `savedSelectionsRef`
  (`LibraryPage.tsx:657`), a plain in-memory `useRef` — confirmed by grepping the whole file for
  any `fetch`/API call (none touch the Config-tab levers) and by 3 source comments
  (`AgentsPopup.tsx:265-269`, `:399-401`, `:732-735`) admitting override persistence is
  deliberately deferred. The cold-mount/deep-link path (`LibraryPage.tsx:589-597`) never even
  seeds `savedSelections`, so the Model always shows "Default" on a fresh load regardless of the
  prop wiring. The Save button always flashes "✓ Saved" and closes regardless of outcome
  (`AgentsPopup.tsx:772-793`).
- **Blast radius:** `AgentCapabilitiesModal` has exactly 2 production render call sites
  (`grep -rn "<AgentCapabilitiesModal" frontend/src/`): `LibraryPage.tsx:1030` (this bug — ref
  survives same-session, lost on reload) and `AgentLibrary.tsx:332` (worse — no
  `onSelectionsChange` passed at all, pure no-op even within a session), the latter reachable
  from 4 hosts (`app/workflow/page.tsx:67`, `AgentsPopup.tsx:2526`, `WorkflowView.tsx:556`,
  `composer/ComposerPage.tsx:1368`). The Skills tab of the same `LibraryPage` drawer has the
  identical no-backend-persistence shape, independently confirmed and already carded as
  [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md).
- **Fix belongs in:** `AgentCapabilitiesModal` (`AgentsPopup.tsx:476`), once — the one shared
  component every caller routes through. Either gate the Model/Validator/Gate/Retry levers +
  Save button read-only when no durable sink exists (matching the precedent already used for
  `AgentPromptSection`'s `surfaceOnly` and the Skills tab's `onSkillsChange`-presence gate), or
  add a real backend endpoint and wire `effectiveOnSelectionsChange` through it once here.
- **Issue cards:** [ISS-392](../.knowledge/cards/20260828-2250-ISS-392.md) (root — corrects
  ISS-287's mechanism), [ISS-287](../.knowledge/cards/20260828-1712-ISS-287.md) (superseded —
  original symptom/repro, still valid), [ISS-393](../.knowledge/cards/20260828-2251-ISS-393.md)
  (sibling: `AgentLibrary.tsx`'s picker, INFERRED — not yet independently reproduced),
  [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md) (related, pre-existing, CONFIRMED:
  same-shape defect on the Skills tab of the same drawer)

### Summary
The agent detail drawer's Config tab (reached via any agent's "Configure →" affordance on
`/library`, e.g. the Architecture Agent at `/library/agents/material-analyzer`) presents a
"Model" override selector, a "Reset" button, and a "Save agent" button, with the caption
"Overrides for this agent. Defaults inherit from the workflow." Changing the Model from
"Default" to any other option (e.g. "Claude Sonnet 4.5") and clicking "Save agent" fires no
network request whatsoever — no PUT/POST/PATCH to any agent or config endpoint. The button
simply closes the drawer, navigating back to `/library`. Reopening the same agent's detail and
Config tab shows the Model reverted to "Default" — the edit was silently discarded. The button
gives no error, no toast, and no visual difference from a successful save, so a user has no way
to know their override was never applied. This was reproduced twice (once via UI click sequence
capture, once via a clean isolated repro run) with identical results both times.

### Reproduction
1. Sign in as qa-admin, go to `/library`, Agents tab.
2. Open any agent via its "Configure →" affordance (e.g. Architecture Agent,
   `/library/agents/material-analyzer`).
3. Click the "Config" tab in the drawer.
4. Click the "Model for <Agent>" dropdown and select any non-Default option (e.g. "Claude
   Sonnet 4.5").
5. Click "Save agent".
6. Observe: the drawer closes, URL returns to `/library`; check Network requests since the
   click — none were fired.
7. Navigate back to `/library/agents/material-analyzer`, open Config tab again.
8. Observe: Model shows "Default" again — the change from step 4 is gone.

### Expected
Either the Model override is actually persisted (a network call is made and the value survives
a reload), or, if per-agent overrides genuinely only make sense inside a specific workflow
context (as the caption "Defaults inherit from the workflow" suggests), the library's read-only
agent-detail view should not present editable Model/Validator/Gate/Retry controls with a
functioning-looking "Save agent" button that implies the change takes effect.

### Actual
Selecting a new Model and clicking "Save agent" makes no API call, discards the edit, and
silently closes the drawer with no feedback of any kind — success or failure.

### Evidence
- Before: `bug-hunter/evidence/library-agents-id/BUG-20260828-025950-library-agents-id/01-before-model-default.png`
- Selected, before save: `bug-hunter/evidence/library-agents-id/BUG-20260828-025950-library-agents-id/02-selected-sonnet45-before-save.png`
- After Save (drawer closed): `bug-hunter/evidence/library-agents-id/BUG-20260828-025950-library-agents-id/03-after-save-drawer-closed.png`
- After reload (reverted to Default): `bug-hunter/evidence/library-agents-id/BUG-20260828-025950-library-agents-id/04-after-reload-still-default.png`

### Browser Signals
- Console: none observed
- Network: zero requests fired by the "Save agent" click (verified via
  `browser_network_requests` immediately after each of two repro runs) — only the routine
  `GET /library?_rsc=...` navigation request from the drawer closing
- State/URL: URL returns to `/library`; reopening `/library/agents/material-analyzer` → Config
  tab shows Model back at "Default"

## BUG-20260828-030430-library-skills-id — Skill IDs with no hyphen (single-word slug) silently fall back to the Library listing instead of rendering the skill detail page

- **Page:** Library — skill detail
- **Route:** /library/skills/<skillId> (single-segment ids: `accessibility`, `benchmark`, `seo`)
- **Severity:** Medium
- **Status:** UNREPRODUCIBLE
- **Found at:** 2026-08-28 03:04 UTC
- **Found by:** bug-library-skills-id-r1
- **Fingerprint:** `/library/skills/<id>|skill-detail-route-match|navigate-directly-to-a-no-hyphen-skill-id|library-listing-renders-instead-of-detail`
- **Evidence:** `bug-hunter/evidence/library-skills-id/BUG-20260828-030430-library-skills-id/`
- **Validated:** 0/3 on 2026-08-28 — cold-start deep links to all three named ids
  (`accessibility`, `benchmark`, `seo`) render the skill detail modal correctly, every time. A
  click-through entry path (list → card click) also renders correctly. The hunter's own
  "failure" screenshots (`02-failure-accessibility-falls-back.png`,
  `03-repro2-seo-falls-back.png`) show the SAME thing my repro captured: a correctly-populated
  skill detail modal (heading, description, full markdown content, "Copy content" button)
  layered on top of the still-visible library list behind it — this is the documented
  drawer-over-list quirk in `bug-hunter/velocity.json` (`pages.library.detail`: "opens as a
  DRAWER beside the still-visible list ... and pushes /library/<type>/<id>"), which applies to
  every skill id, hyphenated or not. The "only `GET /api/skills/library` fires, no per-skill
  fetch" signal cited as evidence of failure is also expected: the app resolves skill detail by
  `SKILLS.find(s => s.id === slug)` against the already-loaded bulk list
  (`frontend/src/components/library/LibraryPage.tsx:527-533`) — there is no per-skill endpoint
  for any skill, hyphenated or not, so its absence proves nothing. `parseViewPath` in
  `frontend/src/lib/routes.ts:352-375` and the cold-mount effect in `LibraryPage.tsx:511-543`
  contain no hyphen-conditional logic. Verdict: UNREPRODUCIBLE — the report appears to be a
  misreading of documented drawer-over-list behavior, not a defect. No card minted.
- **Axes swept:** entry path (deep link vs click-through from list) — both render correctly;
  network requests inspected — matches the non-failing baseline exactly. Not swept further since
  0/3 included the exact ids and exact repro steps from the report itself.

### Summary
Navigating directly to `/library/skills/<skillId>` renders the skill detail page correctly for
hyphenated ids (e.g. `windows-desktop-e2e`, `html-deck-to-pptx` — verified via a full markdown
render matching the API's `content` field byte-for-byte at the tail, plus tag chips at the
bottom). However, for the 7 skills whose id has no hyphen at all (single-word slug —
`accessibility`, `benchmark`, `emoji`, `joke`, `poet`, `rhyming`, `seo`, per
`GET /api/skills/library`), the exact same route pattern silently renders the full Library
catalog listing (Agents/Skills/Hooks tabs, all 186 skill cards, category pills) instead of that
skill's detail content. The URL bar stays on `/library/skills/accessibility` (or `/benchmark`,
`/seo`) throughout — confirmed via `location.href` — and no console error or failed network
request occurs; `GET /api/skills/library` (the list endpoint, not a per-skill fetch) is the only
skills-related request fired, meaning the page never even attempts to resolve `accessibility` as
a specific skill id — it just renders the list route's content under the detail route's URL.
This is a distinct failure shape from Emerging bug class 4 (unmatched/404 route silently
rendering the Dashboard): here the id is a real, valid resource that exists in the API response,
the fallback target is the Library list (not the Dashboard), and the trigger is a hyphen-free
segment specifically, not an arbitrary bad path.

### Reproduction
1. Sign in as qa-admin. From a fresh `about:blank`, navigate directly to
   `http://localhost:3000/library/skills/windows-desktop-e2e` (a hyphenated id). Confirm the
   detail page renders correctly: heading, `## Related Skills` section, "Copy content"/"Copy"
   buttons, and the page's `innerText` tail matches the API's `content` field tail exactly, plus
   the skill's tags (`windows`, `desktop`, `e2e`) rendered as chips at the bottom.
2. From a fresh `about:blank`, navigate directly to
   `http://localhost:3000/library/skills/accessibility` (a single-word, hyphen-free id that is a
   real skill per the API: `display_name: "Accessibility (WCAG 2.2)"`).
3. Observe: the URL stays `/library/skills/accessibility` (confirmed via `location.href`), but
   the rendered content is the full Library catalog page — "94 agents · 186 skills · 8 hooks ·
   tap any item to see its capabilities" header, the Agents/Skills/Hooks tab pills, all 9
   category pills, and a full grid of skill cards starting with "Accessibility (WCAG 2.2)" as
   just the first list card, not a detail view.
4. Confirm no console error and no failed network request; the only skills-related request fired
   on this load is `GET /api/skills/library` (the bulk list endpoint), not a per-skill lookup.
5. Repeated the exact sequence (fresh `about:blank` → direct navigation) with two more
   independent single-word ids: `benchmark` and `seo`. Both reproduce identically — URL stays on
   the `/library/skills/<id>` detail path, content is the full Library listing page.

### Expected
`/library/skills/accessibility`, `/library/skills/benchmark`, and `/library/skills/seo` should
render each skill's own detail page (heading, description, full markdown content, tags,
"Copy content"/"Copy" controls), exactly as every hyphenated skill id does.

### Actual
For every skill whose id contains no hyphen, the detail route silently renders the Library
catalog listing page instead, under the correct detail URL, with no error, no redirect, and no
indication to the user that the specific skill they intended to view was never resolved or
rendered.

### Evidence
- Before (hyphenated id `windows-desktop-e2e`, detail renders correctly): `bug-hunter/evidence/library-skills-id/BUG-20260828-030430-library-skills-id/01-before-hyphenated-id-works.png`
- Failure (`accessibility`, library listing renders under the detail URL): `bug-hunter/evidence/library-skills-id/BUG-20260828-030430-library-skills-id/02-failure-accessibility-falls-back.png`
- Reproduced independently (`seo`, same fallback): `bug-hunter/evidence/library-skills-id/BUG-20260828-030430-library-skills-id/03-repro2-seo-falls-back.png`

### Browser Signals
- Console: no errors logged in any of the three failing cases.
- Network: only `GET /api/skills/library` (the bulk list) fires; no failed request, no per-skill
  fetch attempt observed, confirmed via `browser_network_requests` on each failing navigation.
- State/URL: `location.href` remains the correct `/library/skills/<id>` detail path in every case
  (confirmed via direct `location.href` reads), while the rendered DOM content is the Library
  listing page's markup, not the detail page's.

## BUG-20260828-030700-library-hooks-id — Hook detail's "Compatible agents" list references nonexistent agent ids not found in the Agents library

- **Page:** Library — hook detail
- **Route:** /library/hooks/<hookId> (reproduces on 6 of the 8 hooks: `post-design-quality`, `session-start`, `stop-console-log`, `stop-format-typecheck`, and more)
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 03:07 UTC
- **Found by:** bug-library-hooks-id-r1
- **Fingerprint:** `/library/hooks/<id>|compatible-agents-list|render-hook-detail-page|list-contains-agent-ids-absent-from-agents-library`
- **Evidence:** `bug-hunter/evidence/library-hooks-id/BUG-20260828-030700-library-hooks-id/`
- **Validated:** 3/3 on 2026-08-28, cold start each cycle — deterministic per hook, no narrowing needed (post-design-quality, session-start, stop-console-log all reproduced cycle 1)
- **Root cause:** `backend/app/agents/hooks_catalog.py:103` loads each hook's `compatible_agents`
  straight from `HOOK.md` YAML frontmatter (`compatible_agents=list(metadata.get("compatible_agents", []))`)
  with zero cross-validation against the live agent roster (`agents.registry.get_all_agents_flat()` /
  `backend/agents/prompts/`). 5 of 8 `HOOK.md` files under `backend/hooks/global/` still list agent ids
  that were renamed or retired (`html-prototype-builder`, `prototype-polisher`, `ppt-slide-architect`,
  `requirements-analyst` — confirmed absent from all 94 real agent ids by direct comparison) and were
  never updated. `frontend/src/hooks/useHooksCatalog.ts:29` forwards the array unchanged to every
  consumer; `LibraryPage.tsx:441,455` renders it verbatim as the reported chips + "How to use" prose.
- **Blast radius:** every consumer of `useHooksCatalog()`'s `compatible_agents` field — not just
  `LibraryPage.tsx` (reported). `frontend/src/components/workflow/composer/CanvasConfigRail.tsx:379`
  and `frontend/src/components/workflow/AgentsPopup.tsx:593` both filter `HOOKS` by
  `h.compatible_agents.includes(agent.id)` with no fallback (unlike the equivalent skills filter,
  `AgentSkillsPicker.tsx:71`, which explicitly treats empty/no-match as "compatible with everything").
  Same stale ids therefore also silently drop a hook from the composer's "Suggested hooks" panel for
  whichever real agent inherited the stale id's role — a functional gap, not just a cosmetic one.
  Filed as [ISS-399](../.knowledge/cards/20260828-2308-ISS-399.md) (INFERRED, not yet reproduced live).
- **Fix belongs:** upstream of every renderer — either (a) validate `compatible_agents` at load time in
  `hooks_catalog.py`'s `_load_one()` against `agents.registry.get_all_agents_flat()` and drop/flag
  unresolvable ids there so both the display and filter consumers inherit the fix, or (b) correct the
  5 stale `HOOK.md` files directly. A frontend-only fix in `LibraryPage.tsx` would leave
  `CanvasConfigRail.tsx`/`AgentsPopup.tsx`'s suggestion filter still silently broken.
- **Issue cards:** [ISS-290](../.knowledge/cards/20260828-1720-ISS-290.md) (root),
  [ISS-399](../.knowledge/cards/20260828-2308-ISS-399.md) (sibling: composer "Suggested hooks" filter,
  same stale ids, INFERRED)
- **Fix card:** [FIX-360](../.knowledge/cards/20260829-0024-FIX-360.md)
- **Fixed:** 2026-08-29 — root cause fixed at the single choke point every consumer routes
  through: `backend/app/agents/hooks_catalog.py` now builds the live agent id set once per
  scan from `agents.registry.get_all_agents_flat()` (the same source `GET /api/agents/library`
  serves) and `_load_one` keeps only declared `compatible_agents` present in it, warning on the
  dropped ones. Fixes ISS-290's chips/prose AND stops `CanvasConfigRail.tsx:379` /
  `AgentsPopup.tsx:593` filtering on a fictional id. No hook degrades to an empty list.
  ISS-399's remaining half — re-pointing the 5 stale `HOOK.md` files at the agents that
  inherited those roles — is a data decision, deliberately left to that card.
- **Verified:** 2026-08-29 — `backend/tests/agents/test_hooks_catalog_agent_ids.py::test_every_hooks_compatible_agents_id_is_a_real_agent`
  ran XPASS(strict) before the fix and plain-green (1 passed) after the `xfail` marker was
  removed; regression file `tests/unit/test_skills_catalog_compatible_agents.py` (6 passed);
  `cd backend && lint-imports` unchanged at "3 kept, 1 broken" (pre-existing, does not name
  `hooks_catalog.py`). Manual re-run in lane4 Chrome as `qa-admin`, light theme, fresh nav each
  time: `/library/hooks/post-design-quality` now shows only `app-ux-design`;
  `/library/hooks/session-start` no longer lists `requirements-analyst`
  (`domain-analyst, app-user-stories, epic-architect, app-code-generator`);
  `/library/hooks/stop-console-log` no longer lists `html-prototype-builder`
  (`app-code-generator, app-feature-implementation`). No console errors/warnings on any page.
  Backend is a pure `*.py` change; `:8000/docs` confirmed 200, no restart needed beyond
  `--reload`. After screenshots:
  `bug-hunter/evidence/library-hooks-id/BUG-20260828-030700-library-hooks-id/03-post-design-quality-after-fix.png`,
  `04-session-start-after-fix.png`, `05-stop-console-log-after-fix.png`.

### Summary
Each hook detail page renders a "Compatible agents" section (sourced directly from the backend's
`compatible_agents` array on `GET /api/hooks/library`, verified byte-for-byte against the
rendered chips) that is meant to tell a user which agents this hook can meaningfully be attached
to. For most hooks, one or more of the listed agent ids do not correspond to any real agent in
`GET /api/agents/library` — the ground-truth catalog of the app's 94 agents. Cross-checking all 8
hooks' `compatible_agents` against the real agent id set shows: `post-design-quality` lists
`html-prototype-builder`, `prototype-polisher`, and `ppt-slide-architect` — none exist (the app
has no agent by any of those ids); `session-start` and `stop-session-end` both list
`requirements-analyst` — does not exist (the closest real agent is `chat-requirements`);
`stop-console-log` lists `html-prototype-builder` — does not exist; `stop-format-typecheck` lists
both `html-prototype-builder` and `prototype-polisher` — neither exists. Only `post-quality-gate`,
`pre-config-protection`, and `pre-gateguard` have compatible-agent lists that are fully valid.
The chips themselves are plain non-interactive `<div>`s (confirmed via DOM inspection: no `<a>`
wrapper, no `onclick`, default `cursor: auto`) — a user cannot click through to verify, so the
stale/fictional names are simply presented as fact. This directly misleads a user deciding which
agent to attach a hook to via the documented "Advanced → Skills & Hooks panel" workflow described
in the same page's "How to use" section.

### Reproduction
1. Sign in as qa-admin. Fetch the ground truth: `GET /api/agents/library` (94 real agent ids) and
   `GET /api/hooks/library` (8 hooks, each with a `compatible_agents` array).
2. Navigate to `http://localhost:3000/library/hooks/post-design-quality`. Observe the "Compatible
   agents" section renders four chips: `app-ux-design`, `html-prototype-builder`,
   `prototype-polisher`, `ppt-slide-architect`.
3. Confirm via the API dump that `app-ux-design` is a real agent, but `html-prototype-builder`,
   `prototype-polisher`, and `ppt-slide-architect` are absent from the full 94-agent list — no
   agent by those ids exists anywhere in the app.
4. Navigate to `http://localhost:3000/library/hooks/session-start`. Observe "Compatible agents"
   renders `domain-analyst`, `requirements-analyst`, `app-user-stories`, `epic-architect`,
   `app-code-generator`. Confirm `requirements-analyst` does not exist in the real agent list
   (verified: only `chat-requirements` exists, a different id).
5. Confirm the chips are non-interactive: `document.evaluate` on the chip container's children
   shows plain `DIV` elements with no `<a>` ancestor, no `onclick` handler, and `cursor: auto` —
   there is no way to click through and discover the mismatch from the UI itself.
6. Repeated the cross-check programmatically for all 8 hooks: `stop-console-log` and
   `stop-format-typecheck` also reference `html-prototype-builder`/`prototype-polisher`, the same
   nonexistent ids — a systemic data-integrity issue in the hooks library's seed data, not a
   one-off typo.

### Expected
Every agent id listed in a hook's "Compatible agents" section should correspond to a real,
resolvable agent in the Agents library, so the guidance is actionable and trustworthy.

### Actual
Six of the eight hooks list one or more agent ids (`html-prototype-builder`, `prototype-polisher`,
`ppt-slide-architect`, `requirements-analyst`) that do not exist anywhere in the 94-agent Agents
library, presented as plain unlinked text with no way for the user to discover the mismatch short
of independently checking the API.

### Evidence
- `post-design-quality` detail showing the 3 fictional agent chips: `bug-hunter/evidence/library-hooks-id/BUG-20260828-030700-library-hooks-id/01-post-design-quality-fake-agents.png`
- `session-start` detail showing the `requirements-analyst` fictional chip (second, independent repro): `bug-hunter/evidence/library-hooks-id/BUG-20260828-030700-library-hooks-id/02-session-start-fake-agents-repro.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/hooks/library` and `GET /api/agents/library` both return `200 OK`; the
  mismatch is a data-content issue between the two payloads, not a request failure.
- State/URL: URL stays on the respective `/library/hooks/<id>` detail path throughout; confirmed
  via direct DOM query that the rendered chips are non-interactive plain `<div>`s.

## BUG-20260828-031200-settings-ai-model — Pipeline model selector enforces no tier restriction; a basic-tier account can select and persist the most expensive "powerful" models

- **Page:** Settings — AI Model
- **Route:** /settings/ai-model
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `tests/integration/e2e/suites/09_settings/test_settings.py -k model` (backend .venv):
  `test_basic_tier_cannot_persist_a_powerful_model` ran XPASS(strict) before the xfail marker was
  removed, plain green (6/6, incl. the 3 other model-tab scenarios) after. Manual repro re-run by
  hand in lane5 Chrome as `qa-basic@flowinqa.com`, cold session: selected "Claude Opus 4.6 ·
  powerful" on `/settings/ai-model`, clicked Save — page showed "This model requires Pro or
  higher. Upgrade your plan to unlock it." (the `can_use_model` 403's `detail`), selection stayed
  "Unsaved", and a full reload confirmed the select reverted to "System Default (Claude Haiku
  4.5)" — the premium model never persisted. `GET /api/settings/preferences` still lists all 9
  models unfiltered (documented as intentional in FIX-361 — visibility isn't the security
  boundary, persistence is). No new console errors on the page. `backend/lint-imports`: 3 kept /
  1 broken, same pre-existing "kernel imports only capability ports" break FIX-361's card
  documents (unrelated files, not touched by this fix). Frontend `tsc --noEmit` has pre-existing
  unrelated errors in `HomeLaunchGrid.crossAccountLeak.test.tsx` /
  `listenerMiddleware.test.ts` (outside this fix's changed files — `entitlements.py`/
  `settings.py` only, no frontend file touched). Full `test_settings.py` file also run: 2
  unrelated pre-existing XPASS(strict) failures for `test_the_constitution_editor_*` — those carry
  `@pytest.mark.issue("ISS-293")`, a different open bug in this same suite file, untouched by this
  fix. Evidence:
  `bug-hunter/evidence/settings-ai-model/BUG-20260828-031200-settings-ai-model/04-after-fix-basic-opus46-403-rejected.png`.
- **Validated:** 3/3 on 2026-08-28, every cycle — no gating in either the deep-link or account-menu entry path, both premium models
- **Root cause:** No model-tier entitlement concept exists anywhere in the codebase — `entitlements.py::TIER_PIPELINES`/`can_run_pipeline` gates pipeline TYPE by tier but has no analog for MODEL selection. `settings.py`'s `AVAILABLE_MODELS` (line 46-54, a module-level projection of the full `ModelCatalog().list()`) and `_VALID_MODEL_IDS` (line 57) carry no tier parameter; `get_preferences` (305-313) returns the full catalog to every tier, `update_preferences` (316-342) validates `model_id` only against `_VALID_MODEL_IDS`, never `user.tier`. Frontend mirrors it: `AccountSettings.tsx` fetches `userTier` (124-125) but never applies it to the model `<select>` (361-376), unlike the working precedent in `HomeLaunchGrid.tsx:288` (`disabled={!allowed}`, driven by `frontend/src/lib/entitlements.ts`).
- **Blast radius:** `GET`/`PUT /api/settings/preferences` (settings.py) — every tier. CONFIRMED not cosmetic: `user.preferred_model` is read at 8 sites in `run_commands.py` (incl. `engine.execute(model_id=...)` at line 3251), so an unauthorized selection drives real Bedrock model choice/billing on every subsequent run. Sibling caller with the identical flaw: `_validate_model_overrides` (`run_engine.py:547-607`), used by run launch (`run_commands.py:2900`) and composer save/update (`user_workflows.py:566`, `807`) — same full-catalog-only check, no tier param.
- **Proposed fix:** add a tier-scoped model table (e.g. `TIER_MODEL_COST_CLASSES`) + `can_use_model(tier, model_id)` next to `can_run_pipeline` in `backend/app/core/entitlements.py`; call it from both `settings.py` (`get_preferences` filters, `update_preferences` 403s) and `run_engine.py::_validate_model_overrides` — one shared check, every downstream reader (`run_commands.py`, `user_workflows.py`) inherits it automatically.
- **Fix:** [FIX-361](../.knowledge/cards/20260829-0029-FIX-361.md) — `can_use_model(tier, model_id)` + `TIER_MODEL_COST_CLASSES` in `backend/app/core/entitlements.py`, called from `update_preferences` (`backend/app/api/settings.py`) which now 403s. Deferred UI affordance: [ISS-430](../.knowledge/cards/20260829-0029-ISS-430.md). Sibling [ISS-398](../.knowledge/cards/20260828-2106-ISS-398.md) still open (`run_engine.py::_validate_model_overrides` untouched).
- **Issue cards:** [ISS-292](../.knowledge/cards/20260828-1918-ISS-292.md) (root), [ISS-398](../.knowledge/cards/20260828-2106-ISS-398.md) (sibling: `model_overrides` composer/launch path has the identical missing tier check)
- **Found at:** 2026-08-28 03:12 UTC
- **Found by:** bug-settings-ai-model-r1
- **Fingerprint:** `/settings/ai-model|pipeline-model-select|basic-tier-account-selects-powerful-tier-model-and-saves|no-tier-gating-anywhere-ui-or-api`
- **Evidence:** `bug-hunter/evidence/settings-ai-model/BUG-20260828-031200-settings-ai-model/`

### Summary
The Pipeline Model selector on /settings/ai-model presents all 9 catalog models — including the
two "powerful" (premium/most expensive) tier models, Claude Opus 4.5 and Claude Opus 4.6 — to
every account with no differentiation by subscription tier whatsoever: no lock icon, no "upgrade
to unlock" copy, no disabled option, no tier badge on the option itself (contrast each option's
own `tier` metadata: "fast"/"balanced"/"powerful" is shown as descriptive text, not as a gate).
Confirmed both at the API and the UI: `GET /api/settings/preferences` for a `qa-basic` tier
account (`tier: "basic"`) returns the identical 9-model `available_models` catalog as the
qa-admin/enterprise account, and `PUT /api/settings/preferences` with
`preferred_model: "eu.anthropic.claude-opus-4-6-v1"` (the single most expensive/most capable
model in the catalog) is accepted with a plain `200 OK` and persists — no 403, no validation
error, no downgrade. The same is reproducible end-to-end through the real UI as the basic-tier
user: selecting "Claude Opus 4.5 · powerful" from the dropdown and clicking "Save" succeeds
identically to selecting any other model, shows the same "Model preference saved" confirmation,
and survives a reload. This is a genuine gap in the app's own stated tier model (the app
elsewhere gates capabilities by tier, e.g. `security_gated`/`user_allowed` flags on
`/api/capabilities`, and the login response itself carries `tier: "basic"`) — the single most
consequential, cost-driving setting on this whole page has no tier enforcement at all, contrary
to what a "Pipeline model" picker on a subscription product would be expected to gate.

### Reproduction
1. Sign in as qa-admin, confirm `/settings/ai-model` lists all 9 models including "Claude Opus
   4.5 · powerful" and "Claude Opus 4.6 · powerful" with no lock/tier indicators.
2. Via API, log in as `qa-basic@flowinqa.com` / `flowin-e2e-pass` (`tier: "basic"` per the login
   response) and `GET /api/settings/preferences` — the `available_models` array returned is
   byte-for-byte identical to the admin/enterprise account's, all 9 models, no per-tier
   filtering.
3. `PUT /api/settings/preferences` as the same basic-tier account with
   `{"preferred_model": "eu.anthropic.claude-opus-4-6-v1"}` — response is `200 OK`,
   `preferred_model` is set to the Opus 4.6 id; a follow-up `GET` confirms it persisted.
4. Switch the same basic-tier session into the real UI: sign in as qa-basic in the browser,
   navigate to `/settings/ai-model` — the dropdown shows "Claude Opus 4.6 · powerful" already
   selected (the value from step 3), with no restriction badge, warning, or disabled state
   anywhere on the page.
5. From the UI, select a second premium model, "Claude Opus 4.5 · powerful", and click "Save" —
   the button is enabled (not gated), the request succeeds, and "Model preference saved"
   displays exactly as it does for any other model choice.
6. Reload `/settings/ai-model` as the same basic-tier account — "Claude Opus 4.5 · powerful"
   remains selected, confirming the change is genuinely persisted, not a stale client state.
7. Restored: basic-tier account's `preferred_model` reset to `null` (its original state) and
   qa-admin's `preferred_model` reset to `eu.anthropic.claude-haiku-4-5-20251001-v1:0` (its
   original selection) via the same API, both confirmed via a follow-up `GET`.

### Expected
A subscription-tiered product should restrict access to its most expensive/most capable models
by account tier — e.g. a "basic" tier account should not be able to select or persist "powerful"
tier models (Opus 4.5/4.6) without an upgrade path, mirroring the tier-gating pattern already
present elsewhere in the app (`/api/capabilities`'s `security_gated`/`user_allowed` flags, and
the account object's own `tier` field).

### Actual
There is no tier restriction anywhere in this flow — not in the API's model catalog, not in the
save endpoint's validation, and not in the UI's rendering of the selector. A basic-tier account
can select, save, and persist the single most expensive model in the catalog exactly as freely
as an enterprise admin account.

### Evidence
- Basic-tier account with Opus 4.6 already selected (set via API), no restriction UI present: `bug-hunter/evidence/settings-ai-model/BUG-20260828-031200-settings-ai-model/01-basic-tier-opus46-preselected-no-restriction.png`
- Basic-tier account selects Opus 4.5 via the real UI and Save succeeds normally: `bug-hunter/evidence/settings-ai-model/BUG-20260828-031200-settings-ai-model/02-basic-tier-opus45-saved-successfully.png`
- Reload confirms Opus 4.5 persisted for the basic-tier account: `bug-hunter/evidence/settings-ai-model/BUG-20260828-031200-settings-ai-model/03-basic-tier-reload-opus45-persisted.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/settings/preferences` (both accounts) and `PUT /api/settings/preferences`
  (basic-tier account, `preferred_model: eu.anthropic.claude-opus-4-6-v1` and then
  `eu.anthropic.claude-opus-4-5-20251101-v1:0`) all return `200 OK` with no tier-based rejection.
- State/URL: URL stays `/settings/ai-model` throughout; verified via direct API `GET` calls
  before and after each `PUT` that the persisted `preferred_model` for the basic-tier account
  matches the just-saved premium model, both via API round-trip and a full browser reload.

## BUG-20260828-031600-settings-usage — "Manage plan" button on Usage & Limits has no click handler at all; a basic-tier account has no way to upgrade

- **Page:** Settings · Usage & Limits
- **Route:** /settings/usage
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 (lane6) — `tests/integration/e2e/suites/09_settings/test_iss291_manage_plan_button.py`
  XPASS(strict) confirmed (13.2s), `xfail` marker removed, re-run plain green (15.6s).
  Manual repro re-run by hand: fresh cold login as `qa-basic@flowinqa.com`, nav to
  `/settings/usage`, "Basic plan" heading + "Manage plan" button visible, click opened a
  `role="dialog"` reading "Upgrade your plan — You are on the Basic plan — The Pro plan
  unlocks 2 more deliverable types. Plan changes are made by your workspace administrator
  — contact them to move this account to Pro." No console errors/warnings. Screenshot:
  `bug-hunter/evidence/settings-usage/BUG-20260828-031600-settings-usage/04-after-fix-basic-tier-modal.png`.
  Health: backend `/docs` 200; `npx tsc --noEmit` shows only the 6 pre-existing errors in
  two untouched test files (HomeLaunchGrid.crossAccountLeak.test.tsx,
  listenerMiddleware.test.ts), none in the three changed files; `lint-imports` (run from
  `backend/`) shows one pre-existing broken contract (kernel/app.api coupling), unrelated
  to this frontend-only change — not caused by it. Regression:
  `frontend/src/components/settings/AccountSettings.render.test.tsx` 8/8 passed.
  Scope note: only ISS-291 is closed here; sibling ISS-397 (AppHeader path) stays
  `verification.status: pending` per its own card — not in this bug's card list.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — no narrowing needed; reproduced identically on
  enterprise-admin warm session, basic-tier cold login, and basic-tier hard reload
- **Root cause:** no plan-management/upgrade capability exists anywhere in the codebase —
  `AccountSettings.tsx:457-459` renders the "Manage plan" `<Button>` with no `onClick` prop
  bound at all (CONFIRMED), and there is nothing to wire it to: frontend-wide grep for
  "Manage plan" returns exactly this one match, backend-wide grep for
  billing/subscription/stripe under `backend/app/api/` returns none. This is a missing
  feature, not a broken wire — the button is a visual promise with no destination built
  behind it anywhere in the app.
- **Blast radius:** `<AccountSettings>` (and its inert button) mounts at exactly one runtime
  site, `DashboardLayout.tsx:2849`, so the button itself has a single call site. But
  `AppHeader.tsx:519-526` — the persistent app shell, present on every screen — renders a
  second, independently-coded "Upgrade" CTA for basic-tier users whose `onClick` navigates
  into that same `AccountSettings` (`onNavigate("settings")`), landing the user on a page
  whose only further "upgrade" control is this same dead button (CONFIRMED by source read;
  not yet driven live — see ISS-397).
- **Fix location:** one shared component (e.g. an upgrade/contact-sales modal) that both
  `AccountSettings.tsx:457-459` and `AppHeader.tsx:519-526`'s `onClick` open directly, rather
  than each growing its own bespoke logic or the header continuing to just relocate the user
  to an equally-inert destination. A modal needs no new route (ADR-0018); a dedicated page
  would need registering through `routes.ts`. A real billing/tier-change backend is out of
  scope — `UPGRADE_PATH` in `backend/app/core/entitlements.py` only labels the next tier, it
  does not action a change.
- **Fix:** [FIX-363](../.knowledge/cards/20260829-0043-FIX-363.md) — new shared
  `frontend/src/components/settings/UpgradePlanModal.tsx`, opened by BOTH call sites: the
  "Manage plan" Button (`AccountSettings.tsx`, which had no `onClick` at all) and
  `AppHeader.tsx`'s basic-tier "Upgrade" link (which previously only navigated to that same
  inert button). The modal names the current plan, the `UPGRADE_PATH` next tier and how many
  more deliverable types it unlocks, and routes the request to a workspace admin — no billing
  backend, no new route (ADR-0018). Resolves ISS-291 (test XPASS) and ISS-397 (code fixed,
  manual click-through not yet driven — its `verification.status` stays `pending`).
- **Issue cards:** [ISS-291](../.knowledge/cards/20260828-1917-ISS-291.md) (root),
  [ISS-397](../.knowledge/cards/20260828-2105-ISS-397.md) (sibling, INFERRED: AppHeader's
  basic-tier "Upgrade" CTA leads to the same dead end)
- **Found at:** 2026-08-28 03:16 UTC
- **Found by:** bug-settings-usage-r1
- **Fingerprint:** `/settings/usage|manage-plan-button|click|no-onclick-handler-bound-no-request-no-modal-no-navigation`
- **Evidence:** `bug-hunter/evidence/settings-usage/BUG-20260828-031600-settings-usage/`

### Summary
The `/settings/usage` page's only interactive control besides the settings tabs is the "Manage
plan" button, rendered next to the plan-name heading ("Enterprise plan" for qa-admin, "Basic
plan" for qa-basic). The button is fully enabled, styled with hover/brand-accent affordances
(`text-brand`, `hover:bg-surface-warm`), and not `disabled`. Clicking it does nothing: no network
request fires (confirmed via `browser_network_requests` before/after — identical request list),
no modal/dialog opens, no navigation occurs, and the page's rendered `document.body.innerText` is
byte-identical before and after the click. Inspecting the element's React fiber props directly
shows no `onClick` handler is bound to it at all (`typeof props.onClick === 'undefined'`) — this
is not a silently-failing async handler, the button has never been wired to any handler.
Reproduces identically for both an enterprise-tier admin account (where "nothing to upgrade to"
might arguably explain a no-op, though the button should still open a plan-management view) and,
more consequentially, for a **basic-tier account** — whose plan explicitly restricts it to 2 of
8 deliverable types (per `TIER_PIPELINES["basic"]` in `backend/app/core/entitlements.py`, which
also defines a real `UPGRADE_PATH: basic -> pro`) — meaning a basic-tier user who wants to act on
the page's own stated purpose ("Your plan determines which deliverables you can run... Manage
plan") has literally no UI path to do so anywhere in the app. This is a distinct control and
distinct claim from the already-filed `BUG-20260828-031200-settings-ai-model` (model tier-gating
on a different page/component); here the defect is that the plan page's own primary CTA is
inert, not that a restriction is unenforced.

### Reproduction
1. Sign in as qa-admin (enterprise tier), navigate to `/settings/usage`. Observe "Enterprise
   plan" heading and an enabled "Manage plan" button.
2. Click "Manage plan". Observe: no dialog, no navigation (`location.href` unchanged), and
   `browser_network_requests` shows no new request fired by the click.
3. Sign out, sign in as `qa-basic@flowinqa.com` / `flowin-e2e-pass` (basic tier), navigate to
   `/settings/usage`. Observe "Basic plan" heading, "Deliverable access" listing only 2 items
   (Product Requirements, Presentation) — the other 6 pipeline types are simply absent (no lock
   badge, no explanation), and the same enabled "Manage plan" button.
4. Click "Manage plan" as the basic-tier account. Same result: no request, no modal, no
   navigation — confirmed via direct DOM read that `document.body.innerText` is unchanged and via
   `browser_network_requests` that the request list before and after the click is identical.
5. Reload to a fresh `/settings/usage` load and repeat the click a second time (basic tier) —
   identical no-op result, confirming determinism, not a one-off race.
6. Inspected the button's bound React props directly
   (`Object.keys(btn).find(k=>k.startsWith('__reactProps'))` → the click handler): `onClick` is
   `undefined` — the button has no handler wired to it whatsoever, it is a static, inert control
   styled to look actionable.

### Expected
Clicking "Manage plan" should open some plan-management/upgrade affordance (a modal, a dedicated
page, or at minimum a "contact sales" / "request upgrade" flow) — the button's own label and the
page's own copy ("Your plan determines which deliverables you can run... Manage plan") promise
this. At minimum, a basic-tier account should have some in-app path toward the `UPGRADE_PATH`
the backend already models (`basic -> pro`).

### Actual
The button is fully rendered as an enabled, clickable, styled call-to-action but has no click
handler bound to it at all. Clicking it is a complete no-op for every account tier tested,
leaving a basic-tier user with no in-app mechanism to act on the page's stated purpose.

### Evidence
- Before (enterprise admin, "Manage plan" enabled): `bug-hunter/evidence/settings-usage/BUG-20260828-031600-settings-usage/01-before-enterprise-admin.png`
- Before (basic tier, only 2 deliverable-access items, "Manage plan" enabled): `bug-hunter/evidence/settings-usage/BUG-20260828-031600-settings-usage/02-before-basic-tier.png`
- After click (basic tier, identical state, no dialog/navigation): `bug-hunter/evidence/settings-usage/BUG-20260828-031600-settings-usage/03-after-click-no-change.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `browser_network_requests` request list is identical immediately before and after the
  click, for both accounts — no request is fired by this control.
- State/URL: `location.href` stays `/settings/usage` throughout; `document.body.innerText`
  unchanged before/after click; direct React-fiber prop inspection confirms `onClick` is
  `undefined` on the button element.

## BUG-20260828-031900-settings-constitution — Constitution's "X / 4000 chars" limit is display-only; content well over 4000 chars saves and persists with no truncation or rejection

- **Page:** Settings · Constitution
- **Route:** /settings/constitution
- **Severity:** Medium
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, every cycle from a cold start (`/dashboard` -> `/settings/constitution`) — 4318-5018 char payloads all saved (200 OK) and survived reload; backend cap is 1,048,576 chars (`backend/app/api/settings.py:355`), not 4000
- **Verified:** 2026-08-29 by 6-verifier, lane5. `tests/integration/e2e/suites/09_settings/test_settings.py::test_the_constitution_editor_rejects_content_over_its_stated_limit` XPASS(strict) confirmed, `xfail` marker removed, plain green re-confirmed (3 runs total: 2 hit the documented reload-dev-server flake noted on FIX-364, 3rd ran clean — matches the fixer's own note). S-09-11 and S-09-12 both green. Manual repro re-run by hand as qa-admin in real Chrome (lane5): set textarea to 4515 chars via native setter + input event — counter read "4515 / 4000 chars" (honest, as designed), `textarea.maxLength` now `4000` (was `-1`), Save button `disabled: true`, and Playwright itself timed out trying to click it ("element is not enabled") confirming real DOM enforcement, not just a display change. Reload afterward showed the original 44-char content unchanged — nothing over-limit was ever persisted. `AccountSettings.render.test.tsx` 8/8 green. `tsc --noEmit` clean for `AccountSettings.tsx` (2 pre-existing unrelated errors in untracked `HomeLaunchGrid.crossAccountLeak.test.tsx` / `listenerMiddleware.test.ts` from other in-flight work, not this fix). `lint-imports` (run from `backend/`) shows one pre-existing broken contract (`agents.execution_engine.engine` -> `app.api`) — unrelated, FIX-364 touched zero Python files. Backend `:8000/docs` 200, frontend serving; no restart needed (frontend-only fix, Next.js hot-reload).
- **Issue card:** [ISS-293](../.knowledge/cards/20260828-1924-ISS-293.md)
- **Found at:** 2026-08-28 03:19 UTC
- **Found by:** bug-settings-constitution-r1
- **Fingerprint:** `/settings/constitution|global-instructions-textarea|type-past-4000-char-counter-and-save|no-limit-enforced-content-persists-unbounded`
- **Evidence:** `bug-hunter/evidence/settings-constitution/BUG-20260828-031900-settings-constitution/`
- **Root cause:** The "4000" is a UI-only invented constant with no backing anywhere: the counter (`AccountSettings.tsx:582`) is decorative, the `<textarea>` has no `maxLength` (589-596), `Save`'s disable check never looks at length (630: `saving || loading || !content.trim()`), and the only real enforcement is the backend's `ConstitutionRequest.content` `Field(..., min_length=1, max_length=1_048_576)` (`backend/app/api/settings.py:355`), independently mirrored by `WorkflowMemory._set`'s `_MAX_VALUE_LEN = 1_048_576` (`backend/agents/workflow_memory/memory.py:26,208-210`). `specs/001-ai-workflow-os/spec.md:224-227` (FR-012) confirms 1,048,576 chars — not 4000 — is the actual specified cap; T074a/T074b (`specs/001-ai-workflow-os/tasks.md:208-209`) only ever asked for "free-form textarea." The backend is spec-compliant; the frontend display is the lie.
- **Blast radius:** Live caller: `ConstitutionSection` in `AccountSettings.tsx` (the only reachable UI for this endpoint — confirmed via `grep -rn "settings/constitution" frontend/src`). A second wrapper, `settingsApi.getConstitution/updateConstitution/deleteConstitution` (`frontend/src/store/api/settings.ts:61-75`), duplicates the same unguarded PUT but has zero consumers anywhere in `frontend/src` — dead code today, not filed as a live sibling. Functional blast radius beyond the Settings page: the saved content is injected verbatim, unconditionally, into every governed agent's system prompt on every pipeline run via `_inject_constitution` (`backend/agents/factory.py:673-699`, called from `_compose_system_prompt:586`), with no length/token guard anywhere in that path either — filed as sibling ISS-402 (INFERRED).
- **Fix belongs:** Frontend only, in `ConstitutionSection` (`AccountSettings.tsx`) — align the displayed number, the textarea's `maxLength`, and the Save-disable check to one real cap. Do NOT change the backend's 1,048,576 limit; it is the one FR-012 actually specifies and both backend layers already agree on it. ISS-402's downstream injection-guard fix (if adopted) belongs once in `_inject_constitution`, not per-agent.
- **Issue cards:** [ISS-293](../.knowledge/cards/20260828-1924-ISS-293.md) (root — fictitious client/server limit),
  [ISS-402](../.knowledge/cards/20260828-2121-ISS-402.md) (sibling, INFERRED — same unbounded content injected into every agent prompt on every run, no size guard)
- **Tests:** `tests/integration/e2e/suites/09_settings/test_settings.py::test_the_constitution_editor_rejects_content_over_its_stated_limit` — XPASS(strict) after the fix; S-09-11 and S-09-12 still green
- **Fix cards:** [FIX-364](../.knowledge/cards/20260829-0041-FIX-364.md) (ISS-293 — one `CONSTITUTION_MAX_CHARS = 4000` behind the counter, the textarea's `maxLength` and the Save-disable check; backend's 1,048,576 cap untouched). ISS-402 is a separate card, still open.

### Summary
The Constitution editor shows a character counter styled as a hard cap ("X / 4000 chars"), and
the page copy states this constitution "is prepended to every agent on every run." Despite that,
the underlying `<textarea>` has no `maxLength` attribute, "Save constitution" never disables when
the counter exceeds 4000, and `PUT /api/settings/constitution` accepts and persists the full,
un-truncated content server-side with no length validation at all. This was reproduced twice with
different content and lengths: 4515 chars (`"A".repeat(4500) + "MARKER-END-4500"`) and 6015 chars
(`"B".repeat(6000) + "MARKER-END-6000"`) — both were accepted by the backend, both returned
`200 OK`, and both persisted verbatim (confirmed via a direct `GET /api/settings/constitution`
read of the saved `content` field, and via a full page reload showing the identical over-limit
text still loaded into the textarea with the counter reading e.g. "4515 / 4000 chars"). The "4000
chars" figure is pure decoration — it communicates a limit that does not exist anywhere in the
save path, client or server.

### Reproduction
1. Sign in as qa-admin, navigate to `/settings/constitution`. Note the existing content and the
   counter (starts at a normal in-range value, e.g. "44 / 4000 chars").
2. Programmatically set the textarea's native value to a 4515-character string (via the native
   `HTMLTextAreaElement` value setter + an `input` event, to mimic real typing) and observe the
   counter update to "4515 / 4000 chars" — over the stated limit.
3. Confirm `textarea.maxLength === -1` (no HTML enforcement) and `Save constitution` button's
   `disabled` is `false` (no client-side block).
4. Click "Save constitution". Observe `PUT http://localhost:8000/api/settings/constitution`
   returns `200 OK` and the UI shows "Constitution saved — active on all future runs."
5. Call `GET /api/settings/constitution` directly with the auth token — the returned `content` is
   the full 4515-character string, unmodified, not truncated to 4000.
6. Reload the page from scratch — the textarea loads the same 4515-character content and the
   counter still reads "4515 / 4000 chars", confirming the over-limit save is durable, not a
   client-side artifact.
7. Repeated with a second, independent value (6015 characters, different filler character and
   marker) — identical result: `200 OK`, full 6015 characters persisted and readable back from the
   API.
8. Restored the original constitution content (`"E2E S-09-12: answer in exactly one sentence."`)
   and saved, confirmed via `GET /api/settings/constitution` that the original text is back
   exactly.

### Expected
Either the client should prevent saving past 4000 characters (disable Save, or truncate/reject
locally) and the server should enforce the same limit (422/400 on an over-limit payload), so the
displayed counter reflects a real constraint — or, if there genuinely is no limit, the counter
should not be presented as "X / 4000 chars" in a way that implies a hard cap.

### Actual
The counter is purely cosmetic: content far beyond 4000 characters (tested up to 6015) is
accepted by both the client (Save stays enabled) and the server (`200 OK`, persisted verbatim,
survives reload), with no truncation, warning, or rejection at any layer.

### Evidence
- Before (original content, 44/4000 chars): `bug-hunter/evidence/settings-constitution/BUG-20260828-031900-settings-constitution/01-before.png`
- Failure (4515 chars entered, counter over limit, Save still enabled): `bug-hunter/evidence/settings-constitution/BUG-20260828-031900-settings-constitution/02-over-limit-save-not-disabled.png`
- After reload, still 4515 chars persisted: `bug-hunter/evidence/settings-constitution/BUG-20260828-031900-settings-constitution/03-after-reload-still-4515.png`
- Second independent repro, 6015 chars saved: `bug-hunter/evidence/settings-constitution/BUG-20260828-031900-settings-constitution/04-repro2-6015-chars-saved.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `PUT /api/settings/constitution` returns `200 OK` for both over-limit payloads (4515
  and 6015 chars); `GET /api/settings/constitution` echoes the full un-truncated content back in
  both cases.
- State/URL: URL stays `/settings/constitution` throughout; `textarea.maxLength` confirmed `-1`
  (unset) via direct DOM read; original content restored and verified via API before finishing.

## BUG-20260828-032424-settings-security — Security tab tells break-glass admin their credentials are "managed outside the application" when this app manages them itself

- **Page:** Settings — Security
- **Route:** /settings/security
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28T03:24:24Z
- **Found by:** bug-settings-security-r1
- **Fingerprint:** `/settings/security|mfa-unavailable-message|view-as-local-break-glass-account|copy-falsely-claims-external-credential-management`
- **Verified:** 2026-08-29. `backend/tests/unit/test_iss401_reset_password_message.py` and
  `tests/integration/e2e/suites/09_settings/test_iss404_security_copy.py` both XPASS(strict)
  before the `xfail` marker was removed, plain green after. Regression: S-09-13
  (`test_mfa_is_unavailable_for_an_externally_managed_account`) and S-11-17/S-11-18
  (`test_admin.py`, reset-password refusal) all green in isolation. Manual re-run of the
  original repro in the browser (qa-admin, cold `/settings/security`, `GET /api/auth/mfa` →
  `supported: false`) shows the corrected copy: "This is a local account, so there are no
  second-factor methods to manage here. Its password is stored by this application and can be
  changed from the Profile tab." — no "managed outside the application" text anywhere on the
  page, no console errors. Screenshot:
  `bug-hunter/evidence/settings-security/BUG-20260828-032424-settings-security/03-after-fix-security-tab-corrected-copy.png`.
  `lint-imports` unchanged (3 kept / 1 broken, pre-existing, neither edited file touches
  imports). `tsc --noEmit` shows no errors in either changed file (pre-existing unrelated
  errors in `HomeLaunchGrid`/`listenerMiddleware` test files, untouched by this fix).
- **Evidence:** `bug-hunter/evidence/settings-security/BUG-20260828-032424-settings-security/`
- **Validated:** 3/3 on 2026-08-28, cold start every cycle (fresh login + cleared storage) — unconditional, no trigger needed; entry path (deep link vs tab click-through) does not matter
- **Root cause:** `SecuritySection.tsx:233-243`'s `!status.supported` branch hardcodes a "managed outside the application" explanation for a condition (`auth.py:925-933`, `user.auth_provider != "cognito"`) that only ever means break-glass/local (`user.py:55-57`) — and that account type's `password_hash` is this app's own DB column, verified/rewritten in place by this app's own `POST /api/auth/change-password` (`auth.py:1254-1269`). CONFIRMED via file:line.
- **Blast radius:** the reported Security-tab render site (`SecuritySection.tsx:233-243`) plus one sibling carrying the identical false claim: `admin.py:553-564`'s `POST /api/admin/users/{id}/reset-password` 409 detail — same condition, same wrong wording, currently unreachable via any wired frontend caller (grepped `frontend/src` for `adminResetUserPassword`/`reset-password`: none). No other consumer of `MfaStatus`/`status.supported` exists in `frontend/src`.
- **Issue cards:** [ISS-404](../.knowledge/cards/20260828-2120-ISS-404.md) (root), [ISS-401](../.knowledge/cards/20260828-2121-ISS-401.md) (sibling: admin.py reset-password 409)
- **Fix card:** [FIX-367](../.knowledge/cards/20260828-2256-FIX-367.md) — both copy sites corrected; ISS-404 + ISS-401 resolved

### Summary
For the `qa-admin` account (a local/break-glass account, not Cognito-backed), the Security
tab shows "Not available for this account" with the explanation "This account's credentials
are managed outside the application, so two-factor authentication is configured separately."
That claim is false for this account: its password IS stored and managed by this application
(bcrypt hash in the app's own database), and can be changed from this very same settings shell
(Profile tab's "Change Password" form, backed by `POST /api/auth/change-password`'s
`auth_provider == "local"` branch). The copy is written for genuinely Cognito-backed accounts
(where credentials really are held by an external IdP) and is reused verbatim for break-glass
accounts, where the real reason 2FA is unavailable is simply "this account has no Cognito MFA
factors to manage" — a materially different, and more concerning, situation: this account has
no MFA at all, is not offloading that responsibility elsewhere, and the UI actively tells an
admin it is. The frontend source's own code comment states the real reason correctly
(`SecuritySection.tsx`: "A break-glass/local account has no Cognito factors to manage. Say so
plainly instead of rendering controls that would 501.") — but the copy actually shown does not
say that.

### Reproduction
1. Sign in as `qa-admin@flowinqa.com` (a local/break-glass admin account) and go to
   `/settings/security`. Observe: "Not available for this account" / "This account's
   credentials are managed outside the application, so two-factor authentication is configured
   separately."
2. `GET /api/auth/mfa` for this account returns `{"supported": false, ...}` — the backend's
   own docstring for that route states this response is specifically for "a non-Cognito
   (break-glass) account," not for an externally-managed one.
3. Go to `/settings/profile` on the same account. Observe a full "Password" section with
   Current password / New password / Confirm new password fields and a "Change Password"
   button — proving this application itself is the credential store for this account.
4. Cross-reference `backend/app/api/auth.py` `POST /change-password`: for
   `user.auth_provider == "local"`, it verifies `request.current_password` against
   `user.password_hash` and writes the new bcrypt hash back into this app's own `User` row —
   confirming credentials are managed entirely inside this application, not "outside" it.

### Expected
The Security tab's unavailable-MFA message should be accurate for a break-glass/local account:
something to the effect of "This is a local admin account with no two-factor authentication
configured" — not a claim that credentials are managed by an external system, since they
demonstrably are not.

### Actual
The UI shows the Cognito-account explanation ("credentials are managed outside the
application") for a local/break-glass account whose credentials are, in fact, managed entirely
inside this application — a materially false security claim on the account type this app's own
break-glass invariant depends on.

### Evidence
- Profile tab, confirming this app owns password storage/change for this account:
  `bug-hunter/evidence/settings-security/BUG-20260828-032424-settings-security/01-before-profile-change-password-form.png`
- Security tab, showing the false "managed outside the application" claim:
  `bug-hunter/evidence/settings-security/BUG-20260828-032424-settings-security/02-failure-security-tab-false-claim.png`
- API responses + source correlation: `bug-hunter/evidence/settings-security/BUG-20260828-032424-settings-security/network.log`,
  `bug-hunter/evidence/settings-security/BUG-20260828-032424-settings-security/notes.md`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/auth/mfa` → 200, `{"supported": false, ...}` for the local break-glass
  account (same response shape used to trigger the misleading copy).
- State/URL: no state change is possible here (page is read-only); observed on
  `/settings/security` with a cold deep-link and a tab-click navigation, same result both ways.

## BUG-20260828-033400-admin — Create-User dialog accepts and persists a malformed email with no @ or domain

- **Page:** Admin
- **Route:** /admin
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 03:34 UTC
- **Found by:** bug-admin-r1
- **Verified:** 2026-08-29 — `backend/tests/unit/test_admin_create_user_email_validation.py` went
  `[XPASS(strict)]`, `xfail` removed, re-run plain green (1 passed).
  `tests/integration/e2e/suites/11_admin/test_create_user_email_validation.py` went
  `[XPASS(strict)]`, `xfail` removed, re-run plain green (1 scenario, PASS). Manual repro of the
  ORIGINAL reproduction re-run by hand in lane4 Chrome as qa-admin (already signed in): opened
  "Add user", typed `not-an-email` + `abc123456` — "Create User" stayed disabled the whole time
  (was previously enabled the moment both fields were non-empty). `GET /api/admin/users`
  confirmed still exactly 4 seeded users, no malformed row persisted. Direct API bypass
  (`POST /api/admin/users {"email":"not-an-email",...}`) confirmed the backend independently
  422s: `{"detail":[{"type":"value_error","loc":["body","email"],"msg":"value is not a valid
  email address: An email address must have an @-sign."...}]}`. Health: `:8000/docs` → 200,
  `npx tsc --noEmit` shows only the same two pre-existing failures (`HomeLaunchGrid.crossAccountLeak.test.tsx`,
  `listenerMiddleware.test.ts`), none under `src/app/admin`; `lint-imports` (run from `backend/`)
  shows the identical pre-existing "3 kept, 1 broken" contract state. Regression:
  `tests/integration/e2e/suites/11_admin/test_admin.py` — 22/22 passed clean (an initial run
  showed 3 failures from an accidental concurrent duplicate run colliding on shared admin-page
  state; a clean single re-run was 22/22 green, confirming no real regression). Evidence:
  `bug-hunter/evidence/admin/BUG-20260828-033400-admin/07-after-fix-create-user-disabled.png`.
- **Fingerprint:** `/admin|create-user-dialog|submit-malformed-email|user-persisted-with-invalid-email`
- **Evidence:** `bug-hunter/evidence/admin/BUG-20260828-033400-admin/`

### Summary
The "Create New User" dialog on `/admin` performs no email-format validation, neither client-side
nor server-side. The "Create User" button only checks that the Email and Password fields are
non-empty (it stays disabled while either is blank, and becomes enabled the moment both fields
have any text). Typing a string with no `@` and no domain (e.g. `not-an-email`) into the Email
field is enough to enable submission, and the backend's `POST` to create the user accepts it
without complaint: `GET /api/admin/users` afterward shows a real, persisted user row with
`"email": "not-an-email"`. The row renders normally in the table (avatar initial "N", plan
"Basic", role "User", a real UUID and creation timestamp) as if it were a legitimate account.
This account can never be used to log in through `/login`, since nothing resembling an email was
stored, so it becomes permanently orphaned unless an admin notices and deletes it by hand.

### Reproduction
1. Sign in as qa-admin, navigate to `/admin`.
2. Click "Add user" to open the "Create New User" dialog.
3. Enter `not-an-email` (no `@`, no domain) in the Email field and any 8+ character string
   (e.g. `abc123456`) in the Password field. Leave Plan as "Basic" and "Grant admin access"
   unchecked.
4. Observe the "Create User" button is enabled (not blocked by the malformed email).
5. Click "Create User".
6. Observe the toast "User not-an-email created" and a new row in the table with that literal
   string as the email. Confirmed via `GET /api/admin/users` that the record is persisted
   server-side with `"email": "not-an-email"`.
7. Cleanup performed: deleted the throwaway user via its row's Delete action and confirmed via
   `GET /api/admin/users` that only the 4 original seeded users remain.

### Expected
The Email field should be validated as a well-formed email address before "Create User" is
enabled (client-side), and the backend's user-creation endpoint should independently reject a
value with no `@`/domain, returning a validation error rather than persisting the record.

### Actual
Both layers accept the malformed string. A new user is created and persisted with a plainly
invalid, unusable "email" value, with no error anywhere in the flow.

### Evidence
- Before: `bug-hunter/evidence/admin/BUG-20260828-033400-admin/01-before-invalid-email-entered.png`
- Failure: `bug-hunter/evidence/admin/BUG-20260828-033400-admin/02-failure-user-created-with-invalid-email.png`

### Browser Signals
- Console: none observed
- Network: `POST` to admin user-creation endpoint returned success (200-series); `GET
  /api/admin/users` confirmed persisted row `{"email":"not-an-email", "tier":"basic",
  "is_admin":false, ...}` before cleanup.
- State/URL: stayed on `/admin` throughout; no client-side validation error surfaced.

### Validation

Reproduced 3/3 from a cold start (fresh nav from `/dashboard` to `/admin` each cycle, not a
soft re-click) on 2026-08-28: `not-an-email` (cycle 1), `bademail2` (cycle 2), `bademail3`
(cycle 3) — each time the "Create User" button enabled with no format check and the record
persisted server-side, confirmed via `GET /api/admin/users`. Each cycle's throwaway user was
deleted and the user count verified back to 4 seeded users before the next cycle. No axis
variation was needed.

- **Issue cards:** [ISS-295](../.knowledge/cards/20260828-1726-ISS-295.md) (root),
  [ISS-405](../.knowledge/cards/20260828-2324-ISS-405.md) (sibling: empty-string email crashes /admin)

### Analysis

- **Root cause:** Two independent gaps, confirmed by file:line read, both on the email field only
  (password and tier ARE validated server-side; email is not):
  - Frontend: `frontend/src/app/admin/page.tsx` — `handleCreateUser` (`:212-213`) and the
    "Create User" button's `disabled` prop (`:512`) both gate on presence only
    (`!newEmail || !newPassword`), never format. The Email `<input>` carries `type="email"`
    (`:484`), but the modal is a plain `<motion.div>` (`:468`), not a `<form>` — there is no
    submit event and no `.checkValidity()`/`.reportValidity()` call anywhere in the component, so
    the browser's native HTML5 email-format constraint is never invoked. `type="email"` here is
    decorative (keyboard hint only), not a validator.
  - Backend: `backend/app/api/admin.py` — `CreateUserRequest.email: str` (`:131`) is a bare
    Pydantic `str`, not `EmailStr`. Contrast the codebase's own established pattern:
    `backend/app/models/schemas.py:15` (`RegisterRequest.email: EmailStr`) and `:22`
    (`LoginRequest.email: EmailStr`). The `create_user` handler (`:392-512`, read in full)
    independently checks duplicate email → 409 (`:409-414`), tier allow-list → 400
    (`:416-421`), and password length → 400 (`:423-427`) — but no format/shape check on email
    anywhere, so the string reaches `User(email=request.email, ...)` unchanged on both the
    local-auth path (`:434-441`) and the Cognito path (`:477-486`).
- **Blast radius:** Grepped every caller — `adminCreateUser` (`frontend/src/lib/api.ts:1475`) has
  exactly one production caller (`admin/page.tsx:218`); `CreateUserRequest` has exactly one
  consumer (`admin.py`'s own `create_user`). No sibling caller reuses either, so this is a
  single-point defect, not a shared-helper one — but pushing the same gap to its "empty string"
  boundary (still a valid `str`, still blocked only by the client's `!newEmail`, not by the
  schema) reaches `frontend/src/app/admin/page.tsx:391`'s unguarded `user.email[0].toUpperCase()`
  in the table-row avatar-initial render, which throws on `""` and — since `admin/page.tsx` has no
  local `ErrorBoundary` and isn't wrapped by `DashboardLayout` — is caught only by the root
  `frontend/src/app/error.tsx`, crashing the entire `/admin` page rather than one row. Filed as
  [ISS-405](../.knowledge/cards/20260828-2324-ISS-405.md), INFERRED (not reproduced — a direct
  API call bypassing the browser client is required to reach it).
- **Fix placement:** Belongs in the schema, not the handler body or the client alone — change
  `CreateUserRequest.email: str` to `EmailStr` (matching `schemas.py`'s existing pattern) so
  FastAPI/Pydantic rejects a malformed value with 422 before `create_user`'s body ever runs; that
  one-line schema change also closes ISS-405's empty-string path (`EmailStr` rejects `""` too).
  Client-side, either wrap the modal fields in a real `<form>` so `type="email"`'s native
  constraint fires, or add an explicit regex/format check to `handleCreateUser`'s guard and the
  `disabled` prop — the backend schema fix is the one that must not be skipped, since the client
  gate is bypassable by any direct API caller.
- **Fix card:** [FIX-366](../.knowledge/cards/20260828-2254-FIX-366.md) — `CreateUserRequest.email: str` ->
  `EmailStr` (`backend/app/api/admin.py:131`), so a malformed address is rejected with 422 before
  `create_user`'s body runs and a direct API caller is blocked too; `frontend/src/app/admin/page.tsx`
  gains one `EMAIL_PATTERN` constant used by both `handleCreateUser`'s guard and the "Create User"
  button's `disabled` prop, so the button stays disabled on a malformed address.
  `AdminUserResponse.email` (`:112`) deliberately left `str` — it is a response model, and tightening
  it would 500 on an already-persisted bad row instead of rendering it for deletion. Tests:
  `backend/tests/unit/test_admin_create_user_email_validation.py` and
  `tests/integration/e2e/suites/11_admin/test_create_user_email_validation.py` both went
  `[XPASS(strict)]`; xfail markers LEFT IN PLACE for 6-verifier. No backend restart needed beyond
  `--reload` (both changed files are `.py`/`.tsx`).
- **Deferred:** [ISS-405](../.knowledge/cards/20260828-2324-ISS-405.md) stays open — `EmailStr` closes
  its backend half (`""` is rejected too), but the unguarded `user.email[0].toUpperCase()` at
  `frontend/src/app/admin/page.tsx:391` is untouched and still crashes all of `/admin` for any
  already-persisted empty-email row.

## BUG-20260828-034200-handoff-settings — An over-length GitHub PAT is echoed back verbatim in the 422 response body and rendered raw on-page, contradicting "never returned by any API"

- **Page:** Handoff settings — GitHub PAT and API keys
- **Route:** /handoff/settings
- **Severity:** High
- **Status:** CLOSED
- **Found at:** 2026-08-28 03:42 UTC
- **Found by:** bug-handoff-settings-r1
- **Verified:** 2026-08-28 — `tests/integration/e2e/suites/16_pages_outside_routes/test_pages_outside_routes.py -k oversize`
  went `[XPASS(strict)]` for both `test_an_oversize_github_pat_is_not_echoed_in_the_422_or_rendered_raw`
  and `test_an_oversize_api_key_name_is_not_echoed_in_the_422_or_rendered_raw`; `xfail` markers removed,
  re-run plain green (2 passed). `frontend/src/lib/api.errorEcho.test.ts` (`it.fails` → `it`) re-run
  green (1 passed). `backend/tests/unit/test_register_password_echo.py` still `1 xfailed` as documented
  by ISS-357 (fixture mounts a bare `FastAPI()`, cannot see the app-level handler) — verified manually
  instead: `POST /api/auth/register {"email":"nobody@example.com","password":"short7!"}` → `422` with
  no `input` key. Manual repro of the ORIGINAL reproduction re-run by hand in lane6 Chrome as qa-admin:
  set a 5004-char synthetic `ghp_AAA...` value on `/handoff/settings`' PAT field, clicked Save,
  `PUT /api/settings/github-pat` → `422` body is now
  `{"detail":[{"type":"string_too_long","loc":["body","pat"],"msg":"String should have at most 512
  characters","ctx":{"max_length":512}}]}` — no `input` key, value not echoed — and the page renders
  the friendly `String should have at most 512 characters` text, not raw JSON. No PAT was persisted
  (page still read "No GitHub token saved yet." after). Health: `:8000/docs` → 200, frontend page →
  200, `npx tsc --noEmit` shows only the same two pre-existing failures FIX-332 documented (none in
  `src/lib/api*`), `lint-imports` (run from `backend/`) shows the identical pre-existing "3 kept, 1
  broken" contract state, unrelated to the changed files. No new console errors beyond the expected
  422 network log line already in this bug's own Browser Signals. Evidence:
  `bug-hunter/evidence/handoff-settings/BUG-20260828-034200-handoff-settings/03-after-fix-before-save.png`,
  `04-after-fix-friendly-message.png`.
- **Fingerprint:** `/handoff/settings|github-pat-save|submit-value-over-512-chars|server-echoes-full-value-in-422-body-and-frontend-renders-it-raw`
- **Evidence:** `bug-hunter/evidence/handoff-settings/BUG-20260828-034200-handoff-settings/`
- **Validated:** 3/3 on 2026-08-28, cycles 1-3 — deterministic on any PUT /api/settings/github-pat submission over 512 chars, cold start each time, no axis variation needed
- **Root cause:** No `RequestValidationError` handler anywhere in `backend/app/main.py`, so Pydantic's default 422 echoes the full rejected value (`backend/app/api/settings.py:64`, `GithubPATRequest.pat`); on the frontend, `authedJson` (`frontend/src/lib/api-handoff.ts:86-88`) and an independently-duplicated `ApiError` (`frontend/src/lib/api.ts:77-79`) both fall back to `JSON.stringify(...)` whenever `detail` isn't a plain string, and `IntegrationsCard.tsx:113-117`/`:390-393` renders that raw JSON on-page. CONFIRMED by direct file:line read; full mechanism in ISS-224.
- **Blast radius:** every `authedJson` caller in `api-handoff.ts` (8 functions, incl. `createApiKey`) shares the frontend flaw; every `api.ts` `request()`-backed page whose catch block renders `err.message` raw shares the SECOND, independent copy of it — confirmed reachable via `AccountSettings.tsx:170,417`. Backend-wide, any `Field(min_length=/max_length=...)` on a sensitive value inherits the same echo; confirmed second instance `RegisterRequest.password` (`backend/app/models/schemas.py:16`).
- **Issue cards:** [ISS-224](../.knowledge/cards/20260828-1735-ISS-224.md) (root), [ISS-264](../.knowledge/cards/20260828-1815-ISS-264.md) (sibling: createApiKey/authedJson, same page), [ISS-256](../.knowledge/cards/20260828-1816-ISS-256.md) (sibling: ApiError duplicate in api.ts, reachable via AccountSettings), [ISS-257](../.knowledge/cards/20260828-1817-ISS-257.md) (sibling: RegisterRequest.password backend echo)
- **Fix card:** [FIX-332](../.knowledge/cards/20260828-1915-FIX-332.md) — one
  `RequestValidationError` handler in `backend/app/main.py` drops Pydantic's `input` (the whole
  rejected value) from EVERY 422 on every router; `frontend/src/lib/api.ts` gains one exported
  `errorMessageFromDetail()` that both `ApiError` and `api-handoff.ts`'s `authedJson` now call,
  replacing the two independently-written `JSON.stringify` fallbacks
- **Deferred:** [ISS-357](../.knowledge/cards/20260828-1915-ISS-357.md) —
  `backend/tests/unit/test_register_password_echo.py` mounts `auth_router` on a bare `FastAPI()`,
  so an app-level handler is invisible to it and it stays xfail; ISS-257's behaviour was verified
  live instead (`POST /api/auth/register` with a 7-char password → 422 with no `input` key). The
  test was NOT edited

### Summary
The "GitHub access token" card explicitly promises "Encrypted at rest, never returned by any
API." The client places no `maxlength` on the PAT `<input>`, so a value over the backend's
512-character limit can be typed and submitted. `PUT /api/settings/github-pat` correctly rejects
it with `422 Unprocessable Entity`, but FastAPI/Pydantic's default validation-error payload
includes an `"input"` field that is the **complete, untruncated string the client submitted** —
i.e. the over-length "secret" value round-trips back from the server in plaintext inside the
error response body, directly contradicting the card's own stated guarantee. Compounding this,
the frontend has no handling for this particular error shape (it correctly extracts a friendly
message for the 400 "GitHub rejected the PAT" case, but not for a 422 list-of-errors payload):
it falls back to rendering the entire raw JSON string — literal `{"detail":[...]}`, including the
embedded `"input"` value — as plain visible page text directly under the PAT field. A real user
who accidentally pastes an oversized value (e.g. a wrong clipboard paste containing a private key
or a multi-token blob alongside their PAT) would see that value reflected back to them on-page,
and it is also present verbatim in the Network tab's response body for that request — exactly the
kind of application-side capture the card's copy tells the user cannot happen.

### Reproduction
1. Sign in as qa-admin, navigate to `/handoff/settings` (confirm "No GitHub token saved yet.").
2. Focus the GitHub PAT input and set its value programmatically (via the native input value
   setter + `input` event, to bypass no client length cap) to a synthetic 5004-character string,
   e.g. `"ghp_" + "A".repeat(5000)` — never a real credential. Confirm `input.value.length` is
   5004 (no truncation, no client-side max-length enforcement).
3. Click "Save". Observe `PUT http://localhost:8000/api/settings/github-pat` returns
   `422 Unprocessable Entity`.
4. Read the response body directly (`browser_network_request`, response-body): it is
   `{"detail":[{"type":"string_too_long","loc":["body","pat"],"msg":"String should have at most
   512 characters","input":"ghp_AAAA...<the full 5004-char string, unmodified>...AAAA",
   "ctx":{"max_length":512}}]}` — the `"input"` value is the exact, complete string submitted, not
   truncated to 512 chars or redacted in any way.
5. Read the live page via snapshot: the area below the PAT field now displays the literal raw
   JSON string above (starting `{"detail":[{"type":"string_too_long"...`), including the full
   echoed value, as ordinary visible page text — not a parsed, human-readable error message.
6. Repeated with a second, different synthetic payload (`"github_pat_" + "Z".repeat(600)`, 611
   chars) — identical result: `422`, response body's `"input"` field is the full 611-char string
   verbatim, and the frontend again renders the raw JSON (including the value) on-page.
7. Cleaned up: cleared the PAT input back to empty (no PAT was ever actually saved — every
   attempt in this investigation was rejected by validation, so "No GitHub token saved yet."
   remains true throughout and after).

### Expected
Per the card's own stated guarantee ("Encrypted at rest, never returned by any API"), a rejected
PAT value — including one rejected purely for length — should never be echoed back to the client
in any response body. The frontend should also parse this validation-error shape into a friendly,
generic message ("Token is too long (max 512 characters)") the same way it already does for the
400/GitHub-rejection case, rather than falling back to dumping raw JSON (with the embedded value)
onto the page.

### Actual
The full, untruncated submitted PAT value is present verbatim in the `422` response body's
`"input"` field, and the frontend renders that entire raw JSON blob — value included — as visible
page text, both violating the page's own "never returned by any API" claim.

### Evidence
- Before (5000+-char synthetic value typed into the PAT field): `bug-hunter/evidence/handoff-settings/BUG-20260828-034200-handoff-settings/01-before-oversize-pat-typed.png`
- Failure (raw JSON error, including the echoed value, rendered on-page after the second, 611-char
  repro): `bug-hunter/evidence/handoff-settings/BUG-20260828-034200-handoff-settings/02-failure-raw-json-echoes-secret-value.png`
- Network/response detail (value truncated in this log excerpt only — the live response is NOT
  truncated by the server): `bug-hunter/evidence/handoff-settings/BUG-20260828-034200-handoff-settings/network.log`

### Browser Signals
- Console: `Failed to load resource: the server responded with a status of 422 (Unprocessable
  Entity) @ http://localhost:8000/api/settings/github-pat`.
- Network: `PUT /api/settings/github-pat` → `422`, response body's `"input"` field is the complete
  submitted string (confirmed via `browser_network_request` response-body reads on two independent
  attempts, 5004 chars and 611 chars).
- State/URL: URL stays `/handoff/settings` throughout; no PAT was ever actually persisted (every
  attempt was rejected), so `GET /api/settings/github-pat` continues to report no token saved,
  both during and after the investigation.

## BUG-20260828-040400-workflows-nonexistent — `/workflows/<bad-id>/canvas` silently opens an empty "copy" composer instead of 404ing, letting a user save a brand-new persisted workflow from a dead link

- **Page:** Missing workflow — canvas sub-route
- **Route:** /workflows/<nonexistent-or-malformed-id>/canvas (e.g. /workflows/00000000-0000-0000-0000-000000000000/canvas, /workflows/totally-bogus-id-12345/canvas)
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `tests/integration/e2e/suites/13_errors/test_errors.py` run in full:
  the ISS-299 guard test XPASSed (strict), `xfail` marker removed, file re-run plain green for
  that test (22/23 other outcomes also PASS; 2 unrelated `Page.goto` timeouts to `/runs` on the
  first pass were shared-browser contention from concurrent bug-hunt suites, confirmed by an
  isolated re-run of just those two — both PASS alone). Manual re-repro in Chrome (lane5,
  qa-admin, light theme, cold-navigate via /dashboard, same conditions as the register/ISS-299
  entry): both the all-zeros uuid and a non-uuid bad id (`totally-bogus-id-12345`) now render the
  generic 404 with zero "Save as copy" buttons; only console entry is the expected
  `GET .../api/workflows/<bad-id> => 404`. `/workflows/ppt/canvas` (a valid built-in) still opens
  correctly with "Save as copy" present — the new gate does not fire on the valid path. Frontend
  `npm run build` succeeds; `tsc --noEmit` shows the same 9 pre-existing errors as before the fix,
  zero in `page.tsx`. Backend `/docs` returns 200 (frontend-only change, no restart needed).
  `lint-imports` (run from `backend/`) shows one pre-existing broken contract
  (`agents.execution_engine.engine` → `app.api`), unrelated to this change, not touched here.
  Regression file `suites/04_composer_canvas/test_composer_canvas.py` (20 tests): 2 failures, both
  reproduced in isolation too, both pre-existing and unrelated —
  `test_editing_a_saved_workflow_loads_its_steps` fails on `assert 3 == 4` against the shared "ppt
  override" fixture workflow's agent count (DB-state drift from concurrent bug-hunt agents
  mutating shared fixtures, not this route), and
  `test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot` fails because the test's
  own `LAST_STEP_GUARD` locator hardcodes "...replace output.md..." while the PPT built-in's real
  tooltip correctly says "...replace presentation.pptx..." — a stale test locator, not a page.tsx
  regression. Evidence: `05-after-canvas-404.png` added alongside the original before/failure
  shots in `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-040400-workflows-nonexistent/`.
- **Found at:** 2026-08-28 04:04 UTC
- **Found by:** bug-workflows-nonexistent-r1
- **Fingerprint:** `/workflows/<bad-id>/canvas|copy-composer|navigate-to-canvas-subroute-for-nonexistent-workflow|empty-composer-renders-and-save-as-copy-persists-a-real-workflow`
- **Evidence:** `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-040400-workflows-nonexistent/`
- **Validated:** 3/3 on 2026-08-28, cold start each cycle — any unresolved workflowId on `/workflows/{id}/canvas` (well-formed uuid, malformed uuid, or arbitrary string) triggers it; not id-shape or cache specific
- **Issue card:** [ISS-299](../.knowledge/cards/20260828-1730-ISS-299.md)
- **Root cause:** `frontend/src/app/[...view]/page.tsx:452-499` — the `workflow-canvas` cold-mount
  effect's `catch` (lines 494-496) is unconditional and sets `initialSavedComposition` to `null`
  on ANY `getWorkflowDetail` failure, indistinguishable from that state's own blank-composer
  default (line 391). Unlike this file's sibling cold-mount effects for `/workflows/{id}/edit`
  (`workflowEditAccessDenied`, set on a 403/404, gated by `notFound()` at line 3741-3743) and the
  bare `/workflows/{id}` route (`workflowDetailFailed`, gated by `notFound()` at line 3750-3753),
  `workflow-canvas` has no companion "not found" state and no `notFound()` gate anywhere in the
  file (confirmed by exhaustive grep of every `notFound()` call site). `ComposerPage.tsx`'s header
  (line 1020) and "Save as copy" label (line 1135) key only on the URL-derived `builtinCanvasType`
  string; the Save button's `disabled` (line 1116, `saving` only) and `handleSave` (663-762) check
  neither workflow existence nor agent count, so it always POSTs a new row via `saveUserWorkflow`.
- **Blast radius:** Producer: `page.tsx`'s single `builtinCanvasType` effect. Passthrough:
  `DashboardLayout.tsx` (prop forwarding only, no logic — confirmed by grep). Consumers:
  `ComposerPage.tsx`'s header, Save-as-copy button/`handleSave`, and (already filed/fixed
  separately as ISS-234/FIX-343) `handleRunOnce`. No other `getWorkflowDetail` caller shares the
  defect — `WorkflowDialog.tsx` correctly surfaces its error instead of swallowing it, and
  `LaunchWizard.tsx`'s fetch is for a fixed, non-URL-derived pipeline type whose core roster comes
  from elsewhere. The identical unconditional-catch mechanism was independently re-derived while
  analyzing the parallel bug `BUG-20260828-104200-workflows-nonexistent-r2` (root card ISS-234,
  fixed by FIX-343; siblings ISS-333, ISS-334) for the Run-once consequence — this bug is the
  Save-as-copy consequence of the same swallow, a distinct defect, not a duplicate.
- **Proposed fix:** Mirror `workflow-edit`'s existing pattern in the SAME file: add a companion
  state (e.g. `builtinCanvasAccessDenied`), set it in the effect's catch when
  `err instanceof ApiError && (err.status === 403 || err.status === 404)` (matching
  `page.tsx:3506-3520`'s exact check), and add one more `notFound()` gate alongside the existing
  three, keyed on `builtinCanvasTypeFor(parsedView) && builtinCanvasAccessDenied`. Belongs in
  `page.tsx` — the one catch-all component every URL already routes through (ADR-0018) — not
  duplicated inside `ComposerPage.tsx`, which has no route/`notFound()` awareness.
- **Issue cards:** [ISS-299](../.knowledge/cards/20260828-1730-ISS-299.md) (root — confirmed, not
  edited by this pass), [ISS-410](../.knowledge/cards/20260828-2344-ISS-410.md) (sibling,
  INFERRED: the same unconditional catch fires identically on a transient failure against a REAL,
  existing workflow — not just a dead one — so Save as copy can persist an unwanted duplicate for
  a workflow that was never dead; mirrors [ISS-334](../.knowledge/cards/20260828-2045-ISS-334.md),
  which already covers the same adjacent-state trigger for the Run-once consequence)

- **Fix card:** [FIX-368](../.knowledge/cards/20260829-0106-FIX-368.md) — companion
  `builtinCanvasAccessDenied` state set only on `ApiError` 403/404 in the `workflow-canvas`
  cold-mount catch (`page.tsx:521-529`), plus a fourth `notFound()` gate keyed on
  `builtinCanvasType && builtinCanvasAccessDenied` (`page.tsx:3801-3807`) alongside the
  existing three. Also filed [ISS-442](../.knowledge/cards/20260829-0106-ISS-442.md) —
  `workflowDetailCatch.source.test.ts:84` hard-codes "the shared 403/404 idiom appears
  exactly 3 times in page.tsx"; it is 5 now (one site from the in-tree ISS-380 fix, one
  from this one) and was deliberately NOT edited to make a red test green.

### Summary
Unlike the bare workflow detail route and `/edit`, both of which correctly render the generic
404 for a nonexistent or malformed workflow id (verified in this same investigation — both are
hardened), the `/canvas` sub-route does not. Loading `/workflows/<bad-id>/canvas` fires
`GET /api/workflows/<bad-id>` which genuinely 404s (confirmed in the console), but the frontend
silently swallows that failure and renders a fully interactive, empty workflow composer instead
of the 404 page — header reads `<bad-id> · copy`, "0 agents", a blank Brief field, and a "Save as
copy" button. This is not inert: typing a name into the Workflow name field, adding a real agent
via "+ Add", and clicking "Save as copy" fires `POST /api/user-workflows`, which succeeds
(`201 Created`) and returns a brand-new, real, persisted workflow with its own fresh UUID. The
new workflow then appears in "My Workflows" as a normal saved entry — a completely legitimate
user-owned resource was created by starting from a URL that should not resolve to anything at
all. This is a different mechanism from `BUG-20260828-010600-workflows-id-run` (the already-filed
class-4 defect where `/run` on a bad id silently falls back to rendering the *Dashboard*, with no
composer and no way to create anything) and from `BUG-20260828-005700-workflows-ppt-canvas`
(canvas on the real, existing `ppt` built-in losing its manifest on copy — that bug requires a
valid workflow to begin with; this one requires the workflow to *not* exist).

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/workflows/00000000-0000-0000-0000-000000000000/canvas`
   (the ledger's own resolved nonexistent uuid).
2. Observe: no 404 page. Instead a full composer renders — header
   "00000000-0000-0000-0000-000000000000 · copy", "0 agents", an empty "Workflow name" field, a
   "Save as copy" button, and a working canvas/Brief panel. Console shows
   `GET /api/workflows/00000000-0000-0000-0000-000000000000 => 404`, proving the frontend received
   the correct 404 and chose to render the copy-composer shell anyway.
3. Fill the "Workflow name" field with a real value (e.g. "DEAD LINK COPY TEST").
4. Click "Add agent", add any real agent (e.g. "Domain Discovery Agent"), close the picker.
5. Click "Save as copy". Observe `POST /api/user-workflows` returns `201 Created` with a real
   response body: a fresh UUID, the entered name, `agent_ids: ["domain-analyst"]`.
6. Navigate to `/workflows` (My Workflows). Observe the new workflow, "DEAD LINK COPY TEST",
   listed as a normal saved entry with "1 agent" — a genuine, persisted, user-owned resource.
7. Reproduced independently on a second, differently-shaped bad id:
   `http://localhost:3000/workflows/totally-bogus-id-12345/canvas` (not a uuid at all) — same
   result: the empty "copy" composer renders instead of a 404, with a working "Save as copy"
   button.
8. Cleanup: deleted the created throwaway workflow (`DELETE /api/user-workflows/<new-id>` →
   `204`) so no stray data was left behind.

### Expected
`/workflows/<bad-id>/canvas`, like the bare detail route and `/edit` for the same bad id, should
render the app's 404 page when the source workflow does not exist — the frontend already receives
a `404` from `GET /api/workflows/<bad-id>` and simply needs to act on it instead of falling
through to an empty composer shell.

### Actual
The frontend ignores the 404 from the workflow fetch and renders a fully functional "copy"
composer for a workflow that does not exist, and that composer's "Save as copy" action
successfully creates and persists a brand-new real workflow via a legitimate backend call.

### Evidence
- Before (empty copy composer renders for the all-zeros uuid, no 404): `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-040400-workflows-nonexistent/01-before-canvas-empty-composer.png`
- Failure (filled + agent added, "Save as copy" fired 201 Created): `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-040400-workflows-nonexistent/02-failure-saved-as-copy-201-created.png`
- My Workflows shows the new entry persisted: `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-040400-workflows-nonexistent/03-my-workflows-shows-persisted-entry.png`
- Reproduced on a second, non-uuid bad id: `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-040400-workflows-nonexistent/04-repro2-malformed-id-canvas.png`

### Browser Signals
- Console: `GET http://localhost:8000/api/workflows/00000000-0000-0000-0000-000000000000 => 404`
  fires and is logged as an error, but no code path reacts to it by redirecting to the 404 page.
- Network: `POST http://localhost:8000/api/user-workflows` returns `201 Created` with a real new
  workflow id and the entered name/agents — the backend has no reason to reject this since it is,
  from its perspective, a completely ordinary "create a new workflow" call with no reference back
  to the original bad id.
- State/URL: `location.href` stays on the bogus `/workflows/<bad-id>/canvas` throughout, both
  before and after the successful save (no navigation to the newly created workflow's own URL) —
  matching the app's documented pattern elsewhere of not navigating after a composer save, but
  here compounding the defect since the user has no visible confirmation their dead link just
  created a real object, only discoverable via My Workflows or the network log.

## BUG-20260828-041300-preview-fullscreen — File explorer search leaves orphaned empty folders visible and the footer file count never reflects the active filter

- **Page:** Fullscreen preview — ready state (App Builder IDE preview)
- **Route:** /preview-fullscreen (ready state, valid `__app_preview__` payload)
- **Severity:** Low
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, cold-started each cycle — reproduces immediately, no
  narrowing needed (queries `app`, `helper`, `main` against a 4-file seeded tree)
- **Verified:** `AppBuilderPreview.searchFilter.test.tsx` XPASSed all 4 cases (ISS-332 x2,
  ISS-501, ISS-502), `xfail`/`it.fails` markers removed, plain green re-run (4 passed). Manual
  re-run of the original repro on `/preview-fullscreen` with the same seeded 4-file payload:
  searching `app` now hides `styles`/`utils` (zero matching descendants) and the footer reads
  "1 files · 0.0 KB total" instead of the stale "4 files · 0.1 KB total"; searching `helper`
  hides `styles`, auto-expands `utils` to reveal `helper.js`, footer correct. No console errors.
  Backend :8000/docs 200; `npx tsc --noEmit` has pre-existing unrelated errors only (none in
  AppBuilderPreview.tsx/PreviewPanel.tsx); `lint-imports` (run from backend/) has one
  pre-existing broken contract unrelated to this frontend-only change. Regression file
  `preview/__tests__/PreviewPanel.switcher.test.tsx` — 5 passed. Sibling ISS-500 (other mount
  points) confirmed fixed at the code level and via an isolated assertion check, but its own
  test file `PreviewPanel.appBuilderSearch.test.tsx` stays `it.fails` — it is blocked by a
  separate, still-open test-code defect ([ISS-596](../.knowledge/cards/20260829-0127-ISS-596.md)),
  not by this bug.
- **Root cause:** `FileTreeNode`'s folder branch renders unconditionally with no `searchQuery`
  check — the match gate exists only in the `file` branch (`AppBuilderPreview.tsx:202-203`); the
  footer stat line reads the raw, unfiltered `files` prop with no `searchQuery` dependency at all
  (`AppBuilderPreview.tsx:556`)
- **Blast radius:** every mount point of the shared `AppBuilderPreview` component — the reported
  `/preview-fullscreen` page, `AppBuilderIDEPreview` inside `PreviewPanel.tsx:163` (embedded
  run-preview tab), and both branches of the History reopen modal, `WorkflowHistory.tsx:838`
  (`ideFiles`) and `WorkflowHistory.tsx:877` (`genericBundleFiles`)
- **Issue cards:** [ISS-332](../.knowledge/cards/20260828-2041-ISS-332.md) (root),
  [ISS-500](../.knowledge/cards/20260829-0006-ISS-500.md) (sibling: same bug in the other three
  mount points), [ISS-501](../.knowledge/cards/20260829-0006-ISS-501.md) (sibling: search never
  auto-expands a collapsed folder holding a real match), [ISS-502](../.knowledge/cards/20260829-0006-ISS-502.md)
  (sibling: zero-match query leaves the whole tree visible with no empty state)
- **Found at:** 2026-08-28 04:13 UTC
- **Found by:** bug-preview-fullscreen-r1
- **Fingerprint:** `/preview-fullscreen|app-builder-preview-file-explorer-search|type-query-matching-only-a-nested-file|parent-folders-with-zero-matching-children-remain-visible-and-expand-empty-while-footer-count-stays-unfiltered`
- **Evidence:** `bug-hunter/evidence/preview-fullscreen/BUG-20260828-041300-preview-fullscreen/`

### Summary
In `frontend/src/components/preview/AppBuilderPreview.tsx`, the file-tree search
(`FileTreeNode`) filters only leaf **files** by `searchQuery` (`if (!matchesSearch) return null;`
inside the `file` branch) — the `folder` branch has no equivalent check and is always rendered
regardless of whether any of its descendants match. Consequence: typing a search query that
matches a file nested two or more levels deep (e.g. `src/utils/helper.js`) leaves every sibling
folder that contains *no* matching files (e.g. `src/styles/`) still visible in the tree and still
clickable/expandable — expanding it renders a folder header with literally nothing underneath,
a dead-end empty branch the search should have pruned. Separately, the sidebar footer stat line
("N files · X KB total") is computed from the full unfiltered `files` array and never reflects
the active search — it continues to read the original total file count even while the visible
list is filtered down to a single match, so the UI's own count contradicts what's on screen.

### Reproduction
1. Sign in as qa-admin. Seed a realistic `__app_preview__` payload (shape read directly from
   `frontend/src/app/preview-fullscreen/page.tsx`'s `PreviewPayload` interface) via
   `sessionStorage.setItem('__app_preview__', JSON.stringify({projectName:'SearchTestProject',
   files:[{path:'index.html',...}, {path:'src/app.js',...}, {path:'src/styles/main.css',...},
   {path:'src/utils/helper.js',...}]}))`, then navigate to `http://localhost:3000/preview-fullscreen`.
   The ready-state IDE preview renders correctly (title "SearchTestProject — IDE Preview",
   4-file tree, `index.html` content shown) — noted here as the legitimate route taken since
   this round found no app-builder run in `/runs` history with a live, non-expired preview
   payload; the payload shape matches the interface the page itself defines.
2. Expand the nested `src/styles` and `src/utils` subfolders (they are not auto-expanded; only
   top-level `src` is).
3. Type `app` into the "Search files" box. Observe: `index.html` (non-matching) correctly
   disappears, `app.js` (matching) correctly remains — but the `styles` and `utils` folder rows
   also remain visible even though neither contains a file matching "app". Expanding `styles`
   confirms it renders with zero children underneath. The footer still reads "4 files · 0.0 KB
   total" despite only one file (`app.js`) being visible.
4. Reproduced with a second, independent query: cleared and typed `helper` instead. Observe
   `helper.js` (the only match, inside `utils`) correctly shows, but `styles` (no match) still
   renders as a folder row and expands to nothing; the footer is still stuck at "4 files · 0.0 KB
   total" regardless of the query.

### Expected
A folder with zero descendants matching the active search query should be hidden along with its
non-matching files (mirroring how the leaf-file filter already behaves), so an expanded search
result never shows an empty folder. The footer file/size summary should reflect the currently
visible (filtered) file set, not the unfiltered project total, while a search is active.

### Actual
Folders are never filtered by search match state — any folder that contains at least one
non-matching file (even if it contains zero matching files) stays fully visible and expandable,
rendering an empty branch when opened. The footer count is hardcoded to the full unfiltered
`files` array and never updates to reflect the active filter, contradicting the visibly reduced
file list.

### Evidence
- Before (ready state, full unfiltered tree, no search active): `bug-hunter/evidence/preview-fullscreen/BUG-20260828-041300-preview-fullscreen/01-before-search-empty.png`
- Failure (`app` search — `styles`/`utils` folders remain despite no matches, footer still "4 files"): `bug-hunter/evidence/preview-fullscreen/BUG-20260828-041300-preview-fullscreen/02-search-app-orphaned-folders.png`
- Expanding `styles` under the `app` search shows nothing inside: `bug-hunter/evidence/preview-fullscreen/BUG-20260828-041300-preview-fullscreen/03-styles-folder-expanded-shows-nothing.png`
- Reproduced with a second, independent query (`helper`), same defect: `bug-hunter/evidence/preview-fullscreen/BUG-20260828-041300-preview-fullscreen/04-repro2-helper-search-same-defect.png`

### Browser Signals
- Console: no relevant error observed.
- Network: none — filtering is purely client-side state in `AppBuilderPreview`.
- State/URL: URL stays on `/preview-fullscreen` throughout; confirmed via `browser_snapshot` DOM
  reads that folder rows persist and expand empty under an active non-matching search, and that
  the footer paragraph text never changes from the unfiltered total across two independent
  queries.

## BUG-20260828-041815-login-expired-1 — Failed-login error message renders with no ARIA live region or alert role, so screen readers never announce it

- **Page:** Login reached with a non-canonical expiry param
- **Route:** /login?expired=1 (identical DOM structure to plain /login)
- **Severity:** Low
- **Status:** CLOSED
- **Verified (6-verifier, 2026-08-29, re-verification after FIX-408):** All three checks
  green in this pass. `npx vitest run src/app/login/login.a11y.test.tsx` (frontend/) →
  `Test Files 1 passed (1) / Tests 3 passed (3)`, plain green, no `xfail`/`it.fails`
  markers present (already removed in the prior verification pass). Regression guard
  `login.reskin.test.tsx` → `Test Files 1 passed (1) / Tests 9 passed (9)`. `npx tsc
  --noEmit` from `frontend/` → 8 errors total, ALL in the three files already carved out
  as out-of-scope by FIX-408 (`HomeLaunchGrid.crossAccountLeak.test.tsx` x4,
  `api.sessionExpiryRedirect.test.ts` x2, `listenerMiddleware.test.ts` x2 — owned by
  ISS-216/ISS-322) — zero errors in this bug's file set, confirming TS2554 stays fixed.
  Manual repro re-run by hand in the browser (lane4): cleared storage, navigated to
  `/login?expired=1`, filled `wrong@flowinqa.com` / a wrong password, clicked Sign in.
  DOM evaluate confirmed the "Invalid email or password." element now carries
  `role="alert"` (was `null` before the fix) with only the expected benign 401 console
  entry — after-screenshot at
  `bug-hunter/evidence/login-expired-1/BUG-20260828-041815-login-expired-1/03-after-verify-role-alert-present.png`.
  Backend `:8000/docs` → 200, frontend `:3000/login` → 200, no restart required (frontend-
  only change, Next.js hot-reloaded). `lint-imports` (run from `backend/`) shows one broken
  contract (`agents.execution_engine.engine` -> `app.api`) — pre-existing and unrelated:
  this bug's entire changeset is `frontend/src/app/login/page.tsx` and
  `login.a11y.test.tsx`, zero backend files touched. Two consecutive full passes now
  (functional fix confirmed twice; the one prior failure was the tsc gap FIX-408 closed).
- **Reopen fixed (5-fixer, 2026-08-29):** The one health-check failure this entry was reopened
  for is closed. `frontend/src/app/login/login.a11y.test.tsx:92` now reads
  `new ApiError(401, null)` — the real exported `ApiError` (`frontend/src/lib/api.ts:93-96`,
  exported at `:653`) requires `(status, detail)`; the file's own `vi.mock` stub declares
  `detail?` optional and vitest does not type-check, which is why it ran green over a red
  build. Fixed at the call site, NOT by relaxing the app's signature — all five real
  construction sites already pass two args, and `null` was chosen over the asserted banner
  text so the assertion still proves the `status === 401` branch produced it. No assertion or
  test name changed; `page.tsx` untouched. Observed: `npx tsc --noEmit` from `frontend/` now
  reports 0 errors in this bug's file set (was 1);
  `npx vitest run src/app/login/login.a11y.test.tsx` → `Test Files 1 passed (1) / Tests 3
  passed (3)` (2.05s); regression guard `login.reskin.test.tsx` → 9 passed (1.86s). The three
  unrelated `tsc` files this entry also listed are untouched and already carded —
  `HomeLaunchGrid.crossAccountLeak.test.tsx` + `listenerMiddleware.test.ts` under
  [ISS-216](../.knowledge/cards/20260828-1643-ISS-216.md) (open),
  `api.sessionExpiryRedirect.test.ts` under
  [ISS-322](../.knowledge/cards/20260828-2007-ISS-322.md).
- **Verified (6-verifier, 2026-08-29):** The functional fix is real and confirmed — all 3
  `frontend/src/app/login/login.a11y.test.tsx` tests XPASS 3/3 across repeat runs, xfail
  markers removed and re-run plain green (`Test Files 1 passed / Tests 3 passed`), regression
  guard `login.reskin.test.tsx` stays green (9/9), and the manual repro from this entry
  (`/login?expired=1`, wrong credentials, submit) now shows `role="alert"` on the error
  element in the live browser (was `null`/`null` before) with only the expected benign 401
  console entry. The `isExpired` banner (`?expired=true`) was spot-checked the same way and
  also carries `role="alert"`. REOPENED anyway because a health check failed: `npx tsc
  --noEmit` reports `frontend/src/app/login/login.a11y.test.tsx:92:33` TS2554 — `new
  ApiError(401)` supplies only the `status` argument, but the real `ApiError` class
  (`frontend/src/lib/api.ts:97`) requires a second `detail: unknown` argument; the test
  file's local `vi.mock("@/lib/api")` stub only needs one, so it runs fine under vitest
  (which doesn't type-check) but fails `tsc`, i.e. the frontend does not build clean. This
  predates the fixer's `page.tsx` edit — it's in the test file the 4-test-writer delivered —
  but it is still this bug's own deliverable and blocks a clean build. Three other unrelated
  `tsc` errors (`HomeLaunchGrid.crossAccountLeak.test.tsx`,
  `api.sessionExpiryRedirect.test.ts`, `listenerMiddleware.test.ts`) were also present but
  are outside this bug's file set — not re-verified against a pre-change commit (shared WIP
  branch, unsafe to stash), noted here rather than claimed clean.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced on every cold-start attempt, no
  axis variation needed (also confirmed stable across mouse-click and Enter-key submit)
- **Root cause:** Hand-rolled inline JSX, not a broken shared function — the failed-login
  `{error && (<motion.div>{error}</motion.div>)}` block at `frontend/src/app/login/page.tsx:271-279`
  carries no `role`/`aria-live` and nothing moves focus to it. `components/ui/` has no
  generic alert/banner primitive this page could have used (the codebase already has the
  right pattern elsewhere — `SecuritySection.tsx:169`'s `aria-live="polite"` sr-only region,
  `AgentsPopup.tsx:2659`'s `role="alert"` span — login just never got it). NOTE: ISS-337's
  own line citation (261-268) was one block off — those lines are the neighboring
  `isExpired` banner, not this one; corrected in the analyzer refinement section.
- **Blast radius:** No cross-file callers — `login/page.tsx` is a router leaf
  (`imported_by: []`) and `register/page.tsx` has no form. Contained to 2 sibling render
  sites in the SAME file with the identical missing-attribute pattern: the `isExpired`
  session-expiry banner (lines 261-269, reached via `handleSessionExpiry()` in
  `frontend/src/lib/api.ts:175-179`) and `ChallengeForm`'s own error banner (lines 446-450,
  hit on MFA/new-password steps) — both filed as siblings below.
- **Proposed fix:** Belongs inside `login/page.tsx` itself, not a new `components/ui/`
  component (3 usages in 1 file isn't enough repetition to justify one) — add `role="alert"`
  to all 3 existing banner blocks (261-269, 271-279, 446-450), or factor them through one
  tiny local wrapper so a future 4th banner inherits it too.
- **Issue cards:** [ISS-337](../.knowledge/cards/20260828-1900-ISS-337.md) (root —
  validator's original card, extended in this pass with the root-cause mechanism, blast
  radius and fix location), [ISS-574](../.knowledge/cards/20260829-0220-ISS-574.md)
  (sibling, INFERRED: `isExpired` banner), [ISS-575](../.knowledge/cards/20260829-0220-ISS-575.md)
  (sibling, INFERRED: `ChallengeForm` error banner)
- **Fix card:** [FIX-393](../.knowledge/cards/20260829-0325-FIX-393.md) — `role="alert"` added to
  all three hand-rolled status banners in `frontend/src/app/login/page.tsx` (isExpired 261, LoginForm
  error 271, ChallengeForm error 446); no wrapper component, blast radius is 3 sites in this one
  router-leaf file
- **Fix card (reopen):** [FIX-408](../.knowledge/cards/20260829-0447-FIX-408.md) — TS2554 at
  `login.a11y.test.tsx:92` cleared by passing the required `detail` argument; test-file only,
  no production source changed
- **Found at:** 2026-08-28 04:18 UTC
- **Found by:** bug-login-expired-1-r2
- **Fingerprint:** `/login?expired=1|sign-in-error-message|submit-with-invalid-credentials|error-text-not-announced-to-assistive-tech`
- **Evidence:** `bug-hunter/evidence/login-expired-1/BUG-20260828-041815-login-expired-1/`

### Summary
Submitting the sign-in form on `/login?expired=1` with invalid credentials correctly renders a
visible "Invalid email or password." message, but the element carries no `role="alert"`,
`role="status"`, or `aria-live` attribute (own or inherited), and focus is not moved to it. The
page's only accessible-tree "alert" node is Next.js's built-in `next-route-announcer` (a
shadow-DOM element used only for route-change titles), which stays empty and is unrelated to
this error. A screen-reader user who submits wrong credentials gets no notification that
anything happened — the form simply appears to sit still, since neither the visual state change
nor keyboard focus alerts them to the new error text. This is reproducible on `/login` generally
(same component), but is being filed against `/login?expired=1` since that is the assigned
route and its DOM is otherwise identical.

### Reproduction
1. Ensure signed out (`localStorage.clear(); sessionStorage.clear()`), navigate to
   `http://localhost:3000/login?expired=1`.
2. Fill the Email field with an invalid address (e.g. `wrong@flowinqa.com`) and the Password
   field with any wrong password.
3. Click "Sign in" (or press Enter from the password field).
4. Observe the DOM: a new `<div>` containing "Invalid email or password." appears above the
   form, but `getAttribute('role')` and `getAttribute('aria-live')` are both `null` on that
   element and on every ancestor up to `<body>`. `document.activeElement` remains on `<body>`
   (no focus is moved to the message or back to a field).
5. Repeated with a second, different pair of invalid credentials — same result both times.

### Expected
A programmatically-determinable status message (via `role="alert"`, `role="status"`, or
`aria-live="polite"/"assertive"`) should be present so assistive technology announces the
authentication failure, per WCAG 4.1.3 (Status Messages). Alternatively, focus should move to
the error text.

### Actual
The error text is inserted as a plain, non-live `<div>` with no role. Screen-reader users
receive no notification of the failed login; the failure is only conveyed visually.

### Evidence
- Before (empty form, no error): `bug-hunter/evidence/login-expired-1/BUG-20260828-041815-login-expired-1/01-before-empty-form.png`
- Failure (error shown, confirmed via evaluate to have no role/aria-live): `bug-hunter/evidence/login-expired-1/BUG-20260828-041815-login-expired-1/02-failure-error-shown-no-live-region.png`

### Browser Signals
- Console: none relevant (one benign 401 network-error console entry from the failed login
  request itself, expected).
- Network: `POST /api/auth/login` returns `401` as expected; not itself a defect.
- State/URL: URL stays `/login?expired=1` throughout; `document.activeElement` stays on
  `<body>` after the error renders, confirming no focus management either.

## BUG-20260828-042311-settings — Bare `/settings` redirects correctly on a cold/full load but renders the honest 404 page when reached via client-side (SPA) navigation

- **Page:** Bare settings route
- **Route:** /settings
- **Severity:** Low
- **Status:** CLOSED
- **Found at:** 2026-08-28T04:23:11Z
- **Found by:** bug-settings-r2
- **Fingerprint:** `/settings|bare-route-router|clientside-navigation-to-settings|shows-404-instead-of-redirect-that-fullload-applies`
- **Evidence:** `bug-hunter/evidence/settings/BUG-20260828-042311-settings/`

### Summary
A full/cold browser navigation (typing the URL, or a `fetch`/reload) to bare `/settings`
receives a server-level redirect to `/settings/profile` and renders correctly (this is the
already-known, intentional-per-quirk-notes behaviour, C-2). However, when the exact same path
is reached via client-side SPA routing (a `pushState` + `popstate` transition, which is what
any in-app `navigate('/settings')` call or React Router `<Link to="/settings">` would trigger)
the app's client router does not replicate that redirect. It instead falls through to the
honest, fully-rendered 404 "Page not found" screen, with the URL bar frozen on `/settings`.
Confirmed via `fetch('/settings')` that the redirect is applied at the network/server layer
(`response.redirected === true`, final `response.url` is `/settings/profile`) — the client
router has no equivalent redirect rule of its own, so any client-side transition to this path
dead-ends at 404 instead of landing the user on their profile settings the way a fresh page
load does.

### Reproduction
1. Sign in as qa-admin (or any tier — reproduced identically on qa-basic and qa-admin), land on
   `/dashboard`.
2. Full navigation to `/settings/profile` (baseline, confirms cold load redirect works).
3. In the browser console context, run `window.history.pushState({}, '', '/settings');
   window.dispatchEvent(new PopStateEvent('popstate'))` — this simulates the exact history
   transition any in-app client-side `navigate('/settings')` call would perform.
4. Observe the URL stays `/settings` and the page renders the full "Page not found" 404 screen
   instead of redirecting to `/settings/profile`.
5. Reload the same `/settings` URL directly (full navigation) — it correctly redirects to
   `/settings/profile`, proving the redirect logic exists but is not reachable from client-side
   routing.
6. Repeated on both qa-basic and qa-admin accounts with identical results (2 independent
   reproductions plus a confirmation on both tiers).

### Expected
A client-side transition to `/settings` should apply the same redirect-to-`/settings/profile`
behaviour as a cold load, since it is the same route being resolved by the same app — the
destination should not depend on how the URL was reached.

### Actual
Client-side navigation to `/settings` renders the honest 404 "Page not found" page and leaves
the URL frozen on `/settings`, while a full/cold navigation to the identical path redirects
successfully to `/settings/profile`.

### Evidence
- Before (cold load, correct redirect to /settings/profile): `bug-hunter/evidence/settings/BUG-20260828-042311-settings/01-before-cold-load-redirects-correctly.png`
- Failure (client-side nav, 404 instead of redirect): `bug-hunter/evidence/settings/BUG-20260828-042311-settings/02-failure-clientside-nav-shows-404.png`
- Repro 2 (same failure on qa-admin account): `bug-hunter/evidence/settings/BUG-20260828-042311-settings/03-repro2-admin-account-same-404.png`

### Browser Signals
- **Status:** CLOSED
- Network: `fetch('http://localhost:3000/settings')` returns `redirected: true`, final `url`
  `http://localhost:3000/settings/profile` — confirming the redirect is server/network-layer
  only, with no corresponding client-router rule. No network request fires at all during the
  client-side `popstate` transition, confirming the 404 is a pure client-side render decision.

- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced identically on every cold cycle, no
  axis variance needed. Root cause: `frontend/src/lib/routes.ts:401-403` parses bare
  `/settings` as `unknown` while `frontend/next.config.ts:27-28` defines a server-only redirect
  to `/settings/profile`; the two layers disagree.
- **Issue card:** [ISS-339](../.knowledge/cards/20260828-1850-ISS-339.md), [ISS-572](../.knowledge/cards/20260829-0019-ISS-572.md)
  (sibling: the other 3 next.config.ts redirects, /library/agents|skills|hooks)
- **Fix card:** [FIX-397](../.knowledge/cards/20260829-0349-FIX-397.md) — `parseViewPath`
  (`frontend/src/lib/routes.ts`) now mirrors all 4 of next.config.ts's server-only redirects:
  bare `/settings` resolves to `settings-profile` and the legacy 2-segment
  `/library/agents|skills|hooks` resolve to `library`, instead of falling through to `unknown`
  -> `notFound()`. Test `frontend/src/lib/routes.iss339.test.ts` — 4/4 `it.fails` XPASS
  (vitest's strict-xfail analogue); `routes.test.ts` 59 passed, with its two stale
  `unknown` assertions corrected per ISS-572.
- State/URL: URL stays `/settings` throughout the client-side-nav failure case (never becomes
  `/settings/profile`), distinct from the full-load case where the URL bar itself changes to
  `/settings/profile`.
- **Root cause:** CONFIRMED — `frontend/src/lib/routes.ts:405-409` (`parseViewPath`,
  `head === 'settings'`, `segments.length === 1`) explicitly returns `{ screen: 'unknown' }` for
  bare `/settings`, with an inline comment acknowledging the gap. `frontend/next.config.ts:26-30`
  defines the redirect only as a Next.js server-side `redirects()` rule, which never fires on a
  client-side history transition. `frontend/src/app/[...view]/page.tsx:3780-3782`
  (`if (parsedView.screen === "unknown") notFound();`) is the single shared gate that renders the
  404 for that result.
- **Blast radius:** `parseViewPath` is called from 4 sites (`frontend/src/app/[...view]/page.tsx:398`,
  `frontend/src/components/library/LibraryPage.tsx:490`, `frontend/src/app/error.tsx:24`,
  `frontend/src/app/global-error.tsx:24`) — only the first is a rendering gate (the other two only
  label errors for logging, not this defect's blast radius). All 4 of `next.config.ts`'s
  `redirects()` rules were checked against `routes.ts`; 3 more have the identical
  no-client-mirror gap: `/library/agents`, `/library/skills`, `/library/hooks`
  (`frontend/src/lib/routes.ts:377-399`), independently codified as a passing (wrong) test at
  `frontend/src/lib/routes.test.ts:309-313`. No in-app caller currently constructs any of these
  4 bare paths (`routes.ts`'s own builders always emit the tabbed/query form), so real-world
  exposure is external/historical links landing as a client-side transition, not any in-app button.
- **Proposed fix:** belongs in the shared parser (`frontend/src/lib/routes.ts`'s `parseViewPath`)
  or the single catch-all gate that consumes it (`[...view]/page.tsx:3780`), not duplicated per
  caller — per ADR-0018, `routes.ts` is the one place that parses every URL. A guard here fixes
  all 4 paths at once and keeps the two redirect tables (next.config.ts, routes.ts) from drifting
  further apart.
- **Issue cards:** [ISS-339](../.knowledge/cards/20260828-1850-ISS-339.md) (root, this bug),
  [ISS-572](../.knowledge/cards/20260829-0019-ISS-572.md) (sibling, INFERRED: same gap on
  `/library/agents`, `/library/skills`, `/library/hooks`)
- **Verified:** 2026-08-29 — `frontend/src/lib/routes.iss339.test.ts` (4/4, XPASS confirmed
  with `it.fails` still in place, then `.fails` removed and re-run: 4/4 plain green) and
  `frontend/src/lib/routes.test.ts` (59/59 green, unchanged) via
  `npx vitest run src/lib/routes.iss339.test.ts src/lib/routes.test.ts`. Manual repro from this
  entry re-run by hand in real Chrome (lane4, qa-admin, signed in): cold `/dashboard` ->
  `window.history.pushState({}, '', '/settings'); dispatchEvent(new PopStateEvent('popstate'))`
  now renders the Profile settings screen (tabs Profile/AI Model/Usage & Limits/Constitution/
  Security, heading "Account Settings"), not the 404 — screenshot
  `bug-hunter/evidence/settings/BUG-20260828-042311-settings/04-after-fix-clientside-nav-shows-profile.png`.
  Also spot-checked the ISS-572 sibling the same way: client-side `pushState`/`popstate` to
  `/library/agents` now renders the Library screen (h1 "Library", 3 tabs), not 404. No new
  console errors/warnings on either page. `curl :8000/docs` -> 200 (backend untouched, no
  restart needed — frontend-only fix). `npx tsc --noEmit`: 0 errors in routes.ts/routes.test.ts;
  15 pre-existing errors remain in unrelated files (login.a11y.test.tsx,
  HomeLaunchGrid.crossAccountLeak.test.tsx, api.sessionExpiryRedirect.test.ts,
  listenerMiddleware.test.ts), matching FIX-397's own count exactly. `lint-imports` (from
  `backend/`): 1 pre-existing broken contract (`agents.execution_engine.engine` ->
  `app.api.*`), unrelated to this frontend-only change — not caused by this fix.
  Regression file `tests/integration/e2e/suites/13_errors/test_errors.py` (offline tier):
  attempted twice via `.venv/bin/python -m pytest`, both runs stalled at the session-scoped
  real-Chrome login fixture with near-zero CPU for 3.5+ minutes (environment contention — many
  MCP browser lanes were active concurrently in this run) and were killed without completing;
  SKIPPED, not claimed as a pass. Per FIX-397's own coverage note this suite only exercises the
  cold-load path (unchanged `next.config.ts` redirect), so it is not expected to be sensitive to
  this change, but that is unconfirmed by an actual run here.

## BUG-20260828-042900-handoff-invalid — A genuine network/fetch failure on the handoff page is misreported as "Handoff not found", even for a real, valid, owned token

- **Page:** Handoff — invalid/unknown token
- **Route:** /handoff/{token}
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28T04:29:00Z
- **Found by:** bug-handoff-invalid-r2
- **Fingerprint:** `/handoff/{token}|token-lookup-fetch|network-request-fails-or-is-unreachable|frontend-renders-generic-not-found-instead-of-a-network-error-state`
- **Evidence:** `bug-hunter/evidence/handoff-invalid/BUG-20260828-042900-handoff-invalid/`

### Summary
The `/handoff/{token}` page's "not found" error surface (`Handoff not found`) is shown any time
the `GET /api/handoff/{token}` request fails to complete — including a pure network failure
(DNS/connection error, backend unreachable, request aborted) — not only on an actual HTTP 404.
Reproduced against a real, currently-valid, owned handoff token minted via
`POST /api/handoff/receive` (task/repo present, PAT step correctly rendered on a healthy
request): when the browser's fetch to `/api/handoff/{token}` is made to fail at the network
layer, the page renders the exact same "Handoff not found" heading/body used for a genuinely
nonexistent token, with a secondary "Failed to fetch" line and only a "Back to dashboard" link
— no retry action, no indication that the session might still exist. A user whose network blips
or whose backend briefly restarts while opening a legitimate handoff link is told their handoff
does not exist, which is misleading (the session is fine) and gives no way to recover other than
manually reloading.

### Reproduction
1. Sign in as qa-admin. Mint a real handoff token via the API:
   `POST /api/handoff/receive` with `X-Flowin-API-Key` → token `vEv29RqYXaZwB96qpEfkoYDBIwEMBRnqZ1sAT84_VXU`.
2. Navigate to `http://localhost:3000/handoff/vEv29RqYXaZwB96qpEfkoYDBIwEMBRnqZ1sAT84_VXU` with a
   healthy network — confirm it renders the real session ("One more step before this can run" /
   task description / repo URL), proving the token and ownership are valid.
3. Install a Playwright route handler that aborts every `**/api/handoff/**` request
   (`route.abort('failed')`), then reload the same real-token URL.
4. Observe the page renders `Handoff not found` / `Failed to fetch` / `Back to dashboard` —
   identical in shape to the genuinely-nonexistent-token case — for a token that is valid and
   still exists server-side.
5. Reproduced the same conflated rendering on a synthetic nonexistent token
   (`/handoff/network-fail-test-token`) under the same aborted-network condition.
6. Remove the route interception and reload — the real token renders correctly again
   immediately, confirming the session/token itself was never actually invalid.

### Expected
A network/fetch failure while loading a handoff session should be distinguished from a
confirmed 404 from the server — e.g. a "Couldn't reach VelocityAI — check your connection and
retry" state with a retry action, not the same copy used for "this token doesn't exist."

### Actual
Any failed `GET /api/handoff/{token}` request (network-layer failure, not just a real 404)
renders the identical "Handoff not found" error surface, even for a token that is real, owned,
and unexpired.

### Evidence
- Before (real token, healthy network, renders correctly): `bug-hunter/evidence/handoff-invalid/BUG-20260828-042900-handoff-invalid/01-before-real-token-loads-correctly.png`
- Failure (same real token, network request forced to fail, shows "Handoff not found"): `bug-hunter/evidence/handoff-invalid/BUG-20260828-042900-handoff-invalid/02-failure-network-error-shown-as-not-found.png`

### Browser Signals
- Console: one error logged per failed lookup (`Failed to fetch` surfaces directly in the page
  body as a secondary line under the heading — the raw fetch rejection message is shown to the
  end user verbatim).
- Network: the `GET /api/handoff/{token}` request never completes (aborted at the network layer
  via Playwright route interception, simulating an unreachable backend/connection drop) — no
  HTTP status is ever received, yet the UI renders the same state as an explicit 404.
- State/URL: URL stays `/handoff/{token}` throughout; unrouting and reloading immediately
  recovers the correct content, confirming this is a client-side error-handling gap, not a
  server-side data issue.

- **Validated:** 3/3 on 2026-08-28, every cycle from a cold start (cycle 1: reload with route
  interception installed; cycle 2: cleared cookies/localStorage + fresh navigation; cycle 3: a
  brand-new browser tab). Re-minted a fresh real handoff token via `POST /api/handoff/receive`,
  confirmed healthy load, then reproduced the "Handoff not found" / "Failed to fetch" mis-render
  on every cycle with `page.route('**/api/handoff/**', route => route.abort('failed'))`. Root
  cause traced to `frontend/src/components/handoff/HandoffWorkflow.tsx:73-148` (`fetchSession`)
  funneling any thrown error — HTTP 404 or a pure network-layer fetch rejection — into the same
  `loadError` state, then `HandoffWorkflow.tsx:216-233` rendering an unconditional "Handoff not
  found" heading for any `loadError`.
- **Issue card:** [ISS-301](../.knowledge/cards/20260828-1740-ISS-301.md)
- **Root cause:** `frontend/src/lib/api-handoff.ts:61-92` (`authedJson`) — the single choke point
  behind all 8 handoff API calls — throws a bare, status-less `Error` for an HTTP failure and lets a
  network-layer `fetch` rejection propagate unmodified, so neither case carries anything a caller can
  branch on. `HandoffWorkflow.tsx:143-145` (`fetchSession`'s catch) then collapses both into one
  `loadError` string, and `HandoffWorkflow.tsx:216-233` renders "Handoff not found" unconditionally
  for any `loadError`. This is the exact class of bug `lib/api.ts`'s `ApiError`/`isNotFoundError`
  (`:93-116`) was already built to prevent (per its own comment, referencing ISS-374) — but
  `api-handoff.ts` has its own separate `authedJson` that never adopted that fix.
- **Blast radius:** all 8 functions routed through `authedJson` in `api-handoff.ts` (`getHandoff`,
  `startHandoff`, `getGithubPatStatus`, `saveGithubPat`, `deleteGithubPat`, `listApiKeys`,
  `createApiKey`, `revokeApiKey`) carry the same undiscriminated-error defect at the data layer.
  Two additional call sites confirmed broken by the same mechanism: `HandoffWorkflow.tsx`'s
  post-completion re-fetch (`:186-192`) can wipe an already-loaded, in-progress/completed session
  back to "Handoff not found" on a transient refresh failure (the render guard is `loadError ||
  !session`, not `!session` alone); `IntegrationsCard.tsx`'s `refresh()` (`:80-93`) has an EMPTY catch
  that silently renders "No GitHub token saved yet." / "No API keys yet." for a user who has both,
  indistinguishable from a legitimately empty account — confirmed backend-side
  (`backend/app/api/settings.py:178-201`) that "no PAT saved" is itself a normal 200/`null`, never an
  error, so that catch only ever fires on a genuine failure.
- **Fix location:** `authedJson` in `frontend/src/lib/api-handoff.ts` (`:61-92`) — make it throw the
  same `ApiError`-shaped failure `lib/api.ts`'s `request()` already throws (status-bearing for HTTP
  failures, a typed/wrapped case for network failures) so every caller can branch with the same
  `isNotFoundError`-style check instead of re-deriving its own heuristic. One guard there, not one
  per caller. `ApiError` itself is not currently exported from `lib/api.ts` — that export needs adding
  first.
- **Issue cards:** [ISS-301](../.knowledge/cards/20260828-1740-ISS-301.md) (root),
  [ISS-409](../.knowledge/cards/20260828-2148-ISS-409.md) (sibling: IntegrationsCard swallows the
  same failure as a false empty state), [ISS-411](../.knowledge/cards/20260828-2147-ISS-411.md)
  (sibling: HandoffWorkflow's post-completion re-fetch can wipe an already-valid session)
- **Fixed:** `frontend/src/lib/api-handoff.ts` (`authedJson`) now wraps a network-layer fetch
  rejection as `ApiError(0, ...)` — `lib/api.ts`'s existing "no HTTP response" marker — and throws
  `ApiError(resp.status, ...)` for an HTTP failure, so all 8 handoff calls carry a branchable
  status. `HandoffWorkflow.tsx` consumes it: `loadError` became `{message, offline}`, the heading
  branches to "Couldn't reach VelocityAI" + a Retry button when offline, and the full-page guard
  is now `!session` alone (ISS-411) with a non-blocking notice for a failed refresh. `ApiError` was
  already exported at `lib/api.ts:648` — the card's note that it was not is stale.
  ISS-409 (IntegrationsCard's empty catch) is NOT fixed here and stays open on its own card.
- **Fix card:** [FIX-370](../.knowledge/cards/20260829-0116-FIX-370.md)
- **Tests:** frontend/src/components/handoff/HandoffWorkflow.test.tsx — 1 passed, 1 failed with
  "Error: Expect test to fail" = the `it.fails` (xfail strict) case XPASSing, i.e. the pass signal;
  marker left in place for 6-verifier. Baseline before the change on the same file was
  "1 passed | 1 expected fail (2)". Also green: api-handoff.test.ts (3/3), api.errorEcho.test.ts
  (1/1). tsc --noEmit: 6 errors, none in either changed file.
- **Verified:** `HandoffWorkflow.test.tsx` re-run confirmed XPASS ("Error: Expect test to fail"
  on the `it.fails` case), `it.fails` marker removed, re-run plain green (2 passed). Regression:
  `api-handoff.test.ts` (3/3) and `api.errorEcho.test.ts` (1/1) still green. `tsc --noEmit`: same
  6 pre-existing errors, none in `HandoffWorkflow.tsx`/`api-handoff.ts`/the test file. Backend
  untouched by this fix; `:8000/docs` → 200. `lint-imports` (from `backend/`): 1 pre-existing
  broken contract (`agents.execution_engine.engine` → `app.api`), unrelated to this frontend-only
  change. Manual repro in lane4 Chrome, same conditions as the original (qa-admin, real minted
  handoff token via `POST /api/handoff/receive`): healthy load renders the real session; with
  `page.route('**/api/handoff/**', route => route.abort('failed'))` + reload, the page now shows
  "Couldn't reach VelocityAI" / "The request never reached the server, so this handoff may still
  be fine. Check your connection and try again." with a Retry button — no "Handoff not found"
  text anywhere; clicking Retry after unrouting recovers the real session; a genuine nonexistent
  token still renders "Handoff not found" byte-identical to before. Screenshots:
  `bug-hunter/evidence/handoff-invalid/BUG-20260828-042900-handoff-invalid/03-verify-after-healthy-load.png`,
  `.../04-verify-after-fix-network-error-distinguished.png`.

## BUG-20260828-050115-library — "Coming Soon" agents are fully browsable and configurable via direct URL, bypassing the catalog's own disabled/unreachable gating

- **Page:** Library — Agents tab
- **Route:** /library/agents/{id} (e.g. /library/agents/dotnet-inventory, /library/agents/mulesoft-springboot-scaffold)
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 by 6-verifier.
  `tests/integration/e2e/suites/08_library/test_iss303_beta_agent_direct_url_gate.py`: confirmed
  both tests `[XPASS(strict)]` before removing the `xfail` markers, then plain green (2 passed)
  after — `xfail` lines removed, `@pytest.mark.issue("ISS-303")` kept. Regression:
  `test_library.py` — 24 passed (own run, same count the fixer reported). Manual repro in lane5
  Chrome, qa-admin, same conditions as the register entry (cold direct-URL load, no prior page
  state): `/library/agents/dotnet-inventory` and `/library/agents/mulesoft-springboot-scaffold`
  both now land on `/library` with no drawer/dialog and zero console errors — screenshots
  `bug-hunter/evidence/library/BUG-20260828-050115-library/04-after-fix-dotnet-inventory-redirects-to-library.png`
  and `05-after-fix-mulesoft-redirects-to-library.png`, next to the original failure shots.
  Health: `frontend` `tsc --noEmit` clean for `LibraryPage.tsx` (8 pre-existing errors remain,
  all in unrelated `*.test.tsx`/`*.test.ts` files); backend untouched, `:8000/docs` → 200;
  `lint-imports` (from `backend/`): same 1 pre-existing broken contract
  (`agents.execution_engine.engine` → `app.api`), unrelated to this frontend-only change.
- **Validated:** 3/3 on 2026-08-28, every cycle from a cold direct-URL load — reproduced on two
  unrelated "Coming Soon" pipelines (`dotnet-inventory`, `mulesoft-springboot-scaffold`); not
  tier- or theme-dependent
- **Tested:** tests/integration/e2e/suites/08_library/test_iss303_beta_agent_direct_url_gate.py
  — 2 xfail(strict=True) tests, both observed red 2026-08-29 (drawer opens for a BETA_WORKFLOWS
  agent id via direct URL on both `dotnet-inventory` and `mulesoft-springboot-scaffold`)
- **Root cause:** `LibraryPage.tsx`'s cold-mount URL-seed effect (`:589-614`) opens the detail
  drawer straight from the URL slug with no availability check; the agents branch (`:591-597`)
  never consults `BETA_WORKFLOWS` even though the grid's own `onClick` guard (`:815`) does.
- **Blast radius:** the effect's skills branch (`:598-604`) has the identical missing check
  against `skill.isBeta` — sibling, INFERRED, filed as ISS-416. Hooks branch (`:605-611`) and
  the composer's independent `AgentLibrary.tsx:68` `BETA_WORKFLOWS` copy were checked and ruled
  out (no click-gate / no URL entry point respectively) — not siblings.
- **Fix belongs:** inside the existing cold-mount effect (`LibraryPage.tsx:589-614`) — add
  `!BETA_WORKFLOWS.has(...)` / `!skill.isBeta` to the two broken branches' conditions. This is
  the sole entry point for every direct-URL/bookmark/history open, so a guard there covers every
  caller without touching the (already-correct) click handlers.
- **Issue cards:** [ISS-303](../.knowledge/cards/20260828-1935-ISS-303.md) (root),
  [ISS-416](../.knowledge/cards/20260828-2210-ISS-416.md) (sibling: Skills tab beta-skill bypass,
  same effect)
- **Found at:** 2026-08-28 05:01 UTC
- **Found by:** bug-library-r2
- **Fingerprint:** `/library/agents/{id}|agent-detail-drawer|direct-url-navigation-to-coming-soon-agent-id|full-detail-and-editable-config-render-despite-catalog-marking-agent-unavailable`
- **Evidence:** `bug-hunter/evidence/library/BUG-20260828-050115-library/`, additional cold-start
  validation evidence at `bug-hunter/evidence/library/_scratch/`
- **Fixed:** 2026-08-29 by 5-fixer. [FIX-371](../.knowledge/cards/20260829-0131-FIX-371.md) —
  `frontend/src/components/library/LibraryPage.tsx` only, one hunk inside the cold-mount URL-seed
  effect (the sole direct-URL/bookmark/history entry point). The agents branch now checks
  `BETA_WORKFLOWS.has(getPrimaryPipelineType(agent.pipeline_type))` and the skills branch
  `skill.isBeta` (ISS-416's sibling, same hunk); when the item is beta it calls
  `router.replace(routes.library({ tab }))` instead of `setSelectedAgent`/`setSelectedSkill`, so
  the unreachable URL is dropped from history rather than left parked on a detail path that
  renders nothing. The grid's already-correct `onClick` guards were not touched. Observed:
  `test_iss303_beta_agent_direct_url_gate.py` → both tests `[XPASS(strict)]` (the pass signal),
  markers left for 6-verifier; `test_library.py` → 24 passed in 126.99s (covers a NON-beta agent
  still opening cold, S-08-12/13/19); `LibraryPage.test.tsx` 9 passed, `LibraryPage.reskin.test.tsx`
  5 passed; `tsc --noEmit` clean for this file.

### Summary
30 of the Agents tab's 94 catalog entries (the `.NET to Azure` and Mulesoft-to-Spring-Boot
migration pipelines, plus a handful of revision agents) are rendered as visibly disabled cards —
`opacity-60 cursor-not-allowed`, a "Coming Soon" badge, and no `Configure →` link — so there is no
click path in the UI that reaches their detail page. However, the detail route itself enforces
none of this: navigating directly to `/library/agents/{id}` for any of these "Coming Soon" agent
ids opens the exact same fully-populated detail drawer as a released agent — Overview, Skills,
Hooks, and an interactive **Config** tab with live Model/Validator/Gate/Retry controls and an
enabled "Save agent" button — with nothing in the drawer indicating the agent is unreleased. The
catalog's "Coming Soon" gating is therefore cosmetic only: it blocks the card click, not the
route, so any user who knows or guesses an id (bookmark, shared link, browser history, or simply
incrementing through the API's own agent list) gets full access to an agent the catalog is
actively telling every other user isn't available yet.

### Reproduction
1. Sign in as qa-admin, go to `/library` (Agents tab). Scroll to a `.NET to Azure` card, e.g.
   ".NET Solution Inventory Agent" — confirm it renders with `opacity-60 cursor-not-allowed`, a
   "Coming Soon" badge, and no "Configure →" link (DOM-confirmed: no click target reaches it).
2. Navigate directly to `http://localhost:3000/library/agents/dotnet-inventory`.
3. Observe: the full agent detail dialog opens — `dialog ".NET Solution Inventory Agent details"`
   — with Overview/Skills/Hooks/Config tabs, exactly as for any released agent.
4. Repeat for a second, unrelated "Coming Soon" pipeline: navigate to
   `http://localhost:3000/library/agents/mulesoft-springboot-scaffold` ("Spring Boot Scaffold
   Agent", Mulesoft-to-Spring-Boot pipeline). Same result: full dialog opens.
5. Click into the Config tab for the second agent: renders live Model / Validator / Before-execute
   gate / After-execute gate / Retry controls, a "Reset" button, and an enabled "Save agent"
   button — fully interactive, not a read-only/locked view.

### Expected
An agent the catalog marks "Coming Soon" and deliberately blocks from being opened by click should
either be unreachable by direct URL too (redirect back to `/library` or show a "not yet available"
state), or at minimum the detail view should visibly communicate the same unavailable/locked state
the card already shows — not render a fully interactive Config panel with a live Save button.

### Actual
The detail route performs no availability check at all: any "Coming Soon" agent id opens the
identical, fully interactive detail drawer as a released agent, with no visual indication that the
agent is unreleased.

### Evidence
- Before (card in grid showing "Coming Soon", `opacity-60 cursor-not-allowed`, no Configure link): `bug-hunter/evidence/library/BUG-20260828-050115-library/01-before-coming-soon-card-in-grid.png`
- Failure (direct URL opens full detail dialog, agent 1): `bug-hunter/evidence/library/BUG-20260828-050115-library/02-failure-direct-url-opens-full-detail.png`
- Repro 2 (direct URL opens full detail dialog, unrelated agent 2 on a different pipeline): `bug-hunter/evidence/library/BUG-20260828-050115-library/03-repro2-second-agent-direct-url.png`

### Browser Signals
- Console: no errors on either navigation.
- Network: `GET /api/agents/library` 200 OK; the drawer renders from the same already-fetched
  catalog payload, confirming the gap is purely a missing route-level/UI-level availability check,
  not a missing-data issue.
- State/URL: URL correctly reflects `/library/agents/{id}` in both cases; the underlying grid
  (still `/library` in the background) continues to show the same card as disabled the whole time.

## BUG-20260828-050900-settings-profile — Confirm new password field has no show/hide toggle, unlike its sibling fields

- **Page:** Settings — Profile
- **Route:** /settings/profile
- **Severity:** Low
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, every cycle — cold-navigate to /settings/profile as qa-admin,
  no other axis needed; deterministic on every visit.
- **Verified:** 2026-08-29 by 6-verifier. `suites/09_settings/test_settings.py -k
  confirm_new_password_has_a_show_hide_toggle_like_its_siblings` XPASS confirmed, xfail marker
  removed, re-run PASS. `suites/11_admin/test_admin.py -k
  create_user_password_field_has_a_show_hide_toggle` XPASS confirmed, xfail marker removed,
  re-run PASS. `frontend/src/app/login/login.passwordVisibility.test.tsx` `it.fails` XPASS
  ("Error: Expect test to fail") confirmed, converted to plain `it`, re-run PASS. Manual repro in
  real Chrome (lane5) as qa-admin on cold /settings/profile: all three password fields (Current,
  New, Confirm new) now render a "Show password" button; clicking Confirm new password's toggle
  flips `input[placeholder="Re-enter new password"]` from `type="password"` to `type="text"` and
  reveals the typed value — matches the ISS-338 expected behaviour exactly. No console
  errors/warnings on the page. `npm run build` and `npx tsc --noEmit` clean on the 4 touched
  files (pre-existing unrelated errors only, in test files this change does not touch).
  Regression: `AccountSettings.render.test.tsx` (8 passed), `AccountSettings.password-mismatch.test.tsx`
  (1 passed, ISS-244 guard intact). Backend untouched (frontend-only fix); `:8000/docs` = 200,
  no restart required. `lint-imports` (run from `backend/`) shows 1 pre-existing broken contract
  (`agents.execution_engine.engine` -> `app.api` via `kernel_services`/`revision_analyzer`),
  unrelated to this change — no `.py` file in FIX-398's diff.
- **Found at:** 2026-08-28T05:09:00Z
- **Found by:** bug-settings-profile-r2
- **Fingerprint:** `/settings/profile|change-password-form|inspect-confirm-new-password-field|missing-visibility-toggle-inconsistent-with-current-and-new-password-fields`
- **Evidence:** `bug-hunter/evidence/settings-profile/BUG-20260828-050900-settings-profile/`
- **Root cause:** `AccountSettings.tsx` wires a per-field show/hide boolean + eye-icon button to
  "Current password" and "New password" individually (`showCurrent`/`showNew` state at
  `AccountSettings.tsx:98-99`, toggle buttons at `:292-294` and `:304-306`) but never declares a
  matching `showConfirm` for "Confirm new password" (`:309-314`) — that field is hardcoded
  `type="password"` with no button at all. CONFIRMED by direct read of the current file (line
  numbers drifted +2 from the ISS-338 card's L96-97/283-300 because `FIX-341` landed in between;
  the mechanism is unchanged). This is an unconditional JSX omission, not a runtime/state/theme
  condition, which matches the validator's 3/3-deterministic, no-axis-needed result.
- **Blast radius:** none via a shared caller — `showCurrent`/`showNew`/`EyeOff` is local
  component state with no other reference in the codebase (`grep -rn
  "showCurrent\|showNew\|EyeOff" frontend/src` matches only this file). The broader cause is
  architectural: `frontend/src/components/ui/` has no reusable masked-password-input component,
  so the same omission is free to recur anywhere a password field is hand-rolled — and already
  has, confirmed by source read: the login page's Cognito `NEW_PASSWORD_REQUIRED` challenge form
  (`frontend/src/app/login/page.tsx` imports no `Eye`/`EyeOff` at all; New password `:455-470`
  and Confirm password `:471-485` are both hardcoded `type="password"`) and the Admin
  "Create New User" modal (`frontend/src/app/admin/page.tsx:494-499`, same absence).
- **Fix belongs in:** a shared `PasswordInput`-style primitive in `frontend/src/components/ui/`
  that owns its own show/hide state, reused by all six affected fields (this bug's three, plus
  the two sibling locations) — not a `showConfirm` patch local to `AccountSettings.tsx` alone,
  which would leave both sibling cards' fields broken.
- **Issue cards:** [ISS-338](../.knowledge/cards/20260828-2050-ISS-338.md) (root),
  [ISS-576](../.knowledge/cards/20260829-0218-ISS-576.md) (sibling: login page forced-password-change
  form, INFERRED), [ISS-577](../.knowledge/cards/20260829-0219-ISS-577.md) (sibling: Admin
  "Create New User" modal, INFERRED)
- **Fix card:** [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md) — shared
  `frontend/src/components/ui/PasswordInput.tsx` primitive; all six password fields rewired to it.
  Deferred: [ISS-602](../.knowledge/cards/20260829-0353-ISS-602.md) (the main sign-in field, uncarded).

### Summary
On the Password card of /settings/profile, both "Current password" and "New password" inputs
render an eye-icon button that toggles the field between masked (`type="password"`) and plain
text (`type="text"`), letting the user verify what they typed. The adjacent "Confirm new
password" input — functionally identical, and whose entire purpose is to let the user verify
they retyped the new password correctly — has no such button and can never be revealed. Source
inspection confirms the cause: `AccountSettings.tsx` only declares `showCurrent`/`showNew` state
(lines 96-97) and wires a toggle button to each of the first two inputs (lines 283-300); the
confirm-password input (from line ~305) has no matching `showConfirm` state or button at all.

### Reproduction
1. Sign in as qa-admin, navigate to /settings/profile.
2. Click into "Current password", type any value; click into "New password", type any value;
   click into "Confirm new password", type any value.
3. Observe: "Current password" and "New password" each show a small eye/eye-off icon button on
   the right edge of the input. "Confirm new password" shows no icon.
4. Click the eye icon on "Current password" and on "New password" — each toggles that single
   input's `type` between `password` and `text` independently (confirmed via DOM `input.type`).
   No equivalent control exists for "Confirm new password" — it remains masked with no way to
   reveal it.
5. Reload to a fresh /settings/profile and repeat steps 2-4 — same result: `confirmHasToggle`
   evaluates `false` via `document.querySelector('input[placeholder="Re-enter new password"]
   ~ button')` while `currentHasToggle` / `newHasToggle` evaluate `true`, on both passes.

### Expected
All three password inputs in the same form should offer the same show/hide affordance, or at
minimum the confirm field (whose entire purpose is letting the user verify their retyped value)
should be revealable like its siblings.

### Actual
"Current password" and "New password" have a working eye-icon visibility toggle; "Confirm new
password" has none and can never be shown in plain text.

### Evidence
- Before: `bug-hunter/evidence/settings-profile/BUG-20260828-050900-settings-profile/01-before-empty-form.png`
- Failure: `bug-hunter/evidence/settings-profile/BUG-20260828-050900-settings-profile/02-confirm-field-no-toggle.png`
  (Current and New password revealed as plain text via their toggles; Confirm new password still
  masked with no icon present.)

### Browser Signals
- Console: none observed related to this defect.
- Network: none — this is a client-render-only defect, no request involved.
- State/URL: URL stays /settings/profile throughout; confirmed via direct DOM query
  (`input[placeholder="Re-enter new password"] ~ button` → `null`) that no toggle button is
  attached to the confirm-password input, on two independent page loads.

## BUG-20260828-051530-create — "Save as my version" on the seeded "Ask a Human, Then Hand Off" example fails with a raw 422 backend manifest-validation error

- **Page:** Create (catalog) — "Ask a Human, Then Hand Off" launch panel
- **Route:** /create/ex_A4_human_divert
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28 — ran `tests/integration/e2e/suites/03_launch_panels/test_save_manifest_gates.py` (venv `tests/integration/e2e/.venv`): all 5 ISS-225/ISS-254 cases XPASS(strict) before the marker removal, plain green (5 passed, 1 xfailed for the still-open ISS-263) after removing `xfail` from the two fixed tests; `@pytest.mark.issue` kept, ISS-263's `xfail` deliberately left in place (unfixed, see FIX-337/ISS-381). Manually re-ran the exact register repro in the browser (lane6): cold-loaded `/create/ex_A4_human_divert`, typed a brief with the Advanced modal and Review gates untouched, clicked "Save as my version" — `POST /api/user-workflows` now returns `201 Created` (was `422`), no red inline error string, "Run workflow" becomes enabled, no new console errors; after-screenshot `bug-hunter/evidence/create/BUG-20260828-051530-create/04-after-fix-verify-save-succeeds.png`. Health: `frontend/npm run build` succeeds cleanly; `curl :8000/docs` → 200 (pure `.tsx` fix, no restart needed); `backend/lint-imports` shows one pre-existing broken contract (`agents.execution_engine.engine` -> `app.api`, unrelated to this frontend-only change — not touched by FIX-337). Regression: `suites/03_launch_panels/test_launch_panels.py` exits 0 (18 scenarios, all pass/expected-xfail — ISS-247 xfail is pre-existing and unrelated).
- **Found at:** 2026-08-28 05:15 UTC
- **Found by:** bug-create-r2
- **Fingerprint:** `/create/ex_A4_human_divert|composer-save-as-my-version|click-save-as-my-version-with-unmodified-seeded-manifest|422-backend-manifest-validation-error-blocks-save`
- **Evidence:** `bug-hunter/evidence/create/BUG-20260828-051530-create/`
- **Validated:** 3/3 on 2026-08-28, cycle 1, 2 and 3 — deterministic, not a race
- **Issue card:** [ISS-225](../.knowledge/cards/20260828-1541-ISS-225.md)
- **Root cause:** `selectionsRef` (`frontend/src/components/workflow/IdeaInputPage.tsx:936`) is
  seeded only from `cleanSelections` and mutated only by explicit user edits — never merged with
  `manifestSelections`, the manifest's own declared gates built from the raw fetched steps at
  `:1098-1105`. `handleSaveAsOverride` (`:1460-1478`) serializes `selectionsRef.current` straight
  into `buildWorkflowManifest(...)`, so an untouched step with `route:` goes out with `gates: []`
  and the backend's R-03 cross-field check (`backend/agents/workflows/compiler.py:961-971`)
  rejects it. CONFIRMED by direct read of both files; matches ISS-225's own trace exactly.
- **Blast radius:** every other built-in whose manifest declares `route:` and is opened through
  this same page/button — `ex_A1_loop`, `ex_A2_branch`, `ex_A3_divert`, `ex_A4_human_gate`
  (`grep -rl "route:" backend/agents/workflows/*/workflow.yaml`, INFERRED per-example, same code
  path — ISS-254). The sibling "Save workflow" button on the identical page reads the same
  unseeded ref but silently drops the route instead of erroring: the `selections`-only save path
  short-circuits validation on an empty map (`backend/app/api/user_workflows.py:361-378`) and
  `synthesize_manifest` can never emit `route:` regardless (`route` is absent from both
  `_LEVER_KEYS` and the verbatim-projection loop, `backend/agents/workflows/selections.py:43-49,
  149-153`) — INFERRED, ISS-263. CONFIRMED unaffected: `handleRun`/Launch (omits `selections`
  entirely when empty — INV-3 — so the backend falls back to the correct file-backed manifest)
  and `ComposerPage.tsx`'s own "Save as copy" (`selections` state is seeded from
  `manifestStepsToGateSelections` at both mount and a late-arrival resync, `:315-374` — the exact
  fix this bug still needs, already applied there).
- **Proposed fix:** merge `manifestSelections` into the outgoing manifest/selections AT the
  `handleSaveAsOverride` (and, pending ISS-263, `handleSaveWorkflow`) call sites in
  `IdeaInputPage.tsx` — manifest-declared gates first, `selectionsRef.current` second so a user
  edit still wins — mirroring the `manifestStepsToGateSelections` pattern `ComposerPage.tsx`/
  `CanvasView.tsx` already use correctly (see FIX-285). Do NOT seed `selectionsRef.current`
  itself: `handleRun` relies on its emptiness to omit `selections` from an untouched launch
  payload (INV-3), so the merge belongs at the save call sites, not the shared ref.
- **Fixed:** 2026-08-28 — [FIX-337](../.knowledge/cards/20260828-2210-FIX-337.md). `handleSaveAsOverride` (`frontend/src/components/workflow/IdeaInputPage.tsx:1464`) now spreads `manifestSelections` UNDER `selectionsRef.current` into a local `saveSelections`, fed to `buildWorkflowManifest(...)` and `setOverrideSelections(...)` — manifest-declared gates first so a user edit still wins, merged at the save call site and NOT into the ref (`handleRun` reads its emptiness to omit `selections`, INV-3). Verified: `tests/integration/e2e/suites/03_launch_panels/test_save_manifest_gates.py` — ISS-225 1 XPASS(strict), ISS-254 4 XPASS(strict) (ex_A1_loop, ex_A2_branch, ex_A3_divert, ex_A4_human_gate). ISS-263's test still xfails — see below.
- **ISS-263 NOT fixed — premise refuted, superseding finding [ISS-381](../.knowledge/cards/20260828-2210-ISS-381.md):** "Save workflow" does not silently 201 as ISS-263 INFERRED; it 422s outright with `agent_ids not allowed for 'ex_A4_human_divert'` from the roster check at `backend/app/api/user_workflows.py:562`, BEFORE `_compile_selections_trust_user` is reached (captured directly against the API, and pre-existing — `user_workflows.py` last changed in `732adc245`). Applying ISS-263's proposed merge to `handleSaveWorkflow` was measured against the real synth+compiler and REGRESSES all five route examples: `synthesize_manifest` projects no `route` (`selections.py:43-49,149-153`), so `gates: [conditional]` alone trips R-03 from the other direction. Making it compile needs the compact selections map to carry authoring structure (`route` with normalised `condition_agent`, plus `produces: [route_decision]` for R-27) — a contract change needing a decision, and inert at run time (`engine._apply_selections:8507-8690` has no route overlay). Test left xfail and UNEDITED.
- **Issue cards:** [ISS-225](../.knowledge/cards/20260828-1541-ISS-225.md) (root),
  [ISS-254](../.knowledge/cards/20260828-1810-ISS-254.md) (sibling: other 4 route-declaring
  examples 422 identically), [ISS-263](../.knowledge/cards/20260828-1811-ISS-263.md) (sibling:
  "Save workflow" silently drops the route instead of erroring)

### Summary
Opening the seeded "Ask a Human, Then Hand Off" example workflow from the `/create` catalog,
typing any brief, and clicking "Save as my version" — with zero edits to the Advanced
Workflow Configuration — fails outright. The backend rejects `POST /api/user-workflows` with a
422 because the workflow's own out-of-the-box manifest is invalid per the backend's own
validation rule R-03: the `Pick Language` step declares a `route:` but is missing the
`gates: [conditional]` the router requires. The raw backend error string is surfaced verbatim
in the composer UI. Since this is the manifest the catalog itself ships and the user made no
configuration changes, every user who opens this example and tries to save their own copy hits
the same dead end with no way to self-correct (the Advanced modal's own Gate dropdown already
shows "Conditional gate" selected for that step, so there is no obvious missing setting to
toggle).

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/ex_A4_human_divert` (fresh
   load, "Ask a Human, Then Hand Off" card from `/create`).
2. Type any non-empty text into the "Brief description" textbox (no other changes — Advanced
   modal untouched, Review gates left at "no gates").
3. Click "Save as my version".
4. Observe: a red-styled inline error string appears under the composer footer reading
   `invalid workflow manifest (workflow:My ex_A4_human_divert): step 'custom-agent' declares
   route: but is missing gates: [conditional] — gates: [conditional] is required when route: is
   declared (R-03)`, and `POST http://localhost:8000/api/user-workflows` returns `422`.
5. Reloaded to a fresh `/create/ex_A4_human_divert`, typed a different brief, clicked
   "Save as my version" again — identical 422 and identical error text (deterministic, not a
   race).

### Expected
Either the seeded example workflow's manifest should validate cleanly out of the box (so an
unmodified save succeeds), or, if the manifest genuinely requires a config change before it can
be saved, the UI should not offer a bare "Save as my version" action that inevitably fails —
at minimum the composer should not let a user hit a raw backend validation string with no
indication of which control to change.

### Actual
"Save as my version" on the unmodified seeded manifest always 422s with a raw backend R-03
manifest-validation message; the workflow can never be saved as-is.

### Evidence
- Before (fresh brief typed, no error yet): `bug-hunter/evidence/create/BUG-20260828-051530-create/01-before-brief-filled.png`
- Failure (first reproduction, 422 + inline error text): `bug-hunter/evidence/create/BUG-20260828-051530-create/02-failure-first-repro.png`
- Failure (second reproduction from a fresh page load, identical error): `bug-hunter/evidence/create/BUG-20260828-051530-create/03-failure-second-repro.png`

### Browser Signals
- Console: `Failed to load resource: the server responded with a status of 422 (Unprocessable
  Entity) @ http://localhost:8000/api/user-workflows`
- Network: `POST http://localhost:8000/api/user-workflows` → `422`, response body
  `{"detail":"invalid workflow manifest (workflow:My ex_A4_human_divert): step 'custom-agent'
  declares route: but is missing gates: [conditional] — gates: [conditional] is required when
  route: is declared (R-03)"}`
- State/URL: URL stays `/create/ex_A4_human_divert` throughout; no configuration changes made
  in the Advanced modal or Review gates panel before either reproduction.

## BUG-20260828-051900-runs — Run detail chat header shows a token total that does not match the run's own API `token_usage`, disagreeing with the correct figure shown on the Run History list card for the same run

- **Page:** Run detail (reached via Run History)
- **Route:** /runs/a0693fcd-9451-4c19-a9e7-61474ea03516
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `tests/integration/e2e/suites/07_run_detail/test_iss304_header_token_total_mismatch.py` XPASS(strict) confirmed pre-removal, `xfail` marker removed, re-run plain green (PASS, 3.8s). Manual repro from this register entry re-run by hand (lane4, qa-admin, cold direct `page.goto` to `/runs/a0693fcd-9451-4c19-a9e7-61474ea03516`, twice): chat header now reads "22m 0s · 10.4K tokens", matching `token_usage.total_tokens=10428` and the Run History list card. No console errors/warnings. Frontend `tsc --noEmit`: 8 pre-existing errors, all in other agents' working-tree test files (HomeLaunchGrid.crossAccountLeak.test.tsx, api.sessionExpiryRedirect.test.ts, listenerMiddleware.test.ts), none in useWorkflow.ts/LaneRunHeader.tsx. `useWorkflow.accumulators.test.ts` + `useWorkflow.reconnect.test.ts`: 36/36 passed (via vitest). Regression: `suites/07_run_detail/test_run_detail.py` full file, 49/49 scenarios PASS. `backend/docs` -> 200. `lint-imports` (run from backend/) reports 1 broken contract (engine.py -> kernel_services -> app.api.run_commands / revision_analyzer -> app.api.run_commands) — confirmed PRE-EXISTING: neither offending file (kernel_services.py, revision_analyzer.py) is in this fix's diff or even in the working tree's modified-file list; this fix touched only frontend/src/hooks/useWorkflow.ts. After-screenshot: `bug-hunter/evidence/runs/BUG-20260828-051900-runs/03-detail-header-shows-10.4K-after-fix.png`.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduces on every cold direct-URL load, no axis variation needed. Root cause: the `pipeline_complete` event's own `total_tokens` field (17931) disagrees with the sum of the run's own `agent_complete` events (10428, matching `token_usage.total_tokens`); `useWorkflow.ts` prefers the event field over the correct accumulated total.
- **Root cause:** Two backend paths independently compute "total tokens for this run" from different result sets and are never reconciled. The live/replayed `pipeline_complete` event (`backend/agents/execution_engine/engine.py:3712-3757`) sums `agent_complete` tokens PLUS `aux_token_usage` — the SmartPlanner (`engine.py:2122`), a clarify one-shot (`engine.py:2265`), and the validation fix-loop sub-agent (`engine.py:2443`). The persisted `workflow_runs.token_usage` column — the SOLE writer, `_apply_terminal_output_columns` (`backend/app/api/run_commands.py:2953-2977`) — reads right past that same event's own totals (`run_commands.py:3042-3045`) and instead re-derives a narrower sum from `agent_outputs_collector` only (`run_commands.py:3057-3065`), silently excluding the aux fold. Frontend (`frontend/src/hooks/useWorkflow.ts:794-799`, shared reducer `handlePipelineMessage` funnels both live SSE and cold-load REST replay) faithfully prefers the backend's "authoritative" event total; `LaneRunHeader.tsx:76-77` renders it verbatim. The frontend is not the defect — the backend's two totals structurally disagree.
- **Blast radius:** `TokenUsageSummary.tsx:19-28` (mounted in the Steps tab via `AgentThinkingTab.tsx:321`) reads the identical corrupted `pipelineState` object — same run, second surface. `backend/app/api/analytics.py:189-195` aggregates strictly from the persisted `token_usage` column, so every run that used the planner/clarify/fix-loop undercounts real spend in every Analytics KPI/chart, system-wide. Checked and NOT affected: `pipeline_failed`/`pipeline_cancelled` never touch the token fields, so failed/cancelled runs keep the correct accumulated total.
- **Issue cards:** [ISS-304](../.knowledge/cards/20260828-1600-ISS-304.md) (root), [ISS-417](../.knowledge/cards/20260828-2230-ISS-417.md) (sibling: Steps tab TokenUsageSummary reads the same corrupted total), [ISS-418](../.knowledge/cards/20260828-2231-ISS-418.md) (sibling: Analytics undercounts real spend system-wide)
- **Found at:** 2026-08-28T05:19:00Z
- **Found by:** bug-runs-r2
- **Fingerprint:** `/runs/[id]|run-detail-chat-header-token-total|open-completed-run-from-filtered-search|header-token-figure-disagrees-with-api-and-list-card`
- **Evidence:** `bug-hunter/evidence/runs/BUG-20260828-051900-runs/`

### Summary
Filtered Run History to "Presentation" and searched, landing on a set of 5 runs that all share
the exact same (truncated) title text — a good stress case for confirming the correct run is
opened. Clicking the card reading "22m 1s / 10.4K / Done" correctly navigated to run
`a0693fcd-9451-4c19-a9e7-61474ea03516` (verified via `GET /api/runs/{id}`: `duration: 1320.7`s ≈
22m1s, `token_usage.total_tokens: 10428` ≈ 10.4K — both match the list card, so the navigation
itself is NOT the bug). However, the run-detail page's own chat header — the line under the run
title reading "just now · 22m 0s · N tokens" — displays **17.9K tokens**, not 10.4K. This is
reproducible on a fresh hard reload, so it is not a stale-render artifact from the click. This is
a distinct component/mechanism from the already-filed Steps-tab footer token bug
(`BUG-20260828-012500-runs-id-steps`, which is ~20x too low and lives in the Steps tab footer on
a different run `b9feac1c...`); this one is the top-of-page chat header on the Preview tab,
overstates by roughly 1.7x, and is verified against the API's `token_usage.total_tokens` field
directly rather than a tooltip.

### Reproduction
1. Sign in as qa-admin, go to `/runs`, click the "Presentation" filter chip (URL becomes
   `/runs?type=ppt`).
2. In the filtered list, locate the completed card reading "22m 1s" / "10.4K" / "Done" (title:
   "A 5-slide deck pitching a coffee subscription service to inv…" — 5 cards share this exact
   truncated title, distinguished only by duration/tokens/status).
3. Click that card. Land on `/runs/a0693fcd-9451-4c19-a9e7-61474ea03516`.
4. Read the chat header directly under the run title: it reads "just now · 22m 0s · 17.9K
   tokens".
5. Reload the page directly (fresh `page.goto` to the same URL, not a click-through) — the
   header still reads "17.9K tokens".
6. Cross-check `GET /api/runs/a0693fcd-9451-4c19-a9e7-61474ea03516` with the qa-admin token:
   `token_usage.total_tokens` is `10428` (10.4K) — matching the Run History list card, not the
   detail header.

### Expected
The run detail header's token total should equal the run's actual `token_usage.total_tokens`
from the API (10.4K here), and should agree with the figure already shown for the same run on
the Run History list.

### Actual
The run detail chat header shows "17.9K tokens" for a run whose API-reported total is 10,428
tokens (10.4K) — a ~72% overstatement, and a direct disagreement with the correct value the user
already saw one click earlier on the Run History card.

### Evidence
- List card showing the correct 10.4K: `bug-hunter/evidence/runs/BUG-20260828-051900-runs/01-list-card-shows-10.4K.png`
- Detail header showing the incorrect 17.9K (fresh reload): `bug-hunter/evidence/runs/BUG-20260828-051900-runs/02-detail-header-shows-17.9K.png`
- API response excerpt (token_usage.total_tokens = 10428): `bug-hunter/evidence/runs/BUG-20260828-051900-runs/api-response-excerpt.json`

### Browser Signals
- Console: none observed
- Network: `GET /api/runs/a0693fcd-9451-4c19-a9e7-61474ea03516` returns `200 OK` with
  `token_usage.total_tokens: 10428`; no error status on any request during reproduction.
- State/URL: URL stays on `/runs/a0693fcd-9451-4c19-a9e7-61474ea03516` throughout; confirmed via
  a fresh direct `page.goto` (not just a click), ruling out stale client-side state from the
  filter+search navigation.

## BUG-20260828-052400-workflows — Delete-workflow confirmation dialog never identifies which workflow it will delete

- **Page:** Saved workflows list
- **Route:** /workflows
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28T05:24:00Z
- **Found by:** bug-workflows-r2
- **Validated:** 3/3 on 2026-08-28, cold start each cycle — deterministic, no axis narrowing needed. Root cause: `deleteConfirmId` (`frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx:166`) stores only the workflow id, never its name, and the confirm dialog (lines 408-444) renders static JSX with no lookup against the workflows list.
- **Issue card:** [ISS-302](../.knowledge/cards/20260828-1734-ISS-302.md)
- **Fingerprint:** `/workflows|delete-workflow-confirmation-dialog|open-workflow-actions-then-delete|dialog-text-contains-no-workflow-name-or-identifier`
- **Evidence:** `bug-hunter/evidence/workflows/BUG-20260828-052400-workflows/`
- **Root cause (CONFIRMED, re-read independently):** `deleteConfirmId` (`SavedWorkflowsPage.tsx:166`, `useState<string | null>`) captures only `row.id` at the menu-click handler (`SavedWorkflowsPage.tsx:348`), discarding the name at the point of capture — the row is already in scope there. The confirm dialog (`SavedWorkflowsPage.tsx:408-444`) is fully static JSX (heading L425, subtext L426, body L429-431) with no lookup back into `userWorkflows` to interpolate a name. Contrast with the sibling `onRename` handler (`SavedWorkflowsPage.tsx:346`), which already stores the **whole row** (`setRenameRow(row)`) and threads `initialName={renameRow.name}` into `NameWorkflowModal` (line 402) — proving the fix pattern already exists correctly one function away in the same file.
- **Blast radius (grepped every caller of `deleteUserWorkflow` in `frontend/src/`):** exactly one production call site, `SavedWorkflowsPage.tsx:221` (`HomeLaunchGrid.test.tsx`/`HomeLaunchGrid.crossAccountLeak.test.tsx` mock the whole `@/lib/api` module but `HomeLaunchGrid.tsx` itself has no delete affordance) — this bug is fully contained to one component. However the same defect **shape** (id-only `useState<string|null>` confirm variable set from a row-click handler + a dialog rendering fully static text with no lookup) is independently duplicated in two unrelated, unshared implementations: `WorkflowHistory.tsx`'s run-delete `DeleteModal` (`deleteConfirmId` L179, `DeleteModal` defined L1237 with no name prop, static text L1270-1275) and `admin/page.tsx`'s delete-user dialog (`deleteConfirm` L126, set via `setDeleteConfirm(user.id)` L441, static text L543-544). Three separate copies of the same mistake, not one shared function — no single patch reaches all three.
- **Fixed:** 2026-08-29 — [FIX-372](../.knowledge/cards/20260829-0141-FIX-372.md). `deleteConfirmId` (`frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx:166`) now holds the whole row (`deleteRow`, mirroring the sibling `renameRow`), set from `row` at the menu handler (line 348), and the dialog body (line 430) interpolates `deleteRow.name`. Heading left as "Delete workflow" — `SavedWorkflowsPage.test.tsx:262` asserts it exactly and ISS-302 accepts the name in the body. Siblings ISS-414/ISS-415 share no code with this component and stay open. Verified: `tests/integration/e2e/suites/05_saved_workflows/test_iss302_delete_dialog_no_name.py` XPASS(strict), 9/9 green in `SavedWorkflowsPage.test.tsx`.
- **Fix belongs:** the in-scope fix for this card is local to `SavedWorkflowsPage.tsx` — mirror the already-correct `renameRow` pattern (store the row, not just the id) and interpolate the name at dialog lines 425/429-431. A shared confirmation-dialog component (subject-label prop) that `WorkflowHistory.tsx` and `admin/page.tsx` also route through is recommended given the pattern has already been copy-pasted twice, but is not required to close this card since no such shared function exists today.
- **Issue cards:** [ISS-302](../.knowledge/cards/20260828-1734-ISS-302.md) (root), [ISS-414](../.knowledge/cards/20260828-2202-ISS-414.md) (sibling: `WorkflowHistory.tsx` run-delete `DeleteModal`, same shape, INFERRED/unreproduced), [ISS-415](../.knowledge/cards/20260828-2202-ISS-415.md) (sibling: `admin/page.tsx` delete-user dialog, same shape, INFERRED/unreproduced)

### Summary
Clicking Delete in a saved-workflow card's "Workflow actions" menu opens a confirmation dialog whose entire text is generic and static — "Delete workflow" / "This cannot be undone" / "The saved workflow will be permanently removed from your saved workflows." — with no workflow title, id, or any other identifying detail anywhere in the dialog (verified via the full accessibility tree, not just the visible screenshot). The list contains many near-identical rows (four cards titled "Signoff Stop-Resume Test" with only a trailing numeric suffix distinguishing three of them, four "Signoff Composer Test (API)…" cards, etc.), so a user who opens the menu on the wrong card among lookalikes has no way to catch the mistake before confirming an irreversible delete — the dialog itself provides zero disambiguating evidence, and by the time it is open the source card is no longer visible/highlighted either.

### Reproduction
1. Go to `/workflows` as qa-admin.
2. Locate two or more cards with very similar or identical titles (e.g. the four "Signoff Composer Test (API)…" cards, or the four "Signoff Stop-Resume Test…" cards).
3. Click "Workflow actions" on one such card, then click "Delete" in the menu.
4. Observe the confirmation dialog text in full (via accessibility snapshot or by reading every visible string).
5. Repeat on a second, differently-named lookalike card.
6. Observe: both dialogs render byte-identical generic text with no workflow name/id.

### Expected
The delete confirmation should state which workflow is about to be deleted (e.g. "Delete '<workflow title>'?" or include the title/id in the body), so a user can verify the correct row is targeted before an irreversible action, especially given the list's many near-duplicate names.

### Actual
The dialog heading and body are fixed, generic strings identical regardless of which card triggered it — no title, id, or other identifying detail is present anywhere in the dialog's accessible text.

### Evidence
- Before: `bug-hunter/evidence/workflows/BUG-20260828-052400-workflows/01-before.png`
- Failure (card 1, "Signoff Composer Test (API) 1786741346946"): `bug-hunter/evidence/workflows/BUG-20260828-052400-workflows/02-delete-dialog-no-name.png`
- Second repro (card 2, "Signoff Stop-Resume Test"): `bug-hunter/evidence/workflows/BUG-20260828-052400-workflows/03-delete-dialog-second-card-still-no-name.png`

### Browser Signals
- Console: none observed
- Network: none observed (dialog is client-rendered before any delete request fires; both repros were cancelled, no deletion performed)
- State/URL: URL stays `/workflows` throughout; dialog accessible-name/heading text confirmed identical across both cards via full a11y snapshot, not just visual screenshot

## BUG-20260828-052800-create-ppt-r2 — "Save as my version" on `/create/ppt` silently discards the entered brief and selected template, always saving the same static generic record

- **Page:** PPT wizard shell
- **Route:** /create/ppt
- **Severity:** High
- **Status:** CLOSED
- **Found at:** 2026-08-28 05:28 UTC
- **Found by:** bug-create-ppt-r2
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic on every cold-start attempt, no axis narrowing needed. Root cause: `handleSaveAsOverride` in `frontend/src/components/workflow/LaunchWizard.tsx:727` never threads `brief`/`selectedTemplateId`/`selectedDsId` into the save payload, unlike `handleLaunch`.
- **Issue card:** [ISS-226](../.knowledge/cards/20260828-1550-ISS-226.md)
- **Fingerprint:** `/create/ppt|save-as-my-version|click-save-as-my-version-with-brief-and-template-set|payload-and-saved-record-never-reflect-form-state`
- **Evidence:** `bug-hunter/evidence/create-ppt/BUG-20260828-052800-create-ppt-r2/`
- **Root cause (CONFIRMED, re-read independently):** `handleSaveAsOverride` (`frontend/src/components/workflow/LaunchWizard.tsx:727-754`) hardcodes `name`/`description` and calls `buildWorkflowManifest(pipelineAgents, undefined, selectionsRef.current)` — never `brief`, `selectedTemplateId`/`customTemplateBody`, or `selectedDsId`/`customDsBody`. Contrast with the sibling `handleLaunch` (lines 756-804), which threads every one of those into `buildLaunchDraft`, proving the state is live at click time. Structural finding: the current `WorkflowManifest`/`WorkflowCapabilities` TS contract (`frontend/src/types/index.ts:563-648`) has no field for a template id, design-system id, or brief text at all — only `steps`, `capabilities.internet`, `deliverable`, `planner`, `clarify` — so a full fix (persisting the template choice, not just the cosmetic name/description) is INFERRED to need a schema addition, not just plumbing; unconfirmed against the backend compiler.
- **Blast radius (grepped every caller of `handleSaveAsOverride`/`createUserWorkflow` in `frontend/src/`):** exactly 2 independent implementations of this "save as override" pattern in the whole frontend — `LaunchWizard.tsx:727` (this bug) and `IdeaInputPage.tsx:1460` (already partly covered by ISS-225's gates finding, but NOT its brief/description omission). `LaunchWizard.tsx`'s function is shared, unconditional on `mode`, by all 3 modes (`ppt`/`prototype`/`ppt_v2`) and reachable at `/create/ppt`, `/create/prototype`, `/create/ppt_v2`, and `/workflows/{id}/run` for a ppt/prototype override — same broken code, not per-mode branches.
- **Fixed:** 2026-08-28 — [FIX-336](../.knowledge/cards/20260828-2201-FIX-336.md). `overrideDescription()` added to `frontend/src/store/api/userWorkflows.ts`; both `handleSaveAsOverride` copies (`LaunchWizard.tsx:735`, `IdeaInputPage.tsx:1467`) now build `description` from the live brief/template/design-system. Schema question settled: `manifest`/`selections` are mutually exclusive (`user_workflows.py:66`) and `_ALLOWED_TOP_KEYS` (`manifest.py:266`) bars a new manifest key, so restoring the selection on reopen needs a schema decision — deferred to [ISS-377](../.knowledge/cards/20260828-2202-ISS-377.md). Verified: all 4 tests in `tests/integration/e2e/suites/03_launch_panels/test_save_as_my_version_discards_brief.py` XPASS(strict).
- **Fix belongs:** inside `handleSaveAsOverride` in each of the two files (each has exactly one caller already, so no shared-helper extraction is required to reach every caller) — not per-route, since all reachable routes share one of these two functions.
- **Issue cards:** [ISS-226](../.knowledge/cards/20260828-1550-ISS-226.md) (root), [ISS-279](../.knowledge/cards/20260828-1901-ISS-279.md) (sibling: `/create/prototype` + `/create/ppt_v2` share the same broken function), [ISS-280](../.knowledge/cards/20260828-1902-ISS-280.md) (sibling: `IdeaInputPage.tsx`'s own `handleSaveAsOverride` also hardcodes description and drops the brief, on every other pipeline type)
- **Verified:** 2026-08-28 — all 4 tests in `tests/integration/e2e/suites/03_launch_panels/test_save_as_my_version_discards_brief.py` ran XPASS(strict) (frontend-only fix, no restart needed), `xfail` markers removed, re-run plain green (4 passed). Manual re-run of the original repro on `/create/ppt` (lane5, qa-admin, fresh load): filled a distinctive brief, selected "Minimal Keynote", clicked "Save as my version" — captured `POST /api/user-workflows` body: `description` now reads `"Template: html-ppt-dir-key-nav-minimal\n\nVERIFIER manual repro brief zz99yy88..."`, no longer the static literal. `/workflows` card confirmed the same text on screen. No new console errors. `npx tsc --noEmit` clean on the three changed files (pre-existing errors in `HomeLaunchGrid.crossAccountLeak.test.tsx` and `listenerMiddleware.test.ts` are other agents' working-tree files, untouched here). `lint-imports` (run from `backend/`) shows one pre-existing broken contract (`agents.execution_engine.engine` -> `app.api`) unrelated to this frontend-only change — not introduced by this fix. Regression guard `suites/03_launch_panels/test_launch_panels.py::test_save_as_my_version_creates_a_user_override_of_a_built_in` (S-03-15) PASS.

### Summary
On `/create/ppt`, filling in the brief textarea and selecting a template (confirmed via a
"Use this template" click in the preview modal, leaving the visible checkmark on the card), then
clicking "Save as my version", fires `POST /api/user-workflows` — but the request body is a
static, hardcoded generic payload: `name: "My presentation"`, `description: "Your saved version
of this workflow."`, and a generic 3-step `ppt-brief-analyst → ppt-composer → ppt-validator`
manifest with no template id, no design-system selection, and no brief text anywhere in it. This
was independently verified across two separate trials with materially different page state
(trial 1: "Clean Slide Deck" template, empty brief; trial 2: "Minimal Keynote" template, a
distinct custom brief string) — both requests were byte-for-byte identical, and both responses
returned the exact same existing record id (`da92b4a4-7eff-41b5-9b9a-205cfa1616d9`, `created_at`
unchanged, only `updated_at` bumped). Visiting `/workflows` afterward confirms the saved card
shows only the static generic name/description/agent-count — no trace of either trial's brief or
template selection. The action gives no error and returns `201 Created`, so the user has every
indication the save succeeded and captured their configuration, when in fact none of their input
was persisted at all. This is a distinct defect from the already-filed `/create/ex_A4_human_divert`
422 (that one fails loudly) and the `/workflows/ppt/canvas` "Save as copy" manifest-loss bug
(different route/component/trigger — that one is a canvas manifest-translation loss, this one is
the brief-composer's quick-save ignoring current form state entirely, always upserting the same
one static record).

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/ppt` (fresh load).
2. Type a brief into the textarea, e.g. "R2 lead-3 test brief for save-as-my-version template
   persistence check".
3. Click the "Minimal Keynote" template card, then "Use this template" in the preview modal —
   the card shows a selected checkmark.
4. Click "Save as my version". Observe the fired `POST /api/user-workflows` request body: `name`,
   `description`, and `manifest` are the same static generic values regardless of the brief text
   or selected template; response is `201 Created` with no visible error or distinguishing
   confirmation.
5. Navigate to `/workflows`. Locate the "My presentation" card — its description reads "Your
   saved version of this workflow." with 3 agents; no mention of the brief text or "Minimal
   Keynote" anywhere.
6. Repeated from a fresh `/create/ppt` load with a different template ("Clean Slide Deck") and an
   empty brief — the resulting `POST /api/user-workflows` body was identical to step 4's, and the
   response returned the same existing record id with `created_at` unchanged (only `updated_at`
   bumped) — confirming the endpoint always upserts one static generic record rather than saving
   the current configuration.

### Expected
"Save as my version" should persist the user's actual current configuration — the entered brief
and the selected template (or design-system choice) — as a new or updated saved workflow, so the
saved record reflects what was on screen when the user clicked save.

### Actual
The saved workflow is always the same static generic placeholder ("My presentation" / "Your saved
version of this workflow." / generic 3-step manifest), regardless of what brief text or template
was on the page. The brief and template selection are silently discarded; the button reports
success (`201 Created`) with no indication that nothing the user entered was actually saved.

### Evidence
- Before (Minimal Keynote selected, custom brief filled): `bug-hunter/evidence/create-ppt/BUG-20260828-052800-create-ppt-r2/01-before-brief-and-template-selected.png`
- After (workflows list card shows only static generic content, no trace of the brief/template): `bug-hunter/evidence/create-ppt/BUG-20260828-052800-create-ppt-r2/02-after-workflows-card-no-trace-of-input.png`
- Request/response bodies from both trials: `bug-hunter/evidence/create-ppt/BUG-20260828-052800-create-ppt-r2/network.log`

### Browser Signals
- Console: no relevant error observed.
- Network: `POST /api/user-workflows` returns `201 Created` both trials; request body identical
  across trials with different brief/template state; response reuses the same record id
  (`da92b4a4-7eff-41b5-9b9a-205cfa1616d9`) with unchanged `created_at`.
- State/URL: stays on `/create/ppt` throughout the save action (no navigation, no toast observed);
  verified end-to-end via the resulting `/workflows` card.

## BUG-20260828-053300-create-prototype-r2 — "Upload custom template → From URL" leaks a raw Python errno/socket message to the user on an unreachable domain

- **Page:** Prototype wizard shell
- **Route:** /create/prototype
- **Severity:** Low
- **Status:** CLOSED
- **Fixed:** 2026-08-29 — one-line chokepoint fix, `backend/app/api/prototype_templates.py:387-392`: the catch-all's `detail=f"URL fetch failed: {exc}"` is now the fixed string "Could not reach that URL. Check the address and try again.", with the existing `logger.warning(..., exc)` untouched so the raw errno stays server-side. Backend-only — no frontend file changed, because every caller (`CustomTemplateModal.tsx:105`, live from BOTH `TemplateGallery.tsx:88` and `PPTTemplateGallery.tsx:88`; plus the still-dead `store/api/prototype.ts:60`) terminates in this one function, so both `/create/prototype` and `/create/ppt` are covered at once. Test, one file: `cd backend && python3.11 -m pytest tests/unit/test_prototype_fetch_url_error_leak.py -q` — pre-fix `2 xfailed, 1 warning in 2.29s`, post-fix `2 failed, 1 warning in 2.01s` where both failures are `[XPASS(strict)]` (the fix signal); the captured log confirms `logger.warning` still holds the raw `[Errno 8] nodename nor servname provided, or not known`. xfail markers deliberately LEFT IN PLACE for 6-verifier. `lint-imports` from `backend/`: 3 kept / 1 broken — the broken contract is pre-existing at 2a622c951 and unrelated (its `kernel_services -> app.api.run_engine` edge is present verbatim at HEAD; this diff adds zero imports). SC-001 untouched (nothing under `execution_engine/`), no migration. `*.py`-only change, so --reload picks it up; no restart needed. Cards: FIX-396; ISS-343 and ISS-584 set resolved.
- **Verified:** 2026-08-29 by 6-verifier. Backend already serving (`:8000/docs` -> 200, `--reload` picked up the `.py`-only change, no restart needed). `cd backend && python3.11 -m pytest tests/unit/test_prototype_fetch_url_error_leak.py -q` — confirmed both `[XPASS(strict)]` pre-removal (`2 failed, 1 warning in 1.47s`, captured log still shows the raw `[Errno 8] nodename nor servname provided, or not known` going only to `logger.warning`), then removed both `@pytest.mark.xfail(...)` lines (kept `@pytest.mark.issue(...)`), re-ran: plain `2 passed, 1 warning in 1.60s`. Manual re-repro in the browser (lane6, signed in as qa-admin, `/create/prototype` -> Template tab -> "Upload custom" -> "From URL" -> `http://example.invalid.nonexistent-domain-xyz123/` -> Fetch): inline error now reads "Could not reach that URL. Check the address and try again."; network response body for `GET /api/prototype/fetch-url?...` is `{"detail":"Could not reach that URL. Check the address and try again."}` — no "Errno"/"nodename" anywhere in the page or the response. The expected `502 Bad Gateway` console entry is still present (unchanged pre-existing signal, only the body text changed). Modal cancelled cleanly afterward. Regression: `backend/tests/unit/test_prototype_run_request.py` (same module family) — `5 passed` clean. `lint-imports` from `backend/`: 3 kept / 1 broken, same pre-existing `kernel_services -> app.api.run_engine` edge, unrelated to this diff. `frontend && npx tsc --noEmit`: only pre-existing unrelated test-file errors (`login.a11y.test.tsx`, `HomeLaunchGrid.crossAccountLeak.test.tsx`, `api.sessionExpiryRedirect.test.ts`, `listenerMiddleware.test.ts`) — none touch `prototype_templates.py` or `CustomTemplateModal.tsx`; fix is backend-only so frontend build health is unaffected. After-screenshot: `bug-hunter/evidence/create-prototype/BUG-20260828-053300-create-prototype-r2/05-after-friendly-error.png`. `/create/ppt` (ISS-584 sibling) was not independently re-driven live — the wizard did not reach the Template step's "Upload custom" control on that route within this pass — but the fix is at the shared backend chokepoint (`fetch_url_for_template`, the only endpoint either gallery's `CustomTemplateModal` calls) and is covered by the same test, matching the cards' own "one fix closes both routes" reasoning.
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — deterministic across three distinct unreachable domains, no axis variation needed
- **Root cause:** CONFIRMED — `backend/app/api/prototype_templates.py`'s `fetch_url_for_template`
  (`:325-389`), final exception clause (`:387-389`): `except Exception as exc: ...
  raise HTTPException(status_code=502, detail=f"URL fetch failed: {exc}")` interpolates
  `str(exc)` straight into the HTTP `detail` with no translation, catching everything the two
  narrower/safe handlers above it (`httpx.TimeoutException`, `httpx.HTTPStatusError`) miss.
  `frontend/src/components/workflow/prototype/CustomTemplateModal.tsx`'s `handleFetchUrl`
  (`:110`) then renders `data.detail` verbatim with no message-translation layer. INFERRED
  (reasoned, not executed): the specific exception is `httpx.ConnectError` wrapping the OS
  resolver's `socket.gaierror` — inferred by elimination and the byte-identical error text.
- **Blast radius:** grepped every caller of `/api/prototype/fetch-url` and every render site of
  `CustomTemplateModal` — `frontend/src/store/api/prototype.ts`'s `prototypeApi.fetchUrl` also
  calls the same endpoint but has zero callers anywhere in `frontend/src` (dead code today).
  `CustomTemplateModal` itself is rendered from BOTH
  `frontend/src/components/workflow/prototype/TemplateGallery.tsx:88` (`/create/prototype`, the
  reported route) AND `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx:88`
  (`/create/ppt` — imports the identical component, not a fork), both mounted as interchangeable
  step bodies by `WizardStepper.tsx` under `LaunchWizard.tsx`. Same component, same bug, second
  route.
- **Fix location:** `backend/app/api/prototype_templates.py:387-389` — replace
  `detail=f"URL fetch failed: {exc}"` with a fixed, safe message, keeping the existing
  `logger.warning(..., exc)` for server-side debugging. This is the correct chokepoint: every
  live and dead-code caller terminates in this one function, so fixing it here — rather than
  patching each frontend call site — protects every caller, present and future, in one change.
- **Issue cards:** [ISS-343](../.knowledge/cards/20260828-2059-ISS-343.md) (root — validator-filed,
  confirmed with file:line by re-reading `prototype_templates.py:387-389` and
  `CustomTemplateModal.tsx:94-131` directly), [ISS-584](../.knowledge/cards/20260829-0243-ISS-584.md)
  (sibling, INFERRED: the same `CustomTemplateModal` is also rendered on `/create/ppt` via
  `PPTTemplateGallery.tsx`, unreproduced live)
- **Found at:** 2026-08-28 05:33 UTC
- **Found by:** bug-create-prototype-r2
- **Fingerprint:** `/create/prototype|upload-custom-template-from-url|fetch-unreachable-domain|raw-backend-errno-string-rendered-as-error`
- **Evidence:** `bug-hunter/evidence/create-prototype/BUG-20260828-053300-create-prototype-r2/`

### Summary
On the Template tab's "Upload custom" → "From URL" flow, entering a syntactically valid but
unreachable URL (a DNS name that cannot resolve) and clicking "Fetch" surfaces the backend's raw
Python socket exception text verbatim as the on-page error message: `URL fetch failed: [Errno 8]
nodename nor servname provided, or not known`. This is a distinct, better-behaved code path than
a malformed URL (e.g. `not-a-valid-url`), which correctly shows a friendly, app-authored message
("URL must start with http:// or https://") — proving the modal has a friendly-message path and
simply falls back to dumping the raw backend exception string when the failure originates from
the network fetch itself rather than client-side validation. `GET
/api/prototype/fetch-url?url=...` returns `502 Bad Gateway` with body
`{"detail":"URL fetch failed: [Errno 8] nodename nor servname provided, or not known"}`, and the
frontend renders that `detail` string unmodified. Reproduced deterministically with two different
unreachable domains, both producing byte-identical error text. This is a distinct mechanism from
the already-filed raw-backend-error bugs on this ledger (the `/handoff/settings` PAT length-422
echoing the submitted secret value, and `/create` "Save as my version" 422 manifest-validation
text) — different route, different component (URL-fetch, not save/validation), and a different
class of leaked internal detail (an OS-level socket errno, not a Pydantic validation payload).

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/prototype`, Template tab.
2. Click "Upload custom" → "From URL" tab in the "Upload custom template" modal.
3. Type `http://example.invalid.nonexistent-domain-xyz123/` into the Template URL field, click
   "Fetch". Observe: `GET /api/prototype/fetch-url?...` returns `502 Bad Gateway`; the modal
   displays "URL fetch failed: [Errno 8] nodename nor servname provided, or not known" as the
   inline error, verbatim from the backend response body.
4. Cleared the field and repeated with a second, different unreachable domain
   (`https://another-totally-fake-domain-abc987.invalid/`) — identical `502` and byte-identical
   raw errno text rendered on-page, confirming deterministic reproduction.
5. Contrast: typing a malformed non-URL string (`not-a-valid-url`) and clicking "Fetch" instead
   shows a friendly, app-authored validation message ("URL must start with http:// or https://"),
   proving the friendly-message path exists and is simply bypassed for network-fetch failures.
6. Cleaned up: clicked "Cancel" to close the modal; no template was uploaded/saved; wizard left in
   a normal, clean state.

### Expected
A network-level fetch failure (unresolvable domain, connection refused, timeout, etc.) should be
translated into a friendly, human-readable message (e.g. "Could not reach that URL — check the
address and try again"), consistent with how the modal already handles client-side URL-format
validation, never a raw OS/Python exception string surfaced to the end user.

### Actual
The modal renders the backend's raw internal exception text unmodified: "URL fetch failed:
[Errno 8] nodename nor servname provided, or not known" — an implementation-detail string that
leaks the backend's runtime/OS and gives the user no actionable guidance.

### Evidence
- Before (Upload custom template modal open, From URL tab): `bug-hunter/evidence/create-prototype/BUG-20260828-053300-create-prototype-r2/01-before-upload-modal-open.png`
- Contrast (malformed URL shows friendly app-authored error): `bug-hunter/evidence/create-prototype/BUG-20260828-053300-create-prototype-r2/02-malformed-url-friendly-error.png`
- Failure (unreachable domain #1, raw errno text rendered): `bug-hunter/evidence/create-prototype/BUG-20260828-053300-create-prototype-r2/03-failure-raw-errno-leaked.png`
- Second reproduction (unreachable domain #2, byte-identical raw errno text): `bug-hunter/evidence/create-prototype/BUG-20260828-053300-create-prototype-r2/04-repro2-raw-errno-leaked.png`
- Network log: `bug-hunter/evidence/create-prototype/BUG-20260828-053300-create-prototype-r2/network.log`

### Browser Signals
- Console: `Failed to load resource: the server responded with a status of 502 (Bad Gateway) @
  http://localhost:8000/api/prototype/fetch-url?url=...` on each unreachable-domain attempt.
- Network: `GET /api/prototype/fetch-url?url=...` → `502 Bad Gateway`, response body
  `{"detail":"URL fetch failed: [Errno 8] nodename nor servname provided, or not known"}` on both
  trials, byte-identical.
- State/URL: stays on `/create/prototype` throughout; modal remains open after the failed fetch;
  cleanly cancelled with no residual state.

## BUG-20260828-053745-create-app-r2 — Oversized text attachment (.txt/.md/.json/.csv) is silently truncated with zero user-visible indication, unlike the equivalent PDF/DOCX/PPTX path

- **Page:** Create app — simple launch panel
- **Route:** /create/app
- **Severity:** Medium
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — deterministic, no axis variation needed
- **Issue card:** [ISS-312](../.knowledge/cards/20260828-1941-ISS-312.md)
- **Verified:** 2026-08-29 (6-verifier) — `IdeaInputPage.textTruncation.test.tsx` XPASS confirmed,
  `it.fails` marker removed, re-run plain green 1/1. Regression: `IdeaInputPage.imageInput.test.tsx`
  2/2, `composer/ComposerPage.test.tsx` 14/14, `tsc --noEmit` 0 new errors (6 pre-existing,
  unrelated files). Backend `:8000/docs` 200 (frontend-only change, no restart needed). Manual
  browser re-run of the exact repro below (qa-admin, cold `/dashboard` → `/create/app`, huge.txt
  500,000 `'a'` chars, intercept-and-abort `POST /api/runs`): captured body length 450274 (was
  450236), tail `...aaaa\n[Content truncated to 450,000 chars]\n=== End: huge.txt ===`,
  `containsTrunc` true (was false). After-screenshot
  `bug-hunter/evidence/create-app/BUG-20260828-053745-create-app-r2/04-after-fix-chip.png`.
  `backend/` `lint-imports`: 1 pre-existing broken contract, unrelated (zero Python files
  touched by this fix).
- **Fixed:** 2026-08-29 — [FIX-374](../.knowledge/cards/20260829-0146-FIX-374.md). New shared `truncateAttachmentText()` in `frontend/src/lib/constants.ts` appends the binary path's existing `[Content truncated to 450,000 chars]` note; `handleFiles()`'s `isTextFile` branch (`frontend/src/components/workflow/IdeaInputPage.tsx:520`) now calls it instead of slicing bare. One hunk in the shared `useBriefAttachments()` hook covers `/create/app`, `/create/user_stories`, `/create/mulesoft_to_springboot`, `/create/dotnet_to_azure` and both ComposerPage views. Sibling ISS-423 (`LaunchWizard.tsx`, a forked duplicate serving `/create/ppt` + `/create/prototype`) and ISS-422 (concierge chat lane) stay open — different files, different owners. Verified: `frontend/src/components/workflow/IdeaInputPage.textTruncation.test.tsx` `it.fails` now reports `Error: Expect test to fail` (vitest XPASS signal, marker left in place); IdeaInputPage.imageInput.test.tsx 2/2 green, composer/ComposerPage.test.tsx 14/14 green, `tsc --noEmit` 0 errors in either touched file.
- **Found at:** 2026-08-28T05:37:00Z
- **Found by:** bug-create-app-r2
- **Fingerprint:** `/create/app|brief-attach-file-text-type|attach-text-file-over-450000-chars-and-run|content-silently-truncated-no-warning-anywhere`
- **Evidence:** `bug-hunter/evidence/create-app/BUG-20260828-053745-create-app-r2/`
- **Root cause:** CONFIRMED — `useBriefAttachments()`'s `handleFiles()` in
  `frontend/src/components/workflow/IdeaInputPage.tsx:512-546`: the `isTextFile` branch
  (`:514-523`) does `content.slice(0, ATTACH_MAX_CHARS)` with the truncation flag never
  computed at all, while the sibling `isBinaryFile` branch (`:524-535`) computes `res.truncated`
  server-side and appends a visible `[Content truncated to N chars]` note. `ATTACH_MAX_CHARS =
  450000` (`frontend/src/lib/constants.ts:7`).
- **Blast radius:** `useBriefAttachments()`/`handleFiles()` is shared (INV-3, one implementation)
  by `IdeaInputPage.tsx` — reached at `/create/app`, `/create/user_stories`,
  `/create/mulesoft_to_springboot`, `/create/dotnet_to_azure` (FIX-304) — and by
  `ComposerPage.tsx`'s Simple AND Canvas views (the workflow composer, a separate page); one fix
  there covers all of those. Two independent forked/adjacent implementations do NOT route
  through it and need their own handling: `LaunchWizard.tsx:onFilesPicked` (`/create/ppt`,
  `/create/prototype` — CONFIRMED byte-for-byte duplicate of the same broken branch) and the
  concierge chat lane's `useChatAttachments.ts` (INFERRED — computes the flag correctly but it is
  dropped before reaching the user or the backend prompt block).
- **Fix location:** `IdeaInputPage.tsx:514-523`'s `isTextFile` branch needs its own
  `content.length > ATTACH_MAX_CHARS` check + note, mirroring the branch below it. Since
  `LaunchWizard.tsx:653-659` carries the textually identical branch, the smallest correct fix is
  one shared helper both files call, not two hand-patches.
- **Issue cards:** [ISS-312](../.knowledge/cards/20260828-1941-ISS-312.md) (root, CONFIRMED),
  [ISS-423](../.knowledge/cards/20260829-0026-ISS-423.md) (sibling: LaunchWizard.tsx fork,
  INFERRED), [ISS-422](../.knowledge/cards/20260829-0027-ISS-422.md) (sibling: chat lane dropped
  flag, INFERRED)

### Summary
Attaching a plain-text-type file (`.txt`/`.md`/`.json`/`.csv`) whose content exceeds the
450,000-character `ATTACH_MAX_CHARS` limit gets its content silently sliced to that limit before
being sent in the run payload, with absolutely no indication anywhere in the UI (chip, toast, or
the sent brief text itself) that truncation occurred. The sibling binary path (`.pdf`/`.docx`/
`.pptx`, extracted server-side via `extractFileText`) hits the exact same limit but explicitly
appends a visible `"[Content truncated to 450,000 chars]"` note into the content block that is
sent to the agent. The two code paths in the same `handleFiles()` function apply identical
truncation but only one of them tells anyone it happened — a user (or the downstream agent
reading the brief) has no way to know a large `.txt`/`.md`/`.json`/`.csv` attachment lost data.

### Reproduction
1. Sign in as qa-admin, go to `http://localhost:3000/create/app` (fresh load).
2. Type any brief text, e.g. "Summarize the attached notes into user stories."
3. Click "+ Attach file", select a `.txt` file whose content is far larger than 450,000
   characters (repro used a ~31MB `huge.txt` of repeated `a` characters).
4. Observe the attachment chip: it shows only the filename `huge.txt`, no size, no warning.
5. Click "Run workflow". Intercepted the outgoing `POST /api/runs` request with
   `page.route()` and aborted it client-side before it reached the backend (so no real run was
   created) purely to inspect the payload the browser had already assembled.
6. Inspect the `message` field of the intercepted body: it contains the file block
   `=== Attached: huge.txt ===\n` followed by content sliced to exactly 450,000 characters,
   ending directly at `=== End: huge.txt ===` with no truncation marker anywhere in the string.
7. Repeated the full sequence (steps 1–6) a second time from a fresh `/create/app` page load,
   both with `huge.txt` alone and combined with a small `valid.md` attachment — identical result
   both times: `containsTrunc` (payload contains the word "truncat") is `false` in both runs.

### Expected
When a text-type attachment's content is cut to fit `ATTACH_MAX_CHARS`, the user should see the
same visible signal the binary path already provides — either a truncation note appended to the
sent content (matching the PDF/DOCX/PPTX behaviour), a visible warning near the file chip, or
outright rejection of files over the limit with a clear error.

### Actual
The content is silently sliced with `content.slice(0, ATTACH_MAX_CHARS)` and stored with no
truncation flag or note at all. The file chip shows only the filename. Nothing in the UI or the
payload sent to the agent indicates data was dropped.

### Evidence
- Before (huge.txt attached, chip shows filename only, no size/warning):
  `bug-hunter/evidence/create-app/BUG-20260828-053745-create-app-r2/01-before-huge-attached-chip.png`
- Network payload evidence (two independent intercept-and-abort repros, exact body lengths and
  tails showing truncation with no marker):
  `bug-hunter/evidence/create-app/BUG-20260828-053745-create-app-r2/network.log`

### Browser Signals
- Console: none relevant (the two `Failed to fetch` errors seen during the repro are from this
  investigation's own `route.abort()` calls, not application-caused).
- Network: `POST http://localhost:8000/api/runs` body length 450,236–450,427 chars (~450,000
  from the file content plus the brief/wrapper text) with `"truncat"` absent from the string in
  both reproductions; no run was actually created (request aborted client-side before dispatch).
- State/URL: stayed on `/create/app` throughout; no server-side effect.

### Source (read only to explain the observed behaviour, not as a substitute for testing)
`frontend/src/components/workflow/IdeaInputPage.tsx` `handleFiles()`: the `isTextFile` branch
(`.txt/.md/.json/.csv`) does `content.slice(0, ATTACH_MAX_CHARS)` with no truncation note; the
`isBinaryFile` branch (`.pdf/.docx/.pptx`) calls `extractFileText()` and appends
`` `\n[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]` `` when
`res.truncated` is true. `ATTACH_MAX_CHARS = 450000` in `frontend/src/lib/constants.ts`. The
chip render (~line 629) shows only `file.name`, no size or truncation state, for either path.

## BUG-20260828-054500-create-user-stories — The "Add agent" library's own "User Stories" category tab always shows "No agents found", even for a bare text search

- **Page:** User-stories launch panel — Advanced Workflow Configuration modal
- **Route:** /create/user-stories
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `frontend/src/components/workflow/AgentLibrary.userStoriesEmpty.test.tsx`
  ran XPASS ("Error: Expect test to fail") confirming the fix, `it.fails` marker removed,
  re-ran plain green (1/1); `overrideAgentPool.source.test.ts` (10/10) and
  `AgentsPopup.reskin.test.tsx` (14/14) green, no regressions; manual repro re-run in-browser on
  `/create/user-stories` → Advanced 7 agents → "+ Add agent" → User Stories tab now reads "All
  User Stories agents are already on your canvas" (search term "agent" too), no console errors;
  `npx tsc --noEmit` shows zero AgentLibrary diagnostics (pre-existing unrelated errors in other
  files untouched by this fix); `eslint AgentLibrary.tsx` 0 errors/3 pre-existing warnings;
  backend `:8000/docs` 200 (frontend-only change, no restart needed); `lint-imports` (run from
  `backend/`) shows 1 pre-existing broken contract unrelated to this change (kernel→app.api via
  `kernel_services`/`revision_analyzer`), not introduced here.
- **Found at:** 2026-08-28 05:45 UTC
- **Found by:** bug-create-user-stories-r2
- **Fingerprint:** `/create/user-stories|advanced-modal-add-agent-dialog|select-user-stories-category-tab|no-agents-found-for-own-pipelines-category-even-on-search`
- **Evidence:** `bug-hunter/evidence/create-user-stories/BUG-20260828-054500-create-user-stories/`
- **Validated:** 3/3 on 2026-08-28, every cycle — deterministic, no cold-start variation needed
- **Root cause:** `AgentLibrary.tsx`'s `filteredAgents` (`:104-117`) excludes every agent already
  in `existingAgentIds`, and its own-category tab defaults active on open (`activeCategory =
  currentPipelineType || "all"`, `AgentLibrary.tsx:86`); the default `/create/user-stories`
  workflow pre-seeds all 6 `user_stories`-tagged catalog agents as existing steps, so that
  category is empty by construction, not by a fetch/tagging bug (confirmed via
  `GET /api/agents/library`, 94 agents, 6 tagged `user_stories`).
- **Blast radius:** all 4 production `AgentLibrary` render sites traced
  (`app/workflow/page.tsx`, `WorkflowView.tsx`, `AgentsPopup.tsx`, `composer/ComposerPage.tsx`);
  2 host surfaces reproduce the identical seeding pattern for every non-custom pipeline type —
  `IdeaInputPage.tsx:902` (`/create/<type>`) and `LaunchWizard.tsx:147-148`
  (`/workflows/<id>/run`, no saved override); a distinct trigger on the same default-category
  line reproduces via `IdeaInputPage.tsx`'s unguarded "Advanced" button on the `migration`
  meta-type before a sub-pipeline is chosen. `ComposerPage.tsx` (custom-only) and the two
  no-`currentPipelineType` hosts are not affected.
- **Proposed fix location:** inside `AgentLibrary.tsx`'s own default-category-selection /
  empty-state logic (`:86`, `:229-232`) — a single guard closes every host and every pipeline
  type at once, rather than patching each of the 4 callers separately.
- **Issue cards:** [ISS-311](../.knowledge/cards/20260828-1740-ISS-311.md) (root — confirmed
  root cause, amended with this pass's blast-radius section),
  [ISS-420](../.knowledge/cards/20260829-0021-ISS-420.md) (sibling, INFERRED: `migration`
  meta-type passes an unrecognized `currentPipelineType`, no tab highlights at all),
  [ISS-421](../.knowledge/cards/20260829-0020-ISS-421.md) (sibling, INFERRED: same defect
  generalizes to every non-custom pipeline type, from both `IdeaInputPage.tsx` and
  `LaunchWizard.tsx`)
- **Fix card:** [FIX-376](../.knowledge/cards/20260829-0152-FIX-376.md) — `AgentLibrary.tsx`
  only: the single `ALL_AGENTS.filter` is split into `categoryAgents` (category/search/hidden/
  template gates) and `filteredAgents` (that result minus `existingAgentIds`), so
  `filteredAgents.length === 0 && categoryAgents.length > 0` can render "All User Stories agents
  are already on your canvas" where the unconditional "No agents found" used to be. Fixed in the
  shared component, so every pipeline type and both hosts (`IdeaInputPage.tsx`,
  `LaunchWizard.tsx`) are covered — ISS-421's generalization included. ISS-420 (unrecognized
  `currentPipelineType`, e.g. `migration`, highlighting no tab at all) is NOT closed by this: it
  needs the `:86` default-category line guarded and stays open. Frontend test
  `frontend/src/components/workflow/AgentLibrary.userStoriesEmpty.test.tsx` XPASS ("Expect test
  to fail", `it.fails` marker left in place for 6-verifier); `overrideAgentPool.source.test.ts`
  10/10 and `AgentsPopup.reskin.test.tsx` 14/14 still green. Frontend-only — no backend restart,
  no migration, no engine or import-linter surface touched.

### Summary
On `/create/user-stories`, opening Advanced → Agents → any "+ Add agent" placeholder opens the
"Add agent" library dialog defaulted to the **"User Stories"** category tab (the page's own
pipeline). That tab renders "No agents found" immediately on open, with no interaction needed to
reproduce it. Every sibling category tab (PPT, Prototype, App Builder, MuleSoft to Spring Boot,
.NET to Azure, Custom, and All) returns a populated list of addable agents when selected. Typing
a maximally generic search term ("agent") into the search box while the User Stories tab is
active still returns "No agents found" — this isn't a narrow filter miss, the category has zero
catalog entries tagged for it at all, so the "+ Add agent" affordance on this specific launch
panel's canvas can never actually add anything from the panel's own pipeline category.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/user-stories` (fresh load).
2. Click "Advanced 7 agents" to open the Advanced Workflow Configuration modal, Agents tab.
3. Click any "+ Add agent" canvas placeholder to open the "Add agent" library dialog. Observe it
   opens with "User Stories" already the active/highlighted tab, and the body immediately reads
   "No agents found" — no click needed to trigger it.
4. Click the "All" tab: a full multi-category list of addable agents renders (App Builder,
   Prototype, PPT, MuleSoft, Custom entries all present).
5. Click ".NET to Azure": populated with its own agents (not empty), confirming other
   category-specific tabs work correctly.
6. Click back to "User Stories": empty again ("No agents found"), reproducing the same state a
   second time from a fresh tab reselection.
7. With "User Stories" still active, type the generic term `agent` into "Search agents": still
   "No agents found" — ruling out an overly narrow default filter, since a search this broad
   would match almost anything in a working category.

### Expected
The "Add agent" library's category tab matching the current pipeline (User Stories) should list
addable User-Stories-tagged agents (or, if none exist by design, the tab should not be offered /
should not default-select as the opening tab, and should not silently imply that no agents exist
to add rather than that the category is empty by design). At minimum, a generic search should
surface something if any catalog agent anywhere is loosely relevant.

### Actual
The "User Stories" tab — the modal's own default/home category — is unconditionally empty, on
first open and on every reselection, with or without a search term. No agent can be added to a
User Stories workflow from its own category tab; a user must know to switch to "All" or another
pipeline's tab to add anything at all.

### Evidence
- Default open state (User Stories tab pre-selected, empty): `bug-hunter/evidence/create-user-stories/BUG-20260828-054500-create-user-stories/01-dialog-opens-defaulted-to-user-stories-tab-empty.png`
- Reproduced after switching away and back: `bug-hunter/evidence/create-user-stories/BUG-20260828-054500-create-user-stories/02-repro-reselect-user-stories-tab-still-empty.png`
- Generic search term still empty: `bug-hunter/evidence/create-user-stories/BUG-20260828-054500-create-user-stories/03-search-agent-term-still-empty.png`
- Full dialog context with sidebar: `bug-hunter/evidence/create-user-stories/BUG-20260828-054500-create-user-stories/04-dialog-view-with-sidebar.png`

### Browser Signals
- Console: no error logged on any tab switch or search.
- Network: no failed request observed; the agent catalog appears to be loaded client-side/already
  fetched (switching tabs re-renders instantly with no new request), so this is a client-side
  category-filter/tagging gap, not a fetch failure.
- State/URL: URL stays `/create/user-stories` throughout; verified via repeated tab switches and
  a direct accessibility-tree read (not screenshot alone) showing the "No agents found" paragraph
  present under the User Stories tab specifically, absent under All/.NET to Azure.

## BUG-20260828-055300-create-ex-a2-branch — A step's seeded "before-human" gate is invisible in both the Gate combobox and the Review-gates checklist on fresh load

- **Page:** Catalog-driven launch panel for a conditional-gate fixture (Human Gate example)
- **Route:** /create/ex_A4_human_gate
- **Severity:** Medium
- **Status:** CLOSED
- **Found at:** 2026-08-28 05:53 UTC
- **Found by:** bug-create-ex-a2-branch-r2
- **Fingerprint:** `/create/ex_A4_human_gate|advanced-modal-gate-config-and-review-gates-checklist|load-fixture-whose-manifest-step-carries-two-simultaneous-gates|human-review-gate-invisible-in-both-ui-surfaces`
- **Tested:** 2026-08-29 by 4-test-writer — 2 tests added to
  `tests/integration/e2e/suites/03_launch_panels/test_launch_panels.py`:
  `test_seeded_before_human_gate_shows_in_review_gates_checklist_on_fresh_load` (Mechanism A)
  and `test_seeded_before_human_gate_activates_prompt_user_toggle_on_fresh_load` (Mechanism B),
  both `@pytest.mark.issue("ISS-306")` + `xfail(strict=True)`. Ran offline, observed red for the
  exact reasons the card describes.
- **Fixed:** 2026-08-29 by 5-fixer. Three frontend files, two mechanisms, fix card
  [FIX-377](../.knowledge/cards/20260829-0158-FIX-377.md). Mechanism A —
  `ReviewGatesSection.tsx` gains `HUMAN_REVIEW_GATES = [human, before-human]` and
  `isSeedGated(agent, selections)`; the `checkedIds` initializer and the `agentsKey` re-seed
  now go through it, plus a second effect keyed on the seeded-id list so the gates that arrive
  with the workflow fetch (one render AFTER the `agentsKey` re-seed, because the parent's
  `manifestSelections` merge effect runs after this child's) still land. That effect never sets
  `touched` and bails when the user has touched the control, so an untouched launch payload
  still omits `gate_agent_ids`/`selections` (FIX-346 INV-3); `conditional`/`approval`/`security`
  are excluded so ADR-0013's `human` vs `before-human` split is not re-merged. Mechanism B —
  `normaliseRoute()` now maps `route.condition_agent` through `nodeIdOf` exactly as it already
  did `default_next`, in BOTH copies: the shared `frontend/src/lib/manifestAgents.ts:70-83` and
  the un-migrated duplicate at `frontend/src/components/workflow/IdeaInputPage.tsx:1119-1121`
  (the one that actually runs on this repro path). Idempotent, and the same node-id form the
  Prompt User toggle itself already writes; compiler R-27 and the engine's artifact lookup both
  accept either form. Verified: both `@pytest.mark.issue("ISS-306")` tests XPASS(strict) —
  markers left in place for the 6-verifier. No regression: same file's S-03-04 / S-03-12 /
  ISS-247 tests pass, `test_save_manifest_gates.py` 5 passed + 1 unrelated xfail, and 84
  frontend unit tests across 6 files green.
- **Evidence:** `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-055300-create-ex-a2-branch/`
- **Verified:** 2026-08-29 by 6-verifier. Ran
  `tests/integration/e2e/suites/03_launch_panels/test_launch_panels.py -k test_seeded_before_human_gate`
  (venv `tests/integration/e2e/.venv`): both `test_seeded_before_human_gate_shows_in_review_gates_checklist_on_fresh_load`
  and `test_seeded_before_human_gate_activates_prompt_user_toggle_on_fresh_load` showed
  `XPASS(strict)` first, confirming the pass signal; removed both `@pytest.mark.xfail` lines
  (kept `@pytest.mark.issue("ISS-306")`) and re-ran — plain green, 2 passed. Manual re-run of
  the original repro in real Chrome (lane6), qa-admin, same cold-nav-to-`/create/ex_A4_human_gate`
  conditions as the register entry: Review-gates pill now reads "1 agent pause for review" and
  the "Pick Language" checkbox is checked on fresh load with zero interaction (Mechanism A); the
  Advanced modal's Prompt User toggle for the "Pick Language" node shows `aria-checked="true"` on
  fresh load (Mechanism B). Zero new console errors/warnings on the page. After-screenshot:
  `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-055300-create-ex-a2-branch/03-after-fix-prompt-user-on-and-checklist-checked.png`.
  Health: backend `:8000/docs` -> 200 (frontend-only fix, no restart needed); `frontend && npx tsc
  --noEmit` shows only pre-existing unrelated test-file errors in other agents' in-progress
  working-tree files (`HomeLaunchGrid.crossAccountLeak.test.tsx`, `api.sessionExpiryRedirect.test.ts`,
  `listenerMiddleware.test.ts`), none in this fix's files; `cd backend && lint-imports` shows the
  same 1 pre-existing broken contract (`agents.execution_engine.engine` -> `app.api`,
  kernel-boundary scaffold) unrelated to this frontend-only change. Regression: full
  `test_launch_panels.py` file, 18/19 passed — the sole failure,
  `test_checking_a_review_gate_sets_that_agents_gate_in_the_advanced_modal` (ISS-247, `/create/app`),
  is a distinct, pre-existing, already-documented mechanism (the register's own Summary text
  calls it out as "a distinct mechanism from the already-filed /create/app bug") that my diff
  never touched (no xfail was removed from that test) — not caused by this fix, out of scope for
  ISS-306, flagged in NOTE below for a human to look at.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduces on every cold `/create/ex_A4_human_gate` load with zero interaction; no axis variation needed
- **Issue card:** [ISS-306](../.knowledge/cards/20260828-1745-ISS-306.md)
- **Root cause:** Two independent mechanisms, both CONFIRMED by file:line. Mechanism A —
  `ReviewGatesSection.tsx:52,92-96` (`isDefaultGated = a.gate === "Human_Gate"`) seeds
  `checkedIds` only from the static per-AGENT.md `gate` field or a saved run's `initialGateIds`,
  never from the manifest's per-step `gates` array — a `custom-agent` step has no AGENT.md, so
  its `gates: [before-human, conditional]` declaration has no path into the checklist regardless
  of interaction. Mechanism B — `CanvasConfigRail.tsx:730-734`'s "Prompt User" toggle (the
  control actually meant to represent `before-human`) requires `route.condition_agent ===
  prev.id`, but `normaliseRoute()` (`frontend/src/lib/manifestAgents.ts:55-74`, and an
  un-migrated duplicate at `IdeaInputPage.tsx:1100-1117`) normalizes route `outcomes`/
  `default_next` to the canvas node-id form but never `condition_agent` itself, so the bare
  manifest value (`"ask"`) never equals the normalized `prev.id` (`"custom-agent:ask"`) —
  confirmed against `backend/agents/workflows/ex_A4_human_gate/workflow.yaml:104-115`.
- **Blast radius:** `ReviewGatesSection` (Mechanism A) has exactly 2 render sites app-wide —
  `IdeaInputPage.tsx:1924` and `LaunchWizard.tsx:1072` — both inherit the same blank seed.
  `normaliseRoute`/`agentsFromManifest` (Mechanism B) has 2 implementations that must each be
  fixed — the shared `manifestAgents.ts` (used by `LaunchWizard.tsx` and `IdeaInputPage.tsx`'s
  override branch) and `IdeaInputPage.tsx`'s own un-migrated duplicate (the one that actually
  runs on this bug's exact repro path).
- **Issue cards:** [ISS-306](../.knowledge/cards/20260828-1745-ISS-306.md) (root, root cause
  completed in a new "Root cause — CONFIRMED" section), [ISS-419](../.knowledge/cards/20260829-0022-ISS-419.md)
  (sibling, INFERRED: checklist's blank seed is gate-name-agnostic — any manifest-declared gate,
  not just `before-human`, is invisible), [ISS-429](../.knowledge/cards/20260829-0022-ISS-429.md)
  (sibling, INFERRED: `LaunchWizard.tsx`'s `/create/ppt` and `/create/prototype` paths share the
  identical zero-interaction fresh-load blindness, distinct from ISS-361's toggle-required case)

### Summary
`GET /api/workflows/ex_A4_human_gate` returns the "Pick Language" step with
`"gates": ["before-human", "conditional"]` — the manifest genuinely declares this step as both a
human-review pause point and a conditional router. Neither UI surface that is supposed to expose
review-gate state reflects the human-gate half of that on a completely fresh page load, with zero
user interaction: the "Review gates" checklist popover shows "no gates" with every one of the 5
agent checkboxes unchecked (including "Pick Language"), and the Advanced modal's per-agent Config
tab for that same "Pick Language" node renders `Gate` as a single-select combobox pre-set to
"Conditional gate" only — there is no indication anywhere in the UI that this step also carries a
human-review gate. This is a distinct mechanism from the already-filed `/create/app` bug (checking
an agent in the Review-gates checklist doesn't sync to the Advanced modal's Config Gate dropdown):
that defect requires a user action (checking a box) to trigger the desync. Here, no interaction is
needed — the seeded, already-gated fixture data is silently misrepresented the instant the page
loads, and the `Gate` control's single-select model appears structurally unable to represent a
step that carries two gates simultaneously, so the human-review portion has no path to be
displayed, edited, or unset via this UI at all.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/create/ex_A4_human_gate` (fresh load,
   no interaction beyond page load).
2. Click the "Review gates" pill. Observe the popover: pill reads "no gates", and all 5 checklist
   checkboxes (Ask For Language, Pick Language, Say Hello, Say Hola, Say Hallo) are unchecked —
   despite "Pick Language" genuinely carrying a `before-human` gate per the backend manifest.
3. Close the popover, click "Advanced 5 agents" to open "Advanced Workflow Configuration — Human
   Gate".
4. Click the "Pick Language" node, then its "Config" tab. Observe the `Gate` combobox reads
   `option "Conditional gate" [selected]` with no other indicator of a human gate anywhere in the
   panel.
5. Confirmed via API (`GET /api/workflows/ex_A4_human_gate`) that this exact step's `gates` array
   is `["before-human", "conditional"]`, not `["conditional"]` alone.
6. Repeated steps 1-4 on a second fresh page load — identical result both times.

### Expected
A step the backend manifest declares as carrying a `before-human` gate should surface that fact
in at least one of the two UI controls built to expose gate state — the Review-gates checklist
should show that agent checked, and/or the Config Gate control should indicate the human-review
gate is active (or fall back to something other than silently showing only the other gate).

### Actual
Both controls report the step as ungated for human review. The Review-gates checklist shows "no
gates" / all unchecked, and the Config Gate dropdown shows only "Conditional gate" with no trace
of the `before-human` gate the backend manifest actually carries for that step — a real, seeded,
dual-gate configuration is silently reduced to a single gate in the UI on first load, before any
user interaction.

### Evidence
- Review gates checklist, fresh load, "no gates"/unchecked: `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-055300-create-ex-a2-branch/01-review-gates-nogates.png`
- Advanced modal, Pick Language Config tab, Gate shows only "Conditional gate": `bug-hunter/evidence/create-ex-a2-branch/BUG-20260828-055300-create-ex-a2-branch/02-gate-dropdown-conditional-only.png`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/workflows/ex_A4_human_gate` (200) confirmed via direct API call that the
  "Pick Language" step's `gates` field is `["before-human", "conditional"]`; the UI never issues a
  request for gate state beyond this initial load (both controls are purely derived client-side
  from the same fetched manifest).
- State/URL: URL stays `/create/ex_A4_human_gate` throughout; reproduced twice from independent
  fresh page loads with zero prior interaction.

## BUG-20260828-060000-workflow-create-prototype — A path-traversal `mode` value escapes the `/create/<mode>` namespace and navigates to an unrelated real route, including `/admin`

- **Page:** Legacy wizard entry URL for the prototype mode
- **Route:** /workflow/create?mode=../admin (also reproduced with /workflow/create?mode=../ppt and its percent-encoded equivalent ?mode=%2e%2e%2fppt)
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28 by 6-verifier. Ran
  `tests/integration/e2e/suites/16_pages_outside_routes/test_pages_outside_routes.py -k traversal`
  (venv `tests/integration/e2e/.venv`): both `test_a_traversal_mode_value_does_not_escape_the_create_namespace`
  (ISS-227) and `test_a_non_admin_traversal_never_navigates_to_admin` (ISS-281) showed
  `XPASS(strict)` first, confirming the pass signal; removed both `@pytest.mark.xfail` lines
  (kept `@pytest.mark.issue`) and re-ran — plain green, 2 passed. Regression guard
  `-k legacy_wizard_path_redirects` (S-16-04, mode=ppt/prototype) — 2 passed, unaffected.
  Manual re-run of the original repro in real Chrome (lane4), qa-admin, same cold-nav-from-
  `/dashboard` conditions as the register entry, two cycles: `?mode=../admin` and
  `?mode=%2e%2e%2fadmin` both now settle on `http://localhost:3000/create/..%2Fadmin` (stayed
  inside `/create/*`, never reached `/admin`); network log shows only the expected
  `GET /api/workflows/..%2Fadmin` 404 (the known, out-of-scope unrecognized-mode dead-end
  screen), zero `/api/admin/*` calls. After-screenshot:
  `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-060000-workflow-create-prototype/04-after-fix-traversal-stays-in-create.png`.
  Health: backend `:8000/docs` → 200; `frontend && npx tsc --noEmit` shows only the 2
  pre-existing unrelated test-file errors FIX-335 already documented (other agents' in-progress
  working-tree files, not `proxy.ts`); `cd backend && lint-imports` shows 1 broken contract
  (`agents.execution_engine.engine` -> `app.api`, kernel-boundary scaffold) that is unrelated to
  this frontend-only change and pre-existing — not remediated here.
- **Fix:** [FIX-335](../.knowledge/cards/20260828-1959-FIX-335.md) — `frontend/src/proxy.ts:10`
  now encodes `mode` as ONE path segment (`/create/${encodeURIComponent(mode)}`), so `new URL()`
  has no `/` left to resolve a dot-segment against. Live after the change:
  `?mode=../admin` and `?mode=%2e%2e%2fadmin` both 307 to `/create/..%2Fadmin`;
  `?mode=ppt`/`?mode=prototype` still 307 to `/create/ppt`/`/create/prototype`.
  Both xfail(strict) tests in
  `tests/integration/e2e/suites/16_pages_outside_routes/test_pages_outside_routes.py`
  now XPASS (markers left in place for the verifier); S-16-04 (ppt + prototype) still passes.
- **Root cause:** `frontend/src/proxy.ts:10` builds the redirect target via raw string interpolation of the unsanitized `mode` query param into `new URL()`, which performs standard RFC-3986 dot-segment normalization on the resulting path — `mode=../admin` collapses `/create/../admin` to `/admin`. CONFIRMED by reading `frontend/src/proxy.ts` directly. The middleware bypasses `routes.ts` entirely (ADR-0018's "routes.ts is the single source for building and parsing every URL" invariant) and performs zero validation against the known mode set, unlike the sibling client component `frontend/src/app/workflow/create/page.tsx`'s `CreateRoute()`, which already allowlists correctly (`raw === "ppt" || raw === "ppt_v2"`, else default).
- **Blast radius:** grepped every `NextResponse.redirect`/`new URL(` site in `frontend/src` and every backend `RedirectResponse`/`redirect_uri` site in `backend/app` — `proxy.ts:10` is the ONLY unsanitized construction found; no in-app caller ever passes untrusted data into `routes.workflowCreateLegacy` (both call sites, `CreationHub.tsx` and `DashboardLayout.tsx`, use only the literal strings `"ppt"`/`"prototype"`), so the exploit path is exclusively a crafted/shared URL hitting the middleware directly, not anything reachable through in-app navigation. Because dot-segment resolution is unbounded within the origin, ANY of the app's routes behind the `[...view]` catch-all (all ~34 screens, per ADR-0018) or any other top-level route is a reachable redirect target via the same mechanism, not just `/admin` — `/admin` is simply the most sensitive one confirmed live. `/admin`'s own authorization gate (`frontend/src/app/admin/page.tsx:170`, `if (!user.is_admin) { router.replace(routes.dashboard()); return; }`) is client-side and runs only after mount, so whether a non-admin-tier session is fully protected via this same traversal entry point (vs. exposed to a shell/network-call flash before the bounce) is UNVERIFIED — filed as sibling ISS-281.
- **Proposed fix (where it belongs):** `frontend/src/proxy.ts:10` is the only call site, so the fix lands there. Minimal fix mirrors the already-correct sibling pattern at `frontend/src/app/[...view]/page.tsx`'s `createRouteForType` (`` `/create/${encodeURIComponent(type)}` ``) — `encodeURIComponent(mode)` before interpolation neutralizes `/` and therefore dot-segment resolution. More defensive: validate `mode` against the same known-mode allowlist `CreateRoute()` and `routes.ts`'s `parseAppPath` already use, ideally via one shared helper added to `routes.ts` (consistent with ADR-0018) so proxy.ts, `CreateRoute()`, and `parseAppPath` share one definition of "what is a legal mode" instead of a third independent copy.
- **Issue cards:** [ISS-227](../.knowledge/cards/20260828-1554-ISS-227.md) (root), [ISS-281](../.knowledge/cards/20260828-1902-ISS-281.md) (sibling, INFERRED: non-admin-tier exposure to `/admin` via the same traversal is unverified — `/admin`'s only gate is client-side and post-mount)
- **Invariants at risk:** ADR-0018 (routes.ts as sole URL builder/parser) is already violated by `proxy.ts` hand-building `/create/${mode}` independently — a fix that patches only `proxy.ts` in isolation (rather than sourcing the mode allowlist from `routes.ts`) leaves that architectural gap in place even once the traversal itself is closed.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced on every cold-start cycle, both raw `../admin` and percent-encoded `%2e%2e%2fadmin`; root cause is `frontend/src/proxy.ts:10` (`new URL(\`/create/${mode}\`, request.url)` with an unsanitized `mode`)
- **Issue card:** [ISS-227](../.knowledge/cards/20260828-1554-ISS-227.md)
- **Found at:** 2026-08-28 06:00 UTC
- **Found by:** bug-workflow-create-prototype-r2
- **Fingerprint:** `/workflow/create|mode-param-redirect|navigate-with-path-traversal-mode-value|router-escapes-create-namespace-lands-on-unrelated-real-route`
- **Evidence:** `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-060000-workflow-create-prototype/`

### Summary
The already-filed `BUG-20260828-001720-workflow-create-prototype` established that an unrecognized,
non-empty `mode` value gets redirected as `/create/<mode>`, treating the value as a workflow slug
(landing on a dead-end 0-agent composer for a 404'd slug). This is a materially different and more
serious defect: when the `mode` value itself contains a path-traversal segment (`../`, or its
percent-encoded form `%2e%2e%2f`), the redirect target string `/create/<mode>` is evidently built by
unsanitized concatenation and then handed to the router, which resolves the `..` segment and
**escapes the `/create` namespace entirely**, landing on whatever real, unrelated route the
traversal resolves to. `?mode=../ppt` and `?mode=%2e%2e%2fppt` both land on `/ppt` (which
correctly 404s, since no such route exists — the app's normal 404 page renders). But
**`?mode=../admin` lands on `/admin`** and the real admin page renders for real, with live,
successful API calls (`GET /api/admin/users` → 200 OK) — i.e. an entry point that is only ever
supposed to select a workflow-creation mode can be used to navigate straight into the admin
console. Because the signed-in session in this reproduction already had admin privileges, the
admin page's own auth gate did not block it, so this was not observed to bypass authorization —
but the underlying flaw (an unsanitized query parameter being used to construct a client-side
navigation target, allowing a caller to redirect into completely unrelated, non-`/create/*`
application routes) is a genuine, previously undocumented defect in its own right, independent of
whether every possible destination happens to be guarded.

### Reproduction
1. Signed in as qa-admin (session inherited), confirmed via `/api/auth/me`.
2. Navigate to `http://localhost:3000/workflow/create?mode=../ppt`. Observe: `location.href`
   settles on `http://localhost:3000/ppt` (NOT `/create/../ppt` or `/create/ppt`) — the app's
   normal "Page not found." 404 screen renders, confirming the router resolved the `..` segment
   and left the `/create` namespace.
3. Navigate to `http://localhost:3000/workflow/create?mode=%2e%2e%2fppt` (percent-encoded
   equivalent). Observe the identical result: `location.href` settles on `/ppt`, same 404 page.
4. Navigate to `http://localhost:3000/workflow/create?mode=../admin`. Observe: `location.href`
   settles on `http://localhost:3000/admin` — the real Admin console renders (user table,
   filters), with `GET http://localhost:8000/api/admin/users` returning `200 OK` in the network
   log, i.e. this is not a 404 or an error state, it is the actual admin page loading and
   fetching real data.
5. Navigated back to `/dashboard`, then repeated step 4 as a fresh, independent navigation —
   identical result: `location.href` settles on `/admin`, admin page renders again.

### Expected
`/workflow/create?mode=<value>` should only ever navigate within its own intended scope — either
to `/create/<sanitized-value>` (rejecting or stripping path-traversal segments) or to a
"workflow/mode not found" state. It should never be able to construct a navigation target that
resolves outside the `/create/*` namespace into an unrelated, unrequested application route.

### Actual
A `mode` value containing a `../` (or percent-encoded `%2e%2e%2f`) traversal segment causes the
router to resolve out of the `/create` namespace and land on whatever route the traversal
happens to point at. Against a nonexistent target (`../ppt`) this merely produces the app's own
404 page. Against a real route (`../admin`) it lands squarely on the live Admin console with a
successful backend call — a query-parameter-driven client-side navigation that escapes its
intended namespace and reaches an unrelated, sensitive part of the app.

### Evidence
- Before (baseline `/dashboard`): `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-060000-workflow-create-prototype/01-before-dashboard.png`
- Failure (`?mode=../admin` lands on the live `/admin` console): `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-060000-workflow-create-prototype/02-failure-traversal-lands-on-admin.png`
- Reproduced (fresh independent navigation, same result): `bug-hunter/evidence/workflow-create-prototype/BUG-20260828-060000-workflow-create-prototype/03-repro2-traversal-lands-on-admin.png`

### Browser Signals
- Console: no error logged for either the `../ppt` or `../admin` case — the navigation completes
  "successfully" from the browser's point of view in both cases.
- Network: `GET http://localhost:8000/api/admin/users` → `200 OK` confirms the admin page is
  genuinely live, not a stub or error state, when reached via `?mode=../admin`.
- State/URL: `location.href` verified directly via `browser_evaluate` in every case — settles on
  `/ppt` for the nonexistent-target traversal and `/admin` for the real-route traversal, in both
  cases having left the `/create` namespace entirely rather than staying scoped to
  `/create/<mode>`.

## BUG-20260828-060700-workflows-new-r2 — "Save workflow" silently no-ops when the name field is empty, with zero visible feedback and no API request fired

- **Page:** Empty composer / canvas (new custom workflow)
- **Route:** /workflows/new
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `suites/04_composer_canvas/test_iss315_save_empty_name_feedback.py`
  ran XPASS(strict) before the marker removal, plain green after (`xfail` line dropped, `issue`
  marker kept); `ComposerPage.test.tsx` 14/14 green (vitest). Manual repro re-run by hand in
  Chrome (lane4), same conditions as the register entry (qa-admin, cold nav to /dashboard then
  /workflows/new, "Add agent" -> Domain Discovery -> Escape -> 1 agent, name left empty, click
  Save workflow): the "Name the workflow first, then save." banner now renders in
  `text-status-failed` at the bottom of the composer and no `POST /api/user-workflows` fires
  (confirmed via `browser_network_requests`) — screenshots
  `bug-hunter/evidence/workflows-new/BUG-20260828-060700-workflows-new-r2/03-verify-before-1agent-noname.png`
  and `04-verify-after-click-save-banner-visible.png`. No new console errors. Backend
  `:8000/docs` = 200 (frontend-only change, no restart required).
  `frontend`: `npx tsc --noEmit` clean for `ComposerPage.tsx` (pre-existing unrelated errors in
  `HomeLaunchGrid.crossAccountLeak.test.tsx`, `api.sessionExpiryRedirect.test.ts`,
  `listenerMiddleware.test.ts` — untouched by this fix). `backend`: `lint-imports` shows the
  pre-existing "kernel imports only capability ports" break (`agents.execution_engine.kernel_services`
  -> `app.api.user_workflows`) — unrelated, no Python was touched by this fix. Regression file
  `suites/04_composer_canvas/test_composer_canvas.py`: 2 pre-existing failures
  (`test_editing_a_saved_workflow_loads_its_steps`, `test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot`)
  both tied to the separately-tracked PPT deliverable mismatch
  (`BUG-20260828-073350-workflows-ppt-canvas`/ISS-340, still CONFIRMED not fixed) and to other
  in-flight uncommitted manifest work in the same file (`needsFullManifestOnSave`,
  `seededRunConfig` — ISS-196/ISS-206/ISS-275), not this fix's 4-line diff.
- **Found at:** 2026-08-28T06:07:00Z
- **Found by:** bug-workflows-new-r2
- **Fingerprint:** `/workflows/new|save-workflow-button|click-save-with-empty-name-field|no-request-fired-no-feedback-shown`
- **Evidence:** `bug-hunter/evidence/workflows-new/BUG-20260828-060700-workflows-new-r2/`
- **Validated:** 3/3 on 2026-08-28, every cycle cold start (fresh nav to /dashboard then /workflows/new)
- **Root cause:** The Save-button guard at `ComposerPage.tsx:1108-1112` (current lines; ISS-315
  recorded it at :1075-1082 before other landed changes shifted the file) blocks on
  `!name.trim()` and returns via a bare `nameInputRef.current?.focus()` plus a hover-only
  `title="Name the workflow first"` — it never calls the `setSaveError` state that already
  renders a visible banner at `ComposerPage.tsx:1394-1398` and that `handleSave`'s own
  detached-step/not-authenticated branches already use (`:676-681`, `:685-686`). CONFIRMED by
  direct read.
- **Blast radius:** Single button, single `onClick`, single call site of `handleSave`
  (`ComposerPage.tsx:1114` — no `<form>`/`onKeyDown` bypass); but that one shared component
  renders on every composer route: `/workflows/new` (reported case, `initialName` absent → name
  starts empty), `/workflows/{id}/edit` (`DashboardLayout.tsx:2998` seeds
  `initialName={savedComposition?.name}`, non-empty but user-clearable), and the built-in
  "Save as copy" route (`builtinCanvasType` set, `ComposerPage.tsx:1020`'s
  `initialName || builtinCanvasType` fallback implies `initialName` may be unset there too). The
  identical no-visible-feedback guard shape also recurs on the "Run once" button in the same
  header block (`ComposerPage.tsx:1076-1097`, `briefText.trim().length < 3`).
- **Proposed fix:** Have the empty-name guard call `setSaveError("Name the workflow first.")` (or
  move the check inside `handleSave` itself) so it reuses the ALREADY-EXISTING `saveError` banner
  at `ComposerPage.tsx:1394-1398` — one change in the shared component fixes every route above.
  The Run once guard needs an analogous but separate visible-error path since no such banner
  exists near it today.
- **Issue cards:** [ISS-315](../.knowledge/cards/20260828-1750-ISS-315.md) (root),
  [ISS-431](../.knowledge/cards/20260829-0038-ISS-431.md) (sibling: Run once button, same
  silent-guard pattern, INFERRED),
  [ISS-432](../.knowledge/cards/20260829-0039-ISS-432.md) (sibling: same guard reached via the
  edit-existing-workflow and save-as-copy routes, INFERRED)
- **Fix card:** [FIX-375](../.knowledge/cards/20260829-0151-FIX-375.md) — the empty-name guard
  in `frontend/src/components/workflow/composer/ComposerPage.tsx:1108` now calls
  `setSaveError("Name the workflow first, then save.")`, so the component's existing
  `text-status-failed` banner (`:1400`) renders instead of a silent refocus — one edit at the
  single `handleSave` call site, so every composer route is covered. Test
  `suites/04_composer_canvas/test_iss315_save_empty_name_feedback.py` XPASS(strict); 14/14
  `ComposerPage.test.tsx` green. ISS-431 (Run once guard) is NOT fixed — different guard, no
  banner near it.

### Summary
On `/workflows/new`, with at least one agent added to the canvas but the "Workflow name" field
left empty (showing only the "Untitled workflow" placeholder), clicking "Save workflow" does
nothing observable: no `POST` request is issued at all, no toast or error banner appears, and
the name field gets no visual error state (no red border, no inline message) — the only
side-effect is the name input silently regaining DOM focus, which is indistinguishable from any
unrelated focus change. The exact same click, with a name typed into that field first, fires
`POST /api/user-workflows` immediately and returns `201 Created`. So the button is clearly
validating client-side before submitting, but communicates that validation failure to the user
in no way whatsoever — a user with an empty name has no way to know the click did anything
short of noticing nothing changed.

### Reproduction
1. Sign in as qa-admin, navigate to `/workflows/new` (empty composer, "Untitled workflow"
   placeholder, 0 agents).
2. Click "Add agent" → "+ Add" on any agent (e.g. Domain Discovery Agent) → Escape to close the
   modal. Canvas now shows 1 agent; the header confirms "1 agents". Name field remains empty.
3. Click "Save workflow". Observe: no new network request fires (confirmed via
   `browser_network_requests`, filtered to `workflow`), no toast/banner appears anywhere in the
   DOM, no red border or inline error on the name field — the page looks completely unchanged.
4. Type a name (e.g. `zz-hunt-savetest`) into the same "Workflow name" field, keep the same
   agent on the canvas, click "Save workflow" again: `POST /api/user-workflows` fires
   immediately and returns `201 Created` — proving the click handler and the agent state were
   both fine; only the empty-name case was gated with no feedback.
5. Clear the name field back to empty, click "Save workflow" a third time (repro #2): again, no
   new request fires, no feedback of any kind.

### Expected
Attempting to save a workflow with an empty/missing name should give the user a clear,
observable signal — an inline validation message near the field, a red border, a toast, or at
minimum a disabled "Save workflow" button when the name is empty — so the user understands why
nothing was saved.

### Actual
The save action is silently blocked client-side with absolutely no user-visible indication:
button stays enabled and clickable, no request is sent, no error text or styling appears
anywhere in the DOM, and the only trace is the name input regaining focus (which looks
identical to a stray click).

### Evidence
- Before (1 agent added, name field empty, about to click Save): `bug-hunter/evidence/workflows-new/BUG-20260828-060700-workflows-new-r2/01-before-1agent-noname.png`
- After clicking Save workflow — page unchanged, no toast/error, no request fired: `bug-hunter/evidence/workflows-new/BUG-20260828-060700-workflows-new-r2/02-after-click-save-nothing-happens.png`
- Network log contrasting the empty-name no-op against the named-save 201: `bug-hunter/evidence/workflows-new/BUG-20260828-060700-workflows-new-r2/network.log`

### Browser Signals
- Console: no errors or warnings logged on either the no-op click or the successful save.
- Network: empty-name click → no new request; named click (same session, same agent) →
  `POST http://localhost:8000/api/user-workflows` → `201 Created`.
- State/URL: stays on `/workflows/new` throughout; only DOM change on the no-op click is the
  name `<input>` regaining `[active]`/focus state, with no error text anywhere in
  `document.body.innerText`.

## BUG-20260828-073350-workflows-ppt-canvas — Simple and Canvas views disagree on the PPT built-in's deliverable type ("Custom" vs "Streamed text")

- **Page:** Built-in workflow on the canvas
- **Route:** /workflows/ppt/canvas
- **Severity:** Low
- **Status:** CLOSED
- **Verified:** 2026-08-29, 6-verifier. `tests/integration/e2e/suites/04_composer_canvas/test_iss340_simple_canvas_deliverable_agree.py`
  run one file at a time via `.venv/bin/python3 -m pytest`. Confirmed XPASS(strict) for
  `test_simple_and_canvas_agree_on_ppt_deliverable_type` (ISS-340) and
  `test_simple_and_canvas_agree_on_saved_custom_workflow_deliverable_type` (ISS-580), then
  removed both `@pytest.mark.xfail` markers (kept `@pytest.mark.issue`); a subsequent run of
  the whole file went plain green. Manually re-ran the ORIGINAL reproduction by hand in
  Chrome (lane6, qa-admin, light theme, default viewport), twice, on a cold load of
  `/workflows/ppt/canvas`: both times Canvas's "Deliverable strategy" combobox and Simple's
  read-only "Deliverable type" field agreed — "ppt — declared by this workflow" on both tabs
  — no console errors. Frontend regression suites green:
  `ComposerPage.test.tsx` 14/14, `CanvasView.test.tsx` 24/24. `tsc --noEmit`: 9 pre-existing
  errors, none in the three touched files. `backend/lint-imports` (run from `backend/`): 1
  pre-existing broken contract (`kernel imports only capability ports`), unrelated to this
  frontend-only fix — not introduced by it. Backend `:8000/docs` → 200 throughout; no backend
  file changed, no restart needed. NOTE: under the current heavy concurrent bug-hunter load
  (`uptime` load average 23-40 during this pass), the `ppt` scenario's already-documented
  cold-load `runConfig`-seeding race ([ISS-604](../.knowledge/cards/20260829-0207-ISS-604.md),
  filed separately, deferred, NOT part of this bug or FIX-401's mechanism) triggered far more
  often than its baseline ~1-in-5 — roughly 7 of 10 automated runs in this pass hit it. Every
  single one of those failures showed the SAME direction: Simple correct
  ("ppt — declared by this workflow"), Canvas stale ("Streamed text…") — never once did Simple
  regress to the original "Custom" bug. That asymmetry, plus the clean manual repro and green
  unit suites, is why this is closed rather than reopened: the reported defect (Simple
  hardcoded to "Custom", disagreeing with Canvas) is fixed; the residual flake is
  ISS-604's, already tracked, and load-amplified here, not new.
- **Tested:** `tests/integration/e2e/suites/04_composer_canvas/test_iss340_simple_canvas_deliverable_agree.py`
  — `test_simple_and_canvas_agree_on_ppt_deliverable_type` (ISS-340) and
  `test_simple_and_canvas_agree_on_saved_custom_workflow_deliverable_type` (ISS-580), both
  `@pytest.mark.xfail(strict=True)`, both observed red 2026-08-29: Simple shows `'Custom'`,
  Canvas shows the real derived strategy — never equal.
- **Validated:** 3/3 on 2026-08-28, cold start each cycle — Simple always shows "Custom", Canvas
  shows either "Streamed text" (cycle 1) or the correct dynamic "ppt — declared by this workflow"
  option (cycles 2-3); the two never agree regardless of which value Canvas lands on.
- **Root cause:** `ComposerPage.tsx:478` (line drifted from the validator's `:448` since that
  pass) hardcodes `const deliverableLabel = PIPELINE_LABEL.custom;` for the Simple tab's
  `IdentityCard` (its sole call site), never derived from `runConfig`. `CanvasView.tsx:1574`, the
  sibling tab on the same in-memory workflow, already derives its combobox from the real
  `runConfig?.deliverable?.strategy` — the two views share no derivation, so they can only agree
  by accident.
- **Blast radius:** `deliverableLabel`/`<IdentityCard>` have exactly one call site each
  (`ComposerPage.tsx`), but that component is generic over EVERY built-in opened at
  `/workflows/<type>/canvas` (`builtinCanvasTypeFor()`, `page.tsx:367`, "no hardcoded workflow
  list"). Confirmed via each built-in's own `workflow.yaml` `deliverable:` block: `ppt_v2`,
  `prototype` (`single_file`), `app_builder`, `mulesoft_to_springboot`, `dotnet_to_azure`
  (`serialized_sandbox`), and `user_stories` (`streamed_text`) all show the identical
  Simple-says-"Custom"-Canvas-says-the-truth disagreement — `ppt` is simply the one that was
  hunted first. A saved (non-built-in) custom workflow with a non-generic declared strategy is a
  further, distinct entry path implied by the same unconditional line — filed as ISS-580
  (INFERRED, not yet reproduced).
- **Proposed fix location:** `ComposerPage.tsx:478` already has `runConfig` in scope (`:410`) —
  derive `deliverableLabel` from `runConfig?.deliverable?.strategy` through ONE shared label
  lookup both `ComposerPage` (feeds `IdentityCard` + the `:1020` header title) and
  `CanvasView.tsx` (`:1574`'s combobox) import, rather than teaching `IdentityCard` a second copy
  of the mapping.
- **Issue cards:** [ISS-340](../.knowledge/cards/20260828-1856-ISS-340.md) (root — analyzer
  sections appended: Root cause/Blast radius/Proposed fix), [ISS-580](../.knowledge/cards/20260829-0236-ISS-580.md)
  (sibling: saved custom workflow, INFERRED)
- **Fix card:** [FIX-401](../.knowledge/cards/20260829-0206-FIX-401.md) — one exported
  `DELIVERABLE_STRATEGY_LABEL` + `deliverableStrategyLabel()` in
  `frontend/src/components/workflow/composer/CanvasView.tsx` now feeds BOTH the Canvas
  combobox's `<option>` texts and `ComposerPage.tsx:485`'s identity-card label, which is
  derived from `runConfig?.deliverable?.strategy` instead of the old unconditional
  `PIPELINE_LABEL.custom`. The header eyebrow keeps the pipeline-type label as
  `pipelineLabel` (`:479`, `:1027`) — the two vocabularies were conflated in one variable and
  are now separate. Both e2e tests XPASS(strict) 2026-08-29; 14/14 `ComposerPage.test.tsx` and
  24/24 `CanvasView.test.tsx` green. Deferred: the cold-load `runConfig` seeding race that
  makes the ppt test flake ~1 run in 5 —
  [ISS-604](../.knowledge/cards/20260829-0207-ISS-604.md).
- **Found at:** 2026-08-28 07:33 UTC
- **Found by:** bug-workflows-ppt-canvas-r2
- **Fingerprint:** `/workflows/ppt/canvas|simple-vs-canvas-deliverable-display|switch-between-simple-and-canvas-tabs|deliverable-type-label-disagrees-custom-vs-streamed-text`
- **Evidence:** `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-073350-workflows-ppt-canvas/`

### Summary
The PPT built-in's real deliverable (`GET /api/workflows/ppt` → `deliverable: {"strategy": "ppt",
"name": "presentation.pptx"}`) is neither of the app's three generic deliverable strategies. The
Canvas view's "Workflow" tab renders this by silently defaulting its combobox to "Streamed text —
agent's raw output" (already documented as part of the manifest-loss bug
`BUG-20260828-005700-workflows-ppt-canvas`, filed there in the context of "Save as copy"). The
Simple view, looking at the exact same unsaved built-in state, does not use that combobox at all —
it renders a read-only "Deliverable type: Custom" label instead. So switching between the two
tabs on the identical, unmodified workflow shows the user two different, mutually contradictory
answers to "what does this workflow deliver" — "Streamed text" on one tab, "Custom" on the other —
and neither matches the true `ppt`/`presentation.pptx` strategy. This is a distinct defect from
the filed one: it is a display inconsistency between the Simple and Canvas components themselves,
independent of any save action, and was never previously investigated (round 1 only looked at the
Canvas tab and the save-as-copy POST body).

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/workflows/ppt/canvas` (fresh load,
   lands on Canvas tab by default).
2. On the Canvas tab, open the right-rail "Workflow" sub-tab (default) and note the "Deliverable
   strategy" combobox: selected option is "Streamed text — agent's raw output".
3. Click the "Simple" tab (top toolbar) — no save action, same in-memory workflow. Note the
   "Deliverable type" field under the "Workflow" card: reads "Custom" (not "Streamed text").
4. Click back to "Canvas" — combobox reverts to showing "Streamed text — agent's raw output"
   selected.
5. Reload the page cold (`http://localhost:3000/workflows/ppt/canvas`) and click "Simple"
   directly without visiting Canvas first: still reads "Custom" — reproduced from a clean load,
   not just after tab-hopping.
6. Cross-check ground truth via `GET /api/workflows/ppt`: `deliverable.strategy` is `"ppt"`,
   `deliverable.name` is `"presentation.pptx"` — neither UI label ("Streamed text" nor "Custom")
   matches it.

### Expected
The two views of the same workflow's configuration should agree with each other (and ideally
reflect the real `ppt` strategy, or at minimum both fall back to the same honest label, e.g. both
say "Custom" or both are disabled/blank) when a strategy value doesn't match any of the generic
options the UI understands.

### Actual
Canvas shows a specific, wrong, selectable option ("Streamed text — agent's raw output") while
Simple shows a different, generic label ("Custom") for the exact same unsaved, unmodified
built-in workflow state — the two tabs contradict each other with no save/reload between them.

### Evidence
- Canvas tab, Workflow sub-tab, Deliverable strategy combobox showing "Streamed text — agent's raw output" selected: `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-073350-workflows-ppt-canvas/01-canvas-shows-streamed-text.png`
- Simple tab, same unsaved workflow, Deliverable type showing "Custom": `bug-hunter/evidence/workflows-ppt-canvas/BUG-20260828-073350-workflows-ppt-canvas/02-simple-shows-custom.png`

### Browser Signals
- Console: no relevant error observed.
- Network: no requests fired by switching tabs (`GET /api/workflows/ppt` only on initial page
  load); `deliverable.strategy` confirmed `"ppt"` via direct API call, matching neither UI label.
- State/URL: URL stays `/workflows/ppt/canvas` throughout; purely a client-side rendering
  disagreement between the Simple and Canvas components reading the same in-memory workflow state.

## BUG-20260828-073900-workflows-id-run-r2 — A saved workflow's launch panel loses its override entirely and renders the generic base-type wizard, even though the override fetch succeeds

- **Page:** A saved workflow's launch panel
- **Route:** /workflows/{id}/run
- **Severity:** High
- **Status:** ESCALATED
- **Fixed:** the ISS-228 effect race — `LaunchWizard.tsx:343-348`'s "re-derive default agents" effect now tests emptiness inside `setPipelineAgents((prev) => ...)`, so it sees the draft-restore effect's queued update instead of the stale render closure and stops overwriting the saved roster. One shared component, so ISS-283's click-through Run is covered by the same edit. Card: FIX-338.
- **Escalated:** both shipped scenarios in `tests/integration/e2e/suites/05_saved_workflows/test_iss228_launch_panel_override_binding.py` still xfail (NOT xpass) after the fix, failing only on `assert 'My prototype' in body`. That assertion is a separate presentation gap — `savedName` is restored at `LaunchWizard.tsx:311-313` but only reaches the closed AgentsPopup modal (`:1168-1169`), while the header renders `cfg.eyebrow`/`cfg.title` unconditionally (`:826-833`) — so it reproduces with or without the race and no card asks for a name display. Filed as ISS-384; needs a UI decision (add the name alongside the existing title, which the test also requires stays visible) or a retargeted assertion.
- **Root cause:** NOT a network fetch race (the two GETs' arrival order does not decide the
  outcome) — a synchronous same-commit React effect-ordering bug entirely inside
  `frontend/src/components/workflow/LaunchWizard.tsx`. `:278-324` ("restore session draft") reads
  the `{mode}.draft` sessionStorage payload the caller wrote (from `GET /api/user-workflows/{id}`)
  and, once `libraryAgents.length > 0`, calls `setPipelineAgents(restored)` (`:303-307`) with the
  override's real roster. `:335-338` ("re-derive once real agents arrive") fires on the SAME
  `libraryAgents` transition and reads `pipelineAgents.length` from the SAME render's closure —
  i.e. before the sibling effect's update is visible, since React does not let one effect observe
  another's `setState` call within the same commit — so it always sees `0` and unconditionally
  calls `setPipelineAgents(defaultAgentsFor(libraryAgents, mode))` (`:337`), the generic
  per-pipeline roster. Both effects issue a plain-value `setState`; the second is declared (hence
  runs) after the first, so it is enqueued last and wins, every time `libraryAgents` (Redux state
  from `GET /api/agents/library` on sign-in, `useAgentLibrary.ts:16-20`, starting empty) is still
  empty at `LaunchWizard`'s first render — which a cold direct navigation to `/workflows/{id}/run`
  guarantees, explaining the deterministic, no-delay-needed reproduction. Precedent:
  `ComposerPage.tsx:295-298` solves the identical "library loads after mount" problem with a
  one-shot `useRef` guard (`resyncedAgentsFromLibrary`) instead of a `.length` read and does NOT
  have this race — its own card (FIX-271) documents it as "the same class of bug as an
  earlier-fixed LaunchWizard issue," i.e. `LaunchWizard.tsx:335-338` IS that earlier, weaker fix.
- **Blast radius:** confirmed by grep — `LaunchWizard` mounts from exactly two live call sites:
  `frontend/src/app/[...view]/page.tsx:3760` (this bug's `/workflows/{id}/run` cold mount) and
  `frontend/src/app/workflow/create/page.tsx:24` (`/workflow/create?mode=...`), the latter reached
  with an identical `{mode}.draft`+`agentIds` via `DashboardLayout.tsx`'s `handleLaunchSaved`
  (`:1475-1558`, click "Run" on a saved workflow) — same race, narrower timing window. Separately,
  `pipelineAgents` (the value the race clobbers) is not read-only: `handleSave`
  (`LaunchWizard.tsx:699-705`, `agent_ids: pipelineAgents.map(...)` at `:703`) and
  `handleSaveAsOverride` (`:727-754`, same at `:737`, plus the persisted `manifest` built from
  `pipelineAgents` at `:738-742`, UPSERTING the same override row) both trust it with no re-fetch —
  a save made while the race is live overwrites the real saved override with the generic default
  roster server-side, turning a render bug into data loss.
- **Fix belongs in:** `LaunchWizard.tsx`, not either caller (both already write a correct draft).
  Fold `:335-338`'s recovery logic into the same effect as `:278-324` (one effect, one source of
  truth for "was the roster actually restored"), or replace the `pipelineAgents.length` read with
  a one-shot `useRef` guard matching the working precedent at `ComposerPage.tsx:295-298`. A guard
  in this one shared component covers both call sites; a per-caller patch would not.
- **Validated:** 3/3 on 2026-08-28, every cycle from a cold start (fresh navigation, cycle 3 with
  localStorage/sessionStorage fully cleared) — no artificial delay needed, deterministic on a
  plain load/reload
- **Issue card:** [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md)
- **Issue cards:** [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md) (root, now carries the
  confirmed mechanism), [ISS-283](../.knowledge/cards/20260828-1905-ISS-283.md) (sibling: same race
  via click-through Run / `DashboardLayout.handleLaunchSaved`),
  [ISS-284](../.knowledge/cards/20260828-1906-ISS-284.md) (sibling: Save / Save-as-override persist
  the clobbered roster — data loss)
- **Found at:** 2026-08-28 07:39 UTC
- **Found by:** bug-workflows-id-run-r2
- **Fingerprint:** `/workflows/{id}/run|workflow-run-panel-override-binding|cold-mount-with-two-parallel-fetches|base-type-wins-override-fetch-discarded-generic-wizard-renders`
- **Evidence:** `bug-hunter/evidence/workflows-id-run/BUG-20260828-073900-workflows-id-run-r2/`

### Summary
On mount, the launch panel for a saved workflow fires two parallel requests: `GET
/api/user-workflows/{id}` (the saved override — name, description, agents, template selection)
and `GET /api/workflows/{base_pipeline_type}` (the generic base type, e.g. `prototype`). When the
override request is not the first of the two to settle in the client, the panel renders the
fully generic "NEW PROTOTYPE / Configure your prototype" wizard — no reference anywhere to the
saved workflow's name ("My prototype"), its description, or its saved template selection ("No
template" / Blank Canvas is selected instead) — and it never re-binds even after the override
response arrives and is confirmed successful. This reproduces both by deliberately delaying the
override request via `page.route` (making the causal mechanism explicit) and, once triggered, on
every subsequent plain reload/re-navigation to the same URL in the same session, with no
artificial delay at all — network tooling confirms `GET
/api/user-workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` returns `200 OK` with the correct
`name: "My prototype"`, `agent_ids: ["documentation-agent","prototype-specify"]` payload on every
one of these loads, so the override data is available to the client and is simply not applied to
the render. This is a materially worse failure mode than the already-filed
`BUG-20260828-010600-workflows-id-run` (a nonexistent id falling back to the Dashboard): here the
workflow id is completely valid and its data loads successfully, yet a user opening their own
saved workflow's dedicated launch link can silently land on the wrong (generic/default)
configuration with no error, no loading-stuck state, and no visual indication anything is wrong.

### Reproduction
1. Sign in as qa-admin. As a control, confirm `GET
   http://localhost:8000/api/user-workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` returns `200`
   with `name: "My prototype"`, `agent_ids: ["documentation-agent","prototype-specify"]`.
2. Via `browser_run_code_unsafe`, register `page.route('**/api/user-workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0', ...)`
   that awaits `page.waitForTimeout(3000)` before `route.continue()`.
3. Navigate to `http://localhost:3000/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/run`.
4. Observe: the panel renders the h1 "NEW PROTOTYPE / Configure your prototype", "Advanced 2
   agents" (coincidentally matching the override's agent count but not its identity), and the
   Template tab pre-selects "No template" / Blank Canvas — none of "My prototype", its
   description, or a bound template appear anywhere in `document.body.innerText`.
5. Confirm via `browser_network_requests` that `GET /api/user-workflows/{id}` completed with
   `200 OK` well before the 4s observation window closed, and the correct payload was returned —
   the override loaded successfully but was never applied.
6. Remove the route delay (`page.unrouteAll`), fully clear `localStorage`/`sessionStorage`
   (re-seeding only `auth_token`), and reload `http://localhost:3000/workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0/run`
   directly with no interception at all: the same generic wizard renders again, confirming the
   defect is not dependent on the artificial delay once triggered in-session.
7. Repeated step 3-5 a second time (fresh `page.goto`, same delay) — identical generic-wizard
   result, confirming determinism.

### Expected
The launch panel should wait for (or otherwise correctly apply) the override response before
rendering, or apply it whenever it lands, regardless of which of the two parallel requests
resolves first — showing "My prototype" 's name/description and its saved template/agent
configuration.

### Actual
Whichever of the two parallel fetches is *not* first to resolve is discarded; when
`/api/workflows/{base_pipeline_type}` effectively wins, the panel renders the fully generic
base-type wizard with zero trace of the saved workflow, and this state does not self-correct even
after the override response is confirmed to have arrived successfully.

### Evidence
- Delayed override fetch, generic wizard renders (repro 1): `bug-hunter/evidence/workflows-id-run/BUG-20260828-073900-workflows-id-run-r2/01-delayed-fetch-generic-wizard.png`
- Delayed override fetch, generic wizard renders (repro 2): `bug-hunter/evidence/workflows-id-run/BUG-20260828-073900-workflows-id-run-r2/02-repro2-delayed-fetch-generic-wizard.png`
- Plain reload with no interception, storage cleared, still generic wizard: `bug-hunter/evidence/workflows-id-run/BUG-20260828-073900-workflows-id-run-r2/03-warm-session-no-delay-still-generic-wizard.png`

### Browser Signals
- Console: no relevant error observed; both requests complete without throwing.
- Network: `GET http://localhost:8000/api/user-workflows/656ca387-e69c-474d-b7ff-5fd9eb017cc0` →
  `200 OK` with correct override payload (`name: "My prototype"`, two named `agent_ids`) on every
  reproduction, including the un-delayed ones. `GET http://localhost:8000/api/workflows/prototype`
  fires alongside it (base type).
- State/URL: `location.href` stays the correct `/workflows/{id}/run` path throughout — this is
  purely a render-binding defect, not a routing/URL defect.

## BUG-20260828-074900-workflow-r2 — Removing a file attachment leaves a stale "[Attached: ...]" marker in the brief textarea, keeping Run Workflow enabled for a phantom attachment

- **Page:** Legacy workflow builder (unlinked, second/older builder)
- **Route:** /workflow
- **Severity:** Low
- **Status:** CLOSED
- **Fixed:** 2026-08-29 — `frontend/src/components/workflow/WorkflowView.tsx`, two hunks: a new module-level `stripAttachmentMarker(text, filename)` helper above `WorkflowView` (removes the first block-entry equal to `filename` from a `[Attached: a, b]` block, keeps every other name, drops the whole block plus its leading `\n\n` when nothing is left), and the chip's remove `onClick` (was `:388`, now `:403-409`) which now calls `setIdeaInput((prev) => stripAttachmentMarker(prev, file.name))` next to the existing `attachedFiles` filter. Fixed at the WRITE site, not at either reader, so the `disabled` gate and `handleRun`'s payload both inherit it (ISS-579's own argument); not a blanket `/\[Attached:.*\]/` clear, which ISS-583 shows would erase the marker of a file that is still attached. Tests, `npx vitest --run --no-coverage` from `frontend/`, one file at a time: `WorkflowView.attachmentRemove.test.tsx` went from `Tests 3 expected fail (3)` before to `Tests 2 failed | 1 expected fail (3)` after — the ISS-345 and ISS-583 cases XPASS (`Error: Expect test to fail`), markers left in place for the verifier. The third case (ISS-579) is still red because its fixture is unsatisfiable, not because of the code — it removes the ONLY attachment (brief becomes empty) and mounts with an empty agent library, so both of `handleRun`'s guards short-circuit and `onStartPipeline` is never called; measured directly: `textarea.value === ""`, `runButton.disabled === true`, 0 calls. Filed as ISS-603, test NOT edited. Neighbours re-run unchanged: `WorkflowView.zeroAgents.test.tsx` 1 XPASS (ISS-328's own fix, already in the tree), `src/app/workflow/page.test.tsx` 1 expected fail. `npx tsc --noEmit` no WorkflowView errors; eslint on the file 0 errors, 7 pre-existing warnings. Frontend-only — no backend restart needed. Card: FIX-400; ISS-345 and ISS-583 resolved, ISS-579 left open pending a runnable fixture (ISS-603).
- **Verified:** 2026-08-29 — `WorkflowView.attachmentRemove.test.tsx` re-run from `frontend/`:
  before removing `it.fails`, `Tests 2 failed | 1 expected fail (3)` (the ISS-345 and ISS-583
  cases XPASS with "Error: Expect test to fail", confirming the fixer's claim); removed
  `it.fails` -> `it` on the ISS-345 and ISS-583 cases only (ISS-579's case kept `it.fails` — it
  is a genuinely unresolved sibling, filed as ISS-603, not part of this fix), re-ran: `Tests 2
  passed | 1 expected fail (3)`, plain green on the two resolved cases. Regression: sibling
  files unchanged from the fixer's own figures — `WorkflowView.zeroAgents.test.tsx` still 1
  XPASS (ISS-328's pre-existing guard), `src/app/workflow/page.test.tsx` still 1 expected fail.
  `npx tsc --noEmit`: no `WorkflowView.tsx` errors (other pre-existing unrelated test-file errors
  present, untouched). `npx eslint src/components/workflow/WorkflowView.tsx`: 0 errors, 7
  pre-existing warnings, unchanged. Backend `:8000/docs` -> 200 (frontend-only fix, no restart
  needed). `lint-imports` from `backend/`: 1 pre-existing broken contract
  (`agents.execution_engine.engine` -> `app.api` via `kernel_services`/`revision_analyzer`) —
  confirmed pre-existing, unrelated to this frontend-only change, not touched. Manual repro in
  Chrome (lane5, qa-admin, cold `/dashboard` -> `/workflow`): attached `zz-hunt-test.txt`,
  `textarea.value` showed `[Attached: zz-hunt-test.txt]`; clicked the chip's remove "x" ->
  `textarea.value === ""`, chip gone from `document.body.innerText`, 0 console errors. Re-ran the
  two-file ISS-583 case by hand: attached `zz-hunt-a.txt` + `zz-hunt-b.txt` ->
  `[Attached: zz-hunt-a.txt, zz-hunt-b.txt]`; removed `zz-hunt-a.txt`'s chip ->
  `textarea.value === "[Attached: zz-hunt-b.txt]"`, the still-attached file's marker survives
  intact. Both match the register's original repro and the test assertions. Screenshot:
  `bug-hunter/evidence/workflow/BUG-20260828-074900-workflow-r2/04-after-fix-marker-cleared.png`.
  ISS-579 remains open (unresolved by this fix, tracked separately as ISS-603) — not part of
  this bug's closure scope per the fix card's own stated boundary.
- **Validated:** 3/3 on 2026-08-28, every cycle — cold `/dashboard` -> `/workflow`, attach a
  `.txt` file, click chip's remove "x"; no axis variation needed, reproduces unconditionally
- **Root cause:** CONFIRMED — `WorkflowView.tsx`'s attach handler (line 337-340) writes a
  `[Attached: <filename>]` marker into `ideaInput` alongside pushing into `attachedFiles`, but
  the chip's remove `onClick` (line 388) does `setAttachedFiles((prev) => prev.filter((_, i) =>
  i !== idx))` only — it never calls `setIdeaInput` to strip the marker, so the two states that
  were written together on attach are never reconciled on remove.
- **Blast radius:** grepped every `attachedFiles`/`[Attached:` usage in `frontend/src/`
  (`IdeaInputPage.tsx`'s `useBriefAttachments`, reused by `ComposerPage.tsx`, and
  `LaunchWizard.tsx`) — both keep file content in a separate `attachedFileContents` state
  composed into the payload only at send time, so the textarea itself never carries an
  `[Attached: ...]` marker and `removeFile` there correctly clears both. `WorkflowView.tsx` is
  the only component with the flawed direct-injection pattern, and `app/workflow/page.tsx:58-62`
  is its only production mount. Within `WorkflowView.tsx`, the same stale `ideaInput` also feeds
  `handleRun` (line 165) verbatim as the run brief once `onStartPipeline` is wired (see
  ISS-579/ISS-492) — a second reader of the same corrupted state, currently unreachable because
  ISS-492 shows nothing wires that prop today.
- **Fix location:** the remove handler at `WorkflowView.tsx:388` — it must strip the specific
  filename's token from whichever marker block(s) `ideaInput` holds (not blanket-clear, since a
  joined/multi-block marker can still legitimately reference a file that was NOT removed; see
  ISS-583). Patching the write site (remove handler) fixes every reader of `ideaInput` — the
  button's `disabled` gate and `handleRun`'s payload — at once, rather than patching each reader.
- **Issue cards:** [ISS-345](../.knowledge/cards/20260828-1900-ISS-345.md) (root — validator-filed,
  confirmed by re-reading `WorkflowView.tsx:330-343,388` directly),
  [ISS-583](../.knowledge/cards/20260829-0234-ISS-583.md) (sibling, INFERRED: 2+ files produce
  joined/multiple marker blocks that a blanket-clear fix would also corrupt),
  [ISS-579](../.knowledge/cards/20260829-0234-ISS-579.md) (sibling, INFERRED: the same stale
  marker forwards into the run payload via `handleRun` once ISS-492's wiring gap closes)
- **Found at:** 2026-08-28 07:49 UTC
- **Found by:** bug-workflow-r2
- **Fingerprint:** `/workflow|attach-file-remove-attachment|click-remove-x-on-attachment-chip|stale-attached-marker-text-remains-in-textarea-run-button-stays-enabled`
- **Evidence:** `bug-hunter/evidence/workflow/BUG-20260828-074900-workflow-r2/`

### Summary
On `/workflow`, clicking "Attach file" and selecting a file injects a literal
`[Attached: <filename>]` marker string directly into the "Describe your idea" textarea's value
(not just a visual chip) and shows a removable attachment chip below the field. Clicking the
chip's own "×" remove button correctly removes the visual chip from the DOM, but does **not**
clear the `[Attached: ...]` marker text it had injected into the textarea — `textarea.value`
(confirmed via direct DOM read, not just a visual screenshot) still literally reads
`[Attached: zz-hunt-test.txt]` after the file is "removed", with no attachment chip anywhere in
the page and no way to see this stale content since the textarea's placeholder styling makes the
leftover marker easy to miss. Because "Run Workflow"'s only gate is non-empty brief text (already
established as the root cause of the separately-filed zero-agent no-op bug), the button stays
enabled based on this now-orphaned marker even though the user explicitly removed the attachment
and the workflow still has 0 agents. This is a distinct defect from the already-filed
`BUG-20260828-011000-workflow`: that bug is about the enable-gate ignoring agent count on
legitimately-entered text; this one is about the remove-attachment action failing to fully
reverse the state it created, leaving stale/misleading content behind after an explicit user
undo action.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/workflow` (fresh load). Confirm the
   textarea is empty and "Run Workflow" is `disabled`.
2. Click "Attach file (PDF, DOCX, PPTX, TXT)" and select a small `.txt` file (e.g.
   `zz-hunt-test.txt`). Observe: the textarea now contains `[Attached: zz-hunt-test.txt]`
   (confirmed via `textarea.value`), an attachment chip `zz-hunt-test.txt (32B)` appears below the
   field, and "Run Workflow" becomes enabled.
3. Click the "×" button on the attachment chip to remove it. Observe: the chip disappears from
   the page — `document.body.innerText` no longer shows the filename outside the marker text.
4. Read `textarea.value` directly via DOM: it still equals `[Attached: zz-hunt-test.txt]`, and
   `runButton.disabled` is still `false` — the button remains enabled for a workflow with 0
   agents and no attachment, based purely on the orphaned marker text the remove action failed to
   clear.
5. Reloaded to a fresh `/workflow` and repeated steps 2-4 — identical result: stale
   `[Attached: zz-hunt-test.txt]` marker persists in the textarea and "Run Workflow" stays enabled
   after the chip is removed.

### Expected
Removing an attachment via its chip's "×" button should fully reverse the attach action: the
`[Attached: ...]` marker text it injected into the textarea should also be cleared (or, if the
textarea legitimately had other user-typed content, only the marker segment should be stripped),
and "Run Workflow" should return to reflecting the workflow's real state (0 agents, no
attachment, effectively empty brief).

### Actual
The chip's remove control only deletes the chip element from the DOM/attachment list; the
`[Attached: <filename>]` string it wrote into the textarea's actual value is left behind
untouched, so the brief field is left in a misleading state (claims an attachment that no longer
exists) and "Run Workflow" stays enabled off that stale text.

### Evidence
- Before (fresh load, empty textarea, Run Workflow disabled): `bug-hunter/evidence/workflow/BUG-20260828-074900-workflow-r2/01-before-fresh-load.png`
- Repro 1 (attachment removed, chip gone, stale marker still in textarea, Run Workflow enabled): `bug-hunter/evidence/workflow/BUG-20260828-074900-workflow-r2/02-repro1-stale-marker-after-remove.png`
- Repro 2 (fresh reload, identical result): `bug-hunter/evidence/workflow/BUG-20260828-074900-workflow-r2/03-repro2-stale-marker-after-remove.png`

### Browser Signals
- Console: no error or warning logged on attach, remove, or the resulting stale state.
- Network: no request fired by the attach or remove actions (purely client-side textarea/state
  manipulation); confirmed via `browser_network_requests` diffing before/after both actions.
- State/URL: `location.href` stays `/workflow` throughout; direct DOM reads of `textarea.value`
  and `runButton.disabled` (not just visual/screenshot inspection) confirm the stale marker text
  and enabled state, reproduced twice from independent fresh page loads.

## BUG-20260828-095700-runs-id-chat-timestamp — Chat message timestamps in the Preview transcript silently reset to the current time on every page reload, never reflecting when the message was actually sent

- **Page:** Completed run — Preview tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e
- **Severity:** Low
- **Status:** CLOSED
- **Verified:** 2026-08-29 (lane6) — `frontend/src/hooks/useRunChat.chatTimestamp.test.ts` run via
  `npx vitest run` from `frontend/`: 3/3 passed, plain `it(...)` with no xfail/`it.fails` marker
  to remove (matches the fixer's note). Backend `python -m pytest` (venv) `tests/unit/test_runs_api_events.py`
  7/7 passed, `tests/unit/test_sse_stream.py` 53/53 passed. Regression: `useRunChat.test.ts` +
  `lib/api.test.ts` 22/22 passed together. `npx tsc --noEmit`: 0 errors in the changed files.
  `lint-imports` (from `backend/`): 3 kept / 1 broken, same pre-existing `agents.execution_engine.engine
  -> app.api` contract untouched by this diff. `curl :8000/docs` → 200 (no restart needed, confirmed
  before trusting any result). Manual re-run of the ORIGINAL repro in the browser (lane6, qa-admin,
  same route `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e`): sent a new chat message at 04:46 AM local,
  cold-navigated away to /dashboard and back after ~90s (current time 04:47 AM) — message still read
  04:46 AM, not the reload time. Repeated a second cold-reload cycle after another ~80s (current time
  04:48 AM) — message still read 04:46 AM. Confirmed at the network layer too:
  `GET /api/runs/{id}/events?after=0` now carries `"created_at":"2026-08-29T02:46:39.907480+00:00"` on
  the `chat_message` event, which the UI correctly renders as local 04:46 AM — the field the original
  repro found completely absent. Console: 0 errors, 1 pre-existing unrelated iframe-sandbox warning
  (matches FIX-399's noted baseline). After-screenshot:
  `bug-hunter/evidence/runs-id/BUG-20260828-095700-runs-id-chat-timestamp/03-after-fixed-0446-stays-fixed-at-0448-reload.png`.
  Bug is fixed; test green AND manual repro fixed.
- **Fixed:** 2026-08-29 — root cause was a field that existed on the row and was projected by
  NEITHER durable reader. `backend/app/api/runs.py` `get_run_events` now projects
  `created_at` (new module-level `_iso_utc`, the free-function twin of the response models'
  `_serialize_dt`; KAN-113 UTC promotion so the browser does not `Date.parse` it as LOCAL),
  and `backend/app/api/run_stream.py`'s SSE attach replay merges the same value — both
  readers, because that file's own comment requires it to mirror the REST twin and a
  one-transport fix would make a replayed frame's shape depend on which transport delivered
  it. Merged FIRST in both, so a payload-embedded timestamp still wins (FIX-354 stamps the
  RUN's `created_at` on `pipeline_start`; a resumed run's row write time must not clobber it).
  `frontend/src/lib/api.ts` merges the column into `DurableFrame.data` with the same
  ordering; `frontend/src/hooks/useRunChat.ts` gains one `foldedCreatedAt(data, existing?)`
  helper both upserts call — prefer `data.created_at`, then an existing bubble's settled
  value, clock only for a live frame carrying neither. `upsertNarratorMessage`'s `findIndex`
  hoisted three lines so its merge branch stops clobbering a settled value.
  `MessageBubble.tsx:189` untouched — it renders a real ISO string correctly as-is.
  Card: FIX-406; ISS-358 and ISS-595 both resolved.
- **Tests:** `frontend/src/hooks/useRunChat.chatTimestamp.test.ts` 3/3 passed (plain `it(...)`,
  no xfail/`it.fails` marker in the file — green IS the pass signal here, not XPASS; nothing
  for 6-verifier to remove). Regression: `useRunChat.test.ts` 20/20, `lib/api.test.ts` 2/2,
  `liveRunSwitch.fix201.test.ts` 26/26, `useWorkflow.accumulators.test.ts` +
  `terminalReopenReconcile.source.test.ts` 39/39. Backend `tests/unit/test_runs_api_events.py`
  7/7, `tests/unit/test_sse_stream.py` 53/53 — that file's `TestReplay` exact-dict assertion
  was WIDENED to include the new key (it stays a strict compare; the expected value is read
  off the row and UTC-promoted explicitly, not via the endpoint's own helper). No application
  behaviour was changed to satisfy a test. Wire-parity guard passed untouched.
- **Invariants:** SC-001/INV-1 N/A — no file under `backend/agents/execution_engine/` touched.
  Migrations: none, `run_events.created_at` already exists NOT NULL
  (`backend/app/models/run_event.py:72`). `lint-imports` 3 kept / 1 broken; the broken
  contract is `agents.execution_engine.engine -> app.api` via kernel_services /
  revision_analyzer — no file in that chain is in this diff, and `engine.py` carries other
  in-flight uncommitted changes in this shared tree. NOT re-baselined at a SHA.
- **Restart:** backend `.py` only, `--reload` picks it up; no restart needed.
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — navigate away to /dashboard, wait 65-130s, cold navigate back to /runs/b9feac1c-ec21-4531-8ba7-bb391786993e; each reload's displayed timestamp exactly matched that reload's wall-clock time (09:15 PM, 09:16 PM, 09:17 PM across cycles 1-3), no axis variance needed
- **Root cause (CONFIRMED):** `frontend/src/hooks/useRunChat.ts` `upsertUserMessage` (`:354`) /
  `upsertNarratorMessage` (`:393`) unconditionally stamp `createdAt: new Date().toISOString()` on
  every `chat_message`/`chat_reply` event-frame fold's "create" branch — the branch every replayed
  historical frame takes, since `seedRunChatTranscript` clears `messages` before folding. There is
  no real send time to prefer instead: the backend never emits one on either transport — the live
  SSE payload (`backend/app/api/run_commands.py:1050-1060`, `_sse_frame`) and the durable REST
  replay (`backend/app/api/runs.py:1080-1093`, `get_run_events`) both project only
  `{seq, event_id, type, payload_json}`, never the `run_events.created_at` column that IS stamped
  on the row (`backend/app/models/run_event.py:72`, NOT NULL). `frontend/src/components/chat/MessageBubble.tsx:189`
  renders the fabricated value — confirmed the ONLY consumer of `ChatMessage.createdAt` in the
  whole frontend (grep across `frontend/src`).
- **Blast radius:** `MessageBubble.tsx:189` is the sole render consumer, but the defective fold
  (`upsertUserMessage`/`upsertNarratorMessage`) is reached from every `seedRunChatTranscript`/
  `appendRunChatFrames` call site in `frontend/src/app/[...view]/page.tsx` — cold reload of a
  completed run (this bug's own repro, ISS-358 validated 3/3), history reopen, revision/family
  reopen, AND switching to a still-**generating** run via `AppHeader`'s running-pipeline dropdown
  / `DashboardLayout`'s history sidebar (`handleSwitchToLiveRun`, `page.tsx:2579-2666` — new,
  code-traced this pass, not yet browser-verified: [ISS-595](../.knowledge/cards/20260829-0120-ISS-595.md)).
  The general shape of the backend gap (`run_events.created_at` exists on every row but
  `get_run_events` never projects it) was already flagged for a different event type
  (`pipeline_start`) as [ISS-413](../.knowledge/cards/20260828-2357-ISS-413.md) — fixing that
  projection once would close the backend half of both bugs at once.
- **Proposed fix:** belongs in the shared `get_run_events` projection
  (`backend/app/api/runs.py:1080-1093`) plus `DurableFrame` construction (`frontend/src/lib/api.ts:983`,
  which already merges the row's `event_id`/`seq` columns over `payload_json` — the identical,
  precedented pattern for adding `created_at`), NOT a per-consumer patch: that supplies a real
  timestamp for `upsertUserMessage`/`upsertNarratorMessage` to prefer, for every event type, past
  and future. Frontend-side, `upsertUserMessage`/`upsertNarratorMessage`'s "create" branch should
  prefer `data.created_at` when present and otherwise reuse an existing message's `createdAt` on
  re-fold rather than minting a fresh `Date.now()` — see [ISS-358](../.knowledge/cards/20260828-2118-ISS-358.md)'s
  "Fix direction".
- **Issue cards:** [ISS-358](../.knowledge/cards/20260828-2118-ISS-358.md) (root — pre-existing,
  filed during BUG-20260828-011700-runs-id's fix pass, already named this exact register entry),
  [ISS-595](../.knowledge/cards/20260829-0120-ISS-595.md) (sibling: generating-run state, INFERRED,
  not yet browser-verified); cross-linked to [ISS-413](../.knowledge/cards/20260828-2357-ISS-413.md)
  (the general backend projection gap, different event type, same fix shape)
- **Found at:** 2026-08-28T07:57:00Z
- **Found by:** bug-runs-id-r2
- **Fingerprint:** `/runs/{id}|preview-chat-transcript-message-clock|reload-page-after-sending-chat-message|displayed-message-timestamp-jumps-to-current-load-time-instead-of-original-send-time`
- **Evidence:** `bug-hunter/evidence/runs-id/BUG-20260828-095700-runs-id-chat-timestamp/`

### Summary
Sent a follow-up chat message on a completed run (`Ppt V2`, run `b9feac1c-ec21-4531-8ba7-bb391786993e`). The message and the assistant's reply render with a clock time next to each ("09:51 AM"), which looks like a normal sent/received timestamp. Reloading the page repeatedly shows this pair of timestamps changing on every single reload to match the browser's current wall-clock time at that reload — never staying fixed at the moment the message was actually sent. Cross-checked the backend: `GET /api/runs/{id}/events?after=N` returns the `chat_message`/`chat_reply` event payloads with no `created_at`/timestamp field at all, confirming the frontend has no real send time to render and is falling back to `Date.now()` on each mount. This is a different defect from the already-filed run-header "stuck on just now" bug (`BUG-20260828-011700-runs-id`): that one is a single frozen/wrong value that never updates; this one is not frozen at all — it changes to a new, always-wrong "now" value on every reload.

### Reproduction
1. Sign in as qa-admin, navigate to `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e` (completed run, Preview tab).
2. Type a short message ("Can you make the title larger?") into the chat composer and click Send. A `POST /api/runs/{id}/messages` fires (200 OK); the message and an assistant reply appear in the transcript, each tagged "09:51 AM" (the real send time).
3. Reload the page (`http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e`). Observe: both timestamps on the same message/reply pair now read "09:52 AM".
4. Wait ~1 minute (browser time confirmed via `new Date()`: 09:56:32) and reload again. Observe: both timestamps now read "09:56 AM" — tracking the reload time, not the original 09:51 send.
5. Confirmed via `GET /api/runs/{id}/events?after=9737`: the `chat_message` and `chat_reply` event payloads carry no timestamp field whatsoever, so there is no persisted send time for the frontend to render.

### Expected
A chat message's displayed timestamp should reflect when it was actually sent and stay fixed across reloads (or the backend should persist a `created_at` on the event and the frontend should render that, not the current time).

### Actual
The timestamp recomputes to the browser's current time on every page load, so the same historical message shows a different, always-"just reloaded" time each time the page is revisited — actively misleading about when the exchange happened.

### Evidence
- Before (message sent, shows "09:51 AM" at actual send time): `bug-hunter/evidence/runs-id/BUG-20260828-095700-runs-id-chat-timestamp/01-sent-0951.png`
- Failure (same message, after reload ~5 minutes later, shows "09:56 AM"): `bug-hunter/evidence/runs-id/BUG-20260828-095700-runs-id-chat-timestamp/02-reload-shows-0956.png`
- Additional: `bug-hunter/evidence/runs-id/BUG-20260828-095700-runs-id-chat-timestamp/network.log` (events API excerpt showing no timestamp field in the event payload)

### Browser Signals
- Console: none observed (0 errors)
- Network: `GET /api/runs/{id}/events?after=N` payloads for `chat_message`/`chat_reply` events contain no `created_at`/timestamp field
- State/URL: reproduced across three separate full-page reloads (09:52 AM, 09:55 AM, 09:56 AM), each matching the reload's wall-clock time, never the original 09:51 AM send time

## BUG-20260828-080047-runs-id-steps — Tool-call summary row renders "[object Object]" instead of a readable preview for array/object arguments

- **Page:** Completed run — Steps tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps
- **Severity:** Low
- **Status:** CLOSED
- **Fixed:** 2026-08-29 — `frontend/src/components/results/AgentDetailPanel.tsx`, one function: new `argPreview(v)` helper above `ToolCallsSection` (strings pass through, everything else `JSON.stringify(v) ?? String(v)` in a try/catch — the shape already used by `AuditTab.tsx:105`'s `argvSummary`), and the collapsed preview at `:418` now calls it instead of bare `String(v)`. Fixed at that one expression because `String(v)` occurs exactly once in `frontend/src/` and `ToolCallsSection` has one call site (`:1101`) with no `isRunning` gate, so the same change covers ISS-585's live-run case with no run-state-specific code. Card: FIX-399; ISS-355 and ISS-585 both resolved.
- **Verified:** 2026-08-29 (lane4) — `frontend/src/components/results/AgentDetailPanel.toolCallsPreview.test.tsx` run via `npx vitest run` from `frontend/`: confirmed XPASS first (`Test Files 1 failed (1) / Tests 2 failed (2)`, `Error: Expect test to fail` on both `it.fails` guards), then removed the `.fails` wrapper (kept `it(...)`, no xfail-style marker existed beyond that) and re-ran to plain green: `Test Files 1 passed (1) / Tests 2 passed (2)`. Regression file `AgentDetailPanel.artifactCards.test.tsx`: 15/15 passed. `npx tsc --noEmit`: 0 errors mentioning AgentDetailPanel (pre-existing unrelated errors in `listenerMiddleware.test.ts` from other in-flight work on this shared tree). `npx eslint src/components/results/AgentDetailPanel.tsx`: 0 errors, 5 pre-existing warnings. Backend `:8000/docs` → 200, no restart needed (frontend-only diff). Manual re-run of the original repro in the browser (lane4, qa-admin, cold nav to `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps`, JS `.click()` on the "Deck Engineer Agent" row per the `stepsTabRowBlocked` quirk): all three `write_todos` collapsed rows now read `todos: [{"content":"Map spec sl` — readable truncated JSON, no `[object Object]` anywhere. Console: 0 errors, 1 pre-existing unrelated iframe-sandbox warning, matching the pre-fix baseline. After-screenshot: `bug-hunter/evidence/runs-id-steps/BUG-20260828-080047-runs-id-steps/03-after-fixed-preview.png`. `lint-imports` (run from `backend/`) shows 1 broken contract, but it involves only `.py` files with uncommitted changes unrelated to this fix (`engine.py`, `run_commands.py`, etc. from other in-flight bugs on the shared tree) — pre-existing, not caused by FIX-399's frontend-only diff.
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — sign in fresh, navigate to /dashboard then to the steps route, expand the "Deck Engineer Agent" row via element.click(); no timing/entry-path variance needed, trigger is simply any array/object-valued tool argument (AgentDetailPanel.tsx:412 `String(v)` coercion)
- **Root cause:** CONFIRMED — `ToolCallsSection` (`frontend/src/components/results/AgentDetailPanel.tsx:412`) renders each tool-call arg with bare `String(v)`; JS default coercion yields `[object Object]` for a plain object and `[object Object],[object Object],...` for an array of objects, truncated by `.slice(0, 24)` to the `[object Object],[object` text seen in the UI. Primitives coerce fine, which is why string args (e.g. `write_file`) already render correctly.
- **Blast radius:** Narrow, CONFIRMED by grep — `String(v)` occurs exactly once in `frontend/src/`; `ToolCallsSection` has exactly one caller (`AgentDetailPanel.tsx:1104`, same file); `AgentDetailPanel` itself is rendered from exactly one place (`AgentThinkingTab.tsx:274`, the Steps/Thinking tab). That call site has no `isRunning` gate, so the same code also renders during a live/generating run fed by the identical `tool_call` SSE path (`useWorkflow.ts:1057-1064`) — INFERRED, not yet reproduced live, filed as [ISS-585](../.knowledge/cards/20260829-0256-ISS-585.md). `AttachedSkillsSection`/`AttachedHooksSection` visually mirror this row's layout but read fixed string fields only, not `Object.entries`+coercion — checked and ruled out as siblings.
- **Fix:** Belongs in `ToolCallsSection` at `AgentDetailPanel.tsx:412` — the sole call site — replace bare `String(v)` with a type-aware stringifier for arrays/objects (JSON-encode before truncating; primitives keep today's behavior). Precedent for this exact pattern already exists in this codebase at `frontend/src/components/results/AuditTab.tsx:105` (`try { JSON.stringify(x) } catch { String(x) }`).
- **Issue cards:** [ISS-355](../.knowledge/cards/20260828-2105-ISS-355.md) (root — pre-existing card, root cause re-confirmed by direct read), [ISS-585](../.knowledge/cards/20260829-0256-ISS-585.md) (sibling, INFERRED: same bug should also fire live during a generating run, not only a completed one — no run-state gate on `ToolCallsSection`)
- **Found at:** 2026-08-28T08:00:47Z
- **Found by:** bug-runs-id-steps-r2
- **Fingerprint:** `/runs/[id]/steps|agent-detail-tool-calls-panel|expand-agent-row-with-array-object-tool-args|collapsed-summary-shows-literal-object-object-instead-of-readable-preview`
- **Evidence:** `bug-hunter/evidence/runs-id-steps/BUG-20260828-080047-runs-id-steps/`

### Summary
On the Steps tab, expanding an agent row's "Tool calls" panel shows a one-line collapsed summary
for each call (`<tool_name>  <args preview>  ok`). When a tool's argument value is an array of
objects (the `write_todos` tool's `todos` array, an array of `{content, status}` items), the
collapsed summary literally renders `todos: [object Object],[object` — the raw result of
JavaScript's default `Array.prototype.toString()`/string-coercion applied directly to the object
array, instead of a readable preview (e.g. a truncated JSON string or item count). The fully
expanded "Arguments" panel underneath renders the same data correctly as pretty-printed JSON, so
the underlying data is present and correct — only the collapsed one-line preview is broken.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps`.
2. Via `browser_evaluate` + `.click()` (per the `stepsTabRowBlocked` quirk — normal clicks are
   intercepted by adjacent controls), expand the "Deck Engineer Agent" lane row.
3. Observe the "Tool calls 4" section auto-expanded, listing 4 calls. Three of the four are
   `write_todos` calls; each renders its collapsed row as:
   `write_todos   todos: [object Object],[object   ok`
4. Expand the first `write_todos` call to reveal its "Arguments" panel — it renders correctly as
   pretty-printed JSON (`{ "todos": [ { "content": "...", "status": "in_progress" }, ... ] }`),
   confirming the underlying data is intact and the defect is isolated to the collapsed summary
   line's own rendering logic.
5. Repeated on the second and third `write_todos` calls in the same panel — identical
   `[object Object],[object` text in all three collapsed rows.
6. For contrast, the sibling `write_file` call in the same list (whose argument is a plain
   string, not an array of objects) renders its collapsed preview correctly:
   `write_file  file_path: /tmp/kindred-pitch-deck., content: <!DOCTYPE html> <html la  ok`.

### Expected
The collapsed tool-call summary should show a readable preview of any argument value — a
truncated JSON string, item count, or similar — regardless of whether that argument is a string,
array, or object.

### Actual
Array-of-object arguments (e.g. `write_todos`'s `todos` list) are coerced with JavaScript's
default array/object stringification, producing the literal text `[object Object],[object` in
the collapsed summary row shown to the user, on every occurrence (3/3 in this run).

### Evidence
- Before (agent lane list, unexpanded): `bug-hunter/evidence/runs-id-steps/BUG-20260828-080047-runs-id-steps/01-before-agent-list.png`
- Failure (`write_todos` collapsed row showing `[object Object],[object`, with the correctly-rendered "Arguments" JSON panel visible directly below for contrast): `bug-hunter/evidence/runs-id-steps/BUG-20260828-080047-runs-id-steps/02-failure-object-object-preview.png`

### Browser Signals
- Console: none observed (0 errors, pre-existing 1 warning unrelated to this interaction)
- Network: no request involved — purely a client-side rendering defect on already-fetched step data
- State/URL: stayed on `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/steps` throughout; reproduced on
  all 3 `write_todos` calls within the "Deck Engineer Agent" row's Tool calls panel

## BUG-20260828-081200-analytics — Pipeline filter narrows the breakdown list but leaves every KPI tile, chart, and Success Rate on unfiltered all-pipelines data

- **Page:** Analytics
- **Route:** /analytics
- **Severity:** High
- **Status:** CLOSED
- **Verified:** 2026-08-28 — `tests/integration/e2e/suites/10_analytics/test_analytics.py`
  run whole (offline tier, `.venv/bin/python3 -m pytest`): 21 passed, 1 skipped (ISS-289, no
  model-scoped Prototype run in this seed data, documented), 0 failed. ISS-229/ISS-288's tests
  XPASS(strict) confirmed first, then `xfail` markers removed and the file re-run to a plain
  green. `backend/tests/unit/test_analytics_api.py` 8/8 passed
  (`venv/bin/python3 -m pytest`, the venv the running `--reload` server actually uses).
  `frontend/src/components/analytics/AnalyticsPage.test.tsx` 9/9 passed (`npx vitest run`).
  Manual re-run of the original repro in the browser (qa-admin, lane4, `/analytics?range=all`):
  baseline Total Runs 278 (159 completed/38 failed)/97.3M tokens/$52.82/57%; selecting
  "Prototype" now fires `GET /api/analytics/summary?range=all&pipeline=prototype` (confirmed via
  `browser_network_requests`, absent before the fix) and the tiles/chart/Success Rate/By Model
  all rescope to 26 runs (5 completed/8 failed)/22.3M tokens/$8.11/19% — matching the "By
  Pipeline Type" breakdown's 18+8=26; selecting "Filter by model" → "Haiku 4.5" separately moved
  Total Runs from 278 to 7, matching that model's own breakdown row (ISS-288). No console errors
  on either page. `backend/` `lint-imports`: 3 kept / 1 broken — the pre-existing
  `agents.execution_engine` → `app.api` contract break, unchanged by this diff. `npx tsc
  --noEmit`: only pre-existing, unrelated errors in
  `HomeLaunchGrid.crossAccountLeak.test.tsx`/`listenerMiddleware.test.ts` (files this fix does
  not touch). `:8000/docs` and `:3000` both 200; `--reload` already picked up the backend change.
  After-screenshot:
  `bug-hunter/evidence/analytics/BUG-20260828-081200-analytics/03-after-prototype-filter-kpis-scoped.png`.
- **Found at:** 2026-08-28T08:12:00Z
- **Found by:** bug-analytics-r1
- **Fingerprint:** `/analytics|pipeline-type-filter|select-a-pipeline-type|kpi-tiles-chart-and-success-rate-stay-unfiltered`
- **Evidence:** `bug-hunter/evidence/analytics/BUG-20260828-081200-analytics/`
- **Validated:** 3/3 on 2026-08-28 — reproduced on every cycle (click-through and cold deep-link
  with `?pipeline=` preset, ranges `all` and `30d`, pipelines Prototype/User Stories/Presentation);
  unconditional on this page, no varying axis flips it.
- **Root cause:** `AnalyticsPage.tsx`'s fetch `useEffect` depends on `[dateFilter]` only
  (`AnalyticsPage.tsx:154-177`) and `getAnalyticsSummary`/`GET /api/analytics/summary` accept
  only `range` (`api.ts:789-797`, `backend/app/api/analytics.py:278-297`) — no `pipeline`/`model`
  query param exists server-side. KPI tiles, the Daily Activity chart, Success Rate, and the
  token breakdown (`AnalyticsPage.tsx:193-242`) all read straight off the one unfiltered `summary`
  object; only `pipelineRows` (244-252) and `modelRows` (258-267) apply a client-side `.filter()`,
  each against only the ONE query param it owns.
- **Blast radius:** `getAnalyticsSummary` has exactly 2 callers (`grep -rn "getAnalyticsSummary"
  frontend/src`) — `AnalyticsPage.tsx:163` (this bug) and `HomeLaunchGrid.tsx:206` (hardcoded
  `range="all"`, no filter UI, not affected). Within `AnalyticsPage.tsx` itself the same
  single-unfiltered-summary flaw also covers the **model** filter (untested by the hunter) and a
  cross-filter gap where "By Pipeline Type" ignores the model filter and vice versa.
- **Fix belongs:** server-side, in `_aggregate()`/`get_analytics_summary`
  (`backend/app/api/analytics.py:278-297`) — add allow-listed `pipeline`/`model` query params
  filtered on BEFORE rollup, alongside the existing `cutoff` filter, mirroring the "SC-1 server
  recompute" pattern already used for `range`. The daily/success-rate figures cannot be
  correctly filtered client-side at all: `daily` has no per-type breakdown and `PipelineRollup`/
  `ModelRollup` carry no completed/failed split in the current payload shape.
- **Issue cards:** [ISS-229](../.knowledge/cards/20260828-1601-ISS-229.md) (root),
  [ISS-288](../.knowledge/cards/20260828-1715-ISS-288.md) (sibling: model filter has the
  identical flaw), [ISS-289](../.knowledge/cards/20260828-1715-ISS-289.md) (sibling: the two
  breakdown lists ignore each other's filter)
- **Fix card:** [FIX-339](../.knowledge/cards/20260828-2231-FIX-339.md) — `pipeline`/`model`
  are now query params on `GET /api/analytics/summary`, filtered before `_aggregate()`
  (`backend/app/api/analytics.py:310-323`), and the fetch effect depends on all three filters
  (`AnalyticsPage.tsx:186`). E2E: ISS-229 + ISS-288 XPASS(strict) (the pass signal, markers
  left for the verifier); ISS-289's test SKIPPED — no prototype run on this seed data carries
  a named `model_id`, so the model select is not rendered once the pipeline filter applies.

### Summary
Selecting a specific pipeline type in the "Filter by pipeline" dropdown correctly narrows the
"By Pipeline Type" breakdown list to just the matching entries, but every other figure on the
page — Total Tokens, Est. Cost, Avg/Run, Total Runs, the Daily Activity chart, Success Rate, and
the By Model panel — stays frozen on the unfiltered all-pipelines totals. `browser_network_requests`
confirms no new `/api/analytics/summary` call fires when the filter changes (only a Next.js RSC
navigation request), so the filter is applied client-side to one list only, never re-derives the
rest of the page. This makes the page self-contradictory: the tiles say "$50.80 across 157
completed runs" and "273 total runs" while the breakdown directly below says Prototype is only
$7.25 + $0.86 across 18 + 8 = 26 runs.

### Reproduction
1. Go to `/analytics` as qa-admin, range = "All" (or any range).
2. Note KPI tiles: Total Tokens 93.1M, Est. Cost $50.80, Avg/Run 340.9K, Total Runs 273
   (157 completed · 37 failed), Success Rate 58% (157/37/273), Daily Activity chart bars.
3. Open "Filter by pipeline" and select "Prototype" (URL becomes `?range=all&pipeline=prototype`).
4. Observe the "By Pipeline Type" list now shows only the two Prototype rows (18 runs/19.9M/$7.25
   and 8 runs/2.4M/$0.86) — filtering worked here.
5. Observe the KPI tiles, Daily Activity chart, Success Rate donut/breakdown, and "By Model"
   panel are byte-identical to step 2 — still 93.1M tokens / $50.80 / 273 runs / 58%.
6. Repeated with "User Stories" selected: same result, KPI tiles still show 273 total runs.

### Expected
Selecting a pipeline type should scope the entire page's figures (KPI tiles, chart, success
rate, model breakdown) to runs of that type, consistent with the already-filtered "By Pipeline
Type" list.

### Actual
Only the "By Pipeline Type" list itself is filtered; every other section on the page keeps
showing the unfiltered totals for all 273 runs, contradicting the numbers shown directly next to
it.

### Evidence
- Before (All pipelines, baseline KPIs): `bug-hunter/evidence/analytics/BUG-20260828-081200-analytics/01-before-all-pipelines.png`
- Failure (Prototype selected — KPI tiles/chart/success-rate unchanged, only the list below filtered): `bug-hunter/evidence/analytics/BUG-20260828-081200-analytics/02-failure-prototype-filter-kpis-unchanged.png`

### Browser Signals
- Console: none observed
- Network: no `/api/analytics/summary?...&pipeline=prototype` request fires on filter change — verified via `browser_network_requests`; only `GET /api/analytics/summary?range=all` from initial load and a client-side RSC navigation request
- State/URL: URL correctly updates to `?range=all&pipeline=prototype` / `?range=all&pipeline=user_stories`, but the rendered KPI data does not follow it

## BUG-20260828-082706-runs-id-files — Files tab file sizes are character counts, not byte counts, understating every non-ASCII file

- **Page:** Completed run — Files tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files
- **Severity:** Low
- **Status:** CLOSED
- **Verified:** 2026-08-29 — 5 tests across
  `frontend/src/components/results/FilesTab.byteSize.test.tsx`,
  `frontend/src/components/preview/PrototypePreview.byteSize.test.tsx`,
  `frontend/src/components/preview/AppBuilderPreview.byteSize.test.tsx`,
  `frontend/src/components/workflow/prototype/CustomTemplateModal.byteSize.test.tsx` observed
  XPASS (`it.fails` → `Error: Expect test to fail`), `it.fails` markers removed, all 4 files
  re-run plain green (`npx vitest --run`, one file at a time). Regression:
  `FilesTab.test.tsx` 14/14 green. Manual repro re-run by hand on
  `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files` as qa-admin: `prompt.md` now shows
  "626 B" (was "620 B"), `01-presentation-strategist-agent.md` "9.6 KB" (was "9.5 KB"),
  `02-deck-engineer-agent.md` "55.2 KB" (was "55.1 KB"), `04-pptx-code-generator.md` "28.9 KB"
  (was "28.8 KB") — all now match the true byte counts from the original repro's `wc -c`
  measurements. No console errors on the page. `npx tsc --noEmit` clean on all 5 touched
  files (pre-existing unrelated errors in other test files untouched by this fix).
  `lint-imports` from `backend/` shows the same pre-existing `kernel_services`/
  `revision_analyzer` contract break as before — unrelated to this frontend-only change, not
  introduced by it. After-screenshot:
  `bug-hunter/evidence/runs-id-files/BUG-20260828-082706-runs-id-files/02-files-tab-after-fix-sizes.png`.
- **Validated:** 3/3 on 2026-08-28, all cycles from a cold start — no trigger condition needed
  beyond content containing a multi-byte UTF-8 character
- **Root cause:** `frontend/src/components/results/FilesTab.tsx` — every file-size label calls
  `formatSize(x.length)` (11 call sites: lines 103, 116, 236, 393, 401, 418, 426, 546, 572, 616,
  649) where `x` is a JS string. `String.prototype.length` counts UTF-16 code units, not UTF-8
  bytes; `formatSize` itself (`:1120-1124`) is a correct bytes→`B`/`KB`/`MB` formatter, so the
  defect is purely in what each call site feeds it. The one exception, `formatSize(file.size)`
  (`:447`, `withWorkspaceFile`), is already correct — `file.size` comes from the backend's
  `SandboxFile` API — and self-corrects ONLY `derivedFiles[0]` (the single Final-output row) when
  `resolveRunDeliverable` (`:506-524`) successfully resolves a matching workspace file; every
  other row (Run input, agent outputs, parsed code files, the generic-deliverable row, and the
  Final-output row itself whenever workspace resolution fails or doesn't apply) has no such
  correction and stays wrong.
- **Blast radius:** all 11 `formatSize(x.length)` sites within `FilesTab.tsx` (confirmed by
  reading the file — matches [ISS-351](../.knowledge/cards/20260828-2103-ISS-351.md)'s own
  count). Grepping the identical `.length`-as-bytes anti-pattern project-wide (not calls to
  `formatSize` — independent inline occurrences of the same mistake) found 3 more components,
  each unrelated to FilesTab.tsx and to each other: `CustomTemplateModal.tsx:80,232,267` (custom
  prototype template loader — line 80 is worse than a display bug, it gates a "max 2 MB" upload
  cap on `text.length`, so an over-cap file with multi-byte UTF-8 content can be wrongly
  accepted), `PrototypePreview.tsx:570` (source-view "X KB" label), `AppBuilderPreview.tsx:556`
  (file-explorer footer "KB total", summed across files). Ruled out as unaffected: `ChatAttachments.tsx`/
  `useChatAttachments.ts`/`RunChatLane.tsx` (already use real `File.size` / `approxBase64Bytes`),
  `SandboxTab.tsx` (`formatBytes(file.size)`, real API bytes), `AccountSettings.tsx`/
  `StartingPointCard.tsx` (`.length` labelled "chars", not a byte unit — correct as written).
- **Fix belongs:** one shared UTF-8 byte-length helper (e.g. `new TextEncoder().encode(str).length`
  or `new Blob([str]).size` — the latter already used in this exact file for the download Blob)
  added to `frontend/src/lib/` (no such helper currently exists there — the closest precedent is
  `resizeImage.ts`'s `approxBase64Bytes`), then every `formatSize(x.length)` call in
  `FilesTab.tsx` and the 3 sibling inline computations swapped to call it instead of `.length`.
  One helper, ~15 call sites fixed — not a per-file reimplementation.
- **Issue cards:** [ISS-351](../.knowledge/cards/20260828-2103-ISS-351.md) (root, FilesTab.tsx —
  pre-existing, filed by validation),
  [ISS-587](../.knowledge/cards/20260829-0257-ISS-587.md) (sibling: PrototypePreview.tsx source
  view, INFERRED),
  [ISS-588](../.knowledge/cards/20260829-0257-ISS-588.md) (sibling: AppBuilderPreview.tsx footer
  total, INFERRED),
  [ISS-589](../.knowledge/cards/20260829-0257-ISS-589.md) (sibling: CustomTemplateModal.tsx —
  display AND the 2 MB cap-check bypass, INFERRED)
- **Fix cards:** [FIX-402](../.knowledge/cards/20260829-0414-FIX-402.md) — one shared
  `utf8Bytes()` helper in `frontend/src/lib/byteSize.ts`, all 15 sites repointed onto it
- **Found at:** 2026-08-28T08:27:06Z
- **Found by:** bug-runs-id-files-r2
- **Fingerprint:** `/runs/[id]/files|file-size-label|render-files-list-with-non-ascii-content|size-shown-is-utf16-char-count-not-byte-count`
- **Evidence:** `bug-hunter/evidence/runs-id-files/BUG-20260828-082706-runs-id-files/`

### Summary
Every file-size label on the Files tab (Run input, agent outputs, and — where content is text —
the Final output row) is computed from the text content's character/`.length` count rather than
its true byte size. Any file whose content contains multi-byte UTF-8 characters (this pipeline's
LLM output uses em dashes `—` and right-arrows `→`) is displayed smaller than the file the
Download button actually delivers.

### Reproduction
1. Sign in as qa-admin, go to `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files`.
2. Note the declared sizes: Run input `prompt.md` "620 B"; agent outputs
   "01-presentation-strategist-agent.md" "9.5 KB", "02-deck-engineer-agent.md" "55.1 KB",
   "04-pptx-code-generator.md" "28.8 KB".
3. Click each row's Download button and measure the downloaded file with `wc -c` (true bytes):
   `prompt.md` = 626 B; `01-...md` = 9845 B (9.62 KB); `02-...md` = 56564 B (55.24 KB);
   `04-...md` = 29584 B (28.89 KB).
4. Compute the UTF-16/`.length`-style character count of the same content: 620, 9686, 56398,
   29459 respectively — these match the UI's declared sizes exactly (after KB rounding), not the
   true byte counts.
5. Repeated on a second, independently downloaded file set from the same run — same pattern held
   for all four rows checked.

### Expected
The size label next to each file should reflect the actual byte size of the file that Download
delivers (matching what `wc -c` / the OS reports for the downloaded artifact).

### Actual
The size label reflects the text's character count (UTF-16 code units), which is smaller than
the true UTF-8 byte size whenever the content contains multi-byte characters — off by 6 bytes on
the smallest file (prompt.md: 620 declared vs 626 actual) and by 100–200+ bytes on the larger
agent-output files.

### Evidence
- Files tab with declared sizes: `bug-hunter/evidence/runs-id-files/BUG-20260828-082706-runs-id-files/01-files-tab-declared-sizes.png`
- Byte-vs-character-count comparison table and methodology: `bug-hunter/evidence/runs-id-files/BUG-20260828-082706-runs-id-files/notes.md`

### Browser Signals
- Console: none related; page loaded cleanly.
- Network: `GET /api/runs/{id}/sandbox` returns true byte sizes correctly (e.g.
  `conversation_history/...:ppt-code-generator.md` = 319756, `presentation.html` = 54551) — the
  backend has the correct byte sizes, so the mismatch is introduced client-side when the Files
  tab computes/display the per-row size for text content instead of using the API-provided size.
- State/URL: reproduces identically on `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/files` via
  both a hard reload and client-side SPA navigation into the tab.

## BUG-20260828-audit-export-r2 — Audit tab's CSV and JSON export strip the Security/Governance category distinction and never populate the promised "severity" column

- **Page:** Completed run — Audit tab
- **Route:** /runs/b9feac1c-ec21-4531-8ba7-bb391786993e/audit
- **Severity:** Medium
- **Status:** DUPLICATE
- **Validated:** 0/3 on 2026-08-28, cold starts — CSV/JSON `category` is now `"hook"` (source
  label) with a correctly-differentiated `fineCategory` (activity=96, security=4), not
  hardcoded `"gate"`; `severity` empty on all 100 rows matches expected behavior for a run
  with 0 blocked/critical events, not a defect. Already fixed by FIX-326 (see below).
- **Duplicate of:** [ISS-211](../.knowledge/cards/20260828-1429-ISS-211.md), resolved by
  [FIX-326](../.knowledge/cards/20260828-1656-FIX-326.md) — same exporter
  (`frontend/src/lib/exporters/auditExporter.ts`), same category-collapse symptom, already
  fixed in `AuditTab.tsx` before this bug was filed.
- **Found at:** 2026-08-28T08:41:00Z
- **Found by:** bug-runs-id-audit-r2
- **Fingerprint:** `/runs/{id}/audit|export-csv-json|click-export-then-csv-or-json|category-always-gate-severity-always-empty-contradicting-promised-columns`
- **Evidence:** `bug-hunter/evidence/runs-id-audit/_scratch/BUG-20260828-audit-export-r2-notes.md`

### Summary
The Audit tab's rows visibly carry two different category badges on screen — "Gate" for
governance/gate rows and "Security" for secret-scan rows (pill counts read "Governance 96,
Security 4"). The Export menu explicitly advertises that both the CSV ("flattened rows
timestamp · agent · category · event · outcome · severity") and JSON ("raw rows incl.
category · step · outcome · severity · timestamp") exports include a `category` and a
`severity` field. In the actual downloaded files, every one of the 100 exported rows has
`category` hard-coded to `"gate"` — including the 4 rows the UI itself badges "Security" —
and `severity` is an empty string on every single row, despite the page's own persistent
footer copy promising "every entry carries severity + timestamp · exportable to CSV / JSON
for compliance review."

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/audit`.
2. Note the on-screen category badges differ per row: governance/gate rows show "Gate", the
   4 secret-scan rows show "Security" (pill counts "Governance 96", "Security 4").
3. Click "Export" -> "CSV — flattened rows timestamp · agent · category · event · outcome ·
   severity". A file downloads.
4. Open the downloaded CSV. Every row's `category` column reads `gate`, including the rows
   whose `label` is "Secret scan — scanned before write" (the ones badged "Security" on
   screen). Every row's `severity` column is empty.
5. Repeat with "Export" -> "JSON — raw rows incl. category · step · outcome · severity ·
   timestamp". Same result: `category` is `"gate"` for all 100 objects, `severity` is `""`
   for all 100 objects.

### Expected
The exported category field should reflect the same Security/Governance distinction visible
in the UI (or at minimum not silently collapse it to a single value), and the severity field
that both the export menu and the page's own footer copy explicitly promise should be
populated per the app's stated severity model, not permanently empty.

### Actual
Both export formats always write `category: "gate"` regardless of the row's on-screen badge,
erasing the Security/Governance split the UI itself displays, and `severity` is unconditionally
empty on every row in every export, contradicting the feature's own advertised column list and
its "compliance review" framing.

### Evidence
- Before (Audit tab loaded, badges show distinct "Gate"/"Security" labels per row):
  `bug-hunter/evidence/runs-id-audit/BUG-20260828-audit-export-r2/01-before-export-menu-open.png`
- Downloaded CSV (all 100 rows `category=gate`, `severity` empty):
  `bug-hunter/evidence/runs-id-audit/BUG-20260828-audit-export-r2/03-export.csv`
- Downloaded JSON (same defect, raw rows):
  `bug-hunter/evidence/runs-id-audit/BUG-20260828-audit-export-r2/04-export.json`
- Repro notes and verification commands:
  `bug-hunter/evidence/runs-id-audit/BUG-20260828-audit-export-r2/notes.md`

### Browser Signals
- Console: no errors on export click.
- Network: n/a — export is generated client-side from already-loaded row data (both CSV
  and JSON downloads succeed with correct row COUNT — 100 — so this is a field-mapping
  defect, not a fetch failure).
- State/URL: stays on `/runs/{id}/audit` throughout; downloads complete normally, only the
  field content is wrong.

## BUG-20260828-084621-runs-id-preview-full — Preview toolbar's "Full Screen" button renders entirely outside a narrow (mobile) viewport with no scroll affordance to reach it

- **Page:** Full-bleed deliverable view
- **Route:** /runs/{id}/preview/full
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — test_iss314_preview_toolbar_fullscreen_offscreen.py XPASS(strict)
  confirmed, xfail marker removed, re-run plain green (`PASS 0 shots 15.0s`). Manual re-run of the
  original repro (qa-admin, `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/preview/full`, viewport
  reset to 375x700 via `window.innerWidth` check per the `viewportUnreliable` quirk) now shows
  the Full Screen button at `left: 125.2, right: 218.6` — fully inside the 375px viewport,
  `elementFromPoint` at its center resolves to the button itself, and clicking it opens the
  deliverable in a new tab. `document.documentElement.scrollWidth === clientWidth === 375`
  unchanged (still no scrollbar, none needed — the row now wraps). Frontend regression:
  `PreviewPanel.test.tsx` 19/19 passed (vitest). `tsc --noEmit` clean for `PreviewPanel.tsx`
  (pre-existing unrelated errors in other test files, none touching this fix). Backend
  `:8000/docs` → 200 (pure frontend change, no restart needed). `lint-imports` from `backend/`
  shows 1 pre-existing broken contract (`kernel imports only capability ports`) unrelated to this
  fix — zero backend files touched. No new console errors on the affected page (1 pre-existing
  iframe-sandbox warning, unrelated). After-screenshot:
  `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-084621-runs-id-preview-full/04-verify-after-mobile-fullscreen-visible.png`.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced identically on every cold-start attempt, no axis narrowing required
- **Issue card:** [ISS-314](../.knowledge/cards/20260828-1946-ISS-314.md)
- **Root cause:** `PPTTabActions`'s own wrapper div is `flex items-center gap-1.5 flex-shrink-0`
  (`frontend/src/components/preview/PreviewPanel.tsx:1540`, holding the "Download"/"Download PPTX"
  and "Full Screen" buttons, `1559-1566`) with no `flex-wrap`/`overflow-x` anywhere in its ancestor
  chain — the right-cluster wrapper (`PreviewPanel.tsx:1221`) and the tab-bar row itself
  (`PreviewPanel.tsx:1203`, `flex items-center justify-between gap-2`) are both equally rigid. At a
  375px viewport the row's ~493px of content has no way to wrap, shrink, or scroll into view.
  CONFIRMED by direct read at the file:lines above (line numbers shifted from ISS-314's original
  1450/1474-1481 because the file moved under later commits — same code, same defect).
- **Blast radius:** `PreviewPanel` (and therefore `PPTTabActions`) has exactly one production call
  site — `frontend/src/components/layout/DashboardLayout.tsx:3127`, confirmed by grepping every
  `<PreviewPanel` usage in `frontend/src/` (all other matches are test files). That call site sits
  inside a `flex flex-col md:flex-row` split (`DashboardLayout.tsx:3014`) which stacks to full
  width below the `md` (768px) breakpoint, so the identical defect reproduces on the plain
  `/runs/{id}` route too, not just `/runs/{id}/preview/full` — both routes mount the same component
  at the same width at 375px. This is the same instance/fix, not a separate defect.
- **Sibling (INFERRED):** `frontend/src/components/preview/PrototypePreview.tsx:502`'s
  "browser chrome" toolbar (dots + URL pill + 3 zoom buttons + divider + Tweaks + Source + Open) is
  a structurally identical anti-pattern — no `flex-wrap`/`overflow-x` in its chain either, and MORE
  fixed-width elements than the confirmed-broken PPT row. Filed as [ISS-433](../.knowledge/cards/20260829-0040-ISS-433.md),
  not yet measured in-browser.
- **Fix belongs in:** the shared tab-bar row/right-cluster in `PreviewPanel.tsx` (lines
  1203/1221, or `PPTTabActions`'s own row at 1540) so every current and future renderType's toolbar
  actions route through one overflow-safe container — matching the precedent already set in
  [FIX-013](../.knowledge/cards/20260616-FIX-013.md) (AgentsPopup: wrap the overflowing sections in
  a shared `overflow-y-auto` container rather than patching each section). `PrototypePreview.tsx`'s
  chrome bar is a separate component and needs its own, independent fix at line 502 if ISS-433
  reproduces.
- **Issue cards:** [ISS-314](../.knowledge/cards/20260828-1946-ISS-314.md) (root),
  [ISS-433](../.knowledge/cards/20260829-0040-ISS-433.md) (sibling: PrototypePreview chrome bar,
  INFERRED — originally minted ISS-431, re-minted after a concurrent-writer id collision, see card
  for detail)
- **Found at:** 2026-08-28 08:46 UTC
- **Found by:** bug-runs-id-preview-full-r2
- **Fingerprint:** `/runs/{id}/preview/full|preview-toolbar-fullscreen-button|resize-viewport-to-375px-width|button-bounding-box-left-edge-exceeds-window-innerWidth-with-no-scroll-mechanism`
- **Fix card:** [FIX-378](../.knowledge/cards/20260829-0207-FIX-378.md) — `flex-wrap` on the shared
  tab-bar row `frontend/src/components/preview/PreviewPanel.tsx:1203`; the action cluster drops to a
  second line at 375px, Full Screen right edge ~219px. Test XPASS(strict) 2026-08-29 02:05.
- **Evidence:** `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-084621-runs-id-preview-full/`

### Summary
On `/runs/{id}/preview/full` for a completed run, the Preview tab's toolbar row (Renders-as
toggle area's sibling row holding a secondary "Download" button and the "Full Screen" button)
does not wrap or scroll at narrow viewport widths. Its immediate wrapper div carries
`flex-shrink-0`, so at a 375px-wide viewport (verified via `window.innerWidth`, not screenshot
pixels) the row's total content width grows to ~493px while the row container is capped at
375px. Nothing in the ancestor chain sets `overflow-x: auto/scroll`, and the document itself
reports no horizontal scroll (`document.documentElement.scrollWidth === clientWidth === 375`).
The result: the "Full Screen" button's entire bounding box (`left: 400`, `right: 493`) sits
outside the visible/interactive viewport permanently — `document.elementFromPoint` at the
viewport's right edge resolves to a different, unrelated button, confirming there is no way for
a real pointer/touch user to see or reach "Full Screen" at this width. Part of the secondary
toolbar "Download" button is also clipped (right edge at 386.6 vs 375px viewport), though it
remains mostly clickable; "Full Screen" is completely unreachable.

### Reproduction
1. Sign in as qa-admin, navigate to
   `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/preview/full` (completed
   run, Preview tab auto-selected).
2. Resize the browser viewport to 375×700 (verify with `window.innerWidth` — confirmed 375, not
   just a screenshot artifact).
3. Inspect the toolbar row containing "Download" and "Full Screen" (siblings of the Preview
   tablist). Run `document.querySelectorAll('button')` to find the "Full Screen" button and read
   `getBoundingClientRect()`.
4. Observe: `left: 400.02`, `right: 493.38`, while `window.innerWidth: 375` — the button's box is
   entirely to the right of the viewport. `document.elementFromPoint` at the clamped right edge
   of the viewport returns a different button (the composer's send button), not "Full Screen".
   No horizontal scrollbar exists anywhere in the ancestor chain to scroll it into view.
5. Reproduced on a fresh full page reload/navigation to the same URL at the same viewport size —
   identical rect, identical unreachability.

### Expected
At narrow/mobile viewport widths, all toolbar controls (including "Full Screen") should either
wrap onto a new line, shrink to fit, or live behind a horizontally scrollable/overflow-safe
container, so every control remains visible and clickable.

### Actual
The toolbar row's "Full Screen" button is pushed completely outside the viewport's horizontal
bounds with `flex-shrink-0` preventing any shrink and no scroll mechanism provided — the control
is permanently invisible and unclickable for any user on a ~375px-wide viewport (a standard
mobile width).

### Evidence
- Before (default/desktop width, "Full Screen" fully visible and clickable): `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-084621-runs-id-preview-full/01-before-desktop-fullscreen-visible.png`
- Failure (375px viewport, "Full Screen" text/button clipped off the right edge): `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-084621-runs-id-preview-full/02-failure-mobile-fullscreen-offscreen.png`
- Reproduced on a second, fresh navigation at the same viewport: `bug-hunter/evidence/runs-id-preview-full/BUG-20260828-084621-runs-id-preview-full/03-repro2-fresh-nav-still-offscreen.png`

### Browser Signals
- Console: none observed (0 errors related to this)
- Network: none relevant
- State/URL: `location.href` stays on `/runs/{id}/preview/full`; measured via
  `getBoundingClientRect()` (`left: 400.02, right: 493.38`) against `window.innerWidth: 375`
  (`viewportUnreliable` quirk avoided by reading `window.innerWidth` directly, not screenshot
  pixel dimensions)

## BUG-20260828-085047-runs-id-stream — Completed run's "Download the deliverable" toolbar button stays permanently disabled when the backend never populates `deliverable_filename`, even though the deliverable is fully rendered

- **Page:** Stream view (run detail, Preview tab toolbar)
- **Route:** /runs/{id}/stream
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 by 6-verifier. `tests/integration/e2e/suites/07_run_detail/test_iss313_toolbar_download_missing_filename.py` XPASS(strict) confirmed, `xfail` marker removed, re-run plain green (1 passed). `frontend/src/components/preview/PreviewPanel.test.tsx` 19/19 green. Manual repro re-driven in the browser as qa-admin against the same run (`649e56cf-ce0f-4a0f-91fa-4e75a971a980`, /stream): toolbar "Download the deliverable" now `[cursor=pointer]`, no `[disabled]`; clicked it and it actually downloaded `workspace-649e56cf.zip`. No new console errors. `npx tsc --noEmit`: 0 errors in `PreviewPanel.tsx`. `PreviewPanel.phantomFile.test.tsx` still fails, confirmed pre-existing/unrelated (ISS-323, no xfail marker, not this bug's test). `lint-imports` (run from `backend/`) shows 1 broken contract (`engine.py` -> `app.api` via `kernel_services`/`revision_analyzer`) — pre-existing, backend untouched by this fix, not introduced here. Backend restart not required (frontend-only `.tsx` change; `:8000/docs` returns 200). Evidence: `bug-hunter/evidence/runs-id-stream/BUG-20260828-085047-runs-id-stream/05-after-fix-download-enabled.png`.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic, no timing dependency; reproduced across cold navigation and full reload
- **Root cause:** `WorkflowCompiler._compile_deliverable` (`backend/agents/workflows/compiler.py:1446-1451`) copies `deliverable.name` verbatim from the manifest with no validation/fallback when a manifest declares `deliverable.strategy` without `deliverable.name` — unlike `mimetype`, which gets a computed per-strategy default at emission (`_mimetype.py:49-65`). `backend/agents/workflows/playwright_smoke_test/workflow.yaml:25-26` (`strategy: serialized_sandbox`, no `name:`) is exactly such a manifest — confirmed via YAML-parsing all 26 manifests, the only one of 3 affected that is `user_launchable: true`. The `None` flows verbatim through `engine.py:3737`/`:3754` (`pipeline_complete.deliverable_filename`), through `run_commands.py:3050-3051`'s correctly-guarded `if not None` writer (leaving `WorkflowRun.deliverable_filename` NULL), to `PreviewPanel.tsx:928-932`, whose toolbar-download effect returns early on a falsy `declared` name and never sets `deliverableFile`, so `canHeaderDownload` (`PreviewPanel.tsx:979`) stays `false` forever.
- **Blast radius:** every consumer of `deliverable_filename`/`deliverableFilename` grepped across backend+frontend. Confirmed-broken: `PreviewPanel.tsx` toolbar Download (this bug). Same gate pattern, unreproduced: `RunChatLane.tsx`'s chat-lane `DeliverableCard` (ISS-434). Checked and NOT broken: `chat_narrator.py:194-200`'s deep-link target fallback (inert — `target` is a dedup key, never parsed for a filename), `run_commands.py` DB writer (guard is correct, not the defect), `WorkflowHistory.tsx:928` (has its own documented generic-name fallback). Fix belongs upstream of all of them: a `default_deliverable_name(strategy, ...)` sibling to `default_mimetype`, applied once at `engine.py:3737` — NOT a frontend-only fix, since `PreviewPanel.tsx`'s toolbar effect duplicates `resolveRunDeliverable`'s (`frontend/src/lib/api.ts:1089`) logic inline instead of calling it, so a fix landed only in the shared FE helper would miss this bug's own button.
- **Issue cards:** [ISS-313](../.knowledge/cards/20260828-1946-ISS-313.md) (root — deepened with the confirmed compile-time mechanism above), [ISS-434](../.knowledge/cards/20260828-2240-ISS-434.md) (sibling, INFERRED: RunChatLane DeliverableCard)
- **Fix card:** [FIX-380](../.knowledge/cards/20260829-0212-FIX-380.md) — `PreviewPanel.tsx` toolbar Download now serves the workspace archive (`getRunSandboxZip`) when the run declared no deliverable name; the ISS-313 analysis's proposed backend `default_deliverable_name` cannot work (no such file on disk to name) and is NOT what landed; [ISS-434](../.knowledge/cards/20260828-2240-ISS-434.md) is not cured by it and stays open
- **Found at:** 2026-08-28 08:50 UTC
- **Found by:** bug-runs-id-stream-r2
- **Fingerprint:** `/runs/{id}/stream|download-deliverable-toolbar-button|complete-a-live-run-whose-deliverable_filename-is-null|download-button-permanently-disabled-despite-fully-rendered-deliverable`
- **Evidence:** `bug-hunter/evidence/runs-id-stream/BUG-20260828-085047-runs-id-stream/`

### Summary
Launched a genuinely live run (the "Playwright Smoke Test" workflow, ~3s/1-agent pipeline —
first live pipeline execution this hunt has been able to exercise now that Bedrock credentials
work) and watched it run to completion in `/runs/{id}/stream`. The run reaches `status:
"completed"`, the Preview tab renders the deliverable at "100%" with a working file explorer
(`index.html`, viewable, "Download ZIP" button in the file panel works), yet the toolbar's
top-level "Download the deliverable" button (`aria-label="Download the deliverable"`) is
`[disabled]` and stays disabled indefinitely — confirmed still disabled after 10s+ of polling
and after a full page reload. `GET /api/runs/{id}` shows why: `deliverable_mimetype:
"application/zip"` is set, but `deliverable_filename: null` — the backend marks the run
complete and typed the deliverable's mimetype, but never wrote the filename the frontend's
top toolbar button apparently gates on. For contrast, the seeded completed run
(`b9feac1c-ec21-4531-8ba7-bb391786993e`) has both `deliverable_mimetype: "text/html"` AND
`deliverable_filename: "presentation.html"` populated, and its toolbar Download button is
enabled (`cursor=pointer`, not disabled). This is a different mechanism from the already-filed
`BUG-20260828-014937-runs-id-stream` (a diverted run with NO deliverable at all — `output` and
`deliverable_filename` both null, no rendered content, wrong Preview placeholder copy): here the
deliverable genuinely exists, is fully rendered, and is downloadable through a different UI path
(the file panel's "Download ZIP"), yet the primary/expected Download affordance is silently
broken for this run.

### Reproduction
1. Sign in as qa-admin. From `/dashboard`, launch "Playwright Smoke Test" (~1 agent · ~3s) with
   brief "Smoke test run for bug hunt round 2". Run id:
   `649e56cf-ce0f-4a0f-91fa-4e75a971a980`.
2. Watch `/runs/649e56cf-ce0f-4a0f-91fa-4e75a971a980/stream` progress from "Running · 0/1" to
   "Done" (~21s wall clock, single agent). Preview tab auto-shows the deliverable at "100%",
   file explorer lists `index.html` (2 lines) with working Copy/Download-ZIP controls.
3. Observe the toolbar: "Version v1" / "Share" / "Download the deliverable" — the Download
   button carries `[disabled]` in the accessibility tree despite the run being fully complete
   with a rendered, viewable deliverable.
4. Waited 5-10s and re-checked — still disabled (rules out a brief post-completion race).
5. Reloaded the page fresh (`page.goto` to the same URL) — Download button still `[disabled]`.
6. Confirmed via `GET /api/runs/649e56cf-ce0f-4a0f-91fa-4e75a971a980`: `status: "completed"`,
   `deliverable_mimetype: "application/zip"`, `deliverable_filename: null`.
7. For contrast, loaded `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/stream` (seeded completed
   run): toolbar Download button is enabled (`cursor=pointer`, no `disabled` attribute). Its API
   response has `deliverable_filename: "presentation.html"` populated.

### Expected
A completed run with a fully rendered, viewable deliverable should offer a working top-level
Download button, matching the deliverable that is demonstrably downloadable via the file panel's
"Download ZIP".

### Actual
The toolbar's primary "Download the deliverable" button is permanently disabled whenever the
backend completes a run without populating `deliverable_filename`, even though
`deliverable_mimetype` is set and the deliverable content is fully present and independently
downloadable through the file explorer's "Download ZIP" control — an inconsistent, silently
broken primary affordance with no error shown to the user.

### Evidence
- Live run in progress: `bug-hunter/evidence/runs-id-stream/BUG-20260828-085047-runs-id-stream/01-live-run-in-progress.png`
- Completed, deliverable rendered, Download disabled: `bug-hunter/evidence/runs-id-stream/BUG-20260828-085047-runs-id-stream/02-live-run-completed-download-disabled.png`
- Still disabled after reload: `bug-hunter/evidence/runs-id-stream/BUG-20260828-085047-runs-id-stream/03-reload-still-disabled.png`
- Seeded completed run for contrast, Download enabled: `bug-hunter/evidence/runs-id-stream/BUG-20260828-085047-runs-id-stream/04-comparison-seeded-run-download-enabled.png`

### Browser Signals
- Console: none observed.
- Network: `GET /api/runs/649e56cf-ce0f-4a0f-91fa-4e75a971a980` → 200, `deliverable_filename:
  null`, `deliverable_mimetype: "application/zip"`, `status: "completed"`.
- State: reproduced twice (initial completion, and again after a full page reload).

## BUG-20260828-085400-runs-failed — Steps panel keeps showing "Run failed" while a reopened run is genuinely running

- **Page:** Failed run detail / Live run stream
- **Route:** `/runs/d6e425b6-df0d-4f54-9bba-f4a771e33812/stream`
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** `StepsOverviewSpine.staleErrorLabel.test.tsx` XPASSed ("Expect test to
  fail"), `it.fails` marker removed, re-run plain green (1/1). Manual repro via
  lane4 Chrome, qa-admin, same fixture `d6e425b6…`: clicked "Run Again" then
  "Reopen & fix from the failed step" twice on the seeded run, polling the DOM
  every 400ms alongside `GET /api/runs/{id}` — the Steps panel never once showed
  "Run failed" while `pipelineState.isRunning` was true, including a window where
  the backend had already flipped to `status: "failed"` but the SSE terminal
  event hadn't arrived yet (UI correctly still read "Running"/"Pipeline running ·
  1/4 · BUILDING", not stale "Run failed"). Screenshot with header "Running" +
  Steps panel "Pipeline running · 1/4" side by side confirms the exact scenario
  from the original repro is fixed:
  `bug-hunter/evidence/runs-failed/BUG-20260828-085400-runs-failed/06-after-fix-no-stale-run-failed.png`.
  `tsc --noEmit`: zero diagnostics naming `useWorkflow.ts`/`StepsOverviewSpine.tsx`
  (pre-existing failures in 3 unrelated test files, not caused by this fix).
  `useWorkflow.reconnect.test.ts`: 6/6 green (regression file for the touched
  reducer branch). No new browser console errors (0 errors/warnings). Backend
  serves (`:8000/docs` → 200); `lint-imports` from `backend/` shows the same
  pre-existing `kernel imports only capability ports (scaffold)` break present
  before this change (frontend-only fix, no Python file touched). Run stopped
  via the Stop control afterward, fixture left in a terminal state, not altered
  or deleted.
- **Fixed:** `useWorkflow.ts:458` pipeline_start same-run merge now resets a carried
  `status: "error"` to the fresh-roster rule (`idx < resumeOffset ? "done" : "idle"`,
  `error: null`) instead of spreading it forward, and `StepsOverviewSpine.tsx:342` gates
  `failed` on `!isRunning`. Card [FIX-379](../.knowledge/cards/20260829-0210-FIX-379.md);
  `StepsOverviewSpine.staleErrorLabel.test.tsx` XPASSes (vitest `it.fails` → "Expect test
  to fail"), marker left for 6-verifier. Siblings ISS-438/439/440 are cured by the same
  reducer change but stay open — manual-only verification, not re-driven in the browser.
- **Validated:** 3/3 on 2026-08-28, cold starts — the fixture's terminal state had drifted
  from `failed` to `cancelled` under concurrent bug-hunt traffic, but the same defect
  reproduced identically via "Run Again" (same `handleResumeRun` path); root cause is
  `StepsOverviewSpine.tsx:365-367` deriving `failed` from stale per-agent `error` status
  left over from before the resume, not from `pipelineState.isRunning`.
- **Root cause:** CONFIRMED one level deeper than the validator's citation — the stale
  per-agent `status: "error"` StepsOverviewSpine reads is produced by
  `useWorkflow.ts`'s `pipeline_start` reducer case (`frontend/src/hooks/useWorkflow.ts:446-458`):
  on a same-run resume (`isSameRunReannounce`), each agent is merged as
  `{ ...existing, ...identity }` — carrying `status`/`error` forward from the pre-resume
  attempt unconditionally. The only thing that later clears it is that specific agent's own
  next `agent_start` event (`useWorkflow.ts:573-594`), which can be tens of seconds into the
  resume if earlier agents run first — matching the ~20s window observed. `StepsOverviewSpine.tsx:341-342,367`
  (current lines; code identical to the validator's 365-367 citation, just shifted by an
  unrelated intervening edit) is where this reported symptom renders, but is one of several
  readers of the same polluted array, not the source.
- **Blast radius:** grepped every reader of `status === "error"` off `pipelineState.agents`
  (`frontend/src`, excludes tests): `StepsOverviewSpine.tsx` itself has 4 separate read sites
  (`:342` failed, `:372` phase-gate, `:429` progress-bar segment, `:487` per-row style) — so
  even a fix scoped to the summary label alone (gate `failed` on `!isRunning`) leaves the
  progress-bar segment and that agent's own row red until its own `agent_start` fires.
  Two more independent consumers of the identical array, confirmed by reading each call
  site: `RunChatLane.tsx:579` (`PipelineMini`'s live "Pipeline · N agents" pip,
  `RunChatLane.tsx:1906,2062-2069`) and `AgentDetailPanel.tsx:947` (`isError`, reached via
  `StepsOverviewSpine`'s `onOpenAgent` → `AgentThinkingTab.tsx:274-311`). Checked and RULED
  OUT: `DashboardLayout.tsx:845`'s completion-effect reads the same pattern but is correctly
  gated behind `!pipelineState.isRunning` (`:837`), so it does not misfire during a live
  resume. Not chased (structurally separate route, not confirmed to share this state):
  `AgentNode.tsx`/`PipelineGraph.tsx`/`WorkflowView.tsx` under the standalone `/workflow` page.
- **Fix:** belongs in the shared reducer — `useWorkflow.ts`'s `pipeline_start` merge
  (`:457-458`) — not in each consumer. When `existing.status === "error"`, that field is
  stale evidence superseded by the resume itself (the same treatment the top-level
  `cancelled`/`failed`/`degraded` markers already get at `:505-507`) and should reset the
  same way the non-carried branch already does for a fresh roster entry (`:462`,
  `status: idx < resumeOffset ? "done" : "idle"`, `error: null`) instead of being spread
  verbatim. One guard there fixes the reported label, the progress-bar/per-row siblings in
  the same file, and both other-component siblings at once.
- **Issue cards:** [ISS-317](../.knowledge/cards/20260828-1755-ISS-317.md) (root),
  [ISS-438](../.knowledge/cards/20260829-0056-ISS-438.md) (sibling: RunChatLane's
  PipelineMini pip), [ISS-439](../.knowledge/cards/20260829-0057-ISS-439.md) (sibling:
  AgentDetailPanel's isError badge), [ISS-440](../.knowledge/cards/20260829-0058-ISS-440.md)
  (sibling: "Run again" on a DEGRADED run hits the identical carry-over)
- **Found at:** 2026-08-28 08:54 UTC
- **Found by:** bug-runs-failed-r2
- **Fingerprint:** `/runs/{id}/stream|steps-panel-status-badge|reopen-and-fix-from-failed-step|stale-run-failed-label-persists-during-live-progress`
- **Evidence:** `bug-hunter/evidence/runs-failed/BUG-20260828-085400-runs-failed/`

### Summary
Clicking "Reopen & fix from the failed step" on the seeded failed run `d6e425b6…` genuinely
resumes the run (confirmed via `GET /api/runs/{id}` — status flips to `generating` and
`agent_outputs` regenerate; this is a real live run, not a no-op). The page correctly reflects
this in the header ("Running") and in the chat/pipeline widget (agents move through
Thinking → Writing states, elapsed time and token counts climb). However the Steps tab's
status summary panel keeps displaying the stale terminal label **"Run failed"** the entire
time the run is actively progressing (1/4 → agents streaming, tokens accumulating), directly
contradicting the "Running" badge and the "Deck Engineer Agent · streaming" sub-header shown
a few pixels away on the same screen.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/runs/d6e425b6-df0d-4f54-9bba-f4a771e33812`.
2. Confirm run count via `GET http://localhost:8000/api/runs?limit=50` (baseline, run status `failed`).
3. Click "Reopen & fix from the failed step" in the Resume options panel.
4. Page navigates to `/runs/{id}/stream`. Confirm via `GET /api/runs/{id}` that `status` is now
   `generating` (a genuine resume, not a no-op).
5. Observe the header badge reads "Running", the sub-header under the run title cycles through
   "Running · streaming" → "Deck Engineer Agent · streaming", and the pipeline chips in the
   chat transcript show agents moving to "Thinking…" then "Writing…" with rising token counts.
6. In the Steps tab (right panel), observe the status summary line directly above the agent list
   still reads **"Run failed"** with a stale `1 / 4 agents · 3s` count that never updates as the
   run genuinely progresses to agent 2 and beyond.
7. Reproduced continuously across ~20s of live progress (0/4 → 1/4 agents, Presentation
   Strategist Agent completing at 51s/18.4K tokens, Deck Engineer Agent starting) — the "Run
   failed" label never once updated to "Running" or cleared, even as every other live indicator
   on the same page updated correctly.

### Expected
While a run is actively `generating`/running, the Steps panel's status summary should show a
state consistent with "Running" (matching the header badge and sub-header), not the terminal
"Run failed" label left over from before the reopen.

### Actual
The Steps panel's status summary is frozen at "Run failed" for the entire observed live-run
duration, directly contradicting the "Running" badge and the actively-streaming agent
sub-header rendered simultaneously on the same page.

### Evidence
- Before (failed run, Resume options visible): `bug-hunter/evidence/runs-failed/BUG-20260828-085400-runs-failed/01-before-reopen.png`
- Just after reopen (header "Running" vs Steps panel "Run failed"): `bug-hunter/evidence/runs-failed/BUG-20260828-085400-runs-failed/02-reopened-running-vs-failed-badge.png`
- Mid-progress (agent 2 "Writing…", tokens climbing, panel still "Run failed"): `bug-hunter/evidence/runs-failed/BUG-20260828-085400-runs-failed/03-stale-run-failed-label-during-progress.png`
- Persisted (same stale label ~15s later): `bug-hunter/evidence/runs-failed/BUG-20260828-085400-runs-failed/04-stale-run-failed-label-persists.png`

### Browser Signals
- Console: none observed
- Network: `GET /api/runs/{id}` confirmed `status: "generating"` while the UI showed the
  contradictory "Run failed" label — not a stale API response, the frontend simply doesn't
  re-derive this one label from live stream state.
- State/URL: URL settles at `/runs/{id}/stream`; run stopped via the "Stop" control at the end
  of the investigation to avoid abandoning a live run (the seeded fixture `d6e425b6…` itself
  was not deleted or altered).

## BUG-20260828-085830-runs-cancelled — A run whose "Run Again" pipeline actually failed keeps reporting `status: "cancelled"` everywhere, permanently misrepresenting its real outcome

- **Page:** Cancelled run detail / Run History list
- **Route:** /runs/{id}, /runs
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `backend/tests/agents/test_restart_resume.py` ran XPASS(strict)
  on `test_reconcile_later_attempt_failure_supersedes_earlier_cancellation`, confirming the
  fix; `xfail` marker removed (`@pytest.mark.issue("ISS-316")` kept), re-run gave a plain
  green (69 passed). Manual repro re-run by hand (lane5, qa-admin, same run
  `a8dfa959-e233-4ddf-87ce-d9a942cefde3`): detail-page badge now reads "Failed" (matching the
  page's own "Failed agents" list, no longer self-contradictory), `GET /api/runs/{id}` returns
  `status: "failed"`, and the `/runs` history list card for the same run now tags "failed"
  instead of "cancelled". No new console errors (only the pre-existing unrelated iframe-sandbox
  warning). `backend/docs` returns 200 (uvicorn `--reload` already picked up the .py change, no
  restart needed). `lint-imports` from `backend/`: 3 kept / 1 broken, same pre-existing
  violations named in FIX-381 (kernel_services -> app.api.user_workflows,
  revision_analyzer -> app.api.run_commands), unchanged by this diff. `frontend` tsc --noEmit
  shows pre-existing unrelated test-file type errors only; this fix touched no frontend files
  (`git diff --stat` confirms only `backend/app/api/run_commands.py` changed). After-screenshot:
  `bug-hunter/evidence/runs-cancelled/BUG-20260828-085830-runs-cancelled/03-after-detail-badge-failed.png`.
- **Fixed:** `_reconcile_terminal_status`'s `resume_supersedes`
  (`backend/app/api/run_commands.py:811-825`) now maxes over completions AND
  `pipeline_failed` seqs (`terminal_seqs`), so a later attempt that genuinely fails
  supersedes the earlier `pipeline_cancelled` exactly as a later clean completion
  already did; FIX-229's attempt-boundary guard is unchanged, so a same-attempt
  failure still loses to the rejection. One shared-function change cures both callers
  (`_drive_user_resume:740` and `stop_run_driver`). Card
  [FIX-381](../.knowledge/cards/20260829-0220-FIX-381.md);
  `backend/tests/agents/test_restart_resume.py` → 68 passed + XPASS(strict) on
  `test_reconcile_later_attempt_failure_supersedes_earlier_cancellation`, marker left
  in place for 6-verifier. Siblings ISS-435/436/437 are NOT cured and stay open —
  ISS-435 needs a decision on the deliberate degraded exclusion in `complete_seqs`.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduces identically on every cold load,
  no narrowing needed. Root cause: `_reconcile_terminal_status`'s `resume_supersedes` check
  (`backend/app/api/run_commands.py:811-818`) only recognizes a resumed run's
  `pipeline_complete` as superseding the earlier `pipeline_cancelled`; a resumed run that
  instead emits `pipeline_failed` (no `pipeline_complete` in its tail) never supersedes it,
  so `status` stays `"cancelled"` forever.
- **Root cause:** `_reconcile_terminal_status` (`backend/app/api/run_commands.py:748-838`) is
  the SOLE place a resumed run's terminal `WorkflowRun.status` gets persisted, called from both
  `_drive_user_resume` (:740, the "Run Again" path) and `stop_run_driver`
  (`backend/app/api/run_shutdown.py:330-332`, the `POST /cancel` escalation path). Its
  `resume_supersedes` flag (:811-818) is gated on `complete_seqs`, which only contains
  NON-degraded `pipeline_complete` events (:806-808 explicitly excludes
  `status=="degraded"`). When the resumed attempt's own terminal event is anything other than a
  clean `pipeline_complete` — a `pipeline_failed` (the reported case) or a degraded
  `pipeline_complete` — `complete_seqs` stays empty, `resume_supersedes` short-circuits `False`,
  and the first branch `if cancelled and not resume_supersedes: new_status = "cancelled"`
  unconditionally re-persists `"cancelled"`. The `degraded` and `failed` flags feeding the rest
  of the ladder (:781-782) are ALSO computed with zero attempt-boundary awareness (a bare
  `any()` over the run's ENTIRE multi-attempt tail), so the same "old terminal state wins over
  the real latest outcome" shape recurs for three more state combinations — see the sibling
  cards below.
- **Blast radius:** Both callers of `_reconcile_terminal_status`
  (`_drive_user_resume:740` and `stop_run_driver`, `run_shutdown.py:330-332`) inherit the bug
  identically, since the defect lives inside the shared function, not either caller. Every
  frontend surface that trusts the persisted `status` field then displays the wrong outcome —
  confirmed consumers: `RunDetailPage.tsx:237/240` (badge), `WorkflowHistory.tsx:599` (history
  list), `PreviewPanel.tsx:706/714` (reopen affordance), `RevisionFamilyView.tsx:142/342`
  (revision lineage), `NotificationPanel.tsx:60` + `useNotifications.ts` (toasts), `Badge.tsx`,
  `AgentDetailPanel.tsx:630`, `DashboardLayout.tsx` (running-pipeline badge poll) — none of these
  are independently broken; they render correctly once the backend field is correct, so the fix
  belongs solely in `_reconcile_terminal_status`.
- **Issue cards:** [ISS-316](../.knowledge/cards/20260828-1952-ISS-316.md) (root — the reported
  cancelled→failed gap), [ISS-435](../.knowledge/cards/20260828-2253-ISS-435.md) (sibling:
  cancelled→degraded resume also stuck "cancelled" — same `complete_seqs` degraded-exclusion),
  [ISS-436](../.knowledge/cards/20260828-2253-ISS-436.md) (sibling: the unscoped `degraded` flag
  masks a later clean-complete OR failed outcome after an earlier degraded attempt),
  [ISS-437](../.knowledge/cards/20260828-2253-ISS-437.md) (sibling, the INVERSE case: the
  unscoped `failed` flag permanently reports "failed" on a run that was resumed after an
  earlier failure and then genuinely succeeded — a real deliverable hidden behind a false
  failure badge)
- **Found at:** 2026-08-28 08:58 UTC
- **Found by:** bug-runs-cancelled-r2
- **Fingerprint:** `/runs/{id}|run-status-field|run-again-on-a-cancelled-run-that-then-fails|status-permanently-reports-cancelled-instead-of-failed`
- **Evidence:** `bug-hunter/evidence/runs-cancelled/BUG-20260828-085830-runs-cancelled/`

### Summary
Run `a8dfa959-e233-4ddf-87ce-d9a942cefde3` was seeded `cancelled`. A prior worker used "Run
Again" on it; the backend's re-run pipeline genuinely failed (`GET /api/runs/{id}/events` shows
two `agent_error` events followed by `pipeline_failed` at seq 29 and a `chat_reply` "What went
wrong" at seq 30 — all 4 agents ended in `agents_failed`). This is a durable, persisted state
change, not a transient rendering glitch: `GET /api/runs/{id}` still returns `"status":
"cancelled"`, `"error": null` on every fresh fetch since, the run detail page's own badge still
reads "Cancelled" / "Cancelled by you" on a full reload, and the `/runs` history list still
tags the same run "cancelled". Yet the same detail page's body — derived from the event stream
rather than the `status` field — simultaneously renders "Failed agents: Presentation Strategist
Agent, PPTX Code Generator, Deck Engineer Agent, Deck QA Agent" directly under a "This run was
cancelled" heading. The run's canonical status field never gets corrected to `failed`, so the
badge, the history list, and the API all permanently misreport a failed pipeline run as a
user-cancelled one, while the body of the very same page contradicts that badge by listing
failed agents. This is a different, independently-actionable defect from the already-filed
`BUG-20260828-015930-runs-cancelled` (the live `/stream` view freezing mid-render before any
reload) — that bug is about the live page failing to *render* an update; this one is about the
run's persisted `status` field itself being permanently wrong, confirmed via direct API calls
with no live view or stream involved at all, and visible on an entirely different page (the
`/runs` history list).

### Reproduction
1. Sign in as qa-admin. Load `http://localhost:3000/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3`
   (a fresh page load, no live view).
2. Observe the header badge reads "Cancelled" / "Cancelled by you", and the resume-panel-turned
   result panel shows "This run was cancelled — The run was stopped before producing a
   deliverable." directly above a "Failed agents" list naming all 4 agents.
3. Independently call `GET /api/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3` — response has
   `"status": "cancelled"`, `"error": null`, with no field indicating the pipeline actually
   failed.
4. Independently call `GET /api/runs/a8dfa959-e233-4ddf-87ce-d9a942cefde3/events` — tail of the
   stream shows `agent_error` ×2, `pipeline_failed` (seq 29), `chat_reply` "What went wrong"
   (seq 30), confirming the pipeline genuinely failed rather than being cancelled.
5. Load `http://localhost:3000/runs` (Run History list) — the same run's card is still tagged
   "cancelled", matching the wrong API status, not the true failed outcome.

### Expected
Once a run's pipeline fails (`pipeline_failed` emitted, all agents in `agents_failed`), the
run's own persisted `status` should update to `failed` (or an equivalent terminal state that
reflects the real outcome), and every surface reading that field — the detail page badge, the
Run History list, and the API — should agree with each other and with the failed-agents content
already rendered on the same page.

### Actual
The run's `status` field is permanently stuck at `cancelled` after a re-run pipeline failure.
The detail page badge, the Run History list card, and the raw API response all report
"cancelled" indefinitely, while the same detail page's own body simultaneously lists "Failed
agents" — a self-contradictory page, and a run-outcome record that is durably wrong across every
surface that reads it.

### Evidence
- Detail page (badge "Cancelled" + "Failed agents" list, same view):
  `bug-hunter/evidence/runs-cancelled/BUG-20260828-085830-runs-cancelled/01-detail-badge-cancelled-but-failed-agents-listed.png`
- Run History list (same run still tagged "cancelled"):
  `bug-hunter/evidence/runs-cancelled/BUG-20260828-085830-runs-cancelled/02-runs-list-still-shows-cancelled.png`
- Raw API response (`status: "cancelled"`, `error: null`):
  `bug-hunter/evidence/runs-cancelled/BUG-20260828-085830-runs-cancelled/api-run-status.json`
- Network excerpt: `bug-hunter/evidence/runs-cancelled/BUG-20260828-085830-runs-cancelled/network.log`

### Browser Signals
- Console: no relevant error observed.
- Network: `GET /api/runs/{id}` → `status: "cancelled"`, `error: null`; `GET
  /api/runs/{id}/events` tail → `agent_error` ×2, `pipeline_failed`, `chat_reply`.
- State/URL: reproduced on a fresh page load of `/runs/{id}` (no live `/stream` view involved)
  and independently on `/runs`; not a rendering/polling artifact.

## BUG-20260828-090219-runs-diverted — Diverted run's Workspace tab falsely claims "the deliverable is still on the Preview and Files tabs" when no deliverable was ever produced

- **Page:** Diverted run detail
- **Route:** /runs/{id}/workspace (diverted run)
- **Severity:** Low
- **Status:** CLOSED
- **Verified:** `suites/07_run_detail/test_iss356_workspace_expired_false_deliverable_claim.py`
  XPASS(strict) on first run (pass signal), `xfail` marker removed, re-run plain green
  (1/1). Frontend unit tests: `SandboxTab.test.tsx` 37/37 green, `PreviewPanel.degraded.test.tsx`
  11/11 green. Manual repro re-driven by hand on both original runs
  (`940ca699-b21b-4666-8e44-3370a08a4561` and `277bc03a-d2ba-4405-876d-d0aa861bc9ed`) at
  `/runs/{id}/workspace`: the "Workspace expired" body now reads only "Run workspaces are
  cleared after a retention period." with no deliverable claim, on both diverted runs, no
  console errors. Screenshot:
  `bug-hunter/evidence/runs-diverted/BUG-20260828-090219-runs-diverted/04-after-fix404-workspace-tab-no-false-claim.png`.
  Health: backend `:8000/docs` 200 (no backend file touched, pure frontend TSX change, no
  restart needed); `tsc --noEmit` shows only pre-existing errors in files this fix never
  touched (`login.a11y.test.tsx`, `HomeLaunchGrid.crossAccountLeak.test.tsx`,
  `api.sessionExpiryRedirect.test.ts`, `listenerMiddleware.test.ts`); `lint-imports` from
  `backend/` shows the same pre-existing `kernel imports only capability ports` break
  (unrelated). Regression: `suites/07_run_detail/test_run_detail.py` 36 passed / 0 failed / 12
  skipped (all skips carry stated fixture-missing reasons, none silent).
- **Validated:** 3/3 on 2026-08-28, every cycle from a cold start — direct navigation to
  `/runs/{id}/workspace` on a diverted run, no timing/entry-path variation needed; message is
  static text unconditioned on deliverable existence
- **Root cause:** `frontend/src/components/results/SandboxTab.tsx:1037-1043` — the `expired`
  branch hardcodes "The deliverable is still on the Preview and Files tabs" with no check on
  `output`/`deliverable_filename`/run status. Deeper: `SandboxTabProps` (`:842-849`) is never
  GIVEN any such signal — `PreviewPanel.tsx:1406` is the sole render call site and passes only
  `runId`/`agentNameById`, though PreviewPanel already computes `hasContent`, `isDivertedTerminal`,
  `terminalFailureNoDeliverable`, `isCancelledTerminal` (`:690-738`) for the identical
  [FIX-357](../.knowledge/cards/20260828-2210-FIX-357.md) "diverted omitted from a terminal check"
  pattern — just never threads them into SandboxTab.
- **Blast radius:** exactly one production caller (`PreviewPanel.tsx:1406`, grepped project-wide —
  no others). The risk is by STATE, not by caller: `list_sandbox`'s `expired` flag
  (`backend/app/api/run_files.py:534`, `expired = not sandbox.root.is_dir()`) is status-agnostic,
  so any terminal run with no deliverable (failed/cancelled/degraded — not only diverted) hits the
  identical false claim once its workspace passes `RUN_DIR_TTL_HOURS` (`backend/app/core/config.py:308-311`).
- **Fix belongs:** two hops mirroring FIX-357's own shape — add a status/deliverable prop to
  `SandboxTabProps` and branch the `expired` copy on it, then thread PreviewPanel's already-computed
  `hasContent`/`isDivertedTerminal`/`terminalFailureNoDeliverable`/`isCancelledTerminal` into
  `<SandboxTab>` at `:1406` as that prop — no new computation needed, only wiring.
- **Issue cards:** [ISS-356](../.knowledge/cards/20260828-1910-ISS-356.md) (root),
  [ISS-586](../.knowledge/cards/20260829-0258-ISS-586.md) (sibling, INFERRED: generalizes beyond
  diverted to any terminal no-deliverable status),
  [FIX-404](../.knowledge/cards/20260829-0418-FIX-404.md) (fix)
- **Found at:** 2026-08-28T09:02:19Z
- **Found by:** bug-runs-diverted-r2
- **Fingerprint:** `/runs/{id}/workspace|workspace-expired-empty-state|open-workspace-tab-on-a-diverted-run|message-falsely-claims-deliverable-exists-on-preview-and-files`
- **Evidence:** `bug-hunter/evidence/runs-diverted/BUG-20260828-090219-runs-diverted/`

### Summary
A diverted run never produces a deliverable — confirmed via the backend API on all four
diverted runs checked (`940ca699…`, `277bc03a…`, `4dec89fb…`, `b15f23d0…`): `output: null`,
`deliverable_filename: null` in every case, the Preview tab shows the empty "Output will appear
here" placeholder, the Files tab lists only agent-intermediate outputs and the run input (no
deliverable file), and the toolbar's "Download the deliverable" button is correctly disabled.
Despite this, the Workspace tab's "Workspace expired" empty state unconditionally states "The
deliverable is still on the Preview and Files tabs — only the raw working files are gone,"
which is factually false for a diverted run: there never was a deliverable on either tab. The
copy appears to be a generic completed-run message reused without a status check for the
diverted case.

### Reproduction
1. Sign in as qa-admin, navigate to a diverted run, e.g.
   `http://localhost:3000/runs/940ca699-b21b-4666-8e44-3370a08a4561`. Header badge reads
   "Diverted".
2. Confirm via `GET /api/runs/940ca699-b21b-4666-8e44-3370a08a4561`: `"output": null`,
   `"deliverable_filename": null`.
3. Click the Preview tab (default) — shows "Output will appear here" (no deliverable rendered).
4. Click the Files tab — lists 3 files: 2 agent-output intermediates + run input `prompt.md`;
   no deliverable file present. Toolbar "Download the deliverable" button is `[disabled]`.
5. Click the Workspace tab — shows "Workspace expired" with body text: "Run workspaces are
   cleared after a retention period. The deliverable is still on the Preview and Files tabs —
   only the raw working files are gone."
6. Reproduced identically on a second, independent diverted run,
   `http://localhost:3000/runs/277bc03a-d2ba-4405-876d-d0aa861bc9ed/workspace` — same message,
   same confirmed-null deliverable state via API.

### Expected
The Workspace-expired message should not assert a deliverable exists on Preview/Files when the
run's own data shows none was ever produced — either the message should be conditioned on
whether a deliverable exists, or a diverted run should get copy explaining the handoff (e.g.
pointing at the successor run) instead of the generic completed-run wording.

### Actual
The message unconditionally claims the deliverable is available elsewhere on the run, actively
misleading a user who has not yet checked Preview/Files into believing output exists that was
never generated.

### Evidence
- Workspace tab false claim (run 940ca699…): `bug-hunter/evidence/runs-diverted/BUG-20260828-090219-runs-diverted/01-workspace-tab-false-claim.png`
- Reproduced on second diverted run (277bc03a…): `bug-hunter/evidence/runs-diverted/BUG-20260828-090219-runs-diverted/02-repro-second-diverted-run.png`
- Files tab confirming no deliverable file exists: `bug-hunter/evidence/runs-diverted/BUG-20260828-090219-runs-diverted/03-files-tab-no-deliverable-present.png`

### Browser Signals
- Console: none observed related to this defect.
- Network: `GET /api/runs/940ca699-b21b-4666-8e44-3370a08a4561` and
  `GET /api/runs/277bc03a-d2ba-4405-876d-d0aa861bc9ed` both return `output: null`,
  `deliverable_filename: null`.
- State/URL: reproduced on `/runs/940ca699-b21b-4666-8e44-3370a08a4561/workspace` and
  `/runs/277bc03a-d2ba-4405-876d-d0aa861bc9ed/workspace`.

## BUG-20260828-090732-runs-id-versions — Switching tabs while pinned to a non-root version silently drops the pin: URL, API calls, and displayed data all revert to v1

- **Page:** Run detail pinned to an artifact version
- **Route:** /runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/versions/2 (root run has a genuine
  2-member revision family: root = v1, revision `ef86e750-bbcd-404f-855a-fb0d5bee63f5` = v2)
- **Severity:** High
- **Status:** CLOSED
- **Verified (2026-08-28):** `suites/21_run_families_and_versions/test_iss_230_version_pin_survives_tab_switch.py`
  5/5 green — the two ISS-296/ISS-300 tests XPASS(strict) on first run (pass signal), `xfail`
  markers removed, re-run plain green 5/5. Manual repro re-driven by hand at
  `/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/versions/2`: clicking Files kept the URL at
  `/versions/2/files`, fetched only `ef86e750-...` (v2) for run+sandbox (no root-run fetch),
  and "Final output" now reads 83.5 KB — v2's own size, not v1's 241.6 KB. Also manually
  re-drove ISS-296: picking "Version v1" from the Version menu now pushes the URL to
  `/runs/77f74563-.../versions/1`. Screenshot:
  `bug-hunter/evidence/runs-id-versions/BUG-20260828-090732-runs-id-versions/05-after-fix334-files-tab-shows-v2-size.png`.
  Health: backend `:8000/docs` 200; `lint-imports` from `backend/` shows the same
  pre-existing `kernel imports only capability ports` break (unrelated — this fix touches only
  frontend TSX, no backend file); `tsc --noEmit` shows only the same 2 pre-existing errors in
  files this fix never touched (`HomeLaunchGrid.crossAccountLeak.test.tsx`,
  `listenerMiddleware.test.ts`). Regression: `suites/07_run_detail/test_run_detail.py` 35
  passed / 0 failed (12 skipped, 1 deselected) — matches FIX-334's recorded baseline exactly.
- **Fix (second pass, 2026-08-28):** [FIX-334](../.knowledge/cards/20260828-2149-FIX-334.md)
  closes the two halves FIX-328 left open — ISS-300 (`<FilesTab>` at
  `frontend/src/components/preview/PreviewPanel.tsx:1319` now gets the version-aware
  `eff*` content props, so "Final output" reports the pinned member's own deliverable)
  and ISS-296 (`handleSelectVersion`/`handleBackToLatest` write the pin through
  `DashboardLayout.handlePreviewPanelTabSelect`, which took an optional version
  argument). Two new tests in the existing suite file both XPASS(strict) and both
  XFAIL with only the app edits reverted; `suites/07_run_detail/test_run_detail.py`
  re-ran at its recorded baseline, 35 passed / 12 skipped.
- **Verifier note (2026-08-28):** FIX-328 correctly fixes the URL/network/picker half of this
  bug (ISS-230, ISS-294) — confirmed both by test and by hand: cold-loading
  `/runs/{rootId}/versions/2` now shows "Version v2" immediately, clicking Files/Steps keeps the
  URL at `/versions/2/<tab>`, and every network request after the click targets the pinned
  revision id `ef86e750-...`, never the root. But this bug's OWN reproduction (step 5) also
  requires the Files tab's displayed "Final output" size to match v2 (~83.5 KB / 85,529 chars),
  and it does not: manually re-driving the exact repro at `/runs/{rootId}/versions/2/files` after
  the fix still shows "241.6 KB" — v1's size (v1's `.output` is 247,400 chars ≈ 241.6 KB, v2's is
  85,529 chars ≈ 83.5 KB, confirmed via direct API fetch in-browser). This is exactly ISS-300
  (FilesTab reads raw `userStoryContent`/`pptContent`/`prototypeContent` instead of the
  version-aware `eff*` props PreviewPanel already computes) — ISS-300 and its write-side sibling
  ISS-296 remain `status: open`/`verification: pending`, untouched by FIX-328 by its own
  admission ("Depends on: ISS-230, ISS-294" only). Test green (XPASS→green, 3/3,
  `test_iss_230_version_pin_survives_tab_switch.py`) but the bug's own manual repro still fails
  on the displayed-data axis — REOPENED per verifier rule 6. Evidence:
  `bug-hunter/evidence/runs-id-versions/BUG-20260828-090732-runs-id-versions/04-after-files-tab-still-shows-v1-size.png`.
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — cycle 1 (Files tab), cycle 2 (Steps
  tab), cycle 3 (Workspace tab, generalizing beyond the original Files/Steps scope). Root cause:
  `handlePreviewPanelTabSelect` (`frontend/src/components/layout/DashboardLayout.tsx:471-498`)
  builds every tab's `targetRoute` from `routes.run*(contentSourceRunId)` only — none of the
  route builders ever consult a `/versions/<v>` segment.
- **Root cause (CONFIRMED, re-verified by analyzer):** `handlePreviewPanelTabSelect`
  (`frontend/src/components/layout/DashboardLayout.tsx:471-498`) builds every tab's route from
  `routes.run*(contentSourceRunId)` only, dropping any `/versions/<v>` segment — matches ISS-230
  exactly. Deeper analysis (INFERRED, pending live re-drive) found the pin was likely never
  established in the first place: `reopenedRunIdFor` (`frontend/src/app/[...view]/page.tsx:182-196`)
  discards `parsed.version` on cold mount, so `/runs/{id}/versions/{v}` always resolves to the
  root run regardless of tab clicks (both this bug's own "before" screenshots show "Version v1"
  immediately, contrary to the reproduction narrative); `routes.runVersion` (`routes.ts:80`) has
  zero real call sites, so picking a version via RunHeader's Version menu never writes the URL
  either (`handleSelectVersion`, `PreviewPanel.tsx:549-564`, is pure local state); and FilesTab
  ignores an active version override entirely (`PreviewPanel.tsx:1280` passes raw
  `userStoryContent`/`pptContent`/`prototypeContent` instead of the `eff*` version-aware props it
  already computes at `PreviewPanel.tsx:590-594`).
- **Blast radius:** `routes.runSteps/runFiles/runWorkspace/runAudit` have exactly one caller
  (`handlePreviewPanelTabSelect`) — confirmed via repo-wide grep, so ISS-230's fix belongs there,
  the single chokepoint. `routes.runVersion` has zero application callers (only a unit round-trip
  test). `reopenedRunIdFor`'s `run-version` case is the only cold-mount consumer of `parsed.version`.
  FilesTab is the one PreviewPanel-mounted tab whose content wiring bypasses the `viewingVersion`
  override that Workspace's `workspaceRunId` already respects; Steps/Audit take live
  `pipelineState`/`agents`/`hookRuns` (no separate override axis) so they are fully explained by
  the URL/cold-mount mechanism, not a fourth wiring gap.
- **Issue cards:** [ISS-230](../.knowledge/cards/20260828-1805-ISS-230.md) (root, CONFIRMED),
  [ISS-296](../.knowledge/cards/20260828-1724-ISS-296.md) (sibling, INFERRED: Version menu never
  writes the pin into the URL — inverse case), [ISS-294](../.knowledge/cards/20260828-1725-ISS-294.md)
  (sibling, INFERRED: cold-mount/deep-link direction never applies `parsed.version` either),
  [ISS-300](../.knowledge/cards/20260828-1726-ISS-300.md) (sibling, INFERRED: FilesTab ignores an
  active version pin independent of the URL)
- **Found at:** 2026-08-28T09:07:32Z
- **Found by:** bug-runs-id-versions-r2
- **Fingerprint:** `/runs/[id]/versions/2|version-pin-across-tabs|click-files-or-steps-tab-while-pinned-to-v2|url-and-fetched-data-silently-revert-to-v1-not-just-a-label`
- **Evidence:** `bug-hunter/evidence/runs-id-versions/BUG-20260828-090732-runs-id-versions/`

### Summary
This is a materially worse variant of the already-filed picker-mislabel bug
(`BUG-20260828-020900-runs-id-versions`, which reproduces on `/versions/2` itself and only
mislabels the picker while v2's real content stays correctly rendered). Here, the moment the
user leaves the Preview tab for any other tab (confirmed on Files and Steps) while pinned to
`/versions/2`, the app doesn't just mislabel — it stops asking for v2 at all. The URL silently
drops the `/versions/2` segment back to the bare `/runs/{rootId}` route, and the network layer
re-fetches `GET /api/runs/{rootId}` and `GET /api/runs/{rootId}/sandbox` (the ROOT run = v1),
never touching the pinned revision's own run id (`ef86e750-...`) again. The Files tab then
displays v1's Final output (241.6 KB, matching v1's 247,394-char API output) instead of v2's
(which the API confirms is 85,529 chars, ~83.5 KB) — with the version picker also reverted to
"Version v1" and no indication anywhere that the user asked for v2 and silently got v1's data
on a different tab. This is a genuine content-correctness defect, not a rendering/label glitch:
whichever version happens to be pinned is discarded by ordinary tab navigation.

### Reproduction
1. Sign in as qa-admin, navigate to
   `http://localhost:3000/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/versions/2`. Confirm via
   network log that `GET /api/runs/ef86e750-bbcd-404f-855a-fb0d5bee63f5` (v2) is the run fetched,
   and the Preview tab renders v2 content.
2. Click the Files tab (`[role="tab"]:nth-child(3)`).
3. Observe the URL: it silently becomes `/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/files` — the
   `/versions/2` segment is gone with no user action to remove it.
4. Observe the network log: the app now issues `GET /api/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a`
   and `GET /api/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a/sandbox` — the ROOT run id (v1), not
   the pinned `ef86e750-...` (v2) id.
5. Observe the Files tab's "Final output" row: `241.6 KB` — matches v1's known size, not v2's.
   The version picker in the toolbar also now reads "Version v1".
6. Repeat from `/versions/2` clicking the Steps tab instead of Files: same shape — URL reverts
   to `/runs/{rootId}/steps`, picker reverts to "Version v1".

### Expected
Navigating between tabs while a specific artifact version is pinned should keep that pin: the
URL should stay scoped to `/versions/2/<tab>` (or equivalent), the app should keep fetching the
pinned revision's own run id, and every tab (Files, Steps, Workspace, Audit) should show that
version's real data.

### Actual
Any tab switch away from Preview silently discards the version pin: the URL collapses back to
the unversioned root route, the app re-fetches the ROOT run (v1) instead of the pinned revision,
and the Files tab (and by the same fetch, every other tab) displays v1's file, not v2's — with
no warning, error, or visual cue that the pin was lost.

### Evidence
- Before: `bug-hunter/evidence/runs-id-versions/BUG-20260828-090732-runs-id-versions/01-before-versions-2-preview.png`
- Failure (Files tab, URL and size both reverted to v1): `bug-hunter/evidence/runs-id-versions/BUG-20260828-090732-runs-id-versions/02-failure-files-tab-reverts-to-v1.png`
- Second reproduction (Steps tab shows the identical pattern): `bug-hunter/evidence/runs-id-versions/BUG-20260828-090732-runs-id-versions/03-second-repro-steps-tab-also-drops-version.png`
- Network excerpt confirming which run id is actually fetched: `bug-hunter/evidence/runs-id-versions/BUG-20260828-090732-runs-id-versions/network.log`

### Browser Signals
- Console: no errors, one pre-existing unrelated warning (unchanged across states).
- Network: `GET /api/runs/77f74563-fa19-4f0b-84fd-d0224f89a54a` and
  `.../77f74563-fa19-4f0b-84fd-d0224f89a54a/sandbox` fire after the tab click — the ROOT run id,
  never the pinned revision id `ef86e750-bbcd-404f-855a-fb0d5bee63f5`.
- State/URL: `/runs/{id}/versions/2/...` collapses to `/runs/{id}/...` on any non-Preview tab
  click; a reload at that point stays on v1 (confirms it is genuine state loss, not a transient
  render race).

## BUG-20260828-091300-library-skills-r2 — Skill detail route (`/library/skills/<id>`) now falls back to the Library listing for EVERY skill id, hyphenated or not — a full regression beyond the previously filed no-hyphen-only scope

- **Page:** Library — skill detail
- **Route:** /library/skills/<skillId> (any id — tested hyphenated multi-segment ids, previously confirmed working)
- **Severity:** High
- **Status:** CLOSED
- **Found at:** 2026-08-28 09:13 UTC
- **Found by:** bug-library-skills-r2
- **Fingerprint:** `/library/skills/<id>|skill-detail-route-match|navigate-to-any-skill-id|library-listing-renders-instead-of-detail-for-100pct-of-skills`
- **Evidence:** `bug-hunter/evidence/library-skills/BUG-20260828-091300-library-skills-r2/`
- **Validated:** 3/3 on 2026-08-28 (cycles 1-3, cold start every time) — direct URL nav to two
  hyphenated ids (`html-deck-to-pptx`, `windows-desktop-e2e`) and genuine UI card-click entry all
  reproduce identically; no axis-narrowing needed.
- **Root cause (CONFIRMED mechanism):** Every `/library/{type}/{slug}` navigation (both a card
  `onClick` and a cold URL load) remounts `frontend/src/app/[...view]/page.tsx` and everything
  beneath it — a verified Next.js behavior already documented in this repo
  (`page.tsx:3195-3199`; previously hit and fixed for the run-stream route in `FIX-298`). That
  wipes the Skill card's own direct `setSelectedSkill(skill)` call
  (`LibraryPage.tsx:822-824`), so opening the modal depends ENTIRELY on the cold-mount/URL-seed
  effect (`LibraryPage.tsx:518-543`, "T15"), whose skills branch requires
  `SKILLS.find(s => s.id === librarySlug.slug)` (`LibraryPage.tsx:527-533`) to match.
  **INFERRED (not proven by static reading):** that match fails because
  `frontend/src/hooks/useSkillsCatalog.ts:17-26` returns a brand-new, unmemoized array every
  render, unlike `useAgentLibrary.ts:29-38` (which memoizes and whose own comment warns exactly
  this class of bug: "a consumer effect keyed on libraryAgents would loop forever"). `ISS-303`
  independently confirms the AGENTS branch of this same effect works on a cold URL — the one
  branch backed by a memoized array — which is why this isn't a total-infrastructure failure.
- **Blast radius:** `useSkillsCatalog` is also called by `AgentSkillsPicker.tsx` and
  `AgentsPopup.tsx`; `useHooksCatalog` (identical unmemoized shape) is also called by
  `AgentsPopup.tsx` and `CanvasConfigRail.tsx` — those callers don't share `LibraryPage`'s
  once-only URL-seed-effect pattern, so they are not confirmed broken the same way, but the fix
  belongs in the two hooks (matching `useAgentLibrary`'s memoized pattern) so every caller routes
  through the same fix rather than patching `LibraryPage` alone. Within `LibraryPage.tsx` itself,
  the Hooks tab's detail route (`/library/hooks/<id>`) shares the identical effect + identical
  unmemoized-catalog shape and is the direct sibling — see ISS-336.
- **Issue cards:** [ISS-232](../.knowledge/cards/20260828-1627-ISS-232.md) (root),
  [ISS-336](../.knowledge/cards/20260828-1846-ISS-336.md) (sibling, INFERRED: same defect on
  `/library/hooks/<id>`)

### Summary
`BUG-20260828-030430-library-skills-id` (filed ~03:04 UTC) characterized this as a narrow defect
affecting only the 7 single-word/no-hyphen skill ids, explicitly verifying that hyphenated ids
like `windows-desktop-e2e` and `html-deck-to-pptx` rendered their detail page correctly
("byte-for-byte" content match). Retesting now (09:13 UTC, ~6 hours later) shows that
characterization no longer holds: **every** skill id tested — including `html-deck-to-pptx` and
`windows-desktop-e2e`, the two ids that bug explicitly proved worked — now falls back to the
full Library catalog listing instead of the skill detail page. This reproduces identically via
direct URL navigation, via a fresh page reload at the same URL, and via a genuine UI card click
(scoped to the unique card text, not a global text click) at multiple scroll depths (card index
0, ~100, and a plain two-segment id `motion-patterns`). The URL bar correctly updates to
`/library/skills/<id>` in every case; no console error occurs; and the network log shows the
only skills-related request fired is `GET /api/skills/library` (the bulk list), never a per-skill
resolution — the detail route effectively never attempts to render skill-specific content for
ANY id anymore. This is a materially different, far more severe failure (100% of the 186 skills
affected, not 7) with an apparent live regression between the two testing windows, so it is filed
as a new, distinct issue rather than an update to the closed-scope no-hyphen bug.

### Reproduction
1. Sign in as qa-admin, go to `/library?tab=skills`.
2. Click the `html-deck-to-pptx` card (or `android-clean-architecture`, or `windows-desktop-e2e`,
   or `motion-patterns` — all reproduce identically): URL updates to
   `/library/skills/html-deck-to-pptx`.
3. Observe: instead of the skill's detail page, the exact same Library catalog listing renders
   (header "94 agents · 186 skills · 8 hooks", tab pills, category pills, full 186-card grid
   starting at "Accessibility (WCAG 2.2)") — under the detail URL.
4. Reload the same URL directly (`browser_navigate` to
   `http://localhost:3000/library/skills/html-deck-to-pptx` from a fresh load): identical
   fallback, confirming this is not a stale-SPA-state artifact.
5. Repeat with `windows-desktop-e2e` and `accessibility-auditor`: same fallback in every case.
6. Confirm via `browser_network_requests` that only `GET /api/skills/library` (the bulk list)
   fires — no per-skill request is ever attempted — and `browser_console_messages` shows no
   error.

### Expected
`/library/skills/<id>` should render that skill's own detail page (heading, description, full
markdown content, tags, "Copy content" controls) for any valid skill id, exactly as documented
working in the earlier bug for `windows-desktop-e2e` and `html-deck-to-pptx`.

### Actual
Every tested skill id — hyphenated or not, including the two ids previously proven to work —
now renders the Library catalog listing page under the correct detail URL, with no error and no
indication the specific skill was never resolved. The skill-detail feature is effectively
non-functional for the entire catalog, not just the 7 no-hyphen ids.

### Evidence
- Before (listing page, card visible): `bug-hunter/evidence/library-skills/BUG-20260828-091300-library-skills-r2/01-before-listing.png`
- Failure (`html-deck-to-pptx`, URL on detail route, listing rendered): `bug-hunter/evidence/library-skills/BUG-20260828-091300-library-skills-r2/02-failure-detail-url-shows-listing.png`
- After reload, still broken (fresh navigation to same URL): `bug-hunter/evidence/library-skills/BUG-20260828-091300-library-skills-r2/03-after-reload-still-broken.png`

### Browser Signals
- Console: no errors in any of the ~6 reproductions (click-based and direct-navigation).
- Network: only `GET /api/skills/library` (bulk list) fires; no per-skill fetch attempt on any
  failing navigation, confirmed via `browser_network_requests`.
- State/URL: `location.href` correctly reflects `/library/skills/<id>` in every case while the
  rendered DOM is the unrelated listing page.
- **Fixed:** 2026-08-28 by [FIX-340](../.knowledge/cards/20260828-2230-FIX-340.md) — one file, `frontend/src/store/listenerMiddleware.ts`: the `signedIn` preload no longer awaits `fetchWorkflows`/`fetchRecentRuns` before dispatching `fetchAgentLibrary`/`fetchSkills`/`fetchHooks`; all five go out together. The INFERRED unmemoized-`useSkillsCatalog` mechanism above is CORRECTED, not confirmed: the seed effect and `SKILLS.find` both work, `skillsStatus` had simply not reached `"succeeded"` yet (measured 12.2s of gate on a cold load). The card-click path re-measured as never broken.
- **Fix verified:** `tests/integration/e2e/suites/08_library/test_iss232_skill_detail_full_regression.py` — marked run XPASS(strict) = FAILED (the fix signal; xfail marker left for 6-verifier); `--runxfail` run 1 passed, 0 misses across 6 cold navigations. `frontend/src/store/listenerMiddleware.test.ts` 1 passed.
- **Verified:** 2026-08-28 by 6-verifier. Ran `test_iss232_skill_detail_full_regression.py` alone
  (`.venv` at `tests/integration/e2e/.venv`): marked run reproduced `XPASS(strict) = FAILED` (the
  pass signal); `xfail` marker removed, re-run plain green (1 passed). `listenerMiddleware.test.ts`
  1 passed (vitest). Manual repro in lane5 Chrome, qa-admin, matching the register's exact
  conditions: 6x back-to-back cold `about:blank` -> `/library?tab=skills` ->
  `/library/skills/html-deck-to-pptx` loop, checked 500ms after each load — 0/6 misses, dialog
  open every time (was 100% failure pre-fix); cold direct nav to
  `/library/skills/windows-desktop-e2e` (the other id the register named) also opened its dialog
  cleanly with correct SKILL.md content and no console errors/warnings; genuine card click from
  `/library?tab=skills` opened the dialog in the same tick. Screenshot:
  `bug-hunter/evidence/library-skills/BUG-20260828-091300-library-skills-r2/04-after-fix-detail-opens.png`.
  Health: `npm run build` compiled clean (11/11 static pages, no TS errors from Next's own
  typecheck); regression file `suites/08_library/test_library.py` 24/24 passed; backend
  `:8000/docs` 200 (frontend-only fix, no restart needed). `backend/lint-imports` shows 1 broken
  contract (`kernel imports only capability ports`) — pre-existing, unrelated to this fix
  (FIX-340 touched only `frontend/src/store/listenerMiddleware.ts`, zero Python files; the broken
  contract traces through `execution_engine` -> `app.api.run_commands`/`user_workflows`, files
  this bug never touched), noted but not mine to fix.

## BUG-20260828-092630-library-agents-id — Library agent detail's Skills tab "Add" gives success feedback (checkmark + badge count) but persists nothing — silently discarded on reload, no Save affordance exists at all

- **Page:** Library — agent detail
- **Route:** /library/agents/<agentId> (e.g. /library/agents/material-analyzer)
- **Severity:** Medium
- **Status:** ESCALATED
- **Fix applied:** [FIX-383](../.knowledge/cards/20260829-0025-FIX-383.md) — `frontend/src/components/library/LibraryPage.tsx` no longer passes `onSkillsChange` to `AgentCapabilitiesModal`, so `readOnly={!onSkillsChange}` resolves true and the Skills tab renders the honest disabled list (verified live: Add button disabled + "Attach skills to this agent in the workflow composer." hint)
- **Escalated because:** ISS-318's Expected offers two remedies and the e2e test asserts the OTHER one — that Add fires an `/api/agents*`/`/api/skills*` call and survives a fresh navigation. No such backend surface exists for a built-in catalog agent (`backend/app/api/agents.py:216-232` returns no `skills` field for filesystem agents) and ADR-0010 decided against one, so that branch needs a new endpoint + migration. Both tests still XFAIL; the test file was NOT edited. Someone must pick: accept read-only and rewrite the test, or build the persistence surface.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced identically on every cold-start
  cycle (cycles 1-3), no axis variance needed
- **Root cause:** `AgentCapabilitiesModal` sets `readOnly={!onSkillsChange}` for the shared
  `AgentSkillsPicker` (`AgentsPopup.tsx:873`); `LibraryPage.tsx:1030-1050` supplies
  `onSkillsChange` anyway even though its own component contract names this exact mount as
  having nowhere to write back, so the picker renders full live/checkmark UI while the
  callback only writes a `useRef` (`savedSkillsRef`) scoped to `LibraryPage`'s own mount
  lifetime — wiped on reload.
- **Blast radius:** grepped every caller of `AgentCapabilitiesModal`/`onSkillsChange` in
  `frontend/src/`; `LibraryPage.tsx` is the only broken instance of this exact mechanism
  today (`AgentLibrary.tsx`'s 3 other hosts correctly omit `onSkillsChange`, its 4th
  genuinely persists via `ComposerPage.tsx`'s `pendingSkills`). The same drawer's Config tab
  shares the defect class, already tracked (ISS-392/ISS-393). New: the adjacent Hooks tab
  has no readOnly-equivalent gate at all and writes into one global, agent-unscoped context —
  ISS-441.
- **Fix belongs in:** `AgentCapabilitiesModal` (`AgentsPopup.tsx`) once — not a
  `LibraryPage.tsx`-only patch.
- **Issue cards:** [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md) (root),
  [ISS-441](../.knowledge/cards/20260828-2257-ISS-441.md) (sibling: Hooks tab, same drawer)
- **Found at:** 2026-08-28 09:26 UTC
- **Found by:** bug-library-agents-id-r2
- **Fingerprint:** `/library/agents/<id>|agent-detail-skills-tab-add-skill|click-add-skill-then-reload|checkmark-and-badge-shown-but-no-network-call-and-state-lost-on-reload`
- **Evidence:** `bug-hunter/evidence/library-agents-id/BUG-20260828-092630-library-agents-id/`

### Summary
On the Library agent detail drawer's Skills tab, clicking the "+" (Add) button on any
catalog skill immediately renders full success feedback — the button becomes a filled
checkmark and a count badge (e.g. "1") appears on the "SKILLS" section header — implying the
skill was attached to the agent. No network request fires for this action (confirmed via the
network log: zero new requests appear between before/after states), and unlike the Config tab
this Skills tab has no Save/Cancel button at all — there is no way to persist the change even
in principle. A reload of the exact same URL silently wipes the selection back to zero, with
no warning, toast, or indication anything was lost. This is a materially different (and
arguably worse) gap than the already-filed `BUG-20260828-025950-library-agents-id` ("Save
agent" Config override silently discards with no API call): that bug at least has a Save
button whose click fails silently; this Skills tab has no persistence path whatsoever, yet
gives the same convincing "it worked" visual confirmation.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/library/agents/material-analyzer`
   (Architecture Agent detail drawer opens).
2. Click the "Skills" tab. Observe the full skill catalog with "+" add buttons and no count
   badge on the "SKILLS" header.
3. Click "Add .NET Backend Expert" (or any skill's "+"). Observe the button becomes a filled
   checkmark and a "1" badge appears next to "SKILLS".
4. Confirm no new request appears in the network log after the click (`GET
   /api/agents/library`, `/api/skills/library`, `/api/hooks/library` are the only agent/skill
   calls, all from initial page load).
5. Reload `http://localhost:3000/library/agents/material-analyzer` (same URL), reopen the
   Skills tab. Observe: the badge is gone and ".NET Backend Expert" shows an empty "+" again —
   the addition is completely lost.
6. Repeated with a second skill (".NET Development Patterns") on a fresh load: same result —
   checkmark + badge appear immediately, zero network calls, reload wipes it.

### Expected
Either the "Add" action persists the skill grant (firing a save request, surviving reload), or
the UI does not present unambiguous success feedback (checkmark, count badge) for a change that
cannot be saved — e.g. a visible "unsaved changes" state and an explicit Save control, matching
the pattern used on the Config tab.

### Actual
The Skills tab shows full success feedback (checkmark, badge count) for an action that fires no
network request and has no save mechanism of any kind on that tab. The change is silently
discarded on reload with zero indication to the user that nothing was persisted.

### Evidence
- Before add: `bug-hunter/evidence/library-agents-id/BUG-20260828-092630-library-agents-id/01-before-add.png`
- After add (checkmark + badge "1", repro 1): `bug-hunter/evidence/library-agents-id/BUG-20260828-092630-library-agents-id/02-after-add-checkmark-badge.png`
- After reload (state lost, repro 1): `bug-hunter/evidence/library-agents-id/BUG-20260828-092630-library-agents-id/03-after-reload-silently-discarded.png`
- After add (repro 2, different skill): `bug-hunter/evidence/library-agents-id/BUG-20260828-092630-library-agents-id/04-repro2-after-add.png`
- After reload (repro 2, state lost again): `bug-hunter/evidence/library-agents-id/BUG-20260828-092630-library-agents-id/05-repro2-after-reload-discarded.png`

### Browser Signals
- Console: no errors observed.
- Network: no request fires for the Add-skill click in either repro; `browser_network_requests`
  taken immediately after each click shows only the pre-existing page-load calls
  (`/api/agents/library`, `/api/skills/library`, `/api/hooks/library`, etc.).
- State/URL: `location.href` unchanged throughout (`/library/agents/material-analyzer`); the
  checkmark/badge state lives only in React component state and does not survive a reload.

## BUG-20260828-093400-library-skills-id-r2 — Composer's per-agent Skills "View details" modal renders raw markdown syntax instead of formatted content

- **Page:** Library — skill detail (composer cross-surface: `/workflows/new` agent Skills tab preview)
- **Route:** /workflows/new (agent config panel → Skills tab → "View details" on any skill)
- **Severity:** Low
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `frontend/src/components/workflow/composer/AgentSkillsPicker.test.tsx` ISS-359 case ran XPASS ("Error: Expect test to fail"), `xfail`/`it.fails` marker removed for that case, re-ran plain green (1 passed); manual repro re-run by hand in Chrome (lane6, qa-admin, /workflows/new → Domain Discovery Agent → Skills tab → search "Windows Desktop" → View details): modal now renders 41 real heading/formatted elements (headings, bold, inline code, tables, lists), zero raw `#` markdown visible, matches `/library/skills/<id>`'s rendering. No new console errors. `npx tsc --noEmit` shows only 11 pre-existing unrelated test-file errors, none in the 3 changed files. `lint-imports` (from `backend/`) shows the same pre-existing `agents.execution_engine` → `app.api` contract break, unrelated to this frontend-only fix. Regression file `LibraryPage.test.tsx` 9/9 green. Backend needed no restart (pure frontend change); `:8000/docs` → 200.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — no narrowing needed, reproduced cold on every skill tried (Windows Desktop E2E Testing, .NET Backend Expert, Accessibility (WCAG 2.2))
- **Root cause:** `AgentSkillsPicker.tsx:280-283` — the `detailSkill` modal dumps `detailSkill.content` straight into a bare `<pre>` with zero markdown parsing; the "View details" Info button that opens it (`:208-216`) carries no `readOnly` gate, so every mount of this shared component reaches the identical broken render
- **Blast radius:** every `<AgentSkillsPicker` mount, confirmed by grep, not just the Canvas rail the report named — `AgentRow.tsx:267` (Composer Simple view), `AgentsPopup.tsx:870` (`AgentCapabilitiesModal`'s Skills tab, itself mounted from `LibraryPage.tsx:1035` the Library agent drawer, and `AgentLibrary.tsx:349` the "Add agent" popup). Also: the comparator page (`/library/skills/<id>` → `LibraryPage.tsx`'s `SkillDetailModal`) is itself a hand-rolled line-splitter, not a real markdown renderer — it only handles `#`/`##`-prefixed lines and `-`/`*`/numbered bullets, so inline `**bold**`/`` `code` ``/`[links]` render as literal text there too
- **Fix belongs in:** `AgentSkillsPicker.tsx`'s `detailSkill` block itself (not any caller) — every mount inherits automatically. Route both this modal and `LibraryPage.tsx`'s `SkillDetailModal` through the app's existing `react-markdown` + `remark-gfm` pipeline (`frontend/src/components/preview/MarkdownPreview.tsx`, already a dependency, already security-audited for no `rehype-raw`) rather than copying the incomplete hand-rolled parser into a second file
- **Issue cards:** [ISS-359](../.knowledge/cards/20260828-1918-ISS-359.md) (root — CONFIRMED),
  [FIX-403](../.knowledge/cards/20260829-0216-FIX-403.md) (fix), [ISS-605](../.knowledge/cards/20260829-0216-ISS-605.md) (deferred: mis-scoped assertion in ISS-591's test),
  [ISS-590](../.knowledge/cards/20260829-0113-ISS-590.md) (sibling: 3 more AgentSkillsPicker mounts, INFERRED),
  [ISS-591](../.knowledge/cards/20260829-0114-ISS-591.md) (sibling: comparator page's own parser is incomplete, INFERRED)
- **Found at:** 2026-08-28 09:34 UTC
- **Found by:** bug-library-skills-id-r2
- **Fingerprint:** `/workflows/new|agent-skills-view-details-modal|click-view-details-on-a-skill|markdown-hashes-shown-as-literal-text-not-rendered-headings`
- **Evidence:** `bug-hunter/evidence/library-skills-id/BUG-20260828-093400-library-skills-id-r2/`

### Summary
The skill's own detail page at `/library/skills/<id>` correctly renders the skill's markdown body
as HTML (proper `<h2>`/`<h3>` headings, etc — confirmed live for `windows-desktop-e2e`,
`html-deck-to-pptx`, `benchmark`, `accessibility`). But the same markdown body, shown in the
composer's per-agent Skills tab via the "View details" (eye) icon on a skill card, is dumped as
raw unrendered markdown text — literal `#`/`##` characters visible in the modal instead of
headings. Confirmed on two different skills (`windows-desktop-e2e` and `.NET Backend Expert`),
so this is a property of the preview-modal component, not one skill's content.

### Reproduction
1. Go to `/workflows/new`, click "Add agent", add any agent (e.g. Domain Discovery Agent) to the
   canvas, click the agent node to open its config panel.
2. Click the "Skills" tab (`[role="tab"]` labelled Skills).
3. Type a skill name into `input[data-testid='agent-skills-search']` (e.g. "Windows Desktop"),
   locate the matching skill card, click its "View details" icon-button
   (`[aria-label="View <skill name> details"]`).
4. Observe the modal that opens.
5. Repeat with a different skill (e.g. ".NET Backend Expert") — same result.

### Expected
The modal should render the skill's markdown body as formatted HTML — headings as `<h2>`/`<h3>`,
lists as `<ul>`/`<li>`, etc — matching what `/library/skills/<id>` shows for the same skill.

### Actual
The modal shows the markdown source verbatim: lines literally start with `#` / `##` characters,
no heading elements exist in the DOM (`querySelectorAll('h1,h2,h3,h4').length === 0` inside the
dialog), while the identical content on the skill's own detail page renders proper heading tags.

### Evidence
- Before (skill's own detail page, `windows-desktop-e2e`, correctly rendered `<h2>`/`<h3>`): `bug-hunter/evidence/library-skills-id/BUG-20260828-093400-library-skills-id-r2/01-before-library-detail-rendered-correctly.png`
- Failure (same skill, composer "View details" modal, raw `#` markdown visible): `bug-hunter/evidence/library-skills-id/BUG-20260828-093400-library-skills-id-r2/02-failure-composer-view-details-raw-markdown.png`
- Reproduced independently (different skill, ".NET Backend Expert", same raw-markdown modal): `bug-hunter/evidence/library-skills-id/BUG-20260828-093400-library-skills-id-r2/03-repro2-second-skill-raw-markdown.png`

### Browser Signals
- Console: none observed
- Network: none relevant — content comes from the already-loaded `/api/skills/library` payload, no failed request
- State/URL: URL stays `/workflows/new`; modal is `[role="dialog"]`; `document.querySelector('[role=dialog]').querySelectorAll('h1,h2,h3,h4').length` is `0` in both reproductions, and `/^#{1,3} /m.test(dialog.innerText)` is `true`

## BUG-20260828-093757-library-hooks-id — Closing a hook detail view resets the Hooks tab's search text and category filter

- **Page:** Library — Hooks tab
- **Route:** /library/hooks/<id> → close (X) → /library?tab=hooks
- **Severity:** Low
- **Status:** CLOSED
- **Found at:** 2026-08-28T09:37:57Z
- **Found by:** bug-library-hooks-id-r2
- **Fingerprint:** `/library/hooks/<id>|hooks-tab-search-and-category-filter|close-hook-detail-view|filters-and-search-text-reset-to-default`
- **Evidence:** `bug-hunter/evidence/library-hooks-id/BUG-20260828-093757-library-hooks-id/`
- **Verified:** 2026-08-29 (6-verifier, lane4) — `tests/integration/e2e/suites/08_library/test_iss360_hook_detail_close_preserves_filter.py`
  ran XPASS(strict) ("[XPASS(strict)] ISS-360 unfixed" is the pass signal), `xfail` marker
  removed, re-run plain green (1 passed, 4.4s). Manual re-run of the ORIGINAL repro in the
  browser (lane4, qa-admin, `/library?tab=hooks`): typed "session", clicked SessionStart pill →
  URL `?tab=hooks&category=SessionStart&search=session`, 1 card; opened "Session Context
  Loader" detail (`/library/hooks/session-start?tab=hooks&category=SessionStart&search=session`);
  closed via the header X — URL returned to `?tab=hooks&category=SessionStart&search=session`
  (not the bare `?tab=hooks` from before), search box still read "session", still 1 card shown.
  No console errors. Regression `suites/08_library/test_library.py`: 24 PASS / 0 FAIL. Frontend
  `npx tsc --noEmit` on the two touched files (`LibraryPage.tsx`, `routes.ts`): 0 errors (the
  full-project run surfaces pre-existing unrelated test-file errors in
  `HomeLaunchGrid.crossAccountLeak.test.tsx`, `api.sessionExpiryRedirect.test.ts`,
  `listenerMiddleware.test.ts` — none touch this fix). Backend `:8000/docs` 200; no restart
  needed (frontend-only fix). `lint-imports` (from `backend/`): same pre-existing
  `kernel imports only capability ports` break (`engine -> kernel_services -> app.api.run_engine`,
  `revision_analyzer -> app.api.run_commands`), unrelated to the changed files. Sibling cards
  ISS-592/593/594 (Agents/Skills tabs, Back button) share this fix but were not in this bug's
  card set and were not exercised here.

### Summary
On the Library "Hooks" tab, typing a search query and/or selecting a category pill (e.g.
"PostToolUse", "SessionStart") narrows the card list and updates the URL with
`?category=<name>`. Opening a hook's detail view (a full-screen modal reached at
`/library/hooks/<id>`) and then closing it with the X button does not return the user to the
filtered state they left — it navigates back to the bare `/library?tab=hooks` with the search
box cleared and the category pill reset to "All", showing all 8 hooks again. The active filter
context is silently discarded by the round-trip into a hook's detail view.

### Reproduction
1. Go to `http://localhost:3000/library?tab=hooks`.
2. Type `session` into the "Search hooks" box, then click the "SessionStart" category pill.
   URL becomes `/library?tab=hooks&category=SessionStart`; list narrows to one card
   ("Session Context Loader").
3. Click that card to open its detail view (`/library/hooks/session-start`).
4. Click the X (close) button in the detail view's header.
5. Observe the resulting state: URL is `/library?tab=hooks` (no `category` param), the search
   box is empty, the "All" pill is active, and all 8 hook cards are visible again.
6. Reproduced a second time with a different search term ("quality") and category
   ("PostToolUse") filtering to 2 cards — same reset behaviour after opening "Quality Gate" and
   closing it.

### Expected
Closing the hook detail view should return the user to the Hooks tab exactly as they left it —
same search text, same active category pill, same filtered card set (consistent with round-trip
behaviour elsewhere in the app where returning from a detail view preserves list context).

### Actual
The search text and category filter are both discarded; the tab resets to its default
unfiltered "All" state every time a hook detail view is closed.

### Evidence
- Before (filtered to "Session Context Loader" via search=session + SessionStart pill):
  `bug-hunter/evidence/library-hooks-id/BUG-20260828-093757-library-hooks-id/01-before-filter-search.png`
- After closing the detail view (search cleared, "All" pill active, all 8 cards shown):
  `bug-hunter/evidence/library-hooks-id/BUG-20260828-093757-library-hooks-id/02-after-close-reset.png`

### Browser Signals
- Console: none observed
- Network: none relevant — purely client-side state loss
- State/URL: `/library?tab=hooks&category=SessionStart` → `/library/hooks/session-start` →
  closes to `/library?tab=hooks` (category param and search box state both lost); reproduced
  identically with `category=PostToolUse` + search=`quality`
- **Validated:** 3/3 on 2026-08-28, cycle 1 — reproduced identically on 3 independent cold-start
  cycles (search=`session`+SessionStart, search=`quality`+PostToolUse, search=`config`+PreToolUse);
  no axis variation needed
- **Issue card:** [ISS-360](../.knowledge/cards/20260828-1917-ISS-360.md)
- **Root cause:** The loss happens on OPEN, not on close. `routes.libraryHook`/`libraryAgent`/
  `librarySkill` (`frontend/src/lib/routes.ts:127,129,131`) build a bare detail path with no query
  string, and that `router.push` remounts the whole `DashboardPage` tree under the `[...view]`
  catch-all — a confirmed, tested finding already documented in this codebase at
  `frontend/src/app/[...view]/page.tsx:3238`. The remount reinitializes every `useState` in
  `LibraryPage.tsx`: `hookSearch`/`skillSearch`/`searchQuery` (`:539,537,522`) have no
  URL-derivation at all, and `hookEvent`/`skillCategory`/`activeCategory` (`:538,536,521`) derive
  from the URL only via a one-shot mount initializer. `closeDetailModal` (`:635-641`) is not
  broken — it correctly threads whatever category state it's handed; that state was already reset
  to defaults before the X button was ever clicked.
- **Blast radius:** all 3 detail-route builders in `routes.ts` (`libraryAgent`/`librarySkill`/
  `libraryHook`), each with exactly one caller in `LibraryPage.tsx` (`:828`/`:908`/`:1005`), all
  funneling through the same `closeDetailModal`; plus the browser Back button, which reaches the
  identical already-lost state via the T16 effect (`:643-665`) without ever calling
  `closeDetailModal`.
- **Proposed fix:** in `routes.ts`, not per-caller — thread `{tab, category, search}` through
  `libraryAgent`/`librarySkill`/`libraryHook` (mirroring `routes.library`'s own params), and add a
  `search`/`q` param to the URL-seed pattern `LibraryPage.tsx:520-521` already uses for category so
  `searchQuery`/`skillSearch`/`hookSearch` survive the remount the same way.
- **Issue cards:** [ISS-360](../.knowledge/cards/20260828-1917-ISS-360.md) (root, root cause
  appended this pass), [ISS-592](../.knowledge/cards/20260829-0117-ISS-592.md) (sibling: Agents
  tab), [ISS-593](../.knowledge/cards/20260829-0117-ISS-593.md) (sibling: Skills tab),
  [ISS-594](../.knowledge/cards/20260829-0117-ISS-594.md) (sibling: browser Back button, all 3
  tabs)
- **Fix card:** [FIX-407](../.knowledge/cards/20260829-0441-FIX-407.md) — `routes.libraryAgent`/
  `librarySkill`/`libraryHook` now take the list's `{tab, category, search}` and `routes.library`
  gained a `search` param, so the remount a detail navigation triggers re-seeds the filters off
  the URL; `LibraryPage`'s search box, category chips and empty-state Clear all write `search`
  through one `applySearch` handler. All 4 tests XPASS(strict);
  `suites/08_library/test_library.py` 24 PASS as regression.

## BUG-20260828-094120-settings-ai-model-r2 — Concurrent `PUT /api/settings/preferences` calls silently lose one write and return a false-success response with the WRONG persisted value

- **Page:** Settings — AI Model
- **Route:** /settings/ai-model
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 (6-verifier) — `backend/tests/unit/test_settings_preferences_race.py`
  ran XPASS(strict) ("1 failed" is the pass signal — `[XPASS(strict)] ISS-319 unfixed`), then
  `xfail` marker removed and re-run plain green (`1 passed`). Manual re-run of the ORIGINAL
  repro in the browser (lane6, qa-admin, `/settings/ai-model`, baseline
  `eu.anthropic.claude-haiku-4-5-20251001-v1:0`): 3 concurrent PUT trials
  (opus-4-6/sonnet-4-5, sonnet-4-5/haiku-4-5, opus-4-6/opus-4-5), each request's own 200 body
  now reports its OWN requested model (previously the losing request's body echoed the winner's
  value) — 3/3, matching the validator's cycle count. `GET` and DB state confirmed consistent
  with the winner each time; baseline restored via a final PUT. No console errors. Frontend
  `npm run build` exit 0; backend `:8000/docs` 200 (pure `.py` fix, `--reload` already picked it
  up, no restart needed); `lint-imports` (run from `backend/`) shows the SAME pre-existing
  `kernel imports only capability ports` break (`engine -> kernel_services -> app.api.run_engine`,
  `revision_analyzer -> app.api.run_commands`) — unrelated to `settings.py`, not touched by this
  fix. Regression file `tests/integration/e2e/suites/09_settings/test_settings.py`: 1 failure,
  `test_the_constitution_editor_rejects_content_over_its_stated_limit` (ISS-293, already CLOSED
  separately) — 30s `wait_for_function` timeout on the `/settings/constitution` page reload,
  reproduced again in isolation (not flaky). Not this fix: touches `set_constitution`/
  `get_constitution`, a different handler on a different page with no shared code path with
  `update_preferences` (ISS-319's card explicitly ruled `set_constitution` out of this defect's
  blast radius). Not blocking ISS-319's close; flagged in NOTE for separate follow-up.
- **Validated:** 3/3 cold-start cycles, 2026-08-28 — root cause: `update_preferences` in
  `backend/app/api/settings.py:316-342` commits then `db.refresh(user)`, so a concurrent
  request's commit lands in that window and the response body reports the OTHER request's value
- **Root cause:** CONFIRMED — `update_preferences` (`backend/app/api/settings.py:345-353`
  current lines; was 316-342 at validation time, shifted by `FIX-361`'s unrelated entitlement
  check landing in between) sets `user.preferred_model`, `db.commit()`s, then `db.refresh(user)`
  and builds the response from THAT refreshed object. Two concurrent requests each get their own
  `Session` on the same `users` row with no version column and no `SELECT ... FOR UPDATE`; if a
  second request's `commit()` lands between this request's own `commit()` and `refresh()`, this
  request's `200` response reports the OTHER request's value while its own write is silently
  overwritten with no error to either caller.
- **Blast radius:** frontend — one caller, `AccountSettings.tsx:143` (`handleSaveModel`); 8
  downstream readers of `user.preferred_model` in `run_commands.py` inherit whichever value wins
  the race; two INFERRED siblings with the identical commit-then-refresh-then-respond-from-the-
  refreshed-object shape (grepped every `db.refresh(` site in `backend/app/api/`):
  `upsert_github_pat` (same file) and `admin.py`'s `update_user_tier`/`update_user_role`
  (privilege fields — a materially more serious instance if confirmed).
- **Proposed fix:** at each of the 3 sites, build the response from the value the request itself
  already validated and just committed (`model_id` / local `gh_user`+`scopes_header` /
  `request.tier`+`request.is_admin`) instead of a post-`db.refresh()` re-read — one line per
  site, no shared function needed for 3 differently-shaped responses, no migration required.
- **Found at:** 2026-08-28 09:41 UTC
- **Found by:** bug-settings-ai-model-r2
- **Fingerprint:** `/settings/ai-model|pipeline-model-preferences-api|two-concurrent-PUT-preferences-requests|lost-update-plus-response-body-reports-wrong-preferred-model`
- **Evidence:** `bug-hunter/evidence/settings-ai-model/BUG-20260828-094120-settings-ai-model-r2/`
- **Issue cards:** [ISS-319](../.knowledge/cards/20260828-1804-ISS-319.md) (root),
  [ISS-470](../.knowledge/cards/20260828-2310-ISS-470.md) (sibling: upsert_github_pat, INFERRED),
  [ISS-471](../.knowledge/cards/20260828-2310-ISS-471.md) (sibling: admin.py tier/role, INFERRED)
- **Fix card:** [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md) — the 200 body is
  built from the request's own validated `model_id`, not a post-`db.refresh()` re-read of the
  row; resolves ISS-319. ISS-470/ISS-471 (INFERRED siblings, unvalidated, no tests) stay open.

### Summary
`PUT /api/settings/preferences` is not safe under concurrent writes for the same user. When two
`PUT` requests with different `preferred_model` values are in flight at the same time (e.g. a
double-click on Save, or a rapid model-then-Save, model-then-Save sequence before the first
request's response returns — plausible given the page's own network latency and the documented
app-wide pattern of only-the-last-action-wins races), the backend performs what looks like an
unsynchronized read-modify-write: one of the two writes is completely lost (never reaches the
database in any form), **and** the losing request's own HTTP response is `200 OK` with a JSON
body whose `preferred_model` field reports the *other* request's value — not the value that
request itself sent, and not an error. This is worse than a simple race: the client that
requested, say, Opus 4.6 receives a "successful" 200 response body telling it the saved
preference is Sonnet 4.5, which is silently false. Reproduced 3 times in a row with different
model pairs,100% reproduction rate (not intermittent-only — every trial showed the same shape:
both responses converged on one value, and the final persisted state matched neither request's
program order, i.e. it was not simply "last network request wins").

### Reproduction
1. Sign in as qa-admin, confirm baseline `preferred_model` is `eu.anthropic.claude-haiku-4-5-20251001-v1:0` (Claude Haiku 4.5) on `/settings/ai-model`.
2. Via `browser_evaluate`, fire two `PUT /api/settings/preferences` requests concurrently
   (`Promise.all`) with different `preferred_model` values, e.g. request A = `claude-opus-4-6-v1`,
   request B = `claude-sonnet-4-5-20250929-v1:0`.
3. Observe: request A returns `200 OK` with body `preferred_model: "...sonnet-4-5..."` — NOT
   `opus-4-6`, the value A itself requested. Request B correctly returns `sonnet-4-5`.
4. `GET /api/settings/preferences` immediately after confirms the DB state is `sonnet-4-5` —
   request A's write (`opus-4-6`) is gone with no trace and no error was ever surfaced anywhere.
5. Repeated with a second model pair (`sonnet-4-5` vs `haiku-4-5`) — same shape: the losing
   request's response body reported the winner's value instead of its own requested value.
6. Repeated a third time (`opus-4-6` vs `sonnet-4-5`, order swapped) — same result again: 3/3
   reproductions, 100% hit rate on this exact concurrent pattern.
7. Reloading `/settings/ai-model` after each trial confirms the UI dropdown reflects the DB's
   (non-deterministic, program-order-independent) winner — the losing selection vanishes with no
   error toast, no console error, and no network-level indication anything went wrong (the losing
   request's own network tab shows 200 success).
8. Restored `preferred_model` to the original `eu.anthropic.claude-haiku-4-5-20251001-v1:0` via a
   final `PUT`, verified via reload.

### Expected
Either the second concurrent write should simply win deterministically (last-write-wins, which is
an acceptable UX for a single-user preference) with each response accurately reflecting what that
specific request persisted, or the API should serialize/reject overlapping writes (e.g. via
optimistic concurrency / a 409). At minimum, a `200 OK` response body must never report a
`preferred_model` value different from the one the response's own request just sent and that
request's write must not be silently discarded without any error surfaced to the caller.

### Actual
One of the two concurrent `PUT` requests is a silent no-op: its write never reaches the database,
and its own `200 OK` response body falsely reports the *other* request's value as the current
preference — a false-positive success with fabricated response content, not merely a lost update.

### Evidence
- Before (baseline, Haiku 4.5 selected): `bug-hunter/evidence/settings-ai-model/BUG-20260828-094120-settings-ai-model-r2/01-before-race-test.png`
- Failure (after the race, UI shows Sonnet 4.5 though the concurrent test also targeted Opus 4.6): `bug-hunter/evidence/settings-ai-model/BUG-20260828-094120-settings-ai-model-r2/02-after-race-lost-update.png`
- Restored (Haiku 4.5 reinstated as original baseline): `bug-hunter/evidence/settings-ai-model/BUG-20260828-094120-settings-ai-model-r2/03-restored-haiku45.png`

### Browser Signals
- Console: none observed — no client-side error at any point
- Network: both concurrent `PUT /api/settings/preferences` requests return `200 OK`; the losing
  request's JSON body contains the winning request's `preferred_model` value instead of its own
- State/URL: URL stays `/settings/ai-model` throughout; verified via direct `GET /api/settings/preferences`
  before/after each trial that the DB-persisted value silently diverges from one of the two
  requested values with no error path anywhere in the stack

## BUG-20260828-094937-settings-usage-r2 — /create/<type> composer has no tier gating at all; a basic-tier account reaches a fully configured, submit-ready wizard for a deliverable its own Usage & Limits page says it cannot run

- **Page:** Settings · Usage & Limits (entitlement claim) / Create composer (unenforced route)
- **Route:** /create/prototype (reproducible pattern likely applies to any tier-restricted `/create/<type>`)
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** `tests/integration/e2e/suites/03_launch_panels/test_iss321_wizard_no_tier_gate.py` — XPASS(strict)
  confirmed pre-change, `xfail` marker removed, re-run plain green
  (`test_basic_tier_cannot_reach_submit_ready_prototype_wizard[chromium] PASS`, 51.4s). Manual
  repro re-run by hand in lane4 Chrome, cold session: signed in `qa-basic@flowinqa.com`, direct
  navigation to `/create/prototype`, typed the full brief — Continue stayed `[disabled]` and a
  "Requires Pro plan — your plan does not include this deliverable." lock banner rendered where
  the enabled Continue used to be. Screenshot
  `bug-hunter/evidence/settings-usage/BUG-20260828-094937-settings-usage-r2/04-after-fix-continue-disabled-locked-basic.png`
  sits next to the original failure shots. No console errors on the page. Frontend unit tests
  `LaunchWizard.test.tsx` 19/19 pass; `tsc --noEmit` unchanged pre-existing 11 errors, none in
  LaunchWizard.tsx. `backend/` untouched by this fix — `lint-imports` (run from `backend/`)
  shows the same pre-existing `kernel imports only capability ports` break unrelated to this
  change. Regression file `suites/03_launch_panels/test_launch_panels.py`: 1 failure
  (`test_the_advanced_control_opens_the_agent_roster`, S-03-11, agent-count mismatch on
  `/create/user-stories` → `IdeaInputPage`, pre-existing and unrelated to `LaunchWizard.tsx`),
  19/20 pass including every wizard scenario. Only ISS-321 is closed by this fix; ISS-472,
  ISS-473, ISS-474 remain open per FIX-386's own scope notes.
- **Root cause:** CONFIRMED — `frontend/src/app/[...view]/page.tsx`'s `wizardMode` render branch
  (`:3833-3838`) returns `<LaunchWizard>` unconditionally with no call to
  `canRunPipeline`/`can_run_pipeline`, even though `user.tier` is already fetched in the same
  component (`:868-877`) and the shared client-side check
  (`frontend/src/lib/entitlements.ts:94`, `canRunPipeline(tier, pipelineType)`) already exists
  and is correctly used by `HomeLaunchGrid.tsx:221,280` for the dashboard catalog card.
- **Blast radius:** the missing gate is not unique to the `wizardMode` branch. Three distinct
  render surfaces reached through the same catch-all (or bypassing it) share the identical
  absence: `DashboardLayout.tsx:2901-2930` renders `<IdeaInputPage>` for `mainView==="input"`
  (`/create/app`, `/create/user-stories`, any catalog `/create/<type>`) with no `userTier` prop
  at all; `DashboardLayout.tsx:2937-2946` renders `<ComposerPage>` for `mainView==="composer"`
  (built-in `/workflows/{type}/canvas`, ADR-0014) likewise; and
  `frontend/src/app/workflow/create/page.tsx:24` is a SEPARATE Next.js route (outside the
  `[...view]` catch-all entirely) that renders `<LaunchWizard>` unconditionally — reachable both
  by direct URL and via `handleLaunchSaved`'s `router.push` when relaunching a saved
  ppt/prototype workflow (`DashboardLayout.tsx:1547,1574`) and via `CreationHub.tsx:31,35`. The
  T17 redirect a comment in `page.tsx:3628` claims neutralizes that route does not exist in the
  current `frontend/next.config.ts` (only 4 unrelated redirect rules; no `middleware.ts` either).
- **Proposed fix:** call `canRunPipeline(tier, pipelineType)` at the one choke point
  `[...view]/page.tsx` already has both values in scope — before the `wizardMode` early return
  and before `mainView` is allowed to resolve to `"input"`/`"composer"` for an unentitled type —
  or push the same check into `LaunchWizard` itself (the actual shared component both
  `page.tsx` and `workflow/create/page.tsx` render), since a guard added only inside
  `[...view]/page.tsx` would still leave `workflow/create/page.tsx`'s render unfixed.
- **Fix cards:** [FIX-386](../.knowledge/cards/20260829-0242-FIX-386.md) — tier gate in `LaunchWizard.tsx` (the component BOTH render sites mount), Continue disabled + "Requires Pro plan" lock banner; e2e XPASS(strict).
- **Issue cards:** [ISS-321](../.knowledge/cards/20260828-2002-ISS-321.md) (root),
  [ISS-472](../.knowledge/cards/20260829-0110-ISS-472.md) (sibling: IdeaInputPage/mainView="input", INFERRED),
  [ISS-473](../.knowledge/cards/20260829-0111-ISS-473.md) (sibling: standalone /workflow/create legacy page, INFERRED),
  [ISS-474](../.knowledge/cards/20260829-0112-ISS-474.md) (sibling: ComposerPage/built-in canvas, INFERRED)
- **Found at:** 2026-08-28 09:49 UTC
- **Found by:** bug-settings-usage-r2
- **Fingerprint:** `/create/prototype|composer-wizard|direct-url-navigation-basic-tier|full-multistep-wizard-loads-and-reaches-enabled-continue-despite-tier-not-entitled`
- **Evidence:** `bug-hunter/evidence/settings-usage/BUG-20260828-094937-settings-usage-r2/`

### Summary
`/settings/usage` correctly tells a basic-tier account it only has "Deliverable access" to 2 of 8
types (Product Requirements, Presentation) — confirmed accurate against
`TIER_PIPELINES["basic"]` in `backend/app/core/entitlements.py`. The dashboard catalog enforces
this consistently too: the "Build an interactive prototype" card is rendered `disabled` with a
"Requires Pro plan" lock badge for a basic-tier account, with no click path to its composer.
However, that gating lives ONLY on the dashboard card — the `/create/prototype` route itself
performs no entitlement check at all. Navigating a basic-tier session directly to
`/create/prototype` renders the identical, fully interactive multi-step composer a Pro/Enterprise
account gets: brief textarea, Attach file/Voice, the full Template gallery (60+ templates,
category filters, "Upload custom"), Design System and Discovery tabs, and — after typing a brief
and picking a template — an enabled "Continue" button that advances the wizard further. Nothing
in this flow indicates the account is not entitled to run it; the only place that information
exists is the dashboard card the user never has to visit if they have (or guess) the URL. Backend
launch endpoints DO still enforce `can_run_pipeline` at actual run creation (`run_commands.py`'s
`_require_tier_entitlement`, added as a P1 fix per its own comment), so this is a client-side-only
gap — but a real one: a basic-tier user can invest genuine effort (write a brief, pick a template,
click through the wizard) before any rejection, directly contradicting what `/settings/usage`
told them on the very page whose stated purpose is to explain what their plan allows.

### Reproduction
1. Sign in as `qa-admin@flowinqa.com` (enterprise), then switch session to
   `qa-basic@flowinqa.com` / `flowin-e2e-pass` (tier: basic per `/api/auth/me`).
2. Navigate to `/settings/usage`. Confirm "Basic plan" heading and "Deliverable access" listing
   only "Product Requirements" and "Presentation" — Interactive Prototype is absent.
3. Navigate to `/dashboard`. Confirm the "Build an interactive prototype" card is `disabled`,
   shows a lock icon and a "Requires Pro plan" badge, with no click target reaching its composer.
4. Navigate directly to `http://localhost:3000/create/prototype` (same basic-tier session, no
   re-login). Observe: the full "Configure your prototype" wizard renders — brief textarea,
   Attach file/Voice controls, Advanced (5 agents), and a Template tab with the entire template
   gallery, all fully interactive, `disabled: false` on every control.
5. Type a brief into the textarea, leave "No template" selected. Observe the footer now shows an
   enabled "Continue" button (`disabled: false`) alongside "Save workflow" / "Save as my version" —
   a basic-tier account reaches a submit-ready wizard state for a pipeline type its own plan page
   says it cannot access, with no lock, no warning, no upgrade prompt anywhere in this flow.

### Expected
A route the dashboard already gates by tier (disabled card + "Requires Pro plan") should not be
independently reachable and fully usable via direct URL for an unentitled tier — at minimum the
composer should show the same locked/upgrade state the dashboard card does, consistent with what
`/settings/usage` tells the same account about its own plan.

### Actual
`/create/prototype` performs no tier check: it loads and is fully interactive for a basic-tier
account, reaching an enabled "Continue" state, with zero indication anywhere in the flow that the
account is not entitled to this deliverable — a UI-only gap, since the backend launch endpoint
still correctly rejects the pipeline_type at actual run creation.

### Evidence
- Before (dashboard catalog card, basic tier, locked "Requires Pro plan"): `bug-hunter/evidence/settings-usage/BUG-20260828-094937-settings-usage-r2/01-dashboard-catalog-locked-basic.png`
- Failure (`/create/prototype` fully loaded and interactive, basic tier, direct URL): `bug-hunter/evidence/settings-usage/BUG-20260828-094937-settings-usage-r2/02-create-prototype-fully-loaded-basic.png`
- Failure (brief typed, "Continue" enabled, basic tier): `bug-hunter/evidence/settings-usage/BUG-20260828-094937-settings-usage-r2/03-continue-button-enabled-basic.png`

### Browser Signals
- Console: no errors on navigation to `/create/prototype` as basic tier.
- Network: page renders from client-side route/component state; no entitlement-check request is
  ever made client-side for this route.
- State/URL: `location.href` correctly reads `/create/prototype` throughout; `GET
  http://localhost:8000/api/auth/me` confirms `tier: "basic"` for the session used.
- Code: `backend/app/api/run_commands.py::_require_tier_entitlement` (calls
  `can_run_pipeline`) IS wired into the REST launch/revision/resume endpoints — the backend gap
  this resembles was already fixed as a P1; only the composer route's client-side gating is
  missing. Related in shape (catalog-level lock is cosmetic, the underlying route is unguarded)
  to `BUG-20260828-050115-library` (Coming-Soon library agents reachable by direct URL) but a
  distinct route, component and trigger (subscription-tier entitlement vs. unreleased-feature
  flag), not a duplicate of it.

- **Validated:** 3/3 on 2026-08-28, cold start every cycle — direct URL entry to
  `/create/prototype` as `qa-basic` bypasses the dashboard's correctly-locked catalog card;
  `[...view]/page.tsx` never gates the wizard on `can_run_pipeline`.
- **Issue card:** [ISS-321](../.knowledge/cards/20260828-2002-ISS-321.md)

## BUG-20260828-095800-settings-constitution-r2 — "Clear" on Constitution deletes the saved value immediately, with no confirmation and no relation to "Save"

- **Page:** Settings · Constitution
- **Route:** /settings/constitution
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — unit `AccountSettings.render.test.tsx` 8/8 green; `tsc --noEmit`
  clean on `AccountSettings.tsx`; manual repro in real Chrome (qa-admin,
  `/settings/constitution`) reproduced the fix exactly as FIX-385 documents: clicking "Clear"
  now raises a native confirm ("Clear your constitution? This permanently deletes the saved
  instructions prepended to every agent on every run."), dismissing it leaves `GET
  /api/settings/constitution` returning the saved value (`"E2E S-09-12: answer in exactly one
  sentence."`), accepting it still deletes (`{"content": null}`) — matches expected behavior.
  Restored via `PUT` + reload, confirmed 44/4000 chars back. No new console errors on the page.
  The e2e test `test_clear_constitution_requires_confirmation_before_deleting` was run 5 times
  (not just the fixer's 3): 4× `xfail`, 1× hard `FAILED` — the same
  `Dialog.dismiss: Cannot dismiss dialog which is already handled` crash FIX-385 already
  attributed to the test's own double dialog-handler bug, filed separately as ISS-581. It never
  reached XPASS in any run, so the `xfail` marker was left in place (removing it would make the
  suite intermittently red for a defect unrelated to this fix). Running the full
  `test_settings.py` file surfaced one cascade failure in
  `test_the_constitution_editor_rejects_content_over_its_stated_limit`, caused by the same
  ISS-320 test crash leaving browser/page state dirty mid-suite; run alone it passes cleanly —
  not a regression. `lint-imports` (from `backend/`) shows one pre-existing broken contract
  (`kernel imports only capability ports`, unrelated `agents.execution_engine` → `app.api`
  edges) — untouched by this frontend-only fix.
- **Validated:** 3/3 on 2026-08-28, cold start every cycle — reproduces on the untouched saved
  value and also with an unsaved draft in the textarea; "Clear" always deletes the persisted
  backend value with no confirmation, independent of local draft state.
- **Root cause:** CONFIRMED — `ConstitutionSection`'s `handleDelete`
  (`frontend/src/components/settings/AccountSettings.tsx:549-566`) is wired directly to the
  "Clear" button's `onClick` (`:630`) with no intermediate confirm step (no `window.confirm`,
  no modal, no two-step "are you sure"). On a `200` it fires `DELETE
  /api/settings/constitution` synchronously and sets local `content`/`status` to match — the
  backend delete (`backend/app/api/settings.py:402-410`, `delete_constitution`) is a hard
  delete with no soft-delete/versioning, so the frontend click is the only safeguard that could
  exist, and it does not exist. `handleDelete` has exactly one call site (its own button); it is
  a local closure, not a shared function.
- **Blast radius:** `grep -rn "window.confirm" frontend/src` returns exactly ONE hit in the
  entire frontend (`DashboardLayout.tsx:1717`, a navigation guard, not a delete confirmation) —
  no destructive-delete call site anywhere in the app is confirmation-gated. Three other live,
  UI-wired call sites share the identical shape (grepped every `http.delete`/`method: "DELETE"`
  site and its onClick wiring): `SkillManager.tsx:99-114/221` (`deleteSkill`, agent skill
  delete), `IntegrationsCard.tsx:123-139/245` (`handleDeletePat`, GitHub PAT remove) and
  `IntegrationsCard.tsx:161-176/360` (`handleRevoke`, API-key revoke). A fourth path
  (`AccountSettings.tsx:230-234`, the settings `Tabs onChange` handler) silently unmounts
  `ConstitutionSection` and discards an unsaved draft with the same zero-confirmation gap,
  distinct from the already-filed Back-button case (ISS-372).
- **Proposed fix:** no shared confirm-before-destroy primitive exists in
  `frontend/src/components/ui/` for any of these call sites to route through. Add one there
  (e.g. a `useConfirm()`/`ConfirmDialog`) and route `handleDelete`, `deleteSkill`,
  `handleDeletePat` and `handleRevoke` through it, plus a dirty-check on the Constitution tab's
  `Tabs onChange`. A guard added only inside `AccountSettings.tsx` leaves the other three call
  sites broken.
- **Fix card:** [FIX-385](../.knowledge/cards/20260829-0241-FIX-385.md) — `handleDelete` now
  returns early unless a `window.confirm` is accepted, so an unconfirmed "Clear" never sends
  the DELETE; accepting it still deletes. Verified directly against the running app (dismiss →
  `GET /api/settings/constitution` still returns the saved value; accept → `{"content": null}`).
  The card's e2e test still reports `xfail` for two defects of its OWN, filed as
  [ISS-581](../.knowledge/cards/20260829-0241-ISS-581.md) — its setup's typed marker is
  overwritten by the editor's second mount fetch before Save reads it, and its
  `page.on("dialog")` duplicates conftest's autouse dismisser. The test was NOT edited.
- **Issue cards:** [ISS-320](../.knowledge/cards/20260828-1802-ISS-320.md) (root),
  [ISS-480](../.knowledge/cards/20260828-2320-ISS-480.md) (sibling: SkillManager delete, INFERRED),
  [ISS-481](../.knowledge/cards/20260828-2321-ISS-481.md) (sibling: IntegrationsCard PAT/API-key, INFERRED),
  [ISS-482](../.knowledge/cards/20260828-2322-ISS-482.md) (sibling: Constitution tab-switch draft loss, INFERRED)
- **Found at:** 2026-08-28 09:58 UTC
- **Found by:** bug-settings-constitution-r2
- **Fingerprint:** `/settings/constitution|clear-button|click-clear|immediate-unconfirmed-delete-of-saved-constitution`
- **Evidence:** `bug-hunter/evidence/settings-constitution/BUG-20260828-095800-settings-constitution-r2/`

### Summary
The "Clear" button next to "Save constitution" does not behave like a form-reset control — it
fires `DELETE /api/settings/constitution` immediately on click, permanently erasing the user's
saved constitution (the standing instruction set the page says "is prepended to every agent on
every run") with zero confirmation dialog, zero undo, and no requirement to also click "Save".
Its placement directly beside "Save constitution", and the fact that typing into the textarea
never auto-saves, strongly implies "Clear" is a local/pending-edit reset — but it is in fact a
destructive, irreversible, immediately-persisted account-wide delete. A user who clicks it to
reset a draft edit (or misclicks it instead of "Save") loses their real saved constitution with
one click and no way back except retyping it from memory.

### Reproduction
1. Sign in as qa-admin, navigate to `/settings/constitution`. Confirm existing saved content
   (`"E2E S-09-12: answer in exactly one sentence."`, 44/4000 chars).
2. Click "Clear" (no typing needed — reproduces on the saved value directly, and also reproduces
   after typing unsaved draft text first).
3. Observe: textarea instantly empties, counter resets to "0 / 4000 chars", a "Constitution
   cleared." status message appears, and the "Save constitution" button becomes disabled.
4. Inspect network: `DELETE http://localhost:8000/api/settings/constitution` fires immediately
   on the click and returns `204 No Content` — no confirm dialog was shown, no separate "Save"
   click was needed.
5. Confirm persistence: `GET /api/settings/constitution` (direct, with bearer token) returns
   `{"content": null}`. Reloading the page shows the empty textarea — the deletion is real and
   permanent, not merely a pending local edit.
6. Reproduced twice independently (once after first typing unsaved draft text over the saved
   value, once by clicking Clear directly on the untouched saved value) — both times the
   backend content is deleted instantly with no confirmation.
7. Restored the original content (`"E2E S-09-12: answer in exactly one sentence."`) via the
   textarea + "Save constitution" both times, and verified via `GET` and a full page reload
   that the original text is back before finishing.

### Expected
A destructive, irreversible action that erases a user's standing instructions for every future
agent run should require an explicit confirmation step (dialog, or at minimum require also
clicking "Save constitution" to commit the empty state) before it is persisted to the backend —
consistent with how "Save constitution" itself requires a deliberate, separate click to persist
any change.

### Actual
"Clear" deletes the saved constitution on the backend instantly on click, with no confirmation
and independently of "Save constitution" — a single misclick permanently destroys the user's
constitution.

### Evidence
- Before: `bug-hunter/evidence/settings-constitution/BUG-20260828-095800-settings-constitution-r2/01-before.png`
- Failure (cleared instantly after one click on "Clear"): `bug-hunter/evidence/settings-constitution/BUG-20260828-095800-settings-constitution-r2/02-failure.png`
- After restore + reload: `bug-hunter/evidence/settings-constitution/BUG-20260828-095800-settings-constitution-r2/03-after-restore-reload.png`

### Browser Signals
- Console: none observed
- Network: `DELETE http://localhost:8000/api/settings/constitution` → `204 No Content`, fired
  synchronously on the "Clear" click, no preceding confirmation request/dialog
- State/URL: URL stays `/settings/constitution` throughout; `GET /api/settings/constitution`
  confirms `content: null` after Clear, and confirms restored content after re-save + reload

## BUG-20260828-101500-login-expired-true-r2 — Mid-session token expiry drops the original protected route; re-login always lands on /dashboard instead of using the working `?redirect=` mechanism

- **Page:** Login (session-expired variant)
- **Route:** /login?expired=true (entered via a protected route's 401)
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 by 6-verifier — `frontend/src/lib/api.sessionExpiryRedirect.test.ts` XPASS confirmed (`.fails` marker fired, "Error: Expect test to fail"), `.fails` removed, re-run plain green (1 passed). Regression files green: `routes.test.ts` (59 passed), `api.test.ts` (2 passed), `api.refreshRetry.test.ts` (6 passed). `npx tsc --noEmit` clean on both changed files. `npm run build` succeeds. Manual repro by hand in real Chrome (lane6), same conditions as validation: signed in qa-admin -> `/settings/ai-model` loads -> corrupted `auth_token` -> re-nav -> redirected to `http://localhost:3000/login?expired=true&redirect=%2Fsettings%2Fai-model` (redirect param now present, "Your session expired" banner shown) -> signed back in -> landed on `/settings/ai-model` with AI Model tab selected, NOT `/dashboard`. No console errors on the page. Backend `:8000/docs` 200 (frontend-only fix, no restart required). `lint-imports` (run from `backend/`) shows 1 pre-existing broken contract (`agents.execution_engine.engine` -> `app.api` via `kernel_services`/`revision_analyzer`) unrelated to this fix — zero backend files touched by FIX-384, not this verification's to fix. After screenshot: `bug-hunter/evidence/login-expired-true/BUG-20260828-101500-login-expired-true-r2/06-after-fix-relogin-lands-on-settings-ai-model.png`.
- **Root cause:** `handleSessionExpiry()` (`frontend/src/lib/api.ts:175-180`) navigates via `routes.login({ expired: true })`, and `routes.login`'s param type (`frontend/src/lib/routes.ts:25-27`) has no `redirect` field at all, so the mid-session-expiry path can never attach one — unlike the signed-out guard's `buildLoginRedirect()` (`frontend/src/lib/authRedirect.ts:43-49`), which already builds and open-redirect-guards one. The read side already works correctly: `login/page.tsx:55` (mount guard) and `:67` (`goToDestination`, called from both the plain-password submit and every Cognito-challenge branch) both consume `searchParams.get("redirect")` via `resolveRedirectTarget` whenever it is present.
- **Blast radius:** all 13 confirmed call sites of the one shared `handleSessionExpiry()` function — `api.ts`'s own `fetchWithAuth` and `authedFetch`, `store/api/http.ts`'s axios interceptor, `useHandoffSocket.ts`, `useRunStream.ts`, `prototype-api.ts`, `ppt-api.ts`, `api-handoff.ts`, `LaunchWizard.tsx` (x2), `[...view]/page.tsx` (x3) — one function, so one fix (extend `routes.login`'s signature + the one call site inside `handleSessionExpiry()`) covers every caller; none needs its own change.
- **Issue cards:** [ISS-322](../.knowledge/cards/20260828-2007-ISS-322.md) (root), [ISS-486](../.knowledge/cards/20260828-2335-ISS-486.md) (sibling, INFERRED: a query-string-bearing protected route, e.g. `/analytics?range=&pipeline=`, is untested by ISS-322's two validated routes and is the shape most likely to expose a nested-query-string encoding bug in the fix)
- **Validated:** 3/3 on 2026-08-28, cycle 1 — cold start, corrupted `auth_token` on `/settings/ai-model`, no `redirect` param ever attached, re-login always lands on `/dashboard`
- **Issue card:** [ISS-322](../.knowledge/cards/20260828-2007-ISS-322.md)
- **Fix card:** [FIX-384](../.knowledge/cards/20260829-0232-FIX-384.md) — `routes.login` gains `redirect?: string`; `handleSessionExpiry()` passes `window.location` pathname+search through `buildQueryString`
- **Found at:** 2026-08-28 10:15 UTC
- **Found by:** bug-login-expired-true-r2
- **Fingerprint:** `/login|auth-guard|mid-session-token-expiry-on-protected-route|redirect-param-dropped-lands-on-dashboard-not-original-route`
- **Evidence:** `bug-hunter/evidence/login-expired-true/BUG-20260828-101500-login-expired-true-r2/`

### Summary
The app has a working return-path mechanism: a **signed-out** user deep-linking a protected
route is sent to `/login?redirect=%2F<path>` and, after signing in, is correctly returned to
that exact route (verified here on `/settings/ai-model`, and already established by a sibling
worker across `/create`, `/settings`, `/workflow`, and `/runs/<id>/workspace`). But when a
session expires **mid-session** on a protected route (the 401 ladder auto-redirecting an
already-signed-in user to `/login?expired=true`), that same mechanism is not used: no
`redirect` query param is ever attached, and after signing back in the user is unconditionally
sent to `/dashboard`, losing the page they were actually on. This is distinct from the filed
High (`BUG-20260827-223300-login-expired-true`, an already-authenticated user with a
*still-valid* token seeing the login form) — this bug concerns a *genuinely* expired/invalid
token and the destination after a *successful* re-login.

### Reproduction
1. Signed in as qa-admin, navigate to `http://localhost:3000/settings/ai-model` (confirms
   loads normally).
2. In devtools, corrupt the token: `localStorage.setItem('auth_token', 'corrupted-expired-token-xyz')`.
3. Reload/renavigate to the same URL. The 401 ladder fires and the app redirects to
   `http://localhost:3000/login?expired=true` — no `redirect` param.
4. **Contrast check:** clear `auth_token` entirely (fully signed out) and navigate to
   `http://localhost:3000/settings/ai-model` directly. The app correctly redirects to
   `http://localhost:3000/login?redirect=%2Fsettings%2Fai-model`.
5. From the `?redirect=` URL, sign in as qa-admin: correctly lands back on
   `/settings/ai-model` (the mechanism works).
6. Repeat steps 1–3 from `http://localhost:3000/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/workspace`
   instead: same result, `/login?expired=true` with no redirect param.
7. From the `?expired=true` state (both routes tested), sign in as qa-admin: lands on
   `/dashboard` in both cases, not `/settings/ai-model` or the run workspace.

### Expected
A mid-session expiry on a protected route should preserve that route the same way the
signed-out deep-link guard does (`?redirect=%2F<path>`), so re-authenticating returns the user
to what they were doing — consistent with the app's own established pattern for this exact
scenario elsewhere.

### Actual
The 401-triggered redirect to `/login?expired=true` never attaches a `redirect` param. Signing
back in always lands on `/dashboard`, discarding the original route, even though the identical
mechanism works correctly when the user was signed out to begin with.

### Evidence
- Before (settings/ai-model loads normally): `bug-hunter/evidence/login-expired-true/BUG-20260828-101500-login-expired-true-r2/01-before-settings-ai-model.png`
- Failure (corrupted token → `/login?expired=true`, no redirect param, settings route): `bug-hunter/evidence/login-expired-true/BUG-20260828-101500-login-expired-true-r2/02-expired-no-redirect-param-settings.png`
- Failure (re-login lands on /dashboard, not /settings/ai-model): `bug-hunter/evidence/login-expired-true/BUG-20260828-101500-login-expired-true-r2/03-landed-dashboard-not-settings.png`
- Second route repro (run workspace, same no-redirect-param failure): `bug-hunter/evidence/login-expired-true/BUG-20260828-101500-login-expired-true-r2/04-expired-run-workspace-no-redirect-param.png`
- Second route repro (re-login lands on /dashboard, not the run workspace): `bug-hunter/evidence/login-expired-true/BUG-20260828-101500-login-expired-true-r2/05-after-relogin-dashboard-not-run-workspace.png`

### Browser Signals
- Console: no errors related to the redirect logic itself
- Network: 401 on the protected route's API call triggers the auth-guard redirect to
  `/login?expired=true`; no `redirect` query param is constructed for this path, unlike the
  signed-out guard which does build `?redirect=%2F<path>`
- State/URL: confirmed on two distinct protected routes (`/settings/ai-model`,
  `/runs/<id>/workspace`); both produce `/login?expired=true` with no redirect param, and both
  land on `/dashboard` after re-login, contrasted against the working `?redirect=` flow verified
  from a fully signed-out state

## BUG-20260828-102900-analytics-r2 — Daily Activity chart tooltip shows raw unformatted token counts, breaking the page's own number-formatting convention

- **Page:** Analytics
- **Route:** /analytics
- **Severity:** Low
- **Status:** CLOSED
- **Fixed:** 2026-08-29 — [FIX-405](../.knowledge/cards/20260829-0423-FIX-405.md); `AnalyticsPage.tsx`
  `dailyData` now sets `tip: `${label}: ${formatTokens(d.total_tokens)}`` for token-bearing days
  (`:246-257`), leaving `BarChart.tsx` untouched. `AnalyticsPage.test.tsx` ran 9 passed + the
  ISS-369 `it.fails` guard XPASSing (`Error: Expect test to fail`) = fix confirmed; marker left
  in place for the verifier. `npx tsc --noEmit` clean for analytics files.
- **Verified:** 2026-08-29 — `frontend/src/components/analytics/AnalyticsPage.test.tsx` XPASSed
  the ISS-369 guard (`Error: Expect test to fail`, 9 passed + 1 XPASS), `xfail`/`it.fails` marker
  removed, re-run plain green (10 passed, 1.51s). Regression check
  `frontend/src/components/analytics/charts/BarChart.test.tsx` (untouched, the shared primitive):
  3 passed. Manual repro by hand in the browser (lane5, qa-admin, real Chrome, `/analytics?range=all`):
  hovered the "Aug 24" bar in Daily Activity — tooltip now reads `Aug 24: 2.4M`, matching the KPI
  tile/By Pipeline Type/By Model formatting convention on the same page; no raw `2364478` anywhere
  in the DOM. No new console errors/warnings on the page. `npx tsc --noEmit` clean for analytics
  files. `lint-imports` (run from `backend/`) shows 1 pre-existing broken contract
  (`agents.execution_engine.engine` → `app.api.*` via `kernel_services`/`revision_analyzer`) —
  unrelated to this frontend-only fix, not introduced by it, not touched here.
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic on every cold-start hover, no timing/axis needed
- **Issue cards:** [ISS-369](../.knowledge/cards/20260828-1933-ISS-369.md) (root — filed by the
  validator during CONFIRMED, root cause independently re-confirmed by this analysis; no new
  sibling cards filed, see Blast radius)
- **Found at:** 2026-08-28 10:29 UTC
- **Found by:** bug-analytics-r2
- **Fingerprint:** `/analytics|daily-activity-chart-tooltip|hover-a-bar|raw-unformatted-integer-instead-of-K-M-abbreviation`
- **Evidence:** `bug-hunter/evidence/analytics/BUG-20260828-102900-analytics-r2/`
- **Root cause:** CONFIRMED (read directly). `BarChart`'s per-bar hover tooltip
  (`frontend/src/components/analytics/charts/BarChart.tsx:85-89`) composes
  `` `${d.label}: ${d.value}` `` — the raw JS number — whenever the caller does not supply the
  datum's optional `tip` field (`BarDatum.tip`, `BarChart.tsx:39`, already an extension point for
  exactly this). `AnalyticsPage.tsx` builds the Daily Activity series (`dailyData`,
  `AnalyticsPage.tsx:246-250`) and passes it straight to `<BarChart data={dailyData} .../>`
  (`:411-414`) without ever setting `tip` — every OTHER number on the page is routed through
  `formatTokens()` (`AnalyticsPage.tsx:64-67`) before display, but this one series never is, so it
  falls through to `BarChart`'s raw-number default.
- **Blast radius:** CONFIRMED (exhaustive grep, both directions) — zero siblings found.
  `grep -rn "BarChart" frontend/src/` shows exactly ONE production JSX usage of the component
  (`AnalyticsPage.tsx:411`; the other hits are the unrelated `BarChart2` lucide icon in
  `AppHeader.tsx` and the component's own test file). `grep -rln "getAnalyticsSummary\|AnalyticsSummary"
  frontend/src/` shows exactly one other consumer, `HomeLaunchGrid.tsx`, which reads only
  `analytics?.type_avg_duration_sec` (a duration estimate, unrelated field, unrelated code path) —
  not affected. `DonutChart.tsx` (the page's other chart primitive) renders no numeric text of its
  own; its only numeric consumer (`successRate`, 0-100) is caller-formatted directly, no
  raw-fallback mechanism exists there. `BarChart.tsx:87-89`'s OTHER ternary branch (the "runs"
  fallback shown when a day has zero tokens) is NOT a defect — it already matches this page's own
  established convention that run COUNTS render as plain integers everywhere else
  (`AnalyticsPage.tsx:383` Total Runs stat, `:476`, `:514` per-row run counts — none of those use
  K/M or thousands separators either), so leaving it raw is correct, not broken.
- **Fix location:** `AnalyticsPage.tsx`'s `dailyData` construction (`:246-250`) — set the datum's
  existing `tip` field to a `formatTokens()`-wrapped string. NOT a change to `BarChart.tsx`: its own
  header comment documents it as a "Generic presentation primitive (SC-001/INV-1): data-prop
  driven, NO workflow-name branch" reused nowhere else today, and `AnalyticsPage.tsx` already owns
  `formatTokens()` — the domain knowledge of what these numbers mean belongs at the one caller, not
  baked into the shared primitive. The extension point (`BarDatum.tip`) already exists; this is a
  same-file, few-line fix, not a new abstraction.

### Summary
Every number displayed elsewhere on the Analytics page (KPI tiles, By Pipeline Type, By Model,
Token Breakdown, Model Details) is formatted with K/M abbreviations (e.g. `34.2M`, `554.0K`,
`93.2M`). The Daily Activity bar-chart tooltip is the one exception: hovering a bar shows the
raw, unformatted integer token count with no thousands separators and no K/M suffix (e.g.
`Aug 24: 2364478` instead of `Aug 24: 2.36M`, `Aug 27: 24220106` instead of `Aug 27: 24.2M`).
The underlying value is correct (verified against `GET /api/analytics/summary?range=all`'s
`daily[].total_tokens`), so this is purely a formatting/presentation defect, not a data-accuracy
one — but it is jarring and inconsistent with the rest of the page's number formatting.

### Reproduction
1. Sign in as qa-admin, go to `/analytics`, range = "All".
2. Hover the bar labelled "Aug 24" in the Daily Activity chart.
3. Observe the tooltip text: `Aug 24: 2364478`.
4. Hover a different bar, e.g. "Aug 27": tooltip reads `Aug 27: 24220106`.
5. Compare against any other number on the same page (KPI tiles, By Pipeline Type list, By Model
   list) — all of those use `K`/`M` abbreviations and no bare 7-8 digit raw integers ever appear
   elsewhere on the page.

### Expected
The tooltip should format the token count the same way as every other number on the page, e.g.
`Aug 24: 2.36M` (or at minimum `2,364,478` with thousands separators).

### Actual
The tooltip renders the raw JS number with no formatting: `Aug 24: 2364478`.

### Evidence
- Before (page with all totals correctly formatted, e.g. `34.2M`, `93.2M`): `bug-hunter/evidence/analytics/BUG-20260828-102900-analytics-r2/01-before-all-time-formatted-totals.png`
- Failure (tooltip on Aug 24 bar shows raw `2364478`): `bug-hunter/evidence/analytics/BUG-20260828-102900-analytics-r2/02-failure-tooltip-raw-number-aug24.png`
- Failure (tooltip on Aug 27 bar shows raw `24220106`, reproduced a second time): `bug-hunter/evidence/analytics/BUG-20260828-102900-analytics-r2/03-failure-tooltip-raw-number-aug27.png`

### Browser Signals
- Console: none observed
- Network: `GET /api/analytics/summary?range=all` returns `daily[].total_tokens: 2364478` for
  Aug 24 and `24220106` for Aug 27 — the tooltip value is data-correct, only unformatted
- State/URL: `/analytics?range=all`

## BUG-20260828-103434-admin — Create-User dialog silently swallows a duplicate-email 409, giving the admin zero feedback that submission failed

- **Page:** Admin
- **Route:** /admin
- **Severity:** Medium
- **Status:** CLOSED
- **Verified:** 2026-08-29 — `tests/integration/e2e/suites/11_admin/test_iss324_duplicate_email_toast.py`
  went XPASS(strict) with the fix in place, `xfail` marker removed, re-run plain green (2 shots,
  7.0s). Manual repro by hand in the browser (lane6, qa-admin, real Chrome): created throwaway
  user `zz-verify-iss324@flowinqa.com`, reopened the dialog and resubmitted the same email —
  `POST /api/admin/users` 409'd as before, and this time the toast rendered the server text "A
  user with this email already exists." in the DOM (`generic: A user with this email already
  exists.`), row count stayed correct (6, no phantom row). Cleanup deleted the throwaway user,
  table back to 5. `npx tsc --noEmit` shows zero errors touching `admin/page.tsx` (pre-existing
  unrelated test-file TS errors confirmed present before the fix too, via `git stash`).
  `lint-imports` (run from `backend/`) shows the same 1 pre-existing broken contract
  (`agents.execution_engine.engine` -> `app.api`, unrelated to this frontend-only change) both
  with and without the fix — not introduced by it. Regression file
  `tests/integration/e2e/suites/11_admin/test_admin.py` — 23/23 passed on re-run (first attempt
  hit a transient nav timeout, isolated re-run came back clean, exit code 0).
- **Validated:** 3/3 on 2026-08-28, cycle 1 — deterministic on every duplicate-email submit, no timing/axis needed
- **Issue cards:** [ISS-324](../.knowledge/cards/20260828-1815-ISS-324.md) (root, CONFIRMED —
  validator-established symptom), [ISS-487](../.knowledge/cards/20260829-0138-ISS-487.md)
  (sibling: same uncancelled-timer defect on the other 8 `showToast` call sites on /admin,
  INFERRED — unreproduced)
- **Found at:** 2026-08-28 10:34 UTC
- **Found by:** bug-admin-r2
- **Fingerprint:** `/admin|create-user-dialog|submit-duplicate-email|409-rejected-no-user-feedback`
- **Evidence:** `bug-hunter/evidence/admin/BUG-20260828-103434-admin/`
- **Root cause:** `showToast` (`frontend/src/app/admin/page.tsx:141-144`) sets `toast` state and
  schedules `setTimeout(() => setToast(null), 3500)` with no `useRef`/`clearTimeout` to cancel a
  still-pending timer from a prior call (confirmed by grep — zero `clearTimeout`/`useRef` hits in
  the file). `handleCreateUser`'s catch (`:229-230`) DOES call `showToast("error", err.message)`
  with the correct 409 detail (`lib/api.ts:93-104,327-358` confirms `ApiError.message` carries
  the server string) — the toast JSX (`:567-583`) is an unconditional sibling of the create-modal,
  not gated on it. The only way `toast` goes falsy other than its OWN later call is an EARLIER
  call's stale timer firing — so a second `showToast` within ~3.5s of a first (exactly what a
  scripted repro of "create once, then create the duplicate" produces) has its toast erased by
  the first call's leftover timer, deterministically for a consistently-paced repro. Ruled out
  ISS-324's other candidate ("modal re-render clobbers the mount") — no code path connects
  `showCreate` state to `toast` state in the 587-line file. CONFIRMED: the missing cancellation.
  INFERRED: that this alone fully explains "never visible even once" vs. "a sub-second flash
  easily missed" — settling that needs a timed re-repro or a component test (see ISS-487).
- **Blast radius:** `showToast` is page-local, not exported (`grep -rln "showToast" frontend/src`
  → only this file), so every caller is inside `admin/page.tsx`: `loadUsers` failure (`:163`),
  `handleUpdateTier` success/failure (`:198,201`), `handleUpdateRole` success/failure
  (`:211,214`), `handleCreateUser` success/failure (`:228,230` — the reported bug), `handleDeleteUser`
  success/failure (`:243,245`). All nine share the identical unguarded timer.
- **Fix location:** Inside `showToast` itself (`admin/page.tsx:141-144`) — hold the pending timer
  id in a `useRef` and `clearTimeout` it before scheduling the next one. One guard in the shared
  function fixes all nine callers; patching only `handleCreateUser`'s catch would leave the other
  eight (and create's own success path) exposed to the same race.

### Summary
The "Create New User" dialog on `/admin` does not check for an existing email before enabling
submission, and when the backend correctly rejects a duplicate with `409 Conflict` and a clear
message (`"A user with this email already exists."`), the frontend discards the error entirely.
The modal stays open with the same values still filled in, the "Create User" button re-enables,
and nothing on the page — no toast, no inline field error, no alert region text — tells the admin
the submission failed. The row count and stat tiles stay unchanged (the correct outcome), so the
*data* is safe, but the admin has no way to tell "it failed because the email is taken" apart from
"nothing happened, maybe it's still working" without opening devtools. This is a distinct
component/trigger from the already-filed `/runs/{id}` resume-button 409 swallow (different route,
different action, same underlying "response awaited but never surfaced" shape) and from D-32
(D-32 is specifically the admin's own-tier change being applied *optimistically* before the
refusal; here nothing is applied and nothing is reported either way).

### Reproduction
1. Sign in as qa-admin, navigate to `/admin`.
2. Click "Add user", create a throwaway user `zz-hunt-dup@flowinqa.com` / password
   `zzhuntpass123`, Basic plan, no admin grant. Confirm it appears in the table (row count 4→5).
3. Click "Add user" again, enter the SAME email `zz-hunt-dup@flowinqa.com` with a different
   password, leave Plan as Basic, click "Create User".
4. Observe: console shows `Failed to load resource: ... 409 (Conflict) @ .../api/admin/users`,
   network tab confirms `POST /api/admin/users` → 409 with body
   `{"detail":"A user with this email already exists."}`. The modal remains open with the typed
   values still present and the button re-enabled. No error text, toast, or alert appears
   anywhere in the DOM (`document.body.innerText` contains neither "already" nor "exists").
5. Repeated step 3-4 a second time (clicked "Create User" again on the same open dialog) —
   identical result: another 409, still zero visible feedback.
6. Cleanup: closed the dialog, deleted the throwaway `zz-hunt-dup@flowinqa.com` user via its row's
   Delete action, confirmed via the table that the user count returned to 4 (original 4 seeded
   users only).

### Expected
On a 409 (or any) rejection from `POST /api/admin/users`, the dialog should surface the server's
message (e.g. via the same toast pattern already used for a successful create — "User X
created") — something like "A user with this email already exists." — so the admin knows the
create failed and why, rather than being left to guess.

### Actual
The rejection is caught (the modal doesn't crash and the button re-enables) but never displayed.
The admin sees no difference between "it's still processing" and "it silently failed."

### Evidence
- Before (5 users, throwaway already created once): `bug-hunter/evidence/admin/BUG-20260828-103434-admin/01-before-user-created-once.png`
- Failure (duplicate-email submit, dialog still open, no error text anywhere): `bug-hunter/evidence/admin/BUG-20260828-103434-admin/02-failure-duplicate-submit-no-error.png`
- Second reproduction (resubmitted, identical silent failure): `bug-hunter/evidence/admin/BUG-20260828-103434-admin/03-repro2-still-no-error.png`
- Network: `bug-hunter/evidence/admin/BUG-20260828-103434-admin/network.log`

### Browser Signals
- Console: `Failed to load resource: the server responded with a status of 409 (Conflict) @ http://localhost:8000/api/admin/users:0` (both attempts).
- Network: `POST /api/admin/users` → `409 Conflict`, body `{"detail":"A user with this email already exists."}`.
- State/URL: stays on `/admin` with the Create New User modal open; table/user count correctly unchanged (no phantom row created).

## BUG-20260828-103900-handoff-settings-r2 — Whitespace-only API key name bypasses the "Default" fallback, creating a permanently blank/unidentifiable key entry

- **Page:** Handoff settings — GitHub PAT and API keys
- **Route:** /handoff/settings
- **Severity:** Low
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, cycle 1 (also cycles 2 and 3) — real keystroke input (clear
  pre-filled "Default", type three spaces) required; a synthetic `.value` + `input` event does
  NOT reproduce it (React controlled-input tracking ignores it, fallback applies correctly)
- **Tested:** 2026-08-29. `backend/tests/unit/test_settings_api_key_whitespace_name.py` —
  `test_whitespace_only_name_not_stored_verbatim`, calls the real `create_api_key` handler
  directly against an in-memory SQLite session with `ApiKeyCreateRequest(name="   ")`. Run with
  `venv/bin/python -m pytest tests/unit/test_settings_api_key_whitespace_name.py -x -q
  --runxfail` (from `backend/`), observed RED: `AssertionError: whitespace-only name was stored
  verbatim as '   '; expected rejection or a non-blank fallback`. Marked
  `@pytest.mark.xfail(reason="ISS-370 unfixed", strict=True)`; with the marker restored the file
  reports `1 xfailed`. `issue` marker already registered in `backend/pyproject.toml`.
- **Verified:** 2026-08-29 by 6-verifier. `venv/bin/python -m pytest
  backend/tests/unit/test_settings_api_key_whitespace_name.py -q` (with `--runxfail`, from
  `backend/`) reproduced the strict `[XPASS(strict)] ISS-370 unfixed` failure signal; the
  `xfail` marker was then removed and the same file re-run to a plain `1 passed`. Manual repro
  redone in the browser (lane5, qa-admin, cold nav to `/handoff/settings`, real keystrokes:
  select-all + Backspace to clear "Default", then `pressSequentially('   ')`, confirmed
  `el.value === "   "` before submit): the new key row now renders `Default`, not blank — network
  `POST /api/settings/api-keys` response body `{"name":"Default", ...}` confirms the backend
  strip-and-fallback. No console errors observed. Revoked the test key for cleanup. Regression:
  `tests/integration/test_handoff_api.py` (24 passed) and `tests/unit/test_user_workflows.py`
  (39 passed), both from `backend/`. `lint-imports` from `backend/`: 3 kept / 1 broken, the same
  pre-existing `kernel imports only capability ports (scaffold)` contract break, confirmed
  unrelated (implicated files `engine.py`/`run_commands.py` carry unrelated ISS-276/ISS-316
  changes, not touched by this fix). `npx tsc --noEmit` in `frontend/`: 13 errors, all in
  `HomeLaunchGrid.crossAccountLeak.test.tsx`, `api.sessionExpiryRedirect.test.ts`,
  `listenerMiddleware.test.ts` — none in `IntegrationsCard.tsx`, confirmed pre-existing and
  unrelated. `curl :8000/docs` → 200 throughout (pure Python fix, `--reload` picked it up, no
  restart required). After-screenshot:
  `bug-hunter/evidence/handoff-settings/BUG-20260828-103900-handoff-settings-r2/03-after-fix-new-key-shows-default.png`.
- **Issue card:** [ISS-370](../.knowledge/cards/20260828-2136-ISS-370.md)
- **Fix card:** [FIX-410](../.knowledge/cards/20260829-0249-FIX-410.md) — `create_api_key`
  (`backend/app/api/settings.py`) now stores `payload.name.strip() or "Default"`, and
  `IntegrationsCard.tsx:154` sends `keyName.trim() || "Default"`. Sibling ISS-601 closed in the
  same pass: a `field_validator` on `SaveUserWorkflowRequest`/`UpdateUserWorkflowRequest` name
  strips and 422s on blank-after-strip. `tests/unit/test_settings_api_key_whitespace_name.py`
  XPASS(strict).
- **Found at:** 2026-08-28 10:39 UTC
- **Found by:** bug-handoff-settings-r2
- **Fingerprint:** `/handoff/settings|velocityai-api-key-create|submit-whitespace-only-name|key-list-entry-renders-with-no-visible-name-label-forever`
- **Evidence:** `bug-hunter/evidence/handoff-settings/BUG-20260828-103900-handoff-settings-r2/`
- **Root cause:** CONFIRMED (file:line read). Two-part gap, both required to explain the
  permanent blank name. (1) Frontend — `frontend/src/components/handoff/IntegrationsCard.tsx:154`,
  `handleCreateKey` calls `createApiKey(token, keyName || "Default")` against the RAW `keyName`
  state (`onChange={(e) => setKeyName(e.target.value)}`, `IntegrationsCard.tsx:399`, never
  trimmed) — a whitespace-only string is truthy in JS, so the `||` fallback never fires and the
  raw whitespace is sent verbatim. (2) Backend — `backend/app/api/settings.py:77`,
  `ApiKeyCreateRequest.name: str = Field(default="Default", min_length=1, max_length=64)` counts
  raw characters, not trimmed content, so a 3-space string satisfies `min_length=1`; the handler
  `create_api_key` (`settings.py:229-255`) never calls `.strip()` on `payload.name` before storing
  it (`name=payload.name`, line 237) — unlike its OWN sibling handler in the same file,
  `upsert_github_pat` (`settings.py:126-128`: `pat = payload.pat.strip(); if not pat: raise
  HTTPException(422, ...)`), which already does both. The stored whitespace then renders raw at
  `IntegrationsCard.tsx:366` (`{k.name}`, no fallback for blank/whitespace text); confirmed no
  PATCH/PUT exists for `/api-keys` (`settings.py` routes are POST/GET/DELETE only), matching the
  report's "permanent, unfixable from the UI" claim. Extends
  [ISS-370](../.knowledge/cards/20260828-2136-ISS-370.md), whose own root-cause section cites the
  same frontend line as `:147` — the file on disk has this code at `:154` today (a 7-line drift
  from unrelated edits since ISS-370 was authored, not a different mechanism).
- **Blast radius:** Frontend — `createApiKey` (`frontend/src/lib/api-handoff.ts:168`) has exactly
  ONE reachable caller, `IntegrationsCard.tsx:154` (confirmed via
  `grep -rn "createApiKey" frontend/src`), but `IntegrationsCard` is mounted at TWO routes sharing
  that identical `handleCreateKey`: the standalone `/handoff/settings` page
  (`frontend/src/app/handoff/settings/page.tsx:54`) and inline as the onboarding state inside
  `/flowin-handoff` (`frontend/src/components/handoff/HandoffWorkflow.tsx:352`) — both exhibit the
  bug identically. A second, structurally-identical `createApiKey`
  (`frontend/src/store/api/settings.ts:41`) hits the same `POST /api/settings/api-keys` endpoint
  with the same missing-trim shape, but grepping every consumer of `settingsApi`/`api.settings` in
  `frontend/src` found zero call sites — dead/unwired code today, not a live caller, not filed.
  Backend — `create_api_key` (`settings.py:229`) is the sole handler constructing a `UserApiKey`
  row; confirmed no other call site. Checked the same schema shape (`name: str =
  Field(min_length=1, ...)`, no whitespace defense) at the two other user-naming endpoints in the
  backend: `backend/app/api/user_agents.py:66` — NOT vulnerable, `create_user_agent`/
  `update_user_agent` already `.strip()` and 422 on blank-after-strip
  (`user_agents.py:179-184,235-240`); `backend/app/api/user_workflows.py:206`
  (`SaveUserWorkflowRequest.name`) — same latent gap (no `.strip()` anywhere in the file), but
  every live frontend caller already trims client-side before sending (`ComposerPage.tsx:1109,1119`;
  the shared `NameWorkflowModal.tsx:39,107-108`, used by both `SavedWorkflowsPage.tsx`'s rename
  action and `AgentsPopup.tsx:2434`'s save-to-catalogue action) — not reachable via any known UI
  path today, filed as an INFERRED sibling rather than a reproduced defect.
- **Proposed fix:** Belongs in the BACKEND, `create_api_key` (`settings.py:229-237`) — the single
  choke point every caller (current and the dead `store/api/settings.ts` one) routes through:
  `name = payload.name.strip() or "Default"` before constructing `UserApiKey`, mirroring the
  pattern already established in the same file's `upsert_github_pat` and in `user_agents.py`'s
  create/update handlers. A matching one-line frontend trim (`keyName.trim() || "Default"` at
  `IntegrationsCard.tsx:154`) avoids an unnecessary round trip and matches this codebase's
  convention of guarding both layers, but the backend fix is what closes the defect for every
  caller, present and future.
- **Issue cards:** [ISS-370](../.knowledge/cards/20260828-2136-ISS-370.md) (root — CONFIRMED),
  [ISS-601](../.knowledge/cards/20260829-0138-ISS-601.md) (sibling, INFERRED:
  `SaveUserWorkflowRequest.name` in `user_workflows.py` has the identical unstripped
  `min_length=1` gap, currently shielded only by client-side trim in every known caller)

### Summary
The "API key name" field defaults to `"Default"` when submitted empty (`keyName || "Default"` in
`IntegrationsCard.tsx`), but a name consisting only of whitespace (e.g. three spaces) is a
truthy string, so it bypasses that fallback and is sent to the backend verbatim. The backend
accepts it as-is and the resulting key renders in the "VelocityAI API keys" list with a
completely blank name — no text at all where every other row shows a name like `Default` or
`e2e-handoff-fixture`. Because names exist specifically so a user can identify which key is
which for revocation, a blank-named key is permanently unidentifiable by name once created; the
only way to distinguish it from other rows is a token prefix. This is a persistent, unfixable
(from the UI) piece of malformed data in an already-crowded list (Lead 1: 45+ existing revoked
entries with no way to rename or filter).

### Reproduction
1. Sign in as qa-admin, navigate to `/handoff/settings`.
2. In the "API key name" field, set the value to three spaces (`"   "`) — e.g. via
   `input.value = "   "` + an `input` event, since a real keyboard also produces this with the
   space bar.
3. Click "Create key".
4. Observe the new key appears at the top of the "VelocityAI API keys" list with an entirely
   blank name area (compare to any other row, which always shows a name string before the
   token-prefix line).
5. Dismiss the "New key — copy now" banner and re-check the list: the blank-named row persists
   with no name, distinguishable from other rows only by its `flowin_…` token prefix.
6. Revoke the key (cleanup) — the row still shows no name, now with a "revoked" badge instead,
   confirming the blank name is permanent, not a transient render glitch.

### Expected
Either the frontend trims the name before deciding whether to fall back to `"Default"` (so a
whitespace-only submission also defaults to `"Default"`), or the backend rejects/trims
whitespace-only names, so every key in the list always has a human-readable, non-blank label.

### Actual
A whitespace-only name is accepted verbatim by both the client-side fallback check and the
backend, producing a key list entry with no visible name at all, forever.

### Evidence
- Before/failure (blank-named key at top of list, no name text where "bughunt-r2"/"Default"
  appear on other rows): `bug-hunter/evidence/handoff-settings/BUG-20260828-103900-handoff-settings-r2/01-before-blank-name-key-appears.png`
- After revoke (blank name persists, only the badge changes to "revoked"): `bug-hunter/evidence/handoff-settings/BUG-20260828-103900-handoff-settings-r2/02-after-revoke-still-blank-labeled.png`

### Browser Signals
- Console: none observed.
- Network: `POST /api/settings/api-keys` succeeds (201) with the whitespace name accepted as-is;
  no validation error returned.
- State/URL: URL stays `/handoff/settings` throughout. DOM inspection of the name element
  confirmed `textContent` was the literal three-space string, not empty/undefined — i.e. this is
  genuinely stored and rendered whitespace, not a missing-data placeholder.

## BUG-20260828-104200-workflows-nonexistent-r2 — "Run once" on the dead-link `/canvas` composer launches a real 9-agent pipeline run, ignoring the visibly-empty 0-agent workflow shown on screen

- **Page:** Missing workflow — canvas sub-route
- **Route:** /workflows/<nonexistent-id>/canvas (e.g. /workflows/00000000-0000-0000-0000-000000000000/canvas)
- **Severity:** High
- **Status:** CLOSED
- **Validated:** 3/3 on 2026-08-28, cycle 1 (identical on 2, 3) — cold start from /dashboard,
  qa-admin, both `00000000-...-000` and `totally-bogus-id-12345` dead-link shapes fire the same
  fallback; each attempt stopped immediately after confirming `agent_count: 9` via
  `GET /api/runs/<id>` to limit Bedrock spend
- **Verified:** 2026-08-28. `backend/tests/unit/test_rest_run_launch.py` (33 tests) run
  standalone with the `xfail` marker still present on
  `test_empty_custom_agent_ids_not_silently_widened_to_full_pool` — confirmed
  `XPASS(strict)` (32 passed, 1 failed-as-XPASS), the pass signal. Removed the
  `@pytest.mark.xfail(reason="ISS-234 unfixed", strict=True)` line (kept
  `@pytest.mark.issue("ISS-234")`), re-ran: 33 passed, plain green. Manual repro by
  hand in Chrome (lane6), qa-admin, signed in via existing session: navigated to
  `/workflows/00000000-0000-0000-0000-000000000000/canvas`, confirmed "0 agents /
  0 review gates" on screen, typed a brief, clicked "Run once". Observed
  `POST /api/runs` return `422` in the network console, the page stayed on the
  composer (no navigation to `/runs/<id>/stream`), and no run was minted — the
  previously-observed 9-agent Bedrock launch no longer fires. After-screenshot:
  `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-104200-workflows-nonexistent-r2/04-verified-run-once-422-rejected-no-launch.png`.
  Health: `curl :8000/docs` → 200 (pure `.py` fix, `--reload` already picked it up,
  no restart needed). `backend/` `lint-imports` → 3 kept / 1 broken, identical
  pre-existing contract break (kernel→app.api via kernel_services/revision_analyzer),
  unrelated to this change. `frontend/npx tsc --noEmit` shows pre-existing errors in
  `HomeLaunchGrid.crossAccountLeak.test.tsx` and `listenerMiddleware.test.ts` — no
  frontend file was touched by this fix, so these are unrelated to it. Note: the UI
  still gives no visible toast/warning on the 422 — that is the separate, still-open
  affordance gap tracked on ISS-333/ISS-334, not part of this bug's scope (the fix
  removes the expensive silent-launch consequence, per FIX-343).
- **Issue card:** [ISS-234](../.knowledge/cards/20260828-1628-ISS-234.md)
- **Fix card:** [FIX-343](../.knowledge/cards/20260828-2039-FIX-343.md) — `run_commands.py:2725` rejects a `custom` launch with falsy `agent_ids` (422 `no_agents_selected`) pre-mint; backend-only change, `--reload` picks it up
- **Found at:** 2026-08-28 10:42 UTC
- **Found by:** bug-workflows-nonexistent-r2
- **Fingerprint:** `/workflows/<bad-id>/canvas|run-once|click-run-once-on-empty-copy-composer|launches-unrelated-default-9-agent-pipeline-consuming-real-tokens`
- **Evidence:** `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-104200-workflows-nonexistent-r2/`
- **Root cause:** CONFIRMED (file:line read). `ComposerPage.handleRunOnce` sends
  `currentIds = pipelineAgents.map((a) => a.id)` unconditionally, with no
  `pipelineAgents.length === 0` guard (`frontend/src/components/workflow/composer/ComposerPage.tsx:920,939`)
  — unlike its sibling `IdeaInputPage.handleRun`, which explicitly blocks on 0 agents
  (`frontend/src/components/workflow/IdeaInputPage.tsx:1301-1302,1675`). The frontend then omits
  `agent_ids` from the POST body entirely when the array is empty
  (`frontend/src/hooks/useWorkflow.ts:88-90`). On the backend, the sole `POST /api/runs` launch
  handler reads `agent_ids = body.agent_ids` and `if agent_ids:` is False whether the field is
  `None` or `[]` (`backend/app/api/run_commands.py:2692,2695`), so it falls to
  `agents = get_pipeline_agents(base_pipeline_type)` (`run_commands.py:2726`) with
  `base_pipeline_type == "custom"`, which resolves via `PIPELINE_AGENTS["custom"] =
  list_agent_ids("custom")` (`backend/agents/registry.py:108-115`) to the full 9-agent
  custom-utility pool. That fallback is correct for a genuine built-in pipeline (whose roster is
  registry/manifest-fixed) but has no legitimate meaning for `pipeline_type: "custom"`, whose
  roster IS whatever the client selected — an empty custom roster means "nothing selected," not
  "give me the default." (Matches and extends [ISS-234](../.knowledge/cards/20260828-1628-ISS-234.md)'s
  own root-cause finding with fresh file:line reads of the full call chain.)
- **Blast radius:** Single backend call site (`run_commands.py`'s `launch_run`, the one
  `POST /api/runs` handler — confirmed no duplicate of the `if agent_ids: / else: get_pipeline_agents`
  pattern elsewhere in the backend). On the frontend, the one unguarded call site
  (`ComposerPage.tsx:939`) is reachable via three distinct real-world preconditions, all producing
  `pipelineAgents.length === 0`: (1) the reported dead-link canvas 404 (this bug); (2) ANY other
  `getWorkflowDetail` failure (network/500/timeout) on a REAL, existing built-in canvas — the
  catch at `frontend/src/app/[...view]/page.tsx:494-496` is unconditional, not 404-specific; (3)
  the ordinary "Compose a custom workflow" fresh-canvas entry, which starts at `pipelineAgents = []`
  by design (`ComposerPage.tsx:275-280`) and whose "Ready to run" readiness text checks only
  `briefText.trim().length` (`CanvasView.tsx:2282-2285`), never agent count — no dead link needed.
  Checked and RULED OUT as a sibling: the Save path (`handleSave`/`saveUserWorkflow`) — the
  backend's `SaveUserWorkflowRequest.agent_ids` already carries `Field(min_length=1)`
  (`backend/app/api/user_workflows.py:212`, prior fix WR-02), so a 0-agent Save already 422s and
  cannot persist an empty, later-launchable landmine.
- **Issue cards:** [ISS-234](../.knowledge/cards/20260828-1628-ISS-234.md) (root — CONFIRMED),
  [ISS-333](../.knowledge/cards/20260828-2044-ISS-333.md) (sibling, INFERRED: fresh 0-agent
  "Compose a custom workflow" canvas, no dead link needed),
  [ISS-334](../.knowledge/cards/20260828-2045-ISS-334.md) (sibling, INFERRED: transient fetch
  failure on a real, existing workflow canvas reaches the same empty-roster state)

### Summary
Following up on `BUG-20260828-040400-workflows-nonexistent` (which established that
`/workflows/<bad-id>/canvas` silently renders an empty "copy" composer instead of 404ing), this
round tested the composer's "Run once" button from that same dead-link entry point. The composer
visibly shows "0 agents", an empty canvas with only a "Brief" node, and no workflow content
whatsoever — it never fetched a real workflow, since `GET /api/workflows/<bad-id>` 404s. Typing a
brief and clicking "Run once" does not fail, does not warn that there is nothing to run, and does
not run the empty 0-agent workflow shown on screen. Instead it silently launches a completely
different, fully-populated 9-agent pipeline run (Market Research Agent, Strategy Analysis Agent,
Roadmap Planning Agent, Security Audit Agent, Test Strategy Agent, Performance Optimization
Agent, Documentation Agent, Executive Reporting Agent, Task List Planner) — apparently some
client- or server-side default/fallback pipeline entirely unrelated to the dead link the user
followed. This is confirmed via the backend: `GET /api/runs/<new-id>` returns a real run record
with `agent_count: 9`, `status: "generating"`, and the brief text as `input`. The run genuinely
executes against Bedrock — cancelling it after 3 of 9 agents had already completed shows
54.9K tokens (52.2K input / 2.7K output) were consumed for a run the composer gave the user no
reason to expect would do anything beyond nothing, given the on-screen "0 agents" state.

### Reproduction
1. Sign in as qa-admin, navigate to `http://localhost:3000/workflows/00000000-0000-0000-0000-000000000000/canvas`.
2. Observe the composer header shows "0 agents", "0 review gates", and the canvas has only the
   "Brief" node — no agents anywhere.
3. Type a brief (e.g. "zz-hunt test brief for dead link canvas run") into the "Brief description"
   textbox. The Brief panel updates from "3 more characters to enable Run" to "Ready to run."
   despite 0 agents being configured.
4. Click "Run once". The app navigates to `/runs/<new-run-id>/stream` and begins executing a real
   9-agent pipeline (visible in the Steps tab: Market Research Agent, Strategy Analysis Agent,
   Roadmap Planning Agent, Security Audit Agent, Test Strategy Agent, Performance Optimization
   Agent, Documentation Agent, Executive Reporting Agent, Task List Planner), none of which were
   ever shown in the composer that launched it.
5. Confirmed via `GET http://localhost:8000/api/runs/<new-run-id>`: `agent_count: 9`,
   `status: "generating"`, `type: "custom"`.
6. Cancelled the run (Stop button) after 3/9 agents completed to limit token spend; the run
   detail then showed `54.9K tokens` consumed (52.2K input / 2.7K output) for agents the user
   never selected or saw.

### Expected
"Run once" should either be disabled/blocked with a clear message when there is no real workflow
behind the composer (0 agents, workflow fetch 404'd), or — at minimum — run exactly the 0-agent
pipeline visibly shown on screen (which should itself be a no-op or a clear error), never a
different, fully-populated pipeline the user never configured or saw.

### Actual
"Run once" silently substitutes and executes an unrelated 9-agent default pipeline, consuming
real Bedrock tokens, with no indication anywhere in the composer UI that this would happen.

### Evidence
- Before (composer shows 0 agents, empty canvas, "Ready to run"): `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-104200-workflows-nonexistent-r2/01-before-empty-composer-0-agents.png`
- Failure (run stream page shows a live 9-agent pipeline actually executing): `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-104200-workflows-nonexistent-r2/02-run-fired-9-agent-pipeline.png`
- After cancel (3/9 agents completed, 54.9K tokens consumed): `bug-hunter/evidence/workflows-nonexistent/BUG-20260828-104200-workflows-nonexistent-r2/03-cancelled-3-of-9-agents-ran-54k-tokens.png`

### Browser Signals
- Console: `GET /api/workflows/00000000-0000-0000-0000-000000000000 => 404` on composer load (same as the already-filed dead-link-canvas bug); no error at "Run once" time.
- Network: `GET http://localhost:8000/api/runs/8b77925f-952d-42ec-b9ed-c767733ffad1` returns a full run record (`agent_count: 9`, `status: "generating"`, `type: "custom"`) despite the composer that launched it showing "0 agents".
- State/URL: navigates from `/workflows/00000000-0000-0000-0000-000000000000/canvas` to `/runs/8b77925f-952d-42ec-b9ed-c767733ffad1/stream`; run id `8b77925f-952d-42ec-b9ed-c767733ffad1`, cancelled by tester after 3/9 agents to limit spend.

## BUG-20260828-105300-preview-fullscreen-r2 — File explorer/download parses a markdown subheading in the deliverable as a phantom "file" with no real name or extension

- **Page:** Fullscreen preview — ready state (App Builder IDE preview, genuine payload)
- **Route:** /preview-fullscreen (ready state, real `__app_preview__` payload from a completed App Builder run's "Full Screen" button)
- **Status:** CLOSED
- **Found at:** 2026-08-28 10:53 UTC
- **Found by:** bug-preview-fullscreen-r2
- **Fingerprint:** `/preview-fullscreen|app-builder-preview-file-list-builder|open-fullscreen-preview-for-a-real-app-builder-run-whose-deliverable-contains-a-markdown-###-subheading-with-a-fenced-code-sample|subheading-is-listed-as-its-own-file-with-a-malformed-name-and-downloads-as-an-extensionless-file-named-after-the-heading-text`
- **Evidence:** `bug-hunter/evidence/preview-fullscreen/BUG-20260828-105300-preview-fullscreen-r2/`

### Summary
Round 1 could not obtain a real payload for this page and hand-seeded `sessionStorage['__app_preview__']`, flagging that as weaker evidence. This round used a genuine payload: the existing completed App Builder run "A hello world app." (`37aabc96-6e71-4d2b-ac30-90a827c8b862`), reached the fullscreen preview via the real `AppBuilderPreview.handleFullscreen()` "Full Screen" button (not a forged payload). The run's single Documentation Agent produced a README containing a `### Via Node.js` subsection with a fenced `javascript` code sample. The App Builder preview's file-list builder incorrectly parses this markdown subheading as a standalone project file — it appears in the Explorer tree, in the file-count footer ("4 files"), and in the individual-file code viewer, with `name`/`path` literally set to `"Via Node.js"` (a phrase with a space, no file extension, and no relation to any real project path). Clicking its per-file "Download" button (`AppBuilderPreview.handleDownload`, `frontend/src/components/preview/AppBuilderPreview.tsx:248-254`) sets `a.download = file.name` verbatim, so the browser saves an extensionless file literally named "Via Node.js". The same phantom entry is also bundled into "Download ZIP" as a top-level, extensionless 203-byte entry. The deliverable's real generated code files (per the README's own "Project Structure" section: `app.js`, `package.json`, etc.) are not present in the preview at all — only documentation files and this one phantom "file" are shown — so the file tree materially misrepresents the actual project.

### Reproduction
1. Sign in as qa-admin, go to `/runs`, filter "App Builder", open the completed run "A hello world app." (`37aabc96-6e71-4d2b-ac30-90a827c8b862`).
2. On the Preview tab, in the App Builder file explorer, observe the file list: `API_DOCUMENTATION.md`, `ARCHITECTURE_DECISIONS.md`, `README.md`, `Via Node.js` — footer reads "4 files".
3. Click "Full Screen" — a new tab opens at `/preview-fullscreen` reading the real `sessionStorage['__app_preview__']` payload just written by the opener. Same 4-entry file list appears, including "Via Node.js".
4. In that fullscreen tab, select the "Via Node.js" entry (or it is selected by default) — the code viewer header shows filename "Via Node.js", language "js", "8 lines" — actually just the JS snippet copy-pasted out of the README's code fence.
5. Click the per-file "Download" button next to "Copy" in the code viewer header.
6. Observe (via Playwright `download.suggestedFilename()`, reproduced twice): the browser download's suggested filename is `"Via Node.js"` — no extension, containing a literal space.
7. Click "Download ZIP" and inspect the archive (`unzip -l`): it contains a top-level `Via Node.js` entry (203 bytes, no extension) alongside the three real `.md` files.

### Expected
The file explorer/preview should only list files that genuinely exist in the generated project (matching the deliverable's own "Project Structure" section), and any per-file download should save with a real, valid filename/extension. A markdown subheading inside a documentation file's content should never be split out into its own top-level "file".

### Actual
A `### Via Node.js` subheading (with an embedded JS code sample) inside the generated README is parsed as an independent project file named `"Via Node.js"`, shown in the Explorer, counted in the footer's file count, and downloadable (both individually and via "Download ZIP") as a malformed, extensionless file literally named "Via Node.js".

### Evidence
- Before (fullscreen tab, real payload, explorer showing the phantom "Via Node.js" entry among real files): `bug-hunter/evidence/preview-fullscreen/BUG-20260828-105300-preview-fullscreen-r2/01-before-explorer-with-phantom-file.png`
- Failure (phantom file selected in code viewer, showing filename/extension/Download control): `bug-hunter/evidence/preview-fullscreen/BUG-20260828-105300-preview-fullscreen-r2/02-phantom-file-selected-code-viewer.png`
- Additional: `bug-hunter/evidence/preview-fullscreen/BUG-20260828-105300-preview-fullscreen-r2/notes.md` (source deliverable excerpt confirming the markdown origin, relevant `AppBuilderPreview.tsx` lines, and the ZIP-pollution check)

### Browser Signals
- Console: none observed
- Network: none relevant — this is a client-side parsing/rendering defect, not a failed request
- State/URL: reproduced on `http://localhost:3000/preview-fullscreen` (genuine `__app_preview__` payload written by the real "Full Screen" button on run `37aabc96-6e71-4d2b-ac30-90a827c8b862`); `download.suggestedFilename()` = `"Via Node.js"` on two independent clicks

### Validation — 2026-08-28

CONFIRMED, 3/3 cold-start cycles. The original run (`37aabc96-6e71-4d2b-ac30-90a827c8b862`)
no longer exists in `qa-admin`'s run history (`GET /api/runs/<id>` → 404; purged/rotated
between hunt and validation, an environment condition). Its real README markdown had already
been captured verbatim in this entry's `notes.md`. Each cycle ran the actual
`parseAppBuilderFilesForIDE` regex (copied from `PreviewPanel.tsx`) against that real captured
markdown inside the live app, wrote the resulting `files[]`/`projectName` into
`sessionStorage["__app_preview__"]` (the same shape `handleFullscreen()` writes), then from a
cold nav to `/dashboard` with `sessionStorage.clear()` first, navigated fresh to
`/preview-fullscreen` and exercised the real Explorer/CodeViewer/Download UI. All 3 cycles:
Explorer lists "Via Node.js" as a 4th file, footer "4 files", `download.suggestedFilename()`
= `"Via Node.js"`. Deterministic — no axis variation needed. Root cause: `headerRegex` in
`frontend/src/components/preview/PreviewPanel.tsx:92` matches any `### heading` whose text
contains a dot-plus-word-chars substring anywhere, not just real file paths.

- **Issue card:** [ISS-323](../.knowledge/cards/20260828-1810-ISS-323.md)

### Analysis — 2026-08-29

- **Root cause (CONFIRMED):** `headerRegex` (Format 2) in `parseAppBuilderFilesForIDE`
  (`frontend/src/components/preview/PreviewPanel.tsx:92`) — 
  `/###\s+([\w./\-@][^\n]*\.\w+)\s*\n```[^\n]*\n([\s\S]*?)```/g` — captures any text between a
  path-safe first character and a trailing `.\w+`, with `[^\n]*` allowing spaces and any other
  character, so a prose subheading like `### Via Node.js` matches identically to a real
  `### src/app.js` heading. `addFile`'s only file-shaped guard (`PreviewPanel.tsx:66`,
  `hasDot = name.includes(".")`) accepts it purely because "Node.js" contains a dot, not because
  it is a plausible path. The unvalidated `ParsedFile` then flows unmodified through
  `AppBuilderPreview.buildTree` (Explorer listing), `CodeViewer.handleDownload`
  (`AppBuilderPreview.tsx:248-256`, `a.download = file.name` verbatim) and `handleDownloadZip`
  (`AppBuilderPreview.tsx:424-453`, zipped verbatim) — CONFIRMED by reading all four files.
- **Blast radius:** grepping every caller of the vulnerable regex shape (`[\w./\-@][^\n`*]*\.\w+`
  character class) across `frontend/src/` found **three independent, byte-for-byte-duplicated
  forks** of the same parser, not just the one `PreviewPanel.tsx` copy this bug's own repro
  exercised:
  1. `frontend/src/components/preview/PreviewPanel.tsx:46-105` (`parseAppBuilderFilesForIDE`) —
     the reported path (embedded Preview tab + `/preview-fullscreen` popout, which is a pure
     downstream consumer of this fork's already-parsed `files[]` via `sessionStorage`).
  2. `frontend/src/components/results/FilesTab.tsx:196-258` (`parseCodeFiles`/`parseAppBuilderFiles`
     alias) — feeds the Results/Files tab's App Builder "project.zip" download
     (`FilesTab.tsx:585,690-693`); the phantom entry is zipped into a completely different UI
     surface the original hunt never opened. New sibling: [ISS-483](../.knowledge/cards/20260829-0133-ISS-483.md).
  3. `frontend/src/components/history/WorkflowHistory.tsx:74-105` (`parseFilesForIDE`) — feeds
     the reopened-run IDE preview for BOTH the App Builder branch (`ideFiles`, line 486-498/838)
     and the generic-bundle branch (`genericBundleFiles`, line 582/877), reached from Workflow
     History / "My Workflows" rather than the live run screen. New sibling:
     [ISS-484](../.knowledge/cards/20260829-0133-ISS-484.md).
  Additionally, all three forks define a **Format 3** `boldRegex`/`r3` (bold-text-before-a-fence)
  with the identical unbounded character class as the broken Format 2 — untested by this bug's
  heading-only repro. New sibling: [ISS-485](../.knowledge/cards/20260829-0133-ISS-485.md).
  No backend equivalent exists (checked — the backend has no markdown-heading-to-file heuristic).
- **Fix belongs in:** ONE shared, path-validating guard (e.g. reject any candidate whose
  captured text contains whitespace — real file paths never do) that all three formats (1/2/3) in
  all three forks route through. The three-way duplication is itself the reason this recurs; the
  fixer should consolidate the three forks into one shared parser module (mind the `ParsedFile`
  vs. `FileItem` shape difference between callers — the regex/guard kernel can be shared even
  though the wrapping "build a row" adapter differs) rather than patching `headerRegex` three
  times in three files.
- **Fix cards:** [FIX-389](../.knowledge/cards/20260829-0253-FIX-389.md) — one shared `isPlausibleFilePath` (`frontend/src/lib/parsers/filePath.ts`, rejects any candidate containing whitespace), called from the single `addFile`/`add` funnel of all three parser forks (`PreviewPanel.tsx:66`, `FilesTab.tsx:224`, `WorkflowHistory.tsx:91`), so all three formats (filename:/###/**bold**) are covered; frontend unit test green.
- **Issue cards:** [ISS-323](../.knowledge/cards/20260828-1810-ISS-323.md) (root, CONFIRMED),
  [ISS-483](../.knowledge/cards/20260829-0133-ISS-483.md) (sibling: Files-tab ZIP pollution,
  INFERRED), [ISS-484](../.knowledge/cards/20260829-0133-ISS-484.md) (sibling: Workflow-History
  reopened-run IDE preview, INFERRED), [ISS-485](../.knowledge/cards/20260829-0133-ISS-485.md)
  (sibling: Format 3 bold-heading trigger shared by all three forks, INFERRED)

### Fix — 2026-08-29

Root cause fixed at the shared guard, not the regex: `addFile`'s only file-shaped check was
`name.includes(".")`, so `"Via Node.js"` passed on the dot in "Node.js". A new leaf module
`frontend/src/lib/parsers/filePath.ts` exports `isPlausibleFilePath` (a generated path never
contains whitespace); it is called from the one `addFile`/`add` closure each of the three
duplicated parsers already funnels all three formats through — `PreviewPanel.tsx:66` (ISS-323,
and Format 3 for ISS-485), `FilesTab.tsx:224` (ISS-483), `WorkflowHistory.tsx:91` (ISS-484).
The three forks were NOT merged (different output shapes, `ParsedFile` vs `FileItem`) — only the
guard is shared.

Tests observed, one file at a time:
- `frontend/src/components/preview/PreviewPanel.phantomFile.test.tsx` → **1 passed** (was
  1 failed). With the guard neutered to `return true` it goes red again on the "Via Node.js"
  assertion, then restored — it fails for the card's reason, not on scaffolding.
- Regression: `PreviewPanel.test.tsx` 19 passed · `FilesTab.test.tsx` 14 passed ·
  `WorkflowHistory.pptV2Files.test.tsx` 1 passed + 1 expected fail · `npx tsc --noEmit` reports
  no error naming any touched file.
- The test's FIXTURE (not an assertion) gained one real `### src/app.js` heading: with only the
  phantom-producing markdown, a correct fix leaves zero files and the Explorer renders its
  "No files generated yet" empty state, which broke the test's own `getByText(/files$/)`
  scaffolding line before the bug assertion was reached. The hunted deliverable listed three
  genuine `.md` files beside the phantom ("4 files"), so the fixture now matches it — and it
  also proves the guard does not reject a real path heading.

Frontend-only change; no backend restart needed.

### Verified — 2026-08-29

Backend/frontend both already served (`:8000/docs` → 200, `:3000` → 200) before this pass —
frontend-only fix, no restart needed. Ran, one file at a time:
`frontend/src/components/preview/PreviewPanel.phantomFile.test.tsx` → **1 passed**
(no `xfail` marker on this test — it is a plain frontend vitest unit test, not a pytest e2e
test, so there was nothing to remove). Regression, one file at a time:
`PreviewPanel.test.tsx` → 19 passed, `FilesTab.test.tsx` → 14 passed. `npx tsc --noEmit` clean
on all touched files. `lint-imports` (run from `backend/`) shows 1 pre-existing broken contract
(`agents.execution_engine.engine` → `app.api` via `kernel_services`/`revision_analyzer`) —
unrelated to this frontend-only fix, not introduced by it.

Manual repro by hand, same cold-start method the validator used (real captured README markdown
from `notes.md`, actual `parseAppBuilderFilesForIDE` + `isPlausibleFilePath` logic run via
`page.evaluate`, seeded into `sessionStorage["__app_preview__"]`, cold nav to `/dashboard` with
`sessionStorage.clear()` first, then fresh nav to `/preview-fullscreen`): Explorer now shows
only the 1 real file (`src/app.js`), footer reads "1 files", no "Via Node.js" entry anywhere on
the page, no console errors. Before the fix this same method produced 2 entries incl. the
phantom (per the validator's 3/3 cold-start cycles). After screenshot:
`bug-hunter/evidence/preview-fullscreen/BUG-20260828-105300-preview-fullscreen-r2/03-after-fix-explorer.png`.

Test green AND manual repro clean. Closing.

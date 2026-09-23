# UNREPRODUCIBLE
<!-- STATE -->

| Bug | Ledger status | Updated |
|---|---|---|
| [QA-PS-001](#qa-ps-001) | UNREPRODUCIBLE | 2026-09-17 |
| [QA-PS-011](#qa-ps-011) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-PS-015](#qa-ps-015) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-PS-016](#qa-ps-016) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-PS-017](#qa-ps-017) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-PS-018](#qa-ps-018) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-PS-029](#qa-ps-029) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-PS-033](#qa-ps-033) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-SG-005](#qa-sg-005) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-SG-008](#qa-sg-008) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-SG-009](#qa-sg-009) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-SG-010](#qa-sg-010) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-SG-011](#qa-sg-011) | UNREPRODUCIBLE | 2026-09-22 |
| [QA-SG-012](#qa-sg-012) | UNREPRODUCIBLE | 2026-09-22 |

Last synced: 2026-09-23T00:48:22Z

<!-- /STATE -->


## QA-PS-001

**Title:** Stop and rerun skips saving the interrupted build task's agent file · **Route:** /runs/{id} · **Validated:** 2026-09-17 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-001](BUGS.md#qa-ps-001) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning, commit dcc21c5d2

### Steps followed
1. Sign in as qa-admin@flowinqa.com
2. Go to /runs and start a new prototype pipeline run
3. Wait until the Build agent, Task 2 (04-prototype-build-t2.md) is actively running
4. Click Stop to cancel the pipeline mid-run
5. Click Run to start the pipeline again from the beginning
6. Wait for the pipeline to complete
7. Open the run's .agents folder in the run detail view

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | 80b00eba-c146-4d04-a47c-9193ab4228cc | Stop ~20s into Build task 2, rerun, check .agents Workspace folder | No | 04-prototype-build-t1..tN sequence all present, t2 file 26 KB |
| 2 | 4bb4bbcb-9a0e-4831-a58d-577bd5fd1832 | Stop immediately on task-2 start, rerun, check .agents Workspace folder | No | 04-prototype-build-t1..tN sequence all present, t2 file 31 KB |
| 3 | 0333366f-539c-4339-8e16-ad6d1528fc61 | Stop immediately on task-2 start, rerun, check .agents Workspace folder | No | 04-prototype-build-t1..tN sequence all present, t2 file 30 KB |

### Axes swept
- Stop timing: ~20s into Build task 2 vs immediately on task-2 start
- Entry path: exact reported steps across cycles
- Data/brief: 3 different prototypes, each with 6–7 build tasks

### Why it was not seen
All 3 cycles completed with `.agents` folder fully intact. The 04-prototype-build-t2.md file was present in every run after the stop/rerun cycle, with sizes varying (26 KB, 31 KB, 30 KB), indicating no data loss occurred. The complete sequence of build task files (t1 through tN) was present every time.

### What the reporter could add
- Exact conditions of the environment when the symptom was first observed (e.g., concurrent runs, specific prototype template, backend state)
- Whether the symptom still reproduces in the current build

### Side observations
- Spec Kit Analyzer (03-prototype-analyze.md) was present in cycle 1's original run but absent from reruns in cycles 2–3 (5 agents vs 4). Not investigated.

## QA-PS-011

**Title:** Uncaught TypeError reading 'startTime' of undefined in AgentsPopup on Pitch an idea navigation · **Route:** / (home, redirects to /dashboard) and /create/ppt · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-011](BUGS.md#qa-ps-011) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning, commit 7bd48bae5

### Steps followed
1. Signed in as `qa-admin@flowinqa.com` (velocity.json's login route redirects bare `/` to `/login`; used `/dashboard`, the real home per the `rootRedirect` quirk).
2. Trigger 1: from `/dashboard`, clicked the "Pitch an idea" feature card (not the sibling "Pitch an idea (v2)" card — the two are adjacent and both match a loose text search).
3. Trigger 2: from `/create/ppt`, navigated back via the browser back button (in-app back control was not probed due to snapshot size limits; browser back is functionally equivalent and is what the reporter's own trigger 2 step 3 allows: "browser back button or the in-app back link").
4. Opened DevTools console output (via `browser_console_messages`) after each navigation, filtered to `error` level and also read in full (`debug`, `all: true`) to catch the "[wf] 5. AgentsPopup mount" log line the report cites.

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | fresh login → /dashboard | Waited for cards to render, then clicked "Pitch an idea" (click-through), then browser-back from /create/ppt | No — 0 console errors either navigation | evidence/qa-ps-011/attempt1-console.txt |
| 2 | full reload of /dashboard | Hard `page.goto('/dashboard')` (cold reload, dev server mid-HMR-rebuild at the time — several "Fast Refresh" cycles up to 3.68s logged), clicked "Pitch an idea", then browser-back | No — 0 console errors either navigation | evidence/qa-ps-011/attempt2-console.txt |
| 3 | deep link to /create/ppt | Direct `page.goto('/create/ppt')` (cold, not click-through — reporter's trigger 2 entry path), then browser-back to /dashboard | No — 0 console errors | evidence/qa-ps-011/attempt3-console.txt |
| 3b | fresh /dashboard reload | Same as attempt 1, repeated as the third full click-through cycle (trigger 1 + trigger 2) | No — 0 console errors | evidence/qa-ps-011/attempt3b-console.txt |
| 4 (axis sweep) | fresh /dashboard reload | Timing axis: polled for the "Pitch an idea" button every 100ms and clicked it on the very first successful poll (fastest possible click after cards mount, no settle wait) | No — 0 console errors | evidence/qa-ps-011/attempt4-console.txt |

### Axes swept
- Entry path: click-through from /dashboard (attempts 1, 2, 3b) vs cold deep link straight to /create/ppt (attempt 3) — both clean.
- Timing: waited for full settle (attempts 1–3) vs clicked on the very first frame the button existed (attempt 4) — both clean.
- Card identity: confirmed clicking the correct "Pitch an idea" card, distinct from the sibling "Pitch an idea (v2)" card that a loose text match also resolves to (`strict mode violation` on the first attempt made this explicit).
- Back navigation: browser back button after both a click-through arrival and a cold deep-link arrival at /create/ppt.
- Dev-server state: attempt 2 coincided with active Fast Refresh churn (multiple rebuilds, one taking 3.68s) — even under that load, no crash.

### Why it was not seen
`frontend/src/components/workflow/AgentsPopup.tsx:2474` is the only place in the codebase that logs `"[wf] 5. AgentsPopup mount"` (`grep -rn "\[wf\] 5" frontend/src` returns exactly this one hit), and that log line and the ~30 surrounding lines of its `useState` initializer never read a `startTime` property — `grep -n "startTime" frontend/src/components/workflow/AgentsPopup.tsx` returns no matches. The reported stack trace's top frame, `et.reportAllChanges`, is not an app symbol; `reportAllChanges` is a literal option/function name from the `web-vitals` library that Next.js's dev-mode instrumentation loads internally (no `web-vitals` import exists in `frontend/src`, confirmed via `grep -rn "web-vitals" frontend/src frontend/package.json` returning nothing) — so the crash is most likely a Next.js/web-vitals reporting race unrelated to `AgentsPopup`, coincidentally logged near the app's own mount log in the reporter's console capture. In every attempt here, "[wf] 5. AgentsPopup mount" logged twice per mount (component double-invoked under React StrictMode/dev mode) with no error following it, matching the report's own quoted log line but never producing the TypeError after it.

### What the reporter could add
- Whether DevTools was open with the Performance/Web Vitals panel active, or a browser extension that hooks `PerformanceObserver`, at the time of capture — this is the kind of external reporting hook `reportAllChanges` belongs to.
- The exact dev-server state (mid-HMR rebuild, cold start, or long-idle) — Next.js's own instrumentation is more likely to race during heavy Fast Refresh churn, which this session reproduced without a crash but could not force reliably.
- A HAR/full console capture (not just the error) showing what ran in the ~1-2 lines before `et.reportAllChanges`, since the minified `<anonymous>:2:xxxx` frames give no file attribution.

### Side observations
- The two "Pitch an idea" cards ("Pitch an idea" and "Pitch an idea (v2)") are adjacent on the dashboard and a loose/regex text match resolves both — not itself a bug (existing site quirk, `multipleIdenticalLabels`-adjacent), but worth noting for anyone else reproducing this report.

## QA-PS-015

**Title:** "Chain" option on run history list opens a legacy run UI instead of the current run detail page · **Route:** /runs · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-015](BUGS.md#qa-ps-015) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning, commit dfd167387 (HEAD)

### Steps followed
1. Sign in as `qa-admin@flowinqa.com` (session already present via `auth_token`)
2. Cold navigate to `/runs`
3. Open the row's "Run actions" (⋯) menu on a completed/cancelled run row
4. Look for a **Chain** menu item to click

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | Row "Revision: Make the heading text dark blue." (completed) | Cold nav to `/runs`, opened row's Run-actions menu via `.click()` | No — menu contains only `Delete`, no `Chain` item | menu snapshot: `menuitem "Delete"` only, ref f1e1272 |
| 2 | 2nd row on the list (completed) | Cold nav (fresh `/runs` load), opened Run-actions menu on a different row | No — same, only `Delete` | evaluate result: `[" Delete"]` |
| 3 | Row "Build a clickable prototype of Fieldwise from the attached d..." (cancelled) | Cold nav via `/dashboard` → `/runs`, opened Run-actions menu on a 3rd, differently-statused row | No — same, only `Delete` | `/Users/bilala/Developer/Projects/VELOCITY-AI/evidence/qa-ps-015/attempt3-menu-delete-only.png`; menu snapshot `menuitem "Delete"` ref f4e1285 |

### Axes swept
- Entry path: fresh cold navigation to `/runs` directly, and via `/dashboard` → `/runs`
- Row / run state: completed row, a different completed row, and a cancelled row
- Revisit: reloaded `/runs` between attempts (not a soft re-click of the same open menu)

### Why it was not seen
The row-actions menu (`RowMenu` in `frontend/src/components/history/RevisionFamilyView.tsx`) no longer renders a "Chain" item at all — it renders only `Delete`. Commit `dfd1673877f6a6a0e20c051d4e226742d51ed582` ("fix(history): drop the Chain action, and name ppt_v2 in saved workflows"), already on this branch's HEAD, removed the `onChainClick`/`GitBranch` menu button and its `handleChainAffordance` handler from `RowMenu`, `FamilyGroupCard` (`RevisionFamilyView.tsx`) and `WorkflowHistory.tsx`:
```
git show dfd167387 -- frontend/src/components/history/RevisionFamilyView.tsx
-            {run && onChainClick && (
-              <button ... role="menuitem" onClick={(e) => onChainClick(run, e)} ...>
-                <GitBranch ... /> Chain
-              </button>
-            )}
```
Live confirmation in all 3 attempts: opening the Run-actions menu on 3 different rows (different run status, different position on the list, across independent cold page loads) shows exactly one menuitem, `Delete` — no `Chain` entry exists to click, so the reported repro path (click ⋯ → click Chain → legacy UI opens) cannot be executed on the current build. The commit message itself independently corroborates the mechanism the reporter hit: "a second way into a screen no normal user path mounts" (the internal `selectedRun`/`handleSelectRun({forChain:true})` detail view) — which is exactly the legacy Agents/Timeline/Full-Screen/Suggested-Next-Steps layout the reporter described.

### What the reporter could add
Nothing further needed — the defect is real as reported (confirmed independently by the fix commit's own description) and has already been fixed in the codebase (commit dfd167387) ahead of this validation pass; the entry point no longer exists to re-trigger it.

### Side observations
- The commit is already on this branch's HEAD but `LEDGER.md`'s QA-PS-015 row was still `Open` at the time of validation — the fix landed without the register being updated to reflect it.

## QA-PS-017

**Title:** "Chain" option in run history context menu is enabled for Running and Cancelled runs, should only be active when Done · **Route:** /runs (row context menu) · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-017](BUGS.md#qa-ps-017) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch `feat/git-versioning`, HEAD includes commit `dfd1673877f6a6a0e20c051d4e226742d51ed582`

### Steps followed
1. Sign in as `qa-admin@flowinqa.com` (already signed in via persisted session — verified `!!localStorage.getItem('auth_token')` before driving the UI)
2. Cold-navigate to `/runs`
3. Locate a run in **Running** state (found `Arctic Seed Vault Logistics Briefing .`, backend status `waiting_for_user`, displayed badge "Running") and separately a run in **Cancelled** state (found `PROBE ONLY - verifying pipelineType propagation...`, badge "Cancelled")
4. Click the row's **⋯ "Run actions"** button
5. Observe the dropdown menu's contents

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | Running run `9a19ffde…` area row "Arctic Seed Vault Logistics Briefing ." (status `waiting_for_user`, badge "Running") + Cancelled row "PROBE ONLY - verifying pipelineType propagation..." + a Done row "Greet in Spanish for a bug validation test." | Cold nav to `/runs`, waited for the "Fetching your pipeline history..." loader to clear, opened each row's Run-actions menu in turn | No — every menu (Running, Cancelled, and Done alike) contains exactly one item, `Delete`; no `Chain` item exists anywhere in the row menu | `evidence/qa-ps-017/cycle1-running-menu-delete-only.yml`, `cycle1-cancelled-menu-delete-only.yml`, `cycle1-done-menu-delete-only.yml` |
| 2 | Cancelled row "PROBE ONLY - verifying pipelineType propagation..." | Fresh cold reload of `/runs` (new page load, not a re-click), opened the row's Run-actions menu | No — menu contains only `Delete` | `evidence/qa-ps-017/cycle2-cancelled-menu-delete-only.yml`, `evidence/qa-ps-017/cycle2-cancelled-menu.png` |
| 3 | Running row "Arctic Seed Vault Logistics Briefing ." | Fresh cold reload of `/runs` again, opened the row's Run-actions menu | No — menu contains only `Delete` | `evidence/qa-ps-017/cycle3-running-menu-delete-only.yml`, `evidence/qa-ps-017/cycle3-running-menu.png` |

### Axes swept
- Run status: Running (`waiting_for_user`), Cancelled, and Done — all three checked, none show a `Chain` menu item
- Entry path: fresh cold navigation to `/runs` on every attempt (no soft re-click of an already-open menu)
- Row position: different rows each time (today's section vs. "Earlier this week" section)

### Why it was not seen
The row-actions menu (`RowMenu` in `frontend/src/components/history/RevisionFamilyView.tsx`) no longer renders a "Chain" menu item at all — for any run status, not just Running/Cancelled. Commit `dfd1673877f6a6a0e20c051d4e226742d51ed582` ("fix(history): drop the Chain action, and name ppt_v2 in saved workflows"), already on this branch's HEAD (authored 2026-09-22 08:47:23, ahead of this validation pass), removed the menu's `Chain` button entirely:
```
git show dfd167387 --stat
 .../src/components/history/RevisionFamilyView.tsx  | 32 +++-------------------
 .../src/components/history/WorkflowHistory.tsx     | 11 --------
```
Commit message: "The run-actions menu carried a 'Chain' item that existed only to reach the internal detail view's 'Suggested next steps' panel — a second way into a screen no normal user path mounts. Remove it and the handler it needed; RowMenu keeps the actions that act on the row."

Live confirmation across all 3 attempts, on Running, Cancelled and Done rows alike: the only menuitem present is `Delete`. Since the `Chain` entry point this report describes was removed from the row menu, the enabled-when-it-shouldn't-be state cannot be observed — there is nothing to click.

This is the same root cause and the same fix commit already recorded against [QA-PS-015](UNREPRODUCIBLE.md#qa-ps-015) (same menu, same commit, different symptom of the same now-removed affordance). Chain is still reachable — from the run-detail page's "Suggested next steps" panel (`WorkflowHistory.tsx` "Suggested next steps" section) — which already gates on run status: it only renders for `status === "completed"` or a terminal non-success status (`failed`/`cancelled`/`degraded`/`diverted`) with `chainInto(...).length > 0`, and disables the button (`disabled={opt.beta || !canChain}`) whenever `canChain` is false. A live/running/`waiting_for_user` run never satisfies that render condition at all, so the "Suggested next steps" Chain button is not offered for a Running run either.

### What the reporter could add
Nothing — the defect as reported (Chain enabled outside Done) is now moot because the entire menu entry it names was deleted by a same-branch fix landed ahead of this validation. Re-validate only if that commit is reverted or the Chain surface is reintroduced elsewhere.

### Side observations
- `LEDGER.md`'s QA-PS-017 row was still `Open` at the time of validation even though the fix (commit `dfd167387`) was already on HEAD — same pattern already noted on QA-PS-015's trace.
- The replacement Chain surface (run-detail "Suggested next steps" panel) already implements the correct status gating per SGV2 11.7 code comments (`canChain`, `isNonSuccess`, disabled state + `nonChainableReason` text) — worth spot-checking separately if that panel itself is ever reported as a bug, but it is out of scope for this report.

## QA-PS-016

**Title:** Chain-initiated revision creates a new top-level run entry instead of adding a version (v2) to the parent run · **Route:** /runs · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-016](BUGS.md#qa-ps-016) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning, commit 049a8c3a4 (HEAD)

### Steps followed
1. Sign in as `qa-admin@flowinqa.com` (session already present via `auth_token`)
2. Cold navigate to `/runs`
3. Open the row's "Run actions" (⋯) menu on a completed run row
4. Look for a **Chain** menu item to click, then attempt the revision flow it names

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | "Arctic Seed Vault Logistics Briefing ." (completed, latest version v3) | Cold nav to `/runs`, opened Run-actions menu via `.click()` on row 1 | No — menu contains only `Delete`, no `Chain` item, so the revision flow could not be started | menu snapshot: `menuitem "Delete"` only, ref f1e1241 |
| 2 | "Revision: Make the heading text dark blue." (completed) | Cold nav (`/dashboard` → `/runs`), opened Run-actions menu on row 2 via `evaluate` click | No — same, only `Delete` | evaluate result: `["Delete"]` |
| 3 | 11th row in "Earlier this week" (mixed completed/failed/cancelled) | Cold nav (`/dashboard` → `/runs`), opened Run-actions menu on a differently-statused row | No — same, only `Delete` | `/Users/bilala/Developer/Projects/VELOCITY-AI/evidence/qa-ps-016/attempt3-menu-delete-only.png`; evaluate result: `["Delete"]` |

### Axes swept
- Entry path: fresh cold navigation to `/runs` directly, and via `/dashboard` → `/runs`
- Row / run state: 3 different rows (completed with 3 versions, completed revision-titled run, and a row further down the mixed-status list)
- Revisit: full page reload between every attempt, never a soft re-click of an already-open menu

### Why it was not seen
The row-actions menu (`RowMenu` in `frontend/src/components/history/RevisionFamilyView.tsx`) no longer renders a "Chain" item — only `Delete`. Commit `dfd167387f6a6a0e20c051d4e226742d51ed582` ("fix(history): drop the Chain action, and name ppt_v2 in saved workflows"), already on this branch's HEAD (`git merge-base --is-ancestor dfd167387 HEAD` → true), removed the `onChainClick`/`GitBranch` menu button and its `handleChainAffordance` handler from `RowMenu`, `FamilyGroupCard` and `WorkflowHistory.tsx` — the exact same removal already documented on [QA-PS-015's trace](UNREPRODUCIBLE.md#qa-ps-015).

QA-PS-016's repro path is step 3 of QA-PS-015's repro path: "Click the ⋯ menu on that run and click Chain." With the Chain menu item deleted, there is no way to reach the "ask for a revision" step this bug reports on at all — the entry point the whole scenario depends on does not exist in the running build. All 3 attempts across different rows and entry paths confirm the same thing: `[role=menuitem]` under the Run-actions popover is `["Delete"]`, full stop.

### What the reporter could add
Nothing further needed — the defect is real as reported (QA-PS-015 already established the Chain button pointed at a legacy UI, and this bug is one downstream symptom of that legacy path) and the whole Chain surface has since been deleted by commit `dfd167387` ahead of this validation pass, so the orphaned-run-creation behaviour it describes can no longer be triggered.

### Side observations
- `LEDGER.md`'s QA-PS-016 row was still `Open` at validation time even though the removal commit (`dfd167387`) was already on HEAD — same stale-register pattern already flagged on QA-PS-015 and QA-PS-017.
- Per QA-PS-017's trace, the replacement Chain surface (run-detail "Suggested next steps" panel) already gates on run status; whether that panel's revision flow correctly versions onto the parent run (the behaviour this bug wants) is a separate, unvalidated question for that panel, not this report.

## QA-PS-018

**Title:** Chain flow leaks raw sentinel string "=== EXISTING PRESENTATION CODE ===" into run title, topic display, and Steps starting point · **Route:** /runs and /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-018](BUGS.md#qa-ps-018) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch `feat/git-versioning`, commit `049a8c3a40f17427339316e7bc2fe4f10325ce0a` (HEAD)

### Steps followed
1. Sign in as `qa-admin@flowinqa.com` (session already present via `auth_token`)
2. Cold navigate to `/runs`, locate a completed Presentation run
3. Open the row's "Run actions" (⋯) menu, look for a **Chain** item to click and select **Prototype**
4. (0/3 attempts found any Chain item — steps 5-9 of the reported repro, chaining through and checking the topic/Steps tab, could not be executed at all)

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | Row "Arctic Seed Vault Logistics Briefing ." (Presentation, Done, the exact run type/state named in the report) | Cold nav to `/runs`, opened the row's Run-actions menu via ref click | No — menu contains only `Delete`, no `Chain` item | `evidence/qa-ps-018/attempt1-runmenu-delete-only.png`; menu snapshot `menuitem "Delete"` ref f5e1241 |
| 2 | Row "Revision: Make the heading text dark blue." (Custom Revision, Done) | Fresh cold reload of `/runs`, opened a different row's Run-actions menu | No — same, only `Delete` | `evidence/qa-ps-018/attempt2-runmenu-delete-only.png`; menu snapshot `menuitem "Delete"` ref f6e1241 |
| 3 | 5th row-actions button in DOM order (Cancelled/Prototype-family row) | Cold nav via `/dashboard` → `/runs`, opened a 3rd, differently-statused/typed row's menu via `querySelectorAll('button[aria-label="Run actions"]')[4]` | No — same, only `Delete` | `evidence/qa-ps-018/attempt3-runmenu-delete-only.png`; evaluate result `["Delete"]` |

### Axes swept
- Row / run type: the named Presentation run, a Custom Revision run, and a Prototype-family run — no Chain item on any
- Entry path: direct cold nav to `/runs`, and via `/dashboard` → `/runs`
- Replacement surface (code-level, since the row menu affordance is gone): the run-detail page's "Suggested next steps" chain chips (`RunChatLane.tsx`, gated on `runState === "complete"`) — loaded `/runs/e53d9b1f-5e52-442b-9bb8-d58accc9e029` (the same "Arctic Seed Vault" Presentation run, Done) directly and searched the full transcript text and DOM (`browser_find` for `/suggest|next step|chain/i`, full `innerText` dump) — no chain suggestion UI rendered for a statically-loaded historical run
- Legacy detail view (`WorkflowHistory.tsx`'s `selectedRun`/chain-options panel, the same screen QA-PS-015 found the sentinel-adjacent UI in): traced `handleSelectRun` — it only sets `selectedRun` (making the chain-options panel reachable) when called with `{forChain:true}`, and the only caller of that flag was the row-menu Chain button, which attempt 1-3 confirm no longer exists

### Why it was not seen
The row-actions menu (`RowMenu` in `frontend/src/components/history/RevisionFamilyView.tsx`) renders only `Delete` on every run type/status tried — confirmed live in all 3 attempts. This is the same removal already recorded on [QA-PS-015](UNREPRODUCIBLE.md#qa-ps-015) and [QA-PS-017](UNREPRODUCIBLE.md#qa-ps-017): commit `dfd1673877f6a6a0e20c051d4e226742d51ed582` ("fix(history): drop the Chain action, and name ppt_v2 in saved workflows"), already on this branch's HEAD, deleted the `onChainClick` button and its handler. The reported repro's step 3 ("Click the ⋯ menu ... and click Chain") cannot be executed — there is no Chain entry to click, so steps 4-9 (select Prototype, wait for the chained run, and inspect its title/topic/Starting-point for the leaked sentinel) were never reachable.

Beyond the missing entry point, the code that *would* build the chained run's title was independently inspected and no longer matches the reported mechanism either. `frontend/src/components/layout/DashboardLayout.tsx`'s two current Chain-launch call sites both already strip the sentinel before display:
- `handleChainFromHistory` (`DashboardLayout.tsx:1954-2031`) computes `historyBrief` via `parseRunInput(run.input)` and passes `_display_title: historyBrief` (line 2029) — not the raw `=== EXISTING PRESENTATION CODE ===` block — when starting the chained pipeline.
- For any chain target with a wizard (Prototype has one — `selectWorkflowWizardPath` in `frontend/src/store/slices/globalSlice.ts:249-256` maps `prototype` to `/workflow/create?mode=prototype`), `handleChainFromHistory` takes an earlier branch (`DashboardLayout.tsx:1955-1979`) that never constructs the sentinel message at all: it stores `CHAIN_BRIEF_KEY = cleanBrief` (`run.input.split("\n\n===")[0].trim()`, i.e. the brief with the `=== ... ===` framing already cut off) in `sessionStorage` and routes to the wizard — the sentinel string is stripped before it is ever stored anywhere the title/topic could read it back.

The `=== EXISTING PRESENTATION CODE ===` marker itself still exists in the codebase (`DashboardLayout.tsx:2979`, inside `onRevisePpt`), but that is the same-type-revision flow ("Revise this presentation"), not cross-type Chain, and it already passes `_display_title: instruction.slice(0, 60)` (line 2980) alongside the sentinel-framed `msg` — the sentinel goes into the agent's prompt payload, not the title field the report says leaked.

### What the reporter could add
Nothing to add to the report itself — if the defect was real on an earlier build (plausible, given the marker string and title-field naming exist verbatim in the code the report describes), it is moot now: the only entry point named in the repro was removed by `dfd167387`, and the current Chain code paths that remain already separate the display title from the sentinel-framed prompt body. Re-validate only if the row-menu Chain action is reintroduced, or if a *same-type* revision (`onRevisePpt`/`onRevisePrototype`, which do still build a `=== EXISTING ... ===`-framed message) is found leaking that marker into a title somewhere — that would be a different, not-yet-investigated repro path.

### Side observations
- Same underlying commit (`dfd167387`) as QA-PS-015 and QA-PS-016(already-recorded traces) and QA-PS-017 — four separate PS reports all describing symptoms of the one now-removed row-menu Chain affordance. `LEDGER.md`'s QA-PS-018 row was still `Open` at validation time despite the fix already being on HEAD, the same stale-register pattern flagged on the sibling bugs.

## QA-PS-033

**Title:** Steps, agents and agent outputs do not switch to the selected version when the family member record has no git_tag populated · **Route:** /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-033](BUGS.md#qa-ps-033) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning, commit 049a8c3a4

### Steps followed
1. Signed in as `qa-admin@flowinqa.com` (lane8 already had a session).
2. Used the "BROKEN" family named in the dispatch: root `2708dbf1-50d0-465d-9bed-56b651ea1abf` (git_tag `v1`), revision `23bd9c67-e239-4979-b14a-cb78222795e8` (revision_index 2, **git_tag NULL** in Postgres `workflow_runs`), revision `3839720c-0287-48c0-90cb-4385d910f460` (revision_index 3, git_tag `v3`).
3. Opened the root run, opened the version dropdown, and inspected which versions were offered.
4. Tried to select the null-git_tag member (v2/`23bd9c67`) via the dropdown as the repro literally describes ("Click the version dropdown and select any version").
5. Since the dropdown did not offer it, reached that member instead via the app's own "Answer in Steps" chat link (client-side SPA navigation) and via three separate cold full-page loads of `/runs/{root}/versions/2/steps`.
6. As a control, also performed the literal dropdown-click repro (open dropdown → click "v3" → click Steps tab) for the sibling member that does have a git_tag.

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | `23bd9c67` via SPA click on "Answer in Steps" chat link | Client-side nav to `/runs/2708dbf1…/versions/2/steps` | No — Steps showed 3/3 agents specific to that revision (Prototype Revision Analyzer, Revision Specialist Agent, Validation Agent), chip read "Viewing v2 (read-only)", not the live run's 11-agent pipeline | `evidence/qa-ps-033/01-validate-attempt1-v2-steps-shows-3-agents.png` |
| 2 | `23bd9c67` via cold full-page load of `/versions/2/steps` | Fresh `page.goto`, no prior SPA state | No — same 3/3 agents, "Viewing v2 (read-only)" | `evidence/qa-ps-033/03-validate-attempt2-coldload-v2-steps-shows-3-agents.png` |
| 3 | `23bd9c67` via a second independent cold full-page load (navigated to `/runs` first, then back in) | Fresh `page.goto` after visiting an unrelated route | No — same 3/3 agents, chip "v2 ▾", `Viewing v2 (read-only)` | `evidence/qa-ps-033/04-validate-attempt3-coldload-v2-steps-shows-3-agents.png` |
| control | `3839720c` (v3, has git_tag) via literal dropdown click → Steps tab | Opened dropdown on the root run, clicked option "v3", clicked Steps tab | N/A (control) — correctly showed 2/2 agents (Composed Revision Planner, Composed Revision Builder), confirming the working case for comparison | `evidence/qa-ps-033/05-validate-dropdown-only-offers-latest-and-v3.png` |

### Axes swept
- Entry path: SPA client-side navigation (chat link) vs. cold full-page load (×2) vs. literal dropdown click — all resolved the version's own agents correctly.
- Timing: immediate click vs. `wait_for` on settle text — no difference.
- Member: tested the null-git_tag member (`23bd9c67`) directly by URL/revision_index, and the has-tag member (`3839720c`) via the literal dropdown-click repro path — both correct.

### Why it was not seen
The report's root cause names `handleVersionMenuSelect`'s tag-lookup fallback (`sortedMembers.find(m => m.git_tag === tag)` returning `undefined`) as the trigger. But `GET /api/runs/2708dbf1-50d0-465d-9bed-56b651ea1abf/sandbox/refs` returns `{"refs":["v3"]}` — only members that already have a `git_tag` appear as tags in git, so the dropdown itself only ever offers `"Latest (live)"` and `"v3"`; the null-git_tag member (`23bd9c67`, revision_index 2) is never presented as a selectable option in the version dropdown, so its tag can never be clicked to trigger `handleVersionMenuSelect`'s described undefined-lookup path. The one route that *does* reach that member — the "Answer in Steps" / "Open in Steps" chat links, which navigate by `revision_index` via `/versions/{n}/steps` rather than by git tag — resolves it correctly: Steps/agents/pipeline state all show that revision's own 3-agent run (`Prototype Revision Analyzer`, `Revision Specialist Agent`, `Validation Agent`, 4m 28s total), distinct from both the root's 11-agent pipeline and v3's 2-agent pipeline. This matches `FIX-516` in the knowledge base (`handleVersionMenuSelect` resolves tag→member and calls `handleSelectVersion`), which appears to already cover the general case this bug's root-cause section describes.

### What the reporter could add
- The exact selection path used when this was seen — specifically, was a version actually clickable in the dropdown when its `git_tag` was null? On this build the dropdown excludes such members outright (backed by `GET .../sandbox/refs` returning only git-tagged members), so the `handleVersionMenuSelect` fallback branch quoted in the bug's Root Cause section looks unreachable via the UI as currently built.
- If reproduced through some other UI affordance (not the version-menu dropdown, not the "Answer in Steps" chat link), name it — a third path may exist that was not tested here.

### Side observations
- The genuinely reproducible symptom in this family is that the null-git_tag member is **entirely absent from the version dropdown**, not that selecting it freezes Steps on the live run's data. That is a different (but related) manifestation of the git-tag-missing defect (Defect B / `ISS-671`, `ISS-678`, `ISS-697` already in the knowledge base — dropdown is git-tag-only with no DB fallback) rather than this bug's described `handleVersionMenuSelect` fallback path.

## QA-PS-029
> **Evidence missing** — claims below are unproven.



**Title:** Selecting an older version shows "Loading v{n}…" indefinitely — 404 on deliverable file fetch for any workflow type · **Route:** /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-ps-029](BUGS.md#qa-ps-029)

## QA-SG-011
> **Evidence missing** — claims below are unproven.



**Title:** Version 1 prototype shows no content in preview, preview area is blank when viewing v1 · **Route:** /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-sg-011](BUGS.md#qa-sg-011)

## QA-SG-010

**Title:** Share button on run detail page displays raw JSON instead of a simple message while workflow is running · **Route:** /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-sg-010](BUGS.md#qa-sg-010) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning

### Steps followed
1. Sign in as qa-admin@flowinqa.com (already an active session)
2. Locate an actively-running run via `GET /api/runs?limit=50` (status `generating`)
3. Navigate directly to `/runs/<id>` (cold nav) while the run is running
4. Locate and attempt to click the Share button
5. Observe the message/popover that appears

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | 3bc4403e-e89c-4484-9243-777465964ee3 (prototype, status `generating`, step 1 of 5) | Cold nav to `/runs/<id>` -> redirected to `/runs/<id>/stream`; located "Share this run" button; click attempted | No — button has the `disabled` attribute and `cursor-not-allowed` class; Playwright click timed out after 5s waiting for "element to be visible, enabled and stable" ("element is not enabled") | evidence/qa-sg-010/01-validate-attempt1-share-disabled-while-running.png |
| 2 | 3bc4403e-e89c-4484-9243-777465964ee3 (still generating) | Fresh cold nav (/dashboard -> /runs/<id> again), same run, checked Share state | No — Share button still disabled | evidence/qa-sg-010/02-validate-attempt2-share-disabled-while-running.png |
| 3 | 3bc4403e-e89c-4484-9243-777465964ee3 (still generating) | Third cold nav cycle, same run | No — Share button still disabled | evidence/qa-sg-010/03-validate-attempt3-share-disabled-while-running.png |

### Axes swept
- Run state: `generating` (0/5 agents, "building step 1 of 5") on 3 separate cold-nav cycles — Share button disabled every time, un-clickable (Playwright confirms via timeout, not just visual styling)
- Theme: light vs dark (`page.emulateMedia({colorScheme:'dark'})`) on the same running run — Share still disabled in both
- Comparison state: a `completed` run (7606d868-37ff-4271-a679-0aa8ecfd5ea9) — Share button is enabled, clicking it opens a clean "Share deliverable" popover with a plain-language description, a copyable link, and a "Revoke link" action — no JSON anywhere. See evidence/qa-sg-010/04-validate-completed-run-share-clicked.png
- Tabs: checked Preview and Steps tabs on the running run — Share control is in the shared page header, same disabled state on both tabs

### Why it was not seen
On this build (branch `feat/git-versioning`), the Share button on `/runs/{id}` is rendered with the HTML `disabled` attribute and `cursor-not-allowed` styling whenever the run's status is `generating`/`Running`. Playwright's click confirms this is a real disabled state, not just a visual one: attempting `.click()` on it (evidence attempt 1) times out with "element is not enabled" after repeated retries, meaning no click handler — and therefore no JSON-rendering code path — can fire while a run is running. The reported repro step "click the Share button... Observe the message" cannot occur as described, because the button does not accept clicks in this state at all. On a completed run the same control is enabled and produces the exact friendly "Share deliverable" popover the ticket's own Expected section describes (screenshot 04), which is the opposite of what QA-SG-010 claims should be broken.

### What the reporter could add
- The exact run id/page id and a screenshot of the moment raw JSON appeared, since the current build shows the button disabled (not clickable, not JSON) during that state — if the reporter saw JSON, it likely came from a build predating the disable-while-running guard, or from a different affordance (e.g. a toast/console log) that was mistaken for the Share button's output.

### Side observations
- None.

## QA-SG-009

**Title:** Run detail page takes a long time to render data, causing significant delays · **Route:** /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-sg-009](BUGS.md#qa-sg-009) · **Tree:** feat/git-versioning, checkout /Users/bilala/Developer/Projects/VELOCITY-AI

### Steps followed
1. Sign in as `qa-admin@flowinqa.com` (session already authenticated, `auth_token` present in localStorage).
2. Go to `/runs`.
3. Open a run's detail page (`/runs/{id}`) via both a direct cold URL navigation and a click-through from the Run History card.
4. Measure the time from navigation start until the run data (steps timeline, chat, deliverable preview) is visible on screen, using `performance.getEntriesByType('navigation')[0]` (`domContentLoadedEventEnd`/`loadEventEnd`) plus a screenshot taken immediately after Playwright's navigation settles.

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | 7606d868-37ff-4271-a679-0aa8ecfd5ea9 (ppt, `completed`, 3 agents, ~113KB payload) | Cold nav `/login` → `/dashboard` → `/runs/<id>` (direct URL) | No — `loadEventEnd` 804ms; screenshot taken immediately after navigate shows full timeline, deliverable preview, and "Take this further" panel already rendered | evidence/qa-sg-009/01-validate-attempt1-run-detail-immediate.png |
| 2 | 7606d868-37ff-4271-a679-0aa8ecfd5ea9 (same run, repeat) | Cold nav `/dashboard` → `/runs/<id>` again | No — `loadEventEnd` 2065ms (within the ticket's own "under 2-3 seconds" expectation); screenshot shows full content rendered, only a small non-blocking "Loading workspace…" toast in the corner | evidence/qa-sg-009/02-validate-attempt2-run-detail-immediate.png |
| 3 | e53d9b1f-5e52-442b-9bb8-d58accc9e029 (ppt, `completed`, longest-duration run in the dataset, 114m57s, ~137KB payload, agent_outputs string 111,043 chars — largest available) | Cold nav `/dashboard` → `/runs/<id>` for the heaviest-payload run found via `GET /api/runs?limit=100` sorted by duration | No — `loadEventEnd` 1768ms; screenshot shows full timeline and deliverable preview already rendered | evidence/qa-sg-009/03-validate-attempt3-big-run-immediate.png |

### Axes swept
- Entry path: direct cold URL load (attempts 1-3) vs click-through from the Run History list (`/runs` → click a run card, SPA route change) — sweep attempt, evidence/qa-sg-009/05-validate-sweep-clickthrough-run-detail.png — full content rendered immediately in the post-navigation screenshot either way.
- Run state: `completed` (attempts 1-3) vs `generating` (run 3bc4403e-e89c-4484-9243-777465964ee3, an in-progress prototype run) — sweep attempt, evidence/qa-sg-009/04-validate-sweep-generating-run-immediate.png — `loadEventEnd` 1445ms, redirects cleanly to `/runs/<id>/stream` and renders promptly.
- Payload size: smallest completed run tested (~113KB, attempt 1) vs the largest completed run available in this dataset (~137KB response, 111K-char `agent_outputs` string, attempt 3) — no measurable difference in perceived load time.
- Backend API timing directly: `GET /api/runs/<id>` for the same run ids via `curl`, `time_total` 0.07-0.21s each — ruling out a slow backend response as the bottleneck for the runs actually tested.

### Why it was not seen
Across 5 cold-start attempts (3 required + 2 sweep axes), `navigation.loadEventEnd` ranged 804ms-2065ms — inside the ticket's own "under 2-3 seconds" expectation — and every post-navigation screenshot (evidence/qa-sg-009/01…05) shows the run's steps timeline, chat entries, run summary, and deliverable preview already fully rendered, not blank or partially rendered. `GET /api/runs/<id>` itself returns in 70-210ms for the runs tested (curl `time_total`), so the backend is not the bottleneck for these payload sizes either. No axis tried (entry path, run state, payload size) reproduced a "5+ seconds" delay or a blank/frozen page.

### What the reporter could add
- A specific run id, or the run's approximate `agent_count`/token size/duration, so a heavier or more representative case than the largest one available in the current dataset (111K-char `agent_outputs`, 137KB response) can be tried — if there exists a run with dramatically more steps/files/chat turns than any currently in this database, the slowdown may only appear past that threshold. A screen recording or a browser DevTools Performance/Network trace of the actual slow load (with timestamps) would pin the axis directly instead of requiring a sweep.

### Side observations
- The `/runs` (Run History) list itself issues repeated `GET /api/runs?limit=50` calls in quick succession while runs are actively `generating`/`waiting_for_user` (observed 5 calls within roughly 20 seconds on this page), which invalidates accessibility-tree element refs mid-interaction (`browser_click` on a previously-valid `[ref=...]` intermittently fails with "does not match any elements"). This is a list-page polling/rerender behavior, not the run-detail-page symptom QA-SG-009 describes, and was not pursued further here.

## QA-SG-008

**Title:** SSE events for approvals and clarifications don't sync across multiple browser sessions · **Route:** /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-sg-008](BUGS.md#qa-sg-008) · **Tree:** feat/git-versioning, checkout /Users/bilala/Developer/Projects/VELOCITY-AI

### Steps followed
1. Sign in as `qa-admin@flowinqa.com` (session already authenticated, `auth_token` present in localStorage).
2. Launch a User Stories run from `/create/user-stories` with a "review gate" checked on the `domain-analyst` agent, so the run pauses twice: once for the pipeline's 4 clarification questions, once for the domain-analyst review gate.
3. Once the run redirects to `/runs/<id>/stream`, open a second tab (Browser B) with a cold `goto('/runs/<id>')` for the same run — same signed-in user, separate tab.
4. In Browser A, submit the clarification answers ("Accept all recommended & continue"). Observe Browser B **without reloading or interacting with it**.
5. Wait for the domain-analyst review gate to appear in both tabs. In Browser A, click "Accept & continue to build". Observe Browser B **without reloading or interacting with it**.

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | 1a92ab60-3667-44ca-b8c6-15d6d219fdb7 (User Stories, gate on domain-analyst) | Cold-launched run, opened Tab B cold, answered clarifications in Tab A ~immediately after Tab B loaded, then approved the gate in Tab A ~15s after it appeared in both tabs | No — Tab B showed "Clarifications round 1 answered" / "Run started" and progressed to "Domain Discovery Agent · Thinking…" with zero interaction on that tab (evidence 03, 04); after the gate approval in Tab A, Tab B flipped from "Paused for your approval / REVIEW" to "Pipeline running · 1/6 / BUILDING" with no reload (evidence 05, 07) | evidence/qa-sg-008/01…07 |
| 2 | 05ae375a-99de-4473-8fd0-67d23fd0b253 (fresh run, same config) | Cold-launched a brand-new run, fresh Tab B, answered clarifications and approved the gate from Tab A after longer waits (~40s, ~30s) | No — Tab B's "Clarifications round 1 answered" appeared with no interaction, and after gate approval Tab B showed "Pipeline running · 1/6 / BUILDING" with no reload (evidence 08) | evidence/qa-sg-008/08 |
| 3 | cbe2a1a9-fc72-4b76-a699-2d2414b66f95 (fresh run, same config) | Cold-launched a third fresh run, fresh Tab B, same steps with ~70s and ~30s waits before each action | No — same result: clarifications and gate approval both propagated to Tab B live, no reload (evidence 09) | evidence/qa-sg-008/09 |

### Axes swept
- Timing: gate/clarify answered within seconds of the paused state appearing (attempt 1) vs after 30-70s of the tab sitting idle (attempts 2 and 3) — no difference, SSE delivered live in all three.
- Event type: tested both the clarification-answer SSE broadcast and the review-gate-approval SSE broadcast in every attempt — both synced live every time.
- Run identity/data: three separate runs (different ids, different briefs), so this was not a single-run fluke.
- Not swept (see below): true separate browser profiles/incognito contexts, a different account tier for Browser B, entry into the run via the Run History list-row click-through instead of a direct URL, and dark mode.

### Why it was not seen
In all 3 cold-start attempts, Browser B (a second tab opened with a fresh `goto('/runs/<id>')`, never reloaded or interacted with afterward) updated live and without any manual request the moment Browser A submitted a clarification answer or approved a review gate — the header status, the chat transcript ("Clarifications round 1 answered", "Run started"), and the Steps panel (REVIEW → BUILDING, agent progress counters) all changed in Tab B with zero action taken in that tab (evidence/qa-sg-008/03, 04, 05, 07, 08, 09). This is the opposite of the reported symptom ("Browser B does not receive or display the SSE event... remains on screen... appears stalled"). A pre-existing fix, `.knowledge/cards/20260802-FIX-258.md` (KAN-134, "Multi-Tab SSE Stream Silent Data Loss — fan-out pump had no producer"), already addresses the general multi-subscriber SSE fan-out mechanism this bug report describes, and its `status: done` is consistent with what was observed here: both tabs are independent subscribers on the same run's event bus and both receive every event.

### What the reporter could add
- The literal two-browser setup (e.g. two actual browser processes/profiles, or two different devices) rather than two tabs in one profile, plus the browser/version used — if the drop is specific to genuinely separate cookie/session contexts or a particular browser's SSE/EventSource reconnect behavior, that would not show up with two tabs sharing one Chrome profile as tested here.
- Whether the run had been open in Browser B for a long time (many minutes) before the approval in Browser A, in case the SSE connection needs to have gone through an intermediate reconnect (e.g. after a `stream_attached`/reconnect cycle) for the drop to occur, rather than a fresh subscribe.
- A screen recording or the Network tab's EventStream frames from the affected session, showing the event either never arriving or arriving but not being applied to the UI — this would also distinguish "SSE not delivered" from "SSE delivered but ignored by the client," which point at very different code paths.

### Side observations
- A React console error appeared during clarify/gate re-renders on attempts 2 and 3: "The final argument passed to %s changed size between renders. The order and size of this array must remain constant." referencing a `useEffect` dependency array keyed by the run id (`[runId]` growing to `[runId, ]`), at `_next/static/chunks/...js:3272`. This did not prevent the SSE sync from working in any attempt, but is a real hook-dependency smell worth a look separately from this bug.

## QA-SG-012

**Title:** Concierge chat response text is not white in night mode, hard to read with low contrast · **Route:** /runs/{id} · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-sg-012](BUGS.md#qa-sg-012) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning, commit 049a8c3a4

### Steps followed
1. Signed in as `qa-admin@flowinqa.com` (already authenticated in the lane2 browser profile; confirmed via `GET /api/auth/me` -> `{email: qa-admin@flowinqa.com, tier: enterprise, is_admin: true}`).
2. Enabled dark mode via the account-menu "Dark mode" `[role=menuitem]` item (recipe `toggleDarkMode`); confirmed `document.documentElement.getAttribute('data-theme') === 'dark'` and that it persisted via `localStorage['velocity-theme'] = 'dark'`.
3. Opened a completed workflow run with concierge chat history at `/runs/{id}` (cold, deep-linked navigation each time — not a soft re-click).
4. Read the concierge chat lane (`[data-testid="execution-chat-lane"]`, left rail) and measured `getComputedStyle(el).color` for every leaf text node in the lane, including the agent's own response text ("Round 1: Before I build, I need to lock a few things down.", "Clarifications round 1 answered", "Delivered — open in Preview →").

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | `7606d868-37ff-4271-a679-0aa8ecfd5ea9` (completed PPT run, solar pitch deck) | Cold deep-link to `/runs/{id}` after enabling dark mode and reloading the page fresh | No — agent response text measured `rgb(245,245,245)` on `rgb(13,13,13)` body background (~18.5:1 contrast) | `evidence/qa-sg-012/01-validate-attempt1-chat-lane-dark.png` |
| 2 | `a8eebf7b-4492-4bce-a02b-43e83ccd1a4d` (completed PPT run, meal-kit pitch deck) | Cold nav via `/dashboard` then deep-link to a different completed run | No — same near-white color (`rgb(245,245,245)`) for every agent response line; secondary metadata text (`3 agents · ...`, timestamps) intentionally dimmer at `rgb(168,168,168)`/`rgb(92,92,92)` but that is metadata, not response text | measured via `browser_evaluate`, values in transcript |
| 3 | `76d42df2-c484-48cb-9cb5-70c995930c88` (completed PPT run, coffee subscription pitch deck) | Cold nav via `/dashboard` then deep-link | No — same result, plus a full-viewport screenshot confirms visually legible white text on near-black background | `evidence/qa-sg-012/06-validate-attempt3-chat-lane-coffee-dark.png` |
| supplementary | `3c9d6306-cc62-4863-b1b1-4c7ed49f4828` (User Stories run, `waiting_for_user`/Clarifying state) | Checked the mid-conversation clarification state explicitly named in the report's repro ("User Stories or Prototype run") | No — same white text | `evidence/qa-sg-012/03-validate-attempt1-chat-lane-waiting-dark.png` |
| supplementary | `3bc4403e-e89c-4484-9243-777465964ee3` (Prototype run, `generating`/streaming) | Checked mid-stream, live-generating state | No — same white text, including while an agent card shows "Thinking…" | `evidence/qa-sg-012/04-validate-attempt1-chat-lane-generating-dark.png`, `evidence/qa-sg-012/05-validate-attempt1-chat-lane-streaming-dark.png` |

### Axes swept
- Run state: completed, `waiting_for_user`/clarifying, `generating`/streaming — all white text
- Run/pipeline type: PPT (x3 runs), User Stories, Prototype — all white text
- Entry path: cold deep-link straight to `/runs/{id}`, and cold nav via `/dashboard` then click-through — no difference
- Account/tier: `qa-admin@flowinqa.com` / enterprise, the tier the report implies by omission — matches
- Theme persistence: confirmed `data-theme="dark"` and `localStorage['velocity-theme']='dark'` held across every reload

### Why it was not seen
In all 5 attempts (3 required + 2 supplementary covering the report's own named run types and run states), every leaf text node inside `[data-testid="execution-chat-lane"]` carrying an actual agent message — the clarifying question ("Round 1: Before I build, I need to lock a few things down."), the confirmation ("Clarifications round 1 answered"), and the completion line ("Delivered — open in Preview →") — computed to `color: rgb(245, 245, 245)` against a `rgb(13, 13, 13)` page background (screenshots: `evidence/qa-sg-012/01-validate-attempt1-chat-lane-dark.png`, `06-validate-attempt3-chat-lane-coffee-dark.png`). That is a ~18.5:1 contrast ratio, far above WCAG AA. The frontend source confirms these lines use the `text-ink-900` Tailwind class (`frontend/src/components/layout/DashboardLayout.tsx:3183-3186` mounts `RunChatLane` inside the `execution-chat-lane` div), the same class also used for headings elsewhere. Only genuinely secondary metadata (agent-count captions, "Pipeline · N agents" progress captions, timestamps) uses the dimmer `text-ink-600`/`text-ink-500` tokens (`rgb(168,168,168)`/`rgb(92,92,92)`), which is a deliberate visual-hierarchy choice, not the "agent response text" the report describes.

### What the reporter could add
- The specific chat message that appeared dim/gray, verbatim, and a screenshot from their own session — the report's own steps produce white text in this build, so either the underlying fix already landed after 2026-09-18, or the low-contrast message was some other line (a specific error/toast styled differently, or a message role this validation pass did not happen to trigger) that needs to be pinned down by text content rather than by "agent response messages" in general.

### Side observations
- None.

## QA-SG-005
> **Evidence missing** — claims below are unproven.

**Title:** UI event rendering and notification ringing becomes very slow with 8 parallel workflows running · **Route:** Any (affects all pages) · **Validated:** 2026-09-22 · **Verdict:** UNREPRODUCIBLE
**Report:** [BUGS.md#qa-sg-005](BUGS.md#qa-sg-005) · **Tree:** /Users/bilala/Developer/Projects/VELOCITY-AI, branch feat/git-versioning, commit 049a8c3a4

### Note on BUGS.md structure

`BUGS.md`'s `## QA-SG-005` heading has no matching body — the repro/expected/actual text physically under that heading (steps 2-7, "Write files" toggle content) belongs to `## QA-PS-019` two headings up; the real QA-SG-005 body (8-parallel-workflows repro, expected/actual as summarized below) is physically under the `## QA-PS-020` heading, followed by the `<a id="qa-sg-006"></a>` anchor. Every heading in that stretch of the file is offset by one body-block from its own content. This is a `BUGS.md` authoring/merge defect, not part of this bug and not something this role edits (`BUGS.md` is read-only per the agent's own rules) — flagged here so the drift is visible, not silently worked around. The reproduction below follows the body text that is actually titled and worded for "8 parallel workflows / notification ringing / event rendering", regardless of which heading it currently sits under.

### Steps followed
1. Signed in as `qa-admin@flowinqa.com` (session already valid in the lane2 profile).
2. Launched 8 workflow runs "simultaneously" (per the report) and observed the dashboard/notification panel while they executed, across three different workload shapes (see Attempts).
3. Interacted with the UI (notification bell click, panel render, page nav) during the concurrent-execution window and measured actual browser timing (`performance.now()`, the `longtask` `PerformanceObserver` entry — the standard >50ms main-thread-block signal) rather than eyeballing it, since "slow" and "delayed" are otherwise subjective.

### Attempts
| # | Run / page id | What was done (timing, entry path, data) | Expected symptom seen? | Evidence |
|---|---|---|---|---|
| 1 | 8x `/create/user-stories` runs (`f88c4104…`, `ad318539…`, `ba84643c…`, `8de7e9c4…`, `3948162e…`, `55902f19…`, `706261ea…`, `cabde943…` — 6 real agents each, ~5m estimate) launched one after another (~20-30s apart) plus pre-existing background load (11 older runs also visible) | Cold nav to `/dashboard` after all 8 were in flight; clicked the Notifications bell and measured time-to-rendered-content | No — panel opened and rendered its list (21 total entries) in ~40ms; no visible lag | `evidence/qa-sg-005/01-validate-attempt1-8-runs-active-dashboard.png`, `evidence/qa-sg-005/02-validate-attempt1-notification-panel-8-active.png` |
| 2 | 8x `/create/ex_A3_b_spanish` / `/create/ex_A3_c_dutch` runs (1-agent divert workflows, no gates) fired back-to-back as fast as the UI would accept (~10-15s apart, tightest burst achievable through the real form) | Immediately after the 8th launch, cold-navigated to `/dashboard` and started a `longtask` `PerformanceObserver` + timed the notification-panel open in the same window | No — panel content rendered in 50ms; only one borderline long task (61ms, just over the 50ms threshold) in a 3-second observation window, no sustained jank | measured via `browser_evaluate`, values in the run transcript |
| 3 | Same 20+-run backlog (mixed `waiting_for_user` and completed) already accumulated from attempts 1-2 | Full cold start: navigated to `/login`, which client-side-redirected to `/dashboard` on the existing session (i.e., a genuine fresh page load, not a soft re-click); measured notification-panel open + a fresh 3s `longtask` window | No — panel content rendered in 72ms; 0 long tasks in 3s | `evidence/qa-sg-005/03-validate-attempt3-notification-panel-cold-reload.png` |

### Axes swept
- Workload shape: heavy 6-agent/~5m runs (attempt 1) vs. trivial 1-agent instant-divert runs (attempt 2) — both clean
- Launch timing: staggered ~20-30s apart (attempt 1) vs. tight back-to-back burst (attempt 2) — both clean
- Entry path: direct nav to `/dashboard` (attempts 1-2) vs. full cold reload through `/login`'s client-side redirect (attempt 3) — both clean
- Concurrency depth: 8 fresh runs (attempts 1-2) vs. 8 fresh + ~13 pre-existing backlog entries, 21 total notifications (attempt 3) — no degradation as the count grew
- Measurement: not just "did it look OK" — used the `longtask` `PerformanceObserver` (fires on any >50ms main-thread block) across all 3 attempts; at most one borderline 61ms entry total across ~14s of combined observation windows

### Why it was not seen
No literal "ringing" (audio) mechanism exists in the frontend to test in the first place: `grep -rn "\.play()\|Audio(" frontend/src/components` for anything notification-adjacent returns nothing — the report's "ringing" is necessarily the notification bell's visual/badge update, which is what was measured. In every attempt the Notifications panel (`[role="dialog"][aria-label="Notifications"]`) rendered its full content within 40-72ms of the bell click, and the `longtask` observer — the browser's own signal for a main-thread block long enough to feel like jank — recorded 0 or 1 entries per attempt, never a sustained run of them. `GET /api/runs?limit=50` network calls also returned in normal time (no elevated latency observed in the network log during the loaded windows). The one 61ms entry (attempt 2) is a single frame, not the "several seconds" delay and "noticeable lag" the report describes.

### What the reporter could add
- Whether "8 parallel workflows" means 8 launched by one user in one session (what was tested here) or 8 across multiple concurrent users/sessions sharing the same dev backend — this run against a single shared dev instance already carries other agents' background traffic (visible in the 20+-entry notification backlog), so cross-session load was already present but not deliberately controlled for.
- A screen recording or the exact wall-clock gap observed (the report says "several seconds" but gives no captured timestamp), and whether the delay was in the bell/badge specifically or in the run's own Steps/progress view — those are different code paths and only the bell/badge was tested here.
- The concrete workflow type used (custom composer vs. a built-in pipeline) — QA-PS-019/020's own repro references "eight parallel workflow runs" without naming which pipeline, and pipeline choice materially changed backend behavior here (`user_stories` runs stall in `waiting_for_user` almost immediately on their first Concierge gate, so most of the "8 parallel" window was actually 8 idle runs, not 8 busy ones).

### Side observations
- `BUGS.md`'s heading/body alignment is broken across `## QA-PS-019` through at least `## QA-SG-006` (see the Note above) — worth a human pass to re-pair headings with their intended bodies; this validation only recovered QA-SG-005's real body by cross-reading neighboring sections, not by fixing the file.
- The dashboard's "Jump back in" recent-activity cards render raw backend status strings like `waiting_for_user` verbatim instead of a humanized label, visible in several attempts here — a real find, but out of scope for this bug and not filed as a card by this pass.

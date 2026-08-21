# 015 — Test: how to check each task on the running app

Per-task manual verification. [`quickstart.md`](quickstart.md) checks each *phase* as a whole
once it's done; this file checks each *task* individually — useful mid-workflow, right after one
task lands and before the next one builds on it. Each entry: what changed, exact steps against
the running app, and what a pass looks like. AC in [`tasks.md`](tasks.md) is the source of truth;
this file is "how to actually go do that in a browser."

```bash
cd frontend && npm run dev   # http://localhost:3000, keep running for all of the below
npx tsc --noEmit             # run after any task, cheapest signal something broke
```

Log in once at the start (any test account) — most checks below assume an authenticated session.

---

## Phase 1 — Foundation & core routing

### T1 — Typed path builders

Code-only check, nothing to click yet (no page reads `routes.ts` until T6/T9).

- `grep -c "^  [a-zA-Z]*(" frontend/src/lib/routes.ts` — should roughly match the 34-route count
  in `contracts/route-map.md` (+ login/register).
- Open `frontend/src/lib/routes.ts` and spot-check 3 builders by eye against the contract table,
  including one with an id param and one with query params — confirm the path string shape
  matches exactly (no typos in segment names).
- `npx tsc --noEmit` clean.

### T2 — `parseViewPath`

Still code-only — nothing renders from this yet.

- Open `frontend/src/lib/routes.test.ts` if T3 has landed, otherwise read `parseViewPath` by eye:
  trace 2-3 routes through it by hand (e.g. `["runs", "abc123", "steps"]`) and confirm the
  returned object matches what you'd expect.
- Confirm `parseViewPath(undefined)` and `parseViewPath(["dashboard"])` both read as "home" in
  the code (no `.find()`/`.match` on an empty array without a guard).

### T3 — Round-trip tests

```bash
cd frontend && npm test -- routes.test.ts
```

- All tests green.
- Count the test cases (`grep -c "it(\|test(" frontend/src/lib/routes.test.ts`) — should be close
  to one per contract route (34+) plus the explicit edge cases (undefined, `["dashboard"]`,
  unknown path, all-params-omitted).

### V1 — Contract validator

Not app-testable yourself — this is the validator's own job. Skip to T4; V1's PASS/FAIL report is
what tells you whether Phase 1 continues.

### T4 — Trace the real `MainView` mapping

Docs-only — nothing to click. Open `specs/015-frontend-routing/data-model.md` and confirm:

- Both former TBD rows now cite a real `MainView` value with a `file:line`.
- No other file in the repo was touched (`git status` shows only `data-model.md`).

### T5 — Relocate the wrapper page

```bash
cd frontend && npm run dev
```

- Open `http://localhost:3000/dashboard` — must render exactly as it did before this task (home
  screen, nothing visually different).
- `ls frontend/src/app/dashboard` — should fail, directory is gone.
- `ls frontend/src/app/[...view]/page.tsx` (or `[[...view]]`, whichever this task landed as) —
  should exist.
- `npx tsc --noEmit` clean; no console errors on load.

### T6 — Seed `mainView` from the path

Paste each of these directly into the address bar (not click-through) and confirm each lands on
the matching screen, not home:

- `/dashboard` → home
- `/create` → create catalog
- `/runs` → run history
- `/workflows` → saved workflows list
- `/library/agents` → library, agents tab
- `/settings/profile` → settings
- `/analytics` → analytics

Then open something nonsensical, e.g. `/zzz-not-a-route` — should NOT blank-render (T19's
not-found isn't built yet, so a generic 404 is fine at this point; a blank white page is not).

Also confirm normal in-app clicking (sidebar nav, etc.) still works exactly as before.

### T7 — Fetch run by id on cold mount

- Launch any run, let it progress a bit, note its id from the URL or run list.
- **Cold-open** `/runs/{that-id}` in a fresh tab (not a click from within the app) — must show
  that run's real content (name, status, steps), not an empty shell.
- Cold-open `/runs/{that-id}/steps`, `/files`, `/audit` — each opens on the correct tab with data.
- From `/runs`, click into that same run (client-side nav, not a fresh tab) — open devtools
  Network tab first, confirm it does **not** re-fire the `getRunSummary`-equivalent request
  (data was already in memory).

### T8 — Fetch saved workflow by id

- From `/workflows`, note a saved workflow's id.
- Cold-open `/workflows/{that-id}/edit` in a fresh tab — Composer opens pre-filled with that
  workflow's real steps/name/selections, not blank.
- Cold-open `/workflows/new` — Composer opens blank (confirm this didn't regress).
- If the saved workflow has sub-agent trees or per-node skills, confirm they're present after the
  cold-open load, not dropped.

### T9 — Push URL on view change

- Click through the app using only in-app navigation (sidebar, cards, buttons) — after every
  click that changes the visible screen, check the address bar updates to match (no full reload,
  just the URL changing).
- `grep -c "setMainView(" frontend/src/components/layout/DashboardLayout.tsx` then eyeball a
  handful of call sites — each should have an adjacent `router.push(routes....)` line.
- Click Back in the browser after 3-4 in-app navigations — lands on the previous screen, URL and
  content both match.

### T10 — Root auth redirect

- While logged in, open `/` directly — redirects to `/dashboard`.
- Log out (or clear the token in devtools Application/Storage), open `/` directly — redirects to
  `/login`.
- Watch closely on both — no flash of the wrong screen before the redirect lands.

### T11 — Cold-mount stream re-attach

- Launch a run, wait for it to be actively streaming (not yet finished).
- **Hard refresh** the browser (Cmd+R / F5, not an in-app link) while on `/runs/{id}/stream` —
  the live stream must re-attach and keep updating; it must not restart from scratch or go blank.
- Open a **completed/failed/cancelled** run's `/runs/{id}/stream` URL directly — should show the
  terminal state in place, not hang trying to open a dead connection.
- Navigate to an actively-streaming run via in-app click (not hard refresh) — open devtools
  Network/WS tab, confirm only one connection opens, not two.

### V2 — Core routing validator (hard gate)

Not app-testable yourself — this is the validator's job, and nothing in Phase 2-5 should be
dispatched until it reports PASS. If you want to spot-check ahead of the validator: open all 34
routes from `contracts/route-map.md` cold, in fresh tabs, confirm each shows real content.

---

## Phase 2 — Shareable views

### T12 · T13 · T14 — List-screen query params

For each of the three screens (`/runs`, `/library/{type}`, `/analytics`):

- Set a filter/sort option in the UI, check the URL updated with the matching query param.
- Copy that URL, open it in a **new private/incognito window**, log in, paste it — same filtered
  view renders (not the default).
- Change the same filter 3 times, then press Back once — you should leave the screen entirely
  (land on the previous page), **not** step back through each filter change one at a time. This
  confirms `replace` is used, not `push`.
- Clear all filters — URL has no dangling `?` or `&`.

### T15 — Library item detail as a page

- Cold-open `/library/agents/{any-real-slug}` — renders that item's detail directly, not the
  library list.
- Repeat for one `skills` slug and one `hooks` slug.
- Open an unknown slug, e.g. `/library/agents/not-a-real-agent` — should fall through to
  not-found behavior (T19 branded page, or generic 404 if T19 hasn't landed yet), not a blank
  panel.

### T16 — Shallow push on modal open

- From the library list, click an item — modal should open **instantly** (no visible page
  reload/navigation flash).
- Check the URL updated to that item's path while the modal is open.
- Press Back — modal closes, you're back on the library list (not a full navigation away).
- Copy the URL while the modal is open, paste into a fresh tab — opens the full detail page
  (T15's behavior), confirming the same URL serves both the modal shortcut and the full page.

### V3 — Shareable-URL validator

Not app-testable yourself — reports PASS/FAIL on T12-T16 as a group.

---

## Phase 3 — Edges & boundaries

### T17 — `/workflow/create` redirect

- Open `/workflow/create?mode=ppt` directly — redirects to `/create/ppt`.
- Open `/workflow/create?mode=prototype` — redirects to `/create/prototype`.

### T18 — `/preview-fullscreen` redirect

- From an active run, open its fullscreen artifact preview (whatever in-app action reaches it),
  note the resulting URL shape.
- Open the **old** `/preview-fullscreen` path/query directly — redirects to
  `/runs/{id}/preview/full`.
- If you can construct a case where no run id is resolvable, confirm it redirects to `/runs`
  rather than erroring.

### T19 — Branded not-found

- Open any nonsense path, e.g. `/this-does-not-exist-at-all` — branded page (matches the app's
  visual language — buttons/cards, not the framework default), with a way back into the app.
- Toggle dark mode (if the app has a toggle) — check the not-found page still looks correct.

### T20 — Branded error pages

- Temporarily add `throw new Error("test")` to some client component's render body, save, trigger
  it — branded error page shows, not Next's default red overlay/stack trace screen.
- **Revert the temporary throw immediately after checking.**
- Confirm dark mode still looks right on the error page too.

### T21 — Delete `/test-preview`

- Open `/test-preview` directly — same not-found behavior as any unknown path (not the mock
  hotel app).
- `grep -rn "test-preview" frontend/src` — no results.
- Spot-check 2-3 unrelated routes still work (deletion didn't collaterally break anything).

### V4 — Edges validator

Not app-testable yourself — reports PASS/FAIL on T17-T21 as a group.

---

## Phase 4 — Access & session

### T22 — Centralized 401 redirect

- Log in, then manually clear or corrupt the stored token in devtools (Application → Local/Session
  Storage), then trigger any API call (e.g. click to a data-fetching screen) — redirects to
  `/login?expired=1`.
- Check storage again — token is actually gone, not just ignored.
- On `/login` itself, enter wrong credentials — inline error shows, page does **not**
  redirect-loop back to `/login?expired=1`.

### T23 — Expiry message

- Open `/login?expired=1` directly — visible "session expired" message appears above the form.
- Open plain `/login` (no query) — no expiry message, form looks normal.

### T24 — Ownership failure → not-found

- Using a second test account (or a run/workflow id known to belong to someone else), open
  `/runs/{other-account-run-id}` — not-found/no-access shown, and confirm via devtools Network
  tab that the actual run content never appears in the response body rendered to the page.
- Open a deleted/nonexistent run id — same not-found behavior, not a crash.
- Confirm a 401 (T22's case) and a 403/ownership failure (this task's case) visibly go to
  **different** places (login vs. not-found) — don't let them collapse into one behavior.

### V5 — Auth-boundary validator

Not app-testable yourself — reports PASS/FAIL on T22-T24 as a group. This one's security-adjacent;
if you want to spot-check ahead of it, repeat T22-T24's checks on at least one route from each
area (auth, home, runs, workflows, library, settings/analytics) rather than just one.

---

## Phase 5 — Completion & acceptance

### T25 — Launch navigates to the stream

- Launch a run from the home/create flow — lands on `/runs/{newId}/stream` immediately (URL
  changes, stream starts).
- Launch a run from `/workflows/{id}/run` (a saved workflow) — same landing behavior.
- If a "revision" launch path exists (e.g. re-running a ppt/prototype), test that one too.

### T26 — Edit affordance

- Open `/workflows`, find any saved workflow — an "Edit" action/button is visible on it without
  needing to type a URL.
- Click it — lands on `/workflows/{id}/edit`, Composer pre-filled (T8's behavior).
- Confirm the existing Launch and Delete actions on that same card still work unchanged.

### T27 — Screen label helper

Code-level check, nothing visibly different in the UI yet.

- Read `screenLabel` in `frontend/src/lib/routes.ts`, spot-check 3-4 outputs by hand against
  routes you know — confirm none collide (e.g. `/runs` and `/runs/{id}` don't return the same
  label).

### T28 — Thread label into tracking

- Open devtools (Network tab, filtered to whatever analytics/error endpoint the app already
  calls, or the Console if it logs there instead).
- Walk 4-5 different screens — confirm each fires with a distinct, correct label (not a shared
  generic one, not blank).

### V6 — Completeness validator

Not app-testable yourself — reports PASS/FAIL on T25-T28 as a group.

### V7 — Full acceptance validator (hard gate)

Not app-testable yourself — sweeps all 15 FRs and 9 SCs. Once it reports PASS, move to T29.

### T29 — User acceptance pass

Run [`quickstart.md`](quickstart.md) end-to-end, in one sitting, in a real browser. This is the
only step that actually closes the spec — no agent substitutes for it.

---

## Quick reference: what "done" looks like per task

| Task | One-line pass signal |
|---|---|
| T1 | `routes.ts` has a builder per contract route; `tsc` clean |
| T2 | `parseViewPath` round-trips by hand-trace; `tsc` clean |
| T3 | `npm test -- routes.test.ts` green, ~34+ cases |
| T4 | `data-model.md` has zero TBD rows, each cited `file:line` |
| T5 | `/dashboard` renders unchanged; `app/dashboard/` gone |
| T6 | 7 non-id routes each land on their own screen, pasted cold |
| T7 | Cold `/runs/{id}*` shows real data; no double-fetch on client nav |
| T8 | Cold `/workflows/{id}/edit` shows real pre-filled Composer |
| T9 | Every click-nav updates the URL; back/forward works |
| T10 | `/` → `/dashboard` or `/login` correctly, no flash |
| T11 | Hard refresh on `/runs/{id}/stream` re-attaches live |
| T12-14 | Filtered URL reproduces in a fresh session; uses `replace` |
| T15 | `/library/{type}/{slug}` cold-opens the real detail page |
| T16 | Modal opens instantly + pushes URL; back closes it |
| T17-18 | Both retired paths redirect, no 404 |
| T19-20 | Branded not-found/error pages, both themes |
| T21 | `/test-preview` gone, zero greps left |
| T22 | 401 from anywhere → `/login?expired=1`, token cleared |
| T23 | `?expired=1` shows the message; plain `/login` doesn't |
| T24 | Cross-account/deleted id → not-found, no data leak |
| T25 | Every launch path lands on `/runs/{newId}/stream` |
| T26 | Edit button reachable from `/workflows` list |
| T27-28 | Every screen fires a distinct, correct tracking label |

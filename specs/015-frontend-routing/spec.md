# Feature Specification: Frontend Routing — one real URL per screen

**Spec ID**: 015-frontend-routing
**Created**: 2026-08-20
**Status**: Draft — ready for `/speckit-clarify`
**Root**: `frontend/src/app/`
**Grounding**: `VELOCITY_GO_LIVE/checklist.md` §5.2.1–5.2.5 (routing current-state audit and target route map) and `specs/014-conditional-gates/spec.md` §4.4 (run-history linking that depends on real run-detail routes).

---

## Clarifications

### Session 2026-08-20

- Q: Should 015 absorb 014's frontend canvas requirements (R-21–R-25) or the go-live checklist's
  other non-routing frontend items? → A: No — keep specs fully separate. 015 picks up routing
  only; 014 stays the sole owner of its own frontend (canvas/composer) scope.
- Q: Of the go-live report's remaining frontend items, which are small enough and routing-tree-
  adjacent enough to fold into 015 anyway? → A: Three — BLK-11 (branded `error.tsx` +
  `global-error.tsx`, sibling boundary files to `not-found.tsx`/FR-008), BLK-13 (delete
  `/test-preview`, a route-tree removal), and the 401/session-expiry → `/login?expired=1`
  redirect (a redirect target, extends FR-009). Everything else (BLK-14's login bug, global-nav
  retention, JWT httpOnly migration) stays out — not about URL/route identity, or too large to
  be "easy."
- Q: FR-013/014/015 have no matching Success Criteria — add matching SC entries now, or leave
  them verified directly from the FR text? → A: Add matching SC entries (Option A), mirroring the
  existing SC-001-style pattern.

### Session 2026-08-21

- Q: Post-close, a live check found the library's 3 category LIST screens
  (`/library/agents`, `/library/skills`, `/library/hooks`) never updated the URL when switching
  tabs — the address bar and the visibly active tab could go out of sync, and sharing the URL
  after switching tabs shared the wrong tab. Fix in place, or leave the 3-path-segment shape and
  accept the bug? → A: Merge the 3 list screens into ONE path, `/library` with the tab and
  category as query params (`?tab=&category=`), `tab` omitted for `agents` (the default) —
  matching how `category` was already omitted for `all` elsewhere in this feature. Fixes the
  URL-sync bug (the tab switcher now calls `router.replace` on every tab change) and simplifies 3
  parallel routes into one screen with a tab switcher. Item-DETAIL routes
  (`/library/agents/{slug}`, `/library/skills/{slug}`, `/library/hooks/{slug}`) are unaffected.
  Old list URLs still resolve via redirect (`contracts/route-map.md`'s Retired paths table); §5's
  original screen-inventory table below is left as the historical record of what was originally
  specified and shipped.

## 1. Problem

Ten distinct screens — home launch grid, run history, run detail (with five sub-tabs), saved
workflows list, workflow read view, library (three categories), settings (four tabs), and
analytics — all live inside one 2,862-line page and share a single URL, `/dashboard`. Which
screen is showing is tracked only in in-memory component state, never in the address bar.

The consequences are concrete and already causing product problems: a user cannot bookmark or
share a link to a specific run, a specific saved workflow, or a specific library item. Refreshing
the browser — including mid-run, while a live agent stream is in progress — throws the user back
to the home screen and loses the stream. Back/forward navigation does nothing useful inside the
app. Nothing about which screen a user is looking at reaches error tracking or product analytics,
because there is no page dimension to attach to those events.

Two flows already break this pattern inconsistently: launching a workflow does navigate
(`/workflow/create?mode=...`), while everything else does not — so the app is not "unrouted," it
is routed unevenly, which is its own source of confusion for anyone extending it.

## 2. What it does

**Every screen a user can stand on gets its own URL that survives a refresh, survives
back/forward, and can be pasted into a new tab or a bug report to return to exactly that
screen.** Filters and sort choices on list screens (run history, library categories, analytics
date range) become part of the URL as query parameters, not hidden state. Transient UI — a
confirmation dialog, a dropdown — stays as in-page state, except for library item details, which
graduate from a modal into a shareable page of their own.

The live run stream becomes reachable at its own URL. Launching a run navigates there
immediately, and refreshing that URL while the run is still in progress re-attaches to the same
live stream instead of losing it.

Old links that pointed at the previous ad-hoc paths (`/workflow/create?mode=...`,
`/preview-fullscreen`) redirect to their new equivalents rather than breaking.

## 3. User Scenarios & Testing *(mandatory)*

### Primary user story

A user launches a workflow, watches it run, and wants to send a colleague a link to the finished
result. Today they cannot — there is nothing to send but "go to the dashboard and find it
yourself." With this feature, every stage of that journey — the launch, the in-progress stream,
and the finished run — has its own URL, and the one they send opens directly to what they meant
to share.

### Acceptance scenarios

1. **Given** a user is viewing any screen in the app, **When** they copy the current URL and open
   it in a fresh, unauthenticated-then-logged-in browser tab, **Then** they land on exactly the
   screen they copied it from — not the home screen.
2. **Given** a run is actively streaming live output, **When** the user refreshes the page,
   **Then** the page reconnects to the same in-progress stream and shows its current state,
   rather than restarting or losing progress.
3. **Given** a user is several screens deep (e.g., library → agent detail → back to library
   filtered by category), **When** they use the browser's back and forward buttons, **Then** each
   press moves them to the exact prior or next screen, in order.
4. **Given** a user has an old, previously-shared link to a screen that has since moved,
   **When** they open that old link, **Then** they are redirected to the screen's new location
   rather than seeing an error.
5. **Given** a user pastes an unrecognized URL under the app's domain, **When** the page loads,
   **Then** they see a clear "not found" screen with a way back into the app, not a blank page or
   crash.
6. **Given** a user filters or sorts a list screen (run history, a library category, analytics by
   date range), **When** they share that exact URL with someone else, **Then** the recipient sees
   the same filtered/sorted view, not the default one.

### Edge cases

- What happens when a user opens a run-detail or workflow-detail URL for a record that has since
  been deleted, or that they do not own? → Must show a clear "not found or no access" state, not
  leak another user's data and not crash.
- What happens when a user is not logged in and opens a deep link to a protected screen? → Must
  redirect to login, then land on the originally-requested screen after a successful login.
- What happens when a run transitions to a terminal state (completed, failed, cancelled, or
  diverted to another run — see spec 014) while the user is sitting on its live-stream URL? →
  The screen must reflect the new terminal state in place, without requiring a manual refresh or
  a broken stream connection.

## 4. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST give every screen listed in §5's inventory a distinct, stable URL
  such that no two screens share a URL and no screen is reachable only through in-page state.
- **FR-002**: The root URL MUST route an authenticated user to the home screen and an
  unauthenticated user to login — never both to login regardless of auth state, as happens today.
- **FR-003**: Reloading the browser on any screen's URL MUST restore that same screen with its
  current data, including a run's live-stream screen while the run is still in progress.
- **FR-004**: Back and forward browser navigation MUST move between the screens a user actually
  visited, in the order visited.
- **FR-005**: List-screen filters and sort order (run history's type/sort, a library category
  filter, analytics' date range and pipeline filter) MUST be encoded in the URL so that sharing
  the URL reproduces the same filtered/sorted view for another user.
- **FR-006**: Library item detail (agent, skill, hook) MUST be reachable at its own URL,
  independent of the library list screen it was opened from.
- **FR-007**: Every previously-existing ad-hoc path that this feature supersedes MUST redirect to
  its new equivalent URL rather than 404ing or breaking.
- **FR-008**: An unrecognized URL under the app's domain MUST show a branded "not found" screen
  with a path back into the app, distinct from an application error.
- **FR-009**: Opening a deep link to a screen the current user does not have access to (not
  logged in, or not the owner of the referenced run/workflow) MUST show an access-appropriate
  message (login redirect, or "not found/no access") rather than leaking data or crashing.
- **FR-010**: Launching a run MUST navigate the user to that run's own live-stream screen
  immediately, not leave them on the screen they launched from.
- **FR-011**: A saved workflow MUST be reachable, from its own URL, in both a read-only view and
  an editable view — closing the current gap where a saved workflow has no editing entry point.
- **FR-012**: The screen a user is currently on MUST be identifiable as a distinct label wherever
  the product records errors or usage events, so that error tracking and analytics can be broken
  down by screen.
- **FR-013**: An unhandled application error on any screen MUST show a branded error page distinct
  from the "not found" state (FR-008), rather than an unbranded crash screen.
- **FR-014**: The developer test fixture currently reachable at `/test-preview` MUST be removed
  from the route tree entirely — not merely unlinked from navigation.
- **FR-015**: A session that has expired (an authenticated request rejected as unauthorized) MUST
  redirect the user to login with a visible "your session expired" message, from any screen in the
  app, not only the ones that already handle this today.

### Key Entities

- **Screen**: A distinct view a user can navigate to and stand on — the unit this feature gives
  a URL to. Roughly 35 screens are in scope, grouped by area: auth, home & creation, runs (with
  run-detail sub-views), saved workflows, library (three categories, each with list + detail),
  settings (four tabs), and analytics/admin.
- **Run**: A single execution of a workflow; has an identity that its detail, steps, files,
  audit trail, and live stream screens are all addressed by.
- **Saved workflow**: A user-authored workflow definition, distinct from any particular run of
  it; has its own read and edit screens.
- **Library item**: An agent, skill, or hook a user can view details about; belongs to one of
  three categories, each independently filterable and each item independently linkable.

## 5. Screen inventory (target state)

| Area | Screens | Count |
|---|---|---|
| Auth & root | login, register (root redirects, not its own screen) | 2 |
| Home & creation | home launch grid, full catalog, 4 pipeline-specific creation screens, blank composer | 7 |
| Runs | history list, detail (preview/steps/step-detail/files/audit/live-stream/version/fullscreen) | 9 |
| Saved workflows | list, read view, edit view, launch-and-run | 4 |
| Library | 3 category lists + 3 category detail-item screens | 6 |
| Settings, analytics, admin | 4 settings tabs, analytics, admin | 6 |
| **Total distinct screens** | | **34** |

Three additional entries are pure redirects (root, library index, settings index), not
standalone screens, and three legacy paths are retired via redirect. None of these count as
new screens under FR-001.

**Out of the inventory by design: the handoff screens.** Three further screens exist today
(`/handoff`, `/handoff/{token}`, `/handoff/settings`). They **already** have their own real,
URL-addressable routes — they never lived inside the shared-URL page — so FR-001 is already
satisfied for them and this spec changes nothing about them. They are excluded from the count of
34 and from `contracts/route-map.md` for that reason, not by oversight. The one requirement that
still reaches them is FR-015 (session expiry must redirect from *any* screen), so they are
included in SC-009's per-area verification.

## 6. Out of scope

- **Splitting the underlying page component into separate route-segment files.** This spec
  requires every screen to have its own URL; it does not require the implementation to stop
  sharing layout code behind those URLs. How much internal restructuring accompanies the URL
  change is an implementation decision for planning, not a requirement here.
- **All of spec 014's frontend/canvas scope** — the conditional-gate route-target editor, the
  external-pipeline reference node, the composer's graph-layout rework, serialization changes,
  and the "diverted run" linking UI (spec 014 §4.4–§4.5). Confirmed via clarification (see
  above): the two specs stay fully separate rather than merging or cross-duplicating
  requirements. 014's frontend work depends on this spec's run-detail and live-stream URLs
  existing, but building any of it is 014's scope, not this one's.
- **Any change to what data a screen shows** — this spec is only about giving existing screens
  stable, shareable addresses; it does not add, remove, or redesign any screen's content.
- **The `/login` page's existing runtime error and styling defect (go-live report BLK-14)** — a
  rendering/contrast bug on an already-existing page, not a URL/routing concern.
- **Global navigation not rendering on `/workflow/create` config pages** — a layout-consistency
  bug, not about the page's URL identity.
- **Migrating JWT storage from localStorage to httpOnly cookies** — a real security change
  requiring new backend cookie issuance; FR-015 only covers the redirect-on-expiry behavior, not
  where the token is stored.

## 7. Success Criteria *(mandatory)*

- **SC-001**: 100% of the screens in §5's inventory (34) are reachable at a distinct URL, and
  pasting any one of them into a fresh browser tab restores exactly that screen.
- **SC-002**: Refreshing the browser on any screen, including a run's live-stream screen mid-run,
  never loses the user's place or an in-progress stream.
- **SC-003**: Back/forward navigation correctly retraces a user's last 10 in-app navigations in
  a manual test pass, with zero incorrect screens shown.
- **SC-004**: Every previously-shared or bookmarked link under a retired path redirects
  successfully rather than erroring, verified against the full list of retired paths.
- **SC-005**: A shared URL carrying a filter or sort choice reproduces the identical filtered
  view for a second user, verified for run history, one library category, and analytics.
- **SC-006**: Error-tracking and analytics events captured during a manual walkthrough of all 34
  screens each carry a distinct, correct screen label.
- **SC-007**: An unhandled error thrown on any screen shows the branded error page (FR-013), not
  the framework's default crash screen, verified by deliberately throwing on at least one screen
  of each type (client component, route handler).
- **SC-008**: `/test-preview` returns the same "not found" outcome as any other unrecognized URL
  (FR-014), verified directly and via a search of the built bundle for zero remaining references.
- **SC-009**: A request made with an expired/invalid session from any of the 34 screens lands the
  user on `/login` with a visible expiry message (FR-015), verified for at least one screen from
  each area in §5's inventory.

## Assumptions

- The routes that already exist today (`/`, `/login`, `/register`, `/dashboard`, `/admin`, and
  the workflow-create launch flow) are retained and folded into the target inventory rather than
  replaced outright. The three handoff routes are the exception — already correctly routed, so
  excluded from the inventory entirely (see §5).
- "Diverted" and other terminal run states are display concerns on the existing run-detail and
  live-stream screens (FR-003, edge cases §3) — this spec ensures those screens exist and handle
  a state change in place; it does not define the diverted-state visuals themselves, which spec
  014 owns.
- Query-parameter encoding (FR-005) is a requirement on behavior (shareable, reproducible views),
  not a mandate for a specific technical mechanism — left to planning.

# 015 — Quickstart: verifying frontend routing works

How to confirm each phase of [plan.md](plan.md) actually landed, checked manually in a browser
against `contracts/route-map.md`'s full route list — no new automated-test infra required by
this spec, but each check below maps to one of spec.md's SC-00x criteria.

## After T1–T11 (foundation + core routing) — gated by V1, V2

```bash
cd frontend && npm run dev
```

- Log in, then open each of the 34 routes in `contracts/route-map.md` directly (paste into the
  address bar) — each must restore the exact matching screen, not the home screen. *(SC-001)*
- Launch a run, then hard-refresh the browser (not just navigate) on `/runs/{id}/stream` while
  it's still running — the live stream must re-attach and keep updating, not restart or go
  blank. *(SC-002)*
- Navigate library → agent detail → back to library filtered by category → an agent detail →
  back → back — use only the browser's back/forward buttons and confirm each press lands on the
  correct prior/next screen. *(SC-003)*
- Open `/` both logged in and logged out — confirm it goes to `/dashboard` and `/login`
  respectively, never both to `/login`.

## After T12–T14 (query-param filters)

- On `/runs`, set a type/sort filter, copy the URL, open it in a private/incognito window (fresh
  session) — after logging in, the same filtered/sorted view should render. Repeat for one
  library category and for `/analytics`. *(SC-005)*

## After T15–T16 (library detail pages) — with the above, gated by V3

- Paste `/library/agents/{any-slug}` (and one skills, one hooks slug) directly into a fresh tab —
  each should render that item's detail page directly, not the library list.

## After T17–T18 (retired-path redirects)

- Open `/workflow/create?mode=ppt` — should redirect to `/create/ppt`.
- Open `/preview-fullscreen` (with whatever query shape it used) — should redirect to
  `/runs/{id}/preview/full`. *(SC-004)*

## After T19–T21 (not-found / error / test-preview) — with the above, gated by V4

- Open any nonsense path, e.g. `/this-does-not-exist` — branded not-found page, not blank/crash.
- Open `/test-preview` — same not-found outcome as above, not the mock hotel app. *(SC-008)*
```bash
grep -r "test-preview\|AppBuilderPreview.*MOCK_FILES" frontend/src --include="*.tsx" -l
```
  should return nothing referencing the deleted fixture.
- Force a thrown error on one client component (temporary `throw new Error("test")` — revert
  after checking) — should show the branded error page, not the framework default. *(SC-007)*

## After T22–T24 (deep-link access + session expiry) — gated by V5

- Log out (or manually clear/corrupt the stored token), then open any of `/runs/{id}`,
  `/workflows/{id}`, `/library/agents`, `/analytics` — each should redirect to
  `/login?expired=1` with a visible "session expired" message. Repeat for at least one route
  from each area in spec.md §5's inventory. *(SC-009)*
- Open a `/runs/{id}` for a run belonging to a different account — should show not-found/no-access,
  never that run's real data.

## After T25–T26 (run-launch nav + saved-workflow edit)

- Launch a run from `/workflows/{id}/run` — must land on `/runs/{newId}/stream` immediately.
- Open `/workflows/{id}/edit` for any saved workflow — Composer opens pre-filled; make an edit,
  save, confirm it persists.

## After T27–T28 (observability screen label) — with the above, gated by V6

- Walk all 34 routes once with browser devtools open on whatever error-tracking/analytics call
  the app already makes (network tab or console, depending on current wiring) — confirm each
  fires with a distinct, correct screen label rather than a shared/generic one. *(SC-006)*

## Full acceptance pass

Once all five phases (T1–T29, all validators green) are done, `contracts/route-map.md`'s full table plus the retired-path list
is the acceptance checklist — every row should behave exactly as described, verified in one
sitting before calling this spec done.

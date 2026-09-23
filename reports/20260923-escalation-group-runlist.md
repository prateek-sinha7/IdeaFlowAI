# QA-PS-035 / 036 / 038 / 041 / 046 — group root-cause and fix

Read-only investigation. No source, test, or register file was edited.

## DECISION RECORDED (2026-09-23): Option (a) — accept the shell traffic, re-scope the tests

The user chose **option (a)** from §7/§5 of the per-bug escalations: keep the app shell's one
`/api/runs?limit=50` + one `/api/workflows` call on every non-home route (it is real, consumed
data — `AppHeader`'s badge and `RunConnectionProvider`'s SSE re-attach, see §2), and re-score
each bug's test from "zero run/workflow calls" to "at most one of each, after §1+§2's dedup
fix." `BUGS.md`'s "Problem 2" / "not needed on this page" premise is answered "working as
designed" for all five, same as each escalation's own §"What happens after the decision — Option
a)" already specified.

**This analysis pass cannot execute the decision** — it is read-only on `frontend/`, `backend/`,
and on `LEDGER.md`/`BUGS.md`/`ESCALATIONS.md` by the hard rules it was dispatched under. What
still has to happen, by the pipeline's next stages, is unchanged from what each escalation
already wrote under "Option a)":

1. **Land §1+§2 of this report first** (the `fetchRecentRuns` re-homing to `HomeLaunchGrid`, and
   the `RunConnectionProvider`/`page.tsx` fetch merge) — this is what shrinks the floor each test
   gets re-scored against from today's 2×/2× down to the true 1×/1×. Without it, "re-scope to
   one" re-scopes against a still-doubled number.
2. **4-test-writer** re-scopes the five files named in §5's table (`test_qa_ps_035_...`,
   `test_iss782_...`, `test_qa_ps_038_...`, `test_qa_ps_041_...`,
   `test_qa_ps_046_...`) from a zero-call assertion to a one-call-each assertion, per the
   "Option a)" paragraph already written in each bug's `ESCALATIONS.md` section.
3. **6-verifier** re-runs those five files.
4. Whoever owns the register updates `LEDGER.md`/`ESCALATIONS.md`: Status moves off `ESCALATED`
   for QA-PS-035/036/038/041/046 (and 037, named by the same decision in `ESCALATIONS.md`), each
   closing on its already-in-tree fix (FIX-618, FIX-617, FIX-624, FIX-627, FIX-629) plus this
   report's §1+§2 dedup change; ISS-781/782/785/788/832's "Problem 2"/zero-request expectation
   gets superseded, exactly as each escalation's "What happens after the decision" already says.

This report's own recommendation (§7) was already "(a) is the right call, with §1+§2 landed
first to shrink the floor before re-scoring against it" — the user's choice matches that
recommendation.

## 0. What the five escalations already established (not re-derived here)

`ESCALATIONS.md` for all five bugs independently traced the residual traffic to the same two
sources and correctly identified that removing it outright is a product call, not a difficulty:

- `GET /api/workflows` + `GET /api/runs?limit=6` — the sign-in preload
  (`frontend/src/store/listenerMiddleware.ts:25-70`), fired from `signedIn`, which is dispatched
  unconditionally by the catch-all route on every path
  (`frontend/src/app/[...view]/page.tsx:955-957`).
- `GET /api/runs?limit=50` — `page.tsx`'s own `recentRuns` fetch, threaded into the
  always-mounted `AppHeader` for its "N Running" badge/dropdown.

That framing is right but incomplete in one respect that changes the fix: **it treats "the
`limit=6` preload" and "the `limit=50` page.tsx fetch" as one bundle needing one decision.** They
are not the same mechanism, do not share a consumer, and do not carry the same risk. Splitting
them produces a fix for part of the traffic that needs no decision at all, and — for the part
that genuinely is shell traffic — a fix that halves it without touching ISS-232 or the badge.

## 1. Root cause A — the `limit=6` preload has no consumer outside `/dashboard` (no product decision needed)

**Claim, CONFIRMED:** `fetchRecentRuns()` (`GET /api/runs?limit=6`) populates Redux
`state.global.recentRuns`, and that slice has exactly **one** reader app-wide:
`HomeLaunchGrid.tsx:148` (`useAppSelector((state) => state.global.recentRuns)`), used only as a
fallback for first paint before the live `recentRuns` prop arrives
(`HomeLaunchGrid.tsx:156-198`). `HomeLaunchGrid` itself only renders when `mainView === "home"`
(`frontend/src/components/layout/DashboardLayout.tsx:2896`) — it is not part of the always-on
shell. `AppHeader` does **not** read `state.global.recentRuns` anywhere; grep across
`AppHeader.tsx` shows it only takes `recentRuns` as a **prop** (see Root cause B).

Yet the fetch fires unconditionally on every route:

- `frontend/src/app/[...view]/page.tsx:955-957` — `dispatch(signedIn({ token: storedToken }))`,
  inside the mount effect of the catch-all component that serves every URL.
- `frontend/src/store/listenerMiddleware.ts:50-56` — the `signedIn` listener dispatches
  `fetchWorkflows()` **and** `fetchRecentRuns()` together, gated only on Redux status, not on
  route.
- `frontend/src/store/slices/globalSlice.ts:36-45` — `fetchRecentRuns`'s own doc comment:
  "the 'Jump back in' seed for HomeLaunchGrid's first paint" — it was built as
  HomeLaunchGrid-only, not shell-wide.

So on `/settings/*`, `/analytics`, `/workflows`, `/workflows/new`, `/runs/{id}` — every route in
this group — the app fetches 37 KB into a slice nothing on screen reads.

**Why this is not ISS-232.** `listenerMiddleware.ts:41-49`'s ISS-232 comment is about the two
dispatch *groups* — `preloadHome` (`fetchWorkflows` + `fetchRecentRuns`) vs. `preloadLibrary`
(agents/skills/hooks) — being awaited in parallel instead of sequentially, because a slow
`/api/workflows` used to block the Library tabs for 12.2s. `fetchRecentRuns` was carried along in
the `preloadHome` array for symmetry; the measured regression was never about it. Removing it
from that dispatch does not resurrect the sequential-await bug, because `fetchWorkflows()` keeps
firing unconditionally in the same parallel `Promise.all` regardless of what happens to its
sibling.

**Fix — smallest diff, no product decision:**

- `frontend/src/store/listenerMiddleware.ts:54-56` — delete the `fetchRecentRuns()` branch from
  the `signedIn` effect (`fetchWorkflows()` stays; it has a real app-shell consumer,
  `AppHeader.tsx:138`'s `useWorkflowLabels()`, so it is not the same case).
  `frontend/src/store/slices/globalSlice.ts`'s `fetchRecentRuns` thunk is unchanged and still
  exported.
- `frontend/src/components/catalog/HomeLaunchGrid.tsx` — add a mount effect next to the existing
  `reduxRecentRuns`/`recentRunsStatus` selectors (lines 148-150) that dispatches
  `fetchRecentRuns()` itself, guarded the same way the listener guarded it
  (`recentRunsStatus !== "loading" && !== "succeeded"`). Needs one new import,
  `useAppDispatch` from `@/store/hooks` (the file currently imports only `useAppSelector`,
  confirmed at `HomeLaunchGrid.tsx:33`). This is the same "component owns its own preload"
  shape `page.tsx` already uses for its own `recentRuns` effect
  (`recentRunsRequestedRef`/`viewPathKey`, see below) — not a new pattern.
- Net effect: `/api/runs?limit=6` drops from "every route" to "home route only," with the same
  data arriving through the same slice, one render tick later than today (React flushes a
  child's own mount effect in the same pass as the parent's, so there is no meaningful latency
  regression — INFERRED, not benchmarked; the task's no-server-restart rule means this was not
  measured live).

This alone removes one of the two `/api/runs?limit=6` calls the escalations' own evidence
recorded for QA-PS-035/036/041/046 on every non-home cold load (`ESCALATIONS.md` evidence blocks
for each bug). It does not touch the second `limit=6` duplication noted in QA-PS-035's evidence
#5 (`ISS-784/793/794`'s still-unexplained x2 inside one `signedIn` firing) — that is a distinct,
already-tracked defect, not part of this group's root cause, and is untouched by this fix.

## 2. Root cause B — `limit=50` is fetched by two independent owners for two different derived purposes

**Claim, CONFIRMED.** There are exactly two client call sites that fetch the full 50-row list on
a cold, authenticated load, and neither knows about the other:

1. `frontend/src/app/[...view]/page.tsx:1079` — `getWorkflows(currentToken, { limit: 50 })`,
   guarded per-mount by `recentRunsRequestedRef` (`page.tsx:843`) and, across client-side
   remounts, by a **module-scope** cache, `recentRunsSnapshot` (`page.tsx:118`, written at
   `:1081`, kept fresh by every write path per the comment at `:1102-1113`). Feeds local state
   `recentRuns`/`recentRunsLoaded`, passed to `DashboardLayout` and from there into `AppHeader`
   (`DashboardLayout.tsx:2720` `<AppHeader`, `:2754` `recentRuns={recentRuns}`, **before** any of
   the `mainView` branches at `:3037` settings / `:3054` analytics / `:3068` saved-workflows /
   `:3118` composer). `AppHeader` consumes it at `AppHeader.tsx:188`
   (`liveRunsFromServer = recentRuns.filter(...)`), `:200` (`hasServerData`), `:328`
   (`serverRun = recentRuns.find(...)`), `:371` (`{runningPipelines.length} Running`). This part
   of the escalations' evidence is accurate and reproduced here independently.
2. `frontend/src/providers/RunConnectionProvider.tsx:319` — `getWorkflows(t, { limit: 50 })`,
   inside `refreshLiveRuns` (`:279-331`), fired on boot (`:334-337`) and again on every
   `visibilitychange`-to-visible and `online` event (`:342-355`). This is the literal
   implementation of "SSE live-run re-attach" the task brief names: the provider's own doc
   comment (`RunConnectionProvider.tsx:15-19`) calls it "Server-derived reattach... on
   boot/reconnect it QUERIES the user's live runs." It derives `autoIdsRef`
   (`:320-326`) from the response and **discards the `runs` array itself** — nothing downstream
   of this call can reuse the rows it just fetched.

Both call the same `getWorkflows()` (`frontend/src/lib/api.ts:922-944`), which has a
**single-flight** de-dupe only (`inFlightWorkflows`, `api.ts:920`, comment at `:903-919`,
originally added for ISS-783/QA-PS-037's `/runs` page) — it joins two callers only if they are
in-flight at the *exact same moment*. FIX-618's own record (quoted in QA-PS-035's evidence #5)
already found these two sites are "ticks apart," so the guard usually misses them and both hit
the network. `api.ts:404-406` documents this as deliberate for **mutation-observing** refetches
("their callers refetch precisely to observe a change, e.g. a cancel clearing the header's 'N
Running' pill") — a reasonable rule for a post-action refetch, but it is being applied
uniformly to two **simultaneous cold-boot reads** that want the same rows for two different
derived views, which is a different situation the rule was not written for.

**This is a genuine architectural gap, not the product decision.** Even granting that the shell
needs live-run data everywhere (true — confirmed by both consumers above), there is no reason it
needs **two independent fetches** of the same resource to get it.

**Where the fix belongs.** `RunConnectionProvider` is already the structurally correct single
owner:

- It is mounted **above** the router (its own doc comment, `RunConnectionProvider.tsx:9-13`,
  explains this was deliberate so the SSE connection survives route changes) — strictly higher
  than `page.tsx`, which is itself the catch-all for every route but is still one layer down.
- It already exposes a context (`RunConnectionContext`/`useRunConnection()`,
  `RunConnectionProvider.tsx:145-150`) that `page.tsx` **already consumes** for other things
  (`page.tsx:2279`, `const runConnection = useRunConnection();`) — adding `recentRuns` and
  `recentRunsLoaded` to `RunConnectionContextValue` (currently `enabled, phase, liveRunIds,
  reattach, attachRun, detachRun, subscribe, sendCommand`, `RunConnectionProvider.tsx:96-127`) is
  an extension of a seam `page.tsx` already uses, not a new one.
- It already fetches the exact payload; today it just throws away everything except the derived
  id list.

**Recommended fix:**

- `RunConnectionProvider.tsx` — in `refreshLiveRuns` (`:279-331`), keep the fetched `runs` in a
  new piece of state (`recentRuns`, plus a `recentRunsLoaded` flag mirroring `page.tsx`'s
  `ISS-757` one at `AppHeader.tsx:83-89`) and expose both on `RunConnectionContextValue` /
  `DEFAULT_VALUE` (`:96-143`).
- One behavior change required, not optional: the early return at `:312-316` ("skip the query
  when `tabOwnedIds.size === 0`") was correct when the only consumer was the auto-attach filter,
  which has nothing to do with an empty tab-owned set. It is **not** correct once this same
  fetch also feeds the badge, because the badge needs the full list (including runs launched in
  *other* tabs) regardless of what this tab owns. That branch needs to keep skipping the
  *auto-attach computation* but not the network call. Net effect app-wide is still a reduction
  (2 calls to 1), but this specific branch's own call count does not drop to zero the way it
  does today in the zero-tab-owned-runs case — call this out to whoever implements it so it is
  not "fixed" back to a skip that silently blinds the badge.
- `page.tsx` — delete its own `getWorkflows(currentToken, { limit: 50 })` mount effect
  (`:1056-1100`), the `recentRunsRequestedRef` guard (`:843`) and the module-scope
  `recentRunsSnapshot` cache (`:118`, and its keep-fresh effect at `:1109-1113`) — all three
  exist only to solve problems (remount dedup, cross-mount persistence) that evaporate once the
  data lives in a provider that never unmounts across route changes. Read
  `runConnection.recentRuns` / `runConnection.recentRunsLoaded` instead of local state.
- The three **legitimate** mutation-observing `getWorkflows(..., {limit:50})` calls stay
  untouched and keep hitting the network directly, per `api.ts:404-406`'s own rule — they are
  not part of this root cause:
  - `page.tsx:1860` — the `pipeline_diverted` SSE handler (ISS-842/846/QA-PS-047), gated by
    `recentsToken()` so it is skipped during durable replay (see §3).
  - `page.tsx:4421` — the post-launch refresh (FIX-195/ISS-061) so a just-launched run appears
    in the badge immediately.
  - `WorkflowHistory.tsx:229,250,271,315` — the `/runs` route's own list rendering. This is a
    different, already route-scoped, already-tracked family (QA-PS-050/ISS-785, not in this
    group) and is out of scope here; do not fold it into this fix.

**No backend change required for this half.** `getWorkflows()` and `refreshLiveRuns` keep calling
the same endpoint with the same `limit=50`; only which layer owns the single call changes.

## 3. QA-PS-038 — same root cause for its residual traffic; the replay defect is a separate, already-fixed mechanism

Two distinct mechanisms were bundled under one bug number, and they resolve differently:

- **Mechanism 1 (the bug's headline, "12+ times from durable replay"): already fixed, and not
  part of this group's root cause.** `page.tsx:1122-1129`'s `handleWebSocketMessage` now takes
  an `isReplay` flag; `recentsToken()` (defined right there) returns `null` during replay so
  none of the eight bindings refetch. This is FIX-624, already in the tree, confirmed present at
  the current line numbers during this read. No further action needed on this mechanism.
- **Mechanism 2 (the residual 6 calls the QA-PS-038 test still counts): the exact same root
  cause as §1/§2.** The escalation's own probe shows the six break down as the app shell's
  per-mount traffic multiplied by however many **full navigations** (`page.goto`, not
  `router.push`) the test's reproduction does before the click: each `page.goto` is a real
  document reload, which resets `page.tsx`'s per-mount `recentRunsRequestedRef` **and** the
  module-scope `recentRunsSnapshot` **and** `RunConnectionProvider`'s own state, so a fresh
  `limit=6` and up to two fresh `limit=50` calls fire on every one of those reloads, before the
  in-app click that is what the bug is actually about ever happens. Root cause A removes the
  `limit=6` contribution; root cause B halves the `limit=50` contribution per reload. Neither
  fix is replay-specific — they are the same fix as QA-PS-035/036/041/046, applied once, at the
  same two locations.

Answer to the task's direct question: **QA-PS-038 shares root cause B (and, for its residual
count, root cause A) with the other four. Its original, more dramatic headline was a different,
already-fixed mechanism (FIX-624) that this investigation does not need to touch.**

## 4. Backend note — `status_filter` already exists; it is not wired through

The task asked whether the shell needs the full 50-row payload or could ask for only running
runs. `backend/app/api/runs.py:734-793` (`list_runs`, `GET /api/runs`) already accepts
`status_filter: Optional[str] = None` (`:742`) and applies it server-side
(`:778-779`, `query.filter(WorkflowRun.status == status_filter)`) before `LIMIT`/`OFFSET`. This
is **live today** — no backend change needed to use it for a single status.

It does not fully solve the shell's need as-is: `AppHeader`'s `LIVE_STATUSES`
(`AppHeader.tsx:46-48`) and `RunConnectionProvider`'s `AUTO_STREAM_STATUSES`
(`RunConnectionProvider.tsx:66`) are each a **set** of several statuses, and `status_filter` only
takes one exact value (`WorkflowRun.status == status_filter`, not an `IN` clause), so today's
param cannot express "any of these six statuses" in one request. Reaching a true
running-runs-only endpoint still needs a small backend change — extending `status_filter` to
accept a comma-separated list, or adding an `IN` variant — but that change is materially smaller
than option (c)'s "a real API addition... out of scope for this bug line" implied, since the
query-param plumbing and the DB filter already exist; it is a few-line extension of an existing
endpoint, not a new one. Flagging this as a cheap follow-on for whoever makes the option (c) call
— not implementing it here, since it is a backend/API change and outside this read-only pass.

## 5. Per-bug disposition and test impact

All five/six bugs (035, 036, 038, 041, 046, and 036's own text names 037 too) point at the
identical mechanism, so §1+§2 is **one fix implemented once**, not five separate patches. What it
changes per bug:

| Bug | File | Before this fix (per escalation evidence) | After §1+§2 | Still needs the a/b/c decision to literally pass? |
|---|---|---|---|---|
| QA-PS-035 | `suites/09_settings/test_qa_ps_035_settings_duplicate_requests.py` | `limit=6`×2, `limit=50`×2, `workflows`×1 | `limit=6`×0, `limit=50`×1, `workflows`×1 | Yes — test asserts 0/0 |
| QA-PS-036 | `suites/10_analytics/test_iss782_duplicate_fetches.py` | `runs`×2 total, `workflows`×1 (post FIX-617) | `limit=6`×0, `limit=50`×1, `workflows`×1 | Yes |
| QA-PS-038 | `suites/07_run_detail/test_qa_ps_038_run_detail_duplicate_requests.py` | 6, across 2 full navigations + 1 click | shell contribution roughly halved per navigation; click phase already 1 (FIX-624) | Yes — test asserts `<=2` |
| QA-PS-041 | `suites/05_saved_workflows/test_qa_ps_041_workflows_duplicate_requests.py` | `limit=6`×1, `limit=50`×1 (already low) | `limit=6`×0, `limit=50`×1 | Yes |
| QA-PS-046 | `suites/04_composer_canvas/test_qa_ps_046_composer_unneeded_runs_fetch.py` | `limit=50`×1, `limit=6`×1 | `limit=6`×0, `limit=50`×1 | Yes |

None of these tests goes green from §1+§2 alone — every one of them was written to assert **zero**
`/api/runs`/`/api/workflows`, and the residual one-call floor is exactly the shell traffic the
escalations correctly parked as a product decision. What changes is the size of that floor (from
today's 2×/2× down to a true 1×/1×) and that reaching it needed zero product input.

**Recommended test changes**, in addition to whatever the a/b/c decision produces later:

- Two **new**, decision-independent regression checks that can land with §1+§2 immediately,
  because they assert the fix itself rather than the still-open product question:
  - A `[...view]` source test (same idiom as the existing 16 files there, e.g.
    `authEffectGuard.iss844.source.test.ts`) asserting `page.tsx` no longer calls `getWorkflows`
    directly and instead reads `useRunConnection().recentRuns`.
  - `frontend/src/providers/RunConnectionProvider.test.tsx` — assert `refreshLiveRuns` stores
    the fetched `runs` on context and that the zero-tab-owned-runs branch still calls the network
    (only skips the auto-attach derivation), per the caveat in §2.
- `frontend/src/store/listenerMiddleware.test.ts` and `frontend/src/store/slices/globalSlice.test.ts`
  (both exist today) — update/add a case asserting `signedIn` no longer dispatches
  `fetchRecentRuns()`.
- `frontend/src/components/catalog/HomeLaunchGrid.test.tsx` (exists, 9 cases today per FIX-627's
  coverage note) — add a case asserting the component dispatches `fetchRecentRuns()` on its own
  mount when the slice is idle.
- The five e2e files above each need their strict-zero assertion re-scoped to `<=1`/`==1` once
  the group decision lands — this was already true before this investigation and is unchanged by
  it.

## 6. Risk to ISS-232 and the header badge

- **ISS-232 (deep-link `/library/{type}/{slug}` latency):** no risk from §1 or §2. ISS-232's
  regression was `/api/workflows` blocking the Library tabs; `fetchWorkflows()` is untouched in
  both fixes and keeps firing unconditionally, in parallel with agents/skills/hooks, exactly as
  it does today. §1 removes a fetch (`fetchRecentRuns`) that was never part of the measured
  12.2s case. §2 does not touch the preload at all — it only changes which layer owns the
  already-separate `limit=50` fetch.
- **Header badge / "N Running" pill:** no functional risk if §2's caveat (the
  zero-tab-owned-runs branch must keep the network call, only skip the auto-attach filter) is
  respected — the badge keeps getting the full server-truth list on every route, unchanged from
  today. The risk is purely implementation risk in merging two call sites into one: getting the
  `tabOwnedIds.size === 0` branch wrong (skipping the network call, as it does today) would
  silently blind the badge exactly the way option (b) in every escalation warns about. This is
  the one place in §2 that needs care, not a design gap.
- **SSE live-run re-attach:** no risk — `refreshLiveRuns`'s derivation of `autoIdsRef` from
  `runs` is unchanged, it just reads `runs` from state that was set by the same function instead
  of a second independent call.

## 7. Does one fix close all five?

No, not by itself, and it should not be presented that way. §1+§2 is genuinely **one fix, applied
once**, shared by all five bugs (plus 036/037/038's own siblings) — it is not five separate
patches. It removes all of the traffic that never needed a decision (the `limit=6` misroute) and
halves the traffic that does need one (the `limit=50` duplicate ownership), without reopening
ISS-232 and without a backend change. But every one of the five test files was written to assert
**zero** shell traffic, and after this fix the honest floor is **one** `/api/runs?limit=50` call
and **one** `/api/workflows` call per cold load, everywhere — because `AppHeader` and
`RunConnectionProvider` are both real, confirmed consumers. Reaching literal zero is still
exactly the product decision `ESCALATIONS.md` already framed (options a/b/c); this investigation
does not remove the need for that call, it removes everything that was being lumped in with it
that didn't actually belong to it.

## 8. Confidence

**High** for root cause A (single grep-confirmed consumer, `HomeLaunchGrid.tsx:148`/`:2896`,
zero ambiguity) and for the mechanism split in QA-PS-038 (FIX-624's `isReplay` guard read
directly in the current tree, current line numbers). **High** for root cause B's existence and
location (both fetch sites and the context seam were read directly, not inferred from the
cards). **Medium** on the precise post-fix call counts in §5's table — they follow deductively
from the confirmed mechanisms but were not measured against a live server (out of scope: no
server restarts, no product runs, per the task's hard rules), so treat them as INFERRED, not
measured, until re-run against the same probes the escalations used.

## Evidence index (file:line)

- `frontend/src/components/catalog/HomeLaunchGrid.tsx:33,132-134,148-150,156-198` — sole consumer
  of `state.global.recentRuns`, route-scoped via its own render gate.
- `frontend/src/components/layout/DashboardLayout.tsx:2720,2754,2896,3037,3054,3068,3118` —
  `AppHeader` mounted before every `mainView` branch; `HomeLaunchGrid` only inside `"home"`.
- `frontend/src/app/[...view]/page.tsx:105-118,446,843,955-957,1056-1100,1109-1113,1122-1129,1860,2279,4421` —
  `signedIn` dispatch, `viewPathKey`, the `recentRuns` fetch/guard/snapshot, the replay-aware
  handler, the two legitimate mutation refetches, and the existing `useRunConnection()` seam.
- `frontend/src/store/listenerMiddleware.ts:19-70` — the `signedIn` preload effect.
- `frontend/src/store/slices/globalSlice.ts:7,29-45` — `fetchWorkflows`/`fetchRecentRuns`
  thunks and their documented, different intended consumers.
- `frontend/src/components/layout/AppHeader.tsx:46-48,78-89,126,138,188,200,328,371` —
  `LIVE_STATUSES`, the `recentRuns`/`recentRunsLoaded` props, `useWorkflowLabels()`, the badge
  derivation.
- `frontend/src/providers/RunConnectionProvider.tsx:9-19,66,96-150,279-331,334-355` — doc
  comment, `AUTO_STREAM_STATUSES`, the context shape, `refreshLiveRuns`, boot/wake effects.
- `frontend/src/lib/api.ts:404-406,439-442,903-944` — the deliberate run-list cache exclusion,
  the single-flight guard and its documented "ticks apart" limitation, `getWorkflows()`.
- `backend/app/api/runs.py:734-793` — `list_runs`, including the already-live `status_filter`
  param and its single-value equality filter.
- `frontend/src/hooks/useNotifications.ts` — grepped for `recentRuns`; no match. Notification
  run-matching against the run list happens inside `AppHeader` itself
  (`AppHeader.tsx:193-208`), not in a separate fetching consumer.

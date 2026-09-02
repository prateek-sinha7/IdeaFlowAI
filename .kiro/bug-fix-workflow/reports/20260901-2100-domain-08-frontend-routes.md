# Domain 8 — frontend·routes — Run Report
**Date:** 2026-09-01T21:00:00Z  
**Cards:** 13  **Batches:** 5  **Rounds:** 2

---

## Summary

| Outcome | Cards |
|---------|-------|
| FIXED (new FIX card) | 7 (ISS-342, ISS-602, ISS-492, ISS-350, ISS-624, ISS-376, ISS-405+ISS-415 → FIX-465) |
| ALREADY_FIXED | 3 (ISS-352, ISS-407, ISS-442) |
| ESCALATED | 3 (ISS-195, ISS-579, see below) |

**Verification:** vitest 77/77 green (4 test files). tsc clean on changed files.  
**Dedup regenerated:** 163 open → 144 units.

---

## Round 1

### Batch B1 — `frontend/src/app/login/page.tsx` [haiku]

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-342 | FIXED | FIX-459 |
| ISS-352 | ALREADY_FIXED | — (FIX-345 already added submittingRef to handleChallengeSubmit) |
| ISS-602 | FIXED | FIX-460 |

**ISS-342:** `ChallengeForm` received `setNewPassword`, `setConfirmNewPassword`,
`setMfaCode`, `setSelectedFactor` as props but none of the four `onChange` handlers
cleared the `error` state set by `handleChallengeSubmit`. Added `onClearError: () =>
void` prop to `ChallengeForm`; all four `onChange` handlers now call `onClearError()`.
At the call site in `LoginForm`, passed `onClearError={() => setError("")}`. Fix shape
mirrors ISS-244/AccountSettings.tsx.

**ISS-352:** submittingRef guard was already present in `handleChallengeSubmit` per
FIX-345. Confirmed by source read — ALREADY_FIXED.

**ISS-602:** Replaced the one remaining hand-rolled `<input type="password">` with
`<PasswordInput>` inside the existing Lock-icon wrapper. The Lock icon is positioned at
`z-10 pointer-events-none` in the outer wrapper; `PasswordInput` owns the reveal toggle
on the right.

### Batch B2 — `frontend/src/app/workflow/page.tsx` [haiku]

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-492 | FIXED | FIX-461 |
| ISS-579 | ESCALATED | cross-domain (see below) |

**ISS-492:** `WorkflowPage` never passed `pipelineState`, `onStartPipeline`,
`onResetPipeline`, or `onViewResults` to `<WorkflowView>`. Added `INITIAL_PIPELINE_STATE`
constant, `pipelineState` local state, and three callback handlers. Wired all four props.
Removed the unused `token` state variable. The `it.fails` marker in `page.test.tsx` was
removed — the test now passes (77/77 vitest green).

**ISS-579 — ESCALATED:** The fix belongs in
`frontend/src/components/workflow/WorkflowView.tsx` (remove handler at line 388) — a
file outside domain 8's owned fix sites. ISS-579 depends on ISS-492 being wired first;
that's now done. The WorkflowView fix should be picked up by whichever domain owns
`frontend/src/components/workflow/`.

---

## Round 2

### Batch B3 — `[...view]/page.tsx` + `routes.ts` + `DashboardLayout.tsx` [haiku/sonnet]

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-195 | ESCALATED | INFERRED / already-fixed (see below) |
| ISS-350 | FIXED | FIX-462 |
| ISS-624 | FIXED | FIX-463 |

**ISS-195 — ESCALATED / ALREADY_FIXED:** Deep analysis of the mount mechanism showed:
BFCache never remounts the React tree (values preserved in heap); SPA navigation within
`[...view]` never remounts either (component stays mounted, `pushState` for tab
switches). On a genuine remount (hard navigation away and back), `mounted` and
`isAuthenticated` both reset to `false` but recover within one microtask tick —
`setMounted(true)` fires in an empty-dep `useEffect`, `setIsAuthenticated(true)` fires
in the same render from a synchronous `getToken()` localStorage read. The "permanent
blank" described in ISS-195 is not reproducible with the current code. Root card
ISS-190 has no landed FIX card as per the domain spec note; ISS-195 itself appears to
be an inferred sibling of a mis-diagnosed root. Recommend closing ISS-195 as
already-fixed / diagnosis-refuted. No code change made.

**ISS-350:** Added `&& segments.length === 1` guard to the `head === 'analytics'`
branch in `routes.ts`. Same one-conjunct shape as FIX-344/register. Added two
regression tests to `routes.test.ts` (sub-path → unknown; exact path still resolves).

**ISS-624:** `LibraryPage` calls `useSearchParams()` unconditionally. The Next.js App
Router requires any component calling `useSearchParams()` to be inside a `<Suspense>`
boundary; without one, a hard refresh of `/library?tab=hooks` suspends during SSR and
produces an empty body. Wrapped `<LibraryPage />` in `<Suspense fallback={null}>` in
`DashboardLayout.tsx`. Added `Suspense` to the react import.

### Batch B4 — Mixed routes [haiku]

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-376 | FIXED | FIX-464 |
| ISS-407 | ALREADY_FIXED | — |
| ISS-442 | ALREADY_FIXED | — |

**ISS-376:** `CreateRoute()` in `workflow/create/page.tsx` now detects unrecognized
`raw` mode values (non-null but not `"prototype"`, `"ppt"`, or `"ppt_v2"`), calls
`router.replace('...?mode=prototype')`, and returns `null` while the redirect is in
flight. A null `raw` (no `?mode=` — the normal `proxy.ts`-handled path) passes through
unchanged.

**ISS-407 — ALREADY_FIXED:** `preview-fullscreen/page.tsx` already has the `"quota"`
PageState and `giveUp()` helper that properly handles all three failure exits.

**ISS-442 — ALREADY_FIXED:** `workflowDetailCatch.source.test.ts` already has
`toBe(5)` and an updated comment. No change needed.

### Batch B5 — `frontend/src/app/admin/page.tsx` [haiku]

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-405 | FIXED | FIX-465 |
| ISS-415 | FIXED | FIX-465 |

**ISS-405:** Changed `{user.email[0].toUpperCase()}` to
`{(user.email || "?")[0].toUpperCase()}` — guards against `TypeError` when an
empty-string email reaches the table render.

**ISS-415:** Changed `deleteConfirm` state type from `string | null` to
`{ id: string; email: string } | null`. Dialog now shows the user's email beneath the
heading so an admin can confirm the right account before deleting.

---

## FIX cards written

| FIX | Closes |
|-----|--------|
| FIX-459 | ISS-342 |
| FIX-460 | ISS-602 |
| FIX-461 | ISS-492 |
| FIX-462 | ISS-350 |
| FIX-463 | ISS-624 |
| FIX-464 | ISS-376 |
| FIX-465 | ISS-405, ISS-415 |

---

## Test results

```
vitest: 77/77 passed (4 files)
  - src/app/login/login.reskin.test.tsx         9 passed
  - src/app/workflow/page.test.tsx               1 passed (was it.fails)
  - src/lib/routes.test.ts                      62 passed (2 new)
  - src/app/[...view]/workflowDetailCatch.source.test.ts  5 passed

tsc --noEmit: 0 errors introduced by domain 8 changes
  (2 pre-existing errors in HomeLaunchGrid.crossAccountLeak.test.tsx and
   store/listenerMiddleware.test.ts — neither touched by this domain)
```

---

## What needs human action

1. **Commit** — all changes are in the working tree. No `git commit` made here.
2. **ISS-579** — still open; fix belongs in `WorkflowView.tsx` (remove handler line
   388). Pick up in the domain that owns `frontend/src/components/workflow/`.
3. **ISS-195** — recommend closing as already-fixed / inferred-wrong-root-cause.
   Root card ISS-190 has no FIX card and is in TRIAGE.
4. **e2e test for ISS-624** — `test_every_top_level_screen_survives_a_hard_refresh`
   for `/library?tab=hooks` needs live servers to verify. Run manually with
   `tests/integration/e2e` venv when servers are up.
5. **Dedup regenerated** — 163 → 144 units. Backlog is current.

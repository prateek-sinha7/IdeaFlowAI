---
phase: quick-260805-rte
verified: 2026-08-05
status: passed
---

# Verification — Post-login routing to main app + Admin Dashboard nav

## Truths verified

| Truth | Evidence |
|---|---|
| Normal/admin login with no intended route lands on `/dashboard` | `login/page.tsx` calls `router.push(resolveRedirectTarget(searchParams.get("redirect")))`; with no `redirect` param this resolves to `DEFAULT_POST_LOGIN_ROUTE = "/dashboard"` for every user (`is_admin` no longer read at all in the redirect decision). New tests: `login.reskin.test.tsx` "routes to the main application by default" + "routes an admin to the main application too" — both pass. |
| Unauthenticated protected-page hit preserves the intended route and returns there after login | `buildLoginRedirect()` builds `/login?redirect=<current path+query+hash>`; wired into every guard (`dashboard/page.tsx`, `admin/page.tsx`, `workflow/page.tsx`, `LaunchWizard.tsx` — the 3 call sites: initial guard + 2 template-fetch 401 handlers). Login reads it back via `useSearchParams().get("redirect")` and pushes `resolveRedirectTarget(...)`. New test: "returns to the originally-requested internal page via ?redirect=" passes (`/workflow/create?mode=ppt` round-trips). The param is one-shot by construction — it is only ever read at submit time, never persisted, so it "disappears" once the login navigation replaces the URL. |
| External/malformed `?redirect=` is ignored, falls back to `/dashboard` | `isSafeRedirectPath` rejects non-`/`-rooted, `//`, `/\`, and control-char-prefixed values; `resolveRedirectTarget` falls back to `DEFAULT_POST_LOGIN_ROUTE`. Unit tests in `authRedirect.test.ts` (6 cases) + integration test "ignores an external/malformed ?redirect=" in `login.reskin.test.tsx` — all pass. |
| Admin Dashboard reachable via a role-gated nav item | `AppHeader.tsx` profile dropdown renders an "Admin Dashboard" `menuitem` (routes to `/admin` via `router.push`) only when `isAdmin` prop is true; threaded from `DashboardLayout` -> `dashboard/page.tsx`'s `user?.is_admin`. New tests in `AppHeader.a11y.test.tsx`: "does NOT render 'Admin Dashboard' for a non-admin user" / "renders 'Admin Dashboard' ... for an admin user" — both pass. |
| Route protection unchanged (auth + role) | `admin/page.tsx` guard logic untouched apart from swapping the literal `"/login"` for `buildLoginRedirect()` on the unauthenticated branches; the non-admin branch still does `router.replace("/dashboard")` verbatim (asserted by the pre-existing, unmodified `admin.reskin.test.tsx` "redirects a non-admin user" test, still green). "Back to app" button in `admin/page.tsx` untouched (`onClick={() => router.push("/dashboard")}`). |

## Commands run

- `npx tsc --noEmit` (frontend/) — exit 0, no errors.
- `npx vitest run src/app/login src/app/admin src/components/layout/AppHeader src/lib/authRedirect --run` — 45/45 passed.
- `npx vitest run --run` (full suite) — 727 passed / 125 failed, but confirmed via `git stash` (reverting to clean HEAD) that the exact same 125 tests fail identically on the pre-change baseline (unrelated pre-existing failures in WorkflowHistory/PreviewPanel/AuditTab/RunChatLane/etc. — none touch any file this plan modified). No new failures introduced.

## Gaps Summary

No gaps. All 5 truths hold with passing tests; no regressions in touched files; pre-existing unrelated test failures confirmed unchanged via before/after comparison.

---
phase: quick-260805-rte
plan: 01
subsystem: frontend-auth-routing
tags: [routing, auth, admin, frontend]
affects: [login, dashboard, admin, launch-wizard, app-header]
key-files:
  - frontend/src/lib/authRedirect.ts
  - frontend/src/app/login/page.tsx
  - frontend/src/components/layout/AppHeader.tsx
decisions:
  - "Post-login redirect target is validated against an internal-path allowlist (isSafeRedirectPath), not read raw from the query string, to prevent an open redirect."
  - "Admin dashboard access moved from an automatic post-login redirect to a role-gated nav item (profile-menu 'Admin Dashboard', isAdmin-gated) — reachable any time, not just at login."
  - "No shared auth-guard component introduced; each existing per-page guard (dashboard/admin/workflow/LaunchWizard) now calls one shared buildLoginRedirect() helper instead of duplicating the '/login' literal."
metrics:
  files_changed: 11
  tests_added: 10
---

# Quick task 260805-rte: Post-login routing to main app + Admin Dashboard nav

Changed the app's post-login destination so every user — including admins — lands on the main application (`/dashboard`) by default, while preserving return-to-originally-requested-page behavior for protected routes via a validated `?redirect=` param, and moved admin dashboard access from an automatic redirect to a role-gated "Admin Dashboard" nav item in the profile menu.

## Tasks

| Task | Files |
|---|---|
| Add shared redirect-target validation + builder | `frontend/src/lib/authRedirect.ts`, `authRedirect.test.ts` |
| Login page: read `?redirect=`, default to `/dashboard` for all users | `frontend/src/app/login/page.tsx` (wrapped in `Suspense` for `useSearchParams`), `login.reskin.test.tsx` |
| Preserve intended destination at every existing guard | `frontend/src/app/dashboard/page.tsx`, `frontend/src/app/admin/page.tsx`, `frontend/src/app/workflow/page.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx` |
| Add role-gated "Admin Dashboard" nav item | `frontend/src/components/layout/AppHeader.tsx` (+`AppHeader.a11y.test.tsx`), threaded `isAdmin` through `DashboardLayout.tsx` and `dashboard/page.tsx` |

## What changed

- `login/page.tsx` no longer branches on `data.user.is_admin` to choose `/admin` vs `/dashboard`. It now always defaults to `/dashboard`, unless a validated `?redirect=` query param names a different internal page.
- New `frontend/src/lib/authRedirect.ts`: `isSafeRedirectPath` (rejects absolute/protocol-relative/backslash-trick values — the open-redirect guard), `resolveRedirectTarget` (validate-or-default), `buildLoginRedirect` (builds `/login?redirect=...` from the current browser location).
- Every existing per-page auth guard (`dashboard/page.tsx`, `admin/page.tsx`, `workflow/page.tsx`, `LaunchWizard.tsx`'s 3 call sites) now calls `buildLoginRedirect()` instead of the bare `"/login"` literal, so an unauthenticated hit to any protected route preserves it as the post-login destination.
- `AppHeader.tsx` profile dropdown gained an "Admin Dashboard" `menuitem` (Shield icon, routes via `next/navigation`'s `useRouter().push("/admin")`), rendered only when a new `isAdmin` prop is true. Threaded from `dashboard/page.tsx`'s `user?.is_admin` through `DashboardLayout`.
- `admin/page.tsx`'s existing role gate (non-admin -> `/dashboard`) and "Back to app" button are unchanged.

## Deviations from Plan

None — implemented as designed during investigation. No shared `ProtectedRoute` component was introduced since none existed before and adding one would have been a larger, out-of-scope refactor; the smallest cohesive change was a shared helper each existing guard calls.

---
phase: quick-260805-rte
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/lib/authRedirect.ts
  - frontend/src/lib/authRedirect.test.ts
  - frontend/src/app/login/page.tsx
  - frontend/src/app/login/login.reskin.test.tsx
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/app/admin/page.tsx
  - frontend/src/app/workflow/page.tsx
  - frontend/src/components/workflow/LaunchWizard.tsx
  - frontend/src/components/layout/AppHeader.tsx
  - frontend/src/components/layout/AppHeader.a11y.test.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
autonomous: true
requirements: [ROUTE-01, ROUTE-02, ROUTE-03, ROUTE-04]

must_haves:
  truths:
    - "Login (normal user or admin) with no intended route lands on /dashboard (the main application) — admins are no longer auto-routed to /admin."
    - "An unauthenticated request to a protected page (dashboard, admin, workflow, /workflow/create via LaunchWizard) preserves the originally-requested internal path (+query/hash where the guard can read it) via /login?redirect=..., and login returns the user there; the saved destination is consumed (query param disappears) after use."
    - "An external or malformed ?redirect= value (absolute URL, protocol-relative //, backslash trick) is ignored and the user lands on /dashboard — no open redirect."
    - "The Admin Dashboard is reachable via a profile-menu nav item shown ONLY when the authenticated user is an admin (isAdmin); non-admins never see it."
    - "Authentication and role-based route protection are unchanged: unauthenticated -> /login (with redirect preserved), authenticated non-admin hitting /admin -> /dashboard (unchanged existing behavior), and the admin page's 'Back to app' action still returns to /dashboard."
  artifacts:
    - path: "frontend/src/lib/authRedirect.ts"
      provides: "resolveRedirectTarget / isSafeRedirectPath / buildLoginRedirect — the single redirect-target validation + build logic reused by every guard"
      contains: "isSafeRedirectPath"
    - path: "frontend/src/app/login/page.tsx"
      provides: "post-login navigation to resolveRedirectTarget(searchParams.get('redirect')), default /dashboard for every user including admins"
      contains: "resolveRedirectTarget"
    - path: "frontend/src/components/layout/AppHeader.tsx"
      provides: "isAdmin-gated 'Admin Dashboard' profile-menu item routing to /admin"
      contains: "Admin Dashboard"
  key_links:
    - from: "dashboard/page.tsx, admin/page.tsx, workflow/page.tsx, LaunchWizard.tsx guards"
      to: "frontend/src/lib/authRedirect.ts buildLoginRedirect()"
      via: "router.replace(buildLoginRedirect()) instead of router.replace('/login')"
      pattern: "buildLoginRedirect"
    - from: "DashboardLayout isAdmin prop"
      to: "dashboard/page.tsx user.is_admin (from getMe)"
      via: "isAdmin={user?.is_admin ?? false}"
      pattern: "isAdmin"
---

<objective>
Change post-login routing so every user (including admins) lands on the main
application by default, while preserving return-to-originally-requested-page
behavior for protected routes, and keep the admin dashboard reachable via a
role-gated nav item instead of an automatic post-login redirect. Requested by
user via /velocity-feature.
</objective>

<context>
No pre-existing REQUIREMENTS.md/ROADMAP.md entry covered this (checked
PROJECT.md/STATE.md — unrelated to the active v3.0 resume milestone). This is
a small, self-contained frontend-only behavior change, so it is scoped as a
quick task rather than a full phase.
</context>

<facts_verified_during_planning>
- No middleware.ts, ProtectedRoute/AuthGuard HOC, or shared useAuth hook exists
  in this codebase — every protected page (dashboard, admin, workflow,
  LaunchWizard) independently calls getToken()/getMe() in a useEffect and
  redirects with router.replace("/login") on failure. This plan does not
  introduce a shared guard component (out of scope / bigger refactor); it adds
  one small shared helper (`authRedirect.ts`) that every existing guard calls.
- No `?redirect=`/`?next=` mechanism or saved-destination storage existed
  before this change (confirmed via grep across frontend/src).
- No central route-constants file exists; paths remain literal strings
  ("/dashboard", "/admin", "/login") as in the rest of the codebase.
- `admin.reskin.test.tsx` asserts a non-admin visiting /admin is redirected to
  exactly "/dashboard" (unchanged) and does not otherwise interact with the
  login flow — untouched by this change.
- `ts-a.auth.spec.ts` (Playwright, mocked) asserts unauthenticated /dashboard
  -> /login (still true, target is /login?redirect=%2Fdashboard now) and login
  -> dashboard heading (unchanged, default target is /dashboard).
</facts_verified_during_planning>

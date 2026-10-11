---
inclusion: auto
name: frontend-testing-structure
description: Canonical placement, naming, suite boundaries, and migration rules for Flowin frontend tests under frontend/src and frontend/e2e using Vitest and Playwright. Use for frontend test structure, location, naming, configuration, project selection, or migration questions; do not use for Python/pytest tests.
---

# Frontend Test Structure Standard

This standard governs React 19, Next.js 16 App Router, TypeScript, Vitest/jsdom/React Testing
Library, and Playwright tests under `frontend/`.

Related steering:
- Placement, naming, runner ownership, and migration: this file.
- Detailed Vitest unit/component/hook authoring: `frontend-unit-test-writing`.
- Test-layer selection and recipes: `frontend-test-playbook`.
- General React/Next.js design, accessibility, security, and validation:
  `frontend-coding-guardrails`.

## Scope, precedence, and working directory

For anything under `frontend/`, these frontend test steering files govern placement and authoring.
The existing `testing-structure`, `testing-conventions`, `unit-test-writing`, and
`testing-playbook` files remain authoritative for Python/backend pytest work only.

Run every command from `frontend/` with npm/npx in Windows PowerShell. Automation must be bounded
and single-pass: never start a watcher or a separate development server. Playwright may manage its
configured bounded `webServer` lifecycle during a Playwright command.

## Live configuration sources

Read these files before changing or placing tests; they override copied examples and stale
assumptions:

- `frontend/package.json` — available scripts and pinned dependencies.
- `frontend/vitest.config.ts` — jsdom, collection, exclusions, aliases, coverage, and thresholds.
- `frontend/vitest.setup.ts` — global jest-dom matchers, in-memory `localStorage`, and
  `ResizeObserver`.
- `frontend/playwright.config.ts` — test directory, projects, browser settings, and bounded server.
- `frontend/tsconfig.json` — strict TypeScript and the `@/*` alias.
- `frontend/eslint.config.mjs` — lint scope, generated-output ignores, and project rules.

## Canonical layout

```text
frontend/
├── src/
│   └── <feature>/
│       ├── <subject>.test.ts                 # pure function, reducer, store, API helper
│       ├── <Component>.test.tsx              # component behavior
│       ├── <subject>.hook.test.tsx           # optional clarity for a hook
│       ├── <subject>.integration.test.tsx    # several real frontend units in jsdom
│       ├── <subject>.contract.test.ts        # frontend-owned boundary shape
│       ├── <subject>.property.test.ts        # fast-check invariant
│       ├── <subject>.a11y.test.tsx            # focused accessibility behavior
│       ├── <subject>.security.test.tsx        # adversarial client behavior
│       └── <subject>.performance.test.ts      # stable isolated budget
└── e2e/
    ├── tests/
    │   ├── <journey>.spec.ts                 # deterministic mocked Playwright
    │   ├── <surface>.visual.spec.ts           # optional approved mocked visual contract
    │   ├── <journey>.live.spec.ts             # real backend/provider
    │   └── <surface>.smoke.live.spec.ts       # minimal live liveness
    ├── fixtures/                              # browser fixtures, harnesses, page objects
    └── fidelity/                              # support/manual-review assets, not a suite
```

All Vitest unit, component, hook, jsdom integration, contract, property, accessibility, security,
and isolated performance tests remain colocated under `src/**`. Suffixes clarify intent; they do
not create separate runner suites. Use `.test.ts` or `.test.tsx` for new Vitest files.

Playwright owns `e2e/tests/**` and always uses `.spec.ts`; `.live.spec.ts` is the live-project
discriminator. Files under `e2e/fixtures/`, page objects/harnesses, and fidelity assets are support
code, not independently collected suites.

Do not create a frontend `tests/unit/...` mirror. Source colocation is the configured repository
convention and matches `frontend-coding-guardrails`.

## Placement decision tree (first yes wins)

1. **Support code with no assertions?** Put a shared browser fixture/page object in the existing
   `e2e/fixtures/` area; otherwise keep a narrowly used typed helper beside its test.
2. **Deployed liveness or a real-backend/provider golden path?** Use
   `e2e/tests/<journey>.live.spec.ts`; use `.smoke.live.spec.ts` for minimal liveness.
3. **Browser navigation, multi-page behavior, layout-dependent behavior, or a critical journey
   with deterministic browser-boundary mocks?** Use `e2e/tests/<journey>.spec.ts`.
4. **Stable browser screenshot contract explicitly approved for baselining?** Use a mocked
   `<surface>.visual.spec.ts`. This is optional: no approved automated baseline workflow currently
   exists.
5. **Several real components/hooks/providers/store pieces in jsdom, with transport mocked?** Use a
   colocated `.integration.test.tsx`.
6. **React DOM, interaction, or accessibility behavior?** Use a colocated component `.test.tsx`.
7. **Custom-hook state, lifecycle, rerender, or cleanup?** Use a colocated hook `.test.ts` or
   `.test.tsx`; add `.hook` only when it improves clarity.
8. **Pure function, reducer, parser, store, or type helper without a public-boundary purpose?** Use
   a colocated `.test.ts`.
9. **Frontend-owned request/response or serialization shape?** Use a colocated
   `.contract.test.ts`.
10. **Invariant over generated inputs?** Use a colocated `.property.test.ts` with installed
    `fast-check`.
11. **Adversarial client behavior?** Use a colocated `.security.test.ts[x]`; if proving it requires
    a browser journey, use mocked Playwright. Frontend auth tests never replace backend
    authorization/IDOR tests.
12. **Stable isolated timing budget with a measured baseline and headroom?** Use a colocated
    `.performance.test.ts[x]`; browser timing belongs in controlled Playwright.
13. **Otherwise:** choose the smallest colocated Vitest test that executes the real subject logic.

Split mixed concerns. Test pure transformation separately from rendering, and jsdom state flow
separately from a browser journey. Async React Server Components cannot be mounted faithfully in
jsdom: test pure server collaborators separately, test interactive `'use client'` leaves in Vitest,
and prove route-level server data/render output through an appropriate integration or Playwright
E2E path.

## File naming and ownership

- New Vitest files use `.test.ts` or `.test.tsx`. Existing `src/**/*.spec.ts[x]` files remain
  collected legacy exceptions, not the new canonical spelling.
- Playwright files use `.spec.ts`; live files must end in `.live.spec.ts`.
- Prefer `describe("Subject")` and `it("outcome when condition")`. Keep one observable behavior
  per test.
- Do not apply Python names, pytest markers, mirrored paths, or `__init__.py` rules to frontend
  tests.
- Keep helpers beside the smallest owning scope. Put truly shared Playwright fixtures/page objects
  in `e2e/fixtures/`, and introduce page objects only when repeated locators or journey vocabulary
  make them clearer.
- Never use global mutable test state.

## Collection, projects, and tags

Vitest's effective include is `src/**/*.{test,spec}.{ts,tsx}`. It excludes `e2e/**`,
`node_modules/**`, `dist/**`, and `.next/**`.

Frontend suite boundaries are expressed by file location/suffix, Vitest include/exclude, and
Playwright project selection—not pytest markers:

- **`mocked`**: all `e2e/tests/**/*.spec.ts` except `.live.spec.ts`. This is the deterministic,
  mandatory default browser project; automatic fixtures prevent backend calls.
- **`live`**: only `e2e/tests/**/*.live.spec.ts`. This is opt-in and requires intentionally
  available real services and seeded credentials.

Tags may describe intent, but no tag-filtered npm suite is configured. Never use tags to blur or
replace the filename/project boundary.

## Hard boundaries

- No Vitest tests under `e2e/**`; no `@playwright/test` imports under `src/**`.
- No real backend or third-party network in Vitest or the mocked Playwright project. Real calls are
  confined to explicitly configured `live` specs/project.
- Mock at system boundaries—transport/API modules, router, storage, time, randomness, and missing
  browser APIs—not React internals or the subject under test.
- Do not assert exact unstable AI prose. Assert schema, status, required sections, safe rendering,
  and business invariants.
- No arbitrary sleeps. Use Testing Library `findBy*`/`waitFor`, Playwright web-first assertions,
  controlled promises, or fake timers with explicit advancement.
- No watch mode, separate server process, non-npm package manager, snapshot-heavy suite, silent
  dependency addition, skipped/flaky bypass, or invented script/project/tag.
- `jest-axe`/direct axe integration, MSW, JavaScript mutation tooling, and third-party visual tools
  are not installed capabilities. Treat them only as optional recommendations requiring explicit,
  pinned dependency/config approval. Playwright's built-in screenshot assertions are available but
  have no approved baseline workflow today.
- Accessibility automation never proves conformance. Retain manual keyboard, screen-reader,
  zoom/reflow, contrast, and assistive-technology review.
- Never rename/delete legacy tests or bulk-move them without an approved migration plan. Do not
  change production code merely to satisfy this layout.

## Legacy exceptions and migration guidance

Current tolerated exceptions include `src/**/*.spec.ts[x]` and colocated `__tests__` folders such
as `src/styles/__tests__/`. Vitest collects them, so they remain valid. New work uses direct
colocation and `.test.*`.

Migrate an exception only while intentionally touching its area:

1. Inventory every old path, target path, helper, import, and command in a reviewed migration plan.
2. Run the old targeted test and record its behavior.
3. Move the same test while preserving history; update imports without changing assertions or
   coverage intent.
4. Run the new targeted test, then the applicable full/static checks.
5. Confirm only one canonical copy remains. Never delete first, create a duplicate suite, or rename
   unrelated tests as cleanup.

## Commands and structural done criteria

Run from `frontend/` only:

```powershell
# Targeted Vitest (script wrapper or direct local binary)
npm run test:no-coverage -- src/<path>/<subject>.test.tsx
npx vitest --run src/<path>/<subject>.test.tsx

# Complete Vitest inventory; V8 enforces 80% lines/functions/branches/statements
npm run test

# Static checks
npm run typecheck
npm run lint

# Complete browser projects
npm run e2e
npm run e2e:live

# Targeted browser files
npx playwright test --project=mocked e2e/tests/<journey>.spec.ts
npx playwright test --project=live e2e/tests/<journey>.live.spec.ts
```

Run `npm run e2e:live` or a targeted `live` command only when its real-service prerequisites are
intentionally available; otherwise report it as not run.

Structural work is done when the intended runner collects the file, the other runner does not,
`mocked`/`live` separation is preserved, the relevant bounded commands pass, and no legacy test was
destructively migrated.

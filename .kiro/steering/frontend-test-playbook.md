---
inclusion: auto
name: frontend-test-playbook
description: Decision matrix and repository-specific recipes for Flowin frontend component, hook, jsdom integration, contract, accessibility, security, fast-check property, Playwright mocked/live E2E, visual, performance, and smoke tests. Use when frontend code changes or when deciding which frontend test types are required; do not use for Python/pytest tests.
---

# Frontend Test Playbook — What to Test and at Which Layer

Use this playbook to select the smallest frontend test layer that proves a change. For
`frontend/**`, this playbook and the other frontend test steering files take precedence over the
backend-only `testing-structure`, `testing-conventions`, `unit-test-writing`, and
`testing-playbook` files.

`frontend-testing-structure` owns locations/names/projects, `frontend-unit-test-writing` owns the
phased Vitest/RTL procedure, and `frontend-coding-guardrails` owns general React/Next.js design,
accessibility, security, and validation.

## Repository facts and capability inventory

- Runtime: React/React DOM 19.2.4, Next.js 16.3.4 App Router, TypeScript 5.9.3.
- Vitest 4.1.11 uses jsdom 29.1.1 and `vitest.setup.ts`; V8 coverage 4.1.11 enforces 80% for
  lines, functions, branches, and statements on `npm run test`.
- Installed: RTL 16.3.2, Testing Library DOM 10.4.1, jest-dom 6.9.1, user-event 14.6.1,
  fast-check 4.7.0, and Playwright 1.60.0.
- Vitest collects `src/**/*.{test,spec}.{ts,tsx}`. Playwright collects `e2e/tests/**` through
  exactly two projects: deterministic `mocked` and opt-in `live`.
- Mocked specs use automatic `mockApi`/`mockSse` fixtures and may use the provided dashboard page
  object. Live specs use a distinct fixture and intentionally configured real services.
- Existing screenshot capture/fidelity assets are human-reviewed gallery support, not automated
  visual-regression assertions; no committed `toHaveScreenshot` baseline system is adopted.

Not installed/configured as supported test capabilities: `jest-axe` or a direct axe integration,
MSW, JavaScript mutation tooling, third-party visual-regression tooling beyond Playwright's
built-in screenshot assertion, and a benchmark/Lighthouse test package. These are **optional
recommendations only**. Never import one without explicit approval and an exact pinned install plus
configuration.

## Step 1 — Classify the change

Before completing a frontend production change, classify every affected behavior and select all
required rows below. Keep proof at the lowest sufficient layer. A bug fix needs a regression test
that fails against the fault (or a controlled fault injection/manual mutation) and passes after the
fix.

Use a testing-trophy/pyramid budget, not a rigid quota:

1. Static TypeScript and lint checks form the base.
2. Put most cases in fast colocated pure, component, hook, and jsdom integration tests.
3. Add focused contract, property, accessibility, and security cases where their risks exist.
4. Keep a small set of critical deterministic mocked browser journeys.
5. Keep live E2E/smoke, visual, and performance suites few, deliberate, and expensive only when a
   lower layer cannot prove the contract.

## Step 2 — Decision matrix

| Change | Required | Recommended | Not sufficient / never by default |
|---|---|---|---|
| Pure function, parser, reducer, normalizer | Direct Vitest unit cases for branches/boundaries | fast-check property test for broad invariants | Component/E2E-only proof |
| React Client Component | RTL behavior tests plus semantic/keyboard checks | jsdom integration for provider/store flow; mocked E2E for a critical browser journey | Enzyme-style internals, giant snapshot, CSS-only assertion |
| Custom hook | `renderHook` contract, lifecycle/error/cleanup cases | Consumer integration when user-visible behavior matters | Testing only a mocked hook consumer |
| Provider/store/multi-component composition | jsdom integration with real provider/store pieces | Unit reducer/selectors; mocked E2E for critical flow | Mock-call choreography alone |
| API client or response adapter | Unit + runtime contract tests for request/response/error shapes | Property tests for parser/serializer invariants | TypeScript types or happy path alone |
| Next route/navigation boundary | Client-leaf test for navigation request; mocked E2E for browser routing/render result | Focused server collaborator test | Mounting async RSC in jsdom; mocked router alone for browser semantics |
| Auth/authorization UI | Component/security negative states and mocked E2E UX | Corresponding backend security tests | Frontend visibility as proof of server authorization/IDOR enforcement |
| Unsafe URL/HTML/input handling | Security tests with accepted and rejected adversarial inputs | Mocked browser test when URL/DOM semantics matter | Happy path, snapshot, or client validation alone |
| Generated-input invariant | fast-check property plus concrete regression examples | Reference-model comparison | Unseeded random loops or generated I/O |
| Critical user journey | Mocked Playwright E2E | Supporting lower-layer branch/contract tests | Live third-party journey in the default suite |
| Real backend/provider golden path | A few live Playwright success/failure paths | Mocked contract/journey coverage first | Making live the mandatory PR/default suite |
| Stable visual contract | Behavior/a11y tests first; approved Playwright `toHaveScreenshot` baseline if needed | Human fidelity review | DOM snapshots as pixel proof; unreviewed baseline updates |
| Performance-sensitive render/transform/stream | Measured baseline and repeatable budget with headroom | Profile first; isolated Vitest or controlled browser measurement | Razor-thin wall-clock assertion on a noisy machine |
| Deployed/live liveness | Minimal `.smoke.live.spec.ts` in the live project | One critical authenticated invariant | Mocked test as proof that deployment is alive |
| AI-output rendering | Component/contract cases for shape, states, invariants, and safe rendering | Mocked E2E journey; few live shape checks | Exact generated prose or broad output snapshot |

Tie-breakers:

- Use jsdom when browser layout/navigation is not essential.
- Use mocked Playwright when the browser journey is essential but external services are not.
- Use live only when mocks cannot prove the real contract, and keep lower-layer regression coverage.
- Split mixed concerns instead of making one test prove pure logic, rendering, and navigation.
- Accessibility accompanies interactive component/integration/E2E cases; it is not one final
  checkbox.
- Frontend auth behavior never proves backend authorization.

## Step 3 — Common standards for every recipe

- Assert observable behavior, public contracts, and semantic outcomes—not implementation details.
- Use deterministic independent data and typed minimal builders; one behavior per case.
- Prefer role/name/label queries and awaited user-event or Playwright web-first actions.
- Mock system boundaries, not React internals. Restore globals, timers, storage, routes, and mocks.
- Use no arbitrary sleeps, unseeded randomness, exact unstable AI prose, or real third-party
  network in default suites.
- Keep snapshots narrow and rare. Contract or visual snapshot updates require explicit approval,
  targeted regeneration, and human diff review; rerun without update mode afterward.
- Include negative/error/security paths, not only successful inputs.
- Accessibility automation cannot replace manual assistive-technology checks.
- Use npm/npx from `frontend/`, Windows PowerShell, and single-pass commands only.

## 3.1 Component and pure unit tests

**Location:** `src/<feature>/<subject>.test.ts[x]`.

Call pure TypeScript directly. For components, render with RTL through the smallest real wrapper,
use semantic queries, interact with awaited user-event, and assert visible/accessible output,
callbacks, or navigation contracts. Cover branch boundaries and loading/empty/success/error or
disabled states actually exposed. Mock only API/router/time/browser boundaries.

Async React Server Components do not mount faithfully in jsdom. Test pure server data helpers at
their public boundary, test interactive `'use client'` leaves with RTL, and use an integration or
mocked E2E route test for server-rendered output.

```powershell
npx vitest --run src/<feature>/<subject>.test.tsx
npm run test
```

Done: real subject logic ran, async work was synchronized, observable outcomes are exact, and the
full four-metric coverage gate remains green.

## 3.2 Hook tests

**Location:** colocated `useThing.test.ts[x]` or `useThing.hook.test.ts[x]` when the suffix adds
clarity.

Use RTL `renderHook`, `act`, `rerender`, `unmount`, and the smallest provider wrapper. Cover initial
state, transitions, dependency changes, success/error, cleanup, and timer/retry branches that
exist. Assert the hook's public result and externally visible effects, not private refs or internal
call order. Use fake timers only for timer-owned behavior and always restore them.

Done: lifecycle and cleanup are proved, controlled dependencies are deterministic, and a consumer
can rely on the asserted public contract.

## 3.3 jsdom integration tests

**Location:** colocated `<feature>.integration.test.tsx`.

Render multiple real components/hooks/providers/store pieces together. Control transport and
router edges, then assert the user-observable state flow rather than mock choreography. This is
still a jsdom integration test, not E2E; browser layout, navigation, download, and full RSC behavior
belong in Playwright.

MSW may be an optional future choice for reusable protocol-faithful handlers, but it is not
installed. The current supported approach is a narrow module/client/transport mock.

Done: integration among real frontend units is what makes the test pass, while external boundaries
remain deterministic.

## 3.4 Contract tests

**Location:** colocated `<boundary>.contract.test.ts`.

Exercise frontend-owned API adapters, serializers, parsers, and request builders. Cover required
and optional fields, enums/statuses, malformed payloads, error envelopes, unknown forward-
compatible fields, and exact outbound method/path/body/header shape where owned by the frontend.
TypeScript compile-time types do not validate runtime payloads.

Prefer focused structural assertions over broad snapshots. If a stable serialized snapshot is
truly valuable, baseline updates require explicit contract-owner approval and full diff review. No
OpenAPI/schema contract runner is installed; do not claim one ran.

Done: compatible and incompatible shapes fail for the intended reasons without real network I/O.

## 3.5 Accessibility tests

Put semantic behavior in the owning component/integration/E2E test; use `.a11y.test.tsx` only when
a focused set improves clarity. Assert role/name/label, keyboard operation, focus movement/return,
error association (`aria-describedby` where applicable), live status, and non-color signals.
Use Playwright for browser-level tab order/navigation only when jsdom cannot prove it.

`jest-axe` and Playwright axe integration are optional and not installed. Even if adopted, scans
supplement manual keyboard, screen-reader, zoom/reflow, contrast, and assistive-technology review;
they do not certify WCAG conformance.

Done: key interactions work without pointer-only assumptions and accessible names/errors are
observable.

## 3.6 Security tests

**Location:** colocated `.security.test.ts[x]`, or mocked Playwright when a browser journey is
required.

Test client-owned positive and negative paths: safe URL allow-listing/open-redirect resistance,
unsafe HTML/content rendering, untrusted filenames and inputs, sensitive-data/stack-trace leakage,
expired/missing token and logout UX, and permission-state presentation. Feed adversarial payloads
through controlled mocks; assert rejection, safe encoding/rendering, no unsafe navigation, and no
visible secret/internal detail.

Do not call a real third party. Require backend security tests for authorization, IDOR, token
enforcement, rate limiting, and server-side validation; the UI is not a security boundary.

Done: both accepted and rejected paths are explicit and no assertion depends solely on hidden UI.

## 3.7 Property-based tests with fast-check

**Location:** colocated `<subject>.property.test.ts`.

`fast-check` 4.7.0 is installed but no direct adoption was found in current `src` tests. Use it for
pure parsers, serializers, normalizers, reducers, URL builders, and state transitions. Define
domain-shaped bounded arbitraries and invariants such as round-trip, idempotence, canonical
normalization, valid output shape, no forbidden URL, or agreement with a small independent
reference model. Retain concrete regression examples for known faults.

No generated network/filesystem I/O, uncontrolled time, or vacuous invariant. Preserve the seed
and shrunk counterexample reported by a failure.

Done: the invariant is meaningful, bounded, reproducible, and complements example tests.

## 3.8 Playwright E2E — mocked project

**Location:** `e2e/tests/<journey>.spec.ts`.

Import `test` and `expect` from `e2e/fixtures/test.ts`. Its automatic `mockApi` and `mockSse`
fixtures isolate backend REST/SSE; use the supplied page object where it improves repeated journey
vocabulary. Add a page object only for real reuse—do not build a speculative mega-object.

Use role-based locators and Playwright web-first assertions. Keep one critical journey per
behavior, drive deterministic fixture events/responses, and assert UI plus owned outbound REST/SSE
contracts. The mocked project must never reach a real backend or third party.

```powershell
npx playwright test --project=mocked e2e/tests/<journey>.spec.ts
npm run e2e
```

Done: the default deterministic browser project passes without external services or arbitrary
waits.

## 3.9 Playwright E2E — live project

**Location:** `e2e/tests/<journey>.live.spec.ts`.

Import `liveTest` and `expect` from `e2e/fixtures/live.ts`. Run only with intentionally configured
real backend/provider access and seeded credentials supplied through the environment. Keep a few
golden and failure paths; for AI behavior assert statuses, shape, required/non-empty sections, and
invariants—never exact model prose.

```powershell
npx playwright test --project=live e2e/tests/<journey>.live.spec.ts
npm run e2e:live
```

Live is not the mandatory default PR suite. If prerequisites are absent, record **not run** rather
than converting the test to mocked behavior or claiming success.

## 3.10 Visual regression

Current screenshot/fidelity assets create human-reviewed galleries; no automated pixel-diff
baseline suite is adopted. Playwright's built-in `toHaveScreenshot` can be an optional future layer
only for stable deterministic mocked surfaces with explicit baseline ownership, browser/OS/font
discipline, and review.

Creating or updating a baseline is an **UPDATE gate**: obtain explicit approval, update only the
named screenshot, inspect the image diff, and rerun the targeted mocked test without update mode.
Never accept all changed baselines, treat ordinary DOM snapshots as visual proof, or make a
snapshot-heavy component suite. Third-party visual tools require separate pinned approval.

Done: behavior assertions still exist, baseline ownership is clear, and every changed pixel diff
was intentionally reviewed.

## 3.11 Performance tests

**Location:** colocated `.performance.test.ts[x]` for isolated logic, or controlled mocked
Playwright only when browser measurement is essential.

Profile before adding a budget. Record hardware/runtime/browser context, warm-up strategy,
baseline distribution, sample count, and a threshold with meaningful headroom. Isolate pure hot
transforms or stable render/stream behavior; remove third-party network and control input size.
Never use a razor-thin threshold or one noisy wall-clock sample.

No benchmark or Lighthouse test package is installed. Recommend one only with explicit pinned
approval; do not claim benchmark-grade evidence from an ordinary timer assertion.

Done: the budget is repeatable, justified by a baseline, resistant to normal variance, and detects
a meaningful regression.

## 3.12 Smoke tests

**Location:** `e2e/tests/<surface>.smoke.live.spec.ts`, collected by the existing `live` project.

Keep smoke minimal: verify application/page readiness and one critical authenticated flow using
stable status/shape/visible invariants. Use `npm run e2e:live`; no separate smoke script or project
exists. Do not broaden smoke into exhaustive E2E.

If real-service prerequisites are absent, report not run. A mocked pass is not evidence that the
deployed system is alive.

## Step 4 — Verification matrix and evidence

Record each selected layer before finishing:

| Type | Required / recommended / N/A | Path | Command | Observed result | Deferral reason |
|---|---|---|---|---|---|

Vitest work iterates with a targeted `npx vitest --run <path>` (or
`npm run test:no-coverage -- <path>`) and closes with `npm run test`. Frontend code/test changes
also run `npm run typecheck` and `npm run lint`. Browser work uses a targeted bounded Playwright
command, then `npm run e2e`; run `npm run e2e:live` only with intentional prerequisites.

Record a real result—pass, fail with evidence, or not run with reason. Never record an expected
result as observed.

## Step 5 — Done criteria

- Every required layer exists and passes; no weaker layer is counted as a stronger one.
- The V8 global gate remains at least 80% for lines, functions, branches, and statements.
- Default Vitest and mocked Playwright suites are deterministic and make no third-party calls.
- Mocked/live files remain in their exact projects and live prerequisites are explicit.
- Async interactions are synchronized; negative paths and accessibility behaviors are covered.
- Contract/visual snapshot changes passed explicit UPDATE review gates.
- Performance budgets have measured baselines and headroom.
- Optional tools are labeled accurately and were not imported implicitly.

## Forbidden

- Watch mode, separate manually started servers in automation, or non-npm package managers.
- Real third-party calls in Vitest or mocked Playwright.
- Exact unstable AI prose, giant snapshots, broad snapshot updates, or implementation-only
  assertions.
- Arbitrary sleeps, un-awaited interactions, skip/flaky bypasses, shared mutable state, or
  uncontrolled time/randomness.
- Accessibility automation as a replacement for manual review.
- Frontend auth visibility as proof of backend authorization/security.
- Invented npm scripts, projects, tags, suites, or claims that axe/MSW/mutation/visual/benchmark
  tooling is installed.

---
inclusion: auto
name: frontend-unit-test-writing
description: Phased procedure for trustworthy Flowin React and TypeScript unit, component, and hook tests with Vitest, jsdom, React Testing Library, and user-event, including branch and interaction analysis, deterministic boundary mocks, coverage closure, and manual kill-test verification. Use when writing or improving frontend unit/component/hook tests; do not use for Python/pytest tests.
---

# Frontend Unit, Component, and Hook Test Writing Procedure

Act as a senior frontend test engineer. Test one frontend subject or cohesive feature at a time with
real production logic; never refactor production code merely to make testing convenient.

`frontend-testing-structure` owns placement and naming, `frontend-test-playbook` owns layer
selection, and `frontend-coding-guardrails` owns general React/Next.js, accessibility, security,
and validation rules. For `frontend/**`, these frontend files take precedence over backend-only
`testing-structure`, `testing-conventions`, `unit-test-writing`, and `testing-playbook` guidance.

## Modes

- **WRITE TESTS** — no adequate colocated test exists; create the smallest complete test file.
- **IMPROVE COVERAGE** — tests exist or a measured branch/interaction gap is named; add only
  behavior that closes a real gap.

If no mode is named, use IMPROVE COVERAGE when an existing test covers the subject; otherwise use
WRITE TESTS. Record the selected mode before analysis.

## Absolute rules

1. Read source, exported types, representative callers, existing tests, and live config before
   naming a symbol, signature, import, prop, state, or response shape. Never invent one.
2. Execute the real subject logic. Never mock the subject or duplicate its algorithm in the
   expected value.
3. Assert one observable behavior or public hook/function contract per test with exact, meaningful,
   independently derived expectations.
4. Test behavior, not React internals: avoid private state, implementation-specific call order,
   hook internals, child internals, and CSS class strings as the sole outcome.
5. Prefer accessible queries in this order: role + accessible name, label, placeholder/display
   value, text when text is the contract, then `data-testid` only when no semantic selector exists.
   Scope repeated regions with `within`. Document why a test ID is necessary.
6. Use `const user = userEvent.setup()` and await every interaction. Use `fireEvent` only for a
   low-level event that user-event cannot express, and explain why.
7. For async UI, prefer `findBy*` for appearance, `waitFor` for an eventual assertion, and
   `queryBy*` for absence after synchronization. Never use arbitrary sleeps or leave a promise,
   user action, timer advancement, or state update un-awaited.
8. Mock system boundaries as imported by the subject—not React, Testing Library, the subject, or a
   custom hook merely because a component consumes it.
9. Control network, provider responses, wall clock, timers, randomness, UUIDs, storage, and missing
   browser APIs. Tests must not share mutable state or depend on execution order.
10. Do not use real backend/third-party traffic in Vitest, exact unstable AI prose, broad snapshots,
    watch mode, skips as a repair, coverage suppression, or an unapproved dependency.
11. Snapshot assertions are exceptional. A stable contract snapshot or future Playwright visual
    baseline requires explicit owner approval, a narrowly targeted update, and human review of the
    complete diff. Never run broad snapshot-update mode to make failures green.
12. Async React Server Components are not jsdom-mountable client components. Test their pure
    collaborators directly, their `'use client'` interactive leaves with RTL, and route-level
    server data/render output at an integration/E2E layer.
13. Accessibility automation supplements—not replaces—semantic assertions and manual keyboard,
    screen-reader, zoom/reflow, contrast, and assistive-technology review.
14. Do not change production behavior to satisfy a test. Preserve and report evidence of a likely
    defect rather than weakening the assertion.

## Autonomy and artifact discipline

May proceed without asking: read workspace files, run bounded checks, create a new correctly
colocated test, and create/refresh the Markdown evidence below. Ask before editing shared
`vitest.setup.ts`, runner/coverage config, dependencies, broad portions of existing tests, or
production behavior.

Evidence belongs only under `unit-test-prompt/test-files/`; executable test code belongs only in
its canonical `frontend/src/**` location. For subject path `frontend/src/hooks/useThing.ts`, use
slug `src__hooks__useThing` (path relative to `frontend/`, extension removed, separators replaced
with `__`):

```text
unit-test-prompt/test-files/<frontend_slug>/
├── 00-context.md
├── 01-analysis.md
├── 02-test-plan.md
├── 03-verification.md
├── 04-coverage.md       # when coverage is measured/closed
└── 05-summary.md
```

Never place TypeScript test code in this artifact tree.

## PHASE 0 — Gather context

Read before planning:

1. The complete subject and its exported/public types.
2. Imported project collaborators and the parent/representative callers that establish the public
   contract.
3. Nearest existing tests, typed builders, render wrappers, mocks, and helpers.
4. `frontend/package.json`, `vitest.config.ts`, `vitest.setup.ts`, and `tsconfig.json`.
5. Relevant Next router, provider, context, store, Server/Client Component, and browser boundaries.
6. Playwright config/fixtures only when the behavior may require a real browser.

Inventory actual capabilities: Vitest 4.1.11, V8 coverage, RTL 16.3.2, jest-dom, user-event
14.6.1, jsdom, fast-check 4.7.0, and Playwright 1.60.0. Record `jest-axe`/direct axe integration,
MSW, JavaScript mutation tooling, and an adopted automated visual-baseline workflow as absent; do
not import them.

In IMPROVE COVERAGE mode, run the existing target without coverage first. Use `npm run test` and
its generated V8 report for measured global/per-file gaps; never infer coverage from test count or
a targeted pass.

Write `00-context.md`:

| Item | Evidence to record |
|---|---|
| Source/public contract | path, exports, props/return types, states and errors |
| Dependencies | imported boundary and exact lookup/import path |
| Callers/owners | representative parent, consumer, route, or provider |
| Existing tests/helpers | paths, behaviors already covered, reusable wrappers/builders |
| Environment/setup | jsdom behavior and relevant setup polyfills |
| Config/runner | include/exclude, alias, target command, project if relevant |
| Coverage | measured lines/functions/branches/statements or N/A |
| Missing facts | none, or a concrete blocker requiring user input |

Do not continue if an essential symbol, contract, or environment fact cannot be found.

## PHASE 1 — Analyze branches and interactions

Inventory every exported function/component/hook and its typed contract. Build a boundary map for
props, context/providers, router/navigation, API/fetch modules, storage, timers, browser APIs,
randomness/IDs, dynamic imports, and child-render boundaries. Record the exact module identifier as
imported by the subject; mock where it is looked up.

Assign IDs:

- **Branches `B1...`**: each condition/sub-condition, discriminated UI state, early return/error,
  optional prop, empty/single/many loop case, retry/timeout, effect/cleanup, event handler, keyboard
  path, and loading/error/empty/ready state.
- **Interactions `I1...`**: user action or hook operation through its observable DOM, callback,
  navigation, storage, or public-state result.
- **Accessibility `A1...`**: role/name, label/error association, keyboard operation, focus behavior,
  and non-color signal.

Write `01-analysis.md` with these tables:

| Inventory | Signature/props/return | Public purpose |
|---|---|---|
| Boundary | Kind | Exact import/lookup | Control strategy |
| Branch ID | Decision/state | Outcomes |
| Interaction ID | Action | Observable outcome |
| A11y ID | Input/mechanism | Observable requirement |
| Behavior ID | Branch/interaction IDs | When | Then |

## PHASE 2 — Plan before code

Use `describe("Subject")` and `it("outcome when condition")`. Use `it.each` with readable case
labels only for different data through the same behavior path. Do not duplicate behavior already
covered in IMPROVE COVERAGE mode.

Each planned case records:

| # | Test title | IDs | Arrange | Act | Exact observable assert | Boundary assert | Query/sync |
|---|---|---|---|---|---|---|---|

Also map every relevant branch/interaction/accessibility ID to a case, list typed builders and the
smallest provider wrapper, and list intentionally excluded branches with a concrete reason. Cover
loading, success, empty, error, disabled/permission, cleanup/unmount, and keyboard/focus states
when the subject exposes them. Boundary-call assertions belong only where request/navigation/
callback shape is part of the public contract.

Write this evidence to `02-test-plan.md` before test code.

## PHASE 3 — Write tests

- Follow existing import and formatting style; group tests by subject/behavior.
- Use Arrange/Act/Assert comments only when they improve readability.
- Build minimal typed data with literal expected results independent of production algorithms.
- Render through the smallest real provider wrapper; do not replace all collaborators with mocks.
- Use RTL semantic queries and jest-dom matchers that express the user-visible contract.
- For hooks, use `renderHook`, `act`, `rerender`, and `unmount` as required; assert public return
  state and observable effects.
- Use fake timers only when time owns the behavior. Install before render, explicitly advance,
  flush resulting work, and restore real timers in cleanup.
- Reuse `vitest.setup.ts`'s in-memory `localStorage` and `ResizeObserver` before hand-rolling
  replacements.

### Boundary mocking

Mock only the narrow system boundary: API/client module or fetch transport, Next navigation,
storage, time/random/UUID, browser APIs absent in jsdom, or an expensive animation shell when its
behavior is not under test. Do not mock React, RTL, the subject, every child, or a custom hook just
to isolate its consumer.

Follow established `vi.hoisted`/`vi.mock` patterns where hoisting is required. Keep router/provider
objects stable for the test's lifetime. Use `vi.clearAllMocks()` or a targeted reset between cases,
and `vi.restoreAllMocks()`, `vi.unstubAllGlobals()`, timer restoration, and unmount cleanup when the
test changes globals or implementations. Do not reset away shared setup polyfills accidentally.

Determinism requires fixed timestamps/IDs/random values, controlled resolved/rejected promises,
explicit fake-timer advancement, and boundary-controlled network responses. Include successful,
empty, malformed, rejected, timeout/retry, and negative/security responses when those branches
exist.

### Snapshot update gates

Prefer focused semantic assertions. Use a contract snapshot only when the serialized shape itself
is stable and reviewing the whole shape is valuable. Any snapshot or approved visual-baseline
change must be separately authorized, updated only for the targeted case, inspected by a human,
and rerun without update mode. A changed snapshot is not automatically correct.

## PHASE 3.5 — Targeted execution

Iterate with a bounded target from `frontend/`:

```powershell
npm run test:no-coverage -- src/<path>/<subject>.test.tsx
# Equivalent direct invocation of the installed local runner:
npx vitest --run src/<path>/<subject>.test.tsx
```

Fix test defects—wrong import target, wrapper, synchronization, or expectation—and rerun. If a test
exposes production behavior that contradicts the established contract, keep the failing evidence
and report it; do not weaken, skip, or snapshot-update around it.

After the target passes, run:

```powershell
npm run typecheck
npm run lint
```

Do not proceed while the authored test introduces a static-check failure.

## PHASE 4 — Manual mutation / kill-test verification

No JavaScript mutation tool is installed. Do not claim one ran.

For each important branch/interaction, name one minimal mutation: invert a condition, remove a
callback/navigation, change a return value, omit cleanup, or swap loading/error state. Temporarily
apply only that mutation locally, run the targeted no-coverage command, and confirm the intended
test fails for the expected observable reason. Restore the source immediately, verify the diff is
clean of the mutation, and rerun green. Never commit or leave a production mutation.

Write `03-verification.md`:

| Mutation | Killing test | Expected failure | Observed failure | Restored | Green rerun |
|---|---|---|---|---|---|

If a mutation survives, strengthen the observable assertion and repeat. Delete decorative test
logic rather than counting a test that cannot detect a relevant fault.

## PHASE 5 — Coverage gap closure

Run `npm run test` for the authoritative V8 report. The config includes all
`src/**/*.{ts,tsx}` source files and enforces **80% lines, functions, branches, and statements**.
A targeted pass does not prove this global gate.

Read measured file gaps and prioritize error/security paths, state transitions, boundaries, and
business rules before trivial lines. Add only behaviorally valuable cases; repeat targeted
execution and kill verification, then rerun `npm run test`.

Never add exclusions, coverage suppression, or weaker thresholds to improve the number. Record a
genuinely unreachable/generated/framework-owned case for human review instead.

Write `04-coverage.md`:

| File | Lines | Functions | Branches | Statements | Missing |
|---|---:|---:|---:|---:|---|
| Before (measured) | | | | | |
| After (measured) | | | | | |

Add a gap table with condition, risk, planned test, and outcome. Do not estimate missing numbers.

## PHASE 6 — Summary and done criteria

Write `05-summary.md` with:

- mode, source path, test path, tests/cases added, and covered branch/interaction/a11y IDs;
- targeted result, full `npm run test` result, all four 80% metrics, typecheck, and lint;
- manual mutations killed/survived and proof the source was restored;
- bugs exposed, assumptions, deferred cases, and recommended higher-layer tests.

The run is done only when real logic executes, boundaries are deterministic, async work is
synchronized, assertions express meaningful behavior, the target/static/full coverage checks pass
as applicable, and manual kill evidence exists. Report unavailable higher-layer prerequisites as
not run; never imply success.

## Framework-specific patterns

| Subject | Preferred pattern | Required concerns |
|---|---|---|
| Pure function/reducer | Direct typed call with hand-derived literals | boundaries, invalid input, empty/single/many, immutability |
| Component/form | RTL render + awaited user-event | labels, validation, pending/success/error, double-submit, focus |
| Hook/effect/timer | `renderHook` + `act`/rerender/unmount | public state, dependencies, cleanup, controlled time |
| Next navigation | Mock the imported navigation boundary | destination/parameters and user-visible fallback; browser flow in mocked E2E |
| API module | Mock transport, not adapter logic | request shape, 2xx, malformed payload, 4xx/5xx, timeout/rejection |
| Context/provider/store | Small real wrapper and real reducer/provider | initial state, transition, consumer output, cleanup |
| Suspense/loading/error | Controlled promise or established boundary | fallback, resolved content, rejection/retry, no dead spinner |
| React Server Component | Pure server collaborator test + browser/integration proof | do not mount async RSC in jsdom; test client leaves separately |
| AI-output consumer | Typed representative payloads | schema/status, required sections, missing/malformed fields, safe rendering—not exact prose |

## Forbidden anti-patterns

```ts
expect(result).toBeTruthy();                         // vague alone
expect(normalize(value)).toEqual(normalize(value));  // expected value uses subject
vi.mock("./normalize", () => ({ normalize: vi.fn() })); // mocks subject
expect(componentState.currentStep).toBe(2);          // private implementation state
container.querySelector("button")!.click();          // semantic role exists
user.click(screen.getByRole("button"));              // un-awaited interaction
await new Promise((resolve) => setTimeout(resolve, 500)); // arbitrary sleep
await fetch("https://third-party.example/data");     // real network
expect(container).toMatchSnapshot();                 // giant undifferentiated snapshot
expect(screen.getByText("exact generated paragraph")).toBeVisible(); // unstable AI prose
sharedResult.push(result);                            // test-order dependence
import { axe } from "jest-axe";                      // capability is not installed
```

Also forbidden: computing expectations from copied production constants when the contract has an
independent literal, asserting only mock choreography, mocking all child components, broad
snapshot updates, swallowing rejected promises, leaving fake timers/globals active, and claiming
an optional tool ran.

## When unsure

- Search source, types, callers, existing tests, and live config; never guess.
- If current behavior is ambiguous, record a precise assumption and test the observable current
  contract unless product intent must be decided.
- If behavior is meaningful only in a browser, recommend the playbook's mocked E2E recipe rather
  than forcing jsdom.
- If a capability is missing, list it as an optional pinned recommendation; never import it.
- If production behavior appears wrong, preserve evidence and ask for the product decision before
  changing what users see.

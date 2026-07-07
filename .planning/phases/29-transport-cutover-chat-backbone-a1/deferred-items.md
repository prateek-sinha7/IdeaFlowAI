# Phase 29 — Deferred / Out-of-Scope Items

Append-only log of discoveries encountered during execution that are **outside**
the current plan's file allow-list. Do NOT fix these inside the discovering plan.

---

## DEF-29-06-1 — Pre-existing `feat/ui-2` mocked-suite breakage (NOT caused by 29-06)

- **Discovered during:** 29-06 Task 3 (full mocked Playwright regression run).
- **Symptom:** ~120 of the 123 mocked specs time out at 45s. The failures are
  home-render assertions, e.g. `getByRole('button', { name: /Generate product
  requirements/i })` → "element(s) not found". The dashboard **home heading**
  ("What would you like to build today?") still renders, but the old CreationHub
  workflow-row buttons the specs target do NOT.
- **Root cause (pre-existing, app-side):** The `feat/ui-2` branch redesigned the
  dashboard home. The current home renders a new nav (`Home / Library /
  Catalogue / Notifications`) + a `Create workflow` button — the legacy
  text-labelled CreationHub rows the 123 specs were written against are gone.
  Confirmed via the Playwright accessibility snapshot (error-context.md). Recent
  `feat/ui-2` commits responsible: `9c7b78bb` (redesign AgentsPopup workflow
  config; move Saved Workflows to profile dropdown), `fe7a351b` (KAN-78 restore
  workflow names / home layout).
- **Proof it is NOT 29-06:** 29-06's entire diff is 3 files —
  `frontend/e2e/fixtures/mockWs.ts`, `frontend/e2e/fixtures/mockSse.ts`,
  `frontend/e2e/tests/ts-sse.spec.ts` — **zero** `frontend/src/` app code
  (`git diff --name-only 6c5de02a~1 HEAD`). The failing assertions are on
  app-rendered home content that renders **before any WS/SSE interaction**;
  `TS-B-07` fails on a pure home-render check with **no WS/SSE involvement**.
  The mockWs edit is purely additive (existing helper bodies byte-identical).
  29-06's own spec `ts-sse.spec.ts` passes 2/2, and `dashboard.goto()` (home
  heading + `ws.ready()`) succeeds — the mock transport is healthy.
- **Disposition:** OUT OF SCOPE for 29-06 (allow-list is the 3 files above;
  fixing the home / `mockApi` workflow-catalogue data source is app + non-allow-
  listed-fixture work). The plan's "keep the 123 mocked specs green" bar assumed
  a green baseline that no longer exists on `feat/ui-2`. Owner: the `feat/ui-2`
  UI-convergence workstream must realign the mocked specs (and likely the
  `mockApi` workflow-catalogue stub) with the redesigned home — a dedicated
  spec-realignment task, not this additive transport-driver plan.
- **29-06 verification substituted (per OFFLINE VERIFICATION DISCIPLINE):**
  `npx tsc --noEmit` clean + targeted `ts-sse.spec.ts` green (2/2). Full-suite
  "123 green" bar DEFERRED to the `feat/ui-2` spec-realignment task.

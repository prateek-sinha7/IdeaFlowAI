# Integration / E2E test suite

End-to-end coverage of the VelocityAI (Flowin) web product, driven through the
real UI in a real browser. This directory holds the **specification** the tests
are written against, plus the captured evidence those specs were derived from.

## Why this exists

Unit and component tests already cover the frontend (1,233 vitest cases) and the
backend (3,924 pytest cases). Neither answers the question this suite exists to
answer: **does the assembled product still work when a person clicks through it?**

Several defects recorded in `.knowledge/` were invisible to both suites and only
surfaced in a live browser — FIX-302 (a remount wiped run state, so a PPT run
rendered as "USER STORIES"), FIX-306 (an override saved and rendered, then 400'd
on every launch), BUG-030 (a tab click remounted the run and lost its data).
Every one of them passed its own unit tests. That is the gap this suite closes.

## Phases

| Phase | What | Status |
|---|---|---|
| **1 — Record** | Walk every screen in a real browser, capture what is there, write the spec | **this commit** |
| **2 — Automate** | Turn each `Scenario` below into a runnable Playwright test | not started |
| **3 — Gate** | Run the suite after every change; all green before merge | not started |

Phase 1 deliberately writes **no test code**. The specs come first so that phase 2
is transcription rather than discovery, and so the specs stay reviewable by
someone who does not read Playwright.

## Layout

```
tests/integration/
├── README.md              this file
├── PAGES.md               the per-page index: every URL → shot → fingerprint → spec
├── MANIFEST.md            the scored surface checklist, derived from source
├── INVENTORY.md           every route, its screen, and where its spec lives
├── DEFECTS-OBSERVED.md    what the sweeps found that looks wrong, plus corrections
├── screens/               the specs — 17 files, one per surface, Gherkin scenarios
├── capture/               raw DOM fingerprints (evidence)
│   ├── FIXTURES.json      the live ids the sweep used, and why not to trust them
│   ├── _enumerate.py      lists the surface from frontend/src — run this FIRST
│   └── _dump.py           prints a fingerprint readably
└── screenshots/           80 full-page PNGs
    ├── 01-auth … 11-errors    one folder per area, pNN per page URL
    ├── 12-overlays/           modals, menus and drawers — not pages
    └── 13-states/             themes, tiers, run states, tab variants
```

**Start at `PAGES.md`.** It is the per-page record: all 55 page URLs, what each
one actually does, and where its screenshot, fingerprint and spec live.

## How the capture was made

- **Real Google Chrome 151**, not Playwright's bundled Chromium — driven over CDP
  with `--browser chrome`, so what was captured is what a user sees.
- Signed in as `qa-admin@flowinqa.com` (tier `enterprise`, `is_admin` true), which
  is the only account that can reach every screen including `/admin`.
- Served from the **main checkout** (`feat/conditional-gates`, with uncommitted
  changes present), not from this worktree. The specs describe that build.
- Every route was reached by a **cold navigation** (`page.goto`), never by
  client-side clicking into it. Cold-load fidelity is the point: three of the
  defects listed above only appear on a cold load or a remount.
- **A 2.5s settle after every navigation**, before the fingerprint and the shot.
  Several screens paint a transient state and resolve a moment later; without the
  settle the capture records the wrong frame.
- **The surface list came from source before any capture.** `_enumerate.py` reads
  `frontend/src` for page files, `ParsedView` cases, overlay components and
  empty/error branches; `MANIFEST.md` is that output turned into a scored
  checklist. Sweep 1 walked the app by clicking and reported "41 screens" as if
  complete — it was 51%. Enumerate first, then capture against the list.

## Conventions for the specs

- **Gherkin, loosely.** `Feature` / `Scenario` / `Given-When-Then`. Not parsed by
  any runner — a human contract that phase 2 transcribes.
- **Selectors are named where they are stable.** `data-testid` first, then
  `aria-label`, then role. Text is a last resort: it changes with copy edits and
  several labels in this app are not unique on the page.
- **No assertions on live data.** Run ids, workflow names, and counts in
  `capture/` are dev-database state and will not survive a reset. A scenario that
  needs a run must create one.
- **`@defect` tags** mark scenarios that describe behaviour believed to be WRONG.
  They are written as the product behaves **today** so phase 2 has a baseline, and
  cross-referenced in `DEFECTS-OBSERVED.md`. When one is fixed, its scenario is
  rewritten to the correct behaviour and the tag dropped.
- **`@destructive` tags** mark scenarios that write or delete. They need their own
  fixtures and must not run against a shared dev database.
- **Every routing claim is backed by a capture, never by reading the router.**
  Five earlier claims were wrong for exactly that reason — `parseViewPath`'s
  return value is not the user's destination, and a stale comment in `routes.ts`
  is not the code. They are recorded as C-1 … C-5 in `DEFECTS-OBSERVED.md` rather
  than quietly deleted.

## Running (phase 2, not yet built)

Both servers must be up before any of this suite runs:

```
frontend  http://localhost:3000
backend   http://localhost:8000
```

Seed users come from `backend/scripts/seed_test_users.py` (via
`scripts/local-dev/setup-backend.sh`); the password is overridable with
`E2E_BASE_PASSWORD`.

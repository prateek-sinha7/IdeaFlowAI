# Run-Screen Fidelity Harness (Phase 39 · D39-6 oracle)

The **two-sided screenshot oracle** every Phase 39 surface plan (39-01..39-06)
diffs against. It renders the three target mocks **and** our current run screen,
then assembles a **side-by-side gallery** a human reviewer signs off on.

There is deliberately **no automated pixel-diff**: our live data never equals the
mock's hardcoded values (ND-D), so a pixel compare would always "fail". The
fidelity judgment is a **human review** of the assembled gallery, closed to the
intended-divergence register (ND-A..ND-H) below.

## Pieces

| File | Role |
|------|------|
| `serve-mocks.mjs` | Static HTTP server for the `.dc.html` target mocks (so `support.js` + Google fonts resolve — a `file://` origin can't). |
| `capture-mocks.mjs` | Playwright capture of the TARGET mocks per tab → `shots/target/{surface}__{state}.png`. |
| `../tests/zzz-baseline.spec.ts` | Env-gated (`FIDELITY_CAPTURE=1`) capture of OUR run screen → `shots/current/{surface}__{state}.png`. |
| `assemble-gallery.mjs` | Pairs `target/*` + `current/*` into one self-contained `gallery.html` (the checkpoint artifact). |

`shots/` and `gallery.html` are **git-ignored** — only the scripts + this README
are committed.

## Commands

```bash
# 1. OUR side — capture the current run screen (settled / live / failed).
#    Env-gated so a normal `npm run e2e` skips this spec.
FIDELITY_CAPTURE=1 npm --prefix frontend run e2e -- zzz-baseline

# 2. TARGET side — render + capture the three mocks over the local HTTP server.
#    Needs NETWORK (the DC runtime loads React + Babel + fonts from a CDN).
node frontend/e2e/fidelity/capture-mocks.mjs
#    (spot-check the server alone: node frontend/e2e/fidelity/serve-mocks.mjs)

# 3. Assemble the side-by-side gallery (all surfaces, or one).
node frontend/e2e/fidelity/assemble-gallery.mjs
node frontend/e2e/fidelity/assemble-gallery.mjs --surface steps   # one section

# 4. Open the artifact and review.
open frontend/e2e/fidelity/gallery.html
```

## `shots/` layout

```
shots/
  target/   {surface}__{state}.png   # from capture-mocks.mjs (the mock)
  current/  {surface}__{state}.png   # from zzz-baseline.spec.ts (ours)
```

- **surface** ∈ `preview` · `steps` · `steps-detail` · `files` · `audit` · `leftlane` · `full`
- **state** ∈ `settled` · `live` · `failed`

## How each surface checkpoint regenerates + reviews its section

Each surface plan's human-verify checkpoint (e.g. 39-01 Task 4) runs:

```bash
FIDELITY_CAPTURE=1 npm --prefix frontend run e2e -- zzz-baseline   # refresh ours
node frontend/e2e/fidelity/capture-mocks.mjs                       # refresh target
node frontend/e2e/fidelity/assemble-gallery.mjs --surface leftlane # its section
```

then opens `gallery.html` and confirms every visible difference is a registered
ND divergence below. Any **other** departure is a fidelity gap to fix before
approving.

## Intended-divergence register (ND-A..ND-H) — expected, IGNORE

Captioned in the gallery header as "expected — ignore". Source: `39-01-PLAN.md`
(ND-A..ND-G) + `39-07-PLAN.md` (ND-H).

| # | Divergence | Mock says | We ship | Why |
|---|-----------|-----------|---------|-----|
| ND-A | Brand wordmark | "HEXAWARE" | "VelocityAI" | product brand (SC-001 / D39-5) |
| ND-B | Nav label | "Catalogue" | "My Workflows" | D-11 (Catalogue reserved for the marketplace) |
| ND-C | Nav active-state (underline) | mock's treatment | purple underline | ND-13.1 |
| ND-D | All run data | hardcoded ("14.8M tokens", the fixed transcript, "150 design systems", fixed audit rows) | LIVE data from `pipelineState` / real endpoints | SC-001 (D39-4) |
| ND-E | Left-lane width | 390px | responsive `md:w-[340px] lg:w-[360px]` | keep our responsive shell |
| ND-F | Prototype scrubber / image-slot | left-lane segmented scrubber + "drop a screenshot" | NOT reproduced | demo-only affordances |
| ND-G | Deliverable renderers | mock's hardcoded website/deck/doc | REUSE existing renderers | D39-3 |
| ND-H | Share action | — | client-only Share link (v1) | additive, client-only in v1 |

## Optional: self-regression baseline (NOT built here)

After a surface is human-approved, a `toHaveScreenshot` of OUR approved surface
can be committed as a **self-baseline** so later waves catch unintended
regressions. That is distinct from fidelity-vs-mock (this harness) and is left as
a documented option, not built in 39-07.

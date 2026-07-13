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

---

# Shell Fidelity Harness (Phase 40 · D40-3 / D40-5 oracle)

The SHELL sibling of the run-screen oracle above — the two-sided gallery every
Phase-40 surface plan (40-02..40-07) diffs against for the **shell** surfaces
(Home · Library +Agents/Skills/Hooks +agent-detail · Analytics · Account
Settings · Workflow History · Catalogue / My Workflows). Same method: render the
`Hexaware Workspace v2` mock **and** our current shell, assemble a side-by-side
gallery, human sign-off. No pixel-diff (ND-D live/seeded data ≠ mock values).

## Pieces

| File | Role |
|------|------|
| `serve-mocks.mjs` | (shared) static server for the `.dc.html` mocks. |
| `capture-shell-mocks.mjs` | Playwright capture of the TARGET shell mock per surface → `shots-shell/target/{surface}__{shell\|shellfull}.png`. |
| `../tests/zzz-shell-baseline.spec.ts` | Env-gated (`SHELL_CAPTURE=1`) capture of OUR shell surfaces, on **opt-in seeded** MockApi data → `shots-shell/current/{surface}__{shell\|shellfull}.png`. |
| `assemble-shell-gallery.mjs` | Pairs `target/*` + `current/*` into `gallery-shell.html`; carries the finalized ND register; `--surface <name>` filters to one surface's section. |

`shots-shell/` and `gallery-shell.html` are **git-ignored** — only the scripts +
this README are committed.

## Commands

```bash
# 1. OUR side — capture the current shell surfaces (Catalogue / History /
#    Analytics render POPULATED from the opt-in seeded MockApi). Env-gated so a
#    normal `npm run e2e` SKIPS this spec.
SHELL_CAPTURE=1 npm --prefix frontend run e2e -- zzz-shell-baseline

# 2. TARGET side — render + capture the Hexaware Workspace v2 mock.
#    Needs NETWORK (the DC runtime loads React + Babel + fonts from a CDN).
node frontend/e2e/fidelity/capture-shell-mocks.mjs

# 3. Assemble the side-by-side shell gallery (all surfaces, or one).
node frontend/e2e/fidelity/assemble-shell-gallery.mjs
node frontend/e2e/fidelity/assemble-shell-gallery.mjs --surface history   # one section

# 4. Open the artifact and review.
open frontend/e2e/fidelity/gallery-shell.html
```

All three default to a **repo-relative** base (`e2e/fidelity/shots-shell/`); set
`PHASE40_OUT=/abs` to override for scratch runs.

## `shots-shell/` layout

```
shots-shell/
  target/   {surface}__{state}.png   # from capture-shell-mocks.mjs (the mock)
  current/  {surface}__{state}.png   # from zzz-shell-baseline.spec.ts (ours)
```

- **surface** ∈ `home` · `library` · `library-agents` · `library-skills` · `library-hooks` · `library-agent-detail` · `analytics` · `settings` (+`-model`/`-limits`/`-constitution`) · `history` · `catalogue`
- **state** ∈ `shell` (1440×900 viewport) · `shellfull` (full page)

> The mock emits the Library agent-detail tag as `agent-detail-drawer`; the
> assembler **aliases** it onto `library-agent-detail` so the ND-Z pair renders
> left/right rather than as two unpaired cells.

## How each surface checkpoint regenerates + reviews its section

Each Phase-40 surface plan's human-verify checkpoint runs:

```bash
SHELL_CAPTURE=1 npm --prefix frontend run e2e -- zzz-shell-baseline   # refresh ours
node frontend/e2e/fidelity/capture-shell-mocks.mjs                    # refresh target
node frontend/e2e/fidelity/assemble-shell-gallery.mjs --surface history  # its section
```

then opens `gallery-shell.html` and confirms every visible difference is a
registered ND divergence below. Any **other** departure is a fidelity gap to fix
before approving.

## Intended-divergence register (ND-A..D + ND-W..Z) — expected, IGNORE

The canonical source is the `ND` array in `assemble-shell-gallery.mjs` (captioned
"expected — ignore" in the gallery header). ND-A..D carry from Phase 39; ND-W..Z
are the Phase-40 shell divergences. The Phase-39 scoping candidates (ND-E?..H?)
and the DEFERRED Configure/Composer surfaces are NOT diffed in Phase 40.

| # | Divergence | Mock says | We ship | Why |
|---|-----------|-----------|---------|-----|
| ND-A | Brand wordmark | "HEXAWARE" | "VelocityAI" | product brand (SC-001) — carried |
| ND-B | Catalogue nav label + title | "Catalogue" | "My Workflows" | D-11 (Catalogue reserved for the marketplace) — carried |
| ND-C | Nav active-state | pill-fill | purple underline | ND-13.1 — carried |
| ND-D | All shell data | hardcoded rows/counts/charts | LIVE data; empty surfaces use opt-in W1 seeding for the diff only | SC-001 — carried |
| ND-W | Workflow History title | "Workflow History" | "Run History" | matches the profile-menu label (parallel to ND-B) |
| ND-X | Home prompt affordances | Attach + Voice | Attach only | no product voice-input capability (demo-only affordance not reproduced) |
| ND-Y | Settings profile form | fabricated name/role/org | only real user-backed fields (email, plan/tier) | never fabricate unpersisted data |
| ND-Z | Library agent-detail | right-side drawer | shared modal (drawer rebuild → Phase 41) | composer-owned; restyle-first scope (D40-2) |

---

# Configure + Composer Fidelity Harness (Phase 41 · B7 · HARN-01 oracle)

The oracle every Phase-41 surface plan (41-02..41-07) diffs against for the two
rebuilds Phase 40 deferred — the unified **Configure** screen and the full-page
**Composer** (Simple + Canvas views). Same method as Phase 39/40: render the
target (the `.dc.html` mocks + the **approved Canvas proposal**) and our current
surfaces, assemble a side-by-side gallery, human sign-off. No pixel-diff (ND-D
live/seeded data ≠ mock values; the Canvas gate is a design-match, ND-AJ).

## Pieces

| File | Role |
|------|------|
| `capture-shell-mocks.mjs` | (reused) TARGET capture — already emits `config`/`config-full`, `composer`/`composer-full`, and the `wizard-*` overlays. |
| `composer-canvas-proposal.html` | The **APPROVED** Canvas design reference (ND-AJ), vendored + committed; the assembler embeds it live as the Canvas LEFT/reference cell. |
| `../tests/zzz-shell-baseline.spec.ts` | Env-gated (`SHELL_CAPTURE=1`) capture of OUR surfaces; the Phase-41 driver (guarded, opt-in `seedConfigure()`) emits `config__shell` · `config-settings__shellfull` · `composer-simple__shell` · `composer-canvas__shell`. |
| `assemble-phase41-gallery.mjs` | Pairs target/reference + current into `gallery-phase41.html`; carries the finalized **ND-AE..AJ** register; `--surface config\|composer\|composer-canvas` filters to one section. |

`shots-shell/` and `gallery-phase41.html` are **git-ignored**; the scripts, this
README, and the vendored `composer-canvas-proposal.html` reference ARE committed.

## Commands

```bash
# 1. OUR side — capture the Configure/Composer surfaces (Templates/Design-System
#    overlays render POPULATED from the opt-in seedConfigure() stubs). Env-gated
#    so a normal `npm run e2e` SKIPS this spec. The Phase-41 driver is guarded —
#    it no-ops on surfaces not yet built (Waves 2–6).
SHELL_CAPTURE=1 npm --prefix frontend run e2e -- zzz-shell-baseline

# 2. TARGET side — render + capture the mocks (needs NETWORK for the DC runtime).
node frontend/e2e/fidelity/capture-shell-mocks.mjs

# 3. Assemble the side-by-side Phase-41 gallery (all surfaces, or one).
node frontend/e2e/fidelity/assemble-phase41-gallery.mjs
node frontend/e2e/fidelity/assemble-phase41-gallery.mjs --surface config
node frontend/e2e/fidelity/assemble-phase41-gallery.mjs --surface composer
node frontend/e2e/fidelity/assemble-phase41-gallery.mjs --surface composer-canvas

# 4. Open the artifact and review.
open frontend/e2e/fidelity/gallery-phase41.html
```

Repo-relative by default (`e2e/fidelity/shots-shell/` + `gallery-phase41.html`);
set `PHASE41_OUT=/abs` to override the base dir, `CANVAS_PROPOSAL=/abs` to point
the Canvas reference elsewhere.

## Phase-41 current-side tags

- `config__shell` — the unified Configure screen (Wave 2/3)
- `config-gates__shellfull` — the Review Gates accordion (carried)
- `config-settings__shellfull` — the Workflow Settings accordion/overlay (Wave 2)
- `composer-simple__shell` — the Composer Simple view (Wave 4)
- `composer-canvas__shell` — the built Composer Canvas view (Wave 5)

## Intended-divergence register (ND-AE..AJ) — expected, IGNORE

The canonical source is the `ND` array in `assemble-phase41-gallery.mjs` (captioned
"expected — ignore" in the gallery header). ND-A..D carry from Phase 39, ND-W..AD
are Phase 40's (in `assemble-shell-gallery.mjs`, UNTOUCHED). Phase 41 continues at
ND-AE.

| # | Divergence | Mock says | We ship | Why |
|---|-----------|-----------|---------|-----|
| ND-AE | Configure Templates/DS accordions | all four always render | Templates + Design System only when the deliverable declares `opendesign` | SC-001 (`acceptsTemplateDs`) |
| ND-AF | Configure selections | fabricated "Currently using…" | live registries; "None selected" until picked | SC-001 (specializes ND-D) |
| ND-AG | Composer Run cost + primary action | "Est. cost $4.50" + "Run once now" from the composer | est. cost omitted (no metering); Run via the real onStartPipeline seam; est. duration live | SC-001 |
| ND-AH | Composer "Deliverable type" | editable dropdown | `base_pipeline_type` fixed at entry → read-only | composer scope |
| ND-AI | Configure brief affordances | Attach + Voice | Attach only | no product voice-input capability (carries ND-X) |
| ND-AJ | Composer Canvas reference | no shipped `.dc.html` mock | match the APPROVED PROPOSAL (`composer-canvas-proposal.html`) — a design-match human sign-off | designed + user-approved as a proposal, not in the DC mock |

---
name: web-clone
description: >
  Website reproduction / cloning methodology. USE WHEN the user says clone website, reproduce site,
  clone a site, copy a site, replicate a site, build one just like this site,
  reproduce a certain webpage effect, port this site over and make it mine,
  reproduce a certain interaction/WebGL/Canvas/Three.js effect. Provides a portable decision tree of
  "get the real source first → decide the path → reverse-engineer → set up the project →
  swap in content", covering three major branches — static sites / React-Vue-Next content sites /
  WebGL-Canvas heavy-frontend sites — and mandates verifying any executable code from AI secondhand analysis.
metadata:
  author: jane (xiaoer)
  version: "1.6.0"
  use_case: Personal local site reproduction/learning, distilled from the website-clones cloning hub
triggers:
  - "clone website"
  - "reproduce site"
  - "clone a site"
  - "copy a site"
  - "build one just like this site"
  - "replicate a webpage effect"
  - "WebGL"
  - "Canvas"
  - "Three.js"
od:
  mode: prototype
  category: web-artifacts
  preview:
    type: markdown
  design_system:
    requires: false
  upstream: "https://github.com/Jane-xiaoer/claude-skill-web-clone"
---

# Web Clone · Website Reproduction Methodology

Turn "reproduce a website" into a repeatable process. The companion project area defaults to `./website-clones/` in the target workspace (each clone is a subdirectory). To customize the location, set `WEB_CLONE_ROOT=/absolute/path`.

When running the built-in scripts, execute commands from the user's target workspace/project root, and point `WEB_CLONE_SKILL_DIR` at this skill's directory. Do not `cd` into the skill directory to run scripts, or `./website-clones/` will end up written inside the skill package itself.

```bash
export WEB_CLONE_SKILL_DIR="/absolute/path/to/skills/web-clone"
```

## Golden Rule #1: Real source code above all — never trust AI-guessed code

> For any AI-generated "reproduction analysis / build blueprint", **the conceptual skeleton in the body text can be used as reference, but by default the executable code blocks inside it are all fabricated** and must be checked line-by-line against the real source, or copying it verbatim will break everything.

**Evidence (the marbles case)**: An AI analysis document took the original site's real architecture — "analytically solve ray-sphere intersections, encode the optical result into a displacement map, and hand it to SVG's `feDisplacementMap` to distort the real DOM" — and fabricated it into "ray-marching + SDF, treating the DOM as a texture sample." These are two completely different implementations; copying the fabricated one won't reproduce the original effect and will be N times slower. See `references/marbles-case.md` for details.

So the first move is always: **get the real source code**.

## Decision Tree (follow in order, do not skip)

### Step 0 · Build the standard project skeleton first

```bash
export WEB_CLONE_ROOT="${WEB_CLONE_ROOT:-./website-clones}"
WEB_CLONE_PROJECT="$(node "$WEB_CLONE_SKILL_DIR/scripts/init-clone.mjs" <site-name> --url <original-site-URL>)" || exit 1
export WEB_CLONE_PROJECT
```

This script creates `$WEB_CLONE_PROJECT/`, `NOTES.md`, `RECON/screenshots/`, avoiding manually missing artifacts each time. `WEB_CLONE_PROJECT` must come from the script's output, because `init-clone.mjs` normalizes the site name (spaces, casing, URLs, non-ASCII, etc. all get cleaned into a slug); subsequent steps keep using the same `WEB_CLONE_PROJECT`, ensuring the actual creation path, the default path, and any custom `WEB_CLONE_ROOT` path stay consistent.

### Step 1 · Search GitHub for the source code first — don't rush to scrape the site

```bash
unset SSL_CERT_FILE   # macOS quirk, unset before bash runs
# Search by site name / product name
SSL_CERT_FILE=/etc/ssl/cert.pem gh api "search/repositories?q=<keyword>" \
  | jq -r '.items[] | "\(.full_name) ⭐\(.stargazers_count) \(.description)"' | head -10
# The URL slug on vercel.app/netlify.app/github.io is often the repo name / deployer's username
```
- Single-file site (github.io / plain HTML) → fetch raw directly: `curl -sL https://raw.githubusercontent.com/<user>/<repo>/main/index.html`
- **Found the source and the license allows it → skip to Step 4 and clone directly.** Lesson learned: searching GitHub first can save 30 minutes of detour.

### Step 2 · No source found → browser reconnaissance (probing)

Load the `Browser` skill or the playwright MCP, run probes to gather signals (framework / `window.THREE` / canvas count / smooth-scroll libraries / fonts / scrollHeight). Take screenshots at 1440/768/390 and save recon JSON to `$WEB_CLONE_PROJECT/RECON/`.

Prefer the built-in scripts for standard recon:

```bash
node "$WEB_CLONE_SKILL_DIR/scripts/recon-site.mjs" \
  --url <original-site-URL> \
  --out "$WEB_CLONE_PROJECT/RECON" \
  --label original

node "$WEB_CLONE_SKILL_DIR/scripts/asset-harvest.mjs" \
  --recon "$WEB_CLONE_PROJECT/RECON/original-recon.json" \
  --out "$WEB_CLONE_PROJECT/assets/original" \
  --manifest "$WEB_CLONE_PROJECT/RECON/asset-manifest.json"

node "$WEB_CLONE_SKILL_DIR/scripts/network-capture.mjs" \
  --url <original-site-URL> \
  --out "$WEB_CLONE_PROJECT/RECON/network" \
  --label original

node "$WEB_CLONE_SKILL_DIR/scripts/route-crawl.mjs" \
  --url <original-site-URL> \
  --out "$WEB_CLONE_PROJECT/RECON/routes" \
  --label original \
  --max-pages 25 \
  --max-depth 2

node "$WEB_CLONE_SKILL_DIR/scripts/interaction-probe.mjs" \
  --url <original-site-URL> \
  --out "$WEB_CLONE_PROJECT/RECON/interactions" \
  --label original

node "$WEB_CLONE_SKILL_DIR/scripts/sourcemap-hunt.mjs" \
  --recon "$WEB_CLONE_PROJECT/RECON/original-recon.json" \
  --out "$WEB_CLONE_PROJECT/RECON/sourcemaps"
```

> Only use a browser-automation environment the user has already authorized for logged-in/private sites; for localhost / public sites requiring no login, use the `Browser` skill or Playwright.

### Step 2.5 · Rate the complexity first — don't overpromise blindly

Based on the recon results, first write a "pre-clone assessment": complexity L1–L6, recommended mode (faithful reproduction / visual reproduction / content overhaul), the expected achievable coverage, and what explicitly won't be cloned. Rating and scoring rules are in `references/assessment.md`.

**If the mode is "visual reproduction" or "content overhaul"** → also produce a structured design identity `design-dna.json`, turning "the feel of that site" into a versionable, comparable set of tokens, so that Step 6's replacement work has something to go on ("keep the DNA, swap the content"):

```bash
node "$WEB_CLONE_SKILL_DIR/scripts/dna-scaffold.mjs" \
  --recon "$WEB_CLONE_PROJECT/RECON/original-recon.json" \
  --out   "$WEB_CLONE_PROJECT/RECON/design-dna.json" \
  --name  "<site name>"
```

The script best-effort prefills the fonts/color candidates/framework effect signals found during recon; the remaining fields are filled in manually via Analyze. See `references/design-dna.md` for the three-part structure (design_system / design_style / visual_effects), the full schema, and applicable boundaries.
> ⚠️ **Don't use DNA on the "faithful reproduction" branch**: the real source code is the ground truth — don't let an "approximate style" DNA dilute the byte-for-byte rule.

### Step 3 · Choose the path based on recon results

|Recon result | Which path to take |
|---|---|
| Static HTML/CSS, no framework | `wget --mirror` to grab a mirror → strip tracking scripts → edit copy |
| React / Vue / Next (content-focused) | Rebuild from a template (e.g. `ai-website-cloner-template`, Node 24+), pour in content |
| SPA / SaaS / data-driven pages | First run `network-capture.mjs` to save API fixtures → stand in a local JSON/mock server |
| Multi-page corporate/product site | First run `route-crawl.mjs` to build a route map → extract a template per page type → replace content uniformly |
| Complex interactive site | First run `interaction-probe.mjs` to record hover/click/scroll/canvas drag states → fill in interactions state by state; don't just capture the first screen |
| **WebGL / Canvas / Three.js heavy frontend** | **Deep reverse-engineer the real source (see below) → faithful reproduction, or find a similar open-source 3D template and swap content**. For single-file native sites, byte-for-byte preservation is often the most faithful reproduction possible. **When no real source can be found, fall back to runtime frame capture + baseline gating**; discipline detailed in `references/effect-extraction.md` (can be delegated to web-shader-extractor) |
| **Static build site (Astro/Vite SSG/Hugo) with heavy WebGL** | **`mirror-site.mjs` to fully mirror the deployed assets → self-host fonts + strip tracking → serve locally from a web root = a byte-for-byte faithful reproduction using the real source**. For static sites, "get the real source" = "mirror the entire deployed asset bundle." Recipe in `references/static-mirror.md`. Example: oryzo.ai (Lusion, L6, Gaussian splatting, hero pixel diff 5/5) |
| Sites built on an off-the-shelf open-source theme (Astro/Hugo themes) | Find the original theme on the corresponding theme marketplace (**only for sites using an off-the-shelf theme as-is**; customized sites should use the full-mirror row above instead — don't use this row for those) |

For L4–L6 complex sites, follow `references/complex-playbooks.md` — don't just use the standard corporate-site flow.

### Step 4 · Set up the project in the clone hub

```bash
cd "$WEB_CLONE_PROJECT"
# git source: clone it in; single file: drop it in. Keep one read-only baseline copy of the original source as index-original.html
# Check the Node version (package.json engines), nvm use the matching version, pin .nvmrc
```

### Step 5 · Strip tracking + write metadata + verify

- **Strip tracking**: Google Analytics (`gtag` / `googletagmanager`), pixels, heatmaps — remove them precisely, line by line (GA blocks are often at the top of `<head>`).
- **Write NOTES.md** (mandatory): must include complexity, reproduction mode, original-vs-clone comparison, fidelity score, known gaps. Template in `references/deliverables.md`.
- **For complex sites, also write TEARDOWN.md** (technical breakdown). All conclusions must cite real source line numbers.
- **Post-clone scoring**: score structure / visuals / interaction / responsiveness / content replacement / functional completeness per `references/assessment.md`. Scores must be backed by screenshots, source code, and actual run results.
- **Real browser verification** (a hard requirement — never claim "it should work" from reading code alone): start a local server → open in a browser → capture console output (no JS/WebGL compile errors allowed) → screenshot and compare against the original. Honestly record any parts that couldn't be verified (e.g. a synthetic PointerEvent with `isTrusted=false` that can't trigger a drag — write that down truthfully, don't fake a "drag succeeded").

After the clone is complete, run recon on the clone site again and generate an automated comparison report:

```bash
node "$WEB_CLONE_SKILL_DIR/scripts/recon-site.mjs" \
  --url http://127.0.0.1:<port>/ \
  --out ./RECON \
  --label clone

node "$WEB_CLONE_SKILL_DIR/scripts/route-crawl.mjs" \
  --url http://127.0.0.1:<port>/ \
  --out ./RECON/routes-clone \
  --label clone \
  --max-pages 25 \
  --max-depth 2

node "$WEB_CLONE_SKILL_DIR/scripts/interaction-probe.mjs" \
  --url http://127.0.0.1:<port>/ \
  --out ./RECON/interactions-clone \
  --label clone

node "$WEB_CLONE_SKILL_DIR/scripts/visual-diff.mjs" \
  --original ./RECON/screenshots/original-1440.png \
  --clone ./RECON/screenshots/clone-1440.png \
  --out ./RECON/visual-diff-1440.json \
  --diff ./RECON/screenshots/visual-diff-1440.png

node "$WEB_CLONE_SKILL_DIR/scripts/compare-recon.mjs" \
  --original ./RECON/original-recon.json \
  --clone ./RECON/clone-recon.json \
  --visual-diff ./RECON/visual-diff-1440.json \
  --original-routes ./RECON/routes/original-route-map.json \
  --clone-routes ./RECON/routes-clone/clone-route-map.json \
  --original-interactions ./RECON/interactions/original-interactions.json \
  --clone-interactions ./RECON/interactions-clone/clone-interactions.json \
  --out ./CLONE_REPORT.md

node "$WEB_CLONE_SKILL_DIR/scripts/audit-clone.mjs" \
  --project . \
  --brand "<original site brand name>" \
  --out ./CLONE_AUDIT.md
```

### Step 6 · Replace with the user's own content

The goal is always "build the user's own site," not to ship an identical copy. Replace three things: text (`index.html`/`data/*.json`/`content/*.md`), media (`public`/`assets`), and brand colors (CSS variables / Tailwind theme). If the structure is non-trivial, write a REPLACE_GUIDE.md.

**For projects that produced a `design-dna.json`** (visual reproduction / content overhaul mode): this step is where it pays off — **keep the DNA, swap the content**. Turn `design_system` into CSS custom properties, make subjective calls per `design_style`, and choose the implementation tier based on `visual_effects.effect_intensity` (lightweight CSS / medium Canvas+GSAP / heavy Three.js); for assets, prefer pulling the original site's real images via `asset-harvest.mjs` rather than having AI redraw approximations. Generation workflow in `references/design-dna.md`.

## Reverse-Engineering a WebGL/Canvas Heavy Frontend (the core craft)

Break an interactive site down into **technical pillars**, and for each one, locate the real implementation + cite line numbers: rendering (WebGL/shader algorithms), compositing (SVG filters / multiple canvases / post-processing), physics, interaction, audio. Only then go verify any secondhand analysis.

**The three-part discipline when reverse-engineering an effect** (to cure "trim as you go, prettify at the end, end up neither accurate nor explainable"):
1. **Evidence grading**: every conclusion must be labeled `SOURCE` (real source code/source map/runtime dump/frame capture), `PARTIAL` (name/fragment only, unproven), or `GUESS` (visual fitting/magic numbers). **Unlabeled = GUESS; must be upgraded to SOURCE before copying it.**
2. **No-compensation**: never mask timing/coordinate/state errors by tweaking brightness/speed/position/noise; fitted values still get labeled GUESS, with a note on what evidence would be needed to upgrade them.
3. **Baseline-first gate**: first use the real draw calls/shaders/uniforms to build a minimal, faithful "RAW REPLAY" reproduction → pass a frame-by-frame comparison → **only then** is engineering-style refactoring allowed.
Details in `references/effect-extraction.md` (including a runtime-capture fallback + when to delegate to web-shader-extractor).

**Transferable advanced patterns** (worth keeping in your back pocket):
- **Displacement-map DOM refraction**: an offscreen WebGL pass computes a "displacement map" where RG = displacement and B = fresnel, then SVG's `<filter><feDisplacementMap scale=N>` uses it to distort the real, live, interactive HTML — what's being refracted is the real DOM, and WebGL never touches DOM pixels at all. This is the soul of the marbles site, and it's something Three.js's `MeshPhysicalMaterial(transmission)` cannot do (it can only make "a glass ball's appearance," not "refract the entire webpage").

For full methodology + a line-by-line breakdown of marbles' real architecture → `references/reverse-engineering.md`, `references/marbles-case.md`.

## License and Attribution (must check before cloning)

```bash
SSL_CERT_FILE=/etc/ssl/cert.pem gh api repos/<u>/<r> | jq '.license'  # + look for a LICENSE file + read the README
```

| License | What you can do |
|---|---|
| MIT / Apache / BSD / Unlicense | May modify and deploy; keep attribution |
| **NONE (no LICENSE file / undeclared)** | **All rights reserved by default**. Local learning/reproduction only, must attribute the original author, **must not be redeployed publicly without permission** — don't treat "publicly visible on GitHub" as free-to-use |
| Proprietary / explicitly prohibited | Read-only learning; do not copy or deploy |

⚠️ Don't equate "it's public on GitHub" or "gh api couldn't find a license right now" with MIT — verify it properly.

## Deliverable Standards
- Each sub-project's root directory: `NOTES.md` (source info/tech stack/license/replacement map/how to run it)
- For complex interactive sites, add: `TEARDOWN.md` (technical breakdown, with line numbers cited)
- When external reporting or skill-effectiveness evaluation is needed, add: `CLONE_REPORT.md` (full comparison of original vs. clone)
- Before going live, add: `CLONE_AUDIT.md` (tracking scripts, leftover original-site branding/language, TODOs, external-link risks)
- `RECON/screenshots/`: original-vs-clone comparison images
- Update the hub's `README.md` index line after each clone

## Built-in Scripts
- `scripts/init-clone.mjs`: Initializes a clone project's skeleton and `NOTES.md`.
- `scripts/recon-site.mjs`: Opens the page with Playwright, collects framework/resource/DOM structure/console error signals, and saves screenshots at three breakpoints.
- `scripts/asset-harvest.mjs`: Downloads the original site's images, scripts, and styles from the recon JSON and generates an asset manifest.
- `scripts/network-capture.mjs`: Captures XHR/fetch requests and saves JSON/text responses, for building local fixtures for SPA/SaaS sites.
- `scripts/mirror-site.mjs`: Real-browser full-scroll capture of every real request → mirrors same-origin assets by path (including JS-runtime-fetched `.sog/.buf/.wasm/.riv` files/fonts), for 1:1 faithful reproduction of static build sites (Astro/Vite SSG/Hugo). See `references/static-mirror.md`.
- `scripts/route-crawl.mjs`: Crawls internal links on the same site, saving screenshots, titles, H1s, and structural signals per route — solves the problem of multi-page sites only getting their homepage cloned.
- `scripts/interaction-probe.mjs`: Automatically performs scroll, hover, safe clicks, and canvas drag, saving before/after interaction states, screenshots, network activity, and console evidence.
- `scripts/sourcemap-hunt.mjs`: Looks for source maps inside JS chunks and saves the source mapping if found.
- `scripts/compare-recon.mjs`: Reads the original and clone site recon JSON, route maps, and interaction evidence, and generates `CLONE_REPORT.md`.
- `scripts/visual-diff.mjs`: Uses a browser canvas to do pixel-level screenshot diffing, outputting a visual score and diff image.
- `scripts/audit-clone.mjs`: Scans for tracking scripts, leftover original-site branding, leftover Japanese text, TODOs, and external URL risks.
- `scripts/dna-scaffold.mjs`: Generates a `design-dna.json` design-identity skeleton from the recon JSON (best-effort prefilled fonts/color candidates/framework effect signals), for use with "visual reproduction / content overhaul" mode. See `references/design-dna.md`.

## Capability Boundaries (default stance)
- **Can do high-fidelity**: static marketing pages, corporate sites, content-focused React/Vue/Next frontends, animated sites where source is directly available.
- **Can visually reproduce but will simplify**: CMS backend data, complex scroll-driven narratives, multi-breakpoint responsiveness, WebGL/Canvas effects, third-party embeds.
- **Not guaranteed to fully clone by default**: login, payments, checkout, search/recommendations, permission systems, server-side business logic, proprietary APIs, copyright-restricted assets. Only a demoable frontend stand-in will be built for these when needed.
- **For content-overhaul mode**: prioritize preserving the original site's information architecture, pacing, motion, and visual grammar, while swapping in the user's own copy, images, brand colors, and business messaging.

## Flagship Case Study
`./website-clones/marbles-clone/` — a native WebGL + SVG Filter + custom-physics glass-marbles site, byte-for-byte faithful reproduction with a complete TEARDOWN — the exemplar for the "WebGL heavy-frontend branch."

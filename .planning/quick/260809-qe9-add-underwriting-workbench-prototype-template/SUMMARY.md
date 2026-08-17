---
quick_id: 260809-qe9
slug: add-underwriting-workbench-prototype-template
date: 2026-08-09
status: complete
commits: [8fee820b]
---

# Summary — `underwriting-workbench` prototype template

**Outcome:** a new od_prototype template ships in the launch-wizard gallery under
**Finance & HR**, converted from the user's reference mock. Purely additive: two new files
in one new folder, zero tracked files modified.

## What the reference actually was

Not static HTML. `~/Downloads/Northstar Underwriting.html` is a **Design-Composer
self-extracting bundle** — 528 KB / 393 lines whose real payload is two long lines:

- a `__bundler/manifest` holding 3 gzip+base64 JS assets (69 KB + 10.7 KB + 131.8 KB) and
  16 woff2 IBM Plex faces;
- a `__bundler/template` holding 139 KB of escaped HTML written in DC template syntax
  (`sc-if` / `sc-for` / `{{ }}` / `sc-camel-on-click`) with **all styling inline**.

It boots **React 18 from unpkg** and preconnects **Google Fonts**. The html-prototype
guardrail bans CDN scripts, external fonts, framework runtimes and inline-only styling, so
it could not be shipped or lightly adapted — it had to be re-authored. The bundle was
decoded in the session scratchpad to recover the design intent (not committed).

## What shipped

`skills/opendesign/design-templates/underwriting-workbench/`

**`example.html`** (100,171 chars) — one self-contained vanilla file:
- 6 routed screens — `accounts`, `account`, `txn`, `submissions`, `tasks`, `reports`
- a 5-step transaction wizard (Identification → Coverage & Forms → Quote Details →
  Document → Send), 4 identification topics, 4 forms sub-tabs, 4 modals, a toast
- inline styles → CSS classes over a `:root` block mapping the six core DS roles
  (`--bg/--fg/--accent/--surface/--border/--muted`) plus derived extended roles
- IBM Plex woff2 → system font stack; React state → a single `store` object
- kept the domain-true mechanics: SPECIMEN watermark → confirm modal → FINALIZED stamp,
  premium roll-up, form-set/optional-form library, template-driven broker email

**`SKILL.md`** — frontmatter (`od.mode: prototype`, `od.scenario: finance`,
`design_system.requires: true`, 4 craft rules, `od.inputs` as **list-of-mappings**) plus a
house-style body: resource map, when-to-use, screen inventory (`data-page` ↔ `data-od-id`),
Workflow Steps 0–5, hard rules, output contract.

## Verification (observed, not assumed)

| Check | Result |
|---|---|
| `static_check` | `ok=True`, `issues=[]` |
| — warnings | 2 orphan-section (account, txn) — genuine drill-downs, non-fatal, documented |
| Headless Chromium click-through | **47/47 checks**, 0 console errors/warnings |
| `list_prototype_templates()` | present; 50 total (was 49) |
| `TemplateListItem` / `TemplateDetail` | both validate — no detail-endpoint 500 |
| Gallery tab | `scenario: finance` → **Finance & HR** |
| Craft rules | all 4 resolve (`form-validation`, `state-coverage`, `accessibility-baseline`, `anti-ai-slop`) |
| `load_prototype_context()` | succeeds (template_body 8,488 · ds_body 3,034 · craft 40,961) |
| example.html injection | 100,171 / 120,000 cap — **not truncated**, 19,829 headroom |
| External network refs | zero `http(s)://`, zero `<link>`, zero `<script src>` |
| Banned Tailwind indigo/violet | none |
| Tracked files modified | **none** |

## Decisions

1. **Generic name over the mock's brand** (user-chosen) — `underwriting-workbench`, matching
   house style where templates are named for the reusable pattern, not the fictional brand.
2. **`scenario: finance`** (user-chosen) → the thinner Finance & HR tab.
3. **Top bar, not the guardrail's 220px sidebar.** A dense register plus a wide wizard needs
   full width, and the reference is a top-nav app. The override is stated explicitly in
   SKILL.md's hard rules so the build agent follows the template, not the generic guardrail.
4. **Single navigation mechanism.** An early draft had both `navigateTo()` and literal
   `location.hash = '#/x'` assignments — two implementations of one behavior. Consolidated on
   `navigateTo()`. Cost: `account`/`txn` now surface as advisory orphan-section warnings
   (the dynamic-nav scanner only matches `#`-prefixed string literals). Accepted — the
   warnings are honest and non-fatal, and `ai-coach-hub` ships with one too.
5. **One behavior fix beyond straight conversion:** `createSubmission()` resets `subFilter`
   to `All`. The reference left the filter set, so a newly-created record could land behind
   an active filter and appear to vanish. Surfaced by the browser drive.

## Not done (deliberate)

- `thumbnail.jpg` — generated at image build, gitignored. Cards fall back to the live
  `example.html` iframe until then.
- `references/*.md` — optional; the example plus the seed carry the reference.

## Correction (post-review) — the seed was NOT optional

The first cut of this task shipped only `SKILL.md` + `example.html` and recorded the seed as
out of scope. **That was wrong**, caught by the user on review. `prototype-build` declares
`tools: [prototype_emit_only]`; in `context_providers/opendesign.py` the `template_body` and
`example.html` blocks are both nested inside `if not is_build_task_2_plus`, and the
injection-part filter is `[p for p in all_parts if "TEMPLATE SEED" in p]`. So from build
task 2 onward the seed is the **only** template material in context — while `engine.py:8470`
still appends, every task, `use ONLY its CSS classes from the TEMPLATE SEED`. The build is a
per-task sub-agent loop, so tasks 2..N were running with zero template guidance.

Fixed in `6249ae00` by adding `assets/template.html` (5,946 chars): `:root` tokens, class
families, router contract, and the verbatim routes map / `navigateTo` / `handleRouteChange`.

Sizing was the hard part — `od_context.py:216` injects `seed[:6000]`, truncating silently
mid-file. Drafts at 10,118 / 7,895 / 6,904 chars each lost the router at the tail. The class
inventory was compressed to families to buy room, since every class is recoverable via
`read_file('prototype.html')` whereas a half-written router is not. `web-prototype`'s
16,364-char seed *is* truncated today — that latent flaw is what this avoids. The 6,000-char
limit is now a hard rule in SKILL.md so a later edit cannot silently re-break it.

Verified: seed 5,946/6,000, injected payload 6,072 chars with every marker present and no
truncation marker; `static_check` on the seed `ok=True`; headless Chromium on the seed routes
all 4 nav targets plus both drill-downs with 0 console errors.
- **Not pushed.** A `dev` push auto-fires a CodeBuild→Docker→EC2 deploy; that needs explicit
  authorization.
- **Backend restart required** before the template appears — `_all_templates()` is
  `@lru_cache(maxsize=1)`, process-lifetime.


## Completeness audit (post-review round 2) — 4 more findings

Prompted by "did you check if everything is covered?". Answer was no: the earlier passes
verified the seams I happened to think of. A systematic sweep (full lifecycle trace +
differential vs all 50 templates) found four more, all fixed in `a6ec6aa7`.

1. **`render_check` had never been run.** The engine runs Both-validation —
   `static_check` *and* `render_check` (Chromium: nav switching, console errors, plus a
   coverage gate that fails on 0 nav targets). Now run: ok=True on both files, 4 navs
   exercised, 0 broken, 0 console errors. (It needs an absolute path; `as_uri()` throws
   on a relative one.)

2. **121 raw hex outside `:root`** in example.html — 2nd highest of 46 examples. Broke the
   template's own hard rule, the injected guardrail, and the DS-reskin promise. Converted:
   104 → `var()`, 17 SVG `stroke=`/`fill=` → `currentColor` + class (`var()` is invalid in
   an SVG presentation attribute). Now 0.

   *Proven* paint-identical. Screenshot hashing was rejected as an oracle after a control
   showed Chromium is non-deterministic on 3 of 7 pages (same file, different hashes).
   Used computed styles across 12 screens instead — 0 colour differences; the only deltas
   were one element's in-flight `opacity` mid-`fadeIn`.

3. **A claim in the template was false.** SKILL.md and the seed said the seed is "the ONLY
   template material in context on task 2+". `factory._compose_injection` has zero
   task-number gating, so the SKILL.md body stays in the *system prompt* every task; only
   context-message copies drop. Replaced with a per-channel table. Also documented that
   `task_loop.py:559-572` seeds the full example.html into the sandbox as `template.html`
   (name collides with the seed) — the best task-2+ class reference.

4. **House-norm gaps.** Added `od.preview` (49/50 declare it; UW was the only one without)
   and `references/checklist.md` (3,506/4,000). The checklist earns its place beyond
   convention: `prototype-validate` runs with `build_task_number == ""` so it receives ALL
   injection parts — a checklist is the one artifact that reaches the *validator* as a
   named block.

### Also measured (not defects in this template)

- `GET /api/prototype/templates/{id}` **500s for `ai-coach-hub` and `process-canvas`** —
  swept all 50; exactly those two, both from list-of-string `od.inputs`. Pre-existing;
  underwriting-workbench returns 200 because it uses mappings.
- `web-prototype`'s 16,364-char seed **is** silently truncated at 6,000 today.
- 10 templates declare `outputs.primary: index.html` and every template carries the
  `<artifact>` block, both of which conflict with the live runtime.

### Final state

files: SKILL.md 13,916 · example.html 103,238 · assets/template.html 5,987 ·
references/checklist.md 3,538.
All injections whole: body 11,625 (uncapped) · example 103,132/120,000 · seed 5,977/6,000 ·
checklist 3,506/4,000. static_check + render_check ok on both HTML files. 47/47 interaction
checks. API list/detail/preview/asset 200, traversal 404. 0 hex outside `:root`, 0 external
refs. Still NOT pushed.

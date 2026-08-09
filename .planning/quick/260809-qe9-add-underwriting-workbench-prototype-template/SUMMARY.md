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
- `assets/template.html` seed and `references/*.md` — optional; the example is the reference.
- **Not pushed.** A `dev` push auto-fires a CodeBuild→Docker→EC2 deploy; that needs explicit
  authorization.
- **Backend restart required** before the template appears — `_all_templates()` is
  `@lru_cache(maxsize=1)`, process-lifetime.

---
name: prototype-template-from-html
description: Convert any reference HTML (a design mock, a Design-Composer/.dc.html bundle, an exported page, a live URL's saved source) into a new od_prototype design template that appears in the launch wizard's template gallery. Use when asked to "add a template", "make a template from this HTML", "turn this mock into a prototype template", or when handed an HTML file and told users should be able to pick it when launching a prototype. Covers the full verified contract — folder layout, frontmatter, the TEMPLATE SEED, static_check/render_check, size caps — plus a one-command verifier.
---

# Prototype template from HTML

Adding a template is a **folder drop**. `od_loader` dir-scans
`skills/opendesign/design-templates/`, and **the folder name IS the `template_id`**.
You must not edit `od_loader.py`, `prototype_templates.py`, `od_context.py`, `registry.py`,
any `workflow.yaml`, or any frontend file. If you find yourself editing one, stop — you have
misread the contract.

Worked example to copy: `skills/opendesign/design-templates/underwriting-workbench/`
(built from a DC bundle, all four files, fully verified).

## The one rule

**"It loads" is not "it works."** A template is consumed at five different moments by four
different agents, each with a different gate. Verifying the gallery card renders proves
almost nothing about build task 2, the validator, or the deliverable. Run the verifier
(below) before you claim done — every check in it exists because something silently broke.

---

## Step 0 — Is the reference actually HTML?

Files exported from Design Composer (`.dc.html`, or any page whose `<title>` is
`Bundled Page`) are **self-extracting bundles**, not static HTML: a
`<script type="__bundler/manifest">` of gzip+base64 assets and woff2 fonts, plus a
`<script type="__bundler/template">` holding the real markup in DC syntax
(`sc-if` / `sc-for` / `{{ }}` / `sc-camel-on-click`, all styling inline), booting React
from unpkg with Google Fonts.

**You cannot ship or lightly adapt one** — the `html-prototype` guardrail bans CDN scripts,
external fonts, framework runtimes and inline-only styling. Decode it to recover the design
intent, then **re-author** as one self-contained vanilla file.

```python
# decode (python3.11, stdlib only)
import re, json, gzip, base64, pathlib
raw = pathlib.Path(SRC).read_text()
# the real markup + component script:
tpl = json.loads(re.search(r'<script type="__bundler/template">(.*?)</script>', raw, re.S).group(1))
# the bundled assets:
man = json.loads(re.search(r'<script type="__bundler/manifest">(.*?)</script>', raw, re.S).group(1))
for k, v in man.items():
    data = base64.b64decode(v["data"])
    if v.get("compressed"): data = gzip.decompress(data)
```

Then translate: `sc-if` screens → `<section data-page>` + hash router · `sc-for` → JS render
loops · inline styles → CSS classes over a `:root` token block · web fonts → system stack ·
React state → a single `store` object.

A plain static HTML reference needs the same treatment minus the decode.

---

## The four files

```
<template-id>/
├── SKILL.md              REQUIRED. No SKILL.md ⇒ the folder is SILENTLY dropped.
├── example.html          the full working reference (also the gallery preview)
├── assets/template.html  the TEMPLATE SEED — REQUIRED in practice, see below
└── references/*.md       optional; reaches the builder AND the validator
```

**When each reaches which agent** — this is the part that gets missed:

| | specify / plan | build task 1 | build task 2+ | validate | fix-loop |
|---|---|---|---|---|---|
| SKILL.md body (system prompt) | yes | yes | **yes** | yes | yes |
| SKILL.md body (context message) | yes | yes | no | yes | no |
| `example.html` | **never** | yes | **no** | yes | no |
| seed `assets/template.html` | **never** | yes | **yes** | yes | no |
| `references/*.md` | **never** | yes | no | **yes** | no |

- Planners are deliberately barred from `example.html` (`context_providers/opendesign.py`
  gate on `is_builder`) — "must NOT see a full working HTML doc".
- On build task 2+ the seed is the only template material in the **context message**
  (`emitted_parts = [p for p in all_parts if "TEMPLATE SEED" in p]`). The SKILL.md body is
  still in the *system prompt* — `factory._compose_injection` has **zero** task-number
  gating — but it is prose, not CSS.
- The engine appends on **every** build task: `use ONLY its CSS classes from the TEMPLATE
  SEED`. **Ship without a seed and that instruction points at nothing.**
- `prototype-validate` runs with `build_task_number == ""`, so it receives *all* injection
  parts — a `references/checklist.md` is the only artifact that reaches the validator as a
  named block.

Also on the sandbox from task 1: `read_file('prototype.html')` (what you wrote) and
`read_file('template.html')` — the engine writes the **full `example.html`** there
(`task_loop.py` `_write_reference_files`). Note the name collision with `assets/template.html`.

---

## Size cliffs — all silent truncation

| File | Cap | Failure if exceeded |
|---|---|---|
| `example.html` | **120,000** chars | cut, `...[truncated]` appended |
| `assets/template.html` | **6,000** chars | cut **mid-file** — put the router at the front or stay under |
| `references/*.md` | **4,000** chars each | cut per file |
| SKILL.md body | uncapped | — |

The seed cap is the dangerous one: `seed[:6000]`. Drafts that overshoot lose the tail, which
is where the router lives. When space is tight, **`:root` tokens + the verbatim routes map /
`navigateTo` / `handleRouteChange` beat an exhaustive class list** — every class is
recoverable via `read_file('prototype.html')`; a half-written router is not.
(`web-prototype`'s 16,364-char seed *is* truncated today. Don't copy that.)

---

## SKILL.md frontmatter

```yaml
---
name: Human Readable Name
description: |
  What it is and when to reach for it. Shown on the gallery card.
triggers: ["keyword", "another"]
od:
  mode: prototype          # EXACT string, or it lands in no gallery
  platform: desktop        # or mobile
  scenario: finance        # drives the tab — see table
  preview: {type: html, entry: prototype.html}
  design_system: {requires: true, sections: [color, typography, layout, components]}
  craft: {requires: [form-validation, state-coverage]}
  outputs: {primary: prototype.html}
  example_prompt: "One concrete brief a user could paste."
  inputs:                  # LIST OF MAPPINGS — see trap
    - name: domain
      description: "..."
---
```

**Traps:**
- **`od.inputs` must be a list of mappings.** List-of-strings passes the loader but **500s**
  `GET /api/prototype/templates/{id}` (`ai-coach-hub` and `process-canvas` are broken this
  way today). Omit it or use mappings.
- **`od.scenario` drives the tab.** Unmapped ⇒ visible only under "All":
  `design|personal|creator|education`→Design · `marketing|sale|sales`→Marketing ·
  `operations|operation|live|live-artifacts`→Operations ·
  `engineering|healthcare|video`→Engineering · `product|orbit`→Product ·
  `finance|hr`→Finance & HR.
- **Only name craft rules that exist** in `skills/opendesign/craft/` — unknown names are
  silently dropped. Check the dir; don't guess.
- **`outputs.primary` is `prototype.html`**, not `index.html` — see below.

## SKILL.md body

House shape: Resource map → When to use → Screen inventory (`data-page` ↔ `data-od-id`) →
Workflow Step 0–5 → Hard rules → Output contract. The body is injected into the build
agent's system prompt, so **everything in it is a live instruction.**

**The deliverable is `prototype.html`.** `workflow.yaml` declares
`deliverable.name: prototype.html` and `prototype-build/AGENT.md` repeats it five times
("You MUST always write prototype.html to disk"). Ten shipped templates say `index.html` in
their body — if the model obeys that, `prototype.html` never exists, validation is silently
skipped, and the deliverable degrades to the agent's prose. **Say `prototype.html`.**

**Do not end with the `<artifact identifier=…>` block.** Most templates carry it; it is the
single-shot/daemon shape. This pipeline writes files with `write_file`/`edit_file` and never
streams.

---

## The HTML contract (both `example.html` and the seed)

Enforced by `backend/app/agents/static_check.py` — read it if anything surprises you.

- `data-page` on **`<section>` only**. It registers a section on *any* element, so putting
  it on an `<a>` invents a phantom page.
- Nav anchors carry **all three**: `class="nav-item"` (what the validator collects),
  `data-page-link="<id>"` (the guardrail), `href="#/<id>"`.
- **Section ids and `routes` keys are 1:1** — every section needs an entry and vice-versa.
- **Exactly one** `<section … class="page is-active">`.
- Every inline `onclick="fn(...)"` must call a function defined in a `<script>`.
- Dynamic-nav discovery matches **`#`-prefixed string literals only**
  (`navigateTo('#/x')`, `location.hash='#/x'`). `navigateTo('x')` is invisible to it, so
  drill-down sections show as *orphan section* **warnings** — advisory, `ok = not issues`.
  Don't add fake nav links to silence them.
- Self-contained: no `http(s)://`, no `<link>`, no `<script src>`, no CDN, no web fonts.
  One `<style>` in `<head>`, one `<script>` at the end of `<body>`, state in a single
  `store`, `data-od-id` on every top-level region, no emoji as icons.
- **No raw hex outside `:root`.** The guardrail demands it and it is what makes a design
  system actually reskin the page. **`var()` is invalid inside SVG `stroke=`/`fill=`
  attributes** — use `stroke="currentColor"` plus a colour class there.

---

## Verify — run this, don't reason about it

```bash
python3.11 .claude/skills/prototype-template-from-html/verify.py <template-id>
```

It checks loader pickup, gallery tab, both API response models, craft resolution, every size
cap and truncation, `static_check` **and** `render_check` on both HTML files, task-2+ seed
survival, hex outside `:root`, external refs, and the `index.html` deliverable trap.

Then drive it for real — click every screen, wizard step and modal in headless Chromium with
a console-error sink, and hit the endpoints with `TestClient` plus a `get_current_user`
dependency override.

**Two harness gotchas that will waste your time:**
- `render_check` needs an **absolute** path (`as_uri()` throws on a relative one), and it has
  a coverage gate that fails when 0 nav targets are exercised.
- **Screenshot hashing is not a valid visual oracle.** Headless Chromium is non-deterministic
  on text antialiasing — re-rendering the *same file* changes hashes on some pages. For a
  refactor that must be visually lossless, diff **computed styles** per node
  (fill/stroke/background/border colours/box-shadow) instead.

**After any change: restart the backend.** `_all_templates()` is `@lru_cache(maxsize=1)`,
process-lifetime — a new folder is invisible until then.

## Seeing it in the gallery

`thumbnail.jpg` is gitignored and generated at image build; locally the card falls back to a
live `example.html` iframe, which is expected.

```bash
# backend (check the port is free first — other projects may hold 8000/8001)
cd backend && RUNS_ROOT=/tmp/flowin-runs ENV=development \
  python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8010
# frontend
cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8010 npx next dev -p 3000
```

Log in `qa-enterprise@flowinqa.com` / `flowin-e2e-pass` (SQLite `backend/dev.db`), then
**Build an interactive prototype → Template → <your tab>**. Browsing the gallery needs no
AWS/Bedrock; only an actual run does.

## Known pre-existing bugs — do not copy, do not "fix" as a side effect

Running the verifier against these is the fastest way to see what each failure looks like.

- `ai-coach-hub`, `process-canvas`: detail endpoint 500s (list-of-string `od.inputs`).
- `ai-coach-hub`: `od.scenario: saas-product` is unmapped ⇒ the card is invisible in every
  tab except "All".
- `web-prototype`: 16,364-char seed, silently truncated at 6,000.
- 10 templates declare `outputs.primary: index.html`; nearly all carry the `<artifact>`
  block. Both conflict with the live runtime.
- Most shipped `example.html` files carry raw hex outside `:root`, so their design-system
  reskin is partly cosmetic.

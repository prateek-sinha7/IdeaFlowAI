---
name: Underwriting Workbench
description: |
  An enterprise back-office workbench for regulated, document-producing work:
  a top-bar shell over an account register, an account/case detail with a
  transaction ledger, a five-step transaction wizard (identification →
  coverage & forms → pricing details → document preview → save & send), a
  filtered work queue, a task list, and a reports view. Use when the brief
  asks for an underwriting, policy-administration, claims, loan-origination,
  or any case-management back office where a record is worked through stages
  and ends in a generated document sent to a counterparty.
triggers:
  - "underwriting"
  - "insurance"
  - "policy administration"
  - "back office"
  - "case management"
  - "quote"
  - "binder"
  - "submission"
  - "loan origination"
  - "claims"
  - "workbench"
  - "multi-step wizard"
od:
  mode: prototype
  platform: desktop
  scenario: finance
  design_system:
    requires: true
    sections: [color, typography, layout, components]
  craft:
    requires:
      - form-validation
      - state-coverage
      - accessibility-baseline
      - anti-ai-slop
  outputs:
    primary: index.html
  example_prompt: "Build an underwriting workbench for a specialty marine cargo insurer — an account register, an account detail with a transaction ledger, a five-step quote wizard ending in a quote letter with a specimen watermark, plus a submissions queue, tasks, and a reports view."
  inputs:
    - name: domain
      description: "The record being worked and its lifecycle stages (e.g. submission → quote → binder → bound)"
    - name: register_columns
      description: "The columns of the main register and what each status chip means"
    - name: wizard_steps
      description: "The steps of the transaction wizard and which fields belong to each"
    - name: document
      description: "The document produced at the end — its letterhead, line items, and draft-vs-final states"
    - name: queues
      description: "The secondary views: work queue filters, task types, and the report KPIs"
---

# Underwriting Workbench Skill

Produce a single, self-contained HTML prototype of an **enterprise back-office workbench** —
a sticky top-bar shell over six routed screens, with a five-step transaction wizard that ends
in a previewable, finalizable document. Compose it from the bundled `example.html` reference —
**not** by writing CSS from scratch. The reference already encodes the visual system (deep-navy
chrome, white rounded cards on a cool-grey canvas, dense uppercase table headers, pill status
chips, monospace identifiers) and one inline vanilla-JS controller. Your job is to re-skin the
copy and re-shape the domain data.

## Resource map

```
underwriting-workbench/
├── SKILL.md              ← you're reading this        (build task 1 only)
├── example.html          ← the full, rendered, self-contained reference workbench
│                            (READ FIRST — builders, build task 1 only)
└── assets/
    └── template.html     ← the seed skeleton: tokens, class families, router
                             (injected on EVERY build task — the only template
                              material you still have on task 2+)
```

**What you see when.** The per-task build loop injects the SKILL.md body and
`example.html` on **task 1 only**. From **task 2 onward the seed is the only template
material in context**, which is why the engine's per-task compliance line says *"use ONLY
its CSS classes from the TEMPLATE SEED"*. The seed therefore carries the `:root` tokens,
the class families, and the verbatim router. For anything else on a later task, call
`read_file('prototype.html')` — the file you already wrote holds the full CSS.

## When to use this skill

Use this when the brief describes **a record worked through stages by a professional, ending in
a document sent to a counterparty**:

- insurance underwriting (submission → quote → binder → bound)
- policy administration, endorsements, renewals
- claims adjudication, loan origination / credit underwriting
- any regulated back office with a form/document library and an approval step

Reach for a different template when: the brief is a generic analytics view (`dashboard`), a
process/swimlane map (`process-canvas`), a marketing or landing page (`web-prototype`,
`saas-landing`), or a single financial statement (`invoice`, `finance-report`).

## Screen inventory

Six routed screens. `data-page` ids and `routes` keys must stay in one-to-one correspondence —
the static validator fails the build otherwise.

| Screen | `data-page` id | `data-od-id` | Reached by | Purpose |
|---|---|---|---|---|
| Account register | `accounts` | `accounts` | top nav (`#/accounts`) | searchable master list; the landing page (`is-active`) |
| Account detail | `account` | `account-detail` | folder button in the register | header facts + transaction ledger, clone actions |
| Transaction wizard | `txn` | `transaction` | Open / Clone on a transaction | the 5-step flow (in-page state, **not** routes) |
| Work queue | `submissions` | `submissions` | top nav (`#/submissions`) | filterable queue across all records |
| Tasks | `tasks` | `tasks` | top nav (`#/tasks`) | checkable task list with priority + due |
| Reports | `reports` | `reports` | top nav (`#/reports`) | 4 KPI tiles, a bar breakdown, a stat panel |

`account` and `txn` are drill-downs with no nav link — `static_check` emits an advisory
*orphan section* warning for each. That is expected and non-fatal; do **not** "fix" it by
adding fake nav links.

The wizard's five steps, the four identification topics, the four forms sub-tabs, and the four
modals are **in-page state on the `store` object**, never routes. Only add a `data-page` section
when a screen deserves its own URL.

## Workflow

### Step 0 — Pre-flight (do this once, before writing anything)

1. **Read `example.html` end-to-end** — at minimum the `<style>` block and the whole `<script>`.
   Note the single `store` object (reference arrays `ACCOUNTS` / `STATES` / `FORMSETS` /
   `OPTIONAL` / `SEARCHPOOL` / `TEMPLATES` / `KPIS` / `BARS`, then the mutable UI state), the
   `routes` map + `navigateTo` / `handleRouteChange` router, and the `render*()` functions that
   repaint from state. You will change the **data and copy**, not the mechanism.
2. **Read the active DESIGN.md** (already injected into your system prompt). Map its palette
   onto the six core roles in `:root` — `--bg`, `--fg`, `--accent`, `--surface`, `--border`,
   `--muted` — and let the extended roles (`--navy`, `--teal`, `--green`, `--amber`, `--danger`,
   `--plum`) derive from it. Do not introduce new token families and do not hardcode hex
   outside `:root`.

### Step 1 — Copy the reference

Copy `example.html` to the project root as `index.html` — it is the full workbench, so start
from it, not from the seed. (`assets/template.html` is the same skeleton reduced to tokens +
class families + router; it exists so those survive into later build tasks. If you ever find
yourself on task 2+ without the example, the seed is the authoritative contract.)

Replace the org name in the top bar and the letterhead, the `<title>`, and the environment
pill. Keep the shell (top bar + routed sections + modals + toast) intact.

### Step 2 — Reshape the domain data

Edit the `store` reference arrays, not the render functions:

- **`ACCOUNTS`** — the master records. Every row needs `id`, `name`, `loc`, `st`, `policyNo`,
  `subNo`, `product`, `coverage`, `formSet`, `effIso` / `expIso` (+ their `*Short` forms),
  `created`, `status`, `kind`, `broker` / `brokerShort` / `brokerEmail` / `contactName`,
  `underwriter`, and the money fields (`premium`, `triaPct`, `triaPremium`, `premiumWithTria`).
  Keep 5–7. Rename the money fields to your domain if it isn't insurance, and update `STATUS`.
- **`STATUS`** — the lifecycle chips. Keep 3–5 states; each maps to a `chip-*` class.
- **`FORMSETS` / `OPTIONAL` / `SEARCHPOOL`** — the document library: the mutually-exclusive form
  sets, the checkable optional forms, and the searchable append pool.
- **`TEMPLATES` + `emailContent()`** — the outbound message templates. Each returns a real
  `{subject, body}` built from record fields; keep them switchable.
- **`KPIS` / `BARS` / `tasks`** — the reports and task copy.

### Step 3 — Rewrite the copy

Replace every label, helper line, and banner with real, specific domain copy. **No filler** —
no "Metric A", no lorem. Field-level help should say *why* a field matters (the reference's
"the mailing address determines the domicile state, which drives the state forms" is the bar).
Keep the pre-filled / read-only distinction honest: fields the system supplies stay `readonly`
with a `PRE-FILLED` tag; fields the user owns stay editable.

### Step 4 — Self-check

- All six screens route from the top nav and from the drill-down buttons; reload on a deep
  link (`#/reports`) restores that screen.
- All five wizard steps switch from the numbered tabs; completed steps show a check.
- All four identification topics and all four forms sub-tabs switch.
- Add/remove a location; append a form via Form Search; toggle optional forms.
- Document step shows the **SPECIMEN** watermark until finalized, then the **FINALIZED** stamp;
  Save-PDF stays disabled until then.
- Every modal opens, closes on backdrop click, on Cancel, and on Escape.
- Zero console errors; no external network requests.

### Step 5 — Emit the artifact

Write the single `index.html`. One sentence before it describing what's there.

## Hard rules

- **Single self-contained `index.html`** — one inline `<style>` in `<head>`, one inline
  vanilla-JS `<script>` at the end of `<body>`. No CDN, no external fonts, no framework runtime,
  no build step.
- **System font stack** — `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` for text,
  `ui-monospace, "SF Mono", Menlo, Consolas, monospace` for identifiers (policy/submission
  numbers, form codes, ZIPs). Identifiers in mono is load-bearing to the look; keep it.
- **This shell is a top bar, not a sidebar.** The generic HTML-prototype guardrail describes a
  220px sidebar; this template deliberately overrides that — a dense register plus a wide wizard
  needs the full width. Keep the 54px sticky top bar.
- **`data-page` goes on `<section>` only** — never on an `<a>`. Nav anchors carry
  `class="nav-item"` + `data-page-link="<id>"` + `href="#/<id>"`. Every section id must have a
  `routes` entry and vice-versa, and exactly one section starts with `class="page is-active"`.
- **`data-od-id` on every top-level region** (see the screen inventory) so comment mode can
  target it.
- **State lives in the single `store` object**; every `onclick` calls a function defined in the
  script block. No globals outside `store`.
- **Density is the point.** 12.5–14px body text in tables, 10.5px uppercase table headers,
  status as pill chips — not a spacious marketing layout. Resist the urge to make it airier.
- **No emoji as icons.** Inline SVG, or a single letter in a rounded tile (`S`/`D`/`Q`/`B`).
- **Keep the draft→final document mechanic.** The specimen watermark, the confirm-before-
  finalize modal, and the "changes after finalizing won't update this document" warning are the
  most domain-true part of the reference. Rename them, don't remove them.
- **Every number must be plausible and internally consistent** — the premium breakdown must add
  up, and the document must show the same figures as the summary panel.
- **Keep `assets/template.html` under 6,000 characters.** The seed is injected as
  `seed[:6000]`, so a byte past that is silently dropped mid-file — and the router lives at
  the end. If you extend the seed, trim elsewhere first and re-check the length.

## Output contract

```
<artifact identifier="kebab-case-slug" type="text/html" title="Human Title">
<!doctype html>
<html>...</html>
</artifact>
```

One sentence before the artifact. Nothing after.

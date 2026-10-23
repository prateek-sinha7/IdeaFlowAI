---
name: import-design
description: Use when the user wants to import, extract or add a design system for VelocityAI from a Claude Design design-system export (tokens/, readme.md, _ds_manifest.json), the _ds/ folder inside a Claude prototype export, a pasted or attached design spec (markdown), or any live website URL. Asks for the name and picker category, produces the full set (DESIGN.md with the nine sections, tokens.css with every schema token, components.html), places it in skills/opendesign/design-systems/<id>/, and proves it with the schema, the real loader and real Chrome.
argument-hint: <export folder | _ds folder | spec.md | https://site> [name="..."] [category="..."]
---

# import-design

Builds a full VelocityAI design system from whatever the user has: the same shape
as the 18 full systems, with `iberia` as the reference.

## Conventions

- **Paths.**
  - `SKILL_DIR` is the folder holding this file (`skills/velocity/import-design`, `.claude/skills/import-design` or `.kiro/skills/import-design`).
  - `REPO` is the git root.
  - `OD` is `REPO/skills/opendesign`. A test may point `OD` at a scratch copy; every script derives paths from the folder you pass it, including the `_schema` it reads.
  - `W` is your scratch work dir (for example `<scratchpad>/ds-<id>/`). Nothing in `W` goes into the repo, and no `W` path may appear in a shipped file.
- **Running scripts.**
  - Python scripts are stdlib-only except the validator: `python3 -B` for them, `REPO/backend/.venv/bin/python -B` for `validate_design_system.py`.
  - Node scripts launch real Google Chrome (`channel: 'chrome'`).
  - No `timeout` wrapper (macOS has none). Check exit codes without a pipe.
- **Reference.** Read `SKILL_DIR/reference/design-md.md` before step 4. It has the DESIGN.md skeleton and the source-to-token mapping tables. The model system is `REPO/skills/opendesign/design-systems/iberia/`. Use the repo copy even when `OD` is a scratch root.
- **Schema.** `OD/design-systems/_schema/` is part of `OD`. With a scratch `OD`, edit its copy of `tokens.schema.ts`. With the real `OD`, the BRAND_EXTENSIONS edit is part of the import and is listed in the report.

## What a finished design system is

```
OD/design-systems/<id>/
├─ DESIGN.md        # Design System Inspired by <Name> / > Category: X / > blurb / 9 sections
├─ tokens.css       :root with ALL 56 schema tokens (+ allowlisted brand extensions, + theme blocks)
└─ components.html  reference page: the same :root and themes verbatim, fonts <link>, var(--*) only
```

What the app reads:
- **Loader.** The H1 is the picker label, shown exactly as written. `> Category:` is the picker tab, and the next `>` line is the description (`od_loader.py:405-436`).
- **Every run.** The whole DESIGN.md body goes into every run. `tokens.css` and `components.html` are seeded next to it.
- **prototype_v2.** It treats `tokens.css` as the exact colour source (`workflows/prototype_v2/workflow.yaml:817-845`).
- **Picker swatches.** These are the hex codes in DESIGN.md (`design-system-colors.ts`).
- **Token contract.** `OD/design-systems/_schema/tokens.schema.ts`, which the scripts read directly.

## Step 1: read the source

| Input | Command |
|---|---|
| Claude Design design-system export, a prototype export with `_ds/`, a `.zip`, a `.md` spec, a `.css` file | `python3 -B SKILL_DIR/scripts/read_source.py "<input>" --out W` |
| a website URL (or a local `.html`) | `node SKILL_DIR/scripts/extract_site.cjs <url> --out W [--pages <url2>,<url3>]` |

**Read policy (exports).** Always read in full:
- `uploads/*.md` (the spec)
- `readme.md`, `SKILL.md`
- every `ui_kits/*/README.md`

For `components/**/*.prompt.md`, grep the headings, then read the ones for the
components you will show as signature components. List what you read in the report.

Read what the extractor produced:
- **`W/source.json`**:
  - `docs`: read every one in full. The export's `readme.md`, `SKILL.md` and `uploads/*.md` spec carry the rules, provenance and voice.
  - `variables`: `:root` and every theme selector, including fenced CSS blocks inside a markdown spec.
  - `type_roles`: the source's own heading and body rules: selector, font shorthand, size, weight, line height, letter spacing.
  - `manifest_tokens`, `fonts`, `themes`, `components`, `breakpoints`, `hex_context` (where each hex is used), `suggested_name`.
- **`W/site.json`**: page 0 sits at the top level; all pages are in `pages[]`, with each page's URL at `pages[i].meta.url`. Compare `samples.h1` and the CTA across pages and record any variants. Never write an absolute rule that one page contradicts. CTAs that are `<a>` elements with a filled background are in `samples.buttons_filled`. Read:
  - `colors`, `accents`, `type`, `samples` (h1-h4, body, buttons, inputs, cards, nav, badges, tables), `shape`, `root_vars`, `fonts`, `breakpoints`, `copy`
  - `auto_pages`: the extra same-origin pages it visited

**Look at the source.** Always, before mapping:
- **Site:** `W/shots/desktop-N-full.png`, `tablet-N.png`, `phone-N.png`.
- **Export:** screenshot its own pages with
  `node SKILL_DIR/scripts/shot.cjs W/src-shots "<export>/Reference Sheet.html" "<export>/thumbnail.html" <one ui_kits/*/index.html>`,
  then read the PNGs. Errors inside the export's own React kits can be ignored.

**Coverage list.** Write `W/coverage.md` as a table: one row per H2/H3 and per
table of the source docs (or per visible section of the site, and per `samples`
key per page). The columns are:
- **source item**
- **evidence**: a file path, a `site.json` key or a screenshot name
- **DESIGN.md section**, or "Known gaps"
- **anchor phrase**: words you will write, so the placement can be grepped

Step 4 must place every row, including sample copy, icon names, hover rules and
the product, density and theme tables. A row may say "absent" only if its
evidence shows it is absent (an empty `samples.table` on every page). The report
gives the counts.

Also list the declarations of every colour theme (`theme_overrides`). Each one
becomes a theme-block value, or a Known gaps entry.

For a site, never copy logos, imagery or font files, and never claim the system
is official. The H1 says "Inspired by". Ignore cookie banners and overlays when
you judge colours.

## Step 2: ask, in ONE question round

Use AskUserQuestion unless the user already gave `name=` / `category=`. If
AskUserQuestion is unavailable, or the task supplies the answers, write the
question round into the report and use them. A missing name or category has no
default: stop and ask.

1. **Name**: the brand or system name, as in "Design System Inspired by **<Name>**".
   Offer `suggested_name`, the export's title, or the site's brand.
   The folder id is its kebab case (`Iberia Operations` → `iberia-operations`).
2. **Category**: the picker tab (`DesignSystemPicker.tsx:51-55`, one tab per
   distinct string). Generate the current list from the REAL catalog, since the
   picker is app-wide, even when `OD` is a scratch root:
   `grep -h '^> Category:' REPO/skills/opendesign/design-systems/*/DESIGN.md | sort | uniq -c | sort -rn`.
   Offer the 3-4 best fits, best first with "(Recommended)". A typed new string
   becomes a new tab, so say so. When `category=` was given, still run the grep
   and state "new tab: yes/no" now.

The id defaults to the kebab-case Name. Another id is used only when the check
below finds a collision, or the user gave `id=`.

**Id check, before anything is written** (each command prints a hit or nothing):
- `ls -d OD/design-systems/<id>`
- `grep -n '^  <id>:\|"<id>":' OD/design-systems/_schema/tokens.schema.ts`, since the BRAND_EXTENSIONS key must be free too
- `grep -il '^# Design System Inspired by .*<Name>' OD/design-systems/*/DESIGN.md REPO/skills/opendesign/design-systems/*/DESIGN.md`. An exact H1 match blocks. A partial match (an existing "Iberia" when importing "Iberia Spec") is shown to the user as a near-duplicate.

If any exists, show it and ask: another id or name, or replace. Replace only on
an explicit yes.

## Step 3: map the tokens

Write `W/mapping.json` (shape in the `make_ds.py` docstring). Every schema token
is decided by these rules:

| Layer | Tokens | Rule |
|---|---|---|
| A1-identity (8) | `--bg --surface --fg --muted --border --accent --font-display --font-body` | **Concrete source values**, never aliases |
| A1-structure (18) | `--text-xs`…`--text-4xl`, `--leading-*`, `--tracking-display`, `--section-y-*`, `--container-*` | See the type and layout rules below |
| A2 (26) | accent states, `--success --warn --danger`, `--font-mono`, `--space-*`, `--radius-*`, `--elev-*`, `--focus-ring`, `--motion-*`, `--ease-standard` | Source value when it has one. Omit it to get the schema default; the script reports which defaults it used |
| B-slot (4) | `--surface-warm --fg-2 --meta --border-soft` | The source's tier, or omit it (the script writes the alias) |

**Scale rules:**

- **Spacing.** `--space-N` means **N×4 px**: 1=4, 2=8, 3=12, 4=16, 5=20, 6=24, 8=32, 12=48. Map the source scale **by px value, never by position**. A source step with no tier (64px) is not a token; record it in DESIGN.md §5. The validator warns on a mismatch.
- **Type.** The 8 slots are positional: `--text-xs`, `--text-sm`, `--text-base` (the body size), then `--text-lg`, `--text-xl`, `--text-2xl`, `--text-3xl`, `--text-4xl` (the display size). Fill them in this order:
  1. `--text-base` = the source's body size, and `--text-4xl` = its largest display size.
  2. Below body, xs and sm take the two most-used smaller sizes. A third smaller size (for example 12 / 13 / 14) gets no slot.
  3. Above body, lg…3xl take the four sizes between body and display, keeping the most-used. A size beyond four gets no slot.
  4. Fewer sizes than slots: interpolate between neighbours and mark the token note `authored`. Never add a §3 role row for an interpolated slot.
  5. Every source size without a slot appears in the §3 table with token "none" and its use count. Never write a token whose px differs from the source size it claims.
  - The §3 hierarchy table is copied from `type_roles` / `samples`: weights, sizes, line heights, tracking. Mark any other cell `(authored)`. A value is authored only if it is absent from every extracted file, so check `variables` and `hex_context` first.
- **Radius.** Keep sm, md and lg non-decreasing. A pill-button brand sets `"button_radius": "--radius-pill"`.

**Colour rules:**

- **Map by meaning, never by name.** The export's own `--focus-ring` may be a colour, while the schema's is a box-shadow. Its `--border-soft` may mean something else.
- **Brand red vs danger.** If the brand colour is red, `--danger` is still a distinct critical colour, as in iberia.
- **Composite tokens.** Compose `--focus-ring`, `--elev-ring` and `--elev-raised` from `var(--accent)`, `var(--border)`, `var(--fg)` and `var(--surface)`, never hex, so themes re-resolve them.
- **Fonts.**
  - Put the open font that renders first in the stack, then the proprietary face, then generic fallbacks. Iberia uses `Montserrat, iberiaheadline, Verdana, sans-serif`.
  - `fonts_href` is the Google Fonts css2 URL for exactly those families and weights.
  - A proprietary-only stack fails `preview_ds.cjs`, so substitute the closest open font.

**Fixed brand colours.** A source token that must never re-theme (a brand bar red
the source marks "never remaps", or a logo colour) becomes an extension such as
`--brand-fixed`. Give it a matching fixed on-colour too (`--brand-fixed-on`, the
text and icons on it). Theme blocks override neither, and signature components
use both for the brand chrome.

**Themes.** Use `themes` for real colour themes (dark, ops-dark):
- Each theme block overrides **every** surface, foreground, border, semantic and accent-state token: `--bg --surface --surface-warm --fg --fg-2 --muted --meta --border --border-soft --accent --accent-on --accent-hover --accent-active --success --warn --danger`.
- Author and mark any value the source omits.
- Also override every token the source itself re-declares in its dark block, including elevation (`--elev-raised` and `--elev-ring` may use rgba literals inside a theme block).
- Override every extension that is a tint or a semantic colour (`--success-bg`, `--danger-bg`, `--info`, …) too. The validator checks these.
- Density (compact vs comfortable) is **prose only** in §5: no tokens, no theme block.

**Extensions** are only for brand-only roles a schema token cannot hold (a second
brand colour, an info colour, a gradient). In order:
1. Put them in `mapping.extensions` with a `notes` entry each.
2. Run `python3 -B SKILL_DIR/scripts/make_ds.py W/mapping.json --dest OD/design-systems/<id> --print-extensions`. It prints the snippet only and writes no files.
3. Paste the snippet into `BRAND_EXTENSIONS` in `OD/design-systems/_schema/tokens.schema.ts` (the `iberia:` entry is the model).
4. Then generate (step 5).

Report the snippet.

**§2 coverage.** Every hex that DESIGN.md §2 gives a role must be one of the
following. The hex is checked verbatim in the Known gaps text.
- a schema token
- an extension
- listed under "Known gaps" in §9 as described but not tokenised (tints, tier colours). Write it as:
  `- **Colours described but not tokenised**: \`#e8f5e9\` (success tint), \`#fdecec\` (danger tint)`

`provenance` and `notes` are written into `tokens.css`, so keep them free of
scratch or absolute paths.

## Step 4: write W/DESIGN.md

Follow `reference/design-md.md` exactly: the H1, `> Category:`, the blurb, then
the nine sections with their exact headings.

The content must be:
- **Concrete**: hex with roles, font names, px sizes and weights.
- **Sourced**: from the docs and the extracted values. Any value not found in the source is suffixed `(authored)`.
- **Complete**: every item of the step-1 coverage list is in a section or under Known gaps (§9). That includes accessibility rules, iconography, voice and sample copy.
- **Sized**: about 8-30 KB. Put detail into tables, not prose.
- **Swatch-ready**: at least 5 hex values sit in §2 with their roles.

## Step 5: generate, place, validate, preview

```bash
python3 -B SKILL_DIR/scripts/make_ds.py W/mapping.json --dest OD/design-systems/<id>      # exit 4 = extension not allowlisted yet
cp W/DESIGN.md OD/design-systems/<id>/DESIGN.md
REPO/backend/.venv/bin/python -B SKILL_DIR/scripts/validate_design_system.py OD/design-systems/<id> --source W/source.json   # or W/site.json
# --source adds: source colours missing from DESIGN.md, --text-* sizes the source never uses
# (unless the token note says authored), dark blocks that re-declare shadows without --elev-* overrides
node SKILL_DIR/scripts/preview_ds.cjs OD/design-systems/<id> --out W/preview
```

- `make_ds.py` writes:
  - `tokens.css`, with the source of each token printed: mapping, schema default, alias or extension. Put that split in the report.
  - `components.html`, with the palette, type scale, buttons, form, surfaces, alerts, table, spacing and radius, all through `var(--*)`, plus the same `:root` and theme blocks.
- **Signature components are required** for an export or spec, and expected for a site. Put them in `mapping.signature_html` and re-run `make_ds.py`, using `var()` only.
  - Show one piece per §4 H3, or per row of the source's component list. Any you skip get a written reason each in the report. Time or cost is not a valid reason. Examples: brand bar, status chips, the main domain component (flight row, KPI tile, tier badge, data table, stepper), the CTA, the disabled and error states.
  - Every piece wraps at 390px (`flex-wrap`, a `gap`). The phone shot must show no overlapping text.
  - Each piece reproduces the §4 values: radius, fill, border, text colour, case, dot or icon.
  - Each is traceable to a source screenshot. Do not add controls or brand names the source lacks, and never use a radius that §7 forbids.
- `validate_design_system.py` must print `RESULT: PASS`. It checks:
  - the schema and `:root` parity
  - the px tiers and scale order
  - composite hex, theme completeness and theme parity
  - §2 colour coverage
  - scratch paths and duplicate names
  - the real `od_loader` listing

  Fix every `[E]`. Fix or justify every `[W]`. The "no other system uses category" `[W]` is expected when the user chose a new tab: say so.
- `preview_ds.cjs` must exit 0:
  - no page errors, and all three font families load
  - colours resolve and there is no horizontal scroll at 390px
  - every theme re-themes the page
- **Compare.** Read `W/preview/desktop.png`, `phone.png` and `theme-*.png` next to
  the source screenshots. Colours, type, density, radius and button shape must
  match the source.
  - **Site.** For each signature component, open the matching `site.json` sample (or the source element's computed colour) and confirm the hex you used is the one the component really shows. Text lists contain colours a component never paints.
  - **Markdown spec** (no screenshots). Compare each signature piece with its §4 / component-table row: radius, fill, border, case, dot or icon. List each as present, different or absent.
  - **Before finalising.** For each `samples` key (input, table, card, badge, nav, footer) on every page, quote the extracted values in §4, or say which page lacks it. Never write "not present" for something any page has.

  Fix the mapping and re-run until everything matches.
- **If it cannot pass**: delete `OD/design-systems/<id>/`, revert any
  `tokens.schema.ts` edit, and tell the user it was NOT imported.

## Step 6: make it live and report

The backend caches design systems for the process lifetime (`od_loader.py:439`).
Restart it (dispatch the `devops` agent, or ask the user), then check
`curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/prototype/design-systems/<id>/preview`.
If no backend is running, say so and skip the check.

Report in this shape:

```
Imported: OD/design-systems/<id>/          (full path first)
Name / category: <H1> · <category> (new tab: yes/no)
Source: <input>, <kind>; pages/docs read: <n>
Tokens: <n> from the source · <n> authored · <n> schema defaults · <n> aliases · extensions: <list>   (copy make_ds.py's lines)
Schema: tokens.schema.ts BRAND_EXTENSIONS edited: yes/no (snippet: …)
Read: <docs read> · coverage.md: <n> lines placed, <n> under Known gaps
Themes: <list>   Signature components: <list>
Coverage: every source section → DESIGN.md section / Known gaps
Checks: validate exit <code> (<n> warnings: …why) · preview exit <code> · visual compare per source component: present / different / absent
Live: backend restarted / not running
```

Optionally add a one-line entry to `OD/design-systems/README.md`, as iberia has.
Do not commit.

## Never

- Write into `OD/design-systems/` or `tokens.schema.ts` before step 2's answers
  and the id check.
- Ship boilerplate ("Token from style foundations"), a missing section, or an
  unsourced value without `(authored)`.
- Let `components.html` drift from `tokens.css`. Regenerate both with `make_ds.py`.
- Copy logos, images or proprietary font files from a site or export.
- Use Playwright's bundled Chromium.

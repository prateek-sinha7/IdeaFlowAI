---
name: import-template
description: Use when the user wants to import, convert or add an HTML prototype or slide deck exported from Claude (a Claude Design project folder with .dc.html files, its standalone/bundled HTML, a .zip of either, or a plain HTML artifact) as a VelocityAI design template. Asks for the template name and gallery category, rebuilds the export as a static pipeline-ready example.html plus SKILL.md, places it in skills/opendesign/design-templates/<id>/, and proves it with the real loader and real Chrome.
argument-hint: <path to export folder | .html | .zip> [name="..."] [category="..."]
---

# import-template

Turns an HTML prototype or deck exported from Claude into a template the
VelocityAI galleries list and the prototype and PPT pipelines can build from.

## Conventions

- **Paths.**
  - `SKILL_DIR` is the folder holding this file (`skills/velocity/import-template`, `.claude/skills/import-template` or `.kiro/skills/import-template`).
  - `REPO` is the git root.
  - `OD` is `REPO/skills/opendesign`. A test may point `OD` at a scratch copy; every script derives its paths from the folder you pass it.
  - `W` is your scratch work dir, for example `<scratchpad>/import-<id>/`. Nothing in `W` ever goes into the repo.
- **Python.** `inspect_export.py` is stdlib-only, so run it with `python3 -B`. Run `validate_template.py` with `REPO/backend/.venv/bin/python -B`, which has the real loader and yaml. `-B` keeps `__pycache__` out of the skill folder.
- **Node.** Run Node scripts with `node`. They load Playwright from `REPO/frontend/node_modules` and always launch real Google Chrome (`channel: 'chrome'`).
- **Shell.** Do not wrap commands in `timeout` (it does not exist on macOS). Keep every script's exit code by sending its output to a log first, then printing the code: `node … > W/snap.log 2>&1; echo "exit $?"`. Quote the real exit codes in the report.
- **Contract.** Read `SKILL_DIR/reference/contract.md` before step 4. It lists what the app actually reads from a template folder, with file:line evidence.
- **The goal is the ORIGINAL.** The template must look and contain what the export shows. Never add effects or content the original does not have, and never silently drop content it does have.

## What a finished template is

```
OD/design-templates/<id>/
├─ SKILL.md        frontmatter (name, description, triggers, od.*) + builder instructions
├─ example.html    static, self-contained, one pattern per screen/state (or one slide per slide)
└─ assets/         only if example.html needs local files (prototype only; decks never)
```

A **thin** prototype (`od.shape: thin`) is `SKILL.md` + `example.html` only, with one finished
screen. See `OD/TEMPLATE-DESIGN.md` §9; `airline-disruption-light` is the golden reference.
After placing it, generate the thumbnail with
`cd backend && .venv/bin/python scripts/generate_template_thumbnails.py --only <id> --force`.

Nothing else may be in the folder: no `snapshot-report.json`, `shots/`, source
exports or thumbnails. `thumbnail.jpg` is generated at image build and is gitignored.

## Step 1: inspect the export

```bash
python3 -B SKILL_DIR/scripts/inspect_export.py "<input>" --work "W/src" --od OD
```

`--work` is used only for a `.zip`.

| Field | Use |
|---|---|
| `source_kind` | `claude-design-bundle` (standalone, renders offline: preferred), `claude-design-project` (`.dc.html`, needs network for React and fonts), or `html` |
| `entry` / `candidates` / `versions` | When there is more than one candidate, the step-2 question round MUST ask which is final. Show each file's `screens_declared`; the bundle usually equals the newest `.dc.html`. |
| `kind` | `prototype`, `deck` or `document`, with `signals.scores` |
| `logic` | `screens` (the source's `SCREENS`), `roles`, `roles_snippet`, `state_keys`. This is the coverage checklist for step 3. |
| `deck_stage`, `siblings` | a `<deck-stage>` deck or local files the entry loads |
| `brand_hints` | brand words in the title, the bundled design system, wordmarks |
| `similar_templates` | existing templates with the same title. Possible duplicate: ask. |
| `ds_dirs` | a Claude Design design system shipped with the export (`_ds/<id>/`) |
| `uploads` | the brief, PDF and screenshots given to Claude. Read them with the Read tool: every `.md`/`.txt` in full, a PDF's first 5 pages (`pages: "1-5"`; more only if they define screens or rules the source lacks), and every PNG. Note the personas, the screens and the rules, and list what you read in the report. |
| a `LICENSE` next to the entry | ask whether to keep it; if kept, copy it into the template folder as `LICENSE` and name it in the report |
| `logic.branches` | every `<sc-if>` condition in the template: the raw list for the coverage checklist |

Then read the source logic. For a `.dc.html`, read the
`<script type="text/x-dc">` block: `SCREENS`, `ROLES`, the `state = {…}` keys and the
handlers that set them. For a bundle, read the newest `.dc.html` next to it.

**Coverage checklist.** Make a table with one row per item in `logic.screens`
plus one row per entry in `logic.branches`. Classify each row:

- **screen**: a nav destination, including role-only ones. Captured as a pattern.
- **state**: changes the layout or the available actions. Examples are a drawer
  or dialog open, a wizard step, an approved, sent or closed result, a blocking
  rule, search results, a role menu. Captured as a state pattern.
- **variant**: changes only a value inside a screen (a slider, a toggle, a
  template pick, a language, a filter). Not captured. Listed in the template
  SKILL.md "Not in the example" line, with the control that produces it.

Every row ends up captured, or listed with its reason. Each branch gets its own
row in the report; lumping ("39 branches not captured") is not allowed.

A **blocking rule** or a **result** (approved, sent, printed, closed) is always a
state, never a variant. That holds especially when the brief or uploads mention it
("exit row not allowed", "rule tooltip"). Capture it, or say why its click path is
impossible.
For a deck, the checklist is the slide list, taken from `snapshot-report.json` `slides` after step 3.

If `kind` is `document` (a printable page, a brief rendered to HTML), tell the
user it is not a prototype or a deck. Ask whether to stop, or to import it as a
prototype with a generated frame (one screen per `h2` section, step 3 `--split h2`).

## Step 2: ask, in ONE question round

Use AskUserQuestion unless the user already gave the answer in the request
(`name=`, `category=`). Never invent the final name silently.

- **Non-interactive.** If AskUserQuestion is unavailable, or the task supplies the answers, write the question round into the report and use the given answers.
- **Defaults when an answer is missing.** Branding: keep. Platform: from the viewport. Design system: not now.
- **No default.** The name, the category, and the duplicate question (when `similar_templates` is not empty) have none. Stop and ask; never assume.

1. **Version** (only if `candidates` > 1): which file is final.
2. **Name**: the display name, Title Case, at most 40 characters. Offer 2-3 from
   `title` and the brief. The folder id is its kebab case
   (`Airport Agent Workspace` → `airport-agent-workspace`).
3. **Category**: the gallery tab. Put the best fit first, marked "(Recommended)".
   - **Prototype**: the tab comes from `od.scenario`.

     | Tab | write `od.scenario:` |
     |---|---|
     | Operations | `operations` |
     | Product | `product` |
     | Engineering | `engineering` |
     | Design | `design` |
     | Marketing | `marketing` |
     | Finance & HR | `finance` (or `hr`) |

   - **Deck**: the tab comes from the NAME, not a field
     (`PPTTemplateGallery.tsx:21-31`). Make sure the name contains the keyword:

     | Tab | the name must contain |
     |---|---|
     | Pitch Deck | Pitch, Investor, Fundraising |
     | Business | Weekly, Report, Quarterly, Course, Training |
     | Tech | Tech, Code, Terminal, Engineering |
     | Editorial | Editorial, Magazine |
     | Minimal | Minimal, Simple, Clean |
     | Creative | (no keyword) set `od.scenario: creative` |

     Any other name shows only under "All". Still write an `od.scenario`.
4. **Branding** (only if `brand_hints` shows a brand): keep the brand's wordmark,
   names and sample data as in the export (the default), or neutralise them?
5. **Platform** (prototype only, only if unclear): `desktop` or `mobile`.
5b. **Shape** (prototype only): `full` (every screen, the default) or `thin` (the frame plus ONE finished screen). For `thin`, also ask which screen to keep and name the operator and role for the top bar. Follow `OD/TEMPLATE-DESIGN.md` §9 and copy `design-templates/airline-disruption-light/` as the model.
6. **Design system** (only if `ds_dirs` is not empty and no matching system is in
   `OD/design-systems/`): offer to run `import-design` on it afterwards.
7. **Duplicate** (only if `similar_templates` is not empty): continue, or stop.

**Id check, before anything is written.** Run
`test -e OD/design-templates/<id> && echo EXISTS || echo FREE`. If it prints EXISTS, show what is there
and ask: pick another name, or replace it. Replace only on an explicit yes.
Re-check with the new name. If an answer matches more than one candidate file,
take the one whose `screens_declared` matches, and say which one you took. If
branding is not answered, keep it.

## Step 3: capture in real Chrome

```bash
node SKILL_DIR/scripts/snapshot.cjs --entry "<entry>" --out "W/draft" --kind <prototype|deck> \
     --prefix <2-3 letters from the id> --title "<Name>" [--expect-screens <logic.screens_declared>] [--config W/cfg.json] [--split h2] \
     > W/snap.log 2>&1; echo "exit $?"
```

Pass `--expect-screens` only when `logic.screens_declared` is a number. Omit it for decks and documents.
Exit 3 means nothing was captured; exit 4 means a configured state matched nothing (fix its selector).

The script:
- clicks every nav item and captures the content area per screen
- runs the config `states`
- turns inline styles into shared `<prefix>-N` classes (kept stable across reloads)
- collapses Claude Design's expanded `all: unset`
- drops runtime wrappers and attributes (`#dc-root`, `sc-host`, `sc-interp`, `data-screen-label`)
- collects the page CSS, including runtime-inserted rules, dedupes it and prunes unused rules
- bridges role colours and fonts, including success/warn/danger/info from the source tokens, to `:root`

It writes `W/draft/example.html`, `snapshot-report.json` and
`shots/<id>.png`, the last being screenshots of the ORIGINAL for each screen and
state. With nothing captured it exits 3 and writes no `example.html`.

**Config** (`W/cfg.json`):

```json
{ "states": [
    { "id": "approval-dialog", "purpose": "Confirm a batch before it runs",
      "steps": [{"click": "text=Approve batch"}], "capture": "[role=dialog]", "overlay": true },
    { "id": "supervisor", "purpose": "Station supervisor board", "reset": true,
      "nav": true, "label": "Supervisor", "icon": "monitoring",
      "steps": [{"click": "header button:has-text('Pilar')"}, {"click": "text=Supervisor"}] } ],
  "skipNav": ["Sign out"] }
```

- `content`, `nav` and `capture` are plain CSS selectors (`querySelector`). Step
  `click`, `type[0]` and `hover` take Playwright selectors (`text=…`,
  `button:has-text(…)`, `nav >> text=…`).
- **Exit codes.** `snapshot.cjs` exits 4 when any configured state failed (a click timed out, or the selector matched nothing). Fix it and re-run; never ship with exit 4.
- States run in order, after the nav pass. Without `reset` a state continues
  from where the previous one left the page; `reset: true` reloads it first.
- `capture` defaults to the content area (`main`), and then its children become the pattern.
- **Capture states narrowly.** A state that changes one card (a check-in step, a blocking rule, an approved result) captures only that card's container. Re-capturing the whole `main` for every state duplicates the screen and blows the size budget.
- `overlay: true` is for dialogs and drawers. Capture the dialog or drawer element itself. In the preview it shows fixed over a scrim, on top of the screen named in `under` (default: the first screen), and keeps its own position (right-hand drawers stay right).
- `under` takes a screen id or its nav label. It sets the screen that shows beneath an overlay: use the screen the overlay really opens from (`"under": "gate-boarding"` for the close-flight dialog).
- Overlays get a scrim only if the original page had one. A dialog that the original centred stays centred. Esc closes an overlay in the preview, and the scrim never blocks the nav.
- `"navTo": {"AI assistant": "ai-drawer"}`: a nav item whose screen IS a state (a drawer, a dialog) opens that state instead of capturing a duplicate screen.
- `"order": ["gate-boarding", "close-flight-dialog", …]`: pattern ids emitted right after the first screen, so the screens builders most need sit inside the 120,000-char prompt window. Put role-only screens and overlays before large grids.

**Config recipes:**
- **Role switch.** Open the user menu, then pick the role: `{"click": "[aria-haspopup]"}` (or the button showing the user's name; probe for it first), then `{"click": "text=<role name>"}`, with `reset: true`.
  - Give the state `nav: true`.
  - Copy its `label` and `icon` from that role's own nav, read from the original shot or the `.dc.html` nav and labels. Never guess them.
- **Viewport.** The default is 1440x900. Pass `--viewport 1920x1080` when the brief targets that size, and use the same for the preview.
- **Version tie-break.** When a bundle and a `.dc.html` share `screens_declared`, take the bundle (it renders offline) and say so.
- **Wizard steps.** Click the source's own Continue or Next button once per step (`{"click": "button:has-text('Continue')"}`), one state per step, each with `reset: true` and the steps up to it.
- **Find a selector before a full run.** Use a one-line probe:
  `node -e "const {chromium}=require('REPO/frontend/node_modules/playwright');(async()=>{const b=await chromium.launch({channel:'chrome'});const p=await b.newPage();await p.goto('file://<entry>');await p.waitForTimeout(3000);console.log(await p.evaluate(()=>[...document.querySelectorAll('aside,[role=dialog],[role=menu],header button')].map(e=>e.tagName+'.'+e.className+' '+(e.innerText||'').slice(0,40))));await b.close()})()"`
- `nav: true` adds a nav item for a role-only screen, cloned from the last real nav item, with `label` and `icon`.
- The chrome (brand bar, user name) comes from the first screen's role. Say so in the template SKILL.md's Role section.

Read `snapshot-report.json` and fix before going on:

- **`screens` + `states` vs the coverage checklist.** Every row is covered, or
  has a reason. A `nav shows N of M declared screens` warning means role-gated
  screens are missing.
- **`warnings` starting `role check:`.** Correct the role in `:root` using
  `roles.ranked` and the original shots.
- **`bridged` / `unbridged`.** Unbridged ones are coincidental equal colours.
  Bridge one by hand only if it really is that role.
- **`chars`.** Over 120,000 means run the trimmer. The builder's prompt holds only the first 120,000 characters (`od_context.py:37`), so patterns past that point are never seen there:

  ```bash
  node SKILL_DIR/scripts/trim.cjs W/draft/example.html --budget 120000
  ```

  - **What it does.** It first applies a lossless pass (whitespace, comments, CSS minify). Then it shortens long runs of repeated rows, items and seats.
  - **What it never removes.** Header rows, column cells, controls (buttons, pills, options), rows with a selected or special marker, "N more" summary rows, steppers, tabs, KPI rows, legends, nav, patterns, slides. It never goes below 5 items.
  - **After it runs.**
    - Fix every heading in `heading_claims_to_fix` ("Missing passengers · 9" over 6 rows becomes "Missing passengers · 9 (6 shown)").
    - For a kept "N more" summary row, add the removed count to N.
    - Pin rows that carry a rule the brief shows with `--keep <css>` (an exit row, a blocked seat).
  - **Reverts.** If even the deepest round cannot reach the budget, `trim.cjs` keeps only the lossless pass (`reverted` in its JSON): losing rows for nothing is worse. Pass `--force` only if the trimmed file is within 10% of the budget.
  - **If it is still over budget**, in this order:
    1. use `navTo` for nav items that duplicate a state
    2. re-capture states narrowly
    3. drop near-duplicate patterns the validator names
    4. shorten by hand by the same rules
  - **If it is still more than 15% over** after that, keep it. Use `order` so the most important patterns come first, name the patterns past the cap (`patterns_beyond_cap`) in the template SKILL.md ("Outside the prompt window"), and give the "Patterns in the prompt window" line in the report. The sandbox copy stays complete.
  - **Over budget is NEVER a reason to stop.** Always continue through steps 4-8 and report the size. Only a failing validator or preview stops an import (step 6).

**Deck.** `--kind deck` screenshots every ORIGINAL slide into
`shots/slide-NN.png`, then captures each slide into `div.deck > section.slide`
(1920x1080, scaled) with an inline keyboard/hash navigation script. Labels come
from `data-screen-label` or `data-label`. A `<deck-stage>` deck loses its nav pill,
`R` reset, number keys and speaker-notes UI. Record that in the template SKILL.md
("Original runtime features not carried over").

**Document** (`--split h2`): one pattern per `h2` section, plus a generated frame
(brand bar, a nav item per section, `main`). The script also:
- drops print-only CSS (`@page`, `@media print`, page-break rules)
- converts `pt` sizes to `px`
- treats a transparent page as white
- takes the accent from the heading colour or rule
- writes one original shot per section (`shots/<id>.png`)

**Original shots.** The mouse is parked before each one. A `<deck-stage>` deck's
own nav pill ("‹ 2/8 › Reset") appears in the original slide shots, so ignore it
when you compare.

## Step 4: finish example.html

Work on the draft, never on the export. Follow `reference/contract.md`.

1. **Frame**: `<main>` is the content area, with `.nav-item[data-go]` buttons
   before it (`template_kit.py:195-256`). There is one
   `<section class="pattern" data-pattern="<id>">` per screen or state.
   - The script writes each comment as `<!-- PATTERN <id> - TODO purpose (<hint>) -->`. Replace every TODO with what the user does there: "Agent finds a passenger by booking code, ticket or surname". The validator fails while any TODO is left.
   - Only the first pattern is visible.
   - **Thin shape:** keep one pattern and drop the rest. Keep the whole frame (brand bar with time and operator name and role, banner, nav, footer). Leave the other nav items as plain `.nav-item` buttons with no `data-go`. Remove `<script>` and `style=` attributes. Fill every field with real data, and write `shape: thin` under `od:` in SKILL.md. The page must fit 1100-1900px with no horizontal scroll (`minmax(0, 1fr)` grid columns, stacked panels).
2. **Tokens**: the first `<style>` starts with the Google Fonts `@import`, then
   `:root` with `--bg --surface --fg --muted --border --accent --accent-on`, the
   fonts, and `--success --warn --danger --info` when the source has them.
   - Role colours outside `:root` must be `var(--…)`. The validator flags leaked role literals.
   - Other one-off hex values may stay.
3. **Self-contained**:
   - The only external URLs allowed are Google Fonts. No remote scripts, no `data:` fonts.
   - No runtime: no `support.js`, React, `__bundler`, `x-dc` or `dc-root`.
   - Images: inline small SVGs. For a prototype, larger files go in `assets/` and are referenced as `assets/<file>`. Decks never use `assets/`.
4. **Size**: as step 3 (`trim.cjs`). Report the final size.
5. **Content**: keep the export's realistic sample data and copy. Remove only
   the export's own scaffolding (bundler thumbnail, "Unpacking…" loader). Apply
   the step-2 branding answer.
6. **Title**: `<title>` is the template name.

**Deck checklist.**
- `div.deck > section.slide` once per slide, each with `data-label`.
- The keyboard and hash navigation script stays inline.
- `:root` carries the role variables and the source fonts.
- No `assets/`; everything is inline.
- Check slides that the snapshot warned about (negative z-index) against their original shots.

## Step 5: write the template SKILL.md

Describe the draft first. It needs no SKILL.md and can live outside OD:
`REPO/backend/.venv/bin/python -B SKILL_DIR/scripts/validate_template.py W/draft --draft <prototype|deck>`.
It lists every pattern's (or slide's) headings, buttons, rows and inputs. Base the
SKILL.md on that output and on the uploads or brief, using
`reference/template-skill.md` as the skeleton.

- The **Screen patterns** table lists exactly the patterns in `example.html`, by id.
  The validator cross-checks this.
- Describe only what the example contains: the buttons it really has, the steps
  it really shows. If a source feature was not carried over, say so in a "Not in
  the example" line instead of describing it.
- Do not claim "no colour literals outside :root" unless it is true.
- Every structural claim must hold in `example.html`: a fixed brand bar, `<prefix>-N` shared classes, shortcut keys. Interactions the static example does not run go under "Interactions in the real product", not as if the example did them.

## Step 6: place, validate, preview, compare

```bash
mkdir -p OD/design-templates/<id>
cp W/draft/example.html W/SKILL.md OD/design-templates/<id>/        # plus assets/ if used
REPO/backend/.venv/bin/python -B SKILL_DIR/scripts/validate_template.py OD/design-templates/<id> --describe
node SKILL_DIR/scripts/preview_check.cjs OD/design-templates/<id> --out W/preview
```

- `validate_template.py` must print `RESULT: PASS`. It uses the real `od_loader`
  and `template_kit`, and checks:
  - CSS integrity, and shared classes without rules
  - runtime leftovers and scratch paths
  - role sanity and leaked role literals
  - near-duplicate patterns
  - SKILL.md vs example consistency

  Fix every `[E]`. Fix or justify every `[W]` in the report.
- `preview_check.cjs` must exit 0:
  - every nav item shows its pattern
  - every state pattern renders (`state-<id>.png`)
  - `<main>` is in flow and wide
  - nav items are styled, not browser defaults
  - the body font loads
  - no page errors
- **Compare every screen and state**, with the script:

  ```bash
  node SKILL_DIR/scripts/compare.cjs W/draft/shots W/preview --out W/compare [--mask x1,y1,x2,y2]
  ```

  - It pairs every original shot with its preview shot, writes `W/compare/<id>.png` (original | preview | changed pixels in magenta) and lists any pair over 12% under `review`.
  - Read the composite for every pair in `review`, and for at least 5 others. Check layout, fonts, colours, and content counts (steps, KPI tiles, rows).
  - Fix drift toward the original, then re-run preview and compare.
  - Remaining differences you accept go in the report with their cause:
    - a deck-stage nav pill: use `--mask 846,1022,1073,1058`
    - role chrome
    - trimmed rows
  - `not_compared` must be empty, or each entry must have a reason.
- **If it cannot be made to pass**: delete `OD/design-templates/<id>/`, keep `W`,
  and tell the user it was NOT imported and why.

## Step 7: make it live

The backend caches the catalog for the process lifetime (`od_loader.py:181`).
Restart it (dispatch the `devops` agent, or ask the user), then check:

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/prototype/templates/<id>/preview   # deck: /api/ppt/templates/<id>/preview
```

If no backend is running, say so and skip this step. Deployed environments pick
the template up on the next image build.

## Step 8: report (use this shape)

```
Imported: OD/design-templates/<id>/        (full path first)
Name / tab: <Name> · <tab> (od.scenario=<x>)          deck: <tab from name>
Source: <entry file> (<version chosen>), <kind>
Coverage:
  | Source screen/state | Pattern / slide | Note |      every checklist row
Size: example.html <N> chars (cap 120,000); lossless -<n>; trimmed runs: <n>; headings fixed: <n>
Prompt window: <n> of <total> patterns start inside the first 120,000 chars (first cut: <id> | none)
Uploads read: <file: pages> …
Checks: validate exit <code> (<n> warnings: …why) · preview exit <code> (<n>/<n> checks)
Compare: <compared> of <of> pairs (compare.cjs); over 12%: <ids + cause>; not compared: <ids + reason>
Role chrome: <which role's chrome the captured frame shows; how other roles differ>
Not carried over: <runtime features, states skipped and why>
Live: backend restarted / not running
Next: import-design for <ds_dirs>? (if offered)
```

Do not commit.

## Never

- Write into `OD/design-templates/` before step 2's answers and the id check.
- Copy the export's runtime (`support.js`, `_ds_bundle.js`, React) or its `.dc.html`
  into the template.
- Leave `snapshot-report.json`, `shots/`, `node_modules`, source files or scratch
  paths in the template folder or its files.
- Trim with your own script. Use `trim.cjs`, and shorten by hand only by its rules.
- Use Playwright's bundled Chromium. The scripts launch `channel: 'chrome'`.

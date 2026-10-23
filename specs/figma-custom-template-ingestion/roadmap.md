# Design Ingestion Roadmap
## Figma Frames & Custom HTML → `.context/design/` Filesystem Parity

> **Goal:** Figma frame uploads and custom HTML uploads are processed by a
> **Design Ingestor** agent that produces the SAME `.context/design/` file
> structure that catalog templates and design systems already produce. Every
> downstream agent (`prototype-specify`, `pb-spec`, `pb-design`, builders)
> reads `.context/design/` without knowing how it was populated.
>
> **Constraint:** The catalog template + design system path is UNCHANGED.
> Only the two new source types (Figma, custom HTML) are restructured.

---

## 1. Current State — How `.context/design/` Works Today

### 1.1 The Filesystem Contract

Every prototype run (Fast and V2) that uses a catalog template produces this
sandbox layout before step 1 runs:

```
.context/
├── selections.json                    ← wizard choices; agents read this first
└── design/
    ├── design-system.md               ← DS tokens (colors, type, spacing)
    ├── craft.md                       ← quality rules (may be absent)
    ├── tokens.css                     ← DS raw CSS vars (may be absent)
    ├── components.html                ← DS component markup (may be absent)
    └── template/
        ├── SKILL.md                   ← template workflow instructions
        ├── example.html               ← full working HTML reference
        ├── assets/
        │   └── template.html          ← starter scaffold HTML
        └── references/
            ├── layouts.md
            └── checklist.md
```

`selections.json` shape:
```json
{
  "template_id": "web-prototype",
  "ds_id": "github",
  "template_name": "Web Prototype",
  "ds_name": "GitHub",
  "no_template": false,
  "is_design_system_required": null
}
```

### 1.2 How It Gets Populated (Catalog Path)

```
Wizard (browser)
  │  template_id, design_system_id, [custom_template_body]
  ▼
launch_context.py :: resolve_launch_od_context()
  │  calls load_prototype_od_context()
  ▼
od_context.py :: load_prototype_context()
  │  reads od_loader (disk) → builds od_context dict
  ▼
od_context_sandbox.py :: write_od_context_to_sandbox()
  │  writes all files to .context/design/
  ▼
.context/design/ ← POPULATED before step 1
  │
  ├── prototype-specify reads SKILL.md + example.html + design-system.md
  ├── pb-spec (V2 Analyst) reads ALL files in .context/design/
  ├── pb-design (V2 Architect) reads selections.json + ls .context/design/*
  └── builders reference via opendesign context provider (SKILL.md + DS)
```

### 1.3 What Each Downstream Agent Actually Reads

| Agent | Files read from `.context/design/` |
|---|---|
| `prototype-specify` (Fast) | `template/SKILL.md`, `template/example.html`, `design-system.md`, `../selections.json` |
| `pb-spec` (V2 Analyst) | `../selections.json` + `ls .context/design` + every file present |
| `pb-design` (V2 Architect) | `../selections.json` + `design-system.md`, `tokens.css`, `components.html`, `craft.md`, `template/SKILL.md`, `template/example.html`, `template/assets/template.html` |
| builders | `opendesign` context provider injects DS body + SKILL.md body |

**Key insight:** agents do `ls .context/design/` and read what exists. They
do not fail if a file is absent. The contract is the directory layout, not
a fixed mandatory set.

### 1.4 Current Custom HTML Upload — The Gap

Today, `custom_template_body` (pasted HTML / URL fetch) is handled by
`_synthesize_custom_template()` in `od_context.py`. It wraps the raw HTML in
a SKILL.md-style instruction preamble and injects it as `template_body`.

**What it produces in `.context/design/`:**
```
.context/design/template/SKILL.md   ← instruction wrapper + raw HTML
                                      (NO example.html, NO assets/)
```

**What it is missing:**
- `template/example.html` — so agents have no visual HTML reference to clone
- `design-system.md` — derived colors/fonts from the custom HTML are never
  extracted; the user must still pick a catalog DS separately
- Any visual fidelity signal; the agent sees instructions, not the actual HTML
  as a reference file

**For Figma frames (current state, post-feature-branch):**
Figma PNGs go to `.uploads/` as image-type manifest entries. The fi-planner
creates synthetic shards, fi-readers reads each PNG visually, fi-synth produces
`synthesis.md`. The `pb-spec` (Analyst) then reads `synthesis.md` and
`.context/design/` — but `.context/design/template/` is EMPTY (no template was
selected), and `.context/design/design-system.md` is also absent (no DS was
selected). The Architect (`pb-design`) reads `selections.json` and finds
`no_template: true`, `ds_id: null`.

**The result:** Figma visual fidelity lives only in `synthesis.md` (text
description of what the Reader agents saw). The Architect and builders have
no direct image reference, no extracted color palette, no CSS variable
baseline. This is the gap your diagram is identifying.

---

## 2. Target State — Design Ingestor

### 2.1 The Goal

After the Design Ingestor runs, `.context/design/` looks like this regardless
of whether the user chose a catalog template, uploaded custom HTML, or uploaded
Figma frames:

```
.context/
├── selections.json                    ← SAME shape, new source_type field
└── design/
    ├── design-system.md               ← ALWAYS present; derived if not chosen
    ├── craft.md                       ← absent if no rules
    ├── tokens.css                     ← present if derivable
    └── template/
        ├── SKILL.md                   ← ALWAYS present
        ├── example.html               ← ALWAYS present  ← KEY CHANGE
        ├── figma/                     ← NEW: present when source=figma
        │   ├── frame-1.png
        │   ├── frame-2.png
        │   └── frames.json
        └── assets/
            └── template.html          ← present if derivable
```

`selections.json` — extended shape:
```json
{
  "template_id": "custom-figma",
  "ds_id": "derived",
  "template_name": "Figma Upload",
  "ds_name": "Derived from Figma",
  "no_template": false,
  "is_design_system_required": null,
  "source_type": "figma",            ← NEW: "catalog" | "html" | "figma"
  "figma_frame_count": 5             ← NEW: present when source_type=figma
}
```

### 2.2 What Each Source Produces

#### Catalog Template + Catalog DS (UNCHANGED)
Exact same path as today. `write_od_context_to_sandbox()` writes everything.
The Design Ingestor does NOT run for this path.

#### Custom HTML Upload → Design Ingestor
Input: raw HTML string from wizard

The Ingestor agent produces:
- `template/SKILL.md` — instruction preamble + HTML reference (same as today)
- `template/example.html` — the raw HTML verbatim (NEW — currently missing)
- `design-system.md` — agent extracts: background color, primary/accent
  colors, font families, spacing scale from the HTML's CSS. Falls back to
  brief-compatible neutral tokens if extraction fails.
- `selections.json` with `source_type: "html"`

#### Figma Frames Upload → Design Ingestor
Input: PNG frames already in `.uploads/` (from run_figma_frames endpoint)

The Ingestor agent produces:
- `template/figma/frame-N.png` — symlink/copy of each frame from `.uploads/`
- `template/figma/frames.json` — ordered manifest: `[{index, filename, description}]`
- `template/example.html` — a minimal HTML scaffold that mirrors the Figma
  screens' layout structure (sidebar nav, top bar, content area, etc.) — derived
  by visual analysis of the frames. This becomes the builders' HTML starting point.
- `template/SKILL.md` — workflow instructions: "use these frames as your visual
  reference; replicate their layout, chrome, and visual language faithfully"
- `design-system.md` — agent extracts the color palette, typography, and
  spacing from the frames using vision. Produces a DESIGN.md-formatted doc
  with `--bg`, `--fg`, `--accent`, `--surface`, `--border` values.
- `selections.json` with `source_type: "figma"`, `figma_frame_count: N`

---

## 3. Architecture — Where the Ingestor Lives

### 3.1 Trigger Point

The Design Ingestor runs as a **new workflow step** injected BEFORE `fi-planner`
in prototype_v2 when `source_type` is `html` or `figma`.

For prototype (Fast), it runs as a **new pre-step** before `prototype-specify`.

```
Wizard launch
  │
  ▼
launch_context.py :: resolve_launch_od_context()
  │
  ├── source_type = "catalog"  → existing path (unchanged)
  │     write_od_context_to_sandbox() → .context/design/ populated
  │     ↓ step 1 runs normally
  │
  ├── source_type = "html"     → new path
  │     write minimal selections.json (source_type, template_id="custom-html")
  │     write raw HTML to .context/design/template/raw-upload.html
  │     ↓ Design Ingestor step runs FIRST
  │         reads raw-upload.html
  │         produces: SKILL.md, example.html, design-system.md
  │     ↓ step 1 (prototype-specify / fi-planner) runs normally
  │
  └── source_type = "figma"    → new path
        write minimal selections.json (source_type, figma_frame_count)
        frames already in .uploads/ from run_figma_frames endpoint
        ↓ Design Ingestor step runs FIRST
            reads each frame PNG visually
            produces: template/SKILL.md, template/example.html,
                      template/figma/frame-N.png, template/figma/frames.json,
                      design-system.md
        ↓ fi-planner / prototype-specify runs normally
```

### 3.2 The Ingestor as a Capability (Design)

The Ingestor is a `single_shot` custom-agent step in the workflow YAML.
It is NOT part of the execution engine kernel. It is a pure agent step that
reads input, produces `.context/design/` files, and exits.

This satisfies:
- **SC-001** — no `if pipeline_type ==` in engine.py
- **INV-3** — existing runs without Figma/HTML uploads are byte-identical
- **No new DB migrations** — files only

### 3.3 Existing Agent Changes (Minimal)

`pb-design` (Architect, V2) already reads:
```
.context/selections.json
ls .context/design
ls .context/design/template
```
And reads every file that exists. When `source_type: "figma"` and
`template/figma/frames.json` exists, it will read the frame manifest and
reference the frame images via `read_file` (vision). **No prompt change needed
for pb-design** — it already uses the "read what exists" pattern.

`prototype-specify` (Fast) already reads `template/SKILL.md` and
`template/example.html`. When the Ingestor generates these from Figma/HTML,
`prototype-specify` reads them exactly as it would for a catalog template.
**No prompt change needed for prototype-specify**.

---

## 4. Flow Diagrams

### 4.1 Current Catalog Flow (UNCHANGED — reference)

```
┌─────────────────────────────────────────────────────┐
│  CATALOG TEMPLATE + DESIGN SYSTEM (current, frozen) │
└─────────────────────────────────────────────────────┘

Wizard
  template_id="web-prototype"
  design_system_id="github"
       │
       ▼
od_context.py
  od_loader.get_template("web-prototype")    → SKILL.md body
  od_loader.get_template_files(...)          → example.html, assets/, refs/
  od_loader.get_design_system("github")      → design-system.md body
  od_loader.get_design_system_files(...)     → tokens.css, components.html
       │
       ▼
od_context_sandbox.py :: write_od_context_to_sandbox()
       │
       ▼
.context/design/
  ├── design-system.md      ← github tokens
  ├── tokens.css
  ├── components.html
  └── template/
      ├── SKILL.md
      ├── example.html
      ├── assets/template.html
      └── references/layouts.md
       │
       ▼
Step 1 (prototype-specify / pb-spec)
reads files → writes spec.md
```

### 4.2 New Custom HTML Flow

```
┌──────────────────────────────────────────────────────┐
│  CUSTOM HTML UPLOAD (new, restructured)              │
└──────────────────────────────────────────────────────┘

Wizard
  template_id="custom-<timestamp>"
  custom_template_body="<!DOCTYPE html>..."
  design_system_id="github"   ← still required today; becomes optional
       │
       ▼
launch_context.py (new branch: source_type="html")
  write minimal selections.json:
    { source_type:"html", template_id:"custom-<ts>", ds_id:"derived" }
  write .context/design/template/raw-upload.html
  write .context/design/design-system.md (from DS if selected)
       │
       ▼
[NEW] Design Ingestor Step (single_shot custom-agent)
  reads: .context/design/template/raw-upload.html
  produces:
    .context/design/template/SKILL.md
      "This run uses a custom HTML template uploaded by the user.
       The HTML is your visual and structural reference.
       Replicate its layout, CSS class system, and visual identity."
    .context/design/template/example.html   ← the raw HTML verbatim
    .context/design/design-system.md        ← extracted OR from catalog DS
      (extract: background, primary color, fonts from <style> tags)
  updates selections.json:
    { source_type:"html", template_name:"Custom HTML Upload", ds_name:"..." }
       │
       ▼
.context/design/
  ├── design-system.md      ← extracted or catalog
  └── template/
      ├── SKILL.md           ← generated
      └── example.html       ← the user's HTML  ← KEY: now present
       │
       ▼
Step 1 (prototype-specify / pb-spec / pb-design)
reads files → writes spec.md
(IDENTICAL behavior to catalog template — agents see same file structure)
```

### 4.3 New Figma Frame Flow

```
┌──────────────────────────────────────────────────────┐
│  FIGMA FRAME UPLOAD (new, restructured)              │
└──────────────────────────────────────────────────────┘

Wizard (prototype_v2 mode)
  figmaFrames=[frame-1.png ... frame-5.png]
  [no template_id, no design_system_id]
       │
       ▼
Frontend :: uploadFigmaFrames(token, runId, frames)
  POST /api/runs/{id}/figma-frames
       │
       ▼
run_figma_frames.py
  writes: .uploads/frame-1.png ... frame-5.png
  writes: .uploads/manifest.json
    [{ name:"frame-1.png", type:"image", description:"Dashboard" }, ...]
       │
       ▼
launch_context.py (new branch: source_type="figma")
  write minimal selections.json:
    { source_type:"figma", template_id:"custom-figma",
      ds_id:"derived", figma_frame_count:5, no_template:false }
  (skip write_od_context_to_sandbox — Ingestor handles it)
       │
       ▼
[NEW] Design Ingestor Step (single_shot custom-agent)
  Phase 1 — Read all frames
    read_file .uploads/manifest.json
    for each frame: read_file .uploads/frame-N.png  (vision)
    extract per-frame:
      - screen name / purpose (from description + visual read)
      - layout structure (sidebar? topbar? content area?)
      - primary + background colors (sample from image)
      - font weight + density signal
      - navigation patterns

  Phase 2 — Write design-system.md
    synthesise across all frames:
      - color palette → --bg, --fg, --accent, --surface, --border, --muted
      - typography → --font-body, --font-display
      - density → compact / comfortable / spacious
    write_file .context/design/design-system.md

  Phase 3 — Write template files
    copy/symlink each frame:
      write_file .context/design/template/figma/frame-N.png
    write_file .context/design/template/figma/frames.json
      [{ index:0, filename:"frame-1.png", screen:"Dashboard",
         description:"...", layout:"sidebar-nav" }, ...]

    write_file .context/design/template/example.html
      A minimal HTML scaffold that mirrors the dominant layout:
      - sidebar nav structure if frames show a sidebar
      - topbar + content if frames show a topbar layout
      - uses derived CSS variables from Phase 2
      - ONE real screen as the visual anchor (most complex frame)
      (NOT a full prototype — just the shell structure as starting HTML)

    write_file .context/design/template/SKILL.md
      "# Figma Design Reference
       This run was launched with Figma screen exports as the design source.
       ## Visual Reference
       The Figma frames are at .context/design/template/figma/frames.json.
       Read frames.json for the screen inventory, then read each frame PNG.
       ## Rules
       - Replicate the visual language: colors, spacing, typography from
         the frames. The design-system.md has the extracted tokens.
       - Use the layout structure from example.html as your shell.
       - Each screen in frames.json corresponds to one prototype page."

  Phase 4 — Update selections.json
    write_file .context/selections.json
      { source_type:"figma", template_id:"custom-figma",
        template_name:"Figma Upload (5 screens)",
        ds_id:"derived", ds_name:"Derived from Figma",
        no_template:false, figma_frame_count:5 }
       │
       ▼
.context/design/                          ← SAME SHAPE AS CATALOG
  ├── design-system.md   ← derived from Figma
  └── template/
      ├── SKILL.md        ← generated
      ├── example.html    ← layout scaffold
      └── figma/
          ├── frames.json
          ├── frame-1.png
          └── frame-2.png ...
       │
       ├── prototype_v2: fi-planner → fi-readers → fi-synth → pb-spec → pb-design
       │   pb-design reads .context/selections.json → sees source_type:"figma"
       │   reads .context/design/template/figma/frames.json
       │   reads each frame PNG (vision) for direct visual reference
       │   writes design.md + build/theme.json (from derived design-system.md)
       │
       └── prototype (fast): prototype-specify
           reads template/SKILL.md → knows to use figma frames
           reads template/example.html → uses as layout base
           reads design-system.md → uses extracted color tokens
```

### 4.4 Side-by-side Comparison

```
                  CATALOG          CUSTOM HTML      FIGMA FRAMES
                  ───────────      ───────────      ────────────
SKILL.md          od_loader        Ingestor gen     Ingestor gen
example.html      od_loader        user HTML        Ingestor scaffold
design-system.md  od_loader        extracted/catalog Ingestor vision
tokens.css        od_loader (opt)  —                —
assets/template   od_loader (opt)  —                —
template/figma/   —                —                Ingestor copies
selections.json   od_context_sandbox Ingestor        Ingestor
source_type       "catalog"        "html"           "figma"
```

---

## 5. Implementation Roadmap

### Phase Summary

| Phase | What gets built | Files touched | Depends on | Verification |
|---|---|---|---|---|
| 1 | `source_type` detection, `selections.json` extension, YAML stub steps | `launch_context.py`, `od_context_sandbox.py`, `od_context.py`, both `workflow.yaml` | Nothing — foundation | `pytest tests/unit/` + `ruff check` + `pyright` |
| 2 | HTML Ingestor agent prompt | `design-ingestor-html/AGENT.md`, `prototype_v2/workflow.yaml`, `prototype/workflow.yaml` | Phase 1 | `pytest tests/integration/api/` + sandbox file assertions |
| 3 | Figma Ingestor agent prompt | `design-ingestor-figma/AGENT.md`, `prototype_v2/workflow.yaml` | Phase 1 | `pytest tests/integration/api/` + sandbox file assertions |
| 4 | OpenDesign provider Figma block | `opendesign.py`, `od_context_sandbox.py` | Phase 3 | `pytest tests/unit/` + golden check |
| 5 | pb-design Figma vision prompt | `prototype_v2/workflow.yaml` (pb-design step) | Phase 3 | YAML parses + `pytest --collect-only` |
| 6 | Prototype Fast integration | `prototype/workflow.yaml`, `prototype-specify/AGENT.md` | Phase 2 + 3 | YAML parses + `pytest --collect-only` |
| 7 | Frontend `source_type` signal | `LaunchWizard.tsx`, `page.tsx` | Phase 1 | `npm run build` + vitest |

**Phases 2 and 3 are independent** — they can run in parallel.
**Phases 4, 5, 6 depend on Phases 2 and 3** — run after both complete.
**Phase 7 is independent of all backend phases** — can run in parallel with any backend phase.

---

### Phase 1 — Ingestor Infrastructure (no agent yet)

**Goal:** Get the plumbing right. The Ingestor step can be a no-op stub.

1. **`launch_context.py`** — add `source_type` detection:
   - `source_type = "catalog"` when `template_id` is in the catalog (current)
   - `source_type = "html"` when `custom_template_body` is set
   - `source_type = "figma"` when `.uploads/manifest.json` has any `type=image`
     entries at launch time
   - Pass `source_type` into `od_context` dict

2. **`od_context_sandbox.py`** — write `source_type` into `selections.json`
   - Add `source_type` field to `_write_od_context_to_sandbox`
   - `rebuild_od_context_from_sandbox` reads it back

3. **`prototype_v2/workflow.yaml`** — add ingestor step as step 0:
   ```yaml
   - strategy: single_shot
     instance_id: design-ingestor
     name: Design Ingestor
     condition: "source_type in ['html', 'figma']"   ← only runs for custom
   ```
   For catalog runs, step 0 is skipped (condition false → engine skips step).
   For catalog, existing fi-planner is step 1 as today.

4. **`prototype/workflow.yaml`** — same: add ingestor step before
   `prototype-specify` with the same condition.

**Tests:** unit test `source_type` detection in `launch_context.py`.

**Verification for Phase 1:**
```bash
cd backend
uv run ruff check app/api/launch_context.py app/services/od_context_sandbox.py agents/execution_engine/od_context.py
uv run pyright app/api/launch_context.py app/services/od_context_sandbox.py
uv run pytest tests/unit/ -q --no-header
```
- Confirm `selections.json` written by `_write_od_context_to_sandbox` now contains `source_type`
- Confirm `rebuild_od_context_from_sandbox` reads `source_type` back
- Confirm catalog runs are byte-identical (INV-3): `git diff tests/agents/characterization/golden/` → empty
- Confirm both YAML files parse: `python -c "import yaml; yaml.safe_load(open('agents/workflows/prototype_v2/workflow.yaml'))"` + same for prototype

---

### Phase 2 — HTML Ingestor Agent

**Goal:** Custom HTML uploads produce the full `.context/design/` structure.

5. **`backend/agents/prompts/design-ingestor-html/AGENT.md`** — new prompt:

   ```
   You are the Design Ingestor for a custom HTML template.
   .context/design/template/raw-upload.html contains the user's HTML.

   Phase 1 — Read
     read_file .context/design/template/raw-upload.html  (page to end)

   Phase 2 — Extract design system
     From the HTML's <style> blocks and inline styles, extract:
     - Background color → --bg
     - Primary/accent color → --accent
     - Surface/card color → --surface
     - Text color → --fg
     - Border color → --border
     - Font family (body) → --font-body
     - Font family (display/headings) → --font-display
     If a .context/design/design-system.md already exists (user picked a
     catalog DS), skip this phase — do not overwrite.
     Otherwise: write_file .context/design/design-system.md

   Phase 3 — Write template files
     write_file .context/design/template/example.html
       (the raw HTML verbatim — do not modify it)
     write_file .context/design/template/SKILL.md
       (instruction wrapper explaining this is a user-uploaded HTML reference)

   Phase 4 — Update selections.json
     read_file .context/selections.json
     edit: set template_name="Custom HTML Upload", ds_name="Extracted"
     write_file .context/selections.json
   ```

6. **Regression:** run existing custom HTML tests; verify `example.html` now
   appears in sandbox.

**Verification for Phase 2:**
```bash
cd backend
uv run pytest tests/integration/api/ -q --no-header
uv run ruff check agents/prompts/design-ingestor-html/
```
- Confirm `design-ingestor-html` step appears in `prototype_v2` and `prototype` YAML with correct condition
- Confirm existing custom HTML integration tests still pass (custom_template_body path unchanged for catalog)
- Confirm `example.html` is now written to sandbox for HTML source type

---

### Phase 3 — Figma Ingestor Agent

**Goal:** Figma frame uploads produce the full `.context/design/` structure.

7. **`backend/agents/prompts/design-ingestor-figma/AGENT.md`** — new prompt
   (described in §4.3 Phase 1–4 above).

   Key rules:
   - Reads each PNG via `read_file` (vision) one at a time
   - Derives color palette by visual inspection (not pixel math)
   - Writes `template/figma/frames.json` as the screen inventory
   - Writes `template/example.html` as a layout scaffold
   - Writes `template/SKILL.md` with frame-reading instructions
   - Writes `design-system.md` with extracted tokens

8. **`od_context.py`** — add `load_figma_ingest_context()`:
   - Returns minimal `od_context` dict: `{source_type:"figma", template_id:"custom-figma", ds_id:"derived", figma_frame_count:N}`
   - Called by `launch_context.py` when `source_type="figma"`
   - Does NOT call `od_loader` (no catalog lookup)

9. **`od_context_sandbox.py`** — write minimal sentinel for Figma runs:
   - Write `selections.json` only (no template files — Ingestor does that)
   - Gate downstream `context_already_present()` correctly

**Verification for Phase 3:**
```bash
cd backend
uv run pytest tests/integration/api/test_figma_frames_api.py -q --no-header
uv run ruff check agents/execution_engine/od_context.py app/services/od_context_sandbox.py
uv run pyright agents/execution_engine/od_context.py
```
- Confirm `load_figma_ingest_context()` returns correct dict shape
- Confirm `context_already_present()` returns False for fresh Figma run (Ingestor must be able to write)
- Confirm `context_already_present()` returns True after Ingestor writes (revision runs must not overwrite)
- Confirm existing Figma frame upload tests still pass (12/12)

---

### Phase 4 — OpenDesign Provider Extension

**Goal:** The `opendesign` context provider injects Figma frame references
into agent prompts alongside the DS and SKILL.md.

10. **`opendesign.py`** — add Figma branch:
    When `od.get("source_type") == "figma"` and
    `template/figma/frames.json` exists in the sandbox:
    - Add a `FIGMA DESIGN REFERENCE` block listing the frame paths
    - The agent can then call `read_file` on specific frames during its turn
    - This is additive — the DS block and SKILL.md block still inject normally

11. **`selections.json`** schema extension — add `source_type` to
    `rebuild_od_context_from_sandbox` so resumed runs reload it correctly.

**Verification for Phase 4:**
```bash
cd backend
uv run ruff check agents/capabilities/context_providers/opendesign.py
uv run pyright agents/capabilities/context_providers/opendesign.py
uv run pytest tests/unit/ -q --no-header
# Golden check — must be empty:
git status --porcelain tests/agents/characterization/golden/
```
- Confirm `FIGMA DESIGN REFERENCE` block only appears when `source_type="figma"` AND `frames.json` exists
- Confirm catalog runs produce byte-identical context messages (INV-3 — golden check must be empty)
- Confirm `source_type="html"` runs are also unaffected

---

### Phase 5 — pb-design (Architect) Figma Awareness

**Goal:** The Architect explicitly reads Figma frame images when present,
for maximum visual fidelity in the theme derivation.

12. **`prototype_v2/workflow.yaml` — pb-design prompt** — add 3 lines to
    Phase 1 (Read):
    ```
    4. If .context/design/template/figma/frames.json exists:
       read_file it, then for each frame path, read_file the PNG (vision).
       These are the user's Figma screens — your theme and composition
       decisions should replicate their visual language faithfully.
    ```
    This is additive — the existing `ls .context/design` + read-all-files
    pattern already picks up `frames.json`; the explicit vision read is
    the new piece.

**Verification for Phase 5:**
```bash
cd backend
python -c "import yaml; yaml.safe_load(open('agents/workflows/prototype_v2/workflow.yaml'))" && echo "YAML valid"
uv run pytest --collect-only -q 2>&1 | tail -5
```
- Confirm YAML parses cleanly
- Confirm added lines are inside the Phase 1 Read section of pb-design prompt (not elsewhere)
- Confirm existing pb-design behavior for catalog runs is unchanged (no new required reads)

---

### Phase 6 — Prototype Fast Integration

**Goal:** Prototype (Fast) also uses the Ingestor, making Figma + custom HTML
work for the faster pipeline too.

13. **`prototype/workflow.yaml`** — add design-ingestor step before
    `prototype-specify` with same `condition: source_type in ['html','figma']`

14. **`prototype-specify/AGENT.md`** — add Figma reading guide (same 3 lines
    as pb-design above): when `template/figma/` exists, read frames visually.

**Verification for Phase 6:**
```bash
cd backend
python -c "import yaml; yaml.safe_load(open('agents/workflows/prototype/workflow.yaml'))" && echo "YAML valid"
uv run pytest --collect-only -q 2>&1 | tail -5
uv run pytest tests/unit/ tests/integration/ -q --no-header
# SC-001 checks:
grep -rn "if pipeline_type ==" agents/execution_engine/ | wc -l  # must be 0
grep -rn 'spec\.id ==' agents/execution_engine/ | wc -l           # must be 0
```
- Confirm design-ingestor step added to prototype (Fast) YAML with same condition
- Confirm `prototype-specify/AGENT.md` addition is in the Sandbox Reading Guide section
- Confirm SC-001 invariant still holds (zero pipeline-name branches in engine)

---

### Phase 7 — Frontend Alignment

**Goal:** Wizard correctly signals `source_type` to the backend at launch.

15. **`LaunchWizard.tsx`** — add `source_type` to the draft:
    - `"catalog"` when a template / DS is selected
    - `"html"` when `customTemplateBody` is set
    - `"figma"` when `figmaFrames.length > 0`

16. **`LaunchWizard.tsx`** — when `source_type = "figma"`:
    - DS step already hidden (done in current branch)
    - Template step shows Figma upload zone (done in current branch)

17. **`page.tsx`** — pass `source_type` in the launch payload so
    `launch_context.py` receives it explicitly (rather than inferring it
    from manifest.json contents).

**Verification for Phase 7:**
```bash
cd frontend
npm run build
npx vitest run src/components/workflow/LaunchWizard.figma.test.tsx --reporter=verbose
npx vitest run src/components/workflow/prototype/TemplateGallery.reskin.test.tsx --reporter=verbose
npx eslint src/components/workflow/LaunchWizard.tsx src/app/\\[...view\\]/page.tsx
```
- Confirm `source_type` is included in the draft payload for all three modes
- Confirm existing catalog launch tests are unaffected
- Confirm `source_type="figma"` only set when `mode === "prototype_v2"` and `figmaFrames.length > 0`

---

| Component | Status |
|---|---|
| `od_loader.py` — catalog template disk reads | Unchanged |
| `od_context.py :: load_prototype_context()` — catalog path | Unchanged |
| `od_context_sandbox.py :: write_od_context_to_sandbox()` — catalog writes | Unchanged |
| `opendesign.py` context provider — catalog injection | Unchanged |
| `prototype-specify` AGENT.md — catalog reading | Unchanged |
| `pb-spec`, `fi-readers`, `fi-synth` — document pipeline | Unchanged |
| All existing characterization goldens (INV-3) | Unchanged |
| Execution engine (engine.py) | Unchanged (SC-001) |
| DB schema | Unchanged (no migration) |
| `run_figma_frames.py` — frame upload endpoint | Unchanged |

---

## 6. Tests to Write

New test files agents must create alongside implementation. Follows the workspace test layout standard (mirroring package path, `__init__.py` in every new folder).

---

### 6.1 Unit Tests — Phase 1 (source_type detection + sandbox writes)

**File:** `tests/unit/test_design_ingestion_source_type.py`
**Marker:** `@pytest.mark.unit`  **I/O:** zero (mock sandbox, no DB)

| Test | What it asserts |
|---|---|
| `test_source_type_catalog_when_template_id_in_catalog` | `resolve_launch_od_context` with valid catalog `template_id` → `od_context["source_type"] == "catalog"` |
| `test_source_type_html_when_custom_template_body_set` | `custom_template_body="<html>..."` → `od_context["source_type"] == "html"` |
| `test_source_type_figma_when_manifest_has_image_entries` | `.uploads/manifest.json` has `type="image"` entries → `od_context["source_type"] == "figma"` |
| `test_source_type_defaults_catalog_no_custom` | No custom body, no figma entries → `source_type == "catalog"` |
| `test_selections_json_includes_source_type_field` | `_write_od_context_to_sandbox` with `source_type="html"` → written `selections.json` contains `"source_type": "html"` |
| `test_selections_json_includes_figma_frame_count` | `source_type="figma"`, `figma_frame_count=3` → written JSON has `"figma_frame_count": 3` |
| `test_rebuild_reads_source_type_back` | `rebuild_od_context_from_sandbox` on sandbox with `source_type="figma"` in `selections.json` → `source_type == "figma"` |
| `test_rebuild_backward_compat_no_source_type_field` | Old `selections.json` with no `source_type` field → `rebuild_od_context_from_sandbox` returns `source_type=None` without error |
| `test_load_figma_ingest_context_returns_correct_shape` | `load_figma_ingest_context(frame_count=5)` → dict has `source_type="figma"`, `template_id="custom-figma"`, `ds_id="derived"`, `figma_frame_count=5` |
| `test_load_figma_ingest_context_no_od_loader_call` | `load_figma_ingest_context()` does NOT call `od_loader.get_template()` or `od_loader.get_design_system()` |

---

### 6.2 Unit Tests — Phase 4 (OpenDesign provider)

**File:** `tests/unit/test_opendesign_provider_source_type.py`
**Marker:** `@pytest.mark.unit`  **I/O:** zero (mock ctx)

| Test | What it asserts |
|---|---|
| `test_figma_block_emitted_when_source_type_figma_and_frames_exist` | Provider with `source_type="figma"` + `frames.json` exists in sandbox → `"FIGMA DESIGN REFERENCE"` key in returned blocks |
| `test_figma_block_absent_when_source_type_catalog` | `source_type="catalog"` → no `"FIGMA DESIGN REFERENCE"` key |
| `test_figma_block_absent_when_no_frames_json` | `source_type="figma"` but no `frames.json` → no `"FIGMA DESIGN REFERENCE"` key (graceful degrade) |
| `test_ds_block_still_emitted_alongside_figma_block` | `source_type="figma"` + DS body present → BOTH `"ACTIVE DESIGN SYSTEM"` AND `"FIGMA DESIGN REFERENCE"` keys present |
| `test_catalog_provider_output_byte_identical` | `source_type="catalog"` → output identical to current behavior (INV-3 guard) |
| `test_html_source_type_no_figma_block` | `source_type="html"` → no `"FIGMA DESIGN REFERENCE"`, normal DS + SKILL injection |

---

### 6.3 Integration Tests — Phase 1 (sandbox write chain)

**File:** `tests/integration/api/test_design_ingestor_sandbox.py`
**Marker:** `@pytest.mark.integration`  Uses: real sandbox (tmpdir), no LLM

| Test | What it asserts |
|---|---|
| `test_catalog_sandbox_write_unchanged` | Full catalog launch → `selections.json` matches pre-existing schema exactly (backward compat) |
| `test_html_source_type_written_to_selections_json` | Launch with `custom_template_body` → `selections.json` has `source_type="html"`, `raw-upload.html` exists at `.context/design/template/raw-upload.html` |
| `test_figma_source_type_written_to_selections_json` | Launch with figma frames in manifest → `selections.json` has `source_type="figma"`, `figma_frame_count` matches |
| `test_context_already_present_false_before_ingestor` | Fresh Figma sandbox → `context_already_present()` returns False |
| `test_context_already_present_true_after_selections_written` | After minimal figma od_context written → `context_already_present()` returns True |
| `test_revision_run_does_not_overwrite_figma_context` | Revision run on sandbox where `selections.json` exists → `write_od_context_to_sandbox` skips write (inheritance guard) |
| `test_rebuild_od_context_from_figma_sandbox` | Write figma od_context → `rebuild_od_context_from_sandbox` returns dict with correct `source_type`, `figma_frame_count`, and `template_body=None` |
| `test_figma_od_context_sandbox_writes_only_selections` | `write_od_context_to_sandbox` with figma od_context → writes ONLY `selections.json`; does NOT write `template/SKILL.md` or `design-system.md` (Ingestor owns those) |

---

### 6.4 Integration Tests — Phase 3 (Figma ingest context chain)

**File:** `tests/integration/agents/test_figma_ingest_context_chain.py`
**Marker:** `@pytest.mark.integration`  Uses: real sandbox (tmpdir), no LLM

| Test | What it asserts |
|---|---|
| `test_figma_manifest_triggers_ingest_context_not_catalog` | Manifest with `type="image"` → `resolve_launch_od_context` returns `source_type="figma"`, never calls `od_loader.get_template()` |
| `test_figma_od_context_has_no_template_body` | `load_figma_ingest_context()` → `template_body is None` |
| `test_figma_frame_count_from_manifest` | Manifest with 5 image entries → `figma_frame_count=5` |
| `test_mixed_manifest_counts_only_image_entries` | 3 PDF docs + 2 PNG images → `figma_frame_count=2` |
| `test_existing_figma_frame_upload_tests_unaffected` | Re-run `tests/integration/api/test_figma_frames_api.py` — all 12 pass |

---

### 6.5 Integration Tests — Phases 2 & 3 (prompt file + YAML validation)

**File:** `tests/integration/agents/test_ingestor_prompt_structure.py`
**Marker:** `@pytest.mark.integration`  Uses: disk reads only, no LLM, no DB

| Test | What it asserts |
|---|---|
| `test_html_ingestor_agent_md_exists` | `backend/agents/prompts/design-ingestor-html/AGENT.md` exists on disk |
| `test_figma_ingestor_agent_md_exists` | `backend/agents/prompts/design-ingestor-figma/AGENT.md` exists on disk |
| `test_html_ingestor_step_in_prototype_v2_yaml` | `prototype_v2/workflow.yaml` has step with `instance_id: design-ingestor-html` |
| `test_html_ingestor_step_in_prototype_yaml` | `prototype/workflow.yaml` has step with `instance_id: design-ingestor-html` |
| `test_figma_ingestor_step_in_prototype_v2_yaml` | `prototype_v2/workflow.yaml` has step with `instance_id: design-ingestor-figma` |
| `test_html_ingestor_step_has_source_type_condition` | YAML step condition references `source_type` and `html` |
| `test_figma_ingestor_step_has_source_type_condition` | YAML step condition references `source_type` and `figma` |
| `test_both_ingestor_steps_have_read_write_tools` | Both steps declare `read_files: true`, `write_files: true`, `exec: false` |
| `test_figma_ingestor_step_before_fi_planner` | In `prototype_v2` YAML, `design-ingestor-figma` appears before `fi-planner` |
| `test_figma_ingestor_prompt_mentions_uploads_path` | `design-ingestor-figma/AGENT.md` content contains `.uploads/manifest.json` |
| `test_figma_ingestor_prompt_mentions_context_design_outputs` | AGENT.md mentions `.context/design/template/SKILL.md`, `.context/design/template/example.html`, `.context/design/design-system.md` |
| `test_html_ingestor_prompt_mentions_raw_upload_input` | `design-ingestor-html/AGENT.md` mentions `.context/design/template/raw-upload.html` |
| `test_html_ingestor_prompt_mentions_example_html_output` | AGENT.md mentions `write_file .context/design/template/example.html` |

---

### 6.6 Regression Tests — must remain green across all phases

These already exist. Every phase's verification must confirm they still pass.

| Existing test file | What it guards |
|---|---|
| `tests/integration/api/test_figma_frames_api.py` | 12 frame upload endpoint tests (current branch) |
| `tests/unit/test_od_loader_profile.py` | Catalog od_loader unchanged |
| `tests/unit/test_upload_html.py` | Custom HTML upload path unchanged |
| `tests/agents/test_characterization_*.py` | INV-3 — golden byte-identity for all existing runs |
| `tests/unit/test_banned_patterns.py` | SC-001 — 11 tests, zero pipeline-name branches in engine |
| `tests/unit/test_sse_cutover_banned_patterns.py` | 5 retired WS tokens still absent |
| `frontend: LaunchWizard.figma.test.tsx` | 6 wizard Figma tests (current branch) |
| `frontend: TemplateGallery.reskin.test.tsx` | Existing gallery tests (tab count = 9) |
| `frontend: FigmaUploadSection.test.tsx` | 12 component tests (current branch) |

---

## 7. File Change Summary

```
NEW files:
  backend/agents/prompts/design-ingestor-html/AGENT.md
  backend/agents/prompts/design-ingestor-figma/AGENT.md

MODIFIED files:
  backend/app/api/launch_context.py          ← source_type detection
  backend/agents/execution_engine/od_context.py  ← load_figma_ingest_context()
  backend/app/services/od_context_sandbox.py ← source_type in selections.json
  backend/agents/capabilities/context_providers/opendesign.py  ← figma block
  backend/agents/workflows/prototype_v2/workflow.yaml  ← ingestor step + pb-design
  backend/agents/workflows/prototype/workflow.yaml     ← ingestor step
  backend/agents/prompts/prototype-specify/AGENT.md    ← figma reading guide
  frontend/src/components/workflow/LaunchWizard.tsx    ← source_type in draft
  frontend/src/app/[...view]/page.tsx                  ← source_type in payload
```

Total: **2 new files, 9 modified files.**

---

## 8. New Agents Required

Exactly two new agent prompt files are needed. Everything else is additions
to existing files.

### `design-ingestor-html` (new)
- **Location:** `backend/agents/prompts/design-ingestor-html/AGENT.md`
- **Kind:** `single_shot` custom-agent step in workflow YAML (same pattern
  as `fi-planner`, `pb-spec`, `pb-design` in `prototype_v2/workflow.yaml`)
- **Tools needed:** `read_files: true`, `write_files: true`, `exec: false`
- **No new Python class, no capability registration, no DB entry**
- Runs ONLY when `source_type = "html"` (condition in YAML)
- For catalog runs: step is skipped entirely — zero impact

### `design-ingestor-figma` (new)
- **Location:** `backend/agents/prompts/design-ingestor-figma/AGENT.md`
- **Kind:** `single_shot` custom-agent step in workflow YAML
- **Tools needed:** `read_files: true`, `write_files: true`, `exec: false`
- **Model:** must be vision-capable (all 5 catalog models have `vision=True`)
- **No new Python class, no capability registration, no DB entry**
- Runs ONLY when `source_type = "figma"` (condition in YAML)
- For catalog runs: step is skipped entirely — zero impact

### What does NOT need a new agent

| Component | Change type |
|---|---|
| `prototype-specify` | 3 lines added to existing prompt |
| `pb-design` (Architect) | 3 lines added to existing prompt |
| `fi-planner` | Already patched in current branch |
| `fi-readers` | No change — already handles PNGs natively |
| `opendesign.py` provider | ~10 lines added to existing file |
| `od_context.py` | ~20 lines: new `load_figma_ingest_context()` function |
| `launch_context.py` | ~15 lines: `source_type` detection |

---

## 9. Figma Export Formats — Supported Ingestion Sources

Based on official [Figma developer docs](https://developers.figma.com/docs/plugins/api/ExportSettings/).

| Format | Extension | How user gets it | Supported | Notes |
|---|---|---|---|---|
| PNG frames | `.png` | Right-click frame → Export → PNG | ✅ Phase 1 (done) | Best. Vision-capable, lossless |
| JPG frames | `.jpg` | Right-click frame → Export → JPG | ✅ Phase 1 (done) | Acceptable alternative |
| PDF (all frames) | `.pdf` | File → Export all frames to PDF | ✅ Now (existing V2 doc pipeline) | Each frame = one PDF page |
| SVG frames | `.svg` | Right-click frame → Export → SVG | ⚠️ Future | Structurally rich but verbose for LLMs |
| Figma File JSON | via REST API | Requires personal access token | 🔲 Phase 2 (future) | Richest: node tree, tokens, components |
| Design Tokens JSON | via plugin/REST API | Plugin export or REST `/variables` | 🔲 Phase 2 (future) | Feeds `design-system.md` directly |
| HTML (plugin-generated) | `.html` | Third-party plugins (figma2html etc.) | ✅ Routes through Custom HTML path | Not native Figma — poor quality HTML |
| `.fig` native binary | `.fig` | Not user-accessible for download | ❌ Never | Proprietary protobuf, no parser |
| Video (MP4/GIF/WebM) | `.mp4` `.gif` `.webm` | Animated frames only | ❌ Not useful | Video, not layout reference |

**Key point:** Figma has NO native HTML export. The HTML path is for
user-uploaded HTML only (custom template), not Figma output.

---

## 10. Invariant Compliance

| Invariant | Satisfied by |
|---|---|
| SC-001 (no pipeline names in kernel) | Ingestor is a workflow step, not engine code |
| INV-3 (golden byte-identity) | `source_type="catalog"` path is unchanged; new code only runs for html/figma |
| INV-1 (name-free kernel) | All branching is in `launch_context.py` (app layer) |
| IDOR / auth | `run_figma_frames.py` already enforces two-layer owner check |
| No new DB migrations | Everything is sandbox file I/O |
| import-linter | Ingestor AGENT.md is prompt-only; `od_context.py` imports only `od_loader` |

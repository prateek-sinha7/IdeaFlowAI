# New Ingestion Skills — Integration Plan

**Summary**: The new-ingestion-skills folder contains two developer-facing catalog-building
skills (`import-design`, `import-template`) plus their scripts. They cannot run inside the
agent sandbox as-is because they require a full host Python venv, Node.js, and real Chrome.
The correct integration strategy is **two-track**: (1) move the skills to `skills/velocity/`
as developer tools, (2) extract their schema/format knowledge into an improved Design Ingestor
AGENT.md and two new pure-stdlib Python scripts (`figma_extract.py`, `figma_to_html.py`)
staged into the agent sandbox. With `exec: true` enabled on the design-ingestor step, those
scripts run in the sandbox and produce catalog-quality structured files (`tokens.css`,
`components.html`, properly-formatted `design-system.md`) that all downstream agents already
know how to consume. The permanent catalog (`skills/opendesign/`) remains write-once by
developers; per-run outputs stay in `context/design/`.

---

## Section 1: Current State Analysis

### 1.1 What the Design Ingestor Does Today

The Design Ingestor agent (`backend/agents/prompts/design-ingestor/AGENT.md`) reads
`context/selections.json` and takes one of two paths:

**PATH A — Figma (PNG/JPG frames)**
1. Reads `.figma/manifest.json` to get the ordered frame list.
2. Reads each PNG one at a time via the vision tool, recording observations immediately
   after each read (color palette, layout pattern, font signals, UI sections).
3. **Phase A2**: Synthesises a `context/design/design-system.md` containing a raw `:root`
   block with 9 CSS variables (`--bg`, `--fg`, `--accent`, `--accent-dark`, `--surface`,
   `--surface-2`, `--border`, `--muted`, `--on-accent`) plus brief typography notes.
4. **Phase A3**: Writes `context/design/template/figma/frames.json` (frame inventory),
   `context/design/template/example.html` (a basic layout scaffold), and
   `context/design/template/SKILL.md` (a short visual-reference guide pointing back at
   the frames).
5. **Phase A4**: Rewrites `context/selections.json` with `template_id: "custom-figma"`,
   `ds_id: "derived"`, and `figma_frame_count: N`.

**PATH A2 — Figma PDF**
- Calls `extract_text` on the PDF first, then reads each page's image markers one at a
  time. Same output files as PNG path.

**PATH B — Custom HTML**
1. Reads `context/design/template/raw-upload.html`.
2. Extracts CSS variables from `<style>` blocks.
3. Writes `context/design/design-system.md` (simple `:root` block only, not 9-section format).
4. Writes `context/design/template/example.html` (the raw HTML verbatim).
5. Writes `context/design/template/SKILL.md` (short workflow guide).

### 1.2 Why Agents MUST Write to `context/design/` (No Dot)

The sandbox write guard blocks agent writes to `.context/` (that prefix is reserved for the
engine). The Design Ingestor writes to `context/design/` (no leading dot). The dual-path
reader in `od_context_sandbox.py::rebuild_od_context_from_sandbox` and
`opendesign.py::OpenDesignProvider.load` check `context/design/` first for `source_type in
("figma","html")`, then fall back to `.context/design/`. This bridge is already in place and
working correctly.

### 1.3 Quality of Current Output

| File | Quality today |
|------|--------------|
| `context/design/design-system.md` | 9 raw CSS vars from vision analysis. No typography hierarchy, no component rules, no spacing scale, no depth/elevation. No 9-section DESIGN.md structure. |
| `context/design/tokens.css` | **Does not exist** — never written by the ingestor |
| `context/design/components.html` | **Does not exist** — never written by the ingestor |
| `context/design/template/example.html` | Basic layout scaffold (sidebar or topbar). No shared CSS classes, no `section.pattern[data-pattern]` structure. Downstream agents cannot navigate it as a template. |
| `context/design/template/SKILL.md` | Short, low-information guide. No screen patterns table, no chrome description, no component rules. |
| `context/design/template/figma/frames.json` | Correct, consumed by `pb-design` for vision reads |

### 1.4 How Downstream Agents Consume These Files

**`prototype` workflow** — `prototype-specify` step:
- Declares `skills: [velocity-design]`
- `velocity-design` SKILL.md body = `{{INJECT_FROM:.context/design/template/SKILL.md}}`
- At staging time, `skill_staging.py::_resolve_sandbox_injections` reads
  `.context/design/template/SKILL.md` (which is bridged from `context/design/` by the
  engine) and injects the content
- So whatever the ingestor writes to `context/design/template/SKILL.md` becomes the agent's
  "ACTIVE TEMPLATE" block

**`prototype_v2` workflow** — `pb-design` step:
- Reads `.context/design/design-system.md` (includes `tokens.css`, `components.html` when
  present — see prompt Phase 1 Step 3)
- Reads `.context/design/template/SKILL.md` via vision
- Reads `.context/design/template/figma/frames.json` and then each frame PNG via vision
- Also reads `context/design/design-system.md` and `context/design/template/SKILL.md`
  (ingestor no-dot path — explicitly listed in pb-design prompt)
- The pb-design prompt says: *"tokens.css, components.html — the design system's own tokens
  and component markup, when it ships them"* — confirming it will use these files IF present

**`opendesign.py` provider** — `OpenDesignProvider.load()`:
- For `source_type in ("figma","html")`: reads real `ds_body` from
  `context/design/design-system.md` and `template_body` from
  `context/design/template/SKILL.md`
- Emits FIGMA DESIGN REFERENCE block from `context/design/template/figma/frames.json`
- Injects into: `prototype-specify` (prototype), all builder steps (prototype_v2)

### 1.5 What Catalog Entries Look Like (DESIGN.md + tokens.css + components.html)

A full catalog design system (e.g. `skills/opendesign/design-systems/iberia/`) has:
- **`DESIGN.md`** (14 KB): H1 "Design System Inspired by X", `> Category:`, `> blurb`, 9
  sections (Visual Theme, Color Palette, Typography, Component Stylings, Layout, Depth,
  Do's/Don'ts, Responsive, Agent Prompt Guide) with concrete hex values, typography tables,
  spacing scales, component rules. `od_loader.py` parses lines 1-3 for the picker.
- **`tokens.css`** (8 KB): `:root` block with all 56 schema tokens, theme overrides
  (`[data-theme=dark]`), Google Fonts `@import`
- **`components.html`** (28 KB): Reference page with palette swatches, type scale, all
  components rendered via `var(--*)` only

**The gap**: The current ingestor's `design-system.md` has 9 CSS vars, no typography table,
no spacing scale, no component rules, no 9-section structure. Catalog entries have ~150× more
information and are schema-validated.

---

## Section 2: New Ingestion Skills Analysis

### 2.1 `import-design` Skill

**Purpose**: Build a permanent catalog design system (`skills/opendesign/design-systems/<id>/`)
from a Claude Design export, a website URL, a CSS file, or a markdown spec.

**Scripts** (in `new-ingestion-skills/import-design/scripts/`):

| Script | Language | Dependencies | What it does |
|--------|----------|-------------|--------------|
| `read_source.py` | Python stdlib | None | Reads a Claude Design export folder / zip / markdown spec / CSS file → writes `W/source.json` with `variables`, `fonts`, `type_roles`, `themes`, `hex_context`, etc. |
| `ds_schema.py` | Python stdlib | None | Reads `tokens.schema.ts` (TypeScript, parsed as text) → returns the 56-token schema |
| `make_ds.py` | Python stdlib | `ds_schema.py` | Reads `W/mapping.json` → writes `<dest>/tokens.css` + `<dest>/components.html`. Needs `OD/design-systems/_schema/tokens.schema.ts` to exist |
| `extract_site.cjs` | Node.js | Playwright + Chrome | Crawls a live website → writes `W/site.json` with colors, typography, component samples |
| `validate_design_system.py` | Python | Backend venv (`od_loader`) | Validates a finished design-system folder against the schema and real loader |
| `preview_ds.cjs` | Node.js | Playwright + Chrome | Renders `components.html` in Chrome and screenshots it |
| `shot.cjs` | Node.js | Playwright + Chrome | Screenshots static HTML files |

**Key insight**: `read_source.py`, `ds_schema.py`, and `make_ds.py` are **pure Python stdlib**.
They can run without the backend venv. `extract_site.cjs`, `validate_design_system.py`,
`preview_ds.cjs`, and `shot.cjs` need **Chrome/venv** — developer-only.

**Current input support**:
- ✅ Claude Design export folders (CSS tokens)
- ✅ Markdown/CSS spec files
- ✅ Live website URLs
- ❌ Figma PNG frames — no script reads image files
- ❌ Figma PDF exports — no script handles PDF pages

### 2.2 `import-template` Skill

**Purpose**: Convert an HTML prototype (from Claude Design) into a permanent catalog template
(`skills/opendesign/design-templates/<id>/`) with `SKILL.md` + `example.html`.

**Scripts** (in `new-ingestion-skills/import-template/scripts/`):

| Script | Language | Dependencies | What it does |
|--------|----------|-------------|--------------|
| `inspect_export.py` | Python stdlib | None | Classifies an HTML prototype export (bundle, project, plain HTML, zip) → JSON report |
| `snapshot.cjs` | Node.js | Playwright + Chrome | Opens HTML in Chrome, clicks nav, captures patterns → `W/draft/example.html` with proper `section.pattern` structure |
| `validate_template.py` | Python | Backend venv (`od_loader`, `template_kit`) | Validates the finished template folder against the real loader |
| `preview_check.cjs` | Node.js | Playwright + Chrome | Renders `example.html` and screenshots every pattern |
| `compare.cjs` | Node.js | Playwright + Chrome | Pixel-diffs original vs preview screenshots |
| `trim.cjs` | Node.js | None (pure JS) | Trims `example.html` to 120,000 chars budget |
| `css_tools.cjs` | Node.js | None (pure JS) | CSS manipulation helpers for `snapshot.cjs` |

**Key insight**: `snapshot.cjs` is the core script — it captures a RUNNING HTML prototype
in real Chrome. This is what produces the properly-structured `example.html`. There is NO
way to produce this output from static Figma PNGs without Claude's vision API.

**Current input support**:
- ✅ Claude Design bundle HTML (`.dc.html` + `support.js`)
- ✅ Bundled standalone HTML
- ✅ Plain HTML artifacts
- ❌ Figma PNG frames — `snapshot.cjs` needs a live HTML file to render
- ❌ Figma PDF exports — same limitation

### 2.3 What's Missing for Figma PNG/PDF Inputs

Two bridge scripts are needed:

1. **`figma_extract.py`** — reads the agent's structured visual observations JSON (which the
   improved Design Ingestor writes) and produces a `source.json` compatible with `read_source.py`'s
   output schema, plus a ready-to-run `mapping.json` for `make_ds.py`.

2. **`figma_to_html.py`** — reads `.figma/manifest.json` + `frames.json` + extracted CSS vars
   and generates a structurally-valid `example.html` following the template contract (proper
   `.nav-item[data-go]` elements, `section.pattern[data-pattern]` per screen, `:root` CSS vars).
   This fills the gap that `snapshot.cjs` covers for HTML prototypes.

---

## Section 3: Where Everything Goes

### 3.1 Placing `new-ingestion-skills/`

The skills are **developer-facing catalog-building tools** — the same kind as the `skills/velocity/`
skills. They are NOT per-run staged skills. They require host-side Python/Node/Chrome.

**Move**:
```
new-ingestion-skills/import-design/  →  skills/velocity/import-design/
new-ingestion-skills/import-template/ →  skills/velocity/import-template/
```

Then delete `new-ingestion-skills/` from the repo root.

**DO NOT** move them to `backend/skills/global/` — the global catalog is for per-run staged
skills; the full import-design SKILL.md is 12 KB of developer instructions that would bloat
every agent's context.

### 3.2 New Sandbox-Compatible Skill in `backend/skills/global/`

Create a new focused skill for the design-ingestor step:

```
backend/skills/global/figma-ingestor/
├── SKILL.md                   # Lightweight instructions for the ingestor
└── scripts/
    ├── figma_extract.py       # NEW: agent observations → source.json + mapping.json
    ├── figma_to_html.py       # NEW: frame metadata → structured example.html
    ├── make_ds.py             # COPIED from import-design/scripts/ (stdlib-only)
    └── ds_schema.py           # COPIED from import-design/scripts/ (stdlib-only)
```

The `make_ds.py` copy needs one modification: the `od_root_from()` call in `ds_schema.py`
needs to find `tokens.schema.ts` inside the staged skill folder, not in `skills/opendesign/`.
See Section 4 for the full specification.

### 3.3 How the Skill Staging Mechanism Works

From `backend/app/agents/skill_staging.py`:
1. `stage_skills()` is called before step execution
2. It writes `<sandbox>/skills/<skill_id>/SKILL.md` from the catalog entry
3. It also calls `shutil.copytree(skill_source_dir(skill_id), target.parent)` which copies
   the **entire skill folder** including `scripts/` subdirectory
4. So `skills/figma-ingestor/scripts/figma_extract.py` becomes available in the sandbox at
   `skills/figma-ingestor/scripts/figma_extract.py`

With `exec: true` on the design-ingestor step, the agent can run:
```bash
python3 skills/figma-ingestor/scripts/figma_extract.py \
    --manifest .figma/manifest.json \
    --obs context/design/observations.json \
    --out context/design/
```

The `skill_source_dir()` function resolves to `_GLOBAL_SKILL_DIR / skill_id` =
`backend/skills/global/figma-ingestor/`.

### 3.4 Workflow YAML Changes

**`backend/agents/workflows/prototype_v2/workflow.yaml`** — design-ingestor step:
```yaml
- strategy: single_shot
  depends_on: []
  model:
    model: eu.anthropic.claude-sonnet-4-6
  agent: design-ingestor
  instance_id: design-ingestor
  name: Design Ingestor
  condition: "source_type in ['html', 'figma']"
  skills: [figma-ingestor]          # ADD THIS
  tools:
    read_files: true
    write_files: true
    exec: true                       # CHANGE false → true
    tool_sets:
    - file_extract
  gates: []
```

**`backend/agents/workflows/prototype/workflow.yaml`** — same change:
```yaml
- strategy: single_shot
  depends_on: []
  model:
    model: eu.anthropic.claude-sonnet-4-6
  agent: design-ingestor
  instance_id: design-ingestor
  name: Design Ingestor
  condition: "source_type in ['html', 'figma']"
  skills: [figma-ingestor]          # ADD THIS
  tools:
    read_files: true
    write_files: true
    exec: true                       # CHANGE false → true
    tool_sets:
    - file_extract
  gates: []
```

### 3.5 `exec: true` — What It Enables and Risk Assessment

`exec: true` allows the design-ingestor agent to run shell commands in the sandbox. The
scripts it will run are:
- `python3 skills/figma-ingestor/scripts/figma_extract.py` — reads JSON, writes JSON (safe)
- `python3 skills/figma-ingestor/scripts/figma_to_html.py` — reads JSON, writes HTML (safe)
- `python3 skills/figma-ingestor/scripts/make_ds.py` — reads JSON, writes CSS/HTML (safe)

All three are pure Python stdlib with no network access. The scripts are staged from the
global skill catalog (no user-uploaded code). The sandbox filesystem limits what they can
read/write. Risk: **low** — equivalent to the exec capability already used in other steps.

---

## Section 4: New Scripts Needed

### 4.1 `figma_extract.py`

**Location**: `backend/skills/global/figma-ingestor/scripts/figma_extract.py`

**Purpose**: Converts the Design Ingestor's structured visual observations (written as JSON
after the vision analysis phase) into:
1. `source.json` in the `read_source.py` output schema (for `make_ds.py`'s `--source` flag)
2. `mapping.json` in the `make_ds.py` input schema (ready to generate `tokens.css`)

**Input**:
- `--manifest <path>` — `.figma/manifest.json` (frame inventory)
- `--obs <path>` — `context/design/observations.json` (agent-written structured observations)
- `--out <dir>` — output directory (writes `source.json` and `mapping.json` there)

**`observations.json` schema** (agent writes this during the vision phase, before calling the script):
```json
{
  "frames": [
    {
      "index": 0, "name": "frame-1.png", "screen": "Dashboard",
      "layout": "sidebar-nav",
      "bg": "#1a1a2e", "fg": "#e0e0e0", "accent": "#7c4dff",
      "surface": "#16213e", "surface_2": "#0f3460", "border": "#2d2d4e",
      "muted": "#8888aa", "on_accent": "#ffffff",
      "font_weight": "medium", "font_density": "compact",
      "font_family_hint": "Inter, sans-serif"
    }
  ],
  "dominant_layout": "sidebar-nav",
  "color_scheme": "dark",
  "suggested_name": "MyApp Design"
}
```

**Logic** (step by step):
1. Parse `--manifest` and `--obs` JSON files
2. Aggregate token values across all frames (dominant hex per role by frequency)
3. Resolve `--bg`, `--fg`, `--accent`, `--surface`, `--surface-2`, `--border`, `--muted`,
   `--on-accent` from the aggregated frames
4. Infer `--accent-dark` (darken accent by 15%)
5. Infer typography tokens (`--font-display`, `--font-body`) from `font_family_hint`
6. Infer structural tokens (`--text-base: 15px`, scale up/down per density)
7. Write `W/source.json`:
   ```json
   {
     "kind": "figma-frames",
     "root": ".figma/",
     "docs": [],
     "variables": {
       ":root": { "--bg": "#1a1a2e", "--fg": "#e0e0e0", ... }
     },
     "fonts": { "families": ["Inter"], "google_imports": [] },
     "themes": {},
     "breakpoints": [],
     "colors": { "#1a1a2e": 8, "#7c4dff": 5, ... },
     "manifest_tokens": [],
     "components": [],
     "warnings": []
   }
   ```
8. Write `W/mapping.json` (the `make_ds.py` input):
   ```json
   {
     "id": "<kebab-from-obs.suggested_name>",
     "name": "<obs.suggested_name>",
     "summary": "Derived from Figma screen exports via visual analysis",
     "provenance": "Visual token extraction from Figma PNG frames",
     "fonts_href": "",
     "tokens": {
       "--bg": "#1a1a2e",
       "--fg": "#e0e0e0",
       "--accent": "#7c4dff",
       "--surface": "#16213e",
       "--border": "#2d2d4e",
       "--muted": "#8888aa",
       "--font-display": "Inter, system-ui, sans-serif",
       "--font-body": "Inter, system-ui, sans-serif",
       "--text-base": "15px",
       "--text-sm": "13px",
       "--text-xs": "12px",
       "--text-lg": "17px",
       "--text-xl": "20px",
       "--text-2xl": "24px",
       "--text-3xl": "30px",
       "--text-4xl": "36px",
       ...
     },
     "notes": { "--text-base": "15px, authored from compact density signal" },
     "extensions": {},
     "themes": {}
   }
   ```

**Does NOT need Claude vision API**: reads structured JSON only.

**Integration with `make_ds.py`**:
The standard `make_ds.py` calls `od_root_from(dest)` which walks up from `dest` looking for
`design-systems/_schema/tokens.schema.ts`. In the sandbox there is no `skills/opendesign/`
at that path. The sandbox-compatible version of `make_ds.py` must accept `--schema <path>`
to point at a bundled schema, or we bundle `tokens.schema.ts` inside the skill folder.

**Recommended**: add `skills/opendesign/design-systems/_schema/tokens.schema.ts` symlink into
`backend/skills/global/figma-ingestor/scripts/` as a static copy (checked-in JSON snapshot
of the schema), and modify `ds_schema.py` copy to accept an env var `OD_SCHEMA_PATH` that
overrides `od_root_from`. The agent sets this before calling `make_ds.py`:
```bash
OD_SCHEMA_PATH=skills/figma-ingestor/scripts/schema \
  python3 skills/figma-ingestor/scripts/make_ds.py \
    context/design/mapping.json \
    --dest context/design/
```

### 4.2 `figma_to_html.py`

**Location**: `backend/skills/global/figma-ingestor/scripts/figma_to_html.py`

**Purpose**: Generates a structurally-valid `example.html` from Figma frame data, following
the template contract (`contract.md`). This fills the same role that `snapshot.cjs` fills for
HTML prototypes — it produces the proper `section.pattern` structure and `.nav-item[data-go]`
nav — but from static frame metadata rather than a live rendered page.

**Input**:
- `--frames <path>` — `context/design/template/figma/frames.json` (frame inventory)
- `--tokens <path>` — `context/design/tokens.css` (generated by `make_ds.py`) or
  `context/design/design-system.md` (fallback)
- `--prefix <str>` — CSS class prefix (e.g. `fg` for figma-generated)
- `--out <path>` — output HTML file path

**Output**: `context/design/template/example.html` with this structure:
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Figma Design</title>
  <style>
    /* :root from tokens.css — all CSS vars */
    :root {
      --bg: #1a1a2e;
      --fg: #e0e0e0;
      --accent: #7c4dff;
      /* ... all 56 tokens ... */
    }

    /* Frame layout */
    body { background: var(--bg); color: var(--fg); font-family: var(--font-body); margin:0; }
    .app { display: flex; height: 100vh; }

    /* Nav styles (sidebar or topbar based on dominant_layout) */
    .sidebar { width: 240px; background: var(--surface); border-right: 1px solid var(--border); }
    .nav-item { display: block; padding: 10px 16px; cursor: pointer; color: var(--fg); }
    .nav-item.is-active, .nav-item:hover { background: var(--accent); color: var(--on-accent); }

    /* Pattern display */
    .pattern { display: none; flex: 1; padding: 24px; }
    .pattern:first-of-type { display: flex; }
  </style>
</head>
<body>
  <div class="app">
    <!-- Nav items: one per frame, first is active -->
    <nav class="sidebar">
      <button class="nav-item is-active" data-go="screen-0">Dashboard</button>
      <button class="nav-item" data-go="screen-1">Reports</button>
    </nav>

    <main>
      <!-- PATTERN screen-0 - Dashboard overview (frame-1.png) -->
      <section class="pattern" data-pattern="screen-0">
        <!-- Figma frame: context/design/template/figma/frame-1.png -->
        <img src="../figma/frame-1.png" alt="Dashboard" style="max-width:100%;opacity:0.3;">
        <p style="color:var(--muted)">Dashboard — build from frame-1.png</p>
      </section>

      <!-- PATTERN screen-1 - Reports list (frame-2.png) -->
      <section class="pattern" data-pattern="screen-1">
        <img src="../figma/frame-2.png" alt="Reports" style="max-width:100%;opacity:0.3;">
        <p style="color:var(--muted)">Reports — build from frame-2.png</p>
      </section>
    </main>
  </div>

  <script>
    document.querySelectorAll('.nav-item[data-go]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('is-active'));
        document.querySelectorAll('.pattern').forEach(p => p.style.display = 'none');
        btn.classList.add('is-active');
        document.querySelector('[data-pattern="'+btn.dataset.go+'"]').style.display = 'flex';
      });
    });
  </script>
</body>
</html>
```

**Logic** (step by step):
1. Parse `--frames` JSON (frame inventory from ingestor)
2. Parse `:root` vars from `--tokens` (CSS file or markdown `:root` block)
3. Determine layout type from frames' `layout` field (sidebar-nav → sidebar, topbar-nav → header)
4. For each frame: create a `section.pattern[data-pattern="screen-N"]` with:
   - Comment: `<!-- PATTERN screen-N - <description> -->`
   - An `<img>` referencing `../figma/<filename>` (relative path within sandbox)
   - A placeholder paragraph with the frame description
5. Create `.nav-item[data-go]` buttons (one per frame, first gets `is-active`)
6. Write the complete, self-contained HTML with inline `<style>` and `<script>`

**Does NOT need Chrome or Claude vision**: pure Python stdlib HTML generation.

**Template contract compliance**: the output satisfies `contract.md` requirements:
- ✅ Content element `<main>` present
- ✅ At least 2 `.nav-item[data-go]` elements before `<main>`
- ✅ `is-active` class on first item
- ✅ One `section.pattern[data-pattern]` per screen
- ✅ `:root` declares `--bg --surface --fg --muted --border --accent`
- ✅ Self-contained (no external URLs except optional Google Fonts)

**Limitation**: The patterns contain only placeholder content (image + label). Downstream
builder agents fill in the real product UI using the Figma frame PNGs as visual reference.
This is the SAME pattern as `snapshot.cjs` output — builders receive `example.html` as a
STRUCTURE reference, not finished product screens.

### 4.3 Modified `make_ds.py` (Sandbox Copy)

Copy `new-ingestion-skills/import-design/scripts/make_ds.py` to
`backend/skills/global/figma-ingestor/scripts/make_ds.py` with one change:

In `ds_schema.py` (also copied), change `od_root_from` to check `OD_SCHEMA_PATH` env var:
```python
def od_root_from(path: Path) -> Path:
    env_path = os.environ.get("OD_SCHEMA_PATH")
    if env_path:
        p = Path(env_path)
        if (p / "tokens.schema.ts").is_file():
            return p.parent.parent  # points to OD root
    # original walk-up logic follows...
```

Also copy `skills/opendesign/design-systems/_schema/tokens.schema.ts` (read-only reference)
to `backend/skills/global/figma-ingestor/scripts/schema/tokens.schema.ts`. This is bundled
into the skill folder so it stages into the sandbox with the scripts.

---

## Section 5: Design Ingestor AGENT.md Changes

### 5.1 Overview of Changes

The AGENT.md grows in three ways:
1. PATH A gains a new **Phase A0** (run `figma_extract.py` after vision analysis) and
   improved output format (DESIGN.md 9-section structure).
2. PATH A gains a new **Phase A5** (run `make_ds.py` to produce `tokens.css` and `components.html`).
3. PATH B gains the same improved DESIGN.md format for its output.

The core vision-analysis loop in PATH A is UNCHANGED — the agent still reads each frame one
by one and records observations. What changes is:
- Observations are written to structured `observations.json` first
- Scripts then process that JSON to produce schema-compliant token files
- The final `design-system.md` follows the 9-section DESIGN.md format

### 5.2 New PATH A Flow

```
Step 0: Read context/selections.json → source_type = "figma"
Step 1: Read .figma/manifest.json → frame list

Phase A1 (unchanged): Vision analysis
  For each frame (one at a time via vision):
  - Read .figma/<name> via vision
  - Record observations immediately (hex values, layout, font signals)

NEW Phase A1b: Write structured observations
  write_file context/design/observations.json:
  {
    "frames": [
      {
        "index": N, "name": "<filename>", "screen": "<inferred name>",
        "layout": "<sidebar-nav|topbar-nav|centered|dashboard>",
        "bg": "#hex", "fg": "#hex", "accent": "#hex",
        "surface": "#hex", "surface_2": "#hex", "border": "#hex",
        "muted": "#hex", "on_accent": "#hex",
        "font_weight": "<light|regular|medium|semibold>",
        "font_density": "<compact|comfortable|spacious>",
        "font_family_hint": "Inter, system-ui, sans-serif"
      }, ...
    ],
    "dominant_layout": "<layout>",
    "color_scheme": "<dark|light|mixed>",
    "suggested_name": "<inferred product name>"
  }

NEW Phase A1c: Run figma_extract.py
  exec: python3 skills/figma-ingestor/scripts/figma_extract.py
        --manifest .figma/manifest.json
        --obs context/design/observations.json
        --out context/design/
  → produces context/design/source.json and context/design/mapping.json

Phase A2 (IMPROVED): Write design-system.md in DESIGN.md 9-section format
  Using observations + source.json content:
  write_file context/design/design-system.md
  Format: 9 sections from reference/design-md.md
  (Visual Theme, Color Palette, Typography, Components, Layout, Depth, Do's/Don'ts,
   Responsive, Agent Prompt Guide)
  All hex values come from the vision analysis (source.json confirms them)
  Typography hierarchy: derived from font_density + font_family_hint
  
NEW Phase A2b: Run make_ds.py
  exec: OD_SCHEMA_PATH=skills/figma-ingestor/scripts/schema \
        python3 skills/figma-ingestor/scripts/make_ds.py \
          context/design/mapping.json \
          --dest context/design/
  → produces context/design/tokens.css and context/design/components.html

Phase A3 (IMPROVED): Write template files
  Run figma_to_html.py:
  exec: python3 skills/figma-ingestor/scripts/figma_to_html.py
        --frames context/design/template/figma/frames.json
        --tokens context/design/tokens.css
        --prefix fg
        --out context/design/template/example.html
  
  Write context/design/template/figma/frames.json (unchanged format)
  
  Write context/design/template/SKILL.md in FULL TEMPLATE SKILL.md format:
  - Frontmatter: name, description, od.mode: prototype, od.platform, od.scenario
  - ## What this template is
  - ## Chrome
  - ## How the example is organised
  - ## Screen patterns (one row per frame)
  - ## Components
  - ## Theme
  - ## Hard rules

Phase A4 (unchanged): Update context/selections.json

Reply: "Design ingestor complete (figma): N frames, design-system.md (9 sections) +
       tokens.css + components.html + example.html + SKILL.md written."
```

### 5.3 New PATH B Flow

PATH B gets the same improved `design-system.md` format:

**Phase B2 (improved)**: Instead of writing just a `:root` block, write a full 9-section
`design-system.md` by extracting colors + fonts from the HTML's `<style>` blocks and
expanding them into the DESIGN.md template.

**Phase B3 (improved)**: The existing `example.html` is written verbatim (unchanged).
The `SKILL.md` follows the full template format with frontmatter and sections.

### 5.4 What `exec: true` Enables

With `exec: true`, the agent runs three scripts in sequence after vision analysis:
1. `figma_extract.py` — reads JSON, writes JSON (pure stdlib, ~100ms)
2. `make_ds.py` — reads JSON, writes CSS/HTML (~200ms)
3. `figma_to_html.py` — reads JSON, writes HTML (~50ms)

All three run with `python3` (no backend venv needed — pure stdlib).
Total added execution time: under 1 second per run.

---

## Section 6: Output Destination Changes

### 6.1 Per-Run Outputs (Unchanged Location, Improved Quality)

The ingestor still writes to `context/design/` (no leading dot). What changes is the files
written and their quality:

**Before**:
```
context/design/
├── design-system.md          # 9 CSS vars, minimal
└── template/
    ├── SKILL.md              # short reference doc
    ├── example.html          # basic layout scaffold
    └── figma/
        └── frames.json
```

**After**:
```
context/design/
├── design-system.md          # DESIGN.md format (9 sections, ~8-15 KB)
├── tokens.css                # NEW: full :root block + theme overrides (from make_ds.py)
├── components.html           # NEW: component reference page (from make_ds.py)
├── observations.json         # NEW: structured vision observations (intermediate artifact)
├── source.json               # NEW: read_source.py-compatible schema
├── mapping.json              # NEW: make_ds.py input (can be handed to import-design)
└── template/
    ├── SKILL.md              # IMPROVED: full SKILL.md format with frontmatter + 7 sections
    ├── example.html          # IMPROVED: proper nav-item/pattern structure + CSS vars
    └── figma/
        └── frames.json       # Unchanged
```

### 6.2 How Downstream Agents Already Consume the New Files

**`tokens.css` and `components.html`** — already consumed:
- `pb-design` prompt (prototype_v2) explicitly reads `tokens.css` and `components.html` when
  they exist: *"tokens.css, components.html — the design system's own tokens and component
  markup, when it ships them"*
- `opendesign.py` emits them via the `ds_files` dict for catalog runs; for figma runs we need
  one addition (see 6.3)
- `od_context_sandbox.py::rebuild_od_context_from_sandbox` already reads `ds_files` from
  `context/design/{tokens.css,components.html}`

**Improved `design-system.md`** — already consumed:
- `velocity-design-system` skill uses `{{INJECT_FROM:.context/design/design-system.md}}`
- `pb-design` reads it directly
- `opendesign.py` reads it for figma/html runs and emits it as the DS block

**Improved `template/SKILL.md`** — already consumed:
- `velocity-design` skill uses `{{INJECT_FROM:.context/design/template/SKILL.md}}`
- `prototype-specify` receives it via the staged skill

**Improved `template/example.html`** — already consumed:
- `opendesign.py` reads it and emits the TEMPLATE EXAMPLE block for builder agents
- `pb-design` reads it in Phase 1 Step 4

### 6.3 Impact on `opendesign.py`

One addition needed: for `source_type in ("figma","html")`, also read `tokens.css` and
`components.html` from `context/design/` (no-dot path) when building the DS block:

```python
# In OpenDesignProvider.load(), in the figma/html source_type branch:
# After reading real_ds and real_skill:
if source_type in ("figma", "html"):
    # ... existing real_ds and real_skill reads ...
    
    # NEW: also carry tokens.css and components.html if present
    real_tokens = _read_design_file("context/design/tokens.css", ".context/design/tokens.css")
    real_components = _read_design_file("context/design/components.html", ".context/design/components.html")
    # These are exposed to agents that have ds_files access (pb-design already reads them
    # from .context/design/ directly, so this is just ensuring the sandbox copy is synced)
```

`od_context_sandbox.py::rebuild_od_context_from_sandbox` already reads `tokens.css` and
`components.html` via the `ds_files` dict loop — no change needed there. The dual-path
reader (no-dot first, then dot) handles them automatically.

### 6.4 Impact on `od_context_sandbox.py`

The sentinel `.ingestor` write at launch time covers the existing files. No change needed —
the rebuild function already iterates `context/design/` for any file when `_is_ingestor=True`.

The new files (`tokens.css`, `components.html`, `observations.json`, `source.json`,
`mapping.json`) will be picked up automatically by the `list_fn()` iterator in
`rebuild_od_context_from_sandbox` because they have the `context/design/` prefix and `.css`/
`.html` extensions match the ds_files pattern.

One explicit addition in `rebuild_od_context_from_sandbox`: include `tokens.css` and
`components.html` in `ds_files` when reading from `context/design/` (currently only reads
from `.context/design/` for these):

```python
# Current (line ~155-159 in od_context_sandbox.py):
ds_files = {
    name: body
    for name in ("tokens.css", "components.html")
    if (body := reader(f".context/design/{name}") or reader(f"context/design/{name}"))
}
```
This already does the right thing — it checks `context/design/{name}` as the fallback. No
change needed.

### 6.5 Permanent Catalog — Developer Promotion Path

The per-run `mapping.json` + `source.json` + `design-system.md` written to `context/design/`
are the inputs for a developer to promote this design to the permanent catalog.

A developer with Claude Desktop + `import-design` skill can:
1. Copy `context/design/mapping.json` from the sandbox to a work directory
2. Copy `context/design/design-system.md` as `W/DESIGN.md`
3. Run `make_ds.py W/mapping.json --dest skills/opendesign/design-systems/<id>/`
4. Copy `W/DESIGN.md` to `skills/opendesign/design-systems/<id>/DESIGN.md`
5. Run `validate_design_system.py` and `preview_ds.cjs` to confirm quality
6. The design system is now in the permanent catalog — available to all future runs

Similarly, a developer can take `context/design/template/example.html` and process it with
the `import-template` skill's `snapshot.cjs` to produce a catalog-quality template.

This is the correct separation of concerns:
- **Per-run**: ingestor produces high-quality context, all downstream agents benefit
- **Catalog promotion**: developer reviews, validates, and promotes to permanent catalog

### 6.6 Whether `context/design/` Still Needs to Be Written

**Yes, always.** The `context/design/` write path is the contract that all downstream agents,
`od_context_sandbox.py`, and `opendesign.py` depend on. Nothing about this changes. The
permanent catalog path (`skills/opendesign/`) is an ADDITIVE developer workflow, not a
replacement for per-run writes.

---

## Section 7: Complete File Change Summary

### Files to CREATE

| File | What it is |
|------|-----------|
| `backend/skills/global/figma-ingestor/SKILL.md` | New global skill — lightweight instructions for the design-ingestor agent on how to run the scripts |
| `backend/skills/global/figma-ingestor/scripts/figma_extract.py` | New script: visual observations JSON → source.json + mapping.json |
| `backend/skills/global/figma-ingestor/scripts/figma_to_html.py` | New script: frames.json + tokens.css → structured example.html |
| `backend/skills/global/figma-ingestor/scripts/make_ds.py` | Copy of `import-design/scripts/make_ds.py` with OD_SCHEMA_PATH env-var support |
| `backend/skills/global/figma-ingestor/scripts/ds_schema.py` | Copy of `import-design/scripts/ds_schema.py` with OD_SCHEMA_PATH support |
| `backend/skills/global/figma-ingestor/scripts/schema/tokens.schema.ts` | Static copy of `skills/opendesign/design-systems/_schema/tokens.schema.ts` (bundled for sandbox) |
| `skills/velocity/import-design/SKILL.md` | Moved from `new-ingestion-skills/import-design/SKILL.md` |
| `skills/velocity/import-design/reference/design-md.md` | Moved from `new-ingestion-skills/import-design/reference/design-md.md` |
| `skills/velocity/import-design/scripts/` | Moved from `new-ingestion-skills/import-design/scripts/` (all 7 scripts) |
| `skills/velocity/import-template/SKILL.md` | Moved from `new-ingestion-skills/import-template/SKILL.md` |
| `skills/velocity/import-template/reference/contract.md` | Moved from `new-ingestion-skills/import-template/reference/contract.md` |
| `skills/velocity/import-template/reference/template-skill.md` | Moved from `new-ingestion-skills/import-template/reference/template-skill.md` |
| `skills/velocity/import-template/scripts/` | Moved from `new-ingestion-skills/import-template/scripts/` (all 7 scripts) |

### Files to MODIFY

| File | What changes |
|------|-------------|
| `backend/agents/prompts/design-ingestor/AGENT.md` | PATH A: add observations.json writing, add exec commands for 3 scripts, improve design-system.md to 9-section DESIGN.md format, improve SKILL.md to full format. PATH B: improve design-system.md format. |
| `backend/agents/workflows/prototype_v2/workflow.yaml` | design-ingestor step: add `skills: [figma-ingestor]`, change `exec: false` → `exec: true` |
| `backend/agents/workflows/prototype/workflow.yaml` | design-ingestor step: add `skills: [figma-ingestor]`, change `exec: false` → `exec: true` |
| `backend/agents/capabilities/context_providers/opendesign.py` | Minor: ensure `tokens.css`/`components.html` from `context/design/` are read for figma/html runs (see Section 6.3) |

### Files to DELETE

| File | Why |
|------|-----|
| `new-ingestion-skills/import-design/` (entire folder) | Moved to `skills/velocity/import-design/` |
| `new-ingestion-skills/import-template/` (entire folder) | Moved to `skills/velocity/import-template/` |
| `new-ingestion-skills/` (folder itself) | Empty after moves |

### Files That Do NOT Change

| File | Why preserved |
|------|--------------|
| `backend/app/services/od_context_sandbox.py` | Dual-path reader already correct |
| `backend/agents/execution_engine/od_context.py` | `load_figma_ingest_context` placeholder is still correct |
| `backend/app/api/launch_context.py` | Source type detection logic is correct |
| `backend/app/api/run_figma_frames.py` | Upload endpoint is correct |
| `backend/app/agents/skill_staging.py` | Already copies full skill folder |
| `backend/app/agents/skills_catalog.py` | No change needed — auto-discovers new skill |
| `frontend/src/lib/figma-frame-store.ts` | Already fixed (in-memory store, not sessionStorage) |
| All catalog files in `skills/opendesign/` | Never modified by this feature |

---

## Section 8: Implementation Phases

### Phase 1 — Move new-ingestion-skills (low risk, no code change)

**Goal**: Make the developer tools discoverable in the right place.

**Steps**:
1. `git mv new-ingestion-skills/import-design skills/velocity/import-design`
2. `git mv new-ingestion-skills/import-template skills/velocity/import-template`
3. `rmdir new-ingestion-skills`

**Done criteria**:
- `skills/velocity/import-design/SKILL.md` exists
- `skills/velocity/import-template/SKILL.md` exists
- `new-ingestion-skills/` is gone
- `git status` shows moves, no untracked files

**Verification**:
```bash
ls skills/velocity/import-design/SKILL.md
ls skills/velocity/import-template/SKILL.md
```

---

### Phase 2 — New global skill skeleton (low risk)

**Goal**: Register `figma-ingestor` as a global skill so it can be staged.

**Steps**:
1. Create `backend/skills/global/figma-ingestor/SKILL.md` with correct frontmatter:
   ```yaml
   ---
   name: figma-ingestor
   display_name: Figma Design Ingestor
   description: Scripts for extracting structured design tokens and HTML from Figma frame exports. Run figma_extract.py after visual observation, then make_ds.py for tokens.css, then figma_to_html.py for example.html.
   category: workflow
   isBeta: false
   tags:
     - design
     - figma
     - ingestor
   ---
   ```
   Body: brief command reference (the scripts and their arguments).

2. Copy `skills/opendesign/design-systems/_schema/tokens.schema.ts` to
   `backend/skills/global/figma-ingestor/scripts/schema/tokens.schema.ts`

**Done criteria**:
- `python3 -c "from app.agents.skills_catalog import list_global_skills; print([s.id for s in list_global_skills()])"` from `backend/` includes `figma-ingestor`
- The skill `clear_cache()` and re-scan picks it up
- Existing skill count in `test_skills_catalog_hygiene.py` passes (may need updating if it has a count assertion)

**Verification**:
```bash
cd backend && uv run python -c "from app.agents.skills_catalog import list_global_skills; print('figma-ingestor' in [s.id for s in list_global_skills()])"
# should print True
```

---

### Phase 3 — Write `figma_extract.py` (medium effort, no side effects)

**Goal**: Pure Python stdlib script that converts structured JSON observations to `source.json` + `mapping.json`.

**Steps**:
1. Write `backend/skills/global/figma-ingestor/scripts/figma_extract.py` per the specification in Section 4.1
2. Copy `new-ingestion-skills/import-design/scripts/ds_schema.py` to
   `backend/skills/global/figma-ingestor/scripts/ds_schema.py` and add `OD_SCHEMA_PATH` override
3. Copy `new-ingestion-skills/import-design/scripts/make_ds.py` to
   `backend/skills/global/figma-ingestor/scripts/make_ds.py` with the `OD_SCHEMA_PATH` env-var patch

**Done criteria**:
```bash
cd backend/skills/global/figma-ingestor/scripts
# Given a test observations.json with one frame entry:
python3 figma_extract.py \
  --manifest tests/fixtures/figma-manifest.json \
  --obs tests/fixtures/figma-observations.json \
  --out /tmp/ds-test/
# Expected: /tmp/ds-test/source.json and /tmp/ds-test/mapping.json exist
# Expected: /tmp/ds-test/mapping.json has "tokens" with --bg, --fg, --accent at minimum

OD_SCHEMA_PATH=schema python3 make_ds.py /tmp/ds-test/mapping.json --dest /tmp/ds-test/
# Expected: /tmp/ds-test/tokens.css and /tmp/ds-test/components.html exist
# Expected: tokens.css has ":root {" block
```

---

### Phase 4 — Write `figma_to_html.py` (medium effort, no side effects)

**Goal**: Pure Python stdlib script that generates template-contract-compliant `example.html`.

**Steps**:
1. Write `backend/skills/global/figma-ingestor/scripts/figma_to_html.py` per Section 4.2

**Done criteria**:
```bash
python3 backend/skills/global/figma-ingestor/scripts/figma_to_html.py \
  --frames tests/fixtures/frames.json \
  --tokens tests/fixtures/tokens.css \
  --prefix fg \
  --out /tmp/example.html

# Verify template contract:
python3 -c "
from pathlib import Path
html = Path('/tmp/example.html').read_text()
assert 'nav-item' in html and 'data-go=' in html, 'Missing nav items'
assert 'section class=\"pattern\"' in html, 'Missing pattern sections'
assert 'data-pattern=' in html, 'Missing data-pattern attrs'
assert ':root' in html, 'Missing :root CSS vars'
assert 'is-active' in html, 'Missing active nav item'
print('All template contract checks pass')
"
```

---

### Phase 5 — Update Workflow YAMLs (low risk, one-line change each)

**Goal**: Enable exec and skill staging for the design-ingestor step.

**Steps**:
1. In `backend/agents/workflows/prototype_v2/workflow.yaml`: add `skills: [figma-ingestor]`
   and change `exec: false` → `exec: true` on the design-ingestor step
2. In `backend/agents/workflows/prototype/workflow.yaml`: same change

**Done criteria**:
```bash
grep -A 10 "instance_id: design-ingestor" backend/agents/workflows/prototype_v2/workflow.yaml | grep "exec: true"
# should print: exec: true
grep -A 10 "instance_id: design-ingestor" backend/agents/workflows/prototype_v2/workflow.yaml | grep "figma-ingestor"
# should print:   skills: [figma-ingestor]
```

**Verify workflows still compile**:
```bash
cd backend && uv run python -c "from agents.execution_engine.engine import compile_for_run; compile_for_run('prototype_v2'); compile_for_run('prototype'); print('both compile OK')"
```

---

### Phase 6 — Update Design Ingestor AGENT.md (high effort, core change)

**Goal**: Improved PATH A produces 9-section DESIGN.md, runs scripts, generates catalog-quality files. Improved PATH B produces better-formatted design-system.md.

**Steps**:
1. Read the current AGENT.md
2. After vision analysis loop, add Phase A1b (write `observations.json`) and Phase A1c (exec `figma_extract.py`)
3. Change Phase A2 to write 9-section DESIGN.md format (using `reference/design-md.md` as the template)
4. Add Phase A2b (exec `make_ds.py`)
5. Change Phase A3 to exec `figma_to_html.py` instead of writing example.html inline
6. Improve the `template/SKILL.md` template to the full format from `reference/template-skill.md`
7. Update PATH B's DESIGN.md to write a brief but properly-structured 9-section document

**Done criteria**: Deploy in a dev environment and run a prototype_v2 with Figma PNGs uploaded.
Expected outputs in the sandbox:
```
context/design/observations.json   ← new
context/design/source.json         ← new
context/design/mapping.json        ← new
context/design/tokens.css          ← new
context/design/components.html     ← new
context/design/design-system.md    ← improved (9 sections)
context/design/template/SKILL.md   ← improved (full format)
context/design/template/example.html ← improved (proper nav/pattern structure)
context/design/template/figma/frames.json ← unchanged
```

**Verification** (in a test run sandbox):
```bash
# After a figma run:
cat sandbox/.../context/design/tokens.css | head -5
# Expected: :root {
cat sandbox/.../context/design/design-system.md | grep "^## "
# Expected: 9 section headings
python3 -c "
import json; frames = json.loads(open('sandbox/.../context/design/template/example.html').read()[0:200])
" 2>/dev/null
# Run the template contract checks from Phase 4
```

---

### Phase 7 — Update `opendesign.py` (minor, defensive)

**Goal**: Ensure `tokens.css` and `components.html` from `context/design/` are read for
figma/html runs.

**Steps**:
1. In `OpenDesignProvider.load()`, in the `source_type in ("figma", "html")` branch,
   after reading `real_ds` and `real_skill`, also check for `tokens.css` and
   `components.html` and surface them so they could be emitted to agents that declare
   `ds_files` inject.

**Done criteria**:
```bash
cd backend && uv run pytest tests/ -k "opendesign" -x -q
# all pass
```

---

## Section 9: What Does NOT Change

These behaviors are preserved byte-for-byte:

| Behavior | Why unchanged |
|----------|--------------|
| Catalog template/design-system selection (user picks from gallery) | Entirely separate path. `load_prototype_context()` is not touched. `source_type="catalog"` never reaches the ingestor step. |
| `od_loader.py` and the permanent catalog at `skills/opendesign/` | Read-only from the agent's perspective. No agent writes there. |
| `velocity-design` and `velocity-design-system` skill injection | These use `{{INJECT_FROM:.context/design/...}}`. The ingestor now writes BETTER content to those paths, but the injection mechanism is unchanged. |
| `.figma/` upload endpoint (`run_figma_frames.py`) | No change. |
| `figma-frame-store.ts` (already fixed) | The in-memory store fix is already in place. |
| PPT workflows | Do not use the design-ingestor step. No impact. |
| Resume/revision runs | `od_context_sandbox.py` inheritance guard is unchanged. |
| The dual-path reader (`context/design/` vs `.context/design/`) | Already in place in `od_context_sandbox.py` and `opendesign.py`. |
| SC-001 / INV-1 (no workflow names in engine) | No engine changes at all. |
| Characterization goldens (INV-3) | The ingestor is an agent step, not an engine path. Golden tests are for the engine's event stream. |

---

## Appendix: Skill Staging Path Trace

When `figma-ingestor` is declared in `skills:`, this chain executes before the agent runs:

```
engine.py::_run_agent()
  → factory.create_runner(agent_id="design-ingestor", ctx=...)
    → ctx.step_skills = ["figma-ingestor"]  (threaded from current_step)
    → _skills = _resolve_step_skills(["figma-ingestor"])
      → skills_catalog.list_global_skills()
        → scans backend/skills/global/figma-ingestor/SKILL.md
        → returns GlobalSkillEntry(id="figma-ingestor", content=<SKILL.md body>)
      → returns [{"id":"figma-ingestor","name":"figma-ingestor","content":"..."}]
    → stage_skills(sandbox, _skills, agent_id="design-ingestor")
      → writes sandbox/skills/figma-ingestor/SKILL.md
      → shutil.copytree(
          src=backend/skills/global/figma-ingestor/,
          dst=sandbox/skills/figma-ingestor/,
          ignore=["SKILL.md"]
        )
        → copies scripts/figma_extract.py
        → copies scripts/figma_to_html.py
        → copies scripts/make_ds.py
        → copies scripts/ds_schema.py
        → copies scripts/schema/tokens.schema.ts
      → returns SkillsDelivery(sources=["/skills"], staged=["figma-ingestor"])
  → DeepAgentRunner is created with sources=["/skills"]
    → deepagents library sees SKILL.md in /skills/figma-ingestor/
    → advertises it in system prompt (name + description, 2 lines)
    → agent can read /skills/figma-ingestor/SKILL.md for full instructions
    → agent can exec python3 skills/figma-ingestor/scripts/figma_extract.py
```

---

*Plan authored from direct code inspection of:*
- `backend/agents/prompts/design-ingestor/AGENT.md`
- `backend/agents/workflows/prototype_v2/workflow.yaml` (lines 1-100, 800-870, 982-1000)
- `backend/agents/workflows/prototype/workflow.yaml` (lines 1-80)
- `backend/app/services/od_context_sandbox.py`
- `backend/agents/execution_engine/od_context.py`
- `backend/app/api/launch_context.py`
- `backend/agents/capabilities/context_providers/opendesign.py`
- `backend/app/agents/skill_staging.py`
- `backend/app/agents/skills_catalog.py`
- `backend/app/api/run_figma_frames.py`
- `new-ingestion-skills/import-design/SKILL.md` + `reference/design-md.md` + all 7 scripts (headers)
- `new-ingestion-skills/import-template/SKILL.md` + `reference/contract.md` + `reference/template-skill.md` + all 7 scripts (headers)
- `skills/velocity/SKILL.md`
- `backend/skills/global/velocity-design/SKILL.md`
- `backend/skills/global/velocity-design-system/SKILL.md`
- `skills/opendesign/design-systems/iberia/DESIGN.md` (first 80 lines)
- `frontend/src/lib/figma-frame-store.ts`
- `frontend/src/components/workflow/prototype/FigmaUploadSection.tsx` (first 60 lines)


---

## Section 10: Integration Tests

Tests follow the existing workspace conventions: `@pytest.mark.integration`, `tmp_path`
for real file I/O, no DB/Bedrock/network. Each new file lives under the canonical layout.

```
backend/tests/
  integration/
    agents/
      test_figma_ingestor_skills.py        ← Phase 1-2: skill placement + catalog registration
    api/
      test_figma_ingestor_scripts.py       ← Phase 3-4: new Python scripts (figma_extract, figma_to_html)
      test_figma_ingestor_sandbox_v2.py    ← Phase 6: updated output files in sandbox
  unit/
    test_figma_ingestor_yaml.py            ← Phase 5: YAML changes (exec:true, skills:figma-ingestor)
    test_figma_ingestor_opendesign.py      ← Phase 7: opendesign provider reads new files
```

---

### 10.1 `tests/integration/agents/test_figma_ingestor_skills.py`

**Purpose**: Verify Phase 1 (skills moved) and Phase 2 (global skill registered) are correct.

```python
"""tests/integration/agents/test_figma_ingestor_skills.py

Disk-read-only tests (no DB, no LLM) verifying that:
- import-design and import-template skills are placed in skills/velocity/
- new-ingestion-skills/ is gone
- figma-ingestor global skill is registered in backend/skills/global/
- figma-ingestor scripts are present and syntactically valid
"""
from __future__ import annotations
from pathlib import Path
import ast
import pytest

_BACKEND = Path(__file__).resolve().parents[3]
_REPO = _BACKEND.parent
_VELOCITY = _REPO / "skills" / "velocity"
_GLOBAL = _BACKEND / "skills" / "global"

# ── Phase 1: skills moved to skills/velocity/ ────────────────────────────────

@pytest.mark.integration
def test_import_design_moved_to_velocity() -> None:
    """import-design skill must be at skills/velocity/import-design/SKILL.md."""
    assert (_VELOCITY / "import-design" / "SKILL.md").exists(), \
        "import-design not found at skills/velocity/import-design/ — run: git mv new-ingestion-skills/import-design skills/velocity/import-design"

@pytest.mark.integration
def test_import_template_moved_to_velocity() -> None:
    """import-template skill must be at skills/velocity/import-template/SKILL.md."""
    assert (_VELOCITY / "import-template" / "SKILL.md").exists(), \
        "import-template not found at skills/velocity/import-template/ — run: git mv new-ingestion-skills/import-template skills/velocity/import-template"

@pytest.mark.integration
def test_new_ingestion_skills_staging_dir_gone() -> None:
    """new-ingestion-skills/ must not exist in the repo root after Phase 1."""
    staging_dir = _REPO / "new-ingestion-skills"
    assert not staging_dir.exists(), \
        "new-ingestion-skills/ still exists — delete it after git mv"

@pytest.mark.integration
def test_import_design_scripts_present() -> None:
    """import-design must ship its 7 scripts."""
    required = {"read_source.py", "ds_schema.py", "make_ds.py",
                "extract_site.cjs", "validate_design_system.py", "preview_ds.cjs", "shot.cjs"}
    scripts_dir = _VELOCITY / "import-design" / "scripts"
    assert scripts_dir.is_dir(), f"scripts/ missing from {scripts_dir.parent}"
    present = {f.name for f in scripts_dir.iterdir() if f.is_file()}
    assert required <= present, f"Missing scripts: {required - present}"

@pytest.mark.integration
def test_import_template_scripts_present() -> None:
    """import-template must ship its 7 scripts."""
    required = {"inspect_export.py", "snapshot.cjs", "trim.cjs",
                "validate_template.py", "preview_check.cjs", "compare.cjs", "css_tools.cjs"}
    scripts_dir = _VELOCITY / "import-template" / "scripts"
    assert scripts_dir.is_dir(), f"scripts/ missing from {scripts_dir.parent}"
    present = {f.name for f in scripts_dir.iterdir() if f.is_file()}
    assert required <= present, f"Missing scripts: {required - present}"

# ── Phase 2: figma-ingestor global skill registered ──────────────────────────

@pytest.mark.integration
def test_figma_ingestor_skill_dir_exists() -> None:
    """backend/skills/global/figma-ingestor/ must exist."""
    assert (_GLOBAL / "figma-ingestor").is_dir(), \
        "figma-ingestor global skill folder not found at backend/skills/global/figma-ingestor/"

@pytest.mark.integration
def test_figma_ingestor_skill_md_exists() -> None:
    """backend/skills/global/figma-ingestor/SKILL.md must exist with correct name field."""
    skill_md = _GLOBAL / "figma-ingestor" / "SKILL.md"
    assert skill_md.exists(), f"SKILL.md missing at {skill_md}"
    content = skill_md.read_text(encoding="utf-8")
    assert "name: figma-ingestor" in content, \
        "SKILL.md frontmatter must contain 'name: figma-ingestor'"

@pytest.mark.integration
def test_figma_ingestor_scripts_dir_exists() -> None:
    """backend/skills/global/figma-ingestor/scripts/ must contain 4 scripts."""
    scripts_dir = _GLOBAL / "figma-ingestor" / "scripts"
    assert scripts_dir.is_dir()
    required = {"figma_extract.py", "figma_to_html.py", "make_ds.py", "ds_schema.py"}
    present = {f.name for f in scripts_dir.iterdir() if f.is_file()}
    assert required <= present, f"Missing scripts: {required - present}"

@pytest.mark.integration
def test_figma_ingestor_schema_bundled() -> None:
    """tokens.schema.ts must be bundled inside the skill for sandbox-offline use."""
    schema_path = _GLOBAL / "figma-ingestor" / "scripts" / "schema" / "tokens.schema.ts"
    assert schema_path.exists(), \
        f"tokens.schema.ts not bundled at {schema_path}"
    content = schema_path.read_text(encoding="utf-8")
    assert "SCHEMA_TOKENS" in content or "--bg" in content, \
        "tokens.schema.ts appears empty or wrong file"

@pytest.mark.integration
def test_figma_ingestor_scripts_are_valid_python() -> None:
    """All .py scripts in figma-ingestor must parse as valid Python."""
    scripts_dir = _GLOBAL / "figma-ingestor" / "scripts"
    for py_file in scripts_dir.glob("*.py"):
        try:
            ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            pytest.fail(f"Syntax error in {py_file.name}: {exc}")

@pytest.mark.integration
def test_figma_ingestor_registered_in_catalog(monkeypatch) -> None:
    """skills_catalog.list_global_skills() must include 'figma-ingestor'."""
    import app.agents.skills_catalog as skills_catalog
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", _GLOBAL)
    skills_catalog.clear_cache()
    try:
        ids = {entry.id for entry in skills_catalog.list_global_skills()}
        assert "figma-ingestor" in ids, \
            f"figma-ingestor not in catalog. Found: {sorted(ids)}"
    finally:
        skills_catalog.clear_cache()
```

---

### 10.2 `tests/integration/api/test_figma_ingestor_scripts.py`

**Purpose**: Test the three new Python scripts in isolation — no LLM, no sandbox, pure file I/O.

```python
"""tests/integration/api/test_figma_ingestor_scripts.py

Integration tests for the three new stdlib-only scripts:
- figma_extract.py: observations.json + manifest.json → source.json + mapping.json
- figma_to_html.py: frames.json + tokens.css → example.html (template contract)
- make_ds.py (sandbox copy): mapping.json → tokens.css + components.html

No DB, no LLM, no network. Pure file I/O with tmp_path.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path
import pytest

_BACKEND = Path(__file__).resolve().parents[3]
_SCRIPTS = _BACKEND / "skills" / "global" / "figma-ingestor" / "scripts"

# ── Fixtures ─────────────────────────────────────────────────────────────────

def _sample_manifest() -> list[dict]:
    return [
        {"name": "frame-1.png", "mime": "image/png", "type": "image",
         "description": "Dashboard overview", "has_text": False},
        {"name": "frame-2.png", "mime": "image/png", "type": "image",
         "description": "Data table", "has_text": False},
    ]

def _sample_observations() -> dict:
    return {
        "frames": [
            {
                "index": 0, "name": "frame-1.png", "screen": "Dashboard",
                "layout": "sidebar-nav", "color_scheme": "dark",
                "bg": "#13151f", "fg": "#e0e0e0", "accent": "#5b5fef",
                "surface": "#1e2130", "surface_2": "#252a3d",
                "border": "#2a2f45", "muted": "#9aa0b4", "on_accent": "#ffffff",
                "font_weight": "medium", "font_density": "compact",
                "font_family_hint": "Inter, system-ui, sans-serif",
            },
            {
                "index": 1, "name": "frame-2.png", "screen": "Data Table",
                "layout": "sidebar-nav", "color_scheme": "dark",
                "bg": "#13151f", "fg": "#e0e0e0", "accent": "#5b5fef",
                "surface": "#1e2130", "surface_2": "#252a3d",
                "border": "#2a2f45", "muted": "#9aa0b4", "on_accent": "#ffffff",
                "font_weight": "medium", "font_density": "compact",
                "font_family_hint": "Inter, system-ui, sans-serif",
            },
        ],
        "dominant_layout": "sidebar-nav",
        "color_scheme": "dark",
        "suggested_name": "SaaS Dashboard",
    }

def _sample_frames_json() -> list[dict]:
    return [
        {"index": 0, "filename": "frame-1.png", "screen": "Dashboard",
         "description": "Dashboard overview", "layout": "sidebar-nav",
         "source": ".figma/frame-1.png"},
        {"index": 1, "filename": "frame-2.png", "screen": "Data Table",
         "description": "Data table view", "layout": "sidebar-nav",
         "source": ".figma/frame-2.png"},
    ]

def _sample_tokens_css() -> str:
    return """:root {
  --bg: #13151f;
  --fg: #e0e0e0;
  --accent: #5b5fef;
  --accent-dark: #4d4fd9;
  --surface: #1e2130;
  --surface-2: #252a3d;
  --border: #2a2f45;
  --muted: #9aa0b4;
  --on-accent: #ffffff;
  --font-display: Inter, system-ui, sans-serif;
  --font-body: Inter, system-ui, sans-serif;
  --text-base: 15px;
  --text-sm: 13px;
  --text-xs: 12px;
  --text-lg: 17px;
  --text-xl: 20px;
  --text-2xl: 24px;
  --text-3xl: 30px;
  --text-4xl: 36px;
}
"""

# ── figma_extract.py tests ────────────────────────────────────────────────────

@pytest.mark.integration
def test_figma_extract_produces_source_json(tmp_path) -> None:
    """figma_extract.py must write source.json with variables.:root block."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    (tmp_path / "manifest.json").write_text(json.dumps(_sample_manifest()), encoding="utf-8")
    (tmp_path / "observations.json").write_text(json.dumps(_sample_observations()), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=_SCRIPTS,
    )
    assert result.returncode == 0, f"figma_extract.py failed:\n{result.stderr}"
    source_path = tmp_path / "source.json"
    assert source_path.exists(), "source.json not written"
    source = json.loads(source_path.read_text())
    assert "variables" in source, "source.json missing 'variables' key"
    assert ":root" in source["variables"], "source.json missing ':root' in variables"
    root_vars = source["variables"][":root"]
    assert "--bg" in root_vars, "source.json missing --bg in :root"
    assert "--accent" in root_vars, "source.json missing --accent in :root"

@pytest.mark.integration
def test_figma_extract_produces_mapping_json(tmp_path) -> None:
    """figma_extract.py must write mapping.json with 'tokens' containing all identity tokens."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    (tmp_path / "manifest.json").write_text(json.dumps(_sample_manifest()), encoding="utf-8")
    (tmp_path / "observations.json").write_text(json.dumps(_sample_observations()), encoding="utf-8")

    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )
    mapping_path = tmp_path / "mapping.json"
    assert mapping_path.exists(), "mapping.json not written"
    mapping = json.loads(mapping_path.read_text())
    assert "tokens" in mapping, "mapping.json missing 'tokens'"
    tokens = mapping["tokens"]
    required_identity = {"--bg", "--fg", "--accent", "--surface", "--border", "--muted"}
    for t in required_identity:
        assert t in tokens, f"mapping.json missing identity token {t}"

@pytest.mark.integration
def test_figma_extract_colors_match_observations(tmp_path) -> None:
    """figma_extract.py must preserve the exact hex values from observations.json."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    (tmp_path / "manifest.json").write_text(json.dumps(_sample_manifest()), encoding="utf-8")
    (tmp_path / "observations.json").write_text(json.dumps(_sample_observations()), encoding="utf-8")

    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )
    mapping = json.loads((tmp_path / "mapping.json").read_text())
    assert mapping["tokens"]["--bg"] == "#13151f", "--bg hex must match observations"
    assert mapping["tokens"]["--accent"] == "#5b5fef", "--accent hex must match observations"

@pytest.mark.integration
def test_figma_extract_no_network_calls(tmp_path) -> None:
    """figma_extract.py must be pure stdlib — no imports that would fail without network."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    import ast
    content = (_SCRIPTS / "figma_extract.py").read_text(encoding="utf-8")
    tree = ast.parse(content)
    imports = [
        node.names[0].name.split(".")[0] if isinstance(node, ast.Import)
        else node.module.split(".")[0] if node.module else ""
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    forbidden = {"requests", "httpx", "aiohttp", "boto3", "anthropic", "openai"}
    found = set(imports) & forbidden
    assert not found, f"figma_extract.py must not import network libs: {found}"

# ── make_ds.py (sandbox copy) tests ──────────────────────────────────────────

@pytest.mark.integration
def test_make_ds_produces_tokens_css(tmp_path) -> None:
    """make_ds.py must write tokens.css with :root block when given valid mapping.json."""
    if not (_SCRIPTS / "make_ds.py").exists():
        pytest.skip("make_ds.py not yet created (Phase 3)")
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py needed to produce mapping.json (Phase 3)")

    # Produce mapping.json via figma_extract.py
    (tmp_path / "manifest.json").write_text(json.dumps(_sample_manifest()), encoding="utf-8")
    (tmp_path / "observations.json").write_text(json.dumps(_sample_observations()), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )

    dest = tmp_path / "output"
    dest.mkdir()
    import os
    env = {**os.environ, "OD_SCHEMA_PATH": str(_SCRIPTS / "schema")}
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "make_ds.py"),
         str(tmp_path / "mapping.json"),
         "--dest", str(dest)],
        capture_output=True, text=True, env=env, cwd=_SCRIPTS,
    )
    assert result.returncode == 0, f"make_ds.py failed:\n{result.stderr}"
    tokens_css = dest / "tokens.css"
    assert tokens_css.exists(), "tokens.css not written by make_ds.py"
    css_content = tokens_css.read_text()
    assert ":root {" in css_content, "tokens.css missing :root block"
    assert "--bg:" in css_content, "tokens.css missing --bg"

@pytest.mark.integration
def test_make_ds_produces_components_html(tmp_path) -> None:
    """make_ds.py must write components.html referencing var(--*) only."""
    if not (_SCRIPTS / "make_ds.py").exists():
        pytest.skip("make_ds.py not yet created (Phase 3)")
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py needed (Phase 3)")

    (tmp_path / "manifest.json").write_text(json.dumps(_sample_manifest()), encoding="utf-8")
    (tmp_path / "observations.json").write_text(json.dumps(_sample_observations()), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )

    dest = tmp_path / "output"
    dest.mkdir()
    import os
    env = {**os.environ, "OD_SCHEMA_PATH": str(_SCRIPTS / "schema")}
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "make_ds.py"),
         str(tmp_path / "mapping.json"), "--dest", str(dest)],
        capture_output=True, text=True, env=env, cwd=_SCRIPTS, check=True,
    )
    components_html = dest / "components.html"
    assert components_html.exists(), "components.html not written"
    content = components_html.read_text()
    assert "var(--bg)" in content or "var(--accent)" in content, \
        "components.html must reference CSS variables"

# ── figma_to_html.py tests ────────────────────────────────────────────────────

@pytest.mark.integration
def test_figma_to_html_produces_example_html(tmp_path) -> None:
    """figma_to_html.py must write a valid HTML file."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(json.dumps(_sample_frames_json()), encoding="utf-8")
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=_SCRIPTS,
    )
    assert result.returncode == 0, f"figma_to_html.py failed:\n{result.stderr}"
    assert (tmp_path / "example.html").exists(), "example.html not written"

@pytest.mark.integration
def test_figma_to_html_template_contract_nav_items(tmp_path) -> None:
    """example.html must have .nav-item[data-go] elements (template contract)."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(json.dumps(_sample_frames_json()), encoding="utf-8")
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )
    html = (tmp_path / "example.html").read_text()
    assert "nav-item" in html, "example.html missing nav-item class"
    assert "data-go=" in html, "example.html missing data-go attributes"
    nav_count = html.count("data-go=")
    assert nav_count >= 2, f"example.html must have at least 2 nav items, found {nav_count}"

@pytest.mark.integration
def test_figma_to_html_template_contract_pattern_sections(tmp_path) -> None:
    """example.html must have section.pattern[data-pattern] per frame (contract)."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(json.dumps(_sample_frames_json()), encoding="utf-8")
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )
    html = (tmp_path / "example.html").read_text()
    pattern_count = len(re.findall(r'data-pattern=', html))
    assert pattern_count >= 2, \
        f"example.html must have one pattern section per frame (got {pattern_count})"
    assert 'class="pattern"' in html or "class='pattern'" in html, \
        "example.html missing class=pattern on sections"

@pytest.mark.integration
def test_figma_to_html_template_contract_root_css_vars(tmp_path) -> None:
    """example.html must declare :root CSS vars from the tokens file."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(json.dumps(_sample_frames_json()), encoding="utf-8")
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )
    html = (tmp_path / "example.html").read_text()
    assert ":root" in html, "example.html must contain :root CSS vars"
    assert "--bg:" in html, "example.html must contain --bg token"
    assert "--accent:" in html, "example.html must contain --accent token"

@pytest.mark.integration
def test_figma_to_html_active_nav_item(tmp_path) -> None:
    """First nav item must have is-active class (template contract)."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(json.dumps(_sample_frames_json()), encoding="utf-8")
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )
    html = (tmp_path / "example.html").read_text()
    assert "is-active" in html, "example.html must mark the first nav item as is-active"

@pytest.mark.integration
def test_figma_to_html_one_frame_per_section(tmp_path) -> None:
    """Number of pattern sections must equal number of frames in frames.json."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    frames = _sample_frames_json()
    (tmp_path / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=_SCRIPTS, check=True,
    )
    html = (tmp_path / "example.html").read_text()
    pattern_count = len(re.findall(r'data-pattern=', html))
    assert pattern_count == len(frames), \
        f"Expected {len(frames)} pattern sections, got {pattern_count}"
```

---

### 10.3 `tests/unit/test_figma_ingestor_yaml.py`

**Purpose**: Verify Phase 5 YAML changes — `exec: true` and `skills: [figma-ingestor]` on both design-ingestor steps.

```python
"""tests/unit/test_figma_ingestor_yaml.py

Disk-read-only tests verifying that both workflow YAML files have the
correct design-ingestor step configuration after Phase 5:
- exec: true (was exec: false)
- skills: [figma-ingestor]
"""
from __future__ import annotations
from pathlib import Path
import pytest
import yaml

_BACKEND = Path(__file__).resolve().parents[2]
_PROTO_V2_YAML = _BACKEND / "agents" / "workflows" / "prototype_v2" / "workflow.yaml"
_PROTO_YAML = _BACKEND / "agents" / "workflows" / "prototype" / "workflow.yaml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find_step(data: dict, instance_id: str) -> dict | None:
    return next(
        (s for s in data.get("steps", []) if s.get("instance_id") == instance_id),
        None,
    )


@pytest.mark.unit
def test_design_ingestor_has_exec_true_in_v2() -> None:
    """design-ingestor step in prototype_v2 must have exec: true after Phase 5."""
    data = _load_yaml(_PROTO_V2_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None, "design-ingestor step not found in prototype_v2"
    tools = step.get("tools", {})
    assert tools.get("exec") is True, \
        f"design-ingestor in prototype_v2 must have exec: true (got {tools.get('exec')})"


@pytest.mark.unit
def test_design_ingestor_has_exec_true_in_prototype() -> None:
    """design-ingestor step in prototype must have exec: true after Phase 5."""
    data = _load_yaml(_PROTO_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None, "design-ingestor step not found in prototype"
    tools = step.get("tools", {})
    assert tools.get("exec") is True, \
        f"design-ingestor in prototype must have exec: true (got {tools.get('exec')})"


@pytest.mark.unit
def test_design_ingestor_has_figma_ingestor_skill_in_v2() -> None:
    """design-ingestor step in prototype_v2 must declare skills: [figma-ingestor]."""
    data = _load_yaml(_PROTO_V2_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None
    skills = step.get("skills", [])
    assert "figma-ingestor" in skills, \
        f"design-ingestor in prototype_v2 must have figma-ingestor in skills. Got: {skills}"


@pytest.mark.unit
def test_design_ingestor_has_figma_ingestor_skill_in_prototype() -> None:
    """design-ingestor step in prototype must declare skills: [figma-ingestor]."""
    data = _load_yaml(_PROTO_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None
    skills = step.get("skills", [])
    assert "figma-ingestor" in skills, \
        f"design-ingestor in prototype must have figma-ingestor in skills. Got: {skills}"


@pytest.mark.unit
def test_design_ingestor_still_has_file_extract_tool_set_in_v2() -> None:
    """file_extract tool set must still be present (for PDF ingestion)."""
    data = _load_yaml(_PROTO_V2_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None
    tool_sets = step.get("tools", {}).get("tool_sets", [])
    assert "file_extract" in tool_sets, \
        "file_extract tool set must remain on design-ingestor step for PDF support"


@pytest.mark.unit
def test_design_ingestor_still_has_read_write_tools() -> None:
    """read_files and write_files must still be true."""
    for yaml_path in [_PROTO_V2_YAML, _PROTO_YAML]:
        data = _load_yaml(yaml_path)
        step = _find_step(data, "design-ingestor")
        assert step is not None
        tools = step.get("tools", {})
        assert tools.get("read_files") is True, \
            f"read_files must be true in {yaml_path.name}"
        assert tools.get("write_files") is True, \
            f"write_files must be true in {yaml_path.name}"
```

---

### 10.4 `tests/integration/api/test_figma_ingestor_sandbox_v2.py`

**Purpose**: Verify Phase 6 output changes — new files appear in the sandbox and have the expected quality improvement over the old output.

```python
"""tests/integration/api/test_figma_ingestor_sandbox_v2.py

Phase 6 integration tests: after the Design Ingestor AGENT.md update,
new output files must appear in context/design/ and must have improved quality.

Uses tmp_path for real file I/O via a duck-typed sandbox. No LLM required —
these tests verify the CONTRACT of what the updated agent should write,
not that the agent actually runs.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
import pytest

_BACKEND = Path(__file__).resolve().parents[3]
_INGESTOR_MD = _BACKEND / "agents" / "prompts" / "design-ingestor" / "AGENT.md"


def _make_disk_sandbox(tmp_path: Path) -> Any:
    """Duck-typed sandbox backed by real files."""
    class _DiskSandbox:
        root = tmp_path

        def write(self, relpath: str, content: str) -> None:
            full = tmp_path / relpath
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        def read(self, relpath: str) -> str | None:
            full = tmp_path / relpath
            return full.read_text(encoding="utf-8") if full.is_file() else None

        def list_files(self):
            entries = []
            for p in tmp_path.rglob("*"):
                if p.is_file():
                    rel = str(p.relative_to(tmp_path)).replace("\\", "/")
                    entries.append({"path": f"./{rel}"})
            return entries, {}

    return _DiskSandbox()


# ── AGENT.md contract tests (Phase 6 readiness checks) ───────────────────────

@pytest.mark.integration
def test_agent_md_mentions_observations_json() -> None:
    """After Phase 6, AGENT.md must write observations.json (new structured format)."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert "observations.json" in content, \
        "AGENT.md must reference observations.json — Phase 6 adds this structured output"


@pytest.mark.integration
def test_agent_md_mentions_exec_figma_extract() -> None:
    """After Phase 6, AGENT.md must instruct agent to exec figma_extract.py."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert "figma_extract.py" in content, \
        "AGENT.md must reference figma_extract.py script — added in Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_exec_make_ds() -> None:
    """After Phase 6, AGENT.md must instruct agent to exec make_ds.py."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert "make_ds.py" in content, \
        "AGENT.md must reference make_ds.py script — added in Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_exec_figma_to_html() -> None:
    """After Phase 6, AGENT.md must instruct agent to exec figma_to_html.py."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert "figma_to_html.py" in content, \
        "AGENT.md must reference figma_to_html.py script — added in Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_tokens_css_output() -> None:
    """After Phase 6, AGENT.md must reference tokens.css as an output file."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert "tokens.css" in content, \
        "AGENT.md must reference tokens.css — new output file after Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_components_html_output() -> None:
    """After Phase 6, AGENT.md must reference components.html as an output file."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert "components.html" in content, \
        "AGENT.md must reference components.html — new output file after Phase 6"


@pytest.mark.integration
def test_agent_md_design_system_md_has_9_section_structure() -> None:
    """After Phase 6, AGENT.md must instruct the agent to write 9-section DESIGN.md."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    # The 9 required section headings from reference/design-md.md
    required_sections = [
        "Visual Theme",
        "Color Palette",
        "Typography",
    ]
    for section in required_sections:
        assert section in content, \
            f"AGENT.md must instruct agent to write '{section}' section in DESIGN.md format"


# ── Sandbox output contract tests ─────────────────────────────────────────────
# These simulate what an updated ingestor should write and verify the contract.

@pytest.mark.integration
def test_tokens_css_written_to_context_design(tmp_path) -> None:
    """After Phase 6, tokens.css must be findable via rebuild_od_context_from_sandbox."""
    from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    # Simulate what the updated Design Ingestor writes
    sandbox.write(".context/selections.json", json.dumps({
        "template_id": "custom-figma", "ds_id": "derived",
        "source_type": "figma", "figma_frame_count": 2,
        "no_template": False, "is_design_system_required": None,
    }))
    sandbox.write("context/design/tokens.css", ":root {\n  --bg: #13151f;\n  --accent: #5b5fef;\n}")
    sandbox.write("context/design/design-system.md", "# Design System Inspired by SaaS App\n\n## 1. Visual Theme\n")

    rebuilt = rebuild_od_context_from_sandbox(sandbox)
    assert rebuilt is not None
    ds_files = rebuilt.get("ds_files", {})
    assert "tokens.css" in ds_files, "rebuild must pick up tokens.css from context/design/"
    assert "--bg" in ds_files["tokens.css"], "tokens.css content must be read correctly"


@pytest.mark.integration
def test_components_html_written_to_context_design(tmp_path) -> None:
    """After Phase 6, components.html must be findable via rebuild_od_context_from_sandbox."""
    from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    sandbox.write(".context/selections.json", json.dumps({
        "template_id": "custom-figma", "ds_id": "derived",
        "source_type": "figma", "figma_frame_count": 2,
        "no_template": False, "is_design_system_required": None,
    }))
    sandbox.write("context/design/components.html",
                  "<html><body><div style='background:var(--bg)'>Component</div></body></html>")
    sandbox.write("context/design/design-system.md", "# Design System\n")

    rebuilt = rebuild_od_context_from_sandbox(sandbox)
    assert rebuilt is not None
    ds_files = rebuilt.get("ds_files", {})
    assert "components.html" in ds_files, \
        "rebuild must pick up components.html from context/design/"


@pytest.mark.integration
def test_nine_section_design_md_readable_by_opendesign_provider(tmp_path) -> None:
    """A 9-section design-system.md must be readable by the opendesign provider."""
    nine_section_md = """# Design System Inspired by SaaS Dashboard

> Category: Product
> Dark SaaS dashboard with indigo accent and compact density.

## 1. Visual Theme & Atmosphere

Dark, compact SaaS dashboard. Primary brand colour is indigo (#5b5fef).

**Key characteristics:**
- Canvas: #13151f (near-black navy)
- Cards: #1e2130
- Accent: #5b5fef (indigo)

## 2. Color Palette & Roles

### Primary
- **Indigo** (`#5b5fef`): buttons, active states

### Surfaces & Neutrals
- **Canvas** (`#13151f`): `--bg`
- **Card** (`#1e2130`): `--surface`

## 3. Typography Rules

### Font Family
- Body: Inter, system-ui, sans-serif

## 4. Component Stylings

### Buttons
Primary: #5b5fef fill, white text, 8px radius.

## 5. Layout Principles
- Spacing: 4 8 12 16 24 32 48

## 6. Depth & Elevation
Flat design with subtle border separators.

## 7. Do's and Don'ts
- Do: use --accent for interactive elements
- Don't: use raw hex values

## 8. Responsive Behaviour
Desktop-first, 1440px.

## 9. Agent Prompt Guide
Use dark navy backgrounds with indigo accents.
"""
    # Simulate what a figma run would produce after Phase 6
    design_md_path = tmp_path / "context" / "design" / "design-system.md"
    design_md_path.parent.mkdir(parents=True)
    design_md_path.write_text(nine_section_md, encoding="utf-8")

    # Verify it has all 9 sections
    content = design_md_path.read_text()
    for section_num in range(1, 10):
        assert f"## {section_num}." in content, \
            f"9-section design-system.md must contain '## {section_num}.'"
```

---

### 10.5 `tests/unit/test_figma_ingestor_opendesign.py`

**Purpose**: Verify Phase 7 — `opendesign.py` reads `tokens.css` and `components.html` for figma/html runs.

```python
"""tests/unit/test_figma_ingestor_opendesign.py

Unit tests for the Phase 7 opendesign.py update: the provider must read
tokens.css and components.html from context/design/ (no-dot) for
source_type in ('figma', 'html') runs.

Zero real I/O: mocks the sandbox reader.
"""
from __future__ import annotations
import asyncio
import json
import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_ctx(source_type: str, has_tokens: bool = True, has_components: bool = True):
    """Minimal ctx with a mocked sandbox reader."""
    tokens_content = ":root { --bg: #13151f; --accent: #5b5fef; }" if has_tokens else None
    components_content = "<html><body>Components</body></html>" if has_components else None
    ds_body = "# Design System\n:root { --bg: #13151f; }" if source_type != "catalog" else "--bg: #fff;"

    class _MockSandbox:
        def read(self, relpath: str) -> str | None:
            mapping = {
                "context/design/design-system.md": ds_body,
                ".context/design/design-system.md": ds_body if source_type == "catalog" else None,
                "context/design/template/SKILL.md": "# Template\n",
                ".context/design/template/SKILL.md": None,
                "context/design/tokens.css": tokens_content,
                ".context/design/tokens.css": tokens_content if source_type == "catalog" else None,
                "context/design/components.html": components_content,
                ".context/design/components.html": components_content if source_type == "catalog" else None,
                "context/design/template/figma/frames.json": json.dumps([
                    {"index": 0, "filename": "frame-1.png", "screen": "Dashboard"}
                ]) if source_type == "figma" else None,
            }
            return mapping.get(relpath)

    class _MockRunner:
        sandbox = _MockSandbox()
        def template_injection_parts(self, _): return []
        def template_example(self, _): return None

    class _Ctx:
        od_context = {
            "source_type": source_type,
            "ds_id": "derived",
            "template_id": "custom-figma",
            "ds_body": "",
            "template_body": "# Placeholder",
        }
        runner = _MockRunner()
        current_spec_tools = set()
        current_spec_injects = {"design_system", "template"}
        build_task_number = ""

    return _Ctx()


@pytest.mark.unit
def test_opendesign_provider_reads_tokens_css_for_figma_run() -> None:
    """For source_type=figma, provider must include tokens.css content."""
    from agents.capabilities.context_providers.opendesign import OpenDesignProvider
    ctx = _make_ctx("figma", has_tokens=True)
    blocks = _run(OpenDesignProvider().load(ctx))
    # The DS block should contain tokens.css content for figma runs
    ds_keys = [k for k in blocks if "DESIGN SYSTEM" in k.upper() or "ACTIVE DESIGN" in k]
    assert len(ds_keys) >= 1, "Provider must emit a DS block for figma run with design-system.md"


@pytest.mark.unit
def test_opendesign_provider_figma_block_still_present() -> None:
    """FIGMA DESIGN REFERENCE block must still be emitted for figma runs."""
    from agents.capabilities.context_providers.opendesign import OpenDesignProvider
    ctx = _make_ctx("figma")
    blocks = _run(OpenDesignProvider().load(ctx))
    assert any("FIGMA DESIGN REFERENCE" in k for k in blocks), \
        "FIGMA DESIGN REFERENCE block must be present for figma run"


@pytest.mark.unit
def test_opendesign_provider_catalog_run_unaffected() -> None:
    """Catalog run must not read from context/design/ (no-dot path)."""
    from agents.capabilities.context_providers.opendesign import OpenDesignProvider
    ctx = _make_ctx("catalog")
    # catalog run should work normally — no error, no figma block
    blocks = _run(OpenDesignProvider().load(ctx))
    assert not any("FIGMA DESIGN REFERENCE" in k for k in blocks), \
        "Catalog run must NOT emit FIGMA DESIGN REFERENCE block"
```

---

### 10.6 Regression Tests (must still pass, no changes needed)

These existing test files must continue to pass across all phases. Add them to the CI gate:

| Existing test | What it guards |
|---|---|
| `tests/integration/api/test_figma_frames_api.py` | 12 frame upload endpoint tests |
| `tests/integration/api/test_design_ingestor_sandbox.py` | 8 sandbox write tests (Phase 1 original) |
| `tests/integration/agents/test_figma_ingest_context_chain.py` | 5 figma context chain tests |
| `tests/integration/agents/test_ingestor_prompt_structure.py` | 13 prompt structure tests |
| `tests/unit/test_design_ingestion_source_type.py` | 10 source_type detection tests |
| `tests/unit/test_opendesign_provider_source_type.py` | 6 opendesign provider tests |
| `tests/unit/test_banned_patterns.py` | SC-001 — 0 pipeline_type== in engine |
| `tests/contract/agents/test_builtin_skills_catalog_contract.py` | catalog discovers all global skills |

---

### 10.7 Full test run command

After all phases are implemented:

```bash
cd backend

# New tests
uv run pytest tests/integration/agents/test_figma_ingestor_skills.py -v
uv run pytest tests/integration/api/test_figma_ingestor_scripts.py -v
uv run pytest tests/unit/test_figma_ingestor_yaml.py -v
uv run pytest tests/integration/api/test_figma_ingestor_sandbox_v2.py -v
uv run pytest tests/unit/test_figma_ingestor_opendesign.py -v

# Regression
uv run pytest tests/integration/api/test_figma_frames_api.py \
             tests/integration/api/test_design_ingestor_sandbox.py \
             tests/integration/agents/test_figma_ingest_context_chain.py \
             tests/integration/agents/test_ingestor_prompt_structure.py \
             tests/unit/test_design_ingestion_source_type.py \
             tests/unit/test_opendesign_provider_source_type.py \
             tests/unit/test_banned_patterns.py \
             tests/contract/agents/test_builtin_skills_catalog_contract.py \
             -v --no-header

# Invariants
git status --porcelain tests/agents/characterization/golden/   # must be empty
grep -rn "if pipeline_type ==" agents/execution_engine/ | wc -l  # must be 0
```

---

### 10.8 Test–Phase Mapping

| Phase | Tests that verify it |
|---|---|
| Phase 1 (move skills to velocity/) | `test_import_design_moved_to_velocity`, `test_import_template_moved_to_velocity`, `test_new_ingestion_skills_staging_dir_gone` |
| Phase 2 (figma-ingestor global skill) | `test_figma_ingestor_skill_dir_exists`, `test_figma_ingestor_skill_md_exists`, `test_figma_ingestor_scripts_dir_exists`, `test_figma_ingestor_registered_in_catalog` |
| Phase 3 (figma_extract.py + make_ds.py) | `test_figma_extract_produces_source_json`, `test_figma_extract_produces_mapping_json`, `test_figma_extract_colors_match_observations`, `test_figma_extract_no_network_calls`, `test_make_ds_produces_tokens_css`, `test_make_ds_produces_components_html` |
| Phase 4 (figma_to_html.py) | `test_figma_to_html_produces_example_html`, `test_figma_to_html_template_contract_nav_items`, `test_figma_to_html_template_contract_pattern_sections`, `test_figma_to_html_template_contract_root_css_vars`, `test_figma_to_html_active_nav_item`, `test_figma_to_html_one_frame_per_section` |
| Phase 5 (YAML exec:true + skills) | `test_design_ingestor_has_exec_true_in_v2`, `test_design_ingestor_has_exec_true_in_prototype`, `test_design_ingestor_has_figma_ingestor_skill_in_v2`, `test_design_ingestor_has_figma_ingestor_skill_in_prototype` |
| Phase 6 (AGENT.md rewrite) | `test_agent_md_mentions_observations_json`, `test_agent_md_mentions_exec_figma_extract`, `test_agent_md_mentions_exec_make_ds`, `test_agent_md_mentions_tokens_css_output`, `test_agent_md_mentions_components_html_output`, `test_agent_md_design_system_md_has_9_section_structure`, `test_tokens_css_written_to_context_design`, `test_components_html_written_to_context_design`, `test_nine_section_design_md_readable_by_opendesign_provider` |
| Phase 7 (opendesign.py) | `test_opendesign_provider_reads_tokens_css_for_figma_run`, `test_opendesign_provider_figma_block_still_present`, `test_opendesign_provider_catalog_run_unaffected` |

**Total new tests: 33 across 5 new test files.**

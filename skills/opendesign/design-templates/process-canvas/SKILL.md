---
name: Process Canvas
description: |
  A reusable operations process canvas: a fixed left sidebar plus a
  multi-screen workspace — an overview delta, a connected-systems grounding
  screen, a swimlane process map with baseline/interim/future-state version
  compare, a step-by-step decision gate, an outcome simulation, and a sign-off
  flow. Use when the brief asks for a workflow / process map / swimlane, an
  operations review, a before/after process redesign, or a decision-gate
  walkthrough.
triggers:
  - "workflow"
  - "process"
  - "process map"
  - "swimlane"
  - "operations"
  - "process review"
  - "decision gate"
  - "dashboard"
od:
  mode: prototype
  platform: desktop
  scenario: operations
  preview:
    type: html
    entry: index.html
  design_system:
    requires: true
    sections: [color, typography, layout, components]
  outputs:
    primary: index.html
  example_prompt: "Build a process canvas for a support-ticket workflow — an overview delta, a swimlane map with baseline/interim/future versions, a decision-gate walkthrough, an outcome simulation, and a sign-off screen."
  inputs:
    - "The process to map (steps, lanes, and which systems ground each step)"
    - "The single change being proposed (new step, updated steps, what stays unchanged)"
    - "The decision criteria that gate the new step (all-must-hold)"
---

# Process Canvas Skill

Produce a single, self-contained HTML prototype of an operations **process canvas** — a
sidebar workspace with four screens (Overview, Connections, Recommendation, Sign-off), a
swimlane process map with version compare, an interactive decision gate, and an outcome
simulation. Compose it from the bundled `example.html` reference — **not** by writing CSS from
scratch. The reference already encodes the visual system (soft-grid canvas, white rounded
panels, indigo accent, single green success accent, mono eyebrows) and one inline vanilla-JS
controller; your job is to re-skin the copy and re-shape the process data.

## Resource map

```
process-canvas/
├── SKILL.md         ← you're reading this
└── example.html     ← rendered, self-contained reference canvas (READ FIRST)
```

## When to use this skill

Use this when the user wants to communicate a **process** and a **change to it**, for example:

- an operations workflow / swimlane process map
- a before/after (baseline → interim → future) process redesign
- a decision-gate walkthrough (criteria that must all hold)
- an outcome-simulation / projected-impact review
- an executive-ready, approvable "here's the one change" deliverable

If the brief is a generic landing/marketing page, use `web-prototype` instead. If it is a
single-repo analytics view, use `github-dashboard`.

## Workflow

### Step 0 — Pre-flight (do this once before writing anything)

1. **Read `example.html` end-to-end** — at minimum through the inline `<style>` block and the
   `<script>` controller at the end of `<body>`. Note the state object
   (`view / recoTab / version / selectedStepId / gateStep / simState / scanIndex / signed`),
   the `STEPS` / `SYSTEMS` / `CRITERIA` data arrays, and the render functions that repaint from
   state. You will change the **data and copy**, not the mechanism.
2. **Read the active DESIGN.md** (already injected into your system prompt). Map its colors onto
   the accent (`#2563eb`), success (`#0f8a53`), ink (`#1a2233`), and canvas (`#f4f5f7`) roles;
   don't introduce new token families.

### Step 1 — Copy the reference

Copy `example.html` to the project root as `index.html`. Replace the app name, the org name in
the top strip, and the page `<title>`. Keep the overall shell (sidebar + top strip + scroll
main + four screens) intact.

### Step 2 — Reshape the process data

Edit the JS data arrays, not the markup that renders them:

- **`SYSTEMS` / `SYS_DETAIL`** — the connected systems (2-letter code, name, role). Keep 4–6.
- **`STEPS`** — the swimlane nodes. Each has `id`, `lane`, `kind` (`new` / `updated` /
  `unchanged`), `shape` (`rect` / `diamond`), absolute `x` / `y` / `w`, `title`, `sys` codes,
  `desc`, and an optional `change` note. Keep the topology (x/y/w) unless you deliberately
  re-lay-out; the SVG connectors are positioned to match.
- **`CRITERIA`** — the 3 decision-gate criteria that all must hold.
- **`CAUGHT`** — which of the 40 simulation cells match.

### Step 3 — Rewrite the copy

Replace the Overview / Connections / Sign-off prose and the version-note strings with real,
specific copy from the brief. **No filler** — every metric should carry a source or an explicit
"directional / projected" label, mirroring the reference's observed-vs-directional framing.

### Step 4 — Self-check

- All four screens switch from the sidebar.
- Recommendation sub-tabs (Process / Decision gate / Simulate) switch; the version segmented
  control swaps the swimlane; clicking a step opens its master→detail panel.
- The gate steps through (next / back / auto-play / reset); the simulation scans; sign/unsign
  toggles.
- Single accent used sparingly; success green reserved for confirmations and matches.
- The file is fully self-contained: no external network, no framework syntax, one inline
  `<script>`.

### Step 5 — Emit the artifact

Wrap `index.html` in `<artifact>` tags. One sentence before describing what's there. Stop after
`</artifact>`.

## Hard rules

- **Single self-contained `index.html`** — inline CSS + one inline vanilla-JS controller, no
  external assets, no CDN links, no framework runtime.
- **System font stack**, no external font link (`system-ui, -apple-system, 'Segoe UI',
  sans-serif` for text, `ui-monospace, 'SF Mono', Menlo, monospace` for eyebrows/numerics).
- **Single accent, used sparingly.** Indigo eyebrow + primary action is the default budget;
  green is reserved for live/success/match states.
- **`data-od-id` on every top-level region** (`sidebar`, `overview`, `connections`,
  `recommendation`, `signoff`) so comment mode can target it.
- **Every projected number is labelled directional** — keep the observed-vs-inferred honesty
  of the reference.

## Output contract

```
<artifact identifier="kebab-case-slug" type="text/html" title="Human Title">
<!doctype html>
<html>...</html>
</artifact>
```

One sentence before the artifact. Nothing after.

#!/usr/bin/env node
/**
 * assemble-phase41-gallery.mjs — Phase 41 Configure + Composer fidelity oracle.
 *
 * The RETAINED, repo-relative Phase-41 gallery assembler (sibling of the Phase-40
 * assemble-shell-gallery.mjs). It pairs the TARGET shots (the `.dc.html` mocks +
 * the approved Canvas proposal) with OUR current shots into ONE self-contained
 * gallery-phase41.html — mock/reference LEFT, ours RIGHT — for the two rebuilds
 * Phase 40 deferred:
 *   1. CONFIGURE — the mock's single "Configure your run" screen (Step-1 brief +
 *      four Advanced accordions + overlays).
 *   2. COMPOSER — the full-page composer with a Simple view (mock
 *      `Hexaware Composer.dc.html`) and a node-graph Canvas view (the APPROVED
 *      proposal `composer-canvas-proposal.html` — a design-match reference, ND-AJ).
 *
 * Repo-relative by default (no scratch dir needed): reads
 *   e2e/fidelity/shots-shell/target/{tag}.png   (from capture-shell-mocks.mjs)
 *   e2e/fidelity/shots-shell/current/{tag}.png  (from zzz-shell-baseline.spec.ts)
 * and writes e2e/fidelity/gallery-phase41.html. Set PHASE41_OUT=/abs to override
 * the base dir (then reads <base>/{target,current} + writes
 * <base>/gallery-phase41.html). The Canvas proposal is vendored at
 * e2e/fidelity/composer-canvas-proposal.html (override with CANVAS_PROPOSAL=/abs).
 *
 * Filter to ONE surface's section (a surface checkpoint regenerates only its
 * part): `--surface config` (Configure), `--surface composer` (Simple + Canvas),
 * `--surface composer-canvas` (just the Canvas design-match section).
 *
 * No new dependency (Node built-ins). No pixel-diff (ND-D live data ≠ the mock's
 * fixed values) — human review of the assembled gallery, closed to ND-AE..AL.
 *
 * Usage: node e2e/fidelity/assemble-phase41-gallery.mjs [--surface <name>]
 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url)); // e2e/fidelity
const BASE = process.env.PHASE41_OUT || join(HERE, "shots-shell");
const TARGET = join(BASE, "target");
const CURRENT = join(BASE, "current");
const OUT = process.env.PHASE41_OUT
  ? join(process.env.PHASE41_OUT, "gallery-phase41.html")
  : join(HERE, "gallery-phase41.html");
const CANVAS_PROPOSAL =
  process.env.CANVAS_PROPOSAL || join(HERE, "composer-canvas-proposal.html");

// --surface <name> filter (optional): config | composer | composer-canvas.
const surfaceArg = (() => {
  const i = process.argv.indexOf("--surface");
  return i >= 0 ? process.argv[i + 1] : null;
})();
/** A panel's surface matches the filter when it IS that surface or a sub-view
 *  (`composer-canvas` under `composer`). Mirrors assemble-shell-gallery's rule. */
function matchesSurface(surface) {
  if (!surfaceArg) return true;
  return surface === surfaceArg || surface.startsWith(`${surfaceArg}-`);
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
async function imgUri(dir, base) {
  try {
    const buf = await readFile(join(dir, `${base}.png`));
    return `data:image/png;base64,${buf.toString("base64")}`;
  } catch {
    return null;
  }
}
/** Wrap the Canvas proposal fragment in a minimal doc + base64 into a data: URI
 *  so the gallery stays fully self-contained (no external file at view time). */
async function canvasIframe() {
  let frag;
  try {
    frag = await readFile(CANVAS_PROPOSAL, "utf8");
  } catch {
    return `<div class="missing">canvas proposal not found at<br><small>${esc(CANVAS_PROPOSAL)}</small></div>`;
  }
  const doc = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0}</style></head><body>${frag}</body></html>`;
  const b64 = Buffer.from(doc, "utf8").toString("base64");
  return `<iframe class="canvas" src="data:text/html;base64,${b64}" title="Composer — Canvas view (approved proposal)"></iframe>`;
}
function figure(caption, src, missing) {
  const body = src
    ? `<img loading="lazy" src="${src}" alt="">`
    : `<div class="missing">${esc(missing || "no shot")}</div>`;
  return `<figure><figcaption>${esc(caption)}</figcaption>${body}</figure>`;
}

/** The FINALIZED Phase-41 intended-divergence register (ND-AE..AL). Canonical
 *  source of truth (captioned "expected — ignore" in the gallery header). ND-A..D
 *  carry from Phase 39; ND-W..AD are Phase 40's (in assemble-shell-gallery.mjs,
 *  UNTOUCHED). Phase 41 continues the lettering at ND-AE and adds ND-AJ (the
 *  Composer Canvas design-match reference) + ND-AL (the shared Custom-prompt
 *  presentation). See 41-UI-SPEC.md. */
const ND = [
  ["ND-AE", "Configure Templates/Design-System accordions",
    "mock always renders all four accordions; ours renders Templates + Design System ONLY when the deliverable declares the `opendesign` context provider (a user_stories/custom run shows only Review Gates + Workflow Settings). SC-001 — ConfigureScreen already gates on the declared signal (`acceptsTemplateDs` :132)."],
  ["ND-AF", "Configure selections → live registries / empty-until-chosen",
    'mock\'s fabricated "Currently using: Analytics Hub / Ink & Alabaster / 150 systems / 8 capabilities" → bound to the LIVE template/DS/capability registries; reads "None selected" until picked. SC-001 (a specialization of ND-D).'],
  ["ND-AG", "Composer Run cost + primary action",
    'mock\'s Summary rail shows "Est. cost $4.50" + a "Run once now" launching from the composer → est. cost OMITTED (no metering — parallel to ND-AC); Run routes through the real onStartPipeline seam; est. DURATION is derived live from per-agent estimated_duration. SC-001 (never fabricate consumption numbers).'],
  ["ND-AH", "Composer 'Deliverable type'",
    "mock's editable identity-card dropdown → base_pipeline_type is fixed at composer entry and rendered read-only (the composer composes AGENTS; the deliverable family is chosen upstream on Home). SC-001 / composer scope."],
  ["ND-AI", "Configure Step-1 brief affordances",
    "the mock's brief box shows Attach + Voice → Attach only (there is no product voice-input capability; carries ND-X from Phase 40)."],
  ["ND-AJ", "Composer Canvas reference",
    "the Canvas view has NO shipped `.dc.html` mock → acceptance = match-the-APPROVED-PROPOSAL (composer-canvas-proposal.html, embedded live below), a design reference; the gate is a design-match HUMAN sign-off, not a mock-fidelity pixel-diff. The Canvas view was designed + user-approved as a proposal, not shipped in the DC mock."],
  ["ND-AK", "Composer Simple view per-agent lever depth",
    "Composer Simple view — per-agent levers (Model / Validator / Gate / Retry / Custom prompt) open the REUSED AdvancedExpander + AgentPromptSection one expand deeper, rather than the mock's inline dropdown/toggles — deliberately reuse the shared levers (INV-3), not re-implement them. The collapsed row (pill + Overrides chips + Custom-prompt link) matches the mock pixel-for-pixel; only the interaction depth differs."],
  ["ND-AL", "Composer Custom-prompt presentation (Simple + Canvas)",
    "Composer Custom-prompt (Simple view AgentRow + Canvas config rail) reuses the shared `AgentPromptSection` (collapsible 'System Prompt / Base AGENT.md prompt') rather than the mock/proposal's inline editable textarea — deliberate INV-3 reuse of the shared prompt editor; the field is present, only the presentation is the shared component."],
];

/** The rebuild DECISIONS (settled at planning — retained for provenance). */
const DECISIONS = [
  ["D-CFG-ROUTE", "Configure unification target + routing",
    "The mock's ONE screen maps to THREE current impls across TWO routes: IdeaInputPage (LIVE, /dashboard mainView=input — brief path for user_stories/app_builder/custom/migration), LaunchWizard (LIVE, /workflow/create — od_prototype/od_ppt Template→DS→Discovery wizard), ConfigureScreen (DORMANT, /workflow/configure — the accordion surface structurally CLOSEST to the mock but reached by NO in-app nav and its Launch is a no-op). Decide: does the unified screen live on the /dashboard input surface, or on a route (adopt/rewire ConfigureScreen)? Whichever is chosen, the other two Configure impls' overlapping code is DELETED (INV-3, no dual implementations)."],
  ["D-CFG-STUBS", "Unstubbed template / design-system / ppt-template APIs (harness blocker — CLOSED by 41-01)",
    "GET /api/prototype/templates, /api/prototype/design-systems, /api/ppt/templates were unstubbed in e2e/fixtures/mockApi.ts (catch-all returned {}), so the Templates + Design System accordions/overlays rendered empty in mocked mode. 41-01 stubs them (representative rows, opt-in seedConfigure()) so the two overlays render populated for the fidelity diff."],
  ["D-CMP-ENTRY", "Composer full-page routing + entry + Simple⇄Canvas toggle state",
    "Today AgentsPopup is a MODAL off 'Advanced' on the brief screen (IdeaInputPage + LaunchWizard). The mock is a FULL-PAGE surface reached from Home's 'Compose a custom workflow' card and editable from My Workflows. Decide the route/entry (e.g. a /workflow/compose route or a mainView=composer surface), how 'custom' + saved-workflow-edit re-target it, and where the Simple⇄Canvas toggle state lives (per-session vs persisted)."],
  ["D-CMP-CANVAS", "Canvas render approach — hand-rolled vs graph library",
    "package.json has NO graph/dnd library (no reactflow/@xyflow/dagre/elkjs/cytoscape/d3/dnd-kit; only `motion` for animation). The APPROVED proposal is itself hand-rolled: absolute-positioned node divs + an <svg> edge layer with bezier paths + arrow markers, a left→right sequential chain. RECOMMENDATION (settled): hand-roll (SVG edges + absolute nodes + native drag) — the graph is a linear sequential chain, a library (adds a dep, INV constraint 'extend don't replace') is unwarranted."],
];

/** Surface-map summary rows shown at the top (verified file:line anchors). */
const MAPROWS = [
  ["CONFIGURE ▸ brief path", "IdeaInputPage.tsx", "brief textarea + Attach/Voice + Save/Run (:464-712) · Advanced→AgentsPopup (:765) · inline ReviewGatesSection (:789) · migration sub-tiles (:717). NO template/DS step. LIVE (/dashboard mainView=input).", "partial"],
  ["CONFIGURE ▸ wizard path", "LaunchWizard.tsx", "brief (:575) + WizardStepper Template/DS/Discovery (:677) + Web/Deck toggle + ReviewGatesSection (:723) + Advanced→AgentsPopup (:771). Fetches /api/prototype/templates + /api/ppt/templates + /api/prototype/design-systems (:237-252). LIVE (/workflow/create?mode=prototype|ppt).", "partial/blocked"],
  ["CONFIGURE ▸ accordion surface", "ConfigureScreen.tsx", "Describe/Templates/Design System/Review Gates/Workflow Settings accordions (:273-314) — the mock's structure ALREADY EXISTS. Templates/DS gated on declared opendesign (:132). DORMANT: /workflow/configure has zero in-app nav; onLaunch not passed → 'Launch run' is a no-op.", "partial/dormant"],
  ["CONFIGURE ▸ stepper chrome", "WizardStepper.tsx", "Template/DS/Discovery Tabs + Web/Deck ModeButton + Back/Next (:106-187). Chrome-only; bodies reuse TemplateGallery/PPTTemplateGallery + slots. Used ONLY by LaunchWizard.", "n/a"],
  ["COMPOSER ▸ data owner + modal", "AgentsPopup.tsx", "MODAL 'Workflow configuration' (:1747) · Agents tab flow-grid of agent cards on dot-grid w/ native HTML5 drag-reorder + per-card Info→AgentCapabilitiesModal (:1959) · Workflow tab = SkillsHooksTab + CapabilityPaletteSection (:2067). AdvancedExpander (:1412, EXPORTED) = per-agent Validator/Gate/Model/Retry <select> levers → SelectionsMap (:1382). Save→createUserWorkflow (:1781).", "partial"],
];

async function main() {
  if (process.env.PHASE41_OUT) await mkdir(process.env.PHASE41_OUT, { recursive: true });

  const [
    cfgMock, cfgCur, wTpl, wDs, wGates, wCfg, cfgGatesCur, cfgSettingsCur,
    cmpMock, cmpSimpleCur, canvasCur,
    libMock, libCur,
  ] = await Promise.all([
    imgUri(TARGET, "config__shell"), imgUri(CURRENT, "config__shell"),
    imgUri(TARGET, "wizard-template__shell"),
    imgUri(TARGET, "wizard-designsystem__shell"),
    imgUri(TARGET, "wizard-gates__shell"),
    imgUri(TARGET, "wizard-workflowcfg__shell"),
    imgUri(CURRENT, "config-gates__shellfull"),
    imgUri(CURRENT, "config-settings__shellfull"),
    imgUri(TARGET, "composer__shell"),
    // Prefer the POPULATED Simple-view capture (~5 agent rows + an active Gate
    // chip) when present so the agent-row composition is reviewable against the
    // mock's 5 rows; fall back to the fresh 0-agent shot otherwise (41-04).
    (await imgUri(CURRENT, "composer-simple-populated__shell")) ??
      (await imgUri(CURRENT, "composer-simple__shell")),
    // Prefer the POPULATED Canvas capture (~5 agent nodes + bezier edges + an
    // active Gate chip) when present so the node-graph is reviewable against the
    // approved proposal; fall back to the fresh 0-agent shot otherwise (41-05).
    (await imgUri(CURRENT, "composer-canvas-populated__shell")) ??
      (await imgUri(CURRENT, "composer-canvas__shell")),
    // ── SURFACE 3 — LIBRARY agent-detail drawer (41-07, ND-Z resolved) ──
    imgUri(TARGET, "agent-detail-drawer__shell"),
    imgUri(CURRENT, "library-agent-detail__shell"),
  ]);
  const canvas = await canvasIframe();

  // Each panel carries a `surface` for the --surface filter. Surface HEADERS
  // render only when their section has ≥1 visible panel (computed below).
  const panels = [
    // ── SURFACE 1 — CONFIGURE ──────────────────────────────────────────────
    { kind: "surface", surface: "config", title: "SURFACE 1 — CONFIGURE (unify the split flow into ONE screen)" },
    {
      kind: "pair", surface: "config", tag: "config",
      note: "MOCK = one 'Configure your run' screen: brief Step-1 box + 'ADVANCED CONFIGURATION' with FOUR accordion cards (Templates · Design System · Review Gates · Workflow Settings). OURS (config__shell) = the unified Configure screen once built (Wave 2 revives ConfigureScreen). The template/DS overlays render POPULATED via the 41-01 mocked stubs (seedConfigure()).",
      mock: cfgMock, mockCap: "MOCK — Configure your run (brief + 4 accordions)",
      cur: cfgCur, curCap: "OURS — unified Configure (config__shell)",
    },
    {
      kind: "pair", surface: "config", tag: "config ▸ Review Gates overlay",
      note: "MOCK overlayGates 'Review gates' modal: per-agent avatar + name + toggle. OURS = the ReviewGatesSection accordion (config-gates__shellfull). Same data, different shell (modal vs inline accordion).",
      mock: wGates, mockCap: "MOCK — Review gates overlay (per-agent toggles)",
      cur: cfgGatesCur, curCap: "OURS — Review Gates accordion (config-gates)",
    },
    {
      kind: "pair", surface: "config", tag: "config ▸ Workflow Settings overlay",
      note: "MOCK modalWorkflow 'Workflow configuration': left tab-rail Overview/Skills&Hooks/Capabilities/Context + '8 agents · Single-shot'. OURS = the Workflow Settings accordion (config-settings__shellfull) reusing AdvancedExpander — the per-step validator/gate/model/retry levers.",
      mock: wCfg, mockCap: "MOCK — Workflow configuration overlay",
      cur: cfgSettingsCur, curCap: "OURS — Workflow Settings accordion (config-settings)",
    },
    {
      kind: "solo", surface: "config", tag: "config ▸ Templates overlay",
      note: "MOCK overlayTemplate 'Choose a template': grid of template preview cards (No template/BLANK, blog-post, clinical-report…) + 'Use template'. OURS = TemplateGallery, now POPULATED in mocked mode via the 41-01 /api/prototype/templates stub (D-CFG-STUBS CLOSED). Captured once the Configure surface embeds it (Wave 2).",
      mock: wTpl, mockCap: "MOCK — Choose a template overlay",
    },
    {
      kind: "solo", surface: "config", tag: "config ▸ Design System overlay",
      note: "MOCK overlayDs 'Choose a design system': systems grouped (AI&LLM/Automotive/…) as chips + 'Apply system'. OURS = DesignSystemPicker, now POPULATED in mocked mode via the 41-01 /api/prototype/design-systems stub (D-CFG-STUBS CLOSED). Captured once the Configure surface embeds it (Wave 2).",
      mock: wDs, mockCap: "MOCK — Choose a design system overlay",
    },
    // ── SURFACE 2 — COMPOSER ───────────────────────────────────────────────
    { kind: "surface", surface: "composer", title: "SURFACE 2 — COMPOSER (full-page · Simple + Canvas views)" },
    {
      kind: "pair", surface: "composer", tag: "composer ▸ Simple view",
      note: "MOCK = FULL-PAGE Composer: identity card (Name/Deliverable-type/Description) + reorderable agent ROWS (avatar · name · Core badge · role · per-agent model picker · Validator/Gate/Retry override chips · Custom prompt) + right Summary rail. OURS (composer-simple__shell) = the full-page Simple view once built (Wave 4), bound to the AgentsPopup shared data model.",
      mock: cmpMock, mockCap: "MOCK — Composer Simple view (full page)",
      cur: cmpSimpleCur, curCap: "OURS — Composer Simple view, POPULATED (~5 agent rows; row-03 Gate override ON — composer-simple-populated__shell)",
    },
    {
      kind: "canvas", surface: "composer-canvas", tag: "composer ▸ Canvas view (APPROVED PROPOSAL · ND-AJ)",
      note: "The node-graph Canvas view — ALREADY DESIGNED + USER-APPROVED (composer-canvas-proposal.html, the LEFT reference below). Agents = nodes on a dot-grid; Brief→agents left→right sequential edges; click-node → right config-rail (Model/Validator/Review-gate/Retry/Custom-prompt); +-insert on edges; docked Run summary. Maps 1:1 to the AgentsPopup data. Render approach: HAND-ROLLED SVG edges + absolute-positioned nodes (D-CMP-CANVAS). Acceptance (ND-AJ) = design-match to the proposal; OURS (composer-canvas__shell) captured once built (Wave 5).",
      iframe: canvas, cur: canvasCur, curCap: "OURS — built Canvas, POPULATED (~5 agent nodes + bezier edges; one node Gate override ON — composer-canvas-populated__shell)",
    },
    // ── SURFACE 3 — LIBRARY agent-detail DRAWER (41-07 · ND-Z resolved) ─────
    { kind: "surface", surface: "library", title: "SURFACE 3 — LIBRARY agent-detail DRAWER (restructured AgentCapabilitiesModal · ND-Z resolved)" },
    {
      kind: "pair", surface: "library", tag: "library ▸ agent-detail drawer",
      note: "MOCK drawerOpen (Hexaware Workspace v2.dc.html :709): a right-side slide-in DRAWER — avatar/name/role header + Overview/Skills/Hooks/Config tab bar + Overview body (What it does · Role in pipeline · System prompt). OURS (library-agent-detail__shell) = the SHARED AgentCapabilitiesModal restructured IN PLACE into the drawer form (asDrawer variant; the composer inspector keeps the centered-modal form — not forked), opened from the Library agent card. Tab BODIES are the shipped per-agent sections, unchanged. Carries ND-A..D; ND-Z is now RESOLVED (the drawer is built).",
      mock: libMock, mockCap: "MOCK — agent-detail drawer (drawerOpen, right slide-in · 4 tabs)",
      cur: libCur, curCap: "OURS — Library agent-detail right drawer, OPEN (Overview active · Skills/Hooks/Config · library-agent-detail__shell)",
    },
  ];

  // Compute which surface headers have a visible section (≥1 matching panel
  // between this header and the next) so a filtered gallery drops empty sections.
  const headerVisible = new Map();
  for (let i = 0; i < panels.length; i++) {
    if (panels[i].kind !== "surface") continue;
    let any = false;
    for (let j = i + 1; j < panels.length && panels[j].kind !== "surface"; j++) {
      if (matchesSurface(panels[j].surface)) { any = true; break; }
    }
    headerVisible.set(i, any);
  }

  const sections = panels.map((p, i) => {
    if (p.kind === "surface") {
      return headerVisible.get(i) ? `<h2 class="surface">${esc(p.title)}</h2>` : "";
    }
    if (!matchesSurface(p.surface)) return "";
    if (p.kind === "pair") {
      return `<section class="pair">
        <h3>${esc(p.tag)}</h3>
        <p class="note">${esc(p.note)}</p>
        <div class="cols">
          ${figure(p.mockCap, p.mock, "no target shot")}
          ${figure(p.curCap, p.cur, "no current shot — surface not built yet")}
        </div>
      </section>`;
    }
    if (p.kind === "solo") {
      return `<section class="pair gap">
        <h3>${esc(p.tag)} <span class="flag ok">STUBBED — renders populated in mocked mode</span></h3>
        <p class="note">${esc(p.note)}</p>
        <div class="cols">
          ${figure(p.mockCap, p.mock, "no target shot")}
          <figure class="ph"><figcaption>OURS — no shot</figcaption><div class="missing">captured once the Configure surface embeds it (Wave 2)<br><small>APIs stubbed · D-CFG-STUBS CLOSED</small></div></figure>
        </div>
      </section>`;
    }
    if (p.kind === "canvas") {
      return `<section class="pair gap">
        <h3>${esc(p.tag)} <span class="flag ok">APPROVED PROPOSAL — design-match gate</span></h3>
        <p class="note">${esc(p.note)}</p>
        <div class="cols">
          <div class="canvaswrap"><div class="canvascap">REFERENCE — approved proposal</div>${p.iframe}</div>
          ${figure(p.curCap, p.cur, "no current shot — Canvas not built yet (Wave 5)")}
        </div>
      </section>`;
    }
    return "";
  }).join("\n");

  const ndRows = ND.map(([id, what, note]) => `<tr><td><b>${id}</b></td><td>${esc(what)}</td><td>${esc(note)}</td></tr>`).join("");
  const decRows = DECISIONS.map(([id, what, note]) => `<tr><td><b>${id}</b></td><td>${esc(what)}</td><td>${esc(note)}</td></tr>`).join("");
  const mapRows = MAPROWS.map(([s, f, d, has]) => `<tr><td>${esc(s)}</td><td><code>${esc(f)}</code></td><td>${esc(d)}</td><td class="has ${has.replace(/[^a-z]/g, "")}">${esc(has)}</td></tr>`).join("");
  const scope = surfaceArg ? ` · surface: ${esc(surfaceArg)}` : "";

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Phase 41 — Configure + Composer Fidelity Gallery${scope}</title>
<style>
  :root { color-scheme: light; }
  body { font: 14px/1.55 -apple-system, "Segoe UI", system-ui, sans-serif; margin: 0; background: #F4F3EE; color: #15161A; }
  header { padding: 22px 28px; background: #fff; border-bottom: 1px solid #E2DFD6; }
  header h1 { margin: 0 0 6px; font-size: 20px; }
  header p { margin: 0 0 4px; color: #6E6F76; max-width: 1100px; }
  details { margin: 14px 0 0; }
  summary { cursor: pointer; font-weight: 600; color: #3C2CDA; }
  table { border-collapse: collapse; margin: 10px 0 4px; width: 100%; max-width: 1180px; font-size: 13px; }
  td, th { border: 1px solid #E2DFD6; padding: 6px 9px; vertical-align: top; text-align: left; }
  th { background: #FBFAF6; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: #6E6F76; }
  td:first-child { white-space: nowrap; color: #3C2CDA; }
  .has { white-space: nowrap; font-weight: 600; }
  .has.partial, .has.partialblocked, .has.partialdormant { color: #9A6B1E; }
  .has.na { color: #9A9B92; }
  code { background: #F0EEE7; border-radius: 4px; padding: 1px 5px; font-size: 12px; }
  main { padding: 8px 28px 40px; }
  h2.surface { margin: 32px 0 4px; font-size: 16px; color: #15161A; border-bottom: 2px solid #3C2CDA; padding-bottom: 6px; }
  .pair { margin: 22px 0; }
  .pair h3 { margin: 0 0 4px; font-size: 14px; }
  .pair .note { margin: 0 0 10px; color: #45464D; max-width: 1180px; font-size: 12.5px; }
  .flag { margin-left: 8px; font: 600 10.5px/1 sans-serif; color: #B24; background: #FBE9E7; padding: 3px 8px; border-radius: 5px; text-transform: uppercase; letter-spacing: .04em; }
  .flag.ok { color: #1F7A4D; background: #E7F0EA; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  figure { margin: 0; background: #fff; border: 1px solid #E2DFD6; border-radius: 10px; overflow: hidden; }
  figcaption { font: 600 11px/1 "Manrope", sans-serif; letter-spacing: .06em; text-transform: uppercase; color: #9A9B92; padding: 9px 12px; border-bottom: 1px solid #EDEBE3; background: #FBFAF6; }
  img { display: block; width: 100%; height: auto; }
  .missing { padding: 46px 12px; text-align: center; color: #9A6B1E; }
  figure.ph { border-style: dashed; }
  .canvaswrap { background: #fff; border: 1px solid #E2DFD6; border-radius: 10px; overflow: hidden; }
  .canvascap { font: 600 11px/1 "Manrope", sans-serif; letter-spacing: .06em; text-transform: uppercase; color: #9A9B92; padding: 9px 12px; border-bottom: 1px solid #EDEBE3; background: #FBFAF6; }
  iframe.canvas { display: block; width: 100%; height: 760px; border: 0; }
</style></head>
<body>
<header>
  <h1>Phase 41 — Configure + Composer Fidelity Gallery${scope}</h1>
  <p>The two rebuilds Phase 40 deferred. <b>Configure</b>: the mock's ONE "Configure your run" screen vs our unified surface. <b>Composer</b>: the full-page Simple view + the approved node-graph Canvas view vs our built surfaces.</p>
  <p>Mock/reference (left) vs current app (right). Human review, no pixel-diff (ND-D live data ≠ mock values). Reproduce via <code>capture-shell-mocks.mjs</code> + <code>SHELL_CAPTURE=1 … zzz-shell-baseline</code>, then this assembler. See README.md for the surface→component map + commands.</p>

  <details open>
    <summary>Surface → current-component map (verified file:line)</summary>
    <table><tr><th>Surface piece</th><th>Component</th><th>What it owns</th><th>Has it?</th></tr>${mapRows}</table>
  </details>

  <details open>
    <summary>Intended divergences (ND-A..D carried + ND-W..AD Phase 40 + ND-AE..AL Phase 41) — expected, IGNORE</summary>
    <table><tr><th>ID</th><th>Divergence</th><th>Rationale</th></tr>${ndRows}</table>
  </details>

  <details>
    <summary>Settled rebuild DECISIONS (provenance)</summary>
    <table><tr><th>ID</th><th>Decision</th><th>Context + recommendation</th></tr>${decRows}</table>
  </details>
</header>
<main>
  ${sections || '<div class="missing">No panels for this --surface filter.</div>'}
</main>
</body></html>`;

  await writeFile(OUT, html, "utf8");
  console.log(`[assemble-phase41-gallery] ${surfaceArg ? `(surface=${surfaceArg}) ` : ""}→ ${OUT}`);
  console.log(`  configure: mock=${!!cfgMock} cur=${!!cfgCur} | gates cur=${!!cfgGatesCur} | settings cur=${!!cfgSettingsCur} | tpl=${!!wTpl} ds=${!!wDs}`);
  console.log(`  composer:  simple mock=${!!cmpMock} cur=${!!cmpSimpleCur} | canvas proposal=${canvas.startsWith("<iframe")} cur=${!!canvasCur}`);
  console.log(`  library:   agent-detail drawer mock=${!!libMock} cur=${!!libCur}`);
}
main();

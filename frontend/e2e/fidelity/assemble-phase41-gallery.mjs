#!/usr/bin/env node
/**
 * assemble-phase41-gallery.mjs — Phase 41 SCOPING baseline gallery.
 *
 * Phase 41 = the TWO rebuilds Phase 40 deferred:
 *   1. CONFIGURE — unify the mock's single "Configure your run" screen (brief
 *      Step-1 + four Advanced accordions) that our app splits across THREE
 *      components / TWO routes (IdeaInputPage · LaunchWizard · ConfigureScreen).
 *   2. COMPOSER — the full-page custom-workflow composer with TWO toggled views:
 *      a Simple linear agent-row list (mock: Hexaware Composer.dc.html) and a
 *      node-graph Canvas view (the approved proposal composer-canvas-proposal.html).
 *      Ours today is the AgentsPopup MODAL.
 *
 * This is a READ-ONLY scoping assembler. It does NOT capture — it REUSES the
 * committed Phase-40 shell shots (e2e/fidelity/shots-shell/{target,current}) so
 * the Phase-40 oracle stays the single capture path (reproducible via
 * capture-shell-mocks.mjs + zzz-shell-baseline.spec.ts). It pairs the Configure
 * + Composer surfaces mock-vs-current, shows the four Configure overlays
 * one-sided (their current analogs are dormant/blocked), and embeds the approved
 * Canvas proposal live via a self-contained data: iframe.
 *
 * Output: $PHASE41_OUT/gallery-phase41.html (default:
 *   $CLAUDE_JOB_DIR/tmp/phase41-scope/gallery-phase41.html).
 * Canvas proposal: $CANVAS_PROPOSAL (default: <out>/composer-canvas-proposal.html).
 *
 * No new dependency (Node built-ins). No pixel-diff (ND-D live data ≠ mock).
 *
 * Usage: PHASE41_OUT=/abs node e2e/fidelity/assemble-phase41-gallery.mjs
 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url)); // e2e/fidelity
const SHOTS = join(HERE, "shots-shell");
const TARGET = join(SHOTS, "target");
const CURRENT = join(SHOTS, "current");

const OUT_DIR =
  process.env.PHASE41_OUT ||
  join(process.env.CLAUDE_JOB_DIR || HERE, "tmp", "phase41-scope");
const OUT = join(OUT_DIR, "gallery-phase41.html");
const CANVAS_PROPOSAL =
  process.env.CANVAS_PROPOSAL || join(OUT_DIR, "composer-canvas-proposal.html");

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

/** The Phase-41 intended-divergence CANDIDATES (continue the register at ND-AE;
 *  ND-A..D + ND-W..AD are taken — see assemble-shell-gallery.mjs). These are
 *  deliberate ours≠mock keeps to CONFIRM at planning, NOT rebuild scope (the big
 *  rebuild choices live in DECISIONS below). */
const ND = [
  ["ND-AE", "Configure Templates/Design-System accordions are DECLARED-signal-gated",
    "mock always renders all four Advanced accordions; ours renders Templates + Design System ONLY when the deliverable declares the `opendesign` context provider (SC-001 — ConfigureScreen already gates on this). A user_stories/custom run shows only Review Gates + Workflow Settings."],
  ["ND-AF", "Configure fabricated selections → live registries / empty-until-chosen",
    'mock\'s "Currently using: Analytics Hub / Ink & Alabaster / 150 systems / 8 capabilities" are fabricated; ours bind to live /api/prototype/templates + /api/prototype/design-systems + /api/capabilities and read "None selected" until picked (ND-D specialization).'],
  ["ND-AG", "Composer stays SAVE-first; no fabricated Run cost",
    'mock\'s Summary rail shows "Est. cost $4.50" + a "Run once now" that launches from the composer. Ours omits fabricated cost (no metering — parallel to ND-AC) and routes Run through the real launch seam (SC-001); the composer\'s primary action is Save-to-catalogue. Duration IS derived live from per-agent estimated_duration.'],
  ["ND-AH", "Composer 'Deliverable type' fixed at entry, not an in-composer selector",
    "mock's identity card has an editable Deliverable-type dropdown; ours fixes base_pipeline_type at composer entry (the composer composes AGENTS; the deliverable family is chosen upstream on Home) → render read-only or omit the dropdown."],
  ["ND-AI", "Voice affordance on the Configure brief box → Attach only",
    "the mock's Configure Step-1 brief box shows a Voice button; there is no product voice-input capability (carry ND-X from Phase 40) — Attach file only."],
];

/** The rebuild DECISIONS the orchestrator must settle before planning. */
const DECISIONS = [
  ["D-CFG-ROUTE", "Configure unification target + routing",
    "The mock's ONE screen maps to THREE current impls across TWO routes: IdeaInputPage (LIVE, /dashboard mainView=input — brief path for user_stories/app_builder/custom/migration), LaunchWizard (LIVE, /workflow/create — od_prototype/od_ppt Template→DS→Discovery wizard), ConfigureScreen (DORMANT, /workflow/configure — the accordion surface structurally CLOSEST to the mock but reached by NO in-app nav and its Launch is a no-op). Decide: does the unified screen live on the /dashboard input surface, or on a route (adopt/rewire ConfigureScreen)? Whichever is chosen, the other two Configure impls' overlapping code is DELETED (INV-3, no dual implementations)."],
  ["D-CFG-STUBS", "Unstubbed template / design-system / ppt-template APIs (harness blocker)",
    "GET /api/prototype/templates, /api/prototype/design-systems, /api/ppt/templates are unstubbed in e2e/fixtures/mockApi.ts (catch-all returns {}), so the Templates + Design System accordions/overlays render empty in mocked mode (LaunchWizard shows a 'Couldn't load templates' path; ConfigureScreen's pickers stay empty). Phase 41 must stub them (representative rows) to capture + fidelity-review those two overlays — else there is no current analog to pair."],
  ["D-CMP-ENTRY", "Composer full-page routing + entry + Simple⇄Canvas toggle state",
    "Today AgentsPopup is a MODAL off 'Advanced' on the brief screen (IdeaInputPage + LaunchWizard). The mock is a FULL-PAGE surface reached from Home's 'Compose a custom workflow' card and editable from My Workflows. Decide the route/entry (e.g. a /workflow/compose route or a mainView=composer surface), how 'custom' + saved-workflow-edit re-target it, and where the Simple⇄Canvas toggle state lives (per-session vs persisted)."],
  ["D-CMP-CANVAS", "Canvas render approach — hand-rolled vs graph library",
    "package.json has NO graph/dnd library (no reactflow/@xyflow/dagre/elkjs/cytoscape/d3/dnd-kit; only `motion` for animation). The APPROVED proposal is itself hand-rolled: absolute-positioned node divs + an <svg> edge layer with bezier paths + arrow markers, a left→right sequential chain. The existing AgentsPopup already hand-rolls native HTML5 drag-reorder + a dot-grid flow-grid. RECOMMENDATION: hand-roll (SVG edges + absolute nodes + native drag) — the graph is a linear sequential chain, a library (adds a dep, INV constraint 'extend don't replace') is unwarranted."],
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
  await mkdir(OUT_DIR, { recursive: true });

  const [
    cfgMock, cfgCur, wTpl, wDs, wGates, wCfg, cfgGatesCur,
    cmpMock, agentCur,
  ] = await Promise.all([
    imgUri(TARGET, "config__shell"), imgUri(CURRENT, "config__shell"),
    imgUri(TARGET, "wizard-template__shell"),
    imgUri(TARGET, "wizard-designsystem__shell"),
    imgUri(TARGET, "wizard-gates__shell"),
    imgUri(TARGET, "wizard-workflowcfg__shell"),
    imgUri(CURRENT, "config-gates__shellfull"),
    imgUri(TARGET, "composer__shell"), imgUri(CURRENT, "agent-detail__shell"),
  ]);
  const canvas = await canvasIframe();

  const panels = [
    // ── SURFACE 1 — CONFIGURE ──────────────────────────────────────────────
    { kind: "surface", title: "SURFACE 1 — CONFIGURE (unify the split flow into ONE screen)" },
    {
      kind: "pair", tag: "config",
      note: "MOCK = one 'Configure your run' screen: brief Step-1 box + 'ADVANCED CONFIGURATION' with FOUR accordion cards (Templates · Design System · Review Gates · Workflow Settings). OURS = IdeaInputPage 'Provide the brief' (mainView=input): brief-only + Advanced→popup + inline Review-gates row — NO Templates/Design-System accordions. Structurally-closest current impl is ConfigureScreen.tsx (accordions already exist) but it is DORMANT (no nav) and template-blocked in mocked mode — no current shot.",
      mock: cfgMock, mockCap: "MOCK — Configure your run (brief + 4 accordions)",
      cur: cfgCur, curCap: "OURS — IdeaInputPage 'Provide the brief'",
    },
    {
      kind: "pair", tag: "config ▸ Review Gates overlay",
      note: "MOCK overlayGates 'Review gates' modal: per-agent avatar + name + toggle. OURS = the inline ReviewGatesSection on the brief screen (IdeaInputPage:789 / LaunchWizard:723 / ConfigureScreen 'Review Gates' accordion:309). Same data, different shell (modal vs inline).",
      mock: wGates, mockCap: "MOCK — Review gates overlay (per-agent toggles)",
      cur: cfgGatesCur, curCap: "OURS — inline ReviewGatesSection (fullpage)",
    },
    {
      kind: "pair", tag: "config ▸ Workflow Settings modal",
      note: "MOCK modalWorkflow 'Workflow configuration': left tab-rail Overview/Skills&Hooks/Capabilities/Context + '8 agents · Single-shot'. OURS = AgentsPopup 'Workflow configuration' MODAL (Agents/Workflow tabs) — the SAME component that is the Composer's data owner (see Surface 2). Tab sets differ.",
      mock: wCfg, mockCap: "MOCK — Workflow configuration modal (4 tabs)",
      cur: agentCur, curCap: "OURS — AgentsPopup 'Workflow configuration' modal",
    },
    {
      kind: "solo", tag: "config ▸ Templates overlay",
      note: "MOCK overlayTemplate 'Choose a template': grid of template preview cards (No template/BLANK, blog-post, clinical-report [selected]…) + 'Use template'. CURRENT analog = TemplateGallery on LaunchWizard/ConfigureScreen — BLOCKED in mocked mode (GET /api/prototype/templates unstubbed → empty). No current shot (see D-CFG-STUBS).",
      mock: wTpl, mockCap: "MOCK — Choose a template overlay",
    },
    {
      kind: "solo", tag: "config ▸ Design System overlay",
      note: "MOCK overlayDs 'Choose a design system': 150 systems grouped (AI&LLM/Automotive/…) as chips + 'Apply system'. CURRENT analog = DesignSystemPicker — BLOCKED in mocked mode (GET /api/prototype/design-systems unstubbed → empty). No current shot (see D-CFG-STUBS).",
      mock: wDs, mockCap: "MOCK — Choose a design system overlay",
    },
    // ── SURFACE 2 — COMPOSER ───────────────────────────────────────────────
    { kind: "surface", title: "SURFACE 2 — COMPOSER (full-page · Simple + Canvas views)" },
    {
      kind: "pair", tag: "composer ▸ Simple view",
      note: "MOCK = FULL-PAGE Composer: identity card (Name/Deliverable-type/Description) + reorderable agent ROWS (avatar · name · Core badge · role · per-agent model picker · Validator/Gate/Retry override chips · Custom prompt) + right Summary rail (agents/gates/strategy/est · declared caps · Save-to-catalogue/Run-once). OURS = the AgentsPopup MODAL (Agents tab = a 3-col flow-GRID of agent cards; per-agent config lives behind each card's Info→AgentCapabilitiesModal; summary is absent). Same data model, different shell (full-page vs modal, rows vs grid).",
      mock: cmpMock, mockCap: "MOCK — Composer Simple view (full page)",
      cur: agentCur, curCap: "OURS — AgentsPopup modal (Agents flow-grid)",
    },
    {
      kind: "canvas", tag: "composer ▸ Canvas view (APPROVED PROPOSAL)",
      note: "The node-graph Canvas view — ALREADY DESIGNED + USER-APPROVED (composer-canvas-proposal.html, embedded live below). Agents = nodes on a dot-grid; Brief→agents left→right sequential edges; click-node → right config-rail (Model/Validator/Review-gate/Retry/Custom-prompt); +-insert on edges; docked Run summary. Maps 1:1 to the AgentsPopup data: nodes = the agent list, node config = the per-agent SelectionsMap (model/validators/gates/retry) + prompt override, edges = the sequential order, summary = the existing summary. Render approach: HAND-ROLLED SVG edges + absolute-positioned nodes (no graph lib — see D-CMP-CANVAS). NET-NEW: no current analog.",
      iframe: canvas,
    },
  ];

  const sections = panels.map((p) => {
    if (p.kind === "surface") {
      return `<h2 class="surface">${esc(p.title)}</h2>`;
    }
    if (p.kind === "pair") {
      return `<section class="pair">
        <h3>${esc(p.tag)}</h3>
        <p class="note">${esc(p.note)}</p>
        <div class="cols">
          ${figure(p.mockCap, p.mock, "no target shot")}
          ${figure(p.curCap, p.cur, "no current shot — dormant/blocked")}
        </div>
      </section>`;
    }
    if (p.kind === "solo") {
      return `<section class="pair gap">
        <h3>${esc(p.tag)} <span class="flag">MOCK-ONLY — current analog dormant/blocked</span></h3>
        <p class="note">${esc(p.note)}</p>
        <div class="cols">
          ${figure(p.mockCap, p.mock, "no target shot")}
          <figure class="ph"><figcaption>OURS — no shot</figcaption><div class="missing">dormant / template-blocked in mocked mode<br><small>see DECISIONS · D-CFG-STUBS</small></div></figure>
        </div>
      </section>`;
    }
    if (p.kind === "canvas") {
      return `<section class="pair gap">
        <h3>${esc(p.tag)} <span class="flag ok">APPROVED — build target</span></h3>
        <p class="note">${esc(p.note)}</p>
        <div class="canvaswrap">${p.iframe}</div>
      </section>`;
    }
    return "";
  }).join("\n");

  const ndRows = ND.map(([id, what, note]) => `<tr><td><b>${id}</b></td><td>${esc(what)}</td><td>${esc(note)}</td></tr>`).join("");
  const decRows = DECISIONS.map(([id, what, note]) => `<tr><td><b>${id}</b></td><td>${esc(what)}</td><td>${esc(note)}</td></tr>`).join("");
  const mapRows = MAPROWS.map(([s, f, d, has]) => `<tr><td>${esc(s)}</td><td><code>${esc(f)}</code></td><td>${esc(d)}</td><td class="has ${has.replace(/[^a-z]/g, "")}">${esc(has)}</td></tr>`).join("");

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Phase 41 — Configure + Composer: SCOPING baseline</title>
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
  iframe.canvas { display: block; width: 100%; height: 760px; border: 0; }
</style></head>
<body>
<header>
  <h1>Phase 41 — Configure + Composer · SCOPING baseline</h1>
  <p>The two rebuilds Phase 40 deferred. <b>Configure</b>: the mock's ONE "Configure your run" screen vs our 3-way split (IdeaInputPage · LaunchWizard · ConfigureScreen). <b>Composer</b>: the full-page Simple view + the approved node-graph Canvas view vs our AgentsPopup modal.</p>
  <p>Mock (left) vs current app (right). Human review, no pixel-diff (ND-D live data ≠ mock values). Shots REUSED from the committed Phase-40 oracle (Configure/Composer were untouched by Phase 40) — reproduce via <code>capture-shell-mocks.mjs</code> + <code>SHELL_CAPTURE=1 … zzz-shell-baseline</code>, then this assembler.</p>

  <details open>
    <summary>Surface → current-component map (verified file:line)</summary>
    <table><tr><th>Surface piece</th><th>Component</th><th>What it owns</th><th>Has it?</th></tr>${mapRows}</table>
  </details>

  <details open>
    <summary>Intended-divergence CANDIDATES — continue at ND-AE (ND-A..D + ND-W..AD taken) — expected, confirm at planning</summary>
    <table><tr><th>ID</th><th>Divergence</th><th>Rationale</th></tr>${ndRows}</table>
  </details>

  <details open>
    <summary>DECISIONS the orchestrator must settle before planning</summary>
    <table><tr><th>ID</th><th>Decision</th><th>Context + recommendation</th></tr>${decRows}</table>
  </details>
</header>
<main>
  ${sections}
</main>
</body></html>`;

  await writeFile(OUT, html, "utf8");
  console.log(`[assemble-phase41-gallery] → ${OUT}`);
  console.log(`  configure: mock=${!!cfgMock} cur=${!!cfgCur} | gates mock=${!!wGates} cur=${!!cfgGatesCur} | wfcfg mock=${!!wCfg} cur=${!!agentCur} | tpl=${!!wTpl} ds=${!!wDs}`);
  console.log(`  composer:  simple mock=${!!cmpMock} cur=${!!agentCur} | canvas iframe=${canvas.startsWith("<iframe")}`);
}
main();

#!/usr/bin/env node
/**
 * assemble-shell-gallery.mjs — Phase 40 SCOPING BASELINE gallery assembler.
 *
 * Sibling of assemble-gallery.mjs (Phase 39). Pairs the TARGET shell shots
 * ($PHASE40_OUT/shots/target/{tag}.png, from capture-shell-mocks.mjs) with OUR
 * shots ($PHASE40_OUT/shots/current/{tag}.png, from zzz-shell-baseline.spec.ts)
 * into ONE self-contained gallery-shell.html — mock LEFT, ours RIGHT, per
 * {surface}__{state} tag (state ∈ shell | shellfull). base64-inlined = portable.
 *
 * No pixel-diff (ND-D live data ≠ mock values) — human review of the gallery.
 * No new dependency (Node built-ins).
 *
 * Usage: PHASE40_OUT=/abs node e2e/fidelity/assemble-shell-gallery.mjs
 */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const ROOT = process.env.PHASE40_OUT || "/tmp/phase40-scope";
const TARGET = join(ROOT, "shots", "target");
const CURRENT = join(ROOT, "shots", "current");
const OUT = join(ROOT, "gallery-shell.html");

/** Intended-divergence register carried from Phase 39 (SC-001 shell rules) +
 *  Phase-40 first-pass candidates surfaced while scoping the shell. */
const ND = [
  ["ND-A", "Brand wordmark", 'mock "HEXAWARE" → we ship "VelocityAI" (AppHeader.tsx:109)'],
  ["ND-B", "Catalogue nav label", 'mock "Catalogue" → we ship "My Workflows" (D-11; AppHeader.tsx:98). The mock\'s Catalogue surface maps to our SavedWorkflowsPage ("My Workflows")'],
  ["ND-C", "Nav active-state", "mock's pill-fill treatment → our purple underline (ND-13.1; AppHeader.tsx:124 border-brand)"],
  ["ND-D", "All shell data", "mock's hardcoded rows/counts/charts → our LIVE data (runs, analytics, saved workflows) from real endpoints (SC-001)"],
  ["ND-E?", "History surface title", 'CANDIDATE: mock "Workflow History" → app renders "Run History" (WorkflowHistory.tsx:767). Confirm whether to align'],
  ["ND-F?", "Configure/wizard shape", 'CANDIDATE: mock = ONE "Configure your run" screen (brief + Templates/Design System/Review Gates/Workflow Settings accordions + full-screen overlays). Ours is SPLIT: IdeaInputPage (brief + Advanced + inline Review gates) has NO template/design-system step; those live on separate routes /workflow/create (LaunchWizard) + /workflow/configure (ConfigureScreen)'],
  ["ND-G?", "Agents/Composer shape", 'CANDIDATE: mock = full-page Composer (Hexaware Composer.dc.html: identity + Agent-pipeline reorder/model-pick/add-remove). Ours = AgentsPopup MODAL ("Workflow configuration") opened from the brief screen'],
  ["ND-H?", "Library scope", 'CANDIDATE: mock Library = Agents/Skills/Hooks reference tabs. Confirm our LibraryPage tab parity'],
];

async function pngTags(dir) {
  const files = await readdir(dir).catch(() => []);
  return files.filter((f) => f.endsWith(".png")).map((f) => f.replace(/\.png$/, ""));
}
async function dataUri(dir, tag) {
  try {
    const buf = await readFile(join(dir, `${tag}.png`));
    return `data:image/png;base64,${buf.toString("base64")}`;
  } catch {
    return null;
  }
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function cell(src, missingLabel) {
  return src
    ? `<img loading="lazy" src="${src}" alt="">`
    : `<div class="missing">${esc(missingLabel)}<br><small>no shot — surface may be missing/blocked (see SURFACE-MAP.md)</small></div>`;
}

async function main() {
  const tags = [...new Set([...(await pngTags(TARGET)), ...(await pngTags(CURRENT))])].sort();
  const rows = [];
  for (const tag of tags) {
    const [target, current] = await Promise.all([dataUri(TARGET, tag), dataUri(CURRENT, tag)]);
    const [surface, state] = tag.split("__");
    const onlyMock = target && !current;
    rows.push(`
      <section class="pair${onlyMock ? " gap" : ""}">
        <h2>${esc(tag)} <span class="meta">${esc(surface || "")} · ${esc(state || "")}</span>${onlyMock ? '<span class="flag">MOCK-ONLY — no current analog captured</span>' : ""}</h2>
        <div class="cols">
          <figure><figcaption>MOCK (target)</figcaption>${cell(target, "no target shot")}</figure>
          <figure><figcaption>OURS (current)</figcaption>${cell(current, "no current shot")}</figure>
        </div>
      </section>`);
  }
  const ndRows = ND.map(([id, what, note]) => `<tr><td><b>${id}</b></td><td>${esc(what)}</td><td>${esc(note)}</td></tr>`).join("");

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Phase 40 — Shell Fidelity Baseline Gallery</title>
<style>
  :root { color-scheme: light; }
  body { font: 14px/1.5 -apple-system, "Segoe UI", system-ui, sans-serif; margin: 0; background: #F4F3EE; color: #15161A; }
  header { padding: 22px 28px; background: #fff; border-bottom: 1px solid #E2DFD6; position: sticky; top: 0; z-index: 2; }
  header h1 { margin: 0 0 6px; font-size: 19px; }
  header p { margin: 0; color: #6E6F76; }
  .nd { margin: 14px 0 0; }
  .nd summary { cursor: pointer; font-weight: 600; color: #3C2CDA; }
  table { border-collapse: collapse; margin-top: 10px; width: 100%; max-width: 1100px; }
  td { border: 1px solid #E2DFD6; padding: 5px 9px; vertical-align: top; }
  td:first-child { white-space: nowrap; color: #3C2CDA; }
  main { padding: 24px 28px; display: flex; flex-direction: column; gap: 34px; }
  .pair h2 { margin: 0 0 10px; font-size: 15px; }
  .pair .meta { color: #9A9B92; font-weight: 400; font-size: 12px; }
  .pair .flag { margin-left: 10px; font: 600 11px/1 sans-serif; color: #B24; background: #FBE9E7; padding: 3px 8px; border-radius: 5px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  figure { margin: 0; background: #fff; border: 1px solid #E2DFD6; border-radius: 10px; overflow: hidden; }
  figcaption { font: 600 11px/1 "Manrope", sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #9A9B92; padding: 9px 12px; border-bottom: 1px solid #EDEBE3; background: #FBFAF6; }
  img { display: block; width: 100%; height: auto; }
  .missing { padding: 40px 12px; text-align: center; color: #B24; }
  .empty { padding: 60px; text-align: center; color: #9A9B92; }
</style></head>
<body>
<header>
  <h1>Phase 40 — Shell Fidelity Baseline Gallery</h1>
  <p>Mock (left) vs current app (right), per <code>{surface}__{state}</code> (state ∈ shell = 1440×900 viewport · shellfull = full page). Scoping baseline — human review, no pixel-diff (ND-D). See SURFACE-MAP.md for the surface→component map + notes.</p>
  <details class="nd" open>
    <summary>Intended divergences (carried ND-A..D) + Phase-40 first-pass candidates (ND-E?..H?) — review, don't fix here</summary>
    <table>${ndRows}</table>
  </details>
</header>
<main>
  ${rows.length ? rows.join("\n") : '<div class="empty">No shots found. Run the capture steps first (see SURFACE-MAP.md).</div>'}
</main>
</body></html>`;

  await writeFile(OUT, html, "utf8");
  console.log(`[assemble-shell-gallery] ${rows.length} pair(s) → ${OUT}`);
}
main();

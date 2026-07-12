#!/usr/bin/env node
/**
 * assemble-shell-gallery.mjs — Phase 40 SHELL fidelity gallery assembler.
 *
 * Sibling of assemble-gallery.mjs (Phase 39). Pairs the TARGET shell shots
 * (from capture-shell-mocks.mjs) with OUR shots (from zzz-shell-baseline.spec.ts)
 * into ONE self-contained gallery-shell.html — mock LEFT, ours RIGHT, per
 * {surface}__{state} tag (state ∈ shell = 1440×900 viewport · shellfull = full
 * page). base64-inlined = portable.
 *
 * Repo-relative by default (no scratch dir needed): reads
 *   e2e/fidelity/shots-shell/target/{tag}.png   (from capture-shell-mocks.mjs)
 *   e2e/fidelity/shots-shell/current/{tag}.png  (from zzz-shell-baseline.spec.ts)
 * and writes e2e/fidelity/gallery-shell.html. Set PHASE40_OUT=/abs to override
 * the base dir (then reads <base>/{target,current} + writes <base>/gallery-shell.html).
 *
 * Filter to ONE surface's section (a surface checkpoint regenerates only its
 * part): `--surface history` keeps only tags whose surface is `history` (or a
 * `history-*` sub-view). e.g. `--surface library` → library + library-agents +
 * library-agent-detail…; `--surface settings` → settings + settings-model…
 *
 * No pixel-diff (ND-D live data ≠ mock values) — human review of the gallery.
 * No new dependency (Node built-ins).
 *
 * Usage: node e2e/fidelity/assemble-shell-gallery.mjs [--surface <name>]
 */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url)); // e2e/fidelity
const BASE = process.env.PHASE40_OUT || join(HERE, "shots-shell");
const TARGET = join(BASE, "target");
const CURRENT = join(BASE, "current");
const OUT = process.env.PHASE40_OUT
  ? join(process.env.PHASE40_OUT, "gallery-shell.html")
  : join(HERE, "gallery-shell.html");

// --surface <name> filter (optional).
const surfaceArg = (() => {
  const i = process.argv.indexOf("--surface");
  return i >= 0 ? process.argv[i + 1] : null;
})();

/** The FINALIZED intended-divergence register (SC-001 shell rules). ND-A..D are
 *  carried from Phase 39; ND-W..Z are the Phase-40 shell divergences. This array
 *  is the canonical, shipped source of truth captioned "expected — ignore" in the
 *  gallery header. The Phase-39 scoping candidates (ND-E?..H?) and the DEFERRED
 *  Configure/Composer surfaces are intentionally NOT listed (not diffed here). */
const ND = [
  ["ND-A", "Brand wordmark", 'mock "HEXAWARE" → we ship "VelocityAI" (AppHeader.tsx) — carried from Phase 39'],
  ["ND-B", "Catalogue nav label + surface title", 'mock "Catalogue" → we ship "My Workflows" (D-11; Catalogue reserved for the future marketplace) — carried'],
  ["ND-C", "Nav active-state", "mock's pill-fill treatment → our purple underline (ND-13.1; AppHeader border-brand) — carried"],
  ["ND-D", "All shell data", "mock's hardcoded rows/counts/charts → our LIVE data (runs, analytics, saved workflows) from real endpoints; empty surfaces use opt-in W1 capture seeding for the diff ONLY (SC-001) — carried"],
  ["ND-W", "Workflow History title", 'mock "Workflow History" → we ship "Run History" (matches the profile-menu item; parallel to ND-B)'],
  ["ND-X", "Home prompt affordances", "mock Attach + Voice buttons → Attach only (Attach is a real image-input feature; there is NO product voice-input capability)"],
  ["ND-Y", "Account Settings profile form", "mock's fabricated name / role / organization fields → only profile fields backed by real user data (email, plan/tier) — never fabricate unpersisted data"],
  ["ND-Z", "Library agent-detail", "mock's right-side agent-detail DRAWER (Overview/Skills/Hooks/Config) → Phase 40 keeps the shared AgentCapabilitiesModal; the drawer rebuild lands with the Composer in Phase 41"],
  ["ND-AA", "Analytics 'By Model' vs the mock's 'Recent Runs'", "the /api/analytics/summary payload carries no recent-runs list, so the right-column card shows the live per-model rollup rather than fabricating run rows (ND-D). A recent-runs data wire is a Phase-41 follow-up."],
  ["ND-AB", "Account Settings AI-Model selector", "mock's static radio-card model list → our live-bound dropdown (<select>). The model list is live per ND-D; the dropdown is the existing tested save-preference control (updatePreferences) — the control shape stays put so the pinned behaviour parity holds."],
  ["ND-AC", "Account Settings 'Usage & Limits' this-month bars", "mock's fabricated per-user 'This month' usage bars → omitted; there is no usage-metering endpoint so we never fabricate consumption numbers (SC-001/ND-D). We render the real plan banner + the live per-plan deliverable-access grid instead."],
];

/** Normalize divergent per-side tags so a surface pairs left/right. The mock
 *  side emits `agent-detail-drawer` (Hexaware Library drawer) while our side
 *  emits `library-agent-detail` (the shared modal) — the ND-Z pair. Alias them
 *  onto one surface so they render as a left/right pair, not two unpaired cells. */
function normTag(base) {
  return base.replace(/^agent-detail-drawer(__|$)/, "library-agent-detail$1");
}

/** normalizedTag → real basename, for one shots dir. */
async function tagMap(dir) {
  const files = await readdir(dir).catch(() => []);
  const m = new Map();
  for (const f of files) {
    if (!f.endsWith(".png")) continue;
    const base = f.replace(/\.png$/, "");
    m.set(normTag(base), base);
  }
  return m;
}
async function dataUri(dir, base) {
  try {
    const buf = await readFile(join(dir, `${base}.png`));
    return `data:image/png;base64,${buf.toString("base64")}`;
  } catch {
    return null;
  }
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function surfaceOf(tag) {
  return tag.split("__")[0] || "";
}
function matchesSurface(tag) {
  if (!surfaceArg) return true;
  const s = surfaceOf(tag);
  return s === surfaceArg || s.startsWith(`${surfaceArg}-`);
}
function cell(src, missingLabel) {
  return src
    ? `<img loading="lazy" src="${src}" alt="">`
    : `<div class="missing">${esc(missingLabel)}<br><small>no shot — surface may be missing/blocked</small></div>`;
}

async function main() {
  const [targetMap, currentMap] = await Promise.all([tagMap(TARGET), tagMap(CURRENT)]);
  const tags = [...new Set([...targetMap.keys(), ...currentMap.keys()])]
    .filter(matchesSurface)
    .sort();
  const rows = [];
  for (const tag of tags) {
    const [target, current] = await Promise.all([
      targetMap.has(tag) ? dataUri(TARGET, targetMap.get(tag)) : Promise.resolve(null),
      currentMap.has(tag) ? dataUri(CURRENT, currentMap.get(tag)) : Promise.resolve(null),
    ]);
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
  const scope = surfaceArg ? ` · surface: ${esc(surfaceArg)}` : "";

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Phase 40 — Shell Fidelity Gallery${scope}</title>
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
  <h1>Phase 40 — Shell Fidelity Gallery${scope}</h1>
  <p>Mock (left) vs current app (right), per <code>{surface}__{state}</code> (state ∈ shell = 1440×900 viewport · shellfull = full page). Human review, no pixel-diff (ND-D live data ≠ mock values). See README.md for the surface→component map + commands.</p>
  <details class="nd" open>
    <summary>Intended divergences (ND-A..D carried + ND-W..Z Phase 40) — expected, IGNORE</summary>
    <table>${ndRows}</table>
  </details>
</header>
<main>
  ${rows.length ? rows.join("\n") : '<div class="empty">No shots found. Run the capture steps first (see README.md).</div>'}
</main>
</body></html>`;

  await writeFile(OUT, html, "utf8");
  console.log(`[assemble-shell-gallery] ${rows.length} pair(s)${surfaceArg ? ` (surface=${surfaceArg})` : ""} → ${OUT}`);
}
main();

#!/usr/bin/env node
/**
 * assemble-gallery.mjs — the D39-6 fidelity ORACLE assembler.
 *
 * Pairs the TARGET shots (`shots/target/{tag}.png`, from capture-mocks.mjs) with
 * OUR shots (`shots/current/{tag}.png`, from the FIDELITY_CAPTURE zzz-baseline
 * spec) into ONE self-contained `gallery.html` — mock on the LEFT, ours on the
 * RIGHT, per `{surface}__{state}` tag. Images are inlined as base64 data-URIs so
 * the file is a single portable artifact a reviewer can open anywhere.
 *
 * A header block captions the INTENDED-DIVERGENCE REGISTER (ND-A..ND-J) as
 * "expected — ignore" so a reviewer never mistakes a registered divergence for a
 * fidelity gap. There is deliberately NO automated pixel-diff: ND-D (our live
 * data never equals the mock's hardcoded values) would make a pixel compare
 * always "fail" — the fidelity judgment is a HUMAN review of this gallery.
 *
 * No new dependency — Node built-ins only.
 *
 * Usage:
 *   node e2e/fidelity/assemble-gallery.mjs                 # all tags
 *   node e2e/fidelity/assemble-gallery.mjs --surface steps # one surface section
 */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const TARGET = join(HERE, "shots", "target");
const CURRENT = join(HERE, "shots", "current");
const OUT = join(HERE, "gallery.html");

/** The intended-divergence register (39-01-PLAN ND-A..ND-G + ND-H per 39-07,
 *  ND-I/ND-J added 39-01 for two live-data extras the lane renders vs the mock). */
const ND = [
  ["ND-A", "Brand wordmark", 'mock "HEXAWARE" → we ship "VelocityAI"'],
  ["ND-B", "Nav label", 'mock "Catalogue" → we ship "My Workflows" (D-11)'],
  ["ND-C", "Nav active-state", "mock's treatment → our purple underline (ND-13.1)"],
  ["ND-D", "All run data", "mock's hardcoded values → our LIVE data (SC-001)"],
  ["ND-E", "Left-lane width", "mock 390px → our responsive md/lg widths"],
  ["ND-F", "Prototype scrubber / image-slot", "demo-only — NOT reproduced"],
  ["ND-G", "Deliverable renderers", "we REUSE the existing renderers (D39-3)"],
  ["ND-H", "Share action", "client-only Share link in v1"],
  ["ND-I", "Header Stop control (live)", "we KEEP a Stop while a run is live — essential run control the mock's live lane omits"],
  ["ND-J", "Attachment chips on a failed run", "real run inputs show — the mock's specific failed example happened to have none"],
];

const surfaceArg = process.argv.includes("--surface")
  ? process.argv[process.argv.indexOf("--surface") + 1]
  : null;

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
    : `<div class="missing">${esc(missingLabel)}<br><small>run the capture step</small></div>`;
}

async function main() {
  const tags = [...new Set([...(await pngTags(TARGET)), ...(await pngTags(CURRENT))])]
    .filter((t) => !surfaceArg || t.split("__")[0] === surfaceArg)
    .sort();

  const rows = [];
  for (const tag of tags) {
    const [target, current] = await Promise.all([dataUri(TARGET, tag), dataUri(CURRENT, tag)]);
    const [surface, state] = tag.split("__");
    rows.push(`
      <section class="pair">
        <h2>${esc(tag)} <span class="meta">${esc(surface || "")} · ${esc(state || "")}</span></h2>
        <div class="cols">
          <figure><figcaption>MOCK (target)</figcaption>${cell(target, "no target shot")}</figure>
          <figure><figcaption>OURS (current)</figcaption>${cell(current, "no current shot")}</figure>
        </div>
      </section>`);
  }

  const ndRows = ND.map(([id, what, note]) => `<tr><td><b>${id}</b></td><td>${esc(what)}</td><td>${esc(note)}</td></tr>`).join("");

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Run-Screen Fidelity Gallery${surfaceArg ? ` — ${esc(surfaceArg)}` : ""}</title>
<style>
  :root { color-scheme: light; }
  body { font: 14px/1.5 -apple-system, "Segoe UI", system-ui, sans-serif; margin: 0; background: #F4F3EE; color: #15161A; }
  header { padding: 22px 28px; background: #fff; border-bottom: 1px solid #E2DFD6; position: sticky; top: 0; z-index: 2; }
  header h1 { margin: 0 0 6px; font-size: 19px; }
  header p { margin: 0; color: #6E6F76; }
  .nd { margin: 14px 0 0; }
  .nd summary { cursor: pointer; font-weight: 600; color: #3C2CDA; }
  table { border-collapse: collapse; margin-top: 10px; width: 100%; max-width: 900px; }
  td { border: 1px solid #E2DFD6; padding: 5px 9px; vertical-align: top; }
  td:first-child { white-space: nowrap; color: #3C2CDA; }
  main { padding: 24px 28px; display: flex; flex-direction: column; gap: 34px; }
  .pair h2 { margin: 0 0 10px; font-size: 15px; }
  .pair .meta { color: #9A9B92; font-weight: 400; font-size: 12px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  figure { margin: 0; background: #fff; border: 1px solid #E2DFD6; border-radius: 10px; overflow: hidden; }
  figcaption { font: 600 11px/1 "Manrope", sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #9A9B92; padding: 9px 12px; border-bottom: 1px solid #EDEBE3; background: #FBFAF6; }
  img { display: block; width: 100%; height: auto; }
  .missing { padding: 40px 12px; text-align: center; color: #B24; }
  .empty { padding: 60px; text-align: center; color: #9A9B92; }
</style></head>
<body>
<header>
  <h1>Run-Screen Fidelity Gallery${surfaceArg ? ` — <code>${esc(surfaceArg)}</code>` : ""}</h1>
  <p>Mock (left) vs current (right), per <code>{surface}__{state}</code>. Human review only — no pixel-diff (ND-D live data ≠ mock values).</p>
  <details class="nd" open>
    <summary>Intended divergences — expected, ignore (ND-A..ND-J)</summary>
    <table>${ndRows}</table>
  </details>
</header>
<main>
  ${rows.length ? rows.join("\n") : '<div class="empty">No shots found. Run the capture steps first (see README.md).</div>'}
</main>
</body></html>`;

  await writeFile(OUT, html, "utf8");
  console.log(`[assemble-gallery] ${rows.length} pair(s)${surfaceArg ? ` for surface "${surfaceArg}"` : ""} → ${OUT}`);
}

main();

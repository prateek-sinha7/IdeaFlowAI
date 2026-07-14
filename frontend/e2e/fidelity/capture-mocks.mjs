#!/usr/bin/env node
/**
 * capture-mocks.mjs — TARGET-side capture of the three run-screen mocks.
 *
 * Opens each authored `.dc.html` over the local static server (serve-mocks.mjs),
 * lets the DC runtime (`support.js`) hydrate, drives each tab via the mock's own
 * rendered controls, and screenshots into `shots/target/{surface}__{state}.png`
 * — the LEFT column of the side-by-side fidelity gallery.
 *
 * The DC runtime needs `window.React` / `window.ReactDOM` globals (it polls for
 * them for 30s) and loads Babel + Google fonts from a CDN — so this capture
 * requires NETWORK access. Offline it will time out waiting for hydration; that
 * is expected and does not indicate a harness bug.
 *
 * No new dependency: reuses the already-installed Playwright chromium.
 *
 * Usage:
 *   node e2e/fidelity/capture-mocks.mjs                 # all three states
 *   node e2e/fidelity/capture-mocks.mjs --state live    # one mock
 */
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { startMockServer } from "./serve-mocks.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "shots", "target");

// React 18 UMD — the DC runtime targets React 18 (window.React / window.ReactDOM).
const REACT_UMD = "https://unpkg.com/react@18.3.1/umd/react.production.min.js";
const REACT_DOM_UMD = "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js";

/** state → mock filename. "state" is the run condition; "surface" is the tab. */
const MOCKS = {
  settled: "Hexaware Run.dc.html",
  live: "Hexaware Run - Live.dc.html",
  failed: "Hexaware Run - Failed.dc.html",
};

/** The four right-panel tabs, in the mock's order (Preview·Steps·Files·Audit). */
const SURFACES = ["Preview", "Steps", "Files", "Audit"];

const VIEWPORT = { width: 1440, height: 900 };

async function capture(state, file, browser, origin) {
  const page = await browser.newPage({ viewport: VIEWPORT });
  const url = `${origin}/${encodeURIComponent(file)}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });

  // Provide the globals the DC runtime polls for, then let it hydrate.
  await page.addScriptTag({ url: REACT_UMD }).catch(() => {});
  await page.addScriptTag({ url: REACT_DOM_UMD }).catch(() => {});

  // Hydration is done once ANY real tab button is on the page. The failed mock
  // omits the Preview tab (Steps·Files·Audit only) AND renders a count inside the
  // tab label ("Steps 5"), so gate on a CONTAINS match of any tab word — anchored
  // "^Preview$" would time out on the failed mock and skip its leftlane clip.
  await page
    .getByRole("button", { name: /(Preview|Steps|Files|Audit)/ })
    .first()
    .waitFor({ state: "visible", timeout: 30_000 });

  // Full-panel shot per tab.
  for (const surface of SURFACES) {
    const btn = page.getByRole("button", { name: new RegExp(`^${surface}$`) }).first();
    await btn.click({ timeout: 6_000 }).catch(() => {});
    await page.waitForTimeout(700);
    await page.screenshot({ path: join(OUT, `${surface.toLowerCase()}__${state}.png`), fullPage: false });
  }

  // Left conversation lane clip (the transcript column) — reset to Preview first.
  await page.getByRole("button", { name: /^Preview$/ }).first().click({ timeout: 6_000 }).catch(() => {});
  await page.waitForTimeout(500);
  await page.screenshot({ path: join(OUT, `leftlane__${state}.png`), clip: { x: 0, y: 0, width: 400, height: VIEWPORT.height } });

  // Phase 39 (RUNUI-06/07) — the run-header row crop (Version ▾ / Share / Download
  // in settled; the status badge + version chip in live/failed). The mock's right
  // column starts after the ~390px lane, below the 58px black top nav. Pairs
  // against our `header__{state}` crop in the fidelity gallery (`--surface header`).
  await page.screenshot({ path: join(OUT, `header__${state}.png`), clip: { x: 390, y: 58, width: 1050, height: 132 } });

  // Steps INTERNAL views (settled) — drill the mock's Build Agent → its
  // construction artifact block → a construction task row → L3 task detail, so the
  // gallery can pair `steps-construction` + `steps-task` against our side. The
  // mock's rows are click-handler divs (no roles), so target by text; best-effort
  // (a miss still screenshots whatever is shown).
  if (state === "settled") {
    await page.getByRole("button", { name: /^Steps$/ }).first().click({ timeout: 6_000 }).catch(() => {});
    await page.waitForTimeout(500);
    // The overview spine's "Build Agent" row is the LAST such label (the left-lane
    // pipeline mini lists it earlier) — open its detail (construction block).
    const builds = page.getByText("Build Agent");
    const bn = await builds.count().catch(() => 0);
    if (bn > 0) { await builds.nth(bn - 1).click({ timeout: 4_000 }).catch(() => {}); await page.waitForTimeout(600); }
    await page.screenshot({ path: join(OUT, `steps-construction__${state}.png`), fullPage: false });
    // A construction task row → L3 task detail.
    const taskRow = page.getByText(/Task\s*1\b/).last();
    if ((await taskRow.count().catch(() => 0)) > 0) { await taskRow.click({ timeout: 4_000 }).catch(() => {}); await page.waitForTimeout(600); }
    await page.screenshot({ path: join(OUT, `steps-task__${state}.png`), fullPage: false });

    // Audit INTERNAL view (settled) — re-open the Audit tab and expand the first
    // log entry so the gallery can pair the "What is this?" + key/value body
    // against our side. The mock's entries are click-handler divs (no roles). The
    // entry meta carries an HH:MM:SS timestamp ("09:00:57") — the attribution row
    // only shows "09:00 UTC" (no seconds) — so match on seconds to hit an ENTRY,
    // not the attribution line.
    await page.getByRole("button", { name: /^Audit$/ }).first().click({ timeout: 6_000 }).catch(() => {});
    await page.waitForTimeout(500);
    const auditEntry = page.getByText(/\d{1,2}:\d{2}:\d{2}/).first();
    if ((await auditEntry.count().catch(() => 0)) > 0) { await auditEntry.click({ timeout: 4_000 }).catch(() => {}); await page.waitForTimeout(600); }
    await page.screenshot({ path: join(OUT, `audit-expanded__${state}.png`), fullPage: false });
  }

  // The Live mock carries clarify/gate/building lane variants behind its own
  // phase scrubber (ND-F — a demo-only control we do NOT reproduce, but it is
  // how the mock exposes those lane compositions). Drive it to capture the
  // clarify + gate target lanes so the gallery can pair our live sub-states.
  if (state === "live") {
    for (const phase of ["Clarify", "Gate"]) {
      const btn = page.getByRole("button", { name: new RegExp(`^${phase}$`, "i") }).first();
      if ((await btn.count()) === 0) continue;
      await btn.click({ timeout: 4_000 }).catch(() => {});
      await page.waitForTimeout(500);
      await page.screenshot({ path: join(OUT, `leftlane__${phase.toLowerCase()}.png`), clip: { x: 0, y: 0, width: 400, height: VIEWPORT.height } });
    }

    // Phase 42 (W0 oracle) — the PAUSED / PLANNING TARGET frames. The Live mock's
    // phase scrubber (ND-F) is how it exposes these paused compositions:
    //   Clarify  → clarify-awaiting (the `clarAwaiting` Steps card + status pill)
    //   Gate     → gate-awaiting    (the `gateAwaiting` Steps row + review pill)
    //   Building → planning proxy    — the mock has NO dedicated pre-agent planning
    //              frame (planning = running & 0 agents in OUR screen); its running
    //              `building` phase is the nearest reference, captured as the
    //              planning target so the gallery has a paired left cell. Documented
    //              in README + flagged in the assembler's W0 register row.
    // `full__{tag}` = whole viewport (lane + right panel); `steps__{tag}` = the
    // Steps surface active (clarify/gate only, mirroring our current side which
    // emits no steps__planning); `leftlane__{tag}` = the conversation column clip.
    const pausedPhases = [
      { label: "Clarify", tag: "clarifyawaiting", steps: true },
      { label: "Gate", tag: "gateawaiting", steps: true },
      { label: "Building", tag: "planning", steps: false },
    ];
    for (const { label, tag, steps } of pausedPhases) {
      const btn = page.getByRole("button", { name: new RegExp(`^${label}$`, "i") }).first();
      if ((await btn.count()) === 0) continue;
      await btn.click({ timeout: 4_000 }).catch(() => {});
      await page.waitForTimeout(500);
      await page.screenshot({ path: join(OUT, `full__${tag}.png`), fullPage: false });
      if (steps) {
        await page.getByRole("button", { name: /^Steps$/ }).first().click({ timeout: 4_000 }).catch(() => {});
        await page.waitForTimeout(400);
        await page.screenshot({ path: join(OUT, `steps__${tag}.png`), fullPage: false });
      }
      await page.screenshot({ path: join(OUT, `leftlane__${tag}.png`), clip: { x: 0, y: 0, width: 400, height: VIEWPORT.height } });
    }
  }

  await page.close();
  console.log(`[capture-mocks] ${state}: captured ${SURFACES.length} tabs + leftlane`);
}

async function main() {
  const stateArg = process.argv.includes("--state")
    ? process.argv[process.argv.indexOf("--state") + 1]
    : null;
  const states = stateArg ? [stateArg] : Object.keys(MOCKS);

  await mkdir(OUT, { recursive: true });
  const { origin, close } = await startMockServer();
  const browser = await chromium.launch();
  try {
    for (const state of states) {
      const file = MOCKS[state];
      if (!file) {
        console.warn(`[capture-mocks] unknown state "${state}" — skipping`);
        continue;
      }
      await capture(state, file, browser, origin).catch((err) =>
        console.error(`[capture-mocks] ${state} FAILED: ${err.message}`),
      );
    }
  } finally {
    await browser.close();
    await close();
  }
  console.log(`[capture-mocks] target shots → ${OUT}`);
}

main();

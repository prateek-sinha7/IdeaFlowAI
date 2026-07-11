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

  // Hydration is done once a real tab button (e.g. "Preview") is on the page.
  await page
    .getByRole("button", { name: /^Preview$/ })
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

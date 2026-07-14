#!/usr/bin/env node
/**
 * capture-shell-mocks.mjs — Phase 40 SCOPING BASELINE (TARGET side).
 *
 * Sibling of `capture-mocks.mjs` (Phase 39). Captures the SHELL surfaces of
 * `Hexaware Workspace v2.dc.html` (Home · Configure/wizard + overlays · Library
 * +Agents/Skills/Hooks +agent-drawer · Catalogue · History · Analytics ·
 * Account Settings) plus the single-surface `Hexaware Composer.dc.html`.
 *
 * Mechanics identical to capture-mocks.mjs: serve `.dc.html` over serve-mocks.mjs,
 * inject React 18 UMD (the DC runtime polls window.React / window.ReactDOM), let
 * `support.js` hydrate, then DRIVE the mock's own nav to each surface. NEEDS
 * NETWORK (Babel + Google fonts from a CDN).
 *
 * DRIVING NOTES (learned by observing the mock, 2026-07-12):
 *   - The global top nav (Home/Library/Catalogue + profile menu) is HIDDEN on the
 *     Config surface (showGlobalBar=false). So capture all nav-reachable surfaces
 *     FIRST, and enter Config LAST.
 *   - Overlays/drawers do NOT close on Escape; each has a full-viewport backdrop
 *     scrim wired to closeAll — click a corner (8,8) to close. To avoid ANY state
 *     bleed, each wizard overlay is captured on a FRESH page load.
 *
 * Output → $PHASE40_OUT/shots/target/{surface}__shell.png (+ __shellfull for the
 * scrolling surfaces). Tag {surface}__shell keeps assemble-gallery's convention.
 *
 * Usage: PHASE40_OUT=/abs node e2e/fidelity/capture-shell-mocks.mjs
 */
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { startMockServer } from "./serve-mocks.mjs";

// Repo-relative default (aligns with assemble-shell-gallery.mjs BASE:
// <base>/target). PHASE40_OUT=/abs overrides the base dir for scratch runs.
const HERE = dirname(fileURLToPath(import.meta.url)); // e2e/fidelity
const OUT = process.env.PHASE40_OUT
  ? join(process.env.PHASE40_OUT, "target")
  : join(HERE, "shots-shell", "target");
const REACT_UMD = "https://unpkg.com/react@18.3.1/umd/react.production.min.js";
const REACT_DOM_UMD = "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js";
const VIEWPORT = { width: 1440, height: 900 };
const WORKSPACE = "Hexaware Workspace v2.dc.html";
const COMPOSER = "Hexaware Composer.dc.html";

const clickBtn = (page, name, t = 5000) =>
  page.getByRole("button", { name: new RegExp(`^${name}$`) }).first().click({ timeout: t }).catch(() => {});
const clickText = (page, re, t = 5000) =>
  page.getByText(re).first().click({ timeout: t }).catch(() => {});
const shot = (page, tag) =>
  page.screenshot({ path: join(OUT, `${tag}__shell.png`), fullPage: false }).catch(() => {});
const shotFull = (page, tag) =>
  page.screenshot({ path: join(OUT, `${tag}__shellfull.png`), fullPage: true }).catch(() => {});
const closeOverlay = (page) => page.mouse.click(8, 8).catch(() => {});
const wait = (page, ms) => page.waitForTimeout(ms);

async function openMock(browser, origin, file) {
  const page = await browser.newPage({ viewport: VIEWPORT });
  await page.goto(`${origin}/${encodeURIComponent(file)}`, { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ url: REACT_UMD }).catch(() => {});
  await page.addScriptTag({ url: REACT_DOM_UMD }).catch(() => {});
  return page;
}
async function hydrate(page) {
  await page
    .getByRole("button", { name: /^(Home|Library|Catalogue)$/ })
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
    .catch(() => {});
  await wait(page, 900);
}
/** From a hydrated Workspace page on Home, open the Config surface. */
async function gotoConfig(page) {
  await clickText(page, /^Build$/);
  await page.getByText("Configure your run").first().waitFor({ state: "visible", timeout: 8000 }).catch(() => {});
  await wait(page, 500);
}
/** Open the profile menu (avatar "AK") then click a menu item by text. */
async function profileTo(page, item) {
  await clickText(page, /^AK$/);
  await wait(page, 350);
  await clickText(page, item);
  await wait(page, 800);
}

async function captureMainSurfaces(browser, origin) {
  const page = await openMock(browser, origin, WORKSPACE);
  await hydrate(page);

  // HOME (default surface)
  await shot(page, "home");
  await shotFull(page, "home");

  // LIBRARY (+ Agents/Skills/Hooks sub-tabs + agent-detail drawer)
  await clickBtn(page, "Library");
  await wait(page, 800);
  await shot(page, "library");
  await shotFull(page, "library");
  for (const [tab, tag] of [["Agents", "library-agents"], ["Skills", "library-skills"], ["Hooks", "library-hooks"]]) {
    await clickText(page, new RegExp(`^${tab}$`));
    await wait(page, 450);
    await shot(page, tag);
  }
  // Agent-detail drawer: back to Agents, click the first library agent card so
  // openDrawer() fires the right-side drawerOpen surface. The card is a clickable
  // <div> (mock :316) whose onClick bubbles from its heading — click the first
  // agent's name text ("Architecture Agent", mock AGENTS[0]); an inline-style
  // attribute selector fails here because the DC runtime normalizes `style` to
  // spaced form. Wait for a drawer-only body label before shooting so the capture
  // shows the drawer OPEN.
  await clickText(page, /^Agents$/);
  await wait(page, 400);
  await page.getByText("Architecture Agent", { exact: true }).first().click({ timeout: 4000 }).catch(() => {});
  await page.getByText("What it does", { exact: true }).first().waitFor({ state: "visible", timeout: 6000 }).catch(() => {});
  await wait(page, 600);
  await shot(page, "agent-detail-drawer");
  await closeOverlay(page);
  await wait(page, 300);

  // CATALOGUE
  await clickBtn(page, "Catalogue");
  await wait(page, 800);
  await shot(page, "catalogue");
  await shotFull(page, "catalogue");

  // HISTORY / ANALYTICS / SETTINGS via the profile menu
  await profileTo(page, /Workflow History/);
  await shot(page, "history");
  await shotFull(page, "history");

  await profileTo(page, /^Analytics$/);
  await shot(page, "analytics");
  await shotFull(page, "analytics");

  await profileTo(page, /Account Settings/);
  await shot(page, "settings");
  await shotFull(page, "settings");
  for (const [tab, tag] of [["AI Model", "settings-model"], ["Usage & Limits", "settings-limits"], ["Constitution", "settings-constitution"]]) {
    await clickText(page, new RegExp(tab));
    await wait(page, 450);
    await shot(page, tag);
  }

  // CONFIG base (nav-away is impossible from Config, so do it last here). Return
  // Home via the nav still present on Settings, then Build → Config.
  await clickBtn(page, "Home");
  await wait(page, 500);
  await gotoConfig(page);
  await shot(page, "config");
  await shotFull(page, "config");

  await page.close();
  console.log("[capture-shell] main surfaces + config captured");
}

/** Each wizard overlay on a FRESH page (no state bleed). */
async function captureOverlay(browser, origin, { card, open, tag }) {
  const page = await openMock(browser, origin, WORKSPACE);
  await hydrate(page);
  await gotoConfig(page);
  if (card) { await clickText(page, new RegExp(`^${card}$`)); await wait(page, 400); }
  await clickText(page, open);
  await wait(page, 700);
  await shot(page, tag);
  await page.close();
  console.log(`[capture-shell] overlay ${tag} captured`);
}

async function captureComposer(browser, origin) {
  const page = await openMock(browser, origin, COMPOSER);
  await wait(page, 2800); // single-surface page; give the runtime time to hydrate.
  await shot(page, "composer");
  await shotFull(page, "composer");
  await page.close();
  console.log("[capture-shell] composer captured");
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const { origin, close } = await startMockServer();
  const browser = await chromium.launch();
  try {
    await captureMainSurfaces(browser, origin).catch((e) => console.error("[capture-shell] main FAILED:", e.message));
    for (const ov of [
      { card: "Templates", open: /Browse full library/, tag: "wizard-template" },
      { card: "Design System", open: /Browse all systems/, tag: "wizard-designsystem" },
      { card: "Review Gates", open: /Open gate manager/, tag: "wizard-gates" },
      { card: null, open: /Workflow Settings/, tag: "wizard-workflowcfg" },
    ]) {
      await captureOverlay(browser, origin, ov).catch((e) => console.error(`[capture-shell] ${ov.tag} FAILED:`, e.message));
    }
    await captureComposer(browser, origin).catch((e) => console.error("[capture-shell] composer FAILED:", e.message));
  } finally {
    await browser.close();
    await close();
  }
  console.log(`[capture-shell] target shots → ${OUT}`);
}

main();

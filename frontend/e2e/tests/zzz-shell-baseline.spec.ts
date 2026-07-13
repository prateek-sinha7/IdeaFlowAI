/**
 * PHASE 40 SHELL FIDELITY CAPTURE (our-side) — scoping baseline, GATED.
 *
 * Sibling of zzz-baseline.spec.ts (Phase 39, which captured the RUN screen).
 * This drives OUR CURRENT shell surfaces via the mocked harness and screenshots
 * each into $PHASE40_OUT/shots/current, tagged `{surface}__shell` (viewport) and
 * `{surface}__shellfull` (fullPage) — the RIGHT column of the side-by-side shell
 * gallery. The LEFT column comes from capture-shell-mocks.mjs (the DC mocks).
 *
 * NOT an assertion suite: gated behind SHELL_CAPTURE=1 so a normal `npm run e2e`
 * skips it (it never gates CI green).
 *   Capture: SHELL_CAPTURE=1 PHASE40_OUT=/abs npm run e2e -- zzz-shell-baseline
 *
 * Navigation (verified against AppHeader.tsx + DashboardLayout mainView machine):
 *   - center nav buttons: "Home" / "Library" / "My Workflows"
 *   - profile menu: click "Account menu" → menuitem "Run History"/"Analytics"/"Account Settings"
 *   - config/brief: Home → select a non-wizard row → "Provide the brief" (mainView input)
 *   - agent-details: on the brief screen → "Advanced" → AgentsPopup "Workflow configuration"
 */
import { test } from "../fixtures/test";
import type { Page } from "@playwright/test";
import { mkdirSync } from "fs";
import { resolve } from "path";

test.skip(!process.env.SHELL_CAPTURE, "shell fidelity capture only (set SHELL_CAPTURE=1)");

// Repo-relative by default (aligns with assemble-shell-gallery.mjs BASE:
// <base>/current). PHASE40_OUT=/abs overrides the base dir for scratch runs.
const OUT = process.env.PHASE40_OUT
  ? resolve(process.env.PHASE40_OUT, "current")
  : resolve(process.cwd(), "e2e/fidelity/shots-shell/current");
mkdirSync(OUT, { recursive: true });

test.use({ viewport: { width: 1440, height: 900 } });

const shot = (page: Page, tag: string) =>
  page.screenshot({ path: `${OUT}/${tag}__shell.png`, fullPage: false }).catch(() => {});
const shotFull = (page: Page, tag: string) =>
  page.screenshot({ path: `${OUT}/${tag}__shellfull.png`, fullPage: true }).catch(() => {});

const clickNav = async (page: Page, name: RegExp) =>
  page.getByRole("button", { name }).first().click({ timeout: 6000 }).catch(() => {});
const clickText = async (page: Page, re: RegExp) =>
  page.getByText(re).first().click({ timeout: 6000 }).catch(() => {});

/** Open the profile menu, then click a menuitem by name. */
async function menu(page: Page, item: RegExp) {
  await page.getByRole("button", { name: "Account menu" }).click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(300);
  await page.getByRole("menuitem", { name: item }).click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(700);
}

test("CAPTURE shell surfaces (home/library/catalogue/history/analytics/settings)", async ({ dashboard, page }) => {
  test.setTimeout(120_000);
  dashboard.seedShell(); // opt-in: populate Catalogue/History/Analytics/recents
  await dashboard.goto(); // lands on Home ("What would you like to build today?")

  // 1) HOME
  await page.waitForTimeout(600);
  await shot(page, "home");
  await shotFull(page, "home");

  // 2) LIBRARY (+ Agents/Skills/Hooks sub-tabs)
  await clickNav(page, /^Library$/);
  await page.waitForTimeout(800);
  await shot(page, "library");
  await shotFull(page, "library");
  for (const [tab, tag] of [["Agents", "library-agents"], ["Skills", "library-skills"], ["Hooks", "library-hooks"]] as const) {
    await page.getByRole("tab", { name: new RegExp(tab, "i") }).first().click({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(450);
    await shot(page, tag);
  }
  // Agent-detail: click the first agent card/row in Library>Agents (best-effort).
  await page.getByRole("tab", { name: /Agents/i }).first().click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: /Writer|Planner|Analyzer|Builder|Agent/i }).first().click({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(500);
  await shot(page, "library-agent-detail");

  // 3) RUN HISTORY (mock "Workflow History") — capture the nav-menu surfaces
  //    BEFORE "My Workflows", which crashes in mocked mode (see below) and would
  //    otherwise leave a Next error overlay swallowing every later click.
  await menu(page, /Run History/);
  await shot(page, "history");
  await shotFull(page, "history");

  // 5) ANALYTICS
  await menu(page, /Analytics/);
  await shot(page, "analytics");
  await shotFull(page, "analytics");

  // 6) ACCOUNT SETTINGS (+ Model/Limits/Constitution sub-tabs)
  await menu(page, /Account Settings/);
  await shot(page, "settings");
  await shotFull(page, "settings");
  for (const [tab, tag] of [["Model", "settings-model"], ["Limits", "settings-limits"], ["Constitution", "settings-constitution"]] as const) {
    await page.getByRole("tab", { name: new RegExp(tab, "i") }).first().click({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(450);
    await shot(page, tag);
  }

  // 7) MY WORKFLOWS (mock "Workflow Catalogue"; app relabel D-11) — LAST because
  //    SavedWorkflowsPage crashes in mocked mode: GET /api/user-workflows is
  //    unstubbed (mockApi catch-all returns {}), so userWorkflows.filter throws
  //    (SavedWorkflowsPage.tsx:170). The captured shot documents that blocker.
  await clickNav(page, /^My Workflows$/);
  await page.waitForTimeout(800);
  await shot(page, "catalogue");
  await shotFull(page, "catalogue");
});

test("CAPTURE configure/brief + agent-details (Workflow configuration popup)", async ({ dashboard, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();

  // CONFIG / brief — select a non-wizard row (user_stories → mainView "input").
  await page.getByRole("button", { name: /Generate product requirements/i }).first().click({ timeout: 8000 }).catch(() => {});
  await page.getByRole("heading", { name: /Provide the brief/i }).waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
  await page.locator("textarea").first().fill("A kanban board for a 5-person growth squad — backlog, doing, review, done.").catch(() => {});
  await page.waitForTimeout(500);
  await shot(page, "config");
  await shotFull(page, "config");

  // Review gates section lives inline on the brief screen — scroll to it.
  await clickText(page, /Review gates/i);
  await page.waitForTimeout(400);
  await shotFull(page, "config-gates");

  // AGENT-DETAILS — "Advanced" opens AgentsPopup ("Workflow configuration").
  await page.getByRole("button", { name: /^Advanced/ }).first().click({ timeout: 6000 }).catch(() => {});
  await page.getByText(/Workflow configuration/i).first().waitFor({ state: "visible", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(600);
  await shot(page, "agent-detail");
  await shotFull(page, "agent-detail");
  // Expand a per-agent "Advanced — {name}" row for the agent-detail expander.
  await page.getByRole("button", { name: /Advanced —/ }).first().click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(500);
  await shotFull(page, "agent-detail-expanded");
});

/**
 * PHASE 41 (HARN-01) — Configure + Composer capture drivers, GUARDED.
 *
 * Drives OUR new Phase-41 surfaces (the unified Configure screen + its
 * Workflow-Settings overlay, the Composer Simple view, the Composer Canvas view)
 * into shots-shell/current under the tags the Phase-41 assembler reads:
 *   config__shell · config-settings__shellfull · composer-simple__shell ·
 *   composer-canvas__shell.
 *
 * These surfaces are built in Waves 2–6; this driver is TOLERANT — it best-effort
 * navigates and only screenshots when the surface is actually reachable (`reached`
 * guard), so it no-ops cleanly while the surfaces don't yet exist and the spec
 * stays green. It installs the OPT-IN seeded template/DS/ppt data (seedConfigure)
 * so the Templates/Design-System overlays render POPULATED once the surface lands.
 */
test("CAPTURE phase-41 configure + composer surfaces (guarded, no-op until built)", async ({ dashboard, page }) => {
  test.setTimeout(120_000);
  dashboard.seedConfigure(); // opt-in: populate the Templates/Design-System overlays
  await dashboard.goto();

  // Only shoot when a distinguishing marker is on screen, so an unbuilt surface
  // writes NO shot (the assembler then shows a "not built yet" placeholder).
  const reached = async (marker: RegExp) =>
    page.getByText(marker).first().isVisible({ timeout: 1500 }).catch(() => false);

  // 1) UNIFIED CONFIGURE — Wave 2/3 land it at mainView='configure' (or a route).
  //    Best-effort: try an in-app entry, then check for the Configure marker.
  await page.getByRole("button", { name: /Build an interactive prototype/i }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(600);
  if (await reached(/Configure your run|Set up your run|Set up /i)) {
    await shot(page, "config");
    await shotFull(page, "config");
    // Workflow Settings accordion/overlay → config-settings__shellfull.
    await clickText(page, /Workflow Settings/i);
    await page.waitForTimeout(400);
    await shotFull(page, "config-settings");
  }

  // 2) COMPOSER Simple view — Wave 4 lands a full-page mainView='composer'.
  await dashboard.goto(); // reset to Home
  await page.getByRole("button", { name: /Compose a custom workflow/i }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(600);
  if (await reached(/Compose|Composer|Add agents|Summary/i)) {
    // Ensure the Simple view is active if a Simple⇄Canvas toggle exists.
    await page.getByRole("button", { name: /^Simple$/ }).first().click({ timeout: 2500 }).catch(() => {});
    await page.waitForTimeout(300);
    await shot(page, "composer-simple");
    await shotFull(page, "composer-simple");

    // 3) COMPOSER Canvas view — Wave 5. Toggle to Canvas, then capture.
    await page.getByRole("button", { name: /^Canvas$/ }).first().click({ timeout: 2500 }).catch(() => {});
    await page.waitForTimeout(400);
    if (await reached(/Canvas|Fit|Run summary/i)) {
      await shot(page, "composer-canvas");
      await shotFull(page, "composer-canvas");
    }
  }
});

/**
 * TS-B — Workflow selection / CreationHub (TEST-REGISTER §3).
 * Proves the 6 CreationHub rows route correctly: four open the in-page
 * IdeaInputPage (assert its <h1> heading per TYPE_CONFIG), while prototype/ppt
 * HARD-NAVIGATE via router.push to their template wizards (assert the URL).
 *
 * All rows are exercised at the `enterprise` tier so every workflow is enabled
 * (see entitlements.ts: only enterprise unlocks custom + migration).
 */
import { test, expect } from "../fixtures/test";

test.describe("TS-B — workflow selection", () => {
  test.beforeEach(async ({ dashboard }) => {
    // enterprise → every row enabled (custom/migration require enterprise).
    await dashboard.goto({ tier: "enterprise" });
  });

  test("TS-B-01 'Generate product requirements' opens the brief input view", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Generate product requirements");
    // IdeaInputPage heading for user_stories (TYPE_CONFIG.user_stories.heading).
    await expect(page.getByRole("heading", { name: "Provide the brief" })).toBeVisible();
  });

  test("TS-B-02 'Pitch an idea' hard-navigates to the PPT template wizard", async ({ dashboard, page }) => {
    // ppt routes to /create/ppt (015-frontend-routing; the legacy
    // /workflow/create?mode=ppt redirects there) — NOT an input view.
    await dashboard.selectWorkflow("Pitch an idea");
    await page.waitForURL(/\/create\/ppt(\?|$)/);
  });

  test("TS-B-03 'Build an interactive prototype' hard-navigates to the prototype template wizard", async ({ dashboard, page }) => {
    // prototype routes to /create/prototype (015-frontend-routing) — NOT an input view.
    await dashboard.selectWorkflow("Build an interactive prototype");
    await page.waitForURL(/\/create\/prototype(\?|$)/);
  });

  test("TS-B-04 'Build an end-to-end application' opens the application input view", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Build an end-to-end application");
    // IdeaInputPage heading for app_builder (TYPE_CONFIG.app_builder.heading).
    await expect(page.getByRole("heading", { name: "Describe the application" })).toBeVisible();
  });

  // RE-ANCHORED (40-02): the data-driven home (GET /api/workflows) serves
  // "Platform workflows" as the CONCRETE `mulesoft_to_springboot` id (fixtures
  // DEFAULT_WORKFLOWS), so selecting it opens the concrete "Modernise off
  // Mulesoft" input DIRECTLY. The removed behaviors are flagged, not asserted:
  //   • the `migration` META meta-picker ("Modernise a legacy estate" heading +
  //     "Choose your migration path" + the two sub-pipeline tiles) still exists
  //     in IdeaInputPage but has NO home entry point in the data-driven catalog;
  //   • the NEW pill is gone (the card grid carries no badge field).
  // The load-bearing behavior — selecting the platform card LAUNCHES its concrete
  // migration input — is preserved and asserted below.
  test("TS-B-05 'Platform workflows' opens the concrete Mulesoft migration input", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Platform workflows");

    // IdeaInputPage heading for the concrete mulesoft_to_springboot pipeline
    // (TYPE_CONFIG.mulesoft_to_springboot.heading) — reached directly, no picker.
    await expect(page.getByRole("heading", { name: "Modernise off Mulesoft" })).toBeVisible();
    // The Run control is present for the concrete pipeline (13 agents seeded).
    await expect(dashboard.runButton()).toBeVisible();
  });

  // RE-ANCHORED: since 41-04 (e1490fad, D-CMP-ENTRY) the custom row no longer
  // opens IdeaInputPage ("Describe the task" heading, itself renamed by KAN-112
  // 7732c79a) — DashboardLayout.handleSelectFeature routes COMPOSER_ENABLED_TYPES
  // ("custom") to the full-page Composer at /workflows/new. The custom task-input
  // view is now the Composer: its "Custom · Composer" header + the brief field.
  test("TS-B-06 'Compose a custom workflow' opens the custom task input view", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Compose a custom workflow");
    await page.waitForURL(/\/workflows\/new$/);
    await expect(dashboard.composerEyebrow()).toBeVisible();
    await expect(dashboard.composerNameInput()).toBeVisible();
    // The task input the custom view exists to collect.
    await expect(dashboard.composerBrief()).toBeVisible();
    await expect(dashboard.composerBrief()).toBeEditable();
  });

  test("TS-B-07 workflow rows are focusable, enabled buttons (hover affordance proxy)", async ({ page }) => {
    // The hover highlight is a CSS-only affordance that can't be asserted
    // deterministically; instead assert the row is a real enabled, focusable
    // <button> the user can activate. Scope to the launch row via its <h2> child
    // — the Phase-39 home row's sibling "Inspect …" Info button shares the label
    // in its aria-label (strict-mode-safe).
    const row = page
      .getByRole("button")
      .filter({ has: page.getByRole("heading", { level: 2, name: /Generate product requirements/i }) });
    await expect(row).toBeEnabled();
    await row.focus();
    await expect(row).toBeFocused();
  });
});
